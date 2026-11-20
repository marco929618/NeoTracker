# Full test of the NeoTracker backend with mock services. Usage: python3 test_api.py
import http.client
import importlib.util
import io
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import mock_servizi as mock

PORTA_MOCK, PORTA_APP = 8799, 8751
tmp = Path(tempfile.mkdtemp(prefix="neo_dati_"))
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
ok_n = fail_n = 0


def chiama(metodo, percorso, corpo=None, raw=None, header=None, atteso=200, cookie=True):
    h = {"X-NeoTracker": "1"}
    if cookie:                                    # the real window presents the session key through a cookie
        h["Cookie"] = f"{nt.NOME_COOKIE}={nt.TOKEN_SESSIONE}"
    h.update(header or {})
    dati = raw
    if corpo is not None:
        dati = json.dumps(corpo).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(URL + percorso, data=dati, method=metodo, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            cod, body, tipo = r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        cod, body, tipo = e.code, e.read(), e.headers.get("Content-Type", "")
    esito = json.loads(body) if "json" in tipo else body
    return cod, esito


def verifica(nome, condizione, extra=""):
    global ok_n, fail_n
    if condizione:
        ok_n += 1
        print(f"  ok   {nome}")
    else:
        fail_n += 1
        print(f"  FAIL {nome} {extra}")


print("== general and security")
c, r = chiama("GET", "/api/ping")
verifica("ping", c == 200 and r["app"] == "NeoTracker")
c, r = chiama("GET", "/api/stato")
verifica("status: batch found", c == 200 and r["batch"].endswith("melanoma_batch.py"), str(r))
verifica("status: projects", len(r["progetti"]) == 3 and (r["progetti"][0]["presente"] or not ANALISI), str(r["progetti"]))
verifica("status: Pillow not outdated + notice version", r["pillow_obsoleto"] is False and r["avvertenze_versione"] == nt.AVVERTENZE_VERSIONE and r["max_mb_foto"] == nt.MAX_MB_FOTO)
c, _ = chiama("POST", "/api/utenti", {"nome": "x"}, header={"X-NeoTracker": ""})
verifica("POST without security header rejected", c == 403)
con = http.client.HTTPConnection("127.0.0.1", PORTA_APP)
con.request("GET", "/api/ping", headers={"Host": "evil.example.com"})
verifica("wrong Host rejected (DNS rebinding)", con.getresponse().status == 403)
c, _ = chiama("GET", "/api/ping", header={"Origin": "http://evil.example.com"})
verifica("external Origin rejected", c == 403)
c, _ = chiama("OPTIONS", "/api/utenti")
verifica("OPTIONS (CORS preflight) rejected", c == 403)
c, r = chiama("GET", "/")
verifica("main page served", c == 200 and b"<title>" in r)
c, _ = chiama("GET", "/api/inesistente")
verifica("404 on an unknown address", c == 404)
c, _ = chiama("DELETE", "/api/ping")
verifica("405 on a method not allowed", c == 405)

print("== users and profile")
c, r = chiama("POST", "/api/utenti", {"nome": "  Marco   Rossi "})
uid = r["id"]
verifica("create user (spaces normalised)", c == 200 and r["nome"] == "Marco Rossi")
c, _ = chiama("POST", "/api/utenti", {"nome": "marco rossi"})
verifica("duplicate name -> 409", c == 409)
c, _ = chiama("POST", "/api/utenti", {"nome": " "})
verifica("empty name -> 400", c == 400)
c, r2 = chiama("POST", "/api/utenti", {"nome": "Anna"})
uid2 = r2["id"]
c, r = chiama("GET", "/api/utenti")
verifica("users list sorted", [u["nome"] for u in r] == ["Anna", "Marco Rossi"], str(r))
c, r = chiama("GET", f"/api/utenti/{uid}")
verifica("empty profile -> insufficient data", r["genetica"]["esito"] == "dati_insufficienti" and r["rischio"]["livello"] == "nessuno", str(r["genetica"]["esito"]))
c, r = chiama("PUT", f"/api/utenti/{uid}/profilo", {"sesso": "M", "data_nascita": "1980-05-01", "fototipo": 2, "capelli": "rossi",
                                                      "n_nevi": "100+", "nevi_atipici": "si", "melanomi_personali": 3, "fam_compilata": True,
                                                      "campo_inventato": "x", "occhi": "viola"})
verifica("save profile", c == 200 and r["profilo"]["fototipo"] == 2 and "campo_inventato" not in r["profilo"] and r["profilo"]["occhi"] == "")
verifica("age calculated", r["eta"] is not None and r["eta"] >= 45, str(r["eta"]))
verifica("risk: attention", r["rischio"]["livello"] == "attenzione" and len(r["rischio"]["presenti"]) >= 4)
verifica("genetics: 3-melanoma criterion", r["genetica"]["esito"] == "criteri_soddisfatti" and
         any(x["id"] == "tre_melanomi" and x["soddisfatto"] for x in r["genetica"]["criteri"]) and "CDKN2A" in r["genetica"]["geni_suggeriti"])
c, r = chiama("PUT", f"/api/utenti/{uid2}/profilo", {"fam_compilata": True, "fam_melanoma_1grado": 1, "fam_pancreas_1grado": 1, "melanomi_personali": 1})
verifica("genetics: personal melanoma + first-degree pancreatic cancer", any(x["id"] == "mel_pancreas" and x["soddisfatto"] for x in r["genetica"]["criteri"]), str(r["genetica"]["criteri"]))
verifica("total pancreatic >= first degree", r["profilo"]["fam_pancreas"] == 1)
c, r = chiama("PUT", f"/api/utenti/{uid2}/profilo", {"melanomi_personali": 0, "fam_melanoma_1grado": 0, "fam_pancreas_1grado": 0, "fam_pancreas": 0})
verifica("genetics: no criterion", r["genetica"]["esito"] == "nessun_criterio")
c, _ = chiama("PUT", f"/api/utenti/{uid2}/profilo", {"data_nascita": "31/02/1990"})
verifica("wrong birth date -> 400", c == 400)
c, r = chiama("PATCH", f"/api/utenti/{uid2}", {"nome": "Anna B"})
verifica("rename", c == 200 and r["nome"] == "Anna B")

print("== moles")
c, r = chiama("POST", f"/api/utenti/{uid}/nevi", {"nome": "Back mole", "vista": "retro", "x": 0.52, "y": 0.31, "regione": "Schiena, parte alta"})
nid = r["id"]
verifica("create mole", c == 200 and nid > 0)
c, _ = chiama("POST", f"/api/utenti/{uid}/nevi", {"vista": "retro", "x": 1.4, "y": 0.2})
verifica("position outside the map -> 400", c == 400)
c, _ = chiama("POST", f"/api/utenti/{uid}/nevi", {"vista": "lato", "x": 0.4, "y": 0.2})
verifica("unknown view -> 400", c == 400)
c, r = chiama("POST", f"/api/utenti/{uid}/nevi", {"vista": "fronte", "x": 0.4, "y": 0.2})
verifica("automatic name", c == 200)
c, r = chiama("GET", f"/api/utenti/{uid}/nevi")
verifica("moles list", len(r) == 2 and r[1]["nome"] == "Mole 2", str([n["nome"] for n in r]))
c, _ = chiama("PATCH", f"/api/nevi/{nid}", {"x": 0.55, "y": 0.33})
c, r = chiama("GET", f"/api/nevi/{nid}")
verifica("move mole", r["nevo"]["x"] == 0.55 and r["nevo"]["y"] == 0.33 and r["nevo"]["vista"] == "retro")

print("== photos")
from PIL import Image, ImageDraw
_img = Image.new("RGB", (1200, 900), (226, 184, 160))                      # "skin" with a dark "mole" in the middle (made-up image)
ImageDraw.Draw(_img).ellipse((450, 300, 760, 580), fill=(92, 56, 38))
_buf = io.BytesIO(); _img.save(_buf, "JPEG", quality=92)
jpg = _buf.getvalue()
c, r = chiama("POST", f"/api/nevi/{nid}/foto?data=2026-08-01&tipo=normale&diametro=4,5&note=prima%20foto", raw=jpg)
fid = r["id"]
verifica("upload photo", c == 200 and r["scattata_il"] == "2026-08-01", str(r))
c, r = chiama("POST", f"/api/nevi/{nid}/foto?data=2099-01-01", raw=jpg)
verifica("future date rejected", c == 400)
c, r = chiama("POST", f"/api/nevi/{nid}/foto?data=2026-08-01", raw=b"questo non e' un'immagine")
verifica("non-image file rejected", c == 400)
c, r = chiama("POST", f"/api/nevi/{nid}/foto?data=2026-08-01", raw=b"\x00\x00\x00\x18ftypheic" + b"0" * 100)
verifica("HEIC rejected with an explanation", c == 400 and "HEIC" in r["errore"])
c, r = chiama("POST", f"/api/nevi/{nid}/foto?data=2026-08-01&diametro=500", raw=jpg)
verifica("absurd diameter rejected", c == 400)
c, r = chiama("POST", "/api/nevi/99999/foto?data=2026-08-01", raw=jpg)
verifica("non-existent mole -> 404", c == 404)
# EXIF
from PIL import Image
im = Image.open(io.BytesIO(jpg)).convert("RGB")
ex = Image.Exif()
ex[306] = "2025:03:09 14:22:11"
buf = io.BytesIO(); im.save(buf, "JPEG", exif=ex)
c, r = chiama("POST", f"/api/nevi/{nid}/foto?data=2026-11-08&exif=1&diametro=5", raw=buf.getvalue())
fid2 = r["id"]
verifica("date read from the EXIF", r["scattata_il"] == "2025-03-09" and r["da_exif"], str(r))
c, r = chiama("POST", f"/api/nevi/{nid}/foto?data=2026-11-08&exif=0", raw=buf.getvalue())
fid3 = r["id"]
verifica("EXIF ignored if not requested", r["scattata_il"] == "2026-11-08")
c, r = chiama("GET", f"/api/nevi/{nid}")
verifica("photos in date order", [f["scattata_il"] for f in r["foto"]] == ["2025-03-09", "2026-08-01", "2026-11-08"], str([f["scattata_il"] for f in r["foto"]]))
c, body = chiama("GET", f"/foto/{fid}/mini?l=240")
verifica("JPEG thumbnail", c == 200 and body[:3] == b"\xff\xd8\xff" and len(body) < len(jpg))
im2 = Image.open(io.BytesIO(body)); verifica("thumbnail <= 240 px", max(im2.size) <= 240, str(im2.size))
c, body = chiama("GET", f"/foto/{fid}/originale")
verifica("identical original (historical photo untouched)", c == 200 and body == jpg)
c, _ = chiama("PATCH", f"/api/foto/{fid}", {"diametro_mm": "6,2", "note": "ingrandito"})
c, r = chiama("GET", f"/api/nevi/{nid}")
verifica("edit measurement", any(f["diametro_mm"] == 6.2 for f in r["foto"]))
c, r = chiama("GET", f"/api/utenti/{uid}/nevi")
verifica("list: last photo and days", r[0]["n_foto"] == 3 and r[0]["ultima_data"] == "2026-11-08" and r[0]["giorni_da_ultima"] is not None, str(r[0]))
# malicious path
with nt.connetti() as c2:
    file_vero = c2.execute("SELECT file FROM foto WHERE id=?", (fid3,)).fetchone()[0]
    c2.execute("UPDATE foto SET file='../../../etc/passwd' WHERE id=?", (fid3,))
c, r = chiama("GET", f"/foto/{fid3}/originale")
verifica("path traversal blocked", c == 404, str(c))
with nt.connetti() as c2:
    c2.execute("UPDATE foto SET file=? WHERE id=?", (file_vero, fid3))

if ANALISI:
    print("== automatic analysis (uses melanoma_batch.py)")
    c, r = chiama("POST", f"/api/foto/{fid}/analizza")
    verifica("analysis queued", c == 200 and r["stato"] in ("in_coda", "in_corso"), str(r))
    c, r = chiama("POST", f"/api/foto/{fid}/analizza")
    verifica("double request does not duplicate", r["stato"] in ("in_coda", "in_corso"))
    c, r = chiama("POST", f"/api/foto/{fid2}/analizza")
    t0 = time.time()
    stato = None
    while time.time() - t0 < 400:
        c, st = chiama("GET", f"/api/foto/{fid}/analisi")
        stato = st["stato"]
        if stato in ("ok", "errore"):
            break
        time.sleep(2)
    verifica("analysis finished", stato == "ok", str(st)[:600])
    if stato == "ok":
        s = st["sintesi"]
        verifica("summary: 5 methods", len(s["metodi"]) == 5, str([m["numero"] for m in s["metodi"]]))
        verifica("summary: SkinSense NOT run by default", any("not run" in (r_["nota"] or "").lower() for m in s["metodi"] if m["numero"] == 2 for r_ in m["risultati"]), str(s["metodi"][1]))
        verifica("summary: report text", "RAPPORTO AUTOMATICO" in s["testo"])
        verifica("outcome saved", st["esito"] == s["esito"] and s["esito"] in ("attenzione", "benigno", "discordante", "nessuno"), st["esito"])
        print("   esito:", s["esito"], "| methods with a result:", s["con_risultato"])
        rap = nt.Path(nt.CARTELLA_DATI) / nt.connetti().execute("SELECT rapporto FROM foto WHERE id=?", (fid,)).fetchone()[0]
        verifica("photo analysed without EXIF", not Image.open(rap / "foto_analizzata.jpg").getexif())
    c, r = chiama("DELETE", f"/api/foto/{fid2}")
    verifica("a photo under analysis cannot be deleted", c == 409 or c == 200, str(c))
    # wait for the second one so as not to leave processes behind
    t0 = time.time()
    while time.time() - t0 < 400:
        c, st = chiama("GET", f"/api/foto/{fid2}/analisi")
        if st["stato"] in ("ok", "errore"):
            break
        time.sleep(2)
    verifica("second queued analysis finished", st["stato"] in ("ok", "errore"), str(st)[:300])
else:
    print("== automatic analysis: skipped (needs NEOTRACKER_TEST_REPOS with the projects installed)")

print("== UV and location")
c, r = chiama("PUT", "/api/impostazioni", {"lat": 45.07, "lon": 7.69, "localita": "Turin, IT"})
verifica("settings: location", r["lat"] == 45.07 and r["localita"] == "Turin, IT" and "openweather_key" not in r)
c, imp0 = chiama("GET", "/api/impostazioni")
verifica("default UV source = Open-Meteo", imp0["fonte_uv"] == "open-meteo", str(imp0))
mock.CHIAMATE.clear()
c, r = chiama("GET", "/api/uv?fototipo=2")
verifica("default: Open-Meteo, without warnings", c == 200 and r["fonte"] == "Open-Meteo" and r["avviso"] == "", str(r)[:300])
verifica("default: no call to OpenWeather", not any(x.startswith("/data/") or x.startswith("/geo/") for x in mock.CHIAMATE), str(mock.CHIAMATE))
c, _ = chiama("PUT", "/api/impostazioni", {"fonte_uv": "satellite"})
verifica("invalid UV source rejected", c == 400)
c, r2 = chiama("PUT", "/api/impostazioni", {"fonte_uv": "openweather"})
verifica("OpenWeather choice saved", c == 200 and r2["fonte_uv"] == "openweather")
c, r2 = chiama("GET", "/api/uv?fototipo=2")
verifica("OpenWeather chosen but no key: Open-Meteo with a warning", r2["fonte"] == "Open-Meteo" and "the key is missing" in r2["avviso"], str(r2)[:300])
c, r2 = chiama("PUT", "/api/impostazioni", {"fonte_uv": "open-meteo"})
verifica("UV: category and verdict", r["categoria_max"]["nome"] == "Moderate" and r["verdetto"]["livello"] == "giallo", str(r["categoria_max"]))
verifica("UV: sunburn minutes phototype 2 (2.5*60/4.8=31)", r["scottatura_max"]["minuti"] == 31, str(r["scottatura_max"]))
verifica("UV: 24 hours", len(r["ore"]) == 24 and r["ore"][0]["ora"] == "10:00", str(r["ore"][:2]))
c, r = chiama("PUT", "/api/impostazioni", {"openweather_key": "chiave sbagliata!"})
verifica("key with strange characters rejected", c == 400)
c, r = chiama("PUT", "/api/impostazioni", {"openweather_key": "0000000000000000"})
verifica("key never returned", "openweather_key" not in r and r["ha_chiave_owm"] and r["chiave_owm_finale"] == "…0000", str(r))
mock.CHIAMATE.clear()
c, r = chiama("GET", "/api/uv?fototipo=2")
verifica("saving the key does NOT change the source: it stays Open-Meteo", r["fonte"] == "Open-Meteo" and r["avviso"] == "" and not any(x.startswith("/data/") for x in mock.CHIAMATE), str(mock.CHIAMATE))
c, r = chiama("PUT", "/api/impostazioni", {"fonte_uv": "openweather"})
c, r = chiama("GET", "/api/uv?fototipo=2")
verifica("OpenWeather chosen, key rejected -> Open-Meteo with a 401 warning", c == 200 and r["fonte"] == "Open-Meteo" and "401" in r["avviso"], r.get("avviso", ""))
c, r = chiama("POST", "/api/impostazioni/prova-owm")
verifica("test of a wrong key -> clear message", r["ok"] is False and "401" in r["messaggio"], str(r))
c, r = chiama("PUT", "/api/impostazioni", {"openweather_key": mock.CHIAVE_BUONA})
c, r = chiama("POST", "/api/impostazioni/prova-owm")
verifica("test of a good key", r["ok"] is True, str(r))
c, r = chiama("GET", "/api/uv?fototipo=1")
verifica("OpenWeather One Call used", r["fonte"].startswith("OpenWeather") and r["avviso"] == "", str(r)[:300])
verifica("OWM: uvi max 6.4 -> High -> orange", r["uvi_max"] == 6.4 and r["categoria_max"]["nome"] == "High" and r["verdetto"]["livello"] == "arancio", str(r["verdetto"]))
verifica("OWM: local time (UTC+1)", r["ore"][0]["ora"] == "13:00" or r["ore"][0]["ora"] == "12:00", str(r["ore"][:2]))
verifica("OWM: phototype I -> 2*60/6.4 = 19 min", r["scottatura_max"]["minuti"] == 19, str(r["scottatura_max"]))
c, r = chiama("PUT", "/api/impostazioni", {"openweather_key": mock.CHIAVE_V4})
mock.CHIAMATE.clear()
c, r = chiama("GET", "/api/uv?fototipo=3&lat=45.5&lon=7.5")
verifica("OWM 4.0 used (key valid only for 4.0)", r["fonte"] == "OpenWeather One Call 4.0" and r["avviso"] == "", str(r)[:300])
verifica("OWM 4.0: 24 hours (20 + continuation)", len(r["ore"]) == 24, str(len(r["ore"])))
verifica("OWM 4.0: today's max from the daily data (7.1) and current 3.1", r["uvi_max"] == 7.1 and r["uvi_ora"] == 3.1 and r["categoria_max"]["nome"] == "High", str((r["uvi_max"], r["uvi_ora"])))
verifica("OWM 4.0: calls = current, hourly x2, daily", sum(1 for x in mock.CHIAMATE if x.startswith("/data/4.0/")) == 4 and not any(x.startswith("/data/3.0/") for x in mock.CHIAMATE), str(mock.CHIAMATE))
c, r = chiama("PUT", "/api/impostazioni", {"openweather_key": mock.CHIAVE_BUONA})
c, r = chiama("GET", "/api/uv?lat=999&lon=0")
verifica("invalid coordinates -> 400", c == 400)
c, r = chiama("GET", "/api/localita?q=Tor")
verifica("place search with OpenWeather (chosen + key)", c == 200 and r[0]["nome"] == "Turin, Piedmont, IT", str(r))
c, _ = chiama("PUT", "/api/impostazioni", {"fonte_uv": "open-meteo"})
mock.CHIAMATE.clear()
c, r = chiama("GET", "/api/localita?q=Tor")
verifica("default place search: Open-Meteo, not OpenWeather", c == 200 and r and r[0]["nome"] != "Turin, Piedmont, IT" and not any(x.startswith("/geo/") for x in mock.CHIAMATE), str(r)[:200] + str(mock.CHIAMATE))
c, r = chiama("GET", "/api/posizione-ip")
verifica("location from IP", r["nome"] == "Turin, IT")

print("== literature and genetics (mock PubMed)")
c, r = chiama("GET", f"/api/letteratura/temi?utente={uid}")
verifica("topics + personalised sections", [t["tema"] for t in r][:3] == ["riconoscimento", "strumenti_ai", "genetica"] and r[-1]["tema"] == "personale", str([t["tema"] for t in r]))
verifica("section personalised for phototype II + many moles", any("moles" in s["titolo"].lower() for s in r[-1]["sezioni"]), str(r[-1]))
n_prima = len([x for x in mock.CHIAMATE if "esearch" in x])
c, r = chiama("GET", "/api/letteratura/sezione?id=genetica:0")
verifica("section: articles read from the XML", c == 200 and r["conteggio"] == 1234 and len(r["articoli"]) == 2, str(r)[:300])
a = r["articoli"][0]
verifica("XML: title with clean markup", a["titolo"] == "Selection criteria for genetic assessment of patients with familial melanoma.", a["titolo"])
verifica("XML: abstract with labels and &amp;", a["abstract"].startswith("Background: Melanoma is a common cancer. Results: We propose rule of three & more."), a["abstract"])
verifica("XML: abbreviated authors", a["autori"] == "Leachman SA, Carucci J, Kohlmann W, et al.", a["autori"])
verifica("XML: journal/year/doi/types/url", a["rivista"] == "J Am Acad Dermatol" and a["anno"] == "2009" and a["doi"].startswith("10.1016") and "Review" in a["tipi"] and a["url"].endswith("/19751883/"), str(a))
b = r["articoli"][1]
verifica("XML: year from MedlineDate, no abstract", b["anno"] == "2019" and b["abstract"] == "", str(b))
c, r = chiama("GET", "/api/letteratura/sezione?id=genetica:0")
n_dopo = len([x for x in mock.CHIAMATE if "esearch" in x])
verifica("second request from the cache", r["da_cache"] is True and n_dopo == n_prima + 1, f"{n_prima} {n_dopo}")
c, r = chiama("GET", "/api/letteratura/sezione?id=genetica:0&forza=1")
verifica("refresh forces a new search", r["da_cache"] is False and len([x for x in mock.CHIAMATE if "esearch" in x]) == n_dopo + 1)
c, r = chiama("GET", "/api/letteratura/sezione?id=boh:9")
verifica("unknown section -> 404", c == 404)
c, r = chiama("GET", "/api/letteratura/cerca?q=ugly%20duckling%20sign")
verifica("free search forces 'melanoma'", c == 200 and "melanoma" in r["termine"] and "ugly duckling sign" in r["termine"], str(r)[:200])
c, r = chiama("GET", "/api/letteratura/cerca?q=ab")
verifica("search too short -> 400", c == 400)
c, r = chiama("GET", "/api/genetica/geni")
verifica("gene list", len(r["geni"]) >= 10 and r["geni"][0]["gene"] == "CDKN2A" and "termine" not in r["geni"][0])
c, r = chiama("GET", "/api/genetica/gene?nome=CDKN2A")
verifica("gene: count and articles", c == 200 and r["conteggio"] == 1234 and r["gene"] == "CDKN2A")
c, r = chiama("GET", "/api/genetica/gene?nome=XYZ")
verifica("unknown gene -> 404", c == 404)

print("== PubMed unreachable: it uses the old copy")
os.environ["NEOTRACKER_EUTILS_BASE"] = "http://127.0.0.1:9/"
c, r = chiama("GET", "/api/letteratura/sezione?id=genetica:0&forza=1")
verifica("with no network and a cache -> old copy reported", c == 200 and r.get("obsoleta") is True and len(r["articoli"]) == 2, str(r)[:200])
c, r = chiama("GET", "/api/letteratura/sezione?id=genetica:1")
verifica("with no network and no cache -> clear message", c == 502 and "PubMed" in r["errore"], str(r))
os.environ["NEOTRACKER_EUTILS_BASE"] = base + "/entrez/eutils/"

print("== immagine personale (avatar)")
from PIL import Image as _Img
def _png(w, h, modo="RGBA", col=(200, 30, 30, 120)):
    b = io.BytesIO(); _Img.new(modo, (w, h), col).save(b, "PNG"); return b.getvalue()
def _jpg_con_exif(w, h):
    img = _Img.new("RGB", (w, h), (10, 120, 200))
    ex = img.getexif(); ex[0x010F] = "FotocameraSegreta"; ex[0x0112] = 6          # mark + rotation
    b = io.BytesIO(); img.save(b, "JPEG", exif=ex); return b.getvalue()
c, r = chiama("GET", f"/api/utenti/{uid}")
verifica("no avatar at the beginning (avatar_v = 0)", r["avatar_v"] == 0)
c, _ = chiama("GET", f"/api/utenti/{uid}/avatar")
verifica("GET missing avatar -> 404", c == 404)
c, r = chiama("POST", f"/api/utenti/{uid}/avatar", raw=_png(300, 200))
v1 = r.get("avatar_v", 0)
verifica("save PNG avatar with transparency", c == 200 and v1 > 0, str(r))
c, dati = chiama("GET", f"/api/utenti/{uid}/avatar")
im = _Img.open(io.BytesIO(dati))
verifica("avatar served: JPEG 256x256", c == 200 and im.format == "JPEG" and im.size == (256, 256), f"{im.format} {im.size}")
verifica("transparency becomes a non-black background", sum(im.getpixel((5, 5))) > 300, str(im.getpixel((5, 5))))
c, r = chiama("GET", "/api/utenti")
verifica("users list reports avatar_v", next(u for u in r if u["id"] == uid)["avatar_v"] == v1 and next(u for u in r if u["id"] == uid2)["avatar_v"] == 0)
c, r = chiama("GET", f"/api/utenti/{uid}")
verifica("user detail reports avatar_v", r["avatar_v"] == v1)
time.sleep(0.02)
c, r = chiama("POST", f"/api/utenti/{uid}/avatar", raw=_jpg_con_exif(640, 360))
verifica("replaced with a JPEG (the version changes)", c == 200 and r["avatar_v"] != v1, str(r))
c, dati = chiama("GET", f"/api/utenti/{uid}/avatar")
im = _Img.open(io.BytesIO(dati))
verifica("metadata (EXIF) removed from the avatar", len(im.getexif()) == 0 and b"FotocameraSegreta" not in dati and im.size == (256, 256), str(dict(im.getexif())))
c, _ = chiama("POST", f"/api/utenti/{uid}/avatar", raw=b"")
verifica("empty avatar -> 400", c == 400)
c, _ = chiama("POST", f"/api/utenti/{uid}/avatar", raw=b"GIF89a" + b"\x00" * 100)
verifica("format not allowed (GIF) -> 400", c == 400)
c, _ = chiama("POST", f"/api/utenti/{uid}/avatar", raw=b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>")
verifica("SVG rejected -> 400", c == 400)
c, _ = chiama("POST", f"/api/utenti/{uid}/avatar", raw=b"\xff\xd8\xff" + os.urandom(500))
verifica("fake JPEG (random bytes) -> 400", c == 400)
b = io.BytesIO(); _Img.new("1", (20000, 20000)).save(b, "PNG")
c, _ = chiama("POST", f"/api/utenti/{uid}/avatar", raw=b.getvalue())
verifica("trap image (400 megapixels) -> 400", c == 400 and len(b.getvalue()) < 200_000, f"{c} {len(b.getvalue())}")
sk = socket.create_connection(("127.0.0.1", PORTA_APP), timeout=10)             # I declare 9 MB but do not send them: the server must reject AT ONCE
sk.sendall((f"POST /api/utenti/{uid}/avatar HTTP/1.0\r\nHost: 127.0.0.1:{PORTA_APP}\r\nX-NeoTracker: 1\r\nCookie: {nt.NOME_COOKIE}={nt.TOKEN_SESSIONE}\r\n"
            f"Content-Length: {9 * 1024 * 1024}\r\n\r\n").encode())
verifica("avatar > 8 MB -> 413 without reading the body", sk.recv(100).startswith(b"HTTP/1.0 413"))
sk.close()
c, _ = chiama("POST", "/api/utenti/99999/avatar", raw=_png(10, 10))
verifica("avatar of a non-existent user -> 404", c == 404)
c, r = chiama("GET", f"/api/utenti/{uid}/avatar")
verifica("after the rejections the good avatar is still there", c == 200)
verifica("no temporary file left behind", not list(nt.cartella_avatar().glob("*.tmp")))
c, r = chiama("POST", f"/api/utenti/{uid2}/avatar", raw=_png(50, 50, "RGB", (1, 2, 3)))
verifica("avatar for the second user", c == 200 and nt.percorso_avatar(uid2).exists())
c, r = chiama("DELETE", f"/api/utenti/{uid2}/avatar")
verifica("remove avatar", c == 200 and r["avatar_v"] == 0 and not nt.percorso_avatar(uid2).exists())
c, r = chiama("POST", f"/api/utenti/{uid2}/avatar", raw=_png(50, 50, "RGB", (1, 2, 3)))
c, r = chiama("DELETE", f"/api/utenti/{uid2}", {"conferma": "Anna B"})
verifica("deleting the user also removes the avatar", c == 200 and not nt.percorso_avatar(uid2).exists())

print("== deletions")
c, r = chiama("DELETE", f"/api/foto/{fid3}")
verifica("delete photo", c == 200 and not list((nt.cartella_foto() / f"u{uid}" / f"n{nid}").glob("*20261108*")))
c, r = chiama("DELETE", f"/api/nevi/{nid}")
cartella_neo = nt.cartella_foto() / f"u{uid}" / f"n{nid}"
verifica("delete mole (with its photos)", c == 200 and not list(cartella_neo.glob("*")), str(list(cartella_neo.glob("*"))))
c, r = chiama("DELETE", f"/api/utenti/{uid}", {"conferma": "sbagliato"})
verifica("deleting a user requires the exact name", c == 400)
c, r = chiama("DELETE", f"/api/utenti/{uid}", {"conferma": "Marco Rossi"})
verifica("delete user", c == 200 and not (nt.cartella_foto() / f"u{uid}").exists() and not (nt.cartella_rapporti() / f"u{uid}").exists()
         and not nt.percorso_avatar(uid).exists())
with nt.connetti() as c2:
    verifica("no orphans in the database", c2.execute("SELECT COUNT(*) FROM nevi WHERE utente_id=?", (uid,)).fetchone()[0] == 0 and
             c2.execute("SELECT COUNT(*) FROM foto").fetchone()[0] == 0)

print("== shutdown")
c, r = chiama("POST", "/api/chiudi")
time.sleep(0.5)
verifica("shutdown requested", c == 200 and srv.chiusura_richiesta)

shutil.rmtree(tmp, ignore_errors=True)
print(f"\nRESULT: {ok_n} ok, {fail_n} failed")
sys.exit(1 if fail_n else 0)
