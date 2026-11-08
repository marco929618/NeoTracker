# Privacy e protezione dei dati / Privacy and data protection

**In breve:** NeoTracker gira **solo sul tuo computer**. Non ha account, non ha server degli sviluppatori, non
raccoglie statistiche né telemetria. I dati restano nella tua cartella. Escono dal computer solo le richieste
elencate qui sotto, che avvengono **solo se usi la funzione corrispondente**.

*In short: NeoTracker runs only on your computer, has no accounts, no developer-operated server and no
telemetry. Your data stays in your folder. Only the requests listed below leave your machine, and only when
you use the matching feature.*

## Dati conservati sul tuo computer

Nella cartella dei dati (predefinita: `%USERPROFILE%\melanoma-repos\NeoTracker_dati`, modificabile) trovi:

| Che cosa | Dove | Note |
|---|---|---|
| Utenti, profilo (sesso, età, fototipo, familiarità, storia personale, note), nei e posizioni | `neotracker.db` (SQLite) | Sono **dati sulla salute**: categoria particolare ai sensi dell'art. 9 GDPR |
| Foto dei nei (originali **non modificati**, miniature) | `foto/`, `miniature/` | Gli originali possono contenere metadati (GPS, modello del telefono) |
| Immagine personale (facoltativa) | `avatar/` | Ritagliata a 256×256, **senza metadati** |
| Rapporti delle analisi | `rapporti/` | |
| Impostazioni, eventuale chiave OpenWeather, posizione approssimata (≈ 1 km) | `impostazioni.json` | File leggibile solo dal proprietario (su Linux/Mac) |
| Chiave di sessione temporanea | `sessione.token` | Si cancella alla chiusura |
| Registro tecnico | `neotracker.log` | Solo messaggi del programma, niente dati sanitari |

**Non cifrati:** i file non sono cifrati dal programma. Per proteggerli usa la cifratura del disco
(BitLocker su Windows) e un account utente con password. Chi può aprire la tua cartella può leggere i tuoi dati.

**Backup e cancellazione:** per fare il backup copia la cartella dei dati. Per cancellare un utente usa
«Elimina» nella schermata utenti (rimuove profilo, nei, foto, miniature, rapporti e immagine personale). Per
cancellare tutto, elimina la cartella dei dati.

## Richieste verso internet

| Servizio | Quando | Che cosa viene inviato | Note |
|---|---|---|---|
| **Open-Meteo** (api.open-meteo.com, geocoding-api.open-meteo.com) | Pagina «Indice UV», o ricerca di una città | Coordinate arrotondate a ~1 km, oppure il nome della città cercata. Come ogni richiesta web, il servizio vede il tuo indirizzo IP | Predefinito. Uso **non commerciale**, dati CC BY 4.0 |
| **OpenWeather** | Solo se lo scegli nelle Impostazioni **e** inserisci la tua chiave | Coordinate arrotondate, la tua chiave API | Facoltativo |
| **ipwho.is** | Solo se premi «Stima dall'indirizzo internet» e confermi | Il servizio vede il tuo indirizzo IP | Facoltativo; in alternativa usa la posizione del browser o cerca la città |
| **PubMed / NCBI E-utilities** (eutils.ncbi.nlm.nih.gov) | Pagine «Letteratura» e «Genetica» | Solo i **termini di ricerca** (mai dati personali). Parametri `tool=NeoTracker` e, se la inserisci, la tua email | Massimo 3 richieste/secondo |
| **SkinSense** (servizio online di terzi su Hugging Face) | **Solo se lo attivi** nelle Impostazioni | I **pixel della foto**, ricodificata da zero (senza EXIF/GPS), ridotta a 1600 px | **La foto lascia il computer.** Non controlliamo il servizio né come tratta l'immagine. Disattivato di default |

La posizione del browser (geolocalizzazione) è richiesta solo premendo «Rileva la mia posizione» e solo
dopo il permesso del browser/Windows.

Nessuna foto, nessun dato di profilo e nessun nome di utente viene mai inviato a servizi diversi da SkinSense
(solo la foto, e solo se attivo).

## Sicurezza dei dati sul computer

Vedi [SECURITY.md](SECURITY.md): il programma ascolta solo su `127.0.0.1`, richiede una chiave di sessione
casuale, usa intestazioni di sicurezza restrittive e non carica risorse da altri siti.

## Ruoli ai sensi del GDPR (informazione generale, non consulenza legale)

- **Uso personale/domestico** (tu sul tuo PC, per te o per i tuoi familiari): il GDPR non si applica ai
  trattamenti effettuati da una persona fisica per attività a carattere esclusivamente personale o domestico
  (art. 2, par. 2, lett. c). Se conservi dati di **altre persone**, assicurati del loro consenso.
- **Gli autori di NeoTracker non trattano i tuoi dati**: non li ricevono né vi hanno accesso, quindi non sono
  titolari né responsabili del trattamento per l'uso personale.
- **Uso professionale/organizzativo** (ambulatorio, azienda, ricerca con partecipanti): chi lo adotta diventa
  **titolare del trattamento** e deve valutare base giuridica (per dati sanitari: art. 9), informativa, DPIA,
  misure di sicurezza (cifratura, controllo accessi, backup), ruolo dei servizi esterni e, per la ricerca,
  parere del comitato etico e, se applicabile, il Regolamento MDR. NeoTracker non è progettato per questo.

## Contatti

Domande sulla privacy: apri una *Discussion* o scrivi al maintainer indicato nel profilo GitHub del
repository. Vulnerabilità: vedi [SECURITY.md](SECURITY.md) (non usare le Issue pubbliche).
