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
    thresholdEnabled: false, threshold: 0.70, excludedRows: [], exclusionLimit: 100,
};

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

function metricValue(row) {
    const metric = $("dashboard-metric").value;
    const k = Number($("dashboard-k").value);
    if (metric === "f1" || metric === "precision" || metric === "recall") {
        return row.result.metrics?.metrics?.find((entry) => entry.k === k)?.[metric] ?? null;
    }
    const prefix = metric === "map" ? "map" : "ndcg";
    return row.result.ranking_metrics?.[`${prefix}@${k}`] ?? null;
}

function filtersFromUI() {
    return {
        ranking: $("dashboard-filter-ranking").value,
        seed: $("dashboard-filter-seed").value,
        preset: $("dashboard-filter-preset").value,
        quorum: $("dashboard-filter-quorum").value,
        theme: $("dashboard-filter-theme").value,
        query: $("dashboard-filter-query").value,
        formulation: $("dashboard-filter-formulation").value,
    };
}

function dimensionFilteredRows({ ignoreRanking = false } = {}) {
    const filters = filtersFromUI();
    return dashboard.rows.filter((row) => {
        const result = row.result;
        return (ignoreRanking || !filters.ranking || result.ranking === filters.ranking)
            && (!filters.seed || result.seed_method === filters.seed)
            && (!filters.preset || result.preset === filters.preset)
            && (!filters.quorum || String(result.quorum) === filters.quorum)
            && (!filters.theme || row.evaluation_id.split("__", 1)[0] === filters.theme)
            && (!filters.query || row.evaluation_id === filters.query)
            && (!filters.formulation || row.query_formulation === filters.formulation);
    });
}

function thresholdValue(row) {
    return metricValue(row);
}

function thresholdDecision(row) {
    const value = thresholdValue(row);
    if (!Number.isFinite(value)) return "missing";
    return value < dashboard.threshold ? "below" : "keep";
}

function thresholdFilteredRows(rows) {
    if (!dashboard.thresholdEnabled) return rows;
    return rows.filter((row) => thresholdDecision(row) === "keep");
}

function filteredRows(options = {}) {
    return thresholdFilteredRows(dimensionFilteredRows(options));
}

function syncThresholdControls() {
    const metric = $("dashboard-metric").value;
    const k = $("dashboard-k").value;
    const metricName = { f1: "F1", precision: "Precisão", recall: "Revocação", ndcg: "NDCG", map: "MAP" }[metric] || metric;
    $("dashboard-threshold-enabled").checked = dashboard.thresholdEnabled;
    $("dashboard-threshold-range").value = String(dashboard.threshold);
    $("dashboard-threshold-number").value = String(dashboard.threshold.toFixed(2));
    $("dashboard-threshold-percent").value = `${(dashboard.threshold * 100).toFixed(0)}%`;
    $("dashboard-threshold-range").disabled = !dashboard.thresholdEnabled;
    $("dashboard-threshold-number").disabled = !dashboard.thresholdEnabled;
    $("dashboard-threshold-metric-label").textContent = `${metricName}@${k}`;
}

function renderExclusionAudit(screenedRows) {
    const audit = $("dashboard-exclusion-audit");
    audit.hidden = !dashboard.thresholdEnabled;
    if (!dashboard.thresholdEnabled) {
        dashboard.excludedRows = [];
        return;
    }
    const classified = screenedRows.map((row) => ({ row, reason: thresholdDecision(row), value: thresholdValue(row) }));
    dashboard.excludedRows = classified.filter((entry) => entry.reason !== "keep")
        .sort((a, b) => (a.reason === "missing") - (b.reason === "missing")
            || (a.value ?? -Infinity) - (b.value ?? -Infinity)
            || a.row.evaluation_id.localeCompare(b.row.evaluation_id, "pt-BR"));
    const below = dashboard.excludedRows.filter((entry) => entry.reason === "below").length;
    const missing = dashboard.excludedRows.length - below;
    const kept = screenedRows.length - dashboard.excludedRows.length;
    $("dashboard-exclusion-summary-text").textContent =
        `${dashboard.excludedRows.length.toLocaleString("pt-BR")} de ${screenedRows.length.toLocaleString("pt-BR")} resultados excluídos · ${kept.toLocaleString("pt-BR")} mantidos`;
    $("dashboard-exclusion-counts").textContent =
        `${below.toLocaleString("pt-BR")} abaixo de ${(dashboard.threshold * 100).toFixed(0)}% · ${missing.toLocaleString("pt-BR")} sem valor de ${$("dashboard-threshold-metric-label").textContent}`;
    $("dashboard-exclusion-details").hidden = dashboard.excludedRows.length === 0;

    const combinations = d3.rollups(dashboard.excludedRows,
        (items) => ({
            cases: items.length,
            queries: new Set(items.map(({ row }) => row.evaluation_id)).size,
            themes: new Set(items.map(({ row }) => themeOf(row))).size,
            below: items.filter((entry) => entry.reason === "below").length,
            missing: items.filter((entry) => entry.reason === "missing").length,
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
    for (const { row, reason, value } of visible) {
        const tr = document.createElement("tr");
        const metricText = value == null ? "—" : `${(value * 100).toFixed(1)}%`;
        const cause = reason === "missing" ? "Métrica indisponível" : `Abaixo de ${(dashboard.threshold * 100).toFixed(0)}%`;
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

function updateFilterOptions(id, values, placeholder, current) {
    const select = $(id);
    const unique = [...new Set(values.filter((value) => value != null && value !== ""))]
        .sort((a, b) => String(a).localeCompare(String(b), "pt-BR", { numeric: true }));
    select.replaceChildren(new Option(placeholder, ""));
    for (const value of unique) select.add(new Option(value, value));
    select.value = unique.map(String).includes(String(current)) ? current : "";
}

function refreshFilterOptions() {
    const restored = dashboard.savedFilters || {};
    const current = {
        ranking: $("dashboard-filter-ranking").value || restored.ranking || "",
        seed: $("dashboard-filter-seed").value || restored.seed || "",
        preset: $("dashboard-filter-preset").value || restored.preset || "",
        quorum: $("dashboard-filter-quorum").value || restored.quorum || "",
        theme: $("dashboard-filter-theme").value || restored.theme || "",
        query: $("dashboard-filter-query").value || restored.query || "",
        formulation: $("dashboard-filter-formulation").value || restored.formulation || "",
    };
    const results = dashboard.rows.map((row) => row.result);
    updateFilterOptions("dashboard-filter-ranking", results.map((row) => row.ranking), "Todos", current.ranking);
    updateFilterOptions("dashboard-filter-seed", results.map((row) => row.seed_method), "Todas", current.seed);
    updateFilterOptions("dashboard-filter-preset", results.map((row) => row.preset), "Todos", current.preset);
    updateFilterOptions("dashboard-filter-quorum", results.map((row) => row.quorum), "Todos", current.quorum);
    updateFilterOptions("dashboard-filter-theme", dashboard.rows.map((row) => row.evaluation_id.split("__", 1)[0]), "Todos", current.theme);
    updateFilterOptions("dashboard-filter-query", dashboard.rows.map((row) => row.evaluation_id), "Todas", current.query);
    updateFilterOptions("dashboard-filter-formulation", dashboard.rows.map((row) => row.query_formulation), "Todas", current.formulation);
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
    const metric = $("dashboard-metric").value;
    const k = $("dashboard-k").value;
    const metricName = { f1: "F1", precision: "Precisão", recall: "Revocação", ndcg: "NDCG", map: "MAP" }[metric] || metric;
    $("dashboard-kpi-quality-label").textContent = `${metricName}@${k} · média macro`;
    $("dashboard-kpi-quality").textContent = Number.isFinite(quality.mean) ? `${(quality.mean * 100).toFixed(1)}%` : "—";
    $("dashboard-kpi-coverage").textContent = Number.isFinite(coverage.mean) ? `${(coverage.mean * 100).toFixed(1)}%` : "—";
    $("dashboard-kpi-quality-note").textContent = `${quality.themeCount} temas · ${quality.queryCount} consultas distintas`;
    $("dashboard-kpi-coverage-note").textContent = `${coverage.themeCount} temas · ${coverage.queryCount} consultas distintas`;
    const partial = ["queued", "running"].includes(dashboard.state?.status) ? "Valores parciais durante a execução. " : "";
    $("dashboard-summary-context").textContent = partial +
        `Média macro das configurações incluídas pelos filtros: cada consulta contribui igualmente dentro do tema e cada tema tem o mesmo peso. ${metricName}@${k}; ` +
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
    const partial = ["queued", "running"].includes(dashboard.state?.status) ? "Resumo provisório: a rodada ainda está em andamento. " : "";
    slot.textContent = partial + `Entre os grupos com cobertura igual (${maximumThemeCount} temas), maior média macro: ${combinationLabel(best)} ` +
        `(${(best.mean * 100).toFixed(1)}%). Menor IQR observado: ` +
        `${combinationLabel(mostConsistent)} (${((mostConsistent.q3 - mostConsistent.q1) * 100).toFixed(1)} p.p.). ` +
        `Isto é descritivo, não um teste de significância; o melhor grupo tem IQR de ${(spread * 100).toFixed(1)} p.p.`;
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
    chart.svg.attr("aria-label", `Média macro de ${$("dashboard-metric").value}@${$("dashboard-k").value} por configuração; ponto é a média entre temas e intervalo é o IQR observado entre temas.`);
    if (note) chart.container.appendChild(note);
    chart.container.style.maxHeight = showAll ? "680px" : "none";
    chart.container.style.overflowY = showAll ? "auto" : "visible";
    const margin = { top: 12, right: 20, bottom: 38, left: Math.min(330, Math.max(210, chart.width * 0.42)) };
    const width = chart.width - margin.left - margin.right;
    const innerHeight = chart.height - margin.top - margin.bottom;
    const x = d3.scaleLinear().domain([0, 1]).range([0, width]);
    const y = d3.scaleBand().domain(selected.map((entry) => entry.key)).range([0, innerHeight]).padding(0.28);
    const labels = new Map(selected.map((entry) => [entry.key, combinationLabel(entry)]));
    const g = chart.svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
    g.append("g").attr("transform", `translate(0,${innerHeight})`).call(d3.axisBottom(x).ticks(5, "%"));
    g.append("g").call(d3.axisLeft(y).tickFormat((key) => labels.get(key)).tickSize(0))
        .selectAll("text").attr("font-size", 9);
    g.append("text").attr("class", "dashboard-axis-label").attr("x", width / 2)
        .attr("y", innerHeight + 31).attr("text-anchor", "middle")
        .text(`${$("dashboard-metric").value.toUpperCase()}@${$("dashboard-k").value} · média macro por tema`);
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
    const color = d3.scaleSequential(d3.interpolateBlues).domain([0, 1]);
    const g = chart.svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
    chart.svg.attr("aria-label", `Mapa de calor de ${$("dashboard-metric").value}@${$("dashboard-k").value} por ranking, seed, preset e quorum.`);
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
        .attr("text-anchor", "middle").attr("font-size", 10).attr("fill", (cell) => cell.mean > 0.58 ? "white" : "#243247")
        .text((cell) => `${(cell.mean * 100).toFixed(0)}%`);
    const legend = document.createElement("div"); legend.className = "dashboard-color-scale";
    const low = document.createElement("span"); low.textContent = "0%";
    const ramp = document.createElement("i"); ramp.setAttribute("aria-label", "Escala sequencial de 0 a 100 por cento");
    const high = document.createElement("span"); high.textContent = "100%";
    legend.append(low, ramp, high); chart.container.appendChild(legend);
}

function renderCoverage(rows) {
    const data = uniqueQueryRows(rows).map((row) => ({ row, x: row.result.coverage?.reference_pool_recall,
        y: metricValue(row) })).filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
    const chart = chartBase("dashboard-coverage");
    if (!data.length) return emptyChart(chart, "Aguardando dados de cobertura.");
    const x = d3.scaleLinear().domain([0, 1]).range([0, chart.innerWidth]);
    const y = d3.scaleLinear().domain([0, 1]).range([chart.innerHeight, 0]);
    const g = chart.svg.append("g").attr("transform", `translate(${chart.margin.left},${chart.margin.top})`);
    chart.svg.attr("aria-label", `Dispersão: cobertura da referência no pool versus ${$("dashboard-metric").value}@${$("dashboard-k").value}.`);
    g.append("g").attr("transform", `translate(0,${chart.innerHeight})`).call(d3.axisBottom(x).ticks(5, "%"));
    g.append("g").call(d3.axisLeft(y).ticks(5, "%"));
    g.append("text").attr("class", "dashboard-axis-label").attr("x", chart.innerWidth / 2)
        .attr("y", chart.innerHeight + 40).attr("text-anchor", "middle").text("Recall da referência no pool");
    g.append("text").attr("class", "dashboard-axis-label").attr("transform", "rotate(-90)")
        .attr("x", -chart.innerHeight / 2).attr("y", -39).attr("text-anchor", "middle")
        .text(`${$("dashboard-metric").value.toUpperCase()}@${$("dashboard-k").value}`);
    const points = g.selectAll("circle").data(data).join("circle")
        .attr("cx", (point) => x(point.x)).attr("cy", (point) => y(point.y)).attr("r", 4.5)
        .attr("fill", (point) => COLORS.get(point.row.result.ranking) || "#64748b")
        .attr("fill-opacity", 0.55).attr("stroke", "#fff").attr("stroke-width", 0.7)
        .attr("tabindex", 0).attr("role", "img")
        .attr("aria-label", (point) => `${point.row.evaluation_id}; ${point.row.result.ranking}, ${point.row.result.seed_method}, ${point.row.result.preset}, quorum ${point.row.result.quorum}; cobertura ${(point.x * 100).toFixed(1)}%, métrica ${(point.y * 100).toFixed(1)}%.`);
    points.append("title").text((point) => `${point.row.evaluation_id} · ${point.row.result.ranking}/${point.row.result.seed_method} · ${point.row.result.preset} · q=${point.row.result.quorum}: cobertura ${(point.x * 100).toFixed(1)}%, ${$("dashboard-metric").value.toUpperCase()}@${$("dashboard-k").value} ${(point.y * 100).toFixed(1)}%`);
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
    const color = d3.scaleSequential(d3.interpolateBlues).domain([0, 1]);
    const g = chart.svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
    chart.svg.attr("aria-label", `Mapa de calor de ${$("dashboard-metric").value}@${$("dashboard-k").value} por tema e ranking.`);
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
        .attr("text-anchor", "middle").attr("font-size", 9).attr("fill", (cell) => cell.mean > 0.58 ? "white" : "#243247")
        .text((cell) => `${(cell.mean * 100).toFixed(0)}%`);
    const legend = document.createElement("div"); legend.className = "dashboard-color-scale";
    legend.innerHTML = "<span>0%</span><i aria-label=\"Escala sequencial de 0 a 100 por cento\"></i><span>100%</span>";
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
    chart.svg.attr("aria-label", `Média macro de ${$("dashboard-metric").value}@${$("dashboard-k").value} por estratégia de formulação. Cada consulta tem peso igual dentro do tema e cada tema tem o mesmo peso.`);
    const margin = { top: 12, right: 22, bottom: 42, left: 210 };
    const width = chart.width - margin.left - margin.right;
    const innerHeight = chart.height - margin.top - margin.bottom;
    const x = d3.scaleLinear().domain([0, 1]).range([0, width]);
    const y = d3.scaleBand().domain(data.map((entry) => entry.formulation))
        .range([0, innerHeight]).padding(0.28);
    const g = chart.svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
    g.append("g").attr("transform", `translate(0,${innerHeight})`).call(d3.axisBottom(x).ticks(5, "%"));
    g.append("g").call(d3.axisLeft(y).tickSize(0));
    g.append("text").attr("class", "dashboard-axis-label").attr("x", width / 2)
        .attr("y", innerHeight + 34).attr("text-anchor", "middle")
        .text(`${$("dashboard-metric").value.toUpperCase()}@${$("dashboard-k").value} · média macro por tema`);
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
    g.append("text").attr("class", "dashboard-axis-label").attr("x", width / 2).attr("y", height + 34).attr("text-anchor", "middle")
        .text(`Δ ${$("dashboard-metric").value.toUpperCase()}@${$("dashboard-k").value} · pontos percentuais vs ${baseline}`);
}

function renderSteps(row) {
    const slot = $("dashboard-step-timing");
    slot.replaceChildren();
    if (!row) {
        $("dashboard-step-caption").textContent = "Selecione uma linha na tabela.";
        return;
    }
    const result = row.result;
    $("dashboard-step-caption").textContent = `${row.evaluation_id} · ${result.ranking}/${result.seed_method}`;
    const actual = result.metrics?.metrics || [];
    const oracle = result.coverage?.oracle_metrics || [];
    if (!actual.length) return;
    const chart = chartBase("dashboard-step-timing", 300);
    chart.svg.attr("aria-label", `Precisão, revocação, F1 e F1 teto do pool nos cortes k da configuração ${row.evaluation_id} · ${result.ranking}/${result.seed_method}.`);
    const margin = { top: 14, right: 15, bottom: 40, left: 48 };
    const width = chart.width - margin.left - margin.right;
    const height = chart.height - margin.top - margin.bottom;
    const cutoffs = actual.map((metric) => metric.k);
    const [minK, maxK] = d3.extent(cutoffs);
    const x = d3.scaleLinear().domain(minK === maxK ? [minK - 0.5, maxK + 0.5] : [minK, maxK]).range([0, width]);
    const y = d3.scaleLinear().domain([0, 1]).range([height, 0]);
    const g = chart.svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
    g.append("g").attr("transform", `translate(0,${height})`)
        .call(d3.axisBottom(x).tickValues(cutoffs).tickFormat(d3.format("d")));
    g.append("g").call(d3.axisLeft(y).ticks(5, "%"));
    const series = [
        { name: "Precisão", key: "precision", color: "#2563eb" },
        { name: "Revocação", key: "recall", color: "#b45309", dash: "5 2" },
        { name: "F1", key: "f1", color: "#7c3aed", dash: "2 2" },
        { name: "F1 teto do pool", key: "oracle_f1", color: "#475569", dash: "4 3" },
    ];
    const line = d3.line().x((point) => x(point.k)).y((point) => y(point.value));
    for (const entry of series) {
        const source = entry.key.startsWith("oracle_") ? oracle : actual;
        const key = entry.key.replace("oracle_", "");
        const points = source.map((metric) => ({ k: metric.k, value: metric[key] })).filter((point) => Number.isFinite(point.value));
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

function renderResultsTable(rows) {
    const body = $("dashboard-results-body");
    body.replaceChildren();
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
    if (!visible.length) {
        const tr = document.createElement("tr"); const td = document.createElement("td");
        td.colSpan = 8; td.className = "dashboard-empty"; td.textContent = "Aguardando resultados.";
        tr.appendChild(td); body.appendChild(tr); return;
    }
    for (const row of visible) {
        const result = row.result;
        const tr = document.createElement("tr");
        tr.classList.toggle("selected", row.seq === dashboard.selectedSeq);
        tr.tabIndex = 0;
        tr.setAttribute("aria-label", `Abrir resultado ${row.evaluation_id}, ranking ${row.result.ranking}, seed ${row.result.seed_method}.`);
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
        body.appendChild(tr);
    }
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
            row.result.preset, row.result.quorum, `${$("dashboard-metric").value}@${$("dashboard-k").value}`,
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

function renderDashboard() {
    renderProgress();
    refreshFilterOptions();
    syncThresholdControls();
    const screenedRows = dimensionFilteredRows();
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
    renderResultsTable(rows);
    if (dashboard.selectedSeq != null) {
        const selected = dashboard.rows.find((row) => row.seq === dashboard.selectedSeq);
        if (selected && rows.some((row) => row.seq === dashboard.selectedSeq)) renderSteps(selected);
        else {
            dashboard.selectedSeq = null;
            renderSteps(null);
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
        dashboard.state = state;
        dashboard.startedAt = Date.parse(state.created_at) || null;
        let hasMore = true;
        while (hasMore) {
            const page = await api(`/dashboard/runs/${dashboard.runId}/results?after=${dashboard.cursor}&limit=200`);
            for (const event of page.events || []) dashboard.rows.push(event);
            dashboard.cursor = page.cursor ?? dashboard.cursor;
            hasMore = page.has_more;
        }
        renderDashboard();
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
    dashboard.runId = runId;
    const saved = getUiState().batchDashboard || {};
    dashboard.savedFilters = saved.runId === runId ? (saved.filters || null) : null;
    dashboard.selectedSeq = saved.runId === runId ? saved.selectedSeq ?? null : null;
    dashboard.restoreSelection = dashboard.selectedSeq != null;
    dashboard.rows = [];
    dashboard.cursor = 0;
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
        k: $("dashboard-k")?.value || "20",
        baseline: $("dashboard-baseline-ranking")?.value || "hybrid_max",
        thresholdEnabled: dashboard.thresholdEnabled,
        threshold: dashboard.threshold,
        selectedSeq: dashboard.selectedSeq,
    });
}

export async function initDashboard() {
    const saved = getUiState().batchDashboard || {};
    const savedSettings = saved.settings || {};
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
    $("dashboard-k").value = saved.k || "20";
    $("dashboard-baseline-ranking").value = saved.baseline || "hybrid_max";
    dashboard.thresholdEnabled = Boolean(saved.thresholdEnabled);
    dashboard.threshold = Number.isFinite(Number(saved.threshold))
        ? Math.min(1, Math.max(0, Number(saved.threshold))) : 0.70;
    constrainMetricCutoffs();
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
        dashboard.threshold = Math.round(Math.min(1, Math.max(0, parsed)) * 100) / 100;
        dashboard.tableLimit = 200;
        dashboard.exclusionLimit = 100;
        renderDashboard();
        persistDashboardUI();
    };
    $("dashboard-threshold-range").addEventListener("input", (event) => changeThreshold(event.currentTarget));
    $("dashboard-threshold-number").addEventListener("change", (event) => changeThreshold(event.currentTarget));
    $("dashboard-show-all-combinations").addEventListener("change", () => renderCombinationLeaderboard(filteredRows()));
    $("dashboard-clear-filters").addEventListener("click", () => {
        for (const id of ["dashboard-filter-ranking", "dashboard-filter-seed", "dashboard-filter-preset",
            "dashboard-filter-quorum", "dashboard-filter-theme", "dashboard-filter-query", "dashboard-filter-formulation"]) {
            $(id).value = "";
        }
        dashboard.thresholdEnabled = false;
        dashboard.threshold = 0.70;
        $("dashboard-exclusion-search").value = "";
        dashboard.tableLimit = 200;
        dashboard.exclusionLimit = 100;
        renderDashboard();
        persistDashboardUI();
    });
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
        "dashboard-filter-quorum", "dashboard-filter-theme", "dashboard-filter-query", "dashboard-filter-formulation",
        "dashboard-k", "dashboard-baseline-ranking"]) $(id).addEventListener("change", () => {
            dashboard.tableLimit = 200;
            renderDashboard();
            persistDashboardUI();
        });
    $("dashboard-metric").addEventListener("change", () => {
        dashboard.tableLimit = 200;
        constrainMetricCutoffs();
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
        if (dashboard.runId && $("panel-dashboard").classList.contains("active")) renderDashboard();
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
