"""Casa: luces y escenas de Home Assistant y del Hue Bridge, para usarlas desde los perfiles.

Todo pasa dentro de tu red local:
- Home Assistant: su API REST con un token de acceso de larga duración que pegas en la página /casa.
- Hue Bridge: su API local (v1). Se empareja una vez presionando el botón del puente.

La conexión se guarda en ~/.starlight/casa.json, solo en este equipo. El servidor nunca devuelve el token
ni el usuario del puente: la página solo ve si está conectado.

Las órdenes salen por un hilo aparte, para que una luz lenta no frene los demás controles. Si una perilla
manda muchos valores seguidos, solo se envía el último (como mucho 8 por segundo por luz).
"""
from __future__ import annotations

import http.client
import json
import os
import queue
import socket
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

HOGAR = Path(os.environ.get("STARLIGHT_HOGAR") or Path.home() / ".starlight")
CONFIG = HOGAR / "casa.json"
PAUSA_CONTINUA = 1 / 8  # como mucho 8 órdenes por segundo por luz, para no saturar el puente
DOMINIOS = {"light": "Luz", "switch": "Interruptor", "scene": "Escena", "script": "Rutina", "fan": "Ventilador",
            "media_player": "Reproductor", "cover": "Cortina", "input_boolean": "Interruptor"}


class CasaError(ValueError):
    pass


def _contexto_puente():
    """El puente Hue usa un certificado propio: solo para su IP local se acepta sin verificar."""
    import ssl
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


_conexiones = threading.local()  # una conexión abierta por equipo y por hilo
_SIN_RESPUESTA = "No hubo respuesta. Revisa la dirección y que el equipo esté encendido en tu red."


def _conexion(esquema: str, host: str, puerto: int, espera: float, puente: bool):
    pool = getattr(_conexiones, "pool", None)
    if pool is None:
        pool = _conexiones.pool = {}
    clave = (esquema, host, puerto)
    k = pool.get(clave)
    if k is None:
        k = (http.client.HTTPSConnection(host, puerto, timeout=espera, context=_contexto_puente() if puente else None)
             if esquema == "https" else http.client.HTTPConnection(host, puerto, timeout=espera))
        pool[clave] = k
    elif k.sock is not None:
        k.sock.settimeout(espera)
    return clave, k


def _pedir(metodo: str, url: str, cuerpo=None, token: str | None = None, espera: float = 6.0, puente: bool = False):
    """Una petición HTTP que reutiliza la conexión con cada equipo. Así el puente Hue no negocia el cifrado
    en cada orden: con conexión nueva tardaba ~0,4 s; reutilizada, ~30 ms."""
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    cab = {"Content-Type": "application/json"}
    if token:
        cab["Authorization"] = f"Bearer {token}"
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise CasaError("Escribe la dirección completa, por ejemplo http://homeassistant.local:8123.")
    ruta = (p.path or "/") + (f"?{p.query}" if p.query else "")
    puerto = p.port or (443 if p.scheme == "https" else 80)
    for intento in (1, 2):
        clave, k = _conexion(p.scheme, p.hostname, puerto, espera, puente)
        reutilizada = k.sock is not None
        try:
            k.request(metodo, ruta, body=datos, headers=cab)
            r = k.getresponse()
            estado, texto = r.status, r.read().decode("utf-8", "replace")
            if r.will_close:
                k.close()
                _conexiones.pool.pop(clave, None)
            break
        except (http.client.HTTPException, OSError) as e:
            k.close()
            _conexiones.pool.pop(clave, None)
            # Una conexión guardada que el equipo cerró por estar quieta falla al primer uso: se reintenta una
            # vez con una nueva. Si se acabó el tiempo de espera no se reintenta (y un «alternar» no se repite).
            cerrada = isinstance(e, (http.client.RemoteDisconnected, ConnectionResetError, ConnectionAbortedError,
                                     BrokenPipeError))
            if intento == 2 or not reutilizada or not cerrada:
                raise CasaError(_SIN_RESPUESTA) from None
    if estado == 401:
        raise CasaError("Home Assistant no aceptó el token. Crea uno nuevo en tu perfil de Home Assistant.")
    if estado >= 400:
        raise CasaError(f"Respondió con el error {estado}.")
    try:
        return json.loads(texto) if texto.strip() else {}
    except ValueError:
        raise CasaError("La respuesta no se entendió.") from None


def rgb_a_xy(r: int, g: int, b: int) -> list[float]:
    """Color RGB a las coordenadas xy que usan las luces Hue (gama ancha, D65)."""
    def lineal(c):
        c = c / 255
        return ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92
    r, g, b = lineal(r), lineal(g), lineal(b)
    x = r * 0.664511 + g * 0.154324 + b * 0.162028
    y = r * 0.283881 + g * 0.668433 + b * 0.047685
    z = r * 0.000088 + g * 0.072310 + b * 0.986039
    total = x + y + z
    return [round(x / total, 4), round(y / total, 4)] if total else [0.3127, 0.329]


class Casa:
    def __init__(self, al_cambiar=None):
        self._lock = threading.Lock()
        self._al_cambiar = al_cambiar or (lambda info: None)
        self.config = self._leer()
        self.estado = {"ha": {"error": None, "cuantas": 0}, "hue": {"error": None, "cuantas": 0}}
        self._cosas: list[dict] = []
        self._cosas_ts = 0.0
        self._cola: queue.Queue = queue.Queue(maxsize=500)
        self._ultimo: dict = {}   # orden continua más reciente por luz (solo se envía la última)
        self._enviado: dict = {}  # cuándo se envió la última orden continua de cada luz
        threading.Thread(target=self._trabajar, daemon=True, name="casa").start()

    # ------------------------------------------------------------------ configuración
    def _leer(self) -> dict:
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _guardar(self):
        HOGAR.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8")
        self._cosas_ts = 0.0

    def info(self) -> dict:
        """Lo que puede ver la página: si cada lado está conectado. Nunca el token ni el usuario del puente."""
        ha, hue = self.config.get("ha") or {}, self.config.get("hue") or {}
        return {"ha": {"url": ha.get("url", ""), "conectado": bool(ha.get("token")), **self.estado["ha"]},
                "hue": {"ip": hue.get("ip", ""), "emparejado": bool(hue.get("usuario")), **self.estado["hue"]}}

    def _avisar(self):
        try:
            self._al_cambiar(self.info())
        except Exception:
            pass

    # ------------------------------------------------------------------ Home Assistant
    def conectar_ha(self, url: str, token: str | None) -> dict:
        url = (url or "").strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            raise CasaError("Escribe la dirección completa, por ejemplo http://homeassistant.local:8123.")
        token = (token or "").strip() or (self.config.get("ha") or {}).get("token")
        if not token:
            raise CasaError("Pega el token de acceso de larga duración.")
        r = _pedir("GET", url + "/api/", token=token)
        if not isinstance(r, dict) or "message" not in r:
            raise CasaError("Esa dirección no parece ser Home Assistant.")
        with self._lock:
            self.config["ha"] = {"url": url, "token": token}
            self._guardar()
        self.estado["ha"]["error"] = None
        self.cosas(forzar=True)
        self._avisar()
        return self.info()

    def _ha(self):
        ha = self.config.get("ha") or {}
        if not ha.get("token"):
            raise CasaError("Conecta Home Assistant en la página Casa.")
        return ha["url"], ha["token"]

    def _cosas_ha(self) -> list[dict]:
        url, token = self._ha()
        salida = []
        for e in _pedir("GET", url + "/api/states", token=token):
            ent = e.get("entity_id", "")
            dominio = ent.split(".")[0]
            if dominio not in DOMINIOS:
                continue
            a = e.get("attributes") or {}
            encendida = e.get("state") in ("on", "playing", "open")
            cosa = {"donde": "ha", "id": ent, "nombre": a.get("friendly_name") or ent, "clase": DOMINIOS[dominio],
                    "encendida": encendida}
            if dominio in ("scene", "script"):
                cosa.update(tipo="escena", puede=["activar"])
            elif dominio == "light":
                modos = a.get("supported_color_modes") or []
                puede = ["onoff"]
                if any(m != "onoff" for m in modos):
                    puede.append("brillo")
                if any(m in ("hs", "xy", "rgb", "rgbw", "rgbww") for m in modos):
                    puede.append("color")
                if "color_temp" in modos:
                    puede.append("temperatura")
                    cosa["kelvin"] = [a.get("min_color_temp_kelvin") or 2200, a.get("max_color_temp_kelvin") or 6500]
                cosa.update(tipo="luz", puede=puede, nivel=round((a.get("brightness") or 0) / 255, 3) if encendida else 0)
                if "brillo" not in puede:
                    cosa["clase"] = "Enchufe o luz simple"
            elif dominio == "media_player":
                cosa.update(tipo="reproductor", puede=["play", "volumen"], nivel=a.get("volume_level"))
            else:
                cosa.update(tipo="aparato", puede=["onoff"])
            salida.append(cosa)
        return salida

    def _orden_ha(self, ent: str, que: str, valor=None):
        url, token = self._ha()
        dominio = ent.split(".")[0]
        servicio = lambda dom, srv, datos=None: _pedir("POST", f"{url}/api/services/{dom}/{srv}", {"entity_id": ent, **(datos or {})}, token)
        if que == "escena" or dominio in ("scene", "script"):
            return servicio(dominio, "turn_on")
        if dominio == "media_player":
            if que in ("play", "alternar"):
                return servicio("media_player", "media_play_pause")
            if que == "volumen":
                return servicio("media_player", "volume_set", {"volume_level": round(max(0.0, min(1.0, float(valor))), 3)})
            if que in ("subir", "bajar", "paso"):
                cosa = self._cosa("ha", ent) or {}
                actual = cosa.get("nivel") if isinstance(cosa.get("nivel"), (int, float)) else 0.3
                delta = (float(valor or 10) if que != "bajar" else -float(valor or 10)) / 100
                nuevo = round(max(0.0, min(1.0, actual + delta)), 3)
                cosa["nivel"] = nuevo
                return servicio("media_player", "volume_set", {"volume_level": nuevo})
            return servicio("media_player", {"encender": "turn_on", "apagar": "turn_off"}.get(que, "toggle"))
        if que == "brillo":
            pct = round(max(0.0, min(1.0, float(valor))) * 100)
            return servicio("light", "turn_off") if pct == 0 else servicio("light", "turn_on", {"brightness_pct": pct})
        if que in ("subir", "bajar", "paso"):
            paso = float(valor or 10) * (-1 if que == "bajar" else 1)
            return servicio("light", "turn_on", {"brightness_step_pct": round(max(-100, min(100, paso)))})
        if que == "temperatura":  # 0 cálida, 1 fría
            minimo, maximo = (self._cosa("ha", ent) or {}).get("kelvin", [2200, 6500])
            return servicio("light", "turn_on", {"color_temp_kelvin": round(minimo + (maximo - minimo) * float(valor))})
        if que == "color":
            return servicio("light", "turn_on", {"rgb_color": list(valor)})
        return servicio(dominio if dominio != "scene" else "homeassistant",
                        {"alternar": "toggle", "encender": "turn_on", "apagar": "turn_off"}[que])

    # ------------------------------------------------------------------ Hue Bridge
    @staticmethod
    def _mis_ips() -> list[str]:
        try:
            return sorted({a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)})
        except OSError:
            return []

    @staticmethod
    def _mdns(servicio: str, espera: float = 2.5) -> list[str]:
        """Pregunta por mDNS en cada red del equipo (Wi-Fi, cable, VPN) quién ofrece un servicio.
        Devuelve las IP que respondieron. Todo queda en la red local."""
        mias = Casa._mis_ips()
        nombre = b"".join(bytes([len(x)]) + x.encode() for x in servicio.split(".")) + b"\x00"
        consulta = b"\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00" + nombre + b"\x00\x0c\x00\x01"
        marca = servicio.split(".")[0].encode()
        socks = []
        for mia in mias or ["0.0.0.0"]:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            try:
                s.bind((mia, 0))
                if mia != "0.0.0.0":
                    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(mia))
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
                s.setblocking(False)
                s.sendto(consulta, ("224.0.0.251", 5353))
                socks.append(s)
            except OSError:
                s.close()
        import select
        encontrados, fin = [], time.time() + espera
        try:
            while socks and time.time() < fin:
                listos, _, _ = select.select(socks, [], [], 0.3)
                for s in listos:
                    try:
                        datos, (ip, _) = s.recvfrom(9000)
                    except OSError:
                        continue
                    # solo respuestas (bit QR) de otros equipos que nombran el servicio
                    if ip not in mias and len(datos) > 2 and datos[2] & 0x80 and marca in datos and ip not in encontrados:
                        encontrados.append(ip)
        finally:
            for s in socks:
                s.close()
        return encontrados

    @staticmethod
    def buscar_hue(espera: float = 2.5) -> list[str]:
        """Puentes Hue en tu red (mDNS, sin servicios de internet)."""
        return Casa._mdns("_hue._tcp.local", espera)

    @staticmethod
    def buscar_ha(espera: float = 2.5) -> list[str]:
        """Home Assistant en tu red: devuelve direcciones listas para usar."""
        return [f"http://{ip}:8123" for ip in Casa._mdns("_home-assistant._tcp.local", espera)]

    def emparejar_hue(self, ip: str) -> dict:
        ip = (ip or "").strip()
        if not ip:
            raise CasaError("Escribe la dirección IP del puente o búscalo.")
        r = _pedir("POST", f"https://{ip}/api", {"devicetype": "starlight#computador"}, puente=True)
        r = r[0] if isinstance(r, list) and r else r
        if isinstance(r, dict) and "success" in r:
            with self._lock:
                self.config["hue"] = {"ip": ip, "usuario": r["success"]["username"]}
                self._guardar()
            self.estado["hue"]["error"] = None
            self.cosas(forzar=True)
            self._avisar()
            return self.info()
        if isinstance(r, dict) and (r.get("error") or {}).get("type") == 101:
            raise CasaError("Presiona el botón redondo del puente Hue y, en menos de 30 segundos, vuelve a hacer clic en Emparejar.")
        raise CasaError("El puente no aceptó el emparejamiento.")

    def _hue(self):
        hue = self.config.get("hue") or {}
        if not hue.get("usuario"):
            raise CasaError("Empareja el puente Hue en la página Casa.")
        return f"https://{hue['ip']}/api/{hue['usuario']}"

    @staticmethod
    def _puede_hue(estado: dict) -> list[str]:
        puede = ["onoff"]
        if "bri" in estado:
            puede.append("brillo")
        if "xy" in estado or "hue" in estado:
            puede.append("color")
        if "ct" in estado:
            puede.append("temperatura")
        return puede

    def _cosas_hue(self) -> list[dict]:
        base = self._hue()
        salida = []
        for gid, g in (_pedir("GET", base + "/groups", puente=True) or {}).items():
            if g.get("type") in ("Room", "Zone", "Entertainment"):
                accion = g.get("action") or {}
                on = bool((g.get("state") or {}).get("any_on"))
                salida.append({"donde": "hue", "id": f"grupo:{gid}", "nombre": g.get("name", gid), "tipo": "luz",
                               "clase": {"Room": "Habitación", "Zone": "Zona", "Entertainment": "Área de entretenimiento"}[g["type"]],
                               "encendida": on, "puede": self._puede_hue(accion),
                               "nivel": round(accion.get("bri", 0) / 254, 3) if on else 0})
        for lid, l in (_pedir("GET", base + "/lights", puente=True) or {}).items():
            estado = l.get("state") or {}
            on = bool(estado.get("on"))
            salida.append({"donde": "hue", "id": f"luz:{lid}", "nombre": l.get("name", lid), "tipo": "luz", "clase": "Luz",
                           "encendida": on, "puede": self._puede_hue(estado),
                           "nivel": round(estado.get("bri", 0) / 254, 3) if on else 0})
        cuartos = {c["id"].split(":")[1]: c["nombre"] for c in salida if c["id"].startswith("grupo:")}
        for sid, e in (_pedir("GET", base + "/scenes", puente=True) or {}).items():
            # las escenas temporales que crean las apps (Hue Essentials y otras) no se muestran
            if e.get("type") != "GroupScene" or not e.get("group") or e.get("recycle") or str(e.get("name", "")).startswith("HueEssentials"):
                continue
            cuarto = cuartos.get(str(e["group"]))
            salida.append({"donde": "hue", "id": f"escena:{e['group']}:{sid}", "nombre": e.get("name", sid), "tipo": "escena",
                           "clase": f"Escena · {cuarto}" if cuarto else "Escena", "puede": ["activar"]})
        return salida

    def _orden_hue(self, ident: str, que: str, valor=None):
        base = self._hue()
        partes = ident.split(":")
        if partes[0] == "escena":
            return _pedir("PUT", f"{base}/groups/{partes[1]}/action", {"scene": partes[2]}, puente=True)
        ruta = f"{base}/groups/{partes[1]}/action" if partes[0] == "grupo" else f"{base}/lights/{partes[1]}/state"
        poner = lambda datos: _pedir("PUT", ruta, datos, puente=True)
        if que == "alternar":
            if partes[0] == "grupo":
                on = bool((_pedir("GET", f"{base}/groups/{partes[1]}", puente=True).get("state") or {}).get("any_on"))
            else:
                on = bool((_pedir("GET", f"{base}/lights/{partes[1]}", puente=True).get("state") or {}).get("on"))
            return poner({"on": not on})
        if que == "encender":
            return poner({"on": True})
        if que == "apagar":
            return poner({"on": False})
        if que == "brillo":
            v = max(0.0, min(1.0, float(valor)))
            return poner({"on": False} if v == 0 else {"on": True, "bri": max(1, round(v * 254)), "transitiontime": 1})
        if que in ("subir", "bajar", "paso"):
            paso = float(valor or 10) * (-1 if que == "bajar" else 1)
            return poner({"on": True, "bri_inc": round(max(-254, min(254, paso * 2.54))), "transitiontime": 1})
        if que == "temperatura":  # 0 cálida, 1 fría (en mireds: 500 cálida, 153 fría)
            return poner({"on": True, "ct": round(500 - float(valor) * (500 - 153)), "transitiontime": 1})
        if que == "color":
            return poner({"on": True, "xy": rgb_a_xy(*valor)})
        raise CasaError(f"Orden desconocida: {que}")

    # ------------------------------------------------------------------ lo que hay y las órdenes
    def cosas(self, forzar: bool = False) -> list[dict]:
        """Luces, grupos y escenas de los dos lados (se recuerdan 30 segundos)."""
        if not forzar and time.time() - self._cosas_ts < 30:
            return self._cosas
        salida = []
        for lado, fn in (("ha", self._cosas_ha), ("hue", self._cosas_hue)):
            if not (self.config.get(lado) or {}):
                continue
            try:
                lista = fn()
                salida += lista
                self.estado[lado] = {"error": None, "cuantas": len(lista)}
            except CasaError as e:
                self.estado[lado] = {"error": str(e), "cuantas": 0}
        self._cosas, self._cosas_ts = salida, time.time()
        return salida

    def _cosa(self, donde: str, ident: str):
        return next((c for c in self._cosas if c["donde"] == donde and c["id"] == ident), None)

    def olvidar(self, lado: str):
        with self._lock:
            self.config.pop(lado, None)
            self._guardar()
        self.estado[lado] = {"error": None, "cuantas": 0}
        self._avisar()

    def orden(self, donde: str, ident: str, que: str, valor=None, continua: bool = False, sumar: bool = False):
        """Pone una orden en la cola. Las continuas (perillas) se juntan: solo cuenta la última.
        Con sumar (el jog), los pasos que llegan mientras tanto se suman en una sola orden."""
        if continua or sumar:
            with self._lock:
                nueva = (donde, ident) not in self._ultimo
                previo = self._ultimo.get((donde, ident))
                if sumar and previo and previo[0] == que:
                    valor = previo[1] + valor
                self._ultimo[(donde, ident)] = (que, valor)
            if nueva:
                self._poner(("continua", donde, ident))
            return
        self._poner(("una", donde, ident, que, valor))

    def _poner(self, x):
        try:
            self._cola.put_nowait(x)
        except queue.Full:
            pass

    def ahora(self, donde: str, ident: str, que: str, valor=None):
        """Orden inmediata (para el botón Probar de la página). Lanza CasaError si falla."""
        return (self._orden_ha if donde == "ha" else self._orden_hue)(ident, que, valor)

    def _trabajar(self):
        while True:
            x = self._cola.get()
            try:
                if x[0] == "continua":
                    _, donde, ident = x
                    espera = self._enviado.get((donde, ident), 0) + PAUSA_CONTINUA - time.time()
                    if espera > 0:
                        time.sleep(espera)
                    with self._lock:
                        que, valor = self._ultimo.pop((donde, ident), (None, None))
                    if que:
                        self._enviado[(donde, ident)] = time.time()
                        self.ahora(donde, ident, que, valor)
                else:
                    _, donde, ident, que, valor = x
                    self.ahora(donde, ident, que, valor)
            except CasaError as e:
                lado = "ha" if x[1] == "ha" else "hue"
                self.estado[lado]["error"] = str(e)
                self._avisar()
            except Exception as e:  # nunca tumbar el hilo
                print(f"[casa] {e}")
