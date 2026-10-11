"""Datos del clip 02b (STORM simulado): la adquisición completa sale de storm_sim.py.

Se simula una vez (~15 s) y se guarda en ~/.cache/manim-lab7/storm_sim.npz.
"""
import os
import subprocess

import numpy as np
from PIL import Image

import storm_sim as sim

CACHE = os.path.expanduser("~/.cache/manim-lab7")
CANVAS = 600                      # píxeles del lienzo de reconstrucción (8,3 nm/px)
BOX = sim.ZOOM_BOX                # zoom del "¿cuántos filamentos hay acá?" (µm)
PDF = os.environ.get("STORM_PDF", os.path.expanduser(
    "~/Downloads/Microscopías de super resolución_2023_WorkshopFIUNER.pptx.pdf"))


def ramp(x, a, b):
    u = np.clip((x - a) / (b - a), 0, 1)
    return u * u * (3 - 2 * u)


class Datos:
    def __init__(self, r):
        self.stack = r["stack"]
        self.xy = r["loc_xy"]
        self.fr = r["loc_frame"]
        self.start = np.searchsorted(self.fr, np.arange(sim.NFRAMES + 1))
        # campo amplio: todas las moléculas encendidas a la vez, borrosas por la PSF
        h = np.histogram2d(r["emitters"][:, 1], r["emitters"][:, 0], bins=CANVAS * 6 // 5,
                           range=[[-sim.MARGIN, sim.FOV + sim.MARGIN]] * 2)[0]
        nm_px = sim.FOV * 1000 / CANVAS
        wf = sim.gsmooth(h.astype(np.float32), sim.SIGMA_PSF * 1000 / nm_px)
        o = (wf.shape[0] - CANVAS) // 2
        wf = wf[o:o + CANVAS, o:o + CANVAS]
        self.wf = (wf / wf.max()) ** 0.85
        # lienzo de reconstrucción
        self.cx = np.clip((self.xy[:, 0] / sim.FOV * CANVAS).astype(int), 0, CANVAS - 1)
        self.cy = np.clip((self.xy[:, 1] / sim.FOV * CANVAS).astype(int), 0, CANVAS - 1)
        self.inside = ((self.xy > 0) & (self.xy < sim.FOV)).all(1)
        c = np.zeros((CANVAS, CANVAS), np.float32)
        np.add.at(c, (self.cy[self.inside], self.cx[self.inside]), 1)
        self.blur_sigma = 14.0 / nm_px
        fin = sim.gsmooth(c, self.blur_sigma)
        self.vmax = np.percentile(fin[fin > 0], 99.5)

    def frame_img(self, f):
        """Fotograma de la cámara en el campo mostrado (50x50 píxeles de 100 nm), fondo restado."""
        o = int(round(sim.MARGIN / sim.PIX))
        return np.clip(self.stack[f, o:o + 50, o:o + 50].astype(float) - 8, 0, None)

    def locs_in(self, f):
        return self.xy[self.start[f]:self.start[f + 1]]

    def zoom_wf(self):
        x0, x1, y0, y1 = BOX
        k = CANVAS / sim.FOV
        return self.wf[int(y0 * k):int(y1 * k), int(x0 * k):int(x1 * k)]


class Acumulador:
    """Lienzo de reconstrucción que solo avanza: discos al principio, densidad suavizada después."""
    R = 3
    PAD = 4

    def __init__(self, d):
        self.d = d
        self.C = np.zeros((CANVAS, CANVAS), np.float32)
        p = CANVAS + 2 * self.PAD
        self.D = np.zeros((p, p), np.float32)
        yy, xx = np.mgrid[-self.R:self.R + 1, -self.R:self.R + 1]
        self.disco = (xx ** 2 + yy ** 2 <= self.R ** 2).astype(np.float32) * 0.75   # 0.75 -> color puro
        self.last = 0

    def hasta(self, f):
        d = self.d
        if f < self.last:
            return
        sel = np.arange(d.start[self.last], d.start[f + 1])
        sel = sel[d.inside[sel]]
        np.add.at(self.C, (d.cy[sel], d.cx[sel]), 1)
        if d.start[f + 1] < 4500:
            for i in sel:
                y, x = d.cy[i] + self.PAD - self.R, d.cx[i] + self.PAD - self.R
                blk = self.D[y:y + 2 * self.R + 1, x:x + 2 * self.R + 1]
                np.maximum(blk, self.disco, out=blk)
        self.last = f + 1

    def array(self):
        n = self.d.start[self.last]
        a = ramp(n, 1500, 9000)
        discos = self.D[self.PAD:-self.PAD, self.PAD:-self.PAD]
        if a < 0.01:
            return discos
        dens = np.clip(sim.gsmooth(self.C, self.d.blur_sigma) / self.d.vmax, 0, 1) ** 0.6
        return (1 - a) * discos + a * dens


def cargar():
    os.makedirs(CACHE, exist_ok=True)
    ruta = os.path.join(CACHE, "storm_sim.npz")
    if os.path.exists(ruta):
        r = dict(np.load(ruta))
    else:
        r = sim.run()
        np.savez_compressed(ruta, **r)
    return Datos(r)


def diapositivas(pdf=PDF):
    """Recortes (PIL) de las diapositivas 24 a 26 de la presentación: imágenes reales de STORM."""
    specs = {24: (0, 68, 1000, 520), 25: (490, 88, 958, 527), 26: (95, 72, 858, 545)}
    out = {}
    carpeta = os.path.join(CACHE, "storm_diapositivas")
    os.makedirs(carpeta, exist_ok=True)
    for pag, box in specs.items():
        destino = os.path.join(carpeta, f"s{pag}.png")
        if not os.path.exists(destino):
            base = os.path.join(carpeta, f"p{pag}")
            subprocess.run(["pdftoppm", "-r", "150", "-f", str(pag), "-l", str(pag), "-png", "-singlefile", pdf, base],
                           check=True)
            im = Image.open(base + ".png").convert("RGB")
            w, h = im.size
            im.crop((int(box[0] / 1000 * w), int(box[1] / 563 * h), int(box[2] / 1000 * w), int(box[3] / 563 * h))).save(destino)
        out[pag] = np.array(Image.open(destino).convert("RGB"))
    return out
