"""Ir a un bloque de Wave Terminal desde el servidor, aunque esté en otra pestaña.

`wsh focusblock` solo enfoca bloques de la pestaña de quien lo llama (en Wave cada pestaña es una
vista aparte), así que no sirve para saltar entre pestañas. Lo que sí sirve, leído del código de
Wave 0.14:

    Alt + N           (Cmd en macOS) cambia a la pestaña N (1-9), en el orden de workspace.tabids
    Ctrl + Shift + N  enfoca el bloque N (1-9) de la pestaña, en el orden de su layout (leaforder)

Para saber qué número tiene cada cosa, y para comprobar después que el foco quedó en el bloque
correcto, se lee la base de datos de Wave en solo lectura (waveterm.db: pestaña activa, orden de
pestañas, bloques de cada pestaña y bloque con foco). Si Wave cambia ese formato, esto deja de
funcionar sin romper nada: ir() devuelve False y dice por qué.

Solo Windows por ahora (las teclas y el traer al frente usan la API de Windows).
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

from . import sistema


def _base_de_datos() -> Path | None:
    for carpeta in (os.environ.get("WAVETERM_DATA_HOME"),
                    os.path.join(os.environ.get("LOCALAPPDATA", ""), "waveterm", "Data")):
        if carpeta:
            ruta = Path(carpeta) / "db" / "waveterm.db"
            if ruta.is_file():
                return ruta
    return None


def ubicar(bloque: str) -> dict | None:
    """Dónde está un bloque: {"tab", "pestana" (1-…), "num" (1-…), "activa", "foco"}, o None."""
    ruta = _base_de_datos()
    if not ruta:
        return None
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True, timeout=2)
    try:
        tabs = {oid: json.loads(d) for oid, d in con.execute("select oid, data from db_tab")}
        layouts = {oid: json.loads(d) for oid, d in con.execute("select oid, data from db_layout")}
        espacios = [json.loads(d) for (d,) in con.execute("select data from db_workspace")]
    finally:
        con.close()
    for tab_id, tab in tabs.items():
        if bloque not in (tab.get("blockids") or []):
            continue
        espacio = next((w for w in espacios if tab_id in (w.get("tabids") or [])), None)
        if not espacio:
            return None
        layout = layouts.get(tab.get("layoutstate")) or {}
        orden = [h.get("blockid") for h in layout.get("leaforder") or []]
        nodos = {h.get("nodeid"): h.get("blockid") for h in layout.get("leaforder") or []}
        return {"tab": tab_id, "pestana": espacio["tabids"].index(tab_id) + 1,
                "pestanas": len(espacio["tabids"]),
                "num": orden.index(bloque) + 1 if bloque in orden else None,
                "activa": espacio.get("activetabid"), "foco": nodos.get(layout.get("focusednodeid"))}
    return None


def enfocado() -> str | None:
    """El bloque que tiene el foco en la pestaña activa, si Wave está al frente. Si no, None."""
    if not sistema.WIN or sistema.app_al_frente() != "wave":
        return None
    ruta = _base_de_datos()
    if not ruta:
        return None
    try:
        con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True, timeout=1)
        try:
            espacios = [json.loads(d) for (d,) in con.execute("select data from db_workspace")]
            activas = {w.get("activetabid") for w in espacios}
            for oid, data in con.execute("select oid, data from db_tab"):
                if oid not in activas:
                    continue
                fila = con.execute("select data from db_layout where oid = ?", (json.loads(data).get("layoutstate"),)).fetchone()
                if fila:
                    layout = json.loads(fila[0])
                    nodos = {h.get("nodeid"): h.get("blockid") for h in layout.get("leaforder") or []}
                    return nodos.get(layout.get("focusednodeid"))
        finally:
            con.close()
    except (sqlite3.Error, ValueError):
        return None
    return None


def _listo(bloque: str, tab: str) -> bool:
    u = ubicar(bloque)
    return bool(u and u["activa"] == tab and u["foco"] == bloque)


def ir(bloque: str, espera: float = 1.5) -> tuple[bool, str]:
    """Trae Wave al frente, cambia a la pestaña del bloque y lo enfoca. Devuelve (quedó, por qué no).
    «Quedó» solo es True si la base de datos de Wave confirma la pestaña activa y el bloque con foco:
    así es seguro escribir una respuesta después."""
    if not sistema.WIN:
        return False, "Ir a otra pestaña de Wave solo funciona en Windows por ahora."
    u = ubicar(bloque)
    if not u:
        return False, "No encontré esa terminal en Wave (¿se cerró?)."
    if sistema.app_al_frente() != "wave":
        sistema.traer_al_frente("wave")
        time.sleep(0.15)
        if sistema.app_al_frente() != "wave":
            return False, "No pude traer Wave al frente."
    if u["activa"] != u["tab"]:
        if u["pestana"] > 9:  # Alt+] depende de la distribución del teclado: mejor no adivinar
            return False, f"Esa terminal está en la pestaña {u['pestana']}; el atajo de Wave llega hasta la 9."
        sistema.teclas("alt", str(u["pestana"]))
        time.sleep(0.12)
    if u["num"] and u["num"] <= 9 and (ubicar(bloque) or {}).get("foco") != bloque:
        sistema.teclas("ctrl", "shift", str(u["num"]))
    fin = time.monotonic() + espera
    while time.monotonic() < fin:
        if _listo(bloque, u["tab"]):
            return True, ""
        time.sleep(0.08)
    return False, "Wave no confirmó que esa terminal quedara enfocada."
