"""Seguimiento causal de 21 puntos en píxeles con MediaPipe y recuperación opcional."""

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .preprocessing import Preprocessor


BONES = np.array([
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15),
    (15, 16), (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),
])


@dataclass(frozen=True)
class Region:
    """Recorte de extensión semiabierta con su escala de inferencia."""

    x: int
    y: int
    width: int
    height: int

    def to_frame(self, normalized: np.ndarray) -> np.ndarray:
        """Proyecta puntos normalizados del recorte a píxeles del cuadro."""
        return (normalized * [self.width, self.height] + [self.x, self.y]).astype(np.float32)

    def image(self, frame: np.ndarray, max_side: int = 384) -> np.ndarray:
        """Recorta y redimensiona conservando la relación de aspecto."""
        crop = frame[self.y:self.y + self.height, self.x:self.x + self.width]
        scale = max_side / max(self.width, self.height)
        shape = (max(1, round(scale * self.width)), max(1, round(scale * self.height)))
        method = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
        return cv2.resize(crop, shape, interpolation=method)


def hand_region(points: np.ndarray, shape: tuple, margin: float = 0.55) -> Region | None:
    """Calcula una región cuadrada centrada en los puntos y recortada a la imagen."""
    height, width = shape[:2]
    lower, upper = points.min(axis=0), points.max(axis=0)
    center = (lower + upper) * 0.5
    half_side = max(20.0, max(upper - lower) * (0.5 + margin))
    x0, y0 = np.maximum(np.floor(center - half_side), 0).astype(int)
    x1, y1 = np.minimum(np.ceil(center + half_side), (width, height)).astype(int)
    if x1 - x0 < 24 or y1 - y0 < 24:
        return None
    return Region(x0, y0, x1 - x0, y1 - y0)


def optical_recovery(
    previous: np.ndarray,
    current: np.ndarray,
    points: np.ndarray,
    max_fb_error: float = 1.5,
    max_patch_error: float = 22.0,
    max_displacement_scale: float = 1.0,
) -> np.ndarray | None:
    """Acepta flujo piramidal solo si los 21 puntos tienen evidencia y forma plausible."""
    if previous.shape != current.shape or min(current.shape) < 24:
        return None
    height, width = current.shape
    source = np.ascontiguousarray(points, dtype=np.float32).reshape(-1, 1, 2)
    if not np.all((points >= 0) & (points < [width, height])):
        return None
    lk = dict(winSize=(21, 21), maxLevel=3,
              criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 25, 0.01))
    destination, status, error = cv2.calcOpticalFlowPyrLK(previous, current, source, None, **lk)
    if destination is None or not np.all(status) or not np.all(error <= max_patch_error):
        return None
    if not np.all((destination >= 0) & (destination < [width, height])):
        return None
    returned, backward_status, _ = cv2.calcOpticalFlowPyrLK(current, previous, destination, None, **lk)
    if returned is None or not np.all(backward_status):
        return None
    if not np.all(np.linalg.norm(returned - source, axis=2) <= max_fb_error):
        return None

    moved = destination[:, 0]
    scale = max(12.0, float(np.linalg.norm(points[0] - points[9])))
    displacement = np.linalg.norm(moved - points, axis=1)
    if displacement.max() > scale * max_displacement_scale:
        return None
    before = np.linalg.norm(points[BONES[:, 0]] - points[BONES[:, 1]], axis=1)
    after = np.linalg.norm(moved[BONES[:, 0]] - moved[BONES[:, 1]], axis=1)
    if np.median(np.abs(after - before) / np.maximum(before, 4)) > 0.25:
        return None
    if np.max(np.abs(after - before)) > scale * 0.5:
        return None
    return moved.copy()


class LandmarkFilter:
    """Alternativas causales de estabilización con reinicio en pérdidas prolongadas."""

    def __init__(self, options: dict):
        self.mode = options.get('smoothing', 'none')
        if self.mode not in {'none', 'ema', 'one_euro', 'kalman'}:
            raise ValueError(f'Filtro temporal desconocido: {self.mode}')
        self.min_cutoff = float(options.get('one_euro_min_cutoff', 2.0))
        self.beta = float(options.get('one_euro_beta', 0.04))
        self.ema_alpha = float(options.get('ema_alpha', 0.65))
        self.process_noise = float(options.get('kalman_process_noise', 36_000))
        self.measurement_noise = float(options.get('kalman_measurement_noise', 12))
        self.max_gap_ms = int(options.get('smoothing_max_gap_ms', 120))
        self.gate_scale = float(options.get('kalman_gate_scale', 1.25))
        if not (self.min_cutoff > 0 and self.beta >= 0 and 0 < self.ema_alpha <= 1
                and self.process_noise > 0 and self.measurement_noise > 0
                and self.max_gap_ms >= 0 and self.gate_scale > 0):
            raise ValueError('Parámetros del filtro temporal fuera de rango')
        self.reset()

    def reset(self) -> None:
        """Descarta los estados de posición, velocidad y covarianza."""
        self.filtered = None
        self.previous = None
        self.last_ms = None
        self.state = None
        self.covariance = None
        self.derivative = None
        self.rejected = np.zeros(21, dtype=bool)

    @staticmethod
    def _alpha(cutoff: float | np.ndarray, dt: float) -> float | np.ndarray:
        return 1 / (1 + 1 / (2 * np.pi * cutoff * dt))

    def update(self, points: np.ndarray | None, timestamp_ms: int) -> np.ndarray | None:
        """Estabiliza observaciones válidas y mantiene vacíos los cuadros perdidos."""
        if self.mode == 'none':
            return points
        if self.last_ms is not None and timestamp_ms - self.last_ms > self.max_gap_ms:
            self.reset()
        if points is None:
            return None
        if self.last_ms is None:
            self.filtered = points.copy()
            self.derivative = np.zeros_like(points)
            self.state = np.stack((points, np.zeros_like(points)), axis=-1).astype(float)
            self.covariance = np.broadcast_to(np.diag([self.measurement_noise, 1e4]), (21, 2, 2)).copy()
        else:
            dt = max(0.001, (timestamp_ms - self.last_ms) / 1000)
            if self.mode == 'ema':
                self.filtered += self.ema_alpha * (points - self.filtered)
            elif self.mode == 'one_euro':
                instant = (points - self.previous) / dt
                self.derivative += self._alpha(1.0, dt) * (instant - self.derivative)
                speed = np.linalg.norm(self.derivative, axis=1, keepdims=True)
                alpha = self._alpha(self.min_cutoff + self.beta * speed, dt)
                self.filtered += alpha * (points - self.filtered)
            else:
                self.filtered = self._kalman(points, dt)
        self.last_ms = timestamp_ms
        self.previous = points.copy()
        return self.filtered.astype(np.float32, copy=True)

    def _kalman(self, points: np.ndarray, dt: float) -> np.ndarray:
        transition = np.array([[1., dt], [0., 1.]])
        process = self.process_noise * np.array([[dt**3 / 3, dt**2 / 2], [dt**2 / 2, dt]])
        predicted = self.state @ transition.T
        covariance = transition @ self.covariance @ transition.T + process
        innovation = points - predicted[..., 0]
        scale = max(12.0, float(np.linalg.norm(points[0] - points[9])))
        outliers = np.linalg.norm(innovation, axis=1) > scale * self.gate_scale
        reset = outliers & self.rejected
        if outliers.sum() > 10:
            reset[:] = True
        rejected = outliers & ~reset
        gain = covariance[:, :, 0] / (covariance[:, :1, 0] + self.measurement_noise)
        gain[rejected] = 0
        self.state = predicted + innovation[..., None] * gain[:, None, :]
        self.covariance = covariance - gain[:, :, None] * covariance[:, None, 0, :]
        self.state[reset, :, 0] = points[reset]
        self.state[reset, :, 1] = 0
        self.covariance[reset] = np.diag([self.measurement_noise, 1e4])
        self.rejected = rejected
        return self.state[..., 0].astype(np.float32)


class Tracker:
    """Modela una mano con MediaPipe Tasks en CPU a lo largo de una secuencia."""

    def __init__(self, model: Path, options: dict):
        self.preprocessor = Preprocessor(options)
        self.smoother = LandmarkFilter(options)
        self.use_roi = bool(options.get('roi', False))
        self.use_flow = bool(options.get('flow', False))
        self.roi_margin = float(options.get('roi_margin', 0.55))
        self.roi_side = int(options.get('roi_side', 384))
        self.flow_max_frames = int(options.get('flow_max_frames', 2))
        self.motion_gap_ms = int(options.get('motion_gap_ms', 120))
        self.max_fb_error = float(options.get('flow_max_fb_error', 1.5))
        self.max_patch_error = float(options.get('flow_max_patch_error', 22))
        self.max_displacement = float(options.get('flow_max_displacement_scale', 1.0))
        self.confidence = {
            key: float(options.get(key, 0.5)) for key in (
                'min_hand_detection_confidence',
                'min_hand_presence_confidence',
                'min_tracking_confidence',
            )
        }
        if not (0 <= self.roi_margin <= 2 and self.roi_side >= 24 and self.flow_max_frames >= 0
                and self.motion_gap_ms > 0 and self.max_fb_error > 0
                and self.max_patch_error > 0 and self.max_displacement > 0
                and all(0 <= value <= 1 for value in self.confidence.values())):
            raise ValueError('Parámetros de seguimiento fuera de rango')
        model = Path(model)
        if not model.is_file():
            raise FileNotFoundError(f'Modelo MediaPipe no encontrado: {model}')
        import mediapipe as mp

        self.mp = mp
        self.model = model
        self.video = self._open(mp.tasks.vision.RunningMode.VIDEO)
        self.roi_model = None
        self.last_ms = None
        self.frame_shape = None
        self.previous = None
        self.previous_gray = None
        self.gap = 0
        self.last_source = 'missing'

    def _open(self, mode):
        mp = self.mp
        vision = mp.tasks.vision
        base = mp.tasks.BaseOptions(
            model_asset_path=str(self.model), delegate=mp.tasks.BaseOptions.Delegate.CPU,
        )
        return vision.HandLandmarker.create_from_options(
            vision.HandLandmarkerOptions(
                base_options=base, running_mode=mode, num_hands=1, **self.confidence,
            ),
        )

    def _detect(self, frame: np.ndarray, timestamp_ms: int | None) -> np.ndarray | None:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
        if timestamp_ms is None:
            if self.roi_model is None:
                self.roi_model = self._open(self.mp.tasks.vision.RunningMode.IMAGE)
            detected = self.roi_model.detect(image)
        else:
            detected = self.video.detect_for_video(image, timestamp_ms)
        if not detected.hand_landmarks:
            return None
        points = np.array([(point.x, point.y) for point in detected.hand_landmarks[0]])
        if points.shape != (21, 2) or not np.isfinite(points).all():
            return None
        return points

    def process(self, frame: np.ndarray, timestamp_ms: int) -> np.ndarray | None:
        """Procesa un cuadro BGR y devuelve sus puntos o una ausencia."""
        if timestamp_ms < 0 or (self.last_ms is not None and timestamp_ms <= self.last_ms):
            raise ValueError('Las marcas de tiempo deben ser crecientes y no negativas')
        if self.frame_shape is not None and frame.shape != self.frame_shape:
            # El rastreador de video conserva una región interna con la geometría anterior.
            self.video.close()
            self.video = self._open(self.mp.tasks.vision.RunningMode.VIDEO)
            self.smoother.reset()
            self.previous = self.previous_gray = None
            self.gap = 0
        if self.last_ms is not None and timestamp_ms - self.last_ms > self.motion_gap_ms:
            self.previous = self.previous_gray = None
            self.gap = 0
        self.last_ms = timestamp_ms
        self.frame_shape = frame.shape
        height, width = frame.shape[:2]
        prepared = self.preprocessor.apply(frame)
        result = self._detect(prepared, timestamp_ms)
        points = Region(0, 0, width, height).to_frame(result) if result is not None else None
        self.last_source = 'mediapipe' if points is not None else 'missing'

        if points is None and self.use_roi and self.previous is not None:
            region = hand_region(self.previous, frame.shape, self.roi_margin)
            if region is not None:
                found = self._detect(region.image(prepared, self.roi_side), None)
                if found is not None:
                    points = region.to_frame(found)
                    self.last_source = 'roi'

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if self.use_flow else None
        if (points is None and self.use_flow and self.previous is not None
                and self.gap < self.flow_max_frames):
            points = optical_recovery(self.previous_gray, gray, self.previous,
                                      self.max_fb_error, self.max_patch_error,
                                      self.max_displacement)
            if points is not None:
                self.last_source = 'flow'

        self.gap = self.gap + 1 if self.last_source == 'flow' else 0
        self.previous = points if self.use_roi or self.use_flow else None
        self.previous_gray = gray if points is not None else None
        return self.smoother.update(points, timestamp_ms)

    def close(self) -> None:
        """Libera ambas instancias del grafo MediaPipe."""
        try:
            self.video.close()
        finally:
            if self.roi_model is not None:
                self.roi_model.close()
