# Componenti e servizi di terze parti

NeoTracker è distribuito con licenza **GNU GPL-3.0-or-later** (vedi [LICENSE](LICENSE)).
Questo file elenca ciò che il progetto usa o a cui si collega, con le relative condizioni.
*Non è consulenza legale; le licenze originali prevalgono.*

## 1. Incluso in questo repository

| Componente | Licenza / condizioni | Note |
|---|---|---|
| Codice di NeoTracker (`src/`, `web/`, `neotracker.py`, `build.py`, `tools/`, `windows/`, `tests/`) | GPL-3.0-or-later | © gli autori di NeoTracker |
| `melanoma_batch.py` | GPL-3.0-or-later | Esegue i modelli dei progetti del §2. Ricostruisce l'architettura di alcune reti (vedi nota sotto), quindi per prudenza è trattato come opera derivata di un progetto GPL-3.0 |
| Icone, mappa del corpo, icona dell'app | Opera originale degli autori, GPL-3.0-or-later | Disegnate a mano in SVG / generate da `tools/make_icon.py` |
| Screenshot in `docs/immagini/` | Generati con dati **inventati** | Nessun dato personale |

Il programma usa solo la libreria standard di Python (licenza PSF) e, facoltativamente, **Pillow**
(licenza HPND, installata dall'utente con `pip`, non inclusa).

## 2. Progetti di analisi (NON inclusi: li scarichi tu dalla fonte originale)

`tools/install_melanoma_repos.ps1` clona sul **tuo** computer i repository originali, ciascuno con la propria
licenza. **Questo repository non contiene il loro codice né i loro pesi addestrati.** Non ridistribuirli
insieme a NeoTracker senza verificare la licenza di ciascuno.

| Progetto | Licenza dichiarata | Come lo usa NeoTracker |
|---|---|---|
| DeborahAdedigba/Melanoma-Detection_App | GPL-3.0 | I modelli sono caricati da `melanoma_batch.py` nell'ambiente del progetto |
| ukalwa/melanoma-detection | GPL-3.0 | Solo app Android: non eseguita dal PC |
| VukIG/Melanoma-Detector | Apache-2.0 | Prototipo senza modello: nessuna analisi |
| vatsal30/Melanoma-Detection | **nessuna licenza dichiarata** | Si usano i file di pesi che l'utente addestra/ottiene da sé; nessun codice del progetto è incluso qui |
| soureshmondal/skinsense (servizio online) | **nessuna licenza dichiarata** | Solo chiamata HTTP al servizio pubblico, **facoltativa e disattivata di default** |

Un repository senza licenza resta coperto da diritto d'autore (tutti i diritti riservati): per questo non è
incluso né ridistribuito.

**Nota sul codice derivato.** `melanoma_batch.py` contiene la definizione di alcune reti neurali (CNN a 6 canali,
SE-ResNeXt50 con una testa lineare) riscritta per poterle eseguire senza le parti di addestramento/interfaccia
dei progetti originali. Le architetture sono pubblicate in letteratura; le definizioni sono brevi e dettate dalla
funzione. Se sei un autore di uno dei progetti e ritieni che il testo vada attribuito diversamente, apri una Issue.

## 3. Servizi online (opzionali o a richiesta)

| Servizio | Condizioni da rispettare |
|---|---|
| **Open-Meteo** (indice UV, geocodifica) | API gratuita per **uso non commerciale**, entro i limiti di richieste indicati dal servizio (oggi < 10 000 al giorno); dati sotto **CC BY 4.0**, con attribuzione (mostrata nella pagina «Indice UV»). Un uso commerciale richiede un abbonamento. https://open-meteo.com/en/terms |
| **OpenWeather** (facoltativo) | Chiave **personale** dell'utente; si applicano i termini e i limiti del suo piano |
| **ipwho.is** (facoltativo, a richiesta) | Termini del servizio; vede l'indirizzo IP dell'utente |
| **PubMed / NCBI E-utilities** | Uso pubblico gratuito; il programma dichiara `tool=NeoTracker` (e l'email, se inserita) e rispetta il limite di 3 richieste/secondo. Gli **abstract** possono essere protetti dal diritto d'autore degli editori: il programma ne mostra solo un estratto e rimanda all'articolo; non vanno ridistribuiti in blocco. https://www.ncbi.nlm.nih.gov/home/about/policies/ |

## 4. Fonti scientifiche citate

I criteri e i riferimenti mostrati nelle sezioni «Genetica» e «Indice UV» (es. Leachman et al. 2009, linee guida
NCCN, WHO Global Solar UV Index, Fajuyigbe & Young 2016) sono **citati per riferimento** con link alla fonte,
non riprodotti. Le linee guida NCCN sono proprietarie: il programma rimanda al sito ufficiale.

## 5. Dipendenze per lo sviluppo e i test

Playwright (Apache-2.0) e Chrome, solo per le prove nel browser; bandit (Apache-2.0) per l'analisi statica.
Nessuna è necessaria per usare il programma.
