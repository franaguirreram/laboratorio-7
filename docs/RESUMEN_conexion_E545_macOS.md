# Resumen: conexión del E-545/E-517 a macOS sin la DLL de PI

Fecha: 2026-08-26. Hardware: platina piezoeléctrica PI E-545 (electrónica
de interfaz E-517), número de serie GCS2 `0111176619`. Máquina: MacBook Air
arm64, macOS. Entorno Python: venv en `~/python-envs/pi` (Python 3.14 arm64).

Este documento es both (a) insumo para el cuaderno de laboratorio y (b)
contexto autocontenido para retomar esta conversación con otro chat de
Claude sin perder nada de lo ya resuelto.

## 1. El problema original

El script de trabajo (`Codigo_michelsonTRES_CHAD.py`, que hace un barrido
de un interferómetro de Michelson moviendo la platina y leyendo un
detector) andaba antes desde una PC con Windows, usando `pipython`
(la librería oficial de Physik Instrumente en Python) conectada por USB
vía `pidevice.ConnectUSB("0111176619")`.

Al migrar a macOS (arm64), ese mismo código falla con:
```
OSError: .../libpi_pi_gcs2.dylib not found
```
`pipython` necesita, en macOS, un archivo nativo `libpi_pi_gcs2.dylib`
(análogo a la DLL de Windows) para hablar USB con el controlador. Ese
archivo nunca existió en la máquina.

## 2. Investigación: por qué no existe ese archivo

- El instalador descargado (`PI-Software-Suite-C-990`, ~2.3 GB, ubicado en
  `~/Desktop/LABORATORIO 7/`, no en `~/Downloads` como se creía) es un
  paquete orientado a **Windows**, con un agregado para **Linux x86_64**.
  **No contiene ningún `.dylib` de macOS**, ni x86_64 ni arm64.
- La única librería nativa GCS2 del paquete es
  `libpi_pi_gcs2_x86_64-3.30.0-INSTALL.tar.bz2`, un `.so` de **Linux
  x86_64** — no solo la arquitectura es distinta, el formato binario
  también (ELF vs. el Mach-O que necesita macOS). Renombrar ese archivo a
  `.dylib` nunca iba a funcionar, sin importar la arquitectura.
- `~/.pi_libs/` (la ruta que se sospechaba en un principio) **nunca existió**
  en el sistema. La ruta real que `pipython` buscaba, al no encontrar
  `/usr/local/PI/lib64`, era el directorio de trabajo del script en el
  momento de ejecutarlo (comportamiento de fallback de
  `gcsdll.py::get_gcstranslator_dir()`).
- `pipython` sí estaba instalado, pero en un venv que no era obvio a
  primera vista: `~/python-envs/pi` (Python 3.14, no 3.12 como se creía
  inicialmente).
- De la API de `pipython`: `ConnectTCPIP`/`ConnectRS232` son Python puro
  (usan `socket`/`pyserial`, sin librería nativa). Solo `ConnectUSB` (y
  otras conexiones tipo GPIB/PCI) requieren la DLL/dylib vía `ctypes`. El
  E-545 solo tiene USB, así que esta salida fácil no aplicaba.

## 3. Camino descartado: pedirle el binario a PI / conseguirlo de otro lado

Se evaluaron y descartaron:
- **Emular x86_64 con Rosetta**: no serviría ni con la arquitectura
  correcta, porque el archivo Linux es formato ELF, no Mach-O.
- **Decompilar el `.dll`/`.so` de PI** para "portarlo": descartado
  deliberadamente por motivos legales/de licencia (reversing de un binario
  propietario, muy probablemente contra el EULA de PI). No se hizo nada de
  esto.
- **Web Serial API / notebooks en la nube**: un notebook remoto (Colab,
  etc.) no tiene acceso al USB local, así que queda descartado de plano.
  Web Serial (navegador local) tampoco aplica: el dispositivo no se expone
  como puerto serie estándar del sistema operativo (no aparece como
  `/dev/cu.usbserial-*`), porque usa un Vendor ID propio de PI
  (`0x1a72`), no el de FTDI (`0x0403`).

## 4. La solución real: hablarle directo al chip FTDI

Evidencia que llevó a la solución:
- El instalador Linux de PI incluye `pi_ftdi_usb-2.3.12-INSTALL.tar.bz2`,
  indicio de que el hardware de PI usa chips **FTDI** reprogramados con el
  VID/PID propio de PI.
- Inspeccionando los descriptores USB reales del dispositivo conectado
  (`system_profiler` + `pyusb`): VID `0x1a72`, PID `0x1005`,
  `bInterfaceClass=0xFF` (vendor-specific), 2 endpoints bulk (IN/OUT de 64
  bytes), USB 1.1 full-speed — la huella clásica de un chip FTDI
  monocanal (familia FT232AM/R).

Con eso, se armó un **gateway propio** que habla:
1. El **protocolo FTDI estándar** (público, documentado por FTDI, vía la
   librería open-source `pyftdi`), para configurar baudrate/línea y mandar
   bytes crudos por USB.
2. El **set de comandos ASCII GCS2** de PI (`*IDN?`, `MOV`, `SVO`, `ONL`,
   etc.), documentado públicamente por PI para que el cliente lo use.

**No se decompiló ni copió nada del software de PI.** Todo el protocolo
usado es público (spec de FTDI + comandos GCS2 documentados).

### Detalles técnicos encontrados en el camino

- `pyftdi` 0.57.2 identifica este chip como `ft232am` (por
  `bcdDevice=0x0200`) y tiene un **bug real** (división por cero) en su
  algoritmo de baudrate "legacy" para ciertos valores, 115200 incluido.
  Se reimplementó el cálculo correcto (documentado por FTDI) para
  evitarlo.
- El controlador **no responde si no se afirman DTR y RTS** antes de
  escribir.
- El controlador espera terminador de línea **`\r`** (o `\r\n`); un `\n`
  suelto no dispara respuesta. `pipython` arma sus comandos terminados en
  `\n`, así que el gateway traduce `\n` → `\r` al escribir.
- El descriptor USB no trae el número de serie real del equipo
  (`iSerialNumber` vacío); el serial de GCS2 (`0111176619`) solo se
  obtiene preguntando `*IDN?` una vez conectado.

### Punto de integración con pipython

`pipython` ya soporta inyectar un transporte propio:
```python
GCSDevice(devname='E-545', gateway=mi_gateway)
```
donde `mi_gateway` implementa la interfaz `PIGateway` (la misma que usan
internamente `PISocket`/`PISerial`: `send`, `read`, `flush`, `close`,
`connected`, `timeout`, etc.). Esto permite seguir usando **toda** la API
de alto nivel de `pipython` (`SVO`, `ONL`, `MOV`, `qPOS`, `qVOL`, `qONT`,
`pitools.waitontarget`, etc.) sin tocar el resto del código.

## 5. Estado actual (funcionando)

Validado contra el hardware real, incluyendo un movimiento físico real de
la platina (-5.592 µm → 100.08 µm, confirmado por `qPOS`/`qVOL`):

- **Paquete instalable**: `~/PIPython/pi_ftdi_gateway_pkg/`
  (`pip install -e .` ya corrido contra `~/python-envs/pi`). Provee
  `from pi_ftdi_gateway import PIFtdiGateway, list_devices`.
- Versión 2 del gateway agrega, sobre la versión inicial que ya había
  funcionado:
  1. **Manejo de errores**: `PIFtdiConnectionError` clara si no hay
     dispositivo, hay ambigüedad (más de un equipo PI conectado), o se
     pierde la conexión a mitad de una lectura/escritura.
  2. **Timeout real**: `settimeout()` ahora también configura el timeout
     de las transferencias USB de bajo nivel, no solo lo guarda.
  3. **Autodetección**: `list_devices()` escanea USB por VID/PID de PI;
     `PIFtdiGateway(address=(bus, address))` permite elegir un equipo
     puntual si hay más de uno conectado.
  4. *(Tests automatizados: pendiente, no incluido en esta versión.)*
  5. **Empaquetado instalable**: `pyproject.toml` + `pip install -e .`,
     ya no hace falta `sys.path.insert(...)` a mano.
- Diagnóstico de referencia: `~/Desktop/LABORATORIO 7/diagnostico_minimo.py`
  — prueba exactamente los controles que usa el script de Michelson
  (`qIDN`, `ONL`, `SVO`, `MOV` crudo, `qPOS`, `qVOL`,
  `pitools.waitontarget`).
- La versión vieja de un solo archivo quedó respaldada (no borrada) en
  `~/PIPython/pi_ftdi_gateway_v1_OBSOLETO.py.bak`.
- Para correr esto en Spyder: apuntar **Preferences → Python Interpreter**
  a `~/python-envs/pi/bin/python3.14` (Spyder standalone trae su propio
  entorno interno para la IDE, que no tiene `pipython`/`pyftdi` instalados).

## 6. Pendiente / próximos pasos

- Adaptar `Codigo_michelsonTRES_CHAD.py`: cambiar solo el bloque de
  conexión (usar `GCSDevice('E-545', gateway=PIFtdiGateway())` en vez de
  `ConnectUSB(...)`); el resto de la lógica de escaneo no necesita
  cambios. Ese script además tiene dos problemas propios, no relacionados
  con la platina:
  - `import u12` (driver LabJack, específico de Windows).
  - Ruta de guardado del CSV en formato Windows
    (`C:/Users/NANOFISICA_07/...`).
- Publicar el paquete en GitHub (con README, licencia MIT, aclarando el
  alcance: probado solo contra E-545/E-517, protocolo público, sin
  relación con el código propietario de PI).
- Preparar mediciones usando las funciones de **wave generator** y
  **data recorder** del GCS2 (próximo tema a resolver en la conversación).

## 7. Contexto técnico de referencia rápida (para otro chat)

- VID/PID del controlador: `0x1a72` / `0x1005`.
- Baudrate GCS2: `115200`, 8N1, requiere DTR+RTS altos, terminador `\r`.
- Chip detectado como `ft232am` por pyftdi (vía `bcdDevice=0x0200`) —
  ojo con el bug de baudrate legacy de pyftdi 0.57.2 para ese tipo de chip.
- Venv de trabajo: `~/python-envs/pi` (Python 3.14 arm64).
- Paquete del gateway: `~/PIPython/pi_ftdi_gateway_pkg/` (instalado en
  modo editable).
- Script del experimento real: `~/Laboratorio 6/Codigo_michelsonTRES_CHAD.py`
  (sin adaptar todavía a este gateway).
