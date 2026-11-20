# Tests of the "app window" mode: heartbeat state, browser start-up, log without a console, watchdog.
# Usage: python3 test_finestra.py   (no internet needed, no real window is opened)
import importlib.util
import json
import os
import stat
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

PORTA_APP = 8752
tmp = Path(tempfile.mkdtemp(prefix="neo_fin_"))
spec = importlib.util.spec_from_file_location("neotracker", Path(__file__).parent.parent / "neotracker.py")
nt = importlib.util.module_from_spec(spec)
sys.modules["neotracker"] = nt
spec.loader.exec_module(nt)
nt.CARTELLA_DATI = tmp
nt.PORTA = PORTA_APP
nt.inizializza_db()

ok_n = fail_n = 0


def verifica(nome, condizione, extra=""):
    global ok_n, fail_n
    if condizione:
        ok_n += 1
        print(f"  ok   {nome}")
    else:
        fail_n += 1
        print(f"  FAIL {nome} {extra}")


# ------------------------------------------------------------------------------------------
print("== StatoFinestra: scenarios with simulated time")
S = nt.StatoFinestra
st = S(adesso=0)
verifica("at the beginning no window, and it does not shut down at once", not st.da_spegnere(5) and not st.finestra_aperta(5))
st.battito("a", 10)
verifica("after a heartbeat: window open", st.finestra_aperta(11))
mai_spento = True
for t_ in range(15, 3600, 5):                          # an hour of heartbeats every 5 seconds
    st.battito("a", t_)
    mai_spento = mai_spento and not st.da_spegnere(t_ + 1)
verifica("a page that beats regularly for an hour never causes a shutdown", mai_spento)
st = S(adesso=0)
st.battito("a", 10)
st.battito("a", 15)
st.addio("a", 20)
verifica("goodbye: it does not shut down at once (reload with F5)", not st.da_spegnere(21))
verifica("goodbye: it shuts down after the grace period", st.da_spegnere(20 + nt.GRAZIA_CHIUSURA_S + 0.1))
st.battito("b", 24)                                    # the page comes back within the grace period (F5)
verifica("reload: the new heartbeat cancels the shutdown", not st.da_spegnere(40) and st.finestra_aperta(40))

st = S(adesso=0)
st.battito("a", 1)
st.battito("b", 2)
st.addio("a", 3)
verifica("two windows: closing one does not shut down", not st.da_spegnere(30))
verifica("two windows: the second is still open (recent heartbeats)", st.finestra_aperta(4) and not st.da_spegnere(4 + 10))
st.battito("b", 100)
st.addio("b", 105)
verifica("two windows: the last one closed too -> it shuts down", st.da_spegnere(105 + nt.GRAZIA_CHIUSURA_S))

st = S(adesso=0)
st.battito("a", 5)
verifica("a window silent beyond the maximum silence = closed", not st.da_spegnere(5 + nt.SILENZIO_MASSIMO_S - 1) and
         not st.finestra_aperta(5 + nt.FINESTRA_APERTA_S + 1))
verifica("... and after the maximum silence + grace it shuts down", st.da_spegnere(5 + nt.SILENZIO_MASSIMO_S + 1) is False and
         st.da_spegnere(5 + nt.SILENZIO_MASSIMO_S + 1 + nt.GRAZIA_CHIUSURA_S + 1))

st = S(adesso=0)
st.battito("a", 1)
st.addio("a", 2, definitivo=True)
st.battito("a", 2.001)                                  # heartbeat arriving late, after the goodbye
verifica("final goodbye: a late heartbeat does NOT bring the page back", "a" not in st.pagine and not st.finestra_aperta(2.5))
verifica("... and the program shuts down normally", st.da_spegnere(2 + nt.GRAZIA_CHIUSURA_S + 0.1))
st = S(adesso=0)
st.battito("a", 1)
st.addio("a", 2)                                        # connection dropped (not final)
st.battito("a", 3)                                      # the page was alive: it shows up again with the same number
verifica("non-final goodbye (connection dropped): the page can come back", "a" in st.pagine and not st.da_spegnere(30))
st = S(adesso=0)
for i in range(700):
    st.addio(f"p{i}", i, definitivo=True)
verifica("the list of closed pages does not grow forever", len(st.chiuse) <= 500)
st.azzera(0)
verifica("reset also empties the list of closed pages", not st.chiuse)

st = S(adesso=0)
st.battito("a", 1)
st.addio("a", 2)
verifica("analysis in progress: it does not shut down even if the window is closed", not st.da_spegnere(1000, analisi_in_corso=True))
verifica("analysis finished: it shuts down at once", st.da_spegnere(1001, analisi_in_corso=False))
st.battito("c", 1002)
verifica("during the analysis I reopen the icon: the window comes back and it does not shut down", not st.da_spegnere(1040) and st.finestra_aperta(1040))

st = S(adesso=0)
verifica("no window ever appeared: it waits", not st.da_spegnere(nt.ATTESA_PRIMA_FINESTRA_S - 1))
verifica("... then it shuts down (start-up failed)", st.da_spegnere(nt.ATTESA_PRIMA_FINESTRA_S + 1))

st = S(adesso=0)
st.battito("a", 10)
st.dopo_sospensione(10 + 4000)                          # the PC was suspended for more than an hour
verifica("after the suspension the page does not count as closed", not st.da_spegnere(10 + 4000 + 5) and st.finestra_aperta(10 + 4001))
st.azzera(0)
verifica("azzera: stato pulito", not st.pagine and not st.vista_almeno_una and st.vuoto_da is None)

# ------------------------------------------------------------------------------------------
print("== API: battito, addio, ping")
nt.STATO_FINESTRA.azzera()
srv = nt.Server(("127.0.0.1", PORTA_APP), nt.Gestore)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{PORTA_APP}"


def chiama(metodo, percorso, corpo=None, header=None):
    h = {"X-NeoTracker": "1", "Content-Type": "application/json", "Cookie": f"{nt.NOME_COOKIE}={nt.TOKEN_SESSIONE}"}
    h.update(header or {})
    req = urllib.request.Request(URL + percorso, data=None if corpo is None else json.dumps(corpo).encode(), method=metodo, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


c, r = chiama("GET", "/api/ping")
verifica("ping: finestra_aperta false at the beginning", c == 200 and r["finestra_aperta"] is False, str(r))
c, r = chiama("POST", "/api/battito", {"id": "pagina-1"})
verifica("heartbeat accepted", c == 200 and r["ok"])
c, r = chiama("GET", "/api/ping")
verifica("ping: finestra_aperta true after the heartbeat", r["finestra_aperta"] is True)
c, _ = chiama("POST", "/api/battito", {"id": "<script>"})
verifica("id with strange characters rejected", c == 400)
c, _ = chiama("POST", "/api/battito", {})
verifica("missing id rejected", c == 400)
c, _ = chiama("POST", "/api/battito", {"id": "x" * 65})
verifica("id too long rejected", c == 400)
c, _ = chiama("POST", "/api/battito", {"id": "pagina-2"}, header={"X-NeoTracker": ""})
verifica("heartbeat without the security header rejected", c == 403)
c, _ = chiama("GET", "/api/battito")
verifica("GET on /api/battito not allowed", c == 405)
c, r = chiama("POST", "/api/addio", {"id": "pagina-1"})
c, r = chiama("GET", "/api/ping")
verifica("goodbye: finestra_aperta goes back to false", r["finestra_aperta"] is False and nt.STATO_FINESTRA.vuoto_da is not None)

print("== API: presence connection (/api/presenza)")
import socket


def apri_presenza(id_pagina):
    sk = socket.create_connection(("127.0.0.1", PORTA_APP), timeout=5)
    sk.sendall(f"GET /api/presenza?id={id_pagina} HTTP/1.1\r\nHost: 127.0.0.1:{PORTA_APP}\r\nCookie: {nt.NOME_COOKIE}={nt.TOKEN_SESSIONE}\r\n\r\n".encode())
    dati, fine = b"", time.time() + 4
    while b"retry" not in dati and time.time() < fine:
        dati += sk.recv(4096)
    return sk, dati


sk, dati = apri_presenza("sse-1")
verifica("presence: event-stream response", b"200" in dati.split(b"\r\n")[0] and b"text/event-stream" in dati and b"retry: 1000" in dati, dati[:200].decode(errors="replace"))
c, r = chiama("GET", "/api/ping")
verifica("presence: as long as the connection is open the window counts as open", r["finestra_aperta"] is True and "sse-1" in nt.STATO_FINESTRA.pagine)
sk.close()                                              # the window closes (or the browser is killed)
fine = time.time() + 5
while time.time() < fine and "sse-1" in nt.STATO_FINESTRA.pagine:
    time.sleep(0.1)
verifica("presence: connection closed -> the page disappears in a few seconds", "sse-1" not in nt.STATO_FINESTRA.pagine)
c, r = chiama("GET", "/api/ping")
verifica("presence: ... and the ping confirms it", r["finestra_aperta"] is False and nt.STATO_FINESTRA.vuoto_da is not None)
c, r = chiama("GET", "/api/presenza?id=<x>")
verifica("presence: invalid id rejected", c == 400, str(r))
c, r = chiama("GET", "/api/presenza")
verifica("presence: missing id rejected", c == 400, str(r))
sk = socket.create_connection(("127.0.0.1", PORTA_APP), timeout=5)
sk.sendall(f"GET /api/presenza?id=sse-2 HTTP/1.1\r\nHost: evil.example.com\r\nCookie: {nt.NOME_COOKIE}={nt.TOKEN_SESSIONE}\r\n\r\n".encode())
verifica("presence: wrong Host rejected", b" 403 " in sk.recv(4096).split(b"\r\n")[0])
sk.close()
sk, dati = apri_presenza("sse-3")
srv.fine_sorveglianza.set()                             # the program is closing: the connections are let go
sk.settimeout(4)
fine_flusso = False
try:
    while True:
        pezzo = sk.recv(4096)
        if not pezzo:
            fine_flusso = True
            break
except OSError:
    pass
verifica("presence: at shutdown the server closes the connection", fine_flusso)
sk.close()

srv.shutdown()
srv.server_close()

# ------------------------------------------------------------------------------------------
print("== watchdog (with shortened times)")
nt.GRAZIA_CHIUSURA_S = 0.3


class FintoServer:
    """Stands in for the server: records whether it is asked to stop."""
    def __init__(self):
        self.fine_sorveglianza = threading.Event()
        self.fermato = threading.Event()

    def shutdown(self):
        self.fermato.set()


nt.STATO_FINESTRA.azzera()
nt.STATO_FINESTRA.battito("a")
fs = FintoServer()
t = threading.Thread(target=nt.sorveglia_finestra, args=(fs, 0.05), daemon=True)
t.start()
time.sleep(0.6)
verifica("window open: the watchdog stops nothing", not fs.fermato.is_set())
nt.STATO_FINESTRA.addio("a")
verifica("window closed: the server is stopped", fs.fermato.wait(2))
t.join(2)
verifica("the watchdog ends after stopping the server", not t.is_alive())

nt.STATO_FINESTRA.azzera()
nt.STATO_FINESTRA.battito("a")
nt.STATO_FINESTRA.addio("a")
vera_analisi = nt.analisi_attiva
nt.analisi_attiva = lambda: True                        # I simulate an analysis in progress
fs = FintoServer()
t = threading.Thread(target=nt.sorveglia_finestra, args=(fs, 0.05), daemon=True)
t.start()
time.sleep(0.9)
verifica("analysis in progress: the server is NOT stopped", not fs.fermato.is_set())
nt.analisi_attiva = lambda: False                       # the analysis finishes
verifica("analysis finished: the server is stopped", fs.fermato.wait(2))
nt.analisi_attiva = vera_analisi
fs.fine_sorveglianza.set()

nt.STATO_FINESTRA.azzera()
nt.STATO_FINESTRA.battito("a")
fs = FintoServer()
t = threading.Thread(target=nt.sorveglia_finestra, args=(fs, 0.05), daemon=True)
t.start()
fs.fine_sorveglianza.set()
t.join(2)
verifica("fine_sorveglianza stops the thread without shutting the server down", not t.is_alive() and not fs.fermato.is_set())
nt.GRAZIA_CHIUSURA_S = 6

# ------------------------------------------------------------------------------------------
print("== analisi_attiva")
verifica("no analysis: false", nt.analisi_attiva() is False)
nt._coda_analisi.append(123)
verifica("photo in the queue: true", nt.analisi_attiva() is True)
nt._coda_analisi.clear()
ev = threading.Event()
nt._thread_analisi[0] = threading.Thread(target=ev.wait, daemon=True)
nt._thread_analisi[0].start()
verifica("analysis thread alive: true", nt.analisi_attiva() is True)
ev.set()
nt._thread_analisi[0].join()
verifica("thread finito: falso", nt.analisi_attiva() is False)
nt._thread_analisi[0] = None

# ------------------------------------------------------------------------------------------
print("== eseguibile_python (pythonw -> python)")
cart = tmp / "pyfinto"
cart.mkdir()
(cart / "pythonw.exe").write_text("")
(cart / "python.exe").write_text("")


class FintoOs:
    """An "os" identical to the real one but claiming to be Windows (to test the Windows branch on Linux)."""
    name = "nt"

    def __getattr__(self, n):
        return getattr(os, n)


vero_os, vero_exe = nt.os, sys.executable
try:
    nt.os = FintoOs()
    sys.executable = str(cart / "pythonw.exe")
    verifica("Windows + pythonw.exe -> python.exe", nt.eseguibile_python() == str(cart / "python.exe"), nt.eseguibile_python())
    sys.executable = str(cart / "python.exe")
    verifica("Windows + python.exe -> invariato", nt.eseguibile_python() == str(cart / "python.exe"))
    (cart / "python.exe").unlink()
    sys.executable = str(cart / "pythonw.exe")
    verifica("Windows + pythonw.exe without python.exe next to it -> unchanged (no crash)", nt.eseguibile_python() == str(cart / "pythonw.exe"))
finally:
    nt.os, sys.executable = vero_os, vero_exe
verifica("Linux: invariato", nt.eseguibile_python() == sys.executable)

# ------------------------------------------------------------------------------------------
print("== trova_browser_app / argomenti_finestra / apri_finestra")
registro = tmp / "registro_browser.txt"
finto = tmp / "finto_browser.sh"
finto.write_text(f'#!/bin/sh\nfor a in "$@"; do echo "$a" >> "{registro}"; done\necho "--fine--" >> "{registro}"\n')
finto.chmod(finto.stat().st_mode | stat.S_IEXEC)
os.environ["NEOTRACKER_BROWSER"] = str(finto)
verifica("NEOTRACKER_BROWSER takes precedence", nt.trova_browser_app() == str(finto))
arg = nt.argomenti_finestra("/x/msedge.exe", "http://127.0.0.1:8750/")
verifica("arguments: app mode", "--app=http://127.0.0.1:8750/" in arg)
verifica("arguments: separate profile inside the data folder", f"--user-data-dir={tmp / 'profilo_finestra'}" in arg)
verifica("arguments: no first run / default browser",
         "--no-first-run" in arg and "--no-default-browser-check" in arg)
verifica("arguments: the first element is the executable", arg[0] == "/x/msedge.exe")
verifica("apri_finestra returns True when a browser is found", nt.apri_finestra("http://127.0.0.1:8750/") is True)
for _ in range(50):
    if registro.exists() and "--fine--" in registro.read_text():
        break
    time.sleep(0.1)
righe = registro.read_text().split() if registro.exists() else []
verifica("the fake browser received the right arguments", "--app=http://127.0.0.1:8750/" in righe and
         any(r.startswith("--user-data-dir=") and r.endswith("profilo_finestra") for r in righe), str(righe))

# browser not found -> plan B (default browser)
aperti = []
vero_trova, vero_wb = nt.trova_browser_app, nt.webbrowser.open
nt.trova_browser_app = lambda: None
nt.webbrowser.open = lambda u: aperti.append(u) or True
verifica("without Edge/Chrome: it uses the default browser", nt.apri_finestra("http://x/") is True and aperti == ["http://x/"])
# executable that does not start -> plan B
aperti.clear()
nt.trova_browser_app = lambda: str(tmp / "non_esiste.exe")
verifica("non-existent executable: plan B without errors", nt.apri_finestra("http://y/") is True and aperti == ["http://y/"])
nt.trova_browser_app, nt.webbrowser.open = vero_trova, vero_wb
del os.environ["NEOTRACKER_BROWSER"]

verifica("porta_in_primo_piano on Linux: false (no crash)", nt.porta_in_primo_piano() is False)

# ---- the Windows branch of porta_in_primo_piano, tested with a fake "user32" (invented list of windows) ----
import ctypes


class FintaFunzione:
    """A fake Windows function: it can be called and has the argtypes attribute like the real ones."""
    def __init__(self, f):
        self.f, self.argtypes = f, None

    def __call__(self, *a):
        return self.f(*a)


def prova_primo_piano(finestre):
    chiamate = []
    u = SimpleNamespace(
        EnumWindows=FintaFunzione(lambda cb, lp: [cb(h, 0) for h in finestre] and 1),
        IsWindowVisible=FintaFunzione(lambda h: finestre[h][2]),
        GetWindowTextLengthW=FintaFunzione(lambda h: len(finestre[h][0])),
        GetWindowTextW=FintaFunzione(lambda h, buf, n: setattr(buf, "value", finestre[h][0]) or len(finestre[h][0])),
        GetClassNameW=FintaFunzione(lambda h, buf, n: setattr(buf, "value", finestre[h][1]) or len(finestre[h][1])),
        IsIconic=FintaFunzione(lambda h: finestre[h][3]),
        ShowWindow=FintaFunzione(lambda h, c: chiamate.append(("ShowWindow", h, c))),
        SetForegroundWindow=FintaFunzione(lambda h: chiamate.append(("Foreground", h))),
        keybd_event=FintaFunzione(lambda *a: chiamate.append(("tasto", a[0], a[2]))),
    )
    vero_os, ctypes.windll, ctypes.WINFUNCTYPE = nt.os, SimpleNamespace(user32=u), ctypes.CFUNCTYPE
    nt.os = FintoOs()
    try:
        esito = nt.porta_in_primo_piano()
    finally:
        nt.os = vero_os
        del ctypes.windll
        del ctypes.WINFUNCTYPE
    return esito, chiamate


# (title, class, visible, minimised)
esito, ch = prova_primo_piano({1: ("Other window", "Chrome_WidgetWin_1", True, False),
                               2: ("NeoTracker", "CabinetWClass", True, False),          # a folder called NeoTracker: NO
                               3: ("NeoTracker", "Chrome_WidgetWin_1", True, True),      # ours, minimised
                               4: ("NeoTracker", "Chrome_WidgetWin_1", False, False)})   # invisibile: NO
verifica("app window found (and not the folder with the same name)", esito is True and ("Foreground", 3) in ch, str(ch))
verifica("if minimised it is restored (SW_RESTORE=9)", ("ShowWindow", 3, 9) in ch, str(ch))
verifica("Alt is pressed and released before bringing it to the front", [c for c in ch if c[0] == "tasto"] == [("tasto", 0x12, 0), ("tasto", 0x12, 2)], str(ch))
esito, ch = prova_primo_piano({1: ("NeoTracker", "Chrome_WidgetWin_1", True, False)})
verifica("window already visible: no restore, only bring to the front", esito is True and ch.count(("Foreground", 1)) == 1 and not any(c[0] == "ShowWindow" for c in ch), str(ch))
esito, ch = prova_primo_piano({1: ("Blocco note", "Notepad", True, False), 2: ("NeoTracker", "CabinetWClass", True, False)})
verifica("no app window: it returns False and touches nothing", esito is False and ch == [], str(ch))

# ---- chiudi_finestra_app: Windows branch (the PowerShell command that would be launched is checked) ----
registrate = []
vero_run, vero_os = nt.subprocess.run, nt.os
nt.subprocess.run = lambda cmd, **kw: registrate.append((cmd, kw))
nt.os = FintoOs()
try:
    nt.chiudi_finestra_app()
finally:
    nt.subprocess.run, nt.os = vero_run, vero_os
cmd, kw = registrate[0] if registrate else ([], {})
verifica("chiudi_finestra_app (Windows): launches PowerShell without a window", cmd[0].lower().endswith("powershell.exe") and "System32" in cmd[0] and kw.get("creationflags") == 0x08000000, str(cmd[:1]))
verifica("... passes the separate profile through an environment variable", kw["env"]["NT_PROFILO"] == str(tmp / "profilo_finestra"), str(kw.get("env", {}).get("NT_PROFILO")))
verifica("... filters only the processes of the profile and spares PowerShell itself", "$env:NT_PROFILO" in cmd[-1] and "Contains($p)" in cmd[-1] and "-ne $PID" in cmd[-1], cmd[-1][:200])
verifica("... and it cannot hang (timeout)", kw.get("timeout") == 20)

# ------------------------------------------------------------------------------------------
print("== start without a console (pythonw): text to file")
vero_out, vero_err = sys.stdout, sys.stderr
try:
    sys.stdout = sys.stderr = None
    nt._USCITA_ORIGINALE["senza_console"] = False
    nt.prepara_uscita_testo()
    print("test line printed without a console")
    try:
        raise ValueError("test error")
    except ValueError:
        import traceback
        traceback.print_exc()
    nt.mostra_errore("Title", "Error text")
    uscita_ok = sys.stdout is not None and sys.stderr is not None
    sys.stdout.flush()
finally:
    sys.stdout, sys.stderr = vero_out, vero_err
log = nt.percorso_log().read_text(encoding="utf-8") if nt.percorso_log().exists() else ""
verifica("stdout/stderr are no longer None", uscita_ok)
verifica("the log contains print, traceback and error message",
         "test line" in log and "ValueError: test error" in log and "Error text" in log, log[:300])
verifica("the log has the start-up header", "starting" in log)
nt._USCITA_ORIGINALE["senza_console"] = False
# log too large: it is rotated
nt.percorso_log().write_text("x" * 600_000, encoding="utf-8")
try:
    sys.stdout = sys.stderr = None
    nt.prepara_uscita_testo()
    sys.stdout.flush()
finally:
    sys.stdout, sys.stderr = vero_out, vero_err
verifica("log too large: rotated into neotracker.vecchio.log", (tmp / "neotracker.vecchio.log").exists() and nt.percorso_log().stat().st_size < 10_000)
nt._USCITA_ORIGINALE["senza_console"] = False

print("== with a normal console nothing changes")
prima = sys.stdout
nt.prepara_uscita_testo()
verifica("sys.stdout unchanged if it exists", sys.stdout is prima)

print(f"\nRESULT: {ok_n} ok, {fail_n} failed")
sys.exit(1 if fail_n else 0)
