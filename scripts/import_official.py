"""Conserva resultados del evaluador de la asignatura con la huella de su fuente."""

import argparse
import hashlib
import json
from pathlib import Path

from scripts.run_experiments import save_json
from src.contracts import ROOT


def register(evaluator: Path, results: Path, output: Path) -> None:
    """Importa métricas verificables sin modificar su estructura ni sus valores."""
    raw = results.read_bytes()
    metrics = json.loads(raw)
    if not isinstance(metrics, dict) or not metrics:
        raise ValueError("Se esperaba un objeto JSON de métricas oficiales")
    evidence = {"evaluator": evaluator.name, "evaluator_sha256": hashlib.sha256(evaluator.read_bytes()).hexdigest(),
                "result_file": results.name, "result_sha256": hashlib.sha256(raw).hexdigest(), "metrics": metrics}
    save_json(output, evidence)


def main():
    """Registra el evaluador real y el JSON que produjo con el comando oficial."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluador", required=True, type=Path)
    parser.add_argument("--resultados", required=True, type=Path)
    parser.add_argument("--salida", default=ROOT / "experiments/results/official.json", type=Path)
    args = parser.parse_args()
    register(args.evaluador, args.resultados, args.salida)


if __name__ == "__main__":
    main()
