#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zonas de una rampa: dónde acelera, dónde va a velocidad constante, y qué
parte de eso sirve para escanear.

No toca el hardware. Lee las corridas de rampa del 2026-09-07
(`datos/raw/E517_rampa_*`) y usa `zonas_rampa()` de E517_barrido.py.

La pregunta que responde: de todo el recorrido de la platina, ¿qué tramo
tiene el espaciado entre píxeles uniforme y por lo tanto sirve como
imagen? Hay DOS recortes, y el segundo es el que se suele olvidar:

  1. sacar los extremos donde el generador acelera y desacelera
     (`speedupdown`): ahí el paso espacial entre puntos no es uniforme;
  2. sacar, además, los primeros 3τ ≈ 36 ms del tramo de velocidad
     constante: ahí el comando ya va parejo pero la platina todavía se
     está poniendo al día, y el error de seguimiento todavía está
     creciendo hacia su valor de régimen e = v·τ.
"""
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
TAU_MS = 12.1          # [MEDIDO] constante de tiempo del lazo

def cargar(patron):
    f = sorted(glob.glob(str(REPO / "datos/raw" / patron)))[-1]
    d = pd.read_csv(f)
    meta = dict(l.strip().split("=", 1) for l in
                open(str(REPO / "datos/metadata" /
                         (Path(f).stem + "_metadata.txt")))
                if "=" in l and not l.startswith("#"))
    return d, int(meta["wtr"]), int(meta["rtr"]), int(meta["speedupdown"])

# ---------------------------------------------------------------- figura
fig, ax = plt.subplots(2, 2, figsize=(10, 7))
d, wtr, rtr, sud = cargar("E517_rampa_sud40_*.csv")
t, tgt, cur = d.t_ms.values, d.target_um.values, d.current_um.values
z = b.zonas_rampa(t, tgt, wtr, rtr, tau_ms=TAU_MS)
COL = {"acel": "#ff7f0e", "constante": "#1f77b4", "usable": "#2ca02c"}

# (a) la trayectoria, pintada por zona
ax[0, 0].plot(t, (tgt - 100) * 1e3, color="0.75", lw=2.5, label="comandada")
for nombre in ("acel", "constante", "usable"):
    m = z[nombre]
    y = np.where(m, (tgt - 100) * 1e3, np.nan)
    ax[0, 0].plot(t, y, color=COL[nombre], lw=2.5 if nombre != "usable" else 3.5,
                  label={"acel": "acelerando / frenando",
                         "constante": "velocidad constante (comando)",
                         "usable": "USABLE para escanear"}[nombre])
ax[0, 0].plot(t, (cur - 100) * 1e3, color="k", lw=0.6, label="real (sensor)")
ax[0, 0].set_xlabel("t [ms]"); ax[0, 0].set_ylabel(r"$x - 100\ \mu$m [nm]")
ax[0, 0].set_title(f"(a) triángulo con speedupdown={sud}", fontsize=10, loc="left")
ax[0, 0].legend(frameon=False, fontsize=8, loc="lower center")

# (b) la velocidad comandada: acá se ve por qué el criterio es el que es
v = z["v_um_s"]
ax[0, 1].plot(t, v, color="k", lw=1.0)
ax[0, 1].axhline(0.98 * np.max(np.abs(v)), color="#1f77b4", ls="--", lw=0.8,
                 label="umbral 98 % de |v| máx")
ax[0, 1].axhline(-0.98 * np.max(np.abs(v)), color="#1f77b4", ls="--", lw=0.8)
for nombre in ("acel", "usable"):
    ax[0, 1].fill_between(t, -np.max(np.abs(v)) * 1.15, np.max(np.abs(v)) * 1.15,
                          where=z[nombre], color=COL[nombre], alpha=0.18, lw=0)
ax[0, 1].set_xlabel("t [ms]"); ax[0, 1].set_ylabel("velocidad comandada [µm/s]")
ax[0, 1].set_title("(b) el criterio: derivada del COMANDO, no de la medida",
                   fontsize=10, loc="left")
ax[0, 1].legend(frameon=False, fontsize=8)

# (c) el error: por qué no alcanza con el criterio de velocidad
e = (cur - tgt) * 1e3
ax[1, 0].plot(t, e, color="k", lw=0.7)
ax[1, 0].fill_between(t, e.min(), e.max(), where=z["constante"],
                      color=COL["constante"], alpha=0.15, lw=0)
ax[1, 0].fill_between(t, e.min(), e.max(), where=z["usable"],
                      color=COL["usable"], alpha=0.30, lw=0)
if "v_constante_um_s" in z:
    e_reg = -z["v_constante_um_s"] * TAU_MS * 1e-3 * 1e3
    ax[1, 0].axhline(e_reg, color="#d62728", lw=1.0, ls="--",
                     label=fr"$-v\tau$ = {e_reg:.0f} nm (régimen)")
    ax[1, 0].legend(frameon=False, fontsize=8, loc="lower right")
ax[1, 0].set_xlabel("t [ms]"); ax[1, 0].set_ylabel("error de seguimiento [nm]")
ax[1, 0].set_title("(c) el azul claro ya va a v constante, pero el error\n"
                   "     todavía está creciendo: por eso se descartan 3τ más",
                   fontsize=9, loc="left")

# (d) qué fracción del recorrido sobrevive, según el suavizado
filas = []
for sud_i in (0, 40, 80):
    try:
        di, w, r, sd = cargar(f"E517_rampa_sud{sud_i}_*.csv")
    except IndexError:
        continue
    zi = b.zonas_rampa(di.t_ms.values, di.target_um.values, w, r, tau_ms=TAU_MS)
    if "v_constante_um_s" not in zi:
        continue
    filas.append({"speed\nupdown": sd, "v\n[µm/s]": zi["v_constante_um_s"],
                  "acel\n[ms]": zi["t_acel_ms"],
                  "v cte\n[ms]": zi["t_constante_ms"],
                  "3τ req\n[ms]": zi["t_3tau_necesario_ms"],
                  "usable\n[ms]": zi["t_usable_ms"],
                  "usable\n[µm]": zi["recorrido_usable_um"],
                  "Δx/pto\n[nm]": zi["dx_por_punto_nm"],
                  "% del\nciclo": 100 * zi["frac_usable"]})
tab = pd.DataFrame(filas)
ax[1, 1].axis("off")
ax[1, 1].set_title("(d) cuánto del ciclo queda utilizable", fontsize=10, loc="left")
if len(tab):
    tt = ax[1, 1].table(cellText=np.round(tab.values, 1), colLabels=tab.columns,
                        loc="upper center", cellLoc="center")
    tt.auto_set_font_size(False); tt.set_fontsize(7); tt.scale(1, 2.6)
    ax[1, 1].text(0.0, 0.08,
                  "speedupdown=80 (el que se venía usando con N=400):\n"
                  "la meseta de velocidad constante dura 31 ms, MENOS que\n"
                  "los 36 ms que la platina necesita → 0 % utilizable.",
                  transform=ax[1, 1].transAxes, fontsize=8.5, color="#d62728")

plt.tight_layout()
plt.savefig(REPO / "resultados/figuras/barrido_02_zonas_rampa.pdf",
            bbox_inches="tight", dpi=200)
plt.savefig(REPO / "resultados/figuras/barrido_02_zonas_rampa.png",
            bbox_inches="tight", dpi=200)
print("[figura] resultados/figuras/barrido_02_zonas_rampa.pdf (+ .png)\n")
if len(tab):
    print(tab.round(2).to_string(index=False))
