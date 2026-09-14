const DATE_GROUP_FORMAT = new Intl.DateTimeFormat("pt-BR", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
});

const SHORT_DATE_FORMAT = new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "UTC",
});

export function parseDate(value) {
    if (!value) return null;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
}

function groupChunksByArticle(response) {
    const map = new Map();
    for (const result of response?.results ?? []) {
        if (result.article_url == null) continue;
        if (!map.has(result.article_url)) map.set(result.article_url, []);
        map.get(result.article_url).push({
            text: result.chunk,
            similarity: result.distance,
            rrfScore: result.rrf_score,
            textRank: result.text_rank,
        });
    }
    for (const chunks of map.values()) {
        chunks.sort((a, b) => (b.rrfScore ?? -Infinity) - (a.rrfScore ?? -Infinity)
            || (b.similarity ?? -Infinity) - (a.similarity ?? -Infinity));
    }
    return map;
}

function viewArticles(state) {
    const response = state.response;
    if (!response || !Array.isArray(response.articles)) return [];

    const chunksByUrl = groupChunksByArticle(response);
    const scores = response.articles_scores ?? {};
    const articles = response.articles.map((article) => ({
        ...article,
        date: parseDate(article.date_published),
        score: scores[article.url] ?? 0,
        chunks: chunksByUrl.get(article.url) ?? [],
    }));

    let selection = articles;
    if (state.topN != null && state.topN >= 1 && state.topN < articles.length) {
        selection = [...articles].sort((a, b) => b.score - a.score).slice(0, state.topN);
    }
    if (state.entityFilter) {
        selection = selection.filter((article) => state.entityFilter.urls.has(article.url));
    }
    return selection;
}

export function computeView(state) {
    const articles = viewArticles(state);
    const sorted = [...articles];
    if (state.sort === "date_asc") {
        sorted.sort((a, b) => (a.date?.getTime() ?? Infinity) - (b.date?.getTime() ?? Infinity));
    } else if (state.sort === "ppr_desc") {
        sorted.sort((a, b) => b.score - a.score);
    } else {
        sorted.sort((a, b) => (b.date?.getTime() ?? -Infinity) - (a.date?.getTime() ?? -Infinity));
    }
    return { articles: sorted, total: articles.length };
}

function emptyState(container, title, message) {
    container.replaceChildren();
    const div = document.createElement("div");
    div.className = "empty-state";
    const heading = document.createElement("div");
    heading.className = "empty-title";
    heading.textContent = title;
    const paragraph = document.createElement("p");
    paragraph.textContent = message;
    div.append(heading, paragraph);
    container.appendChild(div);
}

function chunkChip(label, value) {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.append(label);
    const bold = document.createElement("b");
    bold.textContent = value;
    chip.appendChild(bold);
    return chip;
}

function buildChunkBlock(chunks) {
    const block = document.createElement("div");
    block.className = "chunks";
    block.hidden = true;
    for (const chunk of chunks) {
        const item = document.createElement("div");
        item.className = "chunk";
        const chips = document.createElement("div");
        chips.className = "chunk-chips";
        if (chunk.similarity != null) chips.appendChild(chunkChip("sim", Number(chunk.similarity).toFixed(3)));
        if (chunk.rrfScore != null) chips.appendChild(chunkChip("rrf", Number(chunk.rrfScore).toFixed(4)));
        if (chunk.textRank != null) chips.appendChild(chunkChip("rank", String(chunk.textRank)));
        const text = document.createElement("p");
        text.className = "chunk-text";
        text.textContent = chunk.text;
        item.append(chips, text);
        block.appendChild(item);
    }
    return block;
}

function buildCard(article, maxScore) {
    const card = document.createElement("article");
    card.className = "card";
    card.dataset.url = article.url;

    const head = document.createElement("div");
    head.className = "card-head";

    const titleWrap = document.createElement("div");
    titleWrap.style.minWidth = "0";
    const title = document.createElement("a");
    title.className = "card-title";
    title.href = article.url;
    title.target = "_blank";
    title.rel = "noopener";
    title.textContent = article.title || "(sem título)";
    titleWrap.appendChild(title);

    const meta = document.createElement("div");
    meta.className = "card-meta";
    const dateSpan = document.createElement("span");
    dateSpan.className = "num";
    dateSpan.textContent = article.date ? SHORT_DATE_FORMAT.format(article.date) : "sem data";
    meta.appendChild(dateSpan);
    if (article.chunks.length > 0) {
        const chunkCount = document.createElement("span");
        chunkCount.textContent = `${article.chunks.length} trecho${article.chunks.length > 1 ? "s" : ""} recuperado${article.chunks.length > 1 ? "s" : ""}`;
        meta.appendChild(chunkCount);
    }
    titleWrap.appendChild(meta);

    const badge = document.createElement("div");
    badge.className = "score-badge";
    const value = document.createElement("span");
    value.className = "score-value";
    const valueLabel = document.createElement("span");
    valueLabel.className = "score-label";
    valueLabel.textContent = "PPR";
    value.append(valueLabel, document.createTextNode(article.score.toFixed(3)));
    const bar = document.createElement("div");
    bar.className = "score-bar";
    const barFill = document.createElement("i");
    barFill.style.width = `${maxScore > 0 ? Math.max(2, (article.score / maxScore) * 100) : 0}%`;
    bar.appendChild(barFill);
    badge.append(value, bar);

    head.append(titleWrap, badge);
    card.appendChild(head);

    if (article.excerpt) {
        const excerpt = document.createElement("p");
        excerpt.className = "card-excerpt";
        excerpt.textContent = article.excerpt;
        card.appendChild(excerpt);
    }

    if (article.chunks.length > 0) {
        const chunkBlock = buildChunkBlock(article.chunks);
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "chunk-toggle";
        toggle.setAttribute("aria-expanded", "false");
        toggle.textContent = `Ver trechos recuperados (${article.chunks.length})`;
        toggle.addEventListener("click", () => {
            const expanded = !chunkBlock.hidden;
            chunkBlock.hidden = expanded;
            toggle.setAttribute("aria-expanded", String(!expanded));
            toggle.textContent = expanded
                ? `Ver trechos recuperados (${article.chunks.length})`
                : `Ocultar trechos recuperados (${article.chunks.length})`;
        });
        card.append(toggle, chunkBlock);
    }

    return card;
}

export function renderTimeline(container, state) {
    if (!state.response) {
        emptyState(
            container,
            "Busque um assunto para começar",
            "A busca híbrida recupera os trechos mais relevantes do acervo do G1; o PPR reordena os artigos pela centralidade no grafo de entidades. Use os filtros de data para recortar o período de interesse."
        );
        return;
    }

    const { articles } = computeView(state);
    if (articles.length === 0) {
        emptyState(
            container,
            "Nenhum artigo para exibir",
            state.entityFilter
                ? "Nenhum dos artigos recuperados menciona a entidade selecionada."
                : "Nenhum artigo encontrado para essa busca."
        );
        return;
    }

    const maxScore = Math.max(...articles.map((article) => article.score), 0.000001);
    const groups = new Map();
    for (const article of articles) {
        const key = article.date ? article.date.toISOString().slice(0, 10) : "sem-data";
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(article);
    }

    const sortAscending = state.sort === "date_asc";
    const groupKeys = [...groups.keys()].sort((a, b) => {
        const order = a === "sem-data" ? 1 : b === "sem-data" ? -1 : a.localeCompare(b);
        return sortAscending ? order : -order;
    });

    container.replaceChildren();
    const fragment = document.createDocumentFragment();

    for (const key of groupKeys) {
        const groupArticles = groups.get(key);
        const group = document.createElement("section");
        group.className = "timeline-group";

        const header = document.createElement("header");
        header.className = "timeline-date";
        const label = document.createElement("span");
        label.className = "timeline-date-label";
        label.textContent = key === "sem-data"
            ? "Data desconhecida"
            : DATE_GROUP_FORMAT.format(new Date(`${key}T00:00:00Z`));
        const count = document.createElement("span");
        count.className = "timeline-date-count";
        count.textContent = `${groupArticles.length} artigo${groupArticles.length > 1 ? "s" : ""}`;
        header.append(label, count);

        const cards = document.createElement("div");
        cards.className = "timeline-cards";
        for (const article of groupArticles) {
            cards.appendChild(buildCard(article, maxScore));
        }

        group.append(header, cards);
        fragment.appendChild(group);
    }

    container.appendChild(fragment);
}

export function scrollToArticle(container, url) {
    const card = container.querySelector(`.card[data-url="${CSS.escape(url)}"]`);
    if (!card) return false;
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    card.classList.add("card-flash");
    setTimeout(() => card.classList.remove("card-flash"), 1600);
    return true;
}
