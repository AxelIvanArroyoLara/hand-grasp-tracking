# Estado de ejecución

Evaluación local congelada, reporte preliminar, presentación y comparativo disponibles.
El conjunto de trabajo de DexYCB contiene siete tomas completas y la calibración.
El archivo completo de subject-01 permanece en transferencia reanudable. El límite
de caudal es compartido. La prueba de cinco rangos simultáneos no aceleró significativamente
la transferencia. No se descargaron otros sujetos.

## Evidencia

- Entorno ARM64, Python 3.12.14, MediaPipe 0.10.32, OpenCV contrib 4.12.0.88 y 16 GiB RAM.
- Piloto de 220 cuadros, validación de 144 con 23 configuraciones y prueba de 142 cuadros.
- Prueba congelada. Detección 97,81 % en ambos métodos, PCK 73,06 % frente a 64,24 %,
  temblor 3,45 frente a 2,30 px/cuadro² y F1 66,67 % frente a 0 %.
  Velocidad 97,92 FPS frente a 90,13 FPS en CPU. Resultados bajo `experiments/results/test`.
- Exploración de eventos. Reglas, umbral adaptativo, regresión logística, SVM y k-NN
  sin verdaderos positivos en las dos vistas de validación.
- Comparativo MP4 de 74 cuadros a 30 FPS en una vista de prueba. El cuadro 13
  contiene una falla espacial documentada.
- Reporte de cuatro páginas y presentación de diez diapositivas. Productos locales
  y ZIP preliminar bajo `deliverables/`. Auditoría de la rúbrica en `docs/final_audit.md`.

- 38 pruebas automatizadas pasaron. La revisión de dependencias no detectó conflictos.
  Se abrió el ZIP sin errores de CRC y se ejecutó el código extraído con un nuevo archivo
  MP4 creado de cuadros reales reservados, cuya ruta contenía espacios. Produjo 74 filas
  en puntos.csv y el encabezado de eventos.csv usando el delegado CPU.

## Continuación

La descarga se reanuda y valida desde el directorio del repositorio.

```zsh
.venv/bin/python -m scripts.download_dataset
.venv/bin/python -m scripts.inspect_dataset --root data/raw/dexycb
```

Con los videos y anotaciones propios, compilar y reempaquetar con Tectonic y Node
con `pptxgenjs`, `image-size` y LibreOffice disponibles.

```zsh
.venv/bin/python -m scripts.finalize
```

Los pendientes que requieren recursos externos están en [BLOCKERS.md](BLOCKERS.md).
