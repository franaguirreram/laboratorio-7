"""Captura única Mono8 con Aravis; no mueve la platina."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


def imagen_mono8(buffer):
    """Copia los píxeles y retira el padding de cada fila."""
    import numpy as np
    ancho, alto = buffer.get_image_width(), buffer.get_image_height()
    padding_x, _ = buffer.get_image_padding()
    if ancho <= 0 or alto <= 0 or padding_x < 0:
        raise RuntimeError("Dimensiones del buffer inválidas")
    datos = np.frombuffer(bytes(buffer.get_image_data()), dtype=np.uint8)
    necesarios = alto * (ancho + padding_x)
    if datos.size < necesarios:
        raise RuntimeError(f"Buffer incompleto: {datos.size} bytes; se requieren {necesarios}")
    return datos[:necesarios].reshape(alto, ancho + padding_x)[:, :ancho].copy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listar", action="store_true", help="Lista cámaras sin capturar")
    parser.add_argument("--serial", default="4108802838")
    parser.add_argument("--exposicion-us", type=float, help="Desactiva autoexposición y fija microsegundos")
    parser.add_argument("--timeout-s", type=float, default=2.0)
    parser.add_argument("--salida", type=Path, default=Path("datos/camara"))
    parser.add_argument("--mostrar", action="store_true")
    args = parser.parse_args()
    if args.timeout_s <= 0 or (args.exposicion_us is not None and args.exposicion_us <= 0):
        parser.error("Timeout y exposición deben ser positivos")

    import gi
    gi.require_version("Aravis", "0.8")
    from gi.repository import Aravis
    import numpy as np

    Aravis.update_device_list()
    dispositivos = [(Aravis.get_device_id(i), Aravis.get_device_serial_nbr(i))
                    for i in range(Aravis.get_n_devices())]
    if args.listar:
        print(json.dumps(dispositivos, indent=2))
        return
    candidatos = [identificador for identificador, serial in dispositivos if serial == args.serial]
    if len(candidatos) != 1:
        raise RuntimeError(f"Se esperaba una cámara con serial {args.serial}; disponibles: {dispositivos}. "
                           "Conectala por USB 3 y cerrá otras aplicaciones que la usen.")
    camara = Aravis.Camera.new(candidatos[0])
    if camara is None:
        raise RuntimeError("No se pudo abrir la cámara")
    camara.clear_triggers()  # captura inmediata, sin esperar un disparo externo
    camara.set_pixel_format_from_string("Mono8")
    if camara.get_pixel_format_as_string() != "Mono8":
        raise RuntimeError("La cámara no aceptó Mono8")
    if args.exposicion_us is not None:
        minimo, maximo = camara.get_exposure_time_bounds()
        if not minimo <= args.exposicion_us <= maximo:
            raise RuntimeError(f"Exposición fuera de rango [{minimo}, {maximo}] µs")
        camara.set_exposure_time_auto(Aravis.Auto.OFF)
        camara.set_exposure_time(args.exposicion_us)
    foto = camara.acquisition(int(args.timeout_s * 1_000_000))
    if foto is None or foto.get_status() != Aravis.BufferStatus.SUCCESS:
        raise RuntimeError("Falló la captura; revisar conexión, exposición y timeout")
    if foto.get_image_pixel_format() != Aravis.PIXEL_FORMAT_MONO_8:
        raise RuntimeError("El buffer recibido no es Mono8")
    imagen = imagen_mono8(foto)
    meta = {
        "fecha_host_utc": datetime.now(timezone.utc).isoformat(),
        "modelo": camara.get_model_name(), "serial": camara.get_device_serial_number(),
        "frame_id": foto.get_frame_id(), "timestamp_camara_ns": foto.get_timestamp(),
        "formato": camara.get_pixel_format_as_string(),
        "region_xywh": list(camara.get_region()), "binning_xy": list(camara.get_binning()),
        "exposicion_us": camara.get_exposure_time(), "ganancia": camara.get_gain(),
        "shape_yx": list(imagen.shape), "min": int(imagen.min()), "max": int(imagen.max()),
        "saturados_pct": float(100 * np.mean(imagen == 255)),
        "python": sys.executable,
    }
    args.salida.mkdir(parents=True, exist_ok=True)
    base = args.salida / datetime.now(timezone.utc).strftime("foto_%Y%m%dT%H%M%S_%fZ")
    np.save(base.with_suffix(".npy"), imagen)
    from PIL import Image
    Image.fromarray(imagen).save(base.with_suffix(".png"))
    base.with_suffix(".json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, indent=2))
    print("Guardado:", base)
    if args.mostrar:
        import matplotlib.pyplot as plt
        plt.imshow(imagen, cmap="gray", vmin=0, vmax=255, interpolation="nearest")
        plt.colorbar(label="Intensidad digital Mono8")
        plt.show()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"Error: {error}") from error
