import { getUiState, setUiState } from "./ui_state.js";

const RANKINGS = [
    "ppr", "hybrid_max", "rrf", "cross_encoder", "fused", "mmr", "graph_rwr",
    "graph_hits", "graph_salsa", "graph_path", "graph_walk", "graph_fusion",
    "graph_hits_cross_encoder", "lexical", "vector", "ensemble_rrf",
];
const ENSEMBLE_COMPONENTS = RANKINGS.filter((ranking) => ranking !== "ensemble_rrf");
const SEEDS = ["louvain", "hits", "ppr_top10", "query_entities"];
const GRAPH_RANKINGS = new Set([
    "ppr", "fused", "mmr", "graph_rwr", "graph_hits", "graph_salsa", "graph_path",
    "graph_walk", "graph_fusion", "graph_hits_cross_encoder",
]);
const NON_GRAPH_RANKINGS = new Set(["hybrid_max", "rrf", "cross_encoder", "lexical", "vector"]);
const COHORT_GRAPH_METHODS = [...GRAPH_RANKINGS];
const COHORT_BASELINE_METHODS = [...NON_GRAPH_RANKINGS];
const COHORT_METRICS = [
    ...[1, 3, 5, 10, 20].flatMap((k) => [
        { value: `f1@${k}`, label: `F1@${k}` },
        { value: `precision@${k}`, label: `Precisão@${k}` },
        { value: `recall@${k}`, label: `Revocação@${k}` },
    ]),
    { value: "mrr@20", label: "MRR@20" },
    ...[5, 10, 20].flatMap((k) => [
        { value: `ndcg@${k}`, label: `NDCG@${k}` },
        { value: `map@${k}`, label: `MAP@${k}` },
    ]),
];
const QUERY_ENTITY_SEED = "query_entities";
const PRESETS = ["rapido", "balanceado", "profundo"];
const QUORUMS = [0.3, 0.5, 0.7, 0.9];
const FORMULATION_LABELS = {
    keyword: "Palavras-chave",
    short_theme: "Tema curto",
    specific_keywords: "Palavras-chave específicas",
    broad_theme: "Tema amplo",
    short_question: "Pergunta curta",
    specific_question: "Pergunta específica",
    information_request: "Pedido de informação",
    baseline: "Consulta de referência",
    unspecified: "Sem formulação definida",
};
const FORMULATION_VALUES = Object.keys(FORMULATION_LABELS);
const DASHBOARD_RESULT_FIELDS = new Set([
    "ranking", "seed_method", "preset", "quorum", "result_unit", "metrics",
    "ranking_metrics", "coverage", "computation_seconds", "computation_reused",
    "step_timings", "retrieval_steps", "diagnostics",
]);
const RANKING_PALETTE = [...d3.schemeTableau10, ...d3.schemeDark2];
const COLORS = new Map(RANKINGS.map((name, index) => [name, RANKING_PALETTE[index % RANKING_PALETTE.length]]));
const SEED_INDEPENDENT = new Set(["hybrid_max", "rrf", "cross_encoder", "lexical", "vector"]);

const dashboard = {
    datasets: [], runId: null, runGeneration: 0, runAbort: null,
    rows: [], cursor: 0, state: null, timer: null,
    queryByEvaluationId: new Map(), themeByEvaluationId: new Map(), formulationByEvaluationId: new Map(),
    polling: false, pollingGeneration: null, statusPollFailures: 0,
    figureJobId: null, figureJobTimer: null, figureJobPollFailures: 0,
    figureFilterOptions: null, figureFilterRunKey: "", figureFilterGeneration: 0,
    themeCountArtifact: null,
    themeCountInputThemeSignature: null,
    themeCountPreview: null,
    selectedSeq: null, startedAt: null, savedFilters: null,
    historyLoading: false, historyExpected: 0, historyError: null, historyDone: false,
    restoreSelection: false, tableLimit: 200, tableSort: { key: "seq", direction: "desc" },
    multiFilters: {
        theme: { mode: "include", values: [] },
        formulation: { mode: "include", values: [] },
    },
    thresholdEnabled: false, thresholdMode: "absolute", threshold: 0.70, sdThreshold: -1,
    metricView: "raw", distributionHiddenKeys: new Set(), distributionStats: new Map(),
    distributionSignature: null, distributionObserver: null, excludedRows: [], exclusionLimit: 100,
    cohortGraphMethods: new Set(COHORT_GRAPH_METHODS),
    cohortBaselineMethods: new Set(COHORT_BASELINE_METHODS),
    cohortGraphMetric: "f1@20", cohortBaselineMetric: "f1@20", cohortMenuOpenSide: null,
    lastAnalyticsRenderAt: 0, analyticsRenderTimer: null, stepsRenderedSeq: null,
    incrementalRenderPending: false,
};

const ANALYTICS_RENDER_INTERVAL_MS = 3000;

const $ = (id) => document.getElementById(id);

async function api(url, options = {}) {
    let response;
    try {
        response = await fetch(url, options);
    } catch (error) {
        if (options.signal?.aborted) throw error;
        throw new Error("Falha de rede ao contatar o servidor.");
    }
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || `Erro ${response.status}.`);
    return body;
}

function renderThemeCountArtifact(artifact) {
    const container = $("dashboard-theme-count-results");
    container.replaceChildren();
    if (!artifact?.themes || !Object.keys(artifact.themes).length) return;
    const themeFilter = dashboard.multiFilters?.theme || { mode: "include", values: [] };
    const visibleThemes = Object.entries(artifact.themes)
        .filter(([theme]) => matchesMultiFilter(theme, themeFilter));
    if (!visibleThemes.length) {
        const empty = document.createElement("p");
        empty.className = "dashboard-empty";
        empty.textContent = "Nenhum tema com métrica corresponde ao filtro de temas atual.";
        container.appendChild(empty);
        return;
    }
    const caption = document.createElement("p");
    caption.className = "dashboard-muted";
    caption.textContent = `${artifact.date_range
        ? `Período ${artifact.date_range.from} a ${artifact.date_range.to}`
        : "Período indicado por tema"} · artigos com texto integral no denominador ·
        correspondência de todas as entidades. Dificuldade maior indica maior prevalência de artigos.`;
    const table = document.createElement("table");
    const head = document.createElement("thead");
    const header = document.createElement("tr");
    for (const title of ["Tema", "Entidades principais", "Identidades resolvidas", "Período",
        "Correspondentes / elegíveis", "Dificuldade v3 (0–1)", "Auditoria"]) {
        const th = document.createElement("th"); th.textContent = title; header.appendChild(th);
    }
    head.appendChild(header);
    const body = document.createElement("tbody");
    for (const [theme, result] of visibleThemes) {
        const row = document.createElement("tr");
        const difficulty = result.difficulty_score == null ? NaN : Number(result.difficulty_score);
        const difficultyLabel = Number.isFinite(difficulty) ? difficulty.toFixed(5) : "—";
        for (const value of [theme, (result.main_entities || []).join(" + "), result.entities.join(" + "),
            `${result.date_range.from} a ${result.date_range.to}`,
            `${Number(result.matching_articles_count ?? result.article_count).toLocaleString("pt-BR")} / ${Number(result.eligible_articles_count ?? artifact.eligible_articles_count).toLocaleString("pt-BR")}`,
            difficultyLabel]) {
            const cell = document.createElement("td"); cell.textContent = value; row.appendChild(cell);
        }
        const auditCell = document.createElement("td");
        if (result.eligibility_snapshot_id && dashboard.runId) {
            const link = document.createElement("a");
            link.href = `/dashboard/runs/${dashboard.runId}/theme-counts/eligibility/${result.eligibility_snapshot_id}`;
            link.target = "_blank";
            link.rel = "noopener";
            link.textContent = "URLs e contagens";
            auditCell.appendChild(link);
        } else {
            auditCell.textContent = "—";
        }
        row.appendChild(auditCell);
        body.appendChild(row);
    }
    table.append(head, body);
    const updated = document.createElement("p");
    updated.className = "dashboard-muted";
    const coverageSummary = artifact.entity_indexed_articles_count == null
        || artifact.eligible_articles_count == null
        ? "Cobertura de entidades varia por tema/período."
        : `Artigos com entidades indexadas: ${Number(artifact.entity_indexed_articles_count).toLocaleString("pt-BR")}`
            + ` de ${Number(artifact.eligible_articles_count).toLocaleString("pt-BR")} elegíveis.`;
    updated.textContent = `Calculado em ${artifact.computed_at || "data não registrada"}. ${coverageSummary}`;
    container.append(caption, table, updated);
    renderThemeDifficultyChart(container, { ...artifact, themes: Object.fromEntries(visibleThemes) });
    renderThemeDifficultyPerformance(dimensionFilteredRows());
    for (const input of $("dashboard-theme-count-inputs").querySelectorAll("[data-theme-id]")) {
        const saved = artifact.themes[input.dataset.themeId]?.main_entities
            || artifact.themes[input.dataset.themeId]?.entities;
        if (!input.value.trim() && saved) input.value = saved.join(", ");
    }
}

function renderThemeDifficultyChart(container, artifact) {
    const data = Object.entries(artifact.themes || {}).map(([theme, result]) => ({
        theme, score: result.difficulty_score == null ? NaN : Number(result.difficulty_score),
        matching: Number(result.matching_articles_count ?? result.article_count),
        eligible: Number(result.eligible_articles_count ?? artifact.eligible_articles_count),
    })).filter((item) => Number.isFinite(item.score));
    if (!data.length) return;
    data.sort((a, b) => b.score - a.score || a.theme.localeCompare(b.theme, "pt-BR"));
    const heading = document.createElement("h4");
    heading.textContent = "Dificuldade por tema";
    const chartContainer = document.createElement("div");
    chartContainer.className = "dashboard-theme-difficulty-chart";
    container.append(heading, chartContainer);
    const margin = { top: 8, right: 24, bottom: 35, left: 220 };
    const width = Math.max(640, chartContainer.clientWidth || 640);
    const height = Math.max(220, data.length * 30 + margin.top + margin.bottom);
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;
    const x = d3.scaleLinear().domain([0, 1]).range([0, innerWidth]);
    const y = d3.scaleBand().domain(data.map((item) => item.theme))
        .range([0, innerHeight]).padding(0.22);
    const svg = d3.select(chartContainer).append("svg")
        .attr("viewBox", `0 0 ${width} ${height}`).attr("role", "img")
        .attr("aria-label", "Dificuldade de cada tema, calculada como a razão logarítmica entre artigos correspondentes e artigos elegíveis.");
    const group = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
    group.append("g").attr("transform", `translate(0,${innerHeight})`)
        .call(d3.axisBottom(x).ticks(5).tickFormat(d3.format(".1f")));
    group.append("g").call(d3.axisLeft(y).tickSize(0));
    group.selectAll("rect").data(data).join("rect")
        .attr("x", 0).attr("y", (item) => y(item.theme))
        .attr("width", (item) => x(item.score)).attr("height", y.bandwidth())
        .attr("rx", 3).attr("fill", "#527da8").attr("tabindex", 0).attr("role", "img")
        .attr("aria-label", (item) => `${item.theme}: dificuldade ${item.score.toFixed(5)}; ${item.matching} de ${item.eligible} artigos elegíveis.`)
        .append("title")
        .text((item) => `${item.theme}: ${item.score.toFixed(5)} · ${item.matching}/${item.eligible} artigos`);
    group.append("text").attr("class", "dashboard-axis-label")
        .attr("x", innerWidth / 2).attr("y", innerHeight + 31).attr("text-anchor", "middle")
        .text("Dificuldade · log(1 + correspondentes) / log(1 + elegíveis) (0–1)");
}

function refreshThemeCountArtifactForThemeFilter() {
    if (dashboard.themeCountArtifact) renderThemeCountArtifact(dashboard.themeCountArtifact);
}

function renderThemeCountInputs(themeIds, savedThemes = {}) {
    const uniqueIds = [...new Set(themeIds)].sort((a, b) => a.localeCompare(b, "pt-BR"));
    const signature = uniqueIds.join("\u0000");
    const container = $("dashboard-theme-count-inputs");
    if (dashboard.themeCountInputThemeSignature === signature) return;
    const currentValues = new Map([...container.querySelectorAll("[data-theme-id]")]
        .map((input) => [input.dataset.themeId, input.value]));
    container.replaceChildren();
    dashboard.themeCountInputThemeSignature = signature;
    for (const themeId of uniqueIds) {
        const row = document.createElement("label");
        row.className = "dashboard-theme-count-row";
        const name = document.createElement("span");
        name.className = "dashboard-theme-count-name";
        name.textContent = themeId;
        const input = document.createElement("input");
        input.type = "text";
        input.dataset.themeId = themeId;
        input.placeholder = "Entidades separadas por vírgulas";
        input.autocomplete = "off";
        input.value = currentValues.get(themeId)
            ?? savedThemes[themeId]?.entities?.join(", ")
            ?? (Array.isArray(dashboard.state?.theme_main_entities?.[themeId])
                ? dashboard.state.theme_main_entities[themeId].join(", ") : null)
            ?? dashboard.themeCountArtifact?.themes?.[themeId]?.entities?.join(", ")
            ?? "";
        row.append(name, input);
        container.appendChild(row);
    }
}

function currentThemeCountIds() {
    const fromSnapshot = dashboard.state?.theme_ids || [];
    if (fromSnapshot.length) return fromSnapshot;
    return [...new Set(dashboard.rows.map((row) => themeOf(row)).filter(Boolean))];
}

async function loadThemeCountArtifact(runId = dashboard.runId) {
    if (!runId) return;
    try {
        const response = await api(`/dashboard/runs/${runId}/theme-counts`);
        if (dashboard.runId !== runId) return;
        dashboard.themeCountArtifact = response.artifact;
        renderThemeCountArtifact(response.artifact);
    } catch (error) {
        $("dashboard-theme-count-message").textContent = error.message;
    }
}

function themeCountMappingFromDocument(documentValue, runId) {
    let mapping = documentValue;
    if (documentValue && typeof documentValue === "object" && Array.isArray(documentValue.runs)) {
        const run = documentValue.runs.find((item) => item?.run_id === runId);
        if (!run) throw new Error(`O arquivo não contém a rodada atual (${runId}).`);
        mapping = run.themes;
    } else if (documentValue?.themes && typeof documentValue.themes === "object"
        && !Array.isArray(documentValue.themes)) {
        mapping = documentValue.themes;
    }
    if (!mapping || typeof mapping !== "object" || Array.isArray(mapping)) {
        throw new Error("O JSON deve conter um mapeamento de temas para listas de entidades.");
    }

    const themes = {};
    for (const [theme, value] of Object.entries(mapping)) {
        const entities = Array.isArray(value) ? value : value?.entities;
        if (!theme.trim() || !Array.isArray(entities)
            || entities.some((entity) => typeof entity !== "string")) {
            throw new Error(`O mapeamento do tema “${theme}” deve conter uma lista de entidades em texto.`);
        }
        themes[theme.trim()] = [...new Set(entities.map((entity) => entity.trim()).filter(Boolean))];
    }
    if (!Object.keys(themes).length) throw new Error("O JSON não contém temas para preencher.");
    return themes;
}

async function loadThemeCountFile(file) {
    if (!file) return;
    const status = $("dashboard-theme-count-message");
    try {
        const parsed = JSON.parse(await file.text());
        const themes = themeCountMappingFromDocument(parsed, dashboard.runId);
        let themeIds = currentThemeCountIds();
        if (!themeIds.length) {
            themeIds = Object.keys(themes);
            renderThemeCountInputs(themeIds);
        }
        const known = new Set(themeIds);
        const unknown = Object.keys(themes).filter((theme) => !known.has(theme));
        if (unknown.length) throw new Error(`Temas não presentes nesta rodada: ${unknown.join(", ")}`);

        for (const input of $("dashboard-theme-count-inputs").querySelectorAll("[data-theme-id]")) {
            if (Object.hasOwn(themes, input.dataset.themeId)) {
                input.value = themes[input.dataset.themeId].join(", ");
            }
        }
        dashboard.themeCountPreview = null;
        $("dashboard-theme-count-preview-results").replaceChildren();
        $("dashboard-theme-count-preview-results").hidden = true;
        $("dashboard-theme-count-submit").hidden = true;
        status.textContent = "JSON carregado nos campos. Ajuste as entidades se necessário e gere a prévia para continuar.";
    } catch (error) {
        status.textContent = `Não foi possível carregar o JSON: ${error.message}`;
    } finally {
        $("dashboard-theme-count-file").value = "";
    }
}

function readThemeCountInputs() {
    const themes = {};
    const fields = [...$("dashboard-theme-count-inputs").querySelectorAll("[data-theme-id]")];
    if (!fields.length) throw new Error("Esta rodada não contém temas disponíveis para contar.");
    for (const input of fields) {
        const entities = input.value.split(",").map((value) => value.trim()).filter(Boolean);
        if (!entities.length) {
            input.focus();
            throw new Error(`Informe ao menos uma entidade para o tema “${input.dataset.themeId}”.`);
        }
        themes[input.dataset.themeId] = entities;
    }
    return themes;
}

function renderThemeCountPreview(preview) {
    const container = $("dashboard-theme-count-preview-results");
    container.replaceChildren();
    const table = document.createElement("table");
    const head = document.createElement("thead");
    const header = document.createElement("tr");
    for (const title of ["Tema", "Informada", "Entidade identificada", "Identidade para contagem"]) {
        const th = document.createElement("th");
        th.textContent = title;
        header.appendChild(th);
    }
    head.appendChild(header);
    const body = document.createElement("tbody");
    for (const [theme, entries] of Object.entries(preview.themes || {})) {
        for (const entry of entries) {
            for (const match of entry.matches) {
                const row = document.createElement("tr");
                const resolution = match.resolution === "canonical"
                    ? "URI canônica"
                    : match.resolution === "ner_unavailable"
                        ? "NER indisponível · texto exato"
                        : match.resolution === "not_detected"
                            ? "Não identificada · texto exato"
                            : "Sem URI canônica · texto exato";
                const values = [theme, entry.input,
                    match.label ? `${match.text} (${match.label})` : match.text,
                    `${match.identity} — ${resolution}`];
                for (const value of values) {
                    const cell = document.createElement("td");
                    cell.textContent = value;
                    row.appendChild(cell);
                }
                body.appendChild(row);
            }
        }
    }
    table.append(head, body);
    const note = document.createElement("p");
    note.className = "dashboard-muted";
    note.textContent = "Confira as identidades acima. A contagem só será executada depois da confirmação.";
    container.append(note, table);
    container.hidden = false;
    $("dashboard-theme-count-submit").hidden = false;
}

function themeCountDateRange() {
    const from = $("dashboard-theme-count-from").value;
    const to = $("dashboard-theme-count-to").value;
    if (Boolean(from) !== Boolean(to)) {
        throw new Error("Informe as duas datas ou deixe ambas vazias para usar o período salvo na rodada.");
    }
    return from ? { from, to } : null;
}

async function previewThemeCounts() {
    if (!dashboard.runId) return;
    const status = $("dashboard-theme-count-message");
    const button = $("dashboard-theme-count-preview");
    try {
        const themes = readThemeCountInputs();
        const runId = dashboard.runId;
        const inputSignature = JSON.stringify(themes);
        themeCountDateRange();
        dashboard.themeCountPreview = null;
        $("dashboard-theme-count-preview-results").hidden = true;
        $("dashboard-theme-count-submit").hidden = true;
        button.disabled = true;
        status.textContent = "Identificando entidades e buscando identidades canônicas…";
        const response = await api(`/dashboard/runs/${runId}/theme-counts/preview`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ themes }),
        });
        if (dashboard.runId !== runId || JSON.stringify(readThemeCountInputs()) !== inputSignature) {
            status.textContent = "A rodada ou as entidades mudaram durante a identificação. Gere uma nova prévia.";
            return;
        }
        dashboard.themeCountPreview = response;
        renderThemeCountPreview(response);
        status.textContent = "Prévia pronta. Revise os resultados e confirme para iniciar a contagem.";
    } catch (error) {
        status.textContent = error.message;
    } finally {
        button.disabled = dashboard.state?.status !== "completed";
    }
}

async function attachThemeCounts() {
    if (!dashboard.runId || !dashboard.themeCountPreview) return;
    const status = $("dashboard-theme-count-message");
    const button = $("dashboard-theme-count-submit");
    const runId = dashboard.runId;
    button.disabled = true;
    $("dashboard-theme-count-preview").disabled = true;
    status.textContent = "Contando artigos e salvando o resultado…";
    try {
        const dateRange = themeCountDateRange();
        const themes = Object.fromEntries(
            Object.entries(dashboard.themeCountPreview.themes).map(([theme, entries]) => [
                theme,
                [...new Set(entries.flatMap((entry) =>
                    entry.matches.map((match) => match.identity)))],
            ]),
        );
        const main_entities = Object.fromEntries(Object.entries(dashboard.themeCountPreview.themes).map(
            ([theme, entries]) => [theme, entries.map((entry) => entry.input)],
        ));
        const body = { themes, main_entities, entity_resolution: dashboard.themeCountPreview.themes };
        if (dateRange) body.date_range = dateRange;
        const result = await api(`/dashboard/runs/${runId}/theme-counts`, {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        });
        if (dashboard.runId !== runId) return;
        dashboard.themeCountArtifact = result.artifact;
        renderThemeCountArtifact(result.artifact);
        status.textContent = "Contagem salva com a rodada.";
    } catch (error) {
        status.textContent = error.message;
    } finally {
        button.disabled = dashboard.state?.status !== "completed";
        $("dashboard-theme-count-preview").disabled = dashboard.state?.status !== "completed";
    }
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
    if (metric === "mrr") return row.result.ranking_metrics?.["mrr@20"] ?? null;
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
    return ({ f1: "F1", precision: "Precisão", recall: "Revocação", mrr: "MRR", ndcg: "NDCG", map: "MAP" })[
        $("dashboard-metric").value
    ] || $("dashboard-metric").value;
}

function metricDisplayLabel() {
    const label = `${metricBaseLabel()}@${$("dashboard-metric").value === "mrr" ? 20 : $("dashboard-k").value}`;
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

function dimensionFilteredRows({ ignoreRanking = false, ignoreSeed = false } = {}) {
    const filters = filtersFromUI();
    return dashboard.rows.filter((row) => {
        const result = row.result;
        return (ignoreRanking || !filters.ranking || result.ranking === filters.ranking)
            && (ignoreSeed || !filters.seed || result.seed_method === filters.seed)
            && (!filters.preset || result.preset === filters.preset)
            && (!filters.quorum || String(result.quorum) === filters.quorum)
            && matchesMultiFilter(themeOf(row), filters.theme)
            && (!filters.query || row.evaluation_id === filters.query)
            && matchesMultiFilter(formulationFor(row), filters.formulation);
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
        row.evaluation_id, themeOf(row), queryFor(row), row.result.ranking, row.result.seed_method,
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
        const values = [row.evaluation_id, queryFor(row), themeOf(row), row.result.ranking, row.result.seed_method,
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
        ? type === "formulation"
            ? `${label} · ${filter.values.length} selecionada(s)`
            : `${label} · ${filter.mode === "exclude" ? "excluindo" : "incluindo"} ${filter.values.length}`
        : `${label} · todos`;
}

function facetOptionLabel(type, value) {
    return type === "formulation" ? (FORMULATION_LABELS[value] || value) : value;
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
                if (type === "theme") refreshThemeCountArtifactForThemeFilter();
                persistDashboardUI();
            });
            const text = document.createElement("span");
            text.textContent = facetOptionLabel(type, value);
            if (type === "formulation") label.title = value;
            label.append(input, text);
            container.appendChild(label);
            present.add(value);
        }
        const checkbox = label.querySelector("input");
        checkbox.checked = filter.values.includes(value);
        const text = label.querySelector("span");
        text.textContent = available.includes(value)
            ? facetOptionLabel(type, value)
            : `${facetOptionLabel(type, value)} · sem resultados neste recorte`;
    }
    updateFacetSummary(type);
}

function restoreFacetFilter(savedValue, type = "theme") {
    if (typeof savedValue === "string") return { mode: "include", values: savedValue ? [savedValue] : [] };
    if (savedValue && typeof savedValue === "object") {
        const values = Array.isArray(savedValue.values) ? savedValue.values.map(String) : [];
        // Migrate the former formulation exclude-mode to the new include-only
        // control, preserving its meaning for the built-in formulation set.
        if (type === "formulation" && savedValue.mode === "exclude") {
            return { mode: "include", values: FORMULATION_VALUES.filter((value) => !values.includes(value)) };
        }
        return {
            mode: type === "theme" && savedValue.mode === "exclude" ? "exclude" : "include",
            values,
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
    syncFacetOptions("formulation", dashboard.rows.map(formulationFor));
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
        $("dashboard-pause-run").hidden = true;
        $("dashboard-resume-run").hidden = true;
        $("dashboard-theme-count-submit").disabled = true;
        $("dashboard-theme-count-preview").disabled = true;
        return;
    }
    renderThemeCountInputs(currentThemeCountIds(), dashboard.themeCountArtifact?.themes || {});
    const progress = state.progress || {};
    const completed = progress.completed || 0;
    const total = progress.total || 0;
    const terminal = ["completed", "failed", "interrupted", "paused"].includes(state.status);
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
    $("dashboard-pause-run").hidden = !["queued", "running"].includes(state.status);
    $("dashboard-pause-run").disabled = !["queued", "running"].includes(state.status);
    $("dashboard-resume-run").hidden = !["paused", "interrupted", "failed"].includes(state.status);
    $("dashboard-theme-count-submit").disabled = state.status !== "completed";
    $("dashboard-theme-count-preview").disabled = state.status !== "completed";
    $("dashboard-kpi-completed").textContent = `${completed.toLocaleString("pt-BR")} / ${total.toLocaleString("pt-BR")}`;
    $("dashboard-kpi-elapsed").textContent = formatElapsed(elapsed);
    $("dashboard-kpi-elapsed-note").textContent = terminal
        ? "duração da rodada" : "tempo decorrido";
}

function renderHistorySync() {
    const container = $("dashboard-history-sync");
    if (!container) return;
    const state = dashboard.state;
    container.hidden = !dashboard.historyLoading && !dashboard.historyError && !state;
    document.body.classList.toggle("dashboard-sync-active", !container.hidden);
    const label = $("dashboard-history-sync-label");
    const progress = $("dashboard-history-sync-progress");
    const retry = $("dashboard-history-sync-retry");
    if (dashboard.historyError) {
        const completed = Number(state?.progress?.completed) || 0;
        const total = Number(state?.progress?.total) || 0;
        label.textContent = `${state ? `Rodada ${state.status}: ${completed.toLocaleString("pt-BR")}/${total.toLocaleString("pt-BR")} · ` : ""}Falha ao carregar histórico: ${dashboard.historyError}`;
        retry.hidden = false;
        progress.hidden = true;
        return;
    }
    retry.hidden = true;
    progress.hidden = false;
    if (!state && dashboard.cursor === 0) {
        label.textContent = "Conectando à rodada…";
        progress.max = 1;
        progress.value = 0;
        return;
    }
    const loaded = dashboard.cursor;
    const expected = Math.max(dashboard.historyExpected, loaded);
    const completed = Number(state?.progress?.completed) || 0;
    const total = Number(state?.progress?.total) || 0;
    label.textContent = dashboard.historyLoading
        ? `Rodada ${state?.status || "abrindo"}: ${completed.toLocaleString("pt-BR")}/${total.toLocaleString("pt-BR")} · carregando histórico ${loaded.toLocaleString("pt-BR")}/${expected.toLocaleString("pt-BR")}`
        : `Rodada ${state.status}: ${completed.toLocaleString("pt-BR")}/${total.toLocaleString("pt-BR")} resultados · ${loaded.toLocaleString("pt-BR")} carregados no painel`;
    progress.max = Math.max(1, dashboard.historyLoading ? expected : total);
    progress.value = Math.min(dashboard.historyLoading ? loaded : completed, progress.max);
}

function themeOf(row) {
    return dashboard.themeByEvaluationId.get(row.evaluation_id)
        || row.theme || row.evaluation_id.split("__", 1)[0];
}

function queryFor(row) {
    return dashboard.queryByEvaluationId.get(row.evaluation_id) || row.query || "";
}

function formulationFor(row) {
    return dashboard.formulationByEvaluationId.get(row.evaluation_id)
        || row.query_formulation || "unspecified";
}

function compactDashboardEvent(event) {
    // Keep full rankings and rich diagnostics on the server. Analytics only
    // needs these compact metric/configuration fields in the browser.
    const evaluationId = event.evaluation_id;
    if (typeof event.query === "string") dashboard.queryByEvaluationId.set(evaluationId, event.query);
    if (typeof event.theme === "string") dashboard.themeByEvaluationId.set(evaluationId, event.theme);
    if (typeof event.query_formulation === "string") {
        dashboard.formulationByEvaluationId.set(evaluationId, event.query_formulation);
    }
    delete event.query;
    delete event.theme;
    delete event.query_formulation;
    const result = event.result || {};
    for (const key of Object.keys(result)) if (!DASHBOARD_RESULT_FIELDS.has(key)) delete result[key];
    if (result.coverage) {
        const coverage = result.coverage;
        result.coverage = {
            reference_pool_recall: coverage.reference_pool_recall,
            oracle_metrics: coverage.oracle_metrics,
        };
    }
    if (result.diagnostics) {
        result.diagnostics = result.diagnostics.ensemble_rankings
            ? { ensemble_rankings: result.diagnostics.ensemble_rankings } : {};
    }
    event.result = result;
    return event;
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
    const plots = $("dashboard-metric-distribution");
    const currentSeq = rows.length ? rows[rows.length - 1].seq : 0;
    const signature = JSON.stringify([
        dashboard.runId, rows.length, currentSeq, metricDisplayLabel(), dashboard.metricView,
        filtersFromUI(), dashboard.thresholdEnabled, dashboard.thresholdMode,
        dashboard.threshold, dashboard.sdThreshold,
        [...dashboard.distributionHiddenKeys].sort(), plots.clientWidth,
    ]);
    if (signature === dashboard.distributionSignature) return;
    dashboard.distributionSignature = signature;

    dashboard.distributionObserver?.disconnect();
    dashboard.distributionObserver = null;
    dashboard.distributionStats = buildMetricDistributions(rows);
    const entries = [...dashboard.distributionStats.values()].sort((a, b) =>
        distributionLabel(a).localeCompare(distributionLabel(b), "pt-BR"));
    const options = $("dashboard-distribution-options");
    options.replaceChildren();
    for (const entry of entries) {
        const label = document.createElement("label");
        label.className = "dashboard-distribution-option";
        const input = document.createElement("input");
        input.type = "checkbox";
        input.value = entry.key;
        input.checked = !dashboard.distributionHiddenKeys.has(entry.key);
        input.addEventListener("change", () => {
            if (input.checked) dashboard.distributionHiddenKeys.delete(entry.key);
            else dashboard.distributionHiddenKeys.add(entry.key);
            renderMetricDistribution(dimensionFilteredRows());
            persistDashboardUI();
        });
        const text = document.createElement("span");
        text.textContent = `${distributionLabel(entry)} · n=${entry.n}`;
        label.append(input, text);
        options.appendChild(label);
    }

    const visible = entries.filter((entry) => !dashboard.distributionHiddenKeys.has(entry.key));
    $("dashboard-distribution-count").textContent =
        `${visible.length} de ${entries.length} configurações exibidas`;
    plots.replaceChildren();
    if (!entries.length) {
        plots.textContent = "Sem valores de métrica para os filtros atuais.";
        return;
    }
    if (!visible.length) {
        plots.textContent = "Todas as distribuições estão ocultas. Marque uma configuração ou use “Mostrar todas”.";
        return;
    }

    const metric = metricDisplayLabel();
    const distributionMaximum = d3.max(entries, (entry) => d3.max(entry.values)) || 1;
    const domainMax = dashboard.metricView === "oracle"
        ? Math.max(1, Math.ceil(distributionMaximum * 4) / 4) : 1;
    const thresholds = d3.range(1, 20).map((index) => domainMax * index / 20);
    const binned = new Map(entries.map((entry) => [entry.key,
        d3.bin().domain([0, domainMax]).thresholds(thresholds)(entry.values)]));
    let maxFraction = 0;
    for (const entry of entries) {
        for (const bin of binned.get(entry.key)) maxFraction = Math.max(maxFraction, bin.length / entry.n);
    }
    maxFraction ||= 0.1;
    const yMax = Math.min(1, maxFraction * 1.12);

    const renderPanel = (slot, summary) => {
        if (slot.dataset.rendered === "true") return;
        slot.replaceChildren();
        slot.dataset.rendered = "true";
        const chart = chartBase(slot.id, 250);
        const margin = { top: 12, right: 12, bottom: 39, left: 52 };
        const width = chart.width - margin.left - margin.right;
        const height = chart.height - margin.top - margin.bottom;
        const x = d3.scaleLinear().domain([0, domainMax]).range([0, width]);
        const y = d3.scaleLinear().domain([0, yMax]).range([height, 0]);
        const g = chart.svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
        chart.svg.attr("aria-label", `Distribuição de ${metric} para ${distributionLabel(summary)}, n=${summary.n}.`);
        g.append("g").attr("transform", `translate(0,${height})`).call(d3.axisBottom(x).ticks(6, "%"));
        g.append("g").call(d3.axisLeft(y).ticks(4, "%"));
        const bins = binned.get(summary.key);
        g.selectAll("rect.metric-bin").data(bins).join("rect")
            .attr("class", "metric-bin")
            .attr("x", (bin) => x(bin.x0) + 1)
            .attr("y", (bin) => y(bin.length / summary.n))
            .attr("width", (bin) => Math.max(0, x(bin.x1) - x(bin.x0) - 2))
            .attr("height", (bin) => height - y(bin.length / summary.n))
            .attr("fill", "#a5b4fc").attr("stroke", "#4f46e5").attr("stroke-width", 0.7)
            .attr("tabindex", 0).attr("role", "img")
            .attr("aria-label", (bin) => `${(bin.x0 * 100).toFixed(0)} a ${(bin.x1 * 100).toFixed(0)} por cento: ${(bin.length / summary.n * 100).toFixed(1)}% das consultas.`)
            .append("title").text((bin) => `${(bin.x0 * 100).toFixed(0)}–${(bin.x1 * 100).toFixed(0)}%: ${bin.length} consultas (${(bin.length / summary.n * 100).toFixed(1)}%)`);

        const markers = [
            { label: "Média", value: summary.mean, color: "#4338ca", dash: null },
            { label: "Média − 1σ", value: summary.mean - summary.sd, color: "#64748b", dash: "4 3" },
            { label: "Média + 1σ", value: summary.mean + summary.sd, color: "#64748b", dash: "4 3" },
        ];
        if (dashboard.thresholdEnabled) {
            markers.push(dashboard.thresholdMode === "sd"
                ? { label: `Corte z=${dashboard.sdThreshold.toFixed(1)}σ`, value: summary.mean + dashboard.sdThreshold * summary.sd, color: "#d97706", dash: "2 2" }
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
    };

    const slots = [];
    visible.forEach((summary, index) => {
        const panel = document.createElement("section");
        panel.className = "dashboard-distribution-panel";
        const heading = document.createElement("h4");
        heading.textContent = distributionLabel(summary);
        const stats = document.createElement("p");
        stats.className = "dashboard-muted";
        const incomplete = summary.n < 2 || !(summary.sd > 0);
        stats.textContent = `n=${summary.n} consultas · média ${(summary.mean * 100).toFixed(1)}% · mediana ${(summary.median * 100).toFixed(1)}% · desvio padrão ${(summary.sd * 100).toFixed(1)} p.p.${incomplete ? " · sem variação suficiente para z-score" : ""}`;
        const chartSlot = document.createElement("div");
        chartSlot.id = `dashboard-distribution-plot-${index}`;
        chartSlot.className = "dashboard-distribution-plot";
        chartSlot.textContent = "Gráfico carregado ao rolar até aqui.";
        chartSlot.dataset.rendered = "false";
        panel.append(heading, stats, chartSlot);
        plots.appendChild(panel);
        slots.push({ panel, chartSlot, summary });
    });

    if ("IntersectionObserver" in window) {
        dashboard.distributionObserver = new IntersectionObserver((observations) => {
            for (const observation of observations) {
                const { chartSlot, summary } = observation.target.__distributionData;
                if (observation.isIntersecting) renderPanel(chartSlot, summary);
                else if (chartSlot.dataset.rendered === "true") {
                    chartSlot.replaceChildren();
                    chartSlot.textContent = "Gráfico carregado ao rolar até aqui.";
                    chartSlot.dataset.rendered = "false";
                }
            }
        }, { rootMargin: "700px 0px" });
        for (const slot of slots) {
            slot.panel.__distributionData = slot;
            dashboard.distributionObserver.observe(slot.panel);
        }
    } else {
        for (const slot of slots) renderPanel(slot.chartSlot, slot.summary);
    }
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

function renderThemeDifficultyPerformance(rows) {
    const metricDefinitions = [
        {
            key: "f1@20", label: "F1@20", color: "#527da8",
            value: (row) => row.result.metrics?.metrics?.find((item) => item.k === 20)?.f1 ?? null,
        },
        { key: "mrr@20", label: "MRR@20", color: "#2a9d8f",
            value: (row) => row.result.ranking_metrics?.["mrr@20"] ?? null },
        { key: "ndcg@20", label: "NDCG@20", color: "#d98e32",
            value: (row) => row.result.ranking_metrics?.["ndcg@20"] ?? null },
    ];
    const difficultyThemes = Object.entries(dashboard.themeCountArtifact?.themes || {})
        .filter(([theme]) => matchesMultiFilter(theme, dashboard.multiFilters.theme))
        .map(([theme, result]) => ({
            theme,
            difficulty: result.difficulty_score == null ? NaN : Number(result.difficulty_score),
            matching: Number(result.matching_articles_count ?? result.article_count),
            eligible: Number(result.eligible_articles_count ?? dashboard.themeCountArtifact.eligible_articles_count),
        }))
        .filter((item) => Number.isFinite(item.difficulty));
    if (!difficultyThemes.length) {
        const chart = chartBase("dashboard-theme-difficulty-performance", 320, 1000);
        emptyChart(chart, dashboard.themeCountArtifact
            ? "Sem temas selecionados com dificuldade e desempenho disponíveis."
            : "Calcule as contagens de entidades para mostrar a dificuldade por tema.");
        return;
    }

    const performanceByTheme = new Map();
    for (const metric of metricDefinitions) {
        const queryMeans = d3.rollups(
            uniqueQueryRows(rows, metric.value),
            (items) => d3.mean(items, metric.value),
            themeOf,
            (row) => row.evaluation_id,
        );
        performanceByTheme.set(metric.key, new Map(queryMeans.map(([theme, queries]) => [
            theme, d3.mean(queries, (entry) => entry[1]),
        ])));
    }
    const data = difficultyThemes.map((theme) => ({
        ...theme,
        values: Object.fromEntries(metricDefinitions.map((metric) => [
            metric.key, performanceByTheme.get(metric.key).get(theme.theme) ?? null,
        ])),
    })).sort((a, b) => a.difficulty - b.difficulty || a.theme.localeCompare(b.theme, "pt-BR"));
    const rowHeight = 30;
    const marginTop = 42;
    const marginBottom = 48;
    const height = Math.max(300, marginTop + data.length * rowHeight + marginBottom);
    const chart = chartBase("dashboard-theme-difficulty-performance", height, 1140);
    chart.svg.attr("aria-label", "Matriz de pontos: temas ordenados por dificuldade, com F1@20, MRR@20 e NDCG@20. As consultas têm peso igual dentro de cada tema.");
    const themeColumn = 190;
    const difficultyColumn = 95;
    const countsColumn = 130;
    const metricStart = themeColumn + difficultyColumn + countsColumn;
    const metricWidth = (chart.width - metricStart - 12) / metricDefinitions.length;
    const rowEnd = marginTop + data.length * rowHeight;
    const y = d3.scaleBand().domain(data.map((item) => item.theme))
        .range([marginTop, rowEnd]).padding(0.18);

    chart.svg.append("text").attr("x", 8).attr("y", 25).attr("class", "dashboard-chart-column-heading")
        .text("Tema · mais fácil → mais difícil");
    chart.svg.append("text").attr("x", themeColumn + 5).attr("y", 25).attr("class", "dashboard-chart-column-heading")
        .text("Dificuldade");
    chart.svg.append("text").attr("x", themeColumn + difficultyColumn + 5).attr("y", 25).attr("class", "dashboard-chart-column-heading")
        .text("Match / elegíveis");

    for (const [metricIndex, metric] of metricDefinitions.entries()) {
        const start = metricStart + metricIndex * metricWidth;
        const x = d3.scaleLinear().domain([0, 1]).range([start + 8, start + metricWidth - 10]);
        chart.svg.append("text").attr("x", start + metricWidth / 2).attr("y", 25)
            .attr("text-anchor", "middle").attr("class", "dashboard-chart-column-heading")
            .text(metric.label);
        chart.svg.append("g").attr("transform", `translate(0,${rowEnd + 5})`)
            .call(d3.axisBottom(x).tickValues([0, 0.5, 1]).tickFormat(d3.format(".1f")));
        chart.svg.append("text").attr("x", start + metricWidth / 2).attr("y", rowEnd + 38)
            .attr("text-anchor", "middle").attr("class", "dashboard-axis-label")
            .text("Desempenho (0–1)");
        const plot = chart.svg.append("g");
        for (const item of data) {
            const value = item.values[metric.key];
            if (!Number.isFinite(value)) continue;
            const centerY = y(item.theme) + y.bandwidth() / 2;
            plot.append("line").attr("x1", x(0)).attr("x2", x(value))
                .attr("y1", centerY).attr("y2", centerY)
                .attr("stroke", metric.color).attr("stroke-opacity", 0.35).attr("stroke-width", 2);
            plot.append("circle").attr("cx", x(value)).attr("cy", centerY).attr("r", 4.5)
                .attr("fill", metric.color).attr("tabindex", 0).attr("role", "img")
                .attr("aria-label", `${item.theme}, ${metric.label}: ${value.toFixed(3)}; dificuldade ${item.difficulty.toFixed(5)}; ${item.matching} de ${item.eligible} artigos.`)
                .append("title")
                .text(`${item.theme} · ${metric.label} ${value.toFixed(3)} · dificuldade ${item.difficulty.toFixed(5)} · ${item.matching}/${item.eligible} artigos`);
        }
    }
    for (const item of data) {
        const centerY = y(item.theme) + y.bandwidth() / 2;
        chart.svg.append("text").attr("x", 8).attr("y", centerY + 4)
            .attr("class", "dashboard-theme-difficulty-row-label").text(item.theme);
        chart.svg.append("text").attr("x", themeColumn + 5).attr("y", centerY + 4)
            .attr("class", "dashboard-theme-difficulty-row-value").text(item.difficulty.toFixed(4));
        chart.svg.append("text").attr("x", themeColumn + difficultyColumn + 5).attr("y", centerY + 4)
            .attr("class", "dashboard-theme-difficulty-row-value")
            .text(`${item.matching.toLocaleString("pt-BR")} / ${item.eligible.toLocaleString("pt-BR")}`);
    }
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
        formulationFor);
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

function graphCohort(row) {
    const result = row.result;
    const components = result.diagnostics?.ensemble_rankings || result.ensemble_rankings || [];
    const graph = GRAPH_RANKINGS.has(result.ranking)
        ? dashboard.cohortGraphMethods.has(result.ranking)
        : result.ranking === "ensemble_rrf"
            && components.some((name) => dashboard.cohortGraphMethods.has(name));
    const baseline = NON_GRAPH_RANKINGS.has(result.ranking)
        ? dashboard.cohortBaselineMethods.has(result.ranking)
        : result.ranking === "ensemble_rrf"
            && !graph && components.some((name) => dashboard.cohortBaselineMethods.has(name));
    if (graph && result.seed_method === QUERY_ENTITY_SEED) return "graph";
    if (baseline) return "baseline";
    return null;
}

function cohortMetricValue(row, specification) {
    const [metric, cutoffText] = specification.split("@");
    if (metric === "mrr") return row.result.ranking_metrics?.["mrr@20"] ?? null;
    const cutoff = Number(cutoffText);
    if (["precision", "recall", "f1"].includes(metric)) {
        return row.result.metrics?.metrics?.find((entry) => entry.k === cutoff)?.[metric] ?? null;
    }
    return row.result.ranking_metrics?.[`${metric}@${cutoff}`] ?? null;
}

function cohortMetricLabel(specification) {
    return COHORT_METRICS.find((metric) => metric.value === specification)?.label || specification;
}

function cohortMethodMenu(side, methods, selectedMethods) {
    const details = document.createElement("details");
    details.className = "dashboard-cohort-method-menu";
    details.open = dashboard.cohortMenuOpenSide === side;
    details.addEventListener("toggle", () => {
        dashboard.cohortMenuOpenSide = details.open ? side
            : (dashboard.cohortMenuOpenSide === side ? null : dashboard.cohortMenuOpenSide);
    });
    const summary = document.createElement("summary");
    summary.textContent = `Métodos · ${selectedMethods.size}/${methods.length}`;
    details.appendChild(summary);
    const options = document.createElement("div");
    options.className = "dashboard-cohort-method-options";
    for (const method of methods) {
        const label = document.createElement("label");
        const input = document.createElement("input");
        input.type = "checkbox";
        input.value = method;
        input.checked = selectedMethods.has(method);
        input.addEventListener("change", () => {
            const selected = new Set([...options.querySelectorAll("input:checked")].map((node) => node.value));
            if (side === "graph") dashboard.cohortGraphMethods = selected;
            else dashboard.cohortBaselineMethods = selected;
            dashboard.cohortMenuOpenSide = side;
            persistDashboardUI();
            renderGraphCohort();
        });
        const text = document.createElement("span");
        text.textContent = method;
        label.append(input, text);
        options.appendChild(label);
    }
    details.appendChild(options);
    return details;
}

function cohortMetricSelect(side, selected) {
    const label = document.createElement("label");
    label.className = "dashboard-cohort-metric-select";
    const text = document.createElement("span");
    text.textContent = "Métrica";
    const select = document.createElement("select");
    select.setAttribute("aria-label", `Métrica do grupo ${side === "graph" ? "com grafo" : "sem grafo"}`);
    for (const metric of COHORT_METRICS) select.add(new Option(metric.label, metric.value));
    select.value = selected;
    select.addEventListener("change", () => {
        if (side === "graph") dashboard.cohortGraphMetric = select.value;
        else dashboard.cohortBaselineMetric = select.value;
        persistDashboardUI();
        renderGraphCohort();
    });
    label.append(text, select);
    return label;
}

function renderGraphCohort() {
    const rows = dimensionFilteredRows({ ignoreRanking: true, ignoreSeed: true });
    const graphMetric = dashboard.cohortGraphMetric;
    const baselineMetric = dashboard.cohortBaselineMetric;
    const sameMetric = graphMetric === baselineMetric;
    const graphValueFor = (row) => cohortMetricValue(row, graphMetric);
    const baselineValueFor = (row) => cohortMetricValue(row, baselineMetric);
    const grouped = d3.group(rows.filter((row) => graphCohort(row)),
        (row) => [row.evaluation_id, row.result.preset, row.result.quorum, row.result.result_unit].join("|") );
    const settings = dashboard.state?.settings || {};
    const configuredRankings = Array.isArray(settings.rankings) ? new Set(settings.rankings) : null;
    const configuredSeeds = Array.isArray(settings.seed_methods) ? new Set(settings.seed_methods) : null;
    const configuredEnsemble = Array.isArray(settings.ensemble_rankings) ? settings.ensemble_rankings : [];
    const configuredGraphMethods = configuredRankings
        ? COHORT_GRAPH_METHODS.filter((method) => dashboard.cohortGraphMethods.has(method)
            && configuredRankings.has(method)
            && (!configuredSeeds || configuredSeeds.has(QUERY_ENTITY_SEED)))
        : [];
    const configuredBaselineMethods = configuredRankings
        ? COHORT_BASELINE_METHODS.filter((method) => dashboard.cohortBaselineMethods.has(method)
            && configuredRankings.has(method))
        : [];
    const graphEnsembleSelected = configuredRankings?.has("ensemble_rrf")
        && configuredEnsemble.some((method) => dashboard.cohortGraphMethods.has(method))
        && (!configuredSeeds || configuredSeeds.has(QUERY_ENTITY_SEED));
    const baselineEnsembleSelected = configuredRankings?.has("ensemble_rrf")
        && !configuredEnsemble.some((method) => dashboard.cohortGraphMethods.has(method))
        && configuredEnsemble.some((method) => dashboard.cohortBaselineMethods.has(method));
    const observations = [];
    let partial = 0;
    let unpaired = 0;
    for (const [key, group] of grouped) {
        const graphRows = group.filter((row) => graphCohort(row) === "graph"
            && Number.isFinite(graphValueFor(row)));
        // Baseline algorithms do not depend on the seed. Runs contain one
        // duplicate baseline result per selected seed, so count each ranking
        // only once in this comparison.
        const baselineByMethod = new Map();
        for (const row of group) {
            if (graphCohort(row) !== "baseline" || !Number.isFinite(baselineValueFor(row))) continue;
            if (!baselineByMethod.has(row.result.ranking)) baselineByMethod.set(row.result.ranking, row);
        }
        const baselineRows = [...baselineByMethod.values()];
        if (!graphRows.length || !baselineRows.length) { unpaired++; continue; }
        const graphValue = d3.mean(graphRows, graphValueFor);
        const baselineValue = d3.mean(baselineRows, baselineValueFor);
        const [evaluation_id, preset, quorum] = key.split("|");
        const observedGraphMethods = new Set(graphRows.map((row) => row.result.ranking));
        const expectedGraph = configuredRankings
            ? configuredGraphMethods.length + Number(Boolean(graphEnsembleSelected))
            : observedGraphMethods.size;
        const expectedBaseline = configuredRankings
            ? configuredBaselineMethods.length + Number(Boolean(baselineEnsembleSelected))
            : baselineByMethod.size;
        const graphCount = observedGraphMethods.size;
        const complete = graphCount >= (expectedGraph || graphCount)
            && baselineByMethod.size >= (expectedBaseline || baselineByMethod.size);
        if (!complete) partial++;
        observations.push({ evaluation_id, formulation: formulationFor(group[0]), preset,
            quorum, graphValue, baselineValue, delta: sameMetric ? graphValue - baselineValue : null,
            complete, graphCount, baselineCount: baselineByMethod.size });
    }
    const summary = $("dashboard-graph-cohort-summary");
    const body = $("dashboard-graph-cohort-breakdown");
    const chartContainer = $("dashboard-graph-cohort-distribution");
    chartContainer.replaceChildren();
    const complete = observations.filter((item) => item.complete);
    const wins = sameMetric ? observations.filter((item) => item.delta > 1e-9).length : null;
    const losses = sameMetric ? observations.filter((item) => item.delta < -1e-9).length : null;
    const ties = sameMetric ? observations.length - wins - losses : null;
    const graphMetricLabel = cohortMetricLabel(graphMetric);
    const baselineMetricLabel = cohortMetricLabel(baselineMetric);
    const deltaSummary = sameMetric
        ? `Δ ${formatPercent(d3.mean(observations, (item) => item.delta))} · Graph/baseline/empate ${wins}/${losses}/${ties}`
        : "Δ e vitórias indisponíveis porque as métricas selecionadas são diferentes";
    summary.textContent = `${observations.length} pares de consulta/configuração (${complete.length} completos; ${partial} parciais) · média Graph ${graphMetricLabel}: ${formatPercent(d3.mean(observations, (item) => item.graphValue))} · sem grafo ${baselineMetricLabel}: ${formatPercent(d3.mean(observations, (item) => item.baselineValue))} · ${deltaSummary}. Valores parciais são provisórios; sem par: ${unpaired}.`;
    const graphHeading = $("dashboard-cohort-graph-metric-heading");
    const baselineHeading = $("dashboard-cohort-baseline-metric-heading");
    const deltaHeading = $("dashboard-cohort-delta-heading");
    if (graphHeading) graphHeading.textContent = `Graph · ${graphMetricLabel}`;
    if (baselineHeading) baselineHeading.textContent = `Sem grafo · ${baselineMetricLabel}`;
    if (deltaHeading) deltaHeading.textContent = sameMetric ? `Δ ${graphMetricLabel}` : "Δ (métricas diferentes)";
    const makePanel = (side, title, methods, selectedMethods, selectedMetric, values, color) => {
        const panel = document.createElement("section");
        panel.className = `dashboard-cohort-panel dashboard-cohort-panel--${side}`;
        const heading = document.createElement("h4");
        heading.textContent = title;
        const methodCount = document.createElement("p");
        methodCount.className = "dashboard-muted";
        methodCount.textContent = `${values.length.toLocaleString("pt-BR")} pares · ${cohortMetricLabel(selectedMetric)}`;
        const content = document.createElement("div");
        content.className = "dashboard-cohort-panel-content";
        const controls = document.createElement("div");
        controls.className = "dashboard-cohort-panel-controls";
        controls.append(
            cohortMethodMenu(side, methods, selectedMethods),
            cohortMetricSelect(side, selectedMetric),
        );
        const plot = document.createElement("div");
        plot.className = "dashboard-cohort-histogram-plot";
        plot.id = `dashboard-cohort-${side}-histogram`;
        content.append(controls, plot);
        panel.append(heading, methodCount, content);
        chartContainer.appendChild(panel);
        if (!values.length) {
            const empty = document.createElement("p");
            empty.className = "dashboard-chart-empty-message";
            empty.textContent = observations.length
                ? "Nenhum resultado deste grupo corresponde aos métodos e à métrica selecionados."
                : "Aguardando resultados pareáveis.";
            plot.appendChild(empty);
            return null;
        }
        return { plot, values, color, title };
    };
    if (!observations.length) {
        body.innerHTML = '<tr><td colspan="9" class="dashboard-empty">Ainda não há resultados nos dois grupos para a mesma consulta/configuração.</td></tr>';
        makePanel("graph", "Graph + query_entities", COHORT_GRAPH_METHODS,
            dashboard.cohortGraphMethods, graphMetric, [], "#7c3aed");
        makePanel("baseline", "Sem grafo", COHORT_BASELINE_METHODS,
            dashboard.cohortBaselineMethods, baselineMetric, [], "#0891b2");
        return;
    }
    const graphPanel = makePanel("graph", "Graph + query_entities", COHORT_GRAPH_METHODS,
        dashboard.cohortGraphMethods, graphMetric, observations.map((item) => item.graphValue), "#7c3aed");
    const baselinePanel = makePanel("baseline", "Sem grafo", COHORT_BASELINE_METHODS,
        dashboard.cohortBaselineMethods, baselineMetric, observations.map((item) => item.baselineValue), "#0891b2");
    const series = [graphPanel, baselinePanel].filter(Boolean);
    // Keep one shared x/y scale for direct visual comparison, while giving
    // each cohort its own plot so bars no longer obscure each other.
    const xMaximum = Math.max(1, d3.max(series.flatMap((item) => item.values)) || 1);
    const binStep = xMaximum / 10;
    const thresholds = d3.range(binStep, xMaximum, binStep);
    const binValues = (values) => d3.bin().domain([0, xMaximum]).thresholds(thresholds)(values);
    const maximumShare = Math.max(0.1, d3.max(series.flatMap((item) =>
        binValues(item.values).map((bin) => bin.length / item.values.length))) || 0) * 1.15;
    for (const item of series) {
        const chart = chartBase(item.plot.id, 255, 360);
        chart.svg.attr("aria-label", `Distribuição de ${cohortMetricLabel(item === graphPanel ? graphMetric : baselineMetric)} para ${item.title}, ${item.values.length} pares.`);
        const margin = { top: 12, right: 12, bottom: 38, left: 46 };
        const width = chart.width - margin.left - margin.right;
        const height = chart.height - margin.top - margin.bottom;
        const x = d3.scaleLinear().domain([0, xMaximum]).range([0, width]);
        const y = d3.scaleLinear().domain([0, maximumShare]).range([height, 0]);
        const group = chart.svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
        group.append("g").attr("transform", `translate(0,${height})`)
            .call(d3.axisBottom(x).ticks(5, ".0%"));
        group.append("g").call(d3.axisLeft(y).ticks(4, ".0%"));
        const bins = binValues(item.values);
        group.selectAll("rect.cohort-bin").data(bins).join("rect")
            .attr("class", "cohort-bin")
            .attr("x", (bin) => x(bin.x0) + 1)
            .attr("y", (bin) => y(bin.length / item.values.length))
            .attr("width", (bin) => Math.max(0, x(bin.x1) - x(bin.x0) - 2))
            .attr("height", (bin) => height - y(bin.length / item.values.length))
            .attr("fill", item.color).attr("opacity", 0.82).attr("stroke", "white").attr("stroke-width", 1)
            .attr("tabindex", 0).attr("role", "img")
            .attr("aria-label", (bin) => `${item.label}, ${(bin.x0 * 100).toFixed(0)}–${(bin.x1 * 100).toFixed(0)}%: ${bin.length} de ${item.values.length} pares.`)
            .append("title").text((bin) => `${item.title} ${(bin.x0 * 100).toFixed(0)}–${(bin.x1 * 100).toFixed(0)}%: ${bin.length}/${item.values.length}`);
        group.append("text").attr("class", "dashboard-axis-label")
            .attr("x", width / 2).attr("y", height + 34).attr("text-anchor", "middle")
            .text(cohortMetricLabel(item === graphPanel ? graphMetric : baselineMetric));
    }
    const dims = d3.rollups(observations, (items) => {
        const graphMean = d3.mean(items, (item) => item.graphValue);
        const baseMean = d3.mean(items, (item) => item.baselineValue);
        return { delta: sameMetric ? d3.mean(items, (item) => item.delta) : null,
            graphMean, baseMean,
            wins: sameMetric ? items.filter((item) => item.delta > 1e-9).length : null,
            losses: sameMetric ? items.filter((item) => item.delta < -1e-9).length : null,
            ties: sameMetric ? items.filter((item) => Math.abs(item.delta) <= 1e-9).length : null,
            complete: items.filter((item) => item.complete).length, partial: items.filter((item) => !item.complete).length };
    }, (item) => [item.formulation, item.preset, item.quorum].join("|")).sort((a, b) => a[0].localeCompare(b[0], "pt-BR"));
    body.replaceChildren();
    for (const [key, item] of dims) {
        const tr = document.createElement("tr");
        const [formulation, preset, quorum] = key.split("|");
        for (const value of [FORMULATION_LABELS[formulation] || formulation, preset,
            `${Math.round(Number(quorum) * 100)}%`, formatPercent(item.graphMean),
            formatPercent(item.baseMean), sameMetric ? formatPercent(item.delta) : "—",
            sameMetric ? `${item.wins} / ${item.losses} / ${item.ties}` : "N/A",
            `${item.complete} / ${item.partial}`, "—"]) {
            const td = document.createElement("td"); td.textContent = value; tr.appendChild(td);
        }
        body.appendChild(tr);
    }
}

function formatPercent(value) { return Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "—"; }

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
            row.evaluation_id, queryFor(row), formulationFor(row), row.result.ranking, row.result.seed_method,
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
    const runId = dashboard.runId;
    const generation = dashboard.runGeneration;
    const signal = dashboard.runAbort?.signal;
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
    const query = document.createElement("p"); query.textContent = queryFor(row);
    const list = document.createElement("ol");
    const loading = document.createElement("p"); loading.textContent = "Carregando resultados ranqueados…";
    detail.append(heading, query, loading);
    try {
        const full = await api(`/dashboard/runs/${runId}/results/${seq}`, { signal });
        if (dashboard.selectedSeq !== seq || dashboard.runId !== runId
            || dashboard.runGeneration !== generation) return;
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
        if (signal?.aborted || dashboard.runGeneration !== generation) return;
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
    renderThemeDifficultyPerformance(rows);
    renderFormulationComparison(rows);
    renderPairedDeltas(rows);
    renderGraphCohort();
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
    const metric = $("dashboard-metric").value;
    const fixedAtTwenty = metric === "mrr";
    const allowed = fixedAtTwenty ? [20]
        : ["map", "ndcg"].includes(metric) ? [5, 10, 20] : [1, 3, 5, 10, 20];
    const current = Number(cutoff.value);
    cutoff.replaceChildren(...allowed.map((value) => new Option(String(value), String(value))));
    cutoff.value = allowed.includes(current) ? String(current) : String(allowed.at(-1));
    cutoff.disabled = fixedAtTwenty;
}

async function loadDatasets() {
    const data = await api("/dashboard/evaluation-sets");
    dashboard.datasets = data.datasets || [];
    const saved = getUiState().batchDashboard || {};
    renderThemeChoices(initialThemeSelection(saved, dashboard.datasets));
}

function runOptionLabel(run) {
    const label = String(run.dataset_label || run.dataset || "Rodada").replace(/\s+/g, " ").trim();
    const shortLabel = label.length > 88 ? `${label.slice(0, 85)}…` : label;
    const completed = Number(run.progress?.completed) || 0;
    const total = Number(run.progress?.total) || 0;
    return `${shortLabel} · ${run.status} · ${completed.toLocaleString("pt-BR")}/${total.toLocaleString("pt-BR")}`;
}

function updateRunOption(run) {
    const option = [...$("dashboard-existing-run").options].find((entry) => entry.value === run.run_id);
    if (option) option.textContent = runOptionLabel(run);
}

async function refreshRunList() {
    const data = await api("/dashboard/runs");
    const select = $("dashboard-existing-run");
    const current = select.value;
    const figureSelect = $("dashboard-figure-runs");
    const selectedFigureRuns = new Set([...figureSelect.selectedOptions].map((option) => option.value));
    select.replaceChildren(new Option("Rodadas salvas…", ""));
    figureSelect.replaceChildren();
    for (const run of data.runs || []) {
        select.add(new Option(runOptionLabel(run), run.run_id));
        const option = new Option(runOptionLabel(run), run.run_id);
        option.selected = selectedFigureRuns.has(run.run_id);
        option.dataset.status = run.status;
        option.dataset.completed = String(Number(run.progress?.completed) || 0);
        option.dataset.total = String(Number(run.progress?.total) || 0);
        figureSelect.add(option);
    }
    if ((data.runs || []).some((run) => run.run_id === current)) select.value = current;
    const activeRuns = (data.runs || []).filter((run) => ["queued", "running"].includes(run.status)).length;
    $("dashboard-figure-runs-hint").textContent = activeRuns
        ? `Ctrl/Cmd seleciona várias. ${activeRuns} rodada(s) ainda em execução; só os resultados já persistidos estarão disponíveis.`
        : "Use Ctrl/Cmd para selecionar várias rodadas.";
    void loadFigureFilterOptions();
    return data.runs || [];
}

async function revealFigureGeneratorIfAvailable() {
    try {
        const capabilities = await api("/dashboard/figure-jobs");
        $("dashboard-figure-generator").hidden = capabilities.enabled !== true;
    } catch {
        // A still-running older Flask process may serve reloaded templates but
        // not the new routes. Keep these controls hidden until the API updates.
        $("dashboard-figure-generator").hidden = true;
    }
}

function stopFigureJobPolling() {
    if (dashboard.figureJobTimer) clearTimeout(dashboard.figureJobTimer);
    dashboard.figureJobTimer = null;
}

function formatFigureJobPhase(phase) {
    return ({ queued: "Na fila", starting: "Iniciando", loading: "Lendo resultados",
        analyzing: "Analisando dados", plotting: "Gerando gráficos", writing_manifest: "Finalizando",
        run_complete: "Rodada concluída", packaging: "Montando ZIP",
        completed: "Concluído", failed: "Falhou" })[phase] || phase || "Processando";
}

function formatFigureJobElapsed(job) {
    const started = Date.parse(job.started_at || "");
    if (!Number.isFinite(started)) return "";
    const ended = ["completed", "failed"].includes(job.status)
        ? Date.parse(job.updated_at || "") : Date.now();
    const seconds = Math.max(0, Math.floor(((Number.isFinite(ended) ? ended : Date.now()) - started) / 1000));
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainder = seconds % 60;
    return hours
        ? `${hours}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
        : `${minutes}:${String(remainder).padStart(2, "0")}`;
}

function renderFigureJob(job) {
    const panel = $("dashboard-figure-job");
    panel.hidden = false;
    const progress = job.progress || {};
    const terminal = ["completed", "failed"].includes(job.status);
    const phase = job.status === "failed" ? (progress.failed_phase || "failed") : progress.phase;
    $("dashboard-figure-job-status").textContent = job.status === "failed"
        ? `Falha durante: ${formatFigureJobPhase(phase)}` : formatFigureJobPhase(phase);
    const runPosition = progress.run_index && progress.run_total
        ? `Rodada ${progress.run_index}/${progress.run_total}` : "";
    const currentRun = progress.current_run_id ? ` · ${progress.current_run_id}` : "";
    let phaseDetail = "";
    if (phase === "loading") {
        if (Number.isFinite(progress.total_rows)) {
            const loaded = (progress.loaded_rows || 0).toLocaleString("pt-BR");
            const total = progress.total_rows.toLocaleString("pt-BR");
            phaseDetail = `${loaded}/${total} linhas`;
        } else {
            phaseDetail = progress.stage_label || "Contando resultados persistidos";
        }
    } else if (phase === "analyzing" || phase === "writing_manifest") {
        phaseDetail = progress.stage_label || "Preparando resultados";
    } else if (phase === "plotting") {
        const done = progress.completed_tasks || 0;
        const total = progress.total_tasks || "?";
        const lastTask = progress.last_completed_task && Number.isFinite(progress.last_task_seconds)
            ? ` · última: ${progress.last_completed_task} (${progress.last_task_seconds.toFixed(1)} s)` : "";
        const nested = progress.subtask_total > 0
            ? ` · Referências ${progress.subtask_completed || 0}/${progress.subtask_total}`
                + (progress.current_subtask ? ` · ${progress.current_subtask}` : "")
            : "";
        phaseDetail = `Etapas gráficas ${done}/${total}${progress.current_task ? ` · ${progress.current_task}` : ""}${nested}${lastTask}`;
    } else if (phase === "packaging") {
        const done = progress.package_files_done || 0;
        const total = progress.package_files_total ?? "?";
        phaseDetail = `Arquivos ${done}/${total}${progress.current_file ? ` · ${progress.current_file}` : ""}`;
    }
    const elapsed = formatFigureJobElapsed(job);
    const updated = Date.parse(job.updated_at || "");
    const stale = job.status === "running" && Number.isFinite(updated) && Date.now() - updated > 15000;
    const details = [runPosition, currentRun.replace(/^ · /, ""), phaseDetail,
        elapsed ? `decorrido ${elapsed}` : "",
        terminal && Number.isFinite(progress.package_seconds)
            ? `compactação ZIP ${progress.package_seconds.toFixed(1)} s` : "",
        stale ? "etapa ainda em execução" : ""]
        .filter(Boolean).join(" · ");
    $("dashboard-figure-job-progress").textContent = details;
    const bar = $("dashboard-figure-job-bar");
    bar.max = 100;
    let fraction = null;
    if (job.status === "completed") fraction = 1;
    else if (phase === "loading" && Number.isFinite(progress.total_rows)) {
        fraction = progress.total_rows === 0 ? 1 : progress.loaded_rows / progress.total_rows;
    } else if (phase === "plotting" && progress.total_tasks > 0) {
        const nestedFraction = progress.subtask_total > 0
            ? (progress.subtask_completed || 0) / progress.subtask_total : 0;
        fraction = ((progress.completed_tasks || 0) + nestedFraction) / progress.total_tasks;
    } else if (phase === "packaging" && progress.package_files_total > 0) {
        fraction = progress.package_files_done / progress.package_files_total;
    } else if (phase === "packaging" && progress.package_files_total === 0) {
        fraction = 1;
    } else if (phase === "run_complete") fraction = 1;
    if (fraction == null) bar.removeAttribute("value");
    else bar.value = Math.round(Math.max(0, Math.min(1, fraction)) * bar.max);
    bar.setAttribute("aria-valuetext", phaseDetail || formatFigureJobPhase(phase));
    const download = $("dashboard-figure-download");
    download.hidden = job.status !== "completed" || !job.download_url;
    if (!download.hidden) download.href = job.download_url;
    $("dashboard-figure-message").textContent = job.error || (job.status === "completed"
        ? "ZIP pronto. Cada rodada está em uma pasta separada; consulte manifest.json para configurações e exclusões."
        : "");
    $("dashboard-figure-start").disabled = !terminal && job.status !== "failed";
}

function scheduleFigureJobPoll(delay = 1800) {
    stopFigureJobPolling();
    dashboard.figureJobTimer = setTimeout(pollFigureJob, delay);
}

async function pollFigureJob() {
    dashboard.figureJobTimer = null;
    if (!dashboard.figureJobId) return;
    try {
        const job = await api(`/dashboard/figure-jobs/${dashboard.figureJobId}`);
        dashboard.figureJobPollFailures = 0;
        renderFigureJob(job);
        if (["queued", "running"].includes(job.status)) scheduleFigureJobPoll();
    } catch (error) {
        dashboard.figureJobPollFailures += 1;
        $("dashboard-figure-message").textContent = `Não foi possível atualizar o progresso: ${error.message}`;
        scheduleFigureJobPoll(Math.min(30000, 1800 * (2 ** Math.min(dashboard.figureJobPollFailures, 4))));
    }
}

const FIGURE_FILTER_GROUPS = ["themes", "formulations", "presets", "quorums", "evaluation-ids"];

function figureFilterContainer(group) {
    return $(`dashboard-figure-filter-${group}`);
}

function figureFilterValues(group) {
    const container = figureFilterContainer(group);
    return container ? [...container.querySelectorAll("input[type=checkbox]:checked")]
        .map((input) => input.value) : [];
}

function clearFigureFilterOptions(message = "Selecione rodadas para carregar as opções.") {
    for (const group of FIGURE_FILTER_GROUPS) figureFilterContainer(group)?.replaceChildren();
    for (const group of FIGURE_FILTER_GROUPS) {
        const count = $(`dashboard-figure-filter-count-${group}`);
        if (count) count.textContent = "Todos";
    }
    $("dashboard-figure-filter-options-hint").textContent = message;
    dashboard.figureFilterOptions = null;
    renderFigureSelectionPreview();
}

function displayThemeId(value) {
    return String(value || "").replace(/_/g, " ").replace(/\b\p{L}/gu, (letter) => letter.toLocaleUpperCase("pt-BR"));
}

function makeFigureFilterCheckbox(value, text, selected, title = "") {
    const label = document.createElement("label");
    label.className = "dashboard-check";
    if (title) label.title = title;
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = String(value);
    input.checked = selected.has(input.value);
    const caption = document.createElement("span");
    caption.textContent = text;
    label.append(input, caption);
    return label;
}

function renderFigureFilterOptions(options, previous = {}) {
    const simpleFacets = ["themes", "formulations", "presets", "quorums"];
    for (const group of simpleFacets) {
        const container = figureFilterContainer(group);
        const selected = new Set(previous[group] || []);
        container.replaceChildren();
        const values = options[group] || [];
        for (const value of values) {
            let label = String(value);
            if (group === "themes") label = `${displayThemeId(value)} · ${value}`;
            if (group === "formulations") label = FORMULATION_LABELS[value] || value;
            container.appendChild(makeFigureFilterCheckbox(value, label, selected));
        }
    }

    const queryContainer = figureFilterContainer("evaluation-ids");
    const selectedQueries = new Set(previous.evaluation_ids || []);
    queryContainer.replaceChildren();
    const queriesByTheme = d3.group(options.queries || [], (item) => item.theme || "sem tema");
    for (const [theme, items] of [...queriesByTheme].sort((a, b) => a[0].localeCompare(b[0], "pt-BR"))) {
        const details = document.createElement("details");
        details.className = "dashboard-figure-query-group";
        const summary = document.createElement("summary");
        summary.textContent = `${displayThemeId(theme)} · ${items.length} consulta(s)`;
        details.appendChild(summary);
        const queryChecks = document.createElement("div");
        queryChecks.className = "dashboard-figure-check-grid dashboard-figure-query-checks";
        for (const item of items) {
            const query = String(item.query || "").replace(/\s+/g, " ").trim();
            const visible = query.length > 90 ? `${query.slice(0, 87)}…` : query;
            const label = visible ? `${visible} · ${item.id}` : item.id;
            queryChecks.appendChild(makeFigureFilterCheckbox(item.id, label, selectedQueries, item.id));
        }
        details.appendChild(queryChecks);
        queryContainer.appendChild(details);
    }

    dashboard.figureFilterOptions = options;
    $("dashboard-figure-filter-options-hint").textContent =
        "Marque valores para restringir a geração; em cada grupo, sem seleções significa incluir todos.";
    updateFigureFilterCounts();
    renderFigureSelectionPreview();
}

function updateFigureFilterCounts() {
    for (const group of FIGURE_FILTER_GROUPS) {
        const container = figureFilterContainer(group);
        const all = container?.querySelectorAll("input[type=checkbox]").length || 0;
        const selected = figureFilterValues(group).length;
        const count = $(`dashboard-figure-filter-count-${group}`);
        if (count) count.textContent = selected ? `${selected}/${all} selecionado(s)` : `Todos (${all})`;
    }
}

async function loadFigureFilterOptions(force = false) {
    const runIds = [...$("dashboard-figure-runs").selectedOptions].map((option) => option.value);
    const runKey = [...runIds].sort().join("|");
    if (!runKey) {
        dashboard.figureFilterRunKey = "";
        clearFigureFilterOptions();
        return;
    }
    if (!force && runKey === dashboard.figureFilterRunKey && dashboard.figureFilterOptions) return;
    const generation = ++dashboard.figureFilterGeneration;
    const previous = Object.fromEntries(FIGURE_FILTER_GROUPS.map((group) => [group, figureFilterValues(group)]));
    dashboard.figureFilterRunKey = runKey;
    $("dashboard-figure-filter-options-hint").textContent = "Carregando opções das rodadas selecionadas…";
    try {
        const options = await api("/dashboard/figure-jobs/filter-options", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ run_ids: runIds }),
        });
        if (generation !== dashboard.figureFilterGeneration || runKey !== [...$("dashboard-figure-runs").selectedOptions]
            .map((option) => option.value).sort().join("|")) return;
        renderFigureFilterOptions(options, previous);
    } catch (error) {
        if (generation !== dashboard.figureFilterGeneration) return;
        clearFigureFilterOptions(`Não foi possível carregar as opções: ${error.message}`);
        dashboard.figureFilterRunKey = runKey;
    }
}

function renderFigureSelectionPreview() {
    const preview = $("dashboard-figure-preview");
    if (!preview) return;
    const runs = [...$("dashboard-figure-runs").selectedOptions]
        .map((option) => `${option.textContent} (${option.dataset.completed || 0}/${option.dataset.total || 0} persistidos)`);
    const rankings = [...$("dashboard-figure-rankings").querySelectorAll("input:checked")]
        .map((input) => input.value);
    const seeds = [...$("dashboard-figure-seeds").querySelectorAll("input:checked")]
        .map((input) => input.value);
    const families = [...$("dashboard-figure-generator").querySelectorAll(".dashboard-figure-family-options input:checked")]
        .map((input) => input.closest("label")?.textContent.trim() || input.value);
    const baselines = [...$("dashboard-figure-baselines").querySelectorAll("input:checked")]
        .map((input) => input.value);
    const filterLabels = { themes: "temas", formulations: "formulações", presets: "presets",
        quorums: "quorums", "evaluation-ids": "consultas" };
    const filters = FIGURE_FILTER_GROUPS.map((group) => [filterLabels[group], figureFilterValues(group)])
        .filter(([, values]) => values.length);
    const filterSummary = filters.length
        ? filters.map(([label, values]) => `${label} (${values.length})`).join("; ")
        : "nenhum · todos os valores";
    const lines = [
        `Rodadas (${runs.length}): ${runs.join("; ") || "nenhuma selecionada"}`,
        `Rankings (${rankings.length}): ${rankings.join(", ") || "nenhum"}`,
        `Sementes de grafo (${seeds.length}): ${seeds.join(", ") || "nenhuma"}`,
        `Saídas: ${families.join(", ") || "nenhuma"}`,
        `Referências pareadas: ${baselines.join(", ") || "nenhuma"}`,
        `Grupos incompletos: ${$("dashboard-figure-partial").checked ? "incluídos (exploratório)" : "excluídos"}`,
        `Filtros: ${filterSummary}`,
        "Cada rodada será processada separadamente; o manifesto registrará os grupos efetivamente incluídos e análises indisponíveis.",
    ];
    preview.textContent = lines.join("\n");
}

async function startFigureGeneration() {
    const button = $("dashboard-figure-start");
    const runIds = [...$("dashboard-figure-runs").selectedOptions].map((option) => option.value);
    const formats = [...$("dashboard-figure-formats").querySelectorAll("input:checked")]
        .map((input) => input.value);
    const baselines = [...$("dashboard-figure-baselines").querySelectorAll("input:checked")]
        .map((input) => input.value);
    const rankings = [...$("dashboard-figure-rankings").querySelectorAll("input:checked")]
        .map((input) => input.value);
    const seedMethods = [...$("dashboard-figure-seeds").querySelectorAll("input:checked")]
        .map((input) => input.value);
    const figureFamilies = [...$("dashboard-figure-generator").querySelectorAll(".dashboard-figure-family-options input:checked")]
        .map((input) => input.value);
    if (!runIds.length) {
        $("dashboard-figure-message").textContent = "Selecione pelo menos uma rodada salva.";
        return;
    }
    if (!rankings.length || !formats.length || !figureFamilies.length
        || (rankings.some((ranking) => !["hybrid_max", "rrf", "cross_encoder", "lexical", "vector"].includes(ranking))
            && !seedMethods.length)) {
        $("dashboard-figure-message").textContent =
            "Selecione ao menos um ranking, formato, família de figuras e semente para os métodos de grafo escolhidos.";
        return;
    }
    if (figureFamilies.includes("comparisons") && !baselines.length) {
        $("dashboard-figure-message").textContent = "Selecione ao menos uma referência ou desative as comparações pareadas.";
        return;
    }
    const selectedQuorums = figureFilterValues("quorums").map(Number);
    button.disabled = true;
    $("dashboard-figure-message").textContent = "Enviando solicitação…";
    $("dashboard-figure-download").hidden = true;
    try {
        const job = await api("/dashboard/figure-jobs", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                run_ids: runIds, formats, baselines,
                rankings, seed_methods: seedMethods, figure_families: figureFamilies,
                filters: {
                    themes: figureFilterValues("themes"),
                    formulations: figureFilterValues("formulations"),
                    presets: figureFilterValues("presets"),
                    quorums: selectedQuorums,
                    evaluation_ids: figureFilterValues("evaluation-ids"),
                },
                include_partial: $("dashboard-figure-partial").checked,
                include_ranking_overlap: figureFamilies.includes("overlap"),
            }),
        });
        dashboard.figureJobId = job.job_id;
        dashboard.figureJobPollFailures = 0;
        renderFigureJob(job);
        if (["queued", "running"].includes(job.status)) scheduleFigureJobPoll(0);
    } catch (error) {
        button.disabled = false;
        $("dashboard-figure-message").textContent = error.message;
    }
}

async function refreshSavedRuns() {
    const button = $("dashboard-refresh-run-list");
    if (button) { button.disabled = true; button.textContent = "Atualizando…"; }
    try {
        await refreshRunList();
    } catch (error) {
        $("dashboard-launch-hint").textContent = `Não foi possível atualizar as rodadas salvas: ${error.message}`;
    } finally {
        if (button) { button.disabled = false; button.textContent = "Atualizar lista"; }
    }
}

function stopPolling() {
    if (dashboard.timer) clearTimeout(dashboard.timer);
    dashboard.timer = null;
}

function runNeedsPolling(status) {
    return ["queued", "running", "pause_requested"].includes(status);
}

function scheduleStatusPoll(delay = 1500, generation = dashboard.runGeneration) {
    stopPolling();
    dashboard.timer = setTimeout(async () => {
        dashboard.timer = null;
        if (generation !== dashboard.runGeneration) return;
        await pollRun();
        if (generation !== dashboard.runGeneration) return;
        const failures = dashboard.statusPollFailures || 0;
        const nextDelay = failures
            ? Math.min(30000, 1500 * (2 ** Math.min(failures, 4)))
            : (document.visibilityState === "hidden" ? 10000 : 1500);
        if (runNeedsPolling(dashboard.state?.status) || failures) {
            scheduleStatusPoll(nextDelay, generation);
        }
    }, delay);
}

async function pauseRun() {
    if (!dashboard.runId) return;
    const runId = dashboard.runId;
    const generation = dashboard.runGeneration;
    const signal = dashboard.runAbort?.signal;
    const button = $("dashboard-pause-run");
    button.disabled = true;
    $("dashboard-launch-hint").textContent = "Pausa solicitada; a rodada vai parar no próximo ponto seguro…";
    try {
        const state = await api(`/dashboard/runs/${runId}/pause`, { method: "POST", signal });
        if (generation !== dashboard.runGeneration || runId !== dashboard.runId) return;
        dashboard.state = state;
        updateRunOption(state);
        dashboard.statusPollFailures = 0;
        renderProgress();
        renderHistorySync();
        persistDashboardUI();
        if (runNeedsPolling(dashboard.state.status)) scheduleStatusPoll(0);
    } catch (error) {
        if (signal?.aborted || generation !== dashboard.runGeneration) return;
        $("dashboard-launch-hint").textContent = error.message;
    } finally {
        if (generation === dashboard.runGeneration) renderProgress();
    }
}

async function resumeRun() {
    if (!dashboard.runId) return;
    const runId = dashboard.runId;
    const generation = dashboard.runGeneration;
    const signal = dashboard.runAbort?.signal;
    const button = $("dashboard-resume-run");
    button.disabled = true;
    $("dashboard-launch-hint").textContent = "Retomando a partir dos resultados já salvos…";
    try {
        const state = await api(`/dashboard/runs/${runId}/resume`, { method: "POST", signal });
        if (generation !== dashboard.runGeneration || runId !== dashboard.runId) return;
        dashboard.state = state;
        updateRunOption(state);
        dashboard.statusPollFailures = 0;
        renderProgress();
        renderHistorySync();
        persistDashboardUI();
        stopPolling();
        await pollRun();
        if (generation === dashboard.runGeneration && runNeedsPolling(dashboard.state?.status)) {
            scheduleStatusPoll(0, generation);
        }
    } catch (error) {
        if (signal?.aborted || generation !== dashboard.runGeneration) return;
        $("dashboard-launch-hint").textContent = error.message;
    } finally {
        if (generation === dashboard.runGeneration) {
            button.disabled = false;
            renderProgress();
        }
    }
}

async function pollRun() {
    const runId = dashboard.runId;
    const generation = dashboard.runGeneration;
    const signal = dashboard.runAbort?.signal;
    if (!runId || dashboard.pollingGeneration === generation) return;
    dashboard.polling = true;
    dashboard.pollingGeneration = generation;
    try {
        const state = await api(`/dashboard/runs/${runId}`, { signal });
        if (generation !== dashboard.runGeneration || runId !== dashboard.runId) return;
        const previousState = dashboard.state;
        const initialState = !previousState || previousState.run_id !== state.run_id;
        dashboard.state = state;
        dashboard.startedAt = Date.parse(state.created_at) || null;
        updateRunOption(state);
        dashboard.historyExpected = Math.max(dashboard.historyExpected, Number(state.progress?.completed) || 0);
        dashboard.statusPollFailures = 0;
        $("dashboard-launch-hint").textContent = "";
        renderProgress();
        renderHistorySync();
        if (initialState) {
            renderDashboard();
        } else if (previousState.status !== state.status
            && ["completed", "failed", "interrupted", "paused"].includes(state.status)) {
            scheduleDashboardRender(true);
        }
        if (dashboard.cursor < dashboard.historyExpected
            && !dashboard.historyLoading && !dashboard.historyError) {
            void loadRunHistory(runId, generation, signal);
        }
        if (["completed", "failed", "interrupted", "paused"].includes(state.status)) {
            stopPolling();
            $("dashboard-launch-hint").textContent = state.error || (state.status === "paused"
                ? "Rodada pausada. Os resultados salvos foram preservados; use Retomar para continuar."
                : `Rodada ${state.status}.`);
            refreshRunList().catch(() => {});
            if (state.status === "completed") void loadThemeCountArtifact(runId);
        }
    } catch (error) {
        if (signal?.aborted || generation !== dashboard.runGeneration) return;
        dashboard.statusPollFailures += 1;
        const retrySeconds = Math.min(30, 1.5 * (2 ** Math.min(dashboard.statusPollFailures, 4)));
        $("dashboard-launch-hint").textContent = `${error.message} Tentando novamente em ${retrySeconds.toLocaleString("pt-BR")} s.`;
    } finally {
        if (dashboard.pollingGeneration === generation) {
            dashboard.polling = false;
            dashboard.pollingGeneration = null;
        }
    }
}

async function loadRunHistory(runId, generation, signal) {
    if (dashboard.historyLoading || generation !== dashboard.runGeneration) return;
    dashboard.historyLoading = true;
    dashboard.historyError = null;
    renderHistorySync();
    try {
        let hasMore = true;
        while (hasMore && generation === dashboard.runGeneration && runId === dashboard.runId) {
            const previousCursor = dashboard.cursor;
            const page = await api(
                `/dashboard/runs/${runId}/results?after=${previousCursor}&limit=500`, { signal },
            );
            if (generation !== dashboard.runGeneration || runId !== dashboard.runId) return;
            const events = page.events || [];
            for (const event of events) dashboard.rows.push(compactDashboardEvent(event));
            renderThemeCountInputs(currentThemeCountIds(), dashboard.themeCountArtifact?.themes || {});
            dashboard.cursor = page.cursor ?? dashboard.cursor;
            dashboard.historyExpected = Math.max(
                dashboard.historyExpected, Number(page.progress?.completed) || 0, dashboard.cursor,
            );
            renderHistorySync();
            if (events.length) scheduleDashboardRender(false, true);
            hasMore = Boolean(page.has_more);
            if (hasMore && dashboard.cursor <= previousCursor) {
                throw new Error("O histórico não avançou. Tente atualizar os resultados novamente.");
            }
            // Yield between pages so the browser can paint, update progress,
            // and process input while hydrating a large saved round.
            if (hasMore) await new Promise((resolve) => setTimeout(resolve, 0));
        }
        if (generation !== dashboard.runGeneration || runId !== dashboard.runId) return;
        dashboard.historyDone = !hasMore;
        dashboard.historyError = null;
        if (dashboard.restoreSelection && dashboard.rows.some((row) => row.seq === dashboard.selectedSeq)) {
            dashboard.restoreSelection = false;
            void selectResult(dashboard.selectedSeq);
        }
        if (!dashboard.rows.length) renderDashboard();
    } catch (error) {
        if (signal?.aborted || generation !== dashboard.runGeneration) return;
        dashboard.historyError = error.message;
        $("dashboard-launch-hint").textContent = error.message;
    } finally {
        if (generation === dashboard.runGeneration) {
            dashboard.historyLoading = false;
            renderHistorySync();
        }
    }
}

async function openRun(runId) {
    stopPolling();
    dashboard.runAbort?.abort();
    const generation = ++dashboard.runGeneration;
    const controller = new AbortController();
    dashboard.runAbort = controller;
    if (dashboard.analyticsRenderTimer) clearTimeout(dashboard.analyticsRenderTimer);
    dashboard.analyticsRenderTimer = null;
    dashboard.runId = runId;
    dashboard.themeCountArtifact = null;
    dashboard.themeCountPreview = null;
    dashboard.themeCountInputThemeSignature = null;
    $("dashboard-theme-count-results").replaceChildren();
    $("dashboard-theme-count-message").textContent = "";
    $("dashboard-theme-count-inputs").replaceChildren();
    $("dashboard-theme-count-preview-results").replaceChildren();
    $("dashboard-theme-count-preview-results").hidden = true;
    $("dashboard-theme-count-submit").hidden = true;
    $("dashboard-theme-count-file").value = "";
    $("dashboard-theme-count-from").value = "";
    $("dashboard-theme-count-to").value = "";
    dashboard.statusPollFailures = 0;
    const saved = getUiState().batchDashboard || {};
    dashboard.savedFilters = saved.runId === runId ? (saved.filters || null) : null;
    if (dashboard.savedFilters) {
        dashboard.multiFilters = {
            theme: restoreFacetFilter(dashboard.savedFilters.theme, "theme"),
            formulation: restoreFacetFilter(dashboard.savedFilters.formulation, "formulation"),
        };
    } else {
        dashboard.multiFilters = {
            theme: { mode: "include", values: [] },
            formulation: { mode: "include", values: [] },
        };
    }
    $("dashboard-filter-theme-mode").value = dashboard.multiFilters.theme.mode;
    if (saved.runId !== runId) {
        for (const id of ["dashboard-filter-ranking", "dashboard-filter-seed", "dashboard-filter-preset",
            "dashboard-filter-quorum", "dashboard-filter-query"]) $(id).value = "";
        dashboard.distributionHiddenKeys = new Set();
    } else {
        dashboard.distributionHiddenKeys = new Set(Array.isArray(saved.distributionHiddenKeys)
            ? saved.distributionHiddenKeys.map(String) : []);
    }
    dashboard.selectedSeq = saved.runId === runId ? saved.selectedSeq ?? null : null;
    dashboard.restoreSelection = dashboard.selectedSeq != null;
    dashboard.rows = [];
    dashboard.queryByEvaluationId.clear();
    dashboard.themeByEvaluationId.clear();
    dashboard.formulationByEvaluationId.clear();
    dashboard.cursor = 0;
    dashboard.historyExpected = 0;
    dashboard.historyLoading = false;
    dashboard.historyDone = false;
    dashboard.historyError = null;
    $("dashboard-filter-theme-options").replaceChildren();
    $("dashboard-filter-formulation-options").replaceChildren();
    $("dashboard-distribution-options").replaceChildren();
    $("dashboard-metric-distribution").replaceChildren();
    dashboard.distributionSignature = null;
    updateFacetSummary("theme");
    updateFacetSummary("formulation");
    dashboard.state = null;
    dashboard.lastAnalyticsRenderAt = 0;
    dashboard.stepsRenderedSeq = null;
    dashboard.tableLimit = 200;
    dashboard.exclusionLimit = 100;
    $("dashboard-settings").open = false;
    $("dashboard-result-count").textContent = "Abrindo rodada…";
    $("dashboard-launch-hint").textContent = "Abrindo rodada e sincronizando resultados salvos…";
    renderProgress();
    renderHistorySync();
    renderDashboard();
    await pollRun();
    if (generation !== dashboard.runGeneration) return;
    if (runNeedsPolling(dashboard.state?.status) || dashboard.statusPollFailures) {
        const retryDelay = dashboard.statusPollFailures
            ? Math.min(30000, 1500 * (2 ** Math.min(dashboard.statusPollFailures, 4))) : 1500;
        scheduleStatusPoll(retryDelay);
    }
    if (dashboard.cursor < dashboard.historyExpected || !dashboard.historyDone) {
        void loadRunHistory(runId, generation, controller.signal);
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
        distributionHiddenKeys: [...dashboard.distributionHiddenKeys],
        cohortGraphMethods: [...dashboard.cohortGraphMethods],
        cohortBaselineMethods: [...dashboard.cohortBaselineMethods],
        cohortGraphMetric: dashboard.cohortGraphMetric,
        cohortBaselineMetric: dashboard.cohortBaselineMetric,
        selectedSeq: dashboard.selectedSeq,
    });
}

function ensureDashboardTemplateCompatibility() {
    // Flask can keep an older compiled index.html in an already-running dev
    // server while static ES modules update immediately. Add the newly-required
    // controls to that page so the module remains usable until Flask restarts.
    const historyControls = document.querySelector(".dashboard-history-control");
    if (historyControls) {
        for (const [id, text] of [["dashboard-pause-run", "Pausar"], ["dashboard-resume-run", "Retomar"]]) {
            if ($(id)) continue;
            const button = document.createElement("button");
            button.type = "button";
            button.className = "btn-ghost";
            button.id = id;
            button.textContent = text;
            button.hidden = true;
            const status = $("dashboard-status");
            if (status) status.before(button);
            else historyControls.appendChild(button);
        }
        if (!$("dashboard-refresh-run-list")) {
            const refresh = document.createElement("button");
            refresh.type = "button";
            refresh.className = "btn-ghost";
            refresh.id = "dashboard-refresh-run-list";
            refresh.textContent = "Atualizar lista";
            const open = $("dashboard-load-run");
            if (open) open.before(refresh);
            else historyControls.appendChild(refresh);
        }
    }

    if (!$("dashboard-history-sync")) {
        const sync = document.createElement("div");
        sync.id = "dashboard-history-sync";
        sync.className = "dashboard-history-sync";
        sync.hidden = true;
        sync.setAttribute("aria-live", "off");
        const label = document.createElement("span");
        label.id = "dashboard-history-sync-label";
        const progress = document.createElement("progress");
        progress.id = "dashboard-history-sync-progress";
        progress.max = 1; progress.value = 0;
        const retry = document.createElement("button");
        retry.type = "button"; retry.className = "btn-ghost";
        retry.id = "dashboard-history-sync-retry";
        retry.textContent = "Tentar novamente"; retry.hidden = true;
        sync.append(label, progress, retry);
        const launchCard = $("dashboard-progress-wrap")?.closest(".dashboard-launch-card");
        if (launchCard) launchCard.after(sync);
        else $("dashboard-launch-hint")?.after(sync);
    }

    const metricSelect = $("dashboard-metric");
    if (metricSelect && !metricSelect.querySelector('option[value="mrr"]')) {
        const mrr = new Option("MRR@20", "mrr");
        const ndcg = metricSelect.querySelector('option[value="ndcg"]');
        if (ndcg) ndcg.before(mrr);
        else metricSelect.add(mrr);
    }

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
        if ($(config.options) && $(config.summary)) {
            if (type === "formulation") {
                const mode = $("dashboard-filter-formulation-mode");
                mode?.previousElementSibling?.remove();
                mode?.remove();
                $("dashboard-filter-formulation-all")?.remove();
                const details = $(config.summary).closest("details");
                if (details && !details.querySelector(".dashboard-filter-hint")) {
                    const hint = document.createElement("p");
                    hint.className = "dashboard-filter-hint";
                    hint.textContent = "Sem seleção, todas as formulações são exibidas. Marque para mostrar somente as escolhidas.";
                    $(config.summary).after(hint);
                }
                const clear = $("dashboard-filter-formulation-clear");
                if (clear) clear.textContent = "Limpar seleção";
            }
            if (type === "formulation" || $(`dashboard-filter-${type}-mode`)) continue;
        }
        const legacy = $(`dashboard-filter-${type}`);
        const details = document.createElement("details");
        details.className = "dashboard-multi-filter";
        const summary = document.createElement("summary");
        summary.id = config.summary;
        summary.textContent = type === "theme" ? "Temas · todos" : "Formulações · todas";
        details.appendChild(summary);
        if (type === "theme") {
            const modeLabel = document.createElement("label");
            modeLabel.htmlFor = "dashboard-filter-theme-mode";
            modeLabel.textContent = "Filtro de temas";
            const mode = document.createElement("select");
            mode.id = "dashboard-filter-theme-mode";
            mode.add(new Option("Incluir selecionados", "include"));
            mode.add(new Option("Excluir selecionados", "exclude"));
            details.append(modeLabel, mode);
        } else {
            const hint = document.createElement("p");
            hint.className = "dashboard-filter-hint";
            hint.textContent = "Sem seleção, todas as formulações são exibidas. Marque para mostrar somente as escolhidas.";
            details.appendChild(hint);
        }
        const actions = document.createElement("div");
        actions.className = "dashboard-multi-filter-actions";
        if (type === "theme") {
            const selectAll = document.createElement("button");
            selectAll.type = "button"; selectAll.className = "btn-ghost";
            selectAll.id = "dashboard-filter-theme-all";
            selectAll.textContent = "Selecionar todos";
            actions.appendChild(selectAll);
        }
        const clear = document.createElement("button");
        clear.type = "button"; clear.className = "btn-ghost";
        clear.id = `dashboard-filter-${type}-clear`;
        clear.textContent = type === "formulation" ? "Limpar seleção" : "Limpar";
        actions.appendChild(clear); details.appendChild(actions);
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

    {
        const controls = $("dashboard-threshold-enabled")?.closest(".dashboard-threshold-controls");
        if (controls) {
            const enableLabel = $("dashboard-threshold-enabled").closest("label");
            if (!$("dashboard-threshold-mode")) {
                const modeLabel = document.createElement("label");
                modeLabel.htmlFor = "dashboard-threshold-mode";
                modeLabel.textContent = "Modo";
                const mode = document.createElement("select");
                mode.id = "dashboard-threshold-mode";
                mode.add(new Option("Piso absoluto", "absolute"));
                mode.add(new Option("Desvios padrão por configuração", "sd"));
                enableLabel?.after(modeLabel, mode);
            }

            const explanatory = controls.querySelector(".dashboard-muted");
            if (!$("dashboard-absolute-threshold-controls")) {
                const absolute = document.createElement("div");
                absolute.id = "dashboard-absolute-threshold-controls";
                absolute.className = "dashboard-threshold-mode-controls";
                const rangeLabel = controls.querySelector('label[for="dashboard-threshold-range"]');
                for (const node of [rangeLabel, $("dashboard-threshold-range"),
                    $("dashboard-threshold-number"), $("dashboard-threshold-percent")]) {
                    if (node) absolute.appendChild(node);
                }
                controls.insertBefore(absolute, explanatory || null);
            }

            if (!$("dashboard-sd-threshold-controls")) {
                const sdControls = document.createElement("div");
                sdControls.id = "dashboard-sd-threshold-controls";
                sdControls.className = "dashboard-threshold-mode-controls";
                sdControls.hidden = true;
                const sdLabel = document.createElement("label");
                sdLabel.htmlFor = "dashboard-sd-threshold-range";
                sdLabel.textContent = "Manter z ≥";
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
            }

            if (!$("dashboard-threshold-metric-context")) {
                const metricContext = document.createElement("strong");
                metricContext.id = "dashboard-threshold-metric-context";
                metricContext.textContent = "F1@20";
                if (explanatory) explanatory.append(" ", metricContext);
                else controls.appendChild(metricContext);
            }
        }
    }

    if (!$("dashboard-distribution-options") || !$("dashboard-metric-distribution")) {
        const grid = $("panel-dashboard")?.querySelector(".dashboard-chart-grid");
        if (grid) {
            $("dashboard-metric-distribution")?.closest(".dashboard-chart-card")?.remove();
            const card = document.createElement("article");
            card.className = "dashboard-card dashboard-chart-card dashboard-timeline-card dashboard-distribution-card";
            const heading = document.createElement("h3"); heading.textContent = "Distribuição da métrica";
            const caption = document.createElement("p");
            caption.id = "dashboard-distribution-caption"; caption.className = "dashboard-muted";
            caption.textContent = "Cada painel mostra uma configuração, usando os mesmos intervalos e escala.";
            const controls = document.createElement("div"); controls.className = "dashboard-distribution-controls";
            const count = document.createElement("span"); count.id = "dashboard-distribution-count"; count.className = "dashboard-muted";
            const show = document.createElement("button"); show.type = "button"; show.className = "btn-ghost";
            show.id = "dashboard-distribution-show-all"; show.textContent = "Mostrar todas";
            const hide = document.createElement("button"); hide.type = "button"; hide.className = "btn-ghost";
            hide.id = "dashboard-distribution-hide-all"; hide.textContent = "Ocultar todas";
            controls.append(count, show, hide);
            const options = document.createElement("div"); options.id = "dashboard-distribution-options";
            options.className = "dashboard-distribution-options";
            const chart = document.createElement("div");
            chart.id = "dashboard-metric-distribution"; chart.className = "dashboard-distribution-grid";
            card.append(heading, caption, controls, options, chart);
            grid.insertBefore(card, grid.firstChild);
        }
    }

    // Newer dashboard modules may be paired temporarily with an older
    // template held by a running Flask process. Preserve the cohort analysis
    // when that template lacks its card rather than letting rendering abort.
    if (!$("dashboard-graph-cohort-summary") || !$("dashboard-graph-cohort-breakdown")
        || !$("dashboard-graph-cohort-distribution")) {
        const grid = $("panel-dashboard")?.querySelector(".dashboard-chart-grid");
        if (grid) {
            const card = document.createElement("article");
            card.className = "dashboard-card dashboard-chart-card dashboard-graph-cohort-card";
            const heading = document.createElement("h3");
            heading.textContent = "Graph + query_entities vs. sem grafo";
            const description = document.createElement("p");
            description.className = "dashboard-muted";
            description.textContent = "Escolha métodos e uma métrica separadamente para cada grupo. Δ só é calculado quando as métricas dos dois lados são iguais.";
            const summary = $("dashboard-graph-cohort-summary") || document.createElement("p");
            summary.id = "dashboard-graph-cohort-summary";
            summary.className = "dashboard-cohort-summary";
            summary.setAttribute("aria-live", "polite");
            const caption = document.createElement("p");
            caption.className = "dashboard-muted";
            caption.textContent = "Distribuição das médias pareadas por consulta/configuração.";
            const chart = $("dashboard-graph-cohort-distribution") || document.createElement("div");
            chart.id = "dashboard-graph-cohort-distribution";
            chart.className = "dashboard-graph-cohort-distribution";
            const scroll = document.createElement("div");
            scroll.className = "dashboard-cohort-table-scroll";
            const table = document.createElement("table");
            table.className = "dashboard-cohort-table";
            const head = document.createElement("thead");
            const headingRow = document.createElement("tr");
            for (const [id, heading] of [[null, "Formulação"], [null, "Preset"], [null, "Quorum"],
                ["dashboard-cohort-graph-metric-heading", "Graph · F1@20"],
                ["dashboard-cohort-baseline-metric-heading", "Sem grafo · F1@20"],
                ["dashboard-cohort-delta-heading", "Δ F1@20"],
                [null, "Graph / baseline / empate"], [null, "Pares completos / parciais"], [null, "Sem par"]]) {
                const th = document.createElement("th");
                if (id) th.id = id;
                th.scope = "col";
                th.textContent = heading;
                headingRow.appendChild(th);
            }
            head.appendChild(headingRow);
            const body = $("dashboard-graph-cohort-breakdown") || document.createElement("tbody");
            body.id = "dashboard-graph-cohort-breakdown";
            body.innerHTML = '<tr><td colspan="9" class="dashboard-empty">Aguardando resultados.</td></tr>';
            table.append(head, body);
            scroll.appendChild(table);
            card.append(heading, description, summary, caption, chart, scroll);
            const heatmapCard = $("dashboard-heatmap")?.closest("article");
            if (heatmapCard) heatmapCard.before(card);
            else grid.appendChild(card);
        }
    }
}

export async function initDashboard() {
    ensureDashboardTemplateCompatibility();
    const saved = getUiState().batchDashboard || {};
    const savedSettings = saved.settings || {};
    dashboard.multiFilters = {
        theme: restoreFacetFilter(saved.filters?.theme, "theme"),
        formulation: restoreFacetFilter(saved.filters?.formulation, "formulation"),
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
    dashboard.cohortGraphMethods = new Set(Array.isArray(saved.cohortGraphMethods)
        ? saved.cohortGraphMethods.filter((method) => COHORT_GRAPH_METHODS.includes(method))
        : COHORT_GRAPH_METHODS);
    dashboard.cohortBaselineMethods = new Set(Array.isArray(saved.cohortBaselineMethods)
        ? saved.cohortBaselineMethods.filter((method) => COHORT_BASELINE_METHODS.includes(method))
        : COHORT_BASELINE_METHODS);
    const cohortMetricValues = new Set(COHORT_METRICS.map((metric) => metric.value));
    const globalMetric = saved.metric === "mrr" ? "mrr@20" : `${saved.metric || "f1"}@${saved.k || "20"}`;
    const defaultCohortMetric = cohortMetricValues.has(globalMetric) ? globalMetric : "f1@20";
    dashboard.cohortGraphMetric = cohortMetricValues.has(saved.cohortGraphMetric)
        ? saved.cohortGraphMetric : defaultCohortMetric;
    dashboard.cohortBaselineMetric = cohortMetricValues.has(saved.cohortBaselineMetric)
        ? saved.cohortBaselineMetric : defaultCohortMetric;
    dashboard.cohortMenuOpenSide = null;
    $("dashboard-k").value = saved.k || "20";
    $("dashboard-baseline-ranking").value = saved.baseline || "hybrid_max";
    dashboard.thresholdEnabled = Boolean(saved.thresholdEnabled);
    dashboard.thresholdMode = ["absolute", "sd"].includes(saved.thresholdMode) ? saved.thresholdMode : "absolute";
    dashboard.threshold = Number.isFinite(Number(saved.threshold))
        ? Math.min(1, Math.max(0, Number(saved.threshold))) : 0.70;
    dashboard.sdThreshold = Number.isFinite(Number(saved.sdThreshold))
        ? Math.min(2, Math.max(-3, Number(saved.sdThreshold))) : -1;
    dashboard.distributionHiddenKeys = new Set(Array.isArray(saved.distributionHiddenKeys)
        ? saved.distributionHiddenKeys.map(String) : []);
    constrainMetricCutoffs();
    syncMetricView();
    $("dashboard-start").addEventListener("click", startRun);
    $("dashboard-theme-count-preview").addEventListener("click", previewThemeCounts);
    $("dashboard-theme-count-submit").addEventListener("click", attachThemeCounts);
    $("dashboard-theme-count-file").addEventListener("change", (event) => {
        void loadThemeCountFile(event.currentTarget.files?.[0]);
    });
    $("dashboard-theme-count-inputs").addEventListener("input", () => {
        if (!dashboard.themeCountPreview) return;
        dashboard.themeCountPreview = null;
        $("dashboard-theme-count-preview-results").replaceChildren();
        $("dashboard-theme-count-preview-results").hidden = true;
        $("dashboard-theme-count-submit").hidden = true;
        $("dashboard-theme-count-message").textContent = "As entidades foram alteradas. Gere uma nova prévia antes de contar.";
    });
    $("dashboard-figure-start").addEventListener("click", startFigureGeneration);
    for (const [group, selector] of [["rankings", "#dashboard-figure-rankings"],
        ["seeds", "#dashboard-figure-seeds"]]) {
        document.querySelectorAll(`[data-figure-select-all="${group}"]`).forEach((button) => {
            button.addEventListener("click", () => {
                document.querySelectorAll(`${selector} input[type=checkbox]`).forEach((input) => { input.checked = true; });
                renderFigureSelectionPreview();
            });
        });
        document.querySelectorAll(`[data-figure-select-none="${group}"]`).forEach((button) => {
            button.addEventListener("click", () => {
                document.querySelectorAll(`${selector} input[type=checkbox]`).forEach((input) => { input.checked = false; });
                renderFigureSelectionPreview();
            });
        });
    }
    $("dashboard-figure-runs").addEventListener("change", () => { void loadFigureFilterOptions(true); });
    for (const group of FIGURE_FILTER_GROUPS) {
        document.querySelector(`[data-filter-select-all="${group}"]`)?.addEventListener("click", () => {
            figureFilterContainer(group)?.querySelectorAll("input[type=checkbox]")
                .forEach((input) => { input.checked = true; });
            updateFigureFilterCounts();
            renderFigureSelectionPreview();
        });
        document.querySelector(`[data-filter-clear="${group}"]`)?.addEventListener("click", () => {
            figureFilterContainer(group)?.querySelectorAll("input[type=checkbox]")
                .forEach((input) => { input.checked = false; });
            updateFigureFilterCounts();
            renderFigureSelectionPreview();
        });
    }
    $("dashboard-figure-generator").addEventListener("change", (event) => {
        if (event.target.closest(".dashboard-figure-filter-group")) updateFigureFilterCounts();
        renderFigureSelectionPreview();
    });
    $("dashboard-refresh-run-list").addEventListener("click", refreshSavedRuns);
    $("dashboard-pause-run").addEventListener("click", pauseRun);
    $("dashboard-resume-run").addEventListener("click", resumeRun);
    $("dashboard-refresh").addEventListener("click", pollRun);
    $("dashboard-history-sync-retry").addEventListener("click", () => {
        if (!dashboard.runId || !dashboard.runAbort) return;
        dashboard.historyError = null;
        void loadRunHistory(dashboard.runId, dashboard.runGeneration, dashboard.runAbort.signal);
    });
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
    $("dashboard-distribution-show-all").addEventListener("click", () => {
        dashboard.distributionHiddenKeys.clear();
        renderMetricDistribution(dimensionFilteredRows());
        persistDashboardUI();
    });
    $("dashboard-distribution-hide-all").addEventListener("click", () => {
        dashboard.distributionHiddenKeys = new Set(dashboard.distributionStats.keys());
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
        syncFacetOptions("theme", dashboard.rows.map((row) => themeOf(row)));
        syncFacetOptions("formulation", dashboard.rows.map(formulationFor));
        dashboard.thresholdEnabled = false;
        dashboard.thresholdMode = "absolute";
        dashboard.threshold = 0.70;
        dashboard.sdThreshold = -1;
        $("dashboard-exclusion-search").value = "";
        dashboard.tableLimit = 200;
        dashboard.exclusionLimit = 100;
        renderDashboard();
        refreshThemeCountArtifactForThemeFilter();
        persistDashboardUI();
    });
    const themeMode = $("dashboard-filter-theme-mode");
    themeMode.value = dashboard.multiFilters.theme.mode;
    themeMode.addEventListener("change", () => {
        dashboard.multiFilters.theme.mode = themeMode.value === "exclude" ? "exclude" : "include";
        updateFacetSummary("theme");
        dashboard.tableLimit = 200;
        renderDashboard();
        refreshThemeCountArtifactForThemeFilter();
        persistDashboardUI();
    });
    $("dashboard-filter-theme-all").addEventListener("click", () => {
        const config = facetFilterConfig("theme");
        dashboard.multiFilters.theme.values = [...$(config.options).querySelectorAll("input[type=checkbox]")]
            .map((input) => input.value);
        syncFacetOptions("theme", dashboard.rows.map((row) => themeOf(row)));
        dashboard.tableLimit = 200;
        renderDashboard();
        refreshThemeCountArtifactForThemeFilter();
        persistDashboardUI();
    });
    for (const type of ["theme", "formulation"]) {
        $(`dashboard-filter-${type}-clear`).addEventListener("click", () => {
            dashboard.multiFilters[type].values = [];
            syncFacetOptions(type, dashboard.rows.map((row) => type === "theme"
                ? themeOf(row) : formulationFor(row)));
            dashboard.tableLimit = 200;
            renderDashboard();
            if (type === "theme") refreshThemeCountArtifactForThemeFilter();
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
        void refreshSavedRuns();
        if (dashboard.runId) scheduleStatusPoll(0);
    });
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible" && dashboard.runId) {
            void refreshSavedRuns();
            scheduleStatusPoll(0);
        }
    });
    window.addEventListener("resize", () => {
        if (dashboard.runId && $("panel-dashboard").classList.contains("active")) scheduleDashboardRender(true);
    });
    try {
        void revealFigureGeneratorIfAvailable();
        const [datasetsResult, runsResult] = await Promise.allSettled([
            loadDatasets(), refreshRunList(),
        ]);
        const runs = runsResult.status === "fulfilled" ? runsResult.value : [];
        if (datasetsResult.status === "rejected") {
            $("dashboard-launch-hint").textContent = `Não foi possível carregar os temas: ${datasetsResult.reason.message}`;
        }
        if (runsResult.status === "rejected") {
            $("dashboard-launch-hint").textContent = `Não foi possível carregar as rodadas salvas: ${runsResult.reason.message}`;
        }
        const preferred = saved.runId;
        const existing = runs.find((run) => run.run_id === preferred)
            || runs.find((run) => runNeedsPolling(run.status));
        if (existing) {
            $("dashboard-existing-run").value = existing.run_id;
            const activeHint = runNeedsPolling(existing.status)
                ? " A rodada continua em execução; abrir os resultados não é necessário para ela prosseguir."
                : "";
            $("dashboard-launch-hint").textContent =
                `Rodada salva selecionada. Clique em Abrir para carregar os resultados.${activeHint}`;
        } else if (runs.length && !$("dashboard-launch-hint").textContent) {
            $("dashboard-launch-hint").textContent = "Escolha uma rodada salva e clique em Abrir para carregar seus resultados.";
        }
    } catch (error) {
        $("dashboard-launch-hint").textContent = error.message;
    }
}
