"""Escritorio: la Starlight como control del computador."""
from starlight.perfiles import control

nombre = "Escritorio"
descripcion = ("Play pausa la música · Cue y Sync: canción anterior y siguiente · Volume A: volumen de Windows · "
               "Jog B: desplazarse · Pads A: atajos")
color = ("celeste", "fijo")
leer_perillas = False  # si no, al activarlo el volumen de Windows saltaría a la posición de Volume A

# Pads del deck A en modo Hot Cue. Cambia los atajos a tu gusto.
ATAJOS = {
    1: ("Captura de pantalla", ("win", "shift", "s")),
    2: ("Silenciar el micrófono", ("win", "alt", "k")),
    3: ("Mostrar el escritorio", ("win", "d")),
    4: ("Vista de tareas", ("win", "tab")),
}


def al_entrar(s):
    s.aparato.modo_pads("A", "hotcue")
    for c in ("A.play", "A.cue", "A.sync"):
        s.luz(c)
    for n in ATAJOS:
        s.luz(f"A.pad{n}")


@control("A.play", al="presionar")
def play(e, s):
    """Play o pausa la música."""
    s.sistema.multimedia("play_pausa")


@control("A.cue", al="presionar")
def anterior(e, s):
    """Canción anterior."""
    s.sistema.multimedia("anterior")


@control("A.sync", al="presionar")
def siguiente(e, s):
    """Canción siguiente."""
    s.sistema.multimedia("siguiente")


@control("A.volumen")
def volumen(e, s):
    """Volumen de Windows."""
    s.sistema.volumen(e.valor)


@control("B.jog")
def desplazar(e, s):
    """Desplaza la página."""
    # girar a la derecha baja la página; un paso del jog es un tercio de muesca de la rueda
    s.sistema.rueda(-e.pasos / 3)


@control("A.pad*", al="presionar")
def atajo(e, s):
    """Atajos: captura, micrófono, escritorio y vista de tareas."""
    if e.modo == "hotcue" and not e.shift:
        s.sistema.teclas(*ATAJOS[int(e.control[-1])][1])
