# Tutorial: video en vivo de la cámara

Revisión: 12 de octubre de 2026. Cámara: IDS U3-3060CP-M-GL Rev.2.2, serial
`4108802838`, por USB 3 con Aravis (ver `docs/entorno_unificado.md`).

Etiquetas: **[VERIFICADO]** leído en el código fuente o en la fuente citada,
**[INFERENCIA]** razonamiento mío sin comprobar con el equipo,
**[A PROBAR]** hay que comprobarlo con la cámara real. Nada de este tutorial
se probó todavía con la cámara conectada: solo con la cámara simulada.

## 1. Qué archivos hay

| Archivo | Para qué |
|---|---|
| `scripts/camara_aravis.py` | Maneja la cámara (abrir, configurar, adquirir) y trata la imagen (ajuste gaussiano). |
| `scripts/camara_en_vivo.py` | Ventana con video, sliders y la posición del punto. No mueve la platina. |
| `scripts/calibrar_escala_camara.py` | Mueve un eje de la platina y calibra px/µm. Se ve aparte. |

## 2. Comandos

Desde la raíz del repo, con el entorno del laboratorio:

```bash
source ~/python-envs/pi/bin/activate

python scripts/camara_en_vivo.py --listar-formatos   # qué formatos y límites tiene la cámara
python scripts/camara_en_vivo.py                     # Mono8, 30 fps, exposición 5000 µs
python scripts/camara_en_vivo.py --fps 60 --exposicion-us 2000
python scripts/camara_en_vivo.py --formato Mono12    # solo si --listar-formatos lo ofrece
python scripts/camara_en_vivo.py --roi-radio 40      # ROI del ajuste más grande
python scripts/camara_en_vivo.py --simular           # sin cámara, para probar el programa
```

Antes de abrir: cerrar cualquier otro programa que use la cámara (Spyder,
notebooks). Si no la encuentra, revisar el cable USB 3.

### Controles de la ventana

- Slider **log10 exp [µs]**: exposición (escala logarítmica: 3 = 1 ms, 4 = 10 ms).
- Slider **ganancia** y slider **fps pedidos**.
- **Clic** en la imagen: mueve la ROI del ajuste (cuadro cian) a ese lugar.
- Tecla **r**: centra la ROI en el punto más brillante.
- Botón **guardar foto**: guarda el último cuadro en `datos/camara/` como
  `.npy` (valores crudos, sin escalar) más un `.txt` con la configuración.
- Texto amarillo: posición del punto, `sigma`, pico, exposición, ganancia,
  fps configurado y máximo, fps de la cámara, fps de pantalla y % saturado.

## 3. Funciones de Aravis que usamos

Las firmas las verifiqué en los headers del repo de Aravis (rama `main`,
`src/arvcamera.h` y `src/arvstream.h`). En PyGObject se llaman igual sin el
prefijo `arv_camera_` y sin el último argumento de error. Tu versión de
Homebrew puede diferir un poco. **[A PROBAR]** en tu Mac.

| Función de Aravis | Qué hace | Dónde la usamos |
|---|---|---|
| `Aravis.update_device_list()`, `get_n_devices()`, `get_device_id(i)`, `get_device_serial_nbr(i)` | Lista las cámaras USB3 Vision y su serial. | `Camara.__init__`: elige la del serial `4108802838`. |
| `Aravis.Camera.new(id)` | Abre la cámara. | `Camara.__init__` |
| `clear_triggers()` | Quita el disparo externo: la cámara adquiere sola. | `Camara.__init__` |
| `dup_available_pixel_formats_as_strings()` | Formatos de píxel que ofrece la cámara. | `formatos_disponibles`, `--listar-formatos` |
| `set_pixel_format_from_string("Mono8")`, `get_pixel_format_as_string()` | Fija y lee el formato. | `set_formato` |
| `get_exposure_time_bounds()`, `set_exposure_time_auto(OFF)`, `set_exposure_time(us)`, `get_exposure_time()` | Exposición en µs: límites, apagar la automática, fijar, releer. | `set_exposicion_us` |
| `get_gain_bounds()`, `set_gain_auto(OFF)`, `set_gain(g)`, `get_gain()` | Igual para la ganancia. | `set_ganancia` |
| `get_frame_rate_bounds()`, `set_frame_rate(fps)`, `get_frame_rate()` | Cuadros por segundo pedidos. | `set_fps` |
| `set_acquisition_mode(CONTINUOUS)` | Adquisición continua (no una sola foto). | `iniciar` |
| `get_payload()` | Bytes que ocupa un cuadro. | `iniciar`: tamaño de los buffers |
| `create_stream(None, None)` | Crea el canal por donde llegan los cuadros. | `iniciar` |
| `Aravis.Buffer.new_allocate(n)` y `stream.push_buffer(buf)` | Reserva buffers y los entrega al canal para que la cámara los llene. | `iniciar`, y al devolver cada buffer |
| `start_acquisition()` / `stop_acquisition()` | Empieza y termina la adquisición. | `iniciar` / `detener` |
| `stream.timeout_pop_buffer(us)`, `stream.try_pop_buffer()` | Saca un cuadro lleno: esperando hasta un tiempo, o sin esperar. | `cuadro` |
| `buf.get_status()`, `get_image_data()`, `get_image_width/height()`, `get_image_padding()`, `get_frame_id()`, `get_timestamp()` | Datos del cuadro recibido. | `imagen_de_buffer`, `cuadro` |

### Cómo se usa, en orden

1. Abrir la cámara y configurar formato, exposición, ganancia y fps.
2. `iniciar()`: crea el canal, le entrega 6 buffers vacíos y arranca.
3. En cada vuelta del visor, `cuadro()` saca el buffer **más nuevo**, copia la
   imagen (quitando el padding de cada fila), y **devuelve el buffer al canal**.
   Si no se devolviera, la cámara se quedaría sin buffers y se cortaría el video.
4. Si dibujar tarda más que la cámara, se acumulan cuadros viejos; `cuadro()`
   los descarta para que lo que se ve no quede atrasado.

## 4. Exposición, ganancia y fps

**Exposición** es cuánto tiempo integra luz el sensor en cada cuadro.
La señal crece con la exposición (mientras no sature). Con el obturador global
del IMX174 todos los píxeles integran a la vez. **[VERIFICADO]** obturador
global: ficha de IDS citada en `docs/camara_captura_y_escala.md`.

**Ganancia** amplifica la señal digital o analógica después de integrar.
**[INFERENCIA]** (conocimiento general de cámaras): amplifica también el ruido,
así que no sustituye a más luz o más exposición. Sus unidades las define la
cámara; el visor usa los límites que devuelve `get_gain_bounds()`.

**Cuadros por segundo (`set_frame_rate`)** es la cadencia que *pedimos*. La
cámara la limita a `[mínimo, máximo]` (`get_frame_rate_bounds()`), y nuestro
`set_fps` recorta el pedido a ese rango y devuelve el valor que quedó.

Cómo se relacionan **[INFERENCIA]**, comportamiento típico de las cámaras
GenICam, a confirmar mirando el visor:

- Un cuadro no puede durar menos que su exposición: si la exposición es mayor
  que `1/fps`, el fps real baja. El visor muestra "fps cfg (máx ...)": probar
  subir la exposición con el slider y ver si baja el máximo.
- El máximo también lo limita la región (ROI de sensor), el binning y el ancho
  de banda del USB. IDS indica unos 161 fps a resolución máxima
  ([IDS](https://en.ids-imaging.com/store/u3-3060cp-rev-2-2.html)).
- Cuentas mías: 1936 × 1216 × 161 = 379 MB/s con 1 byte por píxel. Con Mono12
  en contenedores de 16 bits sería el doble (~758 MB/s) y empaquetado
  (1,5 bytes) ~568 MB/s; USB 3 a 5 Gbit/s no pasa de 500 MB/s teóricos con la
  codificación 8b/10b. **[INFERENCIA]**: en Mono12 el fps máximo debería ser
  menor que en Mono8.
- El visor muestra dos fps: "fps cámara" (sale de los `frame_id`, o sea
  cuadros que la cámara realmente produjo) y "fps pantalla" (cuántos se
  dibujaron). Si el de pantalla es menor, la pantalla es el cuello de botella.

### Cómo elegir para este montaje (punto de partida, no medido)

1. Ganancia en el mínimo.
2. Exposición baja y subirla hasta que el pico del punto esté a mitad de
   escala aproximadamente (Mono8: ~128 de 255). El pico se lee en el texto.
3. Que **no sature**: el texto avisa. Un punto saturado deforma el ajuste
   gaussiano y la posición pierde exactitud.
4. Si con la exposición mínima todavía satura: bajar la potencia o poner
   atenuación (el filtro ND del esquema), no subir la ganancia.
5. Para estabilizar después: exposición corta = más cuadros por segundo y
   menos arrastre si algo se mueve durante el cuadro. Es un compromiso con la
   señal; se decide con datos del montaje real.

## 5. Mono8 y Mono12

- **Mono8**: 256 niveles. Es lo que usa Scan. Más liviano para el USB.
- **Mono12 / Mono10 / Mono16**: más niveles, mejor para ver un pico débil y
  un fondo a la vez sin saturar, a costa de más datos por cuadro.
- Qué formatos tiene *esta* cámara: correr `--listar-formatos`. **[A PROBAR]**.
  Los formatos empaquetados (nombres con `Packed`) no están soportados.
- El visor muestra siempre en la escala nativa (0 a 2^bits − 1) y guarda los
  valores crudos.

## 6. Tratamiento de la imagen: igual que takyaq

Para que después el flujo sea el mismo, la posición del punto se calcula como
en takyaq (detalles y fuente en `docs/referencias/takyaq.md`):

1. Se define una **ROI** alrededor del punto (cuadro cian). Arranca centrada en
   el máximo y queda fija hasta que se recentre.
2. Sobre los valores **crudos** de la ROI (sin restar fondo) se ajusta una
   **gaussiana 2D** con `scipy.optimize.curve_fit`:
   `offset + A·exp(-((x−x0)² + (y−y0)²) / (2σ²))`.
3. El valor inicial es `(max−min, máximo de la ROI, σ = lado/3, min)`, y en
   los cuadros siguientes se reutiliza el ajuste anterior.
4. Se reportan `x0`, `y0` (centro) y `σ`, en píxeles. takyaq los convierte a nm
   con nm/px, que sale de la calibración.

`ajuste_gaussiano` de `camara_aravis.py` da el mismo resultado que
`_gaussian_fit` de takyaq: lo comparé con una imagen sintética y la diferencia
fue 0,0 (no probé con imágenes reales).

Diferencias a tener presentes:

- **Ejes:** en takyaq `x` es la fila (primer índice del array) e `y` la
  columna. El visor muestra `x` = columna (horizontal) e `y` = fila, como se ve
  en pantalla.
- **Control propio:** takyaq no valida el ajuste. Yo descarto (sin cruz roja)
  los ajustes con centro fuera de la ROI o σ mayor que la ROI. Un ajuste sobre
  puro ruido a veces pasa igual: en la simulación dio `pico=15` contra 159 con
  el punto; si el pico es parecido al fondo, no hay punto.
- takyaq ajusta en paralelo (varios procesos); el visor, en uno solo.

## 7. Prueba con láser y espejo

1. Láser apagado: abrir el visor y ver que la cámara responde (el fondo cambia
   con la luz de la sala).
2. Atenuar y encender el láser; poner el espejo en el portamuestras.
3. Bajar la exposición hasta que no sature; tecla `r` para centrar la ROI.
4. Mover la lente que enfoca sobre la cámara y mirar `sigma`: al enfocar debería
   bajar y el pico subir. **[INFERENCIA]** esperada, a confirmar.
5. Guardar una foto de referencia con el botón.

## 8. Problemas frecuentes

- *No encuentra la cámara:* otro programa la tiene abierta, cable USB 2, o
  falta reiniciar el kernel de Spyder (ver `docs/camara_captura_y_escala.md`).
- *El fps real es menor que el pedido:* mirar "fps cfg (máx ...)"; bajar la
  exposición o usar un formato más liviano.
- *La imagen va atrasada:* no debería, `cuadro()` descarta los viejos; si pasa,
  mirar "fps pantalla".
- *`fps cámara` muestra un valor raro al principio:* es un promedio móvil, se
  estabiliza en unos segundos.
- *Falla una función de Aravis:* anotar el mensaje; puede ser una diferencia
  de versión con los headers que consulté.
