"""Pruebas de cobertura, PCK, temblor y correspondencia temporal."""

import numpy as np
import pytest

from src.evaluation import EventMetrics, TrackingMetrics, match_events
from src.events import Event


def test_missing_predictions_count_in_pck_and_detection_denominators():
    metric = TrackingMetrics()
    truth = np.full((21, 2), 20.0)
    prediction = truth + [10, 0]
    prediction[3] = truth[3] + [10.01, 0]
    truth[0] = np.nan
    truth[1] = [-1, -1]
    truth[2] = [100, 5]
    metric.update(prediction, truth, (100, 100))
    metric.update(None, truth, (100, 100))
    metric.update(prediction, np.full((21, 2), -1.0), (100, 100))
    result = metric.result()
    assert result["visible_frames"] == 2
    assert result["detection_rate"] == pytest.approx(0.5)
    assert result["prediction_rate"] == pytest.approx(2 / 3)
    assert result["false_detection_frames"] == 1
    assert result["matched_points"] == 18
    assert result["pck_10"] == pytest.approx(17 / 36)
    assert result["pck_10_conditional"] == pytest.approx(17 / 18)


def test_jitter_uses_consecutive_covisible_triplets():
    metric = TrackingMetrics()
    truth = np.full((21, 2), 10.0)
    for index, value in enumerate([0, 1, 4]):
        metric.update(truth + [value, 0], truth, frame=index)
    metric.update(truth + [400, 0], truth, frame=20)
    metric.reset_sequence()
    metric.update(truth + [10000, 0], truth, frame=0)
    result = metric.result()
    assert result["jitter_points"] == 21
    assert result["jitter_px"] == pytest.approx(2.0)
    assert result["reference_jitter_px"] == pytest.approx(0.0)
    assert result["residual_jitter_px"] == pytest.approx(2.0)


def test_unknown_reference_keeps_only_descriptive_metrics():
    metric = TrackingMetrics()
    for value in [7, 8, 9]:
        metric.update(np.full((21, 2), value))
    result = metric.result()
    assert result["detection_rate"] is None
    assert result["pck_10"] is None
    assert result["prediction_rate"] == 1.0
    assert result["jitter_px"] == 0.0
    assert result["reference_jitter_px"] is None


def test_event_matching_prefers_two_pairs_over_nearest_first():
    predictions = [Event(1, "agarrar"), Event(5, "agarrar")]
    expected = [Event(4, "agarrar"), Event(9, "agarrar")]
    assert match_events(predictions, expected, tolerance=4) == list(zip(predictions, expected))


def test_event_matching_prefers_lowest_absolute_error_in_a_tie():
    expected = [Event(4, "agarrar")]
    predictions = [Event(2, "agarrar"), Event(5, "agarrar")]
    assert match_events(predictions, expected) == [(predictions[1], expected[0])]


def test_events_are_matched_per_type_and_per_sequence():
    metric = EventMetrics()
    metric.update([Event(8, "agarrar"), Event(10, "agarrar"), Event(12, "soltar")],
                  [Event(7, "agarrar")])
    metric.update([], [Event(8, "agarrar"), Event(12, "soltar")], kinds=("agarrar",))
    result = metric.result()
    assert (result["tp"], result["fp"], result["fn"]) == (1, 2, 1)
    assert result["precision"] == pytest.approx(1 / 3)
    assert result["recall"] == pytest.approx(0.5)
    assert result["f1"] == pytest.approx(0.4)
    assert result["mae_frames"] == 1
    assert result["bias_frames"] == 1
    assert result["by_kind"]["soltar"]["fn"] == 0
