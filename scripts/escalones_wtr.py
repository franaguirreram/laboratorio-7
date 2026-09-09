#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
¿La platina "ve" los escalones de la wave, o los alisa?

El generador NO interpola: cambia el setpoint una vez cada WTR ciclos de
servo y se queda quieto en el medio. O sea que el comando de una rampa es
una ESCALERA de paso dx = amplitud/n_puntos y período T = WTR * T_servo.
La pregunta de este script es si al subir WTR -- darle más tiempo a cada
escalón -- la posición sensada se acomoda escalón por escalón, o si el
lazo los filtra y sale una recta igual.

Cómo se responde, sin ambigüedad:

  1. dentro del tramo de velocidad constante se le resta a la posición
     medida la RECTA que mejor la ajusta. Lo que queda es el rizado: si la
     platina resolviera los escalones, ahí tendría que aparecer un diente
     de sierra de amplitud ~dx;
  2. antes de plegar se le saca al rizado todo lo más lento que ~8
     escalones (media móvil de 8*T, que en la frecuencia del escalón vale
     cero: le saca la deriva sin tocar lo que se busca). Sin este paso el
     residuo queda dominado por la curvatura lenta del tramo -- 8 a 50 nm
     rms contra los 0.1 nm del rizado -- y el plegado devuelve una rampa
     que no tiene nada que ver con los escalones;
  3. se PLIEGAN todos los escalones del tramo (se promedia el rizado en
     función del tiempo transcurrido desde cada transición del comando).
     Promediar N escalones baja el ruido del sensor por sqrt(N). Se reporta
     el error estándar por bin: si el rizado no lo supera por 3x, no hay
     nada medido y el script lo dice;
  4. se compara con lo que predice el modelo de una sola constante de
     tiempo: simular y' = (u - y)/tau sobre el comando REAL, con
     tau = 13.1 ms [MEDIDO], y plegarlo igual;
  5. y con el piso de ruido del sensor, medido en la cola quieta de la
     misma corrida. Si el rizado no supera el ruido, no hay escalones que
     ver: el resultado es que el lazo los alisó.

Corridas usadas: mismo dx (10.05 nm), misma amplitud, mismo n_total,
speedupdown=0, y sólo cambia WTR. Es la comparación limpia: el escalón
espacial es idéntico y lo único distinto es cuánto tiempo dura.

Uso:
    python3 scripts/escalones_wtr.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
TAU_MS = 13.1        # [MEDIDO] constante de tiempo del lazo
T_SERVO_US = 40.0    # [MEDIDO] ciclo de servo del E-517

# mismas condiciones, sólo cambia WTR (dwell por escalón = WTR * 40 µs)
CORRIDAS = [
    ("E517_rampa_scan_w10_sud0_20260907_172911_r0", "#1f77b4"),
    ("E517_rampa_sud0_20260907_171001_r0",          "#2ca02c"),
    ("E517_rampa_scan_w40_sud0_20260907_172949_r0", "#d62728"),
]
# con otro dx y speedupdown=80, pero son los dwell extremos que hay medidos
EXTRAS = [
    ("E517_rampa_vel_wtr5_20260907_171015_r0",  "#9467bd"),
    ("E517_rampa_vel_wtr80_20260907_171026_r0", "#8c564b"),
]

plt.rcParams.update({"font.family": "serif", "font.size": 10,
                     "axes.labelsize": 11, "figure.dpi": 120})


def cargar(stem):
    meta = dict(l.strip().split("=", 1) for l in
                open(REPO / "datos/metadata" / (stem + "_metadata.txt"))
                if "=" in l and not l.startswith("#"))
    return pd.read_csv(REPO / "datos/raw" / (stem + ".csv")), meta


def suave(y, n):
    n = int(max(n, 1))
    if n <= 1:
        return np.asarray(y, float)
    pad = n // 2
    yp = np.pad(np.asarray(y, float), pad, mode="edge")
    return np.convolve(yp, np.ones(n) / n, mode="same")[pad:pad + len(y)]


def tramo_ida(t, tgt, wtr, rtr, frac=0.975):
    """Tramo de velocidad constante de la subida (criterio del recorrido)."""
    n = max(int(round(wtr / max(rtr, 1))), 1)
    v = suave(np.gradient(suave(tgt, 2 * n), t * 1e-3), n)
    lo, hi = np.percentile(v, 1), np.percentile(v, 99)
    m = (v - lo) / (hi - lo) >= frac
    i = np.where(m)[0]
    return max(np.split(i, np.where(np.diff(i) > 1)[0] + 1), key=len), v


def lazo_primer_orden(t_ms, u, tau_ms):
    """Integra y' = (u - y)/tau sobre el comando real (Euler, dt << tau)."""
    dt = float(np.median(np.diff(t_ms)))
    k = dt / tau_ms
    y = np.empty_like(u, dtype=float)
    y[0] = u[0]
    for i in range(1, len(u)):
        y[i] = y[i - 1] + k * (u[i - 1] - y[i - 1])
    return y


def plegar(t, resid, cambios, n_win):
    """Promedia el rizado alineando todos los escalones en su transición."""
    trozos = [resid[c:c + n_win] for c in cambios
              if c + n_win <= len(resid) and c >= 0]
    trozos = [x for x in trozos if len(x) == n_win]
    if not trozos:
        return None, None, 0
    a = np.vstack(trozos)
    return a.mean(axis=0), a.std(axis=0) / np.sqrt(len(a)), len(a)


# ---------------------------------------------------------------- análisis
fig, ax = plt.subplots(1, 3, figsize=(13, 4.2))
filas = []

for stem, color in CORRIDAS + EXTRAS:
    d, m = cargar(stem)
    t, tgt, cur = d.t_ms.values, d.target_um.values, d.current_um.values
    wtr, rtr = int(m["wtr"]), int(m["rtr"])
    dt_ms = float(np.median(np.diff(t)))
    dwell_ms = wtr * T_SERVO_US / 1000
    extra = (stem, color) in EXTRAS

    i, v = tramo_ida(t, tgt, wtr, rtr)
    ti, tg, cu = t[i], tgt[i], cur[i]

    # escalón espacial: el salto de setpoint dentro del tramo
    saltos = np.diff(tg)[np.diff(tg) != 0]
    dx_nm = float(np.median(saltos)) * 1e3

    # rizado = medida menos la recta que mejor la ajusta
    resid = (cu - np.polyval(np.polyfit(ti, cu, 1), ti)) * 1e3          # nm
    sim = lazo_primer_orden(t, tgt, TAU_MS)[i]
    resid_sim = (sim - np.polyval(np.polyfit(ti, sim, 1), ti)) * 1e3    # nm

    # piso de ruido: la cola de la corrida DESPUÉS del último cambio de
    # setpoint, más 50 ms para que el escalón final termine de asentar.
    # (Antes tomaba t > fin_del_tramo + 100 ms, que en una corrida sud0 cae
    # justo en el medio de la vuelta: daba "ruido" de 250-780 nm rms.)
    ult = np.where(np.diff(tgt) != 0)[0]
    i_q = (ult[-1] + 1 + int(round(50 / dt_ms))) if len(ult) else len(t)
    quieto = cur[i_q:]
    ruido_rms = float(np.std(quieto)) * 1e3 if len(quieto) > 100 else np.nan

    # plegado sobre los escalones del comando, después del pasa-altos
    cambios = np.where(np.diff(tg) != 0)[0] + 1
    n_win = max(int(round(dwell_ms / dt_ms)), 2)
    hp = lambda r: r - suave(r, 8 * n_win)     # media móvil de 8 escalones:
                                               # cero en la frecuencia buscada
    pl, err, n_esc = plegar(ti, hp(resid), cambios, n_win)
    pl_sim, _, _ = plegar(ti, hp(resid_sim), cambios, n_win)

    pp = float(np.ptp(pl)) if pl is not None else np.nan
    pp_sim = float(np.ptp(pl_sim)) if pl_sim is not None else np.nan
    se = float(np.mean(err)) if err is not None else np.nan
    filas.append({"corrida": stem.split("_2026")[0], "WTR": wtr, "RTR": rtr,
                  "dwell_ms": dwell_ms, "dx_nm": dx_nm, "n_esc": n_esc,
                  "rizado_pp_nm": pp, "err_est_nm": se,
                  "detectado": "sí" if pp > 3 * se else "NO",
                  "rizado_sim_nm": pp_sim,
                  "teoria_dxT/8tau": dx_nm * dwell_ms / (8 * TAU_MS),
                  "ruido_rms_nm": ruido_rms,
                  "v_um_s": dx_nm / dwell_ms})

    et = f"WTR={wtr} ({dwell_ms:.2f} ms/pto)" + (" *" if extra else "")
    # (a) zoom: 6 escalones de cada corrida, con el eje x en UNIDADES DE
    # ESCALÓN para que las tres se puedan comparar aunque duren distinto.
    # A cada trayectoria se le resta su propia recta: así el comando queda
    # como un diente de sierra de ±dx/2 y la medida, si no resolviera los
    # escalones, tiene que salir plana.
    if not extra:
        j0 = int(cambios[len(cambios) // 2]) + int(i[0])
        sl = slice(j0, j0 + 6 * n_win)
        fase = (t[sl] - t[j0]) / dwell_ms
        off = 16.0 * len(ax[0].lines) / 2      # un carril por WTR
        for y, kw in ((tgt[sl], dict(lw=1.3, drawstyle="steps-post")),
                      (cur[sl], dict(lw=0.9, alpha=0.75))):
            ax[0].plot(fase, (y - np.polyval(np.polyfit(t[sl], y, 1), t[sl])) * 1e3
                       + off, color=color, **kw)
        ax[0].text(6.05, off, et, color=color, fontsize=7.5, va="center")

    # (b) el escalón promedio
    if pl is not None:
        tau_win = np.arange(n_win) * dt_ms
        ls = ":" if extra else "-"
        ax[1].plot(tau_win / dwell_ms, pl - pl.mean(), color=color, lw=1.5, ls=ls,
                   label=f"{et}, {n_esc} escalones")
        ax[1].fill_between(tau_win / dwell_ms, pl - pl.mean() - err,
                           pl - pl.mean() + err, color=color, alpha=0.15, lw=0)
        if not extra:
            ax[1].plot(tau_win / dwell_ms, pl_sim - pl_sim.mean(), color=color,
                       lw=0.9, ls="--", alpha=0.6)

tab = pd.DataFrame(filas)
print("\n" + tab.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
print(f"\n(*) las dos últimas tienen speedupdown=80 y otro dx: van sólo para "
      f"tener los dwell extremos.")
print(f"\ndwell necesario para que la platina alcance a asentar cada escalón:")
print(f"   ~tau  = {TAU_MS:.1f} ms  ->  WTR = {TAU_MS*1000/T_SERVO_US:.0f}")
print(f"   t_conv = 33 ms      ->  WTR = {33*1000/T_SERVO_US:.0f}")
print(f"   contra los WTR medidos, de {tab.WTR.min()} a {tab.WTR.max()}.")

# (c) rizado contra dwell, medido / simulado / piso de ruido
ax[2].plot(tab.dwell_ms, tab.rizado_pp_nm, "o-", color="k", lw=1.2,
           label="rizado medido (plegado)")
ax[2].plot(tab.dwell_ms, tab.rizado_sim_nm, "s--", color="#d62728", lw=1.2,
           label=r"simulado, $\tau$ = 13.1 ms")
ax[2].axhline(np.nanmedian(tab.ruido_rms_nm), color="0.5", ls=":", lw=1.2,
              label="ruido rms del sensor")
ax[2].plot(tab.dwell_ms, tab["teoria_dxT/8tau"], "-", color="#ff7f0e", lw=1.0,
           label=r"teoría  $dx\,T/8\tau$")
ax[2].plot(tab.dwell_ms, tab.dx_nm, "^-", color="#1f77b4", lw=1.0, alpha=0.6,
           label="dx (rizado si resolviera cada escalón)")
ax[2].axvline(TAU_MS, color="k", ls="-.", lw=0.8)
ax[2].text(TAU_MS * 0.85, 0.022, r"dwell = $\tau$" + f"\n(WTR = {TAU_MS*1000/T_SERVO_US:.0f})",
           fontsize=7, ha="right", va="bottom")
ax[2].set_xscale("log"); ax[2].set_yscale("log")
ax[2].set_xlabel("dwell por escalón [ms]")
ax[2].set_ylabel("amplitud [nm]")
ax[2].legend(frameon=False, fontsize=7, loc="upper left",
             bbox_to_anchor=(0.0, 0.88))
ax[2].set_title("(c) el rizado nunca se acerca a dx: la platina no ve los escalones",
                fontsize=9, loc="left")

ax[0].set_xlabel("escalones del comando")
ax[0].set_ylabel("posición − su propia recta [nm]")
ax[0].set_xlim(-0.2, 7.4)
ax[0].set_title("(a) seis escalones: el comando es un diente de sierra de ±dx/2\n"
                "     (escalonado) y la medida sale plana (línea fina)",
                fontsize=9, loc="left")

ax[1].axhline(0, color="0.7", lw=0.5)
ax[1].set_xlabel("fase dentro del escalón (0 = transición, 1 = próxima)")
ax[1].set_ylabel("rizado promediado [nm]")
ax[1].legend(frameon=False, fontsize=7)
ax[1].set_title(r"(b) escalón promedio: medido (llena) vs simulado con $\tau$"
                " (rayada)", fontsize=9, loc="left")

plt.tight_layout()
salida = REPO / "resultados/figuras/escalones_wtr.pdf"
plt.savefig(salida, bbox_inches="tight", dpi=200)
plt.savefig(salida.with_suffix(".png"), bbox_inches="tight", dpi=200)
print(f"\n[figura] {salida.relative_to(REPO)} (+ .png)")
plt.show()
