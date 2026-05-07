from flask import Flask, request, jsonify
from app import App as G1App


app = Flask(__name__)
g1_app = G1App()


@app.route("/search", methods=["GET"])
def search():
    params = request.args
    query = params.get("query")
    if query is None:
        return jsonify({"error": "Query parameter is required"}), 400
    top_k = int(params.get("top_k", 100))
    limit = int(params.get("limit", 100))
    offset = int(params.get("offset", 0))
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    if not query:
        return jsonify({"error": "Query is required"}), 400
    results = g1_app.search_service.search(query, top_k=top_k, limit=limit, offset=offset)
    return jsonify(results)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
