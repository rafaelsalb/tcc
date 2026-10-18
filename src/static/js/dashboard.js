import { getUiState, setUiState } from "./ui_state.js";

const RANKINGS = [
    "ppr", "hybrid_max", "rrf", "cross_encoder", "fused", "mmr", "graph_rwr",
    "graph_hits", "graph_salsa", "graph_path", "graph_walk", "graph_fusion",
    "graph_hits_cross_encoder", "lexical", "vector", "ensemble_rrf",
];
const ENSEMBLE_COMPONENTS = RANKINGS.filter((ranking) => ranking !== "ensemble_rrf");
const SEEDS = ["louvain", "hits", "ppr_top10", "query_entities"];
const PRESETS = ["rapido", "balanceado", "profundo"];
const QUORUMS = [0.3, 0.5, 0.7, 0.9];
const RANKING_PALETTE = [...d3.schemeTableau10, ...d3.schemeDark2];
const COLORS = new Map(RANKINGS.map((name, index) => [name, RANKING_PALETTE[index % RANKING_PALETTE.length]]));
const SEED_INDEPENDENT = new Set(["hybrid_max", "rrf", "cross_encoder", "lexical", "vector"]);

const dashboard = {
    datasets: [], runId: null, rows: [], cursor: 0, state: null, timer: null,
    polling: false, selectedSeq: null, startedAt: null, savedFilters: null,
    restoreSelection: false, tableLimit: 200, tableSort: { key: "seq", direction: "desc" },
    multiFilters: {
        theme: { mode: "include", values: [] },
        formulation: { mode: "include", values: [] },
    },
    thresholdEnabled: false, thresholdMode: "absolute", threshold: 0.70, sdThreshold: -1,
    metricView: "raw", distributionKey: null, distributionStats: new Map(), excludedRows: [], exclusionLimit: 100,
    lastAnalyticsRenderAt: 0, analyticsRenderTimer: null, stepsRenderedSeq: null,
    incrementalRenderPending: false,
};

const ANALYTICS_RENDER_INTERVAL_MS = 3000;

const $ = (id) => document.getElementById(id);

async function api(url, options = {}) {
    let response;
    try {
        response = await fetch(url, options);
    } catch {
        throw new Error("Falha de rede ao contatar o servidor.");
    }
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || `Erro ${response.status}.`);
    return body;
}

function makeCheckGrid(container, values, defaults, labelFor = (value) => value) {
    container.replaceChildren();
    for (const value of values) {
        const label = document.createElement("label");
        label.className = "dashboard-check";
        const input = document.createElement("input");
        input.type = "checkbox";
        input.value = String(value);
        input.checked = defaults.includes(value);
        const text = document.createElement("span");
        text.textContent = labelFor(value);
        label.append(input, text);
        container.appendChild(label);
    }
}

function checkedValues(container) {
    return [...container.querySelectorAll("input:checked")].map((input) => input.value);
}

function selectedDatasetIds() {
    return checkedValues($("dashboard-theme-sets"));
}

function updateThemeSelectionSummary() {
    const selected = new Set(selectedDatasetIds());
    const themes = dashboard.datasets.filter((item) => selected.has(item.id));
    const queries = d3.sum(themes, (item) => item.count || 0);
    $("dashboard-theme-selection-summary").textContent = themes.length
        ? `${themes.length} tema(s)/snapshot(s) · até ${queries} consultas`
        : "Nenhum tema selecionado.";
}

function renderThemeChoices(selectedIds = []) {
    const selected = new Set(selectedIds);
    const groups = d3.group(dashboard.datasets, (item) => `${item.source}|${item.version_label || "Snapshot"}`);
    const container = $("dashboard-theme-sets");
    container.replaceChildren();
    const sortedGroups = [...groups].sort((a, b) => {
        const currentA = a[1].some((item) => item.is_current);
        const currentB = b[1].some((item) => item.is_current);
        return Number(currentB) - Number(currentA) || a[0].localeCompare(b[0], "pt-BR");
    });
    for (const [, items] of sortedGroups) {
        const first = items[0];
        const details = document.createElement("details");
        details.className = "dashboard-theme-source";
        details.open = Boolean(first.is_current);
        const summary = document.createElement("summary");
        summary.textContent = `${first.source} · ${first.version_label || "Snapshot"} · ${items.length} temas`;
        details.appendChild(summary);
        const selectGroup = document.createElement("button");
        selectGroup.type = "button";
        selectGroup.className = "btn-ghost dashboard-theme-select-group";
        selectGroup.textContent = first.is_current ? "Selecionar temas atuais deste conjunto" : "Selecionar este snapshot";
        selectGroup.addEventListener("click", () => {
            const ids = new Set(items.map((item) => item.id));
            for (const checkbox of container.querySelectorAll("input[type=checkbox]")) {
                if (ids.has(checkbox.value)) checkbox.checked = true;
            }
            updateThemeSelectionSummary();
            persistDashboardUI();
        });
        details.appendChild(selectGroup);
        const grid = document.createElement("div");
        grid.className = "dashboard-check-grid dashboard-theme-check-grid";
        for (const item of items) {
            const label = document.createElement("label");
            label.className = "dashboard-check";
            const input = document.createElement("input");
            input.type = "checkbox";
            input.value = item.id;
            input.checked = selected.has(item.id);
            input.addEventListener("change", () => {
                updateThemeSelectionSummary();
                persistDashboardUI();
            });
            const text = document.createElement("span");
            text.textContent = `${item.label} · ${item.count} consultas · ${item.articles ?? "—"} referências`;
            label.title = `${item.source} · ${item.version_label || "Snapshot"}`;
            label.append(input, text);
            grid.appendChild(label);
        }
        details.appendChild(grid);
        container.appendChild(details);
    }
    updateThemeSelectionSummary();
}

function initialThemeSelection(saved, datasets) {
    if (Array.isArray(saved.datasets)) {
        const currentIds = new Set(datasets.map((item) => item.id));
        const valid = saved.datasets.filter((id) => currentIds.has(id));
        if (valid.length) return valid;
    }
    // Migrate the previous single-select preference to one or more matching
    // immutable theme snapshots without exposing their internal hashes.
    if (typeof saved.dataset === "string" && saved.dataset) {
        const exact = datasets.find((item) => item.id === saved.dataset);
        if (exact) return [exact.id];
        const sourceMatch = datasets.filter((item) => item.source === saved.dataset && item.is_current);
        if (sourceMatch.length) return sourceMatch.map((item) => item.id);
        const themeMatches = datasets.filter((item) => item.id.startsWith(`${saved.dataset}::`))
            .sort((a, b) => Number(b.is_current) - Number(a.is_current));
        if (themeMatches.length) return [themeMatches[0].id];
    }
    const firstCurrent = datasets.find((item) => item.is_current);
    return firstCurrent ? [firstCurrent.id] : [];
}

function formatSeconds(value) {
    if (!Number.isFinite(Number(value))) return "—";
    const seconds = Number(value);
    return seconds < 10 ? `${seconds.toFixed(2)}s` : `${seconds.toFixed(1)}s`;
}

function formatElapsed(seconds) {
    if (!Number.isFinite(Number(seconds))) return "—";
    const whole = Math.max(0, Math.floor(Number(seconds)));
    const h = Math.floor(whole / 3600);
    const m = Math.floor((whole % 3600) / 60);
    const s = whole % 60;
    return h ? `${h}h ${m}m` : m ? `${m}m ${s}s` : `${s}s`;
}

function rawMetricValue(row) {
    const metric = $("dashboard-metric").value;
    const k = Number($("dashboard-k").value);
    if (metric === "f1" || metric === "precision" || metric === "recall") {
        return row.result.metrics?.metrics?.find((entry) => entry.k === k)?.[metric] ?? null;
    }
    const prefix = metric === "map" ? "map" : "ndcg";
    return row.result.ranking_metrics?.[`${prefix}@${k}`] ?? null;
}

function metricValue(row) {
    const value = rawMetricValue(row);
    if (dashboard.metricView !== "oracle") return value;
    const metric = $("dashboard-metric").value;
    const k = Number($("dashboard-k").value);
    if (!["precision", "recall", "f1"].includes(metric) || !Number.isFinite(value)) return null;
    const ceiling = row.result.coverage?.oracle_metrics?.find((entry) => entry.k === k)?.[metric];
    if (!Number.isFinite(ceiling) || ceiling <= 0) return null;
    // Keep values above 1 visible rather than silently clipping a diagnostic.
    return value / ceiling;
}

function metricBaseLabel() {
    return ({ f1: "F1", precision: "Precisão", recall: "Revocação", ndcg: "NDCG", map: "MAP" })[
        $("dashboard-metric").value
    ] || $("dashboard-metric").value;
}

function metricDisplayLabel() {
    const label = `${metricBaseLabel()}@${$("dashboard-k").value}`;
    return dashboard.metricView === "oracle" ? `${label} / teto do pool` : label;
}

function metricUpperBound(values) {
    if (dashboard.metricView !== "oracle") return 1;
    return Math.max(1, Math.ceil((d3.max(values) || 1) * 4) / 4);
}

function syncMetricView() {
    const supported = ["f1", "precision", "recall"].includes($("dashboard-metric").value);
    const oracleOption = $("dashboard-metric-view").querySelector('option[value="oracle"]');
    oracleOption.disabled = !supported;
    if (!supported && dashboard.metricView === "oracle") dashboard.metricView = "raw";
    $("dashboard-metric-view").value = dashboard.metricView;
}

function filtersFromUI() {
    return {
        ranking: $("dashboard-filter-ranking").value,
        seed: $("dashboard-filter-seed").value,
        preset: $("dashboard-filter-preset").value,
        quorum: $("dashboard-filter-quorum").value,
        query: $("dashboard-filter-query").value,
        theme: { mode: dashboard.multiFilters.theme.mode, values: [...dashboard.multiFilters.theme.values] },
        formulation: { mode: dashboard.multiFilters.formulation.mode, values: [...dashboard.multiFilters.formulation.values] },
    };
}

function matchesMultiFilter(value, filter) {
    const selected = filter.values;
    if (!selected.length) return true;
    const matched = selected.includes(value ?? "unspecified");
    return filter.mode === "exclude" ? !matched : matched;
}

function dimensionFilteredRows({ ignoreRanking = false } = {}) {
    const filters = filtersFromUI();
    return dashboard.rows.filter((row) => {
        const result = row.result;
        return (ignoreRanking || !filters.ranking || result.ranking === filters.ranking)
            && (!filters.seed || result.seed_method === filters.seed)
            && (!filters.preset || result.preset === filters.preset)
            && (!filters.quorum || String(result.quorum) === filters.quorum)
            && matchesMultiFilter(themeOf(row), filters.theme)
            && (!filters.query || row.evaluation_id === filters.query)
            && matchesMultiFilter(row.query_formulation || "unspecified", filters.formulation);
    });
}

function thresholdValue(row) {
    return metricValue(row);
}

function thresholdDecision(row) {
    const value = thresholdValue(row);
    if (!Number.isFinite(value)) return {
        reason: dashboard.metricView === "oracle" ? "oracle_missing" : "missing",
        value: null, zScore: null,
    };
    if (!dashboard.thresholdEnabled) return { reason: "keep", value, zScore: null };
    if (dashboard.thresholdMode === "sd") {
        const distribution = dashboard.distributionStats.get(combinationKey(row));
        if (!distribution || distribution.n < 2 || !(distribution.sd > 0)) {
            return { reason: "unscreenable", value, zScore: null };
        }
        const zScore = (value - distribution.mean) / distribution.sd;
        return { reason: zScore < dashboard.sdThreshold ? "below_sd" : "keep", value, zScore };
    }
    return { reason: value < dashboard.threshold ? "below" : "keep", value, zScore: null };
}

function thresholdFilteredRows(rows) {
    if (!dashboard.thresholdEnabled) return rows;
    return rows.filter((row) => ["keep", "unscreenable"].includes(thresholdDecision(row).reason));
}

function filteredRows(options = {}) {
    return thresholdFilteredRows(dimensionFilteredRows(options));
}

function syncThresholdControls() {
    const label = metricDisplayLabel();
    $("dashboard-threshold-enabled").checked = dashboard.thresholdEnabled;
    $("dashboard-threshold-mode").value = dashboard.thresholdMode;
    $("dashboard-absolute-threshold-controls").hidden = dashboard.thresholdMode !== "absolute";
    $("dashboard-sd-threshold-controls").hidden = dashboard.thresholdMode !== "sd";
    $("dashboard-threshold-range").value = String(dashboard.threshold);
    $("dashboard-threshold-number").value = String(dashboard.threshold.toFixed(2));
    $("dashboard-threshold-percent").value = `${(dashboard.threshold * 100).toFixed(0)}%`;
    $("dashboard-sd-threshold-range").value = String(dashboard.sdThreshold);
    $("dashboard-sd-threshold-number").value = String(dashboard.sdThreshold.toFixed(1));
    $("dashboard-sd-threshold-value").value = `${dashboard.sdThreshold.toFixed(1).replace("-", "−")}σ`;
    $("dashboard-threshold-range").disabled = !dashboard.thresholdEnabled;
    $("dashboard-threshold-number").disabled = !dashboard.thresholdEnabled;
    $("dashboard-sd-threshold-range").disabled = !dashboard.thresholdEnabled;
    $("dashboard-sd-threshold-number").disabled = !dashboard.thresholdEnabled;
    $("dashboard-threshold-metric-label").textContent = label;
    $("dashboard-threshold-metric-context").textContent = label;
}

function renderExclusionAudit(screenedRows) {
    const audit = $("dashboard-exclusion-audit");
    audit.hidden = !dashboard.thresholdEnabled;
    if (!dashboard.thresholdEnabled) {
        dashboard.excludedRows = [];
        return;
    }
    const classified = screenedRows.map((row) => ({ row, ...thresholdDecision(row) }));
    dashboard.excludedRows = classified.filter((entry) => ["missing", "oracle_missing", "below", "below_sd"].includes(entry.reason))
        .sort((a, b) => (a.reason === "missing") - (b.reason === "missing")
            || (a.value ?? -Infinity) - (b.value ?? -Infinity)
            || a.row.evaluation_id.localeCompare(b.row.evaluation_id, "pt-BR"));
    const below = dashboard.excludedRows.filter((entry) => ["below", "below_sd"].includes(entry.reason)).length;
    const missing = dashboard.excludedRows.filter((entry) => entry.reason === "missing").length;
    const noOracle = dashboard.excludedRows.filter((entry) => entry.reason === "oracle_missing").length;
    const unscreenable = classified.filter((entry) => entry.reason === "unscreenable").length;
    const kept = screenedRows.length - dashboard.excludedRows.length;
    $("dashboard-exclusion-summary-text").textContent =
        `${dashboard.excludedRows.length.toLocaleString("pt-BR")} de ${screenedRows.length.toLocaleString("pt-BR")} resultados excluídos · ${kept.toLocaleString("pt-BR")} mantidos`;
    const cutoffDescription = dashboard.thresholdMode === "sd"
        ? `z < ${dashboard.sdThreshold.toFixed(1).replace("-", "−")}σ dentro da configuração`
        : `abaixo de ${(dashboard.threshold * 100).toFixed(0)}%`;
    $("dashboard-exclusion-counts").textContent =
        `${below.toLocaleString("pt-BR")} ${cutoffDescription} · ${missing.toLocaleString("pt-BR")} sem métrica` +
        (noOracle ? ` · ${noOracle.toLocaleString("pt-BR")} sem teto do pool` : "") +
        (unscreenable ? ` · ${unscreenable.toLocaleString("pt-BR")} sem variação suficiente para z-score (mantidos)` : "");
    const combinations = d3.rollups(dashboard.excludedRows,
        (items) => ({
            cases: items.length,
            queries: new Set(items.map(({ row }) => row.evaluation_id)).size,
            themes: new Set(items.map(({ row }) => themeOf(row))).size,
            below: items.filter((entry) => ["below", "below_sd"].includes(entry.reason)).length,
            missing: items.filter((entry) => ["missing", "oracle_missing"].includes(entry.reason)).length,
        }),
        ({ row }) => [row.result.ranking, row.result.seed_method, row.result.preset,
            String(row.result.quorum), row.result.result_unit].join("|")
    ).map(([key, counts]) => ({ key, ...counts }))
        .sort((a, b) => b.cases - a.cases || a.key.localeCompare(b.key, "pt-BR"));
    const comboBody = $("dashboard-exclusion-combinations");
    comboBody.replaceChildren();
    if (!combinations.length) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 8; td.className = "dashboard-empty";
        td.textContent = "Nenhum resultado foi excluído pelos filtros atuais.";
        tr.appendChild(td); comboBody.appendChild(tr);
    } else {
        for (const combo of combinations) {
            const [ranking, seed, preset, quorum, unit] = combo.key.split("|");
            const tr = document.createElement("tr");
            const values = [ranking, seed, preset, quorum, unit, `${combo.cases} (${combo.queries} consultas)`,
                String(combo.themes), `${combo.below} abaixo · ${combo.missing} sem valor`];
            for (const value of values) {
                const td = document.createElement("td"); td.textContent = value; tr.appendChild(td);
            }
            comboBody.appendChild(tr);
        }
    }
    renderExcludedCases();
}

function renderExcludedCases() {
    const query = normalizeFilterText($("dashboard-exclusion-search").value);
    const matches = dashboard.excludedRows.filter(({ row, reason }) => normalizeFilterText([
        row.evaluation_id, themeOf(row), row.query, row.result.ranking, row.result.seed_method,
        row.result.preset, row.result.quorum, reason,
    ].join(" ")).includes(query));
    const visible = matches.slice(0, dashboard.exclusionLimit);
    $("dashboard-exclusion-result-count").textContent =
        `${matches.length.toLocaleString("pt-BR")} casos correspondem à busca · mostrando ${visible.length.toLocaleString("pt-BR")}`;
    $("dashboard-exclusion-more").hidden = visible.length >= matches.length;
    $("dashboard-exclusion-more").textContent = `Mostrar mais casos (${Math.min(100, matches.length - visible.length)} de ${matches.length - visible.length} restantes)`;
    const body = $("dashboard-excluded-results");
    body.replaceChildren();
    if (!visible.length) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 9;
        cell.className = "dashboard-empty";
        cell.textContent = matches.length ? "Nenhum caso nesta página." : "Nenhum resultado excluído para os filtros atuais.";
        row.appendChild(cell);
        body.appendChild(row);
        return;
    }
    for (const { row, reason, value } of visible) {
        const tr = document.createElement("tr");
        const metricText = value == null ? "—" : `${(value * 100).toFixed(1)}%`;
        const cause = reason === "oracle_missing" ? "Teto do pool indisponível/zero"
            : reason === "missing" ? "Métrica indisponível"
            : reason === "below_sd" ? `z=${value == null ? "—" : ((value - dashboard.distributionStats.get(combinationKey(row)).mean) / dashboard.distributionStats.get(combinationKey(row)).sd).toFixed(2)} < ${dashboard.sdThreshold.toFixed(1)}σ`
                : `Abaixo de ${(dashboard.threshold * 100).toFixed(0)}%`;
        const values = [row.evaluation_id, row.query, themeOf(row), row.result.ranking, row.result.seed_method,
            row.result.preset, String(row.result.quorum), metricText, cause];
        for (const item of values) {
            const td = document.createElement("td"); td.textContent = item; tr.appendChild(td);
        }
        body.appendChild(tr);
    }
}

function normalizeFilterText(value) {
    return String(value ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("pt-BR");
}

function syncSelectChoices(select, choices, selectedValue) {
    const desired = new Map(choices.map(({ value, label }) => [String(value), String(label)]));
    const existing = [...select.options];
    const existingMatches = existing.every((option) => desired.get(option.value) === option.textContent);
    const focused = document.activeElement === select;
    if (existingMatches) {
        const existingValues = new Set(existing.map((option) => option.value));
        const additions = choices.filter((choice) => !existingValues.has(String(choice.value)));
        for (const choice of additions) {
            const option = new Option(String(choice.label), String(choice.value));
            if (!choice.value) {
                select.add(option, 0);
                continue;
            }
            const next = [...select.options].findIndex((item) => item.value
                && String(item.textContent).localeCompare(String(choice.label), "pt-BR", { numeric: true }) > 0);
            select.add(option, next < 0 ? undefined : next);
        }
    } else {
        select.replaceChildren(...choices.map((choice) => new Option(String(choice.label), String(choice.value))));
        if (focused) select.focus({ preventScroll: true });
    }
    const nextValue = String(selectedValue ?? "");
    select.value = desired.has(nextValue) ? nextValue : "";
}

function updateFilterOptions(id, values, placeholder, current) {
    const select = $(id);
    const unique = [...new Set(values.filter((value) => value != null && value !== ""))]
        .map(String).sort((a, b) => a.localeCompare(b, "pt-BR", { numeric: true }));
    const choices = [{ label: placeholder, value: "" }, ...unique.map((value) => ({ label: value, value }))];
    if (current && !unique.includes(String(current))) {
        choices.push({ label: `${current} · sem resultados neste filtro`, value: current });
    }
    syncSelectChoices(select, choices, current);
}

function facetFilterConfig(type) {
    return type === "theme"
        ? { options: "dashboard-filter-theme-options", summary: "dashboard-filter-theme-summary" }
        : { options: "dashboard-filter-formulation-options", summary: "dashboard-filter-formulation-summary" };
}

function updateFacetSummary(type) {
    const filter = dashboard.multiFilters[type];
    const label = type === "theme" ? "Temas" : "Formulações";
    const summary = $(facetFilterConfig(type).summary);
    summary.textContent = filter.values.length
        ? `${label} · ${filter.mode === "exclude" ? "excluindo" : "incluindo"} ${filter.values.length}`
        : `${label} · todos`;
}

function syncFacetOptions(type, values) {
    const filter = dashboard.multiFilters[type];
    const container = $(facetFilterConfig(type).options);
    const available = [...new Set(values.filter((value) => value != null && value !== "").map(String))]
        .sort((a, b) => a.localeCompare(b, "pt-BR", { numeric: true }));
    const desired = [...new Set([...available, ...filter.values])].sort((a, b) =>
        a.localeCompare(b, "pt-BR", { numeric: true }));
    const existing = new Map([...container.querySelectorAll("input[type=checkbox]")]
        .map((input) => [input.value, input.closest("label")]));
    const desiredSet = new Set(desired);
    const canAppend = [...existing.keys()].every((value) => desiredSet.has(value));
    if (!canAppend) container.replaceChildren();
    const present = new Set([...container.querySelectorAll("input[type=checkbox]")].map((input) => input.value));
    for (const value of desired) {
        let label = present.has(value) ? existing.get(value) : null;
        if (!label) {
            label = document.createElement("label");
            label.className = "dashboard-check";
            const input = document.createElement("input");
            input.type = "checkbox";
            input.value = value;
            input.addEventListener("change", () => {
                filter.values = checkedValues(container);
                updateFacetSummary(type);
                dashboard.tableLimit = 200;
                renderDashboard();
                persistDashboardUI();
            });
            const text = document.createElement("span");
            text.textContent = value;
            label.append(input, text);
            container.appendChild(label);
            present.add(value);
        }
        const checkbox = label.querySelector("input");
        checkbox.checked = filter.values.includes(value);
        const text = label.querySelector("span");
        text.textContent = available.includes(value) ? value : `${value} · sem resultados neste recorte`;
    }
    updateFacetSummary(type);
}

function restoreFacetFilter(savedValue) {
    if (typeof savedValue === "string") return { mode: "include", values: savedValue ? [savedValue] : [] };
    if (savedValue && typeof savedValue === "object") {
        return {
            mode: savedValue.mode === "exclude" ? "exclude" : "include",
            values: Array.isArray(savedValue.values) ? savedValue.values.map(String) : [],
        };
    }
    return { mode: "include", values: [] };
}

function refreshFilterOptions() {
    const restored = dashboard.savedFilters || {};
    const current = {
        ranking: $("dashboard-filter-ranking").value || restored.ranking || "",
        seed: $("dashboard-filter-seed").value || restored.seed || "",
        preset: $("dashboard-filter-preset").value || restored.preset || "",
        quorum: $("dashboard-filter-quorum").value || restored.quorum || "",
        query: $("dashboard-filter-query").value || restored.query || "",
    };
    const results = dashboard.rows.map((row) => row.result);
    updateFilterOptions("dashboard-filter-ranking", results.map((row) => row.ranking), "Todos", current.ranking);
    updateFilterOptions("dashboard-filter-seed", results.map((row) => row.seed_method), "Todas", current.seed);
    updateFilterOptions("dashboard-filter-preset", results.map((row) => row.preset), "Todos", current.preset);
    updateFilterOptions("dashboard-filter-quorum", results.map((row) => row.quorum), "Todos", current.quorum);
    updateFilterOptions("dashboard-filter-query", dashboard.rows.map((row) => row.evaluation_id), "Todas", current.query);
    syncFacetOptions("theme", dashboard.rows.map((row) => themeOf(row)));
    syncFacetOptions("formulation", dashboard.rows.map((row) => row.query_formulation || "unspecified"));
    const savedBaseline = $("dashboard-baseline-ranking").value
        || dashboard.savedFilters?.baseline || getUiState().batchDashboard?.baseline || "hybrid_max";
    updateFilterOptions("dashboard-baseline-ranking", results.map((row) => row.ranking), "Ranking de referência", savedBaseline);
    if (!$("dashboard-baseline-ranking").value && results.length) {
        $("dashboard-baseline-ranking").value = results.some((row) => row.ranking === "hybrid_max")
            ? "hybrid_max" : results[0].ranking;
    }
    dashboard.savedFilters = null;
}

function renderProgress() {
    const state = dashboard.state;
    if (!state) {
        $("dashboard-progress-wrap").hidden = true;
        $("dashboard-status").textContent = "Pronto";
        return;
    }
    const progress = state.progress || {};
    const completed = progress.completed || 0;
    const total = progress.total || 0;
    const terminal = ["completed", "failed", "interrupted"].includes(state.status);
    const endedAt = Date.parse(state.completed_at || (terminal ? state.updated_at : ""));
    const elapsed = dashboard.startedAt
        ? (terminal && Number.isFinite(endedAt) ? endedAt - dashboard.startedAt : Date.now() - dashboard.startedAt) / 1000
        : null;
    $("dashboard-progress-wrap").hidden = false;
    $("dashboard-progress").max = Math.max(1, total);
    $("dashboard-progress").value = Math.min(completed, total);
    $("dashboard-progress-label").textContent = `${completed.toLocaleString("pt-BR")} / ${total.toLocaleString("pt-BR")}`;
    const current = progress.current;
    $("dashboard-progress-current").textContent = current
        ? [current.evaluation_id, current.preset, `q=${current.quorum}`, current.ranking, current.seed_method].filter(Boolean).join(" · ")
        : (progress.phase || "");
    if (elapsed != null && completed > 0 && completed < total) {
        const eta = elapsed / completed * (total - completed);
        $("dashboard-progress-current").textContent += ` · ETA ${formatElapsed(eta)}`;
    }
    $("dashboard-status").textContent = state.status;
    $("dashboard-status").className = `dashboard-status-badge is-${state.status}`;
    $("dashboard-kpi-completed").textContent = `${completed.toLocaleString("pt-BR")} / ${total.toLocaleString("pt-BR")}`;
    $("dashboard-kpi-elapsed").textContent = formatElapsed(elapsed);
    $("dashboard-kpi-elapsed-note").textContent = terminal
        ? "duração da rodada" : "tempo decorrido";
}

function themeOf(row) {
    return row.evaluation_id.split("__", 1)[0];
}

function seedKey(row) {
    return SEED_INDEPENDENT.has(row.result.ranking) ? "none" : row.result.seed_method;
}

function combinationKey(row) {
    const result = row.result;
    return [result.ranking, seedKey(row), result.preset, result.quorum, result.result_unit].join("|");
}

function combinationLabel(combo) {
    const seed = combo.seed_method === "none" ? "sem seed" : combo.seed_method;
    return `${combo.ranking} · ${seed} · ${combo.preset} · q=${combo.quorum} · ${combo.result_unit}`;
}

function uniqueQueryRows(rows, valueFn = metricValue) {
    const seen = new Set();
    return rows.filter((row) => {
        if (!Number.isFinite(valueFn(row))) return false;
        const key = `${row.evaluation_id}|${combinationKey(row)}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
    });
}

function summarizeGroups(rows, groupKeyFn, valueFn = metricValue) {
    const grouped = new Map();
    for (const row of uniqueQueryRows(rows, valueFn)) {
        const key = groupKeyFn(row);
        if (!grouped.has(key)) grouped.set(key, { rows: [], themes: new Map() });
        const group = grouped.get(key);
        group.rows.push(row);
        const theme = themeOf(row);
        if (!group.themes.has(theme)) group.themes.set(theme, new Map());
        group.themes.get(theme).set(row.evaluation_id, valueFn(row));
    }
    return [...grouped].map(([key, group]) => {
        const themeValues = [...group.themes.values()].map((queries) => d3.mean([...queries.values()])).sort(d3.ascending);
        const first = group.rows[0].result;
        return {
            key, mean: d3.mean(themeValues), median: d3.median(themeValues),
            q1: d3.quantile(themeValues, 0.25), q3: d3.quantile(themeValues, 0.75),
            themeCount: themeValues.length,
            queryCount: new Set(group.rows.map((row) => row.evaluation_id)).size,
            ranking: first.ranking, seed_method: seedKey(group.rows[0]), preset: first.preset,
            quorum: first.quorum, result_unit: first.result_unit,
        };
    }).filter((entry) => Number.isFinite(entry.mean));
}

function summarizeCombinations(rows) {
    return summarizeGroups(rows, combinationKey);
}

function macroAverage(rows, valueFn) {
    const observations = uniqueQueryRows(rows, valueFn);
    const byTheme = d3.rollups(observations, (items) => {
        const byQuery = d3.rollups(items, (queryRows) => d3.mean(queryRows, valueFn), (row) => row.evaluation_id);
        return d3.mean(byQuery, (entry) => entry[1]);
    }, themeOf);
    return {
        mean: d3.mean(byTheme, (entry) => entry[1]),
        themeCount: byTheme.length,
        queryCount: new Set(observations.map((row) => row.evaluation_id)).size,
    };
}

function renderKpis(rows) {
    const quality = macroAverage(rows, metricValue);
    const coverage = macroAverage(rows, (row) => row.result.coverage?.reference_pool_recall);
    const metricLabel = metricDisplayLabel();
    $("dashboard-kpi-quality-label").textContent = `${metricLabel} · média macro`;
    $("dashboard-kpi-quality").textContent = Number.isFinite(quality.mean) ? `${(quality.mean * 100).toFixed(1)}%` : "—";
    $("dashboard-kpi-coverage").textContent = Number.isFinite(coverage.mean) ? `${(coverage.mean * 100).toFixed(1)}%` : "—";
    $("dashboard-kpi-quality-note").textContent = `${quality.themeCount} temas · ${quality.queryCount} consultas distintas`;
    $("dashboard-kpi-coverage-note").textContent = `${coverage.themeCount} temas · ${coverage.queryCount} consultas distintas`;
    const partial = ["queued", "running"].includes(dashboard.state?.status) ? "Valores parciais durante a execução. " : "";
    $("dashboard-summary-context").textContent = partial +
        `Média macro das configurações incluídas pelos filtros: cada consulta contribui igualmente dentro do tema e cada tema tem o mesmo peso. ${metricLabel}; ` +
        `n=${quality.queryCount} consultas em ${quality.themeCount} temas. O IQR nos gráficos descreve a variação observada entre temas; não é intervalo de confiança.`;
}

function renderInsights(rows) {
    const entries = summarizeCombinations(rows).sort((a, b) => b.mean - a.mean);
    const slot = $("dashboard-insight-findings");
    if (!entries.length) {
        slot.textContent = "Aguardando resultados suficientes para resumir as configurações.";
        return;
    }
    const maximumThemeCount = Math.max(...entries.map((entry) => entry.themeCount));
    const comparable = entries.filter((entry) => entry.themeCount === maximumThemeCount);
    const best = comparable[0];
    const mostConsistent = [...comparable].sort((a, b) => (a.q3 - a.q1) - (b.q3 - b.q1))[0];
    const spread = Math.max(0, best.q3 - best.q1);
    const spreadUnit = dashboard.metricView === "oracle" ? "p.p. do teto" : "p.p.";
    const partial = ["queued", "running"].includes(dashboard.state?.status) ? "Resumo provisório: a rodada ainda está em andamento. " : "";
    slot.textContent = partial + `Para ${metricDisplayLabel()}, entre os grupos com cobertura igual (${maximumThemeCount} temas), maior média macro: ${combinationLabel(best)} ` +
        `(${(best.mean * 100).toFixed(1)}%). Menor IQR observado: ` +
        `${combinationLabel(mostConsistent)} (${((mostConsistent.q3 - mostConsistent.q1) * 100).toFixed(1)} ${spreadUnit}). ` +
        `Isto é descritivo, não um teste de significância; o melhor grupo tem IQR de ${(spread * 100).toFixed(1)} ${spreadUnit}.`;
}

function chartBase(containerId, height = 300, minWidth = 320) {
    const container = $(containerId);
    container.replaceChildren();
    const width = Math.max(320, container.clientWidth || 640, minWidth);
    const margin = { top: 12, right: 18, bottom: 48, left: 52 };
    const svg = d3.select(container).append("svg").attr("width", width).attr("height", height)
        .attr("viewBox", `0 0 ${width} ${height}`).attr("role", "group");
    return { container, width, height, margin, svg,
        innerWidth: width - margin.left - margin.right,
        innerHeight: height - margin.top - margin.bottom };
}

function buildMetricDistributions(rows) {
    const groups = d3.group(
        uniqueQueryRows(rows).filter((row) => Number.isFinite(metricValue(row))),
        combinationKey,
    );
    return new Map([...groups].map(([key, items]) => {
        const values = items.map(metricValue);
        const first = items[0];
        return [key, {
            key, values, n: values.length, mean: d3.mean(values), sd: d3.deviation(values) ?? 0,
            median: d3.median(values), min: d3.min(values), max: d3.max(values),
            queryCount: new Set(items.map((row) => row.evaluation_id)).size,
            themeCount: new Set(items.map(themeOf)).size,
            ranking: first.result.ranking, seed_method: seedKey(first),
            preset: first.result.preset, quorum: first.result.quorum,
            result_unit: first.result.result_unit,
        }];
    }));
}

function distributionLabel(summary) {
    return combinationLabel(summary);
}

function renderMetricDistribution(rows) {
    dashboard.distributionStats = buildMetricDistributions(rows);
    const select = $("dashboard-distribution-config");
    const previous = dashboard.distributionKey || select.value;
    const entries = [...dashboard.distributionStats.values()].sort((a, b) =>
        distributionLabel(a).localeCompare(distributionLabel(b), "pt-BR"));
    const selected = entries.some((entry) => entry.key === previous) ? previous : (entries[0]?.key || "");
    syncSelectChoices(select, [
        { label: "Selecione uma configuração", value: "" },
        ...entries.map((entry) => ({ label: distributionLabel(entry), value: entry.key })),
    ], selected);
    dashboard.distributionKey = select.value || null;

    const metric = metricDisplayLabel();
    const chart = chartBase("dashboard-metric-distribution", 330, 760);
    chart.container.classList.add("dashboard-chart-scroll-x");
    const summary = dashboard.distributionStats.get(dashboard.distributionKey);
    if (!summary) {
        $("dashboard-distribution-caption").textContent = `Sem valores disponíveis para ${metric} nos filtros atuais.`;
        return emptyChart(chart, "Aguardando valores de métrica.");
    }
    const incomplete = summary.n < 2 || !(summary.sd > 0);
    const zCut = summary.mean + dashboard.sdThreshold * summary.sd;
    $("dashboard-distribution-caption").textContent =
        `${distributionLabel(summary)} · n=${summary.queryCount} consultas em ${summary.themeCount} temas · ` +
        `média ${(summary.mean * 100).toFixed(1)}% · desvio padrão amostral ${(summary.sd * 100).toFixed(1)} p.p. · ` +
        `mediana ${(summary.median * 100).toFixed(1)}%${incomplete ? " · amostra sem variação suficiente para z-score" : ""}. ` +
        `Distribuição descritiva; não é teste de significância.`;

    const margin = { top: 18, right: 24, bottom: 46, left: 54 };
    const width = chart.width - margin.left - margin.right;
    const height = chart.height - margin.top - margin.bottom;
    const domainMax = dashboard.metricView === "oracle"
        ? Math.max(1, Math.ceil((d3.max(summary.values) || 1) * 10) / 10) : 1;
    const bins = d3.bin().domain([0, domainMax]).thresholds(20)(summary.values);
    const x = d3.scaleLinear().domain([0, domainMax]).range([0, width]);
    const y = d3.scaleLinear().domain([0, Math.max(1, d3.max(bins, (bin) => bin.length) || 0)]).nice().range([height, 0]);
    const g = chart.svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
    chart.svg.attr("aria-label", `Distribuição de ${metric} para ${distributionLabel(summary)}. n=${summary.queryCount} consultas, média ${(summary.mean * 100).toFixed(1)}%, desvio padrão ${(summary.sd * 100).toFixed(1)} pontos percentuais.`);
    g.append("g").attr("transform", `translate(0,${height})`).call(d3.axisBottom(x).ticks(10, "%"));
    g.append("g").call(d3.axisLeft(y).ticks(5, "d"));
    g.selectAll("rect.metric-bin").data(bins).join("rect")
        .attr("class", "metric-bin")
        .attr("x", (bin) => x(bin.x0) + 1)
        .attr("y", (bin) => y(bin.length))
        .attr("width", (bin) => Math.max(0, x(bin.x1) - x(bin.x0) - 2))
        .attr("height", (bin) => height - y(bin.length))
        .attr("fill", "#a5b4fc").attr("stroke", "#4f46e5").attr("stroke-width", 0.7)
        .attr("tabindex", 0).attr("role", "img")
        .attr("aria-label", (bin) => `${(bin.x0 * 100).toFixed(0)} a ${(bin.x1 * 100).toFixed(0)} por cento: ${bin.length} consultas.`)
        .append("title").text((bin) => `${(bin.x0 * 100).toFixed(0)}–${(bin.x1 * 100).toFixed(0)}%: ${bin.length} consultas`);

    const markers = [
        { label: "Média", value: summary.mean, color: "#4338ca", dash: null },
        { label: "Média − 1σ", value: summary.mean - summary.sd, color: "#64748b", dash: "4 3" },
        { label: "Média + 1σ", value: summary.mean + summary.sd, color: "#64748b", dash: "4 3" },
    ];
    if (dashboard.thresholdEnabled) {
        markers.push(dashboard.thresholdMode === "sd"
            ? { label: `Corte z=${dashboard.sdThreshold.toFixed(1)}σ`, value: zCut, color: "#d97706", dash: "2 2" }
            : { label: `Piso ${(dashboard.threshold * 100).toFixed(0)}%`, value: dashboard.threshold, color: "#d97706", dash: "2 2" });
    }
    for (const marker of markers) {
        const markerX = x(Math.min(domainMax, Math.max(0, marker.value)));
        g.append("line").attr("x1", markerX).attr("x2", markerX)
            .attr("y1", 0).attr("y2", height)
            .attr("stroke", marker.color).attr("stroke-width", marker.label === "Média" ? 2 : 1.4)
            .attr("stroke-dasharray", marker.dash);
    }
    const legend = document.createElement("div"); legend.className = "dashboard-chart-legend";
    for (const marker of markers) {
        const item = document.createElement("span"); item.className = "dashboard-legend-item";
        const swatch = document.createElement("i"); swatch.className = "dashboard-line-swatch";
        swatch.style.borderTopColor = marker.color;
        swatch.style.borderTopStyle = marker.dash ? "dashed" : "solid";
        const label = document.createElement("span"); label.textContent = marker.label;
        item.append(swatch, label); legend.appendChild(item);
    }
    chart.container.appendChild(legend);
}

function addRankingLegend(container, rankings) {
    const unique = [...new Set(rankings)].sort((a, b) => a.localeCompare(b, "en"));
    if (!unique.length) return;
    const legend = document.createElement("div");
    legend.className = "dashboard-chart-legend";
    legend.setAttribute("aria-label", "Legenda de rankings");
    for (const ranking of unique) {
        const item = document.createElement("span");
        item.className = "dashboard-legend-item";
        const swatch = document.createElement("i");
        swatch.style.background = COLORS.get(ranking) || "#64748b";
        const label = document.createElement("span");
        label.textContent = ranking;
        item.append(swatch, label);
        legend.appendChild(item);
    }
    container.appendChild(legend);
}

function renderCombinationLeaderboard(rows) {
    const combos = summarizeCombinations(rows).sort((a, b) => b.mean - a.mean);
    const showAll = $("dashboard-show-all-combinations").checked;
    const selected = showAll || combos.length <= 20
        ? combos
        : [...combos.slice(0, 10), ...combos.slice(-10).reverse()];
    let note = null;
    if (!showAll && combos.length > selected.length) {
        note = document.createElement("p");
        note.className = "dashboard-chart-note";
        note.textContent = `Exibindo 10 maiores e 10 menores de ${combos.length} grupos. Marque “Mostrar todos” para inspecionar o restante.`;
    }
    const height = Math.max(340, selected.length * 25 + 78);
    const chart = chartBase("dashboard-quality-latency", height, 720);
    if (!selected.length) return emptyChart(chart, "Aguardando métricas.");
    chart.container.classList.add("dashboard-chart-scroll-x");
    chart.svg.attr("aria-label", `Média macro de ${metricDisplayLabel()} por configuração; ponto é a média entre temas e intervalo é o IQR observado entre temas.`);
    if (note) chart.container.appendChild(note);
    chart.container.style.maxHeight = showAll ? "680px" : "none";
    chart.container.style.overflowY = "auto";
    const margin = { top: 12, right: 20, bottom: 38, left: Math.min(330, Math.max(210, chart.width * 0.42)) };
    const width = chart.width - margin.left - margin.right;
    const innerHeight = chart.height - margin.top - margin.bottom;
    const x = d3.scaleLinear().domain([0, metricUpperBound(selected.map((entry) => entry.mean))]).range([0, width]);
    const y = d3.scaleBand().domain(selected.map((entry) => entry.key)).range([0, innerHeight]).padding(0.28);
    const labels = new Map(selected.map((entry) => [entry.key, combinationLabel(entry)]));
    const g = chart.svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
    g.append("g").attr("transform", `translate(0,${innerHeight})`).call(d3.axisBottom(x).ticks(5, "%"));
    g.append("g").call(d3.axisLeft(y).tickFormat((key) => labels.get(key)).tickSize(0))
        .selectAll("text").attr("font-size", 9);
    g.append("text").attr("class", "dashboard-axis-label").attr("x", width / 2)
        .attr("y", innerHeight + 31).attr("text-anchor", "middle")
        .text(`${metricDisplayLabel()} · média macro por tema`);
    const marks = g.selectAll("g.combo-mark").data(selected).join("g").attr("class", "combo-mark");
    marks.append("line").attr("x1", (entry) => x(entry.q1)).attr("x2", (entry) => x(entry.q3))
        .attr("y1", (entry) => y(entry.key) + y.bandwidth() / 2)
        .attr("y2", (entry) => y(entry.key) + y.bandwidth() / 2)
        .attr("stroke", (entry) => COLORS.get(entry.ranking) || "#64748b").attr("stroke-width", 5).attr("stroke-linecap", "round");
    marks.append("circle").attr("cx", (entry) => x(entry.mean))
        .attr("cy", (entry) => y(entry.key) + y.bandwidth() / 2).attr("r", 5)
        .attr("fill", (entry) => COLORS.get(entry.ranking) || "#64748b")
        .attr("stroke", "white").attr("stroke-width", 1)
        .attr("tabindex", 0).attr("role", "img")
        .attr("aria-label", (entry) => `${combinationLabel(entry)}: média ${(entry.mean * 100).toFixed(1)}%, mediana ${(entry.median * 100).toFixed(1)}%, intervalo interquartil ${(entry.q1 * 100).toFixed(1)}–${(entry.q3 * 100).toFixed(1)}%, ${entry.themeCount} temas e ${entry.queryCount} consultas.`)
            .append("title").text((entry) => `${combinationLabel(entry)} · média macro ${(entry.mean * 100).toFixed(1)}%, mediana ${(entry.median * 100).toFixed(1)}%, IQR entre temas ${(entry.q1 * 100).toFixed(1)}–${(entry.q3 * 100).toFixed(1)}% (${entry.themeCount} temas, ${entry.queryCount} consultas)`);
    addRankingLegend(chart.container, selected.map((entry) => entry.ranking));
}

function renderHeatmap(rows) {
    const cells = summarizeGroups(rows, (row) => `${row.result.ranking}|${seedKey(row)}|${row.result.preset}|${row.result.quorum}`)
        .map((entry) => {
            const [ranking, seed, preset, quorum] = entry.key.split("|");
            return { ...entry, ranking, seed, preset, quorum,
                combination: `${ranking}|${seed}`, parameters: `${preset}|${quorum}` };
        });
    const rankOrder = new Map(RANKINGS.map((ranking, index) => [ranking, index]));
    const seedOrder = new Map([["none", 0], ...SEEDS.map((seed, index) => [seed, index + 1])]);
    const rowKeys = [...new Set(cells.map((cell) => cell.combination))].sort((a, b) => {
        const [rankA, seedA] = a.split("|"); const [rankB, seedB] = b.split("|");
        return (rankOrder.get(rankA) ?? 999) - (rankOrder.get(rankB) ?? 999)
            || (seedOrder.get(seedA) ?? 999) - (seedOrder.get(seedB) ?? 999);
    });
    const columns = PRESETS.flatMap((preset) => QUORUMS
        .map((quorum) => `${preset}|${quorum}`)
        .filter((key) => cells.some((cell) => cell.parameters === key)));
    const chartHeight = Math.max(360, rowKeys.length * 22 + 80);
    const chart = chartBase("dashboard-heatmap", chartHeight, 760);
    if (!cells.length) return emptyChart(chart, "Aguardando resultados.");
    chart.container.classList.add("dashboard-chart-scroll-x");
    const margin = { top: 12, right: 12, bottom: 86, left: 205 };
    const width = chart.width - margin.left - margin.right;
    const height = chart.height - margin.top - margin.bottom;
    const x = d3.scaleBand().domain(columns).range([0, width]).padding(0.06);
    const y = d3.scaleBand().domain(rowKeys).range([0, height]).padding(0.06);
    const rowLabel = (key) => {
        const [ranking, seed] = key.split("|");
        return `${ranking} · ${seed === "none" ? "sem seed" : seed}`;
    };
    const columnLabel = (key) => {
        const [preset, quorum] = key.split("|");
        return `${preset} · q=${quorum}`;
    };
    const colorMax = metricUpperBound(cells.map((cell) => cell.mean));
    const color = d3.scaleSequential(d3.interpolateBlues).domain([0, colorMax]);
    const g = chart.svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
    chart.svg.attr("aria-label", `Mapa de calor de ${metricDisplayLabel()} por ranking, seed, preset e quorum.`);
    g.append("g").attr("transform", `translate(0,${height})`).call(d3.axisBottom(x).tickSize(0))
        .selectAll("text").text(columnLabel).attr("transform", "rotate(-38)")
        .style("text-anchor", "end").attr("dx", "-0.6em").attr("dy", "0.15em");
    g.append("g").call(d3.axisLeft(y).tickSize(0).tickFormat(rowLabel));
    g.selectAll("rect").data(cells).join("rect")
        .attr("x", (cell) => x(cell.parameters)).attr("y", (cell) => y(cell.combination))
        .attr("width", x.bandwidth()).attr("height", y.bandwidth())
        .attr("rx", 3).attr("fill", (cell) => color(cell.mean))
        .attr("tabindex", 0).attr("role", "img")
        .attr("aria-label", (cell) => `${rowLabel(cell.combination)} · ${columnLabel(cell.parameters)}: média macro ${(cell.mean * 100).toFixed(1)}%, ${cell.themeCount} temas e ${cell.queryCount} consultas.`)
        .append("title").text((cell) => `${rowLabel(cell.combination)} · ${columnLabel(cell.parameters)}: média macro ${(cell.mean * 100).toFixed(1)}%, mediana ${(cell.median * 100).toFixed(1)}%, IQR entre temas ${(cell.q1 * 100).toFixed(1)}–${(cell.q3 * 100).toFixed(1)}% (${cell.themeCount} temas, ${cell.queryCount} consultas)`);
    g.selectAll("text.cell-label").data(cells).join("text").attr("class", "cell-label")
        .attr("x", (cell) => x(cell.parameters) + x.bandwidth() / 2)
        .attr("y", (cell) => y(cell.combination) + y.bandwidth() / 2 + 4)
        .attr("text-anchor", "middle").attr("font-size", 10).attr("fill", (cell) => cell.mean > colorMax * 0.58 ? "white" : "#243247")
        .text((cell) => `${(cell.mean * 100).toFixed(0)}%`);
    const legend = document.createElement("div"); legend.className = "dashboard-color-scale";
    const low = document.createElement("span"); low.textContent = "0%";
    const ramp = document.createElement("i"); ramp.setAttribute("aria-label", `Escala sequencial de 0 a ${(colorMax * 100).toFixed(0)} por cento`);
    const high = document.createElement("span"); high.textContent = `${(colorMax * 100).toFixed(0)}%`;
    legend.append(low, ramp, high); chart.container.appendChild(legend);
}

function renderCoverage(rows) {
    const data = uniqueQueryRows(rows).map((row) => ({ row, x: row.result.coverage?.reference_pool_recall,
        y: metricValue(row) })).filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
    const chart = chartBase("dashboard-coverage");
    if (!data.length) return emptyChart(chart, "Aguardando dados de cobertura.");
    const x = d3.scaleLinear().domain([0, 1]).range([0, chart.innerWidth]);
    const yMax = metricUpperBound(data.map((point) => point.y));
    const y = d3.scaleLinear().domain([0, yMax]).range([chart.innerHeight, 0]);
    const g = chart.svg.append("g").attr("transform", `translate(${chart.margin.left},${chart.margin.top})`);
    chart.svg.attr("aria-label", `Dispersão: cobertura da referência no pool versus ${metricDisplayLabel()}.`);
    g.append("g").attr("transform", `translate(0,${chart.innerHeight})`).call(d3.axisBottom(x).ticks(5, "%"));
    g.append("g").call(d3.axisLeft(y).ticks(5, "%"));
    g.append("text").attr("class", "dashboard-axis-label").attr("x", chart.innerWidth / 2)
        .attr("y", chart.innerHeight + 40).attr("text-anchor", "middle").text("Recall da referência no pool");
    g.append("text").attr("class", "dashboard-axis-label").attr("transform", "rotate(-90)")
        .attr("x", -chart.innerHeight / 2).attr("y", -39).attr("text-anchor", "middle")
        .text(metricDisplayLabel());
    const points = g.selectAll("circle").data(data).join("circle")
        .attr("cx", (point) => x(point.x)).attr("cy", (point) => y(point.y)).attr("r", 4.5)
        .attr("fill", (point) => COLORS.get(point.row.result.ranking) || "#64748b")
        .attr("fill-opacity", 0.55).attr("stroke", "#fff").attr("stroke-width", 0.7)
        .attr("tabindex", 0).attr("role", "img")
        .attr("aria-label", (point) => `${point.row.evaluation_id}; ${point.row.result.ranking}, ${point.row.result.seed_method}, ${point.row.result.preset}, quorum ${point.row.result.quorum}; cobertura ${(point.x * 100).toFixed(1)}%, métrica ${(point.y * 100).toFixed(1)}%.`);
    points.append("title").text((point) => `${point.row.evaluation_id} · ${point.row.result.ranking}/${point.row.result.seed_method} · ${point.row.result.preset} · q=${point.row.result.quorum}: cobertura ${(point.x * 100).toFixed(1)}%, ${metricDisplayLabel()} ${(point.y * 100).toFixed(1)}%`);
    addRankingLegend(chart.container, data.map((point) => point.row.result.ranking));
}

function renderPerformanceByTheme(rows) {
    const observations = uniqueQueryRows(rows);
    const cells = d3.rollups(observations,
        (items) => {
            const queries = d3.rollups(items, (queryRows) => d3.mean(queryRows, metricValue), (row) => row.evaluation_id);
            const values = queries.map((entry) => entry[1]).sort(d3.ascending);
            return { mean: d3.mean(values), median: d3.median(values), q1: d3.quantile(values, 0.25),
                q3: d3.quantile(values, 0.75), queryCount: queries.length };
        }, themeOf, (row) => row.result.ranking);
    const data = cells.flatMap(([theme, rankings]) => rankings.map(([ranking, stats]) => ({ theme, ranking, ...stats })));
    const themes = [...new Set(data.map((cell) => cell.theme))]
        .sort((a, b) => a.localeCompare(b, "pt-BR", { numeric: true }));
    const rankings = RANKINGS.filter((ranking) => data.some((cell) => cell.ranking === ranking));
    const height = Math.max(300, themes.length * 34 + 100);
    const chart = chartBase("dashboard-run-timeline", height, 920);
    if (!data.length || !themes.length) return emptyChart(chart, "Aguardando métricas por tema.");
    chart.container.classList.add("dashboard-chart-scroll-x");
    const margin = { top: 12, right: 15, bottom: 90, left: 180 };
    const width = Math.max(80, chart.width - margin.left - margin.right);
    const chartHeight = chart.height - margin.top - margin.bottom;
    const x = d3.scaleBand().domain(rankings).range([0, width]).padding(0.06);
    const y = d3.scaleBand().domain(themes).range([0, chartHeight]).padding(0.06);
    const colorMax = metricUpperBound(data.map((cell) => cell.mean));
    const color = d3.scaleSequential(d3.interpolateBlues).domain([0, colorMax]);
    const g = chart.svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
    chart.svg.attr("aria-label", `Mapa de calor de ${metricDisplayLabel()} por tema e ranking.`);
    g.append("g").attr("transform", `translate(0,${chartHeight})`).call(d3.axisBottom(x).tickSize(0))
        .selectAll("text").attr("transform", "rotate(-40)").style("text-anchor", "end").attr("dx", "-0.6em").attr("dy", "0.15em");
    g.append("g").call(d3.axisLeft(y).tickSize(0));
    const marks = g.selectAll("rect").data(data).join("rect")
        .attr("x", (cell) => x(cell.ranking)).attr("y", (cell) => y(cell.theme))
        .attr("width", x.bandwidth()).attr("height", y.bandwidth()).attr("rx", 3)
        .attr("fill", (cell) => color(cell.mean)).attr("tabindex", 0).attr("role", "img")
        .attr("aria-label", (cell) => `${cell.theme}, ${cell.ranking}: média ${(cell.mean * 100).toFixed(1)}%, ${cell.queryCount} consultas.`);
    marks.append("title").text((cell) => `${cell.theme} · ${cell.ranking}: média ${(cell.mean * 100).toFixed(1)}%, mediana ${(cell.median * 100).toFixed(1)}%, IQR ${(cell.q1 * 100).toFixed(1)}–${(cell.q3 * 100).toFixed(1)}% (${cell.queryCount} consultas)`);
    g.selectAll("text.theme-cell-label").data(data).join("text").attr("class", "theme-cell-label")
        .attr("x", (cell) => x(cell.ranking) + x.bandwidth() / 2).attr("y", (cell) => y(cell.theme) + y.bandwidth() / 2 + 4)
        .attr("text-anchor", "middle").attr("font-size", 9).attr("fill", (cell) => cell.mean > colorMax * 0.58 ? "white" : "#243247")
        .text((cell) => `${(cell.mean * 100).toFixed(0)}%`);
    const legend = document.createElement("div"); legend.className = "dashboard-color-scale";
    legend.innerHTML = `<span>0%</span><i aria-label="Escala sequencial de 0 a ${(colorMax * 100).toFixed(0)} por cento"></i><span>${(colorMax * 100).toFixed(0)}%</span>`;
    chart.container.appendChild(legend);
}

function renderFormulationComparison(rows) {
    const observations = uniqueQueryRows(rows);
    const strategies = d3.rollups(observations,
        (items) => {
            const themes = d3.rollups(items,
                (themeRows) => {
                    const queries = d3.rollups(themeRows,
                        (queryRows) => d3.mean(queryRows, metricValue),
                        (row) => row.evaluation_id);
                    return d3.mean(queries, (entry) => entry[1]);
                },
                (row) => themeOf(row));
            const values = themes.map((entry) => entry[1]).filter(Number.isFinite).sort(d3.ascending);
            return {
                mean: d3.mean(values), median: d3.median(values),
                q1: d3.quantile(values, 0.25), q3: d3.quantile(values, 0.75),
                themeCount: values.length,
                queryCount: new Set(items.map((row) => row.evaluation_id)).size,
            };
        },
        (row) => row.query_formulation || "unspecified");
    const data = strategies.map(([formulation, summary]) => ({ formulation, ...summary }))
        .filter((entry) => Number.isFinite(entry.mean))
        .sort((a, b) => b.mean - a.mean || a.formulation.localeCompare(b.formulation, "pt-BR"));
    const height = Math.max(280, data.length * 34 + 85);
    const chart = chartBase("dashboard-formulation-chart", height, 720);
    if (!data.length) return emptyChart(chart, "Aguardando resultados com estratégia de formulação.");
    chart.container.classList.add("dashboard-chart-scroll-x");
    chart.svg.attr("aria-label", `Média macro de ${metricDisplayLabel()} por estratégia de formulação. Cada consulta tem peso igual dentro do tema e cada tema tem o mesmo peso.`);
    const margin = { top: 12, right: 22, bottom: 42, left: 210 };
    const width = chart.width - margin.left - margin.right;
    const innerHeight = chart.height - margin.top - margin.bottom;
    const x = d3.scaleLinear().domain([0, metricUpperBound(data.map((entry) => entry.mean))]).range([0, width]);
    const y = d3.scaleBand().domain(data.map((entry) => entry.formulation))
        .range([0, innerHeight]).padding(0.28);
    const g = chart.svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
    g.append("g").attr("transform", `translate(0,${innerHeight})`).call(d3.axisBottom(x).ticks(5, "%"));
    g.append("g").call(d3.axisLeft(y).tickSize(0));
    g.append("text").attr("class", "dashboard-axis-label").attr("x", width / 2)
        .attr("y", innerHeight + 34).attr("text-anchor", "middle")
        .text(`${metricDisplayLabel()} · média macro por tema`);
    const marks = g.selectAll("g.formulation-mark").data(data).join("g").attr("class", "formulation-mark");
    marks.append("line").attr("x1", (entry) => x(entry.q1)).attr("x2", (entry) => x(entry.q3))
        .attr("y1", (entry) => y(entry.formulation) + y.bandwidth() / 2)
        .attr("y2", (entry) => y(entry.formulation) + y.bandwidth() / 2)
        .attr("stroke", "#818cf8").attr("stroke-width", 6).attr("stroke-linecap", "round");
    marks.append("circle").attr("cx", (entry) => x(entry.mean))
        .attr("cy", (entry) => y(entry.formulation) + y.bandwidth() / 2)
        .attr("r", 5).attr("fill", "#4338ca").attr("stroke", "white").attr("stroke-width", 1)
        .attr("tabindex", 0).attr("role", "img")
        .attr("aria-label", (entry) => `${entry.formulation}: média macro ${(entry.mean * 100).toFixed(1)}%, intervalo interquartil entre temas ${(entry.q1 * 100).toFixed(1)}–${(entry.q3 * 100).toFixed(1)}%, ${entry.themeCount} temas e ${entry.queryCount} consultas.`)
        .append("title").text((entry) => `${entry.formulation} · média ${(entry.mean * 100).toFixed(1)}%, mediana ${(entry.median * 100).toFixed(1)}%, IQR entre temas ${(entry.q1 * 100).toFixed(1)}–${(entry.q3 * 100).toFixed(1)}% (${entry.themeCount} temas, ${entry.queryCount} consultas)`);
}

function renderPairedDeltas(rows) {
    const baseline = $("dashboard-baseline-ranking").value;
    const sourceRows = filteredRows({ ignoreRanking: true });
    const baselineRows = sourceRows.filter((row) => row.result.ranking === baseline && Number.isFinite(metricValue(row)));
    const targets = uniqueQueryRows(sourceRows.filter((row) => row.result.ranking !== baseline));
    const deltas = [];
    for (const target of targets) {
        const baseCandidates = baselineRows.filter((row) => row.evaluation_id === target.evaluation_id
            && row.result.preset === target.result.preset
            && String(row.result.quorum) === String(target.result.quorum)
            && row.result.result_unit === target.result.result_unit
            && (SEED_INDEPENDENT.has(baseline) || SEED_INDEPENDENT.has(target.result.ranking)
                || row.result.seed_method === target.result.seed_method));
        if (!baseCandidates.length) continue;
        const baseValue = d3.mean(baseCandidates, metricValue);
        deltas.push({
            evaluation_id: target.evaluation_id, theme: themeOf(target), ranking: target.result.ranking,
            delta: metricValue(target) - baseValue,
        });
    }
    const byRanking = d3.rollups(deltas,
        (items) => {
            const byTheme = d3.rollups(items,
                (themeItems) => d3.mean(d3.rollups(themeItems, (queryItems) => d3.mean(queryItems, (entry) => entry.delta), (entry) => entry.evaluation_id), (entry) => entry[1]),
                (entry) => entry.theme).map((entry) => entry[1]).sort(d3.ascending);
            return { mean: d3.mean(byTheme), q1: d3.quantile(byTheme, 0.25), q3: d3.quantile(byTheme, 0.75), themeCount: byTheme.length };
        }, (entry) => entry.ranking
    ).map(([ranking, summary]) => ({ ranking, ...summary })).filter((entry) => Number.isFinite(entry.mean))
        .sort((a, b) => b.mean - a.mean);
    const chart = chartBase("dashboard-paired-delta", Math.max(300, byRanking.length * 28 + 75), 650);
    if (!byRanking.length) return emptyChart(chart, `Sem pares comparáveis com “${baseline}” nos filtros atuais.`);
    chart.container.classList.add("dashboard-chart-scroll-x");
    chart.svg.attr("aria-label", `Diferença pareada de ${$("dashboard-metric").value}@${$("dashboard-k").value} em relação a ${baseline}; valores positivos favorecem o ranking.`);
    const margin = { top: 12, right: 20, bottom: 40, left: Math.min(210, Math.max(130, chart.width * 0.32)) };
    const width = chart.width - margin.left - margin.right;
    const height = chart.height - margin.top - margin.bottom;
    const maxAbs = Math.max(0.05, ...byRanking.map((entry) => Math.max(Math.abs(entry.q1), Math.abs(entry.q3)))) * 1.08;
    const x = d3.scaleLinear().domain([-maxAbs, maxAbs]).range([0, width]);
    const y = d3.scaleBand().domain(byRanking.map((entry) => entry.ranking)).range([0, height]).padding(0.25);
    const g = chart.svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
    g.append("g").attr("transform", `translate(0,${height})`).call(d3.axisBottom(x).ticks(5, ".0%"));
    g.append("g").call(d3.axisLeft(y).tickSize(0));
    g.append("line").attr("x1", x(0)).attr("x2", x(0)).attr("y1", 0).attr("y2", height)
        .attr("stroke", "#475569").attr("stroke-dasharray", "4 3");
    const marks = g.selectAll("g.delta-mark").data(byRanking).join("g").attr("class", "delta-mark");
    marks.append("line").attr("x1", (entry) => x(entry.q1)).attr("x2", (entry) => x(entry.q3))
        .attr("y1", (entry) => y(entry.ranking) + y.bandwidth() / 2).attr("y2", (entry) => y(entry.ranking) + y.bandwidth() / 2)
        .attr("stroke", (entry) => COLORS.get(entry.ranking) || "#64748b").attr("stroke-width", 5).attr("stroke-linecap", "round");
    marks.append("circle").attr("cx", (entry) => x(entry.mean)).attr("cy", (entry) => y(entry.ranking) + y.bandwidth() / 2)
        .attr("r", 5).attr("fill", (entry) => COLORS.get(entry.ranking) || "#64748b").attr("stroke", "white")
        .attr("tabindex", 0).attr("role", "img")
        .attr("aria-label", (entry) => `${entry.ranking}: diferença média ${(entry.mean * 100).toFixed(1)} pontos percentuais frente a ${baseline}; IQR ${(entry.q1 * 100).toFixed(1)} a ${(entry.q3 * 100).toFixed(1)}; ${entry.themeCount} temas.`)
        .append("title").text((entry) => `${entry.ranking} − ${baseline}: ${(entry.mean * 100).toFixed(1)} p.p. (IQR ${(entry.q1 * 100).toFixed(1)}–${(entry.q3 * 100).toFixed(1)} p.p.; ${entry.themeCount} temas)`);
    const deltaUnit = dashboard.metricView === "oracle" ? "p.p. do teto" : "p.p.";
    g.append("text").attr("class", "dashboard-axis-label").attr("x", width / 2).attr("y", height + 34).attr("text-anchor", "middle")
        .text(`Δ ${metricDisplayLabel()} · ${deltaUnit} vs ${baseline}`);
}

function renderSteps(row) {
    const slot = $("dashboard-step-timing");
    slot.replaceChildren();
    if (!row) {
        $("dashboard-step-caption").textContent = "Selecione uma linha na tabela.";
        return;
    }
    const result = row.result;
    const actual = result.metrics?.metrics || [];
    const oracle = result.coverage?.oracle_metrics || [];
    if (!actual.length) return;
    const selectedMetric = $("dashboard-metric").value;
    const oracleView = dashboard.metricView === "oracle";
    $("dashboard-step-caption").textContent = `${row.evaluation_id} · ${result.ranking}/${result.seed_method} · ${oracleView ? `${metricDisplayLabel()} por corte` : "valores absolutos por corte"}`;
    const chart = chartBase("dashboard-step-timing", 300);
    chart.svg.attr("aria-label", oracleView
        ? `${metricDisplayLabel()} nos cortes k da configuração ${row.evaluation_id} · ${result.ranking}/${result.seed_method}.`
        : `Precisão, revocação, F1 e F1 teto do pool nos cortes k da configuração ${row.evaluation_id} · ${result.ranking}/${result.seed_method}.`);
    const margin = { top: 14, right: 15, bottom: 40, left: 48 };
    const width = chart.width - margin.left - margin.right;
    const height = chart.height - margin.top - margin.bottom;
    const cutoffs = actual.map((metric) => metric.k);
    const [minK, maxK] = d3.extent(cutoffs);
    const x = d3.scaleLinear().domain(minK === maxK ? [minK - 0.5, maxK + 0.5] : [minK, maxK]).range([0, width]);
    const oraclePoints = oracleView ? actual.map((metric) => {
        const ceiling = oracle.find((entry) => entry.k === metric.k)?.[selectedMetric];
        return { k: metric.k, value: Number.isFinite(ceiling) && ceiling > 0
            ? metric[selectedMetric] / ceiling : null };
    }).filter((point) => Number.isFinite(point.value)) : [];
    const yMax = oracleView ? metricUpperBound(oraclePoints.map((point) => point.value)) : 1;
    const y = d3.scaleLinear().domain([0, yMax]).range([height, 0]);
    const g = chart.svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
    g.append("g").attr("transform", `translate(0,${height})`)
        .call(d3.axisBottom(x).tickValues(cutoffs).tickFormat(d3.format("d")));
    g.append("g").call(d3.axisLeft(y).ticks(5, "%"));
    const series = oracleView ? [
        { name: metricDisplayLabel(), key: "oracle_ratio", color: "#4338ca", points: oraclePoints },
    ] : [
        { name: "Precisão", key: "precision", color: "#2563eb" },
        { name: "Revocação", key: "recall", color: "#b45309", dash: "5 2" },
        { name: "F1", key: "f1", color: "#7c3aed", dash: "2 2" },
        { name: "F1 teto do pool", key: "oracle_f1", color: "#475569", dash: "4 3" },
    ];
    const line = d3.line().x((point) => x(point.k)).y((point) => y(point.value));
    for (const entry of series) {
        const source = entry.key.startsWith("oracle_") ? oracle : actual;
        const key = entry.key.replace("oracle_", "");
        const points = entry.points || source.map((metric) => ({ k: metric.k, value: metric[key] }))
            .filter((point) => Number.isFinite(point.value));
        if (!points.length) continue;
        g.append("path").datum(points).attr("fill", "none").attr("stroke", entry.color)
            .attr("stroke-width", 2).attr("stroke-dasharray", entry.dash || null).attr("d", line);
        const marks = g.selectAll(`circle.series-${key}`).data(points).join("circle")
            .attr("class", `series-${key}`).attr("cx", (point) => x(point.k)).attr("cy", (point) => y(point.value))
            .attr("r", 3).attr("fill", entry.color).attr("tabindex", 0).attr("role", "img")
            .attr("aria-label", (point) => `${entry.name} em k=${point.k}: ${(point.value * 100).toFixed(1)}%.`);
        marks.append("title").text((point) => `${entry.name} @${point.k}: ${(point.value * 100).toFixed(1)}%`);
    }
    const legend = document.createElement("div"); legend.className = "dashboard-chart-legend";
    for (const entry of series) {
        const item = document.createElement("span"); item.className = "dashboard-legend-item";
        const swatch = document.createElement("i"); swatch.className = "dashboard-line-swatch";
        swatch.style.borderTopColor = entry.color;
        swatch.style.borderTopStyle = entry.dash ? "dashed" : "solid";
        const label = document.createElement("span"); label.textContent = entry.name;
        item.append(swatch, label); legend.appendChild(item);
    }
    chart.container.appendChild(legend);
}

function resultTableRow(row) {
    const result = row.result;
    const tr = document.createElement("tr");
    tr.dataset.seq = String(row.seq);
    tr.classList.toggle("selected", row.seq === dashboard.selectedSeq);
    tr.tabIndex = 0;
    tr.setAttribute("aria-label", `Abrir resultado ${row.evaluation_id}, ranking ${result.ranking}, seed ${result.seed_method}.`);
    const score = metricValue(row);
    const values = [row.evaluation_id, result.ranking, result.seed_method, result.preset,
        String(result.quorum), score == null ? "—" : `${(score * 100).toFixed(1)}%`,
        formatSeconds(result.computation_seconds), result.computation_reused ? "Sim" : "Não"];
    for (const value of values) {
        const td = document.createElement("td"); td.textContent = value; tr.appendChild(td);
    }
    tr.addEventListener("click", () => selectResult(row.seq));
    tr.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectResult(row.seq); }
    });
    return tr;
}

function renderResultsTable(rows, { incremental = false } = {}) {
    const body = $("dashboard-results-body");
    const scroller = body.closest(".dashboard-table-scroll");
    const previousScrollTop = scroller?.scrollTop ?? 0;
    const scrollerTop = scroller?.getBoundingClientRect().top ?? 0;
    const anchor = scroller ? [...body.querySelectorAll("tr[data-seq]")]
        .find((row) => row.getBoundingClientRect().bottom > scrollerTop) : null;
    const anchorSeq = anchor?.dataset.seq ?? null;
    const anchorOffset = anchor ? anchor.getBoundingClientRect().top - scrollerTop : 0;
    const activeRow = document.activeElement && body.contains(document.activeElement)
        ? document.activeElement.closest("tr[data-seq]") : null;
    const focusedSeq = activeRow?.dataset.seq ?? null;
    const restoreTablePosition = () => {
        if (scroller) {
            const nextAnchor = anchorSeq == null ? null : body.querySelector(`tr[data-seq="${CSS.escape(anchorSeq)}"]`);
            scroller.scrollTop = nextAnchor
                ? scroller.scrollTop + nextAnchor.getBoundingClientRect().top - scroller.getBoundingClientRect().top - anchorOffset
                : previousScrollTop;
        }
        if (focusedSeq != null) {
            const focused = body.querySelector(`tr[data-seq="${CSS.escape(focusedSeq)}"]`);
            (focused || body.querySelector("tr[data-seq]"))?.focus({ preventScroll: true });
        }
    };
    const sorted = [...rows].sort((a, b) => {
        const key = dashboard.tableSort.key;
        let left, right;
        if (key === "seq") { left = a.seq; right = b.seq; }
        else if (key === "metric") { left = metricValue(a); right = metricValue(b); }
        else if (key === "evaluation_id") { left = a.evaluation_id; right = b.evaluation_id; }
        else { left = a.result[key]; right = b.result[key]; }
        const cmp = typeof left === "number" && typeof right === "number"
            ? left - right : String(left ?? "").localeCompare(String(right ?? ""), "pt-BR", { numeric: true });
        return (dashboard.tableSort.direction === "asc" ? 1 : -1) * cmp;
    });
    const visible = sorted.slice(0, dashboard.tableLimit);
    $("dashboard-result-count").textContent = `${rows.length.toLocaleString("pt-BR")} resultados filtrados · mostrando ${visible.length.toLocaleString("pt-BR")}`;
    $("dashboard-show-more").hidden = visible.length >= rows.length;
    $("dashboard-show-more").textContent = `Mostrar mais resultados (${Math.min(200, rows.length - visible.length)} de ${rows.length - visible.length} restantes)`;

    const canAppend = incremental && dashboard.tableSort.key === "seq"
        && dashboard.tableSort.direction === "desc"
        && !(dashboard.thresholdEnabled && dashboard.thresholdMode === "sd");
    if (canAppend) {
        const visibleSeqs = new Set(visible.map((row) => String(row.seq)));
        const existing = new Set([...body.querySelectorAll("tr[data-seq]")].map((row) => row.dataset.seq));
        if (visible.length && body.querySelector(".dashboard-empty")) body.replaceChildren();
        for (const row of visible.filter((entry) => !existing.has(String(entry.seq))).reverse()) {
            const tr = resultTableRow(row);
            body.insertBefore(tr, body.firstElementChild);
        }
        for (const tr of body.querySelectorAll("tr[data-seq]")) {
            if (!visibleSeqs.has(tr.dataset.seq)) tr.remove();
            else tr.classList.toggle("selected", Number(tr.dataset.seq) === dashboard.selectedSeq);
        }
        if (!visible.length && !body.querySelector(".dashboard-empty")) {
            const tr = document.createElement("tr"); const td = document.createElement("td");
            td.colSpan = 8; td.className = "dashboard-empty"; td.textContent = "Nenhum resultado para os filtros atuais.";
            tr.appendChild(td); body.appendChild(tr);
        }
        restoreTablePosition();
        return;
    }

    if (!visible.length) {
        const tr = document.createElement("tr"); const td = document.createElement("td");
        td.colSpan = 8; td.className = "dashboard-empty"; td.textContent = "Aguardando resultados.";
        tr.appendChild(td); body.appendChild(tr); restoreTablePosition(); return;
    }
    for (const row of visible) {
        body.appendChild(resultTableRow(row));
    }
    restoreTablePosition();
}

function exportFilteredCsv() {
    const rows = filteredRows();
    const headers = ["consulta_id", "consulta", "formulacao", "ranking", "seed", "preset", "quorum",
        "metrica", "valor", "recall_pool", "tempo_s", "tema"];
    const quote = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
    const lines = [headers.map(quote).join(",")];
    for (const row of rows) {
        lines.push([
            row.evaluation_id, row.query, row.query_formulation, row.result.ranking, row.result.seed_method,
            row.result.preset, row.result.quorum, metricDisplayLabel(),
            metricValue(row), row.result.coverage?.reference_pool_recall, row.result.computation_seconds,
            themeOf(row),
        ].map(quote).join(","));
    }
    const blob = new Blob(["\uFEFF", lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${dashboard.state?.dataset || "dashboard"}-${$("dashboard-metric").value}-${$("dashboard-k").value}.csv`;
    link.click();
    URL.revokeObjectURL(url);
}

async function selectResult(seq) {
    dashboard.selectedSeq = seq;
    persistDashboardUI();
    const row = dashboard.rows.find((entry) => entry.seq === seq);
    renderSteps(row);
    dashboard.stepsRenderedSeq = row ? seq : null;
    renderResultsTable(filteredRows());
    const detail = $("dashboard-result-detail");
    detail.replaceChildren();
    if (!row) { detail.hidden = true; return; }
    detail.hidden = false;
    const heading = document.createElement("h4"); heading.textContent = `${row.evaluation_id} · ${row.result.ranking}/${row.result.seed_method}`;
    const query = document.createElement("p"); query.textContent = row.query;
    const list = document.createElement("ol");
    const loading = document.createElement("p"); loading.textContent = "Carregando resultados ranqueados…";
    detail.append(heading, query, loading);
    try {
        const full = await api(`/dashboard/runs/${dashboard.runId}/results/${seq}`);
        if (dashboard.selectedSeq !== seq) return;
        const ranked = full.result?.ranked_results || (full.result?.ranked_urls || []).map((article) => ({ article }));
        loading.remove();
        for (const entry of ranked.slice(0, 20)) {
            const url = entry.article;
            const li = document.createElement("li"); const link = document.createElement("a");
            link.href = url; link.target = "_blank"; link.rel = "noopener";
            link.textContent = `${url}${Number.isFinite(entry.score) ? ` · score ${entry.score}` : ""}`;
            li.appendChild(link); list.appendChild(li);
        }
        detail.appendChild(list);
        const retrieved = full.result?.retrieval_steps;
        if (retrieved) {
            const retrievalNote = document.createElement("p");
            retrievalNote.className = "dashboard-muted";
            retrievalNote.textContent = `Artigos retornados no ranking: ${full.result?.ranked_results?.length ?? ranked.length}. Os dados completos da recuperação e dos diagnósticos também foram arquivados com a rodada.`;
            detail.appendChild(retrievalNote);
        }
        const timings = document.createElement("details");
        timings.className = "dashboard-result-timings";
        const summary = document.createElement("summary"); summary.textContent = "Tempos das etapas da busca";
        const table = document.createElement("dl");
        const retrieval = row.result.retrieval_steps || {};
        const ranking = row.result.step_timings || {};
        const timingRows = [
            ["Embedding da consulta", retrieval.query_embedding_seconds],
            ["Busca híbrida no banco", retrieval.hybrid_query_seconds],
            ["Processamento dos resultados", retrieval.result_processing_seconds],
            ["Busca de artigos", retrieval.article_lookup_seconds],
            ["Leitura/extração de entidades", ranking.graph_entity_load_extract_seconds],
            ["Montagem do grafo", ranking.graph_assembly_seconds],
            ["Poda do grafo", ranking.graph_pruning_seconds],
            ["Cálculo PPR/seeds", ranking.ppr_seconds],
            ["MMR", ranking.mmr_seconds],
            ["Cross-encoder (inferência não reutilizada)", ranking.cross_encoder_seconds],
            ["Cálculo total do ranking", row.result.computation_seconds],
        ].filter(([, seconds]) => Number.isFinite(Number(seconds)));
        for (const [label, seconds] of timingRows) {
            const term = document.createElement("dt"); term.textContent = label;
            const value = document.createElement("dd"); value.textContent = formatSeconds(seconds);
            table.append(term, value);
        }
        timings.append(summary, table);
        detail.appendChild(timings);
    } catch (error) {
        loading.textContent = error.message;
    }
}

function emptyChart(chart, message) {
    chart.svg.append("text").attr("class", "dashboard-chart-empty")
        .attr("x", chart.width / 2).attr("y", chart.height / 2).attr("text-anchor", "middle").text(message);
}

function scheduleDashboardRender(force = false, incrementalTable = false) {
    if (!$('panel-dashboard').classList.contains("active")) return;
    dashboard.incrementalRenderPending ||= incrementalTable;
    const elapsed = Date.now() - dashboard.lastAnalyticsRenderAt;
    const wait = Math.max(0, ANALYTICS_RENDER_INTERVAL_MS - elapsed);
    if (force || wait === 0) {
        if (dashboard.analyticsRenderTimer) clearTimeout(dashboard.analyticsRenderTimer);
        dashboard.analyticsRenderTimer = null;
        runScheduledDashboardRender();
        return;
    }
    if (!dashboard.analyticsRenderTimer) {
        dashboard.analyticsRenderTimer = setTimeout(() => {
            dashboard.analyticsRenderTimer = null;
            runScheduledDashboardRender();
        }, wait);
    }
}

function runScheduledDashboardRender() {
    if (!$('panel-dashboard').classList.contains("active")) return;
    if (document.activeElement?.closest(".dashboard-chart")) {
        dashboard.analyticsRenderTimer = setTimeout(() => {
            dashboard.analyticsRenderTimer = null;
            runScheduledDashboardRender();
        }, 750);
        return;
    }
    const incrementalTable = dashboard.incrementalRenderPending;
    dashboard.incrementalRenderPending = false;
    renderDashboard({ incrementalTable, fromSchedule: true });
}

function renderDashboard({ incrementalTable = false, fromSchedule = false } = {}) {
    if (dashboard.analyticsRenderTimer) clearTimeout(dashboard.analyticsRenderTimer);
    dashboard.analyticsRenderTimer = null;
    if (!fromSchedule) dashboard.incrementalRenderPending = false;
    dashboard.lastAnalyticsRenderAt = Date.now();
    syncMetricView();
    renderProgress();
    refreshFilterOptions();
    syncThresholdControls();
    const screenedRows = dimensionFilteredRows();
    renderMetricDistribution(screenedRows);
    renderExclusionAudit(screenedRows);
    const rows = thresholdFilteredRows(screenedRows);
    renderKpis(rows);
    renderInsights(rows);
    renderCombinationLeaderboard(rows);
    renderHeatmap(rows);
    renderCoverage(rows);
    renderPerformanceByTheme(rows);
    renderFormulationComparison(rows);
    renderPairedDeltas(rows);
    renderResultsTable(rows, { incremental: incrementalTable });
    if (dashboard.selectedSeq != null) {
        const selected = dashboard.rows.find((row) => row.seq === dashboard.selectedSeq);
        if (selected && rows.some((row) => row.seq === dashboard.selectedSeq)) {
            if (dashboard.stepsRenderedSeq !== dashboard.selectedSeq) {
                renderSteps(selected);
                dashboard.stepsRenderedSeq = dashboard.selectedSeq;
            }
        }
        else {
            dashboard.selectedSeq = null;
            renderSteps(null);
            dashboard.stepsRenderedSeq = null;
            $("dashboard-result-detail").hidden = true;
        }
    }
}

function constrainMetricCutoffs() {
    const cutoff = $("dashboard-k");
    const allowed = ["map", "ndcg"].includes($("dashboard-metric").value)
        ? [5, 10, 20] : [1, 3, 5, 10, 20];
    const current = Number(cutoff.value);
    cutoff.replaceChildren(...allowed.map((value) => new Option(String(value), String(value))));
    cutoff.value = allowed.includes(current) ? String(current) : "5";
}

async function loadDatasets() {
    const data = await api("/dashboard/evaluation-sets");
    dashboard.datasets = data.datasets || [];
    const saved = getUiState().batchDashboard || {};
    renderThemeChoices(initialThemeSelection(saved, dashboard.datasets));
}

async function refreshRunList() {
    const data = await api("/dashboard/runs");
    const select = $("dashboard-existing-run");
    const current = select.value;
    select.replaceChildren(new Option("Rodadas salvas…", ""));
    for (const run of data.runs || []) {
        select.add(new Option(`${run.dataset_label || run.dataset} · ${run.status} · ${run.progress.completed}/${run.progress.total}`,
            run.run_id));
    }
    if ((data.runs || []).some((run) => run.run_id === current)) select.value = current;
}

function stopPolling() {
    if (dashboard.timer) clearInterval(dashboard.timer);
    dashboard.timer = null;
}

async function pollRun() {
    if (!dashboard.runId || dashboard.polling) return;
    dashboard.polling = true;
    try {
        const state = await api(`/dashboard/runs/${dashboard.runId}`);
        const previousState = dashboard.state;
        const initialState = !previousState || previousState.run_id !== state.run_id;
        let addedResults = 0;
        dashboard.state = state;
        dashboard.startedAt = Date.parse(state.created_at) || null;
        let hasMore = true;
        while (hasMore) {
            const page = await api(`/dashboard/runs/${dashboard.runId}/results?after=${dashboard.cursor}&limit=200`);
            for (const event of page.events || []) {
                dashboard.rows.push(event);
                addedResults += 1;
            }
            dashboard.cursor = page.cursor ?? dashboard.cursor;
            hasMore = page.has_more;
        }
        renderProgress();
        if (initialState) {
            renderDashboard();
        } else if (addedResults > 0) {
            scheduleDashboardRender(false, true);
        } else if (previousState.status !== state.status
            && ["completed", "failed", "interrupted"].includes(state.status)) {
            scheduleDashboardRender(true);
        }
        if (dashboard.restoreSelection && dashboard.rows.some((row) => row.seq === dashboard.selectedSeq)) {
            dashboard.restoreSelection = false;
            selectResult(dashboard.selectedSeq);
        }
        if (["completed", "failed", "interrupted"].includes(state.status)) {
            stopPolling();
            $("dashboard-launch-hint").textContent = state.error || `Rodada ${state.status}.`;
            refreshRunList().catch(() => {});
        }
    } catch (error) {
        $("dashboard-launch-hint").textContent = error.message;
        stopPolling();
    } finally {
        dashboard.polling = false;
    }
}

async function openRun(runId) {
    stopPolling();
    if (dashboard.analyticsRenderTimer) clearTimeout(dashboard.analyticsRenderTimer);
    dashboard.analyticsRenderTimer = null;
    dashboard.runId = runId;
    const saved = getUiState().batchDashboard || {};
    dashboard.savedFilters = saved.runId === runId ? (saved.filters || null) : null;
    if (dashboard.savedFilters) {
        dashboard.multiFilters = {
            theme: restoreFacetFilter(dashboard.savedFilters.theme),
            formulation: restoreFacetFilter(dashboard.savedFilters.formulation),
        };
    } else {
        dashboard.multiFilters = {
            theme: { mode: "include", values: [] },
            formulation: { mode: "include", values: [] },
        };
    }
    $("dashboard-filter-theme-mode").value = dashboard.multiFilters.theme.mode;
    $("dashboard-filter-formulation-mode").value = dashboard.multiFilters.formulation.mode;
    if (saved.runId !== runId) {
        for (const id of ["dashboard-filter-ranking", "dashboard-filter-seed", "dashboard-filter-preset",
            "dashboard-filter-quorum", "dashboard-filter-query"]) $(id).value = "";
        dashboard.distributionKey = null;
    }
    dashboard.selectedSeq = saved.runId === runId ? saved.selectedSeq ?? null : null;
    dashboard.restoreSelection = dashboard.selectedSeq != null;
    dashboard.rows = [];
    dashboard.cursor = 0;
    $("dashboard-filter-theme-options").replaceChildren();
    $("dashboard-filter-formulation-options").replaceChildren();
    updateFacetSummary("theme");
    updateFacetSummary("formulation");
    dashboard.state = null;
    dashboard.lastAnalyticsRenderAt = 0;
    dashboard.stepsRenderedSeq = null;
    dashboard.tableLimit = 200;
    dashboard.exclusionLimit = 100;
    $("dashboard-settings").open = false;
    await pollRun();
    if (["queued", "running"].includes(dashboard.state?.status)) {
        dashboard.timer = setInterval(pollRun, 1500);
    }
    persistDashboardUI();
}

async function startRun() {
    const settings = {
        presets: checkedValues($("dashboard-presets")),
        quorums: checkedValues($("dashboard-quorums")).map(Number),
        rankings: checkedValues($("dashboard-rankings")),
        seed_methods: checkedValues($("dashboard-seeds")),
        query_seed_fallback: $("dashboard-fallback").value,
        ensemble_rankings: checkedValues($("dashboard-ensemble-components")),
        result_unit: $("dashboard-unit").value,
    };
    persistDashboardUI(settings);
    const datasets = selectedDatasetIds();
    if (!datasets.length || !settings.presets.length || !settings.quorums.length || !settings.rankings.length
        || !settings.seed_methods.length || !settings.ensemble_rankings.length) {
        $("dashboard-launch-hint").textContent = "Selecione ao menos um tema, preset, quorum, ranking, seed e componente de ensemble.";
        return;
    }
    const queryCount = d3.sum(dashboard.datasets.filter((entry) => datasets.includes(entry.id)), (entry) => entry.count || 0);
    const configCount = queryCount
        * settings.presets.length * settings.quorums.length * settings.rankings.length * settings.seed_methods.length;
    if (configCount > 512 && !window.confirm(`Esta rodada terá até ${configCount.toLocaleString("pt-BR")} resultados antes de remover consultas duplicadas. Deseja iniciar?`)) return;
    $("dashboard-start").disabled = true;
    $("dashboard-launch-hint").textContent = "Criando rodada…";
    try {
        const run = await api("/dashboard/runs", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ datasets, settings }),
        });
        await refreshRunList();
        $("dashboard-existing-run").value = run.run_id;
        dashboard.selectedSeq = null;
        dashboard.savedFilters = null;
        $("dashboard-launch-hint").textContent = "Resultados serão adicionados conforme cada configuração terminar.";
        await openRun(run.run_id);
    } catch (error) {
        $("dashboard-launch-hint").textContent = error.message;
    } finally {
        $("dashboard-start").disabled = false;
    }
}

function currentFormSettings() {
    return {
        presets: checkedValues($("dashboard-presets")),
        quorums: checkedValues($("dashboard-quorums")).map(Number),
        rankings: checkedValues($("dashboard-rankings")),
        seed_methods: checkedValues($("dashboard-seeds")),
        query_seed_fallback: $("dashboard-fallback").value,
        ensemble_rankings: checkedValues($("dashboard-ensemble-components")),
        result_unit: $("dashboard-unit").value,
    };
}

function persistDashboardUI(settings = currentFormSettings()) {
    setUiState("batchDashboard", {
        runId: dashboard.runId,
        datasets: selectedDatasetIds(),
        settings,
        filters: filtersFromUI(),
        metric: $("dashboard-metric")?.value || "f1",
        metricView: dashboard.metricView,
        k: $("dashboard-k")?.value || "20",
        baseline: $("dashboard-baseline-ranking")?.value || "hybrid_max",
        thresholdEnabled: dashboard.thresholdEnabled,
        thresholdMode: dashboard.thresholdMode,
        threshold: dashboard.threshold,
        sdThreshold: dashboard.sdThreshold,
        distributionKey: dashboard.distributionKey,
        selectedSeq: dashboard.selectedSeq,
    });
}

function ensureDashboardTemplateCompatibility() {
    // Flask can keep an older compiled index.html in an already-running dev
    // server while static ES modules update immediately. Add the newly-required
    // controls to that page so the module remains usable until Flask restarts.
    if (!$("dashboard-metric-view")) {
        const metricLabel = $("dashboard-metric")?.closest("label");
        if (metricLabel) {
            const label = document.createElement("label");
            label.append(document.createTextNode("Escala"));
            const select = document.createElement("select");
            select.id = "dashboard-metric-view";
            select.add(new Option("Valor original", "raw"));
            select.add(new Option("Fração do teto do pool", "oracle"));
            label.appendChild(select);
            metricLabel.after(label);
        }
    }

    for (const type of ["theme", "formulation"]) {
        const config = facetFilterConfig(type);
        if ($(config.options) && $(`dashboard-filter-${type}-mode`)
            && $(`dashboard-filter-${type}-summary`)) continue;
        const legacy = $(`dashboard-filter-${type}`);
        const details = document.createElement("details");
        details.className = "dashboard-multi-filter";
        const summary = document.createElement("summary");
        summary.id = config.summary;
        summary.textContent = type === "theme" ? "Temas · todos" : "Formulações · todas";
        details.appendChild(summary);
        const modeLabel = document.createElement("label");
        modeLabel.htmlFor = `dashboard-filter-${type}-mode`;
        modeLabel.textContent = type === "theme" ? "Filtro de temas" : "Filtro de formulação";
        const mode = document.createElement("select");
        mode.id = `dashboard-filter-${type}-mode`;
        mode.add(new Option("Incluir selecionados", "include"));
        mode.add(new Option("Excluir selecionados", "exclude"));
        details.append(modeLabel, mode);
        const actions = document.createElement("div");
        actions.className = "dashboard-multi-filter-actions";
        const selectAll = document.createElement("button");
        selectAll.type = "button"; selectAll.className = "btn-ghost";
        selectAll.id = `dashboard-filter-${type}-all`;
        selectAll.textContent = type === "theme" ? "Selecionar todos" : "Selecionar todas";
        const clear = document.createElement("button");
        clear.type = "button"; clear.className = "btn-ghost";
        clear.id = `dashboard-filter-${type}-clear`; clear.textContent = "Limpar";
        actions.append(selectAll, clear); details.appendChild(actions);
        const options = document.createElement("div");
        options.id = config.options; options.className = "dashboard-multi-filter-options";
        details.appendChild(options);
        const oldLabel = legacy?.closest("label");
        if (oldLabel) oldLabel.replaceWith(details);
        else {
            const filterbar = $("dashboard-filterbar") || document.querySelector(".dashboard-filterbar");
            filterbar?.appendChild(details);
        }
    }

    if (!$("dashboard-threshold-mode")) {
        const controls = $("dashboard-threshold-enabled")?.closest(".dashboard-threshold-controls");
        if (controls) {
            const enableLabel = $("dashboard-threshold-enabled").closest("label");
            const modeLabel = document.createElement("label");
            modeLabel.htmlFor = "dashboard-threshold-mode"; modeLabel.textContent = "Modo";
            const mode = document.createElement("select"); mode.id = "dashboard-threshold-mode";
            mode.add(new Option("Piso absoluto", "absolute"));
            mode.add(new Option("Desvios padrão por configuração", "sd"));
            enableLabel.after(modeLabel, mode);

            const absolute = document.createElement("div");
            absolute.id = "dashboard-absolute-threshold-controls";
            absolute.className = "dashboard-threshold-mode-controls";
            const range = $("dashboard-threshold-range");
            const number = $("dashboard-threshold-number");
            const percent = $("dashboard-threshold-percent");
            const rangeLabel = controls.querySelector('label[for="dashboard-threshold-range"]');
            for (const node of [rangeLabel, range, number, percent]) if (node) absolute.appendChild(node);
            const explanatory = controls.querySelector(".dashboard-muted");
            controls.insertBefore(absolute, explanatory || null);

            const sdControls = document.createElement("div");
            sdControls.id = "dashboard-sd-threshold-controls";
            sdControls.className = "dashboard-threshold-mode-controls";
            sdControls.hidden = true;
            const sdLabel = document.createElement("label");
            sdLabel.htmlFor = "dashboard-sd-threshold-range"; sdLabel.textContent = "Manter z ≥";
            const sdRange = document.createElement("input");
            sdRange.type = "range"; sdRange.id = "dashboard-sd-threshold-range";
            sdRange.min = "-3"; sdRange.max = "2"; sdRange.step = "0.1"; sdRange.value = "-1";
            const sdNumber = document.createElement("input");
            sdNumber.type = "number"; sdNumber.id = "dashboard-sd-threshold-number";
            sdNumber.min = "-3"; sdNumber.max = "2"; sdNumber.step = "0.1"; sdNumber.value = "-1";
            const sdOutput = document.createElement("output");
            sdOutput.id = "dashboard-sd-threshold-value"; sdOutput.textContent = "−1,0σ";
            sdControls.append(sdLabel, sdRange, sdNumber, sdOutput);
            controls.insertBefore(sdControls, explanatory || null);
            const metricContext = document.createElement("strong");
            metricContext.id = "dashboard-threshold-metric-context";
            metricContext.textContent = "F1@20";
            if (explanatory) explanatory.append(" ", metricContext);
            else controls.appendChild(metricContext);
        }
    }

    if (!$("dashboard-metric-distribution")) {
        const grid = $("panel-dashboard")?.querySelector(".dashboard-chart-grid");
        if (grid) {
            const card = document.createElement("article");
            card.className = "dashboard-card dashboard-chart-card dashboard-timeline-card";
            const heading = document.createElement("h3"); heading.textContent = "Distribuição da métrica";
            const caption = document.createElement("p");
            caption.id = "dashboard-distribution-caption"; caption.className = "dashboard-muted";
            caption.textContent = "Distribuição antes do filtro de métrica.";
            const label = document.createElement("label");
            label.className = "dashboard-distribution-choice";
            label.htmlFor = "dashboard-distribution-config";
            label.append(document.createTextNode("Configuração exibida "));
            const select = document.createElement("select"); select.id = "dashboard-distribution-config";
            label.appendChild(select);
            const chart = document.createElement("div");
            chart.id = "dashboard-metric-distribution"; chart.className = "dashboard-chart";
            card.append(heading, caption, label, chart);
            grid.insertBefore(card, grid.firstChild);
        }
    }
}

export async function initDashboard() {
    ensureDashboardTemplateCompatibility();
    const saved = getUiState().batchDashboard || {};
    const savedSettings = saved.settings || {};
    dashboard.multiFilters = {
        theme: restoreFacetFilter(saved.filters?.theme),
        formulation: restoreFacetFilter(saved.filters?.formulation),
    };
    makeCheckGrid($("dashboard-presets"), PRESETS, savedSettings.presets || ["rapido"], (value) => ({
        rapido: "Rápido (top 250)", balanceado: "Balanceado (top 500)", profundo: "Profundo (top 1000)",
    })[value]);
    makeCheckGrid($("dashboard-quorums"), QUORUMS, savedSettings.quorums || [0.3], (value) => `${Math.round(value * 100)}%`);
    makeCheckGrid($("dashboard-rankings"), RANKINGS, savedSettings.rankings || ["hybrid_max", "ppr", "rrf", "fused"]);
    makeCheckGrid($("dashboard-seeds"), SEEDS, savedSettings.seed_methods || ["hits"]);
    makeCheckGrid($("dashboard-ensemble-components"), ENSEMBLE_COMPONENTS,
        savedSettings.ensemble_rankings || ["rrf", "cross_encoder", "ppr"]);
    $("dashboard-unit").value = savedSettings.result_unit || "articles";
    $("dashboard-fallback").value = savedSettings.query_seed_fallback || "hits";
    $("dashboard-metric").value = saved.metric || "f1";
    dashboard.metricView = saved.metricView === "oracle" ? "oracle" : "raw";
    $("dashboard-k").value = saved.k || "20";
    $("dashboard-baseline-ranking").value = saved.baseline || "hybrid_max";
    dashboard.thresholdEnabled = Boolean(saved.thresholdEnabled);
    dashboard.thresholdMode = ["absolute", "sd"].includes(saved.thresholdMode) ? saved.thresholdMode : "absolute";
    dashboard.threshold = Number.isFinite(Number(saved.threshold))
        ? Math.min(1, Math.max(0, Number(saved.threshold))) : 0.70;
    dashboard.sdThreshold = Number.isFinite(Number(saved.sdThreshold))
        ? Math.min(2, Math.max(-3, Number(saved.sdThreshold))) : -1;
    dashboard.distributionKey = typeof saved.distributionKey === "string" ? saved.distributionKey : null;
    constrainMetricCutoffs();
    syncMetricView();
    $("dashboard-start").addEventListener("click", startRun);
    $("dashboard-refresh").addEventListener("click", pollRun);
    $("dashboard-export").addEventListener("click", exportFilteredCsv);
    $("dashboard-show-more").addEventListener("click", () => {
        dashboard.tableLimit += 200;
        renderResultsTable(filteredRows());
    });
    $("dashboard-exclusion-more").addEventListener("click", () => {
        dashboard.exclusionLimit += 100;
        renderExcludedCases();
    });
    $("dashboard-exclusion-search").addEventListener("input", () => {
        dashboard.exclusionLimit = 100;
        renderExcludedCases();
    });
    $("dashboard-threshold-enabled").addEventListener("change", () => {
        dashboard.thresholdEnabled = $("dashboard-threshold-enabled").checked;
        dashboard.tableLimit = 200;
        dashboard.exclusionLimit = 100;
        renderDashboard();
        persistDashboardUI();
    });
    const changeThreshold = (input) => {
        const parsed = Number.parseFloat(input.value);
        if (!Number.isFinite(parsed)) return;
        if (dashboard.thresholdMode === "sd") {
            dashboard.sdThreshold = Math.round(Math.min(2, Math.max(-3, parsed)) * 10) / 10;
        } else {
            dashboard.threshold = Math.round(Math.min(1, Math.max(0, parsed)) * 100) / 100;
        }
        dashboard.tableLimit = 200;
        dashboard.exclusionLimit = 100;
        renderDashboard();
        persistDashboardUI();
    };
    $("dashboard-threshold-mode").addEventListener("change", () => {
        dashboard.thresholdMode = $("dashboard-threshold-mode").value === "sd" ? "sd" : "absolute";
        renderDashboard();
        persistDashboardUI();
    });
    $("dashboard-threshold-range").addEventListener("input", (event) => changeThreshold(event.currentTarget));
    $("dashboard-threshold-number").addEventListener("change", (event) => changeThreshold(event.currentTarget));
    $("dashboard-sd-threshold-range").addEventListener("input", (event) => changeThreshold(event.currentTarget));
    $("dashboard-sd-threshold-number").addEventListener("change", (event) => changeThreshold(event.currentTarget));
    $("dashboard-distribution-config").addEventListener("change", () => {
        dashboard.distributionKey = $("dashboard-distribution-config").value || null;
        renderMetricDistribution(dimensionFilteredRows());
        persistDashboardUI();
    });
    $("dashboard-show-all-combinations").addEventListener("change", () => renderCombinationLeaderboard(filteredRows()));
    $("dashboard-clear-filters").addEventListener("click", () => {
        for (const id of ["dashboard-filter-ranking", "dashboard-filter-seed", "dashboard-filter-preset",
            "dashboard-filter-quorum", "dashboard-filter-query"]) {
            $(id).value = "";
        }
        dashboard.multiFilters = {
            theme: { mode: "include", values: [] },
            formulation: { mode: "include", values: [] },
        };
        $("dashboard-filter-theme-mode").value = "include";
        $("dashboard-filter-formulation-mode").value = "include";
        syncFacetOptions("theme", dashboard.rows.map((row) => themeOf(row)));
        syncFacetOptions("formulation", dashboard.rows.map((row) => row.query_formulation || "unspecified"));
        dashboard.thresholdEnabled = false;
        dashboard.thresholdMode = "absolute";
        dashboard.threshold = 0.70;
        dashboard.sdThreshold = -1;
        $("dashboard-exclusion-search").value = "";
        dashboard.tableLimit = 200;
        dashboard.exclusionLimit = 100;
        renderDashboard();
        persistDashboardUI();
    });
    for (const type of ["theme", "formulation"]) {
        const config = facetFilterConfig(type);
        const mode = $(`dashboard-filter-${type}-mode`);
        mode.value = dashboard.multiFilters[type].mode;
        mode.addEventListener("change", () => {
            dashboard.multiFilters[type].mode = mode.value === "exclude" ? "exclude" : "include";
            updateFacetSummary(type);
            dashboard.tableLimit = 200;
            renderDashboard();
            persistDashboardUI();
        });
        $(`dashboard-filter-${type}-all`).addEventListener("click", () => {
            dashboard.multiFilters[type].values = [...$(config.options).querySelectorAll("input[type=checkbox]")]
                .map((input) => input.value);
            syncFacetOptions(type, dashboard.rows.map((row) => type === "theme"
                ? themeOf(row) : (row.query_formulation || "unspecified")));
            dashboard.tableLimit = 200;
            renderDashboard();
            persistDashboardUI();
        });
        $(`dashboard-filter-${type}-clear`).addEventListener("click", () => {
            dashboard.multiFilters[type].values = [];
            syncFacetOptions(type, dashboard.rows.map((row) => type === "theme"
                ? themeOf(row) : (row.query_formulation || "unspecified")));
            dashboard.tableLimit = 200;
            renderDashboard();
            persistDashboardUI();
        });
    }
    $("dashboard-clear-themes").addEventListener("click", () => {
        for (const checkbox of $("dashboard-theme-sets").querySelectorAll("input[type=checkbox]")) {
            checkbox.checked = false;
        }
        updateThemeSelectionSummary();
        persistDashboardUI();
    });
    $("dashboard-load-run").addEventListener("click", () => {
        if ($("dashboard-existing-run").value) openRun($("dashboard-existing-run").value);
    });
    for (const id of ["dashboard-filter-ranking", "dashboard-filter-seed", "dashboard-filter-preset",
        "dashboard-filter-quorum", "dashboard-filter-query",
        "dashboard-k", "dashboard-baseline-ranking"]) $(id).addEventListener("change", () => {
            dashboard.tableLimit = 200;
            renderDashboard();
            persistDashboardUI();
        });
    $("dashboard-metric").addEventListener("change", () => {
        dashboard.tableLimit = 200;
        constrainMetricCutoffs();
        syncMetricView();
        renderDashboard();
        persistDashboardUI();
    });
    $("dashboard-metric-view").value = dashboard.metricView;
    $("dashboard-metric-view").addEventListener("change", () => {
        dashboard.metricView = $("dashboard-metric-view").value === "oracle" ? "oracle" : "raw";
        syncMetricView();
        dashboard.tableLimit = 200;
        renderDashboard();
        persistDashboardUI();
    });
    for (const id of ["dashboard-unit", "dashboard-fallback", "dashboard-presets",
        "dashboard-quorums", "dashboard-rankings", "dashboard-seeds", "dashboard-ensemble-components"]) {
        $(id).addEventListener("change", () => persistDashboardUI());
    }
    for (const id of ["dashboard-existing-run"]) $(id).addEventListener("change", () => persistDashboardUI());
    const resultTable = document.querySelector(".dashboard-table");
    resultTable?.querySelectorAll("th[data-sort]").forEach((header) => {
        header.tabIndex = 0;
        header.setAttribute("aria-sort", "none");
        const sort = () => {
            const key = header.dataset.sort;
            dashboard.tableSort = dashboard.tableSort.key === key
                ? { key, direction: dashboard.tableSort.direction === "asc" ? "desc" : "asc" }
                : { key, direction: key === "evaluation_id" || key === "ranking" ? "asc" : "desc" };
            resultTable.querySelectorAll("th[data-sort]").forEach((th) => th.setAttribute("aria-sort", "none"));
            header.setAttribute("aria-sort", dashboard.tableSort.direction === "asc" ? "ascending" : "descending");
            renderResultsTable(filteredRows());
        };
        header.addEventListener("click", sort);
        header.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") { event.preventDefault(); sort(); }
        });
    });
    document.querySelector('[data-tab="panel-dashboard"]')?.addEventListener("click", () => {
        requestAnimationFrame(renderDashboard);
    });
    window.addEventListener("resize", () => {
        if (dashboard.runId && $("panel-dashboard").classList.contains("active")) scheduleDashboardRender(true);
    });
    try {
        await Promise.all([loadDatasets(), refreshRunList()]);
        const runs = await api("/dashboard/runs");
        const preferred = saved.runId;
        const existing = runs.runs?.find((run) => run.run_id === preferred) || runs.runs?.[0];
        if (existing) {
            $("dashboard-existing-run").value = existing.run_id;
            await openRun(existing.run_id);
        }
    } catch (error) {
        $("dashboard-launch-hint").textContent = error.message;
    }
}
