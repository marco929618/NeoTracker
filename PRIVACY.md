# Privacy and data protection

**In short:** NeoTracker runs **only on your computer**. It has no accounts, no server operated by the developers, and
it collects no statistics or telemetry. Your data stays in your folder. Only the requests listed below leave your
computer, and they happen **only if you use the matching feature**.

## Data stored on your computer

In the data folder (default: `%USERPROFILE%\melanoma-repos\NeoTracker_dati`, can be changed) you will find:

| What | Where | Notes |
|---|---|---|
| Users, profile (sex, age, phototype, family history, personal history, notes), moles and positions | `neotracker.db` (SQLite) | This is **health data**: a special category under Art. 9 GDPR |
| Mole photos (**unmodified** originals, thumbnails) | `foto/`, `miniature/` | The originals may contain metadata (GPS, phone model) |
| Personal picture (optional) | `avatar/` | Cropped to 256×256, **without metadata** |
| Analysis reports | `rapporti/` | |
| Settings, any OpenWeather key, approximate location (≈ 1 km) | `impostazioni.json` | File readable only by its owner (on Linux/Mac) |
| Temporary session key | `sessione.token` | Deleted when the program is closed |
| Technical log | `neotracker.log` | Only program messages, no health data |

**Not encrypted:** the program does not encrypt the files. To protect them use disk encryption (BitLocker on
Windows) and a user account with a password. Anyone who can open your folder can read your data.

**Backup and deletion:** to back up, copy the data folder. To delete a user, use "Delete" on the users screen (it
removes profile, moles, photos, thumbnails, reports and personal picture). To delete everything, remove the data folder.

## Requests to the internet

| Service | When | What is sent | Notes |
|---|---|---|---|
| **Open-Meteo** (api.open-meteo.com, geocoding-api.open-meteo.com) | "UV index" page, or when searching for a city | Coordinates rounded to ~1 km, or the name of the city searched. Like any web request, the service sees your IP address | Default. **Non-commercial** use, data CC BY 4.0 |
| **OpenWeather** | Only if you choose it in Settings **and** enter your own key | Rounded coordinates, your API key | Optional |
| **ipwho.is** | Only if you press "Estimate from the internet address" and confirm | The service sees your IP address | Optional; alternatively use the browser location or search for the city |
| **PubMed / NCBI E-utilities** (eutils.ncbi.nlm.nih.gov) | "Literature" and "Genetics" pages | Only the **search terms** (never personal data). Parameters `tool=NeoTracker` and, if you enter it, your email | At most 3 requests/second |
| **SkinSense** (third-party online service on Hugging Face) | **Only if you turn it on** in Settings | The **photo pixels**, re-encoded from scratch (no EXIF/GPS), reduced to 1600 px | **The photo leaves your computer.** We do not control the service or how it handles the image. Off by default |

The browser location (geolocation) is requested only when you press "Detect my location" and only after the
browser/Windows permission.

No photo, no profile data and no user name is ever sent to services other than SkinSense (only the photo, and only
when it is on).

## Security of the data on the computer

See [SECURITY.md](SECURITY.md): the program listens only on `127.0.0.1`, requires a random session key, uses
restrictive security headers and does not load resources from other sites.

## Roles under the GDPR (general information, not legal advice)

- **Personal/household use** (you on your own PC, for yourself or your family): the GDPR does not apply to processing
  carried out by a natural person in the course of a purely personal or household activity (Art. 2(2)(c)). If you
  store data about **other people**, make sure you have their consent.
- **The authors of NeoTracker do not process your data**: they neither receive it nor have access to it, so they are
  neither controller nor processor for personal use.
- **Professional/organisational use** (clinic, company, research with participants): whoever adopts it becomes the
  **controller** and must assess the legal basis (for health data: Art. 9), the privacy notice, the DPIA, security
  measures (encryption, access control, backups), the role of the external services and, for research, the ethics
  committee opinion and, where applicable, the MDR. NeoTracker is not designed for this.

## Contact

Privacy questions: open a *Discussion* or write to the maintainer listed on the GitHub profile of the repository.
Vulnerabilities: see [SECURITY.md](SECURITY.md) (do not use public Issues).
