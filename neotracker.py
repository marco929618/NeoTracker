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

VERSIONE = "1.3"
# Versione dell'avviso iniziale ("non è un dispositivo medico..."). Se la cambi, tutti gli utenti lo rivedono e lo riaccettano.
AVVERTENZE_VERSIONE = "1"

# Lingue dell'interfaccia. L'italiano è il testo originale (e quello che fa fede); le altre sono traduzioni
# (web/i18n_XX.js). Nelle Impostazioni si può scegliere anche "auto" = segui la lingua del sistema/browser.
LINGUE = ("it", "en", "fr", "de", "es")


def T(testo):
    """Segna un testo italiano destinato all'utente: il browser lo traduce con il dizionario della lingua scelta
    (web/i18n_XX.js), cercandolo per intero oppure, se contiene valori variabili, per "forma" (es. "{n} giorni").
    A runtime non fa nulla: serve a build.py per verificare che ogni testo segnato abbia la traduzione."""
    return testo
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
    "lingua": "auto",             # lingua dell'interfaccia: "auto" (come il sistema/browser) oppure it, en, fr, de, es
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


def lingua_corrente():
    """
    Lingua da usare fuori dal browser (per esempio nelle finestrelle di errore all'avvio): quella scelta
    nelle Impostazioni oppure, con "auto", quella del sistema. Se il sistema usa una lingua non
    supportata si ripiega sull'inglese.
    """
    scelta = leggi_impostazioni().get("lingua")
    if scelta in LINGUE:
        return scelta
    codice = ""
    try:
        import locale
        codice = (locale.getlocale()[0] or os.environ.get("LANG") or "")[:2].lower()
        if os.name == "nt":                       # lingua dell'interfaccia di Windows (più affidabile)
            import ctypes
            codice = {0x10: "it", 0x09: "en", 0x0C: "fr", 0x07: "de", 0x0A: "es"}.get(
                ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF, codice)
    except Exception:
        pass
    return codice if codice in LINGUE else "en"


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
        ("fototipo", T("Fototipo chiaro (I-II)"), a_intero(p.get("fototipo")) in (1, 2), False,
         T("Pelle che scotta facilmente e si abbronza poco.")),
        ("capelli", T("Capelli rossi o biondi"), p.get("capelli") in ("rossi", "biondi"), False,
         T("Associati a varianti del gene MC1R.")),
        ("occhi", T("Occhi chiari"), p.get("occhi") in ("azzurri", "verdi"), False, ""),
        ("efelidi", T("Molte efelidi (lentiggini)"), p.get("efelidi") == "molte", False, ""),
        ("nevi_100", T("100 o più nei sul corpo"), p.get("n_nevi") == "100+", True,
         T("Il numero di nei è uno dei fattori di rischio più forti.")),
        ("nevi_50", T("Da 50 a 99 nei sul corpo"), p.get("n_nevi") == "50-99", False, ""),
        ("atipici", T("Nei atipici (displastici)"), p.get("nevi_atipici") == "si", True,
         T("Nei grandi, irregolari, di più colori: vanno seguiti nel tempo.")),
        ("scottature", T("Molte scottature con vesciche"), p.get("scottature") == "molte", False,
         T("Soprattutto in infanzia e adolescenza.")),
        ("lampade", T("Uso di lampade o lettini abbronzanti"), p.get("lampade") in ("alcune", "spesso"), False,
         T("Classificati come cancerogeni certi per l'uomo (IARC).")),
        ("lavoro", T("Lavoro o attività prolungata all'aperto"), bool(p.get("lavoro_aperto")), False, ""),
        ("immuno", T("Immunosoppressione (terapie, trapianto)"), bool(p.get("immunosoppressione")), True, ""),
        ("mel_pers", T("Melanoma già diagnosticato"), a_intero(p.get("melanomi_personali")) >= 1, True,
         T("Chi ha avuto un melanoma ha un rischio maggiore di un secondo.")),
        ("altri_tum", T("Altri tumori della pelle (basalioma, spinalioma)"), bool(p.get("altri_tumori_cutanei")), False, ""),
        ("fam_1", T("Parente di primo grado con melanoma"), fam1 >= 1, True,
         T("Genitori, fratelli o figli.")),
    ]
    presenti = [{"id": i, "etichetta": e, "maggiore": m, "nota": n} for i, e, pr, m, n in voci if pr]
    maggiori = [f for f in presenti if f["maggiore"]]
    if not presenti:
        livello, testo = "nessuno", T("Con i dati inseriti non risultano fattori di rischio noti. Completa il profilo se mancano informazioni.")
    elif maggiori or len(presenti) >= 5:
        livello = "attenzione"
        testo = T("Sono presenti fattori di rischio rilevanti: è consigliato un controllo dermatologico periodico "
                  "(la frequenza la decide il dermatologo) e l'autoesame regolare della pelle.")
    else:
        livello = "alcuni"
        testo = T("Sono presenti alcuni fattori di rischio: protezione solare accurata e autoesame regolare; "
                  "un controllo dermatologico di base è una buona abitudine.")
    return {"livello": livello, "testo": testo, "presenti": presenti,
            "nota": T("Elenco di fattori noti dalla letteratura, non un punteggio validato: non stima la probabilità di ammalarsi.")}


# ------------------------------------------------------------------------------------------
# 4b. Melanoma ereditario: geni e criteri per valutare una consulenza genetica
# ------------------------------------------------------------------------------------------
# Elenco curato dei geni più citati. 'termine' è la ricerca PubMed usata per contare e
# mostrare gli studi (la scansione della letteratura la rifà ogni volta che la richiedi).
GENI_MELANOMA = [
    {"gene": "CDKN2A", "rischio": T("Alto"),
     "ruolo": T("Principale gene di predisposizione ad alta penetranza. Varianti germinali nel 20-40% delle famiglie con melanoma; associato anche a tumore del pancreas, melanomi multipli ed esordio precoce."),
     "termine": 'CDKN2A[tiab] AND melanoma[tiab] AND (germline[tiab] OR hereditary[tiab] OR familial[tiab] OR predisposition[tiab])'},
    {"gene": "CDK4", "rischio": T("Alto (raro)"),
     "ruolo": T("Varianti rare concentrate nel codone 24: il quadro familiare è indistinguibile da quello di CDKN2A."),
     "termine": 'CDK4[tiab] AND melanoma[tiab] AND (germline[tiab] OR hereditary[tiab] OR familial[tiab] OR predisposition[tiab])'},
    {"gene": "BAP1", "rischio": T("Alto (sindrome BAP1)"),
     "ruolo": T("Sindrome di predisposizione ai tumori BAP1: melanoma uveale, mesotelioma, carcinoma renale, melanoma cutaneo e nevi melanocitari atipici."),
     "termine": 'BAP1[tiab] AND melanoma[tiab] AND (germline[tiab] OR hereditary[tiab] OR predisposition[tiab] OR syndrome[tiab])'},
    {"gene": "MITF", "rischio": T("Moderato"),
     "ruolo": T("La variante p.E318K aumenta il rischio di melanoma e di carcinoma renale e si associa a molti nei."),
     "termine": 'MITF[tiab] AND melanoma[tiab] AND (E318K[tiab] OR germline[tiab] OR predisposition[tiab])'},
    {"gene": "POT1", "rischio": T("Raro"),
     "ruolo": T("Gene dei telomeri: varianti rare in alcune famiglie con melanoma."),
     "termine": 'POT1[tiab] AND melanoma[tiab] AND (germline[tiab] OR familial[tiab] OR predisposition[tiab])'},
    {"gene": "ACD", "rischio": T("Raro"),
     "ruolo": T("Gene dei telomeri (complesso shelterin): varianti rare in famiglie con melanoma."),
     "termine": 'ACD[tiab] AND melanoma[tiab] AND (germline[tiab] OR familial[tiab] OR telomere[tiab])'},
    {"gene": "TERF2IP", "rischio": T("Raro"),
     "ruolo": T("Gene dei telomeri (complesso shelterin): varianti rare in famiglie con melanoma."),
     "termine": 'TERF2IP[tiab] AND melanoma[tiab] AND (germline[tiab] OR familial[tiab] OR telomere[tiab])'},
    {"gene": "TERT", "rischio": T("Raro"),
     "ruolo": T("Telomerasi: varianti del promotore descritte in famiglie con melanoma."),
     "termine": 'TERT[tiab] AND melanoma[tiab] AND (germline[tiab] OR familial[tiab] OR predisposition[tiab])'},
    {"gene": "MC1R", "rischio": T("Basso-moderato (comune)"),
     "ruolo": T("Varianti comuni legate a capelli rossi e pelle chiara: aumentano il rischio di melanoma in modo moderato. Non è un test di routine: l'interpretazione è specialistica."),
     "termine": 'MC1R[tiab] AND melanoma[tiab] AND (variant[tiab] OR polymorphism[tiab] OR risk[tiab])'},
    {"gene": "PTEN", "rischio": T("Sindromico"),
     "ruolo": T("Citato dalle linee guida NCCN tra i geni da considerare nei pannelli per melanoma (sindrome di Cowden)."),
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
    {"titolo": T("NCCN Clinical Practice Guidelines in Oncology: Melanoma: Cutaneous (versione corrente; "
               "il testo completo richiede una registrazione gratuita)"),
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
         "titolo": T("3 o più melanomi primari nella stessa persona"),
         "spiegazione": T(f"Melanomi primari indicati: {mel_pers}."),
         "fonte": T("Leachman 2009 e 2017; NCCN")},
        {"id": "regola_tre", "soddisfatto": diagnosi >= 3,
         "titolo": T("Almeno 3 diagnosi tra melanoma, tumore del pancreas e astrocitoma nella stessa linea familiare (tua inclusa)"),
         "spiegazione": T(f"Diagnosi totali indicate: {diagnosi}. Leachman 2009 considera melanoma e tumore del pancreas nei "
                        "parenti di 1o e 2o grado dello stesso lato della famiglia; l'astrocitoma è incluso dalle linee guida NCCN."),
         "fonte": T("Leachman 2009 e 2017; NCCN")},
        {"id": "mel_pancreas", "soddisfatto": mel_pers >= 1 and pancreas_1 >= 1,
         "titolo": T("Melanoma personale e parente di primo grado con tumore del pancreas"),
         "spiegazione": T("Per le linee guida NCCN, in un melanoma invasivo con un parente di primo grado con tumore del pancreas "
                        "è raccomandato un pannello multigene che includa CDKN2A."),
         "fonte": T("NCCN")},
        {"id": "bap1", "soddisfatto": bap1_tipici >= 1 and bap1_spettro >= 2,
         "titolo": T("Più tumori dello spettro BAP1 (melanoma uveale, mesotelioma, carcinoma renale, melanoma cutaneo)"),
         "spiegazione": T(f"Tumori dello spettro BAP1 indicati: {bap1_spettro}. Criterio semplificato: il genetista usa "
                        "criteri più completi."),
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
        esito, msg = "dati_insufficienti", T("Compila la sezione 'Familiarità' nel Profilo: senza quei dati non posso verificare i criteri.")
    elif soddisfatti:
        esito = "criteri_soddisfatti"
        msg = T("I dati inseriti rientrano in almeno un criterio descritto in letteratura. Ti consigliamo di parlarne con il "
                "dermatologo o con un medico genetista (consulenza genetica oncologica): sarà lo specialista a decidere "
                "se e quale test proporre, di norma dopo la consulenza e, quando possibile, partendo da un familiare affetto. "
                "Geni più citati dalle linee guida: {geni}. L'uso dei pannelli multigene è ancora "
                "oggetto di discussione tra gli specialisti: per questo conta la consulenza prima del test.").format(geni=", ".join(geni))
    else:
        esito = "nessun_criterio"
        msg = T("Con i dati inseriti non rientri nei criteri più usati. Il test genetico per il melanoma è indicato solo in una "
                "piccola minoranza di persone e non viene proposto di routine. Se la tua storia familiare cambia o hai dubbi, "
                "aggiorna il profilo e parlane col dermatologo.")
    # frase aggiunta a parte (non incollata al messaggio): così ciascuna si traduce per intero
    aggiunta = ""
    if esito_gen in ("si_positivo", "si_negativo", "si_non_informativo"):
        aggiunta = T("Hai indicato di aver già eseguito un test genetico: porta il referto al dermatologo.")
    return {"esito": esito, "messaggio": msg, "messaggio_aggiunta": aggiunta, "criteri": criteri, "geni_suggeriti": geni, "fonti": FONTI_GENETICA}


# ------------------------------------------------------------------------------------------
# 4c. Indice UV (Open-Meteo di default; OpenWeather One Call 4.0/3.0 se lo scegli e hai la chiave)
# ------------------------------------------------------------------------------------------
CATEGORIE_UV = [
    # (da, a, nome, colore OMS, consiglio)
    (0, 2.99, T("Basso"), "#3f9c35", T("Nessuna protezione particolare per le attività normali; occhiali da sole nelle giornate luminose.")),
    (3, 5.99, T("Moderato"), "#e8c400", T("Protezione consigliata: ombra nelle ore centrali, cappello, occhiali e crema solare.")),
    (6, 7.99, T("Alto"), "#f28c00", T("Protezione necessaria: riduci l'esposizione tra le 10 e le 16, crema solare SPF 30+, cappello e occhiali.")),
    (8, 10.99, T("Molto alto"), "#d9261c", T("Precauzioni extra: evita il sole nelle ore centrali, cerca l'ombra, copri la pelle, SPF 30+. La pelle non protetta si scotta in fretta.")),
    (11, 999, T("Estremo"), "#8e44ad", T("Evita l'esposizione diretta: la pelle non protetta può scottarsi in pochi minuti.")),
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
    return {"nome": T("Basso"), "colore": CATEGORIE_UV[0][3], "consiglio": CATEGORIE_UV[0][4], "da": 0}


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
        return {"minuti": None, "testo": T("oltre 2 ore (UV molto basso)")}
    m = MED_SED_PRUDENTE[ft] * 60.0 / uvi
    return {"minuti": int(round(m)), "testo": T("circa {minuti} minuti").format(minuti=int(round(m)))}


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
        raise ErroreServizio(T("indirizzo non ammesso (solo https)"))
    with _APRITORE_WEB.open(req, timeout=timeout) as r:
        dati = r.read(massimo + 1)
    if len(dati) > massimo:
        raise ErroreServizio(T("risposta troppo grande"))
    return dati


def _http_json(url, timeout=20, headers=None):
    """Scarica un indirizzo web e lo legge come JSON. Trasforma gli errori di rete in messaggi chiari."""
    req = urllib.request.Request(url, headers=dict({"User-Agent": "NeoTracker/" + VERSIONE}, **(headers or {})))
    try:
        return json.loads(_leggi_web(req, timeout).decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        raise ErroreServizio(f"HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise ErroreServizio(T("connessione non riuscita: {motivo}").format(motivo=e.reason)) from e
    except (TimeoutError, OSError) as e:
        raise ErroreServizio(T("tempo scaduto o rete non disponibile")) from e
    except ValueError as e:
        raise ErroreServizio(T("risposta non valida dal servizio")) from e


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
    if mx is None:                            # ripiego: il massimo delle ore note di oggi
        oggi_ore = [o["uvi"] for o, d in zip(ore, date_ore) if d == adesso.date()]
        mx = max(oggi_ore + [uvi_ora])
    return {"fonte": "OpenWeather One Call 4.0", "uvi_ora": uvi_ora, "uvi_max": max(mx, uvi_ora), "ore": ore,
            "aggiornato": adesso.strftime("%d/%m/%Y %H:%M") + " (ora locale del luogo)",
            "aggiornato_iso": adesso.strftime("%Y-%m-%dT%H:%M"), "fuso": cur_r.get("timezone", "")}


def _uv_owm_v3(lat, lon, chiave):
    """One Call 3.0 (vecchio abbonamento): una sola chiamata."""
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
            "aggiornato": _owm_ora_locale(cur.get("dt", time.time()), off).strftime("%d/%m/%Y %H:%M") + " (ora locale del luogo)",
            "aggiornato_iso": _owm_ora_locale(cur.get("dt", time.time()), off).strftime("%Y-%m-%dT%H:%M"),
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
        raise ErroreServizio(T("OpenWeather: limite di chiamate raggiunto (429)."))
    if "401" in testo or "403" in testo:
        raise ErroreServizio(T("OpenWeather ha rifiutato la chiave (401): controlla che sia corretta e che sul tuo account sia "
                             "attivo l'abbonamento 'One Call API' (pagamento a chiamata, 1.000 chiamate al giorno gratuite). "
                             "Dopo l'iscrizione la chiave può impiegare qualche minuto ad attivarsi."))
    raise ErroreServizio("; ".join(T("One Call {n}: {t}").format(n=n, t=t) for n, t in errori))


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
        ore.append({"ora": t[11:16], "giorno": t[8:10] + "/" + t[5:7], "data": t[:10], "uvi": round(float(v or 0), 1)})
    mx = ((d.get("daily") or {}).get("uv_index_max") or [cur.get("uv_index", 0)])[0]
    return {"fonte": "Open-Meteo", "uvi_ora": round(float(cur.get("uv_index") or 0), 1),
            "uvi_max": round(float(mx or 0), 1), "ore": ore,
            "aggiornato": _data_ora_italiana(cur.get("time") or "") + " (ora locale del luogo)",
            "aggiornato_iso": (cur.get("time") or "")[:16],
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
                avviso = T(f"OpenWeather non disponibile ({e}). Mostro i dati di Open-Meteo.")
        elif imp.get("fonte_uv") == "openweather":
            avviso = T("Hai scelto OpenWeather ma manca la chiave (Impostazioni): mostro i dati di Open-Meteo.")
        if dati is None:
            try:
                dati = _uv_openmeteo(lat, lon)
            except ErroreServizio as e:
                if avviso:
                    raise ErroreServizio(T("{avviso} Il servizio Open-Meteo non risponde ({e}).").format(avviso=avviso, e=e))
                raise ErroreServizio(T("Il servizio Open-Meteo non risponde ({e}).").format(e=e))
        dati["avviso"] = avviso
        _cache_uv[chiave_cache] = (time.time(), dict(dati))
    cat_ora, cat_max = categoria_uv(dati["uvi_ora"]), categoria_uv(dati["uvi_max"])
    dati.update({"lat": lat, "lon": lon, "localita": localita,
                 "categoria_ora": cat_ora, "categoria_max": cat_max,
                 "scottatura_max": minuti_scottatura(dati["uvi_max"], fototipo),
                 "scottatura_ora": minuti_scottatura(dati["uvi_ora"], fototipo)})
    mx = dati["uvi_max"]
    if mx >= 8:
        verdetto = {"livello": "rosso", "titolo": T("Oggi i raggi UV sono molto dannosi"),
                    "testo": T("Evita il sole nelle ore centrali e proteggi bene la pelle.")}
    elif mx >= 6:
        verdetto = {"livello": "arancio", "titolo": T("Oggi i raggi UV sono dannosi per pelle non protetta"),
                    "testo": T("Servono ombra, abiti, cappello e crema solare nelle ore centrali.")}
    elif mx >= 3:
        verdetto = {"livello": "giallo", "titolo": T("UV moderati: serve protezione nelle ore centrali"),
                    "testo": T("L'OMS consiglia di proteggersi a partire da un indice UV di 3.")}
    else:
        verdetto = {"livello": "verde", "titolo": T("Oggi i raggi UV sono bassi"),
                    "testo": T("Protezione non necessaria per le attività normali (attenzione a neve, acqua, quota).")}
    dati["verdetto"] = verdetto
    dati["fonti"] = [
        {"titolo": T("OMS/OMM/UNEP/ICNIRP - Global Solar UV Index: A Practical Guide (2002)"),
         "url": "https://www.who.int/publications/i/item/9241590076"},
        {"titolo": T("Lucas RM et al. Are current guidelines for sun protection optimal for health? "
                   "Photochem Photobiol Sci 2018;17:1956-63 (UV Index e dose di eritema)"),
         "url": "https://doi.org/10.1039/c7pp00374a"},
        {"titolo": T("Fajuyigbe D, Young AR. The impact of skin colour on human photobiological responses. "
                   "Pigment Cell Melanoma Res 2016;29:607-18 (dose minima di eritema per fototipo)"),
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
        raise ErroreServizio(T("posizione da indirizzo internet non disponibile"))
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
        raise ErroreServizio(T(f"PubMed ha risposto con errore {e.code}")) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErroreServizio(T("PubMed non raggiungibile (controlla la connessione internet)")) from e


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
        "titolo": T("Riconoscere un neo sospetto"),
        "sezioni": [
            (T("Criteri ABCDE e segno del 'brutto anatroccolo'"),
             '(melanoma[tiab]) AND (ABCDE[tiab] OR "ugly duckling"[tiab]) AND (diagnosis[tiab] OR detection[tiab] OR recognition[tiab])', "relevance"),
            (T("Dermoscopia e diagnosi precoce (revisioni)"),
             'melanoma[tiab] AND dermoscopy[tiab] AND ("early diagnosis"[tiab] OR "early detection"[tiab]) AND review[pt]', "relevance"),
            (T("Autoesame della pelle"),
             'melanoma[tiab] AND ("skin self-examination"[tiab] OR "skin self examination"[tiab])', "relevance"),
            (T("Fotografia sequenziale e monitoraggio dei nei nel tempo"),
             'melanoma[tiab] AND ("total body photography"[tiab] OR "sequential digital dermoscopy"[tiab] OR "digital dermoscopic monitoring"[tiab])', "relevance"),
        ]},
    "strumenti_ai": {
        "titolo": T("Quanto sono affidabili app e intelligenza artificiale"),
        "sezioni": [
            (T("App per smartphone e rischio di cancro della pelle: accuratezza diagnostica"),
             'smartphone[tiab] AND (app[tiab] OR application[tiab]) AND melanoma[tiab] AND (accuracy[tiab] OR diagnostic[tiab])', "relevance"),
            (T("Deep learning e melanoma: revisioni sistematiche"),
             '"deep learning"[tiab] AND melanoma[tiab] AND ("systematic review"[pt] OR meta-analysis[pt])', "relevance"),
        ]},
    "genetica": {
        "titolo": T("Melanoma ereditario e test genetico"),
        "sezioni": [
            (T("Linee guida e criteri per il test genetico"),
             'melanoma[tiab] AND (hereditary[tiab] OR familial[tiab]) AND ("genetic testing"[tiab] OR "genetic counseling"[tiab]) AND (guideline[tiab] OR criteria[tiab] OR recommendations[tiab])', "relevance"),
            (T("Revisioni sul melanoma familiare (CDKN2A, CDK4)"),
             'melanoma[tiab] AND familial[tiab] AND (CDKN2A[tiab] OR CDK4[tiab]) AND review[pt]', "relevance"),
            (T("Studi più recenti sui geni di predisposizione"),
             'melanoma[tiab] AND germline[tiab] AND (susceptibility[tiab] OR predisposition[tiab])', "date"),
        ]},
}

# Parole che indicano una sede "acrale" (mani, piedi, unghie) o del capo. Ci sono anche le parole delle altre lingue
# dell'interfaccia, perché la sede si può scrivere o scegliere in qualsiasi lingua (le sedi della mappa restano in italiano).
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
    """Sezioni di letteratura scelte in base al profilo e alle sedi dei tuoi nei."""
    sez = []
    if a_intero(profilo.get("fototipo")) >= 5:
        sez.append((T("Melanoma nelle pelli scure (spesso acrale)"),
                    'melanoma[tiab] AND ("skin of color"[tiab] OR "dark skin"[tiab] OR acral[tiab]) AND (diagnosis[tiab] OR detection[tiab])', "relevance"))
    reg = " ".join(regioni).lower()
    if any(k in reg for k in REGIONI_ACRALI):
        sez.append((T("Melanoma acrale (mani, piedi, unghie): dermoscopia"),
                    'acral[tiab] AND melanoma[tiab] AND dermoscop*[tiab]', "relevance"))
    if any(k in reg for k in REGIONI_TESTA):
        sez.append((T("Lentigo maligna e melanoma del volto"),
                    '"lentigo maligna"[tiab] AND (diagnosis[tiab] OR dermoscopy[tiab])', "relevance"))
    if profilo.get("n_nevi") in ("50-99", "100+") or profilo.get("nevi_atipici") == "si":
        sez.append((T("Molti nei o nei atipici: sorveglianza"),
                    '("dysplastic nevus"[tiab] OR "atypical nevi"[tiab] OR "high nevus count"[tiab] OR "many nevi"[tiab]) AND melanoma[tiab] AND (surveillance[tiab] OR monitoring[tiab])', "relevance"))
    if profilo.get("immunosoppressione"):
        sez.append((T("Melanoma e immunosoppressione"),
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
        raise ErroreRichiesta(T("Data non valida: usa il formato AAAA-MM-GG."))
    if d > date.today() + timedelta(days=1):
        raise ErroreRichiesta(T("La data della foto non può essere nel futuro."))
    if d.year < 1990:
        raise ErroreRichiesta(T("Data della foto troppo vecchia."))
    return d.isoformat()


def numero_o_vuoto(testo, minimo, massimo, nome):
    """Legge un numero decimale opzionale (virgola o punto) entro un intervallo; '' vale 'non indicato'."""
    if testo is None or str(testo).strip() == "":
        return None
    try:
        v = float(str(testo).replace(",", "."))
    except ValueError:
        raise ErroreRichiesta(T(f"{nome}: inserisci un numero."))
    if not (minimo <= v <= massimo):
        raise ErroreRichiesta(T(f"{nome}: il valore deve essere tra {minimo:g} e {massimo:g}."))
    return round(v, 1)


def salva_foto(nevo_id, dati, data, usa_exif, tipo, diametro, note):
    """
    Salva una foto nello storico del neo. L'originale viene conservato SENZA modifiche
    (è la 'foto storica'). Restituisce l'id della foto e la data effettivamente usata.
    """
    if not dati:
        raise ErroreRichiesta(T("Il file è vuoto."))
    if len(dati) > MAX_MB_FOTO * 1024 * 1024:
        raise ErroreRichiesta(T(f"La foto supera {MAX_MB_FOTO} MB."), 413)
    ext = riconosci_formato(dati)
    if ext is None:
        raise ErroreRichiesta(T("Formato non supportato: servono JPG, PNG, WEBP o BMP. "
                              "Le foto HEIC degli iPhone vanno convertite in JPG "
                              "(impostazioni fotocamera: 'Più compatibile')."))
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
            raise ErroreRichiesta(T("Il file non è un'immagine leggibile, è danneggiato o ha troppi pixel "
                                  "(massimo {mp} megapixel).").format(mp=MAX_PIXEL_IMMAGINE // 1_000_000))
    data_finale = data_exif_trovata if (usa_exif and data_exif_trovata) else data_valida(data or date.today().isoformat())
    diam = numero_o_vuoto(diametro, 0.5, 100, T("Diametro (mm)"))
    note = (note or "").strip()[:1000]

    with connetti() as con:
        nevo = con.execute("SELECT id, utente_id FROM nevi WHERE id=?", (nevo_id,)).fetchone()
        if nevo is None:
            raise ErroreRichiesta(T("Neo non trovato."), 404)
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
        raise ErroreRichiesta(T("File della foto non trovato."), 404)
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
        raise ErroreRichiesta(T("Il file è vuoto."))
    if len(dati) > MAX_BYTE_AVATAR:
        raise ErroreRichiesta(T("L'immagine supera {mb} MB.").format(mb=MAX_BYTE_AVATAR // (1024 * 1024)), 413)
    ext = riconosci_formato(dati)
    if ext not in (".jpg", ".png", ".webp", ".bmp"):
        raise ErroreRichiesta(T("Formato non supportato: servono JPG, PNG, WEBP o BMP."))
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
            raise ErroreRichiesta(T("Il file non è un'immagine leggibile o è troppo grande."))
    else:
        if ext not in (".jpg", ".png") or len(dati) > 400 * 1024:
            raise ErroreRichiesta(T("Senza Pillow l'immagine deve essere un JPG/PNG sotto i 400 KB "
                                  "(la pagina la riduce da sola: riprova con la funzione 'Scegli immagine')."))
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
                {"nome": T("Metodo 1 - App 1 (Deborah Adedigba)"), "presente": app1.exists(),
                 "dettaglio": T("{n} file modello su 10").format(n=n_app1)},
                {"nome": T("Metodo 2 - SkinSense (servizio online)"), "presente": True,
                 "dettaglio": T("attivo solo se lo abiliti qui sotto")},
                {"nome": T("Metodo 4 - vatsal30"), "presente": vatsal.exists(),
                 "dettaglio": T("{n} file modello su 5").format(n=n_vat)},
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
            raise ErroreRichiesta(T("Foto non trovata."), 404)
        if r["stato_analisi"] in ("in_coda", "in_corso"):
            return r["stato_analisi"]
        if trova_batch() is None:
            raise ErroreRichiesta(T("Non trovo melanoma_batch.py: deve stare nella stessa cartella di neotracker.py "
                                  f"(oppure in {CARTELLA_REPO})."), 409)
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
                _scrivi_stato(foto_id, stato_analisi="errore", messaggio=T(f"Errore imprevisto: {e}"))
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
        _scrivi_stato(foto_id, stato_analisi="errore", messaggio=T("File della foto non trovato."))
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
                          messaggio=T("Analisi interrotta dopo {ore} ore (troppo lunga).").format(ore=TIMEOUT_ANALISI_S // 3600))
            return
        finally:
            _processo_attuale.update(foto=None, popen=None)

    sint = sintesi_rapporto(rel)
    if sint is None:
        coda_log = ultime_righe(cartella / "log_analisi.txt", 6)
        _scrivi_stato(foto_id, stato_analisi="errore",
                      messaggio=T("L'analisi non ha prodotto il rapporto. Ultime righe del log: {log}").format(log=coda_log or T("(vuoto)")))
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
        frase = "; ".join(T("{n} su {tot}: {et}").format(n=n, tot=len(ok), et=et) for et, n in sorted(conteggi.items(), key=lambda kv: -kv[1]))
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
        raise ErroreRichiesta(T("Profilo non valido."))
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
                    raise ErroreRichiesta(T("Data di nascita non valida (AAAA-MM-GG)."))
                if not (date(1900, 1, 1) <= d <= date.today()):
                    raise ErroreRichiesta(T("Data di nascita fuori intervallo."))
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


def nome_valido(testo, minimo=1, massimo=60, cosa=T("Il nome")):
    t = re.sub(r"\s+", " ", (testo or "")).strip()
    if len(t) < minimo:
        raise ErroreRichiesta(T(f"{cosa} non può essere vuoto."))
    if len(t) > massimo:
        raise ErroreRichiesta(T(f"{cosa} è troppo lungo (massimo {massimo} caratteri)."))
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
                raise ErroreRichiesta(T("Richiesta troppo grande."), 413)
            self._corpo = self.gestore.rfile.read(lung) if lung > 0 else b""
        return self._corpo

    def json(self):
        try:
            d = json.loads(self.corpo().decode("utf-8") or "{}")
        except ValueError:
            raise ErroreRichiesta(T("Dati non validi (JSON)."))
        if not isinstance(d, dict):
            raise ErroreRichiesta(T("Dati non validi."))
        return d


class RispostaFile:
    def __init__(self, dati, mime, extra=None):
        self.dati, self.mime, self.extra = dati, mime, extra or {}


def get_utente(con, uid):
    r = con.execute("SELECT * FROM utenti WHERE id=?", (uid,)).fetchone()
    if r is None:
        raise ErroreRichiesta(T("Utente non trovato."), 404)
    return r


def get_nevo(con, nid):
    r = con.execute("SELECT * FROM nevi WHERE id=?", (nid,)).fetchone()
    if r is None:
        raise ErroreRichiesta(T("Neo non trovato."), 404)
    return r


def get_foto(con, fid):
    r = con.execute("SELECT f.*, n.utente_id FROM foto f JOIN nevi n ON n.id=f.nevo_id WHERE f.id=?", (fid,)).fetchone()
    if r is None:
        raise ErroreRichiesta(T("Foto non trovata."), 404)
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
        raise ErroreRichiesta(T("Identificativo di pagina non valido."))
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
            raise ErroreRichiesta(T("Esiste già un utente con questo nome."), 409)
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
            raise ErroreRichiesta(T("Esiste già un utente con questo nome."), 409)
        con.execute("UPDATE utenti SET nome=? WHERE id=?", (nome, u["id"]))
    return {"ok": True, "nome": nome}


def api_utente_elimina(rq):
    uid = int(rq.gruppi[0])
    with connetti() as con:
        u = get_utente(con, uid)
        if rq.json().get("conferma") != u["nome"]:
            raise ErroreRichiesta(T("Per eliminare scrivi il nome esatto dell'utente nella conferma."))
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
        raise ErroreRichiesta(T("Nessuna immagine impostata."), 404)
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
            raise ErroreRichiesta(T("La vista deve essere 'fronte' o 'retro'."))
        out["vista"] = d["vista"]
    for c in ("x", "y"):
        if c in d or not parziale:
            try:
                v = float(d.get(c))
            except (TypeError, ValueError):
                raise ErroreRichiesta(T("Posizione non valida."))
            if not (0.0 <= v <= 1.0):
                raise ErroreRichiesta(T("Posizione fuori dalla mappa."))
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
        campi["diametro_mm"] = numero_o_vuoto(d["diametro_mm"], 0.5, 100, T("Diametro (mm)"))
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
            raise ErroreRichiesta(T("L'analisi di questa foto è in corso: attendi che finisca."), 409)
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
            raise ErroreRichiesta(T("File della foto non trovato."), 404)
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
        raise ErroreRichiesta(T("Posizione non impostata: scegli una città o usa 'Rileva la mia posizione'."))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ErroreRichiesta(T("Coordinate non valide."))
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
            raise ErroreRichiesta(T("La chiave OpenWeather contiene caratteri non validi (di solito sono 32 lettere/numeri)."))
        nuove["openweather_key"] = k
    if "fonte_uv" in d:
        if d["fonte_uv"] not in ("open-meteo", "openweather"):
            raise ErroreRichiesta(T("Fonte dell'indice UV non valida."))
        nuove["fonte_uv"] = d["fonte_uv"]
    if "usa_skinsense" in d:
        nuove["usa_skinsense"] = bool(d["usa_skinsense"])
    if "avvertenze_accettate" in d:
        if d["avvertenze_accettate"] not in ("", AVVERTENZE_VERSIONE):
            raise ErroreRichiesta(T("Versione dell'avviso non valida."))
        nuove["avvertenze_accettate"] = d["avvertenze_accettate"]
    for c in ("lat", "lon"):
        if c in d:
            try:
                nuove[c] = None if d[c] in (None, "") else round(float(d[c]), 2)       # ~1 km: all'indice UV basta e si invia meno
            except (TypeError, ValueError):
                raise ErroreRichiesta(T("Coordinate non valide."))
    if "localita" in d:
        nuove["localita"] = str(d["localita"] or "").strip()[:120]
    if "lingua" in d:
        if d["lingua"] != "auto" and d["lingua"] not in LINGUE:
            raise ErroreRichiesta(T("Lingua non supportata."))
        nuove["lingua"] = d["lingua"]
    if "ncbi_email" in d:
        e = str(d["ncbi_email"] or "").strip()[:120]
        if e and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e):
            raise ErroreRichiesta(T("Email non valida."))
        nuove["ncbi_email"] = e
    salva_impostazioni(nuove)
    _cache_uv.clear()
    return impostazioni_pubbliche()


def api_prova_owm(rq):
    imp = leggi_impostazioni()
    chiave = (imp.get("openweather_key") or "").strip()
    if not chiave:
        raise ErroreRichiesta(T("Prima salva una chiave OpenWeather."))
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
    titoli["personale"] = T("Scelti per te (in base a profilo e sede dei nei)")
    for t in ordine:
        elenco = [{"id": k, "titolo": v["titolo"]} for k, v in sezioni.items() if v["tema"] == t]
        if elenco:
            temi.append({"tema": t, "titolo": titoli[t], "sezioni": elenco})
    return temi


def api_lett_sezione(rq):
    sezioni = _sezioni_per_utente(a_intero(rq.q("utente"), 0))
    s = sezioni.get(rq.q("id"))
    if s is None:
        raise ErroreRichiesta(T("Sezione sconosciuta."), 404)
    dati = pubmed_cerca(s["termine"], 5, s["ordina"], rq.q("forza") == "1")
    return dict(dati, titolo=s["titolo"], id=rq.q("id"))


def api_lett_cerca(rq):
    q = re.sub(r"[^\w\s\-\*\"'\.]", " ", rq.q("q"), flags=re.UNICODE).strip()[:200]
    if len(q) < 3:
        raise ErroreRichiesta(T("Scrivi almeno 3 caratteri."))
    dati = pubmed_cerca(f"({q}) AND melanoma[tiab]", 8, "relevance", rq.q("forza") == "1")
    return dict(dati, titolo=f"Risultati per: {q}")


def api_genetica_geni(rq):
    return {"geni": [{k: g[k] for k in ("gene", "rischio", "ruolo")} for g in GENI_MELANOMA], "fonti": FONTI_GENETICA}


def api_genetica_gene(rq):
    g = next((x for x in GENI_MELANOMA if x["gene"] == rq.q("nome")), None)
    if g is None:
        raise ErroreRichiesta(T("Gene non presente nell'elenco."), 404)
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


_ACCESSO_NEGATO_TESTI = (
    ("it", "Accesso non autorizzato", "Questa pagina funziona solo dalla finestra di NeoTracker. Chiudi questa scheda e apri l'app "
                                      "dall'icona <b>NeoTracker</b> sul Desktop."),
    ("en", "Access denied", "This page only works from the NeoTracker window. Close this tab and open the app "
                            "from the <b>NeoTracker</b> icon on your Desktop."),
    ("fr", "Accès non autorisé", "Cette page ne fonctionne que depuis la fenêtre de NeoTracker. Fermez cet onglet et ouvrez "
                                 "l'application avec l'icône <b>NeoTracker</b> du Bureau."),
    ("de", "Zugriff nicht erlaubt", "Diese Seite funktioniert nur im NeoTracker-Fenster. Schließen Sie diesen Tab und starten Sie "
                                    "die App über das <b>NeoTracker</b>-Symbol auf dem Desktop."),
    ("es", "Acceso no autorizado", "Esta página solo funciona desde la ventana de NeoTracker. Cierra esta pestaña y abre la "
                                   "aplicación desde el icono <b>NeoTracker</b> del Escritorio."),
)
PAGINA_ACCESSO_NEGATO = (
    "<!doctype html><html lang='it'><meta charset='utf-8'><title>" + " · ".join(t for _, t, _ in _ACCESSO_NEGATO_TESTI) + "</title>"
    "<body style='font-family:Segoe UI,Arial,sans-serif;max-width:34em;margin:4em auto;padding:0 1em;color:#222'>"
    + "".join(f"<section lang='{lg}'><h1>{tit}</h1><p>{txt}</p></section>" for lg, tit, txt in _ACCESSO_NEGATO_TESTI)
    + "</body></html>").encode("utf-8")

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
            return self._errore(400, T("Identificativo di pagina non valido."))
        with _blocco_presenze:                                      # un tetto ai collegamenti aperti: niente "inondazioni"
            if _presenze_aperte[0] >= MAX_PRESENZE:
                return self._errore(429, T("Troppi collegamenti aperti."))
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
                return self._errore(403, T("Indirizzo non ammesso."))
            if not self._origine_ok():
                return self._errore(403, T("Origine non ammessa."))
            if len(self.path) > 2000:
                return self._errore(414, T("Indirizzo troppo lungo."))
            url = urllib.parse.urlsplit(self.path)
            percorso, query = url.path, urllib.parse.parse_qs(url.query, keep_blank_values=True)
            if self.command in ("POST", "PUT", "PATCH", "DELETE") and self.headers.get("X-NeoTracker") != "1":
                return self._errore(403, T("Richiesta non autorizzata."))

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
                    return self._errore(403, T("Accesso non autorizzato."))

            if self.command == "GET" and percorso == "/api/presenza":
                return self._presenza(query)

            if self.command == "GET" and not percorso.startswith(("/api/", "/foto/")):
                voce = WEB_FILES.get("/index.html" if percorso == "/" else percorso)
                if voce is None:
                    return self._errore(404, T("Pagina non trovata."))
                mime, dati = voce
                if mime.startswith("text/html"):
                    scelta = leggi_impostazioni().get("lingua")
                    dati = dati.replace(b"@@LINGUA@@", (scelta if scelta in LINGUE else "auto").encode("ascii"))
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
                return self._errore(405, T("Operazione non consentita su questo indirizzo."))
            return self._errore(404, T("Indirizzo sconosciuto."))
        except ErroreRichiesta as e:
            self._errore(e.codice, str(e))
        except ErroreServizio as e:
            self._errore(502, str(e))
        except (BrokenPipeError, ConnectionResetError):
            pass                                       # il browser ha chiuso la connessione: nessun problema
        except Exception as e:                         # errore nostro: lo mostro in console e lo segnalo al browser
            traceback.print_exc()                      # i dettagli restano nel registro (neotracker.log), non nella risposta
            try:
                self._errore(500, T("Errore interno. I dettagli sono nel file neotracker.log nella cartella dei dati."))
            except Exception:
                pass

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _gestisci

    def do_HEAD(self):
        self._errore(405, T("Non consentito."))

    def do_OPTIONS(self):
        self._errore(403, T("Non consentito."))


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
    ['mappa', NT.t('Mappa dei nei'), 'mappa'], ['profilo', NT.t('Profilo'), 'profilo'], ['letteratura', NT.t('Letteratura'), 'letteratura'],
    ['genetica', NT.t('Genetica'), 'genetica'], ['uv', NT.t('Indice UV'), 'uv'], ['impostazioni', NT.t('Impostazioni'), 'impostazioni'],
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
    menu.setAttribute('aria-label', NT.t('Sezioni'));
    $('#piede').textContent = NT.t('NeoTracker non è uno strumento medico e non fa diagnosi. Per qualsiasi neo che cambia, sanguina, prude o ti preoccupa, rivolgiti a un dermatologo.');
    menu.replaceChildren(...VOCI.map(([id, testo, ico]) =>
      h('a', { href: '#/' + id, class: 'voce' + (id === attiva ? ' attiva' : ''), 'aria-current': id === attiva ? 'page' : null }, NT.icona(ico, 18), h('span', {}, testo))));
    const box = $('#utente-box');
    box.replaceChildren(S.utente
      ? h('a', { href: '#/utenti', class: 'utente-chip', title: NT.t('Cambia utente') }, NT.avatar(S.utente.nome, 28, S.utente),
        h('span', { class: 'utente-nome' }, S.utente.nome), h('span', { class: 'utente-cambia' }, NT.t('Cambia')))
      : h('a', { href: '#/utenti', class: 'utente-chip' }, h('span', { class: 'utente-nome' }, NT.t('Scegli utente'))));
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
      cont.replaceChildren(h('div', { class: 'scheda errore-pagina' }, h('h2', {}, NT.t('Qualcosa non ha funzionato')), h('p', {}, e.message || String(e)),
        h('button', { class: 'btn', onclick: () => route() }, NT.t('Riprova'))));
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
      $('#vista').replaceChildren(h('div', { class: 'scheda errore-pagina' }, h('h2', {}, NT.t('NeoTracker non risponde')), h('p', {}, e.message)));
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
    if (fr) singola('Collo', rect(168, 128, 232, 170));
    else singola('Nuca e collo', rect(168, 116, 232, 170));
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
    if (fr) {
      coppia('Ginocchio', 'm', trattoPoly(GAMBA, 3, 5, e));
      coppia('Gamba (stinco)', 'f', trattoPoly(GAMBA, 5, 8, e));
    } else {
      coppia('Cavo popliteo', 'm', trattoPoly(GAMBA, 3, 5, e));
      coppia('Polpaccio', 'm', trattoPoly(GAMBA, 5, 8, e));
    }
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
      'aria-label="' + esc(window.NT.t('Mappa del corpo umano: fronte a sinistra, retro a destra')) + '">';
    s += figura('fronte', ft, 0) + figura('retro', ft, LARG);
    // etichette fisse
    const D = esc(window.NT.t('D')), Sx = esc(window.NT.t('S'));          // destra / sinistra del paziente
    s += '<g class="etichette">' +
      '<text x="200" y="14" text-anchor="middle">' + esc(window.NT.t('FRONTE')) + '</text><text x="600" y="14" text-anchor="middle">' + esc(window.NT.t('RETRO')) + '</text>' +
      '<text x="22" y="64" class="lato">' + D + '</text><text x="378" y="64" text-anchor="end" class="lato">' + Sx + '</text>' +
      '<text x="422" y="64" class="lato">' + Sx + '</text><text x="778" y="64" text-anchor="end" class="lato">' + D + '</text></g>';
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

_WEB_I18N_JS = r'''/* ============================================================================
   i18n.js - lingue dell'interfaccia (italiano, inglese, francese, tedesco, spagnolo)

   Come funziona, in breve:
   - Il TESTO ITALIANO è l'originale e fa da chiave: nel codice si scrive NT.t('Salva neo').
   - I dizionari delle altre lingue (i18n_en.js, i18n_fr.js, ...) associano a ogni testo italiano la
     sua traduzione. Se la lingua è l'italiano non serve nessun dizionario.
   - I testi con valori variabili usano segnaposto con nome: NT.t('{n} giorni fa', { n: 3 }).
   - I testi che arrivano dal programma Python (messaggi di errore, criteri di genetica, indice UV...)
     sono ancora in italiano: NT.tr() li traduce cercandoli nel dizionario (anche per "forma",
     cioè con i valori variabili al posto dei segnaposto).
   - La lingua si sceglie nelle Impostazioni ("auto" = come il browser). Il server la scrive nella pagina
     (<meta name="nt-lingua">) così è nota prima di disegnare qualsiasi cosa.
   Per aggiungere una lingua vedi CONTRIBUTING.md.
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT = window.NT || {};

  NT.LINGUE = [['it', 'Italiano'], ['en', 'English'], ['fr', 'Français'], ['de', 'Deutsch'], ['es', 'Español']];
  const CODICI = NT.LINGUE.map(l => l[0]);

  /* ---------- quale lingua usare ---------- */
  NT.linguaDelBrowser = function () {
    const elenco = (navigator.languages && navigator.languages.length) ? navigator.languages : [navigator.language || ''];
    for (const l of elenco) {
      const c = String(l).slice(0, 2).toLowerCase();
      if (CODICI.includes(c)) return c;
    }
    return 'en';                                  // lingua non supportata: l'inglese è la più diffusa
  };
  const meta = document.querySelector('meta[name="nt-lingua"]');
  NT.linguaScelta = meta && CODICI.includes(meta.content) ? meta.content : 'auto';    // 'auto' oppure un codice
  NT.lingua = NT.linguaScelta === 'auto' ? NT.linguaDelBrowser() : NT.linguaScelta;
  document.documentElement.lang = NT.lingua;

  const DIZ = (window.NT_DIZIONARI || {})[NT.lingua] || {};   // vuoto per l'italiano

  /* ---------- traduzione dei testi del programma ---------- */
  const sostituisci = (s, params) => params ? s.replace(/\{(\w+)\}/g, (m, k) => (k in params ? String(params[k]) : m)) : s;

  NT.mancanti = new Set();       // testi senza traduzione trovati durante l'uso (li controllano i test)
  NT.t = function (testo, params) {
    let s = testo;
    if (NT.lingua !== 'it') {
      const tr = DIZ[testo];
      if (tr === undefined) {
        if (!NT.mancanti.has(testo)) { NT.mancanti.add(testo); console.warn('[i18n] manca la traduzione (' + NT.lingua + '): ' + testo); }
      } else s = tr;
    }
    return sostituisci(s, params);
  };

  /* Segna un testo italiano che verrà tradotto più tardi (con NT.tr): non fa nulla, serve a build.py per
     controllare che il testo abbia la traduzione in tutti i dizionari. */
  NT.m = testo => testo;

  /* Singolare/plurale: 'uno' e 'altri' sono i due testi italiani (con {n}). Il francese usa il singolare anche per 0.
     Se in italiano le due forme sono uguali (es. "{n} foto") la traduzione del plurale ha la chiave "{n} foto#pl". */
  NT.tp = function (n, uno, altri, params) {
    const sing = NT.lingua === 'fr' ? Math.abs(n) < 2 : n === 1;
    const p = Object.assign({ n: n }, params);
    if (NT.lingua === 'it') return sostituisci(sing ? uno : altri, p);
    return NT.t(sing ? uno : (altri === uno ? uno + '#pl' : altri), p);
  };

  /* Traduce un testo che viene dal programma Python (già composto, in italiano). Non protesta se non lo trova:
     può essere un nome scritto dall'utente o il testo di un errore tecnico. */
  let schemi = null;
  function costruisciSchemi() {
    schemi = [];
    for (const chiave in DIZ) {
      if (!/\{\w+\}/.test(chiave)) continue;
      const pezzi = chiave.split(/\{(\w+)\}/);          // [testo, nome, testo, nome, ..., testo]
      const nomi = [];
      let re = '^';
      pezzi.forEach((p, i) => {
        if (i % 2) { nomi.push(p); re += '([\\s\\S]+?)'; }
        else re += p.replace(/[.*+?^$()|[\]\\{}]/g, '\\$&');
      });
      schemi.push({ chiave: chiave, nomi: nomi, re: new RegExp(re + '$'), fisso: pezzi.filter((p, i) => i % 2 === 0).join('').length });
    }
    schemi.sort((a, b) => b.fisso - a.fisso);              // prima le forme più specifiche
  }
  NT.tr = function tr(testo) {
    if (testo === null || testo === undefined || testo === '' || NT.lingua === 'it') return testo;
    testo = String(testo);
    if (Object.prototype.hasOwnProperty.call(DIZ, testo)) return DIZ[testo];
    if (!schemi) costruisciSchemi();
    for (const s of schemi) {
      const m = s.re.exec(testo);
      if (!m) continue;
      const params = {};
      s.nomi.forEach((nome, i) => { params[nome] = tr(m[i + 1]); });
      return sostituisci(DIZ[s.chiave], params);
    }
    if (testo.indexOf('; ') > 0) {                           // più messaggi uniti da "; "
      const parti = testo.split('; '), tradotte = parti.map(tr);
      if (tradotte.some((x, i) => x !== parti[i])) return tradotte.join('; ');
    }
    return testo;
  };

  /* ---------- numeri e date nel formato della lingua ---------- */
  const SEP = NT.lingua === 'en' ? '.' : ',';
  const MESI_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const LOCALI = { it: 'it-IT', en: 'en-GB', fr: 'fr-FR', de: 'de-DE', es: 'es-ES' };
  NT.locale = LOCALI[NT.lingua];
  NT.num = (n, dec) => (n === null || n === undefined) ? '' : Number(n).toFixed(dec === undefined ? 1 : dec).replace('.', SEP);
  NT.perc = v => v === null || v === undefined ? '' : (v * 100).toFixed(v >= 0.995 || v < 0.01 ? 1 : 0).replace('.', SEP) + '%';
  NT.migliaia = n => Number(n).toLocaleString(NT.locale);
  /* 'AAAA-MM-GG' -> 08/11/2026 (it, fr, es), 08.11.2026 (de), 8 Nov 2026 (en) */
  NT.fmtData = iso => {
    if (!iso) return '';
    const [a, m, g] = iso.slice(0, 10).split('-');
    if (NT.lingua === 'en') return String(+g) + ' ' + MESI_EN[+m - 1] + ' ' + a;
    return g + (NT.lingua === 'de' ? '.' + m + '.' : '/' + m + '/') + a;
  };
  NT.fmtDataOra = iso => iso ? NT.fmtData(iso) + ' ' + String(iso).slice(11, 16) : '';
  /* giorno e mese senza anno: 08/11, 08.11., 8 Nov */
  NT.fmtGiornoMese = iso => {
    if (!iso) return '';
    const [, m, g] = iso.slice(0, 10).split('-');
    if (NT.lingua === 'en') return String(+g) + ' ' + MESI_EN[+m - 1];
    return g + (NT.lingua === 'de' ? '.' + m + '.' : '/' + m);
  };
  NT.fraseGiorni = g => g === null || g === undefined ? '' : g <= 0 ? NT.t('oggi') : g === 1 ? NT.t('ieri')
    : g < 60 ? NT.t('{n} giorni fa', { n: g })
      : g < 700 ? NT.t('{n} mesi fa', { n: Math.round(g / 30.4) })
        : NT.tp(Math.round(g / 365), '{n} anno fa', '{n} anni fa');
})();
'''
WEB_FILES["/i18n.js"] = ("text/javascript; charset=utf-8", _WEB_I18N_JS.encode("utf-8"))

_WEB_I18N_DE_JS = r'''/* Traduzioni dell'interfaccia di NeoTracker: de. Chiave = testo italiano originale.
   I segnaposto {nome} vanno lasciati uguali. Controllo: python3 tools/traduzioni.py */
(window.NT_DIZIONARI = window.NT_DIZIONARI || {}).de = {
  "(licenza CC BY 4.0). Il servizio gratuito è per uso personale e non commerciale.": "(Lizenz CC BY 4.0). Der kostenlose Dienst ist für den persönlichen, nicht kommerziellen Gebrauch bestimmt.",
  "(ora locale del luogo)": "(Ortszeit des Standorts)",
  "(ricerca salvata del {data})": "(gespeicherte Suche vom {data})",
  "(senza titolo)": "(ohne Titel)",
  "(vuoto)": "(leer)",
  "({variazione} mm dalla foto precedente)": "({variazione} mm seit dem vorherigen Foto)",
  "1 foto del {data}, diametro {mm} mm.": "1 Foto vom {data}, Durchmesser {mm} mm.",
  "1 foto del {data}.": "1 Foto vom {data}.",
  "100 o più": "100 oder mehr",
  "100 o più nei sul corpo": "100 oder mehr Muttermale am Körper",
  "3 = da qui l'OMS consiglia protezione": "3 = ab hier empfiehlt die WHO Schutz",
  "3 o più melanomi primari nella stessa persona": "3 oder mehr primäre Melanome bei derselben Person",
  "A che cosa servono questi dati?": "Wozu dienen diese Angaben?",
  "Accesso non autorizzato.": "Unbefugter Zugriff.",
  "Accetto e continuo": "Akzeptieren und fortfahren",
  "Addome alto destro": "Oberbauch rechts",
  "Addome alto sinistro": "Oberbauch links",
  "Addome basso destro": "Unterbauch rechts",
  "Addome basso sinistro": "Unterbauch links",
  "Adesso": "Jetzt",
  "Aggiorna": "Aktualisieren",
  "Aggiungi la prima foto: diventa la tua foto storica, e ogni foto successiva ne seguirà l'evoluzione.": "Fügen Sie das erste Foto hinzu: Es wird Ihr Ausgangsfoto, und jedes weitere Foto zeigt, wie sich das Muttermal entwickelt.",
  "Aggiungi neo": "Muttermal hinzufügen",
  "Aggiungi qui sotto la prima foto: sarà il punto di partenza per vedere se il neo cambia nel tempo.": "Fügen Sie unten das erste Foto hinzu: Es ist der Ausgangspunkt, um zu sehen, ob sich das Muttermal mit der Zeit verändert.",
  "Aggiungi una foto allo storico": "Foto zum Verlauf hinzufügen",
  "Alla sottoscrizione il limite giornaliero predefinito è di 2.000 chiamate: nella scheda «Billing plans» del tuo account puoi abbassarlo a 1.000, così non spendi nulla. NeoTracker ne usa poche (al massimo 4 ogni 10 minuti, solo quando apri la pagina Indice UV).": "Beim Abschluss liegt das tägliche Standardlimit bei 2.000 Abrufen: Im Reiter «Billing plans» Ihres Kontos können Sie es auf 1.000 senken, dann entstehen keine Kosten. NeoTracker braucht nur wenige (höchstens 4 alle 10 Minuten, nur wenn Sie die Seite UV-Index öffnen).",
  "Almeno 3 diagnosi tra melanoma, tumore del pancreas e astrocitoma nella stessa linea familiare (tua inclusa)": "Mindestens 3 Diagnosen aus Melanom, Bauchspeicheldrüsenkrebs und Astrozytom in derselben Familienlinie (Ihre eigene eingeschlossen)",
  "Almeno un metodo (o un suo modello) segnala una lesione da attenzionare. Non è una diagnosi e questi strumenti sbagliano spesso, ma è un motivo in più per non rimandare la visita dermatologica e per portare questo rapporto.": "Mindestens eine Methode (oder eines ihrer Modelle) meldet eine auffällige Läsion. Das ist keine Diagnose, und diese Werkzeuge irren sich oft; es ist aber ein weiterer Grund, den Hautarzttermin nicht aufzuschieben und diesen Bericht mitzubringen.",
  "Alto": "Hoch",
  "Alto (raro)": "Hoch (selten)",
  "Alto (sindrome BAP1)": "Hoch (BAP1-Syndrom)",
  "Altri parenti con melanoma": "Weitere Verwandte mit Melanom",
  "Altri tumori della pelle (basalioma, spinalioma)": "Andere Hautkrebsarten (Basaliom, Plattenepithelkarzinom)",
  "Altro": "Andere",
  "Altro che vuoi ricordare (allergie, farmaci fotosensibilizzanti, …)": "Sonstiges, woran Sie sich erinnern möchten (Allergien, lichtsensibilisierende Medikamente, …)",
  "Analisi automatica": "Automatische Analyse",
  "Analisi delle foto": "Fotoanalyse",
  "Analisi in corso…": "Analyse läuft…",
  "Analisi interrotta dopo {ore} ore (troppo lunga).": "Analyse nach {ore} Stunden abgebrochen (zu lang).",
  "Analisi: da attenzionare": "Analyse: auffällig",
  "Analizza questa foto": "Dieses Foto analysieren",
  "Analizza subito con tutti i metodi installati": "Jetzt mit allen installierten Methoden analysieren",
  "Anche la ricerca delle città usa Open-Meteo.": "Auch die Ortssuche nutzt Open-Meteo.",
  "Ancora nessuna foto": "Noch keine Fotos",
  "Annulla": "Abbrechen",
  "Anteprima": "Vorschau",
  "App 1 (DeborahAdedigba) - modelli TensorFlow": "App 1 (DeborahAdedigba) - TensorFlow-Modelle",
  "App per smartphone e rischio di cancro della pelle: accuratezza diagnostica": "Smartphone-Apps und Hautkrebsrisiko: diagnostische Genauigkeit",
  "Apri la pagina «API keys» del tuo account e copia la chiave.": "Öffnen Sie in Ihrem Konto die Seite «API keys» und kopieren Sie den Schlüssel.",
  "Archivia (toglie dalla mappa, conserva i dati)": "Archivieren (entfernt es von der Karte, die Daten bleiben erhalten)",
  "Articoli recenti e rilevanti su come riconoscere i nei sospetti, sull'affidabilità di app e intelligenza artificiale e sul melanoma ereditario. I risultati arrivano da PubMed, la banca dati pubblica della National Library of Medicine (USA).": "Aktuelle, relevante Artikel zum Erkennen verdächtiger Muttermale, zur Zuverlässigkeit von Apps und künstlicher Intelligenz und zum erblichen Melanom. Die Ergebnisse stammen von PubMed, der öffentlichen Datenbank der National Library of Medicine (USA).",
  "Asimmetria": "Asymmetrie",
  "Aspetto": "Erscheinungsbild",
  "Associati a varianti del gene MC1R.": "Verbunden mit Varianten des MC1R-Gens.",
  "Astrocitoma": "Astrozytom",
  "Attenzione: non ho trovato l'ambiente .venv di App 1, uso il Python corrente.": "Achtung: Die .venv-Umgebung von App 1 wurde nicht gefunden; es wird das aktuelle Python verwendet.",
  "Aumenta: {voce}": "Erhöhen: {voce}",
  "Autoesame della pelle": "Selbstuntersuchung der Haut",
  "Automatica (come il sistema)": "Automatisch (wie das System)",
  "Avambraccio destro": "Unterarm rechts",
  "Avambraccio sinistro": "Unterarm links",
  "Avvertenze": "Hinweise",
  "Azzurri/grigi": "Blau/grau",
  "Basso": "Niedrig",
  "Basso-moderato (comune)": "Niedrig bis mäßig (häufig)",
  "Benvenuto in NeoTracker": "Willkommen bei NeoTracker",
  "Biondi": "Blond",
  "Bordi": "Rand",
  "Braccio destro": "Arm rechts",
  "Braccio sinistro": "Arm links",
  "Cambia": "Wechseln",
  "Cambia immagine…": "Bild ändern…",
  "Cambia nel tempo: forma, colore, dimensione, rilievo, o compaiono prurito o sanguinamento.": "Es verändert sich im Lauf der Zeit: Form, Farbe, Größe, Erhabenheit, oder es treten Juckreiz oder Blutungen auf.",
  "Cambia utente": "Benutzer wechseln",
  "Capelli": "Haare",
  "Capelli rossi o biondi": "Rote oder blonde Haare",
  "Carcinoma del rene": "Nierenzellkarzinom",
  "Caricamento…": "Wird geladen…",
  "Cartella dei progetti:": "Projektordner:",
  "Cartella dei tuoi dati (da copiare per il backup):": "Ordner mit Ihren Daten (für die Sicherung kopieren):",
  "Castani": "Braun",
  "Caviglia destra": "Knöchel rechts",
  "Caviglia sinistra": "Knöchel links",
  "Cavo popliteo destro": "Kniekehle rechts",
  "Cavo popliteo sinistro": "Kniekehle links",
  "Centra sulla mappa": "Auf der Karte zentrieren",
  "Cerca": "Suchen",
  "Cerca altro (es. \"ugly duckling sign\", \"nail melanoma\"…)": "Weiter suchen (z. B. \"ugly duckling sign\", \"nail melanoma\"…)",
  "Cerca nella letteratura": "In der Literatur suchen",
  "Cerca una città (es. Torino)": "Stadt suchen (z. B. Turin)",
  "Cerco su PubMed…": "Suche in PubMed…",
  "Cerco…": "Suche läuft…",
  "Chi ha avuto un melanoma ha un rischio maggiore di un secondo.": "Wer ein Melanom hatte, hat ein höheres Risiko für ein zweites.",
  "Chi ha tanti nei, nei atipici o una storia di melanoma dovrebbe proteggersi anche con indici moderati.": "Wer viele Muttermale, atypische Muttermale oder ein Melanom in der Vorgeschichte hat, sollte sich auch bei mäßigem Index schützen.",
  "Chi sei?": "Wer sind Sie?",
  "Chiave OpenWeather": "OpenWeather-Schlüssel",
  "Chiave OpenWeather salvata ({finale}).": "OpenWeather-Schlüssel gespeichert ({finale}).",
  "Chiave rimossa.": "Schlüssel entfernt.",
  "Chiave salvata ({finale}) — scrivine una nuova per sostituirla": "Schlüssel gespeichert ({finale}) — geben Sie einen neuen ein, um ihn zu ersetzen",
  "Chiave salvata.": "Schlüssel gespeichert.",
  "Chiedo la posizione al browser… (potrebbe comparire una richiesta di permesso)": "Der Browser wird nach Ihrem Standort gefragt… (möglicherweise erscheint eine Berechtigungsanfrage)",
  "Chiudere NeoTracker?": "NeoTracker beenden?",
  "Chiudere il programma": "Programm beenden",
  "Chiudi": "Schließen",
  "Chiudi NeoTracker": "NeoTracker beenden",
  "Chiudi il programma": "Programm beenden",
  "Circa il 5-10% dei melanomi si presenta in famiglie con una predisposizione ereditaria (Leachman 2009). Qui trovi i criteri che usano gli specialisti per decidere se proporre una consulenza genetica, i geni coinvolti e la letteratura su ciascuno.": "Etwa 5–10 % der Melanome treten in Familien mit erblicher Veranlagung auf (Leachman 2009). Hier finden Sie die Kriterien, nach denen Fachleute entscheiden, ob eine genetische Beratung angeboten wird, die beteiligten Gene und die Literatur zu jedem von ihnen.",
  "Citato dalle linee guida NCCN tra i geni da considerare nei pannelli per melanoma (sindrome di Cowden).": "Von den NCCN-Leitlinien unter den Genen genannt, die in Melanom-Panels zu berücksichtigen sind (Cowden-Syndrom).",
  "Classificati come cancerogeni certi per l'uomo (IARC).": "Als sicher krebserregend für den Menschen eingestuft (IARC).",
  "Clic per vedere la foto originale a schermo intero": "Klicken, um das Originalfoto im Vollbild zu sehen",
  "Clicca sul punto esatto del corpo dove si trova il neo (puoi ingrandire prima)": "Klicken Sie auf die genaue Stelle am Körper, an der sich das Muttermal befindet (Sie können vorher zoomen)",
  "Clicca un neo nell'elenco o sulla mappa per vedere lo storico fotografico.": "Klicken Sie ein Muttermal in der Liste oder auf der Karte an, um seinen Fotoverlauf zu sehen.",
  "Collo": "Hals",
  "Colore": "Farbe",
  "Colore degli occhi": "Augenfarbe",
  "Colore naturale dei capelli (da giovane)": "Natürliche Haarfarbe (in jungen Jahren)",
  "Come ottenere la chiave": "So erhalten Sie den Schlüssel",
  "Come scattare foto confrontabili": "So machen Sie vergleichbare Fotos",
  "Come si legge l'indice UV": "So lesen Sie den UV-Index",
  "Compila la familiarità nel Profilo": "Familienanamnese im Profil ausfüllen",
  "Compila la sezione 'Familiarità' nel Profilo: senza quei dati non posso verificare i criteri.": "Füllen Sie im Profil den Abschnitt „Familienanamnese“ aus: Ohne diese Angaben kann ich die Kriterien nicht prüfen.",
  "Con i dati inseriti non rientri nei criteri più usati. Il test genetico per il melanoma è indicato solo in una piccola minoranza di persone e non viene proposto di routine. Se la tua storia familiare cambia o hai dubbi, aggiorna il profilo e parlane col dermatologo.": "Mit den eingegebenen Daten erfüllen Sie die gebräuchlichsten Kriterien nicht. Ein Gentest auf Melanom ist nur bei einer kleinen Minderheit von Menschen angezeigt und wird nicht routinemäßig angeboten. Wenn sich Ihre Familiengeschichte ändert oder Sie Zweifel haben, aktualisieren Sie Ihr Profil und sprechen Sie mit Ihrer Hautärztin oder Ihrem Hautarzt.",
  "Con i dati inseriti non risultano fattori di rischio noti. Completa il profilo se mancano informazioni.": "Mit den eingegebenen Daten sind keine bekannten Risikofaktoren erkennbar. Vervollständigen Sie Ihr Profil, falls Angaben fehlen.",
  "Con il tuo fototipo ({fototipo})": "Mit Ihrem Hauttyp ({fototipo})",
  "Con o senza test, per chi ha una storia familiare restano fondamentali la protezione dal sole, l'autoesame della pelle e i controlli dermatologici periodici.": "Mit oder ohne Test bleiben bei familiärer Vorbelastung Sonnenschutz, Selbstuntersuchung der Haut und regelmäßige dermatologische Kontrollen entscheidend.",
  "Conferma": "Bestätigen",
  "Confronta": "Vergleichen",
  "Confronta forma, bordi e colori: se noti differenze, mostra le foto al dermatologo.": "Vergleichen Sie Form, Ränder und Farben: Wenn Ihnen Unterschiede auffallen, zeigen Sie die Fotos Ihrer Hautärztin oder Ihrem Hautarzt.",
  "Confronto tra due foto": "Vergleich zweier Fotos",
  "Consenso": "Einwilligung",
  "Conta anche il «brutto anatroccolo»: un neo diverso da tutti gli altri. I noduli che crescono rapidamente o sono duri al tatto vanno mostrati subito. Questo promemoria non sostituisce la visita.": "Auch das «hässliche Entlein» zählt: ein Muttermal, das sich von allen anderen unterscheidet. Knoten, die schnell wachsen oder sich hart anfühlen, sollten sofort gezeigt werden. Diese Erinnerung ersetzt keinen Arztbesuch.",
  "Conta i parenti di sangue (non quelli acquisiti) dello stesso lato della famiglia, materno o paterno: è il criterio che usano i genetisti. Se non lo sai, chiedi a un familiare: queste informazioni sono molto utili.": "Zählen Sie Blutsverwandte (keine angeheirateten) auf derselben Seite der Familie, mütterlicher- oder väterlicherseits: Das ist das Kriterium der Genetiker. Wenn Sie es nicht wissen, fragen Sie einen Angehörigen: Diese Informationen sind sehr nützlich.",
  "Conta solo i melanomi primari invasivi.": "Es zählen nur invasive primäre Melanome.",
  "Controllo lo stato…": "Status wird geprüft…",
  "Coordinate non valide.": "Ungültige Koordinaten.",
  "Cosa fare": "Was tun",
  "Cosa sapere prima di un test genetico": "Was Sie vor einem Gentest wissen sollten",
  "Coscia destra": "Oberschenkel rechts",
  "Coscia sinistra": "Oberschenkel links",
  "Crea un account gratuito su": "Erstellen Sie ein kostenloses Konto bei",
  "Crea utente": "Benutzer anlegen",
  "Criteri ABCDE e segno del 'brutto anatroccolo'": "ABCDE-Kriterien und das Zeichen des „hässlichen Entleins“",
  "Criteri semplificati, a scopo informativo. Il test genetico riguarda una piccola minoranza di persone e non è un esame di routine: è lo specialista a decidere se e quale test proporre, di norma dopo una consulenza genetica e partendo, quando possibile, da un familiare che ha avuto la malattia.": "Vereinfachte Kriterien, nur zur Information. Ein Gentest betrifft eine kleine Minderheit von Menschen und ist keine Routineuntersuchung: Ob und welcher Test angeboten wird, entscheidet die Fachärztin oder der Facharzt, in der Regel nach einer genetischen Beratung und möglichst ausgehend von einem erkrankten Angehörigen.",
  "Cuoio capelluto (testa)": "Kopfhaut (Kopf)",
  "Cursore di confronto": "Vergleichsregler",
  "D": "R",
  "D = destra del paziente · S = sinistra": "R = rechts des Patienten · L = links",
  "Da 50 a 99 nei sul corpo": "50 bis 99 Muttermale am Körper",
  "Da attenzionare": "Auffällig",
  "Da rifotografare?": "Neu fotografieren?",
  "Dai un nome al neo e controlla la sede.": "Geben Sie dem Muttermal einen Namen und prüfen Sie die Stelle.",
  "Data della foto troppo vecchia.": "Das Aufnahmedatum liegt zu weit zurück.",
  "Data dello scatto": "Aufnahmedatum",
  "Data di nascita": "Geburtsdatum",
  "Data di nascita fuori intervallo.": "Geburtsdatum außerhalb des zulässigen Bereichs.",
  "Data di nascita non valida (AAAA-MM-GG).": "Ungültiges Geburtsdatum (JJJJ-MM-TT).",
  "Data non valida: usa il formato AAAA-MM-GG.": "Ungültiges Datum: Verwenden Sie das Format JJJJ-MM-TT.",
  "Dati della persona": "Angaben zur Person",
  "Dati meteo e UV:": "Wetter- und UV-Daten:",
  "Dati non validi (JSON).": "Ungültige Daten (JSON).",
  "Dati non validi.": "Ungültige Daten.",
  "Dati orari non disponibili": "Stundenwerte nicht verfügbar",
  "Dati personali": "Persönliche Daten",
  "Deep learning e melanoma: revisioni sistematiche": "Deep Learning und Melanom: systematische Übersichtsarbeiten",
  "Dermoscopia e diagnosi precoce (revisioni)": "Dermatoskopie und Früherkennung (Übersichtsarbeiten)",
  "Dermoscopica": "Dermatoskopisch",
  "Di qualsiasi grado di parentela.": "Jeder Verwandtschaftsgrad.",
  "Diagnosi totali indicate: {diagnosi}. Leachman 2009 considera melanoma e tumore del pancreas nei parenti di 1o e 2o grado dello stesso lato della famiglia; l'astrocitoma è incluso dalle linee guida NCCN.": "Insgesamt angegebene Diagnosen: {diagnosi}. Leachman 2009 berücksichtigt Melanom und Bauchspeicheldrüsenkrebs bei Verwandten 1. und 2. Grades derselben Familienseite; das Astrozytom wird von den NCCN-Leitlinien einbezogen.",
  "Diametro": "Durchmesser",
  "Diametro (mm)": "Durchmesser (mm)",
  "Diametro del neo nel tempo": "Durchmesser des Muttermals im Zeitverlauf",
  "Diametro misurato (mm)": "Gemessener Durchmesser (mm)",
  "Diametro nel tempo": "Durchmesser im Zeitverlauf",
  "Diametro:": "Durchmesser:",
  "Diametro: da {da} a {a} mm.": "Durchmesser: von {da} auf {a} mm.",
  "Diametro: {diff} mm di differenza.": "Durchmesser: {diff} mm Unterschied.",
  "Diminuisci: {voce}": "Verringern: {voce}",
  "Donna": "Frau",
  "Dopo": "Nachher",
  "Dove si trovano": "Wo sie sich befinden",
  "Efelidi": "Sommersprossen",
  "Efelidi (lentiggini)": "Sommersprossen (Epheliden)",
  "Elenco di fattori noti dalla letteratura, non un punteggio validato: non stima la probabilità di ammalarsi.": "Liste von Faktoren, die aus der Literatur bekannt sind, kein validierter Score: Sie schätzt nicht die Wahrscheinlichkeit zu erkranken.",
  "Elimina": "Löschen",
  "Elimina definitivamente": "Endgültig löschen",
  "Elimina foto": "Foto löschen",
  "Elimina questo neo e le sue foto": "Dieses Muttermal und seine Fotos löschen",
  "Eliminare questa foto?": "Dieses Foto löschen?",
  "Eliminare «{nome}»?": "«{nome}» löschen?",
  "Email non valida.": "Ungültige E-Mail-Adresse.",
  "Email per PubMed": "E-Mail für PubMed",
  "Email salvata.": "E-Mail gespeichert.",
  "Errore imprevisto: {e}": "Unerwarteter Fehler: {e}",
  "Errore interno. I dettagli sono nel file neotracker.log nella cartella dei dati.": "Interner Fehler. Einzelheiten stehen in der Datei neotracker.log im Datenordner.",
  "Errore {codice}": "Fehler {codice}",
  "Esci dal programma": "Programm beenden",
  "Esiste già un utente con questo nome.": "Ein Benutzer mit diesem Namen existiert bereits.",
  "Esposizione al sole": "Sonnenexposition",
  "Estremo": "Extrem",
  "Età": "Alter",
  "Età, sesso e fenotipo non cambiano l'uscita delle reti neurali: servono a mostrarti i fattori di rischio, a scegliere la letteratura, a valutare i criteri di genetica e a stimare il tempo di scottatura.": "Alter, Geschlecht und Phänotyp verändern das Ergebnis der neuronalen Netze nicht: Sie dienen dazu, Ihnen die Risikofaktoren zu zeigen, die Literatur auszuwählen, die genetischen Kriterien zu bewerten und die Zeit bis zum Sonnenbrand abzuschätzen.",
  "Evita il sole nelle ore centrali e proteggi bene la pelle.": "Meiden Sie die Sonne in den Mittagsstunden und schützen Sie Ihre Haut gut.",
  "Evita l'esposizione diretta: la pelle non protetta può scottarsi in pochi minuti.": "Meiden Sie direkte Sonne: Ungeschützte Haut kann innerhalb weniger Minuten verbrennen.",
  "Evoluzione": "Entwicklung",
  "FRONTE": "VORDERSEITE",
  "Facoltativa": "Optional",
  "Fajuyigbe D, Young AR. The impact of skin colour on human photobiological responses. Pigment Cell Melanoma Res 2016;29:607-18 (dose minima di eritema per fototipo)": "Fajuyigbe D, Young AR. The impact of skin colour on human photobiological responses. Pigment Cell Melanoma Res 2016;29:607-18 (minimale Erythemdosis nach Hauttyp)",
  "Familiarità": "Familienanamnese",
  "Fattori di rischio indicati:": "Angegebene Risikofaktoren:",
  "Fattori di rischio presenti": "Vorhandene Risikofaktoren",
  "Fenotipo: pelle, capelli, occhi": "Phänotyp: Haut, Haare, Augen",
  "File della foto non trovato.": "Fotodatei nicht gefunden.",
  "Fonte dell'indice UV cambiata.": "Quelle des UV-Index geändert.",
  "Fonte dell'indice UV non valida.": "Ungültige Quelle für den UV-Index.",
  "Fonte:": "Quelle:",
  "Fonti": "Quellen",
  "Formato non supportato: servono JPG, PNG, WEBP o BMP.": "Nicht unterstütztes Format: Erforderlich sind JPG, PNG, WEBP oder BMP.",
  "Formato non supportato: servono JPG, PNG, WEBP o BMP. Le foto HEIC degli iPhone vanno convertite in JPG (impostazioni fotocamera: 'Più compatibile').": "Nicht unterstütztes Format: Erforderlich sind JPG, PNG, WEBP oder BMP. HEIC-Fotos vom iPhone müssen in JPG umgewandelt werden (Kameraeinstellungen: „Maximale Kompatibilität“).",
  "Foto a fuoco, con il neo al centro e la pelle ben visibile (sposta i peli, se serve).": "Scharfes Foto mit dem Muttermal in der Mitte und gut sichtbarer Haut (Haare bei Bedarf zur Seite schieben).",
  "Foto del {data}": "Foto vom {data}",
  "Foto eliminata.": "Foto gelöscht.",
  "Foto non trovata.": "Foto nicht gefunden.",
  "Foto normale": "Normales Foto",
  "Foto normale (smartphone)": "Normales Foto (Smartphone)",
  "Foto originale": "Originalfoto",
  "Foto salvata ({data}).": "Foto gespeichert ({data}).",
  "Foto salvata ({data}, data letta dalla foto).": "Foto gespeichert ({data}, Datum aus dem Foto gelesen).",
  "Fotografia sequenziale e monitoraggio dei nei nel tempo": "Sequenzielle Fotografie und Verlaufskontrolle von Muttermalen",
  "Fototipo": "Hauttyp",
  "Fototipo (classificazione di Fitzpatrick)": "Hauttyp (Fitzpatrick-Klassifikation)",
  "Fototipo chiaro (I-II)": "Heller Hauttyp (I–II)",
  "Fototipo, età e familiarità non cambiano il risultato delle reti neurali (guardano solo i pixel): servono a contestualizzare il rischio.": "Hauttyp, Alter und Familiengeschichte verändern das Ergebnis der neuronalen Netze nicht (sie betrachten nur Pixel): Sie dienen dazu, das Risiko einzuordnen.",
  "Fronte": "Vorderseite",
  "Fronte e cuoio capelluto": "Stirn und Kopfhaut",
  "Gamba (stinco) destra": "Unterschenkel (Schienbein) rechts",
  "Gamba (stinco) sinistra": "Unterschenkel (Schienbein) links",
  "Gene": "Gen",
  "Gene dei telomeri (complesso shelterin): varianti rare in famiglie con melanoma.": "Telomer-Gen (Shelterin-Komplex): seltene Varianten in Familien mit Melanom.",
  "Gene dei telomeri: varianti rare in alcune famiglie con melanoma.": "Telomer-Gen: seltene Varianten in einigen Familien mit Melanom.",
  "Gene non presente nell'elenco.": "Gen nicht in der Liste.",
  "Gene {n} di {tot} ({nome})…": "Gen {n} von {tot} ({nome})…",
  "Genetica": "Genetik",
  "Genitori, fratelli o figli.": "Eltern, Geschwister oder Kinder.",
  "Genitori, fratelli, sorelle, figli.": "Eltern, Brüder, Schwestern, Kinder.",
  "Ginocchio destro": "Knie rechts",
  "Ginocchio sinistro": "Knie links",
  "Gli articoli sono scelti da una ricerca automatica e non sono stati valutati da NeoTracker: leggili con il tuo medico.": "Die Artikel werden durch eine automatische Suche ausgewählt und wurden von NeoTracker nicht bewertet: Lesen Sie sie gemeinsam mit Ihrer Ärztin oder Ihrem Arzt.",
  "Gluteo destro": "Gesäß rechts",
  "Gluteo sinistro": "Gesäß links",
  "Gomito destro": "Ellbogen rechts",
  "Gomito sinistro": "Ellbogen links",
  "Grigi/bianchi": "Grau/weiß",
  "Hai indicato di aver già eseguito un test genetico: porta il referto al dermatologo.": "Sie haben angegeben, bereits einen Gentest durchgeführt zu haben: Bringen Sie den Befund zu Ihrer Hautärztin oder Ihrem Hautarzt mit.",
  "Hai scelto OpenWeather ma manca la chiave (Impostazioni): mostro i dati di Open-Meteo.": "Sie haben OpenWeather gewählt, aber der Schlüssel fehlt (Einstellungen): Es werden die Daten von Open-Meteo angezeigt.",
  "Hai scelto OpenWeather ma non c'è ancora una chiave: finché manca, il programma usa Open-Meteo.": "Sie haben OpenWeather gewählt, aber es gibt noch keinen Schlüssel: Solange er fehlt, verwendet das Programm Open-Meteo.",
  "Ho avuto (o ho) uno di questi tumori:": "Ich hatte (oder habe) eine dieser Krebserkrankungen:",
  "Ho avuto altri tumori della pelle (basalioma, spinalioma)": "Ich hatte andere Hautkrebsarten (Basaliom, Plattenepithelkarzinom)",
  "Ho già fatto un test genetico per il melanoma?": "Habe ich bereits einen Gentest auf Melanom durchführen lassen?",
  "Ho letto e capito queste avvertenze": "Ich habe diese Hinweise gelesen und verstanden",
  "Ho verificato la mia storia familiare (anche se la risposta è «nessuno»)": "Ich habe meine Familiengeschichte überprüft (auch wenn die Antwort «keine» lautet)",
  "I dati (anche di salute) restano su questo computer. Escono solo le richieste che attivi tu: indice UV (coordinate approssimate), ricerche su PubMed (solo i termini cercati) e, solo se lo attivi, l'invio della foto a SkinSense.": "Ihre Daten (auch Gesundheitsdaten) bleiben auf diesem Computer. Nur die Anfragen, die Sie aktivieren, verlassen ihn: UV-Index (ungefähre Koordinaten), PubMed-Suchen (nur die Suchbegriffe) und, nur wenn Sie es einschalten, das Senden des Fotos an SkinSense.",
  "I dati inseriti rientrano in almeno un criterio descritto in letteratura. Ti consigliamo di parlarne con il dermatologo o con un medico genetista (consulenza genetica oncologica): sarà lo specialista a decidere se e quale test proporre, di norma dopo la consulenza e, quando possibile, partendo da un familiare affetto. Geni più citati dalle linee guida: {geni}. L'uso dei pannelli multigene è ancora oggetto di discussione tra gli specialisti: per questo conta la consulenza prima del test.": "Die eingegebenen Daten erfüllen mindestens ein in der Literatur beschriebenes Kriterium. Wir empfehlen, mit Ihrer Hautärztin bzw. Ihrem Hautarzt oder einem Facharzt für Humangenetik (onkogenetische Beratung) darüber zu sprechen: Die Fachperson entscheidet, ob und welcher Test angeboten wird, in der Regel nach der Beratung und möglichst ausgehend von einem erkrankten Angehörigen. Am häufigsten in den Leitlinien genannte Gene: {geni}. Der Einsatz von Multigen-Panels wird unter Fachleuten noch diskutiert: Deshalb ist die Beratung vor dem Test wichtig.",
  "I geni più studiati": "Die am besten untersuchten Gene",
  "I metodi sono addestrati su fotografie diverse dalle tue: cambiare luce, distanza o fotocamera può cambiare la risposta.": "Die Methoden wurden mit anderen Fotos als Ihren trainiert: Andere Beleuchtung, Entfernung oder Kamera können das Ergebnis verändern.",
  "I numeri corrispondono alle schede seguenti. Sulla figura: a sinistra la vista frontale, a destra quella posteriore.": "Die Nummern entsprechen den folgenden Blättern. In der Abbildung: links die Vorderansicht, rechts die Rückansicht.",
  "I raggi ultravioletti sono il principale fattore di rischio modificabile per il melanoma. Qui vedi quanto sono forti oggi dove ti trovi.": "UV-Strahlen sind der wichtigste beeinflussbare Risikofaktor für das Melanom. Hier sehen Sie, wie stark sie heute an Ihrem Standort sind.",
  "I risultati sono stime sperimentali e possono sbagliare in entrambe le direzioni: un esito rassicurante non esclude un melanoma, un esito di attenzione non significa che ci sia.": "Die Ergebnisse sind experimentelle Schätzungen und können in beide Richtungen falsch sein: Ein beruhigendes Ergebnis schließt ein Melanom nicht aus, ein auffälliges Ergebnis bedeutet nicht, dass eines vorliegt.",
  "I tuoi dati rispetto ai criteri": "Ihre Angaben im Vergleich zu den Kriterien",
  "I tuoi nei ({n})": "Ihre Muttermale ({n})",
  "Identificativo di pagina non valido.": "Ungültige Seitenkennung.",
  "Il computer non riesce a determinare la posizione. Cerca la città per nome.": "Der Computer kann den Standort nicht bestimmen. Suchen Sie die Stadt nach Namen.",
  "Il file non è un'immagine leggibile o è troppo grande.": "Die Datei ist kein lesbares Bild oder zu groß.",
  "Il file non è un'immagine leggibile, è danneggiato o ha troppi pixel (massimo {mp} megapixel).": "Die Datei ist kein lesbares Bild, ist beschädigt oder hat zu viele Pixel (höchstens {mp} Megapixel).",
  "Il file è troppo grande (massimo 40 MB).": "Die Datei ist zu groß (höchstens 40 MB).",
  "Il file è vuoto.": "Die Datei ist leer.",
  "Il metodo 3 NON ha analizzato la foto: il progetto e' un prototipo senza modello. Il suo server si limita a ricevere l'immagine (nessuna rete neurale), quindi qualunque testo rassicurante mostri non deriva da un'analisi e non ha alcun valore.": "Methode 3 hat das Foto NICHT analysiert: Das Projekt ist ein Prototyp ohne Modell. Sein Server nimmt das Bild lediglich entgegen (kein neuronales Netz); jeder beruhigende Text, den er anzeigt, stammt daher nicht aus einer Analyse und hat keinerlei Wert.",
  "Il metodo 5 e' un'app Android: non puo' girare dal PC. Installa l'APK sul telefono, inquadra il neo e annota a mano il risultato qui sotto.\nRisultato dell'app sul telefono: ______________________________": "Methode 5 ist eine Android-App: Sie kann nicht auf dem PC laufen. Installieren Sie die APK auf dem Telefon, richten Sie die Kamera auf das Muttermal und notieren Sie das Ergebnis unten von Hand.\nErgebnis der App auf dem Telefon: ______________________________",
  "Il metodo {n} ha detto che:": "Methode {n} meldete:",
  "Il nome": "Der Name",
  "Il numero di nei è uno dei fattori di rischio più forti.": "Die Zahl der Muttermale ist einer der stärksten Risikofaktoren.",
  "Il programma si spegne. Un'analisi in corso viene interrotta. I dati restano salvati.": "Das Programm wird beendet. Eine laufende Analyse wird abgebrochen. Ihre Daten bleiben gespeichert.",
  "Il risultato riguarda anche i familiari di sangue: per questo la consulenza prima e dopo il test è parte del percorso.": "Das Ergebnis betrifft auch Blutsverwandte: Deshalb gehört die Beratung vor und nach dem Test zum Ablauf.",
  "Il servizio Open-Meteo non risponde ({e}).": "Der Dienst Open-Meteo antwortet nicht ({e}).",
  "Immagine personale": "Eigenes Bild",
  "Immagine personale salvata.": "Eigenes Bild gespeichert.",
  "Immagine rimossa.": "Bild entfernt.",
  "Immunosoppressione (terapie, trapianto)": "Immunsuppression (Therapien, Transplantation)",
  "Impostazioni": "Einstellungen",
  "In coda (posizione {n})…": "In der Warteschlange (Position {n})…",
  "In coda…": "In der Warteschlange…",
  "In inglese": "Auf Englisch",
  "Incolla la chiave qui sopra e premi «Prova la chiave». Dopo l'iscrizione la chiave può impiegare qualche minuto ad attivarsi. Il programma prova prima One Call 4.0 e, se la chiave è di un abbonamento più vecchio, One Call 3.0.": "Fügen Sie den Schlüssel oben ein und klicken Sie auf «Schlüssel testen». Nach dem Abschluss kann es einige Minuten dauern, bis der Schlüssel aktiv ist. Das Programm versucht zuerst One Call 4.0 und, falls der Schlüssel zu einem älteren Tarif gehört, One Call 3.0.",
  "Incolla prima la chiave.": "Fügen Sie zuerst den Schlüssel ein.",
  "Incolla qui la chiave (32 lettere e numeri)": "Schlüssel hier einfügen (32 Buchstaben und Ziffern)",
  "Indice UV": "UV-Index",
  "Indice UV di oggi": "UV-Index heute",
  "Indice UV non disponibile": "UV-Index nicht verfügbar",
  "Indice UV ora per ora nelle prossime 24 ore": "UV-Index Stunde für Stunde für die nächsten 24 Stunden",
  "Indice UV: fonte dei dati": "UV-Index: Datenquelle",
  "Indirizzo non ammesso.": "Adresse nicht zulässig.",
  "Indirizzo sconosciuto.": "Unbekannte Adresse.",
  "Indirizzo troppo lungo.": "Adresse zu lang.",
  "Ingrandisci": "Vergrößern",
  "Inguine destro": "Leiste rechts",
  "Inguine sinistro": "Leiste links",
  "Inviare le foto a SkinSense?": "Fotos an SkinSense senden?",
  "Irregolari, frastagliati o sfumati.": "Unregelmäßig, gezackt oder verwaschen.",
  "Iscriviti all'abbonamento «One Call API» a pagamento per chiamata": "Schließen Sie den Tarif «One Call API» mit Bezahlung pro Abruf ab",
  "JPG, PNG, WEBP o BMP · fino a 60 MB": "JPG, PNG, WEBP oder BMP · bis 60 MB",
  "L'OMS consiglia di proteggersi a partire da un indice UV di 3.": "Die WHO empfiehlt Schutz ab einem UV-Index von 3.",
  "L'analisi di questa foto è in corso: attendi che finisca.": "Dieses Foto wird gerade analysiert: Warten Sie, bis die Analyse abgeschlossen ist.",
  "L'analisi non ha prodotto il rapporto. Ultime righe del log: {log}": "Die Analyse hat keinen Bericht erzeugt. Letzte Zeilen des Protokolls: {log}",
  "L'analisi non è riuscita.": "Die Analyse ist fehlgeschlagen.",
  "L'immagine supera {mb} MB.": "Das Bild ist größer als {mb} MB.",
  "L'indice è una previsione: il valore reale dipende da nuvole, quota e riflessi.": "Der Index ist eine Vorhersage: Der tatsächliche Wert hängt von Wolken, Höhe und Reflexionen ab.",
  "La chiave OpenWeather contiene caratteri non validi (di solito sono 32 lettere/numeri).": "Der OpenWeather-Schlüssel enthält ungültige Zeichen (normalerweise sind es 32 Buchstaben/Ziffern).",
  "La chiave resta salvata solo sul tuo computer e non viene mai mostrata né inviata alla pagina web del programma: la usa il programma Python per chiamare OpenWeather.": "Der Schlüssel bleibt nur auf Ihrem Computer gespeichert und wird der Webseite des Programms nie angezeigt oder gesendet: Das Python-Programm verwendet ihn, um OpenWeather aufzurufen.",
  "La chiave sarà cancellata da questo computer. Potrai inserirla di nuovo quando vuoi.": "Der Schlüssel wird von diesem Computer gelöscht. Sie können ihn jederzeit erneut eingeben.",
  "La data della foto non può essere nel futuro.": "Das Aufnahmedatum darf nicht in der Zukunft liegen.",
  "La foto del {data} e il suo rapporto di analisi saranno cancellati per sempre.": "Das Foto vom {data} und sein Analysebericht werden endgültig gelöscht.",
  "La foto resta sul tuo computer: SkinSense (servizio online) è disattivato.": "Das Foto bleibt auf Ihrem Computer: SkinSense (Online-Dienst) ist ausgeschaltet.",
  "La foto supera i {mb} MB: riducila o scegline un'altra.": "Das Foto ist größer als {mb} MB: Verkleinern Sie es oder wählen Sie ein anderes.",
  "La foto supera {MAX_MB_FOTO} MB.": "Das Foto ist größer als {MAX_MB_FOTO} MB.",
  "La libreria Pillow è vecchia e ha problemi di sicurezza noti: aggiornala con «py -m pip install -U pillow».": "Die Bibliothek Pillow ist veraltet und hat bekannte Sicherheitsprobleme: Aktualisieren Sie sie mit «py -m pip install -U pillow».",
  "La mia posizione ({lat}; {lon})": "Mein Standort ({lat}; {lon})",
  "La posizione resta salvata solo su questo computer; viene inviata al servizio meteo (coordinate arrotondate) per ottenere l'indice UV.": "Der Standort wird nur auf diesem Computer gespeichert; er wird (mit gerundeten Koordinaten) an den Wetterdienst gesendet, um den UV-Index zu erhalten.",
  "La prima analisi può richiedere diversi minuti (i modelli vengono caricati in memoria).": "Die erste Analyse kann mehrere Minuten dauern (die Modelle werden in den Speicher geladen).",
  "La scelta vale per tutti gli utenti di questo computer. Il testo originale e vincolante delle avvertenze legali è quello italiano; il rapporto di testo completo resta in italiano.": "Die Auswahl gilt für alle Benutzer dieses Computers. Maßgeblich und verbindlich ist der italienische Originaltext der rechtlichen Hinweise; der vollständige Textbericht bleibt auf Italienisch.",
  "La variante p.E318K aumenta il rischio di melanoma e di carcinoma renale e si associa a molti nei.": "Die Variante p.E318K erhöht das Risiko für Melanom und Nierenzellkarzinom und ist mit vielen Muttermalen verbunden.",
  "La vista deve essere 'fronte' o 'retro'.": "Die Ansicht muss 'fronte' oder 'retro' sein.",
  "Lampade": "Solarien",
  "Lampade abbronzanti": "Solarien",
  "Lampade o lettini abbronzanti": "Bräunungslampen oder Sonnenbänke",
  "Lavoro o attività prolungata all'aperto": "Arbeit oder längere Aktivität im Freien",
  "Lavoro o faccio attività per molte ore all'aperto": "Ich arbeite oder bin viele Stunden im Freien aktiv",
  "Le due metà del neo non si somigliano.": "Die beiden Hälften des Muttermals sehen nicht gleich aus.",
  "Le informazioni su rischio, letteratura e genetica sono divulgative e non sostituiscono la consulenza di un medico o di un genetista.": "Die Informationen zu Risiko, Literatur und Genetik dienen der allgemeinen Aufklärung und ersetzen nicht die Beratung durch eine Ärztin, einen Arzt oder einen Humangenetiker.",
  "Le linee guida raccomandano il test solo dopo una selezione accurata dei candidati e un'adeguata consulenza (Rossi 2019); l'uso dei pannelli multigene è ancora discusso.": "Die Leitlinien empfehlen den Test nur nach sorgfältiger Auswahl der Kandidaten und angemessener Beratung (Rossi 2019); der Einsatz von Multigen-Panels wird noch diskutiert.",
  "Le nuvole sottili non fermano gran parte degli UV: l'indice può restare alto anche con il cielo velato.": "Dünne Wolken halten einen Großteil der UV-Strahlung nicht ab: Der Index kann auch bei dunstigem Himmel hoch bleiben.",
  "Le ore centrali (circa 11-16) sono quelle con l'indice più alto.": "Die Mittagsstunden (etwa 11–16 Uhr) haben den höchsten Index.",
  "Le ricerche partono da questo computer verso PubMed (nessun dato personale viene inviato). I risultati si salvano per 7 giorni.": "Die Suchen gehen von diesem Computer an PubMed (es werden keine persönlichen Daten gesendet). Die Ergebnisse werden 7 Tage gespeichert.",
  "Le ricerche usano le E-utilities pubbliche di PubMed. NCBI chiede, per cortesia, un'email di contatto: è facoltativa e viene inviata solo a PubMed.": "Die Suchen verwenden die öffentlichen E-Utilities von PubMed. Das NCBI bittet höflich um eine Kontakt-E-Mail: Sie ist freiwillig und wird nur an PubMed gesendet.",
  "Le sezioni «scelte per te» usano parole legate al tuo profilo (per esempio fototipo o numero di nei): se preferisci non inviarle, non scansionare quella sezione.": "Die Abschnitte «für Sie ausgewählt» verwenden Begriffe aus Ihrem Profil (zum Beispiel Hauttyp oder Zahl der Muttermale): Wenn Sie diese lieber nicht senden möchten, durchsuchen Sie diesen Abschnitt nicht.",
  "Leachman 2009 e 2017; NCCN": "Leachman 2009 und 2017; NCCN",
  "Leachman 2017; NCCN": "Leachman 2017; NCCN",
  "Leggi l'abstract": "Abstract lesen",
  "Lentigo maligna e melanoma del volto": "Lentigo maligna und Melanom im Gesicht",
  "Letteratura": "Literatur",
  "Letteratura scientifica": "Wissenschaftliche Literatur",
  "Letteratura: PubMed": "Literatur: PubMed",
  "Linea guida": "Leitlinie",
  "Linee guida e criteri per il test genetico": "Leitlinien und Kriterien für den Gentest",
  "Lingua": "Sprache",
  "Lingua dell'interfaccia": "Sprache der Oberfläche",
  "Lingua non supportata.": "Sprache nicht unterstützt.",
  "Lucas RM et al. Are current guidelines for sun protection optimal for health? Photochem Photobiol Sci 2018;17:1956-63 (UV Index e dose di eritema)": "Lucas RM et al. Are current guidelines for sun protection optimal for health? Photochem Photobiol Sci 2018;17:1956-63 (UV-Index und Erythemdosis)",
  "Mai": "Nie",
  "Manca la posizione": "Standort fehlt",
  "Mano destra": "Hand rechts",
  "Mano sinistra": "Hand links",
  "Mappa dei nei": "Muttermal-Karte",
  "Mappa del corpo umano: fronte a sinistra, retro a destra": "Karte des menschlichen Körpers: Vorderseite links, Rückseite rechts",
  "Massimo di oggi": "Tagesmaximum",
  "Melanoma acrale (mani, piedi, unghie): dermoscopia": "Akrales Melanom (Hände, Füße, Nägel): Dermatoskopie",
  "Melanoma dell'occhio (uveale)": "Melanom des Auges (uveal)",
  "Melanoma e immunosoppressione": "Melanom und Immunsuppression",
  "Melanoma ereditario": "Erbliches Melanom",
  "Melanoma ereditario e test genetico": "Erbliches Melanom und Gentest",
  "Melanoma già diagnosticato": "Melanom bereits diagnostiziert",
  "Melanoma nelle pelli scure (spesso acrale)": "Melanom bei dunkler Haut (oft akral)",
  "Melanoma personale e parente di primo grado con tumore del pancreas": "Eigenes Melanom und ein Verwandter ersten Grades mit Bauchspeicheldrüsenkrebs",
  "Melanoma-Detector (VukIG)": "Melanoma-Detector (VukIG)",
  "Melanomi già diagnosticati": "Bereits diagnostizierte Melanome",
  "Melanomi già diagnosticati a me": "Bei mir bereits diagnostizierte Melanome",
  "Melanomi primari indicati: {mel_pers}.": "Angegebene primäre Melanome: {mel_pers}.",
  "Meno di 25": "Weniger als 25",
  "Mesotelioma": "Mesotheliom",
  "Meta-analisi": "Metaanalyse",
  "Metodi in disaccordo": "Methoden uneinig",
  "Metodo 1 - App 1 (Deborah Adedigba)": "Methode 1 - App 1 (Deborah Adedigba)",
  "Metodo 1 disattivato dalle impostazioni.": "Methode 1 in den Einstellungen deaktiviert.",
  "Metodo 2 - SkinSense (servizio online)": "Methode 2 - SkinSense (Online-Dienst)",
  "Metodo 2 non eseguito (disattivato nelle impostazioni): la foto non e' uscita dal PC.": "Methode 2 nicht ausgeführt (in den Einstellungen deaktiviert): Das Foto hat den PC nicht verlassen.",
  "Metodo 4 - vatsal30": "Methode 4 - vatsal30",
  "Metodo 4 disattivato dalle impostazioni.": "Methode 4 in den Einstellungen deaktiviert.",
  "Metodo {n}": "Methode {n}",
  "Metti accanto al neo un righello o una moneta: serve per misurare il diametro.": "Legen Sie ein Lineal oder eine Münze neben das Muttermal: Damit lässt sich der Durchmesser messen.",
  "Moderato": "Mäßig",
  "Modifica data/misura": "Datum/Messung ändern",
  "Modifica foto": "Foto bearbeiten",
  "Modifica i dati nel Profilo": "Angaben im Profil ändern",
  "Modifiche non salvate…": "Nicht gespeicherte Änderungen…",
  "Molte": "Viele",
  "Molte efelidi (lentiggini)": "Viele Sommersprossen (Epheliden)",
  "Molte scottature con vesciche": "Viele Sonnenbrände mit Blasen",
  "Molti nei o nei atipici: sorveglianza": "Viele oder atypische Muttermale: Überwachung",
  "Molto alto": "Sehr hoch",
  "Mostra affiancate": "Nebeneinander anzeigen",
  "Mostra tutto il corpo": "Ganzen Körper anzeigen",
  "NCCN": "NCCN",
  "NCCN Clinical Practice Guidelines in Oncology: Melanoma: Cutaneous (versione corrente; il testo completo richiede una registrazione gratuita)": "NCCN Clinical Practice Guidelines in Oncology: Melanoma: Cutaneous (aktuelle Version; der Volltext erfordert eine kostenlose Registrierung)",
  "Nei archiviati ({n})": "Archivierte Muttermale ({n})",
  "Nei atipici": "Atypische Muttermale",
  "Nei atipici (displastici)": "Atypische (dysplastische) Muttermale",
  "Nei grandi, irregolari, di più colori: vanno seguiti nel tempo.": "Große, unregelmäßige, mehrfarbige Muttermale: Sie sollten im Zeitverlauf beobachtet werden.",
  "Neo archiviato. Lo trovi in fondo all'elenco.": "Muttermal archiviert. Sie finden es am Ende der Liste.",
  "Neo con foto": "Muttermal mit Fotos",
  "Neo eliminato.": "Muttermal gelöscht.",
  "Neo non trovato.": "Muttermal nicht gefunden.",
  "Neo salvato. Ora aggiungi la prima foto: sarà la tua \"foto storica\".": "Muttermal gespeichert. Fügen Sie jetzt das erste Foto hinzu: Es wird Ihr „Ausgangsfoto“.",
  "Neo {n}": "Muttermal {n}",
  "NeoTracker chiuso": "NeoTracker beendet",
  "NeoTracker non risponde": "NeoTracker antwortet nicht",
  "NeoTracker non è un dispositivo medico e non fa diagnosi.": "NeoTracker ist kein Medizinprodukt und stellt keine Diagnosen.",
  "NeoTracker non è un servizio di consulenza genetica. Per una valutazione personale rivolgiti al dermatologo o a un centro di genetica oncologica.": "NeoTracker ist kein genetischer Beratungsdienst. Für eine persönliche Einschätzung wenden Sie sich an Ihre Hautärztin bzw. Ihren Hautarzt oder an ein onkogenetisches Zentrum.",
  "NeoTracker non è uno strumento medico e non fa diagnosi. Per qualsiasi neo che cambia, sanguina, prude o ti preoccupa, rivolgiti a un dermatologo.": "NeoTracker ist kein medizinisches Werkzeug und stellt keine Diagnosen. Bei jedem Muttermal, das sich verändert, blutet, juckt oder Ihnen Sorgen macht, wenden Sie sich an eine Hautärztin oder einen Hautarzt.",
  "NeoTracker è chiuso": "NeoTracker ist beendet",
  "Neri": "Schwarz",
  "Nessun allarme dai modelli": "Kein Alarm durch die Modelle",
  "Nessun articolo trovato.": "Keine Artikel gefunden.",
  "Nessun metodo ha prodotto un risultato: controlla i motivi indicati sotto.": "Keine Methode hat ein Ergebnis geliefert: Prüfen Sie die unten genannten Gründe.",
  "Nessun neo ancora": "Noch keine Muttermale",
  "Nessun risultato": "Kein Ergebnis",
  "Nessuna": "Keine",
  "Nessuna città trovata con questo nome.": "Keine Stadt mit diesem Namen gefunden.",
  "Nessuna foto ancora registrata.": "Noch kein Foto erfasst.",
  "Nessuna foto: aggiungi la prima": "Keine Fotos: Fügen Sie das erste hinzu",
  "Nessuna immagine impostata.": "Kein Bild festgelegt.",
  "Nessuna protezione particolare per le attività normali; occhiali da sole nelle giornate luminose.": "Kein besonderer Schutz für normale Aktivitäten nötig; an hellen Tagen eine Sonnenbrille.",
  "Nessuno dei metodi che hanno risposto segnala la lesione come sospetta. Questo NON esclude un melanoma: gli strumenti non sono validati clinicamente e sbagliano anche in questa direzione. Se il neo è asimmetrico, ha bordi irregolari, colori diversi, è più grande di 6 mm o è cambiato nel tempo, la visita resta necessaria.": "Keine der Methoden, die geantwortet haben, meldet die Läsion als verdächtig. Das schließt ein Melanom NICHT aus: Die Werkzeuge sind klinisch nicht validiert und irren sich auch in dieser Richtung. Wenn das Muttermal asymmetrisch ist, unregelmäßige Ränder oder mehrere Farben hat, größer als 6 mm ist oder sich verändert hat, ist ein Arztbesuch weiterhin nötig.",
  "No": "Nein",
  "Nome": "Name",
  "Nome del neo": "Name des Muttermals",
  "Nome della città": "Name der Stadt",
  "Nome o soprannome": "Name oder Spitzname",
  "Non ancora scansionata.": "Noch nicht durchsucht.",
  "Non ancora scansionato": "Noch nicht durchsucht",
  "Non cambiano il risultato delle reti neurali, che guardano solo i pixel della foto. Servono a: (1) dare un contesto al rischio, (2) scegliere la letteratura scientifica adatta a te, (3) verificare i criteri per la consulenza genetica, (4) calcolare quanto tempo puoi stare al sole prima di scottarti. Tutto resta sul tuo computer.": "Sie verändern das Ergebnis der neuronalen Netze nicht, die nur die Pixel des Fotos betrachten. Sie dienen dazu, (1) das Risiko einzuordnen, (2) die für Sie passende wissenschaftliche Literatur auszuwählen, (3) die Kriterien für eine genetische Beratung zu prüfen und (4) zu berechnen, wie lange Sie in der Sonne bleiben können, bevor Sie einen Sonnenbrand bekommen. Alles bleibt auf Ihrem Computer.",
  "Non ci sono nei da stampare.": "Es gibt keine Muttermale zum Drucken.",
  "Non consentito.": "Nicht erlaubt.",
  "Non indicato": "Nicht angegeben",
  "Non lo so: lascia vuoto, puoi tornare più tardi.": "Ich weiß es nicht: Lassen Sie es leer, Sie können später zurückkommen.",
  "Non riesci? Stima dall'indirizzo internet": "Es klappt nicht? Aus der Internetadresse schätzen",
  "Non riesco a contattare NeoTracker. Il programma potrebbe essere stato chiuso: riaprilo dall'icona sul Desktop.": "NeoTracker ist nicht erreichbar. Möglicherweise wurde das Programm beendet: Öffnen Sie es über das Symbol auf dem Desktop erneut.",
  "Non riesco a leggere questa immagine. Prova con un JPG o un PNG.": "Dieses Bild kann nicht gelesen werden. Versuchen Sie es mit einer JPG- oder PNG-Datei.",
  "Non riesco a ridurre questa immagine.": "Dieses Bild kann nicht verkleinert werden.",
  "Non so": "Weiß nicht",
  "Non soddisfatto": "Nicht erfüllt",
  "Non trovo melanoma_batch.py: deve stare nella stessa cartella di neotracker.py (oppure in {CARTELLA_REPO}).": "melanoma_batch.py wurde nicht gefunden: Die Datei muss im selben Ordner wie neotracker.py liegen (oder in {CARTELLA_REPO}).",
  "Nonni, zii, nipoti (2° grado).": "Großeltern, Onkel und Tanten, Neffen und Nichten (2. Grad).",
  "Note": "Notizen",
  "Note sul neo…": "Notizen zum Muttermal…",
  "Note:": "Notizen:",
  "Nuca e collo": "Nacken und Hals",
  "Nulla viene inviato online, tranne le richieste che attivi tu (meteo UV, letteratura PubMed, SkinSense).": "Es wird nichts online gesendet, außer den Anfragen, die Sie aktivieren (UV-Wetter, PubMed-Literatur, SkinSense).",
  "Numero di nei": "Anzahl der Muttermale",
  "Nuovo neo": "Neues Muttermal",
  "Nuovo utente": "Neuer Benutzer",
  "OMS/OMM/UNEP/ICNIRP - Global Solar UV Index: A Practical Guide (2002)": "WHO/WMO/UNEP/ICNIRP - Global Solar UV Index: A Practical Guide (2002)",
  "Occhi": "Augen",
  "Occhi chiari": "Helle Augen",
  "Oggi i raggi UV sono bassi": "Die UV-Strahlung ist heute niedrig",
  "Oggi i raggi UV sono dannosi per pelle non protetta": "Die UV-Strahlung ist heute für ungeschützte Haut schädlich",
  "Oggi i raggi UV sono molto dannosi": "Die UV-Strahlung ist heute sehr schädlich",
  "One Call {n}: {t}": "One Call {n}: {t}",
  "Open-Meteo (predefinita)": "Open-Meteo (Standard)",
  "OpenWeather ha rifiutato la chiave (401): controlla che sia corretta e che sul tuo account sia attivo l'abbonamento 'One Call API' (pagamento a chiamata, 1.000 chiamate al giorno gratuite). Dopo l'iscrizione la chiave può impiegare qualche minuto ad attivarsi.": "OpenWeather hat den Schlüssel abgelehnt (401): Prüfen Sie, ob er korrekt ist und ob in Ihrem Konto der Tarif „One Call API“ (Bezahlung pro Abruf, 1.000 kostenlose Abrufe pro Tag) aktiv ist. Nach dem Abschluss kann es einige Minuten dauern, bis der Schlüssel aktiv ist.",
  "OpenWeather non disponibile ({e}). Mostro i dati di Open-Meteo.": "OpenWeather nicht verfügbar ({e}). Es werden die Daten von Open-Meteo angezeigt.",
  "OpenWeather: limite di chiamate raggiunto (429).": "OpenWeather: Abruflimit erreicht (429).",
  "Operazione non consentita su questo indirizzo.": "Vorgang für diese Adresse nicht erlaubt.",
  "Orecchio destro": "Ohr rechts",
  "Orecchio sinistro": "Ohr links",
  "Origine non ammessa.": "Herkunft nicht zulässig.",
  "Pagina non trovata.": "Seite nicht gefunden.",
  "Parente di primo grado con melanoma": "Verwandter ersten Grades mit Melanom",
  "Parenti con astrocitoma (tumore del cervello)": "Verwandte mit Astrozytom (Hirntumor)",
  "Parenti con carcinoma del rene": "Verwandte mit Nierenzellkarzinom",
  "Parenti con melanoma dell'occhio (uveale)": "Verwandte mit Melanom des Auges (uveal)",
  "Parenti con mesotelioma": "Verwandte mit Mesotheliom",
  "Parenti con tumore del pancreas (in tutto)": "Verwandte mit Bauchspeicheldrüsenkrebs (insgesamt)",
  "Parenti di 1° grado con melanoma": "Verwandte 1. Grades mit Melanom",
  "Passa il puntatore sul corpo per vedere la zona": "Bewegen Sie den Zeiger über den Körper, um den Bereich zu sehen",
  "Pelle che scotta facilmente e si abbronza poco.": "Haut, die leicht verbrennt und kaum bräunt.",
  "Pelle chiara-olivastra. Scotta a volte, si abbronza gradualmente.": "Hell-olivfarbene Haut. Verbrennt manchmal, bräunt allmählich.",
  "Pelle chiara. Scotta facilmente, si abbronza poco.": "Helle Haut. Verbrennt leicht, bräunt wenig.",
  "Pelle molto chiara. Scotta sempre, non si abbronza mai (spesso capelli rossi, lentiggini).": "Sehr helle Haut. Verbrennt immer, bräunt nie (oft rote Haare, Sommersprossen).",
  "Pelle molto scura. Non scotta.": "Sehr dunkle Haut. Verbrennt nicht.",
  "Pelle olivastra. Scotta poco, si abbronza facilmente.": "Olivfarbene Haut. Verbrennt kaum, bräunt leicht.",
  "Pelle scura. Scotta raramente.": "Dunkle Haut. Verbrennt selten.",
  "Per chiudere NeoTracker basta chiudere questa finestra con la X in alto a destra: il programma si spegne da solo.": "Um NeoTracker zu beenden, schließen Sie einfach dieses Fenster mit dem X oben rechts: Das Programm beendet sich von selbst.",
  "Per confermare scrivi:": "Zur Bestätigung eingeben:",
  "Per eliminare scrivi il nome esatto dell'utente nella conferma.": "Zum Löschen geben Sie in der Bestätigung den genauen Namen des Benutzers ein.",
  "Per le linee guida NCCN, in un melanoma invasivo con un parente di primo grado con tumore del pancreas è raccomandato un pannello multigene che includa CDKN2A.": "Nach den NCCN-Leitlinien wird bei einem invasiven Melanom mit einem Verwandten ersten Grades mit Bauchspeicheldrüsenkrebs ein Multigen-Panel empfohlen, das CDKN2A einschließt.",
  "Per stimare la città il programma contatta il servizio gratuito ipwho.is, che vede il tuo indirizzo internet. La precisione è quella della città (a volte sbaglia). Procedo?": "Um die Stadt zu schätzen, kontaktiert das Programm den kostenlosen Dienst ipwho.is, der Ihre Internetadresse sieht. Die Genauigkeit entspricht der Stadtebene (manchmal liegt er falsch). Fortfahren?",
  "Per vedere quanto sole ti scotta, indica il fototipo nel": "Um zu sehen, wie viel Sonne Sie verbrennt, geben Sie Ihren Hauttyp im Bereich ein",
  "Permesso negato. Puoi cercare la città per nome oppure usare la stima da indirizzo internet.": "Berechtigung verweigert. Sie können die Stadt nach Namen suchen oder die Schätzung über die Internetadresse verwenden.",
  "Piede destro": "Fuß rechts",
  "Piede sinistro": "Fuß links",
  "Pillow non installato: le anteprime useranno le foto originali (installa con «py -m pip install pillow»).": "Pillow ist nicht installiert: Die Vorschauen verwenden die Originalfotos (Installation mit «py -m pip install pillow»).",
  "Più colori nello stesso neo (marrone, nero, rosso, blu, bianco).": "Mehrere Farben im selben Muttermal (braun, schwarz, rot, blau, weiß).",
  "Più di 6 mm (ma esistono melanomi più piccoli).": "Mehr als 6 mm (es gibt aber auch kleinere Melanome).",
  "Più tumori dello spettro BAP1 (melanoma uveale, mesotelioma, carcinoma renale, melanoma cutaneo)": "Mehrere Tumoren des BAP1-Spektrums (uveales Melanom, Mesotheliom, Nierenzellkarzinom, kutanes Melanom)",
  "Poche": "Wenige",
  "Polpaccio destro": "Wade rechts",
  "Polpaccio sinistro": "Wade links",
  "Posizione": "Standort",
  "Posizione aggiornata.": "Standort aktualisiert.",
  "Posizione aggiornata: {regione}.": "Standort aktualisiert: {regione}.",
  "Posizione fuori dalla mappa.": "Standort außerhalb der Karte.",
  "Posizione impostata": "Standort festgelegt",
  "Posizione non impostata": "Standort nicht festgelegt",
  "Posizione non impostata: scegli una città o usa 'Rileva la mia posizione'.": "Standort nicht festgelegt: Wählen Sie eine Stadt oder verwenden Sie „Meinen Standort ermitteln“.",
  "Posizione non valida.": "Ungültiger Standort.",
  "Posizione salvata: {nome}": "Standort gespeichert: {nome}",
  "Posizione stimata": "Geschätzter Standort",
  "Precauzioni extra: evita il sole nelle ore centrali, cerca l'ombra, copri la pelle, SPF 30+. La pelle non protetta si scotta in fretta.": "Zusätzliche Vorsichtsmaßnahmen: Meiden Sie die Sonne zur Mittagszeit, suchen Sie Schatten, bedecken Sie die Haut, LSF 30+. Ungeschützte Haut verbrennt schnell.",
  "Preferisco non dirlo": "Möchte ich nicht angeben",
  "Premi": "Drücken Sie",
  "Preparo la scheda…": "Blatt wird vorbereitet…",
  "Prima": "Vorher",
  "Prima di cominciare": "Bevor Sie beginnen",
  "Prima salva una chiave OpenWeather.": "Speichern Sie zuerst einen OpenWeather-Schlüssel.",
  "Principale gene di predisposizione ad alta penetranza. Varianti germinali nel 20-40% delle famiglie con melanoma; associato anche a tumore del pancreas, melanomi multipli ed esordio precoce.": "Wichtigstes Prädispositionsgen mit hoher Penetranz. Keimbahnvarianten in 20–40 % der Familien mit Melanom; außerdem verbunden mit Bauchspeicheldrüsenkrebs, multiplen Melanomen und frühem Beginn.",
  "Profilo": "Profil",
  "Profilo da completare": "Profil noch zu vervollständigen",
  "Profilo di {nome}": "Profil von {nome}",
  "Profilo non compilato.": "Profil nicht ausgefüllt.",
  "Profilo non valido.": "Ungültiges Profil.",
  "Programma di analisi (melanoma_batch.py) non trovato: le foto si salvano ma non si possono analizzare.": "Analyseprogramm (melanoma_batch.py) nicht gefunden: Die Fotos werden gespeichert, können aber nicht analysiert werden.",
  "Programma di analisi:": "Analyseprogramm:",
  "Promemoria ABCDE": "ABCDE-Merkhilfe",
  "Promemoria ABCDE per riconoscere un neo": "ABCDE-Merkhilfe zum Erkennen eines Muttermals",
  "Prossime {n} ore": "Nächste {n} Stunden",
  "Protezione consigliata: ombra nelle ore centrali, cappello, occhiali e crema solare.": "Schutz empfohlen: Schatten zur Mittagszeit, Hut, Sonnenbrille und Sonnencreme.",
  "Protezione necessaria: riduci l'esposizione tra le 10 e le 16, crema solare SPF 30+, cappello e occhiali.": "Schutz erforderlich: Verringern Sie die Sonnenexposition zwischen 10 und 16 Uhr, Sonnencreme LSF 30+, Hut und Sonnenbrille.",
  "Protezione non necessaria per le attività normali (attenzione a neve, acqua, quota).": "Für normale Aktivitäten ist kein Schutz nötig (Vorsicht bei Schnee, Wasser, Höhe).",
  "Prova la chiave": "Schlüssel testen",
  "Provo la chiave…": "Schlüssel wird getestet…",
  "PubMed ha risposto con errore {code}": "PubMed hat mit Fehler {code} geantwortet",
  "PubMed non raggiungibile (controlla la connessione internet)": "PubMed nicht erreichbar (prüfen Sie die Internetverbindung)",
  "PubMed non è raggiungibile: mostro l'ultima ricerca salvata il {data}.": "PubMed ist nicht erreichbar: Es wird die letzte gespeicherte Suche vom {data} angezeigt.",
  "PubMed {pmid} · abstract non disponibile": "PubMed {pmid} · Abstract nicht verfügbar",
  "PubMed è un servizio della National Library of Medicine. Gli abstract sono mostrati per consultazione personale, in inglese; per il testo completo apri l'articolo sul sito della rivista.": "PubMed ist ein Dienst der National Library of Medicine. Die Abstracts werden zur persönlichen Information auf Englisch angezeigt; für den Volltext öffnen Sie den Artikel auf der Website der Zeitschrift.",
  "Puoi chiudere questa finestra. Per riaprirlo usa l'icona «NeoTracker» sul Desktop.": "Sie können dieses Fenster schließen. Zum erneuten Öffnen verwenden Sie das Symbol «NeoTracker» auf dem Desktop.",
  "Puoi continuare a usare l'app. Se chiudi la finestra l'analisi non va persa: il programma finisce il lavoro e poi si spegne da solo.": "Sie können die App weiter benutzen. Wenn Sie das Fenster schließen, geht die Analyse nicht verloren: Das Programm beendet die Arbeit und schaltet sich dann von selbst ab.",
  "Puoi usare una tua foto, un disegno o un'icona. L'immagine viene ritagliata a quadrato e ridotta, resta solo su questo computer e non viene mai usata per l'analisi dei nei.": "Sie können ein eigenes Foto, eine Zeichnung oder ein Symbol verwenden. Das Bild wird quadratisch zugeschnitten und verkleinert, bleibt nur auf diesem Computer und wird nie für die Analyse von Muttermalen verwendet.",
  "Qualche volta": "Manchmal",
  "Qualcosa non ha funzionato": "Etwas ist schiefgelaufen",
  "Quando l'hai notato, se prude, se è cambiato…": "Wann es Ihnen aufgefallen ist, ob es juckt, ob es sich verändert hat…",
  "Quanti nei hai sul corpo, circa?": "Wie viele Muttermale haben Sie ungefähr am Körper?",
  "Quanto sono affidabili app e intelligenza artificiale": "Wie zuverlässig sind Apps und künstliche Intelligenz",
  "Questa foto non è ancora stata analizzata. L'analisi confronta più metodi sulla stessa immagine e ti dice cosa ha risposto ciascuno.": "Dieses Foto wurde noch nicht analysiert. Die Analyse vergleicht mehrere Methoden am selben Bild und zeigt Ihnen, was jede geantwortet hat.",
  "Questa scheda raccoglie dati inseriti dalla persona e foto da lei scattate. I risultati dell'analisi automatica sono sperimentali, non sono una diagnosi e non sostituiscono la visita dermatologica o la dermoscopia.": "Dieses Blatt enthält Angaben der Person und von ihr aufgenommene Fotos. Die Ergebnisse der automatischen Analyse sind experimentell, keine Diagnose und ersetzen weder den Hautarztbesuch noch die Dermatoskopie.",
  "Questo browser non offre la geolocalizzazione: cerca la città per nome.": "Dieser Browser bietet keine Standortbestimmung: Suchen Sie die Stadt nach Namen.",
  "Questo metodo prevede l'invio dei pixel della foto (non dei metadati) a un server esterno.": "Bei dieser Methode werden die Pixel des Fotos (nicht die Metadaten) an einen externen Server gesendet.",
  "Questo programma ti aiuta a tenere traccia dei tuoi nei nel tempo: li segni su una mappa del corpo, ne conservi le foto con la data e li fai analizzare da più metodi. Inizia creando il tuo utente.": "Dieses Programm hilft Ihnen, Ihre Muttermale über die Zeit zu verfolgen: Sie markieren sie auf einer Körperkarte, bewahren ihre Fotos mit Datum auf und lassen sie von mehreren Methoden analysieren. Beginnen Sie damit, Ihren Benutzer anzulegen.",
  "Questo rapporto NON è una diagnosi. I programmi usati sono prototipi di ricerca, non dispositivi medici.": "Dieser Bericht ist KEINE Diagnose. Die verwendeten Programme sind Forschungsprototypen, keine Medizinprodukte.",
  "RETRO": "RÜCKSEITE",
  "Rapporto completo (testo)": "Vollständiger Bericht (Text)",
  "Rapporto completo (testo, in italiano)": "Vollständiger Bericht (Text, auf Italienisch)",
  "Raro": "Selten",
  "Regione lombare destra": "Lendenbereich rechts",
  "Regione lombare sinistra": "Lendenbereich links",
  "Regione scapolare destra": "Schulterblattbereich rechts",
  "Regione scapolare sinistra": "Schulterblattbereich links",
  "Retro": "Rückseite",
  "Revisione": "Übersichtsarbeit",
  "Revisione sistematica": "Systematische Übersichtsarbeit",
  "Revisioni sul melanoma familiare (CDKN2A, CDK4)": "Übersichtsarbeiten zum familiären Melanom (CDKN2A, CDK4)",
  "Rianalizza": "Erneut analysieren",
  "Richiesta non autorizzata.": "Nicht autorisierte Anfrage.",
  "Richiesta troppo grande.": "Anfrage zu groß.",
  "Riconoscere un neo sospetto": "Ein verdächtiges Muttermal erkennen",
  "Riduci": "Verkleinern",
  "Rifà la ricerca ignorando i risultati salvati": "Suche wiederholen und gespeicherte Ergebnisse ignorieren",
  "Rileva la mia posizione": "Meinen Standort ermitteln",
  "Rimuovere la chiave?": "Schlüssel entfernen?",
  "Rimuovi": "Entfernen",
  "Rinomina": "Umbenennen",
  "Rinomina utente": "Benutzer umbenennen",
  "Ripristina": "Wiederherstellen",
  "Riprova": "Erneut versuchen",
  "Rischio associato": "Assoziiertes Risiko",
  "Rossi": "Rot",
  "Rotella = zoom · trascina = sposta · doppio clic = ingrandisci": "Mausrad = Zoom · Ziehen = verschieben · Doppelklick = vergrößern",
  "Ruolo e letteratura": "Rolle und Literatur",
  "S": "L",
  "Salva": "Speichern",
  "Salva foto": "Foto speichern",
  "Salva neo": "Muttermal speichern",
  "Salvataggio…": "Wird gespeichert…",
  "Salvato ✓": "Gespeichert ✓",
  "Scansiona la letteratura": "Literatur durchsuchen",
  "Scansiona la letteratura sui geni": "Literatur zu den Genen durchsuchen",
  "Scansione completata.": "Suche abgeschlossen.",
  "Scarico l'indice UV…": "UV-Index wird abgerufen…",
  "Scatta sempre dalla stessa angolazione e salva l'originale, senza filtri.": "Fotografieren Sie immer aus demselben Winkel und bewahren Sie das Original ohne Filter auf.",
  "Scegli dove ti trovi per vedere l'indice UV di oggi.": "Wählen Sie Ihren Standort, um den heutigen UV-Index zu sehen.",
  "Scegli il tuo profilo: ogni persona ha la propria mappa dei nei, le proprie foto e i propri dati.": "Wählen Sie Ihr Profil: Jede Person hat ihre eigene Muttermal-Karte, eigene Fotos und eigene Daten.",
  "Scegli immagine…": "Bild auswählen…",
  "Scegli la città qui sopra: poi vedrai l'indice UV di oggi, ora per ora.": "Wählen Sie oben die Stadt: Dann sehen Sie den heutigen UV-Index Stunde für Stunde.",
  "Scegli un file immagine (JPG, PNG, WEBP o BMP).": "Wählen Sie eine Bilddatei (JPG, PNG, WEBP oder BMP).",
  "Scegli un utente e indica il suo fototipo per vedere quanti minuti servono per scottarsi.": "Wählen Sie einen Benutzer und geben Sie seinen Hauttyp an, um zu sehen, nach wie vielen Minuten ein Sonnenbrand entsteht.",
  "Scegli un'immagine personale": "Eigenes Bild auswählen",
  "Scegli utente": "Benutzer auswählen",
  "Scelti per te (in base a profilo e sede dei nei)": "Für Sie ausgewählt (nach Profil und Lage der Muttermale)",
  "Scheda dei nei – {nome}": "Muttermal-Blatt – {nome}",
  "Scheda per il dermatologo": "Blatt für die Hautärztin / den Hautarzt",
  "Schiena (zona media) destra": "Rücken (mittlerer Bereich) rechts",
  "Schiena (zona media) sinistra": "Rücken (mittlerer Bereich) links",
  "Scottature": "Sonnenbrände",
  "Scottature con vesciche (soprattutto da bambino o ragazzo)": "Sonnenbrände mit Blasen (vor allem als Kind oder Jugendlicher)",
  "Scrivi almeno 3 caratteri.": "Geben Sie mindestens 3 Zeichen ein.",
  "Scrivi un nome.": "Geben Sie einen Namen ein.",
  "Scuri": "Dunkel",
  "Se hai dubbi sul fototipo, pensa a come reagisce la tua pelle alla prima esposizione intensa al sole in estate, senza protezione.": "Wenn Sie sich beim Hauttyp unsicher sind, denken Sie daran, wie Ihre Haut bei der ersten intensiven Sonnenexposition im Sommer ohne Schutz reagiert.",
  "Se i metodi sono in disaccordo è normale: significa solo che nessuno di loro è affidabile da solo.": "Dass die Methoden uneinig sind, ist normal: Es bedeutet nur, dass keine von ihnen allein zuverlässig ist.",
  "Se inserisci dati o foto di altre persone, assicurati di avere il loro consenso.": "Wenn Sie Daten oder Fotos anderer Personen eingeben, stellen Sie sicher, dass Sie deren Einwilligung haben.",
  "Se sta ancora analizzando una foto, finisce prima l'analisi e poi si spegne. Il pulsante qui sotto fa la stessa cosa.": "Wenn gerade ein Foto analysiert wird, schließt es zuerst die Analyse ab und beendet sich dann. Die Schaltfläche unten tut dasselbe.",
  "Sede": "Stelle",
  "Sede (modificabile)": "Stelle (änderbar)",
  "Senza Pillow l'immagine deve essere un JPG/PNG sotto i 400 KB (la pagina la riduce da sola: riprova con la funzione 'Scegli immagine').": "Ohne Pillow muss das Bild eine JPG/PNG-Datei unter 400 KB sein (die Seite verkleinert es selbst: Versuchen Sie es erneut mit der Funktion „Bild auswählen“).",
  "Servono ombra, abiti, cappello e crema solare nelle ore centrali.": "Zur Mittagszeit sind Schatten, Kleidung, Hut und Sonnencreme nötig.",
  "Sesso": "Geschlecht",
  "Sezione sconosciuta.": "Unbekannter Abschnitt.",
  "Sezione {n} di {tot}…": "Abschnitt {n} von {tot}…",
  "Sezioni": "Abschnitte",
  "Sindrome di predisposizione ai tumori BAP1: melanoma uveale, mesotelioma, carcinoma renale, melanoma cutaneo e nevi melanocitari atipici.": "BAP1-Tumor-Prädispositionssyndrom: uveales Melanom, Mesotheliom, Nierenzellkarzinom, kutanes Melanom und atypische melanozytäre Nävi.",
  "Sindromico": "Syndromal",
  "SkinSense (servizio online)": "SkinSense (Online-Dienst)",
  "SkinSense abilitato.": "SkinSense aktiviert.",
  "SkinSense disattivato.": "SkinSense deaktiviert.",
  "SkinSense è attivo: la foto (senza metadati) verrà inviata a un servizio online.": "SkinSense ist aktiv: Das Foto (ohne Metadaten) wird an einen Online-Dienst gesendet.",
  "SkinSense è un servizio online di terzi: le foto dei tuoi nei verrebbero inviate via internet a un server che non controlliamo. Le foto sono dati sulla tua salute. Vuoi abilitarlo?": "SkinSense ist ein Online-Dienst eines Dritten: Die Fotos Ihrer Muttermale würden über das Internet an einen Server gesendet, den wir nicht kontrollieren. Die Fotos sind Gesundheitsdaten. Möchten Sie ihn aktivieren?",
  "Soddisfatto": "Erfüllt",
  "Soglie e colori della scala internazionale dell'OMS. Fonti:": "Schwellenwerte und Farben der internationalen WHO-Skala. Quellen:",
  "Sono immunosoppresso/a (trapianto o terapie che abbassano le difese)": "Ich bin immunsupprimiert (Transplantation oder Therapien, die die Abwehr senken)",
  "Sono misure inserite da te: valgono se prese sempre allo stesso modo. Un neo che cresce o cambia è un buon motivo per farlo vedere al dermatologo; la linea a 6 mm è solo il riferimento classico dei criteri ABCDE.": "Dies sind von Ihnen eingegebene Messwerte: Sie sind aussagekräftig, wenn sie immer auf dieselbe Weise ermittelt werden. Ein Muttermal, das wächst oder sich verändert, ist ein guter Grund, es der Hautärztin oder dem Hautarzt zu zeigen; die 6-mm-Linie ist nur die klassische Referenz der ABCDE-Kriterien.",
  "Sono mostrate {n} foto su {tot}.": "Es werden {n} von {tot} Fotos angezeigt.",
  "Sono presenti alcuni fattori di rischio: protezione solare accurata e autoesame regolare; un controllo dermatologico di base è una buona abitudine.": "Es liegen einige Risikofaktoren vor: sorgfältiger Sonnenschutz und regelmäßige Selbstuntersuchung; eine dermatologische Basiskontrolle ist eine gute Gewohnheit.",
  "Sono presenti fattori di rischio rilevanti: è consigliato un controllo dermatologico periodico (la frequenza la decide il dermatologo) e l'autoesame regolare della pelle.": "Es liegen relevante Risikofaktoren vor: Empfohlen werden regelmäßige dermatologische Kontrollen (die Häufigkeit legt die Hautärztin oder der Hautarzt fest) und eine regelmäßige Selbstuntersuchung der Haut.",
  "Soprattutto in infanzia e adolescenza.": "Vor allem in Kindheit und Jugend.",
  "Sovrapponi con cursore": "Mit Regler überlagern",
  "Spalla destra": "Schulter rechts",
  "Spalla sinistra": "Schulter links",
  "Spento per impostazione predefinita: con gli altri metodi la foto non lascia mai questo computer.": "Standardmäßig ausgeschaltet: Bei den anderen Methoden verlässt das Foto diesen Computer nie.",
  "Spesso": "Oft",
  "Stampa la scheda di questo neo": "Blatt für dieses Muttermal drucken",
  "Stampa una scheda con tutti i nei": "Blatt mit allen Muttermalen drucken",
  "Stampata il {data} con NeoTracker": "Gedruckt am {data} mit NeoTracker",
  "Stato dell'installazione": "Installationsstatus",
  "Stessa luce (luce del giorno, senza flash) e stessa distanza ogni volta, circa 10-15 cm.": "Jedes Mal dasselbe Licht (Tageslicht, ohne Blitz) und derselbe Abstand, etwa 10–15 cm.",
  "Stima dall'indirizzo internet": "Schätzung über die Internetadresse",
  "Storia familiare": "Familiengeschichte",
  "Storia personale": "Persönliche Vorgeschichte",
  "Storico fotografico": "Fotoverlauf",
  "Storico fotografico ({n})": "Fotoverlauf ({n})",
  "Studi più pertinenti": "Relevanteste Studien",
  "Studi più recenti sui geni di predisposizione": "Neueste Studien zu Prädispositionsgenen",
  "Studio clinico": "Klinische Studie",
  "Studio osservazionale": "Beobachtungsstudie",
  "Studio randomizzato": "Randomisierte Studie",
  "Sì": "Ja",
  "Sì, abilita": "Ja, aktivieren",
  "Sì, negativo": "Ja, negativ",
  "Sì, non informativo": "Ja, nicht informativ",
  "Sì, positivo": "Ja, positiv",
  "Sì, stima la città": "Ja, Stadt schätzen",
  "Telomerasi: varianti del promotore descritte in famiglie con melanoma.": "Telomerase: Promotorvarianten, die in Familien mit Melanom beschrieben wurden.",
  "Test genetico": "Gentest",
  "Test genetico già eseguito": "Gentest bereits durchgeführt",
  "Tipo": "Typ",
  "Tipo di foto": "Fototyp",
  "Tipo {n}": "Typ {n}",
  "Torace destro": "Brustkorb rechts",
  "Torace sinistro": "Brustkorb links",
  "Tra le due foto sono passati {n} giorni.": "Zwischen den beiden Fotos liegen {n} Tage.",
  "Tra le due foto è passato {n} giorno.": "Zwischen den beiden Fotos liegt {n} Tag.",
  "Trascina il pallino sulla mappa per correggere la posizione; ingrandisci con la rotella per la massima precisione.": "Ziehen Sie den Punkt auf der Karte, um die Position zu korrigieren; zoomen Sie mit dem Mausrad für maximale Genauigkeit.",
  "Trascina il pallino sulla mappa per spostarlo.": "Ziehen Sie den Punkt auf der Karte, um ihn zu verschieben.",
  "Trascina qui una foto oppure clicca per sceglierla": "Ziehen Sie ein Foto hierher oder klicken Sie, um eines auszuwählen",
  "Troppi collegamenti aperti.": "Zu viele offene Verbindungen.",
  "Tumore del pancreas": "Bauchspeicheldrüsenkrebs",
  "Tumori dello spettro BAP1 indicati: {bap1_spettro}. Criterio semplificato: il genetista usa criteri più completi.": "Angegebene Tumoren des BAP1-Spektrums: {bap1_spettro}. Vereinfachtes Kriterium: Der Humangenetiker verwendet umfassendere Kriterien.",
  "Tutti i dati restano su questo computer, nella cartella:": "Alle Daten bleiben auf diesem Computer, im Ordner:",
  "UV moderati: serve protezione nelle ore centrali": "Mäßige UV-Strahlung: Zur Mittagszeit ist Schutz nötig",
  "Ultima analisi automatica ({data}): {esito}. Strumento di ricerca, non diagnostico.": "Letzte automatische Analyse ({data}): {esito}. Forschungswerkzeug, nicht diagnostisch.",
  "Un medico ti ha detto che hai nei atipici (displastici)?": "Hat Ihnen ein Arzt gesagt, dass Sie atypische (dysplastische) Muttermale haben?",
  "Un neo che cambia (forma, bordi, colore, dimensioni), sanguina, prude o ti preoccupa va mostrato a un dermatologo, qualunque cosa dica l'app. Il controllo periodico dal dermatologo resta insostituibile.": "Ein Muttermal, das sich verändert (Form, Rand, Farbe, Größe), blutet, juckt oder Ihnen Sorgen macht, gehört zur Hautärztin oder zum Hautarzt – ganz gleich, was die App sagt. Die regelmäßige Kontrolle beim Hautarzt bleibt unersetzlich.",
  "Un risultato positivo indica un rischio più alto, non la certezza di ammalarsi; un risultato negativo non azzera il rischio (molte famiglie non hanno una variante identificabile).": "Ein positives Ergebnis weist auf ein höheres Risiko hin, nicht auf die Gewissheit zu erkranken; ein negatives Ergebnis hebt das Risiko nicht auf (viele Familien haben keine nachweisbare Variante).",
  "Una stima va bene.": "Eine Schätzung genügt.",
  "Uomo": "Mann",
  "Usa anche SkinSense (servizio online)": "SkinSense (Online-Dienst) ebenfalls verwenden",
  "Usa la data scritta nella foto, se c'è": "Das im Foto gespeicherte Datum verwenden, falls vorhanden",
  "Uso di lampade o lettini abbronzanti": "Nutzung von Bräunungslampen oder Sonnenbänken",
  "Utente creato. Compila il profilo: serve a contestualizzare i risultati.": "Benutzer angelegt. Füllen Sie das Profil aus: Es dient dazu, die Ergebnisse einzuordnen.",
  "Utente eliminato.": "Benutzer gelöscht.",
  "Utente non trovato.": "Benutzer nicht gefunden.",
  "Vai alla sezione Genetica": "Zum Bereich Genetik",
  "Varianti comuni legate a capelli rossi e pelle chiara: aumentano il rischio di melanoma in modo moderato. Non è un test di routine: l'interpretazione è specialistica.": "Häufige Varianten, die mit roten Haaren und heller Haut zusammenhängen: Sie erhöhen das Melanomrisiko mäßig. Kein Routinetest: Die Interpretation ist Sache von Fachleuten.",
  "Varianti rare concentrate nel codone 24: il quadro familiare è indistinguibile da quello di CDKN2A.": "Seltene Varianten, die sich im Codon 24 häufen: Das Familienbild ist von dem bei CDKN2A nicht zu unterscheiden.",
  "Variazione:": "Veränderung:",
  "Verdi": "Grün",
  "Verranno cancellate per sempre la sua unica foto e i rapporti di analisi.": "Sein einziges Foto und die Analyseberichte werden endgültig gelöscht.",
  "Verranno cancellate per sempre tutte le sue {n} foto e i rapporti di analisi.": "Alle seine {n} Fotos und die Analyseberichte werden endgültig gelöscht.",
  "Verranno cancellati per sempre il profilo, tutti i nei, tutte le foto e tutti i rapporti di questo utente. L'operazione non si può annullare.": "Das Profil, alle Muttermale, alle Fotos und alle Berichte dieses Benutzers werden endgültig gelöscht. Dies kann nicht rückgängig gemacht werden.",
  "Versione": "Version",
  "Versione dell'avviso non valida.": "Ungültige Version des Hinweises.",
  "Viso": "Gesicht",
  "a cielo sereno e senza protezione, al picco di oggi la pelle può arrossarsi in": "Bei klarem Himmel und ohne Schutz kann sich die Haut zur heutigen Spitze röten in",
  "aggiornato": "aktualisiert",
  "altro": "andere",
  "assumo che le 2 uscite siano [benigno, maligno]; ordine non verificabile": "ich nehme an, dass die 2 Ausgaben [gutartig, bösartig] sind; Reihenfolge nicht überprüfbar",
  "attivo solo se lo abiliti qui sotto": "nur aktiv, wenn Sie es unten einschalten",
  "capelli biondi": "blonde Haare",
  "capelli castani": "braune Haare",
  "capelli grigi o bianchi": "graue oder weiße Haare",
  "capelli neri": "schwarze Haare",
  "capelli rossi": "rote Haare",
  "carcinoma basocellulare, tumore della pelle": "Basalzellkarzinom, ein Hautkrebs",
  "carcinoma squamocellulare, tumore della pelle": "Plattenepithelkarzinom, ein Hautkrebs",
  "cheratosi attinica, lesione pre-cancerosa": "aktinische Keratose, eine Krebsvorstufe",
  "cheratosi seborroica, benigna": "seborrhoische Keratose, gutartig",
  "circa {minuti} minuti": "etwa {minuti} Minuten",
  "connessione non riuscita: {motivo}": "Verbindung fehlgeschlagen: {motivo}",
  "cuoio capelluto": "Kopfhaut",
  "dermoscopica": "dermatoskopisch",
  "donna": "Frau",
  "dorso del piede": "Fußrücken",
  "dorso della mano": "Handrücken",
  "e clicca sul punto esatto del corpo (ingrandisci con la rotella per essere più preciso).": "und klicken Sie auf die genaue Stelle am Körper (zoomen Sie mit dem Mausrad für mehr Genauigkeit).",
  "e conferma l'email.": "und bestätigen Sie die E-Mail-Adresse.",
  "es. 4,5": "z. B. 4,5",
  "facoltativa: richiede una tua chiave personale": "optional: erfordert einen eigenen persönlichen Schlüssel",
  "foto normale": "normales Foto",
  "fototipo {tipo}": "Hauttyp {tipo}",
  "fronte": "vorn",
  "gratuita, senza account né chiave": "kostenlos, ohne Konto und Schlüssel",
  "i metodi non concordano tra loro": "die Methoden sind sich untereinander nicht einig",
  "i modelli di App 1 non sono stati scaricati: sono ancora dei segnaposto Git LFS. Apri PowerShell nella cartella {cartella} e lancia 'git lfs pull', poi riprova.": "die Modelle von App 1 wurden nicht heruntergeladen: Es sind noch Git-LFS-Platzhalter. Öffnen Sie PowerShell im Ordner {cartella}, führen Sie 'git lfs pull' aus und versuchen Sie es erneut.",
  "ieri": "gestern",
  "il modello ha {n} uscite: significato sconosciuto": "das Modell hat {n} Ausgaben: Bedeutung unbekannt",
  "impossibile avviare: {e}": "kann nicht gestartet werden: {e}",
  "in {n} giorni.": "in {n} Tagen.",
  "in {n} giorno.": "in {n} Tag.",
  "indirizzo del servizio non ammesso (serve https)": "Adresse des Dienstes nicht zulässig (https erforderlich)",
  "indirizzo non ammesso (solo https)": "Adresse nicht zulässig (nur https)",
  "interrotto dopo {minuti} minuti (tempo massimo)": "nach {minuti} Minuten abgebrochen (Höchstdauer)",
  "la foto non si apre come immagine ({tipo}): {dettaglio}": "das Foto lässt sich nicht als Bild öffnen ({tipo}): {dettaglio}",
  "labbro": "Lippe",
  "le prime 1.000 chiamate al giorno sono gratuite, le successive si pagano. OpenWeather può chiedere una carta di pagamento per attivarlo: controlla le condizioni sul loro sito.": "die ersten 1.000 Abrufe pro Tag sind kostenlos, weitere kosten Geld. OpenWeather kann zur Aktivierung eine Zahlungskarte verlangen: Prüfen Sie die Bedingungen auf deren Website.",
  "mai": "nie",
  "mancano i pesi addestrati: nella cartella {cartella} non ci sono i file model_fold_0.bin ... model_fold_4.bin. Il repository non li contiene: vanno prodotti con train.py sul dataset SIIM-ISIC.": "Die trainierten Gewichte fehlen: Im Ordner {cartella} liegen die Dateien model_fold_0.bin ... model_fold_4.bin nicht. Das Repository enthält sie nicht: Sie müssen mit train.py auf dem SIIM-ISIC-Datensatz erzeugt werden.",
  "media di {n} modelli; punteggio medio {media} (soglia 0)": "Mittelwert aus {n} Modellen; mittlerer Score {media} (Schwelle 0)",
  "melanoma": "Melanom",
  "meno di 25": "weniger als 25",
  "molte": "viele",
  "molte efelidi": "viele Sommersprossen",
  "nel pannello": "im Panel",
  "nessun caso indicato": "keine Fälle angegeben",
  "nessun metodo ha segnalato il neo (questo non esclude un melanoma)": "keine Methode hat das Muttermal gemeldet (das schließt ein Melanom nicht aus)",
  "nessun risultato disponibile": "kein Ergebnis verfügbar",
  "nessuna efelide": "keine Sommersprossen",
  "nevo, cioe' neo benigno": "Nävus, also gutartiges Muttermal",
  "no": "nein",
  "nome@esempio.it (facoltativa)": "name@beispiel.de (optional)",
  "non riesco a preparare la foto in modo sicuro: {e}": "Das Foto kann nicht sicher aufbereitet werden: {e}",
  "non so": "weiß nicht",
  "occhi azzurri o grigi": "blaue oder graue Augen",
  "occhi scuri": "dunkle Augen",
  "occhi verdi": "grüne Augen",
  "oggi": "heute",
  "oltre 2 ore (UV molto basso)": "über 2 Stunden (sehr niedrige UV-Strahlung)",
  "orecchio": "Ohr",
  "pagina del servizio": "Seite des Dienstes",
  "palmo della mano": "Handfläche",
  "palpebra": "Augenlid",
  "pianta del piede": "Fußsohle",
  "poche": "wenige",
  "poche efelidi": "wenige Sommersprossen",
  "posizione da indirizzo internet non disponibile": "Standort aus der Internetadresse nicht verfügbar",
  "prob. melanoma {perc}": "Melanom-Wahrsch. {perc}",
  "probabilita' di malignita' stimata dal modello: {pm}": "vom Modell geschätzte Wahrscheinlichkeit für Bösartigkeit: {pm}",
  "qualche volta": "manchmal",
  "retro": "hinten",
  "rilevante": "relevant",
  "risposta illeggibile: {e}": "Antwort nicht lesbar: {e}",
  "risposta non valida dal servizio": "ungültige Antwort des Dienstes",
  "risposta senza nome della lesione: {risposta}": "Antwort ohne Läsionsnamen: {risposta}",
  "risposta troppo grande": "Antwort zu groß",
  "servizio non raggiungibile: {ultimo_errore}": "Dienst nicht erreichbar: {ultimo_errore}",
  "sicurezza {perc}": "Sicherheit {perc}",
  "sotto l'unghia (mano)": "unter dem Nagel (Hand)",
  "sotto l'unghia (piede)": "unter dem Nagel (Fuß)",
  "spazio tra le dita": "zwischen den Fingern oder Zehen",
  "spesso": "oft",
  "studi su PubMed": "Studien in PubMed",
  "sì": "ja",
  "sì, negativo": "ja, negativ",
  "sì, non informativo": "ja, nicht informativ",
  "sì, positivo": "ja, positiv",
  "tempo scaduto o rete non disponibile": "Zeitüberschreitung oder Netzwerk nicht verfügbar",
  "tutti i metodi con risultato indicano un neo da attenzionare": "alle Methoden mit Ergebnis melden ein auffälliges Muttermal",
  "ukalwa / melanoma-detection (app Android)": "ukalwa / melanoma-detection (Android-App)",
  "uomo": "Mann",
  "uscita letta come le 6 classi di pelle (non verificabile)": "Ausgabe als die 6 Hautklassen gelesen (nicht überprüfbar)",
  "vatsal30 / Melanoma-Detection (PyTorch)": "vatsal30 / Melanoma-Detection (PyTorch)",
  "{avviso} Il servizio Open-Meteo non risponde ({e}).": "{avviso} Der Dienst Open-Meteo antwortet nicht ({e}).",
  "{cosa} non può essere vuoto.": "{cosa} darf nicht leer sein.",
  "{cosa} è troppo lungo (massimo {massimo} caratteri).": "{cosa} ist zu lang (höchstens {massimo} Zeichen).",
  "{file_modello} e' ancora un segnaposto Git LFS: lancia 'git lfs pull' nella cartella {cartella}.": "{file_modello} ist noch ein Git-LFS-Platzhalter: Führen Sie 'git lfs pull' im Ordner {cartella} aus.",
  "{file_pesi} e' ancora un segnaposto Git LFS: apri PowerShell nella cartella {cartella} e lancia 'git lfs pull'.": "{file_pesi} ist noch ein Git-LFS-Platzhalter: Öffnen Sie PowerShell im Ordner {cartella} und führen Sie 'git lfs pull' aus.",
  "{foto} · ultima {quando}": "{foto} · letzte {quando}",
  "{giorno} ore {ora}: indice UV {uvi} ({categoria})": "{giorno}, {ora} Uhr: UV-Index {uvi} ({categoria})",
  "{nome} · {mb} MB · clicca per cambiare": "{nome} · {mb} MB · zum Ändern klicken",
  "{nome}: errore.": "{nome}: Fehler.",
  "{nome}: il valore deve essere tra {minimo} e {massimo}.": "{nome}: Der Wert muss zwischen {minimo} und {massimo} liegen.",
  "{nome}: inserisci un numero.": "{nome}: Geben Sie eine Zahl ein.",
  "{nome}: non disponibile.": "{nome}: nicht verfügbar.",
  "{n} altro/i parente/i con melanoma": "{n} weitere(r) Verwandte(r) mit Melanom",
  "{n} anni": "{n} Jahre",
  "{n} anni fa": "vor {n} Jahren",
  "{n} anno": "{n} Jahr",
  "{n} anno fa": "vor {n} Jahr",
  "{n} articoli su melanoma e «{termine}»": "{n} Artikel zu Melanom und «{termine}»",
  "{n} articoli trovati su PubMed · ricerca del {data}": "{n} Artikel in PubMed gefunden · Suche vom {data}",
  "{n} articoli trovati su PubMed · ricerca del {data} (salvata)": "{n} Artikel in PubMed gefunden · Suche vom {data} (gespeichert)",
  "{n} con astrocitoma": "{n} mit Astrozytom",
  "{n} con melanoma uveale": "{n} mit uvealem Melanom",
  "{n} con tumore del pancreas": "{n} mit Bauchspeicheldrüsenkrebs",
  "{n} file modello su 10": "{n} von 10 Modelldateien",
  "{n} file modello su 5": "{n} von 5 Modelldateien",
  "{n} foto": "{n} Foto",
  "{n} foto in {giorni} (dal {da} al {a}).": "{n} Fotos in {giorni} (vom {da} bis {a}).",
  "{n} foto#pl": "{n} Fotos",
  "{n} giorni": "{n} Tage",
  "{n} giorni fa": "vor {n} Tagen",
  "{n} giorno": "{n} Tag",
  "{n} mesi fa": "vor {n} Monaten",
  "{n} metodi su {tot} hanno risposto": "{n} von {tot} Methoden haben geantwortet",
  "{n} nei": "{n} Muttermale",
  "{n} nei in questa scheda": "{n} Muttermale auf diesem Blatt",
  "{n} neo": "{n} Muttermal",
  "{n} neo in questa scheda": "{n} Muttermal auf diesem Blatt",
  "{n} parente/i di primo grado con melanoma": "{n} Verwandte(r) ersten Grades mit Melanom",
  "{n} su {tot}: {et}": "{n} von {tot}: {et}",
  "{vista} · posizione {x}% da sinistra, {y}% dall'alto": "{vista} · Position {x} % von links, {y} % von oben",
  "È una stima prudente che usa la dose minima di eritema più bassa del tuo fototipo; con riflessi (acqua, neve, sabbia), quota o pelle già arrossata il tempo si accorcia.": "Das ist eine vorsichtige Schätzung auf Grundlage der niedrigsten minimalen Erythemdosis Ihres Hauttyps; bei Reflexionen (Wasser, Schnee, Sand), in der Höhe oder bei bereits geröteter Haut verkürzt sich die Zeit.",
  "È uno strumento personale per organizzare le foto dei tuoi nei e confrontare nel tempo i risultati di alcuni modelli di ricerca. Non è certificato né approvato da alcuna autorità sanitaria.": "Es ist ein persönliches Werkzeug, um die Fotos Ihrer Muttermale zu ordnen und die Ergebnisse einiger Forschungsmodelle im Zeitverlauf zu vergleichen. Es ist von keiner Gesundheitsbehörde zertifiziert oder zugelassen.",
  "…di cui di 1° grado": "…davon 1. Grades",
  "← Tutti i nei": "← Alle Muttermale"
};
'''
WEB_FILES["/i18n_de.js"] = ("text/javascript; charset=utf-8", _WEB_I18N_DE_JS.encode("utf-8"))

_WEB_I18N_EN_JS = r'''/* Traduzioni dell'interfaccia di NeoTracker: en. Chiave = testo italiano originale.
   I segnaposto {nome} vanno lasciati uguali. Controllo: python3 tools/traduzioni.py */
(window.NT_DIZIONARI = window.NT_DIZIONARI || {}).en = {
  "(licenza CC BY 4.0). Il servizio gratuito è per uso personale e non commerciale.": "(CC BY 4.0 licence). The free service is for personal, non-commercial use.",
  "(ora locale del luogo)": "(local time at the location)",
  "(ricerca salvata del {data})": "(saved search from {data})",
  "(senza titolo)": "(untitled)",
  "(vuoto)": "(empty)",
  "({variazione} mm dalla foto precedente)": "({variazione} mm since the previous photo)",
  "1 foto del {data}, diametro {mm} mm.": "1 photo from {data}, diameter {mm} mm.",
  "1 foto del {data}.": "1 photo from {data}.",
  "100 o più": "100 or more",
  "100 o più nei sul corpo": "100 or more moles on the body",
  "3 = da qui l'OMS consiglia protezione": "3 = WHO recommends protection from this level",
  "3 o più melanomi primari nella stessa persona": "3 or more primary melanomas in the same person",
  "A che cosa servono questi dati?": "What is this information used for?",
  "Accesso non autorizzato.": "Unauthorised access.",
  "Accetto e continuo": "Accept and continue",
  "Addome alto destro": "Upper abdomen, right",
  "Addome alto sinistro": "Upper abdomen, left",
  "Addome basso destro": "Lower abdomen, right",
  "Addome basso sinistro": "Lower abdomen, left",
  "Adesso": "Now",
  "Aggiorna": "Refresh",
  "Aggiungi la prima foto: diventa la tua foto storica, e ogni foto successiva ne seguirà l'evoluzione.": "Add the first photo: it becomes your baseline photo, and every later photo will follow how the mole evolves.",
  "Aggiungi neo": "Add mole",
  "Aggiungi qui sotto la prima foto: sarà il punto di partenza per vedere se il neo cambia nel tempo.": "Add the first photo below: it will be the starting point to see whether the mole changes over time.",
  "Aggiungi una foto allo storico": "Add a photo to the history",
  "Alla sottoscrizione il limite giornaliero predefinito è di 2.000 chiamate: nella scheda «Billing plans» del tuo account puoi abbassarlo a 1.000, così non spendi nulla. NeoTracker ne usa poche (al massimo 4 ogni 10 minuti, solo quando apri la pagina Indice UV).": "When you subscribe, the default daily limit is 2,000 calls: in the «Billing plans» tab of your account you can lower it to 1,000, so you spend nothing. NeoTracker uses very few (at most 4 every 10 minutes, only when you open the UV Index page).",
  "Almeno 3 diagnosi tra melanoma, tumore del pancreas e astrocitoma nella stessa linea familiare (tua inclusa)": "At least 3 diagnoses among melanoma, pancreatic cancer and astrocytoma in the same family line (yours included)",
  "Almeno un metodo (o un suo modello) segnala una lesione da attenzionare. Non è una diagnosi e questi strumenti sbagliano spesso, ma è un motivo in più per non rimandare la visita dermatologica e per portare questo rapporto.": "At least one method (or one of its models) flags a lesion that needs attention. This is not a diagnosis and these tools are often wrong, but it is one more reason not to put off the dermatology visit and to bring this report.",
  "Alto": "High",
  "Alto (raro)": "High (rare)",
  "Alto (sindrome BAP1)": "High (BAP1 syndrome)",
  "Altri parenti con melanoma": "Other relatives with melanoma",
  "Altri tumori della pelle (basalioma, spinalioma)": "Other skin cancers (basal cell and squamous cell carcinoma)",
  "Altro": "Other",
  "Altro che vuoi ricordare (allergie, farmaci fotosensibilizzanti, …)": "Anything else you want to remember (allergies, photosensitising medicines, …)",
  "Analisi automatica": "Automatic analysis",
  "Analisi delle foto": "Photo analysis",
  "Analisi in corso…": "Analysis in progress…",
  "Analisi interrotta dopo {ore} ore (troppo lunga).": "Analysis stopped after {ore} hours (too long).",
  "Analisi: da attenzionare": "Analysis: needs attention",
  "Analizza questa foto": "Analyse this photo",
  "Analizza subito con tutti i metodi installati": "Analyse now with all installed methods",
  "Anche la ricerca delle città usa Open-Meteo.": "City search also uses Open-Meteo.",
  "Ancora nessuna foto": "No photos yet",
  "Annulla": "Cancel",
  "Anteprima": "Preview",
  "App 1 (DeborahAdedigba) - modelli TensorFlow": "App 1 (DeborahAdedigba) - TensorFlow models",
  "App per smartphone e rischio di cancro della pelle: accuratezza diagnostica": "Smartphone apps and skin cancer risk: diagnostic accuracy",
  "Apri la pagina «API keys» del tuo account e copia la chiave.": "Open the «API keys» page of your account and copy the key.",
  "Archivia (toglie dalla mappa, conserva i dati)": "Archive (removes it from the map, keeps the data)",
  "Articoli recenti e rilevanti su come riconoscere i nei sospetti, sull'affidabilità di app e intelligenza artificiale e sul melanoma ereditario. I risultati arrivano da PubMed, la banca dati pubblica della National Library of Medicine (USA).": "Recent, relevant articles on recognising suspicious moles, on the reliability of apps and artificial intelligence, and on hereditary melanoma. Results come from PubMed, the public database of the National Library of Medicine (USA).",
  "Asimmetria": "Asymmetry",
  "Aspetto": "Appearance",
  "Associati a varianti del gene MC1R.": "Associated with variants of the MC1R gene.",
  "Astrocitoma": "Astrocytoma",
  "Attenzione: non ho trovato l'ambiente .venv di App 1, uso il Python corrente.": "Warning: I did not find App 1's .venv environment; using the current Python.",
  "Aumenta: {voce}": "Increase: {voce}",
  "Autoesame della pelle": "Skin self-examination",
  "Automatica (come il sistema)": "Automatic (same as the system)",
  "Avambraccio destro": "Forearm, right",
  "Avambraccio sinistro": "Forearm, left",
  "Avvertenze": "Important notices",
  "Azzurri/grigi": "Blue/grey",
  "Basso": "Low",
  "Basso-moderato (comune)": "Low to moderate (common)",
  "Benvenuto in NeoTracker": "Welcome to NeoTracker",
  "Biondi": "Blond",
  "Bordi": "Border",
  "Braccio destro": "Arm, right",
  "Braccio sinistro": "Arm, left",
  "Cambia": "Change",
  "Cambia immagine…": "Change image…",
  "Cambia nel tempo: forma, colore, dimensione, rilievo, o compaiono prurito o sanguinamento.": "It changes over time: shape, colour, size, elevation, or itching or bleeding appear.",
  "Cambia utente": "Switch user",
  "Capelli": "Hair",
  "Capelli rossi o biondi": "Red or blond hair",
  "Carcinoma del rene": "Kidney carcinoma",
  "Caricamento…": "Loading…",
  "Cartella dei progetti:": "Projects folder:",
  "Cartella dei tuoi dati (da copiare per il backup):": "Folder with your data (copy it for backup):",
  "Castani": "Brown",
  "Caviglia destra": "Ankle, right",
  "Caviglia sinistra": "Ankle, left",
  "Cavo popliteo destro": "Back of knee, right",
  "Cavo popliteo sinistro": "Back of knee, left",
  "Centra sulla mappa": "Centre on the map",
  "Cerca": "Search",
  "Cerca altro (es. \"ugly duckling sign\", \"nail melanoma\"…)": "Search for more (e.g. \"ugly duckling sign\", \"nail melanoma\"…)",
  "Cerca nella letteratura": "Search the literature",
  "Cerca una città (es. Torino)": "Search for a city (e.g. Turin)",
  "Cerco su PubMed…": "Searching PubMed…",
  "Cerco…": "Searching…",
  "Chi ha avuto un melanoma ha un rischio maggiore di un secondo.": "Having had a melanoma raises the risk of a second one.",
  "Chi ha tanti nei, nei atipici o una storia di melanoma dovrebbe proteggersi anche con indici moderati.": "People with many moles, atypical moles or a history of melanoma should protect themselves even when the index is moderate.",
  "Chi sei?": "Who are you?",
  "Chiave OpenWeather": "OpenWeather key",
  "Chiave OpenWeather salvata ({finale}).": "OpenWeather key saved ({finale}).",
  "Chiave rimossa.": "Key removed.",
  "Chiave salvata ({finale}) — scrivine una nuova per sostituirla": "Key saved ({finale}) — type a new one to replace it",
  "Chiave salvata.": "Key saved.",
  "Chiedo la posizione al browser… (potrebbe comparire una richiesta di permesso)": "Asking the browser for your position… (a permission request may appear)",
  "Chiudere NeoTracker?": "Close NeoTracker?",
  "Chiudere il programma": "Closing the program",
  "Chiudi": "Close",
  "Chiudi NeoTracker": "Close NeoTracker",
  "Chiudi il programma": "Close the program",
  "Circa il 5-10% dei melanomi si presenta in famiglie con una predisposizione ereditaria (Leachman 2009). Qui trovi i criteri che usano gli specialisti per decidere se proporre una consulenza genetica, i geni coinvolti e la letteratura su ciascuno.": "About 5–10% of melanomas occur in families with an inherited predisposition (Leachman 2009). Here you find the criteria specialists use to decide whether to suggest genetic counselling, the genes involved and the literature on each.",
  "Citato dalle linee guida NCCN tra i geni da considerare nei pannelli per melanoma (sindrome di Cowden).": "Cited by the NCCN guidelines among the genes to consider in melanoma panels (Cowden syndrome).",
  "Classificati come cancerogeni certi per l'uomo (IARC).": "Classified as definite human carcinogens (IARC).",
  "Clic per vedere la foto originale a schermo intero": "Click to see the original photo full screen",
  "Clicca sul punto esatto del corpo dove si trova il neo (puoi ingrandire prima)": "Click on the exact spot on the body where the mole is (you can zoom in first)",
  "Clicca un neo nell'elenco o sulla mappa per vedere lo storico fotografico.": "Click a mole in the list or on the map to see its photo history.",
  "Collo": "Neck",
  "Colore": "Colour",
  "Colore degli occhi": "Eye colour",
  "Colore naturale dei capelli (da giovane)": "Natural hair colour (when young)",
  "Come ottenere la chiave": "How to get the key",
  "Come scattare foto confrontabili": "How to take comparable photos",
  "Come si legge l'indice UV": "How to read the UV index",
  "Compila la familiarità nel Profilo": "Fill in the family history in your Profile",
  "Compila la sezione 'Familiarità' nel Profilo: senza quei dati non posso verificare i criteri.": "Fill in the 'Family history' section of your Profile: without that data I cannot check the criteria.",
  "Con i dati inseriti non rientri nei criteri più usati. Il test genetico per il melanoma è indicato solo in una piccola minoranza di persone e non viene proposto di routine. Se la tua storia familiare cambia o hai dubbi, aggiorna il profilo e parlane col dermatologo.": "With the data entered you do not meet the most commonly used criteria. Genetic testing for melanoma is indicated only in a small minority of people and is not offered routinely. If your family history changes or you have doubts, update your profile and talk to your dermatologist.",
  "Con i dati inseriti non risultano fattori di rischio noti. Completa il profilo se mancano informazioni.": "With the data entered, no known risk factors appear. Complete your profile if information is missing.",
  "Con il tuo fototipo ({fototipo})": "With your phototype ({fototipo})",
  "Con o senza test, per chi ha una storia familiare restano fondamentali la protezione dal sole, l'autoesame della pelle e i controlli dermatologici periodici.": "With or without a test, for people with a family history, sun protection, skin self-examination and regular dermatological check-ups remain essential.",
  "Conferma": "Confirm",
  "Confronta": "Compare",
  "Confronta forma, bordi e colori: se noti differenze, mostra le foto al dermatologo.": "Compare shape, borders and colours: if you notice differences, show the photos to your dermatologist.",
  "Confronto tra due foto": "Comparison of two photos",
  "Consenso": "Consent",
  "Conta anche il «brutto anatroccolo»: un neo diverso da tutti gli altri. I noduli che crescono rapidamente o sono duri al tatto vanno mostrati subito. Questo promemoria non sostituisce la visita.": "The «ugly duckling» also counts: a mole that looks different from all the others. Nodules that grow quickly or feel hard to the touch should be shown straight away. This reminder does not replace a medical visit.",
  "Conta i parenti di sangue (non quelli acquisiti) dello stesso lato della famiglia, materno o paterno: è il criterio che usano i genetisti. Se non lo sai, chiedi a un familiare: queste informazioni sono molto utili.": "Count blood relatives (not in-laws) on the same side of the family, maternal or paternal: this is the criterion geneticists use. If you do not know, ask a relative: this information is very useful.",
  "Conta solo i melanomi primari invasivi.": "Only invasive primary melanomas count.",
  "Controllo lo stato…": "Checking status…",
  "Coordinate non valide.": "Invalid coordinates.",
  "Cosa fare": "What to do",
  "Cosa sapere prima di un test genetico": "What to know before a genetic test",
  "Coscia destra": "Thigh, right",
  "Coscia sinistra": "Thigh, left",
  "Crea un account gratuito su": "Create a free account at",
  "Crea utente": "Create user",
  "Criteri ABCDE e segno del 'brutto anatroccolo'": "ABCDE criteria and the 'ugly duckling' sign",
  "Criteri semplificati, a scopo informativo. Il test genetico riguarda una piccola minoranza di persone e non è un esame di routine: è lo specialista a decidere se e quale test proporre, di norma dopo una consulenza genetica e partendo, quando possibile, da un familiare che ha avuto la malattia.": "Simplified criteria, for information only. Genetic testing concerns a small minority of people and is not a routine examination: it is up to the specialist to decide whether and which test to offer, usually after genetic counselling and, when possible, starting from a relative who has had the disease.",
  "Cuoio capelluto (testa)": "Scalp (head)",
  "Cursore di confronto": "Comparison slider",
  "D": "R",
  "D = destra del paziente · S = sinistra": "R = patient's right · L = left",
  "Da 50 a 99 nei sul corpo": "50 to 99 moles on the body",
  "Da attenzionare": "Needs attention",
  "Da rifotografare?": "Time to re-photograph?",
  "Dai un nome al neo e controlla la sede.": "Give the mole a name and check the site.",
  "Data della foto troppo vecchia.": "Photo date is too old.",
  "Data dello scatto": "Date the photo was taken",
  "Data di nascita": "Date of birth",
  "Data di nascita fuori intervallo.": "Date of birth out of range.",
  "Data di nascita non valida (AAAA-MM-GG).": "Invalid date of birth (YYYY-MM-DD).",
  "Data non valida: usa il formato AAAA-MM-GG.": "Invalid date: use the format YYYY-MM-DD.",
  "Dati della persona": "Personal details",
  "Dati meteo e UV:": "Weather and UV data:",
  "Dati non validi (JSON).": "Invalid data (JSON).",
  "Dati non validi.": "Invalid data.",
  "Dati orari non disponibili": "Hourly data not available",
  "Dati personali": "Personal data",
  "Deep learning e melanoma: revisioni sistematiche": "Deep learning and melanoma: systematic reviews",
  "Dermoscopia e diagnosi precoce (revisioni)": "Dermoscopy and early diagnosis (reviews)",
  "Dermoscopica": "Dermoscopic",
  "Di qualsiasi grado di parentela.": "Of any degree of kinship.",
  "Diagnosi totali indicate: {diagnosi}. Leachman 2009 considera melanoma e tumore del pancreas nei parenti di 1o e 2o grado dello stesso lato della famiglia; l'astrocitoma è incluso dalle linee guida NCCN.": "Total diagnoses entered: {diagnosi}. Leachman 2009 counts melanoma and pancreatic cancer in 1st- and 2nd-degree relatives on the same side of the family; astrocytoma is included by the NCCN guidelines.",
  "Diametro": "Diameter",
  "Diametro (mm)": "Diameter (mm)",
  "Diametro del neo nel tempo": "Mole diameter over time",
  "Diametro misurato (mm)": "Measured diameter (mm)",
  "Diametro nel tempo": "Diameter over time",
  "Diametro:": "Diameter:",
  "Diametro: da {da} a {a} mm.": "Diameter: from {da} to {a} mm.",
  "Diametro: {diff} mm di differenza.": "Diameter: {diff} mm difference.",
  "Diminuisci: {voce}": "Decrease: {voce}",
  "Donna": "Woman",
  "Dopo": "After",
  "Dove si trovano": "Where they are",
  "Efelidi": "Freckles",
  "Efelidi (lentiggini)": "Freckles (ephelides)",
  "Elenco di fattori noti dalla letteratura, non un punteggio validato: non stima la probabilità di ammalarsi.": "List of factors known from the literature, not a validated score: it does not estimate the probability of falling ill.",
  "Elimina": "Delete",
  "Elimina definitivamente": "Delete permanently",
  "Elimina foto": "Delete photo",
  "Elimina questo neo e le sue foto": "Delete this mole and its photos",
  "Eliminare questa foto?": "Delete this photo?",
  "Eliminare «{nome}»?": "Delete «{nome}»?",
  "Email non valida.": "Invalid email address.",
  "Email per PubMed": "Email for PubMed",
  "Email salvata.": "Email saved.",
  "Errore imprevisto: {e}": "Unexpected error: {e}",
  "Errore interno. I dettagli sono nel file neotracker.log nella cartella dei dati.": "Internal error. Details are in the neotracker.log file in the data folder.",
  "Errore {codice}": "Error {codice}",
  "Esci dal programma": "Quit the program",
  "Esiste già un utente con questo nome.": "A user with this name already exists.",
  "Esposizione al sole": "Sun exposure",
  "Estremo": "Extreme",
  "Età": "Age",
  "Età, sesso e fenotipo non cambiano l'uscita delle reti neurali: servono a mostrarti i fattori di rischio, a scegliere la letteratura, a valutare i criteri di genetica e a stimare il tempo di scottatura.": "Age, sex and phenotype do not change the output of the neural networks: they are used to show you the risk factors, choose the literature, evaluate the genetics criteria and estimate the time to sunburn.",
  "Evita il sole nelle ore centrali e proteggi bene la pelle.": "Avoid the sun in the middle hours of the day and protect your skin well.",
  "Evita l'esposizione diretta: la pelle non protetta può scottarsi in pochi minuti.": "Avoid direct exposure: unprotected skin can burn within a few minutes.",
  "Evoluzione": "Evolution",
  "FRONTE": "FRONT",
  "Facoltativa": "Optional",
  "Fajuyigbe D, Young AR. The impact of skin colour on human photobiological responses. Pigment Cell Melanoma Res 2016;29:607-18 (dose minima di eritema per fototipo)": "Fajuyigbe D, Young AR. The impact of skin colour on human photobiological responses. Pigment Cell Melanoma Res 2016;29:607-18 (minimal erythema dose by phototype)",
  "Familiarità": "Family history",
  "Fattori di rischio indicati:": "Risk factors indicated:",
  "Fattori di rischio presenti": "Risk factors present",
  "Fenotipo: pelle, capelli, occhi": "Phenotype: skin, hair, eyes",
  "File della foto non trovato.": "Photo file not found.",
  "Fonte dell'indice UV cambiata.": "UV index source changed.",
  "Fonte dell'indice UV non valida.": "Invalid UV index source.",
  "Fonte:": "Source:",
  "Fonti": "Sources",
  "Formato non supportato: servono JPG, PNG, WEBP o BMP.": "Unsupported format: JPG, PNG, WEBP or BMP are required.",
  "Formato non supportato: servono JPG, PNG, WEBP o BMP. Le foto HEIC degli iPhone vanno convertite in JPG (impostazioni fotocamera: 'Più compatibile').": "Unsupported format: JPG, PNG, WEBP or BMP are required. iPhone HEIC photos must be converted to JPG (camera settings: 'Most Compatible').",
  "Foto a fuoco, con il neo al centro e la pelle ben visibile (sposta i peli, se serve).": "In-focus photo, with the mole in the centre and the skin clearly visible (move hair aside if needed).",
  "Foto del {data}": "Photo from {data}",
  "Foto eliminata.": "Photo deleted.",
  "Foto non trovata.": "Photo not found.",
  "Foto normale": "Normal photo",
  "Foto normale (smartphone)": "Normal photo (smartphone)",
  "Foto originale": "Original photo",
  "Foto salvata ({data}).": "Photo saved ({data}).",
  "Foto salvata ({data}, data letta dalla foto).": "Photo saved ({data}, date read from the photo).",
  "Fotografia sequenziale e monitoraggio dei nei nel tempo": "Sequential photography and monitoring of moles over time",
  "Fototipo": "Phototype",
  "Fototipo (classificazione di Fitzpatrick)": "Phototype (Fitzpatrick classification)",
  "Fototipo chiaro (I-II)": "Fair phototype (I–II)",
  "Fototipo, età e familiarità non cambiano il risultato delle reti neurali (guardano solo i pixel): servono a contestualizzare il rischio.": "Phototype, age and family history do not change the neural networks' result (they only look at pixels): they serve to put the risk in context.",
  "Fronte": "Front",
  "Fronte e cuoio capelluto": "Forehead and scalp",
  "Gamba (stinco) destra": "Lower leg (shin), right",
  "Gamba (stinco) sinistra": "Lower leg (shin), left",
  "Gene": "Gene",
  "Gene dei telomeri (complesso shelterin): varianti rare in famiglie con melanoma.": "Telomere gene (shelterin complex): rare variants in families with melanoma.",
  "Gene dei telomeri: varianti rare in alcune famiglie con melanoma.": "Telomere gene: rare variants in some families with melanoma.",
  "Gene non presente nell'elenco.": "Gene not in the list.",
  "Gene {n} di {tot} ({nome})…": "Gene {n} of {tot} ({nome})…",
  "Genetica": "Genetics",
  "Genitori, fratelli o figli.": "Parents, siblings or children.",
  "Genitori, fratelli, sorelle, figli.": "Parents, brothers, sisters, children.",
  "Ginocchio destro": "Knee, right",
  "Ginocchio sinistro": "Knee, left",
  "Gli articoli sono scelti da una ricerca automatica e non sono stati valutati da NeoTracker: leggili con il tuo medico.": "The articles are chosen by an automatic search and have not been assessed by NeoTracker: read them with your doctor.",
  "Gluteo destro": "Buttock, right",
  "Gluteo sinistro": "Buttock, left",
  "Gomito destro": "Elbow, right",
  "Gomito sinistro": "Elbow, left",
  "Grigi/bianchi": "Grey/white",
  "Hai indicato di aver già eseguito un test genetico: porta il referto al dermatologo.": "You said you have already had a genetic test: take the report to your dermatologist.",
  "Hai scelto OpenWeather ma manca la chiave (Impostazioni): mostro i dati di Open-Meteo.": "You chose OpenWeather but the key is missing (Settings): showing Open-Meteo data.",
  "Hai scelto OpenWeather ma non c'è ancora una chiave: finché manca, il programma usa Open-Meteo.": "You chose OpenWeather but there is no key yet: until one is added, the program uses Open-Meteo.",
  "Ho avuto (o ho) uno di questi tumori:": "I have had (or have) one of these cancers:",
  "Ho avuto altri tumori della pelle (basalioma, spinalioma)": "I have had other skin cancers (basal cell or squamous cell carcinoma)",
  "Ho già fatto un test genetico per il melanoma?": "Have I already had a genetic test for melanoma?",
  "Ho letto e capito queste avvertenze": "I have read and understood these notices",
  "Ho verificato la mia storia familiare (anche se la risposta è «nessuno»)": "I have checked my family history (even if the answer is «none»)",
  "I dati (anche di salute) restano su questo computer. Escono solo le richieste che attivi tu: indice UV (coordinate approssimate), ricerche su PubMed (solo i termini cercati) e, solo se lo attivi, l'invio della foto a SkinSense.": "Your data (including health data) stays on this computer. Only the requests you turn on leave it: UV index (approximate coordinates), PubMed searches (only the search terms) and, only if you enable it, sending the photo to SkinSense.",
  "I dati inseriti rientrano in almeno un criterio descritto in letteratura. Ti consigliamo di parlarne con il dermatologo o con un medico genetista (consulenza genetica oncologica): sarà lo specialista a decidere se e quale test proporre, di norma dopo la consulenza e, quando possibile, partendo da un familiare affetto. Geni più citati dalle linee guida: {geni}. L'uso dei pannelli multigene è ancora oggetto di discussione tra gli specialisti: per questo conta la consulenza prima del test.": "The data entered meet at least one criterion described in the literature. We advise you to talk about it with your dermatologist or a medical geneticist (oncological genetic counselling): the specialist will decide whether and which test to offer, usually after counselling and, when possible, starting from an affected relative. Genes most cited by the guidelines: {geni}. The use of multigene panels is still under discussion among specialists: that is why counselling before the test matters.",
  "I geni più studiati": "The most studied genes",
  "I metodi sono addestrati su fotografie diverse dalle tue: cambiare luce, distanza o fotocamera può cambiare la risposta.": "The methods are trained on photographs different from yours: changing light, distance or camera can change the answer.",
  "I numeri corrispondono alle schede seguenti. Sulla figura: a sinistra la vista frontale, a destra quella posteriore.": "The numbers match the following sheets. In the figure: the front view on the left, the back view on the right.",
  "I raggi ultravioletti sono il principale fattore di rischio modificabile per il melanoma. Qui vedi quanto sono forti oggi dove ti trovi.": "Ultraviolet rays are the main modifiable risk factor for melanoma. Here you can see how strong they are today where you are.",
  "I risultati sono stime sperimentali e possono sbagliare in entrambe le direzioni: un esito rassicurante non esclude un melanoma, un esito di attenzione non significa che ci sia.": "The results are experimental estimates and can be wrong in both directions: a reassuring result does not rule out a melanoma, and a result flagging attention does not mean there is one.",
  "I tuoi dati rispetto ai criteri": "Your data against the criteria",
  "I tuoi nei ({n})": "Your moles ({n})",
  "Identificativo di pagina non valido.": "Invalid page identifier.",
  "Il computer non riesce a determinare la posizione. Cerca la città per nome.": "The computer cannot determine the position. Search for the city by name.",
  "Il file non è un'immagine leggibile o è troppo grande.": "The file is not a readable image or is too large.",
  "Il file non è un'immagine leggibile, è danneggiato o ha troppi pixel (massimo {mp} megapixel).": "The file is not a readable image, is damaged or has too many pixels (maximum {mp} megapixels).",
  "Il file è troppo grande (massimo 40 MB).": "The file is too large (maximum 40 MB).",
  "Il file è vuoto.": "The file is empty.",
  "Il metodo 3 NON ha analizzato la foto: il progetto e' un prototipo senza modello. Il suo server si limita a ricevere l'immagine (nessuna rete neurale), quindi qualunque testo rassicurante mostri non deriva da un'analisi e non ha alcun valore.": "Method 3 did NOT analyse the photo: the project is a prototype without a model. Its server merely receives the image (no neural network), so any reassuring text it shows does not come from an analysis and has no value.",
  "Il metodo 5 e' un'app Android: non puo' girare dal PC. Installa l'APK sul telefono, inquadra il neo e annota a mano il risultato qui sotto.\nRisultato dell'app sul telefono: ______________________________": "Method 5 is an Android app: it cannot run on the PC. Install the APK on the phone, frame the mole and note the result by hand below.\nApp result on the phone: ______________________________",
  "Il metodo {n} ha detto che:": "Method {n} said:",
  "Il nome": "The name",
  "Il numero di nei è uno dei fattori di rischio più forti.": "The number of moles is one of the strongest risk factors.",
  "Il programma si spegne. Un'analisi in corso viene interrotta. I dati restano salvati.": "The program will shut down. An analysis in progress will be interrupted. Your data stays saved.",
  "Il risultato riguarda anche i familiari di sangue: per questo la consulenza prima e dopo il test è parte del percorso.": "The result also concerns blood relatives: that is why counselling before and after the test is part of the process.",
  "Il servizio Open-Meteo non risponde ({e}).": "The Open-Meteo service is not responding ({e}).",
  "Immagine personale": "Personal picture",
  "Immagine personale salvata.": "Personal picture saved.",
  "Immagine rimossa.": "Picture removed.",
  "Immunosoppressione (terapie, trapianto)": "Immunosuppression (therapies, transplant)",
  "Impostazioni": "Settings",
  "In coda (posizione {n})…": "Queued (position {n})…",
  "In coda…": "Queued…",
  "In inglese": "In English",
  "Incolla la chiave qui sopra e premi «Prova la chiave». Dopo l'iscrizione la chiave può impiegare qualche minuto ad attivarsi. Il programma prova prima One Call 4.0 e, se la chiave è di un abbonamento più vecchio, One Call 3.0.": "Paste the key above and press «Test the key». After subscribing, the key can take a few minutes to activate. The program tries One Call 4.0 first and, if the key belongs to an older plan, One Call 3.0.",
  "Incolla prima la chiave.": "Paste the key first.",
  "Incolla qui la chiave (32 lettere e numeri)": "Paste the key here (32 letters and digits)",
  "Indice UV": "UV index",
  "Indice UV di oggi": "Today's UV index",
  "Indice UV non disponibile": "UV index not available",
  "Indice UV ora per ora nelle prossime 24 ore": "Hour-by-hour UV index for the next 24 hours",
  "Indice UV: fonte dei dati": "UV index: data source",
  "Indirizzo non ammesso.": "Address not allowed.",
  "Indirizzo sconosciuto.": "Unknown address.",
  "Indirizzo troppo lungo.": "Address too long.",
  "Ingrandisci": "Enlarge",
  "Inguine destro": "Groin, right",
  "Inguine sinistro": "Groin, left",
  "Inviare le foto a SkinSense?": "Send the photos to SkinSense?",
  "Irregolari, frastagliati o sfumati.": "Irregular, jagged or blurred.",
  "Iscriviti all'abbonamento «One Call API» a pagamento per chiamata": "Subscribe to the pay-per-call «One Call API» plan",
  "JPG, PNG, WEBP o BMP · fino a 60 MB": "JPG, PNG, WEBP or BMP · up to 60 MB",
  "L'OMS consiglia di proteggersi a partire da un indice UV di 3.": "The WHO recommends protection from a UV index of 3.",
  "L'analisi di questa foto è in corso: attendi che finisca.": "This photo is being analysed: wait for it to finish.",
  "L'analisi non ha prodotto il rapporto. Ultime righe del log: {log}": "The analysis did not produce the report. Last lines of the log: {log}",
  "L'analisi non è riuscita.": "The analysis failed.",
  "L'immagine supera {mb} MB.": "The image exceeds {mb} MB.",
  "L'indice è una previsione: il valore reale dipende da nuvole, quota e riflessi.": "The index is a forecast: the actual value depends on clouds, altitude and reflections.",
  "La chiave OpenWeather contiene caratteri non validi (di solito sono 32 lettere/numeri).": "The OpenWeather key contains invalid characters (it is usually 32 letters/digits).",
  "La chiave resta salvata solo sul tuo computer e non viene mai mostrata né inviata alla pagina web del programma: la usa il programma Python per chiamare OpenWeather.": "The key stays saved only on your computer and is never shown to, or sent to, the program's web page: the Python program uses it to call OpenWeather.",
  "La chiave sarà cancellata da questo computer. Potrai inserirla di nuovo quando vuoi.": "The key will be deleted from this computer. You can enter it again whenever you want.",
  "La data della foto non può essere nel futuro.": "The photo date cannot be in the future.",
  "La foto del {data} e il suo rapporto di analisi saranno cancellati per sempre.": "The photo from {data} and its analysis report will be deleted permanently.",
  "La foto resta sul tuo computer: SkinSense (servizio online) è disattivato.": "The photo stays on your computer: SkinSense (online service) is turned off.",
  "La foto supera i {mb} MB: riducila o scegline un'altra.": "The photo exceeds {mb} MB: reduce it or choose another one.",
  "La foto supera {MAX_MB_FOTO} MB.": "The photo exceeds {MAX_MB_FOTO} MB.",
  "La libreria Pillow è vecchia e ha problemi di sicurezza noti: aggiornala con «py -m pip install -U pillow».": "The Pillow library is old and has known security problems: update it with «py -m pip install -U pillow».",
  "La mia posizione ({lat}; {lon})": "My location ({lat}; {lon})",
  "La posizione resta salvata solo su questo computer; viene inviata al servizio meteo (coordinate arrotondate) per ottenere l'indice UV.": "The location is saved only on this computer; it is sent to the weather service (rounded coordinates) to get the UV index.",
  "La prima analisi può richiedere diversi minuti (i modelli vengono caricati in memoria).": "The first analysis can take several minutes (the models are loaded into memory).",
  "La scelta vale per tutti gli utenti di questo computer. Il testo originale e vincolante delle avvertenze legali è quello italiano; il rapporto di testo completo resta in italiano.": "The choice applies to all users of this computer. The original and binding text of the legal notices is the Italian one; the full text report stays in Italian.",
  "La variante p.E318K aumenta il rischio di melanoma e di carcinoma renale e si associa a molti nei.": "The p.E318K variant increases the risk of melanoma and renal carcinoma and is associated with many moles.",
  "La vista deve essere 'fronte' o 'retro'.": "The view must be 'fronte' or 'retro'.",
  "Lampade": "Sunbeds",
  "Lampade abbronzanti": "Tanning lamps",
  "Lampade o lettini abbronzanti": "Tanning lamps or sunbeds",
  "Lavoro o attività prolungata all'aperto": "Work or prolonged activity outdoors",
  "Lavoro o faccio attività per molte ore all'aperto": "I work or do activities outdoors for many hours",
  "Le due metà del neo non si somigliano.": "The two halves of the mole do not look alike.",
  "Le informazioni su rischio, letteratura e genetica sono divulgative e non sostituiscono la consulenza di un medico o di un genetista.": "The information on risk, literature and genetics is for general information and does not replace the advice of a doctor or geneticist.",
  "Le linee guida raccomandano il test solo dopo una selezione accurata dei candidati e un'adeguata consulenza (Rossi 2019); l'uso dei pannelli multigene è ancora discusso.": "Guidelines recommend the test only after careful selection of candidates and adequate counselling (Rossi 2019); the use of multigene panels is still debated.",
  "Le nuvole sottili non fermano gran parte degli UV: l'indice può restare alto anche con il cielo velato.": "Thin clouds do not stop much of the UV: the index can stay high even with a hazy sky.",
  "Le ore centrali (circa 11-16) sono quelle con l'indice più alto.": "The middle hours of the day (about 11–16) have the highest index.",
  "Le ricerche partono da questo computer verso PubMed (nessun dato personale viene inviato). I risultati si salvano per 7 giorni.": "Searches go from this computer to PubMed (no personal data is sent). Results are saved for 7 days.",
  "Le ricerche usano le E-utilities pubbliche di PubMed. NCBI chiede, per cortesia, un'email di contatto: è facoltativa e viene inviata solo a PubMed.": "Searches use PubMed's public E-utilities. NCBI asks, as a courtesy, for a contact email: it is optional and is sent only to PubMed.",
  "Le sezioni «scelte per te» usano parole legate al tuo profilo (per esempio fototipo o numero di nei): se preferisci non inviarle, non scansionare quella sezione.": "The «picked for you» sections use words linked to your profile (for example phototype or number of moles): if you prefer not to send them, do not scan that section.",
  "Leachman 2009 e 2017; NCCN": "Leachman 2009 and 2017; NCCN",
  "Leachman 2017; NCCN": "Leachman 2017; NCCN",
  "Leggi l'abstract": "Read the abstract",
  "Lentigo maligna e melanoma del volto": "Lentigo maligna and melanoma of the face",
  "Letteratura": "Literature",
  "Letteratura scientifica": "Scientific literature",
  "Letteratura: PubMed": "Literature: PubMed",
  "Linea guida": "Guideline",
  "Linee guida e criteri per il test genetico": "Guidelines and criteria for genetic testing",
  "Lingua": "Language",
  "Lingua dell'interfaccia": "Interface language",
  "Lingua non supportata.": "Language not supported.",
  "Lucas RM et al. Are current guidelines for sun protection optimal for health? Photochem Photobiol Sci 2018;17:1956-63 (UV Index e dose di eritema)": "Lucas RM et al. Are current guidelines for sun protection optimal for health? Photochem Photobiol Sci 2018;17:1956-63 (UV Index and erythemal dose)",
  "Mai": "Never",
  "Manca la posizione": "Location missing",
  "Mano destra": "Hand, right",
  "Mano sinistra": "Hand, left",
  "Mappa dei nei": "Mole map",
  "Mappa del corpo umano: fronte a sinistra, retro a destra": "Map of the human body: front on the left, back on the right",
  "Massimo di oggi": "Today's maximum",
  "Melanoma acrale (mani, piedi, unghie): dermoscopia": "Acral melanoma (hands, feet, nails): dermoscopy",
  "Melanoma dell'occhio (uveale)": "Melanoma of the eye (uveal)",
  "Melanoma e immunosoppressione": "Melanoma and immunosuppression",
  "Melanoma ereditario": "Hereditary melanoma",
  "Melanoma ereditario e test genetico": "Hereditary melanoma and genetic testing",
  "Melanoma già diagnosticato": "Melanoma already diagnosed",
  "Melanoma nelle pelli scure (spesso acrale)": "Melanoma in dark skin (often acral)",
  "Melanoma personale e parente di primo grado con tumore del pancreas": "Personal melanoma and a first-degree relative with pancreatic cancer",
  "Melanoma-Detector (VukIG)": "Melanoma-Detector (VukIG)",
  "Melanomi già diagnosticati": "Melanomas already diagnosed",
  "Melanomi già diagnosticati a me": "Melanomas already diagnosed in me",
  "Melanomi primari indicati: {mel_pers}.": "Primary melanomas indicated: {mel_pers}.",
  "Meno di 25": "Fewer than 25",
  "Mesotelioma": "Mesothelioma",
  "Meta-analisi": "Meta-analysis",
  "Metodi in disaccordo": "Methods disagree",
  "Metodo 1 - App 1 (Deborah Adedigba)": "Method 1 - App 1 (Deborah Adedigba)",
  "Metodo 1 disattivato dalle impostazioni.": "Method 1 turned off in the settings.",
  "Metodo 2 - SkinSense (servizio online)": "Method 2 - SkinSense (online service)",
  "Metodo 2 non eseguito (disattivato nelle impostazioni): la foto non e' uscita dal PC.": "Method 2 not run (turned off in the settings): the photo did not leave the PC.",
  "Metodo 4 - vatsal30": "Method 4 - vatsal30",
  "Metodo 4 disattivato dalle impostazioni.": "Method 4 turned off in the settings.",
  "Metodo {n}": "Method {n}",
  "Metti accanto al neo un righello o una moneta: serve per misurare il diametro.": "Place a ruler or a coin next to the mole: it is used to measure the diameter.",
  "Moderato": "Moderate",
  "Modifica data/misura": "Edit date/measurement",
  "Modifica foto": "Edit photo",
  "Modifica i dati nel Profilo": "Edit the data in the Profile",
  "Modifiche non salvate…": "Unsaved changes…",
  "Molte": "Many",
  "Molte efelidi (lentiggini)": "Many freckles (ephelides)",
  "Molte scottature con vesciche": "Many sunburns with blisters",
  "Molti nei o nei atipici: sorveglianza": "Many moles or atypical moles: surveillance",
  "Molto alto": "Very high",
  "Mostra affiancate": "Show side by side",
  "Mostra tutto il corpo": "Show the whole body",
  "NCCN": "NCCN",
  "NCCN Clinical Practice Guidelines in Oncology: Melanoma: Cutaneous (versione corrente; il testo completo richiede una registrazione gratuita)": "NCCN Clinical Practice Guidelines in Oncology: Melanoma: Cutaneous (current version; the full text requires free registration)",
  "Nei archiviati ({n})": "Archived moles ({n})",
  "Nei atipici": "Atypical moles",
  "Nei atipici (displastici)": "Atypical (dysplastic) moles",
  "Nei grandi, irregolari, di più colori: vanno seguiti nel tempo.": "Large, irregular, multicoloured moles: they should be followed over time.",
  "Neo archiviato. Lo trovi in fondo all'elenco.": "Mole archived. You will find it at the bottom of the list.",
  "Neo con foto": "Mole with photos",
  "Neo eliminato.": "Mole deleted.",
  "Neo non trovato.": "Mole not found.",
  "Neo salvato. Ora aggiungi la prima foto: sarà la tua \"foto storica\".": "Mole saved. Now add the first photo: it will be your \"baseline photo\".",
  "Neo {n}": "Mole {n}",
  "NeoTracker chiuso": "NeoTracker closed",
  "NeoTracker non risponde": "NeoTracker is not responding",
  "NeoTracker non è un dispositivo medico e non fa diagnosi.": "NeoTracker is not a medical device and does not make diagnoses.",
  "NeoTracker non è un servizio di consulenza genetica. Per una valutazione personale rivolgiti al dermatologo o a un centro di genetica oncologica.": "NeoTracker is not a genetic counselling service. For a personal assessment, see your dermatologist or an oncological genetics centre.",
  "NeoTracker non è uno strumento medico e non fa diagnosi. Per qualsiasi neo che cambia, sanguina, prude o ti preoccupa, rivolgiti a un dermatologo.": "NeoTracker is not a medical tool and does not make diagnoses. For any mole that changes, bleeds, itches or worries you, see a dermatologist.",
  "NeoTracker è chiuso": "NeoTracker is closed",
  "Neri": "Black",
  "Nessun allarme dai modelli": "No alarm from the models",
  "Nessun articolo trovato.": "No articles found.",
  "Nessun metodo ha prodotto un risultato: controlla i motivi indicati sotto.": "No method produced a result: check the reasons listed below.",
  "Nessun neo ancora": "No moles yet",
  "Nessun risultato": "No result",
  "Nessuna": "None",
  "Nessuna città trovata con questo nome.": "No city found with this name.",
  "Nessuna foto ancora registrata.": "No photo recorded yet.",
  "Nessuna foto: aggiungi la prima": "No photos: add the first one",
  "Nessuna immagine impostata.": "No image set.",
  "Nessuna protezione particolare per le attività normali; occhiali da sole nelle giornate luminose.": "No special protection needed for normal activities; sunglasses on bright days.",
  "Nessuno dei metodi che hanno risposto segnala la lesione come sospetta. Questo NON esclude un melanoma: gli strumenti non sono validati clinicamente e sbagliano anche in questa direzione. Se il neo è asimmetrico, ha bordi irregolari, colori diversi, è più grande di 6 mm o è cambiato nel tempo, la visita resta necessaria.": "None of the methods that responded flags the lesion as suspicious. This does NOT rule out a melanoma: the tools are not clinically validated and are also wrong in this direction. If the mole is asymmetric, has irregular borders, several colours, is larger than 6 mm or has changed over time, a visit is still needed.",
  "No": "No",
  "Nome": "Name",
  "Nome del neo": "Mole name",
  "Nome della città": "City name",
  "Nome o soprannome": "Name or nickname",
  "Non ancora scansionata.": "Not scanned yet.",
  "Non ancora scansionato": "Not scanned yet",
  "Non cambiano il risultato delle reti neurali, che guardano solo i pixel della foto. Servono a: (1) dare un contesto al rischio, (2) scegliere la letteratura scientifica adatta a te, (3) verificare i criteri per la consulenza genetica, (4) calcolare quanto tempo puoi stare al sole prima di scottarti. Tutto resta sul tuo computer.": "They do not change the result of the neural networks, which only look at the pixels of the photo. They are used to: (1) put the risk in context, (2) choose the scientific literature suited to you, (3) check the criteria for genetic counselling, (4) calculate how long you can stay in the sun before burning. Everything stays on your computer.",
  "Non ci sono nei da stampare.": "There are no moles to print.",
  "Non consentito.": "Not allowed.",
  "Non indicato": "Not specified",
  "Non lo so: lascia vuoto, puoi tornare più tardi.": "I don't know: leave it empty, you can come back later.",
  "Non riesci? Stima dall'indirizzo internet": "Can't do it? Estimate from the internet address",
  "Non riesco a contattare NeoTracker. Il programma potrebbe essere stato chiuso: riaprilo dall'icona sul Desktop.": "I cannot reach NeoTracker. The program may have been closed: reopen it from the icon on the Desktop.",
  "Non riesco a leggere questa immagine. Prova con un JPG o un PNG.": "I cannot read this image. Try a JPG or a PNG.",
  "Non riesco a ridurre questa immagine.": "I cannot reduce this image.",
  "Non so": "Don't know",
  "Non soddisfatto": "Not met",
  "Non trovo melanoma_batch.py: deve stare nella stessa cartella di neotracker.py (oppure in {CARTELLA_REPO}).": "I cannot find melanoma_batch.py: it must be in the same folder as neotracker.py (or in {CARTELLA_REPO}).",
  "Nonni, zii, nipoti (2° grado).": "Grandparents, aunts and uncles, nieces and nephews (2nd degree).",
  "Note": "Notes",
  "Note sul neo…": "Notes on the mole…",
  "Note:": "Notes:",
  "Nuca e collo": "Nape and neck",
  "Nulla viene inviato online, tranne le richieste che attivi tu (meteo UV, letteratura PubMed, SkinSense).": "Nothing is sent online, except the requests you turn on (UV weather, PubMed literature, SkinSense).",
  "Numero di nei": "Number of moles",
  "Nuovo neo": "New mole",
  "Nuovo utente": "New user",
  "OMS/OMM/UNEP/ICNIRP - Global Solar UV Index: A Practical Guide (2002)": "WHO/WMO/UNEP/ICNIRP - Global Solar UV Index: A Practical Guide (2002)",
  "Occhi": "Eyes",
  "Occhi chiari": "Light-coloured eyes",
  "Oggi i raggi UV sono bassi": "UV rays are low today",
  "Oggi i raggi UV sono dannosi per pelle non protetta": "UV rays are harmful to unprotected skin today",
  "Oggi i raggi UV sono molto dannosi": "UV rays are very harmful today",
  "One Call {n}: {t}": "One Call {n}: {t}",
  "Open-Meteo (predefinita)": "Open-Meteo (default)",
  "OpenWeather ha rifiutato la chiave (401): controlla che sia corretta e che sul tuo account sia attivo l'abbonamento 'One Call API' (pagamento a chiamata, 1.000 chiamate al giorno gratuite). Dopo l'iscrizione la chiave può impiegare qualche minuto ad attivarsi.": "OpenWeather rejected the key (401): check that it is correct and that the 'One Call API' plan (pay per call, 1,000 free calls per day) is active on your account. After subscribing, the key can take a few minutes to activate.",
  "OpenWeather non disponibile ({e}). Mostro i dati di Open-Meteo.": "OpenWeather unavailable ({e}). Showing Open-Meteo data.",
  "OpenWeather: limite di chiamate raggiunto (429).": "OpenWeather: call limit reached (429).",
  "Operazione non consentita su questo indirizzo.": "Operation not allowed on this address.",
  "Orecchio destro": "Ear, right",
  "Orecchio sinistro": "Ear, left",
  "Origine non ammessa.": "Origin not allowed.",
  "Pagina non trovata.": "Page not found.",
  "Parente di primo grado con melanoma": "First-degree relative with melanoma",
  "Parenti con astrocitoma (tumore del cervello)": "Relatives with astrocytoma (brain tumour)",
  "Parenti con carcinoma del rene": "Relatives with kidney carcinoma",
  "Parenti con melanoma dell'occhio (uveale)": "Relatives with melanoma of the eye (uveal)",
  "Parenti con mesotelioma": "Relatives with mesothelioma",
  "Parenti con tumore del pancreas (in tutto)": "Relatives with pancreatic cancer (in total)",
  "Parenti di 1° grado con melanoma": "1st-degree relatives with melanoma",
  "Passa il puntatore sul corpo per vedere la zona": "Move the pointer over the body to see the area",
  "Pelle che scotta facilmente e si abbronza poco.": "Skin that burns easily and tans little.",
  "Pelle chiara-olivastra. Scotta a volte, si abbronza gradualmente.": "Fair-olive skin. Sometimes burns, tans gradually.",
  "Pelle chiara. Scotta facilmente, si abbronza poco.": "Fair skin. Burns easily, tans little.",
  "Pelle molto chiara. Scotta sempre, non si abbronza mai (spesso capelli rossi, lentiggini).": "Very fair skin. Always burns, never tans (often red hair, freckles).",
  "Pelle molto scura. Non scotta.": "Very dark skin. Does not burn.",
  "Pelle olivastra. Scotta poco, si abbronza facilmente.": "Olive skin. Burns little, tans easily.",
  "Pelle scura. Scotta raramente.": "Dark skin. Rarely burns.",
  "Per chiudere NeoTracker basta chiudere questa finestra con la X in alto a destra: il programma si spegne da solo.": "To close NeoTracker, just close this window with the X at the top right: the program shuts down by itself.",
  "Per confermare scrivi:": "To confirm, type:",
  "Per eliminare scrivi il nome esatto dell'utente nella conferma.": "To delete, type the exact name of the user in the confirmation.",
  "Per le linee guida NCCN, in un melanoma invasivo con un parente di primo grado con tumore del pancreas è raccomandato un pannello multigene che includa CDKN2A.": "According to the NCCN guidelines, in an invasive melanoma with a first-degree relative with pancreatic cancer, a multigene panel that includes CDKN2A is recommended.",
  "Per stimare la città il programma contatta il servizio gratuito ipwho.is, che vede il tuo indirizzo internet. La precisione è quella della città (a volte sbaglia). Procedo?": "To estimate the city, the program contacts the free service ipwho.is, which sees your internet address. Accuracy is at city level (it is sometimes wrong). Proceed?",
  "Per vedere quanto sole ti scotta, indica il fototipo nel": "To see how much sun burns you, enter your phototype in the",
  "Permesso negato. Puoi cercare la città per nome oppure usare la stima da indirizzo internet.": "Permission denied. You can search for the city by name or use the estimate from the internet address.",
  "Piede destro": "Foot, right",
  "Piede sinistro": "Foot, left",
  "Pillow non installato: le anteprime useranno le foto originali (installa con «py -m pip install pillow»).": "Pillow is not installed: previews will use the original photos (install with «py -m pip install pillow»).",
  "Più colori nello stesso neo (marrone, nero, rosso, blu, bianco).": "Several colours in the same mole (brown, black, red, blue, white).",
  "Più di 6 mm (ma esistono melanomi più piccoli).": "More than 6 mm (but smaller melanomas exist).",
  "Più tumori dello spettro BAP1 (melanoma uveale, mesotelioma, carcinoma renale, melanoma cutaneo)": "Multiple BAP1-spectrum tumours (uveal melanoma, mesothelioma, renal carcinoma, cutaneous melanoma)",
  "Poche": "A few",
  "Polpaccio destro": "Calf, right",
  "Polpaccio sinistro": "Calf, left",
  "Posizione": "Location",
  "Posizione aggiornata.": "Location updated.",
  "Posizione aggiornata: {regione}.": "Location updated: {regione}.",
  "Posizione fuori dalla mappa.": "Location outside the map.",
  "Posizione impostata": "Location set",
  "Posizione non impostata": "Location not set",
  "Posizione non impostata: scegli una città o usa 'Rileva la mia posizione'.": "Location not set: choose a city or use 'Detect my location'.",
  "Posizione non valida.": "Invalid location.",
  "Posizione salvata: {nome}": "Location saved: {nome}",
  "Posizione stimata": "Estimated location",
  "Precauzioni extra: evita il sole nelle ore centrali, cerca l'ombra, copri la pelle, SPF 30+. La pelle non protetta si scotta in fretta.": "Extra precautions: avoid the sun in the middle of the day, seek shade, cover your skin, SPF 30+. Unprotected skin burns quickly.",
  "Preferisco non dirlo": "I prefer not to say",
  "Premi": "Press",
  "Preparo la scheda…": "Preparing the sheet…",
  "Prima": "Before",
  "Prima di cominciare": "Before you start",
  "Prima salva una chiave OpenWeather.": "Save an OpenWeather key first.",
  "Principale gene di predisposizione ad alta penetranza. Varianti germinali nel 20-40% delle famiglie con melanoma; associato anche a tumore del pancreas, melanomi multipli ed esordio precoce.": "Main high-penetrance predisposition gene. Germline variants in 20–40% of families with melanoma; also associated with pancreatic cancer, multiple melanomas and early onset.",
  "Profilo": "Profile",
  "Profilo da completare": "Profile to complete",
  "Profilo di {nome}": "Profile of {nome}",
  "Profilo non compilato.": "Profile not filled in.",
  "Profilo non valido.": "Invalid profile.",
  "Programma di analisi (melanoma_batch.py) non trovato: le foto si salvano ma non si possono analizzare.": "Analysis program (melanoma_batch.py) not found: photos are saved but cannot be analysed.",
  "Programma di analisi:": "Analysis program:",
  "Promemoria ABCDE": "ABCDE reminder",
  "Promemoria ABCDE per riconoscere un neo": "ABCDE reminder for recognising a mole",
  "Prossime {n} ore": "Next {n} hours",
  "Protezione consigliata: ombra nelle ore centrali, cappello, occhiali e crema solare.": "Protection recommended: shade in the middle of the day, hat, sunglasses and sunscreen.",
  "Protezione necessaria: riduci l'esposizione tra le 10 e le 16, crema solare SPF 30+, cappello e occhiali.": "Protection necessary: reduce exposure between 10 and 16, SPF 30+ sunscreen, hat and sunglasses.",
  "Protezione non necessaria per le attività normali (attenzione a neve, acqua, quota).": "Protection not needed for normal activities (beware of snow, water, altitude).",
  "Prova la chiave": "Test the key",
  "Provo la chiave…": "Testing the key…",
  "PubMed ha risposto con errore {code}": "PubMed responded with error {code}",
  "PubMed non raggiungibile (controlla la connessione internet)": "PubMed unreachable (check the internet connection)",
  "PubMed non è raggiungibile: mostro l'ultima ricerca salvata il {data}.": "PubMed is unreachable: showing the last saved search from {data}.",
  "PubMed {pmid} · abstract non disponibile": "PubMed {pmid} · abstract not available",
  "PubMed è un servizio della National Library of Medicine. Gli abstract sono mostrati per consultazione personale, in inglese; per il testo completo apri l'articolo sul sito della rivista.": "PubMed is a service of the National Library of Medicine. Abstracts are shown for personal consultation, in English; for the full text, open the article on the journal's website.",
  "Puoi chiudere questa finestra. Per riaprirlo usa l'icona «NeoTracker» sul Desktop.": "You can close this window. To reopen the program, use the «NeoTracker» icon on the Desktop.",
  "Puoi continuare a usare l'app. Se chiudi la finestra l'analisi non va persa: il programma finisce il lavoro e poi si spegne da solo.": "You can keep using the app. If you close the window the analysis is not lost: the program finishes the work and then shuts down by itself.",
  "Puoi usare una tua foto, un disegno o un'icona. L'immagine viene ritagliata a quadrato e ridotta, resta solo su questo computer e non viene mai usata per l'analisi dei nei.": "You can use your own photo, a drawing or an icon. The image is cropped to a square and reduced, stays only on this computer and is never used for mole analysis.",
  "Qualche volta": "Sometimes",
  "Qualcosa non ha funzionato": "Something went wrong",
  "Quando l'hai notato, se prude, se è cambiato…": "When you noticed it, whether it itches, whether it has changed…",
  "Quanti nei hai sul corpo, circa?": "Roughly how many moles do you have on your body?",
  "Quanto sono affidabili app e intelligenza artificiale": "How reliable are apps and artificial intelligence",
  "Questa foto non è ancora stata analizzata. L'analisi confronta più metodi sulla stessa immagine e ti dice cosa ha risposto ciascuno.": "This photo has not been analysed yet. The analysis compares several methods on the same image and tells you what each one answered.",
  "Questa scheda raccoglie dati inseriti dalla persona e foto da lei scattate. I risultati dell'analisi automatica sono sperimentali, non sono una diagnosi e non sostituiscono la visita dermatologica o la dermoscopia.": "This sheet collects data entered by the person and photos taken by them. The results of the automatic analysis are experimental, are not a diagnosis and do not replace a dermatological visit or dermoscopy.",
  "Questo browser non offre la geolocalizzazione: cerca la città per nome.": "This browser does not offer geolocation: search for the city by name.",
  "Questo metodo prevede l'invio dei pixel della foto (non dei metadati) a un server esterno.": "This method sends the pixels of the photo (not the metadata) to an external server.",
  "Questo programma ti aiuta a tenere traccia dei tuoi nei nel tempo: li segni su una mappa del corpo, ne conservi le foto con la data e li fai analizzare da più metodi. Inizia creando il tuo utente.": "This program helps you keep track of your moles over time: you mark them on a body map, keep their photos with the date and have them analysed by several methods. Start by creating your user.",
  "Questo rapporto NON è una diagnosi. I programmi usati sono prototipi di ricerca, non dispositivi medici.": "This report is NOT a diagnosis. The programs used are research prototypes, not medical devices.",
  "RETRO": "BACK",
  "Rapporto completo (testo)": "Full report (text)",
  "Rapporto completo (testo, in italiano)": "Full report (text, in Italian)",
  "Raro": "Rare",
  "Regione lombare destra": "Lower back, right",
  "Regione lombare sinistra": "Lower back, left",
  "Regione scapolare destra": "Shoulder blade area, right",
  "Regione scapolare sinistra": "Shoulder blade area, left",
  "Retro": "Back",
  "Revisione": "Review",
  "Revisione sistematica": "Systematic review",
  "Revisioni sul melanoma familiare (CDKN2A, CDK4)": "Reviews on familial melanoma (CDKN2A, CDK4)",
  "Rianalizza": "Re-analyse",
  "Richiesta non autorizzata.": "Unauthorised request.",
  "Richiesta troppo grande.": "Request too large.",
  "Riconoscere un neo sospetto": "Recognising a suspicious mole",
  "Riduci": "Zoom out",
  "Rifà la ricerca ignorando i risultati salvati": "Repeat the search ignoring the saved results",
  "Rileva la mia posizione": "Detect my location",
  "Rimuovere la chiave?": "Remove the key?",
  "Rimuovi": "Remove",
  "Rinomina": "Rename",
  "Rinomina utente": "Rename user",
  "Ripristina": "Restore",
  "Riprova": "Try again",
  "Rischio associato": "Associated risk",
  "Rossi": "Red",
  "Rotella = zoom · trascina = sposta · doppio clic = ingrandisci": "Wheel = zoom · drag = move · double click = enlarge",
  "Ruolo e letteratura": "Role and literature",
  "S": "L",
  "Salva": "Save",
  "Salva foto": "Save photo",
  "Salva neo": "Save mole",
  "Salvataggio…": "Saving…",
  "Salvato ✓": "Saved ✓",
  "Scansiona la letteratura": "Scan the literature",
  "Scansiona la letteratura sui geni": "Scan the literature on genes",
  "Scansione completata.": "Scan complete.",
  "Scarico l'indice UV…": "Downloading the UV index…",
  "Scatta sempre dalla stessa angolazione e salva l'originale, senza filtri.": "Always shoot from the same angle and keep the original, without filters.",
  "Scegli dove ti trovi per vedere l'indice UV di oggi.": "Choose where you are to see today's UV index.",
  "Scegli il tuo profilo: ogni persona ha la propria mappa dei nei, le proprie foto e i propri dati.": "Choose your profile: each person has their own mole map, photos and data.",
  "Scegli immagine…": "Choose image…",
  "Scegli la città qui sopra: poi vedrai l'indice UV di oggi, ora per ora.": "Choose the city above: then you will see today's UV index, hour by hour.",
  "Scegli un file immagine (JPG, PNG, WEBP o BMP).": "Choose an image file (JPG, PNG, WEBP or BMP).",
  "Scegli un utente e indica il suo fototipo per vedere quanti minuti servono per scottarsi.": "Choose a user and enter their phototype to see how many minutes it takes to burn.",
  "Scegli un'immagine personale": "Choose a personal picture",
  "Scegli utente": "Choose user",
  "Scelti per te (in base a profilo e sede dei nei)": "Picked for you (based on profile and mole locations)",
  "Scheda dei nei – {nome}": "Mole sheet – {nome}",
  "Scheda per il dermatologo": "Sheet for the dermatologist",
  "Schiena (zona media) destra": "Back (middle area), right",
  "Schiena (zona media) sinistra": "Back (middle area), left",
  "Scottature": "Sunburns",
  "Scottature con vesciche (soprattutto da bambino o ragazzo)": "Sunburns with blisters (especially as a child or teenager)",
  "Scrivi almeno 3 caratteri.": "Type at least 3 characters.",
  "Scrivi un nome.": "Type a name.",
  "Scuri": "Dark",
  "Se hai dubbi sul fototipo, pensa a come reagisce la tua pelle alla prima esposizione intensa al sole in estate, senza protezione.": "If you are unsure about your phototype, think about how your skin reacts to the first intense sun exposure in summer, without protection.",
  "Se i metodi sono in disaccordo è normale: significa solo che nessuno di loro è affidabile da solo.": "It is normal for the methods to disagree: it only means that none of them is reliable on its own.",
  "Se inserisci dati o foto di altre persone, assicurati di avere il loro consenso.": "If you enter data or photos of other people, make sure you have their consent.",
  "Se sta ancora analizzando una foto, finisce prima l'analisi e poi si spegne. Il pulsante qui sotto fa la stessa cosa.": "If it is still analysing a photo, it finishes the analysis first and then shuts down. The button below does the same thing.",
  "Sede": "Site",
  "Sede (modificabile)": "Site (editable)",
  "Senza Pillow l'immagine deve essere un JPG/PNG sotto i 400 KB (la pagina la riduce da sola: riprova con la funzione 'Scegli immagine').": "Without Pillow the image must be a JPG/PNG under 400 KB (the page reduces it by itself: try again with the 'Choose image' function).",
  "Servono ombra, abiti, cappello e crema solare nelle ore centrali.": "Shade, clothing, a hat and sunscreen are needed in the middle of the day.",
  "Sesso": "Sex",
  "Sezione sconosciuta.": "Unknown section.",
  "Sezione {n} di {tot}…": "Section {n} of {tot}…",
  "Sezioni": "Sections",
  "Sindrome di predisposizione ai tumori BAP1: melanoma uveale, mesotelioma, carcinoma renale, melanoma cutaneo e nevi melanocitari atipici.": "BAP1 tumour predisposition syndrome: uveal melanoma, mesothelioma, renal carcinoma, cutaneous melanoma and atypical melanocytic naevi.",
  "Sindromico": "Syndromic",
  "SkinSense (servizio online)": "SkinSense (online service)",
  "SkinSense abilitato.": "SkinSense turned on.",
  "SkinSense disattivato.": "SkinSense turned off.",
  "SkinSense è attivo: la foto (senza metadati) verrà inviata a un servizio online.": "SkinSense is on: the photo (without metadata) will be sent to an online service.",
  "SkinSense è un servizio online di terzi: le foto dei tuoi nei verrebbero inviate via internet a un server che non controlliamo. Le foto sono dati sulla tua salute. Vuoi abilitarlo?": "SkinSense is a third-party online service: the photos of your moles would be sent over the internet to a server we do not control. The photos are data about your health. Do you want to enable it?",
  "Soddisfatto": "Met",
  "Soglie e colori della scala internazionale dell'OMS. Fonti:": "Thresholds and colours of the WHO international scale. Sources:",
  "Sono immunosoppresso/a (trapianto o terapie che abbassano le difese)": "I am immunosuppressed (transplant or therapies that lower the body's defences)",
  "Sono misure inserite da te: valgono se prese sempre allo stesso modo. Un neo che cresce o cambia è un buon motivo per farlo vedere al dermatologo; la linea a 6 mm è solo il riferimento classico dei criteri ABCDE.": "These are measurements you entered: they are valid if always taken the same way. A mole that grows or changes is a good reason to show it to your dermatologist; the 6 mm line is just the classic reference of the ABCDE criteria.",
  "Sono mostrate {n} foto su {tot}.": "Showing {n} photos out of {tot}.",
  "Sono presenti alcuni fattori di rischio: protezione solare accurata e autoesame regolare; un controllo dermatologico di base è una buona abitudine.": "Some risk factors are present: careful sun protection and regular self-examination; a basic dermatological check-up is a good habit.",
  "Sono presenti fattori di rischio rilevanti: è consigliato un controllo dermatologico periodico (la frequenza la decide il dermatologo) e l'autoesame regolare della pelle.": "Significant risk factors are present: periodic dermatological check-ups (the dermatologist decides how often) and regular skin self-examination are recommended.",
  "Soprattutto in infanzia e adolescenza.": "Especially in childhood and adolescence.",
  "Sovrapponi con cursore": "Overlay with slider",
  "Spalla destra": "Shoulder, right",
  "Spalla sinistra": "Shoulder, left",
  "Spento per impostazione predefinita: con gli altri metodi la foto non lascia mai questo computer.": "Off by default: with the other methods the photo never leaves this computer.",
  "Spesso": "Often",
  "Stampa la scheda di questo neo": "Print the sheet for this mole",
  "Stampa una scheda con tutti i nei": "Print a sheet with all the moles",
  "Stampata il {data} con NeoTracker": "Printed on {data} with NeoTracker",
  "Stato dell'installazione": "Installation status",
  "Stessa luce (luce del giorno, senza flash) e stessa distanza ogni volta, circa 10-15 cm.": "Same light (daylight, no flash) and same distance every time, about 10–15 cm.",
  "Stima dall'indirizzo internet": "Estimate from the internet address",
  "Storia familiare": "Family history",
  "Storia personale": "Personal history",
  "Storico fotografico": "Photo history",
  "Storico fotografico ({n})": "Photo history ({n})",
  "Studi più pertinenti": "Most relevant studies",
  "Studi più recenti sui geni di predisposizione": "Most recent studies on predisposition genes",
  "Studio clinico": "Clinical trial",
  "Studio osservazionale": "Observational study",
  "Studio randomizzato": "Randomised trial",
  "Sì": "Yes",
  "Sì, abilita": "Yes, enable",
  "Sì, negativo": "Yes, negative",
  "Sì, non informativo": "Yes, uninformative",
  "Sì, positivo": "Yes, positive",
  "Sì, stima la città": "Yes, estimate the city",
  "Telomerasi: varianti del promotore descritte in famiglie con melanoma.": "Telomerase: promoter variants described in families with melanoma.",
  "Test genetico": "Genetic test",
  "Test genetico già eseguito": "Genetic test already done",
  "Tipo": "Type",
  "Tipo di foto": "Photo type",
  "Tipo {n}": "Type {n}",
  "Torace destro": "Chest, right",
  "Torace sinistro": "Chest, left",
  "Tra le due foto sono passati {n} giorni.": "{n} days have passed between the two photos.",
  "Tra le due foto è passato {n} giorno.": "{n} day has passed between the two photos.",
  "Trascina il pallino sulla mappa per correggere la posizione; ingrandisci con la rotella per la massima precisione.": "Drag the dot on the map to correct the position; zoom in with the wheel for maximum precision.",
  "Trascina il pallino sulla mappa per spostarlo.": "Drag the dot on the map to move it.",
  "Trascina qui una foto oppure clicca per sceglierla": "Drag a photo here or click to choose one",
  "Troppi collegamenti aperti.": "Too many open connections.",
  "Tumore del pancreas": "Pancreatic cancer",
  "Tumori dello spettro BAP1 indicati: {bap1_spettro}. Criterio semplificato: il genetista usa criteri più completi.": "BAP1-spectrum tumours indicated: {bap1_spettro}. Simplified criterion: the geneticist uses more complete criteria.",
  "Tutti i dati restano su questo computer, nella cartella:": "All data stays on this computer, in the folder:",
  "UV moderati: serve protezione nelle ore centrali": "Moderate UV: protection needed in the middle of the day",
  "Ultima analisi automatica ({data}): {esito}. Strumento di ricerca, non diagnostico.": "Latest automatic analysis ({data}): {esito}. Research tool, not diagnostic.",
  "Un medico ti ha detto che hai nei atipici (displastici)?": "Has a doctor told you that you have atypical (dysplastic) moles?",
  "Un neo che cambia (forma, bordi, colore, dimensioni), sanguina, prude o ti preoccupa va mostrato a un dermatologo, qualunque cosa dica l'app. Il controllo periodico dal dermatologo resta insostituibile.": "A mole that changes (shape, borders, colour, size), bleeds, itches or worries you must be shown to a dermatologist, whatever the app says. Regular check-ups with the dermatologist remain irreplaceable.",
  "Un risultato positivo indica un rischio più alto, non la certezza di ammalarsi; un risultato negativo non azzera il rischio (molte famiglie non hanno una variante identificabile).": "A positive result indicates a higher risk, not certainty of becoming ill; a negative result does not remove the risk (many families have no identifiable variant).",
  "Una stima va bene.": "An estimate is fine.",
  "Uomo": "Man",
  "Usa anche SkinSense (servizio online)": "Also use SkinSense (online service)",
  "Usa la data scritta nella foto, se c'è": "Use the date written in the photo, if there is one",
  "Uso di lampade o lettini abbronzanti": "Use of tanning lamps or sunbeds",
  "Utente creato. Compila il profilo: serve a contestualizzare i risultati.": "User created. Fill in the profile: it helps put the results in context.",
  "Utente eliminato.": "User deleted.",
  "Utente non trovato.": "User not found.",
  "Vai alla sezione Genetica": "Go to the Genetics section",
  "Varianti comuni legate a capelli rossi e pelle chiara: aumentano il rischio di melanoma in modo moderato. Non è un test di routine: l'interpretazione è specialistica.": "Common variants linked to red hair and fair skin: they raise the melanoma risk moderately. Not a routine test: interpretation is specialist.",
  "Varianti rare concentrate nel codone 24: il quadro familiare è indistinguibile da quello di CDKN2A.": "Rare variants concentrated in codon 24: the family picture is indistinguishable from that of CDKN2A.",
  "Variazione:": "Change:",
  "Verdi": "Green",
  "Verranno cancellate per sempre la sua unica foto e i rapporti di analisi.": "Its only photo and the analysis reports will be deleted permanently.",
  "Verranno cancellate per sempre tutte le sue {n} foto e i rapporti di analisi.": "All its {n} photos and the analysis reports will be deleted permanently.",
  "Verranno cancellati per sempre il profilo, tutti i nei, tutte le foto e tutti i rapporti di questo utente. L'operazione non si può annullare.": "The profile, all moles, all photos and all reports of this user will be deleted permanently. This cannot be undone.",
  "Versione": "Version",
  "Versione dell'avviso non valida.": "Invalid notice version.",
  "Viso": "Face",
  "a cielo sereno e senza protezione, al picco di oggi la pelle può arrossarsi in": "in clear skies and without protection, at today's peak the skin may redden in",
  "aggiornato": "updated",
  "altro": "other",
  "assumo che le 2 uscite siano [benigno, maligno]; ordine non verificabile": "I assume the 2 outputs are [benign, malignant]; order cannot be verified",
  "attivo solo se lo abiliti qui sotto": "active only if you enable it below",
  "capelli biondi": "blond hair",
  "capelli castani": "brown hair",
  "capelli grigi o bianchi": "grey or white hair",
  "capelli neri": "black hair",
  "capelli rossi": "red hair",
  "carcinoma basocellulare, tumore della pelle": "basal cell carcinoma, a skin cancer",
  "carcinoma squamocellulare, tumore della pelle": "squamous cell carcinoma, a skin cancer",
  "cheratosi attinica, lesione pre-cancerosa": "actinic keratosis, a pre-cancerous lesion",
  "cheratosi seborroica, benigna": "seborrhoeic keratosis, benign",
  "circa {minuti} minuti": "about {minuti} minutes",
  "connessione non riuscita: {motivo}": "connection failed: {motivo}",
  "cuoio capelluto": "scalp",
  "dermoscopica": "dermoscopic",
  "donna": "woman",
  "dorso del piede": "top of the foot",
  "dorso della mano": "back of the hand",
  "e clicca sul punto esatto del corpo (ingrandisci con la rotella per essere più preciso).": "and click on the exact spot on the body (zoom in with the wheel to be more precise).",
  "e conferma l'email.": "and confirm the email.",
  "es. 4,5": "e.g. 4.5",
  "facoltativa: richiede una tua chiave personale": "optional: requires a personal key of your own",
  "foto normale": "normal photo",
  "fototipo {tipo}": "phototype {tipo}",
  "fronte": "front",
  "gratuita, senza account né chiave": "free, no account or key needed",
  "i metodi non concordano tra loro": "the methods do not agree with each other",
  "i modelli di App 1 non sono stati scaricati: sono ancora dei segnaposto Git LFS. Apri PowerShell nella cartella {cartella} e lancia 'git lfs pull', poi riprova.": "the App 1 models have not been downloaded: they are still Git LFS placeholders. Open PowerShell in the folder {cartella}, run 'git lfs pull', then try again.",
  "ieri": "yesterday",
  "il modello ha {n} uscite: significato sconosciuto": "the model has {n} outputs: meaning unknown",
  "impossibile avviare: {e}": "cannot start: {e}",
  "in {n} giorni.": "in {n} days.",
  "in {n} giorno.": "in {n} day.",
  "indirizzo del servizio non ammesso (serve https)": "service address not allowed (https required)",
  "indirizzo non ammesso (solo https)": "address not allowed (https only)",
  "interrotto dopo {minuti} minuti (tempo massimo)": "stopped after {minuti} minutes (maximum time)",
  "la foto non si apre come immagine ({tipo}): {dettaglio}": "the photo does not open as an image ({tipo}): {dettaglio}",
  "labbro": "lip",
  "le prime 1.000 chiamate al giorno sono gratuite, le successive si pagano. OpenWeather può chiedere una carta di pagamento per attivarlo: controlla le condizioni sul loro sito.": "the first 1,000 calls per day are free, later ones are charged. OpenWeather may ask for a payment card to activate it: check the conditions on their website.",
  "mai": "never",
  "mancano i pesi addestrati: nella cartella {cartella} non ci sono i file model_fold_0.bin ... model_fold_4.bin. Il repository non li contiene: vanno prodotti con train.py sul dataset SIIM-ISIC.": "the trained weights are missing: in the folder {cartella} there are no files model_fold_0.bin ... model_fold_4.bin. The repository does not contain them: they must be produced with train.py on the SIIM-ISIC dataset.",
  "media di {n} modelli; punteggio medio {media} (soglia 0)": "average of {n} models; mean score {media} (threshold 0)",
  "melanoma": "melanoma",
  "meno di 25": "fewer than 25",
  "molte": "many",
  "molte efelidi": "many freckles",
  "nel pannello": "in the panel",
  "nessun caso indicato": "no cases indicated",
  "nessun metodo ha segnalato il neo (questo non esclude un melanoma)": "no method flagged the mole (this does not rule out a melanoma)",
  "nessun risultato disponibile": "no result available",
  "nessuna efelide": "no freckles",
  "nevo, cioe' neo benigno": "naevus, i.e. a benign mole",
  "no": "no",
  "nome@esempio.it (facoltativa)": "name@example.com (optional)",
  "non riesco a preparare la foto in modo sicuro: {e}": "I cannot prepare the photo safely: {e}",
  "non so": "don't know",
  "occhi azzurri o grigi": "blue or grey eyes",
  "occhi scuri": "dark eyes",
  "occhi verdi": "green eyes",
  "oggi": "today",
  "oltre 2 ore (UV molto basso)": "over 2 hours (very low UV)",
  "orecchio": "ear",
  "pagina del servizio": "service page",
  "palmo della mano": "palm of the hand",
  "palpebra": "eyelid",
  "pianta del piede": "sole of the foot",
  "poche": "a few",
  "poche efelidi": "a few freckles",
  "posizione da indirizzo internet non disponibile": "location from internet address not available",
  "prob. melanoma {perc}": "melanoma prob. {perc}",
  "probabilita' di malignita' stimata dal modello: {pm}": "probability of malignancy estimated by the model: {pm}",
  "qualche volta": "sometimes",
  "retro": "back",
  "rilevante": "significant",
  "risposta illeggibile: {e}": "unreadable response: {e}",
  "risposta non valida dal servizio": "invalid response from the service",
  "risposta senza nome della lesione: {risposta}": "response without a lesion name: {risposta}",
  "risposta troppo grande": "response too large",
  "servizio non raggiungibile: {ultimo_errore}": "service unreachable: {ultimo_errore}",
  "sicurezza {perc}": "confidence {perc}",
  "sotto l'unghia (mano)": "under the nail (hand)",
  "sotto l'unghia (piede)": "under the nail (foot)",
  "spazio tra le dita": "between the fingers or toes",
  "spesso": "often",
  "studi su PubMed": "studies on PubMed",
  "sì": "yes",
  "sì, negativo": "yes, negative",
  "sì, non informativo": "yes, uninformative",
  "sì, positivo": "yes, positive",
  "tempo scaduto o rete non disponibile": "timed out or network unavailable",
  "tutti i metodi con risultato indicano un neo da attenzionare": "all methods with a result flag a mole that needs attention",
  "ukalwa / melanoma-detection (app Android)": "ukalwa / melanoma-detection (Android app)",
  "uomo": "man",
  "uscita letta come le 6 classi di pelle (non verificabile)": "output interpreted as the 6 skin classes (not verifiable)",
  "vatsal30 / Melanoma-Detection (PyTorch)": "vatsal30 / Melanoma-Detection (PyTorch)",
  "{avviso} Il servizio Open-Meteo non risponde ({e}).": "{avviso} The Open-Meteo service is not responding ({e}).",
  "{cosa} non può essere vuoto.": "{cosa} cannot be empty.",
  "{cosa} è troppo lungo (massimo {massimo} caratteri).": "{cosa} is too long (maximum {massimo} characters).",
  "{file_modello} e' ancora un segnaposto Git LFS: lancia 'git lfs pull' nella cartella {cartella}.": "{file_modello} is still a Git LFS placeholder: run 'git lfs pull' in the folder {cartella}.",
  "{file_pesi} e' ancora un segnaposto Git LFS: apri PowerShell nella cartella {cartella} e lancia 'git lfs pull'.": "{file_pesi} is still a Git LFS placeholder: open PowerShell in the folder {cartella} and run 'git lfs pull'.",
  "{foto} · ultima {quando}": "{foto} · last {quando}",
  "{giorno} ore {ora}: indice UV {uvi} ({categoria})": "{giorno} at {ora}: UV index {uvi} ({categoria})",
  "{nome} · {mb} MB · clicca per cambiare": "{nome} · {mb} MB · click to change",
  "{nome}: errore.": "{nome}: error.",
  "{nome}: il valore deve essere tra {minimo} e {massimo}.": "{nome}: the value must be between {minimo} and {massimo}.",
  "{nome}: inserisci un numero.": "{nome}: enter a number.",
  "{nome}: non disponibile.": "{nome}: not available.",
  "{n} altro/i parente/i con melanoma": "{n} other relative(s) with melanoma",
  "{n} anni": "{n} years",
  "{n} anni fa": "{n} years ago",
  "{n} anno": "{n} year",
  "{n} anno fa": "{n} year ago",
  "{n} articoli su melanoma e «{termine}»": "{n} articles on melanoma and «{termine}»",
  "{n} articoli trovati su PubMed · ricerca del {data}": "{n} articles found on PubMed · search of {data}",
  "{n} articoli trovati su PubMed · ricerca del {data} (salvata)": "{n} articles found on PubMed · search of {data} (saved)",
  "{n} con astrocitoma": "{n} with astrocytoma",
  "{n} con melanoma uveale": "{n} with uveal melanoma",
  "{n} con tumore del pancreas": "{n} with pancreatic cancer",
  "{n} file modello su 10": "{n} model files out of 10",
  "{n} file modello su 5": "{n} model files out of 5",
  "{n} foto": "{n} photo",
  "{n} foto in {giorni} (dal {da} al {a}).": "{n} photos in {giorni} (from {da} to {a}).",
  "{n} foto#pl": "{n} photos",
  "{n} giorni": "{n} days",
  "{n} giorni fa": "{n} days ago",
  "{n} giorno": "{n} day",
  "{n} mesi fa": "{n} months ago",
  "{n} metodi su {tot} hanno risposto": "{n} of {tot} methods responded",
  "{n} nei": "{n} moles",
  "{n} nei in questa scheda": "{n} moles on this sheet",
  "{n} neo": "{n} mole",
  "{n} neo in questa scheda": "{n} mole on this sheet",
  "{n} parente/i di primo grado con melanoma": "{n} first-degree relative(s) with melanoma",
  "{n} su {tot}: {et}": "{n} of {tot}: {et}",
  "{vista} · posizione {x}% da sinistra, {y}% dall'alto": "{vista} · position {x}% from the left, {y}% from the top",
  "È una stima prudente che usa la dose minima di eritema più bassa del tuo fototipo; con riflessi (acqua, neve, sabbia), quota o pelle già arrossata il tempo si accorcia.": "This is a cautious estimate that uses the lowest minimal erythema dose for your phototype; with reflections (water, snow, sand), altitude or already reddened skin the time is shorter.",
  "È uno strumento personale per organizzare le foto dei tuoi nei e confrontare nel tempo i risultati di alcuni modelli di ricerca. Non è certificato né approvato da alcuna autorità sanitaria.": "It is a personal tool for organising the photos of your moles and comparing over time the results of some research models. It is not certified or approved by any health authority.",
  "…di cui di 1° grado": "…of which 1st-degree",
  "← Tutti i nei": "← All moles"
};
'''
WEB_FILES["/i18n_en.js"] = ("text/javascript; charset=utf-8", _WEB_I18N_EN_JS.encode("utf-8"))

_WEB_I18N_ES_JS = r'''/* Traduzioni dell'interfaccia di NeoTracker: es. Chiave = testo italiano originale.
   I segnaposto {nome} vanno lasciati uguali. Controllo: python3 tools/traduzioni.py */
(window.NT_DIZIONARI = window.NT_DIZIONARI || {}).es = {
  "(licenza CC BY 4.0). Il servizio gratuito è per uso personale e non commerciale.": "(licencia CC BY 4.0). El servicio gratuito es para uso personal y no comercial.",
  "(ora locale del luogo)": "(hora local del lugar)",
  "(ricerca salvata del {data})": "(búsqueda guardada del {data})",
  "(senza titolo)": "(sin título)",
  "(vuoto)": "(vacío)",
  "({variazione} mm dalla foto precedente)": "({variazione} mm desde la foto anterior)",
  "1 foto del {data}, diametro {mm} mm.": "1 foto del {data}, diámetro {mm} mm.",
  "1 foto del {data}.": "1 foto del {data}.",
  "100 o più": "100 o más",
  "100 o più nei sul corpo": "100 o más lunares en el cuerpo",
  "3 = da qui l'OMS consiglia protezione": "3 = a partir de aquí la OMS recomienda protección",
  "3 o più melanomi primari nella stessa persona": "3 o más melanomas primarios en la misma persona",
  "A che cosa servono questi dati?": "¿Para qué sirven estos datos?",
  "Accesso non autorizzato.": "Acceso no autorizado.",
  "Accetto e continuo": "Aceptar y continuar",
  "Addome alto destro": "Abdomen superior derecho",
  "Addome alto sinistro": "Abdomen superior izquierdo",
  "Addome basso destro": "Abdomen inferior derecho",
  "Addome basso sinistro": "Abdomen inferior izquierdo",
  "Adesso": "Ahora",
  "Aggiorna": "Actualizar",
  "Aggiungi la prima foto: diventa la tua foto storica, e ogni foto successiva ne seguirà l'evoluzione.": "Añade la primera foto: será tu foto de referencia y cada foto posterior mostrará la evolución del lunar.",
  "Aggiungi neo": "Añadir lunar",
  "Aggiungi qui sotto la prima foto: sarà il punto di partenza per vedere se il neo cambia nel tempo.": "Añade abajo la primera foto: será el punto de partida para ver si el lunar cambia con el tiempo.",
  "Aggiungi una foto allo storico": "Añadir una foto al historial",
  "Alla sottoscrizione il limite giornaliero predefinito è di 2.000 chiamate: nella scheda «Billing plans» del tuo account puoi abbassarlo a 1.000, così non spendi nulla. NeoTracker ne usa poche (al massimo 4 ogni 10 minuti, solo quando apri la pagina Indice UV).": "Al suscribirte, el límite diario predeterminado es de 2.000 llamadas: en la pestaña «Billing plans» de tu cuenta puedes bajarlo a 1.000 para no gastar nada. NeoTracker usa pocas (como máximo 4 cada 10 minutos, solo cuando abres la página Índice UV).",
  "Almeno 3 diagnosi tra melanoma, tumore del pancreas e astrocitoma nella stessa linea familiare (tua inclusa)": "Al menos 3 diagnósticos entre melanoma, cáncer de páncreas y astrocitoma en la misma línea familiar (incluido el tuyo)",
  "Almeno un metodo (o un suo modello) segnala una lesione da attenzionare. Non è una diagnosi e questi strumenti sbagliano spesso, ma è un motivo in più per non rimandare la visita dermatologica e per portare questo rapporto.": "Al menos un método (o uno de sus modelos) señala una lesión que requiere atención. No es un diagnóstico y estas herramientas se equivocan con frecuencia, pero es un motivo más para no aplazar la visita al dermatólogo y llevar este informe.",
  "Alto": "Alto",
  "Alto (raro)": "Alto (raro)",
  "Alto (sindrome BAP1)": "Alto (síndrome BAP1)",
  "Altri parenti con melanoma": "Otros familiares con melanoma",
  "Altri tumori della pelle (basalioma, spinalioma)": "Otros cánceres de piel (carcinoma basocelular y espinocelular)",
  "Altro": "Otro",
  "Altro che vuoi ricordare (allergie, farmaci fotosensibilizzanti, …)": "Otra cosa que quieras recordar (alergias, medicamentos fotosensibilizantes, …)",
  "Analisi automatica": "Análisis automático",
  "Analisi delle foto": "Análisis de las fotos",
  "Analisi in corso…": "Análisis en curso…",
  "Analisi interrotta dopo {ore} ore (troppo lunga).": "Análisis interrumpido tras {ore} horas (demasiado largo).",
  "Analisi: da attenzionare": "Análisis: requiere atención",
  "Analizza questa foto": "Analizar esta foto",
  "Analizza subito con tutti i metodi installati": "Analizar ahora con todos los métodos instalados",
  "Anche la ricerca delle città usa Open-Meteo.": "La búsqueda de ciudades también usa Open-Meteo.",
  "Ancora nessuna foto": "Todavía no hay fotos",
  "Annulla": "Cancelar",
  "Anteprima": "Vista previa",
  "App 1 (DeborahAdedigba) - modelli TensorFlow": "App 1 (DeborahAdedigba) - modelos TensorFlow",
  "App per smartphone e rischio di cancro della pelle: accuratezza diagnostica": "Aplicaciones para smartphone y riesgo de cáncer de piel: precisión diagnóstica",
  "Apri la pagina «API keys» del tuo account e copia la chiave.": "Abre la página «API keys» de tu cuenta y copia la clave.",
  "Archivia (toglie dalla mappa, conserva i dati)": "Archivar (lo quita del mapa y conserva los datos)",
  "Articoli recenti e rilevanti su come riconoscere i nei sospetti, sull'affidabilità di app e intelligenza artificiale e sul melanoma ereditario. I risultati arrivano da PubMed, la banca dati pubblica della National Library of Medicine (USA).": "Artículos recientes y relevantes sobre cómo reconocer lunares sospechosos, la fiabilidad de las aplicaciones y la inteligencia artificial, y el melanoma hereditario. Los resultados proceden de PubMed, la base de datos pública de la National Library of Medicine (EE. UU.).",
  "Asimmetria": "Asimetría",
  "Aspetto": "Aspecto",
  "Associati a varianti del gene MC1R.": "Asociados a variantes del gen MC1R.",
  "Astrocitoma": "Astrocitoma",
  "Attenzione: non ho trovato l'ambiente .venv di App 1, uso il Python corrente.": "Atención: no encuentro el entorno .venv de la App 1; uso el Python actual.",
  "Aumenta: {voce}": "Aumentar: {voce}",
  "Autoesame della pelle": "Autoexploración de la piel",
  "Automatica (come il sistema)": "Automático (como el sistema)",
  "Avambraccio destro": "Antebrazo derecho",
  "Avambraccio sinistro": "Antebrazo izquierdo",
  "Avvertenze": "Advertencias",
  "Azzurri/grigi": "Azules/grises",
  "Basso": "Bajo",
  "Basso-moderato (comune)": "Bajo a moderado (frecuente)",
  "Benvenuto in NeoTracker": "Te damos la bienvenida a NeoTracker",
  "Biondi": "Rubios",
  "Bordi": "Bordes",
  "Braccio destro": "Brazo derecho",
  "Braccio sinistro": "Brazo izquierdo",
  "Cambia": "Cambiar",
  "Cambia immagine…": "Cambiar imagen…",
  "Cambia nel tempo: forma, colore, dimensione, rilievo, o compaiono prurito o sanguinamento.": "Cambia con el tiempo: forma, color, tamaño, relieve, o aparecen picor o sangrado.",
  "Cambia utente": "Cambiar de usuario",
  "Capelli": "Cabello",
  "Capelli rossi o biondi": "Cabello pelirrojo o rubio",
  "Carcinoma del rene": "Carcinoma de riñón",
  "Caricamento…": "Cargando…",
  "Cartella dei progetti:": "Carpeta de los proyectos:",
  "Cartella dei tuoi dati (da copiare per il backup):": "Carpeta con tus datos (cópiala para la copia de seguridad):",
  "Castani": "Castaños",
  "Caviglia destra": "Tobillo derecho",
  "Caviglia sinistra": "Tobillo izquierdo",
  "Cavo popliteo destro": "Hueco poplíteo derecho",
  "Cavo popliteo sinistro": "Hueco poplíteo izquierdo",
  "Centra sulla mappa": "Centrar en el mapa",
  "Cerca": "Buscar",
  "Cerca altro (es. \"ugly duckling sign\", \"nail melanoma\"…)": "Buscar otra cosa (p. ej. \"ugly duckling sign\", \"nail melanoma\"…)",
  "Cerca nella letteratura": "Buscar en la literatura",
  "Cerca una città (es. Torino)": "Busca una ciudad (p. ej. Turín)",
  "Cerco su PubMed…": "Buscando en PubMed…",
  "Cerco…": "Buscando…",
  "Chi ha avuto un melanoma ha un rischio maggiore di un secondo.": "Haber tenido un melanoma aumenta el riesgo de un segundo.",
  "Chi ha tanti nei, nei atipici o una storia di melanoma dovrebbe proteggersi anche con indici moderati.": "Quien tiene muchos lunares, lunares atípicos o antecedentes de melanoma debe protegerse incluso con índices moderados.",
  "Chi sei?": "¿Quién eres?",
  "Chiave OpenWeather": "Clave de OpenWeather",
  "Chiave OpenWeather salvata ({finale}).": "Clave de OpenWeather guardada ({finale}).",
  "Chiave rimossa.": "Clave eliminada.",
  "Chiave salvata ({finale}) — scrivine una nuova per sostituirla": "Clave guardada ({finale}) — escribe una nueva para sustituirla",
  "Chiave salvata.": "Clave guardada.",
  "Chiedo la posizione al browser… (potrebbe comparire una richiesta di permesso)": "Pidiendo la posición al navegador… (puede aparecer una solicitud de permiso)",
  "Chiudere NeoTracker?": "¿Cerrar NeoTracker?",
  "Chiudere il programma": "Cerrar el programa",
  "Chiudi": "Cerrar",
  "Chiudi NeoTracker": "Cerrar NeoTracker",
  "Chiudi il programma": "Cerrar el programa",
  "Circa il 5-10% dei melanomi si presenta in famiglie con una predisposizione ereditaria (Leachman 2009). Qui trovi i criteri che usano gli specialisti per decidere se proporre una consulenza genetica, i geni coinvolti e la letteratura su ciascuno.": "Alrededor del 5-10 % de los melanomas aparecen en familias con una predisposición hereditaria (Leachman 2009). Aquí encuentras los criterios que usan los especialistas para decidir si proponer un asesoramiento genético, los genes implicados y la literatura sobre cada uno.",
  "Citato dalle linee guida NCCN tra i geni da considerare nei pannelli per melanoma (sindrome di Cowden).": "Citado por las guías del NCCN entre los genes a considerar en los paneles para melanoma (síndrome de Cowden).",
  "Classificati come cancerogeni certi per l'uomo (IARC).": "Clasificados como carcinógenos ciertos para el ser humano (IARC).",
  "Clic per vedere la foto originale a schermo intero": "Haz clic para ver la foto original a pantalla completa",
  "Clicca sul punto esatto del corpo dove si trova il neo (puoi ingrandire prima)": "Haz clic en el punto exacto del cuerpo donde está el lunar (puedes ampliar antes)",
  "Clicca un neo nell'elenco o sulla mappa per vedere lo storico fotografico.": "Haz clic en un lunar de la lista o del mapa para ver su historial fotográfico.",
  "Collo": "Cuello",
  "Colore": "Color",
  "Colore degli occhi": "Color de los ojos",
  "Colore naturale dei capelli (da giovane)": "Color natural del cabello (de joven)",
  "Come ottenere la chiave": "Cómo obtener la clave",
  "Come scattare foto confrontabili": "Cómo hacer fotos comparables",
  "Come si legge l'indice UV": "Cómo se lee el índice UV",
  "Compila la familiarità nel Profilo": "Completa los antecedentes familiares en el Perfil",
  "Compila la sezione 'Familiarità' nel Profilo: senza quei dati non posso verificare i criteri.": "Completa la sección «Antecedentes familiares» del Perfil: sin esos datos no puedo comprobar los criterios.",
  "Con i dati inseriti non rientri nei criteri più usati. Il test genetico per il melanoma è indicato solo in una piccola minoranza di persone e non viene proposto di routine. Se la tua storia familiare cambia o hai dubbi, aggiorna il profilo e parlane col dermatologo.": "Con los datos introducidos no cumples los criterios más utilizados. La prueba genética para el melanoma solo está indicada en una pequeña minoría de personas y no se ofrece de forma rutinaria. Si cambian tus antecedentes familiares o tienes dudas, actualiza tu perfil y consúltalo con tu dermatólogo.",
  "Con i dati inseriti non risultano fattori di rischio noti. Completa il profilo se mancano informazioni.": "Con los datos introducidos no aparece ningún factor de riesgo conocido. Completa tu perfil si falta información.",
  "Con il tuo fototipo ({fototipo})": "Con tu fototipo ({fototipo})",
  "Con o senza test, per chi ha una storia familiare restano fondamentali la protezione dal sole, l'autoesame della pelle e i controlli dermatologici periodici.": "Con o sin prueba, para quien tiene antecedentes familiares siguen siendo fundamentales la protección solar, la autoexploración de la piel y las revisiones dermatológicas periódicas.",
  "Conferma": "Confirmar",
  "Confronta": "Comparar",
  "Confronta forma, bordi e colori: se noti differenze, mostra le foto al dermatologo.": "Compara la forma, los bordes y los colores: si notas diferencias, enseña las fotos al dermatólogo.",
  "Confronto tra due foto": "Comparación de dos fotos",
  "Consenso": "Consentimiento",
  "Conta anche il «brutto anatroccolo»: un neo diverso da tutti gli altri. I noduli che crescono rapidamente o sono duri al tatto vanno mostrati subito. Questo promemoria non sostituisce la visita.": "También cuenta el «patito feo»: un lunar distinto de todos los demás. Los nódulos que crecen rápidamente o son duros al tacto deben mostrarse de inmediato. Este recordatorio no sustituye la visita médica.",
  "Conta i parenti di sangue (non quelli acquisiti) dello stesso lato della famiglia, materno o paterno: è il criterio che usano i genetisti. Se non lo sai, chiedi a un familiare: queste informazioni sono molto utili.": "Cuenta los familiares de sangre (no los políticos) del mismo lado de la familia, materno o paterno: es el criterio que usan los genetistas. Si no lo sabes, pregunta a un familiar: esta información es muy útil.",
  "Conta solo i melanomi primari invasivi.": "Solo cuentan los melanomas primarios invasivos.",
  "Controllo lo stato…": "Comprobando el estado…",
  "Coordinate non valide.": "Coordenadas no válidas.",
  "Cosa fare": "Qué hacer",
  "Cosa sapere prima di un test genetico": "Qué saber antes de una prueba genética",
  "Coscia destra": "Muslo derecho",
  "Coscia sinistra": "Muslo izquierdo",
  "Crea un account gratuito su": "Crea una cuenta gratuita en",
  "Crea utente": "Crear usuario",
  "Criteri ABCDE e segno del 'brutto anatroccolo'": "Criterios ABCDE y signo del «patito feo»",
  "Criteri semplificati, a scopo informativo. Il test genetico riguarda una piccola minoranza di persone e non è un esame di routine: è lo specialista a decidere se e quale test proporre, di norma dopo una consulenza genetica e partendo, quando possibile, da un familiare che ha avuto la malattia.": "Criterios simplificados, solo a título informativo. La prueba genética afecta a una pequeña minoría de personas y no es un examen rutinario: corresponde al especialista decidir si se propone y qué prueba, normalmente tras un asesoramiento genético y, cuando es posible, partiendo de un familiar que haya tenido la enfermedad.",
  "Cuoio capelluto (testa)": "Cuero cabelludo (cabeza)",
  "Cursore di confronto": "Control deslizante de comparación",
  "D": "D",
  "D = destra del paziente · S = sinistra": "D = derecha del paciente · I = izquierda",
  "Da 50 a 99 nei sul corpo": "De 50 a 99 lunares en el cuerpo",
  "Da attenzionare": "Requiere atención",
  "Da rifotografare?": "¿Hay que volver a fotografiar?",
  "Dai un nome al neo e controlla la sede.": "Ponle un nombre al lunar y comprueba la zona.",
  "Data della foto troppo vecchia.": "La fecha de la foto es demasiado antigua.",
  "Data dello scatto": "Fecha de la toma",
  "Data di nascita": "Fecha de nacimiento",
  "Data di nascita fuori intervallo.": "Fecha de nacimiento fuera de rango.",
  "Data di nascita non valida (AAAA-MM-GG).": "Fecha de nacimiento no válida (AAAA-MM-DD).",
  "Data non valida: usa il formato AAAA-MM-GG.": "Fecha no válida: usa el formato AAAA-MM-DD.",
  "Dati della persona": "Datos de la persona",
  "Dati meteo e UV:": "Datos meteorológicos y de UV:",
  "Dati non validi (JSON).": "Datos no válidos (JSON).",
  "Dati non validi.": "Datos no válidos.",
  "Dati orari non disponibili": "Datos por horas no disponibles",
  "Dati personali": "Datos personales",
  "Deep learning e melanoma: revisioni sistematiche": "Aprendizaje profundo y melanoma: revisiones sistemáticas",
  "Dermoscopia e diagnosi precoce (revisioni)": "Dermatoscopia y diagnóstico precoz (revisiones)",
  "Dermoscopica": "Dermatoscópica",
  "Di qualsiasi grado di parentela.": "De cualquier grado de parentesco.",
  "Diagnosi totali indicate: {diagnosi}. Leachman 2009 considera melanoma e tumore del pancreas nei parenti di 1o e 2o grado dello stesso lato della famiglia; l'astrocitoma è incluso dalle linee guida NCCN.": "Diagnósticos totales indicados: {diagnosi}. Leachman 2009 considera el melanoma y el cáncer de páncreas en familiares de 1.er y 2.º grado del mismo lado de la familia; las guías del NCCN incluyen el astrocitoma.",
  "Diametro": "Diámetro",
  "Diametro (mm)": "Diámetro (mm)",
  "Diametro del neo nel tempo": "Diámetro del lunar a lo largo del tiempo",
  "Diametro misurato (mm)": "Diámetro medido (mm)",
  "Diametro nel tempo": "Diámetro a lo largo del tiempo",
  "Diametro:": "Diámetro:",
  "Diametro: da {da} a {a} mm.": "Diámetro: de {da} a {a} mm.",
  "Diametro: {diff} mm di differenza.": "Diámetro: {diff} mm de diferencia.",
  "Diminuisci: {voce}": "Disminuir: {voce}",
  "Donna": "Mujer",
  "Dopo": "Después",
  "Dove si trovano": "Dónde están",
  "Efelidi": "Pecas",
  "Efelidi (lentiggini)": "Pecas (efélides)",
  "Elenco di fattori noti dalla letteratura, non un punteggio validato: non stima la probabilità di ammalarsi.": "Lista de factores conocidos por la literatura, no una puntuación validada: no estima la probabilidad de enfermar.",
  "Elimina": "Eliminar",
  "Elimina definitivamente": "Eliminar definitivamente",
  "Elimina foto": "Eliminar foto",
  "Elimina questo neo e le sue foto": "Eliminar este lunar y sus fotos",
  "Eliminare questa foto?": "¿Eliminar esta foto?",
  "Eliminare «{nome}»?": "¿Eliminar «{nome}»?",
  "Email non valida.": "Correo electrónico no válido.",
  "Email per PubMed": "Correo electrónico para PubMed",
  "Email salvata.": "Correo electrónico guardado.",
  "Errore imprevisto: {e}": "Error inesperado: {e}",
  "Errore interno. I dettagli sono nel file neotracker.log nella cartella dei dati.": "Error interno. Los detalles están en el archivo neotracker.log de la carpeta de datos.",
  "Errore {codice}": "Error {codice}",
  "Esci dal programma": "Salir del programa",
  "Esiste già un utente con questo nome.": "Ya existe un usuario con este nombre.",
  "Esposizione al sole": "Exposición al sol",
  "Estremo": "Extremo",
  "Età": "Edad",
  "Età, sesso e fenotipo non cambiano l'uscita delle reti neurali: servono a mostrarti i fattori di rischio, a scegliere la letteratura, a valutare i criteri di genetica e a stimare il tempo di scottatura.": "La edad, el sexo y el fenotipo no cambian el resultado de las redes neuronales: sirven para mostrarte los factores de riesgo, elegir la literatura, evaluar los criterios de genética y estimar el tiempo hasta la quemadura solar.",
  "Evita il sole nelle ore centrali e proteggi bene la pelle.": "Evita el sol en las horas centrales del día y protege bien la piel.",
  "Evita l'esposizione diretta: la pelle non protetta può scottarsi in pochi minuti.": "Evita la exposición directa: la piel sin proteger puede quemarse en pocos minutos.",
  "Evoluzione": "Evolución",
  "FRONTE": "FRENTE",
  "Facoltativa": "Opcional",
  "Fajuyigbe D, Young AR. The impact of skin colour on human photobiological responses. Pigment Cell Melanoma Res 2016;29:607-18 (dose minima di eritema per fototipo)": "Fajuyigbe D, Young AR. The impact of skin colour on human photobiological responses. Pigment Cell Melanoma Res 2016;29:607-18 (dosis mínima de eritema por fototipo)",
  "Familiarità": "Antecedentes familiares",
  "Fattori di rischio indicati:": "Factores de riesgo indicados:",
  "Fattori di rischio presenti": "Factores de riesgo presentes",
  "Fenotipo: pelle, capelli, occhi": "Fenotipo: piel, cabello, ojos",
  "File della foto non trovato.": "No se encuentra el archivo de la foto.",
  "Fonte dell'indice UV cambiata.": "Fuente del índice UV cambiada.",
  "Fonte dell'indice UV non valida.": "Fuente del índice UV no válida.",
  "Fonte:": "Fuente:",
  "Fonti": "Fuentes",
  "Formato non supportato: servono JPG, PNG, WEBP o BMP.": "Formato no admitido: se necesita JPG, PNG, WEBP o BMP.",
  "Formato non supportato: servono JPG, PNG, WEBP o BMP. Le foto HEIC degli iPhone vanno convertite in JPG (impostazioni fotocamera: 'Più compatibile').": "Formato no admitido: se necesita JPG, PNG, WEBP o BMP. Las fotos HEIC del iPhone deben convertirse a JPG (ajustes de la cámara: «Más compatible»).",
  "Foto a fuoco, con il neo al centro e la pelle ben visibile (sposta i peli, se serve).": "Foto enfocada, con el lunar en el centro y la piel bien visible (aparta el vello si hace falta).",
  "Foto del {data}": "Foto del {data}",
  "Foto eliminata.": "Foto eliminada.",
  "Foto non trovata.": "Foto no encontrada.",
  "Foto normale": "Foto normal",
  "Foto normale (smartphone)": "Foto normal (smartphone)",
  "Foto originale": "Foto original",
  "Foto salvata ({data}).": "Foto guardada ({data}).",
  "Foto salvata ({data}, data letta dalla foto).": "Foto guardada ({data}, fecha leída de la foto).",
  "Fotografia sequenziale e monitoraggio dei nei nel tempo": "Fotografía secuencial y seguimiento de los lunares a lo largo del tiempo",
  "Fototipo": "Fototipo",
  "Fototipo (classificazione di Fitzpatrick)": "Fototipo (clasificación de Fitzpatrick)",
  "Fototipo chiaro (I-II)": "Fototipo claro (I-II)",
  "Fototipo, età e familiarità non cambiano il risultato delle reti neurali (guardano solo i pixel): servono a contestualizzare il rischio.": "El fototipo, la edad y los antecedentes familiares no cambian el resultado de las redes neuronales (solo miran los píxeles): sirven para contextualizar el riesgo.",
  "Fronte": "Frente",
  "Fronte e cuoio capelluto": "Frente y cuero cabelludo",
  "Gamba (stinco) destra": "Pierna (espinilla) derecha",
  "Gamba (stinco) sinistra": "Pierna (espinilla) izquierda",
  "Gene": "Gen",
  "Gene dei telomeri (complesso shelterin): varianti rare in famiglie con melanoma.": "Gen de los telómeros (complejo shelterina): variantes raras en familias con melanoma.",
  "Gene dei telomeri: varianti rare in alcune famiglie con melanoma.": "Gen de los telómeros: variantes raras en algunas familias con melanoma.",
  "Gene non presente nell'elenco.": "El gen no figura en la lista.",
  "Gene {n} di {tot} ({nome})…": "Gen {n} de {tot} ({nome})…",
  "Genetica": "Genética",
  "Genitori, fratelli o figli.": "Padres, hermanos o hijos.",
  "Genitori, fratelli, sorelle, figli.": "Padres, hermanos, hermanas, hijos.",
  "Ginocchio destro": "Rodilla derecha",
  "Ginocchio sinistro": "Rodilla izquierda",
  "Gli articoli sono scelti da una ricerca automatica e non sono stati valutati da NeoTracker: leggili con il tuo medico.": "Los artículos se eligen mediante una búsqueda automática y NeoTracker no los ha evaluado: léelos con tu médico.",
  "Gluteo destro": "Glúteo derecho",
  "Gluteo sinistro": "Glúteo izquierdo",
  "Gomito destro": "Codo derecho",
  "Gomito sinistro": "Codo izquierdo",
  "Grigi/bianchi": "Canosos/blancos",
  "Hai indicato di aver già eseguito un test genetico: porta il referto al dermatologo.": "Has indicado que ya te has hecho una prueba genética: lleva el informe al dermatólogo.",
  "Hai scelto OpenWeather ma manca la chiave (Impostazioni): mostro i dati di Open-Meteo.": "Has elegido OpenWeather pero falta la clave (Ajustes): muestro los datos de Open-Meteo.",
  "Hai scelto OpenWeather ma non c'è ancora una chiave: finché manca, il programma usa Open-Meteo.": "Has elegido OpenWeather pero aún no hay clave: mientras falte, el programa usa Open-Meteo.",
  "Ho avuto (o ho) uno di questi tumori:": "He tenido (o tengo) uno de estos cánceres:",
  "Ho avuto altri tumori della pelle (basalioma, spinalioma)": "He tenido otros cánceres de piel (carcinoma basocelular o espinocelular)",
  "Ho già fatto un test genetico per il melanoma?": "¿Me he hecho ya una prueba genética para el melanoma?",
  "Ho letto e capito queste avvertenze": "He leído y entendido estas advertencias",
  "Ho verificato la mia storia familiare (anche se la risposta è «nessuno»)": "He comprobado mis antecedentes familiares (aunque la respuesta sea «ninguno»)",
  "I dati (anche di salute) restano su questo computer. Escono solo le richieste che attivi tu: indice UV (coordinate approssimate), ricerche su PubMed (solo i termini cercati) e, solo se lo attivi, l'invio della foto a SkinSense.": "Tus datos (también los de salud) permanecen en este ordenador. Solo salen las solicitudes que activas tú: índice UV (coordenadas aproximadas), búsquedas en PubMed (solo los términos buscados) y, únicamente si lo activas, el envío de la foto a SkinSense.",
  "I dati inseriti rientrano in almeno un criterio descritto in letteratura. Ti consigliamo di parlarne con il dermatologo o con un medico genetista (consulenza genetica oncologica): sarà lo specialista a decidere se e quale test proporre, di norma dopo la consulenza e, quando possibile, partendo da un familiare affetto. Geni più citati dalle linee guida: {geni}. L'uso dei pannelli multigene è ancora oggetto di discussione tra gli specialisti: per questo conta la consulenza prima del test.": "Los datos introducidos cumplen al menos un criterio descrito en la literatura. Te aconsejamos hablarlo con tu dermatólogo o con un médico genetista (asesoramiento genético oncológico): será el especialista quien decida si se propone una prueba y cuál, normalmente tras el asesoramiento y, cuando sea posible, partiendo de un familiar afectado. Genes más citados por las guías: {geni}. El uso de paneles multigénicos sigue siendo objeto de debate entre los especialistas: por eso es importante el asesoramiento antes de la prueba.",
  "I geni più studiati": "Los genes más estudiados",
  "I metodi sono addestrati su fotografie diverse dalle tue: cambiare luce, distanza o fotocamera può cambiare la risposta.": "Los métodos están entrenados con fotografías distintas de las tuyas: cambiar la luz, la distancia o la cámara puede cambiar la respuesta.",
  "I numeri corrispondono alle schede seguenti. Sulla figura: a sinistra la vista frontale, a destra quella posteriore.": "Los números corresponden a las fichas siguientes. En la figura: a la izquierda la vista frontal, a la derecha la posterior.",
  "I raggi ultravioletti sono il principale fattore di rischio modificabile per il melanoma. Qui vedi quanto sono forti oggi dove ti trovi.": "Los rayos ultravioleta son el principal factor de riesgo modificable del melanoma. Aquí ves lo fuertes que son hoy donde te encuentras.",
  "I risultati sono stime sperimentali e possono sbagliare in entrambe le direzioni: un esito rassicurante non esclude un melanoma, un esito di attenzione non significa che ci sia.": "Los resultados son estimaciones experimentales y pueden equivocarse en ambos sentidos: un resultado tranquilizador no descarta un melanoma y un resultado de atención no significa que lo haya.",
  "I tuoi dati rispetto ai criteri": "Tus datos frente a los criterios",
  "I tuoi nei ({n})": "Tus lunares ({n})",
  "Identificativo di pagina non valido.": "Identificador de página no válido.",
  "Il computer non riesce a determinare la posizione. Cerca la città per nome.": "El ordenador no consigue determinar la posición. Busca la ciudad por su nombre.",
  "Il file non è un'immagine leggibile o è troppo grande.": "El archivo no es una imagen legible o es demasiado grande.",
  "Il file non è un'immagine leggibile, è danneggiato o ha troppi pixel (massimo {mp} megapixel).": "El archivo no es una imagen legible, está dañado o tiene demasiados píxeles (máximo {mp} megapíxeles).",
  "Il file è troppo grande (massimo 40 MB).": "El archivo es demasiado grande (máximo 40 MB).",
  "Il file è vuoto.": "El archivo está vacío.",
  "Il metodo 3 NON ha analizzato la foto: il progetto e' un prototipo senza modello. Il suo server si limita a ricevere l'immagine (nessuna rete neurale), quindi qualunque testo rassicurante mostri non deriva da un'analisi e non ha alcun valore.": "El método 3 NO ha analizado la foto: el proyecto es un prototipo sin modelo. Su servidor se limita a recibir la imagen (sin red neuronal), así que cualquier texto tranquilizador que muestre no procede de un análisis y no tiene ningún valor.",
  "Il metodo 5 e' un'app Android: non puo' girare dal PC. Installa l'APK sul telefono, inquadra il neo e annota a mano il risultato qui sotto.\nRisultato dell'app sul telefono: ______________________________": "El método 5 es una aplicación de Android: no puede funcionar en el PC. Instala el APK en el teléfono, enfoca el lunar y anota a mano el resultado más abajo.\nResultado de la aplicación en el teléfono: ______________________________",
  "Il metodo {n} ha detto che:": "El método {n} indicó:",
  "Il nome": "El nombre",
  "Il numero di nei è uno dei fattori di rischio più forti.": "El número de lunares es uno de los factores de riesgo más fuertes.",
  "Il programma si spegne. Un'analisi in corso viene interrotta. I dati restano salvati.": "El programa se apaga. Un análisis en curso se interrumpe. Los datos quedan guardados.",
  "Il risultato riguarda anche i familiari di sangue: per questo la consulenza prima e dopo il test è parte del percorso.": "El resultado afecta también a los familiares de sangre: por eso el asesoramiento antes y después de la prueba forma parte del proceso.",
  "Il servizio Open-Meteo non risponde ({e}).": "El servicio Open-Meteo no responde ({e}).",
  "Immagine personale": "Imagen personal",
  "Immagine personale salvata.": "Imagen personal guardada.",
  "Immagine rimossa.": "Imagen eliminada.",
  "Immunosoppressione (terapie, trapianto)": "Inmunosupresión (tratamientos, trasplante)",
  "Impostazioni": "Ajustes",
  "In coda (posizione {n})…": "En cola (posición {n})…",
  "In coda…": "En cola…",
  "In inglese": "En inglés",
  "Incolla la chiave qui sopra e premi «Prova la chiave». Dopo l'iscrizione la chiave può impiegare qualche minuto ad attivarsi. Il programma prova prima One Call 4.0 e, se la chiave è di un abbonamento più vecchio, One Call 3.0.": "Pega la clave arriba y pulsa «Probar la clave». Tras suscribirte, la clave puede tardar unos minutos en activarse. El programa prueba primero One Call 4.0 y, si la clave es de una suscripción más antigua, One Call 3.0.",
  "Incolla prima la chiave.": "Pega primero la clave.",
  "Incolla qui la chiave (32 lettere e numeri)": "Pega aquí la clave (32 letras y números)",
  "Indice UV": "Índice UV",
  "Indice UV di oggi": "Índice UV de hoy",
  "Indice UV non disponibile": "Índice UV no disponible",
  "Indice UV ora per ora nelle prossime 24 ore": "Índice UV hora a hora para las próximas 24 horas",
  "Indice UV: fonte dei dati": "Índice UV: fuente de los datos",
  "Indirizzo non ammesso.": "Dirección no permitida.",
  "Indirizzo sconosciuto.": "Dirección desconocida.",
  "Indirizzo troppo lungo.": "Dirección demasiado larga.",
  "Ingrandisci": "Ampliar",
  "Inguine destro": "Ingle derecha",
  "Inguine sinistro": "Ingle izquierda",
  "Inviare le foto a SkinSense?": "¿Enviar las fotos a SkinSense?",
  "Irregolari, frastagliati o sfumati.": "Irregulares, dentados o difuminados.",
  "Iscriviti all'abbonamento «One Call API» a pagamento per chiamata": "Suscríbete al plan «One Call API» de pago por llamada",
  "JPG, PNG, WEBP o BMP · fino a 60 MB": "JPG, PNG, WEBP o BMP · hasta 60 MB",
  "L'OMS consiglia di proteggersi a partire da un indice UV di 3.": "La OMS recomienda protegerse a partir de un índice UV de 3.",
  "L'analisi di questa foto è in corso: attendi che finisca.": "Se está analizando esta foto: espera a que termine.",
  "L'analisi non ha prodotto il rapporto. Ultime righe del log: {log}": "El análisis no generó el informe. Últimas líneas del registro: {log}",
  "L'analisi non è riuscita.": "El análisis no se completó.",
  "L'immagine supera {mb} MB.": "La imagen supera los {mb} MB.",
  "L'indice è una previsione: il valore reale dipende da nuvole, quota e riflessi.": "El índice es una previsión: el valor real depende de las nubes, la altitud y los reflejos.",
  "La chiave OpenWeather contiene caratteri non validi (di solito sono 32 lettere/numeri).": "La clave de OpenWeather contiene caracteres no válidos (normalmente son 32 letras/números).",
  "La chiave resta salvata solo sul tuo computer e non viene mai mostrata né inviata alla pagina web del programma: la usa il programma Python per chiamare OpenWeather.": "La clave se guarda solo en tu ordenador y nunca se muestra ni se envía a la página web del programa: la usa el programa Python para llamar a OpenWeather.",
  "La chiave sarà cancellata da questo computer. Potrai inserirla di nuovo quando vuoi.": "La clave se borrará de este ordenador. Podrás introducirla de nuevo cuando quieras.",
  "La data della foto non può essere nel futuro.": "La fecha de la foto no puede ser futura.",
  "La foto del {data} e il suo rapporto di analisi saranno cancellati per sempre.": "La foto del {data} y su informe de análisis se eliminarán para siempre.",
  "La foto resta sul tuo computer: SkinSense (servizio online) è disattivato.": "La foto permanece en tu ordenador: SkinSense (servicio en línea) está desactivado.",
  "La foto supera i {mb} MB: riducila o scegline un'altra.": "La foto supera los {mb} MB: redúcela o elige otra.",
  "La foto supera {MAX_MB_FOTO} MB.": "La foto supera los {MAX_MB_FOTO} MB.",
  "La libreria Pillow è vecchia e ha problemi di sicurezza noti: aggiornala con «py -m pip install -U pillow».": "La biblioteca Pillow es antigua y tiene problemas de seguridad conocidos: actualízala con «py -m pip install -U pillow».",
  "La mia posizione ({lat}; {lon})": "Mi ubicación ({lat}; {lon})",
  "La posizione resta salvata solo su questo computer; viene inviata al servizio meteo (coordinate arrotondate) per ottenere l'indice UV.": "La ubicación se guarda solo en este ordenador; se envía al servicio meteorológico (coordenadas redondeadas) para obtener el índice UV.",
  "La prima analisi può richiedere diversi minuti (i modelli vengono caricati in memoria).": "El primer análisis puede tardar varios minutos (los modelos se cargan en la memoria).",
  "La scelta vale per tutti gli utenti di questo computer. Il testo originale e vincolante delle avvertenze legali è quello italiano; il rapporto di testo completo resta in italiano.": "La elección vale para todos los usuarios de este ordenador. El texto original y vinculante de las advertencias legales es el italiano; el informe de texto completo se mantiene en italiano.",
  "La variante p.E318K aumenta il rischio di melanoma e di carcinoma renale e si associa a molti nei.": "La variante p.E318K aumenta el riesgo de melanoma y de carcinoma renal y se asocia a muchos lunares.",
  "La vista deve essere 'fronte' o 'retro'.": "La vista debe ser 'fronte' o 'retro'.",
  "Lampade": "Cabinas de bronceado",
  "Lampade abbronzanti": "Lámparas de bronceado",
  "Lampade o lettini abbronzanti": "Lámparas o camas solares de bronceado",
  "Lavoro o attività prolungata all'aperto": "Trabajo o actividad prolongada al aire libre",
  "Lavoro o faccio attività per molte ore all'aperto": "Trabajo o hago actividades al aire libre durante muchas horas",
  "Le due metà del neo non si somigliano.": "Las dos mitades del lunar no se parecen.",
  "Le informazioni su rischio, letteratura e genetica sono divulgative e non sostituiscono la consulenza di un medico o di un genetista.": "La información sobre riesgo, literatura y genética es divulgativa y no sustituye el asesoramiento de un médico o de un genetista.",
  "Le linee guida raccomandano il test solo dopo una selezione accurata dei candidati e un'adeguata consulenza (Rossi 2019); l'uso dei pannelli multigene è ancora discusso.": "Las guías recomiendan la prueba solo tras una selección cuidadosa de los candidatos y un asesoramiento adecuado (Rossi 2019); el uso de paneles multigénicos sigue siendo objeto de debate.",
  "Le nuvole sottili non fermano gran parte degli UV: l'indice può restare alto anche con il cielo velato.": "Las nubes finas no detienen gran parte de los UV: el índice puede seguir alto incluso con el cielo velado.",
  "Le ore centrali (circa 11-16) sono quelle con l'indice più alto.": "Las horas centrales (aproximadamente de 11 a 16) son las de índice más alto.",
  "Le ricerche partono da questo computer verso PubMed (nessun dato personale viene inviato). I risultati si salvano per 7 giorni.": "Las búsquedas salen de este ordenador hacia PubMed (no se envían datos personales). Los resultados se guardan durante 7 días.",
  "Le ricerche usano le E-utilities pubbliche di PubMed. NCBI chiede, per cortesia, un'email di contatto: è facoltativa e viene inviata solo a PubMed.": "Las búsquedas usan las E-utilities públicas de PubMed. El NCBI pide, por cortesía, un correo de contacto: es opcional y solo se envía a PubMed.",
  "Le sezioni «scelte per te» usano parole legate al tuo profilo (per esempio fototipo o numero di nei): se preferisci non inviarle, non scansionare quella sezione.": "Las secciones «elegidas para ti» usan palabras ligadas a tu perfil (por ejemplo el fototipo o el número de lunares): si prefieres no enviarlas, no explores esa sección.",
  "Leachman 2009 e 2017; NCCN": "Leachman 2009 y 2017; NCCN",
  "Leachman 2017; NCCN": "Leachman 2017; NCCN",
  "Leggi l'abstract": "Leer el resumen",
  "Lentigo maligna e melanoma del volto": "Lentigo maligna y melanoma de la cara",
  "Letteratura": "Literatura",
  "Letteratura scientifica": "Literatura científica",
  "Letteratura: PubMed": "Literatura: PubMed",
  "Linea guida": "Guía clínica",
  "Linee guida e criteri per il test genetico": "Guías y criterios para la prueba genética",
  "Lingua": "Idioma",
  "Lingua dell'interfaccia": "Idioma de la interfaz",
  "Lingua non supportata.": "Idioma no admitido.",
  "Lucas RM et al. Are current guidelines for sun protection optimal for health? Photochem Photobiol Sci 2018;17:1956-63 (UV Index e dose di eritema)": "Lucas RM et al. Are current guidelines for sun protection optimal for health? Photochem Photobiol Sci 2018;17:1956-63 (índice UV y dosis de eritema)",
  "Mai": "Nunca",
  "Manca la posizione": "Falta la ubicación",
  "Mano destra": "Mano derecha",
  "Mano sinistra": "Mano izquierda",
  "Mappa dei nei": "Mapa de lunares",
  "Mappa del corpo umano: fronte a sinistra, retro a destra": "Mapa del cuerpo humano: frente a la izquierda, espalda a la derecha",
  "Massimo di oggi": "Máximo de hoy",
  "Melanoma acrale (mani, piedi, unghie): dermoscopia": "Melanoma acral (manos, pies, uñas): dermatoscopia",
  "Melanoma dell'occhio (uveale)": "Melanoma del ojo (uveal)",
  "Melanoma e immunosoppressione": "Melanoma e inmunosupresión",
  "Melanoma ereditario": "Melanoma hereditario",
  "Melanoma ereditario e test genetico": "Melanoma hereditario y prueba genética",
  "Melanoma già diagnosticato": "Melanoma ya diagnosticado",
  "Melanoma nelle pelli scure (spesso acrale)": "Melanoma en pieles oscuras (a menudo acral)",
  "Melanoma personale e parente di primo grado con tumore del pancreas": "Melanoma propio y familiar de primer grado con cáncer de páncreas",
  "Melanoma-Detector (VukIG)": "Melanoma-Detector (VukIG)",
  "Melanomi già diagnosticati": "Melanomas ya diagnosticados",
  "Melanomi già diagnosticati a me": "Melanomas ya diagnosticados en mí",
  "Melanomi primari indicati: {mel_pers}.": "Melanomas primarios indicados: {mel_pers}.",
  "Meno di 25": "Menos de 25",
  "Mesotelioma": "Mesotelioma",
  "Meta-analisi": "Metaanálisis",
  "Metodi in disaccordo": "Métodos en desacuerdo",
  "Metodo 1 - App 1 (Deborah Adedigba)": "Método 1 - App 1 (Deborah Adedigba)",
  "Metodo 1 disattivato dalle impostazioni.": "Método 1 desactivado en los ajustes.",
  "Metodo 2 - SkinSense (servizio online)": "Método 2 - SkinSense (servicio en línea)",
  "Metodo 2 non eseguito (disattivato nelle impostazioni): la foto non e' uscita dal PC.": "Método 2 no ejecutado (desactivado en los ajustes): la foto no ha salido del PC.",
  "Metodo 4 - vatsal30": "Método 4 - vatsal30",
  "Metodo 4 disattivato dalle impostazioni.": "Método 4 desactivado en los ajustes.",
  "Metodo {n}": "Método {n}",
  "Metti accanto al neo un righello o una moneta: serve per misurare il diametro.": "Coloca una regla o una moneda junto al lunar: sirve para medir el diámetro.",
  "Moderato": "Moderado",
  "Modifica data/misura": "Editar fecha/medida",
  "Modifica foto": "Editar foto",
  "Modifica i dati nel Profilo": "Modificar los datos en el Perfil",
  "Modifiche non salvate…": "Cambios sin guardar…",
  "Molte": "Muchas",
  "Molte efelidi (lentiggini)": "Muchas pecas (efélides)",
  "Molte scottature con vesciche": "Muchas quemaduras solares con ampollas",
  "Molti nei o nei atipici: sorveglianza": "Muchos lunares o lunares atípicos: vigilancia",
  "Molto alto": "Muy alto",
  "Mostra affiancate": "Mostrar una al lado de la otra",
  "Mostra tutto il corpo": "Mostrar todo el cuerpo",
  "NCCN": "NCCN",
  "NCCN Clinical Practice Guidelines in Oncology: Melanoma: Cutaneous (versione corrente; il testo completo richiede una registrazione gratuita)": "NCCN Clinical Practice Guidelines in Oncology: Melanoma: Cutaneous (versión actual; el texto completo requiere registro gratuito)",
  "Nei archiviati ({n})": "Lunares archivados ({n})",
  "Nei atipici": "Lunares atípicos",
  "Nei atipici (displastici)": "Lunares atípicos (displásicos)",
  "Nei grandi, irregolari, di più colori: vanno seguiti nel tempo.": "Lunares grandes, irregulares y de varios colores: conviene seguirlos en el tiempo.",
  "Neo archiviato. Lo trovi in fondo all'elenco.": "Lunar archivado. Lo encontrarás al final de la lista.",
  "Neo con foto": "Lunar con fotos",
  "Neo eliminato.": "Lunar eliminado.",
  "Neo non trovato.": "Lunar no encontrado.",
  "Neo salvato. Ora aggiungi la prima foto: sarà la tua \"foto storica\".": "Lunar guardado. Ahora añade la primera foto: será tu «foto de referencia».",
  "Neo {n}": "Lunar {n}",
  "NeoTracker chiuso": "NeoTracker cerrado",
  "NeoTracker non risponde": "NeoTracker no responde",
  "NeoTracker non è un dispositivo medico e non fa diagnosi.": "NeoTracker no es un producto sanitario y no hace diagnósticos.",
  "NeoTracker non è un servizio di consulenza genetica. Per una valutazione personale rivolgiti al dermatologo o a un centro di genetica oncologica.": "NeoTracker no es un servicio de asesoramiento genético. Para una valoración personal, acude a tu dermatólogo o a un centro de genética oncológica.",
  "NeoTracker non è uno strumento medico e non fa diagnosi. Per qualsiasi neo che cambia, sanguina, prude o ti preoccupa, rivolgiti a un dermatologo.": "NeoTracker no es una herramienta médica y no hace diagnósticos. Ante cualquier lunar que cambie, sangre, pique o te preocupe, acude a un dermatólogo.",
  "NeoTracker è chiuso": "NeoTracker está cerrado",
  "Neri": "Negros",
  "Nessun allarme dai modelli": "Ninguna alarma de los modelos",
  "Nessun articolo trovato.": "No se han encontrado artículos.",
  "Nessun metodo ha prodotto un risultato: controlla i motivi indicati sotto.": "Ningún método ha producido un resultado: revisa los motivos indicados abajo.",
  "Nessun neo ancora": "Todavía no hay lunares",
  "Nessun risultato": "Sin resultado",
  "Nessuna": "Ninguna",
  "Nessuna città trovata con questo nome.": "No se ha encontrado ninguna ciudad con ese nombre.",
  "Nessuna foto ancora registrata.": "Todavía no hay ninguna foto registrada.",
  "Nessuna foto: aggiungi la prima": "Sin fotos: añade la primera",
  "Nessuna immagine impostata.": "No hay ninguna imagen establecida.",
  "Nessuna protezione particolare per le attività normali; occhiali da sole nelle giornate luminose.": "No hace falta protección especial para las actividades normales; gafas de sol los días luminosos.",
  "Nessuno dei metodi che hanno risposto segnala la lesione come sospetta. Questo NON esclude un melanoma: gli strumenti non sono validati clinicamente e sbagliano anche in questa direzione. Se il neo è asimmetrico, ha bordi irregolari, colori diversi, è più grande di 6 mm o è cambiato nel tempo, la visita resta necessaria.": "Ninguno de los métodos que han respondido señala la lesión como sospechosa. Esto NO descarta un melanoma: las herramientas no están validadas clínicamente y también se equivocan en este sentido. Si el lunar es asimétrico, tiene bordes irregulares, varios colores, mide más de 6 mm o ha cambiado con el tiempo, la visita sigue siendo necesaria.",
  "No": "No",
  "Nome": "Nombre",
  "Nome del neo": "Nombre del lunar",
  "Nome della città": "Nombre de la ciudad",
  "Nome o soprannome": "Nombre o apodo",
  "Non ancora scansionata.": "Aún sin explorar.",
  "Non ancora scansionato": "Aún sin explorar",
  "Non cambiano il risultato delle reti neurali, che guardano solo i pixel della foto. Servono a: (1) dare un contesto al rischio, (2) scegliere la letteratura scientifica adatta a te, (3) verificare i criteri per la consulenza genetica, (4) calcolare quanto tempo puoi stare al sole prima di scottarti. Tutto resta sul tuo computer.": "No cambian el resultado de las redes neuronales, que solo miran los píxeles de la foto. Sirven para: (1) dar un contexto al riesgo, (2) elegir la literatura científica adecuada para ti, (3) comprobar los criterios del asesoramiento genético, (4) calcular cuánto tiempo puedes estar al sol antes de quemarte. Todo permanece en tu ordenador.",
  "Non ci sono nei da stampare.": "No hay lunares que imprimir.",
  "Non consentito.": "No permitido.",
  "Non indicato": "No indicado",
  "Non lo so: lascia vuoto, puoi tornare più tardi.": "No lo sé: déjalo vacío, puedes volver más tarde.",
  "Non riesci? Stima dall'indirizzo internet": "¿No puedes? Estima desde la dirección de internet",
  "Non riesco a contattare NeoTracker. Il programma potrebbe essere stato chiuso: riaprilo dall'icona sul Desktop.": "No consigo contactar con NeoTracker. Puede que el programa se haya cerrado: vuelve a abrirlo desde el icono del Escritorio.",
  "Non riesco a leggere questa immagine. Prova con un JPG o un PNG.": "No puedo leer esta imagen. Prueba con un JPG o un PNG.",
  "Non riesco a ridurre questa immagine.": "No puedo reducir esta imagen.",
  "Non so": "No lo sé",
  "Non soddisfatto": "No cumplido",
  "Non trovo melanoma_batch.py: deve stare nella stessa cartella di neotracker.py (oppure in {CARTELLA_REPO}).": "No encuentro melanoma_batch.py: debe estar en la misma carpeta que neotracker.py (o en {CARTELLA_REPO}).",
  "Nonni, zii, nipoti (2° grado).": "Abuelos, tíos, sobrinos (2.º grado).",
  "Note": "Notas",
  "Note sul neo…": "Notas sobre el lunar…",
  "Note:": "Notas:",
  "Nuca e collo": "Nuca y cuello",
  "Nulla viene inviato online, tranne le richieste che attivi tu (meteo UV, letteratura PubMed, SkinSense).": "No se envía nada por internet, salvo las solicitudes que activas tú (meteorología UV, literatura de PubMed, SkinSense).",
  "Numero di nei": "Número de lunares",
  "Nuovo neo": "Lunar nuevo",
  "Nuovo utente": "Nuevo usuario",
  "OMS/OMM/UNEP/ICNIRP - Global Solar UV Index: A Practical Guide (2002)": "OMS/OMM/PNUMA/ICNIRP - Global Solar UV Index: A Practical Guide (2002)",
  "Occhi": "Ojos",
  "Occhi chiari": "Ojos claros",
  "Oggi i raggi UV sono bassi": "Hoy los rayos UV son bajos",
  "Oggi i raggi UV sono dannosi per pelle non protetta": "Hoy los rayos UV son dañinos para la piel sin proteger",
  "Oggi i raggi UV sono molto dannosi": "Hoy los rayos UV son muy dañinos",
  "One Call {n}: {t}": "One Call {n}: {t}",
  "Open-Meteo (predefinita)": "Open-Meteo (predeterminada)",
  "OpenWeather ha rifiutato la chiave (401): controlla che sia corretta e che sul tuo account sia attivo l'abbonamento 'One Call API' (pagamento a chiamata, 1.000 chiamate al giorno gratuite). Dopo l'iscrizione la chiave può impiegare qualche minuto ad attivarsi.": "OpenWeather ha rechazado la clave (401): comprueba que sea correcta y que en tu cuenta esté activa la suscripción «One Call API» (pago por llamada, 1.000 llamadas gratuitas al día). Tras suscribirte, la clave puede tardar unos minutos en activarse.",
  "OpenWeather non disponibile ({e}). Mostro i dati di Open-Meteo.": "OpenWeather no disponible ({e}). Muestro los datos de Open-Meteo.",
  "OpenWeather: limite di chiamate raggiunto (429).": "OpenWeather: límite de llamadas alcanzado (429).",
  "Operazione non consentita su questo indirizzo.": "Operación no permitida en esta dirección.",
  "Orecchio destro": "Oreja derecha",
  "Orecchio sinistro": "Oreja izquierda",
  "Origine non ammessa.": "Origen no permitido.",
  "Pagina non trovata.": "Página no encontrada.",
  "Parente di primo grado con melanoma": "Familiar de primer grado con melanoma",
  "Parenti con astrocitoma (tumore del cervello)": "Familiares con astrocitoma (tumor cerebral)",
  "Parenti con carcinoma del rene": "Familiares con carcinoma de riñón",
  "Parenti con melanoma dell'occhio (uveale)": "Familiares con melanoma del ojo (uveal)",
  "Parenti con mesotelioma": "Familiares con mesotelioma",
  "Parenti con tumore del pancreas (in tutto)": "Familiares con cáncer de páncreas (en total)",
  "Parenti di 1° grado con melanoma": "Familiares de 1.er grado con melanoma",
  "Passa il puntatore sul corpo per vedere la zona": "Pasa el puntero sobre el cuerpo para ver la zona",
  "Pelle che scotta facilmente e si abbronza poco.": "Piel que se quema con facilidad y se broncea poco.",
  "Pelle chiara-olivastra. Scotta a volte, si abbronza gradualmente.": "Piel clara-aceitunada. A veces se quema, se broncea gradualmente.",
  "Pelle chiara. Scotta facilmente, si abbronza poco.": "Piel clara. Se quema con facilidad, se broncea poco.",
  "Pelle molto chiara. Scotta sempre, non si abbronza mai (spesso capelli rossi, lentiggini).": "Piel muy clara. Siempre se quema, nunca se broncea (a menudo pelo rojo, pecas).",
  "Pelle molto scura. Non scotta.": "Piel muy oscura. No se quema.",
  "Pelle olivastra. Scotta poco, si abbronza facilmente.": "Piel aceitunada. Se quema poco, se broncea con facilidad.",
  "Pelle scura. Scotta raramente.": "Piel oscura. Rara vez se quema.",
  "Per chiudere NeoTracker basta chiudere questa finestra con la X in alto a destra: il programma si spegne da solo.": "Para cerrar NeoTracker basta con cerrar esta ventana con la X de arriba a la derecha: el programa se apaga solo.",
  "Per confermare scrivi:": "Para confirmar, escribe:",
  "Per eliminare scrivi il nome esatto dell'utente nella conferma.": "Para eliminar, escribe en la confirmación el nombre exacto del usuario.",
  "Per le linee guida NCCN, in un melanoma invasivo con un parente di primo grado con tumore del pancreas è raccomandato un pannello multigene che includa CDKN2A.": "Según las guías del NCCN, en un melanoma invasivo con un familiar de primer grado con cáncer de páncreas se recomienda un panel multigénico que incluya CDKN2A.",
  "Per stimare la città il programma contatta il servizio gratuito ipwho.is, che vede il tuo indirizzo internet. La precisione è quella della città (a volte sbaglia). Procedo?": "Para estimar la ciudad, el programa contacta con el servicio gratuito ipwho.is, que ve tu dirección de internet. La precisión es la de la ciudad (a veces se equivoca). ¿Continúo?",
  "Per vedere quanto sole ti scotta, indica il fototipo nel": "Para ver cuánto sol te quema, indica tu fototipo en el",
  "Permesso negato. Puoi cercare la città per nome oppure usare la stima da indirizzo internet.": "Permiso denegado. Puedes buscar la ciudad por su nombre o usar la estimación desde la dirección de internet.",
  "Piede destro": "Pie derecho",
  "Piede sinistro": "Pie izquierdo",
  "Pillow non installato: le anteprime useranno le foto originali (installa con «py -m pip install pillow»).": "Pillow no está instalado: las vistas previas usarán las fotos originales (instálalo con «py -m pip install pillow»).",
  "Più colori nello stesso neo (marrone, nero, rosso, blu, bianco).": "Varios colores en el mismo lunar (marrón, negro, rojo, azul, blanco).",
  "Più di 6 mm (ma esistono melanomi più piccoli).": "Más de 6 mm (aunque existen melanomas más pequeños).",
  "Più tumori dello spettro BAP1 (melanoma uveale, mesotelioma, carcinoma renale, melanoma cutaneo)": "Varios tumores del espectro BAP1 (melanoma uveal, mesotelioma, carcinoma renal, melanoma cutáneo)",
  "Poche": "Pocas",
  "Polpaccio destro": "Pantorrilla derecha",
  "Polpaccio sinistro": "Pantorrilla izquierda",
  "Posizione": "Ubicación",
  "Posizione aggiornata.": "Ubicación actualizada.",
  "Posizione aggiornata: {regione}.": "Ubicación actualizada: {regione}.",
  "Posizione fuori dalla mappa.": "Ubicación fuera del mapa.",
  "Posizione impostata": "Ubicación establecida",
  "Posizione non impostata": "Ubicación no establecida",
  "Posizione non impostata: scegli una città o usa 'Rileva la mia posizione'.": "Ubicación no establecida: elige una ciudad o usa «Detectar mi ubicación».",
  "Posizione non valida.": "Ubicación no válida.",
  "Posizione salvata: {nome}": "Ubicación guardada: {nome}",
  "Posizione stimata": "Ubicación estimada",
  "Precauzioni extra: evita il sole nelle ore centrali, cerca l'ombra, copri la pelle, SPF 30+. La pelle non protetta si scotta in fretta.": "Precauciones extra: evita el sol en las horas centrales, busca la sombra, cubre la piel, SPF 30+. La piel sin proteger se quema enseguida.",
  "Preferisco non dirlo": "Prefiero no decirlo",
  "Premi": "Pulsa",
  "Preparo la scheda…": "Preparando la ficha…",
  "Prima": "Antes",
  "Prima di cominciare": "Antes de empezar",
  "Prima salva una chiave OpenWeather.": "Guarda primero una clave de OpenWeather.",
  "Principale gene di predisposizione ad alta penetranza. Varianti germinali nel 20-40% delle famiglie con melanoma; associato anche a tumore del pancreas, melanomi multipli ed esordio precoce.": "Principal gen de predisposición de alta penetrancia. Variantes germinales en el 20-40 % de las familias con melanoma; también asociado a cáncer de páncreas, melanomas múltiples y aparición temprana.",
  "Profilo": "Perfil",
  "Profilo da completare": "Perfil por completar",
  "Profilo di {nome}": "Perfil de {nome}",
  "Profilo non compilato.": "Perfil sin completar.",
  "Profilo non valido.": "Perfil no válido.",
  "Programma di analisi (melanoma_batch.py) non trovato: le foto si salvano ma non si possono analizzare.": "Programa de análisis (melanoma_batch.py) no encontrado: las fotos se guardan pero no se pueden analizar.",
  "Programma di analisi:": "Programa de análisis:",
  "Promemoria ABCDE": "Recordatorio ABCDE",
  "Promemoria ABCDE per riconoscere un neo": "Recordatorio ABCDE para reconocer un lunar",
  "Prossime {n} ore": "Próximas {n} horas",
  "Protezione consigliata: ombra nelle ore centrali, cappello, occhiali e crema solare.": "Protección recomendada: sombra en las horas centrales, gorro, gafas y crema solar.",
  "Protezione necessaria: riduci l'esposizione tra le 10 e le 16, crema solare SPF 30+, cappello e occhiali.": "Protección necesaria: reduce la exposición entre las 10 y las 16, crema solar SPF 30+, gorro y gafas.",
  "Protezione non necessaria per le attività normali (attenzione a neve, acqua, quota).": "No hace falta protección para las actividades normales (ojo con la nieve, el agua y la altitud).",
  "Prova la chiave": "Probar la clave",
  "Provo la chiave…": "Probando la clave…",
  "PubMed ha risposto con errore {code}": "PubMed respondió con el error {code}",
  "PubMed non raggiungibile (controlla la connessione internet)": "PubMed no accesible (comprueba la conexión a internet)",
  "PubMed non è raggiungibile: mostro l'ultima ricerca salvata il {data}.": "PubMed no está accesible: muestro la última búsqueda guardada el {data}.",
  "PubMed {pmid} · abstract non disponibile": "PubMed {pmid} · resumen no disponible",
  "PubMed è un servizio della National Library of Medicine. Gli abstract sono mostrati per consultazione personale, in inglese; per il testo completo apri l'articolo sul sito della rivista.": "PubMed es un servicio de la National Library of Medicine. Los resúmenes se muestran para consulta personal, en inglés; para el texto completo, abre el artículo en el sitio de la revista.",
  "Puoi chiudere questa finestra. Per riaprirlo usa l'icona «NeoTracker» sul Desktop.": "Puedes cerrar esta ventana. Para volver a abrirlo, usa el icono «NeoTracker» del Escritorio.",
  "Puoi continuare a usare l'app. Se chiudi la finestra l'analisi non va persa: il programma finisce il lavoro e poi si spegne da solo.": "Puedes seguir usando la aplicación. Si cierras la ventana el análisis no se pierde: el programa termina el trabajo y luego se apaga solo.",
  "Puoi usare una tua foto, un disegno o un'icona. L'immagine viene ritagliata a quadrato e ridotta, resta solo su questo computer e non viene mai usata per l'analisi dei nei.": "Puedes usar una foto tuya, un dibujo o un icono. La imagen se recorta en cuadrado y se reduce, permanece solo en este ordenador y nunca se usa para el análisis de los lunares.",
  "Qualche volta": "A veces",
  "Qualcosa non ha funzionato": "Algo ha salido mal",
  "Quando l'hai notato, se prude, se è cambiato…": "Cuándo lo notaste, si pica, si ha cambiado…",
  "Quanti nei hai sul corpo, circa?": "¿Aproximadamente cuántos lunares tienes en el cuerpo?",
  "Quanto sono affidabili app e intelligenza artificiale": "Qué tan fiables son las aplicaciones y la inteligencia artificial",
  "Questa foto non è ancora stata analizzata. L'analisi confronta più metodi sulla stessa immagine e ti dice cosa ha risposto ciascuno.": "Esta foto aún no se ha analizado. El análisis compara varios métodos sobre la misma imagen y te dice qué respondió cada uno.",
  "Questa scheda raccoglie dati inseriti dalla persona e foto da lei scattate. I risultati dell'analisi automatica sono sperimentali, non sono una diagnosi e non sostituiscono la visita dermatologica o la dermoscopia.": "Esta ficha reúne datos introducidos por la persona y fotos tomadas por ella. Los resultados del análisis automático son experimentales, no son un diagnóstico y no sustituyen la visita al dermatólogo ni la dermatoscopia.",
  "Questo browser non offre la geolocalizzazione: cerca la città per nome.": "Este navegador no ofrece geolocalización: busca la ciudad por su nombre.",
  "Questo metodo prevede l'invio dei pixel della foto (non dei metadati) a un server esterno.": "Este método envía los píxeles de la foto (no los metadatos) a un servidor externo.",
  "Questo programma ti aiuta a tenere traccia dei tuoi nei nel tempo: li segni su una mappa del corpo, ne conservi le foto con la data e li fai analizzare da più metodi. Inizia creando il tuo utente.": "Este programa te ayuda a seguir tus lunares a lo largo del tiempo: los marcas en un mapa del cuerpo, guardas sus fotos con la fecha y los haces analizar con varios métodos. Empieza creando tu usuario.",
  "Questo rapporto NON è una diagnosi. I programmi usati sono prototipi di ricerca, non dispositivi medici.": "Este informe NO es un diagnóstico. Los programas utilizados son prototipos de investigación, no productos sanitarios.",
  "RETRO": "ESPALDA",
  "Rapporto completo (testo)": "Informe completo (texto)",
  "Rapporto completo (testo, in italiano)": "Informe completo (texto, en italiano)",
  "Raro": "Raro",
  "Regione lombare destra": "Región lumbar derecha",
  "Regione lombare sinistra": "Región lumbar izquierda",
  "Regione scapolare destra": "Región escapular derecha",
  "Regione scapolare sinistra": "Región escapular izquierda",
  "Retro": "Espalda",
  "Revisione": "Revisión",
  "Revisione sistematica": "Revisión sistemática",
  "Revisioni sul melanoma familiare (CDKN2A, CDK4)": "Revisiones sobre el melanoma familiar (CDKN2A, CDK4)",
  "Rianalizza": "Volver a analizar",
  "Richiesta non autorizzata.": "Solicitud no autorizada.",
  "Richiesta troppo grande.": "Solicitud demasiado grande.",
  "Riconoscere un neo sospetto": "Reconocer un lunar sospechoso",
  "Riduci": "Reducir",
  "Rifà la ricerca ignorando i risultati salvati": "Repetir la búsqueda ignorando los resultados guardados",
  "Rileva la mia posizione": "Detectar mi ubicación",
  "Rimuovere la chiave?": "¿Eliminar la clave?",
  "Rimuovi": "Quitar",
  "Rinomina": "Renombrar",
  "Rinomina utente": "Renombrar usuario",
  "Ripristina": "Restaurar",
  "Riprova": "Reintentar",
  "Rischio associato": "Riesgo asociado",
  "Rossi": "Pelirrojos",
  "Rotella = zoom · trascina = sposta · doppio clic = ingrandisci": "Rueda = zoom · arrastrar = mover · doble clic = ampliar",
  "Ruolo e letteratura": "Función y literatura",
  "S": "I",
  "Salva": "Guardar",
  "Salva foto": "Guardar foto",
  "Salva neo": "Guardar lunar",
  "Salvataggio…": "Guardando…",
  "Salvato ✓": "Guardado ✓",
  "Scansiona la letteratura": "Explorar la literatura",
  "Scansiona la letteratura sui geni": "Explorar la literatura sobre los genes",
  "Scansione completata.": "Exploración completada.",
  "Scarico l'indice UV…": "Descargando el índice UV…",
  "Scatta sempre dalla stessa angolazione e salva l'originale, senza filtri.": "Haz siempre la foto desde el mismo ángulo y guarda el original, sin filtros.",
  "Scegli dove ti trovi per vedere l'indice UV di oggi.": "Elige dónde te encuentras para ver el índice UV de hoy.",
  "Scegli il tuo profilo: ogni persona ha la propria mappa dei nei, le proprie foto e i propri dati.": "Elige tu perfil: cada persona tiene su propio mapa de lunares, sus fotos y sus datos.",
  "Scegli immagine…": "Elegir imagen…",
  "Scegli la città qui sopra: poi vedrai l'indice UV di oggi, ora per ora.": "Elige la ciudad arriba: después verás el índice UV de hoy, hora a hora.",
  "Scegli un file immagine (JPG, PNG, WEBP o BMP).": "Elige un archivo de imagen (JPG, PNG, WEBP o BMP).",
  "Scegli un utente e indica il suo fototipo per vedere quanti minuti servono per scottarsi.": "Elige un usuario e indica su fototipo para ver en cuántos minutos se quema.",
  "Scegli un'immagine personale": "Elige una imagen personal",
  "Scegli utente": "Elegir usuario",
  "Scelti per te (in base a profilo e sede dei nei)": "Elegidos para ti (según el perfil y la ubicación de los lunares)",
  "Scheda dei nei – {nome}": "Ficha de lunares – {nome}",
  "Scheda per il dermatologo": "Ficha para el dermatólogo",
  "Schiena (zona media) destra": "Espalda (zona media) derecha",
  "Schiena (zona media) sinistra": "Espalda (zona media) izquierda",
  "Scottature": "Quemaduras solares",
  "Scottature con vesciche (soprattutto da bambino o ragazzo)": "Quemaduras solares con ampollas (sobre todo de niño o adolescente)",
  "Scrivi almeno 3 caratteri.": "Escribe al menos 3 caracteres.",
  "Scrivi un nome.": "Escribe un nombre.",
  "Scuri": "Oscuros",
  "Se hai dubbi sul fototipo, pensa a come reagisce la tua pelle alla prima esposizione intensa al sole in estate, senza protezione.": "Si dudas sobre tu fototipo, piensa en cómo reacciona tu piel a la primera exposición intensa al sol en verano, sin protección.",
  "Se i metodi sono in disaccordo è normale: significa solo che nessuno di loro è affidabile da solo.": "Es normal que los métodos no coincidan: solo significa que ninguno es fiable por sí solo.",
  "Se inserisci dati o foto di altre persone, assicurati di avere il loro consenso.": "Si introduces datos o fotos de otras personas, asegúrate de contar con su consentimiento.",
  "Se sta ancora analizzando una foto, finisce prima l'analisi e poi si spegne. Il pulsante qui sotto fa la stessa cosa.": "Si todavía está analizando una foto, termina primero el análisis y luego se apaga. El botón de abajo hace lo mismo.",
  "Sede": "Zona",
  "Sede (modificabile)": "Zona (editable)",
  "Senza Pillow l'immagine deve essere un JPG/PNG sotto i 400 KB (la pagina la riduce da sola: riprova con la funzione 'Scegli immagine').": "Sin Pillow la imagen debe ser un JPG/PNG de menos de 400 KB (la página la reduce sola: inténtalo de nuevo con la función «Elegir imagen»).",
  "Servono ombra, abiti, cappello e crema solare nelle ore centrali.": "Hacen falta sombra, ropa, gorro y crema solar en las horas centrales.",
  "Sesso": "Sexo",
  "Sezione sconosciuta.": "Sección desconocida.",
  "Sezione {n} di {tot}…": "Sección {n} de {tot}…",
  "Sezioni": "Secciones",
  "Sindrome di predisposizione ai tumori BAP1: melanoma uveale, mesotelioma, carcinoma renale, melanoma cutaneo e nevi melanocitari atipici.": "Síndrome de predisposición a tumores BAP1: melanoma uveal, mesotelioma, carcinoma renal, melanoma cutáneo y nevus melanocíticos atípicos.",
  "Sindromico": "Sindrómico",
  "SkinSense (servizio online)": "SkinSense (servicio en línea)",
  "SkinSense abilitato.": "SkinSense activado.",
  "SkinSense disattivato.": "SkinSense desactivado.",
  "SkinSense è attivo: la foto (senza metadati) verrà inviata a un servizio online.": "SkinSense está activo: la foto (sin metadatos) se enviará a un servicio en línea.",
  "SkinSense è un servizio online di terzi: le foto dei tuoi nei verrebbero inviate via internet a un server che non controlliamo. Le foto sono dati sulla tua salute. Vuoi abilitarlo?": "SkinSense es un servicio en línea de terceros: las fotos de tus lunares se enviarían por internet a un servidor que no controlamos. Las fotos son datos sobre tu salud. ¿Quieres activarlo?",
  "Soddisfatto": "Cumplido",
  "Soglie e colori della scala internazionale dell'OMS. Fonti:": "Umbrales y colores de la escala internacional de la OMS. Fuentes:",
  "Sono immunosoppresso/a (trapianto o terapie che abbassano le difese)": "Estoy inmunodeprimido/a (trasplante o tratamientos que reducen las defensas)",
  "Sono misure inserite da te: valgono se prese sempre allo stesso modo. Un neo che cresce o cambia è un buon motivo per farlo vedere al dermatologo; la linea a 6 mm è solo il riferimento classico dei criteri ABCDE.": "Son medidas introducidas por ti: valen si se toman siempre del mismo modo. Un lunar que crece o cambia es un buen motivo para enseñárselo al dermatólogo; la línea de 6 mm es solo la referencia clásica de los criterios ABCDE.",
  "Sono mostrate {n} foto su {tot}.": "Se muestran {n} fotos de {tot}.",
  "Sono presenti alcuni fattori di rischio: protezione solare accurata e autoesame regolare; un controllo dermatologico di base è una buona abitudine.": "Hay algunos factores de riesgo: protección solar cuidadosa y autoexploración regular; una revisión dermatológica básica es un buen hábito.",
  "Sono presenti fattori di rischio rilevanti: è consigliato un controllo dermatologico periodico (la frequenza la decide il dermatologo) e l'autoesame regolare della pelle.": "Hay factores de riesgo relevantes: se aconseja una revisión dermatológica periódica (la frecuencia la decide el dermatólogo) y la autoexploración regular de la piel.",
  "Soprattutto in infanzia e adolescenza.": "Sobre todo en la infancia y la adolescencia.",
  "Sovrapponi con cursore": "Superponer con control deslizante",
  "Spalla destra": "Hombro derecho",
  "Spalla sinistra": "Hombro izquierdo",
  "Spento per impostazione predefinita: con gli altri metodi la foto non lascia mai questo computer.": "Desactivado por defecto: con los demás métodos la foto nunca sale de este ordenador.",
  "Spesso": "A menudo",
  "Stampa la scheda di questo neo": "Imprimir la ficha de este lunar",
  "Stampa una scheda con tutti i nei": "Imprimir una ficha con todos los lunares",
  "Stampata il {data} con NeoTracker": "Impreso el {data} con NeoTracker",
  "Stato dell'installazione": "Estado de la instalación",
  "Stessa luce (luce del giorno, senza flash) e stessa distanza ogni volta, circa 10-15 cm.": "La misma luz (luz del día, sin flash) y la misma distancia cada vez, unos 10-15 cm.",
  "Stima dall'indirizzo internet": "Estimación desde la dirección de internet",
  "Storia familiare": "Antecedentes familiares",
  "Storia personale": "Antecedentes personales",
  "Storico fotografico": "Historial fotográfico",
  "Storico fotografico ({n})": "Historial fotográfico ({n})",
  "Studi più pertinenti": "Estudios más pertinentes",
  "Studi più recenti sui geni di predisposizione": "Estudios más recientes sobre los genes de predisposición",
  "Studio clinico": "Estudio clínico",
  "Studio osservazionale": "Estudio observacional",
  "Studio randomizzato": "Estudio aleatorizado",
  "Sì": "Sí",
  "Sì, abilita": "Sí, activar",
  "Sì, negativo": "Sí, negativo",
  "Sì, non informativo": "Sí, no informativo",
  "Sì, positivo": "Sí, positivo",
  "Sì, stima la città": "Sí, estimar la ciudad",
  "Telomerasi: varianti del promotore descritte in famiglie con melanoma.": "Telomerasa: variantes del promotor descritas en familias con melanoma.",
  "Test genetico": "Prueba genética",
  "Test genetico già eseguito": "Prueba genética ya realizada",
  "Tipo": "Tipo",
  "Tipo di foto": "Tipo de foto",
  "Tipo {n}": "Tipo {n}",
  "Torace destro": "Tórax derecho",
  "Torace sinistro": "Tórax izquierdo",
  "Tra le due foto sono passati {n} giorni.": "Entre las dos fotos han pasado {n} días.",
  "Tra le due foto è passato {n} giorno.": "Entre las dos fotos ha pasado {n} día.",
  "Trascina il pallino sulla mappa per correggere la posizione; ingrandisci con la rotella per la massima precisione.": "Arrastra el punto en el mapa para corregir la posición; amplía con la rueda para la máxima precisión.",
  "Trascina il pallino sulla mappa per spostarlo.": "Arrastra el punto en el mapa para moverlo.",
  "Trascina qui una foto oppure clicca per sceglierla": "Arrastra aquí una foto o haz clic para elegirla",
  "Troppi collegamenti aperti.": "Demasiadas conexiones abiertas.",
  "Tumore del pancreas": "Cáncer de páncreas",
  "Tumori dello spettro BAP1 indicati: {bap1_spettro}. Criterio semplificato: il genetista usa criteri più completi.": "Tumores del espectro BAP1 indicados: {bap1_spettro}. Criterio simplificado: el genetista usa criterios más completos.",
  "Tutti i dati restano su questo computer, nella cartella:": "Todos los datos permanecen en este ordenador, en la carpeta:",
  "UV moderati: serve protezione nelle ore centrali": "UV moderados: hace falta protección en las horas centrales",
  "Ultima analisi automatica ({data}): {esito}. Strumento di ricerca, non diagnostico.": "Último análisis automático ({data}): {esito}. Herramienta de investigación, no diagnóstica.",
  "Un medico ti ha detto che hai nei atipici (displastici)?": "¿Algún médico te ha dicho que tienes lunares atípicos (displásicos)?",
  "Un neo che cambia (forma, bordi, colore, dimensioni), sanguina, prude o ti preoccupa va mostrato a un dermatologo, qualunque cosa dica l'app. Il controllo periodico dal dermatologo resta insostituibile.": "Un lunar que cambia (forma, bordes, color, tamaño), sangra, pica o te preocupa debe enseñarse a un dermatólogo, diga lo que diga la aplicación. La revisión periódica con el dermatólogo sigue siendo insustituible.",
  "Un risultato positivo indica un rischio più alto, non la certezza di ammalarsi; un risultato negativo non azzera il rischio (molte famiglie non hanno una variante identificabile).": "Un resultado positivo indica un riesgo más alto, no la certeza de enfermar; un resultado negativo no anula el riesgo (muchas familias no tienen una variante identificable).",
  "Una stima va bene.": "Una estimación basta.",
  "Uomo": "Hombre",
  "Usa anche SkinSense (servizio online)": "Usar también SkinSense (servicio en línea)",
  "Usa la data scritta nella foto, se c'è": "Usar la fecha guardada en la foto, si existe",
  "Uso di lampade o lettini abbronzanti": "Uso de lámparas o camas solares de bronceado",
  "Utente creato. Compila il profilo: serve a contestualizzare i risultati.": "Usuario creado. Completa el perfil: sirve para contextualizar los resultados.",
  "Utente eliminato.": "Usuario eliminado.",
  "Utente non trovato.": "Usuario no encontrado.",
  "Vai alla sezione Genetica": "Ir a la sección Genética",
  "Varianti comuni legate a capelli rossi e pelle chiara: aumentano il rischio di melanoma in modo moderato. Non è un test di routine: l'interpretazione è specialistica.": "Variantes frecuentes ligadas al pelo rojo y la piel clara: aumentan moderadamente el riesgo de melanoma. No es una prueba rutinaria: la interpretación es especializada.",
  "Varianti rare concentrate nel codone 24: il quadro familiare è indistinguibile da quello di CDKN2A.": "Variantes raras concentradas en el codón 24: el cuadro familiar es indistinguible del de CDKN2A.",
  "Variazione:": "Variación:",
  "Verdi": "Verdes",
  "Verranno cancellate per sempre la sua unica foto e i rapporti di analisi.": "Su única foto y los informes de análisis se eliminarán para siempre.",
  "Verranno cancellate per sempre tutte le sue {n} foto e i rapporti di analisi.": "Sus {n} fotos y los informes de análisis se eliminarán para siempre.",
  "Verranno cancellati per sempre il profilo, tutti i nei, tutte le foto e tutti i rapporti di questo utente. L'operazione non si può annullare.": "El perfil, todos los lunares, todas las fotos y todos los informes de este usuario se eliminarán para siempre. La operación no se puede deshacer.",
  "Versione": "Versión",
  "Versione dell'avviso non valida.": "Versión de la advertencia no válida.",
  "Viso": "Cara",
  "a cielo sereno e senza protezione, al picco di oggi la pelle può arrossarsi in": "con cielo despejado y sin protección, en el pico de hoy la piel puede enrojecerse en",
  "aggiornato": "actualizado",
  "altro": "otro",
  "assumo che le 2 uscite siano [benigno, maligno]; ordine non verificabile": "supongo que las 2 salidas son [benigno, maligno]; orden no verificable",
  "attivo solo se lo abiliti qui sotto": "activo solo si lo habilitas más abajo",
  "capelli biondi": "cabello rubio",
  "capelli castani": "cabello castaño",
  "capelli grigi o bianchi": "cabello canoso o blanco",
  "capelli neri": "cabello negro",
  "capelli rossi": "cabello pelirrojo",
  "carcinoma basocellulare, tumore della pelle": "carcinoma basocelular, un cáncer de piel",
  "carcinoma squamocellulare, tumore della pelle": "carcinoma espinocelular, un cáncer de piel",
  "cheratosi attinica, lesione pre-cancerosa": "queratosis actínica, una lesión precancerosa",
  "cheratosi seborroica, benigna": "queratosis seborreica, benigna",
  "circa {minuti} minuti": "unos {minuti} minutos",
  "connessione non riuscita: {motivo}": "no se pudo conectar: {motivo}",
  "cuoio capelluto": "cuero cabelludo",
  "dermoscopica": "dermatoscópica",
  "donna": "mujer",
  "dorso del piede": "empeine",
  "dorso della mano": "dorso de la mano",
  "e clicca sul punto esatto del corpo (ingrandisci con la rotella per essere più preciso).": "y haz clic en el punto exacto del cuerpo (amplía con la rueda para ser más preciso).",
  "e conferma l'email.": "y confirma el correo electrónico.",
  "es. 4,5": "p. ej. 4,5",
  "facoltativa: richiede una tua chiave personale": "opcional: requiere una clave personal tuya",
  "foto normale": "foto normal",
  "fototipo {tipo}": "fototipo {tipo}",
  "fronte": "frente",
  "gratuita, senza account né chiave": "gratuita, sin cuenta ni clave",
  "i metodi non concordano tra loro": "los métodos no coinciden entre sí",
  "i modelli di App 1 non sono stati scaricati: sono ancora dei segnaposto Git LFS. Apri PowerShell nella cartella {cartella} e lancia 'git lfs pull', poi riprova.": "los modelos de la App 1 no se han descargado: siguen siendo marcadores de posición de Git LFS. Abre PowerShell en la carpeta {cartella}, ejecuta 'git lfs pull' y vuelve a intentarlo.",
  "ieri": "ayer",
  "il modello ha {n} uscite: significato sconosciuto": "el modelo tiene {n} salidas: significado desconocido",
  "impossibile avviare: {e}": "no se puede iniciar: {e}",
  "in {n} giorni.": "en {n} días.",
  "in {n} giorno.": "en {n} día.",
  "indirizzo del servizio non ammesso (serve https)": "dirección del servicio no permitida (se requiere https)",
  "indirizzo non ammesso (solo https)": "dirección no permitida (solo https)",
  "interrotto dopo {minuti} minuti (tempo massimo)": "interrumpido tras {minuti} minutos (tiempo máximo)",
  "la foto non si apre come immagine ({tipo}): {dettaglio}": "la foto no se abre como imagen ({tipo}): {dettaglio}",
  "labbro": "labio",
  "le prime 1.000 chiamate al giorno sono gratuite, le successive si pagano. OpenWeather può chiedere una carta di pagamento per attivarlo: controlla le condizioni sul loro sito.": "las primeras 1.000 llamadas al día son gratuitas y las siguientes se pagan. OpenWeather puede pedir una tarjeta de pago para activarlo: consulta las condiciones en su sitio web.",
  "mai": "nunca",
  "mancano i pesi addestrati: nella cartella {cartella} non ci sono i file model_fold_0.bin ... model_fold_4.bin. Il repository non li contiene: vanno prodotti con train.py sul dataset SIIM-ISIC.": "faltan los pesos entrenados: en la carpeta {cartella} no están los archivos model_fold_0.bin ... model_fold_4.bin. El repositorio no los contiene: hay que generarlos con train.py sobre el conjunto de datos SIIM-ISIC.",
  "media di {n} modelli; punteggio medio {media} (soglia 0)": "media de {n} modelos; puntuación media {media} (umbral 0)",
  "melanoma": "melanoma",
  "meno di 25": "menos de 25",
  "molte": "muchas",
  "molte efelidi": "muchas pecas",
  "nel pannello": "en el panel",
  "nessun caso indicato": "ningún caso indicado",
  "nessun metodo ha segnalato il neo (questo non esclude un melanoma)": "ningún método ha señalado el lunar (esto no descarta un melanoma)",
  "nessun risultato disponibile": "ningún resultado disponible",
  "nessuna efelide": "ninguna peca",
  "nevo, cioe' neo benigno": "nevus, es decir, lunar benigno",
  "no": "no",
  "nome@esempio.it (facoltativa)": "nombre@ejemplo.es (opcional)",
  "non riesco a preparare la foto in modo sicuro: {e}": "no puedo preparar la foto de forma segura: {e}",
  "non so": "no lo sé",
  "occhi azzurri o grigi": "ojos azules o grises",
  "occhi scuri": "ojos oscuros",
  "occhi verdi": "ojos verdes",
  "oggi": "hoy",
  "oltre 2 ore (UV molto basso)": "más de 2 horas (UV muy bajo)",
  "orecchio": "oreja",
  "pagina del servizio": "página del servicio",
  "palmo della mano": "palma de la mano",
  "palpebra": "párpado",
  "pianta del piede": "planta del pie",
  "poche": "pocas",
  "poche efelidi": "pocas pecas",
  "posizione da indirizzo internet non disponibile": "ubicación a partir de la dirección de internet no disponible",
  "prob. melanoma {perc}": "prob. de melanoma {perc}",
  "probabilita' di malignita' stimata dal modello: {pm}": "probabilidad de malignidad estimada por el modelo: {pm}",
  "qualche volta": "a veces",
  "retro": "espalda",
  "rilevante": "relevante",
  "risposta illeggibile: {e}": "respuesta ilegible: {e}",
  "risposta non valida dal servizio": "respuesta no válida del servicio",
  "risposta senza nome della lesione: {risposta}": "respuesta sin nombre de la lesión: {risposta}",
  "risposta troppo grande": "respuesta demasiado grande",
  "servizio non raggiungibile: {ultimo_errore}": "servicio no accesible: {ultimo_errore}",
  "sicurezza {perc}": "confianza {perc}",
  "sotto l'unghia (mano)": "bajo la uña (mano)",
  "sotto l'unghia (piede)": "bajo la uña (pie)",
  "spazio tra le dita": "entre los dedos de la mano o del pie",
  "spesso": "a menudo",
  "studi su PubMed": "estudios en PubMed",
  "sì": "sí",
  "sì, negativo": "sí, negativo",
  "sì, non informativo": "sí, no informativo",
  "sì, positivo": "sí, positivo",
  "tempo scaduto o rete non disponibile": "tiempo agotado o red no disponible",
  "tutti i metodi con risultato indicano un neo da attenzionare": "todos los métodos con resultado señalan un lunar que requiere atención",
  "ukalwa / melanoma-detection (app Android)": "ukalwa / melanoma-detection (aplicación Android)",
  "uomo": "hombre",
  "uscita letta come le 6 classi di pelle (non verificabile)": "salida interpretada como las 6 clases de piel (no verificable)",
  "vatsal30 / Melanoma-Detection (PyTorch)": "vatsal30 / Melanoma-Detection (PyTorch)",
  "{avviso} Il servizio Open-Meteo non risponde ({e}).": "{avviso} El servicio Open-Meteo no responde ({e}).",
  "{cosa} non può essere vuoto.": "{cosa} no puede estar vacío.",
  "{cosa} è troppo lungo (massimo {massimo} caratteri).": "{cosa} es demasiado largo (máximo {massimo} caracteres).",
  "{file_modello} e' ancora un segnaposto Git LFS: lancia 'git lfs pull' nella cartella {cartella}.": "{file_modello} sigue siendo un marcador de posición de Git LFS: ejecuta 'git lfs pull' en la carpeta {cartella}.",
  "{file_pesi} e' ancora un segnaposto Git LFS: apri PowerShell nella cartella {cartella} e lancia 'git lfs pull'.": "{file_pesi} sigue siendo un marcador de posición de Git LFS: abre PowerShell en la carpeta {cartella} y ejecuta 'git lfs pull'.",
  "{foto} · ultima {quando}": "{foto} · última {quando}",
  "{giorno} ore {ora}: indice UV {uvi} ({categoria})": "{giorno} a las {ora}: índice UV {uvi} ({categoria})",
  "{nome} · {mb} MB · clicca per cambiare": "{nome} · {mb} MB · haz clic para cambiar",
  "{nome}: errore.": "{nome}: error.",
  "{nome}: il valore deve essere tra {minimo} e {massimo}.": "{nome}: el valor debe estar entre {minimo} y {massimo}.",
  "{nome}: inserisci un numero.": "{nome}: introduce un número.",
  "{nome}: non disponibile.": "{nome}: no disponible.",
  "{n} altro/i parente/i con melanoma": "{n} otro(s) familiar(es) con melanoma",
  "{n} anni": "{n} años",
  "{n} anni fa": "hace {n} años",
  "{n} anno": "{n} año",
  "{n} anno fa": "hace {n} año",
  "{n} articoli su melanoma e «{termine}»": "{n} artículos sobre melanoma y «{termine}»",
  "{n} articoli trovati su PubMed · ricerca del {data}": "{n} artículos encontrados en PubMed · búsqueda del {data}",
  "{n} articoli trovati su PubMed · ricerca del {data} (salvata)": "{n} artículos encontrados en PubMed · búsqueda del {data} (guardada)",
  "{n} con astrocitoma": "{n} con astrocitoma",
  "{n} con melanoma uveale": "{n} con melanoma uveal",
  "{n} con tumore del pancreas": "{n} con cáncer de páncreas",
  "{n} file modello su 10": "{n} archivos de modelo de 10",
  "{n} file modello su 5": "{n} archivos de modelo de 5",
  "{n} foto": "{n} foto",
  "{n} foto in {giorni} (dal {da} al {a}).": "{n} fotos en {giorni} (del {da} al {a}).",
  "{n} foto#pl": "{n} fotos",
  "{n} giorni": "{n} días",
  "{n} giorni fa": "hace {n} días",
  "{n} giorno": "{n} día",
  "{n} mesi fa": "hace {n} meses",
  "{n} metodi su {tot} hanno risposto": "{n} de {tot} métodos respondieron",
  "{n} nei": "{n} lunares",
  "{n} nei in questa scheda": "{n} lunares en esta ficha",
  "{n} neo": "{n} lunar",
  "{n} neo in questa scheda": "{n} lunar en esta ficha",
  "{n} parente/i di primo grado con melanoma": "{n} familiar(es) de primer grado con melanoma",
  "{n} su {tot}: {et}": "{n} de {tot}: {et}",
  "{vista} · posizione {x}% da sinistra, {y}% dall'alto": "{vista} · posición {x} % desde la izquierda, {y} % desde arriba",
  "È una stima prudente che usa la dose minima di eritema più bassa del tuo fototipo; con riflessi (acqua, neve, sabbia), quota o pelle già arrossata il tempo si accorcia.": "Es una estimación prudente que usa la dosis mínima de eritema más baja de tu fototipo; con reflejos (agua, nieve, arena), altitud o piel ya enrojecida el tiempo se acorta.",
  "È uno strumento personale per organizzare le foto dei tuoi nei e confrontare nel tempo i risultati di alcuni modelli di ricerca. Non è certificato né approvato da alcuna autorità sanitaria.": "Es una herramienta personal para organizar las fotos de tus lunares y comparar a lo largo del tiempo los resultados de algunos modelos de investigación. No está certificada ni aprobada por ninguna autoridad sanitaria.",
  "…di cui di 1° grado": "…de los cuales de 1.er grado",
  "← Tutti i nei": "← Todos los lunares"
};
'''
WEB_FILES["/i18n_es.js"] = ("text/javascript; charset=utf-8", _WEB_I18N_ES_JS.encode("utf-8"))

_WEB_I18N_FR_JS = r'''/* Traduzioni dell'interfaccia di NeoTracker: fr. Chiave = testo italiano originale.
   I segnaposto {nome} vanno lasciati uguali. Controllo: python3 tools/traduzioni.py */
(window.NT_DIZIONARI = window.NT_DIZIONARI || {}).fr = {
  "(licenza CC BY 4.0). Il servizio gratuito è per uso personale e non commerciale.": "(licence CC BY 4.0). Le service gratuit est réservé à un usage personnel et non commercial.",
  "(ora locale del luogo)": "(heure locale du lieu)",
  "(ricerca salvata del {data})": "(recherche enregistrée du {data})",
  "(senza titolo)": "(sans titre)",
  "(vuoto)": "(vide)",
  "({variazione} mm dalla foto precedente)": "({variazione} mm par rapport à la photo précédente)",
  "1 foto del {data}, diametro {mm} mm.": "1 photo du {data}, diamètre {mm} mm.",
  "1 foto del {data}.": "1 photo du {data}.",
  "100 o più": "100 ou plus",
  "100 o più nei sul corpo": "100 grains de beauté ou plus sur le corps",
  "3 = da qui l'OMS consiglia protezione": "3 = l'OMS recommande une protection à partir d'ici",
  "3 o più melanomi primari nella stessa persona": "3 mélanomes primaires ou plus chez la même personne",
  "A che cosa servono questi dati?": "À quoi servent ces informations ?",
  "Accesso non autorizzato.": "Accès non autorisé.",
  "Accetto e continuo": "Accepter et continuer",
  "Addome alto destro": "Haut de l'abdomen droit",
  "Addome alto sinistro": "Haut de l'abdomen gauche",
  "Addome basso destro": "Bas de l'abdomen droit",
  "Addome basso sinistro": "Bas de l'abdomen gauche",
  "Adesso": "Maintenant",
  "Aggiorna": "Actualiser",
  "Aggiungi la prima foto: diventa la tua foto storica, e ogni foto successiva ne seguirà l'evoluzione.": "Ajoutez la première photo : elle devient votre photo de référence, et chaque photo suivante montrera l'évolution du grain de beauté.",
  "Aggiungi neo": "Ajouter un grain de beauté",
  "Aggiungi qui sotto la prima foto: sarà il punto di partenza per vedere se il neo cambia nel tempo.": "Ajoutez ci-dessous la première photo : elle servira de point de départ pour voir si le grain de beauté change au fil du temps.",
  "Aggiungi una foto allo storico": "Ajouter une photo à l'historique",
  "Alla sottoscrizione il limite giornaliero predefinito è di 2.000 chiamate: nella scheda «Billing plans» del tuo account puoi abbassarlo a 1.000, così non spendi nulla. NeoTracker ne usa poche (al massimo 4 ogni 10 minuti, solo quando apri la pagina Indice UV).": "À la souscription, la limite quotidienne par défaut est de 2 000 appels : dans l'onglet « Billing plans » de votre compte, vous pouvez la ramener à 1 000 pour ne rien dépenser. NeoTracker en utilise très peu (au maximum 4 toutes les 10 minutes, uniquement lorsque vous ouvrez la page Indice UV).",
  "Almeno 3 diagnosi tra melanoma, tumore del pancreas e astrocitoma nella stessa linea familiare (tua inclusa)": "Au moins 3 diagnostics parmi mélanome, cancer du pancréas et astrocytome dans la même lignée familiale (la vôtre incluse)",
  "Almeno un metodo (o un suo modello) segnala una lesione da attenzionare. Non è una diagnosi e questi strumenti sbagliano spesso, ma è un motivo in più per non rimandare la visita dermatologica e per portare questo rapporto.": "Au moins une méthode (ou l'un de ses modèles) signale une lésion à surveiller. Ce n'est pas un diagnostic et ces outils se trompent souvent, mais c'est une raison de plus de ne pas reporter la consultation dermatologique et d'apporter ce rapport.",
  "Alto": "Élevé",
  "Alto (raro)": "Élevé (rare)",
  "Alto (sindrome BAP1)": "Élevé (syndrome BAP1)",
  "Altri parenti con melanoma": "Autres parents atteints de mélanome",
  "Altri tumori della pelle (basalioma, spinalioma)": "Autres cancers de la peau (carcinome basocellulaire et épidermoïde)",
  "Altro": "Autre",
  "Altro che vuoi ricordare (allergie, farmaci fotosensibilizzanti, …)": "Autre chose dont vous voulez vous souvenir (allergies, médicaments photosensibilisants, …)",
  "Analisi automatica": "Analyse automatique",
  "Analisi delle foto": "Analyse des photos",
  "Analisi in corso…": "Analyse en cours…",
  "Analisi interrotta dopo {ore} ore (troppo lunga).": "Analyse interrompue après {ore} heures (trop longue).",
  "Analisi: da attenzionare": "Analyse : à surveiller",
  "Analizza questa foto": "Analyser cette photo",
  "Analizza subito con tutti i metodi installati": "Analyser maintenant avec toutes les méthodes installées",
  "Anche la ricerca delle città usa Open-Meteo.": "La recherche de villes utilise aussi Open-Meteo.",
  "Ancora nessuna foto": "Aucune photo pour l'instant",
  "Annulla": "Annuler",
  "Anteprima": "Aperçu",
  "App 1 (DeborahAdedigba) - modelli TensorFlow": "App 1 (DeborahAdedigba) - modèles TensorFlow",
  "App per smartphone e rischio di cancro della pelle: accuratezza diagnostica": "Applications pour smartphone et risque de cancer de la peau : précision diagnostique",
  "Apri la pagina «API keys» del tuo account e copia la chiave.": "Ouvrez la page « API keys » de votre compte et copiez la clé.",
  "Archivia (toglie dalla mappa, conserva i dati)": "Archiver (le retire de la carte, conserve les données)",
  "Articoli recenti e rilevanti su come riconoscere i nei sospetti, sull'affidabilità di app e intelligenza artificiale e sul melanoma ereditario. I risultati arrivano da PubMed, la banca dati pubblica della National Library of Medicine (USA).": "Articles récents et pertinents sur la reconnaissance des grains de beauté suspects, la fiabilité des applications et de l'intelligence artificielle, et le mélanome héréditaire. Les résultats proviennent de PubMed, la base de données publique de la National Library of Medicine (États-Unis).",
  "Asimmetria": "Asymétrie",
  "Aspetto": "Apparence",
  "Associati a varianti del gene MC1R.": "Associés à des variants du gène MC1R.",
  "Astrocitoma": "Astrocytome",
  "Attenzione: non ho trovato l'ambiente .venv di App 1, uso il Python corrente.": "Attention : l'environnement .venv de l'App 1 est introuvable ; j'utilise le Python actuel.",
  "Aumenta: {voce}": "Augmenter : {voce}",
  "Autoesame della pelle": "Autoexamen de la peau",
  "Automatica (come il sistema)": "Automatique (comme le système)",
  "Avambraccio destro": "Avant-bras droit",
  "Avambraccio sinistro": "Avant-bras gauche",
  "Avvertenze": "Avertissements",
  "Azzurri/grigi": "Bleus/gris",
  "Basso": "Faible",
  "Basso-moderato (comune)": "Faible à modéré (fréquent)",
  "Benvenuto in NeoTracker": "Bienvenue dans NeoTracker",
  "Biondi": "Blonds",
  "Bordi": "Bords",
  "Braccio destro": "Bras droit",
  "Braccio sinistro": "Bras gauche",
  "Cambia": "Changer",
  "Cambia immagine…": "Changer d'image…",
  "Cambia nel tempo: forma, colore, dimensione, rilievo, o compaiono prurito o sanguinamento.": "Il change avec le temps : forme, couleur, taille, relief, ou apparition de démangeaisons ou de saignements.",
  "Cambia utente": "Changer d'utilisateur",
  "Capelli": "Cheveux",
  "Capelli rossi o biondi": "Cheveux roux ou blonds",
  "Carcinoma del rene": "Carcinome du rein",
  "Caricamento…": "Chargement…",
  "Cartella dei progetti:": "Dossier des projets :",
  "Cartella dei tuoi dati (da copiare per il backup):": "Dossier de vos données (à copier pour la sauvegarde) :",
  "Castani": "Châtains",
  "Caviglia destra": "Cheville droite",
  "Caviglia sinistra": "Cheville gauche",
  "Cavo popliteo destro": "Creux poplité droit",
  "Cavo popliteo sinistro": "Creux poplité gauche",
  "Centra sulla mappa": "Centrer sur la carte",
  "Cerca": "Rechercher",
  "Cerca altro (es. \"ugly duckling sign\", \"nail melanoma\"…)": "Rechercher autre chose (p. ex. « ugly duckling sign », « nail melanoma »…)",
  "Cerca nella letteratura": "Rechercher dans la littérature",
  "Cerca una città (es. Torino)": "Rechercher une ville (p. ex. Turin)",
  "Cerco su PubMed…": "Recherche sur PubMed…",
  "Cerco…": "Recherche…",
  "Chi ha avuto un melanoma ha un rischio maggiore di un secondo.": "Avoir eu un mélanome augmente le risque d'en avoir un second.",
  "Chi ha tanti nei, nei atipici o una storia di melanoma dovrebbe proteggersi anche con indici moderati.": "Les personnes ayant beaucoup de grains de beauté, des grains de beauté atypiques ou des antécédents de mélanome doivent se protéger même lorsque l'indice est modéré.",
  "Chi sei?": "Qui êtes-vous ?",
  "Chiave OpenWeather": "Clé OpenWeather",
  "Chiave OpenWeather salvata ({finale}).": "Clé OpenWeather enregistrée ({finale}).",
  "Chiave rimossa.": "Clé supprimée.",
  "Chiave salvata ({finale}) — scrivine una nuova per sostituirla": "Clé enregistrée ({finale}) — saisissez-en une nouvelle pour la remplacer",
  "Chiave salvata.": "Clé enregistrée.",
  "Chiedo la posizione al browser… (potrebbe comparire una richiesta di permesso)": "Demande de la position au navigateur… (une demande d'autorisation peut s'afficher)",
  "Chiudere NeoTracker?": "Fermer NeoTracker ?",
  "Chiudere il programma": "Fermer le programme",
  "Chiudi": "Fermer",
  "Chiudi NeoTracker": "Fermer NeoTracker",
  "Chiudi il programma": "Fermer le programme",
  "Circa il 5-10% dei melanomi si presenta in famiglie con una predisposizione ereditaria (Leachman 2009). Qui trovi i criteri che usano gli specialisti per decidere se proporre una consulenza genetica, i geni coinvolti e la letteratura su ciascuno.": "Environ 5 à 10 % des mélanomes surviennent dans des familles présentant une prédisposition héréditaire (Leachman 2009). Vous trouvez ici les critères que les spécialistes utilisent pour décider de proposer une consultation de génétique, les gènes concernés et la littérature sur chacun.",
  "Citato dalle linee guida NCCN tra i geni da considerare nei pannelli per melanoma (sindrome di Cowden).": "Cité par les recommandations du NCCN parmi les gènes à envisager dans les panels pour le mélanome (syndrome de Cowden).",
  "Classificati come cancerogeni certi per l'uomo (IARC).": "Classés comme cancérogènes certains pour l'homme (CIRC).",
  "Clic per vedere la foto originale a schermo intero": "Cliquez pour voir la photo originale en plein écran",
  "Clicca sul punto esatto del corpo dove si trova il neo (puoi ingrandire prima)": "Cliquez sur l'endroit exact du corps où se trouve le grain de beauté (vous pouvez d'abord zoomer)",
  "Clicca un neo nell'elenco o sulla mappa per vedere lo storico fotografico.": "Cliquez sur un grain de beauté dans la liste ou sur la carte pour voir son historique photographique.",
  "Collo": "Cou",
  "Colore": "Couleur",
  "Colore degli occhi": "Couleur des yeux",
  "Colore naturale dei capelli (da giovane)": "Couleur naturelle des cheveux (dans la jeunesse)",
  "Come ottenere la chiave": "Comment obtenir la clé",
  "Come scattare foto confrontabili": "Comment prendre des photos comparables",
  "Come si legge l'indice UV": "Comment lire l'indice UV",
  "Compila la familiarità nel Profilo": "Renseigner les antécédents familiaux dans le Profil",
  "Compila la sezione 'Familiarità' nel Profilo: senza quei dati non posso verificare i criteri.": "Remplissez la section « Antécédents familiaux » de votre Profil : sans ces données, je ne peux pas vérifier les critères.",
  "Con i dati inseriti non rientri nei criteri più usati. Il test genetico per il melanoma è indicato solo in una piccola minoranza di persone e non viene proposto di routine. Se la tua storia familiare cambia o hai dubbi, aggiorna il profilo e parlane col dermatologo.": "Avec les données saisies, vous ne remplissez pas les critères les plus utilisés. Le test génétique pour le mélanome n'est indiqué que chez une petite minorité de personnes et n'est pas proposé en routine. Si vos antécédents familiaux changent ou si vous avez des doutes, mettez votre profil à jour et parlez-en à votre dermatologue.",
  "Con i dati inseriti non risultano fattori di rischio noti. Completa il profilo se mancano informazioni.": "Avec les données saisies, aucun facteur de risque connu n'apparaît. Complétez votre profil s'il manque des informations.",
  "Con il tuo fototipo ({fototipo})": "Avec votre phototype ({fototipo})",
  "Con o senza test, per chi ha una storia familiare restano fondamentali la protezione dal sole, l'autoesame della pelle e i controlli dermatologici periodici.": "Avec ou sans test, pour les personnes ayant des antécédents familiaux, la protection solaire, l'autoexamen de la peau et les contrôles dermatologiques réguliers restent essentiels.",
  "Conferma": "Confirmer",
  "Confronta": "Comparer",
  "Confronta forma, bordi e colori: se noti differenze, mostra le foto al dermatologo.": "Comparez la forme, les bords et les couleurs : si vous remarquez des différences, montrez les photos à votre dermatologue.",
  "Confronto tra due foto": "Comparaison de deux photos",
  "Consenso": "Consentement",
  "Conta anche il «brutto anatroccolo»: un neo diverso da tutti gli altri. I noduli che crescono rapidamente o sono duri al tatto vanno mostrati subito. Questo promemoria non sostituisce la visita.": "Le « vilain petit canard » compte aussi : un grain de beauté différent de tous les autres. Les nodules qui grossissent rapidement ou sont durs au toucher doivent être montrés sans attendre. Ce rappel ne remplace pas une consultation.",
  "Conta i parenti di sangue (non quelli acquisiti) dello stesso lato della famiglia, materno o paterno: è il criterio che usano i genetisti. Se non lo sai, chiedi a un familiare: queste informazioni sono molto utili.": "Comptez les parents du même sang (pas les alliés) du même côté de la famille, maternel ou paternel : c'est le critère utilisé par les généticiens. Si vous ne savez pas, demandez à un proche : ces informations sont très utiles.",
  "Conta solo i melanomi primari invasivi.": "Seuls les mélanomes primaires invasifs comptent.",
  "Controllo lo stato…": "Vérification de l'état…",
  "Coordinate non valide.": "Coordonnées non valides.",
  "Cosa fare": "Que faire",
  "Cosa sapere prima di un test genetico": "À savoir avant un test génétique",
  "Coscia destra": "Cuisse droite",
  "Coscia sinistra": "Cuisse gauche",
  "Crea un account gratuito su": "Créez un compte gratuit sur",
  "Crea utente": "Créer l'utilisateur",
  "Criteri ABCDE e segno del 'brutto anatroccolo'": "Critères ABCDE et signe du « vilain petit canard »",
  "Criteri semplificati, a scopo informativo. Il test genetico riguarda una piccola minoranza di persone e non è un esame di routine: è lo specialista a decidere se e quale test proporre, di norma dopo una consulenza genetica e partendo, quando possibile, da un familiare che ha avuto la malattia.": "Critères simplifiés, à titre d'information. Le test génétique ne concerne qu'une petite minorité de personnes et n'est pas un examen de routine : c'est au spécialiste de décider si et quel test proposer, en général après une consultation de génétique et, si possible, en partant d'un parent atteint.",
  "Cuoio capelluto (testa)": "Cuir chevelu (tête)",
  "Cursore di confronto": "Curseur de comparaison",
  "D": "D",
  "D = destra del paziente · S = sinistra": "D = droite du patient · G = gauche",
  "Da 50 a 99 nei sul corpo": "De 50 à 99 grains de beauté sur le corps",
  "Da attenzionare": "À surveiller",
  "Da rifotografare?": "Faut-il refaire une photo ?",
  "Dai un nome al neo e controlla la sede.": "Donnez un nom au grain de beauté et vérifiez l'emplacement.",
  "Data della foto troppo vecchia.": "La date de la photo est trop ancienne.",
  "Data dello scatto": "Date de la prise de vue",
  "Data di nascita": "Date de naissance",
  "Data di nascita fuori intervallo.": "Date de naissance hors limites.",
  "Data di nascita non valida (AAAA-MM-GG).": "Date de naissance non valide (AAAA-MM-JJ).",
  "Data non valida: usa il formato AAAA-MM-GG.": "Date non valide : utilisez le format AAAA-MM-JJ.",
  "Dati della persona": "Données de la personne",
  "Dati meteo e UV:": "Données météo et UV :",
  "Dati non validi (JSON).": "Données non valides (JSON).",
  "Dati non validi.": "Données non valides.",
  "Dati orari non disponibili": "Données horaires indisponibles",
  "Dati personali": "Données personnelles",
  "Deep learning e melanoma: revisioni sistematiche": "Apprentissage profond et mélanome : revues systématiques",
  "Dermoscopia e diagnosi precoce (revisioni)": "Dermoscopie et diagnostic précoce (revues)",
  "Dermoscopica": "Dermoscopique",
  "Di qualsiasi grado di parentela.": "De n'importe quel degré de parenté.",
  "Diagnosi totali indicate: {diagnosi}. Leachman 2009 considera melanoma e tumore del pancreas nei parenti di 1o e 2o grado dello stesso lato della famiglia; l'astrocitoma è incluso dalle linee guida NCCN.": "Nombre total de diagnostics indiqués : {diagnosi}. Leachman 2009 retient le mélanome et le cancer du pancréas chez les parents du 1er et du 2e degré du même côté de la famille ; l'astrocytome est inclus par les recommandations du NCCN.",
  "Diametro": "Diamètre",
  "Diametro (mm)": "Diamètre (mm)",
  "Diametro del neo nel tempo": "Diamètre du grain de beauté au fil du temps",
  "Diametro misurato (mm)": "Diamètre mesuré (mm)",
  "Diametro nel tempo": "Diamètre au fil du temps",
  "Diametro:": "Diamètre :",
  "Diametro: da {da} a {a} mm.": "Diamètre : de {da} à {a} mm.",
  "Diametro: {diff} mm di differenza.": "Diamètre : {diff} mm de différence.",
  "Diminuisci: {voce}": "Diminuer : {voce}",
  "Donna": "Femme",
  "Dopo": "Après",
  "Dove si trovano": "Où ils se trouvent",
  "Efelidi": "Éphélides",
  "Efelidi (lentiggini)": "Éphélides (taches de rousseur)",
  "Elenco di fattori noti dalla letteratura, non un punteggio validato: non stima la probabilità di ammalarsi.": "Liste de facteurs connus dans la littérature, et non un score validé : elle n'estime pas la probabilité de tomber malade.",
  "Elimina": "Supprimer",
  "Elimina definitivamente": "Supprimer définitivement",
  "Elimina foto": "Supprimer la photo",
  "Elimina questo neo e le sue foto": "Supprimer ce grain de beauté et ses photos",
  "Eliminare questa foto?": "Supprimer cette photo ?",
  "Eliminare «{nome}»?": "Supprimer « {nome} » ?",
  "Email non valida.": "Adresse e-mail non valide.",
  "Email per PubMed": "E-mail pour PubMed",
  "Email salvata.": "E-mail enregistré.",
  "Errore imprevisto: {e}": "Erreur inattendue : {e}",
  "Errore interno. I dettagli sono nel file neotracker.log nella cartella dei dati.": "Erreur interne. Les détails se trouvent dans le fichier neotracker.log du dossier des données.",
  "Errore {codice}": "Erreur {codice}",
  "Esci dal programma": "Quitter le programme",
  "Esiste già un utente con questo nome.": "Un utilisateur portant ce nom existe déjà.",
  "Esposizione al sole": "Exposition au soleil",
  "Estremo": "Extrême",
  "Età": "Âge",
  "Età, sesso e fenotipo non cambiano l'uscita delle reti neurali: servono a mostrarti i fattori di rischio, a scegliere la letteratura, a valutare i criteri di genetica e a stimare il tempo di scottatura.": "L'âge, le sexe et le phénotype ne modifient pas le résultat des réseaux de neurones : ils servent à vous montrer les facteurs de risque, à choisir la littérature, à évaluer les critères de génétique et à estimer le temps avant un coup de soleil.",
  "Evita il sole nelle ore centrali e proteggi bene la pelle.": "Évitez le soleil aux heures centrales de la journée et protégez bien votre peau.",
  "Evita l'esposizione diretta: la pelle non protetta può scottarsi in pochi minuti.": "Évitez l'exposition directe : une peau non protégée peut brûler en quelques minutes.",
  "Evoluzione": "Évolution",
  "FRONTE": "FACE",
  "Facoltativa": "Facultatif",
  "Fajuyigbe D, Young AR. The impact of skin colour on human photobiological responses. Pigment Cell Melanoma Res 2016;29:607-18 (dose minima di eritema per fototipo)": "Fajuyigbe D, Young AR. The impact of skin colour on human photobiological responses. Pigment Cell Melanoma Res 2016;29:607-18 (dose érythémale minimale selon le phototype)",
  "Familiarità": "Antécédents familiaux",
  "Fattori di rischio indicati:": "Facteurs de risque indiqués :",
  "Fattori di rischio presenti": "Facteurs de risque présents",
  "Fenotipo: pelle, capelli, occhi": "Phénotype : peau, cheveux, yeux",
  "File della foto non trovato.": "Fichier de la photo introuvable.",
  "Fonte dell'indice UV cambiata.": "Source de l'indice UV modifiée.",
  "Fonte dell'indice UV non valida.": "Source de l'indice UV non valide.",
  "Fonte:": "Source :",
  "Fonti": "Sources",
  "Formato non supportato: servono JPG, PNG, WEBP o BMP.": "Format non pris en charge : JPG, PNG, WEBP ou BMP requis.",
  "Formato non supportato: servono JPG, PNG, WEBP o BMP. Le foto HEIC degli iPhone vanno convertite in JPG (impostazioni fotocamera: 'Più compatibile').": "Format non pris en charge : JPG, PNG, WEBP ou BMP requis. Les photos HEIC des iPhone doivent être converties en JPG (réglages de l'appareil photo : « Le plus compatible »).",
  "Foto a fuoco, con il neo al centro e la pelle ben visibile (sposta i peli, se serve).": "Photo nette, avec le grain de beauté au centre et la peau bien visible (écartez les poils si nécessaire).",
  "Foto del {data}": "Photo du {data}",
  "Foto eliminata.": "Photo supprimée.",
  "Foto non trovata.": "Photo introuvable.",
  "Foto normale": "Photo normale",
  "Foto normale (smartphone)": "Photo normale (smartphone)",
  "Foto originale": "Photo originale",
  "Foto salvata ({data}).": "Photo enregistrée ({data}).",
  "Foto salvata ({data}, data letta dalla foto).": "Photo enregistrée ({data}, date lue dans la photo).",
  "Fotografia sequenziale e monitoraggio dei nei nel tempo": "Photographie séquentielle et suivi des grains de beauté au fil du temps",
  "Fototipo": "Phototype",
  "Fototipo (classificazione di Fitzpatrick)": "Phototype (classification de Fitzpatrick)",
  "Fototipo chiaro (I-II)": "Phototype clair (I-II)",
  "Fototipo, età e familiarità non cambiano il risultato delle reti neurali (guardano solo i pixel): servono a contestualizzare il rischio.": "Le phototype, l'âge et les antécédents familiaux ne modifient pas le résultat des réseaux de neurones (qui ne regardent que les pixels) : ils servent à replacer le risque dans son contexte.",
  "Fronte": "Face",
  "Fronte e cuoio capelluto": "Front et cuir chevelu",
  "Gamba (stinco) destra": "Jambe (tibia) droite",
  "Gamba (stinco) sinistra": "Jambe (tibia) gauche",
  "Gene": "Gène",
  "Gene dei telomeri (complesso shelterin): varianti rare in famiglie con melanoma.": "Gène des télomères (complexe shelterin) : variants rares dans des familles atteintes de mélanome.",
  "Gene dei telomeri: varianti rare in alcune famiglie con melanoma.": "Gène des télomères : variants rares dans certaines familles atteintes de mélanome.",
  "Gene non presente nell'elenco.": "Gène absent de la liste.",
  "Gene {n} di {tot} ({nome})…": "Gène {n} sur {tot} ({nome})…",
  "Genetica": "Génétique",
  "Genitori, fratelli o figli.": "Parents, frères, sœurs ou enfants.",
  "Genitori, fratelli, sorelle, figli.": "Parents, frères, sœurs, enfants.",
  "Ginocchio destro": "Genou droit",
  "Ginocchio sinistro": "Genou gauche",
  "Gli articoli sono scelti da una ricerca automatica e non sono stati valutati da NeoTracker: leggili con il tuo medico.": "Les articles sont choisis par une recherche automatique et n'ont pas été évalués par NeoTracker : lisez-les avec votre médecin.",
  "Gluteo destro": "Fesse droite",
  "Gluteo sinistro": "Fesse gauche",
  "Gomito destro": "Coude droit",
  "Gomito sinistro": "Coude gauche",
  "Grigi/bianchi": "Gris/blancs",
  "Hai indicato di aver già eseguito un test genetico: porta il referto al dermatologo.": "Vous avez indiqué avoir déjà fait un test génétique : apportez le compte rendu à votre dermatologue.",
  "Hai scelto OpenWeather ma manca la chiave (Impostazioni): mostro i dati di Open-Meteo.": "Vous avez choisi OpenWeather mais la clé est absente (Paramètres) : affichage des données d'Open-Meteo.",
  "Hai scelto OpenWeather ma non c'è ancora una chiave: finché manca, il programma usa Open-Meteo.": "Vous avez choisi OpenWeather mais il n'y a pas encore de clé : tant qu'elle manque, le programme utilise Open-Meteo.",
  "Ho avuto (o ho) uno di questi tumori:": "J'ai eu (ou j'ai) l'un de ces cancers :",
  "Ho avuto altri tumori della pelle (basalioma, spinalioma)": "J'ai eu d'autres cancers de la peau (carcinome basocellulaire ou épidermoïde)",
  "Ho già fatto un test genetico per il melanoma?": "Ai-je déjà fait un test génétique pour le mélanome ?",
  "Ho letto e capito queste avvertenze": "J'ai lu et compris ces avertissements",
  "Ho verificato la mia storia familiare (anche se la risposta è «nessuno»)": "J'ai vérifié mes antécédents familiaux (même si la réponse est « aucun »)",
  "I dati (anche di salute) restano su questo computer. Escono solo le richieste che attivi tu: indice UV (coordinate approssimate), ricerche su PubMed (solo i termini cercati) e, solo se lo attivi, l'invio della foto a SkinSense.": "Vos données (y compris de santé) restent sur cet ordinateur. Seules les requêtes que vous activez en sortent : indice UV (coordonnées approximatives), recherches sur PubMed (uniquement les termes recherchés) et, seulement si vous l'activez, l'envoi de la photo à SkinSense.",
  "I dati inseriti rientrano in almeno un criterio descritto in letteratura. Ti consigliamo di parlarne con il dermatologo o con un medico genetista (consulenza genetica oncologica): sarà lo specialista a decidere se e quale test proporre, di norma dopo la consulenza e, quando possibile, partendo da un familiare affetto. Geni più citati dalle linee guida: {geni}. L'uso dei pannelli multigene è ancora oggetto di discussione tra gli specialisti: per questo conta la consulenza prima del test.": "Les données saisies répondent à au moins un critère décrit dans la littérature. Nous vous conseillons d'en parler avec votre dermatologue ou un médecin généticien (consultation de génétique oncologique) : c'est le spécialiste qui décidera si et quel test proposer, en général après la consultation et, si possible, en partant d'un parent atteint. Gènes les plus cités par les recommandations : {geni}. L'utilisation des panels multigéniques fait encore débat entre spécialistes : c'est pourquoi la consultation avant le test est importante.",
  "I geni più studiati": "Les gènes les plus étudiés",
  "I metodi sono addestrati su fotografie diverse dalle tue: cambiare luce, distanza o fotocamera può cambiare la risposta.": "Les méthodes sont entraînées sur des photographies différentes des vôtres : changer d'éclairage, de distance ou d'appareil peut modifier la réponse.",
  "I numeri corrispondono alle schede seguenti. Sulla figura: a sinistra la vista frontale, a destra quella posteriore.": "Les numéros correspondent aux fiches suivantes. Sur la figure : la vue de face à gauche, la vue de dos à droite.",
  "I raggi ultravioletti sono il principale fattore di rischio modificabile per il melanoma. Qui vedi quanto sono forti oggi dove ti trovi.": "Les rayons ultraviolets sont le principal facteur de risque modifiable du mélanome. Vous voyez ici leur intensité aujourd'hui là où vous vous trouvez.",
  "I risultati sono stime sperimentali e possono sbagliare in entrambe le direzioni: un esito rassicurante non esclude un melanoma, un esito di attenzione non significa che ci sia.": "Les résultats sont des estimations expérimentales et peuvent se tromper dans les deux sens : un résultat rassurant n'exclut pas un mélanome, un résultat d'alerte ne signifie pas qu'il y en a un.",
  "I tuoi dati rispetto ai criteri": "Vos données au regard des critères",
  "I tuoi nei ({n})": "Vos grains de beauté ({n})",
  "Identificativo di pagina non valido.": "Identifiant de page non valide.",
  "Il computer non riesce a determinare la posizione. Cerca la città per nome.": "L'ordinateur ne parvient pas à déterminer la position. Recherchez la ville par son nom.",
  "Il file non è un'immagine leggibile o è troppo grande.": "Le fichier n'est pas une image lisible ou est trop volumineux.",
  "Il file non è un'immagine leggibile, è danneggiato o ha troppi pixel (massimo {mp} megapixel).": "Le fichier n'est pas une image lisible, est endommagé ou comporte trop de pixels (maximum {mp} mégapixels).",
  "Il file è troppo grande (massimo 40 MB).": "Le fichier est trop volumineux (maximum 40 Mo).",
  "Il file è vuoto.": "Le fichier est vide.",
  "Il metodo 3 NON ha analizzato la foto: il progetto e' un prototipo senza modello. Il suo server si limita a ricevere l'immagine (nessuna rete neurale), quindi qualunque testo rassicurante mostri non deriva da un'analisi e non ha alcun valore.": "La méthode 3 n'a PAS analysé la photo : le projet est un prototype sans modèle. Son serveur se contente de recevoir l'image (aucun réseau de neurones), donc tout texte rassurant affiché ne provient pas d'une analyse et n'a aucune valeur.",
  "Il metodo 5 e' un'app Android: non puo' girare dal PC. Installa l'APK sul telefono, inquadra il neo e annota a mano il risultato qui sotto.\nRisultato dell'app sul telefono: ______________________________": "La méthode 5 est une application Android : elle ne peut pas tourner sur le PC. Installez l'APK sur le téléphone, cadrez le grain de beauté et notez le résultat à la main ci-dessous.\nRésultat de l'application sur le téléphone : ______________________________",
  "Il metodo {n} ha detto che:": "La méthode {n} a indiqué :",
  "Il nome": "Le nom",
  "Il numero di nei è uno dei fattori di rischio più forti.": "Le nombre de grains de beauté est l'un des facteurs de risque les plus forts.",
  "Il programma si spegne. Un'analisi in corso viene interrotta. I dati restano salvati.": "Le programme va s'arrêter. Une analyse en cours sera interrompue. Vos données restent enregistrées.",
  "Il risultato riguarda anche i familiari di sangue: per questo la consulenza prima e dopo il test è parte del percorso.": "Le résultat concerne aussi les parents du même sang : c'est pourquoi la consultation avant et après le test fait partie du parcours.",
  "Il servizio Open-Meteo non risponde ({e}).": "Le service Open-Meteo ne répond pas ({e}).",
  "Immagine personale": "Image personnelle",
  "Immagine personale salvata.": "Image personnelle enregistrée.",
  "Immagine rimossa.": "Image supprimée.",
  "Immunosoppressione (terapie, trapianto)": "Immunosuppression (traitements, greffe)",
  "Impostazioni": "Paramètres",
  "In coda (posizione {n})…": "En file d'attente (position {n})…",
  "In coda…": "En file d'attente…",
  "In inglese": "En anglais",
  "Incolla la chiave qui sopra e premi «Prova la chiave». Dopo l'iscrizione la chiave può impiegare qualche minuto ad attivarsi. Il programma prova prima One Call 4.0 e, se la chiave è di un abbonamento più vecchio, One Call 3.0.": "Collez la clé ci-dessus et appuyez sur « Tester la clé ». Après la souscription, la clé peut mettre quelques minutes à s'activer. Le programme essaie d'abord One Call 4.0 et, si la clé correspond à un abonnement plus ancien, One Call 3.0.",
  "Incolla prima la chiave.": "Collez d'abord la clé.",
  "Incolla qui la chiave (32 lettere e numeri)": "Collez ici la clé (32 lettres et chiffres)",
  "Indice UV": "Indice UV",
  "Indice UV di oggi": "Indice UV du jour",
  "Indice UV non disponibile": "Indice UV indisponible",
  "Indice UV ora per ora nelle prossime 24 ore": "Indice UV heure par heure pour les prochaines 24 heures",
  "Indice UV: fonte dei dati": "Indice UV : source des données",
  "Indirizzo non ammesso.": "Adresse non autorisée.",
  "Indirizzo sconosciuto.": "Adresse inconnue.",
  "Indirizzo troppo lungo.": "Adresse trop longue.",
  "Ingrandisci": "Agrandir",
  "Inguine destro": "Aine droite",
  "Inguine sinistro": "Aine gauche",
  "Inviare le foto a SkinSense?": "Envoyer les photos à SkinSense ?",
  "Irregolari, frastagliati o sfumati.": "Irréguliers, dentelés ou flous.",
  "Iscriviti all'abbonamento «One Call API» a pagamento per chiamata": "Souscrivez à l'abonnement « One Call API » payant à l'appel",
  "JPG, PNG, WEBP o BMP · fino a 60 MB": "JPG, PNG, WEBP ou BMP · jusqu'à 60 Mo",
  "L'OMS consiglia di proteggersi a partire da un indice UV di 3.": "L'OMS recommande de se protéger à partir d'un indice UV de 3.",
  "L'analisi di questa foto è in corso: attendi che finisca.": "L'analyse de cette photo est en cours : attendez qu'elle se termine.",
  "L'analisi non ha prodotto il rapporto. Ultime righe del log: {log}": "L'analyse n'a pas produit le rapport. Dernières lignes du journal : {log}",
  "L'analisi non è riuscita.": "L'analyse a échoué.",
  "L'immagine supera {mb} MB.": "L'image dépasse {mb} Mo.",
  "L'indice è una previsione: il valore reale dipende da nuvole, quota e riflessi.": "L'indice est une prévision : la valeur réelle dépend des nuages, de l'altitude et des réflexions.",
  "La chiave OpenWeather contiene caratteri non validi (di solito sono 32 lettere/numeri).": "La clé OpenWeather contient des caractères non valides (elle comporte généralement 32 lettres/chiffres).",
  "La chiave resta salvata solo sul tuo computer e non viene mai mostrata né inviata alla pagina web del programma: la usa il programma Python per chiamare OpenWeather.": "La clé reste enregistrée uniquement sur votre ordinateur et n'est jamais affichée ni envoyée à la page web du programme : c'est le programme Python qui l'utilise pour appeler OpenWeather.",
  "La chiave sarà cancellata da questo computer. Potrai inserirla di nuovo quando vuoi.": "La clé sera supprimée de cet ordinateur. Vous pourrez la saisir à nouveau quand vous voulez.",
  "La data della foto non può essere nel futuro.": "La date de la photo ne peut pas être dans le futur.",
  "La foto del {data} e il suo rapporto di analisi saranno cancellati per sempre.": "La photo du {data} et son rapport d'analyse seront supprimés définitivement.",
  "La foto resta sul tuo computer: SkinSense (servizio online) è disattivato.": "La photo reste sur votre ordinateur : SkinSense (service en ligne) est désactivé.",
  "La foto supera i {mb} MB: riducila o scegline un'altra.": "La photo dépasse {mb} Mo : réduisez-la ou choisissez-en une autre.",
  "La foto supera {MAX_MB_FOTO} MB.": "La photo dépasse {MAX_MB_FOTO} Mo.",
  "La libreria Pillow è vecchia e ha problemi di sicurezza noti: aggiornala con «py -m pip install -U pillow».": "La bibliothèque Pillow est ancienne et présente des failles de sécurité connues : mettez-la à jour avec « py -m pip install -U pillow ».",
  "La mia posizione ({lat}; {lon})": "Ma position ({lat} ; {lon})",
  "La posizione resta salvata solo su questo computer; viene inviata al servizio meteo (coordinate arrotondate) per ottenere l'indice UV.": "La position est enregistrée uniquement sur cet ordinateur ; elle est envoyée au service météo (coordonnées arrondies) pour obtenir l'indice UV.",
  "La prima analisi può richiedere diversi minuti (i modelli vengono caricati in memoria).": "La première analyse peut prendre plusieurs minutes (les modèles sont chargés en mémoire).",
  "La scelta vale per tutti gli utenti di questo computer. Il testo originale e vincolante delle avvertenze legali è quello italiano; il rapporto di testo completo resta in italiano.": "Ce choix vaut pour tous les utilisateurs de cet ordinateur. Le texte original et juridiquement contraignant des avertissements est le texte italien ; le rapport texte complet reste en italien.",
  "La variante p.E318K aumenta il rischio di melanoma e di carcinoma renale e si associa a molti nei.": "Le variant p.E318K augmente le risque de mélanome et de carcinome rénal et s'associe à de nombreux grains de beauté.",
  "La vista deve essere 'fronte' o 'retro'.": "La vue doit être 'fronte' ou 'retro'.",
  "Lampade": "Cabines de bronzage",
  "Lampade abbronzanti": "Lampes à bronzer",
  "Lampade o lettini abbronzanti": "Lampes ou cabines de bronzage",
  "Lavoro o attività prolungata all'aperto": "Travail ou activité prolongée en plein air",
  "Lavoro o faccio attività per molte ore all'aperto": "Je travaille ou pratique des activités en plein air pendant de nombreuses heures",
  "Le due metà del neo non si somigliano.": "Les deux moitiés du grain de beauté ne se ressemblent pas.",
  "Le informazioni su rischio, letteratura e genetica sono divulgative e non sostituiscono la consulenza di un medico o di un genetista.": "Les informations sur le risque, la littérature et la génétique sont données à titre informatif et ne remplacent pas l'avis d'un médecin ou d'un généticien.",
  "Le linee guida raccomandano il test solo dopo una selezione accurata dei candidati e un'adeguata consulenza (Rossi 2019); l'uso dei pannelli multigene è ancora discusso.": "Les recommandations préconisent le test uniquement après une sélection rigoureuse des candidats et une consultation adaptée (Rossi 2019) ; l'utilisation des panels multigéniques fait encore débat.",
  "Le nuvole sottili non fermano gran parte degli UV: l'indice può restare alto anche con il cielo velato.": "Les nuages fins n'arrêtent pas une grande partie des UV : l'indice peut rester élevé même par ciel voilé.",
  "Le ore centrali (circa 11-16) sono quelle con l'indice più alto.": "Les heures centrales (environ 11 h-16 h) sont celles où l'indice est le plus élevé.",
  "Le ricerche partono da questo computer verso PubMed (nessun dato personale viene inviato). I risultati si salvano per 7 giorni.": "Les recherches partent de cet ordinateur vers PubMed (aucune donnée personnelle n'est envoyée). Les résultats sont conservés 7 jours.",
  "Le ricerche usano le E-utilities pubbliche di PubMed. NCBI chiede, per cortesia, un'email di contatto: è facoltativa e viene inviata solo a PubMed.": "Les recherches utilisent les E-utilities publiques de PubMed. Le NCBI demande, par courtoisie, une adresse e-mail de contact : elle est facultative et n'est envoyée qu'à PubMed.",
  "Le sezioni «scelte per te» usano parole legate al tuo profilo (per esempio fototipo o numero di nei): se preferisci non inviarle, non scansionare quella sezione.": "Les sections « choisies pour vous » utilisent des mots liés à votre profil (par exemple le phototype ou le nombre de grains de beauté) : si vous préférez ne pas les envoyer, ne lancez pas l'analyse de cette section.",
  "Leachman 2009 e 2017; NCCN": "Leachman 2009 et 2017 ; NCCN",
  "Leachman 2017; NCCN": "Leachman 2017 ; NCCN",
  "Leggi l'abstract": "Lire le résumé",
  "Lentigo maligna e melanoma del volto": "Lentigo malin et mélanome du visage",
  "Letteratura": "Littérature",
  "Letteratura scientifica": "Littérature scientifique",
  "Letteratura: PubMed": "Littérature : PubMed",
  "Linea guida": "Recommandation",
  "Linee guida e criteri per il test genetico": "Recommandations et critères pour le test génétique",
  "Lingua": "Langue",
  "Lingua dell'interfaccia": "Langue de l'interface",
  "Lingua non supportata.": "Langue non prise en charge.",
  "Lucas RM et al. Are current guidelines for sun protection optimal for health? Photochem Photobiol Sci 2018;17:1956-63 (UV Index e dose di eritema)": "Lucas RM et al. Are current guidelines for sun protection optimal for health? Photochem Photobiol Sci 2018;17:1956-63 (indice UV et dose érythémale)",
  "Mai": "Jamais",
  "Manca la posizione": "Position manquante",
  "Mano destra": "Main droite",
  "Mano sinistra": "Main gauche",
  "Mappa dei nei": "Carte des grains de beauté",
  "Mappa del corpo umano: fronte a sinistra, retro a destra": "Carte du corps humain : face à gauche, dos à droite",
  "Massimo di oggi": "Maximum d'aujourd'hui",
  "Melanoma acrale (mani, piedi, unghie): dermoscopia": "Mélanome acral (mains, pieds, ongles) : dermoscopie",
  "Melanoma dell'occhio (uveale)": "Mélanome de l'œil (uvéal)",
  "Melanoma e immunosoppressione": "Mélanome et immunosuppression",
  "Melanoma ereditario": "Mélanome héréditaire",
  "Melanoma ereditario e test genetico": "Mélanome héréditaire et test génétique",
  "Melanoma già diagnosticato": "Mélanome déjà diagnostiqué",
  "Melanoma nelle pelli scure (spesso acrale)": "Mélanome sur peau foncée (souvent acral)",
  "Melanoma personale e parente di primo grado con tumore del pancreas": "Mélanome personnel et parent du premier degré atteint d'un cancer du pancréas",
  "Melanoma-Detector (VukIG)": "Melanoma-Detector (VukIG)",
  "Melanomi già diagnosticati": "Mélanomes déjà diagnostiqués",
  "Melanomi già diagnosticati a me": "Mélanomes déjà diagnostiqués chez moi",
  "Melanomi primari indicati: {mel_pers}.": "Mélanomes primaires indiqués : {mel_pers}.",
  "Meno di 25": "Moins de 25",
  "Mesotelioma": "Mésothéliome",
  "Meta-analisi": "Méta-analyse",
  "Metodi in disaccordo": "Méthodes en désaccord",
  "Metodo 1 - App 1 (Deborah Adedigba)": "Méthode 1 - App 1 (Deborah Adedigba)",
  "Metodo 1 disattivato dalle impostazioni.": "Méthode 1 désactivée dans les paramètres.",
  "Metodo 2 - SkinSense (servizio online)": "Méthode 2 - SkinSense (service en ligne)",
  "Metodo 2 non eseguito (disattivato nelle impostazioni): la foto non e' uscita dal PC.": "Méthode 2 non exécutée (désactivée dans les paramètres) : la photo n'a pas quitté le PC.",
  "Metodo 4 - vatsal30": "Méthode 4 - vatsal30",
  "Metodo 4 disattivato dalle impostazioni.": "Méthode 4 désactivée dans les paramètres.",
  "Metodo {n}": "Méthode {n}",
  "Metti accanto al neo un righello o una moneta: serve per misurare il diametro.": "Placez une règle ou une pièce de monnaie à côté du grain de beauté : cela permet de mesurer le diamètre.",
  "Moderato": "Modéré",
  "Modifica data/misura": "Modifier la date/la mesure",
  "Modifica foto": "Modifier la photo",
  "Modifica i dati nel Profilo": "Modifier les données dans le Profil",
  "Modifiche non salvate…": "Modifications non enregistrées…",
  "Molte": "Beaucoup",
  "Molte efelidi (lentiggini)": "Beaucoup d'éphélides (taches de rousseur)",
  "Molte scottature con vesciche": "Beaucoup de coups de soleil avec cloques",
  "Molti nei o nei atipici: sorveglianza": "Beaucoup de grains de beauté ou grains de beauté atypiques : surveillance",
  "Molto alto": "Très élevé",
  "Mostra affiancate": "Afficher côte à côte",
  "Mostra tutto il corpo": "Afficher tout le corps",
  "NCCN": "NCCN",
  "NCCN Clinical Practice Guidelines in Oncology: Melanoma: Cutaneous (versione corrente; il testo completo richiede una registrazione gratuita)": "NCCN Clinical Practice Guidelines in Oncology: Melanoma: Cutaneous (version actuelle ; le texte complet nécessite une inscription gratuite)",
  "Nei archiviati ({n})": "Grains de beauté archivés ({n})",
  "Nei atipici": "Grains de beauté atypiques",
  "Nei atipici (displastici)": "Grains de beauté atypiques (dysplasiques)",
  "Nei grandi, irregolari, di più colori: vanno seguiti nel tempo.": "Grains de beauté grands, irréguliers, de plusieurs couleurs : ils doivent être suivis dans le temps.",
  "Neo archiviato. Lo trovi in fondo all'elenco.": "Grain de beauté archivé. Vous le trouverez en bas de la liste.",
  "Neo con foto": "Grain de beauté avec photos",
  "Neo eliminato.": "Grain de beauté supprimé.",
  "Neo non trovato.": "Grain de beauté introuvable.",
  "Neo salvato. Ora aggiungi la prima foto: sarà la tua \"foto storica\".": "Grain de beauté enregistré. Ajoutez maintenant la première photo : ce sera votre « photo de référence ».",
  "Neo {n}": "Grain de beauté {n}",
  "NeoTracker chiuso": "NeoTracker fermé",
  "NeoTracker non risponde": "NeoTracker ne répond pas",
  "NeoTracker non è un dispositivo medico e non fa diagnosi.": "NeoTracker n'est pas un dispositif médical et ne pose aucun diagnostic.",
  "NeoTracker non è un servizio di consulenza genetica. Per una valutazione personale rivolgiti al dermatologo o a un centro di genetica oncologica.": "NeoTracker n'est pas un service de conseil génétique. Pour une évaluation personnelle, adressez-vous à votre dermatologue ou à un centre de génétique oncologique.",
  "NeoTracker non è uno strumento medico e non fa diagnosi. Per qualsiasi neo che cambia, sanguina, prude o ti preoccupa, rivolgiti a un dermatologo.": "NeoTracker n'est pas un outil médical et ne pose aucun diagnostic. Pour tout grain de beauté qui change, saigne, démange ou vous inquiète, consultez un dermatologue.",
  "NeoTracker è chiuso": "NeoTracker est fermé",
  "Neri": "Noirs",
  "Nessun allarme dai modelli": "Aucune alerte des modèles",
  "Nessun articolo trovato.": "Aucun article trouvé.",
  "Nessun metodo ha prodotto un risultato: controlla i motivi indicati sotto.": "Aucune méthode n'a produit de résultat : consultez les motifs indiqués ci-dessous.",
  "Nessun neo ancora": "Aucun grain de beauté pour l'instant",
  "Nessun risultato": "Aucun résultat",
  "Nessuna": "Aucune",
  "Nessuna città trovata con questo nome.": "Aucune ville trouvée avec ce nom.",
  "Nessuna foto ancora registrata.": "Aucune photo enregistrée pour l'instant.",
  "Nessuna foto: aggiungi la prima": "Aucune photo : ajoutez la première",
  "Nessuna immagine impostata.": "Aucune image définie.",
  "Nessuna protezione particolare per le attività normali; occhiali da sole nelle giornate luminose.": "Aucune protection particulière pour les activités normales ; lunettes de soleil les jours lumineux.",
  "Nessuno dei metodi che hanno risposto segnala la lesione come sospetta. Questo NON esclude un melanoma: gli strumenti non sono validati clinicamente e sbagliano anche in questa direzione. Se il neo è asimmetrico, ha bordi irregolari, colori diversi, è più grande di 6 mm o è cambiato nel tempo, la visita resta necessaria.": "Aucune des méthodes ayant répondu ne signale la lésion comme suspecte. Cela n'exclut PAS un mélanome : ces outils ne sont pas validés cliniquement et se trompent aussi dans ce sens. Si le grain de beauté est asymétrique, a des bords irréguliers, plusieurs couleurs, mesure plus de 6 mm ou a changé avec le temps, la consultation reste nécessaire.",
  "No": "Non",
  "Nome": "Nom",
  "Nome del neo": "Nom du grain de beauté",
  "Nome della città": "Nom de la ville",
  "Nome o soprannome": "Nom ou surnom",
  "Non ancora scansionata.": "Pas encore analysée.",
  "Non ancora scansionato": "Pas encore analysé",
  "Non cambiano il risultato delle reti neurali, che guardano solo i pixel della foto. Servono a: (1) dare un contesto al rischio, (2) scegliere la letteratura scientifica adatta a te, (3) verificare i criteri per la consulenza genetica, (4) calcolare quanto tempo puoi stare al sole prima di scottarti. Tutto resta sul tuo computer.": "Elles ne modifient pas le résultat des réseaux de neurones, qui ne regardent que les pixels de la photo. Elles servent à : (1) replacer le risque dans son contexte, (2) choisir la littérature scientifique adaptée à vous, (3) vérifier les critères de consultation de génétique, (4) calculer combien de temps vous pouvez rester au soleil avant de brûler. Tout reste sur votre ordinateur.",
  "Non ci sono nei da stampare.": "Il n'y a aucun grain de beauté à imprimer.",
  "Non consentito.": "Non autorisé.",
  "Non indicato": "Non indiqué",
  "Non lo so: lascia vuoto, puoi tornare più tardi.": "Je ne sais pas : laissez vide, vous pourrez y revenir plus tard.",
  "Non riesci? Stima dall'indirizzo internet": "Vous n'y arrivez pas ? Estimer à partir de l'adresse internet",
  "Non riesco a contattare NeoTracker. Il programma potrebbe essere stato chiuso: riaprilo dall'icona sul Desktop.": "Impossible de joindre NeoTracker. Le programme a peut-être été fermé : rouvrez-le avec l'icône du Bureau.",
  "Non riesco a leggere questa immagine. Prova con un JPG o un PNG.": "Impossible de lire cette image. Essayez avec un JPG ou un PNG.",
  "Non riesco a ridurre questa immagine.": "Impossible de réduire cette image.",
  "Non so": "Ne sait pas",
  "Non soddisfatto": "Non satisfait",
  "Non trovo melanoma_batch.py: deve stare nella stessa cartella di neotracker.py (oppure in {CARTELLA_REPO}).": "Impossible de trouver melanoma_batch.py : il doit se trouver dans le même dossier que neotracker.py (ou dans {CARTELLA_REPO}).",
  "Nonni, zii, nipoti (2° grado).": "Grands-parents, oncles et tantes, neveux et nièces (2e degré).",
  "Note": "Notes",
  "Note sul neo…": "Notes sur le grain de beauté…",
  "Note:": "Notes :",
  "Nuca e collo": "Nuque et cou",
  "Nulla viene inviato online, tranne le richieste che attivi tu (meteo UV, letteratura PubMed, SkinSense).": "Rien n'est envoyé en ligne, sauf les requêtes que vous activez (météo UV, littérature PubMed, SkinSense).",
  "Numero di nei": "Nombre de grains de beauté",
  "Nuovo neo": "Nouveau grain de beauté",
  "Nuovo utente": "Nouvel utilisateur",
  "OMS/OMM/UNEP/ICNIRP - Global Solar UV Index: A Practical Guide (2002)": "OMS/OMM/PNUE/ICNIRP - Global Solar UV Index: A Practical Guide (2002)",
  "Occhi": "Yeux",
  "Occhi chiari": "Yeux clairs",
  "Oggi i raggi UV sono bassi": "Les rayons UV sont faibles aujourd'hui",
  "Oggi i raggi UV sono dannosi per pelle non protetta": "Les rayons UV sont nocifs aujourd'hui pour une peau non protégée",
  "Oggi i raggi UV sono molto dannosi": "Les rayons UV sont très nocifs aujourd'hui",
  "One Call {n}: {t}": "One Call {n} : {t}",
  "Open-Meteo (predefinita)": "Open-Meteo (par défaut)",
  "OpenWeather ha rifiutato la chiave (401): controlla che sia corretta e che sul tuo account sia attivo l'abbonamento 'One Call API' (pagamento a chiamata, 1.000 chiamate al giorno gratuite). Dopo l'iscrizione la chiave può impiegare qualche minuto ad attivarsi.": "OpenWeather a refusé la clé (401) : vérifiez qu'elle est correcte et que l'abonnement « One Call API » (paiement à l'appel, 1 000 appels gratuits par jour) est actif sur votre compte. Après la souscription, la clé peut mettre quelques minutes à s'activer.",
  "OpenWeather non disponibile ({e}). Mostro i dati di Open-Meteo.": "OpenWeather indisponible ({e}). Affichage des données d'Open-Meteo.",
  "OpenWeather: limite di chiamate raggiunto (429).": "OpenWeather : limite d'appels atteinte (429).",
  "Operazione non consentita su questo indirizzo.": "Opération non autorisée sur cette adresse.",
  "Orecchio destro": "Oreille droite",
  "Orecchio sinistro": "Oreille gauche",
  "Origine non ammessa.": "Origine non autorisée.",
  "Pagina non trovata.": "Page introuvable.",
  "Parente di primo grado con melanoma": "Parent du premier degré atteint de mélanome",
  "Parenti con astrocitoma (tumore del cervello)": "Parents atteints d'astrocytome (tumeur du cerveau)",
  "Parenti con carcinoma del rene": "Parents atteints de carcinome du rein",
  "Parenti con melanoma dell'occhio (uveale)": "Parents atteints de mélanome de l'œil (uvéal)",
  "Parenti con mesotelioma": "Parents atteints de mésothéliome",
  "Parenti con tumore del pancreas (in tutto)": "Parents atteints d'un cancer du pancréas (au total)",
  "Parenti di 1° grado con melanoma": "Parents du 1er degré atteints de mélanome",
  "Passa il puntatore sul corpo per vedere la zona": "Passez le pointeur sur le corps pour voir la zone",
  "Pelle che scotta facilmente e si abbronza poco.": "Peau qui brûle facilement et bronze peu.",
  "Pelle chiara-olivastra. Scotta a volte, si abbronza gradualmente.": "Peau claire à mate. Brûle parfois, bronze progressivement.",
  "Pelle chiara. Scotta facilmente, si abbronza poco.": "Peau claire. Brûle facilement, bronze peu.",
  "Pelle molto chiara. Scotta sempre, non si abbronza mai (spesso capelli rossi, lentiggini).": "Peau très claire. Brûle toujours, ne bronze jamais (souvent cheveux roux, taches de rousseur).",
  "Pelle molto scura. Non scotta.": "Peau très foncée. Ne brûle pas.",
  "Pelle olivastra. Scotta poco, si abbronza facilmente.": "Peau mate. Brûle peu, bronze facilement.",
  "Pelle scura. Scotta raramente.": "Peau foncée. Brûle rarement.",
  "Per chiudere NeoTracker basta chiudere questa finestra con la X in alto a destra: il programma si spegne da solo.": "Pour fermer NeoTracker, il suffit de fermer cette fenêtre avec la croix en haut à droite : le programme s'arrête tout seul.",
  "Per confermare scrivi:": "Pour confirmer, saisissez :",
  "Per eliminare scrivi il nome esatto dell'utente nella conferma.": "Pour supprimer, saisissez le nom exact de l'utilisateur dans la confirmation.",
  "Per le linee guida NCCN, in un melanoma invasivo con un parente di primo grado con tumore del pancreas è raccomandato un pannello multigene che includa CDKN2A.": "Selon les recommandations du NCCN, en cas de mélanome invasif avec un parent du premier degré atteint d'un cancer du pancréas, un panel multigénique incluant CDKN2A est recommandé.",
  "Per stimare la città il programma contatta il servizio gratuito ipwho.is, che vede il tuo indirizzo internet. La precisione è quella della città (a volte sbaglia). Procedo?": "Pour estimer la ville, le programme contacte le service gratuit ipwho.is, qui voit votre adresse internet. La précision est celle de la ville (il se trompe parfois). Continuer ?",
  "Per vedere quanto sole ti scotta, indica il fototipo nel": "Pour voir combien de temps de soleil vous fait brûler, indiquez votre phototype dans le",
  "Permesso negato. Puoi cercare la città per nome oppure usare la stima da indirizzo internet.": "Autorisation refusée. Vous pouvez rechercher la ville par son nom ou utiliser l'estimation à partir de l'adresse internet.",
  "Piede destro": "Pied droit",
  "Piede sinistro": "Pied gauche",
  "Pillow non installato: le anteprime useranno le foto originali (installa con «py -m pip install pillow»).": "Pillow n'est pas installé : les aperçus utiliseront les photos originales (installez-le avec « py -m pip install pillow »).",
  "Più colori nello stesso neo (marrone, nero, rosso, blu, bianco).": "Plusieurs couleurs dans le même grain de beauté (marron, noir, rouge, bleu, blanc).",
  "Più di 6 mm (ma esistono melanomi più piccoli).": "Plus de 6 mm (mais il existe des mélanomes plus petits).",
  "Più tumori dello spettro BAP1 (melanoma uveale, mesotelioma, carcinoma renale, melanoma cutaneo)": "Plusieurs tumeurs du spectre BAP1 (mélanome uvéal, mésothéliome, carcinome rénal, mélanome cutané)",
  "Poche": "Peu",
  "Polpaccio destro": "Mollet droit",
  "Polpaccio sinistro": "Mollet gauche",
  "Posizione": "Position",
  "Posizione aggiornata.": "Position mise à jour.",
  "Posizione aggiornata: {regione}.": "Position mise à jour : {regione}.",
  "Posizione fuori dalla mappa.": "Position en dehors de la carte.",
  "Posizione impostata": "Position définie",
  "Posizione non impostata": "Position non définie",
  "Posizione non impostata: scegli una città o usa 'Rileva la mia posizione'.": "Position non définie : choisissez une ville ou utilisez « Détecter ma position ».",
  "Posizione non valida.": "Position non valide.",
  "Posizione salvata: {nome}": "Position enregistrée : {nome}",
  "Posizione stimata": "Position estimée",
  "Precauzioni extra: evita il sole nelle ore centrali, cerca l'ombra, copri la pelle, SPF 30+. La pelle non protetta si scotta in fretta.": "Précautions supplémentaires : évitez le soleil aux heures centrales, cherchez l'ombre, couvrez votre peau, SPF 30+. Une peau non protégée brûle vite.",
  "Preferisco non dirlo": "Je préfère ne pas le dire",
  "Premi": "Appuyez sur",
  "Preparo la scheda…": "Préparation de la fiche…",
  "Prima": "Avant",
  "Prima di cominciare": "Avant de commencer",
  "Prima salva una chiave OpenWeather.": "Enregistrez d'abord une clé OpenWeather.",
  "Principale gene di predisposizione ad alta penetranza. Varianti germinali nel 20-40% delle famiglie con melanoma; associato anche a tumore del pancreas, melanomi multipli ed esordio precoce.": "Principal gène de prédisposition à forte pénétrance. Variants germinaux dans 20 à 40 % des familles atteintes de mélanome ; également associé au cancer du pancréas, aux mélanomes multiples et à un début précoce.",
  "Profilo": "Profil",
  "Profilo da completare": "Profil à compléter",
  "Profilo di {nome}": "Profil de {nome}",
  "Profilo non compilato.": "Profil non renseigné.",
  "Profilo non valido.": "Profil non valide.",
  "Programma di analisi (melanoma_batch.py) non trovato: le foto si salvano ma non si possono analizzare.": "Programme d'analyse (melanoma_batch.py) introuvable : les photos sont enregistrées mais ne peuvent pas être analysées.",
  "Programma di analisi:": "Programme d'analyse :",
  "Promemoria ABCDE": "Aide-mémoire ABCDE",
  "Promemoria ABCDE per riconoscere un neo": "Aide-mémoire ABCDE pour reconnaître un grain de beauté",
  "Prossime {n} ore": "{n} prochaines heures",
  "Protezione consigliata: ombra nelle ore centrali, cappello, occhiali e crema solare.": "Protection recommandée : ombre aux heures centrales, chapeau, lunettes et crème solaire.",
  "Protezione necessaria: riduci l'esposizione tra le 10 e le 16, crema solare SPF 30+, cappello e occhiali.": "Protection nécessaire : réduisez l'exposition entre 10 h et 16 h, crème solaire SPF 30+, chapeau et lunettes.",
  "Protezione non necessaria per le attività normali (attenzione a neve, acqua, quota).": "Protection inutile pour les activités normales (attention à la neige, à l'eau, à l'altitude).",
  "Prova la chiave": "Tester la clé",
  "Provo la chiave…": "Test de la clé…",
  "PubMed ha risposto con errore {code}": "PubMed a répondu par l'erreur {code}",
  "PubMed non raggiungibile (controlla la connessione internet)": "PubMed injoignable (vérifiez la connexion internet)",
  "PubMed non è raggiungibile: mostro l'ultima ricerca salvata il {data}.": "PubMed est injoignable : affichage de la dernière recherche enregistrée le {data}.",
  "PubMed {pmid} · abstract non disponibile": "PubMed {pmid} · résumé non disponible",
  "PubMed è un servizio della National Library of Medicine. Gli abstract sono mostrati per consultazione personale, in inglese; per il testo completo apri l'articolo sul sito della rivista.": "PubMed est un service de la National Library of Medicine. Les résumés sont affichés pour consultation personnelle, en anglais ; pour le texte intégral, ouvrez l'article sur le site de la revue.",
  "Puoi chiudere questa finestra. Per riaprirlo usa l'icona «NeoTracker» sul Desktop.": "Vous pouvez fermer cette fenêtre. Pour rouvrir le programme, utilisez l'icône « NeoTracker » du Bureau.",
  "Puoi continuare a usare l'app. Se chiudi la finestra l'analisi non va persa: il programma finisce il lavoro e poi si spegne da solo.": "Vous pouvez continuer à utiliser l'application. Si vous fermez la fenêtre, l'analyse n'est pas perdue : le programme termine le travail puis s'arrête tout seul.",
  "Puoi usare una tua foto, un disegno o un'icona. L'immagine viene ritagliata a quadrato e ridotta, resta solo su questo computer e non viene mai usata per l'analisi dei nei.": "Vous pouvez utiliser une photo de vous, un dessin ou une icône. L'image est recadrée en carré et réduite, reste uniquement sur cet ordinateur et n'est jamais utilisée pour l'analyse des grains de beauté.",
  "Qualche volta": "Parfois",
  "Qualcosa non ha funzionato": "Quelque chose n'a pas fonctionné",
  "Quando l'hai notato, se prude, se è cambiato…": "Quand vous l'avez remarqué, s'il démange, s'il a changé…",
  "Quanti nei hai sul corpo, circa?": "Environ combien de grains de beauté avez-vous sur le corps ?",
  "Quanto sono affidabili app e intelligenza artificiale": "Quelle est la fiabilité des applications et de l'intelligence artificielle",
  "Questa foto non è ancora stata analizzata. L'analisi confronta più metodi sulla stessa immagine e ti dice cosa ha risposto ciascuno.": "Cette photo n'a pas encore été analysée. L'analyse compare plusieurs méthodes sur la même image et vous indique ce que chacune a répondu.",
  "Questa scheda raccoglie dati inseriti dalla persona e foto da lei scattate. I risultati dell'analisi automatica sono sperimentali, non sono una diagnosi e non sostituiscono la visita dermatologica o la dermoscopia.": "Cette fiche rassemble des données saisies par la personne et des photos prises par elle. Les résultats de l'analyse automatique sont expérimentaux, ne constituent pas un diagnostic et ne remplacent pas la consultation dermatologique ni la dermoscopie.",
  "Questo browser non offre la geolocalizzazione: cerca la città per nome.": "Ce navigateur ne propose pas la géolocalisation : recherchez la ville par son nom.",
  "Questo metodo prevede l'invio dei pixel della foto (non dei metadati) a un server esterno.": "Cette méthode envoie les pixels de la photo (et non les métadonnées) à un serveur externe.",
  "Questo programma ti aiuta a tenere traccia dei tuoi nei nel tempo: li segni su una mappa del corpo, ne conservi le foto con la data e li fai analizzare da più metodi. Inizia creando il tuo utente.": "Ce programme vous aide à suivre vos grains de beauté dans le temps : vous les placez sur une carte du corps, vous conservez leurs photos avec la date et vous les faites analyser par plusieurs méthodes. Commencez par créer votre utilisateur.",
  "Questo rapporto NON è una diagnosi. I programmi usati sono prototipi di ricerca, non dispositivi medici.": "Ce rapport n'est PAS un diagnostic. Les programmes utilisés sont des prototypes de recherche, pas des dispositifs médicaux.",
  "RETRO": "DOS",
  "Rapporto completo (testo)": "Rapport complet (texte)",
  "Rapporto completo (testo, in italiano)": "Rapport complet (texte, en italien)",
  "Raro": "Rare",
  "Regione lombare destra": "Région lombaire droite",
  "Regione lombare sinistra": "Région lombaire gauche",
  "Regione scapolare destra": "Région scapulaire droite",
  "Regione scapolare sinistra": "Région scapulaire gauche",
  "Retro": "Dos",
  "Revisione": "Revue",
  "Revisione sistematica": "Revue systématique",
  "Revisioni sul melanoma familiare (CDKN2A, CDK4)": "Revues sur le mélanome familial (CDKN2A, CDK4)",
  "Rianalizza": "Réanalyser",
  "Richiesta non autorizzata.": "Requête non autorisée.",
  "Richiesta troppo grande.": "Requête trop volumineuse.",
  "Riconoscere un neo sospetto": "Reconnaître un grain de beauté suspect",
  "Riduci": "Réduire",
  "Rifà la ricerca ignorando i risultati salvati": "Refaire la recherche en ignorant les résultats enregistrés",
  "Rileva la mia posizione": "Détecter ma position",
  "Rimuovere la chiave?": "Supprimer la clé ?",
  "Rimuovi": "Supprimer",
  "Rinomina": "Renommer",
  "Rinomina utente": "Renommer l'utilisateur",
  "Ripristina": "Restaurer",
  "Riprova": "Réessayer",
  "Rischio associato": "Risque associé",
  "Rossi": "Roux",
  "Rotella = zoom · trascina = sposta · doppio clic = ingrandisci": "Molette = zoom · glisser = déplacer · double clic = agrandir",
  "Ruolo e letteratura": "Rôle et littérature",
  "S": "G",
  "Salva": "Enregistrer",
  "Salva foto": "Enregistrer la photo",
  "Salva neo": "Enregistrer le grain de beauté",
  "Salvataggio…": "Enregistrement…",
  "Salvato ✓": "Enregistré ✓",
  "Scansiona la letteratura": "Parcourir la littérature",
  "Scansiona la letteratura sui geni": "Parcourir la littérature sur les gènes",
  "Scansione completata.": "Recherche terminée.",
  "Scarico l'indice UV…": "Téléchargement de l'indice UV…",
  "Scatta sempre dalla stessa angolazione e salva l'originale, senza filtri.": "Prenez toujours la photo sous le même angle et conservez l'original, sans filtre.",
  "Scegli dove ti trovi per vedere l'indice UV di oggi.": "Choisissez où vous vous trouvez pour voir l'indice UV du jour.",
  "Scegli il tuo profilo: ogni persona ha la propria mappa dei nei, le proprie foto e i propri dati.": "Choisissez votre profil : chaque personne a sa propre carte des grains de beauté, ses photos et ses données.",
  "Scegli immagine…": "Choisir une image…",
  "Scegli la città qui sopra: poi vedrai l'indice UV di oggi, ora per ora.": "Choisissez la ville ci-dessus : vous verrez ensuite l'indice UV du jour, heure par heure.",
  "Scegli un file immagine (JPG, PNG, WEBP o BMP).": "Choisissez un fichier image (JPG, PNG, WEBP ou BMP).",
  "Scegli un utente e indica il suo fototipo per vedere quanti minuti servono per scottarsi.": "Choisissez un utilisateur et indiquez son phototype pour voir en combien de minutes on brûle.",
  "Scegli un'immagine personale": "Choisir une image personnelle",
  "Scegli utente": "Choisir l'utilisateur",
  "Scelti per te (in base a profilo e sede dei nei)": "Choisis pour vous (selon le profil et l'emplacement des grains de beauté)",
  "Scheda dei nei – {nome}": "Fiche des grains de beauté – {nome}",
  "Scheda per il dermatologo": "Fiche pour le dermatologue",
  "Schiena (zona media) destra": "Dos (zone médiane) droit",
  "Schiena (zona media) sinistra": "Dos (zone médiane) gauche",
  "Scottature": "Coups de soleil",
  "Scottature con vesciche (soprattutto da bambino o ragazzo)": "Coups de soleil avec cloques (surtout dans l'enfance ou l'adolescence)",
  "Scrivi almeno 3 caratteri.": "Saisissez au moins 3 caractères.",
  "Scrivi un nome.": "Saisissez un nom.",
  "Scuri": "Foncés",
  "Se hai dubbi sul fototipo, pensa a come reagisce la tua pelle alla prima esposizione intensa al sole in estate, senza protezione.": "Si vous hésitez sur votre phototype, pensez à la réaction de votre peau à la première exposition intense au soleil en été, sans protection.",
  "Se i metodi sono in disaccordo è normale: significa solo che nessuno di loro è affidabile da solo.": "Il est normal que les méthodes ne soient pas d'accord : cela signifie seulement qu'aucune n'est fiable à elle seule.",
  "Se inserisci dati o foto di altre persone, assicurati di avere il loro consenso.": "Si vous saisissez des données ou des photos d'autres personnes, assurez-vous d'avoir leur consentement.",
  "Se sta ancora analizzando una foto, finisce prima l'analisi e poi si spegne. Il pulsante qui sotto fa la stessa cosa.": "S'il est encore en train d'analyser une photo, il termine d'abord l'analyse puis s'arrête. Le bouton ci-dessous fait la même chose.",
  "Sede": "Zone",
  "Sede (modificabile)": "Zone (modifiable)",
  "Senza Pillow l'immagine deve essere un JPG/PNG sotto i 400 KB (la pagina la riduce da sola: riprova con la funzione 'Scegli immagine').": "Sans Pillow, l'image doit être un JPG/PNG de moins de 400 Ko (la page la réduit toute seule : réessayez avec la fonction « Choisir une image »).",
  "Servono ombra, abiti, cappello e crema solare nelle ore centrali.": "Ombre, vêtements, chapeau et crème solaire sont nécessaires aux heures centrales.",
  "Sesso": "Sexe",
  "Sezione sconosciuta.": "Section inconnue.",
  "Sezione {n} di {tot}…": "Section {n} sur {tot}…",
  "Sezioni": "Sections",
  "Sindrome di predisposizione ai tumori BAP1: melanoma uveale, mesotelioma, carcinoma renale, melanoma cutaneo e nevi melanocitari atipici.": "Syndrome de prédisposition aux tumeurs BAP1 : mélanome uvéal, mésothéliome, carcinome rénal, mélanome cutané et naevus mélanocytaires atypiques.",
  "Sindromico": "Syndromique",
  "SkinSense (servizio online)": "SkinSense (service en ligne)",
  "SkinSense abilitato.": "SkinSense activé.",
  "SkinSense disattivato.": "SkinSense désactivé.",
  "SkinSense è attivo: la foto (senza metadati) verrà inviata a un servizio online.": "SkinSense est activé : la photo (sans métadonnées) sera envoyée à un service en ligne.",
  "SkinSense è un servizio online di terzi: le foto dei tuoi nei verrebbero inviate via internet a un server che non controlliamo. Le foto sono dati sulla tua salute. Vuoi abilitarlo?": "SkinSense est un service en ligne tiers : les photos de vos grains de beauté seraient envoyées par internet à un serveur que nous ne contrôlons pas. Les photos sont des données de santé. Voulez-vous l'activer ?",
  "Soddisfatto": "Satisfait",
  "Soglie e colori della scala internazionale dell'OMS. Fonti:": "Seuils et couleurs de l'échelle internationale de l'OMS. Sources :",
  "Sono immunosoppresso/a (trapianto o terapie che abbassano le difese)": "Je suis immunodéprimé(e) (greffe ou traitements qui affaiblissent les défenses)",
  "Sono misure inserite da te: valgono se prese sempre allo stesso modo. Un neo che cresce o cambia è un buon motivo per farlo vedere al dermatologo; la linea a 6 mm è solo il riferimento classico dei criteri ABCDE.": "Ce sont des mesures saisies par vous : elles sont valables si elles sont toujours prises de la même manière. Un grain de beauté qui grossit ou change est une bonne raison de le montrer au dermatologue ; la ligne à 6 mm n'est que la référence classique des critères ABCDE.",
  "Sono mostrate {n} foto su {tot}.": "{n} photos affichées sur {tot}.",
  "Sono presenti alcuni fattori di rischio: protezione solare accurata e autoesame regolare; un controllo dermatologico di base è una buona abitudine.": "Certains facteurs de risque sont présents : protection solaire rigoureuse et autoexamen régulier ; un contrôle dermatologique de base est une bonne habitude.",
  "Sono presenti fattori di rischio rilevanti: è consigliato un controllo dermatologico periodico (la frequenza la decide il dermatologo) e l'autoesame regolare della pelle.": "Des facteurs de risque importants sont présents : un contrôle dermatologique périodique (la fréquence est fixée par le dermatologue) et un autoexamen régulier de la peau sont conseillés.",
  "Soprattutto in infanzia e adolescenza.": "Surtout dans l'enfance et l'adolescence.",
  "Sovrapponi con cursore": "Superposer avec curseur",
  "Spalla destra": "Épaule droite",
  "Spalla sinistra": "Épaule gauche",
  "Spento per impostazione predefinita: con gli altri metodi la foto non lascia mai questo computer.": "Désactivé par défaut : avec les autres méthodes, la photo ne quitte jamais cet ordinateur.",
  "Spesso": "Souvent",
  "Stampa la scheda di questo neo": "Imprimer la fiche de ce grain de beauté",
  "Stampa una scheda con tutti i nei": "Imprimer une fiche avec tous les grains de beauté",
  "Stampata il {data} con NeoTracker": "Imprimé le {data} avec NeoTracker",
  "Stato dell'installazione": "État de l'installation",
  "Stessa luce (luce del giorno, senza flash) e stessa distanza ogni volta, circa 10-15 cm.": "Même lumière (lumière du jour, sans flash) et même distance à chaque fois, environ 10 à 15 cm.",
  "Stima dall'indirizzo internet": "Estimation à partir de l'adresse internet",
  "Storia familiare": "Antécédents familiaux",
  "Storia personale": "Antécédents personnels",
  "Storico fotografico": "Historique photographique",
  "Storico fotografico ({n})": "Historique photographique ({n})",
  "Studi più pertinenti": "Études les plus pertinentes",
  "Studi più recenti sui geni di predisposizione": "Études les plus récentes sur les gènes de prédisposition",
  "Studio clinico": "Essai clinique",
  "Studio osservazionale": "Étude observationnelle",
  "Studio randomizzato": "Essai randomisé",
  "Sì": "Oui",
  "Sì, abilita": "Oui, activer",
  "Sì, negativo": "Oui, négatif",
  "Sì, non informativo": "Oui, non informatif",
  "Sì, positivo": "Oui, positif",
  "Sì, stima la città": "Oui, estimer la ville",
  "Telomerasi: varianti del promotore descritte in famiglie con melanoma.": "Télomérase : variants du promoteur décrits dans des familles atteintes de mélanome.",
  "Test genetico": "Test génétique",
  "Test genetico già eseguito": "Test génétique déjà effectué",
  "Tipo": "Type",
  "Tipo di foto": "Type de photo",
  "Tipo {n}": "Type {n}",
  "Torace destro": "Thorax droit",
  "Torace sinistro": "Thorax gauche",
  "Tra le due foto sono passati {n} giorni.": "{n} jours se sont écoulés entre les deux photos.",
  "Tra le due foto è passato {n} giorno.": "{n} jour s'est écoulé entre les deux photos.",
  "Trascina il pallino sulla mappa per correggere la posizione; ingrandisci con la rotella per la massima precisione.": "Faites glisser le point sur la carte pour corriger la position ; zoomez avec la molette pour une précision maximale.",
  "Trascina il pallino sulla mappa per spostarlo.": "Faites glisser le point sur la carte pour le déplacer.",
  "Trascina qui una foto oppure clicca per sceglierla": "Faites glisser une photo ici ou cliquez pour en choisir une",
  "Troppi collegamenti aperti.": "Trop de connexions ouvertes.",
  "Tumore del pancreas": "Cancer du pancréas",
  "Tumori dello spettro BAP1 indicati: {bap1_spettro}. Criterio semplificato: il genetista usa criteri più completi.": "Tumeurs du spectre BAP1 indiquées : {bap1_spettro}. Critère simplifié : le généticien utilise des critères plus complets.",
  "Tutti i dati restano su questo computer, nella cartella:": "Toutes les données restent sur cet ordinateur, dans le dossier :",
  "UV moderati: serve protezione nelle ore centrali": "UV modérés : une protection est nécessaire aux heures centrales",
  "Ultima analisi automatica ({data}): {esito}. Strumento di ricerca, non diagnostico.": "Dernière analyse automatique ({data}) : {esito}. Outil de recherche, non diagnostique.",
  "Un medico ti ha detto che hai nei atipici (displastici)?": "Un médecin vous a-t-il dit que vous avez des grains de beauté atypiques (dysplasiques) ?",
  "Un neo che cambia (forma, bordi, colore, dimensioni), sanguina, prude o ti preoccupa va mostrato a un dermatologo, qualunque cosa dica l'app. Il controllo periodico dal dermatologo resta insostituibile.": "Un grain de beauté qui change (forme, bords, couleur, taille), saigne, démange ou vous inquiète doit être montré à un dermatologue, quoi que dise l'application. Le contrôle périodique chez le dermatologue reste irremplaçable.",
  "Un risultato positivo indica un rischio più alto, non la certezza di ammalarsi; un risultato negativo non azzera il rischio (molte famiglie non hanno una variante identificabile).": "Un résultat positif indique un risque plus élevé, pas la certitude de tomber malade ; un résultat négatif n'annule pas le risque (beaucoup de familles n'ont pas de variant identifiable).",
  "Una stima va bene.": "Une estimation suffit.",
  "Uomo": "Homme",
  "Usa anche SkinSense (servizio online)": "Utiliser aussi SkinSense (service en ligne)",
  "Usa la data scritta nella foto, se c'è": "Utiliser la date inscrite dans la photo, si elle existe",
  "Uso di lampade o lettini abbronzanti": "Usage de lampes ou de cabines de bronzage",
  "Utente creato. Compila il profilo: serve a contestualizzare i risultati.": "Utilisateur créé. Renseignez le profil : il sert à contextualiser les résultats.",
  "Utente eliminato.": "Utilisateur supprimé.",
  "Utente non trovato.": "Utilisateur introuvable.",
  "Vai alla sezione Genetica": "Aller à la section Génétique",
  "Varianti comuni legate a capelli rossi e pelle chiara: aumentano il rischio di melanoma in modo moderato. Non è un test di routine: l'interpretazione è specialistica.": "Variants courants liés aux cheveux roux et à la peau claire : ils augmentent modérément le risque de mélanome. Ce n'est pas un test de routine : l'interprétation relève d'un spécialiste.",
  "Varianti rare concentrate nel codone 24: il quadro familiare è indistinguibile da quello di CDKN2A.": "Variants rares concentrés dans le codon 24 : le tableau familial est indiscernable de celui de CDKN2A.",
  "Variazione:": "Variation :",
  "Verdi": "Verts",
  "Verranno cancellate per sempre la sua unica foto e i rapporti di analisi.": "Sa seule photo et les rapports d'analyse seront supprimés définitivement.",
  "Verranno cancellate per sempre tutte le sue {n} foto e i rapporti di analisi.": "Ses {n} photos et les rapports d'analyse seront supprimés définitivement.",
  "Verranno cancellati per sempre il profilo, tutti i nei, tutte le foto e tutti i rapporti di questo utente. L'operazione non si può annullare.": "Le profil, tous les grains de beauté, toutes les photos et tous les rapports de cet utilisateur seront supprimés définitivement. Cette opération est irréversible.",
  "Versione": "Version",
  "Versione dell'avviso non valida.": "Version de l'avertissement non valide.",
  "Viso": "Visage",
  "a cielo sereno e senza protezione, al picco di oggi la pelle può arrossarsi in": "par ciel dégagé et sans protection, au pic d'aujourd'hui la peau peut rougir en",
  "aggiornato": "mis à jour",
  "altro": "autre",
  "assumo che le 2 uscite siano [benigno, maligno]; ordine non verificabile": "je suppose que les 2 sorties sont [bénin, malin] ; ordre non vérifiable",
  "attivo solo se lo abiliti qui sotto": "actif seulement si vous l'activez ci-dessous",
  "capelli biondi": "cheveux blonds",
  "capelli castani": "cheveux châtains",
  "capelli grigi o bianchi": "cheveux gris ou blancs",
  "capelli neri": "cheveux noirs",
  "capelli rossi": "cheveux roux",
  "carcinoma basocellulare, tumore della pelle": "carcinome basocellulaire, cancer de la peau",
  "carcinoma squamocellulare, tumore della pelle": "carcinome épidermoïde, cancer de la peau",
  "cheratosi attinica, lesione pre-cancerosa": "kératose actinique, lésion précancéreuse",
  "cheratosi seborroica, benigna": "kératose séborrhéique, bénigne",
  "circa {minuti} minuti": "environ {minuti} minutes",
  "connessione non riuscita: {motivo}": "connexion impossible : {motivo}",
  "cuoio capelluto": "cuir chevelu",
  "dermoscopica": "dermoscopique",
  "donna": "femme",
  "dorso del piede": "dessus du pied",
  "dorso della mano": "dos de la main",
  "e clicca sul punto esatto del corpo (ingrandisci con la rotella per essere più preciso).": "et cliquez sur l'endroit exact du corps (zoomez avec la molette pour être plus précis).",
  "e conferma l'email.": "et confirmez l'e-mail.",
  "es. 4,5": "p. ex. 4,5",
  "facoltativa: richiede una tua chiave personale": "facultative : nécessite une clé personnelle",
  "foto normale": "photo normale",
  "fototipo {tipo}": "phototype {tipo}",
  "fronte": "face",
  "gratuita, senza account né chiave": "gratuite, sans compte ni clé",
  "i metodi non concordano tra loro": "les méthodes ne sont pas d'accord entre elles",
  "i modelli di App 1 non sono stati scaricati: sono ancora dei segnaposto Git LFS. Apri PowerShell nella cartella {cartella} e lancia 'git lfs pull', poi riprova.": "les modèles de l'App 1 n'ont pas été téléchargés : ce sont encore des fichiers de substitution Git LFS. Ouvrez PowerShell dans le dossier {cartella}, lancez « git lfs pull », puis réessayez.",
  "ieri": "hier",
  "il modello ha {n} uscite: significato sconosciuto": "le modèle a {n} sorties : signification inconnue",
  "impossibile avviare: {e}": "impossible de démarrer : {e}",
  "in {n} giorni.": "en {n} jours.",
  "in {n} giorno.": "en {n} jour.",
  "indirizzo del servizio non ammesso (serve https)": "adresse du service non autorisée (https requis)",
  "indirizzo non ammesso (solo https)": "adresse non autorisée (https uniquement)",
  "interrotto dopo {minuti} minuti (tempo massimo)": "interrompu après {minuti} minutes (durée maximale)",
  "la foto non si apre come immagine ({tipo}): {dettaglio}": "la photo ne s'ouvre pas comme une image ({tipo}) : {dettaglio}",
  "labbro": "lèvre",
  "le prime 1.000 chiamate al giorno sono gratuite, le successive si pagano. OpenWeather può chiedere una carta di pagamento per attivarlo: controlla le condizioni sul loro sito.": "les 1 000 premiers appels par jour sont gratuits, les suivants sont payants. OpenWeather peut demander une carte de paiement pour l'activer : vérifiez les conditions sur leur site.",
  "mai": "jamais",
  "mancano i pesi addestrati: nella cartella {cartella} non ci sono i file model_fold_0.bin ... model_fold_4.bin. Il repository non li contiene: vanno prodotti con train.py sul dataset SIIM-ISIC.": "les poids entraînés sont absents : dans le dossier {cartella}, il n'y a pas les fichiers model_fold_0.bin ... model_fold_4.bin. Le dépôt ne les contient pas : ils doivent être produits avec train.py sur le jeu de données SIIM-ISIC.",
  "media di {n} modelli; punteggio medio {media} (soglia 0)": "moyenne de {n} modèles ; score moyen {media} (seuil 0)",
  "melanoma": "mélanome",
  "meno di 25": "moins de 25",
  "molte": "beaucoup",
  "molte efelidi": "beaucoup d'éphélides",
  "nel pannello": "dans le panel",
  "nessun caso indicato": "aucun cas indiqué",
  "nessun metodo ha segnalato il neo (questo non esclude un melanoma)": "aucune méthode n'a signalé le grain de beauté (cela n'exclut pas un mélanome)",
  "nessun risultato disponibile": "aucun résultat disponible",
  "nessuna efelide": "aucune éphélide",
  "nevo, cioe' neo benigno": "naevus, c'est-à-dire grain de beauté bénin",
  "no": "non",
  "nome@esempio.it (facoltativa)": "nom@exemple.fr (facultatif)",
  "non riesco a preparare la foto in modo sicuro: {e}": "impossible de préparer la photo en toute sécurité : {e}",
  "non so": "ne sait pas",
  "occhi azzurri o grigi": "yeux bleus ou gris",
  "occhi scuri": "yeux foncés",
  "occhi verdi": "yeux verts",
  "oggi": "aujourd'hui",
  "oltre 2 ore (UV molto basso)": "plus de 2 heures (UV très faible)",
  "orecchio": "oreille",
  "pagina del servizio": "page du service",
  "palmo della mano": "paume de la main",
  "palpebra": "paupière",
  "pianta del piede": "plante du pied",
  "poche": "peu",
  "poche efelidi": "peu d'éphélides",
  "posizione da indirizzo internet non disponibile": "position à partir de l'adresse internet indisponible",
  "prob. melanoma {perc}": "prob. de mélanome {perc}",
  "probabilita' di malignita' stimata dal modello: {pm}": "probabilité de malignité estimée par le modèle : {pm}",
  "qualche volta": "parfois",
  "retro": "dos",
  "rilevante": "important",
  "risposta illeggibile: {e}": "réponse illisible : {e}",
  "risposta non valida dal servizio": "réponse non valide du service",
  "risposta senza nome della lesione: {risposta}": "réponse sans nom de lésion : {risposta}",
  "risposta troppo grande": "réponse trop volumineuse",
  "servizio non raggiungibile: {ultimo_errore}": "service injoignable : {ultimo_errore}",
  "sicurezza {perc}": "confiance {perc}",
  "sotto l'unghia (mano)": "sous l'ongle (main)",
  "sotto l'unghia (piede)": "sous l'ongle (pied)",
  "spazio tra le dita": "entre les doigts ou les orteils",
  "spesso": "souvent",
  "studi su PubMed": "études sur PubMed",
  "sì": "oui",
  "sì, negativo": "oui, négatif",
  "sì, non informativo": "oui, non informatif",
  "sì, positivo": "oui, positif",
  "tempo scaduto o rete non disponibile": "délai dépassé ou réseau indisponible",
  "tutti i metodi con risultato indicano un neo da attenzionare": "toutes les méthodes ayant un résultat signalent un grain de beauté à surveiller",
  "ukalwa / melanoma-detection (app Android)": "ukalwa / melanoma-detection (application Android)",
  "uomo": "homme",
  "uscita letta come le 6 classi di pelle (non verificabile)": "sortie interprétée comme les 6 classes de peau (non vérifiable)",
  "vatsal30 / Melanoma-Detection (PyTorch)": "vatsal30 / Melanoma-Detection (PyTorch)",
  "{avviso} Il servizio Open-Meteo non risponde ({e}).": "{avviso} Le service Open-Meteo ne répond pas ({e}).",
  "{cosa} non può essere vuoto.": "{cosa} ne peut pas être vide.",
  "{cosa} è troppo lungo (massimo {massimo} caratteri).": "{cosa} est trop long (maximum {massimo} caractères).",
  "{file_modello} e' ancora un segnaposto Git LFS: lancia 'git lfs pull' nella cartella {cartella}.": "{file_modello} est encore un fichier de substitution Git LFS : lancez « git lfs pull » dans le dossier {cartella}.",
  "{file_pesi} e' ancora un segnaposto Git LFS: apri PowerShell nella cartella {cartella} e lancia 'git lfs pull'.": "{file_pesi} est encore un fichier de substitution Git LFS : ouvrez PowerShell dans le dossier {cartella} et lancez « git lfs pull ».",
  "{foto} · ultima {quando}": "{foto} · dernière {quando}",
  "{giorno} ore {ora}: indice UV {uvi} ({categoria})": "{giorno} à {ora} : indice UV {uvi} ({categoria})",
  "{nome} · {mb} MB · clicca per cambiare": "{nome} · {mb} Mo · cliquez pour changer",
  "{nome}: errore.": "{nome} : erreur.",
  "{nome}: il valore deve essere tra {minimo} e {massimo}.": "{nome} : la valeur doit être comprise entre {minimo} et {massimo}.",
  "{nome}: inserisci un numero.": "{nome} : saisissez un nombre.",
  "{nome}: non disponibile.": "{nome} : non disponible.",
  "{n} altro/i parente/i con melanoma": "{n} autre(s) parent(s) atteint(s) de mélanome",
  "{n} anni": "{n} ans",
  "{n} anni fa": "il y a {n} ans",
  "{n} anno": "{n} an",
  "{n} anno fa": "il y a {n} an",
  "{n} articoli su melanoma e «{termine}»": "{n} articles sur le mélanome et « {termine} »",
  "{n} articoli trovati su PubMed · ricerca del {data}": "{n} articles trouvés sur PubMed · recherche du {data}",
  "{n} articoli trovati su PubMed · ricerca del {data} (salvata)": "{n} articles trouvés sur PubMed · recherche du {data} (enregistrée)",
  "{n} con astrocitoma": "{n} atteint(s) d'astrocytome",
  "{n} con melanoma uveale": "{n} atteint(s) de mélanome uvéal",
  "{n} con tumore del pancreas": "{n} atteint(s) d'un cancer du pancréas",
  "{n} file modello su 10": "{n} fichiers de modèle sur 10",
  "{n} file modello su 5": "{n} fichiers de modèle sur 5",
  "{n} foto": "{n} photo",
  "{n} foto in {giorni} (dal {da} al {a}).": "{n} photos en {giorni} (du {da} au {a}).",
  "{n} foto#pl": "{n} photos",
  "{n} giorni": "{n} jours",
  "{n} giorni fa": "il y a {n} jours",
  "{n} giorno": "{n} jour",
  "{n} mesi fa": "il y a {n} mois",
  "{n} metodi su {tot} hanno risposto": "{n} méthodes sur {tot} ont répondu",
  "{n} nei": "{n} grains de beauté",
  "{n} nei in questa scheda": "{n} grains de beauté sur cette fiche",
  "{n} neo": "{n} grain de beauté",
  "{n} neo in questa scheda": "{n} grain de beauté sur cette fiche",
  "{n} parente/i di primo grado con melanoma": "{n} parent(s) du premier degré atteint(s) de mélanome",
  "{n} su {tot}: {et}": "{n} sur {tot} : {et}",
  "{vista} · posizione {x}% da sinistra, {y}% dall'alto": "{vista} · position {x} % depuis la gauche, {y} % depuis le haut",
  "È una stima prudente che usa la dose minima di eritema più bassa del tuo fototipo; con riflessi (acqua, neve, sabbia), quota o pelle già arrossata il tempo si accorcia.": "Il s'agit d'une estimation prudente qui utilise la dose érythémale minimale la plus basse de votre phototype ; avec des réflexions (eau, neige, sable), l'altitude ou une peau déjà rougie, le temps est plus court.",
  "È uno strumento personale per organizzare le foto dei tuoi nei e confrontare nel tempo i risultati di alcuni modelli di ricerca. Non è certificato né approvato da alcuna autorità sanitaria.": "C'est un outil personnel pour organiser les photos de vos grains de beauté et comparer dans le temps les résultats de certains modèles de recherche. Il n'est ni certifié ni approuvé par aucune autorité sanitaire.",
  "…di cui di 1° grado": "…dont du 1er degré",
  "← Tutti i nei": "← Tous les grains de beauté"
};
'''
WEB_FILES["/i18n_fr.js"] = ("text/javascript; charset=utf-8", _WEB_I18N_FR_JS.encode("utf-8"))

_WEB_ICONA_PNG_B64 = """
iVBORw0KGgoAAAANSUhEUgAAAQAAAAEACAYAAABccqhmAADyO0lEQVR42uz9eZxl2VUeCn5r7zPcOeaInLOysipr0FCSSjOIVElg
S8wYl5AEGIPNZBtjv+7XPD/br161u9u/tt39bGw/hP0aLAwGVICZzCBAqJBASEJTScqasnIeY57udM7Ze/Ufe59z9hluRFRRBZhX
oV8osyIjbtx77llrr/Wtb30f8PLHyx8vf7z88fLHyx8vf7z88fLHyx8vf7z88fLHyx8vf7z88fLHyx8vf7z88fLHyx8vf/zl/KCX
X/NBPvi/o5fB/yd+a1+UD345GP4yvK5HHqGHz52j5eX7CQAWF8/xY/ffz3j0Uf3yPf7yx+TwZ8J73iPOVu8b/suYHP6yJAB65JFH
6KMfhVhcPMePPfaYmvSNjzzyiDgHeFfPbXdevtsP8rENoLfPv7sfvQlfP9hP/3l9RIda/dfeelvy2GPvmXjv4OGH5dnl++nxxXOM
xx7TfxkSwn/HCYDp4YffIwCgHPAPft+P+9O7Tx5XpE8JFveC9R1EdFLrZJGknGVGCOj5fQs+2ucSkf3k8uXkPa8yu18oVeyc/j+n
j00AAex+Lf1G5sJzYKbi72Tes7blPToH5uIXuPAyOP+dzqNoUOH5cfp9AKDZeWwAlD4u1z4hdv6bJ74Grr3G7nXIHt9eDy78KAHE
gGaCoDUiMdJab4JohcCXGbhExE+D/QuDRXH5/L/9t+NiPnhYmvvvQ9o80MsJ4CV/vg8//HAl6N/1Q/8mjNefezVrvJWJ30yg14D5
DvL8hpA+IISJFxCYa2KeaiIjDX5y/rvcXlPpe2vyAFeSQSHSi/9a+Tkq/J4sCRQSRpoYCO4/5491gCTApcdLnwOXAqsmOpmKyUG7
8eb8NnZ+UfU5cPXvXHzqxe8pf51KF5ELz736PMy/uY9PzAARiMylFGCQ1oBWQBJHYFwF4QkQ/bEi+iPVbH/h6Z/4lztudfCwuS//
u6oM6L+X0/7s2f9VPv74o0n6lb/yt/7hrBqrh7TirwfwlUTiLhmE0CSh2dyIJreTNkFHRETZ8UAA1b96KgY0lZPC5IN+r6vJNWFR
fpi9vl74GjunKShLDuTc2IWwSO90ovzn3ULCPbg5DSmySTN/5ro2IKkauIXTuBR8VM1LhUqB2f4Mlb5Hl/67pkpzgxv1z5WZ659D
+kQF2b/Z/9ZaCEBIAUgCJDOQRIBSVyDo4wB+M5Hh7z31M//6ZvpYZ88+4j3+0f9Vgf7iVwX0F7/Mf0ykfdkjjzwiPvbczjuh4/eB
8S7ygsOQHhQTNAhMlACCACYT4GRvedrzlVPh/2jyVaGDXD6ekP7pQN/F+32tUKLTxMdj3g/r4prWo+6ULEYdY48grm0t7L+QczJX
fg9niYndaoHLp3fd76C8mi9Vb/WtQ/6IB6swspdtcyOz0FpKAvmCIFhBJ9G6IP5dQf5/2Yi9D1977H8bpi3CX3Tg+S9qAqCzZx/J
TvyvfPiHFnyJ9wpBfxNCvg4yQMKAYtKQUpOJelGstGniK67/t+cT+Ae8dDQhGCeckO5zYK7iCFz6QiWIa6Ke93giE4O2khC4tmze
K1m4J3TppJ3wO3SGjTDr/BnmGaH+eaRVjb12NAFr4QO87v0SAjuVlGZoUzwxJCsZCILUCRBHz5CUP8m68TNf/vn/79UsEfwFxQn+
wiUAc7FMf/+Ov/WPljAc/gCz+gHpNw4pCCQamoXURCSppoh//oFfDf782+hPHeAHHTLzhC8WyuMygFh3+mcnLiplNErtQw6K0QES
AlcTT6WsLyUYKlUObiCRAyWwaWAYOvti+nfm4nXgut6I0t9FzltA+fWiCcFd+Hrpde1REZRfk33WmliRTyxCYiAebxLTTyYIfvTp
n/83l5x7+y8URvAXJgE88sgj4lE7a/3K9//gTIDw72tOflAGzaVEExSksm28qAvkScGdfb320Cdzo9CLeNWoejNVfoaLJexE0HAC
Ir93gO5d0pczFk9E//dC37FXL529psngm/N1nU8+OI922/NzqW0gaK2z97SAA5CD3VhQlCjt+an6HDLMgoon/F7XgWqSX5bs0ioF
mpm1D+01BAHxaEsQfiJh8a+e/rl/fyMFDLHHqPr/bAmAHn74YZGe+g+9/4e/l1n/Y+mHJxMtoIRMCEICTHWn+AsJfHOfiBf26g8Q
/PWne32ZwHv16FR/OuVTgboUQLUpgaulRe3JX19q02S0vqYC2r/c5vxkd5IeMwOsMwzAVNn5qc/MaCHBgKUzRnTLNiomgsLkhmom
A7R3cnL/niWRCdVP6XowEYNZe6xkUwKIxivM+P8MG4N/c/mDHxzZJPDnXg3Qn/OxL1KA5Ox7/8HrhVD/Usjg7QkLKJIJkZRZcSeq
T3ffSoAmfZ0OGL/0vIJ//1aA84AiTAbtJrUWNdBh9QQ/WFVQxkYrN35pylA+6eqDoSZIMAG4S9F+YrBGVutnXwcXEoPJDRpvOrWI
z1xeQQwD+uSPKcD21HcTZz6qLbYCvB/ekV0HOhAmUkgoLjfCAIcqYO01SANJ9HkF7//yzM/9u4/8RagG5J/XLz579hHv8gcfVQ8/
/CG59MChR0jgJyEbp8csFQsPRCTTVo7S4ewewU/pm18KouLXax7HqSAnBj9NaiGKP5z+LrLz5LofIBITElf1OZTv5axlKdMKJuQ2
qnmtTryUn1n+d0E1X90rAZLzM8XfW3jcuuuaAwGF/4dz6qcViwTjm77ydXji4jWMY51SH/I2jsxEofi6nYuYXSznOlZuCdqfBFZz
rxQer/SPBBKKBI+ZFEnviM/quxZe+fp5+Zqzf9D/uf9jfPbsWe/y5ct/LpMC8ecD9H1IPv74o8lXve/v373qf/z3hB8+klAQRPCU
EFJmiH4W/HsEerncp/xNqJz61W/be7xHOMBkYPI3UHZjVH6j82/7FA0irX5qwEzKe91JSaGQ/EDFhEGlO4HyG5+cX1p4PJQCnfaZ
nuyVVHN6ls0DusBHSKsCYoZmjYYv8Op77kQr8KHt91JWK5jvy5JGmjhowlE/4b3NRvfpj6aPVfd4k+4Vqr4XJndLb8hS98lj9sO/
N6uGf3Tm23/wDY8//ngCwyqkv+QJgAmPPCIee+w96uz7f/hhAf4EZHh2pGXCImCRViRUj9rveeo7N2g5aYCoJgTr24T0hCZRPtFL
n3uGd00qqAnU/HfWJY7JJ7s5pUUxodDkpJUF8z7UZiKqb3tqOyGqVAiFfFupCCj7nhytcNmL7LRJGThgpxYMpRS6zRCnjx9FtxlA
K1XCNDivHriu8dgvqXOV+lj32pgrNc3+CTBPvkQQifBpm0USe8GrpcbHzrzvB/+ObQMYjzwi/nImgEceEQAxHn1Uv/19P/TPpKAP
aRHORfAUkfQIIAiqPWkmBX9duV8JfNqD8CfgBLXIy8UXCg5SXsoToQRKTU5a+YlLByv3ifa9JlQiNhUCsra9qb7wYhAX/mFvnIQm
fMHdTygBHOSg7zkHUWePkSQJFqc7OLSwgPmpLhKl7M9wMYC5nleZJx2uXoc0qKlIrCr+r55q6F4KOkiFSKbKICKvz1IPRBBKz//3
97zvB//Dg9/3fT4efVTbauAvTwJ4xIJ9b374Hzbf/v6/97PSD/5JBF8p4TOBJKj4TOrK/r2Cv1Lup4E24ZRLT/dKzTbhXs6mTKUK
YO+EQTbBTIAPhNt8UhEHQJnCw85/F4nC5PS+5b6mig9MSAKVsn7S9ISc5FODH1C5yXEqj9pA4QMkWwYRoLXCkflZSBJYnJ3KyUKc
l/5lhJM5R+lo0vvEOZmAs1Gkg02QU2FwOa/whGUOOLXhHmcGQUTC520tEvLD7+3ver9x57f8wCIee0z9WSUB8WdB7HnUBP9s00t+
TXiN9460TEC+JFubTwSu9moDnF6/AshMKrUFTTyd3Pu+gg/QhEwuUAP81fTFVAL5KO99zbc6/WVtEqDCeI9K2wNUoAk5CYLY9rRc
3ZyjyTcp1bUWqHAt6099otpyuzYdM5W4yOYkFoIgJUEKARIEBmE0inF8ySxwHp6bwXgcmR0GQZBSQEoB4Sb2fTe+iqMQzpIIZ9cO
9WtGkwesVF8G0R49IoFJS8/b0pRoL/jqoIGPnPy277/jzyoJyD8LVt+bH/7+ow1Jv0t+8OYxy0SQ59VVk3Un+16z/XqAsL7/rmv+
i+X6XnPBvXcJ3HyaYwfVQC7nhnTalsYBl04TLkdYtvSz9zyyXOIftHqf/JBiAsBFpeKJ9r3h80iqonMajHGSYDAcoT8cYjgcQsUx
QkE4MtPG3/jGr8GJQ0tQrPC5Lz2F8XiM3cEAu8MRBuMxokRDgyCEyADKbHxcW/1QYfZPhQlEudynmsPA3dikA7VExYmU+/4IMWYk
nhSHAtZ/feaBt/z2+s/95DIeflji3Dn+744HYJl9+h0Pf/9R7fm/DS98RcSeDX6um8gVArw2+Ce2BfVjt7rAPwjzj2iPmnHf+T1P
qDKLjDaUR17u97oUVy7vydfM9rlEvS2tylItk88hFE1AynkSQ5DrWYqTOfZ5xaLTH2YG67Tk1tAqRigYh2d6uOPwIk4eXsSJw4s4
ujiPpfkZzE1PodVqQWuGEITBYIDVjW3cXlvHjeVVXL29govXb+PyrVVcW91AXwHk+cWqDCVSUMYx0MWrm+0elIhcRBm1OEvgwuFK
lFayi5yJvYlSzu9SLcTST+LrSnh/5fzP/NtzLyVXQLxUgN+jjz6qz37XD08r4f02ZcEv8+CfFKzPN/jrTn2qnvo0ISG435+3CeLA
pz5loI5TmnMZk2JLZCyoeeQ4ulOllw8Ycv+xst7CBT4hAcXHsj1wPmF3IS1XdISrrKO9TnCxBxFhT5CU8tebL+JnCz0CQOh7aIUB
mmGAZhDA8yQy8hSXMxPD9yQaQYBmGKIVhggDCSkmaCOWyj0uZNfiyV+/m8GWu8yVyVMdcFSt1GjvKYN5erIPT8UyOCq1+vCJ9//g
nS9lO0AvmTzXJQQUrf438pvvGGsvESS8PQkre6H/k4CsvZiABT4HTdgDOOBcn/Zf3eG9WHtc6tSpeKwzl6m8XL9cM+kUR3G0VuSo
1whllLcLGdWl6bqV2on8/312CVzGnNZOUrQVATOYGEorRFGMaBwhUQkEa3hSoB0GmG4G+H/+0Hfjq177avzB55/AP/rRn8DmMEJ/
NEaUMJgEhCfh+T4aQZCNSfODReSiBmnO1TneD60dQROuio2kGgWUt0VMefWZY4k0gY1J1a3CkhZCceeBVZuU9JLxuUTyQxd++gPL
LnP2L2wF8PDDD4tHH31UY7j6Qek33zHWMqE9g39y8JVBO7d/qrLcqIJgE6GWQUh7BD+hOMorgoMWuKswAErb404oUwU+4lKFUK7x
dc3KW6mk4AJBPv+aNmV1+XeZRXZdqzxUmKI5Cj/gMglm79HWwYhApSmDe1oyQ4DQDAJM99qYm+5hZnoK7U4H8EM8e3sDn/7SUyAA
n/riU3j29ibgh2h1upidmcLc7BSmux20wwDCfX/JRSioflnaKfkpAwC5cA3YjiULyAyjoj40YQ11MqdjEigtIPsQiQ7C+6XGh05+
13c1cO4cvdiHtnix6b2PPfaYevu3/dA/k43Ge4ZKJGbGz3u8XqonlYhJAGA90AdRB7ZQqfqjiWvCGYBYe9qzcypQ4b8KwV4i++Sx
o/ObykRqYXzFbPnw2tmN13lgF/jxWUC7PHl2lHScMtUNYp32uto8PpeSlShXwlwsjpnhFi7Flq1+JDipmqpf16Ds9NSaobWG0jrj
BTQaIa4urwEAbq1tohEGEDYBKs1QSkOzLm0I1tfaXJMBmau9W3GCUmoN3MS9Z/Dv8fXS2BQVXovwdjUlCBpng3HjP+CxxxTOnpV/
IRPA2bOPeI8//mjytvf93W8VnvwnYy0SEingV/OOU4khVkkKNcE8qeQXNb3+Pgw3csZ42Hd7f9Jpj+Jp7M6Ra05vcubJaQCaETlB
CJhPIkiRc6IowwrsZJ0YJKwCCiH7XkFmfFZUvMmfD3Ouk+ae7Fm9wDXjQudrPOnmr6UUT2AJ0oTyj5yWrMCcE1m5LqTEzdUNxFrh
9voWSMi8s6ISn9m+ue6hkWIdlB7dDurGqBFbBYOVAqukioxWMJPiNSPC/hTpSUQpKrWRJL1dhUSEje+869t/4B/g8ccTnH3Ee7Hi
1nsREf/kne//B3cqlfzHWHiayTMTXKI9OOVUP1au4AO1ebIW6EMtG66u5diH8omSoAa5ZZ9T1hOqwpc8uXNPCxsNIFEKSikoe9pp
i4qn10wIytKje/4orS2anj+6EGZuLoQ0c3GRBwC7PSZzhRlXUc4hBgTZ0piKuAK5Qh88QUuR9x+zOEw6I9OYjzfzzULOfqGUHla3
+7i9vo71nV0DDjqlPdsKjifMOcl9Azn/mi70QHmbpDWj6wGSCOsxQ5KdchCDIZzTu0aU1H197nRkIg89B8arWCxDCU/ucqJaLP7F
6e/8vk8+958f/cSLNRl4MRIAnTt3js4+8oiXPLXyUxS0ZhR8RXUcA6qvA2kvkO+gwU8HWRWuC34rf0n76OmVEDN2sgFXZkbs7B8Y
EYtYKURxbCmshMDz0G420Gv3MNPtYHaqi+luG512EzPdDogIU+0WAt8vrJwSEbb7fYyjGKNxjM3dPrb6fWxs72Jtawdbu31s7Q7Q
HwyRaA2A4HkSgedBSpMU2EkGXBrfZfHrcPSJKnzdgkBGdsAipyjns3WqjC7Tli0VDyEmA4zazEISYG3/bhVLPU9iezjC+UtXsTOK
IKVXuJdMJSiy31cQDaFJsmrOdMUR/iMCxkmM+48souUH+Pj5a2iHARTbaU6mYegGMO0rK5fnnv0xFJPU8l3HGB7FHvwg1j9117f/
0IPn75rdPVi2fYkTwNmzj8jHHns0eft7/84jMmx+xVDLhIg8uKc/FU/jA6zmV0Y2dCByxaT/nhT4e+/fE9Xt8junSNoncx4oJAha
A3EcYxzFUFqjEfiYm+ri+NICThxexLGlORxZmMPCzDS67SYagW+CE4DWGolSADPiRJmll/T0seNET+bBLKTMAi6KEwxGY2zs7OLW
2gaur6ziyq1VXLxxGzdX1rG5O0CiNXxPIvCd38nVSoZKfAWuO+y4ri+eoKgMJ0mIgtCeCWAmsMiRSCGErXKsWK8QiJTGuQuXMYwT
SOHQjNOeKHvWovAGUkGKPR9JMBVbuKwtI0IUxzixtIDpdhsfOXcR7UaYLSblBz/bhHOApaA9ev2DiFMQQQxYKi9o3EXj4b/Go49+
Dx7+kMReRiYvdQIwTL9Hk7Pv/+HXQOt/PNKkYEQ89hmv7afiQyXe+iRtP5pMJtoj+Klaz4N5UjJiByBCiSuetrwExYzROMI4ihF4
Eouz0zh9/DDuO3UMZ+44jmOL8+i1WxCCEMexYbv1+1i+tYnRaIRxNEaSJNBKQWtdk5HKstt2tUwISGHGX0EQotFooNtqYun0Cbzx
/jMQQiKKY6xtbePCjVs4d+EKnrp8HZduLmNjZwdgQiP04fl+gXjEDg+e2Bl11bEkHfYSpyu1tdA4FVicBakzoqI8ANKTVmfvWaKB
Pzn3LKJEZ7sUVAL2iIR97lQPstkT3k3cZXoVEUEnCqeOLGGm24FWSZH7T/XF/77j40rrs0/gc2kwLITsa6W6nv/dZ97/9x575r+8
5zf/tK2A92KQfvip1X9LQdPX8FU2HS3slu+1sVaiku6TRZ9X8Ivyo9PEJRQqmHy4rD12Yi/niwsSYGaMoghRHCMMfJw6uoTXnLkT
r7n3NO46dgS9ThNaa+z2+9jc2sT1q1cwHA4QRxEAhicFfM9D4PvoNgP4XqtwulPWxxedAbRl0WnWUIlCkiSI4gRRNMBmfwsrtxWU
0iAh4QchWq0Wer0eXnf3Kbz1VfciShLcXtvEuYtX8dmnn8MXn7uM2xsbYACNMIQvPTurMJOKbB7u4gDa0eGmonMKZ30w74mGk5Xa
MupZZCvptB0oYTr2pP/y5RvQ8DLKtTs7d4VMqrM2KjgaFYA8dvj/WbWicWxxAXNTXUhKlYpzFmNRKahGzknUOUaVD8RSgFMNnbOQ
OxmKJI0FOEiGP3r/w3/ntefuXxhYZwf+M00AKc//off+0PdQEH7lkIUS5O7z0/OT1BLi4Elir+qhpuWAS4itlGO8x4ZX8e/pokqi
GDvDAQQRji/N442vOoM3vupenD5+GK0wRL/fx9raOi5d2sCw34fWCr4n0Wo0MDfVRSMM4PmeOWmURqISxLH5HI3GSGwVYIBBXbm/
DNhnPj3PM4/dbGCq14UnJSDM40ZxjOFwiMGgj+tba7ikGM1WB0ePHsPCzBS+ZnEeX/PG12B1axtfvnAFH//COXzh/EWsbu7A9z00
wtBu4hX5ycQ1fGL39Cq0Bmn1UFNiWaCRnSadUsXgNIC0yNEFIuyyb3v94jURJXnwvMrIE5Uh/JQXex2GBJOhJWtGIAUOL8xibmYK
rcCD1mxBOnZOixrrJJpkH7VHx15J8ntsWxOJIQsVNJp3RePhj+DRR/8pHj4n8RjUnyUTkPDII/TVN0fdaHvny+y1jiTkszATrQpR
p1AN1JhxuHp/BNpjIiD2l76iPaSwsuRNVW8uKgY7lwKfiDCOYwxHEXrtJl5372m8440P4FV334F2q4md3V0sr6xiY20N4/EQvhRo
t1votNtoNBogMrjAcDjCcDTCOIqQJMoQ00hASg+e70FKD9LzIKQp7aWQZbkMKIsNJCpBkiRQSQKlTPvAbLjyge+j2QjQbDbNqe55
GI3HuHDxCg6fuAMzc/NQSWIrEQ+NwAcDuLW2gT/+0tP4yGefwNOXr0Mz0G4EEFKaysNZC06vJZfflDKLsNQ/MFXdhLRzIrMzqWCt
K7sJzJPm+1VJLy47Dll+hYbO+BJZgrO8AwYgdYRf/pf/FFPdDt799/8JtmINT4i8ukl7fyGqrDG7KloxPqlTUKaaPQreQ0/RtIDs
c8KtaDQcS+9VV376313CI4/QC2EJei+U7ffYo4+q6L1/5x94QevoUMtEgD1XGw8TtkNRO+8/yDhQTKgmDxD8TptK5VOeGMUlsBwC
T8lDo8j09ofmZvBNZ9+Ed7zxAdxxZAnjKMKt28t4anUFo+EAge9hqttB99AcPOlhHEXY7fextraBcRwDJOAHARqNJqa7MwgbDQR+
AM/zIKW09FXnQJjkFFQSrmRmM0pMFOI4RhSNMRoOMRwNsbm6AR3Htt2QIOkhbDRNG2NMlKCUxs5gCACY6XXw197+FrzrLQ/iC89e
wG9/8nP49JPPYnc4QrvZhBQCinW2wshUQ5e1/XtqL+Yq9JAL/LmuPsxgd0ZqsQdzOnDholCduCeRgx3YgLJj1KphSpnYwwXdgEQp
zHdamO510Gm1MN/rYv32BvxQOmvDJd/IWu847D0a3cPDYqIllGkFKCZP6bDZDsb9RwD8TZw7J/5sKgDDR+az7/sf5liPnmS/PZeQ
x4IgAKpu9U0SjpjA6aeK4ARNWD2t2SDcK/gLsk5VUUp2+kEiQ8wZRzGG4wjHlubwdW97Ax56/QOYnepiY3MLN27ewObGBqQAprpd
TE314HkSg8EQW9s7GAyHYAg0mk202120Ox00Gg14vgchRInhZ5F4OLTeEhuvrFRLNTdSLozC2YhOKYVoHGE4HKLf30Wr1cL0zMxE
g1K2zDohCK0wAACcv3YTv/bxT+Hxz38Z/eEI7WYDUkozFssCzqW9cim5O558TqDmCcR1B6rnK9TuGdRw6LMV37LiMac0ae2wJ7Xd
SNTZog8R0B+N8fpTR/DT//wfI/B8fM8j/2/83hefRbfdhFL5yI/T6QORyyzLWY11myEOiLu/enKuIl0jAc+eVtxJhjFYv+aZn/0P
T7+QKuB5VwBnP/pR8TiQaD3+e37Ymh9qkRDg7dfvE+qpvJOXe2iPvfPy16nivEeuIwxN2NRlLjjuEhhCEuJEYXt3hGNLc/jat70B
X/3m12K608Kt5VV89vMXMNjdRqvZwLHDi2g1mxiNRlhdXcPuYAghJTrdHo4uHEKr1UbgB0bUwtJvNTOSJLF2MvkplFeRRtgC7nai
q5BLyHABzdrSZl0Goi3TnaTQaDTQbDYxOzcH1oYyC540QCa7TQf0h2MAjDuOLOF/eN+34Bvf9ib8yh98Eo9//ovY6Y/QbrWc5Ek1
1uWWJyCcuGdLpHH376kGA0ilzLhqgVZ/kJZbEZ6AOubsBF3eubDvgVIKhxdmEXo+JICjC3PQ6qmi2apwdqkrAo68t6LwwYUYJmIH
BFAipFJhM5Sj/v/0QquAF+SJ887v/LuzUcRPIT39AVGYuRLqZaPq5KQmaABMOtkJE6jEVJSQcll8RKXF+ZI5RVoOMzN2BgNMdzv4
+re9EV9/9k2Y6bZw8/Yyrl+7jvGoj163g/nZWQgpsLm5jY2tLWgGur0pTM/MotPpwPP87JRJAz933TUzbSklpPRs2W+473GcILJV
h1IJxuMIo/G4RKwB2u02hBAIggCB7yMIfHgpyYfNVp1KzCRAa52Zc5LLtpukjlVDlUkTTDMIEPgenrx8FT/3u3+AP/riUyAyAGTK
w6e07y6U+FQaG6ZjLRcgq3fdYQePqbf0cgmDxRXHIiVa59wNbU57zcoakXBWAQghsLm1jR/+1nfhR77rvSAA/+6xX8b/4z//Mqan
eoajQeRoA4j85BciYyTC5QdUfAOqNm7VLUqq1QsoKBQQ2FMKnWQYxVK++uJ//vfPPN+NQe/5kn4ef/zRJIrxXi9szo9YGsYf7bfu
vAePf6LcdJ2O3f7Bby4WFeW0uMYf1pWgkgKD0QisGV/z5tfive96O44fmsft5RX8ybNPYzzsY3qqh+NHTkErhZW1dezs9hE2mlg4
dBTT09MIgiCjkCZJkpW0BEBKaUt/D1prDEdjrK6vY2V1DcvLy1hbXcXmxgZ2tjcx6PcRjQZQKgGrBJzE+TwzdbAOQhAIXhAiaLTQ
6nTRm57G9MwMFhYXsDC/gLnZGfS6HTSaTYAZSRIjjhNTPRBVxqiTgt+00ub9G8URBtEYp48exv/y3e/DH3/5afzUb/4+nr56HZ2W
wQc0a2f70aXFioKFeSYKklEyuLYvJnceTmVWIRWUxSbT4thZhy7tPGTTv/wnJQEnDi+ma1s4trQAT+QsweKaMJyWJ7//KsUs0/M4
fqlKoqI6nhVRLGSig2Yox8PvBfA/2o3Bl64COPvII1I/tfJZCjqvjCGZADHRFKLAA6C9paMPmgAmTRmqjb1z2nGN3rwZ6Wlm7Oz2
cdeJw/ib3/g1eNOr7sXm9jYuXbqEna1NTPc6WFxYQKIUlpdX0B+O0OlOYX5xEZ1OB0JKu+Oez+eJCL4n4fs+NIDtnV1cv34Lly5d
wZUrl3D7xjXsbm1Aj/vwSaPlC7QCD83QQyPwEPoePCngSYHAk0iUmUFLu+M+imOwBiI7/x+MEwzGMQaRwjBhKOHDb3YxNbeAw8dO
4OTJEzhx/DgW5ufQaITQSiFOYiSJmqimVM0HeYhoi6S3m00Mx2P80h98Ar/wkT/EYByh02rm0wKyfXJG8qFaFWKuLIzRHk69JU8/
Qr1fH6G4Dm37/PT0NxuXee+fqQIJQjIc4if/6Q/jLQ+8Cgzgc089je/4X/4lEDRycVByJgIixQJENnkgd1JQrm5Q5ZsUlJXqHJu4
IiuRYkc6ZCWa8eB25DfuvfzBf7P5fCjC3vOd++un175KesGrIoYmgpjcl9HzsNii6rbMRD5AOfidXW7K5/pUMIG0KcAJfmlPfQLw
8F95G97/7ocQBh6ePn8ey7duotUIcdepkwARbty6hd3BCFPTM7jr+Cm02i0bCBoqSbI3yZMegmaARCmsrK7h2fMX8eSTT+LqxfPo
b6wiRIyppofDnSamjjbQavTge57d4jNAoLkncyMKpTS2Iw3FwEwDCHyJjpVUFLbcNEtDlE0DojjG7mCMzf4VXPvMszj3Rxrab2N6
8QjuvOtunLn3Hpw8fgy9bgdaKYyjKDfdLNBm68VN0opgdziEEAJ/410P4U33ncEHfvk38blnL6DTbkIImcl9gckg/Bnfn6qrtFw2
L53U/9LBji7O33euyIVzaQHI6f+18R84ND+HdEN7YXYavXYTG+MEsrw37QQyOUQjrpRXDl5QSwYSFSfoibNsd72eICII1QwaS0E8
/iYAH8TZRyQefzR5SUBA0vydCAIwS5MADurEuwcvmg70vtLkDZ064o4ojvTMm6QhLGNsc2cXp48dwvf/9Xfjwfvuxs3lFXz5yxeg
4jGOHzmEdquF28sr2NjaRnd6BnffcwrtVsuc9Drv6wURgjCEEBJr65s49yefxWc/81lcvfgsMNzGTMvDHdNtzJ2ZRyMMDPlHMxRr
KM0YRUllTEVO9ZMohYQFWEjEcQRPGo58YXPMGWEREaSQmJ1qY2Gma8daGrvDEVY2r+OZPzqPP3n8t9CcXsJd970CD7zmAZw6eQLt
VgtRHCOK44LMOoMnXm5h8YuNnT7uOLyE/9cP/A3818c/gf/yO49jFI3RbDSgNBt3I8vxZ0oXb6hKmmHXxo+LQTQJDeOqz0Bh9Mg6
m7Iz1wirlBh5SmkrRtJFYnGN6V4Xc70OVm+tw/NljsdQsXViyvcTwS4gWxZvLHcn+xD5CPWij2myEQIxS/a0/hsAPojHoV/sFoAA
8Nnv+uFpPYqf4aCzoEnaKo8O3NNXwT/afxuwPB7MyshiEJDLpyTXuZ0yEogQBKU1+sMh3vXWB/F93/puNMIA55+7gJXlm5id6mFp
aQnb29u4dXsFYauFw0eOodfrgrVB3dPAl0IgbDQQxQkuXLyMP/7jT+GpL34e0fYqFrs+js73MNNtw/MElGKz+mvlsKgGDC1rGaTM
N6UUNsYMDYEpT6ER+nacVb+fUBS1zFsdKQV8CxQOxxGWN3ZxbW0Xm7HA9KETeODB1+O1r3kNFufnbFUwLkwT6nkJ+WZkmpSm2i18
8cJl/G8//yt47sYtTHU7SOHBDA8Q5OBCVCCMZKcg5UKbRfKMrsowFIxEURH5cFsA0wbonBiUUXw1hCDsDsf4qvvuxH989EcQa2Xo
0VLi+/7v/wq/98Qz6DSbdsvSAfqEAwimxKCslaGi8nnFRt4lpDpLSiXF4sJqOoo25gywxwqtaBhBiFc+99P/+/mDgoHeAb38xGOP
vUdxrN4hg8bCGKTLKvGTBBBoYslP+yvz1jL96jTU2HJHUVDeMctbNmClwHA8RuB5+Afv/2Z83Ve9EWsbmzj35DmoaIhTJ44j8H1c
vnIV4zjB4WMnMDc/D0ECyjLsTBIRaDWbGIzG+KNPfgZ/+LGP4cqz59AREU4s9DB/aAmeFIgShY2dfga6pTRiIQiChF3iIbO/L3Ip
a3cngogMxXUUgaSA7xF8z8u35Ni9yZHxCFhzAexku1kYJ4kd8wkcW5zByUOzGAzHuLZyC3/86z+Pj//uh3HvA6/Dm9/yZpw6eRys
NcbjyAHg6oM/bUcAYH23jzMnjuFf/t3vwQd++Tfw4U9/Pm8JNFvWen5z52vEXGSPW4ow2ZVmJlRXrytinoVtJgcvYKfXd+efuqiK
RASt7QiQBCJOwAACCBxfmodWT+bVSWFv2plzas5BQUZxT6I80yeu9zAo/NxBVodBCcmEwmYooujrAfzrsx+FeBzQL1IL8Fh6Ib8B
0mdooQtqQjX6fHU9/b5Bj7Id7uS8ka+sujN/12gyz6pSmh36E0sL+L9+17fivjtP4MLlK7h25RJ6nRaOHj+Nza1NXLpyFb3pWdxx
13GEYQitNBSrrD9utZoYjSN8/I8/jd/78Idx/bknMd8SuG9pGu3mFGKlsbY9QKK5sA5BmQcBZUFtuPwmGFOWnm95/Z4nIUlASAEl
BeRQgYRAEAiEQWiRdi5s7mWjRl0ePyIbgWn7PVprjMYKBIKUEmeOLeCuo/NY2dzF+c98BP/Hp/8Id7/6QZw9exanTh6HsjhBLnnG
9XRcmD2FwXCEwJf4kW//67jr2BH8x1/7MKSnEPpmp74A6hFqZMWLJTQXtLZdReMy+Kcd1iEX1H2y4M+Hm1Wkk8wS0InDS2ZN2nld
R5cWDN7kaBi60mLEDCYNsCjIiKcVaKF7oZIdoduJZIUSOc9/H4Uhw5SlhBk+J98A4F8//nZoPI4XxRiEzp07p89+1yMNJIN/oUQw
m4UcUS1Q59o115b0zsy/Xv2Hagk/FT2KdPJMdZpu6ZIIsLXTx4P334VHfuDbcXhhFueefhq3b1zD0UOLmJ+fw9Wr17G508fxk6dw
+OhRSIvspwHTaJge/9Of+Tw++J9+Ch//nV9HM9rE3UdnMTfThQIwGidIlAbDnvJC2ECXIKvSI4TMPs2mnzk5NAhKm149VgYbMG2G
hPQkxppAwsNMK0CzEUJKAc/z4XvSjBiltLwC85nzDOzSEBnDElEwLckdcaJEQStGt9XAyUMzWGwRrl14Bh//xCdx9dYqFpYOYX5u
FmANpVRtci7qIhicYxTHeN09p3H6yCF8+twz2B1FCHwvxzCc5O2W7bVM2MrmXrkQ0NWoKkuigYsJxNVzFGYqpeIE7/nqr8SZEycw
1ma/JhASt9bX8eE//hz8IHBYjSUFIJcW7Kg1561qje1a7XSAJognUi1Jzr6XxMwUJPFc98E3/qetf/OvdvAIBB7fexogD4L+nzt3
jk++8oHXguh/TMgHGQvdCdTdPfp44e5oU8VQpbDsUzHp4ML6J5XTZkHgMV/g2d7t491f+Xr8yHe/B2DGl8+dw2BnC3eeOgkpBS5c
vAy/0cLpu+5Gt9sDq/yU9DwPjUYDzzx3Cf/5p34av/vr/xWNaBNnjs5hZqqDRDPiWBlkXBgNu7ScF1aeS9hxnglULwtYM+bz4KeB
60m7BmyWSJQGYq2QKIWd4RhgjfmpNlqNEJ7vm0UgpdFqNuDZqsGT9vd55vFlmniy5GOeX9HjML9/VWKUi8LQx8mlaSy2Ja6cfxof
/8SnsDkY4+jRY+h12ojjpPDect3c0D7+cBTh9NHDePCeu/D5Z5/DyuY2GkGQax7UUMWZq4BfhrKXaLWFEp+4JKDqBHoZAHS0FlMS
OxHBE8B3vOsdODQ/j1hrw7cQEv3hEP/t458EW+CTXaJTnUVYeVmBylJLPGHmT87RVuoCeLKkNgGkmXVDioaM1SfWv/gnT57FWXn5
8mX9p2oBlpfvN89Dqa+gsEXMZBV/nifGSNhnLFhP+CkSLGrm/ZnrTpppdfYju/0hvu2vfhW+91vfhdX1DTz7zDPwJXDmrtNY39jA
reVVHDpyFIcOHzEdoe31NTNarSY2t3bxC7/0q/jYRz6MDg3x6pOzCHwfUawwGsd2Z6DGOlyQKeGF2ekXlPvWkcUATCuQVz2ZqjCc
JElGs67XCiFBGEYJhIjQajTQCEMknkIYhsWS31YPOU1Y56vFlhmo7UmuVb5yzKwNL18DSaIRJwrtRoC33n8Cq5s7+MLjv44vf+4z
+Oqv+wa84cHXgq3EGdm9BkzYXJNCYHt3gJOHFvHPv/9v4J998Ofx1NXr6HVaSJQ2eEAm6ewKizg0Yfv4ukimd5B+KxxSJ2XOZb0/
V803R/MFCSTMmO20sDg3i8i5PWMA8zNmFLg+ig0fg83zSQlM2k1YzEXN3QJQSUUjhnQ0SlRiX5XzBJVoyDVVmBBawxMijt4G4JeA
twP79AH7BvLiovEl04S3CBKTBQv24jFPMoekSaYdE0Z9VARJuNQXpqUZM9AfDPG3/9pfxfvf/RCu3ryJC+efNf3+kcO4du0GdgYj
3HnXGUxNT+fceq0hpUQjDPHZz38Rj/38z2HrxgXcfWQWvc4UojjBeBxbJR4qWIsbcM+CeULYnf00AeQgX/pzwkkYBTfj2vbI/CVK
NJLBCKM4QbfVQKfVgudJx3AjN9tIBUNM8OeJQKcipEpD2wpDZ8lBQZFditGEKFGIEoXpbhvveKCDCzfW8Ks/9R/w5SfejG/4pm/E
wvwchoNBtRooHYhCEvqjEaa7bfzz7/8uPPqT/wWfO38BvU4bSqfUbdM+GTqvzk9B1mAqj/F1cZ+vXN5rLix6FUChEn8kW6ISBB0r
zPe66HW7UDpvdZRW6HW7WJjqYXW4Ck9KkFYQDOh0sAGGdvv98gpqST6AqZzM9sLH86WWynUuYAtECQMB+I0A8PhHH1X7zfnkQfr/
B7/v+/xgLB/VMpg3q54Ot09UpZfqtgGpJNRQy/Sjes1AZsokouoVd/MKAGDs9of43m99N9737rfj8tXruHD+POZnpnBoaQkXL11C
rIG7ztyDTrdrg98QaJqNEINxhJ/70C/hl3/2P2MKfZw5sQTPkxjHidkUFNZe3Jb5bu8tPbPL73ueLcu9bNXXK/XrplyXJlHYvj3V
AMhaCEo/i8lFaWAcJdnMPvR9+L6XlfuedJ6bgweYf7dfS59/uUKp0ftPtEkaC9Md3DHfxqVnnsbHPvk5hJ0p3HHyOJi1syVX72Uo
iJDERhjlba9+JZ65cg2Xbi6jGYbZVIORCoSUHJNRrJ5TsLdI6dUlh6XJ5J/sJaaSap4RVkl0gvuOH8E3PfQ2U504wkbNIMBHP/N5
XFndQCP0J67z0r6af+w4RFOV8ORuUmb3vtvrU9WLMldmIzCTr5LO7Ovf8hPr3/yp/n7Iu9x39ffxx/mu+95+Elr9Yy0Cz+it2xwn
Kr6wFUcfogPO9yt0YS7qelkCSUW3nhyNfSbsDob43m99F9737odw4fJVXL54HocX5zEzM4Pzz12AH7Zw+u4zGcqfls/tdgvPXbqK
D/zYB/DMZz6O+47NYHa6iyiK81OKTPlugsorBH/ah/vZnx6kVwx405PbXj+rECgLwLQ1KFcIaetApSBNNGMcJUiUgicdoU/7HIUN
evN8hSMbnieBDCyk/DmJAtsyv+niJIEnBE4dnoEf9/H4xz+Ble0R7r77boRhgCRJSstGRRIREVlRUg9ve/Ur8PSV67h06zaaVnGX
ypFOXOV4Zf0+smQBLqv66YKMFlmXYEHGdjzVa1bMlk4dI04SbO7s4CtfeQ++5g0PYqSS7Bpo1mhJD3/8pS/jj849DQJhnCR2ooFs
rJuCrZltfImVWij795yZlzYkC8Bg6XuoKnEVgJuskl/eeOJPru7nLrxnAnh4cVGcO3eOT7zqtQ9K6X+PIk+DSORgXg3xh+opvDRB
y49oD2DQ2S93bZiISpneAjq7gyG+96+9C+/72odw4dIVXL70HI4dWUK308H55y6g3ZvBnafvMii/DXwiQths4Pf/4I/w//vxH4Ps
38a9J5cghECc5Kw4E1QWrBM56OZ5Ep5vAL785HdP+zwYhbRovNsSZHhAKdgtHlDGDcrjRAYQJWZMBwZCKzACSXkFYQM8bUvSKUU6
MRAiBQ1F3tJkv8M9uEzQxLHCwnQHx2eaeOILX8Dnn3oOJ06dxvzsDKIoRp0Dl1OlQmkNX0p85avvx9NXr+HKrWU0At8q8+QlOjvG
qQxUjDyNxBec5ExZUk1xIMWMOEkwjiKMojHGowhaxfAFMNMKccfiHF5953G85f4z+Lq3PIiv/aq3otfrmYbEdXkC4ejSPE4vzeP0
oUUcmmqj5XngJMF4PMZwOMJgNMYojhEn2pCfyEnuQjhGNDRBzahkZUY1iZhQMFMpz8g1QTckhFDq4+tPfPrzZxcelpcvP65fEAaQ
A4B0L4U+mKlC/93POff5G28CxSEfl953LqyJEhlPuc2dXbz/3W/H+7/2IVy8eg1XLj2HY4cPodVs4pnnLmB2fhHHjp80JZ3tiQ2t
k/AzP/sLePy3fhV3LrQwP7OAcRRnjD1CKr/tlM1ZSS3zMlrkJ20WvAWcwE2T9UzAWhFdxh50WKsXwIw40Vjf6SNKEsz2OmiEISBz
GSyWRngzldtma0SipYDWjK2dXWjWaIQhYplAJQLSyo5RYg1MlIZgDQajP4oQ+D6++jWn8Lnzl/Ef/+2/xre87zvx2gdeiUG/n+v2
1egOCALGcYzA8/A/f/vD+Ec//kFcvLWcrRWbHxMW0+HMmIQc0I7S7xEG64gTDWUl0rRKIEEIPYlOM8DczDQWZ3s4ujiH40uLOH5o
EYcW5rAwM4PpqR6aQQjPQnYjAJFz+qeBGLPG3SdP4lUnTxpTFwDDaITN7R2srG/g5soarty8jWvLq7h6exU31zewtr2LrcEI40QZ
8RQStk2041opMglz7S6qETmYHxdvBHYoeMw1klvETBLQfP+LtgtA4DtQZ5lNz0ff/HkIhJZBn2xjzLGzsrJRkggb27v4ure9AX/7
r70bV27cxOUL53FoaQGddgvPPHcBc4uHcOzY8YwYo7WCH/gYjiL8xE9+EOc+/TG88sQCGo0Ao3FcyL7pCSpLgZ+W0W7gp1tfUsqM
/FOseKgwyeEJF6KQ80VZipxrBvCG8KCZsTMYI0k05qY76LSapnqQRvYLMOCgAIOFsMCgQdyDwAcBCHwPMiIknoCME4hEQJBCQgmI
EmhlTnBAI04SKE148MwxTF9fxYd+4gPY+JZvw0NnvwKj4chx+KnKrAurvd9qNPBPv+u9+JEP/CTWdncR+oHFBHRFszW9DEmiEMUR
VKIgBNAOPCx1WpifnsexhVkT6IeWcHRpHotzs5idnkKn1UJAAsIGm7JBrLTCMIkzvYa08qmrmcdJjKEzYhaej4X5BRyeX8Brz+RC
wGNo7PYH2Njaxq3VNVxfXsW126u4dPM2rq+s4dbGNtZ2++iPIsSaACkRBIEBF0EVzlBVXJgnqx0DUCD4hDsA4PHFc/yCE0A6AQDR
HTxpFWtfZ9iDnfqp526O7nMhGxi3F1v261yae2t3F294xd34ofd9E1Y31nHxuWcxPzeNmakpPHP+OXvyn7D8b/OGNxsNrG5s4QM/
9gEsn/8iHjh92LjBjKNs0y3r62zwe9KD9JwkIGRe2tuyWWmNRGkEfl7CSVFi/6VlakncMEfuc8vsxJKC0rGTs+I4YS/K3LiDKIba
2AYz0Ah89AdD9Hpt40EozWaOVhqCCFoIMGtM97pYXd8EEaHRCBHHiX2NCWKZGH5DQkiEMhWBRlZF9AdjnD46j25rB7/7iz+N7a0t
fMPXfS2iaGxIP44Wm0veEcLQsxdnpvA/fftfx//8H38KSRJDCs8EJLmIvUW5kginZru4//Q9uOfOk7j75DEcPbSE+dlptPwQgb0U
yo7vEpg9jFGSYOjoCpBDPCubuk5m2xGk832aGTqJEbG7bGS+L2g0cKTdxskjR+A7gZYA6CcRVjc2ceP2Cp69fA1fvnAJX3zuMp5b
XkfshbVJEwfdriUic//o4wAIH/qQxh6vbc8EcP/996eCdQtcdvCd6L6K4o1KByn5y0YdRfcVLkDAaYFIGI6GOHFoAf+3734PxvEY
5595Gr1OCwvz83j2/AV0pmZrgj/EtZvL+PEf+zH0bz2HV54+giRRUFrZ4Lc9mz3h0z7ey0A/p3e2wSykxPbOLlgzFudn4AkB3zeg
nKH3uuh+nhBchNul6Wq7NLS6sYn+YIRet4UoTqyXIIOJC4y5uoprHCusbu4g9ATGUYRupwXpSwwGIwNqNZrOggwBbEaCYeAj8H3z
HJW9Fkne5ogkRkIAJYAiY3vGmrE7GGF+qo133u/ho7/7KxgNh/imb/4mSNZQWpU0/PO3V0iJncEI9508gR/6a9+Af/Gzv4hmKAsn
WmGAJyQ2RgmeunYbq7tDPHP1Jg7Pz+DwwhwWZ2cwPzOFmakeOu0WGn6IBgiQHrS0p74djWqdJ9rCEtY+icBlFjqNWEYA80hAOjx5
BWA3jrDT72N9axsr65u4vbaBm2vruLm+idvrm7i9sY2VfgQl/Qn6oqXnlNoAUM2CJDNpACzFDL7vxz0QxXvpA+xXvPPDH/qQXP6l
j31Oh+1XxRDaFQChujn/JHrwPrv9Ls8hG/fVzHLZ2jZrZZD5f/EPvwenjx3GE198AlAxTt1xEhcuXoL0Gzh995lMFVYpjWazgSvX
b+Hf/eiPgrZv4K7jS4jiOGcOihw0yxl7OaiX03kpo/lKKRAGHghA6PuY7nUyXn+24FPnVnSA9cy07yYixEohjlMwy9iOJUrnG4ZF
45nsYvqewPxUFzPdNkgI9AdDsNbopsIdhRvaYgOKobVhGiplEkOSJIgT410QxTGS2MqSK5VVAgxGw7IUf++Jq7jjwbN477c9DK2V
0dUvnZ75tM7YoU112vjJ3/gd/PSHfx/T3Q4SrYvyWvZaJlojSfLfD5tgGr5EOwww3WlhYXoKh+amcXRxDkcW53F4cR5LczOYm55G
u91CKLxCkJrPlOq8x9hMSkiYIJfpCjGAsU7QHwywvrWN5bUN3FwxZf+15VVcXV7D7c0tbOz0sTOKME4UEmZwiglIz4xxhbSaApYP
QWXbMVEVPXWkglI3eZ+YmqPdlUQOzlz+4Af3FAjZFwP48mNflvMeQuzn8PW8xA7L+t4lKS/OxTyoMObhrFnojwb4h9/xLbjvzhP4
0pefRDQc4Mxdp3Ht+g1oSJy+87Q5dSwLrtls4Pqt2/h3P/qjEDs3cfr4EqIoctDpFOCzVlspop8i/1JmozpPSgSBh3YjRKsZohmG
CAMfUsrazTmeaDSKTFgk36/PJxwp4MjM8H0PaITQ3IKyyWA4jjAYjTEcm74/367Lb4440Vjf3oXvSXRbTbRaDetBmKLU+eadNr8U
AgwSPohU1ga5oy5BhIgSUGJRfWXDRwOjKEYYeHjnAyfwkc/+AX4OhPe99z0Ax1k7wDWyQ1IIbPcHeN9Xn8UzV6/jM0+fR7vVtInD
Fd5gSAK8wAPgZVOkVIVopDWubfVxaX0H+plL0KwgAISeQKsRYq7bxuLMFA7Pz9rksIDDC3OYmzaVQ7vdnkieJwA729tY39rG2uYW
bq6s4fryCq4tr+Lmyjpub25hfbuPneEYo0RBwQJ/0txLgiT8ZguBo5moKz4AVB3vkcMqdNmxRJPHiEAgVTP4U4OAPWx3mPW8rrHl
KZq9vEDNszrRwxJ87C76CEHY2t7F177t9fiGs2/CxUtXsL66jLvvvAPrGxvY6Q9x5t774XteRnMNg8D0/P/7B0DbN3D6+BLGUVxg
gaXBZk58LxvzmcA3K7ueJ9FqBOi2W+g0G2iEgQH8iEpeM3t/lH3odvpDgIDpbidHfYFCX+n6xHl2r6DRCDHVaWEcxegPR+hblqBy
zDSIDKNvdXMHnpRohkG+c8+uu66GYGP5xcJx/dUEUihNNdwRVQSltQFBoY1UWRQj8H2889XH8XuffRy/0mrhW775GzAej6EL0BVX
2INaMf7uN389fuTHfwKbu334vl/YEqwIatqkpylVKxIIPELoA0Rhdum01hhpjSsbO7i4ugn19AWAGVIQGoGHTrMJXxK+++v/Cr7j
a9+F3XicJWStNTp+iJ/+jd/ET/z6hxEpxs5giFGUINEabKtBITxzYDQa6IjcVj1tF3QmT5bzAbjQS1Np64/2d9LlqmCINuBrW3je
PIBlKxdee1u+IDOB+qaf9wz+/MauX2tkZ70zu0iuqINlcA2GI9x14jB+4OGvx9r6Jq5duYyjh5eglMLN5VXcceo0mo2mLY3NyTkY
jfGBH/sA+jefM2V/FGeVRB74Xhb86Tw/JfIEvkSv08Sh+RkcXZzH4swU2q2mOfEJRVLGHtLVdZ8A0G410G42qk4qhTaJqheMTUna
ajUwPzOFI4uzWJzpod0ICmAV7B7B2tZuZk9eIWezIRAZzgEg7apyCoCm5KbA9xEG9jP04UnPaiD61tzEsCQj6+D79lccwxN/8Jv4
7d/5PSNQmurwub29fa6CCOM4weLsNH7gm77WVBbOunNBMYvcT8rdipCv5SvNuTJyqt7keWg1QvTabfS6HbTbHciggREDVzd38Zkn
n4FOpcScmlMD+JMnn8WVjV2MNCCDBtqdDnrdLnrtNtphA6HnwU5ljTis1ki0kXPLnAWt52P+PlPx1Bd124DO6K88W69YkeHPyByU
JvQDeyoDl7MWV1RRChquGeXTXlQr7/SDD38dGoGPJ899Gb1OC71eF08/+xwOHTmKqempTMBDWEWWn/jJn8Lt81/Eq04fQRTF2Rqq
EAKJ1hDMCFqBCfwSbbfVCDDT66DXaSEMggp/f0+OwwQT0/JH4AcWJNMFtL+AoZYdeNzLaf8pCALM+D46rSb6wxG2dvsYjuOsitgd
jrC542Nuuls1rKGcree+B4YcxBnxy5OE/mCIJEnQaJgK0/NkZnhKMM46EIxxFKMZBnj7fYfwkd/6ZfR6U3jrm9+AwWDgtDu5bThb
w9Td4RBvecV9ePebX49f/cNPotfpZDoC1Z0SUR2ZUd0WnlNRpfdV6uNpNzkbvoeNnV2MVZzpNKb/PlIRNnZ20Qh8ayeWLl/liSzD
U4tutg5nAyXRz+J9xEA1IThAI9f6ne6tm7Hfx8ErAC6P9KnGsabGAK3m1OeaMXZRqNEVdcz7vu3dAb7lHW/F6+8/g/MXLkJFIxw9
chhXrl5Hq9PDoUOH7bzbPJ8wbOBDv/jLOPfpP8D9pw4hSZLsJiqQezJBjjz4m2GAuakOuu0mZqd71iizyNbjwupq7dFk6RMOc6v0
mb7527t9DMdj6xNQ/LcKl6L8GG55TIDveQh9iaXZacz12vCs04dmYKs/wGhkx52VaswBcp3fI4hykpOQ6HZa6HU78KVnpgaehyDw
4Xt+dv3SamI0jjHVbuLNp6bxm7/4s3jy6fNoNhtQqQhpQRcPmfrxcDzGt3/NQzi5tJh5IxQ1CqnaFxNlm3IZHd117amJjFTOTCsN
gsDKxjZ2+gNIIR35N4l+f4Dlja2MyZhxSkrBn2825k5BJERmZ+46B8GOj6vVgCjcH1Q59Sfwa+j5FwLihZ36+/T7dJAnVVqdZErD
3e5bu6g/MBiNcfeJw/iOr3snbi6vYPX2TRw/dhQbW1sYjWOcOHGyAKq12y38/sf+EI//1q/i/hMLBq3VuctsGvytZgPddjsrYX3P
w1S7icPzM1ian8Xi7Exm0EkOSSRfUCq/eflNR4ImsqXKlyUF2tzljkoCpWqCyQOW8pMCxt6rEQaYn5nGoblptBoBiIAoVtjc7RcQ
9ux3iZq17DQJOKPRMAjQCH14vofA8xGEQWZS4vupxkHaUgCDcYSj81N4xbzEL/3cz2BlbQOBpf6SQ/MlpxVIlEa31cbf+rq/mikg
Fa3aKVsVIRIZap61Aq5VF4lK0mRnWS+VTRNCYGO3j42tbWP/no4qSWB9axsbu33zdV1wcDPfR85acyGA3edgPin7JMdaTOSagu6h
UY4pUW4T+U9l8yteWMnPewY48yQMvPhkmcsjTNcNRmcecWx12//2t7wLjcDHpUsXMTvdQ+D7uHVrGcdOnEBg9+K13eo7f+EKfuFn
fwan5ltohD7iRNlrLRw2n2eDPh3n+Zib6uLw4ix63XZWEYg0mB0PPCpbkJcs0ak2WNPeu3QzAmi3mggbgcOeK5eBTsKh+tYr1eUT
QqDX6WRryr1OG4fnZzDdaYHICF8OhmO4aQNlRWdHnJRs+W8UlfNpgC9TXMDLHIp8zyQBzyaLNGn2R2Pcd2IRM/EqfvEXfgFaW0vv
yo1uBFGkEOiPRnjT/ffgnQ++FjuDofVFKPk+pjr8zuswPXYq0Cmq3n02WLM+nyljJ+4Ox7i9ugbPMV6VAJbX1rE7HBvyVGEJqeb9
Sk99cvwCbDIgQSU/wZK7kGOwS2UsQEwgAdEL1/sVL6jf5/3Ge1SneFQw6eOSHDQcqq/7SUTY7g/wzjc9gLc8cD+eu3QZOo6wtLSE
q9evozczi5mZ2awn86TE7mCEn/rgB9HlPhZmuhhHsb2u5g1Iab2eJ+0arUQjDLA4M4XFuWk0wjAjvhCVMy6VlpWqFshUVGpxw76U
9algnpkaTtQti7j8cEJ5qcSxXc9MOIrgUDMIsDg7jfnpLgBgZzA02oVlW+sam2/396ey6tkWpJ9rGfq+hyAI4FsClPQM+Sl9bqNx
hDfccxTrz34eH/7djyBshGCtKgzXFCST1pL927/6LOanutnkxp2DUxlltQGXtlJUOF3zFiG/9sLdH8QoSXDt9kpG62U777+xsoZx
rPJWi1MRkNLjCScBZSc+Ob/fCfRCgjJLEkQF8kwB6Dw4nZ5eihaA6+OfJ4336h6Bi2wmd+0znUcX3HqNmu1Mt4Pv+Lp3YmNrGyu3
b+LIYSPdPYoSHDl6rOAB5wchfvG//hpWLp7DqSPzGMVxlk2Fc+P6Mt/oazYCHJqbxuxMzxIyhAWpKNeLghuE5dVM90vkvGcl33hB
9cxIgtPvweFcFhNJ+foWFoyIanp4e08Kc0p6UmJuuov56R6U1maDsKREXGpMSttpuXpONjoVeSXg+z4CXyLwzd9TuTOylYDWGoKA
t5xZwqc/8ht48uln0Wg2jOhqyUsvRcvHcYxDs7N4+OxXYDQeW0tzRxvQzVOi1FPboCM3KCHyJCscUk3WkRKuL6+W1QZwfXkFil01
5Bo8JtN5FNlhQzXOQTkmIfKkldHDRbHyK7gO7x/jtI946J9+DEh1xQDt7UZEdYsMeTugHaMGduSuiQxz7Rvf/macOLSIS5cuodUI
0WoZw87DR49lklhaa7SaTXz2C1/CH33kt3DPsXkodlhywiH6SA+eLVObYYBDs9OY7nWMSAeJHKGu01+YcOoX7Lmre9qln6meHFQW
hygk/5rZMDlyCYL2VFoz2425MMd0r43pbqdiOloWtqjcR1YifWNrJ5uiZLqHFkR1WwLf9zMqdXpdxnGC+V4b9835+M1f+SX0ByNI
IS1JCEWwjwApPfSHI/zVN7wedx87YoBSpy0qqvtRPmrL2rb8hM3/WxSD0dEiJCFw9dYKknw7BQmA68tr1uXZwR+c0p+sWAsoX6nm
rKenmlPfJqcUJ6jzz5xwH/Hz8N98CUDAyQFei+5TpQ8o7Qi4Cq45wcMs54xxfGke3/zQW3FreQU72xs4cmgJy8vLCJotzM3NZ6W/
lB42tnfxCz//szjUEWg2QjPztsEvs9Pfg++bnf5mI8DS3BSmusbjT5CAlDWUZvfkp/qRp6hbKEkJM1KU+kSU+j3Ul3qEai9I5YKr
uGLsnhxCSkRRjOu3VjAYjs36qdUI6LRbaDbcxZPc4luQqKV4p5uOvXbLoUOnIimyphJwkoDI16QH4wj3nVwE1q/gdz78u/BtEi+/
rhQPVcxoNUI8/PavQpIoxzCUixUT1YzRqHjiUqHsFnDF5RkMISVurW1gFI8zSbexinFzbd34QLK7w29P7pJDsFt5ZC1J+okcC6Dy
SQ+qmVrUxcxexLqXIgFMOuAJB/AyK+iv5v4NLgsss0nOt6oEEQbjMb7x7Jsw0+vg6tUrmO6a/nV9axtHjhyDECIjXQRBgN/4zd/G
1s0LOLY4g7FjcZVu4mXLPUIiDDwsTPds8ItMxLMwgnPL6YwJJyoTGVF+syhXOR7HMQbDUUnxmEqXr36SQGkgEkqmIalOgahRjXFY
eswIPA9zszNGAUmzcUFmrjksKBO4jOKkONYtlZihBVUTpXKKsIOrmGrATgQsRpAyKskqOCmt8frTi/jiJz6K8+cvGNNSqzWQO+Ka
1yGlRH80xltecR9ecccJ4+kocvNNRlUot2hTJxw0HiUgtTgOlVJiZXMHmzu7mVTbTr+PlY1teMJJAI5QjIsnlAFeKuAQedtRywgT
e1DqxR6n/gsM/hfQAkygu/L+/n9lrXQ4Tjbpuq+r4zYaj3FiaR5/9SvegJu3bmM02MXi4gJuLS+jOzWDXq+XsbwajRBPn7+Aj3/k
wzh9eNbq6sMpU4tsv8CTmOt1MN3rOKo4VOM8nDr6SOz2B7i1vGasvwtgnJiwAk2FwKXSdI/cUtWd+bvsv/LNkN5QZbSeaqSj7Hsk
pMR0rw3f6vEPR+6KbqlqsP31Tr+fLSFVCCv2rdzZHVhz0BQULC1R+WlLYKcCXio9Zl5bFCeY7bVxagr4nd/6DUSxZShy/R3HzAh9
D9/8FW82gp1cdHou9OzpHglZ080MmS9VcTYgUysuzcZXcbM/wMr6BiRENgLc3B1ASC93Mi4nkQKmOwHhFxPaw4miOa7eHz+/U/9F
JQLx3gIW7PTzPEHelGlywmD7xqcbaYKA4XiMb3z7WzDdaePatWuYmZqCUgl2+0McPnykYM6pNePXf+3X0MUIvXYTcaLstbckllSe
yzOCmYbc04VnnXlTuS2ZjmlKpyozI2yEkJ7AKDIkmkLwlwI/e48ZCIMArWazcuOQELWOSgUZLkxoCybuWE+w+tb5tZqe6kF6smDA
6x6dRISZqR48zyvgA1Qa8073Oui1W44Ya04YSrcofc9DYIVRU5KQqQIsHjCO8cqTS9i+8hQ+89nPoRE2cr+A0o6AIEJ/OMSb7r/X
VgFDg9Rn1t6Fob7NC6Lg21FLpCr12kIIDKMYy6vrEAAkyIwAx1Fmz15I1m6iFqkLchEfmKyBsQepZ8/VeaplhqdxxvSSVABUWnrZ
/9TncvvAro2js1Pt6v0BGEURDs/P4qvf9FrcWl5GNBpgfn4Wt5dX0JuZRavVMuun1rXnM59/As9+8TM4eXgGkT2hC6V/qsCbMvym
uwiCIN9uEwah3hkM7SJNUXuNAQS+j4W5WXRaTYtRiAo5qsgNyH+WS+SoFHxLX38RceYCsae2369LArTHaWKvxSiOsba+aVl4eyyY
kEM7JZRGU+Z5elbjIKtysulAqjFoMQHfgIK+l2skCqsrpzTD9yReeaSLT3z0d7G1vQPPk8X9f0fpVzEj9H187RtfbyoxlIw/2LUG
qzEQcVsugcooNr0cMTOu3lrOvnpzZQ3jRGctIpfm8+zwRAq1fIHJiQOe+vsE/6THqwXaX6QEwAcpN3h/LmKdizes/FMaEMZNZox3
vOEBzE33cOPGDeMwqzT6gzEWF5fsPonZDBxFET78W7+JhZaA73umdHUlnx1J7MAz5XC71cxdclJrMRjV2/Q51AhZ2b64osFWJf6U
Tu1sIyzdCtNO4Gf+ffm/x0niONCWQCCHwktVRHCiAgsDCDwPvW4nY7ntm8hrlXKKWA5K/IMUGEzdjtJRq+87S1bp0hAZbsCpw7MQ
2zfxqU99GkEQ5lUAF4fHUggMxiO88d57cMehRYyicQYIMnRFRq5iI1Ow4q4Gf+5QTLhmR4EE4Oqt5cwJqMLGrFwjKljjVZ5Pwdpq
b1YtH8B8t/7wpZdwDFjL4y8z+rhKBHL6tezdSEUonB9OVIJeu4mvefPrsLG5iWF/B/Nzs1hZW0O710Or1QazArNGs9HAZz73BK4/
9xSOLEwjtn1kWormYz+TBFqNENPddrbbTxBWcw/wpIeZqR586RUQcRSUj1HqwauS5ik67AZ1ATspKf9obQCxVApMW0ejcRSZLTRb
3RZoxVSOeaomgRoGshQCjUZY8GqgmvKBKoNA2tPYqUgboEx52Pc8jKMIa5uGWus7PgnC9sXpAf6KI9P4/Cf/EBtb20bVWHOZOWL1
ADV67TYees0DxrA0TcwFUj4Xeb5lnLVW3YqyFlZIievLq4h1Ag3GtdurBnB2DsOc+VtC8d3qYlJ1tpdU3vNi9TEO9sa8CAmgbr9n
4rB8wvNgKrUHJdskQUB/MMIbXnEGdx47gus3bqLVDCGEwPZOHwsLSxlJSAiB/miM3/ud3zGnv+dZkQtkYxazzmpGUIHnYcpu9IlU
jtui+sWerhhIVKDEij1O/tQIlp1FpsyHFtoi30oZiSzzd4VEG2cepcxnkii0mk1jVKEUGIxYKQyGI0RxlLU+uUSWmCTBXLM6ivq5
f51qUx3YROSkA6q84Sb4UTA0aQQBuu0m/MCuFNvWwCQBUwWMowTHFqfgD1bw6U9/BoHv24lAnTSewWG+6tWvxEynY1q+TDBGZzbp
2TRBT55IlYE5ZrLtjYeba5sYjEYYqxi31jYMAMiTtG+qyZlRcwi6p36J8QrX2p25oNUwseTH84/BF4cIVLFxPuDPcWnun7q8Wjun
FKj66je9DuPxCFub65ibncXm1hbCRgudbsd62zEajQa+8MSXcfO5J3F00Zz+KR9eCIIkmRljCCHQDAP02q0M9XeNMesMS9LTehSN
sxuvXvacXKlC13w6G3fpNLitvFacGEWfOFFIEmWktuynsuM1pTRUYqS0BsMR1je2sbXdtzJecGbXRU+GgtHqBFl2KjEZ09Xr0Xic
ibxMPKSIJuo8kjOlSKcDrWYD8zPTCFKdBT81RrVUa5A1BQPuPzKFJz71h9jc3oH0ZK23ABEwjiMcnZ/F68/cjeFobHcgbPBkPoA2
DRDX2I5PCBJ7j3qeh/WdAXb7AwyHI6xsmueTCamklUvNdt++ArlcOk1rQ4j27uX39dl8icaAvA/QV8h67mTABWbYFVYsjnJG4wgn
Di3iNfecxq3lZUgCms0m1je3MTs3BylEliSiOMEffuxjONTzEXg+lGaLzue6fplbrjRyWIGzz0+oI/oUR15RHGN1baO4uloauZXJ
T9r2+OmJrpXO9fSSBFHsfhptv3EUYzyOEEUxxnFknGriGIky3xP4PhrN0GgEamM6kakkaa7w/t2qpZwFqOZGTcdyy2sb0EqVZtuo
34GoSwylm50c05PMREV6kHb/QorcKGUcJzg63wPtLuOLX/oygtRBmMveAlYBiIG3veqVVoAjD353iSxfLS9FGU1C1c21kVJiezjC
6sYmtnZ2sdEfwJPS3P9EVVYn7XEWlk/98h3jgJflxFBpnSfE4AtdBf5TYAB0sDVE2g8BdKSuyOyOv/WB+9BpNbCysorpXhej0Qia
ganp6axXDoMQFy5exrXnnsKdh+eQJCpvv8jo4GcqtkIg8D10Wo3ctCOdCRdKXyr5Ehhy0aGFefjOSGwSqJkGvlap82562htAzwh6
xoiiyAa7+TP7jOynTQTZZxxD2Z/f3u0jiROwgxtUDG9p8qyYagCr9LWGgY8jiwvWbJTrWamYrHZU/kJOcc9xGM/Zv8gmAtmegFnk
Oj3Xwpc++2mMxnFhJbcwiCaB4TjC/XecwInFBYwtGFgI/BpHEkqt5Or51llyFCQwjBOsbGxibXML/SiGkMIhBzs8ftrL2bq0+lqE
lFFNB87Jz45yEpd8Evcasb+k68Bc7wnAXC/95Zo1Fu9VzkhAaYLTWiEMPbzlgfuws9PHeNjH1NQUNjY30en14AdBJu9NQuATf/wp
THkJpjotc0JbHlZmrOkYYTZDH40wyA0wCwCXmJi5BBEC36/dinQlyxQY2tptu2V+FCcYjSMsr6xhdzBEHMUYR27wjzEejzFK/xyN
jerv2HyObRIYjccIfA/zczPGEzBRBjDUbPcdnJueqMbBgaqYVCkRCGGmKJPozHWgYpE0VSd/ZpKxC8a6S1ieJw33wlYJUZzg5NIU
tm9ewsWLl00VwJUhqQWLFababbzu7rswsmCgG/wuEAtUA8itZjImp4P/KDYbgDdX1hApndF4QaLKzyjTw0UpSJmrge/0/+xoImTq
zHVAH0849SeVHkHw4kqCcVWoal/AMgdAOCP8uAYRbAyeMIwinD56CHcfP4qbN28isOyx3cEQx04ezh7L9zysbWziqS99AfcuTWWS
TayR2W9LYai9qa5dMwzszZ3761VZdigaWxLVurKkikL5CE9Da2TYRAbypZLaSYLdfj9bVdZKG9vu7M3nojUKUWHTLpUelxZAi+LE
+BSwBEuRSVd5UmaPR5NOaN7nBC9VOXQAowwiYzlGJQOL1ByTrYa9JAEt8iTAvodEKwipQFZXSymFdiPEUpPxpSc+j3vO3GVPbaoY
IxEIiVJ4w71n8Kt/9EnTLghhfh/b0x7uzxblxLiUDInT+b5FVaTEtVurGAyGYOFQfAFL9qkSL3K+hMgTlnNNtduWuM+g7HrtYoCu
YlJBiZcntOlOfEbRi5gAuMbro/TmUN3FLqiW6tIbmb9J4yjG6+69G81GiPX1NUz3uhgMhiAh0Wl3wMrc3EEY4NyffA7x9goWT55A
lCj4noCOdUbpTU+clAdgTn/hJO26Tb6i/iJPmISkMuwMzswltNZWgFJZHX3rU2ergk67Da0URioBK525ADHr4mJkweQyr2Q8KSGV
hE4tx7UES4ZkA6hBCGxu76DVCDMV3Vzzb2/yFk00m98ru3NFn2CvdpSEAIEhWcDTEokQGI2jTE9Qa53JbCnNuHNxCp8+/yQ2t7fR
aYZIdE05LwijOMJdRw/jyNwMbm5s2s1Q10G4SC+fLGOfvrH5erD0PFxfWcXWzg6k9PO2QZT0E2pk27isduWe6FwRvtxDGTu3By/G
0YQk4Ag9MgAKXiRRUN5v23ASZGylvajuBTpVgNYavifx4P13oT/oIxoP0Tk0j5XVNXQ6PXieD6UTa5Ch8bnPfhZLXUMtHScKgScR
K85Xfp3+3/cEAt8vWG/TAVYeqfSa3JLfzOutu4zOEf7cRMOYVmilMRqNsby6hm6njTDwjWCpNfPIACtHDsvdDUgTmLbkGaU9U2lI
D+yn1YOEB2A0GiPwfPhefluIMkeDnNMkqxREsUTm/RPBfsYmVNhdyNeQ2UnMozhG4HtWuJVtdWZGngvTbYgr13D+2fN4/YOvRTQY
FkRE01eVKI1es4VX3HESl26vGCoxaxALp1plp2rj0mi0KCea6TzC4D+Xb60ilAJBGDoXtEi75om3PmcBzhmYp6tYmDW6ZK0A4ZVw
sxyjISpXAhr1GfjgLMDnxwOYJOyBal88cQ4Kx74k64OAKI5xaHYaZ04cxdrauu0TPQyGQ0xNTZsyU5vTYmVlFdcuPIuj81OmhCRC
6Pl2l78I/gkieJaWKhyOtkuEqZS0qI64uSwgmY327EgvSRDHpl83Pf4YkQX2+oMBpCCANaIoQhzHiOMESRJDqQSsrbOOBQ7dzySJ
EUcRIgsaZgBibP5uJgsm4cxM9+D7EkqrrO/lCuqcvyxZs4sAruNCuH2zqLl25aAo6xUYKTFhW7IUlD00b2jViVIG8LPvmdYagefh
UMfDM08+Ca1RsunOl8nIVmIPnL4zV1V2iGbsyvVOaF0JziKUg+z7noeVnQGub24j8KVVDCoJsZapxFRafHNW3Ev016wy0azhs8a8
Z1SvK/wAzUX0oCy3t5dUH/BSYAAvxAkoF55gQoH8QADGUYS7Th7BVLeNy5cvot1uWdcegVa7bbb7oOH7DZx/7gIw2sZc9ziiRFus
w0dDKcTsbv/lrr1GFZcqHgupRr6xaZ6we82cObikttrKPfXt3D6OE8QqQZJ6+CUJlNLwhDAON3aElxlZMGdjv/E4wng0RqISeJ6H
RqOBRqOBVrOB0PcB5EmH7UQiTZ7pycKsDaiWBlI27c9Pdq01hsMxfE9ia3sHszNT8IQslslwgqZEeNrY2kazEaIZBJX9fWRG11w4
IVOrKzOuE5CCoYVRYVZKodVoQBIhTpQ51AAkWuP4fA+funYRW9s76LSMijCXpkhkx4enjx7GVLuJSCUQnswcpoicwKMJYK9wTmLK
FTcIgPL8AuZT3JEQNa69xYMuO/lLfb87+lZKod0K8OpjS/itJy8hDPw8XwnHLSiNIXIV4ilvEZ732f9CMAC4v7gEHjna5uReAFBN
TBUpmkprvOLOk9DMGPQHOLo0j93dPhrNJvwggLa6cczAU08+hdmWhOd7GCdGHcaTRgCEx0nWAmjNiFk52n5UAH2YGds7u/A8D1Pd
Tr3jMRf15NnSd83Jb+b7ypnxx0kClZl4mv6fLdMvBeciO87b3NrEzuYGosEuVBwBKjKmGUKCPB9e0ECzO4WpmTnMzExjqtsG4Gco
saugVDjoDRZoJx6psEY+am2EIbROQFIYHAPaaQeKSBsxZ8AYAWg1QkPT3ZOXQoXHI+eONW0AFWzVfd+D1gpKM3Tq/ac05not4PIt
XLt+Ha+8/15Eo6Eh/JSW/+MkweL0NI7Nz+PJa9fQ8mR+f6VJUhQrUnIk1BlUwQAybUp3WkRVpeQKBdhJtuXgd4M+A2vJUN9n2lN4
4Myd+M0vPgsEvqlkiIr+mMx5u1Z76tMLIgI9vwpgr/65RmCi6M1QLknN35VmNIMA9995Ejs7u2CVoNkIsbq+js70XCYgIYXE1s4u
rlx8DqdnOuY0dXrlVtMDg6AsFz2VbyKH9YeShl671bR22VTVNnSwee1w9w1dV5vyPE4MySdOECex6f2TxJTwtqxP3/hYKWxsbmH5
1i3sbqxCj3YhOIEH43mQKf/oGBiPoMc76O+sYef2Vdxq9TB76CiOHD6MXredj4sKZJccXJLSIvN2666c24SUmJ3qmddjORRUI/Im
bN9MZDgOjTDIb+bMiqtaXefIOptxudXgNu2ABTaVgLJj2rQ9UEKAUnm3RoC5BnDxuefwylfcW9k+YgdZb/gBzhw/iicuXTLVWkHw
hOHIBleddznfe2An8M0D6CIQN9GfASWDTncl2aGIZSO/rKGAShIsTHVx76mTkBmbsYQRZC2ZzoxQiLnqEEQvVQVAnCFK5ZM8258v
TwTcXqwyFuQMqU7iBHPTPRxbWsDW1hYCO4uOotgYNVrE3Gv4uHH5KoZbq5g7tIAk0YaOYXfrQ983GoLjGESmz2QGNja3cGRhNlv6
cUHfZhjmDEYqsZYyAKYI9plgT7K+P7HsvsQmAG3BP62VQfrB2Nzexc0b17G1chsY7cAnjYBcIcjSSg4RPAI8MJgj6J0VrAy2sL6y
jKMnT+HkscOFEyXfD0jHktKQoUhAF7YGuUguyQ4tLjgFpTP8rIaz/536KlDag1PZngpFq23hrkAbS3e2RBshJYRU2aamkAJSEbSm
jDl6aKqB565exGgcQTolN5duTc0Kdx89YtsMXSj3UzfpgoVy5qRMDjBaTvwMsCjJ7VGhjqiVxAfXrClz6QDMI1slCkszPRw/soim
72GsFYRwjHIr7sCujWjVJJQKfIEXjQdAtWakNTuz+fiCOKcoOcBfGXkdJzFOHFrEVKeNG9euotEIEcUxQAKNsGGDyJxaly5fQQMJ
mmGAYRTnc38yijTdIATRCGNlS05B8BuNbMbOLqnC2USrLALZ55iSbTgN/sT0+Wnwx3GeBNJ2QGttUX6TLG4ur+Dm1ctQO2vwoQ0g
aG9QKlFoqcLeM2+xlAQPMaKtW7j67AisFe44cSzj8Gezf9Zg7UFKBaElpKM0XJw9l2fRbmxQviqfAXjmdExlwd2qLtUu4NJjVewS
7D0kbOLT7rKWNISgxJmAxEpjvtfCly6tYGNzCwsz04iTpHgT2vcuThROLi2h3WhAKW2qOlctqGA57+5PkHOIFZOa+bpLtXNP+lza
q07y0hzwxcDP9hScJEwme+Pw3CzmZmcx3W7g+s4IAUmnRTalP5fHuUS2khDOxGGCrPyfOgHUaXqSm2HLc/Uy6FHkq6YXgyyr7dSR
JUgiDAYDHJqbwmg8hm/15dNyTmuNK5cuYbrlmZEQ564wwiqyhoEHz29jc3doLo0QaIR+VlZRaXmGJ2SyXJyUsxl1kljAL0my8j+O
I8RxYgE/ZRB46y8/GI5x+coVrN+4Ai8eIHQEKMpqv0Up8Oq8Or3BQgkkow1cPf8UhqMx7j51Es1mA7F90lp7mVOvFDIT7qxnZnHh
8M6rWUOTFhDZWq+w3IQ0UEgIK3nhiMQwFUbi7FYXZNoAJs627jLClsy5G2ZyY9x2ldLotkJ48RqWb9/G0sI8dJzkakmcV26xUpif
6mGu28WtzS0EDikqHUVmukVcrODzs5gKC2t5ZUsO7sUFZ6G68w816+/uyZ97E1phFWIcXZhFx29gcaqLyxs7CD3hWI2lWIDOK5IC
Fmct153k9nyowd7B14HtTJ8mJAhRJx+WlpZcSZNsASYi4NjSApRNCqtr60iSBN2ZefOCtDbc7NEIyzev43i3CWadU01FWgWYJNAJ
AhAJbA1GpsRSOpMIY6AQEFSFUPJphXO6muBOkFiUPz35TfDHGQGILcq/ubOLSxcvYnflBkIdZUoyKRYhUBauzXGJ2qLKsu3AgC8A
Ee3guae+jP5ohAdfeZ8B5lKQUsnc89AhP5WJKFRZkKWCklI6sssFVU3AQgoIrY2FOAEr61tot0K0m03ALmoV9fopvweIQNYRKFVi
Mo8rbTVAtgqwQq+ej67PuHnjBl79qlfmrVnJWkZrjXajgaXpaVxdXUMYBFUXC+Ya3YTSBii7sttUnNyVVJGovKmYtkzOKng5+OE6
HDNDg9EMPBxenIcEcHhuBvq5q3l1xU6LxVShBacsy8rSDfNLAAJSsV4un6S0pxkIlcYfnI22As/DkcU5KNY4euwYNqwt0+zcfBaM
nudhZWUN/a0NTJ9o2140P5nM2M/q0XkSM70OGISd0RjMjChOHCFMZxJQ4sakCHZGH9F5BaASjThWSNJNvTg2J39iEX+tTPBv7+L8
s89gvH4LIencils4NHGRg36CUKgKyuwEhqv1ZhKBBLDgx9i6dQ3X52Zx/MghDKLIuPJ4npFBl3ZuXzDI5ZzAUkoEmYqSk1RTpF4K
AS0FWJqVWCmEpcsZFF+SLE4SjBRn0XbQVm2aNJgEhNB2OpMmlzwpKJ0/qdl2gNXbt0xpX/I8cim2UkocnpuDevqZQi9O2SnpqirZ
srpwb9b4I9a4J5ffGQbZg5kzEZOq0K1jIexOv5TCTKuBhZlpMIBji/OA1nlvX15oEnXrwiIfEBR68BctAWwD1MwrEeZatRN2Aqzy
y7k0G3UWOjqtBpZmpsyp3+mh15suyGSBzc2zuroKjoZoN2aMk4woSn6nNysRmcWZ6S54ExiMIozjGFrprKUo21Jn7roFcpZdtrG7
+WbJx53xKyiVWLBPgezJb4L/JoLUUptq9Pyc4M90CVBW93VL9Py5aQta+kKgowe4cuFZeJ5Et93KOAFU6KfzBEBEGV7RcLT4C6W/
JftkjEop4AlhREK1BmsJ9qTVvwd67VZmmFrQFyKywLQRb9kdDMDM6Laa9nBL0f+c8kzCZWua6z/dDnF1Yw2jcQRPUOH9KxY1hCPz
czWrtmkb5V5XKgS/C1jynhMuh4LLVEwKXOQoMBWnM5TRzCmr+iKVYL7XwfRUFwmAI4tz1oRVwLMaiKmrc15h14z9iF+wIpCHFyAD
RkD9goUzToVz48JdZ+Rc/FMphanONLrtFlSisll7MbtrkBBYWV5BIDQC38MwinIFXSGyfjItKYkIzUaIxVmB5fUtxHb3Pgj8yo68
uxlHaYLKJLrsnzbYlbJgn1Pya1v27w6HuPDcBYzS4HeAJqozE3ISAblVQK3EWu5dR47nvQeG3l3FxWefxh13nUEjCKASBRLalOJU
UQ00CUApJFLkNOR0Vk1OVSXzpKql4euzl1tmw5PmPbSy6cZQhQuEq6LFncvEpMwmz+VpCCeps20Deq0Q8eo2dnd3MTPdAydJ4aDJ
mM1aYXF6KtOMQGrql920nJfLzoIaatajXWCPRD7Tz3ddKPtZd5nLpf+mFRULAWhzH6eHR6ISEGsMB0McvucOtFttjME4cXgJQsXY
3Nqyp7o02gmeBwmZvadcWAwsLem4r+3FSQA9MEdFhLQ8CqQ6UgJXWgEqISWJ0pjpdtAIA2vgSRNdhldX19DxReYNJyx4RKJI/yXK
tec7rSYIwOrmDobjCO1msyAC4oJsRMU9jVSeKVXzUZb1lwe/oeuynaVfvXINu8vXEZLOATEqbhkSwQB0Fl5mZ+RGDpckFw+17ENn
b4JKY4tAMMbbq7jwZIzNQ0fQ61nZb8VILCi50x/g+u1VJEmCVjPE4flZs5Xn++i0W2g1G2gEvgn29KRKDECnpIC2OwhsCU3pDS5S
5R/WYDZWWKJEACJbonY7reyakuUGCCsIIlNMgHLQkkDW6TkAJdvY3tnB3Ox0dWMunadrjZluF6HvGUotCQs9MUAaBOkc3MUTkyGq
2KsoSVgWFiG43gqLcjwgUYwoiqCiMQRrNH2JpU4Ti9NzODo/h+NL8ziyOIdX33sGihlKx7jv7rvwYz/y93Dpxk1cvbWCq8uruLG2
iZXtPnaGQ4w1A1LCCwL46WHGNVZ9z0Oo68BjQC6h/5NAQK4VLmTbIukCaqC0xty0EeIccgRZcBXO2Wtaa2xtbqDd8LITZLc/RKsZ
ohmG+anlnCLpqdtttyCExCiKoLTO9O5pH4OF3KLczPRTIhDbz/TvYMby+jpWb12Dz/GEffx8FHZ9vY/tYYxjsx3MtkNo1zDFqh0r
ZiSpqpDdOEwPF6O5l75e87gBMdRwHasXt7EifYAMp55tooqTBBdvrWOzP8LRuS5Gt1uGKiwkvKCBsNXB9MwM5ufnMDfVQxj6hiOo
yFBrlTn9wV6B8CcEQShbbXB+wrrS5VlVo3OTC2KRTQdE1m6YRK60xuZ2H712ExqM0JPwOcHOznaGI3BNf5lojV6rhWYQYBgnkJ6o
RmZuOrmHqk51tufKf7nORVxaest+1TjC4aaHV9x9CvfdeQJ333Ecxw8tYnFhDp2gBd9+qwIwhEKcGBcrz/dw9g1vwNfYcNIARkiw
sbWNWyuruHjtJp66eAVfunAZT99cQR8e4HmWrEUHVud+AUSgagNQqAKIc525Ctuv3JbZNCwMejvT6xQII7nAY47SxkmCne0tLDSC
DNDxLIEknwSIwshKOC6rnXYjWwlORzy1EwAqMupyHoCr4muSAltt/f5wjOtXrwLDHZBMJw0oWkQBkIJwfWOAz1xaQRQr3N4a4Cvu
OYxW4GVqwJoZsdKIlUaUaMSJ+bu2PPgUnfekgC/J9ObpawYhRAKdpMKh+RTDI+CeQz0kSQdSAFonRkgkZsSjXYy2VrF56xquNduY
WzqME8ePmsTsGVoqS5mX1ekyEVGG3CttnleupkwOtsEFDguhuvVIqYMvAb4n0eu0HAaoQCAZO9vbGctP1FScSmm0whCtRoidcQRJ
hnFHLCvtQhnEft5S+FRc4eby0SsldhTwzPI61kcRnrlxG0szU1icncbS7AwWZqcxO91Dr9tBo9HIXZyEwCgZY2V3F5vbO1jd2MLy
+gZurW1gZXMbK1s7WN7cxup2HxFkLghbkenmFxMELIoXUi0foLgbwC5nqtbqKccOuq1WIb+UMV6yWgGjQR/Npp8BPp12E1J6ORBo
fdrSeTVlX0uNLGSB6FoWWcmIYmawlJW6zEbAI3XX4WyX3zzSxuYmBptr8CmfhdfdL4II28MYUazgCYHtYYRRlKAVeEiUoURHicIo
URjFClGsECXKJgAuJIDAEwg9idA3f/qW9UeOtFXxpDJB6EnKHoscbwFDQY2R7Gzgxu42VpZv49Sdp3Hm1AlIaXpqyvpac/JLJcyn
MIi+ZgHBDCEJqxtbUErh6NI8yrT2FAuiTJnZgo6pHJcQCAIPcZxkbWfDI/R3dlFHBnbHbYHvoxGEYN5yqnS2wDVX5/XEjldAOnXj
A5yeDqmsMHWz5Bzpoc8am+vbeOb2miGIKQUBjUAINAIPM+0WWoGHbzr7Fnznt3w9lGbcuHUL//w//BSur29iY3eA3VGEYaKR2KRC
0oCxRlrdN20Kub+bihTJF30ZiMo9f3lnPqeUVsBadhclbC8ImJFdWp2VnrRmhicERqMxotEQjWk7bkqBlrQMzebVlIlM5gi7Q5RI
gZmKolJOqSQHteWyzpw1r0wDSimN7a1tIB6hbBGIgkOfeS1HZ1tY3h5gexjhjoUeOg0f41ghUhrjWGEQJRjGCUaRwjg2q8ZKa4MG
c54AfE8i9MyN1AwYTV8ikGxHaZTfolQULpw0Hs425gkQrBBtruLiswph4OOOI4dAkqGc4FeJQCJMIlNCQnoWvLXAYrMRZO8vWSOO
HG+z1Zcw3JaMzm2TtytlmibnhifQ3911DEu5QrxJE0Cv1YJK54jMJT8A5yQTB6iWqcxt4b0l8pwpgWRAeBINKR3FH7Z6jgqrowib
KxtoffKzeO/X/xU0/Saefu4SfucLT6IzNQUBgmy20Ml0HMlqm+aaBRWDCD6ApssLEgQp6aGb20VU+RXluX/Zu9VtDzj/3mzDrZzf
OZd+0iqBJ1sFjf7UFzB1CRIls01X1EOQ9SB0y8GS1r1mrnpr1DFz7EuIlcJw0Aexqmjwpjdqqj+oGZhuBnjL3UsYxQrdRgBmYGQD
fxAlGIxjDKPEBr/lHzjVRnpSykQh8iTiVHlYe9C+h8CzUxBHcVlni0N5qBfLRV15vyUB4+11PP3UU2iFIQ4tzpoFJyIooZAIAakU
lJZmTVdraJZZi9dttwzQmV1PmwSc0yG9LqmHQNotCVGsxAiAL42ACNeIsaLWtjZl3eWCJOzIn1dclQqrz1Q0vJlkfKtrjG+pQPPP
F4M0OweJzirCXruJrcEIW9u76M41cWN1DWEYouH5UFpZ7MfxlLStM5dcjcpr7pNVSl5gAsheF6HGScZeP1Gk0ZLDkCr0JM4aqxAC
U92WIelMoFQSAdF4DGgFX8pM+RcWPBqOxiAh0Ou2swDJWgKX819aniiuWpCDY3DJg684qyfHT0IrDRVHtdekDJsQGJoJDd9D0/cQ
JRqjJMEwUtgdxeiPYwxs8CeJQqJ1ZoFW3rYVKjcSUdqAhsZhSCKQxu0IDgagHU4FOzTtWpQbOY4x2FjF5avXMDvdRRj4FgwVFgsx
1GcDhhb1DbU2Czh5MBfJTtrBAFLLNXM/C7jWWimJJ/Ak4nhkyFYT2kqDFxB67bYxiCnr2LlEnDKST7X7QPtsu4oc4C5pXqTlOKUu
UQXBUjizfYG1nV2sb27h5NwCrt1ehUrl5lBSL0ZJemwPi/OqY9CLAQKWJIkyDkBhGZCdLJtmLZ1fGC7LOxNC3wdzEVx0v48EYTge
g1WMwJem/9aGRcbaEIlajcDSUIUzVstdXMn16HNn45wHt04ZY86M3uXAZ2Aj5Rt8puUQE24Srp0wKGVK+igxJ//uMMbuKA3+JDv5
C/4J5e03YsdKLLUaMxJZgWfHozW+g7kDcUnKjov03SwxsMLqym1sbh/HofmZjKfBNuhTXcNMySZl3xFVnMfJEoNgEy3Zqu3myhpY
a0x32hBWIJayT1OdNHyJaDRConT18HFm8ARC4PnZum0VsXJcTyo6IVRluxb8RNxAL1YI5E4K2O2/RW5dlt5Y2roIs4Ykgd3BELfX
NsCngRur6yDp2eIi1Sdw3izhSJKnA2H7dXbrH3pRl4G2ATQL8/GMD0BlIlB+wnJpBMMldRouLEqkYzeqW6y0wWxOns1RghgCMkog
PYYfAf5IozGIcedhH0IEjkITFRY+hGWEcQ21UmSa8UabTrrCnHblmFIjC2G95KWE7wcYokzJLu2gO62OZhOow1ihP0qy039kT35V
tv4q3e4aRsRGMyN2Sn2lNeJEwvdENk7Nyn7OG6xskpDN33PtwHK2EUQY93exsbmJpblpVxQxG5Gyu+npvH+CkIGwVRHSPNjmpnpY
297FpbXdzCglToyYSpwozFFS49pU3wqYAltP3GRjZ5XZvdW4rOBNB3XhyUkkxOXKWxQ2DDOBEEG52AgJRAq4sbqGESvc2thyHJFq
gp9ExlnI5NrFpBKFXjwiEMy+2QQHU6661DrSR1QxPuBqP031GwSFxG0fL2ICe6FhipGAZgmlBVRkTiWR0Wwtzx5UEX+lUreYKsNQ
yhC3Pu/pmrEsqQynvIDA99DudrF92wNDQXCNGYQzJTECKBrjRGFoe/5BlGAcKcSZZBgqTj/la6LThKMtQmxFNOJEQ0ozEiwArk6L
mrIlAztK9KWwyaD+3ddJgv5gCK0ZUpIjeFG0fHfBEfd+oBqFILagIBiY6rSwtjvARkQAhUiEhPY0tGBEpDBMhrXLLWV5MJ7ktVXY
RC1sf0yWsN8v+AvJwu6PpJecyIpfcwbcwR4q2gqAutdCE+HG6jo2d7axttuHlEbYJltIElRyMnZWN0WdL6B4CVoA99ploxUqJgEL
+kzarstuYK6RT+DiqcA1gFs6ypttAFE8tKevhyAQaIQC7WYTfuBnaLlr/ZVOAZiKUFFBGIaMR50RrRDQgjMqrCclPCGhpDS0WCWh
hXkj5+bmcPtaCzzcAlv2WaE6yjXSjImIZkSJQf1H1iIsDf6q+xDXMs3c+9rwEgiKgURx1r7U7V64CSCWwo4TzSiRBUGW9vpTxdo4
iqxzj+tfU1OluCh+QYE5ZQVWAypONHqNEEdbEUbRGGMVIVIx4iSBrxiddogNUP15XjdpZq5uAlb+cx+iDJVHe5MekUvIm3AIUaLg
TJovJIs8YQoCeRK31jexvLqG3XEM6QWF0R4giuuj5f4/m3DZZMEv0S5AGVjMT36qnvalNUp21iDZoUznJ0R1rluf0AmtRohGoCGF
hB8Yx59Go4FmI7QCGLkmQmHrzx1BlclMnF5j8+awAIS2p7+2PvdKQikJ5dkEoDUUgJmpHnqzi9i6vmOLPs7KXC5xJ7TVvU8cok9i
gTwwV4uhMp9D18/AU+KPopKyT7lMzkBSIJECSkv7vhHIM6cU0YSVGColF2dpiUqOQLkDk6O9SXkV5GrFMRiN0MPCdAuDocRoJDDy
BOJYIlEaDd+rD7p6mkl9q8D52LgeQygXsFzvuDtpW4iolDVMwuMC1Ex29pm/kRqA9Hwsb+7g4vWbGCtGGIocEytrDxYSQI0VU31a
fnFAQKKKUGwtMagiWcwuy654iimlsb3bN84+To50H0gpjXarBeEFiOIYvifN1MD20yrV63Oow9mmnZXcMloGefALcGHzD4IKkmrC
qvAwG0VhLSW07+VMQE9nwFqzEeLYiePY3VgDDzbsa0Fh70Fna6nI14u1S/O15eFeI1wuBz9XJzGcL8HWZhAiaKsXrJ2kLEkZDoEE
hGtEAQ0iiSAMzJKNIwOXbRCSQ7pyMetMace4ByWJdkBUBzC0j5loS39OP+37SwAGUYzGdMd4I8RxYSfFvUmV0tjuDzLD0EozTwSe
KGZVFI0pfH2SBV5ZJixtd5zfk4GC7DrOUJYvpPSw3h/g3IXLYCkMoKfK5iMW6GMqEr2o1BowvzTegFxbRdVkHHfrj1xRFMo03N03
RLO2vm71gE6GpQrKSh1BRbNKKhtXMjsju7QiEDkxyGHLCYc0BIdHkFKJMz87T8L3PAS+B99+evZPIQUOzc/h6J13IfGbjuFLThEz
dN06CS4uSi1wPibNpKTST2j7yQWXe6qjKJQ853L1cKtvyBpKmUokpR4nyowdXRo3W5g88H14UmA4NDNro8ZUvF6pH0DB4MTByW6s
rGG3P8ySfV6N5XO4NDGIwuOYyimdbNQeNvaW06wxjqMCMYX3MLGtL+yptGqL52eGUzAMpRy5t6Vp7jBsviY940T8xLMXIHy/5D5E
KVOqQLFGYTfhz0IWPCWSEEpEXlRGggUloBqDw5T0Yzl6GEVR3vNwHciq0QhCeH6IcZJYPr+uJyo6QV5W22GLMZhE5CiplA4Jkd6G
9sTzpQXZmMHat1RaLms74M6TxxGNx7h18RmEepwx8pRmrO6MEPoS3Ybv8OhTFD59viUd+VLNSVVYpP6G5rr/KGnoaEALYyyqNEGx
yGzOyg56Qko0w0ZmlOr7dovPJnBRSZwO+k+5yer8zBQCu06csgOZS8nSHhbDcYRRFBkVYgDDSKHRamfVXJVvbd4RxRpRkmTCIRmx
h+rWWepqASpI3B/EJm1StZCS2My95G4PFgNWCoFBovDU7XV4Xlg8YEtz/2yc7e6X8+Q9hRddEsw9aisMwBTZ3QN7Ka5Vmlt5c6df
AMsqai9aIwh8+I0mong3c/hxd7AZRZ2BSu+SXk9GCWBxS76CzmrmfacAaEh47Li61pzATSLcc/dpAMDy5fPwkyE8QTh/exvP3NxE
M/Dwujvm0WsGhs6bIvDSLNNoJkOoyXbMee9etQb82hP3KtNV2YxdUw4Bu/qNzk0cNJrodg0DMwx8eIGfGZJqzQU/xiID08EJmNFp
NbJpRZ3nAuz2ZV756Oy9iBLGbLNVu4+SL/mYpbHd4RBEjkoOcUmvgqubfMiFNJkmVL5c1OHbizLsgjCugxKXx8P28ZSQSEjmK+mi
xEkQTvIQVSXg5+sG9AIwgLzvoJIVmMuBZ9Qgpw6pnrl6v27t9jPRTq4BejQYvh+g2e5gMNwwQF9Faah4EsBh67lPgrN2SlRm7WRB
u3Smm/EdrBAjOQFGpQqRiBAjRrvVxH333I0wDHH94rPg4TY2dkeIYmMYujOKMNMO4UtC6Ek0fA+x4ozOnGsB7J/Gua7n472Wuev2
t2vcgJwyQwPodHvodTr58o7t+z1Pohla4NW2WIJEJRHk7F9djA3KBV/YtYlnRjP04XkiU2QeKka726s8X9dSW0qJ/miEwWhkJMtc
HZCJxoa051jwQBbLNV/OxoNZpVhaH6zUdSVSX0UdiuypX2RXFYhKdc6iL1YC0OXRdplGTXuMUrhaqrk+cutb22b+XRP86T3peRLd
qSn0Ny/kjDLXJ84SJ7lgpEQlQ9OcI58kiZGgSuW5uUhqYkEQ2p7z0v4yz8s1fgqCkjlTMI5jtJqEe+46hXa7hSvPPYtj/RiR0uiE
PpZ6TYA1fCnQ8KWdAOjs5IugoVUeDAUxSBwUJNz/UCALzKVFpaAiOzCr+IREb6qHVmiYlqM4QtNarcmCEWvq/Wfo0VJ4NS0MOfsd
nJmjwtKdUyA3JUsZOrERjYm0QLfXyyYWdVujQhD6wxGG4ygDYicK15bW2ms7gQp/pQYInLADU5DocpFzzg1IC5L5EzgHRJxv+RFN
nlqU0z296KKgXCqHuLDD7+qt1WIARfGADMiSQmJ1cxvjOLaUWq6A12nPODU9iytPJ4U1zFQrK2OiahScVYpae3lGXVvdwnSvi2Yj
hOJcoYatnjXZJJDdcLKILbiqtoXdAwKS2NzqJ48eRrvVRNhqY6Z7GQ2OzUSBGZ4AQimgAq9YicTKsPuUtvx9Othgh5/fP8bK6As0
/VQ6vOaAY4YXhJiZnoZn5b+ENBr+qRR7lgRShV9p3JuSJMGRxbns/U41+ckt+TkXidEOB4KR05al9f6LyUOn24VWun4CAkCSxObu
LobRGEEQVoO5IOFXsvwiKuoF7LcYQNh/dbDMFkxtlNh1FuZKVVJpYYVAyWLrgCzFlwQDqBMBpSLprS5TVsotu7whBTZ2dzEYjdAM
A2g9oddlxtz8PM5F5oQUgrITPyshna05d/mHstMnz7SHFmYzUECkoGZ6gwh3gpluhkkIslLkMEHMSWI1BvOJQspAjGMAnGBhZhrN
++/Hs0GI1avPgdQoM9vwJNC01JvCNneWEHIdgBcr+AnAKGGMY5UlgkbgGUCyZqLQ6nQxNz2V7eq3Qx+e79lgzx19Mnk26x84HOZU
YnfhUJf88XTmkUfZlIIdMRMhBHaHY1DQRK/bMVJsdXr8lgG6tr2NOFEIQ7ILR3t4mVONlNZ+f3du8np8oO6+T0d4roBhDqUXXMsq
wwia6MnOkxiMLxUImK8BV0VAJ40hc30AC3CV7MOlFNja6WNjewedQ4tIVFxD5CAolWBhYQ4xeRhHidGq09ppXYsjMsPFlHYxRWSB
m1JY05l2cZXaFqmcO8CmAJbMqhzT68ax8StoNBpW1IKqfS+AJAa6rSbuPXMXvqwVNq6cR6iNqKUku3drlSudLX5wVFzkeX7BzxO/
QcO46FCmyWiWkjwRmErAfXeExOz8vDUlhYP0C8d4RGQah2nf3WqGRuRFANs7ZmQ43e1AaeXO67LgjxOFta0deEIUlptgEfLtQYRG
ZwHNZhPKmsSi6jYPIQRur69DWaWmMleFaoK/MBCgmqA7QLm9r/gGlSfuLn/A9TmocNVLeEJdLUjVKRueHyVAPG8lYC4LKu6BVruE
iAInHtkbPBiNcHN1HV4qO1WT2VSiMDc7AxG2sTMcGZUa5LNyV7qLC7vXrgIN8mAtAXipSq3Z8MtHr+m+erqMZGjBhHargbnpKQS+
hzDwEVpGYhCYTz/wzadvNPpbjRCn7ziFcGoBic6PDElAIAgNT6IVemgHEk3fQyBFzmqcRMvmvb5YPyysmxwFnrRCIk5gMMMLG1hc
mEcY+JlMuJCp3bqXSbJ5VhHYrYLS7cBGEKIRBpnSM6GG3+AYr+ZVHGc353p/jN7cAnzfy4HEGp0KzRrXVlfNBKDmNGSi6mleNqsj
qj/BCTV04Or9796/TDX3PNVs6rnZKZWxqwMfCfsGP15Ke3Auo/917UBpMYKYClbWGaNJp6Qe4wt/bXm1eCo7m2xk7cO73Q46M3NY
31nG0mwXUcxO2ZgLdWrtkGBKa+FKK8MjcNyCXUAx3QlIF7ZyjQPKTDkAghTsyFjni58u4m4wCbv9FzNmeh0cOnYMl7fXIPXYIXgR
fAkwJJRvNAEjpe1+QG4zd/C6jvfweCU0Aw+jWIEBdEMfvYYH6c7u7RSiNzOHpfm5PEHKfC9CaVNtedIrKTLnc3+wGRumBhlUICVx
xooURJhqt9AfjoxOoTPO1czYGCY4uXQotwan6uUgAsZxjFvr6/A84Yzb9wq2qoFh7ak58dTfixq8TyNe0H6v46NQZX7OJckT1Chv
HXTV4QUmAKq2A+5CUCbqgJIRKE2gr1KmZnr51u3a4He5AM1GA0tHjmHlySu4390fsKd/JtaZgkrOGqyAUQ7a3N7BVKcDP/ByEkr5
RrHZTZDzmkXubccWnCPWIAiIwM8suOCMpbLnwhqsTcAtzM/hRqsLtTOCzIQxzEnnpVp/vkAQE8ZSIE60JTLpGo7DXuFe0wja9yoQ
hIYfwJcCndBDWKo2mBkybOHEieOYsuKcwpb8UghIT0Jb81VP5l4Mghz2ZXYpHRXotLS3uEbquZCarmhXYwBG3GMcxegrD0uHDxsx
kJogZdaQUmK7P8DK1iY8T+aHFZfnwVV+P0+odQsIf50Zx6Rui8qHJU8I1hRTE6XXxLVThsoyzgEES1+0FqBIkJk0G5jUd3B5vlR4
np4vcfH6LQzHY7swwpWxVzoRO378JDaHCklizEKYc9RY6VQey0opaV0ohaUQmOn1jI+epgKjkRz2ZcpyS5MA2f37TI4rRf+lCYY4
TkDMCAMfQeAh9H0Evo/A8+F7Hnwp4UkDnHVbLbR600g0WZQ/v2ZpEvClsKu6wpqc7M9ILX5SkQqdSm+JVAfAPL7RETQtjbRtT+rY
M3foCE4ePWxVl22/L41JhSckep02Os1G1hIYzQRR3V2pGuZkCTJzXbKVW/pnigFIKbDZH4MbXczPzSFJVIVfmt6BnpS4tb6Ojd1d
eNIrTpJE+cadwACsoOs1+/VUN/pznIBowvFL+3ELnkflgT0AR3r+bCDxvL67hqmXZ7icr89OpkxBukrHmlpc+T6uLa9idWO7ggO4
aH6SJDh+/CjGooGdwQielBnel54eJglwngSyCDMrmr4njZKyyGfg7LyofGe+uK2YntLpkpG0lGFPCCRKZavKvvScnQGZ7Qx4ngHM
wjDA7NwcWAbWZCMfYaZTAE8I+FLCl+ZPo/Yr6vGAkvpR0dfPceAVwkqJG8GQ0JcIPYnAE/BFLsbJAMLeDM7cddpYfsGM9qSU8Dzz
854nIT2T/Dy7K5HhJC5PgnniAq122jWdJW5bLSHdnxC4vdVHb/4wOt2OcTyqCX6tGZ7wcPHmTYzjGMI18BQTDmpRltMqLgByje3Y
3jsBe1hzTWoVam30ins0BQUioJKAKjduWcnoxUsAPGEhyLEk5hp3cLfcz1YcRQEc8aTE5s4uLly/gSCTBysuB6U0z4WFOXTnl3B7
YyebqbO18FI6VdA1qjrpbDkTHHV60XQRp7hMVYSO810CzpeHnP0CI77JmO110W42IKwxqfk00s3p6S+lcez1pMDszAy8Zit3/HFb
FUpbAULomX39XLBD5IrHjiNyqu7j28f3hbDJQyCwiST0JEIp0fANyNj0JRq+qQSEszEpGx3cfeYeHDu0kPX9aaVjgD9pE500f5ey
tM9QJxBbLNeLga+yKkA5+E3aitzcinDk5Cl4QjqegFzQlkgHwk9fu2qIXUT1p+F+KP9es33abyRItcSiWh0Bool044Oc+pOXkl4Y
Evg8KgCeCAq6pV1ugYvqBKCiIGRuvlgpfPm5S5CCivi18xelFZqNACdO3YXr64OsrUt16rTW1sNP2ROFs7lyoQQURTPO8kZhvvPu
FtXV9YLUl5DsCCo1yvCc7cH09Pe8lEBDmO520JmaRcJUmIUjc/2BpQlLNALzGXj2BBZ5kAfSlPDGH8BD6BtqcSPwMuHRpi/RCjw0
AzNlaAUeWoHMy387+mNmeO0uztx3P+49fdJUSlJAeiboffuaPFvRSN9OAQTZCYBDXy9xVMkRz2dO131TQdP8TzdhSykwGEfYVh6O
nzwJpZR9T7hisiulxPZggOdu3EDge06ioALjtLw6yxPLejjqwDzZbHfiyT5BZRUH5yRUpmx1CQg168g1fJ0X1RyUC6IKrtZ+zdIQ
8vFLSsMk7S7U5KWO53k4d+kyxnHiCIRU3xStNO4+cwbn/vgjGI4Ns86c9nD8+7Q18vSgtIR0AgyO0ALVSJvB0dQv7oVTRVjDdZUV
2Z6yALOE0ioLnMSTSBJzWmplktihI0ewcfsGdLSbKccqrXFxdQdru2Mcm2mj0/AMHdbiF5lDkOMnKK1gqaSi07DLb3B1AKWwm4jZ
pIMBz0dvdh5n7rkHdx4/Ysd+AtKO+sz6s59/Si+rAKQQIAgnYXLh1CQHAMiWjrKe3yTrxCZtQ4E2IKsvJa4ub8GfWsTS4iKSJC6O
LzknFjV8H5eXl3F7YwN+ZpMlcoynQqjJN0P3PfX5AJb3E0C74tep/utlHcmakn9vQI8mgoAMIHoxEsA2gHYNBkATZMHTN5swSZqG
SrIWBkC7cP02bq6tY3Fm2gBrVKTBCiLEUYwTx49CduZwa30bJw/NYjiOoJmyXjI18dTaVAIsLbJMDJKOZv4EiXMXuXJNT6lmyblQ
SpFAomMADF9KKE8hURJ+YlSEVOJBSGMmevzwEpZvHcPKpWfgw6zUru+O8eytbcTKuAE9cHwWrUBCEOBLQqyEFQxFQf5cWj2/igCn
21KSQ4tOeRGej/bUNI4cPY5TJ45jYXYqG+WZnt/LTv0sCUiJwJe2LUnt2NPqyQqFMAquuey0aVprs4JsJc0TpZCk7xNrJInK1IMu
r/Vx6N4H0WyGGA4HWVAXBECZ4XsenrpyGcPxGL0gKC6Kl05Iqi6Jlk5VUeBCTK599+LxP48VvRc4YnR3CSrKWy82D6AHWK3y8i5z
nSx4dUmI3JvBUVFNpVnZvonr2zv40vlLePdb34goimuvW6IUet0OTp25D5fOfRx3HpnLOG7MwmrVm/I/iRV8z2jXS7brnlqCBedV
hkMDo7JKbCk9FOzOqCRhboNxfXMLnu+h12ohsWCe8jx4SQLPSomxUmg3G7j7rtPY2drEcP0mQnIWhLRGK/AQSIIWxhI60NrYh3HR
BIoKGghV+d1MjIUIQkp4foCg2UK3N4XZ2RkcXlrE/Mw0AqtESymzT3rwPQHPnvqBb4DN0M9PfyHNMxCW2lxZJHKgeAZnegNpkk6U
meYoZQDbKElwY2UNs1NdSCGwOhJ4571noJWaaHdLREhUgi+cP29k4rNlGGMcQ458FrktANUIidLBWumKAMee+ABVR3+TnLMm6QvU
ofyT1pFfGlXgShQUNQDK1GBn0YELZTcyklCRh5uf9H/y5NN491vfUFUa5lxAirXGq179KvziZz6O3eHYtAGKocgE/ngcIVEJPG8K
iVLwlIKSElIT4InioodDs3S1AqiM+jq2VrVyaRbgmp+dzspYT0ooT8NTtndWCloZWbGYGUvzs7jvFa/Ak18Ghuu30QkFXn1sBjvj
GIvdprHd0mz84ARBC3uKspUu9wL4YQNBo4EgCBEEAaRnfGelNKd2GtS+7yMMQrRbTXTaLXRaTYTWDjx3+hUW8RdZBRD4HvrDMQLP
MB59OxGQUkCQSQKCXOTfvWldpp/t/wvBr7KWTSsFAqHXaaPXauDS8haC2cM4evQo4jiumHimWJIvJVY2NvHs9esIA2McC+mKQlJ5
DRBVf8BqO1BLrjnQJt5eCP9epz7vXfLTHkP+umqB6CXCAByd80my4Fy+ggTrE+euhZKjmmp7uTDA5585j5WNTbRbTSilK69NCEIU
jXHq5HG054/iyu1N3HtyEQMVZQ6+cZJADRlTHTM6UtK2BYJAWpubPmtZKMvWjHTNuGgcUR6x7PVeBr5nrL0TZebmSlsswIPylZUT
N4KiYMYdx46g2Wjg2fPnsXrzOjoYoNf0obVGopLca4GMeqznh2i0OuhNz2B6ZhrtVhu9bheN0DeGkTagMy+DzATEQeqdxSgSgIAA
yXy7T6ZIvyfh+z48z0erEZh2QMjszxR7oPLkh0tiLZYUpVzUXykkSa6GrLV5r6c6Lfi+h/PLuzj1xq9EMwwwGAytClSJS6A0wrCB
L168iLXtbXQ7Hdtri5KZrQP0EQoYFhwVq2L1Qvv235OUgif+vSRMUsvj57rx+oR1ZJpULdDzEgY9EAbQKqlU1QU9lV4T1/gxFrS7
uChgGfo+bq1t4InzF/CO178W2/1BhR4MmFOk1WrhFQ+8Fl/6/V/BPccXsoojUQpB4KMbBMZeKwWYtITSnHvZE0CaDB+gsGiRtyYV
nzWqKscVKyNLb4YxFWFBVtRCWBVhH1ppsOIClfrw4hymem3cXjmOldVVbG9uIo7GtvRlSC9Aq91Gu9NGrzeF6akeuq0WfE9iNI7Q
bITwPVlowajk3Fw8mCjDECgV8xApop+P99JxZphOMmzwu5bstTr96dXUOQM8jlU2pk2UQpxKoSfp+2Pag8CTWN0aYAstPHTf/UiS
pF4A1AEBP/3UUwV9vMLcJs0HVKZLHYwyO2n0XdtrE00ewO/X6+OARCE+4MiS/yxkwdNd+VI/XJ4I5ABx7iaU0Z+FNVHgfPz3B599
Ag89+Npa8CXdjIrjGK95zQP41Mc+gtsbO1ic7mAUx9BMWYkZJwn82EPsmTbAkxJaCijW8FiCSYOc3V8qSNVwlT3G1clBkY9upgHa
BodkARYC8P1M6Ya1zg0zKXUYVug0m2gfP4oTRw5hHEXGFdjuvvueROibxSJZZCgh8P2SFToV5NDLXoiuSAoVNA1yAVRPpHP/dJwp
IYUZQ0ohnKWfcvxwgZ6dlv+D0Qi7/SFC38tK/zib/yvb1uhsMenZGxtYPPVqLC0sYDweFRV2nYmC7/u4ubaGL126iEYYWmNXKs9z
a3btKXPcqj1F9xrvTYwLmryiW2crViEQ1dGEae8qYsI68kskCVYVN0HFdxVVXQAqW0alGmdWyCMVTrRtQjMM8dmnz+PG6hrmpnpm
dbXELCIiRHGMhflZnL7/1Tj31CdwZK4HRKYPV8q4CccqQZwk8GKJREpIqTL9Os0MaQj+Tq3IRYCFqIAfM3iPUQhllZywdxdb2ayd
/sAIXAaBXVPOGyBJAolKoBMFZQU2A9+rTidcfz1H0ZhsAFfckAnZngYRajwBXeagKDAG0+D3bK/vpa5I7u8tBT+X6v/0hFRaYXN7
F43AB8goMcVJmqAdvgYATwrsDiNc2WE89O7XWSv2qvgfA1DMaAcBPvfss1jb2cFUt2s8d10esijD/sJRyylyASpyXGUzkNq9gFRc
dgIPniYuCewjPVZeAthvJEhF3cMXPwFsA2gUy32mAq5SiwNQ8S+5NoCzK0mcqfCktOCVzU384Re+hG/7mrdjHO9CVpYlTCBorfHG
N70JP/35T2N9e4BOK0QUJ9CwQFOcIJIxvETAiy3AlcpXgcDSNIaiNCfmssMM5ahFYaxZZ3eWWyLbHlxiPI4xjiJ0W60iD8HuE4hE
QkuVUWGLzrZ2wuDIjqUrza72XsEWHXmQu/enyxFI/RLSwM//zG3QpMUR0n8nB0Mgu6VZdhuGFedgTrX+gJleB0mibGWTmPI/TjIs
gC0BKPQ9PHn1FtqH78SpO04alSiiSvBnnoVRjD944gkz++dctxIiFdlI6x/h4ABUaIXcstnty/kg4729BDombdHShKWfCYKjk9qO
AomJ93EtenFlwalg8kGECWPBtMcXRkyztP3IVYngbHbsez5+95OfwTe87c2Om0z14o/HBgw8ef8D+MKlz+GhV92BKE5ytFmkScBS
c5M4u8nzU1QYs00n+1NF15DzG6dgR0OZ7Xd5JCCspJhmxtL8TLbtlpXjaZsgJaRMbB+sc3HQUsWTexvkZXtKC04ZhnWnfPE+LUqa
uf4HZkNaODTjdEPQ6CPAKh1lI0iqo3sX3Xe04szuLG3J4thUZkmSv+b09B+OYzy9GuErvvmt8KRZskqVn9zfpZnRCkN86eJFPH31
iin/y+o/RJnRa66kW3Tx4VJlW5nnTRzvUf3XJ57SdLAKGwdV+aX9qcH0UrQANX/n0gKUa/iAsv0W1duDG7MEbfXhGM1GA09euoLP
PvUs3vyq+7HroMDlKQNrja9829vwM+c+j/WdATrNEFGiLIquIG3PGUWxLXGNeIUQxpQxDRyN/GRDBTijyagIV5VhCsUlwfbQpi0R
KSvPcv5jYUaUhg6r8gUh99ywp3AaWGmACsvVH43GkFKi1Qide58qpS05s/q8UihPCXJGoTs1cN9NKoBd+emf3gs7/SF2+gPMTHWg
s8C3wZ+YtixJ6dqpu1IQ4HPP3ULr8GncfeYujKPIJJ4ae3QwQwqB3/vsZxGpBCE1zYEk8t6fkJtxkJgQYAKTzUImyn7t4S5Ceytj
1678Tqo89lhHntyOoM784EVyB+aoOgas/VVUOxXg6hggP11L/mYEIGHGf/vDT+LNr7q/Tvk7C8zReIw7Th7HHfe/Bp+/+Fk89OpT
iJLElKBKZ4QiKQVkLHMNOypWAeSOW1KHGldz4KBrlqXKUYCgyejVeUKAvNxRJx25uSux7FicpY8lBGGnP0CzYdR1CMXT35h2CjQa
YSZlTuXeFgXs0NnjcvYhHKCQqCiO6W5uFILSnfuxBkhgNI6wvdtHt21GuUliAj9KYsRxgiRODF07O/0l+qMYT62Os9N/nOSz//JJ
G/g+riwv41NPPYlm2DC2ayQzohmVgUCUXXVdohfViofudwgeZLy3J6D4vE/9g2wkuot39OJiAExhdQJAJUYVU8UopFwdsy7O2TO3
Duek0hroNJv45JeexDOXr+H0sSMYRpGrSFBAX1kpvP2hh/Cfnvwibm9sY67XxihKIIgxHI2NSKTvIy71tuSoAgECQheRYSopGRej
m+o1D1A1xJAwTsMpG211fRNSSkx124hjBe1ZhR1nF74wXbAriIHVGXDNNwUIzUZYOJ3L14nIkKfyNqFcSbomn+UWqKzuzNnbtr3T
x3A0xuLsdHbWaaXQ67bQaoRQWiG2QR/F5s84iU2ys8o/YKARePjEU9fRO3E/7rnnbkTjUW3wp0YkoR/g9z//OWzs7ubgnzv1SGW1
yquJhW3Asigg7SEXTnv02Qcrz7l0TSsTgf0ER2vG0PWA4vN3BxbPiwRU+e+i5CLzBGpjKgIiqNiDAcVNLZudpRTojyP80kc/Ds/z
LDBWoxNAhPE4wvGjR/DKN34FPvXsrSw4tNbZGCuKYnsTxsaOO0kM+q6Umc1nUlTa4Zq7wVjyKeeSmgdKX7OAZ8o5yE98gWazYWf3
HoLAQxD4aAQBwtCc8I0wRNgIETYCNBoBwiDA7FTPsvesBqHvI0x1B9I1YLu5J6UzxrPiGDeWV7HTHyDwvKwKylB/4WABle1IqrHd
NtfEkwKh7+cjP7vlxzbA054/stc8ihMkSmNjawc7/YHlfkisbQ/+/+29d7hdZ30m+v6+VXY5VV1yU8FYxhausmjBJYFQTGASIjAp
kDZp9wkJySSTufPMFc4MM4SEEMgMhoRcwEkwhhuSQGKCA7YlG/du66hYvXfptF1W+X73j9W+b61v7XLOkS0/0dazn3N09tn7rL32
+vX3977YMQG88cabMlISmHgnoqWxo6dP4QdPPYVatRrrVag6eoqhUNGQVZktE+Gtyfi7keQWoi4ZFn56Wd2lDlGfSuyRzByFRGeJ
ECQ1elKveS44IJMOTVFMS23GKMKHFO0eDNZquO/JZ7Bt737UKk6aGhf4EyhCB95081vRrC/CSweOox7/fsI6k9ShiSNII1K6iZY4
AaQiHbojSHhFMvLNZCdfdwac8hi22m202m1tjEkgLBgdxsjQQKSuo6zaRnh7J17tjZiFKo6Dihvh8t14xdhRgTqWSAk7hJLhWCTS
8Z4dk5K6jq1hBoTCeJTh5yi3zsq5qziZw0sM1KqYNzwQqR/LbNknCGRW9wexw43vQRDCCyJHQLFTfHzHMSx//Ruw/OKL4Hme0eiY
o5FiveLi3iefwNHTp+EmQpqx4VNKqEkaXb2+q2wCApGZbZfIXGcXuvI9jPcMRmzGCeQyj06CMGR68f4JQvtnBKI8z78ZGcUogjFS
glB1TVP7wDO1Hsu2MNVs4e/v24RKTBRSlgL5QYB5I8O45cffhaf2nkGz7cGxrBSCGtWhsfF7XhqVfD9uSCkbaSl3HYqGzek4k3D8
5BkcP3VGP/zsVzOxENZxKUl2YCnc+nYSxS2RwXAtK3UQtmWnBq+q8qTNwGTFF4k4Z3bN25bABYsXYmRwIOLa1ww/q/c196q8ZyiC
HapTkGG2wy85I/gIwtjQ/QDtOP33gqjzHwQBRgYHMFivoeY62HHoFE47C/Ajb30rAt8vG0BFtb9t49iZM7j3iSdQq9U0Bp9CdE9I
Z+JpSV5aiwuNa+iruwTzdU0wb7ZSbq3cMN7rLpZpWFXsJfPoe/A3S3nwwh60ciILtN5k1lJLF4W0lEzXWZfMGKzXcd+Tz2Dzrj2o
JWgvLRvnFPvebLZw/bXX4MIrrsej2w6g6tpp+RHKMOpCx6mo185KgiQypc24nMiIRj6vEBS2vCjCFwwmFrlMNuiY2cjdJ2KDtSiH
wxcR+EY1dkuo6kNRZ1vkM9+cGrJKAZ4YKhWmFxmyTtNiK6i0FWf9QEbwkaxiJwCfNNNqJ47Wj7f+olGnYwtMtzw8uX8Sb/rRd2Bk
eBB+EBRn6/HflCxRq1Rwz6OP4tiZcbi2k1J7kVBm/FoDMDfyMxhrPqwzlQiQl5KG9LKub8hojA6DNGCRscNPyq5CH5DmOeoBFBFK
pqUDE4iC1RpL9cSccwJC6QXEfHSNdht/893vw7IsTUSU80KRcWr67ve8B0fCQew4eAIDVTfjCwyjqJRenHEm4Pt+tEAUj6YSymuW
CnQ3F95lyLhw8UJcuHiRzkCsJA2JTkE+k9ClyxUJ+OSugnpUsRHlFAmUbK8yKzsWKieiepKUM6hu7+VTflUNuavxR/DepMxq+z7a
St8lDMK4PxC9B9e28ci2w1hy+VqsWXMlmq22NupVjZ8T0o+jR3HPY49ioFaDTGS20uAhsrFfSrkltMivNq0LPSuiEudTxhFYktar
470SzDiXpQLdmF8N/9FGlqZsxZ1DVuCU0sug/qP3AYq/l47ZEuSfojis7OCmZUHyYUmWGBqo48Fnn8fDz72IoXo9VgQyUDQQwfN8
LF44Hz/27vfikV2nMNVopzRRkiOmID++ONueF3/14XmJE8gcgVTw7MWmH+tNQ4Y5E1D4/lg5V5xTSs6nB4VAhiwDMIuE6IYPzkf5
DlFfO+7c7D0/75eZ40h4/WSy3puk+350Pj0vSv0T6K9khgRQr7gY23ccx6z5uOltb0MYBEV4hVpqxKO/bz5wPyYaDdiOlak4K06A
RMa3RxC6UecagqQzuZTv85Oh/i1l5eXOjb7SPgAZnAwbMg8yXzOlhKM0hyWAegGVNfoMxPUpQzDl5JXVk5QUrKAMuZV8uCL53sJf
f/seNFotfQst14iPSoEm1q29Dq9deyPuf3E/7LhOjrIACT8IMyfQ9go9gShahSmzcCpXZez2I1crKz/XyhU1xe40ScjdlaZio9XC
dKOZzeKZNUXkngwfCklqXhJcM37O9QEy9iaZcPrFxq9H/gCtxKnGI8CE8EMyUHNtnBhv4KlDLdz8rvdhZHhI2/jT9SSi0mWgVsOT
27bjgWefxeBAHSHnaObzNZBq/ApAKI/Z0icF1GXmb+Dn4xLZpbyhlq77lsz2uYvwJ3VYBe4mbTbrMWDZfFOlBDekIjrVv8iyCTI3
PjhlbhGQDAzUahjbsw/f+MEDGB6oIwhDMxQ1PhW+5+E973k35IIVeGzbAQxUnTQaJ+i0JFVttXVH4AcBwiBIqarTiJ18rw0F884g
f2bMzcTCvfTx7Dq2RdQUZLDmQ0qdUcHwUexrFFJ+LtT7Cd4/4ltIuv2hkvZHUb+dlFVpaRWdx4TH0LEEgpBx/9YjuOItb8Pq1Zei
1WrFqtBQypHMBQgRAYvuvPe7MZkrKSoVsbELnffPDATKZbKEUrntjhJgZRuB6oIR52b+3chDUb6RWBAYMTKJc99Rv38HoDQgio0+
MmYMZochjKAmDROQMrqIVC8tZMbQQB133fsDjO3eh4FKNYoEhnVhAiEIJWoVB+//wAewY9rB1v0nMFitpMcValHLQ8vz0Wp7aLf9
NBsIgiDdV2fFEWSL7rloCi5gAYpDbTavjZiygrhp12y20Wi2oqaiG+njZQEw72jiCUS8sQdNYNQU9Q1dfobWEGSOeihJGSVDiTCI
Jyu+D88L0PZ8tDwvOofp+Ys2HGV8PBXHxsbN+zG06hq85UfegrZS97NB+iyUEoO1Or61aSO27t+PWqWiR3/KMsfsWilpCJbN9ams
u65TfZsmE1DK2l7m+kaC2Z7Hex3WkWcQ9Wc+BjSJgZikKCnvCITWNWWQhsgijS899vRCaGKJlm2j0fbwF9/4B4TMRZEIrRQgtNoe
LrpwGd7z/tvw6N4JHD41GeEDFFZa34uiVtvzogs4voi9dDqQba2lI6/ChACa/kCWmKuxLOcMOFcqFH87vRgbrRYarVZMshHdDxw5
jtPjE7FeXvF1pqabUVe94GTyUR+GqK/i+7PNvlDGhp+sWvs+2l6Alh+dt3Zy3rz4vMkwQn5SVPc/tu0QxusX4h23vidCDiZ/32j8
jLpbwQu7duFbmzZisFZDyDLbmFMIQDIB2gjezcKUCsfXk5F/j4pzfZQ3u5nL9f/0Br0BIkwd2Do66f91ZB+iWS0EiZ5HABKGRh8b
e1J5F8WJYGiBeBNKnUZR8yY3Dox6AZEIyFB9AE9u2YZvfP8BjAwOxLRZXGxMxlx4jekmrr3qStz47p/EDzYfxnijjYrrpPRhQToZ
iC7g5N5qR06hra2uRt3uBPWWTQhytbLWAygq4XJeECR3V52DlBLzhocwb3go2yY0dPPVsx6GEgeOHMd0o6kDlXLpvjHq5xxaUu+r
M/4I5ONHWZMXZU3tthc3U6PHk44/Axisunhxz1HsaNVx6/s/gMF6DYEfKtRkORk4JXH82+99F9PtTAVK2zYlhfg0HqUk3f9CQBQG
WS218VpQvO486SpfFuqQPlOJAXcb7/VLNkxnUR04z/yr7QXkacL1LRLDqCL+0LjIK0YKCkr1nqFkDA0O4qv3fA/XXPYavG7FJZhq
tlIuvPzSkBCERrOBm976FoyPT+B7P/xXvPf6lXBdG20vAIQEAsDPR3JFdpw5giI7DkcsP+AINouM4VjbWy9Vh2WUq0xwOZ8aF1Ua
L16yKG7IyULjTAjCiguXwBICYRgamS4Zhp5FkvKn/QKZAnxkKBGEEU9hgqVoK93+tlo2xWNXCWC4VsFLh07hyWOMW2/7IJYsXohm
sxVLeJsHYswM23Gwd/dO3HDBEuw/cQyTbQ+VmPJbkx9lZDgAJGvLWQQlrdbPOCtU6W5w73N91shwOjHz5iJ5p1GdgW6r7Dla45J5
1sbfXw9AqFp/xb2AovJv+XYVI9+4IK0ESDOCeGsvUVEFReg5LwjwqTu/jslGMyaEYMPGYEofgWarhffc+k6sXHsz/uXp3QhCiYpj
p02tII5qXjwebCVZQBLZ0h2CsAgaSpWAuUtNj5Iegf4YgXBqfALNZise+xUbhtGUQio9CD26u46t7NKzNtpj46Qgfg+5Ln+2zRdh
+qNaP6v3W+0o/fd8H0G86BOp+wJDNRe7jp7GQ/saePtP3oaVK5anxl82DWcZGf+pE8ewf99urFqyBB9+85swWK2gHQQp9TerhM6G
jIBzTTGdHJQ6dPl7aQhSF+oNM0oPJRPF4nZhJ4dB5exD9DL2AEoBPzllGC3jZF1/iw1AoHyKx3ETkBLteaJ0KvDSwYP47N3fShGC
JuNXHZDveXjvT7wHi698E+55ejcCKVF17bgfEJNW+L5SCrTRjPH8yc88z0/hw8k9VIg8oq+yvNvfw51ZYnigjorjZBGeM0hsIfIw
CuPEtDxhGEBBujNRcQlhLNwhZeTogiCAFwRo+57S6GvrztFLyqTM+AdrFew+egYP7JrCW9+zHqtXv7az8XNk/JZlodVsYPeO7XAc
B60wxIXz5uFXbrwRQ9Uq2kEAi7KxEhuIWpn0VWitXVNYmy2PnJ3m+txRXtxMy62z/BostwsQiE2sVaWEo3T2HUAR/ptxqak70sUR
NxnXabPdgQznRgmPm4KOobgUGB0awr8++jju/v59GB0aitJd1ptp2Rg2eg6YsX79+yMn8NRutLwAtYqbGm8QRossSRbQbntotSJH
0PbaMXgocgSBQmuVMN4mUFeV3ac06BfuWcfetq1Y/lwb+mmkm4XavlDfl2ADkumAzIw/0usLU1WldIff9+HF56HptdFqKdmR58H3
/WirUkZzflBk/DsPn8LG3VN463s+gGuuXhMbP5Uaf7q2zBI7t40h9H3YtgPbstEKQ1w8fz5+40dvwXC1ipbvZxwOrLJR5YUacsI9
grVFNO7E/JMz/rLHuAOOv4ziu9CILF0DZqXfRmacwEzZhmftADpsNqkYZy7IFxt2JFVoMCkKQpSBhNLtrphsE4IgAQwN1HHH338b
Dz7zPEYGBtKa17SNGDmOEOAQH/zAT2PFDT+Gbz+1F+PTLQxU3VS5NtkebMejwWbiBFpe5AiSBqEy7w78bKswcQJps5BlSgba+Q6d
VNNUOuRr91xZwVqaz2aOfmWkGUqOpbkSw48dYFwOtdo+mp4fnwM9+qfblHEpJARhoFrBi3uO4sH9Ht7+0z+Pa65eg0ajBSJ0NH5m
hmXb2LVjGyYnzsCtuNG2Zbzm3AoDXLxwAT7642/DcK2Glu/FfYR8MMomHSmxisjRllNxe49LZ/QGZR9zFdDj6+WUhHua7XfH4xQy
iT5uVjczX3TldTXLsj4q7UpNUk4zh4p/uKCqY+Lay70hPWOi0tSGNFRVJALJzHjkxc1Yd8XlWLxgXhQhlA9Zm+zG5A7MjNdd8To0
2MXGR5/CgrqFRSOD8JMuv1rbSwZDSfNjw5a5jj5y4zTOHwDzTLY1c426TvWnIdLnav4UB6Fo9alNPj+MGHsSEg+90efB90OcmZhE
EKv1Jn0I27JQdR08tu0gNk/V8K71P4vXvmYVmo1mDNdFR+N3XAcH9u7C4f37Ua1WIYQVaxTYsK1IlzBkxpKRUbz+kovxzJ59mPY8
OK4DpkiXMQkaInEM8WRAINJo0PoEWjOtDNTTAXpbJivWVUCEjAjB4uCMzNyDpcavH59gporvSVjiC+OPP3IcN99M2LiRZ+UAQset
scIf06120VVZc+ZNVJ7CqCKXOQgySKchT9LlqWYTT23dhrdecxWG6nUEsbgol0CwopQ/xOWrV8MenI/7Hn0GVtjCRQtH4wZYXtiS
s9SeM507tX6OHANyqLt8e5Rh7uuQeU+UO21nMowECQpTb974ZbLAE6qjvajJ56sd/iDbkdAIPfxA6TMwJBg114Fk4L4X9uGYewHe
e9vP4uILlqHRbJWIh6jGL2E7Lo4dPoQ9O7fBrVQjDcOEyNWyYMXS6o7tIGDGktERXL38Ejy5Zw+mPQ+u48SkoCJlBVa3p1idLJGK
QisaeDmir4zkg3rc8zdhC7p/33MqnjuGs+QAKjWpsseZUJYGNFMZqSaZvjE6hOT85cqGeC03Uhd2cezUGbywYyfedsP1cBwnjlLm
DydZQvJ8DytXXoJFF63Eg89swYljR7B8ySgcy8qANErUz0aDWZ2fNBFTR5GUAJDZWjGrKErWIjNrdX0OqWfYG2ddLLGA++fcOC8d
5ckwhTeHShMzrfe9aH+/Ha/xtr34ewUUFaQZUvQRDNQqODXRwPdeOAh3+dV470+vx7yR4Xi7j0qjvmr8p04ex0tbXoTjuLBjY7ds
G5Zlw4qdgG3ZkRNwbASSsXR0FNesWI4ndu2ORoSOk5Z52vZfgSIsf51RyfZeufFDBfXkel1m0Q+Dii9KlIVKofYoTNk6ZR4CTJXA
kxBz5ACEZX1UOpWajKbfpKX7xq5C8ciKjiAxYqGTOnBR51DFf5MhHEqOREUOHjuOLXv24ubrroEbK9FQKbV49MXzfCxdvAiXXbEG
m/cdxwtj27B0pIbRwTqCIFT6bIk4J0fy42pWEC8acewMpMyyBKmMCSXrTiQ1UnWdOE9BoPmFYm2vZSCclCsyBfBIqejySQlfjfrK
enSG5fdTIg/V8EMFHOQ6Uco/tu84Nu2exGVveQd+/J3vgmNb8D2/Z+M/feoEto89D0vYsG0npjOz4+hvR9RmdkSGEjmF6P+BlFg6
bx6uXbkCj+3Yial2vPVJrOwCZHoA2ZZgMiqkTDOUyEg/ZiQM4ZwYSCd2YCaj8ZuGOMbGYenUsTsteJQB+BKC5igDEPZHQ6tSi1hX
871MKjROOlGJa08nvSubdIqzD44NDZW8bl8s3C0lqpUKdh06jK2pE3Dgx07AJHKaOCbf9zFYr2PN1VdjPHDw0JMvgIIWli0cgaBI
lhyI1mGZGRNTjRRolETVxNASJ3BqPKqV7Zj2W6XNilB9SDfeMkJQaUYO5u8y4zBMXpdVYo6kqy9jAE+QrexmNN1+GuGzdD/ImJKC
DNiTOBciQr1aQdsLsHHzAezyhvGj/+GDWLv2egSeh1DKQs2fN37JEk5s/NtefA4kCI7jxKpEdlr3J8Yvkv9bVpQVxJmAHzKWjY7i
+pUr8ciOHZhstVCxnZgnUCir5flNQNIX2HK81p0QfTqGgMtJPspWvfM9AeoA7DGO13vjDRCMqASYMwdg2VEJEBespmBOpiOj8pNJ
VE59pPcW81S9hRZM6uWlZNSrVew6cAhb9+7DTddeGzECB0G6S29Kv4gIQWyUr1t9GRZetAJPbNmL3Xv3YtFwDSODEcV1soBk29GK
sdRGf8qabAwzTqSzk12C5HFmYKrRxOnxiaiGVTbtEkNmtUlXuGfGngB2MuntiPcgSMZ5CXw3GeupVF1+NO3wVZ7EZJFHRlFfxld0
JeYs3HHwJO7ffhKDl67Fre//aVx4wVK0mk0jk5XR+N3I+Le+8BxEbPxCWDGRqZ1mANnXzPDthP8wdgq+DLFs3jxct3IlHnnpJUy2
2jFbEMccgXE4yYMsifTIT0XUXpGtpxfGLENfASU8/lRODlrk/u9HDISyHsCcOwAdqlP4w4WMoKzoJ0OZnyNvSNIt9e+QoamoLn4Q
IqOsV6NMYMuePXjL1a/HQLUKL/Cji4JLMjciQDL8wMOSxYtxxTXX4HgDePTZLfCaDSydN4RqxYYfSnAsZaZF3ng/IDFM2xIIpcTp
ySlYlsiMNQjBLDHVaGJyuhkDmRQjltE4MVReKx3bxbRbicpuIrCRfO8rNX1696P63lOM3vODGMffTlV7NDVllrHhR5yC9aqL01Mt
bBo7iF3eEN74jp/EjTffBMcS8Nq+OeqXGP+p48ew7cXnQURwXAdCiMjQrcwBpJmAbaekp5b6vbBAloBt2fDCEMvmz8Palavww+0v
RZmA40SsQbmmMsOUpZKxB6BGXe5g8lw2G+9A8lFkH+IOrN69sgVlvzTnDkAI66Oh7daYRGa+2tiPjFG1l0aHNhIhPQXIZATZyJWg
0jyRMudljpzAnsNH8MTYFrxxzZWYNzyEdrtdVBnKyxzFJYFr27jiitdh8fJL8eKeY3jxpV1wSWLxyEC0267yA0i1KcgZjFaRv5IK
ctAPotKgXqmkAJzE+FIjj1P3yIlM49iZqZjXjzODzRt7DGn2gyDdyktx+36G2guCAOPTDUxMN2CTyP62jAw/Ge3VKw7aQYCndhzB
4wdaWLTmzXjX+34Kyy+5CO12G6FkkOgc9ROwmOO6OHroILaNPR9JjTtORE+eEp7aShaQRX0rpTu349+3YkLUyBFYdgQNXzo6ihtW
rcIPt2/HRKsF17Zj0RAtyiBuBujw4JxD4LwiCrpp7lGBSchMYFt0KJ10CLuq/pLZ+WRNwLl0AEkGkE4CyaA9b0z2jZxrRbGGPHCn
E0wzP2kwlAMsUXMrOHr6FB589jlcuXIlli9dgmbb050Tm7MByQzf87Fo0UKsufoaiKEFeGb7AezcewBVm7BguA7HsmL4bCZ+2mi1
MD45nVKREVGamgeh0oEPgmjuHoapMbdiqHHkJCLtgjAIcODUNA43GFbgoWILtD0/hekmX30/G+MlkX6q2UTb92OYc7TLkEhzRWIh
SJeKZGy5tmWhVnHhhyFe2HscD+86g3DJatxy609h7Q1rYQuBtufFYzd0bfaBCK5bwb5dO7Br+9ao2+/YsfHqEd6ODV+dBmQOITJ6
IaxU10BYBIol39pBgKXz5mHtypV4aPs2TDRb0b6HEjaIlNXfwrWnCnhSyd5W/n9mUI8ZvEPl+/9UUkp0TfnNZffZyQCUHoBxvFda
pqgy1ebn5PL80rIh1b1XJZQNIwNShCSrrouJ6Qa+/8RTWLpgAdasWomW52UbiyjRG4iPxQ98EBgrVyzH6tdfhZY9hGd2HMTu/YdR
sRjzBmuoOHaKpUdCvS1EnA2E2Vqtkr6nkT8IYxoyxuFjJ9H2/EjMxA9SPP5404dHNlzZhiME2nEUT5iOfT92AnGdn3w9eWYSvh91
5f1kiSlR5VXOERHBdSzUKg5ano/N+07g4V3jaIyswLq33Yq33nQTRkeG4bXb8e+Ljsi+JOW3bQcA4+nHH8b+PbswMDAIO47kdjzq
S+p6W3EAaSagpPxR5FcdQaKQHO2KWJaFtu9j2cgI1q5ahYe2bcdEuwnXjnAKCS6ESVeAUteMWUu3yaznZwD1cEEx2tzlRz/LRtRf
1DcCgebMAaQ4AJFTnEOObRVmwE8hI+ic2phqfc6/HukNQzI2GqML3LEdhFLiviefgh8GWHv5alhEUXNQmBs8rIphAmh70bz5tZde
itVrrkbLHsKzOw9jx75DCAMfI/UKBmrRLDsyfqnh+1mqewJhWvPLMNu6ExTpBCRNxMgB+BhvBvBgwQ5acATiaB6kTT5PKQGS54Vx
EzJpVmYNyIzj0BaEmuvAsSycnmzi2d3H8cS+KbRGVuCGH7sVN95yC5YuXgTf8xCGodLo5Z6afdOTE3j4/nuxb9cOuI4L163Add24
zrfS1F5N86ORX1ICiKz7L2JdRxGdX7IIApkDSARPWkGAZaOjuGHVSjy4Nc4E7CgbA6kBJL86QKpMdK62z2+6UtddwDJIejkWgDqD
gbpEfSMQaC4dQJA2AYmM473SjKD8YM3P4fyEECBdo7YomEi55EEFalCKVXccG4++uBnb9+7HtasvxfyRYTTb7ZR+2wiuS3kQoimD
7/uoVVxc+trXYPXrr4IYWoyXjoxj866DOHVmAq4gDNZc1FwnUiFWWIQk6zsCGUgncgIUp6dBqEfryXYAHzasoAlbIFU0CmIMfxjE
2UWcYaRiowkCMF7WIQIsIVB1Hbi2Dc8PsfvoGTy+6zjGThPci67Auh97F95y441YunhROgpMNAfNNPC64TOiev/Y4UN4eOMPcPrk
cQzEexqSGZVKBRW3kqX2SZqfpvpWigAUcfRPDN9SjT9eF1fl3gFEG4W+j2Wjo1i3alXsBJpwHUvvCRjGexpOoASOzh3JOTtRhqPD
a1IXkFCHhX8TFIeZKoEvQXOeASgDAGNaQyifbuTDtHmloCC1k+vyd1JKTcAXpBBCpklDDKWvVSvYefAgNj37HC5atAiXXXJJ3EWX
RWKPQoWR6Q56fpQRrFx+Ca686hosuPg1OOHZGNt/HC/tP4bxySk4gjBQdVGrOLAtke4ipE5BQnMQSbmQUHAljmHalwgtB5bfhJNi
D7Lpg+SoD6GOEtNdGCEi4I5jw7ai8mHf8XE8s+cEnj3cwElnES6+6s14y9veibVr12L+/FHd8FMgVeeoH8oQtUoFthDYveMlbNuy
OZrvWzZkGMC2rRS/UKnW4FYq6ZjPVhp+SbqfSp5ZFiwSoFjVWVgiVkcWQGr8WcmWZALtIMCykRHcsGolNm3biolWM+oJsN4TSJvM
pOwTa30AwzSgjKwDZmbg8udRB8CPecrWdcROESl6xfd6cgB273RAKCgEF9J1ta4iM5ySymSZOY+NZ5Ao2dmOP/CIc07EfPUAiRhu
KwFARiu1MiMzoRjUMjw0hDNT0/ivX/wS3vfWt+AXb303hgYGMNloxFBy86KI2oAUEAhDRiNogoTAZa9dhdWXXYrT4xPYuWMndmzb
gh8e3Aux6yAW1AhLR2pYNFLHUK2Cqm2n9XeYimrGCrssCyHWD0L4ItrWC5WGXdasplQ12LKsSCYsbmS2PR8nJhs4Ot7A4Yk2JkIH
zvAiLLn8OtyyejUuuvBCVCsOQj9IlY7UiNrN+KWUEEJgZHAQL+zcib/5l3/GVUsWYeXSJWgHASpuBdNTEwh8D7ZtIfA9TE2Mw40F
US1hR0ae1Pp23OijTPosMf4E5y+QLP6QuaUUS6VNtFp4zeLF+PSHPoTfu+trONVoRpLizIBINjWL4raUZI9cTiRqBu70AOpRuntM
HQR4+4z6mCElUH+UYKZN/pQWyzzCMHaKwaWjQpUkhBLwT4q/Zih8EJGDkFmDB8QgKcFCRE+TMtoYpJjTUESz/lCGcBwXju3gm/dv
wlPbtuM3f+o/4E1rrozJQX2NZqzwAWmERtHvtVseAMZgrYrrr7sG1157NSYmpnDw4EHs2bUL2/fvwXM7T8AJTmDYBeYPOBgdqGC4
VkG96sCxI1kw9ZykTEfkoxU0MThYQdW1NWmFhL4rCCXafoDTkz4mGm2cmm7jdDPEdGiBq0MYWrgKF1y+Em9YvgKLFy9CrVoBx8So
zUYzR22GrsafZDIDtSranoevfvcefOv++zDdbmP/iWO4bWAAy+bNQ9sJ4VZcTE2Mp04g9NuYjJ2AM+hmkT6p8eNRH6VOII76yWo4
CYhEzpT0PXw1aFtCYKLVwqWLF+PTH/oZ/N7X7sLJRhP1hGSUCZACJJTrTqgXu1IWCi41cC4zfiMWgEpW6rm3Rh86qAjP4Gb3Qwte
nMUXtcyoRGKJSujDC+UB5bjY4xXYFMGVrnRHV38yyqJ4yy/pFzDiHQNLgmQcPaSMiSEAsAQTMG94GAdPnMR/ueMv8c43rsNH3v1O
LFuwEJONBkIpU0fAhu28fHnAQAqsISIM1qu44nWrccUVr0O77eH0mTM4duwYjhw+hJNHj2DvmZPwj06CgjNwEKJqARWbULUJjiXg
2gIVx0opwk/F72y6HUAy0PJDtENGM2B4khCQA7h1VAYXYeSChbhkyTIsXroMCxbMx/DQICzLiicPPlrNhiLCUhzmc0kplKxCVx0H
juPgyW1bcOc992Drvr0YrNcxOjSIyVYbX3vscXzkrT+CC+bPRzsI4LoVTI6fQRC0YVsWAr+FyYkzcNyoOWhZFsiyICzSxE+JrCit
FyLOdLItP5FfONNKuLgnoDqBn/kQfveur+NUsxEBsCRHvJRSaGm4mqsysfa6RaRfBz1BkwpQN5BQv1F/FpTgPTsANpUA6mjOoBBE
uRqAO2ArVMhlYVcgWT1L5bRI781mO0TZmnDKAkMAC7CIMwMSIEjAEtHLxvDeaqUKsMQ///BRPD62Fbe97Ufx7je/CcMDdUw2mpAs
YZEo79IqGntq+pzw6YGjcmbR/FEsWbwAV73+SoSBRMvzMDU1jcmpSUxOTGByYgLTU1NoTk2hEXjwPQ9+q6msNke36rxBCCFQrQ1g
tF7HhYPDGBoextDgIAaHBlGvVSOUHSgFIPmeh3Y88qN4fZbLaAdM3e1kEci2UatUsPfIYXzj/vtw/zNPAwBGhoej6YVkVFwHU20P
d/7wh/jlm2/GhQsWoh0GcFw3cgJeK9q49FqYHI+dgDOYNvmSEV8y7qNYFITUmp8YDAFiKgQogs5gqzqBP/vQbfjdu74WZQLVajS6
FbGcGCs0P0IdzbGSr7NOWdeDnmAnNmHwTKN+R/DNWSgBmAtMq3k+W1OtQzn6AC5tbhZTKEqUM5VFoehhEXvmKLXPaikRj+4ivD1J
EWcHcVkACWYBihsDLACSHGcDhJHhIUw2W/jsN/8e33v0cXzox9+GN1+1BhW7iqlmM54mCLN6rrGUIQ156gUB2A/izIVgC8L80WEs
nD+aXuRJb4Bjiu9kcUg1StuysqZX/POoqZhNAdrNls7YHMuCl006ylJ+qRp+rYpjp0/h6/d9H/c88gjGp6cxWK+n41YIAjEh5MgJ
TLbb+OuNm/Drb38bLl64EK0ggOu6mDhzGqEX0X377SYmTp+C4zgYdB0IsuJ0X8TGL7JNUEUsNT+lI9M1WeoEPoTfvesunIidgJQS
LAgUykytVbVNJnDMSWxE+nVk98mx/JYy/PRZ63fCCfAcMwIJYX00cNyajFwldR77mVVNqKO3olKiE20gQMK8dcj61hUbVDaJcmAi
lY4s2RpjhrAEapUKjp0+g/uffgrPbd+BWqWCFcuWol6rpTBd0kvE0tGYaroEXfWXYwWcMAgQpHLlfjzeC8AyTBl7wWFK/RXGXfpA
kTgPwwBB3ORU/46GwuzD+JNVZtd2MFir49TkBL616QF8/h+/hcfGxmDFDkFqSjyZlgOD4Do2Gl4bL+zfjysvuQSLR0cBy0KtVo+d
WwDLttIRplupwq24sIQdjfpEpBWhzvpJAZURKY6hY/CkmGya0PQ8LBsZwbqVq6LpQDPaItRKWNIWTXOr7qKwU2BGAZJxwWjWxk/U
wzZgvA5M7hfGH39obpCAgVOkBDODeqijSKo2KiyZGRJ183gMTliEE7BOYSmCNAw455pFqgqxfkFFn7vj2Ki4Lg6dOIH7n34Gz720
A5YlcMGihRgdHIRkmVKIFcUtDS1PLgEaqWVDThZc55+nwjalFhGT742AEi43fiXlTxp7AFCrVFB1Kzh84gT+8aGNuOPb/4iHX3wR
DEa9Vk95GSk2UpXKHXHTTiKSAm+023hu7168fvlyLJ43H7AEarU6glCCwzBeloqYhSuVKly3Eht8PAVQjD9fZqlTqI5OIMZx1GoV
BCyxZHgYa1esxIPbtmO82UTFtnSDzPUE0s+DDLV8D2Ki5YIjvW/Qdkz5ScUBJGNAa24dQIgiH4AaVXsz5txcnzq/edL2t/OKo3k8
MSGH5tQEJUnLBnKNIyUTUPe6XceF6zg4dOIENj3zLB598UVMNqexaN48LBodjYlHkq09aFgCLmkasMFbdOorlGcX5X+nV+NXeQhc
x8FArQYwMLZnN75277348nf/BY9v3QoGUK/XotFq3F8hhW0nMVjkfsaIkJhTXhvP7N6Nq1auxJJ58wEhUIszKhkGEW9CjG50YsSg
EBE7skiNXy0FzHvpZU4gDEIsmD+Kf/qX+3D3P/wr3vymayMnsHwFHty+FeM5xGCmI5Df6Sd9aYgMUmOGspBRRhU2N1Ff/UGKBKxY
Xxh/ZC4zADX7L4v83Xb8S5aCqIwSrIRwlIhK4ZF58QcVe0CqoUOPnnkIYqpgQ4DrOKi4Lk5PTuKxsTE88PQz2H3oECzLwoKREYwM
DkaRTEY4f23C0ZHAc6bG3y27UDkCYWzoRcZpY6BahWPbOHr6NB545ml8+Z5/xjfvvx/bDx6AsCzUa/XImAmRxp4Qiiy3yIxfiKih
JlRRlyQTcDDVbuOpnTtx9cpVWDp/HlhYqFVr8Z6CD8sSCPxo0cmpVCMnQCIljUr0/7IsoHT9TPv8wzDE/HnD+Od7N+GP//xL2Lxl
B44dO4U3JU5gxUo8uG0bzjSbqCRCMzlgWn76lfIH5tl+8/R1RhSgQQJsllFfWwdG7ADkHGUApG4D5lf+yUxJbIYAUzEroE4bhB24
z7VFAOVECWXJR2VbIVLWjEknGVMckFZXCio4LduyUatW4Pk+tu7bj/uffgaPvrgZB48dhy0E5g0PYXhgAI7tAPGCkFRUlQndDL87
6q571M+8BcekHjLuHwgScB0H9WoFlhA4OTGBRze/iLvv+z7+9t7vYeOzz+Lk1CSqlQoqlUrW7U4acrHxJ99T4hA0NSfFSVBUyzPH
TqDVxpM7XsI1q16DpfPngwWhVq2l6MPMCYRwKhW4rhOVGCnwR21+oqsTCMIQ80dHcM+/PYg/+tQdcGwbQ0MDeP7FbThy9ISWCWza
vi0qBxLEoCZWo/YBOJcJ6NdJZxQgzkrUh2kbkObQAQSOW5PRCih1ZgA2LPZ0YD+hrlHfhMYiA2O2nrqpXkqkABtVY15J+7WeQDJy
yvUJkODhE+16C7VKBa5j4/TUFJ7fsRMPPP0Mfvj8C9h54CBanoeq62J4YAADtRpcx0675ZI5XSHWCEDLVp+7GH+q55dGd5m+rrAs
VFwX9UoFju2g5XnYe/QIHnz+Odx93w9w1/e/jx889ST2HTsGEKFeq8OxHbCqzGQphk4EilNzspJMIHIAKlov+bnaiEwowKfaLTy+
/SVc95rXYOm8+ZCCUKnW4Ps+wiDOBLw2fD/CDziOkzaA832OTk4givwjuOffNuGPPnUHXCciIAlDiYF6DS9s3l5wAg++ZMoElO4/
R8gfoiTWZjqXSIVyqMjrV0YV1u9svyTqG7cBe3AAfQGBdDhvHsprAAJRDvlnyBR0jRDD49AlY7WeQPKYyHW4sz3PeIST3zKOxojE
8QiQrfj76P8RFyGlj0f48KhOpsjKlIYZoeJWIoipDHHo5CnsOXIE//LwIxgZGMBFSxbj8uWX4LKLL8KKpcuwcHQU9TjlTqC0QcwE
FCqiHYxMLYg0DUYdLRGBZKyIUy82QkHRKM7zfUw0pnHk5EnsOngIW/ftw45DB3D09Ck0W21YsXMYGhyMDRQItX5Ijk1X5CYL2hIN
FYYyqgoRcTRqk5JRq9ZwptnEhrvuwn//uZ/DqqVLMSUsLFq8DCdPHIPXnIKwBNrNKZw8TsCiJRgYGIjXkHWhT5SI1gZhEEX+ezfh
j/4kM/4kEwvCEPNGh3HPvZsAAP/1P/0qVi9bij/7wG342N0RYnCgWo2o4mKcQAQ9j+TuWVKmNkQcq2CXc2Eyz8F4r0PUP7tAIKOu
utlR6UAgMo49ymRCMqgtlZYJbPCWpKztspq6qVJYaj2nwosLpUqEC6V0/Cbi7yn+ysrjimBn/HcrFRfVaiQ35gUhtuzbi+d37YQA
YbBWxfzhESyZPw8XLFqIixYtwuLR+Zg3PISRgQHUq1W4jgPXcQBEiDhVUiuJLmEYbd2FYRhp9zWbmG41cXpiEicnJnDk1EkcOH4c
R06exLEzZ3BmajJV03EdG47tYGSoEuNeGFIZm5Ii164x6SQEIEJoExyRUHEX+CGTaClT5CYxAxRlKLVaFaebTfy3r/0dPvFzP49V
S5dhSggsXLwUJ48fRbs1DUsQWo0pnDwOEC1FfWBA2d0vdwJR2j+Me/7tQfx3g/FnTsLsBD7zwQ/hY3d/HSebjQgsxDLWfIiznViX
EGm5r+AEOGrDc55odDaIPpqB4RMAd66AQMwl8l9lx5dtkJHO7W1A/pneCEOHTVPHN8/qVEBj+8n2B6BpjAglnlqxB48jPccfJGQG
DKdMfktzAoiiGyj7OafOBhCOhbpTS2HKYRji8OlT2H/iOMItWwCOBDErtoNaxUW9WkO9WsFwvQ6AMDI4ANdxNPVjAcJ4Yzoi8wx8
TDabaLRaaLRbaLY9+LFWHxHFVFsWHNdFpVpNiI0j5wElqkOlZtcFWjV1ZqFrNGo1nNAzgMwgBZhllInFDgBECFmiVq/idKOB//q3
f4v/+eEP4zVLl2FSEBYuXoKTx4+h3ZyCEBRnAkcBLOnqBJKGX2T8Xyg1/u5O4Db8zjci2HC9Uo0o5kUEy86DAjnZtY7fm4r86CRA
elaiPp0VJKA+2qAOKifmx0zPK25EEbqlTx0yiBwbUFq/KbvdlMtmKPbkBAmwFTuBeDOEhaKpB6VciEsHJFTZebFOJeOIuf9l4pss
CxXLQiV3nJIlmr6PqXYb8ky8y8/Q6MO1ykZka68ixc0T3IqLClU06HDynDBBVJMyr881rzQwT2LgOaWdZBlHdRikNcSSY1TlzChz
oFLG5UaUydRrNZxuNvB//82d+OSHP4KVS5ZiCpETOHEM8FrTEILQakzi5HF0dAJBoBr/F7safzcn8OcfvA2/c/fXcXK6gXqtGi8Q
AZAiRQtKZfTLqoQb5ZuFs4n6fRh/n/VAn03AEiCQwfV0AgKVj/3yTpF6euOkRSUFLJI8R6iNEkVxOH/hqvNNonSPmJRBMCkRkpKr
gAggK+2QZ0ahPF/o0ZUVjbpk2SWhxnJi7EHSiU/u1fjuum60SefYKVkmCSvbRc9TrKWyWRFAJzpOvYEHkY3zSPlZdLdyHX+hPy8G
/jCJFAmY/L3oEISCschEOhLuxYrjYLLRwkNbxrD2tZdi6fz5CBmoVqvwfB+B50W0Zl4bvu9Hm5yOozR847R/3ii+q6b9VnfjV5GP
+cbg0uFh3LB8BTZu3xbxCdgJz6NKDsIGbEmeZpzmZLzXnR04xwpsdccB9KQOLEvnzWxmMIkDL3cQM9elxU0LE1TQzu1epqhi2qzh
ujXpcSpCZTUgixAAWdrFTkIAVvK9BYjocbIskLD1x6zonnTKo99JjCh2FMJKn4PYIDkWueQ4UssoN4Hk+I7inVVDtZJjtLTXjR6L
tu0grHjDLntf0TFZ2Wukxxc9h6y84Su/IwRYCDAlbD3Ra7DI/gas5Ofx39ccio2QgVo9agz+5zvvxO6jRzA0MACnWsPCRUtQqQ9C
SlYygaNoTE+n8mp+ENX83/23TUrNH4nF9HNTM4FP/OlfohUGWL1sKT77wQ9ifr2O6VYLFqI18wimHVtGTOwS11fxRCbfleYejXgm
KT/NuBMo+tSnzfUCMrxzQQ68oGBdvgedyGRlAAoq/dtqpt1JezBFanFBPi8lh9RTWmU1NjF6daadm3tT6ggi49ceS8AxVhYpU6Mn
xUBTJ5M4k9hZWIpBqoZtZcYU3e3UeMnSDTn6mQWyk9cTKWgnM8rEWakGbSnHkHMiqjNUHiPNQVrp6DBzlpGTSLKk5Fxw4lwsGxKI
GoONafzBnV/FriNHMFSrd3YCjemeG36zcwLL8NkP3oYF9ToarRYEkgZxZPQMBqTUbUCTQO6hQJ9l1J9pH0BgZkLVmb4aivLKXIjb
2YKFbsBFPbWURLNr3M86zZxPFVTUIeU63IoOISdQTxHdWZCy2BLPrkWcvotkDz0fcamYFlsZSg6Jk0gN1Urn6pnRijQ6p3dLeVz9
PjVyS4/EZKWGSkl2YRWjdcHRWKJ4bJaSBVHOMaTGnDg6JXOIS420HBGJbHfiJBRHmLwPJcMIAdRrNZxqNPAHd34Fu44ewVC93Akc
P3IYjkW459824X+U1fwzcARGJ7B0aewEami0WrBiObqIgUoq/aIctkOT9eIeU/5eG339bBDO0gHo0Z30qFwyrmOUiymm0ZjQIerr
/zptFrJSdmSZAumablqfID/PzmrZFOYqCGTFiEDVeLRyQGhRLUv37VzqLzSjTCNsGtkVx6DeLaE4hswwSYvWuVIjOUaytKibGD0s
9fVyxyEssFL+ZK8X9U2Y8n0C0pCA6bRA6M4yyaQ4l9VEDoXiksmKnEC1ilPTDfz+V79SmgkwS1gU4tvf+S7+15/eAdexyiP/XDqB
D3wIC+sDWSaQlALJ2FhyTsRVMXwukobMPOrP3vhnUQJw5/Igh4s29gpUvbY08vfS5TT0HjpAhjNnrP4NUrISitiD0qaOsuQi4vRA
aaKl6Xo6FlNT5Fx2ULjYSX8sjcS20hewsq9KzZzPDmBFBJl6hCctndcyiyTVt7KIrTqGNNUn3fARo/3YBP1Vmp7pxEBAifpWWkYx
6SUIpX0PymUssROoRSPC37/zK9h19DCGFSfg1gYxODCAnTv34F/vvQ8DVStOy7kLqw3mqCegZAIUUbKxlDE3pYzKgWTkmZahKuKT
Zz7bn2XKPwsHIPToXSJplBhzWRbB4HiRwtzl76fWT14rcwhchBOTYSMp/blI3xfHXXtWV4djDHoS+dQmonbXIqFeN2sptaU0AuMa
XnUSlGs2Zo5FTdGVHoHqfKz86yfRXgC2lctYkqhvRQ089W8IJbqnvRG1F0I548++MpE2Zsy6/qRMHERWGoisD5E6ifj4wrgncKox
hd+/8yvYefRI5AQqVSy74AI8/ORm/P13foBlixbgoiXz4VoMyKAHaqu5yQQ+98HbsHAg7gkwojKAZUpQm8KC2eAEylA0M2n00ezA
AKJ3QlA2QoOZWaM5VhlTtPrcACJKDZe4K9Npp96BCghig2NgtRMo9JNJlNss1C5qKIsvpG3AGdP/fOpuqY0ySzNoCDurrylpCFpG
I6ZCPa939rNSw9KnC2qPQVhKn0Fp1iVROt/HyL3XLLUXhSWsrKkq0i3ArPxLRoJxWZBcJloWERl/NiFRegLVOk41mvhPd34FO44e
wWC9jkq9jt0HT2DbnkMYn2pg3sggLlg8ioqNl9EJLMPn1quNQYqNX4leMgaKSXUKUKh957jRR31lAz3hADjGAYSdJAG0bbry9L0A
EabSXa7ur2XWE+9yAqgHwccEcy9yW4xFwIyGH0gyBCHSix/5r8rEIWuaJQ2yPIuPaog6GIcoZ6SUL0eKa7tpFFajsSmbUbf5NKeg
R/30vSfrvykLjgIwEjmshTYDz7JFUiWxiNP3GbES2ZhoNPHQls244dJLsXhkHtbdcA0OHz6Ox596HiNDAxgdGYRtCTSbLYShREG1
dJZkmmacwAjWXbISG7dvw3irBdcxLxBB24cjQyZKcxf1k21ArzccQF8OQJJOCEJaM60T808JTVgXB2BUEKJu3qATIKrTiTYANQrH
TdoUQV9F1h8r0HIJldbKsFQDnVZLM2TKRpJkeCwzfFKAPqZSxVIMXG+AZpOOXMTPLf7oYhYJC5Eo7oyIDA3HGucDaZx62gIYId2z
J6WzK8GouDYmmk08NDaGtatWYem8eXjDG67FgUPH8MQzL2Bk8BVwAm+OwELrlq/ExpeiVWJX3SIknVlII9IgoKhqO8uor24DzqUD
kML6aOA40Tpw/hDKJMA6SYh32O4ldMsgCqqiPUooG+jMychYYqDmyuHk1WgMhZ1GcwwKPDnPQJQq0ig4+vw0osxRUHH3Pv1ddVSp
reRmzidaZlGzC1ES+VHIPlQJK1LgxJx3nCIvjBn3U0SJ8m16PqBkETqfJMfEpBPTDTy0ZQzXrVqFpaPz8MZX2gnEiMF1l6zQnUCB
74+KxDhkuIZnGPUL0mBz5QAWXLamDtvVS4AOAp/Fx3ojByXqkAV04wygfrjVunhRoWsU5mkGuYAvgBLtkIP7UjGbSDIEQakRkQZI
0mm12NRszP1OCnGOt/Uy5yEUpyD0br0W9ZXXzJUqGruSCvMtM3zKb48qUZ91iTemPJGWcs5U7AZnYiSu60SZwJYt564TaKmZABWi
tF4O5AMG9Xe9lmkD+h4z4wsTj/5wdg5g4A3XssPOL0jbnR9CcJ4V0JQ9Gzn+y7KaUmon015A71E/FfukGZ5MyrESpR+e0Fuoheiu
LskUtevyW3dMZQZdzERKswJh6i/EICZlcYcUA1YNWS0hktdjUhmbdfJRhkCReNU0HM47imJtjDxBLGdb2cSKgl78sIy5CyeaTfzw
XM0EtidOwFHYqKCxMxPlA5Uopv+l4+3OezQWQG67NUUOPjX+8MNTeOAB4PbbZzYFWHfrrT4RWmUzevP8nnJjv84GW9rhpzyoCDnI
cHnXNGPIyUGAOT+doO4XRo4EMU23DfRknI4WdVy/hijURmlC65LrEV4oBpm8nlDGapTrA0BrvqXOJ5liJJ14kR1X9jdQoE2jHINz
hKXIXZxC2fswGD4bLlqtJxCfs3RiYEXqv1HJoIwhlV0CGYOFTk438Pt/81VsP3QQNbeCP/y9X8dNN/4IXnxpLyYmG5g/OvTyTweW
LcVfrL8NC2sJWAgpUAgJVkDlkkhToRxYqM+oX4iNDJ+np9uzmQIAzDS2Zg0vvPL6D8lK9RI/UtwQRjbfLjLh+fSeiDp2+YlK3hl1
cOBEc0OzXIrSIsNeMemrzcbmXsnPc9RjlIuoamSM7FQYsoHc75oagElqnW/8qVHfRFKZlDxqxC881kFC2zRrEayffzZ8tkyFz5WJ
tP9HW4Q2xptNPLRlDNefk+XAdnM5ULJKDY1ezKiI28P1KthmSa7vHdxL/Dk8/niI22+nmTmAsTELY2Ny0VXrfoId93U+k1QPT6/p
TWIgHdZ3y2r90vXhEkPuMkqhsif1RKhQYhg50RGkM3BCXoujUCYgB0+GgWKZDCm9il40OSd12xGG3gEZjJ86ZV1KiM8dIlOZgVNv
MPI0SyOF5y/HrJ80/4gU4picwAkzKraD8WYTD27Zcu45geUrsHG7wQnkxtbEnRqD1O/1yhWWZLfau8587jNfxMdvJ9w+0wxg0SIL
e/fKBa+/4Y3suG/0AKloMuZjeqFML57TTtt7RT3BTvU+UQ8jE/QBlk75AxRCBy7LPDhlG8oaVwYBuI54CeR493IGC9K644Vxaq7T
D9MEQBPVyNL6YqRXMgWQYdypp+6GRNF4kbJxBTZfRuQyKlInA7nfS9mWMjEYGTuBiWYTD24dw/UrzxEn8OZrsXQo5wQcR8FC6IZO
ZJqPk9KU7nSNq1moCKtgYfutx8+86x13Y2y9hbExOSMk4E24Odnw2yvi3Wcu+8Nqvd8F0ddRf5C5Jw41VrYSCz2Efo1ffQdq70BF
FKqUX5wRihlXI1Qj1gxf6Nl0GR6EzeVSoQmognmQr92TPkWxj6J3nKnkMVFYtDL3f4p1qXk1nHSYOCmsOQyNVIMTqLAiCMpIoMMq
iUmEnEx2B05ON/B750pP4E/+Ei0ZwYb/Yv0HsTBFDCKDDCd8AtD5JdHLTkzJEh2BIViCGXsBAMeuoBn3APauW0wYG+MFV68bJaaf
86OasaAC2KnD3w3RR0BPUd8sId67skpHv9Qp5Z8NNptyc38BGFvgeTYZ0ptsxTEkjBMKXR+xpEwQVBC7QMHwqQj9NkpdU8HwjeUE
U+kimHbpJuNMFRjE+fG4Xg4k0mohMyp2BBZ6cEsMFjqXMoF8TwBcxI2omJGycoA6g1yImWthICgMv3zm0Yefwi/cLLBxo5xZCbB+
PWHjRl583ZsoDPxfCyzXliS4MLgrKVGohC22bLZPPc/vqagZMCeNPvRm/D2ROphQheUGmwcjcWH6oDoMUXiMTY5TdRQip6iWdwxl
hk8mMaO8JDeX8jsYeyhs4IrI04zn+CQ1uS5VHISyBbt8ObD2XCsHLlmeOQHHTgHnBYwIoRjsCohac++MWFLVaxOx/PSZRx/ei8VR
EJ+ZA9i4EQAwcPU7G7ac/nlpufOCuPAl6gAG6trhpx6jvqnR19uUoauySr8yTd2iftd5LZk/vHxtbYj6+fGe0fDyF42SxnOZ16Hu
WvZFw6fOhp8yMBs+pxIKOM7pPrIq7KQ1H6lENYdT0JBEjBNonMNOYEcuE9BYmWEObpp0HZVR5rMtmdxWY5Lh3j7+6INTSRCfmQMA
gA0bxPhnb/cXXrXuFnacy32IqBFI5rEfEfUcZDOizd6iPmGWyirqOWQqwWDPUdTPSOM7bDGWlQJksuhSoE3xOUIxQCrlbOyUGRVt
NYftL+NqYNM55Q7HkJtwJB5HZPsknPvwtGGAUt4lS0iJ0OlEo4lN52Q5oGQCtpPTGSRoynbC0DAqSbsZxFVIctreC3v//JOfwe23
dzT+nhzATbjZ2rt3o1xw1Q0rybLf5gGSqHim+qv3567Wp7lI+efc8Ptv3iDPNZ9fse7yetzDKqTKYlvqGDp8eEbTN0F/u7wimyJZ
Qasl42WgQsmRGydSXqUakDJDDJ7bmUBLyQTymgwGHosOkwEWIqxLKSyv/e0z73rHP2PDBrtT/d+TA0gagfOvup6I8YuesKIhDBVH
fKXbe0YV4d4MrxPoqNtsn7ql/DRXxk89o7RyempdInG58TP1NuXI19GF98WdswEmKkVecunf7/D7hu1LnVyG9OxAUXPmXIecTFt1
rGcCFcfBeKNxbjqBi5dj446XDDgBpGNoMoHJjBuEBGLmuu8J9oPPjD/28Au4uXMDsLcSYGwMALD08nWnQpIfkY47HIJkVqb0gujr
jOOnXgkQjPqC1IeSKvUWrIlmnvIz6RF8Jo1GQybDvTDIokttro5tufuYteNj3dv6XaO+RuGVV3pSCUcol7gkmYBSJqglEinOU7J8
9TgBR5kOKFwUhJxjKEwGCAxiR4bCbUw3yK784ZlHHhzHzTdj1iVAPA2wjn/zq+0FV61dJxz3Sg8ko4EglYNzjFGfemArMciF9VDr
U3GvuP/xHvpN+XvjMOzH+Lln1FdRsakbiWR3RqUOx8cmp5Cf1fUW9QuGTwYNSsr1BEg1dgU+nw8wSSed1b4Eo+K4GG9GPYEbziEn
sGw4cgKbdr6EyXYLtmUXjDvrc1D5BiGRrMlQ2K32E3v+/I//DGDCxlt4drsASR9g0Xpr796NcuFVN1SJxE95QjCREN339jtEfaLu
rXQqO8+91vpqGdFFpgn9dPh7fKyM93A2mvDcxVB7gecWjI5Ll03MACuD4Zc5E9JniZ00JgtLQ0acQA4azqrCkkGqLjagdETYaGLT
1nPHCaxbdzUuGB3FdRdehO9tHYMfSgghiujPfA9N5JqCRHIgCITwvS+eeezhB7EBXev/nh3A3r1RGjFy9dojIgz/Y2jZ9ZCINTjG
THH8fawOaxqANMMmW4+1PsEEzyMj4rebA+rpPRF1p2TvoXnJvTAgGbMG6uxkqFQMskMWQbpWYsdzVzZloBwPQ15hSm2rKP0KlXko
Rq4kMmTnghOox05g1+4DeMtbrsfy+fMxr1bHv23bgortGEhsc8rNimNlQbCDgCrNaRlY8mMTjzxyrJf0v/cSIC4DTn/9zqkFV91w
vXDcKzwSYX4vgGAAKpQtNHXhNy9i97pHfTKlhXPW6OtxHbOE/qxr85INiXwnIpSOGYH5D7KxmaeM4Lhz5tE5izA4NJPhl0X9DqUM
G+pfRg40wwqXILL1ZVXLnmLjq8SkIpu2bnnFnAAzY2CghrGtu9Bue1i37mqsXrAI248fxbbjx1BN9gYMDFSGHkBYk6Fw2u3H9w0P
/jEeeAC45RaeLSmobv9XXinGxsZ4/tU3tAToZ3wgprUxXzHUQzpr7PCXGB71paSK8hFjHoI5I1BPH1FfS1W5d2XYkkYfd21fUDFv
6PCeOr8em7uBpYafva8CRz+VZyjcbWpQ2CWhDFZNRUxBujpccMLnWCYgGfV6Fc89vxWrL1uJyy9dgfluDf+6ZXOkbZjuRwhtt0Rb
fRdR938gCASF3h+f+eT/egzoLf3vywGMRdMAGrr21r2WP34bHGdBQCQpz/5JZYbXbZ+fSkoI6vM5s6BZnslcv4d0e0ay0JwHwKAn
h8E9HEO6wNOVDB7GTIY7ErF0wwrokEHuOC407B+oOxV5clFNkDavQk2avHzCJ/BKOwEigh8EOH7sFG65+Y1YOjSMZw7sw57TJ6NS
QAMD5fZaIhQlV8KQ3Mb0OEn3N8889tB0jOCd2wwg6gZusMf/6XZvwetvGLQd+8c8pjCW0enAsKtfIL0t6mWjnd4MnHrjTehrvNcP
4egsSEi408it2zFwbhUZveP4exrwUU/IQaaSy43K8QpcBhAqXT7KZRgatqETb0PiHFhndUqcQMw2/Eo5gQS1eOTYCVx3zZW4bMUl
OHjqFB7etRO1SgVSg7bnJO6i9x0OcmhZvv/V3Z/947uxvvP6L2YlDrrxdgkAoiq+ilZr0mFpcdJ1oRy/F5sJOxj51dPOYiTqGm5X
T2CkEEvWWUvkxjs0L/uu9Q01c3Y64r/PuXsfwCJN6oS6gIgKH0VZGWM6K3rJwV1Wss0isYYfM5VKypdF/TxeIROTyS5hVngMqECi
GtOlU1FajSwLIcerxI0GPvZ3d74iq8RCEJqtNp7fvB3CEli9eAlcy4p0B2VOYUizDoIdBMJqNkPJzhcwg5uFfoWB16+3Tv7dVyYW
vH7tEttx39giEYIgqFu6TdTDxK1/UE/HTKFbh30myio0AyXGXqJ0PkJSb7P97jDevEPjrrVEx95BSspBvQOIOmQ5RmFZLitvclFF
kF4alKJMVfot1vEjRJAyLgdacWNwxcubCQhB8PwAC+eP4uYfuQHttofvjm1GIGWaYJPK4Jw6OhEOyNCy2q1v7/3cpz6LDRsEPv95
edbEQQEAV1zBAEi69GlqNyddGVp5VWRjrW1k/kRhzts9SlNhDFQk7ODOfJ8zZFvtvq/cn/PJi5epsmZdjd+USZQeg/GslsiqlaXh
6nklcw5hGBeWZTncsdbvIgYLhaA0T7GdqDojT38W/zyVLrc0gdYQhHq1FmUCX7sT2w8detkyAY5FQ86MT8D3fdRdFxXLgpRSccf6
hy2j6E92uxmGQnwibtTRWVUHBgDcfrvE+vVi51fu2A+W/29NgAAOTUw9ZgNig/onlUYH3SlQX93/RMRUdwwGdh9Wt/dYz7RQtt/C
HXiFkuMu+Udsnu1THwxIPZ+HzvDcwnnN9w7U8iuP6OtStxsN3PQcw+WgOsiuNON57oNYbMUoYZ44AU3JWZcmfyWcgAaOS6/NmDGI
ZaQxqNZjjLAGKTjwv7P/z//kSaxfb+Gb3wzPvgNQsgDPGfwk2o1TFRmK2CkV8OYdo5PpCuAunGfoRPE9k519RcKcFSowVgyWlcdY
jdjFf+gr8yjiJQo9Au6w6af9KBfluzmSDsAi1VnmG21sMmI1UjMb9wxKn1PizExAJe6yrahRr8XKzlQQVFGcgCqWGguphhT3BJoN
fOyul8cJEAFSSsyfPwrHcTDZaqHttSGI9AWobIGMncAju9nwpOX+PzMXB++/B5AQhTDWr7fGv/alyQVXr2Pbtn68DchYlK7rdEyn
Q+5SZ1OP9XaH8Z46BSqk8XMJ6uml39D3eK/MoXF39qF8skLlY4LyTn4HvADlsf1kYAvqxBsAo+J0r2zDRiIUmHQac96H8qvrlIZD
SmHDynTgLPcEhCC0Wm286+1vxRuuXYOndu/Cd158DhXHUbgkE5UnAQBymKUFr/3F/Z/99JdnGv1n7gCSLcENG8R8bj+Jae99lmUv
9YQVUryjVc4NULK2S/3s7NMsV3fndoHn7PMGcG8jxlIyD/M6csdeg8rAU0oawqXviXsmGik3fI3qrGs2JXTnQyWNwdxuPRkINkjd
HWg1sWlbb43BIJSgGTgBZoZjO/jFn/tJXLh4Eb79zNN4fPcuVCvVTM8hVmBmIWQtDITTbBytuiMfOPnjN7ewaFFPsN+5dQAAsHix
OPXlL/vzr37TmM3yFwIQS2EJKgMD9drhJ+rCH4ju2mQzHe+hT8JR9DNl6MYbwH07E+7WlOxpuaf7zn7pqnGpXoHpWT3Ck7m78ykf
BZM5g6Q8cCyHsTdwWkjEiMFmozcn0GohDLmvTMCyBKanm1h73Rr87E/fiulmE1/YeB9ONBpwbDv6XStTg7akDAfDwAL4N3b9+Scf
xeLFfXf+584BjI0x1q+3Tt315d3z11y/yHHtN7RBAYgEdY36PUT3TorJ1K/h9QDX7QvU02F7Txu59epIesskCqSeXam9uOt74h6O
oSxCdwYJsbnXkBi+cVxIfYxNO6x/U35zroiiU7MEyjv/uH+QwobLnMDTL2B4aADDAzX4vo/plq8ItHRv+iXbmH/wO7+MVRdfiIe2
bcOdjzyEWrUKjqN+YvxMIhiSoU1e+zv7/vdn/8tsUv+5cQBKKeCc5gcqYft9whJLPVhhCtjskZyT+qHkBpkTADoLiD70iRXoxNTT
U79BMfRuWQd1YQDCTHD8VMLUU4IXoG6mnx/bcgk8ea7Pq6J3aMIJGJSKTES3GWzYwUQrdgLLMyew/+AxPPnMi3AdB1ONNryAAbJ6
mhBbloVTpyfxqx/5abz77Tei2Wjhf97zTzg0cQau64JjYReQAAtL1gJfuF7rOFP1Jyae+OEU1m+eceo/dw4gLgWmv/6l9rxr3/SY
HQYfZhJWQBZ1VBLuxm9eGqV7iPoandLZaPT1mZrS7FZ3OylAdib56JWHQOkLlFB8FxpyZMYKmB0qd4H5Ug/Z1Gwp3XKNwYITyPHw
5XxtWg4kPYHlq7BsdB5uWHs1Xtq5D089vw22UwEJuysI37IEmIHTZ8bx/ve+Hb/2Sx9EVdj4m0cewv/35OMYGhhABLmNGn9s2XBk
GA4EvhUQbjv4fz7zFNaPWbNJ/efWAcSlwOmvffng6OvXnnJt6yd8IJTCEh2vYerP8Kjv8V4XQ1XZgbnb0KHLzr5GG0AdpMF6WN0t
49akXrYBDduDfTMAd1rd7WD4JQrRnXsRZyObIrOjyAlxEAw6j0ZOS4ozAaS6A5u2b8Ha5atwwfwFeNObr0fb8/Hs5pcQBhKO48Cy
LE3JSRBFG37MmJ5ugsH4jx9Zj1/7pQ+ibjvYtH0rPvGdf0ClUlFGl9FoUhD8IQ4d9tufPHjH/7kDGzbY+Pznw7kw3blxAIkTuGmD
ffo7f/r46JrrLnZte22b4YMiseeOhB3dSEM6Mg1TrtY+C42+vlaRZ6ks1EOHvbOx9vKeuPtorYywQ+tFcGkN3t3w5zabKs8Qy+i0
c5T0RoWeYt8q6wm08OD2Lbj2kuVYvnARbrjhKqx+7UocO3EKR4+dwNR0A74fIPAD+L6PZruNVqsN13Gw9ro1+IPf+WW86+03oips
PLhtC/7wm3chBGA7Nlip+4koGOLQEW3vuweWLf6V2Tb9+hXM6//11q8X1897mzjTfO5fQ7f2oxMQAQmykdOE78VISrECPY/WqKS8
f4Vq/VyJ0kl+q5dj4H6oztX0viM8eeYlB5tGlibSkrMR9Xsqo9jg2ThF3kV6fbFmH8vo52H8f5ndWYawGGi126jbNn7n7e/Eu15/
Der1KiYaDYxt3YkXx7Zjz76DODM+CYCwYP4oVq24CFetWY3LL1uJgUoFU1MN3P34I/j8D74HFhYcxwELigBKlgAsKxyU0rK99hZh
j75l3x2fPIMNGwi3337OOgBgwwaB22+XF/z8/7WgCmwM3MqVU8IOKc02qEcD7wLqmasFntKlpA50YKrSDVFXht2ZHENRd69/vIKZ
lIP6YADuQjraAy0a80yzqV7HwP1iMExbSpHxc4JIhQQkIocgZQTJlVJzBByGEAAC30er3cZNl12On3nDm3HVRZdgZGgAJAQ834cX
hiAAFceB69gIA4lTE5N4as9O/M0PN+LxXTsxUKuDLCuDJtsCbNnhQBhalcA/KIVzy8Evfu6lxLbmNmKfjVt8oMs/8msrLNgPBU7l
wilyFCfQWULceJH0whHIJRlgX1G/X1IHmvlFWtoYnEmE5C79AerRmZRE816VhcoM/2xkU32Ru+i8g9lbU5xAotIrkWUCMs4EcllA
lAlIEDOIGVONBhwhcPVFl2DdilVYvXQZlo2Mol6tgAFMtVo4fPo0thw6gEd37cCLB/aDCRis1aKGH4kk6oOFkHUZimoQTBPopn1f
uuOpuRj5vXwOAEBywJf84m9d4TDu9SznwinhhESwqA/DK+/k94fo0xzETFJ+zE1qyrPpN3SD0nZi6unh0+8ZJAT0oSp0lnoomO2K
d84JKD9jbRFDFjOB2CkkTgCSIcDgMESj1UIYBrCFhaFKBRXbBhhoeh6m2i2EMoBlO6hVKiASEeFHsqhkWWDLCutBYFUCf5qJ3nvw
S1+4DzfdZGPjxuBsmOnZcwCaE/i9Kxz27vVs98IpYQWAsEnFhvUJ5e1pvDdXNF00d8Y/o1rfCNml3jKJnoBF3NWhdnRaHZWFzqWo
34PLSjbMkkwASV9Apl9Z6k4hyRI4dgoCDJIMyRJhGELGfQUhBCwhEq5USFKkwBOgjxBhPUr7p5jC9x380pfOqvGffQcAAOu/YeGb
Hwgv/vBvvaZC/E+BW7lyAiJgYdnERegrzRJDTzQTKO8r0ZDqMXr2WBtzH1GXy6i/qEeRkB6Uhc6JqN+TM2F9hpuwCxsbg8g5AbU3
kJQJnDYQM/0sLk51FKVnFjYICAZY2rbfPkjC+skDf3XHE2fb+IG5HAOW3ca+yVi/3pq468snB9dc8w820bUVIV7jSw6ksM2DICNs
uE/tvW52SNRn5O8jQjFpctgdI2RfS0E9zPbzEOmO5Ch9yIT3VXbMAMdPMzB+miP6dsqhB5FfIEK2Spy+NBWWiyjNToXOQaBE+WT1
GFa02ce2DcEIhiBt2/M2w6F3HfzLL7yADRtsfPWrwdk2z7OfAeTKAfzWb1VWTsi/JKfy4SkmeJYtSd0d6KPWpxmP986S4c9VakqG
pmDPI8ZyZl70hePPKe+8KrKp2Wx6sr4/zarHY70vkPQAWIn6ys8gWX8OTFqNAkxCOoGPQYKA798Drv38gb/+zKmz1fB7ZTIAFSi0
YYPApz4VnHnuiX8cXXP9hMvyRy1BtgcKmEioZBZFAYT+PlCaE47AWYJ6qDuOn/vadJshqKfMocxge+/lgEj3Ihwzo6jfcYkoL7ah
XysFbT6RcQpoRKSUcfelSMAY0ktCgCwBWDYgRFgPA6seBgSWnzxwwZJfmfjMJxsvp/G/vBlADiyEb34zvPgXP/ojDvNfSde9fEpC
+pYNkbIUUW7LkwqAv7kc79EczaB5poSjPWoM9Drb7yTE0Vuz8RUES71c2g3UTQ9B4SnjpJzKTQgYSsSXRSonNQOIVXytMJB1lpbl
eYeJ8Bv7v/j5fwJAcw3yObcyAANseOIfP7Vn3rpb/pa81qIK+HpBoAAiYCGISiQECsKfSVuVZsEMTHN8kfYpcGL6fWbuKd03OiDq
uHZZRAbOBiI91yk/vQxRv2d+h7wSbx68JnTZrjTiU7aGHNf/bFkMUFiVoTUopRBh8A9SyPcf/MIdj8dc/jzbzb5XSwZQ7AsAuPiX
fvu9NstPsuu+rsGEtrDD6FQyzbgmVHTiUidxtpBn3STHSd/oMa/F9r+bwH0ZHndhC3q1RP1ZoD+pd2m1Aqdajtma46mAkcxRWcxm
RugEvlVnhtVuHmDCf9v/+f/9lbwN4BVJx1/5W1oSLPrN3xwcbFr/mcEfDd3acJMBX1hhRDDCZm2huWz0vZwX6AwcEPeLV+Aemnxn
Q9bslRzvzSmlG5uBQwqASOPDV4w/7suEtu9bNUhYraYngL9qVew/OvrpTx/Dhg0iZdl+RY3vXLkpnvDCX/joaysW/lBK+bNhpVpp
MsGPAESWOSPIf+5n4yJ9GepSmiWajrn3qcFcQ6RflmzqbET9Lu8pP79Xa3pWlokUlwCm0A58uwYJu9EAgf4eDj6x98/+7BkVG4Nz
IvqeWzfC+m+I5OSs+vXfWwPf/xgz/0xYqVZbTPAgQilEogtDr0Sj72XZ3uv0nrgzkebcA5VezeO9Ocg8uMQpMKu5AUNKdmVoVZlh
NadBkr/FJP5072f/9BElyMlehTv/PToApMtEY2OUZATLf/V3Lxe+/0tM/DNw3As9YcNjwKe4YcgQpU3DlxXRR3PckOqV5XeW1Gdz
Buo5G9t7vUb9WTjUnhwQo7hEDElgtoPAdsFwwxCi2ToFwt2BsL584NOffCK9ns+BdP/V4wBKHMFFv/yx+Ra891lMHwqZb0Kl6vpk
wWNCICiUEBw3CYSGCp6ren+uL9ISFr8ZlzEvd3p8zhj/2XhPOap1onTWR1KSzdJymeFwCNFoSAI9wqC7Q6v69/v/5PZD57rhvzoc
QIkjAICVv/K7l1HovxuEW0PmG+C4I6FtI2BCACAEWAqSDGKmeKrIIBBnjIO9rg7PFm/OPW4C/nsz/HOh1i9cA8QAcczsxiQlEUth
McgBYLOEFQagVqsJ4GmyrHt8YX3nwB//jxe0/ZcrNvO5bPivLgegHu9NGyxs/HioSuNc9Gsfu9DxwzdChjcysA6Ey9iy58NxIEUk
/CgR8bwnn0g4mzXfGWwwdrXZc6bkOBsLNyUCJ+VkkeVlcgGvwLMuYxiAiAU6CRE4JhIXkxChBPke4AeTBGwj4qdgWQ+G0np436c/
sTsXqGx8/ONh5EReLQb1ar1t2CDwAARuhsx72qW/9VuL3BZea7O4jEN5BYAVTPJiIjFPSrkAIAeCBno6FTSDMzfXEuIz/lTnqNaf
1Tr0DFas59Kh9XYMBOZpMHwS4hTAZ8A4QMBetqwtAG8NRXVHmtqrz9uwwQKK1+B5B/By3pgJH/iAwLErCBtvD8vCxxUbNrjTe87U
W7W2W+GBhefM8bvnyDF4fR5sp+e4r57Lx7FCCmTtJPwzLWfVquaO3/7tdukvf+MbEXp286sjxf/34QBMhFXrY4cAAIvH+Fwbv5y/
neN2sX69wBXx9TM2xvjGN+SrKbX/d+4AurxfZuDjH6fz1/n5W3r7+MdZ6eucDxTnb+dv52/nb+dv52/nb+dv52/nb+dv52/nb+dv
52/nb+dv52/nb+dv52/nb+dvr/Lb/w+Ii+Ivbb82tgAAAABJRU5ErkJggg==
"""
WEB_FILES["/icona.png"] = ("image/png", base64.b64decode(_WEB_ICONA_PNG_B64))

_WEB_INDEX_HTML = r'''<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="nt-lingua" content="@@LINGUA@@">
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
<script src="/i18n_en.js"></script>
<script src="/i18n_fr.js"></script>
<script src="/i18n_de.js"></script>
<script src="/i18n_es.js"></script>
<script src="/i18n.js"></script>
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

  /* I valori del profilo sono codici italiani salvati nel database: qui diventano frasi nella lingua scelta.
     Ogni frase è intera (non "capelli" + colore) perché l'accordo cambia da lingua a lingua. */
  const SESSO = { F: NT.t('donna'), M: NT.t('uomo'), altro: NT.t('altro') };
  const FOTOTIPI = ['I', 'II', 'III', 'IV', 'V', 'VI'];
  const CAPELLI = { neri: NT.t('capelli neri'), castani: NT.t('capelli castani'), biondi: NT.t('capelli biondi'), rossi: NT.t('capelli rossi'), grigi: NT.t('capelli grigi o bianchi') };
  const OCCHI = { scuri: NT.t('occhi scuri'), verdi: NT.t('occhi verdi'), azzurri: NT.t('occhi azzurri o grigi') };
  const EFELIDI = { nessuna: NT.t('nessuna efelide'), poche: NT.t('poche efelidi'), molte: NT.t('molte efelidi') };
  const N_NEVI = { '<25': NT.t('meno di 25'), '25-49': '25–49', '50-99': '50–99', '100+': NT.t('100 o più') };
  const ATIPICI = { no: NT.t('no'), si: NT.t('sì'), 'non so': NT.t('non so') };
  const SCOTTATURE = { mai: NT.t('mai'), poche: NT.t('poche'), molte: NT.t('molte') };
  const LAMPADE = { mai: NT.t('mai'), alcune: NT.t('qualche volta'), spesso: NT.t('spesso') };
  const TEST_GEN = { si_positivo: NT.t('sì, positivo'), si_negativo: NT.t('sì, negativo'), si_non_informativo: NT.t('sì, non informativo') };
  const ESITO_STAMPA = {
    attenzione: NT.t('tutti i metodi con risultato indicano un neo da attenzionare'),
    discordante: NT.t('i metodi non concordano tra loro'),
    benigno: NT.t('nessun metodo ha segnalato il neo (questo non esclude un melanoma)'),
    nessuno: NT.t('nessun risultato disponibile'),
  };
  const lab = (tab, codice) => tab[codice] || codice;

  function riepilogoProfilo(u) {
    const p = u.profilo, righe = [];
    if (u.eta !== null && u.eta !== undefined) righe.push([NT.t('Età'), NT.tp(u.eta, '{n} anno', '{n} anni')]);
    if (p.sesso) righe.push([NT.t('Sesso'), lab(SESSO, p.sesso)]);
    if (p.fototipo) righe.push([NT.t('Fototipo'), FOTOTIPI[p.fototipo - 1]]);
    const fen = [p.capelli && lab(CAPELLI, p.capelli), p.occhi && lab(OCCHI, p.occhi), p.efelidi && lab(EFELIDI, p.efelidi)].filter(Boolean).join(', ');
    if (fen) righe.push([NT.t('Aspetto'), fen]);
    if (p.n_nevi) righe.push([NT.t('Numero di nei'), lab(N_NEVI, p.n_nevi)]);
    if (p.nevi_atipici) righe.push([NT.t('Nei atipici'), lab(ATIPICI, p.nevi_atipici)]);
    if (p.scottature) righe.push([NT.t('Scottature'), lab(SCOTTATURE, p.scottature)]);
    if (p.lampade) righe.push([NT.t('Lampade abbronzanti'), lab(LAMPADE, p.lampade)]);
    if (p.melanomi_personali) righe.push([NT.t('Melanomi già diagnosticati'), String(p.melanomi_personali)]);
    if (p.fam_compilata) {
      const f = [];
      if (p.fam_melanoma_1grado) f.push(NT.t('{n} parente/i di primo grado con melanoma', { n: p.fam_melanoma_1grado }));
      if (p.fam_melanoma_altri) f.push(NT.t('{n} altro/i parente/i con melanoma', { n: p.fam_melanoma_altri }));
      if (p.fam_pancreas) f.push(NT.t('{n} con tumore del pancreas', { n: p.fam_pancreas }));
      if (p.fam_astrocitoma) f.push(NT.t('{n} con astrocitoma', { n: p.fam_astrocitoma }));
      if (p.fam_uveale) f.push(NT.t('{n} con melanoma uveale', { n: p.fam_uveale }));
      righe.push([NT.t('Storia familiare'), f.length ? f.join('; ') : NT.t('nessun caso indicato')]);
    }
    if (p.test_genetico && p.test_genetico !== 'no') righe.push([NT.t('Test genetico già eseguito'), lab(TEST_GEN, p.test_genetico)]);
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
      const dd = (prima.diametro_mm && ultima.diametro_mm) ? ' ' + NT.t('Diametro: da {da} a {a} mm.', { da: NT.num(prima.diametro_mm), a: NT.num(ultima.diametro_mm) }) : '';
      variazione = NT.t('{n} foto in {giorni} (dal {da} al {a}).', { n: foto.length, giorni: NT.tp(giorni, '{n} giorno', '{n} giorni'), da: NT.fmtData(prima.scattata_il), a: NT.fmtData(ultima.scattata_il) }) + dd;
    }
    const mostra = foto.length <= 8 ? foto : [foto[0], foto[1]].concat(foto.slice(-6));
    return h('section', { class: 'st-neo' },
      h('h3', {}, h('span', { class: 'st-badge' }, num), ' ', n.nome, n.regione ? ' – ' + NT.tr(n.regione) : ' – ' + (n.vista === 'retro' ? NT.t('retro') : NT.t('fronte'))),
      n.note ? h('p', { class: 'st-nota' }, NT.t('Note:') + ' ' + n.note) : null,
      foto.length ? [
        variazione ? h('p', {}, variazione) : h('p', {}, prima.diametro_mm ? NT.t('1 foto del {data}, diametro {mm} mm.', { data: NT.fmtData(prima.scattata_il), mm: NT.num(prima.diametro_mm) }) : NT.t('1 foto del {data}.', { data: NT.fmtData(prima.scattata_il) })),
        h('div', { class: 'st-foto' }, mostra.map(f => h('figure', {}, h('img', { src: '/foto/' + f.id + '/mini?l=480', alt: NT.t('Foto del {data}', { data: NT.fmtData(f.scattata_il) }) }),
          h('figcaption', {}, NT.fmtData(f.scattata_il), f.diametro_mm ? ' · ' + NT.num(f.diametro_mm) + ' mm' : '', f.tipo === 'dermoscopica' ? ' · ' + NT.t('dermoscopica') : '')))),
        foto.length > mostra.length ? h('p', { class: 'st-nota' }, NT.t('Sono mostrate {n} foto su {tot}.', { n: mostra.length, tot: foto.length })) : null,
        ultima.esito ? h('p', { class: 'st-nota' }, NT.t('Ultima analisi automatica ({data}): {esito}. Strumento di ricerca, non diagnostico.', { data: NT.fmtData(ultima.scattata_il), esito: ESITO_STAMPA[ultima.esito] || ultima.esito })) : null,
      ] : h('p', { class: 'st-nota' }, NT.t('Nessuna foto ancora registrata.')));
  }

  NT.stampaNei = async function (ids) {
    if (!S.utente) return;
    const area = NT.$('#stampa');
    try {
      NT.toast(NT.t('Preparo la scheda…'), 'info');
      await NT.ricaricaUtente();
      await NT.ricaricaNei();
      const scelti = S.nei.filter(n => !n.archiviato && (!ids || ids.includes(n.id)));
      if (!scelti.length) { NT.toast(NT.t('Non ci sono nei da stampare.'), 'errore'); return; }
      const dettagli = await Promise.all(scelti.map(n => NT.get('/api/nevi/' + n.id)));
      const tutti = S.nei.filter(n => !n.archiviato);
      const numero = id => tutti.findIndex(n => n.id === id) + 1;
      const u = S.utente, rischio = u.rischio.presenti;
      const prof = riepilogoProfilo(u);
      const nuovo = h('div', { class: 'st-pagina' },
        h('header', { class: 'st-testata' }, h('div', {}, h('h1', {}, NT.t('Scheda dei nei – {nome}', { nome: u.nome })), h('div', { class: 'st-sotto' }, NT.t('Stampata il {data} con NeoTracker', { data: NT.fmtData(NT.oggiISO()) }))),
          h('div', { class: 'st-sotto' }, NT.tp(scelti.length, '{n} neo in questa scheda', '{n} nei in questa scheda'))),
        h('section', { class: 'st-profilo' }, h('h2', {}, NT.t('Dati della persona')),
          prof.length ? h('dl', {}, prof.map(([k, v]) => [h('dt', {}, k), h('dd', {}, v)])) : h('p', { class: 'st-nota' }, NT.t('Profilo non compilato.')),
          rischio.length ? h('p', {}, h('strong', {}, NT.t('Fattori di rischio indicati:') + ' '), rischio.map(r => NT.tr(r.etichetta)).join('; ') + '.') : null),
        h('section', {}, h('h2', {}, NT.t('Dove si trovano')), mappaStampa(scelti.map(n => Object.assign({}, n))),
          h('p', { class: 'st-nota' }, NT.t('I numeri corrispondono alle schede seguenti. Sulla figura: a sinistra la vista frontale, a destra quella posteriore.'))),
        dettagli.map(d => schedaNeo(numero(d.nevo.id), d.nevo, d.foto)),
        h('footer', { class: 'st-avviso' }, NT.t('Questa scheda raccoglie dati inseriti dalla persona e foto da lei scattate. I risultati dell\'analisi automatica sono sperimentali, non sono una diagnosi e non sostituiscono la visita dermatologica o la dermoscopia.')));
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
  const NT = window.NT;                      // creato da i18n.js (che si carica per primo)
  Object.assign(NT, { S: { utenti: [], utente: null, nei: [], imp: {}, stato: {} }, viste: {}, pulizie: [] });

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
    catch (e) { throw new Error(NT.t('Non riesco a contattare NeoTracker. Il programma potrebbe essere stato chiuso: riaprilo dall\'icona sul Desktop.')); }
    const t = await r.text();
    let d = null;
    try { d = t ? JSON.parse(t) : null; } catch (e) { /* risposta non JSON */ }
    if (!r.ok) { const er = new Error((d && d.errore) ? NT.tr(d.errore) : NT.t('Errore {codice}', { codice: r.status })); er.codice = r.status; throw er; }
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
      const ok = h('button', { class: 'btn ' + (opz.pericolo ? 'btn-pericolo' : 'btn-pri'), disabled: !!opz.scrivi, onclick: () => fine(campo ? campo.value.trim() : true) }, opz.si || NT.t('Conferma'));
      const d = NT.apriDialogo(h('div', {},
        h('h3', {}, titolo), h('p', {}, testo),
        opz.scrivi ? h('label', { class: 'etichetta' }, NT.t('Per confermare scrivi:') + ' ', h('strong', {}, opz.scrivi)) : null, campo,
        h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => fine(false) }, NT.t('Annulla')), ok)));
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
  NT.oggiISO = () => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
  NT.dataDaMs = ms => { const d = new Date(ms); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
  NT.giorniTra = (a, b) => Math.round((new Date(b + 'T12:00:00') - new Date(a + 'T12:00:00')) / 86400000);
  NT.ls = {
    leggi: k => { try { return localStorage.getItem(k); } catch (e) { return null; } },
    scrivi: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* non disponibile */ } },
  };
  NT.debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

  /* spinner e segnaposto */
  NT.caricamento = (testo) => h('div', { class: 'caricamento' }, h('span', { class: 'spinner' }), testo || NT.t('Caricamento…'));
  NT.vuoto = (titolo, testo) => h('div', { class: 'vuoto' }, h('strong', {}, titolo), testo ? h('p', {}, testo) : null);

  /* Etichetta dell'esito dell'analisi (colori volutamente prudenti: "benigno" non e' mai verde rassicurante) */
  NT.ESITI = {
    attenzione: { testo: NT.t('Da attenzionare'), cls: 'esito-att' },
    discordante: { testo: NT.t('Metodi in disaccordo'), cls: 'esito-disc' },
    benigno: { testo: NT.t('Nessun allarme dai modelli'), cls: 'esito-ben' },
    nessuno: { testo: NT.t('Nessun risultato'), cls: 'esito-nes' },
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
          c.toBlob(b => b ? res(b) : rej(new Error(NT.t('Non riesco a ridurre questa immagine.'))), 'image/jpeg', 0.88);
        } catch (e) { rej(new Error(NT.t('Non riesco a leggere questa immagine. Prova con un JPG o un PNG.'))); }
        finally { URL.revokeObjectURL(url); }
      };
      img.onerror = () => { URL.revokeObjectURL(url); rej(new Error(NT.t('Non riesco a leggere questa immagine. Prova con un JPG o un PNG.'))); };
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
    } }, NT.t('Accetto e continuo'));
    spunta.addEventListener('change', () => { ok.disabled = !spunta.checked; });
    const d = NT.apriDialogo(h('div', { class: 'avvertenze' },
      h('h3', {}, NT.t('Prima di cominciare')),
      h('p', {}, h('strong', {}, NT.t('NeoTracker non è un dispositivo medico e non fa diagnosi.') + ' '),
        NT.t('È uno strumento personale per organizzare le foto dei tuoi nei e confrontare nel tempo i risultati di alcuni modelli di ricerca. Non è certificato né approvato da alcuna autorità sanitaria.')),
      h('ul', {},
        h('li', {}, NT.t('I risultati sono stime sperimentali e possono sbagliare in entrambe le direzioni: un esito rassicurante non esclude un melanoma, un esito di attenzione non significa che ci sia.')),
        h('li', {}, NT.t('Un neo che cambia (forma, bordi, colore, dimensioni), sanguina, prude o ti preoccupa va mostrato a un dermatologo, qualunque cosa dica l\'app. Il controllo periodico dal dermatologo resta insostituibile.')),
        h('li', {}, NT.t('Le informazioni su rischio, letteratura e genetica sono divulgative e non sostituiscono la consulenza di un medico o di un genetista.')),
        h('li', {}, NT.t('I dati (anche di salute) restano su questo computer. Escono solo le richieste che attivi tu: indice UV (coordinate approssimate), ricerche su PubMed (solo i termini cercati) e, solo se lo attivi, l\'invio della foto a SkinSense.')),
        h('li', {}, NT.t('Se inserisci dati o foto di altre persone, assicurati di avere il loro consenso.'))),
      h('label', { class: 'spunta grande' }, spunta, ' ' + NT.t('Ho letto e capito queste avvertenze')),
      h('div', { class: 'azioni' },
        h('button', { class: 'btn', onclick: () => { NT.api('POST', '/api/chiudi').catch(() => {}); NT.battitoAttivo = false; if (NT.presenza) NT.presenza.close(); document.title = NT.t('NeoTracker chiuso'); NT.chiudiDialogo(); } }, NT.t('Esci dal programma')),
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

    /* ---------------- lingua dell'interfaccia ---------------- */
    // 'auto' = la lingua del sistema; per applicare la scelta si salva e si ricarica la pagina
    const selLingua = h('select', { class: 'campo', id: 'sel-lingua', 'aria-label': NT.t('Lingua dell\'interfaccia'),
      onchange: async () => { if (await salva({ lingua: selLingua.value })) location.reload(); else selLingua.value = NT.linguaScelta; } },
      h('option', { value: 'auto' }, NT.t('Automatica (come il sistema)')),
      NT.LINGUE.map(l => h('option', { value: l[0] }, l[1])));
    selLingua.value = NT.linguaScelta;
    const sezLingua = h('section', { class: 'scheda' }, h('h2', {}, NT.t('Lingua')),
      h('label', { for: 'sel-lingua', class: 'blocco' }, NT.t('Lingua dell\'interfaccia')), selLingua,
      h('p', { class: 'piccolo muted' }, NT.t('La scelta vale per tutti gli utenti di questo computer. Il testo originale e vincolante delle avvertenze legali è quello italiano; il rapporto di testo completo resta in italiano.')));

    /* ---------------- indice UV: fonte dei dati ---------------- */
    const esitoProva = h('div', { class: 'prova-esito', role: 'status' });
    const campoChiave = h('input', { type: 'password', class: 'campo', autocomplete: 'off', spellcheck: 'false', maxlength: 64,
      placeholder: '', 'aria-label': NT.t('Chiave OpenWeather') });
    const segnapostoChiave = () => S.imp.ha_chiave_owm ? NT.t('Chiave salvata ({finale}) — scrivine una nuova per sostituirla', { finale: S.imp.chiave_owm_finale }) : NT.t('Incolla qui la chiave (32 lettere e numeri)');
    campoChiave.placeholder = segnapostoChiave();
    const sezOWM = h('section', { class: 'scheda' });
    function disegnaOWM() {
      campoChiave.placeholder = segnapostoChiave();
      const ow = S.imp.fonte_uv === 'openweather';
      // una riga con pallino: scegliere cambia subito la fonte e ridisegna la sezione
      const scelta = (valore, titolo, desc) => h('label', { class: 'riga-inline' },
        h('input', { type: 'radio', name: 'fonte-uv', value: valore, checked: S.imp.fonte_uv === valore,
          onchange: async () => { if (await salva({ fonte_uv: valore }, NT.t('Fonte dell\'indice UV cambiata.'))) { NT.riempi(esitoProva); disegnaOWM(); } } }),
        h('span', {}, h('strong', {}, titolo), ' ', h('span', { class: 'piccolo muted' }, desc)));
      NT.riempi(sezOWM, h('h2', {}, NT.t('Indice UV: fonte dei dati')),
        scelta('open-meteo', NT.t('Open-Meteo (predefinita)'), NT.t('gratuita, senza account né chiave')),
        scelta('openweather', 'OpenWeather', NT.t('facoltativa: richiede una tua chiave personale')),
        !ow ? h('p', { class: 'piccolo muted' }, NT.t('Dati meteo e UV:') + ' ', NT.link('https://open-meteo.com/', 'Open-Meteo.com'), ' ' + NT.t('(licenza CC BY 4.0). Il servizio gratuito è per uso personale e non commerciale.') + ' ',
          NT.t('Anche la ricerca delle città usa Open-Meteo.')) : null,
        ow ? h('div', { class: 'banda ' + (S.imp.ha_chiave_owm ? 'verde' : 'giallo') }, S.imp.ha_chiave_owm ? NT.t('Chiave OpenWeather salvata ({finale}).', { finale: S.imp.chiave_owm_finale }) : NT.t('Hai scelto OpenWeather ma non c\'è ancora una chiave: finché manca, il programma usa Open-Meteo.')) : null,
        ow ? h('div', { class: 'riga-inline' }, campoChiave,
          h('button', { class: 'btn btn-pri', onclick: async () => { const k = campoChiave.value.trim(); if (!k) { NT.toast(NT.t('Incolla prima la chiave.'), 'errore'); return; } if (await salva({ openweather_key: k }, NT.t('Chiave salvata.'))) { campoChiave.value = ''; NT.riempi(esitoProva); disegnaOWM(); } } }, NT.t('Salva')),
          S.imp.ha_chiave_owm ? h('button', { class: 'btn', onclick: provaChiave }, NT.t('Prova la chiave')) : null,
          S.imp.ha_chiave_owm ? h('button', { class: 'btn-testo pericolo', onclick: async () => { if (await NT.conferma(NT.t('Rimuovere la chiave?'), NT.t('La chiave sarà cancellata da questo computer. Potrai inserirla di nuovo quando vuoi.'), { si: NT.t('Rimuovi'), pericolo: true }) && await salva({ openweather_key: '' }, NT.t('Chiave rimossa.'))) { NT.riempi(esitoProva); disegnaOWM(); } } }, NT.t('Rimuovi')) : null) : null,
        ow ? esitoProva : null,
        ow ? h('details', { class: 'abstract' }, h('summary', {}, NT.t('Come ottenere la chiave')),
          h('ol', { class: 'passi' },
            h('li', {}, NT.t('Crea un account gratuito su') + ' ', NT.link('https://home.openweathermap.org/users/sign_up', 'openweathermap.org'), ' ' + NT.t('e conferma l\'email.')),
            h('li', {}, NT.t('Apri la pagina «API keys» del tuo account e copia la chiave.')),
            h('li', {}, NT.t('Iscriviti all\'abbonamento «One Call API» a pagamento per chiamata') + ' (', NT.link('https://openweathermap.org/api/one-call-4', NT.t('pagina del servizio')), '): ' + NT.t('le prime 1.000 chiamate al giorno sono gratuite, le successive si pagano. OpenWeather può chiedere una carta di pagamento per attivarlo: controlla le condizioni sul loro sito.')),
            h('li', {}, NT.t('Alla sottoscrizione il limite giornaliero predefinito è di 2.000 chiamate: nella scheda «Billing plans» del tuo account puoi abbassarlo a 1.000, così non spendi nulla. NeoTracker ne usa poche (al massimo 4 ogni 10 minuti, solo quando apri la pagina Indice UV).')),
            h('li', {}, NT.t('Incolla la chiave qui sopra e premi «Prova la chiave». Dopo l\'iscrizione la chiave può impiegare qualche minuto ad attivarsi. Il programma prova prima One Call 4.0 e, se la chiave è di un abbonamento più vecchio, One Call 3.0.'))),
          h('p', { class: 'piccolo muted' }, NT.t('La chiave resta salvata solo sul tuo computer e non viene mai mostrata né inviata alla pagina web del programma: la usa il programma Python per chiamare OpenWeather.'))) : null);
    }
    async function provaChiave() {
      NT.riempi(esitoProva, NT.caricamento(NT.t('Provo la chiave…')));
      try { const r = await NT.api('POST', '/api/impostazioni/prova-owm'); NT.riempi(esitoProva, h('div', { class: 'banda ' + (r.ok ? 'verde' : 'rosso') }, NT.tr(r.messaggio))); }
      catch (e) { NT.riempi(esitoProva, h('div', { class: 'banda rosso' }, e.message)); }
    }
    disegnaOWM();

    /* ---------------- analisi delle foto ---------------- */
    const swSkin = h('input', { type: 'checkbox', id: 'sw-skin', checked: !!S.imp.usa_skinsense, onchange: async () => {
      if (swSkin.checked) {
        const ok = await NT.conferma(NT.t('Inviare le foto a SkinSense?'), NT.t('SkinSense è un servizio online di terzi: le foto dei tuoi nei verrebbero inviate via internet a un server che non controlliamo. Le foto sono dati sulla tua salute. Vuoi abilitarlo?'), { si: NT.t('Sì, abilita') });
        if (!ok) { swSkin.checked = false; return; }
      }
      if (!await salva({ usa_skinsense: swSkin.checked }, swSkin.checked ? NT.t('SkinSense abilitato.') : NT.t('SkinSense disattivato.'))) swSkin.checked = !swSkin.checked;
    } });
    const sezAnalisi = h('section', { class: 'scheda' }, h('h2', {}, NT.t('Analisi delle foto')),
      h('label', { class: 'interruttore', for: 'sw-skin' }, swSkin, h('span', {}, h('strong', {}, NT.t('Usa anche SkinSense (servizio online)')),
        h('span', { class: 'piccolo muted blocco' }, NT.t('Spento per impostazione predefinita: con gli altri metodi la foto non lascia mai questo computer.')))),
      h('p', { class: 'piccolo muted' }, NT.t('Età, sesso e fenotipo non cambiano l\'uscita delle reti neurali: servono a mostrarti i fattori di rischio, a scegliere la letteratura, a valutare i criteri di genetica e a stimare il tempo di scottatura.')));

    /* ---------------- PubMed ---------------- */
    const campoMail = h('input', { type: 'email', class: 'campo', value: S.imp.ncbi_email || '', placeholder: NT.t('nome@esempio.it (facoltativa)'), maxlength: 120, autocomplete: 'email', 'aria-label': NT.t('Email per PubMed') });
    const sezMail = h('section', { class: 'scheda' }, h('h2', {}, NT.t('Letteratura: PubMed')),
      h('p', {}, NT.t('Le ricerche usano le E-utilities pubbliche di PubMed. NCBI chiede, per cortesia, un\'email di contatto: è facoltativa e viene inviata solo a PubMed.')),
      h('div', { class: 'riga-inline' }, campoMail, h('button', { class: 'btn', onclick: () => salva({ ncbi_email: campoMail.value }, NT.t('Email salvata.')) }, NT.t('Salva'))));

    /* ---------------- stato ---------------- */
    const st = S.stato;
    const sezStato = h('section', { class: 'scheda' }, h('h2', {}, NT.t('Stato dell\'installazione')),
      h('ul', { class: 'stato-lista' }, st.progetti.map(p => h('li', { class: p.presente ? 'si' : 'no' },
        h('span', { class: 'esito-criterio' }, p.presente ? NT.icona('ok', 16) : NT.icona('avviso', 16)), h('div', {}, h('strong', {}, NT.tr(p.nome)), h('div', { class: 'piccolo muted' }, NT.tr(p.dettaglio)))))),
      h('div', { class: 'piccolo' }, st.batch ? [NT.t('Programma di analisi:') + ' ', h('code', {}, st.batch)] : h('span', { class: 'errore-campo' }, NT.t('Programma di analisi (melanoma_batch.py) non trovato: le foto si salvano ma non si possono analizzare.'))),
      h('div', { class: 'piccolo' }, NT.t('Cartella dei progetti:') + ' ', h('code', {}, st.repo)),
      h('div', { class: 'piccolo' }, NT.t('Cartella dei tuoi dati (da copiare per il backup):') + ' ', h('code', {}, st.cartella_dati)),
      st.pillow_obsoleto ? h('div', { class: 'errore-campo' }, NT.t('La libreria Pillow è vecchia e ha problemi di sicurezza noti: aggiornala con «py -m pip install -U pillow».')) : null,
      h('div', { class: 'piccolo muted' }, NT.t('Versione') + ' ' + st.versione + (st.ha_pillow ? '' : ' · ' + NT.t('Pillow non installato: le anteprime useranno le foto originali (installa con «py -m pip install pillow»).'))));

    /* ---------------- chiusura ---------------- */
    const sezEsci = h('section', { class: 'scheda' }, h('h2', {}, NT.t('Chiudere il programma')),
      h('p', {}, NT.t('Per chiudere NeoTracker basta chiudere questa finestra con la X in alto a destra: il programma si spegne da solo.') + ' ' +
        NT.t('Se sta ancora analizzando una foto, finisce prima l\'analisi e poi si spegne. Il pulsante qui sotto fa la stessa cosa.')),
      h('button', { class: 'btn btn-pericolo', onclick: async () => {
        if (!await NT.conferma(NT.t('Chiudere NeoTracker?'), NT.t('Il programma si spegne. Un\'analisi in corso viene interrotta. I dati restano salvati.'), { si: NT.t('Chiudi il programma'), pericolo: true })) return;
        NT.battitoAttivo = false;
        if (NT.presenza) NT.presenza.close();       // non deve riconnettersi mentre il programma si spegne
        try { await NT.api('POST', '/api/chiudi'); } catch (e) { /* si sta spegnendo */ }
        NT.riempi(cont, h('div', { class: 'pagina stretta' }, h('div', { class: 'scheda' }, h('h2', {}, NT.t('NeoTracker è chiuso')), h('p', {}, NT.t('Puoi chiudere questa finestra. Per riaprirlo usa l\'icona «NeoTracker» sul Desktop.')))));
      } }, NT.icona('esci', 18), NT.t('Chiudi NeoTracker')));

    NT.riempi(cont, h('div', { class: 'pagina' }, h('h1', {}, NT.t('Impostazioni')), sezLingua, sezOWM, sezAnalisi, sezMail, sezStato, sezEsci));
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

  const SEDI_UTILI = [NT.m('palmo della mano'), NT.m('dorso della mano'), NT.m('pianta del piede'), NT.m('dorso del piede'), NT.m('spazio tra le dita'),
    NT.m('sotto l\'unghia (mano)'), NT.m('sotto l\'unghia (piede)'), NT.m('cuoio capelluto'), NT.m('orecchio'), NT.m('palpebra'), NT.m('labbro')];
  const GIORNI_PROMEMORIA = 90;

  let mappa = null, modo = 'lista', bozza = null, dett = null, fotoSel = null, pollTimer = null;
  let etichettaRegione = null, panel = null, formFotoAperto = false, sedeBozzaManuale = false;
  const inAnalisi = new Set();

  const nomiAuto = () => new Set(['fronte', 'retro'].flatMap(v => window.Corpo.regioni(v).map(r => r.nome)));
  /* Le sedi della mappa e quelle suggerite si salvano sempre in italiano (così funzionano in tutte le lingue);
     l'utente le vede e le scrive nella sua lingua: qui si torna dal testo tradotto a quello italiano. */
  const sedeCanonica = (() => {
    let inverso = null;
    return testo => {
      const v = String(testo || '').trim();
      if (NT.lingua === 'it') return v;
      if (!inverso) inverso = new Map([...nomiAuto(), ...SEDI_UTILI].map(s => [NT.tr(s), s]));
      return inverso.get(v) || v;
    };
  })();
  const opzioniSedi = () => SEDI_UTILI.map(s => h('option', { value: NT.tr(s) }));
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
      NT.icona('mirino', 18), NT.t('Aggiungi neo'));
    const suggerimento = h('span', { class: 'mappa-hint', id: 'mappa-hint' }, NT.t('Rotella = zoom · trascina = sposta · doppio clic = ingrandisci'));
    const barra = h('div', { class: 'mappa-barra' }, btnAggiungi, suggerimento,
      h('span', { class: 'spazio' }),
      h('button', { class: 'btn-icona', title: NT.t('Riduci'), onclick: () => mappa.zoomSu(1 / 1.5) }, NT.icona('meno')),
      h('button', { class: 'btn-icona', title: NT.t('Ingrandisci'), onclick: () => mappa.zoomSu(1.5) }, NT.icona('piu')),
      h('button', { class: 'btn-icona', title: NT.t('Mostra tutto il corpo'), onclick: () => mappa.reset() }, NT.icona('reset')));
    const box = h('div', { class: 'mappa-box' });
    etichettaRegione = h('div', { class: 'regione-etichetta' }, NT.t('Passa il puntatore sul corpo per vedere la zona'));
    const legenda = h('div', { class: 'legenda' },
      h('span', {}, h('i', { class: 'pallino pieno' }), NT.t('Neo con foto')),
      h('span', {}, h('i', { class: 'pallino vuoto' }), NT.t('Ancora nessuna foto')),
      h('span', {}, h('i', { class: 'pallino rosso' }), NT.t('Analisi: da attenzionare')),
      h('span', { class: 'lato-nota' }, NT.t('D = destra del paziente · S = sinistra')));
    panel = h('aside', { class: 'pannello', 'aria-live': 'polite' });
    cont.replaceChildren(h('div', { class: 'mappa-layout' }, h('section', { class: 'scheda mappa-scheda' }, barra, box, etichettaRegione, legenda), panel));

    mappa = new window.Corpo.MappaCorpo(box, {
      onRegione: nome => { etichettaRegione.textContent = nome ? NT.tr(nome) : NT.t('Passa il puntatore sul corpo per vedere la zona'); },
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
    if (hint) hint.textContent = on ? NT.t('Clicca sul punto esatto del corpo dove si trova il neo (puoi ingrandire prima)') : NT.t('Rotella = zoom · trascina = sposta · doppio clic = ingrandisci');
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
    if (c && bozza) c.value = bozza.regione ? NT.tr(bozza.regione) : '';
    const info = $('#info-pos-bozza');
    if (info && bozza) info.textContent = testoPos(bozza);
  }
  const testoPos = p => NT.t('{vista} · posizione {x}% da sinistra, {y}% dall\'alto',
    { vista: p.vista === 'fronte' ? NT.t('Fronte') : NT.t('Retro'), x: Math.round(p.x * 100), y: Math.round(p.y * 100) });

  function pannelloBozza() {
    const nome = h('input', { type: 'text', class: 'campo', maxlength: 60, value: NT.t('Neo {n}', { n: S.nei.length + 1 }), id: 'campo-nome-bozza' });
    const sede = h('input', { type: 'text', class: 'campo', maxlength: 80, list: 'sedi-utili', value: bozza.regione ? NT.tr(bozza.regione) : '', id: 'campo-sede-bozza',
      oninput: () => { sedeBozzaManuale = true; } });
    const note = h('textarea', { class: 'campo', rows: 3, maxlength: 1000, placeholder: NT.t('Quando l\'hai notato, se prude, se è cambiato…') });
    const salva = h('button', { class: 'btn btn-pri', onclick: async () => {
      salva.disabled = true;
      try {
        const r = await NT.api('POST', '/api/utenti/' + S.utente.id + '/nevi',
          { nome: nome.value, vista: bozza.vista, x: bozza.x, y: bozza.y, regione: sedeCanonica(sede.value), note: note.value });
        await NT.ricaricaNei();
        bozza = null; mappa.setBozza(null);
        formFotoAperto = true;
        await selezionaNeo(r.id);
        NT.toast(NT.t('Neo salvato. Ora aggiungi la prima foto: sarà la tua "foto storica".'), 'ok');
      } catch (e) { salva.disabled = false; NT.errore(e); }
    } }, NT.t('Salva neo'));
    return h('div', { class: 'scheda' },
      h('h2', {}, NT.t('Nuovo neo')),
      h('p', { class: 'piccolo', id: 'info-pos-bozza' }, testoPos(bozza)),
      h('p', { class: 'piccolo' }, NT.icona('mirino', 14), ' ' + NT.t('Trascina il pallino sulla mappa per correggere la posizione; ingrandisci con la rotella per la massima precisione.')),
      h('label', { class: 'etichetta' }, NT.t('Nome'), nome),
      h('label', { class: 'etichetta' }, NT.t('Sede (modificabile)'), sede,
        h('datalist', { id: 'sedi-utili' }, opzioniSedi())),
      h('label', { class: 'etichetta' }, NT.t('Note'), note),
      h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => tornaLista() }, NT.t('Annulla')), salva));
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
      NT.toast(corpo.regione ? NT.t('Posizione aggiornata: {regione}.', { regione: NT.tr(corpo.regione) }) : NT.t('Posizione aggiornata.'), 'ok');
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
        h('span', { class: 'sotto' }, n.regione ? NT.tr(n.regione) : (n.vista === 'fronte' ? NT.t('Fronte') : NT.t('Retro'))),
        h('span', { class: 'sotto' }, n.n_foto === 0 ? NT.t('Nessuna foto: aggiungi la prima')
          : NT.t('{foto} · ultima {quando}', { foto: NT.tp(n.n_foto, '{n} foto', '{n} foto'), quando: NT.fraseGiorni(giorni) })),
        h('span', { class: 'chips' }, NT.chipEsito(n.ultimo_esito), promemoria ? h('span', { class: 'chip chip-neutro' }, NT.t('Da rifotografare?')) : null)));
  }

  function pannelloLista() {
    const lista = attivi(), arch = S.nei.filter(n => n.archiviato);
    const vuoto = !S.nei.length;
    return h('div', { class: 'scheda' },
      h('div', { class: 'testa-lista' }, h('h2', {}, vuoto ? NT.t('Nessun neo ancora') : NT.t('I tuoi nei ({n})', { n: lista.length })),
        lista.length ? h('button', { class: 'btn-testo', title: NT.t('Stampa una scheda con tutti i nei'), onclick: () => NT.stampaNei(lista.map(n => n.id)) }, NT.icona('stampa', 16), NT.t('Scheda per il dermatologo')) : null),
      vuoto
        ? h('ol', { class: 'passi' },
          h('li', {}, NT.t('Premi'), ' ', h('strong', {}, NT.t('Aggiungi neo')), ' ' + NT.t('e clicca sul punto esatto del corpo (ingrandisci con la rotella per essere più preciso).')),
          h('li', {}, NT.t('Dai un nome al neo e controlla la sede.')),
          h('li', {}, NT.t('Aggiungi la prima foto: diventa la tua foto storica, e ogni foto successiva ne seguirà l\'evoluzione.')))
        : h('div', { class: 'neo-elenco' }, lista.map(schedaLista)),
      arch.length ? h('details', { class: 'archiviati' }, h('summary', {}, NT.t('Nei archiviati ({n})', { n: arch.length })),
        arch.map(n => h('div', { class: 'riga-arch' }, h('span', {}, n.nome + (n.regione ? ' – ' + NT.tr(n.regione) : '')),
          h('button', { class: 'btn-testo', onclick: async () => { try { await NT.api('PATCH', '/api/nevi/' + n.id, { archiviato: false }); await NT.ricaricaNei(); aggiornaMarcatori(); renderPannello(); } catch (e) { NT.errore(e); } } }, NT.t('Ripristina'))))) : null,
      !vuoto ? h('p', { class: 'piccolo muted' }, NT.t('Clicca un neo nell\'elenco o sulla mappa per vedere lo storico fotografico.')) : null);
  }

  /* ------------------------------ dettaglio neo ------------------------------ */
  function pannelloNeo() {
    const n = dett.nevo, foto = dett.foto;
    const salva = async (campi) => { try { await NT.api('PATCH', '/api/nevi/' + n.id, campi); await ricaricaDettaglio(); } catch (e) { NT.errore(e); } };

    const nome = h('input', { type: 'text', class: 'campo titolo-modifica', maxlength: 60, value: n.nome, 'aria-label': NT.t('Nome del neo'),
      onchange: () => { if (nome.value.trim()) salva({ nome: nome.value }); else nome.value = n.nome; } });
    const sede = h('input', { type: 'text', class: 'campo', maxlength: 80, list: 'sedi-utili', value: n.regione ? NT.tr(n.regione) : '', placeholder: NT.t('Sede'),
      onchange: () => salva({ regione: sedeCanonica(sede.value) }) });
    const note = h('textarea', { class: 'campo', rows: 2, maxlength: 1000, placeholder: NT.t('Note sul neo…'), onchange: () => salva({ note: note.value }) }, n.note);

    const testa = h('div', { class: 'scheda' },
      h('div', { class: 'neo-testa' },
        h('button', { class: 'btn-testo', onclick: () => tornaLista() }, NT.t('← Tutti i nei')),
        h('span', { class: 'spazio' }),
        h('button', { class: 'btn-icona', title: NT.t('Centra sulla mappa'), onclick: () => mappa.centraSu(n, 5) }, NT.icona('mirino')),
        h('button', { class: 'btn-icona', title: NT.t('Stampa la scheda di questo neo'), onclick: () => NT.stampaNei([n.id]) }, NT.icona('stampa')),
        h('button', { class: 'btn-icona', title: NT.t('Archivia (toglie dalla mappa, conserva i dati)'), onclick: async () => {
          await salva({ archiviato: true }); tornaLista(); NT.toast(NT.t('Neo archiviato. Lo trovi in fondo all\'elenco.'), 'ok'); } }, NT.icona('archivio')),
        h('button', { class: 'btn-icona pericolo', title: NT.t('Elimina questo neo e le sue foto'), onclick: async () => {
          const si = await NT.conferma(NT.t('Eliminare «{nome}»?', { nome: n.nome }),
            NT.tp(foto.length, 'Verranno cancellate per sempre la sua unica foto e i rapporti di analisi.', 'Verranno cancellate per sempre tutte le sue {n} foto e i rapporti di analisi.'),
            { si: NT.t('Elimina'), pericolo: true, scrivi: foto.length ? n.nome : null });
          if (!si) return;
          try { await NT.api('DELETE', '/api/nevi/' + n.id); await NT.ricaricaNei(); tornaLista(); NT.toast(NT.t('Neo eliminato.'), 'ok'); } catch (e) { NT.errore(e); } } }, NT.icona('cestino'))),
      h('div', { class: 'neo-titolo' }, h('span', { class: 'neo-num grande' + (foto.length ? '' : ' vuoto') }, numDi(n.id)), nome),
      h('div', { class: 'riga-2' }, h('label', { class: 'etichetta' }, NT.t('Sede'), sede,
        h('datalist', { id: 'sedi-utili' }, opzioniSedi())),
        h('div', { class: 'etichetta' }, NT.t('Posizione'), h('div', { class: 'piccolo' }, testoPos(n), h('br'), NT.t('Trascina il pallino sulla mappa per spostarlo.')))),
      h('label', { class: 'etichetta' }, NT.t('Note'), note));

    const sezioni = [testa, sezioneStorico(n, foto), formFoto(n)];
    const grafico = graficoDiametro(foto);
    if (grafico) sezioni.push(grafico);
    sezioni.push(h('div', { class: 'scheda', id: 'box-analisi' }, h('h3', {}, NT.t('Analisi automatica')), NT.caricamento(NT.t('Controllo lo stato…'))));
    return h('div', { class: 'pila' }, sezioni);
  }

  /* ----------------------------- storico fotografico ----------------------------- */
  function sezioneStorico(n, foto) {
    if (!foto.length) {
      return h('div', { class: 'scheda' }, h('h3', {}, NT.t('Storico fotografico')),
        NT.vuoto(NT.t('Ancora nessuna foto'), NT.t('Aggiungi qui sotto la prima foto: sarà il punto di partenza per vedere se il neo cambia nel tempo.')));
    }
    const f = foto.find(x => x.id === fotoSel) || foto[foto.length - 1];
    const striscia = h('div', { class: 'striscia' }, foto.map(x => h('button', { class: 'miniatura' + (x.id === f.id ? ' sel' : ''), title: NT.fmtData(x.scattata_il) + (x.diametro_mm ? ' · ' + NT.num(x.diametro_mm) + ' mm' : ''),
      onclick: () => { fotoSel = x.id; renderPannello(); } },
      h('img', { src: '/foto/' + x.id + '/mini?l=240', alt: NT.t('Foto del {data}', { data: NT.fmtData(x.scattata_il) }), loading: 'lazy' }),
      h('span', { class: 'data' }, NT.fmtData(x.scattata_il)),
      x.esito && x.esito !== 'nessuno' ? h('i', { class: 'punto-esito ' + NT.ESITI[x.esito].cls, title: NT.ESITI[x.esito].testo }) : null)));
    const precedente = foto[foto.indexOf(f) - 1];
    const meta = h('div', { class: 'foto-meta' },
      h('span', {}, h('strong', {}, NT.fmtData(f.scattata_il)), ' · ', f.tipo === 'dermoscopica' ? NT.t('dermoscopica') : NT.t('foto normale')),
      f.diametro_mm ? h('span', {}, NT.t('Diametro:') + ' ', h('strong', {}, NT.num(f.diametro_mm) + ' mm'),
        precedente && precedente.diametro_mm ? h('span', { class: 'delta' }, ' ' + NT.t('({variazione} mm dalla foto precedente)', { variazione: (f.diametro_mm - precedente.diametro_mm >= 0 ? '+' : '') + NT.num(f.diametro_mm - precedente.diametro_mm) })) : null) : null,
      f.note ? h('span', { class: 'muted' }, f.note) : null);
    return h('div', { class: 'scheda' },
      h('div', { class: 'testa-lista' }, h('h3', {}, NT.t('Storico fotografico ({n})', { n: foto.length })),
        foto.length >= 2 ? h('button', { class: 'btn-testo', onclick: () => dialogoConfronto(foto, f) }, NT.icona('confronta', 16), NT.t('Confronta')) : null),
      striscia,
      h('button', { class: 'anteprima', title: NT.t('Clic per vedere la foto originale a schermo intero'), onclick: () => apriLightbox(f) },
        h('img', { src: '/foto/' + f.id + '/mini?l=960', alt: NT.t('Foto del {data}', { data: NT.fmtData(f.scattata_il) }) })),
      meta,
      h('div', { class: 'azioni-foto' },
        h('button', { class: 'btn-testo', onclick: () => dialogoModificaFoto(f) }, NT.t('Modifica data/misura')),
        h('button', { class: 'btn-testo pericolo', onclick: async () => {
          const si = await NT.conferma(NT.t('Eliminare questa foto?'), NT.t('La foto del {data} e il suo rapporto di analisi saranno cancellati per sempre.', { data: NT.fmtData(f.scattata_il) }), { si: NT.t('Elimina foto'), pericolo: true });
          if (!si) return;
          try { await NT.api('DELETE', '/api/foto/' + f.id); await ricaricaDettaglio(); fotoSel = dett.foto.length ? dett.foto[dett.foto.length - 1].id : null; renderPannello(); NT.toast(NT.t('Foto eliminata.'), 'ok'); } catch (e) { NT.errore(e); } } }, NT.t('Elimina foto'))));
  }

  function apriLightbox(f) {
    const d = $('#lightbox');
    d.replaceChildren(h('div', { class: 'lb' },
      h('div', { class: 'lb-barra' }, h('strong', {}, NT.fmtData(f.scattata_il)), h('span', { class: 'spazio' }), h('button', { class: 'btn', onclick: () => d.close() }, NT.t('Chiudi'))),
      h('img', { src: '/foto/' + f.id + '/originale', alt: NT.t('Foto originale') })));
    d.showModal();
  }

  function dialogoModificaFoto(f) {
    const data = h('input', { type: 'date', class: 'campo', value: f.scattata_il, max: NT.oggiISO() });
    const diam = h('input', { type: 'text', class: 'campo', inputmode: 'decimal', value: f.diametro_mm === null ? '' : NT.num(f.diametro_mm), placeholder: NT.t('es. 4,5') });
    const tipo = h('select', { class: 'campo' }, h('option', { value: 'normale', selected: f.tipo === 'normale' }, NT.t('Foto normale')), h('option', { value: 'dermoscopica', selected: f.tipo === 'dermoscopica' }, NT.t('Dermoscopica')));
    const nota = h('textarea', { class: 'campo', rows: 2, maxlength: 1000 }, f.note);
    NT.apriDialogo(h('div', {}, h('h3', {}, NT.t('Modifica foto')),
      h('label', { class: 'etichetta' }, NT.t('Data dello scatto'), data), h('label', { class: 'etichetta' }, NT.t('Diametro (mm)'), diam),
      h('label', { class: 'etichetta' }, NT.t('Tipo'), tipo), h('label', { class: 'etichetta' }, NT.t('Note'), nota),
      h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => NT.chiudiDialogo() }, NT.t('Annulla')),
        h('button', { class: 'btn btn-pri', onclick: async () => {
          try {
            await NT.api('PATCH', '/api/foto/' + f.id, { scattata_il: data.value, diametro_mm: diam.value, tipo: tipo.value, note: nota.value });
            NT.chiudiDialogo(); await ricaricaDettaglio(); renderPannello();
          } catch (e) { NT.errore(e); }
        } }, NT.t('Salva')))));
  }

  /* ----------------------------- aggiunta di una foto ----------------------------- */
  function formFoto(n) {
    let file = null;
    const anteprima = h('div', { class: 'drop-testo' }, NT.icona('foto', 26), h('span', {}, NT.t('Trascina qui una foto oppure clicca per sceglierla')), h('small', {}, NT.t('JPG, PNG, WEBP o BMP · fino a 60 MB')));
    const input = h('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp,image/bmp,.jpg,.jpeg,.png,.webp,.bmp', class: 'nascosto' });
    const drop = h('label', { class: 'drop' }, input, anteprima);
    const data = h('input', { type: 'date', class: 'campo', value: NT.oggiISO(), max: NT.oggiISO(), oninput: () => { usaExif.checked = false; } });
    const usaExif = h('input', { type: 'checkbox', checked: true });
    const tipo = h('select', { class: 'campo' }, h('option', { value: 'normale' }, NT.t('Foto normale (smartphone)')), h('option', { value: 'dermoscopica' }, NT.t('Dermoscopica')));
    const diam = h('input', { type: 'text', class: 'campo', inputmode: 'decimal', placeholder: NT.t('es. 4,5') });
    const nota = h('input', { type: 'text', class: 'campo', maxlength: 1000, placeholder: NT.t('Facoltativa') });
    const analizza = h('input', { type: 'checkbox', checked: true });
    const btn = h('button', { class: 'btn btn-pri', disabled: true }, NT.icona('foto', 18), NT.t('Salva foto'));

    function scegli(fl) {
      if (!fl) return;
      if (!/^image\//.test(fl.type) && !/\.(jpe?g|png|webp|bmp)$/i.test(fl.name)) { NT.toast(NT.t('Scegli un file immagine (JPG, PNG, WEBP o BMP).'), 'errore'); return; }
      if (fl.size > (S.stato.max_mb_foto || 60) * 1048576) { NT.toast(NT.t('La foto supera i {mb} MB: riducila o scegline un\'altra.', { mb: S.stato.max_mb_foto || 60 }), 'errore'); return; }
      file = fl;
      data.value = NT.dataDaMs(fl.lastModified); usaExif.checked = true;
      const url = URL.createObjectURL(fl);
      anteprima.replaceChildren(h('img', { src: url, alt: NT.t('Anteprima'), class: 'drop-img' }), h('small', {}, NT.t('{nome} · {mb} MB · clicca per cambiare', { nome: fl.name, mb: NT.num(fl.size / 1048576) })));
      btn.disabled = false;
    }
    input.addEventListener('change', () => scegli(input.files[0]));
    ['dragenter', 'dragover'].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.add('sopra'); }));
    ['dragleave', 'drop'].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.remove('sopra'); }));
    drop.addEventListener('drop', ev => scegli(ev.dataTransfer.files[0]));

    btn.addEventListener('click', async () => {
      if (!file) return;
      btn.disabled = true; btn.replaceChildren(h('span', { class: 'spinner' }), NT.t('Salvataggio…'));
      const q = new URLSearchParams({ data: data.value, exif: usaExif.checked ? '1' : '0', tipo: tipo.value, diametro: diam.value, note: nota.value, analizza: analizza.checked ? '1' : '0' });
      try {
        const r = await NT.api('POST', '/api/nevi/' + n.id + '/foto?' + q.toString(), null, { raw: file, tipo: file.type || 'application/octet-stream' });
        formFotoAperto = false;
        await ricaricaDettaglio();
        fotoSel = r.id;
        renderPannello();
        NT.toast((r.da_exif ? NT.t('Foto salvata ({data}, data letta dalla foto).', { data: NT.fmtData(r.scattata_il) }) : NT.t('Foto salvata ({data}).', { data: NT.fmtData(r.scattata_il) }))
          + (r.analisi_errore ? ' ' + NT.tr(r.analisi_errore) : ''), r.analisi_errore ? 'errore' : 'ok');
      } catch (e) { btn.disabled = false; btn.replaceChildren(NT.icona('foto', 18), NT.t('Salva foto')); NT.errore(e); }
    });

    const det = h('details', { class: 'scheda form-foto', open: formFotoAperto || dett.foto.length === 0 },
      h('summary', {}, NT.icona('piu', 16), NT.t('Aggiungi una foto allo storico')),
      h('div', { class: 'form-corpo' }, drop,
        h('div', { class: 'riga-2' },
          h('label', { class: 'etichetta' }, NT.t('Data dello scatto'), data,
            h('span', { class: 'spunta' }, usaExif, ' ' + NT.t('Usa la data scritta nella foto, se c\'è'))),
          h('label', { class: 'etichetta' }, NT.t('Diametro misurato (mm)'), diam)),
        h('div', { class: 'riga-2' }, h('label', { class: 'etichetta' }, NT.t('Tipo di foto'), tipo), h('label', { class: 'etichetta' }, NT.t('Note'), nota)),
        h('label', { class: 'spunta grande' }, analizza, ' ' + NT.t('Analizza subito con tutti i metodi installati')),
        h('details', { class: 'consigli' }, h('summary', {}, NT.t('Come scattare foto confrontabili')),
          h('ul', {}, h('li', {}, NT.t('Stessa luce (luce del giorno, senza flash) e stessa distanza ogni volta, circa 10-15 cm.')),
            h('li', {}, NT.t('Metti accanto al neo un righello o una moneta: serve per misurare il diametro.')),
            h('li', {}, NT.t('Foto a fuoco, con il neo al centro e la pelle ben visibile (sposta i peli, se serve).')),
            h('li', {}, NT.t('Scatta sempre dalla stessa angolazione e salva l\'originale, senza filtri.')))),
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
    let s = '<svg viewBox="0 0 ' + L + ' ' + A + '" class="grafico" role="img" aria-label="' + NT.esc(NT.t('Diametro del neo nel tempo')) + '">';
    for (let v = 0; v <= vmax; v += passo) s += '<line x1="' + ml + '" x2="' + (L - mr) + '" y1="' + Y(v) + '" y2="' + Y(v) + '" class="gl"/><text x="' + (ml - 6) + '" y="' + (Y(v) + 4) + '" text-anchor="end" class="gt">' + v + '</text>';
    s += '<line x1="' + ml + '" x2="' + (L - mr) + '" y1="' + Y(6) + '" y2="' + Y(6) + '" class="g6"/><text x="' + (L - mr) + '" y="' + (Y(6) - 4) + '" text-anchor="end" class="gt g6t">6 mm</text>';
    s += '<polyline class="gline" points="' + pt.map(p => X(p.d) + ',' + Y(p.v)).join(' ') + '"/>';
    pt.forEach(p => { s += '<circle cx="' + X(p.d) + '" cy="' + Y(p.v) + '" r="4.5" class="gp"><title>' + NT.fmtData(p.d) + ': ' + NT.num(p.v) + ' mm</title></circle>'; });
    s += '<text x="' + X(pt[0].d) + '" y="' + (A - 10) + '" text-anchor="start" class="gt">' + NT.fmtData(pt[0].d) + '</text>';
    s += '<text x="' + X(pt[pt.length - 1].d) + '" y="' + (A - 10) + '" text-anchor="end" class="gt">' + NT.fmtData(pt[pt.length - 1].d) + '</text></svg>';
    const diff = pt[pt.length - 1].v - pt[0].v, giorni = NT.giorniTra(pt[0].d, pt[pt.length - 1].d);
    return h('div', { class: 'scheda' }, h('h3', {}, NT.t('Diametro nel tempo')), NT.html(s),
      h('p', { class: 'piccolo' }, NT.t('Variazione:') + ' ', h('strong', {}, (diff >= 0 ? '+' : '') + NT.num(diff) + ' mm'), ' ' + NT.tp(giorni, 'in {n} giorno.', 'in {n} giorni.') + ' ',
        NT.t('Sono misure inserite da te: valgono se prese sempre allo stesso modo. Un neo che cresce o cambia è un buon motivo per farlo vedere al dermatologo; la linea a 6 mm è solo il riferimento classico dei criteri ABCDE.')),
      h('button', { class: 'btn-testo', onclick: dialogoABCDE }, NT.t('Promemoria ABCDE')));
  }

  function dialogoABCDE() {
    const voci = [['A', NT.t('Asimmetria'), NT.t('Le due metà del neo non si somigliano.')], ['B', NT.t('Bordi'), NT.t('Irregolari, frastagliati o sfumati.')],
      ['C', NT.t('Colore'), NT.t('Più colori nello stesso neo (marrone, nero, rosso, blu, bianco).')], ['D', NT.t('Diametro'), NT.t('Più di 6 mm (ma esistono melanomi più piccoli).')],
      ['E', NT.t('Evoluzione'), NT.t('Cambia nel tempo: forma, colore, dimensione, rilievo, o compaiono prurito o sanguinamento.')]];
    NT.apriDialogo(h('div', {}, h('h3', {}, NT.t('Promemoria ABCDE')),
      h('ul', { class: 'abcde' }, voci.map(([l, t, d]) => h('li', {}, h('b', {}, l), h('span', {}, h('strong', {}, t), ' – ', d)))),
      h('p', { class: 'piccolo' }, NT.t('Conta anche il «brutto anatroccolo»: un neo diverso da tutti gli altri. I noduli che crescono rapidamente o sono duri al tatto vanno mostrati subito. Questo promemoria non sostituisce la visita.')),
      h('div', { class: 'azioni' }, h('button', { class: 'btn btn-pri', onclick: () => NT.chiudiDialogo() }, NT.t('Chiudi')))));
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
    const modoBtn = h('button', { class: 'btn', onclick: () => { sovrapposto = !sovrapposto; modoBtn.textContent = sovrapposto ? NT.t('Mostra affiancate') : NT.t('Sovrapponi con cursore'); ridisegna(); } }, NT.t('Sovrapponi con cursore'));
    function ridisegna() {
      const giorni = NT.giorniTra(a.scattata_il, b.scattata_il);
      const dd = (a.diametro_mm && b.diametro_mm) ? ' ' + NT.t('Diametro: {diff} mm di differenza.', { diff: NT.num(b.diametro_mm - a.diametro_mm) }) : '';
      const nota = h('p', { class: 'piccolo' }, NT.tp(Math.abs(giorni), 'Tra le due foto è passato {n} giorno.', 'Tra le due foto sono passati {n} giorni.') + dd + ' ' + NT.t('Confronta forma, bordi e colori: se noti differenze, mostra le foto al dermatologo.'));
      if (!sovrapposto) {
        area.replaceChildren(h('div', { class: 'confronto-coppia' },
          h('figure', {}, h('img', { src: '/foto/' + a.id + '/mini?l=960', alt: '' }), h('figcaption', {}, etich(a))),
          h('figure', {}, h('img', { src: '/foto/' + b.id + '/mini?l=960', alt: '' }), h('figcaption', {}, etich(b)))), nota);
      } else {
        const top = h('img', { src: '/foto/' + a.id + '/mini?l=960', alt: '', class: 'sopra', style: { clipPath: 'inset(0 ' + (100 - posizione) + '% 0 0)' } });
        const cur = h('input', { type: 'range', min: 0, max: 100, value: posizione, 'aria-label': NT.t('Cursore di confronto'), oninput: () => { posizione = +cur.value; top.style.clipPath = 'inset(0 ' + (100 - posizione) + '% 0 0)'; } });
        area.replaceChildren(h('div', { class: 'sovrapposte' }, h('img', { src: '/foto/' + b.id + '/mini?l=960', alt: '' }), top),
          cur, h('div', { class: 'didascalie' }, h('span', {}, '← ' + etich(a)), h('span', {}, etich(b) + ' →')), nota);
      }
    }
    ridisegna();
    NT.apriDialogo(h('div', {}, h('h3', {}, NT.t('Confronto tra due foto')),
      h('div', { class: 'riga-2' }, h('label', { class: 'etichetta' }, NT.t('Prima'), selA), h('label', { class: 'etichetta' }, NT.t('Dopo'), selB)),
      modoBtn, area, h('div', { class: 'azioni' }, h('button', { class: 'btn btn-pri', onclick: () => NT.chiudiDialogo() }, NT.t('Chiudi')))), true);
  }

  /* ------------------------------ analisi automatica ------------------------------ */
  async function caricaAnalisi(fotoId) {
    const box = $('#box-analisi');
    if (!box || fotoId !== fotoSel) return;
    let st;
    try { st = await NT.get('/api/foto/' + fotoId + '/analisi'); } catch (e) { box.replaceChildren(h('h3', {}, NT.t('Analisi automatica')), h('p', { class: 'errore-campo' }, e.message)); return; }
    if (fotoId !== fotoSel || !$('#box-analisi')) return;
    const attiva = st.stato === 'in_coda' || st.stato === 'in_corso';
    if (attiva) inAnalisi.add(fotoId);
    else if (inAnalisi.has(fotoId)) {                          // appena finita: aggiorno elenco e pallini
      inAnalisi.delete(fotoId);
      await ricaricaDettaglio();
      renderPannello();
      return;
    }
    box.replaceChildren(h('h3', {}, NT.t('Analisi automatica')), contenutoAnalisi(fotoId, st));
    if (attiva) pollTimer = setTimeout(() => caricaAnalisi(fotoId), 3000);
  }

  async function avviaAnalisi(fotoId) {
    try { await NT.api('POST', '/api/foto/' + fotoId + '/analizza'); inAnalisi.add(fotoId); caricaAnalisi(fotoId); } catch (e) { NT.errore(e); }
  }

  function contenutoAnalisi(fotoId, st) {
    if (st.stato === 'nessuna') {
      return h('div', {}, h('p', {}, NT.t('Questa foto non è ancora stata analizzata. L\'analisi confronta più metodi sulla stessa immagine e ti dice cosa ha risposto ciascuno.')),
        h('p', { class: 'piccolo muted' }, NT.t('La prima analisi può richiedere diversi minuti (i modelli vengono caricati in memoria).') + ' ' +
          (st.skinsense_attivo ? NT.t('SkinSense è attivo: la foto (senza metadati) verrà inviata a un servizio online.') : NT.t('La foto resta sul tuo computer: SkinSense (servizio online) è disattivato.'))),
        h('button', { class: 'btn btn-pri', onclick: () => avviaAnalisi(fotoId) }, NT.t('Analizza questa foto')));
    }
    if (st.stato === 'in_coda' || st.stato === 'in_corso') {
      return h('div', { class: 'analisi-attesa' }, h('div', { class: 'riga-spinner' }, h('span', { class: 'spinner grande' }),
        h('div', {}, h('strong', {}, st.stato === 'in_coda' ? (st.posizione_coda > 0 ? NT.t('In coda (posizione {n})…', { n: st.posizione_coda }) : NT.t('In coda…')) : NT.t('Analisi in corso…')),
          h('p', { class: 'piccolo muted' }, NT.t('Puoi continuare a usare l\'app. Se chiudi la finestra l\'analisi non va persa: il programma finisce il lavoro e poi si spegne da solo.')))),
        st.avanzamento && st.avanzamento.length ? h('pre', { class: 'log' }, st.avanzamento.join('\n')) : null);
    }
    if (st.stato === 'errore') {
      return h('div', {}, h('p', { class: 'errore-campo' }, st.messaggio ? NT.tr(st.messaggio) : NT.t('L\'analisi non è riuscita.')),
        h('button', { class: 'btn', onclick: () => avviaAnalisi(fotoId) }, NT.t('Riprova')));
    }
    return renderSintesi(st.sintesi, fotoId);
  }

  const GIUDIZIO_NESSUNO = NT.t('Nessun metodo ha prodotto un risultato: controlla i motivi indicati sotto.');
  const GIUDIZIO_ATT = NT.t('Almeno un metodo (o un suo modello) segnala una lesione da attenzionare. Non è una diagnosi e questi strumenti sbagliano spesso, ma è un motivo in più per non rimandare la visita dermatologica e per portare questo rapporto.');
  const GIUDIZIO_BEN = NT.t('Nessuno dei metodi che hanno risposto segnala la lesione come sospetta. Questo NON esclude un melanoma: gli strumenti non sono validati clinicamente e sbagliano anche in questa direzione. Se il neo è asimmetrico, ha bordi irregolari, colori diversi, è più grande di 6 mm o è cambiato nel tempo, la visita resta necessaria.');
  const AVVERTENZE = [
    NT.t('Questo rapporto NON è una diagnosi. I programmi usati sono prototipi di ricerca, non dispositivi medici.'),
    NT.t('I metodi sono addestrati su fotografie diverse dalle tue: cambiare luce, distanza o fotocamera può cambiare la risposta.'),
    NT.t('Fototipo, età e familiarità non cambiano il risultato delle reti neurali (guardano solo i pixel): servono a contestualizzare il rischio.'),
    NT.t('Se i metodi sono in disaccordo è normale: significa solo che nessuno di loro è affidabile da solo.'),
  ];

  /* Etichetta di un modello, come "NEV (nevo, cioe' neo benigno)": il codice resta, la descrizione si traduce. */
  function etichettaRisultato(testo) {
    const m = /^([A-Z]{3}) \((.+)\)$/.exec(testo || '');
    return m ? m[1] + ' (' + NT.tr(m[2]) + ')' : NT.tr(testo);
  }

  /* "4 su 5: NEV (...); 1 su 5: MEL (...)" - il conteggio dei risultati uguali, nella lingua scelta */
  function fraseConteggio(ok) {
    const conteggi = new Map();
    ok.forEach(r => conteggi.set(r.etichetta, (conteggi.get(r.etichetta) || 0) + 1));
    return [...conteggi.entries()].sort((a, b) => b[1] - a[1])
      .map(([et, n]) => NT.t('{n} su {tot}: {et}', { n: n, tot: ok.length, et: etichettaRisultato(et) })).join('; ');
  }

  function renderSintesi(s, fotoId) {
    const giud = s.con_risultato.length === 0 ? GIUDIZIO_NESSUNO : (s.attenzione.length || s.discordi.length) ? GIUDIZIO_ATT : GIUDIZIO_BEN;
    const schede = s.metodi.map(m => {
      const ok = m.risultati.filter(r => r.stato === 'ok');
      const piu = new Set(m.risultati.map(r => r.gruppo).filter(Boolean)).size > 1;
      return h('div', { class: 'metodo' },
        h('div', { class: 'metodo-testa' }, h('strong', {}, NT.t('Metodo {n}', { n: m.numero })), h('span', { class: 'metodo-titolo' }, NT.tr(m.titolo)),
          m.verdetto ? NT.chipEsito(m.verdetto) : h('span', { class: 'chip chip-neutro' }, NT.t('Nessun risultato'))),
        m.introduzione ? h('p', { class: 'piccolo muted' }, NT.tr(m.introduzione)) : null,
        ok.length ? h('p', { class: 'ha-detto' }, NT.t('Il metodo {n} ha detto che:', { n: m.numero }) + ' ', h('strong', {}, fraseConteggio(ok))) : null,
        h('ul', { class: 'modelli' }, m.risultati.map(r => r.stato === 'ok'
          ? h('li', {}, h('span', { class: 'mod-nome' }, (piu && r.gruppo ? '[' + NT.tr(r.gruppo) + '] ' : '') + r.nome), h('span', {}, '→ ' + etichettaRisultato(r.etichetta)),
            h('span', { class: 'muted' }, NT.t('sicurezza {perc}', { perc: NT.perc(r.valore) }) + (r.prob_mel !== null && r.prob_mel !== undefined ? ' · ' + NT.t('prob. melanoma {perc}', { perc: NT.perc(r.prob_mel) }) : '')))
          : h('li', { class: 'nota-metodo ' + r.stato }, h('span', {}, (r.stato === 'errore' ? NT.t('{nome}: errore.', { nome: r.nome }) + ' ' : r.stato === 'non_disponibile' ? NT.t('{nome}: non disponibile.', { nome: r.nome }) + ' ' : '') + NT.tr(r.nota || ''))))));
    });
    return h('div', { class: 'sintesi' },
      h('div', { class: 'sintesi-testa' }, NT.chipEsito(s.esito), h('span', { class: 'piccolo muted' }, NT.t('{n} metodi su {tot} hanno risposto', { n: s.con_risultato.length, tot: s.metodi.length }))),
      h('p', { class: 'giudizio' }, giud),
      schede,
      h('details', { class: 'consigli' }, h('summary', {}, NT.t('Avvertenze')), h('ul', {}, AVVERTENZE.map(a => h('li', {}, a)))),
      s.testo ? h('details', { class: 'consigli' }, h('summary', {}, NT.lingua === 'it' ? NT.t('Rapporto completo (testo)') : NT.t('Rapporto completo (testo, in italiano)')), h('pre', { class: 'rapporto' }, s.testo)) : null,
      h('button', { class: 'btn-testo', onclick: () => avviaAnalisi(fotoId) }, NT.t('Rianalizza')));
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
    [1, 'I', NT.t('Pelle molto chiara. Scotta sempre, non si abbronza mai (spesso capelli rossi, lentiggini).')],
    [2, 'II', NT.t('Pelle chiara. Scotta facilmente, si abbronza poco.')],
    [3, 'III', NT.t('Pelle chiara-olivastra. Scotta a volte, si abbronza gradualmente.')],
    [4, 'IV', NT.t('Pelle olivastra. Scotta poco, si abbronza facilmente.')],
    [5, 'V', NT.t('Pelle scura. Scotta raramente.')],
    [6, 'VI', NT.t('Pelle molto scura. Non scotta.')],
  ];

  NT.viste.profilo = async function (cont) {
    const u = S.utente;
    let p = Object.assign({}, u.profilo);
    let daSalvare = false;                // true tra una modifica e il salvataggio automatico
    const stato = h('span', { class: 'salvataggio' }, '');
    const riepilogo = h('aside', { class: 'riepilogo-profilo' });

    /* ---------- salvataggio automatico ---------- */
    const salvaOra = async () => {
      daSalvare = false;
      stato.textContent = NT.t('Salvataggio…'); stato.className = 'salvataggio';
      try {
        const r = await NT.api('PUT', '/api/utenti/' + u.id + '/profilo', p);
        S.utente = Object.assign(S.utente, r);
        stato.textContent = NT.t('Salvato ✓'); stato.className = 'salvataggio ok';
        disegnaRiepilogo();
      } catch (e) { stato.textContent = ''; NT.errore(e); }
    };
    const salva = NT.debounce(salvaOra, 700);
    const cambia = (campo, valore) => { p[campo] = valore; daSalvare = true; stato.textContent = NT.t('Modifiche non salvate…'); stato.className = 'salvataggio'; salva(); };
    NT.alCambioPagina(() => { if (daSalvare) salvaOra(); });

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
        h('div', { class: 'contatore' }, h('button', { type: 'button', class: 'btn-icona', 'aria-label': NT.t('Diminuisci: {voce}', { voce: testo }), onclick: () => agg(-1) }, NT.icona('meno', 16)), val,
          h('button', { type: 'button', class: 'btn-icona', 'aria-label': NT.t('Aumenta: {voce}', { voce: testo }), onclick: () => agg(1) }, NT.icona('piu', 16))));
    };

    /* ---------- fototipo ---------- */
    const COL = window.Corpo.colorePelle;
    const fototipi = h('div', { class: 'fototipi', role: 'radiogroup', 'aria-label': NT.t('Fototipo') }, FOTOTIPI.map(([n, r, d]) => h('button', { type: 'button', role: 'radio', class: 'fototipo' + (p.fototipo === n ? ' sel' : ''),
      'aria-checked': p.fototipo === n ? 'true' : 'false', dataset: { n: String(n) },
      onclick: () => { p.fototipo = p.fototipo === n ? 0 : n; NT.$$('.fototipo', fototipi).forEach(b => { const on = +b.dataset.n === p.fototipo; b.classList.toggle('sel', on); b.setAttribute('aria-checked', on ? 'true' : 'false'); }); cambia('fototipo', p.fototipo); } },
      h('span', { class: 'swatch', style: { background: COL(n) } }), h('span', {}, h('strong', {}, NT.t('Tipo {n}', { n: r })), h('small', {}, d)))));

    const eta = h('span', { class: 'eta-calcolata' }, '');
    const aggiornaEta = () => {
      if (!p.data_nascita) { eta.textContent = ''; return; }
      const n = new Date(p.data_nascita + 'T12:00:00'), o = new Date();
      let a = o.getFullYear() - n.getFullYear(); if (o < new Date(o.getFullYear(), n.getMonth(), n.getDate())) a--;
      eta.textContent = a >= 0 ? NT.tp(a, '{n} anno', '{n} anni') : '';
    };
    const nascita = h('input', { type: 'date', class: 'campo corto', value: p.data_nascita || '', min: '1900-01-01', max: NT.oggiISO(),
      onchange: ev => { cambia('data_nascita', ev.target.value); aggiornaEta(); } });
    aggiornaEta();

    const sezione = (titolo, intro, ...figli) => h('section', { class: 'scheda' }, h('h2', {}, titolo), intro ? h('p', { class: 'piccolo muted' }, intro) : null, ...figli);

    /* ---------- immagine personale ---------- */
    const boxAvatar = h('div', { class: 'avatar-editor' });
    const entrata = h('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp,image/bmp', hidden: true, 'aria-label': NT.t('Scegli un\'immagine personale') });
    const aggiornaAvatar = v => { S.utente.avatar_v = v; disegnaAvatar(); NT.ridisegnaTestata(); disegnaRiepilogo(); };
    async function scegliAvatar() {
      const file = entrata.files && entrata.files[0];
      entrata.value = '';
      if (!file) return;
      try {
        if (file.size > 40 * 1024 * 1024) throw new Error(NT.t('Il file è troppo grande (massimo 40 MB).'));
        const blob = await NT.ridimensionaQuadrato(file, 256);      // ritaglio quadrato al centro + riduzione, nel browser
        const r = await NT.api('POST', '/api/utenti/' + u.id + '/avatar', null, { raw: blob, tipo: 'image/jpeg' });
        aggiornaAvatar(r.avatar_v);
        NT.toast(NT.t('Immagine personale salvata.'), 'ok');
      } catch (e) { NT.errore(e); }
    }
    async function togliAvatar() {
      try { const r = await NT.api('DELETE', '/api/utenti/' + u.id + '/avatar'); aggiornaAvatar(r.avatar_v); NT.toast(NT.t('Immagine rimossa.'), 'ok'); }
      catch (e) { NT.errore(e); }
    }
    entrata.addEventListener('change', scegliAvatar);
    function disegnaAvatar() {
      NT.riempi(boxAvatar, NT.avatar(u.nome, 88, S.utente),
        h('div', { class: 'avatar-azioni' },
          h('p', { class: 'piccolo muted' }, NT.t('Puoi usare una tua foto, un disegno o un\'icona. L\'immagine viene ritagliata a quadrato e ridotta, resta solo su questo computer e non viene mai usata per l\'analisi dei nei.')),
          h('div', { class: 'riga-inline' },
            h('button', { type: 'button', class: 'btn', onclick: () => entrata.click() }, S.utente.avatar_v ? NT.t('Cambia immagine…') : NT.t('Scegli immagine…')),
            S.utente.avatar_v ? h('button', { type: 'button', class: 'btn-testo pericolo', onclick: togliAvatar }, NT.t('Rimuovi')) : null)));
    }
    disegnaAvatar();

    const form = h('div', { class: 'pila' },
      h('div', { class: 'scheda info' }, h('strong', {}, NT.t('A che cosa servono questi dati?') + ' '),
        NT.t('Non cambiano il risultato delle reti neurali, che guardano solo i pixel della foto. Servono a: (1) dare un contesto al rischio, (2) scegliere la letteratura scientifica adatta a te, (3) verificare i criteri per la consulenza genetica, (4) calcolare quanto tempo puoi stare al sole prima di scottarti. Tutto resta sul tuo computer.')),
      sezione(NT.t('Immagine personale'), null, boxAvatar, entrata),
      sezione(NT.t('Dati personali'), null,
        campo(NT.t('Sesso'), gruppo('sesso', [['F', NT.t('Donna')], ['M', NT.t('Uomo')], ['altro', NT.t('Altro')], ['', NT.t('Preferisco non dirlo')]], NT.t('Sesso'))),
        campo(NT.t('Data di nascita'), h('div', { class: 'riga-inline' }, nascita, eta))),
      sezione(NT.t('Fenotipo: pelle, capelli, occhi'), NT.t('Se hai dubbi sul fototipo, pensa a come reagisce la tua pelle alla prima esposizione intensa al sole in estate, senza protezione.'),
        campo(NT.t('Fototipo (classificazione di Fitzpatrick)'), fototipi, NT.t('Non lo so: lascia vuoto, puoi tornare più tardi.')),
        campo(NT.t('Colore naturale dei capelli (da giovane)'), gruppo('capelli', [['neri', NT.t('Neri')], ['castani', NT.t('Castani')], ['biondi', NT.t('Biondi')], ['rossi', NT.t('Rossi')], ['grigi', NT.t('Grigi/bianchi')]], NT.t('Capelli'))),
        campo(NT.t('Colore degli occhi'), gruppo('occhi', [['scuri', NT.t('Scuri')], ['verdi', NT.t('Verdi')], ['azzurri', NT.t('Azzurri/grigi')]], NT.t('Occhi'))),
        campo(NT.t('Efelidi (lentiggini)'), gruppo('efelidi', [['nessuna', NT.t('Nessuna')], ['poche', NT.t('Poche')], ['molte', NT.t('Molte')]], NT.t('Efelidi'))),
        campo(NT.t('Quanti nei hai sul corpo, circa?'), gruppo('n_nevi', [['<25', NT.t('Meno di 25')], ['25-49', '25–49'], ['50-99', '50–99'], ['100+', NT.t('100 o più')]], NT.t('Numero di nei')), NT.t('Una stima va bene.')),
        campo(NT.t('Un medico ti ha detto che hai nei atipici (displastici)?'), gruppo('nevi_atipici', [['no', NT.t('No')], ['si', NT.t('Sì')], ['non so', NT.t('Non so')]], NT.t('Nei atipici')))),
      sezione(NT.t('Esposizione al sole'), null,
        campo(NT.t('Scottature con vesciche (soprattutto da bambino o ragazzo)'), gruppo('scottature', [['mai', NT.t('Mai')], ['poche', NT.t('Poche')], ['molte', NT.t('Molte')]], NT.t('Scottature'))),
        campo(NT.t('Lampade o lettini abbronzanti'), gruppo('lampade', [['mai', NT.t('Mai')], ['alcune', NT.t('Qualche volta')], ['spesso', NT.t('Spesso')]], NT.t('Lampade'))),
        spunta('lavoro_aperto', NT.t('Lavoro o faccio attività per molte ore all\'aperto'))),
      sezione(NT.t('Storia personale'), null,
        contatore('melanomi_personali', NT.t('Melanomi già diagnosticati a me'), NT.t('Conta solo i melanomi primari invasivi.')),
        spunta('altri_tumori_cutanei', NT.t('Ho avuto altri tumori della pelle (basalioma, spinalioma)')),
        spunta('immunosoppressione', NT.t('Sono immunosoppresso/a (trapianto o terapie che abbassano le difese)')),
        h('div', { class: 'campo-titolo spazio-su' }, NT.t('Ho avuto (o ho) uno di questi tumori:')),
        h('div', { class: 'spunte-griglia' }, spunta('pers_pancreas', NT.t('Tumore del pancreas')), spunta('pers_astrocitoma', NT.t('Astrocitoma')),
          spunta('pers_uveale', NT.t('Melanoma dell\'occhio (uveale)')), spunta('pers_mesotelioma', NT.t('Mesotelioma')), spunta('pers_rene', NT.t('Carcinoma del rene'))),
        campo(NT.t('Ho già fatto un test genetico per il melanoma?'), gruppo('test_genetico', [['', NT.t('Non indicato')], ['no', NT.t('No')], ['si_positivo', NT.t('Sì, positivo')], ['si_negativo', NT.t('Sì, negativo')], ['si_non_informativo', NT.t('Sì, non informativo')]], NT.t('Test genetico')))),
      sezione(NT.t('Familiarità'), NT.t('Conta i parenti di sangue (non quelli acquisiti) dello stesso lato della famiglia, materno o paterno: è il criterio che usano i genetisti. Se non lo sai, chiedi a un familiare: queste informazioni sono molto utili.'),
        h('label', { class: 'spunta grande' }, h('input', { type: 'checkbox', id: 'ck-fam', checked: !!p.fam_compilata, onchange: ev => cambia('fam_compilata', ev.target.checked) }), ' ' + NT.t('Ho verificato la mia storia familiare (anche se la risposta è «nessuno»)')),
        contatore('fam_melanoma_1grado', NT.t('Parenti di 1° grado con melanoma'), NT.t('Genitori, fratelli, sorelle, figli.')),
        contatore('fam_melanoma_altri', NT.t('Altri parenti con melanoma'), NT.t('Nonni, zii, nipoti (2° grado).')),
        contatore('fam_pancreas', NT.t('Parenti con tumore del pancreas (in tutto)'), NT.t('Di qualsiasi grado di parentela.')),
        contatore('fam_pancreas_1grado', NT.t('…di cui di 1° grado')),
        contatore('fam_astrocitoma', NT.t('Parenti con astrocitoma (tumore del cervello)')),
        contatore('fam_uveale', NT.t('Parenti con melanoma dell\'occhio (uveale)')),
        contatore('fam_mesotelioma', NT.t('Parenti con mesotelioma')),
        contatore('fam_rene', NT.t('Parenti con carcinoma del rene'))),
      sezione(NT.t('Note'), null, h('textarea', { class: 'campo', rows: 3, maxlength: 1000, placeholder: NT.t('Altro che vuoi ricordare (allergie, farmaci fotosensibilizzanti, …)'), value: p.note || '', oninput: ev => cambia('note', ev.target.value) })));

    /* ---------- riepilogo laterale ---------- */
    function disegnaRiepilogo() {
      const ri = S.utente.rischio, ge = S.utente.genetica;
      const colore = { nessuno: 'neutro', alcuni: 'giallo', attenzione: 'arancio' }[ri.livello];
      NT.riempi(riepilogo, 
        h('div', { class: 'scheda' }, h('div', { class: 'riga-spinner' }, NT.avatar(S.utente.nome, 44, S.utente), h('div', {}, h('strong', {}, S.utente.nome),
          h('div', { class: 'piccolo muted' }, [S.utente.eta !== null && S.utente.eta !== undefined ? NT.tp(S.utente.eta, '{n} anno', '{n} anni') : null, S.utente.profilo.fototipo ? NT.t('fototipo {tipo}', { tipo: FOTOTIPI[S.utente.profilo.fototipo - 1][1] }) : null].filter(Boolean).join(' · ') || NT.t('Profilo da completare')))), stato),
        h('div', { class: 'scheda' }, h('h3', {}, NT.t('Fattori di rischio presenti')),
          h('div', { class: 'banda ' + colore }, NT.tr(ri.testo)),
          ri.presenti.length ? h('ul', { class: 'fattori' }, ri.presenti.map(f => h('li', {}, h('span', {}, NT.tr(f.etichetta), f.maggiore ? h('span', { class: 'chip chip-neutro' }, NT.t('rilevante')) : null), f.nota ? h('small', {}, NT.tr(f.nota)) : null))) : null,
          h('p', { class: 'piccolo muted' }, NT.tr(ri.nota))),
        h('div', { class: 'scheda' }, h('h3', {}, NT.t('Melanoma ereditario')),
          h('div', { class: 'banda ' + (ge.esito === 'criteri_soddisfatti' ? 'arancio' : 'neutro') }, NT.tr(ge.messaggio) + (ge.messaggio_aggiunta ? ' ' + NT.tr(ge.messaggio_aggiunta) : '')),
          h('a', { class: 'btn', href: '#/genetica' }, NT.t('Vai alla sezione Genetica'), NT.icona('freccia', 16))));
    }
    disegnaRiepilogo();
    NT.riempi(cont, h('div', { class: 'pagina' }, h('h1', {}, NT.t('Profilo di {nome}', { nome: u.nome })),
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
    'Review': NT.t('Revisione'), 'Systematic Review': NT.t('Revisione sistematica'), 'Meta-Analysis': NT.t('Meta-analisi'),
    'Practice Guideline': NT.t('Linea guida'), 'Guideline': NT.t('Linea guida'), 'Consensus Development Conference': NT.t('Consenso'),
    'Randomized Controlled Trial': NT.t('Studio randomizzato'), 'Clinical Trial': NT.t('Studio clinico'), 'Observational Study': NT.t('Studio osservazionale'),
  };
  const fmtN = n => NT.migliaia(n);
  const dataRicerca = d => d.data_iso ? NT.fmtData(d.data_iso) : d.data;      // 'data_iso' manca nelle ricerche salvate da versioni vecchie

  function articolo(a) {
    const tipi = (a.tipi || []).map(t => TIPI[t]).filter(Boolean);
    return h('article', { class: 'articolo' },
      h('a', { href: a.url, target: '_blank', rel: 'noopener noreferrer', class: 'art-titolo' }, a.titolo || NT.t('(senza titolo)')),
      h('div', { class: 'art-meta' }, [a.autori, a.rivista, a.anno].filter(Boolean).join(' · ')),
      tipi.length ? h('div', { class: 'chips' }, [...new Set(tipi)].map(t => h('span', { class: 'chip chip-neutro' }, t))) : null,
      a.abstract ? h('details', { class: 'abstract' }, h('summary', {}, NT.t('Leggi l\'abstract')), h('p', {}, a.abstract),
        h('div', { class: 'piccolo muted' }, NT.t('In inglese') + ' · PubMed ', a.pmid, a.doi ? [' · ', NT.link('https://doi.org/' + a.doi, 'DOI')] : null)) : h('div', { class: 'piccolo muted' }, NT.t('PubMed {pmid} · abstract non disponibile', { pmid: a.pmid })));
  }

  function avvisoCache(d) {
    if (d.obsoleta) return h('div', { class: 'banda giallo' }, NT.t('PubMed non è raggiungibile: mostro l\'ultima ricerca salvata il {data}.', { data: dataRicerca(d) }));
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
        const corpo = h('div', { class: 'sez-corpo' }, h('div', { class: 'piccolo muted' }, NT.t('Non ancora scansionata.')));
        const testa = h('h3', {}, NT.tr(s.titolo));
        const box = h('div', { class: 'sez' }, testa, corpo);
        sezioni.push({ id: s.id, titolo: s.titolo, corpo, testa });
        return box;
      });
      return h('section', { class: 'scheda' }, h('h2', {}, NT.tr(t.titolo)), corpiSez);
    });

    const progresso = h('span', { class: 'piccolo muted' }, '');
    const btnScan = h('button', { class: 'btn btn-pri', onclick: () => scansiona(false) }, NT.icona('cerca', 18), NT.t('Scansiona la letteratura'));
    const btnForza = h('button', { class: 'btn', title: NT.t('Rifà la ricerca ignorando i risultati salvati'), onclick: () => scansiona(true) }, NT.t('Aggiorna'));

    async function scansiona(forza) {
      if (inCorso) return;
      inCorso = true; btnScan.disabled = true; btnForza.disabled = true;
      let n = 0;
      for (const s of sezioni) {
        if (!attivo) break;
        n++; progresso.textContent = NT.t('Sezione {n} di {tot}…', { n: n, tot: sezioni.length });
        NT.riempi(s.corpo, NT.caricamento(NT.t('Cerco su PubMed…')));
        try {
          const d = await NT.get('/api/letteratura/sezione?id=' + encodeURIComponent(s.id) + '&utente=' + uid + (forza ? '&forza=1' : ''));
          NT.riempi(s.corpo, avvisoCache(d),
            h('div', { class: 'piccolo muted spazio-giu' }, (d.da_cache ? NT.t('{n} articoli trovati su PubMed · ricerca del {data} (salvata)', { n: fmtN(d.conteggio), data: dataRicerca(d) })
              : NT.t('{n} articoli trovati su PubMed · ricerca del {data}', { n: fmtN(d.conteggio), data: dataRicerca(d) }))),
            d.articoli.length ? d.articoli.map(articolo) : h('div', { class: 'piccolo muted' }, NT.t('Nessun articolo trovato.')));
        } catch (e) { NT.riempi(s.corpo, h('div', { class: 'errore-campo' }, e.message)); }
      }
      inCorso = false;
      if (!attivo) return;
      btnScan.disabled = false; btnForza.disabled = false; progresso.textContent = NT.t('Scansione completata.');
    }

    /* ricerca libera */
    const q = h('input', { type: 'search', class: 'campo', placeholder: NT.t('Cerca altro (es. "ugly duckling sign", "nail melanoma"…)'), maxlength: 200 });
    const risLibera = h('div', { class: 'ris-libera' });
    const cerca = async () => {
      if (q.value.trim().length < 3) { NT.toast(NT.t('Scrivi almeno 3 caratteri.'), 'errore'); return; }
      NT.riempi(risLibera, NT.caricamento(NT.t('Cerco su PubMed…')));
      try {
        const d = await NT.get('/api/letteratura/cerca?q=' + encodeURIComponent(q.value));
        NT.riempi(risLibera, avvisoCache(d), h('div', { class: 'piccolo muted spazio-giu' }, NT.t('{n} articoli su melanoma e «{termine}»', { n: fmtN(d.conteggio), termine: q.value.trim() })),
          d.articoli.length ? d.articoli.map(articolo) : h('div', { class: 'piccolo muted' }, NT.t('Nessun articolo trovato.')));
      } catch (e) { NT.riempi(risLibera, h('div', { class: 'errore-campo' }, e.message)); }
    };
    q.addEventListener('keydown', e => { if (e.key === 'Enter') cerca(); });

    NT.riempi(cont, h('div', { class: 'pagina' },
      h('h1', {}, NT.t('Letteratura scientifica')),
      h('p', { class: 'lead' }, NT.t('Articoli recenti e rilevanti su come riconoscere i nei sospetti, sull\'affidabilità di app e intelligenza artificiale e sul melanoma ereditario. I risultati arrivano da PubMed, la banca dati pubblica della National Library of Medicine (USA).')),
      h('div', { class: 'scheda azione-scan' }, h('div', { class: 'riga-inline' }, btnScan, btnForza, progresso),
        h('p', { class: 'piccolo muted' }, NT.t('Le ricerche partono da questo computer verso PubMed (nessun dato personale viene inviato). I risultati si salvano per 7 giorni.') + ' ' +
          NT.t('Le sezioni «scelte per te» usano parole legate al tuo profilo (per esempio fototipo o numero di nei): se preferisci non inviarle, non scansionare quella sezione.')),
        h('div', { class: 'riga-inline' }, h('button', { class: 'btn-testo', onclick: () => NT.dialogoABCDE() }, NT.t('Promemoria ABCDE per riconoscere un neo')))),
      h('div', { class: 'scheda' }, h('h2', {}, NT.t('Cerca nella letteratura')), h('div', { class: 'riga-inline' }, q, h('button', { class: 'btn', onclick: cerca }, NT.t('Cerca'))), risLibera),
      temiEl,
      h('div', { class: 'scheda piccolo muted' }, NT.t('PubMed è un servizio della National Library of Medicine. Gli abstract sono mostrati per consultazione personale, in inglese; per il testo completo apri l\'articolo sul sito della rivista.') + ' ',
        NT.t('Gli articoli sono scelti da una ricerca automatica e non sono stati valutati da NeoTracker: leggili con il tuo medico.'))));
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
      h('span', { class: 'esito-criterio', 'aria-label': c.soddisfatto ? NT.t('Soddisfatto') : NT.t('Non soddisfatto') }, c.soddisfatto ? NT.icona('ok', 16) : '—'),
      h('div', {}, h('strong', {}, NT.tr(c.titolo)), h('div', { class: 'piccolo muted' }, NT.tr(c.spiegazione)), h('div', { class: 'piccolo muted' }, NT.t('Fonte:') + ' ' + NT.tr(c.fonte))))));

    const righe = dati.geni.map(ge => {
      const risultato = h('div', { class: 'gene-ris' }, h('span', { class: 'piccolo muted' }, NT.t('Non ancora scansionato')));
      return { nome: ge.gene, risultato, riga: h('tr', {}, h('td', {}, h('strong', {}, ge.gene), g.geni_suggeriti.includes(ge.gene) ? h('div', { class: 'chip chip-neutro' }, NT.t('nel pannello')) : null),
        h('td', {}, NT.tr(ge.rischio)), h('td', {}, NT.tr(ge.ruolo), risultato)) };
    });
    const progresso = h('span', { class: 'piccolo muted' }, '');
    const btn = h('button', { class: 'btn btn-pri', onclick: () => scansiona(false) }, NT.icona('cerca', 18), NT.t('Scansiona la letteratura sui geni'));
    const btnF = h('button', { class: 'btn', onclick: () => scansiona(true) }, NT.t('Aggiorna'));
    async function scansiona(forza) {
      if (inCorso) return;
      inCorso = true; btn.disabled = true; btnF.disabled = true;
      let n = 0;
      for (const r of righe) {
        if (!attivo) break;
        n++; progresso.textContent = NT.t('Gene {n} di {tot} ({nome})…', { n: n, tot: righe.length, nome: r.nome });
        NT.riempi(r.risultato, NT.caricamento(NT.t('Cerco…')));
        try {
          const d = await NT.get('/api/genetica/gene?nome=' + encodeURIComponent(r.nome) + (forza ? '&forza=1' : ''));
          NT.riempi(r.risultato, h('div', { class: 'gene-conta' }, h('strong', {}, fmtN(d.conteggio)), ' ' + NT.t('studi su PubMed'), d.obsoleta ? ' ' + NT.t('(ricerca salvata del {data})', { data: dataRicerca(d) }) : ''),
            d.articoli.length ? h('details', { class: 'abstract' }, h('summary', {}, NT.t('Studi più pertinenti')), d.articoli.map(articolo)) : null);
        } catch (e) { NT.riempi(r.risultato, h('div', { class: 'errore-campo' }, e.message)); }
      }
      inCorso = false;
      if (attivo) { btn.disabled = false; btnF.disabled = false; progresso.textContent = NT.t('Scansione completata.'); }
    }

    NT.riempi(cont, h('div', { class: 'pagina' },
      h('h1', {}, NT.t('Melanoma ereditario e test genetico')),
      h('p', { class: 'lead' }, NT.t('Circa il 5-10% dei melanomi si presenta in famiglie con una predisposizione ereditaria (Leachman 2009). Qui trovi i criteri che usano gli specialisti per decidere se proporre una consulenza genetica, i geni coinvolti e la letteratura su ciascuno.')),
      h('section', { class: 'scheda' }, h('h2', {}, NT.t('I tuoi dati rispetto ai criteri')),
        h('div', { class: 'banda ' + cls }, NT.tr(g.messaggio) + (g.messaggio_aggiunta ? ' ' + NT.tr(g.messaggio_aggiunta) : '')),
        g.esito !== 'dati_insufficienti' ? criteri : null,
        h('div', { class: 'azioni sinistra' }, h('a', { class: 'btn', href: '#/profilo' }, g.esito === 'dati_insufficienti' ? NT.t('Compila la familiarità nel Profilo') : NT.t('Modifica i dati nel Profilo'))),
        h('p', { class: 'piccolo muted' }, NT.t('Criteri semplificati, a scopo informativo. Il test genetico riguarda una piccola minoranza di persone e non è un esame di routine: è lo specialista a decidere se e quale test proporre, di norma dopo una consulenza genetica e partendo, quando possibile, da un familiare che ha avuto la malattia.'))),
      h('section', { class: 'scheda' }, h('h2', {}, NT.t('Cosa sapere prima di un test genetico')),
        h('ul', { class: 'punti' },
          h('li', {}, NT.t('Un risultato positivo indica un rischio più alto, non la certezza di ammalarsi; un risultato negativo non azzera il rischio (molte famiglie non hanno una variante identificabile).')),
          h('li', {}, NT.t('Il risultato riguarda anche i familiari di sangue: per questo la consulenza prima e dopo il test è parte del percorso.')),
          h('li', {}, NT.t('Le linee guida raccomandano il test solo dopo una selezione accurata dei candidati e un\'adeguata consulenza (Rossi 2019); l\'uso dei pannelli multigene è ancora discusso.')),
          h('li', {}, NT.t('Con o senza test, per chi ha una storia familiare restano fondamentali la protezione dal sole, l\'autoesame della pelle e i controlli dermatologici periodici.')))),
      h('section', { class: 'scheda' }, h('h2', {}, NT.t('I geni più studiati')),
        h('div', { class: 'azione-scan' }, h('div', { class: 'riga-inline' }, btn, btnF, progresso)),
        h('div', { class: 'tabella-scroll' }, h('table', { class: 'tabella' }, h('thead', {}, h('tr', {}, h('th', {}, NT.t('Gene')), h('th', {}, NT.t('Rischio associato')), h('th', {}, NT.t('Ruolo e letteratura')))), h('tbody', {}, righe.map(r => r.riga))))),
      h('section', { class: 'scheda' }, h('h2', {}, NT.t('Fonti')), h('ul', { class: 'fonti' }, dati.fonti.map(f => h('li', {}, NT.link(f.url, NT.tr(f.titolo))))),
        h('p', { class: 'piccolo muted' }, NT.t('NeoTracker non è un servizio di consulenza genetica. Per una valutazione personale rivolgiti al dermatologo o a un centro di genetica oncologica.')))));
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
      const campo = h('input', { type: 'text', class: 'campo', maxlength: 60, value: valore || '', placeholder: NT.t('Nome o soprannome'), autocomplete: 'off' });
      const errore = h('div', { class: 'errore-campo' });
      const invia = () => {
        const v = campo.value.trim();
        if (!v) { errore.textContent = NT.t('Scrivi un nome.'); return; }
        res(v); NT.chiudiDialogo();
      };
      campo.addEventListener('keydown', e => { if (e.key === 'Enter') invia(); });
      const d = NT.apriDialogo(h('div', {}, h('h3', {}, titolo), campo, errore,
        h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => { res(null); NT.chiudiDialogo(); } }, NT.t('Annulla')),
          h('button', { class: 'btn btn-pri', onclick: invia }, testoOk || NT.t('Salva')))));
      d.addEventListener('close', () => res(null), { once: true });
      campo.focus(); campo.select();
    });
  }

  NT.viste.utenti = async function (cont) {
    S.utenti = await NT.get('/api/utenti');

    async function nuovo() {
      const nome = await dialogoNome(NT.t('Nuovo utente'), '', NT.t('Crea utente'));
      if (!nome) return;
      try {
        const r = await NT.api('POST', '/api/utenti', { nome });
        S.utenti = await NT.get('/api/utenti');
        await NT.scegliUtente(r.id, false);
        NT.toast(NT.t('Utente creato. Compila il profilo: serve a contestualizzare i risultati.'), 'ok');
        NT.vai('profilo');
      } catch (e) { NT.errore(e); }
    }
    async function rinomina(u) {
      const nome = await dialogoNome(NT.t('Rinomina utente'), u.nome, NT.t('Salva'));
      if (!nome || nome === u.nome) return;
      try {
        await NT.api('PATCH', '/api/utenti/' + u.id, { nome });
        if (S.utente && S.utente.id === u.id) await NT.ricaricaUtente();
        NT.vai('utenti');
      } catch (e) { NT.errore(e); }
    }
    async function elimina(u) {
      const si = await NT.conferma(NT.t('Eliminare «{nome}»?', { nome: u.nome }),
        NT.t('Verranno cancellati per sempre il profilo, tutti i nei, tutte le foto e tutti i rapporti di questo utente. L\'operazione non si può annullare.'),
        { si: NT.t('Elimina definitivamente'), pericolo: true, scrivi: u.nome });
      if (!si) return;
      try {
        await NT.api('DELETE', '/api/utenti/' + u.id, { conferma: u.nome });
        if (S.utente && S.utente.id === u.id) { S.utente = null; S.nei = []; NT.ls.scrivi('nt_utente', ''); }
        NT.toast(NT.t('Utente eliminato.'), 'ok');
        NT.vai('utenti');
      } catch (e) { NT.errore(e); }
    }

    const schede = S.utenti.map(u => h('div', { class: 'utente-card' + (S.utente && S.utente.id === u.id ? ' corrente' : '') },
      h('button', { class: 'utente-apri', onclick: () => NT.scegliUtente(u.id).catch(NT.errore) },
        NT.avatar(u.nome, 56, u),
        h('span', { class: 'utente-info' }, h('strong', {}, u.nome),
          h('span', { class: 'sotto' }, NT.tp(u.n_nevi, '{n} neo', '{n} nei') + (u.eta !== null && u.eta !== undefined ? ' · ' + NT.tp(u.eta, '{n} anno', '{n} anni') : '')))),
      h('div', { class: 'utente-azioni' },
        h('button', { class: 'btn-testo', onclick: () => rinomina(u) }, NT.t('Rinomina')),
        h('button', { class: 'btn-testo pericolo', onclick: () => elimina(u) }, NT.t('Elimina')))));

    cont.replaceChildren(h('div', { class: 'pagina stretta' },
      h('h1', {}, S.utenti.length ? NT.t('Chi sei?') : NT.t('Benvenuto in NeoTracker')),
      h('p', { class: 'lead' }, S.utenti.length
        ? NT.t('Scegli il tuo profilo: ogni persona ha la propria mappa dei nei, le proprie foto e i propri dati.')
        : NT.t('Questo programma ti aiuta a tenere traccia dei tuoi nei nel tempo: li segni su una mappa del corpo, ne conservi le foto con la data e li fai analizzare da più metodi. Inizia creando il tuo utente.')),
      h('div', { class: 'utenti-griglia' }, schede,
        h('button', { class: 'utente-card nuovo', onclick: nuovo }, h('span', { class: 'piu' }, NT.icona('piu', 28)), h('strong', {}, NT.t('Nuovo utente')))),
      h('div', { class: 'nota-privacy' }, NT.icona('ok', 16),
        h('span', {}, NT.t('Tutti i dati restano su questo computer, nella cartella:') + ' ', h('code', {}, S.stato.cartella_dati || ''),
          ' ' + NT.t('Nulla viene inviato online, tranne le richieste che attivi tu (meteo UV, letteratura PubMed, SkinSense).')))));
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
  const CAT = [[11, NT.m('Estremo'), '#8e44ad'], [8, NT.m('Molto alto'), '#d9261c'], [6, NT.m('Alto'), '#f28c00'], [3, NT.m('Moderato'), '#e8c400'], [0, NT.m('Basso'), '#3f9c35']];
  const cat = v => CAT.find(c => v >= c[0]) || CAT[CAT.length - 1];
  const FOTOTIPI = ['I', 'II', 'III', 'IV', 'V', 'VI'];

  function grafico(ore) {
    const W = 720, H = 230, sx = 44, dx = 12, su = 18, giu = 40;
    const larg = (W - sx - dx) / ore.length;
    const giorno = o => o.data ? NT.fmtGiornoMese(o.data) : o.giorno;       // 'data' = AAAA-MM-GG
    const massimo = Math.max(11, Math.ceil(Math.max(...ore.map(o => o.uvi))) + 1);
    const y = v => su + (H - su - giu) * (1 - v / massimo);
    let s = '<svg class="grafico-uv" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + NT.esc(NT.t('Indice UV ora per ora nelle prossime 24 ore')) + '">';
    for (let t = 0; t <= massimo; t += (massimo > 12 ? 4 : 2)) {
      s += '<line class="gl" x1="' + sx + '" x2="' + (W - dx) + '" y1="' + y(t) + '" y2="' + y(t) + '"/><text class="gt" x="' + (sx - 8) + '" y="' + (y(t) + 4) + '" text-anchor="end">' + t + '</text>';
    }
    ore.forEach((o, i) => {
      const x = sx + i * larg + larg * 0.14, w = larg * 0.72, c = cat(o.uvi);
      const alt = Math.max(o.uvi > 0 ? 2 : 0, y(0) - y(o.uvi));
      s += '<rect x="' + x.toFixed(1) + '" y="' + (y(0) - alt).toFixed(1) + '" width="' + w.toFixed(1) + '" height="' + alt.toFixed(1) + '" rx="2" fill="' + c[2] + '"><title>' +
        NT.esc(NT.t('{giorno} ore {ora}: indice UV {uvi} ({categoria})', { giorno: giorno(o), ora: o.ora, uvi: NT.num(o.uvi), categoria: NT.t(c[1]) })) + '</title></rect>';
      const cambio = i === 0 || o.giorno !== ore[i - 1].giorno;
      const vicinoCambio = [-2, -1, 1, 2].some(k => ore[i + k] && ore[i + k - 1] && ore[i + k].giorno !== ore[i + k - 1].giorno);
      if (cambio || (i % 3 === 0 && !vicinoCambio)) {
        s += '<text class="gt" x="' + (x + w / 2).toFixed(1) + '" y="' + (H - giu + 16) + '" text-anchor="middle">' + NT.esc(o.ora.slice(0, 2)) + '</text>';
        if (i === 0 || o.giorno !== ore[i - 1].giorno) s += '<text class="gt g6t" x="' + (x + w / 2).toFixed(1) + '" y="' + (H - giu + 32) + '" text-anchor="middle">' + NT.esc(giorno(o)) + '</text>';
      }
    });
    s += '<line class="gline" x1="' + sx + '" x2="' + (W - dx) + '" y1="' + y(3) + '" y2="' + y(3) + '" stroke-dasharray="5 4"/>' +
      '<text class="gt g6t" x="' + (W - dx) + '" y="' + (y(3) - 5) + '" text-anchor="end">' + NT.esc(NT.t('3 = da qui l\'OMS consiglia protezione')) + '</text></svg>';
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
        NT.toast(NT.t('Posizione salvata: {nome}', { nome: nome }), 'ok');
        disegnaBarra(); carica();
      } catch (e) { NT.errore(e); }
    }
    function rileva() {
      if (!navigator.geolocation) { NT.toast(NT.t('Questo browser non offre la geolocalizzazione: cerca la città per nome.'), 'errore'); return; }
      NT.toast(NT.t('Chiedo la posizione al browser… (potrebbe comparire una richiesta di permesso)'), 'info');
      navigator.geolocation.getCurrentPosition(
        p => salvaPos(p.coords.latitude, p.coords.longitude, NT.t('La mia posizione ({lat}; {lon})', { lat: NT.num(p.coords.latitude, 2), lon: NT.num(p.coords.longitude, 2) })),
        err => NT.toast(err.code === 1 ? NT.t('Permesso negato. Puoi cercare la città per nome oppure usare la stima da indirizzo internet.') : NT.t('Il computer non riesce a determinare la posizione. Cerca la città per nome.'), 'errore'),
        { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 });
    }
    async function daIP() {
      const ok = await NT.conferma(NT.t('Stima dall\'indirizzo internet'), NT.t('Per stimare la città il programma contatta il servizio gratuito ipwho.is, che vede il tuo indirizzo internet. La precisione è quella della città (a volte sbaglia). Procedo?'), { si: NT.t('Sì, stima la città') });
      if (!ok) return;
      try { const r = await NT.get('/api/posizione-ip'); await salvaPos(r.lat, r.lon, r.nome || NT.t('Posizione stimata')); }
      catch (e) { NT.errore(e); }
    }
    const campoCitta = h('input', { type: 'search', class: 'campo', placeholder: NT.t('Cerca una città (es. Torino)'), maxlength: 80, 'aria-label': NT.t('Nome della città') });
    const elencoCitta = h('div', { class: 'citta-elenco' });
    async function cercaCitta() {
      const q = campoCitta.value.trim();
      if (q.length < 2) return;
      NT.riempi(elencoCitta, NT.caricamento(NT.t('Cerco…')));
      try {
        const r = await NT.get('/api/localita?q=' + encodeURIComponent(q));
        NT.riempi(elencoCitta, r.length ? r.map(c => h('button', { class: 'btn citta-voce', onclick: () => salvaPos(c.lat, c.lon, c.nome) }, NT.icona('posizione', 16), c.nome))
          : h('div', { class: 'piccolo muted' }, NT.t('Nessuna città trovata con questo nome.')));
      } catch (e) { NT.riempi(elencoCitta, h('div', { class: 'errore-campo' }, e.message)); }
    }
    campoCitta.addEventListener('keydown', e => { if (e.key === 'Enter') cercaCitta(); });

    function disegnaBarra() {
      const ho = S.imp.lat !== null && S.imp.lat !== undefined;
      NT.riempi(barra, 
        h('div', { class: 'uv-posizione' }, NT.icona('posizione', 22),
          h('div', {}, h('strong', {}, ho ? (S.imp.localita || NT.t('Posizione impostata')) : NT.t('Posizione non impostata')),
            h('div', { class: 'piccolo muted' }, ho ? NT.num(S.imp.lat, 3) + '; ' + NT.num(S.imp.lon, 3) : NT.t('Scegli dove ti trovi per vedere l\'indice UV di oggi.')))),
        h('div', { class: 'riga-inline spazio-su' }, h('button', { class: 'btn btn-pri', onclick: rileva }, NT.icona('mirino', 18), NT.t('Rileva la mia posizione')),
          campoCitta, h('button', { class: 'btn', onclick: cercaCitta }, NT.t('Cerca'))),
        elencoCitta,
        h('div', { class: 'piccolo muted spazio-su' }, NT.t('La posizione resta salvata solo su questo computer; viene inviata al servizio meteo (coordinate arrotondate) per ottenere l\'indice UV.') + ' ',
          h('button', { class: 'btn-testo', onclick: daIP }, NT.t('Non riesci? Stima dall\'indirizzo internet'))));
    }

    /* ---------------- indice UV ---------------- */
    async function carica() {
      if (S.imp.lat === null || S.imp.lat === undefined) {
        NT.riempi(risultato, NT.vuoto(NT.t('Manca la posizione'), NT.t('Scegli la città qui sopra: poi vedrai l\'indice UV di oggi, ora per ora.')));
        return;
      }
      NT.riempi(risultato, NT.caricamento(NT.t('Scarico l\'indice UV…')));
      const ft = S.utente && S.utente.profilo.fototipo ? S.utente.profilo.fototipo : 0;
      let d;
      try { d = await NT.get('/api/uv?fototipo=' + ft + '&localita=' + encodeURIComponent(S.imp.localita || '')); }
      catch (e) { if (attivo) NT.riempi(risultato, h('div', { class: 'scheda errore-pagina' }, h('h2', {}, NT.t('Indice UV non disponibile')), h('p', {}, e.message), h('button', { class: 'btn', onclick: carica }, NT.t('Riprova')))); return; }
      if (!attivo) return;
      const cm = d.categoria_max, co = d.categoria_ora;
      const sc = d.scottatura_max;
      NT.riempi(risultato, 
        d.avviso ? h('div', { class: 'banda giallo' }, NT.tr(d.avviso), ' ', h('a', { href: '#/impostazioni' }, NT.t('Impostazioni'))) : null,
        h('section', { class: 'scheda uv-verdetto uv-' + d.verdetto.livello },
          h('div', { class: 'uv-titolo' }, h('h2', {}, NT.tr(d.verdetto.titolo)), h('p', {}, NT.tr(d.verdetto.testo))),
          h('div', { class: 'uv-numeri' },
            h('div', { class: 'uv-num' }, h('span', { class: 'uv-val', style: { background: co.colore, color: co.colore === '#e8c400' ? '#222' : '#fff' } }, NT.num(d.uvi_ora)), h('div', {}, h('strong', {}, NT.t('Adesso')), h('div', { class: 'piccolo' }, NT.tr(co.nome)))),
            h('div', { class: 'uv-num' }, h('span', { class: 'uv-val', style: { background: cm.colore, color: cm.colore === '#e8c400' ? '#222' : '#fff' } }, NT.num(d.uvi_max)), h('div', {}, h('strong', {}, NT.t('Massimo di oggi')), h('div', { class: 'piccolo' }, NT.tr(cm.nome)))))),
        h('section', { class: 'scheda' }, h('h2', {}, NT.t('Prossime {n} ore', { n: d.ore.length })), d.ore.length ? grafico(d.ore) : NT.vuoto(NT.t('Dati orari non disponibili')),
          h('div', { class: 'piccolo muted' }, NT.t('Fonte:') + ' ' + d.fonte + ' · ' + NT.t('aggiornato') + ' ' + (d.aggiornato_iso ? NT.fmtDataOra(d.aggiornato_iso) + ' ' + NT.t('(ora locale del luogo)') : d.aggiornato) + (d.fuso ? ' · ' + d.fuso : ''),
            d.fonte === 'Open-Meteo' ? [' · ', NT.link('https://open-meteo.com/', 'Open-Meteo.com'), ' (CC BY 4.0)'] : null)),
        h('section', { class: 'scheda' }, h('h2', {}, NT.t('Cosa fare')), h('p', {}, NT.tr(cm.consiglio)),
          sc ? h('div', { class: 'banda neutro' }, h('strong', {}, NT.t('Con il tuo fototipo ({fototipo})', { fototipo: FOTOTIPI[S.utente.profilo.fototipo - 1] })), ': ' + NT.t('a cielo sereno e senza protezione, al picco di oggi la pelle può arrossarsi in') + ' ',
            h('strong', {}, NT.tr(sc.testo)), '. ' + NT.t('È una stima prudente che usa la dose minima di eritema più bassa del tuo fototipo; con riflessi (acqua, neve, sabbia), quota o pelle già arrossata il tempo si accorcia.'))
            : h('div', { class: 'piccolo muted' }, S.utente ? [NT.t('Per vedere quanto sole ti scotta, indica il fototipo nel') + ' ', h('a', { href: '#/profilo' }, NT.t('Profilo')), '.'] : NT.t('Scegli un utente e indica il suo fototipo per vedere quanti minuti servono per scottarsi.')),
          h('ul', { class: 'punti' },
            h('li', {}, NT.t('Le ore centrali (circa 11-16) sono quelle con l\'indice più alto.')),
            h('li', {}, NT.t('Le nuvole sottili non fermano gran parte degli UV: l\'indice può restare alto anche con il cielo velato.')),
            h('li', {}, NT.t('Chi ha tanti nei, nei atipici o una storia di melanoma dovrebbe proteggersi anche con indici moderati.')),
            h('li', {}, NT.t('L\'indice è una previsione: il valore reale dipende da nuvole, quota e riflessi.')))),
        h('section', { class: 'scheda' }, h('h2', {}, NT.t('Come si legge l\'indice UV')),
          h('div', { class: 'legenda-uv' }, CAT.slice().reverse().map(c => h('span', { class: 'chip', style: { background: c[2], color: c[0] === 3 ? '#222' : '#fff' } }, NT.t(c[1]) + ' (' + (c[0] === 11 ? '11+' : c[0] + '–' + ({ 0: 2, 3: 5, 6: 7, 8: 10 }[c[0]])) + ')'))),
          h('p', { class: 'piccolo muted' }, NT.t('Soglie e colori della scala internazionale dell\'OMS. Fonti:')),
          h('ul', { class: 'fonti' }, d.fonti.map(f => h('li', {}, NT.link(f.url, NT.tr(f.titolo)))))));
    }

    disegnaBarra();
    NT.riempi(cont, h('div', { class: 'pagina' },
      h('h1', {}, NT.t('Indice UV di oggi')),
      h('p', { class: 'lead' }, NT.t('I raggi ultravioletti sono il principale fattore di rischio modificabile per il melanoma. Qui vedi quanto sono forti oggi dove ti trovi.')),
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


# Testi delle finestrelle di errore all'avvio (compaiono prima che il browser sia pronto, quindi non possono
# usare i dizionari web/i18n_XX.js). La chiave è il testo italiano; build.py controlla che ci siano tutte le lingue.
TESTI_AVVIO = {
    "NeoTracker è già acceso": {
        "en": "NeoTracker is already running", "fr": "NeoTracker est déjà lancé",
        "de": "NeoTracker läuft bereits", "es": "NeoTracker ya está en ejecución"},
    "Non riesco ad aprire una nuova finestra perché manca la chiave di sessione.\n"
    "Chiudi NeoTracker (dal Task Manager, processo Python) e riaprilo dall'icona.": {
        "en": "I cannot open a new window because the session key is missing.\n"
              "Close NeoTracker (from Task Manager, Python process) and reopen it from its icon.",
        "fr": "Impossible d'ouvrir une nouvelle fenêtre : la clé de session est introuvable.\n"
              "Fermez NeoTracker (depuis le Gestionnaire des tâches, processus Python) puis rouvrez-le avec son icône.",
        "de": "Es kann kein neues Fenster geöffnet werden, weil der Sitzungsschlüssel fehlt.\n"
              "Beenden Sie NeoTracker (im Task-Manager, Python-Prozess) und starten Sie es erneut über das Symbol.",
        "es": "No puedo abrir una ventana nueva porque falta la clave de sesión.\n"
              "Cierra NeoTracker (desde el Administrador de tareas, proceso Python) y vuelve a abrirlo desde el icono."},
    "NeoTracker non si avvia": {
        "en": "NeoTracker cannot start", "fr": "NeoTracker ne démarre pas",
        "de": "NeoTracker startet nicht", "es": "NeoTracker no se inicia"},
    "Non riesco a usare la porta {porta} ({e}).\n"
    "Un altro programma la sta usando. Chiudilo oppure cambia PORTA in cima al file neotracker.py.": {
        "en": "I cannot use port {porta} ({e}).\n"
              "Another program is using it. Close it, or change PORTA at the top of neotracker.py.",
        "fr": "Impossible d'utiliser le port {porta} ({e}).\n"
              "Un autre programme l'utilise. Fermez-le ou modifiez PORTA en haut du fichier neotracker.py.",
        "de": "Der Port {porta} kann nicht verwendet werden ({e}).\n"
              "Ein anderes Programm belegt ihn. Beenden Sie es oder ändern Sie PORTA am Anfang von neotracker.py.",
        "es": "No puedo usar el puerto {porta} ({e}).\n"
              "Otro programa lo está usando. Ciérralo o cambia PORTA al principio del archivo neotracker.py."},
    "NeoTracker si è fermato": {
        "en": "NeoTracker has stopped", "fr": "NeoTracker s'est arrêté",
        "de": "NeoTracker wurde beendet", "es": "NeoTracker se ha detenido"},
    "Dettagli in:": {
        "en": "Details in:", "fr": "Détails dans :", "de": "Details in:", "es": "Detalles en:"},
}


def testo_avvio(testo, **parametri):
    """Il testo della finestrella di errore nella lingua dell'utente (se manca la traduzione, resta l'italiano)."""
    try:
        lingua = lingua_corrente()
    except Exception:
        lingua = "it"
    scelto = TESTI_AVVIO.get(testo, {}).get(lingua, testo)
    return scelto.format(**parametri) if parametri else scelto


def mostra_errore(titolo, testo):
    """Mostra un problema grave. Con la finestra nera basta scriverlo; senza finestra nera
    (icona sul Desktop) nessuno leggerebbe il log, quindi compare una finestrella di Windows."""
    print(f"\n{titolo}\n{testo}")
    if os.name == "nt" and _USCITA_ORIGINALE["senza_console"]:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f"{testo}\n\n{testo_avvio('Dettagli in:')}\n{percorso_log()}", titolo, 0x10)   # 0x10 = icona di errore
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
                    mostra_errore(testo_avvio("NeoTracker è già acceso"),
                                  testo_avvio("Non riesco ad aprire una nuova finestra perché manca la chiave di sessione.\n"
                                              "Chiudi NeoTracker (dal Task Manager, processo Python) e riaprilo dall'icona."))
                    return
                print("NeoTracker è già acceso: apro una finestra.")
                apri_finestra(url + (f"?avvio={chiave}" if chiave else ""))
            return

        # ---- caso 2: avvio normale ----
        try:
            server = Server((INDIRIZZO, PORTA), Gestore)
        except OSError as e:
            mostra_errore(testo_avvio("NeoTracker non si avvia"),
                          testo_avvio("Non riesco a usare la porta {porta} ({e}).\n"
                                      "Un altro programma la sta usando. Chiudilo oppure cambia PORTA in cima al file neotracker.py.",
                                      porta=PORTA, e=e))
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
        mostra_errore(testo_avvio("NeoTracker si è fermato"), f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    avvia()
