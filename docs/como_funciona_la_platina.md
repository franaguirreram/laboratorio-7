# Cómo funciona la platina, qué medimos, y qué de eso nos importa

Documento de síntesis, escrito el 2026-09-07 a partir de todo lo medido
hasta ahora (43 corridas de rampa + 44 de escalón, en tres jornadas).
Reordena lo que sabemos en el orden en que hace falta entenderlo.

> **Actualizado el mismo 2026-09-07, después de correr el barrido
> RTR × DCO** (20 corridas nuevas): las secciones 3.5, 4.2 y 6 llevan los
> números medidos ese día, que corrigen hacia abajo la ganancia atribuida
> a apagar DCO. Detalle completo en §9 del doc de velocidad.

El análisis numérico completo está en
`docs/velocidad_ancho_de_banda_y_diseno_de_scans.md`; los pasos de
adquisición, en `protocolos/adquisicion_wave_data_recorder.md`. Este
documento es el "por qué", los otros dos son el "cuánto" y el "cómo".

Todo número acá abajo está **medido en nuestro equipo**, salvo donde diga
[MANUAL] o [VERIFICAR].

---

## 1. Qué es la platina, en una frase

Una platina piezoeléctrica es **un cristal al que le crecés un poco el
tamaño aplicándole voltaje**, con una regla que mide cuánto creció, y una
computadora que ajusta el voltaje hasta que "cuánto creció" coincida con
"cuánto le pediste".

Las tres piezas, cada una con su nombre en el equipo:

| pieza | qué hace | dónde vive |
|---|---|---|
| **actuador piezo** | se deforma ~0.1 % al aplicarle 0–100 V. En 200 µm de recorrido total, eso es lo que da el rango | dentro de la **E-545** (la platina) |
| **sensor capacitivo** | mide la separación de dos placas por su capacidad. Sin contacto, sin fricción, sin histéresis | también en la E-545, en paralelo al piezo |
| **controlador digital** | lee el sensor, compara con el objetivo, corrige el voltaje. 25.000 veces por segundo | la **E-517** (la caja) |

Lo importante de esta arquitectura: **el piezo solo es bueno para
moverse, no para saber dónde está.** Un piezo en lazo abierto tiene
histéresis del 10–15 % y creep logarítmico: le pedís 10 µm, te da entre
8.5 y 11.5 según de dónde venías, y sigue moviéndose durante minutos
después. Todo eso desaparece si medís la posición con algo que no sea el
piezo y cerrás el lazo. Por eso la variable física de interés no es "qué
voltaje le pusimos" sino "qué dice el sensor", y por eso el error de
posición que medimos son nanómetros y no micrones.

---

## 2. El lazo: qué pasa cada 40 microsegundos

Cada **40 µs** (25 kHz — medido, no de datasheet) el controlador ejecuta,
en serie, esta cadena entera:

```
   sensor capacitivo → demodulador → ADC → [ P·e + I·∫e ] → DAC → amplificador → piezo
        ^                                                                          |
        |__________________________  la platina se mueve  _______________________|
```

Esto es un único ciclo cerrado. Vale la pena decir explícitamente qué NO
significa, porque es la confusión que más tiempo nos costó:

- **No hay un "reloj del sensor" separado del "reloj de la platina".**
  Los 25 kHz son a la vez la tasa de muestreo del sensor, la tasa de
  actualización del voltaje, el tick del generador de trayectorias y el
  tick del grabador de datos. Un solo reloj para todo.
- **Los 60 MHz del procesador [MANUAL] no son una velocidad física.** Su
  única lectura útil: 60 MHz ÷ 25 kHz = **2400 instrucciones por ciclo**.
  Es el presupuesto de cómputo del firmware por tick. Explica por qué el
  servo corre a 25 kHz y no a 1 MHz. No dice nada sobre qué tan rápido se
  mueve la platina.

### El número que sí manda: τ ≈ 12 ms

La platina no responde instantáneamente porque tiene masa, el
amplificador tiene corriente limitada, y el lazo tiene una ganancia
finita. El resultado neto se resume en **una** constante de tiempo:

> **τ ≈ 12 ms**, o sea un ancho de banda de lazo cerrado **f_c ≈ 15 Hz**.

Lo medimos de dos formas independientes que no se hablan entre sí:

1. **Escalón**: le pedimos un salto instantáneo y tarda
   **t(10–90 %) ≈ 18 ms** en llegar. Eso da f_3dB ≈ 0.35/18 ms ≈ **19 Hz**.
2. **Rampa**: le pedimos que se mueva a velocidad constante y se queda
   **atrás** por una distancia fija `e = v·τ`, con **τ = 12.1 ms**.

Los dos números no son idénticos (un sistema de primer orden puro daría
τ = 18 ms/2.197 = 8.2 ms, no 12.1). **Esa discrepancia es información,
no un error de medición**: dice que el lazo no es de primer orden puro —
tiene al menos un integrador y algo de retardo puro. Para diseñar
escaneos alcanza con τ ≈ 12 ms; para modelarlo bien haría falta un
barrido de frecuencia (Bode) que todavía no hicimos.

Lo notable de τ es lo **constante** que es: el mismo valor sobre cuatro
décadas de velocidad (0.25 a 3150 µm/s) y cuatro de amplitud (10 nm a
200 µm). Es decir, **el sistema es lineal en todo el rango en que lo
usamos**. Eso es lo que hace que valga la pena caracterizarlo una sola
vez.

Y para poner las escalas en perspectiva: el servo es ~1500 veces más
rápido que τ, y el DSP ~4 millones de veces. **Ninguno de los dos es el
cuello de botella. Todo lo que se pueda mejorar de un escaneo pasa por
esos 12 ms, o por evitarlos.**

---

## 3. Cómo se le ordena moverse

Hay dos formas, y la diferencia entre ellas es la diferencia entre un
experimento que funciona y uno que no.

### 3.1 La forma lenta: `MOV`, un comando por posición

```python
pidevice.MOV(['A'], [100.5])   # "andá a 100.5 µm"
```

Cada `MOV` es un viaje de ida y vuelta por USB. Con el gateway FTDI que
escribimos, eso cuesta milisegundos, y encima hay que **esperar** a que
la platina llegue y asiente (~150 ms hasta ±2 nm). Para un barrido de
64 líneas eso son 10 segundos tirados solo en esperas.

Sirve para posicionarse antes de empezar. No sirve para escanear.

### 3.2 La forma real: cargar la trayectoria adentro del controlador

El E-517 tiene un **generador de ondas** (*wave generator*): le cargás la
trayectoria completa de antemano y él la reproduce solo, sincronizado a
su propio reloj de 40 µs, sin que la computadora intervenga. Tres objetos
distintos, que se llaman parecido y conviene no confundir:

| objeto | qué es | cuántos hay |
|---|---|---|
| **wave table** | memoria pasiva: una lista de posiciones | 3 tablas × 8192 puntos |
| **wave generator** | el reproductor: lee una tabla y la empuja como objetivo | 3 |
| **eje** | el piezo físico (A, B) | 2 |

En otros controladores PI se conectan con `WSL(generador, tabla)`.
**En este no**: el firmware V01.243 responde `Unknown command` a `WSL`
[MEDIDO 2026-09-07]. O sea que el mapeo generador↔tabla es **fijo**. Los
scripts anteriores no funcionaban por casualidad al asumir
"tabla 1 ↔ generador 1": funcionaban porque no hay otra opción.

Esto importa para el raster X+Y: como no se puede *elegir* la asignación,
hay que **averiguar cuál es** por experimento (cargar una tabla, disparar
un generador, ver qué eje se mueve) antes de diseñar nada alrededor de
una suposición.

### 3.3 El parámetro que fija la velocidad: `WTR`

El generador avanza un punto de la tabla cada `WTR` ciclos de servo:

```
    dwell por punto = WTR × 40 µs
    velocidad       = Δx_por_punto / (WTR × 40 µs)
```

`Δx_por_punto` lo fija la geometría (amplitud ÷ cantidad de puntos); `WTR`
fija el tiempo. **`WTR` es el knob de velocidad, y es el único.**

> **Resultado nulo, para el cuaderno:** durante 20 corridas barrimos una
> variable llamada `T_SERVO_US` creyendo que cambiaba algo. Nunca se le
> mandaba al controlador: solo etiquetaba el eje temporal del CSV. Las 20
> corridas son físicamente idénticas de a grupos, y la columna de tiempo
> de esos archivos está mal escalada por un factor 4 o 40. Sirvieron igual,
> como medida de repetibilidad: repitiendo el mismo punto físico el error
> varía **±23 %**. Ese es el piso de significancia de todo lo que
> comparemos: **diferencias menores al 23 % no son diferencias.**

### 3.4 El objetivo es una escalera, no una rampa

Verificado leyendo el objetivo grabado: **el generador no interpola.**
Cambia el setpoint una vez cada `WTR` ciclos y se queda quieto en el
medio. Lo que la platina recibe no es una rampa: es un tren de
micro-escalones de `Δx_por_punto` cada `WTR × 40 µs`.

No importa en la práctica —porque τ = 12 ms es mucho más largo que
cualquier dwell razonable, así que el lazo integra la escalera y la
suaviza solo— pero **sí importa al analizar**: cualquier cálculo que use
"la diferencia entre puntos consecutivos del objetivo" da cero la mitad
de las veces. La velocidad hay que sacarla de un ajuste, no de una
derivada punto a punto.

El cuanto del objetivo es **0.1 nm** (21 bits sobre 200 µm): 17 veces por
debajo del piso de ruido. **La resolución digital no es el límite de
nada.**

### 3.5 Cómo se mira lo que pasó: el data recorder

En paralelo, el controlador graba hasta **3 señales × 8192 muestras**,
una muestra cada `RTR` ciclos de servo. Arranca solo al disparar el
generador. Puede grabar posición comandada, posición real, error de
seguimiento, voltaje del piezo, salida del lazo.

**`WTR` y `RTR` son relojes independientes**, y confundirlos tiene dos
consecuencias distintas que nos mordieron las dos:

```
    WTR → cuán rápido se MUEVE       RTR → cuán fino y cuán largo se MIRA
    ventana grabada = 8192 × RTR × 40 µs      resolución = RTR × 40 µs
```

Con `RTR = 1` la ventana está topeada en **328 ms**. **El knob para ver
más tiempo es `RTR`.** Con `RTR = 10` sube a 3.3 s y la subida (18 ms)
todavía tiene ~45 muestras: se gana ventana casi gratis.

Pero hay una trampa, y nos costó 27 archivos [MEDIDO 2026-09-07]: **el
grabador sigue grabando después de que la trayectoria terminó**, y en
cuanto el generador se detiene **el canal de posición comandada pasa a
valer 0** mientras el de posición real sigue midiendo bien. Si la
trayectoria dura menos que la ventana, el archivo termina con "comandada
= 0, real = 101 µm", y cualquier análisis que busque el escalón como el
salto más grande del comando encuentra uno de **−101 µm** al final en vez
del de +2 µm del principio. Todas las métricas salen sin sentido, sin que
nada avise.

La regla que lo evita es simple: **que la trayectoria dure toda la
ventana**.

```
    WTR = RTR   y   n_pre + n_post = 8192
    → ventana = 8192 × RTR × 40 µs,  resolución = RTR × 40 µs
```

Como el tramo posterior al escalón es plano, alargarlo no cuesta nada
(un solo segmento) — y lo que se graba durante todo ese rato es
exactamente lo que queremos ver: la platina asentando sola.

---

## 4. Cómo responde: los cuatro hechos medidos

### 4.1 A un escalón: 18 ms de subida, y después una cola

Le pedimos un salto instantáneo y la platina tarda **18 ms** en cubrir el
10–90 % del camino — **el mismo tiempo para un escalón de 200 nm que para
uno de 200 µm**, que es otra forma de decir que el sistema es lineal (no
hay saturación de velocidad en el rango que usamos).

Pero llegar al 90 % no es llegar. Después hay un sobrepico del 2–3 % y una
**cola lenta de ~100 ms** hasta entrar en ±5 nm. Y esa cola resultó ser lo
más interesante que medimos.

### 4.2 La cola es culpa de DCO, y se puede apagar

`DCO` (*Drift Compensation*) es una corrección lenta que el controlador
aplica para compensar deriva térmica de largo plazo. Con un par
controlado —mismo escalón de 2 µm, misma ventana, la única variable
distinta siendo DCO—:

| | DCO = ON | DCO = OFF |
|---|---|---|
| pico de la excursión lenta ("bump") | **58 nm** en t ≈ 56 ms | **5.5 nm** (= ruido) |
| entra en la banda de ±5 nm | **146 ms** | **84 ms** |
| t(10–90 %) | 18.7 ms | 19.6 ms |
| error final | −0.11 nm | −0.27 nm |

*(Medianas de 18 corridas del 2026-09-07 en ventanas comparables, con dos
corridas descartadas por golpes en la mesa. El bump de 58 nm a 56 ms
reproduce casi exactamente el de 55 nm a 58 ms medido cinco días antes:
buena reproducibilidad.)*

O sea: **10× de diferencia en la excursión** y **1.7× en el tiempo de
asentamiento**. El primer par de corridas del 02/09 había sugerido 2.7×;
con 20 corridas y ventanas suficientes, la ganancia real es la mitad de
eso. Sigue siendo clara, pero conviene decirla bien.

Un control importante salió bien: **el resultado no depende de `RTR`** —
146 ms con DCO ON en las cinco configuraciones de grabación, 84 ms con
DCO OFF. `RTR` cambia lo que mirás, no lo que la platina hace.

Además, **el bump no escala con el tamaño del escalón**: vale 30–105 nm
para escalones de 20 nm a 200 µm. Casi constante en valor absoluto. Esa es
la firma de un **término aditivo del controlador**, no de un límite de
velocidad ni del retraso del lazo — coherente con un compensador de
deriva pensado para constantes de tiempo de segundos, reaccionando mal a
un escalón de milisegundos.

**Cuidado antes de apagarlo y olvidarse**: DCO existe para algo. Apagarlo
acelera el asentamiento, pero puede dejar crecer una deriva lenta que sí
importa en una medición que dure minutos.

Primera respuesta parcial [MEDIDO 2026-09-07]: en los **8 segundos** que
graban las corridas de `RTR = 25`, las dos condiciones se quedan dentro
de **±1.5 nm** sin tendencia visible (DCO OFF ajusta −2 nm/min, al borde
de la significancia; DCO ON, 0).

**Pero este número hay que volver a medirlo**: ese día la platina no
estaba en su posición de montaje definitiva, y la deriva
térmica/mecánica es justamente lo que más depende del montaje. Lo que
midamos de deriva con la platina suelta no dice nada sobre la deriva con
la platina montada. Las medidas de asentamiento y de ancho de banda son
mucho menos sensibles a eso, así que esas sí valen.

### 4.3 A una rampa: se queda atrás, pero de forma perfectamente predecible

Moviéndose a velocidad constante, la platina va atrasada exactamente
`e = v·τ`. Los 43 puntos que medimos colapsan sobre esa recta.

Esto **reencuadra el problema entero**. El error de seguimiento no es
ruido ni imprecisión: es un **desplazamiento rígido, conocido y
constante**. Si en post-proceso corregimos el retraso:

| corrida | velocidad | error RMS crudo | corregido |
|---|---|---|---|
| A = 10 µm | 158 µm/s | 1587 nm | **94 nm** (×17) |
| A = 1 µm | 15.8 µm/s | 169 nm | **105 nm** (×1.6) |
| A = 0.1 µm | 1.63 µm/s | 19 nm | **4.4 nm** (×4.3) |

> **Bajar la velocidad para reducir el error de seguimiento es tirar
> tiempo a la basura.** El error que estabas peleando ya lo conocías.

Se saca de dos maneras equivalentes: mandarle el comando **adelantado**
(`x(t+τ)`, que en velocidad constante es simplemente sumarle `v·τ`), o —
mejor todavía si vas a hacer imagen — **asignar cada muestra a la posición
real medida** en vez de a la comandada. No necesitás que la platina esté
donde le pediste: necesitás **saber dónde estuvo**, y eso ya lo estás
grabando.

Lo único que **no** se arregla así es el **sobrepico del giro** (94–159 nm),
el residuo del integrador desarmándose cuando la velocidad cambia de
signo. Ese hay que sacarlo de la zona de interés, no corregirlo.

### 4.4 Quieta: 1.7 nm de ruido, y son de la red eléctrica

Con la platina quieta y asentada:

- **σ = 1.7 nm RMS**
- una única línea espectral aislada: **2.4 nm de amplitud en 50.0 Hz**

Dos consecuencias, una metodológica y una física:

**(a)** Que la línea caiga en 50.0 Hz exactos **confirma de forma
independiente que el ciclo de servo es 40 µs**. Con los 10 µs que decían
algunos scripts, caería en 200 Hz, que no corresponde a nada del
laboratorio.

**(b)** Promediar no ayuda. σ se queda clavada en 1.7 nm entre 0.04 ms y
4 ms de promediado, y recién baja cuando la ventana cubre un período
completo de 50 Hz (0.4 nm a 20 ms). Es ruido **correlacionado**, no
blanco: **grabar más rápido u oversamplear por píxel no compra nada.** Y
como 50 Hz está por encima del ancho de banda del lazo (15 Hz), **el
servo tampoco lo puede rechazar**. Para un objetivo sub-nanométrico, esos
2.4 nm son el enemigo número uno, y lo primero es saber si son *pickup
eléctrico en el cable del sensor* o *movimiento mecánico real* — se
distingue grabando con el servo abierto.

---

## 5. Qué de todo esto importa para las prácticas

Ordenado por cuánto se gana, no por cuánto cuesta.

**1. Apagar DCO durante el scan — pero volviendo a prenderlo entre
frames.** Apagado corta el asentamiento de 146 a 84 ms (1.7×) y la
excursión posterior al escalón de 58 a 5.5 nm (10×). Pero tiene un costo
que tardamos en ver: **con DCO apagado queda un error estático que
deriva** — en dos tandas separadas por 18 minutos, el mismo escalón de
2 µm asentó con un offset de −0.4 nm en una y de +10.0 nm en la otra, con
el mismo ruido (σ = 1.2 nm) en las dos. Con DCO prendido el offset queda
en ~0 nm siempre.

O sea que las dos cosas son ciertas y no se contradicen: el bump de DCO
es un **transitorio** que molesta dentro de cada línea, y el offset sin
DCO es un **error lento** que molesta entre líneas. El esquema que sale de
ahí es el híbrido: **DCO apagado mientras el scan corre, prendido en las
pausas** para volver a poner el cero.

**2. Corregir el retraso en vez de esperarlo.** Factor 2 a 17 en error de
seguimiento. Gratis. Y si vas a hacer imagen, la versión buena de esta
idea es no corregir nada: **asignar cada píxel a la posición real
grabada**.

**3. No frenar entre líneas.** Un `MOV` con espera cuesta ~150 ms. En un
frame de 64 líneas son 10 segundos de nada. En vez de eso: extender la
rampa más allá de la zona de interés (*over-scan*) por al menos
`v·12 ms + 150 nm`, y darle al giro al menos `3τ ≈ 36 ms`. Los puntos de
over-scan gastan memoria de tabla, que sobra, y no gastan imagen.

**4. Escanear en las dos direcciones.** Hoy, con trayectoria triangular,
la mitad de los puntos son la vuelta y se descartan. Escaneando
bidireccional esa mitad se convierte en imagen: **el presupuesto se
duplica**. Lo único que lo hacía inviable era el retraso, que ahora está
medido: las líneas de ida y de vuelta salen corridas `2·v·τ` una respecto
de la otra, y esa corrección es fija y conocida.

**5. Poner la zona de interés en el tramo de velocidad constante.** Los
puntos de la tabla están equiespaciados en **tiempo**, no en espacio. En
los extremos, donde el generador acelera y desacelera, el paso espacial
entre píxeles **no es uniforme**. Solo en el tramo de velocidad constante
vale `Δx = v · WTR · 40 µs` rigurosamente.

**6. `RTR = WTR` para hacer imagen.** Con esa igualdad el grabador guarda
exactamente una muestra por punto de trayectoria, o sea **una muestra por
píxel**, y entonces "el frame entra en el buffer" quiere decir
`L × P ≤ 8192` (128×64, 90×91, 64×128). Hoy corremos con `RTR=1, WTR=20`:
20 muestras por punto, que es perfecto para estudiar la dinámica *dentro*
de un punto y exactamente lo contrario de lo que hace falta para imagen.

**7. Un raster no cuesta `P×L` puntos de tabla, cuesta `P+L`.** El
generador de X guarda **una línea** y la repite `L` veces; el de Y guarda
la escalera de `L` líneas y avanza un punto por cada línea completa de X.
Un frame de 128×64 gasta 192 de los 8192 puntos disponibles. **La tabla
no es el límite; el grabador sí.**

**8. Lo que NO hay que tocar**: la resolución digital de comando (0.1 nm,
17× por debajo del ruido), y la sintonía del servo (P/I) — esa es la
única vía para bajar τ, pero es la más riesgosa y va última, después de
haber agotado todo lo anterior.

---

## 6. Qué falta medir, en orden

1. ~~Asentamiento real con y sin DCO, en la misma ventana.~~
   **HECHO 2026-09-07**: 146 ms (ON) contra 84 ms (OFF), §4.2.
2. **Deriva con DCO apagado, en la escala de minutos.** A 8 s no se ve
   nada; falta la corrida larga antes de dejarlo apagado en una medición
   que dure más que eso.
3. **De dónde sale el 50 Hz.** Grabar posición y voltaje de control a la
   vez, con el servo cerrado y abierto.
4. **Verificar la corrección de retraso en vivo**, no solo en post.
5. ~~Confirmar `WSL`.~~ **HECHO 2026-09-07**: no existe en este firmware
   (§3.2). Queda pendiente lo otro: **averiguar el mapeo fijo
   generador↔tabla↔eje**, y si `WGO([1,2],[1,1])` arranca los dos
   generadores en el mismo tick. Sigue siendo el prerrequisito duro del
   raster X+Y.

Los cinco están implementados como barridos listos para correr en
`scripts/E517_barrido.py` (`barrido_deriva`, `barrido_rtr_dco`,
`barrido_ruido`, `barrido_lag_wos`, y `WSL` va en toda corrida).

---

## 7. Conexión con pMINFLUX — pendiente

*(Esta sección queda abierta a propósito: falta la descripción del
sistema completo.)*

Lo que el E-517 ofrece como interfaz con el resto de un experimento, y
que habrá que confirmar contra el manual y el panel trasero del equipo
antes de diseñar nada [VERIFICAR]:

- **Salidas de trigger digitales** (`CTO`, `TWS`): el controlador puede
  emitir un pulso en un punto **específico de la tabla de trayectoria**.
  Es exactamente el mecanismo para decir "estoy en el píxel N, contá
  fotones ahora" sin que la computadora esté en el lazo. Es, casi seguro,
  el gancho correcto con pMINFLUX.
- **Entradas/salidas digitales y analógicas** (`DIO`, `qTAV`): para
  recibir un disparo externo o exponer una señal.
- **Trigger del grabador** (`DRT`): el grabador puede arrancar por un
  evento externo en vez de por el generador.
- **El grabador ya guarda posición real muestra a muestra.** Si el
  detector de fotones y el grabador comparten un instante t=0 común, cada
  fotón se puede asignar a la posición **real** de la platina en ese
  momento, no a la comandada. Dado lo del punto 4.3, esto no es un
  detalle: es la forma de que el retraso de 12 ms deje de importar.

Para poder cerrar esta sección hace falta saber: **quién manda el tiempo**
(¿la platina dispara al detector, o al revés?), **con qué precisión** hay
que sincronizarlos, y **qué señales físicas** hay realmente cableadas
entre los dos equipos.
