# Politica di sicurezza / Security policy

## Segnalare una vulnerabilità

**Non aprire una Issue pubblica.** Usa la segnalazione privata di GitHub:
**Security → Report a vulnerability** (*Private vulnerability reporting*) in questo repository.
Indica versione, sistema operativo, passi per riprodurre e impatto. Rispondo appena possibile (progetto
mantenuto nel tempo libero: di norma entro 7 giorni per un primo riscontro). Ringrazio pubblicamente chi
segnala in modo responsabile, se lo desidera.

*Please do not open a public issue. Use GitHub's private vulnerability reporting (Security → Report a vulnerability).*

## Versioni supportate

Solo l'ultima versione pubblicata riceve correzioni di sicurezza.

## Modello di minaccia

NeoTracker è un'app **locale** che custodisce **dati sulla salute** e foto. Si difende da:

1. **Altri computer della rete** → il server ascolta solo su `127.0.0.1`.
2. **Pagine web aperte nel tuo browser** (CSRF, *DNS rebinding*, richieste a `localhost`) → controllo di `Host`
   e `Origin`, intestazione obbligatoria `X-NeoTracker` sulle operazioni che modificano, **chiave di sessione**
   casuale (256 bit) consegnata alla finestra dell'app e conservata in un cookie `HttpOnly; SameSite=Strict`,
   confrontata a tempo costante. Senza la chiave ogni richiesta (tranne `/api/ping`) è rifiutata.
3. **Altri programmi e utenti del PC** → la chiave cambia a ogni avvio; il file `sessione.token` ha permessi
   `0600` (Linux/Mac) e viene cancellato alla chiusura; `impostazioni.json` (con l'eventuale chiave
   OpenWeather) ha permessi `0600` ed è scritto in modo atomico.
4. **Contenuti malevoli** (immagini-trappola, file travestiti, testi con HTML) → riconoscimento del formato dai
   byte e non dall'estensione, limite di megapixel (150 MP) e di dimensione, ricodifica dell'immagine personale,
   nessuna interpretazione di HTML nei testi (la pagina costruisce elementi, non stringhe HTML), CSP rigida
   (`script-src 'self'`, `connect-src 'self'`, nessuna risorsa esterna), `X-Content-Type-Options: nosniff`,
   `X-Frame-Options: DENY`, CSP `sandbox` sulle immagini servite.
5. **Percorsi e SQL** → i file si risolvono solo dentro la cartella dati; query sempre parametrizzate.
6. **Risposte di servizi esterni** → solo `https`, niente `file:`/`ftp:` (nemmeno via reindirizzamento),
   dimensione massima, rifiuto degli XML con dichiarazioni `ENTITY`.
7. **Esaurimento risorse** → timeout dei collegamenti, tetto ai collegamenti di «presenza», limiti di dimensione.

Le prove automatiche sono in `tests/test_sicurezza.py`; l'analisi statica (bandit) e CodeQL girano in CI.

## Limiti noti (cosa NON è protetto)

- **Malware o altri programmi che girano con il tuo stesso account** possono leggere la cartella dati e il file
  della chiave: non è un confine che il programma possa difendere. Usa la cifratura del disco (BitLocker) e
  un account con password. I dati **non sono cifrati** dal programma.
- La chiave di sessione compare nella riga di comando con cui si apre la finestra (visibile ad altri processi dello
  stesso utente per pochi istanti) e, se Edge/Chrome non si trovano, nella cronologia del browser predefinito
  (vale solo fino alla chiusura di NeoTracker).
- I **progetti di analisi** (TensorFlow, PyTorch, ecc.) sono codice e modelli di terzi, eseguiti in ambienti
  virtuali locali: installali solo dalle fonti indicate. I pesi PyTorch si caricano con `weights_only=True`
  (solo numeri, nessun codice); i modelli Keras sono file di terzi.
- **SkinSense** (facoltativo, disattivato) invia la foto a un servizio che non controlliamo.
- Il programma usa la libreria **Pillow** per aprire immagini: tienila aggiornata (≥ 10.3.0; l'app avvisa
  nelle Impostazioni se è vecchia).

## Buone pratiche per chi lo usa

Aggiorna Windows, Python e Pillow; non esporre la porta 8750 con *port forwarding* o tunnel; non eseguire
NeoTracker su un computer condiviso senza cifratura; non pubblicare mai la cartella dei dati (contiene dati
sanitari). Se pubblichi un tuo fork, non includere dati reali, foto o impostazioni: il `.gitignore` li esclude.
