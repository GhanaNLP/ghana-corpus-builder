# Ghana Corpus Builder

A toolkit and small Python library for **retrieving monolingual and parallel
text corpora for Ghanaian languages**. Pull a monolingual corpus for any single
Ghanaian language, or pair one with English, with another Ghanaian language, or
with one of several other world languages. Output is clean, sentence-aligned
CSV, ready for machine-translation training and NLP research.

The corpora are hosted on HuggingFace at
[`ghananlpcommunity/ghana-corpus`](https://huggingface.co/datasets/ghananlpcommunity/ghana-corpus).
The library downloads only the files you actually use and caches them locally,
so the repository itself stays lightweight. New languages pushed to the dataset
are picked up automatically — no code change or update needed.

---

## What you can build

| Corpus type | Example | Notes |
|---|---|---|
| Ghanaian ↔ English | Twi ↔ English | English ships cached; the default target |
| Ghanaian ↔ Ghanaian | Twi ↔ Ewe, Ga ↔ Dagbani | align two local languages directly |
| Ghanaian ↔ other language | Twi ↔ French, Ewe ↔ Arabic | French, Spanish, Portuguese, German, Italian, Arabic, Chinese, Swahili are cached |
| Monolingual | all Twi sentences | any single language |

Every language's text is aligned on a shared verse key, so **any** two
languages can be turned into a parallel corpus by a simple join. That is what
makes Ghanaian ↔ Ghanaian and Ghanaian ↔ other-language pairs possible.

## Dataset statistics

**47 Ghanaian languages** with data, **1,289,419 parallel sentence pairs** in total (English-aligned). Sentence pairs = aligned verses available before de-duplication.

| Language | Code | Sentence pairs |
|---|---|--:|
| Akuapem Twi / Asante Twi | twi | 185,554 |
| Ewe | ewe | 92,544 |
| Ga | gaa | 62,004 |
| Fante | fat | 61,606 |
| Dagbani | dag | 61,558 |
| Hausa | hau | 61,548 |
| Sehwi | sfw | 39,005 |
| Dagaare | dga | 38,948 |
| Kasem | xsm | 38,631 |
| Bimoba | bim | 38,180 |
| Dangme | ada | 38,142 |
| Konkomba | xon | 38,062 |
| Nzema | nzi | 36,195 |
| Fulfulde; Maasina | ffm | 36,012 |
| Vagla | vag | 31,086 |
| Buli | bwu | 31,084 |
| Deg | mzw | 31,082 |
| Sisaala; Tumulung | sil | 31,032 |
| Kusaal | kus | 30,979 |
| Bassar Ntcham | bud | 30,874 |
| Lelemi | lef | 30,715 |
| Gonja | gjn | 30,401 |
| Selee | snw | 25,583 |
| Ninkare | gur | 15,862 |
| Nkonya | nko | 10,321 |
| Tem | kdh | 9,437 |
| Anyin | any | 7,940 |
| Avatime | avn | 7,940 |
| Birifor; Southern | biv | 7,940 |
| Nawuri | naw | 7,939 |
| Bissa | bib | 7,934 |
| Abron | abr | 7,928 |
| Konni | kma | 7,928 |
| Tafi | tcd | 7,924 |
| Siwu | akp | 7,922 |
| Ntrubo | ntr | 7,915 |
| Kabiye | kbp | 7,904 |
| Tampulma | tpm | 7,901 |
| Anufo | cko | 7,900 |
| Tuwuli | bov | 7,898 |
| Mampruli | maw | 7,889 |
| Sekpele | lip | 7,887 |
| Gikyode | acd | 7,886 |
| Paasaal | sig | 7,878 |
| Chumburung | ncu | 7,670 |
| Nyangbo | nyb | 1,531 |
| Hanga | hag | 1,320 |

---

## Quick start

```bash
git clone https://github.com/GhanaNLP/ghana-corpus-builder.git
cd ghana-corpus-builder
```

Requires Python 3.10+ and `huggingface_hub` (used to download the data the
first time you reference a language):

```bash
pip install huggingface_hub
```

Downloaded files are cached, so each language is only fetched once. The dataset
is public — no HuggingFace login is needed to read it.

### List what's available

```bash
python ghana_corpus.py --list
```

### Build a corpus for one language (the common case)

```bash
# Twi ↔ English (English is the default target)
python ghana_corpus.py --source twi

# Twi ↔ Ewe (two Ghanaian languages)
python ghana_corpus.py --source twi --target ewe

# Twi ↔ French
python ghana_corpus.py --source twi --target fr

# Monolingual Twi
python ghana_corpus.py --source twi --monolingual
```

Each writes a CSV named after the languages (e.g. `twi_en_parallel.csv`,
`twi_monolingual.csv`). Use `--out PATH` to choose the filename.

### Limit the number of samples

```bash
# first 5,000 Twi–English pairs (in scripture order, deterministic)
python ghana_corpus.py --source twi --limit 5000

# a random 5,000-pair sample (reproducible via --seed)
python ghana_corpus.py --source twi --limit 5000 --sample --seed 42
```

### Build for many languages at once

`--source` accepts a comma-separated list or the keyword `all`. With more than
one source, one file per language is written into `--out-dir` (default
`corpora/`).

```bash
# every Ghanaian language paired with English, 10k samples each
python ghana_corpus.py --source all --limit 10000 --out-dir corpora/

# a selected set, paired with French
python ghana_corpus.py --source twi,ewe,gaa,dag --target fr --out-dir corpora/

# monolingual corpora for every Ghanaian language
python ghana_corpus.py --source all --monolingual --out-dir corpora/
```

Run `python ghana_corpus.py` with no arguments for an interactive prompt.

### Use it as a library

```python
import ghana_corpus as gc

gc.list_languages()                              # (ghanaian, reference) language lists
rows  = gc.parallel("twi", "ewe", limit=1000)    # [(verse_key, twi, ewe), ...]
rows  = gc.parallel("twi")                        # twi ↔ English
sents = gc.monolingual("twi", limit=500, sample=True)

gc.write_parallel_csv("twi", "fr", "twi_fr.csv", limit=2000)
gc.write_monolingual_csv("twi", "twi.csv")

# one file per language
gc.build_batch(gc.all_ghanaian_codes(), target="en",
               limit=10000, out_dir="corpora/")
```

Languages are referenced by code (`twi`, `ewe`, `fr`) or by name
(`"Asante Twi"`, `"French"`).

---

## Available languages

**Ghanaian languages** are listed in the coverage table below. **Other
("reference") languages** that can be used as the non-Ghanaian side of a
parallel corpus:

| Code | Language |
|---|---|
| `en` | English |
| `fr` | French |
| `es` | Spanish |
| `pt` | Portuguese |
| `de` | German |
| `it` | Italian |
| `ar` | Arabic |
| `zh` | Chinese |
| `sw` | Swahili |

Each reference language has **several Bible versions**, including contemporary
modern-language translations (e.g. English: CEB, ERV, CEV, GNT). By default all
versions of a language are merged, so a Ghanaian verse is paired with **every**
available rendering — many more paraphrases for training. To pin a single
version, append `@<version_id>`:

```bash
python ghana_corpus.py --source twi --target en          # all English versions (most paraphrases)
python ghana_corpus.py --source twi --target en@406      # only ERV (Easy-to-Read)
python ghana_corpus.py --source twi --target fr@21       # only Bible du Semeur
```

Run `python ghana_corpus.py --list` to see every code; version ids are the
`v{id}` in each `reference_caches/` filename.

### Adding more reference languages

The reference set is fully self-describing — no index and no code changes. Each
cache is stored as `reference_caches/{Name}_{code}_v{id}.csv`, and the library
learns the language straight from that filename on HuggingFace.

To add one, find its YouVersion numeric version id (a full-Bible version works
best), then:

```bash
# 1. cache it locally
python scripts/fetch_reference_language.py --code ha --name Hausa --version 380

# 2. push it to HuggingFace
python scripts/push_dataset_to_hf.py
```

That's it — it's immediately selectable in `ghana_corpus.py`, with nothing to
commit. (`reference_languages.csv` is just an optional catalog of common
languages so they can be re-fetched by code; the library never reads it.)

---

## Ghanaian language coverage & contributing

The table lists Ghanaian languages tracked by this project, the YouVersion
versions they were built from, and the volunteers who curated them.

# Language Assignments

| Language | Code | Version IDs | Coverage | Status |
|---|---|---|---|---|
| Akuapem Twi | twi | 1631, 3439, 3440 | OT + NT | ✅ Done |
| Asante Twi | twi | 1461, 1861, 2094 | OT + NT | ✅ Done |
| Bassar Ntcham | bud | 2235 | OT + NT | ✅ Done |
| Bimoba | bim | 1748 | OT + NT | ✅ Done |
| Buli | bwu | 2176 | OT + NT | ✅ Done |
| Dagaare | dga | 4573 | OT + NT | ✅ Done |
| Dagbani | dag | 2263, 2264 | OT + NT | ✅ Done |
| Dangme | ada | 2265 | OT + NT | ✅ Done |
| Deg | mzw | 2012 | OT + NT | ✅ Done |
| Ewe | ewe | 1613, 2259, 3306 | OT + NT | ✅ Done |
| Fante | fat | 2913, 2914 | OT + NT | ✅ Done |
| Fulfulde; Maasina | ffm | 3093 | OT + NT | ✅ Done |
| Ga | gaa | 2708, 2712 | OT + NT | ✅ Done |
| Gonja | gjn | 1729 | OT + NT | ✅ Done |
| Hausa | hau | 71, 1614 | OT + NT | ✅ Done |
| Kasem | xsm | 3661 | OT + NT | ✅ Done |
| Konkomba | xon | 1150 | OT + NT | ✅ Done |
| Kusaal | kus | 3752 | OT + NT | ✅ Done |
| Lelemi | lef | 2442 | OT + NT | ✅ Done |
| Nzema | nzi | 2717 | OT + NT | ✅ Done |
| Sehwi | sfw | 2710 | OT + NT | ✅ Done |
| Sisaala; Tumulung | sil | 2553 | OT + NT | ✅ Done |
| Tem | kdh | 1384 | OT + NT | ✅ Done |
| Vagla | vag | 1938 | OT + NT | ✅ Done |
| Abron | abr | 3971 | NT only | ✅ Done |
| Anufo | cko | 2168 | NT only | ✅ Done |
| Anyin | any | 1731 | NT only | ✅ Done |
| Avatime | avn | 1982 | NT only | ✅ Done |
| Bimoba | bim | 1838 | NT only | ✅ Done |
| Birifor; Southern | biv | 2148 | NT only | ✅ Done |
| Bissa | bib | 1751 | NT only | ✅ Done |
| Chumburung | ncu | 437 | NT only | ✅ Done |
| Dagaare | dga | 2268 | NT only | ✅ Done |
| Dangme | ada | 2322 | NT only | ✅ Done |
| Fulfulde; Maasina | ffm | 1175 | NT only | ✅ Done |
| Gikyode | acd | 1741 | NT only | ✅ Done |
| Hanga | hag | 1499 | OT only | ✅ Done |
| Kabiye | kbp | 555 | NT only | ✅ Done |
| Kasem | xsm | 1303 | NT only | ✅ Done |
| Konkomba | xon | 1460 | NT only | ✅ Done |
| Konni | kma | 2421 | NT only | ✅ Done |
| Mampruli | maw | 1784 | NT only | ✅ Done |
| Nawuri | naw | 1836 | NT only | ✅ Done |
| Ninkare | gur | 1323, 3194 | NT only | ✅ Done |
| Nkonya | nko | 255 | NT only | ✅ Done |
| Ntrubo | ntr | 1795 | NT only | ✅ Done |
| Nyangbo | nyb | 4674 | OT only | ✅ Done |
| Nzema | nzi | 4529 | NT only | ✅ Done |
| Paasaal | sig | 1978 | NT only | ✅ Done |
| Sehwi | sfw | 4630 | NT only | ✅ Done |
| Selee | snw | 1796, 4728 | NT / OT | ✅ Done |
| Sekpele | lip | 1773 | NT only | ✅ Done |
| Siwu | akp | 1738 | NT only | ✅ Done |
| Tafi | tcd | 3070 | NT only | ✅ Done |
| Tampulma | tpm | 1804 | NT only | ✅ Done |
| Tuwuli | bov | 1752 | NT only | ✅ Done |

### Contributors

Thanks to the volunteers who curated these languages:

- [Saani Mustapha Deishini](https://www.linkedin.com/in/saani-mustapha-3747b925a/) — Fulfulde; Maasina, Kasem, Konkomba, Konni, Mampruli, Nawuri, Ninkare, Nkonya, Ntrubo
- [Tyra Koranteng](https://www.linkedin.com/in/tyrakoranteng46/) — Tem, Vagla, Abron, Nyangbo, Nzema, Paasaal, Sehwi
- [Prince Alhassan](https://www.linkedin.com/in/alhassan-prince) — Selee, Sekpele, Siwu, Tafi, Tampulma, Tuwuli
- [Chantelle Amoako-Atta](https://www.linkedin.com/in/chantelleaa/) — Ewe, Hausa, Kasem, Konkomba, Kusaal
- [Foster (Buabeng) Dompreh](https://www.linkedin.com/in/foster-dompreh/) — Fante, Bissa, Chumburung, Dagaare, Dangme
- [Onesimus Addo Appiah](https://www.linkedin.com/in/onesimus-appiah/) — Dangme, Lelemi, Nzema, Sehwi, Sisaala; Tumulung
- [Baffoe Nicholas](https://www.linkedin.com/in/baffoe-nicholas-3b8159267) — Fulfulde; Maasina, Gikyode, Hanga, Kabiye
- [Isaac Donkoh](https://www.linkedin.com/in/isaac-kojo-donkoh) — Anufo, Anyin, Avatime, Bimoba
- [Mich-Seth Owusu](https://linkedin.com/in/mich-seth-owusu) — Asante Twi, Bimoba, Dagaare, Birifor; Southern
- [Bernard Adjei](https://www.linkedin.com/in/bernardmarfoadjei/) — Gonja
- [Dyllis Ofori-Attah](https://www.linkedin.com/in/dyllis-oforiattah/) — Buli
- [Jonathan Asiamah](https://www.linkedin.com/in/jonathan-asiamah-4639a5147/) — Akuapem Twi
- [Kenneth Dotse](https://www.linkedin.com/in/kenneth-kwame-dotse/) — Bassar Ntcham
- [Maxwell Sam](https://www.linkedin.com/in/maxwell-sam-42133044/) — Ga
- [Naporo Alhassan A.Ganiw](https://www.linkedin.com/in/naporo-alhassan-abdul-ganiw-986982319) — Dagbani
- [Timothy Aguya Akasiya](https://www.linkedin.com/in/timothy-aguya-akasiya/) — Deg


To volunteer for a language, open an issue or reach out to the Ghana NLP
Community.

### Maintainer tooling (building the datasets)

The Ghanaian datasets in `bible_parallel_text_datasets/` were produced by the
scripts in this repo and are committed for direct use — **regular users do not
need to run them.** For maintainers and volunteers extending coverage:

- `youversion_parallel_text_builder.py` — builds a Ghanaian-language dataset
  from a YouVersion version id.
- `scripts/scan_viable_versions.py` — probes which versions actually have
  content before scraping.
- `scripts/fetch_reference_language.py` — caches a reference language (see
  *Adding more reference languages* above).
- `scripts/push_dataset_to_hf.py` — publishes data to the
  `ghananlpcommunity/ghana-corpus` dataset. By default it **appends only new
  files** (run `--dry-run` to preview, `--sync` to also re-upload changed
  files). Once a file is on HuggingFace, `ghana_corpus.py` picks it up
  automatically on its next run.
- `scripts/build_and_push_parallel_dataset.py` — merges and publishes a
  curated dataset to HuggingFace (reads `HF_TOKEN` from the environment).

Typical workflow for extending coverage:

```bash
# build a new Ghanaian dataset (or fetch a new reference language), then:
python scripts/push_dataset_to_hf.py --dry-run   # see what's new
python scripts/push_dataset_to_hf.py             # append it to HF
```

---

## Data source

Verse text comes from public **Bible translations**, which are among the best
naturally-occurring sources of sentence-aligned parallel text for low-resource
languages.

> The non-English reference languages were retrieved from
> [YouVersion](https://www.bible.com) (bible.com). Please review YouVersion's
> terms of service before publishing or redistributing derived data.

---

## License

Code in this repository is released under the MIT License. Dataset content is
derived from third-party Bible translations; review the source's terms before
publishing or distributing.

---

## Acknowledgements

Built by the [Ghana NLP Community](https://huggingface.co/ghananlpcommunity).
If you use this data in research, please cite the community and acknowledge the
underlying Bible-translation sources.
