# takyaq — referencia para la estabilización

**Importante para el proyecto:** takyaq es la base con la que vamos a
implementar la estabilización con la platina. El tratamiento de imágenes
de nuestros scripts de cámara sigue el suyo, para que después sea el mismo.

- Repo: <https://github.com/Stefani-Lab/takyaq>
- Revisado: commit `2ced935d24e65a343ec4d660a4f65bf17fb5cb0e`, versión 0.1.0
  (`pyproject.toml`), 12 de octubre de 2026.
- Licencia: AGPL-3.0-or-later. **No se copia su código a este repo**; se usa
  como referencia (mismo criterio que con `trajectories.py`). Si se llega a
  usar como dependencia o a modificar, revisar las condiciones de la AGPL.
- Artículo: Edorna (2025), en esta misma carpeta.

## Qué hace con las imágenes (leído del código, `takyaq/stabilizer.py`)

1. La cámara es una clase con `get_image()` que devuelve un array 2D
   (`base_classes.BaseCamera`). Los valores se usan crudos: no hay resta de
   fondo ni normalización. El mock devuelve `uint16`.
2. Se definen ROIs a mano (`ROI(min_x, max_x, min_y, max_y)`, en píxeles).
   Cada ROI se recorta como `image[min_x:max_x, min_y:max_y]`.
3. En cada ROI se ajusta una **gaussiana 2D** con `scipy.optimize.curve_fit`
   (`_gaussian_fit`). Modelo: `offset + amplitud * exp(-(a (x-x0)² + a (y-y0)²))`,
   `a = 1/(2 sigma²)`. Valor inicial: `(max-min, x_max, y_max, sigma, min)`.
4. Valor inicial por ROI (`_initialize_last_params`): el máximo del recorte y
   `sigma = lado/3`. Después de cada cuadro reutiliza el ajuste anterior como
   valor inicial; si el ajuste falla (`nan`) conserva el anterior.
5. El resultado se suma al origen de la ROI y se multiplica por nm/px.
   Todo el módulo trabaja en **nm**.
6. Para Z no ajusta una gaussiana: usa el centro de masa de la ROI
   (`scipy.ndimage.center_of_mass`).
7. La calibración nm/px (`_calibrate_xy`) mueve la platina en N puntos y ajusta
   una recta por mínimos cuadrados; es la misma idea de
   `scripts/calibrar_escala_camara.py`.

### Cosas a tener cuidado

- **Convención de ejes:** en takyaq `x` es el *primer índice* del array (fila) e
  `y` el segundo (columna) (`meshgrid(..., indexing="ij")`). En una imagen
  mostrada con matplotlib, `x` horizontal es la columna. Nuestro
  `camara_aravis.localizar_punto` devuelve `x` = columna, `y` = fila, y
  `params` en la convención de takyaq.
- El docstring de `_gaussian2D` dice que `sigma` es FWHM, pero la fórmula
  corresponde al desvío estándar. Es una discrepancia interna del repo.
- `adapters.py` hace `from base_classes import ...` (import absoluto), que
  probablemente falle como paquete. No lo verifiqué ejecutándolo.
- Procesa los ajustes en un `ProcessPoolExecutor`; nuestro visor lo hace en
  un solo proceso.

## Dónde conecta una cámara y una platina nuevas

- Cámara: heredar de `BaseCamera` e implementar `get_image()`. Hay un wrapper
  para pylablib (`takyaq/wrappers/pylablib.py`); nuestra cámara va por Aravis.
- Platina: heredar de `BasePiezo` (`get_position`, `set_position_xy`,
  `set_position_z`, en nm). Hay wrappers `InMicrons` / `InNanometers`
  (`adapters.py`) para convertir unidades. La nuestra devuelve µm.
- Parámetros de cámara: `CameraInfo(nm_ppx_xy, nm_ppx_z, angle)`.

Las ideas de este documento salen de leer el código; no se ejecutó takyaq
ni se probó con nuestra platina.
