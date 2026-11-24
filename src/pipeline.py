"""Inferencia por streaming y publicación de las salidas del contrato."""

import csv
import json
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import cv2

from src.contracts import EVENT_COLUMNS, POINT_COLUMNS, ROOT, load_mapping, valid_points
from src.events import EventDetector
from src.input import Frames, timestamps
from src.tracking import Tracker
from src.visualization import overlay, video_writer


def components(model, configuration):
    """Construye un detector de eventos y un rastreador con la configuración indicada."""
    config = load_mapping(configuration)
    if set(config) != {"tracking", "events"} or not all(isinstance(v, dict) for v in config.values()):
        raise ValueError(f"Configuración inválida en {configuration}")
    event_params = config["events"].copy()
    mode = event_params.pop("mode", "proposed")
    detector = EventDetector(mode, event_params)
    return Tracker(model, config["tracking"]), detector


def run(entrada: Path, salida: Path, model: Path, config: Path, fps=30, origin=0,
        video=False, comparison=False, timings=False):
    """Escribe una fila por cuadro y conserva las salidas previas si falla el procesamiento."""
    if not model.is_file():
        raise FileNotFoundError(f"Modelo ausente en {model}. Ejecuta python -m scripts.setup")
    cv2.setNumThreads(1)
    salida.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=salida, prefix=".inferencia-") as tmp, ExitStack() as stack:
        temp = Path(tmp)
        frames = stack.enter_context(Frames(entrada, fps))
        tracker, detector = components(model, config)
        stack.callback(tracker.close)
        baseline = None
        if comparison:
            baseline, baseline_events = components(model, ROOT / "configs/baseline.yaml")
            stack.callback(baseline.close)
        visuals = {}
        last_events = {}
        index, stamp = -1, -1
        started = perf_counter()
        events = []
        with (temp / "puntos.csv").open("w", newline="", encoding="utf-8") as points_file:
            points_csv = csv.writer(points_file)
            points_csv.writerow(POINT_COLUMNS)
            for index, frame in enumerate(frames):
                stamp = timestamps(index, frames.fps, stamp)
                points = tracker.process(frame, stamp)
                event = detector.process(index, frame, points)
                if event is not None:
                    last_events["proposed"] = event
                    events.append((event.frame + origin, event.kind))
                points_csv.writerow([index + origin, *(points.round(4).ravel() if valid_points(points) else [""] * 42)])
                if not (video or comparison):
                    continue
                latest = last_events.get("proposed")
                proposed = overlay(frame, points, index + origin, "Sistema propuesto",
                                   latest if latest and index - latest.frame < frames.fps else None)
                outputs = {}
                if video:
                    outputs["video_anotado.mp4"] = proposed
                if baseline:
                    base = baseline.process(frame, stamp)
                    base_event = baseline_events.process(index, frame, base)
                    if base_event:
                        last_events["baseline"] = base_event
                    latest = last_events.get("baseline")
                    baseline_frame = overlay(frame, base, index + origin, "MediaPipe original",
                                             latest if latest and index - latest.frame < frames.fps else None,
                                             (85, 175, 255))
                    outputs["video_comparativo.mp4"] = cv2.hconcat([baseline_frame, proposed])
                for name, rendered in outputs.items():
                    if name not in visuals:
                        visuals[name] = video_writer(temp / name, rendered, frames.fps)
                        stack.callback(visuals[name].release)
                    visuals[name].write(rendered)
        if index < 0:
            raise ValueError("La entrada no produjo cuadros")
        with (temp / "eventos.csv").open("w", newline="", encoding="utf-8") as event_file:
            writer = csv.writer(event_file)
            writer.writerow(EVENT_COLUMNS)
            writer.writerows(sorted(set(events)))
        elapsed = perf_counter() - started
        if timings:
            payload = {"cuadros": index + 1, "fps_entrada": frames.fps, "segundos": elapsed,
                       "fps_procesamiento": (index + 1) / elapsed}
            (temp / "tiempos.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        for writer in visuals.values():
            writer.release()
        for path in temp.iterdir():
            path.replace(salida / path.name)
        return index + 1
