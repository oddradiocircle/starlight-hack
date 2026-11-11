"""Servidor HTTP: API REST, eventos en vivo (SSE) y la página.

Seguridad:
- Por defecto escucha solo en 127.0.0.1 y solo acepta peticiones con Host local
  (evita que una página web cualquiera le hable a través de tu navegador).
- Para escuchar en la red exige un token (encabezado Authorization: Bearer <token>
  o ?token=<token> en la URL, que es lo que usa la página y EventSource).
- Las órdenes (POST) exigen Content-Type: application/json.
"""
from __future__ import annotations

import hmac
import json
import mimetypes
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__, mapa
from .aparato import Aparato, AparatoDesconectado

WEB = Path(__file__).resolve().parent / "web"
mimetypes.add_type("font/woff2", ".woff2")


class Servidor(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, aparato: Aparato, host: str = "127.0.0.1", puerto: int = 8765, token: str | None = None,
                 motor=None, pruebas=None):
        self.aparato, self.token, self.puerto_http, self.motor = aparato, token, puerto, motor
        self.pruebas = pruebas
        self.hosts_locales = {f"127.0.0.1:{puerto}", f"localhost:{puerto}", f"[::1]:{puerto}"}
        super().__init__((host, puerto), Manejador)


class Manejador(BaseHTTPRequestHandler):
    server: Servidor
    server_version = f"starlight/{__version__}"
    # Conexiones persistentes: además de ser más rápidas, esquivan un problema real visto en
    # Windows con Avast Web Shield: si el cierre de la conexión llega pegado al último paquete,
    # el filtro pierde ese paquete y la página o la fuente quedan cortadas.
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def finish(self):
        time.sleep(0.1)  # deja salir el último paquete antes de cerrar (ver arriba)
        super().finish()

    # ------------------------------------------------------------------ utilidades
    @property
    def ruta(self):
        return urlparse(self.path).path

    def _cors(self):
        if self.server.token:  # con token se puede usar desde cualquier origen
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _error(self, code, mensaje):
        self._json({"error": mensaje}, code)

    def _permitido(self) -> bool:
        token = self.server.token
        if token:
            auth = self.headers.get("Authorization", "")
            dado = auth[7:] if auth.startswith("Bearer ") else parse_qs(urlparse(self.path).query).get("token", [""])[0]
            if hmac.compare_digest(dado.encode(), token.encode()):
                return True
            self._error(401, "Falta el token o no es válido.")
            return False
        if self.headers.get("Host", "") not in self.server.hosts_locales:
            self._error(403, "Este servidor solo acepta peticiones locales. Usa --token para abrirlo a la red.")
            return False
        return True

    # ------------------------------------------------------------------ GET
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self._cors()
        self.end_headers()

    def do_GET(self):
        if not self._permitido():
            return
        r = self.ruta
        ap = self.server.aparato
        if r in ("/", "/index.html"):
            return self._archivo(WEB / "index.html")
        if r in ("/pruebas", "/pruebas.html"):
            return self._archivo(WEB / "pruebas.html")
        if r == "/api/pruebas":
            return self._json(self.server.pruebas.info())
        if r.startswith("/fuentes/"):
            return self._archivo(WEB / "fuentes" / Path(r).name)
        if r.count("/") == 1 and r.endswith((".js", ".css")):  # piezas compartidas de las páginas
            return self._archivo(WEB / r[1:])
        if r == "/api/estado":
            return self._json({"version": __version__, **ap.foto()})
        if r == "/api/controles":
            return self._json(mapa.catalogo())
        if r.startswith("/api/sysex/"):
            try:
                que = r.rsplit("/", 1)[1]
                if que == "info":
                    return self._json(ap.info_aparato())
                if que == "crudo":
                    return self._json(ap.perillas_crudas())
                if que == "calibracion":
                    return self._json({"bloques": ap.calibracion()})
            except AparatoDesconectado as e:
                return self._error(503, str(e))
            except ValueError as e:
                return self._error(504, str(e))
        if r == "/editor":
            return self._archivo(WEB / "editor.html")
        if r == "/casa":
            return self._archivo(WEB / "casa.html")
        if r == "/api/casa":
            return self._json(self.server.motor.casa.info())
        if r == "/api/casa/cosas":
            forzar = parse_qs(urlparse(self.path).query).get("forzar", [""])[0] == "1"
            m = self.server.motor
            return self._json({"cosas": m.casa.cosas(forzar=forzar), **m.casa.info()})
        if r == "/api/perfil/definicion":
            try:
                return self._json(self.server.motor.definicion(parse_qs(urlparse(self.path).query).get("clave", [""])[0]))
            except ValueError as e:
                return self._error(400, str(e))
        if r == "/api/acciones":
            from . import declarativo
            return self._json(declarativo.catalogo())
        if r == "/api/perfiles":
            return self._json(self.server.motor.info() if self.server.motor else {"activo": None, "perfiles": []})
        if r == "/api/claude":
            if not self.server.motor:
                return self._json({"estado": None, "sesiones": []})
            return self._json({**self.server.motor.claude.resumen(), "piloto": self.server.motor.info_piloto()})
        if r == "/api/eventos":
            return self._eventos()
        self._error(404, "No existe esa ruta.")

    def _archivo(self, ruta: Path):
        ruta = ruta.resolve()
        if not ruta.is_file() or WEB not in ruta.parents:
            return self._error(404, "No existe ese archivo.")
        data = ruta.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", (mimetypes.guess_type(ruta.name)[0] or "application/octet-stream")
                         + ("; charset=utf-8" if ruta.suffix in (".html", ".css", ".js") else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store" if ruta.suffix in (".html", ".js", ".css") else "max-age=86400")
        self.end_headers()
        self.wfile.write(data)

    def _eventos(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")  # el flujo no tiene largo: termina al cerrar
        self.close_connection = True
        self._cors()
        self.end_headers()
        cola: queue.Queue = queue.Queue(maxsize=2000)

        def oyente(ev):
            try:
                cola.put_nowait(ev)
            except queue.Full:
                pass

        ap = self.server.aparato
        ap.suscribir(oyente)
        try:
            perfiles = self.server.motor.info() if self.server.motor else None
            pruebas = self.server.pruebas.info() if self.server.pruebas else None
            claude = self.server.motor.claude.resumen() if self.server.motor else None
            self._mandar({"tipo": "estado", "version": __version__, "perfiles": perfiles, "pruebas": pruebas,
                          "claude": claude, **ap.foto()})
            while True:
                try:
                    self._mandar(cola.get(timeout=15))
                except queue.Empty:
                    self.wfile.write(b": sigo aqui\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            ap.desuscribir(oyente)

    def _mandar(self, ev):
        self.wfile.write(f"data: {json.dumps(ev, ensure_ascii=False)}\n\n".encode("utf-8"))
        self.wfile.flush()

    # ------------------------------------------------------------------ POST
    def _hook_claude(self):
        """Lo que manda un hook de Claude Code tal cual (su JSON, quizá cortado a 16 kB). Solo se leen
        session_id, el nombre del evento, la herramienta y la carpeta; el resto se descarta sin guardarlo."""
        if not self.headers.get("Content-Type", "").startswith("application/json"):  # igual que las demás órdenes
            return self._error(415, "Las órdenes deben ir en JSON (Content-Type: application/json).")
        try:
            largo = min(int(self.headers.get("Content-Length") or 0), 65536)
        except ValueError:
            largo = 0
        crudo = self.rfile.read(largo) if largo else b""
        if self.headers.get("Content-Length") and int(self.headers["Content-Length"]) > largo:
            self.close_connection = True  # no leímos todo: mejor cerrar
        if not self.server.motor:
            return self._json({"aplicado": False})
        return self._json(self.server.motor.claude.hook(crudo, self.headers.get("X-Orden")))

    def do_POST(self):
        if not self._permitido():
            return
        if self.ruta == "/api/claude/hook":
            return self._hook_claude()
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            return self._error(415, "Las órdenes deben ir en JSON (Content-Type: application/json).")
        try:
            largo = int(self.headers.get("Content-Length") or 0)
            if largo > 65536:
                self.close_connection = True
                return self._error(413, "La orden es demasiado grande.")
            b = json.loads(self.rfile.read(largo) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._error(400, "El cuerpo no es un JSON válido.")
        ap, r = self.server.aparato, self.ruta
        try:
            if r == "/api/luz":
                control = b["control"]
                if ".pad" in control:
                    deck, pad = control.split(".pad")
                    ap.luz_pad(deck, int(pad), bool(b.get("encendida", True)), b.get("modo"), bool(b.get("shift")),
                               b.get("efecto", "fijo"))
                else:
                    ap.luz(control, bool(b.get("encendida", True)), b.get("efecto", "fijo"))
            elif r == "/api/base":
                m = self.server.motor
                if m and m.activo and m.activo.usa_base:
                    return self._error(409, f"El perfil «{m.activo.nombre}» está usando la base. Cambia de perfil para elegir colores.")
                lado = b.get("lado", "ambos")
                if b.get("auto"):
                    ap.base_auto()
                elif "rgb" in b:
                    rgb = b["rgb"]
                    r_, g_, b_ = mapa.hex_a_rgb(rgb) if isinstance(rgb, str) else rgb
                    ap.base_rgb(int(r_), int(g_), int(b_), lado, b.get("efecto", "fijo"))
                else:
                    ap.base_color(b["color"], b.get("efecto", "fijo"), lado)
            elif r == "/api/modo":
                ap.modo_pads(b["deck"], b["modo"])
            elif r == "/api/midi":
                msgs = [tuple(int(x) & 0xFF for x in (list(m) + [0, 0])[:3]) for m in b["msgs"]][:256]
                ap.enviar([m for m in msgs if 0x80 <= m[0] < 0xF0])
            elif r == "/api/apagar-luces":
                ap.apagar_luces()
            elif r == "/api/perfil/guardar":
                return self._json({"clave": self.server.motor.guardar(b.get("clave"), b["definicion"])})
            elif r == "/api/perfil/borrar":
                self.server.motor.borrar(b["clave"])
            elif r == "/api/casa/ha":
                return self._json(self.server.motor.casa.conectar_ha(b.get("url"), b.get("token")))
            elif r == "/api/casa/ha/buscar":
                return self._json({"direcciones": self.server.motor.casa.buscar_ha()})
            elif r == "/api/casa/hue/buscar":
                return self._json({"puentes": self.server.motor.casa.buscar_hue()})
            elif r == "/api/casa/hue/emparejar":
                return self._json(self.server.motor.casa.emparejar_hue(b.get("ip")))
            elif r == "/api/casa/probar":
                from . import mapa as _m
                c = self.server.motor.casa
                valor = _m.hex_a_rgb(b["rgb"]) if b.get("que") == "color" else b.get("valor")
                c.ahora(b["donde"], b["id"], b.get("que", "alternar"), valor)
            elif r == "/api/casa/olvidar":
                if b.get("lado") not in ("ha", "hue"):
                    return self._error(400, "Di qué olvidar: ha o hue.")
                self.server.motor.casa.olvidar(b["lado"])
            elif r == "/api/perfil/capa":
                self.server.motor.guardar_capa(b["clave"], b.get("asignaciones") or [])
            elif r == "/api/perfil/escena":
                m = self.server.motor
                if b.get("borrar"):
                    m.borrar_escena(b["clave"])
                    return self._json({"escena": {}})
                return self._json({"escena": m.grabar_escena(b.get("clave"))})
            elif r == "/api/claude":
                if b.get("olvidar"):
                    self.server.motor.claude.olvidar()
                    return self._json({"aplicado": True})
                return self._json({"aplicado": self.server.motor.estado_claude(str(b.get("estado", "")))})
            elif r == "/api/avanzado":
                if "demo" in b:
                    ap.demo(bool(b["demo"]))
                if "modo_computador" in b:
                    if b["modo_computador"] and not b.get("entiendo"):
                        return self._error(400, "El modo computador sube mucho el volumen y la perilla Master deja de "
                                                "funcionar hasta desconectar el USB. Para activarlo, manda también "
                                                "\"entiendo\": true.")
                    ap.modo_computador(bool(b["modo_computador"]))
                if "interruptor20" in b:
                    ap.interruptor20(int(b["interruptor20"]))
            elif r == "/api/sysex":
                return self._json({"respuesta": ap.sysex_libre(bytes.fromhex(b["hex"]))})
            elif r == "/api/ritmo":
                for efecto in ("parpadeo", "respira", "botones", "botones_lento"):
                    if efecto in b:
                        ap.poner_ritmo(efecto, float(b[efecto]))
                if self.server.motor:
                    self.server.motor._guardar_estado({"ritmo": ap.estado["ritmo"]})
            elif r == "/api/brillo":
                ap.poner_brillo(float(b["valor"]))
                if self.server.motor:
                    self.server.motor._guardar_estado({"brillo": ap.estado["brillo"]})
            elif r == "/api/prueba":
                return self._json(self.server.pruebas.proponer(b))
            elif r == "/api/prueba/ejecutar":
                self.server.pruebas.ejecutar()
            elif r == "/api/prueba/responder":
                return self._json(self.server.pruebas.responder(b["id"], b["respuesta"], b.get("nota", "")))
            elif r == "/api/perfil":
                if not self.server.motor:
                    return self._error(503, "Los perfiles no están activos en este servidor.")
                self.server.motor.activar(b.get("nombre"))
            else:
                return self._error(404, "No existe esa ruta.")
        except AparatoDesconectado as e:
            return self._error(503, str(e))
        except KeyError as e:
            return self._error(400, f"Falta el campo {e}.")
        except (ValueError, TypeError) as e:
            return self._error(400, str(e))
        self._json({"ok": True})


def servir(host="127.0.0.1", puerto=8765, token=None, texto="Starlight", al_listo=None, perfiles=True):
    ap = Aparato(texto)
    motor = None
    if perfiles:
        from .perfiles import Motor

        motor = Motor(ap)
        ap.poner_brillo(motor._leer_estado().get("brillo", 1.0))
        for efecto, segundos in (motor._leer_estado().get("ritmo") or {}).items():
            ap.poner_ritmo(efecto, segundos)
    from .pruebas import Pruebas

    srv = Servidor(ap, host, puerto, token, motor, Pruebas(ap, motor))
    if al_listo:
        al_listo(srv)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        threading.Thread(target=srv.shutdown, daemon=True).start()
        ap.cerrar()
