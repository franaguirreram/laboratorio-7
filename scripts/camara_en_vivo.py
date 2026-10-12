"""Video en vivo de la cámara con controles. No mueve la platina.

clic en la imagen: mueve la ROI del ajuste ahí; tecla r: la centra en el máximo.

Uso (desde la raíz del repo, con el entorno ~/python-envs/pi):
    python scripts/camara_en_vivo.py --listar-formatos
    python scripts/camara_en_vivo.py                       # Mono8, 30 fps
    python scripts/camara_en_vivo.py --formato Mono12 --fps 60
    python scripts/camara_en_vivo.py --simular             # sin cámara, para probar

Pensado para el paso "láser + espejo en el portamuestras": marca el punto más
brillante con una cruz y avisa si está saturado. Para ajustar foco, mirá que
el pico suba y el ancho del punto baje.
"""
import argparse
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.widgets import Slider, Button

from camara_aravis import abrir_camara, localizar_punto, roi_en_maximo, BITS

REPO = Path(__file__).resolve().parent.parent


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--formato", default="Mono8", help="Mono8 (defecto), Mono10, Mono12, Mono16")
    p.add_argument("--fps", type=float, default=30.0)
    p.add_argument("--exposicion-us", type=float, default=5000.0)
    p.add_argument("--ganancia", type=float, default=0.0)
    p.add_argument("--roi-radio", type=int, default=30, help="semilado de la ROI del ajuste, en píxeles")
    p.add_argument("--salida", type=Path, default=REPO / "datos" / "camara")
    p.add_argument("--listar-formatos", action="store_true")
    p.add_argument("--simular", action="store_true")
    a = p.parse_args()

    cam = abrir_camara(a.simular)
    if a.listar_formatos:
        print("formatos que ofrece la cámara:", cam.formatos_disponibles())
        print("límites:", cam.limites())
        return

    # configuración inicial (el formato se fija antes de iniciar el flujo)
    cam.set_formato(a.formato)
    lim = cam.limites()
    cam.set_exposicion_us(a.exposicion_us)
    cam.set_ganancia(a.ganancia)
    cam.set_fps(a.fps)
    cam.iniciar()
    print("cámara:", cam.info())

    # ---- ventana: imagen arriba, sliders abajo
    fig = plt.figure(figsize=(9, 8))
    ax = fig.add_axes([0.05, 0.28, 0.9, 0.68])
    primero = None
    while primero is None:  # esperar el primer cuadro para conocer el tamaño
        primero = cam.cuadro(1.0)
    vmax = 2 ** BITS[a.formato] - 1
    im = ax.imshow(primero[0], cmap="gray", vmin=0, vmax=vmax, interpolation="nearest")
    cruz, = ax.plot([], [], "r+", ms=18)
    marco = Rectangle((0, 0), 1, 1, fill=False, ec="cyan", lw=1)  # ROI del ajuste
    ax.add_patch(marco)
    texto = ax.text(0.01, 0.99, "", transform=ax.transAxes, va="top", color="yellow",
                    family="monospace", fontsize=9)

    # exposición en escala log (tres décadas se manejan mejor así)
    s_exp = Slider(fig.add_axes([0.15, 0.18, 0.7, 0.03]), "log10 exp [µs]",
                   np.log10(lim["exposicion_us"][0]), np.log10(min(lim["exposicion_us"][1], 1e6)),
                   valinit=np.log10(np.clip(a.exposicion_us, *lim["exposicion_us"])))
    s_gan = Slider(fig.add_axes([0.15, 0.12, 0.7, 0.03]), "ganancia",
                   *lim["ganancia"], valinit=a.ganancia)
    s_fps = Slider(fig.add_axes([0.15, 0.06, 0.7, 0.03]), "fps pedidos",
                   max(lim["fps"][0], 1), min(lim["fps"][1], 160), valinit=a.fps)
    b_foto = Button(fig.add_axes([0.15, 0.005, 0.15, 0.04]), "guardar foto")
    # ROI del ajuste gaussiano, como en takyaq: fija hasta que se recentre
    # (clic en la imagen = centrar ahí; tecla r = centrar en el máximo)
    estado = {"roi": roi_en_maximo(primero[0], a.roi_radio), "previos": None, "fps_max": None, "exp": None, "gan": None, "fps": None, "ultimo": primero[0],
              "t": time.time(), "fid": primero[1], "fps_cam": 0.0, "fps_pant": 0.0, "n": 0}

    # los sliders solo piden; el valor real se lee de vuelta de la cámara
    def al_cambiar_exp(_):
        estado["exp"] = cam.set_exposicion_us(10 ** s_exp.val)
        estado["fps_max"] = cam.limites()["fps"][1]  # el máximo puede bajar al subir la exposición
    def al_cambiar_gan(_):
        estado["gan"] = cam.set_ganancia(s_gan.val)
    def al_cambiar_fps(_):
        estado["fps"] = cam.set_fps(s_fps.val)
    s_exp.on_changed(al_cambiar_exp); s_gan.on_changed(al_cambiar_gan); s_fps.on_changed(al_cambiar_fps)
    al_cambiar_exp(0); al_cambiar_gan(0); al_cambiar_fps(0)

    def guardar(_):  # guarda el último cuadro tal cual (sin escalar) y su metadata
        a.salida.mkdir(parents=True, exist_ok=True)
        base = a.salida / datetime.now().strftime("vivo_%Y%m%d_%H%M%S")
        np.save(base.with_suffix(".npy"), estado["ultimo"])
        base.with_suffix(".txt").write_text(str(cam.info()) + "\n")
        print("guardado:", base)
    b_foto.on_clicked(guardar)

    def centrar(f, c):
        r = a.roi_radio
        h, w = estado["ultimo"].shape
        estado["roi"] = (max(int(f) - r, 0), min(int(f) + r + 1, h), max(int(c) - r, 0), min(int(c) + r + 1, w))
        estado["previos"] = None  # nuevo ajuste desde cero

    def al_clic(ev):
        if ev.inaxes is ax and ev.xdata is not None and (fig.canvas.toolbar is None or fig.canvas.toolbar.mode == ""):  # no mover la ROI si hay zoom/pan activo
            centrar(ev.ydata, ev.xdata)

    def al_tecla(ev):
        if ev.key == "r":
            estado["roi"], estado["previos"] = roi_en_maximo(estado["ultimo"], a.roi_radio), None
    fig.canvas.mpl_connect("button_press_event", al_clic)
    fig.canvas.mpl_connect("key_press_event", al_tecla)

    def actualizar():
        r = cam.cuadro(0.05)  # espera hasta 50 ms; None = no llegó nada
        if r is None:
            return
        img, fid, _ = r
        estado["ultimo"] = img
        ahora = time.time()
        dt = ahora - estado["t"]
        if dt > 0:  # fps de la cámara sale de los frame_id (cuenta los que se descartaron);
            # fps de pantalla = cuántos dibujamos realmente
            estado["fps_cam"] = 0.9 * estado["fps_cam"] + 0.1 * (fid - estado["fid"]) / dt
            estado["fps_pant"] = 0.9 * estado["fps_pant"] + 0.1 / dt
        estado["t"], estado["fid"] = ahora, fid
        im.set_data(img)  # se muestra en la escala nativa del formato (vmax fijo)
        f0, f1, c0, c1 = estado["roi"]
        marco.set_xy((c0, f0)); marco.set_width(c1 - c0); marco.set_height(f1 - f0)
        pt = localizar_punto(img, a.formato, estado["roi"], estado["previos"])
        if pt:
            estado["previos"] = pt["params"]  # valor inicial del próximo ajuste (como takyaq)
            cruz.set_data([pt["x"]], [pt["y"]])
        else:
            cruz.set_data([], [])
            estado["previos"] = None  # reinicia el valor inicial como takyaq._initialize_last_params
        sat = 100 * np.mean(img >= vmax)
        texto.set_text(f"punto: " + (f"x={pt['x']:.2f} y={pt['y']:.2f} sigma={pt['sigma']:.2f} px pico={pt['pico']:.0f}" if pt else "ajuste falló (ROI sin punto?)") +
                       f"\nexp={estado['exp']:.0f} µs  gan={estado['gan']:.1f}  fps cfg={estado['fps']:.1f} (máx {estado['fps_max']:.0f})"
                       f"\nfps cámara={estado['fps_cam']:.1f}  fps pantalla={estado['fps_pant']:.1f}"
                       f"\nsaturados={sat:.2f} %" + ("  ¡SATURADO!" if (pt and pt['saturado']) else ""))
        fig.canvas.draw_idle()

    timer = fig.canvas.new_timer(interval=1)
    timer.add_callback(actualizar)
    timer.start()
    try:
        plt.show()
    finally:
        timer.stop()
        cam.cerrar()


if __name__ == "__main__":
    main()
