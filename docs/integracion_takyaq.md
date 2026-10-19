# Integración de la platina con Takyaq

## Qué traduce el adaptador

Takyaq no conoce comandos GCS2 ni `pipython`. Solo necesita una platina con
estos métodos, siempre en **nanómetros**:

| Takyaq | Adaptador | PIPython/GCS2 | Unidad de la platina |
| --- | --- | --- | --- |
| `get_position()` | lee la posición actual | `qPOS(["A", "B", "C"])` | µm |
| `set_position_xy(x, y)` | mueve X/Y y espera | `MOV(["A", "B"], [...])` + `waitontarget` | µm |
| `set_position_z(z)` | mueve Z y espera | `MOV(["C"], [...])` si se configura | µm |

La clase está en `integraciones/takyaq_piezo_macos.py` como
`TakyaqPIStage`. Por defecto mapea `x -> A`, `y -> B`, `z -> C`.

## Uso mínimo

```python
from integraciones.takyaq_piezo_macos import connect_e545_for_takyaq_macos

from takyaq.stabilizer import Stabilizer

pidevice, piezo = connect_e545_for_takyaq_macos()
try:
    # Construir también la cámara, CameraInfo y el controlador de Takyaq.
    # stabilizer = Stabilizer(camera, piezo, camera_info, controller)
    # stabilizer.start_loop()
    # ...
    pass
finally:
    piezo.close()
```

`connect_e545_for_takyaq_macos()` usa el mismo gateway FTDI que los scripts
de medición (`PIFtdiGateway`) y deja disponible `pidevice` para comandos
específicos del experimento, como wave generator y data recorder. El sufijo
`_macos` es intencional: esta conexión es solo para el MacBook Air que no
puede usar el driver nativo de PI.

En una computadora que sí pueda instalar los drivers de PI, no se usa
`PIFtdiGateway`. Se conecta normalmente:

```python
from pipython import GCSDevice
from integraciones.takyaq_piezo_macos import TakyaqPIStage

pidevice = GCSDevice("E-517")
pidevice.ConnectUSB("0111176619")
piezo = TakyaqPIStage(pidevice)
```

## Cómo se ejecuta el sistema

Takyaq trabaja en un hilo de estabilización. En cada ciclo adquiere una
imagen, localiza los marcadores, el controlador calcula una corrección y
llama a `set_position_xy` o `set_position_z`. El ciclo se inicia con
`stabilizer.start_loop()` y se detiene con `stabilizer.stop_loop()`.

Para este montaje se puede estabilizar XY y Z. Antes de activar el bloqueo
hay que verificar que el eje C esté conectado y que sus límites sean
correctos.

## Celda para usarlo en el MacBook Air

El ejemplo completo está en `scripts/takyaq_e545_macos.py` y está escrito
como celdas de Spyder. El orden es:

1. Instalar Takyaq en el mismo entorno Python que usa Spyder:

   ```bash
   python -m pip install git+https://github.com/Stefani-Lab/takyaq.git
   ```

2. Completar en la primera celda los valores medidos de `NM_PER_PIXEL_XY`,
   `NM_PER_PIXEL_Z`, `Z_SPOT_ANGLE_RAD`, `XY_ROIS` y `Z_ROI`.
3. Ejecutar la conexión de cámara y platina.
4. Iniciar el loop, configurar los ROI y activar primero solo tracking.
5. Revisar posición, imagen y signos; recién después activar
   `enable_xy_stabilization()` y `enable_z_stabilization()`.

El valor `1.0` de calibración que aparece en el ejemplo es un marcador
provisorio y no debe usarse para un resultado experimental. La escala XY se
obtiene con la calibración óptica documentada en
`docs/camara_captura_y_escala.md`; la calibración Z y el ángulo del spot
deben medirse con el procedimiento de calibración de Takyaq.

El adaptador de cámara del ejemplo implementa exactamente el método que
Takyaq necesita, `get_image()`. El adaptador de platina implementa
`get_position()`, `set_position_xy()` y `set_position_z()`.

## Antecedente encontrado

No apareció en la historia de este repositorio una clase Takyaq/PI previa.
Sí quedaron los intentos y decisiones de conexión de la platina en
`docs/RESUMEN_conexion_E545_macOS.md`, y la implementación actual del
gateway se instala desde `e545-pi-ftdi-gateway`. El repositorio de referencia
es [Stefani-Lab/takyaq](https://github.com/Stefani-Lab/takyaq); su interfaz
está documentada en el README y en `takyaq/base_classes.py`.
