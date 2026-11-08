# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# NeoTracker - Copyright (C) 2026 gli autori di NeoTracker.
# Software libero: puoi ridistribuirlo e/o modificarlo secondo i termini della GNU General Public License
# versione 3 o successiva. Nessuna garanzia, nemmeno di idoneità a uno scopo (vedi il file LICENSE).
# NON è un dispositivo medico e non fa diagnosi: vedi DISCLAIMER.md.
"""
==========================================================================================
 NeoTracker  -  mappa del corpo, storico dei nei, analisi automatica, UV e letteratura
==========================================================================================

COSA È
-------
Un'app che gira SOLO sul tuo PC. Ha una finestra tutta sua (senza barra degli indirizzi,
con la propria icona nella barra delle applicazioni): sotto il cofano usa Edge o Chrome già
presenti sul PC, in modalità "app". Nessun dato viene caricato su internet, tranne queste
richieste che hai sotto controllo:
  - il servizio meteo Open-Meteo (predefinito, gratuito) per l'indice UV di oggi, oppure OpenWeather
    se lo scegli tu nelle Impostazioni e inserisci la tua chiave;
  - PubMed (banca dati scientifica pubblica) per la letteratura;
  - SkinSense (un servizio online) SOLO se lo attivi tu nelle Impostazioni.

COSA FA
-------
  1. Più utenti sullo stesso PC: all'avvio scegli chi sei (ognuno ha i suoi dati).
  2. Profilo con fenotipo (fototipo, capelli, occhi, nei...) e familiarità.
  3. Mappa interattiva del corpo (fronte e retro): clicchi dove si trova il neo e il
     punto viene salvato con precisione. Puoi ingrandire, spostare il punto, rinominarlo.
  4. Storico fotografico di ogni neo: ogni foto è salvata con la data; puoi confrontarne
     due, misurare il diametro nel tempo e stampare una scheda per il dermatologo.
  5. Analisi automatica di ogni foto con tutti i metodi installati (usa melanoma_batch.py).
  6. Letteratura scientifica (PubMed) su riconoscimento dei nevi e melanoma ereditario,
     con i geni da conoscere e i criteri per valutare una consulenza/test genetico.
  7. Indice UV di oggi nel punto in cui ti trovi (fonte Open-Meteo; OpenWeather a scelta).

COME SI AVVIA
-------------
  - Dall'icona "NeoTracker" sul Desktop (si apre solo la finestra dell'app, nessuna finestra
    nera), oppure
  - aprendo questo file con Spyder e premendo PLAY (la freccia verde).
Per FERMARE l'app basta chiudere la sua finestra con la X: il programma si spegne da solo
(se sta analizzando una foto, finisce prima l'analisi). Se qualcosa non va, il file
"neotracker.log" nella cartella dei dati dice cosa è successo.

IMPORTANTE
----------
NeoTracker NON è uno strumento medico e non fa diagnosi. Le reti neurali usate sono
prototipi di ricerca. Fototipo, età e familiarità NON cambiano il risultato delle reti
(che guardano solo i pixel della foto): servono a contestualizzare il rischio e a scegliere
la letteratura giusta. Ogni neo che cambia, sanguina, prude o ti preoccupa va fatto vedere
a un dermatologo, qualunque cosa dica l'app.
"""

# ==========================================================================================
# 1. IMPOSTAZIONI (di solito non serve toccarle)
# ==========================================================================================
import os
from pathlib import Path

# Cartella dove vengono salvati TUTTI i dati (database, foto, rapporti). Se la sposti,
# sposta anche i dati già esistenti. Il valore predefinito sta accanto ai tuoi progetti.
# (Per cambiarla senza toccare il codice si può impostare la variabile d'ambiente NEOTRACKER_DATI.)
CARTELLA_DATI = Path(os.environ.get("NEOTRACKER_DATI") or (Path.home() / "melanoma-repos" / "NeoTracker_dati"))

# Cartella dove sono installati i progetti di analisi (serve per lanciare melanoma_batch.py).
# (Variabile d'ambiente facoltativa: NEOTRACKER_REPO.)
CARTELLA_REPO = Path(os.environ.get("NEOTRACKER_REPO") or (Path.home() / "melanoma-repos"))

# Indirizzo e porta del mini-server locale. 127.0.0.1 significa "solo questo computer":
# nessun altro dispositivo della rete può collegarsi.
INDIRIZZO = "127.0.0.1"
PORTA = 8750

# Quanto vecchia può essere una ricerca bibliografica in cache prima di rifarla (giorni).
GIORNI_CACHE_LETTERATURA = 7

# Dimensione massima di una foto caricata (megabyte).
MAX_MB_FOTO = 60

# Dimensione massima di una foto in "megapixel" (larghezza x altezza). Serve a difendersi dalle
# immagini-trappola, piccole come file ma enormi una volta aperte, che riempirebbero la memoria.
MAX_PIXEL_IMMAGINE = 150_000_000

# ==========================================================================================
# 2. LIBRERIE (tutte incluse in Python, tranne Pillow che di solito c'è già)
# ==========================================================================================
import base64
import json
import mimetypes
import os
import hmac
import re
import secrets
import select
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import hashlib
import shutil

try:
    from PIL import Image, ImageOps          # Pillow: serve per miniature, rotazione e data di scatto
    HA_PILLOW = True
except Exception:                            # senza Pillow l'app funziona lo stesso, ma senza miniature
    HA_PILLOW = False

VERSIONE = "1.2"
# Versione dell'avviso iniziale ("non è un dispositivo medico..."). Se la cambi, tutti gli utenti lo rivedono e lo riaccettano.
AVVERTENZE_VERSIONE = "1"
CARTELLA_SCRIPT = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()


# ==========================================================================================
# 3. DATI: database SQLite, impostazioni, cartelle
# ==========================================================================================
# SQLite è un "database in un file" incluso in Python: niente da installare. Tutti i dati
# (utenti, nei, foto) stanno in CARTELLA_DATI\neotracker.db. Le foto stanno in CARTELLA_DATI\foto.

def percorso_db():
    return Path(CARTELLA_DATI) / "neotracker.db"


def adesso():
    """Data e ora attuali come testo ISO, es. '2026-11-08T10:52:31'."""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def connetti():
    """Apre una connessione al database. Ogni richiesta ne apre una propria (è più sicuro)."""
    Path(CARTELLA_DATI).mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(percorso_db()), timeout=30)
    con.row_factory = sqlite3.Row            # permette di leggere le colonne per nome
    con.execute("PRAGMA foreign_keys = ON")  # se cancelli un utente, spariscono anche i suoi nei
    return con


def inizializza_db():
    """Crea le tabelle la prima volta. Se esistono già non fa nulla."""
    with connetti() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS utenti (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nome      TEXT NOT NULL,
            creato    TEXT NOT NULL,
            profilo   TEXT NOT NULL DEFAULT '{}'      -- fenotipo e familiarità (testo JSON)
        );
        CREATE TABLE IF NOT EXISTS nevi (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            utente_id  INTEGER NOT NULL REFERENCES utenti(id) ON DELETE CASCADE,
            nome       TEXT NOT NULL,
            vista      TEXT NOT NULL,                 -- 'fronte' oppure 'retro'
            x          REAL NOT NULL,                 -- posizione sulla mappa, da 0 a 1
            y          REAL NOT NULL,
            regione    TEXT NOT NULL DEFAULT '',      -- es. 'Torace destro'
            note       TEXT NOT NULL DEFAULT '',
            creato     TEXT NOT NULL,
            archiviato INTEGER NOT NULL DEFAULT 0     -- 1 = tolto dalla mappa ma conservato
        );
        CREATE TABLE IF NOT EXISTS foto (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            nevo_id       INTEGER NOT NULL REFERENCES nevi(id) ON DELETE CASCADE,
            file          TEXT NOT NULL,              -- nome del file originale (cartella foto)
            scattata_il   TEXT NOT NULL,              -- data dello scatto (AAAA-MM-GG)
            diametro_mm   REAL,                       -- misura inserita da te (facoltativa)
            tipo          TEXT NOT NULL DEFAULT 'normale',   -- 'normale' oppure 'dermoscopica'
            note          TEXT NOT NULL DEFAULT '',
            stato_analisi TEXT NOT NULL DEFAULT 'nessuna',   -- nessuna | in_coda | in_corso | ok | errore
            rapporto      TEXT NOT NULL DEFAULT '',   -- cartella del rapporto (dentro CARTELLA_DATI)
            messaggio     TEXT NOT NULL DEFAULT '',   -- eventuale errore dell'analisi
            esito         TEXT NOT NULL DEFAULT '',   -- sintesi: attenzione | benigno | discordante | nessuno
            creato        TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_nevi_utente ON nevi(utente_id);
        CREATE INDEX IF NOT EXISTS idx_foto_nevo   ON foto(nevo_id);
        """)
        # se all'avvio ci sono analisi rimaste "in corso" (app chiusa a metà), le segno interrotte
        con.execute("UPDATE foto SET stato_analisi='errore', messaggio='Analisi interrotta (app chiusa).' "
                    "WHERE stato_analisi IN ('in_corso', 'in_coda')")


def riga_a_dict(riga):
    return dict(riga) if riga is not None else None


# ---- impostazioni (chiavi API, posizione, interruttori) -----------------------------------
IMPOSTAZIONI_PREDEFINITE = {
    "avvertenze_accettate": "",   # versione dell'avviso iniziale già accettata (vuoto = non ancora accettato)
    "fonte_uv": "open-meteo",     # da dove arriva l'indice UV: "open-meteo" (predefinita, gratis, senza chiave) oppure "openweather"
    "openweather_key": "",        # la tua chiave OpenWeather (serve solo se scegli OpenWeather; resta solo in questo PC)
    "usa_skinsense": False,       # se True la foto viene inviata a SkinSense (servizio online)
    "lat": None, "lon": None,     # posizione per l'indice UV
    "localita": "",               # nome del posto (es. 'Torino, IT')
    "ncbi_email": "",             # facoltativo: la tua email per cortesia verso PubMed
}
_blocco_impostazioni = threading.Lock()


def leggi_impostazioni():
    p = Path(CARTELLA_DATI) / "impostazioni.json"
    dati = dict(IMPOSTAZIONI_PREDEFINITE)
    try:
        if p.exists():
            dati.update(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        pass
    return dati


def salva_impostazioni(nuove):
    """Aggiorna solo i campi ammessi e salva su file."""
    with _blocco_impostazioni:
        dati = leggi_impostazioni()
        for k in IMPOSTAZIONI_PREDEFINITE:
            if k in nuove:
                dati[k] = nuove[k]
        Path(CARTELLA_DATI).mkdir(parents=True, exist_ok=True)
        destinazione = Path(CARTELLA_DATI) / "impostazioni.json"
        provvisorio = destinazione.with_suffix(".json.tmp")
        provvisorio.write_text(json.dumps(dati, ensure_ascii=False, indent=2), encoding="utf-8")
        if os.name != "nt":
            os.chmod(provvisorio, 0o600)          # il file contiene la tua chiave: leggibile solo da te (Linux/Mac)
        os.replace(provvisorio, destinazione)     # sostituzione "tutta d'un colpo": un'interruzione non lascia un file a metà
        return dati


def impostazioni_pubbliche():
    """Versione per il browser: la chiave segreta NON viene mai restituita, solo se c'è."""
    d = leggi_impostazioni()
    chiave = d.get("openweather_key") or ""
    d["ha_chiave_owm"] = bool(chiave)
    d["chiave_owm_finale"] = ("…" + chiave[-4:]) if len(chiave) >= 8 else ""
    d.pop("openweather_key", None)
    d["cartella_dati"] = str(CARTELLA_DATI)
    d["ha_pillow"] = HA_PILLOW
    d["versione"] = VERSIONE
    return d


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


# ==========================================================================================
# 5. FOTO E ANALISI: salvataggio, miniature, data di scatto, analisi automatica in coda
# ==========================================================================================

class ErroreRichiesta(Exception):
    """Errore dovuto a dati sbagliati inviati dal browser (diventa una risposta 400/404/409)."""
    def __init__(self, messaggio, codice=400):
        super().__init__(messaggio)
        self.codice = codice


def cartella_foto():
    return Path(CARTELLA_DATI) / "foto"


def cartella_rapporti():
    return Path(CARTELLA_DATI) / "rapporti"


def cartella_miniature():
    return Path(CARTELLA_DATI) / "miniature"


def cartella_avatar():
    return Path(CARTELLA_DATI) / "avatar"


def dentro(cartella_base, percorso):
    """True se 'percorso' sta davvero dentro 'cartella_base' (difesa contro percorsi tipo ..\\..)."""
    try:
        Path(percorso).resolve().relative_to(Path(cartella_base).resolve())
        return True
    except (ValueError, OSError):
        return False


# ------------------------------------------------------------------------------------------
# 5a. Controllo e salvataggio della foto
# ------------------------------------------------------------------------------------------
def riconosci_formato(dati):
    """Guarda i primi byte del file (non l'estensione) e dice che immagine è. None se non è supportata."""
    if dati[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if dati[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if dati[:4] == b"RIFF" and dati[8:12] == b"WEBP":
        return ".webp"
    if dati[:2] == b"BM":
        return ".bmp"
    if dati[:4] in (b"II*\x00", b"MM\x00*") and HA_PILLOW:
        return ".tif"
    return None


def data_exif(img):
    """Data di scatto scritta dalla fotocamera nella foto (AAAA-MM-GG), oppure None."""
    try:
        ex = img.getexif()
        valore = None
        try:
            ifd = ex.get_ifd(0x8769)
            valore = ifd.get(36867) or ifd.get(36868)
        except Exception:
            pass
        valore = valore or ex.get(306)
        m = re.match(r"\s*(\d{4}):(\d{2}):(\d{2})", str(valore or ""))
        if m:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if date(1990, 1, 1) <= d <= date.today() + timedelta(days=1):
                return d.isoformat()
    except Exception:
        pass
    return None


def data_valida(testo):
    """Controlla che il testo sia una data AAAA-MM-GG non nel futuro; restituisce il testo pulito."""
    try:
        d = datetime.strptime((testo or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ErroreRichiesta("Data non valida: usa il formato AAAA-MM-GG.")
    if d > date.today() + timedelta(days=1):
        raise ErroreRichiesta("La data della foto non può essere nel futuro.")
    if d.year < 1990:
        raise ErroreRichiesta("Data della foto troppo vecchia.")
    return d.isoformat()


def numero_o_vuoto(testo, minimo, massimo, nome):
    """Legge un numero decimale opzionale (virgola o punto) entro un intervallo; '' vale 'non indicato'."""
    if testo is None or str(testo).strip() == "":
        return None
    try:
        v = float(str(testo).replace(",", "."))
    except ValueError:
        raise ErroreRichiesta(f"{nome}: inserisci un numero.")
    if not (minimo <= v <= massimo):
        raise ErroreRichiesta(f"{nome}: il valore deve essere tra {minimo:g} e {massimo:g}.")
    return round(v, 1)


def salva_foto(nevo_id, dati, data, usa_exif, tipo, diametro, note):
    """
    Salva una foto nello storico del neo. L'originale viene conservato SENZA modifiche
    (è la 'foto storica'). Restituisce l'id della foto e la data effettivamente usata.
    """
    if not dati:
        raise ErroreRichiesta("Il file è vuoto.")
    if len(dati) > MAX_MB_FOTO * 1024 * 1024:
        raise ErroreRichiesta(f"La foto supera {MAX_MB_FOTO} MB.", 413)
    ext = riconosci_formato(dati)
    if ext is None:
        raise ErroreRichiesta("Formato non supportato: servono JPG, PNG, WEBP o BMP. "
                              "Le foto HEIC degli iPhone vanno convertite in JPG "
                              "(impostazioni fotocamera: 'Più compatibile').")
    if tipo not in ("normale", "dermoscopica"):
        tipo = "normale"
    data_exif_trovata = None
    if HA_PILLOW:
        try:
            Image.MAX_IMAGE_PIXELS = MAX_PIXEL_IMMAGINE
            with Image.open(io.BytesIO(dati)) as img:
                if img.width * img.height > MAX_PIXEL_IMMAGINE:        # immagine-trappola: enorme una volta aperta
                    raise ValueError("troppo grande")
                img.verify()
            with Image.open(io.BytesIO(dati)) as img:
                data_exif_trovata = data_exif(img)
        except Exception:
            raise ErroreRichiesta("Il file non è un'immagine leggibile, è danneggiato o ha troppi pixel "
                                  f"(massimo {MAX_PIXEL_IMMAGINE // 1_000_000} megapixel).")
    data_finale = data_exif_trovata if (usa_exif and data_exif_trovata) else data_valida(data or date.today().isoformat())
    diam = numero_o_vuoto(diametro, 0.5, 100, "Diametro (mm)")
    note = (note or "").strip()[:1000]

    with connetti() as con:
        nevo = con.execute("SELECT id, utente_id FROM nevi WHERE id=?", (nevo_id,)).fetchone()
        if nevo is None:
            raise ErroreRichiesta("Neo non trovato.", 404)
        sotto = Path(f"u{nevo['utente_id']}") / f"n{nevo_id}"
        nome_file = f"{data_finale.replace('-', '')}_{datetime.now().strftime('%H%M%S')}_{hashlib.sha1(dati, usedforsecurity=False).hexdigest()[:6]}{ext}"
        dest = cartella_foto() / sotto / nome_file
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(dati)
        cur = con.execute(
            "INSERT INTO foto (nevo_id, file, scattata_il, diametro_mm, tipo, note, creato) VALUES (?,?,?,?,?,?,?)",
            (nevo_id, (sotto / nome_file).as_posix(), data_finale, diam, tipo, note, adesso()))
        return {"id": cur.lastrowid, "scattata_il": data_finale, "da_exif": bool(usa_exif and data_exif_trovata)}


def percorso_foto(riga_foto):
    """Percorso completo del file originale di una foto (solo se sta dentro la cartella foto)."""
    p = cartella_foto() / riga_foto["file"]
    return p if dentro(cartella_foto(), p) and p.exists() else None


def miniatura(foto_id, utente_id, riga_foto, lato):
    """Miniatura JPEG della foto (ruotata correttamente, senza metadati). Restituisce (byte, tipo MIME)."""
    orig = percorso_foto(riga_foto)
    if orig is None:
        raise ErroreRichiesta("File della foto non trovato.", 404)
    if not HA_PILLOW:
        return orig.read_bytes(), (mimetypes.guess_type(str(orig))[0] or "application/octet-stream")
    lato = lato if lato in (120, 240, 480, 960, 1600) else 480
    cache = cartella_miniature() / f"u{utente_id}" / f"f{foto_id}_{lato}.jpg"
    if cache.exists() and cache.stat().st_mtime >= orig.stat().st_mtime:
        return cache.read_bytes(), "image/jpeg"
    Image.MAX_IMAGE_PIXELS = MAX_PIXEL_IMMAGINE
    with Image.open(orig) as img:
        try:
            img.draft("RGB", (lato * 2, lato * 2))      # per i JPEG: legge già in piccolo (molto più veloce)
        except Exception:
            pass
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        img.thumbnail((lato, lato))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=88, optimize=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(buf.getvalue())
    return buf.getvalue(), "image/jpeg"


def cancella_file_foto(riga_foto, utente_id):
    """Toglie dal disco la foto, le sue miniature e il suo rapporto."""
    p = cartella_foto() / riga_foto["file"]
    if dentro(cartella_foto(), p):
        p.unlink(missing_ok=True)
    mini = cartella_miniature() / f"u{utente_id}"
    if mini.exists():
        for f in mini.glob(f"f{riga_foto['id']}_*.jpg"):
            f.unlink(missing_ok=True)
    if riga_foto["rapporto"]:
        r = Path(CARTELLA_DATI) / riga_foto["rapporto"]
        if dentro(cartella_rapporti(), r) and r.exists():
            shutil.rmtree(r, ignore_errors=True)


def cancella_cartelle_utente(utente_id):
    for base in (cartella_foto(), cartella_rapporti(), cartella_miniature()):
        shutil.rmtree(base / f"u{utente_id}", ignore_errors=True)
    cancella_avatar(utente_id)


# ------------------------------------------------------------------------------------------
# 5a-bis. Immagine personale (avatar) dell'utente
# ------------------------------------------------------------------------------------------
# L'utente può scegliere una propria immagine (anche un'icona o un disegno, non per forza la sua
# faccia). Resta sul PC: si salva come piccolo JPEG quadrato 256x256 in CARTELLA_DATI\avatar.
# Non viene mai usata per l'analisi dei nei né inviata a servizi esterni.
LATO_AVATAR = 256
MAX_BYTE_AVATAR = 8 * 1024 * 1024          # l'immagine scelta può essere grande; poi viene ridotta


def percorso_avatar(utente_id):
    return cartella_avatar() / f"u{int(utente_id)}.jpg"


def versione_avatar(utente_id):
    """Un numero che cambia ogni volta che l'immagine cambia (serve al browser per non usare una copia vecchia). 0 = nessuna."""
    try:
        return int(percorso_avatar(utente_id).stat().st_mtime_ns // 1_000_000)
    except OSError:
        return 0


def salva_avatar(utente_id, dati):
    """Controlla l'immagine, la ritaglia al centro in un quadrato, la riduce e la salva come JPEG
    SENZA metadati (niente GPS o dati della fotocamera). Senza Pillow accetta solo un JPEG/PNG già piccolo."""
    if not dati:
        raise ErroreRichiesta("Il file è vuoto.")
    if len(dati) > MAX_BYTE_AVATAR:
        raise ErroreRichiesta(f"L'immagine supera {MAX_BYTE_AVATAR // (1024 * 1024)} MB.", 413)
    ext = riconosci_formato(dati)
    if ext not in (".jpg", ".png", ".webp", ".bmp"):
        raise ErroreRichiesta("Formato non supportato: servono JPG, PNG, WEBP o BMP.")
    if HA_PILLOW:
        try:
            Image.MAX_IMAGE_PIXELS = MAX_PIXEL_IMMAGINE
            with Image.open(io.BytesIO(dati)) as img:
                if img.width * img.height > MAX_PIXEL_IMMAGINE:
                    raise ValueError("troppo grande")
                try:
                    img.draft("RGB", (LATO_AVATAR * 2, LATO_AVATAR * 2))
                except Exception:
                    pass
                img = ImageOps.exif_transpose(img)
                if img.mode in ("RGBA", "LA", "P"):                     # sfondo bianco al posto della trasparenza
                    img = img.convert("RGBA")
                    fondo = Image.new("RGB", img.size, (255, 255, 255))
                    fondo.paste(img, mask=img.split()[-1])
                    img = fondo
                else:
                    img = img.convert("RGB")
                img = ImageOps.fit(img, (LATO_AVATAR, LATO_AVATAR), method=Image.LANCZOS)   # ritaglio centrale + riduzione
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=88, optimize=True)         # nuovo file: nessun metadato originale
            dati_finali = buf.getvalue()
        except ErroreRichiesta:
            raise
        except Exception:
            raise ErroreRichiesta("Il file non è un'immagine leggibile o è troppo grande.")
    else:
        if ext not in (".jpg", ".png") or len(dati) > 400 * 1024:
            raise ErroreRichiesta("Senza Pillow l'immagine deve essere un JPG/PNG sotto i 400 KB "
                                  "(la pagina la riduce da sola: riprova con la funzione 'Scegli immagine').")
        dati_finali = dati
    dest = percorso_avatar(utente_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_bytes(dati_finali)
    os.replace(tmp, dest)                                                # scrittura "atomica": niente file a metà
    return versione_avatar(utente_id)


def cancella_avatar(utente_id):
    try:
        percorso_avatar(utente_id).unlink(missing_ok=True)
    except OSError:
        pass


# ------------------------------------------------------------------------------------------
# 5b. Analisi automatica (usa melanoma_batch.py) - una alla volta, in coda
# ------------------------------------------------------------------------------------------
_coda_analisi = []                       # id delle foto in attesa
_blocco_coda = threading.Lock()
_thread_analisi = [None]
_processo_attuale = {"foto": None, "popen": None}
TIMEOUT_ANALISI_S = 3 * 3600             # tempo massimo per una foto (i modelli sono pesanti)


def analisi_attiva():
    """True se c'è almeno un'analisi in coda o in corso.

    Serve a NON spegnere il programma mentre sta ancora lavorando su una foto: l'analisi può
    durare minuti (i modelli sono pesanti) e chiudere la finestra non deve buttarla via.
    """
    with _blocco_coda:
        if _coda_analisi:
            return True
    t = _thread_analisi[0]
    return t is not None and t.is_alive()


def eseguibile_python():
    """Percorso del Python da usare per lanciare l'analisi.

    Se NeoTracker è stato avviato SENZA finestra nera (con "pythonw.exe", come fa l'icona sul
    Desktop), per l'analisi serve comunque "python.exe" (con pythonw i programmi non possono
    scrivere testo). Lo lanciamo poi con CREATE_NO_WINDOW, quindi non compare nessuna finestra.
    """
    exe = Path(sys.executable)
    if os.name == "nt" and exe.name.lower() == "pythonw.exe":
        candidato = exe.with_name("python.exe")
        if candidato.exists():
            return str(candidato)
    return str(exe)


def trova_batch():
    """Cerca melanoma_batch.py accanto a questo file o nella cartella dei progetti."""
    for c in (CARTELLA_SCRIPT / "melanoma_batch.py", Path(CARTELLA_REPO) / "melanoma_batch.py"):
        if c.exists():
            return c
    return None


def stato_installazione():
    """Che cosa è pronto sul PC (mostrato nelle Impostazioni, per capire subito cosa manca)."""
    repo = Path(CARTELLA_REPO)
    app1, vatsal = repo / "DeborahAdedigba_Melanoma-Detection_App", repo / "vatsal30_Melanoma-Detection"
    n_app1 = len(list(app1.glob("*.keras"))) + len(list(app1.glob("*.weights.h5"))) if app1.exists() else 0
    n_vat = len(list((vatsal / "model").glob("model_fold_*.bin"))) if vatsal.exists() else 0
    return {"batch": str(trova_batch()) if trova_batch() else "", "repo": str(repo),
            "progetti": [
                {"nome": "Metodo 1 - App 1 (Deborah Adedigba)", "presente": app1.exists(),
                 "dettaglio": f"{n_app1} file modello su 10"},
                {"nome": "Metodo 2 - SkinSense (servizio online)", "presente": True,
                 "dettaglio": "attivo solo se lo abiliti qui sotto"},
                {"nome": "Metodo 4 - vatsal30", "presente": vatsal.exists(),
                 "dettaglio": f"{n_vat} file modello su 5"},
            ]}


def _scrivi_stato(foto_id, **campi):
    with connetti() as con:
        imp = ", ".join(f"{k}=?" for k in campi)
        # Controllo di sicurezza (bandit B608): i nomi delle colonne sono scritti da noi, i valori passano come parametri.
        con.execute(f"UPDATE foto SET {imp} WHERE id=?", (*campi.values(), foto_id))   # nosec B608


def accoda_analisi(foto_id):
    """Mette la foto in coda per l'analisi (se non c'è già). Parte da sola in un thread."""
    with connetti() as con:
        r = con.execute("SELECT stato_analisi FROM foto WHERE id=?", (foto_id,)).fetchone()
        if r is None:
            raise ErroreRichiesta("Foto non trovata.", 404)
        if r["stato_analisi"] in ("in_coda", "in_corso"):
            return r["stato_analisi"]
        if trova_batch() is None:
            raise ErroreRichiesta("Non trovo melanoma_batch.py: deve stare nella stessa cartella di neotracker.py "
                                  f"(oppure in {CARTELLA_REPO}).", 409)
        con.execute("UPDATE foto SET stato_analisi='in_coda', messaggio='', esito='' WHERE id=?", (foto_id,))
    with _blocco_coda:
        _coda_analisi.append(foto_id)
        if _thread_analisi[0] is None or not _thread_analisi[0].is_alive():
            t = threading.Thread(target=_ciclo_analisi, name="analisi", daemon=True)
            _thread_analisi[0] = t
            t.start()
    return "in_coda"


def _ciclo_analisi():
    while True:
        with _blocco_coda:
            if not _coda_analisi:
                return
            foto_id = _coda_analisi.pop(0)
        try:
            _esegui_analisi(foto_id)
        except Exception as e:                       # qualunque imprevisto: segno errore e passo alla prossima
            traceback.print_exc()
            try:
                _scrivi_stato(foto_id, stato_analisi="errore", messaggio=f"Errore imprevisto: {e}")
            except Exception:
                pass


def _copia_per_analisi(origine, destinazione):
    """Copia pulita per i modelli: ruotata come nell'originale, senza metadati (GPS ecc.), RGB, JPEG."""
    if not HA_PILLOW:
        destinazione = destinazione.with_suffix(origine.suffix)
        shutil.copyfile(origine, destinazione)
        return destinazione
    Image.MAX_IMAGE_PIXELS = MAX_PIXEL_IMMAGINE
    with Image.open(origine) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        massimo = 4096
        if max(img.size) > massimo:
            img.thumbnail((massimo, massimo), Image.LANCZOS)
        destinazione = destinazione.with_suffix(".jpg")
        img.save(destinazione, "JPEG", quality=95)
    return destinazione


def _esegui_analisi(foto_id):
    with connetti() as con:
        r = con.execute("SELECT f.*, n.utente_id FROM foto f JOIN nevi n ON n.id=f.nevo_id WHERE f.id=?",
                        (foto_id,)).fetchone()
    if r is None:
        return                                       # foto cancellata mentre era in coda
    origine = percorso_foto(r)
    if origine is None:
        _scrivi_stato(foto_id, stato_analisi="errore", messaggio="File della foto non trovato.")
        return
    batch = trova_batch()
    rel = f"rapporti/u{r['utente_id']}/f{foto_id}_{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    cartella = Path(CARTELLA_DATI) / rel
    cartella.mkdir(parents=True, exist_ok=True)
    _scrivi_stato(foto_id, stato_analisi="in_corso", rapporto=rel, messaggio="")

    pulita = _copia_per_analisi(origine, cartella / "foto_analizzata")
    cmd = [eseguibile_python(), "-u", str(batch), "--foto", str(pulita), "--tipo", r["tipo"],
           "--repo", str(CARTELLA_REPO), "--out-dir", str(cartella)]
    if not leggi_impostazioni().get("usa_skinsense"):
        cmd.append("--senza-skinsense")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    flag = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    with open(cartella / "log_analisi.txt", "wb") as log:
        # stdin=DEVNULL: avviato senza finestra nera non esiste una "tastiera" da ereditare e
        # Windows darebbe l'errore "handle non valido"; così il processo figlio parte sempre.
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                             cwd=str(batch.parent), env=env, creationflags=flag)
        _processo_attuale.update(foto=foto_id, popen=p)
        try:
            p.wait(timeout=TIMEOUT_ANALISI_S)
        except subprocess.TimeoutExpired:
            p.kill()
            _processo_attuale.update(foto=None, popen=None)
            _scrivi_stato(foto_id, stato_analisi="errore",
                          messaggio=f"Analisi interrotta dopo {TIMEOUT_ANALISI_S // 3600} ore (troppo lunga).")
            return
        finally:
            _processo_attuale.update(foto=None, popen=None)

    sint = sintesi_rapporto(rel)
    if sint is None:
        coda_log = ultime_righe(cartella / "log_analisi.txt", 6)
        _scrivi_stato(foto_id, stato_analisi="errore",
                      messaggio="L'analisi non ha prodotto il rapporto. Ultime righe del log: " + (coda_log or "(vuoto)"))
        return
    _scrivi_stato(foto_id, stato_analisi="ok", esito=sint["esito"], messaggio="")


def ultime_righe(percorso, n):
    try:
        testo = Path(percorso).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    righe = [x.strip() for x in testo.splitlines() if x.strip()]
    return " | ".join(righe[-n:])


def avanzamento_log(rel):
    """Ultime righe del log di un'analisi in corso (per mostrare 'Metodo 2: avvio...')."""
    if not rel:
        return []
    f = Path(CARTELLA_DATI) / rel / "log_analisi.txt"
    if not dentro(cartella_rapporti(), f) or not f.exists():
        return []
    try:
        testo = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [x.strip() for x in testo.splitlines() if x.strip()][-4:]


def verdetto_metodo(risultati):
    """Stesso criterio di melanoma_batch.py: 'attenzione' | 'benigno' | 'discordante' | None."""
    v = [r.get("verdetto") for r in risultati if r.get("stato") == "ok" and r.get("verdetto") in ("attenzione", "benigno")]
    if not v:
        return None
    if all(x == "attenzione" for x in v):
        return "attenzione"
    if all(x == "benigno" for x in v):
        return "benigno"
    return "discordante"


def sintesi_rapporto(rel):
    """
    Legge rapporto.json e lo riduce a una sintesi per l'interfaccia:
    per ogni metodo: verdetto, conteggio ("4 su 5 dicono ...") e righe per modello.
    """
    if not rel:
        return None
    cartella = Path(CARTELLA_DATI) / rel
    if not dentro(cartella_rapporti(), cartella):
        return None
    try:
        dati = json.loads((cartella / "rapporto.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    metodi, giudizi = [], {}
    for m in dati:
        ris = m.get("risultati", [])
        ok = [x for x in ris if x.get("stato") == "ok"]
        conteggi = {}
        for x in ok:
            conteggi[x.get("etichetta")] = conteggi.get(x.get("etichetta"), 0) + 1
        frase = "; ".join(f"{n} su {len(ok)}: {et}" for et, n in sorted(conteggi.items(), key=lambda kv: -kv[1]))
        verd = verdetto_metodo(ris)
        giudizi[m.get("metodo")] = verd
        metodi.append({"numero": m.get("metodo"), "titolo": m.get("titolo"), "introduzione": m.get("introduzione", ""),
                       "verdetto": verd, "frase": frase,
                       "risultati": [{k: x.get(k) for k in ("nome", "gruppo", "stato", "etichetta", "valore",
                                                              "prob_mel", "verdetto", "nota")} for x in ris]})
    con_ris = [n for n, g in giudizi.items() if g is not None]
    attenzione = [n for n, g in giudizi.items() if g == "attenzione"]
    benigni = [n for n, g in giudizi.items() if g == "benigno"]
    discordi = [n for n, g in giudizi.items() if g == "discordante"]
    if not con_ris:
        esito = "nessuno"
    elif attenzione or discordi:
        esito = "attenzione" if attenzione and not benigni and not discordi else "discordante"
    else:
        esito = "benigno"
    try:
        testo = (cartella / "rapporto.txt").read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        testo = ""
    return {"metodi": metodi, "esito": esito, "con_risultato": con_ris, "attenzione": attenzione,
            "benigni": benigni, "discordi": discordi, "testo": testo}

# ==========================================================================================
# 5c. VITA DELLA FINESTRA: come il programma capisce che hai chiuso la finestra dell'app
# ==========================================================================================
# IDEA (spiegata semplice)
# ------------------------
# NeoTracker è composto da due parti che parlano tra loro:
#   - il "motore" (questo programma Python), che salva i dati e analizza le foto;
#   - la "finestra" (Edge o Chrome aperto in modalità app, cioè senza barra degli indirizzi
#     e senza schede), che mostra la pagina.
# Quando tu chiudi la finestra, il motore deve spegnersi da solo. Ma il motore non può
# "sentire" la chiusura direttamente: allora la pagina gli manda un piccolo segnale ("battito")
# ogni pochi secondi, come un cuore che batte. Se i battiti smettono, la finestra è chiusa.
#
#   - ogni pagina aperta ha un proprio numero (id) casuale e manda un "battito" ogni ~5 secondi;
#   - quando la pagina viene chiusa prova anche a mandare un "addio" (chiusura immediata);
#   - se per 6 secondi non c'è più NESSUNA pagina aperta, il motore si spegne (i 6 secondi
#     servono perché premendo F5 / "ricarica" la pagina sparisce e ricompare in un attimo:
#     non vogliamo spegnere tutto per un ricaricamento);
#   - se la finestra si blocca o il PC va in sospensione senza "addio", dopo 3 minuti di
#     silenzio la pagina è considerata chiusa;
#   - se il motore sta ANCORA analizzando una foto, aspetta la fine dell'analisi e poi si spegne
#     (così non perdi il lavoro); se nel frattempo riapri l'icona, la finestra torna.

GRAZIA_CHIUSURA_S = 6          # secondi senza pagine aperte prima di spegnere (copre il ricaricamento)
SILENZIO_MASSIMO_S = 180       # una pagina muta per 3 minuti è considerata chiusa (finestra bloccata)
FINESTRA_APERTA_S = 90         # entro quanti secondi dall'ultimo battito diciamo "la finestra è aperta"
ATTESA_PRIMA_FINESTRA_S = 600  # se nessuna finestra si apre entro 10 minuti dall'avvio, ci spegniamo


class StatoFinestra:
    """Tiene il conto delle pagine aperte e dice quando il programma deve spegnersi.

    Il tempo viene sempre passato dal chiamante (parametro `adesso`, in secondi): così nei test
    possiamo simulare minuti e ore in un istante, senza aspettare davvero.
    """

    def __init__(self, adesso=None):
        self._blocco = threading.Lock()                       # evita che due richieste modifichino insieme
        self.avviato = time.monotonic() if adesso is None else adesso
        self.pagine = {}                                      # id pagina -> istante dell'ultimo battito
        self.vista_almeno_una = False                         # è mai comparsa una finestra?
        self.vuoto_da = None                                  # da quando non ci sono più pagine (None = ce n'è almeno una)
        self.chiuse = {}                                      # pagine che hanno detto "addio": non possono più "riaprirsi"

    def azzera(self, adesso=None):
        """Riparte da capo (chiamata all'avvio del server): nessuna pagina, nessuna finestra mai vista."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            self.avviato, self.pagine, self.vista_almeno_una, self.vuoto_da = adesso, {}, False, None
            self.chiuse = {}

    # ---- segnali che arrivano dalla pagina ----
    def battito(self, id_pagina, adesso=None):
        """Una pagina dice "sono ancora qui"."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            if id_pagina in self.chiuse:
                return          # un battito in ritardo (arrivato dopo l'addio) non deve far "risuscitare" una pagina chiusa
            self.pagine[id_pagina] = adesso
            self.vista_almeno_una = True
            self.vuoto_da = None                              # c'è almeno una pagina: annulla l'eventuale spegnimento

    def addio(self, id_pagina, adesso=None, definitivo=False):
        """Una pagina non c'è più.
        definitivo=True: è la pagina stessa a dirci "mi sto chiudendo" -> da ora i suoi eventuali battiti
        in ritardo vengono ignorati. definitivo=False: lo deduciamo noi dalla connessione caduta (potrebbe
        essere solo un'interruzione momentanea: se la pagina ricompare con lo stesso numero, vale)."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            self.pagine.pop(id_pagina, None)
            if definitivo:
                self.chiuse[id_pagina] = adesso
                while len(self.chiuse) > 500:                 # non teniamo l'elenco all'infinito
                    del self.chiuse[next(iter(self.chiuse))]
            if not self.pagine and self.vuoto_da is None:
                self.vuoto_da = adesso                        # parte il conto alla rovescia dei 6 secondi

    # ---- domande che fa il programma ----
    def _togli_pagine_mute(self, adesso):
        """Dimentica le pagine che non battono da troppo tempo (finestra bloccata o chiusa a forza)."""
        mute = [i for i, t in self.pagine.items() if adesso - t > SILENZIO_MASSIMO_S]
        for i in mute:
            del self.pagine[i]
        if mute and not self.pagine and self.vuoto_da is None:
            self.vuoto_da = adesso

    def finestra_aperta(self, adesso=None):
        """True se c'è una pagina che ha battuto di recente (serve alla seconda apertura dell'icona)."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            return any(adesso - t <= FINESTRA_APERTA_S for t in self.pagine.values())

    def dopo_sospensione(self, adesso=None):
        """Il PC si è appena risvegliato: durante la sospensione nessuna pagina poteva battere,
        quindi facciamo finta che tutte abbiano battito adesso (altrimenti sembrerebbero chiuse)."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            for i in self.pagine:
                self.pagine[i] = adesso
            if self.vuoto_da is not None:
                self.vuoto_da = adesso
            self.avviato = max(self.avviato, adesso - 1)

    def da_spegnere(self, adesso=None, analisi_in_corso=False):
        """True quando il programma deve chiudersi. Chiamata ogni secondo dal "sorvegliante"."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            self._togli_pagine_mute(adesso)
            if self.pagine:
                return False                                  # c'è ancora almeno una finestra aperta
            if analisi_in_corso:
                return False                                  # non interrompere un'analisi: finirà e poi ci spegniamo
            if self.vista_almeno_una:
                return self.vuoto_da is not None and adesso - self.vuoto_da >= GRAZIA_CHIUSURA_S
            return adesso - self.avviato >= ATTESA_PRIMA_FINESTRA_S   # nessuna finestra è mai comparsa


STATO_FINESTRA = StatoFinestra()


# ==========================================================================================
# 6. SERVER LOCALE: il browser parla con questo programma tramite "indirizzi" (API)
# ==========================================================================================
# Non serve capire questa parte per usare l'app. In breve: la pagina web (HTML/JS) chiede
# dati a indirizzi come /api/utenti oppure /api/nevi/3, e qui sotto c'è la funzione che
# risponde a ciascun indirizzo.

WEB_FILES = {}       # riempito dalla parte "pagine web" incorporata dallo script di costruzione


# ------------------------------------------------------------------------------------------
# 6a. Profilo (fenotipo e familiarità): quali campi esistono e come si controllano
# ------------------------------------------------------------------------------------------
_SC = lambda *v: ("scelta", ("",) + v)
CAMPI_PROFILO = {
    "sesso": _SC("F", "M", "altro"),
    "data_nascita": ("data", None),
    "fototipo": ("intero", (0, 6)),
    "capelli": _SC("neri", "castani", "biondi", "rossi", "grigi"),
    "occhi": _SC("scuri", "verdi", "azzurri"),
    "efelidi": _SC("nessuna", "poche", "molte"),
    "n_nevi": _SC("<25", "25-49", "50-99", "100+"),
    "nevi_atipici": _SC("no", "si", "non so"),
    "scottature": _SC("mai", "poche", "molte"),
    "lampade": _SC("mai", "alcune", "spesso"),
    "lavoro_aperto": ("bool", None),
    "immunosoppressione": ("bool", None),
    "altri_tumori_cutanei": ("bool", None),
    "melanomi_personali": ("intero", (0, 20)),
    "fam_compilata": ("bool", None),
    "fam_melanoma_1grado": ("intero", (0, 20)),
    "fam_melanoma_altri": ("intero", (0, 20)),
    "fam_pancreas": ("intero", (0, 20)),
    "fam_pancreas_1grado": ("intero", (0, 20)),
    "fam_astrocitoma": ("intero", (0, 20)),
    "fam_uveale": ("intero", (0, 20)),
    "fam_mesotelioma": ("intero", (0, 20)),
    "fam_rene": ("intero", (0, 20)),
    "pers_pancreas": ("bool", None),
    "pers_astrocitoma": ("bool", None),
    "pers_uveale": ("bool", None),
    "pers_mesotelioma": ("bool", None),
    "pers_rene": ("bool", None),
    "test_genetico": _SC("no", "si_positivo", "si_negativo", "si_non_informativo"),
    "note": ("testo", 1000),
}


def pulisci_profilo(grezzo):
    """Tiene solo i campi previsti e li controlla uno per uno. Valori strani diventano 'vuoto'."""
    out = {}
    if not isinstance(grezzo, dict):
        raise ErroreRichiesta("Profilo non valido.")
    for campo, (tipo, regola) in CAMPI_PROFILO.items():
        if campo not in grezzo:
            continue
        v = grezzo[campo]
        if tipo == "scelta":
            out[campo] = v if v in regola else ""
        elif tipo == "bool":
            out[campo] = bool(v)
        elif tipo == "intero":
            out[campo] = min(max(a_intero(v, 0), regola[0]), regola[1])
        elif tipo == "data":
            v = (v or "").strip() if isinstance(v, str) else ""
            if v:
                try:
                    d = datetime.strptime(v, "%Y-%m-%d").date()
                except ValueError:
                    raise ErroreRichiesta("Data di nascita non valida (AAAA-MM-GG).")
                if not (date(1900, 1, 1) <= d <= date.today()):
                    raise ErroreRichiesta("Data di nascita fuori intervallo.")
            out[campo] = v
        elif tipo == "testo":
            out[campo] = (str(v) if v is not None else "").strip()[:regola]
    # coerenza: i parenti di primo grado fanno parte del totale dei parenti
    if "fam_pancreas" in out or "fam_pancreas_1grado" in out:
        a, b = out.get("fam_pancreas", grezzo.get("fam_pancreas", 0)), out.get("fam_pancreas_1grado", grezzo.get("fam_pancreas_1grado", 0))
        out["fam_pancreas"] = max(a_intero(a), a_intero(b))
    return out


def profilo_completo(testo_json):
    """Profilo salvato + valori vuoti per i campi mai compilati (così il browser trova sempre tutto)."""
    try:
        salvato = json.loads(testo_json or "{}")
    except ValueError:
        salvato = {}
    base = {}
    for campo, (tipo, regola) in CAMPI_PROFILO.items():
        base[campo] = False if tipo == "bool" else (0 if tipo == "intero" else "")
    base.update({k: v for k, v in salvato.items() if k in base})
    return base


def nome_valido(testo, minimo=1, massimo=60, cosa="Il nome"):
    t = re.sub(r"\s+", " ", (testo or "")).strip()
    if len(t) < minimo:
        raise ErroreRichiesta(f"{cosa} non può essere vuoto.")
    if len(t) > massimo:
        raise ErroreRichiesta(f"{cosa} è troppo lungo (massimo {massimo} caratteri).")
    return t


# ------------------------------------------------------------------------------------------
# 6b. Funzioni che rispondono ai vari indirizzi
# ------------------------------------------------------------------------------------------
class Richiesta:
    """Tutto ciò che serve a una funzione per rispondere: indirizzo, parametri, corpo."""
    def __init__(self, gestore, metodo, percorso, query, gruppi):
        self.gestore, self.metodo, self.percorso, self.query, self.gruppi = gestore, metodo, percorso, query, gruppi
        self._corpo = None

    def q(self, nome, predefinito=""):
        return (self.query.get(nome) or [predefinito])[0]

    def corpo(self, massimo=2 * 1024 * 1024):
        if self._corpo is None:
            lung = a_intero(self.gestore.headers.get("Content-Length"), 0)
            if lung > massimo:
                raise ErroreRichiesta("Richiesta troppo grande.", 413)
            self._corpo = self.gestore.rfile.read(lung) if lung > 0 else b""
        return self._corpo

    def json(self):
        try:
            d = json.loads(self.corpo().decode("utf-8") or "{}")
        except ValueError:
            raise ErroreRichiesta("Dati non validi (JSON).")
        if not isinstance(d, dict):
            raise ErroreRichiesta("Dati non validi.")
        return d


class RispostaFile:
    def __init__(self, dati, mime, extra=None):
        self.dati, self.mime, self.extra = dati, mime, extra or {}


def get_utente(con, uid):
    r = con.execute("SELECT * FROM utenti WHERE id=?", (uid,)).fetchone()
    if r is None:
        raise ErroreRichiesta("Utente non trovato.", 404)
    return r


def get_nevo(con, nid):
    r = con.execute("SELECT * FROM nevi WHERE id=?", (nid,)).fetchone()
    if r is None:
        raise ErroreRichiesta("Neo non trovato.", 404)
    return r


def get_foto(con, fid):
    r = con.execute("SELECT f.*, n.utente_id FROM foto f JOIN nevi n ON n.id=f.nevo_id WHERE f.id=?", (fid,)).fetchone()
    if r is None:
        raise ErroreRichiesta("Foto non trovata.", 404)
    return r


# ---- generale ----------------------------------------------------------------------------
def api_ping(rq):
    # "finestra_aperta" serve a chi riapre l'icona mentre l'app gira già: se una finestra c'è,
    # la portiamo in primo piano invece di aprirne una seconda.
    return {"app": "NeoTracker", "versione": VERSIONE, "finestra_aperta": STATO_FINESTRA.finestra_aperta(),
            "protetto": True}


def _id_pagina(rq):
    """Legge e controlla il numero casuale che identifica la pagina aperta (solo lettere/cifre/trattini)."""
    i = str(rq.json().get("id", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", i):
        raise ErroreRichiesta("Identificativo di pagina non valido.")
    return i


def api_battito(rq):
    """La pagina aperta dice "sono ancora qui" (vedi 5c: vita della finestra)."""
    STATO_FINESTRA.battito(_id_pagina(rq))
    return {"ok": True}


def api_addio(rq):
    """La pagina si sta chiudendo: se era l'ultima, tra pochi secondi il programma si spegne."""
    STATO_FINESTRA.addio(_id_pagina(rq), definitivo=True)
    return {"ok": True}


def pillow_obsoleto():
    """True se Pillow è più vecchio della versione minima consigliata (10.3.0: contiene le correzioni di sicurezza
    sull'apertura delle immagini). NeoTracker apre file scelti da te: tenere Pillow aggiornato conta."""
    try:
        import PIL
        parti = [int(x) for x in re.findall(r"\d+", PIL.__version__)[:2]]
        return parti < [10, 3]
    except Exception:
        return False


def api_stato(rq):
    return dict(stato_installazione(), versione=VERSIONE, ha_pillow=HA_PILLOW, cartella_dati=str(CARTELLA_DATI),
                avvertenze_versione=AVVERTENZE_VERSIONE, max_mb_foto=MAX_MB_FOTO, pillow_obsoleto=pillow_obsoleto())


def api_chiudi(rq):
    rq.gestore.server.chiusura_richiesta = True
    threading.Thread(target=rq.gestore.server.shutdown, daemon=True).start()
    return {"ok": True}


# ---- utenti ------------------------------------------------------------------------------
def api_utenti_lista(rq):
    with connetti() as con:
        righe = con.execute("""SELECT u.id, u.nome, u.creato, u.profilo,
                                      (SELECT COUNT(*) FROM nevi n WHERE n.utente_id=u.id AND n.archiviato=0) AS n_nevi
                               FROM utenti u ORDER BY u.nome COLLATE NOCASE""").fetchall()
    out = []
    for r in righe:
        p = profilo_completo(r["profilo"])
        out.append({"id": r["id"], "nome": r["nome"], "creato": r["creato"], "n_nevi": r["n_nevi"],
                    "eta": eta_da_nascita(p.get("data_nascita")), "avatar_v": versione_avatar(r["id"])})
    return out


def api_utente_crea(rq):
    nome = nome_valido(rq.json().get("nome"))
    with connetti() as con:
        if con.execute("SELECT 1 FROM utenti WHERE nome=? COLLATE NOCASE", (nome,)).fetchone():
            raise ErroreRichiesta("Esiste già un utente con questo nome.", 409)
        cur = con.execute("INSERT INTO utenti (nome, creato) VALUES (?,?)", (nome, adesso()))
        return {"id": cur.lastrowid, "nome": nome}


def api_utente_dettaglio(rq):
    with connetti() as con:
        u = get_utente(con, int(rq.gruppi[0]))
        regioni = [r["regione"] for r in con.execute("SELECT regione FROM nevi WHERE utente_id=? AND archiviato=0", (u["id"],))]
    p = profilo_completo(u["profilo"])
    return {"id": u["id"], "nome": u["nome"], "profilo": p, "eta": eta_da_nascita(p.get("data_nascita")),
            "rischio": fattori_rischio(p), "genetica": valuta_genetica(p), "regioni": regioni,
            "avatar_v": versione_avatar(u["id"])}


def api_utente_rinomina(rq):
    nome = nome_valido(rq.json().get("nome"))
    with connetti() as con:
        u = get_utente(con, int(rq.gruppi[0]))
        if con.execute("SELECT 1 FROM utenti WHERE nome=? COLLATE NOCASE AND id<>?", (nome, u["id"])).fetchone():
            raise ErroreRichiesta("Esiste già un utente con questo nome.", 409)
        con.execute("UPDATE utenti SET nome=? WHERE id=?", (nome, u["id"]))
    return {"ok": True, "nome": nome}


def api_utente_elimina(rq):
    uid = int(rq.gruppi[0])
    with connetti() as con:
        u = get_utente(con, uid)
        if rq.json().get("conferma") != u["nome"]:
            raise ErroreRichiesta("Per eliminare scrivi il nome esatto dell'utente nella conferma.")
        con.execute("DELETE FROM utenti WHERE id=?", (uid,))
    cancella_cartelle_utente(uid)
    return {"ok": True}


# ---- immagine personale dell'utente (avatar) ---------------------------------------------
def api_avatar_leggi(rq):
    uid = int(rq.gruppi[0])
    with connetti() as con:
        get_utente(con, uid)
    p = percorso_avatar(uid)
    if not p.exists():
        raise ErroreRichiesta("Nessuna immagine impostata.", 404)
    return RispostaFile(p.read_bytes(), "image/jpeg",
                        {"Cache-Control": "private, max-age=86400", "Cross-Origin-Resource-Policy": "same-origin"})


def api_avatar_salva(rq):
    uid = int(rq.gruppi[0])
    with connetti() as con:
        get_utente(con, uid)
    return {"ok": True, "avatar_v": salva_avatar(uid, rq.corpo(MAX_BYTE_AVATAR + 1024))}


def api_avatar_elimina(rq):
    uid = int(rq.gruppi[0])
    with connetti() as con:
        get_utente(con, uid)
    cancella_avatar(uid)
    return {"ok": True, "avatar_v": 0}


def api_profilo_salva(rq):
    uid = int(rq.gruppi[0])
    nuovo = pulisci_profilo(rq.json())
    with connetti() as con:
        u = get_utente(con, uid)
        p = profilo_completo(u["profilo"])
        p.update(nuovo)
        con.execute("UPDATE utenti SET profilo=? WHERE id=?", (json.dumps(p, ensure_ascii=False), uid))
    return api_utente_dettaglio(Richiesta(rq.gestore, "GET", rq.percorso, {}, (str(uid),)))


# ---- nei ---------------------------------------------------------------------------------
def _nevo_a_dict(r):
    return {k: r[k] for k in r.keys()}


def api_nevi_lista(rq):
    uid = int(rq.gruppi[0])
    with connetti() as con:
        get_utente(con, uid)
        righe = con.execute("""
            SELECT n.*,
                   (SELECT COUNT(*) FROM foto f WHERE f.nevo_id=n.id) AS n_foto,
                   (SELECT f.id FROM foto f WHERE f.nevo_id=n.id ORDER BY f.scattata_il DESC, f.id DESC LIMIT 1) AS ultima_foto_id,
                   (SELECT f.scattata_il FROM foto f WHERE f.nevo_id=n.id ORDER BY f.scattata_il DESC, f.id DESC LIMIT 1) AS ultima_data,
                   (SELECT f.esito FROM foto f WHERE f.nevo_id=n.id ORDER BY f.scattata_il DESC, f.id DESC LIMIT 1) AS ultimo_esito
            FROM nevi n WHERE n.utente_id=? ORDER BY n.archiviato, n.id""", (uid,)).fetchall()
    oggi = date.today()
    out = []
    for r in righe:
        d = _nevo_a_dict(r)
        d["giorni_da_ultima"] = (oggi - date.fromisoformat(r["ultima_data"])).days if r["ultima_data"] else None
        out.append(d)
    return out


def _controlla_posizione(d, parziale=False):
    out = {}
    if "vista" in d or not parziale:
        if d.get("vista") not in ("fronte", "retro"):
            raise ErroreRichiesta("La vista deve essere 'fronte' o 'retro'.")
        out["vista"] = d["vista"]
    for c in ("x", "y"):
        if c in d or not parziale:
            try:
                v = float(d.get(c))
            except (TypeError, ValueError):
                raise ErroreRichiesta("Posizione non valida.")
            if not (0.0 <= v <= 1.0):
                raise ErroreRichiesta("Posizione fuori dalla mappa.")
            out[c] = round(v, 5)
    return out


def api_nevo_crea(rq):
    uid = int(rq.gruppi[0])
    d = rq.json()
    pos = _controlla_posizione(d)
    regione = (d.get("regione") or "").strip()[:80]
    note = (d.get("note") or "").strip()[:1000]
    with connetti() as con:
        get_utente(con, uid)
        n = con.execute("SELECT COUNT(*) FROM nevi WHERE utente_id=?", (uid,)).fetchone()[0]
        nome = nome_valido(d.get("nome") or f"Neo {n + 1}")
        cur = con.execute("INSERT INTO nevi (utente_id, nome, vista, x, y, regione, note, creato) VALUES (?,?,?,?,?,?,?,?)",
                          (uid, nome, pos["vista"], pos["x"], pos["y"], regione, note, adesso()))
        return {"id": cur.lastrowid}


def api_nevo_dettaglio(rq):
    nid = int(rq.gruppi[0])
    with connetti() as con:
        n = get_nevo(con, nid)
        foto = con.execute("SELECT * FROM foto WHERE nevo_id=? ORDER BY scattata_il, id", (nid,)).fetchall()
    return {"nevo": _nevo_a_dict(n), "foto": [_nevo_a_dict(f) for f in foto]}


def api_nevo_modifica(rq):
    nid = int(rq.gruppi[0])
    d = rq.json()
    campi = {}
    if any(k in d for k in ("vista", "x", "y")):
        with connetti() as con:
            attuale = get_nevo(con, nid)
        unito = {"vista": attuale["vista"], "x": attuale["x"], "y": attuale["y"]}
        unito.update({k: d[k] for k in ("vista", "x", "y") if k in d})
        campi.update(_controlla_posizione(unito))
    if "nome" in d:
        campi["nome"] = nome_valido(d["nome"])
    if "regione" in d:
        campi["regione"] = (d["regione"] or "").strip()[:80]
    if "note" in d:
        campi["note"] = (d["note"] or "").strip()[:1000]
    if "archiviato" in d:
        campi["archiviato"] = 1 if d["archiviato"] else 0
    if not campi:
        return {"ok": True}
    with connetti() as con:
        get_nevo(con, nid)
        # Controllo di sicurezza (bandit B608): i nomi delle colonne sono scritti da noi, i valori passano come parametri.
        con.execute(f"UPDATE nevi SET {', '.join(k + '=?' for k in campi)} WHERE id=?", (*campi.values(), nid))   # nosec B608
    return {"ok": True}


def api_nevo_elimina(rq):
    nid = int(rq.gruppi[0])
    with connetti() as con:
        n = get_nevo(con, nid)
        for f in con.execute("SELECT * FROM foto WHERE nevo_id=?", (nid,)).fetchall():
            cancella_file_foto(f, n["utente_id"])
        con.execute("DELETE FROM nevi WHERE id=?", (nid,))
    return {"ok": True}


# ---- foto --------------------------------------------------------------------------------
def api_foto_carica(rq):
    nid = int(rq.gruppi[0])
    dati = rq.corpo(MAX_MB_FOTO * 1024 * 1024 + 1024)
    ris = salva_foto(nid, dati, rq.q("data"), rq.q("exif") == "1", rq.q("tipo", "normale"),
                     rq.q("diametro"), rq.q("note"))
    if rq.q("analizza") == "1":
        try:
            accoda_analisi(ris["id"])
            ris["analisi"] = "in_coda"
        except ErroreRichiesta as e:
            ris["analisi_errore"] = str(e)
    return ris


def api_foto_modifica(rq):
    fid = int(rq.gruppi[0])
    d = rq.json()
    campi = {}
    if "scattata_il" in d:
        campi["scattata_il"] = data_valida(d["scattata_il"])
    if "diametro_mm" in d:
        campi["diametro_mm"] = numero_o_vuoto(d["diametro_mm"], 0.5, 100, "Diametro (mm)")
    if "tipo" in d and d["tipo"] in ("normale", "dermoscopica"):
        campi["tipo"] = d["tipo"]
    if "note" in d:
        campi["note"] = (d["note"] or "").strip()[:1000]
    with connetti() as con:
        get_foto(con, fid)
        if campi:
            # Controllo di sicurezza (bandit B608): i nomi delle colonne sono scritti da noi, i valori passano come parametri.
            con.execute(f"UPDATE foto SET {', '.join(k + '=?' for k in campi)} WHERE id=?", (*campi.values(), fid))   # nosec B608
    return {"ok": True}


def api_foto_elimina(rq):
    fid = int(rq.gruppi[0])
    with connetti() as con:
        f = get_foto(con, fid)
        if f["stato_analisi"] in ("in_corso", "in_coda"):
            raise ErroreRichiesta("L'analisi di questa foto è in corso: attendi che finisca.", 409)
        cancella_file_foto(f, f["utente_id"])
        con.execute("DELETE FROM foto WHERE id=?", (fid,))
    return {"ok": True}


def api_foto_file(rq):
    fid = int(rq.gruppi[0])
    with connetti() as con:
        f = get_foto(con, fid)
    extra = {"Cache-Control": "private, max-age=3600", "Cross-Origin-Resource-Policy": "same-origin"}
    if rq.gruppi[1] == "mini":
        dati, mime = miniatura(fid, f["utente_id"], f, a_intero(rq.q("l"), 480))
    else:
        p = percorso_foto(f)
        if p is None:
            raise ErroreRichiesta("File della foto non trovato.", 404)
        if p.suffix.lower() in (".tif", ".tiff"):                       # i browser non mostrano i TIFF
            dati, mime = miniatura(fid, f["utente_id"], f, 1600)
        else:
            dati, mime = p.read_bytes(), (mimetypes.guess_type(str(p))[0] or "application/octet-stream")
        extra["Content-Disposition"] = f'inline; filename="{p.name}"'
    return RispostaFile(dati, mime, extra)


def api_analisi_avvia(rq):
    fid = int(rq.gruppi[0])
    with connetti() as con:
        get_foto(con, fid)
    return {"stato": accoda_analisi(fid)}


def api_analisi_stato(rq):
    fid = int(rq.gruppi[0])
    with connetti() as con:
        f = get_foto(con, fid)
    out = {"stato": f["stato_analisi"], "messaggio": f["messaggio"], "esito": f["esito"],
           "skinsense_attivo": bool(leggi_impostazioni().get("usa_skinsense"))}
    if f["stato_analisi"] in ("in_corso", "in_coda"):
        out["avanzamento"] = avanzamento_log(f["rapporto"])
        out["posizione_coda"] = (_coda_analisi.index(fid) + 1) if fid in _coda_analisi else 0
    if f["stato_analisi"] == "ok":
        out["sintesi"] = sintesi_rapporto(f["rapporto"])
    return out


# ---- indice UV, posizione, impostazioni ----------------------------------------------------
def _coordinate(rq):
    imp = leggi_impostazioni()
    try:
        lat = float(rq.q("lat") or imp.get("lat"))
        lon = float(rq.q("lon") or imp.get("lon"))
    except (TypeError, ValueError):
        raise ErroreRichiesta("Posizione non impostata: scegli una città o usa 'Rileva la mia posizione'.")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ErroreRichiesta("Coordinate non valide.")
    return lat, lon


def api_uv(rq):
    lat, lon = _coordinate(rq)
    return indice_uv(lat, lon, rq.q("fototipo"), rq.q("localita") or leggi_impostazioni().get("localita", ""))


def api_localita(rq):
    return cerca_localita(rq.q("q"))


def api_posizione_ip(rq):
    return posizione_da_ip()


def api_impostazioni_leggi(rq):
    return impostazioni_pubbliche()


def api_impostazioni_salva(rq):
    d = rq.json()
    nuove = {}
    if "openweather_key" in d and d["openweather_key"] is not None:
        k = str(d["openweather_key"]).strip()
        if k and not re.fullmatch(r"[A-Za-z0-9]{8,64}", k):
            raise ErroreRichiesta("La chiave OpenWeather contiene caratteri non validi (di solito sono 32 lettere/numeri).")
        nuove["openweather_key"] = k
    if "fonte_uv" in d:
        if d["fonte_uv"] not in ("open-meteo", "openweather"):
            raise ErroreRichiesta("Fonte dell'indice UV non valida.")
        nuove["fonte_uv"] = d["fonte_uv"]
    if "usa_skinsense" in d:
        nuove["usa_skinsense"] = bool(d["usa_skinsense"])
    if "avvertenze_accettate" in d:
        if d["avvertenze_accettate"] not in ("", AVVERTENZE_VERSIONE):
            raise ErroreRichiesta("Versione dell'avviso non valida.")
        nuove["avvertenze_accettate"] = d["avvertenze_accettate"]
    for c in ("lat", "lon"):
        if c in d:
            try:
                nuove[c] = None if d[c] in (None, "") else round(float(d[c]), 2)       # ~1 km: all'indice UV basta e si invia meno
            except (TypeError, ValueError):
                raise ErroreRichiesta("Coordinate non valide.")
    if "localita" in d:
        nuove["localita"] = str(d["localita"] or "").strip()[:120]
    if "ncbi_email" in d:
        e = str(d["ncbi_email"] or "").strip()[:120]
        if e and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e):
            raise ErroreRichiesta("Email non valida.")
        nuove["ncbi_email"] = e
    salva_impostazioni(nuove)
    _cache_uv.clear()
    return impostazioni_pubbliche()


def api_prova_owm(rq):
    imp = leggi_impostazioni()
    chiave = (imp.get("openweather_key") or "").strip()
    if not chiave:
        raise ErroreRichiesta("Prima salva una chiave OpenWeather.")
    lat, lon = imp.get("lat"), imp.get("lon")
    if lat is None or lon is None:
        lat, lon = 45.07, 7.69                       # in mancanza d'altro provo con Torino
    try:
        d = _uv_openweather(float(lat), float(lon), chiave)
    except ErroreServizio as e:
        return {"ok": False, "messaggio": str(e)}
    return {"ok": True, "messaggio": f"Funziona: OpenWeather risponde (indice UV ora: {d['uvi_ora']})."}


# ---- letteratura e genetica ----------------------------------------------------------------
def _sezioni_per_utente(uid):
    """Elenco completo delle sezioni di letteratura, con identificativi stabili."""
    out = {}
    for tema, info in TEMI_LETTERATURA.items():
        for i, (titolo, termine, ordina) in enumerate(info["sezioni"]):
            out[f"{tema}:{i}"] = {"tema": tema, "titolo": titolo, "termine": termine, "ordina": ordina}
    if uid:
        with connetti() as con:
            u = get_utente(con, uid)
            regioni = [r["regione"] for r in con.execute("SELECT regione FROM nevi WHERE utente_id=? AND archiviato=0", (uid,))]
        for i, (titolo, termine, ordina) in enumerate(temi_personalizzati(profilo_completo(u["profilo"]), regioni)):
            out[f"personale:{i}"] = {"tema": "personale", "titolo": titolo, "termine": termine, "ordina": ordina}
    return out


def api_lett_temi(rq):
    uid = a_intero(rq.q("utente"), 0)
    sezioni = _sezioni_per_utente(uid)
    temi = []
    ordine = list(TEMI_LETTERATURA.keys()) + ["personale"]
    titoli = {t: i["titolo"] for t, i in TEMI_LETTERATURA.items()}
    titoli["personale"] = "Scelti per te (in base a profilo e sede dei nei)"
    for t in ordine:
        elenco = [{"id": k, "titolo": v["titolo"]} for k, v in sezioni.items() if v["tema"] == t]
        if elenco:
            temi.append({"tema": t, "titolo": titoli[t], "sezioni": elenco})
    return temi


def api_lett_sezione(rq):
    sezioni = _sezioni_per_utente(a_intero(rq.q("utente"), 0))
    s = sezioni.get(rq.q("id"))
    if s is None:
        raise ErroreRichiesta("Sezione sconosciuta.", 404)
    dati = pubmed_cerca(s["termine"], 5, s["ordina"], rq.q("forza") == "1")
    return dict(dati, titolo=s["titolo"], id=rq.q("id"))


def api_lett_cerca(rq):
    q = re.sub(r"[^\w\s\-\*\"'\.]", " ", rq.q("q"), flags=re.UNICODE).strip()[:200]
    if len(q) < 3:
        raise ErroreRichiesta("Scrivi almeno 3 caratteri.")
    dati = pubmed_cerca(f"({q}) AND melanoma[tiab]", 8, "relevance", rq.q("forza") == "1")
    return dict(dati, titolo=f"Risultati per: {q}")


def api_genetica_geni(rq):
    return {"geni": [{k: g[k] for k in ("gene", "rischio", "ruolo")} for g in GENI_MELANOMA], "fonti": FONTI_GENETICA}


def api_genetica_gene(rq):
    g = next((x for x in GENI_MELANOMA if x["gene"] == rq.q("nome")), None)
    if g is None:
        raise ErroreRichiesta("Gene non presente nell'elenco.", 404)
    dati = pubmed_cerca(g["termine"], 3, "relevance", rq.q("forza") == "1")
    return dict(dati, gene=g["gene"])


# ------------------------------------------------------------------------------------------
# 6c. Tabella degli indirizzi (metodo, forma dell'indirizzo, funzione)
# ------------------------------------------------------------------------------------------
ROTTE = [
    ("GET",    r"/api/ping", api_ping),
    ("GET",    r"/api/stato", api_stato),
    ("POST",   r"/api/chiudi", api_chiudi),
    ("POST",   r"/api/battito", api_battito),
    ("POST",   r"/api/addio", api_addio),
    ("GET",    r"/api/utenti", api_utenti_lista),
    ("POST",   r"/api/utenti", api_utente_crea),
    ("GET",    r"/api/utenti/(\d+)", api_utente_dettaglio),
    ("PATCH",  r"/api/utenti/(\d+)", api_utente_rinomina),
    ("DELETE", r"/api/utenti/(\d+)", api_utente_elimina),
    ("PUT",    r"/api/utenti/(\d+)/profilo", api_profilo_salva),
    ("GET",    r"/api/utenti/(\d+)/avatar", api_avatar_leggi),
    ("POST",   r"/api/utenti/(\d+)/avatar", api_avatar_salva),
    ("DELETE", r"/api/utenti/(\d+)/avatar", api_avatar_elimina),
    ("GET",    r"/api/utenti/(\d+)/nevi", api_nevi_lista),
    ("POST",   r"/api/utenti/(\d+)/nevi", api_nevo_crea),
    ("GET",    r"/api/nevi/(\d+)", api_nevo_dettaglio),
    ("PATCH",  r"/api/nevi/(\d+)", api_nevo_modifica),
    ("DELETE", r"/api/nevi/(\d+)", api_nevo_elimina),
    ("POST",   r"/api/nevi/(\d+)/foto", api_foto_carica),
    ("PATCH",  r"/api/foto/(\d+)", api_foto_modifica),
    ("DELETE", r"/api/foto/(\d+)", api_foto_elimina),
    ("GET",    r"/foto/(\d+)/(mini|originale)", api_foto_file),
    ("POST",   r"/api/foto/(\d+)/analizza", api_analisi_avvia),
    ("GET",    r"/api/foto/(\d+)/analisi", api_analisi_stato),
    ("GET",    r"/api/uv", api_uv),
    ("GET",    r"/api/localita", api_localita),
    ("GET",    r"/api/posizione-ip", api_posizione_ip),
    ("GET",    r"/api/impostazioni", api_impostazioni_leggi),
    ("PUT",    r"/api/impostazioni", api_impostazioni_salva),
    ("POST",   r"/api/impostazioni/prova-owm", api_prova_owm),
    ("GET",    r"/api/letteratura/temi", api_lett_temi),
    ("GET",    r"/api/letteratura/sezione", api_lett_sezione),
    ("GET",    r"/api/letteratura/cerca", api_lett_cerca),
    ("GET",    r"/api/genetica/geni", api_genetica_geni),
    ("GET",    r"/api/genetica/gene", api_genetica_gene),
]
ROTTE = [(m, re.compile(p + r"\Z"), f) for m, p, f in ROTTE]

CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
       "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
# Per le immagini (foto, avatar): nemmeno se per assurdo contenessero codice potrebbero eseguirlo.
CSP_FILE = "default-src 'none'; sandbox"

# ------------------------------------------------------------------------------------------
# 6c-bis. Chi può parlare con il programma: la "chiave di sessione"
# ------------------------------------------------------------------------------------------
# Il server ascolta solo su 127.0.0.1, ma sul tuo PC potrebbero girare altri programmi, oppure una
# pagina web aperta nel tuo browser potrebbe provare a "bussare" a localhost. Per questo ogni volta
# che NeoTracker parte inventa una chiave casuale, lunga e impossibile da indovinare. La finestra
# dell'app la riceve una sola volta, all'apertura (indirizzo ...?avvio=CHIAVE), e la conserva in un
# "cookie" riservato (HttpOnly: nemmeno il JavaScript della pagina può leggerlo; SameSite=Strict:
# i siti esterni non possono usarlo). Senza la chiave ogni richiesta viene rifiutata.
# La chiave cambia a ogni avvio e viene scritta (con permessi riservati) nella cartella dei dati,
# solo perché una seconda icona cliccata possa aprire una finestra sul programma già acceso.
NOME_COOKIE = "nt_sessione"
TOKEN_SESSIONE = secrets.token_urlsafe(32)
PERCORSI_LIBERI = ("/api/ping",)           # unico indirizzo senza chiave: serve a capire se NeoTracker è già acceso
MAX_PRESENZE = 16                          # collegamenti "finestra aperta" contemporanei (una persona ne usa 1 o 2)
_presenze_aperte = [0]
_blocco_presenze = threading.Lock()


def percorso_token():
    return Path(CARTELLA_DATI) / "sessione.token"


def scrivi_token_su_file():
    """Salva la chiave in un file leggibile solo da te (su Windows eredita i permessi della tua cartella utente)."""
    f = percorso_token()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(TOKEN_SESSIONE, encoding="ascii")
    if os.name != "nt":
        os.chmod(tmp, 0o600)
    os.replace(tmp, f)


def leggi_token_da_file():
    """Chiave del NeoTracker già acceso (la legge una seconda icona cliccata). Stringa vuota se non c'è."""
    try:
        t = percorso_token().read_text(encoding="ascii").strip()
    except (OSError, ValueError):
        return ""
    return t if re.fullmatch(r"[A-Za-z0-9_-]{20,100}", t) else ""


def cancella_token_file():
    try:
        percorso_token().unlink(missing_ok=True)
    except OSError:
        pass


def chiave_uguale(a, b):
    """Confronto a tempo costante (non rivela, dai tempi di risposta, quante lettere erano giuste)."""
    return hmac.compare_digest(str(a).encode("utf-8", "replace"), str(b).encode("utf-8", "replace"))


PAGINA_ACCESSO_NEGATO = (
    "<!doctype html><html lang='it'><meta charset='utf-8'><title>Accesso non autorizzato</title>"
    "<body style='font-family:Segoe UI,Arial,sans-serif;max-width:34em;margin:4em auto;padding:0 1em;color:#222'>"
    "<h1>Accesso non autorizzato</h1>"
    "<p>Questa pagina funziona solo dalla finestra di NeoTracker. Chiudi questa scheda e apri l'app "
    "dall'icona <b>NeoTracker</b> sul Desktop.</p></body></html>").encode("utf-8")

# Intestazioni di sicurezza aggiunte a OGNI risposta.
INTESTAZIONI_SICUREZZA = {
    "X-Content-Type-Options": "nosniff",                  # il browser non deve "indovinare" il tipo di file
    "Cache-Control": "no-store",                          # niente copie dei dati personali nella cache del browser
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",                            # la pagina non può essere incorporata in altre pagine
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), payment=(), usb=(), geolocation=(self)",
}


class Gestore(BaseHTTPRequestHandler):
    server_version = "NeoTracker"
    sys_version = ""                  # non dire quale versione di Python c'è sotto
    timeout = 60                      # un collegamento che resta muto per un minuto viene chiuso (difesa da collegamenti "appesi")

    def log_message(self, formato, *args):            # niente rumore nella finestra nera
        pass

    # ---- controlli di sicurezza comuni ----
    def _host_ok(self):
        ammessi = {f"127.0.0.1:{PORTA}", f"localhost:{PORTA}"}
        return self.headers.get("Host", "") in ammessi

    def _origine_ok(self):
        o = self.headers.get("Origin")
        return o is None or o in (f"http://127.0.0.1:{PORTA}", f"http://localhost:{PORTA}")

    def _cookie_ok(self):
        """True se la richiesta porta la chiave di sessione giusta nel cookie."""
        for riga in self.headers.get_all("Cookie") or []:
            for parte in riga.split(";"):
                nome, _, valore = parte.strip().partition("=")
                if nome == NOME_COOKIE and chiave_uguale(valore, TOKEN_SESSIONE):
                    return True
        return False

    def _invia(self, codice, dati, mime, extra=None):
        intestazioni = dict(INTESTAZIONI_SICUREZZA)
        intestazioni.update(extra or {})                 # chi risponde può cambiare un valore (es. cache delle foto)
        self.send_response(codice)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(dati)))
        for k, v in intestazioni.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(dati)

    def _reindirizza(self, dove, cookie=None):
        self.send_response(302)
        self.send_header("Location", dove)
        self.send_header("Content-Length", "0")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        for k, v in INTESTAZIONI_SICUREZZA.items():
            self.send_header(k, v)
        self.end_headers()

    def _json(self, codice, obj):
        self._invia(codice, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _errore(self, codice, messaggio):
        self._json(codice, {"errore": messaggio})

    # ---- presenza della finestra: una connessione che resta aperta finché la pagina è aperta ----
    def _presenza(self, query):
        """La pagina apre questa connessione appena si carica e la tiene aperta. Finché è aperta la
        finestra esiste; appena la pagina si chiude (anche se il browser viene "ucciso" o si blocca)
        Windows chiude la connessione e il programma se ne accorge subito. È il segnale più
        affidabile di "finestra chiusa"; i battiti e l'"addio" della pagina restano come rinforzo."""
        id_pagina = (query.get("id") or [""])[0]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", id_pagina):
            return self._errore(400, "Identificativo di pagina non valido.")
        with _blocco_presenze:                                      # un tetto ai collegamenti aperti: niente "inondazioni"
            if _presenze_aperte[0] >= MAX_PRESENZE:
                return self._errore(429, "Troppi collegamenti aperti.")
            _presenze_aperte[0] += 1
        try:
            self._presenza_aperta(id_pagina)
        finally:
            with _blocco_presenze:
                _presenze_aperte[0] -= 1

    def _presenza_aperta(self, id_pagina):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Connection", "close")
        for k, v in INTESTAZIONI_SICUREZZA.items():
            self.send_header(k, v)
        self.end_headers()
        fine = getattr(self.server, "fine_sorveglianza", None)       # si accende quando il programma sta chiudendo
        try:
            self.wfile.write(b"retry: 1000\n\n")                    # se la connessione cade, la pagina riprova dopo 1 secondo
            self.wfile.flush()
            giri = 0
            while fine is None or not fine.is_set():
                STATO_FINESTRA.battito(id_pagina)                    # "questa pagina è ancora qui"
                # Aspetta fino a 1 secondo. Se la connessione diventa "leggibile" significa che dall'altra
                # parte (il browser) l'hanno chiusa: la pagina non c'è più. Una pagina viva non scrive mai nulla.
                chiusa, _, _ = select.select([self.connection], [], [], 1.0)
                if chiusa:
                    break
                giri += 1
                if giri % 5 == 0:                                    # ogni 5 secondi un segnale vuoto, per accorgerci di errori di scrittura
                    self.wfile.write(b": ok\n\n")
                    self.wfile.flush()
        except (OSError, ValueError):
            pass                                                     # connessione caduta: è proprio quello che cerchiamo
        finally:
            STATO_FINESTRA.addio(id_pagina)                          # la pagina non c'è più (se era l'ultima parte il conto alla rovescia)
            self.close_connection = True

    # ---- smistamento ----
    def _gestisci(self):
        try:
            if not self._host_ok():
                return self._errore(403, "Indirizzo non ammesso.")
            if not self._origine_ok():
                return self._errore(403, "Origine non ammessa.")
            if len(self.path) > 2000:
                return self._errore(414, "Indirizzo troppo lungo.")
            url = urllib.parse.urlsplit(self.path)
            percorso, query = url.path, urllib.parse.parse_qs(url.query, keep_blank_values=True)
            if self.command in ("POST", "PUT", "PATCH", "DELETE") and self.headers.get("X-NeoTracker") != "1":
                return self._errore(403, "Richiesta non autorizzata.")

            # ---- chiave di sessione (vedi 6c-bis) ----
            if percorso not in PERCORSI_LIBERI:
                avvio = (query.get("avvio") or [""])[0]
                if self.command == "GET" and percorso == "/" and avvio:
                    # la finestra si presenta con la chiave: la ricordo in un cookie riservato e ripulisco l'indirizzo
                    if not chiave_uguale(avvio, TOKEN_SESSIONE):
                        return self._invia(403, PAGINA_ACCESSO_NEGATO, "text/html; charset=utf-8",
                                           {"Content-Security-Policy": CSP})
                    cookie = f"{NOME_COOKIE}={TOKEN_SESSIONE}; Path=/; HttpOnly; SameSite=Strict"
                    return self._reindirizza("/", cookie)
                if not self._cookie_ok():
                    if self.command == "GET" and not percorso.startswith(("/api/", "/foto/")):
                        return self._invia(403, PAGINA_ACCESSO_NEGATO, "text/html; charset=utf-8",
                                           {"Content-Security-Policy": CSP})
                    return self._errore(403, "Accesso non autorizzato.")

            if self.command == "GET" and percorso == "/api/presenza":
                return self._presenza(query)

            if self.command == "GET" and not percorso.startswith(("/api/", "/foto/")):
                voce = WEB_FILES.get("/index.html" if percorso == "/" else percorso)
                if voce is None:
                    return self._errore(404, "Pagina non trovata.")
                mime, dati = voce
                extra = {"Content-Security-Policy": CSP} if mime.startswith("text/html") else {}
                return self._invia(200, dati, mime, extra)

            trovato_percorso = False
            for metodo, regex, funzione in ROTTE:
                m = regex.match(percorso)
                if not m:
                    continue
                trovato_percorso = True
                if metodo != self.command:
                    continue
                rq = Richiesta(self, self.command, percorso, query, m.groups())
                ris = funzione(rq)
                if isinstance(ris, RispostaFile):
                    return self._invia(200, ris.dati, ris.mime, dict(ris.extra, **{"Content-Security-Policy": CSP_FILE}))
                return self._json(200, ris)
            if trovato_percorso:
                return self._errore(405, "Operazione non consentita su questo indirizzo.")
            return self._errore(404, "Indirizzo sconosciuto.")
        except ErroreRichiesta as e:
            self._errore(e.codice, str(e))
        except ErroreServizio as e:
            self._errore(502, str(e))
        except (BrokenPipeError, ConnectionResetError):
            pass                                       # il browser ha chiuso la connessione: nessun problema
        except Exception as e:                         # errore nostro: lo mostro in console e lo segnalo al browser
            traceback.print_exc()                      # i dettagli restano nel registro (neotracker.log), non nella risposta
            try:
                self._errore(500, "Errore interno. I dettagli sono nel file neotracker.log nella cartella dei dati.")
            except Exception:
                pass

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _gestisci

    def do_HEAD(self):
        self._errore(405, "Non consentito.")

    def do_OPTIONS(self):
        self._errore(403, "Non consentito.")


# ==========================================================================================
# 6d. PAGINE WEB (HTML / CSS / JavaScript) incorporate in questo file
# ==========================================================================================
# Se vuoi modificare l'aspetto dell'app puoi cambiare anche il testo qui sotto.

_WEB_APP_JS = r'''/* ============================================================================
   app.js - avvio, menu, scelta pagina e utente corrente
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h, $ = NT.$;

  const VOCI = [
    ['mappa', 'Mappa dei nei', 'mappa'], ['profilo', 'Profilo', 'profilo'], ['letteratura', 'Letteratura', 'letteratura'],
    ['genetica', 'Genetica', 'genetica'], ['uv', 'Indice UV', 'uv'], ['impostazioni', 'Impostazioni', 'impostazioni'],
  ];

  NT.colorePerNome = nome => { let x = 0; for (const c of nome) x = (x * 31 + c.charCodeAt(0)) % 360; return 'hsl(' + x + ',45%,38%)'; };
  /* Cerchio con l'immagine personale dell'utente (se l'ha scelta) oppure con l'iniziale del nome.
     "utente" e' facoltativo: serve solo ad avere id e versione dell'immagine (avatar_v, 0 = nessuna). */
  NT.avatar = (nome, dim, utente) => {
    const d = dim || 32, iniziale = (nome.trim()[0] || '?').toUpperCase();
    const cerchio = h('span', { class: 'avatar', style: { background: NT.colorePerNome(nome), width: d + 'px', height: d + 'px', fontSize: Math.round(d * 0.45) + 'px' } }, iniziale);
    if (utente && utente.avatar_v) {
      const img = h('img', { class: 'avatar-img', alt: '', draggable: 'false', src: '/api/utenti/' + utente.id + '/avatar?v=' + utente.avatar_v });
      img.addEventListener('error', () => cerchio.replaceChildren(iniziale));         // se l'immagine manca, torna l'iniziale
      cerchio.replaceChildren(img);
    }
    return cerchio;
  };

  NT.vai = nome => { if (location.hash === '#/' + nome) route(); else location.hash = '#/' + nome; };
  const nomeRotta = () => { const m = /^#\/(\w+)/.exec(location.hash); return m ? m[1] : 'mappa'; };

  function disegnaTestata(attiva) {
    const menu = $('#menu');
    menu.replaceChildren(...VOCI.map(([id, testo, ico]) =>
      h('a', { href: '#/' + id, class: 'voce' + (id === attiva ? ' attiva' : ''), 'aria-current': id === attiva ? 'page' : null }, NT.icona(ico, 18), h('span', {}, testo))));
    const box = $('#utente-box');
    box.replaceChildren(S.utente
      ? h('a', { href: '#/utenti', class: 'utente-chip', title: 'Cambia utente' }, NT.avatar(S.utente.nome, 28, S.utente),
        h('span', { class: 'utente-nome' }, S.utente.nome), h('span', { class: 'utente-cambia' }, 'Cambia'))
      : h('a', { href: '#/utenti', class: 'utente-chip' }, h('span', { class: 'utente-nome' }, 'Scegli utente')));
  }

  async function route() {
    NT.pulizie.splice(0).forEach(f => { try { f(); } catch (e) { /* ignora */ } });
    let nome = nomeRotta();
    const serveUtente = ['mappa', 'profilo', 'genetica'];
    if (!S.utente && serveUtente.includes(nome)) nome = 'utenti';
    if (!NT.viste[nome]) nome = S.utente ? 'mappa' : 'utenti';
    disegnaTestata(nome === 'utenti' ? '' : nome);
    const cont = $('#vista');
    cont.className = 'vista-' + nome;
    cont.replaceChildren(NT.caricamento());
    try { await NT.viste[nome](cont); }
    catch (e) {
      console.error(e);
      cont.replaceChildren(h('div', { class: 'scheda errore-pagina' }, h('h2', {}, 'Qualcosa non ha funzionato'), h('p', {}, e.message || String(e)),
        h('button', { class: 'btn', onclick: () => route() }, 'Riprova')));
    }
    window.scrollTo(0, 0);
  }
  NT.ridisegnaTestata = () => disegnaTestata(nomeRotta());

  NT.scegliUtente = async function (id, vai) {
    S.utente = await NT.get('/api/utenti/' + id);
    S.nei = await NT.get('/api/utenti/' + id + '/nevi');
    NT.ls.scrivi('nt_utente', String(id));
    NT.ridisegnaTestata();
    if (vai !== false) NT.vai('mappa');
  };
  NT.ricaricaUtente = async function () {
    if (!S.utente) return;
    S.utente = await NT.get('/api/utenti/' + S.utente.id);
    NT.ridisegnaTestata();
  };
  NT.ricaricaNei = async function () {
    if (!S.utente) return [];
    S.nei = await NT.get('/api/utenti/' + S.utente.id + '/nevi');
    return S.nei;
  };

  /* ---- "battito": ogni pochi secondi la pagina dice al programma "sono ancora aperta" ----
     Quando la finestra viene chiusa i battiti finiscono (e parte un ultimo messaggio di "addio"):
     il programma capisce che può spegnersi. Ogni pagina ha un numero casuale, così più finestre
     aperte insieme non si confondono. */
  const nuovoId = () => (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
    : String(Date.now()) + Math.random().toString(36).slice(2);
  let ID_PAGINA = nuovoId();
  NT.battitoAttivo = true;                       // diventa false dopo "Chiudi NeoTracker" (non deve più battere)
  function segnale(percorso) {
    if (!NT.battitoAttivo && percorso === '/api/battito') return;
    try {
      // keepalive: la richiesta parte anche mentre la pagina si sta chiudendo
      fetch(percorso, { method: 'POST', keepalive: true,
        headers: { 'Content-Type': 'application/json', 'X-NeoTracker': '1' },
        body: JSON.stringify({ id: ID_PAGINA }) }).catch(() => { /* programma già spento: va bene */ });
    } catch (e) { /* ignora */ }
  }
  // Connessione di presenza: resta aperta finché la pagina è aperta. Quando la finestra si chiude
  // (in qualunque modo) il programma lo nota subito. Si riconnette da sola se cade.
  function apriPresenza() {
    if (NT.presenza) { try { NT.presenza.close(); } catch (e) { /* ignora */ } }
    try { NT.presenza = new EventSource('/api/presenza?id=' + encodeURIComponent(ID_PAGINA)); } catch (e) { NT.presenza = null; }
  }
  apriPresenza();
  segnale('/api/battito');
  setInterval(() => segnale('/api/battito'), 5000);
  window.addEventListener('pageshow', ev => {
    // Se il browser ci "risveglia" da una copia messa da parte (ev.persisted), il programma aveva già
    // ricevuto l'addio: ci presentiamo come una pagina nuova, con un numero nuovo.
    if (ev.persisted) { ID_PAGINA = nuovoId(); apriPresenza(); }
    segnale('/api/battito');
  });
  window.addEventListener('pagehide', () => segnale('/api/addio'));
  document.addEventListener('visibilitychange', () => { if (!document.hidden) segnale('/api/battito'); });

  async function avvia() {
    try {
      [S.stato, S.imp, S.utenti] = await Promise.all([NT.get('/api/stato'), NT.get('/api/impostazioni'), NT.get('/api/utenti')]);
      const ultimo = parseInt(NT.ls.leggi('nt_utente') || '', 10);
      if (ultimo && S.utenti.some(u => u.id === ultimo)) await NT.scegliUtente(ultimo, false);
    } catch (e) {
      $('#vista').replaceChildren(h('div', { class: 'scheda errore-pagina' }, h('h2', {}, 'NeoTracker non risponde'), h('p', {}, e.message)));
      return;
    }
    window.addEventListener('hashchange', route);
    if (!location.hash || location.hash === '#') location.hash = S.utente ? '#/mappa' : '#/utenti';
    else route();
    if (S.imp.avvertenze_accettate !== S.stato.avvertenze_versione) NT.mostraAvvertenze();     // primo avvio (o avviso aggiornato)
  }
  avvia();
})();
'''
WEB_FILES["/app.js"] = ("text/javascript; charset=utf-8", _WEB_APP_JS.encode("utf-8"))

_WEB_BODY_JS = r'''/* ============================================================================
   body.js - mappa interattiva del corpo umano (fronte + retro) disegnata in SVG
   Le coordinate di ogni neo sono salvate "normalizzate": x e y da 0 a 1 dentro la
   figura (fronte o retro). Cosi' restano valide qualunque sia lo zoom o la finestra.
   ============================================================================ */
(function () {
  'use strict';
  const LARG = 400, ALT = 900;            // dimensioni di UNA figura
  const VB_W = 800, VB_H = 930;           // area completa: fronte (0-400) + retro (400-800)
  const CX = 200;
  const NS = 'http://www.w3.org/2000/svg';

  const f = n => Math.round(n * 100) / 100;

  /* ---------- geometria: curve morbide e "tubi" per gli arti ---------- */
  function curva(pts, chiusa) {
    const n = pts.length;
    const get = i => chiusa ? pts[(i + n) % n] : pts[Math.max(0, Math.min(n - 1, i))];
    let d = 'M' + f(pts[0][0]) + ' ' + f(pts[0][1]);
    const fine = chiusa ? n : n - 1;
    for (let i = 0; i < fine; i++) {
      const p0 = get(i - 1), p1 = get(i), p2 = get(i + 1), p3 = get(i + 2);
      d += 'C' + f(p1[0] + (p2[0] - p0[0]) / 6) + ' ' + f(p1[1] + (p2[1] - p0[1]) / 6) + ' ' +
        f(p2[0] - (p3[0] - p1[0]) / 6) + ' ' + f(p2[1] - (p3[1] - p1[1]) / 6) + ' ' + f(p2[0]) + ' ' + f(p2[1]);
    }
    return chiusa ? d + 'Z' : d;
  }

  const PER = 8;                           // punti calcolati tra due punti guida
  function campiona(punti) {
    const out = [], n = punti.length;
    const get = i => punti[Math.max(0, Math.min(n - 1, i))];
    for (let i = 0; i < n - 1; i++) {
      const p0 = get(i - 1), p1 = get(i), p2 = get(i + 1), p3 = get(i + 2);
      for (let k = 0; k < PER; k++) {
        const t = k / PER, t2 = t * t, t3 = t2 * t;
        const c = j => 0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2 +
          (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3);
        out.push([c(0), c(1), c(2)]);
      }
    }
    out.push(punti[n - 1].slice());
    return out;
  }

  /* bordi sinistro e destro di un tubo (punti guida [x, y, raggio]) */
  function bordi(punti, extra) {
    const d = campiona(punti), L = [], R = [];
    for (let i = 0; i < d.length; i++) {
      const a = d[Math.max(0, i - 1)], b = d[Math.min(d.length - 1, i + 1)];
      let tx = b[0] - a[0], ty = b[1] - a[1];
      const l = Math.hypot(tx, ty) || 1; tx /= l; ty /= l;
      const r = d[i][2] + (extra || 0);
      L.push([d[i][0] - ty * r, d[i][1] + tx * r]);
      R.push([d[i][0] + ty * r, d[i][1] - tx * r]);
    }
    return { L, R };
  }
  const aPath = poly => 'M' + poly.map(p => f(p[0]) + ' ' + f(p[1])).join('L') + 'Z';
  function tuboPoly(punti, extra) { const b = bordi(punti, extra); return b.L.concat(b.R.slice().reverse()); }
  /* tratto di tubo tra due punti guida (indici), leggermente allargato: serve per le regioni */
  function trattoPoly(punti, i0, i1, extra) {
    const b = bordi(punti, extra || 0);
    const a = i0 * PER, z = i1 * PER;
    return b.L.slice(a, z + 1).concat(b.R.slice(a, z + 1).reverse());
  }
  const specchia = punti => punti.map(p => [LARG - p[0]].concat(p.slice(1)));
  const rect = (x0, y0, x1, y1) => [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
  const specchiaPoly = poly => poly.map(p => [LARG - p[0], p[1]]);

  /* ---------- anatomia (lato sinistro dello schermo; il destro e' lo specchio) ---------- */
  const BRACCIO = [[124, 190, 22], [116, 225, 19], [108, 262, 17], [101, 300, 14.5], [95, 332, 15],
    [89, 372, 12.5], [83, 405, 9.5], [79, 430, 13.5], [76, 458, 12.5], [73, 484, 7]];
  const GAMBA = [[168, 478, 34], [166, 540, 31], [164, 590, 26], [162, 622, 22.5], [161, 652, 21],
    [160, 680, 20], [160, 720, 18], [159, 765, 15.5], [158, 800, 11.5], [158, 825, 10]];
  const COLLO = [[200, 116, 17], [200, 140, 17.5], [200, 154, 19]];
  const TORSO_SX = [[20, 136], [40, 148], [64, 160], [82, 172], [84, 188], [70, 214], [64, 236], [62, 268],
    [57, 305], [49, 340], [46, 372], [50, 408], [58, 440], [64, 470], [58, 494]];
  const TESTA = [[200, 34], [228, 44], [236, 74], [232, 100], [218, 124], [200, 132], [182, 124], [168, 100],
    [164, 74], [172, 44]];
  const PIEDE_F = [[158, 822, 10], [156, 842, 12.5], [152, 860, 14]];
  const PIEDE_R = [[158, 822, 10], [158, 846, 12.5], [158, 858, 11]];

  function sagoma(vista) {
    const torso = TORSO_SX.map(p => [CX - p[0], p[1]])
      .concat([[CX, 510]], TORSO_SX.slice().reverse().map(p => [CX + p[0], p[1]]));
    const forme = [curva(torso, true), curva(TESTA, true), aPath(tuboPoly(COLLO)),
      aPath(tuboPoly(BRACCIO)), aPath(tuboPoly(specchia(BRACCIO))),
      aPath(tuboPoly(GAMBA)), aPath(tuboPoly(specchia(GAMBA)))];
    const piede = vista === 'fronte' ? PIEDE_F : PIEDE_R;
    forme.push(aPath(tuboPoly(piede)), aPath(tuboPoly(specchia(piede))));
    // orecchie
    forme.push(ellisse(164, 86, 5.5, 11), ellisse(236, 86, 5.5, 11));
    // spalle (deltoidi), punte delle mani e dei piedi arrotondate
    for (const [x, y, r] of [BRACCIO[0], BRACCIO[9], piede[2]]) forme.push(cerchio(x, y, r), cerchio(LARG - x, y, r));
    return forme;
  }
  function ellisse(cx, cy, rx, ry) {
    return 'M' + f(cx - rx) + ' ' + f(cy) + 'a' + rx + ' ' + ry + ' 0 1 0 ' + (2 * rx) + ' 0a' + rx + ' ' + ry + ' 0 1 0 ' + (-2 * rx) + ' 0Z';
  }
  const cerchio = (cx, cy, r) => ellisse(cx, cy, r, r);

  /* ---------- regioni cliccabili ---------- */
  // genere: 'm' maschile (destro/sinistro), 'f' femminile (destra/sinistra), '' nessun lato
  function regioni(vista) {
    const R = [];
    const lato = (schermoSx) => (vista === 'fronte') === schermoSx ? 'destr' : 'sinistr';
    // aggiunge una regione sul lato sinistro dello schermo e il suo specchio sul destro
    function coppia(nome, genere, poly) {
      const suff = genere === 'f' ? 'a' : 'o';
      R.push({ nome: nome + ' ' + lato(true) + suff, poly: poly });
      R.push({ nome: nome + ' ' + lato(false) + suff, poly: specchiaPoly(poly) });
    }
    const singola = (nome, poly) => R.push({ nome: nome, poly: poly });
    const fr = vista === 'fronte';

    // testa e collo (ordine: dal piu' grande al piu' piccolo, cosi' le piccole stanno sopra)
    if (fr) {
      singola('Fronte e cuoio capelluto', rect(150, 24, 250, 58));
      singola('Viso', rect(150, 58, 250, 136));
    } else {
      singola('Cuoio capelluto (testa)', rect(150, 24, 250, 122));
    }
    singola(fr ? 'Collo' : 'Nuca e collo', rect(168, fr ? 128 : 116, 232, 170));
    // tronco
    if (fr) {
      coppia('Torace', 'm', rect(134, 160, 200, 302));
      coppia('Addome alto', 'm', rect(138, 302, 200, 378));
      coppia('Addome basso', 'm', rect(134, 378, 200, 444));
      coppia('Inguine', 'm', rect(130, 444, 200, 512));
    } else {
      coppia('Regione scapolare', 'f', rect(134, 160, 200, 264));
      coppia('Schiena (zona media)', 'f', rect(138, 264, 200, 346));
      coppia('Regione lombare', 'f', rect(134, 346, 200, 442));
      coppia('Gluteo', 'm', rect(130, 442, 200, 524));
    }
    // arti: tratti dello stesso tubo del disegno, un po' piu' larghi, poi ritagliati sulla sagoma
    const e = 7;
    coppia('Spalla', 'f', trattoPoly(BRACCIO, 0, 1, e));
    coppia('Braccio', 'm', trattoPoly(BRACCIO, 1, 3, e));
    coppia('Gomito', 'm', trattoPoly(BRACCIO, 3, 4, e));
    coppia('Avambraccio', 'm', trattoPoly(BRACCIO, 4, 6, e));
    coppia('Mano', 'f', trattoPoly(BRACCIO, 6, 9, e + 3));
    coppia('Coscia', 'f', trattoPoly(GAMBA, 0, 3, e));
    coppia(fr ? 'Ginocchio' : 'Cavo popliteo', 'm', trattoPoly(GAMBA, 3, 5, e));
    coppia(fr ? 'Gamba (stinco)' : 'Polpaccio', fr ? 'f' : 'm', trattoPoly(GAMBA, 5, 8, e));
    coppia('Caviglia', 'f', trattoPoly(GAMBA, 8, 9, e));
    coppia('Piede', 'm', rect(128, 822, 200, 880));
    // orecchie (sopra la testa)
    coppia('Orecchio', 'm', rect(150, 70, 168, 104));
    return R;
  }

  /* ---------- colori ---------- */
  const PELLE = { 0: '#ead9c8', 1: '#f6e0d2', 2: '#efcab0', 3: '#e0b390', 4: '#c58f68', 5: '#9b6a48', 6: '#6a4630' };
  const colorePelle = ft => PELLE[ft] || PELLE[0];

  /* ---------- dettagli anatomici (linee leggere) ---------- */
  function dettagli(vista) {
    const L = [];
    const l = (d, extra) => L.push('<path d="' + d + '" fill="none" ' + (extra || '') + '/>');
    const sp = (d) => d; // segnaposto
    if (vista === 'fronte') {
      l('M192 160Q165 154 140 168'); l('M208 160Q235 154 260 168');
      l('M142 232Q172 256 198 240'); l('M258 232Q228 256 202 240');
      L.push('<circle cx="167" cy="254" r="2.6" class="det-pieno"/>', '<circle cx="233" cy="254" r="2.6" class="det-pieno"/>');
      l('M200 262L200 376');
      L.push('<ellipse cx="200" cy="386" rx="3.2" ry="4.6" class="det-pieno"/>');
      l('M148 454Q176 470 200 494'); l('M252 454Q224 470 200 494');
      L.push('<ellipse cx="161" cy="652" rx="9" ry="11" fill="none"/>', '<ellipse cx="239" cy="652" rx="9" ry="11" fill="none"/>');
    } else {
      l('M200 138L199 220L201 330L200 470');
      l('M176 188Q150 196 152 232Q160 262 180 258'); l('M224 188Q250 196 248 232Q240 262 220 258');
      l('M200 446L200 510');
      l('M138 468Q164 524 200 512'); l('M262 468Q236 524 200 512');
      l('M150 656Q162 662 174 656'); l('M250 656Q238 662 226 656');
    }
    return L.join('');
  }

  /* ---------- costruzione dell'SVG di una figura ---------- */
  function figura(vista, ft, ox) {
    const id = vista === 'fronte' ? 'f' : 'r';
    const forme = sagoma(vista);
    const reg = regioni(vista);
    const colore = colorePelle(ft);
    let s = '<g transform="translate(' + ox + ',20)" data-vista="' + vista + '">';
    s += '<clipPath id="sil-' + id + '">' + forme.map(d => '<path d="' + d + '"/>').join('') + '</clipPath>';
    s += '<g class="contorno">' + forme.map(d => '<path d="' + d + '"/>').join('') + '</g>';
    s += '<g class="pelle" fill="' + colore + '">' + forme.map(d => '<path d="' + d + '"/>').join('') + '</g>';
    s += '<g class="dettagli" clip-path="url(#sil-' + id + ')">' + dettagli(vista) + '</g>';
    s += '<g class="regioni" clip-path="url(#sil-' + id + ')">' +
      reg.map(r => '<polygon points="' + r.poly.map(p => f(p[0]) + ',' + f(p[1])).join(' ') + '" data-regione="' + r.nome + '"/>').join('') + '</g>';
    s += '</g>';
    return s;
  }

  function svgCompleto(ft) {
    let s = '<svg xmlns="' + NS + '" class="corpo-svg" viewBox="0 0 ' + VB_W + ' ' + VB_H + '" preserveAspectRatio="xMidYMid meet" role="img" ' +
      'aria-label="Mappa del corpo umano: fronte a sinistra, retro a destra">';
    s += figura('fronte', ft, 0) + figura('retro', ft, LARG);
    // etichette fisse
    s += '<g class="etichette">' +
      '<text x="200" y="14" text-anchor="middle">FRONTE</text><text x="600" y="14" text-anchor="middle">RETRO</text>' +
      '<text x="22" y="64" class="lato">D</text><text x="378" y="64" text-anchor="end" class="lato">S</text>' +
      '<text x="422" y="64" class="lato">S</text><text x="778" y="64" text-anchor="end" class="lato">D</text></g>';
    s += '<g class="marcatori"></g></svg>';
    return s;
  }

  /* ============================================================================
     Classe MappaCorpo: zoom, trascinamento, aggiunta e spostamento dei nei
     ============================================================================ */
  class MappaCorpo {
    constructor(contenitore, cb) {
      this.box = contenitore;
      this.cb = cb || {};
      this.ft = 0;
      this.nei = [];
      this.selId = null;
      this.aggiunta = false;
      this.bozza = null;
      this.vb = { x: 0, y: 0, w: VB_W, h: VB_H };
      this.zoom = 1;
      this.drag = null;
      this.ricostruisci();
      this.ro = new ResizeObserver(() => this.disegnaMarcatori());
      this.ro.observe(this.box);
    }

    ricostruisci() {
      this.box.innerHTML = svgCompleto(this.ft);
      this.svg = this.box.querySelector('svg');
      this.gMarc = this.svg.querySelector('.marcatori');
      this.applicaVB();
      this.collega();
      this.disegnaMarcatori();
    }

    setFototipo(ft) { if (ft !== this.ft) { this.ft = ft; this.ricostruisci(); } }

    setNei(nei, selId) { this.nei = nei; this.selId = selId; this.disegnaMarcatori(); }
    setSelezione(id) { this.selId = id; this.disegnaMarcatori(); }
    modalitaAggiunta(on) {
      this.aggiunta = on;
      this.svg.classList.toggle('aggiunta', on);
      if (!on) this.bozza = null;
      this.disegnaMarcatori();
    }
    setBozza(b) { this.bozza = b; this.disegnaMarcatori(); }

    /* ---- vista (zoom e spostamento) ---- */
    applicaVB() {
      const v = this.vb;
      this.svg.setAttribute('viewBox', f(v.x) + ' ' + f(v.y) + ' ' + f(v.w) + ' ' + f(v.h));
    }
    limita() {
      const v = this.vb;
      v.w = VB_W / this.zoom; v.h = VB_H / this.zoom;
      v.x = Math.max(0, Math.min(VB_W - v.w, v.x));
      v.y = Math.max(0, Math.min(VB_H - v.h, v.y));
    }
    zoomSu(fattore, cx, cy) {
      const nuovo = Math.max(1, Math.min(12, this.zoom * fattore));
      if (nuovo === this.zoom) return;
      if (cx == null) { cx = this.vb.x + this.vb.w / 2; cy = this.vb.y + this.vb.h / 2; }
      const rx = (cx - this.vb.x) / this.vb.w, ry = (cy - this.vb.y) / this.vb.h;   // punto fisso sotto il cursore
      this.zoom = nuovo;
      this.vb.w = VB_W / nuovo; this.vb.h = VB_H / nuovo;
      this.vb.x = cx - rx * this.vb.w; this.vb.y = cy - ry * this.vb.h;
      this.limita(); this.applicaVB(); this.disegnaMarcatori();
    }
    reset() { this.zoom = 1; this.vb = { x: 0, y: 0, w: VB_W, h: VB_H }; this.applicaVB(); this.disegnaMarcatori(); }
    centraSu(nevo, zoom) {
      const p = this.posizione(nevo.vista, nevo.x, nevo.y);
      this.zoom = zoom || Math.max(this.zoom, 4);
      this.vb.w = VB_W / this.zoom; this.vb.h = VB_H / this.zoom;
      this.vb.x = p.x - this.vb.w / 2; this.vb.y = p.y - this.vb.h / 2;
      this.limita(); this.applicaVB(); this.disegnaMarcatori();
    }

    /* ---- conversioni tra coordinate dello schermo e della figura ---- */
    posizione(vista, x, y) {         // da normalizzate (0-1) a coordinate dell'SVG
      return { x: (vista === 'retro' ? LARG : 0) + x * LARG, y: 20 + y * ALT };
    }
    daSchermo(ev) {                  // da pixel a { vista, x, y } normalizzati
      const pt = this.svg.createSVGPoint();
      pt.x = ev.clientX; pt.y = ev.clientY;
      const p = pt.matrixTransform(this.svg.getScreenCTM().inverse());
      const vista = p.x >= LARG ? 'retro' : 'fronte';
      const x = (p.x - (vista === 'retro' ? LARG : 0)) / LARG, y = (p.y - 20) / ALT;
      return { vista, x, y, px: p.x, py: p.y };
    }
    regioneA(ev) {                   // nome della regione sotto il puntatore (o '')
      const els = document.elementsFromPoint(ev.clientX, ev.clientY);
      for (const el of els) if (el.dataset && el.dataset.regione) return el.dataset.regione;
      return '';
    }
    dentroCorpo(ev) {
      return document.elementsFromPoint(ev.clientX, ev.clientY).some(el => el.dataset && el.dataset.regione);
    }
    scala() { const m = this.svg.getScreenCTM(); return m ? 1 / m.a : 1; }

    /* ---- marcatori ---- */
    disegnaMarcatori() {
      if (!this.gMarc) return;
      const k = this.scala();
      let s = '';
      const mostraNome = this.zoom >= 3;
      for (const n of this.nei) {
        if (n.archiviato) continue;
        const p = this.posizione(n.vista, n.x, n.y);
        const sel = n.id === this.selId;
        const cls = 'marc' + (sel ? ' sel' : '') + (n.flag ? ' flag' : '') + (n.senzaFoto ? ' vuoto' : '');
        s += '<g class="' + cls + '" data-id="' + n.id + '" transform="translate(' + f(p.x) + ',' + f(p.y) + ') scale(' + f(k) + ')">' +
          (sel ? '<circle class="alone" r="17"/>' : '') +
          '<circle class="area" r="15"/><circle class="punto" r="9"/>' +
          '<text class="num" y="3.4" text-anchor="middle">' + n.num + '</text>' +
          (mostraNome ? '<text class="nome" x="14" y="4">' + esc(n.nome) + '</text>' : '') + '</g>';
      }
      if (this.bozza) {
        const p = this.posizione(this.bozza.vista, this.bozza.x, this.bozza.y);
        s += '<g class="marc bozza" transform="translate(' + f(p.x) + ',' + f(p.y) + ') scale(' + f(k) + ')">' +
          '<circle class="area" r="16"/><circle class="punto" r="9"/><path d="M-15 0H-5M5 0H15M0 -15V-5M0 5V15" class="mirino"/></g>';
      }
      s += '<g class="fantasma" style="display:none" transform="scale(' + f(k) + ')"><circle r="8"/><path d="M-12 0H-4M4 0H12M0 -12V-4M0 4V12"/></g>';
      this.gMarc.innerHTML = s;
      this.fantasma = this.gMarc.querySelector('.fantasma');
    }

    /* ---- interazione ---- */
    collega() {
      const svg = this.svg;
      svg.addEventListener('wheel', ev => {
        ev.preventDefault();
        const p = this.daSchermo(ev);
        this.zoomSu(ev.deltaY < 0 ? 1.18 : 1 / 1.18, p.px, p.py);
      }, { passive: false });

      svg.addEventListener('pointerdown', ev => {
        if (ev.button !== 0) return;
        const marc = ev.target.closest && ev.target.closest('.marc:not(.fantasma)');
        const dati = { sx: ev.clientX, sy: ev.clientY, mosso: false, vb0: Object.assign({}, this.vb), id: ev.pointerId };
        if (marc) {
          dati.tipo = marc.classList.contains('bozza') ? 'bozza' : 'marc';
          dati.nid = marc.dataset.id ? parseInt(marc.dataset.id, 10) : null;
        } else dati.tipo = 'sfondo';
        this.drag = dati;
        svg.setPointerCapture(ev.pointerId);
      });

      svg.addEventListener('pointermove', ev => {
        const d = this.drag;
        if (d && d.id === ev.pointerId) {
          const dx = ev.clientX - d.sx, dy = ev.clientY - d.sy;
          if (!d.mosso && Math.hypot(dx, dy) > 5) d.mosso = true;
          if (d.mosso) {
            if (d.tipo === 'sfondo' && !this.aggiunta) {                       // trascinamento della vista
              const k = this.scala();
              this.vb.x = d.vb0.x - dx * k; this.vb.y = d.vb0.y - dy * k;
              this.limita(); this.applicaVB();
              svg.classList.add('trascina');
            } else if (d.tipo === 'marc' || d.tipo === 'bozza') {              // spostamento di un neo
              if (d.tipo === 'marc' && d.nid !== this.selId) return;           // si sposta solo il neo selezionato
              const p = this.daSchermo(ev);
              if (this.dentroCorpo(ev)) {
                d.pos = { vista: p.vista, x: Math.max(0, Math.min(1, p.x)), y: Math.max(0, Math.min(1, p.y)) };
                if (d.tipo === 'bozza') this.bozza = Object.assign({}, this.bozza, d.pos);
                else { const n = this.nei.find(q => q.id === d.nid); if (n) Object.assign(n, d.pos); }
                this.disegnaMarcatori();
              }
            }
          }
        }
        // etichetta della regione e puntatore "fantasma"
        if (this.cb.onRegione && !(d && d.mosso)) this.cb.onRegione(this.regioneA(ev));
        if (this.aggiunta && this.fantasma && !(d && d.mosso)) {
          const p = this.daSchermo(ev);
          if (this.dentroCorpo(ev)) {
            this.fantasma.style.display = '';
            this.fantasma.setAttribute('transform', 'translate(' + f(p.px) + ',' + f(p.py) + ') scale(' + f(this.scala()) + ')');
          } else this.fantasma.style.display = 'none';
        }
      });

      const fine = ev => {
        const d = this.drag;
        if (!d || d.id !== ev.pointerId) return;
        this.drag = null;
        svg.classList.remove('trascina');
        try { svg.releasePointerCapture(ev.pointerId); } catch (e) { /* gia' rilasciato */ }
        if (ev.type === 'pointercancel') { this.disegnaMarcatori(); return; }
        if (d.mosso && d.pos) {                                                // fine dello spostamento
          const reg = this.regioneA(ev);
          if (d.tipo === 'bozza') this.cb.onBozzaMossa && this.cb.onBozzaMossa(Object.assign({ regione: reg }, d.pos));
          else this.cb.onSposta && this.cb.onSposta(d.nid, Object.assign({ regione: reg }, d.pos));
          return;
        }
        if (d.mosso) return;                                                   // era un trascinamento della vista
        // semplice clic
        if (d.tipo === 'marc') { this.cb.onSeleziona && this.cb.onSeleziona(d.nid); return; }
        if (d.tipo === 'bozza') return;
        if (this.aggiunta) {
          if (!this.dentroCorpo(ev)) return;
          const p = this.daSchermo(ev);
          this.cb.onPunto && this.cb.onPunto({ vista: p.vista, x: p.x, y: p.y, regione: this.regioneA(ev) });
        } else this.cb.onSeleziona && this.cb.onSeleziona(null);
      };
      svg.addEventListener('pointerup', fine);
      svg.addEventListener('pointercancel', fine);
      svg.addEventListener('pointerleave', () => {
        if (this.fantasma) this.fantasma.style.display = 'none';
        this.cb.onRegione && this.cb.onRegione('');
      });
      svg.addEventListener('dblclick', ev => {
        if (this.aggiunta) return;
        const p = this.daSchermo(ev); this.zoomSu(2, p.px, p.py);
      });
    }
  }

  function esc(t) {
    return String(t).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  window.Corpo = { MappaCorpo, colorePelle, regioni, svgCompleto, LARG, ALT };
})();
'''
WEB_FILES["/body.js"] = ("text/javascript; charset=utf-8", _WEB_BODY_JS.encode("utf-8"))

_WEB_ICONA_PNG_B64 = """
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
"""
WEB_FILES["/icona.png"] = ("image/png", base64.b64decode(_WEB_ICONA_PNG_B64))

_WEB_INDEX_HTML = r'''<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NeoTracker</title>
<link rel="icon" type="image/png" href="/icona.png">
<link rel="apple-touch-icon" href="/icona.png">
<link rel="stylesheet" href="/style.css">
</head>
<body>
<header id="testata">
  <a class="marchio" href="#/mappa" aria-label="NeoTracker">
    <svg viewBox="0 0 32 32" width="30" height="30" aria-hidden="true"><rect width="32" height="32" rx="8" fill="#fff" fill-opacity=".14"/><circle cx="16" cy="16" r="8" fill="none" stroke="#fff" stroke-width="2.4"/><circle cx="16" cy="16" r="3.6" fill="#ff8a3d"/></svg>
    <span>NeoTracker</span>
  </a>
  <nav id="menu" aria-label="Sezioni"></nav>
  <div id="utente-box"></div>
</header>
<main id="vista" tabindex="-1"></main>
<footer id="piede">NeoTracker non è uno strumento medico e non fa diagnosi. Per qualsiasi neo che cambia, sanguina, prude o ti preoccupa, rivolgiti a un dermatologo.</footer>
<div id="toast" role="status" aria-live="polite"></div>
<dialog id="dialogo"></dialog>
<dialog id="lightbox"></dialog>
<div id="stampa" aria-hidden="true"></div>
<script src="/util.js"></script>
<script src="/body.js"></script>
<script src="/v_utenti.js"></script>
<script src="/v_mappa.js"></script>
<script src="/v_profilo.js"></script>
<script src="/v_scienza.js"></script>
<script src="/v_uv.js"></script>
<script src="/v_impostazioni.js"></script>
<script src="/stampa.js"></script>
<script src="/app.js"></script>
</body>
</html>
'''
WEB_FILES["/index.html"] = ("text/html; charset=utf-8", _WEB_INDEX_HTML.encode("utf-8"))

_WEB_STAMPA_JS = r'''/* ============================================================================
   stampa.js - scheda stampabile per il dermatologo (mappa, storico, misure)
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  const SESSO = { F: 'donna', M: 'uomo', altro: 'altro' };
  const FOTOTIPI = ['I', 'II', 'III', 'IV', 'V', 'VI'];
  const ESITO_STAMPA = {
    attenzione: 'tutti i metodi con risultato indicano un neo da attenzionare',
    discordante: 'i metodi non concordano tra loro',
    benigno: 'nessun metodo ha segnalato il neo (questo non esclude un melanoma)',
    nessuno: 'nessun risultato disponibile',
  };

  function riepilogoProfilo(u) {
    const p = u.profilo, righe = [];
    if (u.eta !== null && u.eta !== undefined) righe.push(['Età', u.eta + ' anni']);
    if (p.sesso) righe.push(['Sesso', SESSO[p.sesso] || p.sesso]);
    if (p.fototipo) righe.push(['Fototipo', FOTOTIPI[p.fototipo - 1]]);
    const fen = [p.capelli && 'capelli ' + p.capelli, p.occhi && 'occhi ' + p.occhi, p.efelidi && 'efelidi: ' + p.efelidi].filter(Boolean).join(', ');
    if (fen) righe.push(['Aspetto', fen]);
    if (p.n_nevi) righe.push(['Numero di nei', p.n_nevi]);
    if (p.nevi_atipici) righe.push(['Nei atipici', p.nevi_atipici]);
    if (p.scottature) righe.push(['Scottature', p.scottature]);
    if (p.lampade) righe.push(['Lampade abbronzanti', p.lampade]);
    if (p.melanomi_personali) righe.push(['Melanomi già diagnosticati', String(p.melanomi_personali)]);
    if (p.fam_compilata) {
      const f = [];
      if (p.fam_melanoma_1grado) f.push(p.fam_melanoma_1grado + ' parente/i di primo grado con melanoma');
      if (p.fam_melanoma_altri) f.push(p.fam_melanoma_altri + ' altro/i parente/i con melanoma');
      if (p.fam_pancreas) f.push(p.fam_pancreas + ' con tumore del pancreas');
      if (p.fam_astrocitoma) f.push(p.fam_astrocitoma + ' con astrocitoma');
      if (p.fam_uveale) f.push(p.fam_uveale + ' con melanoma uveale');
      righe.push(['Storia familiare', f.length ? f.join('; ') : 'nessun caso indicato']);
    }
    if (p.test_genetico && p.test_genetico !== 'no') righe.push(['Test genetico già eseguito', { si_positivo: 'sì, positivo', si_negativo: 'sì, negativo', si_non_informativo: 'sì, non informativo' }[p.test_genetico] || p.test_genetico]);
    return righe;
  }

  function mappaStampa(nei) {
    const ft = S.utente.profilo.fototipo || 0;
    const radice = NT.html(window.Corpo.svgCompleto(ft));
    const g = radice.querySelector('.marcatori');
    const NSV = 'http://www.w3.org/2000/svg';
    nei.forEach((n, i) => {
      const x = (n.vista === 'retro' ? 400 : 0) + n.x * 400, y = 20 + n.y * 900;
      const gr = document.createElementNS(NSV, 'g');
      gr.setAttribute('transform', 'translate(' + x.toFixed(1) + ',' + y.toFixed(1) + ')');
      const c = document.createElementNS(NSV, 'circle'); c.setAttribute('r', '19'); c.setAttribute('class', 'st-punto');
      const t = document.createElementNS(NSV, 'text'); t.setAttribute('y', '7'); t.setAttribute('text-anchor', 'middle'); t.setAttribute('class', 'st-num'); t.textContent = String(i + 1);
      gr.append(c, t); g.appendChild(gr);
    });
    radice.setAttribute('class', 'corpo-svg mappa-stampa');
    return radice;
  }

  function schedaNeo(num, n, foto) {
    const prima = foto[0], ultima = foto[foto.length - 1];
    let variazione = null;
    if (foto.length > 1) {
      const giorni = NT.giorniTra(prima.scattata_il, ultima.scattata_il);
      const dd = (prima.diametro_mm && ultima.diametro_mm) ? ' Diametro: da ' + NT.num(prima.diametro_mm) + ' a ' + NT.num(ultima.diametro_mm) + ' mm.' : '';
      variazione = foto.length + ' foto in ' + giorni + ' giorni (dal ' + NT.fmtData(prima.scattata_il) + ' al ' + NT.fmtData(ultima.scattata_il) + ').' + dd;
    }
    const mostra = foto.length <= 8 ? foto : [foto[0], foto[1]].concat(foto.slice(-6));
    return h('section', { class: 'st-neo' },
      h('h3', {}, h('span', { class: 'st-badge' }, num), ' ', n.nome, n.regione ? ' – ' + n.regione : ' – ' + (n.vista === 'retro' ? 'retro' : 'fronte')),
      n.note ? h('p', { class: 'st-nota' }, 'Note: ' + n.note) : null,
      foto.length ? [
        variazione ? h('p', {}, variazione) : h('p', {}, '1 foto del ' + NT.fmtData(prima.scattata_il) + (prima.diametro_mm ? ', diametro ' + NT.num(prima.diametro_mm) + ' mm' : '') + '.'),
        h('div', { class: 'st-foto' }, mostra.map(f => h('figure', {}, h('img', { src: '/foto/' + f.id + '/mini?l=480', alt: 'Foto del ' + NT.fmtData(f.scattata_il) }),
          h('figcaption', {}, NT.fmtData(f.scattata_il), f.diametro_mm ? ' · ' + NT.num(f.diametro_mm) + ' mm' : '', f.tipo === 'dermoscopica' ? ' · dermoscopica' : '')))),
        foto.length > mostra.length ? h('p', { class: 'st-nota' }, 'Sono mostrate ' + mostra.length + ' foto su ' + foto.length + '.') : null,
        ultima.esito ? h('p', { class: 'st-nota' }, 'Ultima analisi automatica (' + NT.fmtData(ultima.scattata_il) + '): ' + (ESITO_STAMPA[ultima.esito] || ultima.esito) + '. Strumento di ricerca, non diagnostico.') : null,
      ] : h('p', { class: 'st-nota' }, 'Nessuna foto ancora registrata.'));
  }

  NT.stampaNei = async function (ids) {
    if (!S.utente) return;
    const area = NT.$('#stampa');
    try {
      NT.toast('Preparo la scheda…', 'info');
      await NT.ricaricaUtente();
      await NT.ricaricaNei();
      const scelti = S.nei.filter(n => !n.archiviato && (!ids || ids.includes(n.id)));
      if (!scelti.length) { NT.toast('Non ci sono nei da stampare.', 'errore'); return; }
      const dettagli = await Promise.all(scelti.map(n => NT.get('/api/nevi/' + n.id)));
      const tutti = S.nei.filter(n => !n.archiviato);
      const numero = id => tutti.findIndex(n => n.id === id) + 1;
      const u = S.utente, rischio = u.rischio.presenti;
      const prof = riepilogoProfilo(u);
      const nuovo = h('div', { class: 'st-pagina' },
        h('header', { class: 'st-testata' }, h('div', {}, h('h1', {}, 'Scheda dei nei – ' + u.nome), h('div', { class: 'st-sotto' }, 'Stampata il ' + NT.fmtData(NT.oggiISO()) + ' con NeoTracker')),
          h('div', { class: 'st-sotto' }, scelti.length + (scelti.length === 1 ? ' neo' : ' nei') + ' in questa scheda')),
        h('section', { class: 'st-profilo' }, h('h2', {}, 'Dati della persona'),
          prof.length ? h('dl', {}, prof.map(([k, v]) => [h('dt', {}, k), h('dd', {}, v)])) : h('p', { class: 'st-nota' }, 'Profilo non compilato.'),
          rischio.length ? h('p', {}, h('strong', {}, 'Fattori di rischio indicati: '), rischio.map(r => r.etichetta).join('; ') + '.') : null),
        h('section', {}, h('h2', {}, 'Dove si trovano'), mappaStampa(scelti.map(n => Object.assign({}, n))),
          h('p', { class: 'st-nota' }, 'I numeri corrispondono alle schede seguenti. Sulla figura: a sinistra la vista frontale, a destra quella posteriore.')),
        dettagli.map(d => schedaNeo(numero(d.nevo.id), d.nevo, d.foto)),
        h('footer', { class: 'st-avviso' }, 'Questa scheda raccoglie dati inseriti dalla persona e foto da lei scattate. I risultati dell\'analisi automatica sono sperimentali, non sono una diagnosi e non sostituiscono la visita dermatologica o la dermoscopia.'));
      // numeri coerenti con la mappa: usa la numerazione globale, non quella della selezione
      NT.$$('.st-num', nuovo).forEach((t, i) => { t.textContent = String(numero(scelti[i].id)); });
      area.replaceChildren(nuovo);
      const imgs = NT.$$('img', area);
      await Promise.all(imgs.map(im => new Promise(r => { if (im.complete) r(); else { im.addEventListener('load', r, { once: true }); im.addEventListener('error', r, { once: true }); } })));
      const pulisci = () => { area.replaceChildren(); window.removeEventListener('afterprint', pulisci); };
      window.addEventListener('afterprint', pulisci);
      document.body.classList.add('in-stampa');
      window.print();
      setTimeout(() => document.body.classList.remove('in-stampa'), 1000);
    } catch (e) { NT.errore(e); }
  };
})();
'''
WEB_FILES["/stampa.js"] = ("text/javascript; charset=utf-8", _WEB_STAMPA_JS.encode("utf-8"))

_WEB_STYLE_CSS = r'''/* ============================================================================
   NeoTracker - foglio di stile
   Colori: blu-verde #0e5a6b (principale), arancio #e36414 (accento), fondo chiaro.
   ============================================================================ */
:root {
  --pri: #0e5a6b; --pri-sc: #0a4351; --pri-ch: #e3f0f3; --acc: #e36414; --acc-sc: #c4520d;
  --testo: #1d2b33; --muted: #5c6b75; --bordo: #d5dde2; --bordo-sc: #b5c1c9;
  --fondo: #f1f5f7; --scheda: #ffffff; --rosso: #c1121f; --verde: #2f7d32; --giallo: #b78400; --arancio: #d9690b;
  --r: 12px; --ombra: 0 1px 2px rgba(20, 40, 50, .06), 0 4px 14px rgba(20, 40, 50, .05);
  --font: "Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--fondo); color: var(--testo); font: 15px/1.5 var(--font); min-height: 100vh; display: flex; flex-direction: column; }
h1, h2, h3 { line-height: 1.25; margin: 0 0 .5em; color: #12333d; }
h1 { font-size: 1.7rem; letter-spacing: -.01em; }
h2 { font-size: 1.2rem; } h3 { font-size: 1.02rem; }
p { margin: 0 0 .8em; } a { color: var(--pri); }
a:hover { color: var(--pri-sc); }
ul, ol { margin: 0 0 .8em; padding-left: 1.3em; } li { margin: .2em 0; }
code { background: #eaf0f3; padding: .1em .4em; border-radius: 5px; font-size: .9em; word-break: break-all; }
:focus-visible { outline: 3px solid #f7a35c; outline-offset: 2px; border-radius: 4px; }
.nascosto { position: absolute; width: 1px; height: 1px; opacity: 0; overflow: hidden; pointer-events: none; }
.piccolo { font-size: .86rem; } .muted { color: var(--muted); } .spazio { flex: 1; } .spazio-su { margin-top: .8rem; } .spazio-giu { margin-bottom: .6rem; }
.blocco { display: block; } .pericolo { color: var(--rosso) !important; }

/* ---------- testata ---------- */
#testata { background: linear-gradient(135deg, #0b4856, #0e5a6b 60%, #137085); color: #fff; display: flex; align-items: center; gap: 1.2rem; padding: .55rem 1.2rem; position: sticky; top: 0; z-index: 20; box-shadow: 0 2px 8px rgba(0, 0, 0, .18); }
.marchio { display: flex; align-items: center; gap: .55rem; color: #fff; text-decoration: none; font-weight: 700; font-size: 1.15rem; letter-spacing: .01em; }
.marchio:hover { color: #fff; }
#menu { display: flex; gap: .15rem; flex: 1; flex-wrap: wrap; }
.voce { display: inline-flex; align-items: center; gap: .4rem; padding: .45rem .75rem; color: #d7ebef; text-decoration: none; border-radius: 9px; font-weight: 600; font-size: .92rem; }
.voce:hover { background: rgba(255, 255, 255, .13); color: #fff; }
.voce.attiva { background: #fff; color: var(--pri); }
.utente-chip { display: flex; align-items: center; gap: .5rem; padding: .25rem .7rem .25rem .3rem; border-radius: 999px; background: rgba(255, 255, 255, .14); color: #fff; text-decoration: none; font-weight: 600; }
.utente-chip:hover { background: rgba(255, 255, 255, .24); color: #fff; }
.utente-cambia { font-size: .75rem; font-weight: 500; opacity: .8; border-left: 1px solid rgba(255, 255, 255, .4); padding-left: .5rem; }
.avatar { display: inline-flex; align-items: center; justify-content: center; border-radius: 50%; color: #fff; font-weight: 700; flex: none; overflow: hidden; }
.avatar-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.avatar-editor { display: flex; align-items: center; gap: 1.2rem; flex-wrap: wrap; }
.avatar-azioni { flex: 1 1 18rem; display: flex; flex-direction: column; gap: .5rem; }
.avvertenze ul { padding-left: 1.2rem; margin: .6rem 0 1rem; }
.avvertenze li { margin: .35rem 0; }

#vista { flex: 1; padding: 1.3rem 1.2rem 2rem; width: 100%; max-width: 1500px; margin: 0 auto; outline: none; }
#piede { text-align: center; padding: .9rem 1rem; color: var(--muted); font-size: .8rem; border-top: 1px solid var(--bordo); background: #e9eff2; }
.pagina { max-width: 980px; margin: 0 auto; } .pagina.stretta { max-width: 560px; }
.lead { font-size: 1.04rem; color: var(--muted); max-width: 70ch; }

/* ---------- schede, pulsanti, campi ---------- */
.scheda { background: var(--scheda); border: 1px solid var(--bordo); border-radius: var(--r); padding: 1.1rem 1.2rem; box-shadow: var(--ombra); margin-bottom: 1rem; }
.scheda > :last-child { margin-bottom: 0; }
.scheda.info { background: var(--pri-ch); border-color: #b9d8df; }
.scheda.errore-pagina { border-color: #e7b3b7; background: #fff6f6; }
.pila { display: flex; flex-direction: column; } .pila > .scheda { margin-bottom: .9rem; }

.btn { display: inline-flex; align-items: center; justify-content: center; gap: .45rem; padding: .55rem 1rem; border: 1px solid var(--bordo-sc); background: #fff; color: var(--testo); border-radius: 9px; font: inherit; font-weight: 600; cursor: pointer; text-decoration: none; transition: background .12s, border-color .12s, box-shadow .12s; }
.btn:hover:not(:disabled) { background: #f2f6f8; border-color: #8fa2ad; color: var(--testo); }
.btn:disabled { opacity: .55; cursor: not-allowed; }
.btn-pri { background: var(--pri); border-color: var(--pri); color: #fff; }
.btn-pri:hover:not(:disabled) { background: var(--pri-sc); border-color: var(--pri-sc); color: #fff; }
.btn-pericolo { background: var(--rosso); border-color: var(--rosso); color: #fff; }
.btn-pericolo:hover:not(:disabled) { background: #9c0d18; border-color: #9c0d18; color: #fff; }
.btn.attivo { background: var(--acc); border-color: var(--acc); color: #fff; box-shadow: 0 0 0 3px rgba(227, 100, 20, .25); }
.btn-testo { display: inline-flex; align-items: center; gap: .35rem; background: none; border: none; padding: .3rem .4rem; color: var(--pri); font: inherit; font-weight: 600; cursor: pointer; border-radius: 6px; }
.btn-testo:hover { background: var(--pri-ch); }
.btn-icona { display: inline-flex; align-items: center; justify-content: center; width: 36px; height: 36px; border: 1px solid var(--bordo-sc); background: #fff; border-radius: 9px; color: var(--testo); cursor: pointer; }
.btn-icona:hover { background: #eef3f5; }

.campo { width: 100%; padding: .55rem .7rem; border: 1px solid var(--bordo-sc); border-radius: 9px; font: inherit; background: #fff; color: var(--testo); }
.campo:focus { outline: none; border-color: var(--pri); box-shadow: 0 0 0 3px rgba(14, 90, 107, .18); }
.campo.corto { max-width: 11rem; } textarea.campo { resize: vertical; }
.campo.titolo-modifica { font-size: 1.2rem; font-weight: 700; padding: .3rem .5rem; border-color: transparent; background: transparent; }
.campo.titolo-modifica:hover { border-color: var(--bordo); background: #fff; }
.etichetta { display: block; font-weight: 600; font-size: .88rem; margin-bottom: .7rem; color: #2a3f49; }
.etichetta > .campo, .etichetta > select, .etichetta > input { margin-top: .25rem; font-weight: 400; }
.errore-campo { color: var(--rosso); font-size: .88rem; margin: .3rem 0; }
.azioni { display: flex; justify-content: flex-end; gap: .6rem; margin-top: 1rem; flex-wrap: wrap; } .azioni.sinistra { justify-content: flex-start; }
.riga-2 { display: grid; grid-template-columns: 1fr 1fr; gap: .9rem; } .riga-2 > * { min-width: 0; }
.riga-inline { display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; } .riga-inline > .campo { flex: 1; min-width: 12rem; width: auto; }
.riga-spinner, .caricamento { display: flex; align-items: center; gap: .6rem; color: var(--muted); padding: .8rem 0; }
.spinner { width: 1.05em; height: 1.05em; border: 2.5px solid #c5d3d9; border-top-color: var(--pri); border-radius: 50%; display: inline-block; animation: gira .8s linear infinite; flex: none; }
.spinner.grande { width: 2rem; height: 2rem; border-width: 3.5px; }
@keyframes gira { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .spinner { animation-duration: 2.5s; } }
div.vuoto { text-align: center; color: var(--muted); padding: 1.6rem 1rem; border: 1px dashed var(--bordo-sc); border-radius: var(--r); }
div.vuoto strong { display: block; color: var(--testo); margin-bottom: .3rem; }
.link-est .ico { margin-left: .25em; vertical-align: -2px; }
.ico { flex: none; vertical-align: middle; }

.chip { display: inline-flex; align-items: center; padding: .12rem .6rem; border-radius: 999px; font-size: .78rem; font-weight: 700; white-space: nowrap; }
.chip-neutro { background: #e6edf0; color: #3b4f5a; }
.esito-att { background: #fde3e3; color: #9c1c1c; } .esito-disc { background: #fff0d1; color: #8a5a00; }
.esito-ben { background: #e5eef2; color: #2d4f5c; } .esito-nes { background: #eceff1; color: #6b7a83; }
.chips { display: flex; gap: .35rem; flex-wrap: wrap; margin-top: .2rem; }

.banda { padding: .7rem .95rem; border-radius: 10px; margin: .6rem 0; border-left: 5px solid var(--bordo-sc); background: #eef3f5; }
.banda.giallo { background: #fff6dc; border-color: #e2b300; } .banda.arancio { background: #ffeadb; border-color: var(--arancio); }
.banda.rosso { background: #fde7e7; border-color: var(--rosso); } .banda.verde { background: #e6f4e7; border-color: var(--verde); } .banda.neutro { background: #eaf1f4; border-color: #8fb1bd; }

/* ---------- finestre e messaggi ---------- */
dialog { border: none; border-radius: 14px; padding: 0; box-shadow: 0 18px 60px rgba(0, 0, 0, .35); max-width: min(92vw, 520px); width: 100%; color: var(--testo); }
dialog::backdrop { background: rgba(15, 30, 38, .55); }
#dialogo.larga { max-width: min(96vw, 1000px); }
.dlg { padding: 1.3rem 1.4rem; max-height: 88vh; overflow: auto; }
#lightbox { max-width: 96vw; background: #10181d; }
#lightbox .lb { padding: .8rem; } #lightbox .lb-barra { display: flex; align-items: center; gap: .6rem; color: #fff; margin-bottom: .6rem; }
#lightbox img { max-width: 100%; max-height: 80vh; display: block; margin: 0 auto; border-radius: 6px; }
#toast { position: fixed; left: 50%; bottom: 1.4rem; transform: translate(-50%, 30px); background: #243942; color: #fff; padding: .7rem 1.1rem; border-radius: 10px; opacity: 0; pointer-events: none; transition: opacity .2s, transform .2s; max-width: min(92vw, 560px); z-index: 100; box-shadow: 0 6px 24px rgba(0, 0, 0, .3); }
#toast.visibile { opacity: 1; transform: translate(-50%, 0); } #toast.errore { background: #9c1c1c; } #toast.ok { background: #1f6b3a; }

/* ---------- utenti ---------- */
.utenti-griglia { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 1rem; margin-top: 1rem; }
.utente-card { position: relative; background: #fff; border: 2px solid var(--bordo); border-radius: var(--r); box-shadow: var(--ombra); display: flex; flex-direction: column; }
.utente-card.corrente { border-color: var(--pri); }
.utente-card.nuovo { border-style: dashed; background: transparent; box-shadow: none; padding: 1rem; justify-content: center; }
.utente-apri { display: flex; align-items: center; gap: .8rem; padding: 1rem; background: none; border: none; font: inherit; text-align: left; cursor: pointer; color: inherit; border-radius: var(--r); }
.utente-apri:hover { background: #f4f8f9; }
.utente-info { display: flex; flex-direction: column; min-width: 0; } .utente-info strong { font-size: 1.05rem; overflow-wrap: anywhere; }
.sotto { display: block; font-size: .84rem; color: var(--muted); }
.utente-azioni { display: flex; justify-content: flex-end; gap: .2rem; padding: 0 .6rem .5rem; }
.nota-privacy { font-size: .86rem; color: var(--muted); max-width: 70ch; }

/* ---------- mappa del corpo ---------- */
.mappa-layout { display: grid; grid-template-columns: minmax(380px, 1.05fr) minmax(360px, 1fr); gap: 1.1rem; align-items: start; }
.mappa-scheda { position: sticky; top: 4.4rem; padding: .8rem; margin-bottom: 0; }
.mappa-barra { display: flex; align-items: center; gap: .5rem; margin-bottom: .6rem; flex-wrap: wrap; }
.mappa-hint { color: var(--muted); font-size: .8rem; }
.mappa-box { width: 100%; height: calc(100vh - 17rem); min-height: 430px; max-height: 860px; background: radial-gradient(ellipse at 50% 35%, #ffffff, #eaf0f3); border-radius: 10px; border: 1px solid var(--bordo); overflow: hidden; }
.regione-etichetta { margin-top: .5rem; font-weight: 600; text-align: center; color: var(--pri); min-height: 1.5em; }
.legenda { display: flex; gap: .4rem 1rem; flex-wrap: wrap; font-size: .8rem; color: var(--muted); margin-top: .35rem; justify-content: center; }
.legenda span { display: inline-flex; align-items: center; gap: .35rem; } .lato-nota { width: 100%; text-align: center; }
.pallino { display: inline-block; width: 12px; height: 12px; border-radius: 50%; border: 2px solid var(--acc); } .pallino.pieno { background: var(--acc); } .pallino.vuoto { background: #fff; } .pallino.rosso { background: var(--rosso); border-color: var(--rosso); }
.pannello { min-width: 0; }
.corpo-svg { width: 100%; height: 100%; display: block; touch-action: none; user-select: none; }
.corpo-svg .contorno path { fill: #51606b; stroke: #51606b; stroke-width: 5; stroke-linejoin: round; }
.corpo-svg .dettagli path, .corpo-svg .dettagli ellipse { stroke: rgba(60, 40, 30, .22); stroke-width: 1.6; stroke-linecap: round; }
.corpo-svg .dettagli .det-pieno { fill: rgba(60, 40, 30, .22); stroke: none; }
.corpo-svg .dettagli .det-viso { stroke: rgba(60, 40, 30, .16); }
.corpo-svg .regioni polygon { fill: transparent; stroke: none; }
.corpo-svg .regioni polygon:hover { fill: rgba(14, 90, 107, .22); }
.corpo-svg .etichette text { font: 600 13px var(--font); fill: #51606b; letter-spacing: .12em; }
.corpo-svg .etichette .lato { font-size: 13px; fill: var(--pri); }
.marc { cursor: pointer; } .marc .area { fill: transparent; } .marc .punto { fill: var(--acc); stroke: #fff; stroke-width: 2.5; }
.marc .num { font: 700 10px var(--font); fill: #fff; pointer-events: none; }
.marc.sel .alone { fill: rgba(227, 100, 20, .25); stroke: var(--acc); stroke-width: 1.5; }
.marc.vuoto .punto { fill: #fff; stroke: var(--acc); stroke-width: 2.5; } .marc.vuoto .num { fill: var(--acc); }
.marc.flag .punto { fill: var(--rosso); stroke: #fff; } .marc.flag.vuoto .punto { fill: #fff; stroke: var(--rosso); } .marc.flag.vuoto .num { fill: var(--rosso); }
.marc.bozza .punto { fill: rgba(227, 100, 20, .35); stroke: var(--acc); stroke-dasharray: 3 2; } .marc.bozza .mirino { stroke: var(--acc); stroke-width: 2; fill: none; }
.marc .nome { font: 600 11px var(--font); fill: #222; paint-order: stroke; stroke: #fff; stroke-width: 3; pointer-events: none; }
.fantasma circle { fill: rgba(227, 100, 20, .25); stroke: var(--acc); stroke-width: 1.6; } .fantasma path { stroke: var(--acc); stroke-width: 1.6; fill: none; }
svg.aggiunta { cursor: crosshair; } svg.trascina { cursor: grabbing; }

/* ---------- elenco dei nei e dettaglio ---------- */
.testa-lista { display: flex; align-items: center; justify-content: space-between; gap: .6rem; margin-bottom: .6rem; flex-wrap: wrap; } .testa-lista > h2, .testa-lista > h3 { margin: 0; }
.passi { padding-left: 1.4rem; } .passi li { margin: .5em 0; }
.neo-elenco { display: flex; flex-direction: column; gap: .55rem; }
.neo-card { display: flex; align-items: center; gap: .7rem; text-align: left; width: 100%; padding: .55rem .7rem; background: #fff; border: 1px solid var(--bordo); border-radius: 11px; cursor: pointer; font: inherit; color: inherit; }
.neo-card:hover { border-color: var(--pri); box-shadow: 0 2px 10px rgba(14, 90, 107, .14); }
.neo-num { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 50%; background: var(--acc); color: #fff; font-weight: 700; font-size: .85rem; flex: none; border: 2px solid var(--acc); }
.neo-num.vuoto { background: #fff; color: var(--acc); } .neo-num.rosso { background: var(--rosso); border-color: var(--rosso); color: #fff; }
.neo-num.grande { width: 38px; height: 38px; font-size: 1.1rem; }
.neo-thumb { width: 56px; height: 56px; border-radius: 9px; object-fit: cover; background: #e6edf0; flex: none; display: inline-flex; align-items: center; justify-content: center; color: #8ca0aa; }
.neo-info { display: flex; flex-direction: column; min-width: 0; flex: 1; } .neo-info strong { overflow-wrap: anywhere; }
.archiviati { margin-top: .9rem; } .archiviati summary { cursor: pointer; color: var(--muted); font-weight: 600; }
.riga-arch { display: flex; align-items: center; justify-content: space-between; gap: .5rem; padding: .3rem 0; border-bottom: 1px solid #edf1f3; }
.neo-testa { margin-bottom: .6rem; } .neo-titolo { display: flex; align-items: center; gap: .6rem; margin-bottom: .6rem; } .neo-titolo .campo { flex: 1; }

.striscia { display: flex; gap: .5rem; overflow-x: auto; padding: .2rem .1rem .6rem; }
.miniatura { position: relative; flex: none; width: 88px; padding: 0; border: 2px solid var(--bordo); border-radius: 10px; background: #fff; overflow: hidden; cursor: pointer; text-align: center; font: inherit; }
.miniatura img { display: block; width: 100%; height: 76px; object-fit: cover; }
.miniatura.sel { border-color: var(--acc); box-shadow: 0 0 0 3px rgba(227, 100, 20, .22); }
.miniatura .data { display: block; font-size: .72rem; padding: .15rem 0; color: var(--muted); }
.punto-esito { position: absolute; top: 5px; right: 5px; width: 13px; height: 13px; border-radius: 50%; border: 2px solid #fff; display: block; }
.punto-esito.esito-att { background: var(--rosso); } .punto-esito.esito-disc { background: #f0a500; } .punto-esito.esito-ben { background: #6b8fa0; } .punto-esito.esito-nes { background: #b6c0c6; }
.anteprima { display: block; width: 100%; padding: 0; border: 1px solid var(--bordo); border-radius: 10px; overflow: hidden; background: #10181d; cursor: zoom-in; }
.anteprima img { display: block; width: 100%; max-height: 420px; object-fit: contain; }
.foto-meta { display: flex; flex-direction: column; gap: .15rem; margin: .6rem 0; font-size: .92rem; } .delta { color: var(--muted); font-size: .84rem; }
.azioni-foto { display: flex; gap: .6rem; flex-wrap: wrap; }

.form-foto > summary { cursor: pointer; font-weight: 700; color: var(--pri); display: flex; align-items: center; gap: .4rem; }
.form-corpo { margin-top: .8rem; }
.drop { display: block; border: 2px dashed var(--bordo-sc); border-radius: 12px; background: #f7fafb; padding: 1rem; text-align: center; cursor: pointer; margin-bottom: .9rem; }
.drop:hover, .drop.sopra { border-color: var(--pri); background: var(--pri-ch); }
.drop-testo { display: flex; flex-direction: column; align-items: center; gap: .3rem; color: var(--muted); }
.drop-img { max-width: 100%; max-height: 220px; border-radius: 8px; }
.spunta { display: flex; align-items: center; gap: .45rem; font-weight: 400; font-size: .86rem; margin-top: .35rem; } .spunta.grande { font-size: .95rem; font-weight: 600; margin: .5rem 0 .8rem; } .spunta input { width: auto; margin: 0; }
.consigli { margin: .5rem 0 .9rem; font-size: .9rem; } .consigli summary { cursor: pointer; color: var(--pri); font-weight: 600; }

.grafico { width: 100%; height: auto; max-width: 560px; display: block; }
.grafico .gl { stroke: #e1e8ec; stroke-width: 1; } .grafico .gt, .grafico-uv .gt { font: 11px var(--font); fill: var(--muted); }
.grafico .g6 { stroke: var(--rosso); stroke-width: 1.2; stroke-dasharray: 5 4; } .g6t { fill: var(--rosso) !important; }
.grafico .gline { fill: none; stroke: var(--pri); stroke-width: 2.4; stroke-linejoin: round; } .grafico .gp { fill: #fff; stroke: var(--pri); stroke-width: 2.4; }
.abcde { list-style: none; padding: 0; } .abcde li { display: flex; gap: .7rem; align-items: baseline; margin: .55em 0; }
.abcde b { flex: none; width: 1.8rem; height: 1.8rem; border-radius: 50%; background: var(--pri); color: #fff; display: inline-flex; align-items: center; justify-content: center; }

.confronto-area { margin: .8rem 0; } .confronto-coppia { display: grid; grid-template-columns: 1fr 1fr; gap: .6rem; margin: 0; }
.confronto-coppia figure { margin: 0; } .confronto-coppia img { width: 100%; border-radius: 9px; display: block; background: #10181d; }
.confronto-coppia figcaption, .didascalie { font-size: .84rem; color: var(--muted); text-align: center; margin-top: .3rem; }
.sovrapposte { position: relative; max-width: 560px; margin: 0 auto; overflow: hidden; border-radius: 9px; }
.sovrapposte img { display: block; width: 100%; } .sovrapposte .sopra { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }

/* ---------- analisi ---------- */
.analisi-attesa { display: flex; align-items: center; gap: .8rem; } .log { margin: .6rem 0 0; padding: .6rem .8rem; background: #1b2a31; color: #cfe2e8; border-radius: 9px; font: 12px/1.45 Consolas, monospace; max-height: 190px; overflow: auto; white-space: pre-wrap; }
.sintesi-testa { display: flex; align-items: center; gap: .7rem; flex-wrap: wrap; margin-bottom: .6rem; }
.giudizio { padding: .75rem .95rem; border-radius: 10px; background: #f3f6f8; border-left: 5px solid var(--pri); }
.metodo { border: 1px solid var(--bordo); border-radius: 11px; padding: .75rem .9rem; margin: .7rem 0; background: #fcfdfd; }
.metodo-testa { display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; margin-bottom: .3rem; } .metodo-titolo { color: var(--muted); flex: 1; min-width: 10rem; }
.ha-detto { margin: .4rem 0; } .modelli { list-style: none; padding: 0; margin: .4rem 0 0; font-size: .86rem; }
.modelli li { display: grid; grid-template-columns: minmax(9rem, 12rem) 1fr; column-gap: .8rem; padding: .3rem 0; border-top: 1px solid #edf1f3; } .modelli li > :nth-child(3) { grid-column: 2; } .mod-nome { font-weight: 600; }
.modelli li.nota-metodo { display: block; }
.nota-metodo { color: #7a5a00; background: #fff8e1; padding: .35rem .55rem !important; border-radius: 7px; border: none !important; }
.nota-metodo.errore { color: #8a1c1c; background: #fdecec; }
.rapporto { white-space: pre-wrap; font: 12px/1.45 Consolas, monospace; background: #f3f6f8; padding: .8rem; border-radius: 9px; overflow: auto; max-height: 360px; }

/* ---------- profilo ---------- */
.profilo-layout { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 1.1rem; align-items: start; }
.riepilogo-profilo { position: sticky; top: 4.4rem; }
.salvataggio { font-size: .84rem; color: var(--muted); } .salvataggio.ok { color: var(--verde); }
.campo-gruppo { margin-bottom: 1rem; } .campo-blocco { margin-bottom: 1.1rem; } .campo-titolo { font-weight: 600; font-size: .9rem; margin-bottom: .4rem; display: block; }
.pillola { padding: .4rem .85rem; border-radius: 999px; border: 1px solid var(--bordo-sc); background: #fff; cursor: pointer; font: inherit; font-size: .9rem; margin: 0 .3rem .4rem 0; }
.pillola:hover { border-color: var(--pri); } .pillola.sel { background: var(--pri); border-color: var(--pri); color: #fff; font-weight: 600; }
.fototipi { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: .6rem; margin-bottom: 1rem; }
.fototipo { display: flex; flex-direction: column; align-items: flex-start; gap: .25rem; text-align: left; padding: .6rem .7rem; border: 2px solid var(--bordo); border-radius: 11px; background: #fff; cursor: pointer; font: inherit; color: inherit; }
.fototipo:hover { border-color: var(--pri); } .fototipo.sel { border-color: var(--acc); box-shadow: 0 0 0 3px rgba(227, 100, 20, .2); }
.swatch { display: block; width: 100%; height: 22px; border-radius: 6px; border: 1px solid rgba(0, 0, 0, .12); }
.contatore-riga { display: flex; align-items: center; justify-content: space-between; gap: .8rem; padding: .35rem 0; border-bottom: 1px solid #edf1f3; }
.contatore { display: inline-flex; align-items: center; gap: .3rem; } .cont-val { min-width: 2ch; text-align: center; font-weight: 700; }
.spunte-griglia { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: .1rem 1rem; }
.fattori { list-style: none; padding: 0; } .fattori li { padding: .35rem 0; border-bottom: 1px solid #edf1f3; }
.eta-calcolata { font-weight: 600; color: var(--pri); }

/* ---------- letteratura e genetica ---------- */
.azione-scan { margin: 0 0 1rem; } .ris-libera { margin-top: .8rem; }
.sez { border-top: 1px solid #edf1f3; padding: .8rem 0 .2rem; } .sez:first-of-type { border-top: none; padding-top: 0; }
.articolo { padding: .7rem 0; border-bottom: 1px solid #edf1f3; } .articolo:last-child { border-bottom: none; }
.art-titolo { font-weight: 700; text-decoration: none; display: inline-block; margin-bottom: .15rem; } .art-titolo:hover { text-decoration: underline; }
.art-meta { color: var(--muted); font-size: .85rem; margin-bottom: .25rem; }
.abstract { margin: .4rem 0; } .abstract summary { cursor: pointer; color: var(--pri); font-weight: 600; font-size: .9rem; } .abstract p { margin: .4rem 0; font-size: .92rem; }
.criteri { list-style: none; padding: 0; } .criteri li, .stato-lista li { display: flex; gap: .7rem; padding: .55rem 0; border-bottom: 1px solid #edf1f3; }
.stato-lista { list-style: none; padding: 0; }
.esito-criterio { flex: none; width: 24px; height: 24px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; background: #e6edf0; color: var(--muted); }
.criteri li.si .esito-criterio, .stato-lista li.si .esito-criterio { background: #dcefdc; color: var(--verde); } .criteri li.no .esito-criterio { background: #eceff1; } .stato-lista li.no .esito-criterio { background: #fff0d1; color: #8a5a00; }
.punti li { margin: .4em 0; } .fonti { font-size: .88rem; } .fonti li { margin: .4em 0; }
.tabella-scroll { overflow-x: auto; } .tabella { width: 100%; border-collapse: collapse; font-size: .9rem; }
.tabella th, .tabella td { text-align: left; vertical-align: top; padding: .6rem .6rem; border-bottom: 1px solid #e6ecef; } .tabella th { background: #f3f6f8; font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
.gene-ris { margin-top: .5rem; } .gene-conta strong { color: var(--pri); }

/* ---------- indice UV e impostazioni ---------- */
.uv-posizione { display: flex; align-items: center; gap: .7rem; color: var(--pri); } .uv-posizione strong { color: var(--testo); }
.citta-elenco { display: flex; flex-direction: column; gap: .35rem; margin-top: .6rem; align-items: flex-start; } .citta-voce { justify-content: flex-start; }
.uv-verdetto { display: flex; align-items: center; justify-content: space-between; gap: 1.2rem; flex-wrap: wrap; border-left: 8px solid var(--bordo-sc); }
.uv-verdetto.uv-verde { border-left-color: #3f9c35; background: #f2faf1; } .uv-verdetto.uv-giallo { border-left-color: #e8c400; background: #fffbe8; }
.uv-verdetto.uv-arancio { border-left-color: #f28c00; background: #fff4e5; } .uv-verdetto.uv-rosso { border-left-color: #d9261c; background: #fdeeed; }
.uv-titolo h2 { margin-bottom: .2rem; } .uv-titolo p { margin: 0; }
.uv-numeri { display: flex; gap: 1.4rem; flex-wrap: wrap; } .uv-num { display: flex; align-items: center; gap: .65rem; }
.uv-val { display: inline-flex; align-items: center; justify-content: center; min-width: 3.4rem; height: 3.4rem; padding: 0 .5rem; border-radius: 14px; font-size: 1.6rem; font-weight: 800; }
.grafico-uv { width: 100%; height: auto; display: block; } .grafico-uv .gl { stroke: #e1e8ec; stroke-width: 1; } .grafico-uv .gline { stroke: #8a97a0; stroke-width: 1.3; fill: none; }
.legenda-uv { display: flex; gap: .4rem; flex-wrap: wrap; margin-bottom: .6rem; }
.interruttore { display: flex; gap: .7rem; align-items: flex-start; cursor: pointer; margin-bottom: .6rem; } .interruttore input { width: 1.2rem; height: 1.2rem; margin-top: .2rem; flex: none; }
.prova-esito { margin-top: .6rem; }

/* ---------- scheda per il dermatologo (solo stampa) ---------- */
#stampa { display: none; }
@media print {
  @page { size: A4; margin: 14mm; }
  body > *:not(#stampa) { display: none !important; }
  body { background: #fff; display: block; color: #000; font-size: 10.5pt; }
  #stampa { display: block !important; }
  .st-testata { display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 2px solid #0e5a6b; padding-bottom: 6pt; margin-bottom: 10pt; }
  .st-testata h1 { margin: 0; font-size: 18pt; } .st-sotto { color: #555; font-size: 9pt; }
  .st-profilo dl { display: grid; grid-template-columns: max-content 1fr; gap: 2pt 12pt; margin: 4pt 0 8pt; } .st-profilo dt { font-weight: 700; } .st-profilo dd { margin: 0; }
  .mappa-stampa { width: 100%; max-width: 360pt; height: auto; display: block; margin: 0 auto; max-height: 330pt; }
  .mappa-stampa .contorno path { fill: #555; stroke: #555; } .st-punto { fill: #e36414; stroke: #fff; stroke-width: 2; } .st-num { font: 700 19px sans-serif; fill: #fff; }
  .mappa-stampa .regioni { display: none; }
  .st-neo { break-inside: avoid; page-break-inside: avoid; border-top: 1px solid #999; padding-top: 6pt; margin-top: 10pt; }
  .st-neo h3 { margin: 0 0 4pt; font-size: 12pt; } .st-badge { display: inline-block; min-width: 18pt; text-align: center; background: #e36414; color: #fff; border-radius: 9pt; padding: 0 4pt; font-size: 10pt; }
  .st-foto { display: flex; flex-wrap: wrap; gap: 6pt; } .st-foto figure { margin: 0; width: 120pt; } .st-foto img { width: 120pt; height: 100pt; object-fit: cover; border: 1px solid #999; display: block; }
  .st-foto figcaption { font-size: 8pt; text-align: center; } .st-nota { font-size: 9pt; color: #444; }
  .st-avviso { margin-top: 14pt; padding-top: 6pt; border-top: 1px solid #999; font-size: 8.5pt; color: #444; }
  h2 { font-size: 12.5pt; margin: 10pt 0 4pt; }
}

/* ---------- schermi stretti ---------- */
@media (max-width: 1050px) {
  .mappa-layout, .profilo-layout { grid-template-columns: 1fr; }
  .mappa-scheda, .riepilogo-profilo { position: static; }
  .mappa-box { height: 70vh; }
}
@media (max-width: 720px) {
  #testata { flex-wrap: wrap; gap: .5rem; } .utente-cambia { display: none; } .riga-2, .confronto-coppia { grid-template-columns: 1fr; }
  #vista { padding: .8rem .6rem 1.5rem; } .voce span { display: none; } .voce { padding: .5rem; }
}

/* ---------- ritocchi ---------- */
.fototipo strong, .fototipo small { display: block; } .fototipo small { color: var(--muted); font-size: .8rem; line-height: 1.35; }
.fattori li small { display: block; color: var(--muted); font-size: .82rem; } .fattori li .chip { margin-left: .4rem; }
.spunte-griglia { margin-bottom: .9rem; }
.riga-spinner { display: flex; align-items: center; gap: .8rem; }
'''
WEB_FILES["/style.css"] = ("text/css; charset=utf-8", _WEB_STYLE_CSS.encode("utf-8"))

_WEB_UTIL_JS = r'''/* ============================================================================
   util.js - funzioni di servizio comuni a tutte le pagine
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT = { S: { utenti: [], utente: null, nei: [], imp: {}, stato: {} }, viste: {}, pulizie: [] };

  NT.$ = (s, r) => (r || document).querySelector(s);
  NT.$$ = (s, r) => Array.from((r || document).querySelectorAll(s));

  /* Crea elementi senza mai interpretare il testo come HTML (cosi' nomi e note degli utenti sono sicuri). */
  NT.h = function h(tag, attrs, ...figli) {
    const e = document.createElement(tag);
    for (const k in (attrs || {})) {
      const v = attrs[k];
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') e.className = v;
      else if (k === 'dataset') Object.assign(e.dataset, v);
      else if (k === 'style' && typeof v === 'object') Object.assign(e.style, v);
      else if (k.slice(0, 2) === 'on' && typeof v === 'function') e.addEventListener(k.slice(2), v);
      else if (k === 'value' || k === 'checked' || k === 'selected' || k === 'disabled' || k === 'indeterminate') e[k] = v;
      else if (v === true) e.setAttribute(k, '');
      else e.setAttribute(k, v);
    }
    (function aggiungi(lista) {
      for (const f of lista) {
        if (f === null || f === undefined || f === false) continue;
        if (Array.isArray(f)) aggiungi(f);
        else if (f instanceof Node) e.appendChild(f);
        else e.appendChild(document.createTextNode(String(f)));
      }
    })(figli);
    return e;
  };
  const h = NT.h;

  /* Svuota un elemento e lo riempie con elementi, testi, liste (anche annidate); ignora null e false. */
  NT.riempi = function (el, ...figli) {
    const frag = document.createDocumentFragment();
    (function aggiungi(lista) {
      for (const f of lista) {
        if (f === null || f === undefined || f === false) continue;
        if (Array.isArray(f)) aggiungi(f);
        else frag.appendChild(f instanceof Node ? f : document.createTextNode(String(f)));
      }
    })(figli);
    el.replaceChildren(frag);
    return el;
  };

  /* HTML fidato (solo SVG/icone scritti da noi, con numeri e testi gia' "escapati") */
  NT.html = function (stringa) {
    const t = document.createElement('template');
    t.innerHTML = stringa.trim();
    return t.content.firstChild;
  };
  NT.esc = t => String(t).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const ICONE = {
    mappa: '<circle cx="12" cy="5" r="2.5"/><path d="M12 8.5v6.5M6.5 10.5 12 8.5l5.5 2M9.5 21.5 12 15l2.5 6.5"/>',
    profilo: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/>',
    letteratura: '<path d="M12 6c-2-1.5-5-2-8-2v14c3 0 6 .5 8 2 2-1.5 5-2 8-2V4c-3 0-6 .5-8 2zM12 6v14"/>',
    genetica: '<path d="M6 3c0 5 12 5 12 9s-12 4-12 9"/><path d="M18 3c0 5-12 5-12 9s12 4 12 9"/><path d="M8.6 6.6h6.8M8.6 17.4h6.8"/>',
    uv: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2.2M12 19.8V22M4.9 4.9l1.6 1.6M17.5 17.5l1.6 1.6M2 12h2.2M19.8 12H22M4.9 19.1l1.6-1.6M17.5 6.5l1.6-1.6"/>',
    impostazioni: '<path d="M4 6h9M19 6h1M4 12h3M13 12h7M4 18h11M21 18h-1"/><circle cx="16" cy="6" r="2.2"/><circle cx="10" cy="12" r="2.2"/><circle cx="18" cy="18" r="2.2"/>',
    piu: '<path d="M12 5v14M5 12h14"/>', meno: '<path d="M5 12h14"/>',
    reset: '<path d="M4 12a8 8 0 1 0 2.6-5.9M4 4v4.5h4.5"/>',
    stampa: '<path d="M7 9V3h10v6M7 17H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2"/><path d="M7 14h10v7H7z"/>',
    foto: '<path d="M4 8h3l1.6-2.5h6.8L17 8h3v11H4z"/><circle cx="12" cy="13" r="3.6"/>',
    cestino: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    mirino: '<circle cx="12" cy="12" r="7"/><path d="M12 2v5M12 17v5M2 12h5M17 12h5"/>',
    archivio: '<path d="M3 5h18v4H3zM5 9v10h14V9M10 13h4"/>',
    freccia: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    esci: '<path d="M9 4H5v16h4M16 8l4 4-4 4M20 12H9"/>',
    avviso: '<path d="M12 3 2 20h20zM12 10v5M12 17.6v.2"/>',
    ok: '<path d="M5 12.5 10 17.5 19 7"/>',
    posizione: '<path d="M12 21s-7-6.2-7-11.3A7 7 0 0 1 19 9.7C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.7" r="2.4"/>',
    cerca: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
    esterno: '<path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6"/>',
    confronta: '<rect x="3" y="5" width="8" height="14" rx="1.5"/><rect x="13" y="5" width="8" height="14" rx="1.5"/>',
  };
  NT.icona = (nome, dim) => NT.html('<svg class="ico" viewBox="0 0 24 24" width="' + (dim || 18) + '" height="' + (dim || 18) +
    '" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (ICONE[nome] || '') + '</svg>');

  /* ---------- chiamate al programma (API) ---------- */
  NT.api = async function (metodo, url, corpo, opz) {
    opz = opz || {};
    const init = { method: metodo, headers: { 'X-NeoTracker': '1' } };
    if (opz.raw) { init.body = opz.raw; init.headers['Content-Type'] = opz.tipo || 'application/octet-stream'; }
    else if (corpo !== undefined && corpo !== null) { init.body = JSON.stringify(corpo); init.headers['Content-Type'] = 'application/json'; }
    let r;
    try { r = await fetch(url, init); }
    catch (e) { throw new Error('Non riesco a contattare NeoTracker. Il programma potrebbe essere stato chiuso: riaprilo dall\'icona sul Desktop.'); }
    const t = await r.text();
    let d = null;
    try { d = t ? JSON.parse(t) : null; } catch (e) { /* risposta non JSON */ }
    if (!r.ok) { const er = new Error((d && d.errore) || ('Errore ' + r.status)); er.codice = r.status; throw er; }
    return d;
  };
  NT.get = (url) => NT.api('GET', url);

  /* ---------- messaggi a comparsa ---------- */
  let timerToast = null;
  NT.toast = function (testo, tipo) {
    const t = NT.$('#toast');
    t.className = 'visibile ' + (tipo || 'info');
    t.textContent = testo;
    clearTimeout(timerToast);
    timerToast = setTimeout(() => { t.className = ''; }, tipo === 'errore' ? 7000 : 3500);
  };
  NT.errore = (e) => { console.error(e); NT.toast(e && e.message ? e.message : String(e), 'errore'); };

  /* ---------- finestre di dialogo ---------- */
  NT.apriDialogo = function (contenuto, larga) {
    const d = NT.$('#dialogo');
    d.className = larga ? 'larga' : '';
    d.replaceChildren(h('div', { class: 'dlg' }, contenuto));
    if (!d.open) d.showModal();
    return d;
  };
  NT.chiudiDialogo = () => { const d = NT.$('#dialogo'); if (d.open) d.close(); };

  NT.conferma = function (titolo, testo, opz) {
    opz = opz || {};
    return new Promise(res => {
      let fatto = false;
      const fine = v => { if (!fatto) { fatto = true; res(v); } NT.chiudiDialogo(); };
      const campo = opz.scrivi ? h('input', { type: 'text', class: 'campo', autocomplete: 'off', placeholder: opz.scrivi,
        oninput: () => { ok.disabled = campo.value.trim() !== opz.scrivi; } }) : null;
      const ok = h('button', { class: 'btn ' + (opz.pericolo ? 'btn-pericolo' : 'btn-pri'), disabled: !!opz.scrivi, onclick: () => fine(campo ? campo.value.trim() : true) }, opz.si || 'Conferma');
      const d = NT.apriDialogo(h('div', {},
        h('h3', {}, titolo), h('p', {}, testo),
        opz.scrivi ? h('label', { class: 'etichetta' }, 'Per confermare scrivi: ', h('strong', {}, opz.scrivi)) : null, campo,
        h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => fine(false) }, 'Annulla'), ok)));
      d.addEventListener('close', () => fine(false), { once: true });
      if (campo) campo.focus();
    });
  };

  document.addEventListener('click', ev => {                  // clic fuori dalla finestra = chiude
    const d = ev.target;
    if (d instanceof HTMLDialogElement && d.open) {
      const r = d.getBoundingClientRect();
      if (ev.clientX < r.left || ev.clientX > r.right || ev.clientY < r.top || ev.clientY > r.bottom) d.close();
    }
  });

  /* ---------- date e varie ---------- */
  NT.fmtData = iso => { if (!iso) return ''; const [a, m, g] = iso.slice(0, 10).split('-'); return g + '/' + m + '/' + a; };
  NT.oggiISO = () => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
  NT.dataDaMs = ms => { const d = new Date(ms); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
  NT.giorniTra = (a, b) => Math.round((new Date(b + 'T12:00:00') - new Date(a + 'T12:00:00')) / 86400000);
  NT.fraseGiorni = g => g === null || g === undefined ? '' : g <= 0 ? 'oggi' : g === 1 ? 'ieri' : g < 60 ? g + ' giorni fa' : g < 700 ? Math.round(g / 30.4) + ' mesi fa' : Math.round(g / 365) + ' anni fa';
  NT.num = (n, dec) => (n === null || n === undefined) ? '' : Number(n).toFixed(dec === undefined ? 1 : dec).replace('.', ',');
  NT.perc = v => v === null || v === undefined ? '' : (v * 100).toFixed(v >= 0.995 || v < 0.01 ? 1 : 0).replace('.', ',') + '%';
  NT.ls = {
    leggi: k => { try { return localStorage.getItem(k); } catch (e) { return null; } },
    scrivi: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* non disponibile */ } },
  };
  NT.debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

  /* spinner e segnaposto */
  NT.caricamento = (testo) => h('div', { class: 'caricamento' }, h('span', { class: 'spinner' }), testo || 'Caricamento…');
  NT.vuoto = (titolo, testo) => h('div', { class: 'vuoto' }, h('strong', {}, titolo), testo ? h('p', {}, testo) : null);

  /* Etichetta dell'esito dell'analisi (colori volutamente prudenti: "benigno" non e' mai verde rassicurante) */
  NT.ESITI = {
    attenzione: { testo: 'Da attenzionare', cls: 'esito-att' },
    discordante: { testo: 'Metodi in disaccordo', cls: 'esito-disc' },
    benigno: { testo: 'Nessun allarme dai modelli', cls: 'esito-ben' },
    nessuno: { testo: 'Nessun risultato', cls: 'esito-nes' },
  };
  NT.chipEsito = (esito) => { const e = NT.ESITI[esito]; return e ? h('span', { class: 'chip ' + e.cls }, e.testo) : null; };

  NT.link = (url, testo) => h('a', { href: url, target: '_blank', rel: 'noopener noreferrer', class: 'link-est' }, testo, NT.icona('esterno', 13));

  /* Prende un file immagine e restituisce (come Blob JPEG) un quadrato "lato x lato" ritagliato al centro.
     Il JPEG nuovo non contiene i metadati dell'originale (posizione GPS, modello di fotocamera...). */
  NT.ridimensionaQuadrato = function (file, lato) {
    return new Promise((res, rej) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        try {
          const w = img.naturalWidth, alt = img.naturalHeight;
          if (!w || !alt) throw new Error('vuota');
          const q = Math.min(w, alt), sx = (w - q) / 2, sy = (alt - q) / 2;
          const c = document.createElement('canvas');
          c.width = c.height = lato;
          const g = c.getContext('2d');
          g.fillStyle = '#ffffff'; g.fillRect(0, 0, lato, lato);          // le parti trasparenti diventano bianche
          g.imageSmoothingQuality = 'high';
          g.drawImage(img, sx, sy, q, q, 0, 0, lato, lato);
          c.toBlob(b => b ? res(b) : rej(new Error('Non riesco a ridurre questa immagine.')), 'image/jpeg', 0.88);
        } catch (e) { rej(new Error('Non riesco a leggere questa immagine. Prova con un JPG o un PNG.')); }
        finally { URL.revokeObjectURL(url); }
      };
      img.onerror = () => { URL.revokeObjectURL(url); rej(new Error('Non riesco a leggere questa immagine. Prova con un JPG o un PNG.')); };
      img.src = url;
    });
  };

  /* Avviso iniziale (primo avvio): NeoTracker non e' un dispositivo medico. Va accettato per continuare. */
  NT.mostraAvvertenze = function () {
    const spunta = h('input', { type: 'checkbox', id: 'ck-avvertenze' });
    const ok = h('button', { class: 'btn btn-pri', disabled: true, onclick: async () => {
      try {
        NT.S.imp = await NT.api('PUT', '/api/impostazioni', { avvertenze_accettate: NT.S.stato.avvertenze_versione });
        NT.chiudiDialogo();
      } catch (e) { NT.errore(e); }
    } }, 'Accetto e continuo');
    spunta.addEventListener('change', () => { ok.disabled = !spunta.checked; });
    const d = NT.apriDialogo(h('div', { class: 'avvertenze' },
      h('h3', {}, 'Prima di cominciare'),
      h('p', {}, h('strong', {}, 'NeoTracker non è un dispositivo medico e non fa diagnosi. '),
        'È uno strumento personale per organizzare le foto dei tuoi nei e confrontare nel tempo i risultati di alcuni modelli di ricerca. Non è certificato né approvato da alcuna autorità sanitaria.'),
      h('ul', {},
        h('li', {}, 'I risultati sono stime sperimentali e possono sbagliare in entrambe le direzioni: un esito rassicurante non esclude un melanoma, un esito di attenzione non significa che ci sia.'),
        h('li', {}, 'Un neo che cambia (forma, bordi, colore, dimensioni), sanguina, prude o ti preoccupa va mostrato a un dermatologo, qualunque cosa dica l\'app. Il controllo periodico dal dermatologo resta insostituibile.'),
        h('li', {}, 'Le informazioni su rischio, letteratura e genetica sono divulgative e non sostituiscono la consulenza di un medico o di un genetista.'),
        h('li', {}, 'I dati (anche di salute) restano su questo computer. Escono solo le richieste che attivi tu: indice UV (coordinate approssimate), ricerche su PubMed (solo i termini cercati) e, solo se lo attivi, l\'invio della foto a SkinSense.'),
        h('li', {}, 'Se inserisci dati o foto di altre persone, assicurati di avere il loro consenso.')),
      h('label', { class: 'spunta grande' }, spunta, ' Ho letto e capito queste avvertenze'),
      h('div', { class: 'azioni' },
        h('button', { class: 'btn', onclick: () => { NT.api('POST', '/api/chiudi').catch(() => {}); NT.battitoAttivo = false; if (NT.presenza) NT.presenza.close(); document.title = 'NeoTracker chiuso'; NT.chiudiDialogo(); } }, 'Esci dal programma'),
        ok)));
    d.addEventListener('cancel', ev => ev.preventDefault());           // il tasto Esc non salta l'avviso
    return d;
  };

  /* pulizie da eseguire quando si cambia pagina (timer, osservatori...) */
  NT.alCambioPagina = fn => NT.pulizie.push(fn);
})();
'''
WEB_FILES["/util.js"] = ("text/javascript; charset=utf-8", _WEB_UTIL_JS.encode("utf-8"))

_WEB_V_IMPOSTAZIONI_JS = r'''/* ============================================================================
   v_impostazioni.js - fonte dell'indice UV (Open-Meteo / OpenWeather), SkinSense, email PubMed, stato dell'installazione
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  NT.viste.impostazioni = async function (cont) {
    [S.imp, S.stato] = await Promise.all([NT.get('/api/impostazioni'), NT.get('/api/stato')]);

    async function salva(parziale, messaggio) {
      try { S.imp = await NT.api('PUT', '/api/impostazioni', parziale); if (messaggio) NT.toast(messaggio, 'ok'); return true; }
      catch (e) { NT.errore(e); return false; }
    }

    /* ---------------- indice UV: fonte dei dati ---------------- */
    const esitoProva = h('div', { class: 'prova-esito', role: 'status' });
    const campoChiave = h('input', { type: 'password', class: 'campo', autocomplete: 'off', spellcheck: 'false', maxlength: 64,
      placeholder: S.imp.ha_chiave_owm ? 'Chiave salvata (' + S.imp.chiave_owm_finale + ') — scrivine una nuova per sostituirla' : 'Incolla qui la chiave (32 lettere e numeri)', 'aria-label': 'Chiave OpenWeather' });
    const sezOWM = h('section', { class: 'scheda' });
    function disegnaOWM() {
      campoChiave.placeholder = S.imp.ha_chiave_owm ? 'Chiave salvata (' + S.imp.chiave_owm_finale + ') — scrivine una nuova per sostituirla' : 'Incolla qui la chiave (32 lettere e numeri)';
      const ow = S.imp.fonte_uv === 'openweather';
      // una riga con pallino: scegliere cambia subito la fonte e ridisegna la sezione
      const scelta = (valore, titolo, desc) => h('label', { class: 'riga-inline' },
        h('input', { type: 'radio', name: 'fonte-uv', value: valore, checked: S.imp.fonte_uv === valore,
          onchange: async () => { if (await salva({ fonte_uv: valore }, 'Fonte dell\'indice UV cambiata.')) { NT.riempi(esitoProva); disegnaOWM(); } } }),
        h('span', {}, h('strong', {}, titolo), ' ', h('span', { class: 'piccolo muted' }, desc)));
      NT.riempi(sezOWM, h('h2', {}, 'Indice UV: fonte dei dati'),
        scelta('open-meteo', 'Open-Meteo (predefinita)', 'gratuita, senza account né chiave'),
        scelta('openweather', 'OpenWeather', 'facoltativa: richiede una tua chiave personale'),
        !ow ? h('p', { class: 'piccolo muted' }, 'Dati meteo e UV: ', NT.link('https://open-meteo.com/', 'Open-Meteo.com'), ' (licenza CC BY 4.0). Il servizio gratuito è per uso personale e non commerciale. ',
          'Anche la ricerca delle città usa Open-Meteo.') : null,
        ow ? h('div', { class: 'banda ' + (S.imp.ha_chiave_owm ? 'verde' : 'giallo') }, S.imp.ha_chiave_owm ? 'Chiave OpenWeather salvata (' + S.imp.chiave_owm_finale + ').' : 'Hai scelto OpenWeather ma non c\'è ancora una chiave: finché manca, il programma usa Open-Meteo.') : null,
        ow ? h('div', { class: 'riga-inline' }, campoChiave,
          h('button', { class: 'btn btn-pri', onclick: async () => { const k = campoChiave.value.trim(); if (!k) { NT.toast('Incolla prima la chiave.', 'errore'); return; } if (await salva({ openweather_key: k }, 'Chiave salvata.')) { campoChiave.value = ''; NT.riempi(esitoProva); disegnaOWM(); } } }, 'Salva'),
          S.imp.ha_chiave_owm ? h('button', { class: 'btn', onclick: provaChiave }, 'Prova la chiave') : null,
          S.imp.ha_chiave_owm ? h('button', { class: 'btn-testo pericolo', onclick: async () => { if (await NT.conferma('Rimuovere la chiave?', 'La chiave sarà cancellata da questo computer. Potrai inserirla di nuovo quando vuoi.', { si: 'Rimuovi', pericolo: true }) && await salva({ openweather_key: '' }, 'Chiave rimossa.')) { NT.riempi(esitoProva); disegnaOWM(); } } }, 'Rimuovi') : null) : null,
        ow ? esitoProva : null,
        ow ? h('details', { class: 'abstract' }, h('summary', {}, 'Come ottenere la chiave'),
          h('ol', { class: 'passi' },
            h('li', {}, 'Crea un account gratuito su ', NT.link('https://home.openweathermap.org/users/sign_up', 'openweathermap.org'), ' e conferma l\'email.'),
            h('li', {}, 'Apri la pagina «API keys» del tuo account e copia la chiave.'),
            h('li', {}, 'Iscriviti all\'abbonamento «One Call API» a pagamento per chiamata (', NT.link('https://openweathermap.org/api/one-call-4', 'pagina del servizio'), '): le prime 1.000 chiamate al giorno sono gratuite, le successive si pagano. OpenWeather può chiedere una carta di pagamento per attivarlo: controlla le condizioni sul loro sito.'),
            h('li', {}, 'Alla sottoscrizione il limite giornaliero predefinito è di 2.000 chiamate: nella scheda «Billing plans» del tuo account puoi abbassarlo a 1.000, così non spendi nulla. NeoTracker ne usa poche (al massimo 4 ogni 10 minuti, solo quando apri la pagina Indice UV).'),
            h('li', {}, 'Incolla la chiave qui sopra e premi «Prova la chiave». Dopo l\'iscrizione la chiave può impiegare qualche minuto ad attivarsi. Il programma prova prima One Call 4.0 e, se la chiave è di un abbonamento più vecchio, One Call 3.0.')),
          h('p', { class: 'piccolo muted' }, 'La chiave resta salvata solo sul tuo computer e non viene mai mostrata né inviata alla pagina web del programma: la usa il programma Python per chiamare OpenWeather.')) : null);
    }
    async function provaChiave() {
      NT.riempi(esitoProva, NT.caricamento('Provo la chiave…'));
      try { const r = await NT.api('POST', '/api/impostazioni/prova-owm'); NT.riempi(esitoProva, h('div', { class: 'banda ' + (r.ok ? 'verde' : 'rosso') }, r.messaggio)); }
      catch (e) { NT.riempi(esitoProva, h('div', { class: 'banda rosso' }, e.message)); }
    }
    disegnaOWM();

    /* ---------------- analisi delle foto ---------------- */
    const swSkin = h('input', { type: 'checkbox', id: 'sw-skin', checked: !!S.imp.usa_skinsense, onchange: async () => {
      if (swSkin.checked) {
        const ok = await NT.conferma('Inviare le foto a SkinSense?', 'SkinSense è un servizio online di terzi: le foto dei tuoi nei verrebbero inviate via internet a un server che non controlliamo. Le foto sono dati sulla tua salute. Vuoi abilitarlo?', { si: 'Sì, abilita' });
        if (!ok) { swSkin.checked = false; return; }
      }
      if (!await salva({ usa_skinsense: swSkin.checked }, swSkin.checked ? 'SkinSense abilitato.' : 'SkinSense disattivato.')) swSkin.checked = !swSkin.checked;
    } });
    const sezAnalisi = h('section', { class: 'scheda' }, h('h2', {}, 'Analisi delle foto'),
      h('label', { class: 'interruttore', for: 'sw-skin' }, swSkin, h('span', {}, h('strong', {}, 'Usa anche SkinSense (servizio online)'),
        h('span', { class: 'piccolo muted blocco' }, 'Spento per impostazione predefinita: con gli altri metodi la foto non lascia mai questo computer.'))),
      h('p', { class: 'piccolo muted' }, 'Età, sesso e fenotipo non cambiano l\'uscita delle reti neurali: servono a mostrarti i fattori di rischio, a scegliere la letteratura, a valutare i criteri di genetica e a stimare il tempo di scottatura.'));

    /* ---------------- PubMed ---------------- */
    const campoMail = h('input', { type: 'email', class: 'campo', value: S.imp.ncbi_email || '', placeholder: 'nome@esempio.it (facoltativa)', maxlength: 120, autocomplete: 'email', 'aria-label': 'Email per PubMed' });
    const sezMail = h('section', { class: 'scheda' }, h('h2', {}, 'Letteratura: PubMed'),
      h('p', {}, 'Le ricerche usano le E-utilities pubbliche di PubMed. NCBI chiede, per cortesia, un\'email di contatto: è facoltativa e viene inviata solo a PubMed.'),
      h('div', { class: 'riga-inline' }, campoMail, h('button', { class: 'btn', onclick: () => salva({ ncbi_email: campoMail.value }, 'Email salvata.') }, 'Salva')));

    /* ---------------- stato ---------------- */
    const st = S.stato;
    const sezStato = h('section', { class: 'scheda' }, h('h2', {}, 'Stato dell\'installazione'),
      h('ul', { class: 'stato-lista' }, st.progetti.map(p => h('li', { class: p.presente ? 'si' : 'no' },
        h('span', { class: 'esito-criterio' }, p.presente ? NT.icona('ok', 16) : NT.icona('avviso', 16)), h('div', {}, h('strong', {}, p.nome), h('div', { class: 'piccolo muted' }, p.dettaglio))))),
      h('div', { class: 'piccolo' }, st.batch ? ['Programma di analisi: ', h('code', {}, st.batch)] : h('span', { class: 'errore-campo' }, 'Programma di analisi (melanoma_batch.py) non trovato: le foto si salvano ma non si possono analizzare.')),
      h('div', { class: 'piccolo' }, 'Cartella dei progetti: ', h('code', {}, st.repo)),
      h('div', { class: 'piccolo' }, 'Cartella dei tuoi dati (da copiare per il backup): ', h('code', {}, st.cartella_dati)),
      st.pillow_obsoleto ? h('div', { class: 'errore-campo' }, 'La libreria Pillow è vecchia e ha problemi di sicurezza noti: aggiornala con «py -m pip install -U pillow».') : null,
      h('div', { class: 'piccolo muted' }, 'Versione ' + st.versione + (st.ha_pillow ? '' : ' · Pillow non installato: le anteprime useranno le foto originali (installa con «py -m pip install pillow»).')));

    /* ---------------- chiusura ---------------- */
    const sezEsci = h('section', { class: 'scheda' }, h('h2', {}, 'Chiudere il programma'),
      h('p', {}, 'Per chiudere NeoTracker basta chiudere questa finestra con la X in alto a destra: il programma si spegne da solo. ' +
        'Se sta ancora analizzando una foto, finisce prima l\'analisi e poi si spegne. Il pulsante qui sotto fa la stessa cosa.'),
      h('button', { class: 'btn btn-pericolo', onclick: async () => {
        if (!await NT.conferma('Chiudere NeoTracker?', 'Il programma si spegne. Un\'analisi in corso viene interrotta. I dati restano salvati.', { si: 'Chiudi il programma', pericolo: true })) return;
        NT.battitoAttivo = false;
        if (NT.presenza) NT.presenza.close();       // non deve riconnettersi mentre il programma si spegne
        try { await NT.api('POST', '/api/chiudi'); } catch (e) { /* si sta spegnendo */ }
        NT.riempi(cont, h('div', { class: 'pagina stretta' }, h('div', { class: 'scheda' }, h('h2', {}, 'NeoTracker è chiuso'), h('p', {}, 'Puoi chiudere questa finestra. Per riaprirlo usa l\'icona «NeoTracker» sul Desktop.'))));
      } }, NT.icona('esci', 18), 'Chiudi NeoTracker'));

    NT.riempi(cont, h('div', { class: 'pagina' }, h('h1', {}, 'Impostazioni'), sezOWM, sezAnalisi, sezMail, sezStato, sezEsci));
  };
})();
'''
WEB_FILES["/v_impostazioni.js"] = ("text/javascript; charset=utf-8", _WEB_V_IMPOSTAZIONI_JS.encode("utf-8"))

_WEB_V_MAPPA_JS = r'''/* ============================================================================
   v_mappa.js - mappa del corpo, elenco dei nei, storico fotografico e analisi
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h, $ = NT.$;

  const SEDI_UTILI = ['palmo della mano', 'dorso della mano', 'pianta del piede', 'dorso del piede', 'spazio tra le dita',
    'sotto l\'unghia (mano)', 'sotto l\'unghia (piede)', 'cuoio capelluto', 'orecchio', 'palpebra', 'labbro'];
  const GIORNI_PROMEMORIA = 90;

  let mappa = null, modo = 'lista', bozza = null, dett = null, fotoSel = null, pollTimer = null;
  let etichettaRegione = null, panel = null, formFotoAperto = false, sedeBozzaManuale = false;
  const inAnalisi = new Set();

  const nomiAuto = () => new Set(['fronte', 'retro'].flatMap(v => window.Corpo.regioni(v).map(r => r.nome)));
  const attivi = () => S.nei.filter(n => !n.archiviato);
  const numDi = id => { const i = attivi().findIndex(n => n.id === id); return i < 0 ? '–' : i + 1; };

  function datiMarcatori() {
    return S.nei.map(n => ({
      id: n.id, vista: n.vista, x: n.x, y: n.y, nome: n.nome, archiviato: !!n.archiviato,
      num: numDi(n.id), flag: n.ultimo_esito === 'attenzione' || n.ultimo_esito === 'discordante', senzaFoto: n.n_foto === 0,
    }));
  }
  function aggiornaMarcatori() {
    if (mappa) mappa.setNei(datiMarcatori(), modo === 'neo' && dett ? dett.nevo.id : null);
  }
  function stopPoll() { clearTimeout(pollTimer); pollTimer = null; }

  /* ======================================================================== */
  NT.viste.mappa = async function (cont) {
    await NT.ricaricaNei();
    modo = 'lista'; bozza = null; dett = null; fotoSel = null; formFotoAperto = false; sedeBozzaManuale = false;
    inAnalisi.clear();

    const btnAggiungi = h('button', { class: 'btn btn-pri', id: 'btn-aggiungi', onclick: () => attivaAggiunta(!(mappa && mappa.aggiunta)) },
      NT.icona('mirino', 18), 'Aggiungi neo');
    const suggerimento = h('span', { class: 'mappa-hint', id: 'mappa-hint' }, 'Rotella = zoom · trascina = sposta · doppio clic = ingrandisci');
    const barra = h('div', { class: 'mappa-barra' }, btnAggiungi, suggerimento,
      h('span', { class: 'spazio' }),
      h('button', { class: 'btn-icona', title: 'Riduci', onclick: () => mappa.zoomSu(1 / 1.5) }, NT.icona('meno')),
      h('button', { class: 'btn-icona', title: 'Ingrandisci', onclick: () => mappa.zoomSu(1.5) }, NT.icona('piu')),
      h('button', { class: 'btn-icona', title: 'Mostra tutto il corpo', onclick: () => mappa.reset() }, NT.icona('reset')));
    const box = h('div', { class: 'mappa-box' });
    etichettaRegione = h('div', { class: 'regione-etichetta' }, 'Passa il puntatore sul corpo per vedere la zona');
    const legenda = h('div', { class: 'legenda' },
      h('span', {}, h('i', { class: 'pallino pieno' }), 'Neo con foto'),
      h('span', {}, h('i', { class: 'pallino vuoto' }), 'Ancora nessuna foto'),
      h('span', {}, h('i', { class: 'pallino rosso' }), 'Analisi: da attenzionare'),
      h('span', { class: 'lato-nota' }, 'D = destra del paziente · S = sinistra'));
    panel = h('aside', { class: 'pannello', 'aria-live': 'polite' });
    cont.replaceChildren(h('div', { class: 'mappa-layout' }, h('section', { class: 'scheda mappa-scheda' }, barra, box, etichettaRegione, legenda), panel));

    mappa = new window.Corpo.MappaCorpo(box, {
      onRegione: nome => { etichettaRegione.textContent = nome || 'Passa il puntatore sul corpo per vedere la zona'; },
      onPunto: nuovoPunto, onSeleziona: id => { if (id) selezionaNeo(id); else if (modo !== 'bozza') tornaLista(); },
      onSposta: spostaNeo, onBozzaMossa: p => { bozza = Object.assign({}, bozza, p); if (!sedeBozzaManuale) aggiornaSedeBozza(); },
    });
    mappa.setFototipo((S.utente.profilo && S.utente.profilo.fototipo) || 0);
    aggiornaMarcatori();
    renderPannello();
    NT.alCambioPagina(() => { stopPoll(); if (mappa && mappa.ro) mappa.ro.disconnect(); mappa = null; });
  };

  function attivaAggiunta(on) {
    if (!mappa) return;
    if (on) { bozza = null; dett = null; modo = 'lista'; mappa.setSelezione(null); }
    mappa.modalitaAggiunta(on);
    const b = $('#btn-aggiungi');
    if (b) b.classList.toggle('attivo', on);
    const hint = $('#mappa-hint');
    if (hint) hint.textContent = on ? 'Clicca sul punto esatto del corpo dove si trova il neo (puoi ingrandire prima)' : 'Rotella = zoom · trascina = sposta · doppio clic = ingrandisci';
    if (on) { aggiornaMarcatori(); renderPannello(); }
  }

  function tornaLista() {
    stopPoll(); modo = 'lista'; dett = null; fotoSel = null; bozza = null;
    if (mappa) { mappa.modalitaAggiunta(false); }
    attivaAggiunta(false);
    aggiornaMarcatori(); renderPannello();
  }

  /* ---------------------------- nuovo neo ---------------------------------- */
  function nuovoPunto(p) {
    bozza = { vista: p.vista, x: p.x, y: p.y, regione: p.regione };
    modo = 'bozza'; sedeBozzaManuale = false;
    mappa.modalitaAggiunta(false);
    const b = $('#btn-aggiungi'); if (b) b.classList.remove('attivo');
    mappa.setBozza(bozza);
    renderPannello();
  }
  function aggiornaSedeBozza() {
    const c = $('#campo-sede-bozza');
    if (c && bozza) c.value = bozza.regione || '';
    const info = $('#info-pos-bozza');
    if (info && bozza) info.textContent = testoPos(bozza);
  }
  const testoPos = p => (p.vista === 'fronte' ? 'Fronte' : 'Retro') + ' · posizione ' + Math.round(p.x * 100) + '% da sinistra, ' + Math.round(p.y * 100) + '% dall\'alto';

  function pannelloBozza() {
    const nome = h('input', { type: 'text', class: 'campo', maxlength: 60, value: 'Neo ' + (S.nei.length + 1), id: 'campo-nome-bozza' });
    const sede = h('input', { type: 'text', class: 'campo', maxlength: 80, list: 'sedi-utili', value: bozza.regione || '', id: 'campo-sede-bozza',
      oninput: () => { sedeBozzaManuale = true; } });
    const note = h('textarea', { class: 'campo', rows: 3, maxlength: 1000, placeholder: 'Quando l\'hai notato, se prude, se è cambiato…' });
    const salva = h('button', { class: 'btn btn-pri', onclick: async () => {
      salva.disabled = true;
      try {
        const r = await NT.api('POST', '/api/utenti/' + S.utente.id + '/nevi',
          { nome: nome.value, vista: bozza.vista, x: bozza.x, y: bozza.y, regione: sede.value, note: note.value });
        await NT.ricaricaNei();
        bozza = null; mappa.setBozza(null);
        formFotoAperto = true;
        await selezionaNeo(r.id);
        NT.toast('Neo salvato. Ora aggiungi la prima foto: sarà la tua "foto storica".', 'ok');
      } catch (e) { salva.disabled = false; NT.errore(e); }
    } }, 'Salva neo');
    return h('div', { class: 'scheda' },
      h('h2', {}, 'Nuovo neo'),
      h('p', { class: 'piccolo', id: 'info-pos-bozza' }, testoPos(bozza)),
      h('p', { class: 'piccolo' }, NT.icona('mirino', 14), ' Trascina il pallino sulla mappa per correggere la posizione; ingrandisci con la rotella per la massima precisione.'),
      h('label', { class: 'etichetta' }, 'Nome', nome),
      h('label', { class: 'etichetta' }, 'Sede (modificabile)', sede,
        h('datalist', { id: 'sedi-utili' }, SEDI_UTILI.map(s => h('option', { value: s })))),
      h('label', { class: 'etichetta' }, 'Note', note),
      h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => tornaLista() }, 'Annulla'), salva));
  }

  /* ------------------------- spostamento di un neo -------------------------- */
  async function spostaNeo(id, p) {
    const n = S.nei.find(q => q.id === id);
    if (!n) return;
    const corpo = { vista: p.vista, x: p.x, y: p.y };
    if (p.regione && (!n.regione || nomiAuto().has(n.regione))) corpo.regione = p.regione;
    try {
      await NT.api('PATCH', '/api/nevi/' + id, corpo);
      await NT.ricaricaNei();
      if (dett && dett.nevo.id === id) dett = await NT.get('/api/nevi/' + id);
      aggiornaMarcatori(); renderPannello();
      NT.toast('Posizione aggiornata' + (corpo.regione ? ': ' + corpo.regione : '') + '.', 'ok');
    } catch (e) { NT.errore(e); await NT.ricaricaNei(); aggiornaMarcatori(); }
  }

  /* --------------------------- selezione di un neo -------------------------- */
  async function selezionaNeo(id, centra) {
    stopPoll();
    try { dett = await NT.get('/api/nevi/' + id); } catch (e) { NT.errore(e); return; }
    modo = 'neo'; bozza = null;
    fotoSel = dett.foto.length ? dett.foto[dett.foto.length - 1].id : null;
    if (mappa) { mappa.modalitaAggiunta(false); mappa.setBozza(null); }
    const b = $('#btn-aggiungi'); if (b) b.classList.remove('attivo');
    aggiornaMarcatori();
    if (centra && mappa) mappa.centraSu(dett.nevo, 4);
    renderPannello();
  }
  async function ricaricaDettaglio() {
    dett = await NT.get('/api/nevi/' + dett.nevo.id);
    await NT.ricaricaNei();
    aggiornaMarcatori();
  }

  /* ============================== PANNELLO ================================== */
  function renderPannello() {
    if (!panel) return;
    stopPoll();
    const top = panel.scrollTop;
    panel.replaceChildren(modo === 'bozza' && bozza ? pannelloBozza() : modo === 'neo' && dett ? pannelloNeo() : pannelloLista());
    panel.scrollTop = modo === 'neo' ? top : 0;
    if (modo === 'neo' && fotoSel) caricaAnalisi(fotoSel);
  }

  /* ------------------------------ elenco dei nei ----------------------------- */
  function schedaLista(n) {
    const giorni = n.giorni_da_ultima;
    const promemoria = giorni !== null && giorni >= GIORNI_PROMEMORIA && !n.archiviato;
    return h('button', { class: 'neo-card', onclick: () => selezionaNeo(n.id, true) },
      h('span', { class: 'neo-num' + (n.n_foto === 0 ? ' vuoto' : '') + (n.ultimo_esito === 'attenzione' || n.ultimo_esito === 'discordante' ? ' rosso' : '') }, numDi(n.id)),
      n.ultima_foto_id ? h('img', { class: 'neo-thumb', src: '/foto/' + n.ultima_foto_id + '/mini?l=120', alt: '', loading: 'lazy' }) : h('span', { class: 'neo-thumb vuota' }, NT.icona('foto', 22)),
      h('span', { class: 'neo-info' },
        h('strong', {}, n.nome),
        h('span', { class: 'sotto' }, n.regione || (n.vista === 'fronte' ? 'Fronte' : 'Retro')),
        h('span', { class: 'sotto' }, n.n_foto === 0 ? 'Nessuna foto: aggiungi la prima'
          : n.n_foto + (n.n_foto === 1 ? ' foto' : ' foto') + ' · ultima ' + NT.fraseGiorni(giorni)),
        h('span', { class: 'chips' }, NT.chipEsito(n.ultimo_esito), promemoria ? h('span', { class: 'chip chip-neutro' }, 'Da rifotografare?') : null)));
  }

  function pannelloLista() {
    const lista = attivi(), arch = S.nei.filter(n => n.archiviato);
    const vuoto = !S.nei.length;
    return h('div', { class: 'scheda' },
      h('div', { class: 'testa-lista' }, h('h2', {}, vuoto ? 'Nessun neo ancora' : 'I tuoi nei (' + lista.length + ')'),
        lista.length ? h('button', { class: 'btn-testo', title: 'Stampa una scheda con tutti i nei', onclick: () => NT.stampaNei(lista.map(n => n.id)) }, NT.icona('stampa', 16), 'Scheda per il dermatologo') : null),
      vuoto
        ? h('ol', { class: 'passi' },
          h('li', {}, 'Premi ', h('strong', {}, 'Aggiungi neo'), ' e clicca sul punto esatto del corpo (ingrandisci con la rotella per essere più preciso).'),
          h('li', {}, 'Dai un nome al neo e controlla la sede.'),
          h('li', {}, 'Aggiungi la prima foto: diventa la tua foto storica, e ogni foto successiva ne seguirà l\'evoluzione.'))
        : h('div', { class: 'neo-elenco' }, lista.map(schedaLista)),
      arch.length ? h('details', { class: 'archiviati' }, h('summary', {}, 'Nei archiviati (' + arch.length + ')'),
        arch.map(n => h('div', { class: 'riga-arch' }, h('span', {}, n.nome + (n.regione ? ' – ' + n.regione : '')),
          h('button', { class: 'btn-testo', onclick: async () => { try { await NT.api('PATCH', '/api/nevi/' + n.id, { archiviato: false }); await NT.ricaricaNei(); aggiornaMarcatori(); renderPannello(); } catch (e) { NT.errore(e); } } }, 'Ripristina')))) : null,
      !vuoto ? h('p', { class: 'piccolo muted' }, 'Clicca un neo nell\'elenco o sulla mappa per vedere lo storico fotografico.') : null);
  }

  /* ------------------------------ dettaglio neo ------------------------------ */
  function pannelloNeo() {
    const n = dett.nevo, foto = dett.foto;
    const salva = async (campi) => { try { await NT.api('PATCH', '/api/nevi/' + n.id, campi); await ricaricaDettaglio(); } catch (e) { NT.errore(e); } };

    const nome = h('input', { type: 'text', class: 'campo titolo-modifica', maxlength: 60, value: n.nome, 'aria-label': 'Nome del neo',
      onchange: () => { if (nome.value.trim()) salva({ nome: nome.value }); else nome.value = n.nome; } });
    const sede = h('input', { type: 'text', class: 'campo', maxlength: 80, list: 'sedi-utili', value: n.regione, placeholder: 'Sede',
      onchange: () => salva({ regione: sede.value }) });
    const note = h('textarea', { class: 'campo', rows: 2, maxlength: 1000, placeholder: 'Note sul neo…', onchange: () => salva({ note: note.value }) }, n.note);

    const testa = h('div', { class: 'scheda' },
      h('div', { class: 'neo-testa' },
        h('button', { class: 'btn-testo', onclick: () => tornaLista() }, '← Tutti i nei'),
        h('span', { class: 'spazio' }),
        h('button', { class: 'btn-icona', title: 'Centra sulla mappa', onclick: () => mappa.centraSu(n, 5) }, NT.icona('mirino')),
        h('button', { class: 'btn-icona', title: 'Stampa la scheda di questo neo', onclick: () => NT.stampaNei([n.id]) }, NT.icona('stampa')),
        h('button', { class: 'btn-icona', title: 'Archivia (toglie dalla mappa, conserva i dati)', onclick: async () => {
          await salva({ archiviato: true }); tornaLista(); NT.toast('Neo archiviato. Lo trovi in fondo all\'elenco.', 'ok'); } }, NT.icona('archivio')),
        h('button', { class: 'btn-icona pericolo', title: 'Elimina questo neo e le sue foto', onclick: async () => {
          const si = await NT.conferma('Eliminare «' + n.nome + '»?', 'Verranno cancellate per sempre tutte le sue ' + foto.length + ' foto e i rapporti di analisi.',
            { si: 'Elimina', pericolo: true, scrivi: foto.length ? n.nome : null });
          if (!si) return;
          try { await NT.api('DELETE', '/api/nevi/' + n.id); await NT.ricaricaNei(); tornaLista(); NT.toast('Neo eliminato.', 'ok'); } catch (e) { NT.errore(e); } } }, NT.icona('cestino'))),
      h('div', { class: 'neo-titolo' }, h('span', { class: 'neo-num grande' + (foto.length ? '' : ' vuoto') }, numDi(n.id)), nome),
      h('div', { class: 'riga-2' }, h('label', { class: 'etichetta' }, 'Sede', sede,
        h('datalist', { id: 'sedi-utili' }, SEDI_UTILI.map(s => h('option', { value: s })))),
        h('div', { class: 'etichetta' }, 'Posizione', h('div', { class: 'piccolo' }, testoPos(n), h('br'), 'Trascina il pallino sulla mappa per spostarlo.'))),
      h('label', { class: 'etichetta' }, 'Note', note));

    const sezioni = [testa, sezioneStorico(n, foto), formFoto(n)];
    const grafico = graficoDiametro(foto);
    if (grafico) sezioni.push(grafico);
    sezioni.push(h('div', { class: 'scheda', id: 'box-analisi' }, h('h3', {}, 'Analisi automatica'), NT.caricamento('Controllo lo stato…')));
    return h('div', { class: 'pila' }, sezioni);
  }

  /* ----------------------------- storico fotografico ----------------------------- */
  function sezioneStorico(n, foto) {
    if (!foto.length) {
      return h('div', { class: 'scheda' }, h('h3', {}, 'Storico fotografico'),
        NT.vuoto('Ancora nessuna foto', 'Aggiungi qui sotto la prima foto: sarà il punto di partenza per vedere se il neo cambia nel tempo.'));
    }
    const f = foto.find(x => x.id === fotoSel) || foto[foto.length - 1];
    const striscia = h('div', { class: 'striscia' }, foto.map(x => h('button', { class: 'miniatura' + (x.id === f.id ? ' sel' : ''), title: NT.fmtData(x.scattata_il) + (x.diametro_mm ? ' · ' + NT.num(x.diametro_mm) + ' mm' : ''),
      onclick: () => { fotoSel = x.id; renderPannello(); } },
      h('img', { src: '/foto/' + x.id + '/mini?l=240', alt: 'Foto del ' + NT.fmtData(x.scattata_il), loading: 'lazy' }),
      h('span', { class: 'data' }, NT.fmtData(x.scattata_il)),
      x.esito && x.esito !== 'nessuno' ? h('i', { class: 'punto-esito ' + NT.ESITI[x.esito].cls, title: NT.ESITI[x.esito].testo }) : null)));
    const precedente = foto[foto.indexOf(f) - 1];
    const meta = h('div', { class: 'foto-meta' },
      h('span', {}, h('strong', {}, NT.fmtData(f.scattata_il)), ' · ', f.tipo === 'dermoscopica' ? 'dermoscopica' : 'foto normale'),
      f.diametro_mm ? h('span', {}, 'Diametro: ', h('strong', {}, NT.num(f.diametro_mm) + ' mm'),
        precedente && precedente.diametro_mm ? h('span', { class: 'delta' }, ' (' + (f.diametro_mm - precedente.diametro_mm >= 0 ? '+' : '') + NT.num(f.diametro_mm - precedente.diametro_mm) + ' mm dalla foto precedente)') : null) : null,
      f.note ? h('span', { class: 'muted' }, f.note) : null);
    return h('div', { class: 'scheda' },
      h('div', { class: 'testa-lista' }, h('h3', {}, 'Storico fotografico (' + foto.length + ')'),
        foto.length >= 2 ? h('button', { class: 'btn-testo', onclick: () => dialogoConfronto(foto, f) }, NT.icona('confronta', 16), 'Confronta') : null),
      striscia,
      h('button', { class: 'anteprima', title: 'Clic per vedere la foto originale a schermo intero', onclick: () => apriLightbox(f) },
        h('img', { src: '/foto/' + f.id + '/mini?l=960', alt: 'Foto del ' + NT.fmtData(f.scattata_il) })),
      meta,
      h('div', { class: 'azioni-foto' },
        h('button', { class: 'btn-testo', onclick: () => dialogoModificaFoto(f) }, 'Modifica data/misura'),
        h('button', { class: 'btn-testo pericolo', onclick: async () => {
          const si = await NT.conferma('Eliminare questa foto?', 'La foto del ' + NT.fmtData(f.scattata_il) + ' e il suo rapporto di analisi saranno cancellati per sempre.', { si: 'Elimina foto', pericolo: true });
          if (!si) return;
          try { await NT.api('DELETE', '/api/foto/' + f.id); await ricaricaDettaglio(); fotoSel = dett.foto.length ? dett.foto[dett.foto.length - 1].id : null; renderPannello(); NT.toast('Foto eliminata.', 'ok'); } catch (e) { NT.errore(e); } } }, 'Elimina foto')));
  }

  function apriLightbox(f) {
    const d = $('#lightbox');
    d.replaceChildren(h('div', { class: 'lb' },
      h('div', { class: 'lb-barra' }, h('strong', {}, NT.fmtData(f.scattata_il)), h('span', { class: 'spazio' }), h('button', { class: 'btn', onclick: () => d.close() }, 'Chiudi')),
      h('img', { src: '/foto/' + f.id + '/originale', alt: 'Foto originale' })));
    d.showModal();
  }

  function dialogoModificaFoto(f) {
    const data = h('input', { type: 'date', class: 'campo', value: f.scattata_il, max: NT.oggiISO() });
    const diam = h('input', { type: 'text', class: 'campo', inputmode: 'decimal', value: f.diametro_mm === null ? '' : NT.num(f.diametro_mm), placeholder: 'es. 4,5' });
    const tipo = h('select', { class: 'campo' }, h('option', { value: 'normale', selected: f.tipo === 'normale' }, 'Foto normale'), h('option', { value: 'dermoscopica', selected: f.tipo === 'dermoscopica' }, 'Dermoscopica'));
    const nota = h('textarea', { class: 'campo', rows: 2, maxlength: 1000 }, f.note);
    NT.apriDialogo(h('div', {}, h('h3', {}, 'Modifica foto'),
      h('label', { class: 'etichetta' }, 'Data dello scatto', data), h('label', { class: 'etichetta' }, 'Diametro (mm)', diam),
      h('label', { class: 'etichetta' }, 'Tipo', tipo), h('label', { class: 'etichetta' }, 'Note', nota),
      h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => NT.chiudiDialogo() }, 'Annulla'),
        h('button', { class: 'btn btn-pri', onclick: async () => {
          try {
            await NT.api('PATCH', '/api/foto/' + f.id, { scattata_il: data.value, diametro_mm: diam.value, tipo: tipo.value, note: nota.value });
            NT.chiudiDialogo(); await ricaricaDettaglio(); renderPannello();
          } catch (e) { NT.errore(e); }
        } }, 'Salva'))));
  }

  /* ----------------------------- aggiunta di una foto ----------------------------- */
  function formFoto(n) {
    let file = null;
    const anteprima = h('div', { class: 'drop-testo' }, NT.icona('foto', 26), h('span', {}, 'Trascina qui una foto oppure clicca per sceglierla'), h('small', {}, 'JPG, PNG, WEBP o BMP · fino a 60 MB'));
    const input = h('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp,image/bmp,.jpg,.jpeg,.png,.webp,.bmp', class: 'nascosto' });
    const drop = h('label', { class: 'drop' }, input, anteprima);
    const data = h('input', { type: 'date', class: 'campo', value: NT.oggiISO(), max: NT.oggiISO(), oninput: () => { usaExif.checked = false; } });
    const usaExif = h('input', { type: 'checkbox', checked: true });
    const tipo = h('select', { class: 'campo' }, h('option', { value: 'normale' }, 'Foto normale (smartphone)'), h('option', { value: 'dermoscopica' }, 'Dermoscopica'));
    const diam = h('input', { type: 'text', class: 'campo', inputmode: 'decimal', placeholder: 'es. 4,5' });
    const nota = h('input', { type: 'text', class: 'campo', maxlength: 1000, placeholder: 'Facoltativa' });
    const analizza = h('input', { type: 'checkbox', checked: true });
    const btn = h('button', { class: 'btn btn-pri', disabled: true }, NT.icona('foto', 18), 'Salva foto');

    function scegli(fl) {
      if (!fl) return;
      if (!/^image\//.test(fl.type) && !/\.(jpe?g|png|webp|bmp)$/i.test(fl.name)) { NT.toast('Scegli un file immagine (JPG, PNG, WEBP o BMP).', 'errore'); return; }
      if (fl.size > (S.stato.max_mb_foto || 60) * 1048576) { NT.toast('La foto supera i ' + (S.stato.max_mb_foto || 60) + ' MB: riducila o scegline un\'altra.', 'errore'); return; }
      file = fl;
      data.value = NT.dataDaMs(fl.lastModified); usaExif.checked = true;
      const url = URL.createObjectURL(fl);
      anteprima.replaceChildren(h('img', { src: url, alt: 'Anteprima', class: 'drop-img' }), h('small', {}, fl.name + ' · ' + (fl.size / 1048576).toFixed(1).replace('.', ',') + ' MB · clicca per cambiare'));
      btn.disabled = false;
    }
    input.addEventListener('change', () => scegli(input.files[0]));
    ['dragenter', 'dragover'].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.add('sopra'); }));
    ['dragleave', 'drop'].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.remove('sopra'); }));
    drop.addEventListener('drop', ev => scegli(ev.dataTransfer.files[0]));

    btn.addEventListener('click', async () => {
      if (!file) return;
      btn.disabled = true; btn.replaceChildren(h('span', { class: 'spinner' }), 'Salvataggio…');
      const q = new URLSearchParams({ data: data.value, exif: usaExif.checked ? '1' : '0', tipo: tipo.value, diametro: diam.value, note: nota.value, analizza: analizza.checked ? '1' : '0' });
      try {
        const r = await NT.api('POST', '/api/nevi/' + n.id + '/foto?' + q.toString(), null, { raw: file, tipo: file.type || 'application/octet-stream' });
        formFotoAperto = false;
        await ricaricaDettaglio();
        fotoSel = r.id;
        renderPannello();
        NT.toast('Foto salvata (' + NT.fmtData(r.scattata_il) + (r.da_exif ? ', data letta dalla foto' : '') + ').' + (r.analisi_errore ? ' ' + r.analisi_errore : ''), r.analisi_errore ? 'errore' : 'ok');
      } catch (e) { btn.disabled = false; btn.replaceChildren(NT.icona('foto', 18), 'Salva foto'); NT.errore(e); }
    });

    const det = h('details', { class: 'scheda form-foto', open: formFotoAperto || dett.foto.length === 0 },
      h('summary', {}, NT.icona('piu', 16), 'Aggiungi una foto allo storico'),
      h('div', { class: 'form-corpo' }, drop,
        h('div', { class: 'riga-2' },
          h('label', { class: 'etichetta' }, 'Data dello scatto', data,
            h('span', { class: 'spunta' }, usaExif, ' Usa la data scritta nella foto, se c\'è')),
          h('label', { class: 'etichetta' }, 'Diametro misurato (mm)', diam)),
        h('div', { class: 'riga-2' }, h('label', { class: 'etichetta' }, 'Tipo di foto', tipo), h('label', { class: 'etichetta' }, 'Note', nota)),
        h('label', { class: 'spunta grande' }, analizza, ' Analizza subito con tutti i metodi installati'),
        h('details', { class: 'consigli' }, h('summary', {}, 'Come scattare foto confrontabili'),
          h('ul', {}, h('li', {}, 'Stessa luce (luce del giorno, senza flash) e stessa distanza ogni volta, circa 10-15 cm.'),
            h('li', {}, 'Metti accanto al neo un righello o una moneta: serve per misurare il diametro.'),
            h('li', {}, 'Foto a fuoco, con il neo al centro e la pelle ben visibile (sposta i peli, se serve).'),
            h('li', {}, 'Scatta sempre dalla stessa angolazione e salva l\'originale, senza filtri.'))),
        btn));
    return det;
  }

  /* ------------------------------ grafico del diametro ------------------------------ */
  function graficoDiametro(foto) {
    const pt = foto.filter(f => f.diametro_mm !== null && f.diametro_mm !== undefined).map(f => ({ d: f.scattata_il, v: f.diametro_mm }));
    if (pt.length < 2) return null;
    const L = 380, A = 190, ml = 36, mr = 14, mt = 14, mb = 32;
    const t0 = new Date(pt[0].d + 'T12:00:00').getTime(), t1 = new Date(pt[pt.length - 1].d + 'T12:00:00').getTime();
    const vmax = Math.max(7, Math.ceil(Math.max(...pt.map(p => p.v)) + 1));
    const X = d => ml + (t1 === t0 ? (L - ml - mr) / 2 : (new Date(d + 'T12:00:00').getTime() - t0) / (t1 - t0) * (L - ml - mr));
    const Y = v => A - mb - v / vmax * (A - mb - mt);
    const passo = vmax <= 10 ? 2 : 5;
    let s = '<svg viewBox="0 0 ' + L + ' ' + A + '" class="grafico" role="img" aria-label="Diametro del neo nel tempo">';
    for (let v = 0; v <= vmax; v += passo) s += '<line x1="' + ml + '" x2="' + (L - mr) + '" y1="' + Y(v) + '" y2="' + Y(v) + '" class="gl"/><text x="' + (ml - 6) + '" y="' + (Y(v) + 4) + '" text-anchor="end" class="gt">' + v + '</text>';
    s += '<line x1="' + ml + '" x2="' + (L - mr) + '" y1="' + Y(6) + '" y2="' + Y(6) + '" class="g6"/><text x="' + (L - mr) + '" y="' + (Y(6) - 4) + '" text-anchor="end" class="gt g6t">6 mm</text>';
    s += '<polyline class="gline" points="' + pt.map(p => X(p.d) + ',' + Y(p.v)).join(' ') + '"/>';
    pt.forEach(p => { s += '<circle cx="' + X(p.d) + '" cy="' + Y(p.v) + '" r="4.5" class="gp"><title>' + NT.fmtData(p.d) + ': ' + NT.num(p.v) + ' mm</title></circle>'; });
    s += '<text x="' + X(pt[0].d) + '" y="' + (A - 10) + '" text-anchor="start" class="gt">' + NT.fmtData(pt[0].d) + '</text>';
    s += '<text x="' + X(pt[pt.length - 1].d) + '" y="' + (A - 10) + '" text-anchor="end" class="gt">' + NT.fmtData(pt[pt.length - 1].d) + '</text></svg>';
    const diff = pt[pt.length - 1].v - pt[0].v, giorni = NT.giorniTra(pt[0].d, pt[pt.length - 1].d);
    return h('div', { class: 'scheda' }, h('h3', {}, 'Diametro nel tempo'), NT.html(s),
      h('p', { class: 'piccolo' }, 'Variazione: ', h('strong', {}, (diff >= 0 ? '+' : '') + NT.num(diff) + ' mm'), ' in ' + giorni + ' giorni. ',
        'Sono misure inserite da te: valgono se prese sempre allo stesso modo. Un neo che cresce o cambia è un buon motivo per farlo vedere al dermatologo; la linea a 6 mm è solo il riferimento classico dei criteri ABCDE.'),
      h('button', { class: 'btn-testo', onclick: dialogoABCDE }, 'Promemoria ABCDE'));
  }

  function dialogoABCDE() {
    const voci = [['A', 'Asimmetria', 'Le due metà del neo non si somigliano.'], ['B', 'Bordi', 'Irregolari, frastagliati o sfumati.'],
      ['C', 'Colore', 'Più colori nello stesso neo (marrone, nero, rosso, blu, bianco).'], ['D', 'Diametro', 'Più di 6 mm (ma esistono melanomi più piccoli).'],
      ['E', 'Evoluzione', 'Cambia nel tempo: forma, colore, dimensione, rilievo, o compaiono prurito o sanguinamento.']];
    NT.apriDialogo(h('div', {}, h('h3', {}, 'Promemoria ABCDE'),
      h('ul', { class: 'abcde' }, voci.map(([l, t, d]) => h('li', {}, h('b', {}, l), h('span', {}, h('strong', {}, t), ' – ', d)))),
      h('p', { class: 'piccolo' }, 'Conta anche il «brutto anatroccolo»: un neo diverso da tutti gli altri. I noduli che crescono rapidamente o sono duri al tatto vanno mostrati subito. Questo promemoria non sostituisce la visita.'),
      h('div', { class: 'azioni' }, h('button', { class: 'btn btn-pri', onclick: () => NT.chiudiDialogo() }, 'Chiudi'))));
  }

  NT.dialogoABCDE = dialogoABCDE;

  /* ---------------------------------- confronto ---------------------------------- */
  function dialogoConfronto(foto, corrente) {
    let a = foto[0], b = foto[foto.length - 1];
    if (corrente && foto.length > 2) { const i = foto.indexOf(corrente); b = corrente; a = i > 0 ? foto[i - 1] : foto[1]; if (a.id === b.id) a = foto[0]; if (new Date(a.scattata_il) > new Date(b.scattata_il)) [a, b] = [b, a]; }
    let sovrapposto = false, posizione = 50;
    const etich = f => NT.fmtData(f.scattata_il) + (f.diametro_mm ? ' · ' + NT.num(f.diametro_mm) + ' mm' : '');
    const selA = h('select', { class: 'campo', onchange: () => { a = foto.find(x => x.id === +selA.value); ridisegna(); } }, foto.map(f => h('option', { value: f.id, selected: f.id === a.id }, etich(f))));
    const selB = h('select', { class: 'campo', onchange: () => { b = foto.find(x => x.id === +selB.value); ridisegna(); } }, foto.map(f => h('option', { value: f.id, selected: f.id === b.id }, etich(f))));
    const area = h('div', { class: 'confronto-area' });
    const modoBtn = h('button', { class: 'btn', onclick: () => { sovrapposto = !sovrapposto; modoBtn.textContent = sovrapposto ? 'Mostra affiancate' : 'Sovrapponi con cursore'; ridisegna(); } }, 'Sovrapponi con cursore');
    function ridisegna() {
      const giorni = NT.giorniTra(a.scattata_il, b.scattata_il);
      const dd = (a.diametro_mm && b.diametro_mm) ? ' Diametro: ' + NT.num(b.diametro_mm - a.diametro_mm) + ' mm di differenza.' : '';
      const nota = h('p', { class: 'piccolo' }, 'Tra le due foto sono passati ' + Math.abs(giorni) + ' giorni.' + dd + ' Confronta forma, bordi e colori: se noti differenze, mostra le foto al dermatologo.');
      if (!sovrapposto) {
        area.replaceChildren(h('div', { class: 'confronto-coppia' },
          h('figure', {}, h('img', { src: '/foto/' + a.id + '/mini?l=960', alt: '' }), h('figcaption', {}, etich(a))),
          h('figure', {}, h('img', { src: '/foto/' + b.id + '/mini?l=960', alt: '' }), h('figcaption', {}, etich(b)))), nota);
      } else {
        const top = h('img', { src: '/foto/' + a.id + '/mini?l=960', alt: '', class: 'sopra', style: { clipPath: 'inset(0 ' + (100 - posizione) + '% 0 0)' } });
        const cur = h('input', { type: 'range', min: 0, max: 100, value: posizione, 'aria-label': 'Cursore di confronto', oninput: () => { posizione = +cur.value; top.style.clipPath = 'inset(0 ' + (100 - posizione) + '% 0 0)'; } });
        area.replaceChildren(h('div', { class: 'sovrapposte' }, h('img', { src: '/foto/' + b.id + '/mini?l=960', alt: '' }), top),
          cur, h('div', { class: 'didascalie' }, h('span', {}, '← ' + etich(a)), h('span', {}, etich(b) + ' →')), nota);
      }
    }
    ridisegna();
    NT.apriDialogo(h('div', {}, h('h3', {}, 'Confronto tra due foto'),
      h('div', { class: 'riga-2' }, h('label', { class: 'etichetta' }, 'Prima', selA), h('label', { class: 'etichetta' }, 'Dopo', selB)),
      modoBtn, area, h('div', { class: 'azioni' }, h('button', { class: 'btn btn-pri', onclick: () => NT.chiudiDialogo() }, 'Chiudi'))), true);
  }

  /* ------------------------------ analisi automatica ------------------------------ */
  async function caricaAnalisi(fotoId) {
    const box = $('#box-analisi');
    if (!box || fotoId !== fotoSel) return;
    let st;
    try { st = await NT.get('/api/foto/' + fotoId + '/analisi'); } catch (e) { box.replaceChildren(h('h3', {}, 'Analisi automatica'), h('p', { class: 'errore-campo' }, e.message)); return; }
    if (fotoId !== fotoSel || !$('#box-analisi')) return;
    const attiva = st.stato === 'in_coda' || st.stato === 'in_corso';
    if (attiva) inAnalisi.add(fotoId);
    else if (inAnalisi.has(fotoId)) {                          // appena finita: aggiorno elenco e pallini
      inAnalisi.delete(fotoId);
      await ricaricaDettaglio();
      renderPannello();
      return;
    }
    box.replaceChildren(h('h3', {}, 'Analisi automatica'), contenutoAnalisi(fotoId, st));
    if (attiva) pollTimer = setTimeout(() => caricaAnalisi(fotoId), 3000);
  }

  async function avviaAnalisi(fotoId) {
    try { await NT.api('POST', '/api/foto/' + fotoId + '/analizza'); inAnalisi.add(fotoId); caricaAnalisi(fotoId); } catch (e) { NT.errore(e); }
  }

  function contenutoAnalisi(fotoId, st) {
    if (st.stato === 'nessuna') {
      return h('div', {}, h('p', {}, 'Questa foto non è ancora stata analizzata. L\'analisi confronta più metodi sulla stessa immagine e ti dice cosa ha risposto ciascuno.'),
        h('p', { class: 'piccolo muted' }, 'La prima analisi può richiedere diversi minuti (i modelli vengono caricati in memoria). ' +
          (st.skinsense_attivo ? 'SkinSense è attivo: la foto (senza metadati) verrà inviata a un servizio online.' : 'La foto resta sul tuo computer: SkinSense (servizio online) è disattivato.')),
        h('button', { class: 'btn btn-pri', onclick: () => avviaAnalisi(fotoId) }, 'Analizza questa foto'));
    }
    if (st.stato === 'in_coda' || st.stato === 'in_corso') {
      return h('div', { class: 'analisi-attesa' }, h('div', { class: 'riga-spinner' }, h('span', { class: 'spinner grande' }),
        h('div', {}, h('strong', {}, st.stato === 'in_coda' ? 'In coda' + (st.posizione_coda > 0 ? ' (posizione ' + st.posizione_coda + ')' : '') + '…' : 'Analisi in corso…'),
          h('p', { class: 'piccolo muted' }, 'Puoi continuare a usare l\'app. Se chiudi la finestra l\'analisi non va persa: il programma finisce il lavoro e poi si spegne da solo.'))),
        st.avanzamento && st.avanzamento.length ? h('pre', { class: 'log' }, st.avanzamento.join('\n')) : null);
    }
    if (st.stato === 'errore') {
      return h('div', {}, h('p', { class: 'errore-campo' }, st.messaggio || 'L\'analisi non è riuscita.'),
        h('button', { class: 'btn', onclick: () => avviaAnalisi(fotoId) }, 'Riprova'));
    }
    return renderSintesi(st.sintesi, fotoId);
  }

  const GIUDIZIO_NESSUNO = 'Nessun metodo ha prodotto un risultato: controlla i motivi indicati sotto.';
  const GIUDIZIO_ATT = 'Almeno un metodo (o un suo modello) segnala una lesione da attenzionare. Non è una diagnosi e questi strumenti sbagliano spesso, ma è un motivo in più per non rimandare la visita dermatologica e per portare questo rapporto.';
  const GIUDIZIO_BEN = 'Nessuno dei metodi che hanno risposto segnala la lesione come sospetta. Questo NON esclude un melanoma: gli strumenti non sono validati clinicamente e sbagliano anche in questa direzione. Se il neo è asimmetrico, ha bordi irregolari, colori diversi, è più grande di 6 mm o è cambiato nel tempo, la visita resta necessaria.';
  const AVVERTENZE = [
    'Questo rapporto NON è una diagnosi. I programmi usati sono prototipi di ricerca, non dispositivi medici.',
    'I metodi sono addestrati su fotografie diverse dalle tue: cambiare luce, distanza o fotocamera può cambiare la risposta.',
    'Fototipo, età e familiarità non cambiano il risultato delle reti neurali (guardano solo i pixel): servono a contestualizzare il rischio.',
    'Se i metodi sono in disaccordo è normale: significa solo che nessuno di loro è affidabile da solo.',
  ];

  function renderSintesi(s, fotoId) {
    const giud = s.con_risultato.length === 0 ? GIUDIZIO_NESSUNO : (s.attenzione.length || s.discordi.length) ? GIUDIZIO_ATT : GIUDIZIO_BEN;
    const schede = s.metodi.map(m => {
      const ok = m.risultati.filter(r => r.stato === 'ok');
      const piu = new Set(m.risultati.map(r => r.gruppo).filter(Boolean)).size > 1;
      return h('div', { class: 'metodo' },
        h('div', { class: 'metodo-testa' }, h('strong', {}, 'Metodo ' + m.numero), h('span', { class: 'metodo-titolo' }, m.titolo),
          m.verdetto ? NT.chipEsito(m.verdetto) : h('span', { class: 'chip chip-neutro' }, 'Nessun risultato')),
        m.introduzione ? h('p', { class: 'piccolo muted' }, m.introduzione) : null,
        ok.length ? h('p', { class: 'ha-detto' }, 'Il metodo ' + m.numero + ' ha detto che: ', h('strong', {}, m.frase)) : null,
        h('ul', { class: 'modelli' }, m.risultati.map(r => r.stato === 'ok'
          ? h('li', {}, h('span', { class: 'mod-nome' }, (piu && r.gruppo ? '[' + r.gruppo + '] ' : '') + r.nome), h('span', {}, '→ ' + r.etichetta),
            h('span', { class: 'muted' }, 'sicurezza ' + NT.perc(r.valore) + (r.prob_mel !== null && r.prob_mel !== undefined ? ' · prob. melanoma ' + NT.perc(r.prob_mel) : '')))
          : h('li', { class: 'nota-metodo ' + r.stato }, h('span', {}, (r.stato === 'errore' ? r.nome + ': errore. ' : r.stato === 'non_disponibile' ? r.nome + ': non disponibile. ' : '') + (r.nota || ''))))));
    });
    return h('div', { class: 'sintesi' },
      h('div', { class: 'sintesi-testa' }, NT.chipEsito(s.esito), h('span', { class: 'piccolo muted' }, s.con_risultato.length + ' metodi su ' + s.metodi.length + ' hanno risposto')),
      h('p', { class: 'giudizio' }, giud),
      schede,
      h('details', { class: 'consigli' }, h('summary', {}, 'Avvertenze'), h('ul', {}, AVVERTENZE.map(a => h('li', {}, a)))),
      s.testo ? h('details', { class: 'consigli' }, h('summary', {}, 'Rapporto completo (testo)'), h('pre', { class: 'rapporto' }, s.testo)) : null,
      h('button', { class: 'btn-testo', onclick: () => avviaAnalisi(fotoId) }, 'Rianalizza'));
  }
})();
'''
WEB_FILES["/v_mappa.js"] = ("text/javascript; charset=utf-8", _WEB_V_MAPPA_JS.encode("utf-8"))

_WEB_V_PROFILO_JS = r'''/* ============================================================================
   v_profilo.js - fenotipo, storia personale e familiarità (si salva da solo)
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  const FOTOTIPI = [
    [1, 'I', 'Pelle molto chiara. Scotta sempre, non si abbronza mai (spesso capelli rossi, lentiggini).'],
    [2, 'II', 'Pelle chiara. Scotta facilmente, si abbronza poco.'],
    [3, 'III', 'Pelle chiara-olivastra. Scotta a volte, si abbronza gradualmente.'],
    [4, 'IV', 'Pelle olivastra. Scotta poco, si abbronza facilmente.'],
    [5, 'V', 'Pelle scura. Scotta raramente.'],
    [6, 'VI', 'Pelle molto scura. Non scotta.'],
  ];

  NT.viste.profilo = async function (cont) {
    const u = S.utente;
    let p = Object.assign({}, u.profilo);
    const stato = h('span', { class: 'salvataggio' }, '');
    const riepilogo = h('aside', { class: 'riepilogo-profilo' });

    /* ---------- salvataggio automatico ---------- */
    const salvaOra = async () => {
      stato.textContent = 'Salvataggio…'; stato.className = 'salvataggio';
      try {
        const r = await NT.api('PUT', '/api/utenti/' + u.id + '/profilo', p);
        S.utente = Object.assign(S.utente, r);
        stato.textContent = 'Salvato ✓'; stato.className = 'salvataggio ok';
        disegnaRiepilogo();
      } catch (e) { stato.textContent = ''; NT.errore(e); }
    };
    const salva = NT.debounce(salvaOra, 700);
    const cambia = (campo, valore) => { p[campo] = valore; stato.textContent = 'Modifiche non salvate…'; stato.className = 'salvataggio'; salva(); };
    NT.alCambioPagina(() => { if (stato.textContent.startsWith('Modifiche')) salvaOra(); });

    /* ---------- piccoli componenti ---------- */
    const gruppo = (campo, opzioni, nome) => {
      const bottoni = opzioni.map(([val, testo]) => {
        const b = h('button', { type: 'button', class: 'pillola' + (p[campo] === val ? ' sel' : ''), 'aria-pressed': p[campo] === val ? 'true' : 'false',
          onclick: () => { p[campo] = (p[campo] === val && val !== '') ? '' : val; bottoni.forEach(x => { const on = x.dataset.v === p[campo]; x.classList.toggle('sel', on); x.setAttribute('aria-pressed', on ? 'true' : 'false'); }); cambia(campo, p[campo]); },
          dataset: { v: val } }, testo);
        return b;
      });
      return h('div', { class: 'campo-gruppo', role: 'group', 'aria-label': nome }, bottoni);
    };
    const campo = (titolo, contenuto, aiuto) => h('div', { class: 'campo-blocco' }, h('div', { class: 'campo-titolo' }, titolo), contenuto, aiuto ? h('div', { class: 'piccolo muted' }, aiuto) : null);
    const spunta = (c, testo) => h('label', { class: 'spunta' }, h('input', { type: 'checkbox', checked: !!p[c], onchange: ev => cambia(c, ev.target.checked) }), ' ' + testo);
    const contatore = (c, testo, aiuto) => {
      const val = h('output', { class: 'cont-val' }, String(p[c] || 0));
      const agg = d => { p[c] = Math.max(0, Math.min(20, (p[c] || 0) + d)); val.textContent = String(p[c]); if (c.startsWith('fam_') && !p.fam_compilata) { p.fam_compilata = true; const ck = NT.$('#ck-fam'); if (ck) ck.checked = true; } cambia(c, p[c]); };
      return h('div', { class: 'contatore-riga' }, h('div', {}, h('div', { class: 'campo-titolo' }, testo), aiuto ? h('div', { class: 'piccolo muted' }, aiuto) : null),
        h('div', { class: 'contatore' }, h('button', { type: 'button', class: 'btn-icona', 'aria-label': 'Diminuisci: ' + testo, onclick: () => agg(-1) }, NT.icona('meno', 16)), val,
          h('button', { type: 'button', class: 'btn-icona', 'aria-label': 'Aumenta: ' + testo, onclick: () => agg(1) }, NT.icona('piu', 16))));
    };

    /* ---------- fototipo ---------- */
    const COL = window.Corpo.colorePelle;
    const fototipi = h('div', { class: 'fototipi', role: 'radiogroup', 'aria-label': 'Fototipo' }, FOTOTIPI.map(([n, r, d]) => h('button', { type: 'button', role: 'radio', class: 'fototipo' + (p.fototipo === n ? ' sel' : ''),
      'aria-checked': p.fototipo === n ? 'true' : 'false', dataset: { n: String(n) },
      onclick: () => { p.fototipo = p.fototipo === n ? 0 : n; NT.$$('.fototipo', fototipi).forEach(b => { const on = +b.dataset.n === p.fototipo; b.classList.toggle('sel', on); b.setAttribute('aria-checked', on ? 'true' : 'false'); }); cambia('fototipo', p.fototipo); } },
      h('span', { class: 'swatch', style: { background: COL(n) } }), h('span', {}, h('strong', {}, 'Tipo ' + r), h('small', {}, d)))));

    const eta = h('span', { class: 'eta-calcolata' }, '');
    const aggiornaEta = () => {
      if (!p.data_nascita) { eta.textContent = ''; return; }
      const n = new Date(p.data_nascita + 'T12:00:00'), o = new Date();
      let a = o.getFullYear() - n.getFullYear(); if (o < new Date(o.getFullYear(), n.getMonth(), n.getDate())) a--;
      eta.textContent = a >= 0 ? a + ' anni' : '';
    };
    const nascita = h('input', { type: 'date', class: 'campo corto', value: p.data_nascita || '', min: '1900-01-01', max: NT.oggiISO(),
      onchange: ev => { cambia('data_nascita', ev.target.value); aggiornaEta(); } });
    aggiornaEta();

    const sezione = (titolo, intro, ...figli) => h('section', { class: 'scheda' }, h('h2', {}, titolo), intro ? h('p', { class: 'piccolo muted' }, intro) : null, ...figli);

    /* ---------- immagine personale ---------- */
    const boxAvatar = h('div', { class: 'avatar-editor' });
    const entrata = h('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp,image/bmp', hidden: true, 'aria-label': 'Scegli un\'immagine personale' });
    const aggiornaAvatar = v => { S.utente.avatar_v = v; disegnaAvatar(); NT.ridisegnaTestata(); disegnaRiepilogo(); };
    async function scegliAvatar() {
      const file = entrata.files && entrata.files[0];
      entrata.value = '';
      if (!file) return;
      try {
        if (file.size > 40 * 1024 * 1024) throw new Error('Il file è troppo grande (massimo 40 MB).');
        const blob = await NT.ridimensionaQuadrato(file, 256);      // ritaglio quadrato al centro + riduzione, nel browser
        const r = await NT.api('POST', '/api/utenti/' + u.id + '/avatar', null, { raw: blob, tipo: 'image/jpeg' });
        aggiornaAvatar(r.avatar_v);
        NT.toast('Immagine personale salvata.', 'ok');
      } catch (e) { NT.errore(e); }
    }
    async function togliAvatar() {
      try { const r = await NT.api('DELETE', '/api/utenti/' + u.id + '/avatar'); aggiornaAvatar(r.avatar_v); NT.toast('Immagine rimossa.', 'ok'); }
      catch (e) { NT.errore(e); }
    }
    entrata.addEventListener('change', scegliAvatar);
    function disegnaAvatar() {
      NT.riempi(boxAvatar, NT.avatar(u.nome, 88, S.utente),
        h('div', { class: 'avatar-azioni' },
          h('p', { class: 'piccolo muted' }, 'Puoi usare una tua foto, un disegno o un\'icona. L\'immagine viene ritagliata a quadrato e ridotta, resta solo su questo computer e non viene mai usata per l\'analisi dei nei.'),
          h('div', { class: 'riga-inline' },
            h('button', { type: 'button', class: 'btn', onclick: () => entrata.click() }, S.utente.avatar_v ? 'Cambia immagine…' : 'Scegli immagine…'),
            S.utente.avatar_v ? h('button', { type: 'button', class: 'btn-testo pericolo', onclick: togliAvatar }, 'Rimuovi') : null)));
    }
    disegnaAvatar();

    const form = h('div', { class: 'pila' },
      h('div', { class: 'scheda info' }, h('strong', {}, 'A che cosa servono questi dati? '),
        'Non cambiano il risultato delle reti neurali, che guardano solo i pixel della foto. Servono a: (1) dare un contesto al rischio, (2) scegliere la letteratura scientifica adatta a te, (3) verificare i criteri per la consulenza genetica, (4) calcolare quanto tempo puoi stare al sole prima di scottarti. Tutto resta sul tuo computer.'),
      sezione('Immagine personale', null, boxAvatar, entrata),
      sezione('Dati personali', null,
        campo('Sesso', gruppo('sesso', [['F', 'Donna'], ['M', 'Uomo'], ['altro', 'Altro'], ['', 'Preferisco non dirlo']], 'Sesso')),
        campo('Data di nascita', h('div', { class: 'riga-inline' }, nascita, eta))),
      sezione('Fenotipo: pelle, capelli, occhi', 'Se hai dubbi sul fototipo, pensa a come reagisce la tua pelle alla prima esposizione intensa al sole in estate, senza protezione.',
        campo('Fototipo (classificazione di Fitzpatrick)', fototipi, 'Non lo so: lascia vuoto, puoi tornare più tardi.'),
        campo('Colore naturale dei capelli (da giovane)', gruppo('capelli', [['neri', 'Neri'], ['castani', 'Castani'], ['biondi', 'Biondi'], ['rossi', 'Rossi'], ['grigi', 'Grigi/bianchi']], 'Capelli')),
        campo('Colore degli occhi', gruppo('occhi', [['scuri', 'Scuri'], ['verdi', 'Verdi'], ['azzurri', 'Azzurri/grigi']], 'Occhi')),
        campo('Efelidi (lentiggini)', gruppo('efelidi', [['nessuna', 'Nessuna'], ['poche', 'Poche'], ['molte', 'Molte']], 'Efelidi')),
        campo('Quanti nei hai sul corpo, circa?', gruppo('n_nevi', [['<25', 'Meno di 25'], ['25-49', '25–49'], ['50-99', '50–99'], ['100+', '100 o più']], 'Numero di nei'), 'Una stima va bene.'),
        campo('Un medico ti ha detto che hai nei atipici (displastici)?', gruppo('nevi_atipici', [['no', 'No'], ['si', 'Sì'], ['non so', 'Non so']], 'Nei atipici'))),
      sezione('Esposizione al sole', null,
        campo('Scottature con vesciche (soprattutto da bambino o ragazzo)', gruppo('scottature', [['mai', 'Mai'], ['poche', 'Poche'], ['molte', 'Molte']], 'Scottature')),
        campo('Lampade o lettini abbronzanti', gruppo('lampade', [['mai', 'Mai'], ['alcune', 'Qualche volta'], ['spesso', 'Spesso']], 'Lampade')),
        spunta('lavoro_aperto', 'Lavoro o faccio attività per molte ore all\'aperto')),
      sezione('Storia personale', null,
        contatore('melanomi_personali', 'Melanomi già diagnosticati a me', 'Conta solo i melanomi primari invasivi.'),
        spunta('altri_tumori_cutanei', 'Ho avuto altri tumori della pelle (basalioma, spinalioma)'),
        spunta('immunosoppressione', 'Sono immunosoppresso/a (trapianto o terapie che abbassano le difese)'),
        h('div', { class: 'campo-titolo spazio-su' }, 'Ho avuto (o ho) uno di questi tumori:'),
        h('div', { class: 'spunte-griglia' }, spunta('pers_pancreas', 'Tumore del pancreas'), spunta('pers_astrocitoma', 'Astrocitoma'),
          spunta('pers_uveale', 'Melanoma dell\'occhio (uveale)'), spunta('pers_mesotelioma', 'Mesotelioma'), spunta('pers_rene', 'Carcinoma del rene')),
        campo('Ho già fatto un test genetico per il melanoma?', gruppo('test_genetico', [['', 'Non indicato'], ['no', 'No'], ['si_positivo', 'Sì, positivo'], ['si_negativo', 'Sì, negativo'], ['si_non_informativo', 'Sì, non informativo']], 'Test genetico'))),
      sezione('Familiarità', 'Conta i parenti di sangue (non quelli acquisiti) dello stesso lato della famiglia, materno o paterno: è il criterio che usano i genetisti. Se non lo sai, chiedi a un familiare: queste informazioni sono molto utili.',
        h('label', { class: 'spunta grande' }, h('input', { type: 'checkbox', id: 'ck-fam', checked: !!p.fam_compilata, onchange: ev => cambia('fam_compilata', ev.target.checked) }), ' Ho verificato la mia storia familiare (anche se la risposta è «nessuno»)'),
        contatore('fam_melanoma_1grado', 'Parenti di 1° grado con melanoma', 'Genitori, fratelli, sorelle, figli.'),
        contatore('fam_melanoma_altri', 'Altri parenti con melanoma', 'Nonni, zii, nipoti (2° grado).'),
        contatore('fam_pancreas', 'Parenti con tumore del pancreas (in tutto)', 'Di qualsiasi grado di parentela.'),
        contatore('fam_pancreas_1grado', '…di cui di 1° grado'),
        contatore('fam_astrocitoma', 'Parenti con astrocitoma (tumore del cervello)'),
        contatore('fam_uveale', 'Parenti con melanoma dell\'occhio (uveale)'),
        contatore('fam_mesotelioma', 'Parenti con mesotelioma'),
        contatore('fam_rene', 'Parenti con carcinoma del rene')),
      sezione('Note', null, h('textarea', { class: 'campo', rows: 3, maxlength: 1000, placeholder: 'Altro che vuoi ricordare (allergie, farmaci fotosensibilizzanti, …)', value: p.note || '', oninput: ev => cambia('note', ev.target.value) })));

    /* ---------- riepilogo laterale ---------- */
    function disegnaRiepilogo() {
      const ri = S.utente.rischio, ge = S.utente.genetica;
      const colore = { nessuno: 'neutro', alcuni: 'giallo', attenzione: 'arancio' }[ri.livello];
      NT.riempi(riepilogo, 
        h('div', { class: 'scheda' }, h('div', { class: 'riga-spinner' }, NT.avatar(S.utente.nome, 44, S.utente), h('div', {}, h('strong', {}, S.utente.nome),
          h('div', { class: 'piccolo muted' }, [S.utente.eta !== null && S.utente.eta !== undefined ? S.utente.eta + ' anni' : null, S.utente.profilo.fototipo ? 'fototipo ' + FOTOTIPI[S.utente.profilo.fototipo - 1][1] : null].filter(Boolean).join(' · ') || 'Profilo da completare'))), stato),
        h('div', { class: 'scheda' }, h('h3', {}, 'Fattori di rischio presenti'),
          h('div', { class: 'banda ' + colore }, ri.testo),
          ri.presenti.length ? h('ul', { class: 'fattori' }, ri.presenti.map(f => h('li', {}, h('span', {}, f.etichetta, f.maggiore ? h('span', { class: 'chip chip-neutro' }, 'rilevante') : null), f.nota ? h('small', {}, f.nota) : null))) : null,
          h('p', { class: 'piccolo muted' }, ri.nota)),
        h('div', { class: 'scheda' }, h('h3', {}, 'Melanoma ereditario'),
          h('div', { class: 'banda ' + (ge.esito === 'criteri_soddisfatti' ? 'arancio' : 'neutro') }, ge.messaggio),
          h('a', { class: 'btn', href: '#/genetica' }, 'Vai alla sezione Genetica', NT.icona('freccia', 16))));
    }
    disegnaRiepilogo();
    NT.riempi(cont, h('div', { class: 'pagina' }, h('h1', {}, 'Profilo di ' + u.nome),
      h('div', { class: 'profilo-layout' }, form, riepilogo)));
  };
})();
'''
WEB_FILES["/v_profilo.js"] = ("text/javascript; charset=utf-8", _WEB_V_PROFILO_JS.encode("utf-8"))

_WEB_V_SCIENZA_JS = r'''/* ============================================================================
   v_scienza.js - letteratura scientifica (PubMed) e genetica del melanoma ereditario
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  const TIPI = {
    'Review': 'Revisione', 'Systematic Review': 'Revisione sistematica', 'Meta-Analysis': 'Meta-analisi',
    'Practice Guideline': 'Linea guida', 'Guideline': 'Linea guida', 'Consensus Development Conference': 'Consenso',
    'Randomized Controlled Trial': 'Studio randomizzato', 'Clinical Trial': 'Studio clinico', 'Observational Study': 'Studio osservazionale',
  };
  const fmtN = n => Number(n).toLocaleString('it-IT');

  function articolo(a) {
    const tipi = (a.tipi || []).map(t => TIPI[t]).filter(Boolean);
    return h('article', { class: 'articolo' },
      h('a', { href: a.url, target: '_blank', rel: 'noopener noreferrer', class: 'art-titolo' }, a.titolo || '(senza titolo)'),
      h('div', { class: 'art-meta' }, [a.autori, a.rivista, a.anno].filter(Boolean).join(' · ')),
      tipi.length ? h('div', { class: 'chips' }, [...new Set(tipi)].map(t => h('span', { class: 'chip chip-neutro' }, t))) : null,
      a.abstract ? h('details', { class: 'abstract' }, h('summary', {}, 'Leggi l\'abstract'), h('p', {}, a.abstract),
        h('div', { class: 'piccolo muted' }, 'In inglese · PubMed ', a.pmid, a.doi ? [' · ', NT.link('https://doi.org/' + a.doi, 'DOI')] : null)) : h('div', { class: 'piccolo muted' }, 'PubMed ' + a.pmid + ' · abstract non disponibile'));
  }

  function avvisoCache(d) {
    if (d.obsoleta) return h('div', { class: 'banda giallo' }, 'PubMed non è raggiungibile: mostro l\'ultima ricerca salvata il ' + d.data + '.');
    return null;
  }

  /* ============================== LETTERATURA ============================== */
  NT.viste.letteratura = async function (cont) {
    const uid = S.utente ? S.utente.id : 0;
    const temi = await NT.get('/api/letteratura/temi?utente=' + uid);
    let attivo = true, inCorso = false;
    NT.alCambioPagina(() => { attivo = false; });

    const sezioni = [];     // { id, titolo, corpo, stato }
    const temiEl = temi.map(t => {
      const corpiSez = t.sezioni.map(s => {
        const corpo = h('div', { class: 'sez-corpo' }, h('div', { class: 'piccolo muted' }, 'Non ancora scansionata.'));
        const testa = h('h3', {}, s.titolo);
        const box = h('div', { class: 'sez' }, testa, corpo);
        sezioni.push({ id: s.id, titolo: s.titolo, corpo, testa });
        return box;
      });
      return h('section', { class: 'scheda' }, h('h2', {}, t.titolo), corpiSez);
    });

    const progresso = h('span', { class: 'piccolo muted' }, '');
    const btnScan = h('button', { class: 'btn btn-pri', onclick: () => scansiona(false) }, NT.icona('cerca', 18), 'Scansiona la letteratura');
    const btnForza = h('button', { class: 'btn', title: 'Rifà la ricerca ignorando i risultati salvati', onclick: () => scansiona(true) }, 'Aggiorna');

    async function scansiona(forza) {
      if (inCorso) return;
      inCorso = true; btnScan.disabled = true; btnForza.disabled = true;
      let n = 0;
      for (const s of sezioni) {
        if (!attivo) break;
        n++; progresso.textContent = 'Sezione ' + n + ' di ' + sezioni.length + '…';
        NT.riempi(s.corpo, NT.caricamento('Cerco su PubMed…'));
        try {
          const d = await NT.get('/api/letteratura/sezione?id=' + encodeURIComponent(s.id) + '&utente=' + uid + (forza ? '&forza=1' : ''));
          NT.riempi(s.corpo, avvisoCache(d),
            h('div', { class: 'piccolo muted spazio-giu' }, fmtN(d.conteggio) + ' articoli trovati su PubMed · ricerca del ' + d.data + (d.da_cache ? ' (salvata)' : '')),
            d.articoli.length ? d.articoli.map(articolo) : h('div', { class: 'piccolo muted' }, 'Nessun articolo trovato.'));
        } catch (e) { NT.riempi(s.corpo, h('div', { class: 'errore-campo' }, e.message)); }
      }
      inCorso = false;
      if (!attivo) return;
      btnScan.disabled = false; btnForza.disabled = false; progresso.textContent = 'Scansione completata.';
    }

    /* ricerca libera */
    const q = h('input', { type: 'search', class: 'campo', placeholder: 'Cerca altro (es. "ugly duckling sign", "nail melanoma"…)', maxlength: 200 });
    const risLibera = h('div', { class: 'ris-libera' });
    const cerca = async () => {
      if (q.value.trim().length < 3) { NT.toast('Scrivi almeno 3 caratteri.', 'errore'); return; }
      NT.riempi(risLibera, NT.caricamento('Cerco su PubMed…'));
      try {
        const d = await NT.get('/api/letteratura/cerca?q=' + encodeURIComponent(q.value));
        NT.riempi(risLibera, avvisoCache(d), h('div', { class: 'piccolo muted spazio-giu' }, fmtN(d.conteggio) + ' articoli su melanoma e «' + q.value.trim() + '»'),
          d.articoli.length ? d.articoli.map(articolo) : h('div', { class: 'piccolo muted' }, 'Nessun articolo trovato.'));
      } catch (e) { NT.riempi(risLibera, h('div', { class: 'errore-campo' }, e.message)); }
    };
    q.addEventListener('keydown', e => { if (e.key === 'Enter') cerca(); });

    NT.riempi(cont, h('div', { class: 'pagina' },
      h('h1', {}, 'Letteratura scientifica'),
      h('p', { class: 'lead' }, 'Articoli recenti e rilevanti su come riconoscere i nei sospetti, sull\'affidabilità di app e intelligenza artificiale e sul melanoma ereditario. I risultati arrivano da PubMed, la banca dati pubblica della National Library of Medicine (USA).'),
      h('div', { class: 'scheda azione-scan' }, h('div', { class: 'riga-inline' }, btnScan, btnForza, progresso),
        h('p', { class: 'piccolo muted' }, 'Le ricerche partono da questo computer verso PubMed (nessun dato personale viene inviato). I risultati si salvano per 7 giorni. ' +
          'Le sezioni «scelte per te» usano parole legate al tuo profilo (per esempio fototipo o numero di nei): se preferisci non inviarle, non scansionare quella sezione.'),
        h('div', { class: 'riga-inline' }, h('button', { class: 'btn-testo', onclick: () => NT.dialogoABCDE() }, 'Promemoria ABCDE per riconoscere un neo'))),
      h('div', { class: 'scheda' }, h('h2', {}, 'Cerca nella letteratura'), h('div', { class: 'riga-inline' }, q, h('button', { class: 'btn', onclick: cerca }, 'Cerca')), risLibera),
      temiEl,
      h('div', { class: 'scheda piccolo muted' }, 'PubMed è un servizio della National Library of Medicine. Gli abstract sono mostrati per consultazione personale, in inglese; per il testo completo apri l\'articolo sul sito della rivista. ',
        'Gli articoli sono scelti da una ricerca automatica e non sono stati valutati da NeoTracker: leggili con il tuo medico.')));
  };

  /* ================================ GENETICA ================================ */
  NT.viste.genetica = async function (cont) {
    await NT.ricaricaUtente();
    const g = S.utente.genetica;
    const dati = await NT.get('/api/genetica/geni');
    let attivo = true, inCorso = false;
    NT.alCambioPagina(() => { attivo = false; });

    const cls = { criteri_soddisfatti: 'arancio', nessun_criterio: 'neutro', dati_insufficienti: 'giallo' }[g.esito];
    const criteri = h('ul', { class: 'criteri' }, g.criteri.map(c => h('li', { class: c.soddisfatto ? 'si' : 'no' },
      h('span', { class: 'esito-criterio', 'aria-label': c.soddisfatto ? 'Soddisfatto' : 'Non soddisfatto' }, c.soddisfatto ? NT.icona('ok', 16) : '—'),
      h('div', {}, h('strong', {}, c.titolo), h('div', { class: 'piccolo muted' }, c.spiegazione), h('div', { class: 'piccolo muted' }, 'Fonte: ' + c.fonte)))));

    const righe = dati.geni.map(ge => {
      const risultato = h('div', { class: 'gene-ris' }, h('span', { class: 'piccolo muted' }, 'Non ancora scansionato'));
      return { nome: ge.gene, risultato, riga: h('tr', {}, h('td', {}, h('strong', {}, ge.gene), g.geni_suggeriti.includes(ge.gene) ? h('div', { class: 'chip chip-neutro' }, 'nel pannello') : null),
        h('td', {}, ge.rischio), h('td', {}, ge.ruolo, risultato)) };
    });
    const progresso = h('span', { class: 'piccolo muted' }, '');
    const btn = h('button', { class: 'btn btn-pri', onclick: () => scansiona(false) }, NT.icona('cerca', 18), 'Scansiona la letteratura sui geni');
    const btnF = h('button', { class: 'btn', onclick: () => scansiona(true) }, 'Aggiorna');
    async function scansiona(forza) {
      if (inCorso) return;
      inCorso = true; btn.disabled = true; btnF.disabled = true;
      let n = 0;
      for (const r of righe) {
        if (!attivo) break;
        n++; progresso.textContent = 'Gene ' + n + ' di ' + righe.length + ' (' + r.nome + ')…';
        NT.riempi(r.risultato, NT.caricamento('Cerco…'));
        try {
          const d = await NT.get('/api/genetica/gene?nome=' + encodeURIComponent(r.nome) + (forza ? '&forza=1' : ''));
          NT.riempi(r.risultato, h('div', { class: 'gene-conta' }, h('strong', {}, fmtN(d.conteggio)), ' studi su PubMed', d.obsoleta ? ' (ricerca salvata del ' + d.data + ')' : ''),
            d.articoli.length ? h('details', { class: 'abstract' }, h('summary', {}, 'Studi più pertinenti'), d.articoli.map(articolo)) : null);
        } catch (e) { NT.riempi(r.risultato, h('div', { class: 'errore-campo' }, e.message)); }
      }
      inCorso = false;
      if (attivo) { btn.disabled = false; btnF.disabled = false; progresso.textContent = 'Scansione completata.'; }
    }

    NT.riempi(cont, h('div', { class: 'pagina' },
      h('h1', {}, 'Melanoma ereditario e test genetico'),
      h('p', { class: 'lead' }, 'Circa il 5-10% dei melanomi si presenta in famiglie con una predisposizione ereditaria (Leachman 2009). Qui trovi i criteri che usano gli specialisti per decidere se proporre una consulenza genetica, i geni coinvolti e la letteratura su ciascuno.'),
      h('section', { class: 'scheda' }, h('h2', {}, 'I tuoi dati rispetto ai criteri'),
        h('div', { class: 'banda ' + cls }, g.messaggio),
        g.esito !== 'dati_insufficienti' ? criteri : null,
        h('div', { class: 'azioni sinistra' }, h('a', { class: 'btn', href: '#/profilo' }, g.esito === 'dati_insufficienti' ? 'Compila la familiarità nel Profilo' : 'Modifica i dati nel Profilo')),
        h('p', { class: 'piccolo muted' }, 'Criteri semplificati, a scopo informativo. Il test genetico riguarda una piccola minoranza di persone e non è un esame di routine: è lo specialista a decidere se e quale test proporre, di norma dopo una consulenza genetica e partendo, quando possibile, da un familiare che ha avuto la malattia.')),
      h('section', { class: 'scheda' }, h('h2', {}, 'Cosa sapere prima di un test genetico'),
        h('ul', { class: 'punti' },
          h('li', {}, 'Un risultato positivo indica un rischio più alto, non la certezza di ammalarsi; un risultato negativo non azzera il rischio (molte famiglie non hanno una variante identificabile).'),
          h('li', {}, 'Il risultato riguarda anche i familiari di sangue: per questo la consulenza prima e dopo il test è parte del percorso.'),
          h('li', {}, 'Le linee guida raccomandano il test solo dopo una selezione accurata dei candidati e un\'adeguata consulenza (Rossi 2019); l\'uso dei pannelli multigene è ancora discusso.'),
          h('li', {}, 'Con o senza test, per chi ha una storia familiare restano fondamentali la protezione dal sole, l\'autoesame della pelle e i controlli dermatologici periodici.'))),
      h('section', { class: 'scheda' }, h('h2', {}, 'I geni più studiati'),
        h('div', { class: 'azione-scan' }, h('div', { class: 'riga-inline' }, btn, btnF, progresso)),
        h('div', { class: 'tabella-scroll' }, h('table', { class: 'tabella' }, h('thead', {}, h('tr', {}, h('th', {}, 'Gene'), h('th', {}, 'Rischio associato'), h('th', {}, 'Ruolo e letteratura'))), h('tbody', {}, righe.map(r => r.riga))))),
      h('section', { class: 'scheda' }, h('h2', {}, 'Fonti'), h('ul', { class: 'fonti' }, dati.fonti.map(f => h('li', {}, NT.link(f.url, f.titolo)))),
        h('p', { class: 'piccolo muted' }, 'NeoTracker non è un servizio di consulenza genetica. Per una valutazione personale rivolgiti al dermatologo o a un centro di genetica oncologica.'))));
  };
})();
'''
WEB_FILES["/v_scienza.js"] = ("text/javascript; charset=utf-8", _WEB_V_SCIENZA_JS.encode("utf-8"))

_WEB_V_UTENTI_JS = r'''/* ============================================================================
   v_utenti.js - scelta e gestione degli utenti (l'app e' multi-utente)
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  function dialogoNome(titolo, valore, testoOk) {
    return new Promise(res => {
      const campo = h('input', { type: 'text', class: 'campo', maxlength: 60, value: valore || '', placeholder: 'Nome o soprannome', autocomplete: 'off' });
      const errore = h('div', { class: 'errore-campo' });
      const invia = () => {
        const v = campo.value.trim();
        if (!v) { errore.textContent = 'Scrivi un nome.'; return; }
        res(v); NT.chiudiDialogo();
      };
      campo.addEventListener('keydown', e => { if (e.key === 'Enter') invia(); });
      const d = NT.apriDialogo(h('div', {}, h('h3', {}, titolo), campo, errore,
        h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => { res(null); NT.chiudiDialogo(); } }, 'Annulla'),
          h('button', { class: 'btn btn-pri', onclick: invia }, testoOk || 'Salva'))));
      d.addEventListener('close', () => res(null), { once: true });
      campo.focus(); campo.select();
    });
  }

  NT.viste.utenti = async function (cont) {
    S.utenti = await NT.get('/api/utenti');

    async function nuovo() {
      const nome = await dialogoNome('Nuovo utente', '', 'Crea utente');
      if (!nome) return;
      try {
        const r = await NT.api('POST', '/api/utenti', { nome });
        S.utenti = await NT.get('/api/utenti');
        await NT.scegliUtente(r.id, false);
        NT.toast('Utente creato. Compila il profilo: serve a contestualizzare i risultati.', 'ok');
        NT.vai('profilo');
      } catch (e) { NT.errore(e); }
    }
    async function rinomina(u) {
      const nome = await dialogoNome('Rinomina utente', u.nome, 'Salva');
      if (!nome || nome === u.nome) return;
      try {
        await NT.api('PATCH', '/api/utenti/' + u.id, { nome });
        if (S.utente && S.utente.id === u.id) await NT.ricaricaUtente();
        NT.vai('utenti');
      } catch (e) { NT.errore(e); }
    }
    async function elimina(u) {
      const si = await NT.conferma('Eliminare «' + u.nome + '»?',
        'Verranno cancellati per sempre il profilo, tutti i nei, tutte le foto e tutti i rapporti di questo utente. L\'operazione non si può annullare.',
        { si: 'Elimina definitivamente', pericolo: true, scrivi: u.nome });
      if (!si) return;
      try {
        await NT.api('DELETE', '/api/utenti/' + u.id, { conferma: u.nome });
        if (S.utente && S.utente.id === u.id) { S.utente = null; S.nei = []; NT.ls.scrivi('nt_utente', ''); }
        NT.toast('Utente eliminato.', 'ok');
        NT.vai('utenti');
      } catch (e) { NT.errore(e); }
    }

    const schede = S.utenti.map(u => h('div', { class: 'utente-card' + (S.utente && S.utente.id === u.id ? ' corrente' : '') },
      h('button', { class: 'utente-apri', onclick: () => NT.scegliUtente(u.id).catch(NT.errore) },
        NT.avatar(u.nome, 56, u),
        h('span', { class: 'utente-info' }, h('strong', {}, u.nome),
          h('span', { class: 'sotto' }, u.n_nevi + (u.n_nevi === 1 ? ' neo' : ' nei') + (u.eta !== null && u.eta !== undefined ? ' · ' + u.eta + ' anni' : '')))),
      h('div', { class: 'utente-azioni' },
        h('button', { class: 'btn-testo', onclick: () => rinomina(u) }, 'Rinomina'),
        h('button', { class: 'btn-testo pericolo', onclick: () => elimina(u) }, 'Elimina'))));

    cont.replaceChildren(h('div', { class: 'pagina stretta' },
      h('h1', {}, S.utenti.length ? 'Chi sei?' : 'Benvenuto in NeoTracker'),
      h('p', { class: 'lead' }, S.utenti.length
        ? 'Scegli il tuo profilo: ogni persona ha la propria mappa dei nei, le proprie foto e i propri dati.'
        : 'Questo programma ti aiuta a tenere traccia dei tuoi nei nel tempo: li segni su una mappa del corpo, ne conservi le foto con la data e li fai analizzare da più metodi. Inizia creando il tuo utente.'),
      h('div', { class: 'utenti-griglia' }, schede,
        h('button', { class: 'utente-card nuovo', onclick: nuovo }, h('span', { class: 'piu' }, NT.icona('piu', 28)), h('strong', {}, 'Nuovo utente'))),
      h('div', { class: 'nota-privacy' }, NT.icona('ok', 16),
        h('span', {}, 'Tutti i dati restano su questo computer, nella cartella ', h('code', {}, S.stato.cartella_dati || ''),
          '. Nulla viene inviato online, tranne le richieste che attivi tu (meteo UV, letteratura PubMed, SkinSense).'))));
  };
})();
'''
WEB_FILES["/v_utenti.js"] = ("text/javascript; charset=utf-8", _WEB_V_UTENTI_JS.encode("utf-8"))

_WEB_V_UV_JS = r'''/* ============================================================================
   v_uv.js - indice UV di oggi nel luogo scelto (Open-Meteo di default, OpenWeather se scelto)
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  /* Categorie dell'OMS (stesse soglie e colori del programma Python) */
  const CAT = [[11, 'Estremo', '#8e44ad'], [8, 'Molto alto', '#d9261c'], [6, 'Alto', '#f28c00'], [3, 'Moderato', '#e8c400'], [0, 'Basso', '#3f9c35']];
  const cat = v => CAT.find(c => v >= c[0]) || CAT[CAT.length - 1];
  const FOTOTIPI = ['I', 'II', 'III', 'IV', 'V', 'VI'];

  function grafico(ore) {
    const W = 720, H = 230, sx = 44, dx = 12, su = 18, giu = 40;
    const larg = (W - sx - dx) / ore.length;
    const massimo = Math.max(11, Math.ceil(Math.max(...ore.map(o => o.uvi))) + 1);
    const y = v => su + (H - su - giu) * (1 - v / massimo);
    let s = '<svg class="grafico-uv" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Indice UV ora per ora nelle prossime 24 ore">';
    for (let t = 0; t <= massimo; t += (massimo > 12 ? 4 : 2)) {
      s += '<line class="gl" x1="' + sx + '" x2="' + (W - dx) + '" y1="' + y(t) + '" y2="' + y(t) + '"/><text class="gt" x="' + (sx - 8) + '" y="' + (y(t) + 4) + '" text-anchor="end">' + t + '</text>';
    }
    ore.forEach((o, i) => {
      const x = sx + i * larg + larg * 0.14, w = larg * 0.72, c = cat(o.uvi);
      const alt = Math.max(o.uvi > 0 ? 2 : 0, y(0) - y(o.uvi));
      s += '<rect x="' + x.toFixed(1) + '" y="' + (y(0) - alt).toFixed(1) + '" width="' + w.toFixed(1) + '" height="' + alt.toFixed(1) + '" rx="2" fill="' + c[2] + '"><title>' +
        NT.esc(o.giorno + ' ore ' + o.ora + ': indice UV ' + NT.num(o.uvi) + ' (' + c[1] + ')') + '</title></rect>';
      const cambio = i === 0 || o.giorno !== ore[i - 1].giorno;
      const vicinoCambio = [-2, -1, 1, 2].some(k => ore[i + k] && ore[i + k - 1] && ore[i + k].giorno !== ore[i + k - 1].giorno);
      if (cambio || (i % 3 === 0 && !vicinoCambio)) {
        s += '<text class="gt" x="' + (x + w / 2).toFixed(1) + '" y="' + (H - giu + 16) + '" text-anchor="middle">' + NT.esc(o.ora.slice(0, 2)) + '</text>';
        if (i === 0 || o.giorno !== ore[i - 1].giorno) s += '<text class="gt g6t" x="' + (x + w / 2).toFixed(1) + '" y="' + (H - giu + 32) + '" text-anchor="middle">' + NT.esc(o.giorno) + '</text>';
      }
    });
    s += '<line class="gline" x1="' + sx + '" x2="' + (W - dx) + '" y1="' + y(3) + '" y2="' + y(3) + '" stroke-dasharray="5 4"/>' +
      '<text class="gt g6t" x="' + (W - dx) + '" y="' + (y(3) - 5) + '" text-anchor="end">3 = da qui l\'OMS consiglia protezione</text></svg>';
    return NT.html(s);
  }

  NT.viste.uv = async function (cont) {
    S.imp = await NT.get('/api/impostazioni');
    let attivo = true;
    NT.alCambioPagina(() => { attivo = false; });
    const barra = h('section', { class: 'scheda' });
    const risultato = h('div', { class: 'uv-risultato' });

    /* ---------------- scelta del luogo ---------------- */
    async function salvaPos(lat, lon, nome) {
      try {
        S.imp = await NT.api('PUT', '/api/impostazioni', { lat, lon, localita: nome });
        NT.toast('Posizione salvata: ' + nome, 'ok');
        disegnaBarra(); carica();
      } catch (e) { NT.errore(e); }
    }
    function rileva() {
      if (!navigator.geolocation) { NT.toast('Questo browser non offre la geolocalizzazione: cerca la città per nome.', 'errore'); return; }
      NT.toast('Chiedo la posizione al browser… (potrebbe comparire una richiesta di permesso)', 'info');
      navigator.geolocation.getCurrentPosition(
        p => salvaPos(p.coords.latitude, p.coords.longitude, 'La mia posizione (' + NT.num(p.coords.latitude, 2) + '; ' + NT.num(p.coords.longitude, 2) + ')'),
        err => NT.toast(err.code === 1 ? 'Permesso negato. Puoi cercare la città per nome oppure usare la stima da indirizzo internet.' : 'Il computer non riesce a determinare la posizione. Cerca la città per nome.', 'errore'),
        { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 });
    }
    async function daIP() {
      const ok = await NT.conferma('Stima dall\'indirizzo internet', 'Per stimare la città il programma contatta il servizio gratuito ipwho.is, che vede il tuo indirizzo internet. La precisione è quella della città (a volte sbaglia). Procedo?', { si: 'Sì, stima la città' });
      if (!ok) return;
      try { const r = await NT.get('/api/posizione-ip'); await salvaPos(r.lat, r.lon, r.nome || 'Posizione stimata'); }
      catch (e) { NT.errore(e); }
    }
    const campoCitta = h('input', { type: 'search', class: 'campo', placeholder: 'Cerca una città (es. Torino)', maxlength: 80, 'aria-label': 'Nome della città' });
    const elencoCitta = h('div', { class: 'citta-elenco' });
    async function cercaCitta() {
      const q = campoCitta.value.trim();
      if (q.length < 2) return;
      NT.riempi(elencoCitta, NT.caricamento('Cerco…'));
      try {
        const r = await NT.get('/api/localita?q=' + encodeURIComponent(q));
        NT.riempi(elencoCitta, r.length ? r.map(c => h('button', { class: 'btn citta-voce', onclick: () => salvaPos(c.lat, c.lon, c.nome) }, NT.icona('posizione', 16), c.nome))
          : h('div', { class: 'piccolo muted' }, 'Nessuna città trovata con questo nome.'));
      } catch (e) { NT.riempi(elencoCitta, h('div', { class: 'errore-campo' }, e.message)); }
    }
    campoCitta.addEventListener('keydown', e => { if (e.key === 'Enter') cercaCitta(); });

    function disegnaBarra() {
      const ho = S.imp.lat !== null && S.imp.lat !== undefined;
      NT.riempi(barra, 
        h('div', { class: 'uv-posizione' }, NT.icona('posizione', 22),
          h('div', {}, h('strong', {}, ho ? (S.imp.localita || 'Posizione impostata') : 'Posizione non impostata'),
            h('div', { class: 'piccolo muted' }, ho ? NT.num(S.imp.lat, 3) + '; ' + NT.num(S.imp.lon, 3) : 'Scegli dove ti trovi per vedere l\'indice UV di oggi.'))),
        h('div', { class: 'riga-inline spazio-su' }, h('button', { class: 'btn btn-pri', onclick: rileva }, NT.icona('mirino', 18), 'Rileva la mia posizione'),
          campoCitta, h('button', { class: 'btn', onclick: cercaCitta }, 'Cerca')),
        elencoCitta,
        h('div', { class: 'piccolo muted spazio-su' }, 'La posizione resta salvata solo su questo computer; viene inviata al servizio meteo (coordinate arrotondate) per ottenere l\'indice UV. ',
          h('button', { class: 'btn-testo', onclick: daIP }, 'Non riesci? Stima dall\'indirizzo internet')));
    }

    /* ---------------- indice UV ---------------- */
    async function carica() {
      if (S.imp.lat === null || S.imp.lat === undefined) {
        NT.riempi(risultato, NT.vuoto('Manca la posizione', 'Scegli la città qui sopra: poi vedrai l\'indice UV di oggi, ora per ora.'));
        return;
      }
      NT.riempi(risultato, NT.caricamento('Scarico l\'indice UV…'));
      const ft = S.utente && S.utente.profilo.fototipo ? S.utente.profilo.fototipo : 0;
      let d;
      try { d = await NT.get('/api/uv?fototipo=' + ft + '&localita=' + encodeURIComponent(S.imp.localita || '')); }
      catch (e) { if (attivo) NT.riempi(risultato, h('div', { class: 'scheda errore-pagina' }, h('h2', {}, 'Indice UV non disponibile'), h('p', {}, e.message), h('button', { class: 'btn', onclick: carica }, 'Riprova'))); return; }
      if (!attivo) return;
      const cm = d.categoria_max, co = d.categoria_ora;
      const sc = d.scottatura_max;
      NT.riempi(risultato, 
        d.avviso ? h('div', { class: 'banda giallo' }, d.avviso, ' ', h('a', { href: '#/impostazioni' }, 'Impostazioni')) : null,
        h('section', { class: 'scheda uv-verdetto uv-' + d.verdetto.livello },
          h('div', { class: 'uv-titolo' }, h('h2', {}, d.verdetto.titolo), h('p', {}, d.verdetto.testo)),
          h('div', { class: 'uv-numeri' },
            h('div', { class: 'uv-num' }, h('span', { class: 'uv-val', style: { background: co.colore, color: co.colore === '#e8c400' ? '#222' : '#fff' } }, NT.num(d.uvi_ora)), h('div', {}, h('strong', {}, 'Adesso'), h('div', { class: 'piccolo' }, co.nome))),
            h('div', { class: 'uv-num' }, h('span', { class: 'uv-val', style: { background: cm.colore, color: cm.colore === '#e8c400' ? '#222' : '#fff' } }, NT.num(d.uvi_max)), h('div', {}, h('strong', {}, 'Massimo di oggi'), h('div', { class: 'piccolo' }, cm.nome))))),
        h('section', { class: 'scheda' }, h('h2', {}, 'Prossime ' + d.ore.length + ' ore'), d.ore.length ? grafico(d.ore) : NT.vuoto('Dati orari non disponibili'),
          h('div', { class: 'piccolo muted' }, 'Fonte: ' + d.fonte + ' · aggiornato ' + d.aggiornato + (d.fuso ? ' · ' + d.fuso : ''),
            d.fonte === 'Open-Meteo' ? [' · ', NT.link('https://open-meteo.com/', 'Open-Meteo.com'), ' (CC BY 4.0)'] : null)),
        h('section', { class: 'scheda' }, h('h2', {}, 'Cosa fare'), h('p', {}, cm.consiglio),
          sc ? h('div', { class: 'banda neutro' }, h('strong', {}, 'Con il tuo fototipo (' + FOTOTIPI[S.utente.profilo.fototipo - 1] + ')'), ': a cielo sereno e senza protezione, al picco di oggi la pelle può arrossarsi in ',
            h('strong', {}, sc.testo), '. È una stima prudente che usa la dose minima di eritema più bassa del tuo fototipo; con riflessi (acqua, neve, sabbia), quota o pelle già arrossata il tempo si accorcia.')
            : h('div', { class: 'piccolo muted' }, S.utente ? ['Per vedere quanto sole ti scotta, indica il fototipo nel ', h('a', { href: '#/profilo' }, 'Profilo'), '.'] : 'Scegli un utente e indica il suo fototipo per vedere quanti minuti servono per scottarsi.'),
          h('ul', { class: 'punti' },
            h('li', {}, 'Le ore centrali (circa 11-16) sono quelle con l\'indice più alto.'),
            h('li', {}, 'Le nuvole sottili non fermano gran parte degli UV: l\'indice può restare alto anche con il cielo velato.'),
            h('li', {}, 'Chi ha tanti nei, nei atipici o una storia di melanoma dovrebbe proteggersi anche con indici moderati.'),
            h('li', {}, 'L\'indice è una previsione: il valore reale dipende da nuvole, quota e riflessi.'))),
        h('section', { class: 'scheda' }, h('h2', {}, 'Come si legge l\'indice UV'),
          h('div', { class: 'legenda-uv' }, CAT.slice().reverse().map(c => h('span', { class: 'chip', style: { background: c[2], color: c[0] === 3 ? '#222' : '#fff' } }, c[1] + ' (' + (c[0] === 11 ? '11+' : c[0] + '–' + ({ 0: 2, 3: 5, 6: 7, 8: 10 }[c[0]])) + ')'))),
          h('p', { class: 'piccolo muted' }, 'Soglie e colori della scala internazionale dell\'OMS. Fonti:'),
          h('ul', { class: 'fonti' }, d.fonti.map(f => h('li', {}, NT.link(f.url, f.titolo))))));
    }

    disegnaBarra();
    NT.riempi(cont, h('div', { class: 'pagina' },
      h('h1', {}, 'Indice UV di oggi'),
      h('p', { class: 'lead' }, 'I raggi ultravioletti sono il principale fattore di rischio modificabile per il melanoma. Qui vedi quanto sono forti oggi dove ti trovi.'),
      barra, risultato));
    carica();
  };
})();
'''
WEB_FILES["/v_uv.js"] = ("text/javascript; charset=utf-8", _WEB_V_UV_JS.encode("utf-8"))



# ==========================================================================================
# 7. AVVIO: apre la finestra dell'app, tiene acceso il motore e lo spegne quando chiudi
# ==========================================================================================
# Come funziona, in breve (parole semplici):
#   1. Il motore (questo programma) parte e si mette in ascolto sul tuo PC (127.0.0.1).
#   2. Apre Microsoft Edge (o Chrome, se Edge non c'è) in modalità "app": è una finestra
#      normale di Windows, SENZA barra degli indirizzi e SENZA schede, con l'icona di NeoTracker
#      nella barra delle applicazioni. Edge e Chrome sono già sul tuo PC: non si installa nulla.
#   3. La finestra usa un suo profilo separato (cartella "profilo_finestra" dentro i dati di
#      NeoTracker), così non si mescola con la tua navigazione normale (cronologia, password...).
#   4. Quando chiudi la finestra, il motore se ne accorge (vedi 5c) e si spegne da solo.
#   5. Se Edge/Chrome non si trovano, si apre il browser predefinito (funziona uguale,
#      ma con la barra degli indirizzi).

NOME_FINESTRA = "NeoTracker"                      # titolo della finestra (uguale al <title> della pagina)
_USCITA_ORIGINALE = {"senza_console": False}      # diventa True se il programma è partito senza finestra nera


class Server(ThreadingHTTPServer):
    daemon_threads = True                         # i thread non bloccano la chiusura
    allow_reuse_address = (os.name != "nt")       # su Windows questa opzione permetterebbe DUE server sulla stessa porta
    chiusura_richiesta = False                    # diventa True se premi "Esci" nell'app

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fine_sorveglianza = threading.Event()   # serve a fermare il "sorvegliante" quando il server si chiude


# ------------------------------------------------------------------------------------------
# 7a. Se non c'è la finestra nera (avvio con pythonw), scrivere su un file invece che a schermo
# ------------------------------------------------------------------------------------------
def percorso_log():
    return Path(CARTELLA_DATI) / "neotracker.log"


def prepara_uscita_testo():
    """Quando l'icona avvia il programma SENZA finestra nera, Python non ha uno schermo dove
    scrivere (sys.stdout vale None) e ogni print() darebbe errore. Qui colleghiamo schermo ed
    errori a un file di testo (neotracker.log nella cartella dei dati): se qualcosa non va,
    lì c'è scritto cosa. Se invece la finestra nera c'è (o sei in Spyder) non cambia nulla."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    _USCITA_ORIGINALE["senza_console"] = True
    log = percorso_log()
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        if log.exists() and log.stat().st_size > 500_000:          # file troppo grosso: tengo solo il vecchio
            vecchio = log.with_name("neotracker.vecchio.log")
            if vecchio.exists():
                vecchio.unlink()
            log.rename(vecchio)
        f = open(log, "a", encoding="utf-8", errors="replace", buffering=1)   # buffering=1: scrive riga per riga
        f.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S}  avvio NeoTracker {VERSIONE} =====\n")
    except Exception:
        f = open(os.devnull, "w", encoding="utf-8")               # nel peggiore dei casi, buttiamo il testo
    if sys.stdout is None:
        sys.stdout = f
    if sys.stderr is None:
        sys.stderr = f


def mostra_errore(titolo, testo):
    """Mostra un problema grave. Con la finestra nera basta scriverlo; senza finestra nera
    (icona sul Desktop) nessuno leggerebbe il log, quindi compare una finestrella di Windows."""
    print(f"\n{titolo}\n{testo}")
    if os.name == "nt" and _USCITA_ORIGINALE["senza_console"]:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f"{testo}\n\nDettagli in:\n{percorso_log()}", titolo, 0x10)   # 0x10 = icona di errore
        except Exception:
            pass


# ------------------------------------------------------------------------------------------
# 7b. Trovare Edge/Chrome e aprire la finestra "app"
# ------------------------------------------------------------------------------------------
def trova_browser_app():
    """Percorso di Edge o Chrome (None se non si trovano). Edge per primo: c'è sempre su Windows 10/11."""
    forzato = os.environ.get("NEOTRACKER_BROWSER", "")           # usato nei test per simulare un browser
    if forzato and Path(forzato).exists():
        return forzato
    candidati = []
    if os.name == "nt":
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        locale = os.environ.get("LocalAppData", str(Path.home() / "AppData" / "Local"))
        candidati = [
            Path(pf86) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(pf) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(pf) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(pf86) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(locale) / "Google" / "Chrome" / "Application" / "chrome.exe",
        ]
    for c in candidati:
        if c.exists():
            return str(c)
    # Ultimo tentativo: i programmi raggiungibili dal "percorso di sistema" (utile anche su Linux/Mac)
    for nome in ("msedge", "microsoft-edge", "chrome", "google-chrome", "chromium", "chromium-browser"):
        trovato = shutil.which(nome)
        if trovato:
            return trovato
    return None


def argomenti_finestra(exe, url):
    """L'elenco di parole con cui si lancia Edge/Chrome. Ogni riga è spiegata."""
    profilo = Path(CARTELLA_DATI) / "profilo_finestra"
    return [
        exe,
        f"--app={url}",                       # modalità app: niente barra degli indirizzi né schede
        f"--user-data-dir={profilo}",         # profilo separato: non tocca il tuo Edge/Chrome di tutti i giorni
        "--no-first-run",                     # niente schermate di benvenuto al primo avvio del profilo
        "--no-default-browser-check",         # non chiedere di diventare il browser predefinito
        "--hide-crash-restore-bubble",        # niente avviso "il browser non si è chiuso correttamente"
        "--window-size=1320,900",             # grandezza iniziale (poi Windows ricorda l'ultima usata)
    ]


def apri_finestra(url):
    """Apre NeoTracker nella sua finestra. True se qualcosa si è aperto."""
    exe = trova_browser_app()
    if exe:
        try:
            if os.name == "nt":
                # DETACHED_PROCESS: il browser vive per conto suo, anche se questo programma si chiude.
                flag = getattr(subprocess, "DETACHED_PROCESS", 0x8) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
                subprocess.Popen(argomenti_finestra(exe, url), creationflags=flag, close_fds=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(argomenti_finestra(exe, url), start_new_session=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            print(f"Non riesco ad aprire la finestra con {exe}: {e}")
    # Piano B: il browser predefinito, in una scheda normale. Funziona, ma si vede la barra degli indirizzi.
    print("Edge/Chrome non trovati (o non partono): apro il browser predefinito.")
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


def porta_in_primo_piano():
    """Se la finestra di NeoTracker è già aperta (magari ridotta a icona), la riporta davanti.
    Solo Windows. True se l'ha trovata. Qualunque problema -> False e si aprirà una finestra nuova."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        # Diciamo a Python che i "numeri di finestra" sono puntatori a 64 bit (altrimenti si troncano).
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        trovate = []
        # "TipoGuarda" descrive la funzione che Windows richiama una volta per ogni finestra aperta.
        TipoGuarda = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows.argtypes = [TipoGuarda, wintypes.LPARAM]

        @TipoGuarda
        def guarda(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            lung = user32.GetWindowTextLengthW(hwnd)
            if lung <= 0:
                return True
            titolo = ctypes.create_unicode_buffer(lung + 1)
            user32.GetWindowTextW(hwnd, titolo, lung + 1)
            classe = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, classe, 256)
            # Cerchiamo una finestra di Edge/Chrome (classe Chrome_WidgetWin_1) intitolata "NeoTracker":
            # la classe evita di confondersi con, per esempio, una cartella chiamata "NeoTracker".
            if titolo.value == NOME_FINESTRA and classe.value == "Chrome_WidgetWin_1":
                trovate.append(hwnd)
            return True

        user32.EnumWindows(guarda, 0)
        if not trovate:
            return False
        hwnd = trovate[0]
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)                           # 9 = SW_RESTORE: toglie la riduzione a icona
        user32.keybd_event(0x12, 0, 0, 0)                         # piccolo trucco (premere e rilasciare Alt) che permette a
        user32.keybd_event(0x12, 0, 2, 0)                         # Windows di accettare il cambio di finestra in primo piano
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def _strumento_windows(relativo):
    """Percorso completo di uno strumento di Windows (cartella System32). Così non si rischia di lanciare
    per errore un programma con lo stesso nome trovato in un'altra cartella (per esempio quella corrente)."""
    radice = os.environ.get("SystemRoot") or r"C:\Windows"
    return str(Path(radice) / "System32" / relativo)


def chiudi_finestra_app():
    """Chiude la finestra dell'app (solo i processi del nostro profilo separato: il tuo Edge/Chrome
    di tutti i giorni NON viene toccato). Serve quando premi "Esci" dentro l'app."""
    profilo = str(Path(CARTELLA_DATI) / "profilo_finestra")
    try:
        if os.name == "nt":
            # PowerShell cerca i processi la cui riga di comando contiene la cartella del profilo
            # separato e li chiude. Il percorso passa tramite una variabile d'ambiente (più sicuro
            # che incollarlo nel comando). "$PID" è PowerShell stesso: lo escludiamo.
            comando = ("$p = $env:NT_PROFILO; "
                       "Get-CimInstance Win32_Process | "
                       "Where-Object { $_.CommandLine -and $_.CommandLine.Contains($p) -and $_.ProcessId -ne $PID } | "
                       "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
            subprocess.run([_strumento_windows(r"WindowsPowerShell\v1.0\powershell.exe"), "-NoProfile", "-NonInteractive", "-Command", comando],
                           env=dict(os.environ, NT_PROFILO=profilo), stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
        elif shutil.which("pkill"):
            subprocess.run(["pkill", "-f", profilo], stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    except Exception:
        pass                                                      # se non riesce, la finestra resta: la chiudi tu con la X


# ------------------------------------------------------------------------------------------
# 7c. Il "sorvegliante": ogni secondo controlla se la finestra è stata chiusa
# ------------------------------------------------------------------------------------------
def sorveglia_finestra(server, passo=1.0):
    """Gira in un thread a parte. Quando la finestra è chiusa (e nessuna analisi è in corso) ferma il server."""
    ultimo_giro = time.monotonic()
    while not server.fine_sorveglianza.wait(passo):               # aspetta 1 secondo, poi controlla
        adesso = time.monotonic()
        if adesso - ultimo_giro > 15:
            # Il "secondo" è durato più di 15: il PC era in sospensione. Durante il sonno la pagina non
            # poteva battere, quindi non consideriamo la finestra chiusa.
            STATO_FINESTRA.dopo_sospensione(adesso)
        ultimo_giro = adesso
        if STATO_FINESTRA.da_spegnere(adesso, analisi_attiva()):
            print("La finestra di NeoTracker è stata chiusa: spengo il programma.")
            server.shutdown()                                     # fa uscire serve_forever() nel thread principale
            return


# ------------------------------------------------------------------------------------------
# 7d. Avvio vero e proprio
# ------------------------------------------------------------------------------------------
def ping_server():
    """Se su questa porta c'è già un NeoTracker, ne restituisce lo stato (un dizionario); altrimenti None."""
    try:
        # Controllo di sicurezza (bandit B310): indirizzo fisso, questo computer.
        with urllib.request.urlopen(f"http://{INDIRIZZO}:{PORTA}/api/ping", timeout=2) as r:   # nosec B310
            d = json.loads(r.read().decode("utf-8"))
            return d if d.get("app") == "NeoTracker" else None
    except Exception:
        return None


def gia_in_esecuzione():
    """True se su questa porta c'è già un NeoTracker (es. hai cliccato due volte l'icona)."""
    return ping_server() is not None


def ferma_analisi_in_corso():
    """Se chiudi l'app mentre sta analizzando una foto, ferma anche l'analisi (con tutti i suoi processi)."""
    p = _processo_attuale.get("popen")
    if p is not None and p.poll() is None:
        try:
            if os.name == "nt":
                subprocess.run([_strumento_windows("taskkill.exe"), "/PID", str(p.pid), "/T", "/F"], capture_output=True, stdin=subprocess.DEVNULL,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
            else:
                p.terminate()
        except Exception:
            pass


def avvia():
    try:
        CARTELLA_DATI.mkdir(parents=True, exist_ok=True)
        prepara_uscita_testo()                                    # prima di qualunque print()
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        url = f"http://{INDIRIZZO}:{PORTA}/"
        inizializza_db()

        # ---- caso 1: NeoTracker è già acceso (hai cliccato l'icona una seconda volta) ----
        stato = ping_server()
        if stato is not None:
            if stato.get("finestra_aperta") and porta_in_primo_piano():
                print("NeoTracker è già aperto: ho portato la finestra davanti.")
            else:
                # Il programma acceso accetta solo chi presenta la sua chiave di sessione (vedi 6c-bis):
                # la leggiamo dal file che ha scritto all'avvio.
                chiave = leggi_token_da_file()
                if stato.get("protetto") and not chiave:
                    mostra_errore("NeoTracker è già acceso",
                                  "Non riesco ad aprire una nuova finestra perché manca la chiave di sessione.\n"
                                  "Chiudi NeoTracker (dal Task Manager, processo Python) e riaprilo dall'icona.")
                    return
                print("NeoTracker è già acceso: apro una finestra.")
                apri_finestra(url + (f"?avvio={chiave}" if chiave else ""))
            return

        # ---- caso 2: avvio normale ----
        try:
            server = Server((INDIRIZZO, PORTA), Gestore)
        except OSError as e:
            mostra_errore("NeoTracker non si avvia",
                          f"Non riesco a usare la porta {PORTA} ({e}).\n"
                          "Un altro programma la sta usando. Chiudilo oppure cambia PORTA in cima al file neotracker.py.")
            return
        STATO_FINESTRA.azzera()                                   # il conto delle pagine aperte riparte da zero
        scrivi_token_su_file()                                    # la chiave di questa sessione (serve a una seconda icona cliccata)

        print("=" * 70)
        print(f" NeoTracker {VERSIONE} è attivo:  {url}")
        print(f" I tuoi dati sono in: {CARTELLA_DATI}")
        print("=" * 70)
        print(" Si apre la finestra dell'app. Quando la chiudi, il programma si spegne da solo")
        print(" (se sta analizzando una foto, finisce prima l'analisi).")
        print(" Questa finestra nera, se la vedi, serve solo a capire eventuali problemi.")
        # La chiave viaggia solo nell'indirizzo con cui si apre la finestra (poi diventa un cookie e l'indirizzo si ripulisce).
        threading.Timer(0.6, lambda: apri_finestra(f"{url}?avvio={TOKEN_SESSIONE}")).start()
        threading.Thread(target=sorveglia_finestra, args=(server,), name="sorvegliante", daemon=True).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.fine_sorveglianza.set()
            cancella_token_file()                                 # la chiave non vale più
            ferma_analisi_in_corso()
            if server.chiusura_richiesta:
                chiudi_finestra_app()                             # "Esci" premuto: chiudo anche la finestra
            server.server_close()
            print("NeoTracker chiuso. A presto.")
    except Exception as e:                                        # errore imprevisto all'avvio: lo mostro chiaramente
        traceback.print_exc()
        mostra_errore("NeoTracker si è fermato", f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    avvia()
