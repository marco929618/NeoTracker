# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# NeoTracker - Copyright (C) 2026 gli autori di NeoTracker.
# Software libero: puoi ridistribuirlo e/o modificarlo secondo i termini della GNU General Public License
# versione 3 o successiva. Nessuna garanzia, nemmeno di idoneità a uno scopo (vedi il file LICENSE).
# NON è un dispositivo medico e non fa diagnosi: vedi DISCLAIMER.md.
"""
Disegna l'icona "Analizza neo": lente d'ingrandimento su un neo, con scintilla di analisi automatica,
su fondo blu-petrolio. Produce un file .ico multi-risoluzione (16 ... 256 px) e un'anteprima PNG.

Uso:  python make_icon.py <cartella_di_uscita>
"""
import sys
import math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageChops

S = 2048            # tela di lavoro grande (poi ridotta: bordi lisci)
K = S / 1024.0      # fattore di scala: tutte le coordinate qui sotto sono pensate su 1024


def k(v):
    """Converte una misura pensata su 1024 px nella tela reale."""
    return v * K


def gradiente_lineare(size, c1, c2, angolo_gradi=45):
    """Immagine RGBA con sfumatura lineare da c1 a c2 lungo la direzione 'angolo'."""
    w, h = size
    a = math.radians(angolo_gradi)
    xs = np.linspace(-1, 1, w)[None, :]
    ys = np.linspace(-1, 1, h)[:, None]
    t = (xs * math.cos(a) + ys * math.sin(a))
    t = (t - t.min()) / (t.max() - t.min())
    c1 = np.array(c1, dtype=float); c2 = np.array(c2, dtype=float)
    arr = c1[None, None, :] * (1 - t[..., None]) + c2[None, None, :] * t[..., None]
    return Image.fromarray(arr.clip(0, 255).astype("uint8"), "RGBA")


def gradiente_radiale(size, centro, raggio, c_centro, c_bordo):
    """Immagine RGBA con sfumatura radiale (centro -> bordo)."""
    w, h = size
    ys, xs = np.mgrid[0:h, 0:w]
    d = np.hypot(xs - centro[0], ys - centro[1]) / raggio
    t = np.clip(d, 0, 1)[..., None]
    c1 = np.array(c_centro, dtype=float); c2 = np.array(c_bordo, dtype=float)
    arr = c1 * (1 - t) + c2 * t
    return Image.fromarray(arr.clip(0, 255).astype("uint8"), "RGBA")


def maschera(disegna, blur=0):
    """Crea una maschera L dove 'disegna(draw)' disegna in bianco."""
    m = Image.new("L", (S, S), 0)
    disegna(ImageDraw.Draw(m))
    if blur:
        m = m.filter(ImageFilter.GaussianBlur(blur))
    return m


def incolla(base, strato, mask):
    """Incolla 'strato' su 'base' usando 'mask' (mantiene la trasparenza di base)."""
    base.alpha_composite(Image.composite(strato, Image.new("RGBA", base.size, (0, 0, 0, 0)), mask))


def ombra(base, mask, spostamento=(0, 18), sfocatura=26, opacita=0.38, colore=(4, 18, 34)):
    """Ombra morbida sotto una forma (per dare profondita')."""
    m = ImageChops.offset(mask, int(k(spostamento[0])), int(k(spostamento[1]))).filter(ImageFilter.GaussianBlur(k(sfocatura)))
    m = m.point(lambda v: int(v * opacita))
    layer = Image.new("RGBA", base.size, colore + (255,))
    incolla(base, layer, m)


def disegna_icona():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # ------------------------------------------------------------------ 1. fondo: quadrato arrotondato
    fondo_m = maschera(lambda d: d.rounded_rectangle((k(36), k(36), k(988), k(988)), radius=k(222), fill=255))
    fondo = gradiente_lineare((S, S), (14, 46, 84, 255), (16, 140, 142, 255), 55)
    # alone di luce in alto a sinistra
    alone = gradiente_radiale((S, S), (k(300), k(230)), k(760), (255, 255, 255, 70), (255, 255, 255, 0))
    fondo.alpha_composite(alone)
    # leggera ombreggiatura in basso a destra
    buio = gradiente_radiale((S, S), (k(900), k(960)), k(700), (0, 0, 0, 0), (0, 0, 0, 0))
    incolla(img, fondo, fondo_m)
    # filetto luminoso interno
    bordo = maschera(lambda d: d.rounded_rectangle((k(36), k(36), k(988), k(988)), radius=k(222), outline=255, width=int(k(5))))
    bordo = ImageChops.multiply(bordo, fondo_m).point(lambda v: int(v * 0.28))
    incolla(img, Image.new("RGBA", (S, S), (255, 255, 255, 255)), bordo)

    # ------------------------------------------------------------------ 2. lente d'ingrandimento
    C = (k(425), k(425))          # centro della lente
    R = k(296)                    # raggio esterno anello
    spessore = k(40)              # spessore anello
    r = R - spessore              # raggio interno (vetro)
    dirx = diry = 1 / math.sqrt(2)

    # --- manico
    p0 = (C[0] + dirx * (R - k(10)), C[1] + diry * (R - k(10)))
    p1 = (C[0] + dirx * (R + k(330)), C[1] + diry * (R + k(330)))
    larg = int(k(104))

    def manico(d, w=larg, extra=0):
        d.line((p0, p1), fill=255, width=w + extra)
        for p in (p1,):
            d.ellipse((p[0] - (w + extra) / 2, p[1] - (w + extra) / 2, p[0] + (w + extra) / 2, p[1] + (w + extra) / 2), fill=255)

    manico_m = maschera(manico)
    ombra(img, manico_m, (10, 22), 24, 0.42)
    manico_col = gradiente_lineare((S, S), (246, 250, 253, 255), (150, 172, 192, 255), 135)
    incolla(img, manico_col, manico_m)
    # impugnatura scura (parte finale del manico) con rilievo
    imp = maschera(lambda d: d.line(((C[0] + dirx * (R + k(130)), C[1] + diry * (R + k(130))), p1), fill=255, width=int(k(86)))
                   )
    imp2 = maschera(lambda d: (d.line(((C[0] + dirx * (R + k(130)), C[1] + diry * (R + k(130))), p1), fill=255, width=int(k(86))),
                               d.ellipse((p1[0] - k(43), p1[1] - k(43), p1[0] + k(43), p1[1] + k(43)), fill=255)))
    imp_col = gradiente_lineare((S, S), (30, 58, 92, 255), (11, 30, 56, 255), 135)
    incolla(img, imp_col, imp2)
    # riflesso sottile lungo il manico
    rif = maschera(lambda d: d.line(((p0[0] - k(22), p0[1] + k(26)), (p1[0] - k(22), p1[1] + k(26))), fill=255, width=int(k(10))), blur=k(3))
    rif = ImageChops.multiply(rif, manico_m).point(lambda v: int(v * 0.55))
    incolla(img, Image.new("RGBA", (S, S), (255, 255, 255, 255)), rif)

    # --- ombra dell'anello sul fondo
    anello_m = maschera(lambda d: (d.ellipse((C[0] - R, C[1] - R, C[0] + R, C[1] + R), fill=255)))
    ombra(img, anello_m, (8, 26), 30, 0.45)

    # --- vetro: pelle con neo
    vetro_m = maschera(lambda d: d.ellipse((C[0] - r, C[1] - r, C[0] + r, C[1] + r), fill=255))
    pelle = gradiente_radiale((S, S), (C[0] - k(50), C[1] - k(60)), r * 1.25, (255, 232, 214, 255), (238, 190, 162, 255))
    incolla(img, pelle, vetro_m)

    # texture leggerissima della pelle (puntini casuali ma riproducibili)
    rng = np.random.default_rng(7)
    tex = Image.new("L", (S, S), 0)
    td = ImageDraw.Draw(tex)
    for _ in range(110):
        a = rng.uniform(0, 2 * math.pi); d_ = r * math.sqrt(rng.uniform(0, 1)) * 0.96
        x, y = C[0] + d_ * math.cos(a), C[1] + d_ * math.sin(a)
        rr = rng.uniform(k(1.5), k(3.2))
        td.ellipse((x - rr, y - rr, x + rr, y + rr), fill=int(rng.uniform(25, 55)))
    tex = ImageChops.multiply(tex.filter(ImageFilter.GaussianBlur(k(0.8))), vetro_m)
    incolla(img, Image.new("RGBA", (S, S), (150, 96, 70, 255)), tex)

    # --- il neo: macchia irregolare con bordo netto, due toni di pigmento e qualche globulo (aspetto "dermoscopico")
    nc = (C[0] + k(10), C[1] + k(16))
    pts = []
    for i in range(240):
        t = 2 * math.pi * i / 240
        rad = k(92) * (1 + 0.17 * math.sin(2 * t + 0.6) + 0.12 * math.sin(3 * t + 2.1) + 0.07 * math.sin(5 * t + 4.0))
        pts.append((nc[0] + rad * math.cos(t) * 1.08, nc[1] + rad * math.sin(t) * 0.92))
    alone_m = maschera(lambda d: d.polygon([(nc[0] + (x - nc[0]) * 1.22, nc[1] + (y - nc[1]) * 1.22) for x, y in pts], fill=255), blur=k(14))
    incolla(img, Image.new("RGBA", (S, S), (196, 128, 96, 255)), alone_m.point(lambda v: int(v * 0.5)))
    neo_m = maschera(lambda d: d.polygon(pts, fill=255), blur=k(2.0))
    neo = gradiente_radiale((S, S), (nc[0] - k(26), nc[1] - k(30)), k(140), (146, 92, 58, 255), (84, 46, 26, 255))
    incolla(img, neo, ImageChops.multiply(neo_m, vetro_m))
    # nucleo piu' scuro, spostato (asimmetria tipica delle lesioni da osservare)
    inner = maschera(lambda d: d.polygon([(nc[0] + (x - nc[0]) * 0.62 + k(12), nc[1] + (y - nc[1]) * 0.62 + k(14)) for x, y in pts], fill=255), blur=k(7))
    incolla(img, Image.new("RGBA", (S, S), (34, 16, 8, 255)), ImageChops.multiply(inner, neo_m).point(lambda v: int(v * 0.92)))
    # globuli scuri vicino al bordo
    glob = Image.new("L", (S, S), 0)
    gd = ImageDraw.Draw(glob)
    for (gx, gy, gr) in ((-62, -40, 7), (58, -52, 6), (70, 30, 8), (-34, 66, 6), (12, -70, 5), (-76, 12, 6)):
        gd.ellipse((nc[0] + k(gx) - k(gr), nc[1] + k(gy) - k(gr), nc[0] + k(gx) + k(gr), nc[1] + k(gy) + k(gr)), fill=255)
    glob = ImageChops.multiply(glob.filter(ImageFilter.GaussianBlur(k(1.2))), neo_m)
    incolla(img, Image.new("RGBA", (S, S), (24, 10, 5, 255)), glob.point(lambda v: int(v * 0.9)))

    # --- ombra interna del bordo del vetro (profondita')
    ring_in = maschera(lambda d: d.ellipse((C[0] - r, C[1] - r, C[0] + r, C[1] + r), outline=255, width=int(k(22))), blur=k(14))
    ring_in = ImageChops.multiply(ring_in, vetro_m).point(lambda v: int(v * 0.55))
    incolla(img, Image.new("RGBA", (S, S), (70, 36, 22, 255)), ring_in)

    # --- tacche di misura sul vetro (quattro, discrete)
    tacche = maschera(lambda d: [d.line((C[0] + math.cos(a) * (r - k(34)), C[1] + math.sin(a) * (r - k(34)),
                                         C[0] + math.cos(a) * (r - k(8)), C[1] + math.sin(a) * (r - k(8))), fill=255, width=int(k(7)))
                                 for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2)], blur=k(1))
    incolla(img, Image.new("RGBA", (S, S), (255, 255, 255, 255)), tacche.point(lambda v: int(v * 0.55)))

    # --- anello metallico
    anello_f = maschera(lambda d: d.ellipse((C[0] - R, C[1] - R, C[0] + R, C[1] + R), fill=255))
    buco = maschera(lambda d: d.ellipse((C[0] - r, C[1] - r, C[0] + r, C[1] + r), fill=255))
    anello = ImageChops.subtract(anello_f, buco)
    metallo = gradiente_lineare((S, S), (255, 255, 255, 255), (143, 168, 190, 255), 50)
    incolla(img, metallo, anello)
    # filetto scuro interno e riflesso sul bordo esterno dell'anello
    filo = maschera(lambda d: d.ellipse((C[0] - r - k(2), C[1] - r - k(2), C[0] + r + k(2), C[1] + r + k(2)), outline=255, width=int(k(5))))
    incolla(img, Image.new("RGBA", (S, S), (40, 70, 100, 255)), filo.point(lambda v: int(v * 0.55)))
    luce = maschera(lambda d: d.arc((C[0] - R + k(9), C[1] - R + k(9), C[0] + R - k(9), C[1] + R - k(9)), 190, 285, fill=255, width=int(k(9))), blur=k(2))
    incolla(img, Image.new("RGBA", (S, S), (255, 255, 255, 255)), luce.point(lambda v: int(v * 0.9)))

    # --- riflesso sul vetro (mezzaluna luminosa in alto a sinistra)
    vetro_rif = maschera(lambda d: (d.ellipse((C[0] - r + k(26), C[1] - r + k(22), C[0] + r * 0.35, C[1] + r * 0.05), fill=255)), blur=k(2))
    taglio = maschera(lambda d: d.ellipse((C[0] - r + k(58), C[1] - r + k(66), C[0] + r * 0.45, C[1] + r * 0.2), fill=255), blur=k(2))
    mezzaluna = ImageChops.multiply(ImageChops.subtract(vetro_rif, taglio), vetro_m)
    incolla(img, Image.new("RGBA", (S, S), (255, 255, 255, 255)), mezzaluna.point(lambda v: int(v * 0.30)))
    # velatura del vetro: bianco-azzurro che sfuma dall'alto a sinistra verso il centro
    velo = gradiente_lineare((S, S), (210, 240, 255, 70), (210, 240, 255, 0), 45)
    velo_a = velo.getchannel("A").point(lambda v: v)
    velo_m = ImageChops.multiply(velo_a, vetro_m)
    velo_m = ImageChops.multiply(velo_m, maschera(lambda d: d.ellipse((C[0] - r * 1.1, C[1] - r * 1.1, C[0] + r * 0.9, C[1] + r * 0.2), fill=255), blur=k(40)))
    incolla(img, Image.new("RGBA", (S, S), (225, 245, 255, 255)), velo_m)

    # ------------------------------------------------------------------ 3. scintilla "analisi automatica"
    def scintilla(cx, cy, raggio, alpha=255):
        pts_ = []
        for i in range(8):
            ang = math.pi / 2 * (i / 2) - math.pi / 2
            rr = raggio if i % 2 == 0 else raggio * 0.2
            pts_.append((cx + rr * math.cos(ang + math.pi / 4 * 0), cy + rr * math.sin(ang)))
        # costruzione: stella a 4 punte con rientranze concave
        pts_ = []
        for i in range(16):
            ang = 2 * math.pi * i / 16 - math.pi / 2
            if i % 4 == 0:
                rr = raggio
            else:
                rr = raggio * (0.18 + 0.10 * (i % 2))
            pts_.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
        return pts_

    for (cx, cy, rg) in ((k(800), k(235), k(112)), (k(905), k(395), k(52)), (k(690), k(98) + k(6), k(40))):
        glow = maschera(lambda d: d.polygon(scintilla(cx, cy, rg * 1.25), fill=255), blur=k(22))
        incolla(img, Image.new("RGBA", (S, S), (120, 235, 230, 255)), glow.point(lambda v: int(v * 0.65)))
        st = maschera(lambda d: d.polygon(scintilla(cx, cy, rg), fill=255), blur=k(0.8))
        stella = gradiente_lineare((S, S), (255, 255, 255, 255), (170, 245, 238, 255), 90)
        incolla(img, stella, st)

    # ritaglio finale sulla forma del fondo (nessuna sbavatura fuori dal quadrato arrotondato)
    # (le ombre/scintille restano comunque dentro: la lente e' interamente nel quadrato)
    # ritaglio finale: niente deve uscire dal quadrato arrotondato
    alfa = ImageChops.multiply(img.getchannel("A"), fondo_m)
    img.putalpha(alfa)
    return img


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    out.mkdir(parents=True, exist_ok=True)
    grande = disegna_icona().resize((1024, 1024), Image.LANCZOS)
    grande.save(out / "Analizza_neo_1024.png")

    # frame ICO: ognuno ridotto dalla tela grande con LANCZOS (nitido e senza aloni)
    misure = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
    frame = []
    for m in misure:
        f = grande.resize((m, m), Image.LANCZOS)
        if m <= 32:   # a taglie piccole un leggero ritocco di nitidezza aiuta la leggibilita'
            f = f.filter(ImageFilter.UnsharpMask(radius=0.6, percent=70, threshold=2))
        frame.append(f)
    frame[-1].save(out / "Analizza_neo.ico", format="ICO", sizes=[(m, m) for m in misure], append_images=frame[:-1])
    print("ICO scritto:", out / "Analizza_neo.ico")


if __name__ == "__main__":
    main()
