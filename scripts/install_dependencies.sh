#!/usr/bin/env bash
set -e

echo "=== Instalando dependencias de C++ para MemorizeIt (Raspberry Pi 4 / Ubuntu) ==="

sudo apt update
sudo apt install -y \
    build-essential \
    g++ \
    make \
    pkg-config \
    libopencv-dev \
    libraylib-dev \
    libgl1-mesa-dev \
    libx11-dev \
    v4l-utils

echo "=== Instalación de dependencias completada con éxito ==="
echo "Ahora puedes compilar ejecutando:"
echo "  make"
echo "Y lanzar el juego con:"
echo "  ./bin/memorizeit"
