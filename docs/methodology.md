# Protocolo reproducible

- Partición por identificador de secuencia mediante primeros ocho bytes de SHA-256 y módulo 100. La semilla es 20261202 y la regla 60/20/20.
- Presupuesto del prefijo. Primeras tres secuencias de desarrollo, dos de validación y dos de prueba completas por orden TAR. Se mide la misma vista 836212060125 a 30 FPS en cada toma.
- Selección de seguimiento sobre validación. Entre las dos variantes completas se ordena por número de métricas de pose que mejoran frente a MediaPipe, PCK, cobertura, menor temblor y FPS. Después se selecciona F1 de eventos sobre la misma validación, con preferencia por la configuración inicial si empata.
- DexYCB. Únicamente agarres. Consenso de onset de movimiento del objeto manipulado a partir de la anotación multivista. Se reportan exclusiones y TP, FP y FN.
- Pose. Detección sobre cuadros con referencia visible. PCK sobre todas las juntas válidas dentro de la imagen, incluidas las fallas. Temblor de la segunda diferencia de posición en tríos consecutivos válidos, acompañado de temblor de referencia y residuo.
- Eventos. Emparejamiento uno a uno por clase dentro de ±5 cuadros. Se maximiza número de pares y se minimiza error absoluto en un empate. Se informan micro F1, precisión, recall y error temporal. Los casos sin denominador se conservan como nulos.
- Coste. Tiempo desde decodificación JPEG hasta actualización de eventos, excluye lectura de anotaciones y gráficos. El piloto de búsqueda ejecuta varios detectores en paralelo lógico por cuadro, de forma secuencial en un proceso. Para estimar la velocidad de despliegue se usa la comparación de prueba con un detector por sistema.
- Congelación. El manifiesto registra métodos, cámaras, tomas y hash de la implementación y el modelo. La prueba solo admite las opciones del manifiesto congelado.
- Integración oficial. Mantener los CSV del contrato. La importación de métricas JSON y huellas del evaluador está disponible en `scripts.import_official`. La versión oficial deberá inspeccionarse al recibirla.
