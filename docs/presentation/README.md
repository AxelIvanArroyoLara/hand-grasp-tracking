# Presentación técnica

`build.cjs` genera diez diapositivas editables y el PDF correspondiente. Lee únicamente experimentos cuyo manifiesto indica `complete`. La comparación usa la prueba local cuando existe, seguida por validación y piloto. La tabla de ablaciones usa validación o el piloto disponible.

Requiere Node.js, `pptxgenjs@4.0.1`, `image-size@1.2.1` y LibreOffice. Con ambas bibliotecas instaladas en una ruta que Node pueda resolver:

```sh
node docs/presentation/build.cjs
```

En un entorno con bibliotecas externas ya disponibles, se puede indicar su directorio mediante `NODE_PATH`. Si LibreOffice requiere una ruta específica, se configura con `SOFFICE`. Para regenerar con fotografías desde otra carpeta, `DEXYCB_ROOT` apunta al dataset local y `FIGURA_FALLAS` a la imagen producida por la inspección. El generador escribe ambos archivos en `deliverables/`. `PRESENTACION_SALIDA` puede redirigir una compilación de prueba y `PRESENTACION_RESULTADOS` permite elegir el directorio de resultados.

Un archivo opcional `docs/presentation/autores.txt` con tres nombres, uno por línea, sustituye los marcadores de autoría en la portada. El guion contiene el reparto de diez minutos y la secuencia de demostración.
