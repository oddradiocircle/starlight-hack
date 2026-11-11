"""Navegar: los jogs desplazan la pantalla, vertical y horizontal, incluso a la vez."""
from starlight.perfiles import control

nombre = "Navegar"
descripcion = ("Jog A: arriba y abajo · Jog B: izquierda y derecha (a la vez se mueve en diagonal) · "
               "Girar tocando el jog por arriba: más rápido · Shift + Jog A: zoom · Tempo A y B: velocidad")
color = ("verde", "fijo")

PASOS_POR_MUESCA = 3   # cuántos pasos del jog equivalen a una muesca de la rueda del mouse
RAPIDO = 3             # girar tocando el jog por arriba multiplica la velocidad


def al_entrar(s):
    s.estado.update(velocidad={"A": 1.0, "B": 1.0})


def _cuanto(e, s, deck):
    rapido = RAPIDO if e.extra.get("superficie") == "arriba" else 1
    return e.pasos * s.estado["velocidad"][deck] * rapido / PASOS_POR_MUESCA


@control("A.jog")
def vertical(e, s):
    """Desplaza arriba y abajo; con Shift, zoom."""
    if e.shift:
        s.sistema.zoom(_cuanto(e, s, "A"))
    else:
        s.sistema.rueda(-_cuanto(e, s, "A"))   # girar a la derecha baja la página


@control("B.jog")
def horizontal(e, s):
    """Desplaza a los lados."""
    s.sistema.rueda(_cuanto(e, s, "B"), horizontal=True)   # girar a la derecha va a la derecha


@control("A.tempo")
def velocidad_a(e, s):
    """Velocidad del Jog A."""
    s.estado["velocidad"]["A"] = 0.25 + e.valor * 3.75   # de un cuarto a 4 veces


@control("B.tempo")
def velocidad_b(e, s):
    """Velocidad del Jog B."""
    s.estado["velocidad"]["B"] = 0.25 + e.valor * 3.75
