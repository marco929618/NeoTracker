# Prova di tutta l'app nel browser (Chrome senza finestra) con servizi finti. Uso: python3 e2e.py
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
# Cartella dei progetti di analisi: se non è indicata (NEOTRACKER_TEST_REPOS) i metodi risultano "non installati"
# e le prove che richiedono un'analisi vera vengono saltate.
ANALISI = bool(os.environ.get("NEOTRACKER_TEST_REPOS"))
nt.CARTELLA_REPO = Path(os.environ.get("NEOTRACKER_TEST_REPOS") or (tmp / "senza_progetti"))
nt.CARTELLA_SCRIPT = Path(__file__).resolve().parent.parent          # qui sta melanoma_batch.py
nt.inizializza_db()
srv = nt.Server(("127.0.0.1", PORTA_APP), nt.Gestore)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{PORTA_APP}"

# foto finta di un neo
img = Image.new("RGB", (900, 700), (226, 184, 160))
d = ImageDraw.Draw(img)
d.ellipse((330, 230, 580, 440), fill=(92, 56, 38))
d.ellipse((400, 280, 520, 380), fill=(60, 34, 24))
img.save(tmp / "neo1.jpg", quality=92)
img2 = img.copy()
ImageDraw.Draw(img2).ellipse((340, 220, 600, 450), outline=(70, 40, 30), width=6)
img2.save(tmp / "neo2.jpg", quality=92)

problemi = []
log = []


def attendi(pagina, espressione, timeout=60):
    """Come wait_for_function, ma senza eval (la pagina ha una politica di sicurezza rigida)."""
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
    ctx = b.new_context(viewport={"width": 1366, "height": 860}, permissions=["geolocation"], geolocation={"latitude": 45.07, "longitude": 7.69})
    pg = ctx.new_page()
    pg.on("console", lambda m: log.append(m.type + ": " + m.text) if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: log.append("PAGEERROR: " + str(e)))
    pg.on("requestfailed", lambda r: log.append("REQFAIL: " + r.url))
    pg.on("response", lambda r: log.append(f"HTTP {r.status}: {r.url}") if r.status >= 400 and "/analisi" not in r.url else None)

    print("== accesso con la chiave di sessione e avviso iniziale")
    pg.goto(URL + "/?avvio=" + nt.TOKEN_SESSIONE)                  # come la finestra vera: la chiave viaggia una volta sola
    pg.wait_for_selector("#dialogo[open] .avvertenze", timeout=8000)
    passo("indirizzo ripulito dopo la consegna della chiave", "avvio=" not in pg.url and pg.url.split("#")[0] == URL + "/", pg.url)
    passo("il cookie di sessione non è visibile al JavaScript", "nt_sessione" not in pg.evaluate("document.cookie"))
    pg.screenshot(path=str(OUT / "00_avvertenze.png"))
    passo("avviso iniziale mostrato al primo avvio", "non è un dispositivo medico" in pg.inner_text("#dialogo"))
    passo("'Accetto' è disattivato finché non si spunta", pg.get_by_role("button", name="Accetto e continuo").is_disabled())
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(300)
    passo("il tasto Esc non salta l'avviso", pg.locator("#dialogo[open] .avvertenze").count() == 1)
    pg.locator("#ck-avvertenze").check()
    pg.get_by_role("button", name="Accetto e continuo").click()
    pg.wait_for_selector("#dialogo:not([open])", state="attached", timeout=5000)
    passo("accettando l'avviso si salva la versione", pg.evaluate("fetch('/api/impostazioni').then(r=>r.json())")["avvertenze_accettate"] == nt.AVVERTENZE_VERSIONE)
    pg.reload()
    pg.wait_for_selector(".utenti-griglia, .pagina", timeout=8000)
    pg.wait_for_timeout(500)
    passo("ricaricando, l'avviso non riappare", pg.locator("#dialogo[open]").count() == 0)

    print("== utenti")
    pg.screenshot(path=str(OUT / "01_utenti_vuoto.png"))
    pg.get_by_text("Nuovo utente", exact=True).first.click()
    pg.wait_for_selector("#dialogo[open]")
    pg.fill("#dialogo input[type=text]", "Marta")
    pg.screenshot(path=str(OUT / "02_nuovo_utente.png"))
    pg.locator("#dialogo .btn-pri").click()
    pg.wait_for_selector(".profilo-layout", timeout=8000)
    passo("utente creato e profilo aperto", "#/profilo" in pg.url)

    print("== profilo")
    pg.locator(".fototipo").nth(1).click()
    pg.get_by_role("button", name="Donna", exact=True).click()
    pg.fill("input[type=date]", "1985-04-12")
    pg.dispatch_event("input[type=date]", "change")
    pg.wait_for_timeout(1200)
    pg.screenshot(path=str(OUT / "03_profilo.png"), full_page=True)
    r = pg.evaluate("fetch('/api/utenti/1').then(r=>r.json())")
    passo("profilo salvato (fototipo 2, sesso F)", r["profilo"]["fototipo"] == 2 and r["profilo"]["sesso"] == "F" and r["profilo"]["data_nascita"] == "1985-04-12", str(r["profilo"]))

    print("== immagine personale dell'utente")
    Image.new("RGBA", (600, 300), (30, 120, 90, 255)).save(tmp / "avatar.png")
    ImageDraw.Draw(Image.open(tmp / "avatar.png")).rectangle((0, 0, 10, 10))
    passo("senza immagine: nel titolo c'è l'iniziale", pg.locator(".utente-chip .avatar-img").count() == 0 and pg.locator(".utente-chip .avatar").inner_text().strip() == "M")
    pg.set_input_files("section:has(.avatar-editor) input[type=file]", str(tmp / "avatar.png"))
    pg.wait_for_selector(".avatar-editor img.avatar-img", timeout=8000)
    pg.wait_for_selector(".utente-chip img.avatar-img", timeout=8000)
    passo("immagine mostrata nel profilo e nell'intestazione", True)
    info = pg.evaluate("fetch('/api/utenti/1/avatar').then(r => r.blob()).then(b => createImageBitmap(b)).then(i => [i.width, i.height])")
    passo("salvata come quadrato 256x256", info == [256, 256], str(info))
    passo("l'immagine si vede davvero (caricata, non rotta)", pg.evaluate("document.querySelector('.utente-chip img.avatar-img').naturalWidth") == 256)
    pg.screenshot(path=str(OUT / "03b_profilo_avatar.png"), full_page=True)
    pg.goto(URL + "/#/utenti")
    pg.wait_for_selector(".utente-card .avatar-img", timeout=8000)
    passo("l'immagine compare nella scelta utente", pg.locator(".utente-card .avatar-img").count() == 1)
    pg.screenshot(path=str(OUT / "03c_scelta_utente_avatar.png"))
    pg.goto(URL + "/#/profilo")
    pg.wait_for_selector(".avatar-editor")
    pg.get_by_role("button", name="Rimuovi", exact=True).click()
    pg.wait_for_selector(".utente-chip .avatar-img", state="detached", timeout=8000)
    passo("rimuovendo l'immagine torna l'iniziale", pg.locator(".utente-chip .avatar").inner_text().strip() == "M")
    pg.set_input_files("section:has(.avatar-editor) input[type=file]", str(tmp / "neo1.jpg"))        # ri-metto un'immagine (una foto vera)
    pg.wait_for_selector(".avatar-editor img.avatar-img", timeout=8000)
    pg.set_input_files("section:has(.avatar-editor) input[type=file]", {"name": "finto.png", "mimeType": "image/png", "buffer": b"non sono un'immagine"})
    pg.wait_for_selector("#toast.visibile.errore", timeout=8000)
    passo("un file che non è un'immagine viene rifiutato con un messaggio", True)
    passo("... e l'immagine precedente resta", pg.locator(".avatar-editor img.avatar-img").count() == 1)

    print("== testi con HTML dentro non vengono eseguiti")
    xss = pg.evaluate("""fetch('/api/utenti', {method:'POST', headers:{'X-NeoTracker':'1','Content-Type':'application/json'},
                         body: JSON.stringify({nome: '<img src=x onerror="window.__xss=1">'})}).then(r => r.json())""")
    pg.goto(URL + "/#/utenti")
    pg.wait_for_selector(".utente-card")
    pg.wait_for_timeout(500)
    passo("il nome con HTML compare come testo", '<img src=x onerror="window.__xss=1">' in pg.inner_text(".utenti-griglia"))
    passo("... e non viene eseguito", pg.evaluate("window.__xss === undefined") and pg.locator(".utenti-griglia img[src='x']").count() == 0)
    pg.evaluate("id => fetch('/api/utenti/' + id, {method:'DELETE', headers:{'X-NeoTracker':'1','Content-Type':'application/json'}, body: JSON.stringify({conferma: '<img src=x onerror=\"window.__xss=1\">'})})", xss["id"])
    pg.goto(URL + "/#/profilo")
    pg.wait_for_selector(".profilo-layout")

    print("== mappa: aggiungi neo")
    pg.click("a.voce:has-text('Mappa')")
    pg.wait_for_selector(".mappa-box svg")
    pg.click("#btn-aggiungi")
    box = pg.locator(".mappa-box svg").bounding_box()
    pg.mouse.move(box["x"] + box["width"] * 0.30, box["y"] + box["height"] * 0.33)
    pg.wait_for_timeout(200)
    pg.screenshot(path=str(OUT / "04_mappa_aggiunta.png"))
    pg.mouse.click(box["x"] + box["width"] * 0.30, box["y"] + box["height"] * 0.33)
    pg.wait_for_selector(".pannello input[type=text]")
    pg.screenshot(path=str(OUT / "05_mappa_bozza.png"))
    campi = pg.locator(".pannello input[type=text]")
    campi.first.fill("Neo spalla")
    pg.locator(".pannello .btn-pri").first.click()
    pg.wait_for_selector(".neo-titolo, .marc:not(.bozza)", timeout=8000)
    pg.wait_for_timeout(500)
    passo("neo creato", len(pg.evaluate("fetch('/api/utenti/1/nevi').then(r=>r.json())")) == 1)
    pg.screenshot(path=str(OUT / "06_neo_dettaglio.png"), full_page=True)

    print("== foto + analisi")
    pg.set_input_files(".form-foto input[type=file]", str(tmp / "neo1.jpg"))
    pg.fill(".form-foto input[placeholder='es. 4,5']", "4,5")
    pg.locator(".form-foto .btn-pri").click()
    pg.wait_for_selector(".striscia .miniatura", timeout=15000)
    passo("foto salvata", True)
    pg.screenshot(path=str(OUT / "07_foto_in_analisi.png"), full_page=True)
    ok = False
    for _ in range(90):
        st = pg.evaluate("fetch('/api/foto/1/analisi').then(r=>r.json())")
        if st["stato"] in ("ok", "errore"):
            ok = True
            break
        time.sleep(2)
    passo("analisi terminata", ok, str(st)[:300] if ok else "timeout")
    pg.wait_for_timeout(3500)
    pg.screenshot(path=str(OUT / "08_analisi.png"), full_page=True)
    print("   stato analisi:", st["stato"], st.get("messaggio", "")[:140])
    # seconda foto per grafico/confronto
    pg.set_input_files(".form-foto input[type=file]", str(tmp / "neo2.jpg")) if pg.locator(".form-foto input[type=file]").count() else None

    print("== letteratura")
    pg.click("a.voce:has-text('Letteratura')")
    pg.wait_for_selector(".azione-scan")
    pg.click(".azione-scan .btn-pri")
    attendi(pg, "document.querySelector('.azione-scan .piccolo.muted')?.textContent.includes('completata') || false")
    passo("scansione letteratura", pg.locator(".articolo").count() > 3)
    pg.screenshot(path=str(OUT / "09_letteratura.png"), full_page=True)

    print("== genetica")
    pg.click("a.voce:has-text('Genetica')")
    pg.wait_for_selector(".tabella")
    pg.screenshot(path=str(OUT / "10_genetica.png"), full_page=True)
    pg.click(".tabella-scroll >> xpath=../.. >> .btn-pri") if False else pg.locator("section:has(.tabella) .btn-pri").click()
    attendi(pg, "document.querySelectorAll('.gene-conta').length >= 10")
    passo("scansione geni", pg.locator(".gene-conta").count() >= 10)
    pg.screenshot(path=str(OUT / "11_genetica_scan.png"), full_page=True)

    print("== indice UV")
    pg.click("a.voce:has-text('Indice UV')")
    pg.wait_for_selector(".uv-posizione")
    pg.screenshot(path=str(OUT / "12_uv_senza_posizione.png"))
    pg.fill(".uv-risultato ~ * , input[aria-label='Nome della città']", "Torino") if False else pg.fill("input[aria-label='Nome della città']", "Torino")
    pg.keyboard.press("Enter")
    pg.wait_for_selector(".citta-voce")
    pg.click(".citta-voce")
    pg.wait_for_selector(".uv-verdetto", timeout=10000)
    pg.wait_for_timeout(400)
    pg.screenshot(path=str(OUT / "13_uv.png"), full_page=True)
    passo("UV mostrato", pg.locator(".grafico-uv rect").count() >= 10, str(pg.locator(".grafico-uv rect").count()))
    uv_testo = pg.locator(".grafico-uv").locator("xpath=..").inner_text()
    pg.click("button:has-text('Rileva la mia posizione')")
    pg.wait_for_timeout(1500)
    imp = pg.evaluate("fetch('/api/impostazioni').then(r=>r.json())")
    passo("geolocalizzazione del browser", "La mia posizione" in imp["localita"], imp["localita"])

    print("== impostazioni")
    pg.click("a.voce:has-text('Impostazioni')")
    pg.wait_for_selector(".stato-lista")
    passo("UV predefinito: fonte Open-Meteo con attribuzione", "Open-Meteo" in uv_testo and "CC BY 4.0" in uv_testo, uv_testo[-200:])
    passo("impostazioni: Open-Meteo selezionato, nessun campo chiave", pg.locator("input[name='fonte-uv'][value='open-meteo']").is_checked()
          and pg.locator("input[aria-label='Chiave OpenWeather']").count() == 0)
    pg.screenshot(path=str(OUT / "14a_impostazioni_predefinite.png"), full_page=True)
    pg.click("input[name='fonte-uv'][value='openweather']")
    pg.wait_for_selector("input[aria-label='Chiave OpenWeather']")
    pg.fill("input[aria-label='Chiave OpenWeather']", mock.CHIAVE_V4)
    pg.click("button:has-text('Salva') >> nth=0")
    pg.wait_for_selector("button:has-text('Prova la chiave')")
    pg.click("button:has-text('Prova la chiave')")
    pg.wait_for_selector(".prova-esito .banda")
    passo("prova chiave OpenWeather 4.0", "Funziona" in pg.locator(".prova-esito .banda").inner_text(), pg.locator(".prova-esito .banda").inner_text())
    pg.screenshot(path=str(OUT / "14_impostazioni.png"), full_page=True)
    pg.click("a.voce:has-text('Indice UV')")
    pg.wait_for_selector(".uv-verdetto")
    pg.wait_for_timeout(400)
    passo("UV dopo la chiave usa OpenWeather", "OpenWeather" in pg.locator(".grafico-uv").locator("xpath=..").inner_text())

    print("== stampa")
    pg.evaluate("window.print = () => { window.__stampato = true; }")
    pg.click("a.voce:has-text('Mappa')")
    pg.wait_for_selector(".mappa-box svg")
    pg.get_by_role("button", name="Scheda per il dermatologo").click()
    attendi(pg, "window.__stampato === true", 15)
    pg.emulate_media(media="print")
    pg.wait_for_timeout(300)
    pg.screenshot(path=str(OUT / "15_stampa.png"), full_page=True)
    passo("scheda stampabile creata", pg.locator("#stampa .st-neo").count() == 1)
    pg.emulate_media(media="screen")

    print("== schermo stretto")
    pg.set_viewport_size({"width": 420, "height": 860})
    pg.goto(URL + "/#/mappa")
    pg.wait_for_selector(".mappa-box svg")
    pg.screenshot(path=str(OUT / "16_stretto.png"))

    b.close()

print("\n== messaggi del browser")
for m in log:
    print("  ", m)
print("\nPROBLEMI:", problemi or "nessuno")
srv.shutdown()
