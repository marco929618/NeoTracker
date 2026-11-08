# Prove di sicurezza di NeoTracker (chiave di sessione, intestazioni, percorsi, caricamenti, limiti).
# Uso: python3 test_sicurezza.py
import http.client
import importlib.util
import io
import json
import os
import shutil
import socket
import stat
import sys
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
PORTA = 8753
tmp = Path(tempfile.mkdtemp(prefix="neo_sic_"))


def carica():
    spec = importlib.util.spec_from_file_location("neotracker", Path(__file__).parent.parent / "neotracker.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


nt = carica()
nt2 = carica()
nt.CARTELLA_DATI = tmp
nt.PORTA = PORTA
nt.inizializza_db()
srv = nt.Server(("127.0.0.1", PORTA), nt.Gestore)
threading.Thread(target=srv.serve_forever, daemon=True).start()
COOKIE = f"{nt.NOME_COOKIE}={nt.TOKEN_SESSIONE}"
ok_n = fail_n = 0


def verifica(nome, cond, extra=""):
    global ok_n, fail_n
    if cond:
        ok_n += 1
        print(f"  ok   {nome}")
    else:
        fail_n += 1
        print(f"  FAIL {nome} {extra}")


def rich(metodo, percorso, corpo=None, header=None, cookie=True, x=True, host=None):
    """Una richiesta 'a basso livello': restituisce (codice, intestazioni, corpo)."""
    h = {"Host": host or f"127.0.0.1:{PORTA}"}
    if cookie is True:
        h["Cookie"] = COOKIE
    elif cookie:
        h["Cookie"] = cookie
    if x:
        h["X-NeoTracker"] = "1"
    h.update(header or {})
    con = http.client.HTTPConnection("127.0.0.1", PORTA, timeout=4)
    con.putrequest(metodo, percorso, skip_host=True, skip_accept_encoding=True)
    for k, v in h.items():
        con.putheader(k, v)
    if corpo is not None:
        con.putheader("Content-Length", str(len(corpo)))
    con.endheaders(corpo)
    try:
        r = con.getresponse()
        dati = r.read()
    except socket.timeout:                      # risposta che non finisce mai (es. il collegamento "finestra aperta"): codice 0
        con.close()
        return 0, type("R", (), {"getheader": lambda s, n, d=None: d, "getheaders": lambda s: [], "msg": None})(), b""
    out = (r.status, r, dati)
    con.close()
    return out


print("== senza la chiave di sessione non si entra")
c, r, d = rich("GET", "/api/ping", cookie=False)
verifica("ping libero (serve a capire se NeoTracker è già acceso)", c == 200 and json.loads(d)["protetto"] is True)
for metodo, perc in [("GET", "/"), ("GET", "/app.js"), ("GET", "/index.html"), ("GET", "/api/utenti"), ("GET", "/api/stato"),
                     ("GET", "/api/impostazioni"), ("GET", "/foto/1/mini"), ("GET", "/foto/1/originale"), ("GET", "/api/utenti/1/avatar"),
                     ("GET", "/api/presenza?id=abc"), ("GET", "/api/uv"), ("GET", "/api/letteratura/temi")]:
    c, r, d = rich(metodo, perc, cookie=False)
    verifica(f"{metodo} {perc} senza cookie -> 403", c == 403, str(c))
for metodo, perc in [("POST", "/api/utenti"), ("POST", "/api/chiudi"), ("PUT", "/api/impostazioni"), ("DELETE", "/api/utenti/1"),
                     ("POST", "/api/battito"), ("POST", "/api/foto/1/analizza"), ("POST", "/api/utenti/1/avatar")]:
    c, r, d = rich(metodo, perc, corpo=b"{}", cookie=False)
    verifica(f"{metodo} {perc} senza cookie -> 403 (anche con X-NeoTracker)", c == 403, str(c))
verifica("il server non si è spento (POST /api/chiudi respinto)", not srv.chiusura_richiesta)
c, r, d = rich("GET", "/", cookie=False)
verifica("la pagina 403 è HTML fisso, senza script", b"<script" not in d and b"Accesso non autorizzato" in d and "text/html" in r.getheader("Content-Type"))

print("== cookie sbagliati")
for nome, ck in [("chiave sbagliata", f"{nt.NOME_COOKIE}=sbagliata"), ("chiave troncata", f"{nt.NOME_COOKIE}={nt.TOKEN_SESSIONE[:-1]}"),
                 ("chiave con aggiunta", f"{nt.NOME_COOKIE}={nt.TOKEN_SESSIONE}x"), ("chiave di un altro avvio", f"{nt.NOME_COOKIE}={nt2.TOKEN_SESSIONE}"),
                 ("nome cookie diverso", f"altro={nt.TOKEN_SESSIONE}"), ("cookie vuoto", f"{nt.NOME_COOKIE}="),
                 ("chiave non ascii", f"{nt.NOME_COOKIE}=è€")]:
    try:
        c, r, d = rich("GET", "/api/utenti", cookie=ck)
    except (UnicodeEncodeError, http.client.HTTPException):
        c = 403
    verifica(f"{nome} -> 403", c == 403, str(c))
c, r, d = rich("GET", "/api/utenti", cookie=f"x=1; {nt.NOME_COOKIE}={nt.TOKEN_SESSIONE}; y=2")
verifica("cookie giusto in mezzo ad altri -> accettato", c == 200)
verifica("due avvii hanno chiavi diverse e lunghe", nt.TOKEN_SESSIONE != nt2.TOKEN_SESSIONE and len(nt.TOKEN_SESSIONE) >= 40)

print("== consegna della chiave alla finestra (?avvio=)")
c, r, d = rich("GET", f"/?avvio={nt.TOKEN_SESSIONE}", cookie=False)
sc = r.getheader("Set-Cookie") or ""
verifica("chiave giusta -> 302 verso / (indirizzo ripulito)", c == 302 and r.getheader("Location") == "/", f"{c} {r.getheader('Location')}")
verifica("cookie HttpOnly + SameSite=Strict + Path=/", "HttpOnly" in sc and "SameSite=Strict" in sc and "Path=/" in sc and sc.startswith(COOKIE), sc)
verifica("cookie di sessione (senza scadenza: sparisce chiudendo il browser)", "Expires" not in sc and "Max-Age" not in sc)
c, r, d = rich("GET", "/", cookie=COOKIE)
verifica("poi con il cookie la pagina si apre", c == 200 and b"<title>" in d)
c, r, d = rich("GET", "/?avvio=sbagliata", cookie=False)
verifica("chiave sbagliata -> 403 e nessun cookie", c == 403 and not r.getheader("Set-Cookie"))
c, r, d = rich("GET", f"/api/utenti?avvio={nt.TOKEN_SESSIONE}", cookie=False)
verifica("?avvio= vale solo sulla pagina principale (non su /api)", c == 403 and not r.getheader("Set-Cookie"))
c, r, d = rich("POST", f"/?avvio={nt.TOKEN_SESSIONE}", corpo=b"", cookie=False)
verifica("?avvio= con POST non vale", c in (403, 404, 405) and not r.getheader("Set-Cookie"), str(c))

print("== host, origine, CSRF")
c, r, d = rich("GET", "/api/utenti", host="evil.example.com")
verifica("Host estraneo (DNS rebinding) -> 403 anche col cookie", c == 403)
c, r, d = rich("GET", "/api/utenti", host=f"127.0.0.1.evil.com:{PORTA}")
verifica("Host che 'somiglia' -> 403", c == 403)
c, r, d = rich("GET", "/api/utenti", host="127.0.0.1")
verifica("Host senza porta -> 403", c == 403)
c, r, d = rich("GET", "/api/utenti", header={"Origin": "https://evil.example.com"})
verifica("Origin estranea -> 403 anche col cookie", c == 403)
c, r, d = rich("GET", "/api/utenti", header={"Origin": "null"})
verifica("Origin 'null' (pagine in sandbox) -> 403", c == 403)
c, r, d = rich("GET", "/api/utenti", header={"Origin": f"http://127.0.0.1:{PORTA}"})
verifica("Origin della finestra -> ok", c == 200)
c, r, d = rich("POST", "/api/utenti", corpo=b'{"nome":"csrf"}', x=False, header={"Content-Type": "text/plain"})
verifica("POST 'da modulo' senza X-NeoTracker -> 403 anche col cookie", c == 403)
c, r, d = rich("OPTIONS", "/api/utenti")
verifica("OPTIONS (preflight CORS) rifiutato e senza Access-Control-*", c == 403 and not r.getheader("Access-Control-Allow-Origin"))
verifica("nessuna intestazione CORS permissiva sulle risposte", rich("GET", "/api/utenti")[1].getheader("Access-Control-Allow-Origin") is None)
c, r, d = rich("HEAD", "/api/utenti")
verifica("HEAD non ammesso", c == 405)

print("== intestazioni di sicurezza")
def intest(r):
    return {k.lower(): v for k, v in r.getheaders()}
c, r, d = rich("GET", "/")
i = intest(r)
verifica("pagina: CSP rigida (niente script inline, niente rete esterna)", "script-src 'self'" in i["content-security-policy"] and "connect-src 'self'" in i["content-security-policy"]
         and "frame-ancestors 'none'" in i["content-security-policy"] and "unsafe-inline" not in i["content-security-policy"].split("script-src")[1].split(";")[0])
for nome, atteso in [("x-content-type-options", "nosniff"), ("x-frame-options", "DENY"), ("referrer-policy", "no-referrer"), ("cache-control", "no-store"),
                     ("cross-origin-opener-policy", "same-origin"), ("cross-origin-resource-policy", "same-origin")]:
    verifica(f"pagina: {nome}", i.get(nome) == atteso, str(i.get(nome)))
verifica("pagina: Permissions-Policy (camera/microfono off)", "camera=()" in i.get("permissions-policy", "") and "microphone=()" in i.get("permissions-policy", ""))
verifica("il server non dichiara la versione di Python", "Python" not in (r.getheader("Server") or ""), r.getheader("Server"))
c, r, d = rich("GET", "/api/utenti")
i = intest(r)
verifica("API JSON: nosniff + no-store + tipo JSON", i["x-content-type-options"] == "nosniff" and i["cache-control"] == "no-store" and "application/json" in i["content-type"])
c, r, d = rich("GET", "/api/inesistente")
verifica("anche gli errori hanno le intestazioni", c == 404 and r.getheader("X-Frame-Options") == "DENY")
c, r, d = rich("GET", "/", cookie=False)
verifica("anche la pagina 403 ha CSP e nosniff", r.getheader("Content-Security-Policy") and r.getheader("X-Content-Type-Options") == "nosniff")
c, r, d = rich("POST", "/api/utenti", corpo=json.dumps({"nome": "Prova Sic"}).encode())
uid = json.loads(d)["id"]
c, r, d = rich("GET", f"/api/utenti/{uid}/avatar")
verifica("avatar assente -> 404 JSON", c == 404)

print("== immagini: intestazioni e contenuti")
from PIL import Image
b = io.BytesIO(); Image.new("RGB", (400, 300), (30, 90, 200)).save(b, "JPEG")
c, r, d = rich("POST", f"/api/utenti/{uid}/avatar", corpo=b.getvalue())
verifica("avatar caricato", c == 200)
c, r, d = rich("GET", f"/api/utenti/{uid}/avatar")
i = intest(r)
verifica("avatar: CSP 'none'+sandbox, nosniff, JPEG", i["content-security-policy"] == "default-src 'none'; sandbox" and i["x-content-type-options"] == "nosniff" and i["content-type"] == "image/jpeg")
verifica("avatar: una sola intestazione Cache-Control (nessun conflitto)", len(r.msg.get_all("Cache-Control")) == 1 and "private" in i["cache-control"], str(r.msg.get_all("Cache-Control")))
c, r, d = rich("POST", "/api/utenti/%d/nevi" % uid, corpo=json.dumps({"nome": "n", "vista": "fronte", "x": .5, "y": .5}).encode())
nid = json.loads(d)["id"]
c, r, d = rich("POST", f"/api/nevi/{nid}/foto?data=2026-01-02", corpo=b.getvalue())
fid = json.loads(d)["id"]
c, r, d = rich("GET", f"/foto/{fid}/originale")
verifica("foto originale: CSP 'none'+sandbox, una sola Cache-Control", c == 200 and r.getheader("Content-Security-Policy") == "default-src 'none'; sandbox" and len(r.msg.get_all("Cache-Control")) == 1)

print("== caricamenti pericolosi")
html_finto = b"<html><script>alert(1)</script></html>"
c, r, d = rich("POST", f"/api/nevi/{nid}/foto", corpo=html_finto)
verifica("HTML travestito da foto -> 400", c == 400)
c, r, d = rich("POST", f"/api/nevi/{nid}/foto", corpo=b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>")
verifica("SVG come foto -> 400", c == 400)
c, r, d = rich("POST", f"/api/nevi/{nid}/foto", corpo=b"\xff\xd8\xff" + b"<script>alert(1)</script>" * 20)
verifica("JPEG finto con script dentro -> 400", c == 400)
bomba = io.BytesIO(); Image.new("1", (20000, 20000)).save(bomba, "PNG")
c, r, d = rich("POST", f"/api/nevi/{nid}/foto", corpo=bomba.getvalue())
verifica("foto-trappola (400 megapixel, file piccolo) -> 400", c == 400 and len(bomba.getvalue()) < 200_000)
c, r, d = rich("POST", f"/api/nevi/{nid}/foto", corpo=b"")
verifica("corpo vuoto -> 400", c == 400)
sk = socket.create_connection(("127.0.0.1", PORTA), timeout=10)
sk.sendall((f"POST /api/nevi/{nid}/foto HTTP/1.0\r\nHost: 127.0.0.1:{PORTA}\r\nX-NeoTracker: 1\r\nCookie: {COOKIE}\r\nContent-Length: {nt.MAX_MB_FOTO * 1048576 * 5}\r\n\r\n").encode())
verifica("Content-Length enorme -> 413 subito (il corpo non viene letto)", sk.recv(100).startswith(b"HTTP/1.0 413"))
sk.close()
c, r, d = rich("POST", "/api/utenti", corpo=b"{non json", header={"Content-Type": "application/json"})
verifica("JSON rotto -> 400", c == 400)
c, r, d = rich("POST", "/api/utenti", corpo=b'["a"]')
verifica("JSON che non è un oggetto -> 400", c == 400)
c, r, d = rich("POST", "/api/utenti", corpo=b'{"nome": "' + b"A" * 5000 + b'"}')
verifica("nome lunghissimo -> 400", c == 400)

print("== percorsi, SQL e testi strani")
for perc in ["/foto/../../etc/passwd", "/foto/%2e%2e/%2e%2e/etc/passwd", "/../neotracker.db", "/neotracker.db", "/impostazioni.json",
             "/..%2fneotracker.db", "/%2e%2e/%2e%2e/etc/passwd", "/sessione.token", "//etc/passwd", "/app.js/../../neotracker.db"]:
    c, r, d = rich("GET", perc)
    verifica(f"GET {perc} -> nessun file riservato", c in (400, 404) and b"SQLite" not in d and b"root:" not in d and nt.TOKEN_SESSIONE.encode() not in d, str(c))
with nt.connetti() as con:                                  # una riga 'avvelenata': il nome del file esce dalla cartella foto
    cur = con.execute("INSERT INTO foto (nevo_id, file, scattata_il, creato) VALUES (?,?,?,?)", (nid, "../../neotracker.db", "2026-01-01", "x"))
    fid_x = cur.lastrowid
    cur = con.execute("INSERT INTO foto (nevo_id, file, scattata_il, creato) VALUES (?,?,?,?)", (nid, str(tmp / "neotracker.db"), "2026-01-01", "x"))
    fid_y = cur.lastrowid
for f in (fid_x, fid_y):
    for tipo in ("originale", "mini"):
        c, r, d = rich("GET", f"/foto/{f}/{tipo}")
        verifica(f"foto con percorso fuori cartella ({f}/{tipo}) non viene servita", c == 404 and b"SQLite format" not in d, str(c))
for nome in ["'; DROP TABLE utenti;--", "Robert'); DELETE FROM nevi;--", "<img src=x onerror=alert(1)>", "<script>alert(1)</script>", "\" onmouseover=\"alert(1)", "../../x", "x" * 60]:
    c, r, d = rich("POST", "/api/utenti", corpo=json.dumps({"nome": nome}).encode())
    verifica(f"nome strano accettato come semplice testo: {nome[:24]!r}", c == 200)
c, r, d = rich("GET", "/api/utenti")
nomi = [u["nome"] for u in json.loads(d)]
verifica("le tabelle ci sono ancora e i nomi tornano identici", "<script>alert(1)</script>" in nomi and "'; DROP TABLE utenti;--" in nomi and "application/json" in r.getheader("Content-Type"))
with nt.connetti() as con:
    verifica("nessuna tabella persa", con.execute("SELECT COUNT(*) FROM nevi").fetchone()[0] >= 1)
c, r, d = rich("GET", "/api/utenti/1%20OR%201=1")
verifica("id non numerico nell'indirizzo -> 404", c == 404)
c, r, d = rich("GET", "/api/letteratura/cerca?q=" + urllib.parse.quote("melanoma\" OR 1=1 --"))
verifica("ricerca libera con caratteri strani non rompe nulla", c in (200, 502), str(c))
c, r, d = rich("GET", "/api/presenza?id=" + "a" * 200)
verifica("identificativo di pagina troppo lungo -> 400", c == 400)
c, r, d = rich("GET", "/api/presenza?id=a%0d%0aSet-Cookie:x=1")
verifica("identificativo con a-capo -> 400 (niente iniezione di intestazioni)", c == 400)
c, r, d = rich("GET", "/a" * 1500)
verifica("indirizzo lunghissimo -> 414", c == 414)

print("== impostazioni e segreti")
c, r, d = rich("PUT", "/api/impostazioni", corpo=json.dumps({"openweather_key": "ABCD1234efgh5678"}).encode())
j = json.loads(d)
verifica("la chiave API non viene mai restituita", "openweather_key" not in j and j["ha_chiave_owm"] and "ABCD1234" not in d.decode())
c, r, d = rich("GET", "/api/stato")
verifica("/api/stato non contiene chiavi", b"ABCD1234" not in d and nt.TOKEN_SESSIONE.encode() not in d)
if os.name != "nt":
    modo = stat.S_IMODE((tmp / "impostazioni.json").stat().st_mode)
    verifica("impostazioni.json leggibile solo dal proprietario (0600)", modo == 0o600, oct(modo))
verifica("nessun file .tmp lasciato", not list(tmp.glob("*.tmp")))
c, r, d = rich("PUT", "/api/impostazioni", corpo=json.dumps({"fonte_uv": "evil", "avvertenze_accettate": "99", "ncbi_email": "non-una-email"}).encode())
verifica("valori non ammessi nelle impostazioni -> 400", c == 400)
c, r, d = rich("PUT", "/api/impostazioni", corpo=json.dumps({"CARTELLA_DATI": "/etc", "porta": 1, "openweather_key": ""}).encode())
verifica("campi sconosciuti ignorati (non si può cambiare la cartella dati)", c == 200 and "CARTELLA_DATI" not in json.loads((tmp / "impostazioni.json").read_text()))

print("== file della chiave di sessione")
nt.scrivi_token_su_file()
f = nt.percorso_token()
verifica("il file della chiave esiste e contiene la chiave", f.exists() and f.read_text() == nt.TOKEN_SESSIONE and nt.leggi_token_da_file() == nt.TOKEN_SESSIONE)
if os.name != "nt":
    verifica("file chiave 0600", stat.S_IMODE(f.stat().st_mode) == 0o600, oct(stat.S_IMODE(f.stat().st_mode)))
f.write_text("<script>alert(1)</script>")
verifica("contenuto strano nel file -> ignorato", nt.leggi_token_da_file() == "")
f.write_text("corta")
verifica("chiave troppo corta -> ignorata", nt.leggi_token_da_file() == "")
nt.cancella_token_file()
verifica("cancellazione del file della chiave", not f.exists() and nt.leggi_token_da_file() == "")
nt.cancella_token_file()
verifica("cancellare due volte non dà errore", True)

print("== limiti di collegamenti")
vecchio_timeout = nt.Gestore.timeout
nt.Gestore.timeout = 2
sk = socket.create_connection(("127.0.0.1", PORTA), timeout=10)
t0 = time.time()
sk.settimeout(8)
try:
    muto = sk.recv(10)
except socket.timeout:
    muto = None
verifica("collegamento muto chiuso dal server entro pochi secondi", muto == b"" and time.time() - t0 < 6, f"{muto} {time.time() - t0:.1f}s")
sk.close()
nt.Gestore.timeout = vecchio_timeout
socks = []
for n in range(nt.MAX_PRESENZE):
    s = socket.create_connection(("127.0.0.1", PORTA), timeout=10)
    s.sendall(f"GET /api/presenza?id=pag{n} HTTP/1.1\r\nHost: 127.0.0.1:{PORTA}\r\nCookie: {COOKIE}\r\n\r\n".encode())
    socks.append(s)
time.sleep(1.0)
primo = socks[0].recv(200)
verifica("i collegamenti 'finestra aperta' entro il limite funzionano", primo.startswith(b"HTTP/1.0 200") or primo.startswith(b"HTTP/1.1 200"), str(primo[:30]))
c, r, d = rich("GET", "/api/presenza?id=troppi")
verifica(f"il {nt.MAX_PRESENZE + 1}° collegamento -> 429", c == 429, str(c))
for s in socks:
    s.close()
for _ in range(60):
    if nt._presenze_aperte[0] == 0:
        break
    time.sleep(0.1)
verifica("chiusi i collegamenti, il contatore torna a zero", nt._presenze_aperte[0] == 0, str(nt._presenze_aperte[0]))

print("== richieste verso internet")
import urllib.request as _ur
from http.server import BaseHTTPRequestHandler, HTTPServer


class _Finto(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/grande":
            self.send_response(200); self.end_headers()
            try:
                self.wfile.write(b"x" * 3_000_000)
            except OSError:
                pass                                    # il client ha già smesso di leggere: è proprio il caso provato
        elif self.path == "/verso-file":
            self.send_response(302); self.send_header("Location", "file:///etc/passwd"); self.end_headers()
        elif self.path == "/verso-ftp":
            self.send_response(302); self.send_header("Location", "ftp://127.0.0.1/x"); self.end_headers()
        else:
            self.send_response(200); self.end_headers(); self.wfile.write(b"{}")


fs = HTTPServer(("127.0.0.1", 8797), _Finto)
threading.Thread(target=fs.serve_forever, daemon=True).start()
def prova(url, massimo=None):
    try:
        return nt._leggi_web(_ur.Request(url), 5, *([massimo] if massimo else []))
    except nt.ErroreServizio as e:
        return "ErroreServizio: " + str(e)
    except Exception as e:
        return "Errore: " + type(e).__name__
verifica("indirizzo file:// rifiutato", str(prova("file:///etc/passwd")).startswith("ErroreServizio"))
verifica("indirizzo ftp:// rifiutato", str(prova("ftp://example.com/x")).startswith("ErroreServizio"))
verifica("http verso un sito esterno rifiutato (solo https)", str(prova("http://example.com/")).startswith("ErroreServizio"))
verifica("http verso questo computer ammesso (prove)", prova("http://127.0.0.1:8797/ok") == b"{}")
verifica("risposta troppo grande interrotta", prova("http://127.0.0.1:8797/grande", 100_000) == "ErroreServizio: risposta troppo grande")
verifica("reindirizzamento verso file:// non seguito", str(prova("http://127.0.0.1:8797/verso-file")).startswith("Errore"))
verifica("reindirizzamento verso ftp:// non seguito", str(prova("http://127.0.0.1:8797/verso-ftp")).startswith("Errore"))
fs.shutdown()
bomba_xml = b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><PubmedArticleSet><PubmedArticle>&b;</PubmedArticle></PubmedArticleSet>'
verifica("XML con dichiarazioni ENTITY (bomba) ignorato", nt.interpreta_xml_pubmed(bomba_xml) == [])
verifica("XML PubMed normale con DOCTYPE esterno ancora letto", nt.interpreta_xml_pubmed(
    b'<?xml version="1.0"?><!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2024//EN" "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_240101.dtd">'
    b'<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID><Article><ArticleTitle>Titolo</ArticleTitle></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>') != [])

shutil.rmtree(tmp, ignore_errors=True)
print(f"\nRISULTATO: {ok_n} ok, {fail_n} falliti")
sys.exit(1 if fail_n else 0)
