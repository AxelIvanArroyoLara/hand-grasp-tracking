"""Construye y verifica un ZIP local con el código y los productos académicos."""

import argparse
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from scripts.annotate_videos import CONDITIONS, read_events
from scripts.report_metrics import read_authors
from src.contracts import ROOT

ARTIFACTS = ("reporte_IEEE.pdf", "presentacion.pptx", "presentacion.pdf", "video_comparativo.mp4")
CODE_FILES = ("correr.py", "LEEME.md", "requirements.txt", "pyproject.toml",
              "models/README.md", "docs/report/main.tex", "docs/report/references.bib",
              "docs/presentation/build.cjs", "docs/presentation/README.md",
              "docs/presentation/guion_exposicion.md")
CODE_DIRS = ("src", "configs", "scripts")
ALLOWED_SUFFIXES = {".py", ".yaml", ".md", ".js"}


def valid_artifact(path):
    """Revisa la firma del archivo y el contenido básico del PPTX."""
    if not path.is_file() or path.stat().st_size == 0:
        return False
    with path.open("rb") as stream:
        header = stream.read(12)
    if path.suffix == ".pdf":
        return header.startswith(b"%PDF-")
    if path.suffix == ".mp4":
        return header[4:8] == b"ftyp"
    if path.suffix == ".pptx":
        try:
            with ZipFile(path) as archive:
                return "ppt/presentation.xml" in archive.namelist() and archive.testzip() is None
        except BadZipFile:
            return False
    return True


def gather(root, deliverables):
    """Forma una lista explícita con los archivos autorizados para el ZIP."""
    files = [(root / name, f"codigo/{name}") for name in CODE_FILES if (root / name).is_file()]
    for folder in CODE_DIRS:
        for path in sorted((root / folder).rglob("*")):
            if path.is_file() and not path.is_symlink() and path.suffix in ALLOWED_SUFFIXES:
                files.append((path, f"codigo/{path.relative_to(root).as_posix()}"))
    pending = []
    for name in ARTIFACTS:
        path = deliverables / name
        if valid_artifact(path):
            files.append((path, name))
        else:
            pending.append(name)
    for condition in CONDITIONS:
        directory = deliverables / "videos_propios" / condition
        clips = [p for p in directory.glob("video.*") if p.suffix in {".mp4", ".mov", ".m4v"} and valid_artifact(p)]
        indispensable = [directory / name for name in ("anotaciones.csv", "puntos.csv", "eventos.csv")]
        if len(clips) != 1 or not all(valid_artifact(p) for p in indispensable):
            pending.append(f"videos propios completos de {condition}")
            continue
        read_events(indispensable[0], require_five=True)
        files.extend((p, f"videos_propios/{condition}/{p.name}") for p in [*clips, *indispensable])
    for name in ("environment.json", "dexycb_transfer.json", "requirements-macos-arm64-py312.txt"):
        evidence = root / "experiments/manifests" / name
        if evidence.is_file():
            files.append((evidence, f"evidencia/{name}"))
    for stage in ("development", "validation", "test"):
        record = root / "experiments/results" / stage
        manifest = record / "manifest.json"
        if manifest.is_file() and json.loads(manifest.read_text()).get("status") == "complete":
            for name in ("ablation.csv", "ablation.json", "manifest.json", "splits.json", "frozen.json", "selected.yaml"):
                path = record / name
                if path.is_file():
                    files.append((path, f"evidencia/{stage}/{name}"))
        elif stage in {"validation", "test"}:
            pending.append(f"resultados de {stage}")
    classifier = root / "experiments/results/event_classifiers.json"
    if classifier.is_file():
        files.append((classifier, "evidencia/event_classifiers.json"))
    own_metrics = deliverables / "videos_propios/custom_results.json"
    if own_metrics.is_file() and {"micro", *CONDITIONS} <= json.loads(own_metrics.read_text()).keys():
        files.append((own_metrics, "evidencia/videos_propios.json"))
    else:
        pending.append("métricas de las grabaciones propias")
    official = root / "experiments/results/official.json"
    if official.is_file():
        evidence = json.loads(official.read_text())
        checksum_keys = ("evaluator_sha256", "result_sha256")
        if evidence.get("metrics") and all(re.fullmatch(r"[0-9a-f]{64}", evidence.get(k, "")) for k in checksum_keys):
            files.append((official, "evidencia/official.json"))
        else:
            pending.append("resultados oficiales con huellas válidas")
    else:
        pending.append("resultados del evaluador oficial")
    if not read_authors(root / "docs/presentation/autores.txt"):
        pending.append("nombres del equipo en el reporte")
    return files, pending


def build(root, deliverables, final):
    """Valida requisitos, genera el ZIP y reabre una extracción temporal."""
    files, pending = gather(root, deliverables)
    if pending and final:
        raise ValueError("Entrega definitiva incompleta. Faltan " + ", ".join(pending))
    suffix = "" if final else "_PRELIMINAR"
    destination = deliverables / f"Proyecto_Final_Vision_Artificial{suffix}.zip"
    deliverables.mkdir(parents=True, exist_ok=True)
    audit = root / "docs/final_audit.md"
    if audit.is_file():
        files.append((audit, "evidencia/auditoria.md"))
    with TemporaryDirectory(dir=deliverables, prefix=".empaquetado-") as temp:
        stage = Path(temp) / destination.name
        with ZipFile(stage, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("estado_entrega.txt", ("DEFINITIVA" if final else "PRELIMINAR") + "\n"
                             + "\n".join(f"Pendiente: {item}" for item in pending) + "\n")
            for local, entry in files:
                archive.write(local, entry)
        with ZipFile(stage) as archive:
            if archive.testzip() is not None:
                raise ValueError("El ZIP falló la verificación CRC")
            expected = {"estado_entrega.txt", *(entry for _, entry in files)}
            if len(archive.namelist()) != len(expected) or set(archive.namelist()) != expected:
                raise ValueError("El índice del ZIP es inconsistente")
            unzip = Path(temp) / "extraido"
            archive.extractall(unzip)
            if not (unzip / "codigo/correr.py").is_file():
                raise ValueError("Falta el punto de entrada en la extracción")
            if any(not valid_artifact(unzip / name) for name in ARTIFACTS if name not in pending):
                raise ValueError("No se pudo abrir un artefacto de la extracción")
        stage.replace(destination)
    return destination, pending


def main():
    """Genera una entrega preliminar o aplica los requisitos de cierre."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salida", default=ROOT / "deliverables", type=Path)
    parser.add_argument("--definitivo", action="store_true")
    args = parser.parse_args()
    try:
        output, pending = build(ROOT, args.salida, args.definitivo)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    print(output)
    for item in pending:
        print(f"Pendiente: {item}")


if __name__ == "__main__":
    main()
