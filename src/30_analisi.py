
# ==========================================================================================
# 5. PHOTOS AND ANALYSIS: saving, thumbnails, shooting date, automatic analysis in a queue
# ==========================================================================================

class ErroreRichiesta(Exception):
    """Error caused by wrong data sent by the browser (becomes a 400/404/409 response)."""
    def __init__(self, messaggio, codice=400):
        super().__init__(messaggio)
        self.codice = codice


def cartella_foto():
    return Path(CARTELLA_DATI) / "foto"


def cartella_rapporti():
    return Path(CARTELLA_DATI) / "rapporti"


def cartella_miniature():
    return Path(CARTELLA_DATI) / "miniature"


def cartella_avatar():
    return Path(CARTELLA_DATI) / "avatar"


def dentro(cartella_base, percorso):
    """True if 'percorso' really is inside 'cartella_base' (defence against paths like ..\\..)."""
    try:
        Path(percorso).resolve().relative_to(Path(cartella_base).resolve())
        return True
    except (ValueError, OSError):
        return False


# ------------------------------------------------------------------------------------------
# 5a. Checking and saving the photo
# ------------------------------------------------------------------------------------------
def riconosci_formato(dati):
    """Looks at the first bytes of the file (not the extension) and says what kind of image it is. None if not supported."""
    if dati[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if dati[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if dati[:4] == b"RIFF" and dati[8:12] == b"WEBP":
        return ".webp"
    if dati[:2] == b"BM":
        return ".bmp"
    if dati[:4] in (b"II*\x00", b"MM\x00*") and HA_PILLOW:
        return ".tif"
    return None


def data_exif(img):
    """Shooting date written by the camera in the photo (YYYY-MM-DD), or None."""
    try:
        ex = img.getexif()
        valore = None
        try:
            ifd = ex.get_ifd(0x8769)
            valore = ifd.get(36867) or ifd.get(36868)
        except Exception:
            pass
        valore = valore or ex.get(306)
        m = re.match(r"\s*(\d{4}):(\d{2}):(\d{2})", str(valore or ""))
        if m:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if date(1990, 1, 1) <= d <= date.today() + timedelta(days=1):
                return d.isoformat()
    except Exception:
        pass
    return None


def data_valida(testo):
    """Checks that the text is a YYYY-MM-DD date not in the future; returns the cleaned text."""
    try:
        d = datetime.strptime((testo or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ErroreRichiesta(T("Invalid date: use the format YYYY-MM-DD."))
    if d > date.today() + timedelta(days=1):
        raise ErroreRichiesta(T("The photo date cannot be in the future."))
    if d.year < 1990:
        raise ErroreRichiesta(T("Photo date is too old."))
    return d.isoformat()


def numero_o_vuoto(testo, minimo, massimo, nome):
    """Reads an optional decimal number (comma or point) within a range; '' means 'not given'."""
    if testo is None or str(testo).strip() == "":
        return None
    try:
        v = float(str(testo).replace(",", "."))
    except ValueError:
        raise ErroreRichiesta(T(f"{nome}: enter a number."))
    if not (minimo <= v <= massimo):
        raise ErroreRichiesta(T(f"{nome}: the value must be between {minimo} and {massimo}."))
    return round(v, 1)


def salva_foto(nevo_id, dati, data, usa_exif, tipo, diametro, note):
    """
    Saves a photo in the mole's history. The original is kept WITHOUT changes
    (it is the 'historical photo'). Returns the photo id and the date actually used.
    """
    if not dati:
        raise ErroreRichiesta(T("The file is empty."))
    if len(dati) > MAX_MB_FOTO * 1024 * 1024:
        raise ErroreRichiesta(T(f"The photo exceeds {MAX_MB_FOTO} MB."), 413)
    ext = riconosci_formato(dati)
    if ext is None:
        raise ErroreRichiesta(T("Unsupported format: JPG, PNG, WEBP or BMP are required. iPhone HEIC photos must "
                                "be converted to JPG (camera settings: 'Most Compatible')."))
    if tipo not in ("normale", "dermoscopica"):
        tipo = "normale"
    data_exif_trovata = None
    if HA_PILLOW:
        try:
            Image.MAX_IMAGE_PIXELS = MAX_PIXEL_IMMAGINE
            with Image.open(io.BytesIO(dati)) as img:
                if img.width * img.height > MAX_PIXEL_IMMAGINE:        # trap image: huge once opened
                    raise ValueError("too large")
                img.verify()
            with Image.open(io.BytesIO(dati)) as img:
                data_exif_trovata = data_exif(img)
        except Exception:
            raise ErroreRichiesta(T("The file is not a readable image, is damaged or has too many pixels "
                                    "(maximum {mp} megapixels).").format(mp=MAX_PIXEL_IMMAGINE // 1_000_000))
    data_finale = data_exif_trovata if (usa_exif and data_exif_trovata) else data_valida(data or date.today().isoformat())
    diam = numero_o_vuoto(diametro, 0.5, 100, T("Diameter (mm)"))
    note = (note or "").strip()[:1000]

    with connetti() as con:
        nevo = con.execute("SELECT id, utente_id FROM nevi WHERE id=?", (nevo_id,)).fetchone()
        if nevo is None:
            raise ErroreRichiesta(T("Mole not found."), 404)
        sotto = Path(f"u{nevo['utente_id']}") / f"n{nevo_id}"
        nome_file = f"{data_finale.replace('-', '')}_{datetime.now().strftime('%H%M%S')}_{hashlib.sha1(dati, usedforsecurity=False).hexdigest()[:6]}{ext}"
        dest = cartella_foto() / sotto / nome_file
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(dati)
        cur = con.execute(
            "INSERT INTO foto (nevo_id, file, scattata_il, diametro_mm, tipo, note, creato) VALUES (?,?,?,?,?,?,?)",
            (nevo_id, (sotto / nome_file).as_posix(), data_finale, diam, tipo, note, adesso()))
        return {"id": cur.lastrowid, "scattata_il": data_finale, "da_exif": bool(usa_exif and data_exif_trovata)}


def percorso_foto(riga_foto):
    """Full path of the original file of a photo (only if it is inside the photos folder)."""
    p = cartella_foto() / riga_foto["file"]
    return p if dentro(cartella_foto(), p) and p.exists() else None


def miniatura(foto_id, utente_id, riga_foto, lato):
    """JPEG thumbnail of the photo (correctly rotated, without metadata). Returns (bytes, MIME type)."""
    orig = percorso_foto(riga_foto)
    if orig is None:
        raise ErroreRichiesta(T("Photo file not found."), 404)
    if not HA_PILLOW:
        return orig.read_bytes(), (mimetypes.guess_type(str(orig))[0] or "application/octet-stream")
    lato = lato if lato in (120, 240, 480, 960, 1600) else 480
    cache = cartella_miniature() / f"u{utente_id}" / f"f{foto_id}_{lato}.jpg"
    if cache.exists() and cache.stat().st_mtime >= orig.stat().st_mtime:
        return cache.read_bytes(), "image/jpeg"
    Image.MAX_IMAGE_PIXELS = MAX_PIXEL_IMMAGINE
    with Image.open(orig) as img:
        try:
            img.draft("RGB", (lato * 2, lato * 2))      # for JPEGs: it already reads them small (much faster)
        except Exception:
            pass
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        img.thumbnail((lato, lato))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=88, optimize=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(buf.getvalue())
    return buf.getvalue(), "image/jpeg"


def cancella_file_foto(riga_foto, utente_id):
    """Removes the photo, its thumbnails and its report from the disk."""
    p = cartella_foto() / riga_foto["file"]
    if dentro(cartella_foto(), p):
        p.unlink(missing_ok=True)
    mini = cartella_miniature() / f"u{utente_id}"
    if mini.exists():
        for f in mini.glob(f"f{riga_foto['id']}_*.jpg"):
            f.unlink(missing_ok=True)
    if riga_foto["rapporto"]:
        r = Path(CARTELLA_DATI) / riga_foto["rapporto"]
        if dentro(cartella_rapporti(), r) and r.exists():
            shutil.rmtree(r, ignore_errors=True)


def cancella_cartelle_utente(utente_id):
    for base in (cartella_foto(), cartella_rapporti(), cartella_miniature()):
        shutil.rmtree(base / f"u{utente_id}", ignore_errors=True)
    cancella_avatar(utente_id)


# ------------------------------------------------------------------------------------------
# 5a-bis. Personal image (avatar) of the user
# ------------------------------------------------------------------------------------------
# The user can choose an image of their own (even an icon or a drawing, not necessarily their
# face). It stays on the PC: it is saved as a small square 256x256 JPEG in CARTELLA_DATI\avatar.
# It is never used for the analysis of the moles nor sent to external services.
LATO_AVATAR = 256
MAX_BYTE_AVATAR = 8 * 1024 * 1024          # the chosen image can be large; it is reduced afterwards


def percorso_avatar(utente_id):
    return cartella_avatar() / f"u{int(utente_id)}.jpg"


def versione_avatar(utente_id):
    """A number that changes every time the image changes (the browser uses it to avoid using an old copy). 0 = none."""
    try:
        return int(percorso_avatar(utente_id).stat().st_mtime_ns // 1_000_000)
    except OSError:
        return 0


def salva_avatar(utente_id, dati):
    """Checks the image, crops it to a square at the centre, reduces it and saves it as a JPEG
    WITHOUT metadata (no GPS or camera data). Without Pillow it only accepts an already small JPEG/PNG."""
    if not dati:
        raise ErroreRichiesta(T("The file is empty."))
    if len(dati) > MAX_BYTE_AVATAR:
        raise ErroreRichiesta(T("The image exceeds {mb} MB.").format(mb=MAX_BYTE_AVATAR // (1024 * 1024)), 413)
    ext = riconosci_formato(dati)
    if ext not in (".jpg", ".png", ".webp", ".bmp"):
        raise ErroreRichiesta(T("Unsupported format: JPG, PNG, WEBP or BMP are required."))
    if HA_PILLOW:
        try:
            Image.MAX_IMAGE_PIXELS = MAX_PIXEL_IMMAGINE
            with Image.open(io.BytesIO(dati)) as img:
                if img.width * img.height > MAX_PIXEL_IMMAGINE:
                    raise ValueError("too large")
                try:
                    img.draft("RGB", (LATO_AVATAR * 2, LATO_AVATAR * 2))
                except Exception:
                    pass
                img = ImageOps.exif_transpose(img)
                if img.mode in ("RGBA", "LA", "P"):                     # white background instead of transparency
                    img = img.convert("RGBA")
                    fondo = Image.new("RGB", img.size, (255, 255, 255))
                    fondo.paste(img, mask=img.split()[-1])
                    img = fondo
                else:
                    img = img.convert("RGB")
                img = ImageOps.fit(img, (LATO_AVATAR, LATO_AVATAR), method=Image.LANCZOS)   # central crop + reduction
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=88, optimize=True)         # new file: no original metadata
            dati_finali = buf.getvalue()
        except ErroreRichiesta:
            raise
        except Exception:
            raise ErroreRichiesta(T("The file is not a readable image or is too large."))
    else:
        if ext not in (".jpg", ".png") or len(dati) > 400 * 1024:
            raise ErroreRichiesta(T("Without Pillow the image must be a JPG/PNG under 400 KB (the page reduces "
                                    "it by itself: try again with the 'Choose image' function)."))
        dati_finali = dati
    dest = percorso_avatar(utente_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_bytes(dati_finali)
    os.replace(tmp, dest)                                                # "atomic" write: no half-written files
    return versione_avatar(utente_id)


def cancella_avatar(utente_id):
    try:
        percorso_avatar(utente_id).unlink(missing_ok=True)
    except OSError:
        pass


# ------------------------------------------------------------------------------------------
# 5b. Automatic analysis (uses melanoma_batch.py) - one at a time, in a queue
# ------------------------------------------------------------------------------------------
_coda_analisi = []                       # ids of the photos waiting
_blocco_coda = threading.Lock()
_thread_analisi = [None]
_processo_attuale = {"foto": None, "popen": None}
TIMEOUT_ANALISI_S = 3 * 3600             # maximum time for one photo (the models are heavy)


def analisi_attiva():
    """True if there is at least one analysis queued or running.

    It serves to NOT shut the program down while it is still working on a photo: the analysis can
    take minutes (the models are heavy) and closing the window must not throw it away.
    """
    with _blocco_coda:
        if _coda_analisi:
            return True
    t = _thread_analisi[0]
    return t is not None and t.is_alive()


def eseguibile_python():
    """Path of the Python to use to launch the analysis.

    If NeoTracker was started WITHOUT a black window (with "pythonw.exe", as the icon on the
    Desktop does), the analysis still needs "python.exe" (with pythonw programs cannot
    write text). We then launch it with CREATE_NO_WINDOW, so no window appears.
    """
    exe = Path(sys.executable)
    if os.name == "nt" and exe.name.lower() == "pythonw.exe":
        candidato = exe.with_name("python.exe")
        if candidato.exists():
            return str(candidato)
    return str(exe)


def trova_batch():
    """Looks for melanoma_batch.py next to this file or in the projects folder."""
    for c in (CARTELLA_SCRIPT / "melanoma_batch.py", Path(CARTELLA_REPO) / "melanoma_batch.py"):
        if c.exists():
            return c
    return None


def stato_installazione():
    """What is ready on the PC (shown in Settings, to see at once what is missing)."""
    repo = Path(CARTELLA_REPO)
    app1, vatsal = repo / "DeborahAdedigba_Melanoma-Detection_App", repo / "vatsal30_Melanoma-Detection"
    n_app1 = len(list(app1.glob("*.keras"))) + len(list(app1.glob("*.weights.h5"))) if app1.exists() else 0
    n_vat = len(list((vatsal / "model").glob("model_fold_*.bin"))) if vatsal.exists() else 0
    return {"batch": str(trova_batch()) if trova_batch() else "", "repo": str(repo),
            "progetti": [
                {"nome": T("Method 1 - App 1 (Deborah Adedigba)"), "presente": app1.exists(),
                 "dettaglio": T("{n} model files out of 10").format(n=n_app1)},
                {"nome": T("Method 2 - SkinSense (online service)"), "presente": True,
                 "dettaglio": T("active only if you enable it below")},
                {"nome": T("Method 4 - vatsal30"), "presente": vatsal.exists(),
                 "dettaglio": T("{n} model files out of 5").format(n=n_vat)},
            ]}


def _scrivi_stato(foto_id, **campi):
    with connetti() as con:
        imp = ", ".join(f"{k}=?" for k in campi)
        # Security check (bandit B608): the column names are written by us, the values go in as parameters.
        con.execute(f"UPDATE foto SET {imp} WHERE id=?", (*campi.values(), foto_id))   # nosec B608


def accoda_analisi(foto_id):
    """Puts the photo in the analysis queue (if it is not already there). It starts by itself in a thread."""
    with connetti() as con:
        r = con.execute("SELECT stato_analisi FROM foto WHERE id=?", (foto_id,)).fetchone()
        if r is None:
            raise ErroreRichiesta(T("Photo not found."), 404)
        if r["stato_analisi"] in ("in_coda", "in_corso"):
            return r["stato_analisi"]
        if trova_batch() is None:
            raise ErroreRichiesta(T("I cannot find melanoma_batch.py: it must be in the same folder as "
                                    f"neotracker.py (or in {CARTELLA_REPO})."), 409)
        con.execute("UPDATE foto SET stato_analisi='in_coda', messaggio='', esito='' WHERE id=?", (foto_id,))
    with _blocco_coda:
        _coda_analisi.append(foto_id)
        if _thread_analisi[0] is None or not _thread_analisi[0].is_alive():
            t = threading.Thread(target=_ciclo_analisi, name="analisi", daemon=True)
            _thread_analisi[0] = t
            t.start()
    return "in_coda"


def _ciclo_analisi():
    while True:
        with _blocco_coda:
            if not _coda_analisi:
                return
            foto_id = _coda_analisi.pop(0)
        try:
            _esegui_analisi(foto_id)
        except Exception as e:                       # any mishap: I mark an error and go on to the next one
            traceback.print_exc()
            try:
                _scrivi_stato(foto_id, stato_analisi="errore", messaggio=T(f"Unexpected error: {e}"))
            except Exception:
                pass


def _copia_per_analisi(origine, destinazione):
    """Clean copy for the models: rotated as in the original, without metadata (GPS etc.), RGB, JPEG."""
    if not HA_PILLOW:
        destinazione = destinazione.with_suffix(origine.suffix)
        shutil.copyfile(origine, destinazione)
        return destinazione
    Image.MAX_IMAGE_PIXELS = MAX_PIXEL_IMMAGINE
    with Image.open(origine) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        massimo = 4096
        if max(img.size) > massimo:
            img.thumbnail((massimo, massimo), Image.LANCZOS)
        destinazione = destinazione.with_suffix(".jpg")
        img.save(destinazione, "JPEG", quality=95)
    return destinazione


def _esegui_analisi(foto_id):
    with connetti() as con:
        r = con.execute("SELECT f.*, n.utente_id FROM foto f JOIN nevi n ON n.id=f.nevo_id WHERE f.id=?",
                        (foto_id,)).fetchone()
    if r is None:
        return                                       # photo deleted while it was queued
    origine = percorso_foto(r)
    if origine is None:
        _scrivi_stato(foto_id, stato_analisi="errore", messaggio=T("Photo file not found."))
        return
    batch = trova_batch()
    rel = f"rapporti/u{r['utente_id']}/f{foto_id}_{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    cartella = Path(CARTELLA_DATI) / rel
    cartella.mkdir(parents=True, exist_ok=True)
    _scrivi_stato(foto_id, stato_analisi="in_corso", rapporto=rel, messaggio="")

    pulita = _copia_per_analisi(origine, cartella / "foto_analizzata")
    cmd = [eseguibile_python(), "-u", str(batch), "--foto", str(pulita), "--tipo", r["tipo"],
           "--repo", str(CARTELLA_REPO), "--out-dir", str(cartella)]
    if not leggi_impostazioni().get("usa_skinsense"):
        cmd.append("--senza-skinsense")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    flag = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    with open(cartella / "log_analisi.txt", "wb") as log:
        # stdin=DEVNULL: when started without a black window there is no "keyboard" to inherit and Windows
        # would give the "invalid handle" error; this way the child process always starts.
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                             cwd=str(batch.parent), env=env, creationflags=flag)
        _processo_attuale.update(foto=foto_id, popen=p)
        try:
            p.wait(timeout=TIMEOUT_ANALISI_S)
        except subprocess.TimeoutExpired:
            p.kill()
            _processo_attuale.update(foto=None, popen=None)
            _scrivi_stato(foto_id, stato_analisi="errore",
                          messaggio=T("Analysis stopped after {ore} hours (too long).").format(ore=TIMEOUT_ANALISI_S // 3600))
            return
        finally:
            _processo_attuale.update(foto=None, popen=None)

    sint = sintesi_rapporto(rel)
    if sint is None:
        coda_log = ultime_righe(cartella / "log_analisi.txt", 6)
        _scrivi_stato(foto_id, stato_analisi="errore",
                      messaggio=T("The analysis did not produce the report. Last lines of the log: {log}").format(log=coda_log or T("(empty)")))
        return
    _scrivi_stato(foto_id, stato_analisi="ok", esito=sint["esito"], messaggio="")


def ultime_righe(percorso, n):
    try:
        testo = Path(percorso).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    righe = [x.strip() for x in testo.splitlines() if x.strip()]
    return " | ".join(righe[-n:])


def avanzamento_log(rel):
    """Last lines of the log of an analysis in progress (to show 'Method 2: starting...')."""
    if not rel:
        return []
    f = Path(CARTELLA_DATI) / rel / "log_analisi.txt"
    if not dentro(cartella_rapporti(), f) or not f.exists():
        return []
    try:
        testo = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [x.strip() for x in testo.splitlines() if x.strip()][-4:]


def verdetto_metodo(risultati):
    """Same criterion as melanoma_batch.py: 'attenzione' | 'benigno' | 'discordante' | None."""
    v = [r.get("verdetto") for r in risultati if r.get("stato") == "ok" and r.get("verdetto") in ("attenzione", "benigno")]
    if not v:
        return None
    if all(x == "attenzione" for x in v):
        return "attenzione"
    if all(x == "benigno" for x in v):
        return "benigno"
    return "discordante"


def sintesi_rapporto(rel):
    """
    Reads rapporto.json and reduces it to a summary for the interface:
    for each method: verdict, count ("4 out of 5 say ...") and rows per model.
    """
    if not rel:
        return None
    cartella = Path(CARTELLA_DATI) / rel
    if not dentro(cartella_rapporti(), cartella):
        return None
    try:
        dati = json.loads((cartella / "rapporto.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    metodi, giudizi = [], {}
    for m in dati:
        ris = m.get("risultati", [])
        ok = [x for x in ris if x.get("stato") == "ok"]
        conteggi = {}
        for x in ok:
            conteggi[x.get("etichetta")] = conteggi.get(x.get("etichetta"), 0) + 1
        frase = "; ".join(T("{n} of {tot}: {et}").format(n=n, tot=len(ok), et=et) for et, n in sorted(conteggi.items(), key=lambda kv: -kv[1]))
        verd = verdetto_metodo(ris)
        giudizi[m.get("metodo")] = verd
        metodi.append({"numero": m.get("metodo"), "titolo": m.get("titolo"), "introduzione": m.get("introduzione", ""),
                       "verdetto": verd, "frase": frase,
                       "risultati": [{k: x.get(k) for k in ("nome", "gruppo", "stato", "etichetta", "valore",
                                                              "prob_mel", "verdetto", "nota")} for x in ris]})
    con_ris = [n for n, g in giudizi.items() if g is not None]
    attenzione = [n for n, g in giudizi.items() if g == "attenzione"]
    benigni = [n for n, g in giudizi.items() if g == "benigno"]
    discordi = [n for n, g in giudizi.items() if g == "discordante"]
    if not con_ris:
        esito = "nessuno"
    elif attenzione or discordi:
        esito = "attenzione" if attenzione and not benigni and not discordi else "discordante"
    else:
        esito = "benigno"
    try:
        testo = (cartella / "rapporto.txt").read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        testo = ""
    return {"metodi": metodi, "esito": esito, "con_risultato": con_ris, "attenzione": attenzione,
            "benigni": benigni, "discordi": discordi, "testo": testo}
