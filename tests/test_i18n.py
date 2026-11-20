# Test of the languages (English, Italian, French, German, Spanish) on the program side, without a browser.
# Usage: python3 test_i18n.py
#
# It checks:
#   - the dictionaries web/i18n_xx.js: every English text has a translation in all languages, with the same placeholders;
#   - the name of every body region and of every site used for moles differs from the others in the same language
#     (the interface finds the English name again from the translated one: two equal names would confuse it);
#   - the "lingua" (language) setting (allowed values, rejection of wrong ones, default value);
#   - the main page arrives with the chosen language already indicated and the dictionaries are served;
#   - the start-up error windows speak the chosen language.
# The browser test (real screens, date and number formats) is in e2e_lingue.py.
import importlib.util
import json
import os
import re
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))

PORTA_APP = 8755
tmp = Path(tempfile.mkdtemp(prefix="neo_i18n_"))

spec = importlib.util.spec_from_file_location("neotracker", RADICE / "neotracker.py")
nt = importlib.util.module_from_spec(spec)
sys.modules["neotracker"] = nt
spec.loader.exec_module(nt)
nt.CARTELLA_DATI = tmp
nt.PORTA = PORTA_APP
nt.CARTELLA_REPO = tmp / "senza_progetti"
nt.CARTELLA_SCRIPT = RADICE
nt.inizializza_db()
srv = nt.Server(("127.0.0.1", PORTA_APP), nt.Gestore)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{PORTA_APP}"

spec_t = importlib.util.spec_from_file_location("traduzioni", RADICE / "tools" / "traduzioni.py")
trad = importlib.util.module_from_spec(spec_t)
spec_t.loader.exec_module(trad)

ok_n = fail_n = 0
ALTRE = ("it", "fr", "de", "es")        # languages that need a dictionary (English is the source text)


def verifica(nome, condizione, extra=""):
    global ok_n, fail_n
    if condizione:
        ok_n += 1
        print(f"  ok   {nome}")
    else:
        fail_n += 1
        print(f"  FAIL {nome} {extra}")


def chiama(metodo, percorso, corpo=None):
    h = {"X-NeoTracker": "1", "Cookie": f"{nt.NOME_COOKIE}={nt.TOKEN_SESSIONE}"}
    dati = None
    if corpo is not None:
        dati = json.dumps(corpo).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(URL + percorso, data=dati, method=metodo, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            cod, body, tipo = r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        cod, body, tipo = e.code, e.read(), e.headers.get("Content-Type", "")
    return cod, (json.loads(body) if "json" in tipo else body)


print("== dictionaries")
verifica("the languages of the program are en + it fr de es", tuple(nt.LINGUE) == ("en",) + ALTRE, str(nt.LINGUE))
errori, avvisi, testi = trad.controlla()
verifica("all texts translated into all languages, same placeholders", not errori, "\n".join(errori[:10]))
verifica("no dictionary text was left unused", not avvisi, "\n".join(avvisi[:10]))
verifica("there are hundreds of texts (the extractor works)", len(testi) > 500, len(testi))
for l in ALTRE:
    e2 = []
    d = trad.carica_dizionario(l, e2)
    uguali = [k for k, v in d.items() if v == k and len(k) > 25]
    verifica(f"[{l}] long texts were not left in English", len(uguali) <= 3, uguali[:3])

print("== names of regions and sites")
corpo = (RADICE / "web" / "body.js").read_text(encoding="utf-8")
trovati = trad.raccogli_js([])
regioni = sorted(m for m, pos in trovati.items() if any(p.startswith("web/body.js") for p in pos))
mappa = (RADICE / "web" / "v_mappa.js").read_text(encoding="utf-8")
blocco = mappa[mappa.index("const SEDI_UTILI = ["):]
blocco = blocco[:blocco.index("];")]
sedi = [m.replace("\\'", "'") for m in re.findall(r"NT\.m\('((?:[^'\\]|\\.)*)'\)", blocco)]
verifica("found the 47 body regions (plus the texts of body.js) and 11 sites", len(regioni) >= 47 and len(sedi) == 11, (len(regioni), len(sedi)))
for l in ALTRE:
    e2 = []
    d = trad.carica_dizionario(l, e2)
    nomi = [d.get(x, x).lower() for x in regioni + sedi]
    doppi = sorted({n for n in nomi if nomi.count(n) > 1})
    verifica(f"[{l}] no region/site name repeated", not doppi, doppi)

print("== \"lingua\" (language) setting")
c, r = chiama("GET", "/api/impostazioni")
verifica("default: automatic", c == 200 and r["lingua"] == "auto", str(r))
for l in ("en",) + ALTRE + ("auto",):
    c, r = chiama("PUT", "/api/impostazioni", {"lingua": l})
    c2, r2 = chiama("GET", "/api/impostazioni")
    verifica(f"choice \"{l}\" accepted and saved", c == 200 and r2["lingua"] == l, str(r2))
chiama("PUT", "/api/impostazioni", {"lingua": "fr"})
for sbagliata in ("xx", "", "EN", "en ", "../it", 5, None, ["en"]):
    c, r = chiama("PUT", "/api/impostazioni", {"lingua": sbagliata})
    verifica(f"value not allowed {sbagliata!r} rejected", c == 400, (c, r))
c, r = chiama("GET", "/api/impostazioni")
verifica("after the rejections the choice stays \"fr\"", r["lingua"] == "fr", str(r))

print("== page and dictionaries served")
for l in ("en",) + ALTRE + ("auto",):
    chiama("PUT", "/api/impostazioni", {"lingua": l})
    c, pagina = chiama("GET", "/")
    verifica(f"the page indicates the language \"{l}\"", c == 200 and f'<meta name="nt-lingua" content="{l}">'.encode() in pagina)
    verifica(f"[{l}] no @@LINGUA@@ placeholder left", b"@@LINGUA@@" not in pagina)
for l in ALTRE:
    c, js = chiama("GET", f"/i18n_{l}.js")
    verifica(f"dictionary {l} served", c == 200 and b"NT_DIZIONARI" in js and f".{l} = ".encode() in js)
    verifica(f"[{l}] the page loads the dictionary", f'src="/i18n_{l}.js"'.encode() in pagina)
c, js = chiama("GET", "/i18n.js")
verifica("translation engine served", c == 200 and b"NT.t = " in js)

print("== program messages")
chiama("PUT", "/api/impostazioni", {"lingua": "en"})
c, r = chiama("PUT", "/api/impostazioni", {"lingua": "xx"})
verifica("the server error is an English text present in the dictionaries",
         r["errore"] == "Language not supported." and all("Language not supported." in trad.carica_dizionario(l, []) for l in ALTRE), str(r))

print("== start-up windows")
for l, atteso in (("en", "NeoTracker is already running"), ("fr", "NeoTracker est déjà lancé"),
                  ("de", "NeoTracker läuft bereits"), ("es", "NeoTracker ya está en ejecución"), ("it", "NeoTracker è già acceso")):
    chiama("PUT", "/api/impostazioni", {"lingua": l})
    verifica(f"[{l}] \"NeoTracker is already running\"", nt.testo_avvio("NeoTracker is already running") == atteso, nt.testo_avvio("NeoTracker is already running"))
verifica("an unknown text stays as it is", nt.testo_avvio("Never seen text") == "Never seen text")

print(f"\n{ok_n} ok, {fail_n} failed")
sys.exit(1 if fail_n else 0)
