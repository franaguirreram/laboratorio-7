#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zoom al arranque del escalón, en función de la amplitud. No toca el hardware.

La pregunta: ¿el lazo es lineal en amplitud? Y si no, ¿dónde deja de serlo?

Si es lineal, las respuestas NORMALIZADAS de todos los saltos —de 10 nm a
100 µm, cuatro décadas— tienen que caer una arriba de otra. Cualquier
separación entre ellas es no-linealidad, y el panel donde se separan dice de
qué tipo:

  · se separan en el ARRANQUE  → tiempo muerto que no escala (electrónica,
                                  cuantización, umbral)
  · se separan en la PENDIENTE → saturación de velocidad del amplificador
  · se separan solo abajo      → el salto se hundió en el ruido: es el piso
    de medición, no física

Levanta `ampfino_*` (barrido_amplitud_escalon.py) y, si no hay, los `amp_*`
del 2026-09-07 para que se pueda mirar algo desde ya.

Uso:  ~/python-envs/pi/bin/python3 scripts/analisis_escalon_amplitud.py
"""
from pathlib import Path
import re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
RAW, META, FIG = REPO/"datos"/"raw", REPO/"datos"/"metadata", REPO/"resultados"/"figuras"
T_SERVO, T_INT = 40e-6, 50.0
trapz = getattr(np, "trapezoid", None) or np.trapz
plt.rcParams.update({'font.family':'serif','font.size':9,'figure.dpi':120,
                     'axes.grid':True,'grid.alpha':.25,'grid.linewidth':.5})


def cargar(csv):
    d = {}
    for ln in open(META/f"{csv.stem}_metadata.txt", encoding="utf-8", errors="replace"):
        if "=" in ln and not ln.startswith("#"):
            k, v = ln.split("=", 1); d[k.strip()] = v.strip()
    if d.get("dco") == "True":
        return None
    rtr = int(d["rtr"]); dt = rtr*T_SERVO*1e3
    df = pd.read_csv(csv)
    tg, cu = df.target_um.values*1e3, df.current_um.values*1e3
    n = len(tg)
    i = int(np.argmax(np.abs(np.diff(tg[:n//2])))) + 1
    S = tg[i] - tg[i-1]
    if abs(S) < 5:
        return None
    t = (np.arange(n)-i)*dt
    # Normalización: (posición - base) / (final - base), con base y final
    # medidos, no comandados.
    #
    # Por qué NO extrapolar una recta ajustada al baseline: con n_pre=50 el
    # tramo previo dura 2 ms, y extrapolar su pendiente 50 ms adelante
    # multiplica el error por 25. Sobre un escalón de 10 nm eso daba
    # dispersiones de 70 ms en tau. Y por qué NO dividir por el salto
    # COMANDADO: cualquier error de escala del lazo entra directo en el
    # nivel final, y el área es lineal en ese nivel — un 2 % de más en y
    # se lleva 1 ms de tau.
    #
    # Dividir por el salto LOGRADO fuerza y→1 por construcción y mata las
    # dos cosas a la vez. El precio: este análisis es ciego a la ganancia
    # estática (el factor 0.9904), que es otra medición.
    base = float(np.median(cu[:i]))
    sigma = float(np.std(cu[:i] - base)) if i > 5 else float(np.std(cu[:i]))
    tardio = t >= max(150.0, t[-1]*0.6)
    if tardio.sum() < 50:
        return None                       # ventana corta: no hay nivel final
    final = float(np.median(cu[tardio]))
    if abs(final - base) < 3:
        return None
    return dict(t=t, y=(cu-base)/(final-base), S_nm=abs(S), dt=dt, sigma=sigma,
                salto_um=round(abs(S)/1e3, 4), nombre=csv.stem,
                n_pre=int(d.get("n_pre", 50)))


ARCH = sorted(RAW.glob("E517_escalon_ampfino_*.csv"))
FUENTE = "ampfino (barrido nuevo)"
if not ARCH:
    ARCH = sorted(RAW.glob("E517_escalon_amp_*.csv"))
    FUENTE = "amp_* del 2026-09-07 (todavía sin correr el barrido nuevo)"
CORR = [c for c in (cargar(f) for f in ARCH) if c is not None]
# Si hay corridas con baseline largo (n_pre >= 500), usar SOLO ésas: mezclarlas
# con las de n_pre=50 promedia dos calidades distintas y el promedio hereda la
# peor. Con 2 ms de baseline no se ve un ciclo de 50 Hz.
LARGAS = [c for c in CORR if c["n_pre"] >= 500]
if LARGAS:
    print(f"usando {len(LARGAS)} corridas con baseline largo "
          f"(se ignoran {len(CORR)-len(LARGAS)} con n_pre=50)")
    CORR = LARGAS
print(f"fuente: {FUENTE}   |   {len(CORR)} corridas con DCO off\n")
if not CORR:
    raise SystemExit(
        f"no hay corridas utilizables en {RAW}.\n"
        "Correr primero scripts/barrido_amplitud_escalon.py, o revisar que "
        "los archivos tengan DCO off y una ventana de al menos 150 ms "
        "después del escalón.")

# --- promediar las repeticiones de cada salto, en la grilla más fina ------
GRUPOS = {}
for c in CORR:
    GRUPOS.setdefault(c["salto_um"], []).append(c)

tg_ref = np.arange(-2, 60, 0.04)
PROM, filas = {}, []
for salto, cs in sorted(GRUPOS.items()):
    ys = np.array([np.interp(tg_ref, c["t"], c["y"]) for c in cs])
    y = ys.mean(axis=0)
    w = (tg_ref >= 0) & (tg_ref <= T_INT)
    tau = trapz(1-y[w], tg_ref[w])
    disp = [trapz(1-np.interp(tg_ref[w], c["t"], c["y"]), tg_ref[w]) for c in cs]
    sig = np.mean([c["sigma"] for c in cs])
    # dónde la posición se despega: primera muestra fuera de ±5 sigma
    fuera = (tg_ref >= 0) & (np.abs(y*salto*1e3) > 5*sig)
    PROM[salto] = dict(t=tg_ref, y=y, n=len(cs), sigma=sig)
    filas.append(dict(salto_um=salto, n=len(cs), sigma_nm=sig,
                      snr=salto*1e3/sig, tau_area=tau,
                      disp_ms=np.std(disp) if len(disp) > 1 else np.nan,
                      t_despegue=tg_ref[np.argmax(fuera)] if fuera.any() else np.nan))
TAB = pd.DataFrame(filas)
print(TAB.round(2).to_string(index=False))

# --- figura --------------------------------------------------------------
fig, ax = plt.subplots(2, 2, figsize=(11, 7.2))
cmap = plt.cm.viridis(np.linspace(0, .9, len(PROM)))

for (salto, g), col in zip(sorted(PROM.items()), cmap):
    et = f"{salto*1e3:.0f} nm" if salto < 1 else f"{salto:g} µm"
    m = (g["t"] > -2) & (g["t"] < 60)
    ax[0, 0].plot(g["t"][m], g["y"][m], color=col, lw=1.1, label=f"{et} (n={g['n']})")
    m = (g["t"] > -0.5) & (g["t"] < 5)
    ax[0, 1].plot(g["t"][m], g["y"][m]*100, color=col, lw=1.2)
    ax[1, 0].plot(g["t"][m], g["y"][m]*salto*1e3, color=col, lw=1.2)
    ax[1, 0].axhline(5*g["sigma"], color=col, lw=.5, ls=":")

ax[0, 0].set(xlabel="t [ms]", ylabel="posición normalizada",
             title="(a) ¿colapsan? si el lazo es lineal, sí")
ax[0, 0].legend(fontsize=6, ncol=2, loc="lower right")
ax[0, 1].set(xlabel="t [ms]", ylabel="% del salto", xlim=(-0.5, 5), ylim=(-1, 12),
             title="(b) zoom al arranque, normalizado")
ax[0, 1].axhline(0, color="0.7", lw=.6); ax[0, 1].axvline(0, color="0.7", lw=.6)
ax[1, 0].set_yscale("symlog", linthresh=1)
ax[1, 0].set(xlabel="t [ms]", ylabel="desplazamiento [nm]", xlim=(-0.5, 5),
             title="(c) el mismo zoom en nm: punteado = 5σ del ruido")
ax[1, 0].axhline(0, color="0.7", lw=.6); ax[1, 0].axvline(0, color="0.7", lw=.6)

b = ax[1, 1]
b.errorbar(TAB.salto_um*1e3, TAB.tau_area, yerr=TAB.disp_ms, fmt="C0o-", ms=5,
           lw=1, capsize=3, label=r"escalón: $\int(1-y)dt$")
try:
    R = pd.read_csv(sorted((REPO/"resultados"/"barridos").glob("barrido_tau_rampa_2026*.csv"))[-1])
    b.plot(R.amplitud_um*2e3, np.abs(R.error_mediano_nm)/R.v_um_s, "C3s", ms=5,
           label=r"rampa: $e_{ss}/v$ (misma excursión)")
except Exception:
    pass
b.set(xscale="log", xlabel="tamaño del escalón / excursión [nm]",
      ylabel=r"$\tau$ [ms]", title="(d) ¿τ depende de la amplitud?")
b.legend(fontsize=7)

fig.tight_layout()
out = FIG/"escalon_amplitud_zoom.png"
fig.savefig(out, dpi=135)
print(f"\nfigura: {out}")
