"""Backend MIDI con python-rtmidi (macOS, Linux y también Windows)."""
import queue
import threading

import rtmidi

from . import MidiError, buscar


def puertos():
    return rtmidi.MidiIn().get_ports(), rtmidi.MidiOut().get_ports()


class Puerto:
    def __init__(self, texto="Starlight"):
        self.cola = queue.Queue()
        self.sysex = queue.Queue()
        self._turno = threading.Lock()  # un solo envío a la vez
        self._in, self._out = rtmidi.MidiIn(), rtmidi.MidiOut()
        try:
            i_in = buscar(self._in.get_ports(), texto)
            i_out = buscar(self._out.get_ports(), texto)
            self.nombre = self._in.get_ports()[i_in]
            self._in.open_port(i_in)
            self._out.open_port(i_out)
        except rtmidi.SystemError as e:
            self.cerrar()
            raise MidiError(f"No pude abrir la Starlight: {e}. ¿Otro programa la tiene abierta?") from e
        self._in.ignore_types(sysex=False, timing=True, active_sense=True)
        self._in.set_callback(self._callback)

    def _callback(self, evento, _datos=None):
        msg, _delta = evento
        if msg and msg[0] == 0xF0:
            self.sysex.put(bytes(msg))
        elif len(msg) >= 2:
            self.cola.put((msg[0], msg[1], msg[2] if len(msg) > 2 else 0))

    def enviar(self, st, d1, d2=0):
        try:
            with self._turno:
                self._out.send_message([st & 0xFF, d1 & 0x7F, d2 & 0x7F])
        except Exception as e:  # rtmidi lanza tipos distintos según el sistema
            raise MidiError(f"No pude enviar a la Starlight: {e}") from e

    def enviar_sysex(self, datos: bytes):
        try:
            with self._turno:
                self._out.send_message(list(datos))
        except Exception as e:
            raise MidiError(f"No pude enviar a la Starlight: {e}") from e

    def cerrar(self):
        for p in (getattr(self, "_in", None), getattr(self, "_out", None)):
            if p is not None:
                try:
                    p.close_port()
                except Exception:
                    pass
