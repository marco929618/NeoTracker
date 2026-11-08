
# ==========================================================================================
# 3. DATI: database SQLite, impostazioni, cartelle
# ==========================================================================================
# SQLite è un "database in un file" incluso in Python: niente da installare. Tutti i dati
# (utenti, nei, foto) stanno in CARTELLA_DATI\neotracker.db. Le foto stanno in CARTELLA_DATI\foto.

def percorso_db():
    return Path(CARTELLA_DATI) / "neotracker.db"


def adesso():
    """Data e ora attuali come testo ISO, es. '2026-11-08T10:52:31'."""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def connetti():
    """Apre una connessione al database. Ogni richiesta ne apre una propria (è più sicuro)."""
    Path(CARTELLA_DATI).mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(percorso_db()), timeout=30)
    con.row_factory = sqlite3.Row            # permette di leggere le colonne per nome
    con.execute("PRAGMA foreign_keys = ON")  # se cancelli un utente, spariscono anche i suoi nei
    return con


def inizializza_db():
    """Crea le tabelle la prima volta. Se esistono già non fa nulla."""
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
            regione    TEXT NOT NULL DEFAULT '',      -- es. 'Torace destro'
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
        # se all'avvio ci sono analisi rimaste "in corso" (app chiusa a metà), le segno interrotte
        con.execute("UPDATE foto SET stato_analisi='errore', messaggio='Analisi interrotta (app chiusa).' "
                    "WHERE stato_analisi IN ('in_corso', 'in_coda')")


def riga_a_dict(riga):
    return dict(riga) if riga is not None else None


# ---- impostazioni (chiavi API, posizione, interruttori) -----------------------------------
IMPOSTAZIONI_PREDEFINITE = {
    "avvertenze_accettate": "",   # versione dell'avviso iniziale già accettata (vuoto = non ancora accettato)
    "fonte_uv": "open-meteo",     # da dove arriva l'indice UV: "open-meteo" (predefinita, gratis, senza chiave) oppure "openweather"
    "openweather_key": "",        # la tua chiave OpenWeather (serve solo se scegli OpenWeather; resta solo in questo PC)
    "usa_skinsense": False,       # se True la foto viene inviata a SkinSense (servizio online)
    "lat": None, "lon": None,     # posizione per l'indice UV
    "localita": "",               # nome del posto (es. 'Torino, IT')
    "ncbi_email": "",             # facoltativo: la tua email per cortesia verso PubMed
    "lingua": "auto",             # lingua dell'interfaccia: "auto" (come il sistema/browser) oppure it, en, fr, de, es
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
    Lingua da usare fuori dal browser (per esempio nelle finestrelle di errore all'avvio): quella scelta
    nelle Impostazioni oppure, con "auto", quella del sistema. Se il sistema usa una lingua non
    supportata si ripiega sull'inglese.
    """
    scelta = leggi_impostazioni().get("lingua")
    if scelta in LINGUE:
        return scelta
    codice = ""
    try:
        import locale
        codice = (locale.getlocale()[0] or os.environ.get("LANG") or "")[:2].lower()
        if os.name == "nt":                       # lingua dell'interfaccia di Windows (più affidabile)
            import ctypes
            codice = {0x10: "it", 0x09: "en", 0x0C: "fr", 0x07: "de", 0x0A: "es"}.get(
                ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF, codice)
    except Exception:
        pass
    return codice if codice in LINGUE else "en"


def salva_impostazioni(nuove):
    """Aggiorna solo i campi ammessi e salva su file."""
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
            os.chmod(provvisorio, 0o600)          # il file contiene la tua chiave: leggibile solo da te (Linux/Mac)
        os.replace(provvisorio, destinazione)     # sostituzione "tutta d'un colpo": un'interruzione non lascia un file a metà
        return dati


def impostazioni_pubbliche():
    """Versione per il browser: la chiave segreta NON viene mai restituita, solo se c'è."""
    d = leggi_impostazioni()
    chiave = d.get("openweather_key") or ""
    d["ha_chiave_owm"] = bool(chiave)
    d["chiave_owm_finale"] = ("…" + chiave[-4:]) if len(chiave) >= 8 else ""
    d.pop("openweather_key", None)
    d["cartella_dati"] = str(CARTELLA_DATI)
    d["ha_pillow"] = HA_PILLOW
    d["versione"] = VERSIONE
    return d
