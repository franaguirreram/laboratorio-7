# Pendientes a futuro

Lista para retomar de a poco. Marcar con `[x]` lo que se haga.

- [ ] **IMPORTANTE:** implementar la estabilización con la platina sobre takyaq
      (ver `docs/referencias/takyaq.md`): clase de cámara (`BaseCamera`) sobre
      `scripts/camara_aravis.py`, clase de platina (`BasePiezo`, en nm) sobre la
      E-517, y calibrar nm/px y ángulo. Comparar la estabilización con la de la
      platina actual. Revisar la licencia (AGPL-3.0) antes de usarlo como
      dependencia.
- [ ] Entender y optimizar exposición, ganancia y fps para este montaje
      (ver `docs/tutorial_camara_en_vivo.md`).
- [ ] Elegir las lentes f2–f4 según el aumento que se quiera en la cámara.
- [ ] Montaje a futuro con estabilización en z; pinhole entre f2 y f3 para
      hacerlo confocal (fotos por barrido).
- [ ] Circuito para llevar el rango de -10 a 10 V de la ADwin al de 0 a 10 V
      de la platina.
- [ ] `scripts/prueba_camara.py`: mejorarlo (hoy es un script de prueba con dos
      partes pegadas: conexión mínima + captura con Aravis). Ordenarlo en
      funciones, parametrizar exposición/ganancia y guardar las imágenes.
- [ ] Revisar los notebooks en `notebooks/a_revisar/` y decidir cuáles sirven
      (no versionados por ahora).
- [ ] Control (baseline) formal y calibración documentada del sensor de posición.
- [ ] Armar el microscopio de campo amplio para probar la estabilización antes
      de implementarla en el experimento real.
- [ ] Usar `trajectories.py` (no es nuestro, solo de inspiración) para diseñar
      los escaneos de la platina.

## Agregado 2026-10-11 (contexto del montaje y próximos pasos)

**Montaje actual** (croquis del cuaderno, rama principal): láser → ND40 →
espejos E1/E2 → BS → f1 → objetivo → muestra sobre la platina; el retorno
pasa por el BS → f2 → f3 → f4 → cámara. **Físicamente solo está hasta f1**;
f2–f4 están por definir según la magnificación deseada en la cámara.

**Montaje a futuro:** un solo láser dividido con divisores de haz, f1, f2
y cámara, ampliado para tener también estabilización en **z**. Queda en
veremos: podrían conseguir un segundo láser, pero por ahora se asume uno.

- [ ] Diseñar la cadena de lentes f2–f4: elegir focales según la
      magnificación objetivo en la cámara (escala = 5,86 µm / M, ver
      `camara_captura_y_escala.md`). Sin decidir cómo calcularlo todavía.
- [ ] Calibración px↔µm con la platina (paso a paso con fotos): pendiente
      de que la cámara tenga óptica. Diseño discutido: abrir la cámara una
      vez, exposición fija, promediar 3–5 cuadros, `qPOS` antes/después,
      correlación de fase subpíxel y ajuste de matriz A.
- [ ] Programa de visualización de la cámara en "tiempo real" (video con
      interfaz) para enfocar y ajustar.
- [ ] Entender y optimizar exposición, ganancia y demás parámetros de la
      cámara para este tipo de montajes (saturación, ruido, arrastre).
- [ ] Adaptar el software de **Takyaq** a este setup. Las imágenes de la
      cámara deberían pasar por Takyaq para recuperar la estabilización y
      compararla con la de la platina actual.
- [ ] Hacer el sistema **confocal**: agregar un pinhole entre f2 y f3 y
      obtener imágenes por escaneo (más adelante).
- [ ] Mejorar el montaje para estabilización en **z** (versión a futuro).
- [ ] Circuito para llevar el rango completo de la ADwin (−10 a +10 V) al
      rango de la platina (0 a 10 V). Se ve en una sesión aparte.
