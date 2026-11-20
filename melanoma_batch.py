# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# NeoTracker - Copyright (C) 2026 the NeoTracker authors.
# Free software: you can redistribute it and/or modify it under the terms of the GNU General Public License
# version 3 or later. No warranty, not even of fitness for a purpose (see the LICENSE file).
# NOT a medical device and it does not diagnose: see DISCLAIMER.md.
"""
==========================================================================================
 melanoma_batch.py  -  ONE PHOTO IN, ONE REPORT WITH ALL THE METHODS OUT
==========================================================================================

WHAT IT DOES (in plain words)
-----------------------------
You give it the photo of a mole. By itself, it opens one after the other the programs you
installed with the "install_melanoma_repos.ps1" script, makes them look at the photo, and in the end
writes a report like:

    Method 1 said that ...
    Method 2 said that ...
    Method 3 ...

The method numbers are the same as in the installation script and in the guide:

    Method 1 = App 1  (DeborahAdedigba / Melanoma-Detection_App)  - 5 TensorFlow models
    Method 2 = SkinSense (ONLINE service: the photo is sent to an external server!)
    Method 3 = Melanoma-Detector (VukIG)   - it is only a prototype without a model: no analysis
    Method 4 = vatsal30 / Melanoma-Detection - PyTorch, you must have trained the weights
    Method 5 = ukalwa (Android app)        - used on the phone, it cannot run on the PC

HOW TO USE IT (the simplest way)
--------------------------------
 1. Open this file with Spyder.
 2. Press the PLAY button (the green "Run file" arrow).
 3. A window opens: choose the photo of the mole.
 4. Wait (even 5-15 minutes the first time: the models are big).
 5. The report appears in the console and is saved in a folder next to the photo.

If you prefer, you can write the path of the photo below, on the "FOTO = ..." line,
so it does not ask you anything.

From a terminal it is the same:
    python melanoma_batch.py --foto "C:\\path\\mole.jpg"

IMPORTANT: THIS IS NOT A MEDICAL TOOL
-------------------------------------
The programs used are research/study prototypes, not clinically validated. They can
be wrong in both directions: raise a false alarm OR give a false "all clear".
The report is only a note to bring to the dermatology visit, never a replacement
for the visit.

HOW IT IS BUILT (for the curious)
---------------------------------
The programs use different libraries that do not get along in the same Python environment
(TensorFlow on one side, PyTorch on the other). For this reason this file does two jobs:
  - "CONDUCTOR": chooses the photo, starts the "workers" one at a time, collects
    the answers and writes the report. It only uses things already included in Python.
  - "WORKERS": the SAME file, relaunched inside the right .venv environment of each
    project (with the hidden --worker option). Each worker loads its models, looks at the
    photo and writes the answer in a small JSON file.
If a worker breaks, the others go on: the report will simply say which one
failed and why.
"""

# ==========================================================================================
# 1. SETTINGS - these are the only lines you usually need to touch
# ==========================================================================================

# Path of the photo to analyse.
# - Leave it empty ("") and a window opens to choose the photo.
# - Or write the path. The "r" before the quotes is needed by Windows: do not remove it.
# Example:  FOTO = r"C:\Users\YOURNAME\Desktop\nevo.jpg"
FOTO = r""

# What kind of photo is it?
# "normale"      = photo taken with a phone/camera (the most common case)
# "dermoscopica" = photo taken with a dermatoscope (special lens with polarised light)
# "entrambe"     = try both the models for normal photos and those for dermoscopy
# The models are trained on one type or the other: using the wrong type gives
# senseless answers. When in doubt leave "normale".
TIPO_FOTO = "normale"

# Where the project folders were installed (the installation script decided it).
# Path.home() is your personal folder, e.g. C:\Users\YOURNAME
from pathlib import Path
CARTELLA_REPO = Path.home() / "melanoma-repos"

# Switches: put False to skip a method.
USA_APP1 = True          # Method 1 - App 1 (works entirely on your PC)
USA_SKINSENSE = True     # Method 2 - SkinSense. WARNING: IT SENDS THE PHOTO TO AN EXTERNAL SERVER
                         # (Hugging Face). Before sending, the program removes the
                         # photo's metadata (GPS position, phone model, date).
                         # If you do not want the photo to leave your PC, put False.
USA_VATSAL = True        # Method 4 - vatsal30 (only runs if the model_fold_*.bin files exist)

# Address of the online service used by SkinSense (the same one its website uses).
URL_SKINSENSE = "https://souresh-skin-lesion-detection.hf.space/analyze"

# How long to wait at most for each method, in seconds (then it skips it and goes on).
TIMEOUT_APP1 = 40 * 60
TIMEOUT_SKINSENSE = 6 * 60
TIMEOUT_VATSAL = 20 * 60

# ==========================================================================================
# 2. BASIC TOOLS (only libraries included in Python: no installation needed)
# ==========================================================================================

import argparse          # reads the options written in the terminal (--foto, --worker, ...)
import json              # reads/writes JSON files (a text format for exchanging data)
import os                # environment variables and paths
import subprocess        # lets you start another Python program (the "workers")
import sys               # information about the Python in use
import textwrap          # wraps long text neatly
import time              # misura i tempi e prende data/ora
import traceback         # detailed description of errors



def T(testo):
    """Marks an English text that NeoTracker shows translated in the chosen language (dictionaries web/i18n_XX.js).
    Here it does nothing: from the terminal the report stays in English."""
    return testo


# Names of the folders created by the installation script.
CARTELLA_APP1 = "DeborahAdedigba_Melanoma-Detection_App"
CARTELLA_VATSAL = "vatsal30_Melanoma-Detection"

# Accepted image extensions.
ESTENSIONI_OK = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")

# The 6 classes of the App 1 "skin photo" models (PAD-UFES-20 dataset) with their
# meaning and a "rough" judgement: "attenzione" = malignant or pre-malignant lesion,
# "benigno" = benign lesion. It is a simplified classification, only for the summary.
CLASSI_APP1 = {
    "ACK": (T("actinic keratosis, a pre-cancerous lesion"), "attenzione"),
    "BCC": (T("basal cell carcinoma, a skin cancer"), "attenzione"),
    "MEL": (T("melanoma"), "attenzione"),
    "NEV": (T("naevus, i.e. a benign mole"), "benigno"),
    "SCC": (T("squamous cell carcinoma, a skin cancer"), "attenzione"),
    "SEK": (T("seborrhoeic keratosis, benign"), "benigno"),
}
ORDINE_CLASSI_APP1 = ["ACK", "BCC", "MEL", "NEV", "SCC", "SEK"]  # order used by the models


def nuovo_risultato(nome, stato, etichetta=None, valore=None, prob_mel=None,
                    verdetto=None, nota="", gruppo="", dettaglio=None, secondi=None):
    """
    Creates the answer "card" of ONE model. All methods use the same card,
    so the conductor always knows where to find things.

    nome       : name of the model (e.g. "VGG16")
    stato      : "ok" (it answered) | "errore" (it broke) | "non_disponibile" (files/environment
                 missing) | "non_eseguibile" (cannot be done from a PC, by nature)
    etichetta  : the answer in words (e.g. "NEV (naevus, i.e. a benign mole)")
    valore     : confidence of the model in its answer, from 0 to 1 (None if it does not exist)
    prob_mel   : probability of melanoma from 0 to 1, if the model provides it
    verdetto   : "attenzione" | "benigno" | "incerto" | None  (used for the summary)
    nota       : free explanation, mainly in case of error
    gruppo     : subgroup within the method (e.g. "skin photos" / "dermoscopy")
    dettaglio  : dictionary with other numbers (probability per class etc.)
    secondi    : time taken
    """
    return {
        "nome": nome, "stato": stato, "etichetta": etichetta, "valore": valore,
        "prob_mel": prob_mel, "verdetto": verdetto, "nota": nota, "gruppo": gruppo,
        "dettaglio": dettaglio or {}, "secondi": secondi,
    }


def salva_json(percorso, dati):
    """Writes 'dati' to a JSON file (readable text) with the accented letters correct."""
    with open(percorso, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=2)


def e_segnaposto_lfs(percorso):
    """
    The App 1 models are saved with "Git LFS": until you run 'git lfs pull' there is, in their
    place, a fake file of a few lines (a "placeholder") instead of the real model.
    This function says whether the file is still a placeholder.
    """
    try:
        if Path(percorso).stat().st_size > 2048:        # a real model weighs tens of MB
            return False
        with open(percorso, "rb") as f:
            return f.read(40).startswith(b"version https://git-lfs")
    except OSError:
        return False


def apri_immagine_rgb(percorso):
    """
    Opens the photo and returns it in RGB format, rotating it as the phone took it
    (phones save the photo 'crooked' + a note 'rotate it by 90 degrees': here we apply it).
    Requires Pillow, which is present in all the project environments.
    """
    from PIL import Image, ImageOps
    img = Image.open(percorso)
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


# ==========================================================================================
# 3. THE "WORKERS": each one works for one method and runs INSIDE the .venv environment of that project
# ==========================================================================================

# ----------------------------- 3a. METHOD 1: App 1 (TensorFlow) ---------------------------

def lavora_app1(foto, tipo, repo):
    """
    Runs the 10 models of App 1 (5 for skin photos + 5 for dermoscopy), one at a time.
    It faithfully replicates the code of the original app (Melanoma_Detection.py): same
    architectures, same weight files, same sizes and preprocessing.
    Returns the list of answer "cards".
    """
    import gc
    import numpy as np
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")      # fewer technical TensorFlow messages
    import tensorflow as tf
    from tensorflow.keras.models import Model, load_model
    from tensorflow.keras.layers import (Input, Conv2D, MaxPooling2D, Dropout, Flatten, Dense,
                                         BatchNormalization, GlobalAveragePooling2D, concatenate)
    from tensorflow.keras.regularizers import l2
    from tensorflow.keras.applications import VGG16, ResNet50, InceptionResNetV2, EfficientNetB4
    from tensorflow.keras.applications.vgg16 import preprocess_input as prep_vgg16
    from tensorflow.keras.applications.resnet50 import preprocess_input as prep_resnet50
    from tensorflow.keras.applications.efficientnet import preprocess_input as prep_efficientnet
    from tensorflow.keras.applications.inception_resnet_v2 import preprocess_input as prep_inception

    cartella = Path(repo) / CARTELLA_APP1

    # ---- The "recipes" (architectures) of the models, copied from the original app ----------
    # Each model receives 6 "channels": 3 are the photo (red, green, blue) and 3 are a "saliency
    # map" (a sort of attention map). The original app uses all zeros for the map.

    def costruisci_cnn(forma=(224, 224, 6), classi=6):
        """'Home-made' network with 5 convolution blocks, applied to photo and map."""
        ingresso = Input(forma)
        parte_foto = ingresso[:, :, :, :3]          # the first 3 channels = the photo
        parte_mappa = ingresso[:, :, :, 3:]         # the last 3 channels = the saliency map

        def ramo(x):
            for filtri in (32, 64, 128, 256, 512):
                x = Conv2D(filtri, (3, 3), activation='relu', padding='same', kernel_regularizer=l2(0.01))(x)
                x = BatchNormalization()(x)
                x = Conv2D(filtri, (3, 3), activation='relu', padding='same', kernel_regularizer=l2(0.01))(x)
                x = BatchNormalization()(x)
                x = MaxPooling2D(pool_size=(2, 2))(x)
                x = Dropout(0.5)(x)
            return Flatten()(x)

        unito = tf.keras.layers.Concatenate()([ramo(parte_foto), ramo(parte_mappa)])
        denso = Dense(256, activation='relu', kernel_regularizer=l2(0.01))(unito)
        denso = Dropout(0.5)(denso)
        return Model(inputs=ingresso, outputs=Dense(classi, activation='softmax')(denso))

    def costruisci_con_base(classe_base, lato, classi=6):
        """
        'Transfer' model: takes a famous network (VGG16, ResNet50, EfficientNetB4,
        InceptionResNetV2), applies it to the photo and the map, joins the two results and
        passes them to two final layers that choose among the 6 classes.
        """
        base = classe_base(include_top=False, weights=None, input_shape=(lato, lato, 3))
        ingresso = Input((lato, lato, 6))
        x = GlobalAveragePooling2D()(base(ingresso[:, :, :, :3], training=False))
        y = GlobalAveragePooling2D()(base(ingresso[:, :, :, 3:], training=False))
        unito = concatenate([x, y])
        unito = Dense(256, activation='relu')(unito)
        unito = Dropout(0.5)(unito)
        return Model(inputs=ingresso, outputs=Dense(classi, activation='softmax')(unito))

    def prepara_input(lato, funzione_prep, canali):
        """
        Reads the photo, brings it to side x side pixels (as Keras does: 'nearest' method),
        applies the model's preprocessing and, if the model wants 6 channels, adds
        the 3 map channels as zeros (same behaviour as the original app).
        """
        from PIL import Image
        img = apri_immagine_rgb(foto).resize((lato, lato), Image.NEAREST)
        a = np.expand_dims(np.asarray(img, dtype="float32"), axis=0)      # shape (1, side, side, 3)
        if funzione_prep is not None:
            a = funzione_prep(a.copy())
        if canali == 6:
            a = np.concatenate((a, np.zeros_like(a)), axis=-1)
        return a

    def etichetta_classi(p):
        """From 6 probabilities to: readable label, verdict, confidence, melanoma prob."""
        i = int(np.argmax(p))
        codice = ORDINE_CLASSI_APP1[i]
        descr, verdetto = CLASSI_APP1[codice]
        return (f"{codice} ({descr})", verdetto, float(p[i]),
                float(p[ORDINE_CLASSI_APP1.index("MEL")]),
                {c: round(float(p[k]), 4) for k, c in enumerate(ORDINE_CLASSI_APP1)})

    risultati = []

    def tutti_segnaposto(nomi_file):
        """True if ALL the given files exist but are still Git LFS placeholders."""
        percorsi = [cartella / n for n in nomi_file]
        return all(p.exists() and e_segnaposto_lfs(p) for p in percorsi)

    messaggio_lfs = (T("the App 1 models have not been downloaded: they are still Git LFS placeholders. Open "
                       f"PowerShell in the folder {cartella}, run 'git lfs pull', then try again."))

    # ---- "Skin photos" group: recipe + weights files ----------------------------------------
    gruppo_pelle = [
        # name,               recipe,                                              weights file,
        # side, preprocessing
        ("CNN",               lambda: costruisci_cnn(),                              "CNN_skin_classifier_weights.weights.h5",  224, None),
        ("VGG16",             lambda: costruisci_con_base(VGG16, 224),               "best_VGG16_weights.weights.h5",           224, prep_vgg16),
        ("ResNet50",          lambda: costruisci_con_base(ResNet50, 224),            "best_ResNet50_weights.weights.h5",        224, prep_resnet50),
        ("EfficientNetB4",    lambda: costruisci_con_base(EfficientNetB4, 380),      "best_EfficientNetB4_weights.weights.h5",  380, prep_efficientnet),
        ("InceptionResNetV2", lambda: costruisci_con_base(InceptionResNetV2, 299),   "best_InceptionResNetV2_weights.weights.h5", 299, prep_inception),
    ]
    # ---- "Dermoscopy" group: models already complete in a single .keras file ----------------
    gruppo_derm = [
        ("CNN",               "DM_melanoma_cnn_with_saliency.keras",          224, None),
        ("VGG16",             "DM_vgg16_model_with_saliency.keras",           224, prep_vgg16),
        ("ResNet50",          "DM_best_ResNet50_model.keras",                 224, prep_resnet50),
        ("EfficientNetB4",    "DM_efficientnetb4_model_with_saliency.keras",  380, prep_efficientnet),
        ("InceptionResNetV2", "DM_InceptionResNetV2_model.keras",             299, prep_inception),
    ]

    def libera_memoria():
        """Unloads the model from memory before the next one (some weigh quite a lot)."""
        tf.keras.backend.clear_session()
        gc.collect()

    # ---------------------------- skin photos  ------------------------------------------------
    if tipo in ("normale", "entrambe") and tutti_segnaposto([g[2] for g in gruppo_pelle]):
        # Typical case of someone who has not yet run 'git lfs pull': a single clear message, not five.
        risultati.append(nuovo_risultato("5 skin-photo models", "non_disponibile",
                                         gruppo=T("skin photos"), nota=messaggio_lfs))
    elif tipo in ("normale", "entrambe"):
        for nome, ricetta, file_pesi, lato, prep in gruppo_pelle:
            t0 = time.time()
            percorso = cartella / file_pesi
            try:
                if not percorso.exists():
                    raise FileNotFoundError(f"file {file_pesi} not found in {cartella}")
                if e_segnaposto_lfs(percorso):
                    risultati.append(nuovo_risultato(
                        nome, "non_disponibile", gruppo=T("skin photos"),
                        nota=T(f"{file_pesi} is still a Git LFS placeholder: open PowerShell in the folder "
                               f"{cartella} and run 'git lfs pull'.")))
                    continue
                modello = ricetta()
                modello.load_weights(str(percorso))                       # carica i pesi addestrati
                x = prepara_input(lato, prep, 6)
                p = np.asarray(modello.predict(x, verbose=0))[0]          # the 6 probabilities
                etichetta, verdetto, sicurezza, p_mel, tutte = etichetta_classi(p)
                risultati.append(nuovo_risultato(
                    nome, "ok", etichetta, sicurezza, p_mel, verdetto, gruppo=T("skin photos"),
                    dettaglio={"probabilita_per_classe": tutte}, secondi=round(time.time() - t0, 1)))
            except Exception as e:
                traceback.print_exc()
                risultati.append(nuovo_risultato(nome, "errore", gruppo=T("skin photos"),
                                                 nota=f"{type(e).__name__}: {str(e)[:300]}"))
            finally:
                libera_memoria()

    # ---------------------------- dermoscopy  -------------------------------------------------
    if tipo in ("dermoscopica", "entrambe") and tutti_segnaposto([g[1] for g in gruppo_derm]):
        risultati.append(nuovo_risultato("5 dermoscopy models", "non_disponibile",
                                         gruppo=T("dermoscopy"), nota=messaggio_lfs))
    elif tipo in ("dermoscopica", "entrambe"):
        for nome, file_modello, lato_app, prep in gruppo_derm:
            t0 = time.time()
            percorso = cartella / file_modello
            try:
                if not percorso.exists():
                    raise FileNotFoundError(f"file {file_modello} not found in {cartella}")
                if e_segnaposto_lfs(percorso):
                    risultati.append(nuovo_risultato(
                        nome, "non_disponibile", gruppo=T("dermoscopy"),
                        nota=T(f"{file_modello} is still a Git LFS placeholder: run 'git lfs pull' in the folder "
                               f"{cartella}.")))
                    continue
                # compile=False: we only need it to make predictions, not to retrain it.
                # NB: I never disable Keras's 'safe mode': a model file downloaded from
                # the internet must not be run blindly.
                modello = load_model(str(percorso), compile=False)
                forma = modello.input_shape
                if isinstance(forma, list):
                    raise ValueError("the model has more than one input: not supported")
                canali = forma[-1]
                lato = forma[1] if (forma[1] is not None and forma[1] == forma[2]) else lato_app
                if canali not in (3, 6):
                    raise ValueError(f"unexpected number of channels: {canali}")
                x = prepara_input(lato, prep, canali)
                p = np.asarray(modello.predict(x, verbose=0))[0]
                n = len(p)
                # The original app ALWAYS reads the output as 6 skin classes (a programming error of its own:
                # 'if tab1' is always true). Here instead I look at how many outputs the model has and interpret them accordingly.
                if n == 1:
                    pm = float(p[0])
                    etich = "maligno" if pm > 0.5 else "benigno"
                    risultati.append(nuovo_risultato(
                        nome, "ok", etich, max(pm, 1 - pm), None,
                        "attenzione" if pm > 0.5 else "benigno", gruppo=T("dermoscopy"),
                        nota=T(f"probability of malignancy estimated by the model: {pm}"),
                        dettaglio={"prob_maligno": round(pm, 4)}, secondi=round(time.time() - t0, 1)))
                elif n == 2:
                    pm = float(p[1])
                    etich = "maligno" if pm > 0.5 else "benigno"
                    risultati.append(nuovo_risultato(
                        nome, "ok", etich, max(pm, 1 - pm), None,
                        "attenzione" if pm > 0.5 else "benigno", gruppo=T("dermoscopy"),
                        nota=T("I assume the 2 outputs are [benign, malignant]; order cannot be verified"),
                        dettaglio={"prob_benigno": round(float(p[0]), 4), "prob_maligno": round(pm, 4)},
                        secondi=round(time.time() - t0, 1)))
                elif n == 6:
                    etichetta, verdetto, sicurezza, p_mel, tutte = etichetta_classi(p)
                    risultati.append(nuovo_risultato(
                        nome, "ok", etichetta, sicurezza, p_mel, verdetto, gruppo=T("dermoscopy"),
                        nota=T("output interpreted as the 6 skin classes (not verifiable)"),
                        dettaglio={"probabilita_per_classe": tutte}, secondi=round(time.time() - t0, 1)))
                else:
                    risultati.append(nuovo_risultato(
                        nome, "ok", f"classe numero {int(np.argmax(p))}", float(np.max(p)), None, "incerto",
                        gruppo=T("dermoscopy"), nota=T(f"the model has {n} outputs: meaning unknown"),
                        secondi=round(time.time() - t0, 1)))
            except Exception as e:
                traceback.print_exc()
                risultati.append(nuovo_risultato(nome, "errore", gruppo=T("dermoscopy"),
                                                 nota=f"{type(e).__name__}: {str(e)[:300]}"))
            finally:
                libera_memoria()

    return risultati


# ----------------------------- 3b. METHOD 2: SkinSense (online)  --------------------------

def lavora_skinsense(foto, url, cartella_out):
    """
    Sends the photo to the online service used by the SkinSense website and reads the answer.
    BEFORE sending, it re-encodes the photo from scratch, so as to throw away all the metadata
    (GPS position, phone model, date and time): only the pixels are sent.
    """
    import base64
    import urllib.request
    import urllib.error
    import uuid
    import io

    t0 = time.time()
    # Defence: the address must be https (no "file:" or "ftp:", which would read files from your PC).
    if not str(url).lower().startswith("https://"):
        return [nuovo_risultato("SkinSense", "errore", nota=T("service address not allowed (https required)"))]
    # ---- 1. Cleaning the metadata -----------------------------------------------------------
    nota_pulizia = ""
    try:
        img = apri_immagine_rgb(foto)
        # I reduce huge photos (phones take 12 megapixels): the online model reduces them
        # anyway and so the sending is much faster.
        img.thumbnail((1600, 1600))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=92)      # without 'exif=': the metadata is not written
        contenuto = buffer.getvalue()
    except Exception as e:
        # If Pillow fails, I do NOT send the original (it might contain the GPS): I stop.
        return [nuovo_risultato("SkinSense", "errore",
                                nota=T(f"I cannot prepare the photo safely: {e}"))]

    # ---- 2. Building the 'multipart' HTTP request (the standard way to send files) -----------
    confine = uuid.uuid4().hex
    corpo = b"".join([
        f"--{confine}\r\n".encode(),
        b'Content-Disposition: form-data; name="image"; filename="foto.jpg"\r\n',
        b"Content-Type: image/jpeg\r\n\r\n",
        contenuto,
        f"\r\n--{confine}--\r\n".encode(),
    ])
    richiesta = urllib.request.Request(
        url, data=corpo, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={confine}",
                 "Accept": "application/json"})

    # ---- 3. Sending, with a second attempt (the free service may be 'asleep') -----------------
    risposta = None
    ultimo_errore = ""
    for tentativo in (1, 2):
        try:
            # Security check (bandit B310): https checked above.
            with urllib.request.urlopen(richiesta, timeout=150) as r:   # nosec B310
                risposta = json.loads(r.read(5 * 1024 * 1024).decode("utf-8", errors="replace"))   # at most 5 MB of response
            break
        except urllib.error.HTTPError as e:
            ultimo_errore = f"the server answered with HTTP error {e.code}"
        except Exception as e:
            ultimo_errore = f"{type(e).__name__}: {e}"
        if tentativo == 1:
            print(f"SkinSense: first attempt failed ({ultimo_errore}); retrying in 30 seconds...")
            time.sleep(30)
    if risposta is None:
        return [nuovo_risultato("SkinSense", "errore", nota=T(f"service unreachable: {ultimo_errore}"))]

    # ---- 4. Reading the response -------------------------------------------------------------
    nome_lesione = str(risposta.get("full_name") or "").strip()
    confidenza = risposta.get("confidence")
    try:
        c = float(confidenza)
        c = c / 100.0 if c > 1 else c            # the service gives it as a percentage (e.g. 87.3)
    except (TypeError, ValueError):
        c = None

    # Rough judgement from the name of the lesion, comparing keywords.
    n = nome_lesione.lower()
    if "melanoma" in n or "basal" in n or "actinic" in n or "squamous" in n or "carcinoma" in n:
        verdetto = "attenzione"
    elif any(k in n for k in ("nevi", "nevus", "benign", "dermatofibroma", "vascular")):
        verdetto = "benigno"
    else:
        verdetto = "incerto"

    # The response may contain an image (probably a heat map): if it is a real image,
    # I save it as a separate file; I do not print it in the report.
    mappa_salvata = ""
    viz = risposta.get("visualization")
    if isinstance(viz, str) and len(viz) > 200:
        try:
            dati = base64.b64decode(viz.split(",", 1)[-1])
            if dati[:8] == b"\x89PNG\r\n\x1a\n" or dati[:3] == b"\xff\xd8\xff":
                estensione = ".png" if dati[:4] == b"\x89PNG" else ".jpg"
                percorso_mappa = Path(cartella_out) / ("skinsense_mappa" + estensione)
                percorso_mappa.write_bytes(dati)
                mappa_salvata = percorso_mappa.name
        except Exception:
            pass

    dettaglio = {k: risposta.get(k) for k in ("risk_level", "description", "symptoms", "recommendations")
                 if risposta.get(k) is not None}
    if mappa_salvata:
        dettaglio["mappa_salvata_in"] = mappa_salvata
    rischio = risposta.get("risk_level")
    nota = f"risk level declared by the service: {rischio}" if rischio else ""
    if not nome_lesione:
        return [nuovo_risultato("SkinSense", "errore", nota=T("response without a lesion name: {risposta}").format(
                                    risposta=json.dumps(risposta, ensure_ascii=False)[:300]))]
    return [nuovo_risultato("SkinSense", "ok", nome_lesione, c, None, verdetto, nota=nota,
                            dettaglio=dettaglio, secondi=round(time.time() - t0, 1))]


# ----------------------------- 3c. METHOD 4: vatsal30 (PyTorch)  --------------------------

def lavora_vatsal(foto, repo):
    """
    Runs the 'committee' of SE-ResNeXt50 models of vatsal30 (up to 5, one per 'fold') and
    averages them. It works ONLY if the files model_fold_0.bin ... model_fold_4.bin exist
    in the 'model' folder: the repository does NOT include them, they must be trained with the
    SIIM-ISIC dataset from Kaggle (many GB).
    """
    t0 = time.time()
    cartella = Path(repo) / CARTELLA_VATSAL
    pesi = sorted((cartella / "model").glob("model_fold_*.bin"))
    if not pesi:
        return [nuovo_risultato(
            "SE-ResNeXt50 x5", "non_disponibile",
            nota=T("the trained weights are missing: in the folder {cartella} there are no files "
                   "model_fold_0.bin ... model_fold_4.bin. The repository does not contain them: they must be "
                   "produced with train.py on the SIIM-ISIC dataset.").format(cartella=cartella / 'model'))]

    import numpy as np
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    import pretrainedmodels

    class SEResNext50(nn.Module):
        """Same network as the original (prediction.py), without the part that is only needed for training."""
        def __init__(self):
            super().__init__()
            self.base_model = pretrainedmodels.__dict__["se_resnext50_32x4d"](pretrained=None)
            self.l0 = nn.Linear(2048, 1)          # a single number as output: >0 = melanoma, <=0 = no

        def forward(self, immagine):
            x = self.base_model.features(immagine)
            x = F.adaptive_avg_pool2d(x, 1).reshape(immagine.shape[0], -1)
            return self.l0(x)

    # Preparing the photo: the network was trained on 224x224 images (see the project's README),
    # normalised with the ImageNet means/standard deviations.
    from PIL import Image
    img = apri_immagine_rgb(foto).resize((224, 224), Image.BILINEAR)
    a = np.asarray(img, dtype="float32") / 255.0
    media = np.array([0.485, 0.456, 0.406], dtype="float32")
    dev = np.array([0.229, 0.224, 0.225], dtype="float32")
    a = ((a - media) / dev).transpose(2, 0, 1)            # from (height, width, colours) to (colours, height, width)
    x = torch.from_numpy(a).unsqueeze(0)

    punteggi = []
    for percorso in pesi:
        modello = SEResNext50()
        # weights_only=True: the file can only contain numbers, never executable code (a tampered weights file
        # cannot run anything). It needs PyTorch 1.13 or newer: with an older one we stop
        # instead of loading the file "the old way", which would be insecure.
        try:
            stato = torch.load(str(percorso), map_location="cpu", weights_only=True)
        except TypeError:
            raise RuntimeError("PyTorch is too old: update it (pip install -U torch) to load the weights safely")
        modello.load_state_dict(stato)
        modello.eval()
        with torch.no_grad():
            punteggi.append(float(modello(x).reshape(-1)[0]))
    media_punteggi = sum(punteggi) / len(punteggi)
    prob = 1.0 / (1.0 + float(np.exp(-media_punteggi)))     # sigmoid: from score to probability
    melanoma = media_punteggi > 0                            # same threshold as the original app
    return [nuovo_risultato(
        f"SE-ResNeXt50 x{len(pesi)}", "ok",
        T("melanoma detected") if melanoma else T("melanoma not detected"),
        prob if melanoma else 1 - prob, prob, "attenzione" if melanoma else "benigno",
        nota=T("average of {n} models; mean score {media} (threshold 0)").format(n=len(pesi), media=f"{media_punteggi:+.2f}"),
        dettaglio={"punteggi_per_fold": [round(s, 3) for s in punteggi]},
        secondi=round(time.time() - t0, 1))]


def esegui_worker(nome, args):
    """Entry point of the 'workers': does the job of the requested method and writes the JSON."""
    try:
        # First of all I check that the photo really opens: if it is damaged I say so ONCE
        # instead of making every model fail with the same error.
        try:
            apri_immagine_rgb(args.foto).close()
        except Exception as e:
            salva_json(args.out, [nuovo_risultato(nome, "errore",
                                                  nota=T("the photo does not open as an image ({tipo}): "
                                                         "{dettaglio}").format(tipo=type(e).__name__, dettaglio=str(e)[:200]))])
            return
        if nome == "app1":
            risultati = lavora_app1(args.foto, args.tipo, args.repo)
        elif nome == "skinsense":
            risultati = lavora_skinsense(args.foto, args.url, Path(args.out).parent)
        elif nome == "vatsal":
            risultati = lavora_vatsal(args.foto, args.repo)
        else:
            raise ValueError(f"unknown worker: {nome}")
    except Exception as e:
        traceback.print_exc()
        risultati = [nuovo_risultato(nome, "errore", nota=f"{type(e).__name__}: {str(e)[:300]}")]
    salva_json(args.out, risultati)


# ==========================================================================================
# 4. THE "CONDUCTOR": chooses the photo, starts the workers, writes the report
# ==========================================================================================

def trova_python_venv(cartella):
    """Looks for the Python of a project's .venv environment (Windows: Scripts\\python.exe)."""
    for relativo in ("Scripts/python.exe", "bin/python"):
        candidato = Path(cartella) / ".venv" / relativo
        if candidato.exists():
            return candidato
    return None


def scegli_foto(args):
    """Decides which photo to use: from the terminal, from the FOTO setting, or with a window."""
    percorso = args.foto or FOTO
    if not percorso:
        try:
            import tkinter as tk
            from tkinter import filedialog
            radice = tk.Tk()
            radice.withdraw()                       # I hide the empty background window
            radice.attributes("-topmost", True)     # I bring the selector to the front
            percorso = filedialog.askopenfilename(
                title="Choose the photo of the mole to analyse",
                filetypes=[("Immagini", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff"), ("All files", "*.*")])
            radice.destroy()
        except Exception:
            percorso = input("Type the full path of the photo and press Enter: ").strip().strip('"')
    return Path(percorso) if percorso else None


def lancia_operaio(nome, python_exe, argomenti, timeout, cartella_out):
    """
    Starts the worker 'nome' in a separate process, with the given Python, and collects
    its answer. Whatever goes wrong becomes an error 'card' instead of a crash.
    Everything the worker writes to the screen ends up in the file log_<nome>.txt.
    """
    file_json = Path(cartella_out) / f"_risposta_{nome}.json"
    file_log = Path(cartella_out) / f"log_{nome}.txt"
    comando = [str(python_exe), str(Path(__file__).resolve()), "--worker", nome, "--out", str(file_json)] + argomenti
    ambiente = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", TF_CPP_MIN_LOG_LEVEL="2")
    t0 = time.time()
    try:
        with open(file_log, "w", encoding="utf-8", errors="replace") as log:
            subprocess.run(comando, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, env=ambiente)
    except subprocess.TimeoutExpired:
        return [nuovo_risultato(nome, "errore", nota=T("stopped after {minuti} minutes (maximum time)").format(minuti=timeout // 60))]
    except Exception as e:
        return [nuovo_risultato(nome, "errore", nota=T(f"cannot start: {e}"))]
    if file_json.exists():
        try:
            dati = json.loads(file_json.read_text(encoding="utf-8"))
            file_json.unlink()                                  # the temporary file is no longer needed
            return dati
        except Exception as e:
            return [nuovo_risultato(nome, "errore", nota=T(f"unreadable response: {e}"))]
    # No answer: the worker died before writing. I take the last lines of the log.
    try:
        ultime = [r for r in file_log.read_text(encoding="utf-8", errors="replace").splitlines() if r.strip()][-6:]
    except OSError:
        ultime = []
    return [nuovo_risultato(nome, "errore",
                            nota="the program closed without an answer. Last lines: " + " | ".join(ultime)[:500])]


def percentuale(x):
    """0.617 -> '62%'; None -> '-'."""
    return "-" if x is None else f"{x:.0%}"


def a_capo(testo, rientro="      "):
    """
    Wraps a long text with a uniform indent (for the report).
    If the text already contains intended line breaks (\\n), it respects them.
    """
    paragrafi = testo.split("\n")
    return "\n".join(textwrap.fill(p, width=96, initial_indent=rientro, subsequent_indent=rientro)
                     if p.strip() else "" for p in paragrafi)


def frase_conteggio(risultati):
    """Summarises 'how many models said what', e.g. '4 of 5: NEV (...); 1 of 5: MEL (...)'."""
    ok = [r for r in risultati if r["stato"] == "ok"]
    if not ok:
        return ""
    conteggi = {}
    for r in ok:
        conteggi[r["etichetta"]] = conteggi.get(r["etichetta"], 0) + 1
    parti = [f"{n} of {len(ok)}: {et}" for et, n in sorted(conteggi.items(), key=lambda kv: -kv[1])]
    return "; ".join(parti)


def verdetto_metodo(risultati):
    """
    A single judgement for the whole method, for the final summary:
    'attenzione' | 'benigno' | 'discordante' (its models disagree) | None (no result).
    """
    v = [r["verdetto"] for r in risultati if r["stato"] == "ok" and r["verdetto"] in ("attenzione", "benigno")]
    if not v:
        return None
    if all(x == "attenzione" for x in v):
        return "attenzione"
    if all(x == "benigno" for x in v):
        return "benigno"
    return "discordante"


def righe_metodo(numero, titolo, risultati, introduzione=""):
    """Builds the text lines of the report for ONE method."""
    righe = ["", "-" * 98, f"METHOD {numero} - {titolo}", "-" * 98]
    if introduzione:
        righe.append(a_capo(introduzione, "  "))
    ok = [r for r in risultati if r["stato"] == "ok"]
    # ---- sentence "Method N said that ..." ----
    if ok:
        righe.append("")
        for g in dict.fromkeys(r["gruppo"] for r in ok):          # groups in the order in which they appear
            sotto = [r for r in ok if r["gruppo"] == g]
            righe.append(a_capo(f"METHOD {numero} SAID THAT" + (f" [{g}]" if g else "")
                                + " -> " + frase_conteggio(sotto), "  "))
        righe.append("")
    # ---- one line per model ----
    n_gruppi = len({r["gruppo"] for r in risultati if r["gruppo"]})      # the group name is repeated only if there is more than one
    for r in risultati:
        pre = f"  [{r['gruppo']}] " if (r["gruppo"] and n_gruppi > 1) else "  "
        if r["stato"] == "ok":
            extra = f"  [prob. melanoma: {percentuale(r['prob_mel'])}]" if r["prob_mel"] is not None else ""
            riga = f"{pre}- {r['nome']:<18} -> {r['etichetta']}  (confidence {percentuale(r['valore'])}){extra}"
            righe.append(textwrap.fill(riga, width=98, subsequent_indent="        "))
            if r["nota"]:
                righe.append(a_capo(r["nota"], "        "))
        elif r["stato"] == "non_disponibile":
            righe.append(f"{pre}- {r['nome']:<18} NOT AVAILABLE")
            righe.append(a_capo(r["nota"], "        "))
        elif r["stato"] == "non_eseguibile":
            righe.append(a_capo(r["nota"], "  "))
        else:
            righe.append(f"{pre}- {r['nome']:<18} ERROR")
            righe.append(a_capo(r["nota"], "        "))
    return righe


def costruisci_rapporto(foto, tipo, metodi, durata):
    """Assembles the full text of the report (header, 5 methods, summary, warnings)."""
    righe = ["=" * 98,
             " AUTOMATIC REPORT - COMPARISON OF THE METHODS ON THE SAME PHOTO",
             f" Photo: {foto.name}    Declared type: {tipo}",
             f" Date: {time.strftime('%d/%m/%Y %H:%M')}    Duration: {durata // 60:.0f} min {durata % 60:.0f} s",
             "=" * 98]
    for numero, titolo, risultati, intro in metodi:
        righe += righe_metodo(numero, titolo, risultati, intro)

    # ------------------------------ final summary  ------------------------------------------
    righe += ["", "=" * 98, " SUMMARY", "=" * 98]
    giudizi = {}
    for numero, titolo, risultati, intro in metodi:
        giudizi[numero] = verdetto_metodo(risultati)
    con_risultato = [n for n, g in giudizi.items() if g is not None]
    attenzione = [n for n, g in giudizi.items() if g == "attenzione"]
    benigni = [n for n, g in giudizi.items() if g == "benigno"]
    discordi = [n for n, g in giudizi.items() if g == "discordante"]
    senza = [n for n, g in giudizi.items() if g is None]
    elenco = lambda lista: ", ".join(f"method {n}" for n in lista) if lista else "none"
    righe.append(f"  {'Methods that gave a result':<36}: {len(con_risultato)} of {len(metodi)}")
    righe.append(f"  {'Flag a lesion TO WATCH':<36}: {elenco(attenzione)}")
    righe.append(f"  {'Indicate a BENIGN lesion':<36}: {elenco(benigni)}")
    righe.append(f"  {'With models that disagree':<36}: {elenco(discordi)}")
    righe.append(f"  {'No result (see above for why)':<36}: {elenco(senza)}")
    righe.append("")
    if not con_risultato:
        giudizio = "No method produced a result: check the reasons given above."
    elif attenzione or discordi:
        giudizio = ("At least one method (or one of its models) flags a lesion to watch. It is not a "
                    "diagnosis and these tools are often wrong, but it is one more reason not to postpone "
                    "the dermatology visit and to bring this report.")
    else:
        giudizio = ("All the methods that answered indicate a benign lesion. This does NOT rule out a "
                    "melanoma: the tools are not clinically validated and are also wrong in this "
                    "direction. If the mole is asymmetric, has irregular borders, different colours, is larger "
                    "than 6 mm or has changed over time, the visit is still necessary.")
    righe.append(a_capo(giudizio, "  "))
    righe += ["", "-" * 98, " WARNINGS", "-" * 98]
    for avv in (
        "This report is NOT a diagnosis. The programs used are research prototypes, not medical devices.",
        "The methods are trained on photographs different from yours: changing light, distance or camera can change the answer.",
        "The App 1 models here receive an empty 'saliency map' (as the original app does): it is a "
        "simplification that may worsen their reliability.",
        "If the methods disagree, it is normal: it only means that none of them is reliable on its own.",
        "Bring to the visit the photo, this report and the date on which you noticed the mole / any changes.",
    ):
        righe.append(a_capo("* " + avv, "  "))
    return "\n".join(righe)


def principale():
    """Main function: it is the one that starts when you press PLAY."""
    # ---- Reading the options (only needed from the terminal; in Spyder they stay at the default values) ---
    parser = argparse.ArgumentParser(description="Analyse a photo with all the installed methods.")
    parser.add_argument("--foto", default="", help="path of the photo")
    parser.add_argument("--tipo", default=TIPO_FOTO, choices=["normale", "dermoscopica", "entrambe"])
    parser.add_argument("--repo", default=str(CARTELLA_REPO), help="folder where the installed projects are")
    parser.add_argument("--url", default=URL_SKINSENSE, help="address of the SkinSense service")
    parser.add_argument("--senza-app1", action="store_true")
    parser.add_argument("--senza-skinsense", action="store_true")
    parser.add_argument("--senza-vatsal", action="store_true")
    parser.add_argument("--out-dir", default="", help="folder where to save the report (default: next to the photo)")
    parser.add_argument("--worker", default="", help=argparse.SUPPRESS)        # internal use
    parser.add_argument("--out", default="", help=argparse.SUPPRESS)           # internal use
    args, _ = parser.parse_known_args()      # 'known': ignores any extra options added by Spyder

    # If I was started as a 'worker', I just do my job.
    if args.worker:
        esegui_worker(args.worker, args)
        return

    # Makes accented letters readable in Windows consoles too (where possible).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    # ---- Choosing and checking the photo ----
    foto = scegli_foto(args)
    if foto is None or not foto.exists():
        print("No valid photo selected (or file not found). Stopping.")
        return
    if foto.suffix.lower() not in ESTENSIONI_OK:
        extra = " HEIC photos from iPhones must first be converted to JPG." if foto.suffix.lower() in (".heic", ".heif") else ""
        print(f"Format '{foto.suffix}' not supported (accepted: {', '.join(ESTENSIONI_OK)}).{extra}")
        return
    repo = Path(args.repo)
    if not repo.exists():
        print(f"Cannot find the projects folder: {repo}\nCheck CARTELLA_REPO at the top of this file.")
        return
    foto = foto.resolve()

    # ---- Folder where to save the report: next to the photo, one for each analysis -----
    if args.out_dir:
        cartella_out = Path(args.out_dir)
    else:
        cartella_out = foto.parent / f"rapporto_melanoma_{foto.stem}_{time.strftime('%Y%m%d-%H%M%S')}"
    cartella_out.mkdir(parents=True, exist_ok=True)
    print(f"Photo: {foto}\nType: {args.tipo}\nThe report will be saved in: {cartella_out}\n")

    t_inizio = time.time()
    python_app1 = trova_python_venv(repo / CARTELLA_APP1)
    python_vatsal = trova_python_venv(repo / CARTELLA_VATSAL)
    metodi = []          # list of (number, title, results, introduction)

    # ---- METHOD 1: App 1 ----
    titolo1 = T("App 1 (DeborahAdedigba) - TensorFlow models")
    if USA_APP1 and not args.senza_app1:
        print("Method 1 (App 1): starting... the first time it may take quite a while, the models are large.")
        py = python_app1 or Path(sys.executable)
        intro = "" if python_app1 else (T("Warning: I did not find App 1's .venv environment; using the current "
                                          "Python."))
        r1 = lancia_operaio("app1", py, ["--foto", str(foto), "--tipo", args.tipo, "--repo", str(repo)],
                            TIMEOUT_APP1, cartella_out)
        metodi.append((1, titolo1, r1, intro))
    else:
        metodi.append((1, titolo1, [nuovo_risultato("App 1", "non_eseguibile", nota=T("Method 1 turned off in the settings."))], ""))

    # ---- METHOD 2: SkinSense ----
    titolo2 = T("SkinSense (online service)")
    if USA_SKINSENSE and not args.senza_skinsense:
        print("Method 2 (SkinSense): sending the photo (without metadata) to the online service...")
        py = python_app1 or Path(sys.executable)
        r2 = lancia_operaio("skinsense", py, ["--foto", str(foto), "--url", args.url], TIMEOUT_SKINSENSE, cartella_out)
        metodi.append((2, titolo2, r2, T("This method sends the pixels of the photo (not the metadata) to an "
                                         "external server.")))
    else:
        metodi.append((2, titolo2, [nuovo_risultato(
            "SkinSense", "non_eseguibile",
            nota=T("Method 2 not run (turned off in the settings): the photo did not leave the PC."))], ""))

    # ---- METHOD 3: Melanoma-Detector (no analysis possible) ----
    metodi.append((3, T("Melanoma-Detector (VukIG)"), [nuovo_risultato(
        "Melanoma-Detector", "non_eseguibile",
        nota=T("Method 3 did NOT analyse the photo: the project is a prototype without a model. Its server "
               "merely receives the image (no neural network), so any reassuring text it shows does not come "
               "from an analysis and has no value."))], ""))

    # ---- METHOD 4: vatsal30 ----
    titolo4 = T("vatsal30 / Melanoma-Detection (PyTorch)")
    if USA_VATSAL and not args.senza_vatsal:
        print("Method 4 (vatsal30): starting...")
        py = python_vatsal or Path(sys.executable)
        r4 = lancia_operaio("vatsal", py, ["--foto", str(foto), "--repo", str(repo)], TIMEOUT_VATSAL, cartella_out)
        metodi.append((4, titolo4, r4, ""))
    else:
        metodi.append((4, titolo4, [nuovo_risultato("vatsal30", "non_eseguibile", nota=T("Method 4 turned off in the settings."))], ""))

    # ---- METHOD 5: ukalwa (Android) ----
    metodi.append((5, T("ukalwa / melanoma-detection (Android app)"), [nuovo_risultato(
        "ukalwa", "non_eseguibile",
        nota=T("Method 5 is an Android app: it cannot run on the PC. Install the APK on the phone, frame the "
               "mole and note the result by hand below.\n"
               "App result on the phone: ______________________________"))], ""))

    # ---- Report ----
    testo = costruisci_rapporto(foto, args.tipo, metodi, time.time() - t_inizio)
    print("\n" + testo)
    (cartella_out / "rapporto.txt").write_text(testo, encoding="utf-8-sig")      # utf-8-sig: Notepad reads the accents correctly
    salva_json(cartella_out / "rapporto.json", [
        {"metodo": n, "titolo": t, "introduzione": i, "risultati": r} for n, t, r, i in metodi])
    print(f"\nReport saved in:\n  {cartella_out / 'rapporto.txt'}\n  {cartella_out / 'rapporto.json'} (machine-readable version)")


if __name__ == "__main__":
    principale()
