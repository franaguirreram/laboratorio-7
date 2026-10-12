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
