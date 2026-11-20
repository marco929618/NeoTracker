# Test of the whole app in the browser (Chrome without a window) with mock services. Usage: python3 e2e.py
import importlib.util
import io
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import mock_servizi as mock
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

PORTA_MOCK, PORTA_APP = 8798, 8752
OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)
tmp = Path(tempfile.mkdtemp(prefix="neo_e2e_"))
mock.avvia(PORTA_MOCK)
base = f"http://127.0.0.1:{PORTA_MOCK}"
os.environ.update(NEOTRACKER_OWM_BASE=base, NEOTRACKER_OPENMETEO_BASE=base, NEOTRACKER_GEOCODE_BASE=base,
                  NEOTRACKER_IP_BASE=base, NEOTRACKER_EUTILS_BASE=base + "/entrez/eutils/")
spec = importlib.util.spec_from_file_location("neotracker", Path(__file__).parent.parent / "neotracker.py")
nt = importlib.util.module_from_spec(spec)
sys.modules["neotracker"] = nt
spec.loader.exec_module(nt)
nt.CARTELLA_DATI = tmp
nt.PORTA = PORTA_APP
# Folder of the analysis projects: if it is not given (NEOTRACKER_TEST_REPOS) the methods count as "not installed"
# and the tests that need a real analysis are skipped.
ANALISI = bool(os.environ.get("NEOTRACKER_TEST_REPOS"))
nt.CARTELLA_REPO = Path(os.environ.get("NEOTRACKER_TEST_REPOS") or (tmp / "senza_progetti"))
nt.CARTELLA_SCRIPT = Path(__file__).resolve().parent.parent          # melanoma_batch.py is here
nt.inizializza_db()
srv = nt.Server(("127.0.0.1", PORTA_APP), nt.Gestore)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{PORTA_APP}"

# fake photo of a mole
img = Image.new("RGB", (900, 700), (226, 184, 160))
d = ImageDraw.Draw(img)
d.ellipse((330, 230, 580, 440), fill=(92, 56, 38))
d.ellipse((400, 280, 520, 380), fill=(60, 34, 24))
img.save(tmp / "mole1.jpg", quality=92)
img2 = img.copy()
ImageDraw.Draw(img2).ellipse((340, 220, 600, 450), outline=(70, 40, 30), width=6)
img2.save(tmp / "mole2.jpg", quality=92)

problemi = []
log = []


def attendi(pagina, espressione, timeout=60):
    """Like wait_for_function, but without eval (the page has a strict security policy)."""
    fine = time.time() + timeout
    while time.time() < fine:
        if pagina.evaluate(espressione):
            return True
        time.sleep(0.4)
    raise TimeoutError(espressione)


def passo(nome, ok, extra=""):
    print(("  ok   " if ok else "  FAIL ") + nome + (" -> " + extra if (extra and not ok) else ""))
    if not ok:
        problemi.append(nome)


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("NEOTRACKER_TEST_CHROME", "/usr/bin/google-chrome"), args=["--no-sandbox"])
    ctx = b.new_context(viewport={"width": 1366, "height": 860}, permissions=["geolocation"], geolocation={"latitude": 45.07, "longitude": 7.69},
                      locale="en-US")      # automatic language = the browser one: the tests check the English texts
    pg = ctx.new_page()
    pg.on("console", lambda m: log.append(m.type + ": " + m.text) if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: log.append("PAGEERROR: " + str(e)))
    pg.on("requestfailed", lambda r: log.append("REQFAIL: " + r.url))
    pg.on("response", lambda r: log.append(f"HTTP {r.status}: {r.url}") if r.status >= 400 and "/analisi" not in r.url else None)

    print("== access with the session key and start-up notice")
    pg.goto(URL + "/?avvio=" + nt.TOKEN_SESSIONE)                  # like the real window: the key travels only once
    pg.wait_for_selector("#dialogo[open] .avvertenze", timeout=8000)
    passo("address cleaned after the key delivery", "avvio=" not in pg.url and pg.url.split("#")[0] == URL + "/", pg.url)
    passo("the session cookie is not visible to JavaScript", "nt_sessione" not in pg.evaluate("document.cookie"))
    pg.screenshot(path=str(OUT / "00_notices.png"))
    passo("start-up notice shown at the first start", "is not a medical device" in pg.inner_text("#dialogo"))
    passo("'Accept' is disabled until the box is ticked", pg.get_by_role("button", name="Accept and continue").is_disabled())
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(300)
    passo("the Esc key does not skip the notice", pg.locator("#dialogo[open] .avvertenze").count() == 1)
    pg.locator("#ck-avvertenze").check()
    pg.get_by_role("button", name="Accept and continue").click()
    pg.wait_for_selector("#dialogo:not([open])", state="attached", timeout=5000)
    passo("accepting the notice saves the version", pg.evaluate("fetch('/api/impostazioni').then(r=>r.json())")["avvertenze_accettate"] == nt.AVVERTENZE_VERSIONE)
    pg.reload()
    pg.wait_for_selector(".utenti-griglia, .pagina", timeout=8000)
    pg.wait_for_timeout(500)
    passo("after reloading, the notice does not appear again", pg.locator("#dialogo[open]").count() == 0)

    print("== users")
    pg.screenshot(path=str(OUT / "01_users_empty.png"))
    pg.get_by_text("New user", exact=True).first.click()
    pg.wait_for_selector("#dialogo[open]")
    pg.fill("#dialogo input[type=text]", "Marta")
    pg.screenshot(path=str(OUT / "02_new_user.png"))
    pg.locator("#dialogo .btn-pri").click()
    pg.wait_for_selector(".profilo-layout", timeout=8000)
    passo("user created and profile opened", "#/profilo" in pg.url)

    print("== profile")
    pg.locator(".fototipo").nth(1).click()
    pg.get_by_role("button", name="Woman", exact=True).click()
    pg.fill("input[type=date]", "1985-04-12")
    pg.dispatch_event("input[type=date]", "change")
    pg.wait_for_timeout(1200)
    pg.screenshot(path=str(OUT / "03_profile.png"), full_page=True)
    r = pg.evaluate("fetch('/api/utenti/1').then(r=>r.json())")
    passo("profile saved (phototype 2, sex F)", r["profilo"]["fototipo"] == 2 and r["profilo"]["sesso"] == "F" and r["profilo"]["data_nascita"] == "1985-04-12", str(r["profilo"]))

    print("== personal picture of the user")
    Image.new("RGBA", (600, 300), (30, 120, 90, 255)).save(tmp / "avatar.png")
    ImageDraw.Draw(Image.open(tmp / "avatar.png")).rectangle((0, 0, 10, 10))
    passo("without a picture: the title shows the initial", pg.locator(".utente-chip .avatar-img").count() == 0 and pg.locator(".utente-chip .avatar").inner_text().strip() == "M")
    pg.set_input_files("section:has(.avatar-editor) input[type=file]", str(tmp / "avatar.png"))
    pg.wait_for_selector(".avatar-editor img.avatar-img", timeout=8000)
    pg.wait_for_selector(".utente-chip img.avatar-img", timeout=8000)
    passo("picture shown in the profile and in the header", True)
    info = pg.evaluate("fetch('/api/utenti/1/avatar').then(r => r.blob()).then(b => createImageBitmap(b)).then(i => [i.width, i.height])")
    passo("saved as a 256x256 square", info == [256, 256], str(info))
    passo("the picture is really visible (loaded, not broken)", pg.evaluate("document.querySelector('.utente-chip img.avatar-img').naturalWidth") == 256)
    pg.screenshot(path=str(OUT / "03b_profile_avatar.png"), full_page=True)
    pg.goto(URL + "/#/utenti")
    pg.wait_for_selector(".utente-card .avatar-img", timeout=8000)
    passo("the picture appears in the user choice", pg.locator(".utente-card .avatar-img").count() == 1)
    pg.screenshot(path=str(OUT / "03c_user_choice_avatar.png"))
    pg.goto(URL + "/#/profilo")
    pg.wait_for_selector(".avatar-editor")
    pg.get_by_role("button", name="Remove", exact=True).click()
    pg.wait_for_selector(".utente-chip .avatar-img", state="detached", timeout=8000)
    passo("removing the picture brings back the initial", pg.locator(".utente-chip .avatar").inner_text().strip() == "M")
    pg.set_input_files("section:has(.avatar-editor) input[type=file]", str(tmp / "mole1.jpg"))        # I put a picture back (a real photo)
    pg.wait_for_selector(".avatar-editor img.avatar-img", timeout=8000)
    pg.set_input_files("section:has(.avatar-editor) input[type=file]", {"name": "fake.png", "mimeType": "image/png", "buffer": b"I am not an image"})
    pg.wait_for_selector("#toast.visibile.errore", timeout=8000)
    passo("a file that is not an image is rejected with a message", True)
    passo("... and the previous picture stays", pg.locator(".avatar-editor img.avatar-img").count() == 1)

    print("== texts with HTML inside are not executed")
    xss = pg.evaluate("""fetch('/api/utenti', {method:'POST', headers:{'X-NeoTracker':'1','Content-Type':'application/json'},
                         body: JSON.stringify({nome: '<img src=x onerror="window.__xss=1">'})}).then(r => r.json())""")
    pg.goto(URL + "/#/utenti")
    pg.wait_for_selector(".utente-card")
    pg.wait_for_timeout(500)
    passo("the name with HTML appears as text", '<img src=x onerror="window.__xss=1">' in pg.inner_text(".utenti-griglia"))
    passo("... and it is not executed", pg.evaluate("window.__xss === undefined") and pg.locator(".utenti-griglia img[src='x']").count() == 0)
    pg.evaluate("id => fetch('/api/utenti/' + id, {method:'DELETE', headers:{'X-NeoTracker':'1','Content-Type':'application/json'}, body: JSON.stringify({conferma: '<img src=x onerror=\"window.__xss=1\">'})})", xss["id"])
    pg.goto(URL + "/#/profilo")
    pg.wait_for_selector(".profilo-layout")

    print("== map: add mole")
    pg.click("a.voce:has-text('Mole map')")
    pg.wait_for_selector(".mappa-box svg")
    pg.click("#btn-aggiungi")
    box = pg.locator(".mappa-box svg").bounding_box()
    pg.mouse.move(box["x"] + box["width"] * 0.30, box["y"] + box["height"] * 0.33)
    pg.wait_for_timeout(200)
    pg.screenshot(path=str(OUT / "04_map_add.png"))
    pg.mouse.click(box["x"] + box["width"] * 0.30, box["y"] + box["height"] * 0.33)
    pg.wait_for_selector(".pannello input[type=text]")
    pg.screenshot(path=str(OUT / "05_map_draft.png"))
    campi = pg.locator(".pannello input[type=text]")
    campi.first.fill("Shoulder mole")
    pg.locator(".pannello .btn-pri").first.click()
    pg.wait_for_selector(".neo-titolo, .marc:not(.bozza)", timeout=8000)
    pg.wait_for_timeout(500)
    passo("mole created", len(pg.evaluate("fetch('/api/utenti/1/nevi').then(r=>r.json())")) == 1)
    pg.screenshot(path=str(OUT / "06_mole_detail.png"), full_page=True)

    print("== photo + analysis")
    pg.set_input_files(".form-foto input[type=file]", str(tmp / "mole1.jpg"))
    pg.fill(".form-foto input[placeholder='e.g. 4.5']", "4.5")
    pg.locator(".form-foto .btn-pri").click()
    pg.wait_for_selector(".striscia .miniatura", timeout=15000)
    passo("photo saved", True)
    pg.screenshot(path=str(OUT / "07_photo_analysing.png"), full_page=True)
    ok = False
    for _ in range(90):
        st = pg.evaluate("fetch('/api/foto/1/analisi').then(r=>r.json())")
        if st["stato"] in ("ok", "errore"):
            ok = True
            break
        time.sleep(2)
    passo("analysis finished", ok, str(st)[:300] if ok else "timeout")
    pg.wait_for_timeout(3500)
    pg.screenshot(path=str(OUT / "08_analysis.png"), full_page=True)
    print("   analysis state:", st["stato"], st.get("messaggio", "")[:140])
    # second photo for the chart/comparison
    pg.set_input_files(".form-foto input[type=file]", str(tmp / "mole2.jpg")) if pg.locator(".form-foto input[type=file]").count() else None

    print("== literature")
    pg.click("a.voce:has-text('Literature')")
    pg.wait_for_selector(".azione-scan")
    pg.click(".azione-scan .btn-pri")
    attendi(pg, "document.querySelector('.azione-scan .piccolo.muted')?.textContent.includes('complete') || false")
    passo("literature scan", pg.locator(".articolo").count() > 3)
    pg.screenshot(path=str(OUT / "09_literature.png"), full_page=True)

    print("== genetics")
    pg.click("a.voce:has-text('Genetics')")
    pg.wait_for_selector(".tabella")
    pg.screenshot(path=str(OUT / "10_genetics.png"), full_page=True)
    pg.click(".tabella-scroll >> xpath=../.. >> .btn-pri") if False else pg.locator("section:has(.tabella) .btn-pri").click()
    attendi(pg, "document.querySelectorAll('.gene-conta').length >= 10")
    passo("gene scan", pg.locator(".gene-conta").count() >= 10)
    pg.screenshot(path=str(OUT / "11_genetics_scan.png"), full_page=True)

    print("== UV index")
    pg.click("a.voce:has-text('UV index')")
    pg.wait_for_selector(".uv-posizione")
    pg.screenshot(path=str(OUT / "12_uv_no_location.png"))
    pg.fill(".uv-risultato ~ * , input[aria-label='City name']", "Turin") if False else pg.fill("input[aria-label='City name']", "Turin")
    pg.keyboard.press("Enter")
    pg.wait_for_selector(".citta-voce")
    pg.click(".citta-voce")
    pg.wait_for_selector(".uv-verdetto", timeout=10000)
    pg.wait_for_timeout(400)
    pg.screenshot(path=str(OUT / "13_uv.png"), full_page=True)
    passo("UV shown", pg.locator(".grafico-uv rect").count() >= 10, str(pg.locator(".grafico-uv rect").count()))
    uv_testo = pg.locator(".grafico-uv").locator("xpath=..").inner_text()
    pg.click("button:has-text('Detect my location')")
    pg.wait_for_timeout(1500)
    imp = pg.evaluate("fetch('/api/impostazioni').then(r=>r.json())")
    passo("browser geolocation", "My location" in imp["localita"], imp["localita"])

    print("== settings")
    pg.click("a.voce:has-text('Settings')")
    pg.wait_for_selector(".stato-lista")
    passo("UV default: Open-Meteo source with attribution", "Open-Meteo" in uv_testo and "CC BY 4.0" in uv_testo, uv_testo[-200:])
    passo("settings: Open-Meteo selected, no key field", pg.locator("input[name='fonte-uv'][value='open-meteo']").is_checked()
          and pg.locator("input[aria-label='OpenWeather key']").count() == 0)
    pg.screenshot(path=str(OUT / "14a_default_settings.png"), full_page=True)
    pg.click("input[name='fonte-uv'][value='openweather']")
    pg.wait_for_selector("input[aria-label='OpenWeather key']")
    pg.fill("input[aria-label='OpenWeather key']", mock.CHIAVE_V4)
    pg.click("button:has-text('Save') >> nth=0")
    pg.wait_for_selector("button:has-text('Test the key')")
    pg.click("button:has-text('Test the key')")
    pg.wait_for_selector(".prova-esito .banda")
    passo("OpenWeather 4.0 key test", "It works" in pg.locator(".prova-esito .banda").inner_text(), pg.locator(".prova-esito .banda").inner_text())
    pg.screenshot(path=str(OUT / "14_settings.png"), full_page=True)
    pg.click("a.voce:has-text('UV index')")
    pg.wait_for_selector(".uv-verdetto")
    pg.wait_for_timeout(400)
    passo("UV after the key uses OpenWeather", "OpenWeather" in pg.locator(".grafico-uv").locator("xpath=..").inner_text())

    print("== print")
    pg.evaluate("window.print = () => { window.__stampato = true; }")
    pg.click("a.voce:has-text('Mole map')")
    pg.wait_for_selector(".mappa-box svg")
    pg.get_by_role("button", name="Sheet for the dermatologist").click()
    attendi(pg, "window.__stampato === true", 15)
    pg.emulate_media(media="print")
    pg.wait_for_timeout(300)
    pg.screenshot(path=str(OUT / "15_print.png"), full_page=True)
    passo("printable sheet created", pg.locator("#stampa .st-neo").count() == 1)
    pg.emulate_media(media="screen")

    print("== narrow screen")
    pg.set_viewport_size({"width": 420, "height": 860})
    pg.goto(URL + "/#/mappa")
    pg.wait_for_selector(".mappa-box svg")
    pg.screenshot(path=str(OUT / "16_narrow.png"))

    b.close()

print("\n== browser messages")
for m in log:
    print("  ", m)
print("\nPROBLEMS:", problemi or "none")
srv.shutdown()
