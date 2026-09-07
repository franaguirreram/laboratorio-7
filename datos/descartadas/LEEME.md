# Corridas descartadas — 2026-09-07

Estas 27 corridas tienen la columna `target_um` con **ceros exactos** en
la cola del archivo, y por eso son inutilizables.

**Qué pasó.** El data recorder del E-517 no se detiene cuando termina la
trayectoria: sigue grabando sus 8192 muestras. Pero en cuanto el
generador se detiene, el canal de posición comandada pasa a valer 0
mientras el de posición real sigue midiendo bien. Si la trayectoria dura
menos que la ventana del grabador, el archivo termina con
`target_um = 0` y `current_um = 101 µm` — y cualquier análisis que
busque el escalón como "el salto más grande del comando" encuentra uno
de −101 µm al final del archivo en vez del de +2 µm del principio.

**Cómo se evita** (implementado en `escalon()` de `scripts/E517_barrido.py`):
que la trayectoria dure toda la ventana, con `WTR = RTR` y
`n_pre + n_post = 8192`.

Detalle completo en `docs/velocidad_ancho_de_banda_y_diseno_de_scans.md` §9.2.

Se conservan acá en vez de borrarse por si hiciera falta reconstruir algo
del canal `current_um`, que sí es válido hasta donde el generador estuvo
corriendo. Se pueden borrar sin perder nada del análisis.
