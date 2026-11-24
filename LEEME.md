# Seguimiento de manos y eventos de manipulación

En macOS ARM64 se verificó Python 3.12, MediaPipe 0.10.32 y OpenCV contrib 4.12.
La primera instalación necesita acceso a PyPI y al modelo publicado por Google.

```zsh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m scripts.setup
```

## Demostración en CPU

```zsh
python correr.py --entrada "/ruta/al/video.mov" --salida salida
```

La salida contiene `puntos.csv`, con 42 coordenadas por cuadro o celdas vacías si falta la mano, y
`eventos.csv`, con índices ordenados de agarre y suelta. El encabezado se conserva aun sin eventos.
Cuadros desde cero. `--origen-cuadro 1` cambia la convención de exportación.
También se admite una carpeta de imágenes, con orden natural y `--fps` para indicar la cadencia.

Agrega `--video` para abrir `salida/video_anotado.mp4` y `--comparar` para obtener un MP4 lado a lado.
`--baseline` ejecuta MediaPipe original con el detector sencillo y `--tiempos` guarda el resumen.
Después de instalar el modelo, ejecutar la demo sin conexión. Si un contenedor no abre con OpenCV,
usar un MP4 H.264 del mismo video o una carpeta de cuadros en orden. Si el entorno restringe
OpenGL, ejecutar desde Terminal de macOS. MediaPipe inicializa un servicio gráfico en macOS
aunque el modelo use el delegado de inferencia CPU.

## Evaluación de DexYCB

```zsh
python -m scripts.download_dataset
python -m scripts.inspect_dataset --root data/raw/dexycb
python -m scripts.run_experiments --datos data/raw/dexycb --particion development --limite 3 --camara 836212060125 --salida experiments/results/desarrollo_ampliado --tune-events
python -m scripts.run_experiments --datos data/raw/dexycb --particion validation --camara 836212060125 --salida experiments/results/validacion_ampliada --tune-events
python -m scripts.run_experiments --datos data/raw/dexycb --particion test --congelado experiments/results/validacion_ampliada/frozen.json --salida experiments/results/prueba_ampliada
```

La evidencia del subconjunto previamente fijado se conserva en `experiments/results/`.
Para repetir el subconjunto local en la misma Mac se puede usar `data/raw/dexycb/subset`.
Una descarga incompleta se reanuda con el mismo comando. Las cachés se reutilizan por vista,
modelo, parámetros, versiones y estado del código. Nunca mezclar secuencias de prueba con desarrollo.

## Grabaciones propias y entregables

Graba con un celular tres clips horizontales de 30 a 60 s y 30 FPS. En cada clip una persona traslada
cinco objetos distintos de una caja a otra. Mantén ambas cajas y la mano en cuadro, usa una sola cámara
y conserva el audio si no contiene datos personales ajenos. Usa condiciones de buena luz normal, poca
luz y movimiento rápido. Guarda los clips como `buena_luz.mp4`, `poca_luz.mp4` y
`movimiento_rapido.mp4` en `data/raw/custom_videos/`. Se aceptan MOV y M4V.

Anota el primer cuadro en que la mano toma control de cada objeto y el primer cuadro en que deja de sostenerlo.
Haz cinco pares por clip. La anotación humana se guarda en CSV con origen cero.

```zsh
python -m scripts.annotate_videos data/raw/custom_videos/buena_luz.mp4 data/annotations/custom_videos/buena_luz.csv
```

Repite para poca luz y movimiento rápido. Espacio reproduce, A/D retrocede o avanza, G marca agarre, L marca
suelta, X borra, S guarda y Q sale. La opción `--validar` valida los diez eventos.
Después ejecuta `python -m scripts.finalize` con Tectonic, LibreOffice y Node con `pptxgenjs` disponibles.
Se actualizan métricas, videos, informe, presentación y ZIP preliminar. La opción `--definitivo`
comprueba todos los archivos obligatorios antes de emitir el paquete oficial.

## Pruebas

```zsh
python -m pip install pytest==8.4.2
python -m pytest -q
```

El modelo debe estar instalado para las pruebas de integración nativa.

## Evaluador de la asignatura

Al recibirlo, revisar su origen, el significado de sus métricas y el origen de índices.
Ejecutarlo según sus instrucciones con los CSV del contrato. Si su salida es JSON,
conservar su contenido y la huella de la versión evaluada mediante
`python -m scripts.import_official --evaluador RUTA_EVALUADOR --resultados RUTA_JSON`.
Los resultados provisionales de DexYCB conservan su identidad y procedencia experimental.
