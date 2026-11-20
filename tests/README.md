# Automated tests

| File | What it tests | Requires |
|---|---|---|
| `test_sicurezza.py` | Session key, Host/Origin/CSRF, headers, paths, dangerous uploads, limits, web requests | Python + Pillow |
| `test_finestra.py` | Window life cycle (heartbeats, presence, shutdown) with simulated time | Python |
| `test_api.py` | The whole backend (users, profile, moles, photos, avatar, UV, mock PubMed…) with **mock services** | Python + Pillow |
| `test_vita.py` | Real start of the program, window in a real Chrome, closing, "Close NeoTracker", start without a console | Playwright + Chrome |
| `test_i18n.py` | Languages: complete dictionaries, unique region names, "lingua" (language) setting, served page, start-up windows | Python |
| `e2e_lingue.py` | Every screen in Italian, French, German and Spanish (untranslated texts, English words left over, date formats, language change); screenshots in `tests/out/lingue/` | Playwright + Chrome |
| `e2e.py` | The whole app in the browser (start-up notice, avatar, map, photos, UV, print…) | Playwright + Chrome |

```bash
python tests/test_sicurezza.py
python tests/test_finestra.py
python tests/test_api.py
python tests/test_i18n.py
```

For the browser tests: `pip install playwright && playwright install chromium`, then point to the browser with the
`NEOTRACKER_TEST_CHROME` variable (default `/usr/bin/google-chrome`) and run `python tests/e2e.py` / `python tests/e2e_lingue.py` / `python tests/test_vita.py`
(they use local ports between 8751 and 8799 and temporary folders: they do not touch your data).

**Mole analysis:** the third-party projects weigh gigabytes, so the tests of `test_api.py` and `e2e.py` that need
a real analysis are **skipped** unless `NEOTRACKER_TEST_REPOS` points to a folder with the projects installed.
All external services (Open-Meteo, OpenWeather, PubMed, ipwho.is) are replaced by `mock_servizi.py`: the tests do not use the internet.
