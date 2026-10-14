"""Video en vivo mínimo de la cámara IDS (Aravis, Mono8). Cerrá la ventana para terminar.

Uso:  python scripts/camara_mvp.py [exposicion_us] [fps]
      python scripts/camara_mvp.py 2000 30
"""
import sys

import gi
import numpy as np
import matplotlib.pyplot as plt

gi.require_version("Aravis", "0.8")
from gi.repository import Aravis

exposicion_us = float(sys.argv[1]) if len(sys.argv) > 1 else 5000.0
fps = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0

# abre la primera cámara que encuentra y la configura
camara = Aravis.Camera.new(None)
camara.set_pixel_format_from_string("Mono8")
camara.set_exposure_time_auto(Aravis.Auto.OFF)
camara.set_exposure_time(exposicion_us)
camara.set_frame_rate(fps)
print("exposición real [µs]:", camara.get_exposure_time(), "| fps configurado:", camara.get_frame_rate())

# canal de cuadros: le damos buffers vacíos y la cámara los va llenando
flujo = camara.create_stream(None, None)
for _ in range(5):
    flujo.push_buffer(Aravis.Buffer.new_allocate(camara.get_payload()))
camara.set_acquisition_mode(Aravis.AcquisitionMode.CONTINUOUS)
camara.start_acquisition()


def siguiente_cuadro():
    """Espera un cuadro (hasta 1 s), lo copia como array y devuelve el buffer al canal."""
    buf = flujo.timeout_pop_buffer(1_000_000)
    if buf is None:
        return None
    imagen = None
    if buf.get_status() == Aravis.BufferStatus.SUCCESS:
        ancho, alto = buf.get_image_width(), buf.get_image_height()
        pad, _ = buf.get_image_padding()  # bytes sobrantes al final de cada fila
        datos = np.frombuffer(bytes(buf.get_image_data()), dtype=np.uint8)
        imagen = datos[:alto * (ancho + pad)].reshape(alto, ancho + pad)[:, :ancho].copy()
    flujo.push_buffer(buf)  # siempre se devuelve, si no la cámara se queda sin buffers
    return imagen


fig, ax = plt.subplots()
im = None
try:
    while plt.fignum_exists(fig.number):  # termina al cerrar la ventana
        imagen = siguiente_cuadro()
        if imagen is None:
            continue
        if im is None:
            im = ax.imshow(imagen, cmap="gray", vmin=0, vmax=255, interpolation="nearest")
        else:
            im.set_data(imagen)
        ax.set_title(f"máx {imagen.max()}  saturados {100 * np.mean(imagen == 255):.2f} %")
        plt.pause(0.001)  # deja que matplotlib dibuje
finally:
    camara.stop_acquisition()
