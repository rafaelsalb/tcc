import json

from flask import Flask, render_template, request, jsonify
from app import App as G1App
from redis import Redis
import urllib


app = Flask(__name__)
g1_app = G1App()
r = Redis(decode_responses=True)  # Initialize Redis client with decode_responses=True

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
    cached_result = r.hget("search_cache", f"{query_encoded}:{top_k}:{limit}:{offset}:{date_from}:{date_to}")

    if cached_result:
        return jsonify(json.loads(cached_result))

    results = g1_app.search_service.search(query, top_k=top_k, limit=limit, offset=offset, date_from=date_from, date_to=date_to)
    if not results["articles"]:
        return jsonify(results)
    urls = [result['url'] for result in results['articles']]
    page_rank, ranked, graph_data = g1_app.ranking_service.ppr(urls)
    results["page_rank"] = page_rank
    results["ranked"] = ranked
    results["graph"] = graph_data
    # definir o limiar como o terceiro quartil dos scores de PageRank dos artigos retornados
    articles_scores = {article['url']: results["page_rank"].get(article['url'], 0) for article in results['articles']}
    results["articles_scores"] = articles_scores
    scores_sum = sum(articles_scores.values())
    results["articles_scores"] = {url: score / scores_sum if scores_sum > 0 else 0 for url, score in articles_scores.items()}

    for article in results['articles']:
        article['date_published'] = str(article['date_published']) if article['date_published'] else None

    r.hset("search_cache", f"{query_encoded}:{top_k}:{limit}:{offset}:{date_from}:{date_to}", json.dumps(results, default=str))

    return jsonify(results)

@app.get("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
