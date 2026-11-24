"""Punto de entrada para procesar un video RGB o una carpeta de imágenes."""

import argparse
from pathlib import Path

from src.contracts import MODEL, ROOT
from src.pipeline import run


def main():
    """Interpreta opciones y ejecuta la configuración solicitada."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", required=True, type=Path)
    parser.add_argument("--salida", required=True, type=Path)
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--config", type=Path)
    options.add_argument("--baseline", action="store_true")
    parser.add_argument("--modelo", type=Path, default=MODEL)
    parser.add_argument("--fps", type=float, default=30, help="FPS para directorios de imágenes")
    parser.add_argument("--origen-cuadro", type=int, choices=(0, 1), default=0)
    parser.add_argument("--video", action="store_true", help="Escribe video_anotado.mp4")
    parser.add_argument("--comparar", action="store_true", help="Escribe video_comparativo.mp4")
    parser.add_argument("--tiempos", action="store_true")
    args = parser.parse_args()
    config = args.config or ROOT / "configs" / ("baseline.yaml" if args.baseline else "proposed.yaml")
    try:
        frames = run(args.entrada, args.salida, args.modelo, config, args.fps,
                     args.origen_cuadro, args.video, args.comparar, args.tiempos)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    print(f"{frames} cuadros procesados en {args.salida}")


if __name__ == "__main__":
    main()
