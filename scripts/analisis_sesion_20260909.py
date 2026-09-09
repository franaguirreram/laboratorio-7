#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paneo de la sesión del 2026-09-09. Off-line, no toca el hardware.

Tres bloques corridos, tres preguntas:
  1. rampa   — ¿e_ss = v·tau con tau constante?      -> NO, e ~ v^0.85
  2. vuelta  — ¿el flyback cuesta lo mismo que la ida? -> SÍ, dentro del 3 %
  3. diafonía— ¿barrer x mueve y?                    -> NO, cota 0.15 nm/µm

Uso:  ~/python-envs/pi/bin/python3 scripts/analisis_sesion_20260909.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
RAW, BAR, FIG = REPO/"datos"/"raw", REPO/"resultados"/"barridos", REPO/"resultados"/"figuras"
T_SERVO, TAU_ESC, T_CONV = 40e-6, 13.09, 33.0
trapz = getattr(np, "trapezoid", None) or np.trapz
plt.rcParams.update({'font.family':'serif','font.size':9,'figure.dpi':120,
                     'axes.grid':True,'grid.alpha':.25,'grid.linewidth':.5})

SES = "20260909"
ult = lambda pat: sorted(BAR.glob(pat))[-1]

# ── 1. rampa ─────────────────────────────────────────────────────────────
R = pd.read_csv(ult(f"barrido_tau_rampa_{SES}_*.csv"))
v, e = R.v_um_s.values, np.abs(R.error_mediano_nm.values)
tau_origen = float(np.sum(v*e)/np.sum(v*v))
alfa, lnk = np.polyfit(np.log(v), np.log(e), 1)

# ── 2. vuelta ────────────────────────────────────────────────────────────
def tau_area(archivo, T_int=50.0):
    d = pd.read_csv(RAW/f"{archivo}.csv")
    tg, cu = d.target_um.values*1e3, d.current_um.values*1e3
    i = int(np.argmax(np.abs(np.diff(tg[:len(tg)//2])))) + 1
    S, base = tg[i]-tg[i-1], cu[i-50:i].mean()
    t, y = (np.arange(len(tg))-i)*0.04, (cu-cu[i-50:i].mean())/S
    w = (t >= 0) & (t <= T_int)
    ts, u = t[t >= 0], (1-y)[t >= 0]
    ac = np.concatenate([[0], np.cumsum((u[:-1]+u[1:])/2*np.diff(ts))])
    ainf = np.interp(150, ts, ac)
    return trapz(1-y[w], t[w]), float(ts[np.argmax(ac >= .995*ainf)]), abs(S)

V = pd.read_csv(ult(f"barrido_vuelta_{SES}_*.csv"))
V[["tau_area", "t_conv", "salto"]] = V.archivo.apply(lambda a: pd.Series(tau_area(a)))
V["sentido"] = np.where(V.amplitud_um > 0, "sube", "baja")
VG = V.groupby(["salto", "sentido"]).tau_area.mean().unstack()

# ── 3. diafonía ──────────────────────────────────────────────────────────
D = pd.read_csv(ult(f"barrido_diafonia_{SES}_*.csv"))
def xy(archivo):
    d = pd.read_csv(RAW/f"{archivo}.csv")
    return (np.arange(len(d))*0.04, d["current_um_A"].values*1e3,
            d["current_um_B"].values*1e3)
ctrl = D[D.etiqueta.str.contains("control")].archivo.iloc[0]
t_c, xa_c, yb_c = xy(ctrl)
diaf = []
for a in D[D.etiqueta.str.contains("A10um")].archivo:
    t, x, y = xy(a); m = (t > T_CONV) & (t < 158)
    diaf.append((np.polyfit(x[m], y[m], 1)[0]*1000, x[m], y[m]))
pend = np.mean([p for p, _, _ in diaf])

# ── figura ───────────────────────────────────────────────────────────────
fig, ax = plt.subplots(2, 2, figsize=(10, 7))

a = ax[0, 0]
a.loglog(v, e, "C0o", ms=6, label="medido")
vv = np.logspace(np.log10(v.min()*.7), np.log10(v.max()*1.4), 50)
a.loglog(vv, vv*TAU_ESC, "C1--", lw=1.3, label=f"$e=v\\,\\tau$, τ={TAU_ESC:.1f} ms (escalón)")
a.loglog(vv, np.exp(lnk)*vv**alfa, "C0-", lw=1, label=f"ajuste: $e\\propto v^{{{alfa:.2f}}}$")
a.set(xlabel="v [µm/s]", ylabel="$e_{ss}$ [nm]", title="(a) rampa: NO es $e=v\\,\\tau$")
a.legend(fontsize=7, loc="upper left")

b = ax[0, 1]
b.semilogx(v, e/v, "C0o-", ms=5, lw=.8)
b.axhline(TAU_ESC, color="C1", ls="--", lw=1.3, label=f"escalón: {TAU_ESC:.1f} ms")
for vi, ei, Ai in zip(v[::2], e[::2], R.amplitud_um.values[::2]):
    b.annotate(f"A={Ai:g}", (vi, ei/vi), textcoords="offset points",
               xytext=(4, 5), fontsize=6.5, color="0.35")
b.set(xlabel="v [µm/s]   (y amplitud: v ∝ A)", ylabel=r"$e_{ss}/v$  [ms]",
      title="(b) el 'τ' de la rampa cae 2.5× con v", ylim=(0, 30))
b.legend(fontsize=7)

c = ax[1, 0]
xpos = np.arange(len(VG))
c.bar(xpos-.18, VG["sube"], .34, label="sube (+)", color="C0")
c.bar(xpos+.18, VG["baja"], .34, label="baja (−) = flyback", color="C3")
c.axhline(TAU_ESC, color="C1", ls="--", lw=1.2, label=f"escalón 2 µm: {TAU_ESC:.1f} ms")
c.set(xticks=xpos, xticklabels=[f"{s/1000:g} µm" for s in VG.index],
      ylabel=r"$\tau_{\rm area}$ [ms]", ylim=(0, 16),
      title="(c) vuelta: el flyback cuesta lo mismo que la ida")
c.legend(fontsize=7, loc="lower left")
for i, (s, bj) in enumerate(zip(VG["sube"], VG["baja"])):
    c.text(i, max(s, bj)+.4, f"{100*(bj-s)/s:+.1f} %", ha="center", fontsize=7)

d = ax[1, 1]
_, x1, y1 = diaf[0]
d.plot(x1-x1.mean(), y1-y1.mean(), "C0.", ms=1.5, alpha=.5, label="barriendo x (16 µm)")
d.plot(np.linspace(-8000, 8000, 50), xa_c[:50]*0 + (yb_c-yb_c.mean())[:50],
       "none")
d.plot(np.full(len(yb_c), 0), yb_c-yb_c.mean(), "C3.", ms=1.5, alpha=.35,
       label="control (x quieto)")
xx = np.linspace(-8500, 8500, 20)
d.plot(xx, pend*xx/1000, "C0-", lw=1.2, label=f"pendiente {pend:+.2f} nm/µm")
d.set(xlabel="posición x − ⟨x⟩ [nm]", ylabel="posición y − ⟨y⟩ [nm]", ylim=(-6, 6),
      title="(d) diafonía: y no se entera de x")
d.legend(fontsize=7, loc="upper left")

fig.tight_layout()
out = FIG/f"sesion_{SES}_paneo.png"
fig.savefig(out, dpi=130)
print(f"figura: {out}")

# ── resumen ──────────────────────────────────────────────────────────────
print(f"""
1. RAMPA  (12 corridas, v = {v.min():.2f}–{v.max():.0f} µm/s, 2.5 décadas)
   e_ss ∝ v^{alfa:.3f}   ← si fuera lineal daría 1.000
   e/v va de {e[0]/v[0]:.1f} ms (A=0.1 µm) a {e[-1]/v[-1]:.1f} ms (A=30 µm)
   ajuste forzado por el origen: tau = {tau_origen:.2f} ms, residuo {np.std(e-v*tau_origen):.0f} nm

2. VUELTA (12 corridas)
{VG.round(2).to_string()}
   asimetría baja−sube: {', '.join(f'{100*(VG.baja[s]-VG.sube[s])/VG.sube[s]:+.1f} %' for s in VG.index)}
   t_conv medido: {V.t_conv.mean():.0f} ± {V.t_conv.std():.0f} ms   (el del escalón de ayer: {T_CONV:.0f} ms)

3. DIAFONÍA (5 corridas)
   piso del control (x quieto): y rms = {yb_c.std():.2f} nm, pp = {yb_c.max()-yb_c.min():.2f} nm
   barriendo x 16 µm:           y pp = {y1.max()-y1.min():.2f} nm
   pendiente dy/dx = {pend:+.2f} nm/µm  →  sobre una línea de 10 µm: {pend*10:+.1f} nm
""")
