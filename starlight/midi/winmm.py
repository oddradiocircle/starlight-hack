"""Backend MIDI para Windows con winmm.dll (sin dependencias)."""
import ctypes
import ctypes.wintypes as wt
import queue
import threading
import time

from . import MidiError, buscar

_winmm = ctypes.WinDLL("winmm")


class _MIDIINCAPSW(ctypes.Structure):
    _fields_ = [("wMid", wt.WORD), ("wPid", wt.WORD), ("vDriverVersion", wt.UINT),
                ("szPname", wt.WCHAR * 32), ("dwSupport", wt.DWORD)]


class _MIDIOUTCAPSW(ctypes.Structure):
    _fields_ = [("wMid", wt.WORD), ("wPid", wt.WORD), ("vDriverVersion", wt.UINT),
                ("szPname", wt.WCHAR * 32), ("wTechnology", wt.WORD), ("wVoices", wt.WORD),
                ("wNotes", wt.WORD), ("wChannelMask", wt.WORD), ("dwSupport", wt.DWORD)]


_MidiInProc = ctypes.WINFUNCTYPE(None, wt.HANDLE, wt.UINT, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t)
_HP = ctypes.POINTER(wt.HANDLE)
for _nombre, _args in {
    "midiInGetNumDevs": [], "midiOutGetNumDevs": [],
    "midiInGetDevCapsW": [ctypes.c_size_t, ctypes.c_void_p, wt.UINT],
    "midiOutGetDevCapsW": [ctypes.c_size_t, ctypes.c_void_p, wt.UINT],
    "midiInOpen": [_HP, wt.UINT, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD],
    "midiOutOpen": [_HP, wt.UINT, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD],
    "midiInStart": [wt.HANDLE], "midiInStop": [wt.HANDLE], "midiInReset": [wt.HANDLE],
    "midiInClose": [wt.HANDLE], "midiOutClose": [wt.HANDLE],
    "midiOutShortMsg": [wt.HANDLE, wt.DWORD],
    "midiInGetErrorTextW": [wt.UINT, wt.LPWSTR, wt.UINT],
    "midiOutGetErrorTextW": [wt.UINT, wt.LPWSTR, wt.UINT],
}.items():
    _f = getattr(_winmm, _nombre)
    _f.argtypes = _args
    _f.restype = wt.UINT

class _MIDIHDR(ctypes.Structure):
    _fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", wt.DWORD), ("dwBytesRecorded", wt.DWORD),
                ("dwUser", ctypes.c_size_t), ("dwFlags", wt.DWORD), ("lpNext", ctypes.c_void_p),
                ("reserved", ctypes.c_size_t), ("dwOffset", wt.DWORD), ("dwReserved", ctypes.c_size_t * 8)]


for _nombre in ("midiOutPrepareHeader", "midiOutUnprepareHeader", "midiOutLongMsg",
               "midiInPrepareHeader", "midiInUnprepareHeader", "midiInAddBuffer"):
    _f = getattr(_winmm, _nombre)
    _f.argtypes = [wt.HANDLE, ctypes.POINTER(_MIDIHDR), wt.UINT]
    _f.restype = wt.UINT

_MHDR_DONE = 0x1
_CALLBACK_FUNCTION = 0x00030000
_MIM_DATA = 0x3C3
_MIM_LONGDATA = 0x3C4
_BUFERES_SYSEX, _TAM_SYSEX = 4, 1024
_MMSYSERR_ALLOCATED = 4


def _check(res, salida=False):
    if res:
        buf = ctypes.create_unicode_buffer(256)
        (_winmm.midiOutGetErrorTextW if salida else _winmm.midiInGetErrorTextW)(res, buf, 256)
        msg = f"Error MIDI de Windows {res}: {buf.value}"
        if res == _MMSYSERR_ALLOCATED:
            msg = ("Otro programa tiene abierta la Starlight (Mixxx, Serato, DJUCED, Bome…). "
                   "Ciérralo y vuelve a intentar.")
        raise MidiError(msg)


def puertos():
    entradas, salidas = [], []
    for i in range(_winmm.midiInGetNumDevs()):
        c = _MIDIINCAPSW()
        if not _winmm.midiInGetDevCapsW(i, ctypes.byref(c), ctypes.sizeof(c)):
            entradas.append(c.szPname)
    for i in range(_winmm.midiOutGetNumDevs()):
        c = _MIDIOUTCAPSW()
        if not _winmm.midiOutGetDevCapsW(i, ctypes.byref(c), ctypes.sizeof(c)):
            salidas.append(c.szPname)
    return entradas, salidas


class Puerto:
    def __init__(self, texto="Starlight"):
        self.cola = queue.Queue()
        self.sysex = queue.Queue()    # SysEx recibidos (bytes completos F0 … F7)
        self._reponer = queue.Queue()
        self._bufs = []
        self._cerrando = False
        # Un solo envío a la vez: varios hilos mandando por la misma conexión trabaron el servicio MIDI de Windows.
        self._turno = threading.Lock()
        self._pendientes = []  # SysEx que el driver no terminó: su memoria debe seguir viva
        self._hin, self._hout = wt.HANDLE(), wt.HANDLE()
        self._cb = _MidiInProc(self._callback)  # referencia viva para el recolector
        entradas, salidas = puertos()
        i_out, i_in = buscar(salidas, texto), buscar(entradas, texto)
        self.nombre = entradas[i_in]
        _check(_winmm.midiOutOpen(ctypes.byref(self._hout), i_out, None, 0, 0), True)
        try:
            _check(_winmm.midiInOpen(ctypes.byref(self._hin), i_in, ctypes.cast(self._cb, ctypes.c_void_p),
                                     0, _CALLBACK_FUNCTION))
            tam = ctypes.sizeof(_MIDIHDR)
            for i in range(_BUFERES_SYSEX):  # búferes que Windows llena con los SysEx que llegan
                buf = ctypes.create_string_buffer(_TAM_SYSEX)
                hdr = _MIDIHDR(lpData=ctypes.cast(buf, ctypes.c_void_p), dwBufferLength=_TAM_SYSEX, dwUser=i)
                _check(_winmm.midiInPrepareHeader(self._hin, ctypes.byref(hdr), tam))
                _check(_winmm.midiInAddBuffer(self._hin, ctypes.byref(hdr), tam))
                self._bufs.append((hdr, buf))
            threading.Thread(target=self._devolver_bufs, daemon=True, name="sysex-in").start()
            _check(_winmm.midiInStart(self._hin))
        except MidiError:
            _winmm.midiOutClose(self._hout)
            raise

    def _callback(self, _h, msg, _inst, p1, _p2):
        if msg == _MIM_DATA:
            self.cola.put((p1 & 0xFF, (p1 >> 8) & 0x7F, (p1 >> 16) & 0x7F))
        elif msg == _MIM_LONGDATA:
            hdr = ctypes.cast(p1, ctypes.POINTER(_MIDIHDR)).contents
            if hdr.dwBytesRecorded:
                self.sysex.put(ctypes.string_at(hdr.lpData, hdr.dwBytesRecorded))
            self._reponer.put(hdr.dwUser)  # Windows no deja devolver el búfer desde aquí

    def _devolver_bufs(self):
        tam = ctypes.sizeof(_MIDIHDR)
        while True:
            i = self._reponer.get()
            if self._cerrando or i is None:
                break
            hdr, _buf = self._bufs[i]
            hdr.dwBytesRecorded = 0
            _winmm.midiInAddBuffer(self._hin, ctypes.byref(hdr), tam)

    def enviar(self, st, d1, d2=0):
        with self._turno:
            _check(_winmm.midiOutShortMsg(self._hout, (st & 0xFF) | ((d1 & 0x7F) << 8) | ((d2 & 0x7F) << 16)), True)

    def enviar_sysex(self, datos: bytes):
        """Envía un mensaje SysEx completo (F0 … F7)."""
        buf = ctypes.create_string_buffer(bytes(datos), len(datos))
        hdr = _MIDIHDR(lpData=ctypes.cast(buf, ctypes.c_void_p), dwBufferLength=len(datos))
        tam = ctypes.sizeof(hdr)
        with self._turno:
            self._limpiar_pendientes(tam)
            _check(_winmm.midiOutPrepareHeader(self._hout, ctypes.byref(hdr), tam), True)
            _check(_winmm.midiOutLongMsg(self._hout, ctypes.byref(hdr), tam), True)
            for _ in range(1000):  # espera a que el driver lo termine de enviar (máx. ~2 s)
                if hdr.dwFlags & _MHDR_DONE:
                    break
                time.sleep(0.002)
            if hdr.dwFlags & _MHDR_DONE:
                _winmm.midiOutUnprepareHeader(self._hout, ctypes.byref(hdr), tam)
            else:
                self._pendientes.append((hdr, buf))  # no se libera hasta que el driver lo suelte
                raise MidiError("La Starlight no terminó de recibir un mensaje SysEx.")

    def _limpiar_pendientes(self, tam):
        for hdr, buf in list(self._pendientes):
            if hdr.dwFlags & _MHDR_DONE:
                _winmm.midiOutUnprepareHeader(self._hout, ctypes.byref(hdr), tam)
                self._pendientes.remove((hdr, buf))

    def cerrar(self):
        if self._hin:
            self._cerrando = True
            _winmm.midiInStop(self._hin)
            _winmm.midiInReset(self._hin)  # devuelve los búferes de SysEx
            tam = ctypes.sizeof(_MIDIHDR)
            for hdr, _buf in self._bufs:
                _winmm.midiInUnprepareHeader(self._hin, ctypes.byref(hdr), tam)
            self._reponer.put(None)
            _winmm.midiInClose(self._hin)
            self._hin = wt.HANDLE()
        if self._hout:
            _winmm.midiOutClose(self._hout)
            self._hout = wt.HANDLE()
