# Protocolo de adquisición — wave generator + data recorder (E-545/E-517)

Pasos, en orden, para correr cualquiera de los scripts de `scripts/`.
Unidades: posición en µm, tiempo en ms salvo que se indique µs, error en
nm (posición × 1000 al graficar/reportar).

## 0. Setup físico

1. Conectar el E-545/E-517 por USB.
2. Verificar que el equipo está libre (no hay otra conexión activa):
   ```python
   from pi_ftdi_gateway import list_devices
   list_devices()
   ```
3. En Spyder, confirmar que el intérprete de Python apunta a
   `~/python-envs/pi/bin/python3.14` (Preferences → Python Interpreter).

## 1. Diagnóstico (una vez por sesión, o si algo no anda)

Correr `scripts/E517_diagnostico.py` completo. Confirma:
- Identidad del equipo (`qIDN`).
- Rango físico del eje (`qTMN`/`qTMX` — en el E-517 medido: 0 a 200 µm).
- Servo update time (`SPA 0x0E000200` — medido: 40 µs, 25 kHz).
- Cantidad de wave generators, tablas, y puntos máximos por tabla
  (medido: 3 wave generators, 3 record tables, 8192 puntos c/u).
- Que los comandos de wave generator/data recorder responden (`WCL`,
  `WAV_LIN`, `qGWD`, `WGC`, `WTR`, `WOS`, `qHDR`, `qDRR`).

## 2. Cargar una trayectoria (wave table)

Tres formas, según el caso (ver `e545-pi-ftdi-gateway/README.md` para el
detalle de cada comando):

- **`pitools.writewavepoints()`** (usa `WAV_PNT` por debajo): para
  cargar un array de puntos arbitrario, calculado en Python. Límite
  medido en este E-517: máximo 72 puntos por comando — pasar siempre
  `bunchsize<=50`.
- **`WAV_LIN`**: una rampa recta en un solo llamado (offset → offset +
  amplitude, en `numpoints` puntos). Con `amplitude` negativa NO genera
  una rampa descendente en este firmware — no usar para el tramo de
  "vuelta".
- **`WAV_RAMP`**: rampa simétrica completa (sube y baja) en un solo
  llamado, con un parámetro `center` para el índice del pico. Es la
  forma correcta de cargar un ciclo ida+vuelta sin escribir puntos.

En los tres casos: `speedupdown` (puntos de aceleración/desaceleración
en los extremos) suaviza la curva — sin esto, la trayectoria tiene
cambios de velocidad instantáneos en los extremos, que el sistema físico
no puede seguir bien (se ve como redondeo/lag extra en el gráfico).

Verificar siempre releyendo con `qGWD` antes de disparar el movimiento.

## 3. Configurar reproducción y grabación

```python
pidevice.WTR(wave_gen, WTR, 0)      # ciclos de servo por punto de la wave
pidevice.WGC(wave_gen, ciclos)      # cuántas veces repite la tabla
pidevice.WOS(wave_gen, 0.0)         # offset extra (0 si la tabla ya es absoluta)

pidevice.DRC(tables=[1,2,3], sources=['A','A','A'], options=[1,2,3])
# options: 1=target, 2=current, 3=error, 7=voltaje piezo, 15=salida de control
pidevice.RTR(RTR)                   # ciclos de servo por muestra grabada
```

**Importante**: `WTR` y `RTR` son relojes independientes. Si son
distintos, la cantidad de muestras a pedir con `qDRR` NO es la cantidad
de puntos de la wave table — es `N_puntos_wave × WTR / RTR`. Confundir
esto da un gráfico que muestra solo una fracción del movimiento real
(bug real encontrado el 2026-08-27, ver `docs/RESUMEN_conexion_E545_macOS.md`).

## 4. Disparar y leer

```python
pidevice.WGO(wave_gen, 1)
pitools.waitonwavegen(pidevice, wavegens=wave_gen, timeout=...)
pidevice.WGO(wave_gen, 0)

pidevice.qDRR(tabla, 1, n_muestras)
# qDRR/qGWD son asíncronos: hay que esperar bufstate antes de leer bufdata
while pidevice.bufstate is not True:
    time.sleep(0.005)
datos = pidevice.bufdata[0]
```

## 5. Cerrar

`cleanup_gcsdevice(pidevice)`, no `pidevice.close()` suelto (ver
`e545-pi-ftdi-gateway/README.md` — motivo: acumulación de callbacks al
reconectar en la misma consola).

## 6. Guardado

Los scripts de `scripts/` ya guardan solos: CSV crudo en `datos/raw/`,
metadata en `datos/metadata/`, figura en `resultados/figuras/`, con
timestamp en el nombre para no pisar corridas anteriores.
