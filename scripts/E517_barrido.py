#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
E-517 / E-545 — Banco de medición parametrizado (una corrida = una llamada)

Reescritura desde cero de E517_step_response.py + E517_ida_vuelta_speedupdown.py
en una sola función `corrida(pidevice, cfg)` pensada para llamarse dentro de un
`for`, y así barrer parámetros sin tocar el código entre medición y medición.

========================================================================
POR QUÉ ESTE SCRIPT EXISTE (qué se aprendió y qué se arregla acá)
========================================================================
Ver docs/velocidad_ancho_de_banda_y_diseno_de_scans.md para el análisis
completo. Los cinco puntos que motivan esta reescritura:

1. [ARREGLADO] `T_SERVO_US` era una constante escrita a mano en cada script
   (10.0 en unos, 40.0 en otros) que NUNCA se le mandaba al controlador:
   solo etiquetaba el eje temporal del CSV. Resultado: 20 corridas del
   01/09 con la columna `t_ms` mal escalada por un factor 4 o 40 (§2 y §7
   del doc). Acá el tiempo de ciclo de servo se LEE del equipo
   (`qSPA(1, 0x0E000200)`) una sola vez al conectar y se usa en todos lados.
   Ya no es un parámetro del experimento: es una propiedad del hardware.

2. [ARREGLADO] El eje temporal se construye con `RTR`, no con el ciclo de
   servo pelado:  `dt_grabación = RTR × T_servo`. Con RTR=1 daba igual;
   apenas se usa RTR>1 (que es lo que hay que hacer, ver punto 4) la
   fórmula vieja queda mal por un factor RTR.

3. [ARREGLADO] `WSL` — la conexión generador↔tabla — nunca se había llamado
   en este proyecto: todos los scripts asumían tabla 1 ↔ generador 1 sin
   verificarlo (ítem 1 de "Próxima sesión" del protocolo). Acá se llama
   explícitamente y se verifica con `qWSL` antes de cada corrida, y el
   mapeo real queda escrito en la metadata. Es prerrequisito duro para el
   raster de dos generadores (X + Y).

4. [ARREGLADO] Se barría `N_TOTAL` creyendo que cambiaba la resolución
   temporal. No la cambia: con RTR fijo, `N_TOTAL` solo recorta o estira
   la ventana, y la ventana está topeada en `8192 × RTR × T_servo` (§8.1).
   El knob real para ver más tiempo sin perder resolución en la subida es
   **RTR**. Acá `RTR` es un parámetro de primera clase de cada corrida, y
   el script imprime/guarda la ventana y la resolución efectivas.

5. [ARREGLADO] El estado de `DCO` no quedaba registrado en ningún lado
   (§8.3): de 24 corridas de escalón, solo 6 tienen el DCO confirmado.
   Acá `DCO` es un parámetro explícito de la corrida, se aplica al
   controlador, y además se RELEE con `qDCO` y se guarda en la metadata —
   igual que `SVO`, `VCO`, `WSL`, `WTR`, `RTR`, `DRC` y el ciclo de servo.
   La metadata describe lo que el equipo estaba haciendo, no lo que el
   código creía.

========================================================================
QUÉ CONVIENE BARRER (y qué no)
========================================================================
    parámetro    | qué cambia físicamente                 | ¿sirve barrerlo?
    -------------|----------------------------------------|------------------
    WTR          | dwell por punto → VELOCIDAD del scan   | SÍ (rampas)
                 |   v = Δx_punto / (WTR × T_servo)       |
    RTR          | ventana y resolución de la GRABACIÓN   | SÍ (escalones)
                 |   ventana = 8192 × RTR × T_servo       |
    amplitud     | tamaño del escalón / excursión         | SÍ (linealidad)
    DCO          | compensación de deriva on/off          | SÍ (el efecto más
                 |                                        |   grande medido)
    speedupdown  | suavizado de la esquina de la rampa    | SÍ (sobrepico)
    -------------|----------------------------------------|------------------
    N_TOTAL      | solo la LARGO de la trayectoria        | no por sí solo
    T_SERVO_US   | nada: no se le manda al controlador    | NO (resultado nulo)

Piso de significancia medido para comparar corridas: repitiendo el mismo
punto físico, el error mediano varía ±23 % (§7). Diferencias menores no
son diferencias.

========================================================================
CÓMO SE USA
========================================================================
Spyder, por celdas (#%%). La celda de conexión se corre UNA vez; después
se corre la celda del barrido que se quiera (o se escribe uno nuevo):

    pidevice, ctx = conectar()
    filas = correr_barrido(pidevice, ctx, barrido_rtr_dco(), nombre="rtr_dco")
    cerrar(pidevice)

`correr_barrido` guarda, por cada corrida, CSV crudo + metadata (como
siempre), y además un CSV de RESUMEN con una fila por corrida y todas las
métricas — que es lo que después se grafica sin volver a tocar el hardware.

Trazabilidad de comentarios:
    [MEDIDO]     verificado contra el hardware o contra datos de este repo
    [VERIFICAR]  hay que confirmarlo antes de confiar
    [ELEGIDO]    decisión de diseño, no un hecho físico
"""

# %% -- Imports y rutas ---------------------------------------------------
from dataclasses import dataclass, field, asdict, replace
from datetime import datetime
from pathlib import Path
import time
import traceback

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from pipython import GCSDevice, pitools
from pi_ftdi_gateway import PIFtdiGateway, cleanup_gcsdevice

REPO_ROOT = Path(__file__).resolve().parent.parent
DATOS_RAW = REPO_ROOT / "datos" / "raw"
DATOS_METADATA = REPO_ROOT / "datos" / "metadata"
RESULTADOS_FIGURAS = REPO_ROOT / "resultados" / "figuras"
RESULTADOS_BARRIDOS = REPO_ROOT / "resultados" / "barridos"
for _dir in (DATOS_RAW, DATOS_METADATA, RESULTADOS_FIGURAS, RESULTADOS_BARRIDOS):
    _dir.mkdir(parents=True, exist_ok=True)


# %% -- Constantes del hardware -------------------------------------------
N_MAX_TABLA = 8192      # [MEDIDO — qWMS/qTNR] puntos por wave table y por
                         # tabla del data recorder
RANGO_UM = (0.0, 200.0)  # [MEDIDO — qTMN/qTMX] rango físico del eje A
MARGEN_UM = 1.0          # [ELEGIDO] no comandar más cerca que esto del tope

# Opciones del data recorder [MEDIDO — manual PZ214E p. 151 + qHDR]
OPCIONES_DRC = {
    1:  ("target_um",  "posición comandada"),
    2:  ("current_um", "posición real (sensor)"),
    3:  ("error_um",   "error de seguimiento"),
    7:  ("volt_v",     "voltaje del piezo"),
    15: ("ctrl_out",   "salida del lazo de control"),
}

# Registro del parámetro de ciclo de servo (Servo Update Time), en segundos
SPA_SERVO_UPDATE_TIME = 0x0E000200

# %% -- Constantes MEDIDAS del lazo ---------------------------------------
# [MEDIDO 2026-09-08 — notebooks/01_escalon_tiempo_de_retardo.ipynb]
# Sobre 28 corridas de escalón válidas (DCO off, saltos de 0.2 a 100 µm) y
# 8 de rampa. Las dos vías coinciden dentro del 4.3 %.
TAU_LAG_MS = 13.1    # tau_lag = ∫(1-y)dt = 1/Kv. El error de rampa vale v·tau.
T_CONV_MS  = 33.0    # cuándo esa integral llega al 99.5 % de su valor final.
                      # Es lo que hay que DESCARTAR del arranque de una rampa.
                      # NO es 3·tau (39 ms, conservador) ni 5.3·tau (68 ms,
                      # que es lo que pediría un modelo de primer orden).


# %% -- Configuración de UNA corrida --------------------------------------
@dataclass
class Corrida:
    """Todo lo que define una medición. Un barrido es una lista de estos.

    Nada de lo que hay acá se calcula a partir del ciclo de servo: ese se
    lee del equipo al conectar y entra por `ctx`, no por acá.
    """
    # --- qué trayectoria ---
    modo: str = "escalon"        # 'escalon' | 'rampa' | 'quieto'
    centro_x: float = 100.0      # µm
    centro_y: float = 100.0      # µm (el eje B queda quieto acá)
    amplitud_um: float = 1.0     # semi-amplitud: el escalón vale 2×amplitud,
                                  # la rampa va de centro-A a centro+A y vuelve

    # --- relojes (los knobs de verdad) ---
    wtr: int = 1                 # ciclos de servo por punto de wave → dwell
    rtr: int = 1                 # ciclos de servo por muestra grabada
    wgc: int = 1                 # cuántas veces se repite la tabla por disparo

    # --- forma de la trayectoria ---
    n_pre: int = 50              # 'escalon': puntos de baseline antes del salto
    n_post: int = 2000           # 'escalon': puntos después del salto
    n_total: int = 400           # 'rampa'/'quieto': puntos de la tabla
    speedupdown: int = 0         # 'rampa': puntos de aceleración en cada extremo

    # --- estado del controlador ---
    dco: bool = False            # compensación de deriva  [§8.2: apagarlo
                                  # acelera el asentamiento ~2.7×]
    vco: bool = False            # velocity control mode
    svo: bool = True             # lazo cerrado. False = lazo ABIERTO,
                                  # solo permitido en modo 'quieto' y con
                                  # confirmar_lazo_abierto=True  [VERIFICAR]
    confirmar_lazo_abierto: bool = False

    # --- grabación ---
    drc_tablas: tuple = (1, 2, 3)
    drc_fuentes: tuple = ("A", "A", "A")
    drc_opciones: tuple = (1, 2, 3)   # target, current, error

    # --- generador / tabla / eje ---
    tabla: int = 1
    wavegen: int = 1
    eje: str = "A"
    leer_recorder_completo: bool = True   # pedirle al recorder sus 8192
                                  # muestras y recortar solas las que no
                                  # llegó a grabar (ver corrida())
    t_extra_grabacion_s: float = 0.0  # [MEDIDO 2026-09-07] el data recorder
                                  # sigue grabando después de que la wave
                                  # terminó, y recién se detiene con
                                  # WGO(gen, 0). Esperar acá antes de
                                  # mandar ese stop ES la forma de ver la
                                  # cola del asentamiento.
    carga_rapida: bool = True    # escalón en 2 comandos en vez de punto a
                                  # punto; se verifica con qGWD y si no da,
                                  # cae solo al método lento (ver _cargar_wave)
    wos: float = 0.0             # offset de salida del generador (µm). Sirve
                                  # para probar EN VIVO la corrección de lag
                                  # v·τ en un tramo de una sola dirección.

    # --- logística ---
    etiqueta: str = "corrida"    # entra en el nombre del archivo
    repeticion: int = 0          # índice, si se repite la misma config
    t_asentamiento_s: float = 0.5   # espera después del MOV inicial
    guardar_figura: bool = False    # una figura por corrida (en un barrido
                                     # largo conviene False y graficar al final)
    estricto: bool = True        # aborta la corrida si `verificar_coherencia`
                                  # encuentra un problema BLOQUEANTE. Ponerlo
                                  # en False solo para reproducir a propósito
                                  # una configuración vieja y rota.
    notas: str = ""


def escalon(rtr=5, n_pre=50, **kw):
    """Construye una `Corrida` de escalón con los relojes YA coherentes.

    La regla, que sale de haber medido el equipo el 2026-09-07:

        WTR = RTR   y   n_pre + n_post = 8192
        →  ventana = 8192 × RTR × 40 µs   y   resolución = RTR × 40 µs

    Por qué. El data recorder graba 8192 muestras cada `RTR` ciclos, pero
    lo que graba en el canal `target` deja de tener sentido en cuanto el
    generador se detiene. Si la trayectoria dura menos que la ventana, la
    cola del archivo queda con el target en 0 mientras la platina sigue
    en 101 µm — y el análisis lee ese 101→0 como si fuera EL escalón.
    (Pasó en la primera corrida de validación: reportó un salto de
    -101 µm en vez de +2 µm.)

    La solución es que la trayectoria dure toda la ventana. Como el tramo
    posterior al escalón es PLANO, alargarlo es gratis: un solo segmento
    WAV_LIN, cero puntos extra de USB. Y como el tramo plano no manda a
    la platina a ningún lado, lo que se graba durante todo ese tiempo es
    exactamente lo que queremos ver: la platina asentando sola.

    Con esto `RTR` queda como EL knob del escalón, y mueve las dos cosas
    a la vez y en el mismo sentido:
        RTR=1  → 328 ms de ventana, 40 µs de resolución
        RTR=5  → 1.6 s,             200 µs
        RTR=25 → 8.2 s,             1 ms   (la subida de 18 ms todavía
                                            tiene 18 muestras)
    """
    return Corrida(modo="escalon", rtr=rtr, wtr=rtr,
                   n_pre=n_pre, n_post=N_MAX_TABLA - n_pre, **kw)


# %% -- Conexión ----------------------------------------------------------
def conectar(modelo="E-517"):
    """Abre la conexión UNA vez y devuelve (pidevice, ctx).

    `ctx` guarda lo que es propiedad del equipo y no del experimento —
    sobre todo el ciclo de servo, que hasta ahora se venía escribiendo a
    mano en cada script y estaba mal en la mitad de las corridas.
    """
    pidevice = GCSDevice(modelo, gateway=PIFtdiGateway())
    idn = pidevice.qIDN().strip()

    pidevice.ONL([1, 2, 3], [1, 1, 1])

    # [MEDIDO] el ciclo de servo se lee, no se supone.
    t_servo_s = float(pidevice.qSPA(1, SPA_SERVO_UPDATE_TIME)[1][SPA_SERVO_UPDATE_TIME])

    # ¿Este firmware implementa WSL? Se pregunta UNA vez, acá.
    try:
        wsl_estado = dict(pidevice.qWSL([1, 2, 3]))
        wsl_soportado = True
    except Exception:                            # noqa: BLE001
        wsl_estado, wsl_soportado = None, False

    ctx = {
        "idn": idn,
        "wsl_soportado": wsl_soportado,
        "wsl_estado": wsl_estado,
        "t_servo_s": t_servo_s,
        "t_servo_us": t_servo_s * 1e6,
        "f_servo_hz": 1.0 / t_servo_s,
        "n_max_tabla": N_MAX_TABLA,
        "rango_um": RANGO_UM,
    }

    print("=" * 68)
    print(f"[conexión] {idn}")
    print(f"[servo]    T = {ctx['t_servo_us']:.2f} µs  ({ctx['f_servo_hz']:.0f} Hz)"
          "   ← leído del equipo, no hardcodeado")
    print(f"[ventana]  máxima grabable = 8192 × RTR × {ctx['t_servo_us']:.0f} µs "
          f"= {N_MAX_TABLA * ctx['t_servo_s'] * 1e3:.0f} ms × RTR")
    print(f"[WSL]      {'soportado: ' + str(wsl_estado) if wsl_soportado else 'NO soportado por este firmware — mapeo generador↔tabla fijo'}")
    print("=" * 68)
    return pidevice, ctx


def cerrar(pidevice, volver_a=None):
    """Cierra bien (no `close()` suelto: acumula callbacks, ver README del
    gateway)."""
    try:
        if volver_a is not None:
            pidevice.MOV(["A"], [volver_a])
            pitools.waitontarget(pidevice, ["A"], timeout=10)
        print(f"[cierre] posición final {dict(pidevice.qPOS())}")
    finally:
        cleanup_gcsdevice(pidevice)


# %% -- Helpers de bajo nivel ---------------------------------------------
def _leer_array_gcs(pidevice, timeout=20.0):
    """qGWD/qDRR son asíncronos: disparan un hilo que sigue leyendo. Hay que
    esperar bufstate antes de tocar bufdata."""
    t0 = time.time()
    while pidevice.bufstate is not True:
        if time.time() - t0 > timeout:
            raise TimeoutError("bufstate no llegó a True")
        time.sleep(0.005)
    return np.array(pidevice.bufdata[0])


def _suavizar(x, n):
    """Media móvil de n muestras, con padding POR BORDE.

    `np.convolve(x, k, mode="same")` rellena con CEROS fuera del array, así
    que en los extremos devuelve una mezcla de la señal con 0. Sobre una
    posición de ~100 µm eso inventa un salto de 100 µm en el primer punto
    — y si después se deriva para sacar velocidad, aparecen 10^5 µm/s de
    la nada. (Pasó: la segmentación de rampas daba v = 123750 µm/s.)
    """
    n = int(max(n, 1))
    if n <= 1 or len(x) < 3:
        return np.asarray(x, dtype=float)
    pad = n // 2
    xp = np.pad(np.asarray(x, dtype=float), pad, mode="edge")
    return np.convolve(xp, np.ones(n) / n, mode="same")[pad:pad + len(x)]


def _validar_rango(*posiciones):
    lo, hi = RANGO_UM[0] + MARGEN_UM, RANGO_UM[1] - MARGEN_UM
    for p in posiciones:
        if not (lo <= p <= hi):
            raise ValueError(
                f"posición {p:.4f} µm fuera del rango seguro [{lo}, {hi}] µm "
                f"(rango físico {RANGO_UM}, margen {MARGEN_UM} µm)")


def _conectar_generador_a_tabla(pidevice, wavegen, tabla, ctx=None):
    """WSL explícito + verificación. Ítem 1 de 'Próxima sesión' del protocolo:
    hasta ahora se asumía tabla 1 ↔ generador 1 sin haberlo mirado nunca.

    Devuelve el mapeo real leído del equipo, para meterlo en la metadata.
    """
    # Es la PRIMERA vez que este proyecto usa WSL. Si el firmware de este
    # E-517 no lo soportara, no tiene sentido matar el barrido entero: los
    # scripts anteriores funcionaron durante semanas con el mapeo implícito
    # tabla 1 ↔ generador 1. Se registra qué pasó y se sigue.
    # [MEDIDO 2026-09-07, E-517 serial 0111176619, firmware V01.243]
    # ESTE controlador NO implementa WSL: responde "Unknown command".
    # O sea que el mapeo generador↔tabla es fijo y no se puede reasignar —
    # queda resuelto el ítem 1 del protocolo, aunque no como esperábamos.
    # Se deja el intento igual (el código tiene que servir en otro equipo)
    # pero se cachea el resultado en ctx para no repetir el aviso 20 veces
    # ni gastar un round-trip por corrida.
    if ctx is not None and ctx.get("wsl_soportado") is False:
        return {"wsl_previo": None, "wsl": None, "wsl_soportado": False}

    try:
        previo = dict(pidevice.qWSL([1, 2, 3]))
    except Exception as exc:                     # noqa: BLE001
        print(f"      [aviso] qWSL no soportado ({exc}) — mapeo "
              "generador↔tabla implícito y FIJO en este firmware")
        if ctx is not None:
            ctx["wsl_soportado"] = False
        return {"wsl_previo": None, "wsl": None, "wsl_soportado": False}

    try:
        pidevice.WSL(wavegen, tabla)
    except Exception as exc:                     # noqa: BLE001
        print(f"      [aviso] WSL falló ({exc}) — mapeo implícito, qWSL "
              f"previo = {previo}")
        return {"wsl_previo": previo, "wsl": previo, "wsl_soportado": False}

    post = dict(pidevice.qWSL([1, 2, 3]))
    if post.get(wavegen) != tabla:
        raise RuntimeError(
            f"WSL no tomó: pedí generador {wavegen} → tabla {tabla}, "
            f"qWSL devuelve {post}. Si esto pasa, el generador está "
            f"reproduciendo OTRA tabla y todo lo grabado es de otra "
            f"trayectoria — parar y revisar antes de seguir midiendo.")
    return {"wsl_previo": previo, "wsl": post, "wsl_soportado": True}


def ventana_ms(rtr, t_servo_s, n_muestras=N_MAX_TABLA):
    """Cuánto tiempo cubre el data recorder, en ms. ESTE es el número que
    limita lo que se puede ver, no N_TOTAL."""
    return n_muestras * rtr * t_servo_s * 1e3


def rtr_para_ventana(ventana_deseada_ms, t_servo_s):
    """RTR mínimo para que el recorder cubra `ventana_deseada_ms`.
    Ej.: para ver 1 s de asentamiento con T=40 µs → RTR=4 (resolución 160 µs,
    que sigue dando ~110 muestras en una subida de 18 ms)."""
    return int(np.ceil(ventana_deseada_ms * 1e-3 / (N_MAX_TABLA * t_servo_s)))


# %% -- Construcción de la trayectoria ------------------------------------
def _cargar_wave(pidevice, cfg, ctx):
    """Carga la tabla según cfg.modo y devuelve (n_puntos, info).

    'escalon' : plano en x_i, salto, plano en x_f  (punto a punto, WAV_LIN)
    'rampa'   : ida y vuelta simétrica              (WAV_RAMP, una llamada)
    'quieto'  : todo plano en el centro             (WAV_LIN, un solo segmento)

    Nota [MEDIDO 2026-08-28]: una `amplitude` NEGATIVA en WAV_LIN no genera
    rampa descendente en este firmware — por eso la vuelta se hace con
    WAV_RAMP y no con dos WAV_LIN.
    """
    pidevice.WCL(cfg.tabla)

    if cfg.modo == "escalon":
        x_i = cfg.centro_x - cfg.amplitud_um
        x_f = cfg.centro_x + cfg.amplitud_um
        _validar_rango(x_i, x_f)
        n_total = cfg.n_pre + cfg.n_post
        if n_total > N_MAX_TABLA:
            raise ValueError(f"n_pre+n_post = {n_total} > {N_MAX_TABLA}")

        # Un escalón son dos tramos PLANOS. Un tramo plano es un WAV_LIN con
        # amplitude=0, así que la tabla entera se carga con DOS comandos en
        # vez de con n_total.
        #
        # Por qué importa: cada llamada de pipython es un round-trip USB
        # completo (manda el comando y lee ERR? antes de devolver el
        # control). Punto a punto, un escalón de 2050 puntos son 2050
        # round-trips — segundos por corrida, minutos por barrido, y ninguna
        # información a cambio.
        #
        # [VERIFICAR] amplitude=0 como "tramo plano" no está confirmado en
        # este firmware — y ya hay antecedente de que WAV_LIN no hace lo
        # esperado con ciertos argumentos (amplitud negativa, 2026-08-28).
        # Por eso la carga rápida se VERIFICA releyendo con qGWD, y si la
        # tabla no tiene la forma pedida se recarga sola punto a punto.
        metodo = "lento"
        if cfg.carga_rapida:
            pidevice.WAV_LIN(table=cfg.tabla, firstpoint=1, numpoints=cfg.n_pre,
                             append="X", speedupdown=0, amplitude=0.0,
                             offset=x_i, seglength=cfg.n_pre)
            pidevice.WAV_LIN(table=cfg.tabla, firstpoint=cfg.n_pre + 1,
                             numpoints=cfg.n_post, append="&", speedupdown=0,
                             amplitude=0.0, offset=x_f, seglength=cfg.n_post)
            pidevice.qGWD(cfg.tabla, 1, n_total)
            prueba = _leer_array_gcs(pidevice)
            tol = max(abs(x_f - x_i) * 1e-3, 1e-4)      # 0.1 % del salto o 0.1 nm
            ok = (len(prueba) == n_total
                  and abs(prueba[0] - x_i) < tol
                  and abs(prueba[cfg.n_pre - 1] - x_i) < tol
                  and abs(prueba[cfg.n_pre] - x_f) < tol
                  and abs(prueba[-1] - x_f) < tol)
            if ok:
                metodo = "rapido"
            else:
                print("      [aviso] carga rápida no dio la forma pedida "
                      "(amplitude=0 no arma un tramo plano en este firmware) "
                      "→ recargando punto a punto")
                pidevice.WCL(cfg.tabla)

        if metodo == "lento":
            trayectoria = np.concatenate([np.full(cfg.n_pre, x_i),
                                          np.full(cfg.n_post, x_f)])
            for i, val in enumerate(trayectoria):
                pidevice.WAV_LIN(table=cfg.tabla, firstpoint=i,
                                 numpoints=1, append=("X" if i == 0 else "&"),
                                 speedupdown=0, amplitude=0, offset=val,
                                 seglength=1)

        info = {"x_inicial_um": x_i, "x_final_um": x_f,
                "salto_nm": 2 * cfg.amplitud_um * 1e3,
                "idx_escalon": cfg.n_pre,
                "metodo_carga": metodo}

    elif cfg.modo == "rampa":
        x_i = cfg.centro_x - cfg.amplitud_um
        pico = cfg.centro_x + cfg.amplitud_um
        _validar_rango(x_i, pico)
        n_total = cfg.n_total
        if n_total > N_MAX_TABLA:
            raise ValueError(f"n_total = {n_total} > {N_MAX_TABLA}")
        pidevice.WAV_RAMP(table=cfg.tabla, firstpoint=1, numpoints=n_total,
                          append="X", center=n_total // 2,
                          speedupdown=cfg.speedupdown,
                          amplitude=(pico - x_i), offset=x_i, seglength=n_total)
        info = {"x_inicial_um": x_i, "x_pico_um": pico,
                "excursion_nm": 2 * cfg.amplitud_um * 1e3,
                "idx_escalon": None}

    elif cfg.modo == "quieto":
        # Trayectoria plana: la wave existe solo para disparar el recorder.
        # Sirve para ruido (RTR chico) y para deriva (RTR grande).
        n_total = cfg.n_total
        if n_total > N_MAX_TABLA:
            raise ValueError(f"n_total = {n_total} > {N_MAX_TABLA}")
        if cfg.svo:
            valor = cfg.centro_x
            _validar_rango(valor)
        else:
            # [VERIFICAR] en lazo abierto el generador comanda VOLTAJE, no
            # posición. Se arranca desde el voltaje actual para no mover nada.
            valor = float(dict(pidevice.qVOL())[cfg.eje])
            print(f"  [LAZO ABIERTO] wave plana en {valor:.4f} V (qVOL), "
                  "no en µm — [VERIFICAR] unidades del generador con SVO=0")
        pidevice.WAV_LIN(table=cfg.tabla, firstpoint=1, numpoints=n_total,
                         append="X", speedupdown=0, amplitude=0.0,
                         offset=valor, seglength=n_total)
        info = {"x_inicial_um": valor, "x_final_um": valor, "idx_escalon": None}

    else:
        raise ValueError(f"modo desconocido: {cfg.modo!r}")

    # Releer la tabla y verificar antes de disparar nada.
    pidevice.qGWD(cfg.tabla, 1, n_total)
    wave = _leer_array_gcs(pidevice)
    info.update({"n_puntos_wave": int(n_total),
                 "wave_min": float(np.min(wave)),
                 "wave_max": float(np.max(wave)),
                 "wave_primero": float(wave[0]),
                 "wave_ultimo": float(wave[-1])})
    return n_total, info


# %% -- Análisis (se corre sobre los datos ya grabados) -------------------
def _analisis_escalon(t_ms, target, current, error, tol_nm=5.0,
                      t_bump_desde_ms=30.0):
    """Métricas de un escalón. Todo en nm y ms.

    Separa deliberadamente TRES cosas que se confunden entre sí:

      1. la SUBIDA — t(10–90) ≈ 18 ms [MEDIDO], igual para escalones de
         200 nm y de 200 µm. Es la constante de tiempo del lazo cerrado
         (τ ≈ 12 ms, f_c ≈ 15 Hz) y es lo único que fija la "velocidad"
         del sistema;
      2. el SOBREPICO — cuánto se pasa de largo antes de volver;
      3. el BUMP LENTO — la excursión de decenas de nm que aparece
         DESPUÉS de haber llegado al destino y tarda ~50-80 ms en
         reabsorberse. §8.2 la identificó como efecto de DCO: con DCO
         apagado desaparece (1-5 nm, indistinguible del ruido).

    Todo se mide sobre el error normalizado por el signo del escalón, así
    un escalón hacia abajo da los mismos signos que uno hacia arriba.
    El bump se busca recién DESPUÉS del primer cruce por el destino
    (si la respuesta nunca cruza, no hay bump: hay una cola monótona, y
    la métrica devuelve NaN en vez de confundir la cola con un bump).
    """
    out = {}
    d = np.abs(np.diff(target))
    i_step = int(np.argmax(d)) + 1
    t0 = t_ms[i_step]
    x_i = float(np.median(target[:max(i_step - 1, 1)]))
    x_f = float(np.median(target[i_step:]))
    salto_nm = (x_f - x_i) * 1e3
    out.update({"t_escalon_ms": t0, "x_inicial_um": x_i, "x_final_um": x_f,
                "salto_nm": salto_nm})
    if abs(salto_nm) < 1e-6:
        return out

    signo = np.sign(x_f - x_i)
    tr = t_ms[i_step:] - t0
    y = (current[i_step:] - x_i) / (x_f - x_i)      # normalizado 0 → 1
    err_crudo_nm = (current[i_step:] - x_f) * 1e3 * signo  # >0 = pasado de largo

    # SUAVIZADO antes de aplicar cualquier criterio de banda.
    # Sin esto el settling time es basura: con sigma = 1.7 nm [MEDIDO §4] y
    # 8192 muestras, una banda de ±5 nm (2.9 sigma) la cruza el ruido solo
    # ~25 veces al azar repartidas por toda la ventana, así que "el último
    # instante fuera de banda" cae casi al final SIEMPRE, mida lo que mida
    # la platina. Promediando ~1 ms el ruido baja y el criterio vuelve a
    # medir la física en vez del ruido.
    dt_ms = float(np.median(np.diff(tr))) if len(tr) > 1 else 1.0
    # ~1 ms de promediado, pero NUNCA menos de 5 muestras: con RTR grande
    # (dt = 1 ms con RTR=25) "1 ms" es una sola muestra y no promedia nada,
    # y entonces la banda vuelve a estar dominada por el ruido.
    n_suav = max(5, int(round(1.0 / dt_ms)))
    err_nm = _suavizar(err_crudo_nm, n_suav)
    out["suavizado_muestras"] = n_suav
    out["suavizado_ms"] = n_suav * dt_ms

    # --- 1. subida ---
    def _cruce(nivel):
        idx = np.where(y >= nivel)[0]
        return float(tr[idx[0]]) if len(idx) else np.nan

    t10, t50, t90 = _cruce(0.10), _cruce(0.50), _cruce(0.90)
    out["t_subida_10_90_ms"] = t90 - t10
    # t50 es el mejor estadístico de la subida, mejor que t(10-90)
    # [MEDIDO 2026-09-07, barrido de amplitud]: es constante en 10.2-11.0 ms
    # sobre CUATRO décadas de escalón (20 nm a 100 µm), mientras que
    # t(10-90) varía entre 11.6 y 19.2 ms en el mismo barrido. Motivo: el
    # cruce del 10 % y el del 90 % son los más frágiles de la curva — el del
    # 10 % lo arruina el ruido cuando el escalón es chico (a 20 nm, el piso
    # de 1.2 nm es el 6 % del escalón), y el del 90 % depende de la forma de
    # la cola, que cambia con la amplitud. El cruce del 50 % está lejos de
    # las dos patologías.
    out["t_50_ms"] = t50
    out["tau_desde_subida_ms"] = (t90 - t10) / 2.197   # t(10-90) = 2.197 τ
    out["f_3db_hz"] = (0.35 / ((t90 - t10) * 1e-3)) if (t90 - t10) > 0 else np.nan

    # --- 2. sobrepico RÁPIDO: el del lazo, dentro de la primera ventana.
    # Se lo separa del bump lento a propósito: son dos mecanismos distintos
    # (el lazo principal, tau ~ 12 ms, contra el lazo de deriva de DCO).
    rapido = tr < t_bump_desde_ms
    out["sobrepico_nm"] = float(max(0.0, np.max(err_nm[rapido]))) if rapido.any() else np.nan
    out["sobrepico_pct"] = 100 * out["sobrepico_nm"] / abs(salto_nm)

    # --- 3. bump lento: excursión después de llegar por primera vez ---
    cruces = np.where(err_nm >= 0)[0]
    if len(cruces):
        i_cruce = int(cruces[0])
        mascara = (np.arange(len(tr)) > i_cruce) & (tr >= t_bump_desde_ms)
        if mascara.any():
            j = int(np.argmax(np.abs(err_nm[mascara])))
            out["bump_lento_nm"] = float(err_nm[mascara][j])
            out["bump_lento_t_ms"] = float(tr[mascara][j])
        else:
            out["bump_lento_nm"] = np.nan
            out["bump_lento_t_ms"] = np.nan
        out["t_primer_cruce_ms"] = float(tr[i_cruce])
    else:
        # nunca llegó al destino dentro de la ventana: cola monótona, sin
        # bump. NO es lo mismo que "bump = 0".
        out["bump_lento_nm"] = np.nan
        out["bump_lento_t_ms"] = np.nan
        out["t_primer_cruce_ms"] = np.nan

    # --- 4. settling: último instante fuera de la banda ±tol ---
    fuera = np.where(np.abs(err_nm) > tol_nm)[0]
    if len(fuera) == 0:
        out[f"ts_{tol_nm:.0f}nm_ms"] = 0.0
    elif fuera[-1] == len(tr) - 1:
        out[f"ts_{tol_nm:.0f}nm_ms"] = np.nan       # no asentó en la ventana
    else:
        out[f"ts_{tol_nm:.0f}nm_ms"] = float(tr[fuera[-1] + 1])
    out["asento_en_ventana"] = bool(np.isfinite(out[f"ts_{tol_nm:.0f}nm_ms"]))

    # --- 5. estado final: media y ruido del último 10 % de la ventana ---
    cola = current[i_step:][int(0.9 * len(tr)):]
    out["error_final_nm"] = float(np.mean(cola - x_f) * 1e3)
    out["ruido_final_nm_rms"] = float(np.std(cola) * 1e3)
    out["ventana_post_escalon_ms"] = float(tr[-1])
    # Una banda de asentamiento por debajo de ~3 sigma del propio ruido no
    # mide asentamiento: mide ruido. [MEDIDO §4] sigma ≈ 1.7 nm.
    out["tol_bajo_ruido"] = bool(tol_nm < 3 * out["ruido_final_nm_rms"])
    return out


def _cerrar_huecos(mascara, n):
    """Rellena los huecos de menos de n muestras dentro de una máscara.

    La velocidad sale de derivar una ESCALERA, así que tiene rizado con el
    período de la escalera y cruza cualquier umbral muchas veces. Sin
    cerrar esos huecos, una meseta de velocidad constante de 5460 muestras
    se reporta como 300 tramitos de 11 a 51 muestras — y después nada
    supera los 3τ de descarte, así que "no hay zona usable" cuando en
    realidad hay 200 ms de recta. (Pasó, con la tabla de 1600 puntos.)
    """
    m = np.asarray(mascara, dtype=bool).copy()
    if n < 1 or not m.any():
        return m
    idx = np.where(m)[0]
    huecos = np.where(np.diff(idx) > 1)[0]
    for h in huecos:
        i, j = idx[h], idx[h + 1]
        if j - i <= n:
            m[i:j] = True
    return m


def zonas_rampa(t_ms, target, wtr, rtr, t_conv_ms=None, umbral=0.95):
    """Parte una rampa en aceleración / velocidad constante / desaceleración,
    y devuelve además la zona USABLE para escanear.

    ---------------------------------------------------------------
    Idea, en una frase: la segmentación se hace sobre la posición
    COMANDADA, no sobre la medida.
    ---------------------------------------------------------------
    El comando es exacto y no tiene ruido: es la tabla que nosotros
    cargamos. La posición medida tiene ~1.1 nm rms de ruido [MEDIDO], y
    derivar numéricamente eso para sacar una velocidad multiplica el ruido
    por 1/dt = 25000 s⁻¹: a 40 µs de paso, 1.1 nm de ruido se convierten en
    ±28 µm/s de basura sobre una velocidad de ~20 µm/s. Con la posición
    medida no se puede segmentar; con la comandada, sí, y es exacto.

    Dos detalles que hay que respetar:

    1. **El comando es una ESCALERA.** El generador no interpola: cambia
       el setpoint una vez cada WTR ciclos y se queda quieto en el medio.
       Derivar punto a punto da cero la mayor parte del tiempo. Hay que
       suavizar sobre al menos un escalón completo (WTR/RTR muestras).

    2. **La zona de comando a velocidad constante NO es la zona usable.**
       Cuando la aceleración termina, la platina todavía está poniéndose
       al día: el error de seguimiento tarda ~3τ en llegar a su valor de
       régimen e = v·τ. Antes de eso el error está cambiando, o sea que el
       espaciado real entre píxeles no es uniforme todavía. La zona usable
       arranca 3τ ≈ 36 ms después de que el comando alcanzó velocidad
       constante. Esa es la razón física del over-scan.

    Devuelve un dict con máscaras booleanas (`acel`, `constante`, `desacel`,
    `usable`) y los números de la zona usable.
    """
    dt_ms = float(np.median(np.diff(t_ms)))
    # velocidad comandada, suavizada sobre un escalón entero de la escalera
    n_periodo = max(int(round(wtr / max(rtr, 1))), 1)   # una escalón de la escalera
    # suavizar sobre DOS períodos de la escalera antes de derivar, y suavizar
    # la velocidad resultante otro período: el rizado residual es lo que
    # picaba la máscara
    v = np.gradient(_suavizar(target, 2 * n_periodo), t_ms * 1e-3)   # µm/s
    v = _suavizar(v, n_periodo)

    # Referencia de la meseta por PERCENTIL, no por máximo: un solo pico
    # numérico (p. ej. en el arranque) no puede fijar la vara.
    v_ref = float(np.percentile(np.abs(v), 90))
    if v_ref <= 0:
        return {}
    constante = np.abs(v) >= umbral * v_ref
    ida = _cerrar_huecos(constante & (v > 0), 2 * n_periodo)
    vuelta = _cerrar_huecos(constante & (v < 0), 2 * n_periodo)
    constante = ida | vuelta
    acel = (~constante) & (np.abs(v) > 0.02 * v_ref)

    # zona usable: dentro de la IDA, descartando los primeros 3τ
    # Cuánto descartar del arranque. NO es 3·tau: eso sale de suponer que el
    # lazo es de primer orden, y no lo es [notebooks/01_...ipynb §5]. El
    # criterio correcto es t_conv, el tiempo en que la integral acumulada del
    # escalón llega al 99.5 % de su valor final. MEDIDO: 33 ms, contra 39 ms
    # de 3·tau (conservador) y 68 ms de 5.3·tau (lo que pediría 1er orden).
    t_conv_ms = T_CONV_MS if t_conv_ms is None else t_conv_ms
    n_3tau = int(np.ceil(t_conv_ms / dt_ms))
    usable = np.zeros_like(ida)
    idx = np.where(ida)[0]
    if len(idx) > n_3tau:
        # tramo contiguo más largo de la ida
        cortes = np.where(np.diff(idx) > 1)[0]
        tramos = np.split(idx, cortes + 1)
        tramo = max(tramos, key=len)
        if len(tramo) > n_3tau:
            usable[tramo[n_3tau:]] = True

    out = {"acel": acel, "constante": constante, "ida": ida,
           "vuelta": vuelta, "usable": usable, "v_um_s": v}

    # La zona de velocidad constante de la IDA siempre se reporta: es la que
    # sirve para medir v y el lag e = v·tau, exista o no zona usable.
    if ida.any():
        v_c = float(np.median(v[ida]))
        out.update({
            "v_constante_um_s": v_c,
            "t_constante_ms": float(ida.sum() * dt_ms),
            "t_acel_ms": float(acel.sum() * dt_ms),
            "t_conv_necesario_ms": n_3tau * dt_ms,
            "dx_por_punto_nm": abs(v_c) * (wtr * 40e-6) * 1e3,
        })

    # La zona USABLE puede estar VACÍA, y eso es un resultado, no un error:
    # significa que el tramo de velocidad constante dura MENOS que los 3·tau
    # que la platina necesita para que el error de seguimiento llegue a su
    # valor de régimen. En ese caso la trayectoria entera es transitorio y
    # NINGÚN punto tiene el espaciado uniforme: hay que alargar el tramo
    # recto (más puntos, o menos speedupdown, o más velocidad).
    out["hay_zona_usable"] = bool(usable.any())
    if usable.any():
        v_u = float(np.median(v[usable]))
        out.update({
            "v_usable_um_s": v_u,
            "t_usable_ms": float(t_ms[usable][-1] - t_ms[usable][0]),
            "x_usable_ini_um": float(target[usable][0]),
            "x_usable_fin_um": float(target[usable][-1]),
            "recorrido_usable_um": float(abs(target[usable][-1] - target[usable][0])),
            "frac_usable": float(usable.sum() / len(usable)),
        })
    else:
        out.update({"t_usable_ms": 0.0, "recorrido_usable_um": 0.0,
                    "frac_usable": 0.0})
    return out


def _analisis_rampa(t_ms, target, current, error, t_servo_s, wtr, rtr,
                    speedupdown, n_puntos_wave):
    """Métricas de una rampa: velocidad, error de seguimiento y τ = e/v.

    El error de seguimiento en velocidad constante es determinista:
    e = v·τ con τ ≈ 12.1 ms [MEDIDO], constante sobre cuatro décadas de
    velocidad. Por eso τ = e/v es la salida importante de cada corrida:
    si cambia, cambió el lazo.
    """
    out = {}
    dt_s = rtr * t_servo_s
    # Velocidad comandada, del propio target grabado (no de lo que creíamos
    # haber pedido): mediana de la pendiente en el tramo de subida.
    i_pico = int(np.argmax(target))
    if i_pico < 10:
        return out
    # Zona de velocidad constante: detectada de la trayectoria comandada
    # (ver zonas_rampa), no recortada "a ojo" por una fracción fija — el
    # tramo de aceleración que produce speedupdown no dura exactamente lo
    # que uno supondría, y depende de WTR.
    z = zonas_rampa(t_ms, target, wtr, rtr)
    # v y el lag se miden sobre la zona de velocidad constante de la ida.
    # La zona USABLE (esa menos 3τ) se reporta aparte: puede estar vacía.
    idx = np.where(z.get("ida", np.zeros(len(target), bool)))[0]
    if len(idx) < 10:
        return out
    sl = slice(int(idx[0]), int(idx[-1]) + 1)
    for k in ("frac_usable", "dx_por_punto_nm", "recorrido_usable_um",
              "t_acel_ms", "t_constante_ms", "t_usable_ms",
              "t_conv_necesario_ms", "hay_zona_usable"):
        out[k] = z.get(k, np.nan)

    # La velocidad NO se saca de la mediana de las diferencias: el target
    # es una ESCALERA, no una rampa [MEDIDO §2] — el wave generator no
    # interpola, cambia el setpoint una vez cada WTR ciclos de servo y se
    # queda quieto en el medio. Si WTR/RTR > 2, más de la mitad de las
    # diferencias consecutivas valen exactamente 0 y la mediana da 0.
    # Un ajuste lineal sobre el tramo promedia la escalera y da la
    # velocidad media real, que es la que ve la platina (el lazo, con
    # tau = 12 ms, integra los micro-escalones y no los distingue).
    t_s_sl = t_ms[sl] * 1e-3
    v_um_s = float(np.polyfit(t_s_sl, target[sl], 1)[0])
    e_nm = (current[sl] - target[sl]) * 1e3
    out["v_um_s"] = v_um_s
    out["error_mediano_nm"] = float(np.median(e_nm))
    out["error_rms_nm"] = float(np.sqrt(np.mean(e_nm ** 2)))
    out["tau_desde_lag_ms"] = (abs(np.median(e_nm)) * 1e-3 / abs(v_um_s) * 1e3
                               if v_um_s else np.nan)
    # --- uniformidad REAL del paso espacial en la zona usable ---
    # Este es EL número para imagen: si la platina recorriera la zona usable
    # a velocidad perfectamente constante, su posición sería una recta en el
    # tiempo y cada píxel mediría exactamente v·WTR·40 µs de ancho. Lo que
    # se aparta de esa recta es, píxel a píxel, el error de POSICIÓN del
    # píxel — no un error de seguimiento (ese es el lag, que es rígido y se
    # corrige), sino falta de uniformidad, que no se corrige con nada.
    # OJO: se mide en la zona USABLE, no en la de velocidad constante. En la
    # zona de velocidad constante entran los primeros 3τ, donde el error
    # todavía está creciendo — y esa curvatura del transitorio domina el
    # residuo y lo hace parecer 10 veces peor de lo que es.
    idx_u = np.where(z.get("usable", np.zeros(len(target), bool)))[0]
    if len(idx_u) >= 10:
        su = slice(int(idx_u[0]), int(idx_u[-1]) + 1)
        tu = t_ms[su] * 1e-3
        res = current[su] - np.polyval(np.polyfit(tu, current[su], 1), tu)
        out["residuo_recta_usable_nm"] = float(np.sqrt(np.mean(res ** 2)) * 1e3)
        out["residuo_recta_usable_max_nm"] = float(np.max(np.abs(res)) * 1e3)
    else:
        out["residuo_recta_usable_nm"] = np.nan
        out["residuo_recta_usable_max_nm"] = np.nan
    if out.get("dx_por_punto_nm"):
        out["residuo_en_pixeles"] = (out["residuo_recta_usable_nm"]
                                     / out["dx_por_punto_nm"])

    # --- el giro: lo que NO se arregla corrigiendo el lag ---
    # En velocidad constante el error vale +v·tau en la ida y -v·tau en la
    # vuelta: es un desplazamiento rígido, y se corrige. Lo que queda
    # después de descontarlo es el residuo del integrador desarmándose
    # cuando la velocidad cambia de signo [MEDIDO §3: 94-159 nm] — y ESE
    # es el motivo físico del over-scan: tiene que caer fuera de la zona
    # de interés, porque no hay corrección que lo saque.
    e_todo_nm = (current - target) * 1e3
    lag_nm = abs(np.median(e_nm))
    ancho = max(int(0.15 * len(e_todo_nm)), 5)
    giro = slice(max(i_pico - ancho, 0), min(i_pico + ancho, len(e_todo_nm)))
    out["error_max_giro_nm"] = float(np.max(np.abs(e_todo_nm[giro])))
    out["exceso_giro_nm"] = float(out["error_max_giro_nm"] - lag_nm)
    out["error_rms_total_nm"] = float(np.sqrt(np.mean(e_todo_nm ** 2)))
    # RMS que quedaría si se corrigiera el lag (desplazamiento rígido):
    # es el número que dice cuánto se gana corrigiendo, sin recorrer nada.
    med_e = np.median(e_nm)          # error con signo en la IDA
    # Modelo del lag: e = +med_e en la ida, -med_e en la vuelta. La
    # dirección NO se saca de np.gradient(target): el target es una
    # escalera y su gradiente vale 0 en la mayoría de los puntos (mismo
    # motivo por el que la velocidad se saca de un ajuste). Se usa el
    # índice del pico, que para una WAV_RAMP parte la ida de la vuelta.
    direccion = np.where(np.arange(len(target)) < i_pico, 1.0, -1.0)
    e_corr = e_todo_nm - med_e * direccion
    out["error_rms_lag_corregido_nm"] = float(np.sqrt(np.mean(e_corr ** 2)))
    return out


def _analisis_quieto(t_ms, serie_um, t_servo_s, rtr):
    """Ruido y deriva con la platina quieta.

    [MEDIDO §4] σ ≈ 1.7 nm RMS, dominado por una línea de 50 Hz de 2.4 nm
    de amplitud (la red). Ese término NO se promedia y está por encima del
    ancho de banda del lazo: para sub-nm es el enemigo número uno.
    """
    out = {}
    x_nm = (serie_um - np.mean(serie_um)) * 1e3
    dt_s = rtr * t_servo_s
    out["sigma_nm"] = float(np.std(x_nm))
    out["pico_a_pico_nm"] = float(np.ptp(x_nm))
    # deriva: pendiente de un ajuste lineal
    t_s = t_ms * 1e-3
    if len(t_s) > 10 and t_s[-1] > 0:
        p, cov = np.polyfit(t_s, x_nm, 1, cov=True)
        out["deriva_nm_s"] = float(p[0])
        out["deriva_nm_min"] = float(p[0] * 60)
        # La incerteza importa: ajustar una recta a 0.3 s de ruido da
        # pendientes de decenas de nm/min que no son deriva, son ruido.
        # Una deriva solo es deriva si |pendiente| >> su propio error.
        out["deriva_err_nm_min"] = float(np.sqrt(cov[0, 0]) * 60)
        out["deriva_significativa"] = bool(
            abs(out["deriva_nm_min"]) > 3 * out["deriva_err_nm_min"])
        out["ventana_s"] = float(t_s[-1])
    # línea de 50 Hz (solo si la ventana la resuelve)
    f_nyq = 0.5 / dt_s
    if f_nyq > 60 and len(x_nm) > 64:
        X = np.fft.rfft(x_nm - np.polyval(np.polyfit(t_s, x_nm, 1), t_s))
        f = np.fft.rfftfreq(len(x_nm), dt_s)
        amp = 2 * np.abs(X) / len(x_nm)
        banda = (f > 45) & (f < 55)
        if banda.any():
            # La amplitud NO se lee del bin del pico: 50 Hz casi nunca cae
            # en el centro de un bin y la fuga espectral se come hasta un
            # 20 %. Se filtra la banda entera y se mide su RMS.
            X_banda = np.where(banda, X, 0)
            x_banda = np.fft.irfft(X_banda, n=len(x_nm))
            out["amp_50hz_nm"] = float(np.sqrt(2) * np.std(x_banda))
            k = int(np.argmax(amp[banda]))
            out["f_pico_50hz"] = float(f[banda][k])
            out["df_espectral_hz"] = float(f[1] - f[0])
    return out


# %% -- UNA corrida -------------------------------------------------------
def verificar_coherencia(cfg, n_puntos, t_servo_s):
    """Chequea la configuración ANTES de disparar. Devuelve (bloqueantes, avisos).

    Cada regla de acá salió de corridas que se perdieron por no tenerla.
    De las 69 corridas de rampa acumuladas hasta el 2026-09-08, 51 quedaron
    inutilizables por alguna de estas tres cosas — ninguna por física.

        (a) la trayectoria no entra en la ventana del recorder
        (b) el tramo recto es más corto que el transitorio que se quiere medir
        (c) WTR != RTR, así que no hay 1 muestra por punto de wave

    Referencia de los números: notebooks/01_escalon_tiempo_de_retardo.ipynb §6.
    """
    bloq, avisos = [], []
    ventana_ticks = N_MAX_TABLA * cfg.rtr           # en ciclos de servo
    wave_ticks    = n_puntos * cfg.wgc * cfg.wtr
    ventana_ms    = ventana_ticks * t_servo_s * 1e3
    wave_ms       = wave_ticks * t_servo_s * 1e3

    # (a) — vale para todos los modos
    if wave_ticks > ventana_ticks:
        bloq.append(
            f"la trayectoria ({wave_ms:.0f} ms) no entra en la ventana del "
            f"recorder ({ventana_ms:.0f} ms): n_puntos·WGC·WTR = {wave_ticks} "
            f"> 8192·RTR = {ventana_ticks}. Subir RTR o bajar n_total/WTR.")

    # (b) — solo rampa: el tramo recto tiene que superar el transitorio
    if cfg.modo == "rampa":
        n_recta   = n_puntos / 2 - cfg.speedupdown
        t_recta   = n_recta * cfg.wtr * t_servo_s * 1e3
        t_minimo  = T_CONV_MS + 20.0
        if n_recta <= 0:
            bloq.append(f"speedupdown={cfg.speedupdown} se come el tramo recto "
                        f"entero (n_total/2 = {n_puntos/2:.0f} puntos).")
        elif t_recta < t_minimo:
            bloq.append(
                f"tramo recto de {t_recta:.0f} ms < t_conv + 20 ms = "
                f"{t_minimo:.0f} ms: el error de seguimiento todavía está "
                f"creciendo cuando se acaba la pata, así que e_ss no es e_ss. "
                f"Subir n_total·WTR, o bajar speedupdown.")
        elif t_recta < T_CONV_MS + 50.0:
            avisos.append(f"tramo recto de {t_recta:.0f} ms: usable = "
                          f"{t_recta - T_CONV_MS:.0f} ms. Corto pero medible.")
        if cfg.speedupdown and cfg.modo == "rampa":
            avisos.append("speedupdown>0 acorta el tramo recto sin aportar nada "
                          "a la identificación: para medir tau va en 0.")
        if cfg.dco:
            avisos.append("dco=True mete una excursión lenta que sesga e_ss.")

    # (c) — relojes. Dos cosas distintas, no confundirlas:
    #   · WTR < RTR  → se pierden puntos comandados entre muestras. Siempre malo.
    #   · dt grueso  → no se resuelve el transitorio. Malo para identificar.
    # WTR = RTR (1 muestra por punto de wave) hace falta para un SCAN, donde
    # cada píxel necesita su posición medida; para identificar tau no, ahí
    # manda RTR=1.
    if cfg.wtr < cfg.rtr:
        bloq.append(
            f"WTR={cfg.wtr} < RTR={cfg.rtr}: el generador avanza más rápido "
            f"que el grabador, así que hay puntos comandados que no quedan "
            f"registrados en ninguna muestra.")
    dt_ms = cfg.rtr * t_servo_s * 1e3
    if dt_ms > T_CONV_MS / 10:
        avisos.append(
            f"dt de grabación = {dt_ms:.2f} ms: solo "
            f"{T_CONV_MS/dt_ms:.0f} muestras en todo el transitorio "
            f"({T_CONV_MS:.0f} ms). Bajar RTR si interesa la forma de la subida.")

    # escalón: la trayectoria tiene que llenar la ventana o la cola miente
    if cfg.modo == "escalon" and wave_ticks < ventana_ticks * 0.999:
        bloq.append(
            f"escalón con la trayectoria ({wave_ms:.0f} ms) más corta que la "
            f"ventana ({ventana_ms:.0f} ms): al terminar la wave el canal de "
            f"posición comandada pasa a 0 y el análisis lee ESE salto como si "
            f"fuera el escalón. Usar el helper escalon(rtr=...).")
    return bloq, avisos


def n_puntos_de(cfg):
    """Cuántos puntos de wave va a tener esta configuración, sin cargarla."""
    return cfg.n_pre + cfg.n_post if cfg.modo == "escalon" else cfg.n_total


def revisar_lista(configs, t_servo_s, verbose=True):
    """Verifica TODAS las configuraciones antes de tocar el equipo.

    Sin esto, un barrido de 12 corridas con una constante mal puesta se
    entera recién después del primer MOV, con la platina ya movida y medio
    minuto perdido — y si `estricto=False`, ni se entera: guarda 12 archivos
    inutilizables. Chequear la lista es gratis y es instantáneo.
    """
    problemas = [(cfg, *verificar_coherencia(cfg, n_puntos_de(cfg), t_servo_s))
                 for cfg in configs]
    con_bloq = [(c, b) for c, b, _ in problemas if b]
    if verbose:
        n_avisos = sum(1 for _, _, a in problemas if a)
        print(f"[pre-vuelo] {len(configs)} corridas: "
              f"{len(con_bloq)} con bloqueantes, {n_avisos} con avisos")
        for cfg, _, avisos in problemas:
            for a in avisos:
                print(f"   [aviso] {cfg.etiqueta} r{cfg.repeticion}: {a}")
        for cfg, bloq in con_bloq:
            for b in bloq:
                print(f"   [BLOQUEANTE] {cfg.etiqueta} r{cfg.repeticion}: {b}")
    if con_bloq and any(c.estricto for c, _ in con_bloq):
        raise ValueError(
            f"{len(con_bloq)} de {len(configs)} corridas tienen configuración "
            f"incoherente. No se conecta al equipo. Corregir, o poner "
            f"estricto=False si es a propósito.")
    return problemas


def corrida(pidevice, cfg, ctx, verbose=True):
    """Ejecuta UNA medición completa y devuelve una fila (dict) de resumen.

    Hace, en orden: estado del controlador → wave → WSL → WTR/WGC/WOS →
    DRC/RTR → MOV al punto de partida → WGO → leer → analizar → guardar.

    No lanza excepción hacia afuera si algo falla: devuelve la fila con
    ok=False y el traceback, para que un `for` de 20 corridas no se muera
    en la número 3. (Los errores igual se imprimen.)
    """
    t_servo_s = ctx["t_servo_s"]
    fila = {"ok": False, "timestamp": None, "error_msg": ""}
    fila.update({k: v for k, v in asdict(cfg).items()})

    try:
        # --- 1. estado del controlador -------------------------------
        if not cfg.svo and not (cfg.modo == "quieto" and cfg.confirmar_lazo_abierto):
            raise ValueError(
                "svo=False solo está permitido en modo 'quieto' y con "
                "confirmar_lazo_abierto=True — en lazo abierto el generador "
                "comanda VOLTAJE y un valor en µm puede ser un salto enorme.")

        pidevice.SVO(["A", "B"], [cfg.svo, cfg.svo])
        pidevice.DCO(["A", "B"], [cfg.dco, cfg.dco])
        pidevice.VCO(["A", "B"], [cfg.vco, cfg.vco])

        # --- 2. punto de partida (antes de cargar la wave) -----------
        if cfg.svo:
            if cfg.modo == "escalon":
                x0 = cfg.centro_x - cfg.amplitud_um
            elif cfg.modo == "rampa":
                x0 = cfg.centro_x - cfg.amplitud_um
            else:
                x0 = cfg.centro_x
            _validar_rango(x0, cfg.centro_y)
            pidevice.MOV(["A", "B"], [x0, cfg.centro_y])
            pitools.waitontarget(pidevice, ["A", "B"], timeout=15)
            time.sleep(cfg.t_asentamiento_s)

        # --- 3. cargar la trayectoria --------------------------------
        n_puntos, info_wave = _cargar_wave(pidevice, cfg, ctx)

        # --- 4. WSL: conectar generador ↔ tabla, explícito -----------
        info_wsl = _conectar_generador_a_tabla(pidevice, cfg.wavegen, cfg.tabla, ctx)

        # --- 5. reproducción -----------------------------------------
        pidevice.WTR(cfg.wavegen, cfg.wtr, 0)
        pidevice.WGC(cfg.wavegen, cfg.wgc)
        pidevice.WOS(cfg.wavegen, cfg.wos)

        # --- 6. grabación --------------------------------------------
        pidevice.DRC(tables=list(cfg.drc_tablas), sources=list(cfg.drc_fuentes),
                     options=list(cfg.drc_opciones))
        pidevice.RTR(cfg.rtr)

        # --- 7. presupuesto de tiempo, ANTES de disparar -------------
        dt_grab_s = cfg.rtr * t_servo_s
        dur_wave_s = n_puntos * cfg.wgc * cfg.wtr * t_servo_s
        n_wave = int(np.ceil(n_puntos * cfg.wgc * cfg.wtr / cfg.rtr))
        # Cuántas muestras pedirle al recorder. ESTA decisión es la que
        # arruinó 8 de las 11 corridas del 02/09: el recorder graba 8192
        # muestras seguidas desde el WGO, pero el script pedía solo las que
        # duraba la wave — y como la wave duraba 16-80 ms y el asentamiento
        # tarda ~140 ms, la cola lenta quedaba grabada en el equipo y nunca
        # se leía. Por default pedimos el recorder COMPLETO: la platina
        # sigue existiendo después de que la trayectoria termina, y es
        # justo ahí donde asienta.
        # [VERIFICAR] que el recorder efectivamente sigue grabando después
        # de que el generador terminó. Si no lo hiciera, la cola vendría en
        # ceros exactos — el flag `cola_en_cero` de más abajo lo detecta.
        n_pedir = int(min(N_MAX_TABLA if cfg.leer_recorder_completo else n_wave,
                          N_MAX_TABLA))
        ventana_s = n_pedir * dt_grab_s
        fila.update({
            "t_servo_us": ctx["t_servo_us"],
            "dt_grabacion_us": dt_grab_s * 1e6,
            "duracion_wave_ms": dur_wave_s * 1e3,
            "ventana_grabada_ms": ventana_s * 1e3,
            "n_puntos_wave": n_puntos,
            "n_muestras_pedidas": n_pedir,
        })
        if verbose:
            print(f"  [{cfg.etiqueta}] modo={cfg.modo} WTR={cfg.wtr} RTR={cfg.rtr} "
                  f"DCO={cfg.dco} A={cfg.amplitud_um} µm")
            print(f"      wave: {n_puntos} pts × {cfg.wgc} ciclo(s) = "
                  f"{dur_wave_s*1e3:.1f} ms   |   grabación: dt="
                  f"{dt_grab_s*1e6:.0f} µs, ventana={ventana_s*1e3:.1f} ms")
            if ventana_s < dur_wave_s * 0.999:
                print(f"      [aviso] la grabación cubre solo "
                      f"{100*ventana_s/dur_wave_s:.0f} % de la trayectoria "
                      f"— subir RTR para verla entera")
            if cfg.modo == "escalon" and dur_wave_s < ventana_s * 0.999:
                print(f"      [AVISO] la trayectoria ({dur_wave_s*1e3:.0f} ms) "
                      f"es más corta que la ventana del recorder "
                      f"({ventana_s*1e3:.0f} ms): la cola del archivo va a "
                      f"tener el target en 0 y el análisis se confunde. "
                      f"Usar el helper escalon(rtr=...) — pone WTR=RTR y "
                      f"n_post=8192-n_pre.")
            elif cfg.modo == "escalon" and ventana_s < 0.3:
                print(f"      [aviso] ventana de {ventana_s*1e3:.0f} ms para un "
                      "escalón: el asentamiento con DCO=True tarda ~140 ms "
                      "[MEDIDO §8.2] — subir RTR si se quiere ver la cola")

        # --- 7b. coherencia, antes de gastar tiempo de equipo ---------
        # (redundante si se pasó por revisar_lista, pero `corrida()` también
        # se usa suelta, y acá ya se conoce n_puntos REAL de la wave cargada)
        bloq, avisos = verificar_coherencia(cfg, n_puntos, t_servo_s)
        fila["coherencia_ok"] = not bloq
        fila["coherencia_bloqueantes"] = " | ".join(bloq)
        fila["coherencia_avisos"] = " | ".join(avisos)
        for a in avisos:
            print(f"      [aviso] {a}")
        for b in bloq:
            print(f"      [BLOQUEANTE] {b}")
        if bloq and cfg.estricto:
            raise ValueError(
                "configuración incoherente (estricto=True): " + " | ".join(bloq))

        # --- 8. disparo ----------------------------------------------
        t_host = time.time()
        pidevice.WGO(cfg.wavegen, 1)
        pitools.waitonwavegen(pidevice, wavegens=cfg.wavegen,
                              timeout=max(20.0, dur_wave_s * 2 + 10))
        # [MEDIDO 2026-09-07] El data recorder NO se detiene cuando la wave
        # termina: sigue grabando hasta que se frena el generador con
        # WGO(gen, 0). En la corrida de validación eso dio 403 ms grabados
        # para una wave de 82 ms — los 321 ms extra eran, sin querer, la
        # latencia del host entre waitonwavegen y el stop.
        #
        # O sea que la ventana de observación se controla acá, y de forma
        # explícita: la trayectoria termina, la platina se queda asentando
        # sola en el último punto, y el recorder la sigue mirando.
        if cfg.t_extra_grabacion_s > 0:
            time.sleep(cfg.t_extra_grabacion_s)
        pidevice.WGO(cfg.wavegen, 0)
        fila["duracion_host_ms"] = (time.time() - t_host) * 1e3

        # --- 9. leer las tablas del recorder -------------------------
        columnas = {}
        # El nombre de columna sale de la OPCIÓN del recorder, pero si dos
        # tablas graban la misma opción sobre ejes distintos (p. ej. posición
        # real de A y de B, que es lo que hace falta para un raster) hay que
        # desambiguar con el eje, o una pisa a la otra.
        opciones = list(cfg.drc_opciones)
        for tabla, opcion, fuente in zip(cfg.drc_tablas, opciones, cfg.drc_fuentes):
            nombre = OPCIONES_DRC.get(opcion, (f"opt{opcion}",))[0]
            if opciones.count(opcion) > 1:
                nombre = f"{nombre}_{fuente}"
            pidevice.qDRR(tabla, 1, n_pedir)
            columnas[nombre] = _leer_array_gcs(pidevice)
        n = min(len(v) for v in columnas.values())
        columnas = {k: v[:n] for k, v in columnas.items()}

        # Recorte de la cola NO grabada. Le pedimos al recorder más
        # muestras de las que llegó a tomar (no se sabe de antemano cuántas
        # son: depende de la latencia del host hasta el WGO(0)), y las que
        # no grabó vuelven como CEROS EXACTOS. Hay que sacarlas: si no, el
        # salto de 101 µm a 0 al final del array es el escalón más grande
        # del archivo y el análisis lo toma como si fuera EL escalón.
        # (Eso es exactamente lo que pasó en la corrida de validación.)
        _ref = columnas.get("target_um", next(iter(columnas.values())))
        if len(_ref) and _ref[0] != 0.0:
            validas = np.where(np.any([v != 0.0 for v in columnas.values()], axis=0))[0]
            n_val = int(validas[-1]) + 1 if len(validas) else n
            if n_val < n:
                columnas = {k: v[:n_val] for k, v in columnas.items()}
                fila["muestras_descartadas"] = n - n_val
                n = n_val

        # EJE TEMPORAL CORRECTO: dt = RTR × T_servo (leído del equipo).
        t_ms = np.arange(n) * dt_grab_s * 1e3
        fila["muestras_leidas"] = n
        fila["ventana_real_ms"] = float(t_ms[-1]) if n else 0.0
        fila["ventana_post_wave_ms"] = fila["ventana_real_ms"] - dur_wave_s * 1e3
        if verbose:
            print(f"      grabado: {n} muestras = {fila['ventana_real_ms']:.0f} ms "
                  f"({fila.get('muestras_descartadas', 0)} descartadas por venir "
                  f"en cero) | después de la wave: "
                  f"{fila['ventana_post_wave_ms']:.0f} ms")

        # --- 10. análisis --------------------------------------------
        # Si dos tablas graban la MISMA opción sobre ejes distintos (p. ej.
        # posición real de A y de B, que es lo que hace falta para medir
        # diafonía), los nombres se desambiguaron con el eje más arriba:
        # "current_um" pasó a ser "current_um_A". Sin este fallback, el
        # análisis de rampa/escalón no encuentra la columna, se saltea sin
        # avisar, y la corrida queda sin métricas — el CSV está bien, pero
        # el resumen sale en NaN.
        def _col(nombre):
            if nombre in columnas:
                return columnas[nombre]
            propio = f"{nombre}_{cfg.eje}"
            if propio in columnas:
                return columnas[propio]
            candidatos = [v for k, v in columnas.items() if k.startswith(nombre)]
            return candidatos[0] if candidatos else None

        tgt = _col("target_um")
        cur = _col("current_um")
        err = _col("error_um")
        if err is None and (tgt is not None and cur is not None):
            err = cur - tgt
        if err is not None:
            fila["error_max_nm"] = float(np.max(np.abs(err)) * 1e3)
            fila["error_rms_nm"] = float(np.sqrt(np.mean(err ** 2)) * 1e3)

        if cfg.modo == "escalon" and tgt is not None and cur is not None:
            fila.update(_analisis_escalon(t_ms, tgt, cur, err))
        elif cfg.modo == "rampa" and tgt is not None and cur is not None:
            fila.update(_analisis_rampa(t_ms, tgt, cur, err, t_servo_s,
                                        cfg.wtr, cfg.rtr, cfg.speedupdown,
                                        n_puntos))
        elif cfg.modo == "quieto":
            # con nombres desambiguados por eje, "current_um" pasa a ser
            # "current_um_A" — buscar por prefijo antes de rendirse
            serie = cur if cur is not None else next(iter(columnas.values()))
            fila.update(_analisis_quieto(t_ms, serie, t_servo_s, cfg.rtr))

        # --- 11. guardar ---------------------------------------------
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"E517_{cfg.modo}_{cfg.etiqueta}_{ts}_r{cfg.repeticion}"
        fila["timestamp"] = ts
        fila["archivo"] = base

        pd.DataFrame({"t_ms": t_ms, **columnas}).to_csv(
            DATOS_RAW / f"{base}.csv", index=False)

        # Metadata: TODO releído del controlador, no lo que dice el código.
        estado = {
            "qIDN": ctx["idn"],
            "qSPA_servo_us": f"{ctx['t_servo_us']:.4f}",
            "qSVO": dict(pidevice.qSVO()),
            "qDCO": dict(pidevice.qDCO()),
            "qVCO": dict(pidevice.qVCO()),
            "qWSL": info_wsl["wsl"],
            "qWSL_previo": info_wsl["wsl_previo"],
            "qWTR": dict(pidevice.qWTR()),
            "qRTR": pidevice.qRTR(),
            "qDRC": dict(pidevice.qDRC()),
            "qPOS_final": dict(pidevice.qPOS()),
        }
        with open(DATOS_METADATA / f"{base}_metadata.txt", "w") as f:
            f.write(f"E517_barrido.py -- {ts}\n")
            f.write("# --- configuración pedida ---\n")
            for k, v in asdict(cfg).items():
                f.write(f"{k}={v}\n")
            f.write("# --- estado REAL del controlador (releído) ---\n")
            for k, v in estado.items():
                f.write(f"{k}={v}\n")
            # Todo lo que hace falta para reconstruir el eje temporal SIN
            # confiar en la columna t_ms. (Las corridas del 2026-09-01 tienen
            # t_ms mal escalado por un factor 40/T_SERVO_US: aquel script
            # etiquetaba el eje con una variable de Python que nunca se le
            # mandaba al controlador. Acá t_ms sale de qSPA, pero el análisis
            # igual debería reconstruirlo desde RTR.)
            f.write("# --- eje temporal (para reconstruir sin usar t_ms) ---\n")
            f.write(f"rtr={cfg.rtr}\n")
            f.write(f"t_servo_us_real={ctx['t_servo_us']:.6f}\n")
            f.write(f"dt_muestra_us={cfg.rtr * ctx['t_servo_us']:.6f}\n")
            f.write("formula_t_ms=arange(n) * rtr * t_servo_us_real / 1000\n")
            f.write("t_ms_confiable=True\n")
            f.write("# --- wave cargada (releída con qGWD) ---\n")
            for k, v in info_wave.items():
                f.write(f"{k}={v}\n")
            f.write("# --- métricas ---\n")
            for k, v in fila.items():
                if k not in asdict(cfg):
                    f.write(f"{k}={v}\n")

        if cfg.guardar_figura:
            _figura_corrida(t_ms, columnas, cfg, fila, base)

        fila["ok"] = True
        if verbose:
            print(f"      → {base}  " + _resumen_corto(cfg, fila))

    except Exception as exc:                     # noqa: BLE001
        fila["error_msg"] = f"{type(exc).__name__}: {exc}"
        print(f"  [ERROR] {cfg.etiqueta} r{cfg.repeticion}: {fila['error_msg']}")
        traceback.print_exc()
        try:
            pidevice.WGO(cfg.wavegen, 0)
        except Exception:
            pass
    return fila


def _resumen_corto(cfg, fila):
    if cfg.modo == "escalon":
        return (f"t10-90={fila.get('t_subida_10_90_ms', float('nan')):.1f} ms, "
                f"ts(5nm)={fila.get('ts_5nm_ms', float('nan')):.1f} ms, "
                f"bump={fila.get('bump_lento_nm', float('nan')):.1f} nm")
    if cfg.modo == "rampa":
        return (f"v={fila.get('v_um_s', float('nan')):.2f} µm/s, "
                f"e={fila.get('error_mediano_nm', float('nan')):.1f} nm, "
                f"τ={fila.get('tau_desde_lag_ms', float('nan')):.1f} ms")
    return (f"σ={fila.get('sigma_nm', float('nan')):.2f} nm, "
            f"deriva={fila.get('deriva_nm_min', float('nan')):.2f} nm/min")


# %% -- El barrido: correr una lista de corridas --------------------------
def correr_barrido(pidevice, ctx, configs, nombre="barrido", pausa_s=0.3,
                   revisar=True):
    """Corre una lista de `Corrida` y devuelve un DataFrame con una fila por
    corrida. Guarda ese DataFrame en resultados/barridos/.

    Esta es la función que reemplaza al "editar el script y volver a
    correrlo" — un barrido es una lista, no una sesión de edición.
    """
    if revisar:
        revisar_lista(configs, ctx["t_servo_s"])
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filas = []
    print(f"\n{'='*68}\n[barrido: {nombre}] {len(configs)} corridas\n{'='*68}")
    for i, cfg in enumerate(configs, 1):
        print(f"\n--- {i}/{len(configs)} ---")
        filas.append(corrida(pidevice, cfg, ctx))
        time.sleep(pausa_s)

    df = pd.DataFrame(filas)
    salida = RESULTADOS_BARRIDOS / f"barrido_{nombre}_{ts}.csv"
    df.to_csv(salida, index=False)
    n_ok = int(df["ok"].sum())
    try:
        ruta = salida.relative_to(REPO_ROOT)
    except ValueError:
        ruta = salida
    print(f"\n{'='*68}\n[barrido: {nombre}] {n_ok}/{len(configs)} ok "
          f"→ {ruta}\n{'='*68}")
    return df


# %% -- Figuras -----------------------------------------------------------
_ESTILO = {
    "font.family": "serif", "font.size": 11, "axes.labelsize": 13,
    "xtick.labelsize": 11, "ytick.labelsize": 11, "figure.dpi": 120,
}


def _figura_corrida(t_ms, columnas, cfg, fila, base):
    plt.rcParams.update(_ESTILO)
    tgt, cur = columnas.get("target_um"), columnas.get("current_um")
    err = columnas.get("error_um")
    if tgt is None or cur is None:
        return
    t0 = fila.get("t_escalon_ms", 0.0) or 0.0
    ref = fila.get("x_final_um", cfg.centro_x)

    fig, ax = plt.subplots(2, 1, figsize=(6.5, 5), sharex=True)
    ax[0].plot(t_ms - t0, (tgt - ref) * 1e3, lw=1.2, color="#1f77b4", label="comandada")
    ax[0].plot(t_ms - t0, (cur - ref) * 1e3, lw=0.9, color="#d62728", label="real")
    ax[0].set_ylabel(r"$x - x_{\rm final}$ [nm]")
    ax[0].legend(frameon=False)
    ax[0].set_title(f"{cfg.modo} | WTR={cfg.wtr} RTR={cfg.rtr} DCO={cfg.dco} "
                    f"A={cfg.amplitud_um} µm", fontsize=10)
    if err is not None:
        ax[1].plot(t_ms - t0, err * 1e3, lw=0.8, color="k")
    ax[1].axhline(5, color="gray", lw=0.5, ls="--")
    ax[1].axhline(-5, color="gray", lw=0.5, ls="--")
    ax[1].set_ylabel("error [nm]")
    ax[1].set_xlabel("t [ms]")
    plt.tight_layout()
    plt.savefig(RESULTADOS_FIGURAS / f"{base}.pdf", bbox_inches="tight", dpi=200)
    plt.close(fig)


def graficar_barrido(df, x, y, color_por=None, nombre="barrido",
                     logx=False, logy=False):
    """Figura de resumen del barrido: `y` vs `x`, una serie por `color_por`.

    Ej.: graficar_barrido(df, 'rtr', 'ts_5nm_ms', color_por='dco')
         graficar_barrido(df, 'v_um_s', 'error_mediano_nm', logx=True, logy=True)
    """
    plt.rcParams.update(_ESTILO)
    d = df[df["ok"]] if "ok" in df else df
    fig, ax = plt.subplots(figsize=(6, 4))
    grupos = d.groupby(color_por) if color_por else [("", d)]
    for etiqueta, g in grupos:
        g = g.sort_values(x)
        ax.plot(g[x], g[y], "o-", lw=1.2, ms=5,
                label=f"{color_por}={etiqueta}" if color_por else None)
    if logx:
        ax.set_xscale("log")
    if logy:
        ax.set_yscale("log")
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    if color_por:
        ax.legend(frameon=False)
    plt.tight_layout()
    salida = RESULTADOS_FIGURAS / f"barrido_{nombre}_{y}_vs_{x}.pdf"
    plt.savefig(salida, bbox_inches="tight", dpi=200)
    plt.show()
    try:
        print(f"[figura] {salida.relative_to(REPO_ROOT)}")
    except ValueError:
        print(f"[figura] {salida}")


# %% ======================================================================
#    BARRIDOS PREDEFINIDOS — cada uno responde UNA pregunta
#    (son funciones que devuelven listas de Corrida; no tocan el hardware)
# =========================================================================

def barrido_rtr_dco(amplitud_um=1.0, rtrs=(1, 2, 5, 10, 25),
                    dcos=(True, False), repeticiones=2):
    """PREGUNTA: ¿cuánto tarda de verdad en asentar un escalón, con y sin DCO?

    Ítem 5 del protocolo. El único número de asentamiento con DCO=False que
    existe hoy es una inferencia ('≲52 ms'), porque todas esas corridas
    usaron ventanas de ≤82 ms — más cortas que el asentamiento que querían
    medir. Con RTR se abre la ventana sin perder la subida:

        ventana = 8192 × RTR × 40 µs      resolución = RTR × 40 µs
        RTR=1  → 328 ms, 40 µs      RTR=10 → 3.3 s,  400 µs
        RTR=2  → 655 ms, 80 µs      RTR=25 → 8.2 s,  1 ms

    Con RTR=10 la subida (18 ms) todavía tiene ~45 muestras. Ese es el
    punto: RTR compra ventana casi gratis, N_TOTAL no compra nada.
    """
    configs = []
    for dco in dcos:
        for rtr in rtrs:
            for r in range(repeticiones):
                configs.append(escalon(
                    rtr=rtr, amplitud_um=amplitud_um, dco=dco, repeticion=r,
                    etiqueta=f"rtrdco_rtr{rtr}_dco{int(dco)}",
                    notas="ítem 5 protocolo: ts real con y sin DCO, misma ventana",
                ))
    return configs


def barrido_amplitud(amplitudes_um=(0.01, 0.1, 1.0, 10.0, 50.0),
                     dcos=(True, False), rtr=5, repeticiones=2):
    """PREGUNTA: ¿el bump de DCO y la subida escalan con el tamaño del escalón?

    [MEDIDO §8.2] el bump vale 30–105 nm de 20 nm a 200 µm de escalón: casi
    constante en valor ABSOLUTO. Eso es la firma de un término aditivo del
    controlador, no de slew-rate ni del lag e=v·τ. Y t10–90 ≈ 18 ms es el
    mismo para 200 nm y para 200 µm — o sea el lazo es lineal en ese rango.
    Este barrido lo repite bien controlado, con DCO registrado y la misma
    ventana para todos.
    """
    return [escalon(rtr=rtr, amplitud_um=a, dco=dco, repeticion=r,
                    etiqueta=f"amp_{a}um_dco{int(dco)}",
                    notas="linealidad del lazo + escalado del bump de DCO")
            for dco in dcos for a in amplitudes_um for r in range(repeticiones)]


def barrido_wtr(amplitud_um=1.0, wtrs=(2, 5, 10, 20, 50, 100, 200),
                speedupdown_frac=0.2, n_total=400, repeticiones=2):
    """PREGUNTA: ¿sigue valiendo e = v·τ, con τ constante?

    WTR es el knob de VELOCIDAD:  v = Δx_por_punto / (WTR × 40 µs),
    con Δx_por_punto fijado por amplitud y n_total. Barrer WTR barre v sin
    tocar la geometría de la trayectoria.

    [MEDIDO §3] los 43 puntos del 01/09 colapsan sobre e = v·τ con
    τ = 12.1 ms constante en cuatro décadas de velocidad. Si este barrido
    reproduce eso, el lag es un desplazamiento rígido conocido → se corrige
    (ver barrido_lag_wos) en vez de pagarlo bajando la velocidad.
    """
    return [Corrida(modo="rampa", amplitud_um=amplitud_um, n_total=n_total,
                    speedupdown=int(n_total * speedupdown_frac),
                    wtr=w, rtr=max(1, w // 4), dco=False, repeticion=r,
                    etiqueta=f"wtr{w}",
                    notas="e = v·tau: tau debe salir constante")
            for w in wtrs for r in range(repeticiones)]


def barrido_lag_wos(amplitud_um=1.0, wtr=20, n_total=400, taus_ms=(0, 6, 12.1, 18)):
    """PREGUNTA: ¿la corrección de lag funciona EN VIVO, no solo en post?

    Ítem 4 del protocolo. En un tramo de velocidad constante, adelantar el
    comando τ en el TIEMPO equivale exactamente a sumarle v·τ en POSICIÓN —
    y `WOS` suma una constante a todo lo que reproduce el generador. Así
    que: medir v en la corrida con WOS=0, y repetir con WOS = v·τ.

    OJO: en un ciclo ida+vuelta la corrección tiene signos opuestos en cada
    mitad, y WOS es una sola constante para toda la tabla. Este barrido
    solo tiene sentido leído sobre la IDA. Para el ciclo completo hay que
    hornear la corrección punto a punto (WAV_PNT), no WOS.

    Se corre en dos pasos: primero con taus_ms=(0,) para medir v; después
    pasando esa v acá abajo. Por eso `wos` se calcula recién al final.
    """
    # Δx por punto de la ida; la ida son n_total/2 puntos que recorren 2·A
    dx_punto = (2 * amplitud_um) / (n_total / 2)
    v_estimada = dx_punto / (wtr * 40e-6)     # µm/s, con T=40 µs nominal
    configs = []
    for tau_ms in taus_ms:
        configs.append(Corrida(
            modo="rampa", amplitud_um=amplitud_um, n_total=n_total,
            speedupdown=int(n_total * 0.2), wtr=wtr, rtr=max(1, wtr // 4),
            dco=False, wos=v_estimada * (tau_ms * 1e-3),
            etiqueta=f"wos_tau{tau_ms}ms",
            notas=f"v estimada={v_estimada:.2f} µm/s; WOS=v·tau"))
    return configs


def barrido_deriva(minutos=(1, 1), dcos=(True, False), t_servo_us_nominal=40.0):
    """PREGUNTA: si apago DCO para asentar más rápido, ¿cuánto deriva?

    Ítem 2 del protocolo, y la condición para poder adoptar DCO=False como
    default. DCO existe para compensar deriva térmica/mecánica lenta; §8.2
    mostró que apagarlo acelera el asentamiento ~2.7×, pero nadie midió
    todavía qué se paga a cambio en la escala de minutos.

    RTR se elige para que la ventana cubra los minutos pedidos:
        RTR = ceil(T_obs / (8192 × 40 µs))
    y la wave plana tiene que durar al menos lo mismo → n_total × WTR.
    """
    configs = []
    for dco in dcos:
        for min_i, mins in enumerate(minutos):
            t_obs_s = mins * 60
            rtr = int(np.ceil(t_obs_s / (N_MAX_TABLA * t_servo_us_nominal * 1e-6)))
            # wave plana: n_total puntos × WTR ciclos ≥ t_obs
            wtr = int(np.ceil(t_obs_s / (N_MAX_TABLA * t_servo_us_nominal * 1e-6)))
            configs.append(Corrida(
                modo="quieto", n_total=N_MAX_TABLA, wtr=wtr, rtr=rtr,
                dco=dco, repeticion=min_i,
                drc_tablas=(1, 2), drc_fuentes=("A", "B"), drc_opciones=(2, 2),
                etiqueta=f"deriva_{mins}min_dco{int(dco)}",
                notas="ítem 2 protocolo: costo en deriva de apagar DCO"))
    return configs


def barrido_ruido(rtrs=(1,), repeticiones=3):
    """PREGUNTA: el piso de ruido de 1.7 nm con su línea de 50 Hz, ¿de dónde sale?

    Ítem 3 del protocolo, versión de lazo cerrado. Graba posición real +
    voltaje del piezo (opción 7) con la platina quieta: si el 50 Hz está en
    la posición pero NO en el voltaje de control, es pickup en el sensor o
    en el cableado; si está en los dos, el lazo lo está inyectando.

    (La variante de lazo abierto — SVO=False — necesita
    confirmar_lazo_abierto=True y está sin verificar: con el servo abierto
    el generador comanda voltaje, no posición.)
    """
    return [Corrida(modo="quieto", n_total=N_MAX_TABLA, wtr=1, rtr=rtr,
                    dco=False, repeticion=r,
                    drc_tablas=(1, 2, 3), drc_fuentes=("A", "A", "A"),
                    drc_opciones=(2, 7, 15),
                    etiqueta=f"ruido_rtr{rtr}",
                    notas="ítem 3: 50 Hz en posición vs. en voltaje de control")
            for rtr in rtrs for r in range(repeticiones)]


# %% ======================================================================
#    USO — descomentar el bloque que se quiera correr
# =========================================================================
if __name__ == "__main__":
    pidevice, ctx = conectar()
    try:
        # --- 1. asentamiento real con y sin DCO (empezar por acá) -------
        df = correr_barrido(pidevice, ctx, barrido_rtr_dco(), nombre="rtr_dco")
        graficar_barrido(df, "rtr", "ts_5nm_ms", color_por="dco", nombre="rtr_dco")
        graficar_barrido(df, "rtr", "bump_lento_nm", color_por="dco", nombre="rtr_dco")

        # --- 2. linealidad del lazo y escalado del bump ------------------
        # df = correr_barrido(pidevice, ctx, barrido_amplitud(), nombre="amplitud")
        # graficar_barrido(df, "salto_nm", "bump_lento_nm", color_por="dco",
        #                  nombre="amplitud", logx=True)

        # --- 3. e = v·tau -----------------------------------------------
        # df = correr_barrido(pidevice, ctx, barrido_wtr(), nombre="wtr")
        # graficar_barrido(df, "v_um_s", "error_mediano_nm", nombre="wtr",
        #                  logx=True, logy=True)
        # graficar_barrido(df, "v_um_s", "tau_desde_lag_ms", nombre="wtr", logx=True)

        # --- 4. corrección de lag en vivo -------------------------------
        # df = correr_barrido(pidevice, ctx, barrido_lag_wos(), nombre="lag_wos")

        # --- 5. deriva con DCO apagado (tarda: minutos por corrida) ------
        # df = correr_barrido(pidevice, ctx, barrido_deriva(), nombre="deriva")

        # --- 6. ruido / 50 Hz -------------------------------------------
        # df = correr_barrido(pidevice, ctx, barrido_ruido(), nombre="ruido")
    finally:
        cerrar(pidevice, volver_a=100.0)
