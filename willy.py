#!/usr/bin/env python3
"""Willy: mapa con puntos etiquetados y "ve al punto X".

Uso:  ./willy.py              servidor web en http://localhost:8765
      ./willy.py ve cocina    manda el robot al punto "cocina"
      ./willy.py puntos       lista los puntos guardados
      ./willy.py ve-raw X Y   prueba de calibración: manda [X, Y] tal cual al robot

Los puntos se guardan en puntos.json, en metros, en el mismo sistema que la ruta grabada.
Cómo se traducen a la orden del robot está en CONVERSION (puntos.json) y aún se está calibrando.
"""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from mapa import load_segments
from paseo import CHARGING, connect, log, record_path, safe_status

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "rutas"
PUNTOS = ROOT / "data" / "puntos.json"
PORT = 8765

START_POINT_CLEAN = (9, 1)     # point-zone:start-point-clean (sin parámetros, usa target-point)
START_POINT_CLEAN_II = (9, 9)  # point-zone:start-point-clean-ii(target-point piid 5, str)
TARGET_POINT = (9, 5)          # point-zone:target-point
TARGET_POINT_PIID = 5
SUCTION = (7, 5)               # sweep:suction-state: 0 silencioso, 1 estándar, 2 media, 3 turbo
SILENT = 0
MODE = (2, 4)                  # vacuum:mode: 0 aspirar, 1 aspirar y fregar, 2 fregar
SWEEP_ONLY = 0

# Ajustes originales mientras hay un "Ve" en curso (para no guardar los nuestros como originales)
_running = {"thread": None, "original": None}

# Hipótesis inicial: la orden usa milímetros con el mismo origen que la ruta.
# Se calibra mandándolo a un punto y comparando con dónde acaba en la ruta grabada.
DEFAULT_CONVERSION = {"escala": 1000, "dx": 0, "dy": 0}


def load_store():
    if PUNTOS.exists():
        return json.loads(PUNTOS.read_text())
    return {"conversion": DEFAULT_CONVERSION, "puntos": {}}


def save_store(store):
    PUNTOS.parent.mkdir(parents=True, exist_ok=True)
    PUNTOS.write_text(json.dumps(store, indent=2, ensure_ascii=False) + "\n")


def to_robot(store, x, y):
    c = store.get("conversion", DEFAULT_CONVERSION)
    return [round(x * c["escala"] + c["dx"]), round(y * c["escala"] + c["dy"])]


def go_to(name, raw=None):
    """Baja la potencia a silencioso, manda el robot al punto y graba la ruta en segundo plano.

    Al volver a la base (o a los 10 min) restaura la potencia que tenía.
    """
    store = load_store()
    if raw is not None:            # prueba de calibración: coordenadas ya en unidades del robot
        p, target = {"x": None, "y": None}, raw
    else:
        p = store["puntos"].get(name)
        if not p:
            raise KeyError(f"no hay ningún punto llamado '{name}'")
        target = to_robot(store, p["x"], p["y"])
    dev = connect()
    if _running["thread"] and _running["thread"].is_alive():
        original = _running["original"]
    else:
        original = {"suction": dev.get_property_by(*SUCTION)[0]["value"],
                    "mode": dev.get_property_by(*MODE)[0]["value"]}
        _running["original"] = original
    dev.set_property_by(*SUCTION, SILENT)
    dev.set_property_by(*MODE, SWEEP_ONLY)
    if store.get("metodo", "dos-pasos") == "dos-pasos":
        # Como lo hace la app según Home Assistant: fijar el destino y luego arrancar sin parámetros
        dev.set_property_by(*TARGET_POINT, json.dumps(target, separators=(",", ":")))
        res = dev.call_action_by(*START_POINT_CLEAN)
    else:
        res = dev.call_action_by(*START_POINT_CLEAN_II,
                                 [{"piid": TARGET_POINT_PIID, "value": json.dumps(target)}])
    path_file = DATA / f"ve-{time.strftime('%Y%m%d-%H%M%S')}-{name.replace('/', '_')}.jsonl"
    thread = threading.Thread(target=record_until_home, args=(dev, path_file, original), daemon=False)
    _running["thread"] = thread
    thread.start()
    return {"punto": name, "metros": [p["x"], p["y"]], "orden": target, "respuesta": res,
            "grabando": path_file.name, "thread": thread}


def record_until_home(dev, path_file, original, max_seconds=600):
    DATA.mkdir(parents=True, exist_ok=True)
    left_base, end, start = False, time.time() + max_seconds, time.time()
    with path_file.open("w") as out:
        while time.time() < end:
            status = safe_status(dev)
            record_path(dev, out)
            # La limpieza puntual sube la potencia a turbo al arrancar: la volvemos a bajar
            if time.time() - start < 60:
                try:
                    dev.set_property_by(*SUCTION, SILENT)
                except Exception:
                    pass
            if status != CHARGING:
                left_base = True
            elif left_base:
                break
            time.sleep(5)
    if _running["thread"] is not threading.current_thread():
        return  # otro "Ve" posterior se encarga de restaurar
    for _ in range(3):
        try:
            dev.set_property_by(*SUCTION, original["suction"])
            dev.set_property_by(*MODE, original["mode"])
            log(f"de vuelta; ajustes restaurados {original}. Ruta en {path_file.name}")
            return
        except Exception:
            time.sleep(3)
    log(f"no pude restaurar los ajustes {original}; ponlos a mano en la app")


def route_files():
    files = list(DATA.glob("paseo-*.jsonl")) + list(DATA.glob("ve-*.jsonl"))
    return [f.name for f in sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)]


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            body = (ROOT / "willy.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path == "/api/rutas":
            self._json(route_files())
        elif url.path == "/api/ruta":
            name = parse_qs(url.query).get("f", [None])[0] or (route_files() or [None])[0]
            if not name or "/" in name:
                return self._json({"tramos": []})
            segs = load_segments(DATA / name)
            self._json({"fichero": name, "tramos": [[[x, y] for x, y, _ in pts] for pts in segs.values()]})
        elif url.path == "/api/puntos":
            self._json(load_store())
        else:
            self._json({"error": "no existe"}, 404)

    def do_POST(self):
        url = urlparse(self.path)
        try:
            data = self._body()
            if url.path == "/api/puntos":
                store = load_store()
                store["puntos"][data["nombre"]] = {"x": round(data["x"], 3), "y": round(data["y"], 3)}
                save_store(store)
                self._json(store)
            elif url.path == "/api/borrar":
                store = load_store()
                store["puntos"].pop(data["nombre"], None)
                save_store(store)
                self._json(store)
            elif url.path == "/api/ve":
                res = go_to(data["nombre"])
                res.pop("thread")
                self._json(res)
            else:
                self._json({"error": "no existe"}, 404)
        except Exception as e:
            self._json({"error": str(e)}, 500)


def main():
    args = sys.argv[1:]
    if args[:1] == ["ve"] and len(args) > 1:
        res = go_to(" ".join(args[1:]))
        thread = res.pop("thread")
        print(json.dumps(res, ensure_ascii=False, indent=2))
        log("grabando hasta que vuelva a la base…")
        thread.join()
    elif args[:1] == ["ve-raw"] and len(args) == 3:
        x, y = int(args[1]), int(args[2])
        res = go_to(f"raw_{x}_{y}", raw=[x, y])
        thread = res.pop("thread")
        print(json.dumps(res, ensure_ascii=False, indent=2))
        log("grabando hasta que vuelva a la base…")
        thread.join()
    elif args[:1] == ["puntos"]:
        for name, p in load_store()["puntos"].items():
            print(f"{name:20} x={p['x']:.2f} m  y={p['y']:.2f} m")
    else:
        print(f"Willy en http://localhost:{PORT}  (Ctrl+C para parar)")
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
