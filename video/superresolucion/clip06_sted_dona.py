"""Clip 06 · STED paso a paso: del borrón a la dona (~45 s, sin voz).

Escena 1  Cinco moléculas a ~50 nm. La excitación (~250 nm) las enciende a todas
          juntas: un borrón. Llega la dona de depleción y apaga a las que quedan
          bajo el anillo; solo brilla la del centro oscuro.
Escena 2  Al subir la potencia de la dona el anillo se engruesa y el hueco se achica:
          la mancha de fluorescencia efectiva pasa de 250 nm a unas decenas de nm.
Escena 3  El punto efectivo barre la muestra en trama (raster) y la imagen borrosa se
          va reemplazando, línea a línea, por la imagen STED.

Física: excitación gaussiana de FWHM 250 nm; dona I ∝ (r/ρ)² e^{-r²/ρ²} con ρ = 150 nm;
la fluorescencia que sobrevive es exc(r) · exp(-ln2 · (I/I_s) · dona(r)).
Todos los números son ilustrativos (ver PLAN.md).

Render:  manim -qh --media_dir ~/.cache/manim-lab7 clip06_sted_dona.py StedDona < /dev/null
"""
import numpy as np
from manim import *
from scipy.ndimage import gaussian_filter

from estilo import *

FLUO = ESTIMA                       # fluorescencia = verde

# ---------- física (nm) ----------
FWHM_EXC = 250.0
SIG_EXC = FWHM_EXC / 2.3548
RHO = 150.0                         # radio del máximo de la dona
SIG_DET = 50.0                      # halo con que se ve el brillo de una molécula
LN2 = np.log(2)

MOLS = np.array([(-92, 26), (-46, -24), (0, 0), (46, 30), (92, -18)], dtype=float)   # ~50 nm entre vecinas


def exc(r2):
    return np.exp(-r2 / (2 * SIG_EXC ** 2))


def perfil_dona(r2):
    u = r2 / RHO ** 2
    return u * np.exp(1 - u)


def eta(r2, z):
    """Probabilidad de NO ser apagada por la dona; z = I_STED / I_sat."""
    return np.exp(-LN2 * z * perfil_dona(r2))


def fwhm_efectivo(z):
    x = np.linspace(0, 200, 4001)
    f = exc(x ** 2) * eta(x ** 2, z)
    return 2 * x[np.argmax(f < 0.5)]


def rgb(c):
    return np.array(ManimColor(c).to_rgb())


C_EXC, C_STED, C_FLUO, C_CEN = rgb(EXCITA), rgb(STED), rgb(FLUO), rgb(FOTON)
CEN = 2                             # índice de la molécula del medio (resaltada en amarillo)

# ---------- vista de las escenas 1 y 2 ----------
ESC = 0.0135                        # unidades de pantalla por nm
R_FOV = 2.945                        # radio del campo de visión (pantalla)
CENTRO = LEFT * 2.9 + DOWN * 0.15
PANEL_X = 0.95                      # borde izquierdo del panel de texto


def campo(z, a_exc, a_em, mezcla):
    """Imagen RGBA del campo: excitación (azul) + dona (naranja) + fluorescencia (verde).

    mezcla = 0: brillo de las moléculas (halos). mezcla = 1: mancha efectiva exc·η.
    """
    n = 180
    w = 2 * R_FOV
    xs = ((np.arange(n) + 0.5) / n * w - w / 2)
    ys = -xs
    X, Y = np.meshgrid(xs / ESC, ys / ESC)
    r2 = X ** 2 + Y ** 2

    azul = a_exc * exc(r2) * 0.85
    d = perfil_dona(r2)
    naranja = (1 - eta(r2, z)) * np.exp(-(r2 / (1.15 * RHO) ** 2) ** 2)   # zona apagada: borde interno = luz verde

    g, g_cen = 0, 0
    for i, (mx, my) in enumerate(MOLS):
        amp = a_em * exc(mx ** 2 + my ** 2) * eta(mx ** 2 + my ** 2, z)
        h = amp * np.exp(-((X - mx) ** 2 + (Y - my) ** 2) / (2 * SIG_DET ** 2))
        if i == CEN:
            g_cen = g_cen + h
        else:
            g = g + h
    halos = 1 - np.exp(-1.4 * g)
    halo_cen = 1 - np.exp(-2.2 * g_cen)
    efectiva = a_em * exc(r2) * eta(r2, z)
    verde = (1 - mezcla) * halos + mezcla * efectiva
    amarillo = (1 - mezcla) * halo_cen

    mix = (azul[..., None] * C_EXC + naranja[..., None] * C_STED + verde[..., None] * C_FLUO
           + amarillo[..., None] * C_CEN)
    pico = mix.max(-1)
    alfa = np.clip(pico, 0, 1)
    color = np.clip(mix / np.maximum(pico, 1e-6)[..., None], 0, 1)
    rr = np.sqrt((X * ESC) ** 2 + (Y * ESC) ** 2)
    vig = np.clip((R_FOV - rr) / 0.9, 0, 1)
    out = np.dstack([color, alfa * vig])
    img = ImageMobject((out * 255).astype(np.uint8))
    img.set_resampling_algorithm(RESAMPLING_ALGORITHMS["linear"])
    return img.set_height(2 * R_FOV).move_to(CENTRO)


def dona_sola():
    """La dona por sí sola: intensidad real I ∝ (r/ρ)² e^{-r²/ρ²}, cero en el centro. Devuelve (imagen, ρ en pantalla)."""
    n, semi, alto = 160, 2.0 * RHO, 3.0
    x = np.linspace(-semi, semi, n)
    X, Y = np.meshgrid(x, -x)
    r2 = X ** 2 + Y ** 2
    v = perfil_dona(r2)
    vig = np.clip((semi - np.sqrt(r2)) / (0.25 * semi), 0, 1)
    out = np.dstack([np.tile(C_STED, (n, n, 1)), v * vig])
    img = ImageMobject((out * 255).astype(np.uint8))
    img.set_resampling_algorithm(RESAMPLING_ALGORITHMS["linear"])
    return img.set_height(alto), RHO / semi * alto / 2


def a_pantalla(p_nm):
    return CENTRO + np.array([p_nm[0] * ESC, p_nm[1] * ESC, 0])


def panel(*lineas, y=0.5):
    """Bloque de texto alineado a la izquierda; cada línea es (texto, color) o solo texto."""
    g = VGroup(*[Tex(l[0] if isinstance(l, tuple) else l, font_size=38,
                     color=l[1] if isinstance(l, tuple) else WHITE) for l in lineas])
    g.arrange(DOWN, aligned_edge=LEFT, buff=0.2)
    return g.move_to(np.array([PANEL_X, y, 0]), aligned_edge=LEFT)


# ---------- estructura de la escena 3 (nm) ----------
S3 = 0.021375                        # unidades de pantalla por nm
ANCHO3, ALTO3 = 11.4, 5.7
W_NM, H_NM = ANCHO3 / S3, ALTO3 / S3
PX_NM = 2.25                        # píxeles por nm
NX, NY = round(W_NM * PX_NM), round(H_NM * PX_NM)
FILAS = 20
FILA_PX = NY // FILAS
FWHM_STED_FINAL = 20.0
CENTRO3 = DOWN * 0.15


def estructura():
    """Dos filamentos paralelos a 55 nm, un anillo de 100 nm y un trío de moléculas a 45 nm."""
    rng = np.random.default_rng(3)
    pts = []
    for x in np.arange(-240, 241, 4.0):
        y = 70 + 30 * np.sin(x / 75)
        pts += [(x, y), (x, y - 55)]
    for a in np.arange(0, 2 * np.pi, 0.07):
        pts.append((130 + 50 * np.cos(a), -70 + 50 * np.sin(a)))
    for cx, cy in [(-190, -70), (-145, -70), (-168, -108)]:
        pts += [(cx, cy)] * 12
    pts = np.array(pts) + rng.normal(0, 2.0, (len(pts), 2))
    h, _, _ = np.histogram2d(-pts[:, 1], pts[:, 0], bins=[NY, NX],
                             range=[[-H_NM / 2, H_NM / 2], [-W_NM / 2, W_NM / 2]])
    return h


def a_rgba(v, realce=1.0):
    v = np.clip((v - v.min()) / (np.percentile(v, 99.7) - v.min()), 0, 1) ** realce
    t = (v ** 3 * 0.55)[..., None]
    color = C_FLUO * (1 - t) + t
    return np.dstack([color, v ** 0.9])


def fotos_escena3():
    h = estructura()
    borrosa = gaussian_filter(h, SIG_EXC * PX_NM)
    nitida = gaussian_filter(h, FWHM_STED_FINAL / 2.3548 * PX_NM)
    return (a_rgba(borrosa, 2.2) * 255).astype(np.uint8), (a_rgba(nitida) * 255).astype(np.uint8)


class StedDona(Scene):
    def construct(self):
        self.escena_1()
        self.escena_2()
        self.escena_3()

    # ======================= ESCENA 1 =======================
    def escena_1(self):
        self.z = ValueTracker(0.0)          # I_STED / I_sat
        self.ex = ValueTracker(0.0)         # excitación
        self.em = ValueTracker(0.0)         # emisión (cuánto brillan las moléculas)
        self.mezcla = ValueTracker(0.0)     # 0 = halos de moléculas, 1 = mancha efectiva
        z, ex, em, mezcla = self.z, self.ex, self.em, self.mezcla

        tit = titulo(r"Del borrón de luz a la \textbf{dona}")
        self.play(FadeIn(tit, shift=0.15 * DOWN), run_time=0.8)

        fov = Circle(radius=R_FOV, stroke_color=GRIS, stroke_width=2, stroke_opacity=0.6).move_to(CENTRO)
        puntos_fil = [a_pantalla(m) + np.array([0, 0, 0]) for m in MOLS]
        fil = VMobject(stroke_color=GRIS, stroke_width=3, stroke_opacity=0.4)
        ext = [a_pantalla((-140, 40)), *puntos_fil, a_pantalla((140, -35))]
        fil.set_points_smoothly(ext)

        def brillo(i):
            r2 = float((MOLS[i] ** 2).sum())
            return em.get_value() * exc(r2) * eta(r2, z.get_value())

        dots = VGroup(*[Dot(p, radius=0.075, color=APAGADA, stroke_color=WHITE, stroke_width=1.5, stroke_opacity=0.6)
                        for p in puntos_fil])
        for i, dt in enumerate(dots):
            dt.add_updater(lambda m, i=i: m.set_fill(interpolate_color(
                ManimColor(APAGADA), ManimColor(FOTON if i == CEN else FLUO), min(1.0, brillo(i)))))
        escala = barra_escala(50, 1 / ESC).move_to(CENTRO + LEFT * 2.5 + DOWN * 2.85)

        imagen_campo = always_redraw(lambda: campo(z.get_value(), ex.get_value(), em.get_value(), mezcla.get_value()))
        self.add(imagen_campo)
        self.bring_to_front(fil, dots)
        self.play(Create(fov), FadeIn(fil), FadeIn(dots, scale=0.5), FadeIn(escala), run_time=1.0)
        p1 = panel(("Moléculas fluorescentes", WHITE), ("separadas por ~50 nm", GRIS))
        self.play(FadeIn(p1, shift=0.1 * UP), run_time=0.6)
        self.wait(0.8)

        # --- la excitación: una mancha grande ---
        p2 = panel(("Láser de excitación", EXCITA), ("mancha de ~250 nm", GRIS))
        self.play(ex.animate.set_value(1.0), FadeOut(p1), FadeIn(p2, shift=0.1 * UP), run_time=1.5)
        medida = DoubleArrow(CENTRO + LEFT * 125 * ESC + DOWN * 2.55, CENTRO + RIGHT * 125 * ESC + DOWN * 2.55,
                             buff=0, color=EXCITA, stroke_width=3, tip_length=0.15)
        l_medida = Tex("250 nm", font_size=26, color=EXCITA).next_to(medida, DOWN, 0.08)
        self.play(Create(medida), FadeIn(l_medida), run_time=0.7)
        self.wait(0.5)

        # --- todas brillan a la vez: un borrón ---
        p3 = panel(("Todas brillan a la vez:", FLUO), ("un borrón, no se distingue ninguna", GRIS),
                   ("la del medio, en amarillo", FOTON))
        self.play(em.animate.set_value(1.0), ex.animate.set_value(0.3), FadeOut(p2), FadeIn(p3, shift=0.1 * UP), run_time=1.5)
        aro_a = Circle(radius=0.28, color=FOTON, stroke_width=3).move_to(dots[CEN])
        self.play(Create(aro_a), run_time=0.6)
        self.wait(1.8)

        # --- llega la dona ---
        p4 = panel(("Segundo láser: la dona", STED), ("centro oscuro: intensidad cero", GRIS), y=2.3)
        DONA_C = np.array([3.9, -0.6, 0])
        img_d, rho_u = dona_sola()
        img_d.move_to(DONA_C)
        flecha = Arrow(DONA_C + DOWN * 2.15, DONA_C + DOWN * 0.1, buff=0.02, color=WHITE, stroke_width=3,
                       tip_length=0.15, max_tip_length_to_length_ratio=0.3)
        txt_cero = Tex(r"$I = 0$ en el centro", font_size=30, color=WHITE).next_to(flecha, DOWN, 0.1)
        hueco_c = always_redraw(lambda: DashedVMobject(
            Circle(radius=max(fwhm_efectivo(z.get_value()) / 2 * ESC, 0.06), color=WHITE, stroke_width=3),
            num_dashes=28).move_to(CENTRO))
        # primero la dona sola, con su cero en el centro
        self.play(ex.animate.set_value(0.12), FadeOut(p3), FadeOut(medida), FadeOut(l_medida), FadeOut(aro_a),
                  FadeIn(p4, shift=0.1 * UP), FadeIn(img_d), run_time=1.4)
        self.play(Create(flecha), FadeIn(txt_cero), run_time=0.8)
        self.wait(2.0)
        # y después se suma al dibujo de la izquierda
        self.play(FadeOut(img_d, target_position=CENTRO, scale=RHO * ESC / rho_u), FadeOut(flecha), FadeOut(txt_cero),
                  z.animate.set_value(0.8),
                  FadeIn(hueco_c), FadeOut(p4), run_time=2.0)
        p4b = panel(("La dona rodea al punto", STED), ("y deja el centro sin apagar", GRIS))
        self.play(FadeIn(p4b, shift=0.1 * UP), run_time=0.5)
        self.wait(0.8)

        # --- emisión estimulada: las de abajo del anillo se apagan ---
        p5 = panel(("Emisión estimulada:", STED), ("el anillo apaga a las vecinas", GRIS),
                   ("y el hueco central se cierra", WHITE))
        self.play(z.animate.set_value(4.0), FadeOut(p4b), FadeIn(p5, shift=0.1 * UP), run_time=1.8,
                  rate_func=rate_functions.ease_in_quad)
        flashes = [Flash(dots[i], color=STED, flash_radius=0.4, line_length=0.12, num_lines=10, run_time=0.9)
                   for i in (0, 1, 3, 4)]
        self.play(z.animate.set_value(30.0), LaggedStart(*flashes, lag_ratio=0.2), run_time=3.0,
                  rate_func=rate_functions.ease_out_quad)

        # --- queda una sola ---
        p6 = panel(("Solo brilla la del centro:", FOTON), ("un destello limpio", GRIS))
        aro = Circle(radius=0.28, color=FOTON, stroke_width=3).move_to(dots[CEN])
        self.play(FadeOut(p5), FadeIn(p6, shift=0.1 * UP), Create(aro),
                  run_time=0.9)
        self.wait(1.6)

        self.fov, self.dots, self.fil, self.escala = fov, dots, fil, escala
        self.imagen_campo, self.tit, self.p6, self.aro, self.hueco_c = imagen_campo, tit, p6, aro, hueco_c

    # ======================= ESCENA 2 =======================
    def escena_2(self):
        z, ex, em, mezcla = self.z, self.ex, self.em, self.mezcla
        tit2 = titulo(r"El secreto: la \textbf{intensidad}")

        # el campo pasa de "halos de moléculas" a "dónde puede emitir" y se baja la potencia para repetirlo
        otros = VGroup(self.fil, *[self.dots[i] for i in (0, 1, 3, 4)])
        self.play(ReplacementTransform(self.tit, tit2), FadeOut(self.p6), FadeOut(self.aro), FadeOut(self.hueco_c),
                  otros.animate.set_opacity(0.0), ex.animate.set_value(0.12),
                  mezcla.animate.set_value(1.0), z.animate.set_value(1.0), run_time=1.8)

        d_ref = DashedVMobject(Circle(radius=125 * ESC, color=GRIS, stroke_width=3), num_dashes=40).move_to(CENTRO)
        l_ref = Tex(r"\textit{límite de difracción} 250 nm", font_size=26, color=GRIS).move_to(CENTRO + UP * 2.75)
        efectivo = always_redraw(lambda: Circle(radius=fwhm_efectivo(z.get_value()) / 2 * ESC, color=FLUO,
                                                stroke_width=4).move_to(CENTRO))

        # d marcado sobre el punto de luz: flecha doble con guías verticales
        def marca_d():
            r = fwhm_efectivo(z.get_value()) / 2 * ESC
            y = CENTRO[1] - r - 0.35
            guias = VGroup(*[DashedLine(CENTRO + RIGHT * sx * r, np.array([CENTRO[0] + sx * r, y, 0]),
                                        color=WHITE, stroke_width=2, dash_length=0.06) for sx in (-1, 1)])
            flecha = DoubleArrow(np.array([CENTRO[0] - r, y, 0]), np.array([CENTRO[0] + r, y, 0]), buff=0,
                                 color=WHITE, stroke_width=3, tip_length=min(0.14, 0.6 * r))
            etiqueta = MathTex("d", font_size=40, color=WHITE).next_to(flecha, DOWN, 0.08)
            return VGroup(guias, flecha, etiqueta)
        marca = always_redraw(marca_d)

        # barras: potencia de la dona (sube) y d (baja)
        ANCHO_B = 4.2

        def barra(color, frac, y, texto):
            marco = Rectangle(width=ANCHO_B, height=0.3, stroke_color=color, stroke_width=2)
            marco.move_to(np.array([PANEL_X + ANCHO_B / 2, y, 0]))
            lleno = Rectangle(width=max(frac * ANCHO_B, 0.02), height=0.3, stroke_width=0, fill_color=color,
                              fill_opacity=0.85)
            lleno.align_to(marco, LEFT).align_to(marco, DOWN)
            return VGroup(marco, lleno)

        etq_z = Tex("potencia de la dona", font_size=32, color=STED).move_to(np.array([PANEL_X, 2.55, 0]), aligned_edge=LEFT)
        etq_d = Tex("d: tamaño del punto de luz", font_size=32, color=FLUO).move_to(np.array([PANEL_X, 1.25, 0]),
                                                                                      aligned_edge=LEFT)
        barra_z = always_redraw(lambda: barra(STED, np.log(z.get_value()) / np.log(60), 2.05, ""))
        barra_d = always_redraw(lambda: barra(FLUO, fwhm_efectivo(z.get_value()) / 250.0, 0.75, ""))

        p_a = panel(("Más potencia en la dona:", STED), ("el anillo se engruesa", WHITE),
                    ("y el hueco central se achica", WHITE), y=-1.3)
        self.play(FadeIn(d_ref), FadeIn(l_ref), FadeIn(efectivo), FadeIn(marca), FadeIn(etq_z), FadeIn(etq_d),
                  FadeIn(barra_z), FadeIn(barra_d), FadeIn(p_a, shift=0.1 * UP), run_time=1.0)
        self.wait(0.4)

        # subir la potencia de manera logarítmica: 1 → 60
        self.play(UpdateFromAlphaFunc(z, lambda m, a: m.set_value(60 ** a)), FadeOut(l_ref, rate_func=squish_rate_func(smooth, 0.25, 0.4)),
                  run_time=7.0, rate_func=linear)

        p_b = panel(("Más potencia $\\Rightarrow$ $d$ más chico:", FLUO), ("de 250 nm a unos 20 nm", WHITE),
                    ("una molécula por vez", GRIS), y=-1.3)
        self.play(FadeOut(p_a), FadeIn(p_b, shift=0.1 * UP), Indicate(efectivo, color=FLUO, scale_factor=1.8),
                  run_time=1.4)
        self.wait(2.0)

        for m in (barra_z, barra_d, marca):
            m.clear_updaters()
        efectivo.clear_updaters()
        self.imagen_campo.clear_updaters()
        self.play(*[FadeOut(m) for m in self.mobjects], run_time=0.8)

    # ======================= ESCENA 3 =======================
    def escena_3(self):
        borrosa, nitida = fotos_escena3()
        p = ValueTracker(0.0)

        tit = titulo(r"Escaneo \textbf{nanoscópico}")
        marco = Rectangle(width=ANCHO3, height=ALTO3, stroke_color=GRIS, stroke_width=2).move_to(CENTRO3)

        def frame_img():
            P = p.get_value()
            k = int(min(P, FILAS))
            f = P - k
            out = borrosa.copy()
            out[:k * FILA_PX] = nitida[:k * FILA_PX]
            if k < FILAS:
                c = int(f * NX) if k % 2 == 0 else int((1 - f) * NX)
                a, b = k * FILA_PX, (k + 1) * FILA_PX
                if k % 2 == 0:
                    out[a:b, :c] = nitida[a:b, :c]
                else:
                    out[a:b, c:] = nitida[a:b, c:]
            if anillo[0]:
                x0, y0 = nm_actual()
                anillo_v = 0.45 * perfil_dona((GX - x0) ** 2 + (GY - y0) ** 2) ** 2
                a_in = out[..., 3:].astype(float) / 255
                col = out[..., :3].astype(float) * (1 - anillo_v[..., None]) + C_STED * 255 * anillo_v[..., None]
                out = np.dstack([col, np.maximum(a_in[..., 0], anillo_v) * 255]).astype(np.uint8)
            img = ImageMobject(out)
            img.set_resampling_algorithm(RESAMPLING_ALGORITHMS["linear"])
            return img.set_width(ANCHO3).move_to(CENTRO3)

        anillo = [False]
        GX, GY = np.meshgrid((np.arange(NX) + 0.5) / PX_NM - W_NM / 2, H_NM / 2 - (np.arange(NY) + 0.5) / PX_NM)

        def nm_actual():
            P = min(p.get_value(), FILAS - 1e-6)
            k = int(P)
            f = P - k
            x = (-0.5 + (f if k % 2 == 0 else 1 - f)) * W_NM
            y = H_NM / 2 - (k + 0.5) * H_NM / FILAS
            return x, y

        def posicion():
            x, y = nm_actual()
            return CENTRO3 + np.array([x * S3, y * S3, 0])

        # dona (anillo naranja) y punto efectivo (verde) que siguen el barrido
        dona_vis = always_redraw(lambda: Circle(radius=FWHM_STED_FINAL / 2 * S3, color=FLUO, stroke_width=3,
                                                fill_color=FLUO, fill_opacity=0.35).move_to(posicion()))

        img = always_redraw(frame_img)
        esc = barra_escala(100, 1 / S3).move_to(CENTRO3 + RIGHT * 4.6 + DOWN * 2.45)
        cap = Tex(r"Resolución convencional: las estructuras cercanas se funden", font_size=32, color=GRIS)
        cap.to_edge(DOWN, buff=0.28)

        self.play(FadeIn(tit, shift=0.15 * DOWN), Create(marco), run_time=0.8)
        self.play(FadeIn(img), FadeIn(cap, shift=0.1 * UP), FadeIn(esc), run_time=0.8)
        self.wait(1.0)

        cap2 = Tex(r"Barrido en trama: punto a punto, línea a línea", font_size=32, color=STED)
        cap2.to_edge(DOWN, buff=0.28)
        anillo[0] = True
        self.play(FadeOut(cap), FadeIn(cap2, shift=0.1 * UP), FadeIn(dona_vis), run_time=0.8)
        self.add(dona_vis)
        self.play(p.animate.set_value(2), run_time=3.2, rate_func=rate_functions.ease_in_quad)   # al principio se ve bien la idea
        self.play(p.animate.set_value(FILAS / 2), run_time=4.0, rate_func=linear)
        self.play(p.animate.set_value(FILAS), run_time=2.2, rate_func=linear)                   # pasada la mitad, acelera
        dona_vis.clear_updaters()
        anillo[0] = False
        self.play(FadeOut(dona_vis), run_time=0.5)

        cap3 = Tex(r"Imagen STED: ahora sí se ven por separado ($\approx$ 20 nm)", font_size=34, color=FLUO)
        cap3.to_edge(DOWN, buff=0.28)
        self.play(FadeOut(cap2), FadeIn(cap3, shift=0.1 * UP), run_time=0.7)
        self.wait(2.2)
