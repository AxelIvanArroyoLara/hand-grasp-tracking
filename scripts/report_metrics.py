"""Inserta resultados medidos y su procedencia en el informe IEEE."""

import argparse
import json
from pathlib import Path

from src.contracts import ROOT

KEYS = ("detection_rate", "pck_10", "jitter_px", "f1", "fps")
TITLES = {"baseline": "MediaPipe original", "completo": "Completo",
          "completo_rapido": "Completo rápido", "seleccionado": "Seleccionado",
          "gamma": "Gamma", "bilateral": "Bilateral", "roi": "ROI", "ema": "EMA", "clahe": "CLAHE", "gaussian": "Gaussiano",
          "equalize": "Ecualización", "unsharp": "Enfoque", "flow": "Flujo",
          "kalman": "Kalman", "one_euro": "One Euro", "rapido_sin_clahe": "Rápido sin CLAHE",
          "rapido_sin_nitidez": "Rápido sin enfoque", "rapido_sin_roi": "Rápido sin ROI",
          "rapido_sin_flujo": "Rápido sin flujo", "rapido_sin_filtro": "Rápido sin filtro"}


def value(number, pct=False):
    """Usa coma decimal y conserva casos no definidos."""
    return "--" if number is None else f"{number * (100 if pct else 1):.2f}".replace(".", ",")


def table(rows, caption):
    """Renderiza un cuadro compacto compatible con IEEEtran."""
    lines = [r"\begin{table}[ht]", r"\centering", r"\small",
             r"\caption{" + caption + "}", r"\begin{tabular}{lrrrrr}", r"\toprule",
             r"Método & Det. & PCK & T. & F1 & FPS \\", r"\midrule"]
    for row in rows:
        name = TITLES.get(row["name"], row["name"].replace("_", " ").capitalize())
        vals = [value(row[key], key in {"detection_rate", "pck_10", "f1"}) for key in KEYS]
        lines.append(" & ".join([name, *vals]) + r" \\")
    return "\n".join([*lines, r"\bottomrule", r"\end{tabular}", r"\end{table}"])


def load(folder):
    """Admite sólo ejecuciones concluidas y con manifiesto."""
    path = folder / "ablation.json"
    manifest = folder / "manifest.json"
    if path.is_file() and manifest.is_file() and json.loads(manifest.read_text())["status"] == "complete":
        return json.loads(path.read_text())
    return []


def read_authors(path):
    """Obtiene tres nombres para el informe y la portada de la presentación."""
    if not path.is_file():
        return []
    names = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(names) != 3 or any(name.startswith("[Integrante") for name in names):
        raise ValueError("autores.txt debe contener tres nombres de integrantes")
    return names


def escape_tex(value):
    """Representa nombres humanos como texto literal en LaTeX."""
    specials = {
        "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$",
        "&": r"\&", "#": r"\#", "%": r"\%", "_": r"\_",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(specials.get(char, char) for char in value)


def generate(results, output, custom=None):
    """Genera fragmentos para el resumen, resultados y ablación a partir de JSON."""
    output.mkdir(parents=True, exist_ok=True)
    authors = read_authors(ROOT / "docs/presentation/autores.txt")
    display = authors or [f"[Integrante {index}]" for index in range(1, 4)]
    (output / "autores.tex").write_text(", ".join(map(escape_tex, display)) + "\n", encoding="utf-8")
    official = results / "official.json"
    official_ready = official.is_file() and bool(json.loads(official.read_text()).get("metrics"))
    own_ready = bool(custom and custom.is_file())
    missing = []
    if not own_ready:
        missing.append("grabaciones propias")
    if not official_ready:
        missing.append("evaluación de la asignatura")
    if not authors:
        missing.append("autoría")
    status = f"Versión preliminar con pendientes de {', '.join(missing)}." if missing else ""
    (output / "estado.tex").write_text(status + "\n", encoding="utf-8")
    test, val, dev = [load(results / name) for name in ("test", "validation", "development")]
    extended_test = load(results / "test_subject01")
    main = extended_test or test or val or dev
    if extended_test:
        scope = "la prueba reservada ampliada de subject-01"
    elif test:
        scope = "la prueba local reservada"
    else:
        scope = "validación" if val else "desarrollo"
    if main:
        baseline = next(row for row in main if row["name"] == "baseline")
        frozen = results / "validation/frozen.json"
        chosen_name = json.loads(frozen.read_text())["name"] if frozen.is_file() else "completo_rapido"
        chosen = next((row for row in main if row["name"] in ("seleccionado", chosen_name)), main[-1])
        summary = (f"En {scope} se analizaron {chosen['frames']} cuadros en {chosen['sequences']} tomas. "
                   f"El PCK@10 px fue {value(baseline['pck_10'], True)}\\,\\% para MediaPipe y "
                   f"{value(chosen['pck_10'], True)}\\,\\% para la variante comparada.")
        main_text = (f"Se midieron {chosen['frames']} cuadros de {chosen['sequences']} tomas y "
                     f"{chosen['views']} vistas en {scope}. El sistema comparado obtuvo "
                     f"{chosen['tp']} verdaderos positivos, {chosen['fp']} falsos positivos y "
                     f"{chosen['fn']} falsos negativos de agarre. Se usan porcentajes para detección, "
                     r"PCK y F1, y píxeles por cuadro al cuadrado para T. Si un denominador es nulo se indica con --."
                     "\n" + table([baseline, chosen], "Comparación en " + scope))
        relative_jitter = None
        if baseline["jitter_px"] and chosen["jitter_px"] is not None:
            relative_jitter = 100 * (chosen["jitter_px"] / baseline["jitter_px"] - 1)
        if relative_jitter is not None:
            main_text += (f"\nEl cambio relativo de temblor fue {value(relative_jitter)}\\,\\%. "
                          f"La latencia media de MediaPipe fue {value(baseline['mean_latency_ms'])} ms y "
                          f"la del sistema comparado fue {value(chosen['mean_latency_ms'])} ms por cuadro. "
                          "La aceleración residual frente a referencia pasó de "
                          f"{value(baseline['residual_jitter_px'])} a {value(chosen['residual_jitter_px'])} "
                          "píxeles por cuadro al cuadrado.")
        if baseline["f1"] is not None and chosen["f1"] is not None:
            main_text += (f"\nLa diferencia de F1 respecto al detector sencillo fue "
                          f"{value((chosen['f1'] - baseline['f1']) * 100)} puntos porcentuales.")
    else:
        summary = "La evaluación cuantitativa permanece pendiente."
        main_text = "Los experimentos cuantitativos permanecen pendientes de registro."
    if extended_test and test:
        main_text += ("\nLa ampliación conserva la misma cámara y configuración congelada. "
                      f"Las {test[0]['sequences']} tomas de la prueba original se excluyeron de "
                      "la ampliación y se conservan en el análisis de casos.")
    comparison = val or dev
    if comparison:
        included = [row for row in comparison if not row["name"].startswith("rapido_sin_")]
        early = [row for row in included if row["name"] in TITLES or row["name"].startswith("sin_")]
        ablation = table(early, "Ablaciones en " + ("validación" if val else "desarrollo"))
        fast = [row for row in comparison if row["name"].startswith("rapido_sin_")]
        if fast:
            ablation += "\n" + table(fast, "Ablaciones de la variante rápida")
        by_name = {row["name"]: row for row in comparison}
        for candidate in ("clahe", "flow", "kalman", "bilateral"):
            row = by_name.get(candidate)
            base = by_name.get("baseline")
            if not row or not base:
                continue
            if row["pck_10"] is None or base["pck_10"] is None:
                continue
            delta = (row["pck_10"] - base["pck_10"]) * 100
            ablation += f"\n{TITLES.get(candidate, candidate.capitalize())} cambió el PCK en {value(delta)} puntos porcentuales."
    else:
        ablation = "La medición individual de las técnicas permanece pendiente."
    classifiers = results / "event_classifiers.json"
    if classifiers.is_file():
        exploration = json.loads(classifiers.read_text())
        comparisons = exploration.get("validation_comparison", exploration.get("results", {}))
        if comparisons:
            ablation += ("\nSe compararon reglas, apertura adaptativa, regresión logística, SVM y k-NN. "
                         "La tabla de resultados exploratorios registra sus umbrales y errores de validación.")
    failure = "La inspección cuantitativa por vista permanece pendiente."
    if test:
        base, chosen = test
        cases = []
        for original, proposed in zip(base["details"], chosen["details"], strict=True):
            if original["expected_grasp"] is None:
                continue
            base_grasps = [str(event[0]) for event in original["predicted_events"] if event[1] == "agarrar"]
            proposed_grasps = [str(event[0]) for event in proposed["predicted_events"] if event[1] == "agarrar"]
            observed = original["expected_grasp"]
            cases.append(f"{original['sequence'].split('_')[1]} & {observed} & "
                         f"{', '.join(base_grasps) or '--'} & {', '.join(proposed_grasps) or '--'}")
        if cases:
            intro = (r"La Tabla~\ref{tab:case-events} muestra las predicciones de agarre por toma. Los índices corresponden "
                     "al inicio de movimiento de la anotación o al cuadro emitido por el detector. "
                     "En el protocolo de referencia, un cuadro con guion indica que el detector no emitió agarre. "
                     "La precisión queda indefinida cuando no hay ninguna predicción positiva.")
            lines = [r"\begin{table}[ht]", r"\centering", r"\small",
                     r"\caption{Cuadros de agarre en prueba local}", r"\label{tab:case-events}",
                     r"\begin{tabular}{lrrr}", r"\toprule",
                     r"Toma & Referencia & Sencillo & Propuesto \\", r"\midrule"]
            lines += [case + r" \\" for case in cases]
            failure = intro + "\n" + "\n".join([*lines, r"\bottomrule", r"\end{tabular}", r"\end{table}"])
        comparable = [(a, b) for a in base["failures"] for b in chosen["failures"]
                      if a[1:] == b[1:] and max(a[0], b[0]) < 1e6]
        if comparable:
            frame_base, frame_variant = comparable[0]
            failure += (f"\nEn el cuadro {frame_base[3]} de la vista ilustrada, "
                        f"la mediana de error pasó de {value(frame_base[0])} px a "
                        f"{value(frame_variant[0])} px. Se seleccionó el cuadro con mayor "
                        "mediana entre los fallos con pose adjudicados al baseline. "
                        "El contraste en este cuadro es un diagnóstico, mientras que el "
                        "PCK agregado incluye la secuencia completa y los cuadros perdidos.")
    if own_ready:
        data = json.loads(custom.read_text())["micro"]
        main_text += (f"\nLas grabaciones propias obtuvieron F1 micro de {value(data['baseline']['f1'], True)}"
                      f"\\,\\% en el detector sencillo y {value(data['proposed']['f1'], True)}\\,\\% en el propuesto.")
    else:
        main_text += "\nLa evaluación de agarres y sueltas en grabaciones propias sigue pendiente."
    if official_ready:
        main_text += "\nEl registro oficial acompaña a la evaluación local con su huella de procedencia."
    for filename, contents in {"resumen": summary, "resultados": main_text, "ablacion": ablation, "casos": failure}.items():
        (output / f"{filename}.tex").write_text(contents + "\n", encoding="utf-8")


def main():
    """Actualiza los fragmentos que incluye main.tex."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resultados", default=ROOT / "experiments/results", type=Path)
    parser.add_argument("--salida", default=ROOT / "docs/report/build", type=Path)
    parser.add_argument("--propios", default=ROOT / "deliverables/videos_propios/custom_results.json", type=Path)
    args = parser.parse_args()
    generate(args.resultados, args.salida, args.propios)


if __name__ == "__main__":
    main()
