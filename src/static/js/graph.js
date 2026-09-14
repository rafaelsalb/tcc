const ARTICLE_COLOR = "#4f46e5";
const ENTITY_COLOR = "#d97706";
const LINK_COLOR = "#b6bdd0";
const MAX_PROJECTED_LINKS = 1200;

let nodesSel = null;
let linksSel = null;
let simulation = null;
let hoverData = null;
let selectedEntity = null;
let lastOpts = null;
let initialized = false;

const graphContainer = () => document.getElementById("graph");
const tooltipEl = () => document.getElementById("graph-tooltip");
const legendEl = () => document.getElementById("graph-legend");
const tableBodyEl = () => document.getElementById("entity-table-body");

export function hasGraph(response) {
    const graph = response?.graph;
    return Boolean(graph && Array.isArray(graph.nodes) && graph.nodes.length > 0);
}

export function getEntityArticleUrls(response, entityId) {
    const graph = response?.graph;
    if (!graph || !Array.isArray(graph.nodes) || !Array.isArray(graph.links)) return [];
    const isArticle = new Set(
        graph.nodes.filter((node) => node.type === "article").map((node) => node.id)
    );
    const urls = new Set();
    for (const link of graph.links) {
        const source = typeof link.source === "object" ? link.source.id : link.source;
        const target = typeof link.target === "object" ? link.target.id : link.target;
        if (source === entityId && isArticle.has(target)) urls.add(target);
        if (target === entityId && isArticle.has(source)) urls.add(source);
    }
    return [...urls];
}

function projectedLinks(nodes, links) {
    const entityToArticles = new Map();
    const isArticle = new Set(nodes.filter((n) => n.type === "article").map((n) => n.id));
    for (const link of links) {
        const source = typeof link.source === "object" ? link.source.id : link.source;
        const target = typeof link.target === "object" ? link.target.id : link.target;
        for (const [entityId, articleId] of [[source, target], [target, source]]) {
            if (isArticle.has(articleId) && !isArticle.has(entityId)) {
                if (!entityToArticles.has(entityId)) entityToArticles.set(entityId, []);
                entityToArticles.get(entityId).push(articleId);
            }
        }
    }
    const counts = new Map();
    for (const articles of entityToArticles.values()) {
        for (let i = 0; i < articles.length; i++) {
            for (let j = i + 1; j < articles.length; j++) {
                const key = `${articles[i]}\u0000${articles[j]}`;
                counts.set(key, (counts.get(key) ?? 0) + 1);
            }
        }
    }
    let projected = [...counts.entries()].map(([key, count]) => {
        const [source, target] = key.split("\u0000");
        return { source, target, count };
    });
    if (projected.length > MAX_PROJECTED_LINKS) {
        projected = projected.sort((a, b) => b.count - a.count).slice(0, MAX_PROJECTED_LINKS);
    }
    return projected;
}

function radiusOf(node, maxScore) {
    const scale = maxScore > 0 ? Math.sqrt((node.score ?? 0) / maxScore) : 0;
    return node.type === "article" ? 5 + 10 * scale : 3.5 + 7 * scale;
}

function tooltipContent(data) {
    const label = document.createElement("span");
    label.className = "tooltip-label";
    label.textContent = data.label || data.id;
    const lines = document.createElement("span");
    lines.textContent = data.type === "article"
        ? `Artigo · PPR ${(data.score ?? 0).toFixed(4)} · grau ${data.degree ?? 0}`
        : `Entidade · PPR ${(data.score ?? 0).toFixed(4)} · grau ${data.degree ?? 0}`;
    const hint = document.createElement("span");
    hint.className = "tooltip-hint";
    hint.textContent = data.type === "article"
        ? "Clique para localizar na linha do tempo"
        : "Clique para filtrar a linha do tempo";
    const fragment = document.createDocumentFragment();
    fragment.append(label, lines, hint);
    return fragment;
}

function renderTooltip() {
    const tooltip = tooltipEl();
    const container = graphContainer();
    if (!tooltip || !container) return;

    const target = hoverData ?? selectedEntity;
    if (!target || !nodesSel) {
        tooltip.classList.remove("visible");
        return;
    }

    let svgNode = null;
    nodesSel.each(function (d) {
        if (d.id === target.id) svgNode = this;
    });
    if (!svgNode) {
        tooltip.classList.remove("visible");
        return;
    }

    if (!tooltip.classList.contains("visible")) {
        tooltip.replaceChildren(tooltipContent(target));
    }

    const containerRect = container.getBoundingClientRect();
    const nodeRect = svgNode.getBoundingClientRect();
    tooltip.style.left = `${nodeRect.left - containerRect.left + nodeRect.width / 2}px`;
    tooltip.style.top = `${nodeRect.top - containerRect.top - 8}px`;
    tooltip.classList.add("visible");
}

function updateStyles() {
    const highlightId = selectedEntity ? selectedEntity.id : (hoverData ? hoverData.id : null);
    if (!nodesSel || !linksSel) return;

    if (!highlightId) {
        nodesSel.attr("opacity", 1).attr("stroke", null).attr("stroke-width", null);
        linksSel.attr("stroke-opacity", 0.55).attr("stroke", LINK_COLOR);
    } else {
        const connected = new Set([highlightId]);
        linksSel.each(function (l) {
            if (l.source.id === highlightId) connected.add(l.target.id);
            if (l.target.id === highlightId) connected.add(l.source.id);
        });
        nodesSel
            .attr("opacity", (d) => (connected.has(d.id) ? 1 : 0.12))
            .attr("stroke", (d) => (d.id === highlightId ? "#23293b" : null))
            .attr("stroke-width", (d) => (d.id === highlightId ? 1.6 : null));
        linksSel
            .attr("stroke-opacity", (l) => (l.source.id === highlightId || l.target.id === highlightId) ? 0.55 : 0.04)
            .attr("stroke", LINK_COLOR);
    }

    const rows = tableBodyEl()?.querySelectorAll("tr") ?? [];
    rows.forEach((row) => {
        row.classList.remove("selected", "hovered");
        if (selectedEntity && row.dataset.nodeId === selectedEntity.id) {
            row.classList.add("selected");
        } else if (!selectedEntity && hoverData && row.dataset.nodeId === hoverData.id) {
            row.classList.add("hovered");
        }
    });
}

function selectEntity(node, opts) {
    if (node && selectedEntity && selectedEntity.id === node.id) {
        selectedEntity = null;
    } else {
        selectedEntity = node ?? null;
    }
    if (opts.onEntitySelect) {
        opts.onEntitySelect(selectedEntity ? { id: selectedEntity.id, label: selectedEntity.label } : null);
    }
    updateStyles();
    renderTooltip();
}

export function clearEntitySelection() {
    selectedEntity = null;
    updateStyles();
    renderTooltip();
}

function renderLegend(graph, onlyArticles) {
    const legend = legendEl();
    if (!legend) return;
    legend.replaceChildren();
    const meta = graph.meta ?? {};
    const articleCount = meta.article_count ?? graph.nodes.filter((n) => n.type === "article").length;
    const entityCount = meta.entity_count ?? graph.nodes.filter((n) => n.type !== "article").length;

    const articleItem = document.createElement("span");
    articleItem.className = "legend-item";
    const articleDot = document.createElement("span");
    articleDot.className = "legend-dot";
    articleDot.style.background = ARTICLE_COLOR;
    articleItem.append(articleDot, document.createTextNode(`Artigos (${articleCount})`));

    const entityItem = document.createElement("span");
    entityItem.className = "legend-item";
    const entityDot = document.createElement("span");
    entityDot.className = "legend-dot";
    entityDot.style.background = ENTITY_COLOR;
    entityItem.append(entityDot, document.createTextNode(
        onlyArticles ? `Entidades ocultas (${entityCount})` : `Entidades (${entityCount})`
    ));

    legend.append(articleItem, entityItem);
    if (onlyArticles) {
        const note = document.createElement("span");
        note.className = "legend-item";
        note.style.color = "var(--text-3)";
        note.style.fontWeight = "500";
        note.textContent = "Arestas = artigos que compartilham entidades";
        legend.appendChild(note);
    }
}

function renderEntityTable(graph, opts) {
    const body = tableBodyEl();
    if (!body) return;
    body.replaceChildren();
    if (!graph || !Array.isArray(graph.nodes)) return;

    const entities = graph.nodes
        .filter((node) => node.type !== "article")
        .sort((a, b) => (b.degree ?? 0) - (a.degree ?? 0));

    for (const node of entities) {
        const row = document.createElement("tr");
        row.dataset.nodeId = node.id;

        row.addEventListener("mouseenter", () => {
            hoverData = node;
            if (!selectedEntity) updateStyles();
            renderTooltip();
        });
        row.addEventListener("mouseleave", () => {
            hoverData = null;
            if (!selectedEntity) updateStyles();
            renderTooltip();
        });
        row.addEventListener("click", () => selectEntity(node, opts));

        const nameCell = document.createElement("td");
        nameCell.textContent = node.label || node.id;
        const scoreCell = document.createElement("td");
        scoreCell.className = "num-cell";
        scoreCell.textContent = (node.score ?? 0).toFixed(4);
        const degreeCell = document.createElement("td");
        degreeCell.className = "num-cell";
        degreeCell.textContent = String(node.degree ?? 0);

        row.append(nameCell, scoreCell, degreeCell);
        body.appendChild(row);
    }
}

export function clearGraph() {
    const container = graphContainer();
    if (container) container.replaceChildren();
    const tooltip = tooltipEl();
    if (tooltip) tooltip.classList.remove("visible");
    nodesSel = null;
    linksSel = null;
    hoverData = null;
    selectedEntity = null;
    if (simulation) {
        simulation.stop();
        simulation = null;
    }
    initialized = false;
}

function showPlaceholder(message) {
    const container = graphContainer();
    if (!container) return;
    container.replaceChildren();
    const div = document.createElement("div");
    div.className = "graph-placeholder";
    div.textContent = message;
    container.appendChild(div);
    const tooltip = tooltipEl();
    if (tooltip) tooltip.classList.remove("visible");
    nodesSel = null;
    linksSel = null;
    initialized = false;
}

export function renderGraph(opts) {
    lastOpts = opts;
    const { response, onlyArticles = false } = opts;
    const container = graphContainer();
    if (!container) return;

    hoverData = null;
    renderTooltip();

    if (!hasGraph(response)) {
        showPlaceholder("Nenhum grafo disponível para esta busca.");
        renderLegend({ nodes: [] }, onlyArticles);
        renderEntityTable({ nodes: [] }, opts);
        selectedEntity = null;
        return;
    }

    if (typeof d3 === "undefined") {
        showPlaceholder("Falha ao carregar a biblioteca D3.");
        return;
    }

    if (simulation) simulation.stop();

    const graph = response.graph;
    if (selectedEntity && !graph.nodes.some((node) => node.id === selectedEntity.id)) {
        selectedEntity = null;
    }
    const nodes = onlyArticles
        ? graph.nodes.filter((node) => node.type === "article").map((node) => ({ ...node }))
        : graph.nodes.map((node) => ({ ...node }));
    const links = onlyArticles
        ? projectedLinks(graph.nodes, graph.links)
        : graph.links.map((link) => ({
            source: typeof link.source === "object" ? link.source.id : link.source,
            target: typeof link.target === "object" ? link.target.id : link.target,
        }));

    if (nodes.length === 0) {
        showPlaceholder("Nenhum nó para exibir.");
        return;
    }

    const maxScore = Math.max(...nodes.map((node) => node.score ?? 0), 0.000001);

    container.replaceChildren();
    const width = container.clientWidth || 860;
    const height = container.clientHeight || 590;

    const svg = d3.select(container)
        .append("svg")
        .attr("width", width)
        .attr("height", height)
        .attr("viewBox", `0 0 ${width} ${height}`);

    svg.append("rect")
        .attr("width", width)
        .attr("height", height)
        .attr("fill", "transparent")
        .on("click", () => {
            hoverData = null;
            if (selectedEntity) {
                selectEntity(null, opts);
            } else {
                updateStyles();
                renderTooltip();
            }
        });

    const zoomLayer = svg.append("g");
    svg.call(
        d3.zoom().scaleExtent([0.2, 5]).on("zoom", (event) => {
            zoomLayer.attr("transform", event.transform);
            renderTooltip();
        })
    );

    linksSel = zoomLayer.append("g")
        .attr("stroke", LINK_COLOR)
        .attr("stroke-opacity", 0.55)
        .selectAll("line")
        .data(links)
        .join("line")
        .attr("stroke-width", (l) => (l.count ? 0.6 + Math.min(l.count, 6) * 0.5 : 0.6));

    nodesSel = zoomLayer.append("g")
        .selectAll("circle")
        .data(nodes)
        .join("circle")
        .attr("r", (d) => radiusOf(d, maxScore))
        .attr("fill", (d) => (d.type === "article" ? ARTICLE_COLOR : ENTITY_COLOR))
        .on("mouseover", (event, d) => {
            hoverData = d;
            if (!selectedEntity) updateStyles();
            renderTooltip();
        })
        .on("mouseout", () => {
            hoverData = null;
            if (!selectedEntity) updateStyles();
            renderTooltip();
        })
        .on("click", (event, d) => {
            event.stopPropagation();
            if (d.type === "article") {
                hoverData = null;
                if (selectedEntity) {
                    selectedEntity = null;
                    if (opts.onEntitySelect) opts.onEntitySelect(null);
                }
                if (opts.onArticleClick) opts.onArticleClick(d.id);
            } else {
                selectEntity(d, opts);
            }
            updateStyles();
            renderTooltip();
        })
        .call(
            d3.drag()
                .on("start", (event, d) => {
                    if (!event.active) simulation.alphaTarget(0.3).restart();
                    d.fx = d.x;
                    d.fy = d.y;
                })
                .on("drag", (event, d) => {
                    d.fx = event.x;
                    d.fy = event.y;
                    renderTooltip();
                })
                .on("end", (event, d) => {
                    if (!event.active) simulation.alphaTarget(0);
                    d.fx = null;
                    d.fy = null;
                })
        );

    simulation = d3.forceSimulation(nodes)
        .force("link", d3.forceLink(links).id((d) => d.id).distance((l) => (l.count ? 70 : 55)))
        .force("charge", d3.forceManyBody().strength(-90))
        .force("center", d3.forceCenter(width / 2, height / 2))
        .force("collision", d3.forceCollide().radius((d) => radiusOf(d, maxScore) + 3));

    simulation.on("tick", () => {
        linksSel
            .attr("x1", (d) => d.source.x)
            .attr("y1", (d) => d.source.y)
            .attr("x2", (d) => d.target.x)
            .attr("y2", (d) => d.target.y);
        nodesSel
            .attr("cx", (d) => d.x)
            .attr("cy", (d) => d.y);
        if (tooltipEl()?.classList.contains("visible")) renderTooltip();
    });

    renderLegend(graph, onlyArticles);
    renderEntityTable(graph, opts);
    updateStyles();
    renderTooltip();
    initialized = true;
}

export function isGraphInitialized() {
    return initialized;
}

export function rerenderIfInitialized() {
    if (initialized && lastOpts) renderGraph(lastOpts);
}

let resizeTimer = null;
window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(rerenderIfInitialized, 250);
});
