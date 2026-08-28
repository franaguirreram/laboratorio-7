# Laboratorio 7 — Control de platina piezoeléctrica E-545/E-517 (macOS)

## Objetivo físico

Controlar una platina piezoeléctrica PI E-545 (electrónica de interfaz
E-517) desde macOS (Apple Silicon) para experimentos de estabilización
sub-nanométrica, usando el wave generator y el data recorder del propio
controlador para generar trayectorias precisas y grabar la respuesta del
sistema en tiempo real.

**Estado actual: infraestructura y caracterización, no un resultado
final todavía.** PI nunca compiló su librería de control para macOS
arm64; este repo primero resuelve esa capa de comunicación (ver
`e545-pi-ftdi-gateway/`), y después usa esa base para caracterizar la
dinámica de la platina (tracking error, repetibilidad) antes de correr
el experimento de estabilización propiamente dicho.

## Setup experimental

- Controlador: PI E-517 (serial `0111176619`), conectado por USB.
- Eje usado en las pruebas: A (rango físico medido: 0 a 200 µm).
- Reloj de servo interno: 40 µs (25 kHz) — medido, no de datasheet.
- Software: macOS arm64, Python 3.14 en `~/python-envs/pi`, `pipython`
  (librería oficial de PI) + un gateway de transporte propio (ver
  `e545-pi-ftdi-gateway/`) que reemplaza la DLL nativa que PI no
  distribuye para esta plataforma.

## Variable controlada

Posición del eje A, comandada vía wave table (`WAV_LIN`/`WAV_RAMP`) con
distintas amplitudes, velocidades (`WTR`), y perfiles de
aceleración/desaceleración (`speedupdown`). Se graba simultáneamente:
posición comandada, posición real (sensor), y error de seguimiento
(`data recorder`, opciones 1/2/3).

## Qué hay caracterizado hasta ahora

- Tracking error ante una rampa triangular pequeña (~100–500 nm de
  semi-amplitud): error de seguimiento del orden de decenas de nm en la
  zona de velocidad constante, y redondeo esperado en los picos (esquina
  de velocidad instantánea) — ver `resultados/figuras/`.
- Comparación de rampa recta (`WAV_PNT`/`writewavepoints`) vs. rampa
  suavizada con `speedupdown` (`WAV_RAMP`) — la segunda evita el
  quiebre abrupto en el pico.
- Límite real del controlador para cargar puntos de a uno: máximo 72
  puntos por comando `WAV_PNT`, medido en este equipo puntual.
- Test de repetibilidad en el rango físico completo (0–200 µm),
  comparando `WAV_RAMP` repetido vs. `WAV_LIN` + `MOV` directo —
  ver `scripts/E517_repetibilidad.py`.

Los datos crudos de cada corrida están en `datos/raw/` (con su
metadata en `datos/metadata/`), y las figuras correspondientes en
`resultados/figuras/` — cada figura del informe debería poder rastrearse
hasta el CSV que la generó (mismo timestamp en el nombre).

## Estructura del repo

```
.
├── e545-pi-ftdi-gateway/   # el driver de comunicación -- repo GITHUB APARTE
│                           # (github.com/franaguirreram/e545-pi-ftdi-gateway),
│                           # vive acá adentro por comodidad pero este repo
│                           # no lo trackea (ver .gitignore)
├── protocolos/             # pasos de adquisición, en orden, con unidades
├── scripts/                # scripts de adquisición (correr estos)
│   └── archivo/            # versiones obsoletas, conservadas como referencia
├── datos/
│   ├── raw/                # CSV crudos de cada corrida (no tocar a mano)
│   └── metadata/           # parámetros de cada corrida (timestamp compartido con el CSV)
├── resultados/
│   └── figuras/            # PDF/PNG listos para el informe
└── docs/                   # notas de contexto y material de referencia
    └── referencias/
```

## Cómo correr un experimento

Ver `protocolos/adquisicion_wave_data_recorder.md` para el detalle
completo. Instalación del driver (repo aparte en GitHub):

```bash
pip install git+https://github.com/franaguirreram/e545-pi-ftdi-gateway.git
```

Si estás desarrollando el driver a la vez (cambiándole código), instalá
en modo editable apuntando a la copia local:

```bash
pip install -e e545-pi-ftdi-gateway/
```

Después, cualquier script de `scripts/` se corre directo (apuntando el
intérprete de Python a `~/python-envs/pi/bin/python3.14` si se usa
Spyder) — cada uno guarda sus datos y su figura solo, en las carpetas
correspondientes.

## Limitaciones conocidas / pendiente

- El driver está probado solo contra este E-517 puntual — ver
  `e545-pi-ftdi-gateway/README.md` para el alcance exacto.
- Todavía no hay control (baseline) formal ni calibración documentada
  del sensor de posición — pendiente antes de reportar resultados como
  definitivos.
- El experimento de estabilización en sí (el objetivo final) todavía no
  está implementado — lo hecho hasta ahora es la infraestructura y la
  caracterización de la dinámica de la platina.
