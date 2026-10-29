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

        # Priorizar siempre la cámara USB externa (/dev/video2)
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
        self.cached_surface = None
        self.has_new_frame = False
        self.pending_camera_change = None
        self.trigger_recalibrate = True

        # Suavizado exponencial para movimiento fluido y sin saltos
        self.smooth_x = 0.5
        self.smooth_y = 0.5
        self.smoothing_factor = 0.35

    def _detect_camera_devices(self):
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
                    match = re.search(r"/dev/video(\d+)", devs[0])
                    if match:
                        idx = int(match.group(1))
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
            self.trigger_recalibrate = True
            print(f"[VisionTracker] Solicitando cambio a cámara: {next_idx} ({self.get_camera_name(next_idx)})")

    def recalibrate_background(self):
        """Fuerza la captura de un nuevo fondo de referencia."""
        with self.lock:
            self.trigger_recalibrate = True
        print("[VisionTracker] Recalibrando fondo...")

    def get_camera_name(self, index=None):
        target = self.camera_index if index is None else index
        return self.camera_map.get(target, f"Cámara {target}")

    def get_fingertip(self):
        with self.lock:
            return self.fingertip

    def get_preview_surface(self, target_width, target_height):
        with self.lock:
            if self.has_new_frame and self.latest_rgb_frame is not None:
                resized = cv2.resize(self.latest_rgb_frame, (target_width, target_height), interpolation=cv2.INTER_NEAREST)
                self.cached_surface = pygame.surfarray.make_surface(np.transpose(resized, (1, 0, 2)))
                self.has_new_frame = False

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
        running_bg = None
        min_hand_base_y = int(self.height * 0.65)  # La mano SIEMPRE debe entrar desde abajo (Y >= 312)

        while self.running:
            # Cambio de cámara en caliente
            with self.lock:
                req_change = self.pending_camera_change
                self.pending_camera_change = None
                do_recal = self.trigger_recalibrate
                self.trigger_recalibrate = False

            if req_change is not None and req_change != self.camera_index:
                if cap is not None:
                    cap.release()
                self.camera_index = req_change
                cap = self._open_camera(self.camera_index)
                running_bg = None

            if cap is None or not cap.isOpened():
                time.sleep(0.04)
                continue

            ret, raw_frame = cap.read()
            if not ret or raw_frame is None or raw_frame.size == 0:
                time.sleep(0.01)
                continue

            # Efecto espejo horizontal
            mirror_frame = cv2.flip(raw_frame, 1)
            frame_h, frame_w = mirror_frame.shape[:2]

            # Preprocesamiento en escala de grises con desenfoque para eliminar ruido
            gray = cv2.cvtColor(mirror_frame, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (17, 17), 0)

            # Inicialización o recalibración del fondo de referencia
            if running_bg is None or do_recal:
                running_bg = blurred.copy().astype(np.float32)

            # 1. Diferencia absoluta respecto al fondo del entorno
            bg_uint8 = cv2.convertScaleAbs(running_bg)
            diff = cv2.absdiff(blurred, bg_uint8)

            # Umbral binario y dilatación para obtener la silueta sólida de la mano
            _, thresh = cv2.threshold(diff, 20, 255, cv2.THRESH_BINARY)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
            thresh = cv2.dilate(thresh, kernel, iterations=2)

            # 2. Búsqueda de contornos
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            best_contour = None
            best_score = -1e9
            hand_detected = False

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < 1200.0:
                    continue

                topmost = tuple(cnt[cnt[:, :, 1].argmin()][0])
                bottommost = tuple(cnt[cnt[:, :, 1].argmax()][0])

                # REGLA FÍSICA INQUEBRANTABLE:
                # Una mano extendida para tocar la pantalla proviene SIEMPRE de la parte inferior (Y >= min_hand_base_y).
                # La cabeza, el cuello, la pared o las luces flotan arriba y NUNCA tocan la base.
                if bottommost[1] < min_hand_base_y:
                    continue  # Descartar: es la cabeza, cuello o fondo

                # Puntuación basada en altura alcanzada (cuanto más arriba apunte el dedo, mejor)
                score = (frame_h - topmost[1]) * 10.0 + area * 0.02
                if score > best_score:
                    best_score = score
                    best_contour = cnt
                    hand_detected = True

            result = FingertipData()
            if best_contour is not None:
                topmost = tuple(best_contour[best_contour[:, :, 1].argmin()][0])
                raw_norm_x = topmost[0] / float(frame_w)
                raw_norm_y = topmost[1] / float(frame_h)

                # Suavizado exponencial para deslizamiento 100% orgánico
                self.smooth_x = self.smooth_x * (1.0 - self.smoothing_factor) + raw_norm_x * self.smoothing_factor
                self.smooth_y = self.smooth_y * (1.0 - self.smoothing_factor) + raw_norm_y * self.smoothing_factor

                result = FingertipData(
                    detected=True,
                    norm_x=self.smooth_x,
                    norm_y=self.smooth_y,
                    raw_x=topmost[0],
                    raw_y=topmost[1]
                )

            # Si NO hay mano levantada, actualizar lentamente el fondo para adaptarse a la luz
            if not hand_detected:
                cv2.accumulateWeighted(blurred, running_bg, 0.04)

            # 3. Preparar imagen RGB para la interfaz de Pygame
            rgb_frame = cv2.cvtColor(mirror_frame, cv2.COLOR_BGR2RGB)

            # Si se detectó la mano, dibujar su contorno y el marcador de la punta del dedo
            if result.detected and best_contour is not None:
                cv2.drawContours(rgb_frame, [best_contour], -1, (0, 200, 255), 2)
                px = int(result.norm_x * frame_w)
                py = int(result.norm_y * frame_h)

                cv2.circle(rgb_frame, (px, py), 12, (0, 255, 120), -1)
                cv2.circle(rgb_frame, (px, py), 20, (255, 255, 255), 2)
                cv2.line(rgb_frame, (px - 25, py), (px + 25, py), (0, 255, 120), 2)
                cv2.line(rgb_frame, (px, py - 25), (px, py + 25), (0, 255, 120), 2)
                cv2.putText(rgb_frame, "DEDO", (px + 14, py - 10),
                            cv2.FONT_HERSHEY_PLAIN, 1.2, (0, 255, 120), 2)
            else:
                cv2.putText(rgb_frame, "Levanta tu mano hacia la pantalla", (20, frame_h - 25),
                            cv2.FONT_HERSHEY_PLAIN, 1.2, (180, 220, 255), 1)

            with self.lock:
                self.fingertip = result
                self.latest_rgb_frame = rgb_frame
                self.has_new_frame = True

        if cap is not None and cap.isOpened():
            cap.release()
