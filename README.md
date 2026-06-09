# Ghana MT Parallel Corpus

**Ghana Machine Translation Parallel Corpus**

A toolkit for building parallel text datasets from Ghanaian Bible translations on [YouVersion](https://www.bible.com). It automatically pairs local-language Bible verses with their English equivalents and saves the results as clean CSVs ready for machine translation training and NLP research.

---

## What it does

YouVersion hosts hundreds of Bible translations, including many Ghanaian languages — Twi, Ga, Ewe, Dagbani, Fante, and more. Each translation is aligned verse-by-verse with a common reference, which makes Bible text one of the best naturally-occurring sources of parallel sentences for low-resource African languages.

This project scrapes those verse pairs, cleans the text, and saves them as structured CSV files. The end result is a collection of sentence-level `(local language, English)` pairs that can be used directly to train or fine-tune machine translation models.

### What happens when you run it

1. A pool of Chrome browsers opens (in the background) and works through every book and chapter of the Bible in parallel.
2. For each verse, the scraper fetches the local-language text and the English reference text (CEB version).
3. If both sides are present, the pair is saved. If either side is missing, the verse is skipped.
4. English verses are cached so they are only fetched once across all languages.
5. Progress is saved after every chapter so a run can be interrupted and resumed without losing work.

### Output files

Everything is written to `bible_parallel_text_datasets/`:

```
bible_parallel_text_datasets/
    english_cache.csv        verse_key, eng
    Asante_Twi_twi.csv       verse_key, version_id, eng, local
    Ewe_ee.csv
    Ga_gaa.csv
    progress.json
    testament_status.json
```

One CSV per language, named `{Language_Name}_{lang_code}.csv`. The English cache is shared across all languages so it is only built once.

Each language CSV has four columns:

| Column | Description |
|---|---|
| `verse_key` | Bible reference, e.g. `GEN.1.1` |
| `version_id` | YouVersion version number |
| `eng` | Cleaned English verse text |
| `local` | Cleaned local-language verse text |

---

## Quick start

### Requirements

- Python 3.10 or later
- Google Chrome installed
- A `youversion_ghana_versions.csv` file listing the versions to scrape (see format below)

### Install dependencies

```bash
pip install selenium webdriver-manager pandas datasets huggingface_hub
```

### Clone and run

```bash
git clone https://github.com/ghananlpcommunity/Ghana-MT-PC.git
cd Ghana-MT-PC
```

Create your versions file (see format below), then run the scraper:

```bash
python youversion_parallel_text_builder.py
```

Once scraping is done, merge and push to HuggingFace:

```bash
python build_and_push_parallel_dataset.py
```

### Versions file format

The scraper reads a CSV called `youversion_ghana_versions.csv`. Each row is one Bible version to scrape. You can find version IDs in YouVersion URLs — for example `https://www.bible.com/bible/1461/GEN.1.1` has version ID `1461`.

```csv
version_id,lang_code,lang_name,abbr
1461,twi,Asante Twi,ASCMB
1861,twi,Asante Twi,TWI
2708,ee,Ewe,NEGAB
3625,gaa,Ga,GAAGB
```

`abbr` is the version abbreviation used in YouVersion URLs. It is optional but recommended — some versions require it to load correctly.

### Tuning the scraper

At the top of `youversion_parallel_text_builder.py` there are a few settings worth knowing about:

```python
NUM_WORKERS = 8      # number of parallel Chrome browsers
                     # lower this if you hit rate limits or run out of RAM

HEADLESS = True      # set False to watch the browsers while debugging

OUTPUT_ROOT = "./bible_parallel_text_datasets"  # where CSVs are written
```

### Resuming an interrupted run

The scraper tracks progress in `bible_parallel_text_datasets/progress.json`. If a run is interrupted for any reason, just run the same command again — already-completed chapters are skipped automatically.

### Pushing to HuggingFace

Edit the config block at the top of `build_and_push_parallel_dataset.py`:

```python
LANG_CSV     = "Asante_Twi_twi"   # CSV name without .csv, or None for all languages
EXISTING_CSV = Path("...")         # path to any existing parallel sentences to merge in
HF_TOKEN     = "hf_..."           # your HuggingFace write token
HF_REPO_ID   = "your-org/your-dataset-name"
```

Then run:

```bash
python build_and_push_parallel_dataset.py
```

---

## Languages covered

The table below lists all languages confirmed to have content on YouVersion and currently tracked by this project. Coverage was verified by probing Old Testament and New Testament probe verses for each version before scraping.

| Language | Code | Version IDs | Coverage | Volunteer | Status |
|---|---|---|---|---|---|
| Akuapem Twi | twi | 1631, 3439, 3440 | OT + NT | — | Not started |
| Asante Twi | twi | 1461, 1861, 2094 | OT + NT | [Mich-Seth Owusu](https://linkedin.com/in/mich-seth-owusu) | ✅ Done |
| Bassar Ntcham | bud | 2235 | OT + NT | [Mich-Seth Owusu](https://linkedin.com/in/mich-seth-owusu) | ✅ Done |
| Bimoba | bim | 1748 | OT + NT | [Mich-Seth Owusu](https://linkedin.com/in/mich-seth-owusu) | ✅ Done |
| Buli | bwu | 2176 | OT + NT | — | Not started |
| Dagaare | dga | 4573 | OT + NT | — | Not started |
| Dagbani | dag | 2263, 2264 | OT + NT | — | Not started |
| Dangme | ada | 2265 | OT + NT | — | Not started |
| Deg | mzw | 2012 | OT + NT | — | Not started |
| Ewe | ewe | 1613, 2259, 3306 | OT + NT | — | Not started |
| Fante | fat | 2913, 2914 | OT + NT | — | Not started |
| Fulfulde; Maasina | ffm | 3093 | OT + NT | — | Not started |
| Ga | gaa | 2708, 2712 | OT + NT | — | Not started |
| Gonja | gjn | 1729 | OT + NT | — | Not started |
| Hausa | hau | 71, 1614 | OT + NT | — | Not started |
| Kasem | xsm | 3661 | OT + NT | — | Not started |
| Konkomba | xon | 1150 | OT + NT | — | Not started |
| Kusaal | kus | 3752 | OT + NT | — | Not started |
| Lelemi | lef | 2442 | OT + NT | — | Not started |
| Nzema | nzi | 2717 | OT + NT | — | Not started |
| Sehwi | sfw | 2710 | OT + NT | — | Not started |
| Sisaala; Tumulung | sil | 2553 | OT + NT | — | Not started |
| Tem | kdh | 1384 | OT + NT | — | Not started |
| Vagla | vag | 1938 | OT + NT | — | Not started |
| Abron | abr | 3971 | NT only | — | Not started |
| Anufo | cko | 2168 | NT only | — | Not started |
| Anyin | any | 1731 | NT only | — | Not started |
| Avatime | avn | 1982 | NT only | — | Not started |
| Bimoba | bim | 1838 | NT only | — | Not started |
| Birifor; Southern | biv | 2148 | NT only | [Mich-Seth Owusu](https://linkedin.com/in/mich-seth-owusu) | ✅ Done |
| Bissa | bib | 1751 | NT only | — | Not started |
| Chumburung | ncu | 437 | NT only | — | Not started |
| Dagaare | dga | 2268 | NT only | — | Not started |
| Dangme | ada | 2322 | NT only | — | Not started |
| Fulfulde; Maasina | ffm | 1175 | NT only | — | Not started |
| Gikyode | acd | 1741 | NT only | — | Not started |
| Hanga | hag | 1499 | OT only | — | Not started |
| Kabiye | kbp | 555 | NT only | — | Not started |
| Kasem | xsm | 1303 | NT only | — | Not started |
| Konkomba | xon | 1460 | NT only | — | Not started |
| Konni | kma | 2421 | NT only | — | Not started |
| Mampruli | maw | 1784 | NT only | — | Not started |
| Nawuri | naw | 1836 | NT only | — | Not started |
| Ninkare | gur | 1323, 3194 | NT only | — | Not started |
| Nkonya | nko | 255 | NT only | — | Not started |
| Ntrubo | ntr | 1795 | NT only | — | Not started |
| Nyangbo | nyb | 4674 | OT only | — | Not started |
| Nzema | nzi | 4529 | NT only | — | Not started |
| Paasaal | sig | 1978 | NT only | — | Not started |
| Sehwi | sfw | 4630 | NT only | — | Not started |
| Selee | snw | 1796, 4728 | NT / OT | — | Not started |
| Sekpele | lip | 1773 | NT only | — | Not started |
| Siwu | akp | 1738 | NT only | — | Not started |
| Tafi | tcd | 3070 | NT only | — | Not started |
| Tampulma | tpm | 1804 | NT only | — | Not started |
| Tuwuli | bov | 1752 | NT only | — | Not started |

Any language with a YouVersion Bible translation can be added by including its version ID in the versions CSV. To volunteer for a language, open an issue or reach out to the Ghana NLP Community.

---

## License

Dataset content is sourced from YouVersion. Please review [YouVersion's terms of service](https://www.youversion.com/terms/) before publishing or distributing scraped data. Code in this repository is released under the MIT License.

---

## Acknowledgements

Built by the [Ghana NLP Community](https://huggingface.co/ghananlpcommunity). If you use this data in research, please cite the community and acknowledge YouVersion as the source.
