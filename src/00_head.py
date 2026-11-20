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
