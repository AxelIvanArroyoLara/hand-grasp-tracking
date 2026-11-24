"""Integra grabaciones propias, recompila documentos y vuelve a empaquetar."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess

from scripts.build_submission import build
from scripts.evaluate_custom import evaluate
from scripts.report_metrics import generate
from src.contracts import MODEL, ROOT


def compile_report(results, deliverables, custom=None):
    """Compila con Tectonic los fragmentos generados a partir de resultados."""
    source = ROOT / "docs/report"
    working = source / "build"
    generate(results, working, custom)
    command = ["tectonic", "-X", "compile", "--outdir", str(working), str(source / "main.tex")]
    subprocess.run(command, cwd=source, check=True)
    shutil.copyfile(working / "main.pdf", deliverables / "reporte_IEEE.pdf")


def main():
    """Actualiza la versión local de entregables con o sin videos nuevos."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solo-documentos", action="store_true")
    parser.add_argument("--resultados", default=ROOT / "experiments/results", type=Path)
    parser.add_argument("--videos", default=ROOT / "data/raw/custom_videos", type=Path)
    parser.add_argument("--anotaciones", default=ROOT / "data/annotations/custom_videos", type=Path)
    parser.add_argument("--config", default=ROOT / "configs/proposed.yaml", type=Path)
    parser.add_argument("--definitivo", action="store_true")
    args = parser.parse_args()
    destination = ROOT / "deliverables"
    destination.mkdir(exist_ok=True)
    own = destination / "videos_propios"
    if not args.solo_documentos:
        evaluate(args.videos, args.anotaciones, own, MODEL, args.config)
        shutil.copyfile(own / "buena_luz/video_comparativo.mp4", destination / "video_comparativo.mp4")
    compile_report(args.resultados.resolve(), destination, own / "custom_results.json")
    node = os.environ.get("PRESENTATION_NODE", "node")
    environment = dict(os.environ, PRESENTACION_RESULTADOS=str(args.resultados.resolve()),
                       PRESENTACION_SALIDA=str(destination))
    subprocess.run([node, str(ROOT / "docs/presentation/build.cjs")], cwd=ROOT, env=environment, check=True)
    result, pending = build(ROOT, destination, args.definitivo)
    print(result)
    for item in pending:
        print(f"Pendiente: {item}")


if __name__ == "__main__":
    main()
