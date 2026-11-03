"""
Cámara IDS (Aravis): foto completa → elegir ROI → video en la ROI → guardar.

Flujo por celdas:

1. configurar la cámara y definir funciones;
2. foto completa y selección de la ROI (arrastrar un rectángulo + Enter);
3. video en la ROI (espacio: grabar/pausar, q o cerrar la ventana: terminar);
4. guardar el video (también se ofrece al final de la celda 3);
5. liberar la cámara.

La ROI se aplica en la cámara (OffsetX/Y, Width/Height), así el video va más
rápido; si la cámara no la acepta, se recorta por software.
"""

# %% 1) configurar
import json
import shutil
import subprocess
from collections import deque
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.widgets import RectangleSelector

EXPOSICION_US = 1800.0   # exposición en microseg
FPS_VIDEO = None         # None = lo más rápido que permita la exposición
ROI_MANUAL = None        # (x, y, ancho, alto) para saltear la selección con el mouse
TAMANO_ROI_AUTO = 256    # lado de la ROI si se confirma sin dibujar (centrada en el spot)
MEMORIA_MAX_MB = 1500    # tope de la grabación en RAM; se guardan los últimos cuadros
N_BUFFERS = 20           # buffers del stream de video
CARPETA_SALIDA = Path.home() / "LABORATORIO 7" / "datos" / "camara"
# Formatos sin empaquetar, de mayor a menor profundidad: (bytes/píxel, valor máximo).
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

camara.set_exposure_time_auto(Aravis.Auto.OFF)
camara.set_exposure_time(EXPOSICION_US)
camara.set_gain_auto(Aravis.Auto.OFF)
camara.set_gain(camara.get_gain_bounds()[0])
if FPS_VIDEO is not None:
    camara.set_frame_rate(FPS_VIDEO)

print(
    f"cámara lista | formato {FORMATO} | exposición real [µs]: "
    f"{camara.get_exposure_time()} | ganancia: {camara.get_gain()}"
)

roi = None               # (x, y, ancho, alto) en píxeles del sensor
recorte_software = None  # (slice_y, slice_x) si la cámara no aceptó la ROI
foto_completa = None
cuadros = deque()
tiempos_ns = deque()


def imagen_desde_buffer(buffer):
    """Matriz 2D sin padding (uint8 o uint16) a partir de un buffer de Aravis."""
    ancho = buffer.get_image_width()
    alto = buffer.get_image_height()
    padding, _ = buffer.get_image_padding()
    datos = np.frombuffer(bytes(buffer.get_image_data()), dtype=np.uint8)
    fila_util = ancho * BYTES_POR_PIXEL
    fila_bytes = fila_util + padding
    filas = datos[: alto * fila_bytes].reshape(alto, fila_bytes)[:, :fila_util]
    tipo = np.uint8 if BYTES_POR_PIXEL == 1 else np.dtype("<u2")  # little-endian
    imagen = np.ascontiguousarray(filas).view(tipo)
    if recorte_software is not None:
        imagen = imagen[recorte_software].copy()
    return imagen


def adquirir_imagen(timeout_us=2_000_000):
    """Una sola imagen (sin stream), con la región actual de la cámara."""
    buffer = camara.acquisition(timeout_us)
    if buffer is None or buffer.get_status() != Aravis.BufferStatus.SUCCESS:
        raise RuntimeError(
            "No llegó la imagen; revisar USB 3, cámara ocupada o timeout."
        )
    return imagen_desde_buffer(buffer)


def porcentaje_saturado(imagen):
    """Porcentaje de píxeles que alcanzan el máximo valor del formato."""
    return 100.0 * np.count_nonzero(imagen >= VALOR_MAXIMO) / imagen.size


def titulo_imagen(imagen):
    """Resumen de la imagen para el título de la figura."""
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


def quitar_roi():
    """Vuelve a la imagen completa del sensor."""
    global roi, recorte_software
    camara.set_integer("OffsetX", 0)
    camara.set_integer("OffsetY", 0)
    ancho = camara.get_width_bounds()[1]
    alto = camara.get_height_bounds()[1]
    camara.set_region(0, 0, ancho, alto)
    roi, recorte_software = None, None


def roi_automatica(imagen, lado=TAMANO_ROI_AUTO):
    """ROI cuadrada centrada en el centroide de los píxeles > 50 % del máximo."""
    y, x = np.nonzero(imagen > 0.5 * imagen.max())
    return int(x.mean()) - lado // 2, int(y.mean()) - lado // 2, lado, lado


def ajustar_roi(x, y, ancho, alto, ancho_total, alto_total):
    """Redondea la ROI a los incrementos y límites que acepta la cámara."""
    paso_x = max(1, camara.get_x_offset_increment())
    paso_y = max(1, camara.get_y_offset_increment())
    paso_ancho = max(1, camara.get_width_increment())
    paso_alto = max(1, camara.get_height_increment())
    ancho_min = camara.get_width_bounds()[0]
    alto_min = camara.get_height_bounds()[0]

    ancho = int(np.clip(round(ancho / paso_ancho) * paso_ancho, ancho_min, ancho_total))
    alto = int(np.clip(round(alto / paso_alto) * paso_alto, alto_min, alto_total))
    x = int(np.clip(x, 0, ancho_total - ancho)) // paso_x * paso_x
    y = int(np.clip(y, 0, alto_total - alto)) // paso_y * paso_y
    return x, y, ancho, alto


def aplicar_roi(x, y, ancho, alto):
    """Pone la ROI en la cámara; si no la acepta, la deja para recortar por software."""
    global roi, recorte_software
    alto_total, ancho_total = foto_completa.shape
    roi = ajustar_roi(x, y, ancho, alto, ancho_total, alto_total)
    try:
        camara.set_region(*roi)
        if tuple(camara.get_region()) != roi:
            raise RuntimeError(f"la cámara quedó en {tuple(camara.get_region())}")
        recorte_software = None
        print("ROI en la cámara (x, y, ancho, alto):", roi)
    except Exception as error:
        quitar_roi()
        roi = ajustar_roi(x, y, ancho, alto, ancho_total, alto_total)
        x, y, ancho, alto = roi
        recorte_software = (slice(y, y + alto), slice(x, x + ancho))
        print(f"ROI por software {roi} ({error})")
    print(f"para repetirla: ROI_MANUAL = {roi}")


def seleccionar_roi(imagen):
    """Muestra la foto, deja dibujar la ROI y espera Enter (o cerrar la ventana)."""
    fig, ax = plt.subplots()
    vmin, vmax = limites_contraste(imagen)
    ax.imshow(imagen, cmap="gray", vmin=vmin, vmax=vmax, interpolation="nearest")
    ax.imshow(mascara_saturados(imagen), interpolation="nearest")
    ax.set_title(
        f"{titulo_imagen(imagen)}\n"
        "arrastrá la ROI y Enter | Enter sin dibujar: ROI automática en el spot",
        fontsize=9,
    )
    ax.set_xlabel("x [px]")
    ax.set_ylabel("y [px]")

    selector = RectangleSelector(ax, lambda *_: None, interactive=True, button=[1])
    confirmado = {"listo": False}

    def al_apretar_tecla(evento):
        if evento.key == "enter":
            confirmado["listo"] = True

    fig.canvas.mpl_connect("key_press_event", al_apretar_tecla)
    plt.show(block=False)
    while plt.fignum_exists(fig.number) and not confirmado["listo"]:
        plt.pause(0.05)
    plt.close(fig)

    x0, x1, y0, y1 = selector.extents
    if x1 - x0 < 8 or y1 - y0 < 8:
        return roi_automatica(imagen)
    return int(x0), int(y0), int(round(x1 - x0)), int(round(y1 - y0))


def video():
    """Video en la ROI. Espacio: grabar/pausar. q o cerrar la ventana: terminar."""
    global cuadros, tiempos_ns
    ancho, alto = (roi[2], roi[3]) if roi is not None else foto_completa.shape[::-1]
    max_cuadros = int(MEMORIA_MAX_MB * 1e6 // (ancho * alto * BYTES_POR_PIXEL))
    cuadros = deque(maxlen=max_cuadros)
    tiempos_ns = deque(maxlen=max_cuadros)
    print(f"se graban hasta {max_cuadros} cuadros (los últimos)")

    stream = camara.create_stream(None, None)
    payload = camara.get_payload()
    for _ in range(N_BUFFERS):
        stream.push_buffer(Aravis.Buffer.new_allocate(payload))
    camara.set_acquisition_mode(Aravis.AcquisitionMode.CONTINUOUS)

    estado = {"grabando": False}

    def al_apretar_tecla(evento):
        if evento.key == " ":
            estado["grabando"] = not estado["grabando"]

    fig, ax = plt.subplots()
    fig.canvas.mpl_connect("key_press_event", al_apretar_tecla)
    llegadas_ns = deque(maxlen=30)  # para estimar los cuadros por segundo
    im = im_saturados = None

    camara.start_acquisition()
    try:
        while plt.fignum_exists(fig.number):
            imagen = None
            buffer = stream.timeout_pop_buffer(2_000_000)
            while buffer is not None:  # vacía la cola: se graba todo, se muestra el último
                if buffer.get_status() == Aravis.BufferStatus.SUCCESS:
                    imagen = imagen_desde_buffer(buffer)
                    llegadas_ns.append(buffer.get_system_timestamp())
                    if estado["grabando"]:
                        cuadros.append(imagen)
                        tiempos_ns.append(buffer.get_system_timestamp())
                stream.push_buffer(buffer)
                buffer = stream.try_pop_buffer()
            if imagen is None:
                print("timeout esperando cuadros; revisar USB 3 o exposición")
                continue

            if im is None:
                im = ax.imshow(imagen, cmap="gray", interpolation="nearest")
                im_saturados = ax.imshow(mascara_saturados(imagen), interpolation="nearest")
                ax.set_xlabel("x [px] (ROI)")
                ax.set_ylabel("y [px] (ROI)")
            im.set_data(imagen)
            im.set_clim(*limites_contraste(imagen))
            im_saturados.set_data(mascara_saturados(imagen))

            fps = (len(llegadas_ns) - 1) / max(1e-9, (llegadas_ns[-1] - llegadas_ns[0]) * 1e-9)
            grabacion = (
                f"● GRABANDO {len(cuadros)}" if estado["grabando"]
                else f"pausado ({len(cuadros)} grabados) | espacio: grabar"
            )
            ax.set_title(f"{fps:.0f} fps | {titulo_imagen(imagen)}\n{grabacion}", fontsize=9)
            plt.pause(0.001)
    finally:
        camara.stop_acquisition()
        del stream
    print(f"video terminado | {len(cuadros)} cuadros grabados en memoria")


def guardar_video(nombre=""):
    """Guarda los cuadros grabados: .npz (datos crudos), .json (metadatos) y .mp4 (para ver)."""
    if not cuadros:
        print("no hay cuadros grabados (en el video, espacio para grabar)")
        return None

    pila = np.stack(cuadros)
    t_ns = np.array(tiempos_ns, dtype=np.int64)
    fps = (len(t_ns) - 1) / ((t_ns[-1] - t_ns[0]) * 1e-9) if len(t_ns) > 1 else 1.0

    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)
    sufijo = f"_{nombre.strip().replace(' ', '_')}" if nombre.strip() else ""
    base = CARPETA_SALIDA / f"video_{datetime.now():%Y%m%d_%H%M%S}{sufijo}"

    np.savez(
        base.with_suffix(".npz"),
        cuadros=pila,
        t_ns=t_ns - t_ns[0],
        foto_completa=foto_completa if foto_completa is not None else np.empty(0),
    )
    meta = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "modelo": camara.get_model_name(),
        "formato": FORMATO,
        "valor_maximo": VALOR_MAXIMO,
        "roi_xywh": list(roi) if roi is not None else None,
        "roi_por_software": recorte_software is not None,
        "exposicion_us": camara.get_exposure_time(),
        "ganancia": camara.get_gain(),
        "n_cuadros": len(pila),
        "fps_medido": fps,
        "shape_tyx": list(pila.shape),
        "saturados_pct_max": float(max(porcentaje_saturado(c) for c in pila)),
    }
    base.with_suffix(".json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    if Path(ffmpeg).exists():
        vmin, vmax = np.percentile(pila[:: max(1, len(pila) // 50)], PERCENTILES_CONTRASTE)
        escala = 255 / max(vmax - vmin, 1)
        alto, ancho = pila.shape[1:]
        comando = [
            ffmpeg, "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{ancho}x{alto}",
            "-r", f"{fps:.3f}", "-i", "-",
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
            str(base.with_suffix(".mp4")),
        ]
        proceso = subprocess.Popen(comando, stdin=subprocess.PIPE)
        for cuadro in pila:  # de a un cuadro para no duplicar la memoria
            ocho_bits = np.clip((cuadro - np.float32(vmin)) * escala, 0, 255).astype(np.uint8)
            proceso.stdin.write(ocho_bits.tobytes())
        proceso.stdin.close()
        if proceso.wait() != 0:
            print("ffmpeg falló: el .npz y el .json sí se guardaron")
    else:
        print("ffmpeg no encontrado: no se generó el .mp4")

    print(f"guardado {len(pila)} cuadros a {fps:.1f} fps en {base}.[npz|json|mp4]")
    return base


# %% 2) foto completa y selección de ROI
quitar_roi()
foto_completa = adquirir_imagen()
aplicar_roi(*(ROI_MANUAL or seleccionar_roi(foto_completa)))


# %% 3) video en la ROI (espacio: grabar/pausar | q: terminar)
video()
if cuadros:
    respuesta = input("¿Guardar el video? Escribí un nombre (o 's'), Enter para no guardar: ")
    if respuesta.strip():
        guardar_video("" if respuesta.strip().lower() == "s" else respuesta)


# %% 4) guardar el último video (si no se guardó al terminar la celda 3)
guardar_video()


# %% 5) cerrar (correr solo esta celda al terminar)
quitar_roi()
del camara
