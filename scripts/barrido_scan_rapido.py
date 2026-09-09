#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qué medir para escanear RÁPIDO y que el tramo siga siendo lineal.

========================================================================
EL NÚMERO QUE MANDA
========================================================================
Para un campo de tamaño L barrido a velocidad v, la fracción del recorrido
que sirve es

        eficiencia = 1 - v * t_conv / L

porque hay que descartar el arranque mientras el error de seguimiento
todavía crece hacia v*tau, y en ese tiempo la platina recorre v*t_conv.
Con t_conv = 33 ms [MEDIDO] y L = 2 µm:

        v =  12 µm/s  ->  eficiencia 80 %
        v =  30 µm/s  ->  eficiencia 50 %
        v =  60 µm/s  ->  eficiencia  0 %   (el transitorio se come el campo)

O sea que el techo NO lo pone el generador ni la resolución: lo pone
t_conv, que es una propiedad del LAZO. Subir WTR no ayuda -- WTR es el
knob de velocidad, no de asentamiento (ver escalones_wtr.py). La única
forma de escanear más rápido a la misma eficiencia es bajar tau.

Por eso el orden de las mediciones de acá abajo es:

  D. ¿tau es ajustable?   -- lo único que corre el techo. Va primero.
  A. techo de velocidad   -- dónde está el límite HOY, a campo fijo.
  C. resolución           -- hasta qué dx tiene sentido bajar.

Uso:
    ~/python-envs/pi/bin/python3 scripts/barrido_scan_rapido.py D   # solo lectura
    ~/python-envs/pi/bin/python3 scripts/barrido_scan_rapido.py A
    ~/python-envs/pi/bin/python3 scripts/barrido_scan_rapido.py C
"""
import sys

import numpy as np

from E517_barrido import (Corrida, conectar, correr_barrido, cerrar,
                          N_MAX_TABLA, T_CONV_MS, TAU_LAG_MS)

T_SERVO_US = 40.0


def _rtr_minimo(n_total, wtr):
    """La trayectoria entera tiene que entrar en las 8192 muestras."""
    return max(1, int(np.ceil(n_total * wtr / 8192)))


# ======================================================================
# D. ¿tau es ajustable?  (SOLO LECTURA -- no cambia nada)
# ======================================================================
def servo_params(pidevice):
    """Lista los parámetros del controlador y marca los del lazo.

    POR QUÉ ESTA ES LA MEDICIÓN MÁS IMPORTANTE
    ------------------------------------------
    tau = 13.1 ms es un ancho de banda de lazo cerrado de 1/(2*pi*tau) =
    12 Hz. Para una platina piezo con sensor capacitivo eso es MUY lento:
    el límite físico lo pone la resonancia mecánica, típicamente cientos
    de Hz. Si esos 12 Hz salen de una ganancia baja, de un notch o de un
    slew rate configurado -- y no de la mecánica -- entonces tau se puede
    bajar, y con tau baja TODO el resto mejora proporcionalmente: el lag
    v*tau, el desplazamiento 2*v*tau entre ida y vuelta, el descarte
    t_conv, y por lo tanto la velocidad máxima a eficiencia dada.

    Nunca lo miramos: E517_diagnostico.py lee UN solo parámetro (el ciclo
    de servo, 0x0E000200). Este primer paso es puramente de lectura y no
    toca nada.

    ⚠ EL PASO SIGUIENTE NO ES INOFENSIVO. Subir la ganancia de un lazo
    piezo lo puede poner a oscilar, y una platina oscilando a cientos de
    Hz con amplitud creciente se daña. Cuando sepamos qué parámetros
    expone este equipo, el barrido de ganancia hay que hacerlo:
      - anotando ANTES los valores de fábrica de cada parámetro que se
        toque, para poder volver;
      - en pasos chicos (10-20 % por vez), no en saltos;
      - mirando el escalón después de CADA paso: apenas aparezca
        sobrepico u oscilación, se volvió atrás y ése es el límite;
      - con amplitud chica (0.1-1 µm), para que una oscilación no llegue
        a excursiones grandes.
    """
    print("\n=== parámetros disponibles (qHPA) ===")
    try:
        print(pidevice.qHPA())
    except Exception as exc:
        print(f"  qHPA no disponible: {exc}")
    print("\n=== ciclo de servo (el único que veníamos leyendo) ===")
    try:
        print(f"  0x0E000200 = {pidevice.qSPA(1, 0x0E000200)}")
    except Exception as exc:
        print(f"  {exc}")
    print(f"\ntau actual = {TAU_LAG_MS} ms  ->  ancho de banda "
          f"1/(2*pi*tau) = {1/(2*np.pi*TAU_LAG_MS*1e-3):.1f} Hz")
    print("Si el equipo expone P/I del lazo, notch o slew rate, ahí está el "
          "margen.\nEl barrido de ganancia se escribe DESPUÉS de leer esto, "
          "no antes.")


# ======================================================================
# A. techo de velocidad a campo fijo
# ======================================================================
def barrido_techo_velocidad(amplitud_um=1.0, n_total=400,
                            wtrs=(1, 2, 3, 5, 8, 12, 20, 40), repeticiones=2):
    """PREGUNTA: a campo FIJO, ¿hasta qué velocidad el tramo sigue siendo
    lineal dentro de medio píxel, y cuánto hay que descartar?

    Esto es distinto del barrido_tau_rampa que ya está medido. Ahí la
    amplitud crecía junto con la velocidad, así que el transitorio se comía
    siempre la misma FRACCIÓN (79 % de eficiencia en las siete amplitudes,
    de 0.7 a 377 µm/s) y el techo nunca aparecía. Acá el campo queda fijo en
    2*amplitud y sólo cambia v: la eficiencia tiene que derrumbarse, y el
    punto donde se derrumba es el dato.

    speedupdown=0 a propósito: agrega transitorio y acorta el tramo recto
    sin aportar nada (ver la tabla de sudes en tramos_lineales_90.py).

    RTR se elige para que la trayectoria entre en las 8192 muestras del
    recorder, pero lo más chico posible: hay que RESOLVER el arranque del
    tramo para medir cuánto descartar, y ésa es justamente la parte rápida.

    Qué se mira después, sobre cada corrida:
      - el descarte REAL: desde qué instante el residuo a una recta se
        queda por debajo de dx/2, en vez de asumir los 33 ms;
      - la eficiencia resultante = recorrido usable / 2*amplitud;
      - si tau sigue valiendo lo mismo (e/v) a esta velocidad.
    """
    dx_nm = 2 * amplitud_um / n_total * 1e3
    cfgs = []
    for w in wtrs:
        v = dx_nm * 1e-3 / (w * T_SERVO_US * 1e-6)          # µm/s
        cfgs += [Corrida(modo="rampa", amplitud_um=amplitud_um,
                         n_total=n_total, speedupdown=0, wtr=w,
                         rtr=_rtr_minimo(n_total, w), dco=False, vco=False,
                         repeticion=r, etiqueta=f"rapido_w{w}",
                         notas=f"techo de v a campo fijo: dx={dx_nm:.2f} nm, "
                               f"v={v:.1f} um/s, eficiencia esperada "
                               f"{100*max(0, 1 - v*T_CONV_MS*1e-3/(2*amplitud_um)):.0f} %")
                 for r in range(repeticiones)]
    return cfgs


# ======================================================================
# C. resolución: hasta qué dx tiene sentido bajar
# ======================================================================
def barrido_resolucion(amplitud_um=1.0, v_objetivo_um_s=12.0,
                       n_totales=(200, 400, 800, 1600, 4000, 8000),
                       repeticiones=2):
    """PREGUNTA: ¿a partir de qué dx los píxeles de más no agregan nada?

    El sensor tiene ~1.3 nm rms de ruido [MEDIDO en la cola quieta de las
    corridas de rampa]. Pedir dx = 0.25 nm no da más información: da cinco
    veces más puntos del mismo ruido. El dato que falta es DÓNDE está ese
    cruce, medido y no supuesto.

    Se barre n_total a amplitud fija (dx = 2*amplitud/n_total) y se ajusta
    WTR para que la VELOCIDAD quede igual en todas: así lo único que cambia
    es el tamaño del píxel, y el lag v*tau es el mismo para todas.

    El techo duro es N_MAX_TABLA = 8192 puntos por tabla.
    """
    cfgs = []
    for n in n_totales:
        if n > N_MAX_TABLA:
            print(f"  [salteado] n_total={n} > {N_MAX_TABLA}")
            continue
        dx_nm = 2 * amplitud_um / n * 1e3
        wtr = max(1, int(round(dx_nm * 1e-3 / v_objetivo_um_s / (T_SERVO_US * 1e-6))))
        v_real = dx_nm * 1e-3 / (wtr * T_SERVO_US * 1e-6)
        cfgs += [Corrida(modo="rampa", amplitud_um=amplitud_um, n_total=n,
                         speedupdown=0, wtr=wtr, rtr=_rtr_minimo(n, wtr),
                         dco=False, vco=False, repeticion=r,
                         etiqueta=f"resol_n{n}",
                         notas=f"dx={dx_nm:.2f} nm (ruido 1.3 nm rms), "
                               f"wtr={wtr} -> v={v_real:.1f} um/s")
                 for r in range(repeticiones)]
    return cfgs


# ======================================================================
def main(cuales):
    pidevice, ctx = conectar()
    try:
        if "D" in cuales:
            servo_params(pidevice)
        if "A" in cuales:
            correr_barrido(pidevice, ctx, barrido_techo_velocidad(),
                           nombre="scan_rapido_techo")
        if "C" in cuales:
            correr_barrido(pidevice, ctx, barrido_resolucion(),
                           nombre="scan_rapido_resolucion")
    finally:
        cerrar(pidevice)


if __name__ == "__main__":
    cuales = [a.upper() for a in sys.argv[1:]] or ["D"]
    main(cuales)
