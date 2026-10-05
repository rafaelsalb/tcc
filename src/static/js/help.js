let initialized = false;
let bubble = null;
let hoverDot = null;
let pinnedDot = null;

const VIEWPORT_MARGIN = 8; // px needed above the dot before the bubble flips below

/**
 * A small "?" badge that explains a UI element in plain language.
 * The text is read from data-help and shown in one shared bubble appended
 * to <body> (position: fixed), so no ancestor's overflow can clip it.
 */
export function helpDot(text, extraClass = "") {
    const dot = document.createElement("button");
    dot.type = "button";
    dot.className = `help-dot${extraClass ? ` ${extraClass}` : ""}`;
    dot.textContent = "?";
    dot.setAttribute("data-help", text);
    dot.setAttribute("aria-label", "Ajuda: clique ou passe o mouse para ler a explicação");
    dot.addEventListener("click", (event) => event.stopPropagation());
    return dot;
}

function ensureBubble() {
    if (bubble) return bubble;
    bubble = document.createElement("div");
    bubble.id = "help-bubble";
    bubble.setAttribute("role", "tooltip");
    document.body.appendChild(bubble);
    return bubble;
}

function positionBubble(dot) {
    const rect = dot.getBoundingClientRect();
    bubble.textContent = dot.getAttribute("data-help") || "";

    // measure while hidden but laid out
    bubble.style.visibility = "hidden";
    bubble.classList.add("visible");
    const bubbleRect = bubble.getBoundingClientRect();

    const left = Math.min(
        Math.max(VIEWPORT_MARGIN, rect.left + rect.width / 2 - bubbleRect.width / 2),
        window.innerWidth - bubbleRect.width - VIEWPORT_MARGIN
    );
    // keep the arrow pointing at the dot even when the bubble is clamped
    const arrowLeft = Math.min(
        Math.max(12, rect.left + rect.width / 2 - left),
        bubbleRect.width - 12
    );
    bubble.style.setProperty("--arrow-left", `${arrowLeft}px`);
    // fixed positioning ignores ancestor overflow; the only clipping risk is
    // the viewport itself — flip below when there is no room above the dot
    const flip = rect.top < bubbleRect.height + 8 + VIEWPORT_MARGIN;

    bubble.classList.toggle("below", flip);
    if (flip) {
        bubble.style.top = `${Math.min(rect.bottom + 8, window.innerHeight - bubbleRect.height - VIEWPORT_MARGIN)}px`;
    } else {
        bubble.style.top = `${rect.top - bubbleRect.height - 8}px`;
    }
    bubble.style.left = `${left}px`;
    bubble.style.visibility = "";
}

function showFor(dot) {
    ensureBubble();
    positionBubble(dot);
}

function hideBubble() {
    hoverDot = null;
    pinnedDot = null;
    bubble?.classList.remove("visible", "below");
}

/**
 * Hover/focus shows the bubble transiently; click/tap pins it until an
 * outside click, Escape, scroll or resize. Hovering another dot while one is
 * pinned previews it and restores the pinned one on mouse-out. All listeners
 * are delegated on document, so dots created later need no individual wiring.
 */
export function initHelpDots() {
    if (initialized) return;
    initialized = true;

    document.addEventListener("mouseover", (event) => {
        const dot = event.target.closest?.(".help-dot");
        if (!dot || dot === hoverDot) return;
        hoverDot = dot;
        showFor(dot);
    });

    document.addEventListener("mouseout", (event) => {
        const dot = event.target.closest?.(".help-dot");
        if (!dot || dot !== hoverDot) return;
        hoverDot = null;
        if (pinnedDot) {
            showFor(pinnedDot); // restore the pinned dot's bubble
        } else {
            bubble?.classList.remove("visible", "below");
        }
    });

    document.addEventListener("focusin", (event) => {
        const dot = event.target.closest?.(".help-dot");
        if (!dot || dot === hoverDot) return;
        hoverDot = dot;
        showFor(dot);
    });

    document.addEventListener("focusout", (event) => {
        const dot = event.target.closest?.(".help-dot");
        if (!dot || dot !== hoverDot || pinnedDot) return;
        hoverDot = null;
        bubble?.classList.remove("visible", "below");
    });

    document.addEventListener("click", (event) => {
        const dot = event.target.closest?.(".help-dot");
        if (dot) {
            if (pinnedDot === dot) {
                hideBubble();
            } else {
                pinnedDot = dot;
                hoverDot = dot;
                showFor(dot);
            }
            return;
        }
        if (hoverDot || pinnedDot) hideBubble();
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") hideBubble();
    });

    window.addEventListener("scroll", () => {
        if (hoverDot || pinnedDot) hideBubble();
    }, { passive: true, capture: true });
    window.addEventListener("resize", () => {
        if (hoverDot || pinnedDot) hideBubble();
    });
}
