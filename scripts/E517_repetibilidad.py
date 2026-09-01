#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
E-517 / E-545 — Repetibilidad, comparando distintas velocidades (VEL)

Adaptación de tu script de repetibilidad de Labo 6 (el que guardaba en
C:/Users/NANOFISICA_07/.../MEDICIONES/... con paths fijos de Windows) al
mismo formato que E517_step_response.py y E517_ida_vuelta_speedupdown.py:
conexión PIFtdiGateway, guardado en datos/raw + datos/metadata con
timestamp, gráficos en el mismo estilo.

Se agrega respecto al original: un barrido sobre una LISTA de velocidades
(VEL) en vez de una sola velocidad fija, para poder comparar la
repetibilidad de "antes" (la velocidad que usaban en Labo 6) contra las
velocidades que están usando ahora en los ensayos de dwell time / wave
table.

CONVENCIONES DE TRAZABILIDAD:
    [MEDIDO]      verificado en tus scripts o en los manuales del proyecto
    [INFERENCIA]  interpretación razonable, no verificada explícitamente
    [VERIFICAR]   confirmalo vos antes de correr en el equipo
    [PENDIENTE]   parámetro que falta completar

------------------------------------------------------------------------
QUÉ CAMBIÉ RESPECTO A TU SCRIPT ORIGINAL:
------------------------------------------------------------------------
1. Guardado: reemplacé los paths fijos de Windows por la misma estructura
   datos/raw, datos/metadata, resultados/figuras que usan tus otros dos
   scripts, con nombre de archivo con timestamp (así todas las corridas
   quedan juntas ahí, distinguidas por prefijo + timestamp, igual que
   charlamos para el de step response).
2. Agregué VELOCIDADES (lista) en vez de una VEL fija, y una columna
   "vel[um/s]" en los datos crudos, para poder comparar entre ellas.
3. Agregué un panel extra al gráfico: repetibilidad (std) en función de
   la velocidad, que es literalmente lo que pediste comparar.
4. Guardo un archivo de metadata .txt con los parámetros de la corrida,
   igual que en los otros dos scripts (tu original no lo hacía).
5. NO toqué la lógica de medición en sí (mov_raw, medir_repetibilidad,
   los sleeps de 0.0015*dist+0.07): la dejé tal cual la tenías, porque
   evidentemente ya la validaste con hardware real y no tengo motivo
   para tocarla. Sí renombré/reordené código para que quede en el mismo
   estilo que los otros dos scripts (secciones con # %%).

[VERIFICAR] Unidades de VEL: el manual GCS-3.0 solo dice "Velocity of
    the axis in physical units" (SM160E, comando VEL, p.99) sin dar el
    número concreto -- asumo que son las unidades de posición del eje
    por segundo (µm/s acá), coherente con que target_pos está en µm.
    No encontré en los PDFs del proyecto una tabla que lo confirme en
    unidades explícitas -- si tenés dudas, corré VEL? después de setear
    y comparalo con el tiempo real que tarda un MOV de distancia
    conocida.

[VERIFICAR] mov_raw() manda el comando MOV crudo por pidevice.send(),
    saltando el chequeo de error automático de pipython -- así estaba en
    tu script original (con el comentario de que evita un timeout). Lo
    dejé igual, pero tené en cuenta que si el controlador devuelve un
    error real (target fuera de rango, etc.) NO te vas a enterar acá, a
    diferencia de si usaras pidevice.MOV() directamente.

wait_my() estaba en tu script original pero nunca se llamaba (usan
sleeps fijos en vez de esperar ONT real) -- la dejo tal cual, sin
llamarla, por si la querés usar para debuggear a mano.
"""

# %% -- Imports --------------------------------------------------
from pipython import GCSDevice, pitools
from pi_ftdi_gateway import PIFtdiGateway, cleanup_gcsdevice
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATOS_RAW = REPO_ROOT / "datos" / "raw"
DATOS_METADATA = REPO_ROOT / "datos" / "metadata"
RESULTADOS_FIGURAS = REPO_ROOT / "resultados" / "figuras"
for _dir in (DATOS_RAW, DATOS_METADATA, RESULTADOS_FIGURAS):
    _dir.mkdir(parents=True, exist_ok=True)


# %% -- Parámetros del experimento -------------------------------
AXIS = 'B'
CHANNEL = 2

START = 200.0
END = 0.0
N_POS = 100
N_REPS = 30

# [PENDIENTE] Completá con las velocidades que querés comparar. Dejé
# 100 (la que usaba tu script original de Labo 6) como primer elemento
# para tener el punto de referencia "antes"; agregá las velocidades
# "de ahora" que quieras comparar.
VELOCIDADES = [100.0]  # um/s [VERIFICAR unidades, ver docstring]

HOME = START
TARGET_POS = np.linspace(START, END, N_POS + 1)

PRE_MOV_WAIT = 0.1    # s  (definido en tu original, no se usaba -- lo dejo)
QUERY_WAIT = 0.06     # s  (idem)
ONTARGET_TOUT = 10.0  # s  (idem)

print(f"[config] eje={AXIS}, N_POS={N_POS}, N_REPS={N_REPS}, "
      f"velocidades a comparar={VELOCIDADES}")


# %% -- Helpers (idénticos a tu script original) -------------------
def wait_my(pidevice, axes, timeout=10):
    """Sin usar en el flujo principal -- queda para debug manual."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        pos = pidevice.qPOS()[AXIS]
        ont = pidevice.qONT()[AXIS]
        moving = pidevice.IsMoving()[AXIS]
        print(f"POS={pos:8.3f}  ONT={ont}  MOV={moving}")
        if ont:
            return
        time.sleep(0.1)
    raise TimeoutError("No llegó al target")


def mov_raw(pidevice, axis, position):
    """
    Envía el comando MOV como cadena GCS cruda, evitando el ciclo
    automático ERR? de pipython que producía el timeout. [MEDIDO, de tu
    script original]
    """
    cmd = f"MOV {axis} {position:.6f}\n"
    pidevice.send(cmd)


def medir_repetibilidad(pidevice, axis, home, targets, n_reps):
    """Idéntica a tu función original."""
    data = []
    for target in targets:
        for rep in range(n_reps):
            mov_raw(pidevice, axis, home)
            dist = abs(home - target)
            time.sleep(0.0015 * dist + 0.07)

            mov_raw(pidevice, axis, target)
            time.sleep(0.0015 * dist + 0.07)

            qpos = pidevice.qPOS()[axis]
            data.append([target, rep, qpos])
    return data


# %% -- Medición: barrido sobre VELOCIDADES ------------------------
raw_data = []

try:
    with GCSDevice('E-517', gateway=PIFtdiGateway()) as pidevice:
        print(f"[conexión] {pidevice.qIDN().strip()}")

        pidevice.ONL([CHANNEL], [True])
        pidevice.SVO(AXIS, True)

        for vel in VELOCIDADES:
            pidevice.VEL(AXIS, vel)
            print(f"[medición] vel={vel} um/s -- comenzando...")

            data_vel = medir_repetibilidad(
                pidevice, AXIS, HOME, TARGET_POS, N_REPS
            )
            for fila in data_vel:
                raw_data.append([vel] + fila)

            print(f"[medición] vel={vel} um/s -- terminada.")

    print("[medición] Todas las velocidades terminadas.")

except Exception as e:
    print(f"❌ Error durante la medición: {e}")
    raise


# %% -- Armar DataFrames y resumen ---------------------------------
df_raw = pd.DataFrame(
    raw_data,
    columns=["vel[um/s]", "target_pos[um]", "rep", "qpos[um]"],
)

resumen = (
    df_raw
    .groupby(["vel[um/s]", "target_pos[um]"])["qpos[um]"]
    .agg(media="mean", std="std", n="count")
    .reset_index()
)
resumen["sem[um]"] = resumen["std"] / np.sqrt(resumen["n"])
resumen["offset[um]"] = resumen["media"] - resumen["target_pos[um]"]

# repetibilidad promedio por velocidad (lo que querés comparar)
repetibilidad_por_vel = (
    resumen
    .groupby("vel[um/s]")["std"]
    .agg(std_medio="mean", std_max="max")
    .reset_index()
)
repetibilidad_por_vel["std_medio[nm]"] = repetibilidad_por_vel["std_medio"] * 1000
repetibilidad_por_vel["std_max[nm]"] = repetibilidad_por_vel["std_max"] * 1000

print(resumen)
print("\n[repetibilidad por velocidad]")
print(repetibilidad_por_vel[["vel[um/s]", "std_medio[nm]", "std_max[nm]"]])


# %% -- Guardar --------------------------------------------------
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
nombre_base = f"E517_repetibilidad_{timestamp}"

df_raw.to_csv(DATOS_RAW / f"{nombre_base}.csv", index=False)
resumen.to_csv(DATOS_RAW / f"{nombre_base}_resumen.csv", index=False)

with open(DATOS_METADATA / f"{nombre_base}_metadata.txt", 'w') as f:
    f.write(f"E517_repetibilidad.py -- {timestamp}\n")
    f.write(f"AXIS={AXIS} CHANNEL={CHANNEL}\n")
    f.write(f"START={START} END={END} N_POS={N_POS} N_REPS={N_REPS}\n")
    f.write(f"VELOCIDADES={VELOCIDADES}\n")
    f.write("\nrepetibilidad_por_vel:\n")
    f.write(repetibilidad_por_vel.to_string(index=False))
    f.write("\n")

print(f"[guardado] {nombre_base}.csv + {nombre_base}_resumen.csv + "
      f"{nombre_base}_metadata.txt")


# %% -- Gráficos --------------------------------------------
plt.rcParams.update({
    'font.family': 'serif',
    'font.size': 12,
    'axes.labelsize': 14,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    'figure.dpi': 120,
})

colores = plt.cm.tab10(np.linspace(0, 1, len(VELOCIDADES)))

fig, ax = plt.subplots(3, 1, figsize=(6, 9))

# Panel 1: posición medida vs enviada, por velocidad
for vel, color in zip(VELOCIDADES, colores):
    sub = resumen[resumen["vel[um/s]"] == vel]
    ax[0].errorbar(
        sub["target_pos[um]"], sub["media"], yerr=sub["sem[um]"],
        fmt=".", capsize=3, color=color, label=f"vel={vel:g} um/s",
    )
lims = [resumen["target_pos[um]"].min(), resumen["target_pos[um]"].max()]
ax[0].plot(lims, lims, color="black", ls="--", lw=0.8, label="esperado")
ax[0].legend(fontsize=8)
ax[0].set_xlabel("Posición enviada [µm]")
ax[0].set_ylabel("Posición autosensada [µm]")
ax[0].grid()

# Panel 2: offset respecto de la posición enviada, por velocidad
for vel, color in zip(VELOCIDADES, colores):
    sub = resumen[resumen["vel[um/s]"] == vel]
    ax[1].errorbar(
        sub["target_pos[um]"], sub["offset[um]"], yerr=sub["sem[um]"],
        fmt=".", capsize=3, color=color, label=f"vel={vel:g} um/s",
    )
ax[1].axhline(0, color="black", ls="--", lw=0.8)
ax[1].set_xlabel("Posición enviada [µm]")
ax[1].set_ylabel("Diferencia de posición [µm]")
ax[1].legend(fontsize=8)
ax[1].grid()

# Panel 3: repetibilidad (std) en función de la velocidad -- la comparación pedida
ax[2].scatter(
    repetibilidad_por_vel["vel[um/s]"],
    repetibilidad_por_vel["std_medio[nm]"],
    color="tab:blue", label="std medio (todas las posiciones)",
)
ax[2].scatter(
    repetibilidad_por_vel["vel[um/s]"],
    repetibilidad_por_vel["std_max[nm]"],
    color="tab:red", marker="x", label="std máximo",
)
ax[2].set_xlabel("Velocidad [µm/s]")
ax[2].set_ylabel("Repetibilidad (std) [nm]")
ax[2].legend(fontsize=8)
ax[2].grid()

plt.tight_layout()
plt.savefig(RESULTADOS_FIGURAS / f"{nombre_base}.pdf", bbox_inches='tight', dpi=200)
plt.savefig(RESULTADOS_FIGURAS / f"{nombre_base}.png", bbox_inches='tight', dpi=200)
plt.show()

print(f"\n[fin] gráfico guardado como {nombre_base}.pdf/.png")
