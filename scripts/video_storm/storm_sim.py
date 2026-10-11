"""Simulación de una adquisición STORM completa (para el video).

Todo lo que muestra el video sale de acá, no está dibujado a mano:

1. Una muestra de filamentos (tipo microtúbulos) con fluoróforos pegados.
2. Cada fluoróforo parpadea al azar: unos pocos fotogramas ON de vez en cuando.
3. Cada ON es una mancha de difracción (PSF gaussiana, sigma ~110 nm) integrada
   en píxeles de 100 nm, con fotones de Poisson + fondo.
4. Se detectan las manchas y se ajusta una gaussiana 2D (Levenberg-Marquardt
   por mínimos cuadrados) a cada una -> posición (x, y).
5. Se mide el error contra la posición verdadera para saber la precisión real.

Unidades: micrómetros para posiciones, píxeles de cámara de 0.1 um.
La cámara simulada cubre [-0.5, 5.5] um; el campo que se muestra es [0, 5] um
(el margen evita que los bordes queden sin localizaciones).
"""
import numpy as np

FOV = 5.0            # um, campo que se muestra
MARGIN = 0.5         # um, margen simulado a cada lado
PIX = 0.1            # um por píxel de cámara
NS = int(round((FOV + 2 * MARGIN) / PIX))   # 60 píxeles por lado
SIGMA_PSF = 0.110    # um (FWHM ~ 260 nm)
NFRAMES = 6000
BG = 10.0            # fotones de fondo por píxel
N_MEDIAN = 400.0     # fotones por fotograma de una molécula ON (mediana)
SQ2 = np.sqrt(2.0)


def erf(x):
    """erf con la aproximación de Abramowitz-Stegun 7.1.26 (error < 1.5e-7)."""
    s = np.sign(x)
    x = np.abs(x)
    t = 1.0 / (1.0 + 0.3275911 * x)
    poly = ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t
             - 0.284496736) * t + 0.254829592) * t
    return s * (1.0 - poly * np.exp(-x * x))


def gsmooth(a, sigma):
    """Suavizado gaussiano separable sobre los dos últimos ejes."""
    r = int(3 * sigma + 0.5)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    a = np.asarray(a, dtype=np.float32)
    for ax in (-2, -1):
        pad = [(0, 0)] * a.ndim
        pad[ax] = (r, r)
        ap = np.pad(a, pad, mode="reflect")
        out = np.zeros_like(a)
        n = a.shape[ax]
        for i, w in enumerate(k):
            sl = [slice(None)] * a.ndim
            sl[ax] = slice(i, i + n)
            out += np.float32(w) * ap[tuple(sl)]
        a = out
    return a


# ---------------------------------------------------------------- muestra
def catmull(pts, n=300):
    P = np.array(pts, float)
    P = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    t = np.linspace(0, 1, n, endpoint=False)[:, None]
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t
                          + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-2][None])
    return np.vstack(out)


def resample(curve, step):
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(curve, axis=0).T))]
    s = np.arange(0, d[-1], step)
    return np.c_[np.interp(s, d, curve[:, 0]), np.interp(s, d, curve[:, 1])]


# Par de filamentos que se acercan hasta 90 nm entre x = 2.0 y 2.9 um: es el
# "¿cuántos filamentos hay acá?" del video.
PAIR_SEP_NM = 90.0
PAIR_X = [-0.6, 0.0, 0.8, 1.5, 2.0, 2.45, 2.9, 3.4, 4.1, 4.9, 5.7]
PAIR_GAP = [1.6, 1.4, 0.7, 0.22, PAIR_SEP_NM / 1000, PAIR_SEP_NM / 1000,
            PAIR_SEP_NM / 1000, 0.25, 0.9, 1.4, 1.8]
PAIR_C = [2.7, 2.65, 2.6, 2.56, 2.55, 2.55, 2.55, 2.56, 2.5, 2.45, 2.4]
ZOOM_BOX = (1.95, 2.95, 2.05, 3.05)   # x0, x1, y0, y1 en um


def filaments():
    g, c = np.array(PAIR_GAP), np.array(PAIR_C)
    p1 = list(zip(PAIR_X, c - g / 2))
    p2 = list(zip(PAIR_X, c + g / 2))
    return [
        p1, p2,
        [(-0.6, 1.0), (0.5, 1.25), (1.4, 0.85), (2.4, 1.0), (3.3, 0.55),
         (4.4, 0.8), (5.7, 0.55)],
        [(-0.6, 4.3), (0.6, 3.95), (1.7, 4.2), (2.8, 4.55), (3.9, 4.1),
         (5.0, 4.35), (5.7, 4.1)],
        [(3.0, -0.6), (3.35, 0.4), (3.9, 1.4), (4.6, 2.1), (5.0, 3.0),
         (5.1, 3.9), (5.3, 5.7)],
        [(0.7, 5.7), (1.0, 4.9), (0.7, 4.1), (0.9, 3.5), (1.6, 3.1)],
        [(2.2, 5.7), (2.5, 4.9), (3.4, 4.4), (4.3, 4.0)],
        [(-0.6, 2.1), (0.3, 1.8), (0.9, 1.5), (1.8, 1.7)],
        [(2.0, -0.6), (1.7, 0.4), (1.9, 1.0), (2.2, 1.5)],
    ]


def make_emitters(rng, spacing_nm=12.0, lateral_nm=8.0):
    pts = []
    for f in filaments():
        c = resample(catmull(f), spacing_nm / 1000)
        c = c + rng.normal(0, lateral_nm / 1000, c.shape)
        pts.append(c)
    xy = np.vstack(pts)
    lo, hi = -MARGIN + 0.05, FOV + MARGIN - 0.05
    keep = (xy[:, 0] > lo) & (xy[:, 0] < hi) & (xy[:, 1] > lo) & (xy[:, 1] < hi)
    return xy[keep]


# ----------------------------------------------------------- adquisición
def make_events(rng, emitters, cycles=12):
    """Parpadeos al azar: (emisor, fotograma de inicio, duración, fotones)."""
    n_per = rng.poisson(cycles, size=len(emitters))
    em = np.repeat(np.arange(len(emitters)), n_per)
    start = rng.integers(0, NFRAMES, size=em.size)
    dur = rng.geometric(0.6, size=em.size)
    photons = N_MEDIAN * np.exp(rng.normal(0, 0.45, em.size))
    rows = np.repeat(np.arange(em.size), dur)
    off = np.arange(rows.size) - np.repeat(np.cumsum(dur) - dur, dur)
    fr = start[rows] + off
    ok = fr < NFRAMES
    rows, fr = rows[ok], fr[ok]
    o = np.argsort(fr, kind="stable")
    rows, fr = rows[o], fr[o]
    return em[rows], fr, photons[rows] * np.exp(rng.normal(0, 0.1, rows.size))


def render_stack(rng, emitters, ev_em, ev_fr, ev_n):
    """Pila de fotogramas (NFRAMES, NS, NS) en cuentas, con ruido de Poisson."""
    R = 7
    pad = R + 1
    side = NS + 2 * pad
    stack = np.zeros((NFRAMES, NS, NS), np.float32)
    chunk = 500
    edges = np.arange(2 * R + 2)[None, :]
    for f0 in range(0, NFRAMES, chunk):
        a = np.searchsorted(ev_fr, f0)
        b = np.searchsorted(ev_fr, f0 + chunk)
        if b == a:
            continue
        p = (emitters[ev_em[a:b]] + MARGIN) / PIX      # coords en píxeles
        fr = ev_fr[a:b] - f0
        n = ev_n[a:b]
        i0 = np.floor(p).astype(int) - R
        s = SIGMA_PSF / PIX
        ex = 0.5 * (1 + erf((i0[:, 0, None] + edges - p[:, 0, None]) / (s * SQ2)))
        ey = 0.5 * (1 + erf((i0[:, 1, None] + edges - p[:, 1, None]) / (s * SQ2)))
        roi = (n[:, None, None] * np.diff(ey, axis=1)[:, :, None]
               * np.diff(ex, axis=1)[:, None, :])
        jj, ii = np.meshgrid(np.arange(2 * R + 1), np.arange(2 * R + 1))
        yy = i0[:, 1, None, None] + pad + ii[None]
        xx = i0[:, 0, None, None] + pad + jj[None]
        flat = (fr[:, None, None] * side + yy) * side + xx
        acc = np.bincount(flat.ravel(), weights=roi.ravel(),
                          minlength=chunk * side * side)
        acc = acc.reshape(chunk, side, side)[:, pad:pad + NS, pad:pad + NS]
        stack[f0:f0 + chunk] += acc[: NFRAMES - f0].astype(np.float32)
    return rng.poisson(stack + BG).astype(np.uint16)


# ------------------------------------------------------------ localización
def model(p, edges):
    x0, y0, n, s, b = (p[:, i] for i in range(5))
    fx = 0.5 * (1 + erf((edges[None] - x0[:, None]) / (s[:, None] * SQ2)))
    fy = 0.5 * (1 + erf((edges[None] - y0[:, None]) / (s[:, None] * SQ2)))
    return (b[:, None, None] + n[:, None, None]
            * np.diff(fy, axis=1)[:, :, None] * np.diff(fx, axis=1)[:, None, :])


def lm_fit(rois, p0, iters=25, history=False):
    """Levenberg-Marquardt en lote: ajusta (x0, y0, N, sigma, b) a cada ROI."""
    z = rois.astype(float)
    E, n, _ = z.shape
    edges = np.arange(n + 1, dtype=float)
    p = p0.astype(float).copy()
    m = model(p, edges)
    cost = ((z - m) ** 2).sum((1, 2))
    lam = np.full(E, 1e-2)
    hist = [p.copy()]
    for _ in range(iters):
        J = np.empty((E, n * n, 5))
        for k in range(5):
            d = 1e-3 * np.maximum(np.abs(p[:, k]), 1.0)
            pp = p.copy()
            pp[:, k] += d
            J[:, :, k] = ((model(pp, edges) - m) / d[:, None, None]).reshape(E, -1)
        r = (z - m).reshape(E, -1)
        A = np.einsum("eik,eil->ekl", J, J)
        g = np.einsum("eik,ei->ek", J, r)
        A2 = A + lam[:, None, None] * A * np.eye(5) + 1e-9 * np.eye(5)
        try:
            dp = np.linalg.solve(A2, g[..., None])[..., 0]
        except np.linalg.LinAlgError:
            break
        pn = p + dp
        pn[:, 3] = np.clip(pn[:, 3], 0.3, 4.0)
        pn[:, 2] = np.maximum(pn[:, 2], 1.0)
        mn = model(pn, edges)
        cn = ((z - mn) ** 2).sum((1, 2))
        better = np.isfinite(cn) & (cn < cost)
        p[better], m[better], cost[better] = pn[better], mn[better], cn[better]
        lam = np.where(better, lam * 0.3, lam * 5.0)
        if history:
            hist.append(p.copy())
    return (p, cost, hist) if history else (p, cost)


def detect(stack, thr_sigma=5.0, margin=5):
    """Máximos locales del fotograma suavizado por encima de un umbral."""
    d = stack.astype(np.float32) - np.median(stack, axis=(1, 2), keepdims=True)
    g = gsmooth(d, 1.1)
    noise = 1.4826 * np.median(np.abs(g))
    c = g[:, margin:-margin, margin:-margin]
    pk = c > thr_sigma * noise
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            nb = g[:, margin + dy:NS - margin + dy, margin + dx:NS - margin + dx]
            pk &= c >= nb
    f, iy, ix = np.nonzero(pk)
    return f, iy + margin, ix + margin


def localize(stack, roi=9):
    f, iy, ix = detect(stack)
    h = roi // 2
    # descarta picos que tienen a otro a menos de 7 px en el mismo fotograma
    # (dos manchas superpuestas no se pueden ajustar como una sola)
    ok = np.ones(f.size, bool)
    starts = np.searchsorted(f, np.arange(NFRAMES + 1))
    for k in range(NFRAMES):
        a, b = starts[k], starts[k + 1]
        if b - a > 1:
            d = np.hypot(iy[a:b, None] - iy[None, a:b], ix[a:b, None] - ix[None, a:b])
            np.fill_diagonal(d, 99)
            ok[a:b] = d.min(1) > 7
    f, iy, ix = f[ok], iy[ok], ix[ok]
    oy = np.arange(-h, h + 1)
    rois = stack[f[:, None, None], iy[:, None, None] + oy[None, :, None],
                 ix[:, None, None] + oy[None, None, :]].astype(float)
    border = np.r_[rois[:, 0].ravel(), rois[:, -1].ravel()]
    b0 = np.median(border)
    w = np.clip(rois - b0, 0, None)
    cx = (w.sum(1) * (np.arange(roi) + 0.5)).sum(1) / w.sum((1, 2))
    cy = (w.sum(2) * (np.arange(roi) + 0.5)).sum(1) / w.sum((1, 2))
    p0 = np.c_[cx, cy, w.sum((1, 2)), np.full(f.size, 1.2), np.full(f.size, b0)]
    P = np.empty_like(p0)
    C = np.empty(f.size)
    for a in range(0, f.size, 4000):
        P[a:a + 4000], C[a:a + 4000] = lm_fit(rois[a:a + 4000], p0[a:a + 4000])
    good = (np.isfinite(P).all(1) & (P[:, 3] > 0.6) & (P[:, 3] < 2.0)
            & (np.abs(P[:, 0] - cx) < 1.5) & (np.abs(P[:, 1] - cy) < 1.5)
            & (P[:, 2] > 60))
    P, f, iy, ix = P[good], f[good], iy[good], ix[good]
    x = ((ix - h) + P[:, 0]) * PIX - MARGIN
    y = ((iy - h) + P[:, 1]) * PIX - MARGIN
    return dict(xy=np.c_[x, y], frame=f, N=P[:, 2], sigma=P[:, 3] * PIX,
                bg=P[:, 4], peak_iy=iy, peak_ix=ix)


def match_error(loc, emitters, ev_em, ev_fr):
    """Error de cada localización contra el emisor verdadero más cercano."""
    starts = np.searchsorted(ev_fr, np.arange(NFRAMES + 1))
    err = np.full((len(loc["frame"]), 2), np.nan)
    for k in np.unique(loc["frame"]):
        a, b = starts[k], starts[k + 1]
        if a == b:
            continue
        true = emitters[ev_em[a:b]]
        idx = np.nonzero(loc["frame"] == k)[0]
        for i in idx:
            d = true - loc["xy"][i]
            j = np.argmin(np.hypot(*d.T))
            if np.hypot(*d[j]) < 0.25:
                err[i] = -d[j]
    return err


def run(seed=7):
    rng = np.random.default_rng(seed)
    emitters = make_emitters(rng)
    ev_em, ev_fr, ev_n = make_events(rng, emitters)
    stack = render_stack(rng, emitters, ev_em, ev_fr, ev_n)
    loc = localize(stack)
    err = match_error(loc, emitters, ev_em, ev_fr)
    return dict(emitters=emitters, ev_em=ev_em, ev_fr=ev_fr, ev_n=ev_n,
                stack=stack, err=err, **{f"loc_{k}": v for k, v in loc.items()})


if __name__ == "__main__":
    import sys
    import time
    t0 = time.time()
    out = sys.argv[1] if len(sys.argv) > 1 else "storm_sim.npz"
    r = run()
    np.savez_compressed(out, **r)
    e = r["err"][np.isfinite(r["err"][:, 0])] * 1000
    rob = 1.4826 * np.median(np.abs(e - np.median(e, 0)), 0)
    print(f"emisores {len(r['emitters'])}  eventos(emisor-fotograma) {len(r['ev_fr'])}")
    print(f"localizaciones {len(r['loc_frame'])}  con verdad asociada {len(e)}")
    print(f"error std x,y (nm): {e.std(0).round(1)}   robusto: {rob.round(1)}")
    print(f"por fotograma: {len(r['loc_frame']) / NFRAMES:.1f} loc/fotograma"
          f"   N mediana {np.median(r['loc_N']):.0f}   sigma ajustado {np.median(r['loc_sigma']) * 1000:.0f} nm")
    print(f"{time.time() - t0:.0f} s -> {out}")
