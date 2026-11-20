# Test of the interface languages in the browser (Chrome without a window) with mock services.
# Usage: python3 e2e_lingue.py
#
# For every translated language (it, fr, de, es) it checks that:
#   - the language chosen in Settings (or, with "automatic", the browser one) is applied;
#   - every screen opens without errors and without untranslated texts (NT.mancanti empty);
#   - no English phrases are left on the screens (check by tell-tale words: see PAROLE_INGLESI);
#   - dates and numbers are in the format of the language;
#   - the language can be changed from the Settings menu.
# The screenshots go to tests/out/lingue/ (look at them by eye after every change to the texts).
import importlib.util
import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import mock_servizi as mock
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

PORTA_MOCK, PORTA_APP = 8797, 8753
OUT = Path(__file__).parent / "out" / "lingue"
OUT.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp(prefix="neo_lingue_"))
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
nt.CARTELLA_REPO = tmp / "senza_progetti"
nt.CARTELLA_SCRIPT = Path(__file__).resolve().parent.parent
nt.inizializza_db()
srv = nt.Server(("127.0.0.1", PORTA_APP), nt.Gestore)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{PORTA_APP}"

problemi = []


def passo(nome, ok, extra=""):
    print(("  ok   " if ok else "  FAIL ") + nome + (" -> " + str(extra)[:300] if (extra and not ok) else ""))
    if not ok:
        problemi.append(nome)


def api(metodo, percorso, corpo=None, raw=None):
    h = {"X-NeoTracker": "1", "Cookie": f"{nt.NOME_COOKIE}={nt.TOKEN_SESSIONE}"}
    dati = raw
    if corpo is not None:
        dati = json.dumps(corpo).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(URL + percorso, data=dati, method=metodo, headers=h)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"null")


# ---------------- test data (created once, then looked at in the various languages) ----------------
img = Image.new("RGB", (900, 700), (226, 184, 160))
ImageDraw.Draw(img).ellipse((330, 230, 580, 440), fill=(92, 56, 38))
img.save(tmp / "mole.jpg", quality=92)
api("PUT", "/api/impostazioni", {"avvertenze_accettate": nt.AVVERTENZE_VERSIONE, "lat": 45.07, "lon": 7.69, "localita": "Turin"})
uid = api("POST", "/api/utenti", {"nome": "Marta"})["id"]
api("PUT", f"/api/utenti/{uid}/profilo", {
    "sesso": "F", "data_nascita": "1985-04-12", "fototipo": 2, "capelli": "rossi", "occhi": "azzurri", "efelidi": "molte",
    "n_nevi": "100+", "nevi_atipici": "si", "scottature": "molte", "lampade": "alcune", "melanomi_personali": 1,
    "fam_compilata": True, "fam_melanoma_1grado": 1, "fam_pancreas_1grado": 1, "test_genetico": "si_negativo"})
n1 = api("POST", f"/api/utenti/{uid}/nevi", {"nome": "Alfa", "vista": "fronte", "x": 0.30, "y": 0.22, "regione": "Shoulder, right"})["id"]
n2 = api("POST", f"/api/utenti/{uid}/nevi", {"nome": "Beta", "vista": "retro", "x": 0.50, "y": 0.33, "regione": "Shoulder blade area, left"})["id"]
for data, mm in (("2026-05-10", "4.5"), ("2026-11-02", "5.1")):
    api("POST", f"/api/nevi/{n1}/foto?data={data}&tipo=normale&diametro={mm}&note=test", raw=(tmp / "mole.jpg").read_bytes())

# words that must not appear on a translated screen (they are English and do not exist in the other four languages
# as a whole word; proper names and identical technical terms - "melanoma", "dermoscopy" - are not in the list)
PAROLE_INGLESI = re.compile(
    r"\b(the|and|your|you|with|this|that|from|have|are|save|cancel|delete|close|search|choose|settings|"
    r"user|risk|history|today|yesterday|days|months)\b", re.I)

# English words that are identical in some languages (for example "user" in French): they are removed from the check
AMMESSE = {"it": set(), "fr": {"user"}, "de": set(), "es": set()}

SEZIONI = [("map", "#/mappa"), ("profile", "#/profilo"), ("literature", "#/letteratura"), ("genetics", "#/genetica"),
           ("uv", "#/uv"), ("settings", "#/impostazioni"), ("users", "#/utenti")]

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("NEOTRACKER_TEST_CHROME", "/usr/bin/google-chrome"), args=["--no-sandbox"])

    def nuova_pagina(locale):
        ctx = b.new_context(viewport={"width": 1366, "height": 900}, locale=locale, permissions=["geolocation"],
                            geolocation={"latitude": 45.07, "longitude": 7.69})
        pg = ctx.new_page()
        log = []
        pg.on("pageerror", lambda e: log.append("PAGEERROR: " + str(e)))
        pg.on("console", lambda m: log.append("console: " + m.text) if m.type == "error" and "image" not in m.text else None)
        pg.goto(URL + "/?avvio=" + nt.TOKEN_SESSIONE)
        pg.wait_for_selector(".pagina, .utenti-griglia, .profilo-layout, .mappa-box", timeout=10000)
        return ctx, pg, log

    def pronta(pg):
        """Waits until the section is drawn (no more 'Loading…')."""
        pg.wait_for_selector("#vista > *", timeout=15000)           # (wait_for_function does not work: the page forbids eval)
        pg.wait_for_selector("#vista .caricamento", state="detached", timeout=15000)

    def controlla(pg, lingua, nome):
        testo = pg.inner_text("body")
        pg.screenshot(path=str(OUT / f"{lingua}_{nome}.png"), full_page=True)
        # the bibliographic references keep the original English titles of the papers: they are not checked
        pg.evaluate("document.querySelectorAll('.fonti').forEach(e => { e.style.display = 'none'; })")
        testo_senza_fonti = pg.inner_text("body")
        mancanti = pg.evaluate("Array.from(window.NT.mancanti)")
        passo(f"{lingua}/{nome}: no untranslated text", not mancanti, mancanti)
        inglesi = sorted({m.group(0).lower() for m in PAROLE_INGLESI.finditer(testo_senza_fonti)} - AMMESSE.get(lingua, set()))
        passo(f"{lingua}/{nome}: no English word left", not inglesi, inglesi)
        return testo

    # 1) automatic choice from the browser language
    for locale, lingua in (("fr-FR", "fr"), ("de-AT", "de"), ("es-MX", "es"), ("it-IT", "it"), ("en-US", "en"), ("ja-JP", "en")):
        print(f"== automatic language: browser {locale} -> {lingua}")
        api("PUT", "/api/impostazioni", {"lingua": "auto"})
        ctx, pg, log = nuova_pagina(locale)
        passo(f"{locale}: the interface uses \"{lingua}\"", pg.evaluate("window.NT.lingua") == lingua, pg.evaluate("window.NT.lingua"))
        passo(f"{locale}: <html lang> = {lingua}", pg.evaluate("document.documentElement.lang") == lingua)
        ctx.close()

    # 2) the four translated languages, screen by screen (the language is chosen in the settings, the browser is in English)
    for lingua in ("it", "fr", "de", "es"):
        print(f"== language {lingua}")
        api("PUT", "/api/impostazioni", {"lingua": lingua})
        ctx, pg, log = nuova_pagina("en-US")
        passo(f"{lingua}: the manual choice beats the browser language", pg.evaluate("window.NT.lingua") == lingua)
        pg.evaluate(f"window.NT.scegliUtente && window.NT.scegliUtente({uid}, false)")
        for nome, rotta in SEZIONI:
            pg.goto(URL + "/" + rotta)
            pg.reload()
            try:
                pronta(pg)
            except Exception:
                passo(f"{lingua}/{nome}: the page opens", False)
                continue
            if nome in ("letteratura", "genetica"):                   # I start the search in the mock services
                pg.locator("#vista button.btn-pri").first.click()
                pg.wait_for_timeout(3000)
            pg.wait_for_timeout(600)
            controlla(pg, lingua, nome)
        # detail of a mole with photos (chart, photo list, outcome)
        pg.goto(URL + "/#/mappa")
        pg.reload()
        pronta(pg)
        pg.locator(".neo-card").first.click()
        pg.wait_for_selector(".anteprima", timeout=10000)
        pg.wait_for_timeout(1200)
        testo_neo = controlla(pg, lingua, "mole")
        # the comparison dialog and the sheet for the dermatologist (print) have their own texts
        pg.locator("button:has-text('" + {"it": "Confronta", "fr": "Comparer", "de": "Vergleichen", "es": "Comparar"}[lingua] + "')").first.click()
        pg.wait_for_timeout(800)
        controlla(pg, lingua, "comparison")
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(300)
        # date format: the mole has photos of 10/05/2026 and 02/11/2026
        atteso = {"it": "10/05/2026", "fr": "10/05/2026", "de": "10.05.2026", "es": "10/05/2026"}[lingua]
        passo(f"{lingua}: date in the format of the language ({atteso})", atteso in testo_neo, testo_neo[:200].replace("\n", " "))
        errori_js = [l for l in log if l.startswith("PAGEERROR")]
        passo(f"{lingua}: no JavaScript error", not errori_js, errori_js)
        ctx.close()

    # 3) changing the language from the Settings menu
    print("== language change from the menu")
    api("PUT", "/api/impostazioni", {"lingua": "auto"})
    ctx, pg, log = nuova_pagina("en-US")
    pg.goto(URL + "/#/impostazioni")
    pg.reload()
    pg.wait_for_selector("#sel-lingua", timeout=10000)
    passo("the menu starts from \"Automatic\"", pg.eval_on_selector("#sel-lingua", "e => e.value") == "auto")
    with pg.expect_navigation():
        pg.select_option("#sel-lingua", "de")
    pg.wait_for_selector("#sel-lingua", timeout=10000)
    passo("\"de\" chosen: the page reloads in German", pg.evaluate("window.NT.lingua") == "de" and "Sprache" in pg.inner_text("body"))
    passo("the choice is saved", api("GET", "/api/impostazioni")["lingua"] == "de")
    pg.screenshot(path=str(OUT / "de_language_change.png"))
    with pg.expect_navigation():
        pg.select_option("#sel-lingua", "en")
    pg.wait_for_selector("#sel-lingua", timeout=10000)
    passo("going back to \"en\" brings English back", pg.evaluate("window.NT.lingua") == "en" and "Language" in pg.inner_text("body"))
    ctx.close()
    b.close()

print()
print("PROBLEMS:", "none" if not problemi else "\n  " + "\n  ".join(problemi))
sys.exit(1 if problemi else 0)
