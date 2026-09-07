#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Análisis del barrido RTR × DCO del 2026-09-07 (ítem 5 del protocolo).

No toca el hardware: lee `resultados/barridos/barrido_rtr_dco_*.csv` (el
resumen, una fila por corrida) y los CSV crudos correspondientes.

Responde las dos preguntas del ítem 5:
  1. ¿Cuánto tarda REALMENTE en asentar un escalón, con y sin DCO, medido
     en ventanas comparables? (hasta ahora el número de DCO=OFF era una
     inferencia a partir de ventanas demasiado cortas)
  2. ¿El resultado depende de RTR? (control: no debería — RTR cambia lo
     que MIRÁS, no lo que la platina HACE)
"""
import glob
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
FIG = REPO / "resultados" / "figuras"
plt.rcParams.update({"font.family": "serif", "font.size": 10,
                     "axes.labelsize": 11, "figure.dpi": 120})

resumen = sorted(glob.glob(str(REPO / "resultados/barridos/barrido_rtr_dco_*.csv")))[-1]
df = pd.read_csv(resumen)
d = df[df.ok].copy()

# Corridas perturbadas: el ruido de fondo de la cola delata un golpe en la
# mesa o un transitorio. Se marcan, no se borran.
piso = d.ruido_final_nm_rms.median()
d["perturbada"] = d.ruido_final_nm_rms > 3 * piso
lim = d[~d.perturbada]

fig, ax = plt.subplots(2, 2, figsize=(9, 6.5))

# (a) trazas de error superpuestas, DCO on vs off
for f in sorted(glob.glob(str(REPO / "datos/raw/E517_escalon_rtrdco_rtr5_*.csv"))):
    if "20260907_170" not in f:      # solo las corridas buenas de hoy
        continue
    c = pd.read_csv(f)
    if c.target_um.min() == 0:        # corrida con la cola rota
        continue
    # excluir las corridas perturbadas: un golpe en la mesa tapa el efecto
    # que queremos mostrar
    if Path(f).stem in set(lim.archivo.astype(str)) is False:
        continue
    if Path(f).stem not in set(lim.archivo.astype(str)):
        continue
    on = "dco1" in f
    i0 = int(np.argmax(np.abs(np.diff(c.target_um.values)))) + 1
    t = c.t_ms.values - c.t_ms.values[i0]
    e = (c.current_um.values - np.median(c.target_um.values[i0:])) * 1e3
    ax[0, 0].plot(t, e, lw=0.9, color="#d62728" if on else "#2ca02c",
                  label=("DCO = ON" if on else "DCO = OFF"))
ax[0, 0].axhspan(-5, 5, color="gray", alpha=0.2, lw=0)
ax[0, 0].set_xlim(-10, 300); ax[0, 0].set_ylim(-120, 90)
ax[0, 0].set_xlabel("t − t escalón [ms]"); ax[0, 0].set_ylabel("error [nm]")
ax[0, 0].set_title("(a) el 'bump' de DCO, escalón de 2 µm", fontsize=10, loc="left")
h, l = ax[0, 0].get_legend_handles_labels()
ax[0, 0].legend(dict(zip(l, h)).values(), dict(zip(l, h)).keys(), frameon=False)

# (b) ts vs RTR — el control: no debe depender de RTR
for on, col in [(True, "#d62728"), (False, "#2ca02c")]:
    g = lim[lim.dco == on]
    ax[0, 1].semilogx(g.rtr, g.ts_5nm_ms, "o", color=col, ms=6,
                      label=f"DCO = {'ON' if on else 'OFF'}")
    ax[0, 1].axhline(g.ts_5nm_ms.median(), color=col, lw=0.8, ls="--")
ax[0, 1].set_ylim(0, 250)
ax[0, 1].set_xlabel("RTR"); ax[0, 1].set_ylabel(r"$t_s$ (banda ±5 nm) [ms]")
ax[0, 1].set_title("(b) control: el resultado no depende de RTR", fontsize=10, loc="left")
ax[0, 1].legend(frameon=False)

# (c) bump vs RTR
for on, col in [(True, "#d62728"), (False, "#2ca02c")]:
    g = lim[lim.dco == on]
    ax[1, 0].semilogx(g.rtr, g.bump_lento_nm, "o", color=col, ms=6)
    ax[1, 0].axhline(g.bump_lento_nm.median(), color=col, lw=0.8, ls="--")
ax[1, 0].axhline(0, color="k", lw=0.5)
ax[1, 0].set_xlabel("RTR"); ax[1, 0].set_ylabel("pico de la excursión lenta [nm]")
ax[1, 0].set_title("(c) el bump es 10× más grande con DCO", fontsize=10, loc="left")

# (d) la contracara: deriva en la ventana larga (RTR = 25 → 8.2 s)
for f in sorted(glob.glob(str(REPO / "datos/raw/E517_escalon_rtrdco_rtr25_*.csv"))):
    if "20260907_170" not in f:
        continue
    c = pd.read_csv(f)
    if c.target_um.min() == 0:
        continue
    on = "dco1" in f
    t = c.t_ms.values / 1000
    m = t > 0.5
    x = (c.current_um.values - np.median(c.current_um.values[(t > 0.4) & (t < 0.6)])) * 1e3
    col = "#d62728" if on else "#2ca02c"
    ax[1, 1].plot(t[m], x[m], lw=0.4, color=col, alpha=0.25)
    # promedio móvil de 100 ms: el ruido de 1.1 nm tapa una deriva de nm/min
    k = max(int(0.1 / np.median(np.diff(t))), 1)
    xs = np.convolve(x, np.ones(k) / k, mode="same")
    ax[1, 1].plot(t[m][k:-k], xs[m][k:-k], lw=1.4, color=col,
                  label=f"DCO = {'ON' if on else 'OFF'}")
ax[1, 1].axhspan(-5, 5, color="gray", alpha=0.2, lw=0)
ax[1, 1].set_xlabel("t [s]"); ax[1, 1].set_ylabel("posición − posición a 0.5 s [nm]")
ax[1, 1].set_title("(d) la contracara: deriva en 8 s (trazo grueso: media móvil 100 ms)",
                   fontsize=9, loc="left")
h, l = ax[1, 1].get_legend_handles_labels()
ax[1, 1].legend(dict(zip(l, h)).values(), dict(zip(l, h)).keys(),
                frameon=False, fontsize=9, loc="upper right")

plt.tight_layout()
plt.savefig(FIG / "barrido_01_rtr_dco.pdf", bbox_inches="tight", dpi=200)
plt.savefig(FIG / "barrido_01_rtr_dco.png", bbox_inches="tight", dpi=200)
print("[figura] resultados/figuras/barrido_01_rtr_dco.pdf (+ .png)")

print(f"\ncorridas: {len(d)} ok, {int(d.perturbada.sum())} perturbadas "
      f"(ruido > 3× el piso de {piso:.2f} nm rms)")
for var in ("t_subida_10_90_ms", "bump_lento_nm", "ts_5nm_ms", "error_final_nm"):
    on = lim[lim.dco][var]; off = lim[~lim.dco][var]
    print(f"{var:22s}  ON {on.median():8.2f} [{on.min():.2f}, {on.max():.2f}]"
          f"   OFF {off.median():8.2f} [{off.min():.2f}, {off.max():.2f}]")
