# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# NeoTracker - Copyright (C) 2026 gli autori di NeoTracker.
# Software libero: puoi ridistribuirlo e/o modificarlo secondo i termini della GNU General Public License
# versione 3 o successiva. Nessuna garanzia, nemmeno di idoneità a uno scopo (vedi il file LICENSE).
# NON è un dispositivo medico e non fa diagnosi: vedi DISCLAIMER.md.
"""
==========================================================================================
 melanoma_batch.py  -  UNA FOTO IN INGRESSO, UN RAPPORTO CON TUTTI I METODI IN USCITA
==========================================================================================

COSA FA (in parole semplici)
----------------------------
Tu gli dai la foto di un neo. Lui, da solo, apre uno dopo l'altro i programmi che hai
installato con lo script "install_melanoma_repos.ps1", li fa guardare la foto, e alla fine
scrive un rapporto del tipo:

    Metodo 1 ha detto che ...
    Metodo 2 ha detto che ...
    Metodo 3 ...

I numeri dei metodi sono gli stessi dello script di installazione e della guida:

    Metodo 1 = App 1  (DeborahAdedigba / Melanoma-Detection_App)  - 5 modelli TensorFlow
    Metodo 2 = SkinSense (servizio ONLINE: la foto viene inviata a un server esterno!)
    Metodo 3 = Melanoma-Detector (VukIG)   - e' solo un prototipo senza modello: nessuna analisi
    Metodo 4 = vatsal30 / Melanoma-Detection - PyTorch, serve aver addestrato i pesi
    Metodo 5 = ukalwa (app Android)        - si usa sul telefono, non puo' girare dal PC

COME SI USA (il modo piu' semplice)
-----------------------------------
 1. Apri questo file con Spyder.
 2. Premi il tasto PLAY (la freccia verde "Esegui file").
 3. Si apre una finestra: scegli la foto del neo.
 4. Aspetta (anche 5-15 minuti la prima volta: i modelli sono grossi).
 5. Il rapporto compare nella console e viene salvato in una cartella accanto alla foto.

Se preferisci, puoi scrivere il percorso della foto qui sotto, nella riga "FOTO = ...",
cosi' non ti chiede nulla.

Da terminale e' uguale:
    python melanoma_batch.py --foto "C:\\percorso\\nevo.jpg"

IMPORTANTE: QUESTO NON E' UNO STRUMENTO MEDICO
----------------------------------------------
I programmi usati sono prototipi di ricerca/studio, non validati clinicamente. Possono
sbagliare in entrambe le direzioni: dare un allarme falso OPPURE dare un "tutto bene" falso.
Il rapporto serve solo come appunto da portare alla visita dermatologica, mai al posto
della visita.

COME E' FATTO (per chi e' curioso)
----------------------------------
I programmi usano librerie diverse che non vanno d'accordo nello stesso ambiente Python
(TensorFlow da una parte, PyTorch dall'altra). Per questo questo file fa due mestieri:
  - "DIRETTORE D'ORCHESTRA": sceglie la foto, avvia gli "operai" uno alla volta, raccoglie
    le risposte e scrive il rapporto. Usa solo cose gia' incluse in Python.
  - "OPERAI" (worker): lo STESSO file, rilanciato dentro l'ambiente .venv giusto di ciascun
    progetto (con l'opzione nascosta --worker). Ogni operaio carica i suoi modelli, guarda la
    foto e scrive la risposta in un piccolo file JSON.
Se un operaio si rompe, gli altri vanno avanti: il rapporto dira' semplicemente quale ha
fallito e perche'.
"""

# ==========================================================================================
# 1. IMPOSTAZIONI - sono le uniche righe che di solito serve toccare
# ==========================================================================================

# Percorso della foto da analizzare.
# - Lascialo vuoto ("") e ti si apre una finestra per scegliere la foto.
# - Oppure scrivi il percorso. La "r" prima delle virgolette serve a Windows: non toglierla.
#   Esempio:  FOTO = r"C:\Users\TUONOME\Desktop\nevo.jpg"
FOTO = r""

# Che tipo di foto e'?
#   "normale"      = foto fatta con il telefono/macchina fotografica (il caso piu' comune)
#   "dermoscopica" = foto fatta con un dermatoscopio (lente speciale con luce polarizzata)
#   "entrambe"     = prova sia i modelli per foto normali sia quelli per dermoscopia
# I modelli sono addestrati su un tipo o sull'altro: usare il tipo sbagliato da' risposte
# poco sensate. Nel dubbio lascia "normale".
TIPO_FOTO = "normale"

# Dove sono state installate le cartelle dei progetti (lo ha deciso lo script di installazione).
# Path.home() e' la tua cartella personale, es. C:\Users\TUONOME
from pathlib import Path
CARTELLA_REPO = Path.home() / "melanoma-repos"

# Interruttori: metti False per saltare un metodo.
USA_APP1 = True          # Metodo 1 - App 1 (lavora tutto sul tuo PC)
USA_SKINSENSE = True     # Metodo 2 - SkinSense. ATTENZIONE: INVIA LA FOTO A UN SERVER ESTERNO
                         #            (Hugging Face). Prima dell'invio il programma toglie i
                         #            metadati della foto (posizione GPS, modello del telefono, data).
                         #            Se non vuoi che la foto esca dal tuo PC, metti False.
USA_VATSAL = True        # Metodo 4 - vatsal30 (parte solo se esistono i file model_fold_*.bin)

# Indirizzo del servizio online usato da SkinSense (lo stesso che usa il suo sito web).
URL_SKINSENSE = "https://souresh-skin-lesion-detection.hf.space/analyze"

# Quanto aspettare al massimo ciascun metodo, in secondi (poi lo salta e va avanti).
TIMEOUT_APP1 = 40 * 60
TIMEOUT_SKINSENSE = 6 * 60
TIMEOUT_VATSAL = 20 * 60

# ==========================================================================================
# 2. STRUMENTI DI BASE (solo librerie incluse in Python: nessuna installazione necessaria)
# ==========================================================================================

import argparse          # legge le opzioni scritte da terminale (--foto, --worker, ...)
import json              # legge/scrive file JSON (un formato di testo per scambiarsi dati)
import os                # variabili d'ambiente e percorsi
import subprocess        # permette di avviare un altro programma Python (gli "operai")
import sys               # informazioni sul Python in uso
import textwrap          # manda a capo il testo lungo in modo ordinato
import time              # misura i tempi e prende data/ora
import traceback         # descrizione dettagliata degli errori

# Nomi delle cartelle create dallo script di installazione.
CARTELLA_APP1 = "DeborahAdedigba_Melanoma-Detection_App"
CARTELLA_VATSAL = "vatsal30_Melanoma-Detection"

# Estensioni di immagine accettate.
ESTENSIONI_OK = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")

# Le 6 classi dei modelli "foto di pelle" di App 1 (dataset PAD-UFES-20) con il loro
# significato e un giudizio "grossolano": "attenzione" = lesione maligna o pre-maligna,
# "benigno" = lesione benigna. E' una classificazione semplificata, solo per il riepilogo.
CLASSI_APP1 = {
    "ACK": ("cheratosi attinica, lesione pre-cancerosa", "attenzione"),
    "BCC": ("carcinoma basocellulare, tumore della pelle", "attenzione"),
    "MEL": ("melanoma", "attenzione"),
    "NEV": ("nevo, cioe' neo benigno", "benigno"),
    "SCC": ("carcinoma squamocellulare, tumore della pelle", "attenzione"),
    "SEK": ("cheratosi seborroica, benigna", "benigno"),
}
ORDINE_CLASSI_APP1 = ["ACK", "BCC", "MEL", "NEV", "SCC", "SEK"]  # ordine usato dai modelli


def nuovo_risultato(nome, stato, etichetta=None, valore=None, prob_mel=None,
                    verdetto=None, nota="", gruppo="", dettaglio=None, secondi=None):
    """
    Crea la "scheda" di risposta di UN modello. Tutti i metodi usano la stessa scheda,
    cosi' il direttore d'orchestra sa sempre dove trovare le cose.

    nome       : nome del modello (es. "VGG16")
    stato      : "ok" (ha risposto) | "errore" (si e' rotto) | "non_disponibile" (mancano
                 file/ambiente) | "non_eseguibile" (non si puo' fare da PC, per natura)
    etichetta  : la risposta in parole (es. "NEV (nevo, cioe' neo benigno)")
    valore     : sicurezza del modello nella sua risposta, da 0 a 1 (None se non esiste)
    prob_mel   : probabilita' di melanoma da 0 a 1, se il modello la fornisce
    verdetto   : "attenzione" | "benigno" | "incerto" | None  (serve per il riepilogo)
    nota       : spiegazione libera, soprattutto in caso di errore
    gruppo     : sottogruppo dentro il metodo (es. "foto di pelle" / "dermoscopia")
    dettaglio  : dizionario con altri numeri (probabilita' per classe ecc.)
    secondi    : tempo impiegato
    """
    return {
        "nome": nome, "stato": stato, "etichetta": etichetta, "valore": valore,
        "prob_mel": prob_mel, "verdetto": verdetto, "nota": nota, "gruppo": gruppo,
        "dettaglio": dettaglio or {}, "secondi": secondi,
    }


def salva_json(percorso, dati):
    """Scrive 'dati' in un file JSON (testo leggibile) con le lettere accentate corrette."""
    with open(percorso, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=2)


def e_segnaposto_lfs(percorso):
    """
    I modelli di App 1 sono salvati con "Git LFS": finche' non lanci 'git lfs pull' al loro
    posto c'e' un finto file di poche righe (un "segnaposto") invece del modello vero.
    Questa funzione dice se il file e' ancora un segnaposto.
    """
    try:
        if Path(percorso).stat().st_size > 2048:        # un modello vero pesa decine di MB
            return False
        with open(percorso, "rb") as f:
            return f.read(40).startswith(b"version https://git-lfs")
    except OSError:
        return False


def apri_immagine_rgb(percorso):
    """
    Apre la foto e la restituisce in formato RGB, ruotandola come l'ha scattata il telefono
    (i telefoni salvano la foto 'storta' + una nota 'ruotala di 90 gradi': qui la applichiamo).
    Richiede Pillow, che e' presente in tutti gli ambienti dei progetti.
    """
    from PIL import Image, ImageOps
    img = Image.open(percorso)
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


# ==========================================================================================
# 3. GLI "OPERAI": ognuno lavora per un metodo e gira DENTRO l'ambiente .venv di quel progetto
# ==========================================================================================

# ----------------------------- 3a. METODO 1: App 1 (TensorFlow) ---------------------------

def lavora_app1(foto, tipo, repo):
    """
    Esegue i 10 modelli di App 1 (5 per foto di pelle + 5 per dermoscopia), uno alla volta.
    Replica fedelmente il codice dell'app originale (Melanoma_Detection.py): stesse
    architetture, stessi file di pesi, stesse dimensioni e preprocessing.
    Restituisce la lista delle "schede" di risposta.
    """
    import gc
    import numpy as np
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")      # meno messaggi tecnici di TensorFlow
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

    # ---- Le "ricette" (architetture) dei modelli, copiate dall'app originale ----------------
    # Ogni modello riceve 6 "canali": 3 sono la foto (rosso, verde, blu) e 3 sono una "mappa di
    # salienza" (una sorta di mappa di attenzione). L'app originale, per la mappa, usa tutti zeri.

    def costruisci_cnn(forma=(224, 224, 6), classi=6):
        """Rete 'fatta in casa' con 5 blocchi di convoluzioni, applicata a foto e mappa."""
        ingresso = Input(forma)
        parte_foto = ingresso[:, :, :, :3]          # i primi 3 canali = la foto
        parte_mappa = ingresso[:, :, :, 3:]         # gli ultimi 3 canali = la mappa di salienza

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
        Modello a 'trasferimento': prende una rete famosa (VGG16, ResNet50, EfficientNetB4,
        InceptionResNetV2), la applica alla foto e alla mappa, unisce i due risultati e li
        passa a due strati finali che scelgono tra le 6 classi.
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
        Legge la foto, la porta a lato x lato pixel (come fa Keras: metodo 'nearest'),
        applica il preprocessing del modello e, se il modello vuole 6 canali, aggiunge
        i 3 canali di mappa a zero (stesso comportamento dell'app originale).
        """
        from PIL import Image
        img = apri_immagine_rgb(foto).resize((lato, lato), Image.NEAREST)
        a = np.expand_dims(np.asarray(img, dtype="float32"), axis=0)      # forma (1, lato, lato, 3)
        if funzione_prep is not None:
            a = funzione_prep(a.copy())
        if canali == 6:
            a = np.concatenate((a, np.zeros_like(a)), axis=-1)
        return a

    def etichetta_classi(p):
        """Da 6 probabilita' a: etichetta leggibile, verdetto, sicurezza, prob. di melanoma."""
        i = int(np.argmax(p))
        codice = ORDINE_CLASSI_APP1[i]
        descr, verdetto = CLASSI_APP1[codice]
        return (f"{codice} ({descr})", verdetto, float(p[i]),
                float(p[ORDINE_CLASSI_APP1.index("MEL")]),
                {c: round(float(p[k]), 4) for k, c in enumerate(ORDINE_CLASSI_APP1)})

    risultati = []

    def tutti_segnaposto(nomi_file):
        """True se TUTTI i file indicati esistono ma sono ancora segnaposto Git LFS."""
        percorsi = [cartella / n for n in nomi_file]
        return all(p.exists() and e_segnaposto_lfs(p) for p in percorsi)

    messaggio_lfs = (f"i modelli di App 1 non sono stati scaricati: sono ancora dei segnaposto Git LFS. "
                     f"Apri PowerShell nella cartella {cartella} e lancia 'git lfs pull', poi riprova.")

    # ---- Gruppo "foto di pelle": ricetta + file dei pesi ------------------------------------
    gruppo_pelle = [
        # nome,               ricetta,                                              file pesi,                                 lato, preprocessing
        ("CNN",               lambda: costruisci_cnn(),                              "CNN_skin_classifier_weights.weights.h5",  224, None),
        ("VGG16",             lambda: costruisci_con_base(VGG16, 224),               "best_VGG16_weights.weights.h5",           224, prep_vgg16),
        ("ResNet50",          lambda: costruisci_con_base(ResNet50, 224),            "best_ResNet50_weights.weights.h5",        224, prep_resnet50),
        ("EfficientNetB4",    lambda: costruisci_con_base(EfficientNetB4, 380),      "best_EfficientNetB4_weights.weights.h5",  380, prep_efficientnet),
        ("InceptionResNetV2", lambda: costruisci_con_base(InceptionResNetV2, 299),   "best_InceptionResNetV2_weights.weights.h5", 299, prep_inception),
    ]
    # ---- Gruppo "dermoscopia": modelli gia' completi in un unico file .keras ----------------
    gruppo_derm = [
        ("CNN",               "DM_melanoma_cnn_with_saliency.keras",          224, None),
        ("VGG16",             "DM_vgg16_model_with_saliency.keras",           224, prep_vgg16),
        ("ResNet50",          "DM_best_ResNet50_model.keras",                 224, prep_resnet50),
        ("EfficientNetB4",    "DM_efficientnetb4_model_with_saliency.keras",  380, prep_efficientnet),
        ("InceptionResNetV2", "DM_InceptionResNetV2_model.keras",             299, prep_inception),
    ]

    def libera_memoria():
        """Scarica il modello dalla memoria prima del prossimo (alcuni pesano parecchio)."""
        tf.keras.backend.clear_session()
        gc.collect()

    # ---------------------------- foto di pelle -----------------------------------------------
    if tipo in ("normale", "entrambe") and tutti_segnaposto([g[2] for g in gruppo_pelle]):
        # Caso tipico di chi non ha ancora fatto 'git lfs pull': un solo messaggio chiaro, non cinque.
        risultati.append(nuovo_risultato("5 modelli per foto di pelle", "non_disponibile",
                                         gruppo="foto di pelle", nota=messaggio_lfs))
    elif tipo in ("normale", "entrambe"):
        for nome, ricetta, file_pesi, lato, prep in gruppo_pelle:
            t0 = time.time()
            percorso = cartella / file_pesi
            try:
                if not percorso.exists():
                    raise FileNotFoundError(f"file {file_pesi} non trovato in {cartella}")
                if e_segnaposto_lfs(percorso):
                    risultati.append(nuovo_risultato(
                        nome, "non_disponibile", gruppo="foto di pelle",
                        nota=f"{file_pesi} e' ancora un segnaposto Git LFS: apri PowerShell nella cartella "
                             f"{cartella} e lancia 'git lfs pull'."))
                    continue
                modello = ricetta()
                modello.load_weights(str(percorso))                       # carica i pesi addestrati
                x = prepara_input(lato, prep, 6)
                p = np.asarray(modello.predict(x, verbose=0))[0]          # le 6 probabilita'
                etichetta, verdetto, sicurezza, p_mel, tutte = etichetta_classi(p)
                risultati.append(nuovo_risultato(
                    nome, "ok", etichetta, sicurezza, p_mel, verdetto, gruppo="foto di pelle",
                    dettaglio={"probabilita_per_classe": tutte}, secondi=round(time.time() - t0, 1)))
            except Exception as e:
                traceback.print_exc()
                risultati.append(nuovo_risultato(nome, "errore", gruppo="foto di pelle",
                                                 nota=f"{type(e).__name__}: {str(e)[:300]}"))
            finally:
                libera_memoria()

    # ---------------------------- dermoscopia -------------------------------------------------
    if tipo in ("dermoscopica", "entrambe") and tutti_segnaposto([g[1] for g in gruppo_derm]):
        risultati.append(nuovo_risultato("5 modelli per dermoscopia", "non_disponibile",
                                         gruppo="dermoscopia", nota=messaggio_lfs))
    elif tipo in ("dermoscopica", "entrambe"):
        for nome, file_modello, lato_app, prep in gruppo_derm:
            t0 = time.time()
            percorso = cartella / file_modello
            try:
                if not percorso.exists():
                    raise FileNotFoundError(f"file {file_modello} non trovato in {cartella}")
                if e_segnaposto_lfs(percorso):
                    risultati.append(nuovo_risultato(
                        nome, "non_disponibile", gruppo="dermoscopia",
                        nota=f"{file_modello} e' ancora un segnaposto Git LFS: lancia 'git lfs pull' "
                             f"nella cartella {cartella}."))
                    continue
                # compile=False: ci serve solo per fare previsioni, non per riaddestrarlo.
                # NB: non disattivo mai la 'safe mode' di Keras: un file modello scaricato da
                # internet non va fatto eseguire alla cieca.
                modello = load_model(str(percorso), compile=False)
                forma = modello.input_shape
                if isinstance(forma, list):
                    raise ValueError("il modello ha piu' ingressi: non gestito")
                canali = forma[-1]
                lato = forma[1] if (forma[1] is not None and forma[1] == forma[2]) else lato_app
                if canali not in (3, 6):
                    raise ValueError(f"numero di canali inatteso: {canali}")
                x = prepara_input(lato, prep, canali)
                p = np.asarray(modello.predict(x, verbose=0))[0]
                n = len(p)
                # L'app originale legge SEMPRE l'uscita come 6 classi di pelle (un suo errore di
                # programmazione: 'if tab1' e' sempre vero). Qui invece guardo quante uscite ha
                # il modello e le interpreto di conseguenza.
                if n == 1:
                    pm = float(p[0])
                    etich = "maligno" if pm > 0.5 else "benigno"
                    risultati.append(nuovo_risultato(
                        nome, "ok", etich, max(pm, 1 - pm), None,
                        "attenzione" if pm > 0.5 else "benigno", gruppo="dermoscopia",
                        nota=f"probabilita' di malignita' stimata dal modello: {pm:.0%}",
                        dettaglio={"prob_maligno": round(pm, 4)}, secondi=round(time.time() - t0, 1)))
                elif n == 2:
                    pm = float(p[1])
                    etich = "maligno" if pm > 0.5 else "benigno"
                    risultati.append(nuovo_risultato(
                        nome, "ok", etich, max(pm, 1 - pm), None,
                        "attenzione" if pm > 0.5 else "benigno", gruppo="dermoscopia",
                        nota="assumo che le 2 uscite siano [benigno, maligno]; ordine non verificabile",
                        dettaglio={"prob_benigno": round(float(p[0]), 4), "prob_maligno": round(pm, 4)},
                        secondi=round(time.time() - t0, 1)))
                elif n == 6:
                    etichetta, verdetto, sicurezza, p_mel, tutte = etichetta_classi(p)
                    risultati.append(nuovo_risultato(
                        nome, "ok", etichetta, sicurezza, p_mel, verdetto, gruppo="dermoscopia",
                        nota="uscita letta come le 6 classi di pelle (non verificabile)",
                        dettaglio={"probabilita_per_classe": tutte}, secondi=round(time.time() - t0, 1)))
                else:
                    risultati.append(nuovo_risultato(
                        nome, "ok", f"classe numero {int(np.argmax(p))}", float(np.max(p)), None, "incerto",
                        gruppo="dermoscopia", nota=f"il modello ha {n} uscite: significato sconosciuto",
                        secondi=round(time.time() - t0, 1)))
            except Exception as e:
                traceback.print_exc()
                risultati.append(nuovo_risultato(nome, "errore", gruppo="dermoscopia",
                                                 nota=f"{type(e).__name__}: {str(e)[:300]}"))
            finally:
                libera_memoria()

    return risultati


# ----------------------------- 3b. METODO 2: SkinSense (online) ---------------------------

def lavora_skinsense(foto, url, cartella_out):
    """
    Invia la foto al servizio online usato dal sito di SkinSense e legge la risposta.
    PRIMA dell'invio ricodifica la foto da zero, in modo da buttare via tutti i metadati
    (posizione GPS, modello del telefono, data e ora): partono solo i pixel.
    """
    import base64
    import urllib.request
    import urllib.error
    import uuid
    import io

    t0 = time.time()
    # Difesa: l'indirizzo deve essere https (niente "file:" o "ftp:", che leggerebbero file del tuo PC).
    if not str(url).lower().startswith("https://"):
        return [nuovo_risultato("SkinSense", "errore", nota="indirizzo del servizio non ammesso (serve https)")]
    # ---- 1. Pulizia dei metadati ------------------------------------------------------------
    nota_pulizia = ""
    try:
        img = apri_immagine_rgb(foto)
        # Riduco le foto enormi (i telefoni fanno 12 megapixel): il modello online le riduce
        # comunque e cosi' l'invio e' molto piu' veloce.
        img.thumbnail((1600, 1600))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=92)      # senza 'exif=': i metadati non vengono scritti
        contenuto = buffer.getvalue()
    except Exception as e:
        # Se Pillow non riesce, NON invio l'originale (potrebbe contenere il GPS): mi fermo.
        return [nuovo_risultato("SkinSense", "errore",
                                nota=f"non riesco a preparare la foto in modo sicuro: {e}")]

    # ---- 2. Costruzione della richiesta HTTP 'multipart' (il modo standard per inviare file) -
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

    # ---- 3. Invio, con un secondo tentativo (il servizio gratuito puo' essere 'addormentato') -
    risposta = None
    ultimo_errore = ""
    for tentativo in (1, 2):
        try:
            # Controllo di sicurezza (bandit B310): https controllato sopra.
            with urllib.request.urlopen(richiesta, timeout=150) as r:   # nosec B310
                risposta = json.loads(r.read(5 * 1024 * 1024).decode("utf-8", errors="replace"))   # al massimo 5 MB di risposta
            break
        except urllib.error.HTTPError as e:
            ultimo_errore = f"il server ha risposto con errore HTTP {e.code}"
        except Exception as e:
            ultimo_errore = f"{type(e).__name__}: {e}"
        if tentativo == 1:
            print(f"SkinSense: primo tentativo fallito ({ultimo_errore}); riprovo tra 30 secondi...")
            time.sleep(30)
    if risposta is None:
        return [nuovo_risultato("SkinSense", "errore", nota=f"servizio non raggiungibile: {ultimo_errore}")]

    # ---- 4. Lettura della risposta -----------------------------------------------------------
    nome_lesione = str(risposta.get("full_name") or "").strip()
    confidenza = risposta.get("confidence")
    try:
        c = float(confidenza)
        c = c / 100.0 if c > 1 else c            # il servizio la da' in percentuale (es. 87.3)
    except (TypeError, ValueError):
        c = None

    # Giudizio grossolano dal nome della lesione, confrontando parole chiave.
    n = nome_lesione.lower()
    if "melanoma" in n or "basal" in n or "actinic" in n or "squamous" in n or "carcinoma" in n:
        verdetto = "attenzione"
    elif any(k in n for k in ("nevi", "nevus", "benign", "dermatofibroma", "vascular")):
        verdetto = "benigno"
    else:
        verdetto = "incerto"

    # La risposta puo' contenere un'immagine (probabilmente una mappa di calore): se e' un'immagine
    # vera, la salvo come file a parte; non la stampo nel rapporto.
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
    nota = f"livello di rischio dichiarato dal servizio: {rischio}" if rischio else ""
    if not nome_lesione:
        return [nuovo_risultato("SkinSense", "errore", nota="risposta senza nome della lesione: "
                                f"{json.dumps(risposta, ensure_ascii=False)[:300]}")]
    return [nuovo_risultato("SkinSense", "ok", nome_lesione, c, None, verdetto, nota=nota,
                            dettaglio=dettaglio, secondi=round(time.time() - t0, 1))]


# ----------------------------- 3c. METODO 4: vatsal30 (PyTorch) ---------------------------

def lavora_vatsal(foto, repo):
    """
    Esegue il 'comitato' di modelli SE-ResNeXt50 di vatsal30 (fino a 5, uno per 'fold') e
    ne fa la media. Funziona SOLO se esistono i file model_fold_0.bin ... model_fold_4.bin
    nella cartella 'model': il repository NON li include, vanno addestrati col dataset
    SIIM-ISIC di Kaggle (molti GB).
    """
    t0 = time.time()
    cartella = Path(repo) / CARTELLA_VATSAL
    pesi = sorted((cartella / "model").glob("model_fold_*.bin"))
    if not pesi:
        return [nuovo_risultato(
            "SE-ResNeXt50 x5", "non_disponibile",
            nota=f"mancano i pesi addestrati: nella cartella {cartella / 'model'} non ci sono i file "
                 f"model_fold_0.bin ... model_fold_4.bin. Il repository non li contiene: vanno prodotti "
                 f"con train.py sul dataset SIIM-ISIC.")]

    import numpy as np
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    import pretrainedmodels

    class SEResNext50(nn.Module):
        """Stessa rete dell'originale (prediction.py), senza la parte che serve solo all'addestramento."""
        def __init__(self):
            super().__init__()
            self.base_model = pretrainedmodels.__dict__["se_resnext50_32x4d"](pretrained=None)
            self.l0 = nn.Linear(2048, 1)          # un solo numero in uscita: >0 = melanoma, <=0 = no

        def forward(self, immagine):
            x = self.base_model.features(immagine)
            x = F.adaptive_avg_pool2d(x, 1).reshape(immagine.shape[0], -1)
            return self.l0(x)

    # Preparazione della foto: la rete e' stata addestrata su immagini 224x224 (vedi README del
    # progetto), normalizzate con le medie/deviazioni standard di ImageNet.
    from PIL import Image
    img = apri_immagine_rgb(foto).resize((224, 224), Image.BILINEAR)
    a = np.asarray(img, dtype="float32") / 255.0
    media = np.array([0.485, 0.456, 0.406], dtype="float32")
    dev = np.array([0.229, 0.224, 0.225], dtype="float32")
    a = ((a - media) / dev).transpose(2, 0, 1)            # da (alto, largo, colori) a (colori, alto, largo)
    x = torch.from_numpy(a).unsqueeze(0)

    punteggi = []
    for percorso in pesi:
        modello = SEResNext50()
        # weights_only=True: il file può contenere solo numeri, mai codice eseguibile (un file di pesi manomesso
        # non può far girare nulla). Serve PyTorch 1.13 o più recente: con uno più vecchio ci fermiamo
        # invece di caricare il file "alla vecchia maniera", che sarebbe insicuro.
        try:
            stato = torch.load(str(percorso), map_location="cpu", weights_only=True)
        except TypeError:
            raise RuntimeError("PyTorch troppo vecchio: aggiornalo (pip install -U torch) per caricare i pesi in modo sicuro")
        modello.load_state_dict(stato)
        modello.eval()
        with torch.no_grad():
            punteggi.append(float(modello(x).reshape(-1)[0]))
    media_punteggi = sum(punteggi) / len(punteggi)
    prob = 1.0 / (1.0 + float(np.exp(-media_punteggi)))     # sigmoide: da punteggio a probabilita'
    melanoma = media_punteggi > 0                            # stessa soglia dell'app originale
    return [nuovo_risultato(
        f"SE-ResNeXt50 x{len(pesi)}", "ok",
        "melanoma rilevato" if melanoma else "melanoma non rilevato",
        prob if melanoma else 1 - prob, prob, "attenzione" if melanoma else "benigno",
        nota=f"media di {len(pesi)} modelli; punteggio medio {media_punteggi:+.2f} (soglia 0)",
        dettaglio={"punteggi_per_fold": [round(s, 3) for s in punteggi]},
        secondi=round(time.time() - t0, 1))]


def esegui_worker(nome, args):
    """Punto d'ingresso degli 'operai': fa il lavoro del metodo richiesto e scrive il JSON."""
    try:
        # Prima di tutto controllo che la foto si apra davvero: se e' rovinata lo dico UNA volta sola
        # invece di far fallire ogni modello con lo stesso errore.
        try:
            apri_immagine_rgb(args.foto).close()
        except Exception as e:
            salva_json(args.out, [nuovo_risultato(nome, "errore",
                                                  nota=f"la foto non si apre come immagine ({type(e).__name__}): {str(e)[:200]}")])
            return
        if nome == "app1":
            risultati = lavora_app1(args.foto, args.tipo, args.repo)
        elif nome == "skinsense":
            risultati = lavora_skinsense(args.foto, args.url, Path(args.out).parent)
        elif nome == "vatsal":
            risultati = lavora_vatsal(args.foto, args.repo)
        else:
            raise ValueError(f"operaio sconosciuto: {nome}")
    except Exception as e:
        traceback.print_exc()
        risultati = [nuovo_risultato(nome, "errore", nota=f"{type(e).__name__}: {str(e)[:300]}")]
    salva_json(args.out, risultati)


# ==========================================================================================
# 4. IL "DIRETTORE D'ORCHESTRA": sceglie la foto, avvia gli operai, scrive il rapporto
# ==========================================================================================

def trova_python_venv(cartella):
    """Cerca il Python dell'ambiente .venv di un progetto (Windows: Scripts\\python.exe)."""
    for relativo in ("Scripts/python.exe", "bin/python"):
        candidato = Path(cartella) / ".venv" / relativo
        if candidato.exists():
            return candidato
    return None


def scegli_foto(args):
    """Decide quale foto usare: da terminale, dall'impostazione FOTO, oppure con una finestra."""
    percorso = args.foto or FOTO
    if not percorso:
        try:
            import tkinter as tk
            from tkinter import filedialog
            radice = tk.Tk()
            radice.withdraw()                       # nascondo la finestrella vuota di sfondo
            radice.attributes("-topmost", True)     # faccio comparire il selettore in primo piano
            percorso = filedialog.askopenfilename(
                title="Scegli la foto del neo da analizzare",
                filetypes=[("Immagini", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff"), ("Tutti i file", "*.*")])
            radice.destroy()
        except Exception:
            percorso = input("Scrivi il percorso completo della foto e premi Invio: ").strip().strip('"')
    return Path(percorso) if percorso else None


def lancia_operaio(nome, python_exe, argomenti, timeout, cartella_out):
    """
    Avvia l'operaio 'nome' in un processo separato, con il Python indicato, e ne raccoglie
    la risposta. Qualunque cosa vada storta diventa una 'scheda' di errore invece di un crash.
    Tutto quello che l'operaio scrive a schermo finisce nel file log_<nome>.txt.
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
        return [nuovo_risultato(nome, "errore", nota=f"interrotto dopo {timeout // 60} minuti (tempo massimo)")]
    except Exception as e:
        return [nuovo_risultato(nome, "errore", nota=f"impossibile avviare: {e}")]
    if file_json.exists():
        try:
            dati = json.loads(file_json.read_text(encoding="utf-8"))
            file_json.unlink()                                  # il file temporaneo non serve piu'
            return dati
        except Exception as e:
            return [nuovo_risultato(nome, "errore", nota=f"risposta illeggibile: {e}")]
    # Nessuna risposta: l'operaio e' morto prima di scrivere. Prendo le ultime righe del log.
    try:
        ultime = [r for r in file_log.read_text(encoding="utf-8", errors="replace").splitlines() if r.strip()][-6:]
    except OSError:
        ultime = []
    return [nuovo_risultato(nome, "errore",
                            nota="il programma si e' chiuso senza risposta. Ultime righe: " + " | ".join(ultime)[:500])]


def percentuale(x):
    """0.617 -> '62%'; None -> '-'."""
    return "-" if x is None else f"{x:.0%}"


def a_capo(testo, rientro="      "):
    """
    Manda a capo un testo lungo con un rientro uniforme (per il rapporto).
    Se il testo contiene gia' degli 'a capo' voluti (\\n), li rispetta.
    """
    paragrafi = testo.split("\n")
    return "\n".join(textwrap.fill(p, width=96, initial_indent=rientro, subsequent_indent=rientro)
                     if p.strip() else "" for p in paragrafi)


def frase_conteggio(risultati):
    """Riassume 'quanti modelli hanno detto cosa', es. '4 su 5: NEV (...); 1 su 5: MEL (...)'."""
    ok = [r for r in risultati if r["stato"] == "ok"]
    if not ok:
        return ""
    conteggi = {}
    for r in ok:
        conteggi[r["etichetta"]] = conteggi.get(r["etichetta"], 0) + 1
    parti = [f"{n} su {len(ok)}: {et}" for et, n in sorted(conteggi.items(), key=lambda kv: -kv[1])]
    return "; ".join(parti)


def verdetto_metodo(risultati):
    """
    Un unico giudizio per tutto il metodo, per il riepilogo finale:
    'attenzione' | 'benigno' | 'discordante' (i suoi modelli non sono d'accordo) | None (nessun risultato).
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
    """Costruisce le righe di testo del rapporto per UN metodo."""
    righe = ["", "-" * 98, f"METODO {numero} - {titolo}", "-" * 98]
    if introduzione:
        righe.append(a_capo(introduzione, "  "))
    ok = [r for r in risultati if r["stato"] == "ok"]
    # ---- frase "Il metodo N ha detto che ..." ----
    if ok:
        righe.append("")
        for g in dict.fromkeys(r["gruppo"] for r in ok):          # gruppi nell'ordine in cui compaiono
            sotto = [r for r in ok if r["gruppo"] == g]
            righe.append(a_capo(f"IL METODO {numero} HA DETTO CHE" + (f" [{g}]" if g else "")
                                + " -> " + frase_conteggio(sotto), "  "))
        righe.append("")
    # ---- una riga per modello ----
    n_gruppi = len({r["gruppo"] for r in risultati if r["gruppo"]})      # il nome del gruppo si ripete solo se ce n'e' piu' di uno
    for r in risultati:
        pre = f"  [{r['gruppo']}] " if (r["gruppo"] and n_gruppi > 1) else "  "
        if r["stato"] == "ok":
            extra = f"  [prob. melanoma: {percentuale(r['prob_mel'])}]" if r["prob_mel"] is not None else ""
            riga = f"{pre}- {r['nome']:<18} -> {r['etichetta']}  (sicurezza {percentuale(r['valore'])}){extra}"
            righe.append(textwrap.fill(riga, width=98, subsequent_indent="        "))
            if r["nota"]:
                righe.append(a_capo(r["nota"], "        "))
        elif r["stato"] == "non_disponibile":
            righe.append(f"{pre}- {r['nome']:<18} NON DISPONIBILE")
            righe.append(a_capo(r["nota"], "        "))
        elif r["stato"] == "non_eseguibile":
            righe.append(a_capo(r["nota"], "  "))
        else:
            righe.append(f"{pre}- {r['nome']:<18} ERRORE")
            righe.append(a_capo(r["nota"], "        "))
    return righe


def costruisci_rapporto(foto, tipo, metodi, durata):
    """Assembla il testo completo del rapporto (intestazione, 5 metodi, riepilogo, avvertenze)."""
    righe = ["=" * 98,
             " RAPPORTO AUTOMATICO - CONFRONTO DEI METODI SULLA STESSA FOTO",
             f" Foto: {foto.name}    Tipo dichiarato: {tipo}",
             f" Data: {time.strftime('%d/%m/%Y %H:%M')}    Durata: {durata // 60:.0f} min {durata % 60:.0f} s",
             "=" * 98]
    for numero, titolo, risultati, intro in metodi:
        righe += righe_metodo(numero, titolo, risultati, intro)

    # ------------------------------ riepilogo finale ----------------------------------------
    righe += ["", "=" * 98, " RIEPILOGO", "=" * 98]
    giudizi = {}
    for numero, titolo, risultati, intro in metodi:
        giudizi[numero] = verdetto_metodo(risultati)
    con_risultato = [n for n, g in giudizi.items() if g is not None]
    attenzione = [n for n, g in giudizi.items() if g == "attenzione"]
    benigni = [n for n, g in giudizi.items() if g == "benigno"]
    discordi = [n for n, g in giudizi.items() if g == "discordante"]
    senza = [n for n, g in giudizi.items() if g is None]
    elenco = lambda lista: ", ".join(f"metodo {n}" for n in lista) if lista else "nessuno"
    righe.append(f"  Metodi che hanno dato un risultato : {len(con_risultato)} su {len(metodi)}")
    righe.append(f"  Indicano lesione DA ATTENZIONARE   : {elenco(attenzione)}")
    righe.append(f"  Indicano lesione BENIGNA           : {elenco(benigni)}")
    righe.append(f"  Con modelli in disaccordo tra loro : {elenco(discordi)}")
    righe.append(f"  Nessun risultato (vedi sopra perche'): {elenco(senza)}")
    righe.append("")
    if not con_risultato:
        giudizio = "Nessun metodo ha prodotto un risultato: controlla i motivi indicati sopra."
    elif attenzione or discordi:
        giudizio = ("Almeno un metodo (o un suo modello) segnala una lesione da attenzionare. Non e' una "
                    "diagnosi e questi strumenti sbagliano spesso, ma e' un motivo in piu' per non rimandare "
                    "la visita dermatologica e per portare questo rapporto.")
    else:
        giudizio = ("Tutti i metodi che hanno risposto indicano una lesione benigna. Questo NON esclude un "
                    "melanoma: gli strumenti non sono validati clinicamente e sbagliano anche in questa "
                    "direzione. Se il neo e' asimmetrico, ha bordi irregolari, colori diversi, e' piu' grande "
                    "di 6 mm o e' cambiato nel tempo, la visita resta necessaria.")
    righe.append(a_capo(giudizio, "  "))
    righe += ["", "-" * 98, " AVVERTENZE", "-" * 98]
    for avv in (
        "Questo rapporto NON e' una diagnosi. I programmi usati sono prototipi di ricerca, non dispositivi medici.",
        "I metodi sono addestrati su fotografie diverse dalla tua: cambiare luce, distanza o fotocamera puo' cambiare la risposta.",
        "I modelli di App 1 qui ricevono una 'mappa di salienza' vuota (come fa l'app originale): e' una "
        "semplificazione che puo' peggiorarne l'affidabilita'.",
        "Se i metodi sono in disaccordo, e' normale: significa solo che nessuno di loro e' affidabile da solo.",
        "Porta alla visita la foto, questo rapporto e la data in cui hai notato il neo / eventuali cambiamenti.",
    ):
        righe.append(a_capo("* " + avv, "  "))
    return "\n".join(righe)


def principale():
    """Funzione principale: e' quella che parte quando premi PLAY."""
    # ---- Lettura delle opzioni (servono solo da terminale; in Spyder restano ai valori di default) ----
    parser = argparse.ArgumentParser(description="Analizza una foto con tutti i metodi installati.")
    parser.add_argument("--foto", default="", help="percorso della foto")
    parser.add_argument("--tipo", default=TIPO_FOTO, choices=["normale", "dermoscopica", "entrambe"])
    parser.add_argument("--repo", default=str(CARTELLA_REPO), help="cartella dove sono i progetti installati")
    parser.add_argument("--url", default=URL_SKINSENSE, help="indirizzo del servizio SkinSense")
    parser.add_argument("--senza-app1", action="store_true")
    parser.add_argument("--senza-skinsense", action="store_true")
    parser.add_argument("--senza-vatsal", action="store_true")
    parser.add_argument("--out-dir", default="", help="cartella dove salvare il rapporto (default: accanto alla foto)")
    parser.add_argument("--worker", default="", help=argparse.SUPPRESS)        # uso interno
    parser.add_argument("--out", default="", help=argparse.SUPPRESS)           # uso interno
    args, _ = parser.parse_known_args()      # 'known': ignora eventuali opzioni extra messe da Spyder

    # Se sono stato avviato come 'operaio', faccio il mio lavoro e basta.
    if args.worker:
        esegui_worker(args.worker, args)
        return

    # Rende leggibili anche le lettere accentate nelle console Windows (dove possibile).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    # ---- Scelta e controllo della foto ----
    foto = scegli_foto(args)
    if foto is None or not foto.exists():
        print("Nessuna foto valida selezionata (o file non trovato). Interrompo.")
        return
    if foto.suffix.lower() not in ESTENSIONI_OK:
        extra = " Le foto HEIC degli iPhone vanno prima convertite in JPG." if foto.suffix.lower() in (".heic", ".heif") else ""
        print(f"Formato '{foto.suffix}' non supportato (accettati: {', '.join(ESTENSIONI_OK)}).{extra}")
        return
    repo = Path(args.repo)
    if not repo.exists():
        print(f"Non trovo la cartella dei progetti: {repo}\nControlla CARTELLA_REPO in cima a questo file.")
        return
    foto = foto.resolve()

    # ---- Cartella dove salvare il rapporto: accanto alla foto, una per ogni analisi ----
    if args.out_dir:
        cartella_out = Path(args.out_dir)
    else:
        cartella_out = foto.parent / f"rapporto_melanoma_{foto.stem}_{time.strftime('%Y%m%d-%H%M%S')}"
    cartella_out.mkdir(parents=True, exist_ok=True)
    print(f"Foto: {foto}\nTipo: {args.tipo}\nIl rapporto sara' salvato in: {cartella_out}\n")

    t_inizio = time.time()
    python_app1 = trova_python_venv(repo / CARTELLA_APP1)
    python_vatsal = trova_python_venv(repo / CARTELLA_VATSAL)
    metodi = []          # lista di (numero, titolo, risultati, introduzione)

    # ---- METODO 1: App 1 ----
    titolo1 = "App 1 (DeborahAdedigba) - modelli TensorFlow"
    if USA_APP1 and not args.senza_app1:
        print("Metodo 1 (App 1): avvio... la prima volta puo' volerci parecchio, i modelli sono grandi.")
        py = python_app1 or Path(sys.executable)
        intro = "" if python_app1 else ("Attenzione: non ho trovato l'ambiente .venv di App 1, uso il Python corrente.")
        r1 = lancia_operaio("app1", py, ["--foto", str(foto), "--tipo", args.tipo, "--repo", str(repo)],
                            TIMEOUT_APP1, cartella_out)
        metodi.append((1, titolo1, r1, intro))
    else:
        metodi.append((1, titolo1, [nuovo_risultato("App 1", "non_eseguibile", nota="Metodo 1 disattivato dalle impostazioni.")], ""))

    # ---- METODO 2: SkinSense ----
    titolo2 = "SkinSense (servizio online)"
    if USA_SKINSENSE and not args.senza_skinsense:
        print("Metodo 2 (SkinSense): invio della foto (senza metadati) al servizio online...")
        py = python_app1 or Path(sys.executable)
        r2 = lancia_operaio("skinsense", py, ["--foto", str(foto), "--url", args.url], TIMEOUT_SKINSENSE, cartella_out)
        metodi.append((2, titolo2, r2, "Questo metodo prevede l'invio dei pixel della foto (non dei metadati) a un server esterno."))
    else:
        metodi.append((2, titolo2, [nuovo_risultato(
            "SkinSense", "non_eseguibile",
            nota="Metodo 2 non eseguito (disattivato nelle impostazioni): la foto non e' uscita dal PC.")], ""))

    # ---- METODO 3: Melanoma-Detector (nessuna analisi possibile) ----
    metodi.append((3, "Melanoma-Detector (VukIG)", [nuovo_risultato(
        "Melanoma-Detector", "non_eseguibile",
        nota="Il metodo 3 NON ha analizzato la foto: il progetto e' un prototipo senza modello. Il suo "
             "server si limita a ricevere l'immagine (nessuna rete neurale), quindi qualunque testo "
             "rassicurante mostri non deriva da un'analisi e non ha alcun valore.")], ""))

    # ---- METODO 4: vatsal30 ----
    titolo4 = "vatsal30 / Melanoma-Detection (PyTorch)"
    if USA_VATSAL and not args.senza_vatsal:
        print("Metodo 4 (vatsal30): avvio...")
        py = python_vatsal or Path(sys.executable)
        r4 = lancia_operaio("vatsal", py, ["--foto", str(foto), "--repo", str(repo)], TIMEOUT_VATSAL, cartella_out)
        metodi.append((4, titolo4, r4, ""))
    else:
        metodi.append((4, titolo4, [nuovo_risultato("vatsal30", "non_eseguibile", nota="Metodo 4 disattivato dalle impostazioni.")], ""))

    # ---- METODO 5: ukalwa (Android) ----
    metodi.append((5, "ukalwa / melanoma-detection (app Android)", [nuovo_risultato(
        "ukalwa", "non_eseguibile",
        nota="Il metodo 5 e' un'app Android: non puo' girare dal PC. Installa l'APK sul telefono, "
             "inquadra il neo e annota a mano il risultato qui sotto.\n"
             "Risultato dell'app sul telefono: ______________________________")], ""))

    # ---- Rapporto ----
    testo = costruisci_rapporto(foto, args.tipo, metodi, time.time() - t_inizio)
    print("\n" + testo)
    (cartella_out / "rapporto.txt").write_text(testo, encoding="utf-8-sig")      # utf-8-sig: Blocco Note legge bene gli accenti
    salva_json(cartella_out / "rapporto.json", [
        {"metodo": n, "titolo": t, "introduzione": i, "risultati": r} for n, t, r, i in metodi])
    print(f"\nRapporto salvato in:\n  {cartella_out / 'rapporto.txt'}\n  {cartella_out / 'rapporto.json'} (versione per computer)")


if __name__ == "__main__":
    principale()
