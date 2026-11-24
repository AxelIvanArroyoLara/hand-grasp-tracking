# Auditoría de la rúbrica

Evaluación provisional sobre un subconjunto real de DexYCB subject-01. Se procesó
la cámara 836212060125. El conjunto de prueba local contiene dos tomas, 142 cuadros
y dos agarres de referencia. Los resultados no representan el ranking del curso.

| Criterio | Estado | Resultado y evidencia |
|---|---|---|
| Tasa de detección | Parcial | 97,81 % en ambos métodos (134/137). La prueba no muestra mejora. [Prueba](../experiments/results/test/ablation.csv) |
| PCK@10 px | Parcial | 73,06 % de MediaPipe y 64,24 % del seleccionado, −8,83 puntos porcentuales. [Prueba](../experiments/results/test/ablation.csv) |
| Temblor | Cumplido en prueba local | 3,45 frente a 2,30 px/cuadro², una reducción de 33,2 %. El residuo respecto a la referencia baja de 3,77 a 2,80. [Prueba](../experiments/results/test/ablation.csv) |
| F1 y mejora de 15 p.p. | Parcial | 66,67 % frente a 0 %, −66,67 p.p. El detector base obtuvo 1 TP y 1 FN. El propuesto obtuvo 2 FN sin predicciones de agarre. [Prueba por vista](../experiments/results/test/ablation.json) |
| Técnicas de visión y ablación | Cumplido en el subconjunto | CLAHE adaptativo, ROI, Lucas–Kanade y One Euro. 23 configuraciones con variantes individuales, grupos y sustracciones. [Validación](../experiments/results/validation/ablation.csv) |
| Resultados negativos | Cumplido | CLAHE, gamma, ecualización y LK individual no cambiaron cobertura, PCK o temblor en validación. Kalman y EMA redujeron temblor con pérdida de PCK. [Ablación](../experiments/results/validation/ablation.csv) |
| Alternativas de eventos | Cumplido en el subconjunto | Reglas, apertura adaptativa, regresión logística, SVM y k-NN obtuvieron cero TP en validación. Una vista carece de poses utilizables. [Comparación exploratoria](../experiments/results/event_classifiers.json) |
| Aislamiento de prueba | Cumplido en el subconjunto | Se fijaron tomas, cámara, modelo, opciones y hash antes de leer las etiquetas de prueba. [Congelación](../experiments/results/validation/frozen.json) |
| Dataset | Parcial | Siete tomas completas del prefijo y calibración disponibles localmente. Cada toma conserva sus ocho cámaras para la referencia. El avance de la transferencia completa se registra en STATE.md. [Partición](../data/splits/dexycb_subset.json) |
| Videos propios | Bloqueado | Faltan las tres grabaciones reales y los treinta eventos anotados. [Procedimiento](../LEEME.md) |
| Video comparativo | Parcial | Video local lado a lado de una vista de prueba DexYCB. El comparativo con videos propios requiere las grabaciones. |
| Código, CPU y ejecución única | Cumplido en la Mac verificada | 97,92 FPS (10,21 ms/cuadro) de MediaPipe y 90,13 FPS (11,09 ms/cuadro) del sistema seleccionado. El proceso alcanzó aproximadamente 182 MiB RSS pico. [Entorno](../experiments/manifests/environment.json) |
| Informe IEEE | Parcial | Informe preliminar de 4 páginas compilado con las métricas reales de prueba, las ablaciones y el análisis visual. Faltan nombres, videos propios y evaluación oficial. [Fuente](report/main.tex) |
| Presentación | Cumplido como versión preliminar | 10 diapositivas editables en PPTX y PDF. Guion de 10 minutos para tres personas. [Guion](presentation/guion_exposicion.md) |
| Evaluador del profesor | Bloqueado | Falta el programa o la especificación oficial. Los resultados emplean el evaluador provisional. |
| ZIP | Cumplido como versión preliminar | El constructor revisa el índice, CRC y formatos tras extraer el ZIP en un temporal. Desde la extracción se procesaron 74 cuadros RGB en CPU. [Prueba de paquete](../experiments/manifests/submission_smoke.json). [Constructor](../scripts/build_submission.py) |

El protocolo local usa una vista y pocos eventos. Una sola predicción cambia fuertemente
F1. La estabilización reduce el movimiento de alta frecuencia, pero también puede desplazar
la posición estimada en cuadros de movimiento rápido. El conjunto final de evaluación del curso
y los videos del equipo son necesarios para determinar la capacidad de generalización.
