"""El aparato: único dueño de la Starlight.

Lee sus controles, guarda el estado, avisa cada cambio a quien escuche y se reconecta
solo si desconectas el USB (al volver, repinta las luces que tenía).
"""
from __future__ import annotations

import queue
import threading
import time

from . import mapa, midi


class AparatoDesconectado(RuntimeError):
    pass


class Aparato:
    def __init__(self, texto: str = "Starlight", vigilar_cada: float = 2.0):
        self.texto = texto
        self.vigilar_cada = vigilar_cada
        self.puerto = None
        self.error = None                     # por qué no está conectada, en palabras humanas
        self._lock = threading.RLock()
        self._oyentes: list = []
        self._dec = mapa.Decodificador()
        self._vivo = True
        self._animaciones: dict = {}   # lado -> (rgb, efecto, inicio): efectos hechos por el servidor
        self._titilan: dict = {}       # clave de luz -> mensajes (prender, apagar) de las luces que titilan
        self._titilando = False
        self._animando = False
        # Emisor único del color de la base: los efectos y los perfiles dejan aquí el color deseado
        # y un solo hilo lo envía (máx. 60 por segundo, solo si cambió).
        self._deseado: dict = {}
        self._espera_sysex = None   # (condición, cola) de la consulta que espera respuesta
        self._lock_consulta = threading.Lock()
        self._enviado: dict = {}
        self.estado = {
            "controles": {},                  # continuos: nombre -> 0..1
            "luces": {},                      # "A.play" -> bool ; "A.pad1.hotcue" -> bool
            "base": {"modo": "auto"},         # o {"modo": "manual", "izq": {...}, "der": {...}}
            "modos": {"A": None, "B": None},  # modo de pads de cada deck
            "eq": "bajos",                    # la perilla de cada deck: bajos o filtro
            "brillo": 1.0,                    # brillo general de la base, 0 a 1
            "ritmo": {"parpadeo": 1.0, "respira": 2.4},  # duración de un ciclo de cada efecto, en segundos
            "avanzado": {"demo": False, "modo_computador": False},  # interruptores SysEx (viven en RAM)
        }
        self._intentar_conectar()
        threading.Thread(target=self._vigilar, daemon=True, name="vigilar").start()
        threading.Thread(target=self._leer, daemon=True, name="leer").start()
        threading.Thread(target=self._emisor_base, daemon=True, name="emisor-base").start()
        threading.Thread(target=self._leer_sysex, daemon=True, name="leer-sysex").start()

    # ------------------------------------------------------------------ conexión
    @property
    def conectado(self) -> bool:
        return self.puerto is not None

    def _intentar_conectar(self):
        try:
            p = midi.abrir(self.texto)
        except midi.MidiError as e:
            if str(e) != self.error:
                self.error = str(e)
                self._emitir({"tipo": "conexion", **self.info()})
            return
        with self._lock:
            self.puerto, self.error = p, None
            self._enviado = {}  # el aparato vuelve de fábrica: hay que reenviar el color
            self.estado["avanzado"] = {"demo": False, "modo_computador": False}  # y sus interruptores
        self._emitir({"tipo": "conexion", **self.info()})
        self._repintar()
        self.enviar([mapa.VOLCADO])

    def _desconectar(self, motivo: str):
        with self._lock:
            p, self.puerto = self.puerto, None
            self.error = motivo
        if p:
            try:
                p.cerrar()
            except midi.MidiError:
                pass
        self._emitir({"tipo": "conexion", **self.info()})

    def _vigilar(self):
        while self._vivo:
            time.sleep(self.vigilar_cada)
            if not self.conectado:
                self._intentar_conectar()
                continue
            try:
                entradas, _ = midi.puertos()
            except midi.MidiError:
                continue
            if not any(self.texto.lower() in n.lower() for n in entradas):
                self._desconectar("La Starlight se desconectó. Conéctala por USB.")

    def info(self) -> dict:
        return {"conectado": self.conectado, "puerto": self.puerto.nombre if self.puerto else None,
                "error": self.error, "backend": midi.nombre_backend()}

    # ------------------------------------------------------------------ eventos
    def suscribir(self, fn):
        with self._lock:
            self._oyentes.append(fn)

    def desuscribir(self, fn):
        with self._lock:
            if fn in self._oyentes:
                self._oyentes.remove(fn)

    def _emitir(self, ev: dict):
        with self._lock:
            oyentes = list(self._oyentes)
        for fn in oyentes:
            try:
                fn(ev)
            except Exception:
                pass

    def anunciar(self, ev: dict):
        """Avisa un evento a todos los que escuchan (lo usan los perfiles)."""
        self._emitir(ev)

    def anunciar_base(self, lados: dict):
        """Registra y avisa colores de la base que ya se enviaron por otra vía (perfiles rápidos)."""
        with self._lock:
            b = self.estado["base"]
            if b.get("modo") != "manual":
                b = {"modo": "manual", "izq": {"rgb": [0, 0, 0], "efecto": "fijo"},
                     "der": {"rgb": [0, 0, 0], "efecto": "fijo"}}
            for lado, rgb in lados.items():
                b[lado] = {"rgb": list(rgb), "efecto": "fijo"}
            self.estado["base"] = b
            foto = dict(b)
        self._emitir({"tipo": "base", **foto})

    def foto(self) -> dict:
        with self._lock:
            return {**self.info(), **{k: (dict(v) if isinstance(v, dict) else v) for k, v in self.estado.items()}}

    def _leer(self):
        while self._vivo:
            p = self.puerto
            if p is None:
                time.sleep(0.2)
                continue
            try:
                st, d1, d2 = p.cola.get(timeout=0.5)
            except queue.Empty:
                continue
            e = self._dec(st, d1, d2)
            if e is None:
                continue
            self._registrar_entrada(e)
            self._emitir({"tipo": "control", **e.a_dict()})

    def _registrar_entrada(self, e: mapa.Evento):
        cambio_modo = None
        with self._lock:
            if e.tipo == "continuo":
                self.estado["controles"][e.control] = e.valor
                if e.control.endswith(".eq"):
                    self.estado["eq"] = e.extra["modo"]
            elif e.tipo == "pad":
                deck = e.control[0]
                if self.estado["modos"][deck] != e.extra["modo"]:
                    self.estado["modos"][deck] = e.extra["modo"]
                    cambio_modo = (deck, e.extra["modo"])
            elif e.tipo == "boton" and e.valor and ".modo." in e.control:
                deck, modo = e.control[0], e.control.rsplit(".", 1)[1]
                self.estado["modos"][deck] = modo
                cambio_modo = (deck, modo)
        if cambio_modo:
            self._emitir({"tipo": "modo", "deck": cambio_modo[0], "modo": cambio_modo[1]})

    # ------------------------------------------------------------------ salidas
    def enviar(self, msgs, avisar: bool = True):
        p = self.puerto
        if p is None:
            raise AparatoDesconectado(self.error or "La Starlight no está conectada.")
        try:
            for st, d1, d2 in msgs:
                p.enviar(st, d1, d2)
        except midi.MidiError as e:
            self._desconectar(f"Se perdió la conexión con la Starlight: {e}")
            raise AparatoDesconectado(self.error) from e
        if avisar:
            self._emitir({"tipo": "midi", "msgs": [list(m) for m in msgs]})

    def sysex(self, datos: bytes):
        """Envía un mensaje SysEx (F0 … F7)."""
        p = self.puerto
        if p is None:
            raise AparatoDesconectado(self.error or "La Starlight no está conectada.")
        try:
            p.enviar_sysex(datos)
        except midi.MidiError as e:
            self._desconectar(f"Se perdió la conexión con la Starlight: {e}")
            raise AparatoDesconectado(self.error) from e

    # ------------------------------------------------------------------ SysEx avanzado
    def _leer_sysex(self):
        """Consume todo SysEx que llega (cada escritura recibe una confirmación) y entrega la esperada."""
        while self._vivo:
            p = self.puerto
            cola = getattr(p, "sysex", None) if p else None
            if cola is None:
                time.sleep(0.2)
                continue
            try:
                r = cola.get(timeout=0.5)
            except queue.Empty:
                continue
            espera = self._espera_sysex
            if espera and espera[0](r):
                espera[1].put(r)

    def consulta(self, pedido: bytes, timeout: float = 1.5) -> bytes:
        """Envía un SysEx y espera su respuesta."""
        if not hasattr(self.puerto, "sysex"):
            raise AparatoDesconectado(self.error or "La Starlight no está conectada.")
        universal = pedido[:2] == bytes([0xF0, 0x7E])

        def condicion(r):
            if universal:
                return r[:2] == bytes([0xF0, 0x7E])
            return r[:5] == mapa.SYSEX_HERCULES and len(r) > 9 and r[5] in (3, 5) and r[6:10] == pedido[6:10]

        llegada: queue.Queue = queue.Queue()
        with self._lock_consulta:
            self._espera_sysex = (condicion, llegada)
            try:
                self.sysex(pedido)
                return llegada.get(timeout=timeout)
            except queue.Empty:
                raise ValueError("La Starlight no respondió a la consulta.") from None
            finally:
                self._espera_sysex = None

    def _avisar_avanzado(self):
        with self._lock:
            av = dict(self.estado["avanzado"])
        self._emitir({"tipo": "avanzado", **av})

    def demo(self, activo: bool):
        """Modo de demostración del firmware (7F7F): todas las luces y la base cambiando de color sola."""
        self.consulta(mapa.sysex_orden(2, mapa.PARAM_DEMO, 0, (1 if activo else 0, 0, 0, 0)))
        with self._lock:
            self.estado["avanzado"]["demo"] = bool(activo)
        if not activo:
            self._enviado = {}
            self._repintar()  # al apagarse, la demo deja la base oscura
        self._avisar_avanzado()

    def modo_computador(self, activo: bool):
        """Modo 7F7E. Con 1 el computador toma los modos, PERO el volumen de salida sube mucho y la perilla
        Master deja de funcionar. Con 0 el aparato lo acepta, pero el volumen solo vuelve desconectando el USB."""
        self.consulta(mapa.sysex_orden(2, mapa.PARAM_MODO_COMPUTADOR, 0, (1 if activo else 0, 0, 0, 0)))
        with self._lock:
            self.estado["avanzado"]["modo_computador"] = bool(activo)
        self._avisar_avanzado()

    def interruptor20(self, valor: int):
        self.consulta(mapa.sysex_orden(2, mapa.PARAM_INTERRUPTOR, 0, (1 if valor else 0, 0, 0, 0)))

    def info_aparato(self) -> dict:
        ident = self.consulta(mapa.IDENTIDAD)
        chip = mapa.leer_respuesta(self.consulta(mapa.sysex_orden(1, mapa.PARAM_ID)))
        inter = mapa.leer_respuesta(self.consulta(mapa.sysex_orden(1, mapa.PARAM_INTERRUPTOR)))
        return {"fabricante": ident[5:8].hex(" ").upper(), "familia": ident[8:10].hex(" ").upper(),
                "modelo": ident[10:12].hex(" ").upper(), "version": ".".join(str(x) for x in ident[12:16]),
                "id_chip": "".join(f"{v:02X}" for v in chip["valores"][:8]), "interruptor20": inter["valores"][0]}

    def perillas_crudas(self) -> dict:
        r = mapa.leer_respuesta(self.consulta(mapa.sysex_orden(1, mapa.PARAM_CRUDO)))
        return dict(zip(mapa.NOMBRES_CRUDO, r["valores"]))

    def calibracion(self) -> list:
        return [mapa.leer_respuesta(self.consulta(mapa.sysex_orden(1, mapa.PARAM_CALIBRACION, sub)))["valores"][:32]
                for sub in range(8)]

    def sysex_libre(self, datos: bytes):
        """SysEx a mano para experimentar. Siempre bloquea la escritura de la calibración (12)."""
        if mapa.es_escritura_bloqueada(datos):
            raise ValueError("Esa orden grabaría la calibración de fábrica en la flash. Está bloqueada a propósito.")
        if datos[:5] == mapa.SYSEX_HERCULES or datos[:2] == bytes([0xF0, 0x7E]):
            try:
                return self.consulta(datos).hex(" ").upper()
            except ValueError:
                return None
        self.sysex(datos)
        return None

    def luz(self, control: str, encendida: bool, efecto: str = "fijo"):
        self._titilar(control, mapa.msg_luz(control, True), mapa.msg_luz(control, False), encendida and efecto == "parpadeo")
        self.enviar(mapa.msg_luz(control, encendida), avisar=False)
        with self._lock:
            self.estado["luces"][control] = bool(encendida)
        self._emitir({"tipo": "luz", "control": control, "encendida": bool(encendida),
                      "parpadea": control in self._titilan})

    def _titilar(self, clave: str, prender, apagar, activo: bool):
        if not activo:
            self._titilan.pop(clave, None)
            return
        self._titilan[clave] = (prender, apagar)
        if not self._titilando:
            self._titilando = True
            threading.Thread(target=self._bucle_titilar, daemon=True, name="titilar").start()

    def _bucle_titilar(self):
        prendidas = None
        inicio = time.time()
        while self._titilan and self._vivo:
            ciclo = self.estado["ritmo"].get("parpadeo", 1.0)
            fase = ((time.time() - inicio) % ciclo) < ciclo / 2
            if fase != prendidas:
                prendidas = fase
                for prender, apagar in list(self._titilan.values()):
                    try:
                        self.enviar(prender if fase else apagar, avisar=False)
                    except AparatoDesconectado:
                        break
            time.sleep(0.02)
        self._titilando = False

    def luz_pad(self, deck: str, pad: int, encendida: bool, modo: str | None = None, shift: bool = False,
                efecto: str = "fijo"):
        modo = modo or self.estado["modos"][deck] or "hotcue"
        clave = f"{deck}.pad{pad}.{modo}" + (".shift" if shift else "")
        self._titilar(clave, mapa.msg_pad(deck, pad, True, modo, shift), mapa.msg_pad(deck, pad, False, modo, shift),
                      encendida and efecto == "parpadeo")
        self.enviar(mapa.msg_pad(deck, pad, encendida, modo, shift), avisar=False)
        with self._lock:
            self.estado["luces"][clave] = bool(encendida)
        self._emitir({"tipo": "luz", "control": clave, "encendida": bool(encendida), "parpadea": clave in self._titilan})

    def _base_lados(self, lado: str, valor: dict):
        with self._lock:
            b = self.estado["base"]
            if b.get("modo") != "manual":
                b = {"modo": "manual", "izq": {"rgb": [0, 0, 0], "efecto": "fijo"},
                     "der": {"rgb": [0, 0, 0], "efecto": "fijo"}}
            for d in mapa.LADOS[lado]:
                b[mapa.LADO_DE_DECK[d]] = dict(valor)
            self.estado["base"] = b
            foto = dict(b)
        self._emitir({"tipo": "base", **foto})

    def base_color(self, color, efecto: str = "fijo", lado: str = "ambos"):
        """Color de la paleta de 12. Se envía por el SysEx de color completo (conocemos su RGB exacto)
        para que el brillo general y los efectos funcionen igual que con cualquier color."""
        nombre, rgb = mapa.PALETA[mapa.color_paleta(color)]
        self.base_rgb(*rgb, lado=lado, efecto=efecto, nombre=nombre)

    def poner_brillo(self, valor: float):
        """Brillo general de la base, de 0 a 1. No aplica al show normal (lo hace el firmware solo)."""
        valor = min(1.0, max(0.0, float(valor)))
        with self._lock:
            self.estado["brillo"] = valor
        self._enviado = {}  # que el emisor reenvíe todo con el brillo nuevo
        self._emitir({"tipo": "brillo", "valor": valor})

    def poner_ritmo(self, efecto: str, segundos: float):
        """Duración de un ciclo de Parpadea o Respira (0,1 a 10 segundos)."""
        if efecto not in ("parpadeo", "respira"):
            raise ValueError("El efecto debe ser parpadeo o respira.")
        with self._lock:
            self.estado["ritmo"][efecto] = min(10.0, max(0.1, float(segundos)))
            ritmo = dict(self.estado["ritmo"])
        self._emitir({"tipo": "ritmo", **ritmo})

    def base_rgb(self, r: int, g: int, b: int, lado: str = "ambos", efecto: str = "fijo", nombre: str | None = None):
        """Color completo (7 bits por canal) por el SysEx 7F00 que hallamos en el firmware.
        Parpadeo y respiración los hace el servidor, porque el firmware solo los tiene para su paleta."""
        if efecto not in mapa.EFECTOS:
            raise ValueError(f"Efecto desconocido: {efecto}. Opciones: {', '.join(mapa.EFECTOS)}")
        self.parar_animacion(lado)
        self.enviar([(*mapa.BASE_AUTO, 0)], avisar=False)
        rgb = mapa.rgb_completo(r, g, b)
        for d in mapa.LADOS[lado]:
            self.color_rapido(mapa.LADO_DE_DECK[d], rgb)
            if efecto != "fijo":
                self._animaciones[mapa.LADO_DE_DECK[d]] = (rgb, efecto, time.time())
        if self._animaciones and not self._animando:
            self._animando = True
            threading.Thread(target=self._animar, daemon=True, name="efectos").start()
        self._base_lados(lado, {"rgb": list(rgb), "efecto": efecto, **({"color": nombre} if nombre else {})})

    def parar_animacion(self, lado: str = "ambos"):
        for d in mapa.LADOS[lado]:
            self._animaciones.pop(mapa.LADO_DE_DECK[d], None)

    def color_rapido(self, lado: str, rgb):
        """Deja el color deseado para un lado ('izq' o 'der'); lo envía el emisor único."""
        self._deseado[lado] = tuple(mapa.rgb_completo(*(int(c) for c in rgb)))

    def _soltar_color(self, lado: str = "ambos"):
        """Otro mensaje (paleta, show normal) toma el control de la base: el emisor deja de reenviar."""
        for d in mapa.LADOS[lado]:
            self._deseado.pop(mapa.LADO_DE_DECK[d], None)
            self._enviado.pop(mapa.LADO_DE_DECK[d], None)

    def _emisor_base(self):
        while self._vivo:
            if self.puerto is not None:
                factor = self.estado["brillo"] ** 2   # curva aproximada del ojo: 50 % se ve como la mitad
                for lado, rgb in list(self._deseado.items()):
                    final = tuple(round(c * factor) for c in rgb)
                    if self._enviado.get(lado) != final:
                        try:
                            self.sysex(mapa.sysex_base_rgb(*final, lado))
                            self._enviado[lado] = final
                        except AparatoDesconectado:
                            break
            time.sleep(1 / 60)

    def _animar(self):
        import math

        while self._animaciones and self._vivo:
            ahora = time.time()
            for lado, (rgb, efecto, t0) in list(self._animaciones.items()):
                t = ahora - t0
                ciclo = self.estado["ritmo"].get(efecto, 1.0)
                if efecto == "parpadeo":
                    f = 1.0 if (t % ciclo) < ciclo / 2 else 0.06
                else:  # respira: sube y baja suave
                    f = 0.12 + 0.88 * (0.5 + 0.5 * math.cos(2 * math.pi * t / ciclo))
                self.color_rapido(lado, [round(c * f) for c in rgb])
            time.sleep(0.02)
        self._animando = False

    def base_auto(self):
        self.parar_animacion()
        self._soltar_color()
        self.enviar(mapa.msg_base_auto(), avisar=False)
        with self._lock:
            self.estado["base"] = {"modo": "auto"}
        self._emitir({"tipo": "base", "modo": "auto"})

    def modo_pads(self, deck: str, modo: str):
        self.enviar(mapa.msg_modo(deck, modo), avisar=False)
        with self._lock:
            self.estado["modos"][deck] = modo
        self._emitir({"tipo": "modo", "deck": deck, "modo": modo})

    def apagar_luces(self):
        """Apaga todas las luces que conoce y devuelve la base a su show normal."""
        self._titilan.clear()
        with self._lock:
            encendidas = [k for k, v in self.estado["luces"].items() if v]
        for clave in encendidas:
            partes = clave.split(".")
            if len(partes) >= 3 and partes[1].startswith("pad"):
                self.luz_pad(partes[0], int(partes[1][3:]), False, partes[2], shift=len(partes) == 4)
            else:
                self.luz(clave, False)
        self.base_auto()

    def _repintar(self):
        """Tras reconectar, el aparato vuelve de fábrica: le devuelve lo que tenía."""
        with self._lock:
            luces = dict(self.estado["luces"])
            base = dict(self.estado["base"])
            modos = dict(self.estado["modos"])
        try:
            for deck, modo in modos.items():
                if modo:
                    self.enviar(mapa.msg_modo(deck, modo), avisar=False)
            for clave, on in luces.items():
                if not on:
                    continue
                partes = clave.split(".")
                if len(partes) >= 3 and partes[1].startswith("pad"):
                    self.enviar(mapa.msg_pad(partes[0], int(partes[1][3:]), True, partes[2], len(partes) == 4),
                                avisar=False)
                else:
                    self.enviar(mapa.msg_luz(clave, True), avisar=False)
            if base.get("modo") == "manual":
                self.enviar([(*mapa.BASE_AUTO, 0)], avisar=False)
                for lado in ("izq", "der"):
                    v = base[lado]
                    self.color_rapido(lado, v["rgb"])
                    if v.get("efecto", "fijo") != "fijo":
                        self._animaciones[lado] = (tuple(v["rgb"]), v["efecto"], time.time())
                if self._animaciones and not self._animando:
                    self._animando = True
                    threading.Thread(target=self._animar, daemon=True, name="efectos").start()
        except AparatoDesconectado:
            pass

    def cerrar(self, restaurar: bool = True):
        self._vivo = False
        if restaurar and self.conectado:
            try:
                self.apagar_luces()
            except AparatoDesconectado:
                pass
        if self.puerto:
            self.puerto.cerrar()
            self.puerto = None
