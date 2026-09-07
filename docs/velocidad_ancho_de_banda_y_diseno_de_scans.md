# Velocidad, ancho de banda y diseño de scans en el E-517

Escrito a partir del análisis de las 43 corridas de rampa y 13 de escalón
del 2026-09-01 (`scripts/analisis_velocidad_y_ancho_de_banda.py`, figuras
`resultados/figuras/analisis_0*`). Todo número acá sale de esos datos
salvo donde diga [MANUAL].

> **§8 agrega** el análisis de las 11 corridas de escalón del 2026-09-02
> (`scripts/analisis_asentamiento.py`, figuras `resultados/figuras/asent_0*`),
> centrado en tiempo de asentamiento y en el efecto de `DCO`. El resto del
> documento (§1–7) queda como estaba.

---

## 1. Los tres relojes, y cuál importa

| reloj | valor | qué es | ¿limita el scan? |
|---|---|---|---|
| DSP | 60 MHz [MANUAL] | reloj de la CPU del controlador | **no** |
| ciclo de servo | 40 µs (25 kHz) | período del lazo cerrado digital | **no** |
| lazo cerrado | **τ ≈ 12 ms (f_c ≈ 15 Hz)** | dinámica servo + platina + carga | **sí, es este** |

**"Processor = 60 MHz" es el reloj de la CPU, no una velocidad física.**
Su única lectura útil: 60 MHz ÷ 25 kHz = **2400 instrucciones por ciclo de
servo**. Es el presupuesto de cómputo que tiene el firmware para leer el
sensor, correr el PID y actualizar el DAC en cada tick. Dice por qué el
servo corre a 25 kHz y no a 1 MHz. No dice nada sobre qué tan rápido se
puede mover la platina, ni sobre la resolución de un scan.

**El ciclo de servo NO es "la velocidad del sensor" separada de la
platina.** En un controlador digital de lazo cerrado hay un solo reloj, y
cada 40 µs pasa todo esto, en serie:

```
    sensor capacitivo -> demodulador (E-509) -> ADC
        -> ley de control (P-I + filtros)
        -> DAC -> amplificador -> voltaje al piezo
```

O sea: 25 kHz es a la vez la tasa de muestreo del sensor, la tasa de
actualización del actuador, el tick del wave generator y el tick del data
recorder. No hay un "reloj del sensor" y otro "de la platina": la platina
es la planta física dentro de ese lazo.

Lo que **sí** limita todo es el ancho de banda de lazo cerrado. Medido de
dos formas independientes en los datos de hoy, y dan lo mismo:

- **Respuesta al escalón** (fig. 04a): t(10–90 %) ≈ **18 ms**, igual para
  escalones de 200 nm y de 200 µm → f_3dB ≈ 0.35/18 ms ≈ **19 Hz**.
- **Retraso en rampa** (fig. 02): el error de seguimiento vale
  e = v·τ con **τ = 12.1 ms** → f_c = 1/(2πτ) = **13 Hz**.
  Y ese τ es constante sobre **cuatro décadas de velocidad**
  (0.25 → 3150 µm/s) y cuatro de amplitud (10 nm → 200 µm).

El servo es ~1500 veces más rápido que el lazo; el DSP, ~4 millones de
veces. Ninguno de los dos es el cuello de botella. **Todo lo que puedas
hacer para mejorar escaneos pasa por esos 12 ms, o por evitarlos.**

---

## 2. Qué parámetro fija realmente la velocidad

> **`T_SERVO_US` en los scripts de adquisición no hace nada.**

No se le manda al controlador en ningún lado. En
`E517_ida_vuelta_speedupdown.py` solo aparece en `DWELL_US` (un `print`) y
en `t_ms = np.arange(...) * T_SERVO_US/1000`, es decir, **solo etiqueta el
eje temporal del CSV**. Las 20 corridas de hoy donde se barrió
T_SERVO_US de 1 a 80 µs son físicamente idénticas de a grupos; lo único
que cambió fue el nombre que le pusimos al tiempo.

Los datos lo confirman (fig. 01a): a A y WTR fijos, barrer T_SERVO_US ×60
cambia el error menos que la dispersión entre repeticiones del mismo
punto (±23 %).

**Consecuencia práctica: la columna `t_ms` de todo CSV con
`T_SERVO_US ≠ 40` está mal escalada**, por un factor 40/T_SERVO_US. En
particular `settling_time_ms_band5nm` en la metadata de los
`step_response` está mal por ×4 (los de T=10) o ×40 (los de T=1). El
análisis de `analisis_velocidad_y_ancho_de_banda.py` reconstruye el eje
correcto desde cero y **ignora la columna `t_ms`**; conviene hacer lo
mismo con cualquier reanálisis.

El knob real es **WTR**:

```
dwell por punto de wave = WTR × 40 µs
v = Δx_por_punto / (WTR × 40 µs)
```

donde `Δx_por_punto` lo fija la amplitud y la cantidad de puntos, no WTR.
Fig. 01b: a A fija, el error cae ∝ 1/WTR, como debe ser si e = v·τ.

### Nota: el target es una ESCALERA, no una rampa

Verificado en `datos/raw/*_175206.csv`: el target grabado cambia una vez
cada exactamente WTR muestras y se queda quieto en el medio. El wave
generator **no interpola** entre puntos de la tabla. Lo que la platina
recibe es un tren de micro-escalones de `Δx_por_punto` cada
`WTR × 40 µs`. Como τ (12 ms) es mucho más largo que casi cualquier
dwell razonable, el lazo integra esa escalera y el resultado se ve como
una rampa suave — pero conviene saber que ahí abajo hay escalones.

El cuanto del target es **0.1 nm** (1e-4 µm sobre 200 µm ≈ 21 bits). La
resolución digital de comando no es el límite de nada: está 17× por
debajo del piso de ruido.

---

## 3. El error de seguimiento es determinista — corregilo, no lo esperes

Fig. 02: los 43 puntos colapsan sobre `e = v·τ`. Fig. 03: si se corrige
el retraso en post (desplazar el target τ en el tiempo), el RMS cae

| corrida | v | RMS crudo | RMS con lag corregido |
|---|---|---|---|
| A=10 µm, WTR=20 | 158 µm/s | 1587 nm | **94 nm** (×17) |
| A=1 µm, WTR=20 | 15.8 µm/s | 169 nm | **105 nm** (×1.6) |
| A=0.1 µm, WTR=20 | 1.63 µm/s | 19 nm | **4.4 nm** (×4.3) |

Esto reencuadra el problema entero. **Bajar la velocidad para reducir el
error de seguimiento es tirar tiempo a la basura**: el error que estabas
peleando era un desplazamiento rígido, conocido y constante. Se saca de
dos formas equivalentes:

1. **En el comando**: cargar la wave table adelantada, es decir mandar
   x(t + τ). En un tramo de velocidad constante eso es simplemente
   sumarle `v·τ` al offset de ida y restárselo a la vuelta.
2. **En el post-procesamiento**: reasignar cada muestra del recorder a la
   posición `x_real` medida, no a la comandada. Es lo mejor si vas a
   hacer imagen: el data recorder te da la posición real píxel a píxel,
   así que no necesitás que la platina esté donde le pediste — necesitás
   **saber dónde estuvo**, y eso ya lo estás grabando.

Lo que **no** se corrige con un desplazamiento rígido es el **sobrepico
en el retorno**: 94–159 nm en las corridas de hoy (fig. 03, arriba). Ese
es el residuo del integrador desarmándose cuando la velocidad cambia de
signo. No escala simplemente con v porque `speedupdown=40` ya hace que la
desaceleración dure 32 ms > τ. **Ese sobrepico tiene que quedar fuera de
la zona de interés** — es el motivo físico del over-scan (§5).

---

## 4. El piso de ruido: 1.7 nm, y es de 50 Hz

Fig. 04b/c, midiendo la posición con la platina quieta y asentada:

- **σ = 1.7 nm RMS** con el sensor a ancho de banda completo.
- Una línea espectral **aislada de 2.4 nm de amplitud en 50.0 Hz**: la
  red eléctrica. Es el término dominante.
- Promediar **no ayuda hasta los ~20 ms** (fig. 04c): σ se queda clavada
  en 1.7 nm entre 0.04 ms y 4 ms de promediado, y recién baja cuando la
  ventana cubre un período completo de 50 Hz (0.4 nm a 20 ms, 0.24 nm a
  40 ms). Es ruido **correlacionado**, no blanco: subir RTR u
  oversamplear por píxel no compra nada.

Dos cosas importantes salen de acá:

**(a) Confirmación independiente de que el ciclo de servo es 40 µs.** La
línea cae en 50.0 Hz si y solo si dt = 40 µs. Con dt = 10 µs (el valor
que quedó escrito en varios scripts) caería en 200 Hz, que no
corresponde a ninguna fuente física del laboratorio. Esto zanja la
contradicción entre el README (40 µs) y los scripts (10.0 / 1.0):
**el README tiene razón**. Igual conviene volver a correr
`E517_diagnostico.py` y pegar el `qSPA(1, 0x0E000200)` real en el
cuaderno.

**(b) Para un proyecto de estabilización sub-nanométrica, esos 2.4 nm de
50 Hz son el enemigo número uno.** Está por encima del ancho de banda del
lazo (15 Hz), así que el servo no lo puede rechazar; y no se promedia.
Antes de tocar cualquier otra cosa, vale la pena separar si es
**pickup eléctrico en el sensor** o **movimiento mecánico real**:
grabar con `DRC` la opción 7 (voltaje de control) junto con la posición,
y repetir con `SVO` apagado. Si el 50 Hz sigue en la posición con el
servo abierto, es el sensor/cableado (masa, ruteo del cable del sensor,
lazo de masa por el USB al Mac). Si desaparece, el lazo lo está
inyectando.

---

## 5. Cómo repartir los 8192 puntos

### 5.1 Son dos presupuestos distintos, y uno de los dos no es un problema

| recurso | límite | qué lo consume |
|---|---|---|
| wave table | 8192 puntos/tabla, 3 tablas | la **forma** de la trayectoria |
| data recorder | 8192 muestras/tabla, 3 tablas | el **tiempo** grabado |

La confusión típica es creer que un raster de L líneas × P píxeles
necesita L·P puntos de wave table. **No**: `WGC` repite la tabla. Un
frame entero se arma con

- **Generador X (tabla 1)**: `P` puntos = **una sola línea**.
  `WTR_x = w`. `WGC_x = L` ciclos.
- **Generador Y (tabla 2)**: `L` puntos = la escalera (o una rampa
  continua). `WTR_y = P·w` → un punto de Y por cada línea de X,
  sincronizado por construcción. `WGC_y = 1`.
- Arrancar los dos juntos: `WGO([1,2],[1,1])`.

Memoria de wave usada: `P + L` puntos, no `P·L`. Un frame de 128×64 gasta
192 de los 8192. **La wave table no es el límite.** El límite real es el
recorder.

### 5.2 La regla que hace que todo encaje: RTR = WTR

```
dt_recorder = RTR × 40 µs        dwell_píxel = WTR × 40 µs
```

Con **RTR = WTR** el recorder guarda **exactamente una muestra por punto
de wave**, o sea una muestra por píxel. Entonces:

```
frame completo grabado  ⟺  L × P ≤ 8192
```

Ahí está el "8192 puntos del frame": 128×64, 90×91, 64×128. Fig. 05a.

Hoy estás corriendo con **RTR=1 y WTR=20**: 20 muestras por punto de
wave. Eso quema el buffer de 8192 en 409 puntos de wave — por eso
`n_leer = N_TOTAL × WTR` y por eso solo entra una línea. Para
caracterizar la dinámica dentro de un punto (que es lo que estabas
haciendo) está perfecto. Para hacer imagen es exactamente al revés de lo
que querés.

Si el frame necesita más de 8192 píxeles: poner `RTR = k·w` graba
1 de cada k píxeles — un mapa completo pero diezmado, ideal como control
de calidad de la trayectoria mientras la imagen real la da el detector.

Y las tres tablas del recorder conviene reasignarlas: para imagen,
**(X real, Y real, error X)** sirve más que target/current/error de un
solo eje — necesitás los dos ejes para saber dónde cayó cada píxel.

### 5.3 Dónde poner los píxeles dentro de la línea

Tres restricciones físicas, en orden de importancia:

**(a) Los puntos de wave están equiespaciados en TIEMPO, no en espacio.**
`WTR` es uno por generador, no por punto. Así que el único modo de variar
el paso espacial dentro de una línea es variar la velocidad, que es lo que
hace `speedupdown` — y eso hace el paso de píxel **no uniforme** en los
extremos. Conclusión: **la zona de interés tiene que caer íntegramente en
el tramo de velocidad constante**, donde el paso vale exactamente
`Δx = v·WTR·40 µs` y es rigurosamente uniforme.

**(b) Over-scan, no "esperar a que asiente".** Un `MOV` con espera cuesta
**~150 ms** para llegar a ±2 nm (fig. 04a: sobrepico de 2–3 %, más una
cola lenta de ~100 ms). Si el retorno de cada línea cuesta 150 ms, un
frame de 64 líneas tira 10 s a la basura, más la latencia FTDI de cada
comando por línea. La alternativa: **nunca parar**. Extender la rampa de
X más allá de la zona de interés en al menos

```
over-scan ≳ v·τ + sobrepico ≈ v × 12 ms + 150 nm
```

y darle al giro al menos `3τ ≈ 36 ms`. Los puntos de over-scan gastan
wave table (que sobra) y no imagen.

**(c) Escanear bidireccional.** Esta es la respuesta directa a "cómo
repartir los 8192 de la forma más eficiente": hoy, con triángulo, **la
mitad de los puntos son la vuelta y se descartan**. Si escaneás en las
dos direcciones, esa mitad se convierte en imagen y **el presupuesto
efectivo se duplica**. Lo único que lo hacía inviable era justamente el
retraso: las líneas de ida y de vuelta salen corridas en sentidos
opuestos, `2·v·τ` una respecto de la otra. **Ahora τ está medido**
(12.1 ms, constante), así que la corrección es un desplazamiento fijo y
conocido — o directamente sale gratis si asignás cada muestra a la
posición real grabada en vez de a la comandada (§3.2).

En Y, la misma idea: en vez de escalera + `MOV`, una **rampa continua
lenta** (scan tipo diente de sierra con deriva). No hay asentamiento en Y
en ningún momento; la imagen queda con un cizallamiento constante de
`v_y·τ` que se corrige igual que el lag en X.

### 5.4 Ejemplo numérico cerrado

ROI de 10 × 10 µm, 128 × 64 = 8192 píxeles → Δx = 78 nm, Δy = 156 nm.

| | |
|---|---|
| dwell elegido | 1 ms → **w = WTR_x = 25** |
| velocidad en la línea | 78 nm / 1 ms = **78 µm/s** |
| lag (constante, corregible) | 78 µm/s × 12.1 ms = **0.94 µm = 12 px** |
| over-scan por lado | 0.94 µm + 0.15 µm ≈ **1.1 µm** (≈14 px) |
| puntos wave X | 128 + 2×14 ≈ **156** (de 8192) |
| tiempo de línea | 156 × 1 ms = **156 ms** |
| `WTR_y` | 156 × 25 = **3900**; tabla Y de 64 puntos |
| tiempo de frame | 64 × 156 ms = **10 s** |
| `RTR` | **25** → dt_rec = 1 ms → 8192 muestras = 8.2 s |
| ruido de posición por píxel | **1.7 nm** = 2 % del píxel |

El recorder cubre 8.2 s de los 10 s del frame: alcanza justo para los
8192 píxeles útiles si no grabás el over-scan, o poné `RTR = 26` y grabás
el frame entero con margen. Bidireccional, el mismo frame sale en ~5 s.

Chequeos antes de correrlo: `WTR_y = 3900` está muy por encima de lo que
usaste hasta ahora — el valor más alto probado en este equipo es 1000
(`E517_repetibilidad`). **Verificar el máximo de WTR** con `qSPA` o
probando, antes de diseñar alrededor de este esquema. Si WTR tiene techo,
la salida es alargar la tabla de Y (más puntos, cada uno más corto).

---

## 6. Prioridades para mejorar, en orden de retorno

> **Actualizado en §8**: la medición del 2026-09-02 encontró que apagar
> `DCO` (Drift Compensation) corta el asentamiento por escalón a un
> tercio, gratis, sin tocar hardware. Es al menos tan barato como
> corregir el lag (ítem 2) y probablemente más barato que reordenar el
> patrón de scan (ítem 3) — va primero en la lista.

0. **Apagar DCO durante el scan** (`DCO(['A','B'],[False,False])`).
   Corta a un tercio el tiempo hasta ±5 nm después de cada escalón
   (~140 ms → ~50 ms, medido). Ver §8. Antes de adoptarlo sin más:
   confirmar que no haya deriva térmica/mecánica apreciable en la
   escala de tiempo de un frame completo (DCO existe para compensar
   eso), con una corrida larga (minutos) de DCO apagado.
1. **Matar el 50 Hz.** 2.4 nm de amplitud, dominante, fuera del ancho de
   banda del servo, no se promedia. Diagnóstico en §4b. Es el único
   camino a sub-nm sin dwells de 20 ms.
2. **Corregir el lag** (comando adelantado, o reasignar por posición
   real). Factor 2–17 en error de seguimiento, gratis, sin tocar el
   hardware.
3. **No parar entre líneas**: dos generadores + `WGC` + rampa continua en
   Y. Elimina ~150 ms de asentamiento (con DCO=True; ~50 ms con DCO=False,
   ver §8) y una latencia FTDI por línea.
4. **Escanear bidireccional**: duplica el presupuesto de 8192.
5. **Recién después, tocar la sintonía del servo.** τ = 12 ms
   (f_c ≈ 15 Hz) es lento; si la resonancia mecánica de la platina con
   carga está en las centenas de Hz, hay margen para subir P/I. Es la
   única vía para bajar τ, y es la que más riesgo tiene: hacerlo con
   escalones chicos, mirando el sobrepico, y anotando los valores
   originales antes.
6. **Resolución digital de comando: no tocar.** 0.1 nm de cuanto, 17×
   por debajo del ruido. No es el límite de nada.

---

## 7. Resultado nulo, para el cuaderno

El barrido de `T_SERVO_US` del 2026-09-01 (20 corridas, 1–80 µs) es un
**resultado nulo por construcción**: el parámetro nunca llegó al
controlador. Sirve igual, como medida de repetibilidad: repitiendo el
mismo punto físico, el error mediano en velocidad constante varía **±23 %**.
Ese es el piso de significancia para cualquier comparación futura entre
configuraciones — diferencias menores al 23 % no son diferencias.

---

## 8. Addendum (2026-09-03) — asentamiento, corridas del 2026-09-02

Las 11 corridas nuevas son todas de escalón, con `T_SERVO_US=40` (como
correspondía) y `WTR=1` fijo, variando `N_TOTAL` (450 a 8192). Tres
quedaron con `DCO` anotado a mano en el nombre del PDF de figura — dos
sin él y una tercera con DCO apagado —, lo que de paso dejó ver que
también en algunas corridas del 01/09 se había tocado `DCO` desde la
consola sin que quedara registrado en la metadata. Todo esto sale de
`scripts/analisis_asentamiento.py` (no toca el hardware), figuras
`resultados/figuras/asent_0*`. **No reemplaza** el análisis de §1–7 —lo
complementa, con el foco puesto en asentamiento en vez de en velocidad
en régimen—.

### 8.1 ¿Variar N_TOTAL con WTR=1 fijo mejora algo? No — el knob es RTR

`T_SERVO_US=40` sí fue una mejora real: por fin la columna `t_ms` del
CSV queda bien escalada (§2). Pero variar `N_TOTAL` con `WTR=1` y
`RTR=1` fijos **no cambia la resolución temporal ni agrega información
dinámica nueva** — con esos dos relojes fijos, `N_TOTAL` solo recorta o
estira la ventana de observación:

```
ventana post-escalón ≈ N_TOTAL × 40 µs   (con RTR=1)
```

Fig. asent_08a: de las 11 corridas nuevas, **8 quedaron con ventanas de
16–80 ms** — más cortas que el propio asentamiento, que recién cruza
±5 nm entre 120 y 150 ms (con DCO=True, ver 8.2). Esas 8 no ven nada que
no se supiera ya: repiten la subida inicial (t₁₀₋₉₀ ≈ 18 ms, igual en
las 24 corridas de ambos días, fig. asent_08b) y cortan justo antes de
la cola lenta. Las **3 corridas con N=8192** (191721, 191844, 192004) sí
llegan a la ventana completa (~326 ms) y son las únicas nuevas
directamente comparables con las del día 1.

El knob real para "ver más tiempo sin perder resolución en la subida" es
`RTR`, no `N_TOTAL` ni `WTR`:

```
ventana = 8192 × RTR × 40 µs        resolución = RTR × 40 µs
```

Con `RTR=1` (fijo en las 24 corridas de los dos días) la ventana está
topeada en ~328 ms pase lo que pase con `N_TOTAL`. Con `RTR=10`, por
ejemplo, la ventana sube a 3.3 s sin perder nada donde importa: la
subida (18 ms) sigue teniendo ~45 muestras. Fig. asent_08b.

**Lo que sí valió la pena de esta tanda**: las 3 corridas de ventana
completa reproducen extremadamente bien a las del día 1 una vez que se
las compara con el reloj de 40 µs correcto en ambas — incluida la forma
completa de la cola lenta, no solo la subida (fig. asent_06). Es una
confirmación de reproducibilidad entre dos días y dos configuraciones de
`WTR` distintas (1 vs. 20), que es un resultado útil en sí mismo aunque
no hayan sido su objetivo declarado.

### 8.2 DCO: el efecto más grande medido hasta ahora sobre el asentamiento

Con un **par controlado** (mismo día 02/09, mismo escalón de 2 µm, misma
ventana de 82 ms, únicas dos variables distintas WTR=1 y `DCO`):

| | DCO = True (192038) | DCO = False (192114) |
|---|---|---|
| error a t=60 ms | **+54.6 nm** | **+2.2 nm** |
| cruza banda ±5 nm | no dentro de la ventana (recién ~138 ms en la corrida hermana de 326 ms, 191721) | **~52 ms** |
| pico de la excursión lenta ("bump") | **+55 nm** en t≈58 ms | **+4 nm** (~ruido) |

Es decir: al final de la misma ventana de 82 ms, con DCO apagado el
error ya está en el piso de ruido (2–4 nm); con DCO prendido sigue en
~50 nm, **un orden de magnitud más alto**, y tarda otros ~80 ms más en
bajar de la banda de ±5 nm. Asentamiento completo: **~138 ms con
DCO=True** (única medición con ventana suficiente para confirmarlo)
contra **≲52 ms con DCO=False** — al menos **~2.7× más rápido**, y
probablemente más, porque a los 82 ms ya no queda margen visible de
mejora en la corrida con DCO apagado (fig. asent_07a).

Este no es un efecto aislado de una corrida particular:

- **Fig. asent_07b** superpone TODAS las corridas de escalón de 2000 nm
  de ambos días y de cinco `WTR` distintos. Las de DCO=True (rojo) —
  incluidas las tres del día 1 sin DCO confirmado en metadata, que
  coinciden con esa población — forman una sola familia con el mismo
  "bump" de ~50 nm; la única de DCO=False (verde) es la única que no lo
  tiene.
- **Fig. asent_07c** grafica el pico del bump contra el tamaño del
  escalón, de 20 nm a 200 µm: con DCO=True el bump vale **30–105 nm**,
  casi constante en valor absoluto (no escala con el escalón — es
  consistente con un término aditivo del controlador, no con slew-rate
  ni con el propio lag de §3). Con DCO=False, **1–5 nm**, indistinguible
  del piso de ruido de 1.7 nm.

**Qué es DCO, en los términos del manual PI**: *Drift Compensation* — una
corrección lenta que el controlador aplica para contrarrestar deriva
térmica/mecánica de largo plazo del sensor y del piezo. Es razonable que
un lazo de compensación de deriva, ajustado para constantes de tiempo de
segundos o minutos, reaccione de forma no óptima ante un escalón rápido
(constante de tiempo del lazo principal ~12 ms) y le agregue esta
excursión de decenas de nm que tarda ~50–80 ms en reabsorberse. Esto es
una interpretación razonable a partir del nombre y el comportamiento
medido, **no** una confirmación leída del manual — antes de generalizar
conviene revisar la sección de DCO en el manual PZ214E.

**Antes de apagar DCO en todas las mediciones**: DCO existe para algo.
Apagarlo mejora el asentamiento rápido (~100 ms), pero puede dejar
crecer una deriva térmica/mecánica lenta (segundos a minutos) que sí
importa para un experimento de estabilización sub-nanométrica de
duración larga. Antes de adoptarlo como default, correr una medición de
minutos con DCO apagado y ver cuánto deriva la posición — si el
experimento real dura menos que esa deriva, no hay costo; si dura más,
puede convenir un esquema híbrido (DCO apagado durante cada línea/frame,
prendido en las pausas, o una corrección de deriva propia más lenta).

### 8.3 Un problema de trazabilidad para arreglar

El estado de `DCO` no quedó en ningún `.txt` de `datos/metadata/` — solo
en el nombre de algunos PDFs de `resultados/figuras/`, agregado a mano
y después del hecho. De las 24 corridas de escalón entre los dos días,
**solo 6 tienen el DCO que usaron confirmado** (3 por día). El resto
(incluidas 8 de las 11 corridas nuevas) es DCO **desconocido**, no
"asumido True" — el propio hallazgo de 8.2 hace que esa suposición ya no
sea segura, porque quedó claro que se tocó `DCO` desde la consola sin
editar el script en más de una sesión.

Recomendación concreta para `scripts/E517_step_response.py` (y cualquier
script que dispare un `pidevice.DCO(...)`): agregar una línea al bloque
de guardado de metadata, algo como

```python
f.write(f"DCO={dict(pidevice.qDCO())}\n")
```

leyendo el estado real del controlador en el momento de la corrida, en
vez de confiar en que coincida con lo que dice el código o con lo que se
recuerde después. Es una línea de costo cero que evita tener que
reconstruir esto por segunda vez.

---

## 9. Addendum (2026-09-07) — barrido RTR × DCO, y dos hechos nuevos del equipo

20 corridas de escalón de 2 µm con `scripts/E517_barrido.py`, barriendo
`RTR` ∈ {1, 2, 5, 10, 25} × `DCO` ∈ {ON, OFF}, 2 repeticiones cada una.
Análisis y figura: `scripts/analisis_barrido_rtr_dco.py`,
`resultados/figuras/barrido_01_rtr_dco.pdf`. Resuelve los ítems 1 y 5 de
"Próxima sesión" del protocolo.

### 9.1 `WSL` no existe en este controlador

**Ítem 1, resuelto — y no como esperábamos.** El E-517 serial 0111176619,
firmware **V01.243**, responde `Unknown command` a `WSL` y a `WSL?`.

O sea que **el mapeo generador↔tabla es fijo y no se puede reasignar**.
Los scripts anteriores no funcionaban "por casualidad": funcionaban
porque no hay otra opción. Consecuencia para el raster X+Y (§5): no se
puede elegir qué tabla reproduce cada generador, así que hay que
**averiguar cuál es el mapeo fijo por experimento** — cargar una tabla,
disparar un generador, y ver qué eje se mueve — antes de diseñar el
raster alrededor de una asignación supuesta.

### 9.2 El data recorder no se detiene con la wave — y eso rompía los archivos

Creíamos (§8.1) que la ventana observada era `N_TOTAL × 40 µs`. Es más
sutil, y la diferencia arruina archivos enteros:

- El recorder arranca con `WGO` y **sigue grabando después de que la
  trayectoria terminó**. Graba sus 8192 muestras y punto.
- Pero cuando el generador se detiene, **el canal `target` pasa a valer
  0**, mientras el canal `current` sigue midiendo la posición real.

Entonces, si la trayectoria dura menos que la ventana del recorder, el
archivo termina con `target = 0` y `current = 101 µm`. Y ahí el análisis
—cualquier análisis que busque el escalón como "el salto más grande del
target"— encuentra un escalón de **−101 µm** al final del archivo en vez
del de +2 µm del principio. Todas las métricas salen sin sentido.

Nos pasó en la primera corrida de validación de hoy, y **le pasó también
a 24 corridas** que quedaron con este defecto en `datos/raw/`
(identificables porque su columna `target_um` contiene ceros exactos).

**La regla que lo evita**, y que ahora aplica el helper `escalon()`:

```
        WTR = RTR      y      n_pre + n_post = 8192
    →   ventana = 8192 × RTR × 40 µs      resolución = RTR × 40 µs
```

La trayectoria dura exactamente lo que dura la ventana. Como el tramo
posterior al escalón es **plano**, alargarlo es gratis (un solo segmento
`WAV_LIN`), y lo que se graba durante todo ese tiempo es justamente lo
que queremos ver: la platina asentando sola. Con esto **`RTR` queda como
EL knob del escalón** y mueve ventana y resolución juntas:

| RTR | ventana | resolución | muestras en la subida (18 ms) |
|---|---|---|---|
| 1 | 328 ms | 40 µs | 450 |
| 5 | 1.6 s | 200 µs | 90 |
| 25 | 8.2 s | 1 ms | 18 |

### 9.3 Asentamiento con y sin DCO — ahora medido, no inferido

**Ítem 5, resuelto.** Las 20 corridas, en ventanas comparables (medianas;
2 corridas descartadas por perturbación mecánica evidente — ruido de
fondo 6–7 nm rms contra un piso de 1.1 nm):

| | DCO = ON (n=8) | DCO = OFF (n=10) |
|---|---|---|
| t(10–90 %) | **18.7 ms** [18.4, 19.0] | **19.6 ms** [19.5, 20.0] |
| pico del bump lento | **58.2 nm** [53.7, 63.1] | **5.5 nm** [−4.7, 6.7] |
| instante del bump | 56 ms | 79 ms (= ruido) |
| t_s (banda ±5 nm) | **146 ms** [140, 163] | **84 ms** [51, 137] |
| error final | −0.11 nm | −0.27 nm |

Y el control del ítem 5 funciona: **`t_s` no depende de `RTR`** (fig. b) —
146 ms con DCO ON en las cinco configuraciones de RTR, 84 ms con DCO OFF.
`RTR` cambia lo que mirás, no lo que la platina hace, que es exactamente
lo que tenía que pasar.

**Correcciones a §8.2**, que estaba basada en un solo par de corridas:

- El bump se confirma con creces: **10.6× más grande con DCO** (58 contra
  5.5 nm), y su valor (58 nm a 56 ms) reproduce casi exactamente el
  medido el 02/09 (55 nm a 58 ms). Buena reproducibilidad a 5 días.
- Pero **la ganancia en asentamiento es 1.7×, no 2.7×**. El "≲52 ms" de
  §8.2 era una cota inferior sacada de una ventana demasiado corta: la
  mediana real de DCO=OFF es **84 ms**, con dispersión grande
  (51–137 ms). Sigue siendo una mejora clara, pero de la mitad del
  tamaño que la que habíamos anunciado.
- **El error final es el mismo con y sin DCO** (−0.1 contra −0.3 nm).
  Apagar DCO no deja un offset estático.

### 9.4 Deriva: sin efecto medible en 8 segundos

> **CAVEAT (anotado por Fran el mismo día): la platina NO estaba en su
> posición de montaje definitiva cuando se tomaron estos datos.** Todo
> número de DERIVA de esta sección hay que volver a medirlo con el montaje
> final — la deriva térmica/mecánica depende de cómo está apoyada y
> vinculada la platina, que es justamente lo que cambió. Las medidas de
> asentamiento, bump y ancho de banda (§9.3, §9.6) son mucho menos
> sensibles al montaje, así que se toman como válidas mientras no haya
> evidencia en contra.

Las corridas con `RTR = 25` graban **8.2 s** de posición después del
escalón, así que dan gratis una primera respuesta al ítem 2 del protocolo
(el costo de apagar DCO):

| | deriva ajustada | posición a 8 s |
|---|---|---|
| DCO = ON | +0.7 y 0.0 nm/min | 1.4 y 1.6 nm |
| DCO = OFF | −2.6 y −1.5 nm/min | 1.4 y 2.8 nm |

Fig. (d): las dos condiciones se quedan dentro de ±1.5 nm durante los
8 segundos, sin tendencia visible. **En la escala de un frame (≈10 s),
apagar DCO no cuesta nada medible.** Los −2 nm/min de DCO=OFF están al
borde de la significancia con esta ventana; para saber si son reales hace
falta la corrida de minutos del ítem 2, que sigue pendiente.

**Recomendación actualizada (reemplaza al ítem 0 de §6):** apagar DCO
durante los scans sigue siendo lo correcto — 10× menos excursión y 1.7×
más rápido en asentar, sin costo detectable en 8 s. Pero el argumento es
más módico que el de §8.2, y la verificación de deriva en minutos sigue
haciendo falta antes de dejarlo apagado en una medición larga.

### 9.5 Piso de ruido de hoy

`ruido_final_nm_rms` (desviación estándar de la posición ya asentada) dio
**1.1 nm** de mediana sobre las 18 corridas limpias, contra los 1.7 nm
de §4. Mejor día, o el sensor estaba a otro ancho de banda. Y **2 de 20
corridas salieron perturbadas** (6–7 nm rms, con excursiones de decenas
de nm a t > 1 s): golpes en la mesa o transitorios. Con 10 % de corridas
arruinadas por perturbaciones externas, conviene medir de a repeticiones
y quedarse con la mediana, no con una corrida sola.

### 9.6 Zonas de una rampa: dónde el paso entre píxeles es uniforme

6 corridas de rampa del 2026-09-07 (`scripts/analisis_zonas_rampa.py`,
fig. `barrido_02_zonas_rampa.pdf`). Formaliza lo que §5.3(a) decía en
palabras: **la zona de interés tiene que caer en el tramo de velocidad
constante** — pero además cuantifica cuánto tramo queda realmente.

**Cómo se identifica cada zona.** Sobre la trayectoria **comandada**, no
sobre la medida: el comando es exacto y sin ruido (es la tabla que
cargamos), mientras que derivar la posición medida amplifica el ruido por
1/dt — 1.1 nm rms a 40 µs de paso se convierten en ±28 µm/s de basura
sobre una velocidad de 20 µm/s. Con la posición medida no se puede
segmentar; con la comandada, sí, y es exacto.

Dos cuidados: (i) el comando es una **escalera**, así que hay que suavizar
sobre al menos un escalón (`WTR/RTR` muestras) antes de derivar; (ii) el
suavizado tiene que ser con padding **por borde**, no por ceros —
`np.convolve(..., mode="same")` rellena con 0 fuera del array y sobre una
posición de 100 µm eso inventa un salto de 100 µm en el primer punto (nos
dio velocidades de 123750 µm/s hasta que lo encontramos).

Con eso: `|v| ≥ 0.98·máx|v|` marca velocidad constante, y el signo separa
ida de vuelta.

**El segundo recorte, que es el que se olvida.** Que el COMANDO vaya a
velocidad constante no alcanza. Cuando la aceleración termina, la platina
todavía se está poniendo al día: el error de seguimiento tarda **~3τ ≈
36 ms** en llegar a su valor de régimen `e = v·τ`, y hasta que llegue el
espaciado real entre píxeles no es uniforme. La fig. (c) lo muestra
directamente: el error entra en el tramo de velocidad constante todavía
creciendo, y recién después se estaciona en −191 nm = −v·τ.

**Zona usable = velocidad constante − los primeros 3τ.**

| `speedupdown` | v [µm/s] | acel [ms] | v cte [ms] | usable [ms] | usable [µm] | Δx/punto [nm] | % del ciclo |
|---|---|---|---|---|---|---|---|
| 0 | 12.6 | 0.2 | 159 | **123** | 1.55 | 10.1 | **37 %** |
| 40 | 15.8 | 113 | 98 | **60** | 0.96 | 12.6 | **18 %** |
| 80 | 21.4 | 232 | 31 | **0** | 0 | 17.1 | **0 %** |

*(A = 1 µm, N = 400 puntos, WTR = 20, 3τ = 36.3 ms en los tres casos.)*

**El resultado incómodo: `speedupdown = 80` no deja NADA utilizable.** Su
meseta de velocidad constante dura 31 ms, menos que los 36 ms que la
platina necesita para estacionar el error. La trayectoria entera es
transitorio. Y `speedupdown = 40` —el valor que
`E517_ida_vuelta_speedupdown.py` viene usando por default
(`N_IDA // 5`)— deja solo el 18 % del ciclo.

Hay entonces un **compromiso explícito**: `speedupdown` suaviza la esquina
del giro (por eso se lo agregó) pero se come el tramo recto. Con estos
números, para escanear conviene `speedupdown` **chico** y comprar el
suavizado del giro alargando la tabla (más puntos totales), no subiendo
`speedupdown` — porque lo que hace falta no es que el giro sea suave, sino
que el giro y sus 3τ posteriores caigan **fuera** de la zona de interés.

**Regla de diseño, cerrada:**

```
    t_recta ≥ 3τ + t_zona_de_interés          (τ = 12.1 ms)
    over-scan por lado ≥ v·3τ  (+ el sobrepico del giro, ~150 nm)
```

Con τ = 12 ms fijo, esto dice que **todo scan con tramos rectos de menos
de ~36 ms es puro transitorio**, sin importar la amplitud ni la
velocidad. Es el mismo número que aparece en §5.3(b) como "darle al giro
al menos 3τ", visto desde el otro lado.

---

## 10. Addendum (2026-09-07, tarde) — dos tandas más: amplitud y diseño de scan

40 corridas nuevas con `scripts/E517_barrido.py`. Análisis y figuras:
`scripts/analisis_amplitud_y_scan.py`, `barrido_03_amplitud.pdf` y
`barrido_04_diseno_scan.pdf`.

> **Mismo caveat que §9.4: la platina no estaba en su posición de montaje
> definitiva.** Los tiempos de subida, el escalado del bump y la
> uniformidad del paso espacial son poco sensibles a eso. El **offset
> estático** de §10.2 sí puede cambiar con el montaje — el mecanismo es
> real, la magnitud hay que volver a medirla.

### 10.1 Tanda A: el lazo es lineal en cuatro décadas, y `t₅₀` es el estadístico correcto

20 corridas de escalón, de **20 nm a 100 µm**, DCO on/off, `RTR = WTR = 5`.

| escalón | t₅₀ [ms] | t(10–90) [ms] | v pico [µm/s] |
|---|---|---|---|
| 20 nm | 11.4 | 13.9 | 2.4 |
| 200 nm | 11.0 | 15.3 | 14.9 |
| 2 µm | 11.0 | 19.1 | 148.9 |
| 20 µm | 10.1 | 16.0 | 1667 |
| 100 µm | 10.4 | 11.7 | 9497 |

*(medianas, DCO=ON; con DCO=OFF los t₅₀ dan igual salvo el de 20 nm, que
el ruido arruina.)*

**`t₅₀` = 10.1–11.4 ms, constante sobre cuatro décadas**, mientras que
`t(10–90)` varía entre 11.7 y 19.1 ms en las mismas corridas. La
conclusión de §1 (el lazo es lineal, el ancho de banda no depende de la
amplitud) **se confirma** — pero el estadístico que la muestra bien es
`t₅₀`, no `t(10–90)`, porque los cruces del 10 % y del 90 % son los dos
puntos más frágiles de la curva: el del 10 % lo arruina el ruido cuando
el escalón es chico (a 20 nm, el piso de 1.2 nm es el 6 % del escalón) y
el del 90 % depende de la forma de la cola, que sí cambia con la
amplitud. `t₅₀` está lejos de las dos patologías. Se agregó como métrica.

**No hay saturación de slew hasta 100 µm** (fig. d): la velocidad pico
escala proporcional a la amplitud en las cuatro décadas (2.4 → 9497 µm/s
para 20 nm → 100 µm). El controlador no está limitando corriente en
ningún punto del rango que usamos.

**Corrección a §8.2: el bump SÍ escala con el escalón.** Aquella sección
decía "casi constante en valor absoluto (30–105 nm), no escala con el
escalón — consistente con un término aditivo del controlador". Con cinco
amplitudes y dos repeticiones:

| escalón | bump DCO=ON | bump DCO=OFF |
|---|---|---|
| 20 nm | 6.2 nm | 11.4 nm |
| 200 nm | 34.0 nm | 12.8 nm |
| 2 µm | 54.6 nm | 16.6 nm |
| 20 µm | 102.2 nm | 31.6 nm |
| 100 µm | 137.5 nm | 89.5 nm |

Crece un factor **22** mientras el escalón crece un factor 5000: es
**sublineal**, aproximadamente ∝ escalón^0.35 (fig. b). No es aditivo
puro (crece) ni proporcional (crece mucho menos que el escalón). La
lectura de §8.2 estaba sesgada por tener pocas amplitudes y por una
definición de "bump" distinta de la actual (ahora se lo busca recién
después del primer cruce por el destino, para no confundirlo con la cola
de la subida).

### 10.2 El verdadero costo de apagar DCO: un offset estático que deriva

En esta tanda, con DCO apagado, **los escalones de 20 nm, 200 nm y 2 µm
no asentaron nunca** dentro de la banda de ±5 nm en 1.6 s — mientras que
con DCO prendido asentaron en 81, 121 y 138 ms. Es lo **opuesto** a lo
que dio la tanda de §9.3, tomada 18 minutos antes, donde el mismo escalón
de 2 µm con DCO=OFF asentaba en 51–137 ms.

No es un error de configuración: la metadata releída del controlador
confirma `qDCO = False` en las dos tandas. Comparando el mismo escalón de
2 µm con DCO=OFF en las dos:

| | error medio 200–1000 ms | σ | \|máx\| |
|---|---|---|---|
| tanda §9.3 (17:03) | **−0.4 nm** | 1.2 nm | 4.7 nm |
| tanda §10.1 (17:21) | **+10.0 nm** | 1.2 nm | 14.7 nm |

**El ruido es idéntico; lo que cambió es un offset estático de 10 nm.**
Y eso es exactamente lo que DCO anula: con DCO prendido el error estático
queda en ~0 nm en todas las amplitudes (fig. c).

Esto precisa el compromiso, que hasta ahora estaba planteado como una
especulación ("DCO existe para algo"):

| | DCO = ON | DCO = OFF |
|---|---|---|
| transitorio después de un escalón | bump de 6–137 nm, ~100 ms | 5–90 nm |
| error estático ya asentado | **~0 nm** | **hasta 10 nm, y deriva** |
| asentamiento a ±5 nm | 81–140 ms | no asienta si el offset > 5 nm |

**Consecuencia para el diseño:** apagar DCO durante el scan sigue siendo
correcto —el bump es un transitorio por línea, y ahí manda—, pero el
offset estático deriva en decenas de minutos y hay que manejarlo:
re-prender DCO en las pausas entre frames para volver a poner el cero, o
tener una referencia de posición absoluta. Es el "esquema híbrido" que
§8.2 planteaba como hipótesis; ahora hay evidencia de que hace falta.

También corrige la recomendación de §9.3: la ganancia de 1.7× en
asentamiento con DCO apagado **solo vale si el offset estático es chico
en ese momento**. Cuando el offset es de 10 nm, con DCO apagado no se
asienta a ±5 nm en absoluto.

### 10.3 Tanda B: cuánto de un scan sirve, y cuán uniforme es

20 corridas de rampa: `speedupdown` ∈ {0, 20, 40, 80} × `WTR` ∈ {10, 40},
más dos largos de tabla extra. Aplica la segmentación de §9.6.

| N tabla | WTR | sud | v [µm/s] | acel [ms] | v cte [ms] | usable [ms] | % ciclo | Δx/punto [nm] | residuo [nm rms] |
|---|---|---|---|---|---|---|---|---|---|
| 400 | 10 | 0 | 25.1 | 2.6 | 78.9 | 42.5 | 13 % | 10.1 | 1.45 |
| 400 | 10 | 20 | 28.0 | 25.1 | 65.6 | 29.3 | 9 % | 11.2 | 1.88 |
| 400 | 10 | 40 | 31.5 | 50.0 | 51.8 | 15.4 | 5 % | 12.6 | 0.87 |
| 400 | 10 | 80 | 42.5 | 98.3 | 24.8 | **0** | **0 %** | 17.1 | — |
| 400 | 40 | 0 | 6.3 | 10.6 | 315.5 | 279.0 | 21 % | 10.1 | 1.43 |
| 400 | 40 | 20 | 7.0 | 100.5 | 262.6 | 226.1 | 17 % | 11.2 | 1.18 |
| 400 | 40 | 40 | 7.9 | 200.0 | 207.2 | 170.7 | 13 % | 12.6 | 1.35 |
| 400 | 40 | 80 | 10.6 | 393.3 | 99.2 | 62.7 | 5 % | 17.1 | 1.77 |
| **800** | 10 | 80 | 15.7 | 99.0 | 104.4 | 68.0 | 21 % | 6.3 | 1.00 |
| **1600** | 10 | 80 | 7.0 | 52.3 | 264.2 | 227.9 | **70 %** | 2.8 | 1.88 |

**El resultado importante: el residuo a la recta dentro de la zona usable
es 0.9–1.9 nm rms en TODAS las configuraciones** — o sea, en el piso de
ruido (1.1 nm). Traducido: **una vez que estás dentro de la zona usable,
el paso entre píxeles es uniforme al nivel del ruido del sensor.** El
criterio de §9.6 (velocidad constante menos 3τ) no es conservador de más:
es justo lo que hace falta.

*(En una versión anterior este número daba 30–50 nm. Era un error del
análisis, no de la platina: se estaba midiendo el residuo sobre toda la
zona de velocidad constante, que incluye los primeros 3τ donde el error
todavía crece, y esa curvatura del transitorio dominaba el residuo.)*

**Y la regla de diseño se verifica directamente** (últimas dos filas):
con `speedupdown = 80` fijo, que a N=400 dejaba 0 % utilizable, **alargar
la tabla** lo recupera — 21 % a N=800, **70 % a N=1600**. No hace falta
bajar `speedupdown` para tener zona recta: hace falta que el tramo recto
dure más de 3τ. Alargar la tabla hace las dos cosas a la vez (suaviza el
giro *y* alarga la recta), bajar `speedupdown` solo hace la segunda.

Confirmación adicional: `τ = 11.0–12.4 ms` en las 20 corridas, a
velocidades de 6.3 a 42.5 µm/s. Sigue constante.
