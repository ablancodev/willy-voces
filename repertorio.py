#!/usr/bin/env python3
"""Repertorio: la misma mini limpieza con cada voz, para grabar un vídeo comparando.

Para cada voz: la instala, dice "aquí estoy", sale de la base aspirando unos segundos,
pausa, vuelve a la base y espera a que cargue. Orden por defecto:
original (inglés de fábrica) → héroe → borde → andaluz.

Uso:  ./repertorio.py                     todas, 8 s de limpieza cada una
      ./repertorio.py 5                   5 s de limpieza
      ./repertorio.py 8 original andaluz  solo esas voces, en ese orden

Ctrl+C: manda el robot a la base y termina.
"""
import hashlib
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from paseo import BATTERY, CHARGING, GO_CHARGING, START_ONLY_SWEEP, connect, log, safe_status
from voz import DOWNLOAD_VOICE, PORT, local_ip

VOCES = Path(__file__).parent / "voces"
STOP = (2, 2)        # vacuum:stop-sweeping (en pausa)
ALARM = (4, 1)       # "buscar robot": dice "aquí estoy"
ORIGINAL = "original"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def retry(fn, tries=3):
    for i in range(tries):
        try:
            return fn()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2)


def install(dev, voice, base_url):
    if voice == ORIGINAL:
        params = [{"piid": 1, "value": "en_US"}, {"piid": 5, "value": ""}, {"piid": 6, "value": ""}]
    else:
        pack = VOCES / voice / f"{voice}.zip"
        params = [{"piid": 1, "value": "es_ES"},
                  {"piid": 5, "value": f"{base_url}/{voice}/{voice}.zip"},
                  {"piid": 6, "value": hashlib.md5(pack.read_bytes()).hexdigest()}]
    retry(lambda: dev.call_action_by(*DOWNLOAD_VOICE, params))
    time.sleep(4)


def wait_home(dev, max_seconds=120):
    end = time.time() + max_seconds
    while time.time() < end:
        time.sleep(3)
        if safe_status(dev) == CHARGING:
            return True
    return False


def show(dev, voice, seconds):
    log(f"=== {voice.upper()} ===")
    retry(lambda: dev.set_property_by(*ALARM, True))   # "aquí estoy"
    time.sleep(5)
    log("sale a limpiar")
    retry(lambda: dev.call_action_by(*START_ONLY_SWEEP))
    time.sleep(seconds)
    log("pausa")
    retry(lambda: dev.call_action_by(*STOP))
    time.sleep(4)
    log("vuelve a la base")
    retry(lambda: dev.call_action_by(*GO_CHARGING))
    if wait_home(dev):
        log("en la base, cargando")
    else:
        log("no ha llegado a la base en 2 min; sigo igualmente")
    time.sleep(4)


def main():
    args = sys.argv[1:]
    seconds = int(args.pop(0)) if args and args[0].isdigit() else 8
    voices = args or [ORIGINAL, "heroe", "borde", "andaluz"]
    for v in voices:
        if v != ORIGINAL and not (VOCES / v / f"{v}.zip").exists():
            sys.exit(f"no existe el set '{v}' (créalo con ./voces.py crear {v})")

    dev = connect()
    battery = retry(lambda: dev.get_property_by(*BATTERY)[0]["value"])
    if battery < 30:
        sys.exit(f"batería al {battery} %: mejor cargar antes")
    server = ThreadingHTTPServer(("0.0.0.0", PORT), partial(QuietHandler, directory=str(VOCES)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://{local_ip(dev.ip)}:{PORT}"
    log(f"repertorio: {' → '.join(voices)}, {seconds} s de limpieza cada una (batería {battery} %)")

    try:
        for v in voices:
            install(dev, v, base_url)
            show(dev, v, seconds)
        log("fin del repertorio")
    except KeyboardInterrupt:
        log("parado: vuelve a la base")
        retry(lambda: dev.call_action_by(*GO_CHARGING))
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
