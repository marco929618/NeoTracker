# Servizi finti (OpenWeather, Open-Meteo, PubMed, ipwho.is) per provare NeoTracker senza internet.
import json
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CHIAVE_BUONA = "abcdef0123456789abcdef0123456789"      # abilitata solo per One Call 3.0
CHIAVE_V4 = "44444444444444444444444444444444"          # abilitata solo per One Call 4.0
CHIAMATE = []

XML_PUBMED = """<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
<PubmedArticle><MedlineCitation Status="MEDLINE"><PMID Version="1">19751883</PMID>
<Article PubModel="Print"><Journal><JournalIssue CitedMedium="Print"><PubDate><Year>2009</Year><Month>Nov</Month></PubDate></JournalIssue>
<Title>Journal of the American Academy of Dermatology</Title><ISOAbbreviation>J Am Acad Dermatol</ISOAbbreviation></Journal>
<ArticleTitle>Selection criteria for genetic assessment of patients with <i>familial</i> melanoma.</ArticleTitle>
<Abstract><AbstractText Label="BACKGROUND" NlmCategory="BACKGROUND">Melanoma is a common cancer.</AbstractText>
<AbstractText Label="RESULTS" NlmCategory="RESULTS">We propose rule of three &amp; more.</AbstractText></Abstract>
<AuthorList><Author><LastName>Leachman</LastName><Initials>SA</Initials></Author><Author><LastName>Carucci</LastName><Initials>J</Initials></Author>
<Author><LastName>Kohlmann</LastName><Initials>W</Initials></Author><Author><LastName>Banks</LastName><Initials>KC</Initials></Author><Author><LastName>Asgari</LastName><Initials>MM</Initials></Author></AuthorList>
<PublicationTypeList><PublicationType UI="D016428">Journal Article</PublicationType><PublicationType UI="D016454">Review</PublicationType></PublicationTypeList>
</Article></MedlineCitation>
<PubmedData><ArticleIdList><ArticleId IdType="pubmed">19751883</ArticleId><ArticleId IdType="doi">10.1016/j.jaad.2009.03.016</ArticleId></ArticleIdList></PubmedData></PubmedArticle>
<PubmedArticle><MedlineCitation><PMID>30775140</PMID><Article><Journal><JournalIssue><PubDate><MedlineDate>2019 Jan-Feb</MedlineDate></PubDate></JournalIssue><Title>Some Journal</Title></Journal>
<ArticleTitle>Familial melanoma</ArticleTitle></Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="pubmed">30775140</ArticleId></ArticleIdList></PubmedData></PubmedArticle>
</PubmedArticleSet>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _j(self, obj, codice=200):
        d = json.dumps(obj).encode()
        self.send_response(codice)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(d)))
        self.end_headers()
        self.wfile.write(d)

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(u.query)
        CHIAMATE.append(u.path)
        if u.path == "/data/3.0/onecall":
            if q.get("appid", [""])[0] != CHIAVE_BUONA:
                return self._j({"cod": 401, "message": "Invalid API key"}, 401)
            t0 = 1762560000   # 2025-11-08 00:00 UTC (valore arbitrario)
            return self._j({"lat": 45.07, "lon": 7.69, "timezone": "Europe/Rome", "timezone_offset": 3600,
                            "current": {"dt": t0 + 12 * 3600, "uvi": 2.3},
                            "hourly": [{"dt": t0 + 12 * 3600 + 3600 * i, "uvi": max(0, 6 - abs(i - 2) * 1.5)} for i in range(48)],
                            "daily": [{"dt": t0, "uvi": 6.4}]})
        if u.path.startswith("/data/4.0/onecall/"):
            if q.get("appid", [""])[0] != CHIAVE_V4:
                return self._j({"cod": 401, "message": "Invalid API key"}, 401)
            t0 = 1762560000
            base = {"lat": 45.07, "lon": 7.69, "timezone": "Europe/Rome", "timezone_offset": 3600}
            if u.path.endswith("/current"):
                return self._j(dict(base, data=[{"dt": t0 + 12 * 3600, "uvi": 3.1}]))
            if u.path.endswith("/timeline/1h"):
                inizio = int(q.get("start", [str(t0 + 12 * 3600)])[0])
                return self._j(dict(base, data=[{"dt": inizio + 3600 * i, "uvi": 4.0} for i in range(20)]))
            if u.path.endswith("/timeline/1day"):
                return self._j(dict(base, data=[{"dt": t0 + 11 * 3600, "uvi": 7.1}, {"dt": t0 + 35 * 3600, "uvi": 2.0}]))
            return self._j({"cod": 404}, 404)
        if u.path == "/geo/1.0/direct":
            if q.get("appid", [""])[0] != CHIAVE_BUONA:
                return self._j({"cod": 401}, 401)
            return self._j([{"name": "Torino", "lat": 45.0703, "lon": 7.6869, "country": "IT", "state": "Piedmont"}])
        if u.path == "/v1/forecast":
            ore = [f"2026-11-08T{h:02d}:00" for h in range(24)] + [f"2026-11-09T{h:02d}:00" for h in range(24)]
            return self._j({"timezone": "Europe/Rome", "current": {"time": "2026-11-08T10:15", "uv_index": 1.9},
                            "hourly": {"time": ore, "uv_index": [max(0, 5 - abs(i - 13) * 0.6) for i in range(48)]},
                            "daily": {"uv_index_max": [4.8, 4.6]}})
        if u.path == "/v1/search":
            return self._j({"results": [{"name": "Milano", "admin1": "Lombardia", "country_code": "IT", "latitude": 45.46, "longitude": 9.19}]})
        if u.path == "/":
            return self._j({"success": True, "latitude": 45.07, "longitude": 7.69, "city": "Torino", "country_code": "IT"})
        if u.path.endswith("esearch.fcgi"):
            if "nessunrisultato" in q.get("term", [""])[0]:
                return self._j({"esearchresult": {"count": "0", "idlist": []}})
            return self._j({"esearchresult": {"count": "1234", "idlist": ["19751883", "30775140"]}})
        if u.path.endswith("efetch.fcgi"):
            d = XML_PUBMED.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/xml")
            self.send_header("Content-Length", str(len(d)))
            self.end_headers()
            self.wfile.write(d)
            return
        self._j({"errore": "?"}, 404)


def avvia(porta):
    s = ThreadingHTTPServer(("127.0.0.1", porta), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


if __name__ == "__main__":
    avvia(int(sys.argv[1]) if len(sys.argv) > 1 else 8799)
    time.sleep(10 ** 6)
