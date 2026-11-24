"""Lee vistas RGB y anotaciones de DexYCB sin instalar herramientas de GPU."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

import numpy as np
import yaml

SUBJECT = "20200709-subject-01"
FPS = 30
CAMERAS = (
    "836212060125", "839512060362", "840412060917", "841412060263", "932122060857", "932122060861", "932122061900",
    "932122062010",
)
DEFAULT_SEED = 20261202
SEQUENCE_NAME = re.compile(r"\d{8}_\d{6}")


class CalibrationLoader(yaml.SafeLoader):
    """Acepta las tuplas literales que DexYCB incluye en calibración."""


CalibrationLoader.add_constructor(
    "tag:yaml.org,2002:python/tuple", lambda loader, node: tuple(loader.construct_sequence(node))
)


def read_yaml(path: Path) -> dict:
    """Carga un mapa YAML como datos, sin instanciar objetos del documento."""
    with path.open(encoding="utf-8") as source:
        data = yaml.load(source, Loader=CalibrationLoader)
    if not isinstance(data, dict):
        raise ValueError(f"Se esperaba un objeto YAML en {path}")
    return data


@dataclass(frozen=True)
class Labels:
    """Anotaciones de un cuadro en las coordenadas de una cámara RGB."""

    joints: np.ndarray
    segmentation: np.ndarray | None
    poses: np.ndarray


@dataclass(frozen=True)
class FrameRef:
    """Referencia perezosa a un cuadro y sus anotaciones homólogas."""

    index: int
    color: Path
    annotation: Path

    def labels(self, include_seg: bool = False) -> Labels:
        """Lee las juntas en orden de MediaPipe, máscara opcional y pose YCB."""
        with np.load(self.annotation, allow_pickle=False) as archive:
            joints = np.asarray(archive["joint_2d"], dtype=float)
            poses = archive["pose_y"]
            segmentation = archive["seg"] if include_seg else None
        if joints.shape != (1, 21, 2) or poses.ndim != 3 or poses.shape[1:] != (3, 4):
            raise ValueError(f"Formas de anotación inválidas en {self.annotation}")
        if segmentation is not None and (
            segmentation.ndim != 2 or segmentation.dtype != np.uint8
        ):
            raise ValueError(f"Forma o tipo de segmentación inválidos en {self.annotation}")
        # El valor (-1, -1) se reserva para juntas ausentes.
        joints = joints[0]
        invalid = (joints == -1).all(axis=1) | ~np.isfinite(joints).all(axis=1)
        joints[invalid] = np.nan
        return Labels(joints, segmentation, poses)

    def read_rgb(self) -> np.ndarray:
        """Decodifica el JPEG RGB asociado a este cuadro."""
        import cv2

        image = cv2.imread(str(self.color), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"No se pudo leer {self.color}")
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


@dataclass(frozen=True)
class View:
    """Una cámara de una toma con su cronología original."""

    root: Path
    path: Path
    camera: str
    count: int
    extrinsics_id: str

    def frames(self) -> tuple[FrameRef, ...]:
        """Vincula rutas por el índice original sin renumerar faltantes."""
        return tuple(
            FrameRef(
                frame, self.path / f"color_{frame:06d}.jpg",
                self.path / f"labels_{frame:06d}.npz",
            )
            for frame in range(self.count)
        )

    def intrinsics(self) -> dict[str, float]:
        """Devuelve parámetros intrínsecos RGB del archivo de calibración."""
        path = self.root / "calibration" / "intrinsics" / f"{self.camera}_640x480.yml"
        color = read_yaml(path)["color"]
        result = {key: float(color[key]) for key in ("fx", "fy", "ppx", "ppy")}
        if not np.isfinite(tuple(result.values())).all() or min(result["fx"], result["fy"]) <= 0:
            raise ValueError(f"Intrínsecos RGB inválidos en {path}")
        return result

    def extrinsics(self) -> np.ndarray:
        """Lee la transformación de la cámara declarada en los metadatos."""
        if not SEQUENCE_NAME.fullmatch(self.extrinsics_id):
            raise ValueError("Identificador de calibración extrínseca inválido")
        path = self.root / "calibration" / f"extrinsics_{self.extrinsics_id}" / "extrinsics.yml"
        values = read_yaml(path)["extrinsics"][self.camera]
        array = np.asarray(values, dtype=float).reshape(3, 4)
        if not np.isfinite(array).all():
            raise ValueError(f"Extrínsecos inválidos en {path}")
        return array


@dataclass(frozen=True)
class Sequence:
    """Toma de manipulación indivisible al generar las particiones."""

    name: str
    views: tuple[View, ...]
    objects: tuple[int, ...]
    grasp_index: int


def discover(root: Path | str) -> tuple[Sequence, ...]:
    """Enumera tomas oficiales de subject-01, sin leer los fotogramas."""
    root = Path(root)
    subject = root / SUBJECT
    if not subject.is_dir():
        raise FileNotFoundError(f"Falta el directorio de DexYCB {subject}")
    sequences = []
    for path in sorted(item for item in subject.iterdir() if item.is_dir()):
        if not SEQUENCE_NAME.fullmatch(path.name):
            continue
        meta = read_yaml(path / "meta.yml")
        count = int(meta["num_frames"])
        objects = tuple(map(int, meta["ycb_ids"]))
        grasp_index = int(meta["ycb_grasp_ind"])
        if count <= 0 or not 0 <= grasp_index < len(objects):
            raise ValueError(f"Metadatos inconsistentes en {path}")
        views = tuple(
            View(root, path / camera, camera, count, str(meta.get("extrinsics", "")))
            for camera in CAMERAS if (path / camera).is_dir()
        )
        if not views:
            raise ValueError(f"No se encontraron vistas oficiales en {path}")
        sequences.append(Sequence(path.name, views, objects, grasp_index))
    if not sequences:
        raise ValueError(f"No se encontraron tomas en {subject}")
    return tuple(sequences)


def split_name(sequence_name: str, seed: int = DEFAULT_SEED) -> str:
    """Asigna una toma por hash estable, sin mirar sus imágenes o etiquetas."""
    bucket = int.from_bytes(sha256(f"{seed}:{sequence_name}".encode()).digest()[:8], "big") % 100
    if bucket < 60:
        return "development"
    if bucket < 80:
        return "validation"
    return "test"


def split_sequences(sequences: tuple[Sequence, ...], seed: int = DEFAULT_SEED) -> dict:
    """Construye un manifiesto portable con todas las cámaras de cada toma juntas."""
    split = {name: [] for name in ("development", "validation", "test")}
    for sequence in sorted(sequences, key=lambda item: item.name):
        split[split_name(sequence.name, seed)].append(sequence.name)
    return {"subject": SUBJECT, "seed": seed, "rule": "sha256-first8-mod100-60/20/20", "splits": split}


def motion_onset(
    poses: np.ndarray,
    meter_threshold: float = 0.008,
    angle_threshold_deg: float = 12.0,
    reference_frames: int = 5,
    persistence: int = 3,
) -> int | None:
    """Ubica el primer desplazamiento sostenido respecto a la pose inicial."""
    if poses.ndim != 3 or poses.shape[1:] != (3, 4):
        raise ValueError("Las poses deben tener forma (N, 3, 4)")
    if reference_frames < 2 or persistence < 1 or min(meter_threshold, angle_threshold_deg) <= 0:
        raise ValueError("Umbrales o longitudes no válidos")
    rotations = poses[:, :, :3]
    translations = poses[:, :, 3]
    valid = np.isfinite(poses).all(axis=(1, 2)) & (translations[:, 2] > 0)
    valid &= np.abs(np.linalg.det(np.where(valid[:, None, None], rotations, 0)) - 1) < 0.15
    indices = np.flatnonzero(valid)[:reference_frames]
    if len(indices) < reference_frames or indices[-1] > 2 * reference_frames:
        return None
    center = np.median(translations[indices], axis=0)
    distances = np.linalg.norm(translations - center, axis=1)
    angle_cos = (np.einsum("fij,ij->f", rotations, rotations[indices[0]]) - 1) / 2
    moved = valid & (
        (distances >= meter_threshold) | (angle_cos <= np.cos(np.deg2rad(angle_threshold_deg)))
    )
    # Una ventana inicial inestable no permite distinguir el agarre de ruido.
    if moved[indices].any():
        return None
    run = 0
    for index in range(indices[-1] + 1, len(moved)):
        run = run + 1 if moved[index] else 0
        if run == persistence:
            return index - persistence + 1
    return None


def grasp_onset(sequence: Sequence) -> int | None:
    """Obtiene un agarre común a las vistas por consenso de poses elegibles."""
    onsets = []
    for view in sequence.views:
        poses = np.full((view.count, 3, 4), np.nan)
        for frame in view.frames():
            if not frame.annotation.is_file():
                continue
            with np.load(frame.annotation, allow_pickle=False) as archive:
                objects = archive["pose_y"]
            if objects.shape != (len(sequence.objects), 3, 4):
                raise ValueError(f"Pose YCB incompatible en {frame.annotation}")
            poses[frame.index] = objects[sequence.grasp_index]
        onset = motion_onset(poses)
        if onset is not None:
            onsets.append(onset)
    if len(onsets) <= len(sequence.views) / 2 or max(onsets) - min(onsets) > 5:
        return None
    return int(np.rint(np.median(onsets)))
