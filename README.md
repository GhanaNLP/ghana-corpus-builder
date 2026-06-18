# Ghana Corpus Builder

A toolkit for building parallel text datasets from Ghanaian Bible translations on [YouVersion](https://www.bible.com). It automatically pairs local-language Bible verses with their English equivalents and saves the results as clean CSVs ready for machine translation training and NLP research.

---

## What it does

YouVersion hosts hundreds of Bible translations, including many Ghanaian languages — Twi, Ga, Ewe, Dagbani, Fante, and more. Each translation is aligned verse-by-verse with a common reference, which makes Bible text one of the best naturally-occurring sources of parallel sentences for low-resource African languages.

This project scrapes those verse pairs, cleans the text, and saves them as structured CSV files. The end result is a collection of sentence-level `(local language, English)` pairs that can be used directly to train or fine-tune machine translation models.

## Quick start

### Requirements

- Python 3.10 or later
- Google Chrome installed

> All Python dependencies are installed automatically on first run. You do not need to run `pip install` yourself.

### Clone and run

```bash
git clone https://github.com/GhanaNLP/ghana-mt-builder.git
cd ghana-mt-builder
python youversion_parallel_text_builder.py
```

The script will:
1. Ask you to confirm you have Chrome installed, as this is required for the scraping to work.
2. Install any required packages in the background
3. Prompt you for a version ID - This is the version ID you received from Ghana NLP after accepting to participate in this project.

### Resuming an interrupted run

The scraper tracks progress in `bible_parallel_text_datasets/progress.json`. If a run is interrupted for any reason, just run the same command again and select the same version ID — already-completed chapters are skipped automatically.

> `progress.json` and `testament_status.json` are listed in `.gitignore` and will not be committed to the repository.

---

## Languages covered

The table below lists all languages confirmed to have content on YouVersion and currently tracked by this project. Coverage was verified by probing Old Testament and New Testament probe verses for each version before scraping.

| Language | Code | Version IDs | Coverage | Volunteer | Status |
|---|---|---|---|---|---|
| Akuapem Twi | twi | 1631, 3439, 3440 | OT + NT | [Jonathan Asiamah](https://www.linkedin.com/in/jonathan-asiamah-4639a5147/) | Assigned |
| Asante Twi | twi | 1461, 1861, 2094 | OT + NT | [Mich-Seth Owusu](https://linkedin.com/in/mich-seth-owusu) | ✅ Done |
| Bassar Ntcham | bud | 2235 | OT + NT | [Kenneth Dotse](https://www.linkedin.com/in/kenneth-kwame-dotse/) | Assigned |
| Bimoba | bim | 1748 | OT + NT | [Mich-Seth Owusu](https://linkedin.com/in/mich-seth-owusu) | ✅ Done |
| Buli | bwu | 2176 | OT + NT | [Dyllis Ofori-Attah](https://www.linkedin.com/in/dyllis-oforiattah/) | Assigned |
| Dagaare | dga | 4573 | OT + NT | [Mich-Seth Owusu](https://linkedin.com/in/mich-seth-owusu) | ✅ Done |
| Dagbani | dag | 2263, 2264 | OT + NT | [Naporo Alhassan A.Ganiw](https://www.linkedin.com/in/naporo-alhassan-abdul-ganiw-986982319) | Assigned |
| Dangme | ada | 2265 | OT + NT | [Onesimus Addo Appiah](https://www.linkedin.com/in/onesimus-appiah/) | ✅ Done |
| Deg | mzw | 2012 | OT + NT | [Timothy Aguya Akasiya](https://www.linkedin.com/in/timothy-aguya-akasiya/) | Assigned |
| Ewe | ewe | 1613, 2259, 3306 | OT + NT | [Chantelle Amoako-Atta](https://www.linkedin.com/in/chantelleaa/) | ✅ Done |
| Fante | fat | 2913, 2914 | OT + NT | [Foster (Buabeng) Dompreh](https://www.linkedin.com/in/foster-dompreh/) | ✅ Done |
| Fulfulde; Maasina | ffm | 3093 | OT + NT | [Saani Mustapha Deishini](https://www.linkedin.com/in/saani-mustapha-3747b925a/) | ✅ Done |
| Ga | gaa | 2708, 2712 | OT + NT | [Maxwell Sam](https://www.linkedin.com/in/maxwell-sam-42133044/) | ✅ Done |
| Gonja | gjn | 1729 | OT + NT | [Bernard Adjei](https://www.linkedin.com/in/bernardmarfoadjei/) | ✅ Done |
| Hausa | hau | 71, 1614 | OT + NT | [Chantelle Amoako-Atta](https://www.linkedin.com/in/chantelleaa/) | Assigned |
| Kasem | xsm | 3661 | OT + NT | [Chantelle Amoako-Atta](https://www.linkedin.com/in/chantelleaa/) | Assigned |
| Konkomba | xon | 1150 | OT + NT | [Chantelle Amoako-Atta](https://www.linkedin.com/in/chantelleaa/) | Assigned |
| Kusaal | kus | 3752 | OT + NT | [Chantelle Amoako-Atta](https://www.linkedin.com/in/chantelleaa/) | Assigned |
| Lelemi | lef | 2442 | OT + NT | [Onesimus Addo Appiah](https://www.linkedin.com/in/onesimus-appiah/) | Assigned |
| Nzema | nzi | 2717 | OT + NT | [Onesimus Addo Appiah](https://www.linkedin.com/in/onesimus-appiah/) | Assigned |
| Sehwi | sfw | 2710 | OT + NT | [Onesimus Addo Appiah](https://www.linkedin.com/in/onesimus-appiah/) | Assigned |
| Sisaala; Tumulung | sil | 2553 | OT + NT | [Onesimus Addo Appiah](https://www.linkedin.com/in/onesimus-appiah/) | Assigned |
| Tem | kdh | 1384 | OT + NT | [Tyra Koranteng](https://www.linkedin.com/in/tyrakoranteng46/) | ✅ Done |
| Vagla | vag | 1938 | OT + NT | [Tyra Koranteng](https://www.linkedin.com/in/tyrakoranteng46/) | ✅ Done |
| Abron | abr | 3971 | NT only | [Tyra Koranteng](https://www.linkedin.com/in/tyrakoranteng46/) | ✅ Done |
| Anufo | cko | 2168 | NT only | [Isaac Donkoh](https://www.linkedin.com/in/isaac-kojo-donkoh) | ✅ Done |
| Anyin | any | 1731 | NT only | [Isaac Donkoh](https://www.linkedin.com/in/isaac-kojo-donkoh) | ✅ Done |
| Avatime | avn | 1982 | NT only | [Isaac Donkoh](https://www.linkedin.com/in/isaac-kojo-donkoh) | ✅ Done |
| Bimoba | bim | 1838 | NT only | [Isaac Donkoh](https://www.linkedin.com/in/isaac-kojo-donkoh) | ✅ Done |
| Birifor; Southern | biv | 2148 | NT only | [Mich-Seth Owusu](https://linkedin.com/in/mich-seth-owusu) | ✅ Done |
| Bissa | bib | 1751 | NT only | [Foster (Buabeng) Dompreh](https://www.linkedin.com/in/foster-dompreh/) | Assigned |
| Chumburung | ncu | 437 | NT only | [Foster (Buabeng) Dompreh](https://www.linkedin.com/in/foster-dompreh/) | Assigned |
| Dagaare | dga | 2268 | NT only | [Foster (Buabeng) Dompreh](https://www.linkedin.com/in/foster-dompreh/) | Assigned |
| Dangme | ada | 2322 | NT only | [Foster (Buabeng) Dompreh](https://www.linkedin.com/in/foster-dompreh/) | Assigned |
| Fulfulde; Maasina | ffm | 1175 | NT only | [Baffoe Nicholas](https://www.linkedin.com/in/baffoe-nicholas-3b8159267) | Assigned |
| Gikyode | acd | 1741 | NT only | [Baffoe Nicholas](https://www.linkedin.com/in/baffoe-nicholas-3b8159267) | Assigned |
| Hanga | hag | 1499 | OT only | [Baffoe Nicholas](https://www.linkedin.com/in/baffoe-nicholas-3b8159267) | Assigned |
| Kabiye | kbp | 555 | NT only | [Baffoe Nicholas](https://www.linkedin.com/in/baffoe-nicholas-3b8159267) | Assigned |
| Kasem | xsm | 1303 | NT only | [Saani Mustapha Deishini](https://www.linkedin.com/in/saani-mustapha-3747b925a/) | ✅ Done |
| Konkomba | xon | 1460 | NT only | [Saani Mustapha Deishini](https://www.linkedin.com/in/saani-mustapha-3747b925a/) | ✅ Done |
| Konni | kma | 2421 | NT only | [Saani Mustapha Deishini](https://www.linkedin.com/in/saani-mustapha-3747b925a/) | ✅ Done |
| Mampruli | maw | 1784 | NT only | [Saani Mustapha Deishini](https://www.linkedin.com/in/saani-mustapha-3747b925a/) | ✅ Done |
| Nawuri | naw | 1836 | NT only | [Saani Mustapha Deishini](https://www.linkedin.com/in/saani-mustapha-3747b925a/) | ✅ Done |
| Ninkare | gur | 1323, 3194 | NT only | [Saani Mustapha Deishini](https://www.linkedin.com/in/saani-mustapha-3747b925a/) | ✅ Done |
| Nkonya | nko | 255 | NT only | [Saani Mustapha Deishini](https://www.linkedin.com/in/saani-mustapha-3747b925a/) | ✅ Done |
| Ntrubo | ntr | 1795 | NT only | [Saani Mustapha Deishini](https://www.linkedin.com/in/saani-mustapha-3747b925a/) | ✅ Done |
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

Dataset content is sourced from YouVersion. Please review YouVersion's terms of service before publishing or distributing scraped data. Code in this repository is released under the MIT License.

---

## Acknowledgements

Built by the [Ghana NLP Community](https://huggingface.co/ghananlpcommunity). If you use this data in research, please cite the community and acknowledge YouVersion as the source.
