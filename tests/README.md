# Prove automatiche

| File | Che cosa prova | Richiede |
|---|---|---|
| `test_sicurezza.py` | Chiave di sessione, Host/Origin/CSRF, intestazioni, percorsi, caricamenti pericolosi, limiti, richieste web | Python + Pillow |
| `test_finestra.py` | Ciclo di vita della finestra (battiti, presenza, spegnimento) con tempo simulato | Python |
| `test_api.py` | Tutto il backend (utenti, profilo, nei, foto, avatar, UV, PubMed finto…) con **servizi finti** | Python + Pillow |
| `test_vita.py` | Avvio reale del programma, finestra in un Chrome vero, chiusura, «Esci», avvio senza console | Playwright + Chrome |
| `test_i18n.py` | Lingue: dizionari completi, nomi di regione unici, impostazione «lingua», pagina servita, finestrelle d'avvio | Python |
| `e2e_lingue.py` | Ogni schermata in inglese, francese, tedesco e spagnolo (testi senza traduzione, parole italiane rimaste, formati di data, cambio lingua); screenshot in `tests/out/lingue/` | Playwright + Chrome |
| `e2e.py` | L'app intera nel browser (avviso iniziale, avatar, mappa, foto, UV, stampa…) | Playwright + Chrome |

```bash
python tests/test_sicurezza.py
python tests/test_finestra.py
python tests/test_api.py
python tests/test_i18n.py
```

Per le prove nel browser: `pip install playwright && playwright install chromium`, poi indica il browser con la variabile
`NEOTRACKER_TEST_CHROME` (predefinito `/usr/bin/google-chrome`) e lancia `python tests/e2e.py` / `python tests/e2e_lingue.py` / `python tests/test_vita.py`
(usano porte locali tra 8751 e 8799 e cartelle temporanee: non toccano i tuoi dati).

**Analisi dei nei:** i progetti di terzi pesano gigabyte, quindi le prove di `test_api.py` e `e2e.py` che richiedono
un'analisi vera vengono **saltate** a meno che `NEOTRACKER_TEST_REPOS` punti a una cartella con i progetti installati.
Tutti i servizi esterni (Open-Meteo, OpenWeather, PubMed, ipwho.is) sono sostituiti da `mock_servizi.py`: le prove non usano internet.
