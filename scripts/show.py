"""Show de luces de unos 30 s para grabar un video de la Starlight.

Deja el aparato a oscuras con Play A titilando. Cuando presionas Play A, arranca el show. Al terminar,
devuelve el perfil, el brillo y el ritmo de los efectos como estaban.

Uso (con el servidor prendido):  python scripts/show.py
"""
import colorsys
import http.client
import json
import sys
import time

HOST, PUERTO = "127.0.0.1", 8765
FPS = 40
BPM = 128

PADS = [f"A.pad{i}" for i in range(1, 5)] + [f"B.pad{i}" for i in range(1, 5)]
BOTONES_A = ["A.play", "A.cue", "A.sync", "A.pfl"]
BOTONES_B = ["B.play", "B.cue", "B.sync", "B.pfl"]
TODAS = PADS + BOTONES_A + BOTONES_B + ["vinyl", "bassfilter"]


class API:
    def __init__(self):
        self.k = http.client.HTTPConnection(HOST, PUERTO, timeout=5)

    def _pedir(self, metodo, ruta, cuerpo=None):
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        for _ in range(2):
            try:
                self.k.request(metodo, ruta, body=datos, headers={"Content-Type": "application/json"})
                r = self.k.getresponse()
                texto = r.read().decode("utf-8", "replace")
                return json.loads(texto) if texto.strip() else {}
            except (http.client.HTTPException, OSError):
                self.k.close()
                self.k = http.client.HTTPConnection(HOST, PUERTO, timeout=5)
        raise RuntimeError(f"El servidor no respondió a {ruta}")

    def post(self, ruta, cuerpo):
        return self._pedir("POST", ruta, cuerpo)

    def get(self, ruta):
        return self._pedir("GET", ruta)

    # atajos
    def base(self, rgb, lado="ambos", efecto="fijo"):
        self.post("/api/base", {"rgb": [round(max(0, min(255, c))) for c in rgb], "lado": lado, "efecto": efecto})

    def color(self, nombre, efecto="fijo", lado="ambos"):
        self.post("/api/base", {"color": nombre, "efecto": efecto, "lado": lado})

    def luz(self, control, encendida=True, efecto="fijo"):
        self.post("/api/luz", {"control": control, "encendida": encendida, "efecto": efecto})


def hsv(h, s=1.0, v=1.0):
    return [c * 255 for c in colorsys.hsv_to_rgb(h % 1, s, v)]


def mezclar(a, b, t):
    return [x + (y - x) * t for x, y in zip(a, b)]


def cuadros(duracion):
    """Recorre la duración a FPS cuadros por segundo; entrega t de 0 a 1 y los segundos transcurridos."""
    inicio = time.time()
    while True:
        s = time.time() - inicio
        if s >= duracion:
            break
        yield s / duracion, s
        time.sleep(max(0.0, (1 / FPS) - ((time.time() - inicio) - s)))


def esperar_play():
    """Escucha los eventos en vivo y vuelve cuando presionas Play A."""
    k = http.client.HTTPConnection(HOST, PUERTO, timeout=600)
    k.request("GET", "/api/eventos")
    r = k.getresponse()
    while True:
        linea = r.readline()
        if not linea:
            raise RuntimeError("Se cortaron los eventos del servidor")
        if linea.startswith(b"data: "):
            try:
                d = json.loads(linea[6:])
            except ValueError:
                continue
            if d.get("tipo") == "control" and d.get("control") == "A.play" and d.get("valor", 0) > 0:
                k.close()
                return


def show(api):
    # 1. Despertar: de negro a azul profundo y a celeste
    api.luz("A.play", False)
    azul, celeste = [0, 20, 120], [16, 200, 255]
    for t, _ in cuadros(1.6):
        api.base(mezclar([0, 0, 0], azul, t * t))
    for t, _ in cuadros(1.0):
        api.base(mezclar(azul, celeste, t))

    # 2. Barrido: los pads de izquierda a derecha, dos pasadas; la base sigue la posición
    for pasada, duracion in ((0, 2.2), (1, 1.4)):
        anterior = None
        for t, _ in cuadros(duracion):
            i = min(7, int(t * 8))
            if i != anterior:
                if anterior is not None:
                    api.luz(PADS[anterior], False)
                api.luz(PADS[i], True)
                anterior = i
            tono = 0.55 + t * 0.35 + pasada * 0.2
            api.base(hsv(tono, v=1.0 if i < 4 else 0.25), "izq")
            api.base(hsv(tono, v=0.25 if i < 4 else 1.0), "der")
        api.luz(PADS[anterior], False)

    # 3. Ritmo: los botones de cada lado se alternan; los pads golpean cada 4 tiempos; la base gira
    golpe = 60 / BPM
    tiempo_anterior = -1
    for t, s in cuadros(golpe * 12):
        n = int(s / golpe)
        fase = (s % golpe) / golpe
        if n != tiempo_anterior:
            lado_on, lado_off = (BOTONES_A, BOTONES_B) if n % 2 == 0 else (BOTONES_B, BOTONES_A)
            for c in lado_off:
                api.luz(c, False)
            for c in lado_on:
                api.luz(c, True)
            todos = n % 4 == 0
            for p in PADS:
                api.luz(p, todos)
            tiempo_anterior = n
        pulso = 1.0 - 0.6 * fase  # cada golpe enciende fuerte y cae
        api.base(hsv(s * 0.35, v=pulso), "izq")
        api.base(hsv(s * 0.35 + 0.5, v=pulso), "der")

    # 4. Silencio
    for c in TODAS:
        api.luz(c, False)
    ultimo = hsv(golpe * 12 * 0.35)
    for t, _ in cuadros(0.9):
        api.base(mezclar(ultimo, [0, 0, 0], t))
    time.sleep(0.6)

    # 5. Claude te necesita: base naranja que parpadea y titilan las opciones
    api.post("/api/ritmo", {"parpadeo": 0.55, "respira": 1.6})
    api.color("naranja", "parpadeo")
    for c in ("A.pad1", "A.pad2", "A.pad3"):
        api.luz(c, True, "parpadeo")
    time.sleep(4.0)

    # 6. Respondes con el pad 1: trabajando (celeste respira) y luego terminó (verde fijo)
    api.luz("A.pad1", True)
    api.luz("A.pad2", False)
    api.luz("A.pad3", False)
    api.color("celeste", "respira")
    time.sleep(2.6)
    api.color("verde")
    api.luz("A.pad1", False)
    time.sleep(1.4)

    # 7. Final: tres destellos y fundido a negro
    for _ in range(3):
        api.base([255, 255, 255])
        for c in TODAS:
            api.luz(c, True)
        time.sleep(0.12)
        api.base([0, 0, 0])
        for c in TODAS:
            api.luz(c, False)
        time.sleep(0.22)
    verde = [0, 255, 60]
    for t, _ in cuadros(1.2):
        api.base(mezclar(verde, [0, 0, 0], t))
    time.sleep(1.0)


def main():
    api = API()
    estado = api.get("/api/estado")
    perfil = api.get("/api/perfiles").get("activo")
    ritmo = estado.get("ritmo") or {}
    try:
        # a oscuras, sin perfil (así Play A no hace nada en el computador), con Play A invitando a presionarlo
        api.post("/api/perfil", {"nombre": None})
        api.post("/api/apagar-luces", {})
        for deck in ("A", "B"):
            api.post("/api/modo", {"deck": deck, "modo": "hotcue"})
        api.base([0, 0, 0])
        api.post("/api/ritmo", {"parpadeo": 0.9})
        api.luz("A.play", True, "parpadeo")
        print("listo: presiona Play A para empezar", flush=True)
        esperar_play()
        print("show: empezó", flush=True)
        show(api)
        print("show: terminó", flush=True)
    finally:
        try:
            api.post("/api/apagar-luces", {})
            if ritmo:
                api.post("/api/ritmo", {k: ritmo[k] for k in ("parpadeo", "respira") if k in ritmo})
            api.post("/api/perfil", {"nombre": perfil})
            print(f"restaurado: perfil {perfil}", flush=True)
        except Exception as e:
            print(f"no pude restaurar: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
