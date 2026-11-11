"""CLI de starlight.

    starlight serve                      arranca el servidor (único dueño del aparato)
    starlight estado                     cómo está el aparato
    starlight escuchar                   muestra en vivo cada control que tocas
    starlight luz A.play on              prende o apaga una luz (A.pad2 usa el modo actual)
    starlight base rojo --efecto respira color de la paleta: número 1-12 o nombre
    starlight base "#ff0080"             color libre
    starlight base auto                  la base vuelve a su show normal
    starlight brillo 40                  brillo general de la base, de 0 a 100
    starlight modo A fx                  modo de los pads: hotcue, loop, fx, sampler
    starlight midi 91 07 7F              mensaje MIDI crudo (hexadecimal)
    starlight apagar                     apaga las luces y devuelve la base a su show normal
    starlight perfiles                   lista los perfiles (Shift + Vinyl cambia de perfil en el aparato)
    starlight perfil escritorio          activa un perfil («ninguno» para desactivar)
    starlight perfil nuevo "Mi perfil"   crea un perfil tuyo a partir de la plantilla
    starlight puertos                    puertos MIDI de este equipo (no usa el servidor)

Para usar un servidor en otro equipo: --servidor http://equipo:8765 --token XXXX
(o las variables STARLIGHT_URL y STARLIGHT_TOKEN).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import webbrowser

from . import __version__, mapa

URL_DEFECTO = "http://127.0.0.1:8765"


# ----------------------------------------------------------------------------- cliente HTTP
def _peticion(args, metodo, ruta, cuerpo=None, stream=False):
    url = args.servidor.rstrip("/") + ruta
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    cab = {"Content-Type": "application/json"}
    if args.token:
        cab["Authorization"] = f"Bearer {args.token}"
    req = urllib.request.Request(url, data=datos, method=metodo, headers=cab)
    try:
        r = urllib.request.urlopen(req, timeout=None if stream else 10)
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", e.reason)
        except ValueError:
            msg = e.reason
        sys.exit(f"El servidor respondió: {msg}")
    except urllib.error.URLError as e:
        sys.exit(f"No pude hablar con el servidor en {args.servidor} ({e.reason}).\n"
                 f"¿Está corriendo? Arráncalo con: starlight serve")
    if stream:
        return r
    with r:
        return json.loads(r.read() or b"{}")


def _post(args, ruta, cuerpo):
    return _peticion(args, "POST", ruta, cuerpo)


# ----------------------------------------------------------------------------- comandos
def cmd_serve(args):
    from .servidor import servir

    if args.host not in ("127.0.0.1", "localhost", "::1") and not args.token:
        sys.exit("Para escuchar en la red necesitas un token: starlight serve --host 0.0.0.0 --token <secreto>")

    def listo(srv):
        ap = srv.aparato
        url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '::') else args.host}:{args.puerto}"
        print(f"starlight {__version__} · {url}" + (f"/?token={args.token}" if args.token else ""))
        print("Aparato:", f"conectado ({ap.info()['puerto']})" if ap.conectado else ap.error)
        print("Ctrl+C para salir.", flush=True)
        if args.abrir:
            webbrowser.open(url + (f"/?token={args.token}" if args.token else ""))

    servir(args.host, args.puerto, args.token, args.aparato, listo)


def cmd_estado(args):
    e = _peticion(args, "GET", "/api/estado")
    print(f"Aparato: {'conectado · ' + e['puerto'] if e['conectado'] else e.get('error')}")
    base = e["base"]
    if base.get("modo") == "auto":
        print("Base: show normal")
    else:
        for lado in ("izq", "der"):
            v = base.get(lado, {})
            print(f"Base {lado}: {v.get('color') or '#%02x%02x%02x' % tuple(v.get('rgb', (0, 0, 0)))} · {v.get('efecto')}")
    print("Modo de pads:", " · ".join(f"{d} {m or '?'}" for d, m in e["modos"].items()))
    encendidas = [k for k, v in e["luces"].items() if v]
    print("Luces encendidas:", ", ".join(encendidas) if encendidas else "ninguna")
    for k, v in sorted(e["controles"].items()):
        print(f"  {k:14} {v * 100:5.1f} %")


def cmd_escuchar(args):
    r = _peticion(args, "GET", "/api/eventos", stream=True)
    print("Escuchando… (Ctrl+C para salir)", flush=True)
    try:
        for linea in r:
            if not linea.startswith(b"data: "):
                continue
            ev = json.loads(linea[6:])
            if args.json:
                print(json.dumps(ev, ensure_ascii=False), flush=True)
            elif ev["tipo"] == "control":
                crudo = " ".join(f"{x:02X}" for x in ev["crudo"])
                extra = " ".join(f"{k}={v}" for k, v in ev["extra"].items())
                v, clase = ev["valor"], ev["clase"]
                valor = (f"{int(v):+d} pasos" if clase == "jog" else
                         f"{v * 100:.1f} %" if clase in ("continuo", "desconocido") else
                         "presiona" if v else "suelta")
                print(f"{ev['control']:16} {valor:10} {'shift ' if ev['shift'] else ''}{extra:18} {crudo}", flush=True)
            elif ev["tipo"] in ("luz", "base", "modo", "conexion"):
                print(f"· {ev['tipo']}: " + json.dumps({k: v for k, v in ev.items() if k != 'tipo'},
                                                         ensure_ascii=False), flush=True)
    except KeyboardInterrupt:
        pass


def cmd_luz(args):
    _post(args, "/api/luz", {"control": args.control, "encendida": args.estado == "on", "modo": args.modo})
    print(f"{args.control}: {'encendida' if args.estado == 'on' else 'apagada'}")


def cmd_base(args):
    c = args.color
    if c == "auto":
        _post(args, "/api/base", {"auto": True})
        return print("Base: show normal")
    if c.startswith("#") or (len(c) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in c)):
        _post(args, "/api/base", {"rgb": c if c.startswith("#") else "#" + c, "lado": args.lado, "efecto": args.efecto})
        return print(f"Base {args.lado}: {c} · {args.efecto}")
    _post(args, "/api/base", {"color": c, "efecto": args.efecto, "lado": args.lado})
    print(f"Base {args.lado}: {c} · {args.efecto}")


def cmd_claude(args):
    """Estado de Claude Code para la base.

    starlight claude trabajando|esperando|listo|error   lo pone a mano (nunca falla)
    starlight claude hook        para un hook: lee el JSON del evento por la entrada y lo reenvía
    starlight claude sesiones    muestra cada sesión y su estado
    starlight claude olvidar     borra las sesiones que recuerda el servidor
    """
    if args.estado == "sesiones":
        r = _peticion(args, "GET", "/api/claude")
        if not r["sesiones"]:
            return print("No hay sesiones de Claude Code (¿están instalados los hooks?).")
        for s in r["sesiones"]:
            print(f"{s['estado']:<11} {s['proyecto']:<24} {s['motivo'] or ''}  (hace {s['hace']} s)")
        return
    if args.estado == "olvidar":
        _post(args, "/api/claude", {"olvidar": True})
        return print("Sesiones olvidadas.")
    # trabajando/esperando/listo/error y hook: nunca fallan, para no estorbarle a Claude si el servidor no está
    try:
        if args.estado == "hook":
            import time
            ruta, datos = "/api/claude/hook", sys.stdin.buffer.read(16000)
            extra = {"X-Orden": str(time.time_ns())}
        else:
            ruta, datos, extra = "/api/claude", json.dumps({"estado": args.estado}).encode(), {}
        req = urllib.request.Request(args.servidor.rstrip("/") + ruta, method="POST", data=datos,
                                     headers={"Content-Type": "application/json", **extra,
                                              **({"Authorization": f"Bearer {args.token}"} if args.token else {})})
        urllib.request.urlopen(req, timeout=2).read()
    except Exception:
        pass


def cmd_ritmo(args):
    _post(args, "/api/ritmo", {args.efecto: args.segundos})
    print(f"Un ciclo de {args.efecto}: {args.segundos:g} s")


def cmd_brillo(args):
    _post(args, "/api/brillo", {"valor": args.porcentaje / 100})
    print(f"Brillo de la base: {args.porcentaje:g} %")


def cmd_aparato(args):
    i = _peticion(args, "GET", "/api/sysex/info")
    print(f"Fabricante {i['fabricante']} (Guillemot/Hercules) · familia {i['familia']} · modelo {i['modelo']}")
    print(f"Versión {i['version']} · ID del chip {i['id_chip']} · interruptor 20 = {i['interruptor20']}")


def cmd_demo(args):
    _post(args, "/api/avanzado", {"demo": args.estado == "on"})
    print("Demostración de luces " + ("encendida." if args.estado == "on" else "apagada; la base vuelve a su color."))


def cmd_modo_computador(args):
    if args.estado == "on" and not args.entiendo:
        sys.exit("El modo computador sube mucho el volumen y la perilla Master deja de funcionar hasta desconectar "
                 "el USB. Baja el volumen y repite con --entiendo.")
    _post(args, "/api/avanzado", {"modo_computador": args.estado == "on", "entiendo": args.entiendo})
    print("Modo computador " + ("activo. Para volver del todo, desconecta y conecta el USB." if args.estado == "on"
                                else "apagado (el volumen solo vuelve desconectando el USB)."))


def cmd_sysex(args):
    if args.que == "crudo":
        for k, v in _peticion(args, "GET", "/api/sysex/crudo").items():
            print(f"  {k:12} {v:5}  ({v / 4095 * 100:5.1f} %)")
    elif args.que == "calibracion":
        for i, bloque in enumerate(_peticion(args, "GET", "/api/sysex/calibracion")["bloques"]):
            print(f"  bloque {i}: " + " ".join(f"{x:02X}" for x in bloque))
    else:
        if not args.hex:
            sys.exit('Escribe el mensaje: starlight sysex enviar "F0 7E 7F 06 01 F7"')
        r = _post(args, "/api/sysex", {"hex": " ".join(args.hex)})
        print("Respuesta:", r.get("respuesta") or "(ninguna)")


def cmd_modo(args):
    _post(args, "/api/modo", {"deck": args.deck.upper(), "modo": args.modo})
    print(f"Pads del deck {args.deck.upper()}: {args.modo}")


def cmd_midi(args):
    try:
        b = [int(x, 16) for x in args.bytes]
    except ValueError:
        sys.exit("Escribe 2 o 3 números en hexadecimal, por ejemplo: starlight midi 91 07 7F")
    _post(args, "/api/midi", {"msgs": [b]})
    print("Enviado:", " ".join(f"{x:02X}" for x in b))


def cmd_apagar(args):
    _post(args, "/api/apagar-luces", {})
    print("Luces apagadas y base en su show normal.")


def cmd_perfiles(args):
    info = _peticion(args, "GET", "/api/perfiles")
    for p in info["perfiles"]:
        marca = "●" if p["clave"] == info["activo"] else "○"
        print(f"{marca} {p['nombre']:12} ({p['clave']}, {p['origen']})  {p['descripcion']}")
        if p["error"]:
            print(f"    Error: {p['error']}")
    print(f"{'●' if not info['activo'] else '○'} Ninguno")
    print(f"\nTus perfiles van en: {info.get('carpeta')}\nCambia de perfil desde el aparato con Shift + Vinyl.")


def cmd_perfil(args):
    if args.nombre == "nuevo":
        from .perfiles import crear_perfil

        if not args.extra:
            sys.exit("Escribe el nombre: starlight perfil nuevo <nombre>")
        try:
            ruta = crear_perfil(" ".join(args.extra))
        except ValueError as e:
            sys.exit(str(e))
        print(f"Perfil creado: {ruta}\nÁbrelo, cámbialo y guárdalo: el servidor lo carga solo.")
        return
    _post(args, "/api/perfil", {"nombre": None if args.nombre == "ninguno" else args.nombre})
    print("Sin perfil activo." if args.nombre == "ninguno" else f"Perfil activo: {args.nombre}")


def cmd_puertos(_args):
    from . import midi

    entradas, salidas = midi.puertos()
    print(f"Backend: {midi.nombre_backend()}")
    print("Entradas:", *[f"  {n}" for n in entradas] or ["  (ninguna)"], sep="\n")
    print("Salidas:", *[f"  {n}" for n in salidas] or ["  (ninguna)"], sep="\n")


def main(argv=None):
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(prog="starlight", description="Servidor, API y CLI para la Hercules DJControl Starlight.",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n\n", 1)[1])
    p.add_argument("--version", action="version", version=f"starlight {__version__}")
    p.add_argument("--servidor", default=os.environ.get("STARLIGHT_URL", URL_DEFECTO), help="URL del servidor")
    p.add_argument("--token", default=os.environ.get("STARLIGHT_TOKEN"), help="token del servidor")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="comando")

    s = sub.add_parser("serve", help="arranca el servidor")
    s.add_argument("--host", default="127.0.0.1", help="dónde escuchar (por defecto, solo este equipo)")
    s.add_argument("--puerto", type=int, default=8765)
    s.add_argument("--aparato", default="Starlight", help="texto del nombre del puerto MIDI")
    s.add_argument("--abrir", action="store_true", help="abre la página en el navegador")
    s.set_defaults(fn=cmd_serve)

    sub.add_parser("estado", help="cómo está el aparato").set_defaults(fn=cmd_estado)
    e = sub.add_parser("escuchar", help="muestra en vivo cada control que tocas")
    e.add_argument("--json", action="store_true", help="un evento JSON por línea")
    e.set_defaults(fn=cmd_escuchar)

    l = sub.add_parser("luz", help="prende o apaga una luz")
    l.add_argument("control", help="A.play, B.cue, vinyl, bassfilter, A.pad1…")
    l.add_argument("estado", choices=["on", "off"])
    l.add_argument("--modo", choices=mapa.MODOS, help="modo del pad (por defecto, el actual)")
    l.set_defaults(fn=cmd_luz)

    b = sub.add_parser("base", help="color de la base")
    b.add_argument("color", help="1-12, nombre (rojo, celeste…), #rrggbb o auto")
    b.add_argument("--efecto", choices=list(mapa.EFECTOS), default="fijo")
    b.add_argument("--lado", choices=list(mapa.LADOS), default="ambos")
    b.set_defaults(fn=cmd_base)

    cl = sub.add_parser("claude", help="estado de Claude Code para la base (lo usan los hooks)")
    cl.add_argument("estado", choices=["trabajando", "esperando", "listo", "inactivo", "error", "hook", "sesiones", "olvidar"],
                    help="un estado a mano; hook (lee el evento de Claude Code por la entrada); sesiones; olvidar")
    cl.set_defaults(fn=cmd_claude)
    rt = sub.add_parser("ritmo", help="velocidad de un efecto: segundos que dura un ciclo")
    rt.add_argument("efecto", choices=["parpadeo", "respira"])
    rt.add_argument("segundos", type=float)
    rt.set_defaults(fn=cmd_ritmo)
    br = sub.add_parser("brillo", help="brillo general de la base, de 0 a 100")
    br.add_argument("porcentaje", type=float)
    br.set_defaults(fn=cmd_brillo)

    sub.add_parser("aparato", help="identidad, versión e ID del chip (por SysEx)").set_defaults(fn=cmd_aparato)
    dm = sub.add_parser("demo", help="modo de demostración de luces del firmware")
    dm.add_argument("estado", choices=["on", "off"])
    dm.set_defaults(fn=cmd_demo)
    mc = sub.add_parser("modo-computador", help="modo 7F7E (¡sube el volumen!)")
    mc.add_argument("estado", choices=["on", "off"])
    mc.add_argument("--entiendo", action="store_true", help="confirma que bajaste el volumen")
    mc.set_defaults(fn=cmd_modo_computador)
    sx = sub.add_parser("sysex", help="lecturas SysEx y mensajes a mano: crudo, calibracion, enviar HEX")
    sx.add_argument("que", choices=["crudo", "calibracion", "enviar"])
    sx.add_argument("hex", nargs="*")
    sx.set_defaults(fn=cmd_sysex)

    m = sub.add_parser("modo", help="modo de los pads")
    m.add_argument("deck", choices=["A", "B", "a", "b"])
    m.add_argument("modo", choices=mapa.MODOS)
    m.set_defaults(fn=cmd_modo)

    x = sub.add_parser("midi", help="mensaje MIDI crudo")
    x.add_argument("bytes", nargs="+")
    x.set_defaults(fn=cmd_midi)

    sub.add_parser("apagar", help="apaga las luces").set_defaults(fn=cmd_apagar)
    sub.add_parser("perfiles", help="lista los perfiles").set_defaults(fn=cmd_perfiles)
    pf = sub.add_parser("perfil", help="activa un perfil, «ninguno», o crea uno: perfil nuevo <nombre>")
    pf.add_argument("nombre")
    pf.add_argument("extra", nargs="*")
    pf.set_defaults(fn=cmd_perfil)
    sub.add_parser("puertos", help="puertos MIDI de este equipo").set_defaults(fn=cmd_puertos)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
