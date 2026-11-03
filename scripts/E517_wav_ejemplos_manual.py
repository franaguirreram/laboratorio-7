#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
E-517 — Ejemplos de WAV del manual (sección 8.2.1 "Defining Waveforms").

Manda cada comando WAV tal cual está escrito en el manual (string GCS crudo
con pidevice.send), y después de cada uno relee la tabla con qGWD y la grafica.

Sólo escribe wave tables: NO arranca el wave generator (no hay WGO), así que
la platina no se mueve.

Misma conexión que E517_diagnostico.py (gateway FTDI).

Uso en Spyder:
    Python Interpreter debe apuntar a ~/python-envs/pi/bin/python3.12
    Correr por celdas (#%%) o de arriba a abajo.
"""

# %% -- Imports y conexión --------------------------------------------------
import time
import numpy as np
import matplotlib.pyplot as plt
from pipython import GCSDevice
from pi_ftdi_gateway import PIFtdiGateway, cleanup_gcsdevice

pidevice = GCSDevice('E-517', gateway=PIFtdiGateway())
print(f"Conectado a: {pidevice.qIDN().strip()}")
print(f"Wave tables: máx. puntos por tabla (WMS?) = {pidevice.qWMS()}")


# %% -- Helpers -------------------------------------------------------------
def _leer_array_gcs(pidevice, timeout=10.0):
    """qGWD devuelve sólo el header; los datos llegan por bufdata."""
    t0 = time.time()
    while pidevice.bufstate is not True:
        if time.time() - t0 > timeout:
            raise TimeoutError("bufstate no llegó a True")
        time.sleep(0.005)
    return np.array(pidevice.bufdata[0])


def leer_tabla(tabla):
    """Lee la wave table completa: WAV? <tabla> 1 da cuántos puntos tiene."""
    n = int(pidevice.qWAV(tabla, 1)[tabla][1])
    pidevice.qGWD(tabla, 1, n)
    return _leer_array_gcs(pidevice)


# %% -- Comandos del manual (8.2.1) ------------------------------------------
# (comando, descripción corta)
COMANDOS = [
    # SIN_P: WAV <T> <X|&> SIN_P <SegLength> <Amp> <Offset> <WaveLength> <StartPoint> <CurveCenterPoint>
    ("WAV 1 X SIN_P 2000 20 10 2000 0 1000",    "SIN_P simétrico básico"),
    ("WAV 1 X SIN_P 2000 30 0 2000 499 1000",   "SIN_P con StartPoint=499"),
    ("WAV 1 & SIN_P 2000 25 0 1800 100 900",    "SIN_P concatenado (&), WaveLength<SegLength"),
    ("WAV 1 X SIN_P 4000 20 0 4000 0 3100",     "SIN_P asimétrico (centro 3100)"),
    ("WAV 1 X SIN_P 1000 -30 45 1000 0 500",    "SIN_P amplitud negativa"),
    # RAMP: WAV <T> <X|&> RAMP <SegLength> <Amp> <Offset> <WaveLength> <StartPoint> <SpeedUpDown> <CurveCenterPoint>
    ("WAV 1 X RAMP 2000 20 10 2000 0 100 1000", "RAMP simétrica estándar"),
    ("WAV 1 X RAMP 2000 35 0 2000 499 100 1000", "RAMP con StartPoint=499"),
    ("WAV 1 X RAMP 2000 15 0 1800 120 50 900",  "RAMP con meseta (WaveLength<SegLength)"),
    ("WAV 1 & RAMP 3000 35 0 3000 0 200 2250",  "RAMP concatenada (&), asimétrica"),
    # LIN: WAV <T> <X|&> LIN <SegLength> <Amp> <Offset> <WaveLength> <StartPoint> <SpeedUpDown>
    ("WAV 1 X LIN 1500 30 15 1500 0 370",       "LIN simple con offset"),
    ("WAV 1 X LIN 1500 40 0 1100 210 180",      "LIN con meseta final"),
    ("WAV 1 & LIN 3000 -40 50 3000 0 650",      "LIN de vuelta concatenada (&)"),
]


# %% -- Ejecutar cada comando y releer la tabla -----------------------------
resultados = []   # (comando, descripción, array o None)

for cmd, desc in COMANDOS:
    tabla = int(cmd.split()[1])
    print(f"\n>>> {cmd}   # {desc}")
    try:
        pidevice.send(cmd)          # send() ya chequea ERR? y levanta GCSError si falla
        time.sleep(0.1)  # esperar a que el hilo de qGWD termine de llenar bufdata
        datos = leer_tabla(tabla)
        print(f"    OK   tabla {tabla}: {len(datos)} puntos, "
              f"min={datos.min():.3f}, max={datos.max():.3f}, "
              f"primero={datos[0]:.3f}, último={datos[-1]:.3f}")
        resultados.append((cmd, desc, datos))
    except Exception as e:
        print(f"    FAIL -> {type(e).__name__}: {e}")
        resultados.append((cmd, desc, None))


# %% -- Graficar: un panel por comando (estado de la tabla después de él) ---
n = len(resultados)
ncols = 3
nrows = int(np.ceil(n / ncols))
fig, axs = plt.subplots(nrows, ncols, figsize=(15, 3.2 * nrows), squeeze=False)

for ax, (cmd, desc, datos) in zip(axs.flat, resultados):
    if datos is None:
        ax.text(0.5, 0.5, "FALLÓ", ha='center', va='center', color='red',
                transform=ax.transAxes)
    else:
        ax.plot(datos, lw=1.5)
    ax.set_title(f"{cmd}\n{desc}", fontsize=8)
    ax.set_xlabel("punto", fontsize=8)
    ax.set_ylabel("µm", fontsize=8)
    ax.grid(True, ls='--', alpha=0.5)

for ax in list(axs.flat)[n:]:
    ax.set_visible(False)

fig.tight_layout()
plt.show()


# %% -- Cierre limpio --------------------------------------------------------
cleanup_gcsdevice(pidevice)
print("\nFin.")

# %%
