"""Motor de perfiles.

Un perfil es un archivo .py que dice qué hace cada control:

    from starlight.perfiles import control

    nombre = "Mi perfil"
    color = ("verde", "fijo")          # color de la base cuando está activo

    def al_entrar(s): ...              # opcional
    def al_salir(s): ...               # opcional

    @control("A.play", al="presionar")
    def play(e, s):
        s.sistema.multimedia("play_pausa")

`e` es el evento (e.control, e.valor, e.presionado, e.pasos, e.shift, e.modo) y `s` el contexto
(s.sistema, s.aparato, s.luz(), s.base(), s.base_rgb(), s.cada(), s.estado).

Los perfiles incluidos están en starlight/perfiles_incluidos. Los tuyos van en ~/.starlight/perfiles
(o en la carpeta de STARLIGHT_PERFILES) y se recargan solos al guardarlos.
Shift + Vinyl en el aparato pasa al siguiente perfil.
"""
from __future__ import annotations

import fnmatch
import importlib.util
import json
import os
import queue
import sys
import threading
import time
import traceback
from pathlib import Path

from . import declarativo, mapa, sistema
from .aparato import AparatoDesconectado
from .casa import Casa
from .claude import Sesiones

INCLUIDOS = Path(__file__).resolve().parent / "perfiles_incluidos"
HOGAR = Path(os.environ.get("STARLIGHT_HOGAR") or Path.home() / ".starlight")
DE_USUARIO = Path(os.environ.get("STARLIGHT_PERFILES") or HOGAR / "perfiles")
ESTADO = HOGAR / "estado.json"
CAPAS = HOGAR / "capas"  # cambios tuyos encima de un perfil en Python: capas/<clave>.json


def control(*nombres: str, al: str = "siempre", shift: bool | None = None):
    """Asocia una función a uno o más controles. Acepta comodines: "A.pad*", "*.play".

    al: "presionar" (solo al bajar un botón o pad), "soltar", o "siempre".
    shift: True (solo con Shift), False (solo sin Shift) o None (da igual).
    """
    if al not in ("presionar", "soltar", "siempre"):
        raise ValueError("al debe ser 'presionar', 'soltar' o 'siempre'")

    def decorar(fn):
        fn.__dict__.setdefault("_starlight", []).extend((n, al, shift) for n in nombres)
        return fn
    return decorar


class Evento:
    def __init__(self, d: dict):
        self.control, self.clase, self.valor = d["control"], d["clase"], d["valor"]
        self.shift, self.extra, self.crudo = d.get("shift", False), d.get("extra", {}), d.get("crudo", [])

    @property
    def presionado(self) -> bool:
        return self.clase in ("boton", "pad") and self.valor > 0

    @property
    def pasos(self) -> int:
        return int(self.valor) if self.clase == "jog" else 0

    @property
    def modo(self):
        return self.extra.get("modo")

    def __repr__(self):
        return f"<{self.control} {self.valor}{' shift' if self.shift else ''}>"


class Contexto:
    """Lo que un perfil puede usar. Al salir del perfil apaga sus luces y detiene sus tareas."""

    def __init__(self, motor: "Motor", perfil: "Perfil"):
        self.aparato, self.sistema, self.perfil = motor.aparato, sistema, perfil
        self.estado: dict = {}
        self._motor = motor
        self._vivo = True
        self._luces: set = set()
        self._ultimo_rgb: dict = {}
        self._ultimo_aviso = 0.0

    # luces y base
    def luz(self, control: str, encendida: bool = True, modo: str | None = None, efecto: str = "fijo"):
        """Prende o apaga la luz de un botón o pad. efecto="parpadeo" la hace titilar."""
        try:
            if ".pad" in control:
                deck, pad = control.split(".pad")
                self.aparato.luz_pad(deck, int(pad), encendida, modo, efecto=efecto)
            else:
                self.aparato.luz(control, encendida, efecto)
        except AparatoDesconectado:
            return
        (self._luces.add if encendida else self._luces.discard)((control, modo))

    def base(self, color, efecto: str = "fijo", lado: str = "ambos"):
        try:
            self.aparato.base_color(color, efecto, lado)
        except AparatoDesconectado:
            pass

    def base_rgb(self, r: int, g: int, b: int, lado: str = "ambos", rapido: bool = False):
        """Color libre. Con rapido=True solo envía si cambió y avisa a la página como mucho 8 veces por segundo."""
        if not rapido:
            try:
                return self.aparato.base_rgb(r, g, b, lado)
            except AparatoDesconectado:
                return
        valor = mapa.rgb_completo(int(r), int(g), int(b))
        lados = [d for d in mapa.LADOS[lado] if self._ultimo_rgb.get(d) != valor]
        if not lados:
            return
        try:
            if not self._ultimo_rgb:
                self.aparato.parar_animacion()
                self.aparato.enviar([(*mapa.BASE_AUTO, 0)], avisar=False)
        except AparatoDesconectado:
            return
        for d in lados:
            self.aparato.color_rapido(mapa.LADO_DE_DECK[d], valor)
        for d in lados:
            self._ultimo_rgb[d] = valor
        ahora = time.time()
        if ahora - self._ultimo_aviso > 0.12:
            self._ultimo_aviso = ahora
            self.aparato.anunciar_base({mapa.LADO_DE_DECK[d]: list(v) for d, v in self._ultimo_rgb.items()})

    # tareas repetidas
    def cada(self, segundos: float, fn):
        """Llama fn(s) cada `segundos` mientras el perfil esté activo."""
        def bucle():
            while self._vivo:
                inicio = time.time()
                if self._motor.pausado:
                    time.sleep(0.05)
                    continue
                try:
                    fn(self)
                except Exception as e:  # el error se ve en la página y en la consola
                    self._motor._error(self.perfil, e)
                    time.sleep(1)
                time.sleep(max(0.0, segundos - (time.time() - inicio)))
        threading.Thread(target=bucle, daemon=True, name=f"perfil-{self.perfil.clave}").start()

    def _cerrar(self):
        self._vivo = False
        for control_, modo in list(self._luces):
            self.luz(control_, False, modo)


class Perfil:
    def __init__(self, ruta: Path, origen: str):
        self.ruta, self.origen = ruta, origen
        self.clave = ruta.stem.lower()
        self.nombre, self.descripcion, self.color = self.clave.capitalize(), "", None
        self.usa_base = False
        self.leer_perillas = True
        self.tipo = "json" if ruta.suffix == ".json" else "python"
        self.definicion, self.estados = None, {}
        self.color_def: dict | None = None  # perfiles JSON: color, efecto, brillo y ciclo al activar
        self.prendidas: set = set()  # luces que el perfil prende al entrar (para devolverlas a su lugar)
        self.sesiones_en: str | None = None  # modo de pads donde se ven las sesiones de Claude Code
        self.modulo, self.error, self.mtime = None, None, 0.0
        self.manejadores: list = []
        self.capa: dict = {}            # solo perfiles en Python: {"asignaciones": [...], "escena": {...}}
        self.capa_manejadores: list = []
        self.capa_prendidas: list = []
        self.mtime_capa = None
        self.cargar()

    @property
    def ruta_capa(self) -> Path:
        return CAPAS / f"{self.clave}.json"

    @property
    def escena(self) -> dict:
        if self.tipo == "json":
            return (self.definicion or {}).get("escena") or {}
        return self.capa.get("escena") or {}

    def mtime_capa_actual(self):
        try:
            return self.ruta_capa.stat().st_mtime
        except OSError:
            return None

    def cargar_capa(self):
        self.mtime_capa = self.mtime_capa_actual()
        self.capa, self.capa_manejadores, self.capa_prendidas = {}, [], []
        if self.tipo == "json" or self.mtime_capa is None:
            return
        try:
            d = json.loads(self.ruta_capa.read_text(encoding="utf-8"))
            asignaciones = declarativo.validar_asignaciones(d.get("asignaciones") or [])
            self.capa = {"asignaciones": asignaciones, "escena": declarativo.validar_escena(d.get("escena"))}
            self.capa_manejadores = declarativo.construir_asignaciones(asignaciones)
            self.capa_prendidas = declarativo.luces_de(asignaciones)
        except (ValueError, OSError) as e:
            self.error = f"tus cambios ({self.ruta_capa.name}): {e}"

    def cargar(self):
        self.mtime = self.ruta.stat().st_mtime
        if self.tipo == "json":
            return self._cargar_json()
        self._cargar_python()
        if not self.error:
            self.cargar_capa()

    def _cargar_python(self):
        try:
            spec = importlib.util.spec_from_file_location(f"starlight_perfil_{self.clave}", self.ruta)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as e:
            self.error = _explicar(e, self.ruta)
            return
        self.modulo, self.error = mod, None
        self.nombre = getattr(mod, "nombre", self.nombre)
        self.descripcion = getattr(mod, "descripcion", (mod.__doc__ or "").strip().split("\n")[0])
        self.color = getattr(mod, "color", None)
        self.usa_base = bool(getattr(mod, "usa_base", False))
        self.leer_perillas = bool(getattr(mod, "leer_perillas", True))
        self.sesiones_en = getattr(mod, "sesiones_en", None)
        self.manejadores = [(patron, fn, al, shift) for fn in vars(mod).values() if callable(fn)
                            for patron, al, shift in getattr(fn, "_starlight", [])]

    def _cargar_json(self):
        import types

        try:
            d = declarativo.validar(json.loads(self.ruta.read_text(encoding="utf-8")))
            manejadores, al_entrar, prendidas = declarativo.construir(d)
        except (ValueError, OSError) as e:
            self.error = str(e)
            return
        self.definicion, self.error = d, None
        self.nombre, self.descripcion = d["nombre"], d["descripcion"]
        self.color = (d["color"]["color"], d["color"]["efecto"]) if d["color"] and d["color"].get("color") else None
        self.color_def = d["color"]
        self.estados = d["estados"]
        self.sesiones_en = d.get("sesiones_en")
        self.prendidas = set(prendidas)
        self.usa_base = False
        self.leer_perillas = d["leer_perillas"]
        self.manejadores = manejadores
        self.modulo = types.SimpleNamespace(al_entrar=al_entrar)

    def info(self) -> dict:
        return {"clave": self.clave, "nombre": self.nombre, "descripcion": self.descripcion,
                "origen": self.origen, "error": self.error, "ruta": str(self.ruta), "usa_base": self.usa_base,
                "tipo": self.tipo, "editable": self.tipo == "json", "estados": bool(self.estados),
                "leer_perillas": self.leer_perillas, "escena": bool(self.escena), "sesiones_en": self.sesiones_en,
                "cambios": len(self.capa.get("asignaciones") or [])}

    def descripcion_manejadores(self) -> list:
        """Lo que hace un perfil en Python, control por control (para mostrarlo en el tablero)."""
        salida = []
        for patron, fn, al, shift in self.manejadores:
            doc = (fn.__doc__ or "").strip().split("\n")[0]
            salida.append({"control": patron, "al": al, "shift": shift,
                           "descripcion": doc.rstrip(".") or fn.__name__.replace("_", " ").capitalize()})
        return salida


def _explicar(e: Exception, ruta: Path) -> str:
    linea = None
    for f in traceback.extract_tb(e.__traceback__):
        if Path(f.filename).resolve() == ruta.resolve():
            linea = f.lineno
    if isinstance(e, SyntaxError) and e.lineno:
        linea = e.lineno
    return (f"línea {linea}: " if linea else "") + f"{type(e).__name__}: {e}"


class Motor:
    def __init__(self, aparato):
        self.aparato = aparato
        self.perfiles: dict[str, Perfil] = {}
        self.activo: Perfil | None = None
        self.ctx: Contexto | None = None
        self.pausado = False  # una prueba en pantalla pausa el perfil para no interferir
        self._lock = threading.RLock()
        self._cola: queue.Queue = queue.Queue(maxsize=1000)
        self._shift = False          # Shift presionado ahora (para Shift + Bass/Filter)
        self._claude_estado = None   # estado global de Claude Code que se está mostrando
        self._claude_opciones = None  # cuántas opciones tiene en pantalla la sesión que te necesita
        self._titilando: set = set()  # luces que titilan porque Claude Code te necesita
        self.claude = Sesiones(self._claude_cambio)
        self.casa = Casa(lambda info: self._anunciar({"tipo": "casa", **info}))
        DE_USUARIO.mkdir(parents=True, exist_ok=True)
        self._escanear()
        aparato.suscribir(self._oyente)
        threading.Thread(target=self._trabajar, daemon=True, name="perfiles").start()
        threading.Thread(target=self._vigilar_archivos, daemon=True, name="perfiles-archivos").start()
        guardado = self._leer_estado().get("perfil")
        if guardado in self.perfiles:
            self.activar(guardado, guardar=False)

    # ------------------------------------------------------------------ archivos
    def _archivos(self) -> dict[str, tuple[Path, str]]:
        encontrados = {}
        for carpeta, origen in ((INCLUIDOS, "incluido"), (DE_USUARIO, "tuyo")):
            for ruta in sorted([*carpeta.glob("*.py"), *carpeta.glob("*.json")]):
                if not ruta.name.startswith("_") and ruta.stem != "plantilla":
                    encontrados[ruta.stem.lower()] = (ruta, origen)  # los tuyos reemplazan a los incluidos
        return encontrados

    def _escanear(self) -> bool:
        cambio = False
        archivos = self._archivos()
        with self._lock:
            for clave in list(self.perfiles):
                if clave not in archivos:
                    del self.perfiles[clave]
                    cambio = True
            for clave, (ruta, origen) in archivos.items():
                p = self.perfiles.get(clave)
                if p is None or p.ruta != ruta:
                    self.perfiles[clave] = Perfil(ruta, origen)
                    cambio = True
                elif ruta.stat().st_mtime != p.mtime or (p.tipo == "python" and p.mtime_capa_actual() != p.mtime_capa):
                    p.cargar()
                    cambio = True
                    if self.activo is p:
                        self.activar(clave, guardar=False)
                    if p.error:
                        self._anunciar({"tipo": "perfil-error", "perfil": p.nombre, "error": p.error})
            if self.activo and self.activo.clave not in self.perfiles:
                self.activar(None)
        return cambio

    def _vigilar_archivos(self):
        while True:
            time.sleep(1)
            try:
                if self._escanear():
                    self._anunciar({"tipo": "perfiles", **self.info()})
            except Exception as e:  # nunca tumbar el servidor por un archivo
                print(f"[perfiles] {e}", file=sys.stderr)

    # ------------------------------------------------------------------ activar
    def buscar(self, nombre: str | None) -> Perfil | None:
        if nombre in (None, "", "ninguno"):
            return None
        n = str(nombre).lower()
        for p in self.perfiles.values():
            if n in (p.clave, p.nombre.lower()):
                return p
        raise ValueError(f"No hay un perfil llamado «{nombre}». Perfiles: {', '.join(self.perfiles) or 'ninguno'}")

    def activar(self, nombre: str | None, guardar: bool = True):
        nuevo = self.buscar(nombre)
        if nuevo and nuevo.error:
            raise ValueError(f"El perfil «{nuevo.nombre}» tiene un error ({nuevo.error}). Corrígelo y guárdalo.")
        with self._lock:
            if self.ctx:
                self._llamar(self.activo, "al_salir", self.ctx)
                self.ctx._cerrar()
            self.activo, self.ctx = nuevo, (Contexto(self, nuevo) if nuevo else None)
            self._titilando = set()
            if nuevo:
                if nuevo.color_def:
                    self.pintar_color(nuevo.color_def)
                elif nuevo.color:
                    color, efecto = (nuevo.color, "fijo") if isinstance(nuevo.color, (str, int)) else nuevo.color
                    self.ctx.base(color, efecto)
                self._llamar(nuevo, "al_entrar", self.ctx)
                for c in nuevo.capa_prendidas:
                    self.ctx.luz(c)
                if nuevo.escena:
                    self._aplicar_escena(nuevo, self.ctx)
                if nuevo.estados:
                    self._pintar_claude()
                self._pintar_sesiones()
                if nuevo.leer_perillas:
                    # el aparato responde con la posición de cada perilla y fader, y el perfil la recibe
                    # como si la hubieras movido: así arranca ajustado a lo que tienes
                    try:
                        self.aparato.enviar([mapa.VOLCADO])
                    except AparatoDesconectado:
                        pass
            else:
                try:
                    self.aparato.base_auto()
                except AparatoDesconectado:
                    pass
        if guardar:
            self._guardar_estado({"perfil": nuevo.clave if nuevo else None})
        self._anunciar({"tipo": "perfiles", **self.info()})

    def siguiente(self, paso: int = 1):
        claves = [k for k, p in sorted(self.perfiles.items()) if not p.error] + [None]
        actual = self.activo.clave if self.activo else None
        self.activar(claves[(claves.index(actual) + paso) % len(claves)] if actual in claves else claves[0])

    def anterior(self):
        self.siguiente(-1)

    # ------------------------------------------------------------------ escena grabada
    def _aplicar_escena(self, p: Perfil, ctx: Contexto):
        """Deja el aparato como estaba cuando grabaste la escena."""
        e = p.escena
        try:
            if "brillo" in e:
                self.aparato.poner_brillo(e["brillo"])
            for ef, seg in (e.get("ritmo") or {}).items():
                self.aparato.poner_ritmo(ef, seg)
            for deck, modo in (e.get("modos") or {}).items():
                self.aparato.modo_pads(deck, modo)
            b = e.get("base")
            if b and not p.usa_base:
                if b.get("modo") == "auto":
                    self.aparato.base_auto()
                else:
                    for lado, deck in (("izq", "A"), ("der", "B")):
                        v = b.get(lado)
                        if v:
                            self.aparato.base_rgb(*v["rgb"], lado=lado, efecto=v["efecto"])
            if "luces" in e:
                quedan = set()
                for k, ef in e["luces"].items():
                    partes = k.split(".")
                    if len(partes) == 3:  # pad: A.pad1.hotcue
                        control, modo = f"{partes[0]}.{partes[1]}", partes[2]
                    else:
                        control, modo = k, None
                    ctx.luz(control, True, modo, efecto=ef)
                    quedan.add((control, modo))
                for control, modo in list(ctx._luces):  # lo que el perfil prendió y en la escena estaba apagado
                    real = (modo or self.aparato.estado["modos"].get(control[0]) or "hotcue") if ".pad" in control else None
                    if (control, real) not in quedan:
                        ctx.luz(control, False, modo)
        except (AparatoDesconectado, ValueError):
            pass

    def foto_escena(self) -> dict:
        """El estado actual del aparato como escena."""
        f = self.aparato.foto()
        modos = {d: m for d, m in (f.get("modos") or {}).items() if m}
        titilan = set(getattr(self.aparato, "_titilan", {}) or {})
        luces = {}
        for k, encendida in (f.get("luces") or {}).items():
            if not encendida:
                continue
            control = ".".join(k.split(".")[:2]) if ".pad" in k else k
            if control in self._titilando:  # titila porque Claude te necesita: no es parte de la escena
                luces[k] = "fijo"
                continue
            luces[k] = "parpadeo" if k in titilan else "fijo"
        escena = {"brillo": f.get("brillo", 1.0), "ritmo": dict(f.get("ritmo") or {}), "modos": modos, "luces": luces}
        if not (self.activo and self.activo.usa_base):
            b = f.get("base") or {}
            escena["base"] = {"modo": "auto"} if b.get("modo") != "manual" else \
                {"modo": "manual", **{l: {"rgb": b[l]["rgb"], "efecto": b[l].get("efecto", "fijo")} for l in ("izq", "der") if b.get(l)}}
        return declarativo.validar_escena(escena)

    def grabar_escena(self, clave: str | None = None) -> dict:
        """Guarda cómo está el aparato ahora dentro del perfil (el activo si no dices cuál)."""
        p = self.buscar(clave) if clave else self.activo
        if p is None:
            raise ValueError("Activa un perfil primero: la escena se graba dentro de él.")
        escena = self.foto_escena()
        if p.tipo == "json":
            d = dict(p.definicion)
            d["escena"] = escena
            self.guardar(p.clave, d)
        else:
            self._escribir_capa(p, escena=escena)
        return escena

    def borrar_escena(self, clave: str):
        p = self.buscar(clave)
        if p is None:
            raise ValueError("Elige un perfil.")
        if p.tipo == "json":
            d = dict(p.definicion)
            d.pop("escena", None)
            self.guardar(p.clave, d)
        else:
            self._escribir_capa(p, escena={})

    # ------------------------------------------------------------------ capas
    def guardar_capa(self, clave: str, asignaciones: list):
        """Cambios tuyos encima de un perfil en Python: lo que asignes a un control reemplaza lo que
        el perfil hacía con ese control (con o sin Shift, según elijas)."""
        p = self.buscar(clave)
        if p is None:
            raise ValueError("Elige un perfil.")
        if p.tipo == "json":
            raise ValueError("Este perfil se edita directamente: guarda su definición.")
        self._escribir_capa(p, asignaciones=declarativo.validar_asignaciones(asignaciones))

    def _escribir_capa(self, p: Perfil, asignaciones=None, escena=None):
        capa = dict(p.capa)
        if asignaciones is not None:
            capa["asignaciones"] = asignaciones
        if escena is not None:
            capa["escena"] = escena
        capa = {k: v for k, v in capa.items() if v}
        CAPAS.mkdir(parents=True, exist_ok=True)
        if capa:
            p.ruta_capa.write_text(json.dumps(capa, ensure_ascii=False, indent=2), encoding="utf-8")
        elif p.ruta_capa.exists():
            p.ruta_capa.unlink()
        p.error = None
        p.cargar()
        if self.activo is p:
            self.activar(p.clave, guardar=False)
        self._anunciar({"tipo": "perfiles", **self.info()})

    # ------------------------------------------------------------------ editor
    def definicion(self, clave: str) -> dict:
        p = self.buscar(clave)
        if p is None:
            raise ValueError("Elige un perfil.")
        return {"clave": p.clave, "origen": p.origen, "tipo": p.tipo, "ruta": str(p.ruta), "error": p.error,
                "definicion": p.definicion if p.tipo == "json" else None,
                "nombre": p.nombre, "descripcion": p.descripcion, "escena": p.escena,
                "manejadores": p.descripcion_manejadores() if p.tipo == "python" else [],
                "capa": p.capa.get("asignaciones") or [] if p.tipo == "python" else [],
                "usa_base": p.usa_base}

    def guardar(self, clave: str | None, d: dict) -> str:
        """Guarda una definición como JSON en la carpeta del usuario (si era incluido, queda tu copia)."""
        limpia = declarativo.validar(d)
        if not clave:
            clave = "".join(c for c in limpia["nombre"].lower().replace(" ", "_") if c.isalnum() or c == "_")
        clave = "".join(c for c in str(clave).lower() if c.isalnum() or c == "_")
        if not clave:
            raise ValueError("El nombre del perfil necesita letras o números.")
        existente = self.perfiles.get(clave)
        if existente and existente.tipo == "python":
            raise ValueError(f"Ya hay un perfil en Python llamado «{clave}». Usa otro nombre.")
        DE_USUARIO.mkdir(parents=True, exist_ok=True)
        (DE_USUARIO / f"{clave}.json").write_text(json.dumps(limpia, ensure_ascii=False, indent=2), encoding="utf-8")
        self._escanear()
        self._anunciar({"tipo": "perfiles", **self.info()})
        return clave

    def borrar(self, clave: str):
        ruta = DE_USUARIO / f"{clave}.json"
        if not ruta.exists():
            raise ValueError("Solo se pueden borrar los perfiles tuyos hechos en el editor.")
        ruta.unlink()
        self._escanear()
        self._anunciar({"tipo": "perfiles", **self.info()})

    def pintar_color(self, v: dict):
        """Pinta la base con un color del perfil: color, efecto y, si los trae, intensidad y velocidad."""
        try:
            if "brillo" in v:
                self.aparato.poner_brillo(v["brillo"])
            if v.get("ciclo") and v["efecto"] != "fijo":
                self.aparato.poner_ritmo(v["efecto"], v["ciclo"])
            if v.get("rgb"):
                self.aparato.base_rgb(*mapa.hex_a_rgb(v["rgb"]), efecto=v["efecto"])
            else:
                self.aparato.base_color(v["color"], v["efecto"])
        except (AparatoDesconectado, ValueError):
            pass

    # ------------------------------------------------------------------ Claude Code
    def estado_claude(self, estado: str) -> bool:
        """Estado puesto a mano (`starlight claude <estado>`). Devuelve si el perfil activo lo muestra."""
        try:
            self.claude.fijar(estado)
        except ValueError:
            return False
        with self._lock:
            return bool(self.activo and self.activo.estados.get(estado))

    def _claude_cambio(self, resumen: dict):
        self._anunciar({"tipo": "claude", **resumen})
        self._pintar_sesiones(resumen)
        if (resumen["estado"], resumen.get("opciones")) != (self._claude_estado, self._claude_opciones):
            self._claude_estado, self._claude_opciones = resumen["estado"], resumen.get("opciones")
            self._pintar_claude()

    def _pintar_sesiones(self, resumen: dict | None = None):
        """Los 8 pads, en el modo de pads del perfil, muestran tus sesiones de Claude Code:
        apagado = no hay; encendido = abierta; titila = te necesita o falló."""
        with self._lock:
            p, ctx = self.activo, self.ctx
            if not p or not ctx or not p.sesiones_en:
                return
            r = resumen or self.claude.resumen()
            por_puesto = {s["puesto"]: s for s in r["sesiones"] if s.get("puesto")}
            for n in range(1, 9):
                deck, pad = ("A", n) if n <= 4 else ("B", n - 4)
                s = por_puesto.get(n)
                if s:
                    ctx.luz(f"{deck}.pad{pad}", True, p.sesiones_en,
                            efecto="parpadeo" if s["estado"] in ("esperando", "error") else "fijo")
                else:
                    ctx.luz(f"{deck}.pad{pad}", False, p.sesiones_en)

    def _pintar_claude(self):
        """Pinta la base y hace titilar los botones según el estado más urgente de tus sesiones."""
        with self._lock:
            p, ctx = self.activo, self.ctx
            if not p or not p.estados or not ctx:
                return
            v = p.estados.get(self._claude_estado) if self._claude_estado else None
            try:
                if v:
                    self.pintar_color(v)
                elif p.color_def:  # sin sesiones: el color del perfil
                    self.pintar_color(p.color_def)
                elif p.color:
                    color, efecto = (p.color, "fijo") if isinstance(p.color, (str, int)) else p.color
                    self.aparato.base_color(color, efecto)
            except (AparatoDesconectado, ValueError):
                pass
            lista = list((v or {}).get("titilar") or [])
            n = self._claude_opciones if self._claude_estado == "esperando" else None
            if n:  # de los pads que titilan, solo tantos como opciones hay en pantalla (los demás botones, igual)
                pads = sorted((c for c in lista if ".pad" in c), key=lambda c: (c[0], int(c[-1])))
                lista = [c for c in lista if ".pad" not in c] + pads[:n]
            nuevas = set(lista)
            for c in self._titilando - nuevas:  # vuelven a como las dejó el perfil
                ctx.luz(c, c in p.prendidas)
            for c in nuevas:
                ctx.luz(c, True, efecto="parpadeo")
            self._titilando = nuevas

    def info(self) -> dict:
        with self._lock:
            return {"activo": self.activo.clave if self.activo else None,
                    "perfiles": [p.info() for _, p in sorted(self.perfiles.items())],
                    "carpeta": str(DE_USUARIO)}

    # ------------------------------------------------------------------ eventos
    def _oyente(self, ev: dict):
        if ev.get("tipo") == "control":
            try:
                self._cola.put_nowait(ev)
            except queue.Full:
                pass

    def _trabajar(self):
        while True:
            e = Evento(self._cola.get())
            if e.control == "shift":
                self._shift = e.presionado
            cambio = None
            if e.control == "vinyl" and e.shift and e.presionado:
                cambio = self.siguiente
            elif e.control == "bassfilter" and self._shift and e.presionado:
                cambio = self.anterior
            if cambio:
                try:
                    cambio()
                except ValueError as err:
                    self._anunciar({"tipo": "perfil-error", "perfil": "", "error": str(err)})
                continue
            with self._lock:
                p, ctx = self.activo, self.ctx
            if not p or self.pausado:
                continue
            if p.sesiones_en and e.clase == "pad" and e.modo == p.sesiones_en:
                continue  # en este modo, los pads muestran tus sesiones de Claude Code
            # tus cambios (capa) mandan: si uno toma este control, lo del perfil en Python no se ejecuta
            reemplazado = any(fnmatch.fnmatchcase(e.control, patron) and (shift is None or e.shift == shift)
                              for patron, _, _, shift in p.capa_manejadores)
            for patron, fn, al, shift in p.capa_manejadores + ([] if reemplazado else p.manejadores):
                if not fnmatch.fnmatchcase(e.control, patron):
                    continue
                if shift is not None and e.shift != shift:
                    continue
                if al == "presionar" and not e.presionado:
                    continue
                if al == "soltar" and (e.clase not in ("boton", "pad") or e.valor):
                    continue
                try:
                    fn(e, ctx)
                except Exception as err:
                    self._error(p, err)

    def _llamar(self, p: Perfil, nombre: str, ctx: Contexto):
        fn = getattr(p.modulo, nombre, None)
        if callable(fn):
            try:
                fn(ctx)
            except Exception as err:
                self._error(p, err)

    def _error(self, p: Perfil, err: Exception):
        texto = _explicar(err, p.ruta) if not isinstance(err, sistema.AccionNoDisponible) else str(err)
        print(f"[perfil {p.nombre}] {texto}", file=sys.stderr)
        self._anunciar({"tipo": "perfil-error", "perfil": p.nombre, "error": texto})

    def _anunciar(self, ev: dict):
        self.aparato.anunciar(ev)

    # ------------------------------------------------------------------ estado guardado
    def _leer_estado(self) -> dict:
        try:
            return json.loads(ESTADO.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _guardar_estado(self, datos: dict):
        try:
            HOGAR.mkdir(parents=True, exist_ok=True)
            ESTADO.write_text(json.dumps({**self._leer_estado(), **datos}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass


def crear_perfil(nombre: str) -> Path:
    """Crea un perfil nuevo a partir de la plantilla, en la carpeta de perfiles del usuario."""
    clave = "".join(c for c in nombre.lower().replace(" ", "_") if c.isalnum() or c == "_")
    if not clave:
        raise ValueError("Escribe un nombre con letras o números.")
    DE_USUARIO.mkdir(parents=True, exist_ok=True)
    destino = DE_USUARIO / f"{clave}.py"
    if destino.exists():
        raise ValueError(f"Ya existe {destino}. Ábrelo y edítalo.")
    texto = (INCLUIDOS / "plantilla.py").read_text(encoding="utf-8").replace("Mi perfil", nombre)
    destino.write_text(texto, encoding="utf-8")
    return destino


__all__ = ["control", "Evento", "Contexto", "Motor", "crear_perfil"]
