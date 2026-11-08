# Prove della modalità "finestra app": stato dei battiti, avvio del browser, log senza console, sorvegliante.
# Uso: python3 test_finestra.py   (non serve internet, non apre nessuna finestra vera)
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
print("== StatoFinestra: scenari con il tempo simulato")
S = nt.StatoFinestra
st = S(adesso=0)
verifica("all'inizio nessuna finestra e non si spegne subito", not st.da_spegnere(5) and not st.finestra_aperta(5))
st.battito("a", 10)
verifica("dopo un battito: finestra aperta", st.finestra_aperta(11))
mai_spento = True
for t_ in range(15, 3600, 5):                          # un'ora di battiti ogni 5 secondi
    st.battito("a", t_)
    mai_spento = mai_spento and not st.da_spegnere(t_ + 1)
verifica("una pagina che batte regolarmente per un'ora non fa mai spegnere", mai_spento)
st = S(adesso=0)
st.battito("a", 10)
st.battito("a", 15)
st.addio("a", 20)
verifica("addio: non si spegne subito (ricaricamento con F5)", not st.da_spegnere(21))
verifica("addio: si spegne dopo la grazia", st.da_spegnere(20 + nt.GRAZIA_CHIUSURA_S + 0.1))
st.battito("b", 24)                                    # la pagina ricompare entro la grazia (F5)
verifica("ricaricamento: il nuovo battito annulla lo spegnimento", not st.da_spegnere(40) and st.finestra_aperta(40))

st = S(adesso=0)
st.battito("a", 1)
st.battito("b", 2)
st.addio("a", 3)
verifica("due finestre: chiuderne una non spegne", not st.da_spegnere(30))
verifica("due finestre: la seconda ancora aperta (battiti recenti)", st.finestra_aperta(4) and not st.da_spegnere(4 + 10))
st.battito("b", 100)
st.addio("b", 105)
verifica("due finestre: chiusa anche l'ultima -> si spegne", st.da_spegnere(105 + nt.GRAZIA_CHIUSURA_S))

st = S(adesso=0)
st.battito("a", 5)
verifica("finestra muta oltre il silenzio massimo = chiusa", not st.da_spegnere(5 + nt.SILENZIO_MASSIMO_S - 1) and
         not st.finestra_aperta(5 + nt.FINESTRA_APERTA_S + 1))
verifica("... e dopo il silenzio massimo + grazia si spegne", st.da_spegnere(5 + nt.SILENZIO_MASSIMO_S + 1) is False and
         st.da_spegnere(5 + nt.SILENZIO_MASSIMO_S + 1 + nt.GRAZIA_CHIUSURA_S + 1))

st = S(adesso=0)
st.battito("a", 1)
st.addio("a", 2, definitivo=True)
st.battito("a", 2.001)                                  # battito arrivato in ritardo, dopo l'addio
verifica("addio definitivo: un battito in ritardo NON fa risorgere la pagina", "a" not in st.pagine and not st.finestra_aperta(2.5))
verifica("... e il programma si spegne regolarmente", st.da_spegnere(2 + nt.GRAZIA_CHIUSURA_S + 0.1))
st = S(adesso=0)
st.battito("a", 1)
st.addio("a", 2)                                        # connessione caduta (non definitivo)
st.battito("a", 3)                                      # la pagina era viva: si ripresenta con lo stesso numero
verifica("addio non definitivo (connessione caduta): la pagina può tornare", "a" in st.pagine and not st.da_spegnere(30))
st = S(adesso=0)
for i in range(700):
    st.addio(f"p{i}", i, definitivo=True)
verifica("l'elenco delle pagine chiuse non cresce all'infinito", len(st.chiuse) <= 500)
st.azzera(0)
verifica("azzera svuota anche l'elenco delle pagine chiuse", not st.chiuse)

st = S(adesso=0)
st.battito("a", 1)
st.addio("a", 2)
verifica("analisi in corso: non si spegne anche se la finestra è chiusa", not st.da_spegnere(1000, analisi_in_corso=True))
verifica("analisi finita: si spegne subito", st.da_spegnere(1001, analisi_in_corso=False))
st.battito("c", 1002)
verifica("durante l'analisi riapro l'icona: la finestra torna e non si spegne", not st.da_spegnere(1040) and st.finestra_aperta(1040))

st = S(adesso=0)
verifica("nessuna finestra mai comparsa: attende", not st.da_spegnere(nt.ATTESA_PRIMA_FINESTRA_S - 1))
verifica("... poi si spegne (avvio fallito)", st.da_spegnere(nt.ATTESA_PRIMA_FINESTRA_S + 1))

st = S(adesso=0)
st.battito("a", 10)
st.dopo_sospensione(10 + 4000)                          # il PC è stato in sospensione più di un'ora
verifica("dopo la sospensione la pagina non risulta chiusa", not st.da_spegnere(10 + 4000 + 5) and st.finestra_aperta(10 + 4001))
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
verifica("ping: finestra_aperta falso all'inizio", c == 200 and r["finestra_aperta"] is False, str(r))
c, r = chiama("POST", "/api/battito", {"id": "pagina-1"})
verifica("battito accettato", c == 200 and r["ok"])
c, r = chiama("GET", "/api/ping")
verifica("ping: finestra_aperta vero dopo il battito", r["finestra_aperta"] is True)
c, _ = chiama("POST", "/api/battito", {"id": "<script>"})
verifica("id con caratteri strani rifiutato", c == 400)
c, _ = chiama("POST", "/api/battito", {})
verifica("id mancante rifiutato", c == 400)
c, _ = chiama("POST", "/api/battito", {"id": "x" * 65})
verifica("id troppo lungo rifiutato", c == 400)
c, _ = chiama("POST", "/api/battito", {"id": "pagina-2"}, header={"X-NeoTracker": ""})
verifica("battito senza header di sicurezza rifiutato", c == 403)
c, _ = chiama("GET", "/api/battito")
verifica("GET su /api/battito non consentito", c == 405)
c, r = chiama("POST", "/api/addio", {"id": "pagina-1"})
c, r = chiama("GET", "/api/ping")
verifica("addio: finestra_aperta torna falso", r["finestra_aperta"] is False and nt.STATO_FINESTRA.vuoto_da is not None)

print("== API: connessione di presenza (/api/presenza)")
import socket


def apri_presenza(id_pagina):
    sk = socket.create_connection(("127.0.0.1", PORTA_APP), timeout=5)
    sk.sendall(f"GET /api/presenza?id={id_pagina} HTTP/1.1\r\nHost: 127.0.0.1:{PORTA_APP}\r\nCookie: {nt.NOME_COOKIE}={nt.TOKEN_SESSIONE}\r\n\r\n".encode())
    dati, fine = b"", time.time() + 4
    while b"retry" not in dati and time.time() < fine:
        dati += sk.recv(4096)
    return sk, dati


sk, dati = apri_presenza("sse-1")
verifica("presenza: risposta di tipo event-stream", b"200" in dati.split(b"\r\n")[0] and b"text/event-stream" in dati and b"retry: 1000" in dati, dati[:200].decode(errors="replace"))
c, r = chiama("GET", "/api/ping")
verifica("presenza: finché la connessione è aperta la finestra risulta aperta", r["finestra_aperta"] is True and "sse-1" in nt.STATO_FINESTRA.pagine)
sk.close()                                              # la finestra si chiude (o il browser viene ucciso)
fine = time.time() + 5
while time.time() < fine and "sse-1" in nt.STATO_FINESTRA.pagine:
    time.sleep(0.1)
verifica("presenza: connessione chiusa -> la pagina sparisce in pochi secondi", "sse-1" not in nt.STATO_FINESTRA.pagine)
c, r = chiama("GET", "/api/ping")
verifica("presenza: ... e il ping lo conferma", r["finestra_aperta"] is False and nt.STATO_FINESTRA.vuoto_da is not None)
c, r = chiama("GET", "/api/presenza?id=<x>")
verifica("presenza: id non valido rifiutato", c == 400, str(r))
c, r = chiama("GET", "/api/presenza")
verifica("presenza: id mancante rifiutato", c == 400, str(r))
sk = socket.create_connection(("127.0.0.1", PORTA_APP), timeout=5)
sk.sendall(f"GET /api/presenza?id=sse-2 HTTP/1.1\r\nHost: evil.example.com\r\nCookie: {nt.NOME_COOKIE}={nt.TOKEN_SESSIONE}\r\n\r\n".encode())
verifica("presenza: Host sbagliato rifiutato", b" 403 " in sk.recv(4096).split(b"\r\n")[0])
sk.close()
sk, dati = apri_presenza("sse-3")
srv.fine_sorveglianza.set()                             # il programma sta chiudendo: le connessioni vengono lasciate andare
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
verifica("presenza: allo spegnimento il server chiude la connessione", fine_flusso)
sk.close()

srv.shutdown()
srv.server_close()

# ------------------------------------------------------------------------------------------
print("== sorvegliante (con tempi accorciati)")
nt.GRAZIA_CHIUSURA_S = 0.3


class FintoServer:
    """Fa le veci del server: registra se gli viene chiesto di fermarsi."""
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
verifica("finestra aperta: il sorvegliante non ferma nulla", not fs.fermato.is_set())
nt.STATO_FINESTRA.addio("a")
verifica("finestra chiusa: il server viene fermato", fs.fermato.wait(2))
t.join(2)
verifica("il sorvegliante termina dopo aver fermato il server", not t.is_alive())

nt.STATO_FINESTRA.azzera()
nt.STATO_FINESTRA.battito("a")
nt.STATO_FINESTRA.addio("a")
vera_analisi = nt.analisi_attiva
nt.analisi_attiva = lambda: True                        # simulo un'analisi in corso
fs = FintoServer()
t = threading.Thread(target=nt.sorveglia_finestra, args=(fs, 0.05), daemon=True)
t.start()
time.sleep(0.9)
verifica("analisi in corso: il server NON viene fermato", not fs.fermato.is_set())
nt.analisi_attiva = lambda: False                       # l'analisi finisce
verifica("analisi finita: il server viene fermato", fs.fermato.wait(2))
nt.analisi_attiva = vera_analisi
fs.fine_sorveglianza.set()

nt.STATO_FINESTRA.azzera()
nt.STATO_FINESTRA.battito("a")
fs = FintoServer()
t = threading.Thread(target=nt.sorveglia_finestra, args=(fs, 0.05), daemon=True)
t.start()
fs.fine_sorveglianza.set()
t.join(2)
verifica("fine_sorveglianza ferma il thread senza spegnere il server", not t.is_alive() and not fs.fermato.is_set())
nt.GRAZIA_CHIUSURA_S = 6

# ------------------------------------------------------------------------------------------
print("== analisi_attiva")
verifica("nessuna analisi: falso", nt.analisi_attiva() is False)
nt._coda_analisi.append(123)
verifica("foto in coda: vero", nt.analisi_attiva() is True)
nt._coda_analisi.clear()
ev = threading.Event()
nt._thread_analisi[0] = threading.Thread(target=ev.wait, daemon=True)
nt._thread_analisi[0].start()
verifica("thread di analisi vivo: vero", nt.analisi_attiva() is True)
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
    """Un "os" identico al vero ma che dichiara di essere Windows (per provare il ramo Windows su Linux)."""
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
    verifica("Windows + pythonw.exe senza python.exe accanto -> invariato (nessun crash)", nt.eseguibile_python() == str(cart / "pythonw.exe"))
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
verifica("NEOTRACKER_BROWSER ha la precedenza", nt.trova_browser_app() == str(finto))
arg = nt.argomenti_finestra("/x/msedge.exe", "http://127.0.0.1:8750/")
verifica("argomenti: modalità app", "--app=http://127.0.0.1:8750/" in arg)
verifica("argomenti: profilo separato dentro i dati", f"--user-data-dir={tmp / 'profilo_finestra'}" in arg)
verifica("argomenti: niente primo avvio / browser predefinito",
         "--no-first-run" in arg and "--no-default-browser-check" in arg)
verifica("argomenti: il primo elemento è l'eseguibile", arg[0] == "/x/msedge.exe")
verifica("apri_finestra restituisce True con browser trovato", nt.apri_finestra("http://127.0.0.1:8750/") is True)
for _ in range(50):
    if registro.exists() and "--fine--" in registro.read_text():
        break
    time.sleep(0.1)
righe = registro.read_text().split() if registro.exists() else []
verifica("il finto browser ha ricevuto gli argomenti giusti", "--app=http://127.0.0.1:8750/" in righe and
         any(r.startswith("--user-data-dir=") and r.endswith("profilo_finestra") for r in righe), str(righe))

# browser introvabile -> piano B (browser predefinito)
aperti = []
vero_trova, vero_wb = nt.trova_browser_app, nt.webbrowser.open
nt.trova_browser_app = lambda: None
nt.webbrowser.open = lambda u: aperti.append(u) or True
verifica("senza Edge/Chrome: usa il browser predefinito", nt.apri_finestra("http://x/") is True and aperti == ["http://x/"])
# eseguibile che non parte -> piano B
aperti.clear()
nt.trova_browser_app = lambda: str(tmp / "non_esiste.exe")
verifica("eseguibile inesistente: piano B senza errori", nt.apri_finestra("http://y/") is True and aperti == ["http://y/"])
nt.trova_browser_app, nt.webbrowser.open = vero_trova, vero_wb
del os.environ["NEOTRACKER_BROWSER"]

verifica("porta_in_primo_piano su Linux: falso (nessun crash)", nt.porta_in_primo_piano() is False)

# ---- il ramo Windows di porta_in_primo_piano, provato con un finto "user32" (elenco di finestre inventato) ----
import ctypes


class FintaFunzione:
    """Una funzione di Windows finta: si può chiamare e ha l'attributo argtypes come quelle vere."""
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


# (titolo, classe, visibile, ridotta a icona)
esito, ch = prova_primo_piano({1: ("Altra finestra", "Chrome_WidgetWin_1", True, False),
                               2: ("NeoTracker", "CabinetWClass", True, False),          # una cartella chiamata NeoTracker: NO
                               3: ("NeoTracker", "Chrome_WidgetWin_1", True, True),      # la nostra, ridotta a icona
                               4: ("NeoTracker", "Chrome_WidgetWin_1", False, False)})   # invisibile: NO
verifica("finestra app trovata (e non la cartella omonima)", esito is True and ("Foreground", 3) in ch, str(ch))
verifica("se ridotta a icona viene ripristinata (SW_RESTORE=9)", ("ShowWindow", 3, 9) in ch, str(ch))
verifica("viene premuto e rilasciato Alt prima del primo piano", [c for c in ch if c[0] == "tasto"] == [("tasto", 0x12, 0), ("tasto", 0x12, 2)], str(ch))
esito, ch = prova_primo_piano({1: ("NeoTracker", "Chrome_WidgetWin_1", True, False)})
verifica("finestra già visibile: niente ripristino, solo primo piano", esito is True and ch.count(("Foreground", 1)) == 1 and not any(c[0] == "ShowWindow" for c in ch), str(ch))
esito, ch = prova_primo_piano({1: ("Blocco note", "Notepad", True, False), 2: ("NeoTracker", "CabinetWClass", True, False)})
verifica("nessuna finestra dell'app: restituisce False e non tocca nulla", esito is False and ch == [], str(ch))

# ---- chiudi_finestra_app: ramo Windows (si controlla il comando PowerShell che verrebbe lanciato) ----
registrate = []
vero_run, vero_os = nt.subprocess.run, nt.os
nt.subprocess.run = lambda cmd, **kw: registrate.append((cmd, kw))
nt.os = FintoOs()
try:
    nt.chiudi_finestra_app()
finally:
    nt.subprocess.run, nt.os = vero_run, vero_os
cmd, kw = registrate[0] if registrate else ([], {})
verifica("chiudi_finestra_app (Windows): lancia PowerShell senza finestra", cmd[0].lower().endswith("powershell.exe") and "System32" in cmd[0] and kw.get("creationflags") == 0x08000000, str(cmd[:1]))
verifica("... passa il profilo separato tramite variabile d'ambiente", kw["env"]["NT_PROFILO"] == str(tmp / "profilo_finestra"), str(kw.get("env", {}).get("NT_PROFILO")))
verifica("... filtra solo i processi del profilo e salva PowerShell stesso", "$env:NT_PROFILO" in cmd[-1] and "Contains($p)" in cmd[-1] and "-ne $PID" in cmd[-1], cmd[-1][:200])
verifica("... e non può restare appeso (timeout)", kw.get("timeout") == 20)

# ------------------------------------------------------------------------------------------
print("== avvio senza console (pythonw): testo su file")
vero_out, vero_err = sys.stdout, sys.stderr
try:
    sys.stdout = sys.stderr = None
    nt._USCITA_ORIGINALE["senza_console"] = False
    nt.prepara_uscita_testo()
    print("riga di prova stampata senza console")
    try:
        raise ValueError("errore di prova")
    except ValueError:
        import traceback
        traceback.print_exc()
    nt.mostra_errore("Titolo", "Testo dell'errore")
    uscita_ok = sys.stdout is not None and sys.stderr is not None
    sys.stdout.flush()
finally:
    sys.stdout, sys.stderr = vero_out, vero_err
log = nt.percorso_log().read_text(encoding="utf-8") if nt.percorso_log().exists() else ""
verifica("stdout/stderr non sono più None", uscita_ok)
verifica("il log contiene print, traceback e messaggio di errore",
         "riga di prova" in log and "ValueError: errore di prova" in log and "Testo dell'errore" in log, log[:300])
verifica("il log ha l'intestazione di avvio", "avvio NeoTracker" in log)
nt._USCITA_ORIGINALE["senza_console"] = False
# log troppo grande: viene ruotato
nt.percorso_log().write_text("x" * 600_000, encoding="utf-8")
try:
    sys.stdout = sys.stderr = None
    nt.prepara_uscita_testo()
    sys.stdout.flush()
finally:
    sys.stdout, sys.stderr = vero_out, vero_err
verifica("log troppo grande: ruotato in neotracker.vecchio.log", (tmp / "neotracker.vecchio.log").exists() and nt.percorso_log().stat().st_size < 10_000)
nt._USCITA_ORIGINALE["senza_console"] = False

print("== con console normale non cambia nulla")
prima = sys.stdout
nt.prepara_uscita_testo()
verifica("sys.stdout invariato se esiste", sys.stdout is prima)

print(f"\nRISULTATO: {ok_n} ok, {fail_n} falliti")
sys.exit(1 if fail_n else 0)
