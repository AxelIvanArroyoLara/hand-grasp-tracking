# Guion de exposición

**2 de diciembre de 2026 · 10 minutos · tres integrantes**

| Minuto | Responsable | Diapositiva | Tema |
| --- | --- | --- | --- |
| 0:00–0:35 | Integrante 1 | 1 | Problema y objetivo |
| 0:35–1:30 | Integrante 1 | 2 | Salidas y condiciones difíciles |
| 1:30–3:05 | Integrante 1 | 3 | Seguimiento y técnicas clásicas |
| 3:05–4:15 | Integrante 2 | 4 | Detectores y máquina de estados |
| 4:15–5:15 | Integrante 2 | 5 | Datos, separación y métricas |
| 5:15–6:05 | Integrante 2 | 6 | Resultados de la comparación |
| 6:05–6:50 | Integrante 2 | 7 | Aporte y costo de las técnicas |
| 6:50–7:35 | Integrante 3 | 8 | Falla observada |
| 7:35–8:10 | Integrante 3 | 9 | Conclusiones y alcance |
| 8:10–10:00 | Integrante 3 | 10 | Demostración en vivo |

## Integrante 1 · 3:05

1. Explicar que una demostración grabada con celular puede expresarse como una trayectoria de la mano y una secuencia de instantes de interacción. Presentar el trabajo como percepción monocular para una futura demostración robótica.
2. Señalar en la imagen dónde se pueden ocultar los dedos. Definir los 21 puntos, las coordenadas en píxeles y el caso de cuadros sin una estimación válida.
3. Recorrer el diagrama de izquierda a derecha. CLAHE se aplica bajo una compuerta de exposición baja. MediaPipe intenta detectar primero sobre el cuadro completo. La ROI se recorta con margen. Lucas–Kanade acepta una recuperación de dos cuadros como máximo, sujeta a evidencia visual. El filtro temporal One Euro sigue más de cerca movimientos rápidos y atenúa variaciones a baja velocidad.

**Transición.** «Con la trayectoria disponible, el siguiente paso es distinguir cuándo la mano cambia de estado e interactúa con el objeto».

## Integrante 2 · 3:45

1. Diferenciar cierre de dedos y agarre. La distancia entre dedos se normaliza por la palma. Una secuencia de cuadros confirma cada transición, y el CSV conserva el cuadro estimado de inicio. Explicar cómo el movimiento local aporta evidencia adicional cuando la configuración activa esa condición.
2. Describir la partición por secuencias, el inicio de movimiento en DexYCB como aproximación a un agarre, y la tolerancia de ±5 cuadros por evento. PCK cuenta también los puntos con referencia válida cuando falta detección. El temblor mide segunda diferencia temporal, y puede incluir movimiento real.
3. Leer la partición, el número de secuencias y los cambios que aparecen en la diapositiva de resultados. Distinguir los puntos porcentuales de las métricas en píxeles. Relacionar precisión, recall y F1 con falsos positivos y omisiones.
4. En la tabla de ablación, comparar una técnica aislada frente a MediaPipe y luego la combinación completa frente a la combinación sin esa técnica. Presentar un resultado desfavorable concreto y su posible costo en precisión o velocidad. Consultar el nombre de la variante congelada antes de la exposición.

**Transición.** «El promedio resume la comparación. Los cuadros de falla muestran a qué tipo de error corresponde».

## Integrante 3 · 3:10

1. Mostrar una falla visible en la diapositiva 8. Señalar si hay una mano anotada sin estimación, o un esqueleto presente con un error localizado. Presentar la oclusión o la perspectiva como hipótesis cuando la imagen solamente sugiere la causa.
2. Explicar las mejoras y pérdidas observadas usando la diapositiva 9. Mencionar que DexYCB aporta evaluación de agarres y que las sueltas requieren los videos propios anotados. Mantener explícito el uso del evaluador provisional.
3. Recibir el video del profesor, pasar su ruta entre comillas y escribir en una carpeta nueva. Conservar el archivo original y usar el MP4 anotado para mostrar la salida.

## Secuencia de demostración

Ejecutar desde la raíz del repositorio con el entorno activo y el modelo instalado:

```sh
python correr.py --entrada "/ruta/al/video recibido.mp4" --salida salida/demo --video
```

Mostrar primero el encabezado y un cuadro detectado en `salida/demo/puntos.csv`. Luego abrir `salida/demo/eventos.csv` y localizar un evento en `salida/demo/video_anotado.mp4`. Los índices empiezan en cero. La ausencia de eventos conserva el encabezado. Si una codificación de entrada impide la reproducción, utilizar la conversión local descrita en la guía de ejecución y volver a correr sobre el mismo contenido.

## Preguntas probables

- **¿Por qué usar MediaPipe si la propuesta quiere superarlo?** Su detector y el modelo de puntos son una referencia reproducible. Compartirlos entre variantes permite atribuir diferencias a las técnicas evaluadas.
- **¿Cómo evitan que el flujo rellene cuadros erróneos?** Exige correspondencia de los 21 puntos, consistencia ida y vuelta, límites de error fotométrico y geometría plausible. La recuperación consecutiva tiene un límite de dos cuadros.
- **¿Más suavizado siempre ayuda?** Puede bajar la aceleración aparente mientras desplaza puntos durante cambios rápidos. PCK y temblor revelan aspectos distintos de ese intercambio.
- **¿Cómo distinguen un puño de un agarre?** La geometría arma el evento y, cuando está activada, la evidencia de movimiento coherente alrededor de la mano ayuda a corroborarlo. Un objeto sin textura u oculto puede dejar evidencia insuficiente.
- **¿Por qué el movimiento del objeto sirve como referencia?** DexYCB permite localizar el inicio sostenido de su desplazamiento mediante la pose anotada. Un objeto puede comenzar a moverse unos cuadros después del contacto.
- **¿Cómo evitan fuga experimental?** Cada secuencia completa y todas sus cámaras pertenecen a una sola partición. La selección se congela en validación antes de medir la prueba local.
- **¿Qué limita la generalización?** La evidencia proviene de un solo sujeto de DexYCB y de las configuraciones de cámara descritas en el experimento. Las grabaciones propias amplían las condiciones y permiten medir sueltas.
