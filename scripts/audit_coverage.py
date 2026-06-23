"""
audit_coverage.py  —  maintainer tool
=====================================
Checks every Ghanaian language CSV for missing chapters WITHOUT scraping any
verses. For each file it asks YouVersion's per-version metadata endpoint which
books/chapters that version actually contains, and compares that to what the
CSV captured. A whole chapter present in the source but absent from our file is
the tell-tale sign of a scrape gap (e.g. a flaky chapter fetch, or a testament
skipped by the viability probe).

It only counts the 66-book Protestant canon, so deuterocanonical books in a
source version are not reported as false gaps.

Note on versification: some versions number Joel as 4 chapters (Hebrew) while
the English reference (CEB) uses 3. Such a "missing" chapter has no English
counterpart to pair with, so it is reported but is not a fixable gap.

Usage
-----
    python scripts/audit_coverage.py            # audit local data dir
    python scripts/audit_coverage.py --hf       # audit files listed on HuggingFace

Requires: requests, beautifulsoup4 (lxml optional), huggingface_hub (for --hf)
"""

import csv
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.path.join(REPO_ROOT, "bible_parallel_text_datasets")
HF_REPO_ID = os.environ.get("GHANA_CORPUS_REPO", "ghananlpcommunity/ghana-corpus")
VERSION_API = "https://nodejs.bible.com/api/bible/version/3.1"

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
           "Accept-Language": "en-US,en;q=0.9"}

CANON = set((
    "GEN EXO LEV NUM DEU JOS JDG RUT 1SA 2SA 1KI 2KI 1CH 2CH EZR NEH EST JOB "
    "PSA PRO ECC SNG ISA JER LAM EZK DAN HOS JOL AMO OBA JON MIC NAM HAB ZEP "
    "HAG ZEC MAL MAT MRK LUK JHN ACT ROM 1CO 2CO GAL EPH PHP COL 1TH 2TH 1TI "
    "2TI TIT PHM HEB JAS 1PE 2PE 1JN 2JN 3JN JUD REV"
).split())

LANG_RE = re.compile(r"^(.+)_([a-z]{2,4})_v(\d+)\.csv$")

csv.field_size_limit(10_000_000)


def source_chapters(version_id: int) -> set | None:
    """Canonical (book, chapter) pairs the source version contains, 66-book canon."""
    try:
        d = requests.get(VERSION_API, params={"id": version_id},
                         headers=HEADERS, timeout=25).json()
    except Exception:
        return None
    chaps = set()
    for b in d.get("books", []):
        if b.get("usfm") not in CANON:
            continue
        for c in b.get("chapters", []):
            if c.get("canonical"):
                m = re.match(r"^([A-Z0-9]+)\.(\d+)$", c.get("usfm", ""))
                if m:
                    chaps.add((m.group(1), int(m.group(2))))
    return chaps


def captured_chapters(read_lines) -> set:
    chaps = set()
    for row in csv.DictReader(read_lines):
        try:
            b, c, _ = row["verse_key"].split(".")
            chaps.add((b, int(c)))
        except (ValueError, KeyError):
            pass
    return chaps


def main():
    use_hf = "--hf" in sys.argv[1:]

    if use_hf:
        from huggingface_hub import HfApi, hf_hub_download
        names = [f for f in HfApi().list_repo_files(HF_REPO_ID, repo_type="dataset")
                 if "/" not in f and LANG_RE.match(f)]
        def reader(name):
            return open(hf_hub_download(HF_REPO_ID, name, repo_type="dataset"),
                        encoding="utf-8")
    else:
        names = [f for f in sorted(os.listdir(DATA_ROOT))
                 if LANG_RE.match(f) and os.path.getsize(os.path.join(DATA_ROOT, f)) >= 64]
        def reader(name):
            return open(os.path.join(DATA_ROOT, name), encoding="utf-8")

    print(f"Auditing {len(names)} Ghanaian language file(s) "
          f"({'HuggingFace' if use_hf else 'local'})...\n")

    def check(name):
        vid = int(LANG_RE.match(name).group(3))
        src = source_chapters(vid)
        if src is None:
            return (name, vid, None)
        with reader(name) as f:
            ours = captured_chapters(f)
        return (name, vid, sorted(src - ours))

    gaps, errors = [], []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for name, vid, missing in sorted(
                (fut.result() for fut in as_completed(
                    [pool.submit(check, n) for n in names])),
                key=lambda r: r[0]):
            if missing is None:
                errors.append(name)
            elif missing:
                gaps.append((name, vid, missing))

    if gaps:
        print("CHAPTERS IN SOURCE BUT MISSING FROM OUR DATA:")
        for name, vid, missing in gaps:
            head = ", ".join(f"{b} {c}" for b, c in missing[:12])
            more = f"  (+{len(missing) - 12} more)" if len(missing) > 12 else ""
            print(f"  {name} (v{vid}): {len(missing)} missing — {head}{more}")
    else:
        print("No missing chapters — every file is complete vs its source. ✅")

    if errors:
        print(f"\nMetadata fetch failed for: {', '.join(errors)} (retry)")

    print(f"\nTotal {len(names)} | clean {len(names) - len(gaps) - len(errors)} "
          f"| gaps {len(gaps)} | errors {len(errors)}")


if __name__ == "__main__":
    main()
