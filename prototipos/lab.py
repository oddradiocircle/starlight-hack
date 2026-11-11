#!/usr/bin/env python3
"""
lab.py - laboratorio web local para la Hercules DJControl Starlight.

Arranca un servidor que solo escucha en este computador (http://127.0.0.1:8765):
  - muestra en vivo cada control que tocas,
  - deja prender cada luz y marcar qué pasó,
  - guarda lo aprendido para que Claude lo lea en vivo.

Archivos (carpeta lab/):
  mapa.json         nombres y resultados de cada control y luz
  sesion.jsonl      registro completo de la sesión
  para-claude.log   resumen legible de lo que haces en la página

Uso:  python lab.py        (Ctrl+C para salir)
"""
import json
import queue
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import starlight as sl

AQUI = Path(__file__).resolve().parent
LAB = AQUI / "lab"
MAPA = LAB / "mapa.json"
SESION = LAB / "sesion.jsonl"
PARA_CLAUDE = LAB / "para-claude.log"
PAGINA = AQUI / "lab.html"
HOST, PUERTO = "127.0.0.1", 8765


def hx(msg):
    return " ".join(f"{x:02X}" for x in msg)


def desc_limpia(desc):
    return re.sub(r" (\(presiona\)|\(suelta\)|= \d+)$", "", desc)


class Lab:
    def __init__(self):
        LAB.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.clientes = set()
        self.mapa = {"entradas": {}, "luces": {}}
        if MAPA.exists():
            self.mapa.update(json.loads(MAPA.read_text(encoding="utf-8")))
        self.pregunta = None
        self.eco = False
        self.ultimos = {}          # última posición de cada perilla/fader
        self.ultimo_log_cc = {}
        self.vistos = set()        # controles tocados en esta sesión
        self.encendidos = set()    # notas que la página dejó prendidas
        self.silencio_hasta = time.time() + 1.5  # ignora el volcado inicial de perillas
        self.servidor = None
        self.st = sl.Starlight()
        threading.Thread(target=self._bombear, daemon=True).start()
        self.st.enviar(0xB0, 0x7F, 0x7F)  # pide la posición de perillas y faders

    # ---------------------------------------------------------------- utilidades
    def _guardar(self):
        with self.lock:
            tmp = MAPA.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.mapa, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(MAPA)

    def _log(self, ev):
        linea = json.dumps({"hora": time.strftime("%H:%M:%S"), **ev}, ensure_ascii=False)
        with self.lock, SESION.open("a", encoding="utf-8") as f:
            f.write(linea + "\n")

    def para_claude(self, texto):
        linea = f"{time.strftime('%H:%M:%S')} {texto}"
        with self.lock, PARA_CLAUDE.open("a", encoding="utf-8") as f:
            f.write(linea + "\n")
        print(linea, flush=True)

    def suscribir(self):
        q = queue.Queue()
        with self.lock:
            self.clientes.add(q)
        return q

    def desuscribir(self, q):
        with self.lock:
            self.clientes.discard(q)

    def difundir(self, ev):
        with self.lock:
            clientes = list(self.clientes)
        for q in clientes:
            q.put(ev)

    def estado(self):
        return {"mapa": self.mapa, "pregunta": self.pregunta, "eco": self.eco,
                "ultimos": list(self.ultimos.values())}

    # ---------------------------------------------------------------- entrada MIDI
    def _bombear(self):
        while True:
            _t, s, d1, d2 = self.st.cola.get()
            tipo = s & 0xF0
            k = f"{(s | 0x10) if tipo == 0x80 else s:02X}:{d1:02X}"
            desc = sl.describir(s, d1, d2)
            if self.eco and tipo in (0x80, 0x90) and k != "90:03":
                try:
                    self.st.enviar(s | 0x10, d1, 0x7F if tipo == 0x90 and d2 else 0)
                except sl.MidiError:
                    pass
            ev = {"tipo": "midi", "st": s, "d1": d1, "d2": d2, "clave": k, "desc": desc}
            if tipo == 0xB0:
                self.ultimos[k] = [s, d1, d2]
            self.difundir(ev)
            if time.time() < self.silencio_hasta:
                continue

            ahora = time.time()
            if tipo != 0xB0 or ahora - self.ultimo_log_cc.get(k, 0) > 0.3:
                self.ultimo_log_cc[k] = ahora
                self._log(ev)

            es_lsb = tipo == 0xB0 and 0x20 <= d1 < 0x40
            cuenta = tipo == 0xB0 or (tipo == 0x90 and d2 > 0)
            if cuenta and not es_lsb and k not in self.vistos:
                self.vistos.add(k)
                limpia = desc_limpia(desc)
                self.para_claude(f"Tocaste {k.replace(':', ' ')} (1.a vez en la sesión): {limpia}")
                with self.lock:
                    e = self.mapa["entradas"].setdefault(k, {})
                    if not e.get("detectado"):
                        e["detectado"] = True
                        e["desc"] = limpia
                        self._guardar()

    # ---------------------------------------------------------------- acciones
    def enviar(self, msgs, motivo="", origen="pagina", registrar=True):
        limpios = []
        for m in list(msgs)[:256]:
            m = (list(m) + [0, 0, 0])[:3]
            st_, d1, d2 = int(m[0]) & 0xFF, int(m[1]) & 0x7F, int(m[2]) & 0x7F
            if not 0x80 <= st_ < 0xF0:
                continue
            self.st.enviar(st_, d1, d2)
            limpios.append([st_, d1, d2])
            if st_ & 0xF0 in (0x80, 0x90):
                nota = (st_ | 0x10, d1)
                if st_ & 0xF0 == 0x90 and d2:
                    self.encendidos.add(nota)
                else:
                    self.encendidos.discard(nota)
        ev = {"tipo": "enviado", "msgs": limpios, "motivo": motivo, "origen": origen}
        self.difundir(ev)
        if registrar and limpios:
            self._log(ev)
            if origen == "pagina":
                self.para_claude(f"La página envió {' | '.join(hx(m) for m in limpios)}"
                                 + (f" ({motivo})" if motivo else ""))

    def marcar(self, clave, campo, valor, titulo=""):
        with self.lock:
            if campo == "nombre":
                self.mapa["entradas"].setdefault(clave, {})["nombre"] = valor
                texto = f"Nombraste {clave.replace(':', ' ')} como «{valor}»"
            elif campo == "luz":
                self.mapa["luces"][clave] = {**(valor or {}), "titulo": titulo}
                r = (valor or {}).get("resultado")
                nota = (valor or {}).get("nota")
                legible = {"si": "SÍ se prendió", "no": "NO pasó nada", "otra": "otra cosa"}.get(r, r)
                texto = f"Luz {clave.replace(':', ' ')} [{titulo}]: {legible}" + (f" — «{nota}»" if nota else "")
            else:
                raise ValueError(f"campo desconocido: {campo}")
            self._guardar()
        ev = {"tipo": "marca", "clave": clave, "campo": campo, "valor": valor, "titulo": titulo}
        self.difundir(ev)
        self._log(ev)
        self.para_claude(texto)

    def preguntar(self, p):
        p = {"id": p.get("id") or time.strftime("q%H%M%S"), "texto": p.get("texto", ""),
             "opciones": p.get("opciones") or [], "resaltar": p.get("resaltar") or [],
             "enviar": p.get("enviar") or []}
        self.pregunta = p
        if p["enviar"]:
            self.enviar(p["enviar"], motivo=f"pregunta {p['id']}", origen="claude")
        self.difundir({"tipo": "pregunta", "pregunta": p})
        self._log({"tipo": "pregunta", **p})

    def responder(self, r):
        p = self.pregunta or {}
        texto = p.get("texto", "?") if p.get("id") == r.get("id") else "?"
        nota = (r.get("nota") or "").strip()
        self._log({"tipo": "respuesta", **r})
        self.para_claude(f"Respuesta a «{texto}» [{r.get('id')}]: {r.get('respuesta')}"
                         + (f" — «{nota}»" if nota else ""))
        self.pregunta = None
        self.difundir({"tipo": "pregunta", "pregunta": None})

    def comentario(self, texto):
        texto = (texto or "").strip()
        if texto:
            self._log({"tipo": "comentario", "texto": texto})
            self.para_claude(f"Mensaje desde la página: «{texto}»")

    def set_eco(self, activo):
        self.eco = activo
        self.difundir({"tipo": "eco", "activo": activo})
        self.para_claude(f"Eco {'activado' if activo else 'desactivado'} (la luz sigue al botón)")

    def reset(self):
        sl.apagar_todo(self.st)
        for st_, d1 in list(self.encendidos):
            self.st.enviar(st_, d1, 0)
        self.encendidos.clear()
        self.st.enviar(*sl.BASE_IZQ, 0)
        self.st.enviar(*sl.BASE_DER, 0)
        sl.base_manual(self.st, False)
        self.difundir({"tipo": "reset"})

    def cerrar(self):
        try:
            self.reset()
        except sl.MidiError:
            pass
        self.st.cerrar()
        self.para_claude("Laboratorio cerrado")


LAB_ = None


class Handler(BaseHTTPRequestHandler):
    server_version = "StarlightLab/1.0"

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        ruta = self.path.split("?")[0]
        if ruta in ("/", "/index.html"):
            data = PAGINA.read_bytes()  # se lee cada vez: basta recargar para ver cambios
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif ruta == "/eventos":
            self._sse()
        elif ruta == "/api/estado":
            self._json(LAB_.estado())
        else:
            self._json({"error": "no existe"}, 404)

    def _sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        q = LAB_.suscribir()
        LAB_.para_claude("Página abierta en el navegador")

        def mandar(ev):
            self.wfile.write(f"data: {json.dumps(ev, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.flush()

        try:
            mandar({"tipo": "estado", **LAB_.estado()})
            while True:
                try:
                    mandar(q.get(timeout=15))
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            LAB_.desuscribir(q)

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            b = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json({"error": "JSON inválido"}, 400)
        ruta = self.path.split("?")[0]
        try:
            if ruta == "/api/enviar":
                LAB_.enviar(b.get("msgs", []), b.get("motivo", ""), b.get("origen", "pagina"),
                            b.get("registrar", True))
            elif ruta == "/api/marcar":
                LAB_.marcar(b["clave"], b["campo"], b.get("valor"), b.get("titulo", ""))
            elif ruta == "/api/pregunta":
                LAB_.preguntar(b)
            elif ruta == "/api/respuesta":
                LAB_.responder(b)
            elif ruta == "/api/comentario":
                LAB_.comentario(b.get("texto", ""))
            elif ruta == "/api/eco":
                LAB_.set_eco(bool(b.get("activo")))
            elif ruta == "/api/reset":
                LAB_.reset()
            elif ruta == "/api/apagar":
                self._json({"ok": True})
                threading.Thread(target=LAB_.servidor.shutdown, daemon=True).start()
                return
            else:
                return self._json({"error": "no existe"}, 404)
        except (sl.MidiError, KeyError, ValueError, TypeError) as e:
            return self._json({"error": str(e)}, 500)
        self._json({"ok": True})


def main():
    global LAB_
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        LAB_ = Lab()
    except sl.MidiError as e:
        sys.exit(str(e))
    srv = ThreadingHTTPServer((HOST, PUERTO), Handler)
    srv.daemon_threads = True
    LAB_.servidor = srv
    print(f"Starlight Lab listo en http://{HOST}:{PUERTO}", flush=True)
    LAB_.para_claude("Laboratorio iniciado")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        LAB_.cerrar()


if __name__ == "__main__":
    main()
