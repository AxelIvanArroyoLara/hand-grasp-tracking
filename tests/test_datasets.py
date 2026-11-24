"""Verifica el lector DexYCB y la seguridad de la extracción con datos de prueba."""

from gzip import BadGzipFile
from io import BytesIO
from pathlib import Path
from tarfile import TarInfo, SYMTYPE, open as tar_open
from tempfile import TemporaryDirectory
import unittest

import numpy as np

from scripts.download_dataset import extract, member_path
from src.datasets.dexycb import (
    CAMERAS, SUBJECT, discover, grasp_onset, motion_onset, read_yaml, split_name, split_sequences,
)


def poses_fixture(count: int) -> np.ndarray:
    """Crea una trayectoria constante válida en unidades métricas."""
    pose = np.column_stack((np.eye(3), [0.0, 0.0, 0.5]))
    return np.repeat(pose[None], count, axis=0)


class DexYCBTest(unittest.TestCase):
    """Verifica forma, índices, faltantes y particiones."""

    def test_labels_partition_and_missing_files(self):
        """Conserva índices originales junto con la asignación por secuencia."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            sequence_folder = root / SUBJECT / "20200709_150906"
            camera = sequence_folder / CAMERAS[0]
            camera.mkdir(parents=True)
            (sequence_folder / CAMERAS[1]).mkdir()
            (sequence_folder / "meta.yml").write_text(
                "num_frames: 2\nycb_ids: [1]\nycb_grasp_ind: 0\n", encoding="utf-8"
            )
            raw = np.zeros((1, 21, 2))
            raw[0, 5] = (-1, -1)
            np.savez(
                camera / "labels_000001.npz",
                joint_2d=raw, seg=np.full((2, 3), 255, dtype=np.uint8), pose_y=poses_fixture(1),
            )
            sequences = discover(root)
            sequence = sequences[0]
            self.assertEqual(len(sequence.views), 2)
            first, second = sequence.views[0].frames()
            self.assertFalse(first.annotation.exists())
            self.assertEqual(second.index, 1)
            self.assertEqual(second.color.name, "color_000001.jpg")
            labels = second.labels(include_seg=True)
            self.assertTrue(np.isnan(labels.joints[5]).all())
            self.assertEqual(labels.joints.shape, (21, 2))
            self.assertEqual(labels.segmentation.shape, (2, 3))
            self.assertEqual(labels.poses.shape, (1, 3, 4))
            self.assertIsNone(grasp_onset(sequence))
            self.assertEqual(split_name(sequence.name), "development")
            self.assertEqual(split_sequences(sequences)["splits"]["development"], [sequence.name])

    def test_pose_motion_and_noise(self):
        """Descarta picos aislados o faltantes y conserva el inicio sostenido."""
        poses = poses_fixture(13)
        poses[5, 0, 3] = 0.025
        poses[8:, 0, 3] = 0.009
        self.assertEqual(motion_onset(poses), 8)
        poses[10, :, :] = np.nan
        self.assertIsNone(motion_onset(poses))
        self.assertIsNone(motion_onset(poses_fixture(13)))

    def test_rotation_only(self):
        """Considera un giro sostenido cuando la traslación permanece fija."""
        poses = poses_fixture(10)
        angle = np.deg2rad(18)
        poses[6:, :, :3] = [
            [np.cos(angle), -np.sin(angle), 0],
            [np.sin(angle), np.cos(angle), 0],
            [0, 0, 1],
        ]
        self.assertEqual(motion_onset(poses), 6)

    def test_calibration_tuple(self):
        """Lee la tupla literal que acompaña a la calibración oficial."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.yml"
            path.write_text("transform: !!python/tuple [1, 2]\n", encoding="utf-8")
            self.assertEqual(read_yaml(path)["transform"], (1, 2))


class DownloadTest(unittest.TestCase):
    """Valida el archivo comprimido antes de mover la extracción."""

    def test_extract_and_validate(self):
        """Publica un directorio completo de archivos regulares."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "calibration.tar.gz"
            payload = b"color: {}\n"
            with tar_open(archive, mode="w:gz") as tar:
                member = TarInfo("calibration/intrinsics/example.yml")
                member.size = len(payload)
                tar.addfile(member, BytesIO(payload))
            extract(archive, root, "calibration")
            self.assertEqual((root / member.name).read_bytes(), payload)

    def test_corrupt_gzip_never_commits_extraction(self):
        """Descarta la extracción temporal cuando falla la integridad GZIP."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "calibration.tar.gz"
            payload = b"color: {}\n"
            with tar_open(archive, mode="w:gz") as tar:
                member = TarInfo("calibration/intrinsics/example.yml")
                member.size = len(payload)
                tar.addfile(member, BytesIO(payload))
            content = bytearray(archive.read_bytes())
            content[-8] ^= 1
            archive.write_bytes(content)
            with self.assertRaises(BadGzipFile):
                extract(archive, root, "calibration")
            self.assertFalse((root / "calibration").exists())

    def test_reject_external_members(self):
        """Impide que la extracción escriba fuera del destino."""
        for name in ("../outside", "/calibration/path", "calibration/../outside"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                member_path(TarInfo(name), "calibration")
        link = TarInfo("calibration/link")
        link.type = SYMTYPE
        with self.assertRaises(ValueError):
            member_path(link, "calibration")


if __name__ == "__main__":
    unittest.main()
