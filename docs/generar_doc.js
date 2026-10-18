// Genera docs/EP2_Equipo04_Martinez-Castro-Larrieu.docx (arc42 EP1 corregido + EP2)
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun, AlignmentType,
  HeadingLevel, WidthType, ShadingType, BorderStyle, Footer, PageNumber, PageBreak, LevelFormat,
  TabStopType, TabStopPosition,
} = require("docx");

const D = path.join(__dirname, "diagramas");
const AZUL = "1F6FEB", AZUL_OSC = "1A4F9C", GRIS = "5B6777", CELDA = "EEF4FD";
const ANCHO = 9906; // A4 con márgenes de 1000
const PAGINAS = JSON.parse(fs.existsSync(path.join(__dirname, "paginas.json")) ? fs.readFileSync(path.join(__dirname, "paginas.json")) : "{}");

// ---------- texto con **negrita** y `código`
function runs(t, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`)/g;
  let last = 0, m;
  while ((m = re.exec(t))) {
    if (m.index > last) out.push(new TextRun({ text: t.slice(last, m.index), ...base }));
    const s = m[0];
    if (s.startsWith("**")) out.push(new TextRun({ text: s.slice(2, -2), bold: true, ...base }));
    else if (s.startsWith("*")) out.push(new TextRun({ text: s.slice(1, -1), italics: true, ...base }));
    else out.push(new TextRun({ text: s.slice(1, -1), font: "Consolas", size: (base.size || 19) - 1, color: "8A2B06" }));
    last = m.index + s.length;
  }
  if (last < t.length) out.push(new TextRun({ text: t.slice(last), ...base }));
  return out;
}
const P = (t, o = {}) => new Paragraph({ children: runs(t, o.run || {}), spacing: { after: 90, line: 264 }, alignment: o.align || AlignmentType.JUSTIFIED, ...o.p });
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)], spacing: { before: 200, after: 100 } });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)], spacing: { before: 160, after: 70 } });
const H3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)], spacing: { before: 110, after: 50 } });
const BUL = (t) => new Paragraph({ children: runs(t), numbering: { reference: "vinetas", level: 0 }, spacing: { after: 40, line: 252 } });
const SALTO = () => new Paragraph({ children: [new PageBreak()] });
let nFig = 0;
const figuras = [];
function FIG(archivo, titulo, anchoCm) {
  nFig++;
  const buf = fs.readFileSync(path.join(D, archivo));
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20);
  const px = Math.round(anchoCm / 2.54 * 96);
  figuras.push(`Figura ${nFig}. ${titulo}`);
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 60, after: 20 },
      children: [new ImageRun({ type: "png", data: buf, transformation: { width: px, height: Math.round(px * h / w) },
        altText: { title: titulo, description: titulo, name: archivo } })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 },
      children: [new TextRun({ text: `Figura ${nFig}. ${titulo}`, italics: true, size: 16, color: GRIS })] }),
  ];
}
const CODE = (lineas) => lineas.map((l, i) => new Paragraph({
  shading: { type: ShadingType.CLEAR, fill: "F3F5F8", color: "auto" }, spacing: { after: i === lineas.length - 1 ? 100 : 0, line: 228 },
  children: [new TextRun({ text: l || " ", font: "Consolas", size: 15 })] }));

const borde = { style: BorderStyle.SINGLE, size: 4, color: "C9D6EA" };
const bordes = { top: borde, bottom: borde, left: borde, right: borde };
function T(cab, filas, prop, o = {}) {
  const tot = prop.reduce((a, b) => a + b, 0);
  const cols = prop.map((p) => Math.floor(ANCHO * p / tot));
  cols[cols.length - 1] = ANCHO - cols.slice(0, -1).reduce((a, b) => a + b, 0);
  const tam = o.size || 16;
  const celda = (txt, i, esCab, primera) => new TableCell({
    width: { size: cols[i], type: WidthType.DXA }, borders: bordes,
    shading: esCab ? { type: ShadingType.CLEAR, fill: AZUL, color: "auto" } : (primera && o.colorPrimera ? { type: ShadingType.CLEAR, fill: CELDA, color: "auto" } : undefined),
    margins: { top: 40, bottom: 40, left: 70, right: 70 },
    children: String(txt).split("\n").map((l) => new Paragraph({ spacing: { after: 0, line: 240 },
      children: runs(l, esCab ? { bold: true, color: "FFFFFF", size: tam } : { size: tam, bold: primera && o.negritaPrimera }) })),
  });
  return [new Table({
    width: { size: ANCHO, type: WidthType.DXA }, columnWidths: cols,
    rows: [new TableRow({ tableHeader: true, children: cab.map((c, i) => celda(c, i, true)) }),
      ...filas.map((f) => new TableRow({ cantSplit: true, children: f.map((c, i) => celda(c, i, false, i === 0)) }))],
  }), new Paragraph({ spacing: { after: 80 }, children: [] })];
}
// Ficha ADR: tabla de dos columnas
function ADR(titulo, filas) {
  return [H3(titulo), ...T(["Campo", "Contenido"], filas, [1.25, 5], { colorPrimera: true, negritaPrimera: true, size: 16 })];
}

// =====================================================================================
const portada = [
  new Paragraph({ spacing: { before: 1400, after: 40 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "DUOC UC · ESCUELA DE INFORMÁTICA Y TELECOMUNICACIONES", bold: true, color: AZUL_OSC, size: 18 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 700 }, children: [new TextRun({ text: "ITY1102 · Arquitectura de Sistemas de Inteligencia Artificial", color: GRIS, size: 20 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Documentación de arquitectura", bold: true, color: AZUL, size: 52 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 }, children: [new TextRun({ text: "arc42 · Evaluación Parcial 2 · primera versión corriendo en contenedores", color: GRIS, size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 500 }, children: [new TextRun({ text: "Guardián Centinela", bold: true, size: 40, color: "333333" })] }),
  ...T(["Campo", "Valor"], [
    ["Caso asignado", "Caso 3 — Detección de fraude en pagos digitales · Kipu Pagos SpA"],
    ["Equipo N°", "04"], ["Sección", "001D · 2026-02"], ["Docente", "Cristian Calderón"],
    ["Entrega", "Evaluación Parcial 2 — domingo 18 de octubre de 2026, 23:59"],
    ["Versión del documento", "2.0 (EP1 1.0 corregida y extendida)"],
  ], [1.3, 3], { colorPrimera: true, negritaPrimera: true, size: 18 }),
  new Paragraph({ spacing: { before: 200, after: 60 }, children: [new TextRun({ text: "Integrantes", bold: true, color: AZUL_OSC, size: 20 })] }),
  ...T(["Nombre completo", "Correo institucional", "De qué se hizo cargo en EP2"], [
    ["Sergio Martínez", "ser.martinezs@duocuc.cl", "Tratamiento de datos (datos/preparar.py), front; capítulos 1, 2, 3 y 8.4"],
    ["Roberto Castro", "ro.castroc@duocuc.cl", "Microservicio de dominio, gateway y compose.yaml; capítulos 4, 5, 6, 7.1 y 7.2"],
    ["Oscar Larrieu", "os.larrieu@duocuc.cl", "Microservicio de IA, carga y pipeline CI; capítulos 7.3, 7.4, 8.1–8.3, 9 y 10"],
  ], [1.3, 1.6, 3], { size: 17 }),
  SALTO(),
];

// Índice estático con páginas calculadas en una segunda pasada (paginas.json)
const ENTRADAS = [
  ["Historial de versiones", 0], ["1. Introducción y objetivos", 0], ["2. Restricciones", 0], ["3. Alcance y contexto del sistema", 0],
  ["4. Estrategia de solución", 0], ["5. Vista de bloques de construcción", 0], ["5.2 Nivel 2 — contenedores", 1], ["5.3 Nivel 3 — componentes del microservicio de IA", 1],
  ["6. Vista de ejecución", 0], ["7. Vista de implementación", 0], ["7.1 Despliegue actual y objetivo", 1], ["7.2 Dimensionamiento de recursos", 1],
  ["7.3 Estimación de costos", 1], ["7.4 Pipeline y gitflow", 1], ["8. Conceptos transversales", 0], ["8.1 Observabilidad", 1], ["8.2 Confiabilidad y alta disponibilidad", 1],
  ["8.3 Seguridad y datos personales", 1], ["8.4 Datos: tratamiento, variables y modelo de datos", 1], ["9. Decisiones de arquitectura", 0], ["10. Requisitos de calidad", 0],
  ["Anexo A. Referencias", 0], ["Anexo B. Declaración de uso de IA generativa", 0], ["Anexo C. Repositorios y sistema", 0],
];
const indice = [
  new Paragraph({ children: [new TextRun({ text: "Índice", bold: true, color: AZUL, size: 32 })], spacing: { after: 160 } }),
  ...ENTRADAS.map(([t, nivel]) => new Paragraph({
    tabStops: [{ type: TabStopType.RIGHT, position: ANCHO, leader: "dot" }], indent: { left: nivel * 400 }, spacing: { after: 50 },
    children: [new TextRun({ text: t, bold: nivel === 0, size: 19 }), new TextRun({ text: `\t${PAGINAS[t] || ""}`, size: 19 })] })),
  new Paragraph({ spacing: { before: 200 }, children: [new TextRun({ text: "Historial de versiones", bold: true, color: AZUL_OSC, size: 24 })] }),
  ...T(["Fecha", "Versión", "Autor", "Qué cambió y por qué"], [
    ["10-09-2026", "1.0", "Equipo 04", "Entrega EP1: capítulos 1–5 (nivel 1), 7, 8.1–8.3, 9 y 10."],
    ["18-10-2026", "2.0", "Equipo 04", "EP2. Correcciones a partir de la retroalimentación de EP1: (1) los códigos RF/RNF/RT ahora son los del caso (en EP1 se renumeraron y RF-4/RF-5 no coincidían con RF7/RF10); (2) el contexto suma vecinos que faltaban: motor de reglas legado (reserva, RNF3), Redshift, SIEM y la gerencia de riesgo como dueña de los umbrales; (3) en 5.1 el registro de auditoría lo escribe el dominio, no el servicio de inferencia; (4) se borró la orientación en cursiva; (5) el costo de 7.3 se recalculó desde mediciones y no desde supuestos; (6) se agrega el capítulo 6 que faltaba. Extensión EP2: 5.2, 5.3, 6, 7.1 actual/objetivo, 7.2 medido, 7.4 pipeline, 8.1–8.3 extendidos, 8.4 nuevo, ADR-4 a ADR-7 y anexo C."],
  ], [1.1, 0.7, 1, 6], { size: 16 }),
  SALTO(),
];

// =====================================================================================
const c1 = [
  H1("1. Introducción y objetivos"),
  P("**Guardián Centinela** es el sistema de detección de fraude en línea, explicable y auditable de **Kipu Pagos SpA**. Evalúa cada transacción antes de autorizarla y devuelve **aprobar, revisar o bloquear** junto con las razones ordenadas por peso. Su objetivo de negocio es bajar los falsos positivos sobre bloqueos de 40% a menos de 15% sin aumentar el fraude no detectado (hoy USD 500.000/año), porque los falsos positivos cuestan USD 1,16 millones al año, más del doble que el fraude. Este documento describe la arquitectura objetivo (AWS) y la **primera versión construida en EP2**, que corre completa en contenedores con `docker compose`."),
  H2("1.1 Descripción general de los requisitos"),
  ...T(["Código", "Requerimiento funcional (caso)", "Por qué condiciona la arquitectura", "Dónde se ve en EP2"], [
    ["RF1", "Evaluar cada transacción antes de autorizarla: aprobar, revisar o bloquear", "Ruta síncrona con presupuesto de 100 ms (RNF1) dentro de los 150 ms del core (RT3)", "`POST /api/dominio/evaluar`"],
    ["RF2", "Devolver las razones ordenadas por peso", "Obliga a modelos explicables por factores (RT8): árboles + TreeSHAP", "`razones` en `/predict`"],
    ["RF3 / RO5", "Riesgo ajusta umbrales sin desplegar código", "Umbrales como datos versionados, no como constantes", "Tabla `umbrales` (solo INSERT)"],
    ["RF4 / RF8", "Reglas normativas y listas negras mandan sobre el modelo", "Capa de reglas antes del modelo, en el dominio", "`reglas_duras()` del dominio"],
    ["RF7", "Reproducir la decisión de cualquier transacción", "Registro inmutable de entrada, versión de modelo y de umbral", "Tabla `predicciones`, `GET /predicciones/{id}`"],
    ["RF10", "Detectar velocidad (mismo usuario/dispositivo en poco tiempo)", "Historia reciente consultable en milisegundos (Redshift carga de noche, RT7)", "Ventanas 10 min/24 h/1 h"],
    ["RF11", "No publicar un modelo que empeora", "Compuerta de métrica en el pipeline", "Job `ia-modelo` (PR-AUC ≥ 0,70)"],
  ], [0.8, 2.6, 2.8, 1.9]),
  H2("1.2 Objetivos de calidad"),
  ...T(["Prioridad", "Atributo (ISO 25010)", "Meta medible", "Qué se sacrifica por sostenerla"], [
    ["1", "Eficiencia · tiempo de respuesta (RNF1)", "p99 < 100 ms desde que el core envía la transacción, a 5.500 tx/min (RNF4)", "El bureau (900 ms, RT5) y los ensambles pesados quedan fuera de la ruta síncrona"],
    ["2", "Adecuación funcional · exactitud (RNF8)", "Falsos positivos < 15% de los bloqueos; fraude no detectado < USD 350.000/año", "Un margen de riesgo en montos bajos para no bloquear clientes buenos"],
    ["3", "Mantenibilidad · analizabilidad y trazabilidad (RNF6, RNF7)", "Razones en < 5 s para el analista; auditor reproduce una decisión en < 1 h", "Se descartan redes profundas: algo de precisión a cambio de explicación"],
  ], [0.7, 1.8, 2.6, 2.6]),
  H2("1.3 Interesados (stakeholders)"),
  ...T(["Rol o nombre", "Qué espera del sistema", "Qué decisión de arquitectura le afecta"], [
    ["Ignacia Bravo · Gerenta de riesgo", "Menos falsos positivos sin más fraude, explicable ante la CMF", "Modelo explicable (ADR-1) y umbrales versionados que solo ella autoriza (RO5)"],
    ["Matías Ortega · Jefe de ingeniería", "Que no suba la latencia del core ni lo frene una caída", "Llamada síncrona corta (ADR-2), réplicas con balanceo (ADR-5) y política de reserva (ADR-3)"],
    ["Felipe Navarrete · Analista senior", "Mejores herramientas sin quedar fuera", "Cola priorizada por riesgo y razones visibles en el front en < 5 s"],
    ["Carolina Herrera · Cumplimiento", "Trazabilidad total y reportes a la UAF", "Registro de predicciones con versión de modelo y umbral; S3 Object Lock en producción"],
    ["Auditor externo / CMF", "Reproducir cualquier decisión pasada", "`GET /predicciones/{transaccion_id}` une decisión, entrada y umbral vigente"],
  ], [1.7, 2.2, 3.4]),
];

const c2 = [
  H1("2. Restricciones"),
  ...T(["Código", "Tipo", "Restricción (caso)", "Qué le impide a la arquitectura"], [
    ["RT1", "Técnica", "AWS con cuenta segregada PCI y otra para el resto", "Otra nube; el sistema vive en la cuenta no-PCI y recibe solo tokens"],
    ["RT2", "Técnica", "USD 6.000/mes de infraestructura", "Clústeres dedicados multirregión; obliga a medir antes de dimensionar (7.2–7.3)"],
    ["RT3", "Técnica", "El core llama de forma síncrona con 150 ms totales", "Colas en la ruta de decisión; consultas externas lentas en línea"],
    ["RT4 / RNF5", "Técnica", "PCI-DSS 4.0: el PAN no sale del entorno segregado", "Recibir o guardar el número de tarjeta: el dominio rechaza cualquier PAN (422)"],
    ["RT5", "Técnica", "Bureau: USD 0,08 y 900 ms por consulta", "Consultarlo en línea para todas las transacciones (USD 16.000/día, R9)"],
    ["RT7", "Técnica", "Redshift carga una vez al día", "Calcular velocidad desde el data warehouse"],
    ["RT8", "Técnica", "Toda decisión explicable a un auditor no técnico", "Modelos de caja negra"],
    ["RO2", "Organizacional", "Analistas de 08:00 a 22:00, sin turno de madrugada", "Depender de revisión humana nocturna (49% del fraude ocurre 00–06)"],
    ["RO3 / RO6", "Organizacional", "8 semanas en modo sombra; el motor actual no se apaga", "Decidir en activo desde el día 1; por eso `modo` es configuración (RNF11)"],
    ["RN7", "Normativa", "Retención de decisiones por 7 años (CMF)", "Guardar la auditoría solo en bases operativas: exige almacenamiento WORM"],
  ], [0.9, 1.1, 2.8, 3.4]),
];

const c3 = [
  H1("3. Alcance y contexto del sistema"),
  H2("3.1 Contexto empresarial"),
  P("La figura 1 corrige la de EP1 según la retroalimentación: agrega el **motor de reglas legado** (al que cae el core si el sistema no responde, RNF3), **Redshift** como fuente del historial etiquetado, el **SIEM** y a **riesgo** como dueña de los umbrales. El alcance es la decisión sobre la transacción; no se construye la herramienta de analistas, se integra con ella."),
  ...FIG("01-contexto.png", "Diagrama de contexto (C4 nivel 1), actualizado desde EP1.", 15.5),
  ...T(["Vecino", "Qué intercambia con el sistema", "Dirección"], [
    ["Core de pagos", "Envía la transacción tokenizada; recibe decisión y razones", "Bidireccional"],
    ["Motor de reglas legado", "Decide si Guardián Centinela no responde en 100 ms (política de reserva)", "Alternativa del core"],
    ["Gerencia de riesgo", "Publica umbrales, modo (sombra/activo) y política de reserva", "Entrada"],
    ["Analistas de fraude", "Reciben casos priorizados; devuelven la etiqueta confirmada (RF5, RF6)", "Bidireccional"],
    ["Listas de sanciones / listas negras", "Archivo diario y entradas vetadas (RF8)", "Entrada"],
    ["Redshift", "Historial etiquetado para entrenar (no sirve en línea, RT7)", "Entrada"],
    ["Bureau de identidad", "Solo casos dudosos, fuera de la ruta síncrona (RT5)", "Salida/consulta"],
    ["Auditor / CMF · SIEM", "Registro de decisiones 7 años · logs de seguridad", "Salida"],
  ], [1.8, 4.2, 1.3]),
  H2("3.2 Contexto técnico"),
  ...FIG("02-contexto-tecnico.png", "Contexto técnico: canales, protocolos y formatos.", 15),
  ...T(["Canal", "Protocolo y formato", "Restricción que aplica"], [
    ["Evaluación (core → sistema)", "HTTPS/REST JSON, token de tarjeta `****NNNN`", "RT3 150 ms · RNF1 p99 < 100 ms · RT4"],
    ["Umbrales (riesgo → sistema)", "HTTPS `POST /umbrales` con `X-Api-Key` del rol riesgo", "RF3 · RNF10 · RO5"],
    ["Cola de revisión (sistema ↔ consola)", "HTTPS/REST JSON", "RNF6 razones en < 5 s · RO2"],
    ["Bureau", "HTTPS/REST JSON, asíncrono", "RT5 900 ms · USD 0,08"],
    ["Sanciones / listas negras", "SFTP CSV diario · SQL", "RT6"],
    ["Auditoría", "S3 API con Object Lock (producción)", "RN7 · RT8"],
  ], [2.2, 3, 2.2]),
];

const c4 = [
  H1("4. Estrategia de solución"),
  P("La solución es **híbrida por capas** (ADR-1): primero reglas duras y listas negras, que siempre mandan (RF4); después un modelo **XGBoost** que estima la probabilidad de fraude y entrega sus factores con **TreeSHAP** (RF2, RT8); al final, umbrales versionados que fija riesgo (RF3). La ruta de decisión es **síncrona y corta** (ADR-2) y, si el modelo no responde a tiempo, el dominio aplica la **política de reserva** que elige riesgo (ADR-3). En EP2 todo corre en contenedores; en producción, en **ECS Fargate en dos zonas de disponibilidad** (ADR-6)."),
  ...T(["Objetivo de calidad (1.2)", "Decisión que lo sostiene", "Dónde se ve"], [
    ["1. p99 < 100 ms", "Llamada síncrona dominio → IA, modelo de árboles de 3 niveles (inferencia ≈ 5 ms), velocidad por consultas indexadas (Redis en producción)", "Cap. 6, 7.2 · ADR-2"],
    ["2. Falsos positivos < 15%", "Reglas duras + modelo con umbrales ajustables por riesgo; modo sombra para calibrar sobre tráfico real", "8.4 · ADR-1, ADR-3"],
    ["3. Explicación < 5 s / auditoría < 1 h", "Razones TreeSHAP en cada respuesta y registro de cada decisión con versiones", "5.3, 8.4 · ADR-1"],
  ], [1.8, 4, 1.4]),
  H2("4.1 Patrones arquitectónicos aplicados"),
  ...T(["Patrón", "Requerimiento del caso que lo justifica", "Cómo se ve en el sistema entregado", "Ficha"], [
    ["API Gateway", "Un único punto de entrada controlado para el core y la consola (RT3, seguridad 8.3)", "nginx publica solo `:8080`; enruta `/`, `/api/dominio/` y `/api/ia/`; tope de tasa y errores JSON", "ADR-4"],
    ["Microservicios (dominio / IA)", "El modelo cambia cada reentreno (RF11, RNF9) y las reglas no; deben escalar y publicarse por separado", "Dos imágenes con su pipeline; la IA no toca la base, recibe todo en la petición", "ADR-7"],
    ["Réplicas con balanceo y health check", "Disponibilidad 99,9% (RNF2) y tolerancia a fallos (RNF3)", "`ia` con `replicas: 2`, round-robin y reintento en la otra réplica; healthcheck en cada servicio", "ADR-5"],
    ["Event-Driven (candidato, producción)", "Auditoría y features no deben competir por los 100 ms (ADR-2)", "No implementado en EP2: la escritura es síncrona en PostgreSQL; en producción, lote a S3 cada minuto", "ADR-2"],
  ], [1.4, 2.3, 3, 0.7]),
];

const c5 = [
  H1("5. Vista de bloques de construcción"),
  H2("5.1 Nivel 1 — el sistema y su correspondencia con EP2"),
  P("El nivel 1 (figura 1) muestra el sistema como una caja dentro de su entorno. La tabla traza cada bloque diseñado en EP1 a la pieza que existe hoy; donde difiere, se explica por qué."),
  ...T(["Bloque EP1", "Responsabilidad", "Pieza en EP2 (compose)", "Diferencia y razón"], [
    ["API de Evaluación / Reglas", "Valida, aplica reglas duras y umbrales, orquesta", "`dominio` (FastAPI)", "Igual. Corrección EP1: también escribe el registro de auditoría"],
    ["Servicio de Inferencia ML", "Probabilidad + explicación", "`ia` ×2 (FastAPI + XGBoost)", "Igual; ahora con 2 réplicas balanceadas"],
    ["Feature Store (Redis)", "Velocidad en milisegundos (RF10)", "Consultas indexadas en `db`", "En EP2 basta SQL (≈ 6 ms); Redis queda para producción (7.1)"],
    ["Registro auditable (S3 WORM)", "Decisiones inmutables 7 años", "Tabla `predicciones` en `db`", "S3 Object Lock no existe en local; se exporta en producción"],
    ["Consola web del analista", "Muestra decisiones y razones", "`front` + `gateway`", "Página propia mínima; la consola real se integra (fuera de alcance)"],
    ["—", "Llenar la base con datos tratados", "`carga` (una vez)", "Nuevo en EP2 (sección 8.4)"],
  ], [1.6, 2, 1.7, 2.6]),
  H2("5.2 Nivel 2 — contenedores"),
  P("La figura 3 tiene exactamente los mismos servicios que `compose.yaml`: gateway, front, dominio, ia (2 réplicas), carga y db. Cada flecha indica protocolo y ruta. El dominio consume la IA **a través del gateway**, de modo que el balanceo entre réplicas es el mismo para cualquier cliente."),
  ...FIG("03-contenedores.png", "Contenedores (C4 nivel 2): servicios del compose.yaml y cómo se comunican.", 16),
  ...T(["Contenedor", "Responsabilidad", "Tecnología / imagen", "Expone", "Depende de"], [
    ["gateway", "Única puerta de entrada; enruta y balancea; tope de tasa", "nginx 1.28 · `gc-gateway:ep2`", "`:8080` (publicado)", "front, dominio, ia (healthy)"],
    ["front", "Formulario de evaluación, resultado con razones, últimas decisiones", "nginx 1.28 + HTML/JS · `gc-front:ep2`", "`:80` interno", "—"],
    ["dominio", "Reglas duras, velocidad, umbrales, reserva; único que lee/escribe la base", "Python 3.12, FastAPI, psycopg · `gc-dominio:ep2`", "`:8000` interno, `/health`, `/metrics`", "db (healthy), carga (completed)"],
    ["ia (×2)", "Inferencia + explicación; no accede a la base", "Python 3.12, FastAPI, XGBoost · `gc-ia:ep2`", "`:8000` interno, `/predict`, `/health`", "—"],
    ["carga", "Crea el esquema y carga las tablas tratadas sin duplicar", "Python 3.12, psycopg · `gc-carga:ep2`", "— (termina)", "db (healthy)"],
    ["db", "Usuarios, dispositivos, lista negra, transacciones, umbrales, predicciones", "`postgres:16-alpine` + volumen `datos-pg`", "`:5432` interno", "—"],
  ], [0.9, 2.3, 2, 1.5, 1.4]),
  H2("5.3 Nivel 3 — componentes del microservicio de IA"),
  ...FIG("04-componentes-ia.png", "Componentes (C4 nivel 3) del microservicio de IA.", 15.5),
  ...T(["Componente", "Responsabilidad", "Archivo"], [
    ["0 · Cargador del modelo", "Lee `modelo.json` y `metadata.json` (versión, métricas, variables) al arrancar; `/health` responde 503 si no cargó", "`app/main.py · cargar_modelo()`"],
    ["1 · Validador de entrada", "Contrato Pydantic: tipos y rangos (monto > 0, hora 0–23, canal en lista, MCC de 4 dígitos); 422 si no cumple", "`EntradaPrediccion`"],
    ["2 · Vectorizador", "Convierte el JSON en 44 variables; es el mismo código que usa el entrenamiento (evita diferencias entre entrenar y servir)", "`app/features.py`"],
    ["3 · Inferencia", "XGBoost calcula el margen; la probabilidad es su sigmoide", "`Booster.predict`"],
    ["4 · Explicador", "Aportes TreeSHAP de cada variable en la misma pasada; se devuelven los 5 de mayor peso con signo (RF2)", "`pred_contribs=True`"],
    ["5 · Respuesta", "Probabilidad, razones, versión del modelo, réplica y latencia; métricas Prometheus", "`SalidaPrediccion`"],
  ], [1.4, 4.4, 1.7]),
  P("**Contrato de** `POST /predict` (resumen): entrada `{transaccion_id, monto_usd, hora_local, canal, mcc, pais_transaccion, intentos_previos_1h, tx_usuario_10min, tx_usuario_24h, tx_dispositivo_1h, ip_valida, en_lista_negra, u_* (usuario), d_* (dispositivo)}`; salida `{probabilidad_fraude, razones:[{variable, aporte, valor}], version_modelo, replica, latencia_ms}`."),
];

const c6 = [
  H1("6. Vista de ejecución"),
  P("La figura 5 recorre el flujo principal desde el front hasta el modelo y de vuelta, con los dos caminos de falla. Las cifras son de la medición de 7.2."),
  ...FIG("05-secuencia.png", "Secuencia del flujo principal, con réplica caída y modelo que no responde.", 17),
  BUL("**Camino normal.** El dominio lee umbrales vigentes, usuario, dispositivo, lista negra y velocidad (≈ 6–8 ms), llama a `/api/ia/predict` (≈ 5 ms, inferencia interna media 5,2 ms) y registra la decisión (≈ 2 ms). Una petición aislada tarda 12–17 ms; bajo 133 req/s el p99 fue 80 ms."),
  BUL("**Se cae una réplica de IA.** nginx recibe conexión rechazada (502), marca la réplica caída por 10 s (`max_fails=1`) y reintenta la misma petición en la otra (`proxy_next_upstream`, `/predict` no escribe nada, por eso es seguro). En la prueba (1.500 peticiones, réplica detenida a los 3 s) hubo **0 errores**: 1 petición reintentada (502 → 200) y el resto atendida por la réplica viva."),
  BUL("**El modelo tarda más de 300 ms o las dos réplicas caen.** El gateway responde `503 servicio_no_disponible`; el dominio aplica la **política de reserva** de la versión de umbrales vigente (`reglas` por defecto: lista negra → bloquear; monto > USD 150, 3+ intentos o país extranjero → revisar; si no, aprobar). La decisión se registra con `origen = reserva` y el front muestra el aviso. Las reglas duras siempre mandan."),
];

const c7 = [
  H1("7. Vista de implementación"),
  H2("7.1 Despliegue actual y objetivo"),
  P("**Actual (figura 6).** Un solo `compose.yaml` levanta todo con `docker compose -p equipo04 pull` y `up -d`. Solo descarga imágenes `:ep2` públicas de GHCR (linux/amd64), sin `build`, sin bind mounts; la base persiste en el volumen con nombre `datos-pg`; solo el gateway publica el puerto 8080; cada servicio propio tiene healthcheck y `cpus`/`mem_limit` (7.2)."),
  ...FIG("06-despliegue-actual.png", "Despliegue actual: compose en un computador, red interna y un único puerto publicado.", 15),
  P("**Objetivo (figura 7).** AWS us-east-1, cuenta no-PCI (RT1). ALB con WAF delante de servicios ECS Fargate repartidos en **dos zonas de disponibilidad**; el dominio llama a la IA por **ECS Service Connect** (balanceo y reintento, el papel que hoy cumple nginx); RDS PostgreSQL Multi-AZ, ElastiCache Redis como feature store y S3 Object Lock para la auditoría de 7 años. En EP3 la IA pasa a un endpoint de SageMaker."),
  ...FIG("07-despliegue-objetivo.png", "Despliegue objetivo en AWS: orquestador, réplicas, ALB y zonas de disponibilidad.", 17),
  ...T(["Balanceo", "Hoy (gateway nginx)", "Objetivo (ALB + Service Connect)"], [
    ["Algoritmo", "Round-robin entre las IP de `ia` que entrega el DNS de Docker (`resolve`, re-resuelve cada 5 s)", "ALB round-robin / least outstanding requests; Service Connect (Envoy) round-robin"],
    ["Health check", "Pasivo: 1 fallo saca la réplica 10 s; activo en Docker: `/health` cada 10 s, 3 reintentos", "ALB: `GET /health` cada 10 s, 2 fallos = no sano; ECS reemplaza la tarea"],
    ["Reintento", "`proxy_next_upstream error timeout 502 503`, 2 intentos", "Service Connect: reintento en otra tarea; timeout 300 ms"],
  ], [1.1, 3.2, 3.2]),
  ...T(["Servicio", "Imagen base", "Por qué esa y no otra"], [
    ["gateway, front", "`nginx:1.28-alpine`", "≈ 20 MB; 1.28 es la primera estable con `resolve` en upstream sin NGINX Plus (necesario para re-descubrir réplicas)"],
    ["dominio, carga", "`python:3.12-slim`", "glibc: `psycopg[binary]` trae libpq precompilada; en alpine habría que compilar"],
    ["ia", "`python:3.12-slim` + `xgboost-cpu`", "Ruedas manylinux listas; `xgboost-cpu` pesa 4,5 MB contra 150 MB del paquete con CUDA. Sin PyTorch"],
    ["db", "`postgres:16-alpine` (oficial)", "Imagen oficial liviana, mismo motor que RDS PostgreSQL del objetivo"],
  ], [1.2, 1.8, 4.5]),
  P("Todas las imágenes propias corren con un usuario sin privilegios (`uid 10001`) salvo las de nginx. El total estimado de imágenes es < 1,1 GB (bajo el límite de 2 GB), verificable con `docker image ls`."),
  H2("7.2 Dimensionamiento de recursos"),
  P("**Cómo se midió.** Con el sistema levantado, `herramientas/generar_carga.py` envía evaluaciones concurrentes por el gateway mientras se lee `docker stats` (MEM USAGE y CPU %). Además se midió el **tiempo de CPU por petición** de cada servicio (utime + stime de `/proc` antes y después de 2.000 peticiones). Entorno: 2 vCPU, todos los servicios en el mismo equipo."),
  ...T(["Servicio", "Memoria pico medida", "CPU por petición", "Límite compose", "Por qué ese límite", "Proyección AWS (producción)"], [
    ["ia (c/u)", "176 MB", "3,1 ms", "`cpus 0.5` · `mem_limit 256m`", "1,45× el pico; 0,5 CPU atiende ≈ 160 req/s por réplica", "Fargate 0,5 vCPU/1 GB × 2 (1 por AZ)"],
    ["dominio", "71 MB", "4,5 ms", "`cpus 1.0` · `160m`", "2,2× el pico (pool de 8 conexiones); 1 CPU ≈ 220 req/s", "Fargate 0,5 vCPU/1 GB × 2, autoescala a 4"],
    ["db", "≈ 40 MB/proceso (14 procesos, memoria compartida)", "2,9 ms", "`cpus 1.0` · `256m`", "shared_buffers 128 MB + conexiones", "RDS db.t4g.medium Multi-AZ, 200 GB gp3"],
    ["gateway", "< 10 MB", "< 0,5 ms", "`0.5` · `64m`", "nginx: memoria casi constante", "Reemplazado por ALB"],
    ["front", "< 5 MB", "≈ 0", "`0.25` · `32m`", "Solo archivos estáticos", "Fargate 0,25 vCPU/0,5 GB × 2"],
    ["carga", "≈ 40 MB (una vez)", "—", "`0.5` · `128m`", "Copia por bloques de 64 KB, no carga todo en memoria", "Tarea ECS programada"],
  ], [0.8, 1.3, 0.8, 1.4, 2.1, 1.8], { size: 15 }),
  P("**Proyección al volumen del caso.** RNF4 pide 1.000.000 tx/día con peak de 5.500/min = **92 req/s**. CPU necesaria en el peak: dominio 92 × 4,5 ms = **0,42 vCPU**, IA 92 × 3,1 ms = **0,28 vCPU**, base 92 × 2,9 ms = **0,27 vCPU**. Con dos tareas de 0,5 vCPU por servicio (una por zona), si cae una zona la otra queda al 84% (dominio) y al 57% (IA): sobrevive sin rediseño y el autoescalado agrega tareas al 60% de CPU. En la medición local el sistema sostuvo **133 req/s (8.003/min)**, 1,45 veces el peak, con p99 de 80 ms por el gateway. **Almacenamiento:** cada predicción ocupa 1,8 KB → 1,8 GB/día; se mantienen 90 días en RDS (≈ 160 GB) y el resto se exporta a S3. **GPU:** no se usa; XGBoost de 200 árboles de profundidad 3 infiere en ≈ 5 ms en CPU. **Red:** ≈ 2 KB por decisión → 2 GB/día dentro de la VPC."),
  P("Si el `mem_limit` fuera menor que el consumo (p. ej. 128m para la IA), el kernel mata el proceso (OOMKilled, código 137), Docker lo reinicia por `restart: unless-stopped` y, mientras tanto, el gateway envía todo a la otra réplica."),
  H2("7.3 Estimación de costos mensuales (despliegue objetivo, 1.000.000 tx/día)"),
  ...T(["Servicio AWS (us-east-1)", "Supuesto (de 7.2)", "USD/mes", "De dónde sale"], [
    ["ECS Fargate · dominio", "2 tareas × 0,5 vCPU / 1 GB, 730 h", "36", "0,04048 USD/vCPU-h + 0,004445 USD/GB-h"],
    ["ECS Fargate · IA", "2 tareas × 0,5 vCPU / 1 GB", "36", "Ídem"],
    ["ECS Fargate · front", "2 tareas × 0,25 vCPU / 0,5 GB", "18", "Ídem"],
    ["Autoescalado en peak", "+2 tareas dominio/IA, 4 h/día", "24", "Ídem, 120 h/mes"],
    ["Application Load Balancer", "1 ALB + ≈ 2 LCU", "28", "0,0225 USD/h + 0,008 USD/LCU-h"],
    ["AWS WAF", "1 ACL, 5 reglas, 30 M req", "28", "5 + 5 × 1 + 0,60 USD/M req"],
    ["RDS PostgreSQL Multi-AZ", "db.t4g.medium + 200 GB gp3", "141", "0,130 USD/h Multi-AZ + 0,23 USD/GB-mes"],
    ["ElastiCache Redis", "2 × cache.t4g.small (primario + réplica)", "47", "0,032 USD/h por nodo"],
    ["NAT Gateway", "2 (uno por AZ) + 50 GB", "68", "0,045 USD/h + 0,045 USD/GB"],
    ["S3 Object Lock", "≈ 11 GB/mes comprimidos, acumulado año 1", "4", "0,023 USD/GB-mes + PUT por lote/min"],
    ["Observabilidad", "CloudWatch logs 9 GB + Managed Prometheus + Grafana 2 editores", "50", "0,50 USD/GB; 0,90 USD/10 M muestras; 9 USD/editor"],
    ["Otros", "Secrets Manager, ECR, transferencia", "7", "0,40 USD/secreto; 0,10 USD/GB"],
    ["**Total**", "**≈ 30 M decisiones/mes**", "**≈ 487**", "**8% del tope de USD 6.000 (RT2) · ≈ USD 16 por millón de decisiones (RNF12)**"],
  ], [1.9, 2.4, 0.7, 2.7]),
  P("Precios de lista on-demand us-east-1 (AWS Pricing Calculator, octubre 2026). Respecto de EP1 (USD 700) baja porque ahora el tamaño de cada tarea sale de la medición y no de un supuesto de 2 vCPU/4 GB. No incluye el bureau: consultarlo solo en los casos «revisar» (≈ 2,4% del tráfico) cuesta ≈ 4.800 × 0,08 = USD 384/día, que es costo operativo y no de infraestructura."),
  H2("7.4 Pipeline y gitflow"),
  ...FIG("08-pipeline.png", "Pipeline: de una rama feat/ a la imagen :ep2 en GHCR.", 15),
  ...T(["Evento", "Qué hace el workflow `ci.yml`"], [
    ["PR hacia `dev` o `main`", "Corre `datos` (preparar.py + pruebas de nulos/duplicados), `ia-modelo` (entrena y aplica la compuerta), `dominio-carga` (PostgreSQL de servicio: carga dos veces sin duplicar y prueba `/evaluar`, incluida la caída de la IA) y `gateway-front` (`nginx -t`). Construye las 5 imágenes **sin publicar**. Si algo falla, el PR no se integra."],
    ["Push a `main` (merge desde dev)", "Lo mismo y además publica en GHCR con `sha-<commit>` y `latest`. `docker/metadata-action` agrega `org.opencontainers.image.revision`."],
    ["Tag `ep2` sobre `main`", "Publica las mismas imágenes con el tag `ep2`, que es el que usa `compose.yaml`."],
  ], [1.6, 6]),
  P("**Gitflow.** `main` protegida (solo por PR desde `dev`), `dev` de integración y ramas `feat/<descripción>` de corta vida, por ejemplo `feat/datos-tratamiento`, `feat/ia-modelo-v1`, `feat/dominio-reglas-umbrales`, `feat/gateway-balanceo`, `feat/front-formulario` y `feat/pipeline-ci`. Cada integrante integró al menos dos PR `feat/` con su propio usuario (anexo C). El modelo nunca se sube al repositorio: lo producen `preparar.py` y `entrenar.py` dentro del pipeline."),
];

const c8 = [
  H1("8. Conceptos transversales"),
  H2("8.1 Observabilidad"),
  P("**Implementado en EP2:** `/metrics` en formato Prometheus en dominio (`gc_dominio_latencia_segundos`, `gc_dominio_decisiones_total{decision,origen}`, `gc_dominio_fallas_ia_total`) e IA (`gc_ia_latencia_segundos`, `gc_ia_predicciones_total`); log del gateway con réplica que atendió, estado y tiempo (`upstream=… rt=…`); `X-Request-Id` de punta a punta; `GET /resumen` con p50/p99 de la última hora. **Producción (referencia L8):** Prometheus raspa `/metrics` cada 15 s, Grafana muestra los tableros y Alertmanager notifica."),
  ...T(["Métrica", "Fuente", "Umbral", "Acción cuando se cruza"], [
    ["Latencia p99 de `/evaluar`", "`gc_dominio_latencia_segundos` (histograma)", "> 100 ms por 5 min (RNF1)", "Alerta a plataforma; escalar dominio/IA; si > 150 ms, el core ya aplica la reserva"],
    ["Fallas de IA", "`gc_dominio_fallas_ia_total` / decisiones", "> 1% en 5 min", "Alerta a ingeniería; revisar réplicas (`/health`) y último despliegue; rollback < 5 min (RNF9)"],
    ["Tasa de bloqueo", "`gc_dominio_decisiones_total{decision=\"bloquear\"}`", "±20% del rango histórico de la hora (RF12)", "Alerta a riesgo; congelar cambios de umbral hasta revisión (evita repetir R7)"],
    ["Decisiones por reserva", "`decisiones_total{origen=\"reserva\"}`", "> 0,5% en 10 min", "Alerta: el modelo no está decidiendo; revisar timeout y réplicas"],
    ["Memoria vs límite", "`docker stats` / cAdvisor", "> 80% de `mem_limit`", "Subir límite o tamaño de tarea antes de un OOMKilled"],
    ["Réplicas sanas de IA", "healthcheck / ALB target health", "< 2", "ECS reemplaza la tarea; alerta si dura > 2 min"],
    ["Falsos positivos semanales", "Job sobre etiquetas confirmadas", "> 15% de los bloqueos (RNF8)", "Alerta a Felipe Navarrete y riesgo para recalibrar umbrales"],
    ["Costo por millón de decisiones", "AWS Cost Explorer", "> USD 25 (RNF12)", "Revisar dimensionamiento"],
  ], [1.6, 2.1, 1.6, 2.5]),
  H2("8.2 Confiabilidad y alta disponibilidad"),
  P("RNF2 exige 99,9% mensual: como máximo **43,8 minutos** sin servicio al mes. El RTO y el RPO salen de los mecanismos de cada falla, no de un supuesto:"),
  ...T(["Qué falla", "Qué ve el usuario", "Cómo se recupera", "RTO", "RPO"], [
    ["Una réplica de IA (hoy y objetivo)", "Nada: 0 errores medidos", "Gateway/Service Connect reintenta en la otra; Docker la reinicia (`unless-stopped`), ECS la reemplaza", "0 s para el usuario; ≈ 60 s para volver a 2 réplicas", "0 (la IA no guarda estado)"],
    ["Toda la IA", "Decisión por reserva con aviso", "Política de reserva de riesgo (ADR-3)", "0 s (degradado)", "0"],
    ["Una zona de disponibilidad (objetivo)", "Nada en la ruta de decisión; < 2 min de reservas", "Tareas en la otra AZ; RDS Multi-AZ conmuta a la standby síncrona; ElastiCache promueve la réplica", "1–2 min (failover RDS documentado por AWS: 60–120 s)", "0 en RDS (síncrona); segundos en contadores de Redis"],
    ["Base de datos (hoy)", "Error del dominio; el core aplica reserva", "Un solo contenedor con volumen; se reinicia", "≈ 10 s", "0 (volumen persiste)"],
    ["Región completa (objetivo)", "Core en reserva", "Restaurar snapshot copiado a us-west-2 + imágenes", "4 h", "24 h (copia diaria)"],
    ["Modelo nuevo peor", "Más bloqueos", "Rollback automático por alarma de tasa de bloqueo", "< 5 min (RNF9)", "—"],
  ], [1.5, 1.3, 2.4, 1.4, 1.3], { size: 15 }),
  P("**Respaldo:** RDS con backups automáticos de 7 días y punto en el tiempo (PITR, 5 min); la auditoría queda en S3 Object Lock en modo compliance por 7 años y replicada a otra región."),
  H2("8.3 Seguridad y datos personales"),
  ...T(["Aspecto", "Implementado en esta versión (EP2)", "Pendiente para producción"], [
    ["Autenticación", "Ninguna para el front (demo local). Cambio de umbrales exige `X-Api-Key` del rol riesgo; si no se configura, el endpoint queda cerrado (403)", "Cognito/OIDC para analistas; mTLS o IAM SigV4 entre el core y el ALB por PrivateLink"],
    ["Autorización", "Umbrales: solo INSERT con autor y motivo (RNF10, RO5); la IA no tiene acceso a la base", "Roles IAM por servicio; usuario de base de solo lectura para auditoría"],
    ["Cifrado", "Tráfico solo en la red interna de Docker; nada sale del equipo", "TLS 1.2+ en ALB (ACM); RDS, ElastiCache y S3 cifrados con KMS"],
    ["Secretos", "Ninguno en el repositorio ni en las imágenes; `.env.example` con valores locales por defecto", "AWS Secrets Manager inyectado como variable de la tarea ECS"],
    ["Datos de tarjeta (RT4, RNF5)", "El dominio rechaza con 422 cualquier PAN (13–19 dígitos); solo se acepta `****NNNN`", "Tokenización en la cuenta PCI; nunca cruza"],
    ["Superficie expuesta", "Solo `:8080`; tope global de 400 req/s (429); cabeceras `nosniff`, `X-Frame-Options`; contenedores sin root", "AWS WAF, Shield Standard, escaneo de imágenes en ECR"],
    ["Datos personales (RN5)", "El modelo usa variables derivadas (antigüedad, KYC, dominio desechable), no nombre ni correo", "Minimización y retención según Ley 21.719"],
  ], [1.3, 3.3, 2.9]),
];

const c84 = [
  H2("8.4 Datos: tratamiento, variables y modelo de datos"),
  P("El tratamiento está en `datos/preparar.py`: es determinista, se versiona con el repositorio y lo ejecuta el pipeline (job `datos`). Genera las tablas que usa `carga` y el `dataset_modelo.csv` que usa `entrenar.py`, y deja el perfilado completo en `perfilado.json`."),
  H3("Perfilado antes y después"),
  ...T(["Archivo", "Filas antes", "Filas después", "Columnas antes → después", "Duplicados exactos", "Vacíos/nulos antes → después"], [
    ["usuarios", "5.038", "5.000", "10 → 11", "38", "2.100 → 2.256 (los «-1» y vacíos ahora son NULL explícito)"],
    ["dispositivos", "7.000", "7.000", "7 → 8", "0", "5.654 → 5.657"],
    ["transacciones", "28.421", "27.721", "19 → 31", "97", "94.091 → 66.991"],
    ["lista_negra", "350", "349", "7 → 8", "0 (1 clave repetida)", "236 → 94"],
  ], [1.2, 0.8, 0.9, 1.3, 1.1, 2.6]),
  P("**Transacciones descartadas: 700** = 97 duplicados del sistema + 250 montos negativos + 352 montos cero + 1 hora inexistente por cambio de horario. Todas las demás filas se corrigen o se marcan."),
  H3("Reglas de limpieza"),
  ...T(["Problema encontrado", "Filas", "Decisión", "Por qué"], [
    ["Fila idéntica con el mismo `transaccion_id` (duplicado del sistema)", "97", "Descartar", "Es una sola transacción; contarla dos veces infla la velocidad"],
    ["Mismo usuario, comercio y monto con ID nuevo en < 120 s (reintento)", "222", "Marcar `es_reintento`", "Es un evento real que vio el core; cuenta para RF10. No se borra igual que un duplicado"],
    ["Monto con `$`, punto de miles, coma decimal; moneda vacía", "28.324 / 1.162", "Corregir", "`1.662` CLP = 1662; `45,54` = 45.54; sin moneda: decimales o < 1.000 → USD (no hay CLP enteros entre 1 y 999), si no CLP; todo también en USD (950 CLP/USD)"],
    ["Monto negativo / cero", "250 / 352", "Descartar", "Reversa o devolución / no hay compra que evaluar"],
    ["Timestamps en 4 formatos (Z, −04:00, sin zona)", "16.460 sin zona", "Corregir y marcar", "Todo a UTC; sin zona = hora de Chile (`zona_inferida`). Evidencia: los reintentos escritos en ambos formatos solo quedan a 40–80 s con esa regla"],
    ["Coordenadas (0,0)", "1.242", "Marcar", "Valor por defecto del SDK, no una ubicación: NULL"],
    ["IP `-`, `n/a`, `0.0.0.0`, `999.1.1.1`, vacía", "956", "Marcar `ip_valida=0`", "Una IP ilegible es una señal (44% de fraude vs 9%)"],
    ["`es_fraude` vacío", "26.489", "Marcar NULL", "Vacío = nadie revisó; no es «legítima». No entra al entrenamiento"],
    ["País, segmento, canal, tipo de lista con sinónimos (Chile, chile , CL; device/merchant)", "1.243 / 600 / …", "Corregir", "ISO-3166 alfa-2 y categorías canónicas"],
    ["`nivel_kyc = -1`, `edad_cuenta_dias` negativa", "58 / 116", "Marcar NULL", "Fuera de rango; no se inventa un valor"],
    ["Usuario de la transacción no existe en `usuarios.csv`", "598", "Conservar y marcar", "El pago ocurrió; `usuario_conocido = 0`"],
    ["Lista negra: `vigente` vacío / valor con espacios / clave repetida", "74 / 30 / 1", "Corregir / corregir / descartar", "Vacío = nunca desactivada → vigente; sin `strip` la regla dura no encuentra el valor"],
  ], [2.6, 0.9, 1.1, 3.4], { size: 15 }),
  H3("Integración, variables y separación"),
  P("Transacciones ⟕ usuarios (`usuario_id`: 598 sin pareja, se conservan), ⟕ dispositivos (`dispositivo_id`: 2.465 sin dispositivo, típico de POS/API; 0 sin pareja; 205 dispositivos sin transacciones se cargan igual) y contra la lista negra vigente (1.915 coincidencias). **Variables del modelo (44)**: `monto_usd` (log), hora local y franja 00–06, país extranjero y distinto al del usuario, intentos previos 1 h, velocidad (`tx_usuario_10min`, `tx_usuario_24h`, `tx_dispositivo_1h`, calculadas con ventana deslizante sobre todo el historial limpio), IP válida, lista negra, KYC, verificación, antigüedad, correo desechable, usuarios por dispositivo, emulador, sistema operativo inconsistente y one-hot de canal, MCC y tipo de dispositivo. **Excluidas por fuga (R2):** `revisado_por_analista` y `motivo_bloqueo` (se llenan después de la revisión) y `resultado_autorizacion` (es la decisión del motor actual)."),
  P("**Entrenamiento.** Solo las 1.232 filas con etiqueta confirmada (138 fraudes). Separación **temporal y fija** antes de entrenar: el 75% más antiguo entrena (924 filas, 93 fraudes) y el 25% más reciente prueba (308 filas, 45 fraudes, corte 23-11-2025). Resultado en prueba: **PR-AUC 0,972** (azar = 0,146), ROC-AUC 0,995; con umbral 0,85, recall 95,6% y falsos positivos sobre bloqueos 6,5%. Variables de mayor peso: usuarios distintos por dispositivo, país distinto al del usuario, monto e intentos previos. La compuerta del pipeline exige PR-AUC ≥ 0,70. **Advertencia (R3):** la muestra etiquetada tiene 11% de fraude y la producción 0,012%; los umbrales v1 (0,50 revisar / 0,85 bloquear) son provisionales y riesgo los recalibra en las 8 semanas de modo sombra."),
  ...FIG("09-modelo-datos.png", "Modelo de datos de la base: tablas, claves y relaciones, incluida la de predicciones.", 15.5),
  P("`umbrales` es de solo inserción: la versión vigente es la mayor y cada predicción guarda la que usó (RF7). `transacciones.usuario_id` es una FK lógica porque 598 usuarios no vienen en la muestra."),
];

const c9 = [
  H1("9. Decisiones de arquitectura"),
  P("ADR-1 a ADR-3 vienen de EP1 (resumidas). ADR-4 a ADR-7 son nuevas: una por patrón aplicado y la del orquestador."),
  ...ADR("ADR-1. Arquitectura híbrida: reglas duras + modelo explicable", [
    ["Problema", "Bajar falsos positivos sin más fraude, con reglas normativas que siempre mandan (RF4) y decisiones explicables (RT8) en 100 ms."],
    ["Alternativas", "(a) Modelo único de extremo a extremo; (b) mantener el motor y usar el modelo fuera de línea; **(c) reglas duras primero y XGBoost + TreeSHAP después**."],
    ["Decisión", "(c). En EP2: lista negra en el dominio, XGBoost de 200 árboles de profundidad 3 con aportes TreeSHAP nativos."],
    ["Consecuencias", "Cumplimiento garantizado y explicación por diseño; dos lógicas de decisión que mantener y un techo de precisión menor que un ensamble sin restricciones."],
  ]),
  ...ADR("ADR-2. Llamada síncrona en la ruta de decisión; asíncrono para lo demás", [
    ["Problema", "El core espera 150 ms (RT3); auditoría y features no deben competir por ese presupuesto."],
    ["Alternativas", "(a) Cola entre dominio e IA: agrega latencia de encolado; (b) síncrono para todo; **(c) síncrono en la decisión, asíncrono para auditoría y reentreno**."],
    ["Decisión", "(c). En EP2 la escritura a PostgreSQL es síncrona (≈ 2 ms medidos); en producción el envío a S3 es un lote por minuto."],
    ["Consecuencias", "Latencia baja y predecible; dos mecanismos que instrumentar para no perder un evento de auditoría."],
  ]),
  ...ADR("ADR-3. Política de reserva configurable por riesgo", [
    ["Problema", "Qué se decide si la IA no responde a tiempo (RNF3), sin dejarlo fijo en el código."],
    ["Alternativas", "(a) Bloquear todo: repite el incidente de enero (R7); (b) aprobar todo: fraude sin filtro; **(c) caer a reglas, conmutable entre las tres**."],
    ["Decisión", "(c). Columna `politica_reserva` de la versión de umbrales vigente; por defecto `reglas`. Implementado y probado (`test_ia_caida_aplica_politica_de_reserva`)."],
    ["Consecuencias", "Riesgo decide cuánto tolerar durante una caída (DA5); una rama más que probar y auditar."],
  ]),
  ...ADR("ADR-4. API Gateway con nginx como única puerta de entrada", [
    ["Problema", "Un solo punto de entrada que enrute al front y a cada microservicio, balancee y no exponga los servicios internos."],
    ["Alternativas", "(a) Publicar el puerto de cada servicio: más superficie y sin balanceo; (b) Kong o Traefik: más funciones, pero más memoria y configuración; **(c) nginx 1.28**."],
    ["Decisión", "(c): enruta `/`, `/api/dominio/`, `/api/ia/`, re-resuelve réplicas por DNS (`resolve`), reintenta, limita tasa y devuelve errores JSON. Requerimiento: RT3 y seguridad 8.3."],
    ["Consecuencias", "< 10 MB y < 0,5 ms por petición; health check solo pasivo en la versión libre (lo complementa el healthcheck de Docker). En AWS lo reemplaza el ALB."],
  ]),
  ...ADR("ADR-5. Réplicas de IA con balanceo, reintento y health checks", [
    ["Problema", "Que la caída de una instancia del modelo no se note (RNF2 99,9%, RNF3)."],
    ["Alternativas", "(a) Una instancia con reinicio automático: ≈ 10 s de errores por caída; (b) replicar el dominio: no protege el modelo, que es lo que cambia en cada despliegue; **(c) 2 réplicas de IA balanceadas**."],
    ["Decisión", "(c): `replicas: 2`, round-robin, `max_fails=1`, `proxy_next_upstream` (seguro porque `/predict` no escribe)."],
    ["Consecuencias", "Medido: 0 errores al detener una réplica bajo carga. Duplica la memoria de la IA (2 × 176 MB). El dominio queda como punto único local; en el objetivo corre con 2 tareas."],
  ]),
  ...ADR("ADR-6. Orquestador objetivo: Amazon ECS sobre Fargate", [
    ["Problema", "Dónde correr las réplicas en producción con 3 desarrolladores (RO1) y USD 6.000/mes (RT2)."],
    ["Alternativas", "(a) EKS (Kubernetes): USD 73/mes solo el plano de control y operar nodos y versiones; (b) EC2 con Docker: parchar servidores; **(c) ECS Fargate**."],
    ["Decisión", "(c): servicios con 2+ tareas en 2 AZ, ALB, Service Connect y autoescalado; `compose.yaml` se traduce casi uno a uno a definiciones de tarea."],
    ["Consecuencias", "Sin servidores que administrar; menos portabilidad que Kubernetes y sin el ecosistema de Helm (aceptado por el tamaño del equipo)."],
  ]),
  ...ADR("ADR-7. Microservicios separados: el dominio orquesta, la IA solo infiere", [
    ["Problema", "El modelo se reentrena y publica con frecuencia (RF11, RNF9); las reglas y el registro no."],
    ["Alternativas", "(a) Monolito con el modelo dentro: un cambio de modelo redespliega todo; (b) la IA lee la base: acopla el modelo al esquema; **(c) dos servicios; la IA recibe todo en la petición**."],
    ["Decisión", "(c). Contrato JSON de `/predict` y el mismo vectorizador en entrenamiento y servicio."],
    ["Consecuencias", "La IA escala y se revierte sola, sin estado; una llamada de red más (≈ 1 ms por el gateway)."],
  ]),
];

const c10 = [
  H1("10. Requisitos de calidad"),
  ...T(["Atributo", "Escenario (estímulo → respuesta medible)", "Cómo se verifica", "Resultado EP2"], [
    ["Eficiencia (RNF1, RNF4)", "A 5.500 tx/min, el sistema responde con p99 < 100 ms", "`generar_carga.py` por el gateway, p99 real bajo carga", "133 req/s (8.003/min): p99 80 ms"],
    ["Fiabilidad (RNF2, RNF3)", "Se detiene una réplica de IA bajo carga → el usuario no ve errores", "`docker stop` de una réplica con carga en curso", "0 errores en 1.500 peticiones"],
    ["Tolerancia a fallos (RNF3)", "La IA entera cae → decisión por política de reserva en < 300 ms", "Prueba automática y `docker compose stop ia`", "Decisión `origen=reserva` en 5 ms"],
    ["Analizabilidad (RNF6)", "Ante un bloqueo, razones en < 5 s", "Front muestra razones ordenadas al responder", "< 0,1 s"],
    ["Trazabilidad (RF7, RNF7)", "Auditor pide una transacción → versión de modelo, datos y umbral", "`GET /api/dominio/predicciones/{id}`", "Inmediato (7 años: S3 en producción)"],
    ["Madurez (RF11)", "Un modelo con PR-AUC < 0,70 no se publica", "Compuerta del job `ia-modelo`", "Implementado"],
    ["Confidencialidad (RNF5)", "Llega un PAN → se rechaza y no se registra", "`test_pan_completo_es_rechazado`", "422"],
  ], [1.5, 2.6, 2.2, 1.6]),
];

const anexos = [
  H1("Anexo A. Referencias"),
  P("Amazon Web Services. (2026). *AWS Fargate pricing*. https://aws.amazon.com/fargate/pricing/", { align: AlignmentType.LEFT }),
  P("Amazon Web Services. (2026). *Amazon RDS for PostgreSQL pricing*. https://aws.amazon.com/rds/postgresql/pricing/", { align: AlignmentType.LEFT }),
  P("Brown, S. (2018). *The C4 model for visualising software architecture*. https://c4model.com", { align: AlignmentType.LEFT }),
  P("Chen, T., & Guestrin, C. (2016). XGBoost: A scalable tree boosting system. En *Proceedings of the 22nd ACM SIGKDD* (pp. 785–794). https://doi.org/10.1145/2939672.2939785", { align: AlignmentType.LEFT }),
  P("Lundberg, S. M., & Lee, S.-I. (2017). A unified approach to interpreting model predictions. *Advances in Neural Information Processing Systems, 30*, 4765–4774.", { align: AlignmentType.LEFT }),
  P("Starke, G., & Hruschka, P. (2023). *arc42 template* (versión 8.2). https://arc42.org", { align: AlignmentType.LEFT }),
  P("F5 / NGINX. (2025). *Module ngx_http_upstream_module*. https://nginx.org/en/docs/http/ngx_http_upstream_module.html", { align: AlignmentType.LEFT }),
  P("Citas en el cuerpo: XGBoost (Chen & Guestrin, 2016) en ADR-1 y 5.3; TreeSHAP (Lundberg & Lee, 2017) en 5.3; C4 (Brown, 2018) en 5; precios AWS (2026) en 7.3; `resolve` de nginx (F5/NGINX, 2025) en ADR-4.", { run: { size: 16, color: GRIS } }),
  H1("Anexo B. Declaración de uso de IA generativa"),
  ...T(["Herramienta", "Para qué se usó", "Qué verificó el equipo", "Partes"], [
    ["Gemini (EP1)", "Redacción y orden de ideas de EP1", "Cobertura de cada RF/RT por una decisión", "Caps. 1–4, 8–10 (v1.0)"],
    ["mermaid.ai / Mermaid", "Diagramas versionados en `docs/diagramas/*.mmd`", "Que la figura 3 tenga exactamente los servicios de `compose.yaml`", "Figuras 1–9"],
    ["Claude (Anthropic)", "Borrador del código (preparar.py, entrenar.py, servicios, nginx.conf, compose.yaml, ci.yml), de las pruebas y de este documento", "Se ejecutó todo: pruebas en verde, carga dos veces sin duplicar, medición de 7.2 y prueba de caída de réplica; se revisó cada regla de limpieza contra los datos y cada cifra contra su fuente; cada integrante puede explicar y modificar su parte", "Repositorio completo; caps. 5–10 (v2.0)"],
  ], [1.3, 2.4, 3, 1.2]),
  P("Firmas: ______________________ Sergio Martínez     ______________________ Roberto Castro     ______________________ Oscar Larrieu", { align: AlignmentType.LEFT }),
  H1("Anexo C. Repositorios y sistema"),
  P("Un solo repositorio con una carpeta por servicio; el workflow construye y publica una imagen por carpeta. `compose.yaml` de la defensa está en la raíz.", { align: AlignmentType.LEFT }),
  ...T(["Elemento", "Link"], [
    ["Repositorio (público)", "https://github.com/oscarL22997/guardian-centinela"],
    ["Tag ep2", "https://github.com/oscarL22997/guardian-centinela/releases/tag/ep2"],
    ["Última ejecución en verde del workflow en main", "https://github.com/oscarL22997/guardian-centinela/actions/runs/NNNNNNNNNN"],
    ["compose.yaml de la defensa", "https://github.com/oscarL22997/guardian-centinela/blob/main/compose.yaml"],
    ["Paquete gc-gateway", "https://github.com/users/oscarL22997/packages/container/package/gc-gateway"],
    ["Paquete gc-front", "https://github.com/users/oscarL22997/packages/container/package/gc-front"],
    ["Paquete gc-dominio", "https://github.com/users/oscarL22997/packages/container/package/gc-dominio"],
    ["Paquete gc-ia", "https://github.com/users/oscarL22997/packages/container/package/gc-ia"],
    ["Paquete gc-carga", "https://github.com/users/oscarL22997/packages/container/package/gc-carga"],
  ], [2.2, 5]),
  ...T(["Integrante", "Usuario de GitHub", "PR feat/ integrados en dev"], [
    ["Sergio Martínez", "@USUARIO_SERGIO", "feat/datos-tratamiento · feat/front-formulario"],
    ["Roberto Castro", "@USUARIO_ROBERTO", "feat/dominio-reglas-umbrales · feat/gateway-balanceo"],
    ["Oscar Larrieu", "@oscarL22997", "feat/ia-modelo-v1 · feat/pipeline-ci"],
  ], [1.6, 1.6, 4]),
];

const pie = new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
  new TextRun({ text: "ITY1102 · EP2 · Guardián Centinela (arc42) · Equipo 04 · página ", size: 15, color: GRIS }),
  new TextRun({ children: [PageNumber.CURRENT], size: 15, color: GRIS })] })] });

const doc = new Document({
  creator: "Equipo 04", title: "Guardián Centinela · arc42 EP2",
  styles: {
    default: { document: { run: { font: "Arial", size: 19 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 30, bold: true, color: AZUL, font: "Arial" }, paragraph: { outlineLevel: 0, keepNext: true } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 24, bold: true, color: AZUL_OSC, font: "Arial" }, paragraph: { outlineLevel: 1, keepNext: true } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 20, bold: true, color: "333333", font: "Arial" }, paragraph: { outlineLevel: 2, keepNext: true } },
    ],
  },
  numbering: { config: [{ reference: "vinetas", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 400, hanging: 240 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1000, bottom: 900, left: 1000, right: 1000 } } },
    footers: { default: pie },
    children: [...portada, ...indice, ...c1, ...c2, ...c3, ...c4, ...c5, ...c6, ...c7, ...c8, ...c84, ...c9, ...c10, SALTO(), ...anexos],
  }],
});
const salida = path.join(__dirname, "EP2_Equipo04_Martinez-Castro-Larrieu.docx");
Packer.toBuffer(doc).then((b) => { fs.writeFileSync(salida, b); console.log("OK", salida, "figuras:", nFig); });
