# MemorizeIt - Among Us Reactor Memory Game (Raspberry Pi 4)

Videojuego de memoria en cuadrícula 3x3 estilo el minijuego de Reactor de **Among Us**, desarrollado en **Python** con **Pygame** y el **motor de visión artificial de MazeHaus** (Google MediaPipe Hand Landmarker + OpenCV CLAHE de respaldo), optimizado para una **Raspberry Pi 4** con cámara USB.

---

## 🎮 Mecánica de Juego

1. **Inicio con Dedo en el Centro (5 segundos):**
   * El juego inicia en modo de espera. Coloca la punta de tu dedo índice en el **círculo central de la cámara** durante **5 segundos**.
   * Un anillo de progreso y beeps cuentan hasta el inicio (también puedes presionar **`Espacio`** para iniciar de inmediato).
2. **Juego Infinito:**
   * Cada ronda superada añade un nuevo paso a la secuencia sin límite (Ronda 1 a $\infty$).
3. **Pulsación de 2 Segundos (*Dwell Time*):**
   * Mantén tu dedo índice apuntando al panel correspondiente durante **2.0 segundos continuos** hasta que se cargue la barra de energía.
4. **Game Over y Récords:**
   * Si fallas, el reactor se bloquea con alarma roja, anuncia **GAME OVER**, guarda tu mejor ronda en `highscores.json` y vuelve al modo de espera.

---

## ⚡ Motor de Visión Artificial (Adaptado de MazeHaus)

1. **Google MediaPipe Hand Landmarker (Tasks API con aceleración XNNPACK):**
   * Utiliza el modelo neuronal [`models/hand_landmarker.task`](file:///home/andres/Documents/OwnProjects/MemorizeIt-Raspberry/models/hand_landmarker.task) para rastrear con precisión sub-milimétrica los 21 puntos articulares de la mano.
   * **El rostro es 100% inmune:** El modelo busca exclusivamente anatomía de manos y dedos, ignorando totalmente la cara, orejas y hombros.
   * Rastrear específicamente el **Landmark 8** (punta del dedo índice) y detecta si el dedo está extendido.
   * Muestra el esqueleto cinemático de la mano y el punto índice en verde brillante en la cámara.
2. **Motor de Respaldo OpenCV (de MazeHaus):**
   * Si MediaPipe no está instalado o no se encuentra el modelo, se activa automáticamente el `OpenCVHandTracker` nativo con normalización de luz **CLAHE**, segmentación dual YCrCb + HSV, prioridad espacial inferior y *lock-on tracking*.
3. **Buffer de Latencia Mínima:**
   * `CAP_PROP_BUFFERSIZE = 1` para respuesta instantánea en tiempo real.

---

## 🚀 Ejecución Rápida

Ejecuta el script de inicio (usa automáticamente el entorno con MediaPipe):

```bash
./run.sh
```

O directamente con el entorno virtual:
```bash
.venv/bin/python main.py
```

O con `uv`:
```bash
uv run python main.py
```

*(Controles útiles: **`C`** para alternar cámaras, **`Espacio`** para iniciar/reiniciar, **`Esc`** para salir).*
