"""Acciones del computador para los perfiles.

Windows: completo (teclas, multimedia, rueda, volumen general y por app, medidor de nivel).
macOS y Linux: lo básico (atajos, volumen, abrir; multimedia con playerctl en Linux). Sin probar.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
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
        import psutil
        from comtypes import CLSCTX_ALL, CLSCTX_INPROC_SERVER
        from pycaw.constants import CLSID_MMDeviceEnumerator
        from pycaw.pycaw import (IAudioEndpointVolume, IAudioSessionControl2, IAudioSessionManager2,
                                 IMMDeviceEnumerator, ISimpleAudioVolume)
    except ImportError as e:
        raise AccionNoDisponible("Falta pycaw. Instálalo con: pip install pycaw") from e
    import warnings

    warnings.filterwarnings("ignore", module="pycaw")
    comtypes.CoInitialize()
    _hilo.CLSCTX_ALL, _hilo.psutil = CLSCTX_ALL, psutil
    _hilo.IAudioEndpointVolume, _hilo.IAudioSessionManager2 = IAudioEndpointVolume, IAudioSessionManager2
    _hilo.IAudioSessionControl2, _hilo.ISimpleAudioVolume = IAudioSessionControl2, ISimpleAudioVolume
    # AudioUtilities.GetSpeakers() de pycaw tarda ~0,4 s: la salida se le pide directo a Windows (~15 ms)
    _hilo.enumerador = comtypes.CoCreateInstance(CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, CLSCTX_INPROC_SERVER)
    _hilo.nombres = {}
    _conectar_salida(_hilo, _hilo.enumerador.GetDefaultAudioEndpoint(0, 1))  # 0 = salida, 1 = multimedia
    _hilo.listo = True
    return _hilo


def _conectar_salida(a, dev):
    """Guarda los objetos de la salida de audio predeterminada: volumen, medidor y sesiones de las apps."""
    a.dev_id, a.revisado = dev.GetId(), time.time()
    a.volumen = dev.Activate(a.IAudioEndpointVolume._iid_, a.CLSCTX_ALL, None).QueryInterface(a.IAudioEndpointVolume)
    a.medidor = dev.Activate(_IMedidor._iid_, a.CLSCTX_ALL, None).QueryInterface(_IMedidor)
    a.sesiones = dev.Activate(a.IAudioSessionManager2._iid_, a.CLSCTX_ALL, None).QueryInterface(a.IAudioSessionManager2)


def _nombre_proceso(a, pid: int):
    if pid not in a.nombres:
        if len(a.nombres) > 500:
            a.nombres.clear()
        try:
            a.nombres[pid] = a.psutil.Process(pid).name().lower().removesuffix(".exe")
        except Exception:
            a.nombres[pid] = None
    return a.nombres[pid]


def _sesiones_app(proceso: str) -> list:
    """Controles de volumen de las sesiones de audio de una app. Tarda unos 2 ms
    (GetAllSessions de pycaw tarda ~0,4 s, y eso se sentía como un segundo de retraso en las perillas)."""
    a = _audio()
    ahora = time.time()
    if ahora - a.revisado > 2.0:  # ¿cambiaste la salida, por ejemplo a audífonos Bluetooth? entonces se sigue a la nueva
        a.revisado = ahora
        dev = a.enumerador.GetDefaultAudioEndpoint(0, 1)
        if dev.GetId() != a.dev_id:
            _conectar_salida(a, dev)
    buscado = proceso.lower().removesuffix(".exe")
    lista = a.sesiones.GetSessionEnumerator()
    hallados = []
    for i in range(lista.GetCount()):
        ctl = lista.GetSession(i)
        pid = ctl.QueryInterface(a.IAudioSessionControl2).GetProcessId()
        if pid and _nombre_proceso(a, pid) == buscado:
            hallados.append(ctl.QueryInterface(a.ISimpleAudioVolume))
    return hallados


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
    sesiones = _sesiones_app(proceso)
    if not sesiones:
        raise AccionNoDisponible(f"«{proceso}» no está sonando ahora.")
    for s in sesiones:
        s.SetMasterVolume(min(1.0, max(0.0, float(valor))), None)


def volumen_app_actual(proceso: str) -> float | None:
    """Volumen actual de una app, de 0 a 1, o None si no está sonando."""
    sesiones = _sesiones_app(proceso)
    return float(sesiones[0].GetMasterVolume()) if sesiones else None


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


def traer_al_frente(proceso: str) -> bool:
    """Trae al frente la ventana principal de un programa (por ejemplo «wave»). Solo Windows.

    Windows solo deja pasar al frente una ventana a quien recibió la última entrada del teclado o
    el mouse; el servidor recibe MIDI, no eso. Por eso se une un momento a la cola de entrada de la
    ventana que está al frente (AttachThreadInput), el truco habitual.
    """
    global _frente
    if not WIN:
        return False
    import ctypes
    from ctypes import wintypes

    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    proceso = proceso.lower().removesuffix(".exe")
    halladas = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cada(hwnd, _):
        if not u32.IsWindowVisible(hwnd) or u32.GetWindow(hwnd, 4) or not u32.GetWindowTextLengthW(hwnd):
            return True  # invisibles, con dueño (diálogos) o sin título: no son la ventana principal
        pid = wintypes.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = k32.OpenProcess(0x1000, False, pid.value)
        if h:
            try:
                buf, largo = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
                if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(largo)) and \
                        os.path.basename(buf.value).lower().removesuffix(".exe") == proceso:
                    halladas.append(hwnd)
                    return False
            finally:
                k32.CloseHandle(h)
        return True

    u32.EnumWindows(cada, 0)
    if not halladas:
        return False
    hwnd = halladas[0]
    if u32.IsIconic(hwnd):
        u32.ShowWindow(hwnd, 9)  # SW_RESTORE: estaba minimizada
    frente = u32.GetForegroundWindow()
    suyo = u32.GetWindowThreadProcessId(frente, None)
    mio = k32.GetCurrentThreadId()
    unido = bool(suyo and suyo != mio and u32.AttachThreadInput(mio, suyo, True))
    try:
        ok = bool(u32.SetForegroundWindow(hwnd))
        u32.BringWindowToTop(hwnd)
    finally:
        if unido:
            u32.AttachThreadInput(mio, suyo, False)
    _frente = (0.0, "")  # que app_al_frente vuelva a mirar
    return ok
