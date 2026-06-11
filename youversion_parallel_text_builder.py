"""
YouVersion Bible Parallel Text Dataset Builder  (English ↔ Local language)
===========================================================================
HTTP-only version — uses requests + BeautifulSoup instead of Selenium/Chrome.

No Chrome required. Each worker is a lightweight requests.Session (~1 MB)
instead of a browser instance (~400 MB), so you can safely run 20-30
parallel workers on a normal laptop.

Works because bible.com (Next.js) server-side renders verse content into
the initial HTML response — no JavaScript execution needed.

If you ever see 0 pairs and lots of "empty" results, the site may have
switched to client-side rendering for your IP/region; in that case fall
back to youversion_parallel_text_builder.py (Selenium).

OUTPUT LAYOUT
-------------
    {OUTPUT_ROOT}/
        progress.json
        testament_status.json
        english_cache.csv
        {LANG_NAME}_{LANG_CODE}_v{VERSION_ID}.csv

CSV columns in versions file:  version_id, lang_code, lang_name, abbr  (abbr optional)
Requires: requests, beautifulsoup4, lxml
"""

import sys
import subprocess
import os

# ─────────────────────────────────────────────
# BOOTSTRAP
# ─────────────────────────────────────────────

REQUIRED_PACKAGES = [
    "requests",
    "beautifulsoup4",
    "lxml",
    "pandas",
    "datasets",
    "huggingface_hub",
]

def _install_packages():
    import_names = {
        "beautifulsoup4": "bs4",
        "huggingface_hub": "huggingface_hub",
    }
    missing = []
    for pkg in REQUIRED_PACKAGES:
        import_name = import_names.get(pkg, pkg)
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"\n  Installing missing packages: {', '.join(missing)} ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet"] + missing)
        print("  Packages installed.\n")

_install_packages()

# ── Imports ───────────────────────────────────────────────────────────────────
import csv
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue

import requests
from bs4 import BeautifulSoup


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

VERSIONS_CSV = "youversion_ghana_versions.csv"

ENGLISH_VERSION_NUM = 37
ENGLISH_ABBR        = "CEB"

VERSE_SELECTOR = "p.text-17"

# More workers are fine — sessions are ~1 MB, not ~400 MB like browsers.
# Stay moderate to avoid rate-limiting from bible.com.
NUM_WORKERS = 16

# Polite delay between requests per worker (seconds).
REQUEST_DELAY = 2

REQUEST_TIMEOUT = 30   # seconds per HTTP request
MAX_RETRIES     = 3
RETRY_WAIT      = 3

# Fake a real browser so the server returns normal HTML
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

ALL_BOOK_CODES = [
    "GEN","EXO","LEV","NUM","DEU","JOS","JDG","RUT","1SA","2SA",
    "1KI","2KI","1CH","2CH","EZR","NEH","EST","JOB","PSA","PRO",
    "ECC","SNG","ISA","JER","LAM","EZK","DAN","HOS","JOL","AMO",
    "OBA","JON","MIC","NAM","HAB","ZEP","HAG","ZEC","MAL",
    "MAT","MRK","LUK","JHN","ACT","ROM","1CO","2CO","GAL","EPH",
    "PHP","COL","1TH","2TH","1TI","2TI","TIT","PHM","HEB","JAS",
    "1PE","2PE","1JN","2JN","3JN","JUD","REV",
]

BOOK_CHAPTERS = {
    "GEN":50,"EXO":40,"LEV":27,"NUM":36,"DEU":34,"JOS":24,"JDG":21,
    "RUT":4,"1SA":31,"2SA":24,"1KI":22,"2KI":25,"1CH":29,"2CH":36,
    "EZR":10,"NEH":13,"EST":10,"JOB":42,"PSA":150,"PRO":31,"ECC":12,
    "SNG":8,"ISA":66,"JER":52,"LAM":5,"EZK":48,"DAN":12,"HOS":14,
    "JOL":3,"AMO":9,"OBA":1,"JON":4,"MIC":7,"NAM":3,"HAB":3,"ZEP":3,
    "HAG":2,"ZEC":14,"MAL":4,
    "MAT":28,"MRK":16,"LUK":24,"JHN":21,"ACT":28,"ROM":16,"1CO":16,
    "2CO":13,"GAL":6,"EPH":6,"PHP":4,"COL":4,"1TH":5,"2TH":3,"1TI":6,
    "2TI":4,"TIT":3,"PHM":1,"HEB":13,"JAS":5,"1PE":5,"2PE":3,"1JN":5,
    "2JN":1,"3JN":1,"JUD":1,"REV":22,
}

OUTPUT_ROOT           = "./bible_parallel_text_datasets"
PROGRESS_FILE         = os.path.join(OUTPUT_ROOT, "progress.json")
TESTAMENT_STATUS_FILE = os.path.join(OUTPUT_ROOT, "testament_status.json")
ENGLISH_CACHE_CSV     = os.path.join(OUTPUT_ROOT, "english_cache.csv")

CSV_FIELDNAMES = ["verse_key", "version_id", "eng", "local"]

STOP_AFTER_EMPTY_VERSES = 2
MAX_VERSES_PER_CHAPTER  = 200
CHAPTER_DONE_SUFFIX     = ".__done__"

# ── Locks ─────────────────────────────────────────────────────────────────────
PROG_LOCK    = threading.Lock()
EN_CSV_LOCK  = threading.Lock()

_CSV_LOCKS:      dict[str, threading.Lock] = {}
_CSV_LOCKS_META = threading.Lock()

def get_lang_csv_lock(csv_name: str) -> threading.Lock:
    with _CSV_LOCKS_META:
        if csv_name not in _CSV_LOCKS:
            _CSV_LOCKS[csv_name] = threading.Lock()
        return _CSV_LOCKS[csv_name]


# ─────────────────────────────────────────────
# TEXT CLEANING  (unchanged from Selenium version)
# ─────────────────────────────────────────────

def clean_text(text: str) -> str:
    text = re.sub(r'\([^)]*\)', '', text)
    text = re.sub(r'\d+', '', text)
    lines = text.splitlines()
    processed = []
    for line in lines:
        line = line.strip()
        if line:
            if line[-1] not in ['.', '!', '?', ':', ';']:
                line += '.'
            processed.append(line)
    text = ' '.join(processed)
    text = re.sub(r'[\"\""''\(\)\[\]\{\}]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'[,.]{2,}', '.', text)
    text = re.sub(r'([,.!?;:])\.', '.', text)
    if text and not text.endswith('.'):
        text += '.'
    return text


# ─────────────────────────────────────────────
# ENGLISH CACHE
# ─────────────────────────────────────────────

_en_cache: dict[str, str] = {}
_en_cache_loaded = False
_en_cache_lock   = threading.Lock()

def _load_en_cache_once():
    global _en_cache_loaded
    with _en_cache_lock:
        if _en_cache_loaded:
            return
        if os.path.exists(ENGLISH_CACHE_CSV):
            with open(ENGLISH_CACHE_CSV, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    _en_cache[row["verse_key"]] = row.get("eng", "")
        _en_cache_loaded = True

def _append_en_cache_row(verse_key: str, eng: str):
    with EN_CSV_LOCK:
        os.makedirs(OUTPUT_ROOT, exist_ok=True)
        write_header = not os.path.exists(ENGLISH_CACHE_CSV)
        with open(ENGLISH_CACHE_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["verse_key", "eng"])
            if write_header:
                writer.writeheader()
            writer.writerow({"verse_key": verse_key, "eng": eng})
        _en_cache[verse_key] = eng


# ─────────────────────────────────────────────
# HTTP VERSE FETCHING  (replaces Selenium driver calls)
# ─────────────────────────────────────────────

def get_verse_text(session: requests.Session, version_num: int, book: str,
                   chapter: int, verse: int, abbr: str | None = None) -> str | None:
    suffix = f".{abbr}" if abbr else ""
    url = f"https://www.bible.com/bible/{version_num}/{book}.{chapter}.{verse}{suffix}"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(REQUEST_DELAY)
            resp = session.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            paras = soup.select(VERSE_SELECTOR)
            texts = [p.get_text(separator=" ", strip=True) for p in paras if p.get_text(strip=True)]
            if texts:
                return "\n".join(texts)
            return None
        except Exception:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_WAIT)
            else:
                return None
    return None


def get_english_verse(session: requests.Session, book: str, chapter: int, verse: int) -> str | None:
    _load_en_cache_once()
    key = f"{book}.{chapter}.{verse}"
    with _en_cache_lock:
        if key in _en_cache:
            return _en_cache[key] or None
    raw     = get_verse_text(session, ENGLISH_VERSION_NUM, book, chapter, verse, ENGLISH_ABBR)
    cleaned = clean_text(raw) if raw and raw.strip() else ""
    _append_en_cache_row(key, cleaned)
    return cleaned or None


# ─────────────────────────────────────────────
# PROGRESS
# ─────────────────────────────────────────────

def load_global_progress() -> dict:
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {int(k): v for k, v in data.items()}
    return {}

def save_global_progress_locked(progress: dict):
    os.makedirs(OUTPUT_ROOT, exist_ok=True)
    out = {str(k): v for k, v in progress.items()}
    tmp = PROGRESS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    os.replace(tmp, PROGRESS_FILE)

def mark_verse_done(version_num, key, progress_dict, done_set):
    with PROG_LOCK:
        done_set.add(key)
        progress_dict[version_num] = list(done_set)

def is_done(key, done_set) -> bool:
    with PROG_LOCK:
        return key in done_set

def is_chapter_done(book, chapter, done_set) -> bool:
    with PROG_LOCK:
        return f"{book}.{chapter}{CHAPTER_DONE_SUFFIX}" in done_set

def mark_chapter_done(version_num, book, chapter, progress_dict, done_set):
    with PROG_LOCK:
        done_set.add(f"{book}.{chapter}{CHAPTER_DONE_SUFFIX}")
        progress_dict[version_num] = list(done_set)

def flush_progress(progress_dict):
    with PROG_LOCK:
        save_global_progress_locked(progress_dict)


# ─────────────────────────────────────────────
# TESTAMENT STATUS
# ─────────────────────────────────────────────

def load_testament_status() -> dict:
    if os.path.exists(TESTAMENT_STATUS_FILE):
        with open(TESTAMENT_STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {int(k): v for k, v in data.items()}
    return {}

def save_testament_status(status: dict):
    os.makedirs(OUTPUT_ROOT, exist_ok=True)
    out = {str(k): v for k, v in status.items()}
    with open(TESTAMENT_STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)


# ─────────────────────────────────────────────
# CSV HELPERS
# ─────────────────────────────────────────────

def lang_csv_name(lang_name: str, lang_code: str, version_num: int) -> str:
    return f"{lang_name}_{lang_code}_v{version_num}".replace(" ", "_").replace("/", "-") + ".csv"

def lang_csv_path(lang_name: str, lang_code: str, version_num: int) -> str:
    return os.path.join(OUTPUT_ROOT, lang_csv_name(lang_name, lang_code, version_num))

def save_parallel_pair(key: str, version_num: int, en_text: str,
                       local_text: str, csv_path: str) -> bool:
    lock = get_lang_csv_lock(csv_path)
    os.makedirs(OUTPUT_ROOT, exist_ok=True)
    with lock:
        write_header = not os.path.exists(csv_path)
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
            if write_header:
                writer.writeheader()
            writer.writerow({
                "verse_key":  key,
                "version_id": version_num,
                "eng":        en_text,
                "local":      local_text,
            })
    return True


# ─────────────────────────────────────────────
# VERSE HANDLER
# ─────────────────────────────────────────────

def try_save_verse(book, chapter, verse, version_num, session, abbr,
                   csv_path, progress_dict, done_set, stats) -> str:
    key = f"{book}.{chapter}.{verse}"

    raw_local  = get_verse_text(session, version_num, book, chapter, verse, abbr)
    local_text = clean_text(raw_local) if raw_local else ""
    if not local_text:
        return "empty"

    en_text = get_english_verse(session, book, chapter, verse)
    if not en_text:
        mark_verse_done(version_num, key, progress_dict, done_set)
        stats["missing"] += 1
        return "missing"

    save_parallel_pair(key, version_num, en_text, local_text, csv_path)
    mark_verse_done(version_num, key, progress_dict, done_set)
    stats["parallel"] += 1
    print(f"    + {key}")
    return "pair"


# ─────────────────────────────────────────────
# CHAPTER WORKER  (uses a session from the pool instead of a browser)
# ─────────────────────────────────────────────

def process_chapter(book, chapter, version_num, abbr, csv_path,
                    progress_dict, done_set, session_queue: Queue):
    stats = {"parallel": 0, "skipped": 0, "missing": 0}
    session = session_queue.get()
    chapter_finished = False
    try:
        consecutive_empty = 0
        for verse in range(1, MAX_VERSES_PER_CHAPTER + 1):
            key = f"{book}.{chapter}.{verse}"
            if is_done(key, done_set):
                stats["skipped"] += 1
                consecutive_empty = 0
                continue
            result = try_save_verse(book, chapter, verse, version_num, session,
                                    abbr, csv_path, progress_dict, done_set, stats)
            if result == "empty":
                consecutive_empty += 1
                if consecutive_empty >= STOP_AFTER_EMPTY_VERSES:
                    chapter_finished = True
                    break
            else:
                consecutive_empty = 0
    finally:
        session_queue.put(session)

    if chapter_finished:
        mark_chapter_done(version_num, book, chapter, progress_dict, done_set)
    flush_progress(progress_dict)
    return stats


# ─────────────────────────────────────────────
# PROBE TESTAMENT
# ─────────────────────────────────────────────

def probe_testament(label, probe_books, version_num, progress_dict, done_set,
                    stats, session, csv_path, abbr) -> bool:
    book      = probe_books[0]
    confirmed = 0
    for verse in (1, 2):
        key = f"{book}.1.{verse}"
        if is_done(key, done_set):
            if os.path.exists(csv_path):
                print(f"  [{label} probe] {key} already done.")
                confirmed += 1
            continue
        print(f"  [{label} probe] {key}")
        result = try_save_verse(book, 1, verse, version_num, session, abbr,
                                csv_path, progress_dict, done_set, stats)
        if result == "pair":
            confirmed += 1
        elif result == "empty":
            mark_verse_done(version_num, key, progress_dict, done_set)
            stats["missing"] += 1
    return confirmed > 0


# ─────────────────────────────────────────────
# SESSION POOL  (replaces Chrome driver pool)
# ─────────────────────────────────────────────

def build_session_pool(n: int) -> Queue:
    q = Queue()
    for i in range(n):
        s = requests.Session()
        s.headers.update(REQUEST_HEADERS)
        q.put(s)
    print(f"  {n} HTTP sessions ready (no browsers needed)")
    return q


# ─────────────────────────────────────────────
# MAIN PER-VERSION PROCESSING
# ─────────────────────────────────────────────

def build_dataset_for_bible(version_num, lang_code, lang_name, abbr,
                            session_queue, progress_dict, testament_status):
    print(f"\n{'='*60}")
    print(f"  Processing: {lang_name} ({lang_code}) — version {version_num}"
          f"{' / ' + abbr if abbr else ''}")
    print(f"{'='*60}")

    csv_path = lang_csv_path(lang_name, lang_code, version_num)
    done_set = set(progress_dict.get(version_num, []))
    stats    = {"parallel": 0, "skipped": 0, "missing": 0}

    OT_BOOKS = ALL_BOOK_CODES[:39]
    NT_BOOKS = ALL_BOOK_CODES[39:]
    cached   = testament_status.get(version_num)

    # ── Probe phase ──────────────────────────────────────────────────────────
    probe_session = session_queue.get()
    try:
        if cached and "ot" in cached:
            ot_ok = cached["ot"]
            print(f"\n  OT probe cached ({'ok' if ot_ok else 'skip'}).")
        else:
            print(f"\n  Probing OT (GEN 1:1–1:2)...")
            ot_ok = probe_testament("OT", OT_BOOKS, version_num, progress_dict,
                                    done_set, stats, probe_session, csv_path, abbr)
            testament_status.setdefault(version_num, {})["ot"] = ot_ok
            save_testament_status(testament_status)

        if cached and "nt" in cached:
            nt_ok = cached["nt"]
            print(f"  NT probe cached ({'ok' if nt_ok else 'skip'}).")
        else:
            print(f"  Probing NT (MAT 1:1–1:2)...")
            nt_ok = probe_testament("NT", NT_BOOKS, version_num, progress_dict,
                                    done_set, stats, probe_session, csv_path, abbr)
            testament_status.setdefault(version_num, {})["nt"] = nt_ok
            save_testament_status(testament_status)
    finally:
        session_queue.put(probe_session)

    flush_progress(progress_dict)
    print(f"  OT: {'process' if ot_ok else 'skip'} | NT: {'process' if nt_ok else 'skip'}")

    if not ot_ok and not nt_ok:
        print(f"  No content found — skipping {lang_name} ({lang_code}).")
        return stats

    # ── Chapter task list ─────────────────────────────────────────────────────
    tasks = []
    skipped_chapters = 0
    for book in ALL_BOOK_CODES:
        in_ot = book in OT_BOOKS
        if (in_ot and not ot_ok) or (not in_ot and not nt_ok):
            continue
        for chapter in range(1, BOOK_CHAPTERS.get(book, 0) + 1):
            if is_chapter_done(book, chapter, done_set):
                skipped_chapters += 1
            else:
                tasks.append((book, chapter))

    if skipped_chapters:
        print(f"  Skipped {skipped_chapters} already-completed chapters")

    workers = min(NUM_WORKERS, session_queue.qsize())
    print(f"  Processing {len(tasks)} chapters across {workers} workers...")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(process_chapter, book, chapter, version_num, abbr,
                        csv_path, progress_dict, done_set, session_queue):
                (book, chapter)
            for book, chapter in tasks
        }
        for fut in as_completed(futures):
            book, chapter = futures[fut]
            try:
                cs = fut.result()
                stats["parallel"] += cs["parallel"]
                stats["skipped"]  += cs["skipped"]
                stats["missing"]  += cs["missing"]
                print(f"  {book}.{chapter} done "
                      f"(+{cs['parallel']} pairs, {cs['missing']} missing)")
            except Exception as e:
                print(f"  {book}.{chapter} failed: {e}")

    flush_progress(progress_dict)
    print(f"\n  {lang_name} ({lang_code}) v{version_num} Summary:")
    print(f"     Parallel pairs saved  : {stats['parallel']}")
    print(f"     Already done          : {stats['skipped']}")
    print(f"     Missing on one side   : {stats['missing']}")
    print(f"     Output CSV            : {csv_path}")
    return stats


# ─────────────────────────────────────────────
# VERSIONS CSV & LANGUAGE SELECTION
# ─────────────────────────────────────────────

def load_versions_csv(csv_path: str) -> list:
    entries = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            vid = row["version_id"].strip()
            if not vid.isdigit():
                continue
            if row.get("viable", "").strip().lower() == "false":
                continue
            abbr = row.get("abbr", "").strip() or None
            entries.append((int(vid), row["lang_code"].strip(),
                            row["lang_name"].strip(), abbr))
    return entries


def prompt_language_selection(entries: list) -> list:
    available_by_id = {vid: (vid, lc, ln, ab) for (vid, lc, ln, ab) in entries}
    while True:
        raw = input("\n  Enter your version ID (or 'q' to quit): ").strip()
        if raw.lower() in ("q", "quit", "exit"):
            print("\n  Bye!\n")
            sys.exit(0)
        if not raw.isdigit():
            print("  Please enter a numeric version ID, or 'q' to quit.\n")
            continue
        vid = int(raw)
        if vid not in available_by_id:
            print(f"  Version {vid} was not found in the versions CSV.\n")
            continue
        entry = available_by_id[vid]
        _, lang_code, lang_name, abbr = entry
        abbr_str = f" ({abbr})" if abbr else ""
        print(f"\n  Starting scrape for {lang_name}{abbr_str} [{lang_code}]...\n")
        return [entry]


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    all_entries = load_versions_csv(VERSIONS_CSV)
    if not all_entries:
        print("No viable versions found in CSV. Exiting.")
        return

    print(f"Loaded {len(all_entries)} viable language version(s) from {VERSIONS_CSV}")
    selected_entries = prompt_language_selection(all_entries)
    if not selected_entries:
        print("No languages selected. Exiting.")
        return

    print(f"\nSpinning up {NUM_WORKERS} HTTP sessions (no browsers needed)...")
    session_queue = build_session_pool(NUM_WORKERS)

    progress         = load_global_progress()
    testament_status = load_testament_status()
    grand_total      = 0

    for version_num, lang_code, lang_name, abbr in selected_entries:
        stats = build_dataset_for_bible(
            version_num, lang_code, lang_name, abbr,
            session_queue, progress, testament_status,
        )
        grand_total += stats["parallel"]

    print(f"\nAll done!  Total parallel pairs: {grand_total}")
    print(f"   Output root   : {os.path.abspath(OUTPUT_ROOT)}")
    print(f"   English cache : {os.path.abspath(ENGLISH_CACHE_CSV)}")
    print(f"   Progress file : {os.path.abspath(PROGRESS_FILE)}")


if __name__ == "__main__":
    main()
