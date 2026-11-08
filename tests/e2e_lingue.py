# Prova delle lingue dell'interfaccia nel browser (Chrome senza finestra) con servizi finti.
# Uso: python3 e2e_lingue.py
#
# Per ogni lingua (en, fr, de, es) controlla che:
#   - la lingua scelta nelle Impostazioni (o, con "automatica", quella del browser) venga applicata;
#   - ogni schermata si apra senza errori e senza testi senza traduzione (NT.mancanti vuoto);
#   - nelle schermate non restino frasi italiane (controllo a parole-spia: vedi PAROLE_ITALIANE);
#   - date e numeri siano nel formato della lingua;
#   - la scelta della lingua si possa cambiare dal menu delle Impostazioni.
# Gli screenshot finiscono in tests/out/lingue/ (da guardare a occhio dopo ogni modifica ai testi).
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


# ---------------- dati di prova (si creano una volta, poi si guardano nelle varie lingue) ----------------
img = Image.new("RGB", (900, 700), (226, 184, 160))
ImageDraw.Draw(img).ellipse((330, 230, 580, 440), fill=(92, 56, 38))
img.save(tmp / "neo.jpg", quality=92)
api("PUT", "/api/impostazioni", {"avvertenze_accettate": nt.AVVERTENZE_VERSIONE, "lat": 45.07, "lon": 7.69, "localita": "Torino"})
uid = api("POST", "/api/utenti", {"nome": "Marta"})["id"]
api("PUT", f"/api/utenti/{uid}/profilo", {
    "sesso": "F", "data_nascita": "1985-04-12", "fototipo": 2, "capelli": "rossi", "occhi": "azzurri", "efelidi": "molte",
    "n_nevi": "100+", "nevi_atipici": "si", "scottature": "molte", "lampade": "alcune", "melanomi_personali": 1,
    "fam_compilata": True, "fam_melanoma_1grado": 1, "fam_pancreas_1grado": 1, "test_genetico": "si_negativo"})
n1 = api("POST", f"/api/utenti/{uid}/nevi", {"nome": "Alfa", "vista": "fronte", "x": 0.30, "y": 0.22, "regione": "Spalla destra"})["id"]
n2 = api("POST", f"/api/utenti/{uid}/nevi", {"nome": "Beta", "vista": "retro", "x": 0.50, "y": 0.33, "regione": "Regione scapolare sinistra"})["id"]
for data, mm in (("2026-05-10", "4,5"), ("2026-11-02", "5,1")):
    api("POST", f"/api/nevi/{n1}/foto?data={data}&tipo=normale&diametro={mm}&note=prova", raw=(tmp / "neo.jpg").read_bytes())

# parole che in una schermata tradotta non devono comparire (sono italiane e non esistono nelle altre quattro lingue
# come parola intera; i nomi propri e i termini tecnici identici - "melanoma", "dermoscopia" - non sono nell'elenco)
PAROLE_ITALIANE = re.compile(
    r"\b(gli|della|dello|delle|degli|nel|nella|nei|che|sono|hai|puoi|questo|questa|più|anche|"
    r"tutti|tutte|ogni|quando|dove|salva|annulla|elimina|chiudi|cerca|scegli|impostazioni|"
    r"utente|rischio|scottatura|storico|oggi|ieri|giorni|mesi)\b", re.I)

# frasi o parole italiane che in alcune lingue sono identiche (per esempio "profil" o "genetica" in spagnolo): le tolgo dal controllo
AMMESSE = {"es": {"quando"}, "fr": {"quand"}, "de": set(), "en": set()}

SEZIONI = [("mappa", "#/mappa"), ("profilo", "#/profilo"), ("letteratura", "#/letteratura"), ("genetica", "#/genetica"),
           ("uv", "#/uv"), ("impostazioni", "#/impostazioni"), ("utenti", "#/utenti")]

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("NEOTRACKER_TEST_CHROME", "/usr/bin/google-chrome"), args=["--no-sandbox"])

    def nuova_pagina(locale):
        ctx = b.new_context(viewport={"width": 1366, "height": 900}, locale=locale, permissions=["geolocation"],
                            geolocation={"latitude": 45.07, "longitude": 7.69})
        pg = ctx.new_page()
        log = []
        pg.on("pageerror", lambda e: log.append("PAGEERROR: " + str(e)))
        pg.on("console", lambda m: log.append("console: " + m.text) if m.type == "error" and "immagine" not in m.text else None)
        pg.goto(URL + "/?avvio=" + nt.TOKEN_SESSIONE)
        pg.wait_for_selector(".pagina, .utenti-griglia, .profilo-layout, .mappa-box", timeout=10000)
        return ctx, pg, log

    def pronta(pg):
        """Attende che la sezione sia disegnata (niente più 'Caricamento…')."""
        pg.wait_for_selector("#vista > *", timeout=15000)           # (wait_for_function non funziona: la pagina vieta eval)
        pg.wait_for_selector("#vista .caricamento", state="detached", timeout=15000)

    def controlla(pg, lingua, nome):
        testo = pg.inner_text("body")
        pg.screenshot(path=str(OUT / f"{lingua}_{nome}.png"), full_page=True)
        mancanti = pg.evaluate("Array.from(window.NT.mancanti)")
        passo(f"{lingua}/{nome}: nessun testo senza traduzione", not mancanti, mancanti)
        italiane = sorted({m.group(0).lower() for m in PAROLE_ITALIANE.finditer(testo)} - AMMESSE.get(lingua, set()))
        passo(f"{lingua}/{nome}: nessuna parola italiana rimasta", not italiane, italiane)
        return testo

    # 1) scelta automatica dalla lingua del browser
    for locale, lingua in (("fr-FR", "fr"), ("de-AT", "de"), ("es-MX", "es"), ("en-US", "en"), ("it-IT", "it"), ("ja-JP", "en")):
        print(f"== lingua automatica: browser {locale} -> {lingua}")
        api("PUT", "/api/impostazioni", {"lingua": "auto"})
        ctx, pg, log = nuova_pagina(locale)
        passo(f"{locale}: l'interfaccia usa «{lingua}»", pg.evaluate("window.NT.lingua") == lingua, pg.evaluate("window.NT.lingua"))
        passo(f"{locale}: <html lang> = {lingua}", pg.evaluate("document.documentElement.lang") == lingua)
        ctx.close()

    # 2) le quattro lingue, schermata per schermata (la lingua è scelta nelle impostazioni, il browser è in italiano)
    for lingua in ("en", "fr", "de", "es"):
        print(f"== lingua {lingua}")
        api("PUT", "/api/impostazioni", {"lingua": lingua})
        ctx, pg, log = nuova_pagina("it-IT")
        passo(f"{lingua}: la scelta manuale batte la lingua del browser", pg.evaluate("window.NT.lingua") == lingua)
        pg.evaluate(f"window.NT.scegliUtente && window.NT.scegliUtente({uid}, false)")
        for nome, rotta in SEZIONI:
            pg.goto(URL + "/" + rotta)
            pg.reload()
            try:
                pronta(pg)
            except Exception:
                passo(f"{lingua}/{nome}: la pagina si apre", False)
                continue
            if nome in ("letteratura", "genetica"):                   # faccio partire la ricerca nei servizi finti
                pg.locator("#vista button.btn-pri").first.click()
                pg.wait_for_timeout(3000)
            pg.wait_for_timeout(600)
            controlla(pg, lingua, nome)
        # dettaglio di un neo con foto (grafico, elenco foto, esito)
        pg.goto(URL + "/#/mappa")
        pg.reload()
        pronta(pg)
        pg.locator(".neo-card").first.click()
        pg.wait_for_selector(".anteprima", timeout=10000)
        pg.wait_for_timeout(1200)
        testo_neo = controlla(pg, lingua, "neo")
        # il dialogo di confronto e la scheda per il dermatologo (stampa) hanno testi propri
        pg.locator("button:has-text('" + {"en": "Compare", "fr": "Comparer", "de": "Vergleichen", "es": "Comparar"}[lingua] + "')").first.click()
        pg.wait_for_timeout(800)
        controlla(pg, lingua, "confronto")
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(300)
        # formato delle date: il neo ha foto del 10/05/2026 e del 02/11/2026
        atteso = {"en": "10 May 2026", "fr": "10/05/2026", "de": "10.05.2026", "es": "10/05/2026"}[lingua]
        passo(f"{lingua}: data nel formato della lingua ({atteso})", atteso in testo_neo, testo_neo[:200].replace("\n", " "))
        errori_js = [l for l in log if l.startswith("PAGEERROR")]
        passo(f"{lingua}: nessun errore JavaScript", not errori_js, errori_js)
        ctx.close()

    # 3) cambio della lingua dal menu delle Impostazioni
    print("== cambio lingua dal menu")
    api("PUT", "/api/impostazioni", {"lingua": "auto"})
    ctx, pg, log = nuova_pagina("it-IT")
    pg.goto(URL + "/#/impostazioni")
    pg.reload()
    pg.wait_for_selector("#sel-lingua", timeout=10000)
    passo("il menu parte da «Automatica»", pg.eval_on_selector("#sel-lingua", "e => e.value") == "auto")
    with pg.expect_navigation():
        pg.select_option("#sel-lingua", "de")
    pg.wait_for_selector("#sel-lingua", timeout=10000)
    passo("scelto «de»: la pagina si ricarica in tedesco", pg.evaluate("window.NT.lingua") == "de" and "Sprache" in pg.inner_text("body"))
    passo("la scelta è salvata", api("GET", "/api/impostazioni")["lingua"] == "de")
    pg.screenshot(path=str(OUT / "de_cambio_lingua.png"))
    with pg.expect_navigation():
        pg.select_option("#sel-lingua", "it")
    pg.wait_for_selector("#sel-lingua", timeout=10000)
    passo("tornando a «it» riappare l'italiano", pg.evaluate("window.NT.lingua") == "it" and "Lingua" in pg.inner_text("body"))
    ctx.close()
    b.close()

print()
print("PROBLEMI:", "nessuno" if not problemi else "\n  " + "\n  ".join(problemi))
sys.exit(1 if problemi else 0)
