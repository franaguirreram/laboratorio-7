#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tramos lineales de la ida y de la vuelta, por umbral sobre el RECORRIDO
de la velocidad.

Criterio (uno solo, y en una línea):

    se deriva la posición -> v(t); se normaliza v entre su mínimo y su
    máximo; el tramo lineal de la IDA es donde la normalizada supera
    FRAC, y el de la VUELTA donde queda por debajo de 1-FRAC. Todo lo
    del medio -- aceleración, frenado, puntas -- se descarta.

Es el mismo criterio que uno aplicaría a ojo sobre el gráfico del error
de seguimiento en una rampa triangular: sube hasta una meseta, cruza, y
baja hasta la meseta opuesta. Las dos mesetas son los tramos lineales.
Por eso el panel (c) dibuja el error con el MISMO criterio aplicado
encima: si las dos segmentaciones coinciden, el tramo es real.

Nota sobre FRAC: en un triángulo simétrico el mínimo de v es -v_meseta y
el máximo +v_meseta, así que "90 % del recorrido total" equivale a
"80 % de la meseta". La tabla de sensibilidad que imprime el script
muestra cuánto se mueve el resultado con FRAC; conviene mirarla antes de
creerle a un número.

Uso:
    python3 scripts/tramos_lineales_90.py                     # rampa más nueva
    python3 scripts/tramos_lineales_90.py datos/raw/XXX.csv   # una en particular
"""
import sys
import glob
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
FRAC = 0.90        # umbral, como fracción del recorrido máximo-mínimo
T_CONV_MS = 33.0   # [MEDIDO] transitorio a descartar del arranque del tramo

plt.rcParams.update({"font.family": "serif", "font.size": 10,
                     "axes.labelsize": 11, "figure.dpi": 120})
COL = {"ida": "#1f77b4", "vuelta": "#d62728"}


# --------------------------------------------------------------- funciones
def cargar(arg=None):
    """CSV + metadata de una corrida. Sin argumento, la rampa más nueva."""
    if arg is None:
        c = (sorted(glob.glob(str(REPO / "datos/raw/E517_rampa_scan_*.csv")))
             or sorted(glob.glob(str(REPO / "datos/raw/E517_rampa_*.csv"))))
        f = Path(c[-1])
    else:
        f = Path(arg)
        f = f if f.is_absolute() else REPO / f
    meta = dict(l.strip().split("=", 1) for l in
                open(REPO / "datos/metadata" / (f.stem + "_metadata.txt"))
                if "=" in l and not l.startswith("#"))
    return pd.read_csv(f), meta, f.stem


def derivar(t_ms, x, n_suave):
    """Velocidad en µm/s, suavizando antes y después de derivar.

    El comando es una ESCALERA: el generador cambia el setpoint una vez
    cada WTR ciclos de servo y se queda quieto en el medio. Derivarlo
    punto a punto da cero la mayor parte del tiempo, así que hay que
    promediar sobre al menos un escalón entero.
    """
    def suave(y, n):
        n = int(max(n, 1))
        if n <= 1:
            return np.asarray(y, float)
        pad = n // 2
        yp = np.pad(np.asarray(y, float), pad, mode="edge")   # borde, NO ceros
        return np.convolve(yp, np.ones(n) / n, mode="same")[pad:pad + len(y)]

    v = np.gradient(suave(x, 2 * n_suave), np.asarray(t_ms) * 1e-3)
    return suave(v, n_suave)


def mesetas(y, frac=FRAC):
    """Máscaras de la meseta de arriba y la de abajo de una señal.

    Se normaliza y entre su mínimo y su máximo (por percentiles 1 y 99,
    para que un pico aislado no fije la escala) y se corta arriba de
    `frac` y abajo de `1-frac`.
    """
    lo, hi = np.percentile(y, 1), np.percentile(y, 99)
    if hi <= lo:
        return np.zeros(len(y), bool), np.zeros(len(y), bool)
    yn = (np.asarray(y, float) - lo) / (hi - lo)
    return yn >= frac, yn <= 1 - frac


def tramo_mas_largo(mascara):
    """Índices del tramo contiguo más largo de una máscara booleana."""
    idx = np.where(mascara)[0]
    if len(idx) == 0:
        return idx
    return max(np.split(idx, np.where(np.diff(idx) > 1)[0] + 1), key=len)


# ---------------------------------------------------------------- análisis
df, meta, nombre = cargar(sys.argv[1] if len(sys.argv) > 1 else None)
t, tgt, cur = df.t_ms.values, df.target_um.values, df.current_um.values
wtr, rtr = int(meta["wtr"]), int(meta["rtr"])
dt_ms = float(np.median(np.diff(t)))

n_escalon = max(int(round(wtr / max(rtr, 1))), 1)     # muestras por escalón
n_conv = int(np.ceil(T_CONV_MS / dt_ms))              # transitorio del arranque

v = derivar(t, tgt, n_escalon)          # velocidad del COMANDO (exacto, sin ruido)
e = (cur - tgt) * 1e3                   # error de seguimiento, en nm
arriba, abajo = mesetas(v)

print(f"\n{nombre}   wtr={wtr}  rtr={rtr}  dt={dt_ms:.3f} ms")
print(f"criterio: v normalizada entre mín y máx; ida ≥ {FRAC:.2f}, "
      f"vuelta ≤ {1-FRAC:.2f}\n")

res = {}
for cual, m in (("ida", arriba), ("vuelta", abajo)):
    i = tramo_mas_largo(m)
    if len(i) == 0:
        print(f"{cual}: sin tramo")
        continue
    u = i[n_conv:] if len(i) > n_conv else np.array([], int)
    res[cual] = {"i": i, "u": u,
                 "v": float(np.median(v[i])),
                 "med": (cur[i][0], cur[i][-1]),
                 "cmd": (tgt[i][0], tgt[i][-1]),
                 "med_u": (cur[u][0], cur[u][-1]) if len(u) else None}
    r = res[cual]
    print(f"{cual:>7}  v = {r['v']:+8.3f} µm/s   t = {t[i][0]:7.1f} .. {t[i][-1]:7.1f} ms "
          f"({t[i][-1]-t[i][0]:6.1f} ms)")
    print(f"{'':>7}  comandada : {r['cmd'][0]:9.4f} .. {r['cmd'][1]:9.4f} µm "
          f"({abs(np.diff(r['cmd'])[0])*1e3:7.1f} nm)")
    print(f"{'':>7}  medida    : {r['med'][0]:9.4f} .. {r['med'][1]:9.4f} µm "
          f"({abs(np.diff(r['med'])[0])*1e3:7.1f} nm)")
    if r["med_u"]:
        print(f"{'':>7}  usable    : {r['med_u'][0]:9.4f} .. {r['med_u'][1]:9.4f} µm "
              f"({abs(np.diff(r['med_u'])[0])*1e3:7.1f} nm)   "
              f"[descartados los primeros {T_CONV_MS:.0f} ms]")
    else:
        print(f"{'':>7}  usable    : VACÍA (el tramo dura menos de {T_CONV_MS:.0f} ms)")
    print()

if len(res) == 2:
    lo = max(min(res["ida"]["med"]), min(res["vuelta"]["med"]))
    hi = min(max(res["ida"]["med"]), max(res["vuelta"]["med"]))
    print(f"solapamiento ida∩vuelta = {lo:.4f} .. {hi:.4f} µm "
          f"({max(hi-lo, 0)*1e3:.1f} nm)\n")

# control: el MISMO criterio sobre el error de seguimiento, que es una
# señal medida e independiente del comando. Si las dos ventanas coinciden,
# el tramo es real; si no, lo está poniendo el umbral.
e_ida, e_vuelta = mesetas(-e)      # -e porque en la ida el error es negativo
for cual, m in (("ida", e_ida), ("vuelta", e_vuelta)):
    i_e, i_v = tramo_mas_largo(m), res.get(cual, {}).get("i", np.array([], int))
    if len(i_e) and len(i_v):
        print(f"control {cual:>6}: por v     t = {t[i_v][0]:7.1f} .. {t[i_v][-1]:7.1f} ms")
        print(f"{'':>15} por error t = {t[i_e][0]:7.1f} .. {t[i_e][-1]:7.1f} ms   "
              f"(diferencia {t[i_e][0]-t[i_v][0]:+.1f} / {t[i_e][-1]-t[i_v][-1]:+.1f} ms)")
print()

# cuánto depende del umbral: si esta tabla se mueve mucho, el borde del
# tramo lo está poniendo FRAC, no la física
print("sensibilidad al umbral (tramo de la ida):")
for f in (0.80, 0.85, 0.90, 0.95, 0.98):
    i = tramo_mas_largo(mesetas(v, f)[0])
    if len(i):
        print(f"   FRAC = {f:.2f}:  t = {t[i][0]:7.1f} .. {t[i][-1]:7.1f} ms "
              f"({t[i][-1]-t[i][0]:6.1f} ms)   x = {tgt[i][0]:.4f} .. {tgt[i][-1]:.4f} µm")


# ------------------------------------------------------------------ figura
fig, ax = plt.subplots(3, 1, figsize=(8, 8), sharex=True)

ax[0].plot(t, tgt, color="0.8", lw=2.0, label="comandada")
ax[0].plot(t, cur, color="0.35", lw=0.6, label="medida")
for cual, r in res.items():
    ax[0].plot(t[r["i"]], cur[r["i"]], color=COL[cual], lw=2.2, label=cual)
    if len(r["u"]):
        ax[0].plot(t[r["u"]], cur[r["u"]], color="k", lw=1.0)
ax[0].set_ylabel(r"$x$ [µm]")
ax[0].legend(frameon=False, fontsize=8, ncol=4, loc="lower right")
ax[0].set_title(f"(a) {nombre} — negro: usable (tramo − {T_CONV_MS:.0f} ms)",
                fontsize=9, loc="left")

lo_v, hi_v = np.percentile(v, 1), np.percentile(v, 99)
ax[1].plot(t, v, color="k", lw=0.9)
for u_lin, c in ((lo_v + FRAC * (hi_v - lo_v), COL["ida"]),
                 (lo_v + (1 - FRAC) * (hi_v - lo_v), COL["vuelta"])):
    ax[1].axhline(u_lin, color=c, ls="--", lw=0.8)
for cual, r in res.items():
    ax[1].fill_between(t, lo_v, hi_v, where=np.isin(np.arange(len(t)), r["i"]),
                       color=COL[cual], alpha=0.18, lw=0)
ax[1].set_ylabel("velocidad comandada [µm/s]")
ax[1].set_title(f"(b) el criterio: {FRAC:.0%} del recorrido máx−mín de v",
                fontsize=9, loc="left")

ax[2].plot(t, e, color="k", lw=0.7)
for cual, r in res.items():
    ax[2].fill_between(t, e.min(), e.max(), where=np.isin(np.arange(len(t)), r["i"]),
                       color=COL[cual], alpha=0.18, lw=0)
    ax[2].axhline(np.median(e[r["i"]]), color=COL[cual], ls="--", lw=0.8)
ax[2].set_ylabel("error de seguimiento [nm]")
ax[2].set_xlabel("t [ms]")
ax[2].set_title("(c) control: el error tiene sus propias mesetas (±v·tau) — "
                "tienen que caer en las mismas ventanas", fontsize=9, loc="left")

plt.tight_layout()
salida = REPO / "resultados/figuras/tramos_lineales_90.pdf"
plt.savefig(salida, bbox_inches="tight", dpi=200)
plt.savefig(salida.with_suffix(".png"), bbox_inches="tight", dpi=200)
print(f"\n[figura] {salida.relative_to(REPO)} (+ .png)")
plt.show()
