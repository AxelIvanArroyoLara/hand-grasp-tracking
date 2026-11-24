"""Pruebas de contrato para video, imágenes y detector sin anotaciones creadas."""

import csv

import cv2
import numpy as np
import pytest

from scripts.annotate_videos import read_events, save
from src.contracts import MODEL, POINT_COLUMNS, ROOT, load_mapping
from src.input import Frames, timestamps
from src.pipeline import run


def image(path, level):
    """Crea un cuadro sintético uniforme para las pruebas de E/S."""
    assert cv2.imwrite(str(path), np.full((64, 96, 3), level, np.uint8))


def test_natural_frame_order(tmp_path):
    image(tmp_path / "image10.png", 200)
    image(tmp_path / "image2.png", 100)
    with Frames(tmp_path) as frames:
        assert [frame[0, 0, 0] for frame in frames] == [100, 200]
    assert timestamps(2, 5000, 5) == 6


def test_annotation_validation(tmp_path):
    label = tmp_path / "events.csv"
    save(label, {i + 1: "agarrar" if i % 2 == 0 else "soltar" for i in range(10)})
    assert len(read_events(label, count=11, require_five=True)) == 10
    with pytest.raises(ValueError, match="fuera"):
        read_events(label, count=10)
    save(label, {1: "agarrar", 2: "soltar"})
    with pytest.raises(ValueError, match="cinco"):
        read_events(label, require_five=True)


def test_invalid_inputs(tmp_path):
    with pytest.raises(ValueError, match="No hay imágenes"):
        with Frames(tmp_path):
            pass
    with pytest.raises(ValueError, match="positivo"):
        Frames(tmp_path, float("inf"))
    with pytest.raises(FileNotFoundError):
        with Frames(tmp_path / "missing"):
            pass
    config = tmp_path / "config.yaml"
    config.write_text("- invalido\n")
    with pytest.raises(ValueError, match="mapa"):
        load_mapping(config)


@pytest.mark.skipif(not MODEL.is_file(), reason="El modelo oficial se obtiene con scripts.setup")
@pytest.mark.parametrize("name", ("baseline", "proposed"))
def test_real_cpu_pipeline_without_hand(tmp_path, name):
    images = tmp_path / "frames"
    images.mkdir()
    for index in range(4):
        image(images / f"f{index}.png", 180)
    input_path = images
    if name == "proposed":
        input_path = tmp_path / "clip.mp4"
        writer = cv2.VideoWriter(str(input_path), cv2.VideoWriter_fourcc(*"mp4v"), 30, (96, 64))
        assert writer.isOpened()
        for _ in range(4):
            writer.write(np.zeros((64, 96, 3), dtype=np.uint8))
        writer.release()
    output = tmp_path / "missing" / "output"
    assert run(input_path, output, MODEL, ROOT / f"configs/{name}.yaml", origin=1) == 4
    assert {p.name for p in output.iterdir()} == {"puntos.csv", "eventos.csv"}
    with (output / "puntos.csv").open() as source:
        data = list(csv.reader(source))
    assert data[0] == POINT_COLUMNS
    assert data[1:] == [[str(index), *([""] * 42)] for index in range(1, 5)]
    assert (output / "eventos.csv").read_text() == "cuadro,evento\n"
