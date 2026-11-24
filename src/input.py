"""Lectura secuencial de video o imágenes con índices reproducibles."""

import math
import re
from pathlib import Path

import cv2

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}


def image_key(path: Path):
    """Ordena números de cuadro por valor entero y resuelve empates por nombre."""
    tokens = tuple(int(s) if s.isdigit() else s.casefold() for s in re.split(r"(\d+)", path.name))
    return tokens, path.name


class Frames:
    """Libera el VideoCapture y evita retener cuadros anteriores."""

    def __init__(self, path: Path, image_fps: float = 30):
        self.path = path
        self.fps = image_fps
        self.capture = None
        self.images = []
        if not math.isfinite(image_fps) or image_fps <= 0:
            raise ValueError("FPS debe ser finito y positivo")

    def __enter__(self):
        if self.path.is_dir():
            self.images = sorted(
                (p for p in self.path.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES),
                key=image_key,
            )
            if not self.images:
                raise ValueError(f"No hay imágenes compatibles en {self.path}")
        elif self.path.is_file():
            self.capture = cv2.VideoCapture(str(self.path))
            if not self.capture.isOpened():
                self.capture.release()
                raise ValueError(f"No se pudo abrir el video {self.path}")
            fps = self.capture.get(cv2.CAP_PROP_FPS)
            if math.isfinite(fps) and fps > 0:
                self.fps = fps
        else:
            raise FileNotFoundError(self.path)
        return self

    def __exit__(self, *_):
        if self.capture is not None:
            self.capture.release()

    def __iter__(self):
        if self.capture is None:
            for image in self.images:
                frame = cv2.imread(str(image))
                if frame is None:
                    raise ValueError(f"No se pudo decodificar {image}")
                yield frame
            return
        read = 0
        declared = self.capture.get(cv2.CAP_PROP_FRAME_COUNT)
        while True:
            ok, frame = self.capture.read()
            if not ok:
                if math.isfinite(declared) and declared > read:
                    raise ValueError(f"Video interrumpido en cuadro {read} de {int(declared)}")
                return
            read += 1
            yield frame


def timestamps(index: int, fps: float, previous: int) -> int:
    """Garantiza milisegundos estrictamente crecientes desde cero."""
    return max(previous + 1, round(index * 1000 / fps))
