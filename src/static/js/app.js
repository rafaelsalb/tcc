import { searchArticles } from "./api.js";
import { computeView, renderTimeline, scrollToArticle, matchEntities, topArticleUrls } from "./timeline.js";
import { renderScorePlot } from "./scoreplot.js";
import {
    renderGraph,
    setEntitySelection,
    clearEntitySelection,
    getEntityArticleUrls,
    setTopicFilter,
} from "./graph.js";
import { initEvalTab, setEvalResponse } from "./eval.js";

const state = {
    response: null,
    sort: "date_desc",
    topN: null,
    entityFilters: new Map(),
    entityMatch: "any",
};

// Search depth presets exposed to the user as "Nível de busca".
const SEARCH_LEVELS = {
    rapido: { limit: 50, topK: 25 },
    balanceado: { limit: 200, topK: 30 },
    profundo: { limit: 400, topK: 40 },
};
const DEFAULT_LEVEL = "balanceado";

let graphDirty = false;

const els = {
    form: document.getElementById("search-form"),
    query: document.getElementById("query"),
    searchLevel: document.getElementById("search-level"),
    advancedToggle: document.getElementById("advanced-toggle"),
    advancedFilters: document.getElementById("advanced-filters"),
    dateFrom: document.getElementById("date_from"),
    dateTo: document.getElementById("date_to"),
    timeline: document.getElementById("timeline"),
    sortSelect: document.getElementById("sort-select"),
    topN: document.getElementById("top-n"),
    topNValue: document.getElementById("top-n-value"),
    topNAll: document.getElementById("top-n-all"),
    entityFilters: document.getElementById("entity-filters"),
    chipSlot: document.getElementById("entity-chip-slot"),
    matchButtons: [...document.querySelectorAll("#match-toggle button")],
    lucky: document.getElementById("lucky-button"),
    entityPicker: document.getElementById("entity-picker"),
    entityPickerInput: document.getElementById("entity-picker-input"),
    entityPickerList: document.getElementById("entity-picker-list"),
    statStrip: document.getElementById("stat-strip"),
    toolbar: document.getElementById("timeline-toolbar"),
    scorePlotCard: document.getElementById("score-plot-card"),
    scorePlot: document.getElementById("score-plot"),
    scorePlotTooltip: document.getElementById("score-plot-tooltip"),
    statCount: document.getElementById("stat-count"),
    statSpan: document.getElementById("stat-span"),
    statAvg: document.getElementById("stat-avg"),
    statEntities: document.getElementById("stat-entities"),
    errorBanner: document.getElementById("error-banner"),
    errorText: document.getElementById("error-text"),
    errorClose: document.getElementById("error-close"),
    loadingOverlay: document.getElementById("loading-overlay"),
    onlyArticles: document.getElementById("only-articles"),
    topNGraph: document.getElementById("top-n-graph"),
    topNGraphValue: document.getElementById("top-n-graph-value"),
    topNGraphAll: document.getElementById("top-n-graph-all"),
    topicSearch: document.getElementById("topic-search"),
    tabButtons: [...document.querySelectorAll(".tab-button")],
    tabPanels: [...document.querySelectorAll(".tab-panel")],
};

const SHORT_DATE = new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "UTC",
});

/* ----------------------------------------------------------------------
   Loading / errors
   ---------------------------------------------------------------------- */

function setLoading(isLoading) {
    els.loadingOverlay.classList.toggle("visible", isLoading);
    document.body.classList.toggle("is-loading", isLoading);
}

function showError(message) {
    els.errorText.textContent = message;
    els.errorBanner.hidden = false;
}

function hideError() {
    els.errorBanner.hidden = true;
}

/* ----------------------------------------------------------------------
   URL state
   ---------------------------------------------------------------------- */

function readForm() {
    const level = SEARCH_LEVELS[els.searchLevel.value] ? els.searchLevel.value : DEFAULT_LEVEL;
    return {
        query: els.query.value.trim(),
        level,
        limit: String(SEARCH_LEVELS[level].limit),
        topK: String(SEARCH_LEVELS[level].topK),
        dateFrom: els.dateFrom.value,
        dateTo: els.dateTo.value,
    };
}

function fillForm(params) {
    els.query.value = params.get("query") ?? "";
    els.searchLevel.value = SEARCH_LEVELS[params.get("level")] ? params.get("level") : DEFAULT_LEVEL;
    els.dateFrom.value = params.get("date_from") ?? "";
    els.dateTo.value = params.get("date_to") ?? "";
    if (params.get("date_from") || params.get("date_to")) {
        setAdvancedExpanded(true);
    }
}

/* ----------------------------------------------------------------------
   Advanced filters (collapsible date range)
   ---------------------------------------------------------------------- */

function setAdvancedExpanded(expanded) {
    els.advancedFilters.hidden = !expanded;
    els.advancedToggle.setAttribute("aria-expanded", String(expanded));
    els.advancedToggle.textContent = expanded ? "− Filtros avançados" : "+ Filtros avançados";
}

function pushUrl(params) {
    const qs = new URLSearchParams();
    qs.set("query", params.query);
    qs.set("level", params.level);
    if (params.dateFrom) qs.set("date_from", params.dateFrom);
    if (params.dateTo) qs.set("date_to", params.dateTo);
    history.pushState(null, "", `/?${qs.toString()}`);
}

/* ----------------------------------------------------------------------
   Rendering
   ---------------------------------------------------------------------- */

function renderStats() {
    if (!state.response) {
        els.statStrip.hidden = true;
        els.toolbar.hidden = true;
        els.scorePlotCard.hidden = true;
        return;
    }
    const { articles, total } = computeView(state);
    const retrieved = state.response.articles?.length ?? 0;

    els.statCount.textContent = total === retrieved ? `${retrieved}` : `${total} de ${retrieved}`;

    const dates = articles.map((a) => a.date).filter(Boolean);
    if (dates.length > 0) {
        const min = new Date(Math.min(...dates.map((d) => d.getTime())));
        const max = new Date(Math.max(...dates.map((d) => d.getTime())));
        els.statSpan.textContent = dates.length > 1
            ? `${SHORT_DATE.format(min)} – ${SHORT_DATE.format(max)}`
            : SHORT_DATE.format(min);
    } else {
        els.statSpan.textContent = "—";
    }

    if (articles.length > 0) {
        const avg = articles.reduce((sum, a) => sum + (a.score ?? 0), 0) / articles.length;
        els.statAvg.textContent = avg.toFixed(3);
    } else {
        els.statAvg.textContent = "—";
    }

    const entityCount = state.response.graph?.meta?.entity_count;
    els.statEntities.textContent = entityCount != null ? String(entityCount) : "—";

    els.statStrip.hidden = false;
    els.toolbar.hidden = false;
    els.scorePlotCard.hidden = false;
}

function renderEntityChips() {
    els.chipSlot.replaceChildren();
    els.entityFilters.hidden = state.entityFilters.size === 0;
    for (const button of els.matchButtons) {
        button.classList.toggle("active", button.dataset.match === state.entityMatch);
    }
    for (const [id, entity] of state.entityFilters) {
        const chip = document.createElement("span");
        chip.className = "entity-chip";
        chip.append(entity.label);
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "entity-chip-remove";
        remove.setAttribute("aria-label", `Remover filtro: ${entity.label}`);
        remove.textContent = "×";
        remove.addEventListener("click", () => toggleEntityFilter(id, entity.label));
        chip.appendChild(remove);
        els.chipSlot.appendChild(chip);
    }
}

function renderEntityPicker() {
    els.entityPicker.hidden = !state.response;
    els.entityPickerList.replaceChildren();
    if (!state.response) return;

    const matches = matchEntities(state.response, els.entityPickerInput.value);
    if (matches.length === 0) {
        const li = document.createElement("li");
        li.className = "entity-picker-empty";
        li.textContent = "Nenhum tópico encontrado.";
        els.entityPickerList.appendChild(li);
        return;
    }

    for (const node of matches) {
        const li = document.createElement("li");
        li.className = "entity-picker-item";
        if (state.entityFilters.has(node.id)) li.classList.add("selected");

        const name = document.createElement("span");
        name.className = "picker-name";
        name.textContent = node.label || node.id;
        if (node.ppr_seed) {
            const star = document.createElement("span");
            star.className = "seed-mark";
            star.textContent = "★";
            star.title = "Tópico Principal";
            star.setAttribute("aria-label", "Tópico Principal");
            name.appendChild(star);
        }
        const degree = document.createElement("span");
        degree.className = "picker-degree";
        degree.textContent = `${node.degree ?? 0} citações`;

        li.append(name, degree);
        li.addEventListener("click", () => toggleEntityFilter(node.id, node.label || node.id));
        els.entityPickerList.appendChild(li);
    }
}

function syncTopNBounds() {
    const total = state.response?.articles?.length ?? 0;
    const max = Math.max(1, total);
    els.topN.disabled = total === 0;
    els.topNAll.disabled = total === 0;
    els.topNGraph.disabled = total === 0;
    els.topNGraphAll.disabled = total === 0;
    els.topN.min = "1";
    els.topN.max = String(max);
    if (state.topN == null || state.topN > max) state.topN = max;
    if (state.topN < 1) state.topN = 1;
    els.topN.value = String(state.topN);
    els.topNValue.textContent = String(state.topN);
    els.topNGraph.min = "1";
    els.topNGraph.max = String(max);
    els.topNGraph.value = String(state.topN);
    els.topNGraphValue.textContent = String(state.topN);
}

function setTopN(value) {
    if (Number.isNaN(value)) return;
    const max = Math.max(1, state.response?.articles?.length ?? 0);
    state.topN = Math.max(1, Math.min(value, max));
    els.topN.value = String(state.topN);
    els.topNValue.textContent = String(state.topN);
    els.topNGraph.value = String(state.topN);
    els.topNGraphValue.textContent = String(state.topN);
    graphDirty = true;
    renderAll();
}

function renderTimelineView() {
    renderTimeline(els.timeline, state);
}

function renderAll() {
    renderStats();
    renderScorePlot(els.scorePlot, els.scorePlotTooltip, state, { onDotClick: handleScoreDotClick });
    renderTimelineView();
}

/* ----------------------------------------------------------------------
   Score plot dot navigation
   ---------------------------------------------------------------------- */

function handleScoreDotClick(url) {
    setActiveTab("panel-timeline");
    if (!scrollToArticle(els.timeline, url) && state.entityFilters.size > 0) {
        clearEntityFilters();
        requestAnimationFrame(() => {
            scrollToArticle(els.timeline, url);
        });
    }
}

/* ----------------------------------------------------------------------
   Entity filters
   ---------------------------------------------------------------------- */

function toggleEntityFilter(id, label) {
    if (state.entityFilters.has(id)) {
        state.entityFilters.delete(id);
    } else {
        const urls = getEntityArticleUrls(state.response, id);
        state.entityFilters.set(id, { label, urls: new Set(urls) });
    }
    setEntitySelection([...state.entityFilters.keys()]);
    renderEntityChips();
    renderEntityPicker();
    renderAll();
}

function handleEntitySelect(entities) {
    state.entityFilters = new Map(entities.map((entity) => [
        entity.id,
        {
            label: entity.label,
            urls: new Set(getEntityArticleUrls(state.response, entity.id)),
        },
    ]));
    renderEntityChips();
    renderEntityPicker();
    renderAll();
}

function clearEntityFilters() {
    state.entityFilters.clear();
    clearEntitySelection();
    renderEntityChips();
    renderEntityPicker();
    renderAll();
}

/* ----------------------------------------------------------------------
   "Estou com sorte": jump to the most relevant article
   ---------------------------------------------------------------------- */

function handleLucky() {
    if (!state.response) return;
    const { articles } = computeView({ ...state, sort: "ppr_desc" });
    if (articles.length === 0) {
        showError("Nenhum artigo no filtro atual.");
        return;
    }
    const top = articles[0];
    state.topN = 1;
    syncTopNBounds();
    setActiveTab("panel-timeline");
    renderAll();
    requestAnimationFrame(() => {
        scrollToArticle(els.timeline, top.url);
    });
}

/* ----------------------------------------------------------------------
   Graph wiring
   ---------------------------------------------------------------------- */

function graphTabActive() {
    return document.getElementById("panel-graph").classList.contains("active");
}

function renderGraphNow() {
    renderGraph({
        response: state.response,
        onlyArticles: els.onlyArticles.checked,
        topUrls: state.response ? topArticleUrls(state.response, state.topN) : null,
        onEntitySelect: handleEntitySelect,
        onArticleClick: handleArticleClick,
    });
    graphDirty = false;
}

function handleArticleClick(url) {
    setActiveTab("panel-timeline");
    let found = scrollToArticle(els.timeline, url);
    if (!found && state.entityFilters.size > 0) {
        clearEntityFilters();
        requestAnimationFrame(() => {
            scrollToArticle(els.timeline, url);
        });
    }
}

/* ----------------------------------------------------------------------
   Tabs
   ---------------------------------------------------------------------- */

function setActiveTab(tabId) {
    for (const button of els.tabButtons) {
        const isActive = button.dataset.tab === tabId;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-selected", isActive ? "true" : "false");
    }
    for (const panel of els.tabPanels) {
        panel.classList.toggle("active", panel.id === tabId);
    }
    if (tabId === "panel-graph" && (graphDirty || !document.getElementById("graph").hasChildNodes())) {
        renderGraphNow();
    }
}

/* ----------------------------------------------------------------------
   Search flow
   ---------------------------------------------------------------------- */

async function runSearch({ push = true } = {}) {
    const params = readForm();
    if (!params.query) {
        showError("Informe um assunto para buscar.");
        return;
    }

    setLoading(true);
    hideError();
    try {
        const data = await searchArticles(params);
        state.response = data;
        state.entityFilters = new Map();
        syncTopNBounds();
        renderEntityChips();
        renderEntityPicker();
        renderAll();
        setEvalResponse(data);
        els.lucky.disabled = false;
        graphDirty = true;
        if (graphTabActive()) renderGraphNow();
        if (push) pushUrl(params);
    } catch (error) {
        showError(error.message);
    } finally {
        setLoading(false);
    }
}

/* ----------------------------------------------------------------------
   Event wiring
   ---------------------------------------------------------------------- */

els.form.addEventListener("submit", (event) => {
    event.preventDefault();
    runSearch();
});

els.errorClose.addEventListener("click", hideError);

els.sortSelect.addEventListener("change", () => {
    state.sort = els.sortSelect.value;
    renderAll();
});

els.topN.addEventListener("input", () => {
    setTopN(Number.parseInt(els.topN.value, 10));
});

els.topN.addEventListener("change", () => {
    if (graphTabActive()) renderGraphNow();
});

els.topNAll.addEventListener("click", () => {
    setTopN(Math.max(1, state.response?.articles?.length ?? 0));
    if (graphTabActive()) renderGraphNow();
});

els.topNGraph.addEventListener("input", () => {
    setTopN(Number.parseInt(els.topNGraph.value, 10));
});

els.topNGraph.addEventListener("change", () => {
    if (graphTabActive()) renderGraphNow();
});

els.topNGraphAll.addEventListener("click", () => {
    setTopN(Math.max(1, state.response?.articles?.length ?? 0));
    if (graphTabActive()) renderGraphNow();
});

els.topicSearch.addEventListener("input", () => {
    setTopicFilter(els.topicSearch.value);
});

els.advancedToggle.addEventListener("click", () => {
    setAdvancedExpanded(els.advancedFilters.hidden);
});

for (const button of els.matchButtons) {
    button.addEventListener("click", () => {
        state.entityMatch = button.dataset.match;
        renderEntityChips();
        renderAll();
    });
}

els.timeline.addEventListener("entity-toggle", (event) => {
    toggleEntityFilter(event.detail.id, event.detail.label);
});

els.lucky.addEventListener("click", handleLucky);

els.entityPickerInput.addEventListener("input", renderEntityPicker);

els.entityPickerInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    const first = matchEntities(state.response, els.entityPickerInput.value)[0];
    if (first) toggleEntityFilter(first.id, first.label || first.id);
});

els.onlyArticles.addEventListener("change", () => {
    if (graphTabActive() || document.getElementById("graph").hasChildNodes()) {
        renderGraphNow();
    }
});

for (const button of els.tabButtons) {
    button.addEventListener("click", () => setActiveTab(button.dataset.tab));
}

let scorePlotResizeTimer = null;
window.addEventListener("resize", () => {
    clearTimeout(scorePlotResizeTimer);
    scorePlotResizeTimer = setTimeout(() => {
        if (state.response) {
            renderScorePlot(els.scorePlot, els.scorePlotTooltip, state, { onDotClick: handleScoreDotClick });
        }
    }, 250);
});

window.addEventListener("popstate", () => {
    const params = new URLSearchParams(location.search);
    fillForm(params);
    if (params.get("query")) {
        runSearch({ push: false });
    }
});

initEvalTab();

/* ----------------------------------------------------------------------
   Bootstrap: restore a shared/searchable URL if present
   ---------------------------------------------------------------------- */

{
    const params = new URLSearchParams(location.search);
    fillForm(params);
    if (params.get("query")) {
        runSearch({ push: false });
    } else {
        renderTimelineView();
    }
}
