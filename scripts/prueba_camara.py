"""Conexión mínima a la cámara IDS mediante Aravis, sin capturar imágenes.

Ejecutar con: /opt/homebrew/bin/python3.14 conectar_camara.py
"""

import gi

gi.require_version("Aravis", "0.8")
from gi.repository import Aravis


def main():
    Aravis.update_device_list()
    if Aravis.get_n_devices() == 0:
        raise SystemExit(
            "Aravis no detectó ninguna cámara. Revisá el cable y el puerto USB 3."
        )

    identificador = Aravis.get_device_id(0)
    camara = Aravis.Camera.new(identificador)
    if camara is None:
        raise SystemExit("No se pudo abrir la cámara.")

    print("Cámara conectada:", camara.get_model_name())
    print("Número de serie:", camara.get_device_serial_number())
    # Al terminar el programa se libera la conexión.


if __name__ == "__main__":
    main()
#%%
import gi
import numpy as np
import matplotlib.pyplot as plt

gi.require_version("Aravis", "0.8")
from gi.repository import Aravis

camara = Aravis.Camera.new(None)
camara.set_pixel_format_from_string("Mono8")
foto = camara.acquisition(2_000_000)  # espera hasta 2 segundos

if foto is None or foto.get_status() != Aravis.BufferStatus.SUCCESS:
    raise RuntimeError("No se pudo obtener la foto.")

imagen = np.frombuffer(bytes(foto.get_image_data()), dtype=np.uint8)
imagen = imagen.reshape(foto.get_image_height(), foto.get_image_width())

plt.imshow(imagen, cmap="gray")
plt.axis("off")
plt.show()

print("Dimensiones:", imagen.shape)
print("Mínimo / máximo:", imagen.min(), imagen.max())
print("Píxeles saturados (%):", 100 * np.mean(imagen == 255))

plt.figure()
plt.imshow(imagen, cmap="gray", vmin=0, vmax=255,
           interpolation="nearest")
plt.colorbar()
plt.show()

#%%

#%% Capturar una foto nueva
foto = camara.acquisition(2_000_000)

if foto is None or foto.get_status() != Aravis.BufferStatus.SUCCESS:
    raise RuntimeError("Falló la captura.")

alto = foto.get_image_height()
ancho = foto.get_image_width()
px, py = foto.get_image_padding()

datos = np.frombuffer(bytes(foto.get_image_data()), dtype=np.uint8)
imagen = datos[:alto * (ancho + px)].reshape(alto, ancho + px)
imagen = imagen[:, :ancho].copy()

print("Cuadro:", foto.get_frame_id())
print("Tiempo de cámara:", foto.get_timestamp())
print("Mínimo / máximo:", imagen.min(), imagen.max())
print("Saturados (%):", round(100 * np.mean(imagen == 255), 2))

plt.figure()
plt.imshow(imagen, cmap="gray", vmin=0, vmax=255,
           interpolation="nearest")
plt.colorbar()
plt.show()