import cv2
import numpy as np
import threading
import time
import os
import subprocess
import re
import math
import pygame

class FingertipData:
    def __init__(self, detected=False, norm_x=0.5, norm_y=0.5, raw_x=0, raw_y=0, angle=0.0):
        self.detected = detected
        self.norm_x = norm_x  # 0.0 (izq) a 1.0 (der)
        self.norm_y = norm_y  # 0.0 (arriba) a 1.0 (abajo)
        self.raw_x = raw_x
        self.raw_y = raw_y
        self.angle = angle

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
        self.cached_surface = None  # Cache para eliminar parpadeo negro
        self.has_new_frame = False
        self.pending_camera_change = None

        # Suavizado exponencial para evitar saltos bruscos
        self.smooth_x = 0.5
        self.smooth_y = 0.5
        self.smoothing_factor = 0.35

        # Cargar clasificador de rostros
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

        # Parámetros adaptativos de piel calibrados en tiempo real
        self.calibrated_skin = False
        self.skin_mean_h = 130.0
        self.skin_mean_s = 65.0
        self.skin_mean_v = 150.0

        # Máscara de persistencia del rostro (para que NUNCA parpadee ni se filtre)
        self.persistent_face_box = None
        self.face_missing_frames = 0

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
            print(f"[VisionTracker] Solicitando cambio a cámara: {next_idx} ({self.get_camera_name(next_idx)})")

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

    def _find_sharpest_fingertip(self, contour):
        """
        Calcula la curvatura geométrica en cada punto del contorno.
        Un dedo extendido tiene un ángulo agudo (entre 18° y 72°) y apunta hacia arriba.
        Una cabeza, barbilla o cuello tiene un ángulo obtuso (> 110°) y es descartado.
        """
        n_pts = len(contour)
        if n_pts < 20:
            return None, 180.0

        step = max(6, n_pts // 25)
        best_pt = None
        best_angle = 180.0
        min_y = 1e9

        for i in range(n_pts):
            p = contour[i][0].astype(np.float32)
            prev_p = contour[(i - step) % n_pts][0].astype(np.float32)
            next_p = contour[(i + step) % n_pts][0].astype(np.float32)

            # Debe apuntar hacia arriba: ambos vecinos deben estar más abajo (Y mayor)
            if prev_p[1] < p[1] or next_p[1] < p[1]:
                continue

            v1 = prev_p - p
            v2 = next_p - p
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)

            if norm1 < 10.0 or norm2 < 10.0:
                continue

            cos_val = np.clip(np.dot(v1, v2) / (norm1 * norm2), -1.0, 1.0)
            angle = math.degrees(math.acos(cos_val))

            # Solo se aceptan vértices afilados (dedos entre 18° y 72°)
            if angle < 72.0:
                if p[1] < min_y:
                    min_y = p[1]
                    best_angle = angle
                    best_pt = (int(p[0]), int(p[1]))

        return best_pt, best_angle

    def _capture_loop(self):
        cap = self._open_camera(self.camera_index)
        frame_counter = 0

        while self.running:
            # Cambio de cámara en caliente
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

            # 1. Detección periódica de rostros para AUTO-CALIBRAR piel y suprimir cabeza
            if not self.face_cascade.empty() and (frame_counter % 5 == 0 or self.persistent_face_box is None):
                small = cv2.resize(mirror_frame, (160, 120), interpolation=cv2.INTER_LINEAR)
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.18, minNeighbors=4, minSize=(25, 25))

                sx = frame_w / 160.0
                sy = frame_h / 120.0

                if len(faces) > 0:
                    fx, fy, fw, fh = faces[0]
                    rx = int(fx * sx)
                    ry = int(fy * sy)
                    rw = int(fw * sx)
                    rh = int(fh * sy)

                    # Auto-muestreo de piel en mejillas / frente
                    py1 = max(0, ry + int(rh * 0.25))
                    py2 = min(frame_h, ry + int(rh * 0.65))
                    px1 = max(0, rx + int(rw * 0.25))
                    px2 = min(frame_w, rx + int(rw * 0.75))

                    if py2 > py1 and px2 > px1:
                        patch = mirror_frame[py1:py2, px1:px2]
                        patch_hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
                        mh, ms, mv = cv2.mean(patch_hsv)[:3]
                        self.skin_mean_h = self.skin_mean_h * 0.7 + mh * 0.3
                        self.skin_mean_s = self.skin_mean_s * 0.7 + ms * 0.3
                        self.skin_mean_v = self.skin_mean_v * 0.7 + mv * 0.3
                        self.calibrated_skin = True

                    # Zona de bloqueo expandida (cubre cabeza, sienes, barbilla y cuello superior)
                    bx = max(0, rx - int(rw * 0.25))
                    by = max(0, ry - int(rh * 0.30))
                    bw = min(frame_w - bx, rw + int(rw * 0.50))
                    bh = min(frame_h - by, rh + int(rh * 0.65))

                    self.persistent_face_box = (bx, by, bw, bh)
                    self.face_missing_frames = 0
                else:
                    self.face_missing_frames += 1
                    # Mantener el bloqueo de la cara por al menos 30 frames para evitar parpadeos
                    if self.face_missing_frames > 30:
                        self.persistent_face_box = None

            # 2. Segmentación de piel adaptativa
            hsv = cv2.cvtColor(mirror_frame, cv2.COLOR_BGR2HSV)

            tol_h, tol_s, tol_v = 30, 65, 75
            h_min = max(0, int(self.skin_mean_h - tol_h))
            h_max = min(180, int(self.skin_mean_h + tol_h))
            s_min = max(20, int(self.skin_mean_s - tol_s))
            s_max = min(255, int(self.skin_mean_s + tol_s))
            v_min = max(30, int(self.skin_mean_v - tol_v))
            v_max = min(255, int(self.skin_mean_v + tol_v))

            mask_adaptive = cv2.inRange(hsv, np.array([h_min, s_min, v_min]), np.array([h_max, s_max, v_max]))
            mask_std1 = cv2.inRange(hsv, np.array([0, 15, 30]), np.array([30, 255, 255]))
            mask_std2 = cv2.inRange(hsv, np.array([160, 15, 30]), np.array([180, 255, 255]))
            mask_std = cv2.bitwise_or(mask_std1, mask_std2)

            skin_mask = cv2.bitwise_or(mask_adaptive, mask_std)

            # 3. SUPRESIÓN TOTAL DE LA CARA: Borrar toda la cabeza de la máscara
            if self.persistent_face_box is not None:
                fbx, fby, fbw, fbh = self.persistent_face_box
                skin_mask[fby:fby+fbh, fbx:fbx+fbw] = 0

            # 4. Morfología para limpiar ruido
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
            skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
            skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_OPEN, kernel, iterations=1)

            # 5. Detección EXCLUSIVA de Dedos Afilados (Ángulo geométrico < 72°)
            contours, _ = cv2.findContours(skin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            best_finger_pt = None
            best_angle = 180.0
            min_finger_y = 1e9

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < 400.0:
                    continue

                # Buscar la punta afilada del dedo índice en este contorno
                sharp_pt, angle = self._find_sharpest_fingertip(cnt)

                if sharp_pt is not None:
                    # El dedo que alcance mayor altura (menor Y) hacia los paneles es el elegido
                    if sharp_pt[1] < min_finger_y:
                        min_finger_y = sharp_pt[1]
                        best_finger_pt = sharp_pt
                        best_angle = angle

            result = FingertipData()
            if best_finger_pt is not None:
                raw_norm_x = best_finger_pt[0] / float(frame_w)
                raw_norm_y = best_finger_pt[1] / float(frame_h)

                # Suavizado exponencial
                self.smooth_x = self.smooth_x * (1.0 - self.smoothing_factor) + raw_norm_x * self.smoothing_factor
                self.smooth_y = self.smooth_y * (1.0 - self.smoothing_factor) + raw_norm_y * self.smoothing_factor

                result = FingertipData(
                    detected=True,
                    norm_x=self.smooth_x,
                    norm_y=self.smooth_y,
                    raw_x=best_finger_pt[0],
                    raw_y=best_finger_pt[1],
                    angle=best_angle
                )

            # 6. Preparar vista previa en color RGB
            rgb_frame = cv2.cvtColor(mirror_frame, cv2.COLOR_BGR2RGB)

            # Sombrear la zona de la cabeza bloqueada en rojo translúcido
            if self.persistent_face_box is not None:
                fbx, fby, fbw, fbh = self.persistent_face_box
                sub = rgb_frame[fby:fby+fbh, fbx:fbx+fbw]
                red_overlay = np.full(sub.shape, (120, 20, 20), dtype=np.uint8)
                cv2.addWeighted(sub, 0.6, red_overlay, 0.4, 0, sub)
                cv2.rectangle(rgb_frame, (fbx, fby), (fbx + fbw, fby + fbh), (255, 60, 60), 2)
                cv2.putText(rgb_frame, "CARA BLOQUEADA (OMITIDA)", (fbx + 4, fby - 8),
                            cv2.FONT_HERSHEY_PLAIN, 1.1, (255, 80, 80), 2)

            # Dibujar la punta del dedo detectada en verde brillante
            if result.detected:
                px = int(result.norm_x * frame_w)
                py = int(result.norm_y * frame_h)
                cv2.circle(rgb_frame, (px, py), 12, (0, 255, 120), -1)
                cv2.circle(rgb_frame, (px, py), 20, (255, 255, 255), 2)
                cv2.line(rgb_frame, (px - 28, py), (px + 28, py), (0, 255, 120), 2)
                cv2.line(rgb_frame, (px, py - 28), (px, py + 28), (0, 255, 120), 2)
                cv2.putText(rgb_frame, f"DEDO ({result.angle:.0f} deg)", (px + 14, py - 12),
                            cv2.FONT_HERSHEY_PLAIN, 1.2, (0, 255, 120), 2)

            with self.lock:
                self.fingertip = result
                self.latest_rgb_frame = rgb_frame
                self.has_new_frame = True

        if cap is not None and cap.isOpened():
            cap.release()
