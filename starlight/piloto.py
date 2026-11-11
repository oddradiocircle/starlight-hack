"""Piloto de Claude Code: los 8 pads y los botones de un perfil con acciones «Claude: …».

Principio: cada luz dice algo. Fija = presionar sirve ahora. Titila = te necesita o te lo recomiendo.
Apagada = ahora no hace nada.

Dos vistas, y el modo de pads dice en cuál estás (el aparato solo muestra las luces del modo activo):

    Sesiones  (Hot Cue)  un pad por sesión, siempre en el mismo: fijo = abierta, titila = te necesita.
                         Tocar = ir a su bloque en Wave; si te necesita, pasa a Responder.
    Responder (Loop)     lo que esa sesión tiene en pantalla: opciones fijas, titila la recomendada.
                         Tocar = responder. Al terminar (o si respondes con el teclado, o cancelas)
                         vuelve sola a Sesiones.

Presionar Hot Cue o Loop en el aparato también cambia de vista. Las teclas («Claude: tecla») van a la
ventana del frente; en Responder van a la sesión que estás respondiendo, que es la única que se sabe
con certeza (si cambias de sesión con el mouse, el control no se entera).

Ir a una sesión usa Wave Terminal (starlight/wave.py: Alt + N cambia de pestaña, Ctrl + Shift + N
enfoca el bloque, y la base de datos de Wave confirma que quedó). scripts/wave_hook.sh le dice al
servidor en qué bloque corre cada sesión. Una respuesta se escribe solo si Wave confirmó el bloque.
Sin Wave (o fuera de Windows), los pads siguen mostrando y respondiendo, en la ventana del frente.
"""
from __future__ import annotations

import json
import queue
import threading
import time

from . import sistema, wave
from .aparato import AparatoDesconectado

VISTA_MODO = {"sesiones": "hotcue", "responder": "loop"}
PADS_PERMISO = {1: 1, 2: 2, 3: 8}  # opción del diálogo de permisos -> pad: el «No» lejos del «Sí»


def control_de_pad(n: int) -> str:
    """Pad 1-8 -> control: 1-4 son los del deck A, 5-8 los del B."""
    return f"A.pad{n}" if n <= 4 else f"B.pad{n - 4}"


def efecto_sesion(s: dict) -> str:
    """Cómo se ve el pad de una sesión. La velocidad del titileo dice la urgencia:
    titila (rápido) = te necesita ya (pregunta, permiso o error); lento = terminó y es tu turno, y no
    has ido a verla; fijo = abierta (trabajando, o terminada que ya viste)."""
    if s["estado"] in ("esperando", "error"):
        return "parpadeo"
    if s["estado"] in ("listo", "inactivo") and not s.get("visto", True):
        return "lento"
    return "fijo"


def pads_de(detalle: dict) -> dict[int, int]:
    """Opción (1, 2, 3…) -> pad (1-8), según lo que la sesión tiene en pantalla."""
    tipo, n = detalle.get("tipo"), detalle.get("opciones") or 0
    if tipo == "permiso":
        return dict(PADS_PERMISO)
    if tipo in ("pregunta", "plan"):
        return {o: o for o in range(1, min(n, 8) + 1)}
    return {}  # un formulario: no hay nada que elegir desde el control


class Piloto:
    def __init__(self, motor):
        self.motor = motor
        self.vista = "sesiones"
        self.actual: str | None = None     # la última sesión a la que fuiste desde el control
        self.responder: str | None = None  # la sesión cuyas opciones se ven (o se verán al volver a Loop)
        self._lock = threading.RLock()
        self._puestas: dict = {}           # (control, modo) -> efecto o None: lo último que se pintó
        self._base_pendiente = False
        self._cola: queue.Queue = queue.Queue(maxsize=50)
        threading.Thread(target=self._trabajar, daemon=True, name="piloto").start()
        threading.Thread(target=self._mirar_wave, daemon=True, name="piloto-wave").start()

    @property
    def claude(self):
        return self.motor.claude

    def activo(self) -> bool:
        p = self.motor.activo
        return bool(p and p.luces_claude and self.motor.ctx)

    # ------------------------------------------------------------------ entrar y salir del perfil
    def entrar(self):
        with self._lock:
            self.vista, self.responder, self._puestas = "sesiones", None, {}
            self._poner_modos()
        self.pintar()

    def salir(self):
        with self._lock:
            self.vista, self.responder, self._puestas = "sesiones", None, {}

    # ------------------------------------------------------------------ lo que hacen los controles
    def pad(self, n: int, e=None):
        with self._lock:
            if self.vista == "responder":
                d = (self.claude.sesion(self.responder) or {}).get("detalle") or {}
                opcion = next((o for o, p in pads_de(d).items() if p == n), None)
                if opcion is None:
                    return
                sid = self.responder
                fin = None
                if not d.get("varias"):  # una sola respuesta: listo, de vuelta a las sesiones
                    self.responder = None
                    self._a_vista("sesiones")
                    # el «No» de un permiso detiene a Claude (queda esperando tu mensaje); lo demás sigue
                    fin = "interrumpido" if d.get("tipo") == "permiso" and opcion == 3 else "respondido"
                self._encolar("responder", sid, str(opcion), fin)
            else:
                sid = self.claude.por_puesto(n)
                if not sid:
                    return
                self._elegir(sid)
        self.pintar()

    def ir(self, cual: str):
        with self._lock:
            if cual == "espera":
                sid = self.claude.la_que_espera(excepto=self.responder if self.vista == "responder" else None)
                if sid:
                    self._elegir(sid)
            else:
                sid = self.claude.terminada_sin_ver()
                if sid:
                    self.actual = sid
                    self._encolar("ir", sid, None)
        if sid and cual != "espera":
            self.claude.marcar_vista(sid)
        self.pintar()

    def tecla(self, teclas: list):
        with self._lock:
            sid, fin = None, None
            if self.vista == "responder":  # respondiendo desde los pads: la tecla es para esa sesión
                sid = self.responder
                if teclas == ["esc"]:
                    self.responder, fin = None, "interrumpido"
                    self._a_vista("sesiones")
        self._encolar("tecla", sid, list(teclas), fin)
        self.pintar()

    def modo(self, deck: str, modo: str):
        """Presionaste un botón de modo de pads: Hot Cue = Sesiones, Loop = Responder."""
        with self._lock:
            if modo == "loop":
                s = self.claude.sesion(self.responder)
                if s and s["estado"] == "esperando":
                    self.vista = "responder"
                else:
                    sid = self.claude.la_que_espera()
                    if sid:
                        self._elegir(sid)
                    else:
                        self.vista = "sesiones"  # no hay nada que responder
            else:
                self.vista = "sesiones"
            self._poner_modos()
        self.pintar()

    def _elegir(self, sid: str):
        """Ir a una sesión: queda como actual y, si te necesita, sus opciones pasan a los pads."""
        self.actual = sid
        s = self.claude.sesion(sid)
        if s and s["estado"] == "esperando":
            self.responder = sid
            self._a_vista("responder")
        self._encolar("ir", sid, None)
        threading.Thread(target=self.claude.marcar_vista, args=(sid,), daemon=True).start()

    def _a_vista(self, vista: str):
        if vista != self.vista:
            self.vista = vista
            self._poner_modos()

    def _poner_modos(self):
        modo = VISTA_MODO[self.vista]
        for deck in ("A", "B"):
            try:
                if self.motor.aparato.estado["modos"].get(deck) != modo:
                    self.motor.aparato.modo_pads(deck, modo)
            except AparatoDesconectado:
                pass
        # la base cambia con la vista (en Responder deja de titilar); se repinta al soltar el candado,
        # para no pedir el del motor teniendo este (el motor pide este teniendo el suyo: se trabarían)
        self._base_pendiente = True

    def _despues(self):
        if self._base_pendiente:
            self._base_pendiente = False
            self.motor.repintar_base()

    # ------------------------------------------------------------------ luces
    def pintar(self, resumen: dict | None = None):
        """Pone la luz de cada control con una acción de Claude según si presionarlo sirve ahora."""
        if not self.activo():
            return
        r = resumen or self.claude.resumen()
        with self._lock:
            p, ctx = self.motor.activo, self.motor.ctx
            if not p or not ctx:
                return
            self._seguir(r)
            modo = VISTA_MODO[self.vista]
            por_pad = self._pads(r)
            esperan = [s for s in r["sesiones"] if s["estado"] == "esperando"]
            otra_espera = any(s for s in esperan if not (self.vista == "responder" and self.responder
                                                         and s["id"] == self.responder[:8]))
            trabaja = any(s["estado"] == "trabajando" for s in r["sesiones"])
            d = ((self.claude.sesion(self.responder) or {}).get("detalle") or {}) if self.vista == "responder" else {}
            for control, acc in p.luces_claude.items():
                tipo, v = acc["tipo"], acc["valor"]
                if tipo == "claude_pad":
                    efecto = por_pad.get(v)
                elif tipo == "claude_ir" and v == "espera":
                    efecto = "parpadeo" if otra_espera else None
                elif tipo == "claude_ir":
                    efecto = "fijo" if any(efecto_sesion(s) == "lento" for s in r["sesiones"]) else None
                else:  # claude_tecla
                    regla = v.get("luz")
                    sirve = {"interrumpir": self.vista == "responder" or trabaja,
                             "sesion": bool(r["sesiones"]),
                             "confirmar": self.vista == "responder" and bool(d.get("varias")),
                             }.get(regla, False)
                    efecto = "fijo" if sirve else None
                self._luz(ctx, control, efecto, modo if ".pad" in control else None)
        self._despues()

    def _pads(self, r: dict) -> dict[int, str]:
        """Pad (1-8) -> efecto en la vista actual."""
        if self.vista == "responder":
            d = (self.claude.sesion(self.responder) or {}).get("detalle") or {}
            reco = d.get("recomendada")
            return {pad: ("parpadeo" if reco is not None and opcion == reco + 1 else "fijo")
                    for opcion, pad in pads_de(d).items()}
        return {s["puesto"]: efecto_sesion(s) for s in r["sesiones"] if s.get("puesto")}

    def _luz(self, ctx, control: str, efecto: str | None, modo: str | None):
        clave = (control, modo)
        if self._puestas.get(clave, "nada") == efecto:
            return
        self._puestas[clave] = efecto
        ctx.luz(control, efecto is not None, modo, efecto=efecto or "fijo")

    def _seguir(self, r: dict):
        """Pone al día la vista con lo que pasó en las sesiones (respondiste con el teclado, cancelaste…)."""
        if self.responder:
            s = self.claude.sesion(self.responder)
            if not s or s["estado"] != "esperando":
                self.responder = None
                if self.vista == "responder":
                    self._a_vista("sesiones")
        if self.actual and not self.claude.sesion(self.actual):
            self.actual = None

    # ------------------------------------------------------------------ Wave y teclado (en otro hilo)
    def _encolar(self, que: str, sid, valor, fin: str | None = None):
        try:
            self._cola.put_nowait((que, sid, valor, fin))
        except queue.Full:
            pass

    def _trabajar(self):
        while True:
            que, sid, valor, fin = self._cola.get()
            try:
                hecho = False
                if que == "ir":
                    self._enfocar(sid)
                elif que == "responder":
                    if self._enfocar(sid, para_escribir=True):
                        sistema.escribir(valor)
                        hecho = True
                elif que == "tecla":
                    if sid is None or self._enfocar(sid, para_escribir=True):
                        sistema.teclas(*valor)
                        hecho = True
                if hecho and fin and sid:
                    # la espera terminó: no esperar al hook de Claude Code (tarda ~1 s) para dejar de titilar.
                    # Solo después de escribir: si no se pudo, la sesión sigue esperándote, y así se ve.
                    evento = {"session_id": sid, "hook_event_name": "FinEspera", "fin": fin}
                    self.claude.hook(json.dumps(evento).encode())
            except Exception as err:  # nunca tumbar el hilo
                self.motor._anunciar({"tipo": "perfil-error", "perfil": "Claude Code", "error": f"Piloto: {err}"})

    def _enfocar(self, sid: str, para_escribir: bool = False) -> bool:
        """Lleva Wave al bloque de la sesión, aunque esté en otra pestaña (starlight/wave.py).
        Devuelve si es seguro escribir: Wave confirmó la pestaña y el bloque con foco.
        Si la sesión no tiene bloque conocido (no corre en Wave o aún no llegó su primer evento), o no
        es Windows, se escribe en la ventana del frente, como antes."""
        s = self.claude.sesion(sid) or {}
        bloque = s.get("bloque")
        if not bloque or not sistema.WIN:
            if not bloque and not para_escribir:  # ibas a esa sesión y no se puede: decirlo
                self._avisar(f"No sé en qué terminal de Wave corre «{s.get('proyecto', 'esa sesión')}»: "
                             "escríbele algo y lo aprendo.")
            return True
        ok, por_que = wave.ir(bloque)
        if not ok:
            self._avisar(f"No pude ir a «{s.get('proyecto', 'esa sesión')}»: {por_que}"
                         + (" No escribí la respuesta." if para_escribir else ""))
        return ok

    def _mirar_wave(self):
        """Mientras haya sesiones que terminaron y no has visto, mira cada segundo qué terminal tiene
        el foco en Wave: si es la de una de ellas, ya la viste (su pad deja de titilar lento), llegues
        con el control, el mouse o el teclado."""
        while True:
            time.sleep(1)
            try:
                if not sistema.WIN or not self.activo():
                    continue
                pendientes = self.claude.sin_ver()
                if not pendientes:
                    continue
                foco = wave.enfocado()
                for sid, bloque in pendientes:
                    if bloque == foco:
                        self.claude.marcar_vista(sid)
            except Exception:  # nunca tumbar el hilo
                pass

    def _avisar(self, texto: str):
        self.motor._anunciar({"tipo": "perfil-error", "perfil": "Claude Code", "error": texto})
