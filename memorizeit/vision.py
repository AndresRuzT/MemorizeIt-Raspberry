import cv2
import numpy as np
import threading
import time
import os
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
        self.target_camera_index = camera_index
        self.camera_index = camera_index
        self.width = width
        self.height = height

        self.running = False
        self.worker_thread = None
        self.lock = threading.Lock()

        self.fingertip = FingertipData()
        self.latest_rgb_frame = None
        self.has_new_frame = False
        self.camera_status = "Iniciando..."
        self.needs_reconnect = False

        # Suavizado exponencial
        self.smooth_x = 0.5
        self.smooth_y = 0.5
        self.smoothing_factor = 0.30

        # Rango HSV para piel
        self.h_min, self.h_max = 0, 25
        self.s_min, self.s_max = 45, 220
        self.v_min, self.v_max = 50, 255

        # Cargar clasificador de rostros para suprimirlos activamente
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
    def detect_best_camera():
        # Probar candidatos, dando prioridad a USB externa (2, 1, 3) sobre la integrada (0)
        candidates = [2, 1, 0, 3, 4]
        for idx in candidates:
            cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            if not cap.isOpened():
                cap.open(idx, cv2.CAP_ANY)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None and frame.size > 0:
                    print(f"[VisionTracker] Cámara seleccionada automáticamente: /dev/video{idx}")
                    return idx
        return 0

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
        with self.lock:
            cur = self.camera_index if self.camera_index is not None else 0
            self.camera_index = (cur + 1) % 4
            self.needs_reconnect = True

    def set_camera(self, index):
        with self.lock:
            self.camera_index = index
            self.needs_reconnect = True

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

    def _capture_loop(self):
        if self.camera_index is None:
            self.camera_index = self.detect_best_camera()

        cap = None

        def open_cam(idx):
            nonlocal cap
            if cap is not None and cap.isOpened():
                cap.release()
            c = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            if not c.isOpened():
                c.open(idx, cv2.CAP_ANY)
            if c.isOpened():
                c.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
                c.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                c.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                c.set(cv2.CAP_PROP_FPS, 30)
                cap = c
                return True
            return False

        if not open_cam(self.camera_index):
            self.camera_index = self.detect_best_camera()
            open_cam(self.camera_index)

        with self.lock:
            is_open = cap is not None and cap.isOpened()
            self.camera_status = f"CAM [{self.camera_index}] {'Conectada' if is_open else 'Sin senal'}"

        frame_counter = 0
        last_detected_faces = []

        while self.running:
            if self.needs_reconnect:
                self.needs_reconnect = False
                open_cam(self.camera_index)
                with self.lock:
                    is_open = cap is not None and cap.isOpened()
                    self.camera_status = f"CAM [{self.camera_index}] {'Conectada' if is_open else 'Sin senal'}"

            if cap is None or not cap.isOpened():
                time.sleep(0.05)
                continue

            ret, raw_frame = cap.read()
            if not ret or raw_frame is None or raw_frame.size == 0:
                time.sleep(0.02)
                continue

            frame_counter += 1

            # Efecto espejo horizontal para interacción natural
            mirror_frame = cv2.flip(raw_frame, 1)

            # 1. Supresión periódica de rostros (cada 4 frames a baja resolución 160x120)
            if not self.face_cascade.empty() and (frame_counter % 4 == 0 or len(last_detected_faces) == 0):
                small_gray = cv2.cvtColor(mirror_frame, cv2.COLOR_BGR2GRAY)
                small_gray = cv2.resize(small_gray, (160, 120), interpolation=cv2.INTER_LINEAR)
                small_gray = cv2.equalizeHist(small_gray)

                faces = self.face_cascade.detectMultiScale(small_gray, scaleFactor=1.15, minNeighbors=3, minSize=(25, 25))

                scale_x = mirror_frame.shape[1] / 160.0
                scale_y = mirror_frame.shape[0] / 120.0

                last_detected_faces = []
                for (fx, fy, fw, fh) in faces:
                    sx = int(fx * scale_x)
                    sy = int(fy * scale_y)
                    sw = int(fw * scale_x)
                    sh = int(fh * scale_y)

                    # Expandir para cubrir mentón y sienes
                    pad_w = int(sw * 0.25)
                    pad_h = int(sh * 0.35)
                    ex = max(0, sx - pad_w // 2)
                    ey = max(0, sy - pad_h // 2)
                    ew = min(mirror_frame.shape[1] - ex, sw + pad_w)
                    eh = min(mirror_frame.shape[0] - ey, sh + pad_h)
                    last_detected_faces.append((ex, ey, ew, eh))

            # 2. Segmentación de piel HSV
            hsv = cv2.cvtColor(mirror_frame, cv2.COLOR_BGR2HSV)
            lower_skin = np.array([self.h_min, self.s_min, self.v_min], dtype=np.uint8)
            upper_skin = np.array([self.h_max, self.s_max, self.v_max], dtype=np.uint8)
            skin_mask = cv2.inRange(hsv, lower_skin, upper_skin)

            # 3. SUPRESIÓN ESTRICTA: Borrar cualquier rostro de la máscara de piel
            for (ex, ey, ew, eh) in last_detected_faces:
                skin_mask[ey:ey+eh, ex:ex+ew] = 0

            # 4. Morfología para eliminar ruido
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            skin_mask = cv2.erode(skin_mask, kernel, iterations=1)
            skin_mask = cv2.dilate(skin_mask, kernel, iterations=2)

            # 5. Detección de contornos para la mano y dedo
            contours, _ = cv2.findContours(skin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            best_contour = None
            max_area = 0
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area > 1200.0 and area > max_area:
                    max_area = area
                    best_contour = cnt

            result = FingertipData()
            if best_contour is not None:
                # El punto superior de la mano (mínimo Y) es la punta del dedo
                topmost = tuple(best_contour[best_contour[:, :, 1].argmin()][0])
                raw_norm_x = topmost[0] / float(mirror_frame.shape[1])
                raw_norm_y = topmost[1] / float(mirror_frame.shape[0])

                # Suavizado exponencial
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

            # Dibujar caja de rostro ignorado
            for (ex, ey, ew, eh) in last_detected_faces:
                cv2.rectangle(rgb_frame, (ex, ey), (ex + ew, ey + eh), (255, 60, 60), 2)
                cv2.putText(rgb_frame, "ROSTRO IGNORADO", (ex + 4, ey - 6),
                            cv2.FONT_HERSHEY_PLAIN, 1.0, (255, 80, 80), 1)

            # Dibujar dedo detectado
            if result.detected:
                px = int(result.norm_x * rgb_frame.shape[1])
                py = int(result.norm_y * rgb_frame.shape[0])
                cv2.circle(rgb_frame, (px, py), 9, (0, 255, 120), -1)
                cv2.circle(rgb_frame, (px, py), 15, (255, 255, 255), 2)
                cv2.putText(rgb_frame, "DEDO", (px + 12, py + 5),
                            cv2.FONT_HERSHEY_PLAIN, 1.1, (0, 255, 120), 2)

            with self.lock:
                self.fingertip = result
                self.latest_rgb_frame = rgb_frame
                self.has_new_frame = True

        if cap is not None and cap.isOpened():
            cap.release()
