# MemorizeIt - Among Us Reactor Memory Game (Raspberry Pi 4)

Videojuego de memoria en cuadrícula 3x3 estilo el minijuego de Reactor de **Among Us**, desarrollado en **Python 3** con **Pygame**, **OpenCV** y **NumPy**, optimizado específicamente para ejecutarse de forma liviana y fluida en una **Raspberry Pi 4** utilizando una cámara USB.

---

## 🎮 Mecánica de Juego

1. **Ronda 1:** Brilla 1 panel y se emite su sonido característico.
2. **Turno del Jugador:** Una vez concluida la secuencia, el jugador coloca su dedo frente a la cámara sobre el panel correspondiente.
3. **Activación de 2 Segundos (*Dwell Time*):** 
   * Para evitar pulsaciones involuntarias al cruzar la mano, el jugador debe **mantener el dedo sobre el panel durante al menos 2 segundos continuos**.
   * Se muestra un **anillo de carga y cuenta regresiva visual** (`1.8s / 2.0s`) alrededor del dedo, y una barra de energía interna que llena el panel.
4. **Ronda 2 a 5:** En cada ronda subsecuente se repite la secuencia previa y se añade un nuevo panel.
5. **Victoria/Derrota:** 
   * Si pulsas un panel incorrecto: alarma roja y repetición de la ronda actual.
   * Al superar la Ronda 5: Desbloqueo del reactor (*Task Completed*).

---

## ⚡ Visión Artificial Optimizada para Raspberry Pi 4

1. **Captura Multihilo Desacoplada (`threading.Thread`):**
   * El hilo de visión lee a través de `V4L2` con compresión de hardware `MJPG` a 640x480 @ 30 FPS sin bloquear la tasa de refresco del juego (60 FPS en Pygame).
2. **Detección Exclusiva del DEDO (Supresión Total del Rostro):**
   * Un clasificador en segundo plano detecta si hay un rostro en el encuadre y **lo borra en negro absoluto de la máscara de visión**.
   * En la miniatura inferior verás que cualquier rostro se marca en rojo con la advertencia `"ROSTRO IGNORADO"`.
   * El juego únicamente sigue la mano y extrae la punta del dedo índice en verde brillante (`"DEDO"`).
3. **Autodetección y Cambio de Cámara USB:**
   * Prioriza automáticamente la cámara USB externa (`/dev/video2`).
   * Puedes alternar entre cámaras en caliente en cualquier momento presionando la tecla **`C`**.
4. **Audio Procedural en Memoria:**
   * Síntesis senoidal pura de ondas en NumPy (Do4 a Re5, chime de éxito y buzzer de error). Cero dependencias de archivos de sonido externos.
5. **Modo Ratón / Pruebas:**
   * Si no tienes cámara conectada, puedes probar el juego haciendo clic sostenido con el ratón durante 2 segundos.

---

## 📦 Instalación

Ejecuta el script de instalación para instalar OpenCV, Pygame y NumPy desde los repositorios del sistema:

```bash
chmod +x scripts/install_python_dependencies.sh
./scripts/install_python_dependencies.sh
```

*(O manualmente vía APT: `sudo apt install -y python3-opencv python3-pygame python3-numpy v4l-utils`)*

O mediante un entorno virtual con `pip`:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 🚀 Ejecución

Lanzar el juego con detección automática de cámara:
```bash
python3 main.py
```

O forzando el índice de tu cámara USB externa (ej. índice 2):
```bash
python3 main.py --cam 2
```

*(Recuerda que dentro del juego puedes pulsar la tecla **`C`** para alternar de cámara si lo deseas).*

---

## 📁 Estructura del Proyecto

* [`main.py`](file:///home/andres/Documents/OwnProjects/MemorizeIt-Raspberry/main.py): Punto de entrada, ventana de Pygame y bucle a 60 FPS.
* [`memorizeit/vision.py`](file:///home/andres/Documents/OwnProjects/MemorizeIt-Raspberry/memorizeit/vision.py): Hilo V4L2, supresión activa de rostros, segmentación de dedo índice por contorno y suavizado.
* [`memorizeit/game.py`](file:///home/andres/Documents/OwnProjects/MemorizeIt-Raspberry/memorizeit/game.py): Máquina de estados, lógica de rondas 1 a 5 y control del temporizador de 2 segundos.
* [`memorizeit/grid.py`](file:///home/andres/Documents/OwnProjects/MemorizeIt-Raspberry/memorizeit/grid.py): Cuadrícula 3x3 interactiva con llenado visual de energía durante la carga.
* [`memorizeit/audio.py`](file:///home/andres/Documents/OwnProjects/MemorizeIt-Raspberry/memorizeit/audio.py): Síntesis en memoria de los 9 tonos y efectos sonoros con NumPy.
