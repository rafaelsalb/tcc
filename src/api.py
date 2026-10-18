from flask import Flask, render_template, request, jsonify
from app import App as G1App
from redis import Redis

from repositories.judgments import JudgmentRepository
from services.metrics import DEFAULT_KS, evaluate
from services.search_pipeline import search_request
from services.batch_search import evaluate_request
from services.evaluation_jobs import EvaluationJobManager
from config import REDIS_URL


app = Flask(__name__)
g1_app = G1App()
r = Redis.from_url(REDIS_URL, decode_responses=True)
judgment_repo = JudgmentRepository(g1_app.article_repo.engine)
evaluation_jobs = EvaluationJobManager()

@app.route("/search", methods=["GET"])
def search():
    try:
        return jsonify(search_request(g1_app.search_service, g1_app.ranking_service, r, request.args))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

@app.get("/")
def index():
    return render_template("index.html")


@app.post("/evaluate")
def batch_evaluate():
    try:
        return jsonify(evaluate_request(g1_app.search_service, g1_app.ranking_service,
                                       request.get_json(silent=True)))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/evaluate/jobs")
def start_batch_evaluation_job():
    try:
        body = request.get_json(silent=True)
        job_id = evaluation_jobs.submit(g1_app.search_service, g1_app.ranking_service, body)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({
        "job_id": job_id,
        "status": "queued",
        "status_url": f"/evaluate/jobs/{job_id}",
    }), 202


@app.get("/evaluate/jobs/<job_id>")
def batch_evaluation_job_status(job_id):
    job = evaluation_jobs.get(job_id)
    if job is None:
        return jsonify({"error": "evaluation job not found or expired"}), 404
    return jsonify(job)


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
