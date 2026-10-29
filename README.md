# MemorizeIt - Among Us Reactor Memory Game (Raspberry Pi 4)

Videojuego de memoria en cuadrícula 3x3 estilo el minijuego de Reactor de **Among Us**, desarrollado íntegramente en **Python 3** con **Pygame**, **OpenCV** y **NumPy**, optimizado específicamente para ejecutarse de forma liviana y fluida en una **Raspberry Pi 4** con una cámara USB.

---

## 🎮 Mecánica de Juego

1. **Ronda 1:** Brilla 1 panel y se reproduce su sonido característico.
2. **Turno del Jugador:** Una vez concluida la secuencia, el jugador coloca su dedo frente a la cámara sobre el panel correspondiente.
3. **Activación de 2 Segundos (*Dwell Time*):** 
   * Para evitar pulsaciones involuntarias al mover la mano por la cuadrícula, se debe **mantener el dedo sobre el panel durante al menos 2.0 segundos continuos**.
   * Se muestra un **anillo de carga y cuenta regresiva visual** (`1.8s / 2.0s`) alrededor del dedo, junto a una barra de energía interna que llena el panel.
4. **Ronda 2 a 5:** En cada ronda subsecuente se repite la secuencia acumulada y se añade un nuevo panel.
5. **Victoria/Derrota:** 
   * Si pulsas un panel incorrecto: alarma roja y repetición de la ronda actual.
   * Al superar la Ronda 5: Desbloqueo del reactor (*Task Completed*).

---

## ⚡ Visión Artificial Optimizada para Raspberry Pi 4

1. **Captura Multihilo Desacoplada (`threading.Thread`):**
   * El hilo de visión captura a través de `V4L2` con compresión de hardware `MJPG` a 640x480 @ 30 FPS sin bloquear la tasa de refresco del juego (60 FPS en Pygame).
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
   * Si no tienes cámara conectada, puedes probar el juego manteniendo presionado el clic del ratón durante 2 segundos.

---

## 📦 Instalación

Ejecuta el script de instalación automática:

```bash
chmod +x scripts/install_dependencies.sh
./scripts/install_dependencies.sh
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

*(Recuerda que dentro del juego puedes presionar la tecla **`C`** para alternar de cámara si lo deseas).*

---

## 📁 Estructura del Proyecto

```
.
├── main.py                     # Punto de entrada y loop a 60 FPS con Pygame
├── memorizeit/
│   ├── __init__.py
│   ├── audio.py                # Síntesis matemática de audio procedural con NumPy
│   ├── game.py                 # Máquina de estados (rondas 1 a 5) y temporizador de 2s
│   ├── grid.py                 # Cuadrícula 3x3 estilo Among Us con carga visual
│   └── vision.py               # Hilo V4L2, supresión de rostro y tracking de dedo
├── scripts/
│   └── install_dependencies.sh # Script de instalación de dependencias del sistema
├── requirements.txt            # Dependencias Python para pip
└── README.md
```
