#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sesión del 2026-09-09 — los cuatro experimentos, en orden de prioridad.

Ordenados por QUÉ PUEDE ARRUINAR UNA IMAGEN, no por qué es más fácil.

  0. mapeo generador↔eje   descubrimiento, no medición. Bloquea al 3.
  1. tau por rampa         cierra el test escalón↔rampa (hoy n=8, factor 2 en v)
  2. vuelta (flyback)      cierra el presupuesto de tiempo de la línea
  3. diafonía x↔y          distorsión geométrica: no la verías como ruido
  4. tau del eje B         el eje lento hace un escalón por línea

Total ~25 min de equipo. El 4 solo corre si el 0 dice que se puede.

Uso:
    ~/python-envs/pi/bin/python3 scripts/sesion_hoy.py          # todo
    ~/python-envs/pi/bin/python3 scripts/sesion_hoy.py 1 2      # solo esos
"""

import sys

import numpy as np
import pandas as pd

from E517_barrido import (Corrida, escalon, conectar, correr_barrido, cerrar,
                          graficar_barrido, corrida, T_CONV_MS, TAU_LAG_MS)
from barrido_tau_rampa import barrido_tau_rampa
from barrido_vuelta import barrido_vuelta


# %% -- 0. ¿qué generador mueve qué eje? ----------------------------------
def descubrir_generador_eje(pidevice, ctx, wavegen=2, tabla=2, amplitud_um=0.5,
                            confirmar=False):
    """Este firmware NO implementa WSL: el mapeo generador↔tabla es FIJO y,
    para los generadores 2 y 3, DESCONOCIDO [MEDIDO 2026-09-07].

    Todo lo medido hasta hoy usó generador 1 / tabla 1, que mueve el eje A.
    Para medir cualquier cosa del eje B hay que averiguar primero cuál es su
    generador — no se puede elegir, solo descubrir. El experimento es
    trivial: cargar una rampa chica en la tabla 2, disparar el generador 2,
    y grabar la posición de LOS DOS ejes. Se mueve uno, y ése es.

    Amplitud 0.5 µm: suficiente para verse sobre el ruido (2 nm) por un
    factor 250.

    ⚠ POR QUÉ PIDE CONFIRMACIÓN EXPLÍCITA
    -------------------------------------
    El experimento dispara un generador cuyo destino no conocemos — ése es
    justamente el punto. Si el generador 2 resulta estar atado al eje C
    (qPOS lo da en −19.3 µm, y qSVO dice C=False, o sea LAZO ABIERTO), el
    generador no comanda posición sino VOLTAJE, y un valor de ~100 es 100 V:
    fondo de escala de un eje sin sensor. Eso no lo puede prevenir
    `_validar_rango`, que solo sabe de µm.

    Los dos casos benignos (gen 2 → A, o gen 2 → B) son inofensivos: los dos
    ejes están en 100.0 µm y en lazo cerrado, y la wave va de 99.5 a 100.5.

    Antes de poner confirmar=True conviene mirar qué hay conectado en C. Si
    C no tiene actuador físico, no hay riesgo y esto es un trámite de 5 s.
    """
    if not confirmar:
        print("  saltado: descubrir el mapeo dispara un generador de destino "
              "desconocido.\n  Si el eje C no tiene actuador conectado, "
              "correr con confirmar=True.\n  qSVO actual:", dict(pidevice.qSVO()),
              " qPOS:", {k: round(v, 3) for k, v in pidevice.qPOS().items()})
        return None
    cfg = Corrida(modo="rampa", amplitud_um=amplitud_um, n_total=400,
                  wtr=20, rtr=1, speedupdown=0, dco=False,
                  tabla=tabla, wavegen=wavegen,
                  drc_tablas=(1, 2, 3), drc_fuentes=("A", "B", "A"),
                  drc_opciones=(2, 2, 1),
                  etiqueta=f"mapeo_gen{wavegen}_tabla{tabla}",
                  notas="¿qué eje mueve el generador 2? WSL no existe en este firmware")
    fila = corrida(pidevice, cfg, ctx)
    if not fila.get("ok"):
        print("  [!] la corrida de descubrimiento falló — el eje B queda sin medir")
        return None

    df = pd.read_csv(f"datos/raw/{fila['archivo']}.csv")
    rec = {}
    for eje, col in (("A", "current_um_A"), ("B", "current_um_B")):
        if col in df:
            rec[eje] = (df[col].max() - df[col].min()) * 1e3      # nm
    print(f"\n  excursión grabada durante el disparo del generador {wavegen}:")
    for eje, exc in rec.items():
        print(f"     eje {eje}: {exc:8.1f} nm")
    esperado = 2 * amplitud_um * 1e3
    movidos = [e for e, x in rec.items() if x > 0.5 * esperado]
    if len(movidos) == 1:
        print(f"  →  generador {wavegen} / tabla {tabla}  mueve el eje {movidos[0]}")
        return movidos[0]
    print(f"  →  ambiguo (esperaba ~{esperado:.0f} nm en un solo eje): {rec}")
    return None


# %% -- 3. diafonía x↔y ---------------------------------------------------
def barrido_diafonia(amplitudes_um=(1.0, 10.0), n_total=400, wtr=20, rtr=1,
                     repeticiones=2):
    """PREGUNTA: cuando barrés x, ¿se mueve y?

    Es el experimento que ya hacés, con UNA línea de config distinta: en vez
    de grabar (target_A, current_A, error_A) se graba
    (target_A, current_A, current_B).

    Por qué es el primero de la lista de x-y, antes que cualquier raster: la
    diafonía no se ve como ruido, se ve como ESTRUCTURA. Una imagen con
    y = f(x) sale con la geometría deformada de una forma que parece real y
    que no tenés cómo desmentir mirando la imagen. Y si existe, hay que
    saberlo ANTES de diseñar el raster, no después de tomarlo.

    Dos amplitudes para separar las dos diafonías posibles:
      · geométrica (y ∝ x, un cabeceo mecánico): escala con la amplitud
      · dinámica  (y ∝ dv/dt, reacción a la aceleración): escala con v²/A
    Y una corrida QUIETA con la misma grabación, que es el control: sin ella
    no sabés si lo que ves en B es diafonía o la deriva de la oficina.
    """
    corridas = [
        Corrida(modo="quieto", n_total=n_total, wtr=wtr, rtr=rtr, dco=False,
                drc_tablas=(1, 2, 3), drc_fuentes=("A", "A", "B"),
                drc_opciones=(1, 2, 2),
                etiqueta="diafonia_control_quieto", repeticion=0,
                notas="control: cuánto se mueve B con A quieto (ruido + deriva)")
    ]
    for A in amplitudes_um:
        for r in range(repeticiones):
            corridas.append(Corrida(
                modo="rampa", amplitud_um=A, n_total=n_total, wtr=wtr, rtr=rtr,
                speedupdown=0, dco=False,
                drc_tablas=(1, 2, 3), drc_fuentes=("A", "A", "B"),
                drc_opciones=(1, 2, 2),
                etiqueta=f"diafonia_A{A:g}um", repeticion=r,
                notas="barre A, graba A y B: y(x) durante un barrido en x"))
    return corridas


# %% -- 4. tau del eje B --------------------------------------------------
def barrido_tau_ejeB(wavegen, tabla, rtr=1, repeticiones=2):
    """Este notebook entero mide el eje A. El eje B es el LENTO de un raster:
    hace un escalón por línea, y ese escalón está en el camino crítico.

    Nada garantiza que tau_B = tau_A. Son piezos distintos, con masas
    distintas encima, y el PI del E-802.55 es analógico con potenciómetros
    calibrados en fábrica *por canal*. Medirlo es correr este mismo escalón
    apuntando al otro generador.
    """
    return [escalon(rtr=rtr, amplitud_um=1.0, dco=False,
                    tabla=tabla, wavegen=wavegen,
                    drc_tablas=(1, 2, 3), drc_fuentes=("B", "B", "B"),
                    drc_opciones=(1, 2, 3),
                    etiqueta="tau_ejeB", repeticion=r,
                    notas="mismo escalón de 2 µm que el eje A, para comparar tau")
            for r in range(repeticiones)]


# %% -- runner ------------------------------------------------------------
if __name__ == "__main__":
    pedidos = set(sys.argv[1:]) or {"0", "1", "2", "3", "4"}
    print(f"referencias medidas: tau_lag = {TAU_LAG_MS} ms, t_conv = {T_CONV_MS} ms\n")

    pidevice, ctx = conectar()
    eje_gen2 = None
    try:
        if "0" in pedidos:
            print("\n=== 0. mapeo generador↔eje =========================")
            # confirmar=True solo después de verificar qué hay en el eje C
            eje_gen2 = descubrir_generador_eje(pidevice, ctx, confirmar=False)

        if "1" in pedidos:
            print("\n=== 1. tau por rampa (barrer AMPLITUD, no WTR) =====")
            df = correr_barrido(pidevice, ctx, barrido_tau_rampa(), nombre="tau_rampa")
            graficar_barrido(df, "v_um_s", "error_mediano_nm", nombre="tau_rampa",
                             logx=True, logy=True)

        if "2" in pedidos:
            print("\n=== 2. vuelta / flyback ============================")
            correr_barrido(pidevice, ctx, barrido_vuelta(), nombre="vuelta")

        if "3" in pedidos:
            print("\n=== 3. diafonía x↔y ================================")
            correr_barrido(pidevice, ctx, barrido_diafonia(), nombre="diafonia")

        if "4" in pedidos:
            print("\n=== 4. tau del eje B ===============================")
            if eje_gen2 == "B":
                correr_barrido(pidevice, ctx, barrido_tau_ejeB(2, 2), nombre="tau_ejeB")
            else:
                print("  saltado: el paso 0 no confirmó que el generador 2 mueva "
                      "el eje B. Sin eso, disparar una tabla sobre B es a ciegas.")
    finally:
        cerrar(pidevice, volver_a=100.0)
