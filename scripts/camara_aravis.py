"""Utilidades de cámara compartidas (IDS U3-3060CP vía Aravis).

Lo usan camara_en_vivo.py y calibrar_escala_camara.py. No mueve la platina.

Incluye CamaraSimulada para probar el código sin hardware (--simular).
"""
import time

import numpy as np

# bits útiles por formato; los formatos "Packed" no se decodifican acá
BITS = {"Mono8": 8, "Mono10": 10, "Mono12": 12, "Mono16": 16}
SERIAL_POR_DEFECTO = "4108802838"  # el de docs/camara_captura_y_escala.md
PASO_PIXEL_UM = 5.86               # paso del sensor IMX174 según IDS


class Camara:
    """Envuelve Aravis: abrir, configurar, adquirir en continuo, cerrar."""

    def __init__(self, serial=SERIAL_POR_DEFECTO, n_buffers=6):
        import gi
        gi.require_version("Aravis", "0.8")
        from gi.repository import Aravis
        self.Aravis = Aravis
        self.n_buffers = n_buffers
        self.flujo = None

        # buscar la cámara por número de serie (como capturar_camara.py)
        Aravis.update_device_list()
        dispositivos = [(Aravis.get_device_id(i), Aravis.get_device_serial_nbr(i))
                        for i in range(Aravis.get_n_devices())]
        ids = [i for i, s in dispositivos if s == serial]
        if len(ids) != 1:
            raise RuntimeError(f"no encontré la cámara {serial}; hay: {dispositivos}. "
                               "revisá el USB 3 y cerrá otros programas que la usen")
        self.cam = Aravis.Camera.new(ids[0])
        self.cam.clear_triggers()  # sin disparo externo: adquiere libre
        self.formato = self.cam.get_pixel_format_as_string()

    # ---- configuración (hacerla antes de iniciar, salvo exposición/ganancia/fps)
    def formatos_disponibles(self):
        return list(self.cam.dup_available_pixel_formats_as_strings())

    def set_formato(self, nombre):
        if nombre not in BITS:
            raise ValueError(f"formato {nombre} no soportado acá; usar {list(BITS)}")
        if nombre not in self.formatos_disponibles():
            raise RuntimeError(f"la cámara no ofrece {nombre}; ofrece {self.formatos_disponibles()}")
        self.cam.set_pixel_format_from_string(nombre)
        self.formato = self.cam.get_pixel_format_as_string()

    def set_exposicion_us(self, us):
        lo, hi = self.cam.get_exposure_time_bounds()
        self.cam.set_exposure_time_auto(self.Aravis.Auto.OFF)
        self.cam.set_exposure_time(float(np.clip(us, lo, hi)))
        return self.cam.get_exposure_time()  # valor que realmente quedó

    def set_ganancia(self, g):
        lo, hi = self.cam.get_gain_bounds()
        self.cam.set_gain_auto(self.Aravis.Auto.OFF)
        self.cam.set_gain(float(np.clip(g, lo, hi)))
        return self.cam.get_gain()

    def set_fps(self, fps):
        # el fps real puede ser menor: lo limitan la exposición, la ROI y el ancho de banda USB
        lo, hi = self.cam.get_frame_rate_bounds()
        self.cam.set_frame_rate(float(np.clip(fps, lo, hi)))
        return self.cam.get_frame_rate()

    def limites(self):
        return {"exposicion_us": tuple(self.cam.get_exposure_time_bounds()),
                "ganancia": tuple(self.cam.get_gain_bounds()),
                "fps": tuple(self.cam.get_frame_rate_bounds())}

    # ---- adquisición continua
    def iniciar(self):
        A = self.Aravis
        self.cam.set_acquisition_mode(A.AcquisitionMode.CONTINUOUS)
        self.flujo = self.cam.create_stream(None, None)
        payload = self.cam.get_payload()  # tamaño de un cuadro en bytes
        for _ in range(self.n_buffers):
            self.flujo.push_buffer(A.Buffer.new_allocate(payload))
        self.cam.start_acquisition()

    def cuadro(self, timeout_s=0.5):
        """Devuelve (imagen, frame_id, timestamp_ns) del cuadro MÁS NUEVO, o None.

        Si se acumularon cuadros viejos en la cola (porque dibujar tarda más
        que la cámara), los descarta: así lo que se ve no queda atrasado.
        """
        A = self.Aravis
        buf = self.flujo.timeout_pop_buffer(int(timeout_s * 1e6))
        if buf is None:
            return None
        while True:  # vaciar la cola, quedándose con el último
            otro = self.flujo.try_pop_buffer()
            if otro is None:
                break
            self.flujo.push_buffer(buf)  # el viejo vuelve a la cola
            buf = otro
        try:
            if buf.get_status() != A.BufferStatus.SUCCESS:
                return None
            return imagen_de_buffer(buf), buf.get_frame_id(), buf.get_timestamp()
        finally:
            self.flujo.push_buffer(buf)  # siempre se devuelve el buffer

    def info(self):
        c = self.cam
        return {"modelo": c.get_model_name(), "serial": c.get_device_serial_number(),
                "formato": self.formato, "region_xywh": list(c.get_region()),
                "binning_xy": list(c.get_binning()),
                "exposicion_us": c.get_exposure_time(), "ganancia": c.get_gain(),
                "fps_config": c.get_frame_rate()}

    def detener(self):
        if self.flujo is not None:
            self.cam.stop_acquisition()
            self.flujo = None

    def cerrar(self):
        self.detener()  # al soltar el objeto se libera la conexión


def imagen_de_buffer(buf):
    """Copia los píxeles quitando el padding de cada fila (Mono8 y Mono10/12/16 sin empaquetar)."""
    ancho, alto = buf.get_image_width(), buf.get_image_height()
    pad, _ = buf.get_image_padding()
    bpp = 1 if buf.get_image_pixel_format() == 0x01080001 else 2  # 0x01080001 = Mono8 (PFNC)
    datos = np.frombuffer(bytes(buf.get_image_data()), dtype=np.uint8)
    paso = ancho * bpp + pad  # bytes por fila
    if datos.size < alto * paso:
        raise RuntimeError("buffer incompleto")
    filas = datos[:alto * paso].reshape(alto, paso)[:, :ancho * bpp]
    img = filas.copy() if bpp == 1 else filas.copy().view("<u2")
    return img.reshape(alto, ancho)


class CamaraSimulada:
    """Misma interfaz que Camara, con un punto gaussiano. Para probar sin hardware."""

    def __init__(self, forma=(1216, 1936), **_):
        self.alto, self.ancho = forma
        self.formato, self.exp, self.gan, self.fps = "Mono8", 5000.0, 0.0, 30.0
        self.punto_xy = (self.ancho / 2, self.alto / 2)  # lo mueve la platina simulada
        self.textura = None                               # opcional: imagen de fondo
        self._n, self._t = 0, 0.0
        self._rng = np.random.default_rng(0)

    def formatos_disponibles(self): return list(BITS)
    def set_formato(self, n): self.formato = n
    def set_exposicion_us(self, us): self.exp = float(np.clip(us, 10, 1e6)); return self.exp
    def set_ganancia(self, g): self.gan = float(np.clip(g, 0, 20)); return self.gan
    def set_fps(self, f): self.fps = float(np.clip(f, 1, 160)); return self.fps
    def limites(self): return {"exposicion_us": (10, 1e6), "ganancia": (0, 20), "fps": (1, 160)}
    def iniciar(self): pass
    def detener(self): pass
    def cerrar(self): pass
    def info(self): return {"modelo": "SIMULADA", "serial": "0", "formato": self.formato,
                            "exposicion_us": self.exp, "ganancia": self.gan}

    def cuadro(self, timeout_s=0.5):
        time.sleep(1 / self.fps)
        x0, y0 = self.punto_xy
        y, x = np.mgrid[:self.alto, :self.ancho]
        brillo = 150.0 * (self.exp / 5000.0) * 10 ** (self.gan / 20)
        img = brillo * np.exp(-((x - x0) ** 2 + (y - y0) ** 2) / (2 * 6.0 ** 2))
        if self.textura is not None:
            img = img + self.textura(x, y, x0, y0)
        img = img + 10 + self._rng.normal(0, 1.5, img.shape)
        tope = 2 ** BITS[self.formato] - 1
        self._n += 1
        return np.clip(img * (tope / 255), 0, tope).astype(np.uint8 if tope == 255 else np.uint16), self._n, int(time.time() * 1e9)


def abrir_camara(simular=False, serial=SERIAL_POR_DEFECTO):
    return CamaraSimulada() if simular else Camara(serial)


def a_8bit(imagen, formato):
    """Escala a 0..255 solo para mostrar; los datos guardados no se tocan."""
    if imagen.dtype == np.uint8:
        return imagen
    return (imagen >> (BITS[formato] - 8)).astype(np.uint8)


def localizar_punto(imagen, formato, radio=40, fraccion=0.5):
    """Centroide (x, y) en píxeles del punto más brillante, o None.

    Método (elección mía, sin validar con datos reales): suavizo para ubicar el
    máximo, tomo una ventana de ±radio px, resto la mediana de la imagen como
    fondo y pondero por lo que supera `fraccion` del pico.
    """
    from scipy.ndimage import gaussian_filter
    img = imagen.astype(float)
    iy, ix = np.unravel_index(np.argmax(gaussian_filter(img, 3)), img.shape)
    y0, y1 = max(iy - radio, 0), min(iy + radio + 1, img.shape[0])
    x0, x1 = max(ix - radio, 0), min(ix + radio + 1, img.shape[1])
    ventana = img[y0:y1, x0:x1]
    fondo = np.median(img)
    pico = ventana.max() - fondo
    if pico <= 0:
        return None
    peso = np.clip(ventana - fondo - fraccion * pico, 0, None)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    s = peso.sum()
    tope = 2 ** BITS[formato] - 1
    return {"x": float((peso * xx).sum() / s), "y": float((peso * yy).sum() / s),
            "pico": float(ventana.max()), "saturado": bool(ventana.max() >= tope)}


def desplazamiento_correlacion(ref, img):
    """Corrimiento (dx, dy) en px de `img` respecto de `ref`, por correlación cruzada.

    Sirve con cualquier textura (rayas, polvo, una retícula), no solo con un punto.
    Convención: img(y, x) = ref(y - dy, x - dx). Subpíxel por parábola
    alrededor del pico (sin validar con datos reales).
    """
    def prep(a):
        a = a.astype(float)
        a = a - a.mean()
        return a * np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    c = np.fft.ifft2(np.fft.fft2(prep(img)) * np.conj(np.fft.fft2(prep(ref)))).real
    iy, ix = np.unravel_index(np.argmax(c), c.shape)

    def fino(m, i, n):  # vértice de la parábola por tres puntos (con borde circular)
        a, b, d = m[(i - 1) % n], m[i], m[(i + 1) % n]
        den = a - 2 * b + d
        return 0.0 if den == 0 else 0.5 * (a - d) / den
    dy = iy + fino(c[:, ix], iy, c.shape[0])
    dx = ix + fino(c[iy, :], ix, c.shape[1])
    if dy > c.shape[0] / 2: dy -= c.shape[0]
    if dx > c.shape[1] / 2: dx -= c.shape[1]
    return float(dx), float(dy)
