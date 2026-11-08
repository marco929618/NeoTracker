# Prova "dal vivo" del ciclo di vita: si avvia neotracker.py come farebbe l'icona, si apre la pagina in un
# Chrome vero (senza schermo), si ricarica, si chiude, e si controlla che il programma si spenga da solo.
# Il "browser dell'app" è finto (registra solo come viene chiamato) perché qui non c'è uno schermo.
# Uso: python3 test_vita.py        (circa 1-2 minuti)
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

PORTA = 8761
radice = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp(prefix="neo_vita_"))
casa = tmp / "casa"
casa.mkdir()
dati = casa / "melanoma-repos" / "NeoTracker_dati"

# copia del programma con una porta diversa (così non disturba un NeoTracker vero)
programma = tmp / "neotracker.py"
testo = (radice / "neotracker.py").read_text(encoding="utf-8")
assert "PORTA = 8750" in testo
programma.write_text(testo.replace("PORTA = 8750", f"PORTA = {PORTA}"), encoding="utf-8")

# L'avviso iniziale ("non è un dispositivo medico") è già accettato: qui si prova il ciclo di vita, non l'avviso
# (che ha la sua prova in e2e.py).
dati.mkdir(parents=True, exist_ok=True)
(dati / "impostazioni.json").write_text(json.dumps({"avvertenze_accettate": "1"}), encoding="utf-8")

registro = tmp / "browser_chiamato.txt"
finto = tmp / "finto_browser.sh"
finto.write_text(f'#!/bin/sh\necho "$@" >> "{registro}"\n')
finto.chmod(finto.stat().st_mode | stat.S_IEXEC)
env = dict(os.environ, HOME=str(casa), NEOTRACKER_BROWSER=str(finto), PYTHONUNBUFFERED="1")
URL = f"http://127.0.0.1:{PORTA}"
ok_n = fail_n = 0


def verifica(nome, condizione, extra=""):
    global ok_n, fail_n
    if condizione:
        ok_n += 1
        print(f"  ok   {nome}")
    else:
        fail_n += 1
        print(f"  FAIL {nome} {extra}")


def ping():
    try:
        with urllib.request.urlopen(URL + "/api/ping", timeout=2) as r:
            return json.loads(r.read())
    except Exception:
        return None


def attendi(cond, secondi, passo=0.2):
    fine = time.time() + secondi
    while time.time() < fine:
        if cond():
            return True
        time.sleep(passo)
    return False


def avvia_programma(extra_codice=None):
    """Lancia neotracker.py come fa l'icona. Con extra_codice simula l'avvio senza console (stdout vuoto)."""
    if extra_codice:
        cmd = [sys.executable, "-c", extra_codice.replace("PERCORSO", str(programma))]
    else:
        cmd = [sys.executable, str(programma)]
    return subprocess.Popen(cmd, env=env, cwd=str(tmp), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def chiamate_browser():
    return registro.read_text().strip().splitlines() if registro.exists() else []


def token():
    """La chiave di sessione del programma acceso (la legge dal file, come fa una seconda icona cliccata)."""
    try:
        return (dati / "sessione.token").read_text().strip()
    except OSError:
        return ""


def nuovo_contesto(chrome):
    """Un browser pulito che già possiede il cookie di sessione (per le pagine che non provano la consegna della chiave)."""
    c = chrome.new_context()
    c.add_cookies([{"name": "nt_sessione", "value": token(), "url": URL}])
    return c


with sync_playwright() as pw:
    chrome = pw.chromium.launch(executable_path=os.environ.get("NEOTRACKER_TEST_CHROME", "/usr/bin/google-chrome"), args=["--no-sandbox"])

    # ---------------------------------------------------------------------------------------
    print("== 1. avvio, apertura finestra, ricaricamento, chiusura")
    p = avvia_programma()
    verifica("il programma parte e risponde", attendi(lambda: ping() is not None, 15))
    verifica("all'avvio chiede al browser di aprire la finestra app",
             attendi(lambda: any(f"--app={URL}/" in r for r in chiamate_browser()), 5), str(chiamate_browser()))
    r = chiamate_browser()[0] if chiamate_browser() else ""
    verifica("... con profilo separato dentro i dati", "profilo_finestra" in r and "--user-data-dir=" in r, r)
    verifica("senza pagine il ping dice finestra_aperta falso", ping()["finestra_aperta"] is False)

    verifica("il file con la chiave di sessione esiste (0600)", len(token()) >= 40 and
             (os.name == "nt" or stat.S_IMODE((dati / "sessione.token").stat().st_mode) == 0o600))
    verifica("la finestra viene aperta con l'indirizzo ...?avvio=CHIAVE", f"--app={URL}/?avvio={token()}" in r, r)
    chiave_primo_avvio = token()
    ctx = chrome.new_context()
    pagina = ctx.new_page()
    errori = []
    pagina.on("pageerror", lambda e: errori.append(str(e)))
    pagina.on("console", lambda m: errori.append(m.text) if m.type == "error" else None)
    pagina.goto(r.split("--app=")[1].split(" ")[0])           # esattamente l'indirizzo che riceverebbe la finestra vera
    verifica("dopo la consegna l'indirizzo è ripulito (niente chiave nella barra)", pagina.url == URL + "/", pagina.url)
    ck = [c for c in ctx.cookies() if c["name"] == "nt_sessione"]
    verifica("cookie di sessione HttpOnly + SameSite=Strict", len(ck) == 1 and ck[0]["httpOnly"] and ck[0]["sameSite"] == "Strict", str(ck))
    verifica("il JavaScript della pagina NON vede il cookie", "nt_sessione" not in pagina.evaluate("document.cookie"))
    anonimo = chrome.new_context()
    pa = anonimo.new_page()
    risp = pa.goto(URL + "/")
    verifica("un secondo browser senza chiave riceve 403 e non vede l'app", risp.status == 403 and "Accesso non autorizzato" in pa.content() and pa.title() != "NeoTracker")
    anonimo.close()
    verifica("la pagina manda il battito: finestra_aperta vero", attendi(lambda: ping()["finestra_aperta"] is True, 8))
    titolo = pagina.title()
    verifica("titolo della finestra = NeoTracker", titolo == "NeoTracker", titolo)
    icona = pagina.evaluate("document.querySelector('link[rel=icon]').getAttribute('href')")
    verifica("favicon PNG collegata", icona == "/icona.png", str(icona))
    with urllib.request.urlopen(urllib.request.Request(URL + "/icona.png", headers={"Cookie": f"nt_sessione={token()}"})) as ri:
        corpo = ri.read()
        verifica("/icona.png servita come PNG 256x256", ri.headers["Content-Type"] == "image/png" and corpo[:8] == b"\x89PNG\r\n\x1a\n"
                 and int.from_bytes(corpo[16:20], "big") == 256 and int.from_bytes(corpo[20:24], "big") == 256)

    n_prima = len(chiamate_browser())
    p2 = avvia_programma()                                    # seconda pressione dell'icona
    verifica("la seconda copia esce subito senza aprire un secondo server", attendi(lambda: p2.poll() is not None, 10))
    verifica("la seconda copia termina con codice 0", p2.returncode == 0, str(p2.returncode))
    out2 = p2.stdout.read()
    verifica("la seconda copia lo dice in chiaro", "già" in out2, out2[:200])
    verifica("il primo programma è ancora vivo", p.poll() is None and ping() is not None)
    # su Linux non si può "portare in primo piano": ci si aspetta quindi una nuova richiesta di finestra
    verifica("su Linux (niente focus) la seconda copia chiede una finestra", attendi(lambda: len(chiamate_browser()) > n_prima, 5))
    verifica("... e lo fa presentando la chiave del programma già acceso", f"?avvio={chiave_primo_avvio}" in chiamate_browser()[-1], chiamate_browser()[-1][-80:])

    pagina.reload()
    time.sleep(1)
    verifica("dopo F5 il programma è ancora vivo (anche passato il tempo di grazia)", not attendi(lambda: p.poll() is not None, 9) and ping() is not None)
    verifica("... e la finestra risulta ancora aperta", ping()["finestra_aperta"] is True)

    # navigazione dentro l'app (cambio sezione): non deve spegnere nulla
    pagina.goto(URL + "/#/impostazioni")
    time.sleep(1)
    verifica("cambio sezione: programma vivo", p.poll() is None)

    # seconda finestra aperta insieme: chiuderne una non spegne
    pagina_b = ctx.new_page()
    pagina_b.goto(URL + "/")
    time.sleep(1.5)
    pagina_b.close()
    verifica("due finestre: chiudere la seconda non spegne il programma", not attendi(lambda: p.poll() is not None, 9) and ping()["finestra_aperta"] is True)

    t0 = time.time()
    pagina.close()                                           # CHIUSURA DELLA FINESTRA
    chiuso = attendi(lambda: p.poll() is not None, 20)
    durata = time.time() - t0
    verifica("chiudendo la finestra il programma si spegne da solo", chiuso)
    verifica("... entro una decina di secondi (grazia + controllo)", durata < 12, f"{durata:.1f}s")
    verifica("... con codice di uscita 0", p.returncode == 0, str(p.returncode))
    out = p.stdout.read()
    verifica("il messaggio d'uscita è chiaro", "finestra di NeoTracker è stata chiusa" in out and "A presto" in out, out[-300:])
    verifica("la chiave di sessione non viene stampata nel testo del programma", chiave_primo_avvio not in out)
    verifica("allo spegnimento il file della chiave viene cancellato", not (dati / "sessione.token").exists())
    verifica("nessun errore JavaScript durante la prova", not errori, str(errori))
    ctx.close()

    # ---------------------------------------------------------------------------------------
    print("== 1b. finestra chiusa senza 'addio' e senza battiti (browser ucciso/bloccato): conta la connessione di presenza")
    p = avvia_programma()
    attendi(lambda: ping() is not None, 15)
    ctx = nuovo_contesto(chrome)
    pagina = ctx.new_page()
    # Tolgo alla pagina ogni segnale "a mano" (battiti e addio): resta solo la connessione di presenza.
    pagina.add_init_script("""
        const f = window.fetch.bind(window);
        window.fetch = (u, o) => (String(u).startsWith('/api/battito') || String(u).startsWith('/api/addio'))
            ? Promise.resolve(new Response('{}')) : f(u, o);
    """)
    pagina.goto(URL + "/")
    verifica("1b: la presenza basta a far risultare la finestra aperta", attendi(lambda: ping()["finestra_aperta"] is True, 8))
    time.sleep(3)
    verifica("1b: finché la pagina è aperta il programma resta acceso", p.poll() is None)
    t0 = time.time()
    pagina.close()
    verifica("1b: chiusa la pagina il programma si spegne comunque", attendi(lambda: p.poll() is not None, 20))
    verifica("1b: ... in pochi secondi (non 3 minuti)", time.time() - t0 < 12, f"{time.time() - t0:.1f}s")
    p.stdout.read()
    ctx.close()

    # ---------------------------------------------------------------------------------------
    print("== 2. pulsante Esci dell'app (chiude subito)")
    p = avvia_programma()
    attendi(lambda: ping() is not None, 15)
    ctx = nuovo_contesto(chrome)
    pagina = ctx.new_page()
    pagina.goto(URL + "/#/impostazioni")
    attendi(lambda: ping()["finestra_aperta"] is True, 8)
    pagina.get_by_role("button", name="Chiudi NeoTracker").click()
    pagina.get_by_role("button", name="Chiudi il programma").click()
    verifica("Esci: il programma si spegne", attendi(lambda: p.poll() is not None, 10))
    verifica("Esci: la pagina mostra 'NeoTracker è chiuso'", pagina.get_by_text("NeoTracker è chiuso").count() == 1)
    verifica("Esci: codice di uscita 0", p.returncode == 0, str(p.returncode))
    ctx.close()

    # ---------------------------------------------------------------------------------------
    print("== 3. finestra mai comparsa / pagina bloccata (secondi accorciati via codice)")
    # niente finestra: il programma resta in attesa (non si spegne in pochi secondi) e si può chiudere con Ctrl+C
    p = avvia_programma()
    attendi(lambda: ping() is not None, 15)
    verifica("nessuna finestra: il programma non si spegne subito", not attendi(lambda: p.poll() is not None, 8))
    p.send_signal(2)                                          # Ctrl+C
    verifica("Ctrl+C lo spegne ordinatamente", attendi(lambda: p.poll() is not None, 10))
    verifica("... con messaggio di chiusura", "A presto" in p.stdout.read())

    # ---------------------------------------------------------------------------------------
    print("== 4. avvio senza console (come pythonw): tutto va nel file di log")
    for f in (dati / "neotracker.log",):
        if f.exists():
            f.unlink()
    codice = ("import sys, runpy\n"
              "sys.stdout = None\nsys.stderr = None\n"            # come pythonw.exe: nessuno schermo
              "runpy.run_path('PERCORSO', run_name='__main__')\n")
    p = avvia_programma(codice)
    verifica("senza console il programma parte lo stesso", attendi(lambda: ping() is not None, 15))
    ctx = nuovo_contesto(chrome)
    pagina = ctx.new_page()
    pagina.goto(URL + "/")
    attendi(lambda: ping()["finestra_aperta"] is True, 8)
    pagina.close()
    verifica("senza console: si spegne alla chiusura della finestra", attendi(lambda: p.poll() is not None, 20))
    verifica("senza console: codice di uscita 0", p.returncode == 0, str(p.returncode))
    log = (dati / "neotracker.log").read_text(encoding="utf-8") if (dati / "neotracker.log").exists() else ""
    verifica("il file neotracker.log racconta cosa è successo", "avvio NeoTracker" in log and "è attivo" in log and "A presto" in log, log[-400:])
    verifica("niente traceback nel log", "Traceback" not in log, log[-400:])
    ctx.close()

    # ---------------------------------------------------------------------------------------
    print("== 5. porta già occupata da un altro programma")
    import socket
    occupa = socket.socket()
    occupa.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)   # serve solo perché la porta è appena stata usata
    occupa.bind(("127.0.0.1", PORTA))
    occupa.listen(1)
    p = avvia_programma()
    verifica("porta occupata: esce con un messaggio chiaro", attendi(lambda: p.poll() is not None, 10))
    verifica("... che parla della porta", "porta" in p.stdout.read())
    occupa.close()

    chrome.close()

shutil.rmtree(tmp, ignore_errors=True)
print(f"\nRISULTATO: {ok_n} ok, {fail_n} falliti")
sys.exit(1 if fail_n else 0)
