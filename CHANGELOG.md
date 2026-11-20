# Changelog

Format inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- **English is now the source language** of the whole repository: documentation, code comments, messages and the
  texts of the interface (the key of every translation). Italian stays available as a selectable interface language,
  exactly like French, German and Spanish. The English text of the legal notices now prevails over the translations.
- The text report (`rapporto.txt`) and the console messages of the analysis are now written in English.
- Region names of the moles are stored in English; databases from earlier versions are migrated at startup
  (legacy Italian values are still recognised when shown).
- The screenshots in `docs/images/` are in English; `README.en.md` was merged into `README.md`.

## [1.3] - 2026-11-08

### Added
- **Multilingual**: interface in Italian, English, French, German and Spanish (body map, messages, notices, genetic
  criteria, literature, UV index, printable sheet, start-up dialogs). The language starts from the system one and is
  changed in *Settings → Language*. Dates and numbers follow the chosen language.
- `tools/traduzioni.py`: extracts the texts from the code and checks that all translations are present (with the same
  placeholders); `build.py` stops if any is missing.
- Tests: `tests/test_i18n.py` and `tests/e2e_lingue.py` (every screen in the 4 languages, with screenshots).

### Notes
- Stored data stayed in Italian and was translated only when shown. The text report (`rapporto.txt`) and the console
  messages of the analysis stayed in Italian. The Italian text of the legal notices prevailed.
- The translations were made with an AI assistant and should be reviewed by native speakers.
- The "Unauthorised access" page is now in five languages.

## [1.2] - 2026-11-08

### Added
- Optional **personal picture** for each user (cropped to 256×256 and re-encoded without metadata).
- **Start-up notice** ("not a medical device") to accept at first launch.
- Random **session key** at every start (`HttpOnly; SameSite=Strict` cookie): without the key the server rejects every request.
- Security headers on every response, CSP `sandbox` on images, connection and time limits.
- Automated security tests (`tests/test_sicurezza.py`), bandit and CodeQL in CI.
- Documents: DISCLAIMER, PRIVACY, SECURITY, THIRD_PARTY_NOTICES, CONTRIBUTING.

### Changed
- **Open-Meteo** is the default source of the UV index (free, no key); OpenWeather stays optional.
- Coordinates sent to the weather services are rounded to ~1 km.
- More cautious result labels ("No alarm from the models" instead of "Indicates benign").
- Web requests: `https` only, maximum size, no `file:`/`ftp:` even via redirects; PubMed XML with `ENTITY` rejected.
- `melanoma_batch.py`: SkinSense address `https` only; PyTorch weights only with `weights_only=True`.
- Licence: **GPL-3.0-or-later**.

## [1.1]
- Program window (Edge/Chrome in app mode) with an icon in the taskbar; it shuts down when closed.

## [1.0]
- First version: users, profile, body map, photo history, analysis, literature, genetics, UV index, sheet for the dermatologist.
