# NeoTracker

**Body map, photo history of your moles, multi-model analysis, literature, genetics and UV index: all on your own computer.**

> ⚠️ **NeoTracker is NOT a medical device and does NOT diagnose.** The models are unvalidated research prototypes and can be
> wrong both ways. Any mole that changes, bleeds, itches or worries you must be seen by a dermatologist, whatever the
> software says. Read [DISCLAIMER.md](DISCLAIMER.md). *(Italian is the main language of the app and documentation.)*

## What it does

- Several **users** on one PC, each with an optional **personal picture**, a phenotype/family-history profile and separate data.
- **Interactive body map** (front/back) to place each mole precisely; **dated photo history** (originals kept untouched),
  diameter tracking, side-by-side comparison and a **printable sheet for the dermatologist**.
- **Automatic analysis** of each photo with every installed open-source model (`melanoma_batch.py`), summarized in one report.
- **PubMed literature** on mole recognition and hereditary melanoma, plus the criteria used to evaluate genetic counselling.
- **UV index** for your location (Open-Meteo by default, no key needed; OpenWeather optional) with conservative sun-exposure times.
- A real **desktop-like window** (Edge/Chrome in app mode); runs on `127.0.0.1` only. **No account, no server, no telemetry.**

## Quick start (Windows)

Requires Windows 10/11 with Edge or Chrome and Python 3.9+. Optional: `py -m pip install -U "pillow>=10.3.0"`.

```bat
git clone https://github.com/marco929618/NeoTracker.git
cd NeoTracker
py -3 neotracker.py
```

The mole-analysis models are third-party projects installed separately with `tools/install_melanoma_repos.ps1`
(see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)); everything else works without them.

Your data lives in `%USERPROFILE%\melanoma-repos\NeoTracker_dati` (override with `NEOTRACKER_DATI`) and is **not encrypted** by
the program: use disk encryption. See [PRIVACY.md](PRIVACY.md) and [SECURITY.md](SECURITY.md).

## Development

`python build.py` regenerates `neotracker.py` from `src/` and `web/`. Tests live in `tests/` (see [tests/README.md](tests/README.md)).
Contributions: [CONTRIBUTING.md](CONTRIBUTING.md).

## License

GPL-3.0-or-later — see [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). UV data by
[Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0, non-commercial use).
