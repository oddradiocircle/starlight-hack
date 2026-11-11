"""Mi perfil: describe aquí en una línea qué hace."""
from starlight.perfiles import control

nombre = "Mi perfil"
descripcion = "Qué hace cada control, en una línea."
color = ("verde", "fijo")  # color de la base al activarlo: 1-12 o nombre, y fijo, parpadeo o respira


def al_entrar(s):
    """Se llama al activar el perfil: prende las luces de lo que usas."""
    s.luz("A.play")


def al_salir(s):
    """Se llama al salir. Las luces que prendiste con s.luz() se apagan solas."""


@control("A.play", al="presionar")
def play(e, s):
    # e.control, e.valor, e.presionado, e.pasos (jogs), e.shift, e.modo (pads)
    # s.sistema: teclas(), multimedia(), rueda(), abrir(), volumen(), volumen_app(), nivel()
    # s.base("rojo", "respira"), s.base_rgb(255, 0, 128), s.luz("B.cue"), s.cada(segundos, funcion)
    s.sistema.multimedia("play_pausa")


@control("B.jog")
def jog(e, s):
    s.sistema.rueda(-e.pasos / 3)
