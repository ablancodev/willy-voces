#!/usr/bin/env python3
"""Instala un paquete de voz propio en el robot, servido desde este Mac.

Uso:  ./voz.py heroe               instala el set voces/heroe/heroe.zip
      ./voz.py borde               instala el set voces/borde/borde.zip
      ./voz.py estado              solo muestra la voz actual
      ./voz.py <archivo> <nombre>  instala otro paquete con otro nombre
      (los sets se crean con ./voces.py)

Levanta un servidor web temporal en el puerto 8800, pide al robot que se descargue
el paquete (download-voice) y sigue el progreso (get-download-status).
"""
import hashlib
import socket
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from paseo import connect, log

ROOT = Path(__file__).parent
PORT = 8800
DOWNLOAD_VOICE = (14, 1)        # in: target-voice (1), voice-url (5), voice-mdfive (6)
GET_DOWNLOAD_STATUS = (14, 2)   # out: target-voice, cur-voice, download-status, download-progress


def local_ip(robot_ip):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((robot_ip, 54321))
    return s.getsockname()[0]


served = threading.Event()  # el robot ya ha descargado el paquete


class LoggingHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log(f"  servidor: {self.client_address[0]} {fmt % args}")
        if " 200 " in f" {fmt % args} ":
            served.set()


def status(dev, retries=4):
    for i in range(retries):
        res = dev.call_action_by(*GET_DOWNLOAD_STATUS)
        if "out" in res:
            break
        time.sleep(2)
    else:
        return {"sin respuesta": res}
    out = {o["piid"]: o["value"] for o in res["out"]}
    return {"destino": out.get(1), "actual": out.get(2), "estado": out.get(3), "progreso": out.get(4)}


def main():
    args = sys.argv[1:]
    dev = connect()
    if args[:1] == ["estado"]:
        log(status(dev))
        return

    choice = args[0] if args else "heroe"
    set_zip = ROOT / "voces" / choice / f"{choice}.zip"
    pack = set_zip if set_zip.exists() else Path(choice)
    name = args[1] if len(args) > 1 else "es_ES"
    md5 = hashlib.md5(pack.read_bytes()).hexdigest()

    ip = local_ip(dev.ip)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), partial(LoggingHandler, directory=str(pack.parent)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://{ip}:{PORT}/{pack.name}"

    log(f"antes: {status(dev)}")
    log(f"pidiendo al robot que descargue {url} (md5 {md5}) como '{name}'")
    res = dev.call_action_by(*DOWNLOAD_VOICE, [
        {"piid": 1, "value": name},
        {"piid": 5, "value": url},
        {"piid": 6, "value": md5},
    ])
    log(f"respuesta: {res}")

    last, end = None, time.time() + 180
    while time.time() < end:
        time.sleep(3)
        try:
            st = status(dev)
        except Exception as e:
            log(f"  (lectura fallida: {e.__class__.__name__})")
            continue
        if "sin respuesta" in st:
            continue
        if st != last:
            log(f"  {st}")
            last = st
        if st["actual"] == name and st["progreso"] in (0, 100) and served.is_set():
            log("¡voz instalada!")
            break
    server.shutdown()


if __name__ == "__main__":
    main()
