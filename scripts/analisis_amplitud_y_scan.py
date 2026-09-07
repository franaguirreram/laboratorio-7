#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Análisis de las dos tandas del 2026-09-07 (tarde). No toca el hardware.

TANDA A — barrido de amplitud (20 corridas de escalón, 20 nm a 100 µm,
          DCO on/off): ¿el lazo es lineal? ¿el bump de DCO escala con el
          tamaño del escalón?

TANDA B — barrido de diseño de scan (20 corridas de rampa, speedupdown ×
          velocidad × largo de tabla): ¿cuánto del ciclo queda con paso
          espacial uniforme, y cuán uniforme es realmente?

Recalcula las métricas desde los CSV crudos usando las funciones de
E517_barrido.py, así que refleja siempre la versión actual del análisis
(las corridas se guardaron con una versión anterior de `zonas_rampa`).
"""
import glob
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
FIG = REPO / "resultados" / "figuras"
spec = importlib.util.spec_from_file_location("b", REPO / "scripts/E517_barrido.py")
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
plt.rcParams.update({"font.family": "serif", "font.size": 10,
                     "axes.labelsize": 11, "figure.dpi": 120})
T_SERVO = 40e-6


def resumen(patron):
    return pd.read_csv(sorted(glob.glob(str(REPO / "resultados/barridos" / patron)))[-1])


# ══════════════════════════ TANDA A — amplitud ══════════════════════════
dfa = resumen("barrido_amplitud_*.csv")
filas = []
for _, r in dfa[dfa.ok].iterrows():
    d = pd.read_csv(REPO / "datos/raw" / f"{r.archivo}.csv")
    m = b._analisis_escalon(d.t_ms.values, d.target_um.values,
                            d.current_um.values, d.error_um.values)
    i0 = int(np.argmax(np.abs(np.diff(d.target_um.values)))) + 1
    tr = (d.t_ms.values[i0:] - d.t_ms.values[i0]) * 1e-3
    m["v_pico_um_s"] = float(np.max(np.abs(np.gradient(d.current_um.values[i0:i0+400],
                                                       tr[:400]))))
    # error ESTÁTICO ya asentado: la media del error entre 200 y 1000 ms.
    # Es lo que separa de verdad a DCO on de DCO off (ver panel c).
    xf = np.median(d.target_um.values[i0:])
    e_nm = (d.current_um.values - xf) * 1e3
    sel = (d.t_ms.values - d.t_ms.values[i0] > 200) & (d.t_ms.values - d.t_ms.values[i0] < 1000)
    m["error_estatico_nm"] = float(np.mean(e_nm[sel])) if sel.any() else np.nan
    m.update({"dco": r.dco, "rep": r.repeticion})
    filas.append(m)
A = pd.DataFrame(filas)
A["salto_abs_nm"] = A.salto_nm.abs()

fig, ax = plt.subplots(2, 2, figsize=(9.5, 7))
for dco, col in [(True, "#d62728"), (False, "#2ca02c")]:
    g = A[A.dco == dco].sort_values("salto_abs_nm")
    lab = f"DCO = {'ON' if dco else 'OFF'}"
    ax[0, 0].semilogx(g.salto_abs_nm, g.t_50_ms, "o", color=col, ms=6, label=lab)
    ax[0, 0].semilogx(g.salto_abs_nm, g.t_subida_10_90_ms, "^", color=col, ms=5,
                      alpha=0.45, mfc="none")
    ax[0, 1].loglog(g.salto_abs_nm, g.bump_lento_nm.abs(), "o", color=col, ms=6, label=lab)
    ax[1, 0].semilogx(g.salto_abs_nm, g.error_estatico_nm, "o", color=col, ms=6, label=lab)
    ax[1, 1].loglog(g.salto_abs_nm, g.v_pico_um_s, "o", color=col, ms=6, label=lab)

ax[0, 0].axhline(A.t_50_ms.median(), color="k", lw=0.8, ls="--")
ax[0, 0].set_ylim(0, 26)
ax[0, 0].set_xlabel("tamaño del escalón [nm]")
ax[0, 0].set_ylabel("tiempo de subida [ms]")
ax[0, 0].set_title(f"(a) $t_{{50}}$ (círculos) = {A.t_50_ms.median():.1f} ms constante;\n"
                   r"      $t_{10-90}$ (triángulos) no lo es", fontsize=9, loc="left")
ax[0, 0].legend(frameon=False, fontsize=8)

x = np.logspace(1, 5, 50)
ax[0, 1].plot(x, 0.4 * x ** 0.35, "k--", lw=0.8, label=r"$\propto$ escalón$^{0.35}$")
ax[0, 1].set_xlabel("tamaño del escalón [nm]"); ax[0, 1].set_ylabel("|bump| [nm]")
ax[0, 1].set_title("(b) el bump SÍ crece con el escalón (sublineal)", fontsize=9, loc="left")
ax[0, 1].legend(frameon=False, fontsize=8)

ax[1, 0].axhspan(-5, 5, color="gray", alpha=0.2, lw=0)
ax[1, 0].axhline(0, color="k", lw=0.5)
ax[1, 0].set_xlabel("tamaño del escalón [nm]")
ax[1, 0].set_ylabel("error estático (media 200–1000 ms) [nm]")
ax[1, 0].set_title("(c) POR QUÉ con DCO apagado no asienta a ±5 nm:\n"
                   "      queda un offset estático que DCO anula",
                   fontsize=9, loc="left")
ax[1, 0].legend(frameon=False, fontsize=8)

ax[1, 1].plot(x, x * 0.095, "k--", lw=0.8, label="proporcional (sin saturación)")
ax[1, 1].set_xlabel("tamaño del escalón [nm]")
ax[1, 1].set_ylabel("velocidad pico [µm/s]")
ax[1, 1].set_title("(d) sin límite de slew hasta 100 µm", fontsize=9, loc="left")
ax[1, 1].legend(frameon=False, fontsize=8)
plt.tight_layout()
plt.savefig(FIG / "barrido_03_amplitud.pdf", bbox_inches="tight", dpi=200)
plt.savefig(FIG / "barrido_03_amplitud.png", bbox_inches="tight", dpi=200)

print("TANDA A — amplitud")
print(A.groupby(["dco", "salto_abs_nm"])[
    ["t_50_ms", "t_subida_10_90_ms", "bump_lento_nm", "ts_5nm_ms", "v_pico_um_s"]
].median().round(2).to_string())

# ══════════════════════════ TANDA B — diseño de scan ═════════════════════
dfb = resumen("barrido_scan_*.csv")
filas = []
for _, r in dfb[dfb.ok].iterrows():
    d = pd.read_csv(REPO / "datos/raw" / f"{r.archivo}.csv")
    m = b._analisis_rampa(d.t_ms.values, d.target_um.values, d.current_um.values,
                          d.error_um.values, T_SERVO, int(r.wtr), int(r.rtr),
                          int(r.speedupdown), int(r.n_total))
    m.update({"wtr": r.wtr, "n_total": r.n_total, "sud": r.speedupdown,
              "rep": r.repeticion})
    filas.append(m)
B = pd.DataFrame(filas)

fig, ax = plt.subplots(1, 3, figsize=(13, 4))
base = B[B.n_total == 400]
for wtr, col in [(10, "#d62728"), (40, "#1f77b4")]:
    g = base[base.wtr == wtr].groupby("sud").median(numeric_only=True).reset_index()
    ax[0].plot(g.sud, 100 * g.frac_usable, "o-", color=col, ms=6,
               label=f"WTR={wtr}  (v≈{g.v_um_s.mean():.0f} µm/s)")
    ax[1].plot(g.sud, g.residuo_recta_usable_nm, "o-", color=col, ms=6,
               label=f"WTR={wtr}")
ax[0].set_xlabel("speedupdown [puntos]"); ax[0].set_ylabel("% del ciclo utilizable")
ax[0].set_title("(a) speedupdown se come el tramo recto", fontsize=10, loc="left")
ax[0].legend(frameon=False, fontsize=8)
ax[1].axhspan(0, 1.1, color="gray", alpha=0.25, lw=0)
ax[1].text(2, 0.45, "piso de ruido (1.1 nm rms)", fontsize=8)
ax[1].set_ylim(0, 3)
ax[1].set_xlabel("speedupdown [puntos]")
ax[1].set_ylabel("residuo a la recta, zona usable [nm rms]")
ax[1].set_title("(b) dentro de la zona usable el paso es uniforme\n"
                "      al nivel del ruido, en TODAS las configuraciones",
                fontsize=9, loc="left")
ax[1].legend(frameon=False, fontsize=8)

# (c) la regla: alargar la tabla en vez de bajar speedupdown
largos = B[(B.sud == 80) & (B.wtr == 10)].groupby("n_total").median(numeric_only=True)
ax[2].axis("off")
tab = largos[["v_um_s", "t_acel_ms", "t_constante_ms", "t_usable_ms",
              "frac_usable", "residuo_recta_usable_nm"]].round(2).reset_index()
tab.columns = ["N tabla", "v\n[µm/s]", "acel\n[ms]", "v cte\n[ms]",
               "usable\n[ms]", "frac\nusable", "residuo\n[nm]"]
tt = ax[2].table(cellText=tab.values, colLabels=tab.columns, loc="upper center",
                 cellLoc="center")
tt.auto_set_font_size(False); tt.set_fontsize(7.5); tt.scale(1, 2.4)
ax[2].set_title("(c) speedupdown=80 fijo: alargar la tabla\n"
                "      recupera la zona usable", fontsize=10, loc="left")
plt.tight_layout()
plt.savefig(FIG / "barrido_04_diseno_scan.pdf", bbox_inches="tight", dpi=200)
plt.savefig(FIG / "barrido_04_diseno_scan.png", bbox_inches="tight", dpi=200)

print("\n\nTANDA B — diseño de scan")
cols = ["v_um_s", "tau_desde_lag_ms", "t_acel_ms", "t_constante_ms", "t_usable_ms",
        "frac_usable", "dx_por_punto_nm", "residuo_recta_usable_nm", "exceso_giro_nm"]
print(B.groupby(["n_total", "wtr", "sud"])[cols].median().round(2).to_string())
print("\n[figuras] barrido_03_amplitud.pdf, barrido_04_diseno_scan.pdf")
