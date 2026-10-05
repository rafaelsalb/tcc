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

export function normalizeText(value) {
    return (value ?? "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .trim();
}

export function matchEntities(response, queryString, limit = 50) {
    const graph = response?.graph;
    if (!graph || !Array.isArray(graph.nodes)) return [];
    const needle = normalizeText(queryString);
    const entities = graph.nodes.filter((node) => node.type !== "article");
    const matched = needle
        ? entities.filter((node) => normalizeText(node.label || node.id).includes(needle))
        : entities;
    return matched
        .sort((a, b) => (b.degree ?? 0) - (a.degree ?? 0)
            || (a.label || "").localeCompare(b.label || "", "pt-BR"))
        .slice(0, limit);
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

function buildArticleEntities(response) {
    const graph = response?.graph;
    const map = new Map();
    if (!graph || !Array.isArray(graph.nodes) || !Array.isArray(graph.links)) return map;

    const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
    for (const link of graph.links) {
        const source = typeof link.source === "object" ? link.source.id : link.source;
        const target = typeof link.target === "object" ? link.target.id : link.target;
        for (const [articleId, otherId] of [[source, target], [target, source]]) {
            const article = nodeById.get(articleId);
            const other = nodeById.get(otherId);
            if (!article || !other || article.type !== "article" || other.type === "article") continue;
            if (!map.has(articleId)) map.set(articleId, []);
            const list = map.get(articleId);
            if (list.some((e) => e.id === other.id)) continue;
            list.push({
                id: other.id,
                label: other.label || other.id,
                degree: other.degree ?? 0,
                pprSeed: Boolean(other.ppr_seed),
            });
        }
    }
    for (const list of map.values()) {
        list.sort((a, b) => (b.degree ?? 0) - (a.degree ?? 0) || a.label.localeCompare(b.label, "pt-BR"));
    }
    return map;
}

/**
 * URLs of the articles the backend flagged with the MMR diversity pass
 * (`response.ranked`). Empty when the payload predates that field.
 */
export function mmrFlaggedUrls(response) {
    if (!Array.isArray(response?.ranked)) return new Set();
    return new Set(
        response.ranked
            .filter((entry) => entry?.mmr === true && typeof entry.article === "string")
            .map((entry) => entry.article)
    );
}

function viewArticles(state) {
    const response = state.response;
    if (!response || !Array.isArray(response.articles)) return [];

    const chunksByUrl = groupChunksByArticle(response);
    const scores = response.articles_scores ?? {};
    const flagged = mmrFlaggedUrls(response);
    const articles = response.articles.map((article) => ({
        ...article,
        date: parseDate(article.date_published),
        score: scores[article.url] ?? 0,
        mmr: flagged.has(article.url),
        chunks: chunksByUrl.get(article.url) ?? [],
    }));

    let selection = articles;
    if (state.topN != null && state.topN >= 1 && state.topN < selection.length) {
        selection = [...selection].sort((a, b) => b.score - a.score).slice(0, state.topN);
    }
    if (state.entityFilters && state.entityFilters.size > 0) {
        const filters = [...state.entityFilters.values()];
        selection = state.entityMatch === "all"
            ? selection.filter((article) => filters.every((f) => f.urls.has(article.url)))
            : selection.filter((article) => filters.some((f) => f.urls.has(article.url)));
    }
    return selection;
}

/**
 * URLs of the top-N articles by relevance score (the same ranking the
 * timeline's Top-N filter uses). Returns all URLs when topN covers the set.
 */
export function topArticleUrls(response, topN) {
    const scores = response?.articles_scores ?? {};
    const articles = [...(response?.articles ?? [])]
        .sort((a, b) => (scores[b.url] ?? 0) - (scores[a.url] ?? 0));
    if (topN != null && topN >= 1 && topN < articles.length) {
        return new Set(articles.slice(0, topN).map((article) => article.url));
    }
    return new Set(articles.map((article) => article.url));
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
        if (chunk.similarity != null) {
            const percent = Math.max(0, Math.min(100, Math.round(Number(chunk.similarity) * 100)));
            chips.appendChild(chunkChip("Afinidade", `${percent}%`));
        }
        const text = document.createElement("p");
        text.className = "chunk-text";
        text.textContent = chunk.text;
        item.append(chips, text);
        block.appendChild(item);
    }
    return block;
}

function buildEntityTag(entity, active) {
    const tag = document.createElement("button");
    tag.type = "button";
    tag.className = `entity-tag${active ? " active" : ""}`;
    tag.textContent = entity.label;
    if (entity.pprSeed) {
        tag.title = "Tópico Principal";
        const star = document.createElement("span");
        star.className = "seed-mark";
        star.textContent = "★";
        star.setAttribute("aria-label", "Tópico Principal");
        tag.appendChild(star);
    }
    tag.addEventListener("click", () => {
        tag.dispatchEvent(new CustomEvent("entity-toggle", {
            detail: { id: entity.id, label: entity.label },
            bubbles: true,
        }));
    });
    return tag;
}

function buildTagRow(entities, state) {
    const row = document.createElement("div");
    row.className = "card-tags";
    const MAX_TAGS = 8;
    const selected = state.entityFilters ?? new Map();
    for (const entity of entities.slice(0, MAX_TAGS)) {
        row.appendChild(buildEntityTag(entity, selected.has(entity.id)));
    }
    if (entities.length > MAX_TAGS) {
        const more = document.createElement("span");
        more.className = "entity-tag-more";
        more.textContent = `+${entities.length - MAX_TAGS}`;
        more.title = entities.slice(MAX_TAGS).map((e) => e.label).join(", ");
        row.appendChild(more);
    }
    return row;
}

function buildCard(article, maxScore, entities, state, rank) {
    const card = document.createElement("article");
    card.className = "card";
    card.dataset.url = article.url;
    if (article.mmr) {
        card.classList.add("mmr-tagged");
    }

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
    if (rank != null) {
        const rankChip = document.createElement("span");
        rankChip.className = "rank-chip";
        rankChip.textContent = `#${rank}`;
        meta.appendChild(rankChip);
    }
    if (article.mmr) {
        const mmrChip = document.createElement("span");
        mmrChip.className = "mmr-chip";
        mmrChip.textContent = "MMR";
        mmrChip.title = "Selecionado por diversidade (MMR)";
        mmrChip.setAttribute("aria-label", "Selecionado por diversidade (MMR)");
        meta.appendChild(mmrChip);
    }
    const dateSpan = document.createElement("span");
    dateSpan.className = "num";
    dateSpan.textContent = article.date ? SHORT_DATE_FORMAT.format(article.date) : "sem data";
    meta.appendChild(dateSpan);
    if (article.chunks.length > 0) {
        const chunkCount = document.createElement("span");
        chunkCount.textContent = `${article.chunks.length} trecho${article.chunks.length > 1 ? "s" : ""} relacionado${article.chunks.length > 1 ? "s" : ""}`;
        meta.appendChild(chunkCount);
    }
    titleWrap.appendChild(meta);

    const badge = document.createElement("div");
    badge.className = "score-badge";
    const value = document.createElement("span");
    value.className = "score-value";
    const valueLabel = document.createElement("span");
    valueLabel.className = "score-label";
    valueLabel.textContent = "Relevância";
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
        toggle.textContent = `Ver trechos relacionados (${article.chunks.length})`;
        toggle.addEventListener("click", () => {
            const expanded = !chunkBlock.hidden;
            chunkBlock.hidden = expanded;
            toggle.setAttribute("aria-expanded", String(!expanded));
            toggle.textContent = expanded
                ? `Ver trechos relacionados (${article.chunks.length})`
                : `Ocultar trechos relacionados (${article.chunks.length})`;
        });
        card.append(toggle, chunkBlock);
    }

    if (entities.length > 0) {
        card.appendChild(buildTagRow(entities, state));
    }

    return card;
}

export function renderTimeline(container, state) {
    if (!state.response) {
        emptyState(
            container,
            "Busque um assunto para começar",
            "Explore a cobertura do G1 sobre um assunto: os resultados são organizados em uma linha do tempo, e o mapa de tópicos mostra os assuntos que conectam as matérias."
        );
        return;
    }

    const { articles } = computeView(state);
    if (articles.length === 0) {
        const hasFilters = state.entityFilters && state.entityFilters.size > 0;
        emptyState(
            container,
            "Nenhum artigo para exibir",
            hasFilters
                ? (state.entityMatch === "all"
                    ? "Nenhum artigo menciona todos os tópicos selecionados. Tente o modo \u201cQualquer\u201d ou remova alguns filtros."
                    : "Nenhum artigo menciona os tópicos selecionados.")
                : "Nenhum artigo encontrado para essa busca."
        );
        return;
    }

    const maxScore = Math.max(...articles.map((article) => article.score), 0.000001);
    const entitiesByArticle = buildArticleEntities(state.response);
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

    if (state.sort === "ppr_desc") {
        // Score ordering is global: a flat list makes the PPR ranking visible,
        // unlike per-date groups where reordering is barely perceptible.
        container.classList.add("flat");
        const cards = document.createElement("div");
        cards.className = "timeline-cards timeline-cards-flat";
        articles.forEach((article, index) => {
            cards.appendChild(
                buildCard(article, maxScore, entitiesByArticle.get(article.url) ?? [], state, index + 1)
            );
        });
        fragment.appendChild(cards);
        container.appendChild(fragment);
        return;
    }

    container.classList.remove("flat");
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
            cards.appendChild(buildCard(article, maxScore, entitiesByArticle.get(article.url) ?? [], state));
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
