import json

from flask import Flask, render_template, request, jsonify
from app import App as G1App
from redis import Redis
import urllib

from repositories.judgments import JudgmentRepository
from services.metrics import DEFAULT_KS, evaluate


app = Flask(__name__)
g1_app = G1App()
r = Redis(decode_responses=True)  # Initialize Redis client with decode_responses=True
judgment_repo = JudgmentRepository(g1_app.article_repo.engine)

@app.route("/search", methods=["GET"])
def search():
    params = request.args
    query = params.get("query")
    if query is None:
        return jsonify({"error": "Query parameter is required"}), 400
    top_k = None
    top_k_param = params.get("top_k")
    if top_k_param is not None:
        top_k_param = top_k_param.strip().lower()
        if top_k_param not in {"", "null", "none"}:
            try:
                top_k = int(top_k_param)
            except ValueError:
                return jsonify({"error": "top_k must be an integer or null"}), 400
    limit = int(params.get("limit", 100))
    offset = int(params.get("offset", 0))
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    if not query:
        return jsonify({"error": "Query is required"}), 400

    query_encoded = urllib.parse.quote(query)
    seed_method = (params.get("seed_method") or "hits").strip().lower()
    if seed_method not in ("hits", "louvain"):
        return jsonify({"error": "seed_method must be 'hits' or 'louvain'"}), 400
    quorum_param = (params.get("quorum") or "").strip()
    if quorum_param:
        try:
            quorum = float(quorum_param)
        except ValueError:
            return jsonify({"error": "quorum must be a number between 0 and 1"}), 400
        if not 0 <= quorum <= 1:
            return jsonify({"error": "quorum must be a number between 0 and 1"}), 400
    else:
        quorum = 0.7
    cache_key = f"v8:{query_encoded}:{top_k}:{limit}:{offset}:{date_from}:{date_to}:{seed_method}:{quorum}"
    cached_result = r.hget("search_cache", cache_key)

    if cached_result:
        return jsonify(json.loads(cached_result))

    results = g1_app.search_service.search(query, top_k=top_k, limit=limit, offset=offset, date_from=date_from, date_to=date_to, quorum_threshold=quorum)
    if not results["articles"]:
        return jsonify(results)
    urls = [result['url'] for result in results['articles']]
    page_rank, ranked, graph_data = g1_app.ranking_service.ppr(urls, seed_method=seed_method)
    results["page_rank"] = page_rank
    results["ranked"] = ranked
    results["graph"] = graph_data
    # UI ranking = normalized personalized PPR (the same metric that orders
    # `ranked` and drives the MMR pass), renormalized to shares of the total
    articles_scores = {entry['article']: entry['score'] for entry in ranked}
    scores_sum = sum(articles_scores.values())
    results["articles_scores"] = {url: score / scores_sum if scores_sum > 0 else 0 for url, score in articles_scores.items()}

    for article in results['articles']:
        article['date_published'] = str(article['date_published']) if article['date_published'] else None

    r.hset("search_cache", cache_key, json.dumps(results, default=str))

    return jsonify(results)

@app.get("/")
def index():
    return render_template("index.html")


@app.get("/articles")
def articles():
    params = request.args
    q = (params.get("q") or "").strip()
    try:
        page = max(1, int(params.get("page", 1)))
        page_size = min(100, max(1, int(params.get("page_size", 20))))
    except ValueError:
        return jsonify({"error": "page and page_size must be integers"}), 400
    offset = (page - 1) * page_size
    try:
        found, total = g1_app.article_repo.search_by_title(q, limit=page_size, offset=offset)
    except Exception:
        return jsonify({"error": "Erro na busca por títulos."}), 500
    return jsonify({
        "articles": [
            {**article, "date_published": str(article["date_published"]) if article["date_published"] else None}
            for article in found
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
    })


@app.get("/judgments")
def judgments():
    label = (request.args.get("label") or "").strip()
    if label:
        return jsonify({"label": label, "urls": judgment_repo.list_by_label(label)})
    return jsonify({"labels": judgment_repo.list_labels()})


@app.post("/judgments")
def save_judgments():
    body = request.get_json(silent=True) or {}
    label = (body.get("label") or "").strip()
    urls = body.get("urls")
    if not label:
        return jsonify({"error": "label is required"}), 400
    if not isinstance(urls, list) or not all(isinstance(url, str) for url in urls):
        return jsonify({"error": "urls must be a list of strings"}), 400
    try:
        judgment_repo.replace_all(label, urls)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"label": label, "urls": judgment_repo.list_by_label(label)})


@app.post("/metrics")
def metrics():
    body = request.get_json(silent=True) or {}
    ranked = body.get("ranked")
    relevant = body.get("relevant")
    ks = body.get("ks")
    if not isinstance(ranked, list) or not all(isinstance(url, str) for url in ranked):
        return jsonify({"error": "ranked must be a list of strings"}), 400
    if not isinstance(relevant, list) or not all(isinstance(url, str) for url in relevant):
        return jsonify({"error": "relevant must be a list of strings"}), 400
    if ks is None:
        ks = list(DEFAULT_KS)
    if not isinstance(ks, list) or not all(isinstance(k, int) and k >= 1 for k in ks) or not ks:
        return jsonify({"error": "ks must be a non-empty list of positive integers"}), 400
    return jsonify(evaluate(ranked, relevant, ks))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
