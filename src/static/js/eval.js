import { listJudgmentLabels, getJudgments, saveJudgments, searchArticlesByTitle, computeMetrics } from "./api.js";
import { helpDot } from "./help.js";

const PAGE_SIZE = 20;
const KS = [1, 3, 5, 10, 20];
const DEFAULT_LABEL = "avaliacao-1";

const evalState = {
    q: "",
    page: 1,
    total: 0,
    results: [],
    selected: new Map(), // url -> {title, date_published}
    label: DEFAULT_LABEL,
    labels: [],
    rankedUrls: [],
    metrics: null,
};

let els = null;

function $(id) {
    return document.getElementById(id);
}

function shortDate(value) {
    if (!value) return "sem data";
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? "sem data" : d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" });
}

function esc(value) {
    return value ?? "";
}

function renderResults() {
    const body = els.evalResults;
    body.replaceChildren();
    if (evalState.results.length === 0) {
        const div = document.createElement("div");
        div.className = "eval-empty";
        div.textContent = evalState.q ? "Nenhum artigo encontrado para essa busca." : "Nenhum artigo no banco.";
        body.appendChild(div);
        return;
    }
    for (const article of evalState.results) {
        const row = document.createElement("label");
        row.className = "eval-row";
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = evalState.selected.has(article.url);
        checkbox.addEventListener("change", () => {
            if (checkbox.checked) {
                evalState.selected.set(article.url, { title: article.title, date_published: article.date_published });
            } else {
                evalState.selected.delete(article.url);
            }
            renderSelected();
            renderResults(); // keep checkbox states consistent across pages
            persistSelection();
        });
        const info = document.createElement("div");
        info.className = "eval-row-info";
        const title = document.createElement("span");
        title.className = "eval-row-title";
        title.textContent = article.title || "(sem título)";
        const meta = document.createElement("span");
        meta.className = "eval-row-meta";
        meta.textContent = shortDate(article.date_published);
        info.append(title, meta);
        const link = document.createElement("a");
        link.className = "eval-row-link";
        link.href = article.url;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = "abrir";
        link.addEventListener("click", (e) => e.stopPropagation());
        row.append(checkbox, info, link);
        body.appendChild(row);
    }
}

function renderPager() {
    const pages = Math.max(1, Math.ceil(evalState.total / PAGE_SIZE));
    els.evalPageInfo.textContent = `pág. ${evalState.page} de ${pages} · ${evalState.total} artigos`;
    els.evalPrev.disabled = evalState.page <= 1;
    els.evalNext.disabled = evalState.page >= pages;
}

function renderSelected() {
    const slot = els.evalSelected;
    slot.replaceChildren();
    els.evalSelectedCount.textContent = String(evalState.selected.size);
    for (const [url, info] of evalState.selected) {
        const chip = document.createElement("span");
        chip.className = "entity-chip";
        chip.title = info.title || url;
        chip.append(info.title || url);
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "entity-chip-remove";
        remove.setAttribute("aria-label", `Remover: ${info.title || url}`);
        remove.textContent = "×";
        remove.addEventListener("click", () => {
            evalState.selected.delete(url);
            renderSelected();
            renderResults();
            persistSelection();
        });
        chip.appendChild(remove);
        slot.appendChild(chip);
    }
}

function renderLabels() {
    const select = els.evalLabel;
    select.replaceChildren();
    for (const { label, article_count } of evalState.labels) {
        const option = document.createElement("option");
        option.value = label;
        option.textContent = `${label} (${article_count})`;
        select.appendChild(option);
    }
    if (!evalState.labels.some((l) => l.label === evalState.label)) {
        const option = document.createElement("option");
        option.value = evalState.label;
        option.textContent = evalState.label;
        select.appendChild(option);
    }
    select.value = evalState.label;
}

function renderMetrics() {
    const card = els.evalMetrics;
    card.replaceChildren();
    if (!evalState.rankedUrls.length) {
        const div = document.createElement("div");
        div.className = "eval-empty";
        const hint = document.createElement("span");
        hint.textContent = "Faça uma busca principal para calcular as métricas (Precisão@k / Revocação@k). ";
        div.append(hint, helpDot("Compara os artigos que você marcou com a ordenação da busca principal; k é o número de resultados considerados.", "help-dot--inline"));
        card.appendChild(div);
        return;
    }
    if (evalState.selected.size === 0) {
        const div = document.createElement("div");
        div.className = "eval-empty";
        div.textContent = "Marque os artigos relevantes para calcular as métricas.";
        card.appendChild(div);
        return;
    }
    if (!evalState.metrics) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn-primary";
        button.textContent = "Calcular métricas";
        button.addEventListener("click", () => runMetrics());
        card.appendChild(button);
        return;
    }
    const table = document.createElement("table");
    table.className = "eval-metrics-table";
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    for (const label of ["k", "Acertos", "Precisão@k", "Revocação@k"]) {
        const th = document.createElement("th");
        th.textContent = label;
        headRow.appendChild(th);
    }
    thead.appendChild(headRow);
    const tbody = document.createElement("tbody");
    for (const m of evalState.metrics.metrics) {
        const tr = document.createElement("tr");
        const cells = [
            String(m.k),
            m.hits == null ? "—" : String(m.hits),
            m.precision == null ? "—" : `${(m.precision * 100).toFixed(2)}%`,
            m.recall == null ? "—" : `${(m.recall * 100).toFixed(2)}%`,
        ];
        for (const text of cells) {
            const td = document.createElement("td");
            td.textContent = text;
            tr.appendChild(td);
        }
        tbody.appendChild(tr);
    }
    table.append(thead, tbody);
    const summary = document.createElement("p");
    summary.className = "eval-metrics-summary";
    summary.textContent = `${evalState.metrics.relevant_total} artigos marcados como relevantes · ${evalState.metrics.ranked_total} artigos recuperados pela busca principal.`;
    card.append(table, summary);
}

async function runMetrics() {
    try {
        evalState.metrics = await computeMetrics({
            ranked: evalState.rankedUrls,
            relevant: [...evalState.selected.keys()],
            ks: KS,
        });
        renderMetrics();
    } catch (error) {
        alert(error.message);
    }
}

async function persistSelection() {
    try {
        await saveJudgments(evalState.label, [...evalState.selected.keys()]);
    } catch (error) {
        console.error("Falha ao salvar julgamentos:", error);
    }
}

let saveStatusTimer = null;

function showSaveStatus(message, kind) {
    els.evalSaveStatus.textContent = message;
    els.evalSaveStatus.className = `eval-save-status ${kind}`;
    clearTimeout(saveStatusTimer);
    if (message) {
        saveStatusTimer = setTimeout(() => {
            els.evalSaveStatus.textContent = "";
            els.evalSaveStatus.className = "eval-save-status";
        }, 4000);
    }
}

async function sendSelection() {
    const label = els.evalLabel.value.trim() || evalState.label;
    if (evalState.selected.size === 0) {
        showSaveStatus("Nenhum artigo selecionado.", "warn");
        return;
    }
    try {
        const saved = await saveJudgments(label, [...evalState.selected.keys()]);
        evalState.label = label;
        evalState.labels = await listJudgmentLabels().then((data) => data.labels ?? []).catch(() => evalState.labels);
        renderLabels();
        showSaveStatus(`Salvos ${saved.urls.length} artigos em "${label}".`, "ok");
    } catch (error) {
        showSaveStatus(error.message, "err");
    }
}

async function loadLabel(label) {
    evalState.label = label;
    try {
        const { urls } = await getJudgments(label);
        evalState.selected = new Map();
        for (const url of urls) {
            // details filled lazily from search results when available
            evalState.selected.set(url, { title: evalState.selected.get(url)?.title || url, date_published: null });
        }
        // enrich titles from the current result page when possible
        for (const article of evalState.results) {
            if (evalState.selected.has(article.url)) {
                evalState.selected.set(article.url, { title: article.title, date_published: article.date_published });
            }
        }
        evalState.metrics = null;
        renderSelected();
        renderResults();
        renderMetrics();
    } catch (error) {
        console.error("Falha ao carregar julgamentos:", error);
    }
}

async function runEvalSearch(page = 1) {
    evalState.page = Math.max(1, page);
    try {
        const data = await searchArticlesByTitle({ q: evalState.q, page: evalState.page, pageSize: PAGE_SIZE });
        evalState.results = data.articles;
        evalState.total = data.total;
        for (const article of data.articles) {
            if (evalState.selected.has(article.url)) {
                evalState.selected.set(article.url, { title: article.title, date_published: article.date_published });
            }
        }
        renderResults();
        renderPager();
        renderSelected();
    } catch (error) {
        const body = els.evalResults;
        body.replaceChildren();
        const div = document.createElement("div");
        div.className = "eval-empty";
        div.textContent = error.message;
        body.appendChild(div);
    }
}

export function setEvalResponse(response) {
    const ranked = Array.isArray(response?.ranked) ? response.ranked : [];
    evalState.rankedUrls = ranked.map((entry) => entry.article).filter((url) => typeof url === "string");
    evalState.metrics = null;
    renderMetrics();
}

export function initEvalTab() {
    els = {
        evalQuery: $("eval-query"),
        evalSearchButton: $("eval-search-button"),
        evalResults: $("eval-results"),
        evalPrev: $("eval-prev"),
        evalNext: $("eval-next"),
        evalPageInfo: $("eval-page-info"),
        evalSelected: $("eval-selected"),
        evalSelectedCount: $("eval-selected-count"),
        evalSendButton: $("eval-send-button"),
        evalSaveStatus: $("eval-save-status"),
        evalLabel: $("eval-label"),
        evalMetrics: $("eval-metrics"),
        evalPanel: $("panel-eval"),
    };

    els.evalSearchButton.addEventListener("click", () => {
        evalState.q = els.evalQuery.value.trim();
        runEvalSearch(1);
    });
    els.evalQuery.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            evalState.q = els.evalQuery.value.trim();
            runEvalSearch(1);
        }
    });
    els.evalPrev.addEventListener("click", () => runEvalSearch(evalState.page - 1));
    els.evalNext.addEventListener("click", () => runEvalSearch(evalState.page + 1));
    els.evalLabel.addEventListener("change", () => {
        const label = els.evalLabel.value.trim();
        if (label && label !== evalState.label) loadLabel(label);
    });
    els.evalSendButton.addEventListener("click", sendSelection);

    renderMetrics();

    (async () => {
        try {
            evalState.labels = (await listJudgmentLabels()).labels ?? [];
        } catch {
            evalState.labels = [];
        }
        renderLabels();
        await loadLabel(evalState.label);
        await runEvalSearch(1);
    })();
}
