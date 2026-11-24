"""Audita emparejamiento, calibración, anotaciones y particiones de DexYCB."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile
from zipfile import BadZipFile

import numpy as np
import yaml

from src.datasets.dexycb import CAMERAS, DEFAULT_SEED, discover, grasp_onset, split_sequences


def write_json(path: Path, value: dict) -> None:
    """Publica un manifiesto completo y portable tras terminar su escritura."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def audit(root: Path, seed: int, prefix: bool, decode_rgb: bool) -> tuple[dict, dict]:
    """Construye un inventario de cámaras y cuadros con incidencias explícitas."""
    sequences = discover(root)
    errors = []
    items = []
    if len(sequences) != 100 and not prefix:
        errors.append(f"Se esperaban 100 tomas oficiales y se encontraron {len(sequences)}")
    for sequence in sequences:
        missing_cameras = set(CAMERAS) - {view.camera for view in sequence.views}
        if missing_cameras:
            errors.append(f"{sequence.name}: faltan cámaras {', '.join(sorted(missing_cameras))}")
        cameras = {}
        for view in sequence.views:
            visible = 0
            try:
                view.intrinsics()
                view.extrinsics()
            except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as error:
                errors.append(f"{sequence.name}/{view.camera}: calibración: {error}")
            for frame in view.frames():
                absent = [path for path in (frame.color, frame.annotation) if not path.is_file()]
                if absent:
                    errors.extend(f"Falta {path.relative_to(root)}" for path in absent)
                    continue
                try:
                    labels = frame.labels(include_seg=True)
                    if labels.segmentation.shape != (480, 640):
                        raise ValueError("La máscara no tiene resolución 640 × 480")
                    if len(labels.poses) != len(sequence.objects):
                        raise ValueError("Número incorrecto de poses YCB")
                    if decode_rgb and frame.read_rgb().shape[:2] != labels.segmentation.shape:
                        raise ValueError("Dimensiones diferentes de RGB y máscara")
                    visible += bool(np.isfinite(labels.joints).all(axis=1).any())
                except (OSError, EOFError, ValueError, KeyError, TypeError, BadZipFile) as error:
                    errors.append(f"{frame.annotation.relative_to(root)}: {error}")
            cameras[view.camera] = {"cuadros": view.count, "cuadros_con_juntas": visible}
        try:
            onset = grasp_onset(sequence)
        except (OSError, EOFError, ValueError, KeyError, BadZipFile) as error:
            errors.append(f"{sequence.name}: poses YCB: {error}")
            onset = None
        items.append({"toma": sequence.name, "camaras": cameras, "agarre_provisional": onset})
    return split_sequences(sequences, seed), {
        "prefijo": prefix,
        "tomas": items,
        "errores": errors,
        "rgb_decodificado": decode_rgb,
    }


def main() -> None:
    """Comprueba el almacenamiento local y registra un inventario JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/raw/dexycb"))
    parser.add_argument("--splits", type=Path, default=Path("data/splits/dexycb_subject01.json"))
    parser.add_argument("--report", type=Path, default=Path("experiments/manifests/dexycb_inventory.json"))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--prefix", action="store_true", help="Permite un subconjunto de tomas")
    parser.add_argument("--decode-rgb", action="store_true", help="Decodifica todos los RGB para auditarlos")
    arguments = parser.parse_args()
    if arguments.prefix and arguments.splits == parser.get_default("splits"):
        parser.error("Especifica --splits para evitar sobrescribir el manifiesto del sujeto completo")
    splits, report = audit(arguments.root.resolve(), arguments.seed, arguments.prefix, arguments.decode_rgb)
    write_json(arguments.splits, splits)
    write_json(arguments.report, report)
    print(f"{len(report['tomas'])} tomas, {len(report['errores'])} incidencias. Inventario: {arguments.report}")
    if report["errores"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
