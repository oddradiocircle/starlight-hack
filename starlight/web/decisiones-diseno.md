# Decisiones de diseño · página de starlight

La más reciente arriba. Ninguna está aprobada todavía: todas son supuestos que falta revisar con el autor.

Desde D23 también se anotan decisiones del aparato (luces y botones), no solo de la página.

### D31 — En el pad de una sesión, la velocidad del titileo dice la urgencia

- **Fecha:** 2026-11-11
- **Contexto:** el autor: «¿cómo sabemos cuándo una sesión terminó? Se queda esperando un input, pero no está terminada». En los pads, una sesión que terminó su turno se veía fija, igual que una que trabaja. Aclaró: solo los pads de las sesiones; la base sigue siendo general.
- **Escogida:** titila rápido = te necesita ya (pregunta, permiso, error); titila lento = terminó y es tu turno, y no la has visto; fijo = abierta (trabajando o ya vista); apagado = no hay sesión. Cada luz titila a su propio ritmo («botones» 0,8 s y «botones_lento» 2 s). Deja de titilar lento cuando vas a verla, también con el mouse: mientras haya sesiones sin ver, el servidor lee cada segundo qué terminal tiene el foco en Wave. No titila hasta que le escribas, porque una sesión que dejaste quieta titilaría para siempre.
- **Aprobó:** el autor pidió distinguirlo en los pads (2026-11-11); el «hasta que vayas a verla» es la recomendación, sin objeción.

### D30 — Los botones titilan a su propio ritmo

- **Fecha:** 2026-11-11
- **Contexto:** el autor preguntó si se puede cambiar la frecuencia del titileo de los botones. Los botones usaban el ritmo del parpadeo de la base, que cambia con cada estado (1 s, 0,6 s, 0,25 s en error) y con la escena grabada (0,24 s).
- **Escogida:** un ritmo aparte, «botones», 0,8 s por ciclo en el perfil Claude Code (clave `titileo`). También por `starlight ritmo botones` y `/api/ritmo`. Así el titileo de un botón siempre significa lo mismo, sin importar qué hace la base.
- **Aprobó:** supuesto, falta aprobar el valor (0,8 s).

### D29 — Ir a una sesión con los atajos de Wave, y confirmar antes de escribir

- **Fecha:** 2026-11-11
- **Contexto:** el autor tocaba un pad y Wave no lo llevaba a la sesión. `wsh focusblock` solo enfoca bloques de la pestaña de quien lo llama, y sus sesiones están en otras pestañas.
- **Opciones:** A un proceso por sesión que se enfoque a sí mismo con sus propias credenciales (tampoco cambia de pestaña); B los atajos de Wave (Alt + N, Ctrl + Shift + N) y leer su base de datos para saber los números y confirmar.
- **Escogida:** B. Probado en el aparato real del autor: cambió de pestaña y Wave lo confirmó en unos 140 ms. No necesita credenciales de Wave: el servidor ya no tiene que arrancar dentro de Wave. Una respuesta se escribe solo si la base de datos confirma la pestaña y el bloque; si no, la página dice por qué y la sesión sigue esperando. Límite: solo Windows y hasta 9 pestañas y 9 bloques por pestaña.
- **Aprobó:** supuesto, falta aprobar.

### D28 — Responder apaga el titileo apenas escribe

- **Fecha:** 2026-11-11
- **Contexto:** el hook de Claude Code tarda cerca de 1 s después de una respuesta; mientras, el pad y la base seguían titilando.
- **Escogida:** el piloto marca la espera como terminada apenas escribe la respuesta (`FinEspera`). Solo si la escribió: si Wave no quedó al frente, la sesión sigue titilando, porque sigue esperándote. El «No» de un permiso y el Esc cuentan como cancelación (la sesión queda inactiva, no trabajando).
- **Aprobó:** supuesto, falta aprobar.

### D27 — Las teclas van a la ventana del frente, salvo en Responder

- **Fecha:** 2026-11-11
- **Contexto:** se propuso que Play, Cue y Sync actuaran sobre la «sesión actual» (la última elegida desde el control).
- **Opciones:** A ir siempre a la sesión actual; B la ventana del frente; C la del frente, salvo en Responder.
- **Escogida:** C. Si cambias de sesión con el mouse, el control no se entera, y A mandaría un Enter o un Esc a otra sesión. En Responder la sesión se sabe con certeza.
- **Aprobó:** supuesto, falta aprobar (cambia lo que se le propuso al autor).

### D26 — El «No» del permiso va en el pad 8; ninguna opción de permiso titila

- **Fecha:** 2026-11-11
- **Contexto:** el diálogo de permisos tiene 1 Sí, 2 Sí y no volver a preguntar, 3 No.
- **Escogida:** Sí en el pad 1, «Sí, siempre» en el 2 y No en el 8, lejos. Un error ahí cuesta caro, y el control no debe empujar a aprobar.
- **Aprobó:** propuesto al autor el 2026-11-11; respondió «organiza…» sin objetarlo.

### D25 — La vista de los pads es el modo de pads

- **Fecha:** 2026-11-11
- **Contexto:** idea del autor: usar Hot Cue y Loop, fijos y titilando. Prueba en el aparato (2026-11-11): cada pad muestra solo las luces del modo activo de su deck.
- **Escogida:** Sesiones = Hot Cue; Responder = Loop. La luz del botón de modo dice en qué vista estás, y presionar Hot Cue o Loop cambia de vista. Las 8 sesiones caben siempre; las opciones aparecen solo cuando importan.
- **Aprobó:** el autor pidió los 8 pads para sesiones y que al ir a una sesión los pads muestren sus opciones (2026-11-11).

### D24 — La base: un color, intensidad y ritmo

- **Fecha:** 2026-11-11
- **Contexto:** el autor pidió el color de Claude, «minimalista», jugando con intensidad y frecuencia, y que respire más rápido con más terminales trabajando.
- **Escogida:** un solo color. Primero `#ff4423`: el de Claude (`#D97757`) pasado a luz lineal, porque el LED no aplica la curva del monitor y sin convertir se ve lavado. Al final, `#ff1100` (ver abajo). Respira = trabaja (4 / 3 / 2,2 / 1,6 s según cuántas); titila = te necesita (más rápido si son varias); fija brillante = respondiendo; fija media = terminó; tenue = inactiva; titila muy rápido = error. Cuenta las sesiones que trabajan, no las abiertas: una abierta y quieta no es actividad.
- **Tope de intensidad: 50 %.** Al 80 y al 100 % el autor vio la base «muy blanca»; le gustó `#ff4423` al 50 % (estado «terminó» en ese momento).
- **Solo intensidades que conservan el tono.** El LED recibe 7 bits por canal y la intensidad va al cuadrado: al 30 % el color ya se veía distinto, al 12 % era rojo puro y al 6 % la base quedaba apagada.
- **Color final: `#ff1100`.** Aun así `#ff4423` se veía «medio blanco» quieto (respirando, bien). Dos cambios a la vez lo resolvieron: el servidor reenvía el color fijo cada medio segundo, y el autor eligió `#ff1100` en el editor (casi sin verde, sin azul). Intensidades que conservan su proporción (16 a 1): 100 % (127, 8, 0), 71 % (64, 4, 0), 50 % (32, 2, 0) y 36 % (16, 1, 0). Quedó: trabajando, te necesita, respondiendo y error al 100 %; terminó al 71 %; inactiva al 50 %; sin sesiones al 36 %.
- **Aprobó:** el autor eligió `#ff1100` en el aparato y aprobó las intensidades: «sí… ya no cambia el color» (2026-11-11).

### D23 — Cada luz dice algo

- **Fecha:** 2026-11-11
- **Contexto:** el autor: «que la luz indique algo, me lleve, me informe».
- **Escogida:** fija = presionar sirve ahora; titila = te necesita o es lo recomendado; apagada = ahora no hace nada. Las acciones «Claude: …» traen su propia regla de luz y el motor la aplica sola; por eso esos controles no se prenden al activar el perfil.
- **Aprobó:** idea del autor (2026-11-11).

### D22 — Casa: el token no vuelve a la página

- **Fecha:** 2026-11-10
- **Contexto:** conectar Home Assistant pide un token, que es una credencial.
- **Escogida:** se pega una vez en la página local y se guarda solo en el equipo. La página solo sabe si hay conexión; el campo dice «Ya hay un token guardado».
- **Aprobó:** supuesto, falta aprobar.

### D21 — Sesiones de Claude Code: la más urgente primero

- **Fecha:** 2026-11-10
- **Contexto:** El autor tiene 3 o más sesiones abiertas a la vez.
- **Escogida:** un bloque en el tablero, visible solo si hay sesiones. Cada fila lleva un punto de color, la carpeta, el estado en palabras y hace cuánto. Primero va la que te necesita.
- **Aprobó:** supuesto, falta aprobar.

### D20 — En el tablero, un clic en el dibujo hace una de dos cosas

- **Fecha:** 2026-11-10
- **Contexto:** El autor pidió cambiar lo que hace un control desde el tablero.
- **Escogida:** bajo el dibujo, un selector «Luces | Acciones». En Acciones, el mismo panel del editor aparece bajo el dibujo, con «Guardar en <perfil>».
- **Aprobó:** supuesto, falta aprobar.

### D19 — Intensidad y velocidad dicen «Sin cambiar» hasta que las muevas

- **Fecha:** 2026-11-10
- **Contexto:** El autor pidió elegir intensidad y frecuencia junto al efecto. Un perfil viejo no las trae.
- **Escogida:** si no las mueves, el perfil no cambia el brillo ni la velocidad del aparato, y la página lo dice. Junto a los 12 colores hay una muestra con arcoíris para un color libre.
- **Aprobó:** El autor pidió el color libre con selector (2026-11-10).

### D18 — «Así se ve»: la Starlight en pequeño al bajar

- **Fecha:** 2026-11-10
- **Contexto:** idea del autor. Al bajar por el editor se pierde de vista el aparato.
- **Escogida:** aparece flotante en la esquina cuando el dibujo grande sale de la pantalla. Simula la base y las luces al activar y en cada estado de Claude Code. Al pasar por un estado, lo muestra. No se toca: solo se mira.
- **Aprobó:** supuesto, falta aprobar.

### D17 — Borde oscuro: tiene una acción; grafito: el que editas

- **Fecha:** 2026-11-10
- **Contexto:** el naranja ya significa «luz encendida» (D2).
- **Escogida:** en el editor, un control con acción lleva el borde en tinta y el control elegido se rellena en grafito, como cuando se presiona.
- **Aprobó:** supuesto, falta aprobar.

### D16 — El editor gira alrededor del dibujo

- **Fecha:** 2026-11-10
- **Contexto:** el editor era una lista larga de listas desplegables. el autor dijo que elegir colores así era muy pobre.
- **Escogida:** el mismo dibujo del tablero para elegir un control, un panel debajo con lo que hace y un resumen de todo el perfil. Botones segmentados en vez de listas cuando hay pocas opciones, y muestras de color como en el tablero.
- **Aprobó:** el autor: «me encanta la nueva ui de editor» (2026-11-10).

### D15 — No se agrandan los pads (hallazgo de la revisión rechazado)

- **Fecha:** 2026-11-10
- **Contexto:** la revisión con ojo fresco pidió duplicar los pads porque los veía pequeños frente a los jogs.
- **Escogida:** mantenerlos. En la referencia de oro el jog mide unas 3,4 veces el ancho de un pad; en el dibujo, 3,7. La proporción ya es la del aparato.
- **Aprobó:** supuesto, falta aprobar.

### D14 — «Último control» guarda los 6 anteriores

- **Fecha:** 2026-11-10
- **Contexto:** el bloque tenía dos líneas y un vacío grande debajo; el autor trabaja con los códigos MIDI.
- **Escogida:** el último en grande y los 6 anteriores en una lista callada, cada uno con su código. Una perilla o un jog que se mueve actualiza su línea en vez de llenar la lista.
- **Aprobó:** supuesto, falta aprobar.

### D13 — Sin aparato o sin servidor, el aviso va sobre el dibujo

- **Fecha:** 2026-11-10
- **Contexto:** el estado que bloquea toda la página era el texto más pequeño (arriba a la derecha) y no decía qué hacer. Además, la base seguía en arcoíris sin datos.
- **Escogida:** el dibujo y la consola se atenúan con una sola regla; encima del dibujo va un aviso con el problema y el paso a seguir. La base se ve gris y «Último control» dice «Esperando la conexión». El estado de arriba a la derecha solo se muestra cuando todo está bien.
- **Aprobó:** supuesto, falta aprobar.

### D12 — Los controles se llaman como están impresos en el aparato

- **Fecha:** 2026-11-10
- **Contexto:** la revisión encontró idiomas mezclados («Bass/Filter» junto a «Bajos», «Master» junto a «Volumen»).
- **Escogida:** los nombres de los controles son los impresos en el aparato (Volume, Bass o Filter según el modo, Headphones, Master, Tempo), igual que Daniel ya dice «Hot Cue», «Shift» y «PFL». El resto de la interfaz va en español.
- **Aprobó:** supuesto, falta aprobar.
- **Reemplaza:** D9 en lo que toca a «Auriculares».

### D11 — Shift con el mismo estilo que los demás botones

- **Fecha:** 2026-11-10
- **Contexto:** D6 dibujaba Shift sin relleno. La revisión lo vio como un cuarto estado que no es ni apagado, ni encendido, ni presionado.
- **Escogida:** el mismo estilo que los demás botones, pero sin efecto al pasar el puntero ni clic. Se rellena en grafito cuando se presiona en el aparato.
- **Aprobó:** supuesto, falta aprobar.
- **Reemplaza:** D6.

### D10 — Sin versión en la cabecera

- **Fecha:** 2026-11-10
- **Contexto:** la cabecera mostraba «starlight v0.1.0».
- **Opciones:** A mostrar la versión; B quitarla (la da `starlight --version`).
- **Escogida:** B. La versión es un rastro del sistema y compite con el estado de conexión, que es lo único que importa arriba.
- **Aprobó:** supuesto, falta aprobar.

### D9 — «PFL» en los botones y «Auriculares» en la perilla

- **Fecha:** 2026-11-10
- **Contexto:** el aparato tiene botones de escucha previa por deck y una perilla de volumen de audífonos. El autor usó «Auriculares (PFL)» y nombró la perilla «Headphones volume».
- **Opciones:** A «Auriculares» en los dos; B «PFL» en los botones y «Auriculares» en la perilla.
- **Escogida:** B. Una palabra no puede significar dos cosas en la misma pantalla.
- **Aprobó:** supuesto, falta aprobar.

### D8 — La franja de la base parpadea o respira como el aparato (excepción a «nada titila»)

- **Fecha:** 2026-11-10
- **Contexto:** la regla de movimiento dice que nada titila para alertar.
- **Escogida:** la franja reproduce el efecto real de la base (parpadea, respira o el show normal), porque muestra el estado del aparato y no es una alerta. Con «movimiento reducido» queda quieta.
- **Aprobó:** supuesto, falta aprobar.

### D7 — Letra Inter dentro del paquete

- **Fecha:** 2026-11-10
- **Contexto:** la letra debe estar cargada de verdad y el servidor debe funcionar sin internet, en Windows, macOS y Linux.
- **Opciones:** A letra del sistema; B Google Fonts; C Inter (licencia OFL) incluida en `fuentes/`.
- **Escogida:** C. Es una grotesca neutra en la línea de Braun y no depende de la red.
- **Aprobó:** supuesto, falta aprobar.

### D6 — Shift se dibuja como impreso

- **Fecha:** 2026-11-10
- **Contexto:** Shift no tiene luz (verificado en el aparato), así que hacer clic en él no hace nada.
- **Escogida:** sin relleno, solo con su borde. Se rellena en grafito cuando se presiona en el aparato. Lo que no responde no debe parecer tocable.
- **Aprobó:** supuesto, falta aprobar.

### D5 — Los códigos MIDI solo en «Último control»

- **Fecha:** 2026-11-10
- **Contexto:** los códigos («91 0F») son palabras que el autor usa con naturalidad, pero llenarían el dibujo.
- **Escogida:** el nombre en palabras («Pad 3 A · Hot Cue») y, al lado, el código en monoespaciada callada. Nada de códigos sobre el dibujo.
- **Aprobó:** supuesto, falta aprobar.

### D4 — En el celular, el dibujo solo se mira

- **Fecha:** 2026-11-10
- **Contexto:** a 390 px los pads del dibujo miden unos 18 px, muy por debajo de 44 px.
- **Opciones:** A dibujo tocable y diminuto; B dibujo como vista en vivo y acciones abajo con 44 px; C rehacer el dibujo en vertical.
- **Escogida:** B. Las luces de cada botón quedan solo para el escritorio; en el celular se manejan la base y los modos. Si hace falta, C es la siguiente versión.
- **Aprobó:** supuesto, falta aprobar.

### D3 — Mayúscula inicial en todas las etiquetas

- **Fecha:** 2026-11-10
- **Contexto:** la primera versión usaba minúsculas en el dibujo (más «Braun») y mayúscula inicial en la consola, así que «hot cue» y «Hot Cue» convivían.
- **Escogida:** mayúscula inicial en todo. Un mismo concepto se escribe igual en todo el producto.
- **Aprobó:** supuesto, falta aprobar.
- **Reemplaza:** la versión inicial en minúsculas.

### D2 — Un solo acento: naranja significa «luz encendida»

- **Fecha:** 2026-11-10
- **Contexto:** en el aparato cada luz tiene su color (Sync rojo, Play verde, pads azules).
- **Opciones:** A los colores reales de cada luz; B un solo acento para «encendida» y grafito para «presionado».
- **Escogida:** B. Cada estado tiene una sola señal y la página respira. La única excepción es la franja de la base, que muestra su color real porque el color es justamente la información.
- **Aprobó:** supuesto, falta aprobar.

### D1 — La referencia de oro es el aparato

- **Fecha:** 2026-11-10
- **Contexto:** la página dibuja la Starlight en abstracto.
- **Escogida:** foto de la distribución del aparato (manual de VirtualDJ). Se tomaron la silueta y las posiciones: tempo en los extremos, volumen y bajos como perillas, pads en 2×2 entre el jog y el mezclador, y Sync, Cue y Play bajo cada jog. No se tomaron logos ni marca.
- **Aprobó:** supuesto, falta aprobar.
