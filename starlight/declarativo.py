"""Perfiles declarativos (JSON): asignaciones control → acción que se editan desde la página.

    {
      "nombre": "Mi perfil",
      "descripcion": "Qué hace",
      "color": {"color": "verde", "efecto": "respira",        # base al activar (opcional)
                "brillo": 0.6, "ciclo": 2.0},                 #   intensidad 0-1 y segundos por ciclo (opcionales)
      "estados": {"trabajando": {"color": "celeste", "efecto": "respira"}, ...},   # para Claude Code (opcional)
      "asignaciones": [
        {"control": "A.play", "al": "presionar", "shift": null,
         "si": {"claude": "esperando", "app": ["wave"]},      # condiciones (opcional)
         "accion": {"tipo": "multimedia", "valor": "play_pausa"}}
      ],
      "escena": {...}   # cómo dejar el aparato al activar (lo graba el tablero; opcional)
    }

Varias asignaciones del mismo control se ejecutan todas, cada una si se cumplen sus condiciones.
Para «si no»: otra fila con la condición contraria (por ejemplo «Claude no te necesita»).
"""
from __future__ import annotations

from . import mapa, sistema

CUANDO = {"presionar": "Al presionar", "soltar": "Al soltar", "siempre": "Siempre"}

# tipo -> (etiqueta, qué pide como valor, ayuda). El editor de la página arma sus campos con esto.
ACCIONES = {
    "multimedia": ("Tecla multimedia", "multimedia", "Play o pausa, siguiente, anterior…"),
    "teclas": ("Atajo de teclado", "teclas", "Teclas separadas por +, por ejemplo ctrl+shift+s"),
    "escribir": ("Escribir texto", "texto", "Lo escribe en la ventana activa; «y Enter» lo envía"),
    "abrir": ("Abrir programa o página", "texto", "Ruta de un programa o una dirección web"),
    "volumen": ("Volumen de Windows", "nada", "Para una perilla o fader: su posición es el volumen"),
    "volumen_app": ("Volumen de una app", "texto", "Nombre del programa, por ejemplo spotify"),
    "rueda": ("Desplazar", "direccion", "Para un jog: mueve la rueda del mouse"),
    "flechas": ("Flechas", "direccion", "Para un jog: cada pocos pasos pulsa una flecha"),
    "zoom": ("Zoom", "nada", "Para un jog: Ctrl + rueda"),
    "base": ("Color de la base", "color", "Color de la paleta y efecto"),
    "luz": ("Prender su propia luz", "efecto_luz", "Prende o hace titilar la luz del mismo botón"),
    "perfil": ("Cambiar de perfil", "perfil", "Pasa a otro perfil"),
    "casa": ("Luces de la casa", "casa", "Luces, habitaciones y escenas de Hue o Home Assistant"),
    # Claude Code: la luz de estos controles la pone el motor según si presionarlos sirve ahora
    "claude_pad": ("Claude: sesión u opción", "claude_pad",
                   "Pad de sesión: te lleva a ella. Si te necesita, los pads muestran sus opciones y este responde"),
    "claude_ir": ("Claude: ir a una sesión", "claude_ir", "Te lleva a su bloque de Wave"),
    "claude_tecla": ("Claude: tecla", "claude_tecla",
                     "Manda el atajo a la ventana del frente; si estás respondiendo desde los pads, a esa sesión"),
}
CLAUDE_IR = {"espera": "La que te necesita", "terminada": "La que terminó"}
# cuándo se prende la luz de una «Claude: tecla»: solo cuando presionarla sirve
LUZ_CLAUDE = {"interrumpir": "Si algo trabaja o te pregunta", "sesion": "Si hay sesiones",
              "confirmar": "Si hay que confirmar", "nunca": "Nunca"}
CLAUDE_PADS = 8
CASA_QUE = {"alternar": "Prende o apaga", "encender": "Prende", "apagar": "Apaga", "escena": "Activa",
            "brillo": "Brillo", "subir": "Sube", "bajar": "Baja", "paso": "Paso a paso", "color": "Color",
            "temperatura": "Temperatura", "play": "Play o pausa", "volumen": "Volumen"}
MULTIMEDIA = {"play_pausa": "Play o pausa", "siguiente": "Siguiente canción", "anterior": "Canción anterior",
              "detener": "Detener", "silencio": "Silencio", "subir": "Subir volumen", "bajar": "Bajar volumen"}
PASOS_FLECHA = 4  # pasos del jog por cada flecha
ESTADOS_CLAUDE = {"trabajando": "Trabajando", "esperando": "Te necesita", "listo": "Terminó", "inactivo": "Inactiva",
                  "error": "Error"}
# condición «Claude Code»: el estado más urgente de tus sesiones
SI_CLAUDE = {"esperando": "Te necesita", "no_esperando": "No te necesita", "trabajando": "Trabajando",
             "listo": "Terminó"}


class DefinicionInvalida(ValueError):
    pass


def catalogo() -> dict:
    return {"acciones": {k: {"etiqueta": v[0], "valor": v[1], "ayuda": v[2]} for k, v in ACCIONES.items()},
            "cuando": CUANDO, "multimedia": MULTIMEDIA, "efectos": list(mapa.EFECTOS),
            "estados_claude": ESTADOS_CLAUDE, "si_claude": SI_CLAUDE, "casa_que": CASA_QUE,
            "claude_ir": CLAUDE_IR, "luz_claude": LUZ_CLAUDE,
            "colores": [v[0] for v in mapa.PALETA.values()], "controles": mapa.catalogo()["entradas"],
            "con_luz": mapa.catalogo()["luces"]}


def validar(d: dict) -> dict:
    """Revisa una definición y devuelve una copia limpia. Los errores dicen qué arreglar."""
    if not isinstance(d, dict):
        raise DefinicionInvalida("La definición debe ser un objeto JSON.")
    nombre = str(d.get("nombre") or "").strip()
    if not nombre:
        raise DefinicionInvalida("Ponle un nombre al perfil.")
    controles = set(mapa.catalogo()["entradas"])
    limpias = validar_asignaciones(d.get("asignaciones") or [])
    color = validar_color(d["color"], "Base al activar") if d.get("color") else None
    con_luz = set(mapa.catalogo()["luces"])
    estados = {}
    for k, v in (d.get("estados") or {}).items():
        if k not in ESTADOS_CLAUDE or not isinstance(v, dict):
            continue
        estados[k] = validar_color(v, f"Estado «{ESTADOS_CLAUDE[k]}»")
        titilar = [c for c in (v.get("titilar") or []) if c in con_luz or (".pad" in c and c in controles)]
        if titilar:  # botones que titilan en ese estado, por ejemplo los que responden cuando te necesita
            estados[k]["titilar"] = list(dict.fromkeys(titilar))
    # en qué modo de pads se ven las sesiones de Claude Code (por defecto Sampler si muestra sus estados)
    sesiones_en = d.get("sesiones_en", "sampler" if estados else None)
    if sesiones_en not in mapa.MODOS:
        sesiones_en = None
    limpio = {"nombre": nombre, "descripcion": str(d.get("descripcion") or "").strip(), "color": color,
              "leer_perillas": bool(d.get("leer_perillas", True)),
              "estados": estados, "sesiones_en": sesiones_en, "asignaciones": limpias}
    # segundos por ciclo del titileo de botones y pads: el normal («te necesita») y el lento («es tu turno»)
    for clave in ("titileo", "titileo_lento"):
        if isinstance(d.get(clave), (int, float)):
            limpio[clave] = round(max(0.1, min(5.0, float(d[clave]))), 3)
    escena = validar_escena(d.get("escena"))
    if escena:
        limpio["escena"] = escena
    return limpio


def validar_color(v: dict, donde: str, por_defecto: str = "verde") -> dict:
    """Color de la paleta, efecto y, si quieres, intensidad (0 a 1) y velocidad (segundos por ciclo)."""
    if not isinstance(v, dict):
        raise DefinicionInvalida(f"{donde}: el color no es válido.")
    if v.get("rgb"):  # color libre, en hexadecimal: "#ff0080"
        try:
            r, g, b = mapa.hex_a_rgb(str(v["rgb"]))
        except ValueError:
            raise DefinicionInvalida(f"{donde}: el color libre debe ir como #rrggbb.") from None
        limpio = {"rgb": f"#{r:02x}{g:02x}{b:02x}", "efecto": v.get("efecto", "fijo")}
    else:
        try:
            color = mapa.PALETA[mapa.color_paleta(v.get("color", por_defecto))][0]
        except ValueError:
            raise DefinicionInvalida(f"{donde}: no conozco el color «{v.get('color')}».") from None
        limpio = {"color": color, "efecto": v.get("efecto", "fijo")}
    if limpio["efecto"] not in mapa.EFECTOS:
        raise DefinicionInvalida(f"{donde}: el efecto debe ser fijo, parpadeo o respira.")
    if isinstance(v.get("brillo"), (int, float)):
        limpio["brillo"] = round(max(0.0, min(1.0, float(v["brillo"]))), 3)
    if isinstance(v.get("ciclo"), (int, float)) and limpio["efecto"] != "fijo":
        limpio["ciclo"] = round(max(0.1, min(10.0, float(v["ciclo"]))), 3)
    elif isinstance(v.get("ciclo"), list) and limpio["efecto"] != "fijo":
        # un ciclo por cantidad: [1 sesión, 2, 3, 4 o más]. Así la base respira más rápido con más trabajo
        ciclos = [round(max(0.1, min(10.0, float(c))), 3) for c in v["ciclo"][:8] if isinstance(c, (int, float))]
        if ciclos:
            limpio["ciclo"] = ciclos
    for k in ("titilar",):
        if k in v:
            limpio[k] = v[k]
    return limpio


def validar_asignaciones(lista) -> list:
    """Revisa una lista de asignaciones (de un perfil o de una capa) y la devuelve limpia."""
    if not isinstance(lista, list):
        raise DefinicionInvalida("Las asignaciones deben ser una lista.")
    controles = set(mapa.catalogo()["entradas"])
    limpias = []
    for i, a in enumerate(lista, 1):
        donde = f"Asignación {i}"
        if not isinstance(a, dict):
            raise DefinicionInvalida(f"{donde}: no es válida.")
        control = str(a.get("control") or "")
        if control not in controles:
            raise DefinicionInvalida(f"{donde}: elige un control.")
        al = a.get("al", "siempre")
        if al not in CUANDO:
            raise DefinicionInvalida(f"{donde}: «cuándo» debe ser presionar, soltar o siempre.")
        acc = a.get("accion") or {}
        tipo = acc.get("tipo")
        if tipo not in ACCIONES:
            raise DefinicionInvalida(f"{donde}: elige una acción.")
        valor = acc.get("valor")
        if tipo == "multimedia" and valor not in MULTIMEDIA:
            raise DefinicionInvalida(f"{donde}: elige qué tecla multimedia.")
        if tipo == "teclas":
            teclas = [t.strip() for t in (valor if isinstance(valor, list) else str(valor or "").split("+")) if t.strip()]
            if not teclas:
                raise DefinicionInvalida(f"{donde}: escribe el atajo, por ejemplo ctrl+c.")
            for t in teclas:
                try:
                    sistema._vk(t)
                except ValueError:
                    raise DefinicionInvalida(f"{donde}: no conozco la tecla «{t}».") from None
            valor = teclas
        if tipo in ("escribir", "abrir", "volumen_app") and not str(valor or "").strip("\n"):
            raise DefinicionInvalida(f"{donde}: falta el texto.")
        if tipo in ("rueda", "flechas") and valor not in ("vertical", "horizontal"):
            valor = "vertical"
        if tipo == "base":
            valor = validar_color(valor or {}, donde, "rojo")
        if tipo == "luz":
            valor = "parpadeo" if valor == "parpadeo" else "fijo"
        if tipo == "perfil" and not str(valor or "").strip():
            raise DefinicionInvalida(f"{donde}: elige a qué perfil pasar.")
        if tipo == "claude_pad":
            try:
                valor = int(valor)
            except (TypeError, ValueError):
                valor = 0
            if not 1 <= valor <= CLAUDE_PADS:
                raise DefinicionInvalida(f"{donde}: el número de sesión u opción va de 1 a {CLAUDE_PADS}.")
        if tipo == "claude_ir" and valor not in CLAUDE_IR:
            raise DefinicionInvalida(f"{donde}: elige a qué sesión ir.")
        if tipo == "claude_tecla":
            v = valor if isinstance(valor, dict) else {}
            teclas = [str(t).strip() for t in (v.get("teclas") or []) if str(t).strip()]
            if not teclas:
                raise DefinicionInvalida(f"{donde}: escribe el atajo, por ejemplo esc.")
            for t in teclas:
                try:
                    sistema._vk(t)
                except ValueError:
                    raise DefinicionInvalida(f"{donde}: no conozco la tecla «{t}».") from None
            valor = {"teclas": teclas, "luz": v.get("luz") if v.get("luz") in LUZ_CLAUDE else "sesion"}
        if tipo == "casa":
            v = valor if isinstance(valor, dict) else {}
            if v.get("donde") not in ("ha", "hue") or not str(v.get("id") or "").strip():
                raise DefinicionInvalida(f"{donde}: elige qué luz o escena de la casa.")
            que = v.get("que") or "alternar"
            if que not in CASA_QUE:
                raise DefinicionInvalida(f"{donde}: elige qué hacer con la luz.")
            valor = {"donde": v["donde"], "id": str(v["id"]), "nombre": str(v.get("nombre") or v["id"]), "que": que}
            if que in ("brillo", "temperatura", "volumen") and isinstance(v.get("nivel"), (int, float)):
                valor["nivel"] = round(max(0.0, min(1.0, float(v["nivel"]))), 3)  # para un botón: lo deja en ese nivel
            if que in ("subir", "bajar", "paso"):
                valor["paso"] = max(1, min(100, int(v.get("paso") or (2 if que == "paso" else 10))))  # por ciento
            if que == "color":
                try:
                    r, g, b = mapa.hex_a_rgb(str(v.get("rgb") or "#ffffff"))
                except ValueError:
                    raise DefinicionInvalida(f"{donde}: el color debe ir como #rrggbb.") from None
                valor["rgb"] = f"#{r:02x}{g:02x}{b:02x}"
        shift = a.get("shift")
        limpia = {"control": control, "al": al, "shift": shift if shift in (True, False) else None,
                  "accion": {"tipo": tipo, "valor": valor}}
        si = _validar_si(a.get("si"), donde)
        if si:
            limpia["si"] = si
        limpias.append(limpia)
    return limpias


def _validar_si(si, donde) -> dict:
    """Condiciones de una asignación: estado de Claude Code y app al frente."""
    if not si:
        return {}
    if not isinstance(si, dict):
        raise DefinicionInvalida(f"{donde}: las condiciones no son válidas.")
    limpio = {}
    if si.get("claude"):
        if si["claude"] not in SI_CLAUDE:
            raise DefinicionInvalida(f"{donde}: condición de Claude Code desconocida.")
        limpio["claude"] = si["claude"]
    apps = si.get("app")
    if isinstance(apps, str):
        apps = apps.split(",")
    apps = [str(x).strip().lower().removesuffix(".exe") for x in (apps or []) if str(x).strip()]
    if apps:
        limpio["app"] = list(dict.fromkeys(apps))
    return limpio


def validar_escena(e) -> dict:
    """Cómo dejar el aparato al activar un perfil: base, brillo, velocidad, luces y modos de los pads."""
    if not e:
        return {}
    if not isinstance(e, dict):
        raise DefinicionInvalida("La escena grabada no es válida.")
    limpia = {}
    b = e.get("base")
    if isinstance(b, dict):
        if b.get("modo") == "auto" or b.get("auto"):
            limpia["base"] = {"modo": "auto"}
        else:
            lados = {}
            for lado in ("izq", "der"):
                v = b.get(lado)
                if isinstance(v, dict) and isinstance(v.get("rgb"), list) and len(v["rgb"]) == 3:
                    lados[lado] = {"rgb": [max(0, min(255, int(c))) for c in v["rgb"]],
                                   "efecto": v.get("efecto") if v.get("efecto") in mapa.EFECTOS else "fijo"}
            if lados:
                limpia["base"] = {"modo": "manual", **lados}
    if isinstance(e.get("brillo"), (int, float)):
        limpia["brillo"] = max(0.0, min(1.0, float(e["brillo"])))
    if isinstance(e.get("ritmo"), dict):
        limpia["ritmo"] = {k: max(0.1, min(10.0, float(v))) for k, v in e["ritmo"].items()
                           if k in ("parpadeo", "respira", "botones", "botones_lento") and isinstance(v, (int, float))}
    if isinstance(e.get("modos"), dict):
        limpia["modos"] = {d: m for d, m in e["modos"].items() if d in ("A", "B") and m in mapa.MODOS}
    if isinstance(e.get("luces"), dict):  # clave de la luz -> "fijo" o "parpadeo"
        validas = set(mapa.catalogo()["luces"])
        luces = {}
        for k, v in e["luces"].items():
            partes = str(k).split(".")
            es_pad = len(partes) == 3 and partes[0] in ("A", "B") and partes[1] in [f"pad{i}" for i in range(1, 5)] \
                and partes[2] in mapa.MODOS
            if k in validas or es_pad:
                luces[k] = v if v in ("parpadeo", "lento") else "fijo"
        limpia["luces"] = luces
    return limpia


def cumple(si: dict, s) -> bool:
    """¿Se cumplen las condiciones? s es el contexto del perfil."""
    c = si.get("claude")
    if c:
        actual = s._motor._claude_estado
        if c == "no_esperando":
            if actual == "esperando":
                return False
        elif actual != c:
            return False
    apps = si.get("app")
    if apps:
        frente = sistema.app_al_frente()
        if not frente or not any(a in frente for a in apps):
            return False
    return True


def _funcion(a: dict):
    """Convierte una asignación en la función (evento, contexto) que usa el motor."""
    tipo, v, control = a["accion"]["tipo"], a["accion"]["valor"], a["control"]
    if tipo == "multimedia":
        return lambda e, s: s.sistema.multimedia(v)
    if tipo == "teclas":
        return lambda e, s: s.sistema.teclas(*v)
    if tipo == "escribir":
        return lambda e, s: s.sistema.escribir(v)
    if tipo == "abrir":
        return lambda e, s: s.sistema.abrir(v)
    if tipo == "volumen":
        return lambda e, s: s.sistema.volumen(e.valor) if e.clase == "continuo" else None
    if tipo == "volumen_app":
        return lambda e, s: s.sistema.volumen_app(v, e.valor) if e.clase == "continuo" else None
    if tipo == "rueda":
        return lambda e, s: (s.sistema.rueda(e.pasos / 3, horizontal=True) if v == "horizontal"
                             else s.sistema.rueda(-e.pasos / 3))
    if tipo == "zoom":
        return lambda e, s: s.sistema.zoom(e.pasos / 3)
    if tipo == "flechas":
        def flechas(e, s):
            acum = s.estado.setdefault(f"flechas.{control}", 0) + e.pasos
            while abs(acum) >= PASOS_FLECHA:
                paso = 1 if acum > 0 else -1
                acum -= paso * PASOS_FLECHA
                if v == "horizontal":
                    s.sistema.teclas("derecha" if paso > 0 else "izquierda")
                else:
                    s.sistema.teclas("abajo" if paso > 0 else "arriba")
            s.estado[f"flechas.{control}"] = acum
        return flechas
    if tipo == "base":
        return lambda e, s: s._motor.pintar_color(v)
    if tipo == "luz":
        def luz(e, s):
            clave = control if ".pad" not in control else f"{control}.{e.modo or 'hotcue'}"
            encendida = not s.aparato.estado["luces"].get(clave, False)
            if ".pad" in control:
                deck, pad = control.split(".pad")
                s.aparato.luz_pad(deck, int(pad), encendida, e.modo, efecto=v)
            elif control in mapa.catalogo()["luces"]:
                s.aparato.luz(control, encendida, v)
        return luz
    if tipo == "perfil":
        return lambda e, s: s._motor.activar(v)
    if tipo == "claude_pad":
        return lambda e, s: s._motor.piloto.pad(v, e)
    if tipo == "claude_ir":
        return lambda e, s: s._motor.piloto.ir(v)
    if tipo == "claude_tecla":
        return lambda e, s: s._motor.piloto.tecla(v["teclas"])
    if tipo == "casa":
        def casa(e, s):
            c = getattr(s._motor, "casa", None)
            if c is None:
                return
            que = v["que"]
            if que in ("brillo", "temperatura", "volumen"):
                if e.clase == "continuo":  # una perilla o un fader: su posición es el nivel
                    c.orden(v["donde"], v["id"], que, e.valor, continua=True)
                elif "nivel" in v:         # un botón: lo deja en el nivel elegido
                    c.orden(v["donde"], v["id"], que, v["nivel"])
                return
            if que == "paso":              # el jog: cada paso sube o baja un poco
                if e.clase == "jog" and e.pasos:
                    c.orden(v["donde"], v["id"], "paso", e.pasos * v["paso"], sumar=True)
                return
            if que in ("subir", "bajar"):
                return c.orden(v["donde"], v["id"], que, v["paso"])
            c.orden(v["donde"], v["id"], que, mapa.hex_a_rgb(v["rgb"]) if que == "color" else None)
        return casa
    raise DefinicionInvalida(f"Acción desconocida: {tipo}")


def construir_asignaciones(asignaciones: list) -> list:
    """(patrón, función, al, shift) por asignación; las condiciones van dentro de la función."""
    salida = []
    for a in asignaciones:
        fn, si = _funcion(a), a.get("si")
        if si:
            fn = (lambda f, c: (lambda e, s: f(e, s) if cumple(c, s) else None))(fn, si)
        salida.append((a["control"], fn, a["al"], a["shift"]))
    return salida


def luces_de(asignaciones: list) -> list:
    """Controles con luz que tienen una acción: se prenden al activar, para que se vea qué está asignado."""
    con_luz = set(mapa.catalogo()["luces"])
    # la luz de «luz» y la de los controles con una acción de Claude las manejan ellas mismas
    # (la de Claude, según si presionar sirve ahora; aunque el control tenga otra acción con Shift)
    de_claude = set(luces_claude(asignaciones))
    return sorted({a["control"] for a in asignaciones
                   if a["accion"]["tipo"] != "luz" and a["control"] not in de_claude
                   and (a["control"] in con_luz or ".pad" in a["control"])})


def luces_claude(asignaciones: list) -> dict:
    """Controles con una acción de Claude (sin Shift) -> la acción: el motor les pone la luz."""
    salida = {}
    for a in asignaciones:
        if a["accion"]["tipo"].startswith("claude_") and a["shift"] is not True:
            salida.setdefault(a["control"], a["accion"])
    return salida


def construir(d: dict):
    """Devuelve (manejadores, al_entrar, luces que prende) para el motor de perfiles."""
    manejadores = construir_asignaciones(d["asignaciones"])
    prender = luces_de(d["asignaciones"])

    def al_entrar(s):
        if any(".pad" in c for c in prender):
            for deck in {c[0] for c in prender if ".pad" in c}:
                s.aparato.modo_pads(deck, "hotcue")
        for c in prender:  # prende la luz de lo que tiene una acción, para que se vea qué está asignado
            s.luz(c)
    return manejadores, al_entrar, prender
