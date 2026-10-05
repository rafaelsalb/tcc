let initialized = false;

/**
 * A small "?" badge that explains a UI element in plain language.
 * The bubble opens on hover/focus (CSS) and on click/tap (JS below).
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

function closeAllBubbles() {
    document.querySelectorAll(".help-dot.open").forEach((dot) => dot.classList.remove("open"));
}

/**
 * Tap/click support for the help bubbles. Hover/focus is pure CSS; this
 * handler only toggles the .open class for touch and click users and closes
 * bubbles when clicking anywhere else.
 */
export function initHelpDots() {
    if (initialized) return;
    initialized = true;

    document.addEventListener("click", (event) => {
        const dot = event.target.closest?.(".help-dot");
        if (dot) {
            const wasOpen = dot.classList.contains("open");
            closeAllBubbles();
            if (!wasOpen) dot.classList.add("open");
            return;
        }
        closeAllBubbles();
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeAllBubbles();
    });
}
