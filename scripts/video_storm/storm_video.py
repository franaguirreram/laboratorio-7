#!/usr/bin/env python3
"""Video corto de STORM: de las luces que parpadean a la posición de cada molécula.

Uso:
    python3 -I storm_video.py --pdf "Microscopías de super resolución....pdf" \
        --out storm.mp4 [--cache sim.npz] [--snap 5,20,40]

La parte principal es una simulación real (storm_sim.py): los parpadeos, las
manchas, los ajustes gaussianos y la imagen final salen de ahí. Al final entran
imágenes reales de la presentación (diapositivas 24 a 26), que se extraen del PDF.
"""
import argparse
import os
import subprocess
import tempfile

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle, Circle
from PIL import Image

import storm_sim as sim

W, H, DPI, FPS = 1280, 720, 100, 30
BG, FG, MUTED = "#06070b", "#e8ecf1", "#8a93a3"
GREEN, ORANGE, CYAN, MAGENTA = "#3ddc84", "#ff9f1c", "#4cc9f0", "#ff3d81"
plt.rcParams["font.family"] = ["Arial", "Helvetica", "DejaVu Sans"]

CM_GREEN = LinearSegmentedColormap.from_list(
    "wf", ["#000000", "#06301a", "#1fa85a", "#7bf0a8", "#f2fff6"])
CM_HOT = LinearSegmentedColormap.from_list(
    "storm", ["#000000", "#3a0505", "#b3200a", "#ff7a00", "#ffd24a", "#fffbe8"])

CANVAS = 600          # píxeles del lienzo de reconstrucción (8.33 nm/px)
BOX = sim.ZOOM_BOX


def ease(u):
    u = np.clip(u, 0, 1)
    return u * u * (3 - 2 * u)


def ramp(t, a, b):
    return ease((t - a) / (b - a))


# ------------------------------------------------------------------ datos
class Data:
    def __init__(self, r):
        self.r = r
        self.stack = r["stack"]
        self.xy = r["loc_xy"]
        self.fr = r["loc_frame"]
        self.N = r["loc_N"]
        self.start = np.searchsorted(self.fr, np.arange(sim.NFRAMES + 1))
        e = r["err"][np.isfinite(r["err"][:, 0])] * 1000
        self.prec_nm = float(np.mean(1.4826 * np.median(np.abs(e - np.median(e, 0)), 0)))
        self.fwhm_nm = 2.355 * sim.SIGMA_PSF * 1000

        # imagen de campo amplio: todas las moléculas ON a la vez, borrosas por la PSF
        h = np.histogram2d(r["emitters"][:, 1], r["emitters"][:, 0], bins=CANVAS * 6 // 5,
                           range=[[-sim.MARGIN, sim.FOV + sim.MARGIN]] * 2)[0]
        nm_px = sim.FOV * 1000 / CANVAS
        wf = sim.gsmooth(h.astype(np.float32), sim.SIGMA_PSF * 1000 / nm_px)
        o = (wf.shape[0] - CANVAS) // 2
        wf = wf[o:o + CANVAS, o:o + CANVAS]
        self.wf = (wf / wf.max()) ** 0.85
        self.wf_raw = wf / wf.max()

        # reconstrucción final y lienzo para acumular
        self.nm_px = nm_px
        self.cx = np.clip(((self.xy[:, 0]) / sim.FOV * CANVAS).astype(int), 0, CANVAS - 1)
        self.cy = np.clip(((self.xy[:, 1]) / sim.FOV * CANVAS).astype(int), 0, CANVAS - 1)
        inside = ((self.xy > 0) & (self.xy < sim.FOV)).all(1)
        self.inside = inside
        c = np.zeros((CANVAS, CANVAS), np.float32)
        np.add.at(c, (self.cy[inside], self.cx[inside]), 1)
        self.blur_sigma = 14.0 / nm_px
        fin = sim.gsmooth(c, self.blur_sigma)
        self.vmax = np.percentile(fin[fin > 0], 99.5)
        self.final = np.clip(fin / self.vmax, 0, 1) ** 0.6

        self.pick_demo()
        self.profiles()

    def frame_img(self, f):
        o = int(round(sim.MARGIN / sim.PIX))
        return self.stack[f, o:o + 50, o:o + 50]

    def locs_in(self, f):
        a, b = self.start[f], self.start[f + 1]
        return self.xy[a:b]

    def pick_demo(self):
        """Una molécula aislada, central, con fotones típicos, en los primeros fotogramas."""
        r = self.r
        best = None
        err = r["err"]
        for i in range(len(self.fr)):
            f = self.fr[i]
            if f < 6:
                continue
            if f > 40:
                break
            x, y = self.xy[i]
            if not (1.4 < x < 3.6 and 1.4 < y < 3.6):
                continue
            if not (300 < self.N[i] < 600):
                continue
            if not np.isfinite(err[i, 0]) or np.hypot(*err[i]) > 0.015:
                continue
            best = i
            break
        self.demo = best
        self.demo_frame = int(self.fr[best])
        iy, ix = r["loc_peak_iy"][best], r["loc_peak_ix"][best]
        h = 5
        roi = self.stack[self.demo_frame, iy - h:iy + h + 1, ix - h:ix + h + 1].astype(float)
        self.roi = roi
        self.roi_ext = ((ix - h) * sim.PIX - sim.MARGIN, (ix + h + 1) * sim.PIX - sim.MARGIN,
                        (iy + h + 1) * sim.PIX - sim.MARGIN, (iy - h) * sim.PIX - sim.MARGIN)
        # historia del ajuste desde una conjetura inicial mala (pico del píxel, sigma ancha)
        p0 = np.array([[h + 0.5 + 0.9, h + 0.5 - 0.7, roi.sum() - sim.BG * roi.size,
                        1.7, np.median(np.r_[roi[0], roi[-1]])]])
        _, _, hist = sim.lm_fit(roi[None], p0, iters=14, history=True)
        self.fit_hist = [hh[0] for hh in hist]
        self.demo_xy = self.xy[best]
        self.demo_err_nm = float(np.hypot(*err[best]) * 1000)

    def profiles(self):
        x0, x1, y0, y1 = BOX
        sx0, sx1 = 2.1, 2.8
        # campo amplio: perfil perpendicular a los filamentos, promediando a lo largo
        ys = (np.arange(CANVAS) + 0.5) / CANVAS * sim.FOV
        xs = ys
        sel = (xs > sx0) & (xs < sx1)
        wf = self.wf_raw[:, sel].mean(1)
        m = (ys > y0) & (ys < y1)
        self.pf_y = ys[m]
        self.pf_wf = wf[m] / wf[m].max()
        # STORM: histograma de localizaciones en la misma franja
        s = (self.xy[:, 0] > sx0) & (self.xy[:, 0] < sx1)
        bins = np.arange(y0, y1 + 0.004, 0.004)
        hh, _ = np.histogram(self.xy[s, 1], bins=bins)
        hh = sim.gsmooth(hh[None, :].astype(np.float32), 2.0)[0]
        self.ps_y = 0.5 * (bins[1:] + bins[:-1])
        self.ps_st = hh / hh.max()
        # separación entre los dos picos
        pk = [i for i in range(1, len(hh) - 1) if hh[i] >= hh[i - 1] and hh[i] > hh[i + 1]]
        pk = sorted(pk, key=lambda i: -hh[i])
        first = pk[0]
        second = next(i for i in pk[1:] if abs(self.ps_y[i] - self.ps_y[first]) > 0.03)
        self.sep_nm = abs(self.ps_y[second] - self.ps_y[first]) * 1000
        self.pk_y = sorted([self.ps_y[first], self.ps_y[second]])
        # FWHM del perfil de campo amplio
        half = self.pf_wf > 0.5
        self.wf_fwhm_nm = (self.pf_y[half][-1] - self.pf_y[half][0]) * 1000

    def storm_zoom(self, box, npx=300, sigma_nm=9.0):
        x0, x1, y0, y1 = box
        h = np.histogram2d(self.xy[:, 1], self.xy[:, 0], bins=npx,
                           range=[[y0, y1], [x0, x1]])[0].astype(np.float32)
        nm = (x1 - x0) * 1000 / npx
        b = sim.gsmooth(h, sigma_nm / nm)
        return np.clip(b / np.percentile(b[b > 0], 99.7), 0, 1) ** 0.7


# ------------------------------------------------------------------ video
class Writer:
    def __init__(self, out, snaps, snapdir):
        self.proc = None
        if out:
            self.proc = subprocess.Popen(
                ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                 "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
                 "-pix_fmt", "yuv420p", "-crf", "17", "-preset", "medium",
                 "-movflags", "+faststart", out], stdin=subprocess.PIPE)
        self.n = 0
        self.snaps = {int(round(s * FPS)): s for s in snaps}
        self.snapdir = snapdir

    def put(self, fig):
        fig.canvas.draw()
        buf = np.asarray(fig.canvas.buffer_rgba())[:, :, :3]
        if self.proc:
            self.proc.stdin.write(buf.tobytes())
        if self.n in self.snaps:
            Image.fromarray(buf).save(os.path.join(self.snapdir, f"snap_{self.snaps[self.n]:05.1f}.png"))
        self.n += 1

    def close(self):
        if self.proc:
            self.proc.stdin.close()
            self.proc.wait()


def new_fig():
    return plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor=BG)


def pax(fig, x, y, w, h, **kw):
    ax = fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H], **kw)
    ax.set_facecolor("black")
    return ax


def txt(fig, x, y, s, size=14, color=FG, ha="left", va="center", weight="normal", alpha=1.0, **kw):
    return fig.text(x / W, 1 - y / H, s, fontsize=size, color=color, ha=ha, va=va,
                    fontweight=weight, alpha=alpha, **kw)


class Chrome:
    """Etiqueta de capítulo, subtítulo y fundido a negro, comunes a todas las escenas."""

    def __init__(self, fig, chapter, captions, dur):
        self.captions, self.dur = captions, dur
        self.tag = txt(fig, 40, 36, chapter, size=13, color=MUTED, weight="bold")
        self.cap = txt(fig, W / 2, 678, "", size=18, ha="center")
        self.fade = Rectangle((0, 0), 1, 1, transform=fig.transFigure, color="black",
                              zorder=1000, alpha=1.0)
        fig.patches.append(self.fade)

    def update(self, t):
        self.fade.set_alpha(1 - min(ramp(t, 0, 0.35), ramp(self.dur - t, 0, 0.35)))
        text, a = "", 0.0
        for t0, t1, s in self.captions:
            if t0 <= t < t1:
                text, a = s, min(ramp(t, t0, t0 + 0.3), ramp(t1 - t, 0, 0.3))
        self.cap.set_text(text)
        self.cap.set_alpha(a)


def square(ax, extent=(0, sim.FOV, sim.FOV, 0)):
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#2a2f3a")


def scalebar(ax, x, y, length, label, color="white", size=11, fs=None):
    ax.plot([x, x + length], [y, y], color=color, lw=3, solid_capstyle="butt", zorder=20)
    ax.text(x + length / 2, y - fs if fs else y - 0.12 * length, label, color=color,
            fontsize=size, ha="center", va="bottom", zorder=20, fontweight="bold")


# ---------------------------------------------------------------- escenas
def scene_intro(d, wr, dur=4.0):
    fig = new_fig()
    ax = pax(fig, (W - H) / 2, 0, H, H)
    square(ax)
    ax.imshow(d.wf, extent=(0, 5, 5, 0), cmap=CM_GREEN, interpolation="bicubic")
    ax.set_alpha(1)
    veil = Rectangle((0, 0), 1, 1, transform=fig.transFigure, color=BG, alpha=0.62, zorder=5)
    fig.patches.append(veil)
    t1 = txt(fig, W / 2, 300, "STORM", size=84, ha="center", weight="bold")
    t2 = txt(fig, W / 2, 392, "Stochastic Optical Reconstruction Microscopy", size=21,
             ha="center", color=GREEN)
    t3 = txt(fig, W / 2, 440, "cómo recuperar posiciones a partir de luces que parpadean",
             size=19, ha="center", color=FG)
    ch = Chrome(fig, "", [], dur)
    for i in range(int(dur * FPS)):
        t = i / FPS
        for tt, a, b in ((t1, 0.2, 1.0), (t2, 0.8, 1.5), (t3, 1.3, 2.0)):
            tt.set_alpha(ramp(t, a, b))
        ch.update(t)
        wr.put(fig)
    plt.close(fig)


def scene_problem(d, wr, dur=9.0):
    fig = new_fig()
    L, T, S = 40, 70, 560
    ax = pax(fig, L, T, S, S)
    square(ax)
    im = ax.imshow(d.wf, extent=(0, 5, 5, 0), cmap=CM_GREEN, interpolation="bicubic")
    dark = ax.imshow(d.frame_img(0), extent=(0, 5, 5, 0), cmap=CM_GREEN, vmin=8, vmax=90,
                     interpolation="nearest", alpha=0)
    scalebar(ax, 0.3, 4.75, 1.0, "1 µm", fs=0.06)
    x0, x1, y0, y1 = BOX
    box = Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec="white", lw=1.6, ls="--", zorder=10)
    ax.add_patch(box)
    txt(fig, L, T + S + 20, "campo amplio · todas las moléculas encendidas", size=12, color=MUTED)

    az = pax(fig, 700, 110, 420, 420)
    square(az, (x0, x1, y1, y0))
    imz = az.imshow(d.wf, extent=(0, 5, 5, 0), cmap=CM_GREEN, interpolation="bicubic")
    for s in az.spines.values():
        s.set_color("white")
        s.set_linestyle("--")
    scalebar(az, x0 + 0.06, y1 - 0.07, 0.2, "200 nm", fs=0.02)
    q = txt(fig, 910, 560, "¿cuántos filamentos hay acá?", size=19, ha="center", color=ORANGE,
            weight="bold")
    zl = txt(fig, 910, 85, "zoom de 1 µm", size=12, color=MUTED, ha="center")
    caps = [(0.3, 3.7, "Con todo encendido, cada molécula se ve como una mancha de ~260 nm: el límite de difracción."),
            (3.8, 6.2, "Estructuras más cercanas que eso se funden en un solo borrón."),
            (6.6, 9.2, "El truco: apagar casi todas las moléculas y dejar que prendan al azar, de a pocas.")]
    ch = Chrome(fig, "1 · EL PROBLEMA", caps, dur)
    for i in range(int(dur * FPS)):
        t = i / FPS
        off = ramp(t, 6.4, 8.0)
        im.set_alpha(1 - off)
        imz.set_alpha(1 - off)
        dark.set_alpha(off)
        q.set_alpha(ramp(t, 3.6, 4.4) * (1 - ramp(t, 6.2, 6.8)))
        zl.set_alpha(1 - off)
        box.set_alpha(1 - off)
        ch.update(t)
        wr.put(fig)
    plt.close(fig)


def contour_model(p, roi_ext, n=11, g=70):
    """Modelo gaussiano evaluado sobre una grilla fina (en µm), para dibujar contornos."""
    xs = np.linspace(0, n, g)
    gx, gy = np.meshgrid(xs, xs)
    x0, y0, N, s, b = p
    z = N / (2 * np.pi * s * s) * np.exp(-((gx - x0) ** 2 + (gy - y0) ** 2) / (2 * s * s))
    ux = roi_ext[0] + gx * sim.PIX
    uy = roi_ext[3] + gy * sim.PIX
    return ux, uy, z


def scene_blink(d, wr):
    n_f = d.demo_frame
    per = 0.5
    t_seq = (n_f + 1) * per                 # fotogramas 0..demo_frame
    t_sel = t_seq + 0.6
    t_fit = t_sel + 2.2
    n_it = len(d.fit_hist)
    t_it = 0.22
    t_res = t_fit + n_it * t_it + 0.4
    dur = t_res + 5.2
    fig = new_fig()
    S = 560
    ax = pax(fig, (W - S) / 2, 70, S, S)
    square(ax)
    im = ax.imshow(d.frame_img(0), extent=(0, 5, 5, 0), cmap=CM_GREEN, vmin=8, vmax=90,
                   interpolation="nearest")
    scalebar(ax, 0.3, 4.75, 1.0, "1 µm", fs=0.06)
    fcount = txt(fig, 640, 70 + S + 20, "", size=12, color=MUTED, ha="center")
    xs, ys = d.demo_xy
    ring = Circle((xs, ys), 0.42, fill=False, ec=MAGENTA, lw=2, zorder=12, alpha=0)
    ax.add_patch(ring)
    pin = ax.scatter([xs], [ys], s=60, c=[ORANGE], zorder=15, alpha=0, edgecolors="white", linewidths=1)

    # panel de ajuste (derecha)
    R = 380
    ar = pax(fig, 790, 95, R, R)
    ar.set_alpha(0)
    ext = d.roi_ext
    imr = ar.imshow(d.roi, extent=ext, cmap=CM_GREEN, vmin=8, vmax=95, interpolation="nearest")
    square(ar, (ext[0], ext[1], ext[2], ext[3]))
    scalebar(ar, ext[0] + 0.05, ext[2] - 0.07, 0.2, "200 nm", fs=0.025, size=10)
    ap = fig.add_axes([800 / W, 1 - 640 / H, 360 / W, 105 / H])
    ap.set_facecolor("none")
    for s in ("top", "right"):
        ap.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ap.spines[s].set_color(MUTED)
    ap.tick_params(colors=MUTED, labelsize=8)
    ap.set_yticks([])
    ap.set_xlabel("posición x (µm)", color=MUTED, fontsize=8, labelpad=1)
    rowi = int(np.clip(np.floor(d.fit_hist[-1][1]), 0, 10))
    xc = ext[0] + (np.arange(11) + 0.5) * sim.PIX
    pts, = ap.plot(xc, d.roi[rowi], "o", color=GREEN, ms=5)
    crv, = ap.plot([], [], color=MAGENTA, lw=2)
    ap.set_xlim(ext[0], ext[1])
    ap.set_ylim(0, d.roi.max() * 1.15)
    lbl_roi = txt(fig, 790 + R / 2, 78, "una sola molécula, vista por la cámara", size=12, color=MUTED, ha="center")
    xyt = txt(fig, 790 + R / 2, 505, "", size=17, color=MAGENTA, ha="center", weight="bold")
    prt = txt(fig, 790 + R / 2, 535, "", size=14, color=FG, ha="center")
    cross_h, = ar.plot([], [], color=MAGENTA, lw=1.2, zorder=14)
    cross_v, = ar.plot([], [], color=MAGENTA, lw=1.2, zorder=14)
    dot, = ar.plot([], [], "o", color=MAGENTA, ms=5, zorder=15)
    psf_c = Circle((0, 0), d.fwhm_nm / 2000, fill=False, ec="white", lw=1.2, ls="--", zorder=13, alpha=0)
    prec_c = Circle((0, 0), d.prec_nm / 1000, fill=False, ec=MAGENTA, lw=1.6, zorder=16, alpha=0)
    ar.add_patch(psf_c)
    ar.add_patch(prec_c)
    cont = [None]

    caps = [(0.3, t_seq - 0.2, "Cada fotograma muestra solo unas pocas moléculas encendidas, bien separadas."),
            (t_seq + 0.1, t_fit - 0.1, "Miremos una: la cámara la ve como una mancha pixelada de ~260 nm."),
            (t_fit + 0.1, t_res - 0.1, "Se ajusta una gaussiana 2D a la mancha: su centro es la posición de la molécula."),
            (t_res + 0.1, dur - 0.4, f"Posición (x, y) con ~{d.prec_nm:.0f} nm de precisión: mucho menor que la mancha.")]
    ch = Chrome(fig, "2 · UN PARPADEO", caps, dur)
    for i in range(int(dur * FPS)):
        t = i / FPS
        f = min(int(t / per), n_f)
        im.set_data(d.frame_img(f))
        fcount.set_text(f"fotograma {f + 1}" if t < t_sel + 2 else "")
        mv = ramp(t, t_seq, t_sel + 0.5)               # el cuadro principal se corre a la izquierda
        ax.set_position([((W - S) / 2 - mv * ((W - S) / 2 - 40)) / W, 1 - (70 + S) / H, S / W, S / H])
        fcount.set_x((640 - mv * 320) / W)
        ring.set_alpha(ramp(t, t_seq, t_seq + 0.4))
        a_r = ramp(t, t_sel, t_sel + 0.5)
        for a in (ar, ap):
            a.set_visible(a_r > 0.01)
        ar.set_alpha(1)
        for o in (imr, pts, lbl_roi):
            o.set_alpha(a_r)
        lbl_roi.set_alpha(a_r)
        # contornos del ajuste en cada iteración
        k = int(np.clip((t - t_fit) / t_it, -1, n_it - 1))
        if cont[0] is not None:
            cont[0].remove()
            cont[0] = None
        crv.set_data([], [])
        if k >= 0:
            p = d.fit_hist[k]
            ux, uy, z = contour_model(p, ext)
            peak = z.max()
            cont[0] = ar.contour(ux, uy, z, levels=peak * np.array([0.15, 0.35, 0.55, 0.75, 0.92]),
                                 colors=[CYAN, "#6ee7b7", "#fde047", ORANGE, MAGENTA], linewidths=1.5, zorder=11)
            xx = np.linspace(0, 11, 120)
            pr = sim.model(np.array([[p[0], p[1], p[2], p[3], p[4]]]), np.arange(12.0))
            # curva suave del perfil en la fila central
            yy = p[4] + p[2] / (2 * np.pi * p[3] ** 2) * np.exp(-((xx - p[0]) ** 2 + (rowi + 0.5 - p[1]) ** 2) / (2 * p[3] ** 2))
            crv.set_data(ext[0] + xx * sim.PIX, yy)
        fin = ramp(t, t_res - 0.4, t_res + 0.3)
        px_, py_ = ext[0] + d.fit_hist[-1][0] * sim.PIX, ext[3] + d.fit_hist[-1][1] * sim.PIX
        if k >= 0:
            pk_x = ext[0] + d.fit_hist[k][0] * sim.PIX
            pk_y = ext[3] + d.fit_hist[k][1] * sim.PIX
            cross_h.set_data([ext[0], ext[1]], [pk_y, pk_y])
            cross_v.set_data([pk_x, pk_x], [ext[2], ext[3]])
            dot.set_data([pk_x], [pk_y])
        else:
            for l in (cross_h, cross_v, dot):
                l.set_data([], [])
        cross_h.set_alpha(0.25 + 0.75 * fin)
        cross_v.set_alpha(0.25 + 0.75 * fin)
        xyt.set_text(f"(x, y) = ({xs:.3f}, {ys:.3f}) µm" if t > t_res else "")
        xyt.set_alpha(fin)
        psf_c.set_center((px_, py_))
        prec_c.set_center((px_, py_))
        psf_c.set_alpha(ramp(t, t_res + 0.5, t_res + 1.0))
        prec_c.set_alpha(ramp(t, t_res + 1.6, t_res + 2.1))
        prt.set_text("mancha ≈ %d nm   →   posición ± %d nm" % (round(d.fwhm_nm, -1), round(d.prec_nm))
                     if t > t_res + 1.6 else "")
        prt.set_alpha(ramp(t, t_res + 1.6, t_res + 2.1))
        pin.set_alpha(ramp(t, t_res + 3.2, t_res + 3.8))
        ch.update(t)
        wr.put(fig)
    plt.close(fig)


def scene_accumulate(d, wr, dur=15.5):
    fig = new_fig()
    L, T, S = 40, 70, 560
    ax = pax(fig, L, T, S, S)
    square(ax)
    dens = ax.imshow(np.zeros((CANVAS, CANVAS)), extent=(0, 5, 5, 0), cmap=CM_HOT, vmin=0, vmax=1,
                     interpolation="bilinear", alpha=0, zorder=2)
    pins = ax.scatter([], [], s=9, c=ORANGE, zorder=5, linewidths=0)
    flash = ax.scatter([], [], s=120, facecolors="none", edgecolors="white", linewidths=1.2, zorder=6)
    scalebar(ax, 0.3, 4.75, 1.0, "1 µm", fs=0.06, color="white")
    txt(fig, L, T + S + 20, "reconstrucción: cada punto es una posición localizada", size=12, color=MUTED)

    ac = pax(fig, 700, 110, 340, 340)
    square(ac)
    imc = ac.imshow(d.frame_img(0), extent=(0, 5, 5, 0), cmap=CM_GREEN, vmin=8, vmax=90, interpolation="nearest")
    det = ac.scatter([], [], s=130, facecolors="none", edgecolors=CYAN, linewidths=1.4, zorder=5)
    txt(fig, 700 + 170, 90, "lo que ve la cámara", size=12, color=MUTED, ha="center")
    fr_t = txt(fig, 700 + 170, 475, "", size=15, ha="center")
    n_t = txt(fig, 700 + 170, 510, "", size=26, ha="center", weight="bold", color=ORANGE)
    sub_t = txt(fig, 700 + 170, 545, "localizaciones", size=12, ha="center", color=MUTED)
    bar_bg = Rectangle((700 / W, 1 - 585 / H), 340 / W, 6 / H, transform=fig.transFigure, color="#1b1f29")
    bar = Rectangle((700 / W, 1 - 585 / H), 0, 6 / H, transform=fig.transFigure, color=ORANGE)
    fig.patches += [bar_bg, bar]

    caps = [(0.3, 4.8, "Cada parpadeo deja un punto en la posición ajustada. La mancha se descarta."),
            (5.0, 10.2, "Se repite miles de veces, con moléculas distintas encendiéndose al azar."),
            (10.5, 15.0, "Los puntos se acumulan y dibujan la estructura con detalle nanométrico.")]
    ch = Chrome(fig, "3 · ACUMULAR", caps, dur)
    C = np.zeros((CANVAS, CANVAS), np.float32)
    last = 0
    end_ramp = dur - 3.0
    for i in range(int(dur * FPS)):
        t = i / FPS
        u = min(t / end_ramp, 1.0)
        f = min(int(sim.NFRAMES * u ** 2.2), sim.NFRAMES - 1)
        if f >= last:
            a, b = d.start[last], d.start[f + 1]
            sel = np.arange(a, b)
            sel = sel[d.inside[sel]]
            np.add.at(C, (d.cy[sel], d.cx[sel]), 1)
            last = f + 1
        n = d.start[f + 1]
        dens_a = ramp(n, 1500, 9000)
        if dens_a > 0.01:
            B = sim.gsmooth(C, d.blur_sigma)
            dens.set_data(np.clip(B / d.vmax, 0, 1) ** 0.6)
        dens.set_alpha(dens_a)
        m = min(n, 4000)
        pins.set_offsets(d.xy[:m][d.inside[:m]])
        pins.set_alpha(1 - dens_a)
        cur = d.locs_in(f)
        flash.set_offsets(cur if len(cur) else np.empty((0, 2)))
        det.set_offsets(cur if len(cur) else np.empty((0, 2)))
        imc.set_data(d.frame_img(f))
        fr_t.set_text(f"fotograma {f + 1:,} / {sim.NFRAMES:,}".replace(",", "."))
        n_t.set_text(f"{n:,}".replace(",", "."))
        bar.set_width(340 * f / sim.NFRAMES / W)
        ch.update(t)
        wr.put(fig)
    plt.close(fig)
    return C


def scene_result(d, wr):
    dur_a, dur_b = 4.6, 11.0
    # ---- a) mismo campo, campo amplio vs STORM
    fig = new_fig()
    S = 560
    a1 = pax(fig, 40, 70, S, S)
    a2 = pax(fig, 680, 70, S, S)
    for a in (a1, a2):
        square(a)
    a1.imshow(d.wf, extent=(0, 5, 5, 0), cmap=CM_GREEN, interpolation="bicubic")
    a2.imshow(d.final, extent=(0, 5, 5, 0), cmap=CM_HOT, interpolation="bilinear")
    scalebar(a1, 0.3, 4.75, 1.0, "1 µm", fs=0.06)
    scalebar(a2, 0.3, 4.75, 1.0, "1 µm", fs=0.06)
    txt(fig, 40 + S / 2, 52, "campo amplio", size=17, ha="center", weight="bold", color=GREEN)
    txt(fig, 680 + S / 2, 52, "STORM", size=17, ha="center", weight="bold", color=ORANGE)
    txt(fig, 640, 350, "→", size=44, ha="center", color=MUTED)
    x0, x1, y0, y1 = BOX
    boxes = [Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec="white", lw=1.6, ls="--", zorder=10, alpha=0) for _ in (0, 1)]
    a1.add_patch(boxes[0])
    a2.add_patch(boxes[1])
    caps = [(0.3, dur_a - 0.3, "Mismo campo, mismas moléculas: la diferencia es solo localizar en vez de enfocar.")]
    ch = Chrome(fig, "4 · EL RESULTADO", caps, dur_a)
    for i in range(int(dur_a * FPS)):
        t = i / FPS
        for b in boxes:
            b.set_alpha(ramp(t, 2.6, 3.2))
        ch.update(t)
        wr.put(fig)
    plt.close(fig)

    # ---- b) zoom sobre el par de filamentos
    fig = new_fig()
    Z = 290
    b1 = pax(fig, 60, 120, Z, Z)
    b2 = pax(fig, 60 + Z + 20, 120, Z, Z)
    square(b1, (x0, x1, y1, y0))
    square(b2, (x0, x1, y1, y0))
    b1.imshow(d.wf, extent=(0, 5, 5, 0), cmap=CM_GREEN, interpolation="bicubic")
    zs = d.storm_zoom(BOX)
    b2.imshow(zs, extent=(x0, x1, y1, y0), cmap=CM_HOT, interpolation="bilinear")
    scalebar(b1, x0 + 0.06, y1 - 0.07, 0.2, "200 nm", fs=0.02, size=10)
    scalebar(b2, x0 + 0.06, y1 - 0.07, 0.2, "200 nm", fs=0.02, size=10)
    txt(fig, 60 + Z / 2, 100, "campo amplio", size=14, ha="center", weight="bold", color=GREEN)
    txt(fig, 60 + Z + 20 + Z / 2, 100, "STORM", size=14, ha="center", weight="bold", color=ORANGE)

    ap = fig.add_axes([730 / W, 1 - 520 / H, 480 / W, 380 / H])
    ap.set_facecolor("none")
    for s in ("top", "right"):
        ap.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ap.spines[s].set_color(MUTED)
    ap.tick_params(colors=MUTED, labelsize=10)
    ap.set_yticks([])
    ap.set_xlabel("posición perpendicular a los filamentos (nm)", color=MUTED, fontsize=11)
    ap.set_xlim(0, (y1 - y0) * 1000)
    ap.set_ylim(0, 1.18)
    ypos = (d.pf_y - y0) * 1000
    sypos = (d.ps_y - y0) * 1000
    l1, = ap.plot([], [], color=GREEN, lw=3)
    l2, = ap.plot([], [], color=ORANGE, lw=3)
    f1 = [None]
    f2 = [None]
    txt(fig, 970, 105, "perfil de intensidad a través del par", size=13, ha="center", color=MUTED)
    t_wf = txt(fig, 60, 450, "", size=15, color=GREEN)
    t_st = txt(fig, 60, 490, "", size=15, color=ORANGE)
    t_tr = txt(fig, 60, 530, "", size=13, color=MUTED)
    pk_x = [(y - y0) * 1000 for y in d.pk_y]
    dim, = ap.plot([], [], color="white", lw=1.5)
    dtxt = ap.text(np.mean(pk_x), 1.08, "", color="white", ha="center", fontsize=14, fontweight="bold")
    caps = [(0.3, 3.6, "Hacemos zoom al par: en campo amplio es una sola banda ancha."),
            (3.9, 7.4, f"En STORM aparecen dos filamentos, separados ~{d.sep_nm:.0f} nm."),
            (7.7, dur_b - 0.4, f"Una separación unas {d.fwhm_nm / d.sep_nm:.0f} veces menor que la mancha de difracción.")]
    ch = Chrome(fig, "4 · EL RESULTADO", caps, dur_b)
    for i in range(int(dur_b * FPS)):
        t = i / FPS
        n1 = int(len(ypos) * ramp(t, 0.6, 2.6))
        n2 = int(len(sypos) * ramp(t, 4.0, 6.2))
        l1.set_data(ypos[:n1], d.pf_wf[:n1])
        l2.set_data(sypos[:n2], d.ps_st[:n2])
        if f1[0]:
            f1[0].remove()
        if f2[0]:
            f2[0].remove()
        f1[0] = ap.fill_between(ypos[:n1], 0, d.pf_wf[:n1], color=GREEN, alpha=0.18)
        f2[0] = ap.fill_between(sypos[:n2], 0, d.ps_st[:n2], color=ORANGE, alpha=0.18)
        t_wf.set_text(f"campo amplio: un pico de ~{d.wf_fwhm_nm:.0f} nm de ancho")
        t_wf.set_alpha(ramp(t, 2.0, 2.7))
        t_st.set_text(f"STORM: dos picos separados {d.sep_nm:.0f} nm")
        t_st.set_alpha(ramp(t, 5.6, 6.3))
        t_tr.set_text(f"separación real en la simulación: {sim.PAIR_SEP_NM:.0f} nm")
        t_tr.set_alpha(ramp(t, 6.8, 7.5))
        if t > 6.2:
            dim.set_data(pk_x, [1.02, 1.02])
            dtxt.set_text(f"{d.sep_nm:.0f} nm")
            dtxt.set_alpha(ramp(t, 6.2, 6.9))
            dim.set_alpha(ramp(t, 6.2, 6.9))
        ch.update(t)
        wr.put(fig)
    plt.close(fig)


def crop_slide(png, box):
    im = Image.open(png).convert("RGB")
    w, h = im.size
    return im.crop((int(box[0] / 1000 * w), int(box[1] / 563 * h), int(box[2] / 1000 * w), int(box[3] / 563 * h)))


def extract_slides(pdf, tmp):
    out = {}
    specs = {24: (0, 68, 1000, 520), 25: (490, 88, 958, 527), 26: (95, 72, 858, 545)}
    for page, box in specs.items():
        base = os.path.join(tmp, f"s{page}")
        subprocess.run(["pdftoppm", "-r", "150", "-f", str(page), "-l", str(page), "-png", "-singlefile", pdf, base],
                       check=True)
        out[page] = crop_slide(base + ".png", box)
    return out


def scene_examples(d, wr, slides):
    items = [
        (slides[24], "Un tripanosomátido en 2 colores (mucinas y trans-sialidasas): límite de difracción vs. STORM", 3.8),
        (slides[25], "Microtúbulos en neuronas, STORM 3D: el color indica la altura z", 3.6),
        (slides[26], "Axones de neuronas (β2-espectrina), 3D-STORM: la organización periódica del citoesqueleto", 3.8),
    ]
    dur = sum(i[2] for i in items) + 0.6
    fig = new_fig()
    ax = pax(fig, 40, 70, 1200, 560)
    ax.set_axis_off()
    ax.set_facecolor(BG)
    imh = ax.imshow(np.asarray(items[0][0]), interpolation="lanczos")
    ax.set_xlim(0, items[0][0].width)
    ax.set_ylim(items[0][0].height, 0)
    credit = txt(fig, W / 2, 705, "Imágenes: Lucía Lopez, «Microscopías de súper resolución», VI Workshop Internacional de Microscopías Ópticas "
                 "Avanzadas (2023) · colab. O. Campetella (UNSAM), D. Refojo (IBIOBA) · NeuroCyto lab",
                 size=8, color=MUTED, ha="center")
    ch = Chrome(fig, "5 · EJEMPLOS REALES", [], dur)
    cap = ch.cap
    starts = np.cumsum([0.3] + [i[2] for i in items])
    for i in range(int(dur * FPS)):
        t = i / FPS
        k = int(np.clip(np.searchsorted(starts, t, side="right") - 1, 0, len(items) - 1))
        img, text, ln = items[k]
        lt = t - starts[k]
        if getattr(scene_examples, "_k", None) != k or i == 0:
            scene_examples._k = k
            imh.set_data(np.asarray(img))
            imh.set_extent((0, img.width, img.height, 0))
            ar = img.width / img.height
            w = min(1200, 560 * ar)
            h = w / ar
            ax.set_position([(W - w) / 2 / W, 1 - (70 + (560 + h) / 2) / H, w / W, h / H])
            ax.set_xlim(0, img.width)
            ax.set_ylim(img.height, 0)
            cap.set_text(text)
        a = min(ramp(lt, 0, 0.5), ramp(items[k][2] - lt, 0, 0.5))
        imh.set_alpha(a)
        cap.set_alpha(a)
        cap.set_fontsize(16)
        ch.fade.set_alpha(1 - min(ramp(t, 0, 0.35), ramp(dur - t, 0, 0.35)))
        wr.put(fig)
    plt.close(fig)


def scene_end(d, wr, dur=4.4):
    fig = new_fig()
    steps = [("Apagar", "casi todas las moléculas"), ("Parpadeo", "unas pocas ON, al azar"),
             ("Ajuste", "gaussiana 2D → (x, y)"), ("Acumular", f"{len(d.xy):,} puntos".replace(",", "."))]
    objs = []
    for k, (a, b) in enumerate(steps):
        x = 175 + k * 310
        objs.append((txt(fig, x, 250, a, size=26, ha="center", weight="bold", color=ORANGE),
                     txt(fig, x, 290, b, size=13, ha="center", color=MUTED)))
        if k < 3:
            objs.append((txt(fig, x + 155, 250, "→", size=30, ha="center", color=MUTED),))
    big = txt(fig, W / 2, 440, "Localizar, en vez de enfocar", size=40, ha="center", weight="bold")
    num = txt(fig, W / 2, 510, f"mancha ≈ {round(d.fwhm_nm, -1):.0f} nm   →   posición ± {d.prec_nm:.0f} nm", size=24,
              ha="center", color=GREEN)
    ch = Chrome(fig, "", [], dur)
    for i in range(int(dur * FPS)):
        t = i / FPS
        k = 0
        for j, o in enumerate(objs):
            for tt in o:
                tt.set_alpha(ramp(t, 0.2 + j * 0.25, 0.7 + j * 0.25))
        big.set_alpha(ramp(t, 1.9, 2.5))
        num.set_alpha(ramp(t, 2.5, 3.1))
        ch.update(t)
        wr.put(fig)
    plt.close(fig)


# ------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True, help="PDF de la presentación (para las imágenes reales)")
    ap.add_argument("--out", default="storm.mp4")
    ap.add_argument("--cache", help="npz de la simulación; se crea si no existe")
    ap.add_argument("--snap", default="", help="segundos separados por coma: guarda PNG de esos instantes")
    ap.add_argument("--snapdir", default=".")
    ap.add_argument("--no-video", action="store_true", help="no codificar mp4 (solo capturas)")
    a = ap.parse_args()

    if a.cache and os.path.exists(a.cache):
        r = dict(np.load(a.cache))
    else:
        r = sim.run()
        if a.cache:
            np.savez_compressed(a.cache, **r)
    d = Data(r)
    print(f"precisión medida {d.prec_nm:.1f} nm · {len(d.xy)} localizaciones · demo en fotograma {d.demo_frame} "
          f"(error {d.demo_err_nm:.1f} nm) · par: {d.sep_nm:.0f} nm, campo amplio {d.wf_fwhm_nm:.0f} nm")
    snaps = [float(s) for s in a.snap.split(",") if s]
    wr = Writer(None if a.no_video else a.out, snaps, a.snapdir)
    with tempfile.TemporaryDirectory() as tmp:
        slides = extract_slides(a.pdf, tmp)
        scene_intro(d, wr)
        scene_problem(d, wr)
        scene_blink(d, wr)
        scene_accumulate(d, wr)
        scene_result(d, wr)
        scene_examples(d, wr, slides)
        scene_end(d, wr)
    wr.close()
    print(f"{wr.n} fotogramas, {wr.n / FPS:.1f} s")


if __name__ == "__main__":
    main()
