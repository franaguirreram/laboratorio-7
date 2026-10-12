"""Calibra la escala de la cámara (px por µm) moviendo la platina un eje.

Secuencia: foto de referencia en la posición inicial -> N pasos en un eje ->
en cada punto se espera, se lee la posición MEDIDA y se toman fotos ->
se ajusta una recta (desplazamiento en px) vs (posición medida en µm).

Uso (desde la raíz del repo, entorno ~/python-envs/pi):
    python scripts/calibrar_escala_camara.py --simular              # prueba sin hardware
    python scripts/calibrar_escala_camara.py --paso-um 1 --n-pasos 10 --ida-vuelta

IMPORTANTE (INFERENCIA, a confirmar en la mesa): un espejo plano que se
traslada en su propio plano NO mueve el punto láser reflejado, porque la
luz vuelve por el mismo camino. Para ver desplazamiento hace falta algo con
estructura en la muestra (reticula, polvo, un rayón, microesferas). Con
estructura usar --metodo correlacion; con un punto aislado, --metodo punto.
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from camara_aravis import (abrir_camara, localizar_punto, desplazamiento_correlacion,
                           PASO_PIXEL_UM, BITS)

REPO = Path(__file__).resolve().parent.parent
RANGO_UM = (0.0, 200.0)  # igual que E517_barrido.py (medido en el eje A)
MARGEN_UM = 1.0          # no comandar más cerca que esto de los topes


class PlatinaPI:
    """Mover y esperar, nada más. Usa la conexión de E517_barrido."""

    def __init__(self):
        from E517_barrido import conectar  # import tardío: necesita pipython y el gateway
        self.pidevice, _ = conectar()

    def posicion(self, eje):
        return float(self.pidevice.qPOS(eje)[eje])  # posición medida por el sensor

    def mover(self, eje, um):
        from pipython import pitools
        self.pidevice.MOV([eje], [um])
        pitools.waitontarget(self.pidevice, [eje], timeout=15)  # espera "on target"

    def cerrar(self):
        from E517_barrido import cerrar
        cerrar(self.pidevice)


class PlatinaSimulada:
    """Platina falsa: la posición medida difiere de la pedida en ~2 nm."""

    def __init__(self, camara, px_por_um=17.0, angulo_deg=3.0):
        self.cam, self.pos = camara, {"A": 100.0, "B": 100.0}
        self.px_por_um, self.ang = px_por_um, np.deg2rad(angulo_deg)
        self.centro = camara.punto_xy
        self._rng = np.random.default_rng(1)
        # estructura de fondo para poder probar el método de correlación
        camara.textura = lambda x, y, x0, y0: 60 * np.exp(-((x - x0 - 150) ** 2 + (y - y0 + 90) ** 2) / (2 * 15.0 ** 2))

    def posicion(self, eje): return self.pos[eje] + self._rng.normal(0, 0.002)

    def mover(self, eje, um):
        self.pos[eje] = um
        d = (um - 100.0) * self.px_por_um  # la imagen se desplaza en proporción
        sx, sy = (np.cos(self.ang), np.sin(self.ang)) if eje == "A" else (-np.sin(self.ang), np.cos(self.ang))
        self.cam.punto_xy = (self.centro[0] + d * sx, self.centro[1] + d * sy)

    def cerrar(self): pass


def medir_punto(cam, formato, n_fotos, descartar, metodo, ref):
    """Toma fotos en el punto actual; devuelve (x_px, y_px, ruido_px, ultima_imagen)."""
    for _ in range(descartar):  # cuadros que pueden ser previos al movimiento
        cam.cuadro(2.0)
    xs, ys, ultima = [], [], None
    for _ in range(n_fotos):
        r = cam.cuadro(2.0)
        if r is None:
            raise RuntimeError("la cámara no entregó cuadro; revisar conexión/exposición")
        ultima = r[0]
        if metodo == "punto":
            pt = localizar_punto(ultima, formato)
            if pt is None:
                raise RuntimeError("no encontré el punto en la imagen")
            if pt["saturado"]:
                print("   aviso: punto saturado, el centroide pierde exactitud; bajar exposición")
            xs.append(pt["x"]); ys.append(pt["y"])
        else:
            dx, dy = desplazamiento_correlacion(ref, ultima)
            xs.append(dx); ys.append(dy)
    ruido = float(np.hypot(np.std(xs), np.std(ys)))
    return float(np.mean(xs)), float(np.mean(ys)), ruido, ultima


def ajuste_recta(x, y):
    """Pendiente, ordenada, incertidumbre de la pendiente y rms de residuos (mínimos cuadrados)."""
    x, y = np.asarray(x), np.asarray(y)
    A = np.vstack([x, np.ones_like(x)]).T
    (m, b), *_ = np.linalg.lstsq(A, y, rcond=None)
    res = y - (m * x + b)
    n = len(x)
    s_m = np.sqrt(res.var(ddof=2) / np.sum((x - x.mean()) ** 2)) if n > 2 else float("nan")
    return float(m), float(b), float(s_m), float(np.sqrt(np.mean(res ** 2)))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--eje", choices=["A", "B"], default="A")  # el rango de B se asume igual al de A (INFERENCIA)
    p.add_argument("--paso-um", type=float, default=1.0)
    p.add_argument("--n-pasos", type=int, default=10)
    p.add_argument("--ida-vuelta", action="store_true", help="vuelve por los mismos puntos (detecta histéresis)")
    p.add_argument("--metodo", choices=["punto", "correlacion"], default="correlacion")
    p.add_argument("--fotos-por-punto", type=int, default=5)
    p.add_argument("--descartar", type=int, default=3, help="cuadros que se tiran tras cada movimiento")
    p.add_argument("--asentamiento-s", type=float, default=0.5)
    p.add_argument("--formato", default="Mono8")
    p.add_argument("--exposicion-us", type=float, default=5000.0)
    p.add_argument("--ganancia", type=float, default=0.0)
    p.add_argument("--salida", type=Path, default=REPO / "datos" / "camara")
    p.add_argument("--simular", action="store_true")
    a = p.parse_args()

    cam = abrir_camara(a.simular)
    cam.set_formato(a.formato)
    cam.set_exposicion_us(a.exposicion_us)
    cam.set_ganancia(a.ganancia)
    cam.set_fps(30.0)
    cam.iniciar()
    platina = PlatinaSimulada(cam) if a.simular else PlatinaPI()

    carpeta = a.salida / datetime.now().strftime("escala_%Y%m%d_%H%M%S")
    carpeta.mkdir(parents=True, exist_ok=True)
    inicio = platina.posicion(a.eje)
    ida = [inicio + k * a.paso_um for k in range(a.n_pasos + 1)]
    objetivos = ida + (ida[-2::-1] if a.ida_vuelta else [])
    lo, hi = RANGO_UM[0] + MARGEN_UM, RANGO_UM[1] - MARGEN_UM
    if not all(lo <= t <= hi for t in objetivos):  # se valida TODO antes de mover
        raise SystemExit(f"hay posiciones fuera de [{lo}, {hi}] µm: {min(objetivos):.2f}..{max(objetivos):.2f}")
    print(f"inicio {inicio:.4f} µm, {len(objetivos)} puntos, paso {a.paso_um} µm, método {a.metodo}")

    filas, imagenes, ref = [], [], None
    try:
        for i, objetivo in enumerate(objetivos):
            platina.mover(a.eje, objetivo)
            time.sleep(a.asentamiento_s)  # deja que se amortigüe tras llegar
            medida = platina.posicion(a.eje)  # se usa la posición MEDIDA, no la pedida
            if i == 0:  # la referencia es la foto del primer punto
                for _ in range(a.descartar):
                    cam.cuadro(2.0)
                ref = cam.cuadro(2.0)[0]
            x, y, ruido, img = medir_punto(cam, a.formato, a.fotos_por_punto, a.descartar, a.metodo, ref)
            imagenes.append(img)
            filas.append((i, objetivo, medida, x, y, ruido))
            print(f"  {i:2d}  pedida {objetivo:9.4f}  medida {medida:9.4f} µm   u={x:9.3f} v={y:9.3f} px   ruido {ruido:.3f} px")
    finally:
        try:
            platina.mover(a.eje, inicio)  # vuelve al punto inicial pase lo que pase
        finally:
            platina.cerrar()
            cam.cerrar()

    d = np.array(filas)
    x_um = d[:, 2] - d[0, 2]  # desplazamiento medido respecto de la referencia
    u, v = d[:, 3], d[:, 4]
    if a.metodo == "punto":  # el centroide es posición absoluta; la correlación ya es relativa
        u, v = u - u[0], v - v[0]
    su, _, eu, ru = ajuste_recta(x_um, u)
    sv, _, ev, rv = ajuste_recta(x_um, v)
    px_um = float(np.hypot(su, sv))
    res = {
        "eje": a.eje, "metodo": a.metodo, "n_puntos": len(d),
        "du_dx_px_por_um": su, "dv_dx_px_por_um": sv,
        "incertidumbre_pendiente_u": eu, "incertidumbre_pendiente_v": ev,
        "escala_px_por_um": px_um, "um_por_px": 1 / px_um if px_um else None,
        "angulo_deg": float(np.degrees(np.arctan2(sv, su))),
        "rms_residuo_px": [ru, rv],
        # M = paso de pixel (5.86 µm, ficha IDS) * px/µm; vale si no hay binning
        "aumento_total_estimado": PASO_PIXEL_UM * px_um,
        "formato": a.formato, "camara": cam.info(),
    }
    np.savetxt(carpeta / "puntos.csv", d, delimiter=",", comments="",
               header="i,pos_pedida_um,pos_medida_um,u_px,v_px,ruido_px")
    np.save(carpeta / "imagenes.npy", np.array(imagenes))
    (carpeta / "resultado.json").write_text(json.dumps(res, indent=2, default=float) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "camara"}, indent=2, default=float))
    print("guardado en", carpeta)
    print("revisar: rms de residuo vs ruido por punto; si el recorrido es chico "
          "(pocos px) la pendiente queda mal determinada.")


if __name__ == "__main__":
    main()
