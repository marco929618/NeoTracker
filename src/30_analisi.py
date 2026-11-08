
# ==========================================================================================
# 5. FOTO E ANALISI: salvataggio, miniature, data di scatto, analisi automatica in coda
# ==========================================================================================

class ErroreRichiesta(Exception):
    """Errore dovuto a dati sbagliati inviati dal browser (diventa una risposta 400/404/409)."""
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
    """True se 'percorso' sta davvero dentro 'cartella_base' (difesa contro percorsi tipo ..\\..)."""
    try:
        Path(percorso).resolve().relative_to(Path(cartella_base).resolve())
        return True
    except (ValueError, OSError):
        return False


# ------------------------------------------------------------------------------------------
# 5a. Controllo e salvataggio della foto
# ------------------------------------------------------------------------------------------
def riconosci_formato(dati):
    """Guarda i primi byte del file (non l'estensione) e dice che immagine è. None se non è supportata."""
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
    """Data di scatto scritta dalla fotocamera nella foto (AAAA-MM-GG), oppure None."""
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
    """Controlla che il testo sia una data AAAA-MM-GG non nel futuro; restituisce il testo pulito."""
    try:
        d = datetime.strptime((testo or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ErroreRichiesta("Data non valida: usa il formato AAAA-MM-GG.")
    if d > date.today() + timedelta(days=1):
        raise ErroreRichiesta("La data della foto non può essere nel futuro.")
    if d.year < 1990:
        raise ErroreRichiesta("Data della foto troppo vecchia.")
    return d.isoformat()


def numero_o_vuoto(testo, minimo, massimo, nome):
    """Legge un numero decimale opzionale (virgola o punto) entro un intervallo; '' vale 'non indicato'."""
    if testo is None or str(testo).strip() == "":
        return None
    try:
        v = float(str(testo).replace(",", "."))
    except ValueError:
        raise ErroreRichiesta(f"{nome}: inserisci un numero.")
    if not (minimo <= v <= massimo):
        raise ErroreRichiesta(f"{nome}: il valore deve essere tra {minimo:g} e {massimo:g}.")
    return round(v, 1)


def salva_foto(nevo_id, dati, data, usa_exif, tipo, diametro, note):
    """
    Salva una foto nello storico del neo. L'originale viene conservato SENZA modifiche
    (è la 'foto storica'). Restituisce l'id della foto e la data effettivamente usata.
    """
    if not dati:
        raise ErroreRichiesta("Il file è vuoto.")
    if len(dati) > MAX_MB_FOTO * 1024 * 1024:
        raise ErroreRichiesta(f"La foto supera {MAX_MB_FOTO} MB.", 413)
    ext = riconosci_formato(dati)
    if ext is None:
        raise ErroreRichiesta("Formato non supportato: servono JPG, PNG, WEBP o BMP. "
                              "Le foto HEIC degli iPhone vanno convertite in JPG "
                              "(impostazioni fotocamera: 'Più compatibile').")
    if tipo not in ("normale", "dermoscopica"):
        tipo = "normale"
    data_exif_trovata = None
    if HA_PILLOW:
        try:
            Image.MAX_IMAGE_PIXELS = MAX_PIXEL_IMMAGINE
            with Image.open(io.BytesIO(dati)) as img:
                if img.width * img.height > MAX_PIXEL_IMMAGINE:        # immagine-trappola: enorme una volta aperta
                    raise ValueError("troppo grande")
                img.verify()
            with Image.open(io.BytesIO(dati)) as img:
                data_exif_trovata = data_exif(img)
        except Exception:
            raise ErroreRichiesta("Il file non è un'immagine leggibile, è danneggiato o ha troppi pixel "
                                  f"(massimo {MAX_PIXEL_IMMAGINE // 1_000_000} megapixel).")
    data_finale = data_exif_trovata if (usa_exif and data_exif_trovata) else data_valida(data or date.today().isoformat())
    diam = numero_o_vuoto(diametro, 0.5, 100, "Diametro (mm)")
    note = (note or "").strip()[:1000]

    with connetti() as con:
        nevo = con.execute("SELECT id, utente_id FROM nevi WHERE id=?", (nevo_id,)).fetchone()
        if nevo is None:
            raise ErroreRichiesta("Neo non trovato.", 404)
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
    """Percorso completo del file originale di una foto (solo se sta dentro la cartella foto)."""
    p = cartella_foto() / riga_foto["file"]
    return p if dentro(cartella_foto(), p) and p.exists() else None


def miniatura(foto_id, utente_id, riga_foto, lato):
    """Miniatura JPEG della foto (ruotata correttamente, senza metadati). Restituisce (byte, tipo MIME)."""
    orig = percorso_foto(riga_foto)
    if orig is None:
        raise ErroreRichiesta("File della foto non trovato.", 404)
    if not HA_PILLOW:
        return orig.read_bytes(), (mimetypes.guess_type(str(orig))[0] or "application/octet-stream")
    lato = lato if lato in (120, 240, 480, 960, 1600) else 480
    cache = cartella_miniature() / f"u{utente_id}" / f"f{foto_id}_{lato}.jpg"
    if cache.exists() and cache.stat().st_mtime >= orig.stat().st_mtime:
        return cache.read_bytes(), "image/jpeg"
    Image.MAX_IMAGE_PIXELS = MAX_PIXEL_IMMAGINE
    with Image.open(orig) as img:
        try:
            img.draft("RGB", (lato * 2, lato * 2))      # per i JPEG: legge già in piccolo (molto più veloce)
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
    """Toglie dal disco la foto, le sue miniature e il suo rapporto."""
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
# 5a-bis. Immagine personale (avatar) dell'utente
# ------------------------------------------------------------------------------------------
# L'utente può scegliere una propria immagine (anche un'icona o un disegno, non per forza la sua
# faccia). Resta sul PC: si salva come piccolo JPEG quadrato 256x256 in CARTELLA_DATI\avatar.
# Non viene mai usata per l'analisi dei nei né inviata a servizi esterni.
LATO_AVATAR = 256
MAX_BYTE_AVATAR = 8 * 1024 * 1024          # l'immagine scelta può essere grande; poi viene ridotta


def percorso_avatar(utente_id):
    return cartella_avatar() / f"u{int(utente_id)}.jpg"


def versione_avatar(utente_id):
    """Un numero che cambia ogni volta che l'immagine cambia (serve al browser per non usare una copia vecchia). 0 = nessuna."""
    try:
        return int(percorso_avatar(utente_id).stat().st_mtime_ns // 1_000_000)
    except OSError:
        return 0


def salva_avatar(utente_id, dati):
    """Controlla l'immagine, la ritaglia al centro in un quadrato, la riduce e la salva come JPEG
    SENZA metadati (niente GPS o dati della fotocamera). Senza Pillow accetta solo un JPEG/PNG già piccolo."""
    if not dati:
        raise ErroreRichiesta("Il file è vuoto.")
    if len(dati) > MAX_BYTE_AVATAR:
        raise ErroreRichiesta(f"L'immagine supera {MAX_BYTE_AVATAR // (1024 * 1024)} MB.", 413)
    ext = riconosci_formato(dati)
    if ext not in (".jpg", ".png", ".webp", ".bmp"):
        raise ErroreRichiesta("Formato non supportato: servono JPG, PNG, WEBP o BMP.")
    if HA_PILLOW:
        try:
            Image.MAX_IMAGE_PIXELS = MAX_PIXEL_IMMAGINE
            with Image.open(io.BytesIO(dati)) as img:
                if img.width * img.height > MAX_PIXEL_IMMAGINE:
                    raise ValueError("troppo grande")
                try:
                    img.draft("RGB", (LATO_AVATAR * 2, LATO_AVATAR * 2))
                except Exception:
                    pass
                img = ImageOps.exif_transpose(img)
                if img.mode in ("RGBA", "LA", "P"):                     # sfondo bianco al posto della trasparenza
                    img = img.convert("RGBA")
                    fondo = Image.new("RGB", img.size, (255, 255, 255))
                    fondo.paste(img, mask=img.split()[-1])
                    img = fondo
                else:
                    img = img.convert("RGB")
                img = ImageOps.fit(img, (LATO_AVATAR, LATO_AVATAR), method=Image.LANCZOS)   # ritaglio centrale + riduzione
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=88, optimize=True)         # nuovo file: nessun metadato originale
            dati_finali = buf.getvalue()
        except ErroreRichiesta:
            raise
        except Exception:
            raise ErroreRichiesta("Il file non è un'immagine leggibile o è troppo grande.")
    else:
        if ext not in (".jpg", ".png") or len(dati) > 400 * 1024:
            raise ErroreRichiesta("Senza Pillow l'immagine deve essere un JPG/PNG sotto i 400 KB "
                                  "(la pagina la riduce da sola: riprova con la funzione 'Scegli immagine').")
        dati_finali = dati
    dest = percorso_avatar(utente_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_bytes(dati_finali)
    os.replace(tmp, dest)                                                # scrittura "atomica": niente file a metà
    return versione_avatar(utente_id)


def cancella_avatar(utente_id):
    try:
        percorso_avatar(utente_id).unlink(missing_ok=True)
    except OSError:
        pass


# ------------------------------------------------------------------------------------------
# 5b. Analisi automatica (usa melanoma_batch.py) - una alla volta, in coda
# ------------------------------------------------------------------------------------------
_coda_analisi = []                       # id delle foto in attesa
_blocco_coda = threading.Lock()
_thread_analisi = [None]
_processo_attuale = {"foto": None, "popen": None}
TIMEOUT_ANALISI_S = 3 * 3600             # tempo massimo per una foto (i modelli sono pesanti)


def analisi_attiva():
    """True se c'è almeno un'analisi in coda o in corso.

    Serve a NON spegnere il programma mentre sta ancora lavorando su una foto: l'analisi può
    durare minuti (i modelli sono pesanti) e chiudere la finestra non deve buttarla via.
    """
    with _blocco_coda:
        if _coda_analisi:
            return True
    t = _thread_analisi[0]
    return t is not None and t.is_alive()


def eseguibile_python():
    """Percorso del Python da usare per lanciare l'analisi.

    Se NeoTracker è stato avviato SENZA finestra nera (con "pythonw.exe", come fa l'icona sul
    Desktop), per l'analisi serve comunque "python.exe" (con pythonw i programmi non possono
    scrivere testo). Lo lanciamo poi con CREATE_NO_WINDOW, quindi non compare nessuna finestra.
    """
    exe = Path(sys.executable)
    if os.name == "nt" and exe.name.lower() == "pythonw.exe":
        candidato = exe.with_name("python.exe")
        if candidato.exists():
            return str(candidato)
    return str(exe)


def trova_batch():
    """Cerca melanoma_batch.py accanto a questo file o nella cartella dei progetti."""
    for c in (CARTELLA_SCRIPT / "melanoma_batch.py", Path(CARTELLA_REPO) / "melanoma_batch.py"):
        if c.exists():
            return c
    return None


def stato_installazione():
    """Che cosa è pronto sul PC (mostrato nelle Impostazioni, per capire subito cosa manca)."""
    repo = Path(CARTELLA_REPO)
    app1, vatsal = repo / "DeborahAdedigba_Melanoma-Detection_App", repo / "vatsal30_Melanoma-Detection"
    n_app1 = len(list(app1.glob("*.keras"))) + len(list(app1.glob("*.weights.h5"))) if app1.exists() else 0
    n_vat = len(list((vatsal / "model").glob("model_fold_*.bin"))) if vatsal.exists() else 0
    return {"batch": str(trova_batch()) if trova_batch() else "", "repo": str(repo),
            "progetti": [
                {"nome": "Metodo 1 - App 1 (Deborah Adedigba)", "presente": app1.exists(),
                 "dettaglio": f"{n_app1} file modello su 10"},
                {"nome": "Metodo 2 - SkinSense (servizio online)", "presente": True,
                 "dettaglio": "attivo solo se lo abiliti qui sotto"},
                {"nome": "Metodo 4 - vatsal30", "presente": vatsal.exists(),
                 "dettaglio": f"{n_vat} file modello su 5"},
            ]}


def _scrivi_stato(foto_id, **campi):
    with connetti() as con:
        imp = ", ".join(f"{k}=?" for k in campi)
        # Controllo di sicurezza (bandit B608): i nomi delle colonne sono scritti da noi, i valori passano come parametri.
        con.execute(f"UPDATE foto SET {imp} WHERE id=?", (*campi.values(), foto_id))   # nosec B608


def accoda_analisi(foto_id):
    """Mette la foto in coda per l'analisi (se non c'è già). Parte da sola in un thread."""
    with connetti() as con:
        r = con.execute("SELECT stato_analisi FROM foto WHERE id=?", (foto_id,)).fetchone()
        if r is None:
            raise ErroreRichiesta("Foto non trovata.", 404)
        if r["stato_analisi"] in ("in_coda", "in_corso"):
            return r["stato_analisi"]
        if trova_batch() is None:
            raise ErroreRichiesta("Non trovo melanoma_batch.py: deve stare nella stessa cartella di neotracker.py "
                                  f"(oppure in {CARTELLA_REPO}).", 409)
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
        except Exception as e:                       # qualunque imprevisto: segno errore e passo alla prossima
            traceback.print_exc()
            try:
                _scrivi_stato(foto_id, stato_analisi="errore", messaggio=f"Errore imprevisto: {e}")
            except Exception:
                pass


def _copia_per_analisi(origine, destinazione):
    """Copia pulita per i modelli: ruotata come nell'originale, senza metadati (GPS ecc.), RGB, JPEG."""
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
        return                                       # foto cancellata mentre era in coda
    origine = percorso_foto(r)
    if origine is None:
        _scrivi_stato(foto_id, stato_analisi="errore", messaggio="File della foto non trovato.")
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
        # stdin=DEVNULL: avviato senza finestra nera non esiste una "tastiera" da ereditare e
        # Windows darebbe l'errore "handle non valido"; così il processo figlio parte sempre.
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                             cwd=str(batch.parent), env=env, creationflags=flag)
        _processo_attuale.update(foto=foto_id, popen=p)
        try:
            p.wait(timeout=TIMEOUT_ANALISI_S)
        except subprocess.TimeoutExpired:
            p.kill()
            _processo_attuale.update(foto=None, popen=None)
            _scrivi_stato(foto_id, stato_analisi="errore",
                          messaggio=f"Analisi interrotta dopo {TIMEOUT_ANALISI_S // 3600} ore (troppo lunga).")
            return
        finally:
            _processo_attuale.update(foto=None, popen=None)

    sint = sintesi_rapporto(rel)
    if sint is None:
        coda_log = ultime_righe(cartella / "log_analisi.txt", 6)
        _scrivi_stato(foto_id, stato_analisi="errore",
                      messaggio="L'analisi non ha prodotto il rapporto. Ultime righe del log: " + (coda_log or "(vuoto)"))
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
    """Ultime righe del log di un'analisi in corso (per mostrare 'Metodo 2: avvio...')."""
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
    """Stesso criterio di melanoma_batch.py: 'attenzione' | 'benigno' | 'discordante' | None."""
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
    Legge rapporto.json e lo riduce a una sintesi per l'interfaccia:
    per ogni metodo: verdetto, conteggio ("4 su 5 dicono ...") e righe per modello.
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
        frase = "; ".join(f"{n} su {len(ok)}: {et}" for et, n in sorted(conteggi.items(), key=lambda kv: -kv[1]))
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
