"""Métricas provisionales de pose y sucesos para evaluaciones por secuencia."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Sequence

import numpy as np

from .events import Event

KINDS = ("agarrar", "soltar")


def _ratio(numerator: float, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _landmarks(points: np.ndarray | None) -> np.ndarray:
    if points is None:
        return np.full((21, 2), np.nan)
    array = np.asarray(points, dtype=np.float64)
    if array.shape != (21, 2):
        raise ValueError("Se esperaban 21 pares de coordenadas.")
    return array


def _visible(points: np.ndarray, image_shape: Sequence[int] | None) -> np.ndarray:
    valid = np.isfinite(points).all(axis=1) & (points >= 0).all(axis=1)
    if image_shape is not None:
        height, width = image_shape[:2]
        valid &= (points[:, 0] < width) & (points[:, 1] < height)
    return valid


class TrackingMetrics:
    """Acumula pose en flujo con hasta dos cuadros de historia temporal."""

    def __init__(self, threshold_px: float = 10.0):
        if not np.isfinite(threshold_px) or threshold_px <= 0:
            raise ValueError("El umbral de PCK debe ser finito y positivo.")
        self.threshold_px = threshold_px
        self.frames = self.visible_frames = self.detected_frames = 0
        self.predicted_frames = self.empty_frames = self.false_detection_frames = 0
        self.visible_points = self.matched_points = self.correct_points = 0
        self.jitter_points = self.reference_jitter_points = 0
        self.jitter_sum = self.reference_jitter_sum = self.residual_jitter_sum = 0.0
        self.distance_sum = 0.0
        self._history: deque[tuple[np.ndarray, np.ndarray]] = deque(maxlen=2)
        self._last_frame: int | None = None

    def reset_sequence(self) -> None:
        """Interrumpe las diferencias temporales sin borrar los acumuladores."""
        self._history.clear()
        self._last_frame = None

    def update(
        self,
        prediction: np.ndarray | None,
        ground_truth: np.ndarray | None = None,
        image_shape: Sequence[int] | None = None,
        *,
        frame: int | None = None,
    ) -> np.ndarray:
        """Incorpora un cuadro y devuelve errores por punto cuando hay pareja.

        Una referencia ausente indica que se desconoce la visibilidad. Para
        indicar un cuadro anotado sin mano se usa una matriz de NaN.
        """
        predicted = _landmarks(prediction)
        expected = _landmarks(ground_truth)
        valid_pred = np.isfinite(predicted).all(axis=1)
        valid_truth = _visible(expected, image_shape)
        self.frames += 1
        found = bool(valid_pred.all())
        self.predicted_frames += found
        if ground_truth is not None:
            if valid_truth.any():
                self.visible_frames += 1
                self.detected_frames += found
            else:
                self.empty_frames += 1
                self.false_detection_frames += found

        matched = valid_truth & valid_pred
        errors = np.full(21, np.nan)
        errors[matched] = np.linalg.norm(predicted[matched] - expected[matched], axis=1)
        self.visible_points += int(valid_truth.sum())
        self.matched_points += int(matched.sum())
        self.correct_points += int((errors <= self.threshold_px).sum())
        self.distance_sum += float(errors[matched].sum())

        if frame is not None and self._last_frame is not None and frame != self._last_frame + 1:
            self.reset_sequence()
        self._last_frame = frame
        pose_for_jitter = predicted.copy()
        pose_for_jitter[~(matched if ground_truth is not None else valid_pred)] = np.nan
        reference_for_jitter = expected.copy()
        reference_for_jitter[~matched] = np.nan
        if len(self._history) == 2:
            (first, reference_first), (second, reference_second) = self._history
            acceleration = pose_for_jitter - 2 * second + first
            jitter = np.linalg.norm(acceleration, axis=1)
            valid_jitter = np.isfinite(jitter)
            self.jitter_points += int(valid_jitter.sum())
            self.jitter_sum += float(jitter[valid_jitter].sum())
            reference = reference_for_jitter - 2 * reference_second + reference_first
            reference_jitter = np.linalg.norm(reference, axis=1)
            valid_reference = np.isfinite(reference_jitter) & valid_jitter
            self.reference_jitter_points += int(valid_reference.sum())
            self.reference_jitter_sum += float(reference_jitter[valid_reference].sum())
            residual = acceleration[valid_reference] - reference[valid_reference]
            self.residual_jitter_sum += float(np.linalg.norm(residual, axis=1).sum())
        self._history.append((pose_for_jitter, reference_for_jitter))
        return errors

    def result(self) -> dict[str, int | float | None]:
        """Devuelve tasas como fracciones y temblor en píxeles por cuadro al cuadrado."""
        return {
            "frames": self.frames,
            "visible_frames": self.visible_frames,
            "detected_frames": self.detected_frames,
            "predicted_frames": self.predicted_frames,
            "empty_frames": self.empty_frames,
            "false_detection_frames": self.false_detection_frames,
            "detection_rate": _ratio(self.detected_frames, self.visible_frames),
            "prediction_rate": _ratio(self.predicted_frames, self.frames),
            "visible_points": self.visible_points,
            "matched_points": self.matched_points,
            "correct_points": self.correct_points,
            "landmark_coverage": _ratio(self.matched_points, self.visible_points),
            "pck_10": _ratio(self.correct_points, self.visible_points),
            "pck_10_conditional": _ratio(self.correct_points, self.matched_points),
            "mean_error_px": _ratio(self.distance_sum, self.matched_points),
            "jitter_px": _ratio(self.jitter_sum, self.jitter_points),
            "jitter_points": self.jitter_points,
            "reference_jitter_px": _ratio(self.reference_jitter_sum, self.reference_jitter_points),
            "residual_jitter_px": _ratio(self.residual_jitter_sum, self.reference_jitter_points),
            "reference_jitter_points": self.reference_jitter_points,
            "distance_sum": self.distance_sum,
            "jitter_sum": self.jitter_sum,
            "reference_jitter_sum": self.reference_jitter_sum,
            "residual_jitter_sum": self.residual_jitter_sum,
        }


def match_events(
    predicted: Iterable[Event],
    expected: Iterable[Event],
    tolerance: int = 5,
) -> list[tuple[Event, Event]]:
    """Maximiza parejas del mismo tipo y minimiza el error absoluto en empates."""
    if tolerance < 0:
        raise ValueError("La tolerancia no puede ser negativa.")
    predictions = tuple(predicted)
    references = tuple(expected)
    matches = []
    for kind in KINDS:
        candidates = sorted((e for e in predictions if e.kind == kind), key=lambda e: e.frame)
        truths = sorted((e for e in references if e.kind == kind), key=lambda e: e.frame)
        n, m = len(candidates), len(truths)
        if not n or not m:
            continue
        scores = [(0, 0)] * (m + 1)
        choices = [bytearray(m + 1) for _ in range(n + 1)]
        for i, candidate in enumerate(candidates, 1):
            above = scores
            scores = [(0, 0)]
            for j, truth in enumerate(truths, 1):
                best, choice = above[j], 1
                if scores[j - 1] > best:
                    best, choice = scores[j - 1], 2
                distance = abs(candidate.frame - truth.frame)
                count, negative_error = above[j - 1]
                if distance <= tolerance and (count + 1, negative_error - distance) >= best:
                    best, choice = (count + 1, negative_error - distance), 3
                scores.append(best)
                choices[i][j] = choice
        i, j = n, m
        while i and j:
            choice = choices[i][j]
            if choice == 3:
                matches.append((candidates[i - 1], truths[j - 1]))
                i, j = i - 1, j - 1
            elif choice == 1:
                i -= 1
            else:
                j -= 1
    return sorted(matches, key=lambda pair: (pair[0].frame, pair[0].kind))


class _EventCounts:
    """Contadores agregables para tiempos y clasificación."""

    def __init__(self) -> None:
        self.tp = self.fp = self.fn = self.absolute_error = self.signed_error = 0

    def result(self) -> dict[str, int | float | None]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": _ratio(self.tp, self.tp + self.fp),
            "recall": _ratio(self.tp, self.tp + self.fn),
            "f1": _ratio(2 * self.tp, 2 * self.tp + self.fp + self.fn),
            "mae_frames": _ratio(self.absolute_error, self.tp),
            "bias_frames": _ratio(self.signed_error, self.tp),
            "absolute_error_sum": self.absolute_error,
            "signed_error_sum": self.signed_error,
        }


class EventMetrics:
    """Acumula los conteos micro sin permitir parejas entre videos o cámaras."""

    def __init__(self, tolerance: int = 5):
        if tolerance < 0:
            raise ValueError("La tolerancia no puede ser negativa.")
        self.tolerance = tolerance
        self._counts = {kind: _EventCounts() for kind in KINDS}
        self._seen: set[str] = set()

    def update(
        self,
        predicted: Iterable[Event],
        expected: Iterable[Event],
        kinds: Sequence[str] = KINDS,
    ) -> list[tuple[Event, Event]]:
        """Evalúa una secuencia independiente para los tipos solicitados."""
        selected = set(kinds)
        if not selected <= set(KINDS):
            raise ValueError("Tipo de evento no admitido.")
        self._seen.update(selected)
        predictions = [event for event in predicted if event.kind in selected]
        references = [event for event in expected if event.kind in selected]
        matches = match_events(predictions, references, self.tolerance)
        for kind in selected:
            deltas = [p.frame - g.frame for p, g in matches if p.kind == kind]
            counts = self._counts[kind]
            counts.tp += len(deltas)
            counts.fp += sum(e.kind == kind for e in predictions) - len(deltas)
            counts.fn += sum(e.kind == kind for e in references) - len(deltas)
            counts.absolute_error += sum(map(abs, deltas))
            counts.signed_error += sum(deltas)
        return matches

    def result(self) -> dict:
        """Devuelve resultados micro y desglosados por cada tipo evaluado."""
        total = _EventCounts()
        for counts in self._counts.values():
            total.tp += counts.tp
            total.fp += counts.fp
            total.fn += counts.fn
            total.absolute_error += counts.absolute_error
            total.signed_error += counts.signed_error
        return {
            **total.result(),
            "by_kind": {kind: self._counts[kind].result() for kind in KINDS if kind in self._seen},
        }
