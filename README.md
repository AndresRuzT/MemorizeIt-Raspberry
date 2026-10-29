# MemorizeIt - Among Us Reactor Memory Game (Raspberry Pi 4)

Videojuego de memoria en cuadrícula 3x3 estilo el minijuego de Reactor de **Among Us**, desarrollado íntegramente en **Python 3** con **Pygame**, **OpenCV** y **NumPy**, optimizado para una **Raspberry Pi 4** con cámara USB externa.

---

## 🎮 Mecánica de Juego y Novedades

1. **Inicio con Dedo en el Centro (5 segundos):**
   * El juego arranca en estado de espera (*Standby*).
   * Para iniciar la partida, el jugador coloca su dedo en el **círculo central de la cámara** durante **5 segundos continuos**.
   * Un anillo de progreso y beeps sonoros cuentan: `5.0s... 4.0s... 3.0s... 2.0s... 1.0s... ¡INICIANDO!`. Si retiras el dedo antes, se cancela y se reinicia.
2. **Juego Infinito (Ronda 1 a $\infty$):**
   * El juego ya no se detiene en 5 rondas: continúa agregando un nuevo paso por cada ronda superada de forma infinita.
   * La secuencia se acumula y se acelera la destreza mental.
3. **Pulsación de 2 Segundos (*Dwell Time*):** 
   * Para validar cada panel, se debe mantener el dedo sobre el botón correspondiente durante **2.0 segundos continuos**.
   * Una barra de energía interna llena el panel y un anillo circular gira alrededor del dedo con cuenta regresiva.
4. **Game Over y Estado de Espera:**
   * Si pulsas un panel fuera de orden: suena la alarma, la cuadrícula parpadea en rojo y se anuncia **GAME OVER**.
   * Guarda automáticamente tu récord en `highscores.json` y vuelve al estado de espera para iniciar otra partida.
5. **Salón de la Fama / Récords:**
   * Registro persistente del jugador que llegó a la ronda más alta en la esquina superior y en la tarjeta de estadísticas.

---

## 🖥️ Interfaz Separada y Ampliada (1280x720 HD)

* **Columna Izquierda:** Tablero de reactor gigante (500x500 px) con los 9 paneles retroiluminados estilo Among Us y barra de estado inferior.
* **Columna Derecha:** Pantalla de cámara en vivo en alta definición (600x450 px) con:
  * Cuadrícula virtual 3x3 semitransparente superpuesta sobre el video (para ver exactamente qué panel estás tocando con tu mano).
  * Zona objetivo central para el inicio de 5 segundos.
  * Selector e indicador del nombre real de la cámara USB activa.
  * Tabla con el TOP 3 de mejores puntuaciones debajo del video.

---

## ⚡ Visión Artificial Optimizada

1. **Cero Parpadeos Negros:** Búfer de cuadros en caché persistente en Pygame para mantener la señal de video 100% fluida a 60 FPS sin apagones.
2. **Detección Exclusiva de la Mano (Sin Confusión con el Rostro):**
   * Clasificador Haar suprime la cabeza en el área superior.
   * Algoritmo de puntuación geométrica que prioriza contornos que se originan desde abajo (brazo/mano) y que alcanzan mayor altura hacia el panel, ignorando el cuello o el torso.
   * Segmentación dual combinada HSV + YCrCb para máxima fidelidad bajo cualquier iluminación.
3. **Autodetección de Cámara USB:**
   * Prioriza la cámara USB externa (`/dev/video2: XWF-1080P`) sobre la integrada.
   * Permite alternar en caliente en cualquier momento pulsando la tecla **`C`**.

---

## 📦 Instalación

Instala las dependencias del sistema:

```bash
chmod +x scripts/install_dependencies.sh
./scripts/install_dependencies.sh
```

*(O manualmente vía APT: `sudo apt install -y python3-opencv python3-pygame python3-numpy v4l-utils`)*

---

## 🚀 Ejecución

Lanzar el juego:
```bash
python3 main.py
```

O forzando una cámara específica:
```bash
python3 main.py --cam 2
```

*(Teclas útiles: **`C`** para cambiar de cámara, **`Espacio`** para iniciar o salir de Game Over, **`Esc`** para cerrar).*
