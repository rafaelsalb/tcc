import { computeView } from "./timeline.js";

const ACCENT = "#4f46e5";
const MARGIN = { top: 14, right: 18, bottom: 28, left: 46 };

const X_TICK_FORMAT = new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
});
const FULL_DATE_FORMAT = new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit", month: "short", year: "numeric", timeZone: "UTC",
});

/**
 * The current view, with publication timestamps preserved for a true time axis.
 */
export function computePlotData(state) {
    const { articles } = computeView(state);
    const missingDateCount = articles.filter((article) => !article.date || Number.isNaN(article.date.getTime())).length;
    const points = articles
        .filter((article) => article.date && !Number.isNaN(article.date.getTime()))
        .sort((a, b) => a.date.getTime() - b.date.getTime() || (b.score ?? 0) - (a.score ?? 0))
        .map((article) => ({
            url: article.url,
            title: article.title || article.url,
            score: article.score ?? 0,
            date: article.date.getTime(),
        }));
    return { points, missingDateCount, totalCount: articles.length };
}

function placeholderNode(message) {
    const div = document.createElement("div");
    div.className = "score-plot-placeholder";
    div.textContent = message;
    return div;
}

function showTooltip(tooltipEl, point, px, py, containerEl) {
    tooltipEl.replaceChildren();
    const title = document.createElement("span");
    title.className = "tooltip-label";
    title.textContent = point.title;
    const scoreLine = document.createElement("span");
    scoreLine.textContent = `Relevância ${point.score.toFixed(3)}`;
    tooltipEl.append(title, scoreLine);

    // px/py are relative to the plot container; the shared tooltip lives in the
    // positioned card wrapping the plot, so translate to its coordinate space.
    const cardRect = tooltipEl.parentElement.getBoundingClientRect();
    const containerRect = containerEl.getBoundingClientRect();
    tooltipEl.style.left = `${px + containerRect.left - cardRect.left}px`;
    tooltipEl.style.top = `${py + containerRect.top - cardRect.top}px`;
    tooltipEl.classList.add("visible");
}

function hideTooltip(tooltipEl) {
    tooltipEl.classList.remove("visible");
}

/**
 * Scatter plot with a true date-scaled x axis. Points are independent articles,
 * not a continuous series. Dot click/keyboard activation -> onDotClick(url).
 */
export function renderScorePlot(containerEl, tooltipEl, state, { onDotClick } = {}) {
    if (!containerEl) return;
    if (!state || !state.response) {
        containerEl.hidden = true;
        return;
    }

    const width = Math.max(300, containerEl.clientWidth || 900);
    const height = containerEl.clientHeight || 200;
    const innerWidth = Math.max(50, width - MARGIN.left - MARGIN.right);
    const innerHeight = Math.max(40, height - MARGIN.top - MARGIN.bottom);

    const { points, missingDateCount, totalCount } = computePlotData(state);
    containerEl.hidden = false;
    containerEl.replaceChildren();

    if (points.length === 0) {
        containerEl.appendChild(placeholderNode(
            `Sem artigos com data de publicação. ${missingDateCount} de ${totalCount} artigos foram excluídos deste gráfico.`
        ));
        return;
    }

    const n = points.length;
    const maxScore = Math.max(0.000001, ...points.map((p) => p.score));
    let [minDate, maxDate] = d3.extent(points, (point) => point.date);
    if (minDate === maxDate) {
        minDate -= 12 * 60 * 60 * 1000;
        maxDate += 12 * 60 * 60 * 1000;
    }
    const x = d3.scaleTime().domain([new Date(minDate), new Date(maxDate)]).range([MARGIN.left, MARGIN.left + innerWidth]);
    const y = d3.scaleLinear().domain([0, maxScore]).nice().range([MARGIN.top + innerHeight, MARGIN.top]);
    points.forEach((point) => { point.px = x(new Date(point.date)); point.py = y(point.score); });

    const svg = d3.select(containerEl)
        .append("svg")
        .attr("width", "100%")
        .attr("height", height)
        .attr("viewBox", `0 0 ${width} ${height}`)
        .attr("role", "group")
        .attr("aria-label", `Gráfico de dispersão com ${n} artigos: data de publicação no eixo horizontal e score de relevância relativo a esta busca no eixo vertical.`);
    svg.append("title").text("Artigos por data de publicação e score relativo de relevância");

    const g = svg.append("g");
    const axisFormat = maxDate - minDate > 330 * 24 * 60 * 60 * 1000
        ? new Intl.DateTimeFormat("pt-BR", { month: "short", year: "numeric", timeZone: "UTC" })
        : X_TICK_FORMAT;
    const xAxis = d3.axisBottom(x).ticks(Math.min(6, n)).tickFormat(axisFormat);
    const yAxis = d3.axisLeft(y).ticks(4).tickSize(-innerWidth).tickFormat((value) => Number(value).toFixed(3));
    g.append("g").attr("transform", `translate(0,${MARGIN.top + innerHeight})`).call(xAxis);
    g.append("g").attr("transform", `translate(${MARGIN.left},0)`).call(yAxis);
    g.selectAll(".tick line").attr("stroke", "var(--border)").attr("opacity", 0.45);
    g.append("text").attr("class", "score-plot-axis-label")
        .attr("x", MARGIN.left + innerWidth / 2).attr("y", height - 1).attr("text-anchor", "middle").text("Data de publicação");
    g.append("text").attr("class", "score-plot-axis-label")
        .attr("transform", "rotate(-90)").attr("x", -(MARGIN.top + innerHeight / 2)).attr("y", 12)
        .attr("text-anchor", "middle").text("Score relativo nesta busca");

    const showPointTooltip = (event, point) => {
        const circle = d3.select(event.currentTarget);
        circle.attr("r", 6);
        showTooltip(tooltipEl, point, point.px, point.py - 10, containerEl);
    };
    const hidePointTooltip = (event) => {
        d3.select(event.currentTarget).attr("r", 4);
        hideTooltip(tooltipEl);
    };
    const activatePoint = (event, point) => {
        event.stopPropagation();
        if (onDotClick) onDotClick(point.url);
    };
    g.selectAll("circle.score-plot-dot")
        .data(points)
        .join("circle")
        .attr("class", "score-plot-dot")
        .attr("r", 4)
        .attr("fill", ACCENT)
        .attr("cx", (p) => p.px)
        .attr("cy", (p) => p.py)
        .attr("tabindex", 0).attr("role", "button")
        .attr("aria-label", (point) => `${point.title}, ${FULL_DATE_FORMAT.format(new Date(point.date))}, score relativo ${point.score.toFixed(3)}. Ative para localizar o artigo.`)
        .on("mouseover focus", showPointTooltip)
        .on("mouseout blur", hidePointTooltip)
        .on("click", activatePoint)
        .on("keydown", (event, point) => {
            if (event.key === "Enter" || event.key === " ") { event.preventDefault(); activatePoint(event, point); }
        })
        .append("title").text((point) => `${point.title} · ${FULL_DATE_FORMAT.format(new Date(point.date))} · score ${point.score.toFixed(3)}`);
    const note = document.createElement("p");
    note.className = "score-plot-note";
    note.textContent = `Cada ponto é um artigo; datas no eixo são proporcionais ao tempo. O score é relativo a esta busca, não comparável diretamente entre consultas.${missingDateCount ? ` ${missingDateCount} de ${totalCount} artigos sem data não aparecem.` : ""}`;
    containerEl.appendChild(note);
}
