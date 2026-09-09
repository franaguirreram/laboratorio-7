#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""El escalón de la VUELTA — cuánto cuesta el flyback de un scan unidireccional.

Por qué hace falta
------------------
En un scan de una sola dirección cada línea son tres tramos:

    [ pre-roll ]────────[ ROI ]────────[ vuelta ]
      t_conv=33ms    N_px · t_dwell       ¿?

El pre-roll está MEDIDO (t_conv = 33 ms, notebooks/01_...ipynb §5). La
vuelta NO: el presupuesto de tiempo del scan la asume igual al pre-roll
*por linealidad* — el escalón tarda lo mismo para 200 nm que para 100 µm,
así que volver 10 µm debería costar los mismos 33 ms. Es una inferencia
razonable y sin medir. Este script la mide.

Y de paso contesta algo que la linealidad NO garantiza: **¿la vuelta cuesta
lo mismo que la ida?** En un scan unidireccional el flyback va SIEMPRE para
el mismo lado, así que cualquier asimetría entre subir y bajar se acumula
como un corrimiento sistemático línea a línea. Por eso cada amplitud se
mide en los dos sentidos.

Qué corre
---------
saltos de 2, 10 y 20 µm × {ida, vuelta} × 2 repeticiones = 12 corridas.
Cada una con RTR=1 (dt = 40 µs, ventana 328 ms = 10× t_conv) y la
trayectoria llenando la ventana entera, vía el helper escalon().

Cómo se lee
-----------
Los archivos salen como `E517_escalon_vuelta_*` y el notebook los levanta
solos: aparecen en la tabla de la Parte 1 con su propio tau_area. Lo que
hay que mirar es si la fila `vuelta_baja_*` da lo mismo que `vuelta_sube_*`.

Uso:  ~/python-envs/pi/bin/python3 scripts/barrido_vuelta.py
"""

from E517_barrido import (escalon, conectar, correr_barrido, cerrar,
                          graficar_barrido, T_CONV_MS)

SALTOS_UM = (2.0, 10.0, 20.0)     # tamaño del escalón (2 × amplitud)
RTR = 1                            # dt = 40 µs, ventana 328 ms
REPETICIONES = 2


def barrido_vuelta(saltos_um=SALTOS_UM, rtr=RTR, repeticiones=REPETICIONES):
    """PREGUNTA: ¿cuánto tarda el flyback, y cuesta lo mismo para los dos lados?

    `amplitud_um` NEGATIVA da un escalón hacia abajo: en modo 'escalon' la
    tabla son dos tramos planos con offsets explícitos (x_i = centro - A,
    x_f = centro + A), así que el signo de A solo intercambia origen y
    destino. No es el caso de WAV_RAMP, donde una amplitud negativa NO da
    una rampa descendente en este firmware [MEDIDO 2026-08-28].
    """
    corridas = []
    for salto in saltos_um:
        for signo, nombre in ((+1, "sube"), (-1, "baja")):
            for r in range(repeticiones):
                corridas.append(escalon(
                    rtr=rtr, amplitud_um=signo * salto / 2, dco=False,
                    etiqueta=f"vuelta_{nombre}_{salto:g}um", repeticion=r,
                    notas=("flyback del scan unidireccional: t_conv y simetría "
                           "ida/vuelta a la amplitud real de una línea")))
    return corridas


if __name__ == "__main__":
    print(f"vuelta: {len(barrido_vuelta())} corridas  |  "
          f"RTR={RTR} → dt=40 µs, ventana 328 ms  |  "
          f"referencia a batir: t_conv = {T_CONV_MS:.0f} ms")
    for s in SALTOS_UM:
        print(f"   salto {s:5.1f} µm  →  amplitud_um = ±{s/2:.1f}  "
              f"(recorrido {100-s/2:.1f} ↔ {100+s/2:.1f} µm)")

    pidevice, ctx = conectar()
    try:
        df = correr_barrido(pidevice, ctx, barrido_vuelta(), nombre="vuelta")
        graficar_barrido(df, "salto_nm", "t_subida_10_90_ms", nombre="vuelta",
                         logx=True)
    finally:
        cerrar(pidevice, volver_a=100.0)
