"""Detectores causales de agarre y suelta a partir de landmarks y video RGB."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Literal

import cv2
import numpy as np

_PALM = np.array([5, 9, 13, 17])
_FINGERS = np.array([range(start, start + 4) for start in _PALM])
_TIPS = _FINGERS[:, -1]
EventKind = Literal["agarrar", "soltar"]


@dataclass(frozen=True)
class Event:
    """Cuadro estimado en base cero y, opcionalmente, cuadro de confirmación."""

    frame: int
    kind: EventKind
    confirmed_frame: int | None = None


@dataclass(frozen=True)
class HandGeometry:
    """Descriptores de geometría independientes de la escala global de la imagen."""

    aperture: float
    extension: float
    pinch: float
    palm_scale: float
    center: np.ndarray
    fingertips: np.ndarray


def hand_geometry(landmarks: np.ndarray | None) -> HandGeometry | None:
    """Resume apertura y flexión de los dedos proyectados en dos dimensiones."""
    if landmarks is None:
        return None
    points = np.asarray(landmarks, dtype=np.float64)
    if points.shape != (21, 2) or not np.isfinite(points).all():
        return None
    scale = float(np.median(np.linalg.norm(points[_PALM] - points[0], axis=1)))
    if scale < 1.0:
        return None
    fingers = points[_FINGERS]
    chain = np.linalg.norm(np.diff(fingers, axis=1), axis=2).sum(axis=1)
    if np.count_nonzero(chain > 0.15 * scale) < 3:
        return None
    extension = np.linalg.norm(fingers[:, -1] - fingers[:, 0], axis=1)
    extension = float(np.median(extension[chain > 0.15 * scale] / chain[chain > 0.15 * scale]))
    pinch = float(np.linalg.norm(points[4] - points[8]) / scale)
    aperture = 0.75 * extension + 0.25 * min(pinch, 1.0)
    center = np.vstack((points[0], points[_PALM])).mean(axis=0)
    return HandGeometry(aperture, extension, pinch, scale, center, points[_TIPS].mean(axis=0))


@dataclass(frozen=True)
class _Options:
    """Parámetros iniciales sin calibración sobre datos de prueba."""

    closed_threshold: float = 0.67
    open_threshold: float = 0.79
    confirm_frames: int = 2
    evidence_window: int = 7
    min_hold_frames: int = 4
    max_gap: int = 4
    motion_gate: bool = True
    aperture_alpha: float = 0.7
    baseline_stop_speed: float = 0.08

    def __post_init__(self) -> None:
        if not 0.0 < self.closed_threshold < self.open_threshold <= 1.0:
            raise ValueError("Se requieren umbrales de apertura crecientes dentro de (0, 1].")
        if not 0.0 < self.aperture_alpha <= 1.0:
            raise ValueError("El peso de la apertura actual debe estar dentro de (0, 1].")
        for name in ("confirm_frames", "evidence_window", "min_hold_frames", "max_gap"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError(f"{name} debe ser un entero no negativo.")
        if self.confirm_frames < 1 or self.evidence_window < self.confirm_frames:
            raise ValueError("La ventana visual debe cubrir los cuadros de confirmación.")
        if type(self.motion_gate) is not bool:
            raise ValueError("motion_gate debe ser un valor booleano.")
        if not np.isfinite(self.baseline_stop_speed) or self.baseline_stop_speed <= 0:
            raise ValueError("La rapidez del baseline debe ser positiva.")


def _motion_frame(frame: np.ndarray) -> tuple[np.ndarray, float]:
    """Reduce la resolución de la señal visual sin modificar los landmarks."""
    shrink = min(1.0, 420.0 / max(frame.shape[:2]))
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if shrink < 1.0:
        gray = cv2.resize(gray, None, fx=shrink, fy=shrink, interpolation=cv2.INTER_AREA)
    return gray, shrink


def _track_corners(
    first: np.ndarray,
    second: np.ndarray,
    corners: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Aplica LK piramidal y descarta desplazamientos con retorno inconsistente."""
    lk = {"winSize": (15, 15), "maxLevel": 2}
    moved, forward, errors = cv2.calcOpticalFlowPyrLK(first, second, corners, None, **lk)
    if moved is None or forward is None:
        return np.empty((0, 2), dtype=np.float32), np.empty((0, 2), dtype=np.float32)
    valid = forward.ravel().astype(bool)
    valid &= np.isfinite(moved[:, 0]).all(axis=1) & (errors.ravel() <= 25.0)
    if not valid.any():
        return np.empty((0, 2), dtype=np.float32), np.empty((0, 2), dtype=np.float32)
    source, target = corners[valid], moved[valid]
    back, backward, _ = cv2.calcOpticalFlowPyrLK(second, first, target, None, **lk)
    if back is None or backward is None:
        return np.empty((0, 2), dtype=np.float32), np.empty((0, 2), dtype=np.float32)
    valid = backward.ravel().astype(bool) & (np.linalg.norm((source - back)[:, 0], axis=1) <= 1.3)
    return source[valid, 0], target[valid, 0]


def _co_motion(
    previous: tuple[np.ndarray, float, np.ndarray, HandGeometry],
    current: tuple[np.ndarray, float, np.ndarray, HandGeometry],
) -> bool:
    """Busca esquinas cercanas con movimiento coherente fuera de la silueta."""
    first, scale, previous_points, previous_geometry = previous
    second, current_scale, current_points, current_geometry = current
    if first.shape != second.shape or scale != current_scale:
        return False
    palm = previous_geometry.palm_scale * scale
    hand_motion = (current_geometry.center - previous_geometry.center) * scale
    if palm < 6.0 or np.linalg.norm(hand_motion) > 0.65 * palm:
        return False

    hull = cv2.convexHull(np.rint(previous_points * scale).astype(np.int32))
    height, width = first.shape
    near = np.zeros((height, width), np.uint8)
    contact = tuple(np.rint(previous_geometry.fingertips * scale).astype(int))
    cv2.circle(near, contact, round(0.95 * palm), 255, -1)
    cv2.fillConvexPoly(near, hull, 0)
    local = cv2.goodFeaturesToTrack(first, 24, 0.015, 4, mask=near)
    if local is None or len(local) < 2:
        return False
    positions, moved = _track_corners(first, second, local)
    if len(positions) < 2:
        return False

    current_hull = cv2.convexHull((current_points * scale).astype(np.float32))
    outside = np.array([
        cv2.pointPolygonTest(current_hull, tuple(point), False) <= 0 for point in moved
    ])
    if outside.sum() < 2:
        return False
    far = np.full((height, width), 255, np.uint8)
    center = tuple(np.rint(previous_geometry.center * scale).astype(int))
    cv2.circle(far, center, round(2.1 * palm), 0, -1)
    background = cv2.goodFeaturesToTrack(first, 18, 0.02, 10, mask=far)
    camera_motion = np.zeros(2)
    if background is not None and len(background) >= 4:
        start, end = _track_corners(first, second, background)
        if len(start) >= 4:
            camera_motion = np.median(end - start, axis=0)

    hand_motion -= camera_motion
    speed = np.linalg.norm(hand_motion)
    if speed < max(0.55, 0.025 * palm):
        return False
    local_motion = (moved - positions)[outside] - camera_motion
    alignment = local_motion @ (hand_motion / speed)
    residual = np.linalg.norm(local_motion - hand_motion, axis=1)
    coherent = (alignment >= max(0.5, 0.4 * speed)) & (residual <= max(1.4, 0.75 * speed))
    return bool(np.count_nonzero(coherent) >= 2)


class EventDetector:
    """Máquina de estados para una mano con estados de espera y confirmación."""

    def __init__(self, mode: str = "proposed", options: dict | None = None):
        if mode not in ("baseline", "proposed"):
            raise ValueError(f"Detector de eventos desconocido: {mode}")
        options = options or {}
        unknown = options.keys() - {field.name for field in fields(_Options)}
        if unknown:
            raise ValueError(f"Opciones de eventos desconocidas: {', '.join(sorted(unknown))}")
        self.options = _Options(**options)
        self.mode = mode
        self._armed = False
        self._held_at: int | None = None
        self._start: int | None = None
        self._gap = 0
        self._index: int | None = None
        self._aperture: float | None = None
        self._speed: float | None = None
        self._previous_geometry: HandGeometry | None = None
        self._previous_visual: tuple[np.ndarray, float, np.ndarray, HandGeometry] | None = None
        self._seen_motion = False

    def _reset_candidate(self) -> None:
        self._start = None
        self._seen_motion = False

    def _missing(self, count: int) -> None:
        self._gap += count
        self._previous_geometry = None
        self._previous_visual = None
        self._speed = None
        self._aperture = None
        self._reset_candidate()
        if self._gap > self.options.max_gap:
            self._held_at = None
            self._armed = False

    def _baseline(self, index: int, aperture: float, speed: float | None) -> Event | None:
        settings = self.options
        if self._held_at is not None:
            if aperture >= settings.open_threshold:
                self._held_at = None
                self._armed = True
                return Event(index, "soltar", index)
        elif aperture >= settings.open_threshold:
            self._armed = True
        elif (
            self._armed and aperture <= settings.closed_threshold
            and speed is not None and self._speed is not None
            and speed <= settings.baseline_stop_speed and speed < self._speed
        ):
            self._armed = False
            self._held_at = index
            return Event(index, "agarrar", index)
        return None

    def _proposed(self, index: int, aperture: float, visual_motion: bool) -> Event | None:
        settings = self.options
        if self._held_at is not None:
            if aperture < settings.open_threshold or index - self._held_at < settings.min_hold_frames:
                self._reset_candidate()
                return None
        elif aperture >= settings.open_threshold:
            self._armed = True
            self._reset_candidate()
            return None
        elif not self._armed or aperture > settings.closed_threshold:
            self._reset_candidate()
            return None

        if self._start is None:
            self._start = index
        span = index - self._start + 1
        self._seen_motion |= visual_motion
        if span >= settings.confirm_frames:
            if self._held_at is not None:
                event = Event(self._start, "soltar", index)
                self._held_at = None
                self._armed = True
                self._reset_candidate()
                return event
            if self._seen_motion or not settings.motion_gate:
                event = Event(self._start, "agarrar", index)
                self._armed = False
                self._held_at = index
                self._reset_candidate()
                return event
        if span >= settings.evidence_window:
            self._armed = False
            self._reset_candidate()
        return None

    def process(self, index: int, frame: np.ndarray, landmarks: np.ndarray | None) -> Event | None:
        """Consume un cuadro BGR y devuelve un evento cuando puede confirmarlo."""
        if index < 0 or (self._index is not None and index <= self._index):
            raise ValueError("Los índices de cuadros deben ser crecientes y no negativos.")
        if self._index is not None and index > self._index + 1:
            self._missing(index - self._index - 1)
        self._index = index
        geometry = hand_geometry(landmarks)
        if geometry is None:
            self._missing(1)
            return None
        self._gap = 0

        if self.mode == "baseline":
            speed = None
            if self._previous_geometry is not None:
                delta = geometry.center - self._previous_geometry.center
                speed = float(np.linalg.norm(delta) / geometry.palm_scale)
            event = self._baseline(index, geometry.aperture, speed)
            self._speed = speed
            self._previous_geometry = geometry
            return event

        alpha = self.options.aperture_alpha
        self._aperture = (
            geometry.aperture if self._aperture is None
            else alpha * geometry.aperture + (1 - alpha) * self._aperture
        )
        visual_motion = False
        if self.options.motion_gate:
            gray, shrink = _motion_frame(frame)
            visual = (gray, shrink, np.asarray(landmarks).copy(), geometry)
            if (
                self._held_at is None and self._armed and not self._seen_motion
                and self._aperture <= self.options.closed_threshold and self._previous_visual is not None
            ):
                visual_motion = _co_motion(self._previous_visual, visual)
            self._previous_visual = visual
        return self._proposed(index, self._aperture, visual_motion)
