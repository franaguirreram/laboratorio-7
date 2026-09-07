#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Análisis OFF-LINE del TIEMPO DE ASENTAMIENTO — corridas de escalón del
2026-09-01 y 2026-09-02. No toca el hardware.

Complementa (no reemplaza) a analisis_velocidad_y_ancho_de_banda.py, que
se ocupa de rampas y ancho de banda. Acá solo escalones.

Las tres preguntas que responde:

  1. ¿Las corridas del 0902 son mejores que las del 0901?
     Parcialmente. Lo que mejoró: T_SERVO_US=40 hace que la columna t_ms
     del CSV sea por fin correcta, y aparece la variable DCO. Lo que no:
     variar N_TOTAL con WTR=1 y RTR=1 solo ACORTA la ventana de
     observación; 8 de las 11 corridas nuevas tienen ventanas de 16-80 ms,
     más cortas que el asentamiento que se quiere medir.

  2. ¿Qué knob controla la ventana? RTR, no WTR ni N_TOTAL.
         ventana = 8192 x RTR x 40 us        dt = RTR x 40 us
     Con RTR=1 (los dos días) la ventana está topeada en 327.68 ms sin
     importar nada más.

  3. ¿DCO importa? Sí, y mucho: es el efecto más grande medido hasta
     ahora sobre el asentamiento. Con DCO=True aparece una excursión
     lenta de 25-100 nm que pica a ~55-80 ms; con DCO=False casi
     desaparece y el asentamiento a +-5 nm baja ~3x.

Uso:  ~/python-envs/pi/bin/python3 scripts/analisis_asentamiento.py
"""

import re
import glob
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

T_SERVO = 40e-6      # s  [MEDIDO qSPA 0x0E000200; confirmado por la línea de 50 Hz]

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

# El estado de DCO no quedó en la metadata: se reconstruye del nombre del
# PDF de la figura. Dos convenciones conviven:
#   día 2 (el script ya arma el nombre con DCO adentro): _DCOTrue.pdf / _DCOFalse.pdf
#   día 1 (anotado a mano sobre corridas puntuales, después de la sesión):
#       _DCO.pdf = True, _NO_DCO.pdf = False
# El script del día 1 traía DCO(True) fijo en código para TODA la sesión,
# pero de las 13 corridas de escalón ese día solo 3 quedaron anotadas a
# mano (185021=False, 185530 y 185621=True) -- lo que sugiere que se tocó
# DCO desde la consola, celda a celda, sin editar el script, solo para
# esas corridas puntuales. Las demás corridas del día 1 quedan con DCO
# DESCONOCIDO (None): no se puede asumir que el valor por defecto del
# script siguiera vigente toda la sesión si se lo tocó a mano para otras.
DCO = {}
for pdf in glob.glob(str(FIG / "E517_step_response_*.pdf")):
    m = re.search(r'(\d{8}_\d{6})_(NO_)?DCO(True|False)?\.pdf$', pdf)
    if not m:
        continue
    ts, no_, tf = m.groups()
    DCO[ts] = False if no_ else (tf == 'True' if tf else True)


# %% ---------------------------------------------------------------------
def cargar_escalon(ts):
    d = dict(re.findall(r'(\w+)=([^\s]+)',
                        open(META / f"E517_step_response_{ts}_metadata.txt").read()))
    df = pd.read_csv(RAW / f"E517_step_response_{ts}.csv")
    tgt, cur = df.target_um.values, df.current_um.values
    i = int(np.argmax(np.abs(np.diff(tgt)))) + 1        # primera muestra post-escalón
    S = tgt[i] - tgt[i - 2]                             # µm, con signo
    # Error respecto del target FINAL, con el signo normalizado para que
    # positivo siempre signifique "se pasó de largo".
    e = (cur[i:] - tgt[i:]) * 1e3 * np.sign(S)
    t = np.arange(len(e)) * T_SERVO * 1e3
    y = 1 + e / (abs(S) * 1e3)                          # posición normalizada
    return dict(
        ts=ts, dia=ts[:8], t=t, e=e, y=y, S_um=abs(S),
        WTR=int(d['WTR']), RTR=int(d['RTR_VAL']), N=int(d['N_TOTAL']),
        vent_ms=t[-1], dt_us=int(d['RTR_VAL']) * T_SERVO * 1e6,
        Tlabel=float(d['T_SERVO_US']),
        dco=DCO.get(ts, None),          # None = no quedó anotado en ningún PDF
    )


TODOS = [cargar_escalon(re.search(r'(\d{8}_\d{6})', f).group(1))
         for f in sorted(glob.glob(str(META / "E517_step_response_2026*_metadata.txt")))]


def metricas(r):
    t, e, y, S = r['t'], r['e'], r['y'], r['S_um'] * 1e3
    def cruza(l):
        return t[np.argmax(y >= l)] if (y >= l).any() else np.nan
    def asienta(banda):
        fuera = np.where(np.abs(e) > banda)[0]
        if len(fuera) == 0:
            return 0.0
        return t[fuera[-1] + 1] if fuera[-1] + 1 < len(t) else np.nan   # nan = no asentó
    # "Bump": la excursión lenta que aparece DESPUÉS de cruzar el target,
    # entre 25 y 120 ms. Es el término que domina el asentamiento.
    v = (t > 25) & (t < 120)
    bump = e[v].max() if v.sum() > 10 else np.nan
    t_bump = t[v][e[v].argmax()] if v.sum() > 10 else np.nan
    completa = r['vent_ms'] > 120          # ¿la ventana alcanza para ver el bump?
    return dict(
        t10_90=cruza(0.9) - cruza(0.1) if r['vent_ms'] > 25 else np.nan,
        bump_nm=bump, t_bump_ms=t_bump,
        ts_5nm=asienta(5.0), ts_2nm=asienta(2.0), ts_1pct=asienta(S / 100),
        # NaN si la ventana es tan corta que el sistema todavía está en
        # tránsito al final -- si no, "e_final" mide el propio tránsito,
        # no el error de régimen permanente.
        e_final=np.median(e[-max(10, len(e) // 20):]) if completa else np.nan,
        completa=completa,
    )


TAB = pd.DataFrame([dict(ts=r['ts'], dia=r['dia'], paso_um=r['S_um'], WTR=r['WTR'],
                         RTR=r['RTR'], N=r['N'], vent_ms=round(r['vent_ms']),
                         dt_us=r['dt_us'],
                         DCO={None: '?', True: 'True', False: 'False'}[r['dco']],
                         **metricas(r)) for r in TODOS])
TAB = TAB.sort_values(['paso_um', 'DCO', 'dia'])
pd.set_option('display.width', 240)
print(TAB.to_string(index=False, float_format=lambda x: f'{x:.1f}'))
TAB.to_csv(REPO / "resultados" / "tabla_asentamiento.csv", index=False)


# %% ---------------------------------------------------------------------
# FIGURA 06 — ¿Reproducen las corridas nuevas a las viejas?
# Solo las que tienen la ventana post-escalón casi completa: con RTR=1 el
# techo son 8192 muestras = 327.68 ms TOTALES, pero el pre-escalón
# (N_PRE=50 puntos de wave) come una parte -- 40 ms en el día 1 (WTR=20)
# y solo 2 ms en el día 2 (WTR=1). Por eso el corte real es ~287 ms
# post-escalón (día 1) / ~326 ms (día 2), no 300 ms parejo.
# El estado de DCO va EN LA LEYENDA a propósito: recién en la fig. 07 se ve
# que DCO por sí solo mueve 50-100 nm el asentamiento, así que cualquier
# comparación día 1 vs día 2 que lo ignore está potencialmente confundida.
# ------------------------------------------------------------------------
DCOLAB = {True: 'DCO=True', False: 'DCO=False', None: 'DCO=?'}
fig, axes = plt.subplots(1, 3, figsize=(9.6, 3.2), sharey=True)
for ax, paso in zip(axes, [2.0, 20.0, 200.0]):
    for r in TODOS:
        if abs(r['S_um'] - paso) > 0.05 * paso or r['vent_ms'] < 280:
            continue
        col = '#1f77b4' if r['dia'] == '20260901' else '#d62728'
        ls = '-' if r['dco'] is not False else '--'
        alpha = 0.9 if r['dco'] is not None else 0.45
        ax.semilogy(r['t'], np.abs(r['e']), ls, color=col, lw=0.9, alpha=alpha,
                    label=f"{r['dia'][4:6]}/{r['dia'][6:]}  WTR={r['WTR']}  {DCOLAB[r['dco']]}")
    ax.axhline(5, color='k', lw=0.7, ls=':')
    ax.text(300, 5.6, '±5 nm', fontsize=7, ha='right')
    ax.axhline(1.7, color='green', lw=0.7, ls=':')
    ax.text(300, 1.15, 'ruido 1.7 nm', fontsize=7, ha='right', color='green')
    ax.set_xlim(0, 328); ax.set_ylim(0.3, 3e5)
    ax.set_xlabel('t desde el escalón [ms]')
    ax.set_title(f'escalón de {paso:.0f} µm', fontsize=9)
    ax.legend(frameon=False, fontsize=6.3, loc='upper right')
axes[0].set_ylabel('|error| [nm]')
fig.suptitle('Día 1 (WTR=20) y día 2 (WTR=1) reproducen bien CON el mismo DCO\n'
             '(línea llena = DCO=True o desconocido, punteada = DCO=False; opaco = DCO conocido)',
             fontsize=8.8, y=1.05)
fig.tight_layout()
fig.savefig(FIG / "asent_06_reproducibilidad_dia1_dia2.pdf", bbox_inches='tight')
fig.savefig(FIG / "asent_06_reproducibilidad_dia1_dia2.png", bbox_inches='tight', dpi=200)


# %% ---------------------------------------------------------------------
# FIGURA 07 — DCO on/off: el efecto más grande medido
# ------------------------------------------------------------------------
fig = plt.figure(figsize=(9.6, 3.4))
gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1.05], wspace=0.32)
ax0, ax1, ax2 = (fig.add_subplot(gs[i]) for i in range(3))

D = {r['ts']: r for r in TODOS}

# (a) par controlado: mismo día, misma amplitud, misma ventana
for ts, lab, col in [('20260902_192038', 'DCO = True', '#d62728'),
                     ('20260902_192114', 'DCO = False', '#2ca02c')]:
    r = D[ts]
    ax0.plot(r['t'], r['e'], color=col, lw=1.0, label=lab)
ax0.axhspan(-5, 5, color='0.6', alpha=0.2, zorder=0)
ax0.axhline(0, color='k', lw=0.5)
ax0.set_xlim(0, 82); ax0.set_ylim(-260, 90)
ax0.set_xlabel('t desde el escalón [ms]'); ax0.set_ylabel('error [nm]')
ax0.set_title('(a) par controlado 02/09\nescalón 2 µm, misma ventana', fontsize=9)
ax0.legend(frameon=False, loc='lower right')
ax0.annotate('excursión lenta\nde +55 nm', xy=(58, 55), xytext=(30, -140),
             fontsize=7, color='#d62728',
             arrowprops=dict(arrowstyle='->', lw=0.7, color='#d62728'))

# (b) TODAS las corridas de 2000 nm (los dos días, todos los WTR),
# coloreadas por el DCO real, no supuesto. Muestra que el efecto de (a)
# no es un caso aislado, y de paso deja explícitamente a la vista qué
# corridas tienen DCO sin registrar (grises, punteadas) -- esas no
# deberían usarse para afirmar nada sobre DCO, aunque su forma sea
# consistente con la población DCO=True.
colores_dco = {True: '#d62728', False: '#2ca02c', None: '0.55'}
vistos = set()
for r in sorted(TODOS, key=lambda r: r['dco'] is None):   # conocidos primero, arriba en zorder
    if abs(r['S_um'] - 2.0) > 0.1 or r['vent_ms'] < 60:
        continue
    col = colores_dco[r['dco']]
    conocido = r['dco'] is not None
    lab = f"{DCOLAB[r['dco']]} ({r['dia'][4:6]}/{r['dia'][6:]}, WTR={r['WTR']}, {r['vent_ms']:.0f} ms)"
    ax1.plot(r['t'], r['e'], color=col, lw=1.1 if conocido else 0.7,
             ls='-' if conocido else '--', alpha=0.9 if conocido else 0.5,
             label=lab, zorder=3 if conocido else 1)
    vistos.add(lab)
ax1.axhspan(-5, 5, color='0.6', alpha=0.2, zorder=0)
ax1.axhline(0, color='k', lw=0.5)
ax1.set_xlim(0, 328); ax1.set_ylim(-260, 90)
ax1.set_xlabel('t desde el escalón [ms]'); ax1.set_ylabel('error [nm]')
ax1.set_title('(b) todas las corridas de 2000 nm\n(los dos días, todos los WTR)', fontsize=9)
ax1.legend(frameon=False, fontsize=5.6, loc='lower right', ncol=1)

# (c) amplitud del bump vs tamaño del escalón
for dco, col, mk, lab in [(True, '#d62728', 'o', 'DCO = True'),
                          (False, '#2ca02c', 's', 'DCO = False'),
                          (None, '#ff7f0e', '^', 'DCO no registrado')]:
    g = TAB[(TAB.DCO == {True: 'True', False: 'False', None: '?'}[dco])
            & TAB.bump_nm.notna()]
    ax2.loglog(g.paso_um * 1e3, g.bump_nm, mk, color=col, ms=5, label=lab,
               mfc='none' if dco is None else col, mew=1.1)
xx = np.logspace(1.2, 5.4, 20)
ax2.loglog(xx, 0.01 * xx, 'k:', lw=0.8, label='1 % del escalón')
ax2.set_xlabel('tamaño del escalón [nm]'); ax2.set_ylabel('pico del bump lento [nm]')
ax2.set_title('(c) el bump es ~50-100 nm ABSOLUTOS,\ncasi independiente del escalón', fontsize=9)
ax2.legend(frameon=False, fontsize=7, loc='upper left')

fig.savefig(FIG / "asent_07_efecto_DCO.pdf", bbox_inches='tight')
fig.savefig(FIG / "asent_07_efecto_DCO.png", bbox_inches='tight', dpi=200)


# %% ---------------------------------------------------------------------
# FIGURA 08 — Diseño de la medición: RTR es el knob, no N ni WTR
# ------------------------------------------------------------------------
fig, ax = plt.subplots(1, 2, figsize=(8.6, 3.3))

# (a) dónde cayó cada corrida
for dia, col, mk in [('20260901', '#1f77b4', 'o'), ('20260902', '#d62728', 's')]:
    g = TAB[TAB.dia == dia]
    ax[0].semilogy(g.N, g.vent_ms, mk, color=col, ms=6, alpha=0.8,
                   label=f"{dia[4:6]}/{dia[6:]}")
ax[0].set_ylim(14, 700)
ax[0].axhline(327.68, color='k', lw=1, ls='--')
ax[0].text(4300, 380, 'techo teórico con RTR=1: 8192×40µs = 327.68 ms\n'
           '(algo menos en la práctica: se come el pre-escalón)',
           fontsize=6.5, ha='right')
ax[0].axhspan(0, 170, color='crimson', alpha=0.10, zorder=0)
ax[0].text(200, 30, 'ventana MÁS CORTA que el\nasentamiento: no se puede medir',
           fontsize=7.5, color='crimson')
ax[0].set_xlabel('N_TOTAL de la wave'); ax[0].set_ylabel('ventana observada [ms]')
ax[0].set_title('(a) las 24 corridas: RTR=1 en todas', fontsize=9)
ax[0].legend(frameon=False, loc='lower right')

# (b) el plano de diseño
rtr = np.array([1, 2, 5, 10, 25, 50, 100])
ax[1].loglog(rtr, 8192 * rtr * T_SERVO * 1e3, 'o-', color='k', ms=4, lw=1.2,
             label='ventana = 8192 × RTR × 40 µs')
ax[1].loglog(rtr, rtr * T_SERVO * 1e3, 's-', color='#1f77b4', ms=4, lw=1.2,
             label='resolución = RTR × 40 µs')
ax[1].axhspan(150, 400, color='green', alpha=0.12)
ax[1].text(1.15, 200, 'asentamiento\nmedido', fontsize=7.5, color='darkgreen')
ax[1].axhline(18, color='#1f77b4', lw=0.8, ls=':')
ax[1].text(30, 21, 'subida $t_{10-90}$ = 18 ms', fontsize=7, color='#1f77b4')
ax[1].plot(1, 327.68, 'X', color='crimson', ms=10, zorder=5)
ax[1].annotate('dónde estás', xy=(1, 327.68), xytext=(1.6, 1200),
               fontsize=7.5, color='crimson',
               arrowprops=dict(arrowstyle='->', lw=0.7, color='crimson'))
ax[1].plot(10, 8192 * 10 * T_SERVO * 1e3, '*', color='darkgreen', ms=13, zorder=5)
ax[1].annotate('RTR=10: 3.3 s de ventana,\n45 muestras en la subida',
               xy=(10, 3276), xytext=(1.5, 8000), fontsize=7.5, color='darkgreen',
               arrowprops=dict(arrowstyle='->', lw=0.7, color='darkgreen'))
ax[1].set_ylim(0.02, 3e4)
ax[1].set_xlabel('RTR [ciclos de servo por muestra grabada]')
ax[1].set_ylabel('tiempo [ms]')
ax[1].set_title('(b) el knob que no moviste', fontsize=9)
ax[1].legend(frameon=False, fontsize=7, loc='lower right')

fig.tight_layout()
fig.savefig(FIG / "asent_08_diseno_de_la_medicion.pdf", bbox_inches='tight')
fig.savefig(FIG / "asent_08_diseno_de_la_medicion.png", bbox_inches='tight', dpi=200)

print(f"\n[ok] figuras en {FIG}")
