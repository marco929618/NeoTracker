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
