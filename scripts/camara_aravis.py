"""Utilidades de cámara compartidas (IDS U3-3060CP vía Aravis).

Lo usan camara_en_vivo.py y calibrar_escala_camara.py. No mueve la platina.

Incluye CamaraSimulada para probar el código sin hardware (--simular).
"""
import time
import warnings

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


def _gaussiana2d(grid, amplitud, x0, y0, sigma, offset):
    """Gaussiana 2D, igual a takyaq.stabilizer._gaussian2D.

    sigma es el desvío estándar (a = 1/(2 sigma^2)); el docstring de takyaq
    dice "FWHM" pero la fórmula es de sigma.
    """
    x, y = grid
    a = 1.0 / (2 * sigma ** 2)
    return (offset + amplitud * np.exp(-(a * (x - x0) ** 2 + a * (y - y0) ** 2))).ravel()


def ajuste_gaussiano(datos, x_max, y_max, sigma):
    """Ajusta una gaussiana a `datos`; devuelve (x, y, sigma) en píxeles DENTRO del recorte.

    Igual a takyaq.stabilizer._gaussian_fit: sin restar fondo, sobre los valores
    crudos, con curve_fit y p0 = (max-min, x_max, y_max, sigma, min).
    Convención de takyaq: x es el PRIMER índice del array (fila) e y el segundo
    (columna), con meshgrid indexing="ij". Si el ajuste falla devuelve nan.
    """
    from scipy.optimize import curve_fit
    try:
        grid = np.meshgrid(np.arange(datos.shape[0]), np.arange(datos.shape[1]), indexing="ij")
        v_min, v_max = datos.min(), datos.max()
        p0 = (v_max - v_min, x_max, y_max, sigma, v_min)
        with warnings.catch_warnings():  # una ROI sin punto avisa en cada cuadro; solo silencia el aviso
            warnings.simplefilter("ignore")
            popt, _ = curve_fit(_gaussiana2d, grid, datos.ravel(), p0=p0)
    except Exception:
        return np.nan, np.nan, np.nan
    return popt[1], popt[2], popt[3]


def roi_en_maximo(imagen, radio=30):
    """ROI (f0, f1, c0, c1) de lado 2*radio centrada en el máximo de la imagen suavizada."""
    from scipy.ndimage import gaussian_filter
    f, c = np.unravel_index(np.argmax(gaussian_filter(imagen.astype(float), 3)), imagen.shape)
    return (max(f - radio, 0), min(f + radio + 1, imagen.shape[0]),
            max(c - radio, 0), min(c + radio + 1, imagen.shape[1]))


def localizar_punto(imagen, formato, roi=None, previos=None, radio=30):
    """Posición del punto por ajuste gaussiano en una ROI, como en takyaq.

    roi: (f0, f1, c0, c1) en píxeles del array; si es None se centra en el máximo.
    previos: (x, y, sigma) del cuadro anterior dentro de la ROI. takyaq lo reutiliza
    como valor inicial del ajuste siguiente; si es None se inicia como
    takyaq._initialize_last_params (máximo de la ROI, sigma = lado/3).
    Devuelve dict con x (columna) e y (fila) en la imagen completa, sigma [px],
    pico, saturado, roi y params (para pasar como `previos`); None si el ajuste falla
    o es absurdo (centro fuera de la ROI o sigma mayor que la ROI).
    """
    roi = roi or roi_en_maximo(imagen, radio)
    f0, f1, c0, c1 = roi
    recorte = imagen[f0:f1, c0:c1]
    if previos is None:
        pos = np.unravel_index(np.argmax(recorte), recorte.shape)
        previos = (float(pos[0]), float(pos[1]), recorte.shape[0] / 3)
    x, y, s = ajuste_gaussiano(recorte, *previos)
    # control propio (takyaq no lo hace): centro fuera de la ROI o sigma mayor que la ROI = no hay punto
    if (np.isnan(x) or not (0 <= x < recorte.shape[0] and 0 <= y < recorte.shape[1])
            or abs(s) > max(recorte.shape)):
        return None
    return {"x": float(c0 + y), "y": float(f0 + x),  # x de la imagen = columna; y = fila
            "sigma": float(abs(s)), "pico": float(recorte.max()),
            "saturado": bool(recorte.max() >= 2 ** BITS[formato] - 1),
            "roi": roi, "params": (float(x), float(y), float(s))}


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
