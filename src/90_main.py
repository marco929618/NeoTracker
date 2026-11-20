
# ==========================================================================================
# 7. START-UP: opens the app window, keeps the engine running and shuts it down when you close it
# ==========================================================================================
# How it works, in brief (plain words):
# 1. The engine (this program) starts and listens on your PC (127.0.0.1).
# 2. It opens Microsoft Edge (or Chrome, if Edge is not there) in "app" mode: it is a normal
# Windows window, WITHOUT an address bar and WITHOUT tabs, with the NeoTracker icon
# in the taskbar. Edge and Chrome are already on your PC: nothing is installed.
# 3. The window uses a separate profile of its own ("profilo_finestra" folder inside the NeoTracker
# data), so it does not get mixed with your normal browsing (history, passwords...).
# 4. When you close the window, the engine notices (see 5c) and shuts itself down.
# 5. If Edge/Chrome cannot be found, the default browser opens (it works the same,
# but with the address bar).

NOME_FINESTRA = "NeoTracker"                      # window title (same as the <title> of the page)
_USCITA_ORIGINALE = {"senza_console": False}      # becomes True if the program started without a black window


class Server(ThreadingHTTPServer):
    daemon_threads = True                         # threads do not block shutdown
    allow_reuse_address = (os.name != "nt")       # on Windows this option would allow TWO servers on the same port
    chiusura_richiesta = False                    # becomes True if you press "Quit" in the app

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fine_sorveglianza = threading.Event()   # used to stop the "supervisor" when the server closes


# ------------------------------------------------------------------------------------------
# 7a. If there is no black window (start with pythonw), write to a file instead of the screen
# ------------------------------------------------------------------------------------------
def percorso_log():
    return Path(CARTELLA_DATI) / "neotracker.log"


def prepara_uscita_testo():
    """When the icon starts the program WITHOUT a black window, Python has no screen to
    write to (sys.stdout is None) and every print() would fail. Here we connect the screen and
    the errors to a text file (neotracker.log in the data folder): if something goes wrong,
    it says what. If instead the black window is there (or you are in Spyder) nothing changes."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    _USCITA_ORIGINALE["senza_console"] = True
    log = percorso_log()
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        if log.exists() and log.stat().st_size > 500_000:          # file too big: I keep only the old one
            vecchio = log.with_name("neotracker.vecchio.log")
            if vecchio.exists():
                vecchio.unlink()
            log.rename(vecchio)
        f = open(log, "a", encoding="utf-8", errors="replace", buffering=1)   # buffering=1: writes line by line
        f.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S}  NeoTracker {VERSIONE} starting =====\n")
    except Exception:
        f = open(os.devnull, "w", encoding="utf-8")               # in the worst case, we throw the text away
    if sys.stdout is None:
        sys.stdout = f
    if sys.stderr is None:
        sys.stderr = f


# Texts of the start-up error windows (they appear before the browser is ready, so they cannot use the
# web/i18n_XX.js dictionaries). The key is the English text; build.py checks that every language is there.
TESTI_AVVIO = {
    "NeoTracker is already running": {
        "it": "NeoTracker è già acceso",
        "fr": "NeoTracker est déjà lancé",
        "de": "NeoTracker läuft bereits",
        "es": "NeoTracker ya está en ejecución"},
    "I cannot open a new window because the session key is missing.\n"
    "Close NeoTracker (from Task Manager, Python process) and reopen it from its icon.": {
        "it": "Non riesco ad aprire una nuova finestra perché manca la chiave di sessione.\n"
        "Chiudi NeoTracker (dal Task Manager, processo Python) e riaprilo dall'icona.",
        "fr": "Impossible d'ouvrir une nouvelle fenêtre : la clé de session est introuvable.\n"
        "Fermez NeoTracker (depuis le Gestionnaire des tâches, processus Python) puis rouvrez-le avec son icône.",
        "de": "Es kann kein neues Fenster geöffnet werden, weil der Sitzungsschlüssel fehlt.\n"
        "Beenden Sie NeoTracker (im Task-Manager, Python-Prozess) und starten Sie es erneut über das Symbol.",
        "es": "No puedo abrir una ventana nueva porque falta la clave de sesión.\n"
        "Cierra NeoTracker (desde el Administrador de tareas, proceso Python) y vuelve a abrirlo desde el icono."},
    "NeoTracker cannot start": {
        "it": "NeoTracker non si avvia",
        "fr": "NeoTracker ne démarre pas",
        "de": "NeoTracker startet nicht",
        "es": "NeoTracker no se inicia"},
    "I cannot use port {porta} ({e}).\n"
    "Another program is using it. Close it, or change PORTA at the top of neotracker.py.": {
        "it": "Non riesco a usare la porta {porta} ({e}).\n"
        "Un altro programma la sta usando. Chiudilo oppure cambia PORTA in cima al file neotracker.py.",
        "fr": "Impossible d'utiliser le port {porta} ({e}).\n"
        "Un autre programme l'utilise. Fermez-le ou modifiez PORTA en haut du fichier neotracker.py.",
        "de": "Der Port {porta} kann nicht verwendet werden ({e}).\n"
        "Ein anderes Programm belegt ihn. Beenden Sie es oder ändern Sie PORTA am Anfang von neotracker.py.",
        "es": "No puedo usar el puerto {porta} ({e}).\n"
        "Otro programa lo está usando. Ciérralo o cambia PORTA al principio del archivo neotracker.py."},
    "NeoTracker has stopped": {
        "it": "NeoTracker si è fermato",
        "fr": "NeoTracker s'est arrêté",
        "de": "NeoTracker wurde beendet",
        "es": "NeoTracker se ha detenido"},
    "Details in:": {
        "it": "Dettagli in:",
        "fr": "Détails dans :",
        "de": "Details in:",
        "es": "Detalles en:"},
}


def testo_avvio(testo, **parametri):
    """The text of the error window in the user's language (if the translation is missing, the English text stays)."""
    try:
        lingua = lingua_corrente()
    except Exception:
        lingua = "en"
    scelto = TESTI_AVVIO.get(testo, {}).get(lingua, testo)
    return scelto.format(**parametri) if parametri else scelto


def mostra_errore(titolo, testo):
    """Shows a serious problem. With the black window it is enough to write it; without the black window
    (icon on the Desktop) nobody would read the log, so a Windows message box appears."""
    print(f"\n{titolo}\n{testo}")
    if os.name == "nt" and _USCITA_ORIGINALE["senza_console"]:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f"{testo}\n\n{testo_avvio('Details in:')}\n{percorso_log()}", titolo, 0x10)   # 0x10 = error icon
        except Exception:
            pass


# ------------------------------------------------------------------------------------------
# 7b. Finding Edge/Chrome and opening the "app" window
# ------------------------------------------------------------------------------------------
def trova_browser_app():
    """Path of Edge or Chrome (None if they cannot be found). Edge first: it is always there on Windows 10/11."""
    forzato = os.environ.get("NEOTRACKER_BROWSER", "")           # used in the tests to simulate a browser
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
    # Last attempt: the programs reachable from the "system path" (also useful on Linux/Mac)
    for nome in ("msedge", "microsoft-edge", "chrome", "google-chrome", "chromium", "chromium-browser"):
        trovato = shutil.which(nome)
        if trovato:
            return trovato
    return None


def argomenti_finestra(exe, url):
    """The list of words used to launch Edge/Chrome. Every line is explained."""
    profilo = Path(CARTELLA_DATI) / "profilo_finestra"
    return [
        exe,
        f"--app={url}",                       # app mode: no address bar or tabs
        f"--user-data-dir={profilo}",         # separate profile: it does not touch your everyday Edge/Chrome
        "--no-first-run",                     # no welcome screens at the first start of the profile
        "--no-default-browser-check",         # do not ask to become the default browser
        "--hide-crash-restore-bubble",        # no "the browser did not close correctly" notice
        "--window-size=1320,900",             # initial size (then Windows remembers the last one used)
    ]


def apri_finestra(url):
    """Opens NeoTracker in its own window. True if something opened."""
    exe = trova_browser_app()
    if exe:
        try:
            if os.name == "nt":
                # DETACHED_PROCESS: the browser lives on its own, even if this program closes.
                flag = getattr(subprocess, "DETACHED_PROCESS", 0x8) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
                subprocess.Popen(argomenti_finestra(exe, url), creationflags=flag, close_fds=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(argomenti_finestra(exe, url), start_new_session=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            print(f"Cannot open the window with {exe}: {e}")
    # Plan B: the default browser, in a normal tab. It works, but the address bar is visible.
    print("Edge/Chrome not found (or they do not start): opening the default browser.")
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


def porta_in_primo_piano():
    """If the NeoTracker window is already open (perhaps minimised), brings it to the front.
    Windows only. True if it was found. Any problem -> False and a new window will be opened."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        # We tell Python that the "window numbers" are 64-bit pointers (otherwise they get truncated).
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        trovate = []
        # "TipoGuarda" describes the function that Windows calls once for each open window.
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
            # We look for an Edge/Chrome window (class Chrome_WidgetWin_1) titled "NeoTracker": the class
            # avoids confusion with, for example, a folder called "NeoTracker".
            if titolo.value == NOME_FINESTRA and classe.value == "Chrome_WidgetWin_1":
                trovate.append(hwnd)
            return True

        user32.EnumWindows(guarda, 0)
        if not trovate:
            return False
        hwnd = trovate[0]
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)                           # 9 = SW_RESTORE: removes the minimised state
        user32.keybd_event(0x12, 0, 0, 0)                         # small trick (pressing and releasing Alt) that makes
        user32.keybd_event(0x12, 0, 2, 0)                         # Windows accept the change of the foreground window
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def _strumento_windows(relativo):
    """Full path of a Windows tool (System32 folder). This way there is no risk of launching
    by mistake a program with the same name found in another folder (for example the current one)."""
    radice = os.environ.get("SystemRoot") or r"C:\Windows"
    return str(Path(radice) / "System32" / relativo)


def chiudi_finestra_app():
    """Closes the app window (only the processes of our separate profile: your everyday Edge/Chrome
    is NOT touched). Needed when you press "Quit" inside the app."""
    profilo = str(Path(CARTELLA_DATI) / "profilo_finestra")
    try:
        if os.name == "nt":
            # PowerShell looks for the processes whose command line contains the folder of the separate
            # profile and closes them. The path is passed through an environment variable (safer than pasting
            # it into the command). "$PID" is PowerShell itself: we exclude it.
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
        pass                                                      # if it fails, the window stays: you close it with the X


# ------------------------------------------------------------------------------------------
# 7c. The "supervisor": every second it checks whether the window has been closed
# ------------------------------------------------------------------------------------------
def sorveglia_finestra(server, passo=1.0):
    """Runs in a separate thread. When the window is closed (and no analysis is running) it stops the server."""
    ultimo_giro = time.monotonic()
    while not server.fine_sorveglianza.wait(passo):               # wait 1 second, then check
        adesso = time.monotonic()
        if adesso - ultimo_giro > 15:
            # The "second" lasted more than 15: the PC was asleep. During sleep the page could not beat, so we
            # do not consider the window closed.
            STATO_FINESTRA.dopo_sospensione(adesso)
        ultimo_giro = adesso
        if STATO_FINESTRA.da_spegnere(adesso, analisi_attiva()):
            print("The NeoTracker window was closed: shutting the program down.")
            server.shutdown()                                     # makes serve_forever() exit in the main thread
            return


# ------------------------------------------------------------------------------------------
# 7d. The actual start-up
# ------------------------------------------------------------------------------------------
def ping_server():
    """If a NeoTracker is already on this port, returns its state (a dictionary); otherwise None."""
    try:
        # Security check (bandit B310): fixed address, this computer.
        with urllib.request.urlopen(f"http://{INDIRIZZO}:{PORTA}/api/ping", timeout=2) as r:   # nosec B310
            d = json.loads(r.read().decode("utf-8"))
            return d if d.get("app") == "NeoTracker" else None
    except Exception:
        return None


def gia_in_esecuzione():
    """True if a NeoTracker is already on this port (e.g. you clicked the icon twice)."""
    return ping_server() is not None


def ferma_analisi_in_corso():
    """If you close the app while it is analysing a photo, it also stops the analysis (with all its processes)."""
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
        prepara_uscita_testo()                                    # before any print()
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        url = f"http://{INDIRIZZO}:{PORTA}/"
        inizializza_db()

        # ---- case 1: NeoTracker is already running (you clicked the icon a second time) ----
        stato = ping_server()
        if stato is not None:
            if stato.get("finestra_aperta") and porta_in_primo_piano():
                print("NeoTracker is already open: I brought the window to the front.")
            else:
                # The running program only accepts whoever presents its session key (see 6c-bis): we read it
                # from the file it wrote at start-up.
                chiave = leggi_token_da_file()
                if stato.get("protetto") and not chiave:
                    mostra_errore(testo_avvio("NeoTracker is already running"),
                                  testo_avvio("I cannot open a new window because the session key is missing.\n"
                                              "Close NeoTracker (from Task Manager, Python process) and reopen it from its icon."))
                    return
                print("NeoTracker is already running: opening a window.")
                apri_finestra(url + (f"?avvio={chiave}" if chiave else ""))
            return

        # ---- case 2: normal start -----
        try:
            server = Server((INDIRIZZO, PORTA), Gestore)
        except OSError as e:
            mostra_errore(testo_avvio("NeoTracker cannot start"),
                          testo_avvio("I cannot use port {porta} ({e}).\n"
                                      "Another program is using it. Close it, or change PORTA at the top of neotracker.py.",
                                      porta=PORTA, e=e))
            return
        STATO_FINESTRA.azzera()                                   # the count of open pages starts again from zero
        scrivi_token_su_file()                                    # the key of this session (a second clicked icon needs it)

        print("=" * 70)
        print(f" NeoTracker {VERSIONE} is running:  {url}")
        print(f" Your data is in: {CARTELLA_DATI}")
        print("=" * 70)
        print(" The app window opens. When you close it, the program shuts itself down")
        print(" (if it is analysing a photo, it finishes the analysis first).")
        print(" This black window, if you see it, is only there to help diagnose any problems.")
        # The key travels only in the address used to open the window (then it becomes a cookie and the
        # address is cleaned up).
        threading.Timer(0.6, lambda: apri_finestra(f"{url}?avvio={TOKEN_SESSIONE}")).start()
        threading.Thread(target=sorveglia_finestra, args=(server,), name="sorvegliante", daemon=True).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.fine_sorveglianza.set()
            cancella_token_file()                                 # the key is no longer valid
            ferma_analisi_in_corso()
            if server.chiusura_richiesta:
                chiudi_finestra_app()                             # "Quit" pressed: I close the window too
            server.server_close()
            print("NeoTracker closed. See you soon.")
    except Exception as e:                                        # unexpected error at start-up: I show it clearly
        traceback.print_exc()
        mostra_errore(testo_avvio("NeoTracker has stopped"), f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    avvia()
