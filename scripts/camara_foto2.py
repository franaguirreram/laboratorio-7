"""
Flujo por celdas:

1. configurar la cámara;
2. adquirir y mostrar una foto;
3. repetir fotos en una misma ventana;
4. liberar la cámara.
"""

# %% 1) configurar
import matplotlib.pyplot as plt
import numpy as np

EXPOSICION_US = 1800.0 # exposición en microseg
# Formatos sin empaquetar, de mayor a menor profundidad: (bytes/píxel, valor máximo).
# Más bits NO evita saturar (eso lo fija el sensor), pero da más niveles
# en las zonas débiles cuando se baja la exposición.
FORMATOS_PREFERIDOS = {"Mono12": (2, 4095), "Mono10": (2, 1023), "Mono8": (1, 255)}
PERCENTILES_CONTRASTE = (1, 99.9)  # escala de grises según la imagen, no el formato


def abrir_o_reutilizar_camara():
    """Devuelve la cámara de la consola o abre la primera cámara disponible."""
    camara_existente = globals().get("camara")
    if camara_existente is not None:
        return camara_existente

    import gi

    gi.require_version("Aravis", "0.8")
    from gi.repository import Aravis

    camara_nueva = Aravis.Camera.new(None)
    globals()["Aravis"] = Aravis
    globals()["camara"] = camara_nueva
    return camara_nueva


Aravis = globals().get("Aravis")
camara = abrir_o_reutilizar_camara()

disponibles = camara.dup_available_pixel_formats_as_strings()
FORMATO = next(f for f in FORMATOS_PREFERIDOS if f in disponibles)
camara.set_pixel_format_from_string(FORMATO)
BYTES_POR_PIXEL, VALOR_MAXIMO = FORMATOS_PREFERIDOS[FORMATO]
print("formatos disponibles:", disponibles, "| usando:", FORMATO)

camara.set_exposure_time_auto(Aravis.Auto.OFF)
camara.set_exposure_time(EXPOSICION_US)
camara.set_gain_auto(Aravis.Auto.OFF)
ganancia_minima, _ = camara.get_gain_bounds(); print(camara.get_gain_bounds())
camara.set_gain(ganancia_minima)

print(
    "cámara lista | exposición real [µs]:",
    camara.get_exposure_time(),
    "| ganancia:",
    camara.get_gain(),
)


def adquirir_imagen(timeout_us=2_000_000):
    """Adquiere una imagen y devuelve una matriz 2D sin padding (uint8 o uint16)."""
    buffer = camara.acquisition(timeout_us)
    if buffer is None or buffer.get_status() != Aravis.BufferStatus.SUCCESS:
        raise RuntimeError(
            "No llegó la imagen; revisar USB 3, cámara ocupada o timeout."
        )

    ancho = buffer.get_image_width()
    alto = buffer.get_image_height()
    padding, _ = buffer.get_image_padding()
    datos = np.frombuffer(bytes(buffer.get_image_data()), dtype=np.uint8)
    fila_util = ancho * BYTES_POR_PIXEL
    fila_bytes = fila_util + padding
    filas = datos[: alto * fila_bytes].reshape(alto, fila_bytes)[:, :fila_util]
    tipo = np.uint8 if BYTES_POR_PIXEL == 1 else np.dtype("<u2")  # little-endian
    return np.ascontiguousarray(filas).view(tipo)


def porcentaje_saturado(imagen):
    """Porcentaje de píxeles que alcanzan el máximo valor del formato."""
    pixeles_saturados = np.count_nonzero(imagen >= VALOR_MAXIMO)
    return 100.0 * pixeles_saturados / imagen.size


def titulo_imagen(imagen):
    """Construye el resumen actual de la imagen para la figura."""
    return (
        f"máximo {imagen.max()}/{VALOR_MAXIMO} | "
        f"saturados {porcentaje_saturado(imagen):.2f} %"
    )


def limites_contraste(imagen):
    """vmin/vmax por percentiles para que se vea bien aunque la imagen sea tenue."""
    vmin, vmax = np.percentile(imagen, PERCENTILES_CONTRASTE)
    return vmin, max(vmax, vmin + 1)


def mascara_saturados(imagen):
    """Capa RGBA roja sobre los píxeles saturados, transparente en el resto."""
    capa = np.zeros((*imagen.shape, 4))
    capa[imagen >= VALOR_MAXIMO] = (1, 0, 0, 1)
    return capa


# %% 2) sacar una foto y mostrar métricas (rojo = saturado)
imagen = adquirir_imagen()

plt.figure()
vmin, vmax = limites_contraste(imagen)
plt.imshow(imagen, cmap="gray", vmin=vmin, vmax=vmax, interpolation="nearest")
plt.colorbar(label="intensidad [ADU]")
plt.imshow(mascara_saturados(imagen), interpolation="nearest")
plt.title(titulo_imagen(imagen))
plt.xlabel("x [px]")
plt.ylabel("y [px]")
plt.show()


# %% 3) video: repite adquirir_imagen() y actualiza la misma figura
N_CUADROS = 500

fig, ax = plt.subplots()
imagen = adquirir_imagen()
im = ax.imshow(imagen, cmap="gray", interpolation="nearest")
im_saturados = ax.imshow(mascara_saturados(imagen), interpolation="nearest")
for i in range(N_CUADROS):
    if not plt.fignum_exists(fig.number):
        break
    imagen = adquirir_imagen()
    im.set_data(imagen)
    im.set_clim(*limites_contraste(imagen))
    im_saturados.set_data(mascara_saturados(imagen))
    ax.set_title(f"cuadro {i} | {titulo_imagen(imagen)}")
    plt.pause(0.001)


# %% 4) cerrar (correr solo esta celda al terminar)
del camara

# %%
