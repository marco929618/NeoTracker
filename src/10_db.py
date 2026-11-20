
# ==========================================================================================
# 3. DATA: SQLite database, settings, folders
# ==========================================================================================
# SQLite is a "database in a file" included in Python: nothing to install. All the data
# (users, moles, photos) is in CARTELLA_DATI\neotracker.db. The photos are in CARTELLA_DATI\foto.

def percorso_db():
    return Path(CARTELLA_DATI) / "neotracker.db"


def adesso():
    """Current date and time as ISO text, e.g. '2026-11-08T10:52:31'."""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def connetti():
    """Opens a database connection. Every request opens its own (it is safer)."""
    Path(CARTELLA_DATI).mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(percorso_db()), timeout=30)
    con.row_factory = sqlite3.Row            # lets you read the columns by name
    con.execute("PRAGMA foreign_keys = ON")  # if you delete a user, their moles disappear too
    return con


# Databases created by versions up to 1.2 stored the body regions and the suggested sites in Italian
# (e.g. 'Spalla destra'). From version 1.3 the stored text is the English one ('Shoulder, right'): at start-up
# the old names are converted with this table (the Italian names are kept here only for this purpose).
NOMI_SEDI_ITALIANI = {
    "Addome alto destro": "Upper abdomen, right",
    "Addome alto sinistro": "Upper abdomen, left",
    "Addome basso destro": "Lower abdomen, right",
    "Addome basso sinistro": "Lower abdomen, left",
    "Avambraccio destro": "Forearm, right",
    "Avambraccio sinistro": "Forearm, left",
    "Braccio destro": "Arm, right",
    "Braccio sinistro": "Arm, left",
    "Caviglia destra": "Ankle, right",
    "Caviglia sinistra": "Ankle, left",
    "Cavo popliteo destro": "Back of knee, right",
    "Cavo popliteo sinistro": "Back of knee, left",
    "Collo": "Neck",
    "Coscia destra": "Thigh, right",
    "Coscia sinistra": "Thigh, left",
    "Cuoio capelluto (testa)": "Scalp (head)",
    "Fronte e cuoio capelluto": "Forehead and scalp",
    "Gamba (stinco) destra": "Lower leg (shin), right",
    "Gamba (stinco) sinistra": "Lower leg (shin), left",
    "Ginocchio destro": "Knee, right",
    "Ginocchio sinistro": "Knee, left",
    "Gluteo destro": "Buttock, right",
    "Gluteo sinistro": "Buttock, left",
    "Gomito destro": "Elbow, right",
    "Gomito sinistro": "Elbow, left",
    "Inguine destro": "Groin, right",
    "Inguine sinistro": "Groin, left",
    "Mano destra": "Hand, right",
    "Mano sinistra": "Hand, left",
    "Nuca e collo": "Nape and neck",
    "Orecchio destro": "Ear, right",
    "Orecchio sinistro": "Ear, left",
    "Piede destro": "Foot, right",
    "Piede sinistro": "Foot, left",
    "Polpaccio destro": "Calf, right",
    "Polpaccio sinistro": "Calf, left",
    "Regione lombare destra": "Lower back, right",
    "Regione lombare sinistra": "Lower back, left",
    "Regione scapolare destra": "Shoulder blade area, right",
    "Regione scapolare sinistra": "Shoulder blade area, left",
    "Schiena (zona media) destra": "Back (middle area), right",
    "Schiena (zona media) sinistra": "Back (middle area), left",
    "Spalla destra": "Shoulder, right",
    "Spalla sinistra": "Shoulder, left",
    "Torace destro": "Chest, right",
    "Torace sinistro": "Chest, left",
    "Viso": "Face",
    "cuoio capelluto": "scalp",
    "dorso del piede": "top of the foot",
    "dorso della mano": "back of the hand",
    "labbro": "lip",
    "orecchio": "ear",
    "palmo della mano": "palm of the hand",
    "palpebra": "eyelid",
    "pianta del piede": "sole of the foot",
    "sotto l'unghia (mano)": "under the nail (hand)",
    "sotto l'unghia (piede)": "under the nail (foot)",
    "spazio tra le dita": "between the fingers or toes",
}


def inizializza_db():
    """Creates the tables the first time. If they already exist it does nothing."""
    with connetti() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS utenti (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nome      TEXT NOT NULL,
            creato    TEXT NOT NULL,
            profilo   TEXT NOT NULL DEFAULT '{}'      -- fenotipo e familiarità (testo JSON)
        );
        CREATE TABLE IF NOT EXISTS nevi (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            utente_id  INTEGER NOT NULL REFERENCES utenti(id) ON DELETE CASCADE,
            nome       TEXT NOT NULL,
            vista      TEXT NOT NULL,                 -- 'fronte' oppure 'retro'
            x          REAL NOT NULL,                 -- posizione sulla mappa, da 0 a 1
            y          REAL NOT NULL,
            regione    TEXT NOT NULL DEFAULT '',      -- e.g. 'Chest, right'
            note       TEXT NOT NULL DEFAULT '',
            creato     TEXT NOT NULL,
            archiviato INTEGER NOT NULL DEFAULT 0     -- 1 = tolto dalla mappa ma conservato
        );
        CREATE TABLE IF NOT EXISTS foto (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            nevo_id       INTEGER NOT NULL REFERENCES nevi(id) ON DELETE CASCADE,
            file          TEXT NOT NULL,              -- nome del file originale (cartella foto)
            scattata_il   TEXT NOT NULL,              -- data dello scatto (AAAA-MM-GG)
            diametro_mm   REAL,                       -- misura inserita da te (facoltativa)
            tipo          TEXT NOT NULL DEFAULT 'normale',   -- 'normale' oppure 'dermoscopica'
            note          TEXT NOT NULL DEFAULT '',
            stato_analisi TEXT NOT NULL DEFAULT 'nessuna',   -- nessuna | in_coda | in_corso | ok | errore
            rapporto      TEXT NOT NULL DEFAULT '',   -- cartella del rapporto (dentro CARTELLA_DATI)
            messaggio     TEXT NOT NULL DEFAULT '',   -- eventuale errore dell'analisi
            esito         TEXT NOT NULL DEFAULT '',   -- sintesi: attenzione | benigno | discordante | nessuno
            creato        TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_nevi_utente ON nevi(utente_id);
        CREATE INDEX IF NOT EXISTS idx_foto_nevo   ON foto(nevo_id);
        """)
        # if at start-up some analyses are left "in progress" (app closed halfway), mark them as interrupted
        con.execute("UPDATE foto SET stato_analisi='errore', messaggio=? WHERE stato_analisi IN ('in_corso', 'in_coda')",
                    (T("Analysis interrupted (app closed)."),))
        for vecchio, nuovo in NOMI_SEDI_ITALIANI.items():           # old Italian names -> English names
            con.execute("UPDATE nevi SET regione=? WHERE regione=?", (nuovo, vecchio))


def riga_a_dict(riga):
    return dict(riga) if riga is not None else None


# ---- settings (API keys, location, switches) ----------------------------------------------
IMPOSTAZIONI_PREDEFINITE = {
    "avvertenze_accettate": "",   # version of the start-up notice already accepted (empty = not accepted yet)
    "fonte_uv": "open-meteo",     # where the UV index comes from: "open-meteo" (default, free, no key) or "openweather"
    "openweather_key": "",        # your OpenWeather key (only needed if you choose OpenWeather; it stays only on this PC)
    "usa_skinsense": False,       # if True the photo is sent to SkinSense (online service)
    "lat": None, "lon": None,     # location for the UV index
    "localita": "",               # name of the place (e.g. 'Torino, IT')
    "ncbi_email": "",             # optional: your email, as a courtesy to PubMed
    "lingua": "auto",             # interface language: "auto" (same as the system/browser) or en, it, fr, de, es
}
_blocco_impostazioni = threading.Lock()


def leggi_impostazioni():
    p = Path(CARTELLA_DATI) / "impostazioni.json"
    dati = dict(IMPOSTAZIONI_PREDEFINITE)
    try:
        if p.exists():
            dati.update(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        pass
    return dati


def lingua_corrente():
    """
    Language to use outside the browser (for example in the start-up error windows): the one chosen
    in Settings or, with "auto", the one of the system. If the system uses an unsupported
    language, English is used.
    """
    scelta = leggi_impostazioni().get("lingua")
    if scelta in LINGUE:
        return scelta
    codice = ""
    try:
        import locale
        codice = (locale.getlocale()[0] or os.environ.get("LANG") or "")[:2].lower()
        if os.name == "nt":                       # Windows interface language (more reliable)
            import ctypes
            codice = {0x10: "it", 0x09: "en", 0x0C: "fr", 0x07: "de", 0x0A: "es"}.get(
                ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF, codice)
    except Exception:
        pass
    return codice if codice in LINGUE else "en"


def salva_impostazioni(nuove):
    """Updates only the allowed fields and saves to file."""
    with _blocco_impostazioni:
        dati = leggi_impostazioni()
        for k in IMPOSTAZIONI_PREDEFINITE:
            if k in nuove:
                dati[k] = nuove[k]
        Path(CARTELLA_DATI).mkdir(parents=True, exist_ok=True)
        destinazione = Path(CARTELLA_DATI) / "impostazioni.json"
        provvisorio = destinazione.with_suffix(".json.tmp")
        provvisorio.write_text(json.dumps(dati, ensure_ascii=False, indent=2), encoding="utf-8")
        if os.name != "nt":
            os.chmod(provvisorio, 0o600)          # the file contains your key: readable only by you (Linux/Mac)
        os.replace(provvisorio, destinazione)     # replace "all at once": an interruption does not leave a half-written file
        return dati


def impostazioni_pubbliche():
    """Version for the browser: the secret key is NEVER returned, only whether it is there."""
    d = leggi_impostazioni()
    chiave = d.get("openweather_key") or ""
    d["ha_chiave_owm"] = bool(chiave)
    d["chiave_owm_finale"] = ("…" + chiave[-4:]) if len(chiave) >= 8 else ""
    d.pop("openweather_key", None)
    d["cartella_dati"] = str(CARTELLA_DATI)
    d["ha_pillow"] = HA_PILLOW
    d["versione"] = VERSIONE
    return d
