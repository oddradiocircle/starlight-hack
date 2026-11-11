#!/usr/bin/env python3
"""
starlight.py - habla directo con la Hercules DJControl Starlight por MIDI.

Usa la API MIDI de Windows (winmm.dll) con ctypes: no hay que instalar nada.
El mapa de controles sale del mapeo de Mixxx
(C:\\Program Files\\Mixxx\\controllers\\Hercules DJControl Starlight.midi.xml).

Uso:
  python starlight.py puertos             Lista los puertos MIDI de Windows
  python starlight.py escuchar [minutos]  Muestra cada control que tocas y enciende su luz
  python starlight.py luces [N ...]       Demo de luces (todas las partes, o solo las N indicadas)
  python starlight.py enviar 91 07 7F     Envía un mensaje MIDI (en hexadecimal)
  python starlight.py reset               Apaga las luces y devuelve la base a su show normal

Importante: en Windows solo un programa a la vez puede abrir el puerto MIDI.
Cierra Mixxx, Serato, DJUCED o Bome antes de usar este script.
"""
import ctypes
import ctypes.wintypes as wt
import json
import queue
import sys
import time
from pathlib import Path

# --------------------------------------------------------------------------
# Capa winmm (API MIDI de Windows)
# --------------------------------------------------------------------------
_winmm = ctypes.WinDLL("winmm")


class _MIDIINCAPSW(ctypes.Structure):
    _fields_ = [("wMid", wt.WORD), ("wPid", wt.WORD), ("vDriverVersion", wt.UINT),
                ("szPname", wt.WCHAR * 32), ("dwSupport", wt.DWORD)]


class _MIDIOUTCAPSW(ctypes.Structure):
    _fields_ = [("wMid", wt.WORD), ("wPid", wt.WORD), ("vDriverVersion", wt.UINT),
                ("szPname", wt.WCHAR * 32), ("wTechnology", wt.WORD), ("wVoices", wt.WORD),
                ("wNotes", wt.WORD), ("wChannelMask", wt.WORD), ("dwSupport", wt.DWORD)]


_MidiInProc = ctypes.WINFUNCTYPE(None, wt.HANDLE, wt.UINT, ctypes.c_size_t,
                                 ctypes.c_size_t, ctypes.c_size_t)
_HP = ctypes.POINTER(wt.HANDLE)

_SIGS = {
    "midiInGetNumDevs": [],
    "midiOutGetNumDevs": [],
    "midiInGetDevCapsW": [ctypes.c_size_t, ctypes.c_void_p, wt.UINT],
    "midiOutGetDevCapsW": [ctypes.c_size_t, ctypes.c_void_p, wt.UINT],
    "midiInOpen": [_HP, wt.UINT, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD],
    "midiOutOpen": [_HP, wt.UINT, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD],
    "midiInStart": [wt.HANDLE],
    "midiInStop": [wt.HANDLE],
    "midiInReset": [wt.HANDLE],
    "midiInClose": [wt.HANDLE],
    "midiOutClose": [wt.HANDLE],
    "midiOutShortMsg": [wt.HANDLE, wt.DWORD],
    "midiInGetErrorTextW": [wt.UINT, wt.LPWSTR, wt.UINT],
    "midiOutGetErrorTextW": [wt.UINT, wt.LPWSTR, wt.UINT],
}
for _name, _args in _SIGS.items():
    _fn = getattr(_winmm, _name)
    _fn.argtypes = _args
    _fn.restype = wt.UINT

CALLBACK_FUNCTION = 0x00030000
MIM_DATA = 0x3C3
MMSYSERR_ALLOCATED = 4


class MidiError(RuntimeError):
    pass


def _check(res, salida=False):
    if res:
        buf = ctypes.create_unicode_buffer(256)
        fn = _winmm.midiOutGetErrorTextW if salida else _winmm.midiInGetErrorTextW
        fn(res, buf, 256)
        msg = f"Error winmm {res}: {buf.value}"
        if res == MMSYSERR_ALLOCATED:
            msg += ("\n-> Otro programa (Mixxx, Serato, DJUCED, Bome...) tiene el puerto "
                    "abierto. Ciérralo y repite.")
        raise MidiError(msg)


def entradas():
    nombres = []
    for i in range(_winmm.midiInGetNumDevs()):
        caps = _MIDIINCAPSW()
        _check(_winmm.midiInGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps)))
        nombres.append(caps.szPname)
    return nombres


def salidas():
    nombres = []
    for i in range(_winmm.midiOutGetNumDevs()):
        caps = _MIDIOUTCAPSW()
        _check(_winmm.midiOutGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps)), True)
        nombres.append(caps.szPname)
    return nombres


def _buscar(nombres, texto):
    for i, n in enumerate(nombres):
        if texto.lower() in n.lower():
            return i
    raise MidiError(f"No encontré un puerto que contenga '{texto}'. Puertos: {nombres}")


class Starlight:
    """Abre la entrada y la salida MIDI del controlador.

    - st.cola recibe tuplas (segundos, status, data1, data2) por cada mensaje.
    - st.enviar(status, data1, data2) manda un mensaje (luces, etc.).
    """

    def __init__(self, nombre="Starlight", entrada=True, salida=True):
        self.cola = queue.Queue()
        self._hin = wt.HANDLE()
        self._hout = wt.HANDLE()
        self._cb = _MidiInProc(self._callback)  # se guarda para que no lo borre el GC
        if salida:
            idx = _buscar(salidas(), nombre)
            _check(_winmm.midiOutOpen(ctypes.byref(self._hout), idx, None, 0, 0), True)
        if entrada:
            idx = _buscar(entradas(), nombre)
            _check(_winmm.midiInOpen(ctypes.byref(self._hin), idx,
                                     ctypes.cast(self._cb, ctypes.c_void_p), 0,
                                     CALLBACK_FUNCTION))
            _check(_winmm.midiInStart(self._hin))

    def _callback(self, _h, msg, _inst, p1, p2):
        if msg == MIM_DATA:
            self.cola.put((p2 / 1000.0, p1 & 0xFF, (p1 >> 8) & 0x7F, (p1 >> 16) & 0x7F))

    def enviar(self, status, d1, d2=0):
        dato = (status & 0xFF) | ((d1 & 0x7F) << 8) | ((d2 & 0x7F) << 16)
        _check(_winmm.midiOutShortMsg(self._hout, dato), True)

    def cerrar(self):
        if self._hin:
            _winmm.midiInStop(self._hin)
            _winmm.midiInReset(self._hin)
            _winmm.midiInClose(self._hin)
            self._hin = wt.HANDLE()
        if self._hout:
            _winmm.midiOutClose(self._hout)
            self._hout = wt.HANDLE()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cerrar()


# --------------------------------------------------------------------------
# Mapa del controlador (según Mixxx)
# --------------------------------------------------------------------------
DECKS = {1: "A", 2: "B", 4: "A+Shift", 5: "B+Shift"}
NOTAS_DECK = {0x07: "Play", 0x06: "Cue", 0x05: "Sync", 0x0C: "Auriculares (PFL)",
              0x08: "Jog (toque arriba)"}
CC_DECK = {0x00: "Volumen", 0x01: "Filtro", 0x02: "Bajos (EQ)", 0x08: "Tempo (MSB)",
           0x28: "Tempo (LSB)", 0x09: "Jog (borde)", 0x0A: "Jog (scratch)"}
MODOS_PAD = {0: "Hot Cue", 1: "Loop", 2: "FX", 3: "Sampler"}
JOGS = {0x09, 0x0A}

# LEDs conocidos
BASE_AUTO = (0x90, 0x24)            # 7F = show automático de la base, 00 = control manual
BASE_IZQ, BASE_DER = (0x91, 0x23), (0x92, 0x23)
LEDS_DECK = [0x07, 0x06, 0x05, 0x0C]  # Play, Cue, Sync, PFL
LED_VINYL = (0x91, 0x03)


def describir(st, d1, d2):
    tipo, canal = st & 0xF0, st & 0x0F
    if tipo in (0x80, 0x90):
        estado = "suelta" if (tipo == 0x80 or d2 == 0) else "presiona"
        if canal == 0 and d1 == 0x03:
            return f"SHIFT ({estado})"
        if canal == 1 and d1 == 0x03:
            return f"Vinyl ({estado})"
        if canal in (6, 7):
            deck = "A" if canal == 6 else "B"
            modo = MODOS_PAD.get(d1 >> 4, f"modo {d1 >> 4}")
            shift = " +Shift" if d1 & 0x08 else ""
            return f"Pad {(d1 & 0x07) + 1} deck {deck} [{modo}{shift}] ({estado})"
        if canal in DECKS:
            return f"{NOTAS_DECK.get(d1, f'botón 0x{d1:02X}')} deck {DECKS[canal]} ({estado})"
        return f"¿botón nuevo? canal {canal + 1} nota 0x{d1:02X} ({estado})"
    if tipo == 0xB0:
        if canal == 0 and d1 == 0x00:
            return f"Crossfader = {d2}"
        if canal in DECKS:
            nombre = CC_DECK.get(d1, f"control 0x{d1:02X}")
            if d1 in JOGS:
                return f"{nombre} deck {DECKS[canal]}"
            return f"{nombre} deck {DECKS[canal]} = {d2}"
        return f"¿control nuevo? canal {canal + 1} CC 0x{d1:02X} = {d2}"
    return f"otro mensaje (tipo 0x{tipo:02X})"


def _hex(st, d1, d2):
    return f"{st:02X} {d1:02X} {d2:02X}"


# --------------------------------------------------------------------------
# Luces
# --------------------------------------------------------------------------
def base_manual(st, manual=True):
    st.enviar(*BASE_AUTO, 0x00 if manual else 0x7F)


# Hallado en el firmware (DJSTARLIGHT_S401) y verificado en el aparato el 2026-11-10
PALETA = {  # número: (nombre, (R, G, B))
    1: ("fucsia", (200, 0, 100)), 2: ("salmón", (200, 60, 60)), 3: ("rojo", (255, 0, 0)),
    4: ("naranja", (255, 92, 0)), 5: ("amarillo", (255, 240, 16)), 6: ("lima", (118, 200, 16)),
    7: ("verde", (0, 255, 0)), 8: ("aguamarina", (50, 255, 160)), 9: ("celeste", (16, 200, 255)),
    10: ("azul", (0, 0, 255)), 11: ("índigo", (60, 40, 200)), 12: ("morado", (100, 0, 200)),
}
EFECTOS = {"fijo": 0, "parpadeo": 2, "respira": 3}
MODOS_PAD_CMD = {"hotcue": 0x0F, "loop": 0x10, "fx": 0x11, "sampler": 0x12}
LADOS = {"izq": (0x91,), "der": (0x92,), "ambos": (0x91, 0x92)}


def base_color(st, color, efecto="fijo", lado="ambos"):
    """Color de la paleta (1-12) con efecto: fijo, parpadeo o respira."""
    base_manual(st)
    valor = 13 * EFECTOS[efecto] + int(color)
    for ch in LADOS[lado]:
        st.enviar(ch, 0x22, valor)


def base_rgb(st, r, g, b, lado="ambos"):
    """Color libre. El firmware usa 7 bits: rojo 2 bits, verde 3 bits, azul 2 bits."""
    base_manual(st)
    valor = (round(r / 255 * 3) << 5) | (round(g / 255 * 7) << 2) | round(b / 255 * 3)
    for ch in LADOS[lado]:
        st.enviar(ch, 0x23, valor)


def modo_pads(st, deck, modo):
    """Cambia el modo de los pads desde el PC. deck: 'A' o 'B'; modo: hotcue, loop, fx, sampler."""
    st.enviar(0x91 if deck.upper() == "A" else 0x92, MODOS_PAD_CMD[modo], 0x7F)


def apagar_todo(st):
    for ch in (0x91, 0x92):
        for n in LEDS_DECK:
            st.enviar(ch, n, 0)
    st.enviar(*LED_VINYL, 0)
    for ch in (0x96, 0x97):
        for modo in (0x00, 0x10, 0x20, 0x30):
            for p in range(8):
                st.enviar(ch, modo + p, 0)


def saludo(st):
    """Animación corta para confirmar que hay conexión."""
    base_manual(st)
    for v in list(range(0, 128, 8)) + list(range(127, -1, -8)):
        st.enviar(*BASE_IZQ, v)
        st.enviar(*BASE_DER, 127 - v)
        time.sleep(0.02)
    for n in LEDS_DECK:
        for ch in (0x91, 0x92):
            st.enviar(ch, n, 0x7F)
        time.sleep(0.12)
    time.sleep(0.3)
    apagar_todo(st)
    st.enviar(*BASE_IZQ, 0)
    st.enviar(*BASE_DER, 0)
    base_manual(st, False)


def _rampa(st, leds, subir_s=2.0):
    valores = list(range(0, 128, 4)) + [127]
    for v in valores + valores[::-1]:
        for led in leds:
            st.enviar(*led, v)
        time.sleep(subir_s / len(valores))


def parte_base_izq(st):
    for _ in range(2):
        _rampa(st, [BASE_IZQ])


def parte_base_der(st):
    for _ in range(2):
        _rampa(st, [BASE_DER])


def parte_base_escalones(st):
    for v in (0, 16, 32, 48, 64, 80, 96, 112, 127):
        print(f"     valor {v}", flush=True)
        st.enviar(*BASE_IZQ, v)
        st.enviar(*BASE_DER, v)
        time.sleep(1.2)


def parte_botones(st):
    for n, nombre in ((0x07, "Play"), (0x06, "Cue"), (0x05, "Sync"), (0x0C, "Auriculares (PFL)")):
        print(f"     {nombre}", flush=True)
        for ch in (0x91, 0x92):
            st.enviar(ch, n, 0x7F)
        time.sleep(2)
        for ch in (0x91, 0x92):
            st.enviar(ch, n, 0)
        time.sleep(0.5)
    print("     Vinyl", flush=True)
    st.enviar(*LED_VINYL, 0x7F)
    time.sleep(2)
    st.enviar(*LED_VINYL, 0)


def _parte_pads(modo):
    def parte(st):
        for p in range(4):
            print(f"     pad {p + 1} (nota 0x{modo + p:02X})", flush=True)
            st.enviar(0x96, modo + p, 0x7F)
            st.enviar(0x97, modo + p, 0x7F)
            time.sleep(1)
        time.sleep(2)
        for p in range(4):
            st.enviar(0x96, modo + p, 0)
            st.enviar(0x97, modo + p, 0)
    return parte


PARTES = [
    ("Base izquierda: sube y baja de intensidad 2 veces (8 s)", parte_base_izq),
    ("Base derecha: sube y baja de intensidad 2 veces (8 s)", parte_base_der),
    ("Base en 9 escalones, de apagada a máxima (11 s)", parte_base_escalones),
    ("Botones de los decks: Play, Cue, Sync, Auriculares y Vinyl (13 s)", parte_botones),
    ("Pads en modo Hot Cue, uno por uno (6 s)", _parte_pads(0x00)),
    ("Pads en modo Loop, uno por uno (6 s)", _parte_pads(0x10)),
    ("Pads en modo FX, uno por uno (6 s)", _parte_pads(0x20)),
    ("Pads en modo Sampler, uno por uno (6 s)", _parte_pads(0x30)),
]


def demo_luces(st, numeros=None):
    numeros = list(numeros or range(1, len(PARTES) + 1))
    for i in numeros:
        nombre, parte = PARTES[i - 1]
        print(f"Parte {i}/{len(PARTES)}: {nombre}", flush=True)
        # deja todo apagado para que solo se vea lo de esta parte
        base_manual(st)
        st.enviar(*BASE_IZQ, 0)
        st.enviar(*BASE_DER, 0)
        apagar_todo(st)
        parte(st)
        apagar_todo(st)
        st.enviar(*BASE_IZQ, 0)
        st.enviar(*BASE_DER, 0)
    if len(PARTES) in numeros:
        base_manual(st, False)  # al terminar, la base vuelve a su show normal


# --------------------------------------------------------------------------
# Comandos
# --------------------------------------------------------------------------
def cmd_puertos():
    print("Entradas MIDI:")
    for i, n in enumerate(entradas()):
        print(f"  [{i}] {n}")
    print("Salidas MIDI:")
    for i, n in enumerate(salidas()):
        print(f"  [{i}] {n}")


def cmd_escuchar(minutos=10.0, eco=True):
    logs = Path(__file__).with_name("logs")
    logs.mkdir(exist_ok=True)
    parar = logs / "PARAR"
    parar.unlink(missing_ok=True)
    archivo = logs / time.strftime("escucha-%Y%m%d-%H%M%S.jsonl")
    vistos = {}
    jog_ultimo = {}
    jog_cuenta = {}
    fin = time.time() + minutos * 60

    with Starlight() as st, archivo.open("w", encoding="utf-8") as f:
        saludo(st)
        st.enviar(0xB0, 0x7F, 0x7F)  # pide la posición actual de perillas y faders
        print(f"Escuchando hasta {minutos:g} min. Toca todo. Ctrl+C o crea {parar} para terminar.")
        print(f"Registro: {archivo}", flush=True)
        try:
            while time.time() < fin and not parar.exists():
                try:
                    t, s, d1, d2 = st.cola.get(timeout=0.2)
                except queue.Empty:
                    continue
                desc = describir(s, d1, d2)
                f.write(json.dumps({"t": t, "st": s, "d1": d1, "d2": d2, "desc": desc},
                                   ensure_ascii=False) + "\n")
                f.flush()
                clave = (s, d1)
                vistos.setdefault(clave, [desc, 0, d2, d2])
                v = vistos[clave]
                v[1] += 1
                v[2], v[3] = min(v[2], d2), max(v[3], d2)

                # eco: si es un botón, prende su LED mientras lo presionas
                if eco and (s & 0xF0) in (0x80, 0x90) and not (s == 0x90 and d1 == 0x03):
                    st.enviar(s | 0x10 if (s & 0xF0) == 0x80 else s, d1,
                              0x7F if (s & 0xF0) == 0x90 and d2 else 0)

                # los jogs mandan muchísimos mensajes: los resumo cada 0.25 s
                if (s & 0xF0) == 0xB0 and d1 in JOGS:
                    paso = 1 if d2 < 0x40 else -1
                    jog_cuenta[clave] = jog_cuenta.get(clave, 0) + paso
                    if time.time() - jog_ultimo.get(clave, 0) < 0.25:
                        continue
                    jog_ultimo[clave] = time.time()
                    total = jog_cuenta.pop(clave)
                    sentido = "horario" if total > 0 else "antihorario"
                    print(f"{t:9.3f}  {_hex(s, d1, d2)}  {desc}: {abs(total)} pasos {sentido}",
                          flush=True)
                    continue
                print(f"{t:9.3f}  {_hex(s, d1, d2)}  {desc}", flush=True)
        except KeyboardInterrupt:
            pass
        finally:
            apagar_todo(st)
            base_manual(st, False)
            parar.unlink(missing_ok=True)

    print(f"\nResumen: {len(vistos)} controles distintos")
    for (s, d1), (desc, n, lo, hi) in sorted(vistos.items()):
        print(f"  {s:02X} {d1:02X}  x{n:<5} rango {lo:3}-{hi:3}  {desc}")
    print(f"Registro completo: {archivo}")


def cmd_luces(resto):
    with Starlight(entrada=False) as st:
        demo_luces(st, [int(x) for x in resto])


def cmd_enviar(args):
    if len(args) not in (2, 3):
        sys.exit("Uso: python starlight.py enviar STATUS DATA1 [DATA2]   (hex, ej. 91 07 7F)")
    st_, d1, *d2 = (int(a, 16) for a in args)
    with Starlight(entrada=False) as st:
        st.enviar(st_, d1, d2[0] if d2 else 0)
    print(f"Enviado: {_hex(st_, d1, d2[0] if d2 else 0)}")


def cmd_reset():
    with Starlight(entrada=False) as st:
        apagar_todo(st)
        base_manual(st, False)
    print("Luces apagadas y base en modo automático.")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:] or ["puertos"]
    cmd, resto = args[0], args[1:]
    try:
        if cmd == "puertos":
            cmd_puertos()
        elif cmd == "escuchar":
            cmd_escuchar(float(resto[0]) if resto else 10.0)
        elif cmd == "luces":
            cmd_luces(resto)
        elif cmd == "enviar":
            cmd_enviar(resto)
        elif cmd == "reset":
            cmd_reset()
        else:
            print(__doc__)
    except MidiError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
