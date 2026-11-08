## Che cosa cambia

## Controlli
- [ ] Ho modificato `src/` o `web/` (non `neotracker.py` a mano) e ho eseguito `python build.py`
- [ ] `tests/test_sicurezza.py`, `tests/test_finestra.py`, `tests/test_api.py` passano
- [ ] `bandit -q -r neotracker.py melanoma_batch.py -ll` non segnala nulla
- [ ] Nessun dato personale, foto o chiave nel commit
- [ ] Nessun testo che presenti il programma come diagnostico; nessuna nuova richiesta di rete non dichiarata in PRIVACY.md
- [ ] Il codice aggiunto non è copiato da progetti senza licenza o incompatibili con la GPL-3.0
