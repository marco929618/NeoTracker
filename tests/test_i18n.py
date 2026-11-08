# Prova delle lingue (italiano, inglese, francese, tedesco, spagnolo) lato programma, senza browser.
# Uso: python3 test_i18n.py
#
# Controlla:
#   - i dizionari web/i18n_xx.js: ogni testo italiano ha la traduzione in tutte le lingue, con gli stessi segnaposto;
#   - il nome di ogni regione del corpo e di ogni sede usata nei nei è diverso dagli altri nella stessa lingua
#     (l'interfaccia ritrova il nome italiano dal nome tradotto: due nomi uguali la confonderebbero);
#   - l'impostazione "lingua" (valori ammessi, rifiuto di quelli sbagliati, valore predefinito);
#   - la pagina principale arriva con la lingua scelta già indicata e i dizionari vengono serviti;
#   - le finestrelle di errore all'avvio parlano la lingua scelta.
# La prova nel browser (schermate vere, formati di data e numeri) è in e2e_lingue.py.
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
ALTRE = ("en", "fr", "de", "es")


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


print("== dizionari")
verifica("le lingue del programma sono it + en fr de es", tuple(nt.LINGUE) == ("it",) + ALTRE, str(nt.LINGUE))
errori, avvisi, testi = trad.controlla()
verifica("tutti i testi tradotti in tutte le lingue, stessi segnaposto", not errori, "\n".join(errori[:10]))
verifica("nessun testo del dizionario è rimasto senza uso", not avvisi, "\n".join(avvisi[:10]))
verifica("ci sono centinaia di testi (l'estrattore funziona)", len(testi) > 500, len(testi))
for l in ALTRE:
    e2 = []
    d = trad.carica_dizionario(l, e2)
    uguali = [k for k, v in d.items() if v == k and len(k) > 25]
    verifica(f"[{l}] i testi lunghi non sono rimasti in italiano", len(uguali) <= 3, uguali[:3])

print("== nomi delle regioni e delle sedi")
corpo = (RADICE / "web" / "body.js").read_text(encoding="utf-8")
trovati = trad.raccogli_js([])
regioni = sorted(m for m, pos in trovati.items() if any(p.startswith("web/body.js") for p in pos))
mappa = (RADICE / "web" / "v_mappa.js").read_text(encoding="utf-8")
blocco = mappa[mappa.index("const SEDI_UTILI = ["):]
blocco = blocco[:blocco.index("];")]
sedi = [m.replace("\\'", "'") for m in re.findall(r"NT\.m\('((?:[^'\\]|\\.)*)'\)", blocco)]
verifica("trovate le 47 regioni del corpo (più i testi di body.js) e 11 sedi", len(regioni) >= 47 and len(sedi) == 11, (len(regioni), len(sedi)))
for l in ALTRE:
    e2 = []
    d = trad.carica_dizionario(l, e2)
    nomi = [d.get(x, x).lower() for x in regioni + sedi]
    doppi = sorted({n for n in nomi if nomi.count(n) > 1})
    verifica(f"[{l}] nessun nome di regione/sede ripetuto", not doppi, doppi)

print("== impostazione «lingua»")
c, r = chiama("GET", "/api/impostazioni")
verifica("predefinita: automatica", c == 200 and r["lingua"] == "auto", str(r))
for l in ("it",) + ALTRE + ("auto",):
    c, r = chiama("PUT", "/api/impostazioni", {"lingua": l})
    c2, r2 = chiama("GET", "/api/impostazioni")
    verifica(f"scelta «{l}» accettata e salvata", c == 200 and r2["lingua"] == l, str(r2))
chiama("PUT", "/api/impostazioni", {"lingua": "fr"})
for sbagliata in ("xx", "", "EN", "en ", "../it", 5, None, ["en"]):
    c, r = chiama("PUT", "/api/impostazioni", {"lingua": sbagliata})
    verifica(f"valore non ammesso {sbagliata!r} rifiutato", c == 400, (c, r))
c, r = chiama("GET", "/api/impostazioni")
verifica("dopo i rifiuti la scelta resta «fr»", r["lingua"] == "fr", str(r))

print("== pagina e dizionari serviti")
for l in ("it",) + ALTRE + ("auto",):
    chiama("PUT", "/api/impostazioni", {"lingua": l})
    c, pagina = chiama("GET", "/")
    verifica(f"la pagina indica la lingua «{l}»", c == 200 and f'<meta name="nt-lingua" content="{l}">'.encode() in pagina)
    verifica(f"[{l}] nessun segnaposto @@LINGUA@@ rimasto", b"@@LINGUA@@" not in pagina)
for l in ALTRE:
    c, js = chiama("GET", f"/i18n_{l}.js")
    verifica(f"dizionario {l} servito", c == 200 and b"NT_DIZIONARI" in js and f".{l} = ".encode() in js)
    verifica(f"[{l}] la pagina carica il dizionario", f'src="/i18n_{l}.js"'.encode() in pagina)
c, js = chiama("GET", "/i18n.js")
verifica("motore delle traduzioni servito", c == 200 and b"NT.t = " in js)

print("== messaggi del programma")
chiama("PUT", "/api/impostazioni", {"lingua": "it"})
c, r = chiama("PUT", "/api/impostazioni", {"lingua": "xx"})
verifica("l'errore del server è un testo italiano presente nei dizionari",
         r["errore"] == "Lingua non supportata." and all("Lingua non supportata." in trad.carica_dizionario(l, []) for l in ALTRE), str(r))

print("== finestrelle all'avvio")
for l, atteso in (("en", "NeoTracker is already running"), ("fr", "NeoTracker est déjà lancé"),
                  ("de", "NeoTracker läuft bereits"), ("es", "NeoTracker ya está en ejecución"), ("it", "NeoTracker è già acceso")):
    chiama("PUT", "/api/impostazioni", {"lingua": l})
    verifica(f"[{l}] «NeoTracker è già acceso»", nt.testo_avvio("NeoTracker è già acceso") == atteso, nt.testo_avvio("NeoTracker è già acceso"))
verifica("un testo sconosciuto resta com'è", nt.testo_avvio("Testo mai visto") == "Testo mai visto")

print(f"\n{ok_n} ok, {fail_n} falliti")
sys.exit(1 if fail_n else 0)
