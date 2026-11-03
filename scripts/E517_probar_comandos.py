#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
E-517 (E-545) — ¿Qué comandos de las macros 'unidir'/'scan' acepta el firmware?

Dentro de una macro los errores no se ven (y MAC ERR? no contesta en este
firmware), así que acá se manda cada línea POR SEPARADO, fuera de una macro,
y se lee ERR? después de cada una.

1. HLP? -> lista de comandos que el firmware dice soportar.
2. Consultas sueltas (MAC ERR?, #3, #8) con timeout corto: si una consulta
   no está soportada, el controlador NO contesta y se ve como timeout.
3. Cada línea de las macros con su ERR?.

ATENCIÓN: mueve la platina (MOV A 0 B 0, WGO 1 17 durante 2 s, MVR B 2).
No usa DEL 10000 ni MAC NSTART.

Misma conexión que E517_diagnostico.py (gateway FTDI).
"""

# %% -- Imports y conexión --------------------------------------------------
import time
from pipython import GCSDevice
from pipython.pidevice.gcserror import GCSError
from pi_ftdi_gateway import PIFtdiGateway, cleanup_gcsdevice

pidevice = GCSDevice('E-517', gateway=PIFtdiGateway())
print(f"Conectado a: {pidevice.qIDN().strip()}")


def _vaciar_buffer(pidevice, espera_s=0.3):
    """Descarta respuestas atrasadas después de un timeout."""
    interfaz = pidevice.gcsdevice.messages.interface
    time.sleep(espera_s)
    while interfaz.read():
        time.sleep(0.05)
    interfaz.flush()


# %% -- 1. HLP?: comandos que el firmware dice soportar ----------------------
print("\n" + "=" * 60)
print(" HLP? ")
print("=" * 60)
print(pidevice.qHLP())


# %% -- 2. Consultas sueltas (sin respuesta = no soportada) ------------------
print("=" * 60)
print(" CONSULTAS ")
print("=" * 60)
timeout_original = pidevice.timeout
pidevice.timeout = 2000   # ms
for nombre, cmd in [("MAC ERR?", "MAC ERR?"), ("#3 (posición)", chr(3)),
                    ("#8 (¿macro corriendo?)", chr(8)), ("POS?", "POS?")]:
    try:
        resp = pidevice.ReadGCSCommand(cmd)
        print(f"    OK    {nombre:<24} -> {resp.strip()!r}")
    except GCSError as e:
        print(f"    FAIL  {nombre:<24} -> {e}")
        _vaciar_buffer(pidevice)
pidevice.timeout = timeout_original
pidevice.qERR()   # limpia el error que hayan dejado las consultas


# %% -- 3. Cada línea de las macros, con ERR? -------------------------------
LINEAS = [
    # de 'scan'
    "ONL 1 1 2 1",
    "SVO A 1 B 1",
    "VEL A 100 B 100",
    "MOV A 0 B 0",
    "WGC 1 5",
    # de 'unidir'
    "WGO 1 0",
    "WAV 1 X POL 3846 3846 0 2 0",
    "WAV 1 X POL 0 3846 0 0 0",
    "WAV 1 X CFG 7692 1 0 5 2 10",
    "WGO 1 17",
    "WGO 1 0",          # se detiene a los 2 s (ver abajo)
    "MVR B 2",
    "DEL 100",
]

print("\n" + "=" * 60)
print(" LÍNEAS DE LAS MACROS (cada una con ERR?) ")
print("=" * 60)
for linea in LINEAS:
    try:
        pidevice.send(linea)     # send() lee ERR? y levanta GCSError si != 0
        print(f"    OK    {linea}")
    except GCSError as e:
        print(f"    FAIL  {linea:<30} -> {e}")
    if linea == "WGO 1 17":
        time.sleep(2.0)          # dejar correr el generador un rato

print(f"\n[qPOS final] {dict(pidevice.qPOS(['A', 'B']))}")
print(f"[qWAV 1 1]   {pidevice.qWAV(1, 1)}   # puntos cargados en la tabla 1")


# %% -- Cierre limpio --------------------------------------------------------
cleanup_gcsdevice(pidevice)
print("\nFin.")
