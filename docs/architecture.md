# Arquitectura

```mermaid
flowchart LR
  A[Video RGB] --> B[Lectura por cuadros]
  B --> C[Contraste y realce adaptativos]
  C --> D[Hand Landmarker CPU]
  D --> E[Recuperación ROI o LK]
  E --> F[Filtrado temporal]
  F --> G[puntos.csv]
  F --> H[Geometría, movimiento y estados]
  B --> H
  H --> I[eventos.csv]
  G --> J[Evaluación]
  I --> J
  K[Anotaciones] --> J
```

`src/input.py` mantiene el orden de cuadro. `src/tracking.py` opera en coordenadas de la imagen original.
`src/events.py` conserva solo el estado reciente. `src/pipeline.py` escribe las salidas en temporales antes de publicarlas.
El evaluador provisional usa referencias al comparar inferencias RGB, en una etapa independiente del rastreador y del detector. Las gráficas
se generan a partir de los resultados medidos y la vista comparada.
