#!/usr/bin/env python3
"""Paseo: el robot sale de la base, da una vuelta y vuelve.

Uso:  ./paseo.py            (vuelta de 40 s)
      ./paseo.py 90         (vuelta de 90 s)
      ./paseo.py --estado   (solo leer estado, no se mueve)

Ctrl+C en cualquier momento lo manda de vuelta a la base.
"""
import json
import os
import sys
import time
from pathlib import Path

from miio import MiotDevice

# IDs MIoT del S12 (xiaomi.vacuum.b106eu), sacados de `miiocli genericmiot actions/status`
STATUS = (2, 1)          # vacuum:status
BATTERY = (3, 1)         # battery:battery-level
START_ONLY_SWEEP = (2, 3)  # aspirar sin fregar
GO_CHARGING = (3, 1)     # battery:start-charge
GET_CUR_PATH = (10, 12)  # map:get-cur-path(start, end) -> cur-cleaning-path
CHARGING = 4


def load_env():
    for line in (Path(__file__).parent / ".env").read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def discover(did, timeout=5):
    """Busca el robot por su ID con un "hello" miIO a toda la red; devuelve su IP o None."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(1)
    hello = bytes.fromhex("21310020" + "ff" * 28)
    for _ in range(3):
        s.sendto(hello, ("255.255.255.255", 54321))
    end = time.time() + timeout
    while time.time() < end:
        try:
            data, (ip, _) = s.recvfrom(1024)
        except socket.timeout:
            continue
        if int.from_bytes(data[8:12], "big") == did:
            return ip
    return None


def connect():
    """Conecta con el robot; si no responde en su IP (el router se la cambia), lo busca y actualiza .env."""
    load_env()
    ip = os.environ["MIIO_IP"]
    dev = MiotDevice(ip, os.environ["MIIO_TOKEN"], model=os.environ.get("MIIO_MODEL"), timeout=5)
    try:
        dev.send_handshake()
        return dev
    except Exception:
        if "MIIO_DID" not in os.environ:
            return dev
    new_ip = discover(int(os.environ["MIIO_DID"]))
    if not new_ip or new_ip == ip:
        return dev
    log(f"el robot ha cambiado de IP: {ip} -> {new_ip}; actualizo .env")
    env = Path(__file__).parent / ".env"
    env.write_text("".join(f"MIIO_IP={new_ip}\n" if l.startswith("MIIO_IP=") else l + "\n"
                           for l in env.read_text().splitlines()))
    os.environ["MIIO_IP"] = new_ip
    return MiotDevice(new_ip, os.environ["MIIO_TOKEN"], model=os.environ.get("MIIO_MODEL"), timeout=5)


def read(dev, siid_piid, retries=3):
    for i in range(retries):
        try:
            return dev.get_property_by(*siid_piid)[0]["value"]
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2)


def record_path(dev, out):
    """Guarda en bruto lo que devuelve get-cur-path, para dibujar el mapa luego."""
    try:
        res = dev.call_action_by(*GET_CUR_PATH, [{"piid": 15, "value": 0}, {"piid": 16, "value": 100000}])
        out.write(json.dumps({"t": time.time(), "res": res}) + "\n")
        out.flush()
    except Exception as e:
        out.write(json.dumps({"t": time.time(), "error": str(e)}) + "\n")


def safe_status(dev):
    try:
        return read(dev, STATUS)
    except Exception as e:
        return f"? ({e.__class__.__name__})"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    dev = connect()
    battery, status = read(dev, BATTERY), read(dev, STATUS)
    log(f"batería {battery} %, estado {status}" + (" (cargando)" if status == CHARGING else ""))
    if "--estado" in sys.argv:
        return
    if battery < 30:
        log("poca batería, mejor otro rato")
        return

    seconds = int(next((a for a in sys.argv[1:] if a.isdigit()), 40))
    path_file = Path(__file__).parent / "data" / "rutas" / f"paseo-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    path_file.parent.mkdir(parents=True, exist_ok=True)
    out = path_file.open("w")
    try:
        log(f"sale de la base, vuelta de {seconds} s")
        dev.call_action_by(*START_ONLY_SWEEP)
        end = time.time() + seconds
        while time.time() < end:
            time.sleep(5)
            log(f"  estado {safe_status(dev)}")
            record_path(dev, out)
    except KeyboardInterrupt:
        log("interrumpido")
    finally:
        log("vuelve a la base")
        dev.call_action_by(*GO_CHARGING)

    deadline = time.time() + 180
    while time.time() < deadline:
        time.sleep(5)
        status = safe_status(dev)
        log(f"  estado {status}")
        record_path(dev, out)
        if status == CHARGING:
            log(f"en la base, cargando. Fin del paseo. Ruta en {path_file.name}")
            return
    log("no ha llegado a la base en 3 min: míralo en la app")


if __name__ == "__main__":
    main()
