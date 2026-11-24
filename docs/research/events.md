# Detección de interacción en video RGB

Chiche, Jamme, Martinez y Gomes enviaron su estudio de seguimiento de manos para manipulación robótica el 11 de marzo de 2026 y publicaron la revisión v2 el 12 de mayo. Su sistema estima la apertura de una pinza a partir de la geometría del pulgar y el índice. Utiliza MediaPipe, profundidad y cinemática inversa para reproducir trayectorias. Los autores reportan 86.7 % de éxito en su protocolo estructurado, 9.3 % en entornos no estructurados y una caída de 57 a 68 % en el *jerk* con suavizado EMA. En un video ocluido de 347 cuadros, publican 62.8 % de detección con MediaPipe y 67.7 % con WiLoR, equivalentes a 4.9 puntos porcentuales. Estas métricas corresponden al experimento de los autores. La geometría de apertura informa las reglas del proyecto y se sustituye la profundidad por evidencia visual de movimiento en RGB. [Chiche et al., arXiv v2](https://arxiv.org/html/2603.11383v2)

Pu, Chong y Lim enviaron su estudio sobre pruebas metamórficas en estimación de pose el 8 de marzo de 2023. Compararon MediaPipe Hands, OpenPose, BodyHands y NSRM Hand bajo variaciones de iluminación, oclusión y desenfoque. Informan que el desenfoque diagonal dejó sin identificar al menos 50 % de las manos en MediaPipe Hands bajo sus condiciones. Las tres perturbaciones motivan el protocolo propio y la separación por condición de grabación. [Pu et al., arXiv](https://arxiv.org/abs/2303.04566)

Shan, Geng, Shu y Fouhey reportaron en CVPR 2020 un conjunto de 100 mil cuadros anotados con estado de contacto y posición del objeto. Su formulación distingue geometría de la mano, estado de contacto y objeto asociado. El detector del proyecto usa apertura como candidato y busca evidencia de movimiento separado alrededor de la mano, por lo que no requiere entrenar su modelo de contacto. [Shan et al., arXiv](https://arxiv.org/abs/2006.06669)

La publicación de Chao et al. en CVPR 2021 define DexYCB para estudiar poses de mano y objeto durante agarres. El inicio del movimiento del objeto anotado se usa en la evaluación del proyecto como aproximación temporal al agarre. El movimiento sostenido permite descartar ruido de pose de un cuadro. El tiempo entre contacto físico y movimiento visible puede variar según el objeto y la acción. [Chao et al., DexYCB](https://dex-ycb.github.io/)

## Candidatos implementados

- El detector sencillo provisional marca un agarre cuando una mano previamente abierta se cierra y desacelera. Marca una suelta cuando la mano vuelve a abrirse.
- El sistema propuesto combina extensión del dedo, distancia pulgar-índice normalizada por la palma, suavizado de la apertura, histéresis y persistencia. La estimación temporal apunta al primer cuadro del candidato. El detector devuelve el evento después de confirmarlo.
- La evidencia visual se calcula con Lucas–Kanade piramidal sobre esquinas cercanas a los dedos y fuera de la envolvente de la mano. Se filtran las trayectorias incoherentes al volver al cuadro anterior. Se resta el desplazamiento mediano del fondo si hay suficientes esquinas. El movimiento coherente local a la mano refuerza la hipótesis de agarre. La opción `motion_gate: false` permite medir el efecto de retirar esta evidencia.
- El umbral de apertura tiene incertidumbre para agarres de objetos grandes, oclusiones y posiciones oblicuas. Una cámara en movimiento o un entorno con poca textura puede debilitar la confirmación visual. La condición de suelta aún debe contrastarse con videos propios anotados.
- Las reglas son modelos iniciales ligeros. La comparación con regresión logística, k-NN o SVM requiere ejemplos de eventos anotados y rasgos calculados en secuencias de desarrollo. Los eventos estimados a partir de anotaciones de pose se reservan para evaluación y entrenamiento autorizado.

## Comparación supervisada exploratoria

`scripts/compare_event_classifiers.py` compara las reglas con un umbral adaptativo de apertura, regresión logística, SVM con núcleo RBF y k-NN de cinco vecinos. El umbral opera sobre la caída respecto a la apertura máxima de los 12 cuadros anteriores. Los clasificadores añaden apertura, extensión, pinza, cambios de apertura y pinza, rapidez y aceleración del centro de la palma calculados en el cuadro actual y hasta dos anteriores. Las pérdidas de seguimiento reinician el cálculo de los cambios.

Para entrenar se marcan como positivos los cuadros a ±2 del inicio estimado del agarre en desarrollo. La estandarización se ajusta sobre esos mismos datos. La comparación explora tres umbrales por modelo solo en validación y usa la tolerancia de ±5 cuadros. Se conserva el máximo por tramo sobre el umbral, con un espacio mínimo de ocho cuadros entre candidatos. Este decodificador procesa el video después de recibir todos sus cuadros. Los conteos se agregan por vista y todas las vistas de una toma pertenecen a una sola partición.

El tamaño que determina la diversidad de la muestra es el número de tomas de agarre, aunque cada toma genere muchos cuadros y cámaras. Una comparación breve sobre un sujeto y un conjunto reducido de objetos sirve para rechazar candidatos o plantear ajustes en desarrollo. Los intervalos positivos se aproximan con movimiento del objeto y el estudio cubre exclusivamente agarres.

```bash
python -m scripts.compare_event_classifiers --datos data/raw/dexycb/subset \
  --salida experiments/results/event_classifiers.json --camara 836212060125 \
  --config experiments/results/validation/selected.yaml \
  --limite-desarrollo 3 --limite-validacion 2 --reusar-busqueda
```

La opción `--reusar-busqueda` recupera los landmarks de la caché de desarrollo y validación generada con `--tune-events`. Usa la configuración del seguimiento seleccionada en validación.

## Observación del piloto de desarrollo

En las tres vistas iniciales de la cámara `836212060125`, el detector sencillo y las reglas del sistema completo obtuvieron F1 de agarre de 0.50, con un acierto, cero falsos positivos y dos omisiones. En las dos omisiones, la apertura del sistema completo rondaba 0.94–0.95 en el inicio de movimiento anotado. El umbral absoluto de cierre de 0.67 solo activó el candidato de la tercera toma, con apertura cercana a 0.59. El intervalo observado muestra el efecto de la proyección 2D y del tipo de agarre sobre este descriptor. Las cifras corresponden al piloto de desarrollo y la tabla se conserva en [ablation.json](../../experiments/results/development/ablation.json).


## Resultado exploratorio en validación

Los ajustes supervisados usaron 15 cuadros positivos y 177 negativos de tres tomas de desarrollo. En validación hubo dos agarres de referencia de una sola cámara y una de las dos vistas carecía de rasgos utilizables. Las reglas de referencia, el umbral adaptativo, la regresión logística con *liblinear*, la SVM y k-NN obtuvieron F1 de 0.00 en los umbrales evaluados. El umbral adaptativo y la logística generaron hasta tres falsos positivos y la SVM generó uno por umbral. k-NN y las reglas de referencia omitieron ambos agarres sin producir falsas alarmas. Las reglas quedaron en la inferencia de entrega y el estudio supervisado se conserva como exploratorio. [Resultados detallados](../../experiments/results/event_classifiers.json)
