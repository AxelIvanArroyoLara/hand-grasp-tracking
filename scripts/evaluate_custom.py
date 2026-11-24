"""Evalúa las grabaciones propias con las mismas entradas para ambos detectores."""

import argparse
from pathlib import Path
import shutil

from scripts.annotate_videos import CONDITIONS, read_events
from scripts.run_experiments import save_json
from src.contracts import MODEL, ROOT
from src.evaluation import EventMetrics
from src.input import Frames
from src.pipeline import run


def evaluate(raw, labels, output, model, config):
    """Valida las tres entradas antes de computar métricas con anotaciones humanas."""
    queue = []
    for name in CONDITIONS:
        matches = [p for p in raw.glob(f"{name}.*") if p.suffix.lower() in {".mov", ".mp4", ".m4v"}]
        if len(matches) != 1:
            raise ValueError(f"Se esperaba un video llamado {name}.mp4, .mov o .m4v")
        clip = matches[0]
        with Frames(clip) as frames:
            count = sum(1 for _ in frames)
            if abs(frames.fps - 30) > 0.05 or not 30 <= count / frames.fps <= 60:
                raise ValueError(f"{clip} debe tener 30–60 s a 30 FPS")
        truth_file = labels / f"{name}.csv"
        truth = read_events(truth_file, count, require_five=True)
        queue.append((name, clip, truth_file, truth, count))
    aggregates = {method: EventMetrics() for method in ("baseline", "proposed")}
    results = {}
    for name, clip, truth_file, expected, count in queue:
        dest = output / name
        results[name] = {"frames": count}
        for method, configuration in (("baseline", ROOT / "configs/baseline.yaml"), ("proposed", config)):
            path = dest / method if method == "baseline" else dest
            run(clip, path, model, configuration, comparison=method == "proposed", timings=True)
            predicted = read_events(path / "eventos.csv", count)
            local = EventMetrics()
            local.update(predicted, expected)
            aggregates[method].update(predicted, expected)
            results[name][method] = local.result()
        shutil.copyfile(clip, dest / f"video{clip.suffix.lower()}")
        shutil.copyfile(truth_file, dest / "anotaciones.csv")
    results["micro"] = {key: metric.result() for key, metric in aggregates.items()}
    save_json(output / "custom_results.json", results)
    return results


def main():
    """Ejecuta evaluación propia sin pasar datos anotados a la inferencia."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--videos", default=ROOT / "data/raw/custom_videos", type=Path)
    parser.add_argument("--anotaciones", default=ROOT / "data/annotations/custom_videos", type=Path)
    parser.add_argument("--salida", default=ROOT / "deliverables/videos_propios", type=Path)
    parser.add_argument("--config", default=ROOT / "configs/proposed.yaml", type=Path)
    parser.add_argument("--modelo", default=MODEL, type=Path)
    args = parser.parse_args()
    evaluate(args.videos, args.anotaciones, args.salida, args.modelo, args.config)


if __name__ == "__main__":
    main()
