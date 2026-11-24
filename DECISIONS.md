# Decisiones

- Se usa Python 3.12 nativo y un entorno virtual. MediaPipe Tasks 0.10.32 ofrece rueda ARM64.
- La inferencia usa el delegado CPU, una mano, 21 landmarks y BGR convertido a RGB.
- Configuración inicial candidata con CLAHE adaptativo, ROI de recuperación, Lucas-Kanade y One Euro. La selección final depende de validación.
- Cuadros desde cero en anotaciones y métricas provisionales. La CLI permite exportar desde uno.
- El contenido privado y los pesos quedan locales. Se usará el remoto existente para el código y la documentación.

## Experimentos locales

- Se fijó un presupuesto de 3/2/2 tomas completas por orden de archivo en desarrollo, validación y prueba. Se reservó la cámara 836212060125 para inferencia en cada toma.
- El piloto motivó un candidato con enfoque ligero y One Euro de respuesta más rápida. Validación eligió la variante completa original por PCK ante el empate en número de métricas mejoradas.
- El F1 de validación fue cero para todos los candidatos exploratorios. Se retuvieron los parámetros iniciales de eventos por la regla de desempate predeclarada.
- Se procesó la prueba local una vez para métricas con configuración congelada. La renderización posterior de un cuadro y su video se usó para documentar fallas.
- Se mantiene el sistema seleccionado por la regla de validación aunque su PCK y F1 de prueba fueron inferiores. Un ajuste posterior requeriría un conjunto de prueba independiente.
