from flask import Flask, render_template, request, jsonify, send_file
from pathlib import Path
from app import App as G1App
from redis import Redis

from repositories.judgments import JudgmentRepository
from services.metrics import DEFAULT_KS, evaluate
from services.search_pipeline import search_request
from services.batch_search import evaluate_request
from services.evaluation_jobs import EvaluationJobManager
from services.dashboard_runs import DashboardRunManager
from services.figure_jobs import FigureJobManager
from services.theme_counts import (
    attach_theme_counts, get_theme_count_artifact, get_theme_difficulty_metrics,
    get_theme_eligibility_snapshot, preview_theme_entities,
)
from config import REDIS_URL


app = Flask(__name__)
# The dashboard template and its ES module evolve together. In development,
# do not let Flask keep serving a stale index.html against newer static JS.
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True
g1_app = G1App()
r = Redis.from_url(REDIS_URL, decode_responses=True)
judgment_repo = JudgmentRepository(g1_app.article_repo.engine)
evaluation_jobs = EvaluationJobManager()
repo_root = Path(__file__).resolve().parent.parent
dashboard_runs = DashboardRunManager(
    g1_app.search_service, g1_app.ranking_service, g1_app.article_repo.engine,
    evaluations_directory=repo_root,
)
figure_jobs = FigureJobManager(
    repo_root / "resultados" / "figuras",
    run_exists=dashboard_runs.get,
)

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


@app.get("/dashboard/evaluation-sets")
def dashboard_evaluation_sets():
    return jsonify({"datasets": dashboard_runs.available_sets()})


@app.post("/dashboard/runs")
def start_dashboard_run():
    body = request.get_json(silent=True) or {}
    try:
        run = dashboard_runs.start(body.get("datasets", body.get("dataset")), body.get("settings", {}))
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(run), 202


@app.get("/dashboard/runs")
def list_dashboard_runs():
    return jsonify({"runs": dashboard_runs.list()})


@app.get("/dashboard/figure-jobs")
def dashboard_figure_job_capabilities():
    return jsonify({"enabled": True, "formats": ["pdf", "svg", "png"],
                    "max_runs_per_job": 12,
                    "rankings": ["ppr", "hybrid_max", "rrf", "cross_encoder", "fused", "mmr",
                                 "graph_rwr", "graph_hits", "graph_salsa", "graph_path", "graph_walk",
                                 "graph_fusion", "graph_hits_cross_encoder", "lexical", "vector",
                                 "ensemble_rrf"],
                    "seed_methods": ["louvain", "hits", "ppr_top10", "query_entities"],
                    "figure_families": ["overview", "comparisons", "graph", "cutoff", "tail",
                                        "theme", "runtime", "overlap"]})


@app.post("/dashboard/figure-jobs/filter-options")
def dashboard_figure_filter_options():
    body = request.get_json(silent=True) or {}
    try:
        options = dashboard_runs.figure_filter_options(body.get("run_ids"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(options)


@app.post("/dashboard/figure-jobs")
def start_dashboard_figure_job():
    body = request.get_json(silent=True) or {}
    try:
        job = figure_jobs.submit(
            body.get("run_ids"), formats=body.get("formats"),
            baselines=body.get("baselines"),
            rankings=body.get("rankings"),
            seed_methods=body.get("seed_methods"),
            filters=body.get("filters"),
            figure_families=body.get("figure_families"),
            include_partial=body.get("include_partial", False),
            include_ranking_overlap=body.get("include_ranking_overlap", False),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(job), 202


@app.get("/dashboard/figure-jobs/<job_id>")
def dashboard_figure_job_status(job_id):
    job = figure_jobs.get(job_id)
    if job is None:
        return jsonify({"error": "figure job not found or expired"}), 404
    if job["status"] == "completed":
        job["download_url"] = f"/dashboard/figure-jobs/{job_id}/download"
    return jsonify(job)


@app.get("/dashboard/figure-jobs/<job_id>/download")
def download_dashboard_figures(job_id):
    path = figure_jobs.download_path(job_id)
    if path is None:
        job = figure_jobs.get(job_id)
        if job is None:
            return jsonify({"error": "figure job not found or expired"}), 404
        return jsonify({"error": "figure archive is not ready"}), 409
    return send_file(path, as_attachment=True, download_name=f"evaluation-figures-{job_id}.zip",
                     mimetype="application/zip", conditional=True)


@app.get("/dashboard/runs/<run_id>")
def dashboard_run_status(run_id):
    run = dashboard_runs.get(run_id)
    if run is None:
        return jsonify({"error": "dashboard run not found"}), 404
    return jsonify(run)


@app.get("/dashboard/runs/<run_id>/theme-counts")
def dashboard_run_theme_counts(run_id):
    if dashboard_runs.get(run_id) is None:
        return jsonify({"error": "dashboard run not found"}), 404
    return jsonify({
        "artifact": get_theme_count_artifact(g1_app.article_repo.engine, run_id),
        "metrics": get_theme_difficulty_metrics(g1_app.article_repo.engine, run_id),
    })


@app.get("/dashboard/runs/<run_id>/theme-counts/eligibility/<snapshot_id>")
def dashboard_run_theme_eligibility_snapshot(run_id, snapshot_id):
    if dashboard_runs.get(run_id) is None:
        return jsonify({"error": "dashboard run not found"}), 404
    snapshot = get_theme_eligibility_snapshot(g1_app.article_repo.engine, run_id, snapshot_id)
    if snapshot is None:
        return jsonify({"error": "theme eligibility snapshot not found for this run"}), 404
    return jsonify(snapshot)


@app.post("/dashboard/runs/<run_id>/theme-counts/preview")
def preview_dashboard_run_theme_counts(run_id):
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {"themes"}:
        return jsonify({"error": "request must contain themes"}), 400
    try:
        preview = preview_theme_entities(
            g1_app.article_repo.engine, run_id, body.get("themes"), g1_app.ner_service,
        )
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(preview)


@app.post("/dashboard/runs/<run_id>/theme-counts")
def attach_dashboard_run_theme_counts(run_id):
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or "themes" not in body or set(body) - {
        "themes", "date_range", "main_entities", "entity_resolution",
    }:
        return jsonify({"error": "request must contain themes and optional date_range, main_entities, and entity_resolution"}), 400
    try:
        artifact = attach_theme_counts(
            g1_app.article_repo.engine, run_id, body.get("themes"), body.get("date_range"),
            main_entities=body.get("main_entities"),
            entity_resolution=body.get("entity_resolution"),
        )
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({
        "artifact": artifact,
        "metrics": get_theme_difficulty_metrics(g1_app.article_repo.engine, run_id),
    })


@app.post("/dashboard/runs/<run_id>/pause")
def pause_dashboard_run(run_id):
    try:
        run = dashboard_runs.pause(run_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    if run is None:
        return jsonify({"error": "dashboard run not found"}), 404
    return jsonify(run), 202


@app.post("/dashboard/runs/<run_id>/resume")
def resume_dashboard_run(run_id):
    try:
        run = dashboard_runs.resume(run_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    if run is None:
        return jsonify({"error": "dashboard run not found"}), 404
    return jsonify(run), 202


@app.get("/dashboard/runs/<run_id>/results")
def dashboard_run_results(run_id):
    try:
        after = int(request.args.get("after", 0))
        limit = int(request.args.get("limit", 100))
        if after < 0 or limit < 1:
            raise ValueError
    except ValueError:
        return jsonify({"error": "after must be nonnegative and limit must be positive integers"}), 400
    results = dashboard_runs.results(run_id, after=after, limit=limit)
    if results is None:
        return jsonify({"error": "dashboard run not found"}), 404
    return jsonify(results)


@app.get("/dashboard/runs/<run_id>/results/<int:seq>")
def dashboard_run_result_detail(run_id, seq):
    result = dashboard_runs.result(run_id, seq)
    if result is None:
        return jsonify({"error": "dashboard result not found"}), 404
    return jsonify(result)


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
        app.logger.exception("Erro na busca por títulos.")
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
