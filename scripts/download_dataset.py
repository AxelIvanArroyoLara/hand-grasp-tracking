"""Obtiene y extrae los dos archivos autorizados de DexYCB en almacenamiento local."""

from __future__ import annotations

import argparse
import gzip
from hashlib import sha256
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile

SUBJECT = "20200709-subject-01"
ARCHIVES = (
    ("calibration", "1UAwVKT4Rgb1fLcFoa1o71_-0NtSvvLAQ", 14_464),
    (SUBJECT, "1Ehh92wDE3CWAiKG7E9E73HjN2Xk2XfEk", 12_412_314_463),
)
GIB = 1024 ** 3
SUBSET = (("development", "pilot", 3), ("validation", "prefix-validation", 2), ("test", "prefix-test", 2))


def digest(path: Path) -> str:
    """Calcula SHA-256 en bloques, sin cargar archivos grandes en memoria."""
    result = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def obtain(root: Path, folder: str, file_id: str, size: int, offline: bool) -> Path:
    """Descarga o reanuda un archivo oficial y comprueba su longitud."""
    archive = root / "archives" / f"{folder}.tar.gz"
    partial = archive.with_suffix(".gz.part")
    if not archive.is_file():
        if not partial.is_file() or partial.stat().st_size != size:
            if offline:
                raise FileNotFoundError(f"Falta el archivo oficial completo: {archive}")
            url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"
            subprocess.run(
                ["curl", "--fail", "--location", "--retry", "3", "--continue-at", "-",
                 "--connect-timeout", "20", "--speed-limit", "16384", "--speed-time", "90",
                 "--output", str(partial), url],
                check=True,
            )
        if partial.stat().st_size != size:
            raise ValueError(f"Longitud inesperada en {partial}: {partial.stat().st_size}, esperada {size}")
        with partial.open("rb") as response:
            if response.read(2) != b"\x1f\x8b":
                raise ValueError(f"El servidor no devolvió un GZIP: {partial}")
        partial.rename(archive)
    if archive.stat().st_size != size:
        raise ValueError(f"Longitud inesperada en {archive}, esperada {size}")
    return archive


def member_path(member: tarfile.TarInfo, expected_root: str) -> PurePosixPath:
    """Rechaza rutas externas, enlaces, dispositivos y tipos de archivo ajenos."""
    path = PurePosixPath(member.name)
    if (
        not path.parts or path.parts[0] != expected_root
        or ".." in path.parts or member.issparse() or not (member.isdir() or member.isfile())
    ):
        raise ValueError(f"Entrada TAR no permitida: {member.name}")
    return path


def write_member(tar: tarfile.TarFile, member: tarfile.TarInfo, target: Path) -> None:
    """Escribe únicamente directorios y archivos regulares en el área temporal."""
    if member.isdir():
        target.mkdir(parents=True, exist_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    source = tar.extractfile(member)
    if source is None:
        raise ValueError(f"No se pudo leer {member.name}")
    with source, target.open("xb") as destination:
        shutil.copyfileobj(source, destination, length=1024 * 1024)


def extract(archive: Path, root: Path, folder: str) -> None:
    """Extrae en staging y comprueba el CRC GZIP antes de publicar la carpeta."""
    destination = root / folder
    if destination.exists():
        raise FileExistsError(f"Ya existe {destination}")
    limit = 48 * GIB if folder == SUBJECT else 4 * 1024 ** 2
    total = 0
    with tempfile.TemporaryDirectory(prefix=".extract-", dir=root) as temporary:
        staging = Path(temporary)
        with gzip.open(archive, "rb") as compressed:
            with tarfile.open(fileobj=compressed, mode="r|") as tar:
                for member in tar:
                    path = member_path(member, folder)
                    total += member.size
                    if total > limit:
                        raise ValueError(f"{archive} excede el límite de extracción")
                    write_member(tar, member, staging.joinpath(*path.parts))
            while compressed.read(1024 * 1024):
                pass
        (staging / folder).rename(destination)


def extract_prefix(archive: Path, root: Path, count: int, partition: str) -> int:
    """Extrae primeras tomas completas de una partición en una descarga en curso."""
    from src.datasets.dexycb import CAMERAS, SEQUENCE_NAME, read_yaml, split_name

    def complete(path: Path) -> bool:
        """Comprueba que las ocho vistas tengan cada JPEG y NPZ esperado."""
        frames = int(read_yaml(path / "meta.yml")["num_frames"])
        return frames > 0 and all(
            (path / camera / f"{kind}_{n:06d}.{extension}").is_file()
            for camera in CAMERAS for n in range(frames)
            for kind, extension in (("color", "jpg"), ("labels", "npz"))
        )

    output = root / SUBJECT
    output.mkdir(parents=True, exist_ok=True)
    selected = [path for path in output.iterdir() if path.is_dir()]
    if len(selected) > count:
        raise ValueError(f"{root} ya contiene más tomas de las solicitadas")
    if len(selected) == count:
        return count
    with tempfile.TemporaryDirectory(prefix=".pilot-", dir=root) as temporary:
        staging = Path(temporary)
        active = ""
        try:
            with gzip.open(archive, "rb") as compressed:
                with tarfile.open(fileobj=compressed, mode="r|") as tar:
                    for member in tar:
                        path = member_path(member, SUBJECT)
                        if len(path.parts) < 2 or not SEQUENCE_NAME.fullmatch(path.parts[1]):
                            continue
                        name = path.parts[1]
                        if active and name != active:
                            candidate = staging / active
                            if complete(candidate):
                                candidate.rename(output / active)
                                selected.append(output / active)
                                if len(selected) >= count:
                                    break
                            active = ""
                        if (output / name).exists() or split_name(name) != partition:
                            continue
                        if member.isfile() and not (
                            path.name == "meta.yml" or path.name.startswith(("color_", "labels_"))
                        ):
                            continue
                        active = name
                        if member.size > 10 * 1024 ** 2:
                            raise ValueError(f"Archivo de piloto demasiado grande: {path}")
                        write_member(tar, member, staging.joinpath(*path.parts[1:]))
        except (EOFError, tarfile.ReadError):
            # Se conserva lo ya comprobado y se descarta la toma aún incompleta.
            pass
    return len(selected)


def assemble_subset(root: Path) -> None:
    """Agrupa 3/2/2 tomas con enlaces relativos y conserva la separación por toma."""
    from src.datasets.dexycb import SEQUENCE_NAME, split_name

    selected = []
    for partition, directory, expected in SUBSET:
        subject = root / directory / SUBJECT
        sequences = sorted(
            path for path in subject.iterdir()
            if path.is_dir() and SEQUENCE_NAME.fullmatch(path.name)
        )
        if len(sequences) != expected or any(split_name(path.name) != partition for path in sequences):
            raise ValueError(f"Se requieren {expected} tomas de {partition} en {subject}")
        selected.extend(sequences)

    destination = root / "subset"
    if destination.exists():
        links = [destination / "calibration", *(destination / SUBJECT / path.name for path in selected)]
        targets = [root / "pilot" / "calibration", *selected]
        if not all(link.is_symlink() and link.resolve() == target.resolve() for link, target in zip(links, targets)):
            raise FileExistsError(f"El subconjunto existente no corresponde a los prefijos: {destination}")
        print(f"Subconjunto disponible: {destination}")
        return
    with tempfile.TemporaryDirectory(prefix=".subset-", dir=root) as temporary:
        staging = Path(temporary)
        data = staging / "subset"
        (data / SUBJECT).mkdir(parents=True)
        (data / "calibration").symlink_to(
            os.path.relpath(root / "pilot" / "calibration", destination), target_is_directory=True,
        )
        for path in selected:
            (data / SUBJECT / path.name).symlink_to(
                os.path.relpath(path, destination / SUBJECT), target_is_directory=True,
            )
        data.rename(destination)
    print(f"Subconjunto disponible: {destination}")


def main() -> None:
    """Valida los recursos y extrae el dataset entero o un piloto aislado."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/raw/dexycb"))
    parser.add_argument("--extract-only", action="store_true", help="Usa archivos locales sin red")
    prefixes = parser.add_mutually_exclusive_group()
    prefixes.add_argument("--pilot-dev", type=int, metavar="N", help="Copia N tomas de desarrollo a root/pilot")
    prefixes.add_argument("--prefix-validation", type=int, metavar="N", help="Copia N tomas a root/prefix-validation")
    prefixes.add_argument("--prefix-test", type=int, metavar="N", help="Copia N tomas a root/prefix-test")
    prefixes.add_argument("--assemble-subset", action="store_true", help="Enlaza los prefijos 3/2/2 en root/subset")
    parser.add_argument("--subject-sha256", help="SHA-256 esperado, si se obtuvo de fuente confiable")
    arguments = parser.parse_args()
    root = arguments.root
    (root / "archives").mkdir(parents=True, exist_ok=True)
    if arguments.assemble_subset:
        assemble_subset(root)
        return
    prefix_options = (
        (arguments.pilot_dev, "development", "pilot"),
        (arguments.prefix_validation, "validation", "prefix-validation"),
        (arguments.prefix_test, "test", "prefix-test"),
    )
    prefix = next((item for item in prefix_options if item[0] is not None), None)
    if shutil.disk_usage(root).free < (2 if prefix else 64) * GIB:
        raise OSError("Espacio insuficiente para el archivo comprimido y la extracción")
    if prefix:
        count, partition, directory = prefix
        if not 1 <= count <= 10:
            parser.error("El número de tomas del prefijo debe estar entre 1 y 10")
        calibration = obtain(root, *ARCHIVES[0], offline=True)
        pilot = root / directory
        pilot.mkdir(exist_ok=True)
        if not (pilot / "calibration").is_dir():
            extract(calibration, pilot, "calibration")
        completed = root / "archives" / f"{SUBJECT}.tar.gz"
        source = completed if completed.is_file() else completed.with_suffix(".gz.part")
        available = extract_prefix(source, pilot, count, partition)
        print(f"Prefijo {partition}: {available} tomas completas en {pilot}", flush=True)
        if available < count:
            parser.exit(3, "El archivo parcial aún no contiene todas las tomas solicitadas.\n")
        return
    for folder, file_id, size in ARCHIVES:
        path = obtain(root, folder, file_id, size, offline=arguments.extract_only)
        checksum = digest(path)
        if folder == SUBJECT and arguments.subject_sha256 and checksum != arguments.subject_sha256.lower():
            raise ValueError(f"Huella distinta a la esperada para {path}")
        print(f"SHA-256 {checksum}  {path}", flush=True)
        if (root / folder).exists():
            print(f"Conservado directorio existente: {root / folder}")
        else:
            extract(path, root, folder)


if __name__ == "__main__":
    main()
