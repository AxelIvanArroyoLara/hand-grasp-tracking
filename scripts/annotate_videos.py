"""Anota cinco agarres y cinco sueltas con navegación cuadro por cuadro."""

import argparse
import csv
from pathlib import Path
from tempfile import NamedTemporaryFile

import cv2

from src.contracts import EVENT_COLUMNS
from src.events import Event
from src.input import Frames
from src.visualization import overlay

CONDITIONS = ("buena_luz", "poca_luz", "movimiento_rapido")


def read_events(path: Path, count=None, require_five=False):
    """Valida índices, clases, duplicados y cronología de anotaciones CSV."""
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != EVENT_COLUMNS:
            raise ValueError(f"Encabezado incorrecto en {path}")
        events = [Event(int(row["cuadro"]), row["evento"]) for row in reader]
    if any(event.frame < 0 or (count is not None and event.frame >= count) for event in events):
        raise ValueError("Hay eventos fuera del video")
    if any(e.kind not in ("agarrar", "soltar") for e in events):
        raise ValueError("Etiqueta desconocida")
    if any(a.frame >= b.frame for a, b in zip(events, events[1:])):
        raise ValueError("Los cuadros deben ser únicos y estar ordenados")
    if require_five and [e.kind for e in events] != ["agarrar", "soltar"] * 5:
        raise ValueError("Se requieren cinco pares consecutivos de agarre y suelta")
    return events


def save(path, annotations):
    """Guarda una edición ordenada para retomarla después."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", dir=path.parent, delete=False, encoding="utf-8", newline="") as temp:
        writer = csv.writer(temp)
        writer.writerow(EVENT_COLUMNS)
        writer.writerows(sorted(annotations.items()))
    Path(temp.name).replace(path)


def annotate(video, output):
    """Presenta controles OpenCV y conserva borradores mediante la tecla s."""
    title = "Anotacion manual"
    with Frames(video) as frames:
        if frames.capture is None:
            raise ValueError("Selecciona un video para anotar")
        capture = frames.capture
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if total < 1:
            raise ValueError("El contenedor no indica un total de cuadros")
        marks = {e.frame: e.kind for e in read_events(output, total)} if output.exists() else {}
        index, playing, previous = 0, False, -2
        cv2.namedWindow(title, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(title, 1024, 620)
        try:
            while True:
                if index != previous:
                    if index != previous + 1:
                        capture.set(cv2.CAP_PROP_POS_FRAMES, index)
                    ok, frame = capture.read()
                    if not ok:
                        raise ValueError(f"No se pudo leer el cuadro {index}")
                    previous = index
                event = Event(index, marks[index]) if index in marks else None
                screen = overlay(frame, None, index, f"Anotacion ({len(marks)}/10)", event)
                cv2.imshow(title, screen)
                key = cv2.waitKey(max(1, round(1000 / frames.fps)) if playing else 0) & 0xff
                if key in (27, ord("q")):
                    return
                if key == ord(" "):
                    playing = not playing
                elif key == ord("a"):
                    index, playing = max(0, index - 1), False
                elif key == ord("d"):
                    index, playing = min(total - 1, index + 1), False
                elif key in (ord("g"), ord("l")):
                    marks[index] = "agarrar" if key == ord("g") else "soltar"
                elif key == ord("x"):
                    marks.pop(index, None)
                elif key == ord("s"):
                    save(output, marks)
                    try:
                        read_events(output, total, require_five=True)
                        print(f"Diez anotaciones válidas guardadas en {output}")
                    except ValueError as exc:
                        print(f"Borrador guardado. {exc}")
                if playing:
                    index = min(total - 1, index + 1)
                    playing = index < total - 1
        finally:
            cv2.destroyWindow(title)


def main():
    """Selecciona el video y el destino de las anotaciones manuales."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--validar", action="store_true")
    args = parser.parse_args()
    if args.validar:
        with Frames(args.video) as frames:
            count = sum(1 for _ in frames)
        print(f"{len(read_events(args.csv, count, require_five=True))} eventos válidos")
    else:
        print("Espacio reproducir, A/D anterior/siguiente, G agarre, L suelta, X borrar, S guardar, Q salir.")
        annotate(args.video, args.csv)


if __name__ == "__main__":
    main()
