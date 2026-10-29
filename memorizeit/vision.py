import cv2
import numpy as np
import threading
import time
import os
import subprocess
import re
import pygame

class FingertipData:
    def __init__(self, detected=False, norm_x=0.5, norm_y=0.5, raw_x=0, raw_y=0):
        self.detected = detected
        self.norm_x = norm_x  # 0.0 (izq) a 1.0 (der)
        self.norm_y = norm_y  # 0.0 (arriba) a 1.0 (abajo)
        self.raw_x = raw_x
        self.raw_y = raw_y

class VisionTracker:
    def __init__(self, camera_index=None, width=640, height=480):
        self.width = width
        self.height = height

        # Identificar solo dispositivos de video reales (evitar nodos de metadata que cuelgan el bus)
        self.valid_devices = self.get_real_video_devices()
        print(f"[VisionTracker] Cámaras reales detectadas: {self.valid_devices}")

        if camera_index is not None and camera_index in self.valid_devices:
            self.camera_index = camera_index
        elif 2 in self.valid_devices:
            # Priorizar la cámara USB externa (/dev/video2)
            self.camera_index = 2
        elif self.valid_devices:
            self.camera_index = self.valid_devices[0]
        else:
            self.camera_index = 0

        self.running = False
        self.worker_thread = None
        self.lock = threading.Lock()

        self.fingertip = FingertipData()
        self.latest_rgb_frame = None
        self.has_new_frame = False
        self.camera_status = f"CAM [{self.camera_index}] Iniciando..."
        self.pending_camera_change = None

        # Suavizado exponencial
        self.smooth_x = 0.5
        self.smooth_y = 0.5
        self.smoothing_factor = 0.35

        # Cargar clasificador de rostros para suprimirlos
        self.face_cascade = cv2.CascadeClassifier()
        cascade_paths = [
            "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
            "/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml",
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml" if hasattr(cv2, 'data') else ""
        ]
        for p in cascade_paths:
            if p and os.path.exists(p) and self.face_cascade.load(p):
                print(f"[VisionTracker] Clasificador de rostros cargado: {p}")
                break

    @staticmethod
    def get_real_video_devices():
        """Obtiene solo los nodos de captura de video reales, descartando metadata."""
        devices = []
        try:
            out = subprocess.check_output(["v4l2-ctl", "--list-devices"], text=True, stderr=subprocess.DEVNULL)
            for block in out.strip().split("\n\n"):
                lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
                if not lines:
                    continue
                devs = [l for l in lines[1:] if "/dev/video" in l]
                if devs:
                    # El primer /dev/videoX de cada bloque es siempre el stream de video real
                    match = re.search(r"/dev/video(\d+)", devs[0])
                    if match:
                        devices.append(int(match.group(1)))
        except Exception:
            # Fallback seguro
            for idx in (2, 0):
                if os.path.exists(f"/dev/video{idx}"):
                    devices.append(idx)

        # Si encontramos 2 (USB), ponerlo de primero
        if 2 in devices:
            devices.remove(2)
            devices.insert(0, 2)

        return devices if devices else [0]

    def start(self):
        if self.running:
            return
        self.running = True
        self.worker_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.worker_thread.start()

    def stop(self):
        self.running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)

    def cycle_camera(self):
        if len(self.valid_devices) <= 1:
            return
        with self.lock:
            try:
                cur_idx = self.valid_devices.index(self.camera_index)
                next_idx = self.valid_devices[(cur_idx + 1) % len(self.valid_devices)]
            except ValueError:
                next_idx = self.valid_devices[0]
            self.pending_camera_change = next_idx
            print(f"[VisionTracker] Cambiando a cámara: {next_idx}")

    def get_camera_status(self):
        with self.lock:
            return self.camera_status

    def get_fingertip(self):
        with self.lock:
            return self.fingertip

    def get_preview_surface(self, target_width, target_height):
        with self.lock:
            if not self.has_new_frame or self.latest_rgb_frame is None:
                return None
            resized = cv2.resize(self.latest_rgb_frame, (target_width, target_height), interpolation=cv2.INTER_NEAREST)
            self.has_new_frame = False

        # Convertir a pygame.Surface
        surface = pygame.surfarray.make_surface(np.transpose(resized, (1, 0, 2)))
        return surface

    def _open_camera(self, idx):
        print(f"[VisionTracker] Abriendo cámara {idx} con V4L2...")
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.open(idx, cv2.CAP_ANY)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_FPS, 30)
            return cap
        return None

    def _capture_loop(self):
        cap = self._open_camera(self.camera_index)

        with self.lock:
            is_ok = cap is not None and cap.isOpened()
            self.camera_status = f"CAM [{self.camera_index}] {'Conectada' if is_ok else 'Error'}"

        frame_counter = 0
        last_detected_faces = []

        while self.running:
            # Gestionar cambio de cámara si se solicitó
            with self.lock:
                req_change = self.pending_camera_change
                self.pending_camera_change = None

            if req_change is not None and req_change != self.camera_index:
                if cap is not None:
                    cap.release()
                self.camera_index = req_change
                cap = self._open_camera(self.camera_index)
                with self.lock:
                    is_ok = cap is not None and cap.isOpened()
                    self.camera_status = f"CAM [{self.camera_index}] {'Conectada' if is_ok else 'Sin señal'}"

            if cap is None or not cap.isOpened():
                time.sleep(0.05)
                continue

            ret, raw_frame = cap.read()
            if not ret or raw_frame is None or raw_frame.size == 0:
                time.sleep(0.01)
                continue

            frame_counter += 1

            # Efecto espejo horizontal para que la mano coincida con la pantalla
            mirror_frame = cv2.flip(raw_frame, 1)

            # 1. Detección periódica de rostros (cada 5 frames) con minNeighbors alto para NO detectar manos
            if not self.face_cascade.empty() and (frame_counter % 5 == 0 or len(last_detected_faces) == 0):
                small = cv2.resize(mirror_frame, (160, 120), interpolation=cv2.INTER_LINEAR)
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                # minNeighbors=5 y minSize=(30,30) garantiza detectar solo cabezas y no palmas de manos
                faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(25, 25))

                sx = mirror_frame.shape[1] / 160.0
                sy = mirror_frame.shape[0] / 120.0

                last_detected_faces = []
                for (fx, fy, fw, fh) in faces:
                    # Solo considerar rostros si están en la mitad superior de la cámara
                    if fy * sy < mirror_frame.shape[0] * 0.65:
                        rx = int(fx * sx)
                        ry = int(fy * sy)
                        rw = int(fw * sx)
                        rh = int(fh * sy)
                        # Padding moderado
                        px = max(0, rx - int(rw * 0.1))
                        py = max(0, ry - int(rh * 0.15))
                        pw = min(mirror_frame.shape[1] - px, rw + int(rw * 0.2))
                        ph = min(mirror_frame.shape[0] - py, rh + int(rh * 0.3))
                        last_detected_faces.append((px, py, pw, ph))

            # 2. Detección de piel combinada: HSV amplio + YCrCb
            # HSV
            hsv = cv2.cvtColor(mirror_frame, cv2.COLOR_BGR2HSV)
            hsv_mask1 = cv2.inRange(hsv, np.array([0, 15, 30], dtype=np.uint8), np.array([32, 255, 255], dtype=np.uint8))
            hsv_mask2 = cv2.inRange(hsv, np.array([160, 15, 30], dtype=np.uint8), np.array([180, 255, 255], dtype=np.uint8))
            hsv_mask = cv2.bitwise_or(hsv_mask1, hsv_mask2)

            # YCrCb
            ycrcb = cv2.cvtColor(mirror_frame, cv2.COLOR_BGR2YCrCb)
            ycrcb_mask = cv2.inRange(ycrcb, np.array([0, 128, 70], dtype=np.uint8), np.array([255, 185, 135], dtype=np.uint8))

            # Máscara combinada (permissiva para cualquier tono de piel / iluminación)
            skin_mask = cv2.bitwise_and(hsv_mask, ycrcb_mask)

            # 3. SUPRIMIR ROSTROS: Borrar las caras detectadas de la máscara
            for (rx, ry, rw, rh) in last_detected_faces:
                skin_mask[ry:ry+rh, rx:rx+rw] = 0

            # 4. Morfología para limpiar ruido
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_OPEN, kernel, iterations=1)
            skin_mask = cv2.dilate(skin_mask, kernel, iterations=2)

            # 5. Detección de contornos para la mano
            contours, _ = cv2.findContours(skin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            best_contour = None
            max_area = 0
            for cnt in contours:
                area = cv2.contourArea(cnt)
                # Umbral de área accesible para un dedo o mano (500 px)
                if area > 500.0 and area > max_area:
                    max_area = area
                    best_contour = cnt

            result = FingertipData()
            if best_contour is not None:
                # El punto superior de la mano (mínimo Y) es la punta del dedo índice que apunta a los paneles
                topmost = tuple(best_contour[best_contour[:, :, 1].argmin()][0])
                raw_norm_x = topmost[0] / float(mirror_frame.shape[1])
                raw_norm_y = topmost[1] / float(mirror_frame.shape[0])

                # Suavizado exponencial para estabilidad
                self.smooth_x = self.smooth_x * (1.0 - self.smoothing_factor) + raw_norm_x * self.smoothing_factor
                self.smooth_y = self.smooth_y * (1.0 - self.smoothing_factor) + raw_norm_y * self.smoothing_factor

                result = FingertipData(
                    detected=True,
                    norm_x=self.smooth_x,
                    norm_y=self.smooth_y,
                    raw_x=topmost[0],
                    raw_y=topmost[1]
                )

            # 6. Preparar vista previa en color RGB
            rgb_frame = cv2.cvtColor(mirror_frame, cv2.COLOR_BGR2RGB)

            # Mostrar cuadro del rostro ignorado
            for (rx, ry, rw, rh) in last_detected_faces:
                cv2.rectangle(rgb_frame, (rx, ry), (rx + rw, ry + rh), (255, 60, 60), 2)
                cv2.putText(rgb_frame, "ROSTRO IGNORADO", (rx + 4, ry - 6),
                            cv2.FONT_HERSHEY_PLAIN, 1.0, (255, 80, 80), 1)

            # Dibujar la punta del dedo detectada en verde brillante
            if result.detected:
                px = int(result.norm_x * rgb_frame.shape[1])
                py = int(result.norm_y * rgb_frame.shape[0])
                cv2.circle(rgb_frame, (px, py), 9, (0, 255, 120), -1)
                cv2.circle(rgb_frame, (px, py), 16, (255, 255, 255), 2)
                cv2.putText(rgb_frame, "DEDO", (px + 12, py + 5),
                            cv2.FONT_HERSHEY_PLAIN, 1.2, (0, 255, 120), 2)

            with self.lock:
                self.fingertip = result
                self.latest_rgb_frame = rgb_frame
                self.has_new_frame = True

        if cap is not None and cap.isOpened():
            cap.release()
