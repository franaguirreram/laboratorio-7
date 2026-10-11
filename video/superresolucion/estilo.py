"""Estilo y física compartidos por todos los clips de superresolución.

Colores con significado fijo (ver PLAN.md) y utilidades para dibujar
imágenes de microscopio (PSF, donas) como ImageMobject.
"""
import numpy as np
from manim import *

# ---------- colores ----------
BG = "#0b0f14"
FOTON = "#FFD166"       # fotones / luz detectada
PIXEL = "#58C4DD"       # cámara / imagen registrada
MOLECULA = "#FF6B6B"    # posición real
ESTIMA = "#7EE787"      # estimación / localización
GRIS = "#8B98A5"
EXCITA = "#7AA2F7"      # láser de excitación
STED = "#FF9E64"        # haz de depleción (dona STED)
APAGADA = "#3a4552"     # molécula apagada
HACES = ["#7AA2F7", "#BB9AF7", "#FF9E64", "#2AC3DE"]  # las 4 donas de MINFLUX
config.background_color = BG

# ---------- muestra común: un anillo de 8 moléculas (como un poro nuclear) ----------
RADIO_ANILLO = 55.0      # nm
ANILLO = np.array([[RADIO_ANILLO * np.cos(a), RADIO_ANILLO * np.sin(a)]
                   for a in np.linspace(0, 2 * np.pi, 8, endpoint=False) + np.pi / 8])
SIGMA_PSF_NM = 100.0     # σ de la PSF limitada por difracción (FWHM ≈ 235 nm)


def _hex(c):
    c = ManimColor(c).to_hex().lstrip("#")
    return np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)], dtype=float)


def imagen(valores, color, fondo=BG, gamma=0.8, vmax=None):
    """Array 2D (≥0) → ImageMobject coloreado de `fondo` a `color` (blanco en `vmax`, por defecto el máximo)."""
    v = np.clip(valores / max(vmax or valores.max(), 1e-12), 0, 1) ** gamma
    a, b, w = _hex(fondo), _hex(color), np.array([255.0, 255, 255])
    v3 = v[..., None]
    rgb = np.where(v3 < 0.75, a + (b - a) * v3 / 0.75, b + (w - b) * (v3 - 0.75) / 0.25)
    img = ImageMobject(rgb.astype(np.uint8))
    img.set_resampling_algorithm(RESAMPLING_ALGORITHMS["linear"])
    return img


def malla(semi, n):
    """Grilla n×n que cubre [-semi, semi] nm (filas de arriba hacia abajo)."""
    x = np.linspace(-semi, semi, n)
    X, Y = np.meshgrid(x, -x)
    return X, Y


def gauss(X, Y, x0, y0, s):
    return np.exp(-((X - x0) ** 2 + (Y - y0) ** 2) / (2 * s ** 2))


def dona(X, Y, x0, y0, w):
    """Haz con vórtice de fase: I ∝ (r/w)² e^{-r²/w²}, cero en el centro, máximo 1 en r = w."""
    r2 = ((X - x0) ** 2 + (Y - y0) ** 2) / w ** 2
    return r2 * np.exp(1 - r2)


def barra_escala(nm, nm_por_unidad, etiqueta=None, color=GRIS):
    largo = nm / nm_por_unidad
    linea = Line(ORIGIN, RIGHT * largo, color=color, stroke_width=5)
    txt = Tex(etiqueta or f"{nm:g} nm", font_size=24, color=color).next_to(linea, DOWN, 0.1)
    return VGroup(linea, txt)


def titulo(texto, sub=None):
    t = Tex(texto, font_size=52).to_edge(UP, buff=0.4)
    if sub is None:
        return VGroup(t)
    s = Tex(sub, font_size=30, color=GRIS).next_to(t, DOWN, 0.15)
    return VGroup(t, s)
