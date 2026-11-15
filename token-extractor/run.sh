#!/usr/bin/env bash
# Saca token y modelo de los dispositivos de tu cuenta Mi Home.
# Ejecútalo en tu propia terminal (es interactivo: pide usuario/contraseña).
# Fuente: github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor @ c4db715
set -euo pipefail
cd "$(dirname "$0")"
docker build -q -t willy-token-extractor . >/dev/null
docker run --rm -it -p 31415:31415 willy-token-extractor "$@"
