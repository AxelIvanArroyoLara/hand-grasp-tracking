# Tareas

| ID | Tarea | Depende de | Estado | Aceptación y evidencia |
|---|---|---|---|---|
| T0 | Inspección y entorno | | Cumplido | Git, Python ARM64, dependencias y manifiesto de entorno |
| T1 | Inferencia RGB en CPU | T0 | Cumplido | CSV y pruebas de video, imágenes y ausencia de mano |
| T2 | DexYCB | T0 | Parcial | Prefijo de siete tomas completas y calibración. Transferencia íntegra y auditoría total pendientes |
| T3 | Comparación de seguimiento | T1, T2 | Cumplido en subconjunto | Piloto, 23 configuraciones en validación, congelación y prueba local |
| T4 | Detección de eventos | T1, T2 | Parcial | Reglas y clasificadores evaluados. La meta de mejora de F1 no se alcanzó |
| T5 | Videos propios | T1, grabaciones | Bloqueado | Herramienta y validación listas. Faltan grabaciones y anotaciones |
| T6 | Informe y presentación | T3, T4 | Parcial | Versiones preliminares con métricas reales, figura de error y guion |
| T7 | Paquete | T6 | Parcial | Constructor y ZIP preliminar. Para cierre faltan T5, nombres y evaluación oficial |
