"""
YouVersion Bible Parallel Text Dataset Builder  (English ↔ Local language)
===========================================================================
HTTP-only, chapter-level edition.

Instead of one HTTP request per verse (~30 per chapter), this version fetches
one chapter at a time from bible.com's internal JSON API and splits it into
verses using the data-usfm markers in the returned HTML.  That is ~30× fewer
requests for the local language, and near-zero extra requests for English
(verses are batch-cached the first time a chapter is fetched and reused for
every subsequent language).

API endpoint:
    https://nodejs.bible.com/api/bible/chapter/3.1?id={version}&reference={BOOK}.{ch}

The public www.bible.com HTML pages now serve a JavaScript bot-challenge shell
to plain HTTP clients, so we hit the JSON API directly instead — it needs only
the numeric version id and a "BOOK.chapter" reference (no version abbreviation)
and returns clean per-verse content.

No Chrome / Selenium required.

OUTPUT LAYOUT
-------------
    {OUTPUT_ROOT}/
        progress.json
        testament_status.json
        english_cache.csv
        {LANG_NAME}_{LANG_CODE}_v{VERSION_ID}.csv

CSV columns in versions file:  version_id, lang_code, lang_name, viable, abbr
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
    import_names = {"beautifulsoup4": "bs4", "huggingface_hub": "huggingface_hub"}
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            __import__(import_names.get(pkg, pkg))
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

NUM_WORKERS     = 16
REQUEST_DELAY   = 2      # seconds between requests per worker
REQUEST_TIMEOUT = 20
MAX_RETRIES     = 3
RETRY_WAIT      = 5

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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

CSV_FIELDNAMES      = ["verse_key", "version_id", "eng", "local"]
CHAPTER_DONE_SUFFIX = ".__done__"

# ── Locks ─────────────────────────────────────────────────────────────────────
PROG_LOCK    = threading.Lock()
EN_CSV_LOCK  = threading.Lock()

_CSV_LOCKS:      dict[str, threading.Lock] = {}
_CSV_LOCKS_META = threading.Lock()

def get_lang_csv_lock(csv_path: str) -> threading.Lock:
    with _CSV_LOCKS_META:
        if csv_path not in _CSV_LOCKS:
            _CSV_LOCKS[csv_path] = threading.Lock()
        return _CSV_LOCKS[csv_path]


# ─────────────────────────────────────────────
# TEXT CLEANING
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
    text = re.sub(r'[\"“”‘’\(\)\[\]\{\}]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'[,.]{2,}', '.', text)
    text = re.sub(r'([,.!?;:])\.', '.', text)
    if text and not text.endswith('.'):
        text += '.'
    return text


# ─────────────────────────────────────────────
# CHAPTER-LEVEL FETCHING  (YouVersion JSON API)
# ─────────────────────────────────────────────
#
# We use bible.com's internal chapter API instead of scraping the public
# www.bible.com HTML, which now serves a JavaScript bot-challenge shell to
# plain HTTP clients.  The API returns the whole chapter as one JSON payload
# whose `content` field is clean per-verse HTML:
#
#   <span class="verse v1" data-usfm="GEN.1.1">
#       <span class="label">1</span>
#       <span class="content">In the beginning ...</span>
#   </span>
#
# Selecting span.content excludes verse-number labels and footnotes, so the
# extracted text is already clean.  No version abbreviation is required —
# just the numeric version id and a "BOOK.chapter" reference.

CHAPTER_API = "https://nodejs.bible.com/api/bible/chapter/3.1"


def _parse_chapter_content(content_html: str, book: str, chapter: int) -> dict[int, str]:
    """Return {verse_num: raw_text} from a chapter API `content` HTML blob."""
    soup = BeautifulSoup(content_html, "lxml")
    prefix = f"{book}.{chapter}."
    parts: dict[int, list[str]] = {}

    for span in soup.find_all("span", attrs={"data-usfm": True}):
        usfm = span["data-usfm"]
        if not usfm.startswith(prefix):
            continue
        tail = usfm[len(prefix):]
        # Handle ranges/combined verses like "1-3" or "1+2" — key on the first.
        try:
            verse_num = int(re.split(r"[-+]", tail)[0])
        except ValueError:
            continue
        # Prefer the inner content spans (they exclude labels/footnotes).
        content_spans = span.select("span.content")
        if content_spans:
            text = " ".join(c.get_text(" ", strip=True) for c in content_spans)
        else:
            text = span.get_text(" ", strip=True)
        text = text.strip()
        if text:
            parts.setdefault(verse_num, []).append(text)

    return {n: " ".join(chunks) for n, chunks in parts.items()}


def get_chapter_verses(session: requests.Session, version_num: int, book: str,
                       chapter: int, abbr: str | None = None) -> dict[int, str] | None:
    """
    Fetch one chapter via the JSON API and return {verse_num: raw_text}.
    Returns None if the chapter cannot be fetched or has no parseable verses.
    `abbr` is accepted for signature compatibility but is not needed by the API.
    """
    params = {"id": version_num, "reference": f"{book}.{chapter}"}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(REQUEST_DELAY)
            resp = session.get(CHAPTER_API, params=params,
                               headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 404:
                return None          # chapter/version genuinely absent
            resp.raise_for_status()
            data = resp.json()
            content = data.get("content", "")
            if not content:
                return None
            verses = _parse_chapter_content(content, book, chapter)
            return verses if verses else None
        except Exception:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_WAIT)
            else:
                return None
    return None


# ─────────────────────────────────────────────
# ENGLISH CACHE  (chapter-level batch fetching)
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


def _batch_append_en_cache(rows: list[dict]):
    """Append multiple {verse_key, eng} rows to english_cache.csv atomically."""
    with EN_CSV_LOCK:
        os.makedirs(OUTPUT_ROOT, exist_ok=True)
        write_header = not os.path.exists(ENGLISH_CACHE_CSV)
        with open(ENGLISH_CACHE_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["verse_key", "eng"])
            if write_header:
                writer.writeheader()
            writer.writerows(rows)


def get_english_chapter(session: requests.Session, book: str, chapter: int,
                        needed_verses: set[int]) -> dict[int, str]:
    """
    Return {verse_num: cleaned_text} for the requested verse numbers.

    Checks the in-memory cache first.  If any needed verse is missing, fetches
    the full English chapter once, caches all verses found, then returns the
    subset that was requested.  This means subsequent languages reuse the cache
    and incur zero extra HTTP calls for English.
    """
    _load_en_cache_once()
    prefix = f"{book}.{chapter}."

    with _en_cache_lock:
        missing = [v for v in needed_verses if f"{prefix}{v}" not in _en_cache]

    if not missing:
        with _en_cache_lock:
            return {v: _en_cache[f"{prefix}{v}"]
                    for v in needed_verses
                    if _en_cache.get(f"{prefix}{v}")}

    # At least one verse not yet cached — fetch the whole chapter
    raw_verses = get_chapter_verses(session, ENGLISH_VERSION_NUM, book, chapter, ENGLISH_ABBR)

    new_rows: list[dict] = []
    result:   dict[int, str] = {}

    with _en_cache_lock:
        if raw_verses:
            for verse_num, raw_text in raw_verses.items():
                key = f"{prefix}{verse_num}"
                if key not in _en_cache:
                    cleaned = clean_text(raw_text) if raw_text.strip() else ""
                    _en_cache[key] = cleaned
                    new_rows.append({"verse_key": key, "eng": cleaned})

        # Mark any still-missing verses as empty so we don't retry them
        for v in missing:
            key = f"{prefix}{v}"
            if key not in _en_cache:
                _en_cache[key] = ""
                new_rows.append({"verse_key": key, "eng": ""})

        # Build result for the originally requested set
        for v in needed_verses:
            val = _en_cache.get(f"{prefix}{v}", "")
            if val:
                result[v] = val

    if new_rows:
        _batch_append_en_cache(new_rows)

    return result


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
                       local_text: str, csv_path: str):
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


# ─────────────────────────────────────────────
# CHAPTER WORKER
# ─────────────────────────────────────────────

def process_chapter(book, chapter, version_num, abbr, csv_path,
                    progress_dict, done_set, session_queue: Queue):
    stats = {"parallel": 0, "skipped": 0, "missing": 0}
    session = session_queue.get()
    try:
        local_verses = get_chapter_verses(session, version_num, book, chapter, abbr)
        if not local_verses:
            # Version has no content for this chapter
            mark_chapter_done(version_num, book, chapter, progress_dict, done_set)
            flush_progress(progress_dict)
            return stats

        # Split into already-done and still-needed verse numbers
        all_verse_nums = set(local_verses.keys())
        skipped = {v for v in all_verse_nums
                   if is_done(f"{book}.{chapter}.{v}", done_set)}
        needed  = all_verse_nums - skipped
        stats["skipped"] += len(skipped)

        if needed:
            en_verses = get_english_chapter(session, book, chapter, needed)
            for verse_num in sorted(needed):
                key        = f"{book}.{chapter}.{verse_num}"
                local_text = clean_text(local_verses[verse_num])
                if not local_text:
                    mark_verse_done(version_num, key, progress_dict, done_set)
                    continue
                en_text = en_verses.get(verse_num, "")
                if not en_text:
                    mark_verse_done(version_num, key, progress_dict, done_set)
                    stats["missing"] += 1
                    continue
                save_parallel_pair(key, version_num, en_text, local_text, csv_path)
                mark_verse_done(version_num, key, progress_dict, done_set)
                stats["parallel"] += 1
                print(f"    + {key}")

        mark_chapter_done(version_num, book, chapter, progress_dict, done_set)
    finally:
        session_queue.put(session)

    flush_progress(progress_dict)
    return stats


# ─────────────────────────────────────────────
# PROBE TESTAMENT
# ─────────────────────────────────────────────

# ── Version inventory (preferred: exact book/chapter list) ──────────────────
#
# bible.com exposes per-version metadata listing exactly which books and
# chapters the version contains.  Driving the scrape from this is precise:
# no testament probe to misjudge, no static chapter table to drift, and no
# requests wasted on books/chapters the version doesn't have.
VERSION_API = "https://nodejs.bible.com/api/bible/version/3.1"

# The 66-book Protestant canon we build datasets for (== ALL_BOOK_CODES).
_CANON_BOOKS = set(ALL_BOOK_CODES)


def get_version_chapters(session: requests.Session, version_num: int):
    """Return the ordered [(book, chapter), ...] this version actually contains
    (canonical chapters within the 66-book canon), or None if metadata is
    unavailable so the caller can fall back to probing."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(REQUEST_DELAY)
            resp = session.get(VERSION_API, params={"id": version_num},
                               headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            books = resp.json().get("books")
            if not books:
                return None
            out = []
            for b in books:
                if b.get("usfm") not in _CANON_BOOKS:
                    continue
                for c in b.get("chapters", []):
                    if not c.get("canonical"):
                        continue
                    m = re.match(r"^([A-Z0-9]+)\.(\d+)$", c.get("usfm", ""))
                    if m:
                        out.append((m.group(1), int(m.group(2))))
            return out or None
        except Exception:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_WAIT)
    return None


# ── Fallback: probe + static table (used only if metadata is unavailable) ────
#
# Representative books probed per testament. Several are tried (not just one)
# so a testament isn't skipped when only an unusual book is present — e.g. a
# "NT + Psalms" edition whose ONLY Old Testament book is Psalms would be missed
# if we probed Genesis alone.
OT_PROBE_BOOKS = ["GEN", "PSA", "ISA", "EXO", "PRO"]
NT_PROBE_BOOKS = ["MAT", "JHN", "ACT", "REV"]


def probe_testament(label: str, probe_books: list, version_num: int,
                    session: requests.Session, abbr: str | None) -> bool:
    """Return True if the version has content in chapter 1 of ANY probe book."""
    for book in probe_books:
        print(f"  [{label} probe] fetching {book}.1 ...")
        if get_chapter_verses(session, version_num, book, 1, abbr):
            print(f"  [{label} probe] content found in {book}")
            return True
    print(f"  [{label} probe] no content in any probe book — skipping testament")
    return False


def _fallback_chapter_list(version_num, abbr, session_queue, testament_status):
    """Probe-based (book, chapter) list, used only when metadata is unavailable.

    Returns None if neither testament has content.
    """
    OT_BOOKS = ALL_BOOK_CODES[:39]
    cached = testament_status.get(version_num)
    probe_session = session_queue.get()
    try:
        if cached and "ot" in cached:
            ot_ok = cached["ot"]
        else:
            ot_ok = probe_testament("OT", OT_PROBE_BOOKS, version_num, probe_session, abbr)
            testament_status.setdefault(version_num, {})["ot"] = ot_ok
            save_testament_status(testament_status)
        if cached and "nt" in cached:
            nt_ok = cached["nt"]
        else:
            nt_ok = probe_testament("NT", NT_PROBE_BOOKS, version_num, probe_session, abbr)
            testament_status.setdefault(version_num, {})["nt"] = nt_ok
            save_testament_status(testament_status)
    finally:
        session_queue.put(probe_session)

    if not ot_ok and not nt_ok:
        return None

    chapters = []
    for book in ALL_BOOK_CODES:
        in_ot = book in OT_BOOKS
        if (in_ot and not ot_ok) or (not in_ot and not nt_ok):
            continue
        for chapter in range(1, BOOK_CHAPTERS.get(book, 0) + 1):
            chapters.append((book, chapter))
    return chapters


# ─────────────────────────────────────────────
# SESSION POOL
# ─────────────────────────────────────────────

def build_session_pool(n: int) -> Queue:
    q = Queue()
    for _ in range(n):
        s = requests.Session()
        s.headers.update(REQUEST_HEADERS)
        q.put(s)
    print(f"  {n} HTTP sessions ready")
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

    # ── Determine exactly which chapters this version contains ────────────────
    # Ask the version metadata endpoint for the real book/chapter inventory and
    # scrape precisely those. This avoids guessing (no testament probe) and never
    # fires requests at books/chapters the version doesn't have. If the metadata
    # is unavailable we fall back to the older probe + static-table approach.
    meta_session = session_queue.get()
    try:
        inventory = get_version_chapters(meta_session, version_num)
    finally:
        session_queue.put(meta_session)

    if inventory is not None:
        print(f"\n  Metadata: version contains {len(inventory)} canonical chapter(s)")
        candidate_chapters = inventory
    else:
        print("\n  Metadata unavailable — falling back to probe + static table")
        candidate_chapters = _fallback_chapter_list(
            version_num, abbr, session_queue, testament_status)
        if candidate_chapters is None:
            print(f"  No content found — skipping {lang_name} ({lang_code}).")
            return stats

    flush_progress(progress_dict)

    # ── Chapter task list (skip chapters already completed) ───────────────────
    tasks            = []
    skipped_chapters = 0
    for book, chapter in candidate_chapters:
        if is_chapter_done(book, chapter, done_set):
            skipped_chapters += 1
        else:
            tasks.append((book, chapter))

    if skipped_chapters:
        print(f"  Skipped {skipped_chapters} already-completed chapters")

    workers = min(NUM_WORKERS, session_queue.qsize())
    print(f"  Processing {len(tasks)} chapters across {workers} workers ...")
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
        raw = input("\n  Enter version ID (or 'q' to quit): ").strip()
        if raw.lower() in ("q", "quit", "exit"):
            print("\n  Bye!\n")
            sys.exit(0)
        if not raw.isdigit():
            print("  Please enter a numeric version ID.\n")
            continue
        vid = int(raw)
        if vid not in available_by_id:
            print(f"  Version {vid} not found in CSV.\n")
            continue
        entry = available_by_id[vid]
        _, lang_code, lang_name, abbr = entry
        abbr_str = f" ({abbr})" if abbr else ""
        print(f"\n  Starting scrape for {lang_name}{abbr_str} [{lang_code}] ...\n")
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
    selected = prompt_language_selection(all_entries)
    if not selected:
        print("No languages selected. Exiting.")
        return

    print(f"\nSpinning up {NUM_WORKERS} HTTP sessions ...")
    session_queue = build_session_pool(NUM_WORKERS)

    progress         = load_global_progress()
    testament_status = load_testament_status()
    grand_total      = 0

    for version_num, lang_code, lang_name, abbr in selected:
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
