#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Análisis OFF-LINE de las corridas del 2026-09-01 (no toca el hardware).

Responde tres preguntas con los datos que ya están en datos/raw/:

  1. ¿Qué parámetro fija realmente la velocidad?  -> WTR (y solo WTR).
     T_SERVO_US en los scripts de adquisición es una CONSTANTE DE
     SOFTWARE: no se le manda al controlador, solo se usa para armar la
     columna t_ms del CSV. Las corridas donde se barrió T_SERVO_US son
     físicamente idénticas entre sí; lo único que cambió es la etiqueta
     temporal del eje x.

  2. ¿Cuál es el período de servo real? -> 40 µs (25 kHz).
     Verificación independiente del manual: en el ruido de posición con
     la platina quieta aparece una línea espectral aislada que cae en
     50.0 Hz si y solo si dt = 40 µs (red eléctrica). Con dt = 10 µs
     caería en 200 Hz, que no corresponde a ninguna fuente física.

  3. ¿Qué limita el seguimiento? -> el ancho de banda de LAZO CERRADO,
     tau ~ 10 ms (f_c ~ 16 Hz). Ni los 25 kHz del servo ni los 60 MHz
     del DSP. El error de seguimiento es, con mucho, un RETRASO PURO:
     e = v * tau. Es determinista y por lo tanto corregible.

Uso:  ~/python-envs/pi/bin/python3 scripts/analisis_velocidad_y_ancho_de_banda.py
"""

import re
import glob
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# --- Constante física del controlador -------------------------------------
# [MEDIDO] qSPA(1, 0x0E000200) según README; CONFIRMADO acá de forma
# independiente por la línea de 50 Hz en el ruido (ver figura 4).
T_SERVO = 40e-6      # s

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "datos" / "raw"
META = REPO / "datos" / "metadata"
FIG = REPO / "resultados" / "figuras"
FIG.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    'font.family': 'serif', 'font.size': 9,
    'axes.labelsize': 10, 'xtick.labelsize': 8, 'ytick.labelsize': 8,
    'legend.fontsize': 8, 'figure.dpi': 130, 'axes.grid': True,
    'grid.alpha': 0.25, 'grid.linewidth': 0.5,
})


# %% ---------------------------------------------------------------------
# Carga: metadata + CSV, con el eje temporal RECONSTRUIDO a dt = RTR*40us
# ------------------------------------------------------------------------
def cargar(prefijo):
    filas = []
    for f in sorted(glob.glob(str(META / f"{prefijo}_2026*_metadata.txt"))):
        d = dict(re.findall(r'(\w+)=([^\s]+)', open(f).read()))
        ts = re.search(r'(\d{8}_\d{6})', f).group(1)
        csv = RAW / f"{prefijo}_{ts}.csv"
        if not csv.exists():
            continue
        df = pd.read_csv(csv)
        wtr, rtr = int(d['WTR']), int(d['RTR_VAL'])
        dt = rtr * T_SERVO
        filas.append(dict(
            ts=ts, meta=d, df=df, WTR=wtr, RTR=rtr, dt=dt,
            t=np.arange(len(df)) * dt,
            tgt=df.target_um.values, cur=df.current_um.values,
            err=df.error_um.values,
        ))
    return filas


def metricas_rampa(r):
    """Velocidad real de la rampa y error en el tramo de velocidad constante."""
    wtr, dt = r['WTR'], r['dt']
    tgt, err = r['tgt'], r['err']
    # El target es una ESCALERA: cambia una vez cada WTR ciclos de servo.
    # Hay que suavizar con una ventana de WTR antes de derivar, o la
    # derivada mide el salto instantáneo y no la velocidad media.
    k = max(wtr, 3)
    suave = np.convolve(tgt, np.ones(k) / k, mode='same')
    v = np.gradient(suave, dt)
    vmax = np.percentile(np.abs(v), 90)
    m = np.abs(v) > 0.85 * vmax
    m[:k] = m[-k:] = False
    paso = np.abs(np.diff(tgt))
    return dict(
        v_um_s=vmax,
        paso_nm=np.median(paso[paso > 1e-9]) * 1e3 if (paso > 1e-9).any() else np.nan,
        dwell_us=wtr * T_SERVO * 1e6,
        e_cv_nm=np.median(np.abs(err[m])) * 1e3,
        e_max_nm=np.max(np.abs(err)) * 1e3,
        dur_ms=len(tgt) * dt * 1e3,
    )


rampas = cargar("E517_ida_vuelta_speedupdown")
for r in rampas:
    r.update(metricas_rampa(r))
    r['A'] = float(r['meta']['AMPLITUD'])
    r['Tlabel'] = float(r['meta']['T_SERVO_US'])
    r['N'] = int(r['meta']['N_TOTAL'])
    r['SUD'] = int(r['meta']['SPEEDUPDOWN'])

T = pd.DataFrame([{k: r[k] for k in
                   ('ts', 'A', 'Tlabel', 'WTR', 'N', 'SUD', 'dur_ms', 'dwell_us',
                    'paso_nm', 'v_um_s', 'e_cv_nm', 'e_max_nm')} for r in rampas])
T.to_csv(REPO / "resultados" / "tabla_corridas_20260901.csv", index=False)
print(T.sort_values('v_um_s').to_string(index=False))


# %% ---------------------------------------------------------------------
# FIGURA 1 — T_SERVO_US no hace nada; WTR lo hace todo
# ------------------------------------------------------------------------
fig, ax = plt.subplots(1, 2, figsize=(7.4, 3.1))

# (a) Normalizado por grupo: si T_SERVO_US hiciera algo, las series
# tendrían pendiente. Son planas dentro de la dispersión entre repeticiones.
# Dispersión entre REPETICIONES con parámetros idénticos, para tener con
# qué comparar: (A=0.5, WTR=20, T=40) se repitió 3 veces, (A=0.02, WTR=20,
# T=1) también.
reps = [g.e_cv_nm.std() / g.e_cv_nm.mean()
        for _, g in T.groupby(['A', 'WTR', 'Tlabel']) if len(g) >= 3]
cv_rep = float(np.mean(reps))
for (A, wtr), g in T.groupby(['A', 'WTR']):
    if g.Tlabel.nunique() < 3:
        continue
    g = g.groupby('Tlabel', as_index=False).e_cv_nm.mean().sort_values('Tlabel')
    ax[0].plot(g.Tlabel, g.e_cv_nm / g.e_cv_nm.mean(), 'o-', ms=4, lw=1,
               label=f'A={A} µm, WTR={wtr}')
ax[0].axhline(1.0, color='k', lw=0.8, ls='--')
ax[0].axhspan(1 - cv_rep, 1 + cv_rep, color='0.6', alpha=0.18, zorder=0)
ax[0].text(60, 1 + cv_rep + 0.02, f'dispersión entre\nrepeticiones (±{cv_rep*100:.0f} %)',
           fontsize=7, color='0.35')
ax[0].set_ylim(1 - 3 * cv_rep, 1 + 3 * cv_rep)
ax[0].set_xlabel('T_SERVO_US puesto en el script [µs]')
ax[0].set_ylabel('error / error medio del grupo')
ax[0].set_title('(a) T_SERVO_US: variable nula\n(no se le manda al controlador)', fontsize=9)
ax[0].legend(frameon=False, ncol=1, loc='lower left')

# (b) Mismo N y mismo speedupdown para que sea comparable punto a punto.
base = T[(T.N == 400) & (T.SUD == 40)]
for A, g in base[base.A.isin([0.05, 0.1, 0.5])].groupby('A'):
    g = g.groupby('WTR', as_index=False).e_cv_nm.mean().sort_values('WTR')
    ax[1].loglog(g.WTR, g.e_cv_nm, 's-', ms=4, lw=1.1, label=f'A={A} µm')
ww = np.array([1, 20])
ax[1].loglog(ww, 40 * (10 / ww), 'k:', lw=0.9, label=r'$\propto 1/$WTR')
ax[1].set_xlabel('WTR [ciclos de servo por punto de wave]')
ax[1].set_ylabel('error mediano en vel. constante [nm]')
ax[1].set_title('(b) WTR: el único knob de velocidad\n' + r'$v = \Delta x\,/\,($WTR$\times 40\,\mu$s$)$', fontsize=9)
ax[1].legend(frameon=False)

fig.tight_layout()
fig.savefig(FIG / "analisis_01_TSERVO_es_variable_nula.pdf", bbox_inches='tight')
fig.savefig(FIG / "analisis_01_TSERVO_es_variable_nula.png", bbox_inches='tight', dpi=200)


# %% ---------------------------------------------------------------------
# FIGURA 2 — El error de seguimiento colapsa en e = v * tau
# ------------------------------------------------------------------------
# Se descartan las corridas demasiado cortas para alcanzar el régimen
# estacionario (duración total < 5*tau) y las dominadas por el piso de ruido.
TAU = 10.5e-3   # s, ajustado abajo
val = T[(T.dur_ms > 50) & (T.e_cv_nm > 12)]
tau_fit = np.median(val.e_cv_nm * 1e-3 / val.v_um_s)

fig, ax = plt.subplots(figsize=(4.6, 3.6))
sc = ax.scatter(T.v_um_s, T.e_cv_nm, c=np.log10(T.WTR), cmap='viridis',
                s=26, zorder=3, edgecolor='k', linewidth=0.3)
vv = np.logspace(-1, 3.6, 50)
ax.plot(vv, vv * tau_fit * 1e3, 'k--', lw=1,
        label=rf'$e = v\,\tau$,  $\tau$ = {tau_fit*1e3:.1f} ms')
ax.axhline(1.7, color='crimson', lw=1, ls=':', label='piso de ruido 1.7 nm')
ax.set_xscale('log'); ax.set_yscale('log')
ax.set_xlabel(r'velocidad real del scan  $v$ [µm/s]')
ax.set_ylabel('error de seguimiento [nm]')
ax.set_title('Todo el error es un retraso puro', fontsize=9)
cb = fig.colorbar(sc, ax=ax); cb.set_label(r'$\log_{10}$ WTR', fontsize=8)
ax.legend(frameon=False, loc='upper left')
fig.tight_layout()
fig.savefig(FIG / "analisis_02_error_vs_velocidad.pdf", bbox_inches='tight')
fig.savefig(FIG / "analisis_02_error_vs_velocidad.png", bbox_inches='tight', dpi=200)
print(f"\n[fit] tau = {tau_fit*1e3:.2f} ms  ->  f_c = {1/(2*np.pi*tau_fit):.1f} Hz")


# %% ---------------------------------------------------------------------
# FIGURA 3 — Corregir el retraso: el error se derrumba
# ------------------------------------------------------------------------
def mejor_lag(r, kmax=700):
    n = len(r['tgt'])
    mejor = (0, np.inf)
    for k in range(kmax):
        res = r['cur'][k:] - r['tgt'][:n - k]
        m = slice(int(0.1 * len(res)), int(0.9 * len(res)))
        s = np.sqrt(np.mean(res[m] ** 2))
        if s < mejor[1]:
            mejor = (k, s)
    return mejor


demo = {r['ts']: r for r in rampas}
casos = ['20260901_180400', '20260901_183137', '20260901_175206']
fig, axes = plt.subplots(2, len(casos), figsize=(8.4, 4.6), sharex='col')
for j, ts in enumerate(casos):
    r = demo[ts]
    k, rms_c = mejor_lag(r)
    n = len(r['tgt'])
    t = r['t'] * 1e3
    c = np.mean(r['tgt'])
    axes[0, j].plot(t, (r['tgt'] - c) * 1e3, lw=1.0, color='#1f77b4', label='comandada')
    axes[0, j].plot(t, (r['cur'] - c) * 1e3, lw=0.8, color='#d62728', label='real')
    axes[0, j].set_title(f"A={r['A']} µm, WTR={r['WTR']}\n"
                         f"v = {r['v_um_s']:.3g} µm/s", fontsize=8)
    e0 = (r['cur'] - r['tgt']) * 1e3
    ec = (r['cur'][k:] - r['tgt'][:n - k]) * 1e3
    axes[1, j].plot(t, e0, lw=0.7, color='k', label='crudo')
    axes[1, j].plot(t[:n - k], ec, lw=0.7, color='#2ca02c',
                    label=f'lag {k*r["dt"]*1e3:.1f} ms corregido')
    axes[1, j].set_xlabel('t [ms]')
    axes[1, j].set_title(f'RMS: {np.sqrt(np.mean(e0**2)):.0f} nm  '
                         r'$\rightarrow$' + f'  {rms_c*1e3:.1f} nm',
                         fontsize=8, pad=3)
    if j == 0:
        axes[1, j].legend(frameon=False, fontsize=7, loc='lower left')
    # sobrepico en el retorno: el integrador tarda ~tau en desarmarse
    ipk = int(np.argmax(np.abs(r['cur'] - np.mean(r['tgt']))))
    ov = (np.abs(r['cur'][ipk] - np.mean(r['tgt'])) - r['A']) * 1e3
    # El sobrepico NO escala con v: con speedupdown=40 la desaceleración
    # dura 32 ms > tau, así que el lazo alcanza a frenar en parte. Es lo
    # que sobra de eso, y es lo que hay que sacar de la zona de interés.
    axes[0, j].annotate(f'sobrepico {ov:.0f} nm',
                        xy=(t[ipk], (r['cur'][ipk] - c) * 1e3),
                        xytext=(0.05, 0.62), textcoords='axes fraction', fontsize=6.5,
                        arrowprops=dict(arrowstyle='->', lw=0.6))
    if j == 0:
        axes[0, j].set_ylabel(r'$x-x_c$ [nm]')
        axes[1, j].set_ylabel('error [nm]')
        axes[0, j].legend(frameon=False, fontsize=7)
fig.tight_layout()
fig.savefig(FIG / "analisis_03_correccion_de_lag.pdf", bbox_inches='tight')
fig.savefig(FIG / "analisis_03_correccion_de_lag.png", bbox_inches='tight', dpi=200)


# %% ---------------------------------------------------------------------
# FIGURA 4 — Escalón, piso de ruido y la línea de 50 Hz
# ------------------------------------------------------------------------
esc = cargar("E517_step_response")
fig, ax = plt.subplots(1, 3, figsize=(9.4, 3.0))

vistos = set()
for r in sorted(esc, key=lambda z: -abs(float(z['meta']['AMPLITUD_ESCALON']))):
    if r['WTR'] != 20:
        continue
    tgt, cur = r['tgt'], r['cur']
    i = int(np.argmax(np.abs(np.diff(tgt)))) + 1
    y0 = np.median(cur[max(0, i - 300):i - 2])
    S = np.median(cur[-400:]) - y0
    lab = f'{abs(S)*1e3:.0f} nm' if abs(S) < 1 else f'{abs(S):.0f} µm'
    # Los escalones <= 20 nm quedan enterrados en el ruido de 1.7 nm: al
    # normalizar por S dan curvas de ±30 % que NO son dinámica del servo.
    if abs(S) < 0.15 or lab in vistos:
        continue
    vistos.add(lab)
    y = (cur[i:] - y0) / S
    t = np.arange(len(y)) * r['dt'] * 1e3
    ax[0].plot(t, y, lw=0.9, label=lab)
ax[0].axhline(1, color='gray', lw=0.5, ls='--')
ax[0].axhspan(0.99, 1.01, color='0.6', alpha=0.2, zorder=0)
ax[0].annotate('sobrepico 2-3 %, cola lenta ~100 ms',
               xy=(55, 1.03), xytext=(85, 1.22), fontsize=7,
               arrowprops=dict(arrowstyle='->', lw=0.6))
ax[0].set_xlim(0, 200); ax[0].set_ylim(-0.05, 1.35)
ax[0].set_xlabel('t desde el escalón [ms]'); ax[0].set_ylabel('posición normalizada')
ax[0].set_title('(a) respuesta al escalón\n$t_{10-90}\\approx$ 18 ms para todo tamaño', fontsize=9)
ax[0].legend(frameon=False, title='amplitud', title_fontsize=7, fontsize=7)

# ruido: cola ya asentada de los escalones chicos
segs = []
for r in esc:
    if r['WTR'] != 20:
        continue
    s = r['cur'][-4000:] * 1e3
    x = np.arange(len(s))
    segs.append(s - np.polyval(np.polyfit(x, s, 2), x))

P = np.zeros(len(segs[0]) // 2 + 1)
for sg in segs:
    P += np.abs(np.fft.rfft(sg * np.hanning(len(sg)))) * 4 / len(sg)
P /= len(segs)
f40 = np.fft.rfftfreq(len(segs[0]), 40e-6)
ax[1].semilogy(f40, P, lw=0.8, color='k')
kpk = np.argmax(np.where((f40 > 30) & (f40 < 400), P, 0))
ax[1].plot(f40[kpk], P[kpk], 'v', color='crimson', ms=7)
ax[1].annotate(f'{f40[kpk]:.0f} Hz, {P[kpk]:.1f} nm\n= red eléctrica',
               xy=(f40[kpk], P[kpk]), xytext=(120, P[kpk] * 0.75), fontsize=7.5,
               color='crimson', arrowprops=dict(arrowstyle='->', lw=0.7, color='crimson'))
ax[1].set_xlim(0, 400)
sec2 = ax[1].secondary_xaxis('top', functions=(lambda x: x * 4, lambda x: x / 4))
sec2.set_xlabel('la MISMA línea si dt fuera 10 µs [Hz]', fontsize=7, color='0.4')
sec2.tick_params(labelsize=7, colors='0.4')
ax[1].set_xlabel('frecuencia [Hz]  (con dt = 40 µs)')
ax[1].set_ylabel('amplitud [nm]')
ax[1].set_title('(b) ruido con la platina quieta:\nla línea cae en 50 Hz solo si dt = 40 µs', fontsize=9)

Ns = np.unique(np.round(np.logspace(0, 3.4, 22)).astype(int))
sig = [np.mean([s[:len(s) // N * N].reshape(-1, N).mean(1).std() for s in segs])
       for N in Ns]
ax[2].loglog(Ns * T_SERVO * 1e3, sig, 'o-', ms=3.5, lw=1, color='k')
ax[2].loglog(Ns * T_SERVO * 1e3, sig[0] / np.sqrt(Ns), '--', lw=0.8,
             color='gray', label=r'$1/\sqrt{N}$ (ruido blanco)')
ax[2].axvline(20, color='#1f77b4', lw=1, ls=':')
ax[2].text(21, 1.2, '1 período\nde 50 Hz', fontsize=7, color='#1f77b4')
ax[2].set_xlabel('tiempo de promediado por píxel [ms]')
ax[2].set_ylabel(r'$\sigma$ de posición [nm]')
ax[2].set_title('(c) promediar no ayuda hasta 20 ms', fontsize=9)
ax[2].legend(frameon=False, fontsize=7)

fig.tight_layout()
fig.savefig(FIG / "analisis_04_escalon_ruido_50Hz.pdf", bbox_inches='tight')
fig.savefig(FIG / "analisis_04_escalon_ruido_50Hz.png", bbox_inches='tight', dpi=200)


# %% ---------------------------------------------------------------------
# FIGURA 5 — Presupuesto de los 8192 puntos para un raster
# ------------------------------------------------------------------------
# Regla: con RTR = WTR el data recorder guarda exactamente UNA muestra por
# punto de wave -> el frame entero entra en el recorder mientras
# lineas * px_por_linea <= 8192.
fig, ax = plt.subplots(1, 2, figsize=(7.6, 3.2))

px = np.array([16, 32, 64, 128, 256, 512, 1024])
ax[0].loglog(px, 8192 / px, 'o-', ms=4, lw=1.3, color='k',
             label='data recorder: 8192 muestras\n(RTR = WTR -> 1 muestra/píxel)')
ax[0].fill_between(px, 1, 8192 / px, alpha=0.13, color='green')
ax[0].axhline(8192, color='#1f77b4', lw=1.2, ls='--',
              label='wave table con WGC:\nsolo 1 línea + 1 rampa Y\n(no limita el frame)')
for n in [64, 90, 128]:
    ax[0].plot(n, 8192 / n, '*', color='crimson', ms=11, zorder=4)
    ax[0].annotate(f'{n}x{int(8192/n)}', (n, 8192 / n), textcoords='offset points',
                   xytext=(7, 5), fontsize=7.5, color='crimson')
ax[0].text(20, 3, 'frame entero\ngrabado', fontsize=7.5, color='darkgreen')
ax[0].set_ylim(1, 2e4)
ax[0].set_xlabel('píxeles por línea'); ax[0].set_ylabel('líneas por frame')
ax[0].set_title('(a) los dos presupuestos son distintos', fontsize=9)
ax[0].legend(frameon=False, fontsize=6.8, loc='upper right')

# Tiempo de frame y error de lag vs dwell, para un frame de 8192 px
dwell_ms = np.logspace(-1.4, 1.5, 200)
paso_nm = 20.0    # nm de paso entre píxeles (ejemplo: 128 px sobre 2.56 µm)
lag_nm = paso_nm * (tau_fit * 1e3) / dwell_ms
ax[1].loglog(dwell_ms, lag_nm, 'k-', lw=1.2, label=rf'lag $=\Delta x\,\tau/t_{{dwell}}$')
ax[1].axhline(paso_nm / 2, color='crimson', ls='--', lw=1, label='medio píxel')
ax[1].axhline(1.7, color='#1f77b4', ls=':', lw=1, label='piso de ruido')
sec = ax[1].secondary_xaxis('top', functions=(lambda d: d * 8192 / 1000,
                                              lambda s: s * 1000 / 8192))
sec.set_xlabel('tiempo de frame (8192 px) [s]', fontsize=8)
ax[1].set_xlabel('dwell por píxel [ms]')
ax[1].set_ylabel(f'error [nm]  (paso = {paso_nm:.0f} nm)')
ax[1].set_title('(b) por qué hay que CORREGIR el lag,\nno esperarlo', fontsize=9)
ax[1].legend(frameon=False, fontsize=7)

fig.tight_layout()
fig.savefig(FIG / "analisis_05_presupuesto_8192_puntos.pdf", bbox_inches='tight')
fig.savefig(FIG / "analisis_05_presupuesto_8192_puntos.png", bbox_inches='tight', dpi=200)

print(f"\n[ok] figuras en {FIG}")
