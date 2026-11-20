
# ==========================================================================================
# 6. LOCAL SERVER: the browser talks to this program through "addresses" (API)
# ==========================================================================================
# You do not need to understand this part to use the app. In short: the web page (HTML/JS) asks for
# data at addresses like /api/utenti or /api/nevi/3, and below there is the function that
# answers each address.

WEB_FILES = {}       # filled in by the embedded "web pages" part by the build script


# ------------------------------------------------------------------------------------------
# 6a. Profile (phenotype and family history): which fields exist and how they are checked
# ------------------------------------------------------------------------------------------
_SC = lambda *v: ("scelta", ("",) + v)
CAMPI_PROFILO = {
    "sesso": _SC("F", "M", "altro"),
    "data_nascita": ("data", None),
    "fototipo": ("intero", (0, 6)),
    "capelli": _SC("neri", "castani", "biondi", "rossi", "grigi"),
    "occhi": _SC("scuri", "verdi", "azzurri"),
    "efelidi": _SC("nessuna", "poche", "molte"),
    "n_nevi": _SC("<25", "25-49", "50-99", "100+"),
    "nevi_atipici": _SC("no", "si", "non so"),
    "scottature": _SC("mai", "poche", "molte"),
    "lampade": _SC("mai", "alcune", "spesso"),
    "lavoro_aperto": ("bool", None),
    "immunosoppressione": ("bool", None),
    "altri_tumori_cutanei": ("bool", None),
    "melanomi_personali": ("intero", (0, 20)),
    "fam_compilata": ("bool", None),
    "fam_melanoma_1grado": ("intero", (0, 20)),
    "fam_melanoma_altri": ("intero", (0, 20)),
    "fam_pancreas": ("intero", (0, 20)),
    "fam_pancreas_1grado": ("intero", (0, 20)),
    "fam_astrocitoma": ("intero", (0, 20)),
    "fam_uveale": ("intero", (0, 20)),
    "fam_mesotelioma": ("intero", (0, 20)),
    "fam_rene": ("intero", (0, 20)),
    "pers_pancreas": ("bool", None),
    "pers_astrocitoma": ("bool", None),
    "pers_uveale": ("bool", None),
    "pers_mesotelioma": ("bool", None),
    "pers_rene": ("bool", None),
    "test_genetico": _SC("no", "si_positivo", "si_negativo", "si_non_informativo"),
    "note": ("testo", 1000),
}


def pulisci_profilo(grezzo):
    """Keeps only the expected fields and checks them one by one. Strange values become 'empty'."""
    out = {}
    if not isinstance(grezzo, dict):
        raise ErroreRichiesta(T("Invalid profile."))
    for campo, (tipo, regola) in CAMPI_PROFILO.items():
        if campo not in grezzo:
            continue
        v = grezzo[campo]
        if tipo == "scelta":
            out[campo] = v if v in regola else ""
        elif tipo == "bool":
            out[campo] = bool(v)
        elif tipo == "intero":
            out[campo] = min(max(a_intero(v, 0), regola[0]), regola[1])
        elif tipo == "data":
            v = (v or "").strip() if isinstance(v, str) else ""
            if v:
                try:
                    d = datetime.strptime(v, "%Y-%m-%d").date()
                except ValueError:
                    raise ErroreRichiesta(T("Invalid date of birth (YYYY-MM-DD)."))
                if not (date(1900, 1, 1) <= d <= date.today()):
                    raise ErroreRichiesta(T("Date of birth out of range."))
            out[campo] = v
        elif tipo == "testo":
            out[campo] = (str(v) if v is not None else "").strip()[:regola]
    # consistency: first-degree relatives are part of the total number of relatives
    if "fam_pancreas" in out or "fam_pancreas_1grado" in out:
        a, b = out.get("fam_pancreas", grezzo.get("fam_pancreas", 0)), out.get("fam_pancreas_1grado", grezzo.get("fam_pancreas_1grado", 0))
        out["fam_pancreas"] = max(a_intero(a), a_intero(b))
    return out


def profilo_completo(testo_json):
    """Saved profile + empty values for the fields never filled in (so the browser always finds everything)."""
    try:
        salvato = json.loads(testo_json or "{}")
    except ValueError:
        salvato = {}
    base = {}
    for campo, (tipo, regola) in CAMPI_PROFILO.items():
        base[campo] = False if tipo == "bool" else (0 if tipo == "intero" else "")
    base.update({k: v for k, v in salvato.items() if k in base})
    return base


def nome_valido(testo, minimo=1, massimo=60, cosa=T("The name")):
    t = re.sub(r"\s+", " ", (testo or "")).strip()
    if len(t) < minimo:
        raise ErroreRichiesta(T(f"{cosa} cannot be empty."))
    if len(t) > massimo:
        raise ErroreRichiesta(T(f"{cosa} is too long (maximum {massimo} characters)."))
    return t


# ------------------------------------------------------------------------------------------
# 6b. Functions that answer the various addresses
# ------------------------------------------------------------------------------------------
class Richiesta:
    """Everything a function needs to answer: address, parameters, body."""
    def __init__(self, gestore, metodo, percorso, query, gruppi):
        self.gestore, self.metodo, self.percorso, self.query, self.gruppi = gestore, metodo, percorso, query, gruppi
        self._corpo = None

    def q(self, nome, predefinito=""):
        return (self.query.get(nome) or [predefinito])[0]

    def corpo(self, massimo=2 * 1024 * 1024):
        if self._corpo is None:
            lung = a_intero(self.gestore.headers.get("Content-Length"), 0)
            if lung > massimo:
                raise ErroreRichiesta(T("Request too large."), 413)
            self._corpo = self.gestore.rfile.read(lung) if lung > 0 else b""
        return self._corpo

    def json(self):
        try:
            d = json.loads(self.corpo().decode("utf-8") or "{}")
        except ValueError:
            raise ErroreRichiesta(T("Invalid data (JSON)."))
        if not isinstance(d, dict):
            raise ErroreRichiesta(T("Invalid data."))
        return d


class RispostaFile:
    def __init__(self, dati, mime, extra=None):
        self.dati, self.mime, self.extra = dati, mime, extra or {}


def get_utente(con, uid):
    r = con.execute("SELECT * FROM utenti WHERE id=?", (uid,)).fetchone()
    if r is None:
        raise ErroreRichiesta(T("User not found."), 404)
    return r


def get_nevo(con, nid):
    r = con.execute("SELECT * FROM nevi WHERE id=?", (nid,)).fetchone()
    if r is None:
        raise ErroreRichiesta(T("Mole not found."), 404)
    return r


def get_foto(con, fid):
    r = con.execute("SELECT f.*, n.utente_id FROM foto f JOIN nevi n ON n.id=f.nevo_id WHERE f.id=?", (fid,)).fetchone()
    if r is None:
        raise ErroreRichiesta(T("Photo not found."), 404)
    return r


# ---- general -----------------------------------------------------------------------------
def api_ping(rq):
    # "finestra_aperta" is for whoever reopens the icon while the app is already running: if a window exists,
    # we bring it to the front instead of opening a second one.
    return {"app": "NeoTracker", "versione": VERSIONE, "finestra_aperta": STATO_FINESTRA.finestra_aperta(),
            "protetto": True}


def _id_pagina(rq):
    """Reads and checks the random number that identifies the open page (letters/digits/hyphens only)."""
    i = str(rq.json().get("id", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", i):
        raise ErroreRichiesta(T("Invalid page identifier."))
    return i


def api_battito(rq):
    """The open page says "I am still here" (see 5c: life of the window)."""
    STATO_FINESTRA.battito(_id_pagina(rq))
    return {"ok": True}


def api_addio(rq):
    """The page is closing: if it was the last one, the program shuts down in a few seconds."""
    STATO_FINESTRA.addio(_id_pagina(rq), definitivo=True)
    return {"ok": True}


def pillow_obsoleto():
    """True if Pillow is older than the minimum recommended version (10.3.0: it contains the security fixes
    on opening images). NeoTracker opens files you choose: keeping Pillow up to date matters."""
    try:
        import PIL
        parti = [int(x) for x in re.findall(r"\d+", PIL.__version__)[:2]]
        return parti < [10, 3]
    except Exception:
        return False


def api_stato(rq):
    return dict(stato_installazione(), versione=VERSIONE, ha_pillow=HA_PILLOW, cartella_dati=str(CARTELLA_DATI),
                avvertenze_versione=AVVERTENZE_VERSIONE, max_mb_foto=MAX_MB_FOTO, pillow_obsoleto=pillow_obsoleto())


def api_chiudi(rq):
    rq.gestore.server.chiusura_richiesta = True
    threading.Thread(target=rq.gestore.server.shutdown, daemon=True).start()
    return {"ok": True}


# ---- users -------------------------------------------------------------------------------
def api_utenti_lista(rq):
    with connetti() as con:
        righe = con.execute("""SELECT u.id, u.nome, u.creato, u.profilo,
                                      (SELECT COUNT(*) FROM nevi n WHERE n.utente_id=u.id AND n.archiviato=0) AS n_nevi
                               FROM utenti u ORDER BY u.nome COLLATE NOCASE""").fetchall()
    out = []
    for r in righe:
        p = profilo_completo(r["profilo"])
        out.append({"id": r["id"], "nome": r["nome"], "creato": r["creato"], "n_nevi": r["n_nevi"],
                    "eta": eta_da_nascita(p.get("data_nascita")), "avatar_v": versione_avatar(r["id"])})
    return out


def api_utente_crea(rq):
    nome = nome_valido(rq.json().get("nome"))
    with connetti() as con:
        if con.execute("SELECT 1 FROM utenti WHERE nome=? COLLATE NOCASE", (nome,)).fetchone():
            raise ErroreRichiesta(T("A user with this name already exists."), 409)
        cur = con.execute("INSERT INTO utenti (nome, creato) VALUES (?,?)", (nome, adesso()))
        return {"id": cur.lastrowid, "nome": nome}


def api_utente_dettaglio(rq):
    with connetti() as con:
        u = get_utente(con, int(rq.gruppi[0]))
        regioni = [r["regione"] for r in con.execute("SELECT regione FROM nevi WHERE utente_id=? AND archiviato=0", (u["id"],))]
    p = profilo_completo(u["profilo"])
    return {"id": u["id"], "nome": u["nome"], "profilo": p, "eta": eta_da_nascita(p.get("data_nascita")),
            "rischio": fattori_rischio(p), "genetica": valuta_genetica(p), "regioni": regioni,
            "avatar_v": versione_avatar(u["id"])}


def api_utente_rinomina(rq):
    nome = nome_valido(rq.json().get("nome"))
    with connetti() as con:
        u = get_utente(con, int(rq.gruppi[0]))
        if con.execute("SELECT 1 FROM utenti WHERE nome=? COLLATE NOCASE AND id<>?", (nome, u["id"])).fetchone():
            raise ErroreRichiesta(T("A user with this name already exists."), 409)
        con.execute("UPDATE utenti SET nome=? WHERE id=?", (nome, u["id"]))
    return {"ok": True, "nome": nome}


def api_utente_elimina(rq):
    uid = int(rq.gruppi[0])
    with connetti() as con:
        u = get_utente(con, uid)
        if rq.json().get("conferma") != u["nome"]:
            raise ErroreRichiesta(T("To delete, type the exact name of the user in the confirmation."))
        con.execute("DELETE FROM utenti WHERE id=?", (uid,))
    cancella_cartelle_utente(uid)
    return {"ok": True}


# ---- personal image of the user (avatar) -------------------------------------------------
def api_avatar_leggi(rq):
    uid = int(rq.gruppi[0])
    with connetti() as con:
        get_utente(con, uid)
    p = percorso_avatar(uid)
    if not p.exists():
        raise ErroreRichiesta(T("No image set."), 404)
    return RispostaFile(p.read_bytes(), "image/jpeg",
                        {"Cache-Control": "private, max-age=86400", "Cross-Origin-Resource-Policy": "same-origin"})


def api_avatar_salva(rq):
    uid = int(rq.gruppi[0])
    with connetti() as con:
        get_utente(con, uid)
    return {"ok": True, "avatar_v": salva_avatar(uid, rq.corpo(MAX_BYTE_AVATAR + 1024))}


def api_avatar_elimina(rq):
    uid = int(rq.gruppi[0])
    with connetti() as con:
        get_utente(con, uid)
    cancella_avatar(uid)
    return {"ok": True, "avatar_v": 0}


def api_profilo_salva(rq):
    uid = int(rq.gruppi[0])
    nuovo = pulisci_profilo(rq.json())
    with connetti() as con:
        u = get_utente(con, uid)
        p = profilo_completo(u["profilo"])
        p.update(nuovo)
        con.execute("UPDATE utenti SET profilo=? WHERE id=?", (json.dumps(p, ensure_ascii=False), uid))
    return api_utente_dettaglio(Richiesta(rq.gestore, "GET", rq.percorso, {}, (str(uid),)))


# ---- moles -------------------------------------------------------------------------------
def _nevo_a_dict(r):
    return {k: r[k] for k in r.keys()}


def api_nevi_lista(rq):
    uid = int(rq.gruppi[0])
    with connetti() as con:
        get_utente(con, uid)
        righe = con.execute("""
            SELECT n.*,
                   (SELECT COUNT(*) FROM foto f WHERE f.nevo_id=n.id) AS n_foto,
                   (SELECT f.id FROM foto f WHERE f.nevo_id=n.id ORDER BY f.scattata_il DESC, f.id DESC LIMIT 1) AS ultima_foto_id,
                   (SELECT f.scattata_il FROM foto f WHERE f.nevo_id=n.id ORDER BY f.scattata_il DESC, f.id DESC LIMIT 1) AS ultima_data,
                   (SELECT f.esito FROM foto f WHERE f.nevo_id=n.id ORDER BY f.scattata_il DESC, f.id DESC LIMIT 1) AS ultimo_esito
            FROM nevi n WHERE n.utente_id=? ORDER BY n.archiviato, n.id""", (uid,)).fetchall()
    oggi = date.today()
    out = []
    for r in righe:
        d = _nevo_a_dict(r)
        d["giorni_da_ultima"] = (oggi - date.fromisoformat(r["ultima_data"])).days if r["ultima_data"] else None
        out.append(d)
    return out


def _controlla_posizione(d, parziale=False):
    out = {}
    if "vista" in d or not parziale:
        if d.get("vista") not in ("fronte", "retro"):
            raise ErroreRichiesta(T("The view must be 'fronte' or 'retro'."))
        out["vista"] = d["vista"]
    for c in ("x", "y"):
        if c in d or not parziale:
            try:
                v = float(d.get(c))
            except (TypeError, ValueError):
                raise ErroreRichiesta(T("Invalid location."))
            if not (0.0 <= v <= 1.0):
                raise ErroreRichiesta(T("Location outside the map."))
            out[c] = round(v, 5)
    return out


def api_nevo_crea(rq):
    uid = int(rq.gruppi[0])
    d = rq.json()
    pos = _controlla_posizione(d)
    regione = (d.get("regione") or "").strip()[:80]
    note = (d.get("note") or "").strip()[:1000]
    with connetti() as con:
        get_utente(con, uid)
        n = con.execute("SELECT COUNT(*) FROM nevi WHERE utente_id=?", (uid,)).fetchone()[0]
        nome = nome_valido(d.get("nome") or f"Mole {n + 1}")
        cur = con.execute("INSERT INTO nevi (utente_id, nome, vista, x, y, regione, note, creato) VALUES (?,?,?,?,?,?,?,?)",
                          (uid, nome, pos["vista"], pos["x"], pos["y"], regione, note, adesso()))
        return {"id": cur.lastrowid}


def api_nevo_dettaglio(rq):
    nid = int(rq.gruppi[0])
    with connetti() as con:
        n = get_nevo(con, nid)
        foto = con.execute("SELECT * FROM foto WHERE nevo_id=? ORDER BY scattata_il, id", (nid,)).fetchall()
    return {"nevo": _nevo_a_dict(n), "foto": [_nevo_a_dict(f) for f in foto]}


def api_nevo_modifica(rq):
    nid = int(rq.gruppi[0])
    d = rq.json()
    campi = {}
    if any(k in d for k in ("vista", "x", "y")):
        with connetti() as con:
            attuale = get_nevo(con, nid)
        unito = {"vista": attuale["vista"], "x": attuale["x"], "y": attuale["y"]}
        unito.update({k: d[k] for k in ("vista", "x", "y") if k in d})
        campi.update(_controlla_posizione(unito))
    if "nome" in d:
        campi["nome"] = nome_valido(d["nome"])
    if "regione" in d:
        campi["regione"] = (d["regione"] or "").strip()[:80]
    if "note" in d:
        campi["note"] = (d["note"] or "").strip()[:1000]
    if "archiviato" in d:
        campi["archiviato"] = 1 if d["archiviato"] else 0
    if not campi:
        return {"ok": True}
    with connetti() as con:
        get_nevo(con, nid)
        # Security check (bandit B608): the column names are written by us, the values go in as parameters.
        con.execute(f"UPDATE nevi SET {', '.join(k + '=?' for k in campi)} WHERE id=?", (*campi.values(), nid))   # nosec B608
    return {"ok": True}


def api_nevo_elimina(rq):
    nid = int(rq.gruppi[0])
    with connetti() as con:
        n = get_nevo(con, nid)
        for f in con.execute("SELECT * FROM foto WHERE nevo_id=?", (nid,)).fetchall():
            cancella_file_foto(f, n["utente_id"])
        con.execute("DELETE FROM nevi WHERE id=?", (nid,))
    return {"ok": True}


# ---- photos ------------------------------------------------------------------------------
def api_foto_carica(rq):
    nid = int(rq.gruppi[0])
    dati = rq.corpo(MAX_MB_FOTO * 1024 * 1024 + 1024)
    ris = salva_foto(nid, dati, rq.q("data"), rq.q("exif") == "1", rq.q("tipo", "normale"),
                     rq.q("diametro"), rq.q("note"))
    if rq.q("analizza") == "1":
        try:
            accoda_analisi(ris["id"])
            ris["analisi"] = "in_coda"
        except ErroreRichiesta as e:
            ris["analisi_errore"] = str(e)
    return ris


def api_foto_modifica(rq):
    fid = int(rq.gruppi[0])
    d = rq.json()
    campi = {}
    if "scattata_il" in d:
        campi["scattata_il"] = data_valida(d["scattata_il"])
    if "diametro_mm" in d:
        campi["diametro_mm"] = numero_o_vuoto(d["diametro_mm"], 0.5, 100, T("Diameter (mm)"))
    if "tipo" in d and d["tipo"] in ("normale", "dermoscopica"):
        campi["tipo"] = d["tipo"]
    if "note" in d:
        campi["note"] = (d["note"] or "").strip()[:1000]
    with connetti() as con:
        get_foto(con, fid)
        if campi:
            # Security check (bandit B608): the column names are written by us, the values go in as
            # parameters.
            con.execute(f"UPDATE foto SET {', '.join(k + '=?' for k in campi)} WHERE id=?", (*campi.values(), fid))   # nosec B608
    return {"ok": True}


def api_foto_elimina(rq):
    fid = int(rq.gruppi[0])
    with connetti() as con:
        f = get_foto(con, fid)
        if f["stato_analisi"] in ("in_corso", "in_coda"):
            raise ErroreRichiesta(T("This photo is being analysed: wait for it to finish."), 409)
        cancella_file_foto(f, f["utente_id"])
        con.execute("DELETE FROM foto WHERE id=?", (fid,))
    return {"ok": True}


def api_foto_file(rq):
    fid = int(rq.gruppi[0])
    with connetti() as con:
        f = get_foto(con, fid)
    extra = {"Cache-Control": "private, max-age=3600", "Cross-Origin-Resource-Policy": "same-origin"}
    if rq.gruppi[1] == "mini":
        dati, mime = miniatura(fid, f["utente_id"], f, a_intero(rq.q("l"), 480))
    else:
        p = percorso_foto(f)
        if p is None:
            raise ErroreRichiesta(T("Photo file not found."), 404)
        if p.suffix.lower() in (".tif", ".tiff"):                       # browsers do not show TIFFs
            dati, mime = miniatura(fid, f["utente_id"], f, 1600)
        else:
            dati, mime = p.read_bytes(), (mimetypes.guess_type(str(p))[0] or "application/octet-stream")
        extra["Content-Disposition"] = f'inline; filename="{p.name}"'
    return RispostaFile(dati, mime, extra)


def api_analisi_avvia(rq):
    fid = int(rq.gruppi[0])
    with connetti() as con:
        get_foto(con, fid)
    return {"stato": accoda_analisi(fid)}


def api_analisi_stato(rq):
    fid = int(rq.gruppi[0])
    with connetti() as con:
        f = get_foto(con, fid)
    out = {"stato": f["stato_analisi"], "messaggio": f["messaggio"], "esito": f["esito"],
           "skinsense_attivo": bool(leggi_impostazioni().get("usa_skinsense"))}
    if f["stato_analisi"] in ("in_corso", "in_coda"):
        out["avanzamento"] = avanzamento_log(f["rapporto"])
        out["posizione_coda"] = (_coda_analisi.index(fid) + 1) if fid in _coda_analisi else 0
    if f["stato_analisi"] == "ok":
        out["sintesi"] = sintesi_rapporto(f["rapporto"])
    return out


# ---- UV index, location, settings ----------------------------------------------------------
def _coordinate(rq):
    imp = leggi_impostazioni()
    try:
        lat = float(rq.q("lat") or imp.get("lat"))
        lon = float(rq.q("lon") or imp.get("lon"))
    except (TypeError, ValueError):
        raise ErroreRichiesta(T("Location not set: choose a city or use 'Detect my location'."))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ErroreRichiesta(T("Invalid coordinates."))
    return lat, lon


def api_uv(rq):
    lat, lon = _coordinate(rq)
    return indice_uv(lat, lon, rq.q("fototipo"), rq.q("localita") or leggi_impostazioni().get("localita", ""))


def api_localita(rq):
    return cerca_localita(rq.q("q"))


def api_posizione_ip(rq):
    return posizione_da_ip()


def api_impostazioni_leggi(rq):
    return impostazioni_pubbliche()


def api_impostazioni_salva(rq):
    d = rq.json()
    nuove = {}
    if "openweather_key" in d and d["openweather_key"] is not None:
        k = str(d["openweather_key"]).strip()
        if k and not re.fullmatch(r"[A-Za-z0-9]{8,64}", k):
            raise ErroreRichiesta(T("The OpenWeather key contains invalid characters (it is usually 32 "
                                    "letters/digits)."))
        nuove["openweather_key"] = k
    if "fonte_uv" in d:
        if d["fonte_uv"] not in ("open-meteo", "openweather"):
            raise ErroreRichiesta(T("Invalid UV index source."))
        nuove["fonte_uv"] = d["fonte_uv"]
    if "usa_skinsense" in d:
        nuove["usa_skinsense"] = bool(d["usa_skinsense"])
    if "avvertenze_accettate" in d:
        if d["avvertenze_accettate"] not in ("", AVVERTENZE_VERSIONE):
            raise ErroreRichiesta(T("Invalid notice version."))
        nuove["avvertenze_accettate"] = d["avvertenze_accettate"]
    for c in ("lat", "lon"):
        if c in d:
            try:
                nuove[c] = None if d[c] in (None, "") else round(float(d[c]), 2)       # ~1 km: enough for the UV index, and less is sent
            except (TypeError, ValueError):
                raise ErroreRichiesta(T("Invalid coordinates."))
    if "localita" in d:
        nuove["localita"] = str(d["localita"] or "").strip()[:120]
    if "lingua" in d:
        if d["lingua"] != "auto" and d["lingua"] not in LINGUE:
            raise ErroreRichiesta(T("Language not supported."))
        nuove["lingua"] = d["lingua"]
    if "ncbi_email" in d:
        e = str(d["ncbi_email"] or "").strip()[:120]
        if e and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e):
            raise ErroreRichiesta(T("Invalid email address."))
        nuove["ncbi_email"] = e
    salva_impostazioni(nuove)
    _cache_uv.clear()
    return impostazioni_pubbliche()


def api_prova_owm(rq):
    imp = leggi_impostazioni()
    chiave = (imp.get("openweather_key") or "").strip()
    if not chiave:
        raise ErroreRichiesta(T("Save an OpenWeather key first."))
    lat, lon = imp.get("lat"), imp.get("lon")
    if lat is None or lon is None:
        lat, lon = 45.07, 7.69                       # failing anything else I try Turin
    try:
        d = _uv_openweather(float(lat), float(lon), chiave)
    except ErroreServizio as e:
        return {"ok": False, "messaggio": str(e)}
    return {"ok": True, "messaggio": T("It works: OpenWeather answers (current UV index: {uvi}).").format(uvi=d["uvi_ora"])}


# ---- literature and genetics ---------------------------------------------------------------
def _sezioni_per_utente(uid):
    """Complete list of the literature sections, with stable identifiers."""
    out = {}
    for tema, info in TEMI_LETTERATURA.items():
        for i, (titolo, termine, ordina) in enumerate(info["sezioni"]):
            out[f"{tema}:{i}"] = {"tema": tema, "titolo": titolo, "termine": termine, "ordina": ordina}
    if uid:
        with connetti() as con:
            u = get_utente(con, uid)
            regioni = [r["regione"] for r in con.execute("SELECT regione FROM nevi WHERE utente_id=? AND archiviato=0", (uid,))]
        for i, (titolo, termine, ordina) in enumerate(temi_personalizzati(profilo_completo(u["profilo"]), regioni)):
            out[f"personale:{i}"] = {"tema": "personale", "titolo": titolo, "termine": termine, "ordina": ordina}
    return out


def api_lett_temi(rq):
    uid = a_intero(rq.q("utente"), 0)
    sezioni = _sezioni_per_utente(uid)
    temi = []
    ordine = list(TEMI_LETTERATURA.keys()) + ["personale"]
    titoli = {t: i["titolo"] for t, i in TEMI_LETTERATURA.items()}
    titoli["personale"] = T("Picked for you (based on profile and mole locations)")
    for t in ordine:
        elenco = [{"id": k, "titolo": v["titolo"]} for k, v in sezioni.items() if v["tema"] == t]
        if elenco:
            temi.append({"tema": t, "titolo": titoli[t], "sezioni": elenco})
    return temi


def api_lett_sezione(rq):
    sezioni = _sezioni_per_utente(a_intero(rq.q("utente"), 0))
    s = sezioni.get(rq.q("id"))
    if s is None:
        raise ErroreRichiesta(T("Unknown section."), 404)
    dati = pubmed_cerca(s["termine"], 5, s["ordina"], rq.q("forza") == "1")
    return dict(dati, titolo=s["titolo"], id=rq.q("id"))


def api_lett_cerca(rq):
    q = re.sub(r"[^\w\s\-\*\"'\.]", " ", rq.q("q"), flags=re.UNICODE).strip()[:200]
    if len(q) < 3:
        raise ErroreRichiesta(T("Type at least 3 characters."))
    dati = pubmed_cerca(f"({q}) AND melanoma[tiab]", 8, "relevance", rq.q("forza") == "1")
    return dict(dati, titolo=f"Results for: {q}")


def api_genetica_geni(rq):
    return {"geni": [{k: g[k] for k in ("gene", "rischio", "ruolo")} for g in GENI_MELANOMA], "fonti": FONTI_GENETICA}


def api_genetica_gene(rq):
    g = next((x for x in GENI_MELANOMA if x["gene"] == rq.q("nome")), None)
    if g is None:
        raise ErroreRichiesta(T("Gene not in the list."), 404)
    dati = pubmed_cerca(g["termine"], 3, "relevance", rq.q("forza") == "1")
    return dict(dati, gene=g["gene"])


# ------------------------------------------------------------------------------------------
# 6c. Table of addresses (method, shape of the address, function)
# ------------------------------------------------------------------------------------------
ROTTE = [
    ("GET",    r"/api/ping", api_ping),
    ("GET",    r"/api/stato", api_stato),
    ("POST",   r"/api/chiudi", api_chiudi),
    ("POST",   r"/api/battito", api_battito),
    ("POST",   r"/api/addio", api_addio),
    ("GET",    r"/api/utenti", api_utenti_lista),
    ("POST",   r"/api/utenti", api_utente_crea),
    ("GET",    r"/api/utenti/(\d+)", api_utente_dettaglio),
    ("PATCH",  r"/api/utenti/(\d+)", api_utente_rinomina),
    ("DELETE", r"/api/utenti/(\d+)", api_utente_elimina),
    ("PUT",    r"/api/utenti/(\d+)/profilo", api_profilo_salva),
    ("GET",    r"/api/utenti/(\d+)/avatar", api_avatar_leggi),
    ("POST",   r"/api/utenti/(\d+)/avatar", api_avatar_salva),
    ("DELETE", r"/api/utenti/(\d+)/avatar", api_avatar_elimina),
    ("GET",    r"/api/utenti/(\d+)/nevi", api_nevi_lista),
    ("POST",   r"/api/utenti/(\d+)/nevi", api_nevo_crea),
    ("GET",    r"/api/nevi/(\d+)", api_nevo_dettaglio),
    ("PATCH",  r"/api/nevi/(\d+)", api_nevo_modifica),
    ("DELETE", r"/api/nevi/(\d+)", api_nevo_elimina),
    ("POST",   r"/api/nevi/(\d+)/foto", api_foto_carica),
    ("PATCH",  r"/api/foto/(\d+)", api_foto_modifica),
    ("DELETE", r"/api/foto/(\d+)", api_foto_elimina),
    ("GET",    r"/foto/(\d+)/(mini|originale)", api_foto_file),
    ("POST",   r"/api/foto/(\d+)/analizza", api_analisi_avvia),
    ("GET",    r"/api/foto/(\d+)/analisi", api_analisi_stato),
    ("GET",    r"/api/uv", api_uv),
    ("GET",    r"/api/localita", api_localita),
    ("GET",    r"/api/posizione-ip", api_posizione_ip),
    ("GET",    r"/api/impostazioni", api_impostazioni_leggi),
    ("PUT",    r"/api/impostazioni", api_impostazioni_salva),
    ("POST",   r"/api/impostazioni/prova-owm", api_prova_owm),
    ("GET",    r"/api/letteratura/temi", api_lett_temi),
    ("GET",    r"/api/letteratura/sezione", api_lett_sezione),
    ("GET",    r"/api/letteratura/cerca", api_lett_cerca),
    ("GET",    r"/api/genetica/geni", api_genetica_geni),
    ("GET",    r"/api/genetica/gene", api_genetica_gene),
]
ROTTE = [(m, re.compile(p + r"\Z"), f) for m, p, f in ROTTE]

CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
       "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
# For images (photos, avatars): even if by some absurdity they contained code, they could not run it.
CSP_FILE = "default-src 'none'; sandbox"

# ------------------------------------------------------------------------------------------
# 6c-bis. Who can talk to the program: the "session key"
# ------------------------------------------------------------------------------------------
# The server listens only on 127.0.0.1, but other programs could be running on your PC, or a
# web page open in your browser could try to "knock" on localhost. For this reason, every time
# NeoTracker starts it invents a random key, long and impossible to guess. The app window
# receives it only once, when it opens (address ...?avvio=KEY), and keeps it in a reserved
# "cookie" (HttpOnly: not even the JavaScript of the page can read it; SameSite=Strict:
# external sites cannot use it). Without the key every request is refused.
# The key changes at every start and is written (with restricted permissions) in the data folder,
# only so that a second clicked icon can open a window on the program that is already running.
NOME_COOKIE = "nt_sessione"
TOKEN_SESSIONE = secrets.token_urlsafe(32)
PERCORSI_LIBERI = ("/api/ping",)           # the only address without a key: it serves to tell whether NeoTracker is already running
MAX_PRESENZE = 16                          # simultaneous "open window" connections (one person uses 1 or 2)
_presenze_aperte = [0]
_blocco_presenze = threading.Lock()


def percorso_token():
    return Path(CARTELLA_DATI) / "sessione.token"


def scrivi_token_su_file():
    """Saves the key in a file readable only by you (on Windows it inherits the permissions of your user folder)."""
    f = percorso_token()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(TOKEN_SESSIONE, encoding="ascii")
    if os.name != "nt":
        os.chmod(tmp, 0o600)
    os.replace(tmp, f)


def leggi_token_da_file():
    """Key of the NeoTracker that is already running (a second clicked icon reads it). Empty string if there is none."""
    try:
        t = percorso_token().read_text(encoding="ascii").strip()
    except (OSError, ValueError):
        return ""
    return t if re.fullmatch(r"[A-Za-z0-9_-]{20,100}", t) else ""


def cancella_token_file():
    try:
        percorso_token().unlink(missing_ok=True)
    except OSError:
        pass


def chiave_uguale(a, b):
    """Constant-time comparison (it does not reveal, from the response times, how many letters were right)."""
    return hmac.compare_digest(str(a).encode("utf-8", "replace"), str(b).encode("utf-8", "replace"))


_ACCESSO_NEGATO_TESTI = (
    ("en", "Access denied", "This page only works from the NeoTracker window. Close this tab and open the app "
                            "from the <b>NeoTracker</b> icon on your Desktop."),
    ("it", "Accesso non autorizzato", "Questa pagina funziona solo dalla finestra di NeoTracker. Chiudi questa scheda e apri l'app "
                                      "dall'icona <b>NeoTracker</b> sul Desktop."),
    ("fr", "Accès non autorisé", "Cette page ne fonctionne que depuis la fenêtre de NeoTracker. Fermez cet onglet et ouvrez "
                                 "l'application avec l'icône <b>NeoTracker</b> du Bureau."),
    ("de", "Zugriff nicht erlaubt", "Diese Seite funktioniert nur im NeoTracker-Fenster. Schließen Sie diesen Tab und starten Sie "
                                    "die App über das <b>NeoTracker</b>-Symbol auf dem Desktop."),
    ("es", "Acceso no autorizado", "Esta página solo funciona desde la ventana de NeoTracker. Cierra esta pestaña y abre la "
                                   "aplicación desde el icono <b>NeoTracker</b> del Escritorio."),
)
PAGINA_ACCESSO_NEGATO = (
    "<!doctype html><html lang='en'><meta charset='utf-8'><title>" + " · ".join(t for _, t, _ in _ACCESSO_NEGATO_TESTI) + "</title>"
    "<body style='font-family:Segoe UI,Arial,sans-serif;max-width:34em;margin:4em auto;padding:0 1em;color:#222'>"
    + "".join(f"<section lang='{lg}'><h1>{tit}</h1><p>{txt}</p></section>" for lg, tit, txt in _ACCESSO_NEGATO_TESTI)
    + "</body></html>").encode("utf-8")

# Security headers added to EVERY response.
INTESTAZIONI_SICUREZZA = {
    "X-Content-Type-Options": "nosniff",                  # the browser must not "guess" the file type
    "Cache-Control": "no-store",                          # no copies of personal data in the browser cache
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",                            # the page cannot be embedded in other pages
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), payment=(), usb=(), geolocation=(self)",
}


class Gestore(BaseHTTPRequestHandler):
    server_version = "NeoTracker"
    sys_version = ""                  # do not say which Python version is underneath
    timeout = 60                      # a connection that stays silent for a minute is closed (defence against "hanging" connections)

    def log_message(self, formato, *args):            # no noise in the black window
        pass

    # ---- common security checks ----
    def _host_ok(self):
        ammessi = {f"127.0.0.1:{PORTA}", f"localhost:{PORTA}"}
        return self.headers.get("Host", "") in ammessi

    def _origine_ok(self):
        o = self.headers.get("Origin")
        return o is None or o in (f"http://127.0.0.1:{PORTA}", f"http://localhost:{PORTA}")

    def _cookie_ok(self):
        """True if the request carries the right session key in the cookie."""
        for riga in self.headers.get_all("Cookie") or []:
            for parte in riga.split(";"):
                nome, _, valore = parte.strip().partition("=")
                if nome == NOME_COOKIE and chiave_uguale(valore, TOKEN_SESSIONE):
                    return True
        return False

    def _invia(self, codice, dati, mime, extra=None):
        intestazioni = dict(INTESTAZIONI_SICUREZZA)
        intestazioni.update(extra or {})                 # whoever answers can change a value (e.g. photo cache)
        self.send_response(codice)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(dati)))
        for k, v in intestazioni.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(dati)

    def _reindirizza(self, dove, cookie=None):
        self.send_response(302)
        self.send_header("Location", dove)
        self.send_header("Content-Length", "0")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        for k, v in INTESTAZIONI_SICUREZZA.items():
            self.send_header(k, v)
        self.end_headers()

    def _json(self, codice, obj):
        self._invia(codice, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _errore(self, codice, messaggio):
        self._json(codice, {"errore": messaggio})

    # ---- presence of the window: a connection that stays open as long as the page is open ----
    def _presenza(self, query):
        """The page opens this connection as soon as it loads and keeps it open. While it is open the
        window exists; as soon as the page closes (even if the browser is "killed" or freezes)
        Windows closes the connection and the program notices at once. It is the most
        reliable "window closed" signal; the page's heartbeats and the "goodbye" remain as reinforcement."""
        id_pagina = (query.get("id") or [""])[0]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", id_pagina):
            return self._errore(400, T("Invalid page identifier."))
        with _blocco_presenze:                                      # a cap on open connections: no "floods"
            if _presenze_aperte[0] >= MAX_PRESENZE:
                return self._errore(429, T("Too many open connections."))
            _presenze_aperte[0] += 1
        try:
            self._presenza_aperta(id_pagina)
        finally:
            with _blocco_presenze:
                _presenze_aperte[0] -= 1

    def _presenza_aperta(self, id_pagina):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Connection", "close")
        for k, v in INTESTAZIONI_SICUREZZA.items():
            self.send_header(k, v)
        self.end_headers()
        fine = getattr(self.server, "fine_sorveglianza", None)       # turns on when the program is closing
        try:
            self.wfile.write(b"retry: 1000\n\n")                    # if the connection drops, the page retries after 1 second
            self.wfile.flush()
            giri = 0
            while fine is None or not fine.is_set():
                STATO_FINESTRA.battito(id_pagina)                    # "this page is still here"
                # Wait up to 1 second. If the connection becomes "readable" it means that the other side (the
                # browser) has closed it: the page is gone. A live page never writes anything.
                chiusa, _, _ = select.select([self.connection], [], [], 1.0)
                if chiusa:
                    break
                giri += 1
                if giri % 5 == 0:                                    # every 5 seconds an empty signal, to notice write errors
                    self.wfile.write(b": ok\n\n")
                    self.wfile.flush()
        except (OSError, ValueError):
            pass                                                     # connection dropped: it is exactly what we are looking for
        finally:
            STATO_FINESTRA.addio(id_pagina)                          # the page is gone (if it was the last one, the countdown starts)
            self.close_connection = True

    # ---- dispatching ----
    def _gestisci(self):
        try:
            if not self._host_ok():
                return self._errore(403, T("Address not allowed."))
            if not self._origine_ok():
                return self._errore(403, T("Origin not allowed."))
            if len(self.path) > 2000:
                return self._errore(414, T("Address too long."))
            url = urllib.parse.urlsplit(self.path)
            percorso, query = url.path, urllib.parse.parse_qs(url.query, keep_blank_values=True)
            if self.command in ("POST", "PUT", "PATCH", "DELETE") and self.headers.get("X-NeoTracker") != "1":
                return self._errore(403, T("Unauthorised request."))

            # ---- session key (see 6c-bis) ----
            if percorso not in PERCORSI_LIBERI:
                avvio = (query.get("avvio") or [""])[0]
                if self.command == "GET" and percorso == "/" and avvio:
                    # the window presents itself with the key: I remember it in a reserved cookie and clean up
                    # the address
                    if not chiave_uguale(avvio, TOKEN_SESSIONE):
                        return self._invia(403, PAGINA_ACCESSO_NEGATO, "text/html; charset=utf-8",
                                           {"Content-Security-Policy": CSP})
                    cookie = f"{NOME_COOKIE}={TOKEN_SESSIONE}; Path=/; HttpOnly; SameSite=Strict"
                    return self._reindirizza("/", cookie)
                if not self._cookie_ok():
                    if self.command == "GET" and not percorso.startswith(("/api/", "/foto/")):
                        return self._invia(403, PAGINA_ACCESSO_NEGATO, "text/html; charset=utf-8",
                                           {"Content-Security-Policy": CSP})
                    return self._errore(403, T("Unauthorised access."))

            if self.command == "GET" and percorso == "/api/presenza":
                return self._presenza(query)

            if self.command == "GET" and not percorso.startswith(("/api/", "/foto/")):
                voce = WEB_FILES.get("/index.html" if percorso == "/" else percorso)
                if voce is None:
                    return self._errore(404, T("Page not found."))
                mime, dati = voce
                if mime.startswith("text/html"):
                    scelta = leggi_impostazioni().get("lingua")
                    dati = dati.replace(b"@@LINGUA@@", (scelta if scelta in LINGUE else "auto").encode("ascii"))
                extra = {"Content-Security-Policy": CSP} if mime.startswith("text/html") else {}
                return self._invia(200, dati, mime, extra)

            trovato_percorso = False
            for metodo, regex, funzione in ROTTE:
                m = regex.match(percorso)
                if not m:
                    continue
                trovato_percorso = True
                if metodo != self.command:
                    continue
                rq = Richiesta(self, self.command, percorso, query, m.groups())
                ris = funzione(rq)
                if isinstance(ris, RispostaFile):
                    return self._invia(200, ris.dati, ris.mime, dict(ris.extra, **{"Content-Security-Policy": CSP_FILE}))
                return self._json(200, ris)
            if trovato_percorso:
                return self._errore(405, T("Operation not allowed on this address."))
            return self._errore(404, T("Unknown address."))
        except ErroreRichiesta as e:
            self._errore(e.codice, str(e))
        except ErroreServizio as e:
            self._errore(502, str(e))
        except (BrokenPipeError, ConnectionResetError):
            pass                                       # the browser closed the connection: no problem
        except Exception as e:                         # our error: I show it in the console and report it to the browser
            traceback.print_exc()                      # the details stay in the log (neotracker.log), not in the response
            try:
                self._errore(500, T("Internal error. Details are in the neotracker.log file in the data folder."))
            except Exception:
                pass

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _gestisci

    def do_HEAD(self):
        self._errore(405, T("Not allowed."))

    def do_OPTIONS(self):
        self._errore(403, T("Not allowed."))
