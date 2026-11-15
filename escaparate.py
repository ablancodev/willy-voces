#!/usr/bin/env python3
"""Escaparate: el robot dice todas las frases de un set sin moverse de la base.

Truco: no hay orden para reproducir un audio cualquiera, pero "buscar robot" reproduce
43sound_I_am_here.mp3. Para cada frase se instala el set con ese archivo cambiado por
la frase, se lanza "buscar robot" y se pasa a la siguiente. Al acabar se reinstala el set original.

Uso:  ./escaparate.py borde              todas las frases del set
      ./escaparate.py borde 5            solo las 5 primeras (prueba)
"""
import hashlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from paseo import connect, log
from voz import DOWNLOAD_VOICE, PORT, local_ip

ROOT = Path(__file__).parent / "voces"
I_AM_HERE = "43sound_I_am_here.mp3"
ALARM = (4, 1)
VOICE_NAME = "es_ES"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return float(out.strip() or 4)


def make_zip(src_dir, swap, dest):
    """Copia del paquete con 43sound_I_am_here.mp3 sustituido por `swap`, y md5.ini recalculado."""
    files = sorted(p for p in src_dir.iterdir() if p.suffix == ".mp3")
    md5_lines = []
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            data = (swap if f.name == I_AM_HERE else f).read_bytes()
            z.writestr(f.name, data)
            md5_lines += [f"[{f.name}]", f"MD5={hashlib.md5(data).hexdigest()}", ""]
        z.writestr("md5.ini", "\n".join(md5_lines) + "\n")


def install(dev, url, pack):
    md5 = hashlib.md5(pack.read_bytes()).hexdigest()
    for _ in range(3):
        try:
            dev.call_action_by(*DOWNLOAD_VOICE, [
                {"piid": 1, "value": VOICE_NAME}, {"piid": 5, "value": url}, {"piid": 6, "value": md5}])
            return True
        except Exception:
            time.sleep(2)
    return False


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "borde"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    set_dir = ROOT / name
    src = set_dir / "paquete"
    import json
    phrases = json.loads((set_dir / "frases.json").read_text())
    order = sorted(phrases, key=lambda f: (f[0].isdigit() is False, int("".join(c for c in f if c.isdigit()) or 0)))
    seen, items = set(), []
    for f in order:                     # una vez por texto distinto
        if phrases[f] not in seen:
            seen.add(phrases[f])
            items.append(f)
    items = items[:limit] if limit else items

    dev = connect()
    tmp = Path(tempfile.mkdtemp(prefix="escaparate-"))
    server = ThreadingHTTPServer(("0.0.0.0", PORT), partial(QuietHandler, directory=str(tmp)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://{local_ip(dev.ip)}:{PORT}"
    try:
        for i, f in enumerate(items, 1):
            pack = tmp / f"frase-{i}.zip"
            make_zip(src, src / f, pack)
            if not install(dev, f"{base}/{pack.name}", pack):
                log(f"{i}/{len(items)} {f}: no se pudo instalar, salto")
                continue
            time.sleep(3)
            try:
                dev.set_property_by(*ALARM, True)
            except Exception:
                time.sleep(2)
                dev.set_property_by(*ALARM, True)
            log(f"{i}/{len(items)} {f}: {phrases[f]}")
            time.sleep(duration(src / f) + 1.5)
            pack.unlink()
    except KeyboardInterrupt:
        log("parado")
    finally:
        log(f"reinstalando el set '{name}' original")
        pack = set_dir / f"{name}.zip"
        shutil.copy(pack, tmp / pack.name)
        install(dev, f"{base}/{pack.name}", tmp / pack.name)
        time.sleep(4)
        server.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
