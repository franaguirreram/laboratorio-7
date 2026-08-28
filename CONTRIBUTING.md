# Cómo se actualiza este repo con GitHub

Esto es una introducción real a los comandos que se usan, con ejemplos
de lo que ya hicimos en este repo — no una lista abstracta.

## El ciclo básico: status → add → commit → push

Git no manda nada a GitHub solo. Cada vez que cambiás un archivo, tenés
que decirle explícitamente a git "esto ya lo quiero guardar" (3 pasos
locales) y después "ahora sí, subilo" (push, el único paso que toca la
red).

### 1. `git status` — qué cambió

```bash
cd "/Users/fran/Desktop/LABORATORIO 7"
git status
```

Te dice qué archivos modificaste, cuáles son nuevos, y cuáles ya están
"preparados" para el próximo commit. Corré esto seguido — es de solo
lectura, no rompe nada.

### 2. `git add` — elegir qué va en el próximo commit

```bash
git add scripts/E517_ida_vuelta.py       # un archivo puntual
git add datos/raw/                        # una carpeta entera
git add .                                 # todo lo que cambió
```

`add` no "sube" nada — solo marca qué archivos van a entrar en el
próximo commit. Podés armar un commit con solo algunos de los archivos
que cambiaste.

### 3. `git commit` — el guardado real (todavía local)

```bash
git commit -m "Agrego test de repetibilidad con WAV_RAMP vs WAV_LIN+MOV"
```

Esto crea un punto en la historia del repo, **en tu disco, todavía sin
tocar GitHub**. El mensaje debería decir *por qué* cambiaste algo, no
solo *qué* archivo tocaste (`git status`/`git diff` ya muestran el qué).

### 4. `git push` — ahora sí, a GitHub

```bash
git push
```

Este es el único paso que sale a internet. Sin este comando, tus
commits quedan guardados solo en tu Mac — perfectamente reales, pero
invisibles para cualquier otra persona (o computadora) hasta que los
subís.

## Ejemplo real de esta sesión

En `e545-pi-ftdi-gateway/` (que ya tiene remoto configurado en GitHub)
hicimos exactamente esto:

```bash
cd e545-pi-ftdi-gateway
git add -A
git commit -m "v0.3.2: cleanup_gcsdevice() para reconexión sin 'with', ..."
git status   # dice "ahead of origin/main by 1 commit" -- commiteado, no pusheado
git push     # PENDIENTE -- lo corrés vos cuando quieras publicarlo
```

`git status` diciendo "ahead by 1 commit" es exactamente eso: el commit
existe en tu Mac, GitHub todavía no lo tiene.

## Conectar este repo nuevo (Laboratorio 7) a GitHub

Este repo (`LABORATORIO 7/`, el de arriba, con `scripts/`, `datos/`,
etc.) ya tiene su primer commit local, pero **todavía no tiene remoto**
— no está conectado a ninguna URL de GitHub. Para conectarlo (esto
requiere que exista el repo del lado de GitHub primero — crealo vacío
ahí, sin README/licencia, para no generar conflictos con lo que ya
tenés):

```bash
git remote add origin https://github.com/tu-usuario/laboratorio-7.git
git push -u origin main
```

`-u` (upstream) es un detalle que se hace una sola vez: le dice a git
"de ahora en más, cuando yo diga `git push` a secas, andá a este remoto
y esta rama". Sin el `-u` inicial, `git push` no sabe adónde mandar los
commits.

## Un detalle del nombre de esta carpeta

`LABORATORIO 7` tiene un espacio. Git lo banca bien, pero en la
terminal siempre hay que citarlo (`cd "LABORATORIO 7"`, no
`cd LABORATORIO 7`) — si algún script o comando falla raro con "No such
file or directory", casi siempre es por eso.

## Ver la historia

```bash
git log --oneline          # una línea por commit, lo más útil para mirar rápido
git log                    # con detalle completo (autor, fecha, mensaje)
git diff                   # qué cambió, línea por línea, todavía sin 'add'
git diff --staged          # qué cambió, línea por línea, ya con 'add'
```

## Cuándo pedirme ayuda de nuevo con esto

`add`/`commit`/`status`/`log`/`diff` son 100% seguros — no hay forma de
perder trabajo con ellos. `push` sube algo a un lugar que otros pueden
ver (o vos desde otra máquina) — pedime que lo revisemos juntos antes
la primera vez que conectes un repo nuevo a GitHub, después ya vas a
tener el hábito.
