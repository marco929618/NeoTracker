# Contributing to NeoTracker

Thank you! This is a personal/research project: small, focused contributions are welcome.

## First of all

- **Never attach photos of moles, health data or personal data** to Issues, Pull Requests or discussions.
  To reproduce a problem use made-up images and data.
- Vulnerabilities must be reported privately: see [SECURITY.md](SECURITY.md).
- Changes that present the program as a diagnostic or screening tool, or that add telemetry, sending of data to
  undeclared servers or data collection without explicit consent, will not be accepted.

## How to work

```bash
pip install -r requirements-dev.txt
# edit src/ and web/ (NOT neotracker.py: it is generated)
python build.py
python tests/test_sicurezza.py && python tests/test_finestra.py && python tests/test_api.py && python tests/test_i18n.py
bandit -q -r neotracker.py melanoma_batch.py -ll
```

- The program must stay a **single file using only the standard library** (Pillow is optional).
- Comments, documentation and the **source texts** shown to the user are written **in English**, simple and explained
  (the project is also meant for people who do not program). The other languages are translations: see "Languages and
  translations" below. Function and variable names are partly Italian for historical reasons; leave them as they are.
- Every security fix or new network feature must have a test in `tests/`.
- No interface text may promise or suggest a diagnosis; results stay "experimental".
- Always include `python build.py` in the commit: CI checks that `neotracker.py` is up to date.

## Languages and translations

The interface speaks English, Italian, French, German and Spanish. The **English text is the original and acts as the key**:

- in JavaScript write `NT.t('Save mole')`, with named placeholders `NT.t('{n} days ago', { n: 3 })` and plurals with
  `NT.tp(n, '{n} photo', '{n} photos')`; tables of texts are marked with `NT.m('...')`;
- in Python the texts that reach the user (errors, server messages, analysis notes) are marked with `T("...")`;
  for variable values write `T("... {name} ...").format(name=...)`;
- the translations live in `web/i18n_it.js`, `i18n_fr.js`, `i18n_de.js`, `i18n_es.js` (one entry per line:
  `"English text": "translation"`); placeholders (`{n}`, `{name}`…) must stay identical. English needs no dictionary.

`python tools/traduzioni.py` checks that every text has a translation in all languages (`--missing de` lists those
missing in German, `--list` prints all texts, `--italian` looks for unmarked Italian texts). `build.py` stops if
anything is missing, so CI checks it too. Stored data keeps English values (region names) and the profile codes stay
in Italian internally; they are translated only when shown. The text report `rapporto.txt` and the console messages of
the analysis stay in English. The English text of the legal notices prevails over the translations.

**Adding a language** (for example `pt`): copy `web/i18n_it.js` to `web/i18n_pt.js` changing `.it =` to `.pt =` and
translate the values; add the code to `LINGUE` in `src/00_head.py`, to `LINGUE`, `LOCALI` and the month names in
`web/i18n.js`, a `<script src="/i18n_pt.js">` in `web/index.html`, the translations in `TESTI_AVVIO`
(`src/90_main.py`) and in `_ACCESSO_NEGATO_TESTI` (`src/40_http.py`); then run `python tools/traduzioni.py`,
`python build.py` and `python tests/e2e_lingue.py` (look at the screenshots in `tests/out/lingue/`). The translations
were made with the help of an AI assistant: review by native speakers is very welcome.

## Licence of contributions

By submitting a contribution you agree that it is released under the project's licence (GPL-3.0-or-later). Do not add
code copied from projects without a licence or with an incompatible licence (see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).
