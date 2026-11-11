"""Pruebas en pantalla.

Alguien (Claude, un script o tú) propone una prueba; la página /pruebas la muestra con un sonido;
la persona la ejecuta, mira el aparato y responde con un clic. Las respuestas quedan en
~/.starlight/pruebas.jsonl.

Una prueba es un preset de este archivo o una lista de pasos:
    {"titulo": "...", "mirar": "...", "opciones": ["Sí", "No"],
     "pasos": [{"midi": [145, 7, 127]}, {"sysex": "F0 7E 7F 06 01 F7"}, {"esperar": 0.5}]}
"""
from __future__ import annotations

import json
import threading
import time
import uuid

from . import mapa
from .aparato import AparatoDesconectado
from .perfiles import HOGAR

ARCHIVO = HOGAR / "pruebas.jsonl"


# ----------------------------------------------------------------------------- presets
def _fade_sysex(ap, *_):
    ap.enviar([(*mapa.BASE_AUTO, 0)], avisar=False)
    for _ in range(2):
        for i in list(range(128)) + list(range(127, -1, -1)):
            ap.sysex(mapa.sysex_base_rgb(i * 2, 0, 0, "izq"))
            ap.enviar([(0x92, mapa.NOTA_BASE_RGB, mapa.rgb_a_7bits(i * 2, 0, 0))], avisar=False)
            time.sleep(0.012)
    ap.enviar([(0x91, mapa.NOTA_BASE_RGB, 0), (0x92, mapa.NOTA_BASE_RGB, 0)], avisar=False)


COLORES_FINOS = [(60, 0, 110), (255, 140, 190), (0, 130, 110), (200, 160, 40)]


def _colores_sysex(ap, *_):
    ap.enviar([(*mapa.BASE_AUTO, 0)], avisar=False)
    for r, g, b in COLORES_FINOS:
        ap.sysex(mapa.sysex_base_rgb(r, g, b, "izq"))
        ap.enviar([(0x92, mapa.NOTA_BASE_RGB, mapa.rgb_a_7bits(r, g, b))], avisar=False)
        time.sleep(2.5)


def _escritorio(ap, motor):
    if motor:
        motor.activar("escritorio")


PRESETS = {
    "escritorio": {
        "titulo": "Perfil Escritorio: ¿qué funciona?",
        "mirar": "Al ejecutar se activa el perfil Escritorio y se prenden Play, Cue, Sync y los 4 pads del deck A. Prueba: Play A pausa o reanuda Spotify · Cue A canción anterior · Sync A siguiente · gira el Jog B sobre esta página (debe desplazarse) · pad 1 abre la captura de pantalla (Esc para cerrar) · pad 3 muestra el escritorio. Volume A pone el volumen de Windows en su posición: muévelo con cuidado. Escribe abajo lo que no funcionó.",
        "opciones": ["Todo funcionó", "Algunas cosas no", "Nada funcionó"],
        "fn": _escritorio,
    },
    "fade-sysex": {
        "titulo": "Fade de rojo: mensaje nuevo contra el de siempre",
        "mirar": "Mira la base unos 6 segundos. El rojo sube y baja dos veces en los dos lados al mismo tiempo. "
                 "La izquierda usa el mensaje nuevo (SysEx, 128 niveles); la derecha, el de siempre (nota 23, 4 niveles).",
        "opciones": ["La izquierda es más suave", "Se ven iguales", "La derecha es más suave", "No se prendió nada"],
        "fn": _fade_sysex,
    },
    "colores-sysex": {
        "titulo": "Colores finos: mensaje nuevo contra el de siempre",
        "mirar": "Mira la base 10 segundos: pasan 4 colores (morado oscuro, rosa claro, verde azulado y dorado). "
                 "La izquierda los pide exactos con el mensaje nuevo; la derecha, lo más parecido con el de siempre.",
        "opciones": ["La izquierda se ve distinta y más fiel", "Se ven iguales", "La izquierda no se prendió"],
        "fn": _colores_sysex,
    },
}


class Pruebas:
    def __init__(self, aparato, motor=None):
        self.aparato, self.motor = aparato, motor
        self.actual: dict | None = None
        self.corriendo = False
        self._lock = threading.Lock()

    @staticmethod
    def _publica(p):
        return None if p is None else {k: v for k, v in p.items() if k != "fn"}

    def proponer(self, datos: dict) -> dict:
        base = dict(PRESETS[datos["preset"]]) if datos.get("preset") else {}
        if datos.get("preset") and datos["preset"] not in PRESETS:
            raise ValueError(f"No hay una prueba «{datos['preset']}». Hay: {', '.join(PRESETS)}")
        p = {**base, **{k: v for k, v in datos.items() if k in ("titulo", "mirar", "opciones", "pasos", "perfil")}}
        if not p.get("titulo"):
            raise ValueError("Falta el título de la prueba.")
        p.setdefault("opciones", ["Sí", "No"])
        p.update(id=uuid.uuid4().hex[:8], preset=datos.get("preset"), creada=time.strftime("%Y-%m-%d %H:%M:%S"))
        with self._lock:
            self.actual = p
        self.aparato.anunciar({"tipo": "prueba", "prueba": self._publica(p)})
        return self._publica(p)

    def ejecutar(self):
        with self._lock:
            p = self.actual
            if not p:
                raise ValueError("No hay una prueba pendiente.")
            if self.corriendo:
                raise ValueError("La prueba ya está corriendo.")
            self.corriendo = True
        threading.Thread(target=self._correr, args=(p,), daemon=True).start()

    def _correr(self, p):
        if self.motor:
            self.motor.pausado = True
        self.aparato.anunciar({"tipo": "prueba-estado", "id": p["id"], "corriendo": True})
        error = None
        try:
            if p.get("perfil") and self.motor:
                self.motor.activar(p["perfil"])
            if p.get("fn"):
                p["fn"](self.aparato, self.motor)
            for paso in p.get("pasos") or []:
                if "midi" in paso:
                    self.aparato.enviar([tuple(int(x) for x in paso["midi"])])
                elif "sysex" in paso:
                    self.aparato.sysex(bytes.fromhex(paso["sysex"]))
                elif "esperar" in paso:
                    time.sleep(min(10.0, float(paso["esperar"])))
        except AparatoDesconectado as e:
            error = str(e)
        except Exception as e:  # una prueba mal escrita no debe tumbar el servidor
            error = f"La prueba falló: {e}"
        finally:
            self.corriendo = False
            if self.motor:
                self.motor.pausado = False
            self.aparato.anunciar({"tipo": "prueba-estado", "id": p["id"], "corriendo": False, "error": error})

    def responder(self, id_: str, respuesta: str, nota: str = "") -> dict:
        with self._lock:
            p = self.actual
            if not p or p["id"] != id_:
                raise ValueError("Esa prueba ya no está pendiente.")
            self.actual = None
        registro = {"fecha": time.strftime("%Y-%m-%d %H:%M:%S"), "id": id_, "titulo": p["titulo"],
                    "preset": p.get("preset"), "respuesta": respuesta, "nota": (nota or "").strip()}
        HOGAR.mkdir(parents=True, exist_ok=True)
        with ARCHIVO.open("a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
        self.aparato.anunciar({"tipo": "prueba-respuesta", **registro})
        return registro

    def historial(self, n: int = 20) -> list:
        try:
            lineas = ARCHIVO.read_text(encoding="utf-8").splitlines()[-n:]
        except OSError:
            return []
        return [json.loads(x) for x in reversed(lineas) if x.strip()]

    def info(self) -> dict:
        return {"actual": self._publica(self.actual), "corriendo": self.corriendo, "historial": self.historial(),
                "presets": {k: v["titulo"] for k, v in PRESETS.items()}}
