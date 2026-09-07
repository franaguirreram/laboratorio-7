# Protocolo de adquisición — wave generator + data recorder (E-545/E-517)

Pasos, en orden, para correr cualquiera de los scripts de `scripts/`.
Unidades: posición en µm, tiempo en ms salvo que se indique µs, error en
nm (posición × 1000 al graficar/reportar).

## Próxima sesión: qué medir, en orden

> **Desde 2026-09-07 los seis ítems de abajo están implementados como
> barridos en `scripts/E517_barrido.py`** — una función `corrida()` que se
> llama en un `for`, en vez de editar el script entre medición y medición.
> Ese script lee el ciclo de servo del equipo (no lo hardcodea), llama
> `WSL` explícitamente (ítem 1), guarda `DCO` y todo el estado releído del
> controlador en la metadata (§8.3), y usa `RTR` como knob de ventana
> (§8.1). Los scripts viejos quedan como referencia de lo ya medido.
>
> Explicación física de todo esto, para leer antes:
> `docs/como_funciona_la_platina.md`.

Actualizado 2026-09-03 a partir de
`docs/velocidad_ancho_de_banda_y_diseno_de_scans.md` (§6 y §8). Cada
ítem es una medición concreta, no una idea abstracta — parar acá y
ajustar el plan si alguno da un resultado inesperado, antes de seguir
al siguiente.

1. **Confirmar el mapeo eje↔wavegen↔tabla.** Nunca se llamó `WSL` en
   este proyecto — todos los scripts asumen tabla 1 → wavegen 1 → eje A
   sin haberlo verificado explícitamente. Antes de tocar nada más:
   ```python
   print(pidevice.qWSL([1, 2, 3]))   # {wavegen: tabla conectada, o 0}
   ```
   Si da `{1: 0, 2: 0, 3: 0}` (nada conectado por default), hay que
   conectar a mano con `WSL` antes de cada `WAV_*` — revisar si los
   scripts actuales dependen de una conexión implícita que la propia
   firmware arma sola al cargar la tabla, o si viene funcionando por
   otra razón. Esto es un prerrequisito duro para el paso 6 (dos
   generadores a la vez).
2. **Test de deriva con DCO apagado** (§8.2 del doc). `DCO` corta el
   asentamiento a un tercio, pero existe para compensar deriva lenta —
   antes de dejarlo apagado como default hay que saber cuánto deriva
   sin él. `MOV` a un punto fijo, `DCO(['A','B'],[False,False])`,
   `RTR` grande (p. ej. 200 → dt_grabación=8 ms, ventana de 8192
   muestras ≈ 65 s) y grabar posición quieta varios minutos
   (repetir `qDRR`/`qGWD` o encadenar corridas). Comparar el drift
   (µm/min) contra la misma corrida con DCO=True.
3. **Diagnóstico del ruido de 50 Hz** (§4b del doc). Es el término
   dominante del piso de ruido (2.4 nm) y está fuera del ancho de banda
   del servo. Grabar con `DRC` opción 7 (voltaje de control) además de
   la posición, primero con `SVO` cerrado (normal) y después con
   `SVO(['A'],[False])` (lazo abierto). Si el pico de 50 Hz sigue en la
   posición con el lazo abierto → pickup en sensor/cableado. Si
   desaparece → lo está inyectando el lazo.
4. **Verificación EN VIVO de la corrección de lag** (§3 del doc). Hasta
   ahora la corrección de `e = v·τ` fue solo en post-proceso. La forma
   más simple de probarla en vivo, sin tocar la wave table: cargar un
   **tramo de UNA sola dirección** (`WAV_LIN`, no el ciclo ida+vuelta
   completo) a velocidad constante, dejarlo correr sin corregir para
   medir `v`, y en la siguiente corrida usar
   `pidevice.WOS(wave_gen, v*tau)` (`τ ≈ 12.1 ms` medido) antes de
   disparar — para un tramo de velocidad constante, adelantar en el
   TIEMPO por `τ` equivale exactamente a sumar `v·τ` en POSICIÓN (por
   eso `WOS`, que es un corrimiento de valor, funciona acá). Confirmar
   que el error en vivo baja al nivel de la fig. 03.
   El ciclo ida+vuelta completo es más difícil: necesita `+v·τ` en la
   ida y `−v·τ` en la vuelta, signos opuestos dentro de la MISMA tabla,
   así que un solo `WOS` (constante para toda la tabla) no alcanza —
   hay que hornear la corrección en el `offset`/`amplitude` de cada
   segmento por separado, lo que reabre el problema ya conocido de que
   `WAV_LIN` con amplitud negativa no arma la vuelta en este firmware
   (§2.1). Verificar primero el caso de una dirección; el ciclo
   completo puede necesitar `WAV_PNT` con los puntos ya corregidos
   calculados en Python en vez de `WAV_RAMP`.
5. **Barrido de RTR para ventana completa, con y sin DCO.** El único
   número de asentamiento completo con DCO=False que hay hoy es una
   inferencia (§8.2: "≲52 ms, probablemente más rápido"), no una
   medición directa — todas las corridas DCO=False del 02/09 usaron
   ventanas de ≤82 ms. Repetir `E517_step_response.py` con `RTR=5` o
   `RTR=10` (en vez de tocar `N_TOTAL`, ver §8.1) para varios escalones,
   con DCO=True y DCO=False, y así tener el `ts_5nm` real de los dos
   casos en la misma ventana.
6. **Recién después de 1**: prototipo de dos wave generators
   sincronizados (X = una línea, Y = la escalera de líneas) para el
   raster de §5. Ver la sección "Wave generator para raster (X+Y)"
   más abajo — es la parte menos probada de todo este documento.

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

## 2. Controlar el wave generator

### 2.0 Vocabulario — tres cosas distintas que se llaman parecido

| objeto | qué es | cuántos hay | comando que lo referencia |
|---|---|---|---|
| **wave table** | un buffer de puntos (posiciones) en la memoria del controlador | 3 tablas, 8192 puntos c/u [MEDIDO — `qWMS`/`qTWG`, §1] | `WCL`, `WAV_LIN`, `WAV_RAMP`, `WAV_PNT`, `qGWD` |
| **wave generator (WG)** | el "reproductor": lee una tabla a una tasa fija y empuja esos valores como setpoint de un eje | 3 [MEDIDO — `qTWG`, §1] | `WTR`, `WGC`, `WOS`, `WGO`, `WSL` |
| **eje** | el motor/piezo físico (`A`, `B`, ...) | 2 usados acá | `MOV`, `SVO`, `DCO` |

La tabla y el generador **no son lo mismo**: la tabla es memoria pasiva,
el generador es lo que la reproduce. `WSL(wavegen, tabla)` es lo que
conecta un generador a una tabla — **nunca se llamó en este proyecto**
(ver ítem 1 de "Próxima sesión" arriba). Todos los scripts actuales
usan `TABLA_X = WGEN_X = 1` y asumen que ya están conectados por
default; confirmarlo con `qWSL` antes de asumir que un WG≠tabla
funciona igual.

### 2.1 Cargar una trayectoria en la tabla

Tres formas, según el caso (firmas reales de `pipython`, no aproximadas —
`append` es común a las tres: `'X'` = empieza de cero en `firstpoint`,
`'&'` = agrega un tramo nuevo a continuación del último punto cargado,
`'+'` = SUMA los valores nuevos a los que ya había en esos índices, sin
extender la tabla):

```python
# Rampa recta en un solo llamado: offset -> offset+amplitude, numpoints puntos.
pidevice.WAV_LIN(table, firstpoint, numpoints, append,
                  speedupdown, amplitude, offset, seglength)

# Rampa simétrica completa (sube Y baja) en un solo llamado.
# center = índice del pico (0-based). Es la forma correcta de cargar
# un ciclo ida+vuelta sin escribir los puntos uno por uno.
pidevice.WAV_RAMP(table, firstpoint, numpoints, append,
                   center, speedupdown, amplitude, offset, seglength)

# Puntos arbitrarios, calculados en Python. Usar pitools.writewavepoints()
# (bunchsize<=50) en vez de WAV_PNT directo -- límite medido en este
# E-517: máximo 72 puntos por comando WAV_PNT crudo.
pitools.writewavepoints(pidevice, table=1, wavepoints=array,
                         bunchsize=50)
```

- **`speedupdown`** (puntos de aceleración/desaceleración en los
  extremos) suaviza la curva — sin esto, la trayectoria tiene cambios
  de velocidad instantáneos en los extremos que el sistema físico no
  puede seguir bien (se ve como redondeo/lag extra, ver fig. 03 del
  análisis de velocidad).
- **`amplitude` negativa en `WAV_LIN` no genera una rampa descendente en
  este firmware** [MEDIDO, 2026-08-28] — por eso el "vuelta" de un ciclo
  ida+vuelta se carga con `WAV_RAMP` (un solo llamado, sube y baja) y no
  con dos `WAV_LIN`. No se probó todavía si `append='+'` (sumar sobre
  una rampa ascendente ya cargada) logra el mismo efecto que una
  "amplitud negativa" — quedaría como alternativa a `WAV_RAMP` si en
  algún momento hiciera falta más control fino sobre el tramo de vuelta.
- **`offset`** acá es el valor absoluto de arranque de ESA curva
  puntual — no confundir con `WOS` (offset del generador, ver 2.2:
  aplica a TODO lo que reproduzca ese WG, se puede cambiar sin recargar
  la tabla).

Verificar siempre releyendo con `qGWD(table, firstpoint, numpoints)` +
`bufstate`/`bufdata` antes de disparar el movimiento.

### 2.2 Configurar reproducción y grabación

```python
pidevice.WTR(wave_gen, WTR, 0)      # ciclos de servo por punto de la wave (dwell), interpol=0
pidevice.WGC(wave_gen, ciclos)      # cuántas veces repite la tabla completa por disparo
pidevice.WOS(wave_gen, 0.0)         # offset de SALIDA del generador: se suma a TODO punto
                                     # reproducido, sin tocar la tabla -- sirve para
                                     # corregir el lag (e=v·τ) en un tramo de UNA sola
                                     # dirección sin recargar la wave (ítem 4 de
                                     # "Próxima sesión"); no alcanza para un ciclo
                                     # ida+vuelta completo, que necesita signos opuestos.

pidevice.DRC(tables=[1,2,3], sources=['A','A','A'], options=[1,2,3])
# options: 1=target, 2=current, 3=error, 7=voltaje piezo, 15=salida de control
pidevice.RTR(RTR)                   # ciclos de servo por muestra grabada
```

`WTR` (dwell del wave) y `RTR` (dwell del recorder) son **relojes
independientes**, cada uno en ciclos de servo (40 µs). Confundirlos
tiene dos consecuencias distintas y hay que tener las dos presentes:

- Si son distintos, la cantidad de muestras a pedir con `qDRR` NO es la
  cantidad de puntos de la wave table — es `N_puntos_wave × WTR / RTR`.
  Confundir esto da un gráfico que muestra solo una fracción del
  movimiento real (bug real encontrado el 2026-08-27, ver
  `docs/RESUMEN_conexion_E545_macOS.md`).
- `N_TOTAL` de la wave NO extiende la ventana observada más allá de
  `8192 × RTR × 40 µs` — con `RTR=1` (default en casi todos los scripts
  actuales) esa ventana está topeada en ~328 ms sin importar cuántos
  puntos tenga la wave. Para observar más tiempo (p. ej. el
  asentamiento completo de un escalón, que tarda >100 ms) el knob es
  `RTR`, no `N_TOTAL` ni `WTR` — ver
  `docs/velocidad_ancho_de_banda_y_diseno_de_scans.md` §8.1.

## 3. Disparar y leer

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

`WGO(wave_gen, mode)` — `mode` es un bitmask, no un booleano:
**bit 0 = 1 arranca ese generador de inmediato, sincronizado al
siguiente tick de servo** [MEDIDO — manual PZ214E p. 165]. El data
recorder arranca AUTOMÁTICAMENTE al disparar `WGO` (no hace falta un
comando de trigger aparte para él) — pero hay que tener `DRC`+`RTR`
configurados ANTES del `WGO`, no después.

`WGO` acepta una lista: `pidevice.WGO([1, 2], [1, 1])` debería arrancar
los generadores 1 y 2 **en el mismo tick de servo** — es el mecanismo
esperado para sincronizar X e Y en un raster (ver última sección de
este documento). **No se probó todavía en este equipo** si de verdad
arrancan atómicamente juntos o si hay un corrimiento de algunos ciclos
entre uno y otro; confirmarlo con un escalón chico en ambos ejes y
mirando el offset entre las dos curvas grabadas antes de confiar en
esto para un raster real.

## 4. Cerrar

`cleanup_gcsdevice(pidevice)`, no `pidevice.close()` suelto (ver
`e545-pi-ftdi-gateway/README.md` — motivo: acumulación de callbacks al
reconectar en la misma consola).

## 5. Guardado

Los scripts de `scripts/` ya guardan solos: CSV crudo en `datos/raw/`,
metadata en `datos/metadata/`, figura en `resultados/figuras/`, con
timestamp en el nombre para no pisar corridas anteriores. Desde
2026-09-03 la metadata de escalón y rampa también guarda `DCO={...}`
leído del controlador en el momento de la corrida (no lo que diga el
código) — ver `docs/velocidad_ancho_de_banda_y_diseno_de_scans.md` §8.3.

## 6. Wave generator para raster (X+Y) — próximo hito, no probado todavía

Diseño completo y ejemplo numérico en
`docs/velocidad_ancho_de_banda_y_diseno_de_scans.md` §5. Resumen del
mecanismo, en términos de los comandos de §2:

```python
# --- Generador 1 -> eje A (X): UNA línea, se repite L veces por WGC ---
pidevice.WCL(1)
pidevice.WAV_LIN(table=1, firstpoint=1, numpoints=P, append='X',
                  speedupdown=sud_x, amplitude=ancho_x, offset=x0,
                  seglength=P)
pidevice.WTR(1, w, 0)          # dwell por píxel = w * 40 µs
pidevice.WGC(1, L)             # repite la línea L veces (una por fila)

# --- Generador 2 -> eje B (Y): la escalera de L líneas, UNA sola vez ---
pidevice.WCL(2)
pidevice.WAV_LIN(table=2, firstpoint=1, numpoints=L, append='X',
                  speedupdown=0, amplitude=alto_y, offset=y0,
                  seglength=L)
pidevice.WTR(2, P * w, 0)      # UN punto de Y por cada línea completa de X
pidevice.WGC(2, 1)

# --- Data recorder: RTR = w -> una muestra por píxel ---
pidevice.DRC(tables=[1, 2], sources=['A', 'B'], options=[2, 2])  # posición real X, Y
pidevice.RTR(w)

pidevice.WGO([1, 2], [1, 1])   # arranque simultáneo -- VERIFICAR, ver §3
pitools.waitonwavegen(pidevice, wavegens=[1, 2], timeout=...)
```

Memoria de wave usada: `P + L` puntos (no `P × L`) — la wave table no es
el límite del raster, el data recorder sí (`L × P ≤ 8192` con
`RTR = WTR_x`, ver §5.2 del doc). Antes de correr esto en serio: el
ítem 1 y el ítem 6 de "Próxima sesión" (arriba) — confirmar `WSL` y que
`WGO([1,2],[1,1])` realmente sincroniza.
