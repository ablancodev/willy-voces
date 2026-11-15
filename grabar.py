#!/usr/bin/env python3
"""Graba la ruta sin mandar órdenes: para limpiezas lanzadas desde la app o el botón.

Uso:  ./grabar.py          (graba hasta que vuelve a cargar, máx. 30 min)
Ctrl+C para parar. Luego ./mapa.py para dibujarla.
"""
import time
from pathlib import Path

from paseo import CHARGING, connect, log, record_path, safe_status

MAX_SECONDS = 30 * 60


def main():
    dev = connect()
    path_file = Path(__file__).parent / "data" / "rutas" / f"paseo-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    path_file.parent.mkdir(parents=True, exist_ok=True)
    left_base = False
    end = time.time() + MAX_SECONDS
    with path_file.open("w") as out:
        log(f"grabando en {path_file.name}")
        try:
            while time.time() < end:
                status = safe_status(dev)
                record_path(dev, out)
                log(f"  estado {status}")
                if status != CHARGING:
                    left_base = True
                elif left_base:
                    log("de vuelta en la base. Fin.")
                    break
                time.sleep(5)
        except KeyboardInterrupt:
            log("parado")


if __name__ == "__main__":
    main()
