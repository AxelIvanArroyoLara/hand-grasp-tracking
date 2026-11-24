"""Verifica geometría, recuperación óptica, preprocesamiento y continuidad temporal."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from src.preprocessing import Preprocessor
from src.tracking import LandmarkFilter, Tracker, hand_region, optical_recovery


def test_region_at_edge():
    """La inversión de la ROI usa la geometría del cuadro, incluso junto al borde."""
    points = np.repeat([[6., 95.]], 21, axis=0)
    points[-1] = [32., 104.]
    frame = np.zeros((120, 200, 3), np.uint8)
    region = hand_region(points, frame.shape)
    assert region.x == 0
    assert region.y + region.height == 120
    normalized = (points - [region.x, region.y]) / [region.width, region.height]
    np.testing.assert_allclose(region.to_frame(normalized), points)
    assert max(region.image(frame).shape[:2]) == 384


def test_adaptive_illumination_does_not_modify_original():
    """Gamma aclara cuadros oscuros y conserva cuadros bien iluminados."""
    dark = np.full((48, 64, 3), 32, np.uint8)
    bright = np.full_like(dark, 180)
    processor = Preprocessor({'illumination': 'gamma'})
    assert processor.apply(dark).mean() > dark.mean()
    assert dark.mean() == 32
    assert processor.apply(bright) is bright
    assert Preprocessor({}).apply(dark) is dark


def test_lk_translation_and_loss():
    """Comprueba una traslación controlada y el rechazo de señal sin textura."""
    rng = np.random.default_rng(31)
    image = rng.integers(0, 256, (160, 200), dtype=np.uint8)
    points = np.array([(40 + 12 * column, 45 + 14 * row)
                       for row in range(3) for column in range(7)], dtype=np.float32)
    moved = cv2.warpAffine(
        image, np.float32([[1, 0, 4], [0, 1, 3]]), (200, 160),
        borderMode=cv2.BORDER_REFLECT_101,
    )
    found = optical_recovery(image, moved, points)
    assert found is not None
    np.testing.assert_allclose(found, points + [4, 3], atol=0.15)
    assert optical_recovery(image, np.zeros_like(image), points) is None


@pytest.mark.parametrize('method', ('ema', 'one_euro', 'kalman'))
def test_smoothing_and_reinitialization(method):
    """Una pérdida prolongada reinicia el estado y devuelve ausencias en el intervalo."""
    initial = np.column_stack((np.arange(21), np.arange(21) * 2)).astype(np.float32)
    smoother = LandmarkFilter({'smoothing': method})
    np.testing.assert_array_equal(smoother.update(initial, 0), initial)
    updated = smoother.update(initial + 4, 33)
    assert np.all((updated > initial) & (updated < initial + 4))
    assert smoother.update(None, 66) is None
    np.testing.assert_array_equal(smoother.update(initial + 100, 200), initial + 100)


def test_kalman_rejects_isolated_outlier():
    """Una medición aislada muy distante no arrastra el estado del resto de la mano."""
    points = np.column_stack((np.arange(21), np.arange(21) * 2)).astype(np.float32)
    smoother = LandmarkFilter({'smoothing': 'kalman'})
    smoother.update(points, 0)
    outlier = points.copy()
    outlier[10] += 250
    np.testing.assert_array_equal(smoother.update(outlier, 33), points)


def test_missing_frame_does_not_reuse_stale_tracks(monkeypatch, tmp_path):
    """Corta el flujo al alcanzar el límite y reinicializa al volver MediaPipe."""
    model = tmp_path / 'modelo.task'
    model.touch()

    class Graph:
        """Reemplaza la instancia nativa para controlar las detecciones."""

        def close(self):
            """Libera el grafo simulado."""

    monkeypatch.setattr(Tracker, '_open', lambda self, mode: Graph())
    normalized = np.full((21, 2), 0.5)
    responses = iter((normalized, None, None, None, None, normalized))
    monkeypatch.setattr(Tracker, '_detect', lambda self, frame, ms: next(responses))
    monkeypatch.setattr('src.tracking.optical_recovery',
                        lambda previous, current, points, *args: points + 1)
    tracker = Tracker(model, {'flow': True, 'flow_max_frames': 2})
    frame = np.zeros((60, 80, 3), np.uint8)
    for idx, source in enumerate(('mediapipe', 'flow', 'flow', 'missing', 'missing', 'mediapipe')):
        result = tracker.process(frame, idx * 33)
        assert tracker.last_source == source
        assert (result is None) == (source == 'missing')
    with pytest.raises(ValueError, match='crecientes'):
        tracker.process(frame, 33)
    tracker.close()


def test_mediapipe_cpu_accepts_empty_video():
    """Abre el modelo real en CPU y mueve el reloj de un video sin mano."""
    model = Path(__file__).resolve().parents[1] / 'models' / 'hand_landmarker.task'
    if not model.is_file():
        pytest.skip('Modelo requerido para la integración de MediaPipe en CPU')
    tracker = Tracker(model, {})
    try:
        frame = np.zeros((120, 160, 3), np.uint8)
        assert tracker.process(frame, 0) is None
        assert tracker.process(frame, 33) is None
    finally:
        tracker.close()


def test_roi_uses_independent_inference_and_original_pixels(monkeypatch, tmp_path):
    """Confirma el uso de un recorte al perder el cuadro completo y su reproyección."""
    model = tmp_path / 'modelo.task'
    model.touch()
    monkeypatch.setattr(Tracker, '_open', lambda self, mode: None)
    calls = []
    full_points = np.repeat([[0.3, 0.4]], 21, axis=0)
    full_points[-1] = [0.5, 0.6]
    roi_points = np.repeat([[0.65, 0.35]], 21, axis=0)

    def detect(tracker, frame, ms):
        calls.append((frame.shape, ms))
        if ms == 0:
            return full_points
        if ms is None:
            return roi_points
        return None

    monkeypatch.setattr(Tracker, '_detect', detect)
    frame = np.zeros((120, 180, 3), np.uint8)
    tracker = Tracker(model, {'roi': True})
    first = tracker.process(frame, 0)
    np.testing.assert_allclose(first, full_points * [180, 120])
    region = hand_region(first, frame.shape)
    assert tracker.last_source == 'mediapipe'
    result = tracker.process(frame, 33)
    assert tracker.last_source == 'roi'
    np.testing.assert_allclose(result, region.to_frame(roi_points))
    assert calls[:2] == [(frame.shape, 0), (frame.shape, 33)]
    assert calls[-1] == (region.image(frame).shape, None)
