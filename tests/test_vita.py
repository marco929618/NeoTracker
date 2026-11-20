# Live test of the life cycle: neotracker.py is started the way the icon would, the page is opened in a
# real Chrome (without a screen), reloaded, closed, and we check that the program shuts itself down.
# The "app browser" is fake (it only records how it is called) because there is no screen here.
# Usage: python3 test_vita.py        (about 1-2 minutes)
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

# copy of the program with a different port (so it does not disturb a real NeoTracker)
programma = tmp / "neotracker.py"
testo = (radice / "neotracker.py").read_text(encoding="utf-8")
assert "PORTA = 8750" in testo
programma.write_text(testo.replace("PORTA = 8750", f"PORTA = {PORTA}"), encoding="utf-8")

# The start-up notice ("not a medical device") is already accepted: here the life cycle is tested, not the notice
# (which has its own test in e2e.py).
dati.mkdir(parents=True, exist_ok=True)
(dati / "impostazioni.json").write_text(json.dumps({"avvertenze_accettate": "1", "lingua": "en"}), encoding="utf-8")

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
    """Launches neotracker.py as the icon does. With extra_codice it simulates a start without a console (empty stdout)."""
    if extra_codice:
        cmd = [sys.executable, "-c", extra_codice.replace("PERCORSO", str(programma))]
    else:
        cmd = [sys.executable, str(programma)]
    return subprocess.Popen(cmd, env=env, cwd=str(tmp), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def chiamate_browser():
    return registro.read_text().strip().splitlines() if registro.exists() else []


def token():
    """The session key of the running program (read from the file, as a second clicked icon does)."""
    try:
        return (dati / "sessione.token").read_text().strip()
    except OSError:
        return ""


def nuovo_contesto(chrome):
    """A clean browser that already owns the session cookie (for the pages that do not test the delivery of the key)."""
    c = chrome.new_context(locale="en-US")
    c.add_cookies([{"name": "nt_sessione", "value": token(), "url": URL}])
    return c


# The test browser speaks English: with the "automatic" language the interface follows the browser, and English texts are
# looked for here.
with sync_playwright() as pw:
    chrome = pw.chromium.launch(executable_path=os.environ.get("NEOTRACKER_TEST_CHROME", "/usr/bin/google-chrome"), args=["--no-sandbox"])

    # ---------------------------------------------------------------------------------------
    print("== 1. start, window opening, reload, closing")
    p = avvia_programma()
    verifica("the program starts and answers", attendi(lambda: ping() is not None, 15))
    verifica("at start-up it asks the browser to open the app window",
             attendi(lambda: any(f"--app={URL}/" in r for r in chiamate_browser()), 5), str(chiamate_browser()))
    r = chiamate_browser()[0] if chiamate_browser() else ""
    verifica("... with a separate profile inside the data folder", "profilo_finestra" in r and "--user-data-dir=" in r, r)
    verifica("without pages the ping says finestra_aperta false", ping()["finestra_aperta"] is False)

    verifica("the file with the session key exists (0600)", len(token()) >= 40 and
             (os.name == "nt" or stat.S_IMODE((dati / "sessione.token").stat().st_mode) == 0o600))
    verifica("the window is opened with the address ...?avvio=KEY", f"--app={URL}/?avvio={token()}" in r, r)
    chiave_primo_avvio = token()
    ctx = chrome.new_context(locale="en-US")
    pagina = ctx.new_page()
    errori = []
    pagina.on("pageerror", lambda e: errori.append(str(e)))
    pagina.on("console", lambda m: errori.append(m.text) if m.type == "error" else None)
    pagina.goto(r.split("--app=")[1].split(" ")[0])           # exactly the address the real window would receive
    verifica("after delivery the address is cleaned (no key in the address bar)", pagina.url == URL + "/", pagina.url)
    ck = [c for c in ctx.cookies() if c["name"] == "nt_sessione"]
    verifica("HttpOnly + SameSite=Strict session cookie", len(ck) == 1 and ck[0]["httpOnly"] and ck[0]["sameSite"] == "Strict", str(ck))
    verifica("the page JavaScript does NOT see the cookie", "nt_sessione" not in pagina.evaluate("document.cookie"))
    anonimo = chrome.new_context(locale="en-US")
    pa = anonimo.new_page()
    risp = pa.goto(URL + "/")
    verifica("a second browser without the key gets 403 and does not see the app", risp.status == 403 and "Access denied" in pa.content() and pa.title() != "NeoTracker")
    anonimo.close()
    verifica("the page sends the heartbeat: finestra_aperta true", attendi(lambda: ping()["finestra_aperta"] is True, 8))
    titolo = pagina.title()
    verifica("window title = NeoTracker", titolo == "NeoTracker", titolo)
    icona = pagina.evaluate("document.querySelector('link[rel=icon]').getAttribute('href')")
    verifica("PNG favicon linked", icona == "/icona.png", str(icona))
    with urllib.request.urlopen(urllib.request.Request(URL + "/icona.png", headers={"Cookie": f"nt_sessione={token()}"})) as ri:
        corpo = ri.read()
        verifica("/icona.png served as a 256x256 PNG", ri.headers["Content-Type"] == "image/png" and corpo[:8] == b"\x89PNG\r\n\x1a\n"
                 and int.from_bytes(corpo[16:20], "big") == 256 and int.from_bytes(corpo[20:24], "big") == 256)

    n_prima = len(chiamate_browser())
    p2 = avvia_programma()                                    # second press of the icon
    verifica("the second copy exits immediately without opening a second server", attendi(lambda: p2.poll() is not None, 10))
    verifica("the second copy ends with code 0", p2.returncode == 0, str(p2.returncode))
    out2 = p2.stdout.read()
    verifica("the second copy says so clearly", "already" in out2, out2[:200])
    verifica("the first program is still alive", p.poll() is None and ping() is not None)
    # on Linux the window cannot be "brought to the front": a new window request is therefore expected
    verifica("on Linux (no focus) the second copy asks for a window", attendi(lambda: len(chiamate_browser()) > n_prima, 5))
    verifica("... and it does so presenting the key of the program already running", f"?avvio={chiave_primo_avvio}" in chiamate_browser()[-1], chiamate_browser()[-1][-80:])

    pagina.reload()
    time.sleep(1)
    verifica("after F5 the program is still alive (even after the grace time)", not attendi(lambda: p.poll() is not None, 9) and ping() is not None)
    verifica("... and the window is still shown as open", ping()["finestra_aperta"] is True)

    # navigation inside the app (section change): it must not shut anything down
    pagina.goto(URL + "/#/impostazioni")
    time.sleep(1)
    verifica("section change: program alive", p.poll() is None)

    # second window opened at the same time: closing one does not shut down
    pagina_b = ctx.new_page()
    pagina_b.goto(URL + "/")
    time.sleep(1.5)
    pagina_b.close()
    verifica("two windows: closing the second does not shut the program down", not attendi(lambda: p.poll() is not None, 9) and ping()["finestra_aperta"] is True)

    t0 = time.time()
    pagina.close()                                           # CLOSING THE WINDOW
    chiuso = attendi(lambda: p.poll() is not None, 20)
    durata = time.time() - t0
    verifica("closing the window shuts the program down by itself", chiuso)
    verifica("... within about ten seconds (grace + check)", durata < 12, f"{durata:.1f}s")
    verifica("... with exit code 0", p.returncode == 0, str(p.returncode))
    out = p.stdout.read()
    verifica("the exit message is clear", "The NeoTracker window was closed" in out and "See you soon" in out, out[-300:])
    verifica("the session key is not printed in the program output", chiave_primo_avvio not in out)
    verifica("at shutdown the key file is deleted", not (dati / "sessione.token").exists())
    verifica("no JavaScript error during the test", not errori, str(errori))
    ctx.close()

    # ---------------------------------------------------------------------------------------
    print("== 1b. window closed without 'goodbye' and without heartbeats (browser killed/blocked): the presence connection counts")
    p = avvia_programma()
    attendi(lambda: ping() is not None, 15)
    ctx = nuovo_contesto(chrome)
    pagina = ctx.new_page()
    # Remove every "manual" signal from the page (heartbeats and goodbye): only the presence connection is
    # left.
    pagina.add_init_script("""
        const f = window.fetch.bind(window);
        window.fetch = (u, o) => (String(u).startsWith('/api/battito') || String(u).startsWith('/api/addio'))
            ? Promise.resolve(new Response('{}')) : f(u, o);
    """)
    pagina.goto(URL + "/")
    verifica("1b: the presence is enough for the window to count as open", attendi(lambda: ping()["finestra_aperta"] is True, 8))
    time.sleep(3)
    verifica("1b: as long as the page is open the program stays on", p.poll() is None)
    t0 = time.time()
    pagina.close()
    verifica("1b: once the page is closed the program shuts down anyway", attendi(lambda: p.poll() is not None, 20))
    verifica("1b: ... in a few seconds (not 3 minutes)", time.time() - t0 < 12, f"{time.time() - t0:.1f}s")
    p.stdout.read()
    ctx.close()

    # ---------------------------------------------------------------------------------------
    print("== 2. app Close NeoTracker button (closes immediately)")
    p = avvia_programma()
    attendi(lambda: ping() is not None, 15)
    ctx = nuovo_contesto(chrome)
    pagina = ctx.new_page()
    pagina.goto(URL + "/#/impostazioni")
    attendi(lambda: ping()["finestra_aperta"] is True, 8)
    pagina.get_by_role("button", name="Close NeoTracker").click()
    pagina.get_by_role("button", name="Close the program").click()
    verifica("Close: the program shuts down", attendi(lambda: p.poll() is not None, 10))
    verifica("Close: the page shows 'NeoTracker is closed'", pagina.get_by_text("NeoTracker is closed").count() == 1)
    verifica("Close: exit code 0", p.returncode == 0, str(p.returncode))
    ctx.close()

    # ---------------------------------------------------------------------------------------
    print("== 3. window never appeared / page blocked (seconds shortened via code)")
    # no window: the program keeps waiting (it does not shut down within a few seconds) and can be closed with
    # Ctrl+C
    p = avvia_programma()
    attendi(lambda: ping() is not None, 15)
    verifica("no window: the program does not shut down at once", not attendi(lambda: p.poll() is not None, 8))
    p.send_signal(2)                                          # Ctrl+C
    verifica("Ctrl+C shuts it down in an orderly way", attendi(lambda: p.poll() is not None, 10))
    verifica("... with a closing message", "See you soon" in p.stdout.read())

    # ---------------------------------------------------------------------------------------
    print("== 4. start without a console (like pythonw): everything goes to the log file")
    for f in (dati / "neotracker.log",):
        if f.exists():
            f.unlink()
    codice = ("import sys, runpy\n"
              "sys.stdout = None\nsys.stderr = None\n"            # like pythonw.exe: no screen
              "runpy.run_path('PERCORSO', run_name='__main__')\n")
    p = avvia_programma(codice)
    verifica("without a console the program starts anyway", attendi(lambda: ping() is not None, 15))
    ctx = nuovo_contesto(chrome)
    pagina = ctx.new_page()
    pagina.goto(URL + "/")
    attendi(lambda: ping()["finestra_aperta"] is True, 8)
    pagina.close()
    verifica("without a console: it shuts down when the window is closed", attendi(lambda: p.poll() is not None, 20))
    verifica("without a console: exit code 0", p.returncode == 0, str(p.returncode))
    log = (dati / "neotracker.log").read_text(encoding="utf-8") if (dati / "neotracker.log").exists() else ""
    verifica("the neotracker.log file tells what happened", "starting" in log and "is running" in log and "See you soon" in log, log[-400:])
    verifica("no traceback in the log", "Traceback" not in log, log[-400:])
    ctx.close()

    # ---------------------------------------------------------------------------------------
    print("== 5. port already used by another program")
    import socket
    occupa = socket.socket()
    occupa.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)   # only needed because the port has just been used
    occupa.bind(("127.0.0.1", PORTA))
    occupa.listen(1)
    p = avvia_programma()
    verifica("port in use: it exits with a clear message", attendi(lambda: p.poll() is not None, 10))
    verifica("... that talks about the port", "port" in p.stdout.read())
    occupa.close()

    chrome.close()

shutil.rmtree(tmp, ignore_errors=True)
print(f"\nRESULT: {ok_n} ok, {fail_n} failed")
sys.exit(1 if fail_n else 0)
