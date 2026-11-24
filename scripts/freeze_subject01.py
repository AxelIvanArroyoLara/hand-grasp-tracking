"""Amplía la prueba congelada a las tomas reservadas que aún no se evaluaron."""

import argparse
import hashlib
import json
from pathlib import Path

from scripts.run_experiments import save_json
from src.contracts import ROOT
from src.datasets.dexycb import discover, split_sequences


def freeze(data: Path, original: Path, output: Path) -> dict:
    """Fija las tomas adicionales por metadatos, sin abrir RGB ni anotaciones."""
    raw = original.read_bytes()
    frozen = json.loads(raw)
    sequences = discover(data)
    if len(sequences) != 100:
        raise ValueError(f"Se requieren las 100 tomas del sujeto, hay {len(sequences)}")
    split = split_sequences(sequences, frozen["settings"]["seed"])
    previous = set(frozen["test_sequences"])
    held_out = split["splits"]["test"]
    if not previous or not previous <= set(held_out):
        raise ValueError("Las tomas de la prueba original no pertenecen a la partición reservada")
    additional = [name for name in held_out if name not in previous]
    if not additional:
        raise ValueError("No quedan tomas reservadas sin evaluar")
    expanded = {**frozen, "test_sequences": additional,
                "original_freeze_sha256": hashlib.sha256(raw).hexdigest(),
                "original_test_sequences": sorted(previous)}
    if output.exists() and json.loads(output.read_text(encoding="utf-8")) != expanded:
        raise FileExistsError(f"La selección de prueba ampliada ya quedó congelada en {output}")
    save_json(output, expanded)
    return expanded


def main() -> None:
    """Publica los identificadores reservados para el evaluador existente."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datos", default=ROOT / "data/raw/dexycb", type=Path)
    parser.add_argument("--original", default=ROOT / "experiments/results/validation/frozen.json", type=Path)
    parser.add_argument("--salida", default=ROOT / "experiments/results/test_subject01/frozen.json", type=Path)
    args = parser.parse_args()
    frozen = freeze(args.datos, args.original, args.salida)
    print(f"{len(frozen['test_sequences'])} tomas reservadas adicionales en {args.salida}")


if __name__ == "__main__":
    main()
