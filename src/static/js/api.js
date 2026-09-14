export async function searchArticles(params) {
    const qs = new URLSearchParams();
    qs.set("query", params.query);
    if (params.limit) qs.set("limit", params.limit);
    if (params.topK) qs.set("top_k", params.topK);
    if (params.dateFrom) qs.set("date_from", params.dateFrom);
    if (params.dateTo) qs.set("date_to", params.dateTo);

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
