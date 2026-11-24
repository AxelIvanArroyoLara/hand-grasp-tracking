"""Genera un comparativo RGB y muestras de fallas obtenidas durante la evaluación."""

import argparse
import json
from pathlib import Path

import cv2

from src.contracts import MODEL, ROOT
from src.datasets.dexycb import discover
from src.pipeline import run


def main():
    """Selecciona una entrada directa o una vista de la partición medida."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path)
    parser.add_argument("--datos", type=Path)
    parser.add_argument("--resultados", type=Path)
    parser.add_argument("--salida", required=True, type=Path)
    parser.add_argument("--config", default=ROOT / "configs/proposed.yaml", type=Path)
    parser.add_argument("--modelo", default=MODEL, type=Path)
    parser.add_argument("--figuras", type=Path)
    args = parser.parse_args()
    source = args.entrada
    if source is None:
        if args.datos is None or args.resultados is None:
            parser.error("Indica --entrada o ambos --datos y --resultados")
        rows = json.loads((args.resultados / "ablation.json").read_text())
        record = rows[0]["details"][0]
        sequences = {seq.name: seq for seq in discover(args.datos)}
        view = next(v for v in sequences[record["sequence"]].views if v.camera == record["camera"])
        source = view.path
    args.salida.mkdir(parents=True, exist_ok=True)
    if args.entrada is None:
        from tempfile import TemporaryDirectory
        with TemporaryDirectory(prefix="dexycb-rgb-") as staging:
            selected = Path(staging)
            for frame in view.frames():
                (selected / frame.color.name).symlink_to(frame.color.resolve())
            run(selected, args.salida, args.modelo, args.config, comparison=True, timings=True)
    else:
        run(source, args.salida, args.modelo, args.config, comparison=True, timings=True)
    if args.figuras and args.entrada is None:
        args.figuras.mkdir(parents=True, exist_ok=True)
        failure = next((f for f in rows[0]["failures"]
                        if f[1:3] == [record["sequence"], record["camera"]]), None)
        if failure:
            capture = cv2.VideoCapture(str(args.salida / "video_comparativo.mp4"))
            capture.set(cv2.CAP_PROP_POS_FRAMES, failure[3])
            ok, frame = capture.read()
            capture.release()
            if ok:
                cv2.imwrite(str(args.figuras / "falla_dexycb.jpg"), frame)
                (args.figuras / "falla_dexycb.json").write_text(json.dumps(dict(
                    sequence=failure[1], camera=failure[2], frame=failure[3],
                    criterion="Sin pose visible o mediana de error >= 15 px",
                ), indent=2) + "\n")
        capture = cv2.VideoCapture(str(args.salida / "video_comparativo.mp4"))
        capture.set(cv2.CAP_PROP_POS_FRAMES, view.count // 2)
        ok, image = capture.read()
        capture.release()
        if ok:
            cv2.imwrite(str(args.figuras / "comparativo_dexycb.jpg"), image)


if __name__ == "__main__":
    main()
