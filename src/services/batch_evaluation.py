"""Run repeatable search evaluations from a validated JSON input file."""

import csv
import json
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.models import G1Articles
from services.metrics import DEFAULT_KS, evaluate

SCHEMA_VERSION = 1
MIN_RELEVANT_URLS = 10
SEARCH_DEFAULTS = {
    # Frontend's selected "Balanceado" level.
    "limit": 200,
    "top_k": 30,
    "offset": 0,
    "date_from": None,
    "date_to": None,
    # Frontend's selected topic method and quorum.
    "seed_method": "louvain",
    "quorum": 0.7,
}

DOCUMENT_KEYS = {"schema_version", "evaluations"}
EVALUATION_KEYS = {"id", "query", "relevant_urls"}


def validate_document(document: object) -> list[dict[str, object]]:
    """Validate the rigid JSON schema and return its evaluation entries."""
    if not isinstance(document, dict):
        raise ValueError("input must be a JSON object")
    if set(document) != DOCUMENT_KEYS:
        raise ValueError(
            "top-level keys must be exactly: schema_version, evaluations"
        )
    if (
        type(document["schema_version"]) is not int
        or document["schema_version"] != SCHEMA_VERSION
    ):
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")

    evaluations = document["evaluations"]
    if not isinstance(evaluations, list) or not evaluations:
        raise ValueError("evaluations must be a non-empty array")

    seen_ids: set[str] = set()
    for index, item in enumerate(evaluations):
        location = f"evaluations[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{location} must be an object")
        if set(item) != EVALUATION_KEYS:
            raise ValueError(
                f"{location} keys must be exactly: id, query, relevant_urls"
            )

        for field in ("id", "query"):
            value = item[field]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{location}.{field} must be a non-empty string")
        evaluation_id = item["id"].strip()
        if evaluation_id in seen_ids:
            raise ValueError(f"duplicate evaluation id: {evaluation_id!r}")
        seen_ids.add(evaluation_id)

        urls = item["relevant_urls"]
        if not isinstance(urls, list) or len(urls) < MIN_RELEVANT_URLS:
            raise ValueError(
                f"{location}.relevant_urls must contain at least "
                f"{MIN_RELEVANT_URLS} URLs"
            )
        if any(not isinstance(url, str) or not url.strip() for url in urls):
            raise ValueError(f"{location}.relevant_urls must contain non-empty strings")
        if len(set(urls)) != len(urls):
            raise ValueError(f"{location}.relevant_urls must contain unique URLs")
        for url in urls:
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"{location} contains an invalid absolute URL: {url!r}")

    # The frontend trims the search text before sending it; mirror that here.
    return [
        {**item, "id": item["id"].strip(), "query": item["query"].strip()}
        for item in evaluations
    ]


def load_evaluation_file(path: str | Path) -> list[dict[str, object]]:
    """Read and validate a UTF-8 JSON evaluation file."""
    path = Path(path)
    try:
        with path.open(encoding="utf-8") as input_file:
            document = json.load(input_file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"cannot read evaluation file {path}: {exc}") from exc
    return validate_document(document)


def output_paths(input_path: str | Path, output_path: str | Path | None) -> tuple[Path, Path]:
    input_path = Path(input_path)
    json_path = (
        Path(output_path)
        if output_path is not None
        else input_path.with_name(f"{input_path.stem}.results.json")
    )
    if json_path.suffix.lower() != ".json":
        raise ValueError("--output must have a .json extension")
    csv_path = json_path.with_suffix(".csv")
    if not json_path.parent.is_dir() or not csv_path.parent.is_dir():
        raise ValueError(f"output directory does not exist: {json_path.parent}")
    input_resolved = input_path.resolve()
    if input_resolved in {json_path.resolve(), csv_path.resolve()}:
        raise ValueError("output files must not overwrite the input file")
    return json_path, csv_path


def ensure_output_available(paths: tuple[Path, Path], overwrite: bool) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            f"output already exists ({', '.join(existing)}); pass --overwrite to replace it"
        )


def _validate_relevant_urls_exist(engine, evaluations: list[dict[str, object]]) -> None:
    urls = list(dict.fromkeys(
        url
        for item in evaluations
        for url in item["relevant_urls"]
    ))
    existing: set[str] = set()
    # Keep each IN query small enough for PostgreSQL's bind-parameter limits.
    with Session(engine) as session:
        for start in range(0, len(urls), 1000):
            batch = urls[start : start + 1000]
            existing.update(
                session.scalars(select(G1Articles.url).where(G1Articles.url.in_(batch)))
            )
    missing = [url for url in urls if url not in existing]
    if missing:
        raise ValueError(
            f"relevant_urls not found in g1_articles ({len(missing)} missing): "
            f"{missing[:5]}"
        )


def _csv_rows(report: dict[str, object]) -> tuple[list[str], list[dict[str, object]]]:
    ks = report["ks"]
    fields = ["id", "query", "relevant_total", "ranked_total"]
    for k in ks:
        fields.extend((f"hits@{k}", f"precision@{k}", f"recall@{k}"))

    rows = []
    for item in report["evaluations"]:
        row = {
            "id": item["id"],
            "query": item["query"],
            "relevant_total": item["metrics"]["relevant_total"],
            "ranked_total": item["metrics"]["ranked_total"],
        }
        by_k = {metric["k"]: metric for metric in item["metrics"]["metrics"]}
        for k in ks:
            metric = by_k[k]
            row[f"hits@{k}"] = metric["hits"]
            row[f"precision@{k}"] = metric["precision"]
            row[f"recall@{k}"] = metric["recall"]
        rows.append(row)
    return fields, rows


def run_batch_evaluation(
    app,
    evaluations: list[dict[str, object]],
    json_path: Path,
    csv_path: Path,
) -> dict[str, object]:
    """Run evaluations with the frontend's default search/ranking settings."""
    _validate_relevant_urls_exist(app.article_repo.engine, evaluations)
    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "search_defaults": SEARCH_DEFAULTS,
        "ks": list(DEFAULT_KS),
        "evaluations": [],
    }

    for item in evaluations:
        search_result = app.search_service.search(
            item["query"],
            top_k=SEARCH_DEFAULTS["top_k"],
            limit=SEARCH_DEFAULTS["limit"],
            offset=SEARCH_DEFAULTS["offset"],
            date_from=SEARCH_DEFAULTS["date_from"],
            date_to=SEARCH_DEFAULTS["date_to"],
            quorum_threshold=SEARCH_DEFAULTS["quorum"],
        )
        article_urls = list(dict.fromkeys(
            article["url"] for article in search_result.get("articles", [])
        ))
        if article_urls:
            _, ranked, _ = app.ranking_service.ppr(
                article_urls,
                seed_method=SEARCH_DEFAULTS["seed_method"],
            )
            ranked_urls = [entry["article"] for entry in ranked]
        else:
            ranked_urls = []

        report["evaluations"].append({
            "id": item["id"],
            "query": item["query"],
            "relevant_urls": item["relevant_urls"],
            "ranked_urls": ranked_urls,
            "metrics": evaluate(ranked_urls, item["relevant_urls"], DEFAULT_KS),
        })

    with json_path.open("w", encoding="utf-8") as output_file:
        json.dump(report, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")

    fields, rows = _csv_rows(report)
    with csv_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    return report
