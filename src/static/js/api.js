export async function searchArticles(params) {
    const qs = new URLSearchParams();
    qs.set("query", params.query);
    if (params.limit) qs.set("limit", params.limit);
    if (params.topK) qs.set("top_k", params.topK);
    if (params.dateFrom) qs.set("date_from", params.dateFrom);
    if (params.dateTo) qs.set("date_to", params.dateTo);
    if (params.seedMethod) qs.set("seed_method", params.seedMethod);
    if (params.quorum) qs.set("quorum", params.quorum);

    let response;
    try {
        response = await fetch(`/search?${qs.toString()}`);
    } catch {
        throw new Error("Falha de rede ao contatar o servidor.");
    }

    if (!response.ok) {
        let message = `Erro ${response.status} na busca.`;
        try {
            const body = await response.json();
            if (body && body.error) message = body.error;
        } catch { /* body was not JSON */ }
        throw new Error(message);
    }

    return response.json();
}

async function fetchJson(url, options) {
    let response;
    try {
        response = await fetch(url, options);
    } catch {
        throw new Error("Falha de rede ao contatar o servidor.");
    }
    if (!response.ok) {
        let message = `Erro ${response.status}.`;
        try {
            const body = await response.json();
            if (body && body.error) message = body.error;
        } catch { /* body was not JSON */ }
        throw new Error(message);
    }
    return response.json();
}

export async function searchArticlesByTitle({ q = "", page = 1, pageSize = 20 }) {
    const qs = new URLSearchParams();
    qs.set("q", q);
    qs.set("page", String(page));
    qs.set("page_size", String(pageSize));
    return fetchJson(`/articles?${qs.toString()}`);
}

export async function listJudgmentLabels() {
    return fetchJson("/judgments");
}

export async function getJudgments(label) {
    const qs = new URLSearchParams();
    qs.set("label", label);
    return fetchJson(`/judgments?${qs.toString()}`);
}

export async function saveJudgments(label, urls) {
    return fetchJson("/judgments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label, urls }),
    });
}

export async function computeMetrics({ ranked, relevant, ks }) {
    return fetchJson("/metrics", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ranked, relevant, ks }),
    });
}
