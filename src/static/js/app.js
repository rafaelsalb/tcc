import { searchArticles } from "./api.js";
import { computeView, renderTimeline, scrollToArticle } from "./timeline.js";
import {
    renderGraph,
    clearEntitySelection,
    getEntityArticleUrls,
} from "./graph.js";

const state = {
    response: null,
    sort: "date_desc",
    topN: null,
    entityFilter: null,
};

let graphDirty = false;

const els = {
    form: document.getElementById("search-form"),
    query: document.getElementById("query"),
    limit: document.getElementById("limit"),
    topK: document.getElementById("top_k"),
    dateFrom: document.getElementById("date_from"),
    dateTo: document.getElementById("date_to"),
    timeline: document.getElementById("timeline"),
    sortSelect: document.getElementById("sort-select"),
    topN: document.getElementById("top-n"),
    topNAll: document.getElementById("top-n-all"),
    chipSlot: document.getElementById("entity-chip-slot"),
    statStrip: document.getElementById("stat-strip"),
    toolbar: document.getElementById("timeline-toolbar"),
    statCount: document.getElementById("stat-count"),
    statSpan: document.getElementById("stat-span"),
    statAvg: document.getElementById("stat-avg"),
    statEntities: document.getElementById("stat-entities"),
    errorBanner: document.getElementById("error-banner"),
    errorText: document.getElementById("error-text"),
    errorClose: document.getElementById("error-close"),
    loadingOverlay: document.getElementById("loading-overlay"),
    onlyArticles: document.getElementById("only-articles"),
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
    return {
        query: els.query.value.trim(),
        limit: els.limit.value,
        topK: els.topK.value,
        dateFrom: els.dateFrom.value,
        dateTo: els.dateTo.value,
    };
}

function fillForm(params) {
    els.query.value = params.get("query") ?? "";
    els.limit.value = params.get("limit") ?? "";
    els.topK.value = params.get("top_k") ?? "";
    els.dateFrom.value = params.get("date_from") ?? "";
    els.dateTo.value = params.get("date_to") ?? "";
}

function pushUrl(params) {
    const qs = new URLSearchParams();
    qs.set("query", params.query);
    if (params.limit) qs.set("limit", params.limit);
    if (params.topK) qs.set("top_k", params.topK);
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
}

function renderChip() {
    els.chipSlot.replaceChildren();
    if (!state.entityFilter) return;
    const chip = document.createElement("span");
    chip.className = "entity-chip";
    chip.append(`Entidade: ${state.entityFilter.label}`);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "entity-chip-remove";
    remove.setAttribute("aria-label", "Remover filtro de entidade");
    remove.textContent = "×";
    remove.addEventListener("click", () => {
        state.entityFilter = null;
        clearEntitySelection();
        renderChip();
        renderStats();
        renderTimeline(els.timeline, state);
    });
    chip.appendChild(remove);
    els.chipSlot.appendChild(chip);
}

function syncTopNBounds() {
    const total = state.response?.articles?.length ?? 0;
    els.topN.disabled = total === 0;
    els.topNAll.disabled = total === 0;
    els.topN.min = String(Math.min(1, total));
    els.topN.max = String(Math.max(1, total));
    if (state.topN == null || state.topN > total) state.topN = Math.max(1, total);
    els.topN.value = String(state.topN);
}

function renderTimelineView() {
    renderTimeline(els.timeline, state);
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
        onEntitySelect: handleEntitySelect,
        onArticleClick: handleArticleClick,
    });
    graphDirty = false;
}

function handleEntitySelect(entity) {
    if (!entity || !state.response) {
        state.entityFilter = null;
    } else {
        const urls = getEntityArticleUrls(state.response, entity.id);
        state.entityFilter = { id: entity.id, label: entity.label, urls: new Set(urls) };
    }
    renderChip();
    renderStats();
    renderTimelineView();
}

function handleArticleClick(url) {
    setActiveTab("panel-timeline");
    let found = scrollToArticle(els.timeline, url);
    if (!found && state.entityFilter) {
        state.entityFilter = null;
        clearEntitySelection();
        renderChip();
        renderStats();
        renderTimelineView();
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
        state.entityFilter = null;
        syncTopNBounds();
        renderChip();
        renderStats();
        renderTimelineView();
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
    renderStats();
    renderTimelineView();
});

els.topN.addEventListener("change", () => {
    const total = state.response?.articles?.length ?? 0;
    let value = Number.parseInt(els.topN.value, 10);
    if (Number.isNaN(value)) value = total;
    value = Math.max(1, Math.min(value, Math.max(1, total)));
    els.topN.value = String(value);
    state.topN = value;
    renderStats();
    renderTimelineView();
});

els.topNAll.addEventListener("click", () => {
    state.topN = state.response?.articles?.length ?? 0;
    els.topN.value = String(Math.max(1, state.topN));
    renderStats();
    renderTimelineView();
});

els.onlyArticles.addEventListener("change", () => {
    if (graphTabActive() || document.getElementById("graph").hasChildNodes()) {
        renderGraphNow();
    }
});

for (const button of els.tabButtons) {
    button.addEventListener("click", () => setActiveTab(button.dataset.tab));
}

window.addEventListener("popstate", () => {
    const params = new URLSearchParams(location.search);
    fillForm(params);
    if (params.get("query")) {
        runSearch({ push: false });
    }
});

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
