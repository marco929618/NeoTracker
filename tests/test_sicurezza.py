# Security tests of NeoTracker (session key, headers, paths, uploads, limits).
# Usage: python3 test_sicurezza.py
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
    """A 'low-level' request: returns (code, headers, body)."""
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
    except socket.timeout:                      # response that never ends (e.g. the "window open" connection): code 0
        con.close()
        return 0, type("R", (), {"getheader": lambda s, n, d=None: d, "getheaders": lambda s: [], "msg": None})(), b""
    out = (r.status, r, dati)
    con.close()
    return out


print("== without the session key you cannot get in")
c, r, d = rich("GET", "/api/ping", cookie=False)
verifica("free ping (used to find out whether NeoTracker is already running)", c == 200 and json.loads(d)["protetto"] is True)
for metodo, perc in [("GET", "/"), ("GET", "/app.js"), ("GET", "/index.html"), ("GET", "/api/utenti"), ("GET", "/api/stato"),
                     ("GET", "/api/impostazioni"), ("GET", "/foto/1/mini"), ("GET", "/foto/1/originale"), ("GET", "/api/utenti/1/avatar"),
                     ("GET", "/api/presenza?id=abc"), ("GET", "/api/uv"), ("GET", "/api/letteratura/temi")]:
    c, r, d = rich(metodo, perc, cookie=False)
    verifica(f"{metodo} {perc} without cookie -> 403", c == 403, str(c))
for metodo, perc in [("POST", "/api/utenti"), ("POST", "/api/chiudi"), ("PUT", "/api/impostazioni"), ("DELETE", "/api/utenti/1"),
                     ("POST", "/api/battito"), ("POST", "/api/foto/1/analizza"), ("POST", "/api/utenti/1/avatar")]:
    c, r, d = rich(metodo, perc, corpo=b"{}", cookie=False)
    verifica(f"{metodo} {perc} without cookie -> 403 (even with X-NeoTracker)", c == 403, str(c))
verifica("the server did not shut down (POST /api/chiudi rejected)", not srv.chiusura_richiesta)
c, r, d = rich("GET", "/", cookie=False)
verifica("the 403 page is fixed HTML, without scripts", b"<script" not in d and b"Access denied" in d and "text/html" in r.getheader("Content-Type"))

print("== wrong cookies")
for nome, ck in [("wrong key", f"{nt.NOME_COOKIE}=sbagliata"), ("truncated key", f"{nt.NOME_COOKIE}={nt.TOKEN_SESSIONE[:-1]}"),
                 ("key with an addition", f"{nt.NOME_COOKIE}={nt.TOKEN_SESSIONE}x"), ("key from another start", f"{nt.NOME_COOKIE}={nt2.TOKEN_SESSIONE}"),
                 ("different cookie name", f"altro={nt.TOKEN_SESSIONE}"), ("empty cookie", f"{nt.NOME_COOKIE}="),
                 ("non-ascii key", f"{nt.NOME_COOKIE}=è€")]:
    try:
        c, r, d = rich("GET", "/api/utenti", cookie=ck)
    except (UnicodeEncodeError, http.client.HTTPException):
        c = 403
    verifica(f"{nome} -> 403", c == 403, str(c))
c, r, d = rich("GET", "/api/utenti", cookie=f"x=1; {nt.NOME_COOKIE}={nt.TOKEN_SESSIONE}; y=2")
verifica("right cookie among others -> accepted", c == 200)
verifica("two starts have different, long keys", nt.TOKEN_SESSIONE != nt2.TOKEN_SESSIONE and len(nt.TOKEN_SESSIONE) >= 40)

print("== delivery of the key to the window (?avvio=)")
c, r, d = rich("GET", f"/?avvio={nt.TOKEN_SESSIONE}", cookie=False)
sc = r.getheader("Set-Cookie") or ""
verifica("right key -> 302 to / (address cleaned)", c == 302 and r.getheader("Location") == "/", f"{c} {r.getheader('Location')}")
verifica("cookie HttpOnly + SameSite=Strict + Path=/", "HttpOnly" in sc and "SameSite=Strict" in sc and "Path=/" in sc and sc.startswith(COOKIE), sc)
verifica("session cookie (no expiry: it disappears when the browser is closed)", "Expires" not in sc and "Max-Age" not in sc)
c, r, d = rich("GET", "/", cookie=COOKIE)
verifica("then with the cookie the page opens", c == 200 and b"<title>" in d)
c, r, d = rich("GET", "/?avvio=sbagliata", cookie=False)
verifica("wrong key -> 403 and no cookie", c == 403 and not r.getheader("Set-Cookie"))
c, r, d = rich("GET", f"/api/utenti?avvio={nt.TOKEN_SESSIONE}", cookie=False)
verifica("?avvio= only counts on the main page (not on /api)", c == 403 and not r.getheader("Set-Cookie"))
c, r, d = rich("POST", f"/?avvio={nt.TOKEN_SESSIONE}", corpo=b"", cookie=False)
verifica("?avvio= with POST does not count", c in (403, 404, 405) and not r.getheader("Set-Cookie"), str(c))

print("== host, origin, CSRF")
c, r, d = rich("GET", "/api/utenti", host="evil.example.com")
verifica("foreign Host (DNS rebinding) -> 403 even with the cookie", c == 403)
c, r, d = rich("GET", "/api/utenti", host=f"127.0.0.1.evil.com:{PORTA}")
verifica("Host that 'looks similar' -> 403", c == 403)
c, r, d = rich("GET", "/api/utenti", host="127.0.0.1")
verifica("Host without port -> 403", c == 403)
c, r, d = rich("GET", "/api/utenti", header={"Origin": "https://evil.example.com"})
verifica("foreign Origin -> 403 even with the cookie", c == 403)
c, r, d = rich("GET", "/api/utenti", header={"Origin": "null"})
verifica("Origin 'null' (sandboxed pages) -> 403", c == 403)
c, r, d = rich("GET", "/api/utenti", header={"Origin": f"http://127.0.0.1:{PORTA}"})
verifica("Origin of the window -> ok", c == 200)
c, r, d = rich("POST", "/api/utenti", corpo=b'{"nome":"csrf"}', x=False, header={"Content-Type": "text/plain"})
verifica("POST 'from a form' without X-NeoTracker -> 403 even with the cookie", c == 403)
c, r, d = rich("OPTIONS", "/api/utenti")
verifica("OPTIONS (CORS preflight) rejected and without Access-Control-*", c == 403 and not r.getheader("Access-Control-Allow-Origin"))
verifica("no permissive CORS header on the responses", rich("GET", "/api/utenti")[1].getheader("Access-Control-Allow-Origin") is None)
c, r, d = rich("HEAD", "/api/utenti")
verifica("HEAD not allowed", c == 405)

print("== security headers")
def intest(r):
    return {k.lower(): v for k, v in r.getheaders()}
c, r, d = rich("GET", "/")
i = intest(r)
verifica("page: strict CSP (no inline scripts, no external network)", "script-src 'self'" in i["content-security-policy"] and "connect-src 'self'" in i["content-security-policy"]
         and "frame-ancestors 'none'" in i["content-security-policy"] and "unsafe-inline" not in i["content-security-policy"].split("script-src")[1].split(";")[0])
for nome, atteso in [("x-content-type-options", "nosniff"), ("x-frame-options", "DENY"), ("referrer-policy", "no-referrer"), ("cache-control", "no-store"),
                     ("cross-origin-opener-policy", "same-origin"), ("cross-origin-resource-policy", "same-origin")]:
    verifica(f"page: {nome}", i.get(nome) == atteso, str(i.get(nome)))
verifica("page: Permissions-Policy (camera/microphone off)", "camera=()" in i.get("permissions-policy", "") and "microphone=()" in i.get("permissions-policy", ""))
verifica("the server does not declare the Python version", "Python" not in (r.getheader("Server") or ""), r.getheader("Server"))
c, r, d = rich("GET", "/api/utenti")
i = intest(r)
verifica("API JSON: nosniff + no-store + JSON type", i["x-content-type-options"] == "nosniff" and i["cache-control"] == "no-store" and "application/json" in i["content-type"])
c, r, d = rich("GET", "/api/inesistente")
verifica("errors have the headers too", c == 404 and r.getheader("X-Frame-Options") == "DENY")
c, r, d = rich("GET", "/", cookie=False)
verifica("the 403 page also has CSP and nosniff", r.getheader("Content-Security-Policy") and r.getheader("X-Content-Type-Options") == "nosniff")
c, r, d = rich("POST", "/api/utenti", corpo=json.dumps({"nome": "Prova Sic"}).encode())
uid = json.loads(d)["id"]
c, r, d = rich("GET", f"/api/utenti/{uid}/avatar")
verifica("missing avatar -> 404 JSON", c == 404)

print("== images: headers and contents")
from PIL import Image
b = io.BytesIO(); Image.new("RGB", (400, 300), (30, 90, 200)).save(b, "JPEG")
c, r, d = rich("POST", f"/api/utenti/{uid}/avatar", corpo=b.getvalue())
verifica("avatar uploaded", c == 200)
c, r, d = rich("GET", f"/api/utenti/{uid}/avatar")
i = intest(r)
verifica("avatar: CSP 'none'+sandbox, nosniff, JPEG", i["content-security-policy"] == "default-src 'none'; sandbox" and i["x-content-type-options"] == "nosniff" and i["content-type"] == "image/jpeg")
verifica("avatar: a single Cache-Control header (no conflict)", len(r.msg.get_all("Cache-Control")) == 1 and "private" in i["cache-control"], str(r.msg.get_all("Cache-Control")))
c, r, d = rich("POST", "/api/utenti/%d/nevi" % uid, corpo=json.dumps({"nome": "n", "vista": "fronte", "x": .5, "y": .5}).encode())
nid = json.loads(d)["id"]
c, r, d = rich("POST", f"/api/nevi/{nid}/foto?data=2026-01-02", corpo=b.getvalue())
fid = json.loads(d)["id"]
c, r, d = rich("GET", f"/foto/{fid}/originale")
verifica("original photo: CSP 'none'+sandbox, a single Cache-Control", c == 200 and r.getheader("Content-Security-Policy") == "default-src 'none'; sandbox" and len(r.msg.get_all("Cache-Control")) == 1)

print("== dangerous uploads")
html_finto = b"<html><script>alert(1)</script></html>"
c, r, d = rich("POST", f"/api/nevi/{nid}/foto", corpo=html_finto)
verifica("HTML disguised as a photo -> 400", c == 400)
c, r, d = rich("POST", f"/api/nevi/{nid}/foto", corpo=b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>")
verifica("SVG as a photo -> 400", c == 400)
c, r, d = rich("POST", f"/api/nevi/{nid}/foto", corpo=b"\xff\xd8\xff" + b"<script>alert(1)</script>" * 20)
verifica("fake JPEG with a script inside -> 400", c == 400)
bomba = io.BytesIO(); Image.new("1", (20000, 20000)).save(bomba, "PNG")
c, r, d = rich("POST", f"/api/nevi/{nid}/foto", corpo=bomba.getvalue())
verifica("trap photo (400 megapixels, small file) -> 400", c == 400 and len(bomba.getvalue()) < 200_000)
c, r, d = rich("POST", f"/api/nevi/{nid}/foto", corpo=b"")
verifica("empty body -> 400", c == 400)
sk = socket.create_connection(("127.0.0.1", PORTA), timeout=10)
sk.sendall((f"POST /api/nevi/{nid}/foto HTTP/1.0\r\nHost: 127.0.0.1:{PORTA}\r\nX-NeoTracker: 1\r\nCookie: {COOKIE}\r\nContent-Length: {nt.MAX_MB_FOTO * 1048576 * 5}\r\n\r\n").encode())
verifica("huge Content-Length -> 413 at once (the body is not read)", sk.recv(100).startswith(b"HTTP/1.0 413"))
sk.close()
c, r, d = rich("POST", "/api/utenti", corpo=b"{non json", header={"Content-Type": "application/json"})
verifica("broken JSON -> 400", c == 400)
c, r, d = rich("POST", "/api/utenti", corpo=b'["a"]')
verifica("JSON that is not an object -> 400", c == 400)
c, r, d = rich("POST", "/api/utenti", corpo=b'{"nome": "' + b"A" * 5000 + b'"}')
verifica("very long name -> 400", c == 400)

print("== paths, SQL and strange texts")
for perc in ["/foto/../../etc/passwd", "/foto/%2e%2e/%2e%2e/etc/passwd", "/../neotracker.db", "/neotracker.db", "/impostazioni.json",
             "/..%2fneotracker.db", "/%2e%2e/%2e%2e/etc/passwd", "/sessione.token", "//etc/passwd", "/app.js/../../neotracker.db"]:
    c, r, d = rich("GET", perc)
    verifica(f"GET {perc} -> no reserved file", c in (400, 404) and b"SQLite" not in d and b"root:" not in d and nt.TOKEN_SESSIONE.encode() not in d, str(c))
with nt.connetti() as con:                                  # a 'poisoned' row: the file name goes out of the photo folder
    cur = con.execute("INSERT INTO foto (nevo_id, file, scattata_il, creato) VALUES (?,?,?,?)", (nid, "../../neotracker.db", "2026-01-01", "x"))
    fid_x = cur.lastrowid
    cur = con.execute("INSERT INTO foto (nevo_id, file, scattata_il, creato) VALUES (?,?,?,?)", (nid, str(tmp / "neotracker.db"), "2026-01-01", "x"))
    fid_y = cur.lastrowid
for f in (fid_x, fid_y):
    for tipo in ("originale", "mini"):
        c, r, d = rich("GET", f"/foto/{f}/{tipo}")
        verifica(f"photo with a path outside the folder ({f}/{tipo}) is not served", c == 404 and b"SQLite format" not in d, str(c))
for nome in ["'; DROP TABLE utenti;--", "Robert'); DELETE FROM nevi;--", "<img src=x onerror=alert(1)>", "<script>alert(1)</script>", "\" onmouseover=\"alert(1)", "../../x", "x" * 60]:
    c, r, d = rich("POST", "/api/utenti", corpo=json.dumps({"nome": nome}).encode())
    verifica(f"strange name accepted as plain text: {nome[:24]!r}", c == 200)
c, r, d = rich("GET", "/api/utenti")
nomi = [u["nome"] for u in json.loads(d)]
verifica("the tables are still there and the names come back identical", "<script>alert(1)</script>" in nomi and "'; DROP TABLE utenti;--" in nomi and "application/json" in r.getheader("Content-Type"))
with nt.connetti() as con:
    verifica("no table lost", con.execute("SELECT COUNT(*) FROM nevi").fetchone()[0] >= 1)
c, r, d = rich("GET", "/api/utenti/1%20OR%201=1")
verifica("non-numeric id in the address -> 404", c == 404)
c, r, d = rich("GET", "/api/letteratura/cerca?q=" + urllib.parse.quote("melanoma\" OR 1=1 --"))
verifica("free search with strange characters breaks nothing", c in (200, 502), str(c))
c, r, d = rich("GET", "/api/presenza?id=" + "a" * 200)
verifica("page identifier too long -> 400", c == 400)
c, r, d = rich("GET", "/api/presenza?id=a%0d%0aSet-Cookie:x=1")
verifica("identifier with a line break -> 400 (no header injection)", c == 400)
c, r, d = rich("GET", "/a" * 1500)
verifica("very long address -> 414", c == 414)

print("== settings and secrets")
c, r, d = rich("PUT", "/api/impostazioni", corpo=json.dumps({"openweather_key": "ABCD1234efgh5678"}).encode())
j = json.loads(d)
verifica("the API key is never returned", "openweather_key" not in j and j["ha_chiave_owm"] and "ABCD1234" not in d.decode())
c, r, d = rich("GET", "/api/stato")
verifica("/api/stato contains no keys", b"ABCD1234" not in d and nt.TOKEN_SESSIONE.encode() not in d)
if os.name != "nt":
    modo = stat.S_IMODE((tmp / "impostazioni.json").stat().st_mode)
    verifica("impostazioni.json readable only by the owner (0600)", modo == 0o600, oct(modo))
verifica("no .tmp file left behind", not list(tmp.glob("*.tmp")))
c, r, d = rich("PUT", "/api/impostazioni", corpo=json.dumps({"fonte_uv": "evil", "avvertenze_accettate": "99", "ncbi_email": "non-una-email"}).encode())
verifica("values not allowed in the settings -> 400", c == 400)
c, r, d = rich("PUT", "/api/impostazioni", corpo=json.dumps({"CARTELLA_DATI": "/etc", "porta": 1, "openweather_key": ""}).encode())
verifica("unknown fields ignored (the data folder cannot be changed)", c == 200 and "CARTELLA_DATI" not in json.loads((tmp / "impostazioni.json").read_text()))

print("== session key file")
nt.scrivi_token_su_file()
f = nt.percorso_token()
verifica("the key file exists and contains the key", f.exists() and f.read_text() == nt.TOKEN_SESSIONE and nt.leggi_token_da_file() == nt.TOKEN_SESSIONE)
if os.name != "nt":
    verifica("key file 0600", stat.S_IMODE(f.stat().st_mode) == 0o600, oct(stat.S_IMODE(f.stat().st_mode)))
f.write_text("<script>alert(1)</script>")
verifica("strange content in the file -> ignored", nt.leggi_token_da_file() == "")
f.write_text("corta")
verifica("key too short -> ignored", nt.leggi_token_da_file() == "")
nt.cancella_token_file()
verifica("deletion of the key file", not f.exists() and nt.leggi_token_da_file() == "")
nt.cancella_token_file()
verifica("deleting twice gives no error", True)

print("== connection limits")
vecchio_timeout = nt.Gestore.timeout
nt.Gestore.timeout = 2
sk = socket.create_connection(("127.0.0.1", PORTA), timeout=10)
t0 = time.time()
sk.settimeout(8)
try:
    muto = sk.recv(10)
except socket.timeout:
    muto = None
verifica("silent connection closed by the server within a few seconds", muto == b"" and time.time() - t0 < 6, f"{muto} {time.time() - t0:.1f}s")
sk.close()
nt.Gestore.timeout = vecchio_timeout
socks = []
for n in range(nt.MAX_PRESENZE):
    s = socket.create_connection(("127.0.0.1", PORTA), timeout=10)
    s.sendall(f"GET /api/presenza?id=pag{n} HTTP/1.1\r\nHost: 127.0.0.1:{PORTA}\r\nCookie: {COOKIE}\r\n\r\n".encode())
    socks.append(s)
time.sleep(1.0)
primo = socks[0].recv(200)
verifica("'window open' connections within the limit work", primo.startswith(b"HTTP/1.0 200") or primo.startswith(b"HTTP/1.1 200"), str(primo[:30]))
c, r, d = rich("GET", "/api/presenza?id=troppi")
verifica(f"connection number {nt.MAX_PRESENZE + 1} -> 429", c == 429, str(c))
for s in socks:
    s.close()
for _ in range(60):
    if nt._presenze_aperte[0] == 0:
        break
    time.sleep(0.1)
verifica("once the connections are closed, the counter goes back to zero", nt._presenze_aperte[0] == 0, str(nt._presenze_aperte[0]))

print("== requests to the internet")
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
                pass                                    # the client has already stopped reading: this is exactly the case tested
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
        return "Error: " + type(e).__name__
verifica("file:// address rejected", str(prova("file:///etc/passwd")).startswith("ErroreServizio"))
verifica("ftp:// address rejected", str(prova("ftp://example.com/x")).startswith("ErroreServizio"))
verifica("http to an external site rejected (https only)", str(prova("http://example.com/")).startswith("ErroreServizio"))
verifica("http to this computer allowed (tests)", prova("http://127.0.0.1:8797/ok") == b"{}")
verifica("response too large interrupted", prova("http://127.0.0.1:8797/grande", 100_000) == "ErroreServizio: response too large")
verifica("redirect to file:// not followed", str(prova("http://127.0.0.1:8797/verso-file")).startswith("Error"))
verifica("redirect to ftp:// not followed", str(prova("http://127.0.0.1:8797/verso-ftp")).startswith("Error"))
fs.shutdown()
bomba_xml = b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><PubmedArticleSet><PubmedArticle>&b;</PubmedArticle></PubmedArticleSet>'
verifica("XML with ENTITY declarations (bomb) ignored", nt.interpreta_xml_pubmed(bomba_xml) == [])
verifica("normal PubMed XML with an external DOCTYPE still read", nt.interpreta_xml_pubmed(
    b'<?xml version="1.0"?><!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2024//EN" "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_240101.dtd">'
    b'<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID><Article><ArticleTitle>Title</ArticleTitle></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>') != [])

shutil.rmtree(tmp, ignore_errors=True)
print(f"\nRESULT: {ok_n} ok, {fail_n} failed")
sys.exit(1 if fail_n else 0)
