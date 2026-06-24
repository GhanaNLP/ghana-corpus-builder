"""
ghana_corpus.py  —  Ghanaian parallel & monolingual corpus retrieval
====================================================================
A small library (and CLI) for pulling ready-made corpora out of the verse
collections in `bible_parallel_text_datasets/`.

Everything in that directory is aligned on a shared `verse_key`
(BOOK.chapter.verse), so any two languages can be turned into a parallel
corpus with a single join — nothing is scraped at retrieval time.

What you can retrieve
---------------------
  • Parallel  Ghanaian ↔ English        (English ships cached, the default pair)
  • Parallel  Ghanaian ↔ Ghanaian       (e.g. Twi ↔ Ewe, Ga ↔ Dagbani)
  • Parallel  Ghanaian ↔ other language (French, Arabic, Chinese, … — cached)
  • Monolingual corpus for any single language

Library usage
-------------
    import ghana_corpus as gc

    gc.list_languages()                       # what's available
    rows = gc.parallel("twi", "ewe")          # [(verse_key, twi, ewe), ...]
    rows = gc.parallel("twi")                 # twi ↔ English (English default)
    sents = gc.monolingual("twi")             # ["...", "...", ...]
    gc.write_parallel_csv("twi", "ewe", "twi_ewe.csv")
    gc.write_monolingual_csv("twi", "twi.csv")

CLI usage
---------
    python ghana_corpus.py --list
    python ghana_corpus.py --source twi --target ewe --out twi_ewe.csv
    python ghana_corpus.py --source twi                      # twi ↔ English
    python ghana_corpus.py --monolingual twi --out twi.csv
    python ghana_corpus.py                                   # interactive

Source: verse text comes from public Bible translations (see README).
"""

import argparse
import csv
import os
import random
import re
import sys

# Allow very long Bible verses through the csv reader.
csv.field_size_limit(10_000_000)

# ─────────────────────────────────────────────
# PATHS & CONSTANTS
# ─────────────────────────────────────────────

REPO_ROOT      = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT      = os.path.join(REPO_ROOT, "bible_parallel_text_datasets")

# The data lives in a HuggingFace dataset; files are downloaded and cached on
# demand. If a copy is already present under DATA_ROOT (e.g. on a maintainer's
# machine) it is used directly and nothing is downloaded.
HF_REPO_ID   = os.environ.get("GHANA_CORPUS_REPO", "ghananlpcommunity/ghana-corpus")
HF_REPO_TYPE = "dataset"

# Files in DATA_ROOT that are not Ghanaian language datasets.
_NON_LANG_FILES = {"english_cache.csv", "progress.json",
                   "progress.json.tmp", "testament_status.json"}

# Canonical book order, for sorting output in scripture order.
_BOOK_ORDER = [
    "GEN","EXO","LEV","NUM","DEU","JOS","JDG","RUT","1SA","2SA",
    "1KI","2KI","1CH","2CH","EZR","NEH","EST","JOB","PSA","PRO",
    "ECC","SNG","ISA","JER","LAM","EZK","DAN","HOS","JOL","AMO",
    "OBA","JON","MIC","NAM","HAB","ZEP","HAG","ZEC","MAL",
    "MAT","MRK","LUK","JHN","ACT","ROM","1CO","2CO","GAL","EPH",
    "PHP","COL","1TH","2TH","1TI","2TI","TIT","PHM","HEB","JAS",
    "1PE","2PE","1JN","2JN","3JN","JUD","REV",
]
_BOOK_INDEX = {b: i for i, b in enumerate(_BOOK_ORDER)}

_LANG_FILE_RE = re.compile(r"^(?P<name>.+)_(?P<code>[a-z]{2,4})_v(?P<vid>\d+)\.csv$")


def _verse_sort_key(verse_key: str):
    """Sort verse_keys (BOOK.chapter.verse) in canonical scripture order."""
    try:
        book, ch, vs = verse_key.split(".")
        return (_BOOK_INDEX.get(book, 999), int(ch), int(vs))
    except (ValueError, KeyError):
        return (999, 0, 0)


# ─────────────────────────────────────────────
# DATA ACCESS  (local cache + HuggingFace download)
# ─────────────────────────────────────────────

_FILE_LIST: list[str] | None = None


def _local_csvs() -> list[str]:
    if not os.path.isdir(DATA_ROOT):
        return []
    out = []
    for root, _dirs, files in os.walk(DATA_ROOT):
        for name in files:
            full = os.path.join(root, name)
            # Skip empty / header-only files so local discovery matches what is
            # published to HuggingFace (the push tool excludes them too).
            if name.endswith(".csv") and os.path.getsize(full) >= 64:
                rel = os.path.relpath(full, DATA_ROOT)
                out.append(rel.replace(os.sep, "/"))
    return out


def dataset_files() -> list[str]:
    """Repo-relative paths of every data CSV (local copy if present, else HF)."""
    global _FILE_LIST
    if _FILE_LIST is None:
        local = _local_csvs()
        if local:
            _FILE_LIST = local
        else:
            try:
                from huggingface_hub import HfApi
            except ImportError:
                raise RuntimeError(
                    "No local data found and huggingface_hub is not installed.\n"
                    "Install it with:  pip install huggingface_hub")
            files = HfApi().list_repo_files(HF_REPO_ID, repo_type=HF_REPO_TYPE)
            _FILE_LIST = [f for f in files if f.endswith(".csv")]
    return _FILE_LIST


def data_path(rel: str) -> str:
    """Resolve a repo-relative data file to a readable local path.

    Uses DATA_ROOT if the file is already there; otherwise downloads it from
    the HuggingFace dataset (cached by huggingface_hub for next time).
    """
    local = os.path.join(DATA_ROOT, rel)
    if os.path.exists(local):
        return local
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise RuntimeError(
            f"'{rel}' is not present locally and huggingface_hub is not "
            f"installed.\nInstall it with:  pip install huggingface_hub")
    return hf_hub_download(HF_REPO_ID, rel, repo_type=HF_REPO_TYPE)


# ─────────────────────────────────────────────
# LANGUAGE REGISTRY
# ─────────────────────────────────────────────

class Language:
    """A retrievable language: a code, a display name, and where its text lives."""

    def __init__(self, code, name, kind, files=None, text_column="text"):
        self.code = code
        self.name = name
        self.kind = kind                  # "ghanaian" | "reference"
        self.files = files or []          # repo-relative dataset CSV(s)
        self.text_column = text_column    # which column holds the text

    def __repr__(self):
        return f"<Language {self.code} '{self.name}' ({self.kind})>"


def _group_by_filename(rels, kind, text_column) -> dict[str, Language]:
    """Build {code: Language} from `{Name}_{code}_v{id}.csv` filenames.

    Files sharing a code are merged (e.g. multiple Bible versions of one
    language). The language name and code come straight from the filename, so
    nothing else needs to know the file exists — discovery is self-describing.
    """
    langs: dict[str, Language] = {}
    for rel in sorted(rels):
        fname = rel.split("/")[-1]
        m = _LANG_FILE_RE.match(fname)
        if not m:
            continue
        code = m.group("code")
        name = m.group("name").replace("_", " ")
        if code not in langs:
            langs[code] = Language(code, name, kind, files=[],
                                   text_column=text_column)
        if name not in langs[code].name:
            langs[code].name += f" / {name}"
        langs[code].files.append(rel)
    return langs


def _discover_ghanaian() -> dict[str, Language]:
    """Ghanaian datasets: top-level `{Name}_{code}_v{id}.csv` files."""
    rels = [r for r in dataset_files()
            if "/" not in r and r.split("/")[-1] not in _NON_LANG_FILES]
    return _group_by_filename(rels, "ghanaian", "local")


def _discover_reference() -> dict[str, Language]:
    """Reference languages: self-describing from filenames, no index needed.

    `reference_caches/{Name}_{code}_v{id}.csv` files are discovered exactly like
    Ghanaian ones. English ships as the fixed `english_cache.csv` (built
    alongside the Ghanaian datasets) and is registered as a special case.
    """
    files = dataset_files()
    rels = [r for r in files if r.startswith("reference_caches/")]
    langs = _group_by_filename(rels, "reference", "text")
    if "english_cache.csv" in files:
        # english_cache.csv is the default English (CEB). Merge it with any
        # versioned reference_caches/English_en_v*.csv files rather than
        # replacing them, so all English versions are available under "en".
        # text_column "eng" reads english_cache; the per-file fallback in
        # _load_verses reads "text" for the versioned files.
        en = langs.get("en")
        if en is None:
            langs["en"] = Language("en", "English", "reference",
                                   files=["english_cache.csv"], text_column="eng")
        else:
            en.files.insert(0, "english_cache.csv")
            en.text_column = "eng"
    return langs


_REGISTRY: dict[str, Language] | None = None


def registry() -> dict[str, Language]:
    """Return {code: Language} for every available language (cached)."""
    global _REGISTRY
    if _REGISTRY is None:
        reg = _discover_ghanaian()
        reg.update(_discover_reference())   # reference codes won't clash
        _REGISTRY = reg
    return _REGISTRY


def refresh():
    """Forget the cached file list and registry.

    A new CLI run always sees the latest HuggingFace data, so you only need
    this inside a long-running process to pick up languages pushed to HF after
    the process started.
    """
    global _FILE_LIST, _REGISTRY
    _FILE_LIST = None
    _REGISTRY = None


def resolve(token: str) -> Language:
    """Look a language up by exact code or exact (case-insensitive) name.

    Matching is intentionally strict — a code or a full display name (or one of
    the names in a merged "A / B" entry).  Loose substring matching is avoided
    so that, e.g., 'ga' never silently resolves to 'Dagaare'.
    """
    reg = registry()
    token = token.strip()

    # "code@version" selects a single Bible version (e.g. "en@406", "fr@21").
    # Without @, all versions of a language are merged (more paraphrases).
    if "@" in token:
        base_tok, ver = token.rsplit("@", 1)
        base = resolve(base_tok)
        ver = ver.strip()
        sel = [f for f in base.files if f"_v{ver}." in f.split("/")[-1]]
        if not sel:
            avail = [f.split("/")[-1] for f in base.files]
            raise KeyError(f"No version '{ver}' for '{base.code}'. "
                           f"Available files: {avail}")
        return Language(base.code, f"{base.name} (v{ver})", base.kind,
                        files=sel, text_column=base.text_column)

    if token in reg:
        return reg[token]
    low = token.lower()
    for lang in reg.values():
        if lang.code.lower() == low:
            return lang
        name_parts = [p.strip().lower() for p in lang.name.split("/")]
        if low in name_parts:
            return lang
    raise KeyError(f"Unknown language '{token}'. "
                   f"Run with --list to see available codes.")


# ─────────────────────────────────────────────
# VERSE LOADING
# ─────────────────────────────────────────────

def _load_verses(lang: Language) -> dict[str, set[str]]:
    """Return {verse_key: {distinct cleaned texts}} for a language.

    Ghanaian languages may have several version files; their texts are merged
    per verse so that the union is available for alignment.
    """
    verses: dict[str, set[str]] = {}
    for rel in lang.files:
        path = data_path(rel)
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            col = lang.text_column if lang.text_column in (reader.fieldnames or []) else None
            if col is None:
                # Fall back to a sensible default per kind.
                col = "local" if lang.kind == "ghanaian" else "text"
            for row in reader:
                key = row.get("verse_key")
                text = (row.get(col) or "").strip()
                if key and text:
                    verses.setdefault(key, set()).add(text)
    return verses


# ─────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────

def list_languages():
    """Return (ghanaian, reference) lists of Language objects."""
    reg = registry()
    ghanaian  = sorted((l for l in reg.values() if l.kind == "ghanaian"),
                       key=lambda l: l.name)
    reference = sorted((l for l in reg.values() if l.kind == "reference"),
                       key=lambda l: l.name)
    return ghanaian, reference


def _apply_limit(rows: list, limit: int | None, sample: bool, seed: int) -> list:
    """Cap `rows` to `limit` items.

    sample=False keeps the first `limit` rows (scripture order, deterministic).
    sample=True draws a random `limit`-sized sample (reproducible via `seed`),
    returned in the original order.
    """
    if limit is None or limit >= len(rows):
        return rows
    if not sample:
        return rows[:limit]
    idx = sorted(random.Random(seed).sample(range(len(rows)), limit))
    return [rows[i] for i in idx]


def parallel(source: str, target: str = "en", limit: int | None = None,
             sample: bool = False, seed: int = 0) -> list[tuple[str, str, str]]:
    """Aligned (verse_key, source_text, target_text) rows for two languages.

    `target` defaults to English. Both arguments accept a code or a name.
    Where a verse has multiple translations on either side, every distinct
    combination is emitted (deduplicated).  `limit`/`sample`/`seed` control
    how many pairs are returned (see `_apply_limit`).
    """
    a = resolve(source)
    b = resolve(target)
    if a.code == b.code:
        raise ValueError("Source and target languages must differ.")

    va = _load_verses(a)
    vb = _load_verses(b)
    shared = set(va) & set(vb)

    rows: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for key in sorted(shared, key=_verse_sort_key):
        for ta in va[key]:
            for tb in vb[key]:
                pair = (ta, tb)
                if pair in seen:
                    continue
                seen.add(pair)
                rows.append((key, ta, tb))
    return _apply_limit(rows, limit, sample, seed)


def monolingual(language: str, limit: int | None = None,
                sample: bool = False, seed: int = 0) -> list[str]:
    """Return the deduplicated list of sentences for one language."""
    lang = resolve(language)
    verses = _load_verses(lang)
    seen: set[str] = set()
    out: list[str] = []
    for key in sorted(verses, key=_verse_sort_key):
        for text in sorted(verses[key]):
            if text not in seen:
                seen.add(text)
                out.append(text)
    return _apply_limit(out, limit, sample, seed)


def write_parallel_csv(source: str, target: str, out_path: str,
                       limit: int | None = None, sample: bool = False,
                       seed: int = 0) -> int:
    a = resolve(source)
    b = resolve(target)
    rows = parallel(source, target, limit=limit, sample=sample, seed=seed)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["verse_key", a.code, b.code])
        w.writerows(rows)
    return len(rows)


def write_monolingual_csv(language: str, out_path: str, limit: int | None = None,
                          sample: bool = False, seed: int = 0) -> int:
    lang = resolve(language)
    sents = monolingual(language, limit=limit, sample=sample, seed=seed)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([lang.code])
        for s in sents:
            w.writerow([s])
    return len(sents)


def all_ghanaian_codes() -> list[str]:
    """Codes of every available Ghanaian language, in display-name order."""
    ghanaian, _ = list_languages()
    return [l.code for l in ghanaian]


def build_batch(sources: list[str], target: str | None = "en",
                monolingual_mode: bool = False, limit: int | None = None,
                sample: bool = False, seed: int = 0,
                out_dir: str = ".") -> list[tuple[str, str, int]]:
    """Write one corpus file per source language.

    Returns a list of (code, out_path, row_count) tuples.  Languages that
    cannot be produced (e.g. source == target) are skipped with a note.
    """
    os.makedirs(out_dir, exist_ok=True)
    results: list[tuple[str, str, int]] = []
    for src in sources:
        code = resolve(src).code
        try:
            if monolingual_mode:
                out_path = os.path.join(out_dir, f"{code}_monolingual.csv")
                n = write_monolingual_csv(src, out_path, limit, sample, seed)
            else:
                tcode = resolve(target).code
                if tcode == code:
                    print(f"  skip {code}: same as target")
                    continue
                out_path = os.path.join(out_dir, f"{code}_{tcode}_parallel.csv")
                n = write_parallel_csv(src, target, out_path, limit, sample, seed)
            results.append((code, out_path, n))
            print(f"  {code}: {n:,} rows -> {out_path}")
        except (KeyError, ValueError) as e:
            print(f"  skip {src}: {e}")
    return results


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def _print_languages():
    ghanaian, reference = list_languages()
    print("\nGhanaian languages:")
    for l in ghanaian:
        print(f"  {l.code:6s}  {l.name}")
    print("\nOther (reference) languages — usable as parallel candidates:")
    for l in reference:
        print(f"  {l.code:6s}  {l.name}")
    print()


def _default_out_name(source: str, target: str | None) -> str:
    a = resolve(source).code
    if target is None:
        return f"{a}_monolingual.csv"
    b = resolve(target).code
    return f"{a}_{b}_parallel.csv"


def _parse_sources(spec: str) -> list[str]:
    """'all' -> every Ghanaian language; otherwise a comma-separated list."""
    if spec.strip().lower() == "all":
        return all_ghanaian_codes()
    return [s.strip() for s in spec.split(",") if s.strip()]


def _interactive():
    _print_languages()
    mode = input("Build [p]arallel or [m]onolingual corpus? [p]: ").strip().lower()
    mono = mode.startswith("m")

    prompt = ("Language(s) — code, comma-separated list, or 'all' "
              if mono else
              "Source language(s) — code, comma-separated list, or 'all' ")
    sources = _parse_sources(input(prompt + ": ").strip() or "all")

    target = None
    if not mono:
        target = input("Target language code [en]: ").strip() or "en"

    lim = input("Number of samples per language [all]: ").strip()
    limit = int(lim) if lim.isdigit() else None
    sample = False
    if limit:
        sample = input("Random sample? [y/N]: ").strip().lower().startswith("y")

    if len(sources) == 1:
        out = _default_out_name(sources[0], target)
        if mono:
            n = write_monolingual_csv(sources[0], out, limit, sample)
        else:
            n = write_parallel_csv(sources[0], target, out, limit, sample)
        print(f"\nWrote {n:,} rows to {out}")
    else:
        out_dir = input("Output directory [corpora]: ").strip() or "corpora"
        build_batch(sources, target, mono, limit, sample, out_dir=out_dir)
        print(f"\nDone — files written to {out_dir}/")


def main():
    ap = argparse.ArgumentParser(
        description="Retrieve parallel or monolingual corpora for Ghanaian languages.")
    ap.add_argument("--list", action="store_true", help="list available languages")
    ap.add_argument("-s", "--source",
                    help="source language(s): a code, a comma-separated list, or 'all'")
    ap.add_argument("-t", "--target", default="en",
                    help="target language code/name for parallel corpora (default: en)")
    ap.add_argument("-m", "--monolingual", action="store_true",
                    help="build monolingual corpora instead of parallel")
    ap.add_argument("-n", "--limit", type=int,
                    help="max samples per language (default: all)")
    ap.add_argument("--sample", action="store_true",
                    help="randomly sample --limit rows instead of taking the first N")
    ap.add_argument("--seed", type=int, default=0,
                    help="random seed for --sample (default: 0, reproducible)")
    ap.add_argument("--out", help="output CSV path (single language)")
    ap.add_argument("--out-dir", default="corpora",
                    help="output directory when building for multiple languages")
    args = ap.parse_args()

    if args.list:
        _print_languages()
        return

    if not args.source:
        try:
            _interactive()
        except (KeyError, ValueError) as e:
            sys.exit(f"Error: {e}")
        return

    sources = _parse_sources(args.source)
    target = None if args.monolingual else args.target

    try:
        if len(sources) == 1:
            out = args.out or _default_out_name(sources[0], target)
            if args.monolingual:
                n = write_monolingual_csv(sources[0], out, args.limit,
                                          args.sample, args.seed)
            else:
                n = write_parallel_csv(sources[0], target, out, args.limit,
                                       args.sample, args.seed)
            print(f"Wrote {n:,} rows to {out}")
        else:
            build_batch(sources, target, args.monolingual, args.limit,
                        args.sample, args.seed, out_dir=args.out_dir)
            print(f"Done — files written to {args.out_dir}/")
    except (KeyError, ValueError) as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
