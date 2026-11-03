#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
E-517 / E-545 — Diagnóstico del wave generator + carga de una rampa LIN
vía gateway FTDI (macOS/arm64).

Misma conexión que repo-lab7/scripts/E517_diagnostico.py:
GCSDevice('E-517', gateway=PIFtdiGateway()) y cierre con cleanup_gcsdevice().

Sólo escribe y relee la wave table: NO arranca el wave generator (no hay WGO),
así que la platina no se mueve.

Uso en Spyder:
    Python Interpreter debe apuntar a ~/python-envs/pi/bin/python3.12
    Correr por celdas (#%%) o de arriba a abajo. Sin argumentos.
"""

# %% -- Imports y conexión --------------------------------------------------
import time

import matplotlib.pyplot as plt
import numpy as np
from pi_ftdi_gateway import PIFtdiGateway, cleanup_gcsdevice
from pipython import GCSDevice, pitools

WAVE_TABLE_ID = 1  # Tabla / wave generator asignado al eje X (canal 1)

pidevice = GCSDevice("E-517", gateway=PIFtdiGateway())
print(f"Conectado a: {pidevice.qIDN().strip()}")


# %% -- Helper: leer un array GCS asíncrono (qGWD/qDRR) --------------------
# qGWD devuelve SOLO el header; los datos llegan por pidevice.bufdata cuando
# pidevice.bufstate pasa a True (ver docstring de qGWD en pipython).
def _leer_array_gcs(pidevice, timeout=10.0):
    t0 = time.time()
    while pidevice.bufstate is not True:
        if time.time() - t0 > timeout:
            raise TimeoutError("bufstate no llegó a True")
        time.sleep(0.005)
    return np.array(pidevice.bufdata[0])


def _primero(valor):
    """Algunas queries (p. ej. WTR?) pueden devolver (rate, tipo)."""
    return valor[0] if isinstance(valor, (list, tuple)) else valor


# %% -- 2. Lectura de parámetros del wave generator -------------------------
t_servo_s = float(pidevice.qSPA(1, 0x0E000200)[1][0x0E000200])  # servo update time
num_generators = pidevice.qTWG()  # TWG?
max_points = pidevice.qWMS(WAVE_TABLE_ID)[WAVE_TABLE_ID]  # WMS?
table_rate = int(_primero(pidevice.qWTR(WAVE_TABLE_ID)[WAVE_TABLE_ID]))  # WTR?
cycles = pidevice.qWGC(WAVE_TABLE_ID)[WAVE_TABLE_ID]  # WGC?
wave_offset = pidevice.qWOS(WAVE_TABLE_ID)[WAVE_TABLE_ID]  # WOS?
start_mode = pidevice.qWGO(WAVE_TABLE_ID)[WAVE_TABLE_ID]  # WGO?

print("\n" + "=" * 50)
print(" PARÁMETROS DEL WAVE GENERATOR ")
print("=" * 50)
print(f"• Servo update time (SPA 0x0E000200): {t_servo_s * 1e6:.2f} µs")
print(f"• Número de generadores disponibles (TWG?): {num_generators}")
print(f"• Capacidad máxima de la tabla (WMS?): {max_points} puntos")
print(f"• Tasa de tabla (WTR?): {table_rate} ciclos de servo por punto")
print(f"• Duración por punto: {table_rate * t_servo_s * 1e6:.1f} µs")
print(f"• Ciclos de onda configurados (WGC?): {cycles} (0 = continuo)")
print(f"• Offset de salida (WOS?): {wave_offset} µm")
print(f"• Modo de inicio configurado (WGO?): {start_mode}")


# %% -- 3. Generación de onda de rampa lineal ('LIN') -----------------------
seg_length = 1000  # Puntos totales del segmento en la tabla
amp = 50.0  # Amplitud de barrido en µm (lazo cerrado)
segment_off = 0.0  # Offset propio dentro del segmento
wave_length = 1000  # Longitud de la rampa en puntos
start_point = 1  # Índice inicial del tramo (1-indexado)
speed_up_down = 120  # Puntos asignados a aceleración y desaceleración

print("\n" + "=" * 50)
print(" PROGRAMANDO ONDA 'LIN' EN TABLA DE ONDA ")
print("=" * 50)
print(
    f"Escribiendo rampa de {amp} µm en {seg_length} puntos (SpeedUpDown={speed_up_down})..."
)

# append='X' borra el contenido previo de la tabla y escribe desde el punto 1
pidevice.WCL(WAVE_TABLE_ID)
pidevice.WAV_LIN(
    table=WAVE_TABLE_ID,
    firstpoint=start_point,
    numpoints=wave_length,
    append="X",
    speedupdown=speed_up_down,
    amplitude=amp,
    offset=segment_off,
    seglength=seg_length,
)

# WAV? <tabla> 1 -> cantidad de puntos cargados en la tabla
points_written = int(pidevice.qWAV(WAVE_TABLE_ID, 1)[WAVE_TABLE_ID][1])
print(f"• Puntos actuales cargados en la tabla (WAV? 1 1): {points_written}")


# %% -- 4. Lectura de la tabla de onda con GWD? -----------------------------
# qGWD(tabla, punto_inicial, n_puntos)
pidevice.qGWD(WAVE_TABLE_ID, 1, points_written)
wave_array = _leer_array_gcs(pidevice)

print("\n" + "=" * 50)
print(" LECTURA DE TABLA CON GWD? ")
print("=" * 50)
print(f"• Puntos recuperados: {len(wave_array)}")
print(f"• Valor mínimo de la onda: {wave_array.min():.3f} µm")
print(f"• Valor máximo de la onda: {wave_array.max():.3f} µm")
print(f"• Primeros 5 puntos: {np.round(wave_array[:5], 3)}")
print(f"• Últimos 5 puntos: {np.round(wave_array[-5:], 3)}")


# %% -- 5. Graficación del perfil leído con GWD? ----------------------------
plt.figure(figsize=(10, 4.5))
plt.plot(wave_array, label=f"Rampa LIN ({amp} µm)", color="navy", linewidth=2)

# Destacar las regiones de aceleración y desaceleración (SpeedUpDown)
plt.axvspan(
    0, speed_up_down, color="orange", alpha=0.25, label="Aceleración (SpeedUpDown)"
)
plt.axvspan(
    seg_length - speed_up_down,
    seg_length,
    color="orange",
    alpha=0.25,
    label="Desaceleración",
)

plt.title(f"Perfil teórico de la rampa en Wave Table {WAVE_TABLE_ID} (leído con GWD?)")
plt.xlabel("Índice de punto en la tabla")
plt.ylabel("Posición objetivo (µm)")
plt.grid(True, linestyle="--", alpha=0.7)
plt.legend(loc="upper left")
plt.tight_layout()
plt.show()


# %% -- Cierre limpio --------------------------------------------------------
# cleanup_gcsdevice() (no pidevice.close() suelto) para poder volver a correr
# el script en la misma consola sin reiniciar el kernel.
cleanup_gcsdevice(pidevice)
print("\nDIAGNÓSTICO — fin")
