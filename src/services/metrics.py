DEFAULT_KS = (1, 3, 5, 10, 20)


def evaluate(ranked_urls: list[str], relevant_urls: list[str], ks: list[int] | tuple[int, ...] = DEFAULT_KS) -> dict:
    """Precision@k and Recall@k of `ranked_urls` against judged-relevant articles.

    Relevant articles that were never retrieved count against recall (standard
    IR definition). Duplicates are removed; k values are clamped to the ranked
    list length.
    """
    relevant = [url for url in dict.fromkeys(relevant_urls) if url]
    ranked = [url for url in dict.fromkeys(ranked_urls) if url]
    relevant_set = set(relevant)

    if not relevant or not ranked:
        return {
            "metrics": [
                {"k": k, "hits": None, "precision": None, "recall": None}
                for k in ks
            ],
            "relevant_total": len(relevant),
            "ranked_total": len(ranked),
        }

    metrics = []
    for k in ks:
        k = max(1, k)
        cutoff = min(k, len(ranked))
        top = ranked[:cutoff]
        hits = sum(1 for url in top if url in relevant_set)
        metrics.append({
            "k": k,
            "hits": hits,
            # when k exceeds the retrieved set, precision is computed at the
            # available cutoff (the whole ranked list was inspected)
            "precision": hits / cutoff,
            "recall": hits / len(relevant),
        })
    return {
        "metrics": metrics,
        "relevant_total": len(relevant),
        "ranked_total": len(ranked),
    }
