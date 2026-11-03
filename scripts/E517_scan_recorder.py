#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
E-517 (E-545) — Scan de área unidireccional con wave generator + data recorder.

Reemplaza la prueba con macros ('unidir'/'scan'). Con macros no se podía ver
nada mientras corrían: el controlador no atiende consultas durante una macro,
y #3 / MAC ERR? no existen en este firmware [MEDIDO 2026-10-30].
Acá el bucle de líneas lo maneja Python y cada línea la graba el data recorder
del controlador, que se lee al terminar con DRR?.

Por línea:
    1. MOV A X0 (retroceso) y asentamiento.
    2. WGO 1 1: el wave generator recorre X0 -> X0+AMPLITUD_X (WAV LIN con
       speedupdown). El data recorder arranca automáticamente con WGO.
    3. Se espera a que termine y se leen las tablas del recorder:
         tabla 1: A target  (opción 1)
         tabla 2: A current (opción 2)
         tabla 3: B current (opción 2)
    4. MVR B PASO_Y.

ATENCIÓN: mueve la platina en A y B dentro de los rangos de abajo.

Misma conexión que E517_diagnostico.py (gateway FTDI).
Uso en Spyder: intérprete ~/python-envs/pi/bin/python3.12, correr por celdas.
"""

# %% -- Imports ---------------------------------------------------------------
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pipython import GCSDevice, pitools
from pi_ftdi_gateway import PIFtdiGateway, cleanup_gcsdevice

DATOS_RAW = Path(__file__).resolve().parent / "datos" / "raw"
DATOS_RAW.mkdir(parents=True, exist_ok=True)


# %% -- Parámetros del scan ---------------------------------------------------
# [ELEGIDO] Geometría (mismo espíritu que 'unidir'/'scan': 5 líneas, paso 2 µm)
X0          = 0.0      # µm, inicio de cada línea
AMPLITUD_X  = 50.0     # µm, largo de la línea (X0 -> X0+AMPLITUD_X)
Y0          = 0.0      # µm, primera línea
PASO_Y      = 2.0      # µm, paso entre líneas
N_LINEAS    = 5

# [ELEGIDO] Wave table
N_PUNTOS    = 1000     # puntos de la línea en la tabla
SPEEDUPDOWN = 100      # puntos de aceleración/desaceleración en cada extremo
WTR         = 5        # ciclos de servo por punto de la tabla

# [ELEGIDO] Data recorder
RTR         = 1        # ciclos de servo por muestra grabada
T_ASENT_S   = 0.2      # asentamiento después del retroceso

# Identificadores fijos del E-517 (1<->A, 2<->B)
TABLA_X, WGEN_X = 1, 1


# %% -- Conexión y estado inicial ---------------------------------------------
pidevice = GCSDevice('E-517', gateway=PIFtdiGateway())
print(f"Conectado a: {pidevice.qIDN().strip()}")
print(f"[ERR?] {pidevice.qERR()}   # limpia errores viejos")

pidevice.WGO(WGEN_X, 0)                    # por si quedó algo corriendo
pidevice.ONL([1, 2], [1, 1])
pidevice.SVO(['A', 'B'], [True, True])

t_servo_s = float(pidevice.qSPA(1, 0x0E000200)[1][0x0E000200])
dur_linea_s = N_PUNTOS * WTR * t_servo_s
n_muestras = N_PUNTOS * WTR // RTR         # muestras que cubren una línea
print(f"[timing] servo = {t_servo_s*1e6:.1f} µs, línea = {dur_linea_s*1e3:.1f} ms "
      f"({AMPLITUD_X / dur_linea_s:.0f} µm/s), {n_muestras} muestras/línea")
# [MEDIDO, E517_ida_vuelta.py] 5000 muestras por tabla entran bien; el límite
# exacto del recorder no está medido [VERIFICAR con DRL? si se agranda].
assert n_muestras <= 8192, "Demasiadas muestras por línea: subir RTR o bajar N_PUNTOS/WTR"


# %% -- Helper: leer un array GCS asíncrono (qGWD/qDRR) -----------------------
def _leer_array_gcs(pidevice, timeout=10.0):
    """qGWD/qDRR devuelven sólo el header; los datos llegan por bufdata."""
    t0 = time.time()
    while pidevice.bufstate is not True:
        if time.time() - t0 > timeout:
            raise TimeoutError("bufstate no llegó a True")
        time.sleep(0.005)
    return np.array(pidevice.bufdata[0])


# %% -- Cargar la línea en la wave table --------------------------------------
pidevice.WCL(TABLA_X)
pidevice.WAV_LIN(
    table=TABLA_X, firstpoint=1, numpoints=N_PUNTOS, append='X',
    speedupdown=SPEEDUPDOWN, amplitude=AMPLITUD_X, offset=X0, seglength=N_PUNTOS,
)
pidevice.qGWD(TABLA_X, 1, N_PUNTOS)
wave = _leer_array_gcs(pidevice)
print(f"[wave] {len(wave)} puntos, {wave[0]:.3f} -> {wave[-1]:.3f} µm")

pidevice.WTR(WGEN_X, WTR, 0)
pidevice.WGC(WGEN_X, 1)                    # una pasada por WGO
# [MEDIDO 2026-10-30] Después de las pruebas con WAV CFG quedó WOS = 2.0 µm:
# hay que ponerlo en 0 explícitamente, si no toda la línea sale corrida.
pidevice.WOS(WGEN_X, 0.0)

pidevice.DRC(tables=[1, 2, 3], sources=['A', 'A', 'B'], options=[1, 2, 2])
pidevice.RTR(RTR)
print(f"[DRC] {dict(pidevice.qDRC())}   [RTR] {pidevice.qRTR()}")


# %% -- Scan: una línea por vuelta del bucle ----------------------------------
pidevice.MOV(['A', 'B'], [float(wave[0]), Y0])
pitools.waitontarget(pidevice, ['A', 'B'], timeout=10)

lineas = []
for i in range(N_LINEAS):
    # retroceso al inicio de la línea y asentamiento
    pidevice.MOV('A', float(wave[0]))
    pitools.waitontarget(pidevice, ['A', 'B'], timeout=10)
    time.sleep(T_ASENT_S)

    # disparo: el recorder arranca con WGO
    pidevice.WGO(WGEN_X, 1)
    pitools.waitonwavegen(pidevice, wavegens=WGEN_X, timeout=dur_linea_s + 5)
    pidevice.WGO(WGEN_X, 0)

    # leer el recorder (drenar cada qDRR antes del siguiente)
    n_leer = min(n_muestras, int(pidevice.qDRL(1)[1]))
    datos = {}
    for tabla, clave in [(1, 'x_target'), (2, 'x_current'), (3, 'y_current')]:
        pidevice.qDRR(tabla, 1, n_leer)
        datos[clave] = _leer_array_gcs(pidevice)
    datos['t_ms'] = np.arange(n_leer) * RTR * t_servo_s * 1e3
    datos['linea'] = np.full(n_leer, i)
    lineas.append(pd.DataFrame(datos))

    err = datos['x_target'] - datos['x_current']
    print(f"[línea {i}] Y≈{datos['y_current'].mean():.3f} µm, {n_leer} muestras, "
          f"X {datos['x_current'].min():.2f}..{datos['x_current'].max():.2f} µm, "
          f"error X máx {np.abs(err).max()*1e3:.1f} nm, RMS {np.sqrt(np.mean(err**2))*1e3:.1f} nm")

    if i < N_LINEAS - 1:
        pidevice.MVR('B', PASO_Y)

df = pd.concat(lineas, ignore_index=True)
print(f"[ERR?] {pidevice.qERR()}   # 0 = sin error")


# %% -- Guardar ------------------------------------------------------------------
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
archivo = DATOS_RAW / f"E517_scan_recorder_{timestamp}.csv"
df.to_csv(archivo, index=False)
print(f"[guardado] {archivo}")


# %% -- Graficar ------------------------------------------------------------------
fig, axs = plt.subplots(1, 3, figsize=(16, 4.5))

for i, d in df.groupby('linea'):
    axs[0].plot(d['t_ms'], d['x_current'], lw=1, label=f'línea {i}')
    axs[1].plot(d['t_ms'], (d['x_target'] - d['x_current']) * 1e3, lw=0.8)
    axs[2].plot(d['x_current'], d['y_current'], lw=0.8)

axs[0].set(xlabel='t (ms)', ylabel='X real (µm)', title='X por línea')
axs[0].legend(fontsize=8)
axs[1].set(xlabel='t (ms)', ylabel='target − real (nm)', title='Error de seguimiento en X')
axs[2].set(xlabel='X real (µm)', ylabel='Y real (µm)', title='Trayectoria XY')
for ax in axs:
    ax.grid(True, ls='--', alpha=0.5)
fig.tight_layout()
plt.show()


# %% -- Volver al inicio y cerrar -------------------------------------------------
pidevice.MOV(['A', 'B'], [X0, Y0])
pitools.waitontarget(pidevice, ['A', 'B'], timeout=10)
print(f"[cierre] posición final {dict(pidevice.qPOS(['A', 'B']))}")
cleanup_gcsdevice(pidevice)
print("Fin.")
