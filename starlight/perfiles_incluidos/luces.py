"""Luces: la base sigue lo que suena en el computador, con muchos colores y fades suaves."""
import colorsys
import time

from starlight.perfiles import control

nombre = "Luces"
descripcion = ("La base sigue lo que suena, a todo color · Bass A: sensibilidad · Bass B: modo (ritmo, giro, noche, semáforo, hielo) · "
               "Volume A: suavidad · Volume B: separación de color")
color = ("morado", "fijo")
usa_base = True  # la página no deja cambiar la base mientras este perfil la maneja

# Gamas fijas: colores (R, G, B) de lo más suave a lo más fuerte.
GAMAS = {
    "noche": [(0, 0, 40), (40, 0, 255), (255, 0, 120), (255, 60, 0)],
    "semaforo": [(0, 30, 0), (0, 255, 60), (255, 240, 0), (255, 0, 0)],
    "hielo": [(0, 20, 50), (0, 200, 255), (200, 255, 255), (255, 255, 255)],
}
MODOS = ["ritmo", "giro", "noche", "semaforo", "hielo"]
FPS = 60              # con el SysEx de color completo (128 niveles por canal) ya no hace falta alternar tonos
PISO = 0.3            # brillo mínimo: así el color se sigue viendo en las partes suaves


def al_entrar(s):
    s.estado.update(nivel=[0.0, 0.0], promedio=0.05, ultimo_golpe=0.0, tono=0.0, separacion=0.5,
                    ganancia=1.8, modo="ritmo", caida=0.05)
    s.cada(1 / FPS, pulso)


def _mezclar(gama, x):
    x = max(0.0, min(1.0, x)) * (len(gama) - 1)
    i = min(int(x), len(gama) - 2)
    t = x - i
    return [a + (b - a) * t for a, b in zip(gama[i], gama[i + 1])]


def _golpe(e, pico):
    """Un golpe es un pico claramente por encima del promedio reciente."""
    e["promedio"] += (pico - e["promedio"]) * 0.01
    ahora = time.time()
    if pico > 0.06 and pico > e["promedio"] * 1.45 and ahora - e["ultimo_golpe"] > 0.18:
        e["ultimo_golpe"] = ahora
        return True
    return False


def pulso(s):
    e = s.estado
    picos = s.sistema.nivel()
    pico = max(picos)
    if _golpe(e, pico) and e["modo"] == "ritmo":
        e["tono"] = (e["tono"] + 0.085) % 1      # cada golpe avanza el tono un poco más de 30 grados
    deriva = 0.10 if e["modo"] == "giro" else 0.012
    e["tono"] = (e["tono"] + deriva / FPS) % 1   # entre golpes, el color sigue girando despacio
    for i, lado in enumerate(("izq", "der")):
        objetivo = min(1.0, picos[i] * e["ganancia"])
        actual = e["nivel"][i]
        rapidez = 0.35 if objetivo > actual else e["caida"]   # sube rápido, baja en fade
        actual += (objetivo - actual) * rapidez * (30 / FPS)
        e["nivel"][i] = actual
        if e["modo"] in GAMAS:
            rgb = _mezclar(GAMAS[e["modo"]], actual)
        else:
            tono = (e["tono"] + (e["separacion"] * 0.5 if i else 0)) % 1
            brillo = PISO + (1 - PISO) * actual
            rgb = [c * 255 for c in colorsys.hsv_to_rgb(tono, 1.0, brillo)]
        s.base_rgb(*(round(c) for c in rgb), lado=lado, rapido=True)


@control("A.eq")
def sensibilidad(e, s):
    """Sensibilidad al ritmo."""
    s.estado["ganancia"] = 0.5 + e.valor * 3


@control("B.eq")
def modo(e, s):
    """Elige el efecto: ritmo, giro, noche, semáforo o hielo."""
    s.estado["modo"] = MODOS[min(len(MODOS) - 1, int(e.valor * len(MODOS)))]


@control("A.volumen")
def suavidad(e, s):
    """Suavidad de la caída."""
    s.estado["caida"] = 0.2 - e.valor * 0.19   # abajo: caída rápida · arriba: muy lenta


@control("B.volumen")
def separacion(e, s):
    """Separación de color entre los lados."""
    s.estado["separacion"] = e.valor            # 0: los dos lados iguales · 1: colores opuestos

