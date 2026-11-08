
# ==========================================================================================
# 4. LOGICA: fattori di rischio, criteri genetici, indice UV, letteratura PubMed
# ==========================================================================================

class ErroreServizio(Exception):
    """Errore 'previsto' (rete assente, chiave sbagliata...): il messaggio è per l'utente."""


def a_intero(valore, predefinito=0):
    """Converte in numero intero senza mai dare errore ('' o None diventano il valore predefinito)."""
    try:
        return int(float(valore))
    except (TypeError, ValueError):
        return predefinito


def eta_da_nascita(data_nascita):
    """Età in anni da una data AAAA-MM-GG (None se la data manca o non è valida)."""
    try:
        n = datetime.strptime(data_nascita, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    oggi = date.today()
    return oggi.year - n.year - ((oggi.month, oggi.day) < (n.month, n.day))


# ------------------------------------------------------------------------------------------
# 4a. Fattori di rischio noti (elenco trasparente, NON un punteggio validato)
# ------------------------------------------------------------------------------------------
def fattori_rischio(p):
    """
    Confronta il profilo con i fattori di rischio per melanoma più riconosciuti in letteratura.
    Restituisce l'elenco di quelli presenti. NON calcola una probabilità: è solo un promemoria
    ordinato, utile per decidere quanto spesso farsi controllare dal dermatologo.
    """
    fam1 = a_intero(p.get("fam_melanoma_1grado"))
    voci = [
        # (id, descrizione, presente?, 'maggiore'? , spiegazione)
        ("fototipo", "Fototipo chiaro (I-II)", a_intero(p.get("fototipo")) in (1, 2), False,
         "Pelle che scotta facilmente e si abbronza poco."),
        ("capelli", "Capelli rossi o biondi", p.get("capelli") in ("rossi", "biondi"), False,
         "Associati a varianti del gene MC1R."),
        ("occhi", "Occhi chiari", p.get("occhi") in ("azzurri", "verdi"), False, ""),
        ("efelidi", "Molte efelidi (lentiggini)", p.get("efelidi") == "molte", False, ""),
        ("nevi_100", "100 o più nei sul corpo", p.get("n_nevi") == "100+", True,
         "Il numero di nei è uno dei fattori di rischio più forti."),
        ("nevi_50", "Da 50 a 99 nei sul corpo", p.get("n_nevi") == "50-99", False, ""),
        ("atipici", "Nei atipici (displastici)", p.get("nevi_atipici") == "si", True,
         "Nei grandi, irregolari, di più colori: vanno seguiti nel tempo."),
        ("scottature", "Molte scottature con vesciche", p.get("scottature") == "molte", False,
         "Soprattutto in infanzia e adolescenza."),
        ("lampade", "Uso di lampade o lettini abbronzanti", p.get("lampade") in ("alcune", "spesso"), False,
         "Classificati come cancerogeni certi per l'uomo (IARC)."),
        ("lavoro", "Lavoro o attività prolungata all'aperto", bool(p.get("lavoro_aperto")), False, ""),
        ("immuno", "Immunosoppressione (terapie, trapianto)", bool(p.get("immunosoppressione")), True, ""),
        ("mel_pers", "Melanoma già diagnosticato", a_intero(p.get("melanomi_personali")) >= 1, True,
         "Chi ha avuto un melanoma ha un rischio maggiore di un secondo."),
        ("altri_tum", "Altri tumori della pelle (basalioma, spinalioma)", bool(p.get("altri_tumori_cutanei")), False, ""),
        ("fam_1", "Parente di primo grado con melanoma", fam1 >= 1, True,
         "Genitori, fratelli o figli."),
    ]
    presenti = [{"id": i, "etichetta": e, "maggiore": m, "nota": n} for i, e, pr, m, n in voci if pr]
    maggiori = [f for f in presenti if f["maggiore"]]
    if not presenti:
        livello, testo = "nessuno", "Con i dati inseriti non risultano fattori di rischio noti. Completa il profilo se mancano informazioni."
    elif maggiori or len(presenti) >= 5:
        livello = "attenzione"
        testo = ("Sono presenti fattori di rischio rilevanti: è consigliato un controllo dermatologico periodico "
                 "(la frequenza la decide il dermatologo) e l'autoesame regolare della pelle.")
    else:
        livello = "alcuni"
        testo = ("Sono presenti alcuni fattori di rischio: protezione solare accurata e autoesame regolare; "
                 "un controllo dermatologico di base è una buona abitudine.")
    return {"livello": livello, "testo": testo, "presenti": presenti,
            "nota": "Elenco di fattori noti dalla letteratura, non un punteggio validato: non stima la probabilità di ammalarsi."}


# ------------------------------------------------------------------------------------------
# 4b. Melanoma ereditario: geni e criteri per valutare una consulenza genetica
# ------------------------------------------------------------------------------------------
# Elenco curato dei geni più citati. 'termine' è la ricerca PubMed usata per contare e
# mostrare gli studi (la scansione della letteratura la rifà ogni volta che la richiedi).
GENI_MELANOMA = [
    {"gene": "CDKN2A", "rischio": "Alto",
     "ruolo": "Principale gene di predisposizione ad alta penetranza. Varianti germinali nel 20-40% delle famiglie con melanoma; associato anche a tumore del pancreas, melanomi multipli ed esordio precoce.",
     "termine": 'CDKN2A[tiab] AND melanoma[tiab] AND (germline[tiab] OR hereditary[tiab] OR familial[tiab] OR predisposition[tiab])'},
    {"gene": "CDK4", "rischio": "Alto (raro)",
     "ruolo": "Varianti rare concentrate nel codone 24: il quadro familiare è indistinguibile da quello di CDKN2A.",
     "termine": 'CDK4[tiab] AND melanoma[tiab] AND (germline[tiab] OR hereditary[tiab] OR familial[tiab] OR predisposition[tiab])'},
    {"gene": "BAP1", "rischio": "Alto (sindrome BAP1)",
     "ruolo": "Sindrome di predisposizione ai tumori BAP1: melanoma uveale, mesotelioma, carcinoma renale, melanoma cutaneo e nevi melanocitari atipici.",
     "termine": 'BAP1[tiab] AND melanoma[tiab] AND (germline[tiab] OR hereditary[tiab] OR predisposition[tiab] OR syndrome[tiab])'},
    {"gene": "MITF", "rischio": "Moderato",
     "ruolo": "La variante p.E318K aumenta il rischio di melanoma e di carcinoma renale e si associa a molti nei.",
     "termine": 'MITF[tiab] AND melanoma[tiab] AND (E318K[tiab] OR germline[tiab] OR predisposition[tiab])'},
    {"gene": "POT1", "rischio": "Raro",
     "ruolo": "Gene dei telomeri: varianti rare in alcune famiglie con melanoma.",
     "termine": 'POT1[tiab] AND melanoma[tiab] AND (germline[tiab] OR familial[tiab] OR predisposition[tiab])'},
    {"gene": "ACD", "rischio": "Raro",
     "ruolo": "Gene dei telomeri (complesso shelterin): varianti rare in famiglie con melanoma.",
     "termine": 'ACD[tiab] AND melanoma[tiab] AND (germline[tiab] OR familial[tiab] OR telomere[tiab])'},
    {"gene": "TERF2IP", "rischio": "Raro",
     "ruolo": "Gene dei telomeri (complesso shelterin): varianti rare in famiglie con melanoma.",
     "termine": 'TERF2IP[tiab] AND melanoma[tiab] AND (germline[tiab] OR familial[tiab] OR telomere[tiab])'},
    {"gene": "TERT", "rischio": "Raro",
     "ruolo": "Telomerasi: varianti del promotore descritte in famiglie con melanoma.",
     "termine": 'TERT[tiab] AND melanoma[tiab] AND (germline[tiab] OR familial[tiab] OR predisposition[tiab])'},
    {"gene": "MC1R", "rischio": "Basso-moderato (comune)",
     "ruolo": "Varianti comuni legate a capelli rossi e pelle chiara: aumentano il rischio di melanoma in modo moderato. Non è un test di routine: l'interpretazione è specialistica.",
     "termine": 'MC1R[tiab] AND melanoma[tiab] AND (variant[tiab] OR polymorphism[tiab] OR risk[tiab])'},
    {"gene": "PTEN", "rischio": "Sindromico",
     "ruolo": "Citato dalle linee guida NCCN tra i geni da considerare nei pannelli per melanoma (sindrome di Cowden).",
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
    {"titolo": "NCCN Clinical Practice Guidelines in Oncology: Melanoma: Cutaneous (versione corrente; "
               "il testo completo richiede una registrazione gratuita)",
     "url": "https://www.nccn.org/guidelines/category_1"},
]


def valuta_genetica(p):
    """
    Applica i criteri descritti in letteratura per decidere se vale la pena parlare con un
    genetista. Importante: NON dice "devi fare il test" né "non ti serve": segnala solo se
    i dati inseriti rientrano nei criteri e chiede di discuterne con uno specialista.
    """
    mel_pers = a_intero(p.get("melanomi_personali"))
    mel_fam = a_intero(p.get("fam_melanoma_1grado")) + a_intero(p.get("fam_melanoma_altri"))
    pancreas_fam = a_intero(p.get("fam_pancreas"))
    pancreas_1 = a_intero(p.get("fam_pancreas_1grado"))
    astro_fam = a_intero(p.get("fam_astrocitoma"))
    pers_panc = 1 if p.get("pers_pancreas") else 0
    pers_astro = 1 if p.get("pers_astrocitoma") else 0

    # Regola dei 3: totale delle diagnosi di melanoma, pancreas, astrocitoma nella stessa linea familiare
    diagnosi = mel_pers + mel_fam + pancreas_fam + pers_panc + astro_fam + pers_astro

    # Spettro dei tumori BAP1 (uveale, mesotelioma, rene) + melanoma cutaneo
    bap1_tipici = (a_intero(p.get("fam_uveale")) + a_intero(p.get("fam_mesotelioma")) + a_intero(p.get("fam_rene"))
                   + sum(1 for k in ("pers_uveale", "pers_mesotelioma", "pers_rene") if p.get(k)))
    bap1_spettro = bap1_tipici + (1 if (mel_pers + mel_fam) >= 1 else 0)

    criteri = [
        {"id": "tre_melanomi", "soddisfatto": mel_pers >= 3,
         "titolo": "3 o più melanomi primari nella stessa persona",
         "spiegazione": f"Melanomi primari indicati: {mel_pers}.",
         "fonte": "Leachman 2009 e 2017; NCCN"},
        {"id": "regola_tre", "soddisfatto": diagnosi >= 3,
         "titolo": "Almeno 3 diagnosi tra melanoma, tumore del pancreas e astrocitoma nella stessa linea familiare (tua inclusa)",
         "spiegazione": f"Diagnosi totali indicate: {diagnosi}. Leachman 2009 considera melanoma e tumore del pancreas nei "
                        "parenti di 1o e 2o grado dello stesso lato della famiglia; l'astrocitoma è incluso dalle linee guida NCCN.",
         "fonte": "Leachman 2009 e 2017; NCCN"},
        {"id": "mel_pancreas", "soddisfatto": mel_pers >= 1 and pancreas_1 >= 1,
         "titolo": "Melanoma personale e parente di primo grado con tumore del pancreas",
         "spiegazione": "Per le linee guida NCCN, in un melanoma invasivo con un parente di primo grado con tumore del pancreas "
                        "è raccomandato un pannello multigene che includa CDKN2A.",
         "fonte": "NCCN"},
        {"id": "bap1", "soddisfatto": bap1_tipici >= 1 and bap1_spettro >= 2,
         "titolo": "Più tumori dello spettro BAP1 (melanoma uveale, mesotelioma, carcinoma renale, melanoma cutaneo)",
         "spiegazione": f"Tumori dello spettro BAP1 indicati: {bap1_spettro}. Criterio semplificato: il genetista usa "
                        "criteri più completi.",
         "fonte": "Leachman 2017; NCCN"},
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
        esito, msg = "dati_insufficienti", ("Compila la sezione 'Familiarità' nel Profilo: senza quei dati non posso verificare i criteri.")
    elif soddisfatti:
        esito = "criteri_soddisfatti"
        msg = ("I dati inseriti rientrano in almeno un criterio descritto in letteratura. Ti consigliamo di parlarne con il "
               "dermatologo o con un medico genetista (consulenza genetica oncologica): sarà lo specialista a decidere "
               "se e quale test proporre, di norma dopo la consulenza e, quando possibile, partendo da un familiare affetto. "
               "Geni più citati dalle linee guida: " + ", ".join(geni) + ". L'uso dei pannelli multigene è ancora "
               "oggetto di discussione tra gli specialisti: per questo conta la consulenza prima del test.")
    else:
        esito = "nessun_criterio"
        msg = ("Con i dati inseriti non rientri nei criteri più usati. Il test genetico per il melanoma è indicato solo in una "
               "piccola minoranza di persone e non viene proposto di routine. Se la tua storia familiare cambia o hai dubbi, "
               "aggiorna il profilo e parlane col dermatologo.")
    if esito_gen in ("si_positivo", "si_negativo", "si_non_informativo"):
        msg += " Hai indicato di aver già eseguito un test genetico: porta il referto al dermatologo."
    return {"esito": esito, "messaggio": msg, "criteri": criteri, "geni_suggeriti": geni, "fonti": FONTI_GENETICA}


# ------------------------------------------------------------------------------------------
# 4c. Indice UV (Open-Meteo di default; OpenWeather One Call 4.0/3.0 se lo scegli e hai la chiave)
# ------------------------------------------------------------------------------------------
CATEGORIE_UV = [
    # (da, a, nome, colore OMS, consiglio)
    (0, 2.99, "Basso", "#3f9c35", "Nessuna protezione particolare per le attività normali; occhiali da sole nelle giornate luminose."),
    (3, 5.99, "Moderato", "#e8c400", "Protezione consigliata: ombra nelle ore centrali, cappello, occhiali e crema solare."),
    (6, 7.99, "Alto", "#f28c00", "Protezione necessaria: riduci l'esposizione tra le 10 e le 16, crema solare SPF 30+, cappello e occhiali."),
    (8, 10.99, "Molto alto", "#d9261c", "Precauzioni extra: evita il sole nelle ore centrali, cerca l'ombra, copri la pelle, SPF 30+. La pelle non protetta si scotta in fretta."),
    (11, 999, "Estremo", "#8e44ad", "Evita l'esposizione diretta: la pelle non protetta può scottarsi in pochi minuti."),
]

# Dose minima che provoca arrossamento (MED) in "dosi standard di eritema" (1 SED = 100 J/m2).
# Intervalli riportati da Fajuyigbe & Young 2016 (Tabella 1): I 2-3, II 2,5-3, III 3-5, IV 4-7, V 6-20,
# VI 6-20. Qui si usa il valore PIÙ BASSO di ciascun intervallo, cioè la stima più prudente.
MED_SED_PRUDENTE = {1: 2.0, 2: 2.5, 3: 3.0, 4: 4.0, 5: 6.0, 6: 6.0}

_cache_uv = {}


def categoria_uv(uvi):
    for da, a, nome, colore, consiglio in CATEGORIE_UV:
        if da <= uvi <= a or (uvi > a and a == 999):
            return {"nome": nome, "colore": colore, "consiglio": consiglio, "da": da}
    return {"nome": "Basso", "colore": CATEGORIE_UV[0][3], "consiglio": CATEGORIE_UV[0][4], "da": 0}


def minuti_scottatura(uvi, fototipo):
    """
    Stima PRUDENTE dei minuti di sole a cielo sereno e pelle non protetta prima di un
    arrossamento. Formula: minuti = MED(in SED) x 60 / UVI, perché in un'ora si ricevono circa
    tanti SED quanti sono i punti di UVI (Lucas et al. 2018, su superficie orizzontale non ombreggiata).
    Serve solo come ordine di grandezza: nuvole, riflessi (neve, acqua), quota e creme cambiano molto.
    """
    ft = a_intero(fototipo)
    if ft not in MED_SED_PRUDENTE or uvi is None:
        return None
    if uvi < 0.5:
        return {"minuti": None, "testo": "oltre 2 ore (UV molto basso)"}
    m = MED_SED_PRUDENTE[ft] * 60.0 / uvi
    return {"minuti": int(round(m)), "testo": f"circa {int(round(m))} minuti"}


# Tutte le richieste verso internet passano da qui. Regole: solo https (http solo verso questo stesso computer,
# per le prove), niente indirizzi "file:" o "ftp:" (nemmeno se un servizio ci reindirizza lì), e una risposta
# non può superare una dimensione massima (una risposta enorme non deve riempire la memoria).
_APRITORE_WEB = urllib.request.OpenerDirector()
for _gestore in (urllib.request.ProxyHandler(), urllib.request.HTTPHandler(), urllib.request.HTTPSHandler(),
                 urllib.request.HTTPRedirectHandler(), urllib.request.HTTPDefaultErrorHandler(), urllib.request.HTTPErrorProcessor()):
    _APRITORE_WEB.add_handler(_gestore)
MAX_BYTE_RISPOSTA_WEB = 8 * 1024 * 1024


def _leggi_web(req, timeout, massimo=MAX_BYTE_RISPOSTA_WEB):
    """Esegue la richiesta e restituisce i byte della risposta (con i controlli descritti sopra)."""
    u = urllib.parse.urlsplit(req.full_url)
    if not (u.scheme == "https" or (u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost"))):
        raise ErroreServizio("indirizzo non ammesso (solo https)")
    with _APRITORE_WEB.open(req, timeout=timeout) as r:
        dati = r.read(massimo + 1)
    if len(dati) > massimo:
        raise ErroreServizio("risposta troppo grande")
    return dati


def _http_json(url, timeout=20, headers=None):
    """Scarica un indirizzo web e lo legge come JSON. Trasforma gli errori di rete in messaggi chiari."""
    req = urllib.request.Request(url, headers=dict({"User-Agent": "NeoTracker/" + VERSIONE}, **(headers or {})))
    try:
        return json.loads(_leggi_web(req, timeout).decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        raise ErroreServizio(f"HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise ErroreServizio("connessione non riuscita: " + str(e.reason)) from e
    except (TimeoutError, OSError) as e:
        raise ErroreServizio("tempo scaduto o rete non disponibile") from e
    except ValueError as e:
        raise ErroreServizio("risposta non valida dal servizio") from e


def _owm_ora_locale(ts, off):
    return datetime.fromtimestamp(int(ts) + int(off), timezone.utc)


def _owm_chiamata(base, percorso, lat, lon, chiave, extra=""):
    return _http_json(f"{base}{percorso}?lat={lat:.2f}&lon={lon:.2f}&units=metric{extra}&appid={urllib.parse.quote(chiave)}")


def _uv_owm_v4(lat, lon, chiave):
    """One Call 4.0 (abbonamento 'One Call pay-per-call'): corrente + orario + giornaliero = 3-4 chiamate."""
    base = os.environ.get("NEOTRACKER_OWM_BASE", "https://api.openweathermap.org")
    cur_r = _owm_chiamata(base, "/data/4.0/onecall/current", lat, lon, chiave)
    cur = (cur_r.get("data") or [{}])[0]
    off = int(cur_r.get("timezone_offset", 0))
    ore_r = _owm_chiamata(base, "/data/4.0/onecall/timeline/1h", lat, lon, chiave)
    voci = list(ore_r.get("data") or [])
    if 0 < len(voci) < 24:                    # una risposta contiene al massimo 20 ore: ne chiedo altre
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
        ore.append({"ora": t.strftime("%H:%M"), "giorno": t.strftime("%d/%m"), "uvi": round(float(v.get("uvi") or 0), 1)})
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
    if mx is None:                            # ripiego: il massimo delle ore note di oggi
        oggi_ore = [o["uvi"] for o, d in zip(ore, date_ore) if d == adesso.date()]
        mx = max(oggi_ore + [uvi_ora])
    return {"fonte": "OpenWeather One Call 4.0", "uvi_ora": uvi_ora, "uvi_max": max(mx, uvi_ora), "ore": ore,
            "aggiornato": adesso.strftime("%d/%m/%Y %H:%M") + " (ora locale del luogo)", "fuso": cur_r.get("timezone", "")}


def _uv_owm_v3(lat, lon, chiave):
    """One Call 3.0 (vecchio abbonamento): una sola chiamata."""
    base = os.environ.get("NEOTRACKER_OWM_BASE", "https://api.openweathermap.org")
    d = _owm_chiamata(base, "/data/3.0/onecall", lat, lon, chiave, "&exclude=minutely,alerts")
    off = int(d.get("timezone_offset", 0))
    ore = []
    for v in (d.get("hourly") or [])[:24]:
        t = _owm_ora_locale(v["dt"], off)
        ore.append({"ora": t.strftime("%H:%M"), "giorno": t.strftime("%d/%m"), "uvi": round(float(v.get("uvi", 0)), 1)})
    cur = d.get("current") or {}
    daily0 = (d.get("daily") or [{}])[0]
    return {"fonte": "OpenWeather One Call 3.0", "uvi_ora": round(float(cur.get("uvi", 0)), 1),
            "uvi_max": round(float(daily0.get("uvi", cur.get("uvi", 0))), 1), "ore": ore,
            "aggiornato": _owm_ora_locale(cur.get("dt", time.time()), off).strftime("%d/%m/%Y %H:%M") + " (ora locale del luogo)",
            "fuso": d.get("timezone", "")}


def _uv_openweather(lat, lon, chiave):
    """
    Prima prova One Call 4.0 (quella che OpenWeather consiglia oggi); se la chiave non è abilitata
    prova One Call 3.0 (abbonamenti più vecchi). Se nessuna delle due risponde, spiega perché.
    """
    errori = []
    for nome, funzione in (("4.0", _uv_owm_v4), ("3.0", _uv_owm_v3)):
        try:
            return funzione(lat, lon, chiave)
        except ErroreServizio as e:
            errori.append((nome, str(e)))
            if not any(c in str(e) for c in ("401", "403", "404")):
                break                          # non è un problema di abilitazione: inutile riprovare con l'altra versione
    testo = " ".join(t for _, t in errori)
    if "429" in testo:
        raise ErroreServizio("OpenWeather: limite di chiamate raggiunto (429).")
    if "401" in testo or "403" in testo:
        raise ErroreServizio("OpenWeather ha rifiutato la chiave (401): controlla che sia corretta e che sul tuo account sia "
                             "attivo l'abbonamento 'One Call API' (pagamento a chiamata, 1.000 chiamate al giorno gratuite). "
                             "Dopo l'iscrizione la chiave può impiegare qualche minuto ad attivarsi.")
    raise ErroreServizio("; ".join(f"One Call {n}: {t}" for n, t in errori))


def _data_ora_italiana(iso):
    """'2026-11-08T10:15' -> '08/11/2026 10:15' (se il formato è diverso lo lascia com'è)."""
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
        ore.append({"ora": t[11:16], "giorno": t[8:10] + "/" + t[5:7], "uvi": round(float(v or 0), 1)})
    mx = ((d.get("daily") or {}).get("uv_index_max") or [cur.get("uv_index", 0)])[0]
    return {"fonte": "Open-Meteo", "uvi_ora": round(float(cur.get("uv_index") or 0), 1),
            "uvi_max": round(float(mx or 0), 1), "ore": ore,
            "aggiornato": _data_ora_italiana(cur.get("time") or "") + " (ora locale del luogo)",
            "fuso": d.get("timezone", "")}


def usa_openweather(imp):
    """True solo se hai SCELTO OpenWeather nelle Impostazioni e hai inserito la chiave."""
    return imp.get("fonte_uv") == "openweather" and bool((imp.get("openweather_key") or "").strip())


def indice_uv(lat, lon, fototipo=None, localita=""):
    """
    Restituisce l'indice UV per il punto indicato.
    - Predefinito: Open-Meteo (gratuito, senza chiave).
    - Se nelle Impostazioni scegli OpenWeather e inserisci la tua chiave, usa OpenWeather;
      se OpenWeather dà errore, usa Open-Meteo e te lo dice chiaramente.
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
                avviso = f"OpenWeather non disponibile ({e}). Mostro i dati di Open-Meteo."
        elif imp.get("fonte_uv") == "openweather":
            avviso = "Hai scelto OpenWeather ma manca la chiave (Impostazioni): mostro i dati di Open-Meteo."
        if dati is None:
            try:
                dati = _uv_openmeteo(lat, lon)
            except ErroreServizio as e:
                raise ErroreServizio((avviso + " " if avviso else "") + f"Il servizio Open-Meteo non risponde ({e}).")
        dati["avviso"] = avviso
        _cache_uv[chiave_cache] = (time.time(), dict(dati))
    cat_ora, cat_max = categoria_uv(dati["uvi_ora"]), categoria_uv(dati["uvi_max"])
    dati.update({"lat": lat, "lon": lon, "localita": localita,
                 "categoria_ora": cat_ora, "categoria_max": cat_max,
                 "scottatura_max": minuti_scottatura(dati["uvi_max"], fototipo),
                 "scottatura_ora": minuti_scottatura(dati["uvi_ora"], fototipo)})
    mx = dati["uvi_max"]
    if mx >= 8:
        verdetto = {"livello": "rosso", "titolo": "Oggi i raggi UV sono molto dannosi",
                    "testo": "Evita il sole nelle ore centrali e proteggi bene la pelle."}
    elif mx >= 6:
        verdetto = {"livello": "arancio", "titolo": "Oggi i raggi UV sono dannosi per pelle non protetta",
                    "testo": "Servono ombra, abiti, cappello e crema solare nelle ore centrali."}
    elif mx >= 3:
        verdetto = {"livello": "giallo", "titolo": "UV moderati: serve protezione nelle ore centrali",
                    "testo": "L'OMS consiglia di proteggersi a partire da un indice UV di 3."}
    else:
        verdetto = {"livello": "verde", "titolo": "Oggi i raggi UV sono bassi",
                    "testo": "Protezione non necessaria per le attività normali (attenzione a neve, acqua, quota)."}
    dati["verdetto"] = verdetto
    dati["fonti"] = [
        {"titolo": "OMS/OMM/UNEP/ICNIRP - Global Solar UV Index: A Practical Guide (2002)",
         "url": "https://www.who.int/publications/i/item/9241590076"},
        {"titolo": "Lucas RM et al. Are current guidelines for sun protection optimal for health? "
                   "Photochem Photobiol Sci 2018;17:1956-63 (UV Index e dose di eritema)",
         "url": "https://doi.org/10.1039/c7pp00374a"},
        {"titolo": "Fajuyigbe D, Young AR. The impact of skin colour on human photobiological responses. "
                   "Pigment Cell Melanoma Res 2016;29:607-18 (dose minima di eritema per fototipo)",
         "url": "https://pubmed.ncbi.nlm.nih.gov/27454804/"},
    ]
    return dati


def cerca_localita(testo):
    """Trasforma un nome di città in coordinate (Open-Meteo; OpenWeather solo se l'hai scelto e hai la chiave)."""
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
    r = _http_json(f"{base}/v1/search?name={urllib.parse.quote(testo)}&count=5&language=it&format=json")
    return [{"nome": ", ".join(x for x in (c.get("name"), c.get("admin1"), c.get("country_code")) if x),
             "lat": c["latitude"], "lon": c["longitude"]} for c in (r.get("results") or [])]


def posizione_da_ip():
    """Posizione approssimata dal tuo indirizzo internet (precisione: la città)."""
    base = os.environ.get("NEOTRACKER_IP_BASE", "https://ipwho.is")
    r = _http_json(base + "/")
    if r.get("success") is False or "latitude" not in r:
        raise ErroreServizio("posizione da indirizzo internet non disponibile")
    return {"lat": r["latitude"], "lon": r["longitude"],
            "nome": ", ".join(x for x in (r.get("city"), r.get("country_code")) if x)}


# ------------------------------------------------------------------------------------------
# 4d. Letteratura scientifica da PubMed (E-utilities, gratuite e pubbliche)
# ------------------------------------------------------------------------------------------
_ultima_chiamata_ncbi = [0.0]
_blocco_ncbi = threading.Lock()


def _ncbi_get(percorso, parametri):
    """Una chiamata a PubMed, con almeno 0,4 s tra una e l'altra (il limite senza chiave è 3 al secondo)."""
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
        raise ErroreServizio(f"PubMed ha risposto con errore {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErroreServizio("PubMed non raggiungibile (controlla la connessione internet)") from e


def interpreta_xml_pubmed(xml_bytes, max_abstract=1100):
    """Legge la risposta XML di PubMed e restituisce un elenco di articoli semplici."""
    articoli = []
    if b"<!ENTITY" in xml_bytes:           # le risposte vere di PubMed non dichiarano "entità": è il trucco degli XML-bomba
        return articoli
    try:
        # Controllo di sicurezza (bandit B314): fonte: PubMed via https, senza dichiarazioni ENTITY, dimensione limitata.
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
    Cerca su PubMed e restituisce {conteggio, articoli, da_cache, data}.
    I risultati vengono tenuti in cache per GIORNI_CACHE_LETTERATURA giorni: se la rete manca
    e c'è una copia vecchia, la usa e lo segnala.
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
        dati = {"t": time.time(), "data": datetime.now().strftime("%d/%m/%Y"), "conteggio": conteggio,
                "articoli": articoli, "termine": termine, "da_cache": False}
        f.write_text(json.dumps(dati, ensure_ascii=False), encoding="utf-8")
        return dati
    except ErroreServizio:
        if vecchia:
            vecchia["da_cache"] = True
            vecchia["obsoleta"] = True
            return vecchia
        raise


TEMI_LETTERATURA = {
    "riconoscimento": {
        "titolo": "Riconoscere un neo sospetto",
        "sezioni": [
            ("Criteri ABCDE e segno del 'brutto anatroccolo'",
             '(melanoma[tiab]) AND (ABCDE[tiab] OR "ugly duckling"[tiab]) AND (diagnosis[tiab] OR detection[tiab] OR recognition[tiab])', "relevance"),
            ("Dermoscopia e diagnosi precoce (revisioni)",
             'melanoma[tiab] AND dermoscopy[tiab] AND ("early diagnosis"[tiab] OR "early detection"[tiab]) AND review[pt]', "relevance"),
            ("Autoesame della pelle",
             'melanoma[tiab] AND ("skin self-examination"[tiab] OR "skin self examination"[tiab])', "relevance"),
            ("Fotografia sequenziale e monitoraggio dei nei nel tempo",
             'melanoma[tiab] AND ("total body photography"[tiab] OR "sequential digital dermoscopy"[tiab] OR "digital dermoscopic monitoring"[tiab])', "relevance"),
        ]},
    "strumenti_ai": {
        "titolo": "Quanto sono affidabili app e intelligenza artificiale",
        "sezioni": [
            ("App per smartphone e rischio di cancro della pelle: accuratezza diagnostica",
             'smartphone[tiab] AND (app[tiab] OR application[tiab]) AND melanoma[tiab] AND (accuracy[tiab] OR diagnostic[tiab])', "relevance"),
            ("Deep learning e melanoma: revisioni sistematiche",
             '"deep learning"[tiab] AND melanoma[tiab] AND ("systematic review"[pt] OR meta-analysis[pt])', "relevance"),
        ]},
    "genetica": {
        "titolo": "Melanoma ereditario e test genetico",
        "sezioni": [
            ("Linee guida e criteri per il test genetico",
             'melanoma[tiab] AND (hereditary[tiab] OR familial[tiab]) AND ("genetic testing"[tiab] OR "genetic counseling"[tiab]) AND (guideline[tiab] OR criteria[tiab] OR recommendations[tiab])', "relevance"),
            ("Revisioni sul melanoma familiare (CDKN2A, CDK4)",
             'melanoma[tiab] AND familial[tiab] AND (CDKN2A[tiab] OR CDK4[tiab]) AND review[pt]', "relevance"),
            ("Studi più recenti sui geni di predisposizione",
             'melanoma[tiab] AND germline[tiab] AND (susceptibility[tiab] OR predisposition[tiab])', "date"),
        ]},
}

REGIONI_ACRALI = ("palmo", "mano", "piede", "tallone", "pianta", "dita")
REGIONI_TESTA = ("viso", "testa", "cuoio", "collo", "nuca")


def temi_personalizzati(profilo, regioni):
    """Sezioni di letteratura scelte in base al profilo e alle sedi dei tuoi nei."""
    sez = []
    if a_intero(profilo.get("fototipo")) >= 5:
        sez.append(("Melanoma nelle pelli scure (spesso acrale)",
                    'melanoma[tiab] AND ("skin of color"[tiab] OR "dark skin"[tiab] OR acral[tiab]) AND (diagnosis[tiab] OR detection[tiab])', "relevance"))
    reg = " ".join(regioni).lower()
    if any(k in reg for k in REGIONI_ACRALI):
        sez.append(("Melanoma acrale (mani, piedi, unghie): dermoscopia",
                    'acral[tiab] AND melanoma[tiab] AND dermoscop*[tiab]', "relevance"))
    if any(k in reg for k in REGIONI_TESTA):
        sez.append(("Lentigo maligna e melanoma del volto",
                    '"lentigo maligna"[tiab] AND (diagnosis[tiab] OR dermoscopy[tiab])', "relevance"))
    if profilo.get("n_nevi") in ("50-99", "100+") or profilo.get("nevi_atipici") == "si":
        sez.append(("Molti nei o nei atipici: sorveglianza",
                    '("dysplastic nevus"[tiab] OR "atypical nevi"[tiab] OR "high nevus count"[tiab] OR "many nevi"[tiab]) AND melanoma[tiab] AND (surveillance[tiab] OR monitoring[tiab])', "relevance"))
    if profilo.get("immunosoppressione"):
        sez.append(("Melanoma e immunosoppressione",
                    'melanoma[tiab] AND (immunosuppress*[tiab] OR "organ transplant"[tiab]) AND (screening[tiab] OR risk[tiab])', "relevance"))
    return sez
