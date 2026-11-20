
# ==========================================================================================
# 4. LOGIC: risk factors, genetic criteria, UV index, PubMed literature
# ==========================================================================================

class ErroreServizio(Exception):
    """'Expected' error (no network, wrong key...): the message is for the user."""


def a_intero(valore, predefinito=0):
    """Converts to an integer without ever raising an error ('' or None become the default value)."""
    try:
        return int(float(valore))
    except (TypeError, ValueError):
        return predefinito


def eta_da_nascita(data_nascita):
    """Age in years from a YYYY-MM-DD date (None if the date is missing or invalid)."""
    try:
        n = datetime.strptime(data_nascita, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    oggi = date.today()
    return oggi.year - n.year - ((oggi.month, oggi.day) < (n.month, n.day))


# ------------------------------------------------------------------------------------------
# 4a. Known risk factors (a transparent list, NOT a validated score)
# ------------------------------------------------------------------------------------------
def fattori_rischio(p):
    """
    Compares the profile with the melanoma risk factors best recognised in the literature.
    Returns the list of those that are present. It does NOT compute a probability: it is only an ordered
    reminder, useful to decide how often to be checked by the dermatologist.
    """
    fam1 = a_intero(p.get("fam_melanoma_1grado"))
    voci = [
        # (id, description, present?, 'major'?, explanation)
        ("fototipo", T("Fair phototype (I–II)"), a_intero(p.get("fototipo")) in (1, 2), False,
         T("Skin that burns easily and tans little.")),
        ("capelli", T("Red or blond hair"), p.get("capelli") in ("rossi", "biondi"), False,
         T("Associated with variants of the MC1R gene.")),
        ("occhi", T("Light-coloured eyes"), p.get("occhi") in ("azzurri", "verdi"), False, ""),
        ("efelidi", T("Many freckles (ephelides)"), p.get("efelidi") == "molte", False, ""),
        ("nevi_100", T("100 or more moles on the body"), p.get("n_nevi") == "100+", True,
         T("The number of moles is one of the strongest risk factors.")),
        ("nevi_50", T("50 to 99 moles on the body"), p.get("n_nevi") == "50-99", False, ""),
        ("atipici", T("Atypical (dysplastic) moles"), p.get("nevi_atipici") == "si", True,
         T("Large, irregular, multicoloured moles: they should be followed over time.")),
        ("scottature", T("Many sunburns with blisters"), p.get("scottature") == "molte", False,
         T("Especially in childhood and adolescence.")),
        ("lampade", T("Use of tanning lamps or sunbeds"), p.get("lampade") in ("alcune", "spesso"), False,
         T("Classified as definite human carcinogens (IARC).")),
        ("lavoro", T("Work or prolonged activity outdoors"), bool(p.get("lavoro_aperto")), False, ""),
        ("immuno", T("Immunosuppression (therapies, transplant)"), bool(p.get("immunosoppressione")), True, ""),
        ("mel_pers", T("Melanoma already diagnosed"), a_intero(p.get("melanomi_personali")) >= 1, True,
         T("Having had a melanoma raises the risk of a second one.")),
        ("altri_tum", T("Other skin cancers (basal cell and squamous cell carcinoma)"), bool(p.get("altri_tumori_cutanei")), False, ""),
        ("fam_1", T("First-degree relative with melanoma"), fam1 >= 1, True,
         T("Parents, siblings or children.")),
    ]
    presenti = [{"id": i, "etichetta": e, "maggiore": m, "nota": n} for i, e, pr, m, n in voci if pr]
    maggiori = [f for f in presenti if f["maggiore"]]
    if not presenti:
        livello, testo = "nessuno", T("With the data entered, no known risk factors appear. Complete your "
                                      "profile if information is missing.")
    elif maggiori or len(presenti) >= 5:
        livello = "attenzione"
        testo = T("Significant risk factors are present: periodic dermatological check-ups (the dermatologist "
                  "decides how often) and regular skin self-examination are recommended.")
    else:
        livello = "alcuni"
        testo = T("Some risk factors are present: careful sun protection and regular self-examination; a basic "
                  "dermatological check-up is a good habit.")
    return {"livello": livello, "testo": testo, "presenti": presenti,
            "nota": T("List of factors known from the literature, not a validated score: it does not estimate "
                      "the probability of falling ill.")}


# ------------------------------------------------------------------------------------------
# 4b. Hereditary melanoma: genes and criteria for assessing genetic counselling
# ------------------------------------------------------------------------------------------
# Curated list of the most cited genes. 'termine' is the PubMed search used to count and
# show the studies (the literature scan is redone every time you request it).
GENI_MELANOMA = [
    {"gene": "CDKN2A", "rischio": T("High"),
     "ruolo": T("Main high-penetrance predisposition gene. Germline variants in 20–40% of families with "
                "melanoma; also associated with pancreatic cancer, multiple melanomas and early onset."),
     "termine": 'CDKN2A[tiab] AND melanoma[tiab] AND (germline[tiab] OR hereditary[tiab] OR familial[tiab] OR predisposition[tiab])'},
    {"gene": "CDK4", "rischio": T("High (rare)"),
     "ruolo": T("Rare variants concentrated in codon 24: the family picture is indistinguishable from that of "
                "CDKN2A."),
     "termine": 'CDK4[tiab] AND melanoma[tiab] AND (germline[tiab] OR hereditary[tiab] OR familial[tiab] OR predisposition[tiab])'},
    {"gene": "BAP1", "rischio": T("High (BAP1 syndrome)"),
     "ruolo": T("BAP1 tumour predisposition syndrome: uveal melanoma, mesothelioma, renal carcinoma, cutaneous "
                "melanoma and atypical melanocytic naevi."),
     "termine": 'BAP1[tiab] AND melanoma[tiab] AND (germline[tiab] OR hereditary[tiab] OR predisposition[tiab] OR syndrome[tiab])'},
    {"gene": "MITF", "rischio": T("Moderate"),
     "ruolo": T("The p.E318K variant increases the risk of melanoma and renal carcinoma and is associated with "
                "many moles."),
     "termine": 'MITF[tiab] AND melanoma[tiab] AND (E318K[tiab] OR germline[tiab] OR predisposition[tiab])'},
    {"gene": "POT1", "rischio": T("Rare"),
     "ruolo": T("Telomere gene: rare variants in some families with melanoma."),
     "termine": 'POT1[tiab] AND melanoma[tiab] AND (germline[tiab] OR familial[tiab] OR predisposition[tiab])'},
    {"gene": "ACD", "rischio": T("Rare"),
     "ruolo": T("Telomere gene (shelterin complex): rare variants in families with melanoma."),
     "termine": 'ACD[tiab] AND melanoma[tiab] AND (germline[tiab] OR familial[tiab] OR telomere[tiab])'},
    {"gene": "TERF2IP", "rischio": T("Rare"),
     "ruolo": T("Telomere gene (shelterin complex): rare variants in families with melanoma."),
     "termine": 'TERF2IP[tiab] AND melanoma[tiab] AND (germline[tiab] OR familial[tiab] OR telomere[tiab])'},
    {"gene": "TERT", "rischio": T("Rare"),
     "ruolo": T("Telomerase: promoter variants described in families with melanoma."),
     "termine": 'TERT[tiab] AND melanoma[tiab] AND (germline[tiab] OR familial[tiab] OR predisposition[tiab])'},
    {"gene": "MC1R", "rischio": T("Low to moderate (common)"),
     "ruolo": T("Common variants linked to red hair and fair skin: they raise the melanoma risk moderately. Not "
                "a routine test: interpretation is specialist."),
     "termine": 'MC1R[tiab] AND melanoma[tiab] AND (variant[tiab] OR polymorphism[tiab] OR risk[tiab])'},
    {"gene": "PTEN", "rischio": T("Syndromic"),
     "ruolo": T("Cited by the NCCN guidelines among the genes to consider in melanoma panels (Cowden syndrome)."),
     "termine": 'PTEN[tiab] AND melanoma[tiab] AND (germline[tiab] OR hereditary[tiab] OR Cowden[tiab])'},
]

FONTI_GENETICA = [
    {"titolo": "Leachman SA et al. Selection criteria for genetic assessment of patients with familial melanoma. "
               "J Am Acad Dermatol 2009;61(4):677.e1-14",
     "url": "https://pubmed.ncbi.nlm.nih.gov/19751883/"},
    {"titolo": "Leachman SA et al. Identification, genetic testing, and management of hereditary melanoma. "
               "Cancer Metastasis Rev 2017;36(1):77-90",
     "url": "https://doi.org/10.1007/s10555-017-9661-5"},
    {"titolo": "Rossi M et al. Familial melanoma: diagnostic and management implications. "
               "Dermatol Pract Concept 2019;9(1):10-16",
     "url": "https://pubmed.ncbi.nlm.nih.gov/30775140/"},
    {"titolo": T("NCCN Clinical Practice Guidelines in Oncology: Melanoma: Cutaneous (current version; the full "
                 "text requires free registration)"),
     "url": "https://www.nccn.org/guidelines/category_1"},
]


def valuta_genetica(p):
    """
    Applies the criteria described in the literature to decide whether it is worth talking to a
    geneticist. Important: it does NOT say "you must take the test" nor "you do not need it": it only reports whether
    the data entered meets the criteria and asks you to discuss it with a specialist.
    """
    mel_pers = a_intero(p.get("melanomi_personali"))
    mel_fam = a_intero(p.get("fam_melanoma_1grado")) + a_intero(p.get("fam_melanoma_altri"))
    pancreas_fam = a_intero(p.get("fam_pancreas"))
    pancreas_1 = a_intero(p.get("fam_pancreas_1grado"))
    astro_fam = a_intero(p.get("fam_astrocitoma"))
    pers_panc = 1 if p.get("pers_pancreas") else 0
    pers_astro = 1 if p.get("pers_astrocitoma") else 0

    # Rule of 3: total diagnoses of melanoma, pancreatic cancer, astrocytoma in the same family line
    diagnosi = mel_pers + mel_fam + pancreas_fam + pers_panc + astro_fam + pers_astro

    # BAP1 tumour spectrum (uveal, mesothelioma, kidney) + cutaneous melanoma
    bap1_tipici = (a_intero(p.get("fam_uveale")) + a_intero(p.get("fam_mesotelioma")) + a_intero(p.get("fam_rene"))
                   + sum(1 for k in ("pers_uveale", "pers_mesotelioma", "pers_rene") if p.get(k)))
    bap1_spettro = bap1_tipici + (1 if (mel_pers + mel_fam) >= 1 else 0)

    criteri = [
        {"id": "tre_melanomi", "soddisfatto": mel_pers >= 3,
         "titolo": T("3 or more primary melanomas in the same person"),
         "spiegazione": T(f"Primary melanomas indicated: {mel_pers}."),
         "fonte": T("Leachman 2009 and 2017; NCCN")},
        {"id": "regola_tre", "soddisfatto": diagnosi >= 3,
         "titolo": T("At least 3 diagnoses among melanoma, pancreatic cancer and astrocytoma in the same family "
                     "line (yours included)"),
         "spiegazione": T(f"Total diagnoses entered: {diagnosi}. Leachman 2009 counts melanoma and pancreatic "
                          "cancer in 1st- and 2nd-degree relatives on the same side of the family; astrocytoma "
                          "is included by the NCCN guidelines."),
         "fonte": T("Leachman 2009 and 2017; NCCN")},
        {"id": "mel_pancreas", "soddisfatto": mel_pers >= 1 and pancreas_1 >= 1,
         "titolo": T("Personal melanoma and a first-degree relative with pancreatic cancer"),
         "spiegazione": T("According to the NCCN guidelines, in an invasive melanoma with a first-degree "
                          "relative with pancreatic cancer, a multigene panel that includes CDKN2A is "
                          "recommended."),
         "fonte": T("NCCN")},
        {"id": "bap1", "soddisfatto": bap1_tipici >= 1 and bap1_spettro >= 2,
         "titolo": T("Multiple BAP1-spectrum tumours (uveal melanoma, mesothelioma, renal carcinoma, cutaneous "
                     "melanoma)"),
         "spiegazione": T(f"BAP1-spectrum tumours indicated: {bap1_spettro}. Simplified criterion: the geneticist "
                          "uses more complete criteria."),
         "fonte": T("Leachman 2017; NCCN")},
    ]
    soddisfatti = [c for c in criteri if c["soddisfatto"]]
    compilata = bool(p.get("fam_compilata"))

    geni = []
    if any(c["id"] in ("tre_melanomi", "regola_tre", "mel_pancreas") for c in soddisfatti):
        geni = ["CDKN2A", "CDK4", "BAP1", "MITF", "POT1"]
    if any(c["id"] == "bap1" for c in soddisfatti) and "BAP1" not in geni:
        geni = ["BAP1"] + geni

    esito_gen = p.get("test_genetico", "no")
    if not compilata:
        esito, msg = "dati_insufficienti", T("Fill in the 'Family history' section of your Profile: without that "
                                             "data I cannot check the criteria.")
    elif soddisfatti:
        esito = "criteri_soddisfatti"
        msg = T("The data entered meet at least one criterion described in the literature. We advise you to talk "
                "about it with your dermatologist or a medical geneticist (oncological genetic counselling): the "
                "specialist will decide whether and which test to offer, usually after counselling and, when "
                "possible, starting from an affected relative. Genes most cited by the guidelines: {geni}. The "
                "use of multigene panels is still under discussion among specialists: that is why counselling "
                "before the test matters.").format(geni=", ".join(geni))
    else:
        esito = "nessun_criterio"
        msg = T("With the data entered you do not meet the most commonly used criteria. Genetic testing for "
                "melanoma is indicated only in a small minority of people and is not offered routinely. If your "
                "family history changes or you have doubts, update your profile and talk to your dermatologist.")
    # sentence added separately (not glued to the message): so each one is translated in full
    aggiunta = ""
    if esito_gen in ("si_positivo", "si_negativo", "si_non_informativo"):
        aggiunta = T("You said you have already had a genetic test: take the report to your dermatologist.")
    return {"esito": esito, "messaggio": msg, "messaggio_aggiunta": aggiunta, "criteri": criteri, "geni_suggeriti": geni, "fonti": FONTI_GENETICA}


# ------------------------------------------------------------------------------------------
# 4c. UV index (Open-Meteo by default; OpenWeather One Call 4.0/3.0 if you choose it and have the key)
# ------------------------------------------------------------------------------------------
CATEGORIE_UV = [
    # (from, to, name, WHO colour, advice)
    (0, 2.99, T("Low"), "#3f9c35", T("No special protection needed for normal activities; sunglasses on bright "
                                       "days.")),
    (3, 5.99, T("Moderate"), "#e8c400", T("Protection recommended: shade in the middle of the day, hat, "
                                          "sunglasses and sunscreen.")),
    (6, 7.99, T("High"), "#f28c00", T("Protection necessary: reduce exposure between 10 and 16, SPF 30+ "
                                      "sunscreen, hat and sunglasses.")),
    (8, 10.99, T("Very high"), "#d9261c", T("Extra precautions: avoid the sun in the middle of the day, seek "
                                             "shade, cover your skin, SPF 30+. Unprotected skin burns quickly.")),
    (11, 999, T("Extreme"), "#8e44ad", T("Avoid direct exposure: unprotected skin can burn within a few minutes.")),
]

# Minimum dose that causes reddening (MED) in "standard erythema doses" (1 SED = 100 J/m2). Ranges reported by
# Fajuyigbe & Young 2016 (Table 1): I 2-3, II 2.5-3, III 3-5, IV 4-7, V 6-20, VI 6-20. Here the LOWEST value
# of each range is used, i.e. the most cautious estimate.
MED_SED_PRUDENTE = {1: 2.0, 2: 2.5, 3: 3.0, 4: 4.0, 5: 6.0, 6: 6.0}

_cache_uv = {}


def categoria_uv(uvi):
    for da, a, nome, colore, consiglio in CATEGORIE_UV:
        if da <= uvi <= a or (uvi > a and a == 999):
            return {"nome": nome, "colore": colore, "consiglio": consiglio, "da": da}
    return {"nome": T("Low"), "colore": CATEGORIE_UV[0][3], "consiglio": CATEGORIE_UV[0][4], "da": 0}


def minuti_scottatura(uvi, fototipo):
    """
    CAUTIOUS estimate of the minutes of sun, with a clear sky and unprotected skin, before
    reddening. Formula: minutes = MED(in SED) x 60 / UVI, because in one hour you receive about
    as many SED as there are UVI points (Lucas et al. 2018, on an unshaded horizontal surface).
    It only gives an order of magnitude: clouds, reflections (snow, water), altitude and creams change it a lot.
    """
    ft = a_intero(fototipo)
    if ft not in MED_SED_PRUDENTE or uvi is None:
        return None
    if uvi < 0.5:
        return {"minuti": None, "testo": T("over 2 hours (very low UV)")}
    m = MED_SED_PRUDENTE[ft] * 60.0 / uvi
    return {"minuti": int(round(m)), "testo": T("about {minuti} minutes").format(minuti=int(round(m)))}


# All requests to the internet go through here. Rules: https only (http only towards this same computer, for
# tests), no "file:" or "ftp:" addresses (not even if a service redirects us there), and a response cannot
# exceed a maximum size (a huge response must not fill the memory).
_APRITORE_WEB = urllib.request.OpenerDirector()
for _gestore in (urllib.request.ProxyHandler(), urllib.request.HTTPHandler(), urllib.request.HTTPSHandler(),
                 urllib.request.HTTPRedirectHandler(), urllib.request.HTTPDefaultErrorHandler(), urllib.request.HTTPErrorProcessor()):
    _APRITORE_WEB.add_handler(_gestore)
MAX_BYTE_RISPOSTA_WEB = 8 * 1024 * 1024


def _leggi_web(req, timeout, massimo=MAX_BYTE_RISPOSTA_WEB):
    """Performs the request and returns the bytes of the response (with the checks described above)."""
    u = urllib.parse.urlsplit(req.full_url)
    if not (u.scheme == "https" or (u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost"))):
        raise ErroreServizio(T("address not allowed (https only)"))
    with _APRITORE_WEB.open(req, timeout=timeout) as r:
        dati = r.read(massimo + 1)
    if len(dati) > massimo:
        raise ErroreServizio(T("response too large"))
    return dati


def _http_json(url, timeout=20, headers=None):
    """Downloads a web address and reads it as JSON. Turns network errors into clear messages."""
    req = urllib.request.Request(url, headers=dict({"User-Agent": "NeoTracker/" + VERSIONE}, **(headers or {})))
    try:
        return json.loads(_leggi_web(req, timeout).decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        raise ErroreServizio(f"HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise ErroreServizio(T("connection failed: {motivo}").format(motivo=e.reason)) from e
    except (TimeoutError, OSError) as e:
        raise ErroreServizio(T("timed out or network unavailable")) from e
    except ValueError as e:
        raise ErroreServizio(T("invalid response from the service")) from e


def _owm_ora_locale(ts, off):
    return datetime.fromtimestamp(int(ts) + int(off), timezone.utc)


def _owm_chiamata(base, percorso, lat, lon, chiave, extra=""):
    return _http_json(f"{base}{percorso}?lat={lat:.2f}&lon={lon:.2f}&units=metric{extra}&appid={urllib.parse.quote(chiave)}")


def _uv_owm_v4(lat, lon, chiave):
    """One Call 4.0 ('One Call pay-per-call' subscription): current + hourly + daily = 3-4 calls."""
    base = os.environ.get("NEOTRACKER_OWM_BASE", "https://api.openweathermap.org")
    cur_r = _owm_chiamata(base, "/data/4.0/onecall/current", lat, lon, chiave)
    cur = (cur_r.get("data") or [{}])[0]
    off = int(cur_r.get("timezone_offset", 0))
    ore_r = _owm_chiamata(base, "/data/4.0/onecall/timeline/1h", lat, lon, chiave)
    voci = list(ore_r.get("data") or [])
    if 0 < len(voci) < 24:                    # a response contains at most 20 hours: I ask for more
        try:
            seguito = _owm_chiamata(base, "/data/4.0/onecall/timeline/1h", lat, lon, chiave, f"&start={int(voci[-1]['dt']) + 3600}")
            voci += list(seguito.get("data") or [])
        except ErroreServizio:
            pass
    ore, visti, date_ore = [], set(), []
    for v in voci:
        if v.get("dt") in visti:
            continue
        visti.add(v.get("dt"))
        t = _owm_ora_locale(v["dt"], off)
        date_ore.append(t.date())
        ore.append({"ora": t.strftime("%H:%M"), "giorno": t.strftime("%d/%m"), "data": t.strftime("%Y-%m-%d"), "uvi": round(float(v.get("uvi") or 0), 1)})
        if len(ore) == 24:
            break
    adesso = _owm_ora_locale(cur.get("dt", time.time()), off)
    uvi_ora = round(float(cur.get("uvi") or 0), 1)
    mx = None
    try:
        giorni = _owm_chiamata(base, "/data/4.0/onecall/timeline/1day", lat, lon, chiave).get("data") or []
        oggi = next((g for g in giorni if _owm_ora_locale(g["dt"], off).date() == adesso.date()), None)
        if oggi is not None and oggi.get("uvi") is not None:
            mx = round(float(oggi["uvi"]), 1)
    except ErroreServizio:
        pass
    if mx is None:                            # fallback: the maximum of today's known hours
        oggi_ore = [o["uvi"] for o, d in zip(ore, date_ore) if d == adesso.date()]
        mx = max(oggi_ore + [uvi_ora])
    return {"fonte": "OpenWeather One Call 4.0", "uvi_ora": uvi_ora, "uvi_max": max(mx, uvi_ora), "ore": ore,
            "aggiornato": adesso.strftime("%d/%m/%Y %H:%M") + " (local time at the location)",
            "aggiornato_iso": adesso.strftime("%Y-%m-%dT%H:%M"), "fuso": cur_r.get("timezone", "")}


def _uv_owm_v3(lat, lon, chiave):
    """One Call 3.0 (old subscription): a single call."""
    base = os.environ.get("NEOTRACKER_OWM_BASE", "https://api.openweathermap.org")
    d = _owm_chiamata(base, "/data/3.0/onecall", lat, lon, chiave, "&exclude=minutely,alerts")
    off = int(d.get("timezone_offset", 0))
    ore = []
    for v in (d.get("hourly") or [])[:24]:
        t = _owm_ora_locale(v["dt"], off)
        ore.append({"ora": t.strftime("%H:%M"), "giorno": t.strftime("%d/%m"), "data": t.strftime("%Y-%m-%d"), "uvi": round(float(v.get("uvi", 0)), 1)})
    cur = d.get("current") or {}
    daily0 = (d.get("daily") or [{}])[0]
    return {"fonte": "OpenWeather One Call 3.0", "uvi_ora": round(float(cur.get("uvi", 0)), 1),
            "uvi_max": round(float(daily0.get("uvi", cur.get("uvi", 0))), 1), "ore": ore,
            "aggiornato": _owm_ora_locale(cur.get("dt", time.time()), off).strftime("%d/%m/%Y %H:%M") + " (local time at the location)",
            "aggiornato_iso": _owm_ora_locale(cur.get("dt", time.time()), off).strftime("%Y-%m-%dT%H:%M"),
            "fuso": d.get("timezone", "")}


def _uv_openweather(lat, lon, chiave):
    """
    First tries One Call 4.0 (the one OpenWeather recommends today); if the key is not enabled
    tries One Call 3.0 (older subscriptions). If neither answers, explains why.
    """
    errori = []
    for nome, funzione in (("4.0", _uv_owm_v4), ("3.0", _uv_owm_v3)):
        try:
            return funzione(lat, lon, chiave)
        except ErroreServizio as e:
            errori.append((nome, str(e)))
            if not any(c in str(e) for c in ("401", "403", "404")):
                break                          # not an enabling problem: no point retrying with the other version
    testo = " ".join(t for _, t in errori)
    if "429" in testo:
        raise ErroreServizio(T("OpenWeather: call limit reached (429)."))
    if "401" in testo or "403" in testo:
        raise ErroreServizio(T("OpenWeather rejected the key (401): check that it is correct and that the 'One "
                               "Call API' plan (pay per call, 1,000 free calls per day) is active on your "
                               "account. After subscribing, the key can take a few minutes to activate."))
    raise ErroreServizio("; ".join(T("One Call {n}: {t}").format(n=n, t=t) for n, t in errori))


def _data_ora_italiana(iso):
    """'2026-11-08T10:15' -> '08/11/2026 10:15' (if the format is different it leaves it as it is)."""
    try:
        return datetime.strptime(iso[:16], "%Y-%m-%dT%H:%M").strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return iso


def _uv_openmeteo(lat, lon):
    base = os.environ.get("NEOTRACKER_OPENMETEO_BASE", "https://api.open-meteo.com")
    d = _http_json(f"{base}/v1/forecast?latitude={lat:.2f}&longitude={lon:.2f}&current=uv_index&hourly=uv_index"
                   f"&daily=uv_index_max&timezone=auto&forecast_days=2")
    cur = d.get("current") or {}
    ora_corrente = (cur.get("time") or "")[:13]
    tempi = (d.get("hourly") or {}).get("time") or []
    valori = (d.get("hourly") or {}).get("uv_index") or []
    ore = []
    inizio = next((i for i, t in enumerate(tempi) if t[:13] >= ora_corrente), 0)
    for t, v in list(zip(tempi, valori))[inizio:inizio + 24]:
        ore.append({"ora": t[11:16], "giorno": t[8:10] + "/" + t[5:7], "data": t[:10], "uvi": round(float(v or 0), 1)})
    mx = ((d.get("daily") or {}).get("uv_index_max") or [cur.get("uv_index", 0)])[0]
    return {"fonte": "Open-Meteo", "uvi_ora": round(float(cur.get("uv_index") or 0), 1),
            "uvi_max": round(float(mx or 0), 1), "ore": ore,
            "aggiornato": _data_ora_italiana(cur.get("time") or "") + " (local time at the location)",
            "aggiornato_iso": (cur.get("time") or "")[:16],
            "fuso": d.get("timezone", "")}


def usa_openweather(imp):
    """True only if you CHOSE OpenWeather in Settings and entered the key."""
    return imp.get("fonte_uv") == "openweather" and bool((imp.get("openweather_key") or "").strip())


def indice_uv(lat, lon, fototipo=None, localita=""):
    """
    Returns the UV index for the given point.
    - Default: Open-Meteo (free, no key).
    - If in Settings you choose OpenWeather and enter your key, it uses OpenWeather;
      if OpenWeather gives an error, it uses Open-Meteo and tells you clearly.
    """
    imp = leggi_impostazioni()
    ow = usa_openweather(imp)
    chiave = (imp.get("openweather_key") or "").strip()
    chiave_cache = (round(lat, 2), round(lon, 2), ow)
    voce = _cache_uv.get(chiave_cache)
    if voce and time.time() - voce[0] < 600:
        dati = dict(voce[1])
    else:
        avviso = ""
        dati = None
        if ow:
            try:
                dati = _uv_openweather(lat, lon, chiave)
            except ErroreServizio as e:
                avviso = T(f"OpenWeather unavailable ({e}). Showing Open-Meteo data.")
        elif imp.get("fonte_uv") == "openweather":
            avviso = T("You chose OpenWeather but the key is missing (Settings): showing Open-Meteo data.")
        if dati is None:
            try:
                dati = _uv_openmeteo(lat, lon)
            except ErroreServizio as e:
                if avviso:
                    raise ErroreServizio(T("{avviso} The Open-Meteo service is not responding ({e}).").format(avviso=avviso, e=e))
                raise ErroreServizio(T("The Open-Meteo service is not responding ({e}).").format(e=e))
        dati["avviso"] = avviso
        _cache_uv[chiave_cache] = (time.time(), dict(dati))
    cat_ora, cat_max = categoria_uv(dati["uvi_ora"]), categoria_uv(dati["uvi_max"])
    dati.update({"lat": lat, "lon": lon, "localita": localita,
                 "categoria_ora": cat_ora, "categoria_max": cat_max,
                 "scottatura_max": minuti_scottatura(dati["uvi_max"], fototipo),
                 "scottatura_ora": minuti_scottatura(dati["uvi_ora"], fototipo)})
    mx = dati["uvi_max"]
    if mx >= 8:
        verdetto = {"livello": "rosso", "titolo": T("UV rays are very harmful today"),
                    "testo": T("Avoid the sun in the middle hours of the day and protect your skin well.")}
    elif mx >= 6:
        verdetto = {"livello": "arancio", "titolo": T("UV rays are harmful to unprotected skin today"),
                    "testo": T("Shade, clothing, a hat and sunscreen are needed in the middle of the day.")}
    elif mx >= 3:
        verdetto = {"livello": "giallo", "titolo": T("Moderate UV: protection needed in the middle of the day"),
                    "testo": T("The WHO recommends protection from a UV index of 3.")}
    else:
        verdetto = {"livello": "verde", "titolo": T("UV rays are low today"),
                    "testo": T("Protection not needed for normal activities (beware of snow, water, altitude).")}
    dati["verdetto"] = verdetto
    dati["fonti"] = [
        {"titolo": T("WHO/WMO/UNEP/ICNIRP - Global Solar UV Index: A Practical Guide (2002)"),
         "url": "https://www.who.int/publications/i/item/9241590076"},
        {"titolo": T("Lucas RM et al. Are current guidelines for sun protection optimal for health? Photochem "
                     "Photobiol Sci 2018;17:1956-63 (UV Index and erythemal dose)"),
         "url": "https://doi.org/10.1039/c7pp00374a"},
        {"titolo": T("Fajuyigbe D, Young AR. The impact of skin colour on human photobiological responses. "
                     "Pigment Cell Melanoma Res 2016;29:607-18 (minimal erythema dose by phototype)"),
         "url": "https://pubmed.ncbi.nlm.nih.gov/27454804/"},
    ]
    return dati


def cerca_localita(testo):
    """Turns a city name into coordinates (Open-Meteo; OpenWeather only if you chose it and have the key)."""
    testo = (testo or "").strip()
    if len(testo) < 2:
        return []
    imp = leggi_impostazioni()
    chiave = (imp.get("openweather_key") or "").strip()
    if usa_openweather(imp):
        try:
            base = os.environ.get("NEOTRACKER_OWM_BASE", "https://api.openweathermap.org")
            r = _http_json(f"{base}/geo/1.0/direct?q={urllib.parse.quote(testo)}&limit=5&appid={urllib.parse.quote(chiave)}")
            return [{"nome": ", ".join(x for x in (c.get("name"), c.get("state"), c.get("country")) if x),
                     "lat": c["lat"], "lon": c["lon"]} for c in r]
        except ErroreServizio:
            pass
    base = os.environ.get("NEOTRACKER_GEOCODE_BASE", "https://geocoding-api.open-meteo.com")
    r = _http_json(f"{base}/v1/search?name={urllib.parse.quote(testo)}&count=5&language={lingua_corrente()}&format=json")
    return [{"nome": ", ".join(x for x in (c.get("name"), c.get("admin1"), c.get("country_code")) if x),
             "lat": c["latitude"], "lon": c["longitude"]} for c in (r.get("results") or [])]


def posizione_da_ip():
    """Approximate position from your internet address (precision: the city)."""
    base = os.environ.get("NEOTRACKER_IP_BASE", "https://ipwho.is")
    r = _http_json(base + "/")
    if r.get("success") is False or "latitude" not in r:
        raise ErroreServizio(T("location from internet address not available"))
    return {"lat": r["latitude"], "lon": r["longitude"],
            "nome": ", ".join(x for x in (r.get("city"), r.get("country_code")) if x)}


# ------------------------------------------------------------------------------------------
# 4d. Scientific literature from PubMed (E-utilities, free and public)
# ------------------------------------------------------------------------------------------
_ultima_chiamata_ncbi = [0.0]
_blocco_ncbi = threading.Lock()


def _ncbi_get(percorso, parametri):
    """A call to PubMed, with at least 0.4 s between one and the next (the limit without a key is 3 per second)."""
    base = os.environ.get("NEOTRACKER_EUTILS_BASE", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/")
    parametri = dict(parametri, tool="NeoTracker")
    mail = (leggi_impostazioni().get("ncbi_email") or "").strip()
    if mail:
        parametri["email"] = mail
    with _blocco_ncbi:
        attesa = 0.4 - (time.time() - _ultima_chiamata_ncbi[0])
        if attesa > 0:
            time.sleep(attesa)
        _ultima_chiamata_ncbi[0] = time.time()
    url = base + percorso + "?" + urllib.parse.urlencode(parametri)
    req = urllib.request.Request(url, headers={"User-Agent": "NeoTracker/" + VERSIONE})
    try:
        return _leggi_web(req, 30, 20 * 1024 * 1024)
    except urllib.error.HTTPError as e:
        raise ErroreServizio(T(f"PubMed responded with error {e.code}")) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErroreServizio(T("PubMed unreachable (check the internet connection)")) from e


def interpreta_xml_pubmed(xml_bytes, max_abstract=1100):
    """Reads the XML response of PubMed and returns a list of simple articles."""
    articoli = []
    if b"<!ENTITY" in xml_bytes:           # real PubMed responses do not declare "entities": that is the trick of XML bombs
        return articoli
    try:
        # Security check (bandit B314): source: PubMed via https, without ENTITY declarations, limited size.
        radice = ET.fromstring(xml_bytes)   # nosec B314
    except ET.ParseError:
        return articoli
    for pa in radice.findall(".//PubmedArticle"):
        pmid = (pa.findtext(".//MedlineCitation/PMID") or "").strip()
        art = pa.find(".//MedlineCitation/Article")
        if art is None:
            continue
        titolo = "".join(art.find("ArticleTitle").itertext()).strip() if art.find("ArticleTitle") is not None else ""
        parti = []
        for at in art.findall("./Abstract/AbstractText"):
            testo = "".join(at.itertext()).strip()
            etichetta = at.get("Label")
            parti.append((etichetta.capitalize() + ": " if etichetta else "") + testo)
        abstract = " ".join(parti)
        if len(abstract) > max_abstract:
            abstract = abstract[:max_abstract].rsplit(" ", 1)[0] + "…"
        autori = []
        for a in art.findall("./AuthorList/Author"):
            cognome, iniz = a.findtext("LastName"), a.findtext("Initials")
            if cognome:
                autori.append(cognome + (" " + iniz if iniz else ""))
        if len(autori) > 4:
            autori = autori[:3] + ["et al."]
        rivista = art.findtext("./Journal/ISOAbbreviation") or art.findtext("./Journal/Title") or ""
        anno = (art.findtext("./Journal/JournalIssue/PubDate/Year")
                or (art.findtext("./Journal/JournalIssue/PubDate/MedlineDate") or "")[:4])
        doi = ""
        for aid in pa.findall(".//PubmedData/ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi":
                doi = (aid.text or "").strip()
        tipi = [t.text for t in art.findall("./PublicationTypeList/PublicationType") if t.text]
        articoli.append({"pmid": pmid, "titolo": titolo, "autori": ", ".join(autori), "rivista": rivista,
                         "anno": anno, "doi": doi, "tipi": tipi, "abstract": abstract,
                         "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"})
    return articoli


def pubmed_cerca(termine, quanti=4, ordina="relevance", forza=False):
    """
    Searches PubMed and returns {conteggio, articoli, da_cache, data}.
    Results are kept in cache for GIORNI_CACHE_LETTERATURA days: if the network is missing
    and there is an old copy, it uses it and says so.
    """
    chiave = hashlib.sha1(f"{termine}|{quanti}|{ordina}".encode("utf-8"), usedforsecurity=False).hexdigest()[:20]
    cartella = Path(CARTELLA_DATI) / "cache_letteratura"
    cartella.mkdir(parents=True, exist_ok=True)
    f = cartella / f"{chiave}.json"
    vecchia = None
    if f.exists():
        try:
            vecchia = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            vecchia = None
        if vecchia and not forza and time.time() - vecchia.get("t", 0) < GIORNI_CACHE_LETTERATURA * 86400:
            vecchia["da_cache"] = True
            vecchia["data_iso"] = date.fromtimestamp(vecchia.get("t", 0)).isoformat()
            return vecchia
    try:
        es = json.loads(_ncbi_get("esearch.fcgi", {"db": "pubmed", "term": termine, "retmax": quanti,
                                                      "sort": ordina, "retmode": "json"}).decode("utf-8"))
        ris = es.get("esearchresult", {})
        ids = ris.get("idlist", [])
        conteggio = a_intero(ris.get("count"))
        articoli = []
        if ids:
            xml = _ncbi_get("efetch.fcgi", {"db": "pubmed", "id": ",".join(ids), "retmode": "xml", "rettype": "abstract"})
            articoli = interpreta_xml_pubmed(xml)
            ordine = {i: n for n, i in enumerate(ids)}
            articoli.sort(key=lambda a: ordine.get(a["pmid"], 99))
        dati = {"t": time.time(), "data": datetime.now().strftime("%d/%m/%Y"), "data_iso": date.today().isoformat(), "conteggio": conteggio,
                "articoli": articoli, "termine": termine, "da_cache": False}
        f.write_text(json.dumps(dati, ensure_ascii=False), encoding="utf-8")
        return dati
    except ErroreServizio:
        if vecchia:
            vecchia["da_cache"] = True
            vecchia["obsoleta"] = True
            vecchia["data_iso"] = date.fromtimestamp(vecchia.get("t", 0)).isoformat()
            return vecchia
        raise


TEMI_LETTERATURA = {
    "riconoscimento": {
        "titolo": T("Recognising a suspicious mole"),
        "sezioni": [
            (T("ABCDE criteria and the 'ugly duckling' sign"),
             '(melanoma[tiab]) AND (ABCDE[tiab] OR "ugly duckling"[tiab]) AND (diagnosis[tiab] OR detection[tiab] OR recognition[tiab])', "relevance"),
            (T("Dermoscopy and early diagnosis (reviews)"),
             'melanoma[tiab] AND dermoscopy[tiab] AND ("early diagnosis"[tiab] OR "early detection"[tiab]) AND review[pt]', "relevance"),
            (T("Skin self-examination"),
             'melanoma[tiab] AND ("skin self-examination"[tiab] OR "skin self examination"[tiab])', "relevance"),
            (T("Sequential photography and monitoring of moles over time"),
             'melanoma[tiab] AND ("total body photography"[tiab] OR "sequential digital dermoscopy"[tiab] OR "digital dermoscopic monitoring"[tiab])', "relevance"),
        ]},
    "strumenti_ai": {
        "titolo": T("How reliable are apps and artificial intelligence"),
        "sezioni": [
            (T("Smartphone apps and skin cancer risk: diagnostic accuracy"),
             'smartphone[tiab] AND (app[tiab] OR application[tiab]) AND melanoma[tiab] AND (accuracy[tiab] OR diagnostic[tiab])', "relevance"),
            (T("Deep learning and melanoma: systematic reviews"),
             '"deep learning"[tiab] AND melanoma[tiab] AND ("systematic review"[pt] OR meta-analysis[pt])', "relevance"),
        ]},
    "genetica": {
        "titolo": T("Hereditary melanoma and genetic testing"),
        "sezioni": [
            (T("Guidelines and criteria for genetic testing"),
             'melanoma[tiab] AND (hereditary[tiab] OR familial[tiab]) AND ("genetic testing"[tiab] OR "genetic counseling"[tiab]) AND (guideline[tiab] OR criteria[tiab] OR recommendations[tiab])', "relevance"),
            (T("Reviews on familial melanoma (CDKN2A, CDK4)"),
             'melanoma[tiab] AND familial[tiab] AND (CDKN2A[tiab] OR CDK4[tiab]) AND review[pt]', "relevance"),
            (T("Most recent studies on predisposition genes"),
             'melanoma[tiab] AND germline[tiab] AND (susceptibility[tiab] OR predisposition[tiab])', "date"),
        ]},
}

# Words that indicate an "acral" site (hands, feet, nails) or of the head. The words of the other interface
# languages are here too, because the site can be written or chosen in any language (stored site names are in
# English).
REGIONI_ACRALI = ("palmo", "mano", "piede", "tallone", "pianta", "dita", "unghi",
                  "palm", "hand", "foot", "feet", "heel", "sole", "toe", "finger", "nail",
                  "paume", "main", "pied", "talon", "plante", "orteil", "doigt", "ongle",
                  "handfl", "hand", "fuß", "fuss", "ferse", "zeh", "finger", "nagel",
                  "palma", "mano", "pie", "talón", "talon", "planta", "dedo", "uña")
REGIONI_TESTA = ("viso", "testa", "cuoio", "collo", "nuca",
                 "face", "head", "scalp", "neck", "forehead",
                 "visage", "tête", "cuir chevelu", "cou", "nuque", "front",
                 "gesicht", "kopf", "kopfhaut", "hals", "nacken", "stirn",
                 "cara", "rostro", "cabeza", "cuero", "cuello", "nuca", "frente")


def temi_personalizzati(profilo, regioni):
    """Literature sections chosen according to the profile and the locations of your moles."""
    sez = []
    if a_intero(profilo.get("fototipo")) >= 5:
        sez.append((T("Melanoma in dark skin (often acral)"),
                    'melanoma[tiab] AND ("skin of color"[tiab] OR "dark skin"[tiab] OR acral[tiab]) AND (diagnosis[tiab] OR detection[tiab])', "relevance"))
    reg = " ".join(regioni).lower()
    if any(k in reg for k in REGIONI_ACRALI):
        sez.append((T("Acral melanoma (hands, feet, nails): dermoscopy"),
                    'acral[tiab] AND melanoma[tiab] AND dermoscop*[tiab]', "relevance"))
    if any(k in reg for k in REGIONI_TESTA):
        sez.append((T("Lentigo maligna and melanoma of the face"),
                    '"lentigo maligna"[tiab] AND (diagnosis[tiab] OR dermoscopy[tiab])', "relevance"))
    if profilo.get("n_nevi") in ("50-99", "100+") or profilo.get("nevi_atipici") == "si":
        sez.append((T("Many moles or atypical moles: surveillance"),
                    '("dysplastic nevus"[tiab] OR "atypical nevi"[tiab] OR "high nevus count"[tiab] OR "many nevi"[tiab]) AND melanoma[tiab] AND (surveillance[tiab] OR monitoring[tiab])', "relevance"))
    if profilo.get("immunosoppressione"):
        sez.append((T("Melanoma and immunosuppression"),
                    'melanoma[tiab] AND (immunosuppress*[tiab] OR "organ transplant"[tiab]) AND (screening[tiab] OR risk[tiab])', "relevance"))
    return sez
