#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Barrido de rampa para medir tau_lag  —  el que hay que correr.

Reemplaza a `barrido_wtr()` de E517_barrido.py, que barre WTR y por eso
rompe dos de las cuatro condiciones (ver notebooks/01_...ipynb §5):

    (a) RTR = 1                        -> ventana 328 ms, dt 40 us
    (b) n_total * WTR <= 8192          -> la tabla entra en la ventana
    (c) v = 2A / (n_total*WTR*40us)    -> con (a)+(b) la duracion esta
                                          clavada, asi que v ~ A:
                                          la velocidad se barre con la
                                          AMPLITUD, no con WTR
    (d) t_recta = (n_total/2 - sud)*WTR*40us >= t_conv + 50 ms = 83 ms
                                       -> speedupdown = 0

Con n_total=400, WTR=20:  tabla 320 ms (~ventana), tramo recto 160 ms.
Amplitudes 0.1 .. 30 um  ->  v = 0.6 .. 190 um/s  (2.5 decadas),
lag esperado e = v*tau = 8 nm .. 2.4 um.

12 corridas, ~2 min de equipo.

Uso:  ~/python-envs/pi/bin/python3 scripts/barrido_tau_rampa.py
"""

from E517_barrido import Corrida, conectar, correr_barrido, cerrar, graficar_barrido

AMPLITUDES_UM = (0.1, 0.3, 1.0, 3.0, 10.0, 30.0)
N_TOTAL, WTR, RTR = 400, 20, 1   # 400x20 = 8000 ticks = 320 ms ~ ventana
REPETICIONES = 2


def barrido_tau_rampa(amplitudes=AMPLITUDES_UM, n_total=N_TOTAL, wtr=WTR,
                      rtr=RTR, repeticiones=REPETICIONES):
    """PREGUNTA: ¿el lag de rampa da el mismo tau que el area del escalon?

    e_ss = v * tau_lag, con tau_lag = 1/Kv el MISMO numero que sale de
    integrar (1-y) en el escalon. Si los dos coinciden, el lazo queda
    descrito por un solo parametro y el test es falsable.
    """
    return [Corrida(modo="rampa", amplitud_um=A, n_total=n_total, wtr=wtr, rtr=rtr,
                    speedupdown=10, dco=False, repeticion=r,
                    etiqueta=f"tau_A{A:g}um",
                    notas="e=v*tau con RTR=1 y tramo recto > t_conv")
            for A in amplitudes for r in range(repeticiones)]


if __name__ == "__main__":
    t_tabla_ms  = N_TOTAL * WTR * 40e-3
    t_recta_ms  = (N_TOTAL / 2) * WTR * 40e-3
    ventana_ms  = 8192 * RTR * 40e-3
    print(f"tabla {t_tabla_ms:.0f} ms  |  ventana {ventana_ms:.0f} ms  "
          f"|  tramo recto {t_recta_ms:.0f} ms  (hace falta > 83 ms)")
    for A in AMPLITUDES_UM:
        v = 2 * A / (t_tabla_ms * 1e-3)
        print(f"   A = {A:5.1f} um  ->  v = {v:7.1f} um/s   e = v*tau = {v * 13.1:7.0f} nm")

    pidevice, ctx = conectar()
    try:
        df = correr_barrido(pidevice, ctx, barrido_tau_rampa(), nombre="tau_rampa")
        graficar_barrido(df, "v_um_s", "error_mediano_nm", nombre="tau_rampa",
                         logx=True, logy=True)
    finally:
        cerrar(pidevice, volver_a=100.0)
