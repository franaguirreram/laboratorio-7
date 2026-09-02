#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
E-517 / E-545 — Respuesta a escalón (step response)

Hermano de E517_ida_vuelta_speedupdown.py: misma conexión (PIFtdiGateway),
mismo esquema de data recorder (DRC target/current/error + RTR + qDRR vía
bufstate/bufdata), mismo guardado en datos/raw + datos/metadata con
timestamp, mismos gráficos en estilo Nature.

Se diferencia solo en la wave table cargada: en vez de una rampa
(WAV_RAMP), acá se carga una trayectoria plana-salto-plana (baseline en
POS_INICIAL, salto instantáneo a POS_FINAL, y se mantiene ahí) para medir
el tiempo de asentamiento tras un escalón.

CONVENCIONES DE TRAZABILIDAD:
    [MEDIDO]      verificado en tu propio código (E517_ida_vuelta_speedupdown.py)
                   o en los manuales del proyecto
    [INFERENCIA]  interpretación razonable, no verificada explícitamente
    [VERIFICAR]   confirmalo vos antes de correr en el equipo
    [PENDIENTE]   parámetro que falta completar

------------------------------------------------------------------------
QUÉ CAMBIÓ RESPECTO A LA VERSIÓN ANTERIOR DE ESTE SCRIPT (la que te di
antes de ver tu código real):
------------------------------------------------------------------------
[RESUELTO] options=[1,2,3] en DRC = target, current, error. Antes había
    marcado esto como VERIFICAR-1 (no sabía qué número de "option" daba
    la posición comandada); tu propio script lo confirma.
[RESUELTO] La lectura de datos grabados NO es "qDRR(...) devuelve un
    dict" como yo había asumido (VERIFICAR-2 anterior). Es:
        pidevice.qDRR(tabla, inicio, n)   # dispara la lectura async
        # y después hay que ESPERAR a que pidevice.bufstate sea True
        # y leer de pidevice.bufdata[0]
    -- eso es lo que hace tu helper _leer_array_gcs, que reutilizo tal
    cual.
[SIGUE SIN VERIFICAR] El comando STE (que dispararía un step "nativo" de
    una sola instrucción) -- tu propio código tampoco lo usa (usa
    WAV_RAMP/WAV_LIN para todo), así que sigo sin sintaxis confirmada
    para STE. Acá armo el escalón punto a punto con WAV_LIN, igual que
    tu ejemplo de "onda personalizada" (numpoints=1, seglength=1 por
    punto) -- 100% dentro de lo que ya usás y confirmaste que funciona.
[NUEVO, PENDIENTE de tu parte] T_SERVO_US = 10.0 lo tomé de tu script
    (comentario "[MEDIDO — E517_diagnostico.py, SPA 0x0E000200]"). Yo no
    corrí ese diagnóstico, así que si tu hardware cambió o usás otro
    controlador, confirmalo de nuevo con SPA 0x0E000200 antes de confiar
    en el eje temporal.
"""

# %% -- Imports --------------------------------------------------
from pipython import GCSDevice, pitools
from pi_ftdi_gateway import PIFtdiGateway, cleanup_gcsdevice
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATOS_RAW = REPO_ROOT / "datos" / "raw"
DATOS_METADATA = REPO_ROOT / "datos" / "metadata"
RESULTADOS_FIGURAS = REPO_ROOT / "resultados" / "figuras"
for _dir in (DATOS_RAW, DATOS_METADATA, RESULTADOS_FIGURAS):
    _dir.mkdir(parents=True, exist_ok=True)
# [MEDIDO] mismos tres directorios que tu script; todas las corridas
# (ida_vuelta, step_response, lo que sea) quedan mezcladas ahí adentro,
# distinguidas solo por el prefijo del nombre + timestamp.


# %% -- Parámetros del experimento -------------------------------
CENTRO_X = 100.0        # µm, punto de referencia  [PENDIENTE: ajustar]
CENTRO_Y = 100.0        # µm, Y queda quieto

AMPLITUD_ESCALON = .1  # µm, tamaño del escalón (semi-amplitud, igual
                         # convención que AMPLITUD en tu script de ida y
                         # vuelta) [PENDIENTE: ajustar]
                         # sugerencia: correlo primero con un escalón
                         # chico (representativo del paso entre puntos
                         # de un escaneo) y después con uno grande, igual
                         # que tus barridos de Bode a dos amplitudes —
                         # el settling time puede cambiar si hay
                         # saturación de slew-rate

T_SERVO_US = 40.0        # [MEDIDO, de tu script — E517_diagnostico.py,
                          #  SPA 0x0E000200] -- volver a confirmar si
                          #  cambia el hardware
WTR = 1                 # ciclos de servo por punto de wave table
                          # → dwell = T_SERVO_US * WTR
DWELL_US = T_SERVO_US * WTR

N_PRE = 50               # puntos de baseline en POS_INICIAL, antes del
                          # escalón (para tener referencia de ruido de
                          # fondo antes del salto)
N_POST = 8000              # puntos después del escalón, en POS_FINAL
                          # (tiene que alcanzar para ver el asentamiento
                          # completo -- si tu tau de asentamiento es
                          # largo, subí este número)
N_TOTAL = N_PRE + N_POST
DURACION_MS = N_TOTAL * DWELL_US / 1000

print(f"[timing] dwell/punto = {DWELL_US:.0f} µs, N_total = {N_TOTAL}, "
      f"duración = {DURACION_MS:.2f} ms")

TABLA_X = 1
WGEN_X = 1
AXIS_X = 'A'


# %% -- Conexión y estado inicial --------------------------------
pidevice = GCSDevice('E-517', gateway=PIFtdiGateway())
print(f"[conexión] {pidevice.qIDN().strip()}")

pidevice.ONL([1, 2, 3], [1, 1, 1])
pidevice.SVO(['A', 'B'], [True, True])

pidevice.DCO(['A', 'B'], [False, False])
print(pidevice.qDCO())
pidevice.VCO(['A', 'B'], [False, False])
print(pidevice.qVCO())


# %% -- Puntos inicial y final del escalón ------------------------
pos_inicial = CENTRO_X - AMPLITUD_ESCALON
pos_final = CENTRO_X + AMPLITUD_ESCALON

print(f"[trayectoria] escalón: {pos_inicial:.4f} -> {pos_final:.4f} µm "
      f"(tamaño: {2*AMPLITUD_ESCALON*1000:.0f} nm)")


# %% -- Ir al punto de partida y asentar --------------------------
pidevice.MOV(['A', 'B'], [pos_inicial, CENTRO_Y])
pitools.waitontarget(pidevice, ['A', 'B'], timeout=10)

T_ASENTAMIENTO_S = 0.5
time.sleep(T_ASENTAMIENTO_S)
print(f"[posición inicial + asentamiento {T_ASENTAMIENTO_S}s] {dict(pidevice.qPOS())}")


# %% -- Helper: leer un array GCS asíncrono (qGWD/qDRR) --------------
# [MEDIDO, idéntico a tu script]
def _leer_array_gcs(pidevice, timeout=10.0):
    t0 = time.time()
    while pidevice.bufstate is not True:
        if time.time() - t0 > timeout:
            raise TimeoutError("bufstate no llegó a True")
        time.sleep(0.005)
    return np.array(pidevice.bufdata[0])


# %% -- Cargar la wave table: baseline plana + escalón + hold plano ----
# Punto a punto con WAV_LIN, igual que tu ejemplo de "onda personalizada"
# (numpoints=1, seglength=1 por punto) -- no uso WAV_RAMP porque acá no
# quiero una rampa, quiero un salto lo más abrupto posible seguido de un
# tramo plano para medir el asentamiento.
pidevice.WCL(TABLA_X)

trayectoria = np.concatenate([
    np.full(N_PRE, pos_inicial),
    np.full(N_POST, pos_final),
])

for i, val in enumerate(trayectoria):
    append_mode = 'X' if i == 0 else '&'
    pidevice.WAV_LIN(
        table=TABLA_X, firstpoint=i, numpoints=1, append=append_mode,
        speedupdown=0, amplitude=0, offset=val, seglength=1,
    )
# Verificar leyendo la tabla completa
pidevice.qGWD(TABLA_X, 1, N_TOTAL)
wave_cargada = _leer_array_gcs(pidevice)

print(f"[carga] {N_TOTAL} puntos cargados con WAV_LIN punto a punto")
print(f"[wave] primeros 3 puntos={wave_cargada[:3]}, "
      f"puntos alrededor del escalón (idx {N_PRE-1}:{N_PRE+2})="
      f"{wave_cargada[N_PRE-1:N_PRE+2]}, últimos 3={wave_cargada[-3:]}")


# %% -- Configurar reproducción ---------------------------------
pidevice.WTR(WGEN_X, WTR, 0)
pidevice.WGC(WGEN_X, 1)
pidevice.WOS(WGEN_X, 0.0)
print(f"[wave] WTR={WTR}, WGC=1, WOS=0.0")


# %% -- Configurar el data recorder ------------------------------
# [MEDIDO, idéntico a tu script] options=[1,2,3] = target, current, error
pidevice.DRC(tables=[1, 2, 3], sources=['A', 'A', 'A'], options=[1, 2, 3])
print(f"[DRC] {dict(pidevice.qDRC())}")

RTR_VAL = 1
pidevice.RTR(RTR_VAL)
print(f"[RTR] {pidevice.qRTR()} → dt_grabación = {RTR_VAL*T_SERVO_US:.0f} µs")


# %% -- DISPARO ----------------------------------------------
print("\n[GO] disparando wave generator...")
t_start = time.time()
pidevice.WGO(WGEN_X, 1)
pitools.waitonwavegen(pidevice, wavegens=WGEN_X, timeout=10)
pidevice.WGO(WGEN_X, 0)
print(f"[GO] duración medida en host: {(time.time()-t_start)*1000:.1f} ms "
      f"(esperado ≈ {DURACION_MS:.1f} ms)")


# %% -- Leer datos grabados ----------------------------------------
N_MAX_TABLA = 8192  # tamaño máximo de cada tabla del data recorder
n_leer = min(N_TOTAL * WTR, N_MAX_TABLA)

pidevice.qDRR(1, 1, n_leer)
target = _leer_array_gcs(pidevice)

pidevice.qDRR(2, 1, n_leer)
current = _leer_array_gcs(pidevice)

pidevice.qDRR(3, 1, n_leer)
error = _leer_array_gcs(pidevice)

t_ms = np.arange(len(current)) * (T_SERVO_US / 1000)

print(f"[data] {len(current)} muestras leídas; span temporal = {t_ms[-1]:.2f} ms")
print(f"[error tracking] max = {np.max(np.abs(error))*1000:.2f} nm, "
      f"RMS = {np.sqrt(np.mean(error**2))*1000:.2f} nm")


# %% -- Análisis: tiempo de asentamiento (settling time) -----------
def tiempo_de_asentamiento(t_ms, pos_um, pos_final_um,
                            tolerancia_nm=5.0, t_escalon_ms=None):
    """
    Primer instante a partir del cual pos_um permanece dentro de
    +-tolerancia_nm alrededor de pos_final_um, sin volver a salir.
    Si t_escalon_ms se especifica, el resultado se reporta relativo al
    instante del escalón (en vez de relativo a t_ms[0]).

    Devuelve (t_settling_ms, dentro_de_banda).
    """
    pos_final_nm = pos_final_um * 1000
    pos_nm = pos_um * 1000
    dentro_de_banda = np.abs(pos_nm - pos_final_nm) <= tolerancia_nm

    fuera = np.where(~dentro_de_banda)[0]
    if len(fuera) == 0:
        t_settling_ms = t_ms[0]
    else:
        ultimo_fuera = fuera[-1]
        if ultimo_fuera == len(t_ms) - 1:
            return np.nan, dentro_de_banda   # nunca asentó en la ventana medida
        t_settling_ms = t_ms[ultimo_fuera + 1]

    if t_escalon_ms is not None:
        t_settling_ms = t_settling_ms - t_escalon_ms

    return t_settling_ms, dentro_de_banda


# instante nominal del escalón (fin del baseline, en la escala de current/target)
t_escalon_ms = N_PRE * WTR * (T_SERVO_US / 1000)

t_settling_ms, dentro_de_banda = tiempo_de_asentamiento(
    t_ms, current, pos_final, tolerancia_nm=5.0, t_escalon_ms=t_escalon_ms
)
print(f"[settling] tiempo de asentamiento tras el escalón (banda ±5 nm): "
      f"{t_settling_ms:.3f} ms" if not np.isnan(t_settling_ms)
      else "[settling] no asentó dentro de la ventana medida -- subí N_POST")


# %% -- Guardar los datos crudos (para analizar después) ----------
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
nombre_base = f"E517_step_response_{timestamp}"

df = pd.DataFrame({
    't_ms': t_ms,
    'target_um': target,
    'current_um': current,
    'error_um': error,
})
df.to_csv(DATOS_RAW / f"{nombre_base}.csv", index=False)

with open(DATOS_METADATA / f"{nombre_base}_metadata.txt", 'w') as f:
    f.write(f"E517_step_response.py -- {timestamp}\n")
    f.write(f"CENTRO_X={CENTRO_X} CENTRO_Y={CENTRO_Y} "
            f"AMPLITUD_ESCALON={AMPLITUD_ESCALON}\n")
    f.write(f"pos_inicial={pos_inicial} pos_final={pos_final}\n")
    f.write(f"T_SERVO_US={T_SERVO_US} WTR={WTR} RTR_VAL={RTR_VAL}\n")
    f.write(f"N_PRE={N_PRE} N_POST={N_POST} N_TOTAL={N_TOTAL}\n")
    f.write(f"T_ASENTAMIENTO_S={T_ASENTAMIENTO_S}\n")
    f.write(f"n_leer={n_leer} muestras_leidas={len(current)}\n")
    f.write(f"t_escalon_ms={t_escalon_ms:.4f}\n")
    f.write(f"error_max_nm={np.max(np.abs(error))*1000:.3f}\n")
    f.write(f"error_rms_nm={np.sqrt(np.mean(error**2))*1000:.3f}\n")
    f.write(f"settling_time_ms_band5nm={t_settling_ms:.4f}\n")

print(f"[guardado] {nombre_base}.csv + {nombre_base}_metadata.txt")


# %% -- Volver al centro y cerrar --------------------------------
pidevice.MOV(['A'], [CENTRO_X])
pitools.waitontarget(pidevice, ['A'], timeout=5)
print(f"[cierre] posición final {dict(pidevice.qPOS())}")
cleanup_gcsdevice(pidevice)


# %% -- Gráficos --------------------------------------------
plt.rcParams.update({
    'font.family': 'serif',
    'font.size': 12,
    'axes.labelsize': 14,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    'figure.dpi': 120,
})

fig, axes = plt.subplots(2, 1, figsize=(6.5, 5), sharex=True)

axes[0].plot(t_ms - t_escalon_ms, (target - CENTRO_X) * 1000,
             color='#1f77b4', lw=1.2, label='comandada')
axes[0].plot(t_ms - t_escalon_ms, (current - CENTRO_X) * 1000,
             color='#d62728', lw=0.9, label='real')
axes[0].axvline(0, color='gray', lw=0.5, ls='--')
axes[0].set_ylabel(r'$x - x_c$ [nm]')
axes[0].legend(frameon=False, loc='lower right')

axes[1].plot(t_ms - t_escalon_ms, error * 1000, color='k', lw=0.8)
axes[1].axhline(5, color='gray', lw=0.5, ls='--')
axes[1].axhline(-5, color='gray', lw=0.5, ls='--')
if not np.isnan(t_settling_ms):
    axes[1].axvline(t_settling_ms, color='red',
                     label=f'settling = {t_settling_ms:.2f} ms')
    axes[1].legend(frameon=False, loc='upper right')
axes[1].set_ylabel('error [nm]')
axes[1].set_xlabel('t − t_escalón [ms]')

plt.tight_layout()
plt.savefig(RESULTADOS_FIGURAS / f"{nombre_base}_DCOFalse.pdf", bbox_inches='tight', dpi=200)
plt.show()

print(f"\n[fin] gráfico guardado como {nombre_base}.pdf")
