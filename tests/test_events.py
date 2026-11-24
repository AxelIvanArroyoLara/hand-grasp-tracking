"""Pruebas sintéticas de los rasgos geométricos y los estados de manipulación."""

import cv2
import numpy as np
import pytest

from src.events import Event, EventDetector, _co_motion, hand_geometry


def pose(closed: bool, x: float = 0.0) -> np.ndarray:
    """Construye extensiones y flexiones controladas en una mano esquemática."""
    points = np.zeros((21, 2))
    points[0] = 100, 120
    points[1:5] = [[93, 114], [88, 106], [82, 96], [76, 86]]
    for start, offset in zip((5, 9, 13, 17), (-15, -4, 6, 15), strict=True):
        xs = 100 + offset
        if closed:
            points[start:start + 4] = [[xs, 100], [xs, 86], [xs + 1, 94], [xs, 102]]
        else:
            points[start:start + 4] = [[xs, 100], [xs, 88], [xs, 79], [xs, 72]]
    if closed:
        points[4] = points[8] + [1, 1]
    points[:, 0] += x
    return points


def test_geometry_scale_and_flexion():
    opened = hand_geometry(pose(False))
    closed = hand_geometry(pose(True))
    assert opened.aperture >= 0.79
    assert closed.aperture <= 0.67
    assert hand_geometry(2.8 * pose(False) - 20).aperture == pytest.approx(opened.aperture)
    assert hand_geometry(np.zeros((21, 2))) is None


def test_hysteresis_event_origin_and_confirmation():
    frame = np.zeros((150, 200, 3), dtype=np.uint8)
    detector = EventDetector(options={"motion_gate": False, "aperture_alpha": 1.0, "min_hold_frames": 2})
    sequence = [False, True, False, True, True, True, False, False, False]
    detected = [detector.process(i, frame, pose(closed)) for i, closed in enumerate(sequence)]
    assert [event for event in detected if event is not None] == [
        Event(3, "agarrar", 4), Event(6, "soltar", 7)
    ]


def test_gap_breaks_persistence_and_resets_held():
    frame = np.zeros((150, 200, 3), dtype=np.uint8)
    detector = EventDetector(options={"motion_gate": False, "max_gap": 1, "aperture_alpha": 1.0})
    assert detector.process(0, frame, pose(False)) is None
    assert detector.process(1, frame, pose(True)) is None
    assert detector.process(2, frame, None) is None
    assert detector.process(3, frame, pose(True)) is None
    assert detector.process(4, frame, pose(True)) == Event(3, "agarrar", 4)
    assert detector.process(7, frame, pose(False)) is None
    assert detector.process(8, frame, pose(False)) is None
    with pytest.raises(ValueError):
        detector.process(8, frame, pose(False))


def test_static_image_cannot_confirm_visual_grasp():
    frame = np.zeros((150, 200, 3), dtype=np.uint8)
    detector = EventDetector()
    detections = [detector.process(i, frame, pose(i > 0, i * 2)) for i in range(12)]
    assert all(event is None for event in detections)


def test_local_motion_rejects_static_background():
    previous = np.zeros((180, 220), dtype=np.uint8)
    for x in (91, 99, 107):
        cv2.rectangle(previous, (x, 80), (x + 4, 84), 255, -1)
    moved = cv2.warpAffine(previous, np.array([[1, 0, 3], [0, 1, 0]], np.float32), (220, 180))
    before, after = pose(True), pose(True, 3)
    prior = (previous, 1.0, before, hand_geometry(before))
    current = (moved, 1.0, after, hand_geometry(after))
    stationary = (previous, 1.0, after, hand_geometry(after))
    assert _co_motion(prior, current)
    assert not _co_motion(prior, stationary)


def test_baseline_deceleration():
    frame = np.zeros((150, 200, 3), dtype=np.uint8)
    detector = EventDetector(mode="baseline")
    sequence = [(False, 0), (False, 7), (True, 8), (False, 9)]
    detections = [detector.process(i, frame, pose(closed, x)) for i, (closed, x) in enumerate(sequence)]
    assert detections == [None, None, Event(2, "agarrar", 2), Event(3, "soltar", 3)]


def test_events_configuration_errors():
    with pytest.raises(ValueError):
        EventDetector(options={"closed_threshold": 0.85})
    with pytest.raises(ValueError):
        EventDetector(options={"clave_invalida": False})
