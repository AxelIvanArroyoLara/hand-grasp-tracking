"""Configuración, validación y contratos de salida del sistema."""

from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "models" / "hand_landmarker.task"
POINT_COLUMNS = ["cuadro", *(f"{axis}{i}" for i in range(21) for axis in "xy")]
EVENT_COLUMNS = ["cuadro", "evento"]


def load_mapping(path: Path) -> dict:
    """Lee un documento YAML con un mapa raíz."""
    with path.open(encoding="utf-8") as source:
        value = yaml.safe_load(source)
    if not isinstance(value, dict):
        raise ValueError(f"Se esperaba un mapa YAML en {path}")
    return value


def valid_points(points) -> bool:
    """Comprueba que se pueda exportar una pose completa y finita."""
    return points is not None and np.shape(points) == (21, 2) and bool(np.isfinite(points).all())
