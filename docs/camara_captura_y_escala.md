# Obtener una imagen y entender su escala

Revisión: 5 de octubre de 2026. Cámara identificada en los chats:
IDS U3-3060CP-M-GL Rev.2.2, serial `4108802838`.

## Comandos de adquisición

Conectar la cámara por USB 3, cerrar las aplicaciones que puedan tenerla
abierta y ejecutar desde la raíz del repo:

```bash
source ~/python-envs/pi/bin/activate
python scripts/capturar_camara.py --listar
python scripts/capturar_camara.py --exposicion-us 1000 --mostrar
```

`1000` significa **1 ms de exposición**, un valor de prueba que debe
ajustarse a la iluminación. El programa desactiva el disparo externo,
elige el serial indicado, solicita Mono8 y, si se especifica exposición,
desactiva la autoexposición. Guarda `.npy`, `.png` y metadata `.json` en
`datos/camara/`. Cada ejecución solicita una foto nueva. El PNG conserva
los valores de 8 bits; no es una captura del gráfico con autoescala.
El NPY conserva la matriz sin compresión de imagen.

```bash
python scripts/capturar_camara.py --exposicion-us 5000 --timeout-s 5 --salida datos/camara/prueba
```

El timeout es el máximo de espera de la adquisición y no la exposición.
Para exposiciones largas, darle margen suficiente. Sin `--exposicion-us`,
se conserva la exposición/autoexposición existente y se registra el valor
releído. No garantiza comparabilidad fotométrica entre sesiones.
`--serial OTRO_SERIAL` permite seleccionar explícitamente otra unidad.

Para terminar: esperar el fin de la captura y cerrar la consola/kernel
si la cámara continúa abierta desde un notebook o Spyder. El script de
terminal libera los recursos al finalizar el proceso.

## Qué mide el sensor

Según la [ficha oficial de IDS](https://en.ids-imaging.com/store/u3-3060cp-rev-2-2.html),
el sensor CMOS Sony IMX174 tiene 1936 × 1216 píxeles, paso de 5,86 µm,
área activa aproximada de 11,345 × 7,126 mm y obturador global.
La variante M es monocromática. El global shutter integra simultáneamente
los píxeles; la transmisión de datos ocurre después y no elimina el
desenfoque por movimiento durante la exposición.

Cada píxel integra señal luminosa durante la exposición y entrega un
valor digital. En Mono8 los valores van de 0 a 255; 255 indica recorte
en ese formato. Aumentar ganancia también amplifica ruido. Ni exposición
ni ganancia convierten un sensor sin lente en una cámara enfocada.

Sin óptica, el sensor recibe luz con una distribución espacial, pero no
forma una imagen nítida de objetos lejanos. En la prueba anterior se
conectó sin óptica: variar el brillo con la tapa demuestra respuesta a
la luz. Para observar una muestra hay que formar su imagen sobre el
sensor, por ejemplo con objetivo y lente de tubo si es un sistema
corregido a infinito.

## Píxeles, campo y distancia sobre la muestra

El paso físico del sensor no es la distancia que representa un píxel
sobre la muestra. Con aumento lateral total efectivo M y sin binning:

`escala = 5,86 / M` µm/píxel.

`campo_x = ancho_en_píxeles × escala`; análogamente para Y.

Ejemplos calculados, **no calibraciones del montaje**:

| Aumento total supuesto | Escala | Campo completo aproximado |
|---|---:|---:|
| 100× | 58,6 nm/píxel | 113,45 × 71,26 µm |
| 150× | 39,07 nm/píxel | 75,63 × 47,51 µm |

El aumento grabado en un objetivo se cumple con la lente de tubo de
diseño. Otra focal, un adaptador o un relay cambia M. Una ROI reduce el
campo, pero por sí sola no cambia la escala. Binning/decimación cambian
el muestreo: registrarlos y calibrar otra vez cuando se modifiquen.
El programa conserva la ROI/binning existente y los informa; no presupone
que se esté usando el sensor completo.

## Calibración experimental

1. Formar una imagen enfocada de una retícula con distancia conocida L.
2. Medir la separación N en píxeles entre marcas: escala = L/N.
3. Repetir en X e Y, en varios lugares del campo y con varias separaciones.
4. Registrar objetivo, lente de tubo/relay, ROI, binning, fecha y resultado
   con su dispersión e incertidumbre de la retícula.

También puede estimarse usando un marcador fijo y varios desplazamientos
conocidos de platina, esperando el asentamiento. La posición **medida**
por la platina es preferible a asumir que el movimiento comandado se
alcanzó. Este método incluye las incertidumbres de ambos instrumentos.
El movimiento aparente puede invertir el signo o tener rotación.

Para relacionar ambos ejes de platina con la cámara, ajustar una matriz
`[Δu, Δv] = A [Δx, Δy]`, con u,v en píxeles y x,y en µm. Obtener las
columnas de A moviendo cada eje por separado y repitiendo en ambos
sentidos. Su inversa convierte desplazamientos de imagen a coordenadas
de platina cuando A es invertible. Así se incluye rotación y diferencia
de escala. Para Z por astigmatismo hace falta **otra calibración**: una
curva de forma/ancho de la imagen frente a Z; la escala lateral no la da.

## Resolución y precisión

Más píxeles no implican más resolución óptica. La PSF del montaje, la
apertura numérica, la longitud de onda, aberraciones y desenfoque fijan
el detalle separable. Muestrear con varios píxeles una PSF permite
ajustarla mejor; localizar un marcador con precisión subpíxel no significa
resolver dos objetos a esa misma distancia. La precisión debe evaluarse
con repeticiones, señal, fondo, ruido y deriva.

Para barrido continuo, el movimiento durante la exposición introduce una
longitud de arrastre aproximada `|v| × exposición`. Es distinto de la
latencia entre cuadro y posición: un error temporal δt introduce un
error espacial aproximado `|v| δt`. Los timestamps de cámara no equivalen
automáticamente al reloj del controlador; requieren sincronización.

## Diagnóstico de capturas

- Sin detección: comprobar USB 3, aplicaciones abiertas y el intérprete.
  Los chats registran un falso negativo por restricciones USB del entorno
  de ejecución del agente; repetir en Terminal local puede distinguirlo.
- Mucha saturación: reducir exposición/ganancia o iluminación y repetir.
- Imagen clara sin figuras: comprobar primero lente y plano de enfoque.
- Foto que parece repetida: volver a adquirir; comparar timestamp,
  frame ID y respuesta a un cambio controlado de iluminación. Un timestamp
  distinto por sí solo no valida toda la cadena de imagen.
- Filas mal ordenadas: verificar formato y padding; el script solo decodifica
  Mono8 y retira los bytes de separación de cada fila.
- Conflicto `gobject`: reiniciar el kernel del entorno unificado; usar
  PyGObject con `from gi.repository import ...`.

API de adquisición, exposición y formatos:
[Aravis Camera](https://aravisproject.github.io/docs/aravis-0.8/ArvCamera.html).
Datos y padding:
[Aravis Buffer](https://aravisproject.github.io/docs/aravis-0.8/ArvBuffer.html).
