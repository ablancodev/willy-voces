#!/usr/bin/env python3
"""Sets de voz para Willy: genera el audio con ElevenLabs y empaqueta en formato Ijai.

Cada set vive en voces/<set>/:
  frases.json   {"11sound_global_clean_start.mp3": "texto", ...}
  voz.json      {"voice_id", "model_id", "settings", "prefijo"}   (opcional, por defecto Bee enérgica;
                "prefijo" se antepone a cada frase, p. ej. una etiqueta de acento de eleven_v3)
  <set>.zip     el paquete listo para ./voz.py

Uso:  ./voces.py                 lista los sets
      ./voces.py crear <set>     genera los audios que falten y monta <set>.zip
      ./voces.py coste <set>     cuántos caracteres de ElevenLabs gastaría

El audio se cachea por texto en voces/_cache/, así que una frase repetida
o un set que reutiliza frases no vuelve a gastar caracteres.
"""
import concurrent.futures as cf
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent / "voces"
CACHE = ROOT / "_cache"
DEFAULT_VOICE = {
    "voice_id": "7ojlGL9bli0p29zYHSQ4",  # Bee
    "model_id": "eleven_multilingual_v2",
    "settings": {"stability": 0.25, "similarity_boost": 0.8, "style": 0.7, "use_speaker_boost": True},
    "prefijo": "",
}


def load_set(name):
    d = ROOT / name
    phrases = json.loads((d / "frases.json").read_text())
    voice = {**DEFAULT_VOICE, **(json.loads((d / "voz.json").read_text()) if (d / "voz.json").exists() else {})}
    return d, phrases, voice


def cache_path(voice, text):
    parts = [voice["voice_id"], voice["model_id"], voice["settings"], text]
    if voice.get("prefijo"):
        parts.append(voice["prefijo"])
    key = json.dumps(parts, sort_keys=True)
    return CACHE / f"{hashlib.md5(key.encode()).hexdigest()}.mp3"


def tts(voice, text):
    out = cache_path(voice, text)
    if out.exists() and out.stat().st_size > 1000:
        return text, "cache"
    body = {"text": voice.get("prefijo", "") + text, "model_id": voice["model_id"], "voice_settings": voice["settings"]}
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice['voice_id']}?output_format=mp3_44100_128",
        data=json.dumps(body).encode(),
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json"},
        method="POST")
    err = ""
    for _ in range(3):
        try:
            out.write_bytes(urllib.request.urlopen(req, timeout=90).read())
            return text, "nueva"
        except Exception as e:
            err = str(e)
    return text, f"ERROR {err}"


def cost(name):
    _, phrases, voice = load_set(name)
    pending = {t for t in phrases.values() if not cache_path(voice, t).exists()}
    return len(pending), sum(len(voice.get("prefijo", "")) + len(t) for t in pending)


def build(name):
    d, phrases, voice = load_set(name)
    CACHE.mkdir(parents=True, exist_ok=True)
    with cf.ThreadPoolExecutor(3) as ex:
        results = list(ex.map(lambda t: tts(voice, t), sorted(set(phrases.values()))))
    errors = [r for r in results if r[1].startswith("ERROR")]
    if errors:
        sys.exit(f"{len(errors)} frases fallaron: {errors[:3]}")
    print(f"audio: {sum(r[1] == 'nueva' for r in results)} nuevas, {sum(r[1] == 'cache' for r in results)} de caché")

    work = d / "paquete"
    work.mkdir(exist_ok=True)
    md5_lines = []
    for fname, text in sorted(phrases.items()):
        dst = work / fname
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(cache_path(voice, text)),
                        "-ar", "44100", "-ac", "2", "-b:a", "96k", "-map_metadata", "-1", str(dst)], check=True)
        md5_lines += [f"[{fname}]", f"MD5={hashlib.md5(dst.read_bytes()).hexdigest()}", ""]
    (work / "md5.ini").write_text("\n".join(md5_lines) + "\n")

    pack = d / f"{name}.zip"
    with zipfile.ZipFile(pack, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(work.iterdir()):
            z.write(f, f.name)
    print(f"{pack}  ({len(phrases)} archivos + md5.ini, {pack.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["crear"] and len(args) == 2:
        build(args[1])
    elif args[:1] == ["coste"] and len(args) == 2:
        n, chars = cost(args[1])
        print(f"{args[1]}: {n} frases por generar, {chars} caracteres")
    else:
        for d in sorted(p for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith("_")):
            zips = list(d.glob("*.zip"))
            print(f"{d.name:12} {'listo: ' + zips[0].name if zips else 'sin paquete'}")
