#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
¿Dónde está, EN POSICIÓN, el tramo lineal de la ida y el de la vuelta?

No toca el hardware: lee un CSV ya medido de una rampa triangular
(`datos/raw/E517_rampa_*` o el que se le pase por línea de comandos) y
responde una sola pregunta:

    de los ~2 µm que recorre la platina, ¿qué intervalo de x barre a
    velocidad constante yendo, qué intervalo barre volviendo, y cuánto
    de eso es COMÚN a las dos direcciones?

Por qué no dan lo mismo: en velocidad constante el error de seguimiento
vale e = v·tau [MEDIDO: tau ~ 12.1 ms], y v cambia de signo entre la ida
y la vuelta. O sea que la platina va corrida ~v·tau *hacia atrás* en la
ida y ~v·tau *hacia adelante* en la vuelta: los dos tramos rectos MEDIDOS
quedan desplazados uno respecto del otro por 2·v·tau, aunque el comando
sea exactamente el mismo intervalo. Eso es lo que se ve en el panel (b):
el solapamiento es la franja de x que se puede escanear en las dos
direcciones (imagen ida+vuelta sin descartar media pasada).

Además de la zona de velocidad constante se marca la zona USABLE de cada
dirección: la que queda después de descartar los primeros t_conv = 33 ms
[MEDIDO], mientras el error de seguimiento todavía está creciendo hacia
v·tau y el espaciado entre píxeles todavía no es uniforme.

Uso:
    python3 scripts/tramos_lineales.py                      # última corrida de rampa
    python3 scripts/tramos_lineales.py datos/raw/XXXX.csv   # una en particular
"""
import sys
import glob
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("b", REPO / "scripts/E517_barrido.py")
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)

plt.rcParams.update({"font.family": "serif", "font.size": 10,
                     "axes.labelsize": 11, "figure.dpi": 120})

COL = {"ida": "#1f77b4", "vuelta": "#d62728"}


# ----------------------------------------------------------------- datos
def cargar(arg=None):
    """Devuelve (df, metadata, nombre). Sin argumento, la rampa más nueva."""
    if arg is None:
        candidatos = sorted(glob.glob(str(REPO / "datos/raw/E517_rampa_scan_*.csv")))
        if not candidatos:
            candidatos = sorted(glob.glob(str(REPO / "datos/raw/E517_rampa_*.csv")))
        f = Path(candidatos[-1])
    else:
        f = Path(arg)
        if not f.is_absolute():
            f = REPO / f
    meta = dict(l.strip().split("=", 1) for l in
                open(REPO / "datos/metadata" / (f.stem + "_metadata.txt"))
                if "=" in l and not l.startswith("#"))
    return pd.read_csv(f), meta, f.stem


def tramo_mas_largo(mascara):
    """Índices del tramo contiguo más largo de una máscara booleana."""
    idx = np.where(mascara)[0]
    if len(idx) == 0:
        return idx
    cortes = np.where(np.diff(idx) > 1)[0]
    return max(np.split(idx, cortes + 1), key=len)


def retardo_ms(t, tgt, cur, i):
    """Cuánto se atrasa la posición MEDIDA respecto de la comandada.

    Corrimiento k que minimiza ||cur[n+k] − tgt[n]|| sobre la rampa. Da
    ~13 ms [MEDIDO: tau_lag = 13.1 ms], y es la razón por la que la
    máscara —que se calcula sobre el COMANDO— no cae exactamente encima
    del tramo recto de la MEDIDA.
    """
    dt = float(np.median(np.diff(t)))
    lo = max(i[0] - int(50 / dt), 0)
    hi = min(i[-1] + int(50 / dt), len(t) - 1)
    ks = range(int(60 / dt))
    mse = [np.mean((cur[lo + k:hi] - tgt[lo:hi - k]) ** 2) for k in ks]
    return int(np.argmin(mse)) * dt


def ventana_lineal(t, x, i0, tol_nm, paso_ms=1.0):
    """Mayor ventana alrededor de i0 cuyo residuo a UNA recta < tol_nm.

    Criterio independiente del comando y de cualquier constante de tiempo:
    se le pide directamente a la trayectoria MEDIDA que sea una recta
    dentro de la tolerancia que uno esté dispuesto a aceptar. La
    tolerancia natural es medio píxel: si la posición se aparta de la
    recta menos que eso, el espaciado entre píxeles es uniforme a los
    fines prácticos.
    """
    paso = max(int(round(paso_ms / np.median(np.diff(t)))), 1)

    def residuo(a, c):
        p = np.polyfit(t[a:c + 1], x[a:c + 1], 1)
        return np.max(np.abs(x[a:c + 1] - np.polyval(p, t[a:c + 1]))) * 1e3

    a, c = max(i0 - paso, 0), min(i0 + paso, len(t) - 1)
    creciendo = True
    while creciendo:
        creciendo = False
        if a - paso >= 0 and residuo(a - paso, c) < tol_nm:
            a -= paso; creciendo = True
        if c + paso < len(t) and residuo(a, c + paso) < tol_nm:
            c += paso; creciendo = True
    return a, c


# ------------------------------------------------------------- análisis
df, meta, nombre = cargar(sys.argv[1] if len(sys.argv) > 1 else None)
t = df.t_ms.values
tgt = df.target_um.values
cur = df.current_um.values
wtr, rtr = int(meta["wtr"]), int(meta["rtr"])
dt_ms = float(np.median(np.diff(t)))

# La segmentación se hace sobre el COMANDO (exacto, sin ruido), no sobre
# la medida: derivar la medida amplifica 1.1 nm rms de ruido a decenas de
# µm/s. Ver docstring de zonas_rampa() en E517_barrido.py.
z = b.zonas_rampa(t, tgt, wtr, rtr)

n_conv = int(np.ceil(b.T_CONV_MS / dt_ms))   # muestras a descartar del arranque

print(f"\n{nombre}   (wtr={wtr}, rtr={rtr}, dt={dt_ms:.3f} ms)")
print(f"tramo lineal = |v| >= 95 % de la meseta;  usable = tramo lineal "
      f"menos los primeros {b.T_CONV_MS:.0f} ms\n")

res = {}
for cual in ("ida", "vuelta"):
    i = tramo_mas_largo(z[cual])
    if len(i) == 0:
        print(f"{cual}: no hay tramo a velocidad constante")
        continue
    u = i[n_conv:] if len(i) > n_conv else np.array([], dtype=int)
    # el lag se mide donde ya está en régimen: en la zona usable si la hay
    j = u if len(u) else i
    # chequeo independiente: hasta dónde la MEDIDA es una recta dentro de
    # medio píxel, sin usar ni el umbral de velocidad ni los 33 ms
    v_i = float(np.median(z["v_um_s"][i]))
    px_nm = abs(v_i) * (wtr * 40e-6) * 1e3
    a, c = ventana_lineal(t, cur, i[len(i) // 2], px_nm / 2)
    res[cual] = {
        "i": i, "u": u,
        "lag_nm": float(np.median(cur[j] - tgt[j])) * 1e3,
        "v": float(np.median(z["v_um_s"][i])),
        "t": (t[i][0], t[i][-1]),
        "cmd": (tgt[i][0], tgt[i][-1]),
        "med": (cur[i][0], cur[i][-1]),
        "med_u": (cur[u][0], cur[u][-1]) if len(u) else None,
        "px_nm": px_nm,
        "lin": (a, c),
        "t_lin": (t[a], t[c]),
        "med_lin": (cur[a], cur[c]),
        "retardo_ms": retardo_ms(t, tgt, cur, i),
    }
    r = res[cual]
    print(f"{cual:>7}   v = {r['v']:+8.3f} µm/s   t = {r['t'][0]:7.1f} .. "
          f"{r['t'][1]:7.1f} ms  ({r['t'][1]-r['t'][0]:6.1f} ms)   "
          f"lag = {r['lag_nm']:+6.1f} nm")
    print(f"{'':>7}   comandada : x = {r['cmd'][0]:9.4f} .. {r['cmd'][1]:9.4f} µm "
          f"({abs(r['cmd'][1]-r['cmd'][0])*1e3:7.1f} nm)")
    print(f"{'':>7}   medida    : x = {r['med'][0]:9.4f} .. {r['med'][1]:9.4f} µm "
          f"({abs(r['med'][1]-r['med'][0])*1e3:7.1f} nm)")
    if r["med_u"] is not None:
        print(f"{'':>7}   usable    : x = {r['med_u'][0]:9.4f} .. {r['med_u'][1]:9.4f} µm "
              f"({abs(r['med_u'][1]-r['med_u'][0])*1e3:7.1f} nm)")
    else:
        print(f"{'':>7}   usable    : VACÍA (el tramo recto dura menos que "
              f"{b.T_CONV_MS:.0f} ms)")
    print(f"{'':>7}   [chequeo] la MEDIDA es recta dentro de {r['px_nm']/2:.1f} nm "
          f"(½ píxel) entre t = {r['t_lin'][0]:.1f} .. {r['t_lin'][1]:.1f} ms")
    print(f"{'':>7}             x = {r['med_lin'][0]:9.4f} .. {r['med_lin'][1]:9.4f} µm "
          f"({abs(r['med_lin'][1]-r['med_lin'][0])*1e3:7.1f} nm)   "
          f"retardo medida←comando = {r['retardo_ms']:.1f} ms")
    print()

# solapamiento de los tramos MEDIDOS: la franja escaneable en las dos direcciones
if len(res) == 2:
    lo = max(min(res["ida"]["med"]), min(res["vuelta"]["med"]))
    hi = min(max(res["ida"]["med"]), max(res["vuelta"]["med"]))
    # el corrimiento entre las dos pasadas es la diferencia de lags, no la
    # de los extremos de los intervalos: los extremos también dependen de
    # dónde arranca y termina la meseta de velocidad constante.
    corrimiento = res["vuelta"]["lag_nm"] - res["ida"]["lag_nm"]
    print(f"corrimiento ida↔vuelta = lag_vuelta − lag_ida = {corrimiento:+.1f} nm "
          f"(≈ 2·v·tau = {2*abs(res['ida']['v'])*12.1e-3*1e3:.1f} nm con tau = 12.1 ms)")
    print(f"solapamiento medido = {lo:.4f} .. {hi:.4f} µm "
          f"({max(hi-lo, 0)*1e3:.1f} nm de los "
          f"{abs(res['ida']['med'][1]-res['ida']['med'][0])*1e3:.1f} nm de una pasada)")


# --------------------------------------------------------------- figura
fig, ax = plt.subplots(2, 1, figsize=(8, 6),
                       gridspec_kw={"height_ratios": [3, 1]})

# (a) la trayectoria, con los tramos rectos pintados
ax[0].plot(t, tgt, color="0.8", lw=2.0, label="comandada")
ax[0].plot(t, cur, color="0.35", lw=0.6, label="medida")
for cual, r in res.items():
    ax[0].plot(t[r["i"]], cur[r["i"]], color=COL[cual], lw=2.0,
               label=f"{cual}: tramo lineal")
    if len(r["u"]):
        ax[0].plot(t[r["u"]], cur[r["u"]], color=COL[cual], lw=4.0, alpha=0.35,
                   solid_capstyle="butt", label=f"{cual}: usable")
ax[0].set_xlabel("t [ms]"); ax[0].set_ylabel(r"$x$ [µm]")
ax[0].legend(frameon=False, fontsize=8, ncol=2, loc="lower center")
ax[0].set_title(f"(a) {nombre}", fontsize=9, loc="left")

# (b) lo mismo pero en el eje de POSICIÓN: dónde cae cada tramo
for k, (cual, r) in enumerate(res.items()):
    y = 1 - k
    ax[1].plot(r["med"], [y, y], color=COL[cual], lw=6, solid_capstyle="butt",
               label=f"{cual} (medida)")
    if len(r["u"]):
        ax[1].plot(r["med_u"], [y, y], color="k", lw=2, solid_capstyle="butt")
    ax[1].plot(r["med_lin"], [y - 0.12, y - 0.12], color="0.3", lw=1.2, ls=":",
               solid_capstyle="butt")
    ax[1].plot(r["cmd"], [y + 0.22, y + 0.22], color=COL[cual], lw=2, alpha=0.4,
               solid_capstyle="butt")
    # punta de flecha: en qué sentido se recorre ese intervalo
    ax[1].annotate("", xy=(r["med"][1], y - 0.25), xytext=(r["med"][0], y - 0.25),
                   arrowprops=dict(arrowstyle="-|>,head_width=0.28,head_length=0.5",
                                   color=COL[cual], lw=1.2, shrinkA=0, shrinkB=0))
if len(res) == 2 and hi > lo:
    ax[1].axvspan(lo, hi, color="#2ca02c", alpha=0.15, lw=0)
    ax[1].text((lo + hi) / 2, -0.55, f"común: {(hi-lo)*1e3:.0f} nm",
               ha="center", fontsize=8, color="#2ca02c")
ax[1].set_yticks([1, 0]); ax[1].set_yticklabels(["ida", "vuelta"])
ax[1].set_ylim(-0.7, 1.6)
ax[1].set_xlabel(r"$x$ [µm]")
ax[1].set_title("(b) posición de los tramos lineales — grueso: velocidad constante "
                "(medida) · negro: usable · fino claro: comando\n"
                "     punteado: ventana en que la MEDIDA es recta dentro de ½ píxel "
                "(chequeo independiente)",
                fontsize=8, loc="left")

plt.tight_layout()
salida = REPO / "resultados/figuras/tramos_lineales_ida_vuelta.pdf"
plt.savefig(salida, bbox_inches="tight", dpi=200)
plt.savefig(salida.with_suffix(".png"), bbox_inches="tight", dpi=200)
print(f"\n[figura] {salida.relative_to(REPO)} (+ .png)")
plt.show()
