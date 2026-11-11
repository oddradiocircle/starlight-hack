"""Estado de Claude Code, una sesión por terminal.

Los hooks de Claude Code mandan cada evento (con su session_id) a POST /api/claude/hook. Aquí se
lleva el estado de cada sesión y se calcula el que se ve en la base: el más urgente de todos.

    te necesita (esperando) > error > trabajando > listo (terminó) > inactivo

Así, con tres o más Claude Code abiertos, la base avisa en cuanto cualquiera te necesita.
Los subagentes comparten la sesión de quien los lanzó: sus permisos también cuentan.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

PRIORIDAD = ("esperando", "error", "trabajando", "listo", "inactivo")
PUESTOS = 8  # los 8 pads: A1-A4 y B1-B4
OLVIDAR = 6 * 3600  # una sesión sin eventos en 6 horas se olvida (por si se cerró la terminal sin avisar)
MOTIVOS = {"permiso": "pide permiso", "pregunta": "te hizo una pregunta", "plan": "quiere que apruebes el plan"}

_CAMPO = r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)"'


def _campo(texto: str, nombre: str):
    m = re.search(_CAMPO % nombre, texto)
    if not m:
        return None
    try:
        return json.loads('"' + m.group(1) + '"')
    except ValueError:
        return m.group(1)


def leer_hook(crudo: bytes) -> dict:
    """Saca del JSON del hook solo lo que hace falta. El hook manda como mucho los primeros 16 kB,
    así que el JSON puede venir cortado: entonces se buscan los campos uno por uno (van al principio).
    De una pregunta (AskUserQuestion) se guardan el texto y las opciones, para mostrarlas y hacer titilar
    tantos pads como opciones haya. Del resto del evento no se guarda nada."""
    texto = crudo.decode("utf-8", "replace")
    campos = ("session_id", "hook_event_name", "notification_type", "tool_name", "cwd", "source", "message")
    try:
        d = json.loads(texto)
    except ValueError:
        return {k: v for k in campos if (v := _campo(texto, k)) is not None}
    ev = {k: d.get(k) for k in campos if isinstance(d.get(k), str)}
    entrada = d.get("tool_input") if isinstance(d.get("tool_input"), dict) else {}
    if ev.get("tool_name") == "AskUserQuestion" and isinstance(entrada.get("questions"), list):
        preguntas = []
        for q in entrada["questions"][:4]:
            if not isinstance(q, dict):
                continue
            opciones = [str(o.get("label", ""))[:80] for o in (q.get("options") or []) if isinstance(o, dict)][:4]
            preguntas.append({"texto": str(q.get("question", ""))[:300], "titulo": str(q.get("header", ""))[:40],
                              "opciones": opciones, "varias": bool(q.get("multiSelect"))})
        ev["preguntas"] = preguntas
    return ev


def detalle(ev: dict, motivo: str | None) -> dict | None:
    """Qué pide la sesión que te necesita y cuántas opciones hay en pantalla (si se sabe)."""
    if motivo == "pregunta" and ev.get("preguntas"):
        p = ev["preguntas"]
        return {"preguntas": p, "opciones": len(p[0]["opciones"]) or None}
    if motivo == "permiso":
        m = re.search(r"permission to use (.+)$", ev.get("message") or "")
        texto = f"Pide permiso para usar {m.group(1).strip()}" if m else "Pide permiso"
        # el diálogo de permisos de Claude Code: 1 sí, 2 sí y no volver a preguntar, 3 no
        return {"texto": texto, "opciones": 3}
    if motivo == "plan":
        return {"texto": "Quiere que apruebes el plan", "opciones": None}
    if motivo == "pregunta":
        return {"texto": (ev.get("message") or "Te hizo una pregunta")[:300], "opciones": None}
    return None


def traducir(ev: dict) -> tuple[str | None, str | None]:
    """Evento de Claude Code -> (estado, motivo). (None, None) si no cambia nada."""
    nombre, herramienta = ev.get("hook_event_name"), ev.get("tool_name")
    if nombre == "UserPromptSubmit":
        return "trabajando", None
    if nombre == "PreToolUse":
        if herramienta == "AskUserQuestion":
            return "esperando", "pregunta"
        if herramienta == "ExitPlanMode":
            return "esperando", "plan"
        return "trabajando", None
    if nombre == "PostToolUse":  # también llega después de que respondes un permiso o una pregunta
        return "trabajando", None
    if nombre == "Notification":
        tipo = ev.get("notification_type")
        if tipo == "permission_prompt":
            return "esperando", "permiso"
        if tipo == "elicitation_dialog":
            return "esperando", "pregunta"
        if tipo == "idle_prompt":  # Claude Code lleva un rato esperando tu siguiente mensaje
            return "inactivo", None
        return None, None
    if nombre == "Stop":
        return "listo", None
    if nombre == "StopFailure":
        return "error", None
    return None, None


class Sesiones:
    def __init__(self, al_cambiar):
        self._s: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._al_cambiar = al_cambiar
        self._ultimo = None

    def _puesto_libre(self) -> int | None:
        usados = {s.get("puesto") for s in self._s.values()}
        return next((n for n in range(1, PUESTOS + 1) if n not in usados), None)

    def hook(self, crudo: bytes, orden: str | None = None) -> dict:
        ev = leer_hook(crudo)
        sid = ev.get("session_id")
        if not sid:
            return {"aplicado": False, "motivo": "El evento no trae session_id."}
        try:
            n = int(orden) if orden else time.time_ns()
        except ValueError:
            n = time.time_ns()
        nombre = ev.get("hook_event_name")
        with self._lock:
            s = self._s.get(sid)
            if s and n < s["orden"]:
                return {"aplicado": False, "motivo": "Llegó tarde: ya hay un evento más nuevo."}
            if nombre == "SessionEnd":
                self._s.pop(sid, None)
            elif nombre == "SessionStart":
                if not s:
                    self._s[sid] = self._nueva(ev, "listo", None, n)
                    self._s[sid]["puesto"] = self._puesto_libre()
                else:
                    s["orden"], s["ts"] = n, time.time()
            else:
                estado, motivo = traducir(ev)
                if estado is None:
                    return {"aplicado": False}
                if not s:
                    s = self._s[sid] = self._nueva(ev, estado, motivo, n)
                    s["puesto"] = self._puesto_libre()
                s.update(estado=estado, motivo=motivo, orden=n, ts=time.time(),
                         detalle=detalle(ev, motivo) if estado == "esperando" else None)
                if ev.get("cwd"):
                    s["proyecto"] = Path(ev["cwd"]).name or ev["cwd"]
        self._avisar()
        return {"aplicado": True}

    def fijar(self, estado: str, sesion: str = "manual"):
        """Para `starlight claude <estado>` o la página: una sesión «a mano»."""
        if estado not in PRIORIDAD:
            raise ValueError(f"Estado desconocido: {estado}. Usa {', '.join(PRIORIDAD)}.")
        with self._lock:
            puesto = (self._s.get(sesion) or {}).get("puesto") or self._puesto_libre()
            self._s[sesion] = self._nueva({"cwd": ""}, estado, None, time.time_ns())
            self._s[sesion].update(proyecto="a mano", puesto=puesto)
        self._avisar()

    def olvidar(self):
        with self._lock:
            self._s.clear()
        self._avisar()

    @staticmethod
    def _nueva(ev, estado, motivo, n):
        cwd = ev.get("cwd") or ""
        return {"estado": estado, "motivo": motivo, "orden": n, "ts": time.time(), "desde": time.time(),
                "proyecto": Path(cwd).name if cwd else "Claude Code"}

    def _limpiar(self):
        viejo = time.time() - OLVIDAR
        for k in [k for k, s in self._s.items() if s["ts"] < viejo]:
            del self._s[k]

    def resumen(self) -> dict:
        """Estado global (el más urgente) y la lista de sesiones, la más urgente primero."""
        with self._lock:
            self._limpiar()
            lista = sorted(self._s.items(), key=lambda kv: (PRIORIDAD.index(kv[1]["estado"]), -kv[1]["ts"]))
            ahora = time.time()
            sesiones = [{"id": k[:8], "proyecto": s["proyecto"], "estado": s["estado"],
                         "motivo": MOTIVOS.get(s["motivo"]) if s["motivo"] else None,
                         "detalle": s.get("detalle"), "puesto": s.get("puesto"),
                         "hace": round(ahora - s["ts"])} for k, s in lista]
        estado = sesiones[0]["estado"] if sesiones else None
        cuantas = sum(1 for s in sesiones if s["estado"] == estado) if estado else 0
        # cuántas opciones tiene en pantalla la sesión que te necesita (para hacer titilar esos pads)
        opciones = ((sesiones[0].get("detalle") or {}).get("opciones") if estado == "esperando" else None)
        return {"estado": estado, "cuantas": cuantas, "opciones": opciones, "sesiones": sesiones}

    def _avisar(self):
        r = self.resumen()
        clave = (r["estado"], r["opciones"],
                 tuple((s["id"], s["estado"], s["motivo"], s["puesto"], str(s["detalle"])) for s in r["sesiones"]))
        if clave == self._ultimo:
            return
        self._ultimo = clave
        try:
            self._al_cambiar(r)
        except Exception:  # nunca romper el hook
            pass
