# MemorizeIt - Among Us Reactor Memory Game (Raspberry Pi 4)

Videojuego de memoria en cuadrícula 3x3 estilo el minijuego de Reactor de **Among Us**, desarrollado en **C++17** con **Raylib** y **OpenCV**, optimizado específicamente para ejecutarse de forma fluida (60 FPS) en una **Raspberry Pi 4** con una cámara USB estándar.

---

## 🎮 Mecánica de Juego

1. **Ronda 1:** Brilla 1 panel y se emite su sonido característico.
2. **Turno del Jugador:** Una vez concluida la secuencia, el jugador coloca su dedo frente a la cámara sobre el panel que brilló. Al mantener el dedo sobre el botón durante un breve instante (*dwell time*), se registra la pulsación.
3. **Ronda 2 a 5:** En cada ronda subsecuente se repite la secuencia acumulada y se añade un nuevo panel.
4. **Victoria/Derrota:** 
   * Si pulsas un panel incorrecto: alarma roja y reinicio de la ronda actual.
   * Al superar la Ronda 5: Desbloqueo del reactor (*Task Completed*).

---

## ⚡ Optimizaciones para Raspberry Pi 4

1. **Pipeline Desacoplado Multihilo:**
   * **Hilo de Visión:** Captura continua a 320x240 @ 30 FPS vía `V4L2` con compresión `MJPG` por hardware para no sobrecargar el bus USB ni acumular buffer lag.
   * **Hilo de Renderizado / Juego:** Bucle principal a 60 FPS acelerado por hardware con Raylib (OpenGL ES).
2. **Detección Geométrica Ultra-ligera:**
   * En lugar de modelos pesados de Deep Learning que sobrecalientan la Pi, utiliza segmentación HSV y detección del extremo superior del contorno de la mano con suavizado exponencial.
3. **Audio Procedural:**
   * Tonos musicales y efectos sonoros generados en memoria mediante síntesis de ondas (sin depender de archivos `.wav` externos).
4. **Modo Espejo:**
   * La vista de cámara se invierte horizontalmente para que la interacción motriz sea 100% natural.
5. **Modo Ratón / Pruebas:**
   * Si no tienes cámara conectada al desarrollar en tu PC, puedes jugar y probar haciendo clic con el ratón.

---

## 📦 Instalación de Dependencias

Ejecuta el script automatizado (requiere permisos sudo):

```bash
chmod +x scripts/install_dependencies.sh
./scripts/install_dependencies.sh
```

O instala los paquetes manualmente:

```bash
sudo apt update
sudo apt install -y build-essential g++ make pkg-config libopencv-dev libraylib-dev libgl1-mesa-dev libx11-dev v4l-utils
```

---

## 🚀 Compilación y Ejecución

Compila con optimizaciones `-O3`:

```bash
make
```

Ejecuta el juego:

```bash
./bin/memorizeit
```

O compila y ejecuta en un solo paso:

```bash
make run
```

---

## 📁 Estructura del Proyecto

* [`include/VisionTracker.hpp`](file:///home/andres/Documents/OwnProjects/MemorizeIt-Raspberry/include/VisionTracker.hpp) / [`src/VisionTracker.cpp`](file:///home/andres/Documents/OwnProjects/MemorizeIt-Raspberry/src/VisionTracker.cpp): Captura V4L2 en hilo dedicado, detección de dedo por contornos, cálculo de coordenadas normalizadas y vista previa RGB.
* [`include/GridPanel.hpp`](file:///home/andres/Documents/OwnProjects/MemorizeIt-Raspberry/include/GridPanel.hpp) / [`src/GridPanel.cpp`](file:///home/andres/Documents/OwnProjects/MemorizeIt-Raspberry/src/GridPanel.cpp): Cuadrícula 3x3 con animaciones de brillo cian, verde de acierto y rojo de fallo.
* [`include/SoundSystem.hpp`](file:///home/andres/Documents/OwnProjects/MemorizeIt-Raspberry/include/SoundSystem.hpp) / [`src/SoundSystem.cpp`](file:///home/andres/Documents/OwnProjects/MemorizeIt-Raspberry/src/SoundSystem.cpp): Síntesis procedural de frecuencias para cada botón, sonido de acierto y zumbador de error.
* [`include/GameEngine.hpp`](file:///home/andres/Documents/OwnProjects/MemorizeIt-Raspberry/include/GameEngine.hpp) / [`src/GameEngine.cpp`](file:///home/andres/Documents/OwnProjects/MemorizeIt-Raspberry/src/GameEngine.cpp): Máquina de estados del reactor, gestión de turnos, lógica de *dwell time* y progreso.
* [`src/main.cpp`](file:///home/andres/Documents/OwnProjects/MemorizeIt-Raspberry/src/main.cpp): Ventana Raylib y bucle principal a 60 FPS.
