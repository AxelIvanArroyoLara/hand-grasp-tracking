# DexYCB

Yu-Wei Chao, Wei Yang, Yu Xiang, Pavlo Molchanov, Ankur Handa, Jonathan Tremblay, Yashraj S. Narang, Karl Van Wyk, Umar Iqbal, Stan Birchfield, Jan Kautz y Dieter Fox presentaron *DexYCB: A Benchmark for Capturing Hand Grasping of Objects* en CVPR 2021. Se registraron 582 mil cuadros RGB-D en 1,000 tomas de 10 participantes, con 20 objetos objetivo y ocho cámaras calibradas y sincronizadas a 30 FPS. Cada toma comienza en reposo, sigue el acercamiento y el agarre, y termina con el objeto sostenido. El trabajo reporta evaluaciones de puntos 2D, poses 3D y generación de agarres robóticos. Por ejemplo, en S0 reportan 52.26 mm de error medio articular 3D absoluto con HRNet32 sobre RGB y 27.53 mm con A2J sobre profundidad. El estudio reporta mayor error de HRNet32 ante sujetos (70.10 mm) y vistas (80.63 mm) ausentes del entrenamiento. Estas mediciones documentan la dificultad del dominio y los umbrales temporales del proyecto se definen en su propio protocolo. [Artículo original](https://openaccess.thecvf.com/content/CVPR2021/html/Chao_DexYCB_A_Benchmark_for_Capturing_Hand_Grasping_of_Objects_CVPR_2021_paper.html)

El sitio distribuye el corpus bajo CC BY-NC 4.0. Se usan exclusivamente los archivos `20200709-subject-01.tar.gz` (12.4 GB) y `calibration.tar.gz` (14,464 bytes verificados en el archivo local). El toolkit tiene licencia GPLv3, fue probado originalmente en GNU/Linux con Python 3.7 y las instrucciones completas usan BOP y MANO. El lector local independiente se basó en el esquema documentado y usa NumPy y PyYAML sobre ARM64. [Sitio oficial](https://dex-ycb.github.io/), [manual del toolkit](https://github.com/NVlabs/dex-ycb-toolkit/blob/master/README.md)

## Lectura y particiones

Cada toma declara número de cuadros, ID de extrínsecos, objetos YCB e índice del objeto manipulado en `meta.yml`. El número original de cuadro vincula `color_NNNNNN.jpg` con `labels_NNNNNN.npz`. El lector conserva el orden anatómico de 21 juntas, que coincide con el usado por MediaPipe, y representa el par centinela `(-1, -1)` como faltante. La máscara indexada distingue fondo, cada clase YCB y mano. La pose de cada objeto tiene tres filas y cuatro columnas, con rotación en las tres primeras y traslación métrica en la última. Se leen valores intrínsecos RGB y extrínsecos por cámara. [Esquema oficial](https://github.com/NVlabs/dex-ycb-toolkit/blob/master/README.md#loading-dataset-and-visualizing-samples), [orden de articulaciones y rutas](https://github.com/NVlabs/dex-ycb-toolkit/blob/master/dex_ycb_toolkit/dex_ycb.py)

Las cámaras y los cuadros de una toma comparten partición. Se aplica SHA-256 a `20261202:NOMBRE_TOMA`, se toman los primeros ocho bytes en orden big-endian y se calcula el residuo módulo 100. Los residuos 0–59 corresponden a desarrollo, 60–79 a validación y 80–99 a prueba local. Las proporciones son aproximadas por construcción. La asignación de una toma permanece estable mientras se incorporan nuevas tomas. El tamaño por partición se obtiene del inventario. Ante una descarga en curso, los prefijos de cada partición se limitan a tomas completas por orden del TAR y se guardan separados. Sus muestras son pequeñas y los resultados describen esas tomas y cámaras observadas.

## Referencia provisional de agarre

Para cada vista se extrae la trayectoria de `pose_y[ycb_grasp_ind]` usando exclusivamente las anotaciones. Se descartan poses no finitas, traslaciones con profundidad no positiva y rotaciones con determinante a más de 0.15 de uno. Las primeras cinco poses válidas dentro de los primeros 11 cuadros forman la referencia. Se usa la mediana de las traslaciones de esa ventana y su primera orientación válida. Si la ventana ya cruza el umbral de movimiento, la vista queda sin una referencia inicial confiable.

Se estima el primer cuadro de un tramo de tres cuadros consecutivos con desplazamiento de al menos 8 mm o giro de al menos 12 grados respecto a la referencia. A nivel de toma, se requiere una mayoría estricta de cámaras con estimaciones dentro de un rango máximo de cinco cuadros y se usa la mediana redondeada. Una toma sin consenso queda sin etiqueta temporal apta para F1. El desplazamiento aproxima el levantamiento, que puede ocurrir después del contacto de los dedos. Las sueltas se evalúan únicamente con grabaciones propias anotadas.

## Reproducción

```sh
python -m scripts.download_dataset
python -m scripts.inspect_dataset --decode-rgb
```

La descarga conserva `.part` para reanudar mediante HTTP Range. El script exige 64 GiB libres para el comprimido (11.56 GiB), un límite conservador de extracción (48 GiB) y espacio de operación, coteja la longitud anunciada por Drive y publica una huella SHA-256 local. Durante la extracción comprueba el CRC GZIP y rechaza enlaces, archivos especiales y rutas externas. Si se cuenta con un SHA-256 conocido por una vía confiable, `--subject-sha256` lo coteja antes de extraer. Con los tarballs oficiales locales, `--extract-only` evita el acceso a red. Los datos permanecen fuera de Git y del ZIP.

Para inspeccionar una descarga parcial se puede ejecutar lo siguiente.

```sh
python -m scripts.download_dataset --pilot-dev 3
python -m scripts.inspect_dataset --root data/raw/dexycb/pilot --prefix --decode-rgb \
  --splits data/splits/dexycb_pilot.json --report experiments/manifests/dexycb_pilot_inventory.json
```

Los selectores `--prefix-validation 2` y `--prefix-test 2` preparan raíces análogas bajo `data/raw/dexycb/`. El selector `--assemble-subset` enlaza las tres raíces en `data/raw/dexycb/subset`. La configuración debe quedar congelada antes de ejecutar la inferencia y el cálculo de métricas sobre prueba.
