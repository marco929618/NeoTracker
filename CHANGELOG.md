# Changelog

Formato ispirato a [Keep a Changelog](https://keepachangelog.com/it/1.1.0/).

## [1.3] - 2026-11-08

### Aggiunto
- **Multilingua**: interfaccia in italiano, inglese, francese, tedesco e spagnolo (mappa del corpo, messaggi, avvertenze,
  criteri genetici, letteratura, indice UV, scheda stampabile, finestrelle d'avvio). La lingua parte da quella del
  sistema e si cambia in *Impostazioni → Lingua*. Date e numeri seguono la lingua scelta.
- `tools/traduzioni.py`: estrae i testi dal codice e controlla che le traduzioni ci siano tutte (con gli stessi segnaposto);
  `build.py` si ferma se ne manca qualcuna.
- Prove: `tests/test_i18n.py` e `tests/e2e_lingue.py` (ogni schermata nelle 4 lingue, con screenshot).

### Note
- I dati salvati restano in italiano e vengono tradotti solo alla visualizzazione. Il rapporto di testo (`rapporto.txt`) e i
  messaggi della console dell'analisi restano in italiano. Fa fede il testo italiano delle avvertenze legali.
- Le traduzioni sono state fatte con un assistente AI e vanno riviste da madrelingua.
- La pagina «Accesso non autorizzato» è ora in cinque lingue.

## [1.2] - 2026-11-08

### Aggiunto
- **Immagine personale** facoltativa per ogni utente (ritagliata a 256×256 e ricodificata senza metadati).
- **Avviso iniziale** («non è un dispositivo medico») da accettare al primo avvio.
- **Chiave di sessione** casuale per ogni avvio (cookie `HttpOnly; SameSite=Strict`): senza la chiave il server rifiuta ogni richiesta.
- Intestazioni di sicurezza su ogni risposta, CSP `sandbox` sulle immagini, limiti di collegamenti e di tempo.
- Prove di sicurezza automatiche (`tests/test_sicurezza.py`), bandit e CodeQL in CI.
- Documenti: DISCLAIMER, PRIVACY, SECURITY, THIRD_PARTY_NOTICES, CONTRIBUTING.

### Cambiato
- **Open-Meteo** è la fonte predefinita dell'indice UV (gratuita, senza chiave); OpenWeather resta a scelta.
- Coordinate inviate ai servizi meteo arrotondate a ~1 km.
- Etichette dei risultati più prudenti («Nessun allarme dai modelli» al posto di «Indica benigno»).
- Richieste web: solo `https`, dimensione massima, niente `file:`/`ftp:` nemmeno via reindirizzamento; XML PubMed con `ENTITY` rifiutato.
- `melanoma_batch.py`: indirizzo SkinSense solo `https`; pesi PyTorch solo con `weights_only=True`.
- Licenza: **GPL-3.0-or-later**.

## [1.1]
- Finestra di programma (Edge/Chrome in modalità app) con icona nella barra delle applicazioni; si spegne alla chiusura.

## [1.0]
- Prima versione: utenti, profilo, mappa del corpo, storico foto, analisi, letteratura, genetica, indice UV, scheda per il dermatologo.
