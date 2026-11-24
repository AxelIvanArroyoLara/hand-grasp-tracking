/** Genera la presentación editable a partir de los experimentos y exporta su PDF local. */
'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { createRequire } = require('node:module');
const { pathToFileURL } = require('node:url');
const PptxGenJS = require('pptxgenjs');
const { imageSize } = require('image-size');
const JSZip = createRequire(require.resolve('pptxgenjs'))('jszip');

const root = path.resolve(__dirname, '../..');
const results = path.resolve(process.env.PRESENTACION_RESULTADOS || path.join(root, 'experiments', 'results'));
const output = path.resolve(process.env.PRESENTACION_SALIDA || path.join(root, 'deliverables'));
const data = path.resolve(process.env.DEXYCB_ROOT || path.join(root, 'data', 'raw', 'dexycb'));
const figures = path.join(root, 'experiments', 'figures');
const authorFile = path.join(__dirname, 'autores.txt');
const authors = fs.existsSync(authorFile)
    ? fs.readFileSync(authorFile, 'utf8').split(/\r?\n/).map(line => line.trim()).filter(Boolean)
    : [];
if (authors.length && authors.length !== 3) throw Error('autores.txt debe contener tres nombres');

const C = {
    ink: '182724', dark: '112B29', teal: '116E60', mint: 'BDECCC',
    paper: 'F8F7F0', muted: '455A54', line: 'C7D2C6', white: 'FFFFFF',
    accent: 'F2B366', pale: 'E6EDE2', red: '9A4A41', neutral: '526565',
};
const font = 'Arial';
const names = {
    baseline: 'MediaPipe original', seleccionado: 'Método seleccionado',
    clahe: 'CLAHE', gamma: 'Gamma', equalize: 'Ecualización',
    gaussian: 'Gaussiano', bilateral: 'Bilateral', unsharp: 'Máscara de enfoque',
    roi: 'ROI', flow: 'Lucas–Kanade', kalman: 'Kalman', ema: 'EMA',
    one_euro: 'One Euro', completo: 'Combinación completa', sin_clahe: 'Sin CLAHE',
    sin_roi: 'Sin ROI', sin_flujo: 'Sin flujo', sin_filtro: 'Sin One Euro',
};

function json(file) {
    return fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : null;
}

/** Usa únicamente resultados que cerraron correctamente su ejecución. */
function experiment(partition) {
    const dir = path.join(results, partition);
    const manifest = json(path.join(dir, 'manifest.json'));
    const rows = manifest?.status === 'complete' ? json(path.join(dir, 'ablation.json')) : null;
    if (!Array.isArray(rows) || !rows.length) return null;
    return { partition, rows, manifest };
}

const development = experiment('development');
const validation = experiment('validation');
const test = experiment('test');
const track = test || validation || development;
const ablation = validation || development;
const frozen = json(path.join(results, 'validation', 'frozen.json'));
const baseline = track?.rows.find(row => row.name === 'baseline');
const proposed = track?.rows.find(row => row.name === (test ? 'seleccionado' : frozen?.name || 'completo'))
    || track?.rows.find(row => row.name === 'completo');
const custom = json(path.join(output, 'videos_propios', 'custom_results.json'));
const labels = {
    development: 'Piloto de desarrollo',
    validation: 'Validación',
    test: 'Prueba local reservada',
};
const format = new Intl.NumberFormat('es-MX', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const integer = new Intl.NumberFormat('es-MX', { maximumFractionDigits: 0 });
const num = (value, scale = 1) => Number.isFinite(value) ? format.format(value * scale) : '—';
const pct = value => Number.isFinite(value) ? `${num(value, 100)} %` : '—';
const whole = value => Number.isFinite(value) ? integer.format(value) : '—';
function valueDiff(a, b, scale = 1) {
    if (!Number.isFinite(a) || !Number.isFinite(b)) return '—';
    const change = (b - a) * scale;
    if (Math.abs(change) < 0.05) return num(0);
    return `${change > 0 ? '+' : '−'}${num(Math.abs(change))}`;
}

function evidenceSource(experiment, row = experiment?.rows[0]) {
    if (!row) return 'DexYCB, sujeto 01';
    return `${labels[experiment.partition]} · ${whole(row.sequences)} secuencias · ${whole(row.views)} vistas · ${whole(row.frames)} cuadros`;
}

/** Busca el fotograma original de una vista que aparece en los resultados. */
function frameImage(sequence, camera, index) {
    const file = `color_${String(index).padStart(6, '0')}.jpg`;
    const subject = '20200709-subject-01';
    const candidates = ['', 'extracted', 'subset', 'prefix-test', 'prefix-validation', 'pilot'].flatMap(location => [
        path.join(data, location, subject, sequence, camera, file),
        path.join(data, location, sequence, camera, file),
    ]);
    return candidates.find(candidate => fs.existsSync(candidate));
}

const example = development?.rows[0]?.details?.[0];
const coverFrame = example && Number.isInteger(example.expected_grasp)
    ? Math.max(0, example.expected_grasp + 5) : 42;
const coverImage = example && frameImage(example.sequence, example.camera, coverFrame);
const sample = development?.rows[0]?.details?.[1] || example;
const sampleFrame = sample && Number.isInteger(sample.expected_grasp)
    ? Math.max(0, sample.expected_grasp - 3) : 27;
const sampleImage = sample && frameImage(sample.sequence, sample.camera, sampleFrame);

const pptx = new PptxGenJS();
pptx.layout = 'LAYOUT_WIDE';
pptx.lang = 'es-MX';
pptx.title = 'Seguimiento de manos y detección de eventos de manipulación';
pptx.subject = 'Proyecto final de Visión Artificial';
pptx.author = authors.length ? authors.join(', ') : 'Equipo de Visión Artificial';

function text(slide, value, x, y, w, h, style = {}) {
    const { color = C.ink, fontSize = 19, bold = false, ...more } = style;
    slide.addText(value, { x, y, w, h, fontFace: font, color, fontSize, bold,
        margin: 0, valign: 'middle', breakLine: false, ...more });
}

function line(slide, x, y, w, color = C.line) {
    slide.addShape(pptx.ShapeType.line, { x, y, w, h: 0, line: { color, width: 0.85 } });
}

function arrow(slide, x, y, w, color = C.teal) {
    slide.addShape(pptx.ShapeType.line, {
        x, y, w, h: 0, line: { color, width: 1.65, endArrowType: 'triangle' },
    });
}

function photo(slide, file, x, y, w, h) {
    if (!file) return;
    const { width, height } = imageSize(fs.readFileSync(file));
    const factor = Math.min(w / width, h / height);
    const fittedWidth = width * factor;
    const fittedHeight = height * factor;
    slide.addImage({ path: file, x: x + (w - fittedWidth) / 2, y: y + (h - fittedHeight) / 2,
        w: fittedWidth, h: fittedHeight });
}

function title(value, options = {}) {
    const slide = pptx.addSlide();
    slide.background = { color: C.paper };
    text(slide, value, 0.72, 0.56, 11.90, 0.68, { bold: true, fontSize: options.size || 36 });
    if (options.caption) text(slide, options.caption, 0.74, 1.31, 11.85, 0.32, { fontSize: 14, color: C.muted });
    return slide;
}

function foot(slide, value, dark = false) {
    const color = dark ? C.mint : C.muted;
    line(slide, 0.72, 6.91, 11.86, dark ? '46716B' : C.line);
    text(slide, value, 0.72, 7, 11.86, 0.22, { fontSize: 10.5, color });
}

function section(slide, heading, body, x, y, w, dark = false) {
    text(slide, heading, x, y, w, 0.40, { bold: true, fontSize: 20, color: dark ? C.mint : C.teal });
    text(slide, body, x, y + 0.46, w, w < 4 ? 1.13 : 0.86,
        { fontSize: 18, color: dark ? C.white : C.ink, valign: 'top' });
}

function diagram(slide, items, x, y, w, h) {
    const gap = 0.36;
    const block = (w - gap * (items.length - 1)) / items.length;
    for (const [i, item] of items.entries()) {
        const left = x + i * (block + gap);
        slide.addShape(pptx.ShapeType.rect, {
            x: left, y, w: block, h, fill: { color: i % 2 ? C.pale : C.dark },
            line: { color: i % 2 ? C.pale : C.dark, transparency: 100 },
        });
        text(slide, item, left + 0.07, y + 0.04, block - 0.14, h - 0.08,
            { fontSize: 16, color: i % 2 ? C.ink : C.white, align: 'center', bold: true });
        if (i < items.length - 1) arrow(slide, left + block + 0.05, y + h / 2, gap - 0.10);
    }
}

function dataTable(slide, headers, body, left, top, widths, options = {}) {
    const getCells = (row, header, idx) => row.map((cell, col) => ({
        text: cell,
        options: {
            align: col ? 'center' : 'left',
            bold: header || col === 0 || options.highlight?.includes(idx),
            color: header ? C.white : options.highlight?.includes(idx) ? C.teal : C.ink,
            fill: { color: header ? C.dark : idx % 2 === 0 ? C.white : C.pale },
        },
    }));
    slide.addTable([getCells(headers, true, -1), ...body.map((row, i) => getCells(row, false, i))],
        { x: left, y: top, w: widths.reduce((a, b) => a + b), colW: widths,
            autoPage: false, rowH: options.rowH || 0.46, fontFace: font, fontSize: options.size || 15,
            margin: [3, 7, 3, 7], border: { type: 'solid', pt: 0.4, color: C.line }, valign: 'middle' });
}

function appendNotes(slide, ...lines) {
    slide.addNotes(lines.join('\n\n'));
}

// 1. Portada
{
    const slide = pptx.addSlide();
    slide.background = { color: C.dark };
    text(slide, 'Proyecto final de Visión Artificial', 0.75, 0.75, 6.4, 0.39,
        { color: C.mint, fontSize: 16, bold: true });
    text(slide, 'Seguimiento de manos\ny detección de eventos\nde manipulación', 0.72, 1.52, 6.45, 2.74,
        { color: C.white, fontSize: 42, bold: true, valign: 'top' });
    text(slide, 'Del video de celular\na la demostración para robot', 0.75, 4.62, 6.12, 0.72,
        { color: C.mint, fontSize: 22, valign: 'top' });
    if (coverImage) photo(slide, coverImage, 7.43, 1.23, 5.16, 4.52);
    const people = authors.length ? authors.join(' · ') : '[Integrante 1] · [Integrante 2] · [Integrante 3]';
    text(slide, people, 0.75, 6.03, 11.85, 0.27, { color: C.white, fontSize: 14 });
    const status = custom?.micro && test ? 'Evaluación provisional' : 'Entrega preliminar';
    foot(slide, `2 de diciembre de 2026 · ${status}`, true);
    appendNotes(slide, 'Integrante 1. Presentar el problema de convertir una grabación RGB en una secuencia geométrica y marcas temporales.',
        coverImage ? `Imagen RGB de DexYCB, sujeto 01, ${example.sequence}, cámara ${example.camera}, cuadro ${coverFrame}. https://dex-ycb.github.io/` : 'Fuente de datos: https://dex-ycb.github.io/');
}

// 2. Problema
{
    const slide = title('Qué debe recuperar el sistema');
    section(slide, 'Pose en cada cuadro', '21 puntos en píxeles con el orden anatómico de MediaPipe.', 0.75, 1.68, 5.4);
    section(slide, 'Instantes de interacción', 'Cuadro estimado en que la persona agarra o suelta el objeto.', 0.75, 3.01, 5.4);
    section(slide, 'Condiciones difíciles', 'La oclusión, la poca luz y el movimiento rápido pueden degradar el seguimiento.', 0.75, 4.34, 5.45);
    if (sampleImage) photo(slide, sampleImage, 6.68, 1.63, 5.81, 4.35);
    foot(slide, 'Entrada monocular RGB · Inferencia en CPU');
    appendNotes(slide, 'Integrante 1. Mostrar que el contacto puede ocultar simultáneamente puntas de los dedos y parte del objeto.',
        'Pu, Chong y Lim, Robustness Evaluation in Hand Pose Estimation Models using Metamorphic Testing. https://arxiv.org/abs/2303.04566',
        'Google AI Edge, Hand Landmarker. https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker/python',
        sampleImage ? `Imagen RGB de DexYCB, ${sample.sequence}, ${sample.camera}, cuadro ${sampleFrame}.` : '');
}

// 3. Arquitectura
{
    const slide = title('Seguimiento y recuperación temporal');
    diagram(slide, ['Video\nRGB', 'Corrección\nadaptativa', 'MediaPipe\nVIDEO', 'ROI y\nflujo óptico', 'Filtro\ntemporal', 'CSV de\nlandmarks'],
        0.74, 1.84, 11.82, 1.11);
    section(slide, 'Fotometría', 'CLAHE actúa en cuadros oscuros. También evaluamos gamma, realce y reducción de ruido.', 0.75, 3.65, 3.51);
    section(slide, 'Recuperación', 'El recorte reintenta la detección. Lucas–Kanade verifica los 21 puntos en ida y vuelta.', 4.89, 3.65, 3.49);
    section(slide, 'Estabilidad', 'One Euro ajusta el suavizado según la velocidad. También evaluamos EMA y Kalman.', 9.02, 3.65, 3.52);
    foot(slide, 'Las variantes comparten modelo, delegado y umbrales de MediaPipe');
    appendNotes(slide, 'Integrante 1. Explicar que se realiza detección de cuadro completo siempre y que ROI y flujo son recuperaciones. LK deja de emitir después de dos cuadros recuperados consecutivos.',
        'Fuentes: https://arxiv.org/abs/2006.10214 · https://doi.org/10.1016/B978-0-12-336156-1.50061-6 · https://courses.cs.duke.edu/cps274/fall11/papers/LucasKanade81.pdf · https://gery.casiez.net/1euro/');
}

// 4. Eventos
{
    const slide = title('Detección de agarre y suelta');
    diagram(slide, ['Mano libre', 'Cierre\ncandidato', 'Objeto\nretenido', 'Apertura\ncandidata', 'Mano libre'],
        0.74, 1.86, 11.82, 1.10);
    section(slide, 'Apertura y flexión', 'Las distancias se normalizan por el tamaño de la palma. La histéresis estabiliza las transiciones.', 0.75, 3.65, 5.54);
    section(slide, 'Movimiento local', 'Puntos cercanos a la mano aportan evidencia de movimiento coordinado con el objeto.', 6.82, 3.65, 5.55);
    text(slide, 'La confirmación usa varios cuadros y conserva el instante estimado de inicio.',
        0.75, 5.46, 11.87, 0.52, { fontSize: 19, color: C.teal, bold: true });
    foot(slide, 'Referencia sencilla provisional basada en apertura y desaceleración');
    appendNotes(slide, 'Integrante 2. Ilustrar que los dedos pueden cerrarse en vacío. El flujo del entorno aporta una condición visual adicional cuando está activada en la configuración. La regla de suelta utiliza apertura y duración mínima de sujeción.',
        'Geometría de pulgar e índice y oclusiones en manipulación: https://arxiv.org/html/2603.11383v2');
}

// 5. Datos y métricas
{
    const slide = title('Protocolo de evaluación');
    section(slide, 'DexYCB · sujeto 01', 'Los cuadros y las cámaras de cada secuencia permanecen en una sola partición.', 0.75, 1.72, 5.51);
    section(slide, 'Referencia de agarre', 'Calculamos el inicio del movimiento del objeto a partir de su pose anotada.', 0.75, 3.25, 5.51);
    section(slide, 'Grabaciones propias', 'Buena luz, poca luz y movimiento rápido. Cada video requiere cinco agarres y cinco sueltas anotados.', 0.75, 4.78, 5.51);
    slide.addShape(pptx.ShapeType.line, { x: 6.68, y: 1.83, w: 0, h: 4.22, line: { color: C.line, width: 1 } });
    text(slide, 'Cobertura', 7.1, 1.78, 2.2, 0.37, { fontSize: 19, bold: true });
    text(slide, 'Detección con mano visible', 9.17, 1.78, 3.35, 0.37, { fontSize: 17 });
    text(slide, 'PCK@10 px', 7.1, 2.87, 2.0, 0.37, { fontSize: 19, bold: true });
    text(slide, 'Puntos a ≤10 px de la referencia', 9.17, 2.67, 3.35, 0.81, { fontSize: 17 });
    text(slide, 'Temblor', 7.1, 3.98, 2.05, 0.37, { fontSize: 19, bold: true });
    text(slide, 'Segunda diferencia temporal', 9.17, 3.78, 3.35, 0.81, { fontSize: 17 });
    text(slide, 'F1 de eventos', 7.1, 5.10, 2.00, 0.37, { fontSize: 19, bold: true });
    text(slide, 'Emparejamiento uno a uno, ±5 cuadros', 9.17, 4.90, 3.35, 0.81, { fontSize: 17 });
    foot(slide, 'Las anotaciones intervienen únicamente al evaluar');
    appendNotes(slide, 'Integrante 2. Explicar la selección en validación y la congelación previa a la prueba. PCK incluye puntos válidos de anotación aunque falte predicción. En DexYCB el tipo evaluado es agarrar. Temblor reporta píxeles por cuadro al cuadrado.',
        'DexYCB, proyecto y toolkit. https://dex-ycb.github.io/ · https://github.com/NVlabs/dex-ycb-toolkit');
}

// 6. Evaluación y gráfica editable
{
    const slide = title('Comparación con la línea base', { caption: evidenceSource(track, baseline) });
    if (baseline && proposed) {
        const metrics = [
            ['Detección', 'detection_rate', pct, 100, ' pp'],
            ['PCK@10 px', 'pck_10', pct, 100, ' pp'],
            ['Temblor', 'jitter_px', v => `${num(v)} px/cuadro²`, 1, ''],
            ['Velocidad CPU', 'fps', v => `${num(v)} FPS`, 1, ''],
        ];
        const rows = metrics.map(([label, key, display, scale, unit]) => [
            label, display(baseline[key]), display(proposed[key]),
            valueDiff(baseline[key], proposed[key], scale) + unit,
        ]);
        dataTable(slide, ['Métrica', 'Original', 'Propuesto', 'Cambio'], rows,
            0.74, 2.12, [1.64, 1.74, 1.74, 1.08], { size: 13.4, rowH: 0.64 });
        text(slide, 'Agarres · métricas de eventos (%)', 7.30, 1.76, 5.15, 0.32,
            { fontSize: 17, bold: true, color: C.teal });
        const eventMetrics = [['Precisión', 'precision'], ['Recall', 'recall'], ['F1', 'f1']];
        const measured = eventMetrics.filter(([, key]) => Number.isFinite(baseline[key]) && Number.isFinite(proposed[key]));
        if (measured.length) {
            const dataSeries = (name, row) => ({ name, labels: measured.map(([label]) => label),
                values: measured.map(([, key]) => 100 * row[key]) });
            slide.addChart(pptx.ChartType.bar, [
                dataSeries('Original', baseline), dataSeries('Propuesto', proposed),
            ], {
                x: 7.15, y: 2.15, w: 5.45, h: measured.length === 3 ? 3.92 : 3.61,
                barDir: 'col', barGrouping: 'clustered',
                chartColors: [C.neutral, C.teal], showLegend: true, legendPos: 'b', legendFontSize: 12,
                legendFontFace: font, catAxisLabelFontFace: font, catAxisLabelFontSize: 12,
                valAxisLabelFontFace: font, valAxisLabelFontSize: 10, valAxisMinVal: 0,
                valAxisMaxVal: 105, valAxisMajorUnit: 25, valAxisLabelFormatCode: '0',
                valGridLine: { color: C.line, size: 0.5 }, showTitle: false,
            });
            for (const [i, [label, key]] of eventMetrics.filter((cell) => !measured.includes(cell)).entries()) {
                const value = row => {
                    if (Number.isFinite(row[key])) return pct(row[key]);
                    return key === 'precision' && row.tp + row.fp === 0 ? 'sin predicciones' : 'sin valor';
                };
                text(slide, `${label} · Original ${value(baseline)} · Propuesto ${value(proposed)}`,
                    7.30, 5.88 + i * 0.23, 5.20, 0.24, { fontSize: 12.5, color: C.muted });
            }
        } else {
            dataTable(slide, ['Métrica', 'Original', 'Propuesto'],
                eventMetrics.map(([label, key]) => [label, pct(baseline[key]), pct(proposed[key])]),
                7.30, 2.15, [1.45, 1.8, 1.8], { rowH: 0.59 });
        }
        text(slide, `F1 de agarre  ${pct(baseline.f1)} / ${pct(proposed.f1)}  (${valueDiff(baseline.f1, proposed.f1, 100)} pp)`,
            0.75, 5.64, 6.34, 0.34, { fontSize: 15.4, bold: true, color: C.teal });
        const { illumination, roi, flow, smoothing } = proposed.tracking_options;
        const enabled = [names[illumination], roi && names.roi, flow && names.flow, names[smoothing]].filter(Boolean);
        if (enabled.length) text(slide, `Propuesta con ${enabled.join(', ')}`, 0.75, 6.38, 11.8, 0.26,
            { fontSize: 13, color: C.muted });
    } else {
        text(slide, 'Comparación pendiente de un experimento completo.', 0.75, 2.30, 10.80, 0.67,
            { fontSize: 22, color: C.muted });
    }
    foot(slide, test ? 'Prueba con configuración congelada · Evaluación provisional' : 'Resultados preliminares · Evaluación provisional');
    appendNotes(slide, 'Integrante 2. Leer el cambio en puntos porcentuales para detección, PCK y F1. Explicar qué indica un temblor más bajo y señalar los cambios desfavorables.',
        track ? `Resultados utilizados: experiments/results/${track.partition}/ablation.json.` : '');
}

// 7. Ablación
{
    const slide = title('Aporte individual de las técnicas', { caption: evidenceSource(ablation) });
    if (ablation) {
        const order = ['baseline', 'clahe', 'roi', 'flow', 'one_euro', 'completo',
            'sin_clahe', 'sin_roi', 'sin_flujo', 'sin_filtro'];
        const rows = order.map(name => ablation.rows.find(row => row.name === name)).filter(Boolean);
        const body = rows.map(row => [names[row.name], pct(row.detection_rate), pct(row.pck_10),
            num(row.jitter_px), pct(row.f1), num(row.fps)]);
        dataTable(slide, ['Configuración', 'Detección', 'PCK@10 px', 'Temblor¹', 'F1', 'FPS'],
            body, 0.74, 1.78, [3.08, 1.75, 1.92, 1.75, 1.65, 1.67],
            { size: 13, rowH: 0.39, highlight: rows.flatMap((row, i) => row.name === frozen?.name ? [i] : []) });
        text(slide, '¹ Píxeles por cuadro cuadrado.', 0.76, 6.53, 11.80, 0.21, { fontSize: 10.5, color: C.muted });
    } else {
        text(slide, 'Ablaciones pendientes de resultados completos.', 0.75, 2.30, 11.50, 0.66, { fontSize: 22, color: C.muted });
    }
    foot(slide, 'Cada variante usa exactamente las mismas vistas de su partición');
    appendNotes(slide, 'Integrante 2. Comparar una técnica aislada y la misma técnica al quitarla de la combinación completa. Comentar cualquier intercambio entre temblor y precisión. Las variantes gamma, ecualización, gaussiano, bilateral, enfoque, EMA y Kalman están en el registro completo.',
        ablation ? `Resultados utilizados: experiments/results/${ablation.partition}/ablation.json.` : '');
}

// 8. Inspección de fallas
{
    const failures = baseline?.failures || [];
    const figure = process.env.FIGURA_FALLAS || [
        'falla_dexycb.jpg', 'fallas.png', 'fallas_representativas.png', 'fallos.png', 'falla.png',
    ].map(file => path.join(figures, file)).find(file => fs.existsSync(file));
    const item = failures.find(([, seq, camera, frame]) => frameImage(seq, camera, frame));
    const slide = title('Análisis visual de una falla');
    if (figure && fs.existsSync(figure)) {
        const meta = json(figure.replace(/\.[^.]+$/, '.json'));
        photo(slide, figure, 0.74, 1.55, 11.84, 4.44);
        if (Number.isFinite(meta?.baseline_median_px)) {
            text(slide, `MediaPipe original · mediana de error de ${num(meta.baseline_median_px)} px en el cuadro ${meta.frame}`,
                0.75, 6.22, 11.82, 0.34, { fontSize: 16.5, color: C.teal, bold: true });
        }
        foot(slide, meta ? `DexYCB · Secuencia ${meta.sequence} · Cámara ${meta.camera}` : 'Imágenes reales de DexYCB');
    } else if (item) {
        const [error, seq, camera, frame] = item;
        photo(slide, frameImage(seq, camera, frame), 0.75, 1.53, 7.28, 5.03);
        section(slide, 'MediaPipe original', error >= 1e6 ? 'La evaluación registró una detección ausente con referencia visible.'
            : `La mediana del error en este cuadro fue ${num(error)} px.`, 8.26, 2.11, 4.26);
        text(slide, `Cuadro ${frame}\nSecuencia ${seq}\nCámara ${camera}`, 8.26, 3.91, 4.26, 1.17,
            { fontSize: 17, color: C.muted, valign: 'top' });
    } else {
        text(slide, 'La inspección visual requiere cuadros de una ejecución registrada.', 0.75, 2.30, 11.50, 0.67,
            { fontSize: 22, color: C.muted });
    }
    if (!figure || !fs.existsSync(figure)) foot(slide, 'Imágenes reales de DexYCB');
    appendNotes(slide, 'Integrante 3. Señalar los puntos ausentes o desplazados. Si se muestran ambos métodos, se visualizan solo las predicciones y se cuantifica el error de la línea base contra la anotación.',
        'Imágenes de la evaluación sobre DexYCB. https://dex-ycb.github.io/');
}

// 9. Conclusiones
{
    const slide = title('Qué muestran los resultados');
    function conclusion(metric, short, factor, unit, lowerIsBetter = false) {
        if (!baseline || !proposed || !Number.isFinite(baseline[metric]) || !Number.isFinite(proposed[metric])) {
            return `${short} pendiente de medición.`;
        }
        const a = baseline[metric], b = proposed[metric];
        const difference = Math.abs(a - b) * factor;
        if (difference < 0.05) return `${short} se mantiene en la comparación.`;
        const change = lowerIsBetter ? b < a ? 'baja' : 'sube' : b > a ? 'sube' : 'baja';
        return `${short} ${change} ${num(difference)}\u00a0${unit}.`;
    }
    section(slide, 'Seguimiento', `${conclusion('detection_rate', 'La detección', 100, 'pp')} ${conclusion('pck_10', 'El PCK@10 px', 100, 'pp')}`, 0.76, 1.70, 8.0);
    section(slide, 'Estabilidad y agarre', `${conclusion('jitter_px', 'El temblor', 1, 'px/cuadro²', true)} ${conclusion('f1', 'El F1 de agarre', 100, 'pp')}`, 0.76, 3.20, 8.0);
    section(slide, 'Alcance', custom?.micro ? `Videos propios · F1 de suelta ${pct(custom.micro.proposed?.by_kind?.soltar?.f1)}. La línea base obtuvo ${pct(custom.micro.baseline?.by_kind?.soltar?.f1)}.`
        : 'La estimación de sueltas requiere validación con las tres grabaciones propias anotadas.', 0.76, 4.70, 8.0);
    if (proposed && Number.isFinite(proposed.fps)) {
        text(slide, num(proposed.fps), 9.30, 2.54, 3.07, 1.09,
            { fontSize: 53, bold: true, align: 'center', color: C.teal });
        text(slide, 'cuadros/s en CPU', 9.32, 3.74, 3.03, 0.35,
            { fontSize: 17, align: 'center' });
    }
    foot(slide, track ? `${labels[track.partition]} · Evaluación provisional` : 'Evaluación pendiente');
    appendNotes(slide, 'Integrante 3. Distinguir mejoras parciales y objetivos pendientes. Las cifras dependen del subconjunto y de la definición provisional del agarre.');
}

// 10. Demostración
{
    const slide = pptx.addSlide();
    slide.background = { color: C.dark };
    text(slide, 'Demostración con un video nuevo', 0.72, 0.69, 11.93, 0.80,
        { fontSize: 37, bold: true, color: C.white });
    text(slide, 'python correr.py --entrada VIDEO --salida SALIDA', 0.75, 2.25, 11.72, 0.60,
        { fontFace: 'Courier New', fontSize: 23, color: C.white });
    text(slide, 'Añadir --video para guardar la visualización anotada', 0.75, 3.05, 11.67, 0.40,
        { fontSize: 18, color: C.mint });
    section(slide, 'puntos.csv', 'Una fila por cuadro con 21 pares de coordenadas.', 0.75, 4.24, 5.42, true);
    section(slide, 'eventos.csv', 'Cuadros estimados de agarre y suelta.', 6.84, 4.24, 5.40, true);
    foot(slide, 'Modelo y dependencias instalados en el equipo de demostración', true);
    appendNotes(slide, 'Integrante 3. Ejecutar el comando sobre el archivo del profesor. Revisar una fila con puntos y la secuencia de eventos. Abrir el MP4 anotado si el tiempo permite.');
}

async function exportFiles() {
    fs.mkdirSync(output, { recursive: true });
    const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'presentacion-vision-'));
    try {
        const deck = path.join(temporary, 'presentacion.pptx');
        // PptxGenJS 4.0.1 declara un maestro por diapositiva aunque exporta un maestro compartido.
        const archive = await JSZip.loadAsync(await pptx.write({ outputType: 'nodebuffer' }));
        const part = '[Content_Types].xml';
        const manifest = await archive.file(part).async('string');
        const cleaned = manifest.replace(
            /<Override PartName="\/(ppt\/slideMasters\/slideMaster\d+\.xml)"[^>]*\/>/g,
            (entry, target) => archive.file(target) ? entry : '',
        );
        archive.file(part, cleaned);
        fs.writeFileSync(deck, await archive.generateAsync({ type: 'nodebuffer', compression: 'DEFLATE' }));
        const soffice = process.env.SOFFICE || 'soffice';
        const profile = pathToFileURL(path.join(temporary, 'profile')).href;
        const conversion = spawnSync(soffice, [
            `-env:UserInstallation=${profile}`, '--headless', '--convert-to', 'pdf', '--outdir', temporary, deck,
        ], { encoding: 'utf8', timeout: 90000 });
        if (conversion.error) throw conversion.error;
        const pdf = path.join(temporary, 'presentacion.pdf');
        if (conversion.status !== 0 || !fs.existsSync(pdf)) throw Error(conversion.stderr || conversion.stdout || 'Falló la exportación PDF');
        for (const number of [deck, pdf]) fs.copyFileSync(number, path.join(output, path.basename(number)));
        console.log(output);
    } finally {
        fs.rmSync(temporary, { recursive: true, force: true });
    }
}

exportFiles().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
