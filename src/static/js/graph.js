const ARTICLE_COLOR = "#4f46e5";
const ENTITY_COLOR = "#d97706";
const MMR_RING = "#0d9488";
const LINK_COLOR = "#b6bdd0";
const MAX_PROJECTED_LINKS = 1200;

import { normalizeText, mmrFlaggedUrls } from "./timeline.js";
import { helpDot } from "./help.js";

let nodesSel = null;
let linksSel = null;
let simulation = null;
let nodesById = new Map();
let hoverData = null;
let selectedEntities = [];
let lastTooltipTargetId = null;
let lastOpts = null;
let lastGraph = null;
let topicQuery = "";
let entitySort = { key: "degree", dir: "desc" };
let sortListenersBound = false;
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

function filterGraphToUrls(graph, urls) {
    const articles = graph.nodes.filter((node) => node.type === "article" && urls.has(node.id));
    const articleIds = new Set(articles.map((node) => node.id));
    // Bipartite graph (article <-> entity): keep every link whose article end
    // is selected; the entity end then defines which entities survive.
    const links = graph.links.filter((link) => {
        const sIn = articleIds.has(link.source);
        const tIn = articleIds.has(link.target);
        return (sIn && !tIn) || (tIn && !sIn);
    });
    const entityIds = new Set();
    for (const link of links) {
        if (!articleIds.has(link.source)) entityIds.add(link.source);
        if (!articleIds.has(link.target)) entityIds.add(link.target);
    }
    const entities = graph.nodes.filter((node) => node.type !== "article" && entityIds.has(node.id));
    return {
        nodes: [...articles, ...entities],
        links,
        meta: {
            article_count: articles.length,
            entity_count: entities.length,
            ppr_seed_count: entities.filter((node) => node.ppr_seed).length,
        },
    };
}

function radiusOf(node, maxScore) {
    const scale = maxScore > 0 ? Math.sqrt((node.score ?? 0) / maxScore) : 0;
    return node.type === "article" ? 5 + 10 * scale : 3.5 + 7 * scale;
}

function relevancePct(score) {
    return `${((score ?? 0) * 100).toFixed(2)}%`;
}

function ringAttrs() {
    return {
        stroke: (d) => (d.type === "article" && d.mmr ? MMR_RING : null),
        strokeWidth: (d) => (d.type === "article" && d.mmr ? 2.5 : null),
        dasharray: (d) => null,
    };
}

function tooltipContent(data) {
    const label = document.createElement("span");
    label.className = "tooltip-label";
    label.textContent = data.label || data.id;
    const hitsPart = data.hits != null ? ` · HITS ${relevancePct(data.hits)}` : "";
    const lines = document.createElement("span");
    lines.textContent = data.type === "article"
        ? `Artigo · Relevância ${relevancePct(data.score)} · ${data.degree ?? 0} citações${hitsPart}`
        : `Tópico · Relevância ${relevancePct(data.score)} · ${data.degree ?? 0} citações${hitsPart}`;
    const fragment = document.createDocumentFragment();
    fragment.append(label, lines);
    if (data.type === "article" && data.mmr) {
        const mmr = document.createElement("span");
        mmr.className = "tooltip-mmr";
        mmr.textContent = "Selecionado por diversidade (MMR)";
        fragment.appendChild(mmr);
    }
    const hint = document.createElement("span");
    hint.className = "tooltip-hint";
    hint.textContent = data.type === "article"
        ? "Clique para localizar na linha do tempo"
        : "Clique para filtrar a linha do tempo";
    fragment.appendChild(hint);
    return fragment;
}

function renderTooltip() {
    const tooltip = tooltipEl();
    const container = graphContainer();
    if (!tooltip || !container) return;

    const target = hoverData ?? (selectedEntities.length > 0
        ? selectedEntities[selectedEntities.length - 1]
        : null);
    if (!target || !nodesSel) {
        tooltip.classList.remove("visible");
        lastTooltipTargetId = null;
        return;
    }

    let svgNode = null;
    nodesSel.each(function (d) {
        if (d.id === target.id) svgNode = this;
    });
    if (!svgNode) {
        tooltip.classList.remove("visible");
        lastTooltipTargetId = null;
        return;
    }

    if (target.id !== lastTooltipTargetId) {
        tooltip.replaceChildren(tooltipContent(target));
        lastTooltipTargetId = target.id;
    }

    const containerRect = container.getBoundingClientRect();
    const nodeRect = svgNode.getBoundingClientRect();
    tooltip.style.left = `${nodeRect.left - containerRect.left + nodeRect.width / 2}px`;
    tooltip.style.top = `${nodeRect.top - containerRect.top - 8}px`;
    tooltip.classList.add("visible");
}

function updateStyles() {
    if (!nodesSel || !linksSel) return;
    const ring = ringAttrs();

    const selectedIdSet = new Set(selectedEntities.map((e) => e.id));
    const hoverId = selectedIdSet.size === 0 && hoverData ? hoverData.id : null;
    const highlightIds = selectedIdSet.size > 0 ? selectedIdSet : (hoverId ? new Set([hoverId]) : null);

    if (!highlightIds) {
        nodesSel.attr("opacity", 1)
            .attr("stroke", ring.stroke)
            .attr("stroke-width", ring.strokeWidth)
            .attr("stroke-dasharray", ring.dasharray);
        linksSel.attr("stroke-opacity", 0.55).attr("stroke", LINK_COLOR);
    } else {
        const connected = new Set(highlightIds);
        linksSel.each(function (l) {
            if (highlightIds.has(l.source.id)) connected.add(l.target.id);
            if (highlightIds.has(l.target.id)) connected.add(l.source.id);
        });
        nodesSel
            .attr("opacity", (d) => (connected.has(d.id) ? 1 : 0.12))
            .attr("stroke", (d) => (highlightIds.has(d.id) ? "#23293b" : ring.stroke(d)))
            .attr("stroke-width", (d) => (highlightIds.has(d.id) ? 1.6 : ring.strokeWidth(d)))
            .attr("stroke-dasharray", (d) => (highlightIds.has(d.id) ? null : ring.dasharray(d)));
        linksSel
            .attr("stroke-opacity", (l) => (highlightIds.has(l.source.id) || highlightIds.has(l.target.id)) ? 0.55 : 0.04)
            .attr("stroke", LINK_COLOR);
    }

    const rows = tableBodyEl()?.querySelectorAll("tr") ?? [];
    rows.forEach((row) => {
        row.classList.remove("selected", "hovered");
        if (selectedIdSet.has(row.dataset.nodeId)) {
            row.classList.add("selected");
        } else if (hoverId && row.dataset.nodeId === hoverId) {
            row.classList.add("hovered");
        }
    });
}

function notifySelection(opts) {
    if (opts.onEntitySelect) {
        opts.onEntitySelect(selectedEntities.map((e) => ({ id: e.id, label: e.label })));
    }
}

function selectEntity(node, opts) {
    const index = selectedEntities.findIndex((e) => e.id === node.id);
    if (index >= 0) selectedEntities.splice(index, 1);
    else selectedEntities.push(node);
    notifySelection(opts);
    updateStyles();
    renderTooltip();
}

export function setEntitySelection(ids) {
    selectedEntities = (ids ?? [])
        .map((id) => nodesById.get(id))
        .filter(Boolean);
    updateStyles();
    renderTooltip();
}

export function clearEntitySelection() {
    selectedEntities = [];
    updateStyles();
    renderTooltip();
}

function renderLegend(graph, onlyArticles, mmrFlagged) {
    const legend = legendEl();
    if (!legend) return;
    legend.replaceChildren();
    const meta = graph.meta ?? {};
    const articleCount = meta.article_count ?? graph.nodes.filter((n) => n.type === "article").length;
    const entityCount = meta.entity_count ?? graph.nodes.filter((n) => n.type !== "article").length;
    const mmrCount = graph.nodes.filter((n) => n.type === "article" && mmrFlagged.has(n.id)).length;

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
        onlyArticles ? `Tópicos ocultos (${entityCount})` : `Tópicos (${entityCount})`
    ));

    legend.append(articleItem, entityItem);
    legend.appendChild(helpDot(
        "Cada bola é um artigo (azul) ou um tópico (laranja); as linhas mostram quem cita quem. Passe o mouse para detalhes, arraste para organizar, clique para filtrar ou abrir o artigo.",
        "help-dot--inline"
    ));

    if (mmrCount > 0) {
        const mmrItem = document.createElement("span");
        mmrItem.className = "legend-item";
        const mmrDot = document.createElement("span");
        mmrDot.className = "legend-dot";
        mmrDot.style.background = "transparent";
        mmrDot.style.border = `2px solid ${MMR_RING}`;
        mmrItem.append(mmrDot, document.createTextNode(`MMR (${mmrCount})`));
        legend.appendChild(mmrItem);
    }

    if (onlyArticles) {
        const note = document.createElement("span");
        note.className = "legend-item";
        note.style.color = "var(--text-3)";
        note.style.fontWeight = "500";
        note.textContent = "Conexões = artigos que compartilham tópicos";
        legend.appendChild(note);
    }
}

function renderEntityTable(graph, opts) {
    const body = tableBodyEl();
    if (!body) return;
    body.replaceChildren();
    if (!graph || !Array.isArray(graph.nodes)) return;

    const needle = normalizeText(topicQuery);
    const entities = graph.nodes
        .filter((node) => node.type !== "article")
        .filter((node) => !needle || normalizeText(node.label || node.id).includes(needle));

    sortEntities(entities);

    if (entities.length === 0) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 4;
        cell.className = "entity-table-empty";
        cell.textContent = topicQuery ? "Nenhum tópico encontrado." : "Nenhum tópico nesta seleção.";
        row.appendChild(cell);
        body.appendChild(row);
        return;
    }

    for (const node of entities) {
        const row = document.createElement("tr");
        row.dataset.nodeId = node.id;

        row.addEventListener("mouseenter", () => {
            hoverData = node;
            if (selectedEntities.length === 0) updateStyles();
            renderTooltip();
        });
        row.addEventListener("mouseleave", () => {
            hoverData = null;
            if (selectedEntities.length === 0) updateStyles();
            renderTooltip();
        });
        row.addEventListener("click", () => selectEntity(node, opts));

        const nameCell = document.createElement("td");
        nameCell.textContent = node.label || node.id;
        const scoreCell = document.createElement("td");
        scoreCell.className = "num-cell";
        scoreCell.textContent = relevancePct(node.score);
        const hitsCell = document.createElement("td");
        hitsCell.className = "num-cell";
        hitsCell.textContent = relevancePct(node.hits ?? 0);
        const degreeCell = document.createElement("td");
        degreeCell.className = "num-cell";
        degreeCell.textContent = String(node.degree ?? 0);

        row.append(nameCell, scoreCell, hitsCell, degreeCell);
        body.appendChild(row);
    }
}

const ENTITY_SORT_DEFAULTS = {
    label: { dir: "asc" },
    score: { dir: "desc" },
    hits: { dir: "desc" },
    degree: { dir: "desc" },
};

function entityValue(node, key) {
    if (key === "label") return node.label || node.id;
    return node[key] ?? 0;
}

function sortEntities(entities) {
    const { key, dir } = entitySort;
    const sign = dir === "asc" ? 1 : -1;
    entities.sort((a, b) => {
        const va = entityValue(a, key);
        const vb = entityValue(b, key);
        const cmp = typeof va === "string" ? va.localeCompare(vb, "pt-BR") : va - vb;
        if (cmp !== 0) return sign * cmp;
        return (entityValue(a, "label")).localeCompare(entityValue(b, "label"), "pt-BR");
    });
}

function renderSortIndicators() {
    const table = tableBodyEl()?.closest("table");
    if (!table) return;
    for (const th of table.querySelectorAll("th[data-key]")) {
        const indicator = th.querySelector(".sort-indicator");
        if (th.dataset.key === entitySort.key) {
            if (!indicator) {
                const span = document.createElement("span");
                span.className = "sort-indicator";
                th.appendChild(span);
            }
            th.querySelector(".sort-indicator").textContent = entitySort.dir === "asc" ? "▲" : "▼";
        } else if (indicator) {
            indicator.remove();
        }
    }
}

function bindEntitySortListeners() {
    if (sortListenersBound) return;
    const table = tableBodyEl()?.closest("table");
    if (!table) return;
    for (const th of table.querySelectorAll("th[data-key]")) {
        th.addEventListener("click", () => {
            const key = th.dataset.key;
            if (entitySort.key === key) {
                entitySort.dir = entitySort.dir === "asc" ? "desc" : "asc";
            } else {
                entitySort = { key, dir: ENTITY_SORT_DEFAULTS[key]?.dir ?? "desc" };
            }
            renderSortIndicators();
            if (lastGraph) {
                renderEntityTable(lastGraph, lastOpts);
                updateStyles();
            }
        });
    }
    sortListenersBound = true;
}

export function setTopicFilter(query) {
    topicQuery = query ?? "";
    if (lastGraph) {
        renderEntityTable(lastGraph, lastOpts);
        updateStyles();
    }
}

export function clearGraph() {
    const container = graphContainer();
    if (container) container.replaceChildren();
    const tooltip = tooltipEl();
    if (tooltip) tooltip.classList.remove("visible");
    lastTooltipTargetId = null;
    nodesSel = null;
    linksSel = null;
    hoverData = null;
    selectedEntities = [];
    lastGraph = null;
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
    lastTooltipTargetId = null;
    lastGraph = null;
    nodesSel = null;
    linksSel = null;
    initialized = false;
}

export function renderGraph(opts) {
    lastOpts = opts;
    const { response, onlyArticles = false, topUrls = null } = opts;
    const container = graphContainer();
    if (!container) return;

    hoverData = null;
    renderTooltip();

    if (!hasGraph(response)) {
        showPlaceholder("Nenhum mapa disponível para esta busca.");
        renderLegend({ nodes: [] }, onlyArticles);
        renderEntityTable({ nodes: [] }, opts);
        selectedEntities = [];
        return;
    }

    if (typeof d3 === "undefined") {
        showPlaceholder("Não foi possível carregar o mapa.");
        return;
    }

    if (simulation) simulation.stop();

    // Top-N filter first: only the selected articles, their entities and the
    // links between them survive (the "Só artigos" projection builds on this).
    const graph = topUrls ? filterGraphToUrls(response.graph, topUrls) : response.graph;
    lastGraph = graph;
    nodesById = new Map(graph.nodes.map((node) => [node.id, node]));
    selectedEntities = selectedEntities.filter((e) => nodesById.has(e.id));

    const mmrFlagged = mmrFlaggedUrls(response);
    const nodes = onlyArticles
        ? graph.nodes.filter((node) => node.type === "article").map((node) => ({ ...node, mmr: mmrFlagged.has(node.id) }))
        : graph.nodes.map((node) => ({ ...node, mmr: node.type === "article" && mmrFlagged.has(node.id) }));
    const links = onlyArticles
        ? projectedLinks(graph.nodes, graph.links)
        : graph.links.map((link) => ({
            source: typeof link.source === "object" ? link.source.id : link.source,
            target: typeof link.target === "object" ? link.target.id : link.target,
        }));

    if (nodes.length === 0) {
        showPlaceholder("Nada para exibir aqui.");
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
            if (selectedEntities.length > 0) {
                selectedEntities = [];
                notifySelection(opts);
            }
            updateStyles();
            renderTooltip();
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
            if (selectedEntities.length === 0) updateStyles();
            renderTooltip();
        })
        .on("mouseout", () => {
            hoverData = null;
            if (selectedEntities.length === 0) updateStyles();
            renderTooltip();
        })
        .on("click", (event, d) => {
            event.stopPropagation();
            if (d.type === "article") {
                hoverData = null;
                if (selectedEntities.length > 0) {
                    selectedEntities = [];
                    notifySelection(opts);
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

    renderLegend(graph, onlyArticles, mmrFlagged);
    renderEntityTable(graph, opts);
    renderSortIndicators();
    bindEntitySortListeners();
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
