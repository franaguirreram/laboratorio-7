# Respuesta para Copilot — ajustes a la plantilla de repo propuesta

La estructura que propusiste (README, protocolos/, datos/raw+processed+metadata,
notebooks/, resultados/figuras/) está bien pensada para un repo de datos
experimentales puro. Pero nuestro caso es un híbrido: además de datos de
laboratorio, hay una **librería de software reusable** (el driver de
comunicación con el controlador). Ya la separamos en dos repos por ese
motivo — tenerla en el mismo repo que los CSVs de una corrida puntual
mezclaría dos cosas con ciclos de vida distintos (una librería versiona
y se reusa; los datos de una corrida no).

## Repo 1: `e545-pi-ftdi-gateway` (ya existe, github.com/franaguirreram/e545-pi-ftdi-gateway)

Es la librería. Se queda con su propia estructura de paquete Python
(`pyproject.toml`, tests, README técnico) — no aplica la plantilla de
"repo de datos" acá. Lo único a agregar en este repo: un
`CHANGELOG.md` corto (ya tenemos el historial de versiones 0.2.0→0.3.2
documentado en `INFORME_AUDITORIA.md`, solo falta el formato estándar).

## Repo 2: "Laboratorio 7" (el de datos/experimento) — ya implementado así

```
.
├── README.md                — objetivo, setup, variable controlada, qué está caracterizado
├── CONTRIBUTING.md           — flujo de git explicado paso a paso (para aprenderlo, no ocultarlo)
├── protocolos/
│   └── adquisicion_wave_data_recorder.md   — pasos en orden, con unidades, comandos reales
├── scripts/                  — un script por tipo de experimento (no un único "run_experimento.py":
│   │                            tenemos varios experimentos distintos, no uno solo con flags)
│   ├── E517_diagnostico.py
│   ├── E517_ida_vuelta.py
│   ├── E517_ida_vuelta_speedupdown.py
│   ├── E517_repetibilidad.py
│   └── archivo/               — versiones obsoletas, conservadas como referencia histórica
├── datos/
│   ├── raw/                   — CSV crudos, un archivo por corrida, timestamp en el nombre
│   └── metadata/               — parámetros de cada corrida, MISMO timestamp que su CSV
├── resultados/
│   └── figuras/                — PDF/PNG, mismo timestamp que el CSV que graficaron
└── docs/
    └── referencias/             — material externo (paper de referencia, propuesta del proyecto)
```

### Diferencias respecto a tu propuesta, y por qué

- **`datos/processed/` todavía no existe** — hoy los scripts grafican
  directo desde el CSV crudo, sin un paso de procesamiento intermedio
  guardado aparte. La creamos cuando aparezca ese paso (por ejemplo, al
  hacer el análisis de repetibilidad agregando estadística sobre varias
  corridas).
- **No hay un `run_experimento.py` único** — cada script es un
  experimento distinto (diagnóstico, ida-vuelta simple, ida-vuelta
  suavizada, repetibilidad), con parámetros propios. Forzarlos a un
  único script con flags hoy agregaría complejidad sin necesidad real;
  si en algún momento comparten mucho código, ahí vale la pena extraer
  un módulo común.
- **Trazabilidad**: en vez de una convención aparte, usamos el mismo
  timestamp (`%Y%m%d_%H%M%S`) en el nombre del CSV, la metadata, y la
  figura de cada corrida — mirando el nombre del archivo ya sabés cuáles
  van juntos, sin necesidad de un índice separado.

## Lo que falta (gaps reales, no resueltos todavía)

- **Incertidumbre**: los scripts reportan error máximo y RMS de
  seguimiento, pero no hay todavía un análisis formal de incertidumbre
  de la medición de posición en sí (calibración del sensor).
- **Calibración**: no hay un documento de cuándo/cómo se calibró el
  sensor de posición del E-517 — pendiente.
- **Controles**: falta un baseline/test negativo explícito (por ejemplo,
  grabar con el wave generator apagado, servo abierto, para caracterizar
  el piso de ruido del sensor solo).
- **`notebooks/`**: no existe todavía — el análisis hoy vive adentro de
  cada script de adquisición (carga, grafica, listo). Si el análisis
  crece (comparar muchas corridas, ajustes, estadística), separarlo a
  un notebook de `notebooks/analisis_principal.ipynb` que lea de
  `datos/raw/` tiene sentido recién en ese momento.
- **`requirements.txt`**: falta en el repo de datos (el de la librería
  ya tiene sus dependencias en `pyproject.toml`). Debería listar:
  `numpy`, `pandas`, `matplotlib`, `pipython`, y
  `pi-ftdi-gateway @ git+https://github.com/franaguirreram/e545-pi-ftdi-gateway.git`.
- **GitHub Actions**: no hay ningún workflow todavía. Con hardware real
  de por medio, un workflow no puede correr los scripts de adquisición
  (no hay controlador conectado en el runner de GitHub) — lo único
  razonable de automatizar es un chequeo liviano: que los scripts
  compilen (`python -m py_compile`) y que los tests de la librería
  (`e545-pi-ftdi-gateway/tests/`, corren contra hardware simulado, sin
  necesitar el equipo real) pasen en cada push.

## Pedido concreto para la plantilla

Con esto ya armado a mano, lo que serviría de la plantilla de Copilot es
un generador liviano (`cookiecutter` o similar) que arme el
esqueleto de carpetas + README + CONTRIBUTING + `requirements.txt` para
el *próximo* repo de datos de laboratorio (otro instrumento, otro
experimento) — no hace falta tocar más este.
