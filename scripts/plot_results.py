"""Genera gráficas de ablación y trazas de una vista con resultados medidos."""

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path("experiments/cache/matplotlib").resolve()))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

INK, TEAL, ORANGE = "#172838", "#087f75", "#be542d"
LABELS = {"baseline": "MediaPipe", "completo": "Completo", "seleccionado": "Seleccionado",
          "sin_clahe": "Sin CLAHE", "sin_roi": "Sin ROI", "sin_flujo": "Sin flujo",
          "sin_filtro": "Sin filtro", "one_euro": "One Euro"}


def plot(folder, output):
    """Grafica cobertura, PCK, estabilidad, F1 y velocidad con denominadores fijos."""
    rows = json.loads((folder / "ablation.json").read_text())
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": INK,
                         "axes.labelcolor": INK, "axes.titleweight": "bold", "axes.spines.top": False,
                         "axes.spines.right": False, "axes.axisbelow": True})
    count = len(rows)
    figure, axes = plt.subplots(1, 4, figsize=(12.5, max(3.1, 1.25 + .27 * count)), sharey=True)
    labels = [LABELS.get(r["name"], r["name"].replace("_", " ").title()) for r in rows]
    colors = [ORANGE if r["name"] == "baseline" else TEAL for r in rows]
    titles = (("detection_rate", "Detección (%)", 100), ("pck_10", "PCK@10 px (%)", 100),
              ("jitter_px", "Temblor (px/cuadro²)", 1), ("fps", "Velocidad (FPS)", 1))
    for ax, (key, title, scale) in zip(axes, titles, strict=True):
        values = [scale * r[key] if r[key] is not None else np.nan for r in rows]
        ax.barh(labels, values, color=colors, alpha=.87)
        ax.set_title(title, fontsize=10)
        ax.grid(axis="x", alpha=.23)
        ax.tick_params(labelsize=8)
    axes[0].invert_yaxis()
    figure.tight_layout()
    figure.savefig(output / "ablacion.png", dpi=175, bbox_inches="tight")
    plt.close(figure)

    figure, ax = plt.subplots(figsize=(7.6, 3.4))
    preferred = [row for row in rows if row["name"] in ("baseline", "completo", "seleccionado")]
    x = np.arange(len(preferred))
    for index, (metric, label, color) in enumerate((("precision", "Precisión", ORANGE),
            ("recall", "Recall", TEAL), ("f1", "F1", INK))):
        bars = ax.bar(x + (index - 1) * .24, [100 * r[metric] if r[metric] is not None else 0 for r in preferred],
                      .22, color=color, label=label)
        for bar, row in zip(bars, preferred, strict=True):
            if row[metric] is None:
                ax.text(bar.get_x() + bar.get_width() / 2, 2, "N/D", ha="center", fontsize=7, rotation=90)
    ax.set_xticks(x, [LABELS.get(row["name"], row["name"]) for row in preferred])
    ax.set(ylim=(0, 105), ylabel="Porcentaje", title="Agarres DexYCB · tolerancia ±5 cuadros")
    ax.grid(axis="y", alpha=.22)
    ax.legend(frameon=False, ncol=3, loc="upper right")
    figure.tight_layout()
    figure.savefig(output / "eventos.png", dpi=175, bbox_inches="tight")
    plt.close(figure)


def trajectory(comparison, output):
    """Grafica la muñeca y sus cambios cuadro a cuadro desde puntos.csv."""
    import csv
    with (comparison / "puntos.csv").open() as source:
        rows = list(csv.DictReader(source))
    points = np.array([[float(row[key]) if row[key] else np.nan for key in ("x0", "y0")] for row in rows])
    index = np.array([int(row["cuadro"]) for row in rows])
    fig, axes = plt.subplots(2, 1, figsize=(8, 4), sharex=True)
    for dim, name in enumerate(("x", "y")):
        axes[0].plot(index, points[:, dim], label=name)
    axes[0].set_ylabel("Posición (px)")
    axes[0].legend(frameon=False)
    axes[1].plot(index[2:], np.linalg.norm(np.diff(points, n=2, axis=0), axis=1), color=TEAL)
    axes[1].set(xlabel="Cuadro", ylabel="Aceleración\n(px/cuadro²)")
    fig.tight_layout()
    fig.savefig(output / "trayectoria.png", dpi=175, bbox_inches="tight")
    plt.close(fig)


def errors(source, output):
    """Grafica error de puntos y PCK de la vista, incluidos cuadros sin pose."""
    import csv
    with source.open() as stream:
        rows = list(csv.DictReader(stream))
    index = [int(row["cuadro"]) for row in rows]
    figure, axes = plt.subplots(2, 1, figsize=(7.6, 3.8), sharex=True)
    for axis, key, title, scale in zip(axes, ("mediana_px", "pck_10"),
                                      ("Error mediano (px)", "PCK@10 px (%)"), (1, 100), strict=True):
        values = [float(row[key]) * scale if row[key] else np.nan for row in rows]
        axis.plot(index, values, color=TEAL)
        axis.set_ylabel(title)
        axis.grid(alpha=.25)
    axes[0].axhline(10, color=ORANGE, linestyle="--", linewidth=1)
    axes[-1].set_xlabel("Cuadro")
    figure.tight_layout()
    figure.savefig(output / "errores.png", dpi=175, bbox_inches="tight")
    plt.close(figure)


def main():
    """Crea las figuras auditables de una ejecución completa."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("resultados", type=Path)
    parser.add_argument("salida", type=Path)
    parser.add_argument("--comparativo", type=Path)
    args = parser.parse_args()
    plot(args.resultados, args.salida)
    if (args.salida / "errores.csv").is_file():
        errors(args.salida / "errores.csv", args.salida)
    if args.comparativo:
        trajectory(args.comparativo, args.salida)


if __name__ == "__main__":
    main()
