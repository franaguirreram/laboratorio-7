# Contexto vigente y limpieza local

Revisión: 5 de octubre de 2026.

## Estado que conviene conservar

La platina PI E-545/E-517 se controla desde macOS mediante PIPython y
el gateway FTDI público propio. `ConnectUSB` dependía de una biblioteca
nativa de PI que no estaba disponible en esta instalación. El gateway
resuelve ese transporte, no el control óptico. Serial GCS2: `0111176619`.

Los análisis de escalones y rampas caracterizan posición registrada por
el controlador. No son imágenes ni conteos de fotones sincronizados.
El resumen revisado del 28/09 encontró un retardo cercano a 13 ms en
ciertas condiciones, pero no una constante universal. El offset, DCO,
montaje y selección del tramo útil importan. Una desviación de ajuste o
ruido del sensor no demuestra por sí sola estabilización subnanométrica.
Conservar CSV, metadata, notebooks reproducibles y procedencia.

La IDS U3-3060CP-M-GL Rev.2.2, serial `4108802838`, se detectó y se abrió
con Aravis por USB 3. El usuario confirmó adquisiciones que respondían
a la tapa. La interpretación inicial de que hacía falta necesariamente
Windows/Linux quedó superada por esa prueba en macOS. Aravis reemplaza
la necesidad de usar el SDK IDS para las funciones comprobadas; no es
una adaptación binaria del software Linux.

Confirmación del usuario en esta revisión: **ahora no dispone de la
cámara; la prueba previa se hizo sin sistema óptico**. Por eso no se
había demostrado enfoque ni correspondencia espacial con una muestra.
No atribuir automáticamente la imagen difusa a promediado o buffer viejo.

El montaje conversado apunta primero a campo amplio para seguir marcas
y estabilizar. Se mencionaron un Nikon 100× NA 1,4 y un Olympus 150×;
la configuración definitiva y su aumento efectivo no están verificados.
La iluminación amplia y la formación de imagen son dos ramas distintas:
enfocar el láser en el plano focal posterior para iluminación amplia no
sustituye la óptica de detección. El plano focal posterior no coincide
necesariamente con el hombro del objetivo. La estabilización Z por
astigmatismo exige curva de calibración independiente.

## Qué falta para dejarlo operativo

1. Usar el entorno único `~/python-envs/pi` y reiniciar consolas antiguas.
2. Adquirir una referencia enfocada cuando haya óptica; calibrar nm/píxel,
   orientación XY y, si corresponde, forma de PSF frente a Z.
3. Verificar exposición, ganancia, ROI/binning y repetibilidad de captura.
4. Definir sincronización cámara–platina y medir latencia/jitter antes
   de reconstruir barridos o cerrar un lazo óptico.
5. Validar estabilización con referencia independiente y montaje final.

## Fuentes de los chats y alcance

Se leyeron los chats accesibles **Conectar cámara a la computadora**,
**Verificar control de cámara por USB**, **Montaje óptico del objetivo**,
**Diseño sistema óptico**, **Buscar Nikon 100x NA 1.4** y
**Alinear sistema óptico**. La caracterización anterior proviene también
de `Resumen_Laboratorio_7.md` revisado el 28/09 y de las notas del repo.
No se afirma haber recuperado todo el historial de Work ni chats eliminados.
Las explicaciones previas son antecedentes, no mediciones nuevas.

## Criterio de limpieza

| Material | Decisión |
|---|---|
| `~/python-envs/pi` | Único venv de trabajo; recreado con Homebrew, sin `gi`/`ginext-core` |
| `~/python-envs/camara` | Redundante una vez verificadas las dependencias de `pi` |
| `.venv` del repo del Escritorio | Tercera copia; retirar solo tras inventario y comprobar que no contiene trabajo ajeno al venv |
| `__pycache__`, `.pyc`, caché pip | Regenerables; pueden retirarse con alcance limitado al laboratorio |
| Bibliotecas de Homebrew, Python del sistema, Spyder interno | Dependencias compartidas; conservar |
| CSV crudos y metadata | Conservar; no deducir obsolescencia por antigüedad |
| `scripts/archivo/` | Referencia histórica versionada; retirar solo al comprobar reemplazos y referencias |
| Figuras y tablas derivadas | Candidatas si se demuestra su regeneración con scripts/datos actuales |
| Instaladores y binarios propietarios de PI | Candidatos externos; el gateway no los usa, pero comprobar otras necesidades antes de borrar |
| Chats | Conservar el resumen; archivar los dos chats técnicos de cámara después de documentarlos |
| Fuentes sincronizadas del proyecto | Solo lectura; no modificarlas ni usarlas como carpeta de trabajo |

Archivar chats es reversible y sirve para ordenar; no implica eliminar
su contenido ni promete recuperar espacio local de caché. No editar a
mano las bases de datos internas de Work/Codex.

## Repositorio y archivos locales

El repo del Escritorio es `/Users/fran/Desktop/LABORATORIO 7`, con remoto
`franaguirreram/laboratorio-7`. La copia de referencia del proyecto estaba
en `7266846`, también HEAD de GitHub al iniciar esta revisión. Se preparó
una copia de trabajo separada en `entregables/laboratorio-7`, porque algunas
lecturas del repo del Escritorio se bloquearon y el código del gateway
editable mostraba archivos `dataless` de iCloud. La copia de referencia
y `sources/` se conservaron sin cambios.

No limpiar `.git/objects` manualmente ni borrar `.claude/worktrees` como
si fueran caché: pueden contener trabajo único. Revisar cada worktree,
su estado y commits antes de retirarlo. El script local `prueba_camara.py`
del Escritorio contenía las pruebas previas; la nueva adquisición tiene
entrada única, selección de serial, padding y guardado con metadata.
No descartar ese archivo hasta integrar la actualización en esa copia.

La limpieza del historial público para eliminar binarios requeriría una
operación distinta a este commit; borrar un archivo del árbol actual no
lo elimina de commits antiguos. Esta revisión no reescribe historia.

## Limpieza ejecutada y validación

- Se retiraron `camara`, el respaldo temporal del antiguo `pi`, el `.venv`
  vacío de dependencias de trabajo (solo pip), y bytecode de scripts/gateway.
- Se retiró la caché regenerable de pip (aproximadamente 44 MiB); el entorno
  `camara` ocupaba aproximadamente 214 MiB. No es un cálculo del balance
  total de disco, porque también se recreó `pi` y se preparó una copia del repo.
- Se retiraron los kernels Jupyter duplicado `pi` (etiquetado erróneamente
  Python 3.12) y roto `pi-rosetta`; quedó `laboratorio-pi`.
- Se cambió la selección de Spyder a `/Users/fran/python-envs/pi/bin/python`.
  Los respaldos de configuración están en `/private/tmp/labo-config-20261005`.
- Se archivaron los dos chats técnicos de cámara citados; son recuperables.
  Se conservaron los chats de diseño óptico que contienen decisiones abiertas.
- Pasaron imports, `pip check`, arranque de un kernel Jupyter real y
  decodificación con padding/buffer incompleto. Una captura simulada comprobó
  exposición y guardado NPY/PNG/JSON; no reemplaza validación de hardware.

No se retiraron CSV, notebooks, diseño mecánico, instaladores ni worktrees
no auditados. Los inventarios de entornos y el registro de limpieza se
guardaron localmente en `entregables/2026-10-05`; no incluyen credenciales.
