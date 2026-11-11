"""Capa MIDI. Elige el backend según el sistema:

- Windows: winmm (API nativa, sin dependencias).
- macOS y Linux: python-rtmidi (pip install python-rtmidi).

Se puede forzar con la variable de entorno STARLIGHT_MIDI=winmm|rtmidi.

Todo backend expone:
    Puerto(texto)  abre entrada y salida cuyo nombre contiene `texto`
      .nombre      nombre del puerto
      .cola        queue.Queue con tuplas (status, data1, data2)
      .enviar(st, d1, d2)
      .cerrar()
    puertos() -> (entradas, salidas)
"""
import os
import sys


class MidiError(RuntimeError):
    pass


def nombre_backend() -> str:
    return os.environ.get("STARLIGHT_MIDI") or ("winmm" if sys.platform == "win32" else "rtmidi")


def _backend():
    nombre = nombre_backend()
    if nombre == "winmm":
        from . import winmm as modulo
    elif nombre == "rtmidi":
        try:
            from . import rt as modulo
        except ImportError as e:
            raise MidiError("Falta python-rtmidi. Instálalo con: pip install python-rtmidi") from e
    else:
        raise MidiError(f"Backend MIDI desconocido: {nombre}. Usa winmm o rtmidi.")
    return modulo


def abrir(texto: str = "Starlight"):
    return _backend().Puerto(texto)


def puertos():
    return _backend().puertos()


def buscar(nombres, texto):
    for i, n in enumerate(nombres):
        if texto.lower() in n.lower():
            return i
    raise MidiError(f"No encontré un puerto MIDI que contenga «{texto}».")
