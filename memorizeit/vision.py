"""
Vision Tracking Engine adapted directly from MazeHaus.
Uses Google MediaPipe Hand Landmarker (Tasks API) as primary tracker,
with seamless fallback to MazeHaus's high-reliability OpenCVHandTracker.
"""

from __future__ import annotations

import cv2
import numpy as np
import threading
import time
import math
import os
import subprocess
import re
import pygame
from pathlib import Path

INDEX_FINGER_TIP = 8

class FingertipData:
    def __init__(self, detected: bool = False, norm_x: float = 0.5, norm_y: float = 0.5, raw_x: int = 0, raw_y: int = 0, status: str = "LOOKING FOR HAND"):
        self.detected = detected
        self.norm_x = norm_x  # 0.0 (left) to 1.0 (right)
        self.norm_y = norm_y  # 0.0 (top) to 1.0 (bottom)
        self.raw_x = raw_x
        self.raw_y = raw_y
        self.status = status

# ==============================================================================
# 1. Google MediaPipe Hand Landmarker Tracker (From MazeHaus)
# ==============================================================================
class MediaPipeHandTracker:
    def __init__(self, model_path: str = "models/hand_landmarker.task"):
        import mediapipe as mp
        self.mp = mp
        self.model_path = Path(model_path).resolve()
        if not self.model_path.exists():
            raise FileNotFoundError(f"MediaPipe model file not found at: {self.model_path}")

        BaseOptions = mp.tasks.BaseOptions
        HandLandmarker = mp.tasks.vision.HandLandmarker
        HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
        VisionRunningMode = mp.tasks.vision.RunningMode

        options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(self.model_path)),
            running_mode=VisionRunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=0.45,
            min_tracking_confidence=0.45,
        )
        self.landmarker = HandLandmarker.create_from_options(options)
        self.start_time = time.monotonic()
        self.status_message = "SHOW HAND TO CAMERA"
        self.is_pointing = True
        self.last_landmarks = None

    def process_frame(self, frame_bgr: np.ndarray) -> tuple[bool, float, float, list[tuple[float, float]] | None]:
        # Convert BGR to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb_frame)
        timestamp_ms = int((time.monotonic() - self.start_time) * 1000)

        result = self.landmarker.detect_for_video(mp_image, timestamp_ms)

        if not result.hand_landmarks or len(result.hand_landmarks) == 0:
            self.status_message = "SHOW HAND TO CAMERA"
            self.last_landmarks = None
            return False, 0.5, 0.5, None

        landmarks = result.hand_landmarks[0]
        # Landmarks: [0=Wrist, 4=Thumb, 8=Index Tip, 12=Middle, 16=Ring, 20=Pinky]
        w_x, w_y = landmarks[0].x, landmarks[0].y
        dist_idx = math.hypot(landmarks[8].x - w_x, landmarks[8].y - w_y)
        dist_idx_pip = math.hypot(landmarks[6].x - w_x, landmarks[6].y - w_y)
        idx_extended = dist_idx > (dist_idx_pip * 1.10)

        dist_mid = math.hypot(landmarks[12].x - w_x, landmarks[12].y - w_y)
        dist_mid_pip = math.hypot(landmarks[10].x - w_x, landmarks[10].y - w_y)
        mid_folded = dist_mid < (dist_mid_pip * 1.15)

        dist_rng = math.hypot(landmarks[16].x - w_x, landmarks[16].y - w_y)
        dist_rng_pip = math.hypot(landmarks[14].x - w_x, landmarks[14].y - w_y)
        rng_folded = dist_rng < (dist_rng_pip * 1.15)

        is_open = not mid_folded and not rng_folded
        is_pointing = idx_extended and (mid_folded or rng_folded)

        if is_open:
            self.status_message = "POINT WITH INDEX FINGER"
        elif is_pointing:
            self.status_message = "INDEX FINGER (OK)"
        else:
            self.status_message = "HAND DETECTED (OK)"

        tip = landmarks[INDEX_FINGER_TIP]
        lms_norm = [(float(lm.x), float(lm.y)) for lm in landmarks]
        self.last_landmarks = lms_norm

        return True, float(tip.x), float(tip.y), lms_norm

    def close(self):
        if hasattr(self, "landmarker") and self.landmarker is not None:
            self.landmarker.close()


# ==============================================================================
# 2. Native OpenCV Hand Tracker (From MazeHaus)
# ==============================================================================
class OpenCVHandTracker:
    def __init__(self, work_width: int = 320, work_height: int = 240):
        self.work_w = work_width
        self.work_h = work_height

        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        self.kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        self.kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

        self.smooth_x: float | None = None
        self.smooth_y: float | None = None
        self.last_contour = None
        self.status_message = "LOOKING FOR HAND"

    def process_frame(self, frame: np.ndarray) -> tuple[bool, float, float, np.ndarray | None]:
        orig_h, orig_w = frame.shape[:2]

        # 1. Downscale to working resolution (320x240)
        work_frame = cv2.resize(frame, (self.work_w, self.work_h), interpolation=cv2.INTER_AREA)

        # 2. Gaussian blur
        blurred = cv2.GaussianBlur(work_frame, (5, 5), 0)

        # 3. CLAHE on Y channel
        ycrcb = cv2.cvtColor(blurred, cv2.COLOR_BGR2YCrCb)
        ycrcb[:, :, 0] = self.clahe.apply(ycrcb[:, :, 0])

        # 4. Dual-color-space skin segmentation
        lower_ycrcb = np.array([20, 130, 75], dtype=np.uint8)
        upper_ycrcb = np.array([255, 180, 140], dtype=np.uint8)
        mask_ycrcb = cv2.inRange(ycrcb, lower_ycrcb, upper_ycrcb)

        hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
        mask_hsv1 = cv2.inRange(hsv, np.array([0, 20, 30]), np.array([25, 255, 255]))
        mask_hsv2 = cv2.inRange(hsv, np.array([168, 20, 30]), np.array([180, 255, 255]))
        mask_hsv = cv2.bitwise_or(mask_hsv1, mask_hsv2)

        combined = cv2.bitwise_and(mask_hsv, mask_ycrcb)
        if cv2.countNonZero(combined) < 150:
            combined = cv2.bitwise_or(mask_hsv, mask_ycrcb)

        # 5. Morphological cleaning
        clean = cv2.morphologyEx(combined, cv2.MORPH_OPEN, self.kernel_open, iterations=1)
        clean = cv2.dilate(clean, self.kernel_close, iterations=1)

        # 6. Contours
        contours, _ = cv2.findContours(clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            self.last_contour = None
            self.status_message = "SHOW HAND TO CAMERA"
            return False, 0.5, 0.5, None

        # 7. Spatial Hand Prior: must reach into the lower part of the camera frame
        hand_candidates = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 100:
                continue
            max_y = cnt[:, :, 1].max()
            if max_y > (self.work_h * 0.45):
                hand_candidates.append(cnt)

        if not hand_candidates:
            self.last_contour = None
            self.status_message = "SHOW HAND TO CAMERA"
            return False, 0.5, 0.5, None

        # 8. Lock-on Tracking: prioritize candidate closest to previous position
        if self.smooth_x is not None and self.smooth_y is not None:
            prev_cx = self.smooth_x * self.work_w
            prev_cy = self.smooth_y * self.work_h

            def candidate_dist(c):
                m = cv2.moments(c)
                if m["m00"] > 1e-4:
                    cx, cy = m["m10"] / m["m00"], m["m01"] / m["m00"]
                else:
                    cx, cy = float(c[:, 0, 0].mean()), float(c[:, 0, 1].mean())
                spatial_dist = math.hypot(cx - prev_cx, cy - prev_cy)
                return float(spatial_dist - (c[:, :, 1].max() * 0.5))

            hand_cnt = min(hand_candidates, key=candidate_dist)
        else:
            hand_cnt = max(hand_candidates, key=lambda c: (c[:, :, 1].max(), cv2.contourArea(c)))

        # 9. Sub-Pixel Apex Clustering within 12 pixels of highest point
        min_y = hand_cnt[:, 0, 1].min()
        top_pts = hand_cnt[hand_cnt[:, 0, 1] <= min_y + 12]
        raw_x = float(np.mean(top_pts[:, 0, 0])) / float(self.work_w)
        raw_y = float(np.mean(top_pts[:, 0, 1])) / float(self.work_h)

        # 10. Dual-Speed Adaptive Smoothing
        if self.smooth_x is None or self.smooth_y is None:
            self.smooth_x = raw_x
            self.smooth_y = raw_y
        else:
            delta = math.hypot(raw_x - self.smooth_x, raw_y - self.smooth_y)
            if delta < 0.008:
                alpha = 0.20
            elif delta < 0.025:
                alpha = 0.45
            else:
                alpha = 0.75
            self.smooth_x = alpha * raw_x + (1.0 - alpha) * self.smooth_x
            self.smooth_y = alpha * raw_y + (1.0 - alpha) * self.smooth_y

        self.status_message = "INDEX FINGER (OK)"
        scale_x = orig_w / float(self.work_w)
        scale_y = orig_h / float(self.work_h)
        self.last_contour = np.array(hand_cnt * [scale_x, scale_y], dtype=np.int32)

        return True, self.smooth_x, self.smooth_y, self.last_contour

    def close(self):
        self.smooth_x = None
        self.smooth_y = None
        self.last_contour = None


# ==============================================================================
# 3. Unified Vision Tracker Worker
# ==============================================================================
class VisionTracker:
    def __init__(self, camera_index: int | None = None, width: int = 640, height: int = 480):
        self.width = width
        self.height = height

        self.camera_map = self._detect_camera_devices()
        self.valid_devices = list(self.camera_map.keys())

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

        # Intentar cargar MediaPipe Hand Landmarker como en MazeHaus
        self.tracker_name = "OpenCV"
        self.tracker = None
        model_path = Path("models/hand_landmarker.task")
        if not model_path.exists():
            model_path = Path("/home/andres/Documents/OwnProjects/MazeHaus-Raspberry/models/hand_landmarker.task")

        try:
            if model_path.exists():
                self.tracker = MediaPipeHandTracker(str(model_path))
                self.tracker_name = "MediaPipe AI"
                print(f"[VisionTracker] Motor activado: Google MediaPipe Hand Landmarker ({model_path})")
            else:
                self.tracker = OpenCVHandTracker()
                self.tracker_name = "OpenCV CLAHE"
                print("[VisionTracker] Modelo no encontrado. Activado motor de respaldo: OpenCVHandTracker (MazeHaus)")
        except Exception as e:
            print(f"[VisionTracker] Aviso ({e}). Activando motor de respaldo: OpenCVHandTracker (MazeHaus)")
            self.tracker = OpenCVHandTracker()
            self.tracker_name = "OpenCV CLAHE"

    def _detect_camera_devices(self) -> dict[int, str]:
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
        if self.tracker is not None:
            self.tracker.close()

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

    def get_fingertip(self) -> FingertipData:
        with self.lock:
            return self.fingertip

    def get_preview_surface(self, target_width: int, target_height: int) -> pygame.Surface | None:
        with self.lock:
            if self.has_new_frame and self.latest_rgb_frame is not None:
                resized = cv2.resize(self.latest_rgb_frame, (target_width, target_height), interpolation=cv2.INTER_NEAREST)
                self.cached_surface = pygame.surfarray.make_surface(np.transpose(resized, (1, 0, 2)))
                self.has_new_frame = False

            return self.cached_surface

    def _open_camera(self, idx: int) -> cv2.VideoCapture | None:
        print(f"[VisionTracker] Abriendo cámara {idx} ({self.get_camera_name(idx)})...")
        cap = cv2.VideoCapture(idx)
        if not cap.isOpened():
            cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_FPS, 30)
            # Como en MazeHaus: buffer de 1 fotograma para latencia ultra baja
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            return cap
        return None

    def _capture_loop(self):
        cap = self._open_camera(self.camera_index)

        # Conexiones anatómicas del esqueleto de la mano en MediaPipe
        HAND_CONNECTIONS = [
            (0, 1), (1, 2), (2, 3), (3, 4),        # Pulgar
            (0, 5), (5, 6), (6, 7), (7, 8),        # Índice
            (5, 9), (9, 10), (10, 11), (11, 12),   # Medio
            (9, 13), (13, 14), (14, 15), (15, 16), # Anular
            (13, 17), (17, 18), (18, 19), (19, 20),# Meñique
            (0, 17)                                # Palma
        ]

        while self.running:
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

            # Modo espejo horizontal idéntico a MazeHaus
            mirror_frame = cv2.flip(raw_frame, 1)
            frame_h, frame_w = mirror_frame.shape[:2]

            # Procesar detección
            detected = False
            tip_x, tip_y = 0.5, 0.5
            extra_data = None

            if isinstance(self.tracker, MediaPipeHandTracker):
                detected, tip_x, tip_y, extra_data = self.tracker.process_frame(mirror_frame)
            elif isinstance(self.tracker, OpenCVHandTracker):
                detected, tip_x, tip_y, extra_data = self.tracker.process_frame(mirror_frame)

            result = FingertipData(
                detected=detected,
                norm_x=tip_x,
                norm_y=tip_y,
                raw_x=int(tip_x * frame_w),
                raw_y=int(tip_y * frame_h),
                status=self.tracker.status_message if self.tracker else ""
            )

            # Preparar vista RGB para renderizado
            rgb_frame = cv2.cvtColor(mirror_frame, cv2.COLOR_BGR2RGB)

            # Dibujar visualización según motor activo
            if detected:
                px = int(tip_x * frame_w)
                py = int(tip_y * frame_h)

                # Si es MediaPipe, dibujar el esqueleto completo de la mano
                if isinstance(self.tracker, MediaPipeHandTracker) and extra_data:
                    pts = [(int(lm[0] * frame_w), int(lm[1] * frame_h)) for lm in extra_data]
                    for p1, p2 in HAND_CONNECTIONS:
                        cv2.line(rgb_frame, pts[p1], pts[p2], (0, 200, 255), 2)
                    for idx, pt in enumerate(pts):
                        color = (0, 255, 120) if idx == INDEX_FINGER_TIP else (255, 255, 255)
                        radius = 6 if idx == INDEX_FINGER_TIP else 3
                        cv2.circle(rgb_frame, pt, radius, color, -1)

                # Si es OpenCV, dibujar el contorno
                elif isinstance(self.tracker, OpenCVHandTracker) and extra_data is not None:
                    cv2.drawContours(rgb_frame, [extra_data], -1, (0, 200, 255), 2)

                # Indicador de la punta del dedo índice
                cv2.circle(rgb_frame, (px, py), 12, (0, 255, 120), -1)
                cv2.circle(rgb_frame, (px, py), 20, (255, 255, 255), 2)
                cv2.line(rgb_frame, (px - 28, py), (px + 28, py), (0, 255, 120), 2)
                cv2.line(rgb_frame, (px, py - 28), (px, py + 28), (0, 255, 120), 2)
                cv2.putText(rgb_frame, "DEDO INDICE", (px + 14, py - 12),
                            cv2.FONT_HERSHEY_PLAIN, 1.2, (0, 255, 120), 2)

            with self.lock:
                self.fingertip = result
                self.latest_rgb_frame = rgb_frame
                self.has_new_frame = True

        if cap is not None and cap.isOpened():
            cap.release()
