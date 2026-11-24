# Estado de ejecución

Evaluación local congelada, prueba reservada ampliada, reporte preliminar, presentación
y comparativo disponibles. DexYCB subject-01 y calibración se descargaron, extrajeron
y verificaron mediante SHA-256 local y CRC GZIP. La auditoría decodificó 58.160 pares
RGB/anotación en 100 tomas y 800 vistas sin incidencias. La partición completa contiene
66 tomas de desarrollo, 20 de validación y 14 de prueba.
[Transferencia](experiments/manifests/dexycb_transfer.json) ·
[Auditoría de datos](experiments/manifests/dexycb_audit_summary.json)

## Evidencia

- Entorno ARM64, Python 3.12.14, MediaPipe 0.10.32, OpenCV contrib 4.12.0.88 y 16 GiB RAM.
- Piloto de 220 cuadros, validación de 144 con 23 configuraciones y prueba de 142 cuadros.
- Prueba congelada. Detección 97,81 % en ambos métodos, PCK 73,06 % frente a 64,24 %,
  temblor 3,45 frente a 2,30 px/cuadro² y F1 66,67 % frente a 0 %.
  Velocidad 97,92 FPS frente a 90,13 FPS en CPU. Resultados bajo `experiments/results/test`.
- Prueba ampliada congelada en otras 12 tomas, 868 cuadros. Detección 88,31 % frente a
  89,16 %, PCK 62,89 % frente a 60,78 %, temblor 2,65 frente a 1,97 px/cuadro²
  y F1 de agarre de 0 % en ambos. Rendimiento en CPU 95,05 frente a 85,98 FPS.
  Resultados en `experiments/results/test_subject01`. Las dos tomas originales
  se excluyeron de esta ampliación.
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

El sujeto completo queda disponible en `data/raw/dexycb`. El protocolo de repetición
de la auditoría y la prueba ampliada está en [Metodología](docs/methodology.md).

Con los videos y anotaciones propios, compilar y reempaquetar con Tectonic y Node
con `pptxgenjs`, `image-size` y LibreOffice disponibles.

```zsh
.venv/bin/python -m scripts.finalize
```

Los pendientes que requieren recursos externos están en [BLOCKERS.md](BLOCKERS.md).
