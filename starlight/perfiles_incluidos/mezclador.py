"""Mezclador: una perilla por app, como en una consola de DJ."""
import threading
import time

from starlight.perfiles import control

nombre = "Mezclador"
descripcion = ("Volume A: Spotify · Volume B: Chrome · Crossfader: reparte entre los dos · PFL: silencia · "
               "La base muestra el volumen de cada uno")
color = ("verde", "fijo")
usa_base = True  # la base muestra el volumen: la página no deja cambiarla mientras tanto

# Cada deck maneja una app: (nombre, proceso, color en la base). Cambia el proceso por el de otra app:
# «msedge», «firefox», «discord», «vlc»… (el nombre del .exe, sin .exe).
APPS = {
    "A": ("Spotify", "spotify", (30, 215, 96)),
    "B": ("Chrome", "chrome", (66, 133, 244)),
}
SILENCIO = (90, 0, 0)  # color de la base cuando la app está silenciada
CADA = 0.05            # aplica los cambios 20 veces por segundo, desde un solo hilo
REVISAR = 2.0          # cada 2 s vuelve a aplicar, por si la app empezó a sonar después


def al_entrar(s):
    s.estado.update(perilla={"A": None, "B": None}, cruce=0.5, mudo={"A": False, "B": False},
                    aplicado={"A": None, "B": None}, original={}, revision=0.0,
                    candado=threading.Lock(), saliendo=False)
    s.cada(CADA, aplicar)


def al_salir(s):
    """Cada app vuelve al volumen que tenía antes de activar el perfil."""
    e = s.estado
    with e["candado"]:
        e["saliendo"] = True
        for deck, valor in e["original"].items():
            try:
                s.sistema.volumen_app(APPS[deck][1], valor)
            except s.sistema.AccionNoDisponible:
                pass


def _ganancia(deck, cruce):
    """Crossfader: en el centro las dos suenan completas; hacia un lado, la otra baja hasta cero."""
    return min(1.0, 2 * (1 - cruce)) if deck == "A" else min(1.0, 2 * cruce)


def _volumen(e, deck):
    if e["perilla"][deck] is None:
        return None  # aún no sabemos dónde está la perilla: no se toca la app
    if e["mudo"][deck]:
        return 0.0
    return e["perilla"][deck] * _ganancia(deck, e["cruce"])


def aplicar(s):
    e = s.estado
    with e["candado"]:
        if e["saliendo"]:
            return
        ahora = time.time()
        revisar = ahora - e["revision"] > REVISAR
        if revisar:
            e["revision"] = ahora
        for deck, (_, proceso, rgb) in APPS.items():
            v = _volumen(e, deck)
            if v is None:
                continue
            if revisar or v != e["aplicado"][deck]:
                try:
                    if deck not in e["original"]:
                        actual = s.sistema.volumen_app_actual(proceso)
                        if actual is not None:
                            e["original"][deck] = actual
                    s.sistema.volumen_app(proceso, v)
                except s.sistema.AccionNoDisponible:
                    pass  # la app no está sonando: se aplica cuando empiece
                e["aplicado"][deck] = v
            luz = SILENCIO if e["mudo"][deck] else tuple(round(c * v) for c in rgb)
            s.base_rgb(*luz, lado="izq" if deck == "A" else "der", rapido=True)


def _silenciar(s, deck):
    m = s.estado["mudo"]
    m[deck] = not m[deck]
    s.luz(f"{deck}.pfl", m[deck])


@control("A.volumen")
def volumen_a(e, s):
    """Volumen de Spotify."""
    s.estado["perilla"]["A"] = e.valor


@control("B.volumen")
def volumen_b(e, s):
    """Volumen de Chrome."""
    s.estado["perilla"]["B"] = e.valor


@control("crossfader")
def cruce(e, s):
    """Reparte entre Spotify (izquierda) y Chrome (derecha)."""
    s.estado["cruce"] = e.valor


@control("A.pfl", al="presionar")
def silenciar_a(e, s):
    """Silencia Spotify o le devuelve el sonido."""
    _silenciar(s, "A")


@control("B.pfl", al="presionar")
def silenciar_b(e, s):
    """Silencia Chrome o le devuelve el sonido."""
    _silenciar(s, "B")
