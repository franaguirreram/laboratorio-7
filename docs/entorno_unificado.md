# Un entorno para cámara y platina

Revisión: 5 de octubre de 2026.

El único entorno de trabajo del laboratorio es `~/python-envs/pi`.
Su intérprete es `/Users/fran/python-envs/pi/bin/python`, basado en Python
3.14 de Homebrew. Conserva las versiones de las dependencias de la platina
y accede a PyGObject y Aravis de Homebrew con `--system-site-packages`.
Las bibliotecas nativas compartidas de Homebrew no son otro entorno virtual.
El entorno interno de Spyder pertenece a la aplicación y no debe eliminarse.

## Qué se corrigió

El antiguo `pi` usaba Python de python.org, mientras que Aravis/PyGObject
se habían instalado para Homebrew. `pip install gi` instaló `gi==0.8.1`
y `ginext-core`, que no proporcionaban el módulo necesario para Aravis.
El módulo `gi` correcto proviene de **PyGObject**. No instalar el paquete
homónimo de PyPI. Reiniciar la consola después de cambiar el entorno;
una sesión con módulos viejos cargados puede conservar el conflicto.

El gateway FTDI se instaló desde el commit
`b70382d43a47e88e66de21205e35dce4fe3b51da` de su repositorio.
Ya no depende de una instalación editable en el Escritorio: esa copia
tenía archivos descargables de iCloud que podían bloquear un import.
Su versión sigue siendo 0.3.2.

## Usar el entorno

```bash
source ~/python-envs/pi/bin/activate
python -c 'import sys; print(sys.executable)'
python -m pip check
```

En Spyder: Preferencias → Intérprete de Python → Usar el siguiente intérprete:
`/Users/fran/python-envs/pi/bin/python`. Cerrar las consolas anteriores y
abrir una nueva. No usar el intérprete `camara` ni el `.venv` del repo.
En notebooks, seleccionar el kernel **Laboratorio: cámara y platina**.

```python
import gi
gi.require_version("Aravis", "0.8")
from gi.repository import Aravis
from pipython import GCSDevice
from pi_ftdi_gateway import PIFtdiGateway, cleanup_gcsdevice
import numpy, pandas, scipy, matplotlib
```

La cámara sigue `Python → PyGObject → Aravis → USB3 Vision → IDS`.
La platina sigue `Python → PIPython → gateway FTDI → libusb → E-545/E-517`.
Son conexiones independientes; este cambio no establece sincronización
entre cuadros y movimientos y no ordena movimientos de la platina.

## Recrear en otra Mac Apple Silicon

Con Homebrew disponible, desde la raíz del repo:

```bash
brew install python@3.14 aravis pygobject3 libusb
/opt/homebrew/bin/python3.14 -m venv --system-site-packages ~/python-envs/pi
~/python-envs/pi/bin/python -m pip install -r requirements.txt
~/python-envs/pi/bin/python -m ipykernel install --user --name laboratorio-pi --display-name 'Laboratorio: cámara y platina'
```

`requirements.txt` define dependencias de uso. `requirements-laboratorio-lock.txt`
registra las versiones locales comprobadas; para reproducirlas instalar ese
archivo en lugar de `requirements.txt`. PyGObject/Aravis se gestionan con
Homebrew y no están fijados por ese lock de pip. Una actualización mayor
del Python de Homebrew requiere recrear el venv y verificar los imports.
No reutilizar estas instrucciones sobre un entorno existente sin inventariarlo.

## Verificación y límites

Se comprobaron los imports de cámara, análisis, Spyder y gateway, y
`pip check`. La cámara y la platina no estaban disponibles durante esta
revisión; no se repitió una adquisición ni se verificó movimiento físico.
La conexión/captura de cámara se había comprobado en la sesión anterior.
La prueba completa pendiente es capturar con óptica, medir una escala
y verificar luego la sincronización con la platina.
