const STORAGE_KEY = "g1-news-ui-state-v1";

export function getUiState() {
    try {
        const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
        return value && typeof value === "object" && !Array.isArray(value) ? value : {};
    } catch {
        return {};
    }
}

export function setUiState(section, patch) {
    const state = getUiState();
    const current = state[section] && typeof state[section] === "object" ? state[section] : {};
    state[section] = { ...current, ...patch };
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (error) {
        console.warn("Could not persist UI state", error);
    }
}
