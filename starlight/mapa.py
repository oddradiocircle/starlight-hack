"""Mapa de la Hercules DJControl Starlight.

Traduce MIDI crudo a controles con nombre (entrada) y órdenes con nombre a MIDI (salida).

Fuentes: mapeo de Mixxx 2.5, pruebas en el aparato (2026-11-09 y 2026-11-10) e
ingeniería inversa del firmware DJSTARLIGHT_S401 (paleta, efectos, color RGB, modos).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

# ----------------------------------------------------------------------------- canales
CANAL_DECK = {1: "A", 2: "B"}        # 0x91 / 0x92
CANAL_SHIFT = {4: "A", 5: "B"}       # 0x94 / 0x95: el mismo deck con Shift presionado
CANAL_PADS = {6: "A", 7: "B"}        # 0x96 / 0x97
ST_DECK = {"A": 0x91, "B": 0x92}
ST_PADS = {"A": 0x96, "B": 0x97}

# ----------------------------------------------------------------------------- entradas
BOTONES_GLOBAL = {0x03: "shift", 0x01: "bassfilter"}
BOTONES_DECK = {
    0x07: "play", 0x06: "cue", 0x05: "sync", 0x0C: "pfl", 0x08: "jog.toque",
    0x0F: "modo.hotcue", 0x10: "modo.loop", 0x11: "modo.fx", 0x12: "modo.sampler",
}
CONTINUOS_GLOBAL = {0x00: "crossfader", 0x03: "master", 0x04: "audifonos"}
CONTINUOS_DECK = {0x00: "volumen", 0x01: "eq", 0x02: "eq", 0x08: "tempo"}  # eq: 01 filtro, 02 bajos
JOGS = {0x09: "borde", 0x0A: "arriba"}
MODOS = ("hotcue", "loop", "fx", "sampler")
NOTA_VINYL = 0x03  # un solo botón físico que avisa por los canales de A y de B

# ----------------------------------------------------------------------------- salidas
LUCES_DECK = {"play": 0x07, "cue": 0x06, "sync": 0x05, "pfl": 0x0C}
LUCES_GLOBAL = {"vinyl": (0x91, 0x03), "bassfilter": (0x90, 0x01)}
BASE_AUTO = (0x90, 0x24)
NOTA_BASE_PALETA = 0x22   # oculto en el firmware: 13 x efecto + color (1-12)
NOTA_BASE_RGB = 0x23      # color RGB empaquetado en 7 bits: rr ggg bb
VOLCADO = (0xB0, 0x7F, 0x7F)  # pide la posición de todas las perillas y faders
LADOS = {"izq": ("A",), "der": ("B",), "ambos": ("A", "B")}
LADO_DE_DECK = {"A": "izq", "B": "der"}

PALETA = {  # número: (nombre, (R, G, B)), leída del firmware
    1: ("fucsia", (200, 0, 100)), 2: ("salmon", (200, 60, 60)), 3: ("rojo", (255, 0, 0)),
    4: ("naranja", (255, 92, 0)), 5: ("amarillo", (255, 240, 16)), 6: ("lima", (118, 200, 16)),
    7: ("verde", (0, 255, 0)), 8: ("aguamarina", (50, 255, 160)), 9: ("celeste", (16, 200, 255)),
    10: ("azul", (0, 0, 255)), 11: ("indigo", (60, 40, 200)), 12: ("morado", (100, 0, 200)),
}
EFECTOS = {"fijo": 0, "parpadeo": 2, "respira": 3}


def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def color_paleta(color) -> int:
    """Acepta número (1-12) o nombre ('rojo', 'índigo'...). Devuelve el número."""
    if isinstance(color, int) or str(color).isdigit():
        n = int(color)
        if n in PALETA:
            return n
        raise ValueError(f"El color debe ir de 1 a 12, no {n}")
    buscado = _sin_tildes(str(color))
    for n, (nombre, _) in PALETA.items():
        if nombre == buscado:
            return n
    raise ValueError(f"Color desconocido: {color}. Opciones: " + ", ".join(v[0] for v in PALETA.values()))


def rgb_a_7bits(r: int, g: int, b: int) -> int:
    return (round(r / 255 * 3) << 5) | (round(g / 255 * 7) << 2) | round(b / 255 * 3)


def rgb_de_7bits(v: int) -> tuple[int, int, int]:
    """El color que realmente muestra el aparato para un valor de la nota 23."""
    return ((v >> 5) & 3) * 85, round(((v >> 2) & 7) * 255 / 7), (v & 3) * 85


def hex_a_rgb(texto: str) -> tuple[int, int, int]:
    t = texto.strip().lstrip("#")
    if len(t) != 6:
        raise ValueError(f"Color RGB inválido: {texto}. Usa el formato #rrggbb")
    return int(t[0:2], 16), int(t[2:4], 16), int(t[4:6], 16)


# ----------------------------------------------------------------------------- eventos
@dataclass
class Evento:
    control: str            # "A.play", "crossfader", "A.pad3", "A.jog", "vinyl"...
    tipo: str               # boton | continuo | jog | pad | desconocido
    valor: float            # boton/pad: 1 o 0 · continuo: 0..1 · jog: pasos (+ horario)
    shift: bool = False
    extra: dict = field(default_factory=dict)
    crudo: tuple = ()

    def a_dict(self) -> dict:
        return {"control": self.control, "clase": self.tipo, "valor": self.valor,
                "shift": self.shift, "extra": self.extra, "crudo": list(self.crudo)}


class Decodificador:
    """Convierte mensajes MIDI crudos en Eventos. Recuerda MSB/LSB para los valores de 14 bits."""

    def __init__(self):
        self._msb: dict = {}
        self._lsb: dict = {}

    def __call__(self, st: int, d1: int, d2: int) -> Evento | None:
        tipo, ch = st & 0xF0, st & 0x0F
        crudo = (st, d1, d2)
        if tipo in (0x80, 0x90):
            return self._nota(ch, d1, 1.0 if (tipo == 0x90 and d2) else 0.0, crudo)
        if tipo == 0xB0:
            return self._cc(ch, d1, d2, crudo)
        return Evento(f"crudo.{st:02X}{d1:02X}", "desconocido", d2 / 127, crudo=crudo)

    def _nota(self, ch, d1, on, crudo):
        if ch in CANAL_PADS:
            deck, pad, fila = CANAL_PADS[ch], (d1 & 7) + 1, d1 >> 4
            if pad <= 4 and fila < 4:
                return Evento(f"{deck}.pad{pad}", "pad", on, shift=bool(d1 & 8),
                              extra={"modo": MODOS[fila]}, crudo=crudo)
        elif ch == 0 and d1 in BOTONES_GLOBAL:
            return Evento(BOTONES_GLOBAL[d1], "boton", on, crudo=crudo)
        elif ch in CANAL_DECK or ch in CANAL_SHIFT:
            deck = CANAL_DECK.get(ch) or CANAL_SHIFT[ch]
            shift = ch in CANAL_SHIFT
            if d1 == NOTA_VINYL:
                if deck == "B":
                    return None  # el mismo botón Vinyl ya llegó por el canal de A
                return Evento("vinyl", "boton", on, shift=shift, crudo=crudo)
            if d1 in BOTONES_DECK:
                return Evento(f"{deck}.{BOTONES_DECK[d1]}", "boton", on, shift=shift, crudo=crudo)
        return Evento(f"crudo.{crudo[0]:02X}{d1:02X}", "desconocido", on, crudo=crudo)

    def _cc(self, ch, d1, d2, crudo):
        deck = CANAL_DECK.get(ch) or CANAL_SHIFT.get(ch)
        shift = ch in CANAL_SHIFT
        if deck and d1 in JOGS:
            pasos = d2 if d2 < 64 else d2 - 128
            return Evento(f"{deck}.jog", "jog", pasos, shift=shift,
                          extra={"superficie": JOGS[d1]}, crudo=crudo)
        es_lsb = 0x20 <= d1 < 0x40
        base = d1 - 0x20 if es_lsb else d1
        clave = (ch, base)
        (self._lsb if es_lsb else self._msb)[clave] = d2
        if clave not in self._msb:
            return None  # LSB sin MSB todavía
        valor = ((self._msb[clave] << 7) | self._lsb.get(clave, 0)) / 16383
        if ch == 0 and base in CONTINUOS_GLOBAL:
            return Evento(CONTINUOS_GLOBAL[base], "continuo", valor, crudo=crudo)
        if deck and base in CONTINUOS_DECK:
            extra = {"modo": "filtro" if base == 0x01 else "bajos"} if CONTINUOS_DECK[base] == "eq" else {}
            return Evento(f"{deck}.{CONTINUOS_DECK[base]}", "continuo", valor, shift=shift,
                          extra=extra, crudo=crudo)
        return Evento(f"crudo.{crudo[0]:02X}{base:02X}", "desconocido", valor, crudo=crudo)


# ----------------------------------------------------------------------------- órdenes -> MIDI
def msg_luz(control: str, encendida: bool) -> list[tuple]:
    v = 0x7F if encendida else 0x00
    if control in LUCES_GLOBAL:
        st, nota = LUCES_GLOBAL[control]
        return [(st, nota, v)]
    deck, _, nombre = control.partition(".")
    if deck in ST_DECK and nombre in LUCES_DECK:
        return [(ST_DECK[deck], LUCES_DECK[nombre], v)]
    raise ValueError(f"Ese control no tiene luz: {control}. Con luz: "
                     + ", ".join(sorted([f"{d}.{n}" for d in ST_DECK for n in LUCES_DECK] + list(LUCES_GLOBAL))))


def msg_pad(deck: str, pad: int, encendida: bool, modo: str = "hotcue", shift: bool = False) -> list[tuple]:
    if deck not in ST_PADS or not 1 <= pad <= 4 or modo not in MODOS:
        raise ValueError("Pad inválido: deck A/B, pad 1-4, modo hotcue/loop/fx/sampler")
    nota = MODOS.index(modo) * 16 + (8 if shift else 0) + pad - 1
    return [(ST_PADS[deck], nota, 0x7F if encendida else 0)]


def msg_base_paleta(color, efecto: str = "fijo", lado: str = "ambos") -> list[tuple]:
    if efecto not in EFECTOS:
        raise ValueError(f"Efecto desconocido: {efecto}. Opciones: {', '.join(EFECTOS)}")
    valor = 13 * EFECTOS[efecto] + color_paleta(color)
    return [(BASE_AUTO[0], BASE_AUTO[1], 0)] + [(ST_DECK[d], NOTA_BASE_PALETA, valor) for d in LADOS[lado]]


def msg_base_rgb(r: int, g: int, b: int, lado: str = "ambos") -> list[tuple]:
    valor = rgb_a_7bits(r, g, b)
    return [(BASE_AUTO[0], BASE_AUTO[1], 0)] + [(ST_DECK[d], NOTA_BASE_RGB, valor) for d in LADOS[lado]]


SYSEX_HERCULES = bytes([0xF0, 0x00, 0x01, 0x4E, 0x1B])  # Guillemot (00 01 4E) + modelo Starlight (1B)


def sysex_base_rgb(r: int, g: int, b: int, lado: str = "izq") -> bytes:
    """Color de la base con 7 bits por canal (SysEx privado, parámetro 7F00; hallado en el firmware).
    r, g, b van de 0 a 255; el aparato usa la mitad (0-127) y la duplica en su luz."""
    sub = {"izq": 0, "der": 1}[lado]
    return SYSEX_HERCULES + bytes([0x02, 0x00, 0x7F, sub, 0x00, r >> 1, g >> 1, b >> 1, 0x00, 0xF7])


PARAM_COLOR, PARAM_MODO_COMPUTADOR, PARAM_DEMO = 0x7F00, 0x7F7E, 0x7F7F
PARAM_CRUDO, PARAM_CALIBRACION, PARAM_INTERRUPTOR, PARAM_ID = 0x14, 0x12, 0x20, 0x7F7D
ESCRITURAS_BLOQUEADAS = {PARAM_CALIBRACION}   # grabaría la calibración de fábrica en la flash
IDENTIDAD = bytes.fromhex("F0 7E 7F 06 01 F7")
NOMBRES_CRUDO = ["audifonos", "master", "crossfader", "A.volumen", "B.volumen", "A.tempo", "B.tempo", "A.eq", "B.eq"]


def sysex_orden(tipo: int, param: int, sub: int = 0, valor=(0, 0, 0, 0)) -> bytes:
    """Mensaje del protocolo privado: tipo 1 = leer, 2 = escribir."""
    return SYSEX_HERCULES + bytes([tipo, param & 0xFF, param >> 8, sub & 0xFF, sub >> 8, *valor, 0xF7])


def leer_respuesta(datos: bytes) -> dict | None:
    """Respuesta del protocolo privado: tipo 3 = lectura, 5 = escritura aceptada; datos en pares de 7 bits."""
    if datos[:5] != SYSEX_HERCULES or len(datos) < 11:
        return None
    cuerpo = datos[10:-1]
    return {"tipo": datos[5], "param": datos[6] | datos[7] << 8, "sub": datos[8] | datos[9] << 8,
            "valores": [cuerpo[i] | (cuerpo[i + 1] << 7) for i in range(0, len(cuerpo) - 1, 2)],
            "hex": datos.hex(" ").upper()}


def es_escritura_bloqueada(datos: bytes) -> bool:
    return (datos[:5] == SYSEX_HERCULES and len(datos) > 7 and datos[5] == 2
            and (datos[6] | datos[7] << 8) in ESCRITURAS_BLOQUEADAS)


def rgb_completo(r: int, g: int, b: int) -> tuple[int, int, int]:
    """El color que realmente muestra el aparato con el SysEx 7F00 (7 bits por canal)."""
    return (r >> 1) << 1, (g >> 1) << 1, (b >> 1) << 1


def msg_base_auto() -> list[tuple]:
    return [(BASE_AUTO[0], BASE_AUTO[1], 0x7F)]


def msg_modo(deck: str, modo: str) -> list[tuple]:
    if deck not in ST_DECK or modo not in MODOS:
        raise ValueError("Modo inválido: deck A/B y modo hotcue/loop/fx/sampler")
    return [(ST_DECK[deck], 0x0F + MODOS.index(modo), 0x7F)]


def catalogo() -> dict:
    """Lista de controles y luces, para clientes de la API."""
    entradas = ["shift", "bassfilter", "vinyl", "crossfader", "master", "audifonos"]
    for d in ("A", "B"):
        entradas += [f"{d}.{n}" for n in ("play", "cue", "sync", "pfl", "jog", "jog.toque", "volumen", "eq",
                                          "tempo", "modo.hotcue", "modo.loop", "modo.fx", "modo.sampler")]
        entradas += [f"{d}.pad{i}" for i in range(1, 5)]
    luces = sorted([f"{d}.{n}" for d in ST_DECK for n in LUCES_DECK] + list(LUCES_GLOBAL))
    return {"entradas": entradas, "luces": luces, "modos": list(MODOS), "efectos": list(EFECTOS),
            "paleta": {n: {"nombre": v[0], "rgb": v[1]} for n, v in PALETA.items()}}
