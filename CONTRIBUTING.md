# Contribuire a NeoTracker

Grazie! Questo è un progetto personale/di ricerca: contributi piccoli e mirati sono i benvenuti.

## Prima di tutto

- **Non allegare mai foto di nei, dati sanitari o dati personali** in Issue, Pull Request o discussioni.
  Per riprodurre un problema usa immagini e dati inventati.
- Le vulnerabilità vanno segnalate in privato: vedi [SECURITY.md](SECURITY.md).
- Non verranno accettate modifiche che presentino il programma come strumento diagnostico o di screening,
  che aggiungano telemetria, invii di dati a server non dichiarati o raccolta di dati senza consenso esplicito.

## Come lavorare

```bash
pip install -r requirements-dev.txt
# modifica src/ e web/ (NON neotracker.py: è generato)
python build.py
python tests/test_sicurezza.py && python tests/test_finestra.py && python tests/test_api.py
bandit -q -r neotracker.py melanoma_batch.py -ll
```

- Il programma deve restare **a file singolo con sola libreria standard** (Pillow è facoltativo).
- Commenti e testi per l'utente **in italiano**, semplici e spiegati (il progetto è pensato anche per chi non programma).
- Ogni correzione di sicurezza o nuova funzione di rete deve avere una prova in `tests/`.
- Nessun testo dell'interfaccia che prometta o suggerisca diagnosi; i risultati restano «sperimentali».
- Includi sempre `python build.py` nel commit: la CI controlla che `neotracker.py` sia aggiornato.

## Licenza dei contributi

Inviando un contributo accetti che sia rilasciato con la licenza del progetto (GPL-3.0-or-later). Non inserire codice
copiato da progetti senza licenza o con licenza incompatibile (vedi [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).
