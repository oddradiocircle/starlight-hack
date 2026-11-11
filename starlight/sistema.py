"""Acciones del computador para los perfiles.

Windows: completo (teclas, multimedia, rueda, volumen general y por app, medidor de nivel).
macOS y Linux: lo básico (atajos, volumen, abrir; multimedia con playerctl en Linux). Sin probar.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import webbrowser

WIN, MAC = sys.platform == "win32", sys.platform == "darwin"


class AccionNoDisponible(RuntimeError):
    pass


# ----------------------------------------------------------------------------- teclas (Windows)
_VK = {"ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "tab": 0x09, "enter": 0x0D,
       "esc": 0x1B, "espacio": 0x20, "space": 0x20, "arriba": 0x26, "abajo": 0x28, "izquierda": 0x25,
       "derecha": 0x27, "inicio": 0x24, "fin": 0x23, "supr": 0x2E, "borrar": 0x08, "rePag": 0x21, "avPag": 0x22,
       **{f"f{i}": 0x6F + i for i in range(1, 13)}}
_EXTENDIDAS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2E, 0x5B}
MULTIMEDIA = {"play_pausa": 0xB3, "siguiente": 0xB0, "anterior": 0xB1, "detener": 0xB2,
              "silencio": 0xAD, "bajar": 0xAE, "subir": 0xAF}


def _vk(nombre: str) -> int:
    n = nombre.lower()
    if n in _VK:
        return _VK[n]
    if len(n) == 1 and n.isalnum():
        return ord(n.upper())
    raise ValueError(f"Tecla desconocida: {nombre}")


def _tecla(vk: int, soltar: bool):
    flags = (0x0002 if soltar else 0) | (0x0001 if vk in _EXTENDIDAS or vk in MULTIMEDIA.values() else 0)
    import ctypes
    ctypes.windll.user32.keybd_event(vk, 0, flags, 0)


def teclas(*combinacion: str):
    """Pulsa un atajo: teclas("win", "shift", "s"), teclas("ctrl", "c")."""
    if WIN:
        vks = [_vk(t) for t in combinacion]
        for vk in vks:
            _tecla(vk, False)
        for vk in reversed(vks):
            _tecla(vk, True)
    elif MAC:
        mods = {"ctrl": "control down", "control": "control down", "shift": "shift down",
                "alt": "option down", "cmd": "command down", "win": "command down"}
        tecla = [t for t in combinacion if t.lower() not in mods]
        usando = ", ".join(mods[t.lower()] for t in combinacion if t.lower() in mods)
        guion = f'tell application "System Events" to keystroke "{tecla[0] if tecla else ""}"'
        subprocess.run(["osascript", "-e", guion + (f" using {{{usando}}}" if usando else "")], check=False)
    else:
        _linux(["xdotool", "key", "+".join("super" if t == "win" else t for t in combinacion)])


def multimedia(accion: str):
    """play_pausa, siguiente, anterior, detener, silencio, subir, bajar."""
    if accion not in MULTIMEDIA:
        raise ValueError(f"Acción multimedia desconocida: {accion}. Opciones: {', '.join(MULTIMEDIA)}")
    if WIN:
        _tecla(MULTIMEDIA[accion], False)
        _tecla(MULTIMEDIA[accion], True)
    elif not MAC:
        orden = {"play_pausa": "play-pause", "siguiente": "next", "anterior": "previous", "detener": "stop"}
        if accion in orden:
            return _linux(["playerctl", orden[accion]])
        return volumen_cambiar({"subir": .05, "bajar": -.05}.get(accion, 0)) if accion != "silencio" else None
    else:
        raise AccionNoDisponible("Las teclas multimedia todavía no están hechas para macOS.")


def rueda(pasos: float, horizontal: bool = False):
    """Gira la rueda del mouse. Positivo = hacia arriba (o a la derecha)."""
    if WIN:
        import ctypes
        ctypes.windll.user32.mouse_event(0x01000 if horizontal else 0x0800, 0, 0, int(pasos * 120) & 0xFFFFFFFF, 0)
    elif not MAC:
        boton = ("6" if pasos < 0 else "7") if horizontal else ("5" if pasos < 0 else "4")
        _linux(["xdotool", "click", "--repeat", str(max(1, int(abs(pasos)))), boton])
    else:
        raise AccionNoDisponible("La rueda del mouse todavía no está hecha para macOS.")


def escribir(texto: str):
    """Escribe texto en la ventana activa, como si lo tecleara. «\\n» es Enter."""
    if WIN:
        import ctypes
        import ctypes.wintypes as wt

        class KI(ctypes.Structure):
            _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                        ("dwExtraInfo", ctypes.c_size_t)]

        class INPUT(ctypes.Structure):
            class _U(ctypes.Union):
                _fields_ = [("ki", KI), ("relleno", ctypes.c_byte * 32)]
            _anonymous_ = ("u",)
            _fields_ = [("type", wt.DWORD), ("u", _U)]

        for ch in texto:
            if ch == "\n":
                teclas("enter")
                continue
            for flags in (0x0004, 0x0004 | 0x0002):  # KEYEVENTF_UNICODE, y luego soltar
                inp = INPUT(type=1)
                inp.ki = KI(0, ord(ch), flags, 0, 0)
                ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
    elif MAC:
        for parte in texto.split("\n"):
            if parte:
                subprocess.run(["osascript", "-e", f'tell application "System Events" to keystroke {json_str(parte)}'],
                               check=False)
        if texto.endswith("\n"):
            subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 36'], check=False)
    else:
        _linux(["xdotool", "type", "--", texto])


def json_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def zoom(pasos: float):
    """Acerca (positivo) o aleja: Ctrl + rueda del mouse."""
    if WIN:
        _tecla(_VK["ctrl"], False)
        try:
            rueda(pasos)
        finally:
            _tecla(_VK["ctrl"], True)
    elif MAC:
        teclas("cmd", "=" if pasos > 0 else "-")
    else:
        _linux(["xdotool", "key", "ctrl+plus" if pasos > 0 else "ctrl+minus"])


def abrir(cosa: str):
    """Abre un programa, archivo, carpeta o página web."""
    if cosa.startswith(("http://", "https://")):
        webbrowser.open(cosa)
    elif WIN:
        os.startfile(cosa)  # noqa: S606 - lo pide el perfil del usuario
    else:
        subprocess.Popen(["open" if MAC else "xdg-open", cosa])


def _linux(cmd):
    try:
        subprocess.run(cmd, check=False)
    except FileNotFoundError as e:
        raise AccionNoDisponible(f"Falta el programa «{cmd[0]}». Instálalo para usar esta acción.") from e


# ----------------------------------------------------------------------------- audio (Windows, con pycaw)
_hilo = threading.local()


def _audio():
    """Objetos de audio de Windows, uno por hilo (COM lo exige)."""
    if not WIN:
        raise AccionNoDisponible("Esta acción de audio solo está hecha para Windows.")
    if getattr(_hilo, "listo", False):
        return _hilo
    try:
        import comtypes
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    except ImportError as e:
        raise AccionNoDisponible("Falta pycaw. Instálalo con: pip install pycaw") from e
    import warnings

    warnings.filterwarnings("ignore", module="pycaw")
    comtypes.CoInitialize()
    salida = AudioUtilities.GetSpeakers()
    dev = getattr(salida, "_dev", salida)
    _hilo.volumen = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None).QueryInterface(IAudioEndpointVolume)
    _hilo.medidor = dev.Activate(_IMedidor._iid_, CLSCTX_ALL, None).QueryInterface(_IMedidor)
    _hilo.AudioUtilities = AudioUtilities
    _hilo.listo = True
    return _hilo


if WIN:
    try:
        from ctypes import POINTER, c_float, c_uint, c_ulong

        from comtypes import COMMETHOD, GUID, HRESULT, IUnknown

        class _IMedidor(IUnknown):  # IAudioMeterInformation completa (pycaw solo trae el pico total)
            _iid_ = GUID("{C02216F6-8C67-4B5B-9D00-D008E73E0064}")
            _methods_ = [
                COMMETHOD([], HRESULT, "GetPeakValue", (["out"], POINTER(c_float), "pico")),
                COMMETHOD([], HRESULT, "GetMeteringChannelCount", (["out"], POINTER(c_uint), "canales")),
                COMMETHOD([], HRESULT, "GetChannelsPeakValues", (["in"], c_uint, "n"), (["in"], POINTER(c_float), "v")),
                COMMETHOD([], HRESULT, "QueryHardwareSupport", (["out"], POINTER(c_ulong), "mascara")),
            ]
    except ImportError:
        pass


def volumen(valor: float):
    """Volumen general del computador, de 0 a 1."""
    valor = min(1.0, max(0.0, float(valor)))
    if WIN:
        _audio().volumen.SetMasterVolumeLevelScalar(valor, None)
    elif MAC:
        subprocess.run(["osascript", "-e", f"set volume output volume {round(valor * 100)}"], check=False)
    else:
        _linux(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{round(valor * 100)}%"])


def volumen_actual() -> float:
    if WIN:
        return float(_audio().volumen.GetMasterVolumeLevelScalar())
    raise AccionNoDisponible("Leer el volumen solo está hecho para Windows.")


def volumen_cambiar(delta: float):
    volumen(volumen_actual() + delta)


def volumen_app(proceso: str, valor: float):
    """Volumen de una app que está sonando, de 0 a 1. proceso: «spotify», «chrome»…"""
    a = _audio()
    buscado = proceso.lower().removesuffix(".exe")
    hallada = False
    for s in a.AudioUtilities.GetAllSessions():
        if s.Process and s.Process.name().lower().removesuffix(".exe") == buscado:
            s.SimpleAudioVolume.SetMasterVolume(min(1.0, max(0.0, float(valor))), None)
            hallada = True
    if not hallada:
        raise AccionNoDisponible(f"«{proceso}» no está sonando ahora.")


def volumen_app_actual(proceso: str) -> float | None:
    """Volumen actual de una app, de 0 a 1, o None si no está sonando."""
    a = _audio()
    buscado = proceso.lower().removesuffix(".exe")
    for s in a.AudioUtilities.GetAllSessions():
        if s.Process and s.Process.name().lower().removesuffix(".exe") == buscado:
            return float(s.SimpleAudioVolume.GetMasterVolume())
    return None


def nivel() -> tuple[float, float]:
    """Pico de lo que suena ahora (izquierda, derecha), de 0 a 1. Lee el medidor de Windows: no graba nada."""
    a = _audio()
    from ctypes import c_float

    n = a.medidor.GetMeteringChannelCount()
    v = (c_float * n)()
    a.medidor.GetChannelsPeakValues(n, v)
    return (float(v[0]), float(v[1] if n > 1 else v[0]))


# ----------------------------------------------------------------------------- app al frente
_frente = (0.0, "")


def app_al_frente() -> str:
    """Nombre del programa de la ventana que tienes al frente, en minúsculas y sin .exe
    (chrome, spotify, wave, code…). Se recuerda 1/4 de segundo. Solo Windows; en otros, "".
    """
    global _frente
    import time

    ahora = time.monotonic()
    if ahora - _frente[0] < 0.25:
        return _frente[1]
    nombre = ""
    if WIN:
        import ctypes
        from ctypes import wintypes

        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        hwnd = u32.GetForegroundWindow()
        pid = wintypes.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = k32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if h:
            try:
                buf, largo = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
                if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(largo)):
                    nombre = os.path.basename(buf.value).lower().removesuffix(".exe")
            finally:
                k32.CloseHandle(h)
    _frente = (ahora, nombre)
    return nombre
