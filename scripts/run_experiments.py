"""Ejecuta comparaciones DexYCB en CPU con caché por vista y selección en validación."""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import resource
import subprocess
from tempfile import NamedTemporaryFile
from time import perf_counter

import cv2
import numpy as np
import yaml

from src.contracts import MODEL, ROOT, load_mapping
from src.datasets.dexycb import FPS, discover, grasp_onset, split_sequences
from src.evaluation import EventMetrics, TrackingMetrics
from src.events import Event, EventDetector
from src.input import timestamps
from src.tracking import Tracker

EVENT_VARIANTS = {"sin_movimiento": {"motion_gate": False},
                  "una_confirmacion": {"confirm_frames": 1},
                  "mas_confirmacion": {"confirm_frames": 4},
                  "apertura_alta": {"closed_threshold": 0.82, "open_threshold": 0.91}}


def save_json(path, value):
    """Publica un checkpoint completo mediante reemplazo atómico."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", dir=path.parent, delete=False, encoding="utf-8") as tmp:
        json.dump(value, tmp, indent=2, allow_nan=False)
        tmp.write("\n")
    Path(tmp.name).replace(path)


def context(model):
    """Identifica modelo, implementación y librerías que afectan la inferencia."""
    code = hashlib.sha256()
    for path in sorted((ROOT / "src").rglob("*.py")):
        code.update(str(path.relative_to(ROOT)).encode())
        code.update(path.read_bytes())
    versions = {name: importlib.metadata.version(name) for name in ("mediapipe", "opencv-contrib-python", "numpy")}
    return {"code_sha256": code.hexdigest(), "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
            "versions": versions, "delegate": "CPU", "fps": FPS}


def identify_view(view):
    """Incluye las rutas y los metadatos de los JPEG para invalidar reemplazos."""
    digest = hashlib.sha256(str(view.path.resolve()).encode())
    for frame in view.frames():
        stat = frame.color.stat()
        digest.update(f"{frame.index}:{stat.st_size}:{stat.st_mtime_ns}".encode())
    return digest.hexdigest()


def infer(view, options, model, base, cache, view_hash, variants):
    """Produce landmarks y eventos desde RGB. Las etiquetas se leen fuera de esta función."""
    key_data = [base, view_hash, options, variants]
    key = hashlib.sha256(json.dumps(key_data, sort_keys=True).encode()).hexdigest()
    target = cache / f"{key}.npz"
    if target.is_file():
        with np.load(target, allow_pickle=False) as archive:
            return (archive["points"], archive["shapes"], json.loads(archive["info"].item()), True)
    tracker = Tracker(model, options)
    detectors = {name: EventDetector(mode, params) for name, (mode, params) in variants.items()}
    point_rows, shapes = [], []
    events = {name: [] for name in variants}
    elapsed_frames = []
    sources = Counter()
    stamp = -1
    try:
        for ref in view.frames():
            start = perf_counter()
            frame = cv2.imread(str(ref.color))
            if frame is None:
                raise ValueError(f"Imagen ilegible {ref.color}")
            stamp = timestamps(ref.index, FPS, stamp)
            points = tracker.process(frame, stamp)
            for name, detector in detectors.items():
                event = detector.process(ref.index, frame, points)
                if event:
                    events[name].append([event.frame, event.kind, event.confirmed_frame])
            elapsed_frames.append(perf_counter() - start)
            point_rows.append(points if points is not None else np.full((21, 2), np.nan))
            shapes.append(frame.shape[:2])
            sources[tracker.last_source] += 1
    finally:
        tracker.close()
    points, shapes = np.asarray(point_rows), np.asarray(shapes)
    info = {"sources": dict(sources), "seconds": sum(elapsed_frames), "events": events,
            "latency_p95_ms": float(np.quantile(elapsed_frames, 0.95) * 1000)}
    with NamedTemporaryFile(dir=cache, suffix=".npz", delete=False) as temp:
        np.savez_compressed(temp, points=points, shapes=shapes, info=json.dumps(info))
    Path(temp.name).replace(target)
    return points, shapes, info, False


def prepare(root, options, partition, limit, cameras, output, selected_names=None):
    """Fija las tomas antes de leer anotaciones y conserva cámaras dentro de cada toma."""
    sequences = discover(root)
    split = split_sequences(sequences, options["seed"])
    save_json(output / "splits.json", split)
    names = split["splits"][partition]
    if selected_names is not None:
        if not set(selected_names) <= set(names):
            raise ValueError("La selección de prueba congelada ya no corresponde a las particiones")
        names = selected_names
    elif limit:
        names = names[:limit]
    by_name = {seq.name: seq for seq in sequences}
    prepared = []
    for name in names:
        sequence = by_name[name]
        views = [v for v in sequence.views if not cameras or v.camera in cameras]
        if not views:
            raise ValueError(f"Ninguna cámara pedida está disponible en {name}")
        onset = grasp_onset(sequence)
        for view in views:
            truth = np.array([frame.labels().joints for frame in view.frames()])
            prepared.append((name, view, truth, onset, identify_view(view)))
    if not prepared:
        raise ValueError(f"La partición {partition} no tiene vistas en el subconjunto")
    return prepared


def benchmark(prepared, variants, args, base, out, tolerance):
    """Compara todos los métodos sobre las mismas vistas y genera evidencia por vista."""
    result_rows = []
    args.cache.mkdir(parents=True, exist_ok=True)
    for name, setup in variants.items():
        options, designated_mode, event_options = setup
        detectors = {"primary": (designated_mode, event_options)}
        if args.tune_events and designated_mode == "proposed":
            detectors.update({n: ("proposed", params) for n, params in EVENT_VARIANTS.items()})
        aggregate = TrackingMetrics()
        event_metrics = {n: EventMetrics(tolerance) for n in detectors}
        details, sources, failures = [], Counter(), []
        seconds = 0
        for seq, view, truth, onset, view_hash in prepared:
            predictions, shapes, info, reused = infer(view, options, args.modelo, base, args.cache, view_hash, detectors)
            aggregate.reset_sequence()
            local = TrackingMetrics()
            for index, (points, target, shape) in enumerate(zip(predictions, truth, shapes, strict=True)):
                errors = aggregate.update(points, target, shape, frame=index)
                local.update(points, target, shape, frame=index)
                if not np.isfinite(errors).any():
                    if np.isfinite(target).sum() >= 32:
                        failures.append((1e6, seq, view.camera, index))
                elif np.nanmedian(errors) >= 15:
                    failures.append((float(np.nanmedian(errors)), seq, view.camera, index))
            per_events = EventMetrics(tolerance)
            if onset is not None:
                for detector_name, metric in event_metrics.items():
                    predicted = [Event(*e) for e in info["events"][detector_name]]
                    expected = [Event(onset, "agarrar")]
                    metric.update(predicted, expected, ("agarrar",))
                    if detector_name == "primary":
                        per_events.update(predicted, expected, ("agarrar",))
            details.append({"sequence": seq, "camera": view.camera, "tracking": local.result(),
                            "events": per_events.result(), "expected_grasp": onset,
                            "predicted_events": info["events"]["primary"],
                            "seconds": info["seconds"], "p95_ms": info["latency_p95_ms"], "cache": reused})
            seconds += info["seconds"]
            sources.update(info["sources"])
            print(name, seq, view.camera, f"{len(predictions)} cuadros", "caché" if reused else "CPU", flush=True)
        metrics = aggregate.result()
        result_rows.append({"name": name, "tracking_options": options, "event_mode": designated_mode,
                            "event_options": event_options, **metrics,
                            **event_metrics["primary"].result(), "sources": dict(sources),
                            "event_candidates": {n: m.result() for n, m in event_metrics.items()},
                            "views": len(details), "sequences": len({d["sequence"] for d in details}),
                            "seconds": seconds, "fps": metrics["frames"] / seconds,
                            "mean_latency_ms": 1000 * seconds / metrics["frames"],
                            "memory_peak_bytes": peak_memory(),
                            "details": details, "failures": sorted(failures, reverse=True)[:12]})
        save_json(out / "checkpoint.json", result_rows)
    return result_rows


def peak_memory():
    """Normaliza RSS pico a bytes según la plataforma."""
    import sys
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == "darwin" else value * 1024


def select(rows):
    """Selecciona configuración por PCK, cobertura, temblor y coste, con tres técnicas."""
    baseline = rows[0]
    qualifying = []
    for row in rows[1:]:
        if row["name"] in {"completo", "completo_rapido"}:
            qualifying.append(row)
    def score(row):
        wins = sum((row[key] or 0) > (baseline[key] or 0) for key in ("pck_10", "detection_rate"))
        wins += (row["jitter_px"] or float("inf")) < (baseline["jitter_px"] or float("inf"))
        return wins, row["pck_10"] or 0, row["detection_rate"] or 0, -(row["jitter_px"] or 0), row["fps"]
    chosen = max(qualifying, key=score)
    event = max(chosen["event_candidates"], key=lambda v: (chosen["event_candidates"][v]["f1"] or 0, v == "primary"))
    return chosen, (chosen["event_options"] if event == "primary" else EVENT_VARIANTS[event])


def save_csv(path, rows):
    """Escribe la tabla plana de las métricas comparables."""
    fields = ("name", "sequences", "views", "frames", "detection_rate", "pck_10", "pck_10_conditional",
              "jitter_px", "reference_jitter_px", "residual_jitter_px", "precision", "recall", "f1",
              "mae_frames", "tp", "fp", "fn", "seconds", "fps", "mean_latency_ms", "memory_peak_bytes")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    """Ejecuta desarrollo, validación o una prueba con configuración congelada."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datos", required=True, type=Path)
    parser.add_argument("--particion", choices=("development", "validation", "test"), default="development")
    parser.add_argument("--salida", required=True, type=Path)
    parser.add_argument("--modelo", default=MODEL, type=Path)
    parser.add_argument("--cache", default=ROOT / "experiments/cache", type=Path)
    parser.add_argument("--limite", default=0, type=int)
    parser.add_argument("--camara", action="append", default=[])
    parser.add_argument("--variantes", nargs="+")
    parser.add_argument("--tune-events", action="store_true")
    parser.add_argument("--congelado", type=Path)
    opt = parser.parse_args()
    cfg = load_mapping(ROOT / "configs/experiments.yaml")
    if opt.limite < 0:
        parser.error("El límite debe ser no negativo")
    if opt.particion == "test" and (not opt.congelado or opt.tune_events or opt.variantes or opt.limite or opt.camara):
        parser.error("Prueba requiere --congelado y hereda selección y cámaras de validación")
    if opt.particion != "test" and opt.congelado:
        parser.error("--congelado se aplica únicamente a prueba")
    cv2.setNumThreads(1)
    opt.salida.mkdir(parents=True, exist_ok=True)
    base = context(opt.modelo)
    configurations = load_mapping(ROOT / "configs/ablation.yaml")
    if opt.particion == "test":
        frozen = json.loads(opt.congelado.read_text())
        if frozen["context"] != base or frozen["settings"] != cfg:
            raise ValueError("Cambió la implementación, el modelo o el protocolo después de congelar")
        opt.camara = frozen["cameras"]
        names, limit = frozen["test_sequences"], 0
        variants = {"baseline": ({}, "baseline", {}),
                    "seleccionado": (frozen["tracking"], "proposed", frozen["events"])}
    else:
        names, limit = None, opt.limite
        variants = {name: (configurations[name], "baseline" if name == "baseline" else "proposed", {})
                    for name in (opt.variantes or configurations)}
    started = perf_counter()
    prepared = prepare(opt.datos, cfg, opt.particion, limit, opt.camara, opt.salida, names)
    running = {"id": opt.salida.name, "status": "running", "context": base, "settings": cfg,
               "started_utc": datetime.now(timezone.utc).isoformat(), "partition": opt.particion,
               "git": subprocess.getoutput("git rev-parse HEAD"), "cameras": opt.camara}
    save_json(opt.salida / "manifest.json", running)
    try:
        rows = benchmark(prepared, variants, opt, base, opt.salida, cfg["tolerance"])
        save_json(opt.salida / "ablation.json", rows)
        save_csv(opt.salida / "ablation.csv", rows)
        if opt.particion == "validation" and not opt.variantes:
            chosen, event_options = select(rows)
            names = json.loads((opt.salida / "splits.json").read_text())["splits"]["test"]
            frozen = {"context": base, "settings": cfg, "cameras": opt.camara, "test_sequences": names,
                      "tracking": chosen["tracking_options"], "events": event_options, "name": chosen["name"]}
            save_json(opt.salida / "frozen.json", frozen)
            (opt.salida / "selected.yaml").write_text(yaml.safe_dump({"tracking": frozen["tracking"],
                "events": {"mode": "proposed", **event_options}}, sort_keys=False), encoding="utf-8")
        running.update(status="complete", seconds=perf_counter() - started)
    except Exception as exc:
        running.update(status="failed", seconds=perf_counter() - started, error=str(exc))
        raise
    finally:
        save_json(opt.salida / "manifest.json", running)


if __name__ == "__main__":
    main()
