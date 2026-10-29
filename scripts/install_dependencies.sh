#!/usr/bin/env bash
set -e

echo "=== Instalando dependencias para MemorizeIt (Python 3 / Raspberry Pi 4 / Ubuntu) ==="

sudo apt update
sudo apt install -y \
    python3 \
    python3-opencv \
    python3-pygame \
    python3-numpy \
    v4l-utils

echo ""
echo "=== Instalación de dependencias completada con éxito ==="
echo "Ahora puedes ejecutar el juego con:"
echo "  python3 main.py"
echo "O especificando la cámara USB directamente (ej. /dev/video2):"
echo "  python3 main.py --cam 2"
