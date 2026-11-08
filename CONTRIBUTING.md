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
python tests/test_sicurezza.py && python tests/test_finestra.py && python tests/test_api.py && python tests/test_i18n.py
bandit -q -r neotracker.py melanoma_batch.py -ll
```

- Il programma deve restare **a file singolo con sola libreria standard** (Pillow è facoltativo).
- Commenti e **testi originali** per l'utente **in italiano**, semplici e spiegati (il progetto è pensato anche per chi non programma).
  Le altre lingue sono traduzioni: vedi «Lingue e traduzioni» qui sotto.
- Ogni correzione di sicurezza o nuova funzione di rete deve avere una prova in `tests/`.
- Nessun testo dell'interfaccia che prometta o suggerisca diagnosi; i risultati restano «sperimentali».
- Includi sempre `python build.py` nel commit: la CI controlla che `neotracker.py` sia aggiornato.

## Lingue e traduzioni

L'interfaccia parla italiano, inglese, francese, tedesco e spagnolo. Il **testo italiano è l'originale e fa da chiave**:

- in JavaScript si scrive `NT.t('Salva neo')`, con segnaposto con nome `NT.t('{n} giorni fa', { n: 3 })` e plurali con
  `NT.tp(n, '{n} foto', '{n} foto')`; le tabelle di testi si segnano con `NT.m('...')`;
- in Python i testi che arrivano all'utente (errori, messaggi del server, note dell'analisi) si segnano con `T("...")`;
  per valori variabili si scrive `T("... {nome} ...").format(nome=...)`;
- le traduzioni stanno in `web/i18n_en.js`, `i18n_fr.js`, `i18n_de.js`, `i18n_es.js` (una voce per riga: `"testo italiano": "traduzione"`);
  i segnaposto (`{n}`, `{nome}`…) devono restare identici.

`python tools/traduzioni.py` controlla che ogni testo abbia la traduzione in tutte le lingue (`--mancano de` elenca quelli
che mancano in tedesco, `--elenco` stampa tutti i testi, `--italiano` cerca testi italiani non segnati). `build.py` si ferma se
qualcosa manca, quindi anche la CI lo verifica. I dati salvati restano in italiano (nomi delle regioni, profilo) e si
traducono solo quando vengono mostrati; il rapporto di testo `rapporto.txt` e i messaggi della console dell'analisi restano in italiano.
Il testo italiano delle avvertenze legali prevale sulle traduzioni.

**Aggiungere una lingua** (per esempio `pt`): copia `web/i18n_en.js` in `web/i18n_pt.js` cambiando `.en =` in `.pt =` e traduci
i valori; aggiungi il codice a `LINGUE` in `src/00_head.py`, a `LINGUE`, `LOCALI` e ai nomi dei mesi in `web/i18n.js`, uno
`<script src="/i18n_pt.js">` in `web/index.html`, le traduzioni in `TESTI_AVVIO` (`src/90_main.py`) e in `_ACCESSO_NEGATO_TESTI`
(`src/40_http.py`); poi `python tools/traduzioni.py`, `python build.py` e `python tests/e2e_lingue.py` (guarda gli screenshot
in `tests/out/lingue/`). Le traduzioni sono state fatte con l'aiuto di un assistente AI: la revisione di madrelingua è molto gradita.

## Licenza dei contributi

Inviando un contributo accetti che sia rilasciato con la licenza del progetto (GPL-3.0-or-later). Non inserire codice
copiato da progetti senza licenza o con licenza incompatibile (vedi [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).
