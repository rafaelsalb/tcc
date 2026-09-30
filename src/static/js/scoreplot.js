import { computeView } from "./timeline.js";

const ACCENT = "#4f46e5";
const MARGIN = { top: 14, right: 18, bottom: 28, left: 46 };

const X_TICK_FORMAT = new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
});

/**
 * Pure data prep: the current view (already filtered by Top-N and entity
 * filters) ordered chronologically — date ascending, score descending within
 * a date. Articles without a publication date are excluded. Spacing is
 * ordinal: every article occupies an even slot on the x-axis regardless of
 * the time gap between publications.
 */
export function computePlotData(state) {
    const { articles } = computeView(state);
    const points = articles
        .filter((article) => article.date && !Number.isNaN(article.date.getTime()))
        .sort((a, b) => a.date.getTime() - b.date.getTime() || (b.score ?? 0) - (a.score ?? 0))
        .map((article) => ({
            url: article.url,
            title: article.title || article.url,
            score: article.score ?? 0,
            date: article.date.getTime(),
        }));
    return { points };
}

function gradientStops(gradient) {
    gradient.append("stop")
        .attr("offset", "0%")
        .attr("stop-color", ACCENT)
        .attr("stop-opacity", 0.28);
    gradient.append("stop")
        .attr("offset", "100%")
        .attr("stop-color", ACCENT)
        .attr("stop-opacity", 0);
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
 * Line plot with a transparent gradient area under the curve, one dot per
 * article, evenly spaced on the x-axis (ordinal — not time-proportional).
 * Only the x-axis labels show dates (the publication date of the article at
 * each labeled slot). Dot click -> onDotClick(url); hover -> tooltip.
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

    const { points } = computePlotData(state);
    containerEl.hidden = false;
    containerEl.replaceChildren();

    if (points.length === 0) {
        containerEl.appendChild(placeholderNode("Sem artigos com data de publicação para exibir."));
        return;
    }

    const n = points.length;
    const maxScore = Math.max(0.000001, ...points.map((p) => p.score));
    const xAt = (index) => n === 1
        ? MARGIN.left + innerWidth / 2
        : MARGIN.left + (index * innerWidth) / (n - 1);
    const y = (score) => MARGIN.top + innerHeight * (1 - score / maxScore);
    points.forEach((p, i) => {
        p.px = xAt(i);
        p.py = y(p.score);
    });

    const svg = d3.select(containerEl)
        .append("svg")
        .attr("width", width)
        .attr("height", height)
        .attr("viewBox", `0 0 ${width} ${height}`);

    const gradient = svg.append("defs")
        .append("linearGradient")
        .attr("id", "score-plot-gradient")
        .attr("x1", "0%")
        .attr("y1", "0%")
        .attr("x2", "0%")
        .attr("y2", "100%");
    gradientStops(gradient);

    const g = svg.append("g");

    const area = d3.area()
        .x((p) => p.px)
        .y0(y(0))
        .y1((p) => y(p.score))
        .curve(d3.curveMonotoneX);
    const line = d3.line()
        .x((p) => p.px)
        .y((p) => y(p.score))
        .curve(d3.curveMonotoneX);

    g.append("path")
        .attr("class", "score-plot-area")
        .attr("fill", "url(#score-plot-gradient)")
        .attr("d", area(points));
    g.append("path")
        .attr("class", "score-plot-line")
        .attr("stroke", ACCENT)
        .attr("stroke-width", 1.5)
        .attr("fill", "none")
        .attr("d", line(points));

    // Y gridlines + tick labels
    for (let i = 0; i <= 4; i++) {
        const tick = (maxScore * i) / 4;
        g.append("line")
            .attr("class", "score-plot-grid")
            .attr("x1", MARGIN.left)
            .attr("x2", MARGIN.left + innerWidth)
            .attr("y1", y(tick))
            .attr("y2", y(tick));
        g.append("text")
            .attr("class", "score-plot-tick")
            .attr("x", MARGIN.left - 6)
            .attr("y", y(tick) + 3)
            .attr("text-anchor", "end")
            .text(i === 0 ? "0" : tick.toFixed(3));
    }

    // X labels: the publication date of the article at evenly sampled slots.
    const labelCount = Math.min(6, n);
    const indices = new Set();
    for (let i = 0; i < labelCount; i++) {
        indices.add(Math.round((i * (n - 1)) / Math.max(1, labelCount - 1)));
    }
    const labeled = [...indices].sort((a, b) => a - b);
    labeled.forEach((index, k) => {
        g.append("text")
            .attr("class", "score-plot-tick score-plot-date")
            .attr("x", xAt(index))
            .attr("y", height - 6)
            .attr("text-anchor", labeled.length === 1 ? "middle" : (k === 0 ? "start" : (k === labeled.length - 1 ? "end" : "middle")))
            .text(X_TICK_FORMAT.format(new Date(points[index].date)));
    });

    // Dots
    g.selectAll("circle.score-plot-dot")
        .data(points)
        .join("circle")
        .attr("class", "score-plot-dot")
        .attr("r", 4)
        .attr("fill", ACCENT)
        .attr("cx", (p) => p.px)
        .attr("cy", (p) => p.py)
        .on("mouseover", (event, p) => {
            d3.select(event.currentTarget).attr("r", 6);
            showTooltip(tooltipEl, p, p.px, p.py - 10, containerEl);
        })
        .on("mouseout", (event) => {
            d3.select(event.currentTarget).attr("r", 4);
            hideTooltip(tooltipEl);
        })
        .on("click", (event, p) => {
            event.stopPropagation();
            if (onDotClick) onDotClick(p.url);
        });
}
