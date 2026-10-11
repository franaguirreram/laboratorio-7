"""Clip 02b · STORM simulado: de las luces que parpadean a la posición de cada molécula (~48 s, sin voz).

Complementa a clip02_storm.py (el anillo de 8 moléculas). Acá la muestra es una red de filamentos
(simulada en storm_sim.py: parpadeo al azar, cámara con ruido de Poisson, ajuste gaussiano 2D a cada
mancha), así que lo que se ve no está dibujado a mano: cada punto verde es una localización real
de la simulación (≈10 nm de precisión medida contra la posición verdadera).

Escenas:  título · el problema (todo encendido = borrón) · parpadeo → puntos → acumulación
          · ejemplos reales (diapositivas 24-26 de la charla de L. Lopez) · cierre.
Colores de la serie: celeste = cámara, verde = localización, amarillo = pregunta/atención.

Render:  ~/.venvs/manim/bin/manim -qh --media_dir ~/.cache/manim-lab7 clip02b_storm_simulado.py StormSimulado < /dev/null
"""
import numpy as np
from manim import *

from estilo import *
import storm_datos as sd
from storm_sim import NFRAMES, FOV

D = sd.cargar()
ACUM = sd.Acumulador(D)

S = 5.6                      # lado de los cuadros grandes (unidades de Manim)
CENTRO_IZQ = LEFT * 3.5 + UP * 0.35


def punto(c, lado, x, y):
    """Posición en pantalla de (x, y) µm dentro de un cuadro de lado `lado` centrado en c."""
    return c + np.array([(x - FOV / 2) * lado / FOV, -(y - FOV / 2) * lado / FOV, 0])


def imagen_px(arr, color, ancho, c, gamma=0.8, vmax=None, nitido=False, op=1.0):
    m = imagen(arr, color, gamma=gamma, vmax=vmax).set_width(ancho).move_to(c)
    if nitido:
        m.set_resampling_algorithm(RESAMPLING_ALGORITHMS["nearest"])
    return m.set_opacity(op)


def cuadro_cam(f, color=PIXEL):
    return D.frame_img(f), dict(vmax=82.0, nitido=True)


def op_leyenda(t, t0, t1):
    return float(min(sd.ramp(t, t0, t0 + 0.3), sd.ramp(t1 - t, 0, 0.3)))


def leyenda(texto, t0, t1, tt, color=WHITE):
    m = Tex(r"\mbox{" + texto + "}", font_size=30, color=color).to_edge(DOWN, buff=0.35)
    if m.width > 12.8:
        m.scale_to_fit_width(12.8)
    m.add_updater(lambda mm: mm.set_opacity(op_leyenda(tt.get_value(), t0, t1)))
    m.set_opacity(0)
    return m


def marco(c, lado):
    return Square(lado, stroke_color=GRIS, stroke_width=2).move_to(c)


class StormSimulado(Scene):
    # ------------------------------------------------------------------ título
    def titulo_inicial(self):
        t = Tex(r"\textbf{STORM}", font_size=150)
        sub = Tex(r"cómo recuperar posiciones a partir de luces que parpadean", font_size=34, color=GRIS)
        sub.next_to(t, DOWN, 0.5)
        self.play(FadeIn(t, shift=0.15 * UP), run_time=0.8)
        self.play(FadeIn(sub), run_time=0.7)
        self.wait(1.4)
        self.play(FadeOut(VGroup(t, sub)), run_time=0.6)

    # ---------------------------------------------------------------- problema
    def problema(self, T=9.0):
        tt = ValueTracker(0)
        c = CENTRO_IZQ
        cz = RIGHT * 3.4 + UP * 0.6
        lz = 4.4
        wf = D.wf
        x0, x1, y0, y1 = sd.BOX
        izq_wf = imagen_px(wf, PIXEL, S, c, gamma=1.0, vmax=1.0)
        izq_osc = imagen_px(D.frame_img(0), PIXEL, S, c, vmax=82.0, nitido=True, op=0)
        izq_wf.add_updater(lambda m: m.set_opacity(1 - sd.ramp(tt.get_value(), 6.4, 8.0)))
        izq_osc.add_updater(lambda m: m.set_opacity(sd.ramp(tt.get_value(), 6.4, 8.0)))
        zoom = imagen_px(D.zoom_wf(), PIXEL, lz, cz, gamma=1.0, vmax=1.0)
        zoom.add_updater(lambda m: m.set_opacity(1 - sd.ramp(tt.get_value(), 6.4, 8.0)))
        caja_w = (x1 - x0) * S / FOV
        caja = DashedVMobject(Rectangle(width=caja_w, height=caja_w, stroke_color=WHITE, stroke_width=2).move_to(
            punto(c, S, (x0 + x1) / 2, (y0 + y1) / 2)), num_dashes=40)
        marco_z = DashedVMobject(Square(lz, stroke_color=WHITE, stroke_width=2).move_to(cz), num_dashes=60)
        for m in (caja, marco_z):
            m.add_updater(lambda mm: mm.set_opacity(1 - sd.ramp(tt.get_value(), 6.4, 8.0)))
        lbl = Tex("campo amplio: todas las moléculas encendidas", font_size=26, color=GRIS).next_to(marco(c, S), DOWN, 0.15)
        lbl_z = Tex("zoom de 1 $\\mu$m", font_size=26, color=GRIS).next_to(marco_z, UP, 0.15)
        pregunta = Tex(r"¿cuántos filamentos hay acá?", font_size=40, color=FOTON).next_to(marco_z, DOWN, 0.3)
        pregunta.add_updater(lambda m: m.set_opacity(sd.ramp(tt.get_value(), 3.6, 4.4) * (1 - sd.ramp(tt.get_value(), 6.2, 6.8))))
        pregunta.set_opacity(0)
        for m in (lbl, lbl_z):
            m.add_updater(lambda mm: mm.set_opacity(1 - sd.ramp(tt.get_value(), 6.4, 8.0)))
        barra = barra_escala(1000, FOV * 1000 / S, r"1 $\mu$m").move_to(c + np.array([-S / 2 + 1.0, -S / 2 + 0.45, 0]))
        barra_z = barra_escala(200, 1000 * (x1 - x0) * 1000 / (1000 * lz), "200 nm").scale(0.8).move_to(
            cz + np.array([-lz / 2 + 0.75, -lz / 2 + 0.4, 0]))
        barra_z.add_updater(lambda m: m.set_opacity(1 - sd.ramp(tt.get_value(), 6.4, 8.0)))
        caps = [leyenda(r"Con todo encendido, cada molécula es una mancha de $\sim$260 nm: el límite de difracción.", 0.3, 3.7, tt),
                leyenda("Estructuras más cercanas que eso se funden en un solo borrón.", 3.8, 6.2, tt),
                leyenda("El truco: apagar casi todas las moléculas y dejar que prendan al azar, de a pocas.", 6.6, 9.2, tt)]
        self.add(izq_wf, izq_osc, marco(c, S), zoom, marco_z, caja, lbl, lbl_z, pregunta, barra, barra_z, *caps)
        self.play(tt.animate.set_value(T), run_time=T, rate_func=linear)
        self.play(FadeOut(Group(*self.mobjects)), run_time=0.4)
        self.clear()

    # --------------------------------------------- parpadeo → puntos → acumulación
    def parpadeo_y_acumulacion(self, T1=9.0, T2=12.0):
        dur = T1 + T2
        NF = NFRAMES
        TA, TB = 4.5, 5.7                # fin del parpadeo solo / fin del desplazamiento de paneles
        f_a = 3.3 * TA
        tt = ValueTracker(0)

        def f_of(t):
            if t < TA:
                return 3.3 * t
            tau = min(t, T1) - TA
            f1 = f_a + 6 * tau + 4.2 * tau ** 2
            if t < T1:
                return f1
            r0 = 6 + 8.4 * (T1 - TA)
            te = T2 - 2.2
            u = min(t - T1, te)
            return f1 + r0 * u + (NF - 1 - f1 - r0 * te) * (u / te) ** 2.2

        def fotograma():
            return min(int(f_of(tt.get_value())), NF - 1)

        cam_c = lambda mv: np.array([0 + (3.55 - 0) * mv, 0.35 + (0.85 - 0.35) * mv, 0])
        cam_w = lambda mv: S + (3.5 - S) * mv
        mv_ = lambda: sd.ramp(tt.get_value(), TA, TB)

        def camara():
            mv, f = mv_(), fotograma()
            a = min(1.0, tt.get_value() / 0.4)
            arr, kw = cuadro_cam(f)
            return imagen_px(arr, PIXEL, cam_w(mv), cam_c(mv), op=a, **kw)

        def marco_cam():
            mv = mv_()
            return marco(cam_c(mv), cam_w(mv))

        def circulos():
            mv, f = mv_(), fotograma()
            w = cam_w(mv)
            g = VGroup()
            for x, y in D.locs_in(f):
                if 0 < x < FOV and 0 < y < FOV:
                    g.add(Circle(radius=0.30 * w / S + 0.04, stroke_color=ESTIMA, stroke_width=3).move_to(punto(cam_c(mv), w, x, y)))
            return g

        def barra_cam():
            mv = mv_()
            w = cam_w(mv)
            b = barra_escala(1000, FOV * 1000 / w, r"1 $\mu$m").scale(0.8 if mv > 0.5 else 1.0)
            return b.move_to(cam_c(mv) + np.array([-w / 2 + 0.95 * w / S + 0.1, -w / 2 + 0.45 * w / S + 0.05, 0]))

        def recon():
            ACUM.hasta(fotograma())
            m = imagen_px(ACUM.array(), ESTIMA, S, CENTRO_IZQ, gamma=1.0, vmax=1.0)
            return m.set_opacity(sd.ramp(tt.get_value(), TA + 0.3, TA + 1.2))

        def marco_rec():
            m = marco(CENTRO_IZQ, S)
            return m.set_stroke(opacity=sd.ramp(tt.get_value(), TA + 0.3, TA + 1.2))

        def barra_rec():
            b = barra_escala(1000, FOV * 1000 / S, r"1 $\mu$m")
            b.move_to(CENTRO_IZQ + np.array([-S / 2 + 1.0, -S / 2 + 0.45, 0]))
            return b.set_opacity(sd.ramp(tt.get_value(), TA + 0.3, TA + 1.2))

        lbl_rec = Tex("reconstrucción: cada punto es una posición localizada", font_size=26, color=GRIS)
        lbl_rec.next_to(marco(CENTRO_IZQ, S), DOWN, 0.15)
        lbl_rec.add_updater(lambda m: m.set_opacity(sd.ramp(tt.get_value(), TA + 0.5, TA + 1.2)))
        lbl_cam = Tex("lo que ve la cámara", font_size=26, color=GRIS).move_to(np.array([3.55, 2.85, 0]))
        lbl_cam.add_updater(lambda m: m.set_opacity(mv_()))

        # contadores (aparecen cuando la cámara se corre a la derecha)
        cuadro_t = Tex("cuadro", font_size=30, color=GRIS)
        cuadro_n = always_redraw(lambda: Integer(fotograma() + 1, font_size=34, color=GRIS, group_with_commas=False)
                                 .next_to(cuadro_t, RIGHT, 0.2))
        de_t = always_redraw(lambda: Tex(rf"/ {NF}", font_size=30, color=GRIS).next_to(cuadro_n, RIGHT, 0.15))
        grupo_cuadro = VGroup(cuadro_t).move_to(np.array([2.6, -1.25, 0]))
        n_loc = always_redraw(lambda: Integer(int(D.start[fotograma() + 1]), font_size=62, color=ESTIMA,
                                              group_with_commas=False).move_to(np.array([3.55, -2.0, 0])))
        lbl_n = Tex("localizaciones", font_size=28, color=GRIS).move_to(np.array([3.55, -2.65, 0]))
        barra_t = always_redraw(lambda: Rectangle(width=max(1e-3, 3.5 * fotograma() / NF), height=0.07, stroke_width=0,
                                                  fill_color=ESTIMA, fill_opacity=mv_()).align_to(np.array([1.8, 0, 0]), LEFT)
                                .move_to(np.array([1.8 + max(1e-3, 3.5 * fotograma() / NF) / 2, -3.05, 0])))
        for m in (cuadro_t, lbl_n):
            m.add_updater(lambda mm: mm.set_opacity(mv_()))
        for m in (cuadro_n, de_t, n_loc):
            m.add_updater(lambda mm: mm.set_opacity(mv_()))

        caps = [leyenda("Las moléculas se prenden y se apagan solas, al azar.", 0.3, 4.2, tt),
                leyenda("Cada vez que una se enciende se ubica su posición, y queda un punto.", 4.8, T1 - 0.3, tt),
                leyenda("Se repite miles de veces, con moléculas distintas encendiéndose al azar.", T1 + 0.3, T1 + 5.2, tt),
                leyenda("Los puntos se acumulan y dibujan la estructura con detalle nanométrico.", T1 + 5.5, dur - 0.5, tt)]
        self.add(always_redraw(recon), always_redraw(marco_rec), always_redraw(barra_rec), lbl_rec,
                 always_redraw(camara), always_redraw(marco_cam), always_redraw(circulos), always_redraw(barra_cam),
                 lbl_cam, grupo_cuadro, cuadro_n, de_t, n_loc, lbl_n, barra_t, *caps)
        self.play(tt.animate.set_value(dur), run_time=dur, rate_func=linear)
        self.play(FadeOut(Group(*self.mobjects)), run_time=0.5)
        self.clear()

    # ------------------------------------------------------ ejemplos reales
    def ejemplos(self):
        slides = sd.diapositivas()
        items = [(slides[24], r"Un tripanosomátido en 2 colores (mucinas y trans-sialidasas): límite de difracción vs. STORM", 3.8),
                 (slides[25], "Microtúbulos en neuronas, STORM 3D: el color indica la altura z", 3.6),
                 (slides[26], r"Axones de neuronas ($\beta$2-espectrina), 3D-STORM: la organización periódica del citoesqueleto", 3.8)]
        for arr, texto, dur in items:
            im = ImageMobject(arr)
            im.set_resampling_algorithm(RESAMPLING_ALGORITHMS["cubic"])
            h, w = arr.shape[:2]
            ancho = min(12.4, 5.9 * w / h)
            im.set_width(ancho).move_to(UP * 0.3)
            cap = Tex(r"\mbox{" + texto + "}", font_size=30).to_edge(DOWN, buff=0.35)
            if cap.width > 12.8:
                cap.scale_to_fit_width(12.8)
            self.play(FadeIn(im), FadeIn(cap), run_time=0.5)
            self.wait(dur - 1.0)
            self.play(FadeOut(im), FadeOut(cap), run_time=0.5)

    # ---------------------------------------------------------------- cierre
    def cierre(self):
        t = Tex(r"\textbf{STORM}", font_size=150)
        self.play(FadeIn(t, shift=0.15 * UP), run_time=0.7)
        self.wait(1.7)
        self.play(FadeOut(t), run_time=0.6)

    def construct(self):
        self.titulo_inicial()
        self.problema()
        self.parpadeo_y_acumulacion()
        self.ejemplos()
        self.cierre()
