# starlight-hack

**Usa tu Hercules DJControl Starlight para mucho más que mezclar.** Sus botones, perillas y pads pueden manejar tu computador, las luces de tu casa y tus sesiones de Claude Code. Su luz de colores te avisa lo que pasa.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/tablero-oscuro.png">
  <img src="docs/img/tablero-claro.png" alt="El tablero de starlight: un dibujo de la Starlight que se mueve cuando tocas el aparato, los controles de la luz de la base, los modos de los pads y tres sesiones de Claude Code, una de ellas con una pregunta y sus opciones en los pads A1, A2 y A3.">
</picture>

Proyecto independiente, sin relación con Hercules. Probado en Windows 11 con la versión 1.0.0.0 del aparato. Tiene código para macOS y Linux, pero aún no lo hemos probado ahí.

## Qué puedes hacer

- **Manejar el computador.** Cada control hace lo que elijas: un atajo de teclado, pausar la música, el volumen de Windows o de una app, desplazarte, abrir un programa.
- **Ver tus sesiones de Claude Code.** La luz de la base se pone naranja cuando una sesión te necesita. Respondes con los pads, sin tocar el teclado.
- **Prender las luces de tu casa.** Philips Hue y Home Assistant, con un botón o una perilla.
- **Pintar la luz de la base.** La base son las dos luces de colores que el aparato tiene debajo. Puedes usar 12 colores o cualquier otro, fijos, parpadeando o respirando.
- **Programarla a tu gusto.** Trae un servidor con una API (una forma de darle órdenes por HTTP desde cualquier programa), una CLI (los comandos `starlight …` de la terminal) y perfiles en Python.

## Empieza en 5 minutos

Necesitas:

- Una Hercules DJControl Starlight conectada por USB.
- Python 3.10 o más reciente, y Git.

**1. Descarga e instala.** En la terminal:

```powershell
git clone https://github.com/oddradiocircle/starlight-hack.git
cd starlight-hack
python -m venv .venv
.venv\Scripts\pip install -e .
```

En macOS o Linux, cambia la última línea por `.venv/bin/pip install -e .`.

**2. Arranca el servidor.**

```powershell
.venv\Scripts\starlight serve --abrir
```

Se abre el tablero en tu navegador, en `http://127.0.0.1:8765`.

**3. Toca un control de la Starlight.** El dibujo del tablero se mueve contigo y abajo ves qué control fue y su mensaje.

Para no escribir `.venv\Scripts\` cada vez, activa el entorno con `.venv\Scripts\activate` (en macOS o Linux: `source .venv/bin/activate`).

### Si algo falla

| Si pasa esto | Haz esto |
|---|---|
| El tablero dice «Desconectada» | Revisa el cable USB. Luego corre `starlight estado`. |
| La Starlight dejó de responder | Detén el servidor con Ctrl + C y arráncalo otra vez. Si sigue igual, desconecta y conecta el USB. |
| `pip` falla con un error de certificados | Tu antivirus revisa las conexiones seguras (pasa con Avast). Define la variable `PIP_USE_FEATURE=truststore` y repite. |
| El volumen subió muchísimo | Activaste el modo computador. Baja el volumen y desconecta y conecta el USB. |

## Úsala

### El tablero

Es la página que abre el servidor. Muestra la Starlight en vivo y te deja:

- prender o hacer titilar la luz de cada botón y pad;
- pintar la base y elegir su efecto, su brillo y su velocidad;
- cambiar el modo de los pads (Hot Cue, Loop, FX, Sampler);
- ver tus sesiones de Claude Code.

También funciona en el celular. Mira [Desde otro equipo](#desde-otro-equipo-o-el-celular).

### Perfiles

Un perfil dice qué hace cada control en el computador. Vienen cuatro:

| Perfil | Qué hace |
|---|---|
| Claude Code | Play A envía, Cue A interrumpe, Sync A cambia de modo y los pads A responden 1, 2 y 3. La base muestra el estado de tus sesiones. |
| Escritorio | Play pausa la música. Cue y Sync pasan a la canción anterior o a la siguiente. Volume A es el volumen de Windows. |
| Luces | La base sigue el ritmo de lo que suena en el computador. |
| Navegar | Jog A desplaza arriba y abajo, Jog B a los lados. Shift + Jog A hace zoom. |

Para cambiar de perfil:

- **En el aparato:** Shift + Vinyl pasa al siguiente. Shift + Bass/Filter vuelve al anterior.
- **En el tablero:** elígelo arriba, junto a «Perfil».
- **En la terminal:** `starlight perfil <nombre>`.

El servidor recuerda el último perfil que usaste.

### Edita un perfil

![El editor de perfiles: a la izquierda la lista de perfiles; a la derecha, qué pasa al activar el perfil, la luz de la base y un dibujo de la Starlight donde eliges el control que quieres cambiar.](docs/img/editor.png)

1. En el tablero, abre **Editar perfiles**.
2. Elige un control: tócalo en el dibujo, o presiona «Elegir tocando la Starlight» y tócalo en el aparato.
3. Debajo aparece lo que hace. Cámbialo y presiona **Guardar**.

Puedes asignar:

- **Acciones:** un atajo de teclado (lo grabas presionándolo), una tecla multimedia, escribir un texto, abrir un programa o una página, el volumen de Windows o de una app, desplazarte, flechas, zoom, el color de la base, cambiar de perfil o las luces de la casa.
- **Cuándo:** al presionar o al soltar, con Shift o sin Shift.
- **Solo si:** según el programa que tengas al frente o el estado de Claude Code. Ejemplo: Play A envía Enter solo si la terminal está al frente.
- **Escena:** deja el aparato como lo quieres y presiona «Grabar en el perfil». Al activar el perfil, la base, las luces y los modos de los pads vuelven a quedar así.

Para compartir un perfil, presiona **Exportar**. Se descarga un archivo `.starlight.json`. Quien lo reciba lo abre con **Importar…** y lo revisa antes de guardarlo.

Los perfiles incluidos no se borran. Si cambias uno, se guarda tu copia en `~/.starlight/perfiles` (en Windows, `C:\Users\<tu usuario>\.starlight\perfiles`).

### Claude Code en la Starlight

![La parte del editor que define el color de la base para cada estado de Claude Code: trabajando, te necesita, terminó, inactiva y error. Abajo a la derecha, una Starlight en pequeño muestra cómo se verá.](docs/img/editor-claude.png)

Con el perfil Claude Code activo, la base muestra cómo van tus sesiones:

| La base | Qué significa |
|---|---|
| Naranja, parpadea | Una sesión te necesita: pide permiso, te hace una pregunta o quiere que apruebes un plan. |
| Rojo, parpadea | Una respuesta falló. |
| Celeste, respira | Claude está trabajando. |
| Verde, fija | Terminó y espera tu siguiente mensaje. |
| Índigo, fija | La sesión lleva un rato esperando sin que le escribas. |

Con varias sesiones abiertas, la base muestra la más urgente. Cuando Claude te hace una pregunta, titilan tantos pads como opciones haya. Tocas uno y respondes. Los colores se cambian en el editor.

**Para conectarla, agrega los hooks a Claude Code.** Un hook es un comando que Claude Code corre en cada evento. Estos le avisan al servidor:

1. Abre `~/.claude/settings.json` (en Windows, `C:\Users\<tu usuario>\.claude\settings.json`).
2. Copia ahí la clave `"hooks"` de [`scripts/hooks-claude-code.json`](scripts/hooks-claude-code.json). Si ya tienes hooks, agrega cada evento a tu lista.
3. Abre una sesión nueva de Claude Code y comprueba con `starlight claude sesiones`.

Los hooks usan `curl`, que ya viene en Windows 10 y 11, macOS y Linux. Corren en segundo plano y nunca fallan, aunque el servidor esté apagado. De cada evento, el servidor solo lee la sesión, el tipo de evento, la herramienta, la carpeta, el aviso y el texto de las preguntas. No guarda nada en disco.

**Opcional: Wave Terminal.** Si usas [Wave](https://www.waveterm.dev/), [`scripts/wave_hook.sh`](scripts/wave_hook.sh) pinta de naranja el borde de la terminal que te necesita y le pone una insignia verde cuando termina. Agrégalo como un segundo hook en los mismos eventos:

```json
{ "type": "command", "async": true, "timeout": 10,
  "command": "bash \"/ruta/a/starlight-hack/scripts/wave_hook.sh\" esperando" }
```

Usa `esperando` en PreToolUse y en Notification (permission_prompt y elicitation_dialog), `trabajando` en UserPromptSubmit, PostToolUse y SessionEnd, y `listo` en Stop.

### Las luces de tu casa

![La página Casa: una tarjeta para conectar Home Assistant con su dirección y un token de acceso, y otra para emparejar el puente Hue.](docs/img/casa.png)

En el tablero, abre **Casa**:

- **Home Assistant:** presiona «Buscar en mi red». Luego pega un token de acceso de larga duración. Lo creas en tu perfil de Home Assistant, en «Seguridad».
- **Philips Hue:** presiona «Buscar en mi red». Luego presiona el botón redondo del puente y, antes de 30 segundos, «Emparejar».

Después, en un perfil, la acción **«Luces de la casa»** prende, apaga o cambia el color de una luz, o activa una escena. Con una perilla mueves el brillo.

Todo pasa dentro de tu red. La conexión se guarda solo en tu equipo, en `~/.starlight/casa.json`, y la página nunca vuelve a mostrar el token. Si Hue Sync está sincronizando un área, esas luces no responden hasta que la pauses.

### Desde la terminal

```bash
starlight escuchar                      # muestra en vivo cada control que tocas
starlight base rojo --efecto respira    # color de la paleta (1 a 12, o su nombre)
starlight base "#ff0080" --lado izq     # cualquier color
starlight base auto                     # la base vuelve a su show normal
starlight brillo 40                     # brillo de la base, de 0 a 100
starlight luz A.play on                 # luces: A.play, B.cue, vinyl, bassfilter, A.pad1…
starlight modo A fx                     # modo de los pads: hotcue, loop, fx, sampler
starlight perfil navegar                # cambia de perfil
starlight midi 91 07 7F                 # un mensaje MIDI a mano
starlight estado                        # todo lo que sabe el servidor
```

MIDI es el idioma en que la Starlight y el computador se hablan. Cada mensaje son 3 números en hexadecimal: `91 07 7F` prende la luz de Play A.

### Desde tus programas

El servidor es el único que habla con el aparato. Tus scripts le hablan por HTTP, en `http://127.0.0.1:8765`. Ejemplo con `curl`:

```bash
curl -X POST http://127.0.0.1:8765/api/base -H "Content-Type: application/json" -d '{"color": "verde", "efecto": "respira"}'
```

<details>
<summary>Todas las rutas de la API</summary>

| Método | Ruta | Cuerpo | Qué hace |
|---|---|---|---|
| GET | `/api/estado` | | Conexión, posiciones, luces, base y modos |
| GET | `/api/controles` | | Lista de controles, luces, modos, efectos y paleta |
| GET | `/api/eventos` | | Flujo en vivo (SSE): `control`, `luz`, `base`, `modo`, `conexion` |
| POST | `/api/luz` | `{"control": "A.play", "encendida": true}` | Prende o apaga una luz; los pads aceptan `modo` |
| POST | `/api/base` | `{"color": "rojo", "efecto": "respira", "lado": "ambos"}` | Paleta; también `{"rgb": "#ff0080"}` o `{"auto": true}` |
| POST | `/api/modo` | `{"deck": "A", "modo": "fx"}` | Modo de los pads |
| POST | `/api/midi` | `{"msgs": [[145, 7, 127]]}` | MIDI a mano |
| POST | `/api/apagar-luces` | `{}` | Apaga las luces y devuelve la base a su show normal |
| POST | `/api/brillo` | `{"valor": 0.4}` | Brillo de la base (0 a 1) |
| POST | `/api/avanzado` | `{"demo": true}` · `{"modo_computador": true, "entiendo": true}` | Interruptores SysEx del aparato |
| GET | `/api/sysex/info` · `/api/sysex/crudo` · `/api/sysex/calibracion` | | Lecturas SysEx |
| POST | `/api/sysex` | `{"hex": "F0 7E 7F 06 01 F7"}` | SysEx a mano; devuelve la respuesta. Grabar la calibración está bloqueado |
| GET | `/api/perfiles` | | Perfiles, cuál está activo y la carpeta de los tuyos |
| POST | `/api/perfil` | `{"nombre": "luces"}` | Activa un perfil (`null` para ninguno) |
| GET | `/api/perfil/definicion?clave=` | | Definición de un perfil |
| POST | `/api/perfil/guardar` | `{"clave", "definicion"}` | Guarda un perfil del editor |
| POST | `/api/perfil/capa` | `{"clave", "asignaciones"}` | Tus cambios encima de un perfil en Python (`[]` los quita) |
| POST | `/api/perfil/escena` | `{"clave"}` · `{"clave", "borrar": true}` | Graba en el perfil cómo está el aparato, o lo quita |
| GET | `/api/acciones` | | Catálogo de acciones y condiciones del editor |
| GET | `/api/claude` | | Estado de cada sesión de Claude Code |
| POST | `/api/claude` | `{"estado": "listo"}` · `{"olvidar": true}` | Un estado a mano, u olvidar las sesiones |
| POST | `/api/claude/hook` | el JSON del hook | Lo usan los hooks de Claude Code |
| GET | `/api/casa` · `/api/casa/cosas` | | Si Home Assistant y Hue están conectados; sus luces y escenas |
| POST | `/api/casa/ha` | `{"url", "token"}` | Conecta Home Assistant |
| POST | `/api/casa/ha/buscar` · `/api/casa/hue/buscar` | `{}` | Busca en tu red (mDNS) |
| POST | `/api/casa/hue/emparejar` | `{"ip"}` | Empareja el puente (antes presiona su botón) |
| POST | `/api/casa/probar` | `{"donde", "id", "que"}` | Prueba una luz o escena |
| POST | `/api/casa/olvidar` | `{"lado": "ha"}` | Olvida una conexión |

</details>

Por seguridad, el servidor solo acepta peticiones del mismo equipo y en JSON.

### Desde otro equipo o el celular

<img src="docs/img/celular.png" alt="El tablero en un celular: el dibujo de la Starlight arriba y los controles de la base debajo, en una sola columna." width="260" align="right">

1. En el equipo de la Starlight, arranca el servidor abierto a la red y con una clave:
   `starlight serve --host 0.0.0.0 --token <tu-clave>`
2. En el otro equipo o en el celular, abre `http://<equipo>:8765/?token=<tu-clave>`.
3. Para la CLI desde otro equipo, usa `--servidor http://<equipo>:8765 --token <tu-clave>`, o las variables `STARLIGHT_URL` y `STARLIGHT_TOKEN`.

Por [Tailscale](https://tailscale.com/) funciona igual.

<br clear="right">

### Perfiles en Python

Para lo que no cabe en el editor, escribe un perfil en Python. `starlight perfil nuevo "Mi perfil"` crea `~/.starlight/perfiles/mi_perfil.py` desde una plantilla. Al guardarlo, el servidor lo recarga solo. Si tiene un error, el tablero dice en qué línea.

```python
from starlight.perfiles import control

nombre = "Mi perfil"
color = ("verde", "respira")

@control("A.play", al="presionar")
def play(e, s):
    """Play o pausa la música."""          # este texto se ve en el editor
    s.sistema.multimedia("play_pausa")      # también: teclas(), rueda(), abrir(), volumen(), volumen_app()
```

## ⚠️ Cuidado con dos órdenes

- **Modo computador** (`starlight modo-computador on --entiendo`): **sube muchísimo el volumen de salida** y la perilla Master deja de controlarlo. Antes de probarlo, baja el volumen de tus parlantes o audífonos. Para volver a la normalidad, desconecta y conecta el USB. Apagarlo con la orden no basta.
- **Grabar la calibración** (SysEx tipo 2, parámetro `12`): escribe en la memoria permanente del aparato y podría descalibrar las perillas. El servidor la bloquea.

## Lo que sabemos del aparato

Lo verificamos en una Starlight entre el 2026-11-09 y el 2026-11-10. Los mensajes de la base y de los modos salieron de estudiar el firmware `DJSTARLIGHT_S401` (el programa interno del aparato; ARM Cortex-M, sin cifrar). Si tienes otra Starlight u otro controlador Hercules, nos ayuda saber si se comporta igual.

### Mensajes MIDI

| Mensaje | Qué hace |
|---|---|
| `90 24 00` / `7F` | Base en control manual / show normal |
| `91`/`92 22 v` | Base con paleta de 12 colores: `v = 13 × efecto + color`; efecto 0–1 fijo, 2 parpadea, 3 respira |
| `91`/`92 23 v` | Base con color RGB de 7 bits (`rr ggg bb`) |
| `91`/`92 0F`–`12 7F` | Modo de los pads: Hot Cue, Loop, FX, Sampler |
| `91`/`92` notas `03 05 06 07 0C` | Luces Vinyl, Sync, Cue, Play, PFL |
| `90 01` | Luz de Bass/Filter |
| `96`/`97` nota `16·modo + 8·shift + pad` | Luces de los pads, por modo |
| `B0 7F 7F` | Pide la posición de todas las perillas y faders |

### Protocolo SysEx privado

SysEx son mensajes MIDI largos que cada fabricante define a su manera. Los de la Starlight tienen esta forma:

```
F0 00 01 4E 1B | tipo | parámetro (2 bytes, el bajo primero) | subíndice (2 bytes) | valor (4 bytes) | F7
                 1 = leer · 2 = escribir
```

| Tipo | Parámetro | Qué hace | Estado |
|---|---|---|---|
| 2 | `7F00` | **Color de la base con 7 bits por canal.** Subíndice 0 = izquierda, 1 = derecha; valor = R, G, B (0–127) y 0. Ejemplo: `F0 00 01 4E 1B 02 00 7F 00 00 7F 00 00 00 F7` (izquierda en rojo) | ✅ Verificado: los cambios de color salen más suaves |
| 1 | `14` | Lectura cruda (12 bits, 0–4095, sin calibrar) de las 9 perillas y faders, en este orden: Headphones, Master, Crossfader, Volume A, Volume B, Tempo A, Tempo B, Bass A, Bass B | ✅ Verificado: coincide con las posiciones MIDI |
| 1 | `12` | Bloques de 32 bytes (subíndices 0–7). Del 0 al 1 está **la calibración de fábrica** (centros cerca de 2047); del 2 al 7, memoria vacía (`FF`) | ✅ Leído |
| 1 | `7F7D` | 8 bytes que parecen un identificador único del chip | ✅ Leído, sin confirmar qué es |
| 1 | `20` | Un estado interno: subíndice 0 = 1, subíndice 1 = 0 | ✅ Leído, sin confirmar qué es |
| 2 | `7F7E` | Modo de funcionamiento (0 = normal; 1–4 = el computador toma los modos). Vive solo en la memoria temporal | ⚠️ Con 1, el volumen de salida sube muchísimo y la perilla Master deja de controlarlo. Escribir 0 no lo arregla: hay que desconectar y conectar el USB |
| 2 | `7F7F` | **Modo de demostración:** con 1 se prenden todas las luces y la base cambia de color sola; con 0 se apaga y la base queda oscura | ✅ Verificado; no toca el audio |
| 2 | `20` | Un interruptor interno en la memoria temporal (de fábrica vale 1) | ✅ Con 0 no se nota ningún cambio; se restaura escribiendo 1 |
| 2 | `12` | **Graba la calibración en la memoria permanente** | ⛔ No lo probamos y el servidor lo bloquea |

El aparato responde con el mismo encabezado y tipo `03`, seguido del parámetro, el subíndice y los datos en pares de 7 bits (`bajo, alto` → `bajo | alto << 7`). También responde a la consulta de identidad estándar (`F0 7E 7F 06 01 F7`).

### Otros hallazgos

- **Varios programas a la vez.** En Windows 11, varios programas pueden abrir la Starlight al mismo tiempo y todos reciben lo que tocas. Lo más probable es que venga de Windows MIDI Services. Así, Mixxx y este servidor pueden convivir.
- **Shift no tiene luz.** Los canales `94`/`95` guardan una segunda capa de luces sin efecto visible.
- **Shift + Bass/Filter no cambia las perillas.** Sin Shift, Bass/Filter pasa las perillas de «bajos» (`B1`/`B2 02`) a «filtro» (`01`). Con Shift sostenido no las cambia; por eso el servidor usa ese atajo para volver al perfil anterior.
- **La tarjeta de sonido** tiene 4 canales de salida: 1-2 para los parlantes y 3-4 para los audífonos. Windows manda el sonido normal solo a 1-2. No tiene entrada.
- **Avast Web Shield** a veces corta las respuestas de servidores locales. El servidor lo evita con conexiones persistentes. Si otra herramienta local falla igual, agrega `127.0.0.1` a las excepciones del Web Shield.

## Súmate

Este proyecto empezó como un juego y creció. Nos ayuda mucho que lo pruebes:

- **Cuéntanos cómo te fue.** Abre un [issue](https://github.com/oddradiocircle/starlight-hack/issues) con lo que funcionó y lo que no. Nos interesa sobre todo **macOS y Linux**, que aún no hemos probado.
- **Comparte tus perfiles.** Exporta tu perfil y súbelo en un issue, con una línea que diga para qué sirve.
- **¿Tienes otro controlador Hercules?** Prueba los mensajes de [Lo que sabemos del aparato](#lo-que-sabemos-del-aparato) y cuéntanos qué pasa.
- **Ideas que tenemos en lista:** un perfil mezclador (una perilla por app: Spotify, el navegador…), un puente con Mixxx y un servidor MCP para que los agentes de IA usen la Starlight.

Los cambios al código llegan por pull request. Si es algo grande, abre antes un issue para conversarlo.

## Cómo está hecho

```
starlight/
  aparato.py        habla con la Starlight: luces, base, modos y SysEx
  mapa.py           traduce los mensajes MIDI a controles con nombre
  midi/             WinMM en Windows, python-rtmidi en macOS y Linux
  servidor.py       la API HTTP y el flujo de eventos en vivo
  perfiles.py       el motor de perfiles; declarativo.py, los del editor
  sistema.py        teclado, volumen, programas al frente
  claude.py         el estado de las sesiones de Claude Code
  casa.py           Home Assistant y Philips Hue
  cli.py            los comandos starlight …
  web/              el tablero, el editor, Casa y Pruebas
scripts/            hooks de ejemplo para Claude Code y Wave
prototipos/         las primeras versiones, como referencia
```

Las decisiones de diseño de la página y su porqué están en [`starlight/web/decisiones-diseno.md`](starlight/web/decisiones-diseno.md).

## Licencia

[GPL-3.0](LICENSE) o posterior. Puedes usarlo, cambiarlo y compartirlo. Si distribuyes una versión modificada, publica su código con la misma licencia.

La fuente Inter es de Rasmus Andersson, con licencia [SIL Open Font License](starlight/web/fuentes/LICENCIA-Inter.txt).

Hercules y DJControl Starlight son marcas de Guillemot Corporation. Este proyecto no tiene relación con Guillemot ni con Hercules.

---

### In English

**starlight-hack** turns the Hercules DJControl Starlight into a general-purpose controller: keyboard shortcuts, media and per-app volume, Philips Hue and Home Assistant lights, and a status light for your Claude Code sessions (orange when a session needs you; answer its questions with the pads). It ships an HTTP API server, a CLI, a web dashboard and a profile editor, plus what we learned about the device's MIDI and private SysEx protocol. Tested on Windows 11; macOS and Linux code paths exist but are untested. Install with `pip install -e .` and run `starlight serve --abrir`. The UI is in Spanish. Issues and pull requests in English are welcome.
