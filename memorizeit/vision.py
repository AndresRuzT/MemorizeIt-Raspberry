"""
Vision Tracking Engine for MemorizeIt.
Uses Google MediaPipe Hand Landmarker (Tasks API) as primary tracker with
strict index-finger isolation and OneEuroFilter2D jitter elimination.
Includes native OpenCV contour tracker as fallback.
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

# ==============================================================================
# OneEuroFilter & OneEuroFilter2D (Adaptive Low-Pass Filter with Deadband)
# ==============================================================================
class LowPassFilter:
    def __init__(self, alpha: float = 1.0) -> None:
        self.alpha = alpha
        self.y: float | None = None

    def filter(self, value: float, alpha: float | None = None) -> float:
        if alpha is not None:
            self.alpha = alpha
        if self.y is None:
            self.y = value
        else:
            self.y = self.alpha * value + (1.0 - self.alpha) * self.y
        return self.y

    def reset(self) -> None:
        self.y = None


class OneEuroFilter:
    def __init__(self, min_cutoff: float = 0.8, beta: float = 0.25, d_cutoff: float = 1.0) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x_filter = LowPassFilter()
        self.dx_filter = LowPassFilter()
        self.last_time: float | None = None

    def _alpha(self, cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def filter(self, x: float, timestamp: float) -> float:
        if self.last_time is None:
            self.last_time = timestamp
            return self.x_filter.filter(x, alpha=1.0)

        dt = timestamp - self.last_time
        self.last_time = timestamp
        if dt <= 1e-6:
            dt = 1e-6

        prev_x = self.x_filter.y if self.x_filter.y is not None else x
        dx = (x - prev_x) / dt
        edx = self.dx_filter.filter(dx, alpha=self._alpha(self.d_cutoff, dt))
        cutoff = self.min_cutoff + self.beta * abs(edx)
        return self.x_filter.filter(x, alpha=self._alpha(cutoff, dt))

    def reset(self) -> None:
        self.x_filter.reset()
        self.dx_filter.reset()
        self.last_time = None


class OneEuroFilter2D:
    def __init__(self, min_cutoff: float = 0.8, beta: float = 0.35, d_cutoff: float = 1.0, deadband: float = 0.004) -> None:
        self.filter_x = OneEuroFilter(min_cutoff=min_cutoff, beta=beta, d_cutoff=d_cutoff)
        self.filter_y = OneEuroFilter(min_cutoff=min_cutoff, beta=beta, d_cutoff=d_cutoff)
        self.deadband = deadband
        self.last_stable_x: float | None = None
        self.last_stable_y: float | None = None

    def filter(self, x: float, y: float, timestamp: float) -> tuple[float, float]:
        fx = self.filter_x.filter(x, timestamp)
        fy = self.filter_y.filter(y, timestamp)

        if self.last_stable_x is None or self.last_stable_y is None:
            self.last_stable_x = fx
            self.last_stable_y = fy
            return fx, fy

        dist = math.hypot(fx - self.last_stable_x, fy - self.last_stable_y)
        if dist < self.deadband:
            return self.last_stable_x, self.last_stable_y

        self.last_stable_x = fx
        self.last_stable_y = fy
        return fx, fy

    def reset(self) -> None:
        self.filter_x.reset()
        self.filter_y.reset()
        self.last_stable_x = None
        self.last_stable_y = None


# ==============================================================================
# Fingertip Data Structure
# ==============================================================================
class FingertipData:
    def __init__(
        self,
        detected: bool = False,
        norm_x: float = 0.5,
        norm_y: float = 0.5,
        raw_x: int = 0,
        raw_y: int = 0,
        hand_present: bool = False,
        is_pointing: bool = False,
        status: str = "LOOKING FOR HAND",
    ):
        self.detected = detected  # True ONLY when pointing with index finger
        self.norm_x = norm_x      # 0.0 (left) to 1.0 (right)
        self.norm_y = norm_y      # 0.0 (top) to 1.0 (bottom)
        self.raw_x = raw_x
        self.raw_y = raw_y
        self.hand_present = hand_present
        self.is_pointing = is_pointing
        self.status = status


# ==============================================================================
# 1. Google MediaPipe Hand Landmarker Tracker (Primary)
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
        self.last_timestamp_ms = 0
        self.status_message = "SHOW HAND TO CAMERA"
        self.is_pointing = False
        self.last_landmarks = None
        self.filter_2d = OneEuroFilter2D(min_cutoff=0.8, beta=0.35, d_cutoff=1.0, deadband=0.004)

    def process_frame(self, frame_bgr: np.ndarray) -> tuple[bool, float, float, list[tuple[float, float]] | None, bool]:
        """
        Returns:
            (detected: bool, norm_x: float, norm_y: float, landmarks: list, is_pointing: bool)
            'detected' is True ONLY when index pointing gesture is confirmed.
        """
        rgb_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb_frame)

        now = time.monotonic()
        timestamp_ms = int((now - self.start_time) * 1000)
        if timestamp_ms <= self.last_timestamp_ms:
            timestamp_ms = self.last_timestamp_ms + 1
        self.last_timestamp_ms = timestamp_ms

        try:
            result = self.landmarker.detect_for_video(mp_image, timestamp_ms)
        except Exception:
            return False, 0.5, 0.5, None, False

        if not result.hand_landmarks or len(result.hand_landmarks) == 0:
            self.status_message = "MUESTRA LA MANO A LA CAMARA"
            self.last_landmarks = None
            self.is_pointing = False
            self.filter_2d.reset()
            return False, 0.5, 0.5, None, False

        landmarks = result.hand_landmarks[0]
        lms_norm = [(float(lm.x), float(lm.y)) for lm in landmarks]
        self.last_landmarks = lms_norm

        # Análisis anatómico de postura del dedo índice
        # 0=Wrist, 5=Index_MCP, 6=Index_PIP, 8=Index_TIP
        # 9=Middle_MCP, 10=Middle_PIP, 12=Middle_TIP
        # 13=Ring_MCP, 14=Ring_PIP, 16=Ring_TIP
        # 17=Pinky_MCP, 18=Pinky_PIP, 20=Pinky_TIP
        w_x, w_y, w_z = landmarks[0].x, landmarks[0].y, getattr(landmarks[0], "z", 0.0)

        def dist3(a_idx: int, b_idx: int = 0) -> float:
            lm_a = landmarks[a_idx]
            if b_idx == 0:
                bx, by, bz = w_x, w_y, w_z
            else:
                lm_b = landmarks[b_idx]
                bx, by, bz = lm_b.x, lm_b.y, getattr(lm_b, "z", 0.0)
            az = getattr(lm_a, "z", 0.0)
            return math.sqrt((lm_a.x - bx) ** 2 + (lm_a.y - by) ** 2 + (az - bz) ** 2)

        dist_idx = dist3(8, 0)
        dist_idx_pip = dist3(6, 0)
        idx_extended = dist_idx > (dist_idx_pip * 1.10)

        dist_mid = dist3(12, 0)
        dist_mid_pip = dist3(10, 0)
        mid_folded = (dist_mid < dist_mid_pip * 1.15) or (dist_idx > dist_mid * 1.12)

        dist_rng = dist3(16, 0)
        dist_rng_pip = dist3(14, 0)
        rng_folded = (dist_rng < dist_rng_pip * 1.15) or (dist_idx > dist_rng * 1.12)

        dist_pnk = dist3(20, 0)
        dist_pnk_pip = dist3(18, 0)
        pnk_folded = (dist_pnk < dist_pnk_pip * 1.15) or (dist_idx > dist_pnk * 1.12)

        folded_count = sum([1 for f in (mid_folded, rng_folded, pnk_folded) if f])
        is_pointing = idx_extended and (folded_count >= 2)
        self.is_pointing = is_pointing

        raw_tip_x = float(landmarks[INDEX_FINGER_TIP].x)
        raw_tip_y = float(landmarks[INDEX_FINGER_TIP].y)

        if is_pointing:
            self.status_message = "DEDO INDICE (ACTIVO)"
            fx, fy = self.filter_2d.filter(raw_tip_x, raw_tip_y, now)
            fx = max(0.0, min(1.0, fx))
            fy = max(0.0, min(1.0, fy))
            return True, fx, fy, lms_norm, True
        else:
            self.status_message = "APUNTA CON EL DEDO INDICE"
            return False, raw_tip_x, raw_tip_y, lms_norm, False

    def close(self):
        if hasattr(self, "landmarker") and self.landmarker is not None:
            self.landmarker.close()
        self.filter_2d.reset()


# ==============================================================================
# 2. Native OpenCV Hand Tracker (Robust Fallback)
# ==============================================================================
class OpenCVHandTracker:
    def __init__(self, work_width: int = 320, work_height: int = 240):
        self.work_w = work_width
        self.work_h = work_height
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        self.kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        self.kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        self.filter_2d = OneEuroFilter2D(min_cutoff=0.8, beta=0.35, d_cutoff=1.0, deadband=0.005)
        self.last_contour = None
        self.status_message = "LOOKING FOR HAND"
        self.is_pointing = False

    def process_frame(self, frame: np.ndarray) -> tuple[bool, float, float, np.ndarray | None, bool]:
        orig_h, orig_w = frame.shape[:2]
        now = time.monotonic()

        work_frame = cv2.resize(frame, (self.work_w, self.work_h), interpolation=cv2.INTER_AREA)
        blurred = cv2.GaussianBlur(work_frame, (5, 5), 0)

        ycrcb = cv2.cvtColor(blurred, cv2.COLOR_BGR2YCrCb)
        ycrcb[:, :, 0] = self.clahe.apply(ycrcb[:, :, 0])

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

        clean = cv2.morphologyEx(combined, cv2.MORPH_OPEN, self.kernel_open, iterations=1)
        clean = cv2.dilate(clean, self.kernel_close, iterations=1)

        # Omitir totalmente el tercio superior del fotograma (donde reside el rostro)
        clean[: int(self.work_h * 0.35), :] = 0

        contours, _ = cv2.findContours(clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            self.last_contour = None
            self.status_message = "SHOW HAND TO CAMERA"
            self.filter_2d.reset()
            return False, 0.5, 0.5, None, False

        hand_candidates = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 150:
                continue
            max_y = cnt[:, :, 1].max()
            if max_y > (self.work_h * 0.45):
                hand_candidates.append(cnt)

        if not hand_candidates:
            self.last_contour = None
            self.status_message = "SHOW HAND TO CAMERA"
            return False, 0.5, 0.5, None, False

        hand_cnt = max(hand_candidates, key=lambda c: (c[:, :, 1].max(), cv2.contourArea(c)))
        min_y = hand_cnt[:, 0, 1].min()
        top_pts = hand_cnt[hand_cnt[:, 0, 1] <= min_y + 12]
        raw_x = float(np.mean(top_pts[:, 0, 0])) / float(self.work_w)
        raw_y = float(np.mean(top_pts[:, 0, 1])) / float(self.work_h)

        fx, fy = self.filter_2d.filter(raw_x, raw_y, now)
        self.status_message = "DEDO INDICE (OK)"
        scale_x = orig_w / float(self.work_w)
        scale_y = orig_h / float(self.work_h)
        self.last_contour = np.array(hand_cnt * [scale_x, scale_y], dtype=np.int32)
        return True, fx, fy, self.last_contour, True

    def close(self):
        self.filter_2d.reset()
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

        # Cargar MediaPipe Hand Landmarker como en MazeHaus
        self.tracker_name = "OpenCV"
        self.tracker = None

        model_candidates = [
            Path("models/hand_landmarker.task"),
            Path(__file__).parent.parent / "models" / "hand_landmarker.task",
            Path("/home/andres/Documents/OwnProjects/MazeHaus-Raspberry/models/hand_landmarker.task"),
        ]
        model_path = next((p for p in model_candidates if p.exists()), None)

        try:
            if model_path is not None:
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
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            return cap
        return None

    def _capture_loop(self):
        cap = self._open_camera(self.camera_index)

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

            # Modo espejo horizontal
            mirror_frame = cv2.flip(raw_frame, 1)
            frame_h, frame_w = mirror_frame.shape[:2]

            # Procesar detección
            detected = False
            tip_x, tip_y = 0.5, 0.5
            extra_data = None
            is_pointing = False

            if self.tracker is not None:
                try:
                    res = self.tracker.process_frame(mirror_frame)
                    if len(res) == 5:
                        detected, tip_x, tip_y, extra_data, is_pointing = res
                    else:
                        detected, tip_x, tip_y, extra_data = res[:4]
                        is_pointing = detected
                except Exception as exc:
                    detected = False

            hand_present = extra_data is not None

            result = FingertipData(
                detected=detected,
                norm_x=tip_x,
                norm_y=tip_y,
                raw_x=int(tip_x * frame_w),
                raw_y=int(tip_y * frame_h),
                hand_present=hand_present,
                is_pointing=is_pointing,
                status=self.tracker.status_message if self.tracker else "",
            )

            # Preparar vista RGB para renderizado
            rgb_frame = cv2.cvtColor(mirror_frame, cv2.COLOR_BGR2RGB)

            # Dibujar visualización según motor activo
            if isinstance(self.tracker, MediaPipeHandTracker) and extra_data:
                pts = [(int(lm[0] * frame_w), int(lm[1] * frame_h)) for lm in extra_data]
                bone_color = (0, 255, 120) if is_pointing else (255, 170, 0)
                for p1, p2 in HAND_CONNECTIONS:
                    cv2.line(rgb_frame, pts[p1], pts[p2], bone_color, 2)
                for idx, pt in enumerate(pts):
                    color = (0, 255, 200) if idx == INDEX_FINGER_TIP else (255, 255, 255)
                    radius = 6 if idx == INDEX_FINGER_TIP else 3
                    cv2.circle(rgb_frame, pt, radius, color, -1)

            elif isinstance(self.tracker, OpenCVHandTracker) and extra_data is not None:
                cv2.drawContours(rgb_frame, [extra_data], -1, (0, 200, 255), 2)

            # Indicador de la punta del dedo índice (Landmark 8)
            px = int(tip_x * frame_w)
            py = int(tip_y * frame_h)

            if detected:
                # Dedo índice activo apuntando
                cv2.circle(rgb_frame, (px, py), 12, (0, 255, 120), -1)
                cv2.circle(rgb_frame, (px, py), 22, (255, 255, 255), 2)
                cv2.line(rgb_frame, (px - 30, py), (px + 30, py), (0, 255, 120), 2)
                cv2.line(rgb_frame, (px, py - 30), (px, py + 30), (0, 255, 120), 2)
                cv2.putText(rgb_frame, "DEDO INDICE", (px + 14, py - 12),
                            cv2.FONT_HERSHEY_PLAIN, 1.2, (0, 255, 120), 2)
            elif hand_present:
                # Mano visible pero no apuntando con el índice
                cv2.circle(rgb_frame, (px, py), 10, (255, 180, 0), 2)
                cv2.putText(rgb_frame, "APUNTA CON EL INDICE", (px + 14, py - 12),
                            cv2.FONT_HERSHEY_PLAIN, 1.1, (255, 200, 50), 2)

            with self.lock:
                self.fingertip = result
                self.latest_rgb_frame = rgb_frame
                self.has_new_frame = True

        if cap is not None and cap.isOpened():
            cap.release()
