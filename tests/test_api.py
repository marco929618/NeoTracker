# Prova completa del backend di NeoTracker con servizi finti. Uso: python3 test_api.py
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
# Cartella dei progetti di analisi: se non è indicata (NEOTRACKER_TEST_REPOS) i metodi risultano "non installati"
# e le prove che richiedono un'analisi vera vengono saltate.
ANALISI = bool(os.environ.get("NEOTRACKER_TEST_REPOS"))
nt.CARTELLA_REPO = Path(os.environ.get("NEOTRACKER_TEST_REPOS") or (tmp / "senza_progetti"))
nt.CARTELLA_SCRIPT = Path(__file__).resolve().parent.parent          # qui sta melanoma_batch.py
nt.inizializza_db()
srv = nt.Server(("127.0.0.1", PORTA_APP), nt.Gestore)
threading.Thread(target=srv.serve_forever, daemon=True).start()

URL = f"http://127.0.0.1:{PORTA_APP}"
ok_n = fail_n = 0


def chiama(metodo, percorso, corpo=None, raw=None, header=None, atteso=200, cookie=True):
    h = {"X-NeoTracker": "1"}
    if cookie:                                    # la finestra vera presenta la chiave di sessione tramite cookie
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


print("== generale e sicurezza")
c, r = chiama("GET", "/api/ping")
verifica("ping", c == 200 and r["app"] == "NeoTracker")
c, r = chiama("GET", "/api/stato")
verifica("stato: batch trovato", c == 200 and r["batch"].endswith("melanoma_batch.py"), str(r))
verifica("stato: progetti", len(r["progetti"]) == 3 and (r["progetti"][0]["presente"] or not ANALISI), str(r["progetti"]))
verifica("stato: Pillow non obsoleto + versione avviso", r["pillow_obsoleto"] is False and r["avvertenze_versione"] == nt.AVVERTENZE_VERSIONE and r["max_mb_foto"] == nt.MAX_MB_FOTO)
c, _ = chiama("POST", "/api/utenti", {"nome": "x"}, header={"X-NeoTracker": ""})
verifica("POST senza header di sicurezza rifiutato", c == 403)
con = http.client.HTTPConnection("127.0.0.1", PORTA_APP)
con.request("GET", "/api/ping", headers={"Host": "evil.example.com"})
verifica("Host sbagliato rifiutato (DNS rebinding)", con.getresponse().status == 403)
c, _ = chiama("GET", "/api/ping", header={"Origin": "http://evil.example.com"})
verifica("Origin esterna rifiutata", c == 403)
c, _ = chiama("OPTIONS", "/api/utenti")
verifica("OPTIONS (CORS preflight) rifiutato", c == 403)
c, r = chiama("GET", "/")
verifica("pagina principale servita", c == 200 and b"<title>" in r)
c, _ = chiama("GET", "/api/inesistente")
verifica("404 su indirizzo sconosciuto", c == 404)
c, _ = chiama("DELETE", "/api/ping")
verifica("405 su metodo non ammesso", c == 405)

print("== utenti e profilo")
c, r = chiama("POST", "/api/utenti", {"nome": "  Marco   Rossi "})
uid = r["id"]
verifica("crea utente (spazi normalizzati)", c == 200 and r["nome"] == "Marco Rossi")
c, _ = chiama("POST", "/api/utenti", {"nome": "marco rossi"})
verifica("nome duplicato -> 409", c == 409)
c, _ = chiama("POST", "/api/utenti", {"nome": " "})
verifica("nome vuoto -> 400", c == 400)
c, r2 = chiama("POST", "/api/utenti", {"nome": "Anna"})
uid2 = r2["id"]
c, r = chiama("GET", "/api/utenti")
verifica("lista utenti ordinata", [u["nome"] for u in r] == ["Anna", "Marco Rossi"], str(r))
c, r = chiama("GET", f"/api/utenti/{uid}")
verifica("profilo vuoto -> dati insufficienti", r["genetica"]["esito"] == "dati_insufficienti" and r["rischio"]["livello"] == "nessuno", str(r["genetica"]["esito"]))
c, r = chiama("PUT", f"/api/utenti/{uid}/profilo", {"sesso": "M", "data_nascita": "1980-05-01", "fototipo": 2, "capelli": "rossi",
                                                      "n_nevi": "100+", "nevi_atipici": "si", "melanomi_personali": 3, "fam_compilata": True,
                                                      "campo_inventato": "x", "occhi": "viola"})
verifica("salva profilo", c == 200 and r["profilo"]["fototipo"] == 2 and "campo_inventato" not in r["profilo"] and r["profilo"]["occhi"] == "")
verifica("eta calcolata", r["eta"] is not None and r["eta"] >= 45, str(r["eta"]))
verifica("rischio: attenzione", r["rischio"]["livello"] == "attenzione" and len(r["rischio"]["presenti"]) >= 4)
verifica("genetica: criterio 3 melanomi", r["genetica"]["esito"] == "criteri_soddisfatti" and
         any(x["id"] == "tre_melanomi" and x["soddisfatto"] for x in r["genetica"]["criteri"]) and "CDKN2A" in r["genetica"]["geni_suggeriti"])
c, r = chiama("PUT", f"/api/utenti/{uid2}/profilo", {"fam_compilata": True, "fam_melanoma_1grado": 1, "fam_pancreas_1grado": 1, "melanomi_personali": 1})
verifica("genetica: melanoma personale + pancreas 1 grado", any(x["id"] == "mel_pancreas" and x["soddisfatto"] for x in r["genetica"]["criteri"]), str(r["genetica"]["criteri"]))
verifica("pancreas totale >= 1 grado", r["profilo"]["fam_pancreas"] == 1)
c, r = chiama("PUT", f"/api/utenti/{uid2}/profilo", {"melanomi_personali": 0, "fam_melanoma_1grado": 0, "fam_pancreas_1grado": 0, "fam_pancreas": 0})
verifica("genetica: nessun criterio", r["genetica"]["esito"] == "nessun_criterio")
c, _ = chiama("PUT", f"/api/utenti/{uid2}/profilo", {"data_nascita": "31/02/1990"})
verifica("data di nascita errata -> 400", c == 400)
c, r = chiama("PATCH", f"/api/utenti/{uid2}", {"nome": "Anna B"})
verifica("rinomina", c == 200 and r["nome"] == "Anna B")

print("== nei")
c, r = chiama("POST", f"/api/utenti/{uid}/nevi", {"nome": "Neo schiena", "vista": "retro", "x": 0.52, "y": 0.31, "regione": "Schiena, parte alta"})
nid = r["id"]
verifica("crea neo", c == 200 and nid > 0)
c, _ = chiama("POST", f"/api/utenti/{uid}/nevi", {"vista": "retro", "x": 1.4, "y": 0.2})
verifica("posizione fuori mappa -> 400", c == 400)
c, _ = chiama("POST", f"/api/utenti/{uid}/nevi", {"vista": "lato", "x": 0.4, "y": 0.2})
verifica("vista sconosciuta -> 400", c == 400)
c, r = chiama("POST", f"/api/utenti/{uid}/nevi", {"vista": "fronte", "x": 0.4, "y": 0.2})
verifica("nome automatico", c == 200)
c, r = chiama("GET", f"/api/utenti/{uid}/nevi")
verifica("lista nei", len(r) == 2 and r[1]["nome"] == "Neo 2", str([n["nome"] for n in r]))
c, _ = chiama("PATCH", f"/api/nevi/{nid}", {"x": 0.55, "y": 0.33})
c, r = chiama("GET", f"/api/nevi/{nid}")
verifica("sposta neo", r["nevo"]["x"] == 0.55 and r["nevo"]["y"] == 0.33 and r["nevo"]["vista"] == "retro")

print("== foto")
from PIL import Image, ImageDraw
_img = Image.new("RGB", (1200, 900), (226, 184, 160))                      # "pelle" con un "neo" scuro in mezzo (immagine inventata)
ImageDraw.Draw(_img).ellipse((450, 300, 760, 580), fill=(92, 56, 38))
_buf = io.BytesIO(); _img.save(_buf, "JPEG", quality=92)
jpg = _buf.getvalue()
c, r = chiama("POST", f"/api/nevi/{nid}/foto?data=2026-08-01&tipo=normale&diametro=4,5&note=prima%20foto", raw=jpg)
fid = r["id"]
verifica("carica foto", c == 200 and r["scattata_il"] == "2026-08-01", str(r))
c, r = chiama("POST", f"/api/nevi/{nid}/foto?data=2099-01-01", raw=jpg)
verifica("data futura rifiutata", c == 400)
c, r = chiama("POST", f"/api/nevi/{nid}/foto?data=2026-08-01", raw=b"questo non e' un'immagine")
verifica("file non immagine rifiutato", c == 400)
c, r = chiama("POST", f"/api/nevi/{nid}/foto?data=2026-08-01", raw=b"\x00\x00\x00\x18ftypheic" + b"0" * 100)
verifica("HEIC rifiutato con spiegazione", c == 400 and "HEIC" in r["errore"])
c, r = chiama("POST", f"/api/nevi/{nid}/foto?data=2026-08-01&diametro=500", raw=jpg)
verifica("diametro assurdo rifiutato", c == 400)
c, r = chiama("POST", "/api/nevi/99999/foto?data=2026-08-01", raw=jpg)
verifica("neo inesistente -> 404", c == 404)
# EXIF
from PIL import Image
im = Image.open(io.BytesIO(jpg)).convert("RGB")
ex = Image.Exif()
ex[306] = "2025:03:09 14:22:11"
buf = io.BytesIO(); im.save(buf, "JPEG", exif=ex)
c, r = chiama("POST", f"/api/nevi/{nid}/foto?data=2026-11-08&exif=1&diametro=5", raw=buf.getvalue())
fid2 = r["id"]
verifica("data letta dall'EXIF", r["scattata_il"] == "2025-03-09" and r["da_exif"], str(r))
c, r = chiama("POST", f"/api/nevi/{nid}/foto?data=2026-11-08&exif=0", raw=buf.getvalue())
fid3 = r["id"]
verifica("EXIF ignorato se non richiesto", r["scattata_il"] == "2026-11-08")
c, r = chiama("GET", f"/api/nevi/{nid}")
verifica("foto in ordine di data", [f["scattata_il"] for f in r["foto"]] == ["2025-03-09", "2026-08-01", "2026-11-08"], str([f["scattata_il"] for f in r["foto"]]))
c, body = chiama("GET", f"/foto/{fid}/mini?l=240")
verifica("miniatura JPEG", c == 200 and body[:3] == b"\xff\xd8\xff" and len(body) < len(jpg))
im2 = Image.open(io.BytesIO(body)); verifica("miniatura <= 240 px", max(im2.size) <= 240, str(im2.size))
c, body = chiama("GET", f"/foto/{fid}/originale")
verifica("originale identico (foto storica intatta)", c == 200 and body == jpg)
c, _ = chiama("PATCH", f"/api/foto/{fid}", {"diametro_mm": "6,2", "note": "ingrandito"})
c, r = chiama("GET", f"/api/nevi/{nid}")
verifica("modifica misura", any(f["diametro_mm"] == 6.2 for f in r["foto"]))
c, r = chiama("GET", f"/api/utenti/{uid}/nevi")
verifica("lista: ultima foto e giorni", r[0]["n_foto"] == 3 and r[0]["ultima_data"] == "2026-11-08" and r[0]["giorni_da_ultima"] is not None, str(r[0]))
# percorso malevolo
with nt.connetti() as c2:
    file_vero = c2.execute("SELECT file FROM foto WHERE id=?", (fid3,)).fetchone()[0]
    c2.execute("UPDATE foto SET file='../../../etc/passwd' WHERE id=?", (fid3,))
c, r = chiama("GET", f"/foto/{fid3}/originale")
verifica("path traversal bloccato", c == 404, str(c))
with nt.connetti() as c2:
    c2.execute("UPDATE foto SET file=? WHERE id=?", (file_vero, fid3))

if ANALISI:
    print("== analisi automatica (usa melanoma_batch.py)")
    c, r = chiama("POST", f"/api/foto/{fid}/analizza")
    verifica("analisi in coda", c == 200 and r["stato"] in ("in_coda", "in_corso"), str(r))
    c, r = chiama("POST", f"/api/foto/{fid}/analizza")
    verifica("doppia richiesta non duplica", r["stato"] in ("in_coda", "in_corso"))
    c, r = chiama("POST", f"/api/foto/{fid2}/analizza")
    t0 = time.time()
    stato = None
    while time.time() - t0 < 400:
        c, st = chiama("GET", f"/api/foto/{fid}/analisi")
        stato = st["stato"]
        if stato in ("ok", "errore"):
            break
        time.sleep(2)
    verifica("analisi terminata", stato == "ok", str(st)[:600])
    if stato == "ok":
        s = st["sintesi"]
        verifica("sintesi: 5 metodi", len(s["metodi"]) == 5, str([m["numero"] for m in s["metodi"]]))
        verifica("sintesi: SkinSense NON eseguito di default", any("non eseguito" in (r_["nota"] or "").lower() for m in s["metodi"] if m["numero"] == 2 for r_ in m["risultati"]), str(s["metodi"][1]))
        verifica("sintesi: testo rapporto", "RAPPORTO AUTOMATICO" in s["testo"])
        verifica("esito salvato", st["esito"] == s["esito"] and s["esito"] in ("attenzione", "benigno", "discordante", "nessuno"), st["esito"])
        print("   esito:", s["esito"], "| metodi con risultato:", s["con_risultato"])
        rap = nt.Path(nt.CARTELLA_DATI) / nt.connetti().execute("SELECT rapporto FROM foto WHERE id=?", (fid,)).fetchone()[0]
        verifica("foto analizzata senza EXIF", not Image.open(rap / "foto_analizzata.jpg").getexif())
    c, r = chiama("DELETE", f"/api/foto/{fid2}")
    verifica("non si cancella foto in analisi", c == 409 or c == 200, str(c))
    # attendi la seconda per non lasciare processi
    t0 = time.time()
    while time.time() - t0 < 400:
        c, st = chiama("GET", f"/api/foto/{fid2}/analisi")
        if st["stato"] in ("ok", "errore"):
            break
        time.sleep(2)
    verifica("seconda analisi in coda terminata", st["stato"] in ("ok", "errore"), str(st)[:300])
else:
    print("== analisi automatica: saltata (serve NEOTRACKER_TEST_REPOS con i progetti installati)")

print("== UV e posizione")
c, r = chiama("PUT", "/api/impostazioni", {"lat": 45.07, "lon": 7.69, "localita": "Torino, IT"})
verifica("impostazioni: posizione", r["lat"] == 45.07 and r["localita"] == "Torino, IT" and "openweather_key" not in r)
c, imp0 = chiama("GET", "/api/impostazioni")
verifica("fonte UV predefinita = Open-Meteo", imp0["fonte_uv"] == "open-meteo", str(imp0))
mock.CHIAMATE.clear()
c, r = chiama("GET", "/api/uv?fototipo=2")
verifica("predefinito: Open-Meteo, senza avvisi", c == 200 and r["fonte"] == "Open-Meteo" and r["avviso"] == "", str(r)[:300])
verifica("predefinito: nessuna chiamata a OpenWeather", not any(x.startswith("/data/") or x.startswith("/geo/") for x in mock.CHIAMATE), str(mock.CHIAMATE))
c, _ = chiama("PUT", "/api/impostazioni", {"fonte_uv": "satellite"})
verifica("fonte UV non valida rifiutata", c == 400)
c, r2 = chiama("PUT", "/api/impostazioni", {"fonte_uv": "openweather"})
verifica("scelta OpenWeather salvata", c == 200 and r2["fonte_uv"] == "openweather")
c, r2 = chiama("GET", "/api/uv?fototipo=2")
verifica("OpenWeather scelto ma senza chiave: Open-Meteo con avviso", r2["fonte"] == "Open-Meteo" and "manca la chiave" in r2["avviso"], str(r2)[:300])
c, r2 = chiama("PUT", "/api/impostazioni", {"fonte_uv": "open-meteo"})
verifica("UV: categoria e verdetto", r["categoria_max"]["nome"] == "Moderato" and r["verdetto"]["livello"] == "giallo", str(r["categoria_max"]))
verifica("UV: minuti scottatura fototipo 2 (2.5*60/4.8=31)", r["scottatura_max"]["minuti"] == 31, str(r["scottatura_max"]))
verifica("UV: 24 ore", len(r["ore"]) == 24 and r["ore"][0]["ora"] == "10:00", str(r["ore"][:2]))
c, r = chiama("PUT", "/api/impostazioni", {"openweather_key": "chiave sbagliata!"})
verifica("chiave con caratteri strani rifiutata", c == 400)
c, r = chiama("PUT", "/api/impostazioni", {"openweather_key": "0000000000000000"})
verifica("chiave mai restituita", "openweather_key" not in r and r["ha_chiave_owm"] and r["chiave_owm_finale"] == "…0000", str(r))
mock.CHIAMATE.clear()
c, r = chiama("GET", "/api/uv?fototipo=2")
verifica("salvare la chiave NON cambia la fonte: resta Open-Meteo", r["fonte"] == "Open-Meteo" and r["avviso"] == "" and not any(x.startswith("/data/") for x in mock.CHIAMATE), str(mock.CHIAMATE))
c, r = chiama("PUT", "/api/impostazioni", {"fonte_uv": "openweather"})
c, r = chiama("GET", "/api/uv?fototipo=2")
verifica("OpenWeather scelto, chiave rifiutata -> Open-Meteo con avviso 401", c == 200 and r["fonte"] == "Open-Meteo" and "401" in r["avviso"], r.get("avviso", ""))
c, r = chiama("POST", "/api/impostazioni/prova-owm")
verifica("prova chiave sbagliata -> messaggio chiaro", r["ok"] is False and "401" in r["messaggio"], str(r))
c, r = chiama("PUT", "/api/impostazioni", {"openweather_key": mock.CHIAVE_BUONA})
c, r = chiama("POST", "/api/impostazioni/prova-owm")
verifica("prova chiave buona", r["ok"] is True, str(r))
c, r = chiama("GET", "/api/uv?fototipo=1")
verifica("OpenWeather One Call usato", r["fonte"].startswith("OpenWeather") and r["avviso"] == "", str(r)[:300])
verifica("OWM: uvi max 6.4 -> Alto -> arancio", r["uvi_max"] == 6.4 and r["categoria_max"]["nome"] == "Alto" and r["verdetto"]["livello"] == "arancio", str(r["verdetto"]))
verifica("OWM: ora locale (UTC+1)", r["ore"][0]["ora"] == "13:00" or r["ore"][0]["ora"] == "12:00", str(r["ore"][:2]))
verifica("OWM: fototipo I -> 2*60/6.4 = 19 min", r["scottatura_max"]["minuti"] == 19, str(r["scottatura_max"]))
c, r = chiama("PUT", "/api/impostazioni", {"openweather_key": mock.CHIAVE_V4})
mock.CHIAMATE.clear()
c, r = chiama("GET", "/api/uv?fototipo=3&lat=45.5&lon=7.5")
verifica("OWM 4.0 usato (chiave buona solo per la 4.0)", r["fonte"] == "OpenWeather One Call 4.0" and r["avviso"] == "", str(r)[:300])
verifica("OWM 4.0: 24 ore (20 + seguito)", len(r["ore"]) == 24, str(len(r["ore"])))
verifica("OWM 4.0: max di oggi dal giornaliero (7.1) e ora 3.1", r["uvi_max"] == 7.1 and r["uvi_ora"] == 3.1 and r["categoria_max"]["nome"] == "Alto", str((r["uvi_max"], r["uvi_ora"])))
verifica("OWM 4.0: chiamate = corrente, orario x2, giornaliero", sum(1 for x in mock.CHIAMATE if x.startswith("/data/4.0/")) == 4 and not any(x.startswith("/data/3.0/") for x in mock.CHIAMATE), str(mock.CHIAMATE))
c, r = chiama("PUT", "/api/impostazioni", {"openweather_key": mock.CHIAVE_BUONA})
c, r = chiama("GET", "/api/uv?lat=999&lon=0")
verifica("coordinate non valide -> 400", c == 400)
c, r = chiama("GET", "/api/localita?q=Tor")
verifica("ricerca localita con OpenWeather (scelto + chiave)", c == 200 and r[0]["nome"] == "Torino, Piedmont, IT", str(r))
c, _ = chiama("PUT", "/api/impostazioni", {"fonte_uv": "open-meteo"})
mock.CHIAMATE.clear()
c, r = chiama("GET", "/api/localita?q=Tor")
verifica("ricerca localita predefinita: Open-Meteo, non OpenWeather", c == 200 and r and r[0]["nome"] != "Torino, Piedmont, IT" and not any(x.startswith("/geo/") for x in mock.CHIAMATE), str(r)[:200] + str(mock.CHIAMATE))
c, r = chiama("GET", "/api/posizione-ip")
verifica("posizione da IP", r["nome"] == "Torino, IT")

print("== letteratura e genetica (PubMed finto)")
c, r = chiama("GET", f"/api/letteratura/temi?utente={uid}")
verifica("temi + sezioni personalizzate", [t["tema"] for t in r][:3] == ["riconoscimento", "strumenti_ai", "genetica"] and r[-1]["tema"] == "personale", str([t["tema"] for t in r]))
verifica("sezione personalizzata per fototipo II + molti nei", any("nei" in s["titolo"].lower() for s in r[-1]["sezioni"]), str(r[-1]))
n_prima = len([x for x in mock.CHIAMATE if "esearch" in x])
c, r = chiama("GET", "/api/letteratura/sezione?id=genetica:0")
verifica("sezione: articoli letti dal XML", c == 200 and r["conteggio"] == 1234 and len(r["articoli"]) == 2, str(r)[:300])
a = r["articoli"][0]
verifica("XML: titolo con markup pulito", a["titolo"] == "Selection criteria for genetic assessment of patients with familial melanoma.", a["titolo"])
verifica("XML: abstract con etichette e &amp;", a["abstract"].startswith("Background: Melanoma is a common cancer. Results: We propose rule of three & more."), a["abstract"])
verifica("XML: autori abbreviati", a["autori"] == "Leachman SA, Carucci J, Kohlmann W, et al.", a["autori"])
verifica("XML: rivista/anno/doi/tipi/url", a["rivista"] == "J Am Acad Dermatol" and a["anno"] == "2009" and a["doi"].startswith("10.1016") and "Review" in a["tipi"] and a["url"].endswith("/19751883/"), str(a))
b = r["articoli"][1]
verifica("XML: anno da MedlineDate, nessun abstract", b["anno"] == "2019" and b["abstract"] == "", str(b))
c, r = chiama("GET", "/api/letteratura/sezione?id=genetica:0")
n_dopo = len([x for x in mock.CHIAMATE if "esearch" in x])
verifica("seconda richiesta dalla cache", r["da_cache"] is True and n_dopo == n_prima + 1, f"{n_prima} {n_dopo}")
c, r = chiama("GET", "/api/letteratura/sezione?id=genetica:0&forza=1")
verifica("aggiorna forza nuova ricerca", r["da_cache"] is False and len([x for x in mock.CHIAMATE if "esearch" in x]) == n_dopo + 1)
c, r = chiama("GET", "/api/letteratura/sezione?id=boh:9")
verifica("sezione sconosciuta -> 404", c == 404)
c, r = chiama("GET", "/api/letteratura/cerca?q=ugly%20duckling%20sign")
verifica("ricerca libera forza 'melanoma'", c == 200 and "melanoma" in r["termine"] and "ugly duckling sign" in r["termine"], str(r)[:200])
c, r = chiama("GET", "/api/letteratura/cerca?q=ab")
verifica("ricerca troppo corta -> 400", c == 400)
c, r = chiama("GET", "/api/genetica/geni")
verifica("elenco geni", len(r["geni"]) >= 10 and r["geni"][0]["gene"] == "CDKN2A" and "termine" not in r["geni"][0])
c, r = chiama("GET", "/api/genetica/gene?nome=CDKN2A")
verifica("gene: conteggio e articoli", c == 200 and r["conteggio"] == 1234 and r["gene"] == "CDKN2A")
c, r = chiama("GET", "/api/genetica/gene?nome=XYZ")
verifica("gene sconosciuto -> 404", c == 404)

print("== PubMed non raggiungibile: usa la copia vecchia")
os.environ["NEOTRACKER_EUTILS_BASE"] = "http://127.0.0.1:9/"
c, r = chiama("GET", "/api/letteratura/sezione?id=genetica:0&forza=1")
verifica("con rete assente e cache -> copia vecchia segnalata", c == 200 and r.get("obsoleta") is True and len(r["articoli"]) == 2, str(r)[:200])
c, r = chiama("GET", "/api/letteratura/sezione?id=genetica:1")
verifica("con rete assente e senza cache -> messaggio chiaro", c == 502 and "PubMed" in r["errore"], str(r))
os.environ["NEOTRACKER_EUTILS_BASE"] = base + "/entrez/eutils/"

print("== immagine personale (avatar)")
from PIL import Image as _Img
def _png(w, h, modo="RGBA", col=(200, 30, 30, 120)):
    b = io.BytesIO(); _Img.new(modo, (w, h), col).save(b, "PNG"); return b.getvalue()
def _jpg_con_exif(w, h):
    img = _Img.new("RGB", (w, h), (10, 120, 200))
    ex = img.getexif(); ex[0x010F] = "FotocameraSegreta"; ex[0x0112] = 6          # marca + rotazione
    b = io.BytesIO(); img.save(b, "JPEG", exif=ex); return b.getvalue()
c, r = chiama("GET", f"/api/utenti/{uid}")
verifica("nessun avatar all'inizio (avatar_v = 0)", r["avatar_v"] == 0)
c, _ = chiama("GET", f"/api/utenti/{uid}/avatar")
verifica("GET avatar assente -> 404", c == 404)
c, r = chiama("POST", f"/api/utenti/{uid}/avatar", raw=_png(300, 200))
v1 = r.get("avatar_v", 0)
verifica("salva avatar PNG con trasparenza", c == 200 and v1 > 0, str(r))
c, dati = chiama("GET", f"/api/utenti/{uid}/avatar")
im = _Img.open(io.BytesIO(dati))
verifica("avatar servito: JPEG 256x256", c == 200 and im.format == "JPEG" and im.size == (256, 256), f"{im.format} {im.size}")
verifica("la trasparenza diventa sfondo non nero", sum(im.getpixel((5, 5))) > 300, str(im.getpixel((5, 5))))
c, r = chiama("GET", "/api/utenti")
verifica("lista utenti riporta avatar_v", next(u for u in r if u["id"] == uid)["avatar_v"] == v1 and next(u for u in r if u["id"] == uid2)["avatar_v"] == 0)
c, r = chiama("GET", f"/api/utenti/{uid}")
verifica("dettaglio utente riporta avatar_v", r["avatar_v"] == v1)
time.sleep(0.02)
c, r = chiama("POST", f"/api/utenti/{uid}/avatar", raw=_jpg_con_exif(640, 360))
verifica("sostituisce con JPEG (la versione cambia)", c == 200 and r["avatar_v"] != v1, str(r))
c, dati = chiama("GET", f"/api/utenti/{uid}/avatar")
im = _Img.open(io.BytesIO(dati))
verifica("metadati (EXIF) rimossi dall'avatar", len(im.getexif()) == 0 and b"FotocameraSegreta" not in dati and im.size == (256, 256), str(dict(im.getexif())))
c, _ = chiama("POST", f"/api/utenti/{uid}/avatar", raw=b"")
verifica("avatar vuoto -> 400", c == 400)
c, _ = chiama("POST", f"/api/utenti/{uid}/avatar", raw=b"GIF89a" + b"\x00" * 100)
verifica("formato non ammesso (GIF) -> 400", c == 400)
c, _ = chiama("POST", f"/api/utenti/{uid}/avatar", raw=b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>")
verifica("SVG rifiutato -> 400", c == 400)
c, _ = chiama("POST", f"/api/utenti/{uid}/avatar", raw=b"\xff\xd8\xff" + os.urandom(500))
verifica("JPEG finto (byte a caso) -> 400", c == 400)
b = io.BytesIO(); _Img.new("1", (20000, 20000)).save(b, "PNG")
c, _ = chiama("POST", f"/api/utenti/{uid}/avatar", raw=b.getvalue())
verifica("immagine-trappola (400 megapixel) -> 400", c == 400 and len(b.getvalue()) < 200_000, f"{c} {len(b.getvalue())}")
sk = socket.create_connection(("127.0.0.1", PORTA_APP), timeout=10)             # dichiaro 9 MB ma non li mando: il server deve rifiutare SUBITO
sk.sendall((f"POST /api/utenti/{uid}/avatar HTTP/1.0\r\nHost: 127.0.0.1:{PORTA_APP}\r\nX-NeoTracker: 1\r\nCookie: {nt.NOME_COOKIE}={nt.TOKEN_SESSIONE}\r\n"
            f"Content-Length: {9 * 1024 * 1024}\r\n\r\n").encode())
verifica("avatar > 8 MB -> 413 senza leggere il corpo", sk.recv(100).startswith(b"HTTP/1.0 413"))
sk.close()
c, _ = chiama("POST", "/api/utenti/99999/avatar", raw=_png(10, 10))
verifica("avatar di utente inesistente -> 404", c == 404)
c, r = chiama("GET", f"/api/utenti/{uid}/avatar")
verifica("dopo i rifiuti l'avatar buono è ancora lì", c == 200)
verifica("nessun file temporaneo lasciato", not list(nt.cartella_avatar().glob("*.tmp")))
c, r = chiama("POST", f"/api/utenti/{uid2}/avatar", raw=_png(50, 50, "RGB", (1, 2, 3)))
verifica("avatar per il secondo utente", c == 200 and nt.percorso_avatar(uid2).exists())
c, r = chiama("DELETE", f"/api/utenti/{uid2}/avatar")
verifica("rimuovi avatar", c == 200 and r["avatar_v"] == 0 and not nt.percorso_avatar(uid2).exists())
c, r = chiama("POST", f"/api/utenti/{uid2}/avatar", raw=_png(50, 50, "RGB", (1, 2, 3)))
c, r = chiama("DELETE", f"/api/utenti/{uid2}", {"conferma": "Anna B"})
verifica("eliminando l'utente sparisce anche l'avatar", c == 200 and not nt.percorso_avatar(uid2).exists())

print("== eliminazioni")
c, r = chiama("DELETE", f"/api/foto/{fid3}")
verifica("elimina foto", c == 200 and not list((nt.cartella_foto() / f"u{uid}" / f"n{nid}").glob("*20261108*")))
c, r = chiama("DELETE", f"/api/nevi/{nid}")
cartella_neo = nt.cartella_foto() / f"u{uid}" / f"n{nid}"
verifica("elimina neo (con le sue foto)", c == 200 and not list(cartella_neo.glob("*")), str(list(cartella_neo.glob("*"))))
c, r = chiama("DELETE", f"/api/utenti/{uid}", {"conferma": "sbagliato"})
verifica("elimina utente richiede il nome esatto", c == 400)
c, r = chiama("DELETE", f"/api/utenti/{uid}", {"conferma": "Marco Rossi"})
verifica("elimina utente", c == 200 and not (nt.cartella_foto() / f"u{uid}").exists() and not (nt.cartella_rapporti() / f"u{uid}").exists()
         and not nt.percorso_avatar(uid).exists())
with nt.connetti() as c2:
    verifica("niente orfani nel database", c2.execute("SELECT COUNT(*) FROM nevi WHERE utente_id=?", (uid,)).fetchone()[0] == 0 and
             c2.execute("SELECT COUNT(*) FROM foto").fetchone()[0] == 0)

print("== chiusura")
c, r = chiama("POST", "/api/chiudi")
time.sleep(0.5)
verifica("chiusura richiesta", c == 200 and srv.chiusura_richiesta)

shutil.rmtree(tmp, ignore_errors=True)
print(f"\nRISULTATO: {ok_n} ok, {fail_n} falliti")
sys.exit(1 if fail_n else 0)
