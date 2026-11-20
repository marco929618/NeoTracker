# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# NeoTracker - Copyright (C) 2026 the NeoTracker authors.
# Free software: you can redistribute it and/or modify it under the terms of the GNU General Public License
# version 3 or later. No warranty, not even of fitness for a purpose (see the LICENSE file).
# NOT a medical device and it does not diagnose: see DISCLAIMER.md.
"""
==========================================================================================
 NeoTracker  -  body map, mole history, automatic analysis, UV index and literature
==========================================================================================

WHAT IT IS
----------
An app that runs ONLY on your PC. It has a window of its own (no address bar, with its own
icon in the taskbar): under the hood it uses the Edge or Chrome already installed on the PC,
in "app" mode. No data is uploaded to the internet, except for these requests, which you control:
  - the Open-Meteo weather service (default, free) for today's UV index, or OpenWeather
    if you choose it in Settings and enter your own key;
  - PubMed (a public scientific database) for the literature;
  - SkinSense (an online service) ONLY if you turn it on in Settings.

WHAT IT DOES
------------
  1. Several users on the same PC: at start-up you choose who you are (everyone has their own data).
  2. Profile with phenotype (phototype, hair, eyes, moles...) and family history.
  3. Interactive body map (front and back): you click where the mole is and the
     point is saved precisely. You can zoom, move the point, rename it.
  4. Photo history of every mole: each photo is saved with its date; you can compare
     two of them, measure the diameter over time and print a sheet for the dermatologist.
  5. Automatic analysis of every photo with all the installed methods (uses melanoma_batch.py).
  6. Scientific literature (PubMed) on nevus recognition and hereditary melanoma,
     with the genes to know about and the criteria for evaluating genetic counselling/testing.
  7. Today's UV index where you are (source Open-Meteo; OpenWeather if you choose it).

HOW TO START IT
---------------
  - From the "NeoTracker" icon on the Desktop (only the app window opens, no black
    window), or
  - by opening this file with Spyder and pressing PLAY (the green arrow).
To STOP the app, just close its window with the X: the program shuts itself down
(if it is analysing a photo, it finishes the analysis first). If something goes wrong, the file
"neotracker.log" in the data folder tells you what happened.

IMPORTANT
---------
NeoTracker is NOT a medical tool and does not diagnose. The neural networks used are
research prototypes. Phototype, age and family history do NOT change the result of the networks
(which only look at the pixels of the photo): they serve to put the risk in context and to choose
the right literature. Every mole that changes, bleeds, itches or worries you must be shown
to a dermatologist, whatever the app says.
"""

# ==========================================================================================
# 1. SETTINGS (you usually do not need to touch them)
# ==========================================================================================
import os
from pathlib import Path

# Folder where ALL the data is saved (database, photos, reports). If you move it, also move the data that
# already exists. The default value is next to your projects. (To change it without touching the code you can
# set the NEOTRACKER_DATI environment variable.)
CARTELLA_DATI = Path(os.environ.get("NEOTRACKER_DATI") or (Path.home() / "melanoma-repos" / "NeoTracker_dati"))

# Folder where the analysis projects are installed (needed to launch melanoma_batch.py). (Optional environment
# variable: NEOTRACKER_REPO.)
CARTELLA_REPO = Path(os.environ.get("NEOTRACKER_REPO") or (Path.home() / "melanoma-repos"))

# Address and port of the local mini-server. 127.0.0.1 means "only this computer": no other device on the
# network can connect.
INDIRIZZO = "127.0.0.1"
PORTA = 8750

# How old a cached literature search can be before it is redone (days).
GIORNI_CACHE_LETTERATURA = 7

# Maximum size of an uploaded photo (megabytes).
MAX_MB_FOTO = 60

# Maximum size of a photo in "megapixels" (width x height). It protects against trap images, small as files
# but huge once opened, which would fill the memory.
MAX_PIXEL_IMMAGINE = 150_000_000

# ==========================================================================================
# 2. LIBRARIES (all included in Python, except Pillow which is usually already there)
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
    from PIL import Image, ImageOps          # Pillow: needed for thumbnails, rotation and the shooting date
    HA_PILLOW = True
except Exception:                            # without Pillow the app still works, but without thumbnails
    HA_PILLOW = False

VERSIONE = "1.3"
# Version of the start-up notice ("this is not a medical device..."). If you change it, all users see it again
# and accept it again.
AVVERTENZE_VERSIONE = "1"

# Interface languages. English is the source text of the app; the others are translations (web/i18n_XX.js). In
# Settings you can also choose "auto" = follow the system/browser language.
LINGUE = ("en", "it", "fr", "de", "es")


def T(testo):
    """Marks an English text meant for the user: the browser translates it with the dictionary of the chosen language
    (web/i18n_XX.js), looking it up in full or, if it contains variable values, by "shape" (e.g. "{n} days").
    At runtime it does nothing: build.py uses it to check that every marked text has its translation."""
    return testo
CARTELLA_SCRIPT = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()


# ==========================================================================================
# 3. DATA: SQLite database, settings, folders
# ==========================================================================================
# SQLite is a "database in a file" included in Python: nothing to install. All the data
# (users, moles, photos) is in CARTELLA_DATI\neotracker.db. The photos are in CARTELLA_DATI\foto.

def percorso_db():
    return Path(CARTELLA_DATI) / "neotracker.db"


def adesso():
    """Current date and time as ISO text, e.g. '2026-11-08T10:52:31'."""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def connetti():
    """Opens a database connection. Every request opens its own (it is safer)."""
    Path(CARTELLA_DATI).mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(percorso_db()), timeout=30)
    con.row_factory = sqlite3.Row            # lets you read the columns by name
    con.execute("PRAGMA foreign_keys = ON")  # if you delete a user, their moles disappear too
    return con


# Databases created by versions up to 1.2 stored the body regions and the suggested sites in Italian
# (e.g. 'Spalla destra'). From version 1.3 the stored text is the English one ('Shoulder, right'): at start-up
# the old names are converted with this table (the Italian names are kept here only for this purpose).
NOMI_SEDI_ITALIANI = {
    "Addome alto destro": "Upper abdomen, right",
    "Addome alto sinistro": "Upper abdomen, left",
    "Addome basso destro": "Lower abdomen, right",
    "Addome basso sinistro": "Lower abdomen, left",
    "Avambraccio destro": "Forearm, right",
    "Avambraccio sinistro": "Forearm, left",
    "Braccio destro": "Arm, right",
    "Braccio sinistro": "Arm, left",
    "Caviglia destra": "Ankle, right",
    "Caviglia sinistra": "Ankle, left",
    "Cavo popliteo destro": "Back of knee, right",
    "Cavo popliteo sinistro": "Back of knee, left",
    "Collo": "Neck",
    "Coscia destra": "Thigh, right",
    "Coscia sinistra": "Thigh, left",
    "Cuoio capelluto (testa)": "Scalp (head)",
    "Fronte e cuoio capelluto": "Forehead and scalp",
    "Gamba (stinco) destra": "Lower leg (shin), right",
    "Gamba (stinco) sinistra": "Lower leg (shin), left",
    "Ginocchio destro": "Knee, right",
    "Ginocchio sinistro": "Knee, left",
    "Gluteo destro": "Buttock, right",
    "Gluteo sinistro": "Buttock, left",
    "Gomito destro": "Elbow, right",
    "Gomito sinistro": "Elbow, left",
    "Inguine destro": "Groin, right",
    "Inguine sinistro": "Groin, left",
    "Mano destra": "Hand, right",
    "Mano sinistra": "Hand, left",
    "Nuca e collo": "Nape and neck",
    "Orecchio destro": "Ear, right",
    "Orecchio sinistro": "Ear, left",
    "Piede destro": "Foot, right",
    "Piede sinistro": "Foot, left",
    "Polpaccio destro": "Calf, right",
    "Polpaccio sinistro": "Calf, left",
    "Regione lombare destra": "Lower back, right",
    "Regione lombare sinistra": "Lower back, left",
    "Regione scapolare destra": "Shoulder blade area, right",
    "Regione scapolare sinistra": "Shoulder blade area, left",
    "Schiena (zona media) destra": "Back (middle area), right",
    "Schiena (zona media) sinistra": "Back (middle area), left",
    "Spalla destra": "Shoulder, right",
    "Spalla sinistra": "Shoulder, left",
    "Torace destro": "Chest, right",
    "Torace sinistro": "Chest, left",
    "Viso": "Face",
    "cuoio capelluto": "scalp",
    "dorso del piede": "top of the foot",
    "dorso della mano": "back of the hand",
    "labbro": "lip",
    "orecchio": "ear",
    "palmo della mano": "palm of the hand",
    "palpebra": "eyelid",
    "pianta del piede": "sole of the foot",
    "sotto l'unghia (mano)": "under the nail (hand)",
    "sotto l'unghia (piede)": "under the nail (foot)",
    "spazio tra le dita": "between the fingers or toes",
}


def inizializza_db():
    """Creates the tables the first time. If they already exist it does nothing."""
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
            regione    TEXT NOT NULL DEFAULT '',      -- e.g. 'Chest, right'
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
        # if at start-up some analyses are left "in progress" (app closed halfway), mark them as interrupted
        con.execute("UPDATE foto SET stato_analisi='errore', messaggio=? WHERE stato_analisi IN ('in_corso', 'in_coda')",
                    (T("Analysis interrupted (app closed)."),))
        for vecchio, nuovo in NOMI_SEDI_ITALIANI.items():           # old Italian names -> English names
            con.execute("UPDATE nevi SET regione=? WHERE regione=?", (nuovo, vecchio))


def riga_a_dict(riga):
    return dict(riga) if riga is not None else None


# ---- settings (API keys, location, switches) ----------------------------------------------
IMPOSTAZIONI_PREDEFINITE = {
    "avvertenze_accettate": "",   # version of the start-up notice already accepted (empty = not accepted yet)
    "fonte_uv": "open-meteo",     # where the UV index comes from: "open-meteo" (default, free, no key) or "openweather"
    "openweather_key": "",        # your OpenWeather key (only needed if you choose OpenWeather; it stays only on this PC)
    "usa_skinsense": False,       # if True the photo is sent to SkinSense (online service)
    "lat": None, "lon": None,     # location for the UV index
    "localita": "",               # name of the place (e.g. 'Torino, IT')
    "ncbi_email": "",             # optional: your email, as a courtesy to PubMed
    "lingua": "auto",             # interface language: "auto" (same as the system/browser) or en, it, fr, de, es
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
    Language to use outside the browser (for example in the start-up error windows): the one chosen
    in Settings or, with "auto", the one of the system. If the system uses an unsupported
    language, English is used.
    """
    scelta = leggi_impostazioni().get("lingua")
    if scelta in LINGUE:
        return scelta
    codice = ""
    try:
        import locale
        codice = (locale.getlocale()[0] or os.environ.get("LANG") or "")[:2].lower()
        if os.name == "nt":                       # Windows interface language (more reliable)
            import ctypes
            codice = {0x10: "it", 0x09: "en", 0x0C: "fr", 0x07: "de", 0x0A: "es"}.get(
                ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF, codice)
    except Exception:
        pass
    return codice if codice in LINGUE else "en"


def salva_impostazioni(nuove):
    """Updates only the allowed fields and saves to file."""
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
            os.chmod(provvisorio, 0o600)          # the file contains your key: readable only by you (Linux/Mac)
        os.replace(provvisorio, destinazione)     # replace "all at once": an interruption does not leave a half-written file
        return dati


def impostazioni_pubbliche():
    """Version for the browser: the secret key is NEVER returned, only whether it is there."""
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


# ==========================================================================================
# 5. PHOTOS AND ANALYSIS: saving, thumbnails, shooting date, automatic analysis in a queue
# ==========================================================================================

class ErroreRichiesta(Exception):
    """Error caused by wrong data sent by the browser (becomes a 400/404/409 response)."""
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
    """True if 'percorso' really is inside 'cartella_base' (defence against paths like ..\\..)."""
    try:
        Path(percorso).resolve().relative_to(Path(cartella_base).resolve())
        return True
    except (ValueError, OSError):
        return False


# ------------------------------------------------------------------------------------------
# 5a. Checking and saving the photo
# ------------------------------------------------------------------------------------------
def riconosci_formato(dati):
    """Looks at the first bytes of the file (not the extension) and says what kind of image it is. None if not supported."""
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
    """Shooting date written by the camera in the photo (YYYY-MM-DD), or None."""
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
    """Checks that the text is a YYYY-MM-DD date not in the future; returns the cleaned text."""
    try:
        d = datetime.strptime((testo or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ErroreRichiesta(T("Invalid date: use the format YYYY-MM-DD."))
    if d > date.today() + timedelta(days=1):
        raise ErroreRichiesta(T("The photo date cannot be in the future."))
    if d.year < 1990:
        raise ErroreRichiesta(T("Photo date is too old."))
    return d.isoformat()


def numero_o_vuoto(testo, minimo, massimo, nome):
    """Reads an optional decimal number (comma or point) within a range; '' means 'not given'."""
    if testo is None or str(testo).strip() == "":
        return None
    try:
        v = float(str(testo).replace(",", "."))
    except ValueError:
        raise ErroreRichiesta(T(f"{nome}: enter a number."))
    if not (minimo <= v <= massimo):
        raise ErroreRichiesta(T(f"{nome}: the value must be between {minimo} and {massimo}."))
    return round(v, 1)


def salva_foto(nevo_id, dati, data, usa_exif, tipo, diametro, note):
    """
    Saves a photo in the mole's history. The original is kept WITHOUT changes
    (it is the 'historical photo'). Returns the photo id and the date actually used.
    """
    if not dati:
        raise ErroreRichiesta(T("The file is empty."))
    if len(dati) > MAX_MB_FOTO * 1024 * 1024:
        raise ErroreRichiesta(T(f"The photo exceeds {MAX_MB_FOTO} MB."), 413)
    ext = riconosci_formato(dati)
    if ext is None:
        raise ErroreRichiesta(T("Unsupported format: JPG, PNG, WEBP or BMP are required. iPhone HEIC photos must "
                                "be converted to JPG (camera settings: 'Most Compatible')."))
    if tipo not in ("normale", "dermoscopica"):
        tipo = "normale"
    data_exif_trovata = None
    if HA_PILLOW:
        try:
            Image.MAX_IMAGE_PIXELS = MAX_PIXEL_IMMAGINE
            with Image.open(io.BytesIO(dati)) as img:
                if img.width * img.height > MAX_PIXEL_IMMAGINE:        # trap image: huge once opened
                    raise ValueError("too large")
                img.verify()
            with Image.open(io.BytesIO(dati)) as img:
                data_exif_trovata = data_exif(img)
        except Exception:
            raise ErroreRichiesta(T("The file is not a readable image, is damaged or has too many pixels "
                                    "(maximum {mp} megapixels).").format(mp=MAX_PIXEL_IMMAGINE // 1_000_000))
    data_finale = data_exif_trovata if (usa_exif and data_exif_trovata) else data_valida(data or date.today().isoformat())
    diam = numero_o_vuoto(diametro, 0.5, 100, T("Diameter (mm)"))
    note = (note or "").strip()[:1000]

    with connetti() as con:
        nevo = con.execute("SELECT id, utente_id FROM nevi WHERE id=?", (nevo_id,)).fetchone()
        if nevo is None:
            raise ErroreRichiesta(T("Mole not found."), 404)
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
    """Full path of the original file of a photo (only if it is inside the photos folder)."""
    p = cartella_foto() / riga_foto["file"]
    return p if dentro(cartella_foto(), p) and p.exists() else None


def miniatura(foto_id, utente_id, riga_foto, lato):
    """JPEG thumbnail of the photo (correctly rotated, without metadata). Returns (bytes, MIME type)."""
    orig = percorso_foto(riga_foto)
    if orig is None:
        raise ErroreRichiesta(T("Photo file not found."), 404)
    if not HA_PILLOW:
        return orig.read_bytes(), (mimetypes.guess_type(str(orig))[0] or "application/octet-stream")
    lato = lato if lato in (120, 240, 480, 960, 1600) else 480
    cache = cartella_miniature() / f"u{utente_id}" / f"f{foto_id}_{lato}.jpg"
    if cache.exists() and cache.stat().st_mtime >= orig.stat().st_mtime:
        return cache.read_bytes(), "image/jpeg"
    Image.MAX_IMAGE_PIXELS = MAX_PIXEL_IMMAGINE
    with Image.open(orig) as img:
        try:
            img.draft("RGB", (lato * 2, lato * 2))      # for JPEGs: it already reads them small (much faster)
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
    """Removes the photo, its thumbnails and its report from the disk."""
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
# 5a-bis. Personal image (avatar) of the user
# ------------------------------------------------------------------------------------------
# The user can choose an image of their own (even an icon or a drawing, not necessarily their
# face). It stays on the PC: it is saved as a small square 256x256 JPEG in CARTELLA_DATI\avatar.
# It is never used for the analysis of the moles nor sent to external services.
LATO_AVATAR = 256
MAX_BYTE_AVATAR = 8 * 1024 * 1024          # the chosen image can be large; it is reduced afterwards


def percorso_avatar(utente_id):
    return cartella_avatar() / f"u{int(utente_id)}.jpg"


def versione_avatar(utente_id):
    """A number that changes every time the image changes (the browser uses it to avoid using an old copy). 0 = none."""
    try:
        return int(percorso_avatar(utente_id).stat().st_mtime_ns // 1_000_000)
    except OSError:
        return 0


def salva_avatar(utente_id, dati):
    """Checks the image, crops it to a square at the centre, reduces it and saves it as a JPEG
    WITHOUT metadata (no GPS or camera data). Without Pillow it only accepts an already small JPEG/PNG."""
    if not dati:
        raise ErroreRichiesta(T("The file is empty."))
    if len(dati) > MAX_BYTE_AVATAR:
        raise ErroreRichiesta(T("The image exceeds {mb} MB.").format(mb=MAX_BYTE_AVATAR // (1024 * 1024)), 413)
    ext = riconosci_formato(dati)
    if ext not in (".jpg", ".png", ".webp", ".bmp"):
        raise ErroreRichiesta(T("Unsupported format: JPG, PNG, WEBP or BMP are required."))
    if HA_PILLOW:
        try:
            Image.MAX_IMAGE_PIXELS = MAX_PIXEL_IMMAGINE
            with Image.open(io.BytesIO(dati)) as img:
                if img.width * img.height > MAX_PIXEL_IMMAGINE:
                    raise ValueError("too large")
                try:
                    img.draft("RGB", (LATO_AVATAR * 2, LATO_AVATAR * 2))
                except Exception:
                    pass
                img = ImageOps.exif_transpose(img)
                if img.mode in ("RGBA", "LA", "P"):                     # white background instead of transparency
                    img = img.convert("RGBA")
                    fondo = Image.new("RGB", img.size, (255, 255, 255))
                    fondo.paste(img, mask=img.split()[-1])
                    img = fondo
                else:
                    img = img.convert("RGB")
                img = ImageOps.fit(img, (LATO_AVATAR, LATO_AVATAR), method=Image.LANCZOS)   # central crop + reduction
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=88, optimize=True)         # new file: no original metadata
            dati_finali = buf.getvalue()
        except ErroreRichiesta:
            raise
        except Exception:
            raise ErroreRichiesta(T("The file is not a readable image or is too large."))
    else:
        if ext not in (".jpg", ".png") or len(dati) > 400 * 1024:
            raise ErroreRichiesta(T("Without Pillow the image must be a JPG/PNG under 400 KB (the page reduces "
                                    "it by itself: try again with the 'Choose image' function)."))
        dati_finali = dati
    dest = percorso_avatar(utente_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_bytes(dati_finali)
    os.replace(tmp, dest)                                                # "atomic" write: no half-written files
    return versione_avatar(utente_id)


def cancella_avatar(utente_id):
    try:
        percorso_avatar(utente_id).unlink(missing_ok=True)
    except OSError:
        pass


# ------------------------------------------------------------------------------------------
# 5b. Automatic analysis (uses melanoma_batch.py) - one at a time, in a queue
# ------------------------------------------------------------------------------------------
_coda_analisi = []                       # ids of the photos waiting
_blocco_coda = threading.Lock()
_thread_analisi = [None]
_processo_attuale = {"foto": None, "popen": None}
TIMEOUT_ANALISI_S = 3 * 3600             # maximum time for one photo (the models are heavy)


def analisi_attiva():
    """True if there is at least one analysis queued or running.

    It serves to NOT shut the program down while it is still working on a photo: the analysis can
    take minutes (the models are heavy) and closing the window must not throw it away.
    """
    with _blocco_coda:
        if _coda_analisi:
            return True
    t = _thread_analisi[0]
    return t is not None and t.is_alive()


def eseguibile_python():
    """Path of the Python to use to launch the analysis.

    If NeoTracker was started WITHOUT a black window (with "pythonw.exe", as the icon on the
    Desktop does), the analysis still needs "python.exe" (with pythonw programs cannot
    write text). We then launch it with CREATE_NO_WINDOW, so no window appears.
    """
    exe = Path(sys.executable)
    if os.name == "nt" and exe.name.lower() == "pythonw.exe":
        candidato = exe.with_name("python.exe")
        if candidato.exists():
            return str(candidato)
    return str(exe)


def trova_batch():
    """Looks for melanoma_batch.py next to this file or in the projects folder."""
    for c in (CARTELLA_SCRIPT / "melanoma_batch.py", Path(CARTELLA_REPO) / "melanoma_batch.py"):
        if c.exists():
            return c
    return None


def stato_installazione():
    """What is ready on the PC (shown in Settings, to see at once what is missing)."""
    repo = Path(CARTELLA_REPO)
    app1, vatsal = repo / "DeborahAdedigba_Melanoma-Detection_App", repo / "vatsal30_Melanoma-Detection"
    n_app1 = len(list(app1.glob("*.keras"))) + len(list(app1.glob("*.weights.h5"))) if app1.exists() else 0
    n_vat = len(list((vatsal / "model").glob("model_fold_*.bin"))) if vatsal.exists() else 0
    return {"batch": str(trova_batch()) if trova_batch() else "", "repo": str(repo),
            "progetti": [
                {"nome": T("Method 1 - App 1 (Deborah Adedigba)"), "presente": app1.exists(),
                 "dettaglio": T("{n} model files out of 10").format(n=n_app1)},
                {"nome": T("Method 2 - SkinSense (online service)"), "presente": True,
                 "dettaglio": T("active only if you enable it below")},
                {"nome": T("Method 4 - vatsal30"), "presente": vatsal.exists(),
                 "dettaglio": T("{n} model files out of 5").format(n=n_vat)},
            ]}


def _scrivi_stato(foto_id, **campi):
    with connetti() as con:
        imp = ", ".join(f"{k}=?" for k in campi)
        # Security check (bandit B608): the column names are written by us, the values go in as parameters.
        con.execute(f"UPDATE foto SET {imp} WHERE id=?", (*campi.values(), foto_id))   # nosec B608


def accoda_analisi(foto_id):
    """Puts the photo in the analysis queue (if it is not already there). It starts by itself in a thread."""
    with connetti() as con:
        r = con.execute("SELECT stato_analisi FROM foto WHERE id=?", (foto_id,)).fetchone()
        if r is None:
            raise ErroreRichiesta(T("Photo not found."), 404)
        if r["stato_analisi"] in ("in_coda", "in_corso"):
            return r["stato_analisi"]
        if trova_batch() is None:
            raise ErroreRichiesta(T("I cannot find melanoma_batch.py: it must be in the same folder as "
                                    f"neotracker.py (or in {CARTELLA_REPO})."), 409)
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
        except Exception as e:                       # any mishap: I mark an error and go on to the next one
            traceback.print_exc()
            try:
                _scrivi_stato(foto_id, stato_analisi="errore", messaggio=T(f"Unexpected error: {e}"))
            except Exception:
                pass


def _copia_per_analisi(origine, destinazione):
    """Clean copy for the models: rotated as in the original, without metadata (GPS etc.), RGB, JPEG."""
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
        return                                       # photo deleted while it was queued
    origine = percorso_foto(r)
    if origine is None:
        _scrivi_stato(foto_id, stato_analisi="errore", messaggio=T("Photo file not found."))
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
        # stdin=DEVNULL: when started without a black window there is no "keyboard" to inherit and Windows
        # would give the "invalid handle" error; this way the child process always starts.
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                             cwd=str(batch.parent), env=env, creationflags=flag)
        _processo_attuale.update(foto=foto_id, popen=p)
        try:
            p.wait(timeout=TIMEOUT_ANALISI_S)
        except subprocess.TimeoutExpired:
            p.kill()
            _processo_attuale.update(foto=None, popen=None)
            _scrivi_stato(foto_id, stato_analisi="errore",
                          messaggio=T("Analysis stopped after {ore} hours (too long).").format(ore=TIMEOUT_ANALISI_S // 3600))
            return
        finally:
            _processo_attuale.update(foto=None, popen=None)

    sint = sintesi_rapporto(rel)
    if sint is None:
        coda_log = ultime_righe(cartella / "log_analisi.txt", 6)
        _scrivi_stato(foto_id, stato_analisi="errore",
                      messaggio=T("The analysis did not produce the report. Last lines of the log: {log}").format(log=coda_log or T("(empty)")))
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
    """Last lines of the log of an analysis in progress (to show 'Method 2: starting...')."""
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
    """Same criterion as melanoma_batch.py: 'attenzione' | 'benigno' | 'discordante' | None."""
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
    Reads rapporto.json and reduces it to a summary for the interface:
    for each method: verdict, count ("4 out of 5 say ...") and rows per model.
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
        frase = "; ".join(T("{n} of {tot}: {et}").format(n=n, tot=len(ok), et=et) for et, n in sorted(conteggi.items(), key=lambda kv: -kv[1]))
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
# 5c. LIFE OF THE WINDOW: how the program understands that you closed the app window
# ==========================================================================================
# IDEA (explained simply)
# ------------------------
# NeoTracker is made of two parts that talk to each other:
# - the "engine" (this Python program), which saves the data and analyses the photos;
# - the "window" (Edge or Chrome opened in app mode, i.e. without an address bar
# and without tabs), which shows the page.
# When you close the window, the engine must shut itself down. But the engine cannot
# "hear" the closing directly: so the page sends it a small signal ("heartbeat")
# every few seconds, like a beating heart. If the heartbeats stop, the window is closed.
#
# - every open page has its own random number (id) and sends a "heartbeat" every ~5 seconds;
# - when the page is closed it also tries to send a "goodbye" (immediate close);
# - if for 6 seconds there is NO page open any more, the engine shuts down (the 6 seconds
# are needed because pressing F5 / "reload" makes the page disappear and reappear in an instant:
# we do not want to shut everything down for a reload);
# - if the window freezes or the PC goes to sleep without a "goodbye", after 3 minutes of
# silence the page is considered closed;
# - if the engine is STILL analysing a photo, it waits for the analysis to finish and then shuts down
# (so you do not lose the work); if in the meantime you reopen the icon, the window comes back.

GRAZIA_CHIUSURA_S = 6          # seconds without open pages before shutting down (covers reloading)
SILENZIO_MASSIMO_S = 180       # a page that stays silent for 3 minutes is considered closed (frozen window)
FINESTRA_APERTA_S = 90         # within how many seconds of the last heartbeat we say "the window is open"
ATTESA_PRIMA_FINESTRA_S = 600  # if no window opens within 10 minutes of start-up, we shut down


class StatoFinestra:
    """Keeps count of the open pages and says when the program must shut down.

    The time is always passed by the caller (parameter `adesso`, in seconds): so in the tests
    we can simulate minutes and hours in an instant, without really waiting.
    """

    def __init__(self, adesso=None):
        self._blocco = threading.Lock()                       # prevents two requests from modifying at the same time
        self.avviato = time.monotonic() if adesso is None else adesso
        self.pagine = {}                                      # page id -> instant of the last heartbeat
        self.vista_almeno_una = False                         # has a window ever appeared?
        self.vuoto_da = None                                  # since when there have been no pages (None = there is at least one)
        self.chiuse = {}                                      # pages that said "goodbye": they can no longer "reopen"

    def azzera(self, adesso=None):
        """Starts over (called when the server starts): no page, no window ever seen."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            self.avviato, self.pagine, self.vista_almeno_una, self.vuoto_da = adesso, {}, False, None
            self.chiuse = {}

    # ---- signals coming from the page ----
    def battito(self, id_pagina, adesso=None):
        """A page says "I am still here"."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            if id_pagina in self.chiuse:
                return          # a late heartbeat (arrived after the goodbye) must not "resurrect" a closed page
            self.pagine[id_pagina] = adesso
            self.vista_almeno_una = True
            self.vuoto_da = None                              # there is at least one page: cancels any pending shutdown

    def addio(self, id_pagina, adesso=None, definitivo=False):
        """A page is gone.
        definitivo=True: the page itself tells us "I am closing" -> from now on its possible late heartbeats
        are ignored. definitivo=False: we infer it from the dropped connection (it could
        be just a momentary interruption: if the page reappears with the same number, it counts)."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            self.pagine.pop(id_pagina, None)
            if definitivo:
                self.chiuse[id_pagina] = adesso
                while len(self.chiuse) > 500:                 # we do not keep the list forever
                    del self.chiuse[next(iter(self.chiuse))]
            if not self.pagine and self.vuoto_da is None:
                self.vuoto_da = adesso                        # the 6-second countdown starts

    # ---- questions the program asks ----
    def _togli_pagine_mute(self, adesso):
        """Forgets the pages that have not beaten for too long (window frozen or closed by force)."""
        mute = [i for i, t in self.pagine.items() if adesso - t > SILENZIO_MASSIMO_S]
        for i in mute:
            del self.pagine[i]
        if mute and not self.pagine and self.vuoto_da is None:
            self.vuoto_da = adesso

    def finestra_aperta(self, adesso=None):
        """True if there is a page that has beaten recently (needed when the icon is opened a second time)."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            return any(adesso - t <= FINESTRA_APERTA_S for t in self.pagine.values())

    def dopo_sospensione(self, adesso=None):
        """The PC has just woken up: during sleep no page could beat,
        so we pretend that all of them have beaten now (otherwise they would seem closed)."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            for i in self.pagine:
                self.pagine[i] = adesso
            if self.vuoto_da is not None:
                self.vuoto_da = adesso
            self.avviato = max(self.avviato, adesso - 1)

    def da_spegnere(self, adesso=None, analisi_in_corso=False):
        """True when the program must close. Called every second by the "supervisor"."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            self._togli_pagine_mute(adesso)
            if self.pagine:
                return False                                  # there is still at least one open window
            if analisi_in_corso:
                return False                                  # do not interrupt an analysis: it will finish and then we shut down
            if self.vista_almeno_una:
                return self.vuoto_da is not None and adesso - self.vuoto_da >= GRAZIA_CHIUSURA_S
            return adesso - self.avviato >= ATTESA_PRIMA_FINESTRA_S   # no window has ever appeared


STATO_FINESTRA = StatoFinestra()


# ==========================================================================================
# 6. LOCAL SERVER: the browser talks to this program through "addresses" (API)
# ==========================================================================================
# You do not need to understand this part to use the app. In short: the web page (HTML/JS) asks for
# data at addresses like /api/utenti or /api/nevi/3, and below there is the function that
# answers each address.

WEB_FILES = {}       # filled in by the embedded "web pages" part by the build script


# ------------------------------------------------------------------------------------------
# 6a. Profile (phenotype and family history): which fields exist and how they are checked
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
    """Keeps only the expected fields and checks them one by one. Strange values become 'empty'."""
    out = {}
    if not isinstance(grezzo, dict):
        raise ErroreRichiesta(T("Invalid profile."))
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
                    raise ErroreRichiesta(T("Invalid date of birth (YYYY-MM-DD)."))
                if not (date(1900, 1, 1) <= d <= date.today()):
                    raise ErroreRichiesta(T("Date of birth out of range."))
            out[campo] = v
        elif tipo == "testo":
            out[campo] = (str(v) if v is not None else "").strip()[:regola]
    # consistency: first-degree relatives are part of the total number of relatives
    if "fam_pancreas" in out or "fam_pancreas_1grado" in out:
        a, b = out.get("fam_pancreas", grezzo.get("fam_pancreas", 0)), out.get("fam_pancreas_1grado", grezzo.get("fam_pancreas_1grado", 0))
        out["fam_pancreas"] = max(a_intero(a), a_intero(b))
    return out


def profilo_completo(testo_json):
    """Saved profile + empty values for the fields never filled in (so the browser always finds everything)."""
    try:
        salvato = json.loads(testo_json or "{}")
    except ValueError:
        salvato = {}
    base = {}
    for campo, (tipo, regola) in CAMPI_PROFILO.items():
        base[campo] = False if tipo == "bool" else (0 if tipo == "intero" else "")
    base.update({k: v for k, v in salvato.items() if k in base})
    return base


def nome_valido(testo, minimo=1, massimo=60, cosa=T("The name")):
    t = re.sub(r"\s+", " ", (testo or "")).strip()
    if len(t) < minimo:
        raise ErroreRichiesta(T(f"{cosa} cannot be empty."))
    if len(t) > massimo:
        raise ErroreRichiesta(T(f"{cosa} is too long (maximum {massimo} characters)."))
    return t


# ------------------------------------------------------------------------------------------
# 6b. Functions that answer the various addresses
# ------------------------------------------------------------------------------------------
class Richiesta:
    """Everything a function needs to answer: address, parameters, body."""
    def __init__(self, gestore, metodo, percorso, query, gruppi):
        self.gestore, self.metodo, self.percorso, self.query, self.gruppi = gestore, metodo, percorso, query, gruppi
        self._corpo = None

    def q(self, nome, predefinito=""):
        return (self.query.get(nome) or [predefinito])[0]

    def corpo(self, massimo=2 * 1024 * 1024):
        if self._corpo is None:
            lung = a_intero(self.gestore.headers.get("Content-Length"), 0)
            if lung > massimo:
                raise ErroreRichiesta(T("Request too large."), 413)
            self._corpo = self.gestore.rfile.read(lung) if lung > 0 else b""
        return self._corpo

    def json(self):
        try:
            d = json.loads(self.corpo().decode("utf-8") or "{}")
        except ValueError:
            raise ErroreRichiesta(T("Invalid data (JSON)."))
        if not isinstance(d, dict):
            raise ErroreRichiesta(T("Invalid data."))
        return d


class RispostaFile:
    def __init__(self, dati, mime, extra=None):
        self.dati, self.mime, self.extra = dati, mime, extra or {}


def get_utente(con, uid):
    r = con.execute("SELECT * FROM utenti WHERE id=?", (uid,)).fetchone()
    if r is None:
        raise ErroreRichiesta(T("User not found."), 404)
    return r


def get_nevo(con, nid):
    r = con.execute("SELECT * FROM nevi WHERE id=?", (nid,)).fetchone()
    if r is None:
        raise ErroreRichiesta(T("Mole not found."), 404)
    return r


def get_foto(con, fid):
    r = con.execute("SELECT f.*, n.utente_id FROM foto f JOIN nevi n ON n.id=f.nevo_id WHERE f.id=?", (fid,)).fetchone()
    if r is None:
        raise ErroreRichiesta(T("Photo not found."), 404)
    return r


# ---- general -----------------------------------------------------------------------------
def api_ping(rq):
    # "finestra_aperta" is for whoever reopens the icon while the app is already running: if a window exists,
    # we bring it to the front instead of opening a second one.
    return {"app": "NeoTracker", "versione": VERSIONE, "finestra_aperta": STATO_FINESTRA.finestra_aperta(),
            "protetto": True}


def _id_pagina(rq):
    """Reads and checks the random number that identifies the open page (letters/digits/hyphens only)."""
    i = str(rq.json().get("id", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", i):
        raise ErroreRichiesta(T("Invalid page identifier."))
    return i


def api_battito(rq):
    """The open page says "I am still here" (see 5c: life of the window)."""
    STATO_FINESTRA.battito(_id_pagina(rq))
    return {"ok": True}


def api_addio(rq):
    """The page is closing: if it was the last one, the program shuts down in a few seconds."""
    STATO_FINESTRA.addio(_id_pagina(rq), definitivo=True)
    return {"ok": True}


def pillow_obsoleto():
    """True if Pillow is older than the minimum recommended version (10.3.0: it contains the security fixes
    on opening images). NeoTracker opens files you choose: keeping Pillow up to date matters."""
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


# ---- users -------------------------------------------------------------------------------
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
            raise ErroreRichiesta(T("A user with this name already exists."), 409)
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
            raise ErroreRichiesta(T("A user with this name already exists."), 409)
        con.execute("UPDATE utenti SET nome=? WHERE id=?", (nome, u["id"]))
    return {"ok": True, "nome": nome}


def api_utente_elimina(rq):
    uid = int(rq.gruppi[0])
    with connetti() as con:
        u = get_utente(con, uid)
        if rq.json().get("conferma") != u["nome"]:
            raise ErroreRichiesta(T("To delete, type the exact name of the user in the confirmation."))
        con.execute("DELETE FROM utenti WHERE id=?", (uid,))
    cancella_cartelle_utente(uid)
    return {"ok": True}


# ---- personal image of the user (avatar) -------------------------------------------------
def api_avatar_leggi(rq):
    uid = int(rq.gruppi[0])
    with connetti() as con:
        get_utente(con, uid)
    p = percorso_avatar(uid)
    if not p.exists():
        raise ErroreRichiesta(T("No image set."), 404)
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


# ---- moles -------------------------------------------------------------------------------
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
            raise ErroreRichiesta(T("The view must be 'fronte' or 'retro'."))
        out["vista"] = d["vista"]
    for c in ("x", "y"):
        if c in d or not parziale:
            try:
                v = float(d.get(c))
            except (TypeError, ValueError):
                raise ErroreRichiesta(T("Invalid location."))
            if not (0.0 <= v <= 1.0):
                raise ErroreRichiesta(T("Location outside the map."))
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
        nome = nome_valido(d.get("nome") or f"Mole {n + 1}")
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
        # Security check (bandit B608): the column names are written by us, the values go in as parameters.
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


# ---- photos ------------------------------------------------------------------------------
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
        campi["diametro_mm"] = numero_o_vuoto(d["diametro_mm"], 0.5, 100, T("Diameter (mm)"))
    if "tipo" in d and d["tipo"] in ("normale", "dermoscopica"):
        campi["tipo"] = d["tipo"]
    if "note" in d:
        campi["note"] = (d["note"] or "").strip()[:1000]
    with connetti() as con:
        get_foto(con, fid)
        if campi:
            # Security check (bandit B608): the column names are written by us, the values go in as
            # parameters.
            con.execute(f"UPDATE foto SET {', '.join(k + '=?' for k in campi)} WHERE id=?", (*campi.values(), fid))   # nosec B608
    return {"ok": True}


def api_foto_elimina(rq):
    fid = int(rq.gruppi[0])
    with connetti() as con:
        f = get_foto(con, fid)
        if f["stato_analisi"] in ("in_corso", "in_coda"):
            raise ErroreRichiesta(T("This photo is being analysed: wait for it to finish."), 409)
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
            raise ErroreRichiesta(T("Photo file not found."), 404)
        if p.suffix.lower() in (".tif", ".tiff"):                       # browsers do not show TIFFs
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


# ---- UV index, location, settings ----------------------------------------------------------
def _coordinate(rq):
    imp = leggi_impostazioni()
    try:
        lat = float(rq.q("lat") or imp.get("lat"))
        lon = float(rq.q("lon") or imp.get("lon"))
    except (TypeError, ValueError):
        raise ErroreRichiesta(T("Location not set: choose a city or use 'Detect my location'."))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ErroreRichiesta(T("Invalid coordinates."))
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
            raise ErroreRichiesta(T("The OpenWeather key contains invalid characters (it is usually 32 "
                                    "letters/digits)."))
        nuove["openweather_key"] = k
    if "fonte_uv" in d:
        if d["fonte_uv"] not in ("open-meteo", "openweather"):
            raise ErroreRichiesta(T("Invalid UV index source."))
        nuove["fonte_uv"] = d["fonte_uv"]
    if "usa_skinsense" in d:
        nuove["usa_skinsense"] = bool(d["usa_skinsense"])
    if "avvertenze_accettate" in d:
        if d["avvertenze_accettate"] not in ("", AVVERTENZE_VERSIONE):
            raise ErroreRichiesta(T("Invalid notice version."))
        nuove["avvertenze_accettate"] = d["avvertenze_accettate"]
    for c in ("lat", "lon"):
        if c in d:
            try:
                nuove[c] = None if d[c] in (None, "") else round(float(d[c]), 2)       # ~1 km: enough for the UV index, and less is sent
            except (TypeError, ValueError):
                raise ErroreRichiesta(T("Invalid coordinates."))
    if "localita" in d:
        nuove["localita"] = str(d["localita"] or "").strip()[:120]
    if "lingua" in d:
        if d["lingua"] != "auto" and d["lingua"] not in LINGUE:
            raise ErroreRichiesta(T("Language not supported."))
        nuove["lingua"] = d["lingua"]
    if "ncbi_email" in d:
        e = str(d["ncbi_email"] or "").strip()[:120]
        if e and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e):
            raise ErroreRichiesta(T("Invalid email address."))
        nuove["ncbi_email"] = e
    salva_impostazioni(nuove)
    _cache_uv.clear()
    return impostazioni_pubbliche()


def api_prova_owm(rq):
    imp = leggi_impostazioni()
    chiave = (imp.get("openweather_key") or "").strip()
    if not chiave:
        raise ErroreRichiesta(T("Save an OpenWeather key first."))
    lat, lon = imp.get("lat"), imp.get("lon")
    if lat is None or lon is None:
        lat, lon = 45.07, 7.69                       # failing anything else I try Turin
    try:
        d = _uv_openweather(float(lat), float(lon), chiave)
    except ErroreServizio as e:
        return {"ok": False, "messaggio": str(e)}
    return {"ok": True, "messaggio": T("It works: OpenWeather answers (current UV index: {uvi}).").format(uvi=d["uvi_ora"])}


# ---- literature and genetics ---------------------------------------------------------------
def _sezioni_per_utente(uid):
    """Complete list of the literature sections, with stable identifiers."""
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
    titoli["personale"] = T("Picked for you (based on profile and mole locations)")
    for t in ordine:
        elenco = [{"id": k, "titolo": v["titolo"]} for k, v in sezioni.items() if v["tema"] == t]
        if elenco:
            temi.append({"tema": t, "titolo": titoli[t], "sezioni": elenco})
    return temi


def api_lett_sezione(rq):
    sezioni = _sezioni_per_utente(a_intero(rq.q("utente"), 0))
    s = sezioni.get(rq.q("id"))
    if s is None:
        raise ErroreRichiesta(T("Unknown section."), 404)
    dati = pubmed_cerca(s["termine"], 5, s["ordina"], rq.q("forza") == "1")
    return dict(dati, titolo=s["titolo"], id=rq.q("id"))


def api_lett_cerca(rq):
    q = re.sub(r"[^\w\s\-\*\"'\.]", " ", rq.q("q"), flags=re.UNICODE).strip()[:200]
    if len(q) < 3:
        raise ErroreRichiesta(T("Type at least 3 characters."))
    dati = pubmed_cerca(f"({q}) AND melanoma[tiab]", 8, "relevance", rq.q("forza") == "1")
    return dict(dati, titolo=f"Results for: {q}")


def api_genetica_geni(rq):
    return {"geni": [{k: g[k] for k in ("gene", "rischio", "ruolo")} for g in GENI_MELANOMA], "fonti": FONTI_GENETICA}


def api_genetica_gene(rq):
    g = next((x for x in GENI_MELANOMA if x["gene"] == rq.q("nome")), None)
    if g is None:
        raise ErroreRichiesta(T("Gene not in the list."), 404)
    dati = pubmed_cerca(g["termine"], 3, "relevance", rq.q("forza") == "1")
    return dict(dati, gene=g["gene"])


# ------------------------------------------------------------------------------------------
# 6c. Table of addresses (method, shape of the address, function)
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
# For images (photos, avatars): even if by some absurdity they contained code, they could not run it.
CSP_FILE = "default-src 'none'; sandbox"

# ------------------------------------------------------------------------------------------
# 6c-bis. Who can talk to the program: the "session key"
# ------------------------------------------------------------------------------------------
# The server listens only on 127.0.0.1, but other programs could be running on your PC, or a
# web page open in your browser could try to "knock" on localhost. For this reason, every time
# NeoTracker starts it invents a random key, long and impossible to guess. The app window
# receives it only once, when it opens (address ...?avvio=KEY), and keeps it in a reserved
# "cookie" (HttpOnly: not even the JavaScript of the page can read it; SameSite=Strict:
# external sites cannot use it). Without the key every request is refused.
# The key changes at every start and is written (with restricted permissions) in the data folder,
# only so that a second clicked icon can open a window on the program that is already running.
NOME_COOKIE = "nt_sessione"
TOKEN_SESSIONE = secrets.token_urlsafe(32)
PERCORSI_LIBERI = ("/api/ping",)           # the only address without a key: it serves to tell whether NeoTracker is already running
MAX_PRESENZE = 16                          # simultaneous "open window" connections (one person uses 1 or 2)
_presenze_aperte = [0]
_blocco_presenze = threading.Lock()


def percorso_token():
    return Path(CARTELLA_DATI) / "sessione.token"


def scrivi_token_su_file():
    """Saves the key in a file readable only by you (on Windows it inherits the permissions of your user folder)."""
    f = percorso_token()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(TOKEN_SESSIONE, encoding="ascii")
    if os.name != "nt":
        os.chmod(tmp, 0o600)
    os.replace(tmp, f)


def leggi_token_da_file():
    """Key of the NeoTracker that is already running (a second clicked icon reads it). Empty string if there is none."""
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
    """Constant-time comparison (it does not reveal, from the response times, how many letters were right)."""
    return hmac.compare_digest(str(a).encode("utf-8", "replace"), str(b).encode("utf-8", "replace"))


_ACCESSO_NEGATO_TESTI = (
    ("en", "Access denied", "This page only works from the NeoTracker window. Close this tab and open the app "
                            "from the <b>NeoTracker</b> icon on your Desktop."),
    ("it", "Accesso non autorizzato", "Questa pagina funziona solo dalla finestra di NeoTracker. Chiudi questa scheda e apri l'app "
                                      "dall'icona <b>NeoTracker</b> sul Desktop."),
    ("fr", "Accès non autorisé", "Cette page ne fonctionne que depuis la fenêtre de NeoTracker. Fermez cet onglet et ouvrez "
                                 "l'application avec l'icône <b>NeoTracker</b> du Bureau."),
    ("de", "Zugriff nicht erlaubt", "Diese Seite funktioniert nur im NeoTracker-Fenster. Schließen Sie diesen Tab und starten Sie "
                                    "die App über das <b>NeoTracker</b>-Symbol auf dem Desktop."),
    ("es", "Acceso no autorizado", "Esta página solo funciona desde la ventana de NeoTracker. Cierra esta pestaña y abre la "
                                   "aplicación desde el icono <b>NeoTracker</b> del Escritorio."),
)
PAGINA_ACCESSO_NEGATO = (
    "<!doctype html><html lang='en'><meta charset='utf-8'><title>" + " · ".join(t for _, t, _ in _ACCESSO_NEGATO_TESTI) + "</title>"
    "<body style='font-family:Segoe UI,Arial,sans-serif;max-width:34em;margin:4em auto;padding:0 1em;color:#222'>"
    + "".join(f"<section lang='{lg}'><h1>{tit}</h1><p>{txt}</p></section>" for lg, tit, txt in _ACCESSO_NEGATO_TESTI)
    + "</body></html>").encode("utf-8")

# Security headers added to EVERY response.
INTESTAZIONI_SICUREZZA = {
    "X-Content-Type-Options": "nosniff",                  # the browser must not "guess" the file type
    "Cache-Control": "no-store",                          # no copies of personal data in the browser cache
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",                            # the page cannot be embedded in other pages
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), payment=(), usb=(), geolocation=(self)",
}


class Gestore(BaseHTTPRequestHandler):
    server_version = "NeoTracker"
    sys_version = ""                  # do not say which Python version is underneath
    timeout = 60                      # a connection that stays silent for a minute is closed (defence against "hanging" connections)

    def log_message(self, formato, *args):            # no noise in the black window
        pass

    # ---- common security checks ----
    def _host_ok(self):
        ammessi = {f"127.0.0.1:{PORTA}", f"localhost:{PORTA}"}
        return self.headers.get("Host", "") in ammessi

    def _origine_ok(self):
        o = self.headers.get("Origin")
        return o is None or o in (f"http://127.0.0.1:{PORTA}", f"http://localhost:{PORTA}")

    def _cookie_ok(self):
        """True if the request carries the right session key in the cookie."""
        for riga in self.headers.get_all("Cookie") or []:
            for parte in riga.split(";"):
                nome, _, valore = parte.strip().partition("=")
                if nome == NOME_COOKIE and chiave_uguale(valore, TOKEN_SESSIONE):
                    return True
        return False

    def _invia(self, codice, dati, mime, extra=None):
        intestazioni = dict(INTESTAZIONI_SICUREZZA)
        intestazioni.update(extra or {})                 # whoever answers can change a value (e.g. photo cache)
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

    # ---- presence of the window: a connection that stays open as long as the page is open ----
    def _presenza(self, query):
        """The page opens this connection as soon as it loads and keeps it open. While it is open the
        window exists; as soon as the page closes (even if the browser is "killed" or freezes)
        Windows closes the connection and the program notices at once. It is the most
        reliable "window closed" signal; the page's heartbeats and the "goodbye" remain as reinforcement."""
        id_pagina = (query.get("id") or [""])[0]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", id_pagina):
            return self._errore(400, T("Invalid page identifier."))
        with _blocco_presenze:                                      # a cap on open connections: no "floods"
            if _presenze_aperte[0] >= MAX_PRESENZE:
                return self._errore(429, T("Too many open connections."))
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
        fine = getattr(self.server, "fine_sorveglianza", None)       # turns on when the program is closing
        try:
            self.wfile.write(b"retry: 1000\n\n")                    # if the connection drops, the page retries after 1 second
            self.wfile.flush()
            giri = 0
            while fine is None or not fine.is_set():
                STATO_FINESTRA.battito(id_pagina)                    # "this page is still here"
                # Wait up to 1 second. If the connection becomes "readable" it means that the other side (the
                # browser) has closed it: the page is gone. A live page never writes anything.
                chiusa, _, _ = select.select([self.connection], [], [], 1.0)
                if chiusa:
                    break
                giri += 1
                if giri % 5 == 0:                                    # every 5 seconds an empty signal, to notice write errors
                    self.wfile.write(b": ok\n\n")
                    self.wfile.flush()
        except (OSError, ValueError):
            pass                                                     # connection dropped: it is exactly what we are looking for
        finally:
            STATO_FINESTRA.addio(id_pagina)                          # the page is gone (if it was the last one, the countdown starts)
            self.close_connection = True

    # ---- dispatching ----
    def _gestisci(self):
        try:
            if not self._host_ok():
                return self._errore(403, T("Address not allowed."))
            if not self._origine_ok():
                return self._errore(403, T("Origin not allowed."))
            if len(self.path) > 2000:
                return self._errore(414, T("Address too long."))
            url = urllib.parse.urlsplit(self.path)
            percorso, query = url.path, urllib.parse.parse_qs(url.query, keep_blank_values=True)
            if self.command in ("POST", "PUT", "PATCH", "DELETE") and self.headers.get("X-NeoTracker") != "1":
                return self._errore(403, T("Unauthorised request."))

            # ---- session key (see 6c-bis) ----
            if percorso not in PERCORSI_LIBERI:
                avvio = (query.get("avvio") or [""])[0]
                if self.command == "GET" and percorso == "/" and avvio:
                    # the window presents itself with the key: I remember it in a reserved cookie and clean up
                    # the address
                    if not chiave_uguale(avvio, TOKEN_SESSIONE):
                        return self._invia(403, PAGINA_ACCESSO_NEGATO, "text/html; charset=utf-8",
                                           {"Content-Security-Policy": CSP})
                    cookie = f"{NOME_COOKIE}={TOKEN_SESSIONE}; Path=/; HttpOnly; SameSite=Strict"
                    return self._reindirizza("/", cookie)
                if not self._cookie_ok():
                    if self.command == "GET" and not percorso.startswith(("/api/", "/foto/")):
                        return self._invia(403, PAGINA_ACCESSO_NEGATO, "text/html; charset=utf-8",
                                           {"Content-Security-Policy": CSP})
                    return self._errore(403, T("Unauthorised access."))

            if self.command == "GET" and percorso == "/api/presenza":
                return self._presenza(query)

            if self.command == "GET" and not percorso.startswith(("/api/", "/foto/")):
                voce = WEB_FILES.get("/index.html" if percorso == "/" else percorso)
                if voce is None:
                    return self._errore(404, T("Page not found."))
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
                return self._errore(405, T("Operation not allowed on this address."))
            return self._errore(404, T("Unknown address."))
        except ErroreRichiesta as e:
            self._errore(e.codice, str(e))
        except ErroreServizio as e:
            self._errore(502, str(e))
        except (BrokenPipeError, ConnectionResetError):
            pass                                       # the browser closed the connection: no problem
        except Exception as e:                         # our error: I show it in the console and report it to the browser
            traceback.print_exc()                      # the details stay in the log (neotracker.log), not in the response
            try:
                self._errore(500, T("Internal error. Details are in the neotracker.log file in the data folder."))
            except Exception:
                pass

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _gestisci

    def do_HEAD(self):
        self._errore(405, T("Not allowed."))

    def do_OPTIONS(self):
        self._errore(403, T("Not allowed."))


# ==========================================================================================
# 6d. WEB PAGES (HTML / CSS / JavaScript) embedded in this file
# ==========================================================================================
# If you want to change the look of the app you can also change the text below.

_WEB_APP_JS = r'''/* ============================================================================
   app.js - start-up, menu, page choice and current user
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h, $ = NT.$;

  const VOCI = [
    ['mappa', NT.t('Mole map'), 'mappa'], ['profilo', NT.t('Profile'), 'profilo'], ['letteratura', NT.t('Literature'), 'letteratura'],
    ['genetica', NT.t('Genetics'), 'genetica'], ['uv', NT.t('UV index'), 'uv'], ['impostazioni', NT.t('Settings'), 'impostazioni'],
  ];

  NT.colorePerNome = nome => { let x = 0; for (const c of nome) x = (x * 31 + c.charCodeAt(0)) % 360; return 'hsl(' + x + ',45%,38%)'; };
  /* Circle with the user's personal image (if they chose one) or with the initial of their name.
     "utente" is optional: it only serves to have the id and version of the image (avatar_v, 0 = none). */
  NT.avatar = (nome, dim, utente) => {
    const d = dim || 32, iniziale = (nome.trim()[0] || '?').toUpperCase();
    const cerchio = h('span', { class: 'avatar', style: { background: NT.colorePerNome(nome), width: d + 'px', height: d + 'px', fontSize: Math.round(d * 0.45) + 'px' } }, iniziale);
    if (utente && utente.avatar_v) {
      const img = h('img', { class: 'avatar-img', alt: '', draggable: 'false', src: '/api/utenti/' + utente.id + '/avatar?v=' + utente.avatar_v });
      img.addEventListener('error', () => cerchio.replaceChildren(iniziale));         // if the image is missing, it falls back to the initial
      cerchio.replaceChildren(img);
    }
    return cerchio;
  };

  NT.vai = nome => { if (location.hash === '#/' + nome) route(); else location.hash = '#/' + nome; };
  const nomeRotta = () => { const m = /^#\/(\w+)/.exec(location.hash); return m ? m[1] : 'mappa'; };

  function disegnaTestata(attiva) {
    const menu = $('#menu');
    menu.setAttribute('aria-label', NT.t('Sections'));
    $('#piede').textContent = NT.t('NeoTracker is not a medical tool and does not make diagnoses. For any mole that changes, bleeds, itches or worries you, see a dermatologist.');
    menu.replaceChildren(...VOCI.map(([id, testo, ico]) =>
      h('a', { href: '#/' + id, class: 'voce' + (id === attiva ? ' attiva' : ''), 'aria-current': id === attiva ? 'page' : null }, NT.icona(ico, 18), h('span', {}, testo))));
    const box = $('#utente-box');
    box.replaceChildren(S.utente
      ? h('a', { href: '#/utenti', class: 'utente-chip', title: NT.t('Switch user') }, NT.avatar(S.utente.nome, 28, S.utente),
        h('span', { class: 'utente-nome' }, S.utente.nome), h('span', { class: 'utente-cambia' }, NT.t('Change')))
      : h('a', { href: '#/utenti', class: 'utente-chip' }, h('span', { class: 'utente-nome' }, NT.t('Choose user'))));
  }

  async function route() {
    NT.pulizie.splice(0).forEach(f => { try { f(); } catch (e) { /* ignore */ } });
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
      cont.replaceChildren(h('div', { class: 'scheda errore-pagina' }, h('h2', {}, NT.t('Something went wrong')), h('p', {}, e.message || String(e)),
        h('button', { class: 'btn', onclick: () => route() }, NT.t('Try again'))));
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

  /* ---- "heartbeat": every few seconds the page tells the program "I am still open" ----
     When the window is closed the heartbeats stop (and a last "goodbye" message is sent):
     the program understands that it can shut down. Each page has a random number, so several windows
     open at the same time do not get mixed up. */
  const nuovoId = () => (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
    : String(Date.now()) + Math.random().toString(36).slice(2);
  let ID_PAGINA = nuovoId();
  NT.battitoAttivo = true;                       // becomes false after "Close NeoTracker" (it must not beat any more)
  function segnale(percorso) {
    if (!NT.battitoAttivo && percorso === '/api/battito') return;
    try {
      // keepalive: the request goes out even while the page is closing
      fetch(percorso, { method: 'POST', keepalive: true,
        headers: { 'Content-Type': 'application/json', 'X-NeoTracker': '1' },
        body: JSON.stringify({ id: ID_PAGINA }) }).catch(() => { /* program already shut down: fine */ });
    } catch (e) { /* ignore */ }
  }
  // Presence connection: it stays open as long as the page is open. When the window closes (in any way) the
  // program notices at once. It reconnects by itself if it drops.
  function apriPresenza() {
    if (NT.presenza) { try { NT.presenza.close(); } catch (e) { /* ignore */ } }
    try { NT.presenza = new EventSource('/api/presenza?id=' + encodeURIComponent(ID_PAGINA)); } catch (e) { NT.presenza = null; }
  }
  apriPresenza();
  segnale('/api/battito');
  setInterval(() => segnale('/api/battito'), 5000);
  window.addEventListener('pageshow', ev => {
    // If the browser "wakes" us from a copy set aside (ev.persisted), the program had already received the
    // goodbye: we present ourselves as a new page, with a new number.
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
      $('#vista').replaceChildren(h('div', { class: 'scheda errore-pagina' }, h('h2', {}, NT.t('NeoTracker is not responding')), h('p', {}, e.message)));
      return;
    }
    window.addEventListener('hashchange', route);
    if (!location.hash || location.hash === '#') location.hash = S.utente ? '#/mappa' : '#/utenti';
    else route();
    if (S.imp.avvertenze_accettate !== S.stato.avvertenze_versione) NT.mostraAvvertenze();     // first start (or updated notice)
  }
  avvia();
})();
'''
WEB_FILES["/app.js"] = ("text/javascript; charset=utf-8", _WEB_APP_JS.encode("utf-8"))

_WEB_BODY_JS = r'''/* ============================================================================
   body.js - interactive map of the human body (front + back) drawn in SVG
   The coordinates of each mole are saved "normalised": x and y from 0 to 1 inside the
   figure (front or back). This way they stay valid whatever the zoom or the window.
   ============================================================================ */
(function () {
  'use strict';
  const LARG = 400, ALT = 900;            // size of ONE figure
  const VB_W = 800, VB_H = 930;           // full area: front (0-400) + back (400-800)
  const CX = 200;
  const NS = 'http://www.w3.org/2000/svg';

  const f = n => Math.round(n * 100) / 100;

  /* ---------- geometry: soft curves and "tubes" for the limbs ---------- */
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

  const PER = 8;                           // points computed between two guide points
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

  /* left and right edges of a tube (guide points [x, y, radius]) */
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
  /* stretch of tube between two guide points (indices), slightly widened: used for the regions */
  function trattoPoly(punti, i0, i1, extra) {
    const b = bordi(punti, extra || 0);
    const a = i0 * PER, z = i1 * PER;
    return b.L.slice(a, z + 1).concat(b.R.slice(a, z + 1).reverse());
  }
  const specchia = punti => punti.map(p => [LARG - p[0]].concat(p.slice(1)));
  const rect = (x0, y0, x1, y1) => [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
  const specchiaPoly = poly => poly.map(p => [LARG - p[0], p[1]]);

  /* ---------- anatomy (left side of the screen; the right one is the mirror) ---------- */
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
    // ears
    forme.push(ellisse(164, 86, 5.5, 11), ellisse(236, 86, 5.5, 11));
    // shoulders (deltoids), rounded tips of the hands and feet
    for (const [x, y, r] of [BRACCIO[0], BRACCIO[9], piede[2]]) forme.push(cerchio(x, y, r), cerchio(LARG - x, y, r));
    return forme;
  }
  function ellisse(cx, cy, rx, ry) {
    return 'M' + f(cx - rx) + ' ' + f(cy) + 'a' + rx + ' ' + ry + ' 0 1 0 ' + (2 * rx) + ' 0a' + rx + ' ' + ry + ' 0 1 0 ' + (-2 * rx) + ' 0Z';
  }
  const cerchio = (cx, cy, r) => ellisse(cx, cy, r, r);

  /* ---------- clickable regions ---------- */
  // The name of a region is the English text 'Shoulder, right' / 'Shoulder, left' (it is also the key of its translations).
  function regioni(vista) {
    const R = [];
    const lato = (schermoSx) => (vista === 'fronte') === schermoSx ? 'right' : 'left';
    // adds a region on the left side of the screen and its mirror image on the right side
    function coppia(nome, poly) {
      R.push({ nome: nome + ', ' + lato(true), poly: poly });
      R.push({ nome: nome + ', ' + lato(false), poly: specchiaPoly(poly) });
    }
    const singola = (nome, poly) => R.push({ nome: nome, poly: poly });
    const fr = vista === 'fronte';

    // head and neck (order: from the largest to the smallest, so the small ones are on top)
    if (fr) {
      singola('Forehead and scalp', rect(150, 24, 250, 58));
      singola('Face', rect(150, 58, 250, 136));
    } else {
      singola('Scalp (head)', rect(150, 24, 250, 122));
    }
    if (fr) singola('Neck', rect(168, 128, 232, 170));
    else singola('Nape and neck', rect(168, 116, 232, 170));
    // trunk
    if (fr) {
      coppia('Chest', rect(134, 160, 200, 302));
      coppia('Upper abdomen', rect(138, 302, 200, 378));
      coppia('Lower abdomen', rect(134, 378, 200, 444));
      coppia('Groin', rect(130, 444, 200, 512));
    } else {
      coppia('Shoulder blade area', rect(134, 160, 200, 264));
      coppia('Back (middle area)', rect(138, 264, 200, 346));
      coppia('Lower back', rect(134, 346, 200, 442));
      coppia('Buttock', rect(130, 442, 200, 524));
    }
    // limbs: stretches of the same tube as the drawing, a little wider, then clipped to the silhouette
    const e = 7;
    coppia('Shoulder', trattoPoly(BRACCIO, 0, 1, e));
    coppia('Arm', trattoPoly(BRACCIO, 1, 3, e));
    coppia('Elbow', trattoPoly(BRACCIO, 3, 4, e));
    coppia('Forearm', trattoPoly(BRACCIO, 4, 6, e));
    coppia('Hand', trattoPoly(BRACCIO, 6, 9, e + 3));
    coppia('Thigh', trattoPoly(GAMBA, 0, 3, e));
    if (fr) {
      coppia('Knee', trattoPoly(GAMBA, 3, 5, e));
      coppia('Lower leg (shin)', trattoPoly(GAMBA, 5, 8, e));
    } else {
      coppia('Back of knee', trattoPoly(GAMBA, 3, 5, e));
      coppia('Calf', trattoPoly(GAMBA, 5, 8, e));
    }
    coppia('Ankle', trattoPoly(GAMBA, 8, 9, e));
    coppia('Foot', rect(128, 822, 200, 880));
    // ears (above the head)
    coppia('Ear', rect(150, 70, 168, 104));
    return R;
  }

  /* ---------- colours ---------- */
  const PELLE = { 0: '#ead9c8', 1: '#f6e0d2', 2: '#efcab0', 3: '#e0b390', 4: '#c58f68', 5: '#9b6a48', 6: '#6a4630' };
  const colorePelle = ft => PELLE[ft] || PELLE[0];

  /* ---------- anatomical details (light lines) ---------- */
  function dettagli(vista) {
    const L = [];
    const l = (d, extra) => L.push('<path d="' + d + '" fill="none" ' + (extra || '') + '/>');
    const sp = (d) => d; // placeholder
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

  /* ---------- building the SVG of a figure ---------- */
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
      'aria-label="' + esc(window.NT.t('Map of the human body: front on the left, back on the right')) + '">';
    s += figura('fronte', ft, 0) + figura('retro', ft, LARG);
    // fixed labels
    const D = esc(window.NT.t('R')), Sx = esc(window.NT.t('L'));          // patient's right / left
    s += '<g class="etichette">' +
      '<text x="200" y="14" text-anchor="middle">' + esc(window.NT.t('FRONT')) + '</text><text x="600" y="14" text-anchor="middle">' + esc(window.NT.t('BACK')) + '</text>' +
      '<text x="22" y="64" class="lato">' + D + '</text><text x="378" y="64" text-anchor="end" class="lato">' + Sx + '</text>' +
      '<text x="422" y="64" class="lato">' + Sx + '</text><text x="778" y="64" text-anchor="end" class="lato">' + D + '</text></g>';
    s += '<g class="marcatori"></g></svg>';
    return s;
  }

  /* ============================================================================
     MappaCorpo class: zoom, dragging, adding and moving moles
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

    /* ---- view (zoom and panning) ---- */
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
      const rx = (cx - this.vb.x) / this.vb.w, ry = (cy - this.vb.y) / this.vb.h;   // fixed point under the cursor
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

    /* ---- conversions between screen and figure coordinates ---- */
    posizione(vista, x, y) {         // from normalised (0-1) to SVG coordinates
      return { x: (vista === 'retro' ? LARG : 0) + x * LARG, y: 20 + y * ALT };
    }
    daSchermo(ev) {                  // from pixels to normalised { vista, x, y }
      const pt = this.svg.createSVGPoint();
      pt.x = ev.clientX; pt.y = ev.clientY;
      const p = pt.matrixTransform(this.svg.getScreenCTM().inverse());
      const vista = p.x >= LARG ? 'retro' : 'fronte';
      const x = (p.x - (vista === 'retro' ? LARG : 0)) / LARG, y = (p.y - 20) / ALT;
      return { vista, x, y, px: p.x, py: p.y };
    }
    regioneA(ev) {                   // name of the region under the pointer (or '')
      const els = document.elementsFromPoint(ev.clientX, ev.clientY);
      for (const el of els) if (el.dataset && el.dataset.regione) return el.dataset.regione;
      return '';
    }
    dentroCorpo(ev) {
      return document.elementsFromPoint(ev.clientX, ev.clientY).some(el => el.dataset && el.dataset.regione);
    }
    scala() { const m = this.svg.getScreenCTM(); return m ? 1 / m.a : 1; }

    /* ---- markers ---- */
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

    /* ---- interaction ---- */
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
            if (d.tipo === 'sfondo' && !this.aggiunta) {                       // dragging the view
              const k = this.scala();
              this.vb.x = d.vb0.x - dx * k; this.vb.y = d.vb0.y - dy * k;
              this.limita(); this.applicaVB();
              svg.classList.add('trascina');
            } else if (d.tipo === 'marc' || d.tipo === 'bozza') {              // moving a mole
              if (d.tipo === 'marc' && d.nid !== this.selId) return;           // only the selected mole moves
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
        // label of the region and "ghost" pointer
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
        try { svg.releasePointerCapture(ev.pointerId); } catch (e) { /* already released */ }
        if (ev.type === 'pointercancel') { this.disegnaMarcatori(); return; }
        if (d.mosso && d.pos) {                                                // end of the move
          const reg = this.regioneA(ev);
          if (d.tipo === 'bozza') this.cb.onBozzaMossa && this.cb.onBozzaMossa(Object.assign({ regione: reg }, d.pos));
          else this.cb.onSposta && this.cb.onSposta(d.nid, Object.assign({ regione: reg }, d.pos));
          return;
        }
        if (d.mosso) return;                                                   // it was a drag of the view
        // simple click
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
   i18n.js - interface languages (English, Italian, French, German, Spanish)

   How it works, in short:
   - The ENGLISH text is the source and also the key: the code writes NT.t('Save mole').
   - The dictionaries i18n_it.js, i18n_fr.js, i18n_de.js and i18n_es.js map every English text to its
     translation. English itself needs no dictionary.
   - Texts with variable values use named placeholders: NT.t('{n} days ago', { n: 3 }).
   - Texts that come from the Python program (error messages, genetics criteria, UV index...) are English
     too: NT.tr() translates them by looking them up in the dictionary (also by "shape", i.e. with the
     variable values in place of the placeholders).
   - Data saved by earlier versions contains the Italian text of that time: NT.tr() recognises it by
     looking it up among the Italian translations, so old records are shown in the current language.
   - The language is chosen in Settings ("auto" = same as the browser). The server writes it into the
     page (<meta name="nt-lingua">) so that it is known before anything is drawn.
   To add a language see CONTRIBUTING.md.
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT = window.NT || {};

  NT.LINGUE = [['en', 'English'], ['it', 'Italiano'], ['fr', 'Français'], ['de', 'Deutsch'], ['es', 'Español']];
  const CODICI = NT.LINGUE.map(l => l[0]);

  /* ---------- which language to use ---------- */
  NT.linguaDelBrowser = function () {
    const elenco = (navigator.languages && navigator.languages.length) ? navigator.languages : [navigator.language || ''];
    for (const l of elenco) {
      const c = String(l).slice(0, 2).toLowerCase();
      if (CODICI.includes(c)) return c;
    }
    return 'en';                                  // unsupported language: English is the most widespread
  };
  const meta = document.querySelector('meta[name="nt-lingua"]');
  NT.linguaScelta = meta && CODICI.includes(meta.content) ? meta.content : 'auto';    // 'auto' or a language code
  NT.lingua = NT.linguaScelta === 'auto' ? NT.linguaDelBrowser() : NT.linguaScelta;
  document.documentElement.lang = NT.lingua;

  const DIZIONARI = window.NT_DIZIONARI || {};
  const DIZ = NT.lingua === 'en' ? {} : (DIZIONARI[NT.lingua] || {});   // empty for English (the source)
  const IT = DIZIONARI.it || {};              // every English text is a key here: it is the list of all texts

  /* ---------- translation of the program's texts ---------- */
  const sostituisci = (s, params) => params ? s.replace(/\{(\w+)\}/g, (m, k) => (k in params ? String(params[k]) : m)) : s;

  NT.mancanti = new Set();       // texts without a translation found during use (the tests check this set)
  NT.t = function (testo, params) {
    let s = testo;
    if (NT.lingua !== 'en') {
      const tr = DIZ[testo];
      if (tr === undefined) {
        if (!NT.mancanti.has(testo)) { NT.mancanti.add(testo); console.warn('[i18n] missing translation (' + NT.lingua + '): ' + testo); }
      } else s = tr;
    }
    return sostituisci(s, params);
  };

  /* Marks an English text that will be translated later (with NT.tr): it does nothing, but build.py uses it
     to check that the text has a translation in every dictionary. */
  NT.m = testo => testo;

  /* Singular/plural: 'uno' and 'altri' are the two English texts (with {n}). French uses the singular for 0 too.
     If the two English forms are equal, the translation of the plural has the key "<text>#pl". */
  NT.tp = function (n, uno, altri, params) {
    const sing = NT.lingua === 'fr' ? Math.abs(n) < 2 : n === 1;
    const p = Object.assign({ n: n }, params);
    if (NT.lingua === 'en') return sostituisci(sing ? uno : altri, p);
    return NT.t(sing ? uno : (altri === uno ? uno + '#pl' : altri), p);
  };

  /* Translates a text that comes from the Python program (already composed, in English) or that was saved
     by an earlier version (in Italian). It does not complain when it finds nothing: it may be a name typed
     by the user or the text of a technical error. */
  let schemi = null, vecchi = null, schemiVecchi = null;
  const resa = (chiave, params) => sostituisci(NT.lingua === 'en' ? chiave : (DIZ[chiave] !== undefined ? DIZ[chiave] : chiave), params);
  function schema(forma, chiave) {
    const pezzi = forma.split(/\{(\w+)\}/);               // [text, name, text, name, ..., text]
    const nomi = [];
    let re = '^';
    pezzi.forEach((p, i) => {
      if (i % 2) { nomi.push(p); re += '([\\s\\S]+?)'; }
      else re += p.replace(/[.*+?^$()|[\]\\{}]/g, '\\$&');
    });
    return { chiave: chiave, nomi: nomi, re: new RegExp(re + '$'), fisso: pezzi.filter((p, i) => i % 2 === 0).join('').length };
  }
  function costruisciSchemi() {
    schemi = []; schemiVecchi = []; vecchi = {};
    for (const chiave in IT) {
      if (/\{\w+\}/.test(chiave)) schemi.push(schema(chiave, chiave));
      const it = IT[chiave];
      if (/\{\w+\}/.test(it)) schemiVecchi.push(schema(it, chiave));
      else if (!(it in vecchi)) vecchi[it] = chiave;
    }
    const piuSpecifico = (a, b) => b.fisso - a.fisso;       // the most specific shapes first
    schemi.sort(piuSpecifico); schemiVecchi.sort(piuSpecifico);
  }
  function cercaSchema(lista, testo) {
    for (const s of lista) {
      const m = s.re.exec(testo);
      if (!m) continue;
      const params = {};
      s.nomi.forEach((nome, i) => { params[nome] = NT.tr(m[i + 1]); });
      return resa(s.chiave, params);
    }
    return null;
  }
  NT.tr = function (testo) {
    if (testo === null || testo === undefined || testo === '') return testo;
    testo = String(testo);
    if (!schemi) costruisciSchemi();
    if (Object.prototype.hasOwnProperty.call(IT, testo)) return resa(testo);              // an English text of the program
    let r = cercaSchema(schemi, testo);                                                    // ... with variable values
    if (r !== null) return r;
    if (Object.prototype.hasOwnProperty.call(vecchi, testo)) return resa(vecchi[testo]);  // Italian text saved by an old version
    r = cercaSchema(schemiVecchi, testo);
    if (r !== null) return r;
    if (testo.indexOf('; ') > 0) {                                                         // several messages joined by "; "
      const parti = testo.split('; '), tradotte = parti.map(NT.tr);
      if (tradotte.some((x, i) => x !== parti[i])) return tradotte.join('; ');
    }
    return testo;
  };

  /* ---------- numbers and dates in the format of the language ---------- */
  const SEP = NT.lingua === 'en' ? '.' : ',';
  const MESI_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const LOCALI = { it: 'it-IT', en: 'en-GB', fr: 'fr-FR', de: 'de-DE', es: 'es-ES' };
  NT.locale = LOCALI[NT.lingua];
  NT.num = (n, dec) => (n === null || n === undefined) ? '' : Number(n).toFixed(dec === undefined ? 1 : dec).replace('.', SEP);
  NT.perc = v => v === null || v === undefined ? '' : (v * 100).toFixed(v >= 0.995 || v < 0.01 ? 1 : 0).replace('.', SEP) + '%';
  NT.migliaia = n => Number(n).toLocaleString(NT.locale);
  /* 'YYYY-MM-DD' -> 08/11/2026 (it, fr, es), 08.11.2026 (de), 8 Nov 2026 (en) */
  NT.fmtData = iso => {
    if (!iso) return '';
    const [a, m, g] = iso.slice(0, 10).split('-');
    if (NT.lingua === 'en') return String(+g) + ' ' + MESI_EN[+m - 1] + ' ' + a;
    return g + (NT.lingua === 'de' ? '.' + m + '.' : '/' + m + '/') + a;
  };
  NT.fmtDataOra = iso => iso ? NT.fmtData(iso) + ' ' + String(iso).slice(11, 16) : '';
  /* day and month without the year: 08/11, 08.11., 8 Nov */
  NT.fmtGiornoMese = iso => {
    if (!iso) return '';
    const [, m, g] = iso.slice(0, 10).split('-');
    if (NT.lingua === 'en') return String(+g) + ' ' + MESI_EN[+m - 1];
    return g + (NT.lingua === 'de' ? '.' + m + '.' : '/' + m);
  };
  NT.fraseGiorni = g => g === null || g === undefined ? '' : g <= 0 ? NT.t('today') : g === 1 ? NT.t('yesterday')
    : g < 60 ? NT.t('{n} days ago', { n: g })
      : g < 700 ? NT.t('{n} months ago', { n: Math.round(g / 30.4) })
        : NT.tp(Math.round(g / 365), '{n} year ago', '{n} years ago');
})();
'''
WEB_FILES["/i18n.js"] = ("text/javascript; charset=utf-8", _WEB_I18N_JS.encode("utf-8"))

_WEB_I18N_DE_JS = r'''/* NeoTracker interface translations: de. Key = the English source text.
   Keep the {name} placeholders unchanged. Check: python3 tools/traduzioni.py */
(window.NT_DIZIONARI = window.NT_DIZIONARI || {}).de = {
  "(CC BY 4.0 licence). The free service is for personal, non-commercial use.": "(Lizenz CC BY 4.0). Der kostenlose Dienst ist für den persönlichen, nicht kommerziellen Gebrauch bestimmt.",
  "(empty)": "(leer)",
  "(local time at the location)": "(Ortszeit des Standorts)",
  "(saved search from {data})": "(gespeicherte Suche vom {data})",
  "(untitled)": "(ohne Titel)",
  "({variazione} mm since the previous photo)": "({variazione} mm seit dem vorherigen Foto)",
  "1 photo from {data}, diameter {mm} mm.": "1 Foto vom {data}, Durchmesser {mm} mm.",
  "1 photo from {data}.": "1 Foto vom {data}.",
  "100 or more": "100 oder mehr",
  "100 or more moles on the body": "100 oder mehr Muttermale am Körper",
  "1st-degree relatives with melanoma": "Verwandte 1. Grades mit Melanom",
  "3 = WHO recommends protection from this level": "3 = ab hier empfiehlt die WHO Schutz",
  "3 or more primary melanomas in the same person": "3 oder mehr primäre Melanome bei derselben Person",
  "50 to 99 moles on the body": "50 bis 99 Muttermale am Körper",
  "A few": "Wenige",
  "A mole that changes (shape, borders, colour, size), bleeds, itches or worries you must be shown to a dermatologist, whatever the app says. Regular check-ups with the dermatologist remain irreplaceable.": "Ein Muttermal, das sich verändert (Form, Rand, Farbe, Größe), blutet, juckt oder Ihnen Sorgen macht, gehört zur Hautärztin oder zum Hautarzt – ganz gleich, was die App sagt. Die regelmäßige Kontrolle beim Hautarzt bleibt unersetzlich.",
  "A positive result indicates a higher risk, not certainty of becoming ill; a negative result does not remove the risk (many families have no identifiable variant).": "Ein positives Ergebnis weist auf ein höheres Risiko hin, nicht auf die Gewissheit zu erkranken; ein negatives Ergebnis hebt das Risiko nicht auf (viele Familien haben keine nachweisbare Variante).",
  "A user with this name already exists.": "Ein Benutzer mit diesem Namen existiert bereits.",
  "ABCDE criteria and the 'ugly duckling' sign": "ABCDE-Kriterien und das Zeichen des „hässlichen Entleins“",
  "ABCDE reminder": "ABCDE-Merkhilfe",
  "ABCDE reminder for recognising a mole": "ABCDE-Merkhilfe zum Erkennen eines Muttermals",
  "About 5–10% of melanomas occur in families with an inherited predisposition (Leachman 2009). Here you find the criteria specialists use to decide whether to suggest genetic counselling, the genes involved and the literature on each.": "Etwa 5–10 % der Melanome treten in Familien mit erblicher Veranlagung auf (Leachman 2009). Hier finden Sie die Kriterien, nach denen Fachleute entscheiden, ob eine genetische Beratung angeboten wird, die beteiligten Gene und die Literatur zu jedem von ihnen.",
  "Accept and continue": "Akzeptieren und fortfahren",
  "According to the NCCN guidelines, in an invasive melanoma with a first-degree relative with pancreatic cancer, a multigene panel that includes CDKN2A is recommended.": "Nach den NCCN-Leitlinien wird bei einem invasiven Melanom mit einem Verwandten ersten Grades mit Bauchspeicheldrüsenkrebs ein Multigen-Panel empfohlen, das CDKN2A einschließt.",
  "Acral melanoma (hands, feet, nails): dermoscopy": "Akrales Melanom (Hände, Füße, Nägel): Dermatoskopie",
  "Add a photo to the history": "Foto zum Verlauf hinzufügen",
  "Add mole": "Muttermal hinzufügen",
  "Add the first photo below: it will be the starting point to see whether the mole changes over time.": "Fügen Sie unten das erste Foto hinzu: Es ist der Ausgangspunkt, um zu sehen, ob sich das Muttermal mit der Zeit verändert.",
  "Add the first photo: it becomes your baseline photo, and every later photo will follow how the mole evolves.": "Fügen Sie das erste Foto hinzu: Es wird Ihr Ausgangsfoto, und jedes weitere Foto zeigt, wie sich das Muttermal entwickelt.",
  "Address not allowed.": "Adresse nicht zulässig.",
  "Address too long.": "Adresse zu lang.",
  "After": "Nachher",
  "Age": "Alter",
  "Age, sex and phenotype do not change the output of the neural networks: they are used to show you the risk factors, choose the literature, evaluate the genetics criteria and estimate the time to sunburn.": "Alter, Geschlecht und Phänotyp verändern das Ergebnis der neuronalen Netze nicht: Sie dienen dazu, Ihnen die Risikofaktoren zu zeigen, die Literatur auszuwählen, die genetischen Kriterien zu bewerten und die Zeit bis zum Sonnenbrand abzuschätzen.",
  "All data stays on this computer, in the folder:": "Alle Daten bleiben auf diesem Computer, im Ordner:",
  "All its {n} photos and the analysis reports will be deleted permanently.": "Alle seine {n} Fotos und die Analyseberichte werden endgültig gelöscht.",
  "Also use SkinSense (online service)": "SkinSense (Online-Dienst) ebenfalls verwenden",
  "Always shoot from the same angle and keep the original, without filters.": "Fotografieren Sie immer aus demselben Winkel und bewahren Sie das Original ohne Filter auf.",
  "An estimate is fine.": "Eine Schätzung genügt.",
  "Analyse now with all installed methods": "Jetzt mit allen installierten Methoden analysieren",
  "Analyse this photo": "Dieses Foto analysieren",
  "Analysis in progress…": "Analyse läuft…",
  "Analysis interrupted (app closed).": "Analyse abgebrochen (App geschlossen).",
  "Analysis program (melanoma_batch.py) not found: photos are saved but cannot be analysed.": "Analyseprogramm (melanoma_batch.py) nicht gefunden: Die Fotos werden gespeichert, können aber nicht analysiert werden.",
  "Analysis program:": "Analyseprogramm:",
  "Analysis stopped after {ore} hours (too long).": "Analyse nach {ore} Stunden abgebrochen (zu lang).",
  "Analysis: needs attention": "Analyse: auffällig",
  "Ankle, left": "Knöchel links",
  "Ankle, right": "Knöchel rechts",
  "Anything else you want to remember (allergies, photosensitising medicines, …)": "Sonstiges, woran Sie sich erinnern möchten (Allergien, lichtsensibilisierende Medikamente, …)",
  "App 1 (DeborahAdedigba) - TensorFlow models": "App 1 (DeborahAdedigba) - TensorFlow-Modelle",
  "Appearance": "Erscheinungsbild",
  "Archive (removes it from the map, keeps the data)": "Archivieren (entfernt es von der Karte, die Daten bleiben erhalten)",
  "Archived moles ({n})": "Archivierte Muttermale ({n})",
  "Arm, left": "Arm links",
  "Arm, right": "Arm rechts",
  "Asking the browser for your position… (a permission request may appear)": "Der Browser wird nach Ihrem Standort gefragt… (möglicherweise erscheint eine Berechtigungsanfrage)",
  "Associated risk": "Assoziiertes Risiko",
  "Associated with variants of the MC1R gene.": "Verbunden mit Varianten des MC1R-Gens.",
  "Astrocytoma": "Astrozytom",
  "Asymmetry": "Asymmetrie",
  "At least 3 diagnoses among melanoma, pancreatic cancer and astrocytoma in the same family line (yours included)": "Mindestens 3 Diagnosen aus Melanom, Bauchspeicheldrüsenkrebs und Astrozytom in derselben Familienlinie (Ihre eigene eingeschlossen)",
  "At least one method (or one of its models) flags a lesion that needs attention. This is not a diagnosis and these tools are often wrong, but it is one more reason not to put off the dermatology visit and to bring this report.": "Mindestens eine Methode (oder eines ihrer Modelle) meldet eine auffällige Läsion. Das ist keine Diagnose, und diese Werkzeuge irren sich oft; es ist aber ein weiterer Grund, den Hautarzttermin nicht aufzuschieben und diesen Bericht mitzubringen.",
  "Atypical (dysplastic) moles": "Atypische (dysplastische) Muttermale",
  "Atypical moles": "Atypische Muttermale",
  "Automatic (same as the system)": "Automatisch (wie das System)",
  "Automatic analysis": "Automatische Analyse",
  "Avoid direct exposure: unprotected skin can burn within a few minutes.": "Meiden Sie direkte Sonne: Ungeschützte Haut kann innerhalb weniger Minuten verbrennen.",
  "Avoid the sun in the middle hours of the day and protect your skin well.": "Meiden Sie die Sonne in den Mittagsstunden und schützen Sie Ihre Haut gut.",
  "BACK": "RÜCKSEITE",
  "BAP1 tumour predisposition syndrome: uveal melanoma, mesothelioma, renal carcinoma, cutaneous melanoma and atypical melanocytic naevi.": "BAP1-Tumor-Prädispositionssyndrom: uveales Melanom, Mesotheliom, Nierenzellkarzinom, kutanes Melanom und atypische melanozytäre Nävi.",
  "BAP1-spectrum tumours indicated: {bap1_spettro}. Simplified criterion: the geneticist uses more complete criteria.": "Angegebene Tumoren des BAP1-Spektrums: {bap1_spettro}. Vereinfachtes Kriterium: Der Humangenetiker verwendet umfassendere Kriterien.",
  "Back": "Rückseite",
  "Back (middle area), left": "Rücken (mittlerer Bereich) links",
  "Back (middle area), right": "Rücken (mittlerer Bereich) rechts",
  "Back of knee, left": "Kniekehle links",
  "Back of knee, right": "Kniekehle rechts",
  "Before": "Vorher",
  "Before you start": "Bevor Sie beginnen",
  "Black": "Schwarz",
  "Blond": "Blond",
  "Blue/grey": "Blau/grau",
  "Border": "Rand",
  "Brown": "Braun",
  "Buttock, left": "Gesäß links",
  "Buttock, right": "Gesäß rechts",
  "Calf, left": "Wade links",
  "Calf, right": "Wade rechts",
  "Can't do it? Estimate from the internet address": "Es klappt nicht? Aus der Internetadresse schätzen",
  "Cancel": "Abbrechen",
  "Centre on the map": "Auf der Karte zentrieren",
  "Change": "Wechseln",
  "Change image…": "Bild ändern…",
  "Change:": "Veränderung:",
  "Checking status…": "Status wird geprüft…",
  "Chest, left": "Brustkorb links",
  "Chest, right": "Brustkorb rechts",
  "Choose a personal picture": "Eigenes Bild auswählen",
  "Choose a user and enter their phototype to see how many minutes it takes to burn.": "Wählen Sie einen Benutzer und geben Sie seinen Hauttyp an, um zu sehen, nach wie vielen Minuten ein Sonnenbrand entsteht.",
  "Choose an image file (JPG, PNG, WEBP or BMP).": "Wählen Sie eine Bilddatei (JPG, PNG, WEBP oder BMP).",
  "Choose image…": "Bild auswählen…",
  "Choose the city above: then you will see today's UV index, hour by hour.": "Wählen Sie oben die Stadt: Dann sehen Sie den heutigen UV-Index Stunde für Stunde.",
  "Choose user": "Benutzer auswählen",
  "Choose where you are to see today's UV index.": "Wählen Sie Ihren Standort, um den heutigen UV-Index zu sehen.",
  "Choose your profile: each person has their own mole map, photos and data.": "Wählen Sie Ihr Profil: Jede Person hat ihre eigene Muttermal-Karte, eigene Fotos und eigene Daten.",
  "Cited by the NCCN guidelines among the genes to consider in melanoma panels (Cowden syndrome).": "Von den NCCN-Leitlinien unter den Genen genannt, die in Melanom-Panels zu berücksichtigen sind (Cowden-Syndrom).",
  "City name": "Name der Stadt",
  "City search also uses Open-Meteo.": "Auch die Ortssuche nutzt Open-Meteo.",
  "Classified as definite human carcinogens (IARC).": "Als sicher krebserregend für den Menschen eingestuft (IARC).",
  "Click a mole in the list or on the map to see its photo history.": "Klicken Sie ein Muttermal in der Liste oder auf der Karte an, um seinen Fotoverlauf zu sehen.",
  "Click on the exact spot on the body where the mole is (you can zoom in first)": "Klicken Sie auf die genaue Stelle am Körper, an der sich das Muttermal befindet (Sie können vorher zoomen)",
  "Click to see the original photo full screen": "Klicken, um das Originalfoto im Vollbild zu sehen",
  "Clinical trial": "Klinische Studie",
  "Close": "Schließen",
  "Close NeoTracker": "NeoTracker beenden",
  "Close NeoTracker?": "NeoTracker beenden?",
  "Close the program": "Programm beenden",
  "Closing the program": "Programm beenden",
  "Colour": "Farbe",
  "Common variants linked to red hair and fair skin: they raise the melanoma risk moderately. Not a routine test: interpretation is specialist.": "Häufige Varianten, die mit roten Haaren und heller Haut zusammenhängen: Sie erhöhen das Melanomrisiko mäßig. Kein Routinetest: Die Interpretation ist Sache von Fachleuten.",
  "Compare": "Vergleichen",
  "Compare shape, borders and colours: if you notice differences, show the photos to your dermatologist.": "Vergleichen Sie Form, Ränder und Farben: Wenn Ihnen Unterschiede auffallen, zeigen Sie die Fotos Ihrer Hautärztin oder Ihrem Hautarzt.",
  "Comparison of two photos": "Vergleich zweier Fotos",
  "Comparison slider": "Vergleichsregler",
  "Confirm": "Bestätigen",
  "Consent": "Einwilligung",
  "Count blood relatives (not in-laws) on the same side of the family, maternal or paternal: this is the criterion geneticists use. If you do not know, ask a relative: this information is very useful.": "Zählen Sie Blutsverwandte (keine angeheirateten) auf derselben Seite der Familie, mütterlicher- oder väterlicherseits: Das ist das Kriterium der Genetiker. Wenn Sie es nicht wissen, fragen Sie einen Angehörigen: Diese Informationen sind sehr nützlich.",
  "Create a free account at": "Erstellen Sie ein kostenloses Konto bei",
  "Create user": "Benutzer anlegen",
  "Dark": "Dunkel",
  "Dark skin. Rarely burns.": "Dunkle Haut. Verbrennt selten.",
  "Date of birth": "Geburtsdatum",
  "Date of birth out of range.": "Geburtsdatum außerhalb des zulässigen Bereichs.",
  "Date the photo was taken": "Aufnahmedatum",
  "Decrease: {voce}": "Verringern: {voce}",
  "Deep learning and melanoma: systematic reviews": "Deep Learning und Melanom: systematische Übersichtsarbeiten",
  "Delete": "Löschen",
  "Delete permanently": "Endgültig löschen",
  "Delete photo": "Foto löschen",
  "Delete this mole and its photos": "Dieses Muttermal und seine Fotos löschen",
  "Delete this photo?": "Dieses Foto löschen?",
  "Delete «{nome}»?": "«{nome}» löschen?",
  "Dermoscopic": "Dermatoskopisch",
  "Dermoscopy and early diagnosis (reviews)": "Dermatoskopie und Früherkennung (Übersichtsarbeiten)",
  "Detect my location": "Meinen Standort ermitteln",
  "Diameter": "Durchmesser",
  "Diameter (mm)": "Durchmesser (mm)",
  "Diameter over time": "Durchmesser im Zeitverlauf",
  "Diameter:": "Durchmesser:",
  "Diameter: from {da} to {a} mm.": "Durchmesser: von {da} auf {a} mm.",
  "Diameter: {diff} mm difference.": "Durchmesser: {diff} mm Unterschied.",
  "Don't know": "Weiß nicht",
  "Downloading the UV index…": "UV-Index wird abgerufen…",
  "Drag a photo here or click to choose one": "Ziehen Sie ein Foto hierher oder klicken Sie, um eines auszuwählen",
  "Drag the dot on the map to correct the position; zoom in with the wheel for maximum precision.": "Ziehen Sie den Punkt auf der Karte, um die Position zu korrigieren; zoomen Sie mit dem Mausrad für maximale Genauigkeit.",
  "Drag the dot on the map to move it.": "Ziehen Sie den Punkt auf der Karte, um ihn zu verschieben.",
  "Ear, left": "Ohr links",
  "Ear, right": "Ohr rechts",
  "Edit date/measurement": "Datum/Messung ändern",
  "Edit photo": "Foto bearbeiten",
  "Edit the data in the Profile": "Angaben im Profil ändern",
  "Elbow, left": "Ellbogen links",
  "Elbow, right": "Ellbogen rechts",
  "Email for PubMed": "E-Mail für PubMed",
  "Email saved.": "E-Mail gespeichert.",
  "Enlarge": "Vergrößern",
  "Error {codice}": "Fehler {codice}",
  "Especially in childhood and adolescence.": "Vor allem in Kindheit und Jugend.",
  "Estimate from the internet address": "Schätzung über die Internetadresse",
  "Estimated location": "Geschätzter Standort",
  "Evolution": "Entwicklung",
  "Extra precautions: avoid the sun in the middle of the day, seek shade, cover your skin, SPF 30+. Unprotected skin burns quickly.": "Zusätzliche Vorsichtsmaßnahmen: Meiden Sie die Sonne zur Mittagszeit, suchen Sie Schatten, bedecken Sie die Haut, LSF 30+. Ungeschützte Haut verbrennt schnell.",
  "Extreme": "Extrem",
  "Eye colour": "Augenfarbe",
  "Eyes": "Augen",
  "FRONT": "VORDERSEITE",
  "Face": "Gesicht",
  "Fair phototype (I–II)": "Heller Hauttyp (I–II)",
  "Fair skin. Burns easily, tans little.": "Helle Haut. Verbrennt leicht, bräunt wenig.",
  "Fair-olive skin. Sometimes burns, tans gradually.": "Hell-olivfarbene Haut. Verbrennt manchmal, bräunt allmählich.",
  "Fajuyigbe D, Young AR. The impact of skin colour on human photobiological responses. Pigment Cell Melanoma Res 2016;29:607-18 (minimal erythema dose by phototype)": "Fajuyigbe D, Young AR. The impact of skin colour on human photobiological responses. Pigment Cell Melanoma Res 2016;29:607-18 (minimale Erythemdosis nach Hauttyp)",
  "Family history": "Familienanamnese",
  "Fewer than 25": "Weniger als 25",
  "Fill in the 'Family history' section of your Profile: without that data I cannot check the criteria.": "Füllen Sie im Profil den Abschnitt „Familienanamnese“ aus: Ohne diese Angaben kann ich die Kriterien nicht prüfen.",
  "Fill in the family history in your Profile": "Familienanamnese im Profil ausfüllen",
  "First-degree relative with melanoma": "Verwandter ersten Grades mit Melanom",
  "Folder with your data (copy it for backup):": "Ordner mit Ihren Daten (für die Sicherung kopieren):",
  "Foot, left": "Fuß links",
  "Foot, right": "Fuß rechts",
  "Forearm, left": "Unterarm links",
  "Forearm, right": "Unterarm rechts",
  "Forehead and scalp": "Stirn und Kopfhaut",
  "Freckles": "Sommersprossen",
  "Freckles (ephelides)": "Sommersprossen (Epheliden)",
  "Front": "Vorderseite",
  "Full report (text)": "Vollständiger Bericht (Text)",
  "Full report (text, in English)": "Vollständiger Bericht (Text, auf Englisch)",
  "Gene": "Gen",
  "Gene not in the list.": "Gen nicht in der Liste.",
  "Gene {n} of {tot} ({nome})…": "Gen {n} von {tot} ({nome})…",
  "Genetic test": "Gentest",
  "Genetic test already done": "Gentest bereits durchgeführt",
  "Genetics": "Genetik",
  "Give the mole a name and check the site.": "Geben Sie dem Muttermal einen Namen und prüfen Sie die Stelle.",
  "Go to the Genetics section": "Zum Bereich Genetik",
  "Grandparents, aunts and uncles, nieces and nephews (2nd degree).": "Großeltern, Onkel und Tanten, Neffen und Nichten (2. Grad).",
  "Green": "Grün",
  "Grey/white": "Grau/weiß",
  "Groin, left": "Leiste links",
  "Groin, right": "Leiste rechts",
  "Guideline": "Leitlinie",
  "Guidelines and criteria for genetic testing": "Leitlinien und Kriterien für den Gentest",
  "Guidelines recommend the test only after careful selection of candidates and adequate counselling (Rossi 2019); the use of multigene panels is still debated.": "Die Leitlinien empfehlen den Test nur nach sorgfältiger Auswahl der Kandidaten und angemessener Beratung (Rossi 2019); der Einsatz von Multigen-Panels wird noch diskutiert.",
  "Hair": "Haare",
  "Hand, left": "Hand links",
  "Hand, right": "Hand rechts",
  "Has a doctor told you that you have atypical (dysplastic) moles?": "Hat Ihnen ein Arzt gesagt, dass Sie atypische (dysplastische) Muttermale haben?",
  "Have I already had a genetic test for melanoma?": "Habe ich bereits einen Gentest auf Melanom durchführen lassen?",
  "Having had a melanoma raises the risk of a second one.": "Wer ein Melanom hatte, hat ein höheres Risiko für ein zweites.",
  "Hereditary melanoma": "Erbliches Melanom",
  "Hereditary melanoma and genetic testing": "Erbliches Melanom und Gentest",
  "High": "Hoch",
  "High (BAP1 syndrome)": "Hoch (BAP1-Syndrom)",
  "High (rare)": "Hoch (selten)",
  "Hour-by-hour UV index for the next 24 hours": "UV-Index Stunde für Stunde für die nächsten 24 Stunden",
  "Hourly data not available": "Stundenwerte nicht verfügbar",
  "How reliable are apps and artificial intelligence": "Wie zuverlässig sind Apps und künstliche Intelligenz",
  "How to get the key": "So erhalten Sie den Schlüssel",
  "How to read the UV index": "So lesen Sie den UV-Index",
  "How to take comparable photos": "So machen Sie vergleichbare Fotos",
  "I am immunosuppressed (transplant or therapies that lower the body's defences)": "Ich bin immunsupprimiert (Transplantation oder Therapien, die die Abwehr senken)",
  "I assume the 2 outputs are [benign, malignant]; order cannot be verified": "ich nehme an, dass die 2 Ausgaben [gutartig, bösartig] sind; Reihenfolge nicht überprüfbar",
  "I cannot find melanoma_batch.py: it must be in the same folder as neotracker.py (or in {CARTELLA_REPO}).": "melanoma_batch.py wurde nicht gefunden: Die Datei muss im selben Ordner wie neotracker.py liegen (oder in {CARTELLA_REPO}).",
  "I cannot prepare the photo safely: {e}": "Das Foto kann nicht sicher aufbereitet werden: {e}",
  "I cannot reach NeoTracker. The program may have been closed: reopen it from the icon on the Desktop.": "NeoTracker ist nicht erreichbar. Möglicherweise wurde das Programm beendet: Öffnen Sie es über das Symbol auf dem Desktop erneut.",
  "I cannot read this image. Try a JPG or a PNG.": "Dieses Bild kann nicht gelesen werden. Versuchen Sie es mit einer JPG- oder PNG-Datei.",
  "I cannot reduce this image.": "Dieses Bild kann nicht verkleinert werden.",
  "I don't know: leave it empty, you can come back later.": "Ich weiß es nicht: Lassen Sie es leer, Sie können später zurückkommen.",
  "I have checked my family history (even if the answer is «none»)": "Ich habe meine Familiengeschichte überprüft (auch wenn die Antwort «keine» lautet)",
  "I have had (or have) one of these cancers:": "Ich hatte (oder habe) eine dieser Krebserkrankungen:",
  "I have had other skin cancers (basal cell or squamous cell carcinoma)": "Ich hatte andere Hautkrebsarten (Basaliom, Plattenepithelkarzinom)",
  "I have read and understood these notices": "Ich habe diese Hinweise gelesen und verstanden",
  "I prefer not to say": "Möchte ich nicht angeben",
  "I work or do activities outdoors for many hours": "Ich arbeite oder bin viele Stunden im Freien aktiv",
  "If it is still analysing a photo, it finishes the analysis first and then shuts down. The button below does the same thing.": "Wenn gerade ein Foto analysiert wird, schließt es zuerst die Analyse ab und beendet sich dann. Die Schaltfläche unten tut dasselbe.",
  "If you are unsure about your phototype, think about how your skin reacts to the first intense sun exposure in summer, without protection.": "Wenn Sie sich beim Hauttyp unsicher sind, denken Sie daran, wie Ihre Haut bei der ersten intensiven Sonnenexposition im Sommer ohne Schutz reagiert.",
  "If you enter data or photos of other people, make sure you have their consent.": "Wenn Sie Daten oder Fotos anderer Personen eingeben, stellen Sie sicher, dass Sie deren Einwilligung haben.",
  "Immunosuppression (therapies, transplant)": "Immunsuppression (Therapien, Transplantation)",
  "Important notices": "Hinweise",
  "In English": "Auf Englisch",
  "In-focus photo, with the mole in the centre and the skin clearly visible (move hair aside if needed).": "Scharfes Foto mit dem Muttermal in der Mitte und gut sichtbarer Haut (Haare bei Bedarf zur Seite schieben).",
  "Increase: {voce}": "Erhöhen: {voce}",
  "Installation status": "Installationsstatus",
  "Interface language": "Sprache der Oberfläche",
  "Internal error. Details are in the neotracker.log file in the data folder.": "Interner Fehler. Einzelheiten stehen in der Datei neotracker.log im Datenordner.",
  "Invalid UV index source.": "Ungültige Quelle für den UV-Index.",
  "Invalid coordinates.": "Ungültige Koordinaten.",
  "Invalid data (JSON).": "Ungültige Daten (JSON).",
  "Invalid data.": "Ungültige Daten.",
  "Invalid date of birth (YYYY-MM-DD).": "Ungültiges Geburtsdatum (JJJJ-MM-TT).",
  "Invalid date: use the format YYYY-MM-DD.": "Ungültiges Datum: Verwenden Sie das Format JJJJ-MM-TT.",
  "Invalid email address.": "Ungültige E-Mail-Adresse.",
  "Invalid location.": "Ungültiger Standort.",
  "Invalid notice version.": "Ungültige Version des Hinweises.",
  "Invalid page identifier.": "Ungültige Seitenkennung.",
  "Invalid profile.": "Ungültiges Profil.",
  "Irregular, jagged or blurred.": "Unregelmäßig, gezackt oder verwaschen.",
  "It changes over time: shape, colour, size, elevation, or itching or bleeding appear.": "Es verändert sich im Lauf der Zeit: Form, Farbe, Größe, Erhabenheit, oder es treten Juckreiz oder Blutungen auf.",
  "It is a personal tool for organising the photos of your moles and comparing over time the results of some research models. It is not certified or approved by any health authority.": "Es ist ein persönliches Werkzeug, um die Fotos Ihrer Muttermale zu ordnen und die Ergebnisse einiger Forschungsmodelle im Zeitverlauf zu vergleichen. Es ist von keiner Gesundheitsbehörde zertifiziert oder zugelassen.",
  "It is normal for the methods to disagree: it only means that none of them is reliable on its own.": "Dass die Methoden uneinig sind, ist normal: Es bedeutet nur, dass keine von ihnen allein zuverlässig ist.",
  "It works: OpenWeather answers (current UV index: {uvi}).": "Es funktioniert: OpenWeather antwortet (aktueller UV-Index: {uvi}).",
  "Its only photo and the analysis reports will be deleted permanently.": "Sein einziges Foto und die Analyseberichte werden endgültig gelöscht.",
  "JPG, PNG, WEBP or BMP · up to 60 MB": "JPG, PNG, WEBP oder BMP · bis 60 MB",
  "Key removed.": "Schlüssel entfernt.",
  "Key saved ({finale}) — type a new one to replace it": "Schlüssel gespeichert ({finale}) — geben Sie einen neuen ein, um ihn zu ersetzen",
  "Key saved.": "Schlüssel gespeichert.",
  "Kidney carcinoma": "Nierenzellkarzinom",
  "Knee, left": "Knie links",
  "Knee, right": "Knie rechts",
  "L": "L",
  "Language": "Sprache",
  "Language not supported.": "Sprache nicht unterstützt.",
  "Large, irregular, multicoloured moles: they should be followed over time.": "Große, unregelmäßige, mehrfarbige Muttermale: Sie sollten im Zeitverlauf beobachtet werden.",
  "Latest automatic analysis ({data}): {esito}. Research tool, not diagnostic.": "Letzte automatische Analyse ({data}): {esito}. Forschungswerkzeug, nicht diagnostisch.",
  "Leachman 2009 and 2017; NCCN": "Leachman 2009 und 2017; NCCN",
  "Leachman 2017; NCCN": "Leachman 2017; NCCN",
  "Lentigo maligna and melanoma of the face": "Lentigo maligna und Melanom im Gesicht",
  "Light-coloured eyes": "Helle Augen",
  "List of factors known from the literature, not a validated score: it does not estimate the probability of falling ill.": "Liste von Faktoren, die aus der Literatur bekannt sind, kein validierter Score: Sie schätzt nicht die Wahrscheinlichkeit zu erkranken.",
  "Literature": "Literatur",
  "Literature: PubMed": "Literatur: PubMed",
  "Loading…": "Wird geladen…",
  "Location": "Standort",
  "Location missing": "Standort fehlt",
  "Location not set": "Standort nicht festgelegt",
  "Location not set: choose a city or use 'Detect my location'.": "Standort nicht festgelegt: Wählen Sie eine Stadt oder verwenden Sie „Meinen Standort ermitteln“.",
  "Location outside the map.": "Standort außerhalb der Karte.",
  "Location saved: {nome}": "Standort gespeichert: {nome}",
  "Location set": "Standort festgelegt",
  "Location updated.": "Standort aktualisiert.",
  "Location updated: {regione}.": "Standort aktualisiert: {regione}.",
  "Low": "Niedrig",
  "Low to moderate (common)": "Niedrig bis mäßig (häufig)",
  "Lower abdomen, left": "Unterbauch links",
  "Lower abdomen, right": "Unterbauch rechts",
  "Lower back, left": "Lendenbereich links",
  "Lower back, right": "Lendenbereich rechts",
  "Lower leg (shin), left": "Unterschenkel (Schienbein) links",
  "Lower leg (shin), right": "Unterschenkel (Schienbein) rechts",
  "Lucas RM et al. Are current guidelines for sun protection optimal for health? Photochem Photobiol Sci 2018;17:1956-63 (UV Index and erythemal dose)": "Lucas RM et al. Are current guidelines for sun protection optimal for health? Photochem Photobiol Sci 2018;17:1956-63 (UV-Index und Erythemdosis)",
  "Main high-penetrance predisposition gene. Germline variants in 20–40% of families with melanoma; also associated with pancreatic cancer, multiple melanomas and early onset.": "Wichtigstes Prädispositionsgen mit hoher Penetranz. Keimbahnvarianten in 20–40 % der Familien mit Melanom; außerdem verbunden mit Bauchspeicheldrüsenkrebs, multiplen Melanomen und frühem Beginn.",
  "Man": "Mann",
  "Many": "Viele",
  "Many freckles (ephelides)": "Viele Sommersprossen (Epheliden)",
  "Many moles or atypical moles: surveillance": "Viele oder atypische Muttermale: Überwachung",
  "Many sunburns with blisters": "Viele Sonnenbrände mit Blasen",
  "Map of the human body: front on the left, back on the right": "Karte des menschlichen Körpers: Vorderseite links, Rückseite rechts",
  "Measured diameter (mm)": "Gemessener Durchmesser (mm)",
  "Melanoma already diagnosed": "Melanom bereits diagnostiziert",
  "Melanoma and immunosuppression": "Melanom und Immunsuppression",
  "Melanoma in dark skin (often acral)": "Melanom bei dunkler Haut (oft akral)",
  "Melanoma of the eye (uveal)": "Melanom des Auges (uveal)",
  "Melanoma-Detector (VukIG)": "Melanoma-Detector (VukIG)",
  "Melanomas already diagnosed": "Bereits diagnostizierte Melanome",
  "Melanomas already diagnosed in me": "Bei mir bereits diagnostizierte Melanome",
  "Mesothelioma": "Mesotheliom",
  "Met": "Erfüllt",
  "Meta-analysis": "Metaanalyse",
  "Method 1 - App 1 (Deborah Adedigba)": "Methode 1 - App 1 (Deborah Adedigba)",
  "Method 1 turned off in the settings.": "Methode 1 in den Einstellungen deaktiviert.",
  "Method 2 - SkinSense (online service)": "Methode 2 - SkinSense (Online-Dienst)",
  "Method 2 not run (turned off in the settings): the photo did not leave the PC.": "Methode 2 nicht ausgeführt (in den Einstellungen deaktiviert): Das Foto hat den PC nicht verlassen.",
  "Method 3 did NOT analyse the photo: the project is a prototype without a model. Its server merely receives the image (no neural network), so any reassuring text it shows does not come from an analysis and has no value.": "Methode 3 hat das Foto NICHT analysiert: Das Projekt ist ein Prototyp ohne Modell. Sein Server nimmt das Bild lediglich entgegen (kein neuronales Netz); jeder beruhigende Text, den er anzeigt, stammt daher nicht aus einer Analyse und hat keinerlei Wert.",
  "Method 4 - vatsal30": "Methode 4 - vatsal30",
  "Method 4 turned off in the settings.": "Methode 4 in den Einstellungen deaktiviert.",
  "Method 5 is an Android app: it cannot run on the PC. Install the APK on the phone, frame the mole and note the result by hand below.\nApp result on the phone: ______________________________": "Methode 5 ist eine Android-App: Sie kann nicht auf dem PC laufen. Installieren Sie die APK auf dem Telefon, richten Sie die Kamera auf das Muttermal und notieren Sie das Ergebnis unten von Hand.\nErgebnis der App auf dem Telefon: ______________________________",
  "Method {n}": "Methode {n}",
  "Method {n} said:": "Methode {n} meldete:",
  "Methods disagree": "Methoden uneinig",
  "Moderate": "Mäßig",
  "Moderate UV: protection needed in the middle of the day": "Mäßige UV-Strahlung: Zur Mittagszeit ist Schutz nötig",
  "Mole archived. You will find it at the bottom of the list.": "Muttermal archiviert. Sie finden es am Ende der Liste.",
  "Mole deleted.": "Muttermal gelöscht.",
  "Mole diameter over time": "Durchmesser des Muttermals im Zeitverlauf",
  "Mole map": "Muttermal-Karte",
  "Mole name": "Name des Muttermals",
  "Mole not found.": "Muttermal nicht gefunden.",
  "Mole saved. Now add the first photo: it will be your \"baseline photo\".": "Muttermal gespeichert. Fügen Sie jetzt das erste Foto hinzu: Es wird Ihr „Ausgangsfoto“.",
  "Mole sheet – {nome}": "Muttermal-Blatt – {nome}",
  "Mole with photos": "Muttermal mit Fotos",
  "Mole {n}": "Muttermal {n}",
  "More than 6 mm (but smaller melanomas exist).": "Mehr als 6 mm (es gibt aber auch kleinere Melanome).",
  "Most recent studies on predisposition genes": "Neueste Studien zu Prädispositionsgenen",
  "Most relevant studies": "Relevanteste Studien",
  "Move the pointer over the body to see the area": "Bewegen Sie den Zeiger über den Körper, um den Bereich zu sehen",
  "Multiple BAP1-spectrum tumours (uveal melanoma, mesothelioma, renal carcinoma, cutaneous melanoma)": "Mehrere Tumoren des BAP1-Spektrums (uveales Melanom, Mesotheliom, Nierenzellkarzinom, kutanes Melanom)",
  "My location ({lat}; {lon})": "Mein Standort ({lat}; {lon})",
  "NCCN": "NCCN",
  "NCCN Clinical Practice Guidelines in Oncology: Melanoma: Cutaneous (current version; the full text requires free registration)": "NCCN Clinical Practice Guidelines in Oncology: Melanoma: Cutaneous (aktuelle Version; der Volltext erfordert eine kostenlose Registrierung)",
  "Name": "Name",
  "Name or nickname": "Name oder Spitzname",
  "Nape and neck": "Nacken und Hals",
  "Natural hair colour (when young)": "Natürliche Haarfarbe (in jungen Jahren)",
  "Neck": "Hals",
  "Needs attention": "Auffällig",
  "NeoTracker closed": "NeoTracker beendet",
  "NeoTracker is closed": "NeoTracker ist beendet",
  "NeoTracker is not a genetic counselling service. For a personal assessment, see your dermatologist or an oncological genetics centre.": "NeoTracker ist kein genetischer Beratungsdienst. Für eine persönliche Einschätzung wenden Sie sich an Ihre Hautärztin bzw. Ihren Hautarzt oder an ein onkogenetisches Zentrum.",
  "NeoTracker is not a medical device and does not make diagnoses.": "NeoTracker ist kein Medizinprodukt und stellt keine Diagnosen.",
  "NeoTracker is not a medical tool and does not make diagnoses. For any mole that changes, bleeds, itches or worries you, see a dermatologist.": "NeoTracker ist kein medizinisches Werkzeug und stellt keine Diagnosen. Bei jedem Muttermal, das sich verändert, blutet, juckt oder Ihnen Sorgen macht, wenden Sie sich an eine Hautärztin oder einen Hautarzt.",
  "NeoTracker is not responding": "NeoTracker antwortet nicht",
  "Never": "Nie",
  "New mole": "Neues Muttermal",
  "New user": "Neuer Benutzer",
  "Next {n} hours": "Nächste {n} Stunden",
  "No": "Nein",
  "No alarm from the models": "Kein Alarm durch die Modelle",
  "No articles found.": "Keine Artikel gefunden.",
  "No city found with this name.": "Keine Stadt mit diesem Namen gefunden.",
  "No image set.": "Kein Bild festgelegt.",
  "No method produced a result: check the reasons listed below.": "Keine Methode hat ein Ergebnis geliefert: Prüfen Sie die unten genannten Gründe.",
  "No moles yet": "Noch keine Muttermale",
  "No photo recorded yet.": "Noch kein Foto erfasst.",
  "No photos yet": "Noch keine Fotos",
  "No photos: add the first one": "Keine Fotos: Fügen Sie das erste hinzu",
  "No result": "Kein Ergebnis",
  "No special protection needed for normal activities; sunglasses on bright days.": "Kein besonderer Schutz für normale Aktivitäten nötig; an hellen Tagen eine Sonnenbrille.",
  "None": "Keine",
  "None of the methods that responded flags the lesion as suspicious. This does NOT rule out a melanoma: the tools are not clinically validated and are also wrong in this direction. If the mole is asymmetric, has irregular borders, several colours, is larger than 6 mm or has changed over time, a visit is still needed.": "Keine der Methoden, die geantwortet haben, meldet die Läsion als verdächtig. Das schließt ein Melanom NICHT aus: Die Werkzeuge sind klinisch nicht validiert und irren sich auch in dieser Richtung. Wenn das Muttermal asymmetrisch ist, unregelmäßige Ränder oder mehrere Farben hat, größer als 6 mm ist oder sich verändert hat, ist ein Arztbesuch weiterhin nötig.",
  "Normal photo": "Normales Foto",
  "Normal photo (smartphone)": "Normales Foto (Smartphone)",
  "Not allowed.": "Nicht erlaubt.",
  "Not met": "Nicht erfüllt",
  "Not scanned yet": "Noch nicht durchsucht",
  "Not scanned yet.": "Noch nicht durchsucht.",
  "Not specified": "Nicht angegeben",
  "Notes": "Notizen",
  "Notes on the mole…": "Notizen zum Muttermal…",
  "Notes:": "Notizen:",
  "Nothing is sent online, except the requests you turn on (UV weather, PubMed literature, SkinSense).": "Es wird nichts online gesendet, außer den Anfragen, die Sie aktivieren (UV-Wetter, PubMed-Literatur, SkinSense).",
  "Now": "Jetzt",
  "Number of moles": "Anzahl der Muttermale",
  "Observational study": "Beobachtungsstudie",
  "Of any degree of kinship.": "Jeder Verwandtschaftsgrad.",
  "Off by default: with the other methods the photo never leaves this computer.": "Standardmäßig ausgeschaltet: Bei den anderen Methoden verlässt das Foto diesen Computer nie.",
  "Often": "Oft",
  "Olive skin. Burns little, tans easily.": "Olivfarbene Haut. Verbrennt kaum, bräunt leicht.",
  "One Call {n}: {t}": "One Call {n}: {t}",
  "Only invasive primary melanomas count.": "Es zählen nur invasive primäre Melanome.",
  "Open the «API keys» page of your account and copy the key.": "Öffnen Sie in Ihrem Konto die Seite «API keys» und kopieren Sie den Schlüssel.",
  "Open-Meteo (default)": "Open-Meteo (Standard)",
  "OpenWeather key": "OpenWeather-Schlüssel",
  "OpenWeather key saved ({finale}).": "OpenWeather-Schlüssel gespeichert ({finale}).",
  "OpenWeather rejected the key (401): check that it is correct and that the 'One Call API' plan (pay per call, 1,000 free calls per day) is active on your account. After subscribing, the key can take a few minutes to activate.": "OpenWeather hat den Schlüssel abgelehnt (401): Prüfen Sie, ob er korrekt ist und ob in Ihrem Konto der Tarif „One Call API“ (Bezahlung pro Abruf, 1.000 kostenlose Abrufe pro Tag) aktiv ist. Nach dem Abschluss kann es einige Minuten dauern, bis der Schlüssel aktiv ist.",
  "OpenWeather unavailable ({e}). Showing Open-Meteo data.": "OpenWeather nicht verfügbar ({e}). Es werden die Daten von Open-Meteo angezeigt.",
  "OpenWeather: call limit reached (429).": "OpenWeather: Abruflimit erreicht (429).",
  "Operation not allowed on this address.": "Vorgang für diese Adresse nicht erlaubt.",
  "Optional": "Optional",
  "Origin not allowed.": "Herkunft nicht zulässig.",
  "Original photo": "Originalfoto",
  "Other": "Andere",
  "Other relatives with melanoma": "Weitere Verwandte mit Melanom",
  "Other skin cancers (basal cell and squamous cell carcinoma)": "Andere Hautkrebsarten (Basaliom, Plattenepithelkarzinom)",
  "Overlay with slider": "Mit Regler überlagern",
  "Page not found.": "Seite nicht gefunden.",
  "Pancreatic cancer": "Bauchspeicheldrüsenkrebs",
  "Parents, brothers, sisters, children.": "Eltern, Brüder, Schwestern, Kinder.",
  "Parents, siblings or children.": "Eltern, Geschwister oder Kinder.",
  "Paste the key above and press «Test the key». After subscribing, the key can take a few minutes to activate. The program tries One Call 4.0 first and, if the key belongs to an older plan, One Call 3.0.": "Fügen Sie den Schlüssel oben ein und klicken Sie auf «Schlüssel testen». Nach dem Abschluss kann es einige Minuten dauern, bis der Schlüssel aktiv ist. Das Programm versucht zuerst One Call 4.0 und, falls der Schlüssel zu einem älteren Tarif gehört, One Call 3.0.",
  "Paste the key first.": "Fügen Sie zuerst den Schlüssel ein.",
  "Paste the key here (32 letters and digits)": "Schlüssel hier einfügen (32 Buchstaben und Ziffern)",
  "People with many moles, atypical moles or a history of melanoma should protect themselves even when the index is moderate.": "Wer viele Muttermale, atypische Muttermale oder ein Melanom in der Vorgeschichte hat, sollte sich auch bei mäßigem Index schützen.",
  "Permission denied. You can search for the city by name or use the estimate from the internet address.": "Berechtigung verweigert. Sie können die Stadt nach Namen suchen oder die Schätzung über die Internetadresse verwenden.",
  "Personal data": "Persönliche Daten",
  "Personal details": "Angaben zur Person",
  "Personal history": "Persönliche Vorgeschichte",
  "Personal melanoma and a first-degree relative with pancreatic cancer": "Eigenes Melanom und ein Verwandter ersten Grades mit Bauchspeicheldrüsenkrebs",
  "Personal picture": "Eigenes Bild",
  "Personal picture saved.": "Eigenes Bild gespeichert.",
  "Phenotype: skin, hair, eyes": "Phänotyp: Haut, Haare, Augen",
  "Photo analysis": "Fotoanalyse",
  "Photo date is too old.": "Das Aufnahmedatum liegt zu weit zurück.",
  "Photo deleted.": "Foto gelöscht.",
  "Photo file not found.": "Fotodatei nicht gefunden.",
  "Photo from {data}": "Foto vom {data}",
  "Photo history": "Fotoverlauf",
  "Photo history ({n})": "Fotoverlauf ({n})",
  "Photo not found.": "Foto nicht gefunden.",
  "Photo saved ({data}).": "Foto gespeichert ({data}).",
  "Photo saved ({data}, date read from the photo).": "Foto gespeichert ({data}, Datum aus dem Foto gelesen).",
  "Photo type": "Fototyp",
  "Phototype": "Hauttyp",
  "Phototype (Fitzpatrick classification)": "Hauttyp (Fitzpatrick-Klassifikation)",
  "Phototype, age and family history do not change the neural networks' result (they only look at pixels): they serve to put the risk in context.": "Hauttyp, Alter und Familiengeschichte verändern das Ergebnis der neuronalen Netze nicht (sie betrachten nur Pixel): Sie dienen dazu, das Risiko einzuordnen.",
  "Picked for you (based on profile and mole locations)": "Für Sie ausgewählt (nach Profil und Lage der Muttermale)",
  "Picture removed.": "Bild entfernt.",
  "Pillow is not installed: previews will use the original photos (install with «py -m pip install pillow»).": "Pillow ist nicht installiert: Die Vorschauen verwenden die Originalfotos (Installation mit «py -m pip install pillow»).",
  "Place a ruler or a coin next to the mole: it is used to measure the diameter.": "Legen Sie ein Lineal oder eine Münze neben das Muttermal: Damit lässt sich der Durchmesser messen.",
  "Preparing the sheet…": "Blatt wird vorbereitet…",
  "Press": "Drücken Sie",
  "Preview": "Vorschau",
  "Primary melanomas indicated: {mel_pers}.": "Angegebene primäre Melanome: {mel_pers}.",
  "Print a sheet with all the moles": "Blatt mit allen Muttermalen drucken",
  "Print the sheet for this mole": "Blatt für dieses Muttermal drucken",
  "Printed on {data} with NeoTracker": "Gedruckt am {data} mit NeoTracker",
  "Profile": "Profil",
  "Profile not filled in.": "Profil nicht ausgefüllt.",
  "Profile of {nome}": "Profil von {nome}",
  "Profile to complete": "Profil noch zu vervollständigen",
  "Projects folder:": "Projektordner:",
  "Protection necessary: reduce exposure between 10 and 16, SPF 30+ sunscreen, hat and sunglasses.": "Schutz erforderlich: Verringern Sie die Sonnenexposition zwischen 10 und 16 Uhr, Sonnencreme LSF 30+, Hut und Sonnenbrille.",
  "Protection not needed for normal activities (beware of snow, water, altitude).": "Für normale Aktivitäten ist kein Schutz nötig (Vorsicht bei Schnee, Wasser, Höhe).",
  "Protection recommended: shade in the middle of the day, hat, sunglasses and sunscreen.": "Schutz empfohlen: Schatten zur Mittagszeit, Hut, Sonnenbrille und Sonnencreme.",
  "PubMed is a service of the National Library of Medicine. Abstracts are shown for personal consultation, in English; for the full text, open the article on the journal's website.": "PubMed ist ein Dienst der National Library of Medicine. Die Abstracts werden zur persönlichen Information auf Englisch angezeigt; für den Volltext öffnen Sie den Artikel auf der Website der Zeitschrift.",
  "PubMed is unreachable: showing the last saved search from {data}.": "PubMed ist nicht erreichbar: Es wird die letzte gespeicherte Suche vom {data} angezeigt.",
  "PubMed responded with error {code}": "PubMed hat mit Fehler {code} geantwortet",
  "PubMed unreachable (check the internet connection)": "PubMed nicht erreichbar (prüfen Sie die Internetverbindung)",
  "PubMed {pmid} · abstract not available": "PubMed {pmid} · Abstract nicht verfügbar",
  "Queued (position {n})…": "In der Warteschlange (Position {n})…",
  "Queued…": "In der Warteschlange…",
  "Quit the program": "Programm beenden",
  "R": "R",
  "R = patient's right · L = left": "R = rechts des Patienten · L = links",
  "Randomised trial": "Randomisierte Studie",
  "Rare": "Selten",
  "Rare variants concentrated in codon 24: the family picture is indistinguishable from that of CDKN2A.": "Seltene Varianten, die sich im Codon 24 häufen: Das Familienbild ist von dem bei CDKN2A nicht zu unterscheiden.",
  "Re-analyse": "Erneut analysieren",
  "Read the abstract": "Abstract lesen",
  "Recent, relevant articles on recognising suspicious moles, on the reliability of apps and artificial intelligence, and on hereditary melanoma. Results come from PubMed, the public database of the National Library of Medicine (USA).": "Aktuelle, relevante Artikel zum Erkennen verdächtiger Muttermale, zur Zuverlässigkeit von Apps und künstlicher Intelligenz und zum erblichen Melanom. Die Ergebnisse stammen von PubMed, der öffentlichen Datenbank der National Library of Medicine (USA).",
  "Recognising a suspicious mole": "Ein verdächtiges Muttermal erkennen",
  "Red": "Rot",
  "Red or blond hair": "Rote oder blonde Haare",
  "Refresh": "Aktualisieren",
  "Relatives with astrocytoma (brain tumour)": "Verwandte mit Astrozytom (Hirntumor)",
  "Relatives with kidney carcinoma": "Verwandte mit Nierenzellkarzinom",
  "Relatives with melanoma of the eye (uveal)": "Verwandte mit Melanom des Auges (uveal)",
  "Relatives with mesothelioma": "Verwandte mit Mesotheliom",
  "Relatives with pancreatic cancer (in total)": "Verwandte mit Bauchspeicheldrüsenkrebs (insgesamt)",
  "Remove": "Entfernen",
  "Remove the key?": "Schlüssel entfernen?",
  "Rename": "Umbenennen",
  "Rename user": "Benutzer umbenennen",
  "Repeat the search ignoring the saved results": "Suche wiederholen und gespeicherte Ergebnisse ignorieren",
  "Request too large.": "Anfrage zu groß.",
  "Restore": "Wiederherstellen",
  "Review": "Übersichtsarbeit",
  "Reviews on familial melanoma (CDKN2A, CDK4)": "Übersichtsarbeiten zum familiären Melanom (CDKN2A, CDK4)",
  "Risk factors indicated:": "Angegebene Risikofaktoren:",
  "Risk factors present": "Vorhandene Risikofaktoren",
  "Role and literature": "Rolle und Literatur",
  "Roughly how many moles do you have on your body?": "Wie viele Muttermale haben Sie ungefähr am Körper?",
  "Same light (daylight, no flash) and same distance every time, about 10–15 cm.": "Jedes Mal dasselbe Licht (Tageslicht, ohne Blitz) und derselbe Abstand, etwa 10–15 cm.",
  "Save": "Speichern",
  "Save an OpenWeather key first.": "Speichern Sie zuerst einen OpenWeather-Schlüssel.",
  "Save mole": "Muttermal speichern",
  "Save photo": "Foto speichern",
  "Saved ✓": "Gespeichert ✓",
  "Saving…": "Wird gespeichert…",
  "Scalp (head)": "Kopfhaut (Kopf)",
  "Scan complete.": "Suche abgeschlossen.",
  "Scan the literature": "Literatur durchsuchen",
  "Scan the literature on genes": "Literatur zu den Genen durchsuchen",
  "Scientific literature": "Wissenschaftliche Literatur",
  "Search": "Suchen",
  "Search for a city (e.g. Turin)": "Stadt suchen (z. B. Turin)",
  "Search for more (e.g. \"ugly duckling sign\", \"nail melanoma\"…)": "Weiter suchen (z. B. \"ugly duckling sign\", \"nail melanoma\"…)",
  "Search the literature": "In der Literatur suchen",
  "Searches go from this computer to PubMed (no personal data is sent). Results are saved for 7 days.": "Die Suchen gehen von diesem Computer an PubMed (es werden keine persönlichen Daten gesendet). Die Ergebnisse werden 7 Tage gespeichert.",
  "Searches use PubMed's public E-utilities. NCBI asks, as a courtesy, for a contact email: it is optional and is sent only to PubMed.": "Die Suchen verwenden die öffentlichen E-Utilities von PubMed. Das NCBI bittet höflich um eine Kontakt-E-Mail: Sie ist freiwillig und wird nur an PubMed gesendet.",
  "Searching PubMed…": "Suche in PubMed…",
  "Searching…": "Suche läuft…",
  "Section {n} of {tot}…": "Abschnitt {n} von {tot}…",
  "Sections": "Abschnitte",
  "Send the photos to SkinSense?": "Fotos an SkinSense senden?",
  "Sequential photography and monitoring of moles over time": "Sequenzielle Fotografie und Verlaufskontrolle von Muttermalen",
  "Settings": "Einstellungen",
  "Several colours in the same mole (brown, black, red, blue, white).": "Mehrere Farben im selben Muttermal (braun, schwarz, rot, blau, weiß).",
  "Sex": "Geschlecht",
  "Shade, clothing, a hat and sunscreen are needed in the middle of the day.": "Zur Mittagszeit sind Schatten, Kleidung, Hut und Sonnencreme nötig.",
  "Sheet for the dermatologist": "Blatt für die Hautärztin / den Hautarzt",
  "Shoulder blade area, left": "Schulterblattbereich links",
  "Shoulder blade area, right": "Schulterblattbereich rechts",
  "Shoulder, left": "Schulter links",
  "Shoulder, right": "Schulter rechts",
  "Show side by side": "Nebeneinander anzeigen",
  "Show the whole body": "Ganzen Körper anzeigen",
  "Showing {n} photos out of {tot}.": "Es werden {n} von {tot} Fotos angezeigt.",
  "Significant risk factors are present: periodic dermatological check-ups (the dermatologist decides how often) and regular skin self-examination are recommended.": "Es liegen relevante Risikofaktoren vor: Empfohlen werden regelmäßige dermatologische Kontrollen (die Häufigkeit legt die Hautärztin oder der Hautarzt fest) und eine regelmäßige Selbstuntersuchung der Haut.",
  "Simplified criteria, for information only. Genetic testing concerns a small minority of people and is not a routine examination: it is up to the specialist to decide whether and which test to offer, usually after genetic counselling and, when possible, starting from a relative who has had the disease.": "Vereinfachte Kriterien, nur zur Information. Ein Gentest betrifft eine kleine Minderheit von Menschen und ist keine Routineuntersuchung: Ob und welcher Test angeboten wird, entscheidet die Fachärztin oder der Facharzt, in der Regel nach einer genetischen Beratung und möglichst ausgehend von einem erkrankten Angehörigen.",
  "Site": "Stelle",
  "Site (editable)": "Stelle (änderbar)",
  "Skin self-examination": "Selbstuntersuchung der Haut",
  "Skin that burns easily and tans little.": "Haut, die leicht verbrennt und kaum bräunt.",
  "SkinSense (online service)": "SkinSense (Online-Dienst)",
  "SkinSense is a third-party online service: the photos of your moles would be sent over the internet to a server we do not control. The photos are data about your health. Do you want to enable it?": "SkinSense ist ein Online-Dienst eines Dritten: Die Fotos Ihrer Muttermale würden über das Internet an einen Server gesendet, den wir nicht kontrollieren. Die Fotos sind Gesundheitsdaten. Möchten Sie ihn aktivieren?",
  "SkinSense is on: the photo (without metadata) will be sent to an online service.": "SkinSense ist aktiv: Das Foto (ohne Metadaten) wird an einen Online-Dienst gesendet.",
  "SkinSense turned off.": "SkinSense deaktiviert.",
  "SkinSense turned on.": "SkinSense aktiviert.",
  "Smartphone apps and skin cancer risk: diagnostic accuracy": "Smartphone-Apps und Hautkrebsrisiko: diagnostische Genauigkeit",
  "Some risk factors are present: careful sun protection and regular self-examination; a basic dermatological check-up is a good habit.": "Es liegen einige Risikofaktoren vor: sorgfältiger Sonnenschutz und regelmäßige Selbstuntersuchung; eine dermatologische Basiskontrolle ist eine gute Gewohnheit.",
  "Something went wrong": "Etwas ist schiefgelaufen",
  "Sometimes": "Manchmal",
  "Source:": "Quelle:",
  "Sources": "Quellen",
  "Subscribe to the pay-per-call «One Call API» plan": "Schließen Sie den Tarif «One Call API» mit Bezahlung pro Abruf ab",
  "Sun exposure": "Sonnenexposition",
  "Sunbeds": "Solarien",
  "Sunburns": "Sonnenbrände",
  "Sunburns with blisters (especially as a child or teenager)": "Sonnenbrände mit Blasen (vor allem als Kind oder Jugendlicher)",
  "Switch user": "Benutzer wechseln",
  "Syndromic": "Syndromal",
  "Systematic review": "Systematische Übersichtsarbeit",
  "Tanning lamps": "Solarien",
  "Tanning lamps or sunbeds": "Bräunungslampen oder Sonnenbänke",
  "Telomerase: promoter variants described in families with melanoma.": "Telomerase: Promotorvarianten, die in Familien mit Melanom beschrieben wurden.",
  "Telomere gene (shelterin complex): rare variants in families with melanoma.": "Telomer-Gen (Shelterin-Komplex): seltene Varianten in Familien mit Melanom.",
  "Telomere gene: rare variants in some families with melanoma.": "Telomer-Gen: seltene Varianten in einigen Familien mit Melanom.",
  "Test the key": "Schlüssel testen",
  "Testing the key…": "Schlüssel wird getestet…",
  "The Open-Meteo service is not responding ({e}).": "Der Dienst Open-Meteo antwortet nicht ({e}).",
  "The OpenWeather key contains invalid characters (it is usually 32 letters/digits).": "Der OpenWeather-Schlüssel enthält ungültige Zeichen (normalerweise sind es 32 Buchstaben/Ziffern).",
  "The Pillow library is old and has known security problems: update it with «py -m pip install -U pillow».": "Die Bibliothek Pillow ist veraltet und hat bekannte Sicherheitsprobleme: Aktualisieren Sie sie mit «py -m pip install -U pillow».",
  "The WHO recommends protection from a UV index of 3.": "Die WHO empfiehlt Schutz ab einem UV-Index von 3.",
  "The analysis did not produce the report. Last lines of the log: {log}": "Die Analyse hat keinen Bericht erzeugt. Letzte Zeilen des Protokolls: {log}",
  "The analysis failed.": "Die Analyse ist fehlgeschlagen.",
  "The articles are chosen by an automatic search and have not been assessed by NeoTracker: read them with your doctor.": "Die Artikel werden durch eine automatische Suche ausgewählt und wurden von NeoTracker nicht bewertet: Lesen Sie sie gemeinsam mit Ihrer Ärztin oder Ihrem Arzt.",
  "The choice applies to all users of this computer. The original and binding text of the legal notices is the English one; the full text report stays in English.": "Die Auswahl gilt für alle Benutzer dieses Computers. Maßgeblich und verbindlich ist der englische Originaltext der rechtlichen Hinweise; der vollständige Textbericht bleibt auf Englisch.",
  "The computer cannot determine the position. Search for the city by name.": "Der Computer kann den Standort nicht bestimmen. Suchen Sie die Stadt nach Namen.",
  "The data entered meet at least one criterion described in the literature. We advise you to talk about it with your dermatologist or a medical geneticist (oncological genetic counselling): the specialist will decide whether and which test to offer, usually after counselling and, when possible, starting from an affected relative. Genes most cited by the guidelines: {geni}. The use of multigene panels is still under discussion among specialists: that is why counselling before the test matters.": "Die eingegebenen Daten erfüllen mindestens ein in der Literatur beschriebenes Kriterium. Wir empfehlen, mit Ihrer Hautärztin bzw. Ihrem Hautarzt oder einem Facharzt für Humangenetik (onkogenetische Beratung) darüber zu sprechen: Die Fachperson entscheidet, ob und welcher Test angeboten wird, in der Regel nach der Beratung und möglichst ausgehend von einem erkrankten Angehörigen. Am häufigsten in den Leitlinien genannte Gene: {geni}. Der Einsatz von Multigen-Panels wird unter Fachleuten noch diskutiert: Deshalb ist die Beratung vor dem Test wichtig.",
  "The file is empty.": "Die Datei ist leer.",
  "The file is not a readable image or is too large.": "Die Datei ist kein lesbares Bild oder zu groß.",
  "The file is not a readable image, is damaged or has too many pixels (maximum {mp} megapixels).": "Die Datei ist kein lesbares Bild, ist beschädigt oder hat zu viele Pixel (höchstens {mp} Megapixel).",
  "The file is too large (maximum 40 MB).": "Die Datei ist zu groß (höchstens 40 MB).",
  "The first analysis can take several minutes (the models are loaded into memory).": "Die erste Analyse kann mehrere Minuten dauern (die Modelle werden in den Speicher geladen).",
  "The image exceeds {mb} MB.": "Das Bild ist größer als {mb} MB.",
  "The index is a forecast: the actual value depends on clouds, altitude and reflections.": "Der Index ist eine Vorhersage: Der tatsächliche Wert hängt von Wolken, Höhe und Reflexionen ab.",
  "The information on risk, literature and genetics is for general information and does not replace the advice of a doctor or geneticist.": "Die Informationen zu Risiko, Literatur und Genetik dienen der allgemeinen Aufklärung und ersetzen nicht die Beratung durch eine Ärztin, einen Arzt oder einen Humangenetiker.",
  "The key stays saved only on your computer and is never shown to, or sent to, the program's web page: the Python program uses it to call OpenWeather.": "Der Schlüssel bleibt nur auf Ihrem Computer gespeichert und wird der Webseite des Programms nie angezeigt oder gesendet: Das Python-Programm verwendet ihn, um OpenWeather aufzurufen.",
  "The key will be deleted from this computer. You can enter it again whenever you want.": "Der Schlüssel wird von diesem Computer gelöscht. Sie können ihn jederzeit erneut eingeben.",
  "The location is saved only on this computer; it is sent to the weather service (rounded coordinates) to get the UV index.": "Der Standort wird nur auf diesem Computer gespeichert; er wird (mit gerundeten Koordinaten) an den Wetterdienst gesendet, um den UV-Index zu erhalten.",
  "The methods are trained on photographs different from yours: changing light, distance or camera can change the answer.": "Die Methoden wurden mit anderen Fotos als Ihren trainiert: Andere Beleuchtung, Entfernung oder Kamera können das Ergebnis verändern.",
  "The middle hours of the day (about 11–16) have the highest index.": "Die Mittagsstunden (etwa 11–16 Uhr) haben den höchsten Index.",
  "The most studied genes": "Die am besten untersuchten Gene",
  "The name": "Der Name",
  "The number of moles is one of the strongest risk factors.": "Die Zahl der Muttermale ist einer der stärksten Risikofaktoren.",
  "The numbers match the following sheets. In the figure: the front view on the left, the back view on the right.": "Die Nummern entsprechen den folgenden Blättern. In der Abbildung: links die Vorderansicht, rechts die Rückansicht.",
  "The p.E318K variant increases the risk of melanoma and renal carcinoma and is associated with many moles.": "Die Variante p.E318K erhöht das Risiko für Melanom und Nierenzellkarzinom und ist mit vielen Muttermalen verbunden.",
  "The photo date cannot be in the future.": "Das Aufnahmedatum darf nicht in der Zukunft liegen.",
  "The photo exceeds {MAX_MB_FOTO} MB.": "Das Foto ist größer als {MAX_MB_FOTO} MB.",
  "The photo exceeds {mb} MB: reduce it or choose another one.": "Das Foto ist größer als {mb} MB: Verkleinern Sie es oder wählen Sie ein anderes.",
  "The photo from {data} and its analysis report will be deleted permanently.": "Das Foto vom {data} und sein Analysebericht werden endgültig gelöscht.",
  "The photo stays on your computer: SkinSense (online service) is turned off.": "Das Foto bleibt auf Ihrem Computer: SkinSense (Online-Dienst) ist ausgeschaltet.",
  "The profile, all moles, all photos and all reports of this user will be deleted permanently. This cannot be undone.": "Das Profil, alle Muttermale, alle Fotos und alle Berichte dieses Benutzers werden endgültig gelöscht. Dies kann nicht rückgängig gemacht werden.",
  "The program will shut down. An analysis in progress will be interrupted. Your data stays saved.": "Das Programm wird beendet. Eine laufende Analyse wird abgebrochen. Ihre Daten bleiben gespeichert.",
  "The result also concerns blood relatives: that is why counselling before and after the test is part of the process.": "Das Ergebnis betrifft auch Blutsverwandte: Deshalb gehört die Beratung vor und nach dem Test zum Ablauf.",
  "The results are experimental estimates and can be wrong in both directions: a reassuring result does not rule out a melanoma, and a result flagging attention does not mean there is one.": "Die Ergebnisse sind experimentelle Schätzungen und können in beide Richtungen falsch sein: Ein beruhigendes Ergebnis schließt ein Melanom nicht aus, ein auffälliges Ergebnis bedeutet nicht, dass eines vorliegt.",
  "The two halves of the mole do not look alike.": "Die beiden Hälften des Muttermals sehen nicht gleich aus.",
  "The view must be 'fronte' or 'retro'.": "Die Ansicht muss 'fronte' oder 'retro' sein.",
  "The «picked for you» sections use words linked to your profile (for example phototype or number of moles): if you prefer not to send them, do not scan that section.": "Die Abschnitte «für Sie ausgewählt» verwenden Begriffe aus Ihrem Profil (zum Beispiel Hauttyp oder Zahl der Muttermale): Wenn Sie diese lieber nicht senden möchten, durchsuchen Sie diesen Abschnitt nicht.",
  "The «ugly duckling» also counts: a mole that looks different from all the others. Nodules that grow quickly or feel hard to the touch should be shown straight away. This reminder does not replace a medical visit.": "Auch das «hässliche Entlein» zählt: ein Muttermal, das sich von allen anderen unterscheidet. Knoten, die schnell wachsen oder sich hart anfühlen, sollten sofort gezeigt werden. Diese Erinnerung ersetzt keinen Arztbesuch.",
  "There are no moles to print.": "Es gibt keine Muttermale zum Drucken.",
  "These are measurements you entered: they are valid if always taken the same way. A mole that grows or changes is a good reason to show it to your dermatologist; the 6 mm line is just the classic reference of the ABCDE criteria.": "Dies sind von Ihnen eingegebene Messwerte: Sie sind aussagekräftig, wenn sie immer auf dieselbe Weise ermittelt werden. Ein Muttermal, das wächst oder sich verändert, ist ein guter Grund, es der Hautärztin oder dem Hautarzt zu zeigen; die 6-mm-Linie ist nur die klassische Referenz der ABCDE-Kriterien.",
  "They do not change the result of the neural networks, which only look at the pixels of the photo. They are used to: (1) put the risk in context, (2) choose the scientific literature suited to you, (3) check the criteria for genetic counselling, (4) calculate how long you can stay in the sun before burning. Everything stays on your computer.": "Sie verändern das Ergebnis der neuronalen Netze nicht, die nur die Pixel des Fotos betrachten. Sie dienen dazu, (1) das Risiko einzuordnen, (2) die für Sie passende wissenschaftliche Literatur auszuwählen, (3) die Kriterien für eine genetische Beratung zu prüfen und (4) zu berechnen, wie lange Sie in der Sonne bleiben können, bevor Sie einen Sonnenbrand bekommen. Alles bleibt auf Ihrem Computer.",
  "Thigh, left": "Oberschenkel links",
  "Thigh, right": "Oberschenkel rechts",
  "Thin clouds do not stop much of the UV: the index can stay high even with a hazy sky.": "Dünne Wolken halten einen Großteil der UV-Strahlung nicht ab: Der Index kann auch bei dunstigem Himmel hoch bleiben.",
  "This browser does not offer geolocation: search for the city by name.": "Dieser Browser bietet keine Standortbestimmung: Suchen Sie die Stadt nach Namen.",
  "This is a cautious estimate that uses the lowest minimal erythema dose for your phototype; with reflections (water, snow, sand), altitude or already reddened skin the time is shorter.": "Das ist eine vorsichtige Schätzung auf Grundlage der niedrigsten minimalen Erythemdosis Ihres Hauttyps; bei Reflexionen (Wasser, Schnee, Sand), in der Höhe oder bei bereits geröteter Haut verkürzt sich die Zeit.",
  "This method sends the pixels of the photo (not the metadata) to an external server.": "Bei dieser Methode werden die Pixel des Fotos (nicht die Metadaten) an einen externen Server gesendet.",
  "This photo has not been analysed yet. The analysis compares several methods on the same image and tells you what each one answered.": "Dieses Foto wurde noch nicht analysiert. Die Analyse vergleicht mehrere Methoden am selben Bild und zeigt Ihnen, was jede geantwortet hat.",
  "This photo is being analysed: wait for it to finish.": "Dieses Foto wird gerade analysiert: Warten Sie, bis die Analyse abgeschlossen ist.",
  "This program helps you keep track of your moles over time: you mark them on a body map, keep their photos with the date and have them analysed by several methods. Start by creating your user.": "Dieses Programm hilft Ihnen, Ihre Muttermale über die Zeit zu verfolgen: Sie markieren sie auf einer Körperkarte, bewahren ihre Fotos mit Datum auf und lassen sie von mehreren Methoden analysieren. Beginnen Sie damit, Ihren Benutzer anzulegen.",
  "This report is NOT a diagnosis. The programs used are research prototypes, not medical devices.": "Dieser Bericht ist KEINE Diagnose. Die verwendeten Programme sind Forschungsprototypen, keine Medizinprodukte.",
  "This sheet collects data entered by the person and photos taken by them. The results of the automatic analysis are experimental, are not a diagnosis and do not replace a dermatological visit or dermoscopy.": "Dieses Blatt enthält Angaben der Person und von ihr aufgenommene Fotos. Die Ergebnisse der automatischen Analyse sind experimentell, keine Diagnose und ersetzen weder den Hautarztbesuch noch die Dermatoskopie.",
  "Thresholds and colours of the WHO international scale. Sources:": "Schwellenwerte und Farben der internationalen WHO-Skala. Quellen:",
  "Time to re-photograph?": "Neu fotografieren?",
  "To close NeoTracker, just close this window with the X at the top right: the program shuts down by itself.": "Um NeoTracker zu beenden, schließen Sie einfach dieses Fenster mit dem X oben rechts: Das Programm beendet sich von selbst.",
  "To confirm, type:": "Zur Bestätigung eingeben:",
  "To delete, type the exact name of the user in the confirmation.": "Zum Löschen geben Sie in der Bestätigung den genauen Namen des Benutzers ein.",
  "To estimate the city, the program contacts the free service ipwho.is, which sees your internet address. Accuracy is at city level (it is sometimes wrong). Proceed?": "Um die Stadt zu schätzen, kontaktiert das Programm den kostenlosen Dienst ipwho.is, der Ihre Internetadresse sieht. Die Genauigkeit entspricht der Stadtebene (manchmal liegt er falsch). Fortfahren?",
  "To see how much sun burns you, enter your phototype in the": "Um zu sehen, wie viel Sonne Sie verbrennt, geben Sie Ihren Hauttyp im Bereich ein",
  "Today's UV index": "UV-Index heute",
  "Today's maximum": "Tagesmaximum",
  "Too many open connections.": "Zu viele offene Verbindungen.",
  "Total diagnoses entered: {diagnosi}. Leachman 2009 counts melanoma and pancreatic cancer in 1st- and 2nd-degree relatives on the same side of the family; astrocytoma is included by the NCCN guidelines.": "Insgesamt angegebene Diagnosen: {diagnosi}. Leachman 2009 berücksichtigt Melanom und Bauchspeicheldrüsenkrebs bei Verwandten 1. und 2. Grades derselben Familienseite; das Astrozytom wird von den NCCN-Leitlinien einbezogen.",
  "Try again": "Erneut versuchen",
  "Type": "Typ",
  "Type a name.": "Geben Sie einen Namen ein.",
  "Type at least 3 characters.": "Geben Sie mindestens 3 Zeichen ein.",
  "Type {n}": "Typ {n}",
  "UV index": "UV-Index",
  "UV index not available": "UV-Index nicht verfügbar",
  "UV index source changed.": "Quelle des UV-Index geändert.",
  "UV index: data source": "UV-Index: Datenquelle",
  "UV rays are harmful to unprotected skin today": "Die UV-Strahlung ist heute für ungeschützte Haut schädlich",
  "UV rays are low today": "Die UV-Strahlung ist heute niedrig",
  "UV rays are very harmful today": "Die UV-Strahlung ist heute sehr schädlich",
  "Ultraviolet rays are the main modifiable risk factor for melanoma. Here you can see how strong they are today where you are.": "UV-Strahlen sind der wichtigste beeinflussbare Risikofaktor für das Melanom. Hier sehen Sie, wie stark sie heute an Ihrem Standort sind.",
  "Unauthorised access.": "Unbefugter Zugriff.",
  "Unauthorised request.": "Nicht autorisierte Anfrage.",
  "Unexpected error: {e}": "Unerwarteter Fehler: {e}",
  "Unknown address.": "Unbekannte Adresse.",
  "Unknown section.": "Unbekannter Abschnitt.",
  "Unsaved changes…": "Nicht gespeicherte Änderungen…",
  "Unsupported format: JPG, PNG, WEBP or BMP are required.": "Nicht unterstütztes Format: Erforderlich sind JPG, PNG, WEBP oder BMP.",
  "Unsupported format: JPG, PNG, WEBP or BMP are required. iPhone HEIC photos must be converted to JPG (camera settings: 'Most Compatible').": "Nicht unterstütztes Format: Erforderlich sind JPG, PNG, WEBP oder BMP. HEIC-Fotos vom iPhone müssen in JPG umgewandelt werden (Kameraeinstellungen: „Maximale Kompatibilität“).",
  "Upper abdomen, left": "Oberbauch links",
  "Upper abdomen, right": "Oberbauch rechts",
  "Use of tanning lamps or sunbeds": "Nutzung von Bräunungslampen oder Sonnenbänken",
  "Use the date written in the photo, if there is one": "Das im Foto gespeicherte Datum verwenden, falls vorhanden",
  "User created. Fill in the profile: it helps put the results in context.": "Benutzer angelegt. Füllen Sie das Profil aus: Es dient dazu, die Ergebnisse einzuordnen.",
  "User deleted.": "Benutzer gelöscht.",
  "User not found.": "Benutzer nicht gefunden.",
  "Version": "Version",
  "Very dark skin. Does not burn.": "Sehr dunkle Haut. Verbrennt nicht.",
  "Very fair skin. Always burns, never tans (often red hair, freckles).": "Sehr helle Haut. Verbrennt immer, bräunt nie (oft rote Haare, Sommersprossen).",
  "Very high": "Sehr hoch",
  "WHO/WMO/UNEP/ICNIRP - Global Solar UV Index: A Practical Guide (2002)": "WHO/WMO/UNEP/ICNIRP - Global Solar UV Index: A Practical Guide (2002)",
  "Warning: I did not find App 1's .venv environment; using the current Python.": "Achtung: Die .venv-Umgebung von App 1 wurde nicht gefunden; es wird das aktuelle Python verwendet.",
  "Weather and UV data:": "Wetter- und UV-Daten:",
  "Welcome to NeoTracker": "Willkommen bei NeoTracker",
  "What is this information used for?": "Wozu dienen diese Angaben?",
  "What to do": "Was tun",
  "What to know before a genetic test": "Was Sie vor einem Gentest wissen sollten",
  "Wheel = zoom · drag = move · double click = enlarge": "Mausrad = Zoom · Ziehen = verschieben · Doppelklick = vergrößern",
  "When you noticed it, whether it itches, whether it has changed…": "Wann es Ihnen aufgefallen ist, ob es juckt, ob es sich verändert hat…",
  "When you subscribe, the default daily limit is 2,000 calls: in the «Billing plans» tab of your account you can lower it to 1,000, so you spend nothing. NeoTracker uses very few (at most 4 every 10 minutes, only when you open the UV Index page).": "Beim Abschluss liegt das tägliche Standardlimit bei 2.000 Abrufen: Im Reiter «Billing plans» Ihres Kontos können Sie es auf 1.000 senken, dann entstehen keine Kosten. NeoTracker braucht nur wenige (höchstens 4 alle 10 Minuten, nur wenn Sie die Seite UV-Index öffnen).",
  "Where they are": "Wo sie sich befinden",
  "Who are you?": "Wer sind Sie?",
  "With or without a test, for people with a family history, sun protection, skin self-examination and regular dermatological check-ups remain essential.": "Mit oder ohne Test bleiben bei familiärer Vorbelastung Sonnenschutz, Selbstuntersuchung der Haut und regelmäßige dermatologische Kontrollen entscheidend.",
  "With the data entered you do not meet the most commonly used criteria. Genetic testing for melanoma is indicated only in a small minority of people and is not offered routinely. If your family history changes or you have doubts, update your profile and talk to your dermatologist.": "Mit den eingegebenen Daten erfüllen Sie die gebräuchlichsten Kriterien nicht. Ein Gentest auf Melanom ist nur bei einer kleinen Minderheit von Menschen angezeigt und wird nicht routinemäßig angeboten. Wenn sich Ihre Familiengeschichte ändert oder Sie Zweifel haben, aktualisieren Sie Ihr Profil und sprechen Sie mit Ihrer Hautärztin oder Ihrem Hautarzt.",
  "With the data entered, no known risk factors appear. Complete your profile if information is missing.": "Mit den eingegebenen Daten sind keine bekannten Risikofaktoren erkennbar. Vervollständigen Sie Ihr Profil, falls Angaben fehlen.",
  "With your phototype ({fototipo})": "Mit Ihrem Hauttyp ({fototipo})",
  "Without Pillow the image must be a JPG/PNG under 400 KB (the page reduces it by itself: try again with the 'Choose image' function).": "Ohne Pillow muss das Bild eine JPG/PNG-Datei unter 400 KB sein (die Seite verkleinert es selbst: Versuchen Sie es erneut mit der Funktion „Bild auswählen“).",
  "Woman": "Frau",
  "Work or prolonged activity outdoors": "Arbeit oder längere Aktivität im Freien",
  "Yes": "Ja",
  "Yes, enable": "Ja, aktivieren",
  "Yes, estimate the city": "Ja, Stadt schätzen",
  "Yes, negative": "Ja, negativ",
  "Yes, positive": "Ja, positiv",
  "Yes, uninformative": "Ja, nicht informativ",
  "You can close this window. To reopen the program, use the «NeoTracker» icon on the Desktop.": "Sie können dieses Fenster schließen. Zum erneuten Öffnen verwenden Sie das Symbol «NeoTracker» auf dem Desktop.",
  "You can keep using the app. If you close the window the analysis is not lost: the program finishes the work and then shuts down by itself.": "Sie können die App weiter benutzen. Wenn Sie das Fenster schließen, geht die Analyse nicht verloren: Das Programm beendet die Arbeit und schaltet sich dann von selbst ab.",
  "You can use your own photo, a drawing or an icon. The image is cropped to a square and reduced, stays only on this computer and is never used for mole analysis.": "Sie können ein eigenes Foto, eine Zeichnung oder ein Symbol verwenden. Das Bild wird quadratisch zugeschnitten und verkleinert, bleibt nur auf diesem Computer und wird nie für die Analyse von Muttermalen verwendet.",
  "You chose OpenWeather but the key is missing (Settings): showing Open-Meteo data.": "Sie haben OpenWeather gewählt, aber der Schlüssel fehlt (Einstellungen): Es werden die Daten von Open-Meteo angezeigt.",
  "You chose OpenWeather but there is no key yet: until one is added, the program uses Open-Meteo.": "Sie haben OpenWeather gewählt, aber es gibt noch keinen Schlüssel: Solange er fehlt, verwendet das Programm Open-Meteo.",
  "You said you have already had a genetic test: take the report to your dermatologist.": "Sie haben angegeben, bereits einen Gentest durchgeführt zu haben: Bringen Sie den Befund zu Ihrer Hautärztin oder Ihrem Hautarzt mit.",
  "Your data (including health data) stays on this computer. Only the requests you turn on leave it: UV index (approximate coordinates), PubMed searches (only the search terms) and, only if you enable it, sending the photo to SkinSense.": "Ihre Daten (auch Gesundheitsdaten) bleiben auf diesem Computer. Nur die Anfragen, die Sie aktivieren, verlassen ihn: UV-Index (ungefähre Koordinaten), PubMed-Suchen (nur die Suchbegriffe) und, nur wenn Sie es einschalten, das Senden des Fotos an SkinSense.",
  "Your data against the criteria": "Ihre Angaben im Vergleich zu den Kriterien",
  "Your moles ({n})": "Ihre Muttermale ({n})",
  "Zoom out": "Verkleinern",
  "a few": "wenige",
  "a few freckles": "wenige Sommersprossen",
  "about {minuti} minutes": "etwa {minuti} Minuten",
  "actinic keratosis, a pre-cancerous lesion": "aktinische Keratose, eine Krebsvorstufe",
  "active only if you enable it below": "nur aktiv, wenn Sie es unten einschalten",
  "address not allowed (https only)": "Adresse nicht zulässig (nur https)",
  "all methods with a result flag a mole that needs attention": "alle Methoden mit Ergebnis melden ein auffälliges Muttermal",
  "and click on the exact spot on the body (zoom in with the wheel to be more precise).": "und klicken Sie auf die genaue Stelle am Körper (zoomen Sie mit dem Mausrad für mehr Genauigkeit).",
  "and confirm the email.": "und bestätigen Sie die E-Mail-Adresse.",
  "average of {n} models; mean score {media} (threshold 0)": "Mittelwert aus {n} Modellen; mittlerer Score {media} (Schwelle 0)",
  "back": "hinten",
  "back of the hand": "Handrücken",
  "basal cell carcinoma, a skin cancer": "Basalzellkarzinom, ein Hautkrebs",
  "between the fingers or toes": "zwischen den Fingern oder Zehen",
  "black hair": "schwarze Haare",
  "blond hair": "blonde Haare",
  "blue or grey eyes": "blaue oder graue Augen",
  "brown hair": "braune Haare",
  "cannot start: {e}": "kann nicht gestartet werden: {e}",
  "confidence {perc}": "Sicherheit {perc}",
  "connection failed: {motivo}": "Verbindung fehlgeschlagen: {motivo}",
  "dark eyes": "dunkle Augen",
  "dermoscopic": "dermatoskopisch",
  "dermoscopy": "Dermoskopie",
  "don't know": "weiß nicht",
  "e.g. 4.5": "z. B. 4,5",
  "ear": "Ohr",
  "eyelid": "Augenlid",
  "fewer than 25": "weniger als 25",
  "free, no account or key needed": "kostenlos, ohne Konto und Schlüssel",
  "front": "vorn",
  "green eyes": "grüne Augen",
  "grey or white hair": "graue oder weiße Haare",
  "in clear skies and without protection, at today's peak the skin may redden in": "Bei klarem Himmel und ohne Schutz kann sich die Haut zur heutigen Spitze röten in",
  "in the panel": "im Panel",
  "in {n} day.": "in {n} Tag.",
  "in {n} days.": "in {n} Tagen.",
  "invalid response from the service": "ungültige Antwort des Dienstes",
  "lip": "Lippe",
  "location from internet address not available": "Standort aus der Internetadresse nicht verfügbar",
  "man": "Mann",
  "many": "viele",
  "many freckles": "viele Sommersprossen",
  "melanoma": "Melanom",
  "melanoma detected": "Melanom erkannt",
  "melanoma not detected": "Melanom nicht erkannt",
  "melanoma prob. {perc}": "Melanom-Wahrsch. {perc}",
  "naevus, i.e. a benign mole": "Nävus, also gutartiges Muttermal",
  "name@example.com (optional)": "name@beispiel.de (optional)",
  "never": "nie",
  "no": "nein",
  "no cases indicated": "keine Fälle angegeben",
  "no freckles": "keine Sommersprossen",
  "no method flagged the mole (this does not rule out a melanoma)": "keine Methode hat das Muttermal gemeldet (das schließt ein Melanom nicht aus)",
  "no result available": "kein Ergebnis verfügbar",
  "normal photo": "normales Foto",
  "often": "oft",
  "optional: requires a personal key of your own": "optional: erfordert einen eigenen persönlichen Schlüssel",
  "other": "andere",
  "output interpreted as the 6 skin classes (not verifiable)": "Ausgabe als die 6 Hautklassen gelesen (nicht überprüfbar)",
  "over 2 hours (very low UV)": "über 2 Stunden (sehr niedrige UV-Strahlung)",
  "palm of the hand": "Handfläche",
  "phototype {tipo}": "Hauttyp {tipo}",
  "probability of malignancy estimated by the model: {pm}": "vom Modell geschätzte Wahrscheinlichkeit für Bösartigkeit: {pm}",
  "red hair": "rote Haare",
  "response too large": "Antwort zu groß",
  "response without a lesion name: {risposta}": "Antwort ohne Läsionsnamen: {risposta}",
  "scalp": "Kopfhaut",
  "seborrhoeic keratosis, benign": "seborrhoische Keratose, gutartig",
  "service address not allowed (https required)": "Adresse des Dienstes nicht zulässig (https erforderlich)",
  "service page": "Seite des Dienstes",
  "service unreachable: {ultimo_errore}": "Dienst nicht erreichbar: {ultimo_errore}",
  "significant": "relevant",
  "skin photos": "Hautfotos",
  "sole of the foot": "Fußsohle",
  "sometimes": "manchmal",
  "squamous cell carcinoma, a skin cancer": "Plattenepithelkarzinom, ein Hautkrebs",
  "stopped after {minuti} minutes (maximum time)": "nach {minuti} Minuten abgebrochen (Höchstdauer)",
  "studies on PubMed": "Studien in PubMed",
  "the App 1 models have not been downloaded: they are still Git LFS placeholders. Open PowerShell in the folder {cartella}, run 'git lfs pull', then try again.": "die Modelle von App 1 wurden nicht heruntergeladen: Es sind noch Git-LFS-Platzhalter. Öffnen Sie PowerShell im Ordner {cartella}, führen Sie 'git lfs pull' aus und versuchen Sie es erneut.",
  "the first 1,000 calls per day are free, later ones are charged. OpenWeather may ask for a payment card to activate it: check the conditions on their website.": "die ersten 1.000 Abrufe pro Tag sind kostenlos, weitere kosten Geld. OpenWeather kann zur Aktivierung eine Zahlungskarte verlangen: Prüfen Sie die Bedingungen auf deren Website.",
  "the methods do not agree with each other": "die Methoden sind sich untereinander nicht einig",
  "the model has {n} outputs: meaning unknown": "das Modell hat {n} Ausgaben: Bedeutung unbekannt",
  "the photo does not open as an image ({tipo}): {dettaglio}": "das Foto lässt sich nicht als Bild öffnen ({tipo}): {dettaglio}",
  "the trained weights are missing: in the folder {cartella} there are no files model_fold_0.bin ... model_fold_4.bin. The repository does not contain them: they must be produced with train.py on the SIIM-ISIC dataset.": "Die trainierten Gewichte fehlen: Im Ordner {cartella} liegen die Dateien model_fold_0.bin ... model_fold_4.bin nicht. Das Repository enthält sie nicht: Sie müssen mit train.py auf dem SIIM-ISIC-Datensatz erzeugt werden.",
  "timed out or network unavailable": "Zeitüberschreitung oder Netzwerk nicht verfügbar",
  "today": "heute",
  "top of the foot": "Fußrücken",
  "ukalwa / melanoma-detection (Android app)": "ukalwa / melanoma-detection (Android-App)",
  "under the nail (foot)": "unter dem Nagel (Fuß)",
  "under the nail (hand)": "unter dem Nagel (Hand)",
  "unreadable response: {e}": "Antwort nicht lesbar: {e}",
  "updated": "aktualisiert",
  "vatsal30 / Melanoma-Detection (PyTorch)": "vatsal30 / Melanoma-Detection (PyTorch)",
  "woman": "Frau",
  "yes": "ja",
  "yes, negative": "ja, negativ",
  "yes, positive": "ja, positiv",
  "yes, uninformative": "ja, nicht informativ",
  "yesterday": "gestern",
  "{avviso} The Open-Meteo service is not responding ({e}).": "{avviso} Der Dienst Open-Meteo antwortet nicht ({e}).",
  "{cosa} cannot be empty.": "{cosa} darf nicht leer sein.",
  "{cosa} is too long (maximum {massimo} characters).": "{cosa} ist zu lang (höchstens {massimo} Zeichen).",
  "{file_modello} is still a Git LFS placeholder: run 'git lfs pull' in the folder {cartella}.": "{file_modello} ist noch ein Git-LFS-Platzhalter: Führen Sie 'git lfs pull' im Ordner {cartella} aus.",
  "{file_pesi} is still a Git LFS placeholder: open PowerShell in the folder {cartella} and run 'git lfs pull'.": "{file_pesi} ist noch ein Git-LFS-Platzhalter: Öffnen Sie PowerShell im Ordner {cartella} und führen Sie 'git lfs pull' aus.",
  "{foto} · last {quando}": "{foto} · letzte {quando}",
  "{giorno} at {ora}: UV index {uvi} ({categoria})": "{giorno}, {ora} Uhr: UV-Index {uvi} ({categoria})",
  "{nome} · {mb} MB · click to change": "{nome} · {mb} MB · zum Ändern klicken",
  "{nome}: enter a number.": "{nome}: Geben Sie eine Zahl ein.",
  "{nome}: error.": "{nome}: Fehler.",
  "{nome}: not available.": "{nome}: nicht verfügbar.",
  "{nome}: the value must be between {minimo} and {massimo}.": "{nome}: Der Wert muss zwischen {minimo} und {massimo} liegen.",
  "{n} articles found on PubMed · search of {data}": "{n} Artikel in PubMed gefunden · Suche vom {data}",
  "{n} articles found on PubMed · search of {data} (saved)": "{n} Artikel in PubMed gefunden · Suche vom {data} (gespeichert)",
  "{n} articles on melanoma and «{termine}»": "{n} Artikel zu Melanom und «{termine}»",
  "{n} day": "{n} Tag",
  "{n} day has passed between the two photos.": "Zwischen den beiden Fotos liegt {n} Tag.",
  "{n} days": "{n} Tage",
  "{n} days ago": "vor {n} Tagen",
  "{n} days have passed between the two photos.": "Zwischen den beiden Fotos liegen {n} Tage.",
  "{n} first-degree relative(s) with melanoma": "{n} Verwandte(r) ersten Grades mit Melanom",
  "{n} model files out of 10": "{n} von 10 Modelldateien",
  "{n} model files out of 5": "{n} von 5 Modelldateien",
  "{n} mole": "{n} Muttermal",
  "{n} mole on this sheet": "{n} Muttermal auf diesem Blatt",
  "{n} moles": "{n} Muttermale",
  "{n} moles on this sheet": "{n} Muttermale auf diesem Blatt",
  "{n} months ago": "vor {n} Monaten",
  "{n} of {tot} methods responded": "{n} von {tot} Methoden haben geantwortet",
  "{n} of {tot}: {et}": "{n} von {tot}: {et}",
  "{n} other relative(s) with melanoma": "{n} weitere(r) Verwandte(r) mit Melanom",
  "{n} photo": "{n} Foto",
  "{n} photos": "{n} Fotos",
  "{n} photos in {giorni} (from {da} to {a}).": "{n} Fotos in {giorni} (vom {da} bis {a}).",
  "{n} with astrocytoma": "{n} mit Astrozytom",
  "{n} with pancreatic cancer": "{n} mit Bauchspeicheldrüsenkrebs",
  "{n} with uveal melanoma": "{n} mit uvealem Melanom",
  "{n} year": "{n} Jahr",
  "{n} year ago": "vor {n} Jahr",
  "{n} years": "{n} Jahre",
  "{n} years ago": "vor {n} Jahren",
  "{vista} · position {x}% from the left, {y}% from the top": "{vista} · Position {x} % von links, {y} % von oben",
  "…of which 1st-degree": "…davon 1. Grades",
  "← All moles": "← Alle Muttermale"
};
'''
WEB_FILES["/i18n_de.js"] = ("text/javascript; charset=utf-8", _WEB_I18N_DE_JS.encode("utf-8"))

_WEB_I18N_ES_JS = r'''/* NeoTracker interface translations: es. Key = the English source text.
   Keep the {name} placeholders unchanged. Check: python3 tools/traduzioni.py */
(window.NT_DIZIONARI = window.NT_DIZIONARI || {}).es = {
  "(CC BY 4.0 licence). The free service is for personal, non-commercial use.": "(licencia CC BY 4.0). El servicio gratuito es para uso personal y no comercial.",
  "(empty)": "(vacío)",
  "(local time at the location)": "(hora local del lugar)",
  "(saved search from {data})": "(búsqueda guardada del {data})",
  "(untitled)": "(sin título)",
  "({variazione} mm since the previous photo)": "({variazione} mm desde la foto anterior)",
  "1 photo from {data}, diameter {mm} mm.": "1 foto del {data}, diámetro {mm} mm.",
  "1 photo from {data}.": "1 foto del {data}.",
  "100 or more": "100 o más",
  "100 or more moles on the body": "100 o más lunares en el cuerpo",
  "1st-degree relatives with melanoma": "Familiares de 1.er grado con melanoma",
  "3 = WHO recommends protection from this level": "3 = a partir de aquí la OMS recomienda protección",
  "3 or more primary melanomas in the same person": "3 o más melanomas primarios en la misma persona",
  "50 to 99 moles on the body": "De 50 a 99 lunares en el cuerpo",
  "A few": "Pocas",
  "A mole that changes (shape, borders, colour, size), bleeds, itches or worries you must be shown to a dermatologist, whatever the app says. Regular check-ups with the dermatologist remain irreplaceable.": "Un lunar que cambia (forma, bordes, color, tamaño), sangra, pica o te preocupa debe enseñarse a un dermatólogo, diga lo que diga la aplicación. La revisión periódica con el dermatólogo sigue siendo insustituible.",
  "A positive result indicates a higher risk, not certainty of becoming ill; a negative result does not remove the risk (many families have no identifiable variant).": "Un resultado positivo indica un riesgo más alto, no la certeza de enfermar; un resultado negativo no anula el riesgo (muchas familias no tienen una variante identificable).",
  "A user with this name already exists.": "Ya existe un usuario con este nombre.",
  "ABCDE criteria and the 'ugly duckling' sign": "Criterios ABCDE y signo del «patito feo»",
  "ABCDE reminder": "Recordatorio ABCDE",
  "ABCDE reminder for recognising a mole": "Recordatorio ABCDE para reconocer un lunar",
  "About 5–10% of melanomas occur in families with an inherited predisposition (Leachman 2009). Here you find the criteria specialists use to decide whether to suggest genetic counselling, the genes involved and the literature on each.": "Alrededor del 5-10 % de los melanomas aparecen en familias con una predisposición hereditaria (Leachman 2009). Aquí encuentras los criterios que usan los especialistas para decidir si proponer un asesoramiento genético, los genes implicados y la literatura sobre cada uno.",
  "Accept and continue": "Aceptar y continuar",
  "According to the NCCN guidelines, in an invasive melanoma with a first-degree relative with pancreatic cancer, a multigene panel that includes CDKN2A is recommended.": "Según las guías del NCCN, en un melanoma invasivo con un familiar de primer grado con cáncer de páncreas se recomienda un panel multigénico que incluya CDKN2A.",
  "Acral melanoma (hands, feet, nails): dermoscopy": "Melanoma acral (manos, pies, uñas): dermatoscopia",
  "Add a photo to the history": "Añadir una foto al historial",
  "Add mole": "Añadir lunar",
  "Add the first photo below: it will be the starting point to see whether the mole changes over time.": "Añade abajo la primera foto: será el punto de partida para ver si el lunar cambia con el tiempo.",
  "Add the first photo: it becomes your baseline photo, and every later photo will follow how the mole evolves.": "Añade la primera foto: será tu foto de referencia y cada foto posterior mostrará la evolución del lunar.",
  "Address not allowed.": "Dirección no permitida.",
  "Address too long.": "Dirección demasiado larga.",
  "After": "Después",
  "Age": "Edad",
  "Age, sex and phenotype do not change the output of the neural networks: they are used to show you the risk factors, choose the literature, evaluate the genetics criteria and estimate the time to sunburn.": "La edad, el sexo y el fenotipo no cambian el resultado de las redes neuronales: sirven para mostrarte los factores de riesgo, elegir la literatura, evaluar los criterios de genética y estimar el tiempo hasta la quemadura solar.",
  "All data stays on this computer, in the folder:": "Todos los datos permanecen en este ordenador, en la carpeta:",
  "All its {n} photos and the analysis reports will be deleted permanently.": "Sus {n} fotos y los informes de análisis se eliminarán para siempre.",
  "Also use SkinSense (online service)": "Usar también SkinSense (servicio en línea)",
  "Always shoot from the same angle and keep the original, without filters.": "Haz siempre la foto desde el mismo ángulo y guarda el original, sin filtros.",
  "An estimate is fine.": "Una estimación basta.",
  "Analyse now with all installed methods": "Analizar ahora con todos los métodos instalados",
  "Analyse this photo": "Analizar esta foto",
  "Analysis in progress…": "Análisis en curso…",
  "Analysis interrupted (app closed).": "Análisis interrumpido (aplicación cerrada).",
  "Analysis program (melanoma_batch.py) not found: photos are saved but cannot be analysed.": "Programa de análisis (melanoma_batch.py) no encontrado: las fotos se guardan pero no se pueden analizar.",
  "Analysis program:": "Programa de análisis:",
  "Analysis stopped after {ore} hours (too long).": "Análisis interrumpido tras {ore} horas (demasiado largo).",
  "Analysis: needs attention": "Análisis: requiere atención",
  "Ankle, left": "Tobillo izquierdo",
  "Ankle, right": "Tobillo derecho",
  "Anything else you want to remember (allergies, photosensitising medicines, …)": "Otra cosa que quieras recordar (alergias, medicamentos fotosensibilizantes, …)",
  "App 1 (DeborahAdedigba) - TensorFlow models": "App 1 (DeborahAdedigba) - modelos TensorFlow",
  "Appearance": "Aspecto",
  "Archive (removes it from the map, keeps the data)": "Archivar (lo quita del mapa y conserva los datos)",
  "Archived moles ({n})": "Lunares archivados ({n})",
  "Arm, left": "Brazo izquierdo",
  "Arm, right": "Brazo derecho",
  "Asking the browser for your position… (a permission request may appear)": "Pidiendo la posición al navegador… (puede aparecer una solicitud de permiso)",
  "Associated risk": "Riesgo asociado",
  "Associated with variants of the MC1R gene.": "Asociados a variantes del gen MC1R.",
  "Astrocytoma": "Astrocitoma",
  "Asymmetry": "Asimetría",
  "At least 3 diagnoses among melanoma, pancreatic cancer and astrocytoma in the same family line (yours included)": "Al menos 3 diagnósticos entre melanoma, cáncer de páncreas y astrocitoma en la misma línea familiar (incluido el tuyo)",
  "At least one method (or one of its models) flags a lesion that needs attention. This is not a diagnosis and these tools are often wrong, but it is one more reason not to put off the dermatology visit and to bring this report.": "Al menos un método (o uno de sus modelos) señala una lesión que requiere atención. No es un diagnóstico y estas herramientas se equivocan con frecuencia, pero es un motivo más para no aplazar la visita al dermatólogo y llevar este informe.",
  "Atypical (dysplastic) moles": "Lunares atípicos (displásicos)",
  "Atypical moles": "Lunares atípicos",
  "Automatic (same as the system)": "Automático (como el sistema)",
  "Automatic analysis": "Análisis automático",
  "Avoid direct exposure: unprotected skin can burn within a few minutes.": "Evita la exposición directa: la piel sin proteger puede quemarse en pocos minutos.",
  "Avoid the sun in the middle hours of the day and protect your skin well.": "Evita el sol en las horas centrales del día y protege bien la piel.",
  "BACK": "ESPALDA",
  "BAP1 tumour predisposition syndrome: uveal melanoma, mesothelioma, renal carcinoma, cutaneous melanoma and atypical melanocytic naevi.": "Síndrome de predisposición a tumores BAP1: melanoma uveal, mesotelioma, carcinoma renal, melanoma cutáneo y nevus melanocíticos atípicos.",
  "BAP1-spectrum tumours indicated: {bap1_spettro}. Simplified criterion: the geneticist uses more complete criteria.": "Tumores del espectro BAP1 indicados: {bap1_spettro}. Criterio simplificado: el genetista usa criterios más completos.",
  "Back": "Espalda",
  "Back (middle area), left": "Espalda (zona media) izquierda",
  "Back (middle area), right": "Espalda (zona media) derecha",
  "Back of knee, left": "Hueco poplíteo izquierdo",
  "Back of knee, right": "Hueco poplíteo derecho",
  "Before": "Antes",
  "Before you start": "Antes de empezar",
  "Black": "Negros",
  "Blond": "Rubios",
  "Blue/grey": "Azules/grises",
  "Border": "Bordes",
  "Brown": "Castaños",
  "Buttock, left": "Glúteo izquierdo",
  "Buttock, right": "Glúteo derecho",
  "Calf, left": "Pantorrilla izquierda",
  "Calf, right": "Pantorrilla derecha",
  "Can't do it? Estimate from the internet address": "¿No puedes? Estima desde la dirección de internet",
  "Cancel": "Cancelar",
  "Centre on the map": "Centrar en el mapa",
  "Change": "Cambiar",
  "Change image…": "Cambiar imagen…",
  "Change:": "Variación:",
  "Checking status…": "Comprobando el estado…",
  "Chest, left": "Tórax izquierdo",
  "Chest, right": "Tórax derecho",
  "Choose a personal picture": "Elige una imagen personal",
  "Choose a user and enter their phototype to see how many minutes it takes to burn.": "Elige un usuario e indica su fototipo para ver en cuántos minutos se quema.",
  "Choose an image file (JPG, PNG, WEBP or BMP).": "Elige un archivo de imagen (JPG, PNG, WEBP o BMP).",
  "Choose image…": "Elegir imagen…",
  "Choose the city above: then you will see today's UV index, hour by hour.": "Elige la ciudad arriba: después verás el índice UV de hoy, hora a hora.",
  "Choose user": "Elegir usuario",
  "Choose where you are to see today's UV index.": "Elige dónde te encuentras para ver el índice UV de hoy.",
  "Choose your profile: each person has their own mole map, photos and data.": "Elige tu perfil: cada persona tiene su propio mapa de lunares, sus fotos y sus datos.",
  "Cited by the NCCN guidelines among the genes to consider in melanoma panels (Cowden syndrome).": "Citado por las guías del NCCN entre los genes a considerar en los paneles para melanoma (síndrome de Cowden).",
  "City name": "Nombre de la ciudad",
  "City search also uses Open-Meteo.": "La búsqueda de ciudades también usa Open-Meteo.",
  "Classified as definite human carcinogens (IARC).": "Clasificados como carcinógenos ciertos para el ser humano (IARC).",
  "Click a mole in the list or on the map to see its photo history.": "Haz clic en un lunar de la lista o del mapa para ver su historial fotográfico.",
  "Click on the exact spot on the body where the mole is (you can zoom in first)": "Haz clic en el punto exacto del cuerpo donde está el lunar (puedes ampliar antes)",
  "Click to see the original photo full screen": "Haz clic para ver la foto original a pantalla completa",
  "Clinical trial": "Estudio clínico",
  "Close": "Cerrar",
  "Close NeoTracker": "Cerrar NeoTracker",
  "Close NeoTracker?": "¿Cerrar NeoTracker?",
  "Close the program": "Cerrar el programa",
  "Closing the program": "Cerrar el programa",
  "Colour": "Color",
  "Common variants linked to red hair and fair skin: they raise the melanoma risk moderately. Not a routine test: interpretation is specialist.": "Variantes frecuentes ligadas al pelo rojo y la piel clara: aumentan moderadamente el riesgo de melanoma. No es una prueba rutinaria: la interpretación es especializada.",
  "Compare": "Comparar",
  "Compare shape, borders and colours: if you notice differences, show the photos to your dermatologist.": "Compara la forma, los bordes y los colores: si notas diferencias, enseña las fotos al dermatólogo.",
  "Comparison of two photos": "Comparación de dos fotos",
  "Comparison slider": "Control deslizante de comparación",
  "Confirm": "Confirmar",
  "Consent": "Consentimiento",
  "Count blood relatives (not in-laws) on the same side of the family, maternal or paternal: this is the criterion geneticists use. If you do not know, ask a relative: this information is very useful.": "Cuenta los familiares de sangre (no los políticos) del mismo lado de la familia, materno o paterno: es el criterio que usan los genetistas. Si no lo sabes, pregunta a un familiar: esta información es muy útil.",
  "Create a free account at": "Crea una cuenta gratuita en",
  "Create user": "Crear usuario",
  "Dark": "Oscuros",
  "Dark skin. Rarely burns.": "Piel oscura. Rara vez se quema.",
  "Date of birth": "Fecha de nacimiento",
  "Date of birth out of range.": "Fecha de nacimiento fuera de rango.",
  "Date the photo was taken": "Fecha de la toma",
  "Decrease: {voce}": "Disminuir: {voce}",
  "Deep learning and melanoma: systematic reviews": "Aprendizaje profundo y melanoma: revisiones sistemáticas",
  "Delete": "Eliminar",
  "Delete permanently": "Eliminar definitivamente",
  "Delete photo": "Eliminar foto",
  "Delete this mole and its photos": "Eliminar este lunar y sus fotos",
  "Delete this photo?": "¿Eliminar esta foto?",
  "Delete «{nome}»?": "¿Eliminar «{nome}»?",
  "Dermoscopic": "Dermatoscópica",
  "Dermoscopy and early diagnosis (reviews)": "Dermatoscopia y diagnóstico precoz (revisiones)",
  "Detect my location": "Detectar mi ubicación",
  "Diameter": "Diámetro",
  "Diameter (mm)": "Diámetro (mm)",
  "Diameter over time": "Diámetro a lo largo del tiempo",
  "Diameter:": "Diámetro:",
  "Diameter: from {da} to {a} mm.": "Diámetro: de {da} a {a} mm.",
  "Diameter: {diff} mm difference.": "Diámetro: {diff} mm de diferencia.",
  "Don't know": "No lo sé",
  "Downloading the UV index…": "Descargando el índice UV…",
  "Drag a photo here or click to choose one": "Arrastra aquí una foto o haz clic para elegirla",
  "Drag the dot on the map to correct the position; zoom in with the wheel for maximum precision.": "Arrastra el punto en el mapa para corregir la posición; amplía con la rueda para la máxima precisión.",
  "Drag the dot on the map to move it.": "Arrastra el punto en el mapa para moverlo.",
  "Ear, left": "Oreja izquierda",
  "Ear, right": "Oreja derecha",
  "Edit date/measurement": "Editar fecha/medida",
  "Edit photo": "Editar foto",
  "Edit the data in the Profile": "Modificar los datos en el Perfil",
  "Elbow, left": "Codo izquierdo",
  "Elbow, right": "Codo derecho",
  "Email for PubMed": "Correo electrónico para PubMed",
  "Email saved.": "Correo electrónico guardado.",
  "Enlarge": "Ampliar",
  "Error {codice}": "Error {codice}",
  "Especially in childhood and adolescence.": "Sobre todo en la infancia y la adolescencia.",
  "Estimate from the internet address": "Estimación desde la dirección de internet",
  "Estimated location": "Ubicación estimada",
  "Evolution": "Evolución",
  "Extra precautions: avoid the sun in the middle of the day, seek shade, cover your skin, SPF 30+. Unprotected skin burns quickly.": "Precauciones extra: evita el sol en las horas centrales, busca la sombra, cubre la piel, SPF 30+. La piel sin proteger se quema enseguida.",
  "Extreme": "Extremo",
  "Eye colour": "Color de los ojos",
  "Eyes": "Ojos",
  "FRONT": "FRENTE",
  "Face": "Cara",
  "Fair phototype (I–II)": "Fototipo claro (I-II)",
  "Fair skin. Burns easily, tans little.": "Piel clara. Se quema con facilidad, se broncea poco.",
  "Fair-olive skin. Sometimes burns, tans gradually.": "Piel clara-aceitunada. A veces se quema, se broncea gradualmente.",
  "Fajuyigbe D, Young AR. The impact of skin colour on human photobiological responses. Pigment Cell Melanoma Res 2016;29:607-18 (minimal erythema dose by phototype)": "Fajuyigbe D, Young AR. The impact of skin colour on human photobiological responses. Pigment Cell Melanoma Res 2016;29:607-18 (dosis mínima de eritema por fototipo)",
  "Family history": "Antecedentes familiares",
  "Fewer than 25": "Menos de 25",
  "Fill in the 'Family history' section of your Profile: without that data I cannot check the criteria.": "Completa la sección «Antecedentes familiares» del Perfil: sin esos datos no puedo comprobar los criterios.",
  "Fill in the family history in your Profile": "Completa los antecedentes familiares en el Perfil",
  "First-degree relative with melanoma": "Familiar de primer grado con melanoma",
  "Folder with your data (copy it for backup):": "Carpeta con tus datos (cópiala para la copia de seguridad):",
  "Foot, left": "Pie izquierdo",
  "Foot, right": "Pie derecho",
  "Forearm, left": "Antebrazo izquierdo",
  "Forearm, right": "Antebrazo derecho",
  "Forehead and scalp": "Frente y cuero cabelludo",
  "Freckles": "Pecas",
  "Freckles (ephelides)": "Pecas (efélides)",
  "Front": "Frente",
  "Full report (text)": "Informe completo (texto)",
  "Full report (text, in English)": "Informe completo (texto, en inglés)",
  "Gene": "Gen",
  "Gene not in the list.": "El gen no figura en la lista.",
  "Gene {n} of {tot} ({nome})…": "Gen {n} de {tot} ({nome})…",
  "Genetic test": "Prueba genética",
  "Genetic test already done": "Prueba genética ya realizada",
  "Genetics": "Genética",
  "Give the mole a name and check the site.": "Ponle un nombre al lunar y comprueba la zona.",
  "Go to the Genetics section": "Ir a la sección Genética",
  "Grandparents, aunts and uncles, nieces and nephews (2nd degree).": "Abuelos, tíos, sobrinos (2.º grado).",
  "Green": "Verdes",
  "Grey/white": "Canosos/blancos",
  "Groin, left": "Ingle izquierda",
  "Groin, right": "Ingle derecha",
  "Guideline": "Guía clínica",
  "Guidelines and criteria for genetic testing": "Guías y criterios para la prueba genética",
  "Guidelines recommend the test only after careful selection of candidates and adequate counselling (Rossi 2019); the use of multigene panels is still debated.": "Las guías recomiendan la prueba solo tras una selección cuidadosa de los candidatos y un asesoramiento adecuado (Rossi 2019); el uso de paneles multigénicos sigue siendo objeto de debate.",
  "Hair": "Cabello",
  "Hand, left": "Mano izquierda",
  "Hand, right": "Mano derecha",
  "Has a doctor told you that you have atypical (dysplastic) moles?": "¿Algún médico te ha dicho que tienes lunares atípicos (displásicos)?",
  "Have I already had a genetic test for melanoma?": "¿Me he hecho ya una prueba genética para el melanoma?",
  "Having had a melanoma raises the risk of a second one.": "Haber tenido un melanoma aumenta el riesgo de un segundo.",
  "Hereditary melanoma": "Melanoma hereditario",
  "Hereditary melanoma and genetic testing": "Melanoma hereditario y prueba genética",
  "High": "Alto",
  "High (BAP1 syndrome)": "Alto (síndrome BAP1)",
  "High (rare)": "Alto (raro)",
  "Hour-by-hour UV index for the next 24 hours": "Índice UV hora a hora para las próximas 24 horas",
  "Hourly data not available": "Datos por horas no disponibles",
  "How reliable are apps and artificial intelligence": "Qué tan fiables son las aplicaciones y la inteligencia artificial",
  "How to get the key": "Cómo obtener la clave",
  "How to read the UV index": "Cómo se lee el índice UV",
  "How to take comparable photos": "Cómo hacer fotos comparables",
  "I am immunosuppressed (transplant or therapies that lower the body's defences)": "Estoy inmunodeprimido/a (trasplante o tratamientos que reducen las defensas)",
  "I assume the 2 outputs are [benign, malignant]; order cannot be verified": "supongo que las 2 salidas son [benigno, maligno]; orden no verificable",
  "I cannot find melanoma_batch.py: it must be in the same folder as neotracker.py (or in {CARTELLA_REPO}).": "No encuentro melanoma_batch.py: debe estar en la misma carpeta que neotracker.py (o en {CARTELLA_REPO}).",
  "I cannot prepare the photo safely: {e}": "no puedo preparar la foto de forma segura: {e}",
  "I cannot reach NeoTracker. The program may have been closed: reopen it from the icon on the Desktop.": "No consigo contactar con NeoTracker. Puede que el programa se haya cerrado: vuelve a abrirlo desde el icono del Escritorio.",
  "I cannot read this image. Try a JPG or a PNG.": "No puedo leer esta imagen. Prueba con un JPG o un PNG.",
  "I cannot reduce this image.": "No puedo reducir esta imagen.",
  "I don't know: leave it empty, you can come back later.": "No lo sé: déjalo vacío, puedes volver más tarde.",
  "I have checked my family history (even if the answer is «none»)": "He comprobado mis antecedentes familiares (aunque la respuesta sea «ninguno»)",
  "I have had (or have) one of these cancers:": "He tenido (o tengo) uno de estos cánceres:",
  "I have had other skin cancers (basal cell or squamous cell carcinoma)": "He tenido otros cánceres de piel (carcinoma basocelular o espinocelular)",
  "I have read and understood these notices": "He leído y entendido estas advertencias",
  "I prefer not to say": "Prefiero no decirlo",
  "I work or do activities outdoors for many hours": "Trabajo o hago actividades al aire libre durante muchas horas",
  "If it is still analysing a photo, it finishes the analysis first and then shuts down. The button below does the same thing.": "Si todavía está analizando una foto, termina primero el análisis y luego se apaga. El botón de abajo hace lo mismo.",
  "If you are unsure about your phototype, think about how your skin reacts to the first intense sun exposure in summer, without protection.": "Si dudas sobre tu fototipo, piensa en cómo reacciona tu piel a la primera exposición intensa al sol en verano, sin protección.",
  "If you enter data or photos of other people, make sure you have their consent.": "Si introduces datos o fotos de otras personas, asegúrate de contar con su consentimiento.",
  "Immunosuppression (therapies, transplant)": "Inmunosupresión (tratamientos, trasplante)",
  "Important notices": "Advertencias",
  "In English": "En inglés",
  "In-focus photo, with the mole in the centre and the skin clearly visible (move hair aside if needed).": "Foto enfocada, con el lunar en el centro y la piel bien visible (aparta el vello si hace falta).",
  "Increase: {voce}": "Aumentar: {voce}",
  "Installation status": "Estado de la instalación",
  "Interface language": "Idioma de la interfaz",
  "Internal error. Details are in the neotracker.log file in the data folder.": "Error interno. Los detalles están en el archivo neotracker.log de la carpeta de datos.",
  "Invalid UV index source.": "Fuente del índice UV no válida.",
  "Invalid coordinates.": "Coordenadas no válidas.",
  "Invalid data (JSON).": "Datos no válidos (JSON).",
  "Invalid data.": "Datos no válidos.",
  "Invalid date of birth (YYYY-MM-DD).": "Fecha de nacimiento no válida (AAAA-MM-DD).",
  "Invalid date: use the format YYYY-MM-DD.": "Fecha no válida: usa el formato AAAA-MM-DD.",
  "Invalid email address.": "Correo electrónico no válido.",
  "Invalid location.": "Ubicación no válida.",
  "Invalid notice version.": "Versión de la advertencia no válida.",
  "Invalid page identifier.": "Identificador de página no válido.",
  "Invalid profile.": "Perfil no válido.",
  "Irregular, jagged or blurred.": "Irregulares, dentados o difuminados.",
  "It changes over time: shape, colour, size, elevation, or itching or bleeding appear.": "Cambia con el tiempo: forma, color, tamaño, relieve, o aparecen picor o sangrado.",
  "It is a personal tool for organising the photos of your moles and comparing over time the results of some research models. It is not certified or approved by any health authority.": "Es una herramienta personal para organizar las fotos de tus lunares y comparar a lo largo del tiempo los resultados de algunos modelos de investigación. No está certificada ni aprobada por ninguna autoridad sanitaria.",
  "It is normal for the methods to disagree: it only means that none of them is reliable on its own.": "Es normal que los métodos no coincidan: solo significa que ninguno es fiable por sí solo.",
  "It works: OpenWeather answers (current UV index: {uvi}).": "Funciona: OpenWeather responde (índice UV actual: {uvi}).",
  "Its only photo and the analysis reports will be deleted permanently.": "Su única foto y los informes de análisis se eliminarán para siempre.",
  "JPG, PNG, WEBP or BMP · up to 60 MB": "JPG, PNG, WEBP o BMP · hasta 60 MB",
  "Key removed.": "Clave eliminada.",
  "Key saved ({finale}) — type a new one to replace it": "Clave guardada ({finale}) — escribe una nueva para sustituirla",
  "Key saved.": "Clave guardada.",
  "Kidney carcinoma": "Carcinoma de riñón",
  "Knee, left": "Rodilla izquierda",
  "Knee, right": "Rodilla derecha",
  "L": "I",
  "Language": "Idioma",
  "Language not supported.": "Idioma no admitido.",
  "Large, irregular, multicoloured moles: they should be followed over time.": "Lunares grandes, irregulares y de varios colores: conviene seguirlos en el tiempo.",
  "Latest automatic analysis ({data}): {esito}. Research tool, not diagnostic.": "Último análisis automático ({data}): {esito}. Herramienta de investigación, no diagnóstica.",
  "Leachman 2009 and 2017; NCCN": "Leachman 2009 y 2017; NCCN",
  "Leachman 2017; NCCN": "Leachman 2017; NCCN",
  "Lentigo maligna and melanoma of the face": "Lentigo maligna y melanoma de la cara",
  "Light-coloured eyes": "Ojos claros",
  "List of factors known from the literature, not a validated score: it does not estimate the probability of falling ill.": "Lista de factores conocidos por la literatura, no una puntuación validada: no estima la probabilidad de enfermar.",
  "Literature": "Literatura",
  "Literature: PubMed": "Literatura: PubMed",
  "Loading…": "Cargando…",
  "Location": "Ubicación",
  "Location missing": "Falta la ubicación",
  "Location not set": "Ubicación no establecida",
  "Location not set: choose a city or use 'Detect my location'.": "Ubicación no establecida: elige una ciudad o usa «Detectar mi ubicación».",
  "Location outside the map.": "Ubicación fuera del mapa.",
  "Location saved: {nome}": "Ubicación guardada: {nome}",
  "Location set": "Ubicación establecida",
  "Location updated.": "Ubicación actualizada.",
  "Location updated: {regione}.": "Ubicación actualizada: {regione}.",
  "Low": "Bajo",
  "Low to moderate (common)": "Bajo a moderado (frecuente)",
  "Lower abdomen, left": "Abdomen inferior izquierdo",
  "Lower abdomen, right": "Abdomen inferior derecho",
  "Lower back, left": "Región lumbar izquierda",
  "Lower back, right": "Región lumbar derecha",
  "Lower leg (shin), left": "Pierna (espinilla) izquierda",
  "Lower leg (shin), right": "Pierna (espinilla) derecha",
  "Lucas RM et al. Are current guidelines for sun protection optimal for health? Photochem Photobiol Sci 2018;17:1956-63 (UV Index and erythemal dose)": "Lucas RM et al. Are current guidelines for sun protection optimal for health? Photochem Photobiol Sci 2018;17:1956-63 (índice UV y dosis de eritema)",
  "Main high-penetrance predisposition gene. Germline variants in 20–40% of families with melanoma; also associated with pancreatic cancer, multiple melanomas and early onset.": "Principal gen de predisposición de alta penetrancia. Variantes germinales en el 20-40 % de las familias con melanoma; también asociado a cáncer de páncreas, melanomas múltiples y aparición temprana.",
  "Man": "Hombre",
  "Many": "Muchas",
  "Many freckles (ephelides)": "Muchas pecas (efélides)",
  "Many moles or atypical moles: surveillance": "Muchos lunares o lunares atípicos: vigilancia",
  "Many sunburns with blisters": "Muchas quemaduras solares con ampollas",
  "Map of the human body: front on the left, back on the right": "Mapa del cuerpo humano: frente a la izquierda, espalda a la derecha",
  "Measured diameter (mm)": "Diámetro medido (mm)",
  "Melanoma already diagnosed": "Melanoma ya diagnosticado",
  "Melanoma and immunosuppression": "Melanoma e inmunosupresión",
  "Melanoma in dark skin (often acral)": "Melanoma en pieles oscuras (a menudo acral)",
  "Melanoma of the eye (uveal)": "Melanoma del ojo (uveal)",
  "Melanoma-Detector (VukIG)": "Melanoma-Detector (VukIG)",
  "Melanomas already diagnosed": "Melanomas ya diagnosticados",
  "Melanomas already diagnosed in me": "Melanomas ya diagnosticados en mí",
  "Mesothelioma": "Mesotelioma",
  "Met": "Cumplido",
  "Meta-analysis": "Metaanálisis",
  "Method 1 - App 1 (Deborah Adedigba)": "Método 1 - App 1 (Deborah Adedigba)",
  "Method 1 turned off in the settings.": "Método 1 desactivado en los ajustes.",
  "Method 2 - SkinSense (online service)": "Método 2 - SkinSense (servicio en línea)",
  "Method 2 not run (turned off in the settings): the photo did not leave the PC.": "Método 2 no ejecutado (desactivado en los ajustes): la foto no ha salido del PC.",
  "Method 3 did NOT analyse the photo: the project is a prototype without a model. Its server merely receives the image (no neural network), so any reassuring text it shows does not come from an analysis and has no value.": "El método 3 NO ha analizado la foto: el proyecto es un prototipo sin modelo. Su servidor se limita a recibir la imagen (sin red neuronal), así que cualquier texto tranquilizador que muestre no procede de un análisis y no tiene ningún valor.",
  "Method 4 - vatsal30": "Método 4 - vatsal30",
  "Method 4 turned off in the settings.": "Método 4 desactivado en los ajustes.",
  "Method 5 is an Android app: it cannot run on the PC. Install the APK on the phone, frame the mole and note the result by hand below.\nApp result on the phone: ______________________________": "El método 5 es una aplicación de Android: no puede funcionar en el PC. Instala el APK en el teléfono, enfoca el lunar y anota a mano el resultado más abajo.\nResultado de la aplicación en el teléfono: ______________________________",
  "Method {n}": "Método {n}",
  "Method {n} said:": "El método {n} indicó:",
  "Methods disagree": "Métodos en desacuerdo",
  "Moderate": "Moderado",
  "Moderate UV: protection needed in the middle of the day": "UV moderados: hace falta protección en las horas centrales",
  "Mole archived. You will find it at the bottom of the list.": "Lunar archivado. Lo encontrarás al final de la lista.",
  "Mole deleted.": "Lunar eliminado.",
  "Mole diameter over time": "Diámetro del lunar a lo largo del tiempo",
  "Mole map": "Mapa de lunares",
  "Mole name": "Nombre del lunar",
  "Mole not found.": "Lunar no encontrado.",
  "Mole saved. Now add the first photo: it will be your \"baseline photo\".": "Lunar guardado. Ahora añade la primera foto: será tu «foto de referencia».",
  "Mole sheet – {nome}": "Ficha de lunares – {nome}",
  "Mole with photos": "Lunar con fotos",
  "Mole {n}": "Lunar {n}",
  "More than 6 mm (but smaller melanomas exist).": "Más de 6 mm (aunque existen melanomas más pequeños).",
  "Most recent studies on predisposition genes": "Estudios más recientes sobre los genes de predisposición",
  "Most relevant studies": "Estudios más pertinentes",
  "Move the pointer over the body to see the area": "Pasa el puntero sobre el cuerpo para ver la zona",
  "Multiple BAP1-spectrum tumours (uveal melanoma, mesothelioma, renal carcinoma, cutaneous melanoma)": "Varios tumores del espectro BAP1 (melanoma uveal, mesotelioma, carcinoma renal, melanoma cutáneo)",
  "My location ({lat}; {lon})": "Mi ubicación ({lat}; {lon})",
  "NCCN": "NCCN",
  "NCCN Clinical Practice Guidelines in Oncology: Melanoma: Cutaneous (current version; the full text requires free registration)": "NCCN Clinical Practice Guidelines in Oncology: Melanoma: Cutaneous (versión actual; el texto completo requiere registro gratuito)",
  "Name": "Nombre",
  "Name or nickname": "Nombre o apodo",
  "Nape and neck": "Nuca y cuello",
  "Natural hair colour (when young)": "Color natural del cabello (de joven)",
  "Neck": "Cuello",
  "Needs attention": "Requiere atención",
  "NeoTracker closed": "NeoTracker cerrado",
  "NeoTracker is closed": "NeoTracker está cerrado",
  "NeoTracker is not a genetic counselling service. For a personal assessment, see your dermatologist or an oncological genetics centre.": "NeoTracker no es un servicio de asesoramiento genético. Para una valoración personal, acude a tu dermatólogo o a un centro de genética oncológica.",
  "NeoTracker is not a medical device and does not make diagnoses.": "NeoTracker no es un producto sanitario y no hace diagnósticos.",
  "NeoTracker is not a medical tool and does not make diagnoses. For any mole that changes, bleeds, itches or worries you, see a dermatologist.": "NeoTracker no es una herramienta médica y no hace diagnósticos. Ante cualquier lunar que cambie, sangre, pique o te preocupe, acude a un dermatólogo.",
  "NeoTracker is not responding": "NeoTracker no responde",
  "Never": "Nunca",
  "New mole": "Lunar nuevo",
  "New user": "Nuevo usuario",
  "Next {n} hours": "Próximas {n} horas",
  "No": "No",
  "No alarm from the models": "Ninguna alarma de los modelos",
  "No articles found.": "No se han encontrado artículos.",
  "No city found with this name.": "No se ha encontrado ninguna ciudad con ese nombre.",
  "No image set.": "No hay ninguna imagen establecida.",
  "No method produced a result: check the reasons listed below.": "Ningún método ha producido un resultado: revisa los motivos indicados abajo.",
  "No moles yet": "Todavía no hay lunares",
  "No photo recorded yet.": "Todavía no hay ninguna foto registrada.",
  "No photos yet": "Todavía no hay fotos",
  "No photos: add the first one": "Sin fotos: añade la primera",
  "No result": "Sin resultado",
  "No special protection needed for normal activities; sunglasses on bright days.": "No hace falta protección especial para las actividades normales; gafas de sol los días luminosos.",
  "None": "Ninguna",
  "None of the methods that responded flags the lesion as suspicious. This does NOT rule out a melanoma: the tools are not clinically validated and are also wrong in this direction. If the mole is asymmetric, has irregular borders, several colours, is larger than 6 mm or has changed over time, a visit is still needed.": "Ninguno de los métodos que han respondido señala la lesión como sospechosa. Esto NO descarta un melanoma: las herramientas no están validadas clínicamente y también se equivocan en este sentido. Si el lunar es asimétrico, tiene bordes irregulares, varios colores, mide más de 6 mm o ha cambiado con el tiempo, la visita sigue siendo necesaria.",
  "Normal photo": "Foto normal",
  "Normal photo (smartphone)": "Foto normal (smartphone)",
  "Not allowed.": "No permitido.",
  "Not met": "No cumplido",
  "Not scanned yet": "Aún sin explorar",
  "Not scanned yet.": "Aún sin explorar.",
  "Not specified": "No indicado",
  "Notes": "Notas",
  "Notes on the mole…": "Notas sobre el lunar…",
  "Notes:": "Notas:",
  "Nothing is sent online, except the requests you turn on (UV weather, PubMed literature, SkinSense).": "No se envía nada por internet, salvo las solicitudes que activas tú (meteorología UV, literatura de PubMed, SkinSense).",
  "Now": "Ahora",
  "Number of moles": "Número de lunares",
  "Observational study": "Estudio observacional",
  "Of any degree of kinship.": "De cualquier grado de parentesco.",
  "Off by default: with the other methods the photo never leaves this computer.": "Desactivado por defecto: con los demás métodos la foto nunca sale de este ordenador.",
  "Often": "A menudo",
  "Olive skin. Burns little, tans easily.": "Piel aceitunada. Se quema poco, se broncea con facilidad.",
  "One Call {n}: {t}": "One Call {n}: {t}",
  "Only invasive primary melanomas count.": "Solo cuentan los melanomas primarios invasivos.",
  "Open the «API keys» page of your account and copy the key.": "Abre la página «API keys» de tu cuenta y copia la clave.",
  "Open-Meteo (default)": "Open-Meteo (predeterminada)",
  "OpenWeather key": "Clave de OpenWeather",
  "OpenWeather key saved ({finale}).": "Clave de OpenWeather guardada ({finale}).",
  "OpenWeather rejected the key (401): check that it is correct and that the 'One Call API' plan (pay per call, 1,000 free calls per day) is active on your account. After subscribing, the key can take a few minutes to activate.": "OpenWeather ha rechazado la clave (401): comprueba que sea correcta y que en tu cuenta esté activa la suscripción «One Call API» (pago por llamada, 1.000 llamadas gratuitas al día). Tras suscribirte, la clave puede tardar unos minutos en activarse.",
  "OpenWeather unavailable ({e}). Showing Open-Meteo data.": "OpenWeather no disponible ({e}). Muestro los datos de Open-Meteo.",
  "OpenWeather: call limit reached (429).": "OpenWeather: límite de llamadas alcanzado (429).",
  "Operation not allowed on this address.": "Operación no permitida en esta dirección.",
  "Optional": "Opcional",
  "Origin not allowed.": "Origen no permitido.",
  "Original photo": "Foto original",
  "Other": "Otro",
  "Other relatives with melanoma": "Otros familiares con melanoma",
  "Other skin cancers (basal cell and squamous cell carcinoma)": "Otros cánceres de piel (carcinoma basocelular y espinocelular)",
  "Overlay with slider": "Superponer con control deslizante",
  "Page not found.": "Página no encontrada.",
  "Pancreatic cancer": "Cáncer de páncreas",
  "Parents, brothers, sisters, children.": "Padres, hermanos, hermanas, hijos.",
  "Parents, siblings or children.": "Padres, hermanos o hijos.",
  "Paste the key above and press «Test the key». After subscribing, the key can take a few minutes to activate. The program tries One Call 4.0 first and, if the key belongs to an older plan, One Call 3.0.": "Pega la clave arriba y pulsa «Probar la clave». Tras suscribirte, la clave puede tardar unos minutos en activarse. El programa prueba primero One Call 4.0 y, si la clave es de una suscripción más antigua, One Call 3.0.",
  "Paste the key first.": "Pega primero la clave.",
  "Paste the key here (32 letters and digits)": "Pega aquí la clave (32 letras y números)",
  "People with many moles, atypical moles or a history of melanoma should protect themselves even when the index is moderate.": "Quien tiene muchos lunares, lunares atípicos o antecedentes de melanoma debe protegerse incluso con índices moderados.",
  "Permission denied. You can search for the city by name or use the estimate from the internet address.": "Permiso denegado. Puedes buscar la ciudad por su nombre o usar la estimación desde la dirección de internet.",
  "Personal data": "Datos personales",
  "Personal details": "Datos de la persona",
  "Personal history": "Antecedentes personales",
  "Personal melanoma and a first-degree relative with pancreatic cancer": "Melanoma propio y familiar de primer grado con cáncer de páncreas",
  "Personal picture": "Imagen personal",
  "Personal picture saved.": "Imagen personal guardada.",
  "Phenotype: skin, hair, eyes": "Fenotipo: piel, cabello, ojos",
  "Photo analysis": "Análisis de las fotos",
  "Photo date is too old.": "La fecha de la foto es demasiado antigua.",
  "Photo deleted.": "Foto eliminada.",
  "Photo file not found.": "No se encuentra el archivo de la foto.",
  "Photo from {data}": "Foto del {data}",
  "Photo history": "Historial fotográfico",
  "Photo history ({n})": "Historial fotográfico ({n})",
  "Photo not found.": "Foto no encontrada.",
  "Photo saved ({data}).": "Foto guardada ({data}).",
  "Photo saved ({data}, date read from the photo).": "Foto guardada ({data}, fecha leída de la foto).",
  "Photo type": "Tipo de foto",
  "Phototype": "Fototipo",
  "Phototype (Fitzpatrick classification)": "Fototipo (clasificación de Fitzpatrick)",
  "Phototype, age and family history do not change the neural networks' result (they only look at pixels): they serve to put the risk in context.": "El fototipo, la edad y los antecedentes familiares no cambian el resultado de las redes neuronales (solo miran los píxeles): sirven para contextualizar el riesgo.",
  "Picked for you (based on profile and mole locations)": "Elegidos para ti (según el perfil y la ubicación de los lunares)",
  "Picture removed.": "Imagen eliminada.",
  "Pillow is not installed: previews will use the original photos (install with «py -m pip install pillow»).": "Pillow no está instalado: las vistas previas usarán las fotos originales (instálalo con «py -m pip install pillow»).",
  "Place a ruler or a coin next to the mole: it is used to measure the diameter.": "Coloca una regla o una moneda junto al lunar: sirve para medir el diámetro.",
  "Preparing the sheet…": "Preparando la ficha…",
  "Press": "Pulsa",
  "Preview": "Vista previa",
  "Primary melanomas indicated: {mel_pers}.": "Melanomas primarios indicados: {mel_pers}.",
  "Print a sheet with all the moles": "Imprimir una ficha con todos los lunares",
  "Print the sheet for this mole": "Imprimir la ficha de este lunar",
  "Printed on {data} with NeoTracker": "Impreso el {data} con NeoTracker",
  "Profile": "Perfil",
  "Profile not filled in.": "Perfil sin completar.",
  "Profile of {nome}": "Perfil de {nome}",
  "Profile to complete": "Perfil por completar",
  "Projects folder:": "Carpeta de los proyectos:",
  "Protection necessary: reduce exposure between 10 and 16, SPF 30+ sunscreen, hat and sunglasses.": "Protección necesaria: reduce la exposición entre las 10 y las 16, crema solar SPF 30+, gorro y gafas.",
  "Protection not needed for normal activities (beware of snow, water, altitude).": "No hace falta protección para las actividades normales (ojo con la nieve, el agua y la altitud).",
  "Protection recommended: shade in the middle of the day, hat, sunglasses and sunscreen.": "Protección recomendada: sombra en las horas centrales, gorro, gafas y crema solar.",
  "PubMed is a service of the National Library of Medicine. Abstracts are shown for personal consultation, in English; for the full text, open the article on the journal's website.": "PubMed es un servicio de la National Library of Medicine. Los resúmenes se muestran para consulta personal, en inglés; para el texto completo, abre el artículo en el sitio de la revista.",
  "PubMed is unreachable: showing the last saved search from {data}.": "PubMed no está accesible: muestro la última búsqueda guardada el {data}.",
  "PubMed responded with error {code}": "PubMed respondió con el error {code}",
  "PubMed unreachable (check the internet connection)": "PubMed no accesible (comprueba la conexión a internet)",
  "PubMed {pmid} · abstract not available": "PubMed {pmid} · resumen no disponible",
  "Queued (position {n})…": "En cola (posición {n})…",
  "Queued…": "En cola…",
  "Quit the program": "Salir del programa",
  "R": "D",
  "R = patient's right · L = left": "D = derecha del paciente · I = izquierda",
  "Randomised trial": "Estudio aleatorizado",
  "Rare": "Raro",
  "Rare variants concentrated in codon 24: the family picture is indistinguishable from that of CDKN2A.": "Variantes raras concentradas en el codón 24: el cuadro familiar es indistinguible del de CDKN2A.",
  "Re-analyse": "Volver a analizar",
  "Read the abstract": "Leer el resumen",
  "Recent, relevant articles on recognising suspicious moles, on the reliability of apps and artificial intelligence, and on hereditary melanoma. Results come from PubMed, the public database of the National Library of Medicine (USA).": "Artículos recientes y relevantes sobre cómo reconocer lunares sospechosos, la fiabilidad de las aplicaciones y la inteligencia artificial, y el melanoma hereditario. Los resultados proceden de PubMed, la base de datos pública de la National Library of Medicine (EE. UU.).",
  "Recognising a suspicious mole": "Reconocer un lunar sospechoso",
  "Red": "Pelirrojos",
  "Red or blond hair": "Cabello pelirrojo o rubio",
  "Refresh": "Actualizar",
  "Relatives with astrocytoma (brain tumour)": "Familiares con astrocitoma (tumor cerebral)",
  "Relatives with kidney carcinoma": "Familiares con carcinoma de riñón",
  "Relatives with melanoma of the eye (uveal)": "Familiares con melanoma del ojo (uveal)",
  "Relatives with mesothelioma": "Familiares con mesotelioma",
  "Relatives with pancreatic cancer (in total)": "Familiares con cáncer de páncreas (en total)",
  "Remove": "Quitar",
  "Remove the key?": "¿Eliminar la clave?",
  "Rename": "Renombrar",
  "Rename user": "Renombrar usuario",
  "Repeat the search ignoring the saved results": "Repetir la búsqueda ignorando los resultados guardados",
  "Request too large.": "Solicitud demasiado grande.",
  "Restore": "Restaurar",
  "Review": "Revisión",
  "Reviews on familial melanoma (CDKN2A, CDK4)": "Revisiones sobre el melanoma familiar (CDKN2A, CDK4)",
  "Risk factors indicated:": "Factores de riesgo indicados:",
  "Risk factors present": "Factores de riesgo presentes",
  "Role and literature": "Función y literatura",
  "Roughly how many moles do you have on your body?": "¿Aproximadamente cuántos lunares tienes en el cuerpo?",
  "Same light (daylight, no flash) and same distance every time, about 10–15 cm.": "La misma luz (luz del día, sin flash) y la misma distancia cada vez, unos 10-15 cm.",
  "Save": "Guardar",
  "Save an OpenWeather key first.": "Guarda primero una clave de OpenWeather.",
  "Save mole": "Guardar lunar",
  "Save photo": "Guardar foto",
  "Saved ✓": "Guardado ✓",
  "Saving…": "Guardando…",
  "Scalp (head)": "Cuero cabelludo (cabeza)",
  "Scan complete.": "Exploración completada.",
  "Scan the literature": "Explorar la literatura",
  "Scan the literature on genes": "Explorar la literatura sobre los genes",
  "Scientific literature": "Literatura científica",
  "Search": "Buscar",
  "Search for a city (e.g. Turin)": "Busca una ciudad (p. ej. Turín)",
  "Search for more (e.g. \"ugly duckling sign\", \"nail melanoma\"…)": "Buscar otra cosa (p. ej. \"ugly duckling sign\", \"nail melanoma\"…)",
  "Search the literature": "Buscar en la literatura",
  "Searches go from this computer to PubMed (no personal data is sent). Results are saved for 7 days.": "Las búsquedas salen de este ordenador hacia PubMed (no se envían datos personales). Los resultados se guardan durante 7 días.",
  "Searches use PubMed's public E-utilities. NCBI asks, as a courtesy, for a contact email: it is optional and is sent only to PubMed.": "Las búsquedas usan las E-utilities públicas de PubMed. El NCBI pide, por cortesía, un correo de contacto: es opcional y solo se envía a PubMed.",
  "Searching PubMed…": "Buscando en PubMed…",
  "Searching…": "Buscando…",
  "Section {n} of {tot}…": "Sección {n} de {tot}…",
  "Sections": "Secciones",
  "Send the photos to SkinSense?": "¿Enviar las fotos a SkinSense?",
  "Sequential photography and monitoring of moles over time": "Fotografía secuencial y seguimiento de los lunares a lo largo del tiempo",
  "Settings": "Ajustes",
  "Several colours in the same mole (brown, black, red, blue, white).": "Varios colores en el mismo lunar (marrón, negro, rojo, azul, blanco).",
  "Sex": "Sexo",
  "Shade, clothing, a hat and sunscreen are needed in the middle of the day.": "Hacen falta sombra, ropa, gorro y crema solar en las horas centrales.",
  "Sheet for the dermatologist": "Ficha para el dermatólogo",
  "Shoulder blade area, left": "Región escapular izquierda",
  "Shoulder blade area, right": "Región escapular derecha",
  "Shoulder, left": "Hombro izquierdo",
  "Shoulder, right": "Hombro derecho",
  "Show side by side": "Mostrar una al lado de la otra",
  "Show the whole body": "Mostrar todo el cuerpo",
  "Showing {n} photos out of {tot}.": "Se muestran {n} fotos de {tot}.",
  "Significant risk factors are present: periodic dermatological check-ups (the dermatologist decides how often) and regular skin self-examination are recommended.": "Hay factores de riesgo relevantes: se aconseja una revisión dermatológica periódica (la frecuencia la decide el dermatólogo) y la autoexploración regular de la piel.",
  "Simplified criteria, for information only. Genetic testing concerns a small minority of people and is not a routine examination: it is up to the specialist to decide whether and which test to offer, usually after genetic counselling and, when possible, starting from a relative who has had the disease.": "Criterios simplificados, solo a título informativo. La prueba genética afecta a una pequeña minoría de personas y no es un examen rutinario: corresponde al especialista decidir si se propone y qué prueba, normalmente tras un asesoramiento genético y, cuando es posible, partiendo de un familiar que haya tenido la enfermedad.",
  "Site": "Zona",
  "Site (editable)": "Zona (editable)",
  "Skin self-examination": "Autoexploración de la piel",
  "Skin that burns easily and tans little.": "Piel que se quema con facilidad y se broncea poco.",
  "SkinSense (online service)": "SkinSense (servicio en línea)",
  "SkinSense is a third-party online service: the photos of your moles would be sent over the internet to a server we do not control. The photos are data about your health. Do you want to enable it?": "SkinSense es un servicio en línea de terceros: las fotos de tus lunares se enviarían por internet a un servidor que no controlamos. Las fotos son datos sobre tu salud. ¿Quieres activarlo?",
  "SkinSense is on: the photo (without metadata) will be sent to an online service.": "SkinSense está activo: la foto (sin metadatos) se enviará a un servicio en línea.",
  "SkinSense turned off.": "SkinSense desactivado.",
  "SkinSense turned on.": "SkinSense activado.",
  "Smartphone apps and skin cancer risk: diagnostic accuracy": "Aplicaciones para smartphone y riesgo de cáncer de piel: precisión diagnóstica",
  "Some risk factors are present: careful sun protection and regular self-examination; a basic dermatological check-up is a good habit.": "Hay algunos factores de riesgo: protección solar cuidadosa y autoexploración regular; una revisión dermatológica básica es un buen hábito.",
  "Something went wrong": "Algo ha salido mal",
  "Sometimes": "A veces",
  "Source:": "Fuente:",
  "Sources": "Fuentes",
  "Subscribe to the pay-per-call «One Call API» plan": "Suscríbete al plan «One Call API» de pago por llamada",
  "Sun exposure": "Exposición al sol",
  "Sunbeds": "Cabinas de bronceado",
  "Sunburns": "Quemaduras solares",
  "Sunburns with blisters (especially as a child or teenager)": "Quemaduras solares con ampollas (sobre todo de niño o adolescente)",
  "Switch user": "Cambiar de usuario",
  "Syndromic": "Sindrómico",
  "Systematic review": "Revisión sistemática",
  "Tanning lamps": "Lámparas de bronceado",
  "Tanning lamps or sunbeds": "Lámparas o camas solares de bronceado",
  "Telomerase: promoter variants described in families with melanoma.": "Telomerasa: variantes del promotor descritas en familias con melanoma.",
  "Telomere gene (shelterin complex): rare variants in families with melanoma.": "Gen de los telómeros (complejo shelterina): variantes raras en familias con melanoma.",
  "Telomere gene: rare variants in some families with melanoma.": "Gen de los telómeros: variantes raras en algunas familias con melanoma.",
  "Test the key": "Probar la clave",
  "Testing the key…": "Probando la clave…",
  "The Open-Meteo service is not responding ({e}).": "El servicio Open-Meteo no responde ({e}).",
  "The OpenWeather key contains invalid characters (it is usually 32 letters/digits).": "La clave de OpenWeather contiene caracteres no válidos (normalmente son 32 letras/números).",
  "The Pillow library is old and has known security problems: update it with «py -m pip install -U pillow».": "La biblioteca Pillow es antigua y tiene problemas de seguridad conocidos: actualízala con «py -m pip install -U pillow».",
  "The WHO recommends protection from a UV index of 3.": "La OMS recomienda protegerse a partir de un índice UV de 3.",
  "The analysis did not produce the report. Last lines of the log: {log}": "El análisis no generó el informe. Últimas líneas del registro: {log}",
  "The analysis failed.": "El análisis no se completó.",
  "The articles are chosen by an automatic search and have not been assessed by NeoTracker: read them with your doctor.": "Los artículos se eligen mediante una búsqueda automática y NeoTracker no los ha evaluado: léelos con tu médico.",
  "The choice applies to all users of this computer. The original and binding text of the legal notices is the English one; the full text report stays in English.": "La elección vale para todos los usuarios de este ordenador. El texto original y vinculante de las advertencias legales es el inglés; el informe de texto completo se mantiene en inglés.",
  "The computer cannot determine the position. Search for the city by name.": "El ordenador no consigue determinar la posición. Busca la ciudad por su nombre.",
  "The data entered meet at least one criterion described in the literature. We advise you to talk about it with your dermatologist or a medical geneticist (oncological genetic counselling): the specialist will decide whether and which test to offer, usually after counselling and, when possible, starting from an affected relative. Genes most cited by the guidelines: {geni}. The use of multigene panels is still under discussion among specialists: that is why counselling before the test matters.": "Los datos introducidos cumplen al menos un criterio descrito en la literatura. Te aconsejamos hablarlo con tu dermatólogo o con un médico genetista (asesoramiento genético oncológico): será el especialista quien decida si se propone una prueba y cuál, normalmente tras el asesoramiento y, cuando sea posible, partiendo de un familiar afectado. Genes más citados por las guías: {geni}. El uso de paneles multigénicos sigue siendo objeto de debate entre los especialistas: por eso es importante el asesoramiento antes de la prueba.",
  "The file is empty.": "El archivo está vacío.",
  "The file is not a readable image or is too large.": "El archivo no es una imagen legible o es demasiado grande.",
  "The file is not a readable image, is damaged or has too many pixels (maximum {mp} megapixels).": "El archivo no es una imagen legible, está dañado o tiene demasiados píxeles (máximo {mp} megapíxeles).",
  "The file is too large (maximum 40 MB).": "El archivo es demasiado grande (máximo 40 MB).",
  "The first analysis can take several minutes (the models are loaded into memory).": "El primer análisis puede tardar varios minutos (los modelos se cargan en la memoria).",
  "The image exceeds {mb} MB.": "La imagen supera los {mb} MB.",
  "The index is a forecast: the actual value depends on clouds, altitude and reflections.": "El índice es una previsión: el valor real depende de las nubes, la altitud y los reflejos.",
  "The information on risk, literature and genetics is for general information and does not replace the advice of a doctor or geneticist.": "La información sobre riesgo, literatura y genética es divulgativa y no sustituye el asesoramiento de un médico o de un genetista.",
  "The key stays saved only on your computer and is never shown to, or sent to, the program's web page: the Python program uses it to call OpenWeather.": "La clave se guarda solo en tu ordenador y nunca se muestra ni se envía a la página web del programa: la usa el programa Python para llamar a OpenWeather.",
  "The key will be deleted from this computer. You can enter it again whenever you want.": "La clave se borrará de este ordenador. Podrás introducirla de nuevo cuando quieras.",
  "The location is saved only on this computer; it is sent to the weather service (rounded coordinates) to get the UV index.": "La ubicación se guarda solo en este ordenador; se envía al servicio meteorológico (coordenadas redondeadas) para obtener el índice UV.",
  "The methods are trained on photographs different from yours: changing light, distance or camera can change the answer.": "Los métodos están entrenados con fotografías distintas de las tuyas: cambiar la luz, la distancia o la cámara puede cambiar la respuesta.",
  "The middle hours of the day (about 11–16) have the highest index.": "Las horas centrales (aproximadamente de 11 a 16) son las de índice más alto.",
  "The most studied genes": "Los genes más estudiados",
  "The name": "El nombre",
  "The number of moles is one of the strongest risk factors.": "El número de lunares es uno de los factores de riesgo más fuertes.",
  "The numbers match the following sheets. In the figure: the front view on the left, the back view on the right.": "Los números corresponden a las fichas siguientes. En la figura: a la izquierda la vista frontal, a la derecha la posterior.",
  "The p.E318K variant increases the risk of melanoma and renal carcinoma and is associated with many moles.": "La variante p.E318K aumenta el riesgo de melanoma y de carcinoma renal y se asocia a muchos lunares.",
  "The photo date cannot be in the future.": "La fecha de la foto no puede ser futura.",
  "The photo exceeds {MAX_MB_FOTO} MB.": "La foto supera los {MAX_MB_FOTO} MB.",
  "The photo exceeds {mb} MB: reduce it or choose another one.": "La foto supera los {mb} MB: redúcela o elige otra.",
  "The photo from {data} and its analysis report will be deleted permanently.": "La foto del {data} y su informe de análisis se eliminarán para siempre.",
  "The photo stays on your computer: SkinSense (online service) is turned off.": "La foto permanece en tu ordenador: SkinSense (servicio en línea) está desactivado.",
  "The profile, all moles, all photos and all reports of this user will be deleted permanently. This cannot be undone.": "El perfil, todos los lunares, todas las fotos y todos los informes de este usuario se eliminarán para siempre. La operación no se puede deshacer.",
  "The program will shut down. An analysis in progress will be interrupted. Your data stays saved.": "El programa se apaga. Un análisis en curso se interrumpe. Los datos quedan guardados.",
  "The result also concerns blood relatives: that is why counselling before and after the test is part of the process.": "El resultado afecta también a los familiares de sangre: por eso el asesoramiento antes y después de la prueba forma parte del proceso.",
  "The results are experimental estimates and can be wrong in both directions: a reassuring result does not rule out a melanoma, and a result flagging attention does not mean there is one.": "Los resultados son estimaciones experimentales y pueden equivocarse en ambos sentidos: un resultado tranquilizador no descarta un melanoma y un resultado de atención no significa que lo haya.",
  "The two halves of the mole do not look alike.": "Las dos mitades del lunar no se parecen.",
  "The view must be 'fronte' or 'retro'.": "La vista debe ser 'fronte' o 'retro'.",
  "The «picked for you» sections use words linked to your profile (for example phototype or number of moles): if you prefer not to send them, do not scan that section.": "Las secciones «elegidas para ti» usan palabras ligadas a tu perfil (por ejemplo el fototipo o el número de lunares): si prefieres no enviarlas, no explores esa sección.",
  "The «ugly duckling» also counts: a mole that looks different from all the others. Nodules that grow quickly or feel hard to the touch should be shown straight away. This reminder does not replace a medical visit.": "También cuenta el «patito feo»: un lunar distinto de todos los demás. Los nódulos que crecen rápidamente o son duros al tacto deben mostrarse de inmediato. Este recordatorio no sustituye la visita médica.",
  "There are no moles to print.": "No hay lunares que imprimir.",
  "These are measurements you entered: they are valid if always taken the same way. A mole that grows or changes is a good reason to show it to your dermatologist; the 6 mm line is just the classic reference of the ABCDE criteria.": "Son medidas introducidas por ti: valen si se toman siempre del mismo modo. Un lunar que crece o cambia es un buen motivo para enseñárselo al dermatólogo; la línea de 6 mm es solo la referencia clásica de los criterios ABCDE.",
  "They do not change the result of the neural networks, which only look at the pixels of the photo. They are used to: (1) put the risk in context, (2) choose the scientific literature suited to you, (3) check the criteria for genetic counselling, (4) calculate how long you can stay in the sun before burning. Everything stays on your computer.": "No cambian el resultado de las redes neuronales, que solo miran los píxeles de la foto. Sirven para: (1) dar un contexto al riesgo, (2) elegir la literatura científica adecuada para ti, (3) comprobar los criterios del asesoramiento genético, (4) calcular cuánto tiempo puedes estar al sol antes de quemarte. Todo permanece en tu ordenador.",
  "Thigh, left": "Muslo izquierdo",
  "Thigh, right": "Muslo derecho",
  "Thin clouds do not stop much of the UV: the index can stay high even with a hazy sky.": "Las nubes finas no detienen gran parte de los UV: el índice puede seguir alto incluso con el cielo velado.",
  "This browser does not offer geolocation: search for the city by name.": "Este navegador no ofrece geolocalización: busca la ciudad por su nombre.",
  "This is a cautious estimate that uses the lowest minimal erythema dose for your phototype; with reflections (water, snow, sand), altitude or already reddened skin the time is shorter.": "Es una estimación prudente que usa la dosis mínima de eritema más baja de tu fototipo; con reflejos (agua, nieve, arena), altitud o piel ya enrojecida el tiempo se acorta.",
  "This method sends the pixels of the photo (not the metadata) to an external server.": "Este método envía los píxeles de la foto (no los metadatos) a un servidor externo.",
  "This photo has not been analysed yet. The analysis compares several methods on the same image and tells you what each one answered.": "Esta foto aún no se ha analizado. El análisis compara varios métodos sobre la misma imagen y te dice qué respondió cada uno.",
  "This photo is being analysed: wait for it to finish.": "Se está analizando esta foto: espera a que termine.",
  "This program helps you keep track of your moles over time: you mark them on a body map, keep their photos with the date and have them analysed by several methods. Start by creating your user.": "Este programa te ayuda a seguir tus lunares a lo largo del tiempo: los marcas en un mapa del cuerpo, guardas sus fotos con la fecha y los haces analizar con varios métodos. Empieza creando tu usuario.",
  "This report is NOT a diagnosis. The programs used are research prototypes, not medical devices.": "Este informe NO es un diagnóstico. Los programas utilizados son prototipos de investigación, no productos sanitarios.",
  "This sheet collects data entered by the person and photos taken by them. The results of the automatic analysis are experimental, are not a diagnosis and do not replace a dermatological visit or dermoscopy.": "Esta ficha reúne datos introducidos por la persona y fotos tomadas por ella. Los resultados del análisis automático son experimentales, no son un diagnóstico y no sustituyen la visita al dermatólogo ni la dermatoscopia.",
  "Thresholds and colours of the WHO international scale. Sources:": "Umbrales y colores de la escala internacional de la OMS. Fuentes:",
  "Time to re-photograph?": "¿Hay que volver a fotografiar?",
  "To close NeoTracker, just close this window with the X at the top right: the program shuts down by itself.": "Para cerrar NeoTracker basta con cerrar esta ventana con la X de arriba a la derecha: el programa se apaga solo.",
  "To confirm, type:": "Para confirmar, escribe:",
  "To delete, type the exact name of the user in the confirmation.": "Para eliminar, escribe en la confirmación el nombre exacto del usuario.",
  "To estimate the city, the program contacts the free service ipwho.is, which sees your internet address. Accuracy is at city level (it is sometimes wrong). Proceed?": "Para estimar la ciudad, el programa contacta con el servicio gratuito ipwho.is, que ve tu dirección de internet. La precisión es la de la ciudad (a veces se equivoca). ¿Continúo?",
  "To see how much sun burns you, enter your phototype in the": "Para ver cuánto sol te quema, indica tu fototipo en el",
  "Today's UV index": "Índice UV de hoy",
  "Today's maximum": "Máximo de hoy",
  "Too many open connections.": "Demasiadas conexiones abiertas.",
  "Total diagnoses entered: {diagnosi}. Leachman 2009 counts melanoma and pancreatic cancer in 1st- and 2nd-degree relatives on the same side of the family; astrocytoma is included by the NCCN guidelines.": "Diagnósticos totales indicados: {diagnosi}. Leachman 2009 considera el melanoma y el cáncer de páncreas en familiares de 1.er y 2.º grado del mismo lado de la familia; las guías del NCCN incluyen el astrocitoma.",
  "Try again": "Reintentar",
  "Type": "Tipo",
  "Type a name.": "Escribe un nombre.",
  "Type at least 3 characters.": "Escribe al menos 3 caracteres.",
  "Type {n}": "Tipo {n}",
  "UV index": "Índice UV",
  "UV index not available": "Índice UV no disponible",
  "UV index source changed.": "Fuente del índice UV cambiada.",
  "UV index: data source": "Índice UV: fuente de los datos",
  "UV rays are harmful to unprotected skin today": "Hoy los rayos UV son dañinos para la piel sin proteger",
  "UV rays are low today": "Hoy los rayos UV son bajos",
  "UV rays are very harmful today": "Hoy los rayos UV son muy dañinos",
  "Ultraviolet rays are the main modifiable risk factor for melanoma. Here you can see how strong they are today where you are.": "Los rayos ultravioleta son el principal factor de riesgo modificable del melanoma. Aquí ves lo fuertes que son hoy donde te encuentras.",
  "Unauthorised access.": "Acceso no autorizado.",
  "Unauthorised request.": "Solicitud no autorizada.",
  "Unexpected error: {e}": "Error inesperado: {e}",
  "Unknown address.": "Dirección desconocida.",
  "Unknown section.": "Sección desconocida.",
  "Unsaved changes…": "Cambios sin guardar…",
  "Unsupported format: JPG, PNG, WEBP or BMP are required.": "Formato no admitido: se necesita JPG, PNG, WEBP o BMP.",
  "Unsupported format: JPG, PNG, WEBP or BMP are required. iPhone HEIC photos must be converted to JPG (camera settings: 'Most Compatible').": "Formato no admitido: se necesita JPG, PNG, WEBP o BMP. Las fotos HEIC del iPhone deben convertirse a JPG (ajustes de la cámara: «Más compatible»).",
  "Upper abdomen, left": "Abdomen superior izquierdo",
  "Upper abdomen, right": "Abdomen superior derecho",
  "Use of tanning lamps or sunbeds": "Uso de lámparas o camas solares de bronceado",
  "Use the date written in the photo, if there is one": "Usar la fecha guardada en la foto, si existe",
  "User created. Fill in the profile: it helps put the results in context.": "Usuario creado. Completa el perfil: sirve para contextualizar los resultados.",
  "User deleted.": "Usuario eliminado.",
  "User not found.": "Usuario no encontrado.",
  "Version": "Versión",
  "Very dark skin. Does not burn.": "Piel muy oscura. No se quema.",
  "Very fair skin. Always burns, never tans (often red hair, freckles).": "Piel muy clara. Siempre se quema, nunca se broncea (a menudo pelo rojo, pecas).",
  "Very high": "Muy alto",
  "WHO/WMO/UNEP/ICNIRP - Global Solar UV Index: A Practical Guide (2002)": "OMS/OMM/PNUMA/ICNIRP - Global Solar UV Index: A Practical Guide (2002)",
  "Warning: I did not find App 1's .venv environment; using the current Python.": "Atención: no encuentro el entorno .venv de la App 1; uso el Python actual.",
  "Weather and UV data:": "Datos meteorológicos y de UV:",
  "Welcome to NeoTracker": "Te damos la bienvenida a NeoTracker",
  "What is this information used for?": "¿Para qué sirven estos datos?",
  "What to do": "Qué hacer",
  "What to know before a genetic test": "Qué saber antes de una prueba genética",
  "Wheel = zoom · drag = move · double click = enlarge": "Rueda = zoom · arrastrar = mover · doble clic = ampliar",
  "When you noticed it, whether it itches, whether it has changed…": "Cuándo lo notaste, si pica, si ha cambiado…",
  "When you subscribe, the default daily limit is 2,000 calls: in the «Billing plans» tab of your account you can lower it to 1,000, so you spend nothing. NeoTracker uses very few (at most 4 every 10 minutes, only when you open the UV Index page).": "Al suscribirte, el límite diario predeterminado es de 2.000 llamadas: en la pestaña «Billing plans» de tu cuenta puedes bajarlo a 1.000 para no gastar nada. NeoTracker usa pocas (como máximo 4 cada 10 minutos, solo cuando abres la página Índice UV).",
  "Where they are": "Dónde están",
  "Who are you?": "¿Quién eres?",
  "With or without a test, for people with a family history, sun protection, skin self-examination and regular dermatological check-ups remain essential.": "Con o sin prueba, para quien tiene antecedentes familiares siguen siendo fundamentales la protección solar, la autoexploración de la piel y las revisiones dermatológicas periódicas.",
  "With the data entered you do not meet the most commonly used criteria. Genetic testing for melanoma is indicated only in a small minority of people and is not offered routinely. If your family history changes or you have doubts, update your profile and talk to your dermatologist.": "Con los datos introducidos no cumples los criterios más utilizados. La prueba genética para el melanoma solo está indicada en una pequeña minoría de personas y no se ofrece de forma rutinaria. Si cambian tus antecedentes familiares o tienes dudas, actualiza tu perfil y consúltalo con tu dermatólogo.",
  "With the data entered, no known risk factors appear. Complete your profile if information is missing.": "Con los datos introducidos no aparece ningún factor de riesgo conocido. Completa tu perfil si falta información.",
  "With your phototype ({fototipo})": "Con tu fototipo ({fototipo})",
  "Without Pillow the image must be a JPG/PNG under 400 KB (the page reduces it by itself: try again with the 'Choose image' function).": "Sin Pillow la imagen debe ser un JPG/PNG de menos de 400 KB (la página la reduce sola: inténtalo de nuevo con la función «Elegir imagen»).",
  "Woman": "Mujer",
  "Work or prolonged activity outdoors": "Trabajo o actividad prolongada al aire libre",
  "Yes": "Sí",
  "Yes, enable": "Sí, activar",
  "Yes, estimate the city": "Sí, estimar la ciudad",
  "Yes, negative": "Sí, negativo",
  "Yes, positive": "Sí, positivo",
  "Yes, uninformative": "Sí, no informativo",
  "You can close this window. To reopen the program, use the «NeoTracker» icon on the Desktop.": "Puedes cerrar esta ventana. Para volver a abrirlo, usa el icono «NeoTracker» del Escritorio.",
  "You can keep using the app. If you close the window the analysis is not lost: the program finishes the work and then shuts down by itself.": "Puedes seguir usando la aplicación. Si cierras la ventana el análisis no se pierde: el programa termina el trabajo y luego se apaga solo.",
  "You can use your own photo, a drawing or an icon. The image is cropped to a square and reduced, stays only on this computer and is never used for mole analysis.": "Puedes usar una foto tuya, un dibujo o un icono. La imagen se recorta en cuadrado y se reduce, permanece solo en este ordenador y nunca se usa para el análisis de los lunares.",
  "You chose OpenWeather but the key is missing (Settings): showing Open-Meteo data.": "Has elegido OpenWeather pero falta la clave (Ajustes): muestro los datos de Open-Meteo.",
  "You chose OpenWeather but there is no key yet: until one is added, the program uses Open-Meteo.": "Has elegido OpenWeather pero aún no hay clave: mientras falte, el programa usa Open-Meteo.",
  "You said you have already had a genetic test: take the report to your dermatologist.": "Has indicado que ya te has hecho una prueba genética: lleva el informe al dermatólogo.",
  "Your data (including health data) stays on this computer. Only the requests you turn on leave it: UV index (approximate coordinates), PubMed searches (only the search terms) and, only if you enable it, sending the photo to SkinSense.": "Tus datos (también los de salud) permanecen en este ordenador. Solo salen las solicitudes que activas tú: índice UV (coordenadas aproximadas), búsquedas en PubMed (solo los términos buscados) y, únicamente si lo activas, el envío de la foto a SkinSense.",
  "Your data against the criteria": "Tus datos frente a los criterios",
  "Your moles ({n})": "Tus lunares ({n})",
  "Zoom out": "Reducir",
  "a few": "pocas",
  "a few freckles": "pocas pecas",
  "about {minuti} minutes": "unos {minuti} minutos",
  "actinic keratosis, a pre-cancerous lesion": "queratosis actínica, una lesión precancerosa",
  "active only if you enable it below": "activo solo si lo habilitas más abajo",
  "address not allowed (https only)": "dirección no permitida (solo https)",
  "all methods with a result flag a mole that needs attention": "todos los métodos con resultado señalan un lunar que requiere atención",
  "and click on the exact spot on the body (zoom in with the wheel to be more precise).": "y haz clic en el punto exacto del cuerpo (amplía con la rueda para ser más preciso).",
  "and confirm the email.": "y confirma el correo electrónico.",
  "average of {n} models; mean score {media} (threshold 0)": "media de {n} modelos; puntuación media {media} (umbral 0)",
  "back": "espalda",
  "back of the hand": "dorso de la mano",
  "basal cell carcinoma, a skin cancer": "carcinoma basocelular, un cáncer de piel",
  "between the fingers or toes": "entre los dedos de la mano o del pie",
  "black hair": "cabello negro",
  "blond hair": "cabello rubio",
  "blue or grey eyes": "ojos azules o grises",
  "brown hair": "cabello castaño",
  "cannot start: {e}": "no se puede iniciar: {e}",
  "confidence {perc}": "confianza {perc}",
  "connection failed: {motivo}": "no se pudo conectar: {motivo}",
  "dark eyes": "ojos oscuros",
  "dermoscopic": "dermatoscópica",
  "dermoscopy": "dermatoscopia",
  "don't know": "no lo sé",
  "e.g. 4.5": "p. ej. 4,5",
  "ear": "oreja",
  "eyelid": "párpado",
  "fewer than 25": "menos de 25",
  "free, no account or key needed": "gratuita, sin cuenta ni clave",
  "front": "frente",
  "green eyes": "ojos verdes",
  "grey or white hair": "cabello canoso o blanco",
  "in clear skies and without protection, at today's peak the skin may redden in": "con cielo despejado y sin protección, en el pico de hoy la piel puede enrojecerse en",
  "in the panel": "en el panel",
  "in {n} day.": "en {n} día.",
  "in {n} days.": "en {n} días.",
  "invalid response from the service": "respuesta no válida del servicio",
  "lip": "labio",
  "location from internet address not available": "ubicación a partir de la dirección de internet no disponible",
  "man": "hombre",
  "many": "muchas",
  "many freckles": "muchas pecas",
  "melanoma": "melanoma",
  "melanoma detected": "melanoma detectado",
  "melanoma not detected": "melanoma no detectado",
  "melanoma prob. {perc}": "prob. de melanoma {perc}",
  "naevus, i.e. a benign mole": "nevus, es decir, lunar benigno",
  "name@example.com (optional)": "nombre@ejemplo.es (opcional)",
  "never": "nunca",
  "no": "no",
  "no cases indicated": "ningún caso indicado",
  "no freckles": "ninguna peca",
  "no method flagged the mole (this does not rule out a melanoma)": "ningún método ha señalado el lunar (esto no descarta un melanoma)",
  "no result available": "ningún resultado disponible",
  "normal photo": "foto normal",
  "often": "a menudo",
  "optional: requires a personal key of your own": "opcional: requiere una clave personal tuya",
  "other": "otro",
  "output interpreted as the 6 skin classes (not verifiable)": "salida interpretada como las 6 clases de piel (no verificable)",
  "over 2 hours (very low UV)": "más de 2 horas (UV muy bajo)",
  "palm of the hand": "palma de la mano",
  "phototype {tipo}": "fototipo {tipo}",
  "probability of malignancy estimated by the model: {pm}": "probabilidad de malignidad estimada por el modelo: {pm}",
  "red hair": "cabello pelirrojo",
  "response too large": "respuesta demasiado grande",
  "response without a lesion name: {risposta}": "respuesta sin nombre de la lesión: {risposta}",
  "scalp": "cuero cabelludo",
  "seborrhoeic keratosis, benign": "queratosis seborreica, benigna",
  "service address not allowed (https required)": "dirección del servicio no permitida (se requiere https)",
  "service page": "página del servicio",
  "service unreachable: {ultimo_errore}": "servicio no accesible: {ultimo_errore}",
  "significant": "relevante",
  "skin photos": "fotos de piel",
  "sole of the foot": "planta del pie",
  "sometimes": "a veces",
  "squamous cell carcinoma, a skin cancer": "carcinoma espinocelular, un cáncer de piel",
  "stopped after {minuti} minutes (maximum time)": "interrumpido tras {minuti} minutos (tiempo máximo)",
  "studies on PubMed": "estudios en PubMed",
  "the App 1 models have not been downloaded: they are still Git LFS placeholders. Open PowerShell in the folder {cartella}, run 'git lfs pull', then try again.": "los modelos de la App 1 no se han descargado: siguen siendo marcadores de posición de Git LFS. Abre PowerShell en la carpeta {cartella}, ejecuta 'git lfs pull' y vuelve a intentarlo.",
  "the first 1,000 calls per day are free, later ones are charged. OpenWeather may ask for a payment card to activate it: check the conditions on their website.": "las primeras 1.000 llamadas al día son gratuitas y las siguientes se pagan. OpenWeather puede pedir una tarjeta de pago para activarlo: consulta las condiciones en su sitio web.",
  "the methods do not agree with each other": "los métodos no coinciden entre sí",
  "the model has {n} outputs: meaning unknown": "el modelo tiene {n} salidas: significado desconocido",
  "the photo does not open as an image ({tipo}): {dettaglio}": "la foto no se abre como imagen ({tipo}): {dettaglio}",
  "the trained weights are missing: in the folder {cartella} there are no files model_fold_0.bin ... model_fold_4.bin. The repository does not contain them: they must be produced with train.py on the SIIM-ISIC dataset.": "faltan los pesos entrenados: en la carpeta {cartella} no están los archivos model_fold_0.bin ... model_fold_4.bin. El repositorio no los contiene: hay que generarlos con train.py sobre el conjunto de datos SIIM-ISIC.",
  "timed out or network unavailable": "tiempo agotado o red no disponible",
  "today": "hoy",
  "top of the foot": "empeine",
  "ukalwa / melanoma-detection (Android app)": "ukalwa / melanoma-detection (aplicación Android)",
  "under the nail (foot)": "bajo la uña (pie)",
  "under the nail (hand)": "bajo la uña (mano)",
  "unreadable response: {e}": "respuesta ilegible: {e}",
  "updated": "actualizado",
  "vatsal30 / Melanoma-Detection (PyTorch)": "vatsal30 / Melanoma-Detection (PyTorch)",
  "woman": "mujer",
  "yes": "sí",
  "yes, negative": "sí, negativo",
  "yes, positive": "sí, positivo",
  "yes, uninformative": "sí, no informativo",
  "yesterday": "ayer",
  "{avviso} The Open-Meteo service is not responding ({e}).": "{avviso} El servicio Open-Meteo no responde ({e}).",
  "{cosa} cannot be empty.": "{cosa} no puede estar vacío.",
  "{cosa} is too long (maximum {massimo} characters).": "{cosa} es demasiado largo (máximo {massimo} caracteres).",
  "{file_modello} is still a Git LFS placeholder: run 'git lfs pull' in the folder {cartella}.": "{file_modello} sigue siendo un marcador de posición de Git LFS: ejecuta 'git lfs pull' en la carpeta {cartella}.",
  "{file_pesi} is still a Git LFS placeholder: open PowerShell in the folder {cartella} and run 'git lfs pull'.": "{file_pesi} sigue siendo un marcador de posición de Git LFS: abre PowerShell en la carpeta {cartella} y ejecuta 'git lfs pull'.",
  "{foto} · last {quando}": "{foto} · última {quando}",
  "{giorno} at {ora}: UV index {uvi} ({categoria})": "{giorno} a las {ora}: índice UV {uvi} ({categoria})",
  "{nome} · {mb} MB · click to change": "{nome} · {mb} MB · haz clic para cambiar",
  "{nome}: enter a number.": "{nome}: introduce un número.",
  "{nome}: error.": "{nome}: error.",
  "{nome}: not available.": "{nome}: no disponible.",
  "{nome}: the value must be between {minimo} and {massimo}.": "{nome}: el valor debe estar entre {minimo} y {massimo}.",
  "{n} articles found on PubMed · search of {data}": "{n} artículos encontrados en PubMed · búsqueda del {data}",
  "{n} articles found on PubMed · search of {data} (saved)": "{n} artículos encontrados en PubMed · búsqueda del {data} (guardada)",
  "{n} articles on melanoma and «{termine}»": "{n} artículos sobre melanoma y «{termine}»",
  "{n} day": "{n} día",
  "{n} day has passed between the two photos.": "Entre las dos fotos ha pasado {n} día.",
  "{n} days": "{n} días",
  "{n} days ago": "hace {n} días",
  "{n} days have passed between the two photos.": "Entre las dos fotos han pasado {n} días.",
  "{n} first-degree relative(s) with melanoma": "{n} familiar(es) de primer grado con melanoma",
  "{n} model files out of 10": "{n} archivos de modelo de 10",
  "{n} model files out of 5": "{n} archivos de modelo de 5",
  "{n} mole": "{n} lunar",
  "{n} mole on this sheet": "{n} lunar en esta ficha",
  "{n} moles": "{n} lunares",
  "{n} moles on this sheet": "{n} lunares en esta ficha",
  "{n} months ago": "hace {n} meses",
  "{n} of {tot} methods responded": "{n} de {tot} métodos respondieron",
  "{n} of {tot}: {et}": "{n} de {tot}: {et}",
  "{n} other relative(s) with melanoma": "{n} otro(s) familiar(es) con melanoma",
  "{n} photo": "{n} foto",
  "{n} photos": "{n} fotos",
  "{n} photos in {giorni} (from {da} to {a}).": "{n} fotos en {giorni} (del {da} al {a}).",
  "{n} with astrocytoma": "{n} con astrocitoma",
  "{n} with pancreatic cancer": "{n} con cáncer de páncreas",
  "{n} with uveal melanoma": "{n} con melanoma uveal",
  "{n} year": "{n} año",
  "{n} year ago": "hace {n} año",
  "{n} years": "{n} años",
  "{n} years ago": "hace {n} años",
  "{vista} · position {x}% from the left, {y}% from the top": "{vista} · posición {x} % desde la izquierda, {y} % desde arriba",
  "…of which 1st-degree": "…de los cuales de 1.er grado",
  "← All moles": "← Todos los lunares"
};
'''
WEB_FILES["/i18n_es.js"] = ("text/javascript; charset=utf-8", _WEB_I18N_ES_JS.encode("utf-8"))

_WEB_I18N_FR_JS = r'''/* NeoTracker interface translations: fr. Key = the English source text.
   Keep the {name} placeholders unchanged. Check: python3 tools/traduzioni.py */
(window.NT_DIZIONARI = window.NT_DIZIONARI || {}).fr = {
  "(CC BY 4.0 licence). The free service is for personal, non-commercial use.": "(licence CC BY 4.0). Le service gratuit est réservé à un usage personnel et non commercial.",
  "(empty)": "(vide)",
  "(local time at the location)": "(heure locale du lieu)",
  "(saved search from {data})": "(recherche enregistrée du {data})",
  "(untitled)": "(sans titre)",
  "({variazione} mm since the previous photo)": "({variazione} mm par rapport à la photo précédente)",
  "1 photo from {data}, diameter {mm} mm.": "1 photo du {data}, diamètre {mm} mm.",
  "1 photo from {data}.": "1 photo du {data}.",
  "100 or more": "100 ou plus",
  "100 or more moles on the body": "100 grains de beauté ou plus sur le corps",
  "1st-degree relatives with melanoma": "Parents du 1er degré atteints de mélanome",
  "3 = WHO recommends protection from this level": "3 = l'OMS recommande une protection à partir d'ici",
  "3 or more primary melanomas in the same person": "3 mélanomes primaires ou plus chez la même personne",
  "50 to 99 moles on the body": "De 50 à 99 grains de beauté sur le corps",
  "A few": "Peu",
  "A mole that changes (shape, borders, colour, size), bleeds, itches or worries you must be shown to a dermatologist, whatever the app says. Regular check-ups with the dermatologist remain irreplaceable.": "Un grain de beauté qui change (forme, bords, couleur, taille), saigne, démange ou vous inquiète doit être montré à un dermatologue, quoi que dise l'application. Le contrôle périodique chez le dermatologue reste irremplaçable.",
  "A positive result indicates a higher risk, not certainty of becoming ill; a negative result does not remove the risk (many families have no identifiable variant).": "Un résultat positif indique un risque plus élevé, pas la certitude de tomber malade ; un résultat négatif n'annule pas le risque (beaucoup de familles n'ont pas de variant identifiable).",
  "A user with this name already exists.": "Un utilisateur portant ce nom existe déjà.",
  "ABCDE criteria and the 'ugly duckling' sign": "Critères ABCDE et signe du « vilain petit canard »",
  "ABCDE reminder": "Aide-mémoire ABCDE",
  "ABCDE reminder for recognising a mole": "Aide-mémoire ABCDE pour reconnaître un grain de beauté",
  "About 5–10% of melanomas occur in families with an inherited predisposition (Leachman 2009). Here you find the criteria specialists use to decide whether to suggest genetic counselling, the genes involved and the literature on each.": "Environ 5 à 10 % des mélanomes surviennent dans des familles présentant une prédisposition héréditaire (Leachman 2009). Vous trouvez ici les critères que les spécialistes utilisent pour décider de proposer une consultation de génétique, les gènes concernés et la littérature sur chacun.",
  "Accept and continue": "Accepter et continuer",
  "According to the NCCN guidelines, in an invasive melanoma with a first-degree relative with pancreatic cancer, a multigene panel that includes CDKN2A is recommended.": "Selon les recommandations du NCCN, en cas de mélanome invasif avec un parent du premier degré atteint d'un cancer du pancréas, un panel multigénique incluant CDKN2A est recommandé.",
  "Acral melanoma (hands, feet, nails): dermoscopy": "Mélanome acral (mains, pieds, ongles) : dermoscopie",
  "Add a photo to the history": "Ajouter une photo à l'historique",
  "Add mole": "Ajouter un grain de beauté",
  "Add the first photo below: it will be the starting point to see whether the mole changes over time.": "Ajoutez ci-dessous la première photo : elle servira de point de départ pour voir si le grain de beauté change au fil du temps.",
  "Add the first photo: it becomes your baseline photo, and every later photo will follow how the mole evolves.": "Ajoutez la première photo : elle devient votre photo de référence, et chaque photo suivante montrera l'évolution du grain de beauté.",
  "Address not allowed.": "Adresse non autorisée.",
  "Address too long.": "Adresse trop longue.",
  "After": "Après",
  "Age": "Âge",
  "Age, sex and phenotype do not change the output of the neural networks: they are used to show you the risk factors, choose the literature, evaluate the genetics criteria and estimate the time to sunburn.": "L'âge, le sexe et le phénotype ne modifient pas le résultat des réseaux de neurones : ils servent à vous montrer les facteurs de risque, à choisir la littérature, à évaluer les critères de génétique et à estimer le temps avant un coup de soleil.",
  "All data stays on this computer, in the folder:": "Toutes les données restent sur cet ordinateur, dans le dossier :",
  "All its {n} photos and the analysis reports will be deleted permanently.": "Ses {n} photos et les rapports d'analyse seront supprimés définitivement.",
  "Also use SkinSense (online service)": "Utiliser aussi SkinSense (service en ligne)",
  "Always shoot from the same angle and keep the original, without filters.": "Prenez toujours la photo sous le même angle et conservez l'original, sans filtre.",
  "An estimate is fine.": "Une estimation suffit.",
  "Analyse now with all installed methods": "Analyser maintenant avec toutes les méthodes installées",
  "Analyse this photo": "Analyser cette photo",
  "Analysis in progress…": "Analyse en cours…",
  "Analysis interrupted (app closed).": "Analyse interrompue (application fermée).",
  "Analysis program (melanoma_batch.py) not found: photos are saved but cannot be analysed.": "Programme d'analyse (melanoma_batch.py) introuvable : les photos sont enregistrées mais ne peuvent pas être analysées.",
  "Analysis program:": "Programme d'analyse :",
  "Analysis stopped after {ore} hours (too long).": "Analyse interrompue après {ore} heures (trop longue).",
  "Analysis: needs attention": "Analyse : à surveiller",
  "Ankle, left": "Cheville gauche",
  "Ankle, right": "Cheville droite",
  "Anything else you want to remember (allergies, photosensitising medicines, …)": "Autre chose dont vous voulez vous souvenir (allergies, médicaments photosensibilisants, …)",
  "App 1 (DeborahAdedigba) - TensorFlow models": "App 1 (DeborahAdedigba) - modèles TensorFlow",
  "Appearance": "Apparence",
  "Archive (removes it from the map, keeps the data)": "Archiver (le retire de la carte, conserve les données)",
  "Archived moles ({n})": "Grains de beauté archivés ({n})",
  "Arm, left": "Bras gauche",
  "Arm, right": "Bras droit",
  "Asking the browser for your position… (a permission request may appear)": "Demande de la position au navigateur… (une demande d'autorisation peut s'afficher)",
  "Associated risk": "Risque associé",
  "Associated with variants of the MC1R gene.": "Associés à des variants du gène MC1R.",
  "Astrocytoma": "Astrocytome",
  "Asymmetry": "Asymétrie",
  "At least 3 diagnoses among melanoma, pancreatic cancer and astrocytoma in the same family line (yours included)": "Au moins 3 diagnostics parmi mélanome, cancer du pancréas et astrocytome dans la même lignée familiale (la vôtre incluse)",
  "At least one method (or one of its models) flags a lesion that needs attention. This is not a diagnosis and these tools are often wrong, but it is one more reason not to put off the dermatology visit and to bring this report.": "Au moins une méthode (ou l'un de ses modèles) signale une lésion à surveiller. Ce n'est pas un diagnostic et ces outils se trompent souvent, mais c'est une raison de plus de ne pas reporter la consultation dermatologique et d'apporter ce rapport.",
  "Atypical (dysplastic) moles": "Grains de beauté atypiques (dysplasiques)",
  "Atypical moles": "Grains de beauté atypiques",
  "Automatic (same as the system)": "Automatique (comme le système)",
  "Automatic analysis": "Analyse automatique",
  "Avoid direct exposure: unprotected skin can burn within a few minutes.": "Évitez l'exposition directe : une peau non protégée peut brûler en quelques minutes.",
  "Avoid the sun in the middle hours of the day and protect your skin well.": "Évitez le soleil aux heures centrales de la journée et protégez bien votre peau.",
  "BACK": "DOS",
  "BAP1 tumour predisposition syndrome: uveal melanoma, mesothelioma, renal carcinoma, cutaneous melanoma and atypical melanocytic naevi.": "Syndrome de prédisposition aux tumeurs BAP1 : mélanome uvéal, mésothéliome, carcinome rénal, mélanome cutané et naevus mélanocytaires atypiques.",
  "BAP1-spectrum tumours indicated: {bap1_spettro}. Simplified criterion: the geneticist uses more complete criteria.": "Tumeurs du spectre BAP1 indiquées : {bap1_spettro}. Critère simplifié : le généticien utilise des critères plus complets.",
  "Back": "Dos",
  "Back (middle area), left": "Dos (zone médiane) gauche",
  "Back (middle area), right": "Dos (zone médiane) droit",
  "Back of knee, left": "Creux poplité gauche",
  "Back of knee, right": "Creux poplité droit",
  "Before": "Avant",
  "Before you start": "Avant de commencer",
  "Black": "Noirs",
  "Blond": "Blonds",
  "Blue/grey": "Bleus/gris",
  "Border": "Bords",
  "Brown": "Châtains",
  "Buttock, left": "Fesse gauche",
  "Buttock, right": "Fesse droite",
  "Calf, left": "Mollet gauche",
  "Calf, right": "Mollet droit",
  "Can't do it? Estimate from the internet address": "Vous n'y arrivez pas ? Estimer à partir de l'adresse internet",
  "Cancel": "Annuler",
  "Centre on the map": "Centrer sur la carte",
  "Change": "Changer",
  "Change image…": "Changer d'image…",
  "Change:": "Variation :",
  "Checking status…": "Vérification de l'état…",
  "Chest, left": "Thorax gauche",
  "Chest, right": "Thorax droit",
  "Choose a personal picture": "Choisir une image personnelle",
  "Choose a user and enter their phototype to see how many minutes it takes to burn.": "Choisissez un utilisateur et indiquez son phototype pour voir en combien de minutes on brûle.",
  "Choose an image file (JPG, PNG, WEBP or BMP).": "Choisissez un fichier image (JPG, PNG, WEBP ou BMP).",
  "Choose image…": "Choisir une image…",
  "Choose the city above: then you will see today's UV index, hour by hour.": "Choisissez la ville ci-dessus : vous verrez ensuite l'indice UV du jour, heure par heure.",
  "Choose user": "Choisir l'utilisateur",
  "Choose where you are to see today's UV index.": "Choisissez où vous vous trouvez pour voir l'indice UV du jour.",
  "Choose your profile: each person has their own mole map, photos and data.": "Choisissez votre profil : chaque personne a sa propre carte des grains de beauté, ses photos et ses données.",
  "Cited by the NCCN guidelines among the genes to consider in melanoma panels (Cowden syndrome).": "Cité par les recommandations du NCCN parmi les gènes à envisager dans les panels pour le mélanome (syndrome de Cowden).",
  "City name": "Nom de la ville",
  "City search also uses Open-Meteo.": "La recherche de villes utilise aussi Open-Meteo.",
  "Classified as definite human carcinogens (IARC).": "Classés comme cancérogènes certains pour l'homme (CIRC).",
  "Click a mole in the list or on the map to see its photo history.": "Cliquez sur un grain de beauté dans la liste ou sur la carte pour voir son historique photographique.",
  "Click on the exact spot on the body where the mole is (you can zoom in first)": "Cliquez sur l'endroit exact du corps où se trouve le grain de beauté (vous pouvez d'abord zoomer)",
  "Click to see the original photo full screen": "Cliquez pour voir la photo originale en plein écran",
  "Clinical trial": "Essai clinique",
  "Close": "Fermer",
  "Close NeoTracker": "Fermer NeoTracker",
  "Close NeoTracker?": "Fermer NeoTracker ?",
  "Close the program": "Fermer le programme",
  "Closing the program": "Fermer le programme",
  "Colour": "Couleur",
  "Common variants linked to red hair and fair skin: they raise the melanoma risk moderately. Not a routine test: interpretation is specialist.": "Variants courants liés aux cheveux roux et à la peau claire : ils augmentent modérément le risque de mélanome. Ce n'est pas un test de routine : l'interprétation relève d'un spécialiste.",
  "Compare": "Comparer",
  "Compare shape, borders and colours: if you notice differences, show the photos to your dermatologist.": "Comparez la forme, les bords et les couleurs : si vous remarquez des différences, montrez les photos à votre dermatologue.",
  "Comparison of two photos": "Comparaison de deux photos",
  "Comparison slider": "Curseur de comparaison",
  "Confirm": "Confirmer",
  "Consent": "Consentement",
  "Count blood relatives (not in-laws) on the same side of the family, maternal or paternal: this is the criterion geneticists use. If you do not know, ask a relative: this information is very useful.": "Comptez les parents du même sang (pas les alliés) du même côté de la famille, maternel ou paternel : c'est le critère utilisé par les généticiens. Si vous ne savez pas, demandez à un proche : ces informations sont très utiles.",
  "Create a free account at": "Créez un compte gratuit sur",
  "Create user": "Créer l'utilisateur",
  "Dark": "Foncés",
  "Dark skin. Rarely burns.": "Peau foncée. Brûle rarement.",
  "Date of birth": "Date de naissance",
  "Date of birth out of range.": "Date de naissance hors limites.",
  "Date the photo was taken": "Date de la prise de vue",
  "Decrease: {voce}": "Diminuer : {voce}",
  "Deep learning and melanoma: systematic reviews": "Apprentissage profond et mélanome : revues systématiques",
  "Delete": "Supprimer",
  "Delete permanently": "Supprimer définitivement",
  "Delete photo": "Supprimer la photo",
  "Delete this mole and its photos": "Supprimer ce grain de beauté et ses photos",
  "Delete this photo?": "Supprimer cette photo ?",
  "Delete «{nome}»?": "Supprimer « {nome} » ?",
  "Dermoscopic": "Dermoscopique",
  "Dermoscopy and early diagnosis (reviews)": "Dermoscopie et diagnostic précoce (revues)",
  "Detect my location": "Détecter ma position",
  "Diameter": "Diamètre",
  "Diameter (mm)": "Diamètre (mm)",
  "Diameter over time": "Diamètre au fil du temps",
  "Diameter:": "Diamètre :",
  "Diameter: from {da} to {a} mm.": "Diamètre : de {da} à {a} mm.",
  "Diameter: {diff} mm difference.": "Diamètre : {diff} mm de différence.",
  "Don't know": "Ne sait pas",
  "Downloading the UV index…": "Téléchargement de l'indice UV…",
  "Drag a photo here or click to choose one": "Faites glisser une photo ici ou cliquez pour en choisir une",
  "Drag the dot on the map to correct the position; zoom in with the wheel for maximum precision.": "Faites glisser le point sur la carte pour corriger la position ; zoomez avec la molette pour une précision maximale.",
  "Drag the dot on the map to move it.": "Faites glisser le point sur la carte pour le déplacer.",
  "Ear, left": "Oreille gauche",
  "Ear, right": "Oreille droite",
  "Edit date/measurement": "Modifier la date/la mesure",
  "Edit photo": "Modifier la photo",
  "Edit the data in the Profile": "Modifier les données dans le Profil",
  "Elbow, left": "Coude gauche",
  "Elbow, right": "Coude droit",
  "Email for PubMed": "E-mail pour PubMed",
  "Email saved.": "E-mail enregistré.",
  "Enlarge": "Agrandir",
  "Error {codice}": "Erreur {codice}",
  "Especially in childhood and adolescence.": "Surtout dans l'enfance et l'adolescence.",
  "Estimate from the internet address": "Estimation à partir de l'adresse internet",
  "Estimated location": "Position estimée",
  "Evolution": "Évolution",
  "Extra precautions: avoid the sun in the middle of the day, seek shade, cover your skin, SPF 30+. Unprotected skin burns quickly.": "Précautions supplémentaires : évitez le soleil aux heures centrales, cherchez l'ombre, couvrez votre peau, SPF 30+. Une peau non protégée brûle vite.",
  "Extreme": "Extrême",
  "Eye colour": "Couleur des yeux",
  "Eyes": "Yeux",
  "FRONT": "FACE",
  "Face": "Visage",
  "Fair phototype (I–II)": "Phototype clair (I-II)",
  "Fair skin. Burns easily, tans little.": "Peau claire. Brûle facilement, bronze peu.",
  "Fair-olive skin. Sometimes burns, tans gradually.": "Peau claire à mate. Brûle parfois, bronze progressivement.",
  "Fajuyigbe D, Young AR. The impact of skin colour on human photobiological responses. Pigment Cell Melanoma Res 2016;29:607-18 (minimal erythema dose by phototype)": "Fajuyigbe D, Young AR. The impact of skin colour on human photobiological responses. Pigment Cell Melanoma Res 2016;29:607-18 (dose érythémale minimale selon le phototype)",
  "Family history": "Antécédents familiaux",
  "Fewer than 25": "Moins de 25",
  "Fill in the 'Family history' section of your Profile: without that data I cannot check the criteria.": "Remplissez la section « Antécédents familiaux » de votre Profil : sans ces données, je ne peux pas vérifier les critères.",
  "Fill in the family history in your Profile": "Renseigner les antécédents familiaux dans le Profil",
  "First-degree relative with melanoma": "Parent du premier degré atteint de mélanome",
  "Folder with your data (copy it for backup):": "Dossier de vos données (à copier pour la sauvegarde) :",
  "Foot, left": "Pied gauche",
  "Foot, right": "Pied droit",
  "Forearm, left": "Avant-bras gauche",
  "Forearm, right": "Avant-bras droit",
  "Forehead and scalp": "Front et cuir chevelu",
  "Freckles": "Éphélides",
  "Freckles (ephelides)": "Éphélides (taches de rousseur)",
  "Front": "Face",
  "Full report (text)": "Rapport complet (texte)",
  "Full report (text, in English)": "Rapport complet (texte, en anglais)",
  "Gene": "Gène",
  "Gene not in the list.": "Gène absent de la liste.",
  "Gene {n} of {tot} ({nome})…": "Gène {n} sur {tot} ({nome})…",
  "Genetic test": "Test génétique",
  "Genetic test already done": "Test génétique déjà effectué",
  "Genetics": "Génétique",
  "Give the mole a name and check the site.": "Donnez un nom au grain de beauté et vérifiez l'emplacement.",
  "Go to the Genetics section": "Aller à la section Génétique",
  "Grandparents, aunts and uncles, nieces and nephews (2nd degree).": "Grands-parents, oncles et tantes, neveux et nièces (2e degré).",
  "Green": "Verts",
  "Grey/white": "Gris/blancs",
  "Groin, left": "Aine gauche",
  "Groin, right": "Aine droite",
  "Guideline": "Recommandation",
  "Guidelines and criteria for genetic testing": "Recommandations et critères pour le test génétique",
  "Guidelines recommend the test only after careful selection of candidates and adequate counselling (Rossi 2019); the use of multigene panels is still debated.": "Les recommandations préconisent le test uniquement après une sélection rigoureuse des candidats et une consultation adaptée (Rossi 2019) ; l'utilisation des panels multigéniques fait encore débat.",
  "Hair": "Cheveux",
  "Hand, left": "Main gauche",
  "Hand, right": "Main droite",
  "Has a doctor told you that you have atypical (dysplastic) moles?": "Un médecin vous a-t-il dit que vous avez des grains de beauté atypiques (dysplasiques) ?",
  "Have I already had a genetic test for melanoma?": "Ai-je déjà fait un test génétique pour le mélanome ?",
  "Having had a melanoma raises the risk of a second one.": "Avoir eu un mélanome augmente le risque d'en avoir un second.",
  "Hereditary melanoma": "Mélanome héréditaire",
  "Hereditary melanoma and genetic testing": "Mélanome héréditaire et test génétique",
  "High": "Élevé",
  "High (BAP1 syndrome)": "Élevé (syndrome BAP1)",
  "High (rare)": "Élevé (rare)",
  "Hour-by-hour UV index for the next 24 hours": "Indice UV heure par heure pour les prochaines 24 heures",
  "Hourly data not available": "Données horaires indisponibles",
  "How reliable are apps and artificial intelligence": "Quelle est la fiabilité des applications et de l'intelligence artificielle",
  "How to get the key": "Comment obtenir la clé",
  "How to read the UV index": "Comment lire l'indice UV",
  "How to take comparable photos": "Comment prendre des photos comparables",
  "I am immunosuppressed (transplant or therapies that lower the body's defences)": "Je suis immunodéprimé(e) (greffe ou traitements qui affaiblissent les défenses)",
  "I assume the 2 outputs are [benign, malignant]; order cannot be verified": "je suppose que les 2 sorties sont [bénin, malin] ; ordre non vérifiable",
  "I cannot find melanoma_batch.py: it must be in the same folder as neotracker.py (or in {CARTELLA_REPO}).": "Impossible de trouver melanoma_batch.py : il doit se trouver dans le même dossier que neotracker.py (ou dans {CARTELLA_REPO}).",
  "I cannot prepare the photo safely: {e}": "impossible de préparer la photo en toute sécurité : {e}",
  "I cannot reach NeoTracker. The program may have been closed: reopen it from the icon on the Desktop.": "Impossible de joindre NeoTracker. Le programme a peut-être été fermé : rouvrez-le avec l'icône du Bureau.",
  "I cannot read this image. Try a JPG or a PNG.": "Impossible de lire cette image. Essayez avec un JPG ou un PNG.",
  "I cannot reduce this image.": "Impossible de réduire cette image.",
  "I don't know: leave it empty, you can come back later.": "Je ne sais pas : laissez vide, vous pourrez y revenir plus tard.",
  "I have checked my family history (even if the answer is «none»)": "J'ai vérifié mes antécédents familiaux (même si la réponse est « aucun »)",
  "I have had (or have) one of these cancers:": "J'ai eu (ou j'ai) l'un de ces cancers :",
  "I have had other skin cancers (basal cell or squamous cell carcinoma)": "J'ai eu d'autres cancers de la peau (carcinome basocellulaire ou épidermoïde)",
  "I have read and understood these notices": "J'ai lu et compris ces avertissements",
  "I prefer not to say": "Je préfère ne pas le dire",
  "I work or do activities outdoors for many hours": "Je travaille ou pratique des activités en plein air pendant de nombreuses heures",
  "If it is still analysing a photo, it finishes the analysis first and then shuts down. The button below does the same thing.": "S'il est encore en train d'analyser une photo, il termine d'abord l'analyse puis s'arrête. Le bouton ci-dessous fait la même chose.",
  "If you are unsure about your phototype, think about how your skin reacts to the first intense sun exposure in summer, without protection.": "Si vous hésitez sur votre phototype, pensez à la réaction de votre peau à la première exposition intense au soleil en été, sans protection.",
  "If you enter data or photos of other people, make sure you have their consent.": "Si vous saisissez des données ou des photos d'autres personnes, assurez-vous d'avoir leur consentement.",
  "Immunosuppression (therapies, transplant)": "Immunosuppression (traitements, greffe)",
  "Important notices": "Avertissements",
  "In English": "En anglais",
  "In-focus photo, with the mole in the centre and the skin clearly visible (move hair aside if needed).": "Photo nette, avec le grain de beauté au centre et la peau bien visible (écartez les poils si nécessaire).",
  "Increase: {voce}": "Augmenter : {voce}",
  "Installation status": "État de l'installation",
  "Interface language": "Langue de l'interface",
  "Internal error. Details are in the neotracker.log file in the data folder.": "Erreur interne. Les détails se trouvent dans le fichier neotracker.log du dossier des données.",
  "Invalid UV index source.": "Source de l'indice UV non valide.",
  "Invalid coordinates.": "Coordonnées non valides.",
  "Invalid data (JSON).": "Données non valides (JSON).",
  "Invalid data.": "Données non valides.",
  "Invalid date of birth (YYYY-MM-DD).": "Date de naissance non valide (AAAA-MM-JJ).",
  "Invalid date: use the format YYYY-MM-DD.": "Date non valide : utilisez le format AAAA-MM-JJ.",
  "Invalid email address.": "Adresse e-mail non valide.",
  "Invalid location.": "Position non valide.",
  "Invalid notice version.": "Version de l'avertissement non valide.",
  "Invalid page identifier.": "Identifiant de page non valide.",
  "Invalid profile.": "Profil non valide.",
  "Irregular, jagged or blurred.": "Irréguliers, dentelés ou flous.",
  "It changes over time: shape, colour, size, elevation, or itching or bleeding appear.": "Il change avec le temps : forme, couleur, taille, relief, ou apparition de démangeaisons ou de saignements.",
  "It is a personal tool for organising the photos of your moles and comparing over time the results of some research models. It is not certified or approved by any health authority.": "C'est un outil personnel pour organiser les photos de vos grains de beauté et comparer dans le temps les résultats de certains modèles de recherche. Il n'est ni certifié ni approuvé par aucune autorité sanitaire.",
  "It is normal for the methods to disagree: it only means that none of them is reliable on its own.": "Il est normal que les méthodes ne soient pas d'accord : cela signifie seulement qu'aucune n'est fiable à elle seule.",
  "It works: OpenWeather answers (current UV index: {uvi}).": "Ça fonctionne : OpenWeather répond (indice UV actuel : {uvi}).",
  "Its only photo and the analysis reports will be deleted permanently.": "Sa seule photo et les rapports d'analyse seront supprimés définitivement.",
  "JPG, PNG, WEBP or BMP · up to 60 MB": "JPG, PNG, WEBP ou BMP · jusqu'à 60 Mo",
  "Key removed.": "Clé supprimée.",
  "Key saved ({finale}) — type a new one to replace it": "Clé enregistrée ({finale}) — saisissez-en une nouvelle pour la remplacer",
  "Key saved.": "Clé enregistrée.",
  "Kidney carcinoma": "Carcinome du rein",
  "Knee, left": "Genou gauche",
  "Knee, right": "Genou droit",
  "L": "G",
  "Language": "Langue",
  "Language not supported.": "Langue non prise en charge.",
  "Large, irregular, multicoloured moles: they should be followed over time.": "Grains de beauté grands, irréguliers, de plusieurs couleurs : ils doivent être suivis dans le temps.",
  "Latest automatic analysis ({data}): {esito}. Research tool, not diagnostic.": "Dernière analyse automatique ({data}) : {esito}. Outil de recherche, non diagnostique.",
  "Leachman 2009 and 2017; NCCN": "Leachman 2009 et 2017 ; NCCN",
  "Leachman 2017; NCCN": "Leachman 2017 ; NCCN",
  "Lentigo maligna and melanoma of the face": "Lentigo malin et mélanome du visage",
  "Light-coloured eyes": "Yeux clairs",
  "List of factors known from the literature, not a validated score: it does not estimate the probability of falling ill.": "Liste de facteurs connus dans la littérature, et non un score validé : elle n'estime pas la probabilité de tomber malade.",
  "Literature": "Littérature",
  "Literature: PubMed": "Littérature : PubMed",
  "Loading…": "Chargement…",
  "Location": "Position",
  "Location missing": "Position manquante",
  "Location not set": "Position non définie",
  "Location not set: choose a city or use 'Detect my location'.": "Position non définie : choisissez une ville ou utilisez « Détecter ma position ».",
  "Location outside the map.": "Position en dehors de la carte.",
  "Location saved: {nome}": "Position enregistrée : {nome}",
  "Location set": "Position définie",
  "Location updated.": "Position mise à jour.",
  "Location updated: {regione}.": "Position mise à jour : {regione}.",
  "Low": "Faible",
  "Low to moderate (common)": "Faible à modéré (fréquent)",
  "Lower abdomen, left": "Bas de l'abdomen gauche",
  "Lower abdomen, right": "Bas de l'abdomen droit",
  "Lower back, left": "Région lombaire gauche",
  "Lower back, right": "Région lombaire droite",
  "Lower leg (shin), left": "Jambe (tibia) gauche",
  "Lower leg (shin), right": "Jambe (tibia) droite",
  "Lucas RM et al. Are current guidelines for sun protection optimal for health? Photochem Photobiol Sci 2018;17:1956-63 (UV Index and erythemal dose)": "Lucas RM et al. Are current guidelines for sun protection optimal for health? Photochem Photobiol Sci 2018;17:1956-63 (indice UV et dose érythémale)",
  "Main high-penetrance predisposition gene. Germline variants in 20–40% of families with melanoma; also associated with pancreatic cancer, multiple melanomas and early onset.": "Principal gène de prédisposition à forte pénétrance. Variants germinaux dans 20 à 40 % des familles atteintes de mélanome ; également associé au cancer du pancréas, aux mélanomes multiples et à un début précoce.",
  "Man": "Homme",
  "Many": "Beaucoup",
  "Many freckles (ephelides)": "Beaucoup d'éphélides (taches de rousseur)",
  "Many moles or atypical moles: surveillance": "Beaucoup de grains de beauté ou grains de beauté atypiques : surveillance",
  "Many sunburns with blisters": "Beaucoup de coups de soleil avec cloques",
  "Map of the human body: front on the left, back on the right": "Carte du corps humain : face à gauche, dos à droite",
  "Measured diameter (mm)": "Diamètre mesuré (mm)",
  "Melanoma already diagnosed": "Mélanome déjà diagnostiqué",
  "Melanoma and immunosuppression": "Mélanome et immunosuppression",
  "Melanoma in dark skin (often acral)": "Mélanome sur peau foncée (souvent acral)",
  "Melanoma of the eye (uveal)": "Mélanome de l'œil (uvéal)",
  "Melanoma-Detector (VukIG)": "Melanoma-Detector (VukIG)",
  "Melanomas already diagnosed": "Mélanomes déjà diagnostiqués",
  "Melanomas already diagnosed in me": "Mélanomes déjà diagnostiqués chez moi",
  "Mesothelioma": "Mésothéliome",
  "Met": "Satisfait",
  "Meta-analysis": "Méta-analyse",
  "Method 1 - App 1 (Deborah Adedigba)": "Méthode 1 - App 1 (Deborah Adedigba)",
  "Method 1 turned off in the settings.": "Méthode 1 désactivée dans les paramètres.",
  "Method 2 - SkinSense (online service)": "Méthode 2 - SkinSense (service en ligne)",
  "Method 2 not run (turned off in the settings): the photo did not leave the PC.": "Méthode 2 non exécutée (désactivée dans les paramètres) : la photo n'a pas quitté le PC.",
  "Method 3 did NOT analyse the photo: the project is a prototype without a model. Its server merely receives the image (no neural network), so any reassuring text it shows does not come from an analysis and has no value.": "La méthode 3 n'a PAS analysé la photo : le projet est un prototype sans modèle. Son serveur se contente de recevoir l'image (aucun réseau de neurones), donc tout texte rassurant affiché ne provient pas d'une analyse et n'a aucune valeur.",
  "Method 4 - vatsal30": "Méthode 4 - vatsal30",
  "Method 4 turned off in the settings.": "Méthode 4 désactivée dans les paramètres.",
  "Method 5 is an Android app: it cannot run on the PC. Install the APK on the phone, frame the mole and note the result by hand below.\nApp result on the phone: ______________________________": "La méthode 5 est une application Android : elle ne peut pas tourner sur le PC. Installez l'APK sur le téléphone, cadrez le grain de beauté et notez le résultat à la main ci-dessous.\nRésultat de l'application sur le téléphone : ______________________________",
  "Method {n}": "Méthode {n}",
  "Method {n} said:": "La méthode {n} a indiqué :",
  "Methods disagree": "Méthodes en désaccord",
  "Moderate": "Modéré",
  "Moderate UV: protection needed in the middle of the day": "UV modérés : une protection est nécessaire aux heures centrales",
  "Mole archived. You will find it at the bottom of the list.": "Grain de beauté archivé. Vous le trouverez en bas de la liste.",
  "Mole deleted.": "Grain de beauté supprimé.",
  "Mole diameter over time": "Diamètre du grain de beauté au fil du temps",
  "Mole map": "Carte des grains de beauté",
  "Mole name": "Nom du grain de beauté",
  "Mole not found.": "Grain de beauté introuvable.",
  "Mole saved. Now add the first photo: it will be your \"baseline photo\".": "Grain de beauté enregistré. Ajoutez maintenant la première photo : ce sera votre « photo de référence ».",
  "Mole sheet – {nome}": "Fiche des grains de beauté – {nome}",
  "Mole with photos": "Grain de beauté avec photos",
  "Mole {n}": "Grain de beauté {n}",
  "More than 6 mm (but smaller melanomas exist).": "Plus de 6 mm (mais il existe des mélanomes plus petits).",
  "Most recent studies on predisposition genes": "Études les plus récentes sur les gènes de prédisposition",
  "Most relevant studies": "Études les plus pertinentes",
  "Move the pointer over the body to see the area": "Passez le pointeur sur le corps pour voir la zone",
  "Multiple BAP1-spectrum tumours (uveal melanoma, mesothelioma, renal carcinoma, cutaneous melanoma)": "Plusieurs tumeurs du spectre BAP1 (mélanome uvéal, mésothéliome, carcinome rénal, mélanome cutané)",
  "My location ({lat}; {lon})": "Ma position ({lat} ; {lon})",
  "NCCN": "NCCN",
  "NCCN Clinical Practice Guidelines in Oncology: Melanoma: Cutaneous (current version; the full text requires free registration)": "NCCN Clinical Practice Guidelines in Oncology: Melanoma: Cutaneous (version actuelle ; le texte complet nécessite une inscription gratuite)",
  "Name": "Nom",
  "Name or nickname": "Nom ou surnom",
  "Nape and neck": "Nuque et cou",
  "Natural hair colour (when young)": "Couleur naturelle des cheveux (dans la jeunesse)",
  "Neck": "Cou",
  "Needs attention": "À surveiller",
  "NeoTracker closed": "NeoTracker fermé",
  "NeoTracker is closed": "NeoTracker est fermé",
  "NeoTracker is not a genetic counselling service. For a personal assessment, see your dermatologist or an oncological genetics centre.": "NeoTracker n'est pas un service de conseil génétique. Pour une évaluation personnelle, adressez-vous à votre dermatologue ou à un centre de génétique oncologique.",
  "NeoTracker is not a medical device and does not make diagnoses.": "NeoTracker n'est pas un dispositif médical et ne pose aucun diagnostic.",
  "NeoTracker is not a medical tool and does not make diagnoses. For any mole that changes, bleeds, itches or worries you, see a dermatologist.": "NeoTracker n'est pas un outil médical et ne pose aucun diagnostic. Pour tout grain de beauté qui change, saigne, démange ou vous inquiète, consultez un dermatologue.",
  "NeoTracker is not responding": "NeoTracker ne répond pas",
  "Never": "Jamais",
  "New mole": "Nouveau grain de beauté",
  "New user": "Nouvel utilisateur",
  "Next {n} hours": "{n} prochaines heures",
  "No": "Non",
  "No alarm from the models": "Aucune alerte des modèles",
  "No articles found.": "Aucun article trouvé.",
  "No city found with this name.": "Aucune ville trouvée avec ce nom.",
  "No image set.": "Aucune image définie.",
  "No method produced a result: check the reasons listed below.": "Aucune méthode n'a produit de résultat : consultez les motifs indiqués ci-dessous.",
  "No moles yet": "Aucun grain de beauté pour l'instant",
  "No photo recorded yet.": "Aucune photo enregistrée pour l'instant.",
  "No photos yet": "Aucune photo pour l'instant",
  "No photos: add the first one": "Aucune photo : ajoutez la première",
  "No result": "Aucun résultat",
  "No special protection needed for normal activities; sunglasses on bright days.": "Aucune protection particulière pour les activités normales ; lunettes de soleil les jours lumineux.",
  "None": "Aucune",
  "None of the methods that responded flags the lesion as suspicious. This does NOT rule out a melanoma: the tools are not clinically validated and are also wrong in this direction. If the mole is asymmetric, has irregular borders, several colours, is larger than 6 mm or has changed over time, a visit is still needed.": "Aucune des méthodes ayant répondu ne signale la lésion comme suspecte. Cela n'exclut PAS un mélanome : ces outils ne sont pas validés cliniquement et se trompent aussi dans ce sens. Si le grain de beauté est asymétrique, a des bords irréguliers, plusieurs couleurs, mesure plus de 6 mm ou a changé avec le temps, la consultation reste nécessaire.",
  "Normal photo": "Photo normale",
  "Normal photo (smartphone)": "Photo normale (smartphone)",
  "Not allowed.": "Non autorisé.",
  "Not met": "Non satisfait",
  "Not scanned yet": "Pas encore analysé",
  "Not scanned yet.": "Pas encore analysée.",
  "Not specified": "Non indiqué",
  "Notes": "Notes",
  "Notes on the mole…": "Notes sur le grain de beauté…",
  "Notes:": "Notes :",
  "Nothing is sent online, except the requests you turn on (UV weather, PubMed literature, SkinSense).": "Rien n'est envoyé en ligne, sauf les requêtes que vous activez (météo UV, littérature PubMed, SkinSense).",
  "Now": "Maintenant",
  "Number of moles": "Nombre de grains de beauté",
  "Observational study": "Étude observationnelle",
  "Of any degree of kinship.": "De n'importe quel degré de parenté.",
  "Off by default: with the other methods the photo never leaves this computer.": "Désactivé par défaut : avec les autres méthodes, la photo ne quitte jamais cet ordinateur.",
  "Often": "Souvent",
  "Olive skin. Burns little, tans easily.": "Peau mate. Brûle peu, bronze facilement.",
  "One Call {n}: {t}": "One Call {n} : {t}",
  "Only invasive primary melanomas count.": "Seuls les mélanomes primaires invasifs comptent.",
  "Open the «API keys» page of your account and copy the key.": "Ouvrez la page « API keys » de votre compte et copiez la clé.",
  "Open-Meteo (default)": "Open-Meteo (par défaut)",
  "OpenWeather key": "Clé OpenWeather",
  "OpenWeather key saved ({finale}).": "Clé OpenWeather enregistrée ({finale}).",
  "OpenWeather rejected the key (401): check that it is correct and that the 'One Call API' plan (pay per call, 1,000 free calls per day) is active on your account. After subscribing, the key can take a few minutes to activate.": "OpenWeather a refusé la clé (401) : vérifiez qu'elle est correcte et que l'abonnement « One Call API » (paiement à l'appel, 1 000 appels gratuits par jour) est actif sur votre compte. Après la souscription, la clé peut mettre quelques minutes à s'activer.",
  "OpenWeather unavailable ({e}). Showing Open-Meteo data.": "OpenWeather indisponible ({e}). Affichage des données d'Open-Meteo.",
  "OpenWeather: call limit reached (429).": "OpenWeather : limite d'appels atteinte (429).",
  "Operation not allowed on this address.": "Opération non autorisée sur cette adresse.",
  "Optional": "Facultatif",
  "Origin not allowed.": "Origine non autorisée.",
  "Original photo": "Photo originale",
  "Other": "Autre",
  "Other relatives with melanoma": "Autres parents atteints de mélanome",
  "Other skin cancers (basal cell and squamous cell carcinoma)": "Autres cancers de la peau (carcinome basocellulaire et épidermoïde)",
  "Overlay with slider": "Superposer avec curseur",
  "Page not found.": "Page introuvable.",
  "Pancreatic cancer": "Cancer du pancréas",
  "Parents, brothers, sisters, children.": "Parents, frères, sœurs, enfants.",
  "Parents, siblings or children.": "Parents, frères, sœurs ou enfants.",
  "Paste the key above and press «Test the key». After subscribing, the key can take a few minutes to activate. The program tries One Call 4.0 first and, if the key belongs to an older plan, One Call 3.0.": "Collez la clé ci-dessus et appuyez sur « Tester la clé ». Après la souscription, la clé peut mettre quelques minutes à s'activer. Le programme essaie d'abord One Call 4.0 et, si la clé correspond à un abonnement plus ancien, One Call 3.0.",
  "Paste the key first.": "Collez d'abord la clé.",
  "Paste the key here (32 letters and digits)": "Collez ici la clé (32 lettres et chiffres)",
  "People with many moles, atypical moles or a history of melanoma should protect themselves even when the index is moderate.": "Les personnes ayant beaucoup de grains de beauté, des grains de beauté atypiques ou des antécédents de mélanome doivent se protéger même lorsque l'indice est modéré.",
  "Permission denied. You can search for the city by name or use the estimate from the internet address.": "Autorisation refusée. Vous pouvez rechercher la ville par son nom ou utiliser l'estimation à partir de l'adresse internet.",
  "Personal data": "Données personnelles",
  "Personal details": "Données de la personne",
  "Personal history": "Antécédents personnels",
  "Personal melanoma and a first-degree relative with pancreatic cancer": "Mélanome personnel et parent du premier degré atteint d'un cancer du pancréas",
  "Personal picture": "Image personnelle",
  "Personal picture saved.": "Image personnelle enregistrée.",
  "Phenotype: skin, hair, eyes": "Phénotype : peau, cheveux, yeux",
  "Photo analysis": "Analyse des photos",
  "Photo date is too old.": "La date de la photo est trop ancienne.",
  "Photo deleted.": "Photo supprimée.",
  "Photo file not found.": "Fichier de la photo introuvable.",
  "Photo from {data}": "Photo du {data}",
  "Photo history": "Historique photographique",
  "Photo history ({n})": "Historique photographique ({n})",
  "Photo not found.": "Photo introuvable.",
  "Photo saved ({data}).": "Photo enregistrée ({data}).",
  "Photo saved ({data}, date read from the photo).": "Photo enregistrée ({data}, date lue dans la photo).",
  "Photo type": "Type de photo",
  "Phototype": "Phototype",
  "Phototype (Fitzpatrick classification)": "Phototype (classification de Fitzpatrick)",
  "Phototype, age and family history do not change the neural networks' result (they only look at pixels): they serve to put the risk in context.": "Le phototype, l'âge et les antécédents familiaux ne modifient pas le résultat des réseaux de neurones (qui ne regardent que les pixels) : ils servent à replacer le risque dans son contexte.",
  "Picked for you (based on profile and mole locations)": "Choisis pour vous (selon le profil et l'emplacement des grains de beauté)",
  "Picture removed.": "Image supprimée.",
  "Pillow is not installed: previews will use the original photos (install with «py -m pip install pillow»).": "Pillow n'est pas installé : les aperçus utiliseront les photos originales (installez-le avec « py -m pip install pillow »).",
  "Place a ruler or a coin next to the mole: it is used to measure the diameter.": "Placez une règle ou une pièce de monnaie à côté du grain de beauté : cela permet de mesurer le diamètre.",
  "Preparing the sheet…": "Préparation de la fiche…",
  "Press": "Appuyez sur",
  "Preview": "Aperçu",
  "Primary melanomas indicated: {mel_pers}.": "Mélanomes primaires indiqués : {mel_pers}.",
  "Print a sheet with all the moles": "Imprimer une fiche avec tous les grains de beauté",
  "Print the sheet for this mole": "Imprimer la fiche de ce grain de beauté",
  "Printed on {data} with NeoTracker": "Imprimé le {data} avec NeoTracker",
  "Profile": "Profil",
  "Profile not filled in.": "Profil non renseigné.",
  "Profile of {nome}": "Profil de {nome}",
  "Profile to complete": "Profil à compléter",
  "Projects folder:": "Dossier des projets :",
  "Protection necessary: reduce exposure between 10 and 16, SPF 30+ sunscreen, hat and sunglasses.": "Protection nécessaire : réduisez l'exposition entre 10 h et 16 h, crème solaire SPF 30+, chapeau et lunettes.",
  "Protection not needed for normal activities (beware of snow, water, altitude).": "Protection inutile pour les activités normales (attention à la neige, à l'eau, à l'altitude).",
  "Protection recommended: shade in the middle of the day, hat, sunglasses and sunscreen.": "Protection recommandée : ombre aux heures centrales, chapeau, lunettes et crème solaire.",
  "PubMed is a service of the National Library of Medicine. Abstracts are shown for personal consultation, in English; for the full text, open the article on the journal's website.": "PubMed est un service de la National Library of Medicine. Les résumés sont affichés pour consultation personnelle, en anglais ; pour le texte intégral, ouvrez l'article sur le site de la revue.",
  "PubMed is unreachable: showing the last saved search from {data}.": "PubMed est injoignable : affichage de la dernière recherche enregistrée le {data}.",
  "PubMed responded with error {code}": "PubMed a répondu par l'erreur {code}",
  "PubMed unreachable (check the internet connection)": "PubMed injoignable (vérifiez la connexion internet)",
  "PubMed {pmid} · abstract not available": "PubMed {pmid} · résumé non disponible",
  "Queued (position {n})…": "En file d'attente (position {n})…",
  "Queued…": "En file d'attente…",
  "Quit the program": "Quitter le programme",
  "R": "D",
  "R = patient's right · L = left": "D = droite du patient · G = gauche",
  "Randomised trial": "Essai randomisé",
  "Rare": "Rare",
  "Rare variants concentrated in codon 24: the family picture is indistinguishable from that of CDKN2A.": "Variants rares concentrés dans le codon 24 : le tableau familial est indiscernable de celui de CDKN2A.",
  "Re-analyse": "Réanalyser",
  "Read the abstract": "Lire le résumé",
  "Recent, relevant articles on recognising suspicious moles, on the reliability of apps and artificial intelligence, and on hereditary melanoma. Results come from PubMed, the public database of the National Library of Medicine (USA).": "Articles récents et pertinents sur la reconnaissance des grains de beauté suspects, la fiabilité des applications et de l'intelligence artificielle, et le mélanome héréditaire. Les résultats proviennent de PubMed, la base de données publique de la National Library of Medicine (États-Unis).",
  "Recognising a suspicious mole": "Reconnaître un grain de beauté suspect",
  "Red": "Roux",
  "Red or blond hair": "Cheveux roux ou blonds",
  "Refresh": "Actualiser",
  "Relatives with astrocytoma (brain tumour)": "Parents atteints d'astrocytome (tumeur du cerveau)",
  "Relatives with kidney carcinoma": "Parents atteints de carcinome du rein",
  "Relatives with melanoma of the eye (uveal)": "Parents atteints de mélanome de l'œil (uvéal)",
  "Relatives with mesothelioma": "Parents atteints de mésothéliome",
  "Relatives with pancreatic cancer (in total)": "Parents atteints d'un cancer du pancréas (au total)",
  "Remove": "Supprimer",
  "Remove the key?": "Supprimer la clé ?",
  "Rename": "Renommer",
  "Rename user": "Renommer l'utilisateur",
  "Repeat the search ignoring the saved results": "Refaire la recherche en ignorant les résultats enregistrés",
  "Request too large.": "Requête trop volumineuse.",
  "Restore": "Restaurer",
  "Review": "Revue",
  "Reviews on familial melanoma (CDKN2A, CDK4)": "Revues sur le mélanome familial (CDKN2A, CDK4)",
  "Risk factors indicated:": "Facteurs de risque indiqués :",
  "Risk factors present": "Facteurs de risque présents",
  "Role and literature": "Rôle et littérature",
  "Roughly how many moles do you have on your body?": "Environ combien de grains de beauté avez-vous sur le corps ?",
  "Same light (daylight, no flash) and same distance every time, about 10–15 cm.": "Même lumière (lumière du jour, sans flash) et même distance à chaque fois, environ 10 à 15 cm.",
  "Save": "Enregistrer",
  "Save an OpenWeather key first.": "Enregistrez d'abord une clé OpenWeather.",
  "Save mole": "Enregistrer le grain de beauté",
  "Save photo": "Enregistrer la photo",
  "Saved ✓": "Enregistré ✓",
  "Saving…": "Enregistrement…",
  "Scalp (head)": "Cuir chevelu (tête)",
  "Scan complete.": "Recherche terminée.",
  "Scan the literature": "Parcourir la littérature",
  "Scan the literature on genes": "Parcourir la littérature sur les gènes",
  "Scientific literature": "Littérature scientifique",
  "Search": "Rechercher",
  "Search for a city (e.g. Turin)": "Rechercher une ville (p. ex. Turin)",
  "Search for more (e.g. \"ugly duckling sign\", \"nail melanoma\"…)": "Rechercher autre chose (p. ex. « ugly duckling sign », « nail melanoma »…)",
  "Search the literature": "Rechercher dans la littérature",
  "Searches go from this computer to PubMed (no personal data is sent). Results are saved for 7 days.": "Les recherches partent de cet ordinateur vers PubMed (aucune donnée personnelle n'est envoyée). Les résultats sont conservés 7 jours.",
  "Searches use PubMed's public E-utilities. NCBI asks, as a courtesy, for a contact email: it is optional and is sent only to PubMed.": "Les recherches utilisent les E-utilities publiques de PubMed. Le NCBI demande, par courtoisie, une adresse e-mail de contact : elle est facultative et n'est envoyée qu'à PubMed.",
  "Searching PubMed…": "Recherche sur PubMed…",
  "Searching…": "Recherche…",
  "Section {n} of {tot}…": "Section {n} sur {tot}…",
  "Sections": "Sections",
  "Send the photos to SkinSense?": "Envoyer les photos à SkinSense ?",
  "Sequential photography and monitoring of moles over time": "Photographie séquentielle et suivi des grains de beauté au fil du temps",
  "Settings": "Paramètres",
  "Several colours in the same mole (brown, black, red, blue, white).": "Plusieurs couleurs dans le même grain de beauté (marron, noir, rouge, bleu, blanc).",
  "Sex": "Sexe",
  "Shade, clothing, a hat and sunscreen are needed in the middle of the day.": "Ombre, vêtements, chapeau et crème solaire sont nécessaires aux heures centrales.",
  "Sheet for the dermatologist": "Fiche pour le dermatologue",
  "Shoulder blade area, left": "Région scapulaire gauche",
  "Shoulder blade area, right": "Région scapulaire droite",
  "Shoulder, left": "Épaule gauche",
  "Shoulder, right": "Épaule droite",
  "Show side by side": "Afficher côte à côte",
  "Show the whole body": "Afficher tout le corps",
  "Showing {n} photos out of {tot}.": "{n} photos affichées sur {tot}.",
  "Significant risk factors are present: periodic dermatological check-ups (the dermatologist decides how often) and regular skin self-examination are recommended.": "Des facteurs de risque importants sont présents : un contrôle dermatologique périodique (la fréquence est fixée par le dermatologue) et un autoexamen régulier de la peau sont conseillés.",
  "Simplified criteria, for information only. Genetic testing concerns a small minority of people and is not a routine examination: it is up to the specialist to decide whether and which test to offer, usually after genetic counselling and, when possible, starting from a relative who has had the disease.": "Critères simplifiés, à titre d'information. Le test génétique ne concerne qu'une petite minorité de personnes et n'est pas un examen de routine : c'est au spécialiste de décider si et quel test proposer, en général après une consultation de génétique et, si possible, en partant d'un parent atteint.",
  "Site": "Zone",
  "Site (editable)": "Zone (modifiable)",
  "Skin self-examination": "Autoexamen de la peau",
  "Skin that burns easily and tans little.": "Peau qui brûle facilement et bronze peu.",
  "SkinSense (online service)": "SkinSense (service en ligne)",
  "SkinSense is a third-party online service: the photos of your moles would be sent over the internet to a server we do not control. The photos are data about your health. Do you want to enable it?": "SkinSense est un service en ligne tiers : les photos de vos grains de beauté seraient envoyées par internet à un serveur que nous ne contrôlons pas. Les photos sont des données de santé. Voulez-vous l'activer ?",
  "SkinSense is on: the photo (without metadata) will be sent to an online service.": "SkinSense est activé : la photo (sans métadonnées) sera envoyée à un service en ligne.",
  "SkinSense turned off.": "SkinSense désactivé.",
  "SkinSense turned on.": "SkinSense activé.",
  "Smartphone apps and skin cancer risk: diagnostic accuracy": "Applications pour smartphone et risque de cancer de la peau : précision diagnostique",
  "Some risk factors are present: careful sun protection and regular self-examination; a basic dermatological check-up is a good habit.": "Certains facteurs de risque sont présents : protection solaire rigoureuse et autoexamen régulier ; un contrôle dermatologique de base est une bonne habitude.",
  "Something went wrong": "Quelque chose n'a pas fonctionné",
  "Sometimes": "Parfois",
  "Source:": "Source :",
  "Sources": "Sources",
  "Subscribe to the pay-per-call «One Call API» plan": "Souscrivez à l'abonnement « One Call API » payant à l'appel",
  "Sun exposure": "Exposition au soleil",
  "Sunbeds": "Cabines de bronzage",
  "Sunburns": "Coups de soleil",
  "Sunburns with blisters (especially as a child or teenager)": "Coups de soleil avec cloques (surtout dans l'enfance ou l'adolescence)",
  "Switch user": "Changer d'utilisateur",
  "Syndromic": "Syndromique",
  "Systematic review": "Revue systématique",
  "Tanning lamps": "Lampes à bronzer",
  "Tanning lamps or sunbeds": "Lampes ou cabines de bronzage",
  "Telomerase: promoter variants described in families with melanoma.": "Télomérase : variants du promoteur décrits dans des familles atteintes de mélanome.",
  "Telomere gene (shelterin complex): rare variants in families with melanoma.": "Gène des télomères (complexe shelterin) : variants rares dans des familles atteintes de mélanome.",
  "Telomere gene: rare variants in some families with melanoma.": "Gène des télomères : variants rares dans certaines familles atteintes de mélanome.",
  "Test the key": "Tester la clé",
  "Testing the key…": "Test de la clé…",
  "The Open-Meteo service is not responding ({e}).": "Le service Open-Meteo ne répond pas ({e}).",
  "The OpenWeather key contains invalid characters (it is usually 32 letters/digits).": "La clé OpenWeather contient des caractères non valides (elle comporte généralement 32 lettres/chiffres).",
  "The Pillow library is old and has known security problems: update it with «py -m pip install -U pillow».": "La bibliothèque Pillow est ancienne et présente des failles de sécurité connues : mettez-la à jour avec « py -m pip install -U pillow ».",
  "The WHO recommends protection from a UV index of 3.": "L'OMS recommande de se protéger à partir d'un indice UV de 3.",
  "The analysis did not produce the report. Last lines of the log: {log}": "L'analyse n'a pas produit le rapport. Dernières lignes du journal : {log}",
  "The analysis failed.": "L'analyse a échoué.",
  "The articles are chosen by an automatic search and have not been assessed by NeoTracker: read them with your doctor.": "Les articles sont choisis par une recherche automatique et n'ont pas été évalués par NeoTracker : lisez-les avec votre médecin.",
  "The choice applies to all users of this computer. The original and binding text of the legal notices is the English one; the full text report stays in English.": "Ce choix vaut pour tous les utilisateurs de cet ordinateur. Le texte original et juridiquement contraignant des avertissements est le texte anglais ; le rapport texte complet reste en anglais.",
  "The computer cannot determine the position. Search for the city by name.": "L'ordinateur ne parvient pas à déterminer la position. Recherchez la ville par son nom.",
  "The data entered meet at least one criterion described in the literature. We advise you to talk about it with your dermatologist or a medical geneticist (oncological genetic counselling): the specialist will decide whether and which test to offer, usually after counselling and, when possible, starting from an affected relative. Genes most cited by the guidelines: {geni}. The use of multigene panels is still under discussion among specialists: that is why counselling before the test matters.": "Les données saisies répondent à au moins un critère décrit dans la littérature. Nous vous conseillons d'en parler avec votre dermatologue ou un médecin généticien (consultation de génétique oncologique) : c'est le spécialiste qui décidera si et quel test proposer, en général après la consultation et, si possible, en partant d'un parent atteint. Gènes les plus cités par les recommandations : {geni}. L'utilisation des panels multigéniques fait encore débat entre spécialistes : c'est pourquoi la consultation avant le test est importante.",
  "The file is empty.": "Le fichier est vide.",
  "The file is not a readable image or is too large.": "Le fichier n'est pas une image lisible ou est trop volumineux.",
  "The file is not a readable image, is damaged or has too many pixels (maximum {mp} megapixels).": "Le fichier n'est pas une image lisible, est endommagé ou comporte trop de pixels (maximum {mp} mégapixels).",
  "The file is too large (maximum 40 MB).": "Le fichier est trop volumineux (maximum 40 Mo).",
  "The first analysis can take several minutes (the models are loaded into memory).": "La première analyse peut prendre plusieurs minutes (les modèles sont chargés en mémoire).",
  "The image exceeds {mb} MB.": "L'image dépasse {mb} Mo.",
  "The index is a forecast: the actual value depends on clouds, altitude and reflections.": "L'indice est une prévision : la valeur réelle dépend des nuages, de l'altitude et des réflexions.",
  "The information on risk, literature and genetics is for general information and does not replace the advice of a doctor or geneticist.": "Les informations sur le risque, la littérature et la génétique sont données à titre informatif et ne remplacent pas l'avis d'un médecin ou d'un généticien.",
  "The key stays saved only on your computer and is never shown to, or sent to, the program's web page: the Python program uses it to call OpenWeather.": "La clé reste enregistrée uniquement sur votre ordinateur et n'est jamais affichée ni envoyée à la page web du programme : c'est le programme Python qui l'utilise pour appeler OpenWeather.",
  "The key will be deleted from this computer. You can enter it again whenever you want.": "La clé sera supprimée de cet ordinateur. Vous pourrez la saisir à nouveau quand vous voulez.",
  "The location is saved only on this computer; it is sent to the weather service (rounded coordinates) to get the UV index.": "La position est enregistrée uniquement sur cet ordinateur ; elle est envoyée au service météo (coordonnées arrondies) pour obtenir l'indice UV.",
  "The methods are trained on photographs different from yours: changing light, distance or camera can change the answer.": "Les méthodes sont entraînées sur des photographies différentes des vôtres : changer d'éclairage, de distance ou d'appareil peut modifier la réponse.",
  "The middle hours of the day (about 11–16) have the highest index.": "Les heures centrales (environ 11 h-16 h) sont celles où l'indice est le plus élevé.",
  "The most studied genes": "Les gènes les plus étudiés",
  "The name": "Le nom",
  "The number of moles is one of the strongest risk factors.": "Le nombre de grains de beauté est l'un des facteurs de risque les plus forts.",
  "The numbers match the following sheets. In the figure: the front view on the left, the back view on the right.": "Les numéros correspondent aux fiches suivantes. Sur la figure : la vue de face à gauche, la vue de dos à droite.",
  "The p.E318K variant increases the risk of melanoma and renal carcinoma and is associated with many moles.": "Le variant p.E318K augmente le risque de mélanome et de carcinome rénal et s'associe à de nombreux grains de beauté.",
  "The photo date cannot be in the future.": "La date de la photo ne peut pas être dans le futur.",
  "The photo exceeds {MAX_MB_FOTO} MB.": "La photo dépasse {MAX_MB_FOTO} Mo.",
  "The photo exceeds {mb} MB: reduce it or choose another one.": "La photo dépasse {mb} Mo : réduisez-la ou choisissez-en une autre.",
  "The photo from {data} and its analysis report will be deleted permanently.": "La photo du {data} et son rapport d'analyse seront supprimés définitivement.",
  "The photo stays on your computer: SkinSense (online service) is turned off.": "La photo reste sur votre ordinateur : SkinSense (service en ligne) est désactivé.",
  "The profile, all moles, all photos and all reports of this user will be deleted permanently. This cannot be undone.": "Le profil, tous les grains de beauté, toutes les photos et tous les rapports de cet utilisateur seront supprimés définitivement. Cette opération est irréversible.",
  "The program will shut down. An analysis in progress will be interrupted. Your data stays saved.": "Le programme va s'arrêter. Une analyse en cours sera interrompue. Vos données restent enregistrées.",
  "The result also concerns blood relatives: that is why counselling before and after the test is part of the process.": "Le résultat concerne aussi les parents du même sang : c'est pourquoi la consultation avant et après le test fait partie du parcours.",
  "The results are experimental estimates and can be wrong in both directions: a reassuring result does not rule out a melanoma, and a result flagging attention does not mean there is one.": "Les résultats sont des estimations expérimentales et peuvent se tromper dans les deux sens : un résultat rassurant n'exclut pas un mélanome, un résultat d'alerte ne signifie pas qu'il y en a un.",
  "The two halves of the mole do not look alike.": "Les deux moitiés du grain de beauté ne se ressemblent pas.",
  "The view must be 'fronte' or 'retro'.": "La vue doit être 'fronte' ou 'retro'.",
  "The «picked for you» sections use words linked to your profile (for example phototype or number of moles): if you prefer not to send them, do not scan that section.": "Les sections « choisies pour vous » utilisent des mots liés à votre profil (par exemple le phototype ou le nombre de grains de beauté) : si vous préférez ne pas les envoyer, ne lancez pas l'analyse de cette section.",
  "The «ugly duckling» also counts: a mole that looks different from all the others. Nodules that grow quickly or feel hard to the touch should be shown straight away. This reminder does not replace a medical visit.": "Le « vilain petit canard » compte aussi : un grain de beauté différent de tous les autres. Les nodules qui grossissent rapidement ou sont durs au toucher doivent être montrés sans attendre. Ce rappel ne remplace pas une consultation.",
  "There are no moles to print.": "Il n'y a aucun grain de beauté à imprimer.",
  "These are measurements you entered: they are valid if always taken the same way. A mole that grows or changes is a good reason to show it to your dermatologist; the 6 mm line is just the classic reference of the ABCDE criteria.": "Ce sont des mesures saisies par vous : elles sont valables si elles sont toujours prises de la même manière. Un grain de beauté qui grossit ou change est une bonne raison de le montrer au dermatologue ; la ligne à 6 mm n'est que la référence classique des critères ABCDE.",
  "They do not change the result of the neural networks, which only look at the pixels of the photo. They are used to: (1) put the risk in context, (2) choose the scientific literature suited to you, (3) check the criteria for genetic counselling, (4) calculate how long you can stay in the sun before burning. Everything stays on your computer.": "Elles ne modifient pas le résultat des réseaux de neurones, qui ne regardent que les pixels de la photo. Elles servent à : (1) replacer le risque dans son contexte, (2) choisir la littérature scientifique adaptée à vous, (3) vérifier les critères de consultation de génétique, (4) calculer combien de temps vous pouvez rester au soleil avant de brûler. Tout reste sur votre ordinateur.",
  "Thigh, left": "Cuisse gauche",
  "Thigh, right": "Cuisse droite",
  "Thin clouds do not stop much of the UV: the index can stay high even with a hazy sky.": "Les nuages fins n'arrêtent pas une grande partie des UV : l'indice peut rester élevé même par ciel voilé.",
  "This browser does not offer geolocation: search for the city by name.": "Ce navigateur ne propose pas la géolocalisation : recherchez la ville par son nom.",
  "This is a cautious estimate that uses the lowest minimal erythema dose for your phototype; with reflections (water, snow, sand), altitude or already reddened skin the time is shorter.": "Il s'agit d'une estimation prudente qui utilise la dose érythémale minimale la plus basse de votre phototype ; avec des réflexions (eau, neige, sable), l'altitude ou une peau déjà rougie, le temps est plus court.",
  "This method sends the pixels of the photo (not the metadata) to an external server.": "Cette méthode envoie les pixels de la photo (et non les métadonnées) à un serveur externe.",
  "This photo has not been analysed yet. The analysis compares several methods on the same image and tells you what each one answered.": "Cette photo n'a pas encore été analysée. L'analyse compare plusieurs méthodes sur la même image et vous indique ce que chacune a répondu.",
  "This photo is being analysed: wait for it to finish.": "L'analyse de cette photo est en cours : attendez qu'elle se termine.",
  "This program helps you keep track of your moles over time: you mark them on a body map, keep their photos with the date and have them analysed by several methods. Start by creating your user.": "Ce programme vous aide à suivre vos grains de beauté dans le temps : vous les placez sur une carte du corps, vous conservez leurs photos avec la date et vous les faites analyser par plusieurs méthodes. Commencez par créer votre utilisateur.",
  "This report is NOT a diagnosis. The programs used are research prototypes, not medical devices.": "Ce rapport n'est PAS un diagnostic. Les programmes utilisés sont des prototypes de recherche, pas des dispositifs médicaux.",
  "This sheet collects data entered by the person and photos taken by them. The results of the automatic analysis are experimental, are not a diagnosis and do not replace a dermatological visit or dermoscopy.": "Cette fiche rassemble des données saisies par la personne et des photos prises par elle. Les résultats de l'analyse automatique sont expérimentaux, ne constituent pas un diagnostic et ne remplacent pas la consultation dermatologique ni la dermoscopie.",
  "Thresholds and colours of the WHO international scale. Sources:": "Seuils et couleurs de l'échelle internationale de l'OMS. Sources :",
  "Time to re-photograph?": "Faut-il refaire une photo ?",
  "To close NeoTracker, just close this window with the X at the top right: the program shuts down by itself.": "Pour fermer NeoTracker, il suffit de fermer cette fenêtre avec la croix en haut à droite : le programme s'arrête tout seul.",
  "To confirm, type:": "Pour confirmer, saisissez :",
  "To delete, type the exact name of the user in the confirmation.": "Pour supprimer, saisissez le nom exact de l'utilisateur dans la confirmation.",
  "To estimate the city, the program contacts the free service ipwho.is, which sees your internet address. Accuracy is at city level (it is sometimes wrong). Proceed?": "Pour estimer la ville, le programme contacte le service gratuit ipwho.is, qui voit votre adresse internet. La précision est celle de la ville (il se trompe parfois). Continuer ?",
  "To see how much sun burns you, enter your phototype in the": "Pour voir combien de temps de soleil vous fait brûler, indiquez votre phototype dans le",
  "Today's UV index": "Indice UV du jour",
  "Today's maximum": "Maximum d'aujourd'hui",
  "Too many open connections.": "Trop de connexions ouvertes.",
  "Total diagnoses entered: {diagnosi}. Leachman 2009 counts melanoma and pancreatic cancer in 1st- and 2nd-degree relatives on the same side of the family; astrocytoma is included by the NCCN guidelines.": "Nombre total de diagnostics indiqués : {diagnosi}. Leachman 2009 retient le mélanome et le cancer du pancréas chez les parents du 1er et du 2e degré du même côté de la famille ; l'astrocytome est inclus par les recommandations du NCCN.",
  "Try again": "Réessayer",
  "Type": "Type",
  "Type a name.": "Saisissez un nom.",
  "Type at least 3 characters.": "Saisissez au moins 3 caractères.",
  "Type {n}": "Type {n}",
  "UV index": "Indice UV",
  "UV index not available": "Indice UV indisponible",
  "UV index source changed.": "Source de l'indice UV modifiée.",
  "UV index: data source": "Indice UV : source des données",
  "UV rays are harmful to unprotected skin today": "Les rayons UV sont nocifs aujourd'hui pour une peau non protégée",
  "UV rays are low today": "Les rayons UV sont faibles aujourd'hui",
  "UV rays are very harmful today": "Les rayons UV sont très nocifs aujourd'hui",
  "Ultraviolet rays are the main modifiable risk factor for melanoma. Here you can see how strong they are today where you are.": "Les rayons ultraviolets sont le principal facteur de risque modifiable du mélanome. Vous voyez ici leur intensité aujourd'hui là où vous vous trouvez.",
  "Unauthorised access.": "Accès non autorisé.",
  "Unauthorised request.": "Requête non autorisée.",
  "Unexpected error: {e}": "Erreur inattendue : {e}",
  "Unknown address.": "Adresse inconnue.",
  "Unknown section.": "Section inconnue.",
  "Unsaved changes…": "Modifications non enregistrées…",
  "Unsupported format: JPG, PNG, WEBP or BMP are required.": "Format non pris en charge : JPG, PNG, WEBP ou BMP requis.",
  "Unsupported format: JPG, PNG, WEBP or BMP are required. iPhone HEIC photos must be converted to JPG (camera settings: 'Most Compatible').": "Format non pris en charge : JPG, PNG, WEBP ou BMP requis. Les photos HEIC des iPhone doivent être converties en JPG (réglages de l'appareil photo : « Le plus compatible »).",
  "Upper abdomen, left": "Haut de l'abdomen gauche",
  "Upper abdomen, right": "Haut de l'abdomen droit",
  "Use of tanning lamps or sunbeds": "Usage de lampes ou de cabines de bronzage",
  "Use the date written in the photo, if there is one": "Utiliser la date inscrite dans la photo, si elle existe",
  "User created. Fill in the profile: it helps put the results in context.": "Utilisateur créé. Renseignez le profil : il sert à contextualiser les résultats.",
  "User deleted.": "Utilisateur supprimé.",
  "User not found.": "Utilisateur introuvable.",
  "Version": "Version",
  "Very dark skin. Does not burn.": "Peau très foncée. Ne brûle pas.",
  "Very fair skin. Always burns, never tans (often red hair, freckles).": "Peau très claire. Brûle toujours, ne bronze jamais (souvent cheveux roux, taches de rousseur).",
  "Very high": "Très élevé",
  "WHO/WMO/UNEP/ICNIRP - Global Solar UV Index: A Practical Guide (2002)": "OMS/OMM/PNUE/ICNIRP - Global Solar UV Index: A Practical Guide (2002)",
  "Warning: I did not find App 1's .venv environment; using the current Python.": "Attention : l'environnement .venv de l'App 1 est introuvable ; j'utilise le Python actuel.",
  "Weather and UV data:": "Données météo et UV :",
  "Welcome to NeoTracker": "Bienvenue dans NeoTracker",
  "What is this information used for?": "À quoi servent ces informations ?",
  "What to do": "Que faire",
  "What to know before a genetic test": "À savoir avant un test génétique",
  "Wheel = zoom · drag = move · double click = enlarge": "Molette = zoom · glisser = déplacer · double clic = agrandir",
  "When you noticed it, whether it itches, whether it has changed…": "Quand vous l'avez remarqué, s'il démange, s'il a changé…",
  "When you subscribe, the default daily limit is 2,000 calls: in the «Billing plans» tab of your account you can lower it to 1,000, so you spend nothing. NeoTracker uses very few (at most 4 every 10 minutes, only when you open the UV Index page).": "À la souscription, la limite quotidienne par défaut est de 2 000 appels : dans l'onglet « Billing plans » de votre compte, vous pouvez la ramener à 1 000 pour ne rien dépenser. NeoTracker en utilise très peu (au maximum 4 toutes les 10 minutes, uniquement lorsque vous ouvrez la page Indice UV).",
  "Where they are": "Où ils se trouvent",
  "Who are you?": "Qui êtes-vous ?",
  "With or without a test, for people with a family history, sun protection, skin self-examination and regular dermatological check-ups remain essential.": "Avec ou sans test, pour les personnes ayant des antécédents familiaux, la protection solaire, l'autoexamen de la peau et les contrôles dermatologiques réguliers restent essentiels.",
  "With the data entered you do not meet the most commonly used criteria. Genetic testing for melanoma is indicated only in a small minority of people and is not offered routinely. If your family history changes or you have doubts, update your profile and talk to your dermatologist.": "Avec les données saisies, vous ne remplissez pas les critères les plus utilisés. Le test génétique pour le mélanome n'est indiqué que chez une petite minorité de personnes et n'est pas proposé en routine. Si vos antécédents familiaux changent ou si vous avez des doutes, mettez votre profil à jour et parlez-en à votre dermatologue.",
  "With the data entered, no known risk factors appear. Complete your profile if information is missing.": "Avec les données saisies, aucun facteur de risque connu n'apparaît. Complétez votre profil s'il manque des informations.",
  "With your phototype ({fototipo})": "Avec votre phototype ({fototipo})",
  "Without Pillow the image must be a JPG/PNG under 400 KB (the page reduces it by itself: try again with the 'Choose image' function).": "Sans Pillow, l'image doit être un JPG/PNG de moins de 400 Ko (la page la réduit toute seule : réessayez avec la fonction « Choisir une image »).",
  "Woman": "Femme",
  "Work or prolonged activity outdoors": "Travail ou activité prolongée en plein air",
  "Yes": "Oui",
  "Yes, enable": "Oui, activer",
  "Yes, estimate the city": "Oui, estimer la ville",
  "Yes, negative": "Oui, négatif",
  "Yes, positive": "Oui, positif",
  "Yes, uninformative": "Oui, non informatif",
  "You can close this window. To reopen the program, use the «NeoTracker» icon on the Desktop.": "Vous pouvez fermer cette fenêtre. Pour rouvrir le programme, utilisez l'icône « NeoTracker » du Bureau.",
  "You can keep using the app. If you close the window the analysis is not lost: the program finishes the work and then shuts down by itself.": "Vous pouvez continuer à utiliser l'application. Si vous fermez la fenêtre, l'analyse n'est pas perdue : le programme termine le travail puis s'arrête tout seul.",
  "You can use your own photo, a drawing or an icon. The image is cropped to a square and reduced, stays only on this computer and is never used for mole analysis.": "Vous pouvez utiliser une photo de vous, un dessin ou une icône. L'image est recadrée en carré et réduite, reste uniquement sur cet ordinateur et n'est jamais utilisée pour l'analyse des grains de beauté.",
  "You chose OpenWeather but the key is missing (Settings): showing Open-Meteo data.": "Vous avez choisi OpenWeather mais la clé est absente (Paramètres) : affichage des données d'Open-Meteo.",
  "You chose OpenWeather but there is no key yet: until one is added, the program uses Open-Meteo.": "Vous avez choisi OpenWeather mais il n'y a pas encore de clé : tant qu'elle manque, le programme utilise Open-Meteo.",
  "You said you have already had a genetic test: take the report to your dermatologist.": "Vous avez indiqué avoir déjà fait un test génétique : apportez le compte rendu à votre dermatologue.",
  "Your data (including health data) stays on this computer. Only the requests you turn on leave it: UV index (approximate coordinates), PubMed searches (only the search terms) and, only if you enable it, sending the photo to SkinSense.": "Vos données (y compris de santé) restent sur cet ordinateur. Seules les requêtes que vous activez en sortent : indice UV (coordonnées approximatives), recherches sur PubMed (uniquement les termes recherchés) et, seulement si vous l'activez, l'envoi de la photo à SkinSense.",
  "Your data against the criteria": "Vos données au regard des critères",
  "Your moles ({n})": "Vos grains de beauté ({n})",
  "Zoom out": "Réduire",
  "a few": "peu",
  "a few freckles": "peu d'éphélides",
  "about {minuti} minutes": "environ {minuti} minutes",
  "actinic keratosis, a pre-cancerous lesion": "kératose actinique, lésion précancéreuse",
  "active only if you enable it below": "actif seulement si vous l'activez ci-dessous",
  "address not allowed (https only)": "adresse non autorisée (https uniquement)",
  "all methods with a result flag a mole that needs attention": "toutes les méthodes ayant un résultat signalent un grain de beauté à surveiller",
  "and click on the exact spot on the body (zoom in with the wheel to be more precise).": "et cliquez sur l'endroit exact du corps (zoomez avec la molette pour être plus précis).",
  "and confirm the email.": "et confirmez l'e-mail.",
  "average of {n} models; mean score {media} (threshold 0)": "moyenne de {n} modèles ; score moyen {media} (seuil 0)",
  "back": "dos",
  "back of the hand": "dos de la main",
  "basal cell carcinoma, a skin cancer": "carcinome basocellulaire, cancer de la peau",
  "between the fingers or toes": "entre les doigts ou les orteils",
  "black hair": "cheveux noirs",
  "blond hair": "cheveux blonds",
  "blue or grey eyes": "yeux bleus ou gris",
  "brown hair": "cheveux châtains",
  "cannot start: {e}": "impossible de démarrer : {e}",
  "confidence {perc}": "confiance {perc}",
  "connection failed: {motivo}": "connexion impossible : {motivo}",
  "dark eyes": "yeux foncés",
  "dermoscopic": "dermoscopique",
  "dermoscopy": "dermoscopie",
  "don't know": "ne sait pas",
  "e.g. 4.5": "p. ex. 4,5",
  "ear": "oreille",
  "eyelid": "paupière",
  "fewer than 25": "moins de 25",
  "free, no account or key needed": "gratuite, sans compte ni clé",
  "front": "face",
  "green eyes": "yeux verts",
  "grey or white hair": "cheveux gris ou blancs",
  "in clear skies and without protection, at today's peak the skin may redden in": "par ciel dégagé et sans protection, au pic d'aujourd'hui la peau peut rougir en",
  "in the panel": "dans le panel",
  "in {n} day.": "en {n} jour.",
  "in {n} days.": "en {n} jours.",
  "invalid response from the service": "réponse non valide du service",
  "lip": "lèvre",
  "location from internet address not available": "position à partir de l'adresse internet indisponible",
  "man": "homme",
  "many": "beaucoup",
  "many freckles": "beaucoup d'éphélides",
  "melanoma": "mélanome",
  "melanoma detected": "mélanome détecté",
  "melanoma not detected": "mélanome non détecté",
  "melanoma prob. {perc}": "prob. de mélanome {perc}",
  "naevus, i.e. a benign mole": "naevus, c'est-à-dire grain de beauté bénin",
  "name@example.com (optional)": "nom@exemple.fr (facultatif)",
  "never": "jamais",
  "no": "non",
  "no cases indicated": "aucun cas indiqué",
  "no freckles": "aucune éphélide",
  "no method flagged the mole (this does not rule out a melanoma)": "aucune méthode n'a signalé le grain de beauté (cela n'exclut pas un mélanome)",
  "no result available": "aucun résultat disponible",
  "normal photo": "photo normale",
  "often": "souvent",
  "optional: requires a personal key of your own": "facultative : nécessite une clé personnelle",
  "other": "autre",
  "output interpreted as the 6 skin classes (not verifiable)": "sortie interprétée comme les 6 classes de peau (non vérifiable)",
  "over 2 hours (very low UV)": "plus de 2 heures (UV très faible)",
  "palm of the hand": "paume de la main",
  "phototype {tipo}": "phototype {tipo}",
  "probability of malignancy estimated by the model: {pm}": "probabilité de malignité estimée par le modèle : {pm}",
  "red hair": "cheveux roux",
  "response too large": "réponse trop volumineuse",
  "response without a lesion name: {risposta}": "réponse sans nom de lésion : {risposta}",
  "scalp": "cuir chevelu",
  "seborrhoeic keratosis, benign": "kératose séborrhéique, bénigne",
  "service address not allowed (https required)": "adresse du service non autorisée (https requis)",
  "service page": "page du service",
  "service unreachable: {ultimo_errore}": "service injoignable : {ultimo_errore}",
  "significant": "important",
  "skin photos": "photos de peau",
  "sole of the foot": "plante du pied",
  "sometimes": "parfois",
  "squamous cell carcinoma, a skin cancer": "carcinome épidermoïde, cancer de la peau",
  "stopped after {minuti} minutes (maximum time)": "interrompu après {minuti} minutes (durée maximale)",
  "studies on PubMed": "études sur PubMed",
  "the App 1 models have not been downloaded: they are still Git LFS placeholders. Open PowerShell in the folder {cartella}, run 'git lfs pull', then try again.": "les modèles de l'App 1 n'ont pas été téléchargés : ce sont encore des fichiers de substitution Git LFS. Ouvrez PowerShell dans le dossier {cartella}, lancez « git lfs pull », puis réessayez.",
  "the first 1,000 calls per day are free, later ones are charged. OpenWeather may ask for a payment card to activate it: check the conditions on their website.": "les 1 000 premiers appels par jour sont gratuits, les suivants sont payants. OpenWeather peut demander une carte de paiement pour l'activer : vérifiez les conditions sur leur site.",
  "the methods do not agree with each other": "les méthodes ne sont pas d'accord entre elles",
  "the model has {n} outputs: meaning unknown": "le modèle a {n} sorties : signification inconnue",
  "the photo does not open as an image ({tipo}): {dettaglio}": "la photo ne s'ouvre pas comme une image ({tipo}) : {dettaglio}",
  "the trained weights are missing: in the folder {cartella} there are no files model_fold_0.bin ... model_fold_4.bin. The repository does not contain them: they must be produced with train.py on the SIIM-ISIC dataset.": "les poids entraînés sont absents : dans le dossier {cartella}, il n'y a pas les fichiers model_fold_0.bin ... model_fold_4.bin. Le dépôt ne les contient pas : ils doivent être produits avec train.py sur le jeu de données SIIM-ISIC.",
  "timed out or network unavailable": "délai dépassé ou réseau indisponible",
  "today": "aujourd'hui",
  "top of the foot": "dessus du pied",
  "ukalwa / melanoma-detection (Android app)": "ukalwa / melanoma-detection (application Android)",
  "under the nail (foot)": "sous l'ongle (pied)",
  "under the nail (hand)": "sous l'ongle (main)",
  "unreadable response: {e}": "réponse illisible : {e}",
  "updated": "mis à jour",
  "vatsal30 / Melanoma-Detection (PyTorch)": "vatsal30 / Melanoma-Detection (PyTorch)",
  "woman": "femme",
  "yes": "oui",
  "yes, negative": "oui, négatif",
  "yes, positive": "oui, positif",
  "yes, uninformative": "oui, non informatif",
  "yesterday": "hier",
  "{avviso} The Open-Meteo service is not responding ({e}).": "{avviso} Le service Open-Meteo ne répond pas ({e}).",
  "{cosa} cannot be empty.": "{cosa} ne peut pas être vide.",
  "{cosa} is too long (maximum {massimo} characters).": "{cosa} est trop long (maximum {massimo} caractères).",
  "{file_modello} is still a Git LFS placeholder: run 'git lfs pull' in the folder {cartella}.": "{file_modello} est encore un fichier de substitution Git LFS : lancez « git lfs pull » dans le dossier {cartella}.",
  "{file_pesi} is still a Git LFS placeholder: open PowerShell in the folder {cartella} and run 'git lfs pull'.": "{file_pesi} est encore un fichier de substitution Git LFS : ouvrez PowerShell dans le dossier {cartella} et lancez « git lfs pull ».",
  "{foto} · last {quando}": "{foto} · dernière {quando}",
  "{giorno} at {ora}: UV index {uvi} ({categoria})": "{giorno} à {ora} : indice UV {uvi} ({categoria})",
  "{nome} · {mb} MB · click to change": "{nome} · {mb} Mo · cliquez pour changer",
  "{nome}: enter a number.": "{nome} : saisissez un nombre.",
  "{nome}: error.": "{nome} : erreur.",
  "{nome}: not available.": "{nome} : non disponible.",
  "{nome}: the value must be between {minimo} and {massimo}.": "{nome} : la valeur doit être comprise entre {minimo} et {massimo}.",
  "{n} articles found on PubMed · search of {data}": "{n} articles trouvés sur PubMed · recherche du {data}",
  "{n} articles found on PubMed · search of {data} (saved)": "{n} articles trouvés sur PubMed · recherche du {data} (enregistrée)",
  "{n} articles on melanoma and «{termine}»": "{n} articles sur le mélanome et « {termine} »",
  "{n} day": "{n} jour",
  "{n} day has passed between the two photos.": "{n} jour s'est écoulé entre les deux photos.",
  "{n} days": "{n} jours",
  "{n} days ago": "il y a {n} jours",
  "{n} days have passed between the two photos.": "{n} jours se sont écoulés entre les deux photos.",
  "{n} first-degree relative(s) with melanoma": "{n} parent(s) du premier degré atteint(s) de mélanome",
  "{n} model files out of 10": "{n} fichiers de modèle sur 10",
  "{n} model files out of 5": "{n} fichiers de modèle sur 5",
  "{n} mole": "{n} grain de beauté",
  "{n} mole on this sheet": "{n} grain de beauté sur cette fiche",
  "{n} moles": "{n} grains de beauté",
  "{n} moles on this sheet": "{n} grains de beauté sur cette fiche",
  "{n} months ago": "il y a {n} mois",
  "{n} of {tot} methods responded": "{n} méthodes sur {tot} ont répondu",
  "{n} of {tot}: {et}": "{n} sur {tot} : {et}",
  "{n} other relative(s) with melanoma": "{n} autre(s) parent(s) atteint(s) de mélanome",
  "{n} photo": "{n} photo",
  "{n} photos": "{n} photos",
  "{n} photos in {giorni} (from {da} to {a}).": "{n} photos en {giorni} (du {da} au {a}).",
  "{n} with astrocytoma": "{n} atteint(s) d'astrocytome",
  "{n} with pancreatic cancer": "{n} atteint(s) d'un cancer du pancréas",
  "{n} with uveal melanoma": "{n} atteint(s) de mélanome uvéal",
  "{n} year": "{n} an",
  "{n} year ago": "il y a {n} an",
  "{n} years": "{n} ans",
  "{n} years ago": "il y a {n} ans",
  "{vista} · position {x}% from the left, {y}% from the top": "{vista} · position {x} % depuis la gauche, {y} % depuis le haut",
  "…of which 1st-degree": "…dont du 1er degré",
  "← All moles": "← Tous les grains de beauté"
};
'''
WEB_FILES["/i18n_fr.js"] = ("text/javascript; charset=utf-8", _WEB_I18N_FR_JS.encode("utf-8"))

_WEB_I18N_IT_JS = r'''/* NeoTracker interface translations: it. Key = the English source text.
   Keep the {name} placeholders unchanged. Check: python3 tools/traduzioni.py */
(window.NT_DIZIONARI = window.NT_DIZIONARI || {}).it = {
  "(CC BY 4.0 licence). The free service is for personal, non-commercial use.": "(licenza CC BY 4.0). Il servizio gratuito è per uso personale e non commerciale.",
  "(empty)": "(vuoto)",
  "(local time at the location)": "(ora locale del luogo)",
  "(saved search from {data})": "(ricerca salvata del {data})",
  "(untitled)": "(senza titolo)",
  "({variazione} mm since the previous photo)": "({variazione} mm dalla foto precedente)",
  "1 photo from {data}, diameter {mm} mm.": "1 foto del {data}, diametro {mm} mm.",
  "1 photo from {data}.": "1 foto del {data}.",
  "100 or more": "100 o più",
  "100 or more moles on the body": "100 o più nei sul corpo",
  "1st-degree relatives with melanoma": "Parenti di 1° grado con melanoma",
  "3 = WHO recommends protection from this level": "3 = da qui l'OMS consiglia protezione",
  "3 or more primary melanomas in the same person": "3 o più melanomi primari nella stessa persona",
  "50 to 99 moles on the body": "Da 50 a 99 nei sul corpo",
  "A few": "Poche",
  "A mole that changes (shape, borders, colour, size), bleeds, itches or worries you must be shown to a dermatologist, whatever the app says. Regular check-ups with the dermatologist remain irreplaceable.": "Un neo che cambia (forma, bordi, colore, dimensioni), sanguina, prude o ti preoccupa va mostrato a un dermatologo, qualunque cosa dica l'app. Il controllo periodico dal dermatologo resta insostituibile.",
  "A positive result indicates a higher risk, not certainty of becoming ill; a negative result does not remove the risk (many families have no identifiable variant).": "Un risultato positivo indica un rischio più alto, non la certezza di ammalarsi; un risultato negativo non azzera il rischio (molte famiglie non hanno una variante identificabile).",
  "A user with this name already exists.": "Esiste già un utente con questo nome.",
  "ABCDE criteria and the 'ugly duckling' sign": "Criteri ABCDE e segno del 'brutto anatroccolo'",
  "ABCDE reminder": "Promemoria ABCDE",
  "ABCDE reminder for recognising a mole": "Promemoria ABCDE per riconoscere un neo",
  "About 5–10% of melanomas occur in families with an inherited predisposition (Leachman 2009). Here you find the criteria specialists use to decide whether to suggest genetic counselling, the genes involved and the literature on each.": "Circa il 5-10% dei melanomi si presenta in famiglie con una predisposizione ereditaria (Leachman 2009). Qui trovi i criteri che usano gli specialisti per decidere se proporre una consulenza genetica, i geni coinvolti e la letteratura su ciascuno.",
  "Accept and continue": "Accetto e continuo",
  "According to the NCCN guidelines, in an invasive melanoma with a first-degree relative with pancreatic cancer, a multigene panel that includes CDKN2A is recommended.": "Per le linee guida NCCN, in un melanoma invasivo con un parente di primo grado con tumore del pancreas è raccomandato un pannello multigene che includa CDKN2A.",
  "Acral melanoma (hands, feet, nails): dermoscopy": "Melanoma acrale (mani, piedi, unghie): dermoscopia",
  "Add a photo to the history": "Aggiungi una foto allo storico",
  "Add mole": "Aggiungi neo",
  "Add the first photo below: it will be the starting point to see whether the mole changes over time.": "Aggiungi qui sotto la prima foto: sarà il punto di partenza per vedere se il neo cambia nel tempo.",
  "Add the first photo: it becomes your baseline photo, and every later photo will follow how the mole evolves.": "Aggiungi la prima foto: diventa la tua foto storica, e ogni foto successiva ne seguirà l'evoluzione.",
  "Address not allowed.": "Indirizzo non ammesso.",
  "Address too long.": "Indirizzo troppo lungo.",
  "After": "Dopo",
  "Age": "Età",
  "Age, sex and phenotype do not change the output of the neural networks: they are used to show you the risk factors, choose the literature, evaluate the genetics criteria and estimate the time to sunburn.": "Età, sesso e fenotipo non cambiano l'uscita delle reti neurali: servono a mostrarti i fattori di rischio, a scegliere la letteratura, a valutare i criteri di genetica e a stimare il tempo di scottatura.",
  "All data stays on this computer, in the folder:": "Tutti i dati restano su questo computer, nella cartella:",
  "All its {n} photos and the analysis reports will be deleted permanently.": "Verranno cancellate per sempre tutte le sue {n} foto e i rapporti di analisi.",
  "Also use SkinSense (online service)": "Usa anche SkinSense (servizio online)",
  "Always shoot from the same angle and keep the original, without filters.": "Scatta sempre dalla stessa angolazione e salva l'originale, senza filtri.",
  "An estimate is fine.": "Una stima va bene.",
  "Analyse now with all installed methods": "Analizza subito con tutti i metodi installati",
  "Analyse this photo": "Analizza questa foto",
  "Analysis in progress…": "Analisi in corso…",
  "Analysis interrupted (app closed).": "Analisi interrotta (app chiusa).",
  "Analysis program (melanoma_batch.py) not found: photos are saved but cannot be analysed.": "Programma di analisi (melanoma_batch.py) non trovato: le foto si salvano ma non si possono analizzare.",
  "Analysis program:": "Programma di analisi:",
  "Analysis stopped after {ore} hours (too long).": "Analisi interrotta dopo {ore} ore (troppo lunga).",
  "Analysis: needs attention": "Analisi: da attenzionare",
  "Ankle, left": "Caviglia sinistra",
  "Ankle, right": "Caviglia destra",
  "Anything else you want to remember (allergies, photosensitising medicines, …)": "Altro che vuoi ricordare (allergie, farmaci fotosensibilizzanti, …)",
  "App 1 (DeborahAdedigba) - TensorFlow models": "App 1 (DeborahAdedigba) - modelli TensorFlow",
  "Appearance": "Aspetto",
  "Archive (removes it from the map, keeps the data)": "Archivia (toglie dalla mappa, conserva i dati)",
  "Archived moles ({n})": "Nei archiviati ({n})",
  "Arm, left": "Braccio sinistro",
  "Arm, right": "Braccio destro",
  "Asking the browser for your position… (a permission request may appear)": "Chiedo la posizione al browser… (potrebbe comparire una richiesta di permesso)",
  "Associated risk": "Rischio associato",
  "Associated with variants of the MC1R gene.": "Associati a varianti del gene MC1R.",
  "Astrocytoma": "Astrocitoma",
  "Asymmetry": "Asimmetria",
  "At least 3 diagnoses among melanoma, pancreatic cancer and astrocytoma in the same family line (yours included)": "Almeno 3 diagnosi tra melanoma, tumore del pancreas e astrocitoma nella stessa linea familiare (tua inclusa)",
  "At least one method (or one of its models) flags a lesion that needs attention. This is not a diagnosis and these tools are often wrong, but it is one more reason not to put off the dermatology visit and to bring this report.": "Almeno un metodo (o un suo modello) segnala una lesione da attenzionare. Non è una diagnosi e questi strumenti sbagliano spesso, ma è un motivo in più per non rimandare la visita dermatologica e per portare questo rapporto.",
  "Atypical (dysplastic) moles": "Nei atipici (displastici)",
  "Atypical moles": "Nei atipici",
  "Automatic (same as the system)": "Automatica (come il sistema)",
  "Automatic analysis": "Analisi automatica",
  "Avoid direct exposure: unprotected skin can burn within a few minutes.": "Evita l'esposizione diretta: la pelle non protetta può scottarsi in pochi minuti.",
  "Avoid the sun in the middle hours of the day and protect your skin well.": "Evita il sole nelle ore centrali e proteggi bene la pelle.",
  "BACK": "RETRO",
  "BAP1 tumour predisposition syndrome: uveal melanoma, mesothelioma, renal carcinoma, cutaneous melanoma and atypical melanocytic naevi.": "Sindrome di predisposizione ai tumori BAP1: melanoma uveale, mesotelioma, carcinoma renale, melanoma cutaneo e nevi melanocitari atipici.",
  "BAP1-spectrum tumours indicated: {bap1_spettro}. Simplified criterion: the geneticist uses more complete criteria.": "Tumori dello spettro BAP1 indicati: {bap1_spettro}. Criterio semplificato: il genetista usa criteri più completi.",
  "Back": "Retro",
  "Back (middle area), left": "Schiena (zona media) sinistra",
  "Back (middle area), right": "Schiena (zona media) destra",
  "Back of knee, left": "Cavo popliteo sinistro",
  "Back of knee, right": "Cavo popliteo destro",
  "Before": "Prima",
  "Before you start": "Prima di cominciare",
  "Black": "Neri",
  "Blond": "Biondi",
  "Blue/grey": "Azzurri/grigi",
  "Border": "Bordi",
  "Brown": "Castani",
  "Buttock, left": "Gluteo sinistro",
  "Buttock, right": "Gluteo destro",
  "Calf, left": "Polpaccio sinistro",
  "Calf, right": "Polpaccio destro",
  "Can't do it? Estimate from the internet address": "Non riesci? Stima dall'indirizzo internet",
  "Cancel": "Annulla",
  "Centre on the map": "Centra sulla mappa",
  "Change": "Cambia",
  "Change image…": "Cambia immagine…",
  "Change:": "Variazione:",
  "Checking status…": "Controllo lo stato…",
  "Chest, left": "Torace sinistro",
  "Chest, right": "Torace destro",
  "Choose a personal picture": "Scegli un'immagine personale",
  "Choose a user and enter their phototype to see how many minutes it takes to burn.": "Scegli un utente e indica il suo fototipo per vedere quanti minuti servono per scottarsi.",
  "Choose an image file (JPG, PNG, WEBP or BMP).": "Scegli un file immagine (JPG, PNG, WEBP o BMP).",
  "Choose image…": "Scegli immagine…",
  "Choose the city above: then you will see today's UV index, hour by hour.": "Scegli la città qui sopra: poi vedrai l'indice UV di oggi, ora per ora.",
  "Choose user": "Scegli utente",
  "Choose where you are to see today's UV index.": "Scegli dove ti trovi per vedere l'indice UV di oggi.",
  "Choose your profile: each person has their own mole map, photos and data.": "Scegli il tuo profilo: ogni persona ha la propria mappa dei nei, le proprie foto e i propri dati.",
  "Cited by the NCCN guidelines among the genes to consider in melanoma panels (Cowden syndrome).": "Citato dalle linee guida NCCN tra i geni da considerare nei pannelli per melanoma (sindrome di Cowden).",
  "City name": "Nome della città",
  "City search also uses Open-Meteo.": "Anche la ricerca delle città usa Open-Meteo.",
  "Classified as definite human carcinogens (IARC).": "Classificati come cancerogeni certi per l'uomo (IARC).",
  "Click a mole in the list or on the map to see its photo history.": "Clicca un neo nell'elenco o sulla mappa per vedere lo storico fotografico.",
  "Click on the exact spot on the body where the mole is (you can zoom in first)": "Clicca sul punto esatto del corpo dove si trova il neo (puoi ingrandire prima)",
  "Click to see the original photo full screen": "Clic per vedere la foto originale a schermo intero",
  "Clinical trial": "Studio clinico",
  "Close": "Chiudi",
  "Close NeoTracker": "Chiudi NeoTracker",
  "Close NeoTracker?": "Chiudere NeoTracker?",
  "Close the program": "Chiudi il programma",
  "Closing the program": "Chiudere il programma",
  "Colour": "Colore",
  "Common variants linked to red hair and fair skin: they raise the melanoma risk moderately. Not a routine test: interpretation is specialist.": "Varianti comuni legate a capelli rossi e pelle chiara: aumentano il rischio di melanoma in modo moderato. Non è un test di routine: l'interpretazione è specialistica.",
  "Compare": "Confronta",
  "Compare shape, borders and colours: if you notice differences, show the photos to your dermatologist.": "Confronta forma, bordi e colori: se noti differenze, mostra le foto al dermatologo.",
  "Comparison of two photos": "Confronto tra due foto",
  "Comparison slider": "Cursore di confronto",
  "Confirm": "Conferma",
  "Consent": "Consenso",
  "Count blood relatives (not in-laws) on the same side of the family, maternal or paternal: this is the criterion geneticists use. If you do not know, ask a relative: this information is very useful.": "Conta i parenti di sangue (non quelli acquisiti) dello stesso lato della famiglia, materno o paterno: è il criterio che usano i genetisti. Se non lo sai, chiedi a un familiare: queste informazioni sono molto utili.",
  "Create a free account at": "Crea un account gratuito su",
  "Create user": "Crea utente",
  "Dark": "Scuri",
  "Dark skin. Rarely burns.": "Pelle scura. Scotta raramente.",
  "Date of birth": "Data di nascita",
  "Date of birth out of range.": "Data di nascita fuori intervallo.",
  "Date the photo was taken": "Data dello scatto",
  "Decrease: {voce}": "Diminuisci: {voce}",
  "Deep learning and melanoma: systematic reviews": "Deep learning e melanoma: revisioni sistematiche",
  "Delete": "Elimina",
  "Delete permanently": "Elimina definitivamente",
  "Delete photo": "Elimina foto",
  "Delete this mole and its photos": "Elimina questo neo e le sue foto",
  "Delete this photo?": "Eliminare questa foto?",
  "Delete «{nome}»?": "Eliminare «{nome}»?",
  "Dermoscopic": "Dermoscopica",
  "Dermoscopy and early diagnosis (reviews)": "Dermoscopia e diagnosi precoce (revisioni)",
  "Detect my location": "Rileva la mia posizione",
  "Diameter": "Diametro",
  "Diameter (mm)": "Diametro (mm)",
  "Diameter over time": "Diametro nel tempo",
  "Diameter:": "Diametro:",
  "Diameter: from {da} to {a} mm.": "Diametro: da {da} a {a} mm.",
  "Diameter: {diff} mm difference.": "Diametro: {diff} mm di differenza.",
  "Don't know": "Non so",
  "Downloading the UV index…": "Scarico l'indice UV…",
  "Drag a photo here or click to choose one": "Trascina qui una foto oppure clicca per sceglierla",
  "Drag the dot on the map to correct the position; zoom in with the wheel for maximum precision.": "Trascina il pallino sulla mappa per correggere la posizione; ingrandisci con la rotella per la massima precisione.",
  "Drag the dot on the map to move it.": "Trascina il pallino sulla mappa per spostarlo.",
  "Ear, left": "Orecchio sinistro",
  "Ear, right": "Orecchio destro",
  "Edit date/measurement": "Modifica data/misura",
  "Edit photo": "Modifica foto",
  "Edit the data in the Profile": "Modifica i dati nel Profilo",
  "Elbow, left": "Gomito sinistro",
  "Elbow, right": "Gomito destro",
  "Email for PubMed": "Email per PubMed",
  "Email saved.": "Email salvata.",
  "Enlarge": "Ingrandisci",
  "Error {codice}": "Errore {codice}",
  "Especially in childhood and adolescence.": "Soprattutto in infanzia e adolescenza.",
  "Estimate from the internet address": "Stima dall'indirizzo internet",
  "Estimated location": "Posizione stimata",
  "Evolution": "Evoluzione",
  "Extra precautions: avoid the sun in the middle of the day, seek shade, cover your skin, SPF 30+. Unprotected skin burns quickly.": "Precauzioni extra: evita il sole nelle ore centrali, cerca l'ombra, copri la pelle, SPF 30+. La pelle non protetta si scotta in fretta.",
  "Extreme": "Estremo",
  "Eye colour": "Colore degli occhi",
  "Eyes": "Occhi",
  "FRONT": "FRONTE",
  "Face": "Viso",
  "Fair phototype (I–II)": "Fototipo chiaro (I-II)",
  "Fair skin. Burns easily, tans little.": "Pelle chiara. Scotta facilmente, si abbronza poco.",
  "Fair-olive skin. Sometimes burns, tans gradually.": "Pelle chiara-olivastra. Scotta a volte, si abbronza gradualmente.",
  "Fajuyigbe D, Young AR. The impact of skin colour on human photobiological responses. Pigment Cell Melanoma Res 2016;29:607-18 (minimal erythema dose by phototype)": "Fajuyigbe D, Young AR. The impact of skin colour on human photobiological responses. Pigment Cell Melanoma Res 2016;29:607-18 (dose minima di eritema per fototipo)",
  "Family history": "Familiarità",
  "Fewer than 25": "Meno di 25",
  "Fill in the 'Family history' section of your Profile: without that data I cannot check the criteria.": "Compila la sezione 'Familiarità' nel Profilo: senza quei dati non posso verificare i criteri.",
  "Fill in the family history in your Profile": "Compila la familiarità nel Profilo",
  "First-degree relative with melanoma": "Parente di primo grado con melanoma",
  "Folder with your data (copy it for backup):": "Cartella dei tuoi dati (da copiare per il backup):",
  "Foot, left": "Piede sinistro",
  "Foot, right": "Piede destro",
  "Forearm, left": "Avambraccio sinistro",
  "Forearm, right": "Avambraccio destro",
  "Forehead and scalp": "Fronte e cuoio capelluto",
  "Freckles": "Efelidi",
  "Freckles (ephelides)": "Efelidi (lentiggini)",
  "Front": "Fronte",
  "Full report (text)": "Rapporto completo (testo)",
  "Full report (text, in English)": "Rapporto completo (testo, in inglese)",
  "Gene": "Gene",
  "Gene not in the list.": "Gene non presente nell'elenco.",
  "Gene {n} of {tot} ({nome})…": "Gene {n} di {tot} ({nome})…",
  "Genetic test": "Test genetico",
  "Genetic test already done": "Test genetico già eseguito",
  "Genetics": "Genetica",
  "Give the mole a name and check the site.": "Dai un nome al neo e controlla la sede.",
  "Go to the Genetics section": "Vai alla sezione Genetica",
  "Grandparents, aunts and uncles, nieces and nephews (2nd degree).": "Nonni, zii, nipoti (2° grado).",
  "Green": "Verdi",
  "Grey/white": "Grigi/bianchi",
  "Groin, left": "Inguine sinistro",
  "Groin, right": "Inguine destro",
  "Guideline": "Linea guida",
  "Guidelines and criteria for genetic testing": "Linee guida e criteri per il test genetico",
  "Guidelines recommend the test only after careful selection of candidates and adequate counselling (Rossi 2019); the use of multigene panels is still debated.": "Le linee guida raccomandano il test solo dopo una selezione accurata dei candidati e un'adeguata consulenza (Rossi 2019); l'uso dei pannelli multigene è ancora discusso.",
  "Hair": "Capelli",
  "Hand, left": "Mano sinistra",
  "Hand, right": "Mano destra",
  "Has a doctor told you that you have atypical (dysplastic) moles?": "Un medico ti ha detto che hai nei atipici (displastici)?",
  "Have I already had a genetic test for melanoma?": "Ho già fatto un test genetico per il melanoma?",
  "Having had a melanoma raises the risk of a second one.": "Chi ha avuto un melanoma ha un rischio maggiore di un secondo.",
  "Hereditary melanoma": "Melanoma ereditario",
  "Hereditary melanoma and genetic testing": "Melanoma ereditario e test genetico",
  "High": "Alto",
  "High (BAP1 syndrome)": "Alto (sindrome BAP1)",
  "High (rare)": "Alto (raro)",
  "Hour-by-hour UV index for the next 24 hours": "Indice UV ora per ora nelle prossime 24 ore",
  "Hourly data not available": "Dati orari non disponibili",
  "How reliable are apps and artificial intelligence": "Quanto sono affidabili app e intelligenza artificiale",
  "How to get the key": "Come ottenere la chiave",
  "How to read the UV index": "Come si legge l'indice UV",
  "How to take comparable photos": "Come scattare foto confrontabili",
  "I am immunosuppressed (transplant or therapies that lower the body's defences)": "Sono immunosoppresso/a (trapianto o terapie che abbassano le difese)",
  "I assume the 2 outputs are [benign, malignant]; order cannot be verified": "assumo che le 2 uscite siano [benigno, maligno]; ordine non verificabile",
  "I cannot find melanoma_batch.py: it must be in the same folder as neotracker.py (or in {CARTELLA_REPO}).": "Non trovo melanoma_batch.py: deve stare nella stessa cartella di neotracker.py (oppure in {CARTELLA_REPO}).",
  "I cannot prepare the photo safely: {e}": "non riesco a preparare la foto in modo sicuro: {e}",
  "I cannot reach NeoTracker. The program may have been closed: reopen it from the icon on the Desktop.": "Non riesco a contattare NeoTracker. Il programma potrebbe essere stato chiuso: riaprilo dall'icona sul Desktop.",
  "I cannot read this image. Try a JPG or a PNG.": "Non riesco a leggere questa immagine. Prova con un JPG o un PNG.",
  "I cannot reduce this image.": "Non riesco a ridurre questa immagine.",
  "I don't know: leave it empty, you can come back later.": "Non lo so: lascia vuoto, puoi tornare più tardi.",
  "I have checked my family history (even if the answer is «none»)": "Ho verificato la mia storia familiare (anche se la risposta è «nessuno»)",
  "I have had (or have) one of these cancers:": "Ho avuto (o ho) uno di questi tumori:",
  "I have had other skin cancers (basal cell or squamous cell carcinoma)": "Ho avuto altri tumori della pelle (basalioma, spinalioma)",
  "I have read and understood these notices": "Ho letto e capito queste avvertenze",
  "I prefer not to say": "Preferisco non dirlo",
  "I work or do activities outdoors for many hours": "Lavoro o faccio attività per molte ore all'aperto",
  "If it is still analysing a photo, it finishes the analysis first and then shuts down. The button below does the same thing.": "Se sta ancora analizzando una foto, finisce prima l'analisi e poi si spegne. Il pulsante qui sotto fa la stessa cosa.",
  "If you are unsure about your phototype, think about how your skin reacts to the first intense sun exposure in summer, without protection.": "Se hai dubbi sul fototipo, pensa a come reagisce la tua pelle alla prima esposizione intensa al sole in estate, senza protezione.",
  "If you enter data or photos of other people, make sure you have their consent.": "Se inserisci dati o foto di altre persone, assicurati di avere il loro consenso.",
  "Immunosuppression (therapies, transplant)": "Immunosoppressione (terapie, trapianto)",
  "Important notices": "Avvertenze",
  "In English": "In inglese",
  "In-focus photo, with the mole in the centre and the skin clearly visible (move hair aside if needed).": "Foto a fuoco, con il neo al centro e la pelle ben visibile (sposta i peli, se serve).",
  "Increase: {voce}": "Aumenta: {voce}",
  "Installation status": "Stato dell'installazione",
  "Interface language": "Lingua dell'interfaccia",
  "Internal error. Details are in the neotracker.log file in the data folder.": "Errore interno. I dettagli sono nel file neotracker.log nella cartella dei dati.",
  "Invalid UV index source.": "Fonte dell'indice UV non valida.",
  "Invalid coordinates.": "Coordinate non valide.",
  "Invalid data (JSON).": "Dati non validi (JSON).",
  "Invalid data.": "Dati non validi.",
  "Invalid date of birth (YYYY-MM-DD).": "Data di nascita non valida (AAAA-MM-GG).",
  "Invalid date: use the format YYYY-MM-DD.": "Data non valida: usa il formato AAAA-MM-GG.",
  "Invalid email address.": "Email non valida.",
  "Invalid location.": "Posizione non valida.",
  "Invalid notice version.": "Versione dell'avviso non valida.",
  "Invalid page identifier.": "Identificativo di pagina non valido.",
  "Invalid profile.": "Profilo non valido.",
  "Irregular, jagged or blurred.": "Irregolari, frastagliati o sfumati.",
  "It changes over time: shape, colour, size, elevation, or itching or bleeding appear.": "Cambia nel tempo: forma, colore, dimensione, rilievo, o compaiono prurito o sanguinamento.",
  "It is a personal tool for organising the photos of your moles and comparing over time the results of some research models. It is not certified or approved by any health authority.": "È uno strumento personale per organizzare le foto dei tuoi nei e confrontare nel tempo i risultati di alcuni modelli di ricerca. Non è certificato né approvato da alcuna autorità sanitaria.",
  "It is normal for the methods to disagree: it only means that none of them is reliable on its own.": "Se i metodi sono in disaccordo è normale: significa solo che nessuno di loro è affidabile da solo.",
  "It works: OpenWeather answers (current UV index: {uvi}).": "Funziona: OpenWeather risponde (indice UV attuale: {uvi}).",
  "Its only photo and the analysis reports will be deleted permanently.": "Verranno cancellate per sempre la sua unica foto e i rapporti di analisi.",
  "JPG, PNG, WEBP or BMP · up to 60 MB": "JPG, PNG, WEBP o BMP · fino a 60 MB",
  "Key removed.": "Chiave rimossa.",
  "Key saved ({finale}) — type a new one to replace it": "Chiave salvata ({finale}) — scrivine una nuova per sostituirla",
  "Key saved.": "Chiave salvata.",
  "Kidney carcinoma": "Carcinoma del rene",
  "Knee, left": "Ginocchio sinistro",
  "Knee, right": "Ginocchio destro",
  "L": "S",
  "Language": "Lingua",
  "Language not supported.": "Lingua non supportata.",
  "Large, irregular, multicoloured moles: they should be followed over time.": "Nei grandi, irregolari, di più colori: vanno seguiti nel tempo.",
  "Latest automatic analysis ({data}): {esito}. Research tool, not diagnostic.": "Ultima analisi automatica ({data}): {esito}. Strumento di ricerca, non diagnostico.",
  "Leachman 2009 and 2017; NCCN": "Leachman 2009 e 2017; NCCN",
  "Leachman 2017; NCCN": "Leachman 2017; NCCN",
  "Lentigo maligna and melanoma of the face": "Lentigo maligna e melanoma del volto",
  "Light-coloured eyes": "Occhi chiari",
  "List of factors known from the literature, not a validated score: it does not estimate the probability of falling ill.": "Elenco di fattori noti dalla letteratura, non un punteggio validato: non stima la probabilità di ammalarsi.",
  "Literature": "Letteratura",
  "Literature: PubMed": "Letteratura: PubMed",
  "Loading…": "Caricamento…",
  "Location": "Posizione",
  "Location missing": "Manca la posizione",
  "Location not set": "Posizione non impostata",
  "Location not set: choose a city or use 'Detect my location'.": "Posizione non impostata: scegli una città o usa 'Rileva la mia posizione'.",
  "Location outside the map.": "Posizione fuori dalla mappa.",
  "Location saved: {nome}": "Posizione salvata: {nome}",
  "Location set": "Posizione impostata",
  "Location updated.": "Posizione aggiornata.",
  "Location updated: {regione}.": "Posizione aggiornata: {regione}.",
  "Low": "Basso",
  "Low to moderate (common)": "Basso-moderato (comune)",
  "Lower abdomen, left": "Addome basso sinistro",
  "Lower abdomen, right": "Addome basso destro",
  "Lower back, left": "Regione lombare sinistra",
  "Lower back, right": "Regione lombare destra",
  "Lower leg (shin), left": "Gamba (stinco) sinistra",
  "Lower leg (shin), right": "Gamba (stinco) destra",
  "Lucas RM et al. Are current guidelines for sun protection optimal for health? Photochem Photobiol Sci 2018;17:1956-63 (UV Index and erythemal dose)": "Lucas RM et al. Are current guidelines for sun protection optimal for health? Photochem Photobiol Sci 2018;17:1956-63 (UV Index e dose di eritema)",
  "Main high-penetrance predisposition gene. Germline variants in 20–40% of families with melanoma; also associated with pancreatic cancer, multiple melanomas and early onset.": "Principale gene di predisposizione ad alta penetranza. Varianti germinali nel 20-40% delle famiglie con melanoma; associato anche a tumore del pancreas, melanomi multipli ed esordio precoce.",
  "Man": "Uomo",
  "Many": "Molte",
  "Many freckles (ephelides)": "Molte efelidi (lentiggini)",
  "Many moles or atypical moles: surveillance": "Molti nei o nei atipici: sorveglianza",
  "Many sunburns with blisters": "Molte scottature con vesciche",
  "Map of the human body: front on the left, back on the right": "Mappa del corpo umano: fronte a sinistra, retro a destra",
  "Measured diameter (mm)": "Diametro misurato (mm)",
  "Melanoma already diagnosed": "Melanoma già diagnosticato",
  "Melanoma and immunosuppression": "Melanoma e immunosoppressione",
  "Melanoma in dark skin (often acral)": "Melanoma nelle pelli scure (spesso acrale)",
  "Melanoma of the eye (uveal)": "Melanoma dell'occhio (uveale)",
  "Melanoma-Detector (VukIG)": "Melanoma-Detector (VukIG)",
  "Melanomas already diagnosed": "Melanomi già diagnosticati",
  "Melanomas already diagnosed in me": "Melanomi già diagnosticati a me",
  "Mesothelioma": "Mesotelioma",
  "Met": "Soddisfatto",
  "Meta-analysis": "Meta-analisi",
  "Method 1 - App 1 (Deborah Adedigba)": "Metodo 1 - App 1 (Deborah Adedigba)",
  "Method 1 turned off in the settings.": "Metodo 1 disattivato dalle impostazioni.",
  "Method 2 - SkinSense (online service)": "Metodo 2 - SkinSense (servizio online)",
  "Method 2 not run (turned off in the settings): the photo did not leave the PC.": "Metodo 2 non eseguito (disattivato nelle impostazioni): la foto non e' uscita dal PC.",
  "Method 3 did NOT analyse the photo: the project is a prototype without a model. Its server merely receives the image (no neural network), so any reassuring text it shows does not come from an analysis and has no value.": "Il metodo 3 NON ha analizzato la foto: il progetto e' un prototipo senza modello. Il suo server si limita a ricevere l'immagine (nessuna rete neurale), quindi qualunque testo rassicurante mostri non deriva da un'analisi e non ha alcun valore.",
  "Method 4 - vatsal30": "Metodo 4 - vatsal30",
  "Method 4 turned off in the settings.": "Metodo 4 disattivato dalle impostazioni.",
  "Method 5 is an Android app: it cannot run on the PC. Install the APK on the phone, frame the mole and note the result by hand below.\nApp result on the phone: ______________________________": "Il metodo 5 e' un'app Android: non puo' girare dal PC. Installa l'APK sul telefono, inquadra il neo e annota a mano il risultato qui sotto.\nRisultato dell'app sul telefono: ______________________________",
  "Method {n}": "Metodo {n}",
  "Method {n} said:": "Il metodo {n} ha detto che:",
  "Methods disagree": "Metodi in disaccordo",
  "Moderate": "Moderato",
  "Moderate UV: protection needed in the middle of the day": "UV moderati: serve protezione nelle ore centrali",
  "Mole archived. You will find it at the bottom of the list.": "Neo archiviato. Lo trovi in fondo all'elenco.",
  "Mole deleted.": "Neo eliminato.",
  "Mole diameter over time": "Diametro del neo nel tempo",
  "Mole map": "Mappa dei nei",
  "Mole name": "Nome del neo",
  "Mole not found.": "Neo non trovato.",
  "Mole saved. Now add the first photo: it will be your \"baseline photo\".": "Neo salvato. Ora aggiungi la prima foto: sarà la tua \"foto storica\".",
  "Mole sheet – {nome}": "Scheda dei nei – {nome}",
  "Mole with photos": "Neo con foto",
  "Mole {n}": "Neo {n}",
  "More than 6 mm (but smaller melanomas exist).": "Più di 6 mm (ma esistono melanomi più piccoli).",
  "Most recent studies on predisposition genes": "Studi più recenti sui geni di predisposizione",
  "Most relevant studies": "Studi più pertinenti",
  "Move the pointer over the body to see the area": "Passa il puntatore sul corpo per vedere la zona",
  "Multiple BAP1-spectrum tumours (uveal melanoma, mesothelioma, renal carcinoma, cutaneous melanoma)": "Più tumori dello spettro BAP1 (melanoma uveale, mesotelioma, carcinoma renale, melanoma cutaneo)",
  "My location ({lat}; {lon})": "La mia posizione ({lat}; {lon})",
  "NCCN": "NCCN",
  "NCCN Clinical Practice Guidelines in Oncology: Melanoma: Cutaneous (current version; the full text requires free registration)": "NCCN Clinical Practice Guidelines in Oncology: Melanoma: Cutaneous (versione corrente; il testo completo richiede una registrazione gratuita)",
  "Name": "Nome",
  "Name or nickname": "Nome o soprannome",
  "Nape and neck": "Nuca e collo",
  "Natural hair colour (when young)": "Colore naturale dei capelli (da giovane)",
  "Neck": "Collo",
  "Needs attention": "Da attenzionare",
  "NeoTracker closed": "NeoTracker chiuso",
  "NeoTracker is closed": "NeoTracker è chiuso",
  "NeoTracker is not a genetic counselling service. For a personal assessment, see your dermatologist or an oncological genetics centre.": "NeoTracker non è un servizio di consulenza genetica. Per una valutazione personale rivolgiti al dermatologo o a un centro di genetica oncologica.",
  "NeoTracker is not a medical device and does not make diagnoses.": "NeoTracker non è un dispositivo medico e non fa diagnosi.",
  "NeoTracker is not a medical tool and does not make diagnoses. For any mole that changes, bleeds, itches or worries you, see a dermatologist.": "NeoTracker non è uno strumento medico e non fa diagnosi. Per qualsiasi neo che cambia, sanguina, prude o ti preoccupa, rivolgiti a un dermatologo.",
  "NeoTracker is not responding": "NeoTracker non risponde",
  "Never": "Mai",
  "New mole": "Nuovo neo",
  "New user": "Nuovo utente",
  "Next {n} hours": "Prossime {n} ore",
  "No": "No",
  "No alarm from the models": "Nessun allarme dai modelli",
  "No articles found.": "Nessun articolo trovato.",
  "No city found with this name.": "Nessuna città trovata con questo nome.",
  "No image set.": "Nessuna immagine impostata.",
  "No method produced a result: check the reasons listed below.": "Nessun metodo ha prodotto un risultato: controlla i motivi indicati sotto.",
  "No moles yet": "Nessun neo ancora",
  "No photo recorded yet.": "Nessuna foto ancora registrata.",
  "No photos yet": "Ancora nessuna foto",
  "No photos: add the first one": "Nessuna foto: aggiungi la prima",
  "No result": "Nessun risultato",
  "No special protection needed for normal activities; sunglasses on bright days.": "Nessuna protezione particolare per le attività normali; occhiali da sole nelle giornate luminose.",
  "None": "Nessuna",
  "None of the methods that responded flags the lesion as suspicious. This does NOT rule out a melanoma: the tools are not clinically validated and are also wrong in this direction. If the mole is asymmetric, has irregular borders, several colours, is larger than 6 mm or has changed over time, a visit is still needed.": "Nessuno dei metodi che hanno risposto segnala la lesione come sospetta. Questo NON esclude un melanoma: gli strumenti non sono validati clinicamente e sbagliano anche in questa direzione. Se il neo è asimmetrico, ha bordi irregolari, colori diversi, è più grande di 6 mm o è cambiato nel tempo, la visita resta necessaria.",
  "Normal photo": "Foto normale",
  "Normal photo (smartphone)": "Foto normale (smartphone)",
  "Not allowed.": "Non consentito.",
  "Not met": "Non soddisfatto",
  "Not scanned yet": "Non ancora scansionato",
  "Not scanned yet.": "Non ancora scansionata.",
  "Not specified": "Non indicato",
  "Notes": "Note",
  "Notes on the mole…": "Note sul neo…",
  "Notes:": "Note:",
  "Nothing is sent online, except the requests you turn on (UV weather, PubMed literature, SkinSense).": "Nulla viene inviato online, tranne le richieste che attivi tu (meteo UV, letteratura PubMed, SkinSense).",
  "Now": "Adesso",
  "Number of moles": "Numero di nei",
  "Observational study": "Studio osservazionale",
  "Of any degree of kinship.": "Di qualsiasi grado di parentela.",
  "Off by default: with the other methods the photo never leaves this computer.": "Spento per impostazione predefinita: con gli altri metodi la foto non lascia mai questo computer.",
  "Often": "Spesso",
  "Olive skin. Burns little, tans easily.": "Pelle olivastra. Scotta poco, si abbronza facilmente.",
  "One Call {n}: {t}": "One Call {n}: {t}",
  "Only invasive primary melanomas count.": "Conta solo i melanomi primari invasivi.",
  "Open the «API keys» page of your account and copy the key.": "Apri la pagina «API keys» del tuo account e copia la chiave.",
  "Open-Meteo (default)": "Open-Meteo (predefinita)",
  "OpenWeather key": "Chiave OpenWeather",
  "OpenWeather key saved ({finale}).": "Chiave OpenWeather salvata ({finale}).",
  "OpenWeather rejected the key (401): check that it is correct and that the 'One Call API' plan (pay per call, 1,000 free calls per day) is active on your account. After subscribing, the key can take a few minutes to activate.": "OpenWeather ha rifiutato la chiave (401): controlla che sia corretta e che sul tuo account sia attivo l'abbonamento 'One Call API' (pagamento a chiamata, 1.000 chiamate al giorno gratuite). Dopo l'iscrizione la chiave può impiegare qualche minuto ad attivarsi.",
  "OpenWeather unavailable ({e}). Showing Open-Meteo data.": "OpenWeather non disponibile ({e}). Mostro i dati di Open-Meteo.",
  "OpenWeather: call limit reached (429).": "OpenWeather: limite di chiamate raggiunto (429).",
  "Operation not allowed on this address.": "Operazione non consentita su questo indirizzo.",
  "Optional": "Facoltativa",
  "Origin not allowed.": "Origine non ammessa.",
  "Original photo": "Foto originale",
  "Other": "Altro",
  "Other relatives with melanoma": "Altri parenti con melanoma",
  "Other skin cancers (basal cell and squamous cell carcinoma)": "Altri tumori della pelle (basalioma, spinalioma)",
  "Overlay with slider": "Sovrapponi con cursore",
  "Page not found.": "Pagina non trovata.",
  "Pancreatic cancer": "Tumore del pancreas",
  "Parents, brothers, sisters, children.": "Genitori, fratelli, sorelle, figli.",
  "Parents, siblings or children.": "Genitori, fratelli o figli.",
  "Paste the key above and press «Test the key». After subscribing, the key can take a few minutes to activate. The program tries One Call 4.0 first and, if the key belongs to an older plan, One Call 3.0.": "Incolla la chiave qui sopra e premi «Prova la chiave». Dopo l'iscrizione la chiave può impiegare qualche minuto ad attivarsi. Il programma prova prima One Call 4.0 e, se la chiave è di un abbonamento più vecchio, One Call 3.0.",
  "Paste the key first.": "Incolla prima la chiave.",
  "Paste the key here (32 letters and digits)": "Incolla qui la chiave (32 lettere e numeri)",
  "People with many moles, atypical moles or a history of melanoma should protect themselves even when the index is moderate.": "Chi ha tanti nei, nei atipici o una storia di melanoma dovrebbe proteggersi anche con indici moderati.",
  "Permission denied. You can search for the city by name or use the estimate from the internet address.": "Permesso negato. Puoi cercare la città per nome oppure usare la stima da indirizzo internet.",
  "Personal data": "Dati personali",
  "Personal details": "Dati della persona",
  "Personal history": "Storia personale",
  "Personal melanoma and a first-degree relative with pancreatic cancer": "Melanoma personale e parente di primo grado con tumore del pancreas",
  "Personal picture": "Immagine personale",
  "Personal picture saved.": "Immagine personale salvata.",
  "Phenotype: skin, hair, eyes": "Fenotipo: pelle, capelli, occhi",
  "Photo analysis": "Analisi delle foto",
  "Photo date is too old.": "Data della foto troppo vecchia.",
  "Photo deleted.": "Foto eliminata.",
  "Photo file not found.": "File della foto non trovato.",
  "Photo from {data}": "Foto del {data}",
  "Photo history": "Storico fotografico",
  "Photo history ({n})": "Storico fotografico ({n})",
  "Photo not found.": "Foto non trovata.",
  "Photo saved ({data}).": "Foto salvata ({data}).",
  "Photo saved ({data}, date read from the photo).": "Foto salvata ({data}, data letta dalla foto).",
  "Photo type": "Tipo di foto",
  "Phototype": "Fototipo",
  "Phototype (Fitzpatrick classification)": "Fototipo (classificazione di Fitzpatrick)",
  "Phototype, age and family history do not change the neural networks' result (they only look at pixels): they serve to put the risk in context.": "Fototipo, età e familiarità non cambiano il risultato delle reti neurali (guardano solo i pixel): servono a contestualizzare il rischio.",
  "Picked for you (based on profile and mole locations)": "Scelti per te (in base a profilo e sede dei nei)",
  "Picture removed.": "Immagine rimossa.",
  "Pillow is not installed: previews will use the original photos (install with «py -m pip install pillow»).": "Pillow non installato: le anteprime useranno le foto originali (installa con «py -m pip install pillow»).",
  "Place a ruler or a coin next to the mole: it is used to measure the diameter.": "Metti accanto al neo un righello o una moneta: serve per misurare il diametro.",
  "Preparing the sheet…": "Preparo la scheda…",
  "Press": "Premi",
  "Preview": "Anteprima",
  "Primary melanomas indicated: {mel_pers}.": "Melanomi primari indicati: {mel_pers}.",
  "Print a sheet with all the moles": "Stampa una scheda con tutti i nei",
  "Print the sheet for this mole": "Stampa la scheda di questo neo",
  "Printed on {data} with NeoTracker": "Stampata il {data} con NeoTracker",
  "Profile": "Profilo",
  "Profile not filled in.": "Profilo non compilato.",
  "Profile of {nome}": "Profilo di {nome}",
  "Profile to complete": "Profilo da completare",
  "Projects folder:": "Cartella dei progetti:",
  "Protection necessary: reduce exposure between 10 and 16, SPF 30+ sunscreen, hat and sunglasses.": "Protezione necessaria: riduci l'esposizione tra le 10 e le 16, crema solare SPF 30+, cappello e occhiali.",
  "Protection not needed for normal activities (beware of snow, water, altitude).": "Protezione non necessaria per le attività normali (attenzione a neve, acqua, quota).",
  "Protection recommended: shade in the middle of the day, hat, sunglasses and sunscreen.": "Protezione consigliata: ombra nelle ore centrali, cappello, occhiali e crema solare.",
  "PubMed is a service of the National Library of Medicine. Abstracts are shown for personal consultation, in English; for the full text, open the article on the journal's website.": "PubMed è un servizio della National Library of Medicine. Gli abstract sono mostrati per consultazione personale, in inglese; per il testo completo apri l'articolo sul sito della rivista.",
  "PubMed is unreachable: showing the last saved search from {data}.": "PubMed non è raggiungibile: mostro l'ultima ricerca salvata il {data}.",
  "PubMed responded with error {code}": "PubMed ha risposto con errore {code}",
  "PubMed unreachable (check the internet connection)": "PubMed non raggiungibile (controlla la connessione internet)",
  "PubMed {pmid} · abstract not available": "PubMed {pmid} · abstract non disponibile",
  "Queued (position {n})…": "In coda (posizione {n})…",
  "Queued…": "In coda…",
  "Quit the program": "Esci dal programma",
  "R": "D",
  "R = patient's right · L = left": "D = destra del paziente · S = sinistra",
  "Randomised trial": "Studio randomizzato",
  "Rare": "Raro",
  "Rare variants concentrated in codon 24: the family picture is indistinguishable from that of CDKN2A.": "Varianti rare concentrate nel codone 24: il quadro familiare è indistinguibile da quello di CDKN2A.",
  "Re-analyse": "Rianalizza",
  "Read the abstract": "Leggi l'abstract",
  "Recent, relevant articles on recognising suspicious moles, on the reliability of apps and artificial intelligence, and on hereditary melanoma. Results come from PubMed, the public database of the National Library of Medicine (USA).": "Articoli recenti e rilevanti su come riconoscere i nei sospetti, sull'affidabilità di app e intelligenza artificiale e sul melanoma ereditario. I risultati arrivano da PubMed, la banca dati pubblica della National Library of Medicine (USA).",
  "Recognising a suspicious mole": "Riconoscere un neo sospetto",
  "Red": "Rossi",
  "Red or blond hair": "Capelli rossi o biondi",
  "Refresh": "Aggiorna",
  "Relatives with astrocytoma (brain tumour)": "Parenti con astrocitoma (tumore del cervello)",
  "Relatives with kidney carcinoma": "Parenti con carcinoma del rene",
  "Relatives with melanoma of the eye (uveal)": "Parenti con melanoma dell'occhio (uveale)",
  "Relatives with mesothelioma": "Parenti con mesotelioma",
  "Relatives with pancreatic cancer (in total)": "Parenti con tumore del pancreas (in tutto)",
  "Remove": "Rimuovi",
  "Remove the key?": "Rimuovere la chiave?",
  "Rename": "Rinomina",
  "Rename user": "Rinomina utente",
  "Repeat the search ignoring the saved results": "Rifà la ricerca ignorando i risultati salvati",
  "Request too large.": "Richiesta troppo grande.",
  "Restore": "Ripristina",
  "Review": "Revisione",
  "Reviews on familial melanoma (CDKN2A, CDK4)": "Revisioni sul melanoma familiare (CDKN2A, CDK4)",
  "Risk factors indicated:": "Fattori di rischio indicati:",
  "Risk factors present": "Fattori di rischio presenti",
  "Role and literature": "Ruolo e letteratura",
  "Roughly how many moles do you have on your body?": "Quanti nei hai sul corpo, circa?",
  "Same light (daylight, no flash) and same distance every time, about 10–15 cm.": "Stessa luce (luce del giorno, senza flash) e stessa distanza ogni volta, circa 10-15 cm.",
  "Save": "Salva",
  "Save an OpenWeather key first.": "Prima salva una chiave OpenWeather.",
  "Save mole": "Salva neo",
  "Save photo": "Salva foto",
  "Saved ✓": "Salvato ✓",
  "Saving…": "Salvataggio…",
  "Scalp (head)": "Cuoio capelluto (testa)",
  "Scan complete.": "Scansione completata.",
  "Scan the literature": "Scansiona la letteratura",
  "Scan the literature on genes": "Scansiona la letteratura sui geni",
  "Scientific literature": "Letteratura scientifica",
  "Search": "Cerca",
  "Search for a city (e.g. Turin)": "Cerca una città (es. Torino)",
  "Search for more (e.g. \"ugly duckling sign\", \"nail melanoma\"…)": "Cerca altro (es. \"ugly duckling sign\", \"nail melanoma\"…)",
  "Search the literature": "Cerca nella letteratura",
  "Searches go from this computer to PubMed (no personal data is sent). Results are saved for 7 days.": "Le ricerche partono da questo computer verso PubMed (nessun dato personale viene inviato). I risultati si salvano per 7 giorni.",
  "Searches use PubMed's public E-utilities. NCBI asks, as a courtesy, for a contact email: it is optional and is sent only to PubMed.": "Le ricerche usano le E-utilities pubbliche di PubMed. NCBI chiede, per cortesia, un'email di contatto: è facoltativa e viene inviata solo a PubMed.",
  "Searching PubMed…": "Cerco su PubMed…",
  "Searching…": "Cerco…",
  "Section {n} of {tot}…": "Sezione {n} di {tot}…",
  "Sections": "Sezioni",
  "Send the photos to SkinSense?": "Inviare le foto a SkinSense?",
  "Sequential photography and monitoring of moles over time": "Fotografia sequenziale e monitoraggio dei nei nel tempo",
  "Settings": "Impostazioni",
  "Several colours in the same mole (brown, black, red, blue, white).": "Più colori nello stesso neo (marrone, nero, rosso, blu, bianco).",
  "Sex": "Sesso",
  "Shade, clothing, a hat and sunscreen are needed in the middle of the day.": "Servono ombra, abiti, cappello e crema solare nelle ore centrali.",
  "Sheet for the dermatologist": "Scheda per il dermatologo",
  "Shoulder blade area, left": "Regione scapolare sinistra",
  "Shoulder blade area, right": "Regione scapolare destra",
  "Shoulder, left": "Spalla sinistra",
  "Shoulder, right": "Spalla destra",
  "Show side by side": "Mostra affiancate",
  "Show the whole body": "Mostra tutto il corpo",
  "Showing {n} photos out of {tot}.": "Sono mostrate {n} foto su {tot}.",
  "Significant risk factors are present: periodic dermatological check-ups (the dermatologist decides how often) and regular skin self-examination are recommended.": "Sono presenti fattori di rischio rilevanti: è consigliato un controllo dermatologico periodico (la frequenza la decide il dermatologo) e l'autoesame regolare della pelle.",
  "Simplified criteria, for information only. Genetic testing concerns a small minority of people and is not a routine examination: it is up to the specialist to decide whether and which test to offer, usually after genetic counselling and, when possible, starting from a relative who has had the disease.": "Criteri semplificati, a scopo informativo. Il test genetico riguarda una piccola minoranza di persone e non è un esame di routine: è lo specialista a decidere se e quale test proporre, di norma dopo una consulenza genetica e partendo, quando possibile, da un familiare che ha avuto la malattia.",
  "Site": "Sede",
  "Site (editable)": "Sede (modificabile)",
  "Skin self-examination": "Autoesame della pelle",
  "Skin that burns easily and tans little.": "Pelle che scotta facilmente e si abbronza poco.",
  "SkinSense (online service)": "SkinSense (servizio online)",
  "SkinSense is a third-party online service: the photos of your moles would be sent over the internet to a server we do not control. The photos are data about your health. Do you want to enable it?": "SkinSense è un servizio online di terzi: le foto dei tuoi nei verrebbero inviate via internet a un server che non controlliamo. Le foto sono dati sulla tua salute. Vuoi abilitarlo?",
  "SkinSense is on: the photo (without metadata) will be sent to an online service.": "SkinSense è attivo: la foto (senza metadati) verrà inviata a un servizio online.",
  "SkinSense turned off.": "SkinSense disattivato.",
  "SkinSense turned on.": "SkinSense abilitato.",
  "Smartphone apps and skin cancer risk: diagnostic accuracy": "App per smartphone e rischio di cancro della pelle: accuratezza diagnostica",
  "Some risk factors are present: careful sun protection and regular self-examination; a basic dermatological check-up is a good habit.": "Sono presenti alcuni fattori di rischio: protezione solare accurata e autoesame regolare; un controllo dermatologico di base è una buona abitudine.",
  "Something went wrong": "Qualcosa non ha funzionato",
  "Sometimes": "Qualche volta",
  "Source:": "Fonte:",
  "Sources": "Fonti",
  "Subscribe to the pay-per-call «One Call API» plan": "Iscriviti all'abbonamento «One Call API» a pagamento per chiamata",
  "Sun exposure": "Esposizione al sole",
  "Sunbeds": "Lampade",
  "Sunburns": "Scottature",
  "Sunburns with blisters (especially as a child or teenager)": "Scottature con vesciche (soprattutto da bambino o ragazzo)",
  "Switch user": "Cambia utente",
  "Syndromic": "Sindromico",
  "Systematic review": "Revisione sistematica",
  "Tanning lamps": "Lampade abbronzanti",
  "Tanning lamps or sunbeds": "Lampade o lettini abbronzanti",
  "Telomerase: promoter variants described in families with melanoma.": "Telomerasi: varianti del promotore descritte in famiglie con melanoma.",
  "Telomere gene (shelterin complex): rare variants in families with melanoma.": "Gene dei telomeri (complesso shelterin): varianti rare in famiglie con melanoma.",
  "Telomere gene: rare variants in some families with melanoma.": "Gene dei telomeri: varianti rare in alcune famiglie con melanoma.",
  "Test the key": "Prova la chiave",
  "Testing the key…": "Provo la chiave…",
  "The Open-Meteo service is not responding ({e}).": "Il servizio Open-Meteo non risponde ({e}).",
  "The OpenWeather key contains invalid characters (it is usually 32 letters/digits).": "La chiave OpenWeather contiene caratteri non validi (di solito sono 32 lettere/numeri).",
  "The Pillow library is old and has known security problems: update it with «py -m pip install -U pillow».": "La libreria Pillow è vecchia e ha problemi di sicurezza noti: aggiornala con «py -m pip install -U pillow».",
  "The WHO recommends protection from a UV index of 3.": "L'OMS consiglia di proteggersi a partire da un indice UV di 3.",
  "The analysis did not produce the report. Last lines of the log: {log}": "L'analisi non ha prodotto il rapporto. Ultime righe del log: {log}",
  "The analysis failed.": "L'analisi non è riuscita.",
  "The articles are chosen by an automatic search and have not been assessed by NeoTracker: read them with your doctor.": "Gli articoli sono scelti da una ricerca automatica e non sono stati valutati da NeoTracker: leggili con il tuo medico.",
  "The choice applies to all users of this computer. The original and binding text of the legal notices is the English one; the full text report stays in English.": "La scelta vale per tutti gli utenti di questo computer. Il testo originale e vincolante delle avvertenze legali è quello inglese; il rapporto di testo completo resta in inglese.",
  "The computer cannot determine the position. Search for the city by name.": "Il computer non riesce a determinare la posizione. Cerca la città per nome.",
  "The data entered meet at least one criterion described in the literature. We advise you to talk about it with your dermatologist or a medical geneticist (oncological genetic counselling): the specialist will decide whether and which test to offer, usually after counselling and, when possible, starting from an affected relative. Genes most cited by the guidelines: {geni}. The use of multigene panels is still under discussion among specialists: that is why counselling before the test matters.": "I dati inseriti rientrano in almeno un criterio descritto in letteratura. Ti consigliamo di parlarne con il dermatologo o con un medico genetista (consulenza genetica oncologica): sarà lo specialista a decidere se e quale test proporre, di norma dopo la consulenza e, quando possibile, partendo da un familiare affetto. Geni più citati dalle linee guida: {geni}. L'uso dei pannelli multigene è ancora oggetto di discussione tra gli specialisti: per questo conta la consulenza prima del test.",
  "The file is empty.": "Il file è vuoto.",
  "The file is not a readable image or is too large.": "Il file non è un'immagine leggibile o è troppo grande.",
  "The file is not a readable image, is damaged or has too many pixels (maximum {mp} megapixels).": "Il file non è un'immagine leggibile, è danneggiato o ha troppi pixel (massimo {mp} megapixel).",
  "The file is too large (maximum 40 MB).": "Il file è troppo grande (massimo 40 MB).",
  "The first analysis can take several minutes (the models are loaded into memory).": "La prima analisi può richiedere diversi minuti (i modelli vengono caricati in memoria).",
  "The image exceeds {mb} MB.": "L'immagine supera {mb} MB.",
  "The index is a forecast: the actual value depends on clouds, altitude and reflections.": "L'indice è una previsione: il valore reale dipende da nuvole, quota e riflessi.",
  "The information on risk, literature and genetics is for general information and does not replace the advice of a doctor or geneticist.": "Le informazioni su rischio, letteratura e genetica sono divulgative e non sostituiscono la consulenza di un medico o di un genetista.",
  "The key stays saved only on your computer and is never shown to, or sent to, the program's web page: the Python program uses it to call OpenWeather.": "La chiave resta salvata solo sul tuo computer e non viene mai mostrata né inviata alla pagina web del programma: la usa il programma Python per chiamare OpenWeather.",
  "The key will be deleted from this computer. You can enter it again whenever you want.": "La chiave sarà cancellata da questo computer. Potrai inserirla di nuovo quando vuoi.",
  "The location is saved only on this computer; it is sent to the weather service (rounded coordinates) to get the UV index.": "La posizione resta salvata solo su questo computer; viene inviata al servizio meteo (coordinate arrotondate) per ottenere l'indice UV.",
  "The methods are trained on photographs different from yours: changing light, distance or camera can change the answer.": "I metodi sono addestrati su fotografie diverse dalle tue: cambiare luce, distanza o fotocamera può cambiare la risposta.",
  "The middle hours of the day (about 11–16) have the highest index.": "Le ore centrali (circa 11-16) sono quelle con l'indice più alto.",
  "The most studied genes": "I geni più studiati",
  "The name": "Il nome",
  "The number of moles is one of the strongest risk factors.": "Il numero di nei è uno dei fattori di rischio più forti.",
  "The numbers match the following sheets. In the figure: the front view on the left, the back view on the right.": "I numeri corrispondono alle schede seguenti. Sulla figura: a sinistra la vista frontale, a destra quella posteriore.",
  "The p.E318K variant increases the risk of melanoma and renal carcinoma and is associated with many moles.": "La variante p.E318K aumenta il rischio di melanoma e di carcinoma renale e si associa a molti nei.",
  "The photo date cannot be in the future.": "La data della foto non può essere nel futuro.",
  "The photo exceeds {MAX_MB_FOTO} MB.": "La foto supera {MAX_MB_FOTO} MB.",
  "The photo exceeds {mb} MB: reduce it or choose another one.": "La foto supera i {mb} MB: riducila o scegline un'altra.",
  "The photo from {data} and its analysis report will be deleted permanently.": "La foto del {data} e il suo rapporto di analisi saranno cancellati per sempre.",
  "The photo stays on your computer: SkinSense (online service) is turned off.": "La foto resta sul tuo computer: SkinSense (servizio online) è disattivato.",
  "The profile, all moles, all photos and all reports of this user will be deleted permanently. This cannot be undone.": "Verranno cancellati per sempre il profilo, tutti i nei, tutte le foto e tutti i rapporti di questo utente. L'operazione non si può annullare.",
  "The program will shut down. An analysis in progress will be interrupted. Your data stays saved.": "Il programma si spegne. Un'analisi in corso viene interrotta. I dati restano salvati.",
  "The result also concerns blood relatives: that is why counselling before and after the test is part of the process.": "Il risultato riguarda anche i familiari di sangue: per questo la consulenza prima e dopo il test è parte del percorso.",
  "The results are experimental estimates and can be wrong in both directions: a reassuring result does not rule out a melanoma, and a result flagging attention does not mean there is one.": "I risultati sono stime sperimentali e possono sbagliare in entrambe le direzioni: un esito rassicurante non esclude un melanoma, un esito di attenzione non significa che ci sia.",
  "The two halves of the mole do not look alike.": "Le due metà del neo non si somigliano.",
  "The view must be 'fronte' or 'retro'.": "La vista deve essere 'fronte' o 'retro'.",
  "The «picked for you» sections use words linked to your profile (for example phototype or number of moles): if you prefer not to send them, do not scan that section.": "Le sezioni «scelte per te» usano parole legate al tuo profilo (per esempio fototipo o numero di nei): se preferisci non inviarle, non scansionare quella sezione.",
  "The «ugly duckling» also counts: a mole that looks different from all the others. Nodules that grow quickly or feel hard to the touch should be shown straight away. This reminder does not replace a medical visit.": "Conta anche il «brutto anatroccolo»: un neo diverso da tutti gli altri. I noduli che crescono rapidamente o sono duri al tatto vanno mostrati subito. Questo promemoria non sostituisce la visita.",
  "There are no moles to print.": "Non ci sono nei da stampare.",
  "These are measurements you entered: they are valid if always taken the same way. A mole that grows or changes is a good reason to show it to your dermatologist; the 6 mm line is just the classic reference of the ABCDE criteria.": "Sono misure inserite da te: valgono se prese sempre allo stesso modo. Un neo che cresce o cambia è un buon motivo per farlo vedere al dermatologo; la linea a 6 mm è solo il riferimento classico dei criteri ABCDE.",
  "They do not change the result of the neural networks, which only look at the pixels of the photo. They are used to: (1) put the risk in context, (2) choose the scientific literature suited to you, (3) check the criteria for genetic counselling, (4) calculate how long you can stay in the sun before burning. Everything stays on your computer.": "Non cambiano il risultato delle reti neurali, che guardano solo i pixel della foto. Servono a: (1) dare un contesto al rischio, (2) scegliere la letteratura scientifica adatta a te, (3) verificare i criteri per la consulenza genetica, (4) calcolare quanto tempo puoi stare al sole prima di scottarti. Tutto resta sul tuo computer.",
  "Thigh, left": "Coscia sinistra",
  "Thigh, right": "Coscia destra",
  "Thin clouds do not stop much of the UV: the index can stay high even with a hazy sky.": "Le nuvole sottili non fermano gran parte degli UV: l'indice può restare alto anche con il cielo velato.",
  "This browser does not offer geolocation: search for the city by name.": "Questo browser non offre la geolocalizzazione: cerca la città per nome.",
  "This is a cautious estimate that uses the lowest minimal erythema dose for your phototype; with reflections (water, snow, sand), altitude or already reddened skin the time is shorter.": "È una stima prudente che usa la dose minima di eritema più bassa del tuo fototipo; con riflessi (acqua, neve, sabbia), quota o pelle già arrossata il tempo si accorcia.",
  "This method sends the pixels of the photo (not the metadata) to an external server.": "Questo metodo prevede l'invio dei pixel della foto (non dei metadati) a un server esterno.",
  "This photo has not been analysed yet. The analysis compares several methods on the same image and tells you what each one answered.": "Questa foto non è ancora stata analizzata. L'analisi confronta più metodi sulla stessa immagine e ti dice cosa ha risposto ciascuno.",
  "This photo is being analysed: wait for it to finish.": "L'analisi di questa foto è in corso: attendi che finisca.",
  "This program helps you keep track of your moles over time: you mark them on a body map, keep their photos with the date and have them analysed by several methods. Start by creating your user.": "Questo programma ti aiuta a tenere traccia dei tuoi nei nel tempo: li segni su una mappa del corpo, ne conservi le foto con la data e li fai analizzare da più metodi. Inizia creando il tuo utente.",
  "This report is NOT a diagnosis. The programs used are research prototypes, not medical devices.": "Questo rapporto NON è una diagnosi. I programmi usati sono prototipi di ricerca, non dispositivi medici.",
  "This sheet collects data entered by the person and photos taken by them. The results of the automatic analysis are experimental, are not a diagnosis and do not replace a dermatological visit or dermoscopy.": "Questa scheda raccoglie dati inseriti dalla persona e foto da lei scattate. I risultati dell'analisi automatica sono sperimentali, non sono una diagnosi e non sostituiscono la visita dermatologica o la dermoscopia.",
  "Thresholds and colours of the WHO international scale. Sources:": "Soglie e colori della scala internazionale dell'OMS. Fonti:",
  "Time to re-photograph?": "Da rifotografare?",
  "To close NeoTracker, just close this window with the X at the top right: the program shuts down by itself.": "Per chiudere NeoTracker basta chiudere questa finestra con la X in alto a destra: il programma si spegne da solo.",
  "To confirm, type:": "Per confermare scrivi:",
  "To delete, type the exact name of the user in the confirmation.": "Per eliminare scrivi il nome esatto dell'utente nella conferma.",
  "To estimate the city, the program contacts the free service ipwho.is, which sees your internet address. Accuracy is at city level (it is sometimes wrong). Proceed?": "Per stimare la città il programma contatta il servizio gratuito ipwho.is, che vede il tuo indirizzo internet. La precisione è quella della città (a volte sbaglia). Procedo?",
  "To see how much sun burns you, enter your phototype in the": "Per vedere quanto sole ti scotta, indica il fototipo nel",
  "Today's UV index": "Indice UV di oggi",
  "Today's maximum": "Massimo di oggi",
  "Too many open connections.": "Troppi collegamenti aperti.",
  "Total diagnoses entered: {diagnosi}. Leachman 2009 counts melanoma and pancreatic cancer in 1st- and 2nd-degree relatives on the same side of the family; astrocytoma is included by the NCCN guidelines.": "Diagnosi totali indicate: {diagnosi}. Leachman 2009 considera melanoma e tumore del pancreas nei parenti di 1o e 2o grado dello stesso lato della famiglia; l'astrocitoma è incluso dalle linee guida NCCN.",
  "Try again": "Riprova",
  "Type": "Tipo",
  "Type a name.": "Scrivi un nome.",
  "Type at least 3 characters.": "Scrivi almeno 3 caratteri.",
  "Type {n}": "Tipo {n}",
  "UV index": "Indice UV",
  "UV index not available": "Indice UV non disponibile",
  "UV index source changed.": "Fonte dell'indice UV cambiata.",
  "UV index: data source": "Indice UV: fonte dei dati",
  "UV rays are harmful to unprotected skin today": "Oggi i raggi UV sono dannosi per pelle non protetta",
  "UV rays are low today": "Oggi i raggi UV sono bassi",
  "UV rays are very harmful today": "Oggi i raggi UV sono molto dannosi",
  "Ultraviolet rays are the main modifiable risk factor for melanoma. Here you can see how strong they are today where you are.": "I raggi ultravioletti sono il principale fattore di rischio modificabile per il melanoma. Qui vedi quanto sono forti oggi dove ti trovi.",
  "Unauthorised access.": "Accesso non autorizzato.",
  "Unauthorised request.": "Richiesta non autorizzata.",
  "Unexpected error: {e}": "Errore imprevisto: {e}",
  "Unknown address.": "Indirizzo sconosciuto.",
  "Unknown section.": "Sezione sconosciuta.",
  "Unsaved changes…": "Modifiche non salvate…",
  "Unsupported format: JPG, PNG, WEBP or BMP are required.": "Formato non supportato: servono JPG, PNG, WEBP o BMP.",
  "Unsupported format: JPG, PNG, WEBP or BMP are required. iPhone HEIC photos must be converted to JPG (camera settings: 'Most Compatible').": "Formato non supportato: servono JPG, PNG, WEBP o BMP. Le foto HEIC degli iPhone vanno convertite in JPG (impostazioni fotocamera: 'Più compatibile').",
  "Upper abdomen, left": "Addome alto sinistro",
  "Upper abdomen, right": "Addome alto destro",
  "Use of tanning lamps or sunbeds": "Uso di lampade o lettini abbronzanti",
  "Use the date written in the photo, if there is one": "Usa la data scritta nella foto, se c'è",
  "User created. Fill in the profile: it helps put the results in context.": "Utente creato. Compila il profilo: serve a contestualizzare i risultati.",
  "User deleted.": "Utente eliminato.",
  "User not found.": "Utente non trovato.",
  "Version": "Versione",
  "Very dark skin. Does not burn.": "Pelle molto scura. Non scotta.",
  "Very fair skin. Always burns, never tans (often red hair, freckles).": "Pelle molto chiara. Scotta sempre, non si abbronza mai (spesso capelli rossi, lentiggini).",
  "Very high": "Molto alto",
  "WHO/WMO/UNEP/ICNIRP - Global Solar UV Index: A Practical Guide (2002)": "OMS/OMM/UNEP/ICNIRP - Global Solar UV Index: A Practical Guide (2002)",
  "Warning: I did not find App 1's .venv environment; using the current Python.": "Attenzione: non ho trovato l'ambiente .venv di App 1, uso il Python corrente.",
  "Weather and UV data:": "Dati meteo e UV:",
  "Welcome to NeoTracker": "Benvenuto in NeoTracker",
  "What is this information used for?": "A che cosa servono questi dati?",
  "What to do": "Cosa fare",
  "What to know before a genetic test": "Cosa sapere prima di un test genetico",
  "Wheel = zoom · drag = move · double click = enlarge": "Rotella = zoom · trascina = sposta · doppio clic = ingrandisci",
  "When you noticed it, whether it itches, whether it has changed…": "Quando l'hai notato, se prude, se è cambiato…",
  "When you subscribe, the default daily limit is 2,000 calls: in the «Billing plans» tab of your account you can lower it to 1,000, so you spend nothing. NeoTracker uses very few (at most 4 every 10 minutes, only when you open the UV Index page).": "Alla sottoscrizione il limite giornaliero predefinito è di 2.000 chiamate: nella scheda «Billing plans» del tuo account puoi abbassarlo a 1.000, così non spendi nulla. NeoTracker ne usa poche (al massimo 4 ogni 10 minuti, solo quando apri la pagina Indice UV).",
  "Where they are": "Dove si trovano",
  "Who are you?": "Chi sei?",
  "With or without a test, for people with a family history, sun protection, skin self-examination and regular dermatological check-ups remain essential.": "Con o senza test, per chi ha una storia familiare restano fondamentali la protezione dal sole, l'autoesame della pelle e i controlli dermatologici periodici.",
  "With the data entered you do not meet the most commonly used criteria. Genetic testing for melanoma is indicated only in a small minority of people and is not offered routinely. If your family history changes or you have doubts, update your profile and talk to your dermatologist.": "Con i dati inseriti non rientri nei criteri più usati. Il test genetico per il melanoma è indicato solo in una piccola minoranza di persone e non viene proposto di routine. Se la tua storia familiare cambia o hai dubbi, aggiorna il profilo e parlane col dermatologo.",
  "With the data entered, no known risk factors appear. Complete your profile if information is missing.": "Con i dati inseriti non risultano fattori di rischio noti. Completa il profilo se mancano informazioni.",
  "With your phototype ({fototipo})": "Con il tuo fototipo ({fototipo})",
  "Without Pillow the image must be a JPG/PNG under 400 KB (the page reduces it by itself: try again with the 'Choose image' function).": "Senza Pillow l'immagine deve essere un JPG/PNG sotto i 400 KB (la pagina la riduce da sola: riprova con la funzione 'Scegli immagine').",
  "Woman": "Donna",
  "Work or prolonged activity outdoors": "Lavoro o attività prolungata all'aperto",
  "Yes": "Sì",
  "Yes, enable": "Sì, abilita",
  "Yes, estimate the city": "Sì, stima la città",
  "Yes, negative": "Sì, negativo",
  "Yes, positive": "Sì, positivo",
  "Yes, uninformative": "Sì, non informativo",
  "You can close this window. To reopen the program, use the «NeoTracker» icon on the Desktop.": "Puoi chiudere questa finestra. Per riaprirlo usa l'icona «NeoTracker» sul Desktop.",
  "You can keep using the app. If you close the window the analysis is not lost: the program finishes the work and then shuts down by itself.": "Puoi continuare a usare l'app. Se chiudi la finestra l'analisi non va persa: il programma finisce il lavoro e poi si spegne da solo.",
  "You can use your own photo, a drawing or an icon. The image is cropped to a square and reduced, stays only on this computer and is never used for mole analysis.": "Puoi usare una tua foto, un disegno o un'icona. L'immagine viene ritagliata a quadrato e ridotta, resta solo su questo computer e non viene mai usata per l'analisi dei nei.",
  "You chose OpenWeather but the key is missing (Settings): showing Open-Meteo data.": "Hai scelto OpenWeather ma manca la chiave (Impostazioni): mostro i dati di Open-Meteo.",
  "You chose OpenWeather but there is no key yet: until one is added, the program uses Open-Meteo.": "Hai scelto OpenWeather ma non c'è ancora una chiave: finché manca, il programma usa Open-Meteo.",
  "You said you have already had a genetic test: take the report to your dermatologist.": "Hai indicato di aver già eseguito un test genetico: porta il referto al dermatologo.",
  "Your data (including health data) stays on this computer. Only the requests you turn on leave it: UV index (approximate coordinates), PubMed searches (only the search terms) and, only if you enable it, sending the photo to SkinSense.": "I dati (anche di salute) restano su questo computer. Escono solo le richieste che attivi tu: indice UV (coordinate approssimate), ricerche su PubMed (solo i termini cercati) e, solo se lo attivi, l'invio della foto a SkinSense.",
  "Your data against the criteria": "I tuoi dati rispetto ai criteri",
  "Your moles ({n})": "I tuoi nei ({n})",
  "Zoom out": "Riduci",
  "a few": "poche",
  "a few freckles": "poche efelidi",
  "about {minuti} minutes": "circa {minuti} minuti",
  "actinic keratosis, a pre-cancerous lesion": "cheratosi attinica, lesione pre-cancerosa",
  "active only if you enable it below": "attivo solo se lo abiliti qui sotto",
  "address not allowed (https only)": "indirizzo non ammesso (solo https)",
  "all methods with a result flag a mole that needs attention": "tutti i metodi con risultato indicano un neo da attenzionare",
  "and click on the exact spot on the body (zoom in with the wheel to be more precise).": "e clicca sul punto esatto del corpo (ingrandisci con la rotella per essere più preciso).",
  "and confirm the email.": "e conferma l'email.",
  "average of {n} models; mean score {media} (threshold 0)": "media di {n} modelli; punteggio medio {media} (soglia 0)",
  "back": "retro",
  "back of the hand": "dorso della mano",
  "basal cell carcinoma, a skin cancer": "carcinoma basocellulare, tumore della pelle",
  "between the fingers or toes": "spazio tra le dita",
  "black hair": "capelli neri",
  "blond hair": "capelli biondi",
  "blue or grey eyes": "occhi azzurri o grigi",
  "brown hair": "capelli castani",
  "cannot start: {e}": "impossibile avviare: {e}",
  "confidence {perc}": "sicurezza {perc}",
  "connection failed: {motivo}": "connessione non riuscita: {motivo}",
  "dark eyes": "occhi scuri",
  "dermoscopic": "dermoscopica",
  "dermoscopy": "dermoscopia",
  "don't know": "non so",
  "e.g. 4.5": "es. 4,5",
  "ear": "orecchio",
  "eyelid": "palpebra",
  "fewer than 25": "meno di 25",
  "free, no account or key needed": "gratuita, senza account né chiave",
  "front": "fronte",
  "green eyes": "occhi verdi",
  "grey or white hair": "capelli grigi o bianchi",
  "in clear skies and without protection, at today's peak the skin may redden in": "a cielo sereno e senza protezione, al picco di oggi la pelle può arrossarsi in",
  "in the panel": "nel pannello",
  "in {n} day.": "in {n} giorno.",
  "in {n} days.": "in {n} giorni.",
  "invalid response from the service": "risposta non valida dal servizio",
  "lip": "labbro",
  "location from internet address not available": "posizione da indirizzo internet non disponibile",
  "man": "uomo",
  "many": "molte",
  "many freckles": "molte efelidi",
  "melanoma": "melanoma",
  "melanoma detected": "melanoma rilevato",
  "melanoma not detected": "melanoma non rilevato",
  "melanoma prob. {perc}": "prob. melanoma {perc}",
  "naevus, i.e. a benign mole": "nevo, cioe' neo benigno",
  "name@example.com (optional)": "nome@esempio.it (facoltativa)",
  "never": "mai",
  "no": "no",
  "no cases indicated": "nessun caso indicato",
  "no freckles": "nessuna efelide",
  "no method flagged the mole (this does not rule out a melanoma)": "nessun metodo ha segnalato il neo (questo non esclude un melanoma)",
  "no result available": "nessun risultato disponibile",
  "normal photo": "foto normale",
  "often": "spesso",
  "optional: requires a personal key of your own": "facoltativa: richiede una tua chiave personale",
  "other": "altro",
  "output interpreted as the 6 skin classes (not verifiable)": "uscita letta come le 6 classi di pelle (non verificabile)",
  "over 2 hours (very low UV)": "oltre 2 ore (UV molto basso)",
  "palm of the hand": "palmo della mano",
  "phototype {tipo}": "fototipo {tipo}",
  "probability of malignancy estimated by the model: {pm}": "probabilita' di malignita' stimata dal modello: {pm}",
  "red hair": "capelli rossi",
  "response too large": "risposta troppo grande",
  "response without a lesion name: {risposta}": "risposta senza nome della lesione: {risposta}",
  "scalp": "cuoio capelluto",
  "seborrhoeic keratosis, benign": "cheratosi seborroica, benigna",
  "service address not allowed (https required)": "indirizzo del servizio non ammesso (serve https)",
  "service page": "pagina del servizio",
  "service unreachable: {ultimo_errore}": "servizio non raggiungibile: {ultimo_errore}",
  "significant": "rilevante",
  "skin photos": "foto di pelle",
  "sole of the foot": "pianta del piede",
  "sometimes": "qualche volta",
  "squamous cell carcinoma, a skin cancer": "carcinoma squamocellulare, tumore della pelle",
  "stopped after {minuti} minutes (maximum time)": "interrotto dopo {minuti} minuti (tempo massimo)",
  "studies on PubMed": "studi su PubMed",
  "the App 1 models have not been downloaded: they are still Git LFS placeholders. Open PowerShell in the folder {cartella}, run 'git lfs pull', then try again.": "i modelli di App 1 non sono stati scaricati: sono ancora dei segnaposto Git LFS. Apri PowerShell nella cartella {cartella} e lancia 'git lfs pull', poi riprova.",
  "the first 1,000 calls per day are free, later ones are charged. OpenWeather may ask for a payment card to activate it: check the conditions on their website.": "le prime 1.000 chiamate al giorno sono gratuite, le successive si pagano. OpenWeather può chiedere una carta di pagamento per attivarlo: controlla le condizioni sul loro sito.",
  "the methods do not agree with each other": "i metodi non concordano tra loro",
  "the model has {n} outputs: meaning unknown": "il modello ha {n} uscite: significato sconosciuto",
  "the photo does not open as an image ({tipo}): {dettaglio}": "la foto non si apre come immagine ({tipo}): {dettaglio}",
  "the trained weights are missing: in the folder {cartella} there are no files model_fold_0.bin ... model_fold_4.bin. The repository does not contain them: they must be produced with train.py on the SIIM-ISIC dataset.": "mancano i pesi addestrati: nella cartella {cartella} non ci sono i file model_fold_0.bin ... model_fold_4.bin. Il repository non li contiene: vanno prodotti con train.py sul dataset SIIM-ISIC.",
  "timed out or network unavailable": "tempo scaduto o rete non disponibile",
  "today": "oggi",
  "top of the foot": "dorso del piede",
  "ukalwa / melanoma-detection (Android app)": "ukalwa / melanoma-detection (app Android)",
  "under the nail (foot)": "sotto l'unghia (piede)",
  "under the nail (hand)": "sotto l'unghia (mano)",
  "unreadable response: {e}": "risposta illeggibile: {e}",
  "updated": "aggiornato",
  "vatsal30 / Melanoma-Detection (PyTorch)": "vatsal30 / Melanoma-Detection (PyTorch)",
  "woman": "donna",
  "yes": "sì",
  "yes, negative": "sì, negativo",
  "yes, positive": "sì, positivo",
  "yes, uninformative": "sì, non informativo",
  "yesterday": "ieri",
  "{avviso} The Open-Meteo service is not responding ({e}).": "{avviso} Il servizio Open-Meteo non risponde ({e}).",
  "{cosa} cannot be empty.": "{cosa} non può essere vuoto.",
  "{cosa} is too long (maximum {massimo} characters).": "{cosa} è troppo lungo (massimo {massimo} caratteri).",
  "{file_modello} is still a Git LFS placeholder: run 'git lfs pull' in the folder {cartella}.": "{file_modello} e' ancora un segnaposto Git LFS: lancia 'git lfs pull' nella cartella {cartella}.",
  "{file_pesi} is still a Git LFS placeholder: open PowerShell in the folder {cartella} and run 'git lfs pull'.": "{file_pesi} e' ancora un segnaposto Git LFS: apri PowerShell nella cartella {cartella} e lancia 'git lfs pull'.",
  "{foto} · last {quando}": "{foto} · ultima {quando}",
  "{giorno} at {ora}: UV index {uvi} ({categoria})": "{giorno} ore {ora}: indice UV {uvi} ({categoria})",
  "{nome} · {mb} MB · click to change": "{nome} · {mb} MB · clicca per cambiare",
  "{nome}: enter a number.": "{nome}: inserisci un numero.",
  "{nome}: error.": "{nome}: errore.",
  "{nome}: not available.": "{nome}: non disponibile.",
  "{nome}: the value must be between {minimo} and {massimo}.": "{nome}: il valore deve essere tra {minimo} e {massimo}.",
  "{n} articles found on PubMed · search of {data}": "{n} articoli trovati su PubMed · ricerca del {data}",
  "{n} articles found on PubMed · search of {data} (saved)": "{n} articoli trovati su PubMed · ricerca del {data} (salvata)",
  "{n} articles on melanoma and «{termine}»": "{n} articoli su melanoma e «{termine}»",
  "{n} day": "{n} giorno",
  "{n} day has passed between the two photos.": "Tra le due foto è passato {n} giorno.",
  "{n} days": "{n} giorni",
  "{n} days ago": "{n} giorni fa",
  "{n} days have passed between the two photos.": "Tra le due foto sono passati {n} giorni.",
  "{n} first-degree relative(s) with melanoma": "{n} parente/i di primo grado con melanoma",
  "{n} model files out of 10": "{n} file modello su 10",
  "{n} model files out of 5": "{n} file modello su 5",
  "{n} mole": "{n} neo",
  "{n} mole on this sheet": "{n} neo in questa scheda",
  "{n} moles": "{n} nei",
  "{n} moles on this sheet": "{n} nei in questa scheda",
  "{n} months ago": "{n} mesi fa",
  "{n} of {tot} methods responded": "{n} metodi su {tot} hanno risposto",
  "{n} of {tot}: {et}": "{n} su {tot}: {et}",
  "{n} other relative(s) with melanoma": "{n} altro/i parente/i con melanoma",
  "{n} photo": "{n} foto",
  "{n} photos": "{n} foto",
  "{n} photos in {giorni} (from {da} to {a}).": "{n} foto in {giorni} (dal {da} al {a}).",
  "{n} with astrocytoma": "{n} con astrocitoma",
  "{n} with pancreatic cancer": "{n} con tumore del pancreas",
  "{n} with uveal melanoma": "{n} con melanoma uveale",
  "{n} year": "{n} anno",
  "{n} year ago": "{n} anno fa",
  "{n} years": "{n} anni",
  "{n} years ago": "{n} anni fa",
  "{vista} · position {x}% from the left, {y}% from the top": "{vista} · posizione {x}% da sinistra, {y}% dall'alto",
  "…of which 1st-degree": "…di cui di 1° grado",
  "← All moles": "← Tutti i nei"
};
'''
WEB_FILES["/i18n_it.js"] = ("text/javascript; charset=utf-8", _WEB_I18N_IT_JS.encode("utf-8"))

_WEB_ICONA_PNG_B64 = """
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
"""
WEB_FILES["/icona.png"] = ("image/png", base64.b64decode(_WEB_ICONA_PNG_B64))

_WEB_INDEX_HTML = r'''<!DOCTYPE html>
<html lang="en">
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
  <nav id="menu" aria-label="Sections"></nav>
  <div id="utente-box"></div>
</header>
<main id="vista" tabindex="-1"></main>
<footer id="piede">NeoTracker is not a medical tool and does not make diagnoses. For any mole that changes, bleeds, itches or worries you, see a dermatologist.</footer>
<div id="toast" role="status" aria-live="polite"></div>
<dialog id="dialogo"></dialog>
<dialog id="lightbox"></dialog>
<div id="stampa" aria-hidden="true"></div>
<script src="/i18n_it.js"></script>
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
   stampa.js - printable sheet for the dermatologist (map, history, measurements)
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  /* The profile values are Italian codes saved in the database: here they become sentences in the chosen language.
     Each sentence is whole (not "hair" + colour) because agreement changes from language to language. */
  const SESSO = { F: NT.t('woman'), M: NT.t('man'), altro: NT.t('other') };
  const FOTOTIPI = ['I', 'II', 'III', 'IV', 'V', 'VI'];
  const CAPELLI = { neri: NT.t('black hair'), castani: NT.t('brown hair'), biondi: NT.t('blond hair'), rossi: NT.t('red hair'), grigi: NT.t('grey or white hair') };
  const OCCHI = { scuri: NT.t('dark eyes'), verdi: NT.t('green eyes'), azzurri: NT.t('blue or grey eyes') };
  const EFELIDI = { nessuna: NT.t('no freckles'), poche: NT.t('a few freckles'), molte: NT.t('many freckles') };
  const N_NEVI = { '<25': NT.t('fewer than 25'), '25-49': '25–49', '50-99': '50–99', '100+': NT.t('100 or more') };
  const ATIPICI = { no: NT.t('no'), si: NT.t('yes'), 'non so': NT.t("don't know") };
  const SCOTTATURE = { mai: NT.t('never'), poche: NT.t('a few'), molte: NT.t('many') };
  const LAMPADE = { mai: NT.t('never'), alcune: NT.t('sometimes'), spesso: NT.t('often') };
  const TEST_GEN = { si_positivo: NT.t('yes, positive'), si_negativo: NT.t('yes, negative'), si_non_informativo: NT.t('yes, uninformative') };
  const ESITO_STAMPA = {
    attenzione: NT.t('all methods with a result flag a mole that needs attention'),
    discordante: NT.t('the methods do not agree with each other'),
    benigno: NT.t('no method flagged the mole (this does not rule out a melanoma)'),
    nessuno: NT.t('no result available'),
  };
  const lab = (tab, codice) => tab[codice] || codice;

  function riepilogoProfilo(u) {
    const p = u.profilo, righe = [];
    if (u.eta !== null && u.eta !== undefined) righe.push([NT.t('Age'), NT.tp(u.eta, '{n} year', '{n} years')]);
    if (p.sesso) righe.push([NT.t('Sex'), lab(SESSO, p.sesso)]);
    if (p.fototipo) righe.push([NT.t('Phototype'), FOTOTIPI[p.fototipo - 1]]);
    const fen = [p.capelli && lab(CAPELLI, p.capelli), p.occhi && lab(OCCHI, p.occhi), p.efelidi && lab(EFELIDI, p.efelidi)].filter(Boolean).join(', ');
    if (fen) righe.push([NT.t('Appearance'), fen]);
    if (p.n_nevi) righe.push([NT.t('Number of moles'), lab(N_NEVI, p.n_nevi)]);
    if (p.nevi_atipici) righe.push([NT.t('Atypical moles'), lab(ATIPICI, p.nevi_atipici)]);
    if (p.scottature) righe.push([NT.t('Sunburns'), lab(SCOTTATURE, p.scottature)]);
    if (p.lampade) righe.push([NT.t('Tanning lamps'), lab(LAMPADE, p.lampade)]);
    if (p.melanomi_personali) righe.push([NT.t('Melanomas already diagnosed'), String(p.melanomi_personali)]);
    if (p.fam_compilata) {
      const f = [];
      if (p.fam_melanoma_1grado) f.push(NT.t('{n} first-degree relative(s) with melanoma', { n: p.fam_melanoma_1grado }));
      if (p.fam_melanoma_altri) f.push(NT.t('{n} other relative(s) with melanoma', { n: p.fam_melanoma_altri }));
      if (p.fam_pancreas) f.push(NT.t('{n} with pancreatic cancer', { n: p.fam_pancreas }));
      if (p.fam_astrocitoma) f.push(NT.t('{n} with astrocytoma', { n: p.fam_astrocitoma }));
      if (p.fam_uveale) f.push(NT.t('{n} with uveal melanoma', { n: p.fam_uveale }));
      righe.push([NT.t('Family history'), f.length ? f.join('; ') : NT.t('no cases indicated')]);
    }
    if (p.test_genetico && p.test_genetico !== 'no') righe.push([NT.t('Genetic test already done'), lab(TEST_GEN, p.test_genetico)]);
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
      const dd = (prima.diametro_mm && ultima.diametro_mm) ? ' ' + NT.t('Diameter: from {da} to {a} mm.', { da: NT.num(prima.diametro_mm), a: NT.num(ultima.diametro_mm) }) : '';
      variazione = NT.t('{n} photos in {giorni} (from {da} to {a}).', { n: foto.length, giorni: NT.tp(giorni, '{n} day', '{n} days'), da: NT.fmtData(prima.scattata_il), a: NT.fmtData(ultima.scattata_il) }) + dd;
    }
    const mostra = foto.length <= 8 ? foto : [foto[0], foto[1]].concat(foto.slice(-6));
    return h('section', { class: 'st-neo' },
      h('h3', {}, h('span', { class: 'st-badge' }, num), ' ', n.nome, n.regione ? ' – ' + NT.tr(n.regione) : ' – ' + (n.vista === 'retro' ? NT.t('back') : NT.t('front'))),
      n.note ? h('p', { class: 'st-nota' }, NT.t('Notes:') + ' ' + n.note) : null,
      foto.length ? [
        variazione ? h('p', {}, variazione) : h('p', {}, prima.diametro_mm ? NT.t('1 photo from {data}, diameter {mm} mm.', { data: NT.fmtData(prima.scattata_il), mm: NT.num(prima.diametro_mm) }) : NT.t('1 photo from {data}.', { data: NT.fmtData(prima.scattata_il) })),
        h('div', { class: 'st-foto' }, mostra.map(f => h('figure', {}, h('img', { src: '/foto/' + f.id + '/mini?l=480', alt: NT.t('Photo from {data}', { data: NT.fmtData(f.scattata_il) }) }),
          h('figcaption', {}, NT.fmtData(f.scattata_il), f.diametro_mm ? ' · ' + NT.num(f.diametro_mm) + ' mm' : '', f.tipo === 'dermoscopica' ? ' · ' + NT.t('dermoscopic') : '')))),
        foto.length > mostra.length ? h('p', { class: 'st-nota' }, NT.t('Showing {n} photos out of {tot}.', { n: mostra.length, tot: foto.length })) : null,
        ultima.esito ? h('p', { class: 'st-nota' }, NT.t('Latest automatic analysis ({data}): {esito}. Research tool, not diagnostic.', { data: NT.fmtData(ultima.scattata_il), esito: ESITO_STAMPA[ultima.esito] || ultima.esito })) : null,
      ] : h('p', { class: 'st-nota' }, NT.t('No photo recorded yet.')));
  }

  NT.stampaNei = async function (ids) {
    if (!S.utente) return;
    const area = NT.$('#stampa');
    try {
      NT.toast(NT.t('Preparing the sheet…'), 'info');
      await NT.ricaricaUtente();
      await NT.ricaricaNei();
      const scelti = S.nei.filter(n => !n.archiviato && (!ids || ids.includes(n.id)));
      if (!scelti.length) { NT.toast(NT.t('There are no moles to print.'), 'errore'); return; }
      const dettagli = await Promise.all(scelti.map(n => NT.get('/api/nevi/' + n.id)));
      const tutti = S.nei.filter(n => !n.archiviato);
      const numero = id => tutti.findIndex(n => n.id === id) + 1;
      const u = S.utente, rischio = u.rischio.presenti;
      const prof = riepilogoProfilo(u);
      const nuovo = h('div', { class: 'st-pagina' },
        h('header', { class: 'st-testata' }, h('div', {}, h('h1', {}, NT.t('Mole sheet – {nome}', { nome: u.nome })), h('div', { class: 'st-sotto' }, NT.t('Printed on {data} with NeoTracker', { data: NT.fmtData(NT.oggiISO()) }))),
          h('div', { class: 'st-sotto' }, NT.tp(scelti.length, '{n} mole on this sheet', '{n} moles on this sheet'))),
        h('section', { class: 'st-profilo' }, h('h2', {}, NT.t('Personal details')),
          prof.length ? h('dl', {}, prof.map(([k, v]) => [h('dt', {}, k), h('dd', {}, v)])) : h('p', { class: 'st-nota' }, NT.t('Profile not filled in.')),
          rischio.length ? h('p', {}, h('strong', {}, NT.t('Risk factors indicated:') + ' '), rischio.map(r => NT.tr(r.etichetta)).join('; ') + '.') : null),
        h('section', {}, h('h2', {}, NT.t('Where they are')), mappaStampa(scelti.map(n => Object.assign({}, n))),
          h('p', { class: 'st-nota' }, NT.t('The numbers match the following sheets. In the figure: the front view on the left, the back view on the right.'))),
        dettagli.map(d => schedaNeo(numero(d.nevo.id), d.nevo, d.foto)),
        h('footer', { class: 'st-avviso' }, NT.t('This sheet collects data entered by the person and photos taken by them. The results of the automatic analysis are experimental, are not a diagnosis and do not replace a dermatological visit or dermoscopy.')));
      // numbers consistent with the map: it uses the global numbering, not that of the selection
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
   NeoTracker - style sheet
   Colours: teal #0e5a6b (main), orange #e36414 (accent), light background.
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

/* ---------- header ---------- */
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

/* ---------- cards, buttons, fields ---------- */
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

/* ---------- windows and messages ---------- */
dialog { border: none; border-radius: 14px; padding: 0; box-shadow: 0 18px 60px rgba(0, 0, 0, .35); max-width: min(92vw, 520px); width: 100%; color: var(--testo); }
dialog::backdrop { background: rgba(15, 30, 38, .55); }
#dialogo.larga { max-width: min(96vw, 1000px); }
.dlg { padding: 1.3rem 1.4rem; max-height: 88vh; overflow: auto; }
#lightbox { max-width: 96vw; background: #10181d; }
#lightbox .lb { padding: .8rem; } #lightbox .lb-barra { display: flex; align-items: center; gap: .6rem; color: #fff; margin-bottom: .6rem; }
#lightbox img { max-width: 100%; max-height: 80vh; display: block; margin: 0 auto; border-radius: 6px; }
#toast { position: fixed; left: 50%; bottom: 1.4rem; transform: translate(-50%, 30px); background: #243942; color: #fff; padding: .7rem 1.1rem; border-radius: 10px; opacity: 0; pointer-events: none; transition: opacity .2s, transform .2s; max-width: min(92vw, 560px); z-index: 100; box-shadow: 0 6px 24px rgba(0, 0, 0, .3); }
#toast.visibile { opacity: 1; transform: translate(-50%, 0); } #toast.errore { background: #9c1c1c; } #toast.ok { background: #1f6b3a; }

/* ---------- users ---------- */
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

/* ---------- body map ---------- */
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

/* ---------- list of moles and detail ---------- */
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

/* ---------- analysis ---------- */
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

/* ---------- profile ---------- */
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

/* ---------- literature and genetics ---------- */
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

/* ---------- UV index and settings ---------- */
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

/* ---------- dermatologist sheet (print only) ---------- */
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

/* ---------- narrow screens ---------- */
@media (max-width: 1050px) {
  .mappa-layout, .profilo-layout { grid-template-columns: 1fr; }
  .mappa-scheda, .riepilogo-profilo { position: static; }
  .mappa-box { height: 70vh; }
}
@media (max-width: 720px) {
  #testata { flex-wrap: wrap; gap: .5rem; } .utente-cambia { display: none; } .riga-2, .confronto-coppia { grid-template-columns: 1fr; }
  #vista { padding: .8rem .6rem 1.5rem; } .voce span { display: none; } .voce { padding: .5rem; }
}

/* ---------- touch-ups ---------- */
.fototipo strong, .fototipo small { display: block; } .fototipo small { color: var(--muted); font-size: .8rem; line-height: 1.35; }
.fattori li small { display: block; color: var(--muted); font-size: .82rem; } .fattori li .chip { margin-left: .4rem; }
.spunte-griglia { margin-bottom: .9rem; }
.riga-spinner { display: flex; align-items: center; gap: .8rem; }
'''
WEB_FILES["/style.css"] = ("text/css; charset=utf-8", _WEB_STYLE_CSS.encode("utf-8"))

_WEB_UTIL_JS = r'''/* ============================================================================
   util.js - helper functions common to all the pages
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT;                      // created by i18n.js (which is loaded first)
  Object.assign(NT, { S: { utenti: [], utente: null, nei: [], imp: {}, stato: {} }, viste: {}, pulizie: [] });

  NT.$ = (s, r) => (r || document).querySelector(s);
  NT.$$ = (s, r) => Array.from((r || document).querySelectorAll(s));

  /* Creates elements without ever interpreting the text as HTML (so users' names and notes are safe). */
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

  /* Empties an element and fills it with elements, texts, lists (even nested); ignores null and false. */
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

  /* Trusted HTML (only SVG/icons written by us, with numbers and texts already "escaped") */
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

  /* ---------- calls to the program (API) ---------- */
  NT.api = async function (metodo, url, corpo, opz) {
    opz = opz || {};
    const init = { method: metodo, headers: { 'X-NeoTracker': '1' } };
    if (opz.raw) { init.body = opz.raw; init.headers['Content-Type'] = opz.tipo || 'application/octet-stream'; }
    else if (corpo !== undefined && corpo !== null) { init.body = JSON.stringify(corpo); init.headers['Content-Type'] = 'application/json'; }
    let r;
    try { r = await fetch(url, init); }
    catch (e) { throw new Error(NT.t('I cannot reach NeoTracker. The program may have been closed: reopen it from the icon on the Desktop.')); }
    const t = await r.text();
    let d = null;
    try { d = t ? JSON.parse(t) : null; } catch (e) { /* non-JSON response */ }
    if (!r.ok) { const er = new Error((d && d.errore) ? NT.tr(d.errore) : NT.t('Error {codice}', { codice: r.status })); er.codice = r.status; throw er; }
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

  /* ---------- dialog windows ---------- */
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
      const ok = h('button', { class: 'btn ' + (opz.pericolo ? 'btn-pericolo' : 'btn-pri'), disabled: !!opz.scrivi, onclick: () => fine(campo ? campo.value.trim() : true) }, opz.si || NT.t('Confirm'));
      const d = NT.apriDialogo(h('div', {},
        h('h3', {}, titolo), h('p', {}, testo),
        opz.scrivi ? h('label', { class: 'etichetta' }, NT.t('To confirm, type:') + ' ', h('strong', {}, opz.scrivi)) : null, campo,
        h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => fine(false) }, NT.t('Cancel')), ok)));
      d.addEventListener('close', () => fine(false), { once: true });
      if (campo) campo.focus();
    });
  };

  document.addEventListener('click', ev => {                  // click outside the window = closes
    const d = ev.target;
    if (d instanceof HTMLDialogElement && d.open) {
      const r = d.getBoundingClientRect();
      if (ev.clientX < r.left || ev.clientX > r.right || ev.clientY < r.top || ev.clientY > r.bottom) d.close();
    }
  });

  /* ---------- dates and miscellaneous ---------- */
  NT.oggiISO = () => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
  NT.dataDaMs = ms => { const d = new Date(ms); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
  NT.giorniTra = (a, b) => Math.round((new Date(b + 'T12:00:00') - new Date(a + 'T12:00:00')) / 86400000);
  NT.ls = {
    leggi: k => { try { return localStorage.getItem(k); } catch (e) { return null; } },
    scrivi: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* not available */ } },
  };
  NT.debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

  /* spinner and placeholder */
  NT.caricamento = (testo) => h('div', { class: 'caricamento' }, h('span', { class: 'spinner' }), testo || NT.t('Loading…'));
  NT.vuoto = (titolo, testo) => h('div', { class: 'vuoto' }, h('strong', {}, titolo), testo ? h('p', {}, testo) : null);

  /* Label of the analysis outcome (deliberately cautious colours: "benigno" is never a reassuring green) */
  NT.ESITI = {
    attenzione: { testo: NT.t('Needs attention'), cls: 'esito-att' },
    discordante: { testo: NT.t('Methods disagree'), cls: 'esito-disc' },
    benigno: { testo: NT.t('No alarm from the models'), cls: 'esito-ben' },
    nessuno: { testo: NT.t('No result'), cls: 'esito-nes' },
  };
  NT.chipEsito = (esito) => { const e = NT.ESITI[esito]; return e ? h('span', { class: 'chip ' + e.cls }, e.testo) : null; };

  NT.link = (url, testo) => h('a', { href: url, target: '_blank', rel: 'noopener noreferrer', class: 'link-est' }, testo, NT.icona('esterno', 13));

  /* Takes an image file and returns (as a JPEG Blob) a "side x side" square cropped at the centre.
     The new JPEG does not contain the metadata of the original (GPS position, camera model...). */
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
          g.fillStyle = '#ffffff'; g.fillRect(0, 0, lato, lato);          // transparent parts become white
          g.imageSmoothingQuality = 'high';
          g.drawImage(img, sx, sy, q, q, 0, 0, lato, lato);
          c.toBlob(b => b ? res(b) : rej(new Error(NT.t('I cannot reduce this image.'))), 'image/jpeg', 0.88);
        } catch (e) { rej(new Error(NT.t('I cannot read this image. Try a JPG or a PNG.'))); }
        finally { URL.revokeObjectURL(url); }
      };
      img.onerror = () => { URL.revokeObjectURL(url); rej(new Error(NT.t('I cannot read this image. Try a JPG or a PNG.'))); };
      img.src = url;
    });
  };

  /* Start-up notice (first start): NeoTracker is not a medical device. It must be accepted to continue. */
  NT.mostraAvvertenze = function () {
    const spunta = h('input', { type: 'checkbox', id: 'ck-avvertenze' });
    const ok = h('button', { class: 'btn btn-pri', disabled: true, onclick: async () => {
      try {
        NT.S.imp = await NT.api('PUT', '/api/impostazioni', { avvertenze_accettate: NT.S.stato.avvertenze_versione });
        NT.chiudiDialogo();
      } catch (e) { NT.errore(e); }
    } }, NT.t('Accept and continue'));
    spunta.addEventListener('change', () => { ok.disabled = !spunta.checked; });
    const d = NT.apriDialogo(h('div', { class: 'avvertenze' },
      h('h3', {}, NT.t('Before you start')),
      h('p', {}, h('strong', {}, NT.t('NeoTracker is not a medical device and does not make diagnoses.') + ' '),
        NT.t('It is a personal tool for organising the photos of your moles and comparing over time the results of some research models. It is not certified or approved by any health authority.')),
      h('ul', {},
        h('li', {}, NT.t('The results are experimental estimates and can be wrong in both directions: a reassuring result does not rule out a melanoma, and a result flagging attention does not mean there is one.')),
        h('li', {}, NT.t('A mole that changes (shape, borders, colour, size), bleeds, itches or worries you must be shown to a dermatologist, whatever the app says. Regular check-ups with the dermatologist remain irreplaceable.')),
        h('li', {}, NT.t('The information on risk, literature and genetics is for general information and does not replace the advice of a doctor or geneticist.')),
        h('li', {}, NT.t('Your data (including health data) stays on this computer. Only the requests you turn on leave it: UV index (approximate coordinates), PubMed searches (only the search terms) and, only if you enable it, sending the photo to SkinSense.')),
        h('li', {}, NT.t('If you enter data or photos of other people, make sure you have their consent.'))),
      h('label', { class: 'spunta grande' }, spunta, ' ' + NT.t('I have read and understood these notices')),
      h('div', { class: 'azioni' },
        h('button', { class: 'btn', onclick: () => { NT.api('POST', '/api/chiudi').catch(() => {}); NT.battitoAttivo = false; if (NT.presenza) NT.presenza.close(); document.title = NT.t('NeoTracker closed'); NT.chiudiDialogo(); } }, NT.t('Quit the program')),
        ok)));
    d.addEventListener('cancel', ev => ev.preventDefault());           // the Esc key does not skip the notice
    return d;
  };

  /* clean-ups to run when the page changes (timers, observers...) */
  NT.alCambioPagina = fn => NT.pulizie.push(fn);
})();
'''
WEB_FILES["/util.js"] = ("text/javascript; charset=utf-8", _WEB_UTIL_JS.encode("utf-8"))

_WEB_V_IMPOSTAZIONI_JS = r'''/* ============================================================================
   v_impostazioni.js - source of the UV index (Open-Meteo / OpenWeather), SkinSense, PubMed email, installation status
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

    /* ---------------- interface language ---------------- */
    // 'auto' = the system language; to apply the choice it saves and reloads the page
    const selLingua = h('select', { class: 'campo', id: 'sel-lingua', 'aria-label': NT.t('Interface language'),
      onchange: async () => { if (await salva({ lingua: selLingua.value })) location.reload(); else selLingua.value = NT.linguaScelta; } },
      h('option', { value: 'auto' }, NT.t('Automatic (same as the system)')),
      NT.LINGUE.map(l => h('option', { value: l[0] }, l[1])));
    selLingua.value = NT.linguaScelta;
    const sezLingua = h('section', { class: 'scheda' }, h('h2', {}, NT.t('Language')),
      h('label', { for: 'sel-lingua', class: 'blocco' }, NT.t('Interface language')), selLingua,
      h('p', { class: 'piccolo muted' }, NT.t('The choice applies to all users of this computer. The original and binding text of the legal notices is the English one; the full text report stays in English.')));

    /* ---------------- UV index: data source ---------------- */
    const esitoProva = h('div', { class: 'prova-esito', role: 'status' });
    const campoChiave = h('input', { type: 'password', class: 'campo', autocomplete: 'off', spellcheck: 'false', maxlength: 64,
      placeholder: '', 'aria-label': NT.t('OpenWeather key') });
    const segnapostoChiave = () => S.imp.ha_chiave_owm ? NT.t('Key saved ({finale}) — type a new one to replace it', { finale: S.imp.chiave_owm_finale }) : NT.t('Paste the key here (32 letters and digits)');
    campoChiave.placeholder = segnapostoChiave();
    const sezOWM = h('section', { class: 'scheda' });
    function disegnaOWM() {
      campoChiave.placeholder = segnapostoChiave();
      const ow = S.imp.fonte_uv === 'openweather';
      // a row with a dot: choosing changes the source at once and redraws the section
      const scelta = (valore, titolo, desc) => h('label', { class: 'riga-inline' },
        h('input', { type: 'radio', name: 'fonte-uv', value: valore, checked: S.imp.fonte_uv === valore,
          onchange: async () => { if (await salva({ fonte_uv: valore }, NT.t('UV index source changed.'))) { NT.riempi(esitoProva); disegnaOWM(); } } }),
        h('span', {}, h('strong', {}, titolo), ' ', h('span', { class: 'piccolo muted' }, desc)));
      NT.riempi(sezOWM, h('h2', {}, NT.t('UV index: data source')),
        scelta('open-meteo', NT.t('Open-Meteo (default)'), NT.t('free, no account or key needed')),
        scelta('openweather', 'OpenWeather', NT.t('optional: requires a personal key of your own')),
        !ow ? h('p', { class: 'piccolo muted' }, NT.t('Weather and UV data:') + ' ', NT.link('https://open-meteo.com/', 'Open-Meteo.com'), ' ' + NT.t('(CC BY 4.0 licence). The free service is for personal, non-commercial use.') + ' ',
          NT.t('City search also uses Open-Meteo.')) : null,
        ow ? h('div', { class: 'banda ' + (S.imp.ha_chiave_owm ? 'verde' : 'giallo') }, S.imp.ha_chiave_owm ? NT.t('OpenWeather key saved ({finale}).', { finale: S.imp.chiave_owm_finale }) : NT.t('You chose OpenWeather but there is no key yet: until one is added, the program uses Open-Meteo.')) : null,
        ow ? h('div', { class: 'riga-inline' }, campoChiave,
          h('button', { class: 'btn btn-pri', onclick: async () => { const k = campoChiave.value.trim(); if (!k) { NT.toast(NT.t('Paste the key first.'), 'errore'); return; } if (await salva({ openweather_key: k }, NT.t('Key saved.'))) { campoChiave.value = ''; NT.riempi(esitoProva); disegnaOWM(); } } }, NT.t('Save')),
          S.imp.ha_chiave_owm ? h('button', { class: 'btn', onclick: provaChiave }, NT.t('Test the key')) : null,
          S.imp.ha_chiave_owm ? h('button', { class: 'btn-testo pericolo', onclick: async () => { if (await NT.conferma(NT.t('Remove the key?'), NT.t('The key will be deleted from this computer. You can enter it again whenever you want.'), { si: NT.t('Remove'), pericolo: true }) && await salva({ openweather_key: '' }, NT.t('Key removed.'))) { NT.riempi(esitoProva); disegnaOWM(); } } }, NT.t('Remove')) : null) : null,
        ow ? esitoProva : null,
        ow ? h('details', { class: 'abstract' }, h('summary', {}, NT.t('How to get the key')),
          h('ol', { class: 'passi' },
            h('li', {}, NT.t('Create a free account at') + ' ', NT.link('https://home.openweathermap.org/users/sign_up', 'openweathermap.org'), ' ' + NT.t('and confirm the email.')),
            h('li', {}, NT.t('Open the «API keys» page of your account and copy the key.')),
            h('li', {}, NT.t('Subscribe to the pay-per-call «One Call API» plan') + ' (', NT.link('https://openweathermap.org/api/one-call-4', NT.t('service page')), '): ' + NT.t('the first 1,000 calls per day are free, later ones are charged. OpenWeather may ask for a payment card to activate it: check the conditions on their website.')),
            h('li', {}, NT.t('When you subscribe, the default daily limit is 2,000 calls: in the «Billing plans» tab of your account you can lower it to 1,000, so you spend nothing. NeoTracker uses very few (at most 4 every 10 minutes, only when you open the UV Index page).')),
            h('li', {}, NT.t('Paste the key above and press «Test the key». After subscribing, the key can take a few minutes to activate. The program tries One Call 4.0 first and, if the key belongs to an older plan, One Call 3.0.'))),
          h('p', { class: 'piccolo muted' }, NT.t("The key stays saved only on your computer and is never shown to, or sent to, the program's web page: the Python program uses it to call OpenWeather."))) : null);
    }
    async function provaChiave() {
      NT.riempi(esitoProva, NT.caricamento(NT.t('Testing the key…')));
      try { const r = await NT.api('POST', '/api/impostazioni/prova-owm'); NT.riempi(esitoProva, h('div', { class: 'banda ' + (r.ok ? 'verde' : 'rosso') }, NT.tr(r.messaggio))); }
      catch (e) { NT.riempi(esitoProva, h('div', { class: 'banda rosso' }, e.message)); }
    }
    disegnaOWM();

    /* ---------------- photo analysis ---------------- */
    const swSkin = h('input', { type: 'checkbox', id: 'sw-skin', checked: !!S.imp.usa_skinsense, onchange: async () => {
      if (swSkin.checked) {
        const ok = await NT.conferma(NT.t('Send the photos to SkinSense?'), NT.t('SkinSense is a third-party online service: the photos of your moles would be sent over the internet to a server we do not control. The photos are data about your health. Do you want to enable it?'), { si: NT.t('Yes, enable') });
        if (!ok) { swSkin.checked = false; return; }
      }
      if (!await salva({ usa_skinsense: swSkin.checked }, swSkin.checked ? NT.t('SkinSense turned on.') : NT.t('SkinSense turned off.'))) swSkin.checked = !swSkin.checked;
    } });
    const sezAnalisi = h('section', { class: 'scheda' }, h('h2', {}, NT.t('Photo analysis')),
      h('label', { class: 'interruttore', for: 'sw-skin' }, swSkin, h('span', {}, h('strong', {}, NT.t('Also use SkinSense (online service)')),
        h('span', { class: 'piccolo muted blocco' }, NT.t('Off by default: with the other methods the photo never leaves this computer.')))),
      h('p', { class: 'piccolo muted' }, NT.t('Age, sex and phenotype do not change the output of the neural networks: they are used to show you the risk factors, choose the literature, evaluate the genetics criteria and estimate the time to sunburn.')));

    /* ---------------- PubMed ---------------- */
    const campoMail = h('input', { type: 'email', class: 'campo', value: S.imp.ncbi_email || '', placeholder: NT.t('name@example.com (optional)'), maxlength: 120, autocomplete: 'email', 'aria-label': NT.t('Email for PubMed') });
    const sezMail = h('section', { class: 'scheda' }, h('h2', {}, NT.t('Literature: PubMed')),
      h('p', {}, NT.t("Searches use PubMed's public E-utilities. NCBI asks, as a courtesy, for a contact email: it is optional and is sent only to PubMed.")),
      h('div', { class: 'riga-inline' }, campoMail, h('button', { class: 'btn', onclick: () => salva({ ncbi_email: campoMail.value }, NT.t('Email saved.')) }, NT.t('Save'))));

    /* ---------------- status ---------------- */
    const st = S.stato;
    const sezStato = h('section', { class: 'scheda' }, h('h2', {}, NT.t('Installation status')),
      h('ul', { class: 'stato-lista' }, st.progetti.map(p => h('li', { class: p.presente ? 'si' : 'no' },
        h('span', { class: 'esito-criterio' }, p.presente ? NT.icona('ok', 16) : NT.icona('avviso', 16)), h('div', {}, h('strong', {}, NT.tr(p.nome)), h('div', { class: 'piccolo muted' }, NT.tr(p.dettaglio)))))),
      h('div', { class: 'piccolo' }, st.batch ? [NT.t('Analysis program:') + ' ', h('code', {}, st.batch)] : h('span', { class: 'errore-campo' }, NT.t('Analysis program (melanoma_batch.py) not found: photos are saved but cannot be analysed.'))),
      h('div', { class: 'piccolo' }, NT.t('Projects folder:') + ' ', h('code', {}, st.repo)),
      h('div', { class: 'piccolo' }, NT.t('Folder with your data (copy it for backup):') + ' ', h('code', {}, st.cartella_dati)),
      st.pillow_obsoleto ? h('div', { class: 'errore-campo' }, NT.t('The Pillow library is old and has known security problems: update it with «py -m pip install -U pillow».')) : null,
      h('div', { class: 'piccolo muted' }, NT.t('Version') + ' ' + st.versione + (st.ha_pillow ? '' : ' · ' + NT.t('Pillow is not installed: previews will use the original photos (install with «py -m pip install pillow»).'))));

    /* ---------------- shutdown ---------------- */
    const sezEsci = h('section', { class: 'scheda' }, h('h2', {}, NT.t('Closing the program')),
      h('p', {}, NT.t('To close NeoTracker, just close this window with the X at the top right: the program shuts down by itself.') + ' ' +
        NT.t('If it is still analysing a photo, it finishes the analysis first and then shuts down. The button below does the same thing.')),
      h('button', { class: 'btn btn-pericolo', onclick: async () => {
        if (!await NT.conferma(NT.t('Close NeoTracker?'), NT.t('The program will shut down. An analysis in progress will be interrupted. Your data stays saved.'), { si: NT.t('Close the program'), pericolo: true })) return;
        NT.battitoAttivo = false;
        if (NT.presenza) NT.presenza.close();       // it must not reconnect while the program is shutting down
        try { await NT.api('POST', '/api/chiudi'); } catch (e) { /* it is shutting down */ }
        NT.riempi(cont, h('div', { class: 'pagina stretta' }, h('div', { class: 'scheda' }, h('h2', {}, NT.t('NeoTracker is closed')), h('p', {}, NT.t('You can close this window. To reopen the program, use the «NeoTracker» icon on the Desktop.')))));
      } }, NT.icona('esci', 18), NT.t('Close NeoTracker')));

    NT.riempi(cont, h('div', { class: 'pagina' }, h('h1', {}, NT.t('Settings')), sezLingua, sezOWM, sezAnalisi, sezMail, sezStato, sezEsci));
  };
})();
'''
WEB_FILES["/v_impostazioni.js"] = ("text/javascript; charset=utf-8", _WEB_V_IMPOSTAZIONI_JS.encode("utf-8"))

_WEB_V_MAPPA_JS = r'''/* ============================================================================
   v_mappa.js - body map, list of moles, photo history and analysis
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h, $ = NT.$;

  const SEDI_UTILI = [NT.m('palm of the hand'), NT.m('back of the hand'), NT.m('sole of the foot'), NT.m('top of the foot'), NT.m('between the fingers or toes'),
    NT.m('under the nail (hand)'), NT.m('under the nail (foot)'), NT.m('scalp'), NT.m('ear'), NT.m('eyelid'), NT.m('lip')];
  const GIORNI_PROMEMORIA = 90;

  let mappa = null, modo = 'lista', bozza = null, dett = null, fotoSel = null, pollTimer = null;
  let etichettaRegione = null, panel = null, formFotoAperto = false, sedeBozzaManuale = false;
  const inAnalisi = new Set();

  const nomiAuto = () => new Set(['fronte', 'retro'].flatMap(v => window.Corpo.regioni(v).map(r => r.nome)));
  /* The sites from the map and the suggested ones are always saved in English (so they work in every language);
     the user sees and types them in his/her own language: here we go back from the translated text to the English one. */
  const sedeCanonica = (() => {
    let inverso = null;
    return testo => {
      const v = String(testo || '').trim();
      if (NT.lingua === 'en') return v;
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
      NT.icona('mirino', 18), NT.t('Add mole'));
    const suggerimento = h('span', { class: 'mappa-hint', id: 'mappa-hint' }, NT.t('Wheel = zoom · drag = move · double click = enlarge'));
    const barra = h('div', { class: 'mappa-barra' }, btnAggiungi, suggerimento,
      h('span', { class: 'spazio' }),
      h('button', { class: 'btn-icona', title: NT.t('Zoom out'), onclick: () => mappa.zoomSu(1 / 1.5) }, NT.icona('meno')),
      h('button', { class: 'btn-icona', title: NT.t('Enlarge'), onclick: () => mappa.zoomSu(1.5) }, NT.icona('piu')),
      h('button', { class: 'btn-icona', title: NT.t('Show the whole body'), onclick: () => mappa.reset() }, NT.icona('reset')));
    const box = h('div', { class: 'mappa-box' });
    etichettaRegione = h('div', { class: 'regione-etichetta' }, NT.t('Move the pointer over the body to see the area'));
    const legenda = h('div', { class: 'legenda' },
      h('span', {}, h('i', { class: 'pallino pieno' }), NT.t('Mole with photos')),
      h('span', {}, h('i', { class: 'pallino vuoto' }), NT.t('No photos yet')),
      h('span', {}, h('i', { class: 'pallino rosso' }), NT.t('Analysis: needs attention')),
      h('span', { class: 'lato-nota' }, NT.t("R = patient's right · L = left")));
    panel = h('aside', { class: 'pannello', 'aria-live': 'polite' });
    cont.replaceChildren(h('div', { class: 'mappa-layout' }, h('section', { class: 'scheda mappa-scheda' }, barra, box, etichettaRegione, legenda), panel));

    mappa = new window.Corpo.MappaCorpo(box, {
      onRegione: nome => { etichettaRegione.textContent = nome ? NT.tr(nome) : NT.t('Move the pointer over the body to see the area'); },
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
    if (hint) hint.textContent = on ? NT.t('Click on the exact spot on the body where the mole is (you can zoom in first)') : NT.t('Wheel = zoom · drag = move · double click = enlarge');
    if (on) { aggiornaMarcatori(); renderPannello(); }
  }

  function tornaLista() {
    stopPoll(); modo = 'lista'; dett = null; fotoSel = null; bozza = null;
    if (mappa) { mappa.modalitaAggiunta(false); }
    attivaAggiunta(false);
    aggiornaMarcatori(); renderPannello();
  }

  /* ---------------------------- new mole ---------------------------------- */
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
  const testoPos = p => NT.t('{vista} · position {x}% from the left, {y}% from the top',
    { vista: p.vista === 'fronte' ? NT.t('Front') : NT.t('Back'), x: Math.round(p.x * 100), y: Math.round(p.y * 100) });

  function pannelloBozza() {
    const nome = h('input', { type: 'text', class: 'campo', maxlength: 60, value: NT.t('Mole {n}', { n: S.nei.length + 1 }), id: 'campo-nome-bozza' });
    const sede = h('input', { type: 'text', class: 'campo', maxlength: 80, list: 'sedi-utili', value: bozza.regione ? NT.tr(bozza.regione) : '', id: 'campo-sede-bozza',
      oninput: () => { sedeBozzaManuale = true; } });
    const note = h('textarea', { class: 'campo', rows: 3, maxlength: 1000, placeholder: NT.t('When you noticed it, whether it itches, whether it has changed…') });
    const salva = h('button', { class: 'btn btn-pri', onclick: async () => {
      salva.disabled = true;
      try {
        const r = await NT.api('POST', '/api/utenti/' + S.utente.id + '/nevi',
          { nome: nome.value, vista: bozza.vista, x: bozza.x, y: bozza.y, regione: sedeCanonica(sede.value), note: note.value });
        await NT.ricaricaNei();
        bozza = null; mappa.setBozza(null);
        formFotoAperto = true;
        await selezionaNeo(r.id);
        NT.toast(NT.t('Mole saved. Now add the first photo: it will be your "baseline photo".'), 'ok');
      } catch (e) { salva.disabled = false; NT.errore(e); }
    } }, NT.t('Save mole'));
    return h('div', { class: 'scheda' },
      h('h2', {}, NT.t('New mole')),
      h('p', { class: 'piccolo', id: 'info-pos-bozza' }, testoPos(bozza)),
      h('p', { class: 'piccolo' }, NT.icona('mirino', 14), ' ' + NT.t('Drag the dot on the map to correct the position; zoom in with the wheel for maximum precision.')),
      h('label', { class: 'etichetta' }, NT.t('Name'), nome),
      h('label', { class: 'etichetta' }, NT.t('Site (editable)'), sede,
        h('datalist', { id: 'sedi-utili' }, opzioniSedi())),
      h('label', { class: 'etichetta' }, NT.t('Notes'), note),
      h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => tornaLista() }, NT.t('Cancel')), salva));
  }

  /* ------------------------- moving a mole -------------------------- */
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
      NT.toast(corpo.regione ? NT.t('Location updated: {regione}.', { regione: NT.tr(corpo.regione) }) : NT.t('Location updated.'), 'ok');
    } catch (e) { NT.errore(e); await NT.ricaricaNei(); aggiornaMarcatori(); }
  }

  /* --------------------------- selecting a mole -------------------------- */
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

  /* ============================== PANEL ================================== */
  function renderPannello() {
    if (!panel) return;
    stopPoll();
    const top = panel.scrollTop;
    panel.replaceChildren(modo === 'bozza' && bozza ? pannelloBozza() : modo === 'neo' && dett ? pannelloNeo() : pannelloLista());
    panel.scrollTop = modo === 'neo' ? top : 0;
    if (modo === 'neo' && fotoSel) caricaAnalisi(fotoSel);
  }

  /* ------------------------------ list of moles ----------------------------- */
  function schedaLista(n) {
    const giorni = n.giorni_da_ultima;
    const promemoria = giorni !== null && giorni >= GIORNI_PROMEMORIA && !n.archiviato;
    return h('button', { class: 'neo-card', onclick: () => selezionaNeo(n.id, true) },
      h('span', { class: 'neo-num' + (n.n_foto === 0 ? ' vuoto' : '') + (n.ultimo_esito === 'attenzione' || n.ultimo_esito === 'discordante' ? ' rosso' : '') }, numDi(n.id)),
      n.ultima_foto_id ? h('img', { class: 'neo-thumb', src: '/foto/' + n.ultima_foto_id + '/mini?l=120', alt: '', loading: 'lazy' }) : h('span', { class: 'neo-thumb vuota' }, NT.icona('foto', 22)),
      h('span', { class: 'neo-info' },
        h('strong', {}, n.nome),
        h('span', { class: 'sotto' }, n.regione ? NT.tr(n.regione) : (n.vista === 'fronte' ? NT.t('Front') : NT.t('Back'))),
        h('span', { class: 'sotto' }, n.n_foto === 0 ? NT.t('No photos: add the first one')
          : NT.t('{foto} · last {quando}', { foto: NT.tp(n.n_foto, '{n} photo', '{n} photos'), quando: NT.fraseGiorni(giorni) })),
        h('span', { class: 'chips' }, NT.chipEsito(n.ultimo_esito), promemoria ? h('span', { class: 'chip chip-neutro' }, NT.t('Time to re-photograph?')) : null)));
  }

  function pannelloLista() {
    const lista = attivi(), arch = S.nei.filter(n => n.archiviato);
    const vuoto = !S.nei.length;
    return h('div', { class: 'scheda' },
      h('div', { class: 'testa-lista' }, h('h2', {}, vuoto ? NT.t('No moles yet') : NT.t('Your moles ({n})', { n: lista.length })),
        lista.length ? h('button', { class: 'btn-testo', title: NT.t('Print a sheet with all the moles'), onclick: () => NT.stampaNei(lista.map(n => n.id)) }, NT.icona('stampa', 16), NT.t('Sheet for the dermatologist')) : null),
      vuoto
        ? h('ol', { class: 'passi' },
          h('li', {}, NT.t('Press'), ' ', h('strong', {}, NT.t('Add mole')), ' ' + NT.t('and click on the exact spot on the body (zoom in with the wheel to be more precise).')),
          h('li', {}, NT.t('Give the mole a name and check the site.')),
          h('li', {}, NT.t('Add the first photo: it becomes your baseline photo, and every later photo will follow how the mole evolves.')))
        : h('div', { class: 'neo-elenco' }, lista.map(schedaLista)),
      arch.length ? h('details', { class: 'archiviati' }, h('summary', {}, NT.t('Archived moles ({n})', { n: arch.length })),
        arch.map(n => h('div', { class: 'riga-arch' }, h('span', {}, n.nome + (n.regione ? ' – ' + NT.tr(n.regione) : '')),
          h('button', { class: 'btn-testo', onclick: async () => { try { await NT.api('PATCH', '/api/nevi/' + n.id, { archiviato: false }); await NT.ricaricaNei(); aggiornaMarcatori(); renderPannello(); } catch (e) { NT.errore(e); } } }, NT.t('Restore'))))) : null,
      !vuoto ? h('p', { class: 'piccolo muted' }, NT.t('Click a mole in the list or on the map to see its photo history.')) : null);
  }

  /* ------------------------------ mole detail ------------------------------ */
  function pannelloNeo() {
    const n = dett.nevo, foto = dett.foto;
    const salva = async (campi) => { try { await NT.api('PATCH', '/api/nevi/' + n.id, campi); await ricaricaDettaglio(); } catch (e) { NT.errore(e); } };

    const nome = h('input', { type: 'text', class: 'campo titolo-modifica', maxlength: 60, value: n.nome, 'aria-label': NT.t('Mole name'),
      onchange: () => { if (nome.value.trim()) salva({ nome: nome.value }); else nome.value = n.nome; } });
    const sede = h('input', { type: 'text', class: 'campo', maxlength: 80, list: 'sedi-utili', value: n.regione ? NT.tr(n.regione) : '', placeholder: NT.t('Site'),
      onchange: () => salva({ regione: sedeCanonica(sede.value) }) });
    const note = h('textarea', { class: 'campo', rows: 2, maxlength: 1000, placeholder: NT.t('Notes on the mole…'), onchange: () => salva({ note: note.value }) }, n.note);

    const testa = h('div', { class: 'scheda' },
      h('div', { class: 'neo-testa' },
        h('button', { class: 'btn-testo', onclick: () => tornaLista() }, NT.t('← All moles')),
        h('span', { class: 'spazio' }),
        h('button', { class: 'btn-icona', title: NT.t('Centre on the map'), onclick: () => mappa.centraSu(n, 5) }, NT.icona('mirino')),
        h('button', { class: 'btn-icona', title: NT.t('Print the sheet for this mole'), onclick: () => NT.stampaNei([n.id]) }, NT.icona('stampa')),
        h('button', { class: 'btn-icona', title: NT.t('Archive (removes it from the map, keeps the data)'), onclick: async () => {
          await salva({ archiviato: true }); tornaLista(); NT.toast(NT.t('Mole archived. You will find it at the bottom of the list.'), 'ok'); } }, NT.icona('archivio')),
        h('button', { class: 'btn-icona pericolo', title: NT.t('Delete this mole and its photos'), onclick: async () => {
          const si = await NT.conferma(NT.t('Delete «{nome}»?', { nome: n.nome }),
            NT.tp(foto.length, 'Its only photo and the analysis reports will be deleted permanently.', 'All its {n} photos and the analysis reports will be deleted permanently.'),
            { si: NT.t('Delete'), pericolo: true, scrivi: foto.length ? n.nome : null });
          if (!si) return;
          try { await NT.api('DELETE', '/api/nevi/' + n.id); await NT.ricaricaNei(); tornaLista(); NT.toast(NT.t('Mole deleted.'), 'ok'); } catch (e) { NT.errore(e); } } }, NT.icona('cestino'))),
      h('div', { class: 'neo-titolo' }, h('span', { class: 'neo-num grande' + (foto.length ? '' : ' vuoto') }, numDi(n.id)), nome),
      h('div', { class: 'riga-2' }, h('label', { class: 'etichetta' }, NT.t('Site'), sede,
        h('datalist', { id: 'sedi-utili' }, opzioniSedi())),
        h('div', { class: 'etichetta' }, NT.t('Location'), h('div', { class: 'piccolo' }, testoPos(n), h('br'), NT.t('Drag the dot on the map to move it.')))),
      h('label', { class: 'etichetta' }, NT.t('Notes'), note));

    const sezioni = [testa, sezioneStorico(n, foto), formFoto(n)];
    const grafico = graficoDiametro(foto);
    if (grafico) sezioni.push(grafico);
    sezioni.push(h('div', { class: 'scheda', id: 'box-analisi' }, h('h3', {}, NT.t('Automatic analysis')), NT.caricamento(NT.t('Checking status…'))));
    return h('div', { class: 'pila' }, sezioni);
  }

  /* ----------------------------- photo history ----------------------------- */
  function sezioneStorico(n, foto) {
    if (!foto.length) {
      return h('div', { class: 'scheda' }, h('h3', {}, NT.t('Photo history')),
        NT.vuoto(NT.t('No photos yet'), NT.t('Add the first photo below: it will be the starting point to see whether the mole changes over time.')));
    }
    const f = foto.find(x => x.id === fotoSel) || foto[foto.length - 1];
    const striscia = h('div', { class: 'striscia' }, foto.map(x => h('button', { class: 'miniatura' + (x.id === f.id ? ' sel' : ''), title: NT.fmtData(x.scattata_il) + (x.diametro_mm ? ' · ' + NT.num(x.diametro_mm) + ' mm' : ''),
      onclick: () => { fotoSel = x.id; renderPannello(); } },
      h('img', { src: '/foto/' + x.id + '/mini?l=240', alt: NT.t('Photo from {data}', { data: NT.fmtData(x.scattata_il) }), loading: 'lazy' }),
      h('span', { class: 'data' }, NT.fmtData(x.scattata_il)),
      x.esito && x.esito !== 'nessuno' ? h('i', { class: 'punto-esito ' + NT.ESITI[x.esito].cls, title: NT.ESITI[x.esito].testo }) : null)));
    const precedente = foto[foto.indexOf(f) - 1];
    const meta = h('div', { class: 'foto-meta' },
      h('span', {}, h('strong', {}, NT.fmtData(f.scattata_il)), ' · ', f.tipo === 'dermoscopica' ? NT.t('dermoscopic') : NT.t('normal photo')),
      f.diametro_mm ? h('span', {}, NT.t('Diameter:') + ' ', h('strong', {}, NT.num(f.diametro_mm) + ' mm'),
        precedente && precedente.diametro_mm ? h('span', { class: 'delta' }, ' ' + NT.t('({variazione} mm since the previous photo)', { variazione: (f.diametro_mm - precedente.diametro_mm >= 0 ? '+' : '') + NT.num(f.diametro_mm - precedente.diametro_mm) })) : null) : null,
      f.note ? h('span', { class: 'muted' }, f.note) : null);
    return h('div', { class: 'scheda' },
      h('div', { class: 'testa-lista' }, h('h3', {}, NT.t('Photo history ({n})', { n: foto.length })),
        foto.length >= 2 ? h('button', { class: 'btn-testo', onclick: () => dialogoConfronto(foto, f) }, NT.icona('confronta', 16), NT.t('Compare')) : null),
      striscia,
      h('button', { class: 'anteprima', title: NT.t('Click to see the original photo full screen'), onclick: () => apriLightbox(f) },
        h('img', { src: '/foto/' + f.id + '/mini?l=960', alt: NT.t('Photo from {data}', { data: NT.fmtData(f.scattata_il) }) })),
      meta,
      h('div', { class: 'azioni-foto' },
        h('button', { class: 'btn-testo', onclick: () => dialogoModificaFoto(f) }, NT.t('Edit date/measurement')),
        h('button', { class: 'btn-testo pericolo', onclick: async () => {
          const si = await NT.conferma(NT.t('Delete this photo?'), NT.t('The photo from {data} and its analysis report will be deleted permanently.', { data: NT.fmtData(f.scattata_il) }), { si: NT.t('Delete photo'), pericolo: true });
          if (!si) return;
          try { await NT.api('DELETE', '/api/foto/' + f.id); await ricaricaDettaglio(); fotoSel = dett.foto.length ? dett.foto[dett.foto.length - 1].id : null; renderPannello(); NT.toast(NT.t('Photo deleted.'), 'ok'); } catch (e) { NT.errore(e); } } }, NT.t('Delete photo'))));
  }

  function apriLightbox(f) {
    const d = $('#lightbox');
    d.replaceChildren(h('div', { class: 'lb' },
      h('div', { class: 'lb-barra' }, h('strong', {}, NT.fmtData(f.scattata_il)), h('span', { class: 'spazio' }), h('button', { class: 'btn', onclick: () => d.close() }, NT.t('Close'))),
      h('img', { src: '/foto/' + f.id + '/originale', alt: NT.t('Original photo') })));
    d.showModal();
  }

  function dialogoModificaFoto(f) {
    const data = h('input', { type: 'date', class: 'campo', value: f.scattata_il, max: NT.oggiISO() });
    const diam = h('input', { type: 'text', class: 'campo', inputmode: 'decimal', value: f.diametro_mm === null ? '' : NT.num(f.diametro_mm), placeholder: NT.t('e.g. 4.5') });
    const tipo = h('select', { class: 'campo' }, h('option', { value: 'normale', selected: f.tipo === 'normale' }, NT.t('Normal photo')), h('option', { value: 'dermoscopica', selected: f.tipo === 'dermoscopica' }, NT.t('Dermoscopic')));
    const nota = h('textarea', { class: 'campo', rows: 2, maxlength: 1000 }, f.note);
    NT.apriDialogo(h('div', {}, h('h3', {}, NT.t('Edit photo')),
      h('label', { class: 'etichetta' }, NT.t('Date the photo was taken'), data), h('label', { class: 'etichetta' }, NT.t('Diameter (mm)'), diam),
      h('label', { class: 'etichetta' }, NT.t('Type'), tipo), h('label', { class: 'etichetta' }, NT.t('Notes'), nota),
      h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => NT.chiudiDialogo() }, NT.t('Cancel')),
        h('button', { class: 'btn btn-pri', onclick: async () => {
          try {
            await NT.api('PATCH', '/api/foto/' + f.id, { scattata_il: data.value, diametro_mm: diam.value, tipo: tipo.value, note: nota.value });
            NT.chiudiDialogo(); await ricaricaDettaglio(); renderPannello();
          } catch (e) { NT.errore(e); }
        } }, NT.t('Save')))));
  }

  /* ----------------------------- adding a photo ----------------------------- */
  function formFoto(n) {
    let file = null;
    const anteprima = h('div', { class: 'drop-testo' }, NT.icona('foto', 26), h('span', {}, NT.t('Drag a photo here or click to choose one')), h('small', {}, NT.t('JPG, PNG, WEBP or BMP · up to 60 MB')));
    const input = h('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp,image/bmp,.jpg,.jpeg,.png,.webp,.bmp', class: 'nascosto' });
    const drop = h('label', { class: 'drop' }, input, anteprima);
    const data = h('input', { type: 'date', class: 'campo', value: NT.oggiISO(), max: NT.oggiISO(), oninput: () => { usaExif.checked = false; } });
    const usaExif = h('input', { type: 'checkbox', checked: true });
    const tipo = h('select', { class: 'campo' }, h('option', { value: 'normale' }, NT.t('Normal photo (smartphone)')), h('option', { value: 'dermoscopica' }, NT.t('Dermoscopic')));
    const diam = h('input', { type: 'text', class: 'campo', inputmode: 'decimal', placeholder: NT.t('e.g. 4.5') });
    const nota = h('input', { type: 'text', class: 'campo', maxlength: 1000, placeholder: NT.t('Optional') });
    const analizza = h('input', { type: 'checkbox', checked: true });
    const btn = h('button', { class: 'btn btn-pri', disabled: true }, NT.icona('foto', 18), NT.t('Save photo'));

    function scegli(fl) {
      if (!fl) return;
      if (!/^image\//.test(fl.type) && !/\.(jpe?g|png|webp|bmp)$/i.test(fl.name)) { NT.toast(NT.t('Choose an image file (JPG, PNG, WEBP or BMP).'), 'errore'); return; }
      if (fl.size > (S.stato.max_mb_foto || 60) * 1048576) { NT.toast(NT.t('The photo exceeds {mb} MB: reduce it or choose another one.', { mb: S.stato.max_mb_foto || 60 }), 'errore'); return; }
      file = fl;
      data.value = NT.dataDaMs(fl.lastModified); usaExif.checked = true;
      const url = URL.createObjectURL(fl);
      anteprima.replaceChildren(h('img', { src: url, alt: NT.t('Preview'), class: 'drop-img' }), h('small', {}, NT.t('{nome} · {mb} MB · click to change', { nome: fl.name, mb: NT.num(fl.size / 1048576) })));
      btn.disabled = false;
    }
    input.addEventListener('change', () => scegli(input.files[0]));
    ['dragenter', 'dragover'].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.add('sopra'); }));
    ['dragleave', 'drop'].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.remove('sopra'); }));
    drop.addEventListener('drop', ev => scegli(ev.dataTransfer.files[0]));

    btn.addEventListener('click', async () => {
      if (!file) return;
      btn.disabled = true; btn.replaceChildren(h('span', { class: 'spinner' }), NT.t('Saving…'));
      const q = new URLSearchParams({ data: data.value, exif: usaExif.checked ? '1' : '0', tipo: tipo.value, diametro: diam.value, note: nota.value, analizza: analizza.checked ? '1' : '0' });
      try {
        const r = await NT.api('POST', '/api/nevi/' + n.id + '/foto?' + q.toString(), null, { raw: file, tipo: file.type || 'application/octet-stream' });
        formFotoAperto = false;
        await ricaricaDettaglio();
        fotoSel = r.id;
        renderPannello();
        NT.toast((r.da_exif ? NT.t('Photo saved ({data}, date read from the photo).', { data: NT.fmtData(r.scattata_il) }) : NT.t('Photo saved ({data}).', { data: NT.fmtData(r.scattata_il) }))
          + (r.analisi_errore ? ' ' + NT.tr(r.analisi_errore) : ''), r.analisi_errore ? 'errore' : 'ok');
      } catch (e) { btn.disabled = false; btn.replaceChildren(NT.icona('foto', 18), NT.t('Save photo')); NT.errore(e); }
    });

    const det = h('details', { class: 'scheda form-foto', open: formFotoAperto || dett.foto.length === 0 },
      h('summary', {}, NT.icona('piu', 16), NT.t('Add a photo to the history')),
      h('div', { class: 'form-corpo' }, drop,
        h('div', { class: 'riga-2' },
          h('label', { class: 'etichetta' }, NT.t('Date the photo was taken'), data,
            h('span', { class: 'spunta' }, usaExif, ' ' + NT.t('Use the date written in the photo, if there is one'))),
          h('label', { class: 'etichetta' }, NT.t('Measured diameter (mm)'), diam)),
        h('div', { class: 'riga-2' }, h('label', { class: 'etichetta' }, NT.t('Photo type'), tipo), h('label', { class: 'etichetta' }, NT.t('Notes'), nota)),
        h('label', { class: 'spunta grande' }, analizza, ' ' + NT.t('Analyse now with all installed methods')),
        h('details', { class: 'consigli' }, h('summary', {}, NT.t('How to take comparable photos')),
          h('ul', {}, h('li', {}, NT.t('Same light (daylight, no flash) and same distance every time, about 10–15 cm.')),
            h('li', {}, NT.t('Place a ruler or a coin next to the mole: it is used to measure the diameter.')),
            h('li', {}, NT.t('In-focus photo, with the mole in the centre and the skin clearly visible (move hair aside if needed).')),
            h('li', {}, NT.t('Always shoot from the same angle and keep the original, without filters.')))),
        btn));
    return det;
  }

  /* ------------------------------ diameter chart ------------------------------ */
  function graficoDiametro(foto) {
    const pt = foto.filter(f => f.diametro_mm !== null && f.diametro_mm !== undefined).map(f => ({ d: f.scattata_il, v: f.diametro_mm }));
    if (pt.length < 2) return null;
    const L = 380, A = 190, ml = 36, mr = 14, mt = 14, mb = 32;
    const t0 = new Date(pt[0].d + 'T12:00:00').getTime(), t1 = new Date(pt[pt.length - 1].d + 'T12:00:00').getTime();
    const vmax = Math.max(7, Math.ceil(Math.max(...pt.map(p => p.v)) + 1));
    const X = d => ml + (t1 === t0 ? (L - ml - mr) / 2 : (new Date(d + 'T12:00:00').getTime() - t0) / (t1 - t0) * (L - ml - mr));
    const Y = v => A - mb - v / vmax * (A - mb - mt);
    const passo = vmax <= 10 ? 2 : 5;
    let s = '<svg viewBox="0 0 ' + L + ' ' + A + '" class="grafico" role="img" aria-label="' + NT.esc(NT.t('Mole diameter over time')) + '">';
    for (let v = 0; v <= vmax; v += passo) s += '<line x1="' + ml + '" x2="' + (L - mr) + '" y1="' + Y(v) + '" y2="' + Y(v) + '" class="gl"/><text x="' + (ml - 6) + '" y="' + (Y(v) + 4) + '" text-anchor="end" class="gt">' + v + '</text>';
    s += '<line x1="' + ml + '" x2="' + (L - mr) + '" y1="' + Y(6) + '" y2="' + Y(6) + '" class="g6"/><text x="' + (L - mr) + '" y="' + (Y(6) - 4) + '" text-anchor="end" class="gt g6t">6 mm</text>';
    s += '<polyline class="gline" points="' + pt.map(p => X(p.d) + ',' + Y(p.v)).join(' ') + '"/>';
    pt.forEach(p => { s += '<circle cx="' + X(p.d) + '" cy="' + Y(p.v) + '" r="4.5" class="gp"><title>' + NT.fmtData(p.d) + ': ' + NT.num(p.v) + ' mm</title></circle>'; });
    s += '<text x="' + X(pt[0].d) + '" y="' + (A - 10) + '" text-anchor="start" class="gt">' + NT.fmtData(pt[0].d) + '</text>';
    s += '<text x="' + X(pt[pt.length - 1].d) + '" y="' + (A - 10) + '" text-anchor="end" class="gt">' + NT.fmtData(pt[pt.length - 1].d) + '</text></svg>';
    const diff = pt[pt.length - 1].v - pt[0].v, giorni = NT.giorniTra(pt[0].d, pt[pt.length - 1].d);
    return h('div', { class: 'scheda' }, h('h3', {}, NT.t('Diameter over time')), NT.html(s),
      h('p', { class: 'piccolo' }, NT.t('Change:') + ' ', h('strong', {}, (diff >= 0 ? '+' : '') + NT.num(diff) + ' mm'), ' ' + NT.tp(giorni, 'in {n} day.', 'in {n} days.') + ' ',
        NT.t('These are measurements you entered: they are valid if always taken the same way. A mole that grows or changes is a good reason to show it to your dermatologist; the 6 mm line is just the classic reference of the ABCDE criteria.')),
      h('button', { class: 'btn-testo', onclick: dialogoABCDE }, NT.t('ABCDE reminder')));
  }

  function dialogoABCDE() {
    const voci = [['A', NT.t('Asymmetry'), NT.t('The two halves of the mole do not look alike.')], ['B', NT.t('Border'), NT.t('Irregular, jagged or blurred.')],
      ['C', NT.t('Colour'), NT.t('Several colours in the same mole (brown, black, red, blue, white).')], ['D', NT.t('Diameter'), NT.t('More than 6 mm (but smaller melanomas exist).')],
      ['E', NT.t('Evolution'), NT.t('It changes over time: shape, colour, size, elevation, or itching or bleeding appear.')]];
    NT.apriDialogo(h('div', {}, h('h3', {}, NT.t('ABCDE reminder')),
      h('ul', { class: 'abcde' }, voci.map(([l, t, d]) => h('li', {}, h('b', {}, l), h('span', {}, h('strong', {}, t), ' – ', d)))),
      h('p', { class: 'piccolo' }, NT.t('The «ugly duckling» also counts: a mole that looks different from all the others. Nodules that grow quickly or feel hard to the touch should be shown straight away. This reminder does not replace a medical visit.')),
      h('div', { class: 'azioni' }, h('button', { class: 'btn btn-pri', onclick: () => NT.chiudiDialogo() }, NT.t('Close')))));
  }

  NT.dialogoABCDE = dialogoABCDE;

  /* ---------------------------------- comparison ---------------------------------- */
  function dialogoConfronto(foto, corrente) {
    let a = foto[0], b = foto[foto.length - 1];
    if (corrente && foto.length > 2) { const i = foto.indexOf(corrente); b = corrente; a = i > 0 ? foto[i - 1] : foto[1]; if (a.id === b.id) a = foto[0]; if (new Date(a.scattata_il) > new Date(b.scattata_il)) [a, b] = [b, a]; }
    let sovrapposto = false, posizione = 50;
    const etich = f => NT.fmtData(f.scattata_il) + (f.diametro_mm ? ' · ' + NT.num(f.diametro_mm) + ' mm' : '');
    const selA = h('select', { class: 'campo', onchange: () => { a = foto.find(x => x.id === +selA.value); ridisegna(); } }, foto.map(f => h('option', { value: f.id, selected: f.id === a.id }, etich(f))));
    const selB = h('select', { class: 'campo', onchange: () => { b = foto.find(x => x.id === +selB.value); ridisegna(); } }, foto.map(f => h('option', { value: f.id, selected: f.id === b.id }, etich(f))));
    const area = h('div', { class: 'confronto-area' });
    const modoBtn = h('button', { class: 'btn', onclick: () => { sovrapposto = !sovrapposto; modoBtn.textContent = sovrapposto ? NT.t('Show side by side') : NT.t('Overlay with slider'); ridisegna(); } }, NT.t('Overlay with slider'));
    function ridisegna() {
      const giorni = NT.giorniTra(a.scattata_il, b.scattata_il);
      const dd = (a.diametro_mm && b.diametro_mm) ? ' ' + NT.t('Diameter: {diff} mm difference.', { diff: NT.num(b.diametro_mm - a.diametro_mm) }) : '';
      const nota = h('p', { class: 'piccolo' }, NT.tp(Math.abs(giorni), '{n} day has passed between the two photos.', '{n} days have passed between the two photos.') + dd + ' ' + NT.t('Compare shape, borders and colours: if you notice differences, show the photos to your dermatologist.'));
      if (!sovrapposto) {
        area.replaceChildren(h('div', { class: 'confronto-coppia' },
          h('figure', {}, h('img', { src: '/foto/' + a.id + '/mini?l=960', alt: '' }), h('figcaption', {}, etich(a))),
          h('figure', {}, h('img', { src: '/foto/' + b.id + '/mini?l=960', alt: '' }), h('figcaption', {}, etich(b)))), nota);
      } else {
        const top = h('img', { src: '/foto/' + a.id + '/mini?l=960', alt: '', class: 'sopra', style: { clipPath: 'inset(0 ' + (100 - posizione) + '% 0 0)' } });
        const cur = h('input', { type: 'range', min: 0, max: 100, value: posizione, 'aria-label': NT.t('Comparison slider'), oninput: () => { posizione = +cur.value; top.style.clipPath = 'inset(0 ' + (100 - posizione) + '% 0 0)'; } });
        area.replaceChildren(h('div', { class: 'sovrapposte' }, h('img', { src: '/foto/' + b.id + '/mini?l=960', alt: '' }), top),
          cur, h('div', { class: 'didascalie' }, h('span', {}, '← ' + etich(a)), h('span', {}, etich(b) + ' →')), nota);
      }
    }
    ridisegna();
    NT.apriDialogo(h('div', {}, h('h3', {}, NT.t('Comparison of two photos')),
      h('div', { class: 'riga-2' }, h('label', { class: 'etichetta' }, NT.t('Before'), selA), h('label', { class: 'etichetta' }, NT.t('After'), selB)),
      modoBtn, area, h('div', { class: 'azioni' }, h('button', { class: 'btn btn-pri', onclick: () => NT.chiudiDialogo() }, NT.t('Close')))), true);
  }

  /* ------------------------------ automatic analysis ------------------------------ */
  async function caricaAnalisi(fotoId) {
    const box = $('#box-analisi');
    if (!box || fotoId !== fotoSel) return;
    let st;
    try { st = await NT.get('/api/foto/' + fotoId + '/analisi'); } catch (e) { box.replaceChildren(h('h3', {}, NT.t('Automatic analysis')), h('p', { class: 'errore-campo' }, e.message)); return; }
    if (fotoId !== fotoSel || !$('#box-analisi')) return;
    const attiva = st.stato === 'in_coda' || st.stato === 'in_corso';
    if (attiva) inAnalisi.add(fotoId);
    else if (inAnalisi.has(fotoId)) {                          // just finished: I update the list and the dots
      inAnalisi.delete(fotoId);
      await ricaricaDettaglio();
      renderPannello();
      return;
    }
    box.replaceChildren(h('h3', {}, NT.t('Automatic analysis')), contenutoAnalisi(fotoId, st));
    if (attiva) pollTimer = setTimeout(() => caricaAnalisi(fotoId), 3000);
  }

  async function avviaAnalisi(fotoId) {
    try { await NT.api('POST', '/api/foto/' + fotoId + '/analizza'); inAnalisi.add(fotoId); caricaAnalisi(fotoId); } catch (e) { NT.errore(e); }
  }

  function contenutoAnalisi(fotoId, st) {
    if (st.stato === 'nessuna') {
      return h('div', {}, h('p', {}, NT.t('This photo has not been analysed yet. The analysis compares several methods on the same image and tells you what each one answered.')),
        h('p', { class: 'piccolo muted' }, NT.t('The first analysis can take several minutes (the models are loaded into memory).') + ' ' +
          (st.skinsense_attivo ? NT.t('SkinSense is on: the photo (without metadata) will be sent to an online service.') : NT.t('The photo stays on your computer: SkinSense (online service) is turned off.'))),
        h('button', { class: 'btn btn-pri', onclick: () => avviaAnalisi(fotoId) }, NT.t('Analyse this photo')));
    }
    if (st.stato === 'in_coda' || st.stato === 'in_corso') {
      return h('div', { class: 'analisi-attesa' }, h('div', { class: 'riga-spinner' }, h('span', { class: 'spinner grande' }),
        h('div', {}, h('strong', {}, st.stato === 'in_coda' ? (st.posizione_coda > 0 ? NT.t('Queued (position {n})…', { n: st.posizione_coda }) : NT.t('Queued…')) : NT.t('Analysis in progress…')),
          h('p', { class: 'piccolo muted' }, NT.t('You can keep using the app. If you close the window the analysis is not lost: the program finishes the work and then shuts down by itself.')))),
        st.avanzamento && st.avanzamento.length ? h('pre', { class: 'log' }, st.avanzamento.join('\n')) : null);
    }
    if (st.stato === 'errore') {
      return h('div', {}, h('p', { class: 'errore-campo' }, st.messaggio ? NT.tr(st.messaggio) : NT.t('The analysis failed.')),
        h('button', { class: 'btn', onclick: () => avviaAnalisi(fotoId) }, NT.t('Try again')));
    }
    return renderSintesi(st.sintesi, fotoId);
  }

  const GIUDIZIO_NESSUNO = NT.t('No method produced a result: check the reasons listed below.');
  const GIUDIZIO_ATT = NT.t('At least one method (or one of its models) flags a lesion that needs attention. This is not a diagnosis and these tools are often wrong, but it is one more reason not to put off the dermatology visit and to bring this report.');
  const GIUDIZIO_BEN = NT.t('None of the methods that responded flags the lesion as suspicious. This does NOT rule out a melanoma: the tools are not clinically validated and are also wrong in this direction. If the mole is asymmetric, has irregular borders, several colours, is larger than 6 mm or has changed over time, a visit is still needed.');
  const AVVERTENZE = [
    NT.t('This report is NOT a diagnosis. The programs used are research prototypes, not medical devices.'),
    NT.t('The methods are trained on photographs different from yours: changing light, distance or camera can change the answer.'),
    NT.t("Phototype, age and family history do not change the neural networks' result (they only look at pixels): they serve to put the risk in context."),
    NT.t('It is normal for the methods to disagree: it only means that none of them is reliable on its own.'),
  ];

  /* Label of a model, like "NEV (naevus, i.e. a benign mole)": the code stays, the description is translated. */
  function etichettaRisultato(testo) {
    const m = /^([A-Z]{3}) \((.+)\)$/.exec(testo || '');
    return m ? m[1] + ' (' + NT.tr(m[2]) + ')' : NT.tr(testo);
  }

  /* "4 of 5: NEV (...); 1 of 5: MEL (...)" - the count of identical results, in the chosen language */
  function fraseConteggio(ok) {
    const conteggi = new Map();
    ok.forEach(r => conteggi.set(r.etichetta, (conteggi.get(r.etichetta) || 0) + 1));
    return [...conteggi.entries()].sort((a, b) => b[1] - a[1])
      .map(([et, n]) => NT.t('{n} of {tot}: {et}', { n: n, tot: ok.length, et: etichettaRisultato(et) })).join('; ');
  }

  function renderSintesi(s, fotoId) {
    const giud = s.con_risultato.length === 0 ? GIUDIZIO_NESSUNO : (s.attenzione.length || s.discordi.length) ? GIUDIZIO_ATT : GIUDIZIO_BEN;
    const schede = s.metodi.map(m => {
      const ok = m.risultati.filter(r => r.stato === 'ok');
      const piu = new Set(m.risultati.map(r => r.gruppo).filter(Boolean)).size > 1;
      return h('div', { class: 'metodo' },
        h('div', { class: 'metodo-testa' }, h('strong', {}, NT.t('Method {n}', { n: m.numero })), h('span', { class: 'metodo-titolo' }, NT.tr(m.titolo)),
          m.verdetto ? NT.chipEsito(m.verdetto) : h('span', { class: 'chip chip-neutro' }, NT.t('No result'))),
        m.introduzione ? h('p', { class: 'piccolo muted' }, NT.tr(m.introduzione)) : null,
        ok.length ? h('p', { class: 'ha-detto' }, NT.t('Method {n} said:', { n: m.numero }) + ' ', h('strong', {}, fraseConteggio(ok))) : null,
        h('ul', { class: 'modelli' }, m.risultati.map(r => r.stato === 'ok'
          ? h('li', {}, h('span', { class: 'mod-nome' }, (piu && r.gruppo ? '[' + NT.tr(r.gruppo) + '] ' : '') + r.nome), h('span', {}, '→ ' + etichettaRisultato(r.etichetta)),
            h('span', { class: 'muted' }, NT.t('confidence {perc}', { perc: NT.perc(r.valore) }) + (r.prob_mel !== null && r.prob_mel !== undefined ? ' · ' + NT.t('melanoma prob. {perc}', { perc: NT.perc(r.prob_mel) }) : '')))
          : h('li', { class: 'nota-metodo ' + r.stato }, h('span', {}, (r.stato === 'errore' ? NT.t('{nome}: error.', { nome: r.nome }) + ' ' : r.stato === 'non_disponibile' ? NT.t('{nome}: not available.', { nome: r.nome }) + ' ' : '') + NT.tr(r.nota || ''))))));
    });
    return h('div', { class: 'sintesi' },
      h('div', { class: 'sintesi-testa' }, NT.chipEsito(s.esito), h('span', { class: 'piccolo muted' }, NT.t('{n} of {tot} methods responded', { n: s.con_risultato.length, tot: s.metodi.length }))),
      h('p', { class: 'giudizio' }, giud),
      schede,
      h('details', { class: 'consigli' }, h('summary', {}, NT.t('Important notices')), h('ul', {}, AVVERTENZE.map(a => h('li', {}, a)))),
      s.testo ? h('details', { class: 'consigli' }, h('summary', {}, NT.lingua === 'en' ? NT.t('Full report (text)') : NT.t('Full report (text, in English)')), h('pre', { class: 'rapporto' }, s.testo)) : null,
      h('button', { class: 'btn-testo', onclick: () => avviaAnalisi(fotoId) }, NT.t('Re-analyse')));
  }
})();
'''
WEB_FILES["/v_mappa.js"] = ("text/javascript; charset=utf-8", _WEB_V_MAPPA_JS.encode("utf-8"))

_WEB_V_PROFILO_JS = r'''/* ============================================================================
   v_profilo.js - phenotype, personal history and family history (saves by itself)
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  const FOTOTIPI = [
    [1, 'I', NT.t('Very fair skin. Always burns, never tans (often red hair, freckles).')],
    [2, 'II', NT.t('Fair skin. Burns easily, tans little.')],
    [3, 'III', NT.t('Fair-olive skin. Sometimes burns, tans gradually.')],
    [4, 'IV', NT.t('Olive skin. Burns little, tans easily.')],
    [5, 'V', NT.t('Dark skin. Rarely burns.')],
    [6, 'VI', NT.t('Very dark skin. Does not burn.')],
  ];

  NT.viste.profilo = async function (cont) {
    const u = S.utente;
    let p = Object.assign({}, u.profilo);
    let daSalvare = false;                // true between an edit and the automatic save
    const stato = h('span', { class: 'salvataggio' }, '');
    const riepilogo = h('aside', { class: 'riepilogo-profilo' });

    /* ---------- automatic saving ---------- */
    const salvaOra = async () => {
      daSalvare = false;
      stato.textContent = NT.t('Saving…'); stato.className = 'salvataggio';
      try {
        const r = await NT.api('PUT', '/api/utenti/' + u.id + '/profilo', p);
        S.utente = Object.assign(S.utente, r);
        stato.textContent = NT.t('Saved ✓'); stato.className = 'salvataggio ok';
        disegnaRiepilogo();
      } catch (e) { stato.textContent = ''; NT.errore(e); }
    };
    const salva = NT.debounce(salvaOra, 700);
    const cambia = (campo, valore) => { p[campo] = valore; daSalvare = true; stato.textContent = NT.t('Unsaved changes…'); stato.className = 'salvataggio'; salva(); };
    NT.alCambioPagina(() => { if (daSalvare) salvaOra(); });

    /* ---------- small components ---------- */
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
        h('div', { class: 'contatore' }, h('button', { type: 'button', class: 'btn-icona', 'aria-label': NT.t('Decrease: {voce}', { voce: testo }), onclick: () => agg(-1) }, NT.icona('meno', 16)), val,
          h('button', { type: 'button', class: 'btn-icona', 'aria-label': NT.t('Increase: {voce}', { voce: testo }), onclick: () => agg(1) }, NT.icona('piu', 16))));
    };

    /* ---------- phototype ---------- */
    const COL = window.Corpo.colorePelle;
    const fototipi = h('div', { class: 'fototipi', role: 'radiogroup', 'aria-label': NT.t('Phototype') }, FOTOTIPI.map(([n, r, d]) => h('button', { type: 'button', role: 'radio', class: 'fototipo' + (p.fototipo === n ? ' sel' : ''),
      'aria-checked': p.fototipo === n ? 'true' : 'false', dataset: { n: String(n) },
      onclick: () => { p.fototipo = p.fototipo === n ? 0 : n; NT.$$('.fototipo', fototipi).forEach(b => { const on = +b.dataset.n === p.fototipo; b.classList.toggle('sel', on); b.setAttribute('aria-checked', on ? 'true' : 'false'); }); cambia('fototipo', p.fototipo); } },
      h('span', { class: 'swatch', style: { background: COL(n) } }), h('span', {}, h('strong', {}, NT.t('Type {n}', { n: r })), h('small', {}, d)))));

    const eta = h('span', { class: 'eta-calcolata' }, '');
    const aggiornaEta = () => {
      if (!p.data_nascita) { eta.textContent = ''; return; }
      const n = new Date(p.data_nascita + 'T12:00:00'), o = new Date();
      let a = o.getFullYear() - n.getFullYear(); if (o < new Date(o.getFullYear(), n.getMonth(), n.getDate())) a--;
      eta.textContent = a >= 0 ? NT.tp(a, '{n} year', '{n} years') : '';
    };
    const nascita = h('input', { type: 'date', class: 'campo corto', value: p.data_nascita || '', min: '1900-01-01', max: NT.oggiISO(),
      onchange: ev => { cambia('data_nascita', ev.target.value); aggiornaEta(); } });
    aggiornaEta();

    const sezione = (titolo, intro, ...figli) => h('section', { class: 'scheda' }, h('h2', {}, titolo), intro ? h('p', { class: 'piccolo muted' }, intro) : null, ...figli);

    /* ---------- personal image ---------- */
    const boxAvatar = h('div', { class: 'avatar-editor' });
    const entrata = h('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp,image/bmp', hidden: true, 'aria-label': NT.t('Choose a personal picture') });
    const aggiornaAvatar = v => { S.utente.avatar_v = v; disegnaAvatar(); NT.ridisegnaTestata(); disegnaRiepilogo(); };
    async function scegliAvatar() {
      const file = entrata.files && entrata.files[0];
      entrata.value = '';
      if (!file) return;
      try {
        if (file.size > 40 * 1024 * 1024) throw new Error(NT.t('The file is too large (maximum 40 MB).'));
        const blob = await NT.ridimensionaQuadrato(file, 256);      // square crop at the centre + reduction, in the browser
        const r = await NT.api('POST', '/api/utenti/' + u.id + '/avatar', null, { raw: blob, tipo: 'image/jpeg' });
        aggiornaAvatar(r.avatar_v);
        NT.toast(NT.t('Personal picture saved.'), 'ok');
      } catch (e) { NT.errore(e); }
    }
    async function togliAvatar() {
      try { const r = await NT.api('DELETE', '/api/utenti/' + u.id + '/avatar'); aggiornaAvatar(r.avatar_v); NT.toast(NT.t('Picture removed.'), 'ok'); }
      catch (e) { NT.errore(e); }
    }
    entrata.addEventListener('change', scegliAvatar);
    function disegnaAvatar() {
      NT.riempi(boxAvatar, NT.avatar(u.nome, 88, S.utente),
        h('div', { class: 'avatar-azioni' },
          h('p', { class: 'piccolo muted' }, NT.t('You can use your own photo, a drawing or an icon. The image is cropped to a square and reduced, stays only on this computer and is never used for mole analysis.')),
          h('div', { class: 'riga-inline' },
            h('button', { type: 'button', class: 'btn', onclick: () => entrata.click() }, S.utente.avatar_v ? NT.t('Change image…') : NT.t('Choose image…')),
            S.utente.avatar_v ? h('button', { type: 'button', class: 'btn-testo pericolo', onclick: togliAvatar }, NT.t('Remove')) : null)));
    }
    disegnaAvatar();

    const form = h('div', { class: 'pila' },
      h('div', { class: 'scheda info' }, h('strong', {}, NT.t('What is this information used for?') + ' '),
        NT.t('They do not change the result of the neural networks, which only look at the pixels of the photo. They are used to: (1) put the risk in context, (2) choose the scientific literature suited to you, (3) check the criteria for genetic counselling, (4) calculate how long you can stay in the sun before burning. Everything stays on your computer.')),
      sezione(NT.t('Personal picture'), null, boxAvatar, entrata),
      sezione(NT.t('Personal data'), null,
        campo(NT.t('Sex'), gruppo('sesso', [['F', NT.t('Woman')], ['M', NT.t('Man')], ['altro', NT.t('Other')], ['', NT.t('I prefer not to say')]], NT.t('Sex'))),
        campo(NT.t('Date of birth'), h('div', { class: 'riga-inline' }, nascita, eta))),
      sezione(NT.t('Phenotype: skin, hair, eyes'), NT.t('If you are unsure about your phototype, think about how your skin reacts to the first intense sun exposure in summer, without protection.'),
        campo(NT.t('Phototype (Fitzpatrick classification)'), fototipi, NT.t("I don't know: leave it empty, you can come back later.")),
        campo(NT.t('Natural hair colour (when young)'), gruppo('capelli', [['neri', NT.t('Black')], ['castani', NT.t('Brown')], ['biondi', NT.t('Blond')], ['rossi', NT.t('Red')], ['grigi', NT.t('Grey/white')]], NT.t('Hair'))),
        campo(NT.t('Eye colour'), gruppo('occhi', [['scuri', NT.t('Dark')], ['verdi', NT.t('Green')], ['azzurri', NT.t('Blue/grey')]], NT.t('Eyes'))),
        campo(NT.t('Freckles (ephelides)'), gruppo('efelidi', [['nessuna', NT.t('None')], ['poche', NT.t('A few')], ['molte', NT.t('Many')]], NT.t('Freckles'))),
        campo(NT.t('Roughly how many moles do you have on your body?'), gruppo('n_nevi', [['<25', NT.t('Fewer than 25')], ['25-49', '25–49'], ['50-99', '50–99'], ['100+', NT.t('100 or more')]], NT.t('Number of moles')), NT.t('An estimate is fine.')),
        campo(NT.t('Has a doctor told you that you have atypical (dysplastic) moles?'), gruppo('nevi_atipici', [['no', NT.t('No')], ['si', NT.t('Yes')], ['non so', NT.t("Don't know")]], NT.t('Atypical moles')))),
      sezione(NT.t('Sun exposure'), null,
        campo(NT.t('Sunburns with blisters (especially as a child or teenager)'), gruppo('scottature', [['mai', NT.t('Never')], ['poche', NT.t('A few')], ['molte', NT.t('Many')]], NT.t('Sunburns'))),
        campo(NT.t('Tanning lamps or sunbeds'), gruppo('lampade', [['mai', NT.t('Never')], ['alcune', NT.t('Sometimes')], ['spesso', NT.t('Often')]], NT.t('Sunbeds'))),
        spunta('lavoro_aperto', NT.t('I work or do activities outdoors for many hours'))),
      sezione(NT.t('Personal history'), null,
        contatore('melanomi_personali', NT.t('Melanomas already diagnosed in me'), NT.t('Only invasive primary melanomas count.')),
        spunta('altri_tumori_cutanei', NT.t('I have had other skin cancers (basal cell or squamous cell carcinoma)')),
        spunta('immunosoppressione', NT.t("I am immunosuppressed (transplant or therapies that lower the body's defences)")),
        h('div', { class: 'campo-titolo spazio-su' }, NT.t('I have had (or have) one of these cancers:')),
        h('div', { class: 'spunte-griglia' }, spunta('pers_pancreas', NT.t('Pancreatic cancer')), spunta('pers_astrocitoma', NT.t('Astrocytoma')),
          spunta('pers_uveale', NT.t('Melanoma of the eye (uveal)')), spunta('pers_mesotelioma', NT.t('Mesothelioma')), spunta('pers_rene', NT.t('Kidney carcinoma'))),
        campo(NT.t('Have I already had a genetic test for melanoma?'), gruppo('test_genetico', [['', NT.t('Not specified')], ['no', NT.t('No')], ['si_positivo', NT.t('Yes, positive')], ['si_negativo', NT.t('Yes, negative')], ['si_non_informativo', NT.t('Yes, uninformative')]], NT.t('Genetic test')))),
      sezione(NT.t('Family history'), NT.t('Count blood relatives (not in-laws) on the same side of the family, maternal or paternal: this is the criterion geneticists use. If you do not know, ask a relative: this information is very useful.'),
        h('label', { class: 'spunta grande' }, h('input', { type: 'checkbox', id: 'ck-fam', checked: !!p.fam_compilata, onchange: ev => cambia('fam_compilata', ev.target.checked) }), ' ' + NT.t('I have checked my family history (even if the answer is «none»)')),
        contatore('fam_melanoma_1grado', NT.t('1st-degree relatives with melanoma'), NT.t('Parents, brothers, sisters, children.')),
        contatore('fam_melanoma_altri', NT.t('Other relatives with melanoma'), NT.t('Grandparents, aunts and uncles, nieces and nephews (2nd degree).')),
        contatore('fam_pancreas', NT.t('Relatives with pancreatic cancer (in total)'), NT.t('Of any degree of kinship.')),
        contatore('fam_pancreas_1grado', NT.t('…of which 1st-degree')),
        contatore('fam_astrocitoma', NT.t('Relatives with astrocytoma (brain tumour)')),
        contatore('fam_uveale', NT.t('Relatives with melanoma of the eye (uveal)')),
        contatore('fam_mesotelioma', NT.t('Relatives with mesothelioma')),
        contatore('fam_rene', NT.t('Relatives with kidney carcinoma'))),
      sezione(NT.t('Notes'), null, h('textarea', { class: 'campo', rows: 3, maxlength: 1000, placeholder: NT.t('Anything else you want to remember (allergies, photosensitising medicines, …)'), value: p.note || '', oninput: ev => cambia('note', ev.target.value) })));

    /* ---------- side summary ---------- */
    function disegnaRiepilogo() {
      const ri = S.utente.rischio, ge = S.utente.genetica;
      const colore = { nessuno: 'neutro', alcuni: 'giallo', attenzione: 'arancio' }[ri.livello];
      NT.riempi(riepilogo, 
        h('div', { class: 'scheda' }, h('div', { class: 'riga-spinner' }, NT.avatar(S.utente.nome, 44, S.utente), h('div', {}, h('strong', {}, S.utente.nome),
          h('div', { class: 'piccolo muted' }, [S.utente.eta !== null && S.utente.eta !== undefined ? NT.tp(S.utente.eta, '{n} year', '{n} years') : null, S.utente.profilo.fototipo ? NT.t('phototype {tipo}', { tipo: FOTOTIPI[S.utente.profilo.fototipo - 1][1] }) : null].filter(Boolean).join(' · ') || NT.t('Profile to complete')))), stato),
        h('div', { class: 'scheda' }, h('h3', {}, NT.t('Risk factors present')),
          h('div', { class: 'banda ' + colore }, NT.tr(ri.testo)),
          ri.presenti.length ? h('ul', { class: 'fattori' }, ri.presenti.map(f => h('li', {}, h('span', {}, NT.tr(f.etichetta), f.maggiore ? h('span', { class: 'chip chip-neutro' }, NT.t('significant')) : null), f.nota ? h('small', {}, NT.tr(f.nota)) : null))) : null,
          h('p', { class: 'piccolo muted' }, NT.tr(ri.nota))),
        h('div', { class: 'scheda' }, h('h3', {}, NT.t('Hereditary melanoma')),
          h('div', { class: 'banda ' + (ge.esito === 'criteri_soddisfatti' ? 'arancio' : 'neutro') }, NT.tr(ge.messaggio) + (ge.messaggio_aggiunta ? ' ' + NT.tr(ge.messaggio_aggiunta) : '')),
          h('a', { class: 'btn', href: '#/genetica' }, NT.t('Go to the Genetics section'), NT.icona('freccia', 16))));
    }
    disegnaRiepilogo();
    NT.riempi(cont, h('div', { class: 'pagina' }, h('h1', {}, NT.t('Profile of {nome}', { nome: u.nome })),
      h('div', { class: 'profilo-layout' }, form, riepilogo)));
  };
})();
'''
WEB_FILES["/v_profilo.js"] = ("text/javascript; charset=utf-8", _WEB_V_PROFILO_JS.encode("utf-8"))

_WEB_V_SCIENZA_JS = r'''/* ============================================================================
   v_scienza.js - scientific literature (PubMed) and genetics of hereditary melanoma
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  const TIPI = {
    'Review': NT.t('Review'), 'Systematic Review': NT.t('Systematic review'), 'Meta-Analysis': NT.t('Meta-analysis'),
    'Practice Guideline': NT.t('Guideline'), 'Guideline': NT.t('Guideline'), 'Consensus Development Conference': NT.t('Consent'),
    'Randomized Controlled Trial': NT.t('Randomised trial'), 'Clinical Trial': NT.t('Clinical trial'), 'Observational Study': NT.t('Observational study'),
  };
  const fmtN = n => NT.migliaia(n);
  const dataRicerca = d => d.data_iso ? NT.fmtData(d.data_iso) : d.data;      // 'data_iso' is missing in searches saved by old versions

  function articolo(a) {
    const tipi = (a.tipi || []).map(t => TIPI[t]).filter(Boolean);
    return h('article', { class: 'articolo' },
      h('a', { href: a.url, target: '_blank', rel: 'noopener noreferrer', class: 'art-titolo' }, a.titolo || NT.t('(untitled)')),
      h('div', { class: 'art-meta' }, [a.autori, a.rivista, a.anno].filter(Boolean).join(' · ')),
      tipi.length ? h('div', { class: 'chips' }, [...new Set(tipi)].map(t => h('span', { class: 'chip chip-neutro' }, t))) : null,
      a.abstract ? h('details', { class: 'abstract' }, h('summary', {}, NT.t('Read the abstract')), h('p', {}, a.abstract),
        h('div', { class: 'piccolo muted' }, NT.t('In English') + ' · PubMed ', a.pmid, a.doi ? [' · ', NT.link('https://doi.org/' + a.doi, 'DOI')] : null)) : h('div', { class: 'piccolo muted' }, NT.t('PubMed {pmid} · abstract not available', { pmid: a.pmid })));
  }

  function avvisoCache(d) {
    if (d.obsoleta) return h('div', { class: 'banda giallo' }, NT.t('PubMed is unreachable: showing the last saved search from {data}.', { data: dataRicerca(d) }));
    return null;
  }

  /* ============================== LITERATURE ============================== */
  NT.viste.letteratura = async function (cont) {
    const uid = S.utente ? S.utente.id : 0;
    const temi = await NT.get('/api/letteratura/temi?utente=' + uid);
    let attivo = true, inCorso = false;
    NT.alCambioPagina(() => { attivo = false; });

    const sezioni = [];     // { id, titolo, corpo, stato }
    const temiEl = temi.map(t => {
      const corpiSez = t.sezioni.map(s => {
        const corpo = h('div', { class: 'sez-corpo' }, h('div', { class: 'piccolo muted' }, NT.t('Not scanned yet.')));
        const testa = h('h3', {}, NT.tr(s.titolo));
        const box = h('div', { class: 'sez' }, testa, corpo);
        sezioni.push({ id: s.id, titolo: s.titolo, corpo, testa });
        return box;
      });
      return h('section', { class: 'scheda' }, h('h2', {}, NT.tr(t.titolo)), corpiSez);
    });

    const progresso = h('span', { class: 'piccolo muted' }, '');
    const btnScan = h('button', { class: 'btn btn-pri', onclick: () => scansiona(false) }, NT.icona('cerca', 18), NT.t('Scan the literature'));
    const btnForza = h('button', { class: 'btn', title: NT.t('Repeat the search ignoring the saved results'), onclick: () => scansiona(true) }, NT.t('Refresh'));

    async function scansiona(forza) {
      if (inCorso) return;
      inCorso = true; btnScan.disabled = true; btnForza.disabled = true;
      let n = 0;
      for (const s of sezioni) {
        if (!attivo) break;
        n++; progresso.textContent = NT.t('Section {n} of {tot}…', { n: n, tot: sezioni.length });
        NT.riempi(s.corpo, NT.caricamento(NT.t('Searching PubMed…')));
        try {
          const d = await NT.get('/api/letteratura/sezione?id=' + encodeURIComponent(s.id) + '&utente=' + uid + (forza ? '&forza=1' : ''));
          NT.riempi(s.corpo, avvisoCache(d),
            h('div', { class: 'piccolo muted spazio-giu' }, (d.da_cache ? NT.t('{n} articles found on PubMed · search of {data} (saved)', { n: fmtN(d.conteggio), data: dataRicerca(d) })
              : NT.t('{n} articles found on PubMed · search of {data}', { n: fmtN(d.conteggio), data: dataRicerca(d) }))),
            d.articoli.length ? d.articoli.map(articolo) : h('div', { class: 'piccolo muted' }, NT.t('No articles found.')));
        } catch (e) { NT.riempi(s.corpo, h('div', { class: 'errore-campo' }, e.message)); }
      }
      inCorso = false;
      if (!attivo) return;
      btnScan.disabled = false; btnForza.disabled = false; progresso.textContent = NT.t('Scan complete.');
    }

    /* free search */
    const q = h('input', { type: 'search', class: 'campo', placeholder: NT.t('Search for more (e.g. "ugly duckling sign", "nail melanoma"…)'), maxlength: 200 });
    const risLibera = h('div', { class: 'ris-libera' });
    const cerca = async () => {
      if (q.value.trim().length < 3) { NT.toast(NT.t('Type at least 3 characters.'), 'errore'); return; }
      NT.riempi(risLibera, NT.caricamento(NT.t('Searching PubMed…')));
      try {
        const d = await NT.get('/api/letteratura/cerca?q=' + encodeURIComponent(q.value));
        NT.riempi(risLibera, avvisoCache(d), h('div', { class: 'piccolo muted spazio-giu' }, NT.t('{n} articles on melanoma and «{termine}»', { n: fmtN(d.conteggio), termine: q.value.trim() })),
          d.articoli.length ? d.articoli.map(articolo) : h('div', { class: 'piccolo muted' }, NT.t('No articles found.')));
      } catch (e) { NT.riempi(risLibera, h('div', { class: 'errore-campo' }, e.message)); }
    };
    q.addEventListener('keydown', e => { if (e.key === 'Enter') cerca(); });

    NT.riempi(cont, h('div', { class: 'pagina' },
      h('h1', {}, NT.t('Scientific literature')),
      h('p', { class: 'lead' }, NT.t('Recent, relevant articles on recognising suspicious moles, on the reliability of apps and artificial intelligence, and on hereditary melanoma. Results come from PubMed, the public database of the National Library of Medicine (USA).')),
      h('div', { class: 'scheda azione-scan' }, h('div', { class: 'riga-inline' }, btnScan, btnForza, progresso),
        h('p', { class: 'piccolo muted' }, NT.t('Searches go from this computer to PubMed (no personal data is sent). Results are saved for 7 days.') + ' ' +
          NT.t('The «picked for you» sections use words linked to your profile (for example phototype or number of moles): if you prefer not to send them, do not scan that section.')),
        h('div', { class: 'riga-inline' }, h('button', { class: 'btn-testo', onclick: () => NT.dialogoABCDE() }, NT.t('ABCDE reminder for recognising a mole')))),
      h('div', { class: 'scheda' }, h('h2', {}, NT.t('Search the literature')), h('div', { class: 'riga-inline' }, q, h('button', { class: 'btn', onclick: cerca }, NT.t('Search'))), risLibera),
      temiEl,
      h('div', { class: 'scheda piccolo muted' }, NT.t("PubMed is a service of the National Library of Medicine. Abstracts are shown for personal consultation, in English; for the full text, open the article on the journal's website.") + ' ',
        NT.t('The articles are chosen by an automatic search and have not been assessed by NeoTracker: read them with your doctor.'))));
  };

  /* ================================ GENETICS ================================ */
  NT.viste.genetica = async function (cont) {
    await NT.ricaricaUtente();
    const g = S.utente.genetica;
    const dati = await NT.get('/api/genetica/geni');
    let attivo = true, inCorso = false;
    NT.alCambioPagina(() => { attivo = false; });

    const cls = { criteri_soddisfatti: 'arancio', nessun_criterio: 'neutro', dati_insufficienti: 'giallo' }[g.esito];
    const criteri = h('ul', { class: 'criteri' }, g.criteri.map(c => h('li', { class: c.soddisfatto ? 'si' : 'no' },
      h('span', { class: 'esito-criterio', 'aria-label': c.soddisfatto ? NT.t('Met') : NT.t('Not met') }, c.soddisfatto ? NT.icona('ok', 16) : '—'),
      h('div', {}, h('strong', {}, NT.tr(c.titolo)), h('div', { class: 'piccolo muted' }, NT.tr(c.spiegazione)), h('div', { class: 'piccolo muted' }, NT.t('Source:') + ' ' + NT.tr(c.fonte))))));

    const righe = dati.geni.map(ge => {
      const risultato = h('div', { class: 'gene-ris' }, h('span', { class: 'piccolo muted' }, NT.t('Not scanned yet')));
      return { nome: ge.gene, risultato, riga: h('tr', {}, h('td', {}, h('strong', {}, ge.gene), g.geni_suggeriti.includes(ge.gene) ? h('div', { class: 'chip chip-neutro' }, NT.t('in the panel')) : null),
        h('td', {}, NT.tr(ge.rischio)), h('td', {}, NT.tr(ge.ruolo), risultato)) };
    });
    const progresso = h('span', { class: 'piccolo muted' }, '');
    const btn = h('button', { class: 'btn btn-pri', onclick: () => scansiona(false) }, NT.icona('cerca', 18), NT.t('Scan the literature on genes'));
    const btnF = h('button', { class: 'btn', onclick: () => scansiona(true) }, NT.t('Refresh'));
    async function scansiona(forza) {
      if (inCorso) return;
      inCorso = true; btn.disabled = true; btnF.disabled = true;
      let n = 0;
      for (const r of righe) {
        if (!attivo) break;
        n++; progresso.textContent = NT.t('Gene {n} of {tot} ({nome})…', { n: n, tot: righe.length, nome: r.nome });
        NT.riempi(r.risultato, NT.caricamento(NT.t('Searching…')));
        try {
          const d = await NT.get('/api/genetica/gene?nome=' + encodeURIComponent(r.nome) + (forza ? '&forza=1' : ''));
          NT.riempi(r.risultato, h('div', { class: 'gene-conta' }, h('strong', {}, fmtN(d.conteggio)), ' ' + NT.t('studies on PubMed'), d.obsoleta ? ' ' + NT.t('(saved search from {data})', { data: dataRicerca(d) }) : ''),
            d.articoli.length ? h('details', { class: 'abstract' }, h('summary', {}, NT.t('Most relevant studies')), d.articoli.map(articolo)) : null);
        } catch (e) { NT.riempi(r.risultato, h('div', { class: 'errore-campo' }, e.message)); }
      }
      inCorso = false;
      if (attivo) { btn.disabled = false; btnF.disabled = false; progresso.textContent = NT.t('Scan complete.'); }
    }

    NT.riempi(cont, h('div', { class: 'pagina' },
      h('h1', {}, NT.t('Hereditary melanoma and genetic testing')),
      h('p', { class: 'lead' }, NT.t('About 5–10% of melanomas occur in families with an inherited predisposition (Leachman 2009). Here you find the criteria specialists use to decide whether to suggest genetic counselling, the genes involved and the literature on each.')),
      h('section', { class: 'scheda' }, h('h2', {}, NT.t('Your data against the criteria')),
        h('div', { class: 'banda ' + cls }, NT.tr(g.messaggio) + (g.messaggio_aggiunta ? ' ' + NT.tr(g.messaggio_aggiunta) : '')),
        g.esito !== 'dati_insufficienti' ? criteri : null,
        h('div', { class: 'azioni sinistra' }, h('a', { class: 'btn', href: '#/profilo' }, g.esito === 'dati_insufficienti' ? NT.t('Fill in the family history in your Profile') : NT.t('Edit the data in the Profile'))),
        h('p', { class: 'piccolo muted' }, NT.t('Simplified criteria, for information only. Genetic testing concerns a small minority of people and is not a routine examination: it is up to the specialist to decide whether and which test to offer, usually after genetic counselling and, when possible, starting from a relative who has had the disease.'))),
      h('section', { class: 'scheda' }, h('h2', {}, NT.t('What to know before a genetic test')),
        h('ul', { class: 'punti' },
          h('li', {}, NT.t('A positive result indicates a higher risk, not certainty of becoming ill; a negative result does not remove the risk (many families have no identifiable variant).')),
          h('li', {}, NT.t('The result also concerns blood relatives: that is why counselling before and after the test is part of the process.')),
          h('li', {}, NT.t('Guidelines recommend the test only after careful selection of candidates and adequate counselling (Rossi 2019); the use of multigene panels is still debated.')),
          h('li', {}, NT.t('With or without a test, for people with a family history, sun protection, skin self-examination and regular dermatological check-ups remain essential.')))),
      h('section', { class: 'scheda' }, h('h2', {}, NT.t('The most studied genes')),
        h('div', { class: 'azione-scan' }, h('div', { class: 'riga-inline' }, btn, btnF, progresso)),
        h('div', { class: 'tabella-scroll' }, h('table', { class: 'tabella' }, h('thead', {}, h('tr', {}, h('th', {}, NT.t('Gene')), h('th', {}, NT.t('Associated risk')), h('th', {}, NT.t('Role and literature')))), h('tbody', {}, righe.map(r => r.riga))))),
      h('section', { class: 'scheda' }, h('h2', {}, NT.t('Sources')), h('ul', { class: 'fonti' }, dati.fonti.map(f => h('li', {}, NT.link(f.url, NT.tr(f.titolo))))),
        h('p', { class: 'piccolo muted' }, NT.t('NeoTracker is not a genetic counselling service. For a personal assessment, see your dermatologist or an oncological genetics centre.')))));
  };
})();
'''
WEB_FILES["/v_scienza.js"] = ("text/javascript; charset=utf-8", _WEB_V_SCIENZA_JS.encode("utf-8"))

_WEB_V_UTENTI_JS = r'''/* ============================================================================
   v_utenti.js - choosing and managing users (the app is multi-user)
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  function dialogoNome(titolo, valore, testoOk) {
    return new Promise(res => {
      const campo = h('input', { type: 'text', class: 'campo', maxlength: 60, value: valore || '', placeholder: NT.t('Name or nickname'), autocomplete: 'off' });
      const errore = h('div', { class: 'errore-campo' });
      const invia = () => {
        const v = campo.value.trim();
        if (!v) { errore.textContent = NT.t('Type a name.'); return; }
        res(v); NT.chiudiDialogo();
      };
      campo.addEventListener('keydown', e => { if (e.key === 'Enter') invia(); });
      const d = NT.apriDialogo(h('div', {}, h('h3', {}, titolo), campo, errore,
        h('div', { class: 'azioni' }, h('button', { class: 'btn', onclick: () => { res(null); NT.chiudiDialogo(); } }, NT.t('Cancel')),
          h('button', { class: 'btn btn-pri', onclick: invia }, testoOk || NT.t('Save')))));
      d.addEventListener('close', () => res(null), { once: true });
      campo.focus(); campo.select();
    });
  }

  NT.viste.utenti = async function (cont) {
    S.utenti = await NT.get('/api/utenti');

    async function nuovo() {
      const nome = await dialogoNome(NT.t('New user'), '', NT.t('Create user'));
      if (!nome) return;
      try {
        const r = await NT.api('POST', '/api/utenti', { nome });
        S.utenti = await NT.get('/api/utenti');
        await NT.scegliUtente(r.id, false);
        NT.toast(NT.t('User created. Fill in the profile: it helps put the results in context.'), 'ok');
        NT.vai('profilo');
      } catch (e) { NT.errore(e); }
    }
    async function rinomina(u) {
      const nome = await dialogoNome(NT.t('Rename user'), u.nome, NT.t('Save'));
      if (!nome || nome === u.nome) return;
      try {
        await NT.api('PATCH', '/api/utenti/' + u.id, { nome });
        if (S.utente && S.utente.id === u.id) await NT.ricaricaUtente();
        NT.vai('utenti');
      } catch (e) { NT.errore(e); }
    }
    async function elimina(u) {
      const si = await NT.conferma(NT.t('Delete «{nome}»?', { nome: u.nome }),
        NT.t('The profile, all moles, all photos and all reports of this user will be deleted permanently. This cannot be undone.'),
        { si: NT.t('Delete permanently'), pericolo: true, scrivi: u.nome });
      if (!si) return;
      try {
        await NT.api('DELETE', '/api/utenti/' + u.id, { conferma: u.nome });
        if (S.utente && S.utente.id === u.id) { S.utente = null; S.nei = []; NT.ls.scrivi('nt_utente', ''); }
        NT.toast(NT.t('User deleted.'), 'ok');
        NT.vai('utenti');
      } catch (e) { NT.errore(e); }
    }

    const schede = S.utenti.map(u => h('div', { class: 'utente-card' + (S.utente && S.utente.id === u.id ? ' corrente' : '') },
      h('button', { class: 'utente-apri', onclick: () => NT.scegliUtente(u.id).catch(NT.errore) },
        NT.avatar(u.nome, 56, u),
        h('span', { class: 'utente-info' }, h('strong', {}, u.nome),
          h('span', { class: 'sotto' }, NT.tp(u.n_nevi, '{n} mole', '{n} moles') + (u.eta !== null && u.eta !== undefined ? ' · ' + NT.tp(u.eta, '{n} year', '{n} years') : '')))),
      h('div', { class: 'utente-azioni' },
        h('button', { class: 'btn-testo', onclick: () => rinomina(u) }, NT.t('Rename')),
        h('button', { class: 'btn-testo pericolo', onclick: () => elimina(u) }, NT.t('Delete')))));

    cont.replaceChildren(h('div', { class: 'pagina stretta' },
      h('h1', {}, S.utenti.length ? NT.t('Who are you?') : NT.t('Welcome to NeoTracker')),
      h('p', { class: 'lead' }, S.utenti.length
        ? NT.t('Choose your profile: each person has their own mole map, photos and data.')
        : NT.t('This program helps you keep track of your moles over time: you mark them on a body map, keep their photos with the date and have them analysed by several methods. Start by creating your user.')),
      h('div', { class: 'utenti-griglia' }, schede,
        h('button', { class: 'utente-card nuovo', onclick: nuovo }, h('span', { class: 'piu' }, NT.icona('piu', 28)), h('strong', {}, NT.t('New user')))),
      h('div', { class: 'nota-privacy' }, NT.icona('ok', 16),
        h('span', {}, NT.t('All data stays on this computer, in the folder:') + ' ', h('code', {}, S.stato.cartella_dati || ''),
          ' ' + NT.t('Nothing is sent online, except the requests you turn on (UV weather, PubMed literature, SkinSense).')))));
  };
})();
'''
WEB_FILES["/v_utenti.js"] = ("text/javascript; charset=utf-8", _WEB_V_UTENTI_JS.encode("utf-8"))

_WEB_V_UV_JS = r'''/* ============================================================================
   v_uv.js - today's UV index in the chosen place (Open-Meteo by default, OpenWeather if chosen)
   ============================================================================ */
(function () {
  'use strict';
  const NT = window.NT, S = NT.S, h = NT.h;

  /* WHO categories (same thresholds and colours as the Python program) */
  const CAT = [[11, NT.m('Extreme'), '#8e44ad'], [8, NT.m('Very high'), '#d9261c'], [6, NT.m('High'), '#f28c00'], [3, NT.m('Moderate'), '#e8c400'], [0, NT.m('Low'), '#3f9c35']];
  const cat = v => CAT.find(c => v >= c[0]) || CAT[CAT.length - 1];
  const FOTOTIPI = ['I', 'II', 'III', 'IV', 'V', 'VI'];

  function grafico(ore) {
    const W = 720, H = 230, sx = 44, dx = 12, su = 18, giu = 40;
    const larg = (W - sx - dx) / ore.length;
    const giorno = o => o.data ? NT.fmtGiornoMese(o.data) : o.giorno;       // 'data' = YYYY-MM-DD
    const massimo = Math.max(11, Math.ceil(Math.max(...ore.map(o => o.uvi))) + 1);
    const y = v => su + (H - su - giu) * (1 - v / massimo);
    let s = '<svg class="grafico-uv" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + NT.esc(NT.t('Hour-by-hour UV index for the next 24 hours')) + '">';
    for (let t = 0; t <= massimo; t += (massimo > 12 ? 4 : 2)) {
      s += '<line class="gl" x1="' + sx + '" x2="' + (W - dx) + '" y1="' + y(t) + '" y2="' + y(t) + '"/><text class="gt" x="' + (sx - 8) + '" y="' + (y(t) + 4) + '" text-anchor="end">' + t + '</text>';
    }
    ore.forEach((o, i) => {
      const x = sx + i * larg + larg * 0.14, w = larg * 0.72, c = cat(o.uvi);
      const alt = Math.max(o.uvi > 0 ? 2 : 0, y(0) - y(o.uvi));
      s += '<rect x="' + x.toFixed(1) + '" y="' + (y(0) - alt).toFixed(1) + '" width="' + w.toFixed(1) + '" height="' + alt.toFixed(1) + '" rx="2" fill="' + c[2] + '"><title>' +
        NT.esc(NT.t('{giorno} at {ora}: UV index {uvi} ({categoria})', { giorno: giorno(o), ora: o.ora, uvi: NT.num(o.uvi), categoria: NT.t(c[1]) })) + '</title></rect>';
      const cambio = i === 0 || o.giorno !== ore[i - 1].giorno;
      const vicinoCambio = [-2, -1, 1, 2].some(k => ore[i + k] && ore[i + k - 1] && ore[i + k].giorno !== ore[i + k - 1].giorno);
      if (cambio || (i % 3 === 0 && !vicinoCambio)) {
        s += '<text class="gt" x="' + (x + w / 2).toFixed(1) + '" y="' + (H - giu + 16) + '" text-anchor="middle">' + NT.esc(o.ora.slice(0, 2)) + '</text>';
        if (i === 0 || o.giorno !== ore[i - 1].giorno) s += '<text class="gt g6t" x="' + (x + w / 2).toFixed(1) + '" y="' + (H - giu + 32) + '" text-anchor="middle">' + NT.esc(giorno(o)) + '</text>';
      }
    });
    s += '<line class="gline" x1="' + sx + '" x2="' + (W - dx) + '" y1="' + y(3) + '" y2="' + y(3) + '" stroke-dasharray="5 4"/>' +
      '<text class="gt g6t" x="' + (W - dx) + '" y="' + (y(3) - 5) + '" text-anchor="end">' + NT.esc(NT.t('3 = WHO recommends protection from this level')) + '</text></svg>';
    return NT.html(s);
  }

  NT.viste.uv = async function (cont) {
    S.imp = await NT.get('/api/impostazioni');
    let attivo = true;
    NT.alCambioPagina(() => { attivo = false; });
    const barra = h('section', { class: 'scheda' });
    const risultato = h('div', { class: 'uv-risultato' });

    /* ---------------- choosing the place ---------------- */
    async function salvaPos(lat, lon, nome) {
      try {
        S.imp = await NT.api('PUT', '/api/impostazioni', { lat, lon, localita: nome });
        NT.toast(NT.t('Location saved: {nome}', { nome: nome }), 'ok');
        disegnaBarra(); carica();
      } catch (e) { NT.errore(e); }
    }
    function rileva() {
      if (!navigator.geolocation) { NT.toast(NT.t('This browser does not offer geolocation: search for the city by name.'), 'errore'); return; }
      NT.toast(NT.t('Asking the browser for your position… (a permission request may appear)'), 'info');
      navigator.geolocation.getCurrentPosition(
        p => salvaPos(p.coords.latitude, p.coords.longitude, NT.t('My location ({lat}; {lon})', { lat: NT.num(p.coords.latitude, 2), lon: NT.num(p.coords.longitude, 2) })),
        err => NT.toast(err.code === 1 ? NT.t('Permission denied. You can search for the city by name or use the estimate from the internet address.') : NT.t('The computer cannot determine the position. Search for the city by name.'), 'errore'),
        { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 });
    }
    async function daIP() {
      const ok = await NT.conferma(NT.t('Estimate from the internet address'), NT.t('To estimate the city, the program contacts the free service ipwho.is, which sees your internet address. Accuracy is at city level (it is sometimes wrong). Proceed?'), { si: NT.t('Yes, estimate the city') });
      if (!ok) return;
      try { const r = await NT.get('/api/posizione-ip'); await salvaPos(r.lat, r.lon, r.nome || NT.t('Estimated location')); }
      catch (e) { NT.errore(e); }
    }
    const campoCitta = h('input', { type: 'search', class: 'campo', placeholder: NT.t('Search for a city (e.g. Turin)'), maxlength: 80, 'aria-label': NT.t('City name') });
    const elencoCitta = h('div', { class: 'citta-elenco' });
    async function cercaCitta() {
      const q = campoCitta.value.trim();
      if (q.length < 2) return;
      NT.riempi(elencoCitta, NT.caricamento(NT.t('Searching…')));
      try {
        const r = await NT.get('/api/localita?q=' + encodeURIComponent(q));
        NT.riempi(elencoCitta, r.length ? r.map(c => h('button', { class: 'btn citta-voce', onclick: () => salvaPos(c.lat, c.lon, c.nome) }, NT.icona('posizione', 16), c.nome))
          : h('div', { class: 'piccolo muted' }, NT.t('No city found with this name.')));
      } catch (e) { NT.riempi(elencoCitta, h('div', { class: 'errore-campo' }, e.message)); }
    }
    campoCitta.addEventListener('keydown', e => { if (e.key === 'Enter') cercaCitta(); });

    function disegnaBarra() {
      const ho = S.imp.lat !== null && S.imp.lat !== undefined;
      NT.riempi(barra, 
        h('div', { class: 'uv-posizione' }, NT.icona('posizione', 22),
          h('div', {}, h('strong', {}, ho ? (S.imp.localita || NT.t('Location set')) : NT.t('Location not set')),
            h('div', { class: 'piccolo muted' }, ho ? NT.num(S.imp.lat, 3) + '; ' + NT.num(S.imp.lon, 3) : NT.t("Choose where you are to see today's UV index.")))),
        h('div', { class: 'riga-inline spazio-su' }, h('button', { class: 'btn btn-pri', onclick: rileva }, NT.icona('mirino', 18), NT.t('Detect my location')),
          campoCitta, h('button', { class: 'btn', onclick: cercaCitta }, NT.t('Search'))),
        elencoCitta,
        h('div', { class: 'piccolo muted spazio-su' }, NT.t('The location is saved only on this computer; it is sent to the weather service (rounded coordinates) to get the UV index.') + ' ',
          h('button', { class: 'btn-testo', onclick: daIP }, NT.t("Can't do it? Estimate from the internet address"))));
    }

    /* ---------------- UV index ---------------- */
    async function carica() {
      if (S.imp.lat === null || S.imp.lat === undefined) {
        NT.riempi(risultato, NT.vuoto(NT.t('Location missing'), NT.t("Choose the city above: then you will see today's UV index, hour by hour.")));
        return;
      }
      NT.riempi(risultato, NT.caricamento(NT.t('Downloading the UV index…')));
      const ft = S.utente && S.utente.profilo.fototipo ? S.utente.profilo.fototipo : 0;
      let d;
      try { d = await NT.get('/api/uv?fototipo=' + ft + '&localita=' + encodeURIComponent(S.imp.localita || '')); }
      catch (e) { if (attivo) NT.riempi(risultato, h('div', { class: 'scheda errore-pagina' }, h('h2', {}, NT.t('UV index not available')), h('p', {}, e.message), h('button', { class: 'btn', onclick: carica }, NT.t('Try again')))); return; }
      if (!attivo) return;
      const cm = d.categoria_max, co = d.categoria_ora;
      const sc = d.scottatura_max;
      NT.riempi(risultato, 
        d.avviso ? h('div', { class: 'banda giallo' }, NT.tr(d.avviso), ' ', h('a', { href: '#/impostazioni' }, NT.t('Settings'))) : null,
        h('section', { class: 'scheda uv-verdetto uv-' + d.verdetto.livello },
          h('div', { class: 'uv-titolo' }, h('h2', {}, NT.tr(d.verdetto.titolo)), h('p', {}, NT.tr(d.verdetto.testo))),
          h('div', { class: 'uv-numeri' },
            h('div', { class: 'uv-num' }, h('span', { class: 'uv-val', style: { background: co.colore, color: co.colore === '#e8c400' ? '#222' : '#fff' } }, NT.num(d.uvi_ora)), h('div', {}, h('strong', {}, NT.t('Now')), h('div', { class: 'piccolo' }, NT.tr(co.nome)))),
            h('div', { class: 'uv-num' }, h('span', { class: 'uv-val', style: { background: cm.colore, color: cm.colore === '#e8c400' ? '#222' : '#fff' } }, NT.num(d.uvi_max)), h('div', {}, h('strong', {}, NT.t("Today's maximum")), h('div', { class: 'piccolo' }, NT.tr(cm.nome)))))),
        h('section', { class: 'scheda' }, h('h2', {}, NT.t('Next {n} hours', { n: d.ore.length })), d.ore.length ? grafico(d.ore) : NT.vuoto(NT.t('Hourly data not available')),
          h('div', { class: 'piccolo muted' }, NT.t('Source:') + ' ' + d.fonte + ' · ' + NT.t('updated') + ' ' + (d.aggiornato_iso ? NT.fmtDataOra(d.aggiornato_iso) + ' ' + NT.t('(local time at the location)') : d.aggiornato) + (d.fuso ? ' · ' + d.fuso : ''),
            d.fonte === 'Open-Meteo' ? [' · ', NT.link('https://open-meteo.com/', 'Open-Meteo.com'), ' (CC BY 4.0)'] : null)),
        h('section', { class: 'scheda' }, h('h2', {}, NT.t('What to do')), h('p', {}, NT.tr(cm.consiglio)),
          sc ? h('div', { class: 'banda neutro' }, h('strong', {}, NT.t('With your phototype ({fototipo})', { fototipo: FOTOTIPI[S.utente.profilo.fototipo - 1] })), ': ' + NT.t("in clear skies and without protection, at today's peak the skin may redden in") + ' ',
            h('strong', {}, NT.tr(sc.testo)), '. ' + NT.t('This is a cautious estimate that uses the lowest minimal erythema dose for your phototype; with reflections (water, snow, sand), altitude or already reddened skin the time is shorter.'))
            : h('div', { class: 'piccolo muted' }, S.utente ? [NT.t('To see how much sun burns you, enter your phototype in the') + ' ', h('a', { href: '#/profilo' }, NT.t('Profile')), '.'] : NT.t('Choose a user and enter their phototype to see how many minutes it takes to burn.')),
          h('ul', { class: 'punti' },
            h('li', {}, NT.t('The middle hours of the day (about 11–16) have the highest index.')),
            h('li', {}, NT.t('Thin clouds do not stop much of the UV: the index can stay high even with a hazy sky.')),
            h('li', {}, NT.t('People with many moles, atypical moles or a history of melanoma should protect themselves even when the index is moderate.')),
            h('li', {}, NT.t('The index is a forecast: the actual value depends on clouds, altitude and reflections.')))),
        h('section', { class: 'scheda' }, h('h2', {}, NT.t('How to read the UV index')),
          h('div', { class: 'legenda-uv' }, CAT.slice().reverse().map(c => h('span', { class: 'chip', style: { background: c[2], color: c[0] === 3 ? '#222' : '#fff' } }, NT.t(c[1]) + ' (' + (c[0] === 11 ? '11+' : c[0] + '–' + ({ 0: 2, 3: 5, 6: 7, 8: 10 }[c[0]])) + ')'))),
          h('p', { class: 'piccolo muted' }, NT.t('Thresholds and colours of the WHO international scale. Sources:')),
          h('ul', { class: 'fonti' }, d.fonti.map(f => h('li', {}, NT.link(f.url, NT.tr(f.titolo)))))));
    }

    disegnaBarra();
    NT.riempi(cont, h('div', { class: 'pagina' },
      h('h1', {}, NT.t("Today's UV index")),
      h('p', { class: 'lead' }, NT.t('Ultraviolet rays are the main modifiable risk factor for melanoma. Here you can see how strong they are today where you are.')),
      barra, risultato));
    carica();
  };
})();
'''
WEB_FILES["/v_uv.js"] = ("text/javascript; charset=utf-8", _WEB_V_UV_JS.encode("utf-8"))



# ==========================================================================================
# 7. START-UP: opens the app window, keeps the engine running and shuts it down when you close it
# ==========================================================================================
# How it works, in brief (plain words):
# 1. The engine (this program) starts and listens on your PC (127.0.0.1).
# 2. It opens Microsoft Edge (or Chrome, if Edge is not there) in "app" mode: it is a normal
# Windows window, WITHOUT an address bar and WITHOUT tabs, with the NeoTracker icon
# in the taskbar. Edge and Chrome are already on your PC: nothing is installed.
# 3. The window uses a separate profile of its own ("profilo_finestra" folder inside the NeoTracker
# data), so it does not get mixed with your normal browsing (history, passwords...).
# 4. When you close the window, the engine notices (see 5c) and shuts itself down.
# 5. If Edge/Chrome cannot be found, the default browser opens (it works the same,
# but with the address bar).

NOME_FINESTRA = "NeoTracker"                      # window title (same as the <title> of the page)
_USCITA_ORIGINALE = {"senza_console": False}      # becomes True if the program started without a black window


class Server(ThreadingHTTPServer):
    daemon_threads = True                         # threads do not block shutdown
    allow_reuse_address = (os.name != "nt")       # on Windows this option would allow TWO servers on the same port
    chiusura_richiesta = False                    # becomes True if you press "Quit" in the app

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fine_sorveglianza = threading.Event()   # used to stop the "supervisor" when the server closes


# ------------------------------------------------------------------------------------------
# 7a. If there is no black window (start with pythonw), write to a file instead of the screen
# ------------------------------------------------------------------------------------------
def percorso_log():
    return Path(CARTELLA_DATI) / "neotracker.log"


def prepara_uscita_testo():
    """When the icon starts the program WITHOUT a black window, Python has no screen to
    write to (sys.stdout is None) and every print() would fail. Here we connect the screen and
    the errors to a text file (neotracker.log in the data folder): if something goes wrong,
    it says what. If instead the black window is there (or you are in Spyder) nothing changes."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    _USCITA_ORIGINALE["senza_console"] = True
    log = percorso_log()
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        if log.exists() and log.stat().st_size > 500_000:          # file too big: I keep only the old one
            vecchio = log.with_name("neotracker.vecchio.log")
            if vecchio.exists():
                vecchio.unlink()
            log.rename(vecchio)
        f = open(log, "a", encoding="utf-8", errors="replace", buffering=1)   # buffering=1: writes line by line
        f.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S}  NeoTracker {VERSIONE} starting =====\n")
    except Exception:
        f = open(os.devnull, "w", encoding="utf-8")               # in the worst case, we throw the text away
    if sys.stdout is None:
        sys.stdout = f
    if sys.stderr is None:
        sys.stderr = f


# Texts of the start-up error windows (they appear before the browser is ready, so they cannot use the
# web/i18n_XX.js dictionaries). The key is the English text; build.py checks that every language is there.
TESTI_AVVIO = {
    "NeoTracker is already running": {
        "it": "NeoTracker è già acceso",
        "fr": "NeoTracker est déjà lancé",
        "de": "NeoTracker läuft bereits",
        "es": "NeoTracker ya está en ejecución"},
    "I cannot open a new window because the session key is missing.\n"
    "Close NeoTracker (from Task Manager, Python process) and reopen it from its icon.": {
        "it": "Non riesco ad aprire una nuova finestra perché manca la chiave di sessione.\n"
        "Chiudi NeoTracker (dal Task Manager, processo Python) e riaprilo dall'icona.",
        "fr": "Impossible d'ouvrir une nouvelle fenêtre : la clé de session est introuvable.\n"
        "Fermez NeoTracker (depuis le Gestionnaire des tâches, processus Python) puis rouvrez-le avec son icône.",
        "de": "Es kann kein neues Fenster geöffnet werden, weil der Sitzungsschlüssel fehlt.\n"
        "Beenden Sie NeoTracker (im Task-Manager, Python-Prozess) und starten Sie es erneut über das Symbol.",
        "es": "No puedo abrir una ventana nueva porque falta la clave de sesión.\n"
        "Cierra NeoTracker (desde el Administrador de tareas, proceso Python) y vuelve a abrirlo desde el icono."},
    "NeoTracker cannot start": {
        "it": "NeoTracker non si avvia",
        "fr": "NeoTracker ne démarre pas",
        "de": "NeoTracker startet nicht",
        "es": "NeoTracker no se inicia"},
    "I cannot use port {porta} ({e}).\n"
    "Another program is using it. Close it, or change PORTA at the top of neotracker.py.": {
        "it": "Non riesco a usare la porta {porta} ({e}).\n"
        "Un altro programma la sta usando. Chiudilo oppure cambia PORTA in cima al file neotracker.py.",
        "fr": "Impossible d'utiliser le port {porta} ({e}).\n"
        "Un autre programme l'utilise. Fermez-le ou modifiez PORTA en haut du fichier neotracker.py.",
        "de": "Der Port {porta} kann nicht verwendet werden ({e}).\n"
        "Ein anderes Programm belegt ihn. Beenden Sie es oder ändern Sie PORTA am Anfang von neotracker.py.",
        "es": "No puedo usar el puerto {porta} ({e}).\n"
        "Otro programa lo está usando. Ciérralo o cambia PORTA al principio del archivo neotracker.py."},
    "NeoTracker has stopped": {
        "it": "NeoTracker si è fermato",
        "fr": "NeoTracker s'est arrêté",
        "de": "NeoTracker wurde beendet",
        "es": "NeoTracker se ha detenido"},
    "Details in:": {
        "it": "Dettagli in:",
        "fr": "Détails dans :",
        "de": "Details in:",
        "es": "Detalles en:"},
}


def testo_avvio(testo, **parametri):
    """The text of the error window in the user's language (if the translation is missing, the English text stays)."""
    try:
        lingua = lingua_corrente()
    except Exception:
        lingua = "en"
    scelto = TESTI_AVVIO.get(testo, {}).get(lingua, testo)
    return scelto.format(**parametri) if parametri else scelto


def mostra_errore(titolo, testo):
    """Shows a serious problem. With the black window it is enough to write it; without the black window
    (icon on the Desktop) nobody would read the log, so a Windows message box appears."""
    print(f"\n{titolo}\n{testo}")
    if os.name == "nt" and _USCITA_ORIGINALE["senza_console"]:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f"{testo}\n\n{testo_avvio('Details in:')}\n{percorso_log()}", titolo, 0x10)   # 0x10 = error icon
        except Exception:
            pass


# ------------------------------------------------------------------------------------------
# 7b. Finding Edge/Chrome and opening the "app" window
# ------------------------------------------------------------------------------------------
def trova_browser_app():
    """Path of Edge or Chrome (None if they cannot be found). Edge first: it is always there on Windows 10/11."""
    forzato = os.environ.get("NEOTRACKER_BROWSER", "")           # used in the tests to simulate a browser
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
    # Last attempt: the programs reachable from the "system path" (also useful on Linux/Mac)
    for nome in ("msedge", "microsoft-edge", "chrome", "google-chrome", "chromium", "chromium-browser"):
        trovato = shutil.which(nome)
        if trovato:
            return trovato
    return None


def argomenti_finestra(exe, url):
    """The list of words used to launch Edge/Chrome. Every line is explained."""
    profilo = Path(CARTELLA_DATI) / "profilo_finestra"
    return [
        exe,
        f"--app={url}",                       # app mode: no address bar or tabs
        f"--user-data-dir={profilo}",         # separate profile: it does not touch your everyday Edge/Chrome
        "--no-first-run",                     # no welcome screens at the first start of the profile
        "--no-default-browser-check",         # do not ask to become the default browser
        "--hide-crash-restore-bubble",        # no "the browser did not close correctly" notice
        "--window-size=1320,900",             # initial size (then Windows remembers the last one used)
    ]


def apri_finestra(url):
    """Opens NeoTracker in its own window. True if something opened."""
    exe = trova_browser_app()
    if exe:
        try:
            if os.name == "nt":
                # DETACHED_PROCESS: the browser lives on its own, even if this program closes.
                flag = getattr(subprocess, "DETACHED_PROCESS", 0x8) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
                subprocess.Popen(argomenti_finestra(exe, url), creationflags=flag, close_fds=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(argomenti_finestra(exe, url), start_new_session=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            print(f"Cannot open the window with {exe}: {e}")
    # Plan B: the default browser, in a normal tab. It works, but the address bar is visible.
    print("Edge/Chrome not found (or they do not start): opening the default browser.")
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


def porta_in_primo_piano():
    """If the NeoTracker window is already open (perhaps minimised), brings it to the front.
    Windows only. True if it was found. Any problem -> False and a new window will be opened."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        # We tell Python that the "window numbers" are 64-bit pointers (otherwise they get truncated).
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        trovate = []
        # "TipoGuarda" describes the function that Windows calls once for each open window.
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
            # We look for an Edge/Chrome window (class Chrome_WidgetWin_1) titled "NeoTracker": the class
            # avoids confusion with, for example, a folder called "NeoTracker".
            if titolo.value == NOME_FINESTRA and classe.value == "Chrome_WidgetWin_1":
                trovate.append(hwnd)
            return True

        user32.EnumWindows(guarda, 0)
        if not trovate:
            return False
        hwnd = trovate[0]
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)                           # 9 = SW_RESTORE: removes the minimised state
        user32.keybd_event(0x12, 0, 0, 0)                         # small trick (pressing and releasing Alt) that makes
        user32.keybd_event(0x12, 0, 2, 0)                         # Windows accept the change of the foreground window
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def _strumento_windows(relativo):
    """Full path of a Windows tool (System32 folder). This way there is no risk of launching
    by mistake a program with the same name found in another folder (for example the current one)."""
    radice = os.environ.get("SystemRoot") or r"C:\Windows"
    return str(Path(radice) / "System32" / relativo)


def chiudi_finestra_app():
    """Closes the app window (only the processes of our separate profile: your everyday Edge/Chrome
    is NOT touched). Needed when you press "Quit" inside the app."""
    profilo = str(Path(CARTELLA_DATI) / "profilo_finestra")
    try:
        if os.name == "nt":
            # PowerShell looks for the processes whose command line contains the folder of the separate
            # profile and closes them. The path is passed through an environment variable (safer than pasting
            # it into the command). "$PID" is PowerShell itself: we exclude it.
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
        pass                                                      # if it fails, the window stays: you close it with the X


# ------------------------------------------------------------------------------------------
# 7c. The "supervisor": every second it checks whether the window has been closed
# ------------------------------------------------------------------------------------------
def sorveglia_finestra(server, passo=1.0):
    """Runs in a separate thread. When the window is closed (and no analysis is running) it stops the server."""
    ultimo_giro = time.monotonic()
    while not server.fine_sorveglianza.wait(passo):               # wait 1 second, then check
        adesso = time.monotonic()
        if adesso - ultimo_giro > 15:
            # The "second" lasted more than 15: the PC was asleep. During sleep the page could not beat, so we
            # do not consider the window closed.
            STATO_FINESTRA.dopo_sospensione(adesso)
        ultimo_giro = adesso
        if STATO_FINESTRA.da_spegnere(adesso, analisi_attiva()):
            print("The NeoTracker window was closed: shutting the program down.")
            server.shutdown()                                     # makes serve_forever() exit in the main thread
            return


# ------------------------------------------------------------------------------------------
# 7d. The actual start-up
# ------------------------------------------------------------------------------------------
def ping_server():
    """If a NeoTracker is already on this port, returns its state (a dictionary); otherwise None."""
    try:
        # Security check (bandit B310): fixed address, this computer.
        with urllib.request.urlopen(f"http://{INDIRIZZO}:{PORTA}/api/ping", timeout=2) as r:   # nosec B310
            d = json.loads(r.read().decode("utf-8"))
            return d if d.get("app") == "NeoTracker" else None
    except Exception:
        return None


def gia_in_esecuzione():
    """True if a NeoTracker is already on this port (e.g. you clicked the icon twice)."""
    return ping_server() is not None


def ferma_analisi_in_corso():
    """If you close the app while it is analysing a photo, it also stops the analysis (with all its processes)."""
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
        prepara_uscita_testo()                                    # before any print()
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        url = f"http://{INDIRIZZO}:{PORTA}/"
        inizializza_db()

        # ---- case 1: NeoTracker is already running (you clicked the icon a second time) ----
        stato = ping_server()
        if stato is not None:
            if stato.get("finestra_aperta") and porta_in_primo_piano():
                print("NeoTracker is already open: I brought the window to the front.")
            else:
                # The running program only accepts whoever presents its session key (see 6c-bis): we read it
                # from the file it wrote at start-up.
                chiave = leggi_token_da_file()
                if stato.get("protetto") and not chiave:
                    mostra_errore(testo_avvio("NeoTracker is already running"),
                                  testo_avvio("I cannot open a new window because the session key is missing.\n"
                                              "Close NeoTracker (from Task Manager, Python process) and reopen it from its icon."))
                    return
                print("NeoTracker is already running: opening a window.")
                apri_finestra(url + (f"?avvio={chiave}" if chiave else ""))
            return

        # ---- case 2: normal start -----
        try:
            server = Server((INDIRIZZO, PORTA), Gestore)
        except OSError as e:
            mostra_errore(testo_avvio("NeoTracker cannot start"),
                          testo_avvio("I cannot use port {porta} ({e}).\n"
                                      "Another program is using it. Close it, or change PORTA at the top of neotracker.py.",
                                      porta=PORTA, e=e))
            return
        STATO_FINESTRA.azzera()                                   # the count of open pages starts again from zero
        scrivi_token_su_file()                                    # the key of this session (a second clicked icon needs it)

        print("=" * 70)
        print(f" NeoTracker {VERSIONE} is running:  {url}")
        print(f" Your data is in: {CARTELLA_DATI}")
        print("=" * 70)
        print(" The app window opens. When you close it, the program shuts itself down")
        print(" (if it is analysing a photo, it finishes the analysis first).")
        print(" This black window, if you see it, is only there to help diagnose any problems.")
        # The key travels only in the address used to open the window (then it becomes a cookie and the
        # address is cleaned up).
        threading.Timer(0.6, lambda: apri_finestra(f"{url}?avvio={TOKEN_SESSIONE}")).start()
        threading.Thread(target=sorveglia_finestra, args=(server,), name="sorvegliante", daemon=True).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.fine_sorveglianza.set()
            cancella_token_file()                                 # the key is no longer valid
            ferma_analisi_in_corso()
            if server.chiusura_richiesta:
                chiudi_finestra_app()                             # "Quit" pressed: I close the window too
            server.server_close()
            print("NeoTracker closed. See you soon.")
    except Exception as e:                                        # unexpected error at start-up: I show it clearly
        traceback.print_exc()
        mostra_errore(testo_avvio("NeoTracker has stopped"), f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    avvia()
