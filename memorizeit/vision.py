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

        # Identificar cámaras reales y sus nombres descriptivos
        self.camera_map = self._detect_camera_devices()
        self.valid_devices = list(self.camera_map.keys())

        # Priorizar siempre la cámara USB externa (ej. índice 2)
        if camera_index is not None and camera_index in self.valid_devices:
            self.camera_index = camera_index
        elif 2 in self.valid_devices:
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
        self.cached_surface = None  # Cache de Surface para evitar parpadeos negros
        self.has_new_frame = False
        self.pending_camera_change = None

        # Suavizado exponencial para evitar vibración
        self.smooth_x = 0.5
        self.smooth_y = 0.5
        self.smoothing_factor = 0.35

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

    def _detect_camera_devices(self):
        """Detecta cámaras reales y sus nombres usando v4l2-ctl."""
        cam_map = {}
        try:
            out = subprocess.check_output(["v4l2-ctl", "--list-devices"], text=True, stderr=subprocess.DEVNULL)
            for block in out.strip().split("\n\n"):
                lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
                if not lines:
                    continue
                header = lines[0].split("(")[0].strip().replace(":", "")
                devs = [l for l in lines[1:] if "/dev/video" in l]
                if devs:
                    # El primer nodo de cada bloque es el stream de captura real
                    match = re.search(r"/dev/video(\d+)", devs[0])
                    if match:
                        idx = int(match.group(1))
                        # Etiqueta limpia
                        is_usb = "usb" in lines[0].lower() or "xwf" in header.lower()
                        label = f"{header} ({'USB' if is_usb else 'Integrada'})"
                        cam_map[idx] = label
        except Exception:
            for idx in (2, 0):
                if os.path.exists(f"/dev/video{idx}"):
                    cam_map[idx] = f"Cámara /dev/video{idx}"

        if not cam_map:
            cam_map[0] = "Cámara predeterminada"

        print(f"[VisionTracker] Dispositivos de video identificados: {cam_map}")
        return cam_map

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
            print(f"[VisionTracker] Solicitando cambio a cámara: {next_idx} ({self.get_camera_name(next_idx)})")

    def get_camera_name(self, index=None):
        target = self.camera_index if index is None else index
        return self.camera_map.get(target, f"Cámara {target}")

    def get_fingertip(self):
        with self.lock:
            return self.fingertip

    def get_preview_surface(self, target_width, target_height):
        """Retorna una Surface de Pygame de forma continua sin parpadeos negros."""
        with self.lock:
            if self.has_new_frame and self.latest_rgb_frame is not None:
                resized = cv2.resize(self.latest_rgb_frame, (target_width, target_height), interpolation=cv2.INTER_NEAREST)
                self.cached_surface = pygame.surfarray.make_surface(np.transpose(resized, (1, 0, 2)))
                self.has_new_frame = False

            # Retornar siempre la última superficie válida guardada en caché
            return self.cached_surface

    def _open_camera(self, idx):
        print(f"[VisionTracker] Abriendo cámara {idx} ({self.get_camera_name(idx)})...")
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
        frame_counter = 0
        last_detected_faces = []

        while self.running:
            # Gestionar cambio de cámara en caliente
            with self.lock:
                req_change = self.pending_camera_change
                self.pending_camera_change = None

            if req_change is not None and req_change != self.camera_index:
                if cap is not None:
                    cap.release()
                self.camera_index = req_change
                cap = self._open_camera(self.camera_index)

            if cap is None or not cap.isOpened():
                time.sleep(0.04)
                continue

            ret, raw_frame = cap.read()
            if not ret or raw_frame is None or raw_frame.size == 0:
                time.sleep(0.01)
                continue

            frame_counter += 1

            # Efecto espejo horizontal
            mirror_frame = cv2.flip(raw_frame, 1)
            frame_h, frame_w = mirror_frame.shape[:2]

            # 1. Detección periódica de rostros para suprimirlos activamente
            if not self.face_cascade.empty() and (frame_counter % 5 == 0 or len(last_detected_faces) == 0):
                small = cv2.resize(mirror_frame, (160, 120), interpolation=cv2.INTER_LINEAR)
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=4, minSize=(25, 25))

                sx = frame_w / 160.0
                sy = frame_h / 120.0

                last_detected_faces = []
                for (fx, fy, fw, fh) in faces:
                    # Considerar rostro si está en el 65% superior
                    if fy * sy < frame_h * 0.65:
                        rx = int(fx * sx)
                        ry = int(fy * sy)
                        rw = int(fw * sx)
                        rh = int(fh * sy)
                        # Padding para tapar barbilla y orejas
                        px = max(0, rx - int(rw * 0.15))
                        py = max(0, ry - int(rh * 0.20))
                        pw = min(frame_w - px, rw + int(rw * 0.30))
                        ph = min(frame_h - py, rh + int(rh * 0.40))
                        last_detected_faces.append((px, py, pw, ph))

            # 2. Segmentación de piel robusta: HSV amplio + YCrCb
            hsv = cv2.cvtColor(mirror_frame, cv2.COLOR_BGR2HSV)
            mask1 = cv2.inRange(hsv, np.array([0, 15, 30], dtype=np.uint8), np.array([35, 255, 255], dtype=np.uint8))
            mask2 = cv2.inRange(hsv, np.array([160, 15, 30], dtype=np.uint8), np.array([180, 255, 255], dtype=np.uint8))
            hsv_mask = cv2.bitwise_or(mask1, mask2)

            ycrcb = cv2.cvtColor(mirror_frame, cv2.COLOR_BGR2YCrCb)
            ycrcb_mask = cv2.inRange(ycrcb, np.array([0, 125, 65], dtype=np.uint8), np.array([255, 185, 140], dtype=np.uint8))

            skin_mask = cv2.bitwise_and(hsv_mask, ycrcb_mask)

            # 3. SUPRIMIR ROSTROS: Borrar la cabeza de la máscara de piel
            for (rx, ry, rw, rh) in last_detected_faces:
                skin_mask[ry:ry+rh, rx:rx+rw] = 0

            # 4. Morfología para limpiar ruido
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_OPEN, kernel, iterations=1)
            skin_mask = cv2.dilate(skin_mask, kernel, iterations=2)

            # 5. Detección Inteligente de la Mano (Priorizar el brazo/mano sobre el cuello/cabeza)
            contours, _ = cv2.findContours(skin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            best_contour = None
            best_score = -1e9

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < 400.0:
                    continue

                # Puntos clave del contorno
                topmost = tuple(cnt[cnt[:, :, 1].argmin()][0])
                bottommost = tuple(cnt[cnt[:, :, 1].argmax()][0])

                # ¿El contorno se origina desde la mitad inferior o bordes inferiores de la cámara?
                # Los brazos y manos entran por abajo (Y > frame_h * 0.5)
                touches_bottom = bottommost[1] > (frame_h * 0.55)

                # Calcular puntuación:
                # - Gran bonificación si viene desde la parte inferior (es un brazo/mano extendida)
                # - Bonificación por alcanzar mayor altura (menor Y del topmost)
                # - Ponderación del área
                score = area * 0.05
                if touches_bottom:
                    score += 5000.0
                score += (frame_h - topmost[1]) * 10.0  # Cuanto más arriba apunte, más probable que sea el dedo

                # Penalizar contornos flotantes aislados en la parte superior central (posibles restos de cabeza/cuello)
                if not touches_bottom and topmost[1] < frame_h * 0.40 and (frame_w * 0.25 < topmost[0] < frame_w * 0.75):
                    score -= 3000.0

                if score > best_score:
                    best_score = score
                    best_contour = cnt

            result = FingertipData()
            if best_contour is not None and best_score > 0:
                topmost = tuple(best_contour[best_contour[:, :, 1].argmin()][0])
                raw_norm_x = topmost[0] / float(frame_w)
                raw_norm_y = topmost[1] / float(frame_h)

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

            # Dibujar rostros ignorados
            for (rx, ry, rw, rh) in last_detected_faces:
                cv2.rectangle(rgb_frame, (rx, ry), (rx + rw, ry + rh), (255, 60, 60), 2)
                cv2.putText(rgb_frame, "ROSTRO IGNORADO", (rx + 4, ry - 6),
                            cv2.FONT_HERSHEY_PLAIN, 1.0, (255, 80, 80), 1)

            # Dibujar dedo índice detectado
            if result.detected:
                px = int(result.norm_x * frame_w)
                py = int(result.norm_y * frame_h)
                cv2.circle(rgb_frame, (px, py), 10, (0, 255, 120), -1)
                cv2.circle(rgb_frame, (px, py), 18, (255, 255, 255), 2)
                cv2.line(rgb_frame, (px - 25, py), (px + 25, py), (0, 255, 120), 1)
                cv2.line(rgb_frame, (px, py - 25), (px, py + 25), (0, 255, 120), 1)
                cv2.putText(rgb_frame, "DEDO", (px + 14, py - 10),
                            cv2.FONT_HERSHEY_PLAIN, 1.2, (0, 255, 120), 2)

            with self.lock:
                self.fingertip = result
                self.latest_rgb_frame = rgb_frame
                self.has_new_frame = True

        if cap is not None and cap.isOpened():
            cap.release()
