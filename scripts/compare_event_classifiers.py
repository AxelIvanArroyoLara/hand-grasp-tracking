"""Compara clasificadores RGB de agarre en desarrollo y validación de DexYCB."""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
import subprocess
from time import perf_counter

import cv2
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from threadpoolctl import threadpool_limits

from scripts.run_experiments import EVENT_VARIANTS, context, identify_view, infer, save_json
from src.contracts import MODEL, ROOT, load_mapping
from src.datasets.dexycb import discover, grasp_onset, split_sequences
from src.evaluation import EventMetrics
from src.events import Event, hand_geometry


@dataclass(frozen=True)
class Sample:
    """Rasgos para una vista, cuadro de referencia y salidas heurísticas."""

    sequence: str
    camera: str
    indices: np.ndarray
    features: np.ndarray
    onset: int
    heuristic_events: list[Event]


def frame_features(poses: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Extrae geometría y cambios causales descartando intervalos sin pose."""
    frames = []
    rows = []
    previous = None
    speed_previous = None
    recent_aperture = deque(maxlen=12)
    for index, points in enumerate(poses):
        geometry = hand_geometry(points)
        if geometry is None or previous is None:
            previous = geometry
            speed_previous = None
            recent_aperture.clear()
            if geometry is not None:
                recent_aperture.append(geometry.aperture)
            continue
        speed = float(np.linalg.norm(geometry.center - previous.center) / geometry.palm_scale)
        if speed_previous is not None:
            rows.append([
                geometry.aperture, geometry.extension, geometry.pinch,
                geometry.aperture - previous.aperture,
                geometry.pinch - previous.pinch, speed, speed - speed_previous,
                max(recent_aperture) - geometry.aperture,
            ])
            frames.append(index)
        previous = geometry
        speed_previous = speed
        recent_aperture.append(geometry.aperture)
    return np.asarray(frames, dtype=int), np.asarray(rows, dtype=float).reshape(-1, 8)


def decode_events(indices: np.ndarray, scores: np.ndarray, threshold: float) -> list[Event]:
    """Devuelve máximos de episodios sobre el umbral con un intervalo refractario."""
    scores = np.asarray(scores)
    if scores.shape != indices.shape or scores.ndim != 1:
        raise ValueError("Índices y puntajes deben ser vectores del mismo tamaño.")
    active = np.flatnonzero(scores >= threshold)
    if not len(active):
        return []
    regions = np.split(active, np.flatnonzero(np.diff(indices[active]) > 1) + 1)
    peaks = []
    for region in regions:
        best = region[np.argmax(scores[region])]
        peaks.append((scores[best], int(indices[best]), int(indices[region[-1]])))
    accepted: list[Event] = []
    for _, peak, end in sorted(peaks, key=lambda item: (-item[0], item[1])):
        if all(abs(event.frame - peak) >= 8 for event in accepted):
            accepted.append(Event(peak, "agarrar", end))
    return sorted(accepted, key=lambda event: event.frame)


def samples(sequences, config, args, base, split, partition, limit):
    """Recorre vistas de una sola partición y conserva únicamente rasgos compactos."""
    options = config["tracking"]
    event_options = config["events"].copy()
    mode = event_options.pop("mode", "proposed")
    detector = {"primary": (mode, event_options)}
    if args.reusar_busqueda and mode == "proposed":
        detector.update({name: ("proposed", options) for name, options in EVENT_VARIANTS.items()})
    selected = split["splits"][partition]
    if limit:
        selected = selected[:limit]
    by_name = {sequence.name: sequence for sequence in sequences}
    skipped = 0
    views = []
    for name in selected:
        sequence = by_name[name]
        onset = grasp_onset(sequence)
        if onset is None:
            skipped += 1
            continue
        for view in sequence.views:
            if args.camara and view.camera not in args.camara:
                continue
            points, _, info, reused = infer(
                view, options, args.modelo, base, args.cache, identify_view(view), detector,
            )
            frames, features = frame_features(points)
            predicted = [Event(*values) for values in info["events"]["primary"]]
            views.append(Sample(name, view.camera, frames, features, onset, predicted))
            print(partition, name, view.camera, len(features), "rasgos", "caché" if reused else "CPU", flush=True)
    if not views:
        raise ValueError(f"La partición {partition} no tiene vistas con agarre de referencia.")
    return views, skipped


def train_and_compare(development, validation, seed, tolerance):
    """Ajusta en desarrollo, evalúa umbrales finitos en validación y devuelve métricas."""
    development_ids = {sample.sequence for sample in development}
    validation_ids = {sample.sequence for sample in validation}
    if not development_ids or not validation_ids or development_ids & validation_ids:
        raise ValueError("Se requieren grupos independientes para desarrollo y validación.")
    features = np.concatenate([sample.features for sample in development])
    labels = np.concatenate([abs(sample.indices - sample.onset) <= 2 for sample in development])
    if np.unique(labels).size < 2 or len(features) < 5:
        raise ValueError("Desarrollo requiere rasgos válidos positivos y negativos para comparar.")
    candidates = (
        ("regresion_logistica", LogisticRegression(class_weight="balanced", solver="liblinear", max_iter=500, random_state=seed),
         (0.35, 0.50, 0.65)),
        ("svm_rbf", SVC(C=1.0, class_weight="balanced"), (-0.25, 0.0, 0.25)),
        ("knn", KNeighborsClassifier(n_neighbors=5, weights="distance", n_jobs=1), (0.20, 0.35, 0.50)),
    )

    heuristic = EventMetrics(tolerance)
    for sample in validation:
        truth = [Event(sample.onset, "agarrar")]
        heuristic.update(sample.heuristic_events, truth, ("agarrar",))
    rows = [{"model": "reglas", "threshold": None, **heuristic.result()}]
    for threshold in (0.025, 0.05, 0.10):
        adaptive = EventMetrics(tolerance)
        for sample in validation:
            truth = [Event(sample.onset, "agarrar")]
            predicted = decode_events(sample.indices, sample.features[:, -1], threshold)
            adaptive.update(predicted, truth, ("agarrar",))
        rows.append({"model": "umbral_adaptativo", "threshold": threshold, **adaptive.result()})
    for name, estimator, thresholds in candidates:
        started = perf_counter()
        pipeline = make_pipeline(StandardScaler(), estimator).fit(features, labels)
        training_seconds = perf_counter() - started
        started = perf_counter()
        scores = []
        for sample in validation:
            if not len(sample.features):
                score = np.empty(0)
            elif name == "svm_rbf":
                score = pipeline.decision_function(sample.features)
            else:
                score = pipeline.predict_proba(sample.features)[:, 1]
            if not np.isfinite(score).all():
                raise ValueError(f"El candidato {name} produjo puntajes no finitos.")
            scores.append(score)
        scoring_seconds = perf_counter() - started
        for threshold in thresholds:
            evaluation = EventMetrics(tolerance)
            for sample, score in zip(validation, scores, strict=True):
                expected = [Event(sample.onset, "agarrar")]
                predicted = decode_events(sample.indices, score, threshold)
                evaluation.update(predicted, expected, ("agarrar",))
            rows.append({
                "model": name,
                "threshold": threshold,
                "fit_seconds": training_seconds,
                "scoring_seconds": scoring_seconds,
                **evaluation.result(),
            })
    return rows, {"positive": int(labels.sum()), "negative": int((~labels).sum())}


def main():
    """Ejecuta el estudio exploratorio evitando la partición local de prueba."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datos", type=Path, required=True)
    parser.add_argument("--salida", type=Path, required=True)
    parser.add_argument("--modelo", default=MODEL, type=Path)
    parser.add_argument("--config", default=ROOT / "configs/proposed.yaml", type=Path)
    parser.add_argument("--cache", default=ROOT / "experiments/cache", type=Path)
    parser.add_argument("--camara", action="append", default=[])
    parser.add_argument("--reusar-busqueda", action="store_true",
                        help="usa las entradas de caché generadas por --tune-events")
    parser.add_argument("--limite-desarrollo", type=int, default=8)
    parser.add_argument("--limite-validacion", type=int, default=5)
    args = parser.parse_args()
    if min(args.limite_desarrollo, args.limite_validacion) < 0:
        parser.error("Los límites deben ser no negativos. Cero toma toda la partición.")
    cv2.setNumThreads(1)
    started = perf_counter()
    settings = load_mapping(ROOT / "configs/experiments.yaml")
    config = load_mapping(args.config)
    base = context(args.modelo)
    sequences = discover(args.datos)
    split = split_sequences(sequences, settings["seed"])
    args.cache.mkdir(parents=True, exist_ok=True)
    development, missing_dev = samples(sequences, config, args, base, split, "development", args.limite_desarrollo)
    validation, missing_val = samples(sequences, config, args, base, split, "validation", args.limite_validacion)
    with threadpool_limits(limits=1):
        rows, label_counts = train_and_compare(development, validation, settings["seed"], settings["tolerance"])
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    save_json(args.salida, {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "context": base,
        "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "git": commit.stdout.strip() if commit.returncode == 0 else None,
        "scikit_learn_version": version("scikit-learn"),
        "settings": settings,
        "config": config,
        "development": [[s.sequence, s.camera] for s in development],
        "validation": [[s.sequence, s.camera] for s in validation],
        "sequences_without_onset": {"development": missing_dev, "validation": missing_val},
        "training_label_counts": label_counts,
        "validation_views": [
            {"sequence": sample.sequence, "camera": sample.camera, "frames_with_features": len(sample.features)}
            for sample in validation
        ],
        "tested_event_types": ["agarrar"],
        "seconds": perf_counter() - started,
        "results": rows,
    })
    print(args.salida)


if __name__ == "__main__":
    main()
