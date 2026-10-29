#!/usr/bin/env bash
set -e

echo "=== 1. Instalando dependencias del sistema y OpenCV vía APT ==="

# Actualizar e instalar OpenCV y herramientas de compilación
# Nota: libraylib-dev no existe en todos los repositorios oficiales de Ubuntu/Debian,
# por lo que instalamos las librerías gráficas necesarias y configuramos Raylib automáticamente.
sudo apt update
sudo apt install -y \
    build-essential \
    g++ \
    make \
    pkg-config \
    libopencv-dev \
    libgl1-mesa-dev \
    libglu1-mesa-dev \
    libasound2-dev \
    libx11-dev \
    libxrandr-dev \
    libxi-dev \
    libxcursor-dev \
    libxinerama-dev \
    v4l-utils \
    curl \
    tar

echo "=== 2. Configurando Raylib automáticamente ==="

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
THIRD_PARTY_DIR="$PROJECT_DIR/third_party"
mkdir -p "$THIRD_PARTY_DIR"

ARCH=$(uname -m)
echo "Arquitectura detectada: $ARCH"

RAYLIB_VERSION="6.2"

if [ "$ARCH" = "x86_64" ]; then
    RAYLIB_PKG="raylib-${RAYLIB_VERSION}_linux_amd64.tar.gz"
elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    RAYLIB_PKG="raylib-${RAYLIB_VERSION}_linux_arm64.tar.gz"
elif [ "$ARCH" = "i386" ] || [ "$ARCH" = "i686" ]; then
    RAYLIB_PKG="raylib-${RAYLIB_VERSION}_linux_i386.tar.gz"
else
    echo "Arquitectura no estándar para binarios precompilados ($ARCH). Se compilará desde código fuente..."
    RAYLIB_PKG=""
fi

cd "$THIRD_PARTY_DIR"

if [ -n "$RAYLIB_PKG" ]; then
    echo "Descargando Raylib $RAYLIB_VERSION para $ARCH..."
    curl -L -o raylib.tar.gz "https://github.com/raysan5/raylib/releases/download/${RAYLIB_VERSION}/${RAYLIB_PKG}"
    rm -rf raylib
    tar -xzf raylib.tar.gz
    mv "raylib-${RAYLIB_VERSION}_linux_"* raylib
    rm -f raylib.tar.gz
else
    # Compilación desde código fuente para otras variantes de Raspberry Pi (ej. armv7l 32-bit)
    if [ ! -d "raylib_src" ]; then
        git clone --depth 1 https://github.com/raysan5/raylib.git raylib_src
    fi
    cd raylib_src/src
    make PLATFORM=PLATFORM_DESKTOP RAYLIB_LIBTYPE=STATIC -j$(nproc)
    mkdir -p "$THIRD_PARTY_DIR/raylib/include" "$THIRD_PARTY_DIR/raylib/lib"
    cp raylib.h raymath.h rlgl.h "$THIRD_PARTY_DIR/raylib/include/"
    cp libraylib.a "$THIRD_PARTY_DIR/raylib/lib/"
    cd "$THIRD_PARTY_DIR"
fi

echo "=== Instalación completada con éxito ==="
echo "Ahora puedes compilar ejecutando:"
echo "  make"
echo "Y lanzar el juego con:"
echo "  ./bin/memorizeit"
