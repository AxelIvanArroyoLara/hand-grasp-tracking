"""Pruebas del decodificador de puntajes y los rasgos causales del clasificador."""

import numpy as np

from scripts.compare_event_classifiers import Sample, decode_events, frame_features, train_and_compare
from src.events import Event


def test_score_regions_and_gaps():
    frames = np.array([2, 3, 4, 8, 9, 17, 18])
    scores = np.array([0.65, 0.9, 0.70, 0.8, 0.45, 0.7, 0.85])
    assert decode_events(frames, scores, 0.5) == [Event(3, "agarrar", 4), Event(18, "agarrar", 18)]


def test_features_restart_after_a_missing_pose():
    points = np.arange(42, dtype=float).reshape(21, 2)
    poses = np.stack([points, points + 1, points + 2, points * np.nan,
                      points + 4, points + 5, points + 6])
    indices, features = frame_features(poses)
    assert indices.tolist() == [2, 6]
    assert features.shape == (2, 8)
    assert np.isfinite(features).all()



def test_classifiers_fit_development_and_score_independent_validation():
    frames = np.arange(15)
    features = np.zeros((15, 8))
    features[5:10] = 1.0
    development = [Sample("toma-desarrollo", "vista", frames, features, 7, [])]
    validation = [Sample("toma-validacion", "vista", frames, features, 7, [])]
    rows, counts = train_and_compare(development, validation, seed=6, tolerance=5)
    assert counts == {"positive": 5, "negative": 10}
    assert {row["model"] for row in rows} == {
        "reglas", "umbral_adaptativo", "regresion_logistica", "svm_rbf", "knn"
    }
    assert max(row["f1"] for row in rows if row["model"] == "regresion_logistica") == 1.0
