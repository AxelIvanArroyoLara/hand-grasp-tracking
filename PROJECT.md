# Del video de celular a la demostración para robot

Proyecto final de Visión Artificial. Entrega y exposición de diez minutos el 2 de diciembre de 2026.
Una entrada RGB debe producir 21 pares de coordenadas por cuadro y los eventos agarrar y soltar.
El contrato se ejecuta en CPU con `python correr.py --entrada RUTA --salida RUTA`.

## Aceptación

- Comparar cobertura, PCK@10 px y temblor con Hand Landmarker original.
- Comparar F1 de eventos con el detector sencillo. La meta de mejora es 15 puntos porcentuales.
- Evaluar al menos tres técnicas individualmente y con ablaciones en las mismas secuencias.
- Separar desarrollo, validación y prueba por secuencia. Usar DexYCB subject-01 para agarre únicamente.
- Evaluar tres grabaciones propias de 30 a 60 segundos a 30 FPS con cinco agarres y cinco sueltas por video.
- Entregar código, IEEE de cuatro a seis páginas, diapositivas, comparativo y ZIP.
