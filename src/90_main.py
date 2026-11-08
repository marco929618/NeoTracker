
# ==========================================================================================
# 7. AVVIO: apre la finestra dell'app, tiene acceso il motore e lo spegne quando chiudi
# ==========================================================================================
# Come funziona, in breve (parole semplici):
#   1. Il motore (questo programma) parte e si mette in ascolto sul tuo PC (127.0.0.1).
#   2. Apre Microsoft Edge (o Chrome, se Edge non c'è) in modalità "app": è una finestra
#      normale di Windows, SENZA barra degli indirizzi e SENZA schede, con l'icona di NeoTracker
#      nella barra delle applicazioni. Edge e Chrome sono già sul tuo PC: non si installa nulla.
#   3. La finestra usa un suo profilo separato (cartella "profilo_finestra" dentro i dati di
#      NeoTracker), così non si mescola con la tua navigazione normale (cronologia, password...).
#   4. Quando chiudi la finestra, il motore se ne accorge (vedi 5c) e si spegne da solo.
#   5. Se Edge/Chrome non si trovano, si apre il browser predefinito (funziona uguale,
#      ma con la barra degli indirizzi).

NOME_FINESTRA = "NeoTracker"                      # titolo della finestra (uguale al <title> della pagina)
_USCITA_ORIGINALE = {"senza_console": False}      # diventa True se il programma è partito senza finestra nera


class Server(ThreadingHTTPServer):
    daemon_threads = True                         # i thread non bloccano la chiusura
    allow_reuse_address = (os.name != "nt")       # su Windows questa opzione permetterebbe DUE server sulla stessa porta
    chiusura_richiesta = False                    # diventa True se premi "Esci" nell'app

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fine_sorveglianza = threading.Event()   # serve a fermare il "sorvegliante" quando il server si chiude


# ------------------------------------------------------------------------------------------
# 7a. Se non c'è la finestra nera (avvio con pythonw), scrivere su un file invece che a schermo
# ------------------------------------------------------------------------------------------
def percorso_log():
    return Path(CARTELLA_DATI) / "neotracker.log"


def prepara_uscita_testo():
    """Quando l'icona avvia il programma SENZA finestra nera, Python non ha uno schermo dove
    scrivere (sys.stdout vale None) e ogni print() darebbe errore. Qui colleghiamo schermo ed
    errori a un file di testo (neotracker.log nella cartella dei dati): se qualcosa non va,
    lì c'è scritto cosa. Se invece la finestra nera c'è (o sei in Spyder) non cambia nulla."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    _USCITA_ORIGINALE["senza_console"] = True
    log = percorso_log()
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        if log.exists() and log.stat().st_size > 500_000:          # file troppo grosso: tengo solo il vecchio
            vecchio = log.with_name("neotracker.vecchio.log")
            if vecchio.exists():
                vecchio.unlink()
            log.rename(vecchio)
        f = open(log, "a", encoding="utf-8", errors="replace", buffering=1)   # buffering=1: scrive riga per riga
        f.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S}  avvio NeoTracker {VERSIONE} =====\n")
    except Exception:
        f = open(os.devnull, "w", encoding="utf-8")               # nel peggiore dei casi, buttiamo il testo
    if sys.stdout is None:
        sys.stdout = f
    if sys.stderr is None:
        sys.stderr = f


# Testi delle finestrelle di errore all'avvio (compaiono prima che il browser sia pronto, quindi non possono
# usare i dizionari web/i18n_XX.js). La chiave è il testo italiano; build.py controlla che ci siano tutte le lingue.
TESTI_AVVIO = {
    "NeoTracker è già acceso": {
        "en": "NeoTracker is already running", "fr": "NeoTracker est déjà lancé",
        "de": "NeoTracker läuft bereits", "es": "NeoTracker ya está en ejecución"},
    "Non riesco ad aprire una nuova finestra perché manca la chiave di sessione.\n"
    "Chiudi NeoTracker (dal Task Manager, processo Python) e riaprilo dall'icona.": {
        "en": "I cannot open a new window because the session key is missing.\n"
              "Close NeoTracker (from Task Manager, Python process) and reopen it from its icon.",
        "fr": "Impossible d'ouvrir une nouvelle fenêtre : la clé de session est introuvable.\n"
              "Fermez NeoTracker (depuis le Gestionnaire des tâches, processus Python) puis rouvrez-le avec son icône.",
        "de": "Es kann kein neues Fenster geöffnet werden, weil der Sitzungsschlüssel fehlt.\n"
              "Beenden Sie NeoTracker (im Task-Manager, Python-Prozess) und starten Sie es erneut über das Symbol.",
        "es": "No puedo abrir una ventana nueva porque falta la clave de sesión.\n"
              "Cierra NeoTracker (desde el Administrador de tareas, proceso Python) y vuelve a abrirlo desde el icono."},
    "NeoTracker non si avvia": {
        "en": "NeoTracker cannot start", "fr": "NeoTracker ne démarre pas",
        "de": "NeoTracker startet nicht", "es": "NeoTracker no se inicia"},
    "Non riesco a usare la porta {porta} ({e}).\n"
    "Un altro programma la sta usando. Chiudilo oppure cambia PORTA in cima al file neotracker.py.": {
        "en": "I cannot use port {porta} ({e}).\n"
              "Another program is using it. Close it, or change PORTA at the top of neotracker.py.",
        "fr": "Impossible d'utiliser le port {porta} ({e}).\n"
              "Un autre programme l'utilise. Fermez-le ou modifiez PORTA en haut du fichier neotracker.py.",
        "de": "Der Port {porta} kann nicht verwendet werden ({e}).\n"
              "Ein anderes Programm belegt ihn. Beenden Sie es oder ändern Sie PORTA am Anfang von neotracker.py.",
        "es": "No puedo usar el puerto {porta} ({e}).\n"
              "Otro programa lo está usando. Ciérralo o cambia PORTA al principio del archivo neotracker.py."},
    "NeoTracker si è fermato": {
        "en": "NeoTracker has stopped", "fr": "NeoTracker s'est arrêté",
        "de": "NeoTracker wurde beendet", "es": "NeoTracker se ha detenido"},
    "Dettagli in:": {
        "en": "Details in:", "fr": "Détails dans :", "de": "Details in:", "es": "Detalles en:"},
}


def testo_avvio(testo, **parametri):
    """Il testo della finestrella di errore nella lingua dell'utente (se manca la traduzione, resta l'italiano)."""
    try:
        lingua = lingua_corrente()
    except Exception:
        lingua = "it"
    scelto = TESTI_AVVIO.get(testo, {}).get(lingua, testo)
    return scelto.format(**parametri) if parametri else scelto


def mostra_errore(titolo, testo):
    """Mostra un problema grave. Con la finestra nera basta scriverlo; senza finestra nera
    (icona sul Desktop) nessuno leggerebbe il log, quindi compare una finestrella di Windows."""
    print(f"\n{titolo}\n{testo}")
    if os.name == "nt" and _USCITA_ORIGINALE["senza_console"]:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f"{testo}\n\n{testo_avvio('Dettagli in:')}\n{percorso_log()}", titolo, 0x10)   # 0x10 = icona di errore
        except Exception:
            pass


# ------------------------------------------------------------------------------------------
# 7b. Trovare Edge/Chrome e aprire la finestra "app"
# ------------------------------------------------------------------------------------------
def trova_browser_app():
    """Percorso di Edge o Chrome (None se non si trovano). Edge per primo: c'è sempre su Windows 10/11."""
    forzato = os.environ.get("NEOTRACKER_BROWSER", "")           # usato nei test per simulare un browser
    if forzato and Path(forzato).exists():
        return forzato
    candidati = []
    if os.name == "nt":
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        locale = os.environ.get("LocalAppData", str(Path.home() / "AppData" / "Local"))
        candidati = [
            Path(pf86) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(pf) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(pf) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(pf86) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(locale) / "Google" / "Chrome" / "Application" / "chrome.exe",
        ]
    for c in candidati:
        if c.exists():
            return str(c)
    # Ultimo tentativo: i programmi raggiungibili dal "percorso di sistema" (utile anche su Linux/Mac)
    for nome in ("msedge", "microsoft-edge", "chrome", "google-chrome", "chromium", "chromium-browser"):
        trovato = shutil.which(nome)
        if trovato:
            return trovato
    return None


def argomenti_finestra(exe, url):
    """L'elenco di parole con cui si lancia Edge/Chrome. Ogni riga è spiegata."""
    profilo = Path(CARTELLA_DATI) / "profilo_finestra"
    return [
        exe,
        f"--app={url}",                       # modalità app: niente barra degli indirizzi né schede
        f"--user-data-dir={profilo}",         # profilo separato: non tocca il tuo Edge/Chrome di tutti i giorni
        "--no-first-run",                     # niente schermate di benvenuto al primo avvio del profilo
        "--no-default-browser-check",         # non chiedere di diventare il browser predefinito
        "--hide-crash-restore-bubble",        # niente avviso "il browser non si è chiuso correttamente"
        "--window-size=1320,900",             # grandezza iniziale (poi Windows ricorda l'ultima usata)
    ]


def apri_finestra(url):
    """Apre NeoTracker nella sua finestra. True se qualcosa si è aperto."""
    exe = trova_browser_app()
    if exe:
        try:
            if os.name == "nt":
                # DETACHED_PROCESS: il browser vive per conto suo, anche se questo programma si chiude.
                flag = getattr(subprocess, "DETACHED_PROCESS", 0x8) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
                subprocess.Popen(argomenti_finestra(exe, url), creationflags=flag, close_fds=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(argomenti_finestra(exe, url), start_new_session=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            print(f"Non riesco ad aprire la finestra con {exe}: {e}")
    # Piano B: il browser predefinito, in una scheda normale. Funziona, ma si vede la barra degli indirizzi.
    print("Edge/Chrome non trovati (o non partono): apro il browser predefinito.")
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


def porta_in_primo_piano():
    """Se la finestra di NeoTracker è già aperta (magari ridotta a icona), la riporta davanti.
    Solo Windows. True se l'ha trovata. Qualunque problema -> False e si aprirà una finestra nuova."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        # Diciamo a Python che i "numeri di finestra" sono puntatori a 64 bit (altrimenti si troncano).
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        trovate = []
        # "TipoGuarda" descrive la funzione che Windows richiama una volta per ogni finestra aperta.
        TipoGuarda = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows.argtypes = [TipoGuarda, wintypes.LPARAM]

        @TipoGuarda
        def guarda(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            lung = user32.GetWindowTextLengthW(hwnd)
            if lung <= 0:
                return True
            titolo = ctypes.create_unicode_buffer(lung + 1)
            user32.GetWindowTextW(hwnd, titolo, lung + 1)
            classe = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, classe, 256)
            # Cerchiamo una finestra di Edge/Chrome (classe Chrome_WidgetWin_1) intitolata "NeoTracker":
            # la classe evita di confondersi con, per esempio, una cartella chiamata "NeoTracker".
            if titolo.value == NOME_FINESTRA and classe.value == "Chrome_WidgetWin_1":
                trovate.append(hwnd)
            return True

        user32.EnumWindows(guarda, 0)
        if not trovate:
            return False
        hwnd = trovate[0]
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)                           # 9 = SW_RESTORE: toglie la riduzione a icona
        user32.keybd_event(0x12, 0, 0, 0)                         # piccolo trucco (premere e rilasciare Alt) che permette a
        user32.keybd_event(0x12, 0, 2, 0)                         # Windows di accettare il cambio di finestra in primo piano
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def _strumento_windows(relativo):
    """Percorso completo di uno strumento di Windows (cartella System32). Così non si rischia di lanciare
    per errore un programma con lo stesso nome trovato in un'altra cartella (per esempio quella corrente)."""
    radice = os.environ.get("SystemRoot") or r"C:\Windows"
    return str(Path(radice) / "System32" / relativo)


def chiudi_finestra_app():
    """Chiude la finestra dell'app (solo i processi del nostro profilo separato: il tuo Edge/Chrome
    di tutti i giorni NON viene toccato). Serve quando premi "Esci" dentro l'app."""
    profilo = str(Path(CARTELLA_DATI) / "profilo_finestra")
    try:
        if os.name == "nt":
            # PowerShell cerca i processi la cui riga di comando contiene la cartella del profilo
            # separato e li chiude. Il percorso passa tramite una variabile d'ambiente (più sicuro
            # che incollarlo nel comando). "$PID" è PowerShell stesso: lo escludiamo.
            comando = ("$p = $env:NT_PROFILO; "
                       "Get-CimInstance Win32_Process | "
                       "Where-Object { $_.CommandLine -and $_.CommandLine.Contains($p) -and $_.ProcessId -ne $PID } | "
                       "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
            subprocess.run([_strumento_windows(r"WindowsPowerShell\v1.0\powershell.exe"), "-NoProfile", "-NonInteractive", "-Command", comando],
                           env=dict(os.environ, NT_PROFILO=profilo), stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
        elif shutil.which("pkill"):
            subprocess.run(["pkill", "-f", profilo], stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    except Exception:
        pass                                                      # se non riesce, la finestra resta: la chiudi tu con la X


# ------------------------------------------------------------------------------------------
# 7c. Il "sorvegliante": ogni secondo controlla se la finestra è stata chiusa
# ------------------------------------------------------------------------------------------
def sorveglia_finestra(server, passo=1.0):
    """Gira in un thread a parte. Quando la finestra è chiusa (e nessuna analisi è in corso) ferma il server."""
    ultimo_giro = time.monotonic()
    while not server.fine_sorveglianza.wait(passo):               # aspetta 1 secondo, poi controlla
        adesso = time.monotonic()
        if adesso - ultimo_giro > 15:
            # Il "secondo" è durato più di 15: il PC era in sospensione. Durante il sonno la pagina non
            # poteva battere, quindi non consideriamo la finestra chiusa.
            STATO_FINESTRA.dopo_sospensione(adesso)
        ultimo_giro = adesso
        if STATO_FINESTRA.da_spegnere(adesso, analisi_attiva()):
            print("La finestra di NeoTracker è stata chiusa: spengo il programma.")
            server.shutdown()                                     # fa uscire serve_forever() nel thread principale
            return


# ------------------------------------------------------------------------------------------
# 7d. Avvio vero e proprio
# ------------------------------------------------------------------------------------------
def ping_server():
    """Se su questa porta c'è già un NeoTracker, ne restituisce lo stato (un dizionario); altrimenti None."""
    try:
        # Controllo di sicurezza (bandit B310): indirizzo fisso, questo computer.
        with urllib.request.urlopen(f"http://{INDIRIZZO}:{PORTA}/api/ping", timeout=2) as r:   # nosec B310
            d = json.loads(r.read().decode("utf-8"))
            return d if d.get("app") == "NeoTracker" else None
    except Exception:
        return None


def gia_in_esecuzione():
    """True se su questa porta c'è già un NeoTracker (es. hai cliccato due volte l'icona)."""
    return ping_server() is not None


def ferma_analisi_in_corso():
    """Se chiudi l'app mentre sta analizzando una foto, ferma anche l'analisi (con tutti i suoi processi)."""
    p = _processo_attuale.get("popen")
    if p is not None and p.poll() is None:
        try:
            if os.name == "nt":
                subprocess.run([_strumento_windows("taskkill.exe"), "/PID", str(p.pid), "/T", "/F"], capture_output=True, stdin=subprocess.DEVNULL,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
            else:
                p.terminate()
        except Exception:
            pass


def avvia():
    try:
        CARTELLA_DATI.mkdir(parents=True, exist_ok=True)
        prepara_uscita_testo()                                    # prima di qualunque print()
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        url = f"http://{INDIRIZZO}:{PORTA}/"
        inizializza_db()

        # ---- caso 1: NeoTracker è già acceso (hai cliccato l'icona una seconda volta) ----
        stato = ping_server()
        if stato is not None:
            if stato.get("finestra_aperta") and porta_in_primo_piano():
                print("NeoTracker è già aperto: ho portato la finestra davanti.")
            else:
                # Il programma acceso accetta solo chi presenta la sua chiave di sessione (vedi 6c-bis):
                # la leggiamo dal file che ha scritto all'avvio.
                chiave = leggi_token_da_file()
                if stato.get("protetto") and not chiave:
                    mostra_errore(testo_avvio("NeoTracker è già acceso"),
                                  testo_avvio("Non riesco ad aprire una nuova finestra perché manca la chiave di sessione.\n"
                                              "Chiudi NeoTracker (dal Task Manager, processo Python) e riaprilo dall'icona."))
                    return
                print("NeoTracker è già acceso: apro una finestra.")
                apri_finestra(url + (f"?avvio={chiave}" if chiave else ""))
            return

        # ---- caso 2: avvio normale ----
        try:
            server = Server((INDIRIZZO, PORTA), Gestore)
        except OSError as e:
            mostra_errore(testo_avvio("NeoTracker non si avvia"),
                          testo_avvio("Non riesco a usare la porta {porta} ({e}).\n"
                                      "Un altro programma la sta usando. Chiudilo oppure cambia PORTA in cima al file neotracker.py.",
                                      porta=PORTA, e=e))
            return
        STATO_FINESTRA.azzera()                                   # il conto delle pagine aperte riparte da zero
        scrivi_token_su_file()                                    # la chiave di questa sessione (serve a una seconda icona cliccata)

        print("=" * 70)
        print(f" NeoTracker {VERSIONE} è attivo:  {url}")
        print(f" I tuoi dati sono in: {CARTELLA_DATI}")
        print("=" * 70)
        print(" Si apre la finestra dell'app. Quando la chiudi, il programma si spegne da solo")
        print(" (se sta analizzando una foto, finisce prima l'analisi).")
        print(" Questa finestra nera, se la vedi, serve solo a capire eventuali problemi.")
        # La chiave viaggia solo nell'indirizzo con cui si apre la finestra (poi diventa un cookie e l'indirizzo si ripulisce).
        threading.Timer(0.6, lambda: apri_finestra(f"{url}?avvio={TOKEN_SESSIONE}")).start()
        threading.Thread(target=sorveglia_finestra, args=(server,), name="sorvegliante", daemon=True).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.fine_sorveglianza.set()
            cancella_token_file()                                 # la chiave non vale più
            ferma_analisi_in_corso()
            if server.chiusura_richiesta:
                chiudi_finestra_app()                             # "Esci" premuto: chiudo anche la finestra
            server.server_close()
            print("NeoTracker chiuso. A presto.")
    except Exception as e:                                        # errore imprevisto all'avvio: lo mostro chiaramente
        traceback.print_exc()
        mostra_errore(testo_avvio("NeoTracker si è fermato"), f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    avvia()
