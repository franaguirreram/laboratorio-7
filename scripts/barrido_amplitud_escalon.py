#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Barrido de AMPLITUD del escalón — cuatro décadas, con repeticiones donde hace falta.

Por qué
-------
El barrido de rampa del 2026-09-09 dio e_ss ∝ v^0.851 sobre 2.5 décadas: el
"tau" cae de 26.3 a 10.6 ms. Pero en esa receta la velocidad y la amplitud
están CONFUNDIDAS (con RTR=1 y la tabla llenando la ventana, v = 4A/t_tabla
con t_tabla fijo ⇒ v ∝ A), así que no se sabe si el efecto es de velocidad o
de excursión.

El escalón separa las dos: **un escalón no tiene velocidad**. Si tau depende
de la amplitud, se ve acá; si sale plano acá, el efecto de la rampa es de
velocidad y hay que buscarlo en otro lado.

Qué cambia respecto del barrido de amplitud del 2026-09-07
----------------------------------------------------------
Aquel tenía 5 amplitudes (0.01 a 50 µm), RTR=5 (dt = 200 µs) y 2
repeticiones. Los puntos chicos salieron inservibles: con un salto de 20 nm
y ~1.3 nm de ruido a 50 Hz, una sola corrida no alcanza. Acá:

  · 13 amplitudes, de 10 nm a 100 µm  (4 décadas)
  · n_pre = 2000 → 80 ms de baseline (4 ciclos de 50 Hz), contra 2 ms.
  · RTR = 1  →  dt = 40 µs, la mejor resolución temporal posible.
    Hace falta para ver el arranque: el tiempo muerto es ~1 ms, o sea
    25 muestras a 40 µs y solo 5 a 200 µs.
  · repeticiones escaladas: 8 para los saltos chicos, 2 para los grandes.
    El análisis promedia las respuestas NORMALIZADAS antes de integrar.

58 corridas, ~8 min de equipo.

Uso:  ~/python-envs/pi/bin/python3 scripts/barrido_amplitud_escalon.py
"""

from E517_barrido import escalon, conectar, correr_barrido, cerrar, graficar_barrido

# saltos en µm (el escalón vale 2 × amplitud_um)
SALTOS_UM = (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0)
RTR = 1
N_PRE = 2000     # 80 ms de baseline ANTES del salto (contra los 2 ms de siempre)
                  # Con n_pre=50 el baseline dura 2 ms: menos de un décimo de un
                  # ciclo de 50 Hz. Sobre un escalón de 10 nm, con los 50 Hz
                  # valiendo 1.3 nm, de dónde caiga la fase del baseline
                  # decide un 13 % de la altura del escalón. 80 ms son 4
                  # ciclos completos: la mediana del baseline los promedia.
                  # El tramo posterior queda en 8192-2000 = 6192 puntos =
                  # 248 ms, todavía 7.5 × t_conv.


def repeticiones_para(salto_um):
    """Cuántas veces repetir cada salto.

    NO sale de un modelo de ruido blanco: con ruido blanco de 1.3 nm el área
    de un escalón de 20 nm tendría una incerteza de 0.1 ms, y la realidad es
    otra. Las cuatro corridas de 20 nm del 2026-09-07 dieron tau_area de
    17.1, 11.7, 6.6 y 3.2 ms — dispersión de ±40 %, no de ±1 %.

    Lo que domina en los saltos chicos no es el ruido de alta frecuencia
    (que la integral promedia sola) sino la DERIVA entre la ventana de
    baseline y la de integración: un corrimiento de 0.5 nm sobre un escalón
    de 20 nm es un 2.5 % de error de escala en y, y entra directo al área.
    Contra eso, repetir sí sirve — la deriva cambia de signo entre corridas —
    pero hace falta más que sqrt(N) de un modelo optimista.
    """
    if salto_um <= 0.05:  return 8
    if salto_um <= 0.2:   return 6
    if salto_um <= 2.0:   return 4
    return 2


def barrido_amplitud_escalon(saltos_um=SALTOS_UM, rtr=RTR):
    """PREGUNTA: ¿tau depende de la amplitud del escalón?

    Todo lo demás fijo: RTR=1, DCO off, misma ventana, mismo centro. La
    ÚNICA variable es el tamaño del salto. Si tau sale plano sobre cuatro
    décadas, el sistema es lineal y el efecto de la rampa es de velocidad.
    """
    return [escalon(rtr=rtr, n_pre=N_PRE, amplitud_um=salto / 2, dco=False,
                    repeticion=r, etiqueta=f"ampfino_{salto:g}um",
                    notas="amplitud del escalon: ¿tau(A) o tau constante?")
            for salto in saltos_um for r in range(repeticiones_para(salto))]


if __name__ == "__main__":
    corridas = barrido_amplitud_escalon()
    print(f"barrido de amplitud: {len(corridas)} corridas, RTR={RTR} "
          f"(dt = 40 µs, ventana 328 ms)\n")
    print(f"  {'salto':>9}  {'amplitud_um':>11}  {'recorrido':>18}  {'reps':>4}  {'SNR crudo':>9}")
    for s in SALTOS_UM:
        n = repeticiones_para(s)
        print(f"  {s:7g} µm  {s/2:+11.3f}  {100-s/2:7.2f} → {100+s/2:6.2f} µm  "
              f"{n:4d}  {s*1e3/1.3:9.0f}")
    print(f"\n  total: {len(corridas)} corridas")

    pidevice, ctx = conectar()
    try:
        df = correr_barrido(pidevice, ctx, corridas, nombre="amplitud_escalon")
        graficar_barrido(df, "salto_nm", "t_subida_10_90_ms",
                         nombre="amplitud_escalon", logx=True)
    finally:
        cerrar(pidevice, volver_a=100.0)
