"""Generate reproducible thesis figures from persisted dashboard evaluation runs.

Examples:
    uv run python scripts/generate_evaluation_figures.py --list-runs
    uv run python scripts/generate_evaluation_figures.py --run-id RUN_ID
    uv run python scripts/generate_evaluation_figures.py --run-id RUN_A --run-id RUN_B \
        --output-dir resultados/figuras --include-ranking-overlap

Runs are always rendered into separate directories. This intentionally avoids
silently pooling datasets while the authoritative run/protocol is undecided.
It never changes evaluation results; for older completed runs it may populate
the derived group-count cache used to accelerate later figure generation.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import itertools
import json
import math
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sqlalchemy import bindparam, create_engine, text


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

DEFAULT_OUTPUT_DIR = ROOT / "resultados" / "figuras"
PROGRESS_PREFIX = "FIGURE_PROGRESS "
PARTIAL_INCLUSIVE = False
SEED_INDEPENDENT = {"hybrid_max", "rrf", "cross_encoder", "lexical", "vector"}
GRAPH_RANKINGS = {
    "ppr", "fused", "mmr", "graph_rwr", "graph_hits", "graph_salsa", "graph_path",
    "graph_walk", "graph_fusion", "graph_hits_cross_encoder", "ensemble_rrf",
}
SUPPORTED_RANKINGS = GRAPH_RANKINGS | SEED_INDEPENDENT
SUPPORTED_SEED_METHODS = {"louvain", "hits", "ppr_top10", "query_entities"}
FIGURE_FAMILIES = {
    "overview": "Visão geral e qualidade",
    "comparisons": "Comparações pareadas",
    "graph": "Métodos e diagnósticos de grafo",
    "cutoff": "Perfis por corte",
    "tail": "Cauda de desempenho",
    "theme": "Variação por tema",
    "runtime": "Custo computacional",
    "overlap": "Sobreposição top-20",
}
DEFAULT_FIGURE_FAMILIES = set(FIGURE_FAMILIES) - {"overlap"}
FORMULATION_LABELS = {
    "keyword": "Palavras-chave",
    "short_theme": "Tema curto",
    "specific_keywords": "Palavras-chave específicas",
    "broad_theme": "Tema amplo",
    "short_question": "Pergunta curta",
    "specific_question": "Pergunta específica",
    "information_request": "Pedido de informação",
    "baseline": "Consulta de referência",
    "unspecified": "Não especificada",
}
FORMULATION_TICK_LABELS = {
    "Consulta de referência": "Consulta ref.",
    "Palavras-chave específicas": "Palavras-chave esp.",
    "Pedido de informação": "Pedido info.",
    "Pergunta específica": "Pergunta esp.",
}
THEME_LABELS = {
    "acordo_mercosul_uniao_europeia": "Acordo Mercosul–União Europeia",
    "eleicoes_brasil_2026": "Eleições no Brasil (2026)",
    "gripe_aviaria_brasil": "Gripe aviária no Brasil",
    "guerra_israel_ira_2025": "Guerra entre Israel e Irã (2025)",
    "mundial_clubes_2025": "Copa do Mundo de Clubes (2025)",
    "brics_rio_2025": "BRICS no Rio de Janeiro (2025)",
    "concurso_nacional_unificado_2025": "Concurso Nacional Unificado (2025)",
    "crise_venezuela_2026": "Crise na Venezuela (2026)",
    "dengue_brasil_2025_2026": "Dengue no Brasil (2025–2026)",
    "enem_2025": "ENEM (2025)",
    "gaza_2025_2026": "Gaza (2025–2026)",
    "imposto_renda_2026": "Imposto de Renda (2026)",
    "libertadores_2025": "Copa Libertadores (2025)",
    "pix_brasil": "Pix no Brasil",
    "queda_aviao_air_india_2025": "Queda de avião da Air India (2025)",
    "banco_master": "Banco Master",
    "cao_orelha": "Cão Orelha",
    "caso_benicio": "Caso Benício",
    "cop30_negociacoes": "Negociações da COP30",
    "descontos_inss": "Descontos do INSS",
    "julgamento_nucleo_golpe": "Julgamento do núcleo da tentativa de golpe",
    "juliana_marins": "Juliana Marins",
    "metanol_bebidas": "Metanol em bebidas",
    "operacao_contencao": "Operação Contenção",
    "tarifaco_eua_brasil": "Tarifaço dos EUA contra o Brasil",
    "rio_security_operation": "Operação de segurança no Rio de Janeiro",
}
RANKING_LABELS = {
    "ppr": "PPR",
    "hybrid_max": "Híbrido (máximo por artigo)",
    "rrf": "Fusão RRF",
    "lexical": "Lexical",
    "vector": "Vetorial",
    "cross_encoder": "Cross-encoder",
    "fused": "Híbrido + PPR",
    "mmr": "Diversidade MMR",
    "graph_rwr": "Caminhada com reinício (RWR)",
    "graph_hits": "HITS no grafo",
    "graph_salsa": "SALSA",
    "graph_path": "Caminhos no grafo",
    "graph_walk": "Caminhada no grafo",
    "graph_fusion": "Híbrido + HITS (RRF)",
    "graph_hits_cross_encoder": "HITS ponderado + cross-encoder",
    "ensemble_rrf": "Ensemble RRF",
}
SEED_LABELS = {
    "independent": "independente",
    "none": "sem semente",
    "hits": "HITS",
    "louvain": "Louvain",
    "ppr_top10": "PPR top 10%",
    "query_entities": "entidades da consulta",
}
METRIC_LABELS = {
    "precision": "Precisão",
    "recall": "Revocação",
    "f1": "F1",
    "mrr": "MRR",
    "map": "MAP",
    "ndcg": "NDCG",
}
RANKING_COLORS = {
    # Muted context baselines; focal method colors use an Okabe–Ito-inspired set.
    "hybrid_max": "#7A8793",
    "rrf": "#A0A8B0",
    "cross_encoder": "#58636D",
    "fused": "#0072B2",
    "graph_rwr": "#0072B2",
    "graph_salsa": "#D55E00",
    "graph_fusion": "#009E73",
    "graph_hits": "#009E73",
    "graph_hits_cross_encoder": "#CC79A7",
    "ensemble_rrf": "#E69F00",
    "graph_path": "#56B4E9",
    "graph_walk": "#56B4E9",
    "mmr": "#0072B2",
    "ppr": "#0072B2",
    "lexical": "#7A8793",
    "vector": "#A0A8B0",
}
RANKING_MARKERS = {
    "hybrid_max": "o", "rrf": "s", "cross_encoder": "^", "fused": "D",
    "graph_rwr": "v", "graph_salsa": "P", "graph_fusion": "X",
    "graph_hits": "X", "graph_hits_cross_encoder": "*", "ensemble_rrf": "h",
    "graph_path": "<", "graph_walk": ">", "mmr": "d", "ppr": "o",
    "lexical": "s", "vector": "^",
}
RANKING_LINESTYLES = {
    "hybrid_max": "-", "rrf": "--", "cross_encoder": ":", "fused": "-.",
    "graph_rwr": "-.", "graph_salsa": "--", "graph_fusion": "-", "graph_hits": "--",
    "graph_hits_cross_encoder": ":", "ensemble_rrf": "-.", "graph_path": "--",
    "graph_walk": ":", "mmr": "-.", "ppr": "-", "lexical": "--", "vector": ":",
}
F1_CUTOFFS = (1, 3, 5, 10, 20)
RANKING_CUTOFFS = (5, 10, 20)
PRIMARY_METRICS = ("f1@20", "mrr@20", "ndcg@20")
DIAGNOSTIC_KEYS = (
    "effective_seed_method", "query_entity_count", "query_entity_matched_count",
    "query_seed_fallback_reason", "query_seed_type", "graph_surviving_articles",
    "graph_entity_count", "graph_seed_count", "ppr_seed_count", "cross_encoder_reranked_count",
    "cross_encoder_missing_document_count", "candidate_cap_hit", "effective_quorum",
)


def _json_value(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _flatten_metrics(metrics, ranking_metrics, coverage):
    values = {}
    for item in metrics or []:
        if item.get("k") is None:
            continue
        k = int(item["k"])
        for metric in ("precision", "recall", "f1"):
            if item.get(metric) is not None:
                values[f"{metric}@{k}"] = item[metric]
    for key, value in (ranking_metrics or {}).items():
        if value is not None:
            values[key.lower()] = value
    coverage = coverage or {}
    if coverage.get("reference_pool_recall") is not None:
        values["reference_pool_recall"] = coverage["reference_pool_recall"]
    for item in coverage.get("oracle_metrics") or []:
        if item.get("k") is None:
            continue
        k = int(item["k"])
        for metric in ("precision", "recall", "f1"):
            if item.get(metric) is not None:
                values[f"oracle_{metric}@{k}"] = item[metric]
    return values


def _theme_of(evaluation_id):
    return str(evaluation_id or "unknown").split("__", 1)[0]


def _canonical_value(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def _event_to_row(event, run_id, relevant_counts=None, include_ranking_lists=False):
    result = event.get("result") or {}
    diagnostics = result.get("diagnostics") or {}
    evaluation_id = event.get("evaluation_id") or event.get("id") or "unknown"
    row = {
        "run_id": run_id,
        "seq": event.get("seq"),
        "evaluation_id": evaluation_id,
        "theme": _theme_of(evaluation_id),
        "query": event.get("query"),
        "formulation": event.get("query_formulation") or event.get("formulation") or "unspecified",
        "ranking": result.get("ranking"),
        "seed": result.get("seed_method") or "none",
        "preset": result.get("preset"),
        "quorum": result.get("quorum"),
        "result_unit": result.get("result_unit"),
        "top_k": result.get("top_k"),
        "limit": result.get("limit"),
        "retrieval_id": result.get("retrieval_id"),
        "computation_seconds": result.get("computation_seconds"),
        "computation_reused": result.get("computation_reused"),
        "retrieval_seconds": result.get("retrieval_seconds"),
        "group_elapsed_seconds": result.get("group_elapsed_seconds"),
    }
    reference_count = (relevant_counts or {}).get(evaluation_id)
    row["reference_count"] = reference_count
    row.update(_flatten_metrics(
        (result.get("metrics") or {}).get("metrics"),
        result.get("ranking_metrics"), result.get("coverage"),
    ))
    for key in DIAGNOSTIC_KEYS:
        row[key] = diagnostics.get(key)
    for source, target in (("cross_encoder_seconds", "cross_encoder_seconds"),
                           ("graph_seconds", "graph_seconds"), ("ppr_seconds", "ppr_seconds")):
        if diagnostics.get(source) is not None:
            row[target] = diagnostics[source]
    for name, value in (result.get("step_timings") or {}).items():
        if value is not None and isinstance(value, (int, float)):
            row[f"step_{name}"] = value
    for name, value in (result.get("retrieval_steps") or {}).items():
        if value is not None and isinstance(value, (int, float)):
            row[f"retrieval_{name}"] = value
    if include_ranking_lists:
        row["ranked_urls"] = result.get("ranked_urls") or [
            item.get("article") for item in result.get("ranked_results") or [] if item.get("article")
        ]
    return row


def _query_projection(include_ranking_lists=False, where_clause="run_id=:run_id", expanding=()):
    ranking_urls = ", payload->'result'->'ranked_urls' AS ranked_urls" if include_ranking_lists else ""
    diagnostic_fields = (*DIAGNOSTIC_KEYS, "cross_encoder_seconds", "graph_seconds", "ppr_seconds")
    diagnostic_projection = "jsonb_strip_nulls(jsonb_build_object(" + ", ".join(
        f"'{key}', payload->'result'->'diagnostics'->'{key}'" for key in diagnostic_fields
    ) + "))"
    query = text(f"""SELECT
        payload->>'seq' AS seq,
        payload->>'evaluation_id' AS evaluation_id,
        payload->>'query' AS query,
        payload->>'query_formulation' AS query_formulation,
        payload->'result'->>'ranking' AS ranking,
        payload->'result'->>'seed_method' AS seed,
        payload->'result'->>'preset' AS preset,
        payload->'result'->>'quorum' AS quorum,
        payload->'result'->>'result_unit' AS result_unit,
        payload->'result'->>'top_k' AS top_k,
        payload->'result'->>'limit' AS result_limit,
        payload->'result'->>'retrieval_id' AS retrieval_id,
        payload->'result'->>'computation_seconds' AS computation_seconds,
        payload->'result'->>'computation_reused' AS computation_reused,
        payload->'result'->>'retrieval_seconds' AS retrieval_seconds,
        payload->'result'->>'group_elapsed_seconds' AS group_elapsed_seconds,
        payload->'result'->'metrics'->'metrics' AS metrics,
        payload->'result'->'ranking_metrics' AS ranking_metrics,
        payload->'result'->'coverage' AS coverage,
        {diagnostic_projection} AS diagnostics,
        payload->'result'->'step_timings' AS step_timings,
        payload->'result'->'retrieval_steps' AS retrieval_steps
        {ranking_urls}
        FROM evaluation_run_results WHERE {where_clause} ORDER BY seq""")
    if expanding:
        query = query.bindparams(*expanding)
    return query


def _scope_predicate(rankings, seed_methods, filters=None):
    """Build a parameterized SQL predicate shared by selected-row and audit queries."""
    filters = filters or {}
    clauses = []
    params = {}
    expanding = []

    def include(name, expression, values):
        values = list(values or [])
        if not values:
            return
        clauses.append(f"{expression} IN :{name}")
        params[name] = values
        expanding.append(bindparam(name, expanding=True))

    include("selected_rankings", "payload->'result'->>'ranking'", rankings)
    params["graph_rankings"] = sorted(GRAPH_RANKINGS)
    expanding.append(bindparam("graph_rankings", expanding=True))
    if rankings:
        clauses.append("(NOT (payload->'result'->>'ranking' IN :graph_rankings) "
                       "OR payload->'result'->>'seed_method' IN :selected_seeds)")
        params["selected_seeds"] = list(seed_methods or [])
        expanding.append(bindparam("selected_seeds", expanding=True))
    include("selected_themes", "split_part(evaluation_id, '__', 1)", filters.get("themes"))
    include("selected_formulations", "payload->>'query_formulation'", filters.get("formulations"))
    include("selected_presets", "payload->'result'->>'preset'", filters.get("presets"))
    include("selected_evaluation_ids", "evaluation_id", filters.get("evaluation_ids"))
    quorums = filters.get("quorums") or []
    if quorums:
        clauses.append("NULLIF(payload->'result'->>'quorum', '')::DOUBLE PRECISION IN :selected_quorums")
        params["selected_quorums"] = [float(value) for value in quorums]
        expanding.append(bindparam("selected_quorums", expanding=True))
    return " AND ".join(clauses) if clauses else "TRUE", params, expanding


def _audit_projection(scope_clause):
    return text(f"""SELECT evaluation_id,
            MIN(payload->>'query_formulation') AS formulation,
            payload->'result'->>'preset' AS preset,
            payload->'result'->>'quorum' AS quorum,
            payload->'result'->>'result_unit' AS result_unit,
            payload->'result'->>'ranking' AS ranking,
            COALESCE(payload->'result'->>'seed_method', 'none') AS seed,
            COUNT(*) AS row_count,
            COUNT(*) FILTER (WHERE {scope_clause}) AS selected_count
        FROM evaluation_run_results
        WHERE run_id=:run_id
        GROUP BY evaluation_id, payload->'result'->>'preset', payload->'result'->>'quorum',
            payload->'result'->>'result_unit', payload->'result'->>'ranking',
            COALESCE(payload->'result'->>'seed_method', 'none')""")


def _group_count_is_selected(row, rankings, seed_methods, filters):
    filters = filters or {}
    ranking = row.get("ranking")
    if ranking not in rankings:
        return False
    if ranking in GRAPH_RANKINGS and row.get("seed") not in seed_methods:
        return False
    exact_filters = {
        "themes": _theme_of(row.get("evaluation_id")),
        "formulations": row.get("formulation"),
        "presets": row.get("preset"),
        "evaluation_ids": row.get("evaluation_id"),
    }
    for key, actual in exact_filters.items():
        values = filters.get(key) or []
        if values and str(actual) not in {str(value) for value in values}:
            return False
    quorums = filters.get("quorums") or []
    if quorums:
        try:
            if float(row.get("quorum")) not in {float(value) for value in quorums}:
                return False
        except (TypeError, ValueError):
            return False
    return True


def _db_raw_row(row):
    result = {
        "ranking": row["ranking"], "seed_method": row["seed"], "preset": row["preset"],
        "quorum": float(row["quorum"]) if row["quorum"] is not None else None,
        "result_unit": row["result_unit"], "top_k": int(row["top_k"]) if row["top_k"] else None,
        "limit": int(row["result_limit"]) if row["result_limit"] else None,
        "retrieval_id": row["retrieval_id"],
        "computation_seconds": float(row["computation_seconds"]) if row["computation_seconds"] else None,
        "computation_reused": (str(row["computation_reused"]).lower() == "true"
                               if row["computation_reused"] is not None else None),
        "retrieval_seconds": float(row["retrieval_seconds"]) if row["retrieval_seconds"] else None,
        "group_elapsed_seconds": float(row["group_elapsed_seconds"])
                                  if row["group_elapsed_seconds"] else None,
        "metrics": {"metrics": _json_value(row["metrics"]) or []},
        "ranking_metrics": _json_value(row["ranking_metrics"]) or {},
        "coverage": _json_value(row["coverage"]) or {},
        "diagnostics": _json_value(row["diagnostics"]) or {},
        "step_timings": _json_value(row["step_timings"]) or {},
        "retrieval_steps": _json_value(row["retrieval_steps"]) or {},
    }
    if "ranked_urls" in row:
        result["ranked_urls"] = _json_value(row["ranked_urls"]) or []
    return {
        "seq": int(row["seq"]) if row["seq"] is not None else None,
        "evaluation_id": row["evaluation_id"], "query": row["query"],
        "query_formulation": row["query_formulation"], "result": result,
    }


def load_run(engine, run_id, include_ranking_lists=False, progress_callback=None,
             rankings=None, seed_methods=None, baselines=None, filters=None):
    """Read selected result rows and compact full-run audit counts from one snapshot."""
    load_started = time.perf_counter()
    rankings = list(rankings or SUPPORTED_RANKINGS)
    seed_methods = list(seed_methods or SUPPORTED_SEED_METHODS)
    selected_rankings = sorted(set(rankings) | set(baselines or []))
    scope_clause, scope_params, expanding = _scope_predicate(
        selected_rankings, seed_methods, filters
    )
    scoped_where = f"run_id=:run_id AND ({scope_clause})"
    timings = {}
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with connection.begin():
            record = connection.execute(text("""SELECT run_id, created_at, updated_at,
                dataset, settings, state, dataset_snapshot
                FROM evaluation_runs WHERE run_id=:run_id"""), {"run_id": run_id}).mappings().one_or_none()
            if record is None:
                raise ValueError(f"Unknown dashboard run: {run_id}")
            settings = _json_value(record["settings"]) or {}
            state = _json_value(record["state"]) or {}
            snapshot = _json_value(record["dataset_snapshot"]) or {}
            evaluations = snapshot.get("evaluations") or []
            relevant_counts = {
                item.get("id"): len(set(item.get("relevant_urls") or [])) for item in evaluations
            }
            has_theme_metrics = connection.execute(
                text("SELECT to_regclass('evaluation_theme_difficulty_metrics')")
            ).scalar_one_or_none() is not None
            theme_difficulty = {}
            if has_theme_metrics:
                metric_rows = connection.execute(text("""SELECT DISTINCT ON (theme_id)
                        theme_id, revision, metric_version, main_entities, resolved_entities,
                        eligibility_snapshot_id, eligible_articles_count, matching_articles_count,
                        difficulty_score
                    FROM evaluation_theme_difficulty_metrics WHERE run_id=:run_id
                    ORDER BY theme_id, revision DESC"""), {"run_id": run_id}).mappings().all()
                theme_difficulty = {
                    row["theme_id"]: {
                        "revision": row["revision"], "metric_version": row["metric_version"],
                        "main_entities": _json_value(row["main_entities"]),
                        "resolved_entities": _json_value(row["resolved_entities"]),
                        "eligibility_snapshot_id": row["eligibility_snapshot_id"],
                        "eligible_articles_count": row["eligible_articles_count"],
                        "matching_articles_count": row["matching_articles_count"],
                        "difficulty_score": row["difficulty_score"],
                    }
                    for row in metric_rows
                }
            if progress_callback:
                progress_callback({"phase": "analyzing", "stage": "auditing",
                                   "stage_label": "Conferindo grupos e contando linhas selecionadas"})
            has_group_counts = connection.execute(
                text("SELECT to_regclass('evaluation_run_group_counts')")
            ).scalar_one_or_none() is not None
            audit_started = time.perf_counter()
            cached_counts_valid = False
            if has_group_counts:
                try:
                    expected_rows = int((state.get("progress") or {}).get("completed", 0))
                except (TypeError, ValueError):
                    expected_rows = None
                cached_row_total = connection.execute(text("""SELECT COALESCE(SUM(row_count), 0)
                    FROM evaluation_run_group_counts WHERE run_id=:run_id"""),
                    {"run_id": run_id}).scalar_one()
                cached_counts_valid = (expected_rows is not None
                                       and int(cached_row_total) == expected_rows)
                run_is_immutable = state.get("status") == "completed"
                if not cached_counts_valid and run_is_immutable:
                    # One-time backfill (or repair) for runs saved before the
                    # compact per-group counts were maintained transactionally.
                    # Only backfill completed runs: active/paused runs may be
                    # resumed while this figure job is reading the snapshot.
                    connection.execute(text("DELETE FROM evaluation_run_group_counts WHERE run_id=:run_id"),
                                       {"run_id": run_id})
                    connection.execute(text("""INSERT INTO evaluation_run_group_counts
                        (run_id, evaluation_id, preset, quorum, result_unit, ranking, seed,
                         formulation, row_count)
                        SELECT run_id, evaluation_id,
                            COALESCE(payload->'result'->>'preset', ''),
                            COALESCE(payload->'result'->>'quorum', ''),
                            COALESCE(payload->'result'->>'result_unit', ''),
                            COALESCE(payload->'result'->>'ranking', ''),
                            COALESCE(payload->'result'->>'seed_method', 'none'),
                            COALESCE(MIN(payload->>'query_formulation'), 'unspecified'), COUNT(*)
                        FROM evaluation_run_results WHERE run_id=:run_id
                        GROUP BY run_id, evaluation_id, payload->'result'->>'preset',
                            payload->'result'->>'quorum', payload->'result'->>'result_unit',
                            payload->'result'->>'ranking',
                            COALESCE(payload->'result'->>'seed_method', 'none')"""),
                        {"run_id": run_id})
                    cached_counts_valid = expected_rows is not None

            if has_group_counts and cached_counts_valid:
                audit_rows = [dict(row) for row in connection.execute(text("""SELECT evaluation_id, formulation,
                        preset, NULLIF(quorum, '') AS quorum, result_unit, ranking, seed,
                        row_count
                    FROM evaluation_run_group_counts WHERE run_id=:run_id"""),
                    {"run_id": run_id}).mappings().all()]
                for row in audit_rows:
                    row["selected_count"] = row["row_count"] if _group_count_is_selected(
                        row, selected_rankings, seed_methods, filters
                    ) else 0
            else:
                audit_query = _audit_projection(scope_clause)
                if expanding:
                    audit_query = audit_query.bindparams(*expanding)
                audit_rows = connection.execute(
                    audit_query, {"run_id": run_id, **scope_params}
                ).mappings().all()
            timings["audit_query_seconds"] = time.perf_counter() - audit_started
            audit_counts = pd.DataFrame(audit_rows)
            if not audit_counts.empty:
                audit_counts["quorum"] = pd.to_numeric(audit_counts["quorum"], errors="coerce")
                audit_counts["row_count"] = pd.to_numeric(audit_counts["row_count"], errors="coerce").fillna(0)
                audit_counts["selected_count"] = pd.to_numeric(
                    audit_counts["selected_count"], errors="coerce").fillna(0)
            total_rows = int(pd.to_numeric(audit_counts.get("selected_count"), errors="coerce")
                             .fillna(0).sum()) if not audit_counts.empty else 0
            full_run_rows = int(pd.to_numeric(audit_counts.get("row_count"), errors="coerce")
                                .fillna(0).sum()) if not audit_counts.empty else 0
            if progress_callback:
                progress_callback({"phase": "loading", "loaded_rows": 0, "total_rows": total_rows,
                                   "stage_label": None})
            selected_query = _query_projection(
                include_ranking_lists, where_clause=scoped_where, expanding=expanding
            )
            results_started = time.perf_counter()
            cursor = connection.execution_options(stream_results=True).execute(
                selected_query, {"run_id": run_id, **scope_params}
            ).mappings()
            rows = []
            while batch := cursor.fetchmany(250):
                rows.extend(_event_to_row(_db_raw_row(row), run_id, relevant_counts,
                                          include_ranking_lists=include_ranking_lists) for row in batch)
                if progress_callback:
                    progress_callback({"phase": "loading", "loaded_rows": len(rows),
                                       "total_rows": total_rows})
            timings["selected_rows_seconds"] = time.perf_counter() - results_started
            report_keys = connection.execute(text("""SELECT payload->>'evaluation_version' AS evaluation_version
                FROM evaluation_run_artifacts WHERE run_id=:run_id
                  AND artifact_key LIKE '%evaluation_report%' AND payload ? 'evaluation_version'
                LIMIT 5"""), {"run_id": run_id}).scalars().all()
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["quorum"] = pd.to_numeric(frame["quorum"], errors="coerce")
        for column in ("top_k", "limit", "reference_count", "computation_seconds", "retrieval_seconds",
                       "group_elapsed_seconds", "reference_pool_recall", "query_entity_count",
                       "query_entity_matched_count", "f1@20", "mrr@20", "ndcg@20"):
            if column in frame:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
        for column in ("matching_articles_count", "eligible_articles_count", "difficulty_score"):
            frame[column] = frame["theme"].map({
                theme: values.get(column) for theme, values in theme_difficulty.items()
            })
        frame["main_entities"] = frame["theme"].map({
            theme: ", ".join(values.get("main_entities") or [])
            for theme, values in theme_difficulty.items()
        })
        frame["eligibility_snapshot_id"] = frame["theme"].map({
            theme: values.get("eligibility_snapshot_id")
            for theme, values in theme_difficulty.items()
        })
    timings["load_run_seconds"] = time.perf_counter() - load_started
    snapshot_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False,
                                               separators=(",", ":")).encode()).hexdigest()
    metadata = {
        "run_id": run_id,
        "created_at": record["created_at"].isoformat() if record["created_at"] else None,
        "updated_at": record["updated_at"].isoformat() if record["updated_at"] else None,
        "dataset": record["dataset"], "settings": settings, "state": state,
        "theme_difficulty_metrics": theme_difficulty,
        "dataset_snapshot_sha256": snapshot_hash,
        "dataset_snapshot_version": state.get("dataset_snapshot_version"),
        "evaluation_versions": sorted({str(value) for value in report_keys if value is not None}),
        "expected_evaluation_groups": len(evaluations),
        "observed_result_rows": full_run_rows,
        "selected_result_rows": len(frame),
        "timings_seconds": timings,
    }
    return metadata, frame, audit_counts


def _expected_configurations(settings):
    rankings = settings.get("rankings")
    seeds = settings.get("seed_methods")
    if not isinstance(rankings, list) or not isinstance(seeds, list):
        return None
    return {(ranking, seed) for ranking in rankings for seed in seeds}


def audit_groups(frame, settings):
    if frame.empty:
        return pd.DataFrame(columns=["evaluation_id", "preset", "quorum", "rows", "expected",
                                     "complete", "missing", "duplicates", "unexpected"])
    group_cols = ["evaluation_id", "preset", "quorum", "result_unit"]
    grouped = frame.groupby([*group_cols, "ranking", "seed"], dropna=False, sort=False).agg(
        row_count=("ranking", "size"),
        formulation=("formulation", "first"),
        theme=("theme", "first"),
    ).reset_index()
    return audit_groups_from_counts(grouped, settings)


def audit_groups_from_counts(counts_frame, settings):
    """Audit full-run configuration completeness from compact SQL aggregates."""
    output_columns = ["evaluation_id", "theme", "formulation", "preset", "quorum", "result_unit",
                      "rows", "expected", "expected_inferred", "complete", "missing",
                      "duplicates", "unexpected"]
    if counts_frame.empty:
        return pd.DataFrame(columns=output_columns)
    expected = _expected_configurations(settings)
    inferred_expected = False
    if expected is None:
        group_sizes = counts_frame.groupby(["evaluation_id", "preset", "quorum", "result_unit"],
                                           dropna=False)["row_count"].sum()
        if len(group_sizes):
            largest = tuple(_canonical_value(value) for value in group_sizes.idxmax())
            mask = np.ones(len(counts_frame), dtype=bool)
            for column, target in zip(["evaluation_id", "preset", "quorum", "result_unit"], largest):
                values = counts_frame[column]
                mask &= values.isna().to_numpy() if target is None else values.eq(target).fillna(False).to_numpy()
            sample = counts_frame.loc[mask]
            expected = set(zip(sample["ranking"], sample["seed"].replace({None: "none"})))
            inferred_expected = True
    records = []
    group_cols = ["evaluation_id", "preset", "quorum", "result_unit"]
    for keys, group in counts_frame.groupby(group_cols, dropna=False, sort=False):
        evaluation_id, preset, quorum, result_unit = keys
        actual_rows = list(zip(group["ranking"], group["seed"].replace({None: "none"})))
        counts = dict(zip(actual_rows, group["row_count"].astype(int)))
        actual = set(actual_rows)
        missing = sorted(expected - actual) if expected is not None else []
        unexpected = sorted(actual - expected) if expected is not None else []
        duplicates = sum(count - 1 for count in counts.values() if count > 1)
        total_rows = int(group["row_count"].sum())
        complete = (expected is not None and not missing and not unexpected and duplicates == 0
                    and total_rows == len(expected))
        records.append({"evaluation_id": evaluation_id, "theme": _theme_of(evaluation_id),
                        "formulation": group["formulation"].iloc[0] if "formulation" in group else None,
                        "preset": preset,
                        "quorum": quorum, "result_unit": result_unit, "rows": total_rows,
                        "expected": len(expected) if expected is not None else None,
                        "expected_inferred": inferred_expected,
                        "complete": bool(complete), "missing": json.dumps(missing),
                        "duplicates": duplicates, "unexpected": json.dumps(unexpected)})
    return pd.DataFrame(records)


def prepare_analysis_frame(frame, audit, include_partial=False):
    if frame.empty:
        return frame.copy()
    group_keys = ["evaluation_id", "preset", "quorum", "result_unit"]
    complete_keys = {tuple(_canonical_value(value) for value in row)
                     for row in audit.loc[audit["complete"], group_keys].itertuples(index=False, name=None)}
    row_keys = [tuple(_canonical_value(value) for value in row)
                for row in frame[group_keys].itertuples(index=False, name=None)]
    complete_mask = pd.Series([key in complete_keys for key in row_keys], index=frame.index)
    if include_partial:
        selected = frame.copy()
        selected["partial_group"] = ~complete_mask
    else:
        selected = frame[complete_mask].copy()
        selected["partial_group"] = False
    for column in ("query_entity_count", "query_entity_matched_count", "computation_seconds",
                   "retrieval_seconds", *PRIMARY_METRICS):
        if column in selected:
            selected[column] = pd.to_numeric(selected[column], errors="coerce")
    selected["seed_label"] = np.where(selected["ranking"].isin(SEED_INDEPENDENT), "independent",
                                       selected["seed"].fillna("none"))
    configuration = np.where(selected["seed_label"].eq("independent"), selected["ranking"],
                              selected["ranking"] + " · semente=" + selected["seed_label"])
    if selected["preset"].nunique(dropna=True) > 1:
        configuration = configuration + " · preset=" + selected["preset"].fillna("?").astype(str)
    if selected["quorum"].nunique(dropna=True) > 1:
        configuration = configuration + " · quorum=" + selected["quorum"].map(
            lambda value: f"{value:g}" if pd.notna(value) else "?"
        )
    if selected["result_unit"].nunique(dropna=True) > 1:
        configuration = configuration + " · unidade=" + selected["result_unit"].fillna("?").astype(str)
    selected["configuration"] = configuration
    selected["formulation_label"] = selected["formulation"].map(FORMULATION_LABELS).fillna(selected["formulation"])
    selected["theme_label"] = selected["theme"].map(THEME_LABELS).fillna(selected["theme"])
    # Seed-independent rankings are persisted once per configured seed. Keep one
    # query observation, but leave the original rows in normalized_results.csv.
    selected = selected.sort_values(["seq"], na_position="last")
    selected = selected.drop_duplicates(
        ["evaluation_id", "preset", "quorum", "result_unit", "ranking", "seed_label"], keep="first"
    )
    return selected.reset_index(drop=True)


def filter_result_scope(frame, filters=None):
    """Apply explicit dimension filters without changing the source frame."""
    filters = filters or {}
    selected = frame.copy()
    exact_columns = {
        "themes": "theme",
        "formulations": "formulation",
        "presets": "preset",
        "evaluation_ids": "evaluation_id",
    }
    for key, column in exact_columns.items():
        values = filters.get(key) or []
        if values and column in selected:
            selected = selected[selected[column].astype(str).isin({str(value) for value in values})]
    quorums = filters.get("quorums") or []
    if quorums and "quorum" in selected:
        targets = {float(value) for value in quorums}
        selected = selected[pd.to_numeric(selected["quorum"], errors="coerce").isin(targets)]
    return selected.copy()


def filter_methods(frame, rankings=None, seed_methods=None):
    rankings = set(rankings or SUPPORTED_RANKINGS)
    seed_methods = set(seed_methods or SUPPORTED_SEED_METHODS)
    if frame.empty:
        return frame.copy()
    selected = frame[frame["ranking"].isin(rankings)].copy()
    graph_mask = selected["ranking"].isin(GRAPH_RANKINGS)
    return selected[~graph_mask | selected["seed_label"].isin(seed_methods)].copy()


def _theme_macro(frame, metric):
    valid = frame[["theme", "evaluation_id", metric]].dropna()
    if valid.empty:
        return pd.DataFrame(columns=["theme", "value"])
    by_query = valid.groupby(["theme", "evaluation_id"], as_index=False)[metric].mean()
    return by_query.groupby("theme", as_index=False)[metric].mean().rename(columns={metric: "value"})


def bootstrap_theme_mean(theme_values, samples=1000, seed=42):
    values = np.asarray(theme_values, dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        return np.nan, np.nan, np.nan
    estimate = float(values.mean())
    if len(values) == 1:
        return estimate, estimate, estimate
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(values), size=(samples, len(values)))
    means = values[indices].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return estimate, float(low), float(high)


def summarize_configurations(frame):
    records = []
    if frame.empty:
        return pd.DataFrame()
    metrics = [metric for metric in PRIMARY_METRICS if metric in frame]
    for config, group in frame.groupby("configuration", sort=False):
        record = {"configuration": config, "ranking": group["ranking"].iloc[0],
                  "seed": group["seed_label"].iloc[0], "queries": group["evaluation_id"].nunique(),
                  "themes": group["theme"].nunique()}
        for metric in metrics:
            theme_values = _theme_macro(group, metric)["value"].to_numpy()
            estimate, low, high = bootstrap_theme_mean(theme_values)
            record[metric] = estimate
            record[f"{metric}_ci_low"] = low
            record[f"{metric}_ci_high"] = high
        records.append(record)
    return pd.DataFrame(records)


def _format_metric(metric):
    value = str(metric).lower()
    if "@" in value:
        name, cutoff = value.rsplit("@", 1)
        return f"{METRIC_LABELS.get(name, name.upper())}@{cutoff}"
    return METRIC_LABELS.get(value, value.upper())


HEADLINE_BASELINES = {"hybrid_max", "rrf", "cross_encoder", "lexical", "vector"}


def _headline_configurations(frame, top_n=10):
    """Predeclared readable subset: top F1 configurations plus retrieval baselines."""
    if frame.empty:
        return []
    summary = summarize_configurations(frame)
    if summary.empty:
        return []
    top = summary.sort_values("f1@20", ascending=False)["configuration"].head(top_n).tolist()
    baselines = summary.loc[summary["ranking"].isin(HEADLINE_BASELINES), "configuration"].tolist()
    selected = set(top) | set(baselines)
    return [name for name in summary["configuration"] if name in selected]


def _short_configuration(value):
    value = str(value)
    for raw, label in sorted(RANKING_LABELS.items(), key=lambda item: len(item[0]), reverse=True):
        if value == raw or value.startswith(raw + " ·"):
            value = label + value[len(raw):]
            break
    value = value.replace(" · semente=", " · ")
    for raw, label in SEED_LABELS.items():
        value = value.replace(raw, label)
    value = value.replace("preset=rapido", "preset=rápido")
    value = value.replace("preset=balanceado", "preset=balanceado")
    value = value.replace("preset=profundo", "preset=profundo")
    return value


def _ranking_color(ranking):
    return RANKING_COLORS.get(str(ranking), "#667085")


def _ranking_marker(ranking):
    return RANKING_MARKERS.get(str(ranking), "o")


def _ranking_linestyle(ranking):
    return RANKING_LINESTYLES.get(str(ranking), "-")


def _heatmap_annotations_readable(shape):
    """Avoid cell text where a multi-panel heatmap would make it collide."""
    rows, columns = shape
    return rows * columns <= 60 and columns <= 6


def _uncertainty_band_alpha(series_count):
    """Reduce overlapping interval fills as more configurations share an axis."""
    return max(.02, min(.08, .16 / max(1, int(series_count))))


def _sparse_plot_height(row_count):
    """Use less vertical space for point/interval plots with few rows."""
    return max(3.5, 1.4 + .28 * int(row_count))


def _runtime_frontier_label_configs(frontier, max_labels=4):
    """Select evenly spaced Pareto points for labels; the CSV retains every point."""
    if frontier.empty or max_labels <= 0:
        return set()
    ordered = frontier.sort_values("seconds")
    if len(ordered) <= max_labels:
        return set(ordered["configuration"])
    positions = np.linspace(0, len(ordered) - 1, num=max_labels).round().astype(int)
    return set(ordered.iloc[positions]["configuration"])


def _short_formulation_label(label):
    return FORMULATION_TICK_LABELS.get(str(label), str(label))


def _ceil_axis_max(values, step=0.05, minimum=0.05, maximum=1.0):
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if not len(finite):
        return minimum
    value = min(maximum, max(minimum, math.ceil(float(finite.max()) / step) * step))
    return round(value, 10)


def _natural_figure_sort_key(path):
    return tuple(int(part) if part.isdigit() else part.casefold()
                 for part in re.split(r"(\d+)", Path(path).name))


def _save(fig, directory, stem, formats):
    paths = []
    if PARTIAL_INCLUSIVE:
        fig.text(.012, .992, "PROVISÓRIO — INCLUI GRUPOS PARCIAIS", ha="left", va="top",
                 color="#9f2d20", fontsize=9, fontweight="bold",
                 bbox={"facecolor": "white", "edgecolor": "#9f2d20", "alpha": .9, "pad": 3})
    for fmt in formats:
        path = directory / f"{stem}.{fmt}"
        fig.savefig(path, format=fmt, dpi=300, bbox_inches="tight", facecolor="white")
        paths.append(path.name)
    plt.close(fig)
    return paths


def _plot_composition(frame, directory, formats):
    if frame.empty:
        return []
    query = frame.drop_duplicates("evaluation_id")
    counts = pd.crosstab(query["theme_label"], query["formulation_label"])
    counts = counts.loc[counts.sum(axis=1).sort_values(ascending=False).index]
    constant_counts = counts.size > 0 and counts.to_numpy().min() == counts.to_numpy().max()
    reference = query.dropna(subset=["reference_count"])
    constant_reference = (reference.empty or reference["reference_count"].nunique() == 1)
    compact_summary = constant_counts and constant_reference
    figure_size = (11, 3.8) if compact_summary else (17, max(5, 0.3 * len(counts)))
    width_ratios = [1.25, 1] if compact_summary else [1.6, 1]
    fig, axes = plt.subplots(1, 2, figsize=figure_size,
                             gridspec_kw={"width_ratios": width_ratios})
    if constant_counts:
        # A uniform all-ones heatmap encodes no variation; state the design directly.
        axes[0].axis("off")
        axes[0].set_title("Consultas avaliadas por tema e formulação")
        axes[0].text(.5, .63, f"{len(counts)} temas × {len(counts.columns)} formulações",
                     transform=axes[0].transAxes, ha="center", va="center", fontsize=15,
                     fontweight="bold")
        axes[0].text(.5, .48, f"{int(counts.to_numpy().min())} consulta por combinação",
                     transform=axes[0].transAxes, ha="center", va="center", fontsize=12)
        axes[0].text(.5, .35, f"{int(counts.to_numpy().sum())} consultas no total",
                     transform=axes[0].transAxes, ha="center", va="center", fontsize=11)
    else:
        sns.heatmap(counts, cmap="Blues", annot=True, fmt="g", linewidths=.3,
                    cbar=True, cbar_kws={"label": "Número de consultas"}, ax=axes[0])
        axes[0].set(title="Consultas avaliadas por tema e formulação", xlabel="Formulação", ylabel="Tema")
        axes[0].set_xticks(np.arange(len(counts.columns)) + .5)
        axes[0].set_xticklabels([_short_formulation_label(label.get_text())
                                 for label in axes[0].get_xticklabels()], rotation=45, ha="right", fontsize=8)
    if reference.empty:
        axes[1].text(.5, .5, "Tamanho do conjunto de referência indisponível", ha="center", va="center")
    elif reference["reference_count"].nunique() == 1:
        count = int(reference["reference_count"].iloc[0])
        axes[1].axis("off")
        axes[1].text(.5, .58, f"{len(reference)} consultas", ha="center", va="center", fontsize=16,
                     fontweight="bold")
        axes[1].text(.5, .43, f"{count} artigos de referência cada", ha="center", va="center", fontsize=12)
        axes[1].set_title("Tamanho do conjunto de referência")
    else:
        sns.histplot(reference["reference_count"], discrete=True, color="#4c78a8", ax=axes[1])
        axes[1].set(xlabel="Artigos relevantes de referência por consulta", ylabel="Consultas",
                    title="Tamanho do conjunto de referência")
    fig.suptitle(f"Composição do conjunto de avaliação · {query['theme'].nunique()} temas / "
                 f"{query['evaluation_id'].nunique()} consultas", y=1.02)
    fig.tight_layout()
    return _save(fig, directory, "fig01_evaluation_composition", formats)


def _query_level(frame):
    cols = ["evaluation_id", "theme", "theme_label", "formulation", "formulation_label", "reference_count",
            "preset", "quorum", "result_unit", "retrieval_id", "reference_pool_recall"]
    valid_cols = [column for column in cols if column in frame]
    return frame.sort_values("seq", na_position="last").drop_duplicates("evaluation_id")[valid_cols]


def _design_label(frame):
    """Return run-specific query/theme counts without counting configuration repeats."""
    if frame.empty or "evaluation_id" not in frame:
        return "0 temas / 0 consultas"
    query = frame.drop_duplicates("evaluation_id")
    theme_count = query["theme"].nunique() if "theme" in query else 0
    return f"{theme_count} temas / {query['evaluation_id'].nunique()} consultas"


def _bootstrap_label(theme_counts):
    values = pd.to_numeric(pd.Series(theme_counts), errors="coerce").dropna().astype(int).unique()
    if not len(values):
        return "IC bootstrap sobre temas"
    low, high = int(values.min()), int(values.max())
    if low == high:
        return f"IC bootstrap sobre {low} temas"
    return f"IC bootstrap sobre temas (n={low}–{high})"


def _formulation_sample_label(frame):
    query = _query_level(frame)
    column = "formulation_label" if "formulation_label" in query else "formulation"
    if query.empty or column not in query:
        return "n por formulação indisponível"
    counts = query.groupby(column)["evaluation_id"].nunique()
    if counts.empty:
        return "n por formulação indisponível"
    low, high = int(counts.min()), int(counts.max())
    if low == high:
        return f"n={low} consultas por formulação"
    return f"n varia de {low} a {high} consultas por formulação"


def _theme_metric_interval(frame, column):
    by_theme = frame.groupby("theme")[column].mean().dropna()
    if by_theme.empty:
        return np.nan, np.nan, np.nan
    return bootstrap_theme_mean(by_theme.to_numpy())


def _plot_retrieval_ceiling(frame, directory, formats):
    query = _query_level(frame)
    if query.empty or not any(c in query for c in ("reference_pool_recall", "oracle_f1@20")):
        return []
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.8))
    metrics = (
        ("reference_pool_recall", "Cobertura da recuperação", "#0072B2"),
        ("oracle_f1@20", "Teto no conjunto recuperado", "#009E73"),
    )
    generated = []
    pool = frame.drop_duplicates(["evaluation_id", "preset", "quorum"])
    query_pool = _query_level(pool)
    for ax, (column, title, color) in zip(axes, metrics):
        if column not in pool or pool[column].notna().sum() == 0:
            ax.set_visible(False)
            continue
        sns.boxplot(data=pool, x="formulation_label", y=column, color="#e8edf2", width=.58,
                    showfliers=False, ax=ax)
        sns.stripplot(data=pool, x="formulation_label", y=column, color=color, alpha=.55,
                      size=3.2, jitter=.16, ax=ax)
        counts = query_pool.groupby("formulation_label")["evaluation_id"].nunique()
        for position, label in enumerate([tick.get_text() for tick in ax.get_xticklabels()]):
            ax.text(position, .02, f"n={counts.get(label, 0)}", ha="center", va="bottom",
                    transform=ax.get_xaxis_transform(), fontsize=8)
        ylabel = ("Revocação das referências no conjunto recuperado" if column == "reference_pool_recall"
                  else "F1@20 do oráculo")
        ax.set(xlabel="Formulação", ylabel=ylabel, ylim=(-.03, 1.03),
               title=f"{title} · distribuição por formulação")
    for ax in axes:
        if ax.get_visible():
            ticks = ax.get_xticks()
            labels = [_short_formulation_label(label.get_text()) for label in ax.get_xticklabels()]
            ax.set_xticks(ticks)
            ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=8)
    fig.suptitle(f"Cobertura e teto dentro do conjunto · descritivo · {_formulation_sample_label(frame)} · "
                 f"{_design_label(query)}", y=1.03)
    fig.tight_layout()
    generated.extend(_save(fig, directory, "fig02_retrieval_coverage_and_ceiling", formats))

    # Distribution summaries do not identify the theme behind each value. This
    # companion view preserves that mapping using one theme/formulation mean.
    heatmap_columns = [column for column, _, _ in metrics
                       if column in query and query[column].notna().any()]
    if heatmap_columns:
        heatmap_frame = query.dropna(subset=heatmap_columns, how="all")
        matrices = [heatmap_frame.pivot_table(index="theme_label", columns="formulation_label",
                                              values=column, aggfunc="mean")
                    for column in heatmap_columns]
        theme_order = (heatmap_frame.groupby("theme_label")[heatmap_columns].mean().mean(axis=1)
                       .sort_values(ascending=False).index)
        fig, heat_axes = plt.subplots(1, len(heatmap_columns),
                                      figsize=(max(10, 1.2 * len(query["formulation_label"].unique())),
                                               max(6, .32 * len(theme_order))), squeeze=False)
        heat_axes = heat_axes.ravel()
        title_by_column = {column: title for column, title, _ in metrics}
        for ax, column, matrix in zip(heat_axes, heatmap_columns, matrices):
            matrix = matrix.reindex(theme_order)
            sns.heatmap(matrix, vmin=0, vmax=1, cmap="viridis", mask=matrix.isna(), ax=ax,
                        cbar_kws={"label": "Revocação · escala 0–1" if column == "reference_pool_recall"
                                  else "F1@20 · escala 0–1"})
            ax.set(title=f"{title_by_column[column]} · média por tema/formulação",
                   xlabel="Formulação", ylabel="Tema")
            ax.set_xticklabels([_short_formulation_label(label.get_text())
                                for label in ax.get_xticklabels()], rotation=40, ha="right", fontsize=8)
            ax.tick_params(axis="y", labelsize=7)
        fig.suptitle(f"Valores por tema e formulação · {_design_label(query)}", y=1.02)
        fig.tight_layout()
        generated.extend(_save(fig, directory, "fig02_theme_formulation_values", formats))
    return generated


def _plot_ranking_leaderboard(frame, directory, formats):
    summary = summarize_configurations(frame)
    if summary.empty:
        return []
    summary.to_csv(directory / "configuration_summary.csv", index=False)
    headline = _headline_configurations(frame)

    def draw(selected, stem, full_scale):
        view = summary[summary["configuration"].isin(selected)].sort_values("f1@20").reset_index(drop=True)
        y = np.arange(len(view))
        labels = [_short_configuration(value) for value in view["configuration"]]
        fig, axes = plt.subplots(1, 3, figsize=(17, max(6.5, .34 * len(view))), sharey=True)
        for ax, metric in zip(axes, PRIMARY_METRICS):
            x = view[metric].to_numpy()
            low = x - view[f"{metric}_ci_low"].to_numpy()
            high = view[f"{metric}_ci_high"].to_numpy() - x
            for point, (row_index, row) in enumerate(view.iterrows()):
                color = _ranking_color(row["ranking"])
                ax.errorbar(x[point], y[point], xerr=[[low[point]], [high[point]]],
                            fmt=_ranking_marker(row["ranking"]), markersize=4,
                            color=color, ecolor=color, alpha=.85, capsize=2, linewidth=1)
            ax.axvline(float(np.nanmean(x)), color="#bf4b42", linestyle="--", linewidth=1, alpha=.75)
            axis_max = 1.0 if full_scale else _ceil_axis_max(view[f"{metric}_ci_high"], step=.05)
            scale_note = "escala completa" if full_scale else f"zoom 0–{axis_max:g}"
            ax.set(title=f"{_format_metric(metric)} · {scale_note}",
                   xlabel=f"Média macro por tema · {_bootstrap_label(view['themes'])}", xlim=(0, axis_max))
            ax.grid(axis="x", alpha=.25)
        axes[0].set_yticks(y, labels)
        axes[0].set_ylabel("Ranking · semente")
        title = "Lista completa (apêndice)" if full_scale else "Configurações em destaque"
        fig.suptitle(f"Qualidade dos rankings · {title} · {_design_label(frame)} · "
                     "linha tracejada: média das configurações exibidas", y=1.01)
        fig.tight_layout()
        return _save(fig, directory, stem, formats)

    generated = draw(headline, "fig03_ranking_quality_leaderboard", full_scale=False)
    if len(headline) < len(summary):
        generated.extend(draw(summary["configuration"].tolist(),
                              "fig03_ranking_quality_full_appendix", full_scale=True))
    return generated


def _plot_formulation_heatmaps(frame, directory, formats):
    if frame.empty:
        return []
    formulations = [name for name in FORMULATION_LABELS.values()
                    if name in set(frame["formulation_label"].dropna())]
    all_configs = frame["configuration"].drop_duplicates().tolist()
    headline = _headline_configurations(frame)
    metric_maxima = {}
    for metric in PRIMARY_METRICS:
        if metric not in frame:
            continue
        theme_means = frame.groupby(["configuration", "formulation_label", "theme"])[metric].mean()
        formulation_means = theme_means.groupby(level=["configuration", "formulation_label"]).mean()
        metric_maxima[metric] = _ceil_axis_max(formulation_means, step=.05)

    def draw(configs, stem, appendix=False):
        rows = len(configs)
        fig, axes = plt.subplots(1, 3, figsize=(max(14, len(formulations) * 1.45), max(5.5, rows * .34)),
                                 sharey=True)
        for ax, metric in zip(axes, PRIMARY_METRICS):
            if metric not in frame or frame[metric].notna().sum() == 0:
                ax.set_visible(False)
                continue
            theme_means = frame.groupby(["configuration", "formulation_label", "theme"], as_index=False)[metric].mean()
            formulation_means = theme_means.groupby(["configuration", "formulation_label"], as_index=False)[metric].mean()
            pivot = formulation_means.pivot(index="configuration", columns="formulation_label", values=metric)
            pivot = pivot.reindex(index=configs, columns=formulations)
            annotate = _heatmap_annotations_readable(pivot.shape)
            vmax = metric_maxima.get(metric, 1.0)
            sns.heatmap(pivot, vmin=0, vmax=vmax, cmap="viridis", mask=pivot.isna(),
                        annot=annotate, fmt=".2f", ax=ax,
                        cbar_kws={"label": f"Média macro por tema · escala 0–{vmax:g}"})
            ax.set(title=_format_metric(metric), xlabel="Formulação", ylabel="Ranking · semente" if ax is axes[0] else "")
            ax.set_xticks(np.arange(len(formulations)) + .5)
            ax.set_xticklabels([_short_formulation_label(label.get_text())
                                for label in ax.get_xticklabels()], rotation=45, ha="right", fontsize=8)
        if axes[0].get_visible():
            axes[0].set_yticklabels([_short_configuration(label.get_text())
                                     for label in axes[0].get_yticklabels()], rotation=0, fontsize=8)
        for ax in axes[1:]:
            ax.tick_params(axis="y", labelleft=False)
        label = "lista completa · apêndice" if appendix else "configurações em destaque"
        fig.suptitle(f"Desempenho por formulação · {label} · {_design_label(frame)} · "
                     "escalas por métrica explícitas nos colorbars", y=1.01)
        fig.tight_layout()
        return _save(fig, directory, stem, formats)

    generated = draw(headline, "fig04_method_by_formulation")
    if len(headline) < len(all_configs):
        generated.extend(draw(all_configs, "fig04_method_by_formulation_full_appendix", appendix=True))
    return generated


def _plot_paired_deltas(frame, directory, formats, baselines, progress_callback=None):
    if frame.empty:
        return []
    index = ["evaluation_id", "preset", "quorum", "result_unit"]
    if "retrieval_id" in frame and frame["retrieval_id"].notna().any():
        index.append("retrieval_id")
    generated = []
    csv_records = []
    baseline_total = len(baselines)
    for baseline_index, baseline in enumerate(baselines, start=1):
        if progress_callback:
            progress_callback({"phase": "plotting", "subtask_completed": baseline_index - 1,
                               "subtask_total": baseline_total,
                               "current_subtask": baseline})
        baseline_rows = frame[frame["ranking"] == baseline]
        if baseline_rows.empty:
            if progress_callback:
                progress_callback({"phase": "plotting", "subtask_completed": baseline_index,
                                   "subtask_total": baseline_total,
                                   "current_subtask": baselines[baseline_index]
                                   if baseline_index < baseline_total else None})
            continue
        outputs = {}
        for metric in PRIMARY_METRICS:
            if metric not in frame:
                continue
            base = baseline_rows.groupby(index, as_index=False)[metric].mean()
            for config in frame["configuration"].drop_duplicates():
                target_ranking = frame.loc[frame["configuration"] == config, "ranking"].iloc[0]
                if target_ranking == baseline:
                    continue
                target = frame[frame["configuration"] == config].groupby(index, as_index=False)[metric].mean()
                paired = target.merge(base, on=index, how="inner", suffixes=("_target", "_baseline"))
                if paired.empty:
                    continue
                paired["delta"] = paired[f"{metric}_target"] - paired[f"{metric}_baseline"]
                query_delta = paired.dropna(subset=["delta"])
                if query_delta.empty:
                    continue
                query_delta["theme"] = query_delta["evaluation_id"].map(_theme_of)
                theme_values = query_delta.groupby("theme")["delta"].mean().to_numpy()
                estimate, low, high = bootstrap_theme_mean(theme_values)
                ranking = frame.loc[frame["configuration"] == config, "ranking"].iloc[0]
                record = {"baseline": baseline, "configuration": config, "ranking": ranking,
                          "metric": metric,
                          "delta": estimate, "ci_low": low, "ci_high": high,
                          "queries": query_delta["evaluation_id"].nunique(),
                          "themes": len(theme_values),
                          "wins": int((query_delta["delta"] > 1e-12).sum()),
                          "losses": int((query_delta["delta"] < -1e-12).sum()),
                          "ties": int((query_delta["delta"].abs() <= 1e-12).sum())}
                outputs.setdefault(metric, []).append(record)
                csv_records.append(record)
        if not outputs:
            if progress_callback:
                progress_callback({"phase": "plotting", "subtask_completed": baseline_index,
                                   "subtask_total": baseline_total,
                                   "current_subtask": baselines[baseline_index]
                                   if baseline_index < baseline_total else None})
            continue
        labels_all = sorted({row["configuration"] for values in outputs.values() for row in values})
        headline = set(_headline_configurations(frame))
        labels = [label for label in labels_all if label in headline]
        if not labels:
            labels = labels_all
        f1_order = {row["configuration"]: row["delta"] for row in outputs.get("f1@20", [])}
        labels.sort(key=lambda label: f1_order.get(label, 0.0))
        fig, axes = plt.subplots(1, 3, figsize=(16, max(6, .29 * len(labels))), sharey=True)
        for ax, metric in zip(axes, PRIMARY_METRICS):
            by_config = {row["configuration"]: row for row in outputs.get(metric, [])}
            rows = [by_config[label] for label in labels if label in by_config]
            if not rows:
                ax.set_visible(False)
                continue
            y = np.arange(len(rows))
            x = np.array([row["delta"] for row in rows])
            err = np.vstack([x - np.array([row["ci_low"] for row in rows]),
                             np.array([row["ci_high"] for row in rows]) - x])
            for point, row in enumerate(rows):
                color = _ranking_color(row["ranking"])
                ax.errorbar(x[point], y[point], xerr=[[err[0, point]], [err[1, point]]],
                            fmt=_ranking_marker(row["ranking"]), color=color, ecolor=color,
                            capsize=2, alpha=.9)
            ax.axvline(0, color="#333333", linewidth=.9)
            ax.set(title=_format_metric(metric), xlabel="")
            ax.grid(axis="x", alpha=.25)
            if ax is axes[0]:
                ax.set_yticks(y, [_short_configuration(row["configuration"]) for row in rows])
        metric_rows = [row for values in outputs.values() for row in values]
        figure_themes = [row["themes"] for row in metric_rows]
        fig.suptitle(f"Diferenças pareadas vs. {_short_configuration(baseline)} · destaque · "
                     f"{_design_label(frame)} · pares completos e V/E/D no CSV · "
                     f"{_bootstrap_label(figure_themes)} (descritivo)", y=1.01)
        fig.supxlabel("Diferença pareada (método − referência); valores positivos favorecem o método",
                      y=.025)
        fig.tight_layout(rect=(0, .08, 1, 1))
        generated.extend(_save(fig, directory, f"fig05_paired_deltas_vs_{baseline}", formats))
        if progress_callback:
            progress_callback({"phase": "plotting", "subtask_completed": baseline_index,
                               "subtask_total": baseline_total,
                               "current_subtask": baselines[baseline_index]
                               if baseline_index < baseline_total else None})
    if csv_records:
        pd.DataFrame(csv_records).sort_values(["baseline", "metric", "configuration"]).to_csv(
            directory / "paired_method_deltas.csv", index=False)
    return generated


def _plot_seed_sensitivity(frame, directory, formats):
    graph = frame[frame["ranking"].isin(GRAPH_RANKINGS)]
    if graph.empty or "query_entities" not in set(graph["seed_label"]):
        return []
    base_cols = ["evaluation_id", "preset", "quorum", "result_unit", "ranking"]
    records = []
    for metric in PRIMARY_METRICS:
        if metric not in graph:
            continue
        pivot = graph.pivot_table(index=base_cols, columns="seed_label", values=metric, aggfunc="mean")
        if "query_entities" not in pivot:
            continue
        for seed in pivot.columns:
            if seed == "query_entities":
                continue
            delta = (pivot[seed] - pivot["query_entities"]).dropna().rename("delta").reset_index()
            delta["seed"] = seed
            delta["metric"] = metric
            delta["theme"] = delta["evaluation_id"].map(_theme_of)
            records.extend(delta.to_dict("records"))
    if not records:
        return []
    deltas = pd.DataFrame(records)
    pairs = sorted({(row["ranking"], row["seed"], row["preset"], row["quorum"])
                    for row in records}, key=lambda item: tuple(str(value) for value in item))
    summary_rows = []
    generated = []
    for metric in PRIMARY_METRICS:
        metric_rows = deltas[deltas["metric"] == metric]
        means = []
        for ranking, seed, preset, quorum in pairs:
            sub = metric_rows[(metric_rows["ranking"] == ranking) & (metric_rows["seed"] == seed)
                              & (metric_rows["preset"] == preset) & (metric_rows["quorum"] == quorum)]
            theme_values = sub.groupby("theme")["delta"].mean()
            est, low, high = bootstrap_theme_mean(theme_values.to_numpy())
            means.append({"ranking": ranking, "seed": seed, "preset": preset, "quorum": quorum,
                          "metric": metric, "delta": est, "ci_low": low, "ci_high": high,
                          "queries": sub["evaluation_id"].nunique(), "themes": theme_values.size})
        summary_rows.extend(means)
        means = [row for row in means if np.isfinite(row["delta"])]
        means.sort(key=lambda row: row["delta"])
        y = np.arange(len(means))
        x = np.array([row["delta"] for row in means])
        err = np.vstack([x - np.array([row["ci_low"] for row in means]),
                         np.array([row["ci_high"] for row in means]) - x])
        fig, ax = plt.subplots(figsize=(10, _sparse_plot_height(len(means))))
        if means:
            for point, row in enumerate(means):
                color = _ranking_color(row["ranking"])
                ax.errorbar(x[point], y[point], xerr=[[err[0, point]], [err[1, point]]],
                            fmt=_ranking_marker(row["ranking"]), color=color, ecolor=color,
                            capsize=2, alpha=.9)
            ax.axvline(0, color="#333333", linewidth=.9)
            labels = [f"{_short_configuration(row['ranking'])} · {_short_configuration(row['seed'])}"
                      for row in means]
            ax.set_yticks(y, labels)
        ax.set(xlabel=f"Variação vs. entidades da consulta em {_format_metric(metric)}",
               title=f"Sensibilidade à semente · {_format_metric(metric)} · contraste pareado vs. "
                     f"entidades da consulta · {len(means)} combinações; "
                       f"{_design_label(graph)} · {_bootstrap_label([row['themes'] for row in means])} (descritivo)")
        ax.grid(axis="x", alpha=.25)
        fig.tight_layout()
        generated.extend(_save(fig, directory, f"fig06_graph_seed_sensitivity_{metric.replace('@', '_')}", formats))
    pd.DataFrame(summary_rows).to_csv(directory / "graph_seed_sensitivity.csv", index=False)
    return generated


def _plot_quorum_sensitivity(frame, directory, formats):
    values = sorted(frame["quorum"].dropna().unique()) if "quorum" in frame else []
    if frame.empty or len(values) < 2:
        return []
    low_q, high_q = values[0], values[-1]
    index = ["evaluation_id", "preset", "result_unit", "ranking", "seed_label"]
    pivot = frame.pivot_table(index=index, columns="quorum", values="f1@20", aggfunc="mean")
    if low_q not in pivot or high_q not in pivot:
        return []
    delta = (pivot[high_q] - pivot[low_q]).dropna().rename("delta").reset_index()
    delta["theme"] = delta["evaluation_id"].map(_theme_of)
    delta["configuration"] = delta["ranking"] + " · semente=" + delta["seed_label"]
    if delta["preset"].nunique(dropna=True) > 1:
        delta["configuration"] += " · preset=" + delta["preset"].fillna("?").astype(str)
    if delta["result_unit"].nunique(dropna=True) > 1:
        delta["configuration"] += " · unidade=" + delta["result_unit"].fillna("?").astype(str)
    rows = []
    for config, group in delta.groupby("configuration"):
        estimate, ci_low, ci_high = bootstrap_theme_mean(group.groupby("theme")["delta"].mean().to_numpy())
        rows.append({"configuration": config, "delta": estimate, "ci_low": ci_low, "ci_high": ci_high,
                     "queries": group["evaluation_id"].nunique()})
    summary = pd.DataFrame(rows).sort_values("delta")
    y = np.arange(len(summary))
    x = summary["delta"].to_numpy()
    fig, ax = plt.subplots(figsize=(9, max(5, .3 * len(summary))))
    ax.errorbar(x, y, xerr=np.vstack([x - summary["ci_low"].to_numpy(),
                                     summary["ci_high"].to_numpy() - x]),
                fmt="o", color="#e07a32", capsize=2)
    ax.axvline(0, color="#333333", linewidth=.9)
    ax.set_yticks(y, summary["configuration"])
    ax.set(xlabel=f"Variação em F1@20: quorum {high_q:g} − {low_q:g}",
           title="Sensibilidade ao quorum (consultas pareadas)")
    ax.grid(axis="x", alpha=.25)
    summary.to_csv(directory / "quorum_sensitivity.csv", index=False)
    fig.tight_layout()
    return _save(fig, directory, "fig07_quorum_sensitivity", formats)


def _plot_cutoff_profiles(frame, directory, formats):
    if frame.empty:
        return []
    chosen = frame[(~frame["ranking"].isin(GRAPH_RANKINGS)) | (frame["seed_label"] == "query_entities")]
    if chosen.empty:
        return []
    common_limits = {}
    for metric in ("precision", "recall", "f1"):
        values = []
        for configuration in chosen["configuration"].drop_duplicates():
            subset = chosen[chosen["configuration"] == configuration]
            for k in F1_CUTOFFS:
                column = f"{metric}@{k}"
                if column in subset:
                    values.extend(subset.groupby("theme")[column].mean().tolist())
        common_limits[metric] = _ceil_axis_max(values, step=.05)
    families = [
        ("retrieval", chosen[~chosen["ranking"].isin(GRAPH_RANKINGS)], "baselines de recuperação"),
        ("graph", chosen[chosen["ranking"].isin(GRAPH_RANKINGS)], "métodos de grafo · entidades da consulta"),
    ]
    generated = []
    for suffix, family, label in families:
        if family.empty:
            continue
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        band_alpha = min(_uncertainty_band_alpha(family["configuration"].nunique()), .035)
        retrieval_colors = {"hybrid_max": "#0072B2", "rrf": "#D55E00", "cross_encoder": "#009E73"}
        for ax, metric in zip(axes, ("precision", "recall", "f1")):
            for configuration in family["configuration"].drop_duplicates():
                subset = family[family["configuration"] == configuration]
                ranking = subset["ranking"].iloc[0]
                ys = []
                lows = []
                highs = []
                for k in F1_CUTOFFS:
                    column = f"{metric}@{k}"
                    if column not in subset:
                        ys.append(np.nan)
                        lows.append(np.nan)
                        highs.append(np.nan)
                        continue
                    estimate, low, high = _theme_metric_interval(subset, column)
                    ys.append(estimate)
                    lows.append(low)
                    highs.append(high)
                if np.isfinite(ys).any():
                    color = retrieval_colors.get(ranking, _ranking_color(ranking))
                    ax.fill_between(F1_CUTOFFS, lows, highs, color=color, alpha=band_alpha, linewidth=0)
                    ax.plot(F1_CUTOFFS, ys, marker=_ranking_marker(ranking),
                            color=color, linestyle=_ranking_linestyle(ranking), linewidth=1.4,
                            label=_short_configuration(configuration))
            axis_max = common_limits[metric]
            ax.set(xticks=F1_CUTOFFS, ylim=(0, axis_max), xlabel="Corte k",
                   ylabel=f"Média macro por tema · escala 0–{axis_max:g}", title=_format_metric(metric))
            ax.grid(alpha=.25)
        axes[-1].legend(loc="center left", bbox_to_anchor=(1.02, .5), fontsize=7.5, frameon=False)
        fig.suptitle(f"Precisão, revocação e F1 por corte · {label} · zoom com zero visível · "
                     f"{_design_label(family)} · IC bootstrap 95% sobre temas (descritivo)", y=1.02)
        fig.tight_layout()
        stem = "fig08_retrieval_cutoff_profiles" if suffix == "retrieval" else "supp_graph_method_cutoff_profiles"
        generated.extend(_save(fig, directory, stem, formats))
    return generated


def _plot_ranking_cutoff_profiles(frame, directory, formats):
    if frame.empty:
        return []
    chosen = frame[(~frame["ranking"].isin(GRAPH_RANKINGS)) | (frame["seed_label"] == "query_entities")]
    if chosen.empty:
        return []
    families = [
        ("baselines", chosen[~chosen["ranking"].isin(GRAPH_RANKINGS)],
         "baselines de recuperação", "fig09_map_ndcg_cutoff_profiles"),
        ("graph", chosen[chosen["ranking"].isin(GRAPH_RANKINGS)],
         "métodos de grafo · entidades da consulta", "supp_graph_map_ndcg_cutoff_profiles"),
    ]
    generated = []
    for _, family, label, stem in families:
        if family.empty:
            continue
        fig, axes = plt.subplots(1, 2, figsize=(13, 5))
        family_metric_limits = {}
        # Use the same metric limits for both split figures to preserve direct comparison.
        for metric in ("map", "ndcg"):
            values = []
            for configuration in chosen["configuration"].drop_duplicates():
                rows = chosen[chosen["configuration"] == configuration]
                for k in RANKING_CUTOFFS:
                    column = f"{metric}@{k}"
                    if column in rows:
                        estimate, _, _ = _theme_metric_interval(rows, column)
                        values.append(estimate)
            family_metric_limits[metric] = _ceil_axis_max(values, step=.05)
        for ax, metric in zip(axes, ("map", "ndcg")):
            for configuration in family["configuration"].drop_duplicates():
                subset = family[family["configuration"] == configuration]
                ys, lows, highs = [], [], []
                for k in RANKING_CUTOFFS:
                    column = f"{metric}@{k}"
                    if column not in subset:
                        ys.append(np.nan); lows.append(np.nan); highs.append(np.nan)
                        continue
                    estimate, low, high = _theme_metric_interval(subset, column)
                    ys.append(estimate); lows.append(low); highs.append(high)
                if np.isfinite(ys).any():
                    ranking = subset["ranking"].iloc[0]
                    color = _ranking_color(ranking)
                    ax.plot(RANKING_CUTOFFS, ys, marker=_ranking_marker(ranking),
                            color=color, linestyle=_ranking_linestyle(ranking), linewidth=1.5,
                            label=_short_configuration(configuration))
                    interval_positions = [0, len(RANKING_CUTOFFS) - 1]
                    valid_positions = [position for position in interval_positions
                                       if np.isfinite(ys[position]) and np.isfinite(lows[position])
                                       and np.isfinite(highs[position])]
                    if valid_positions:
                        ax.errorbar([RANKING_CUTOFFS[position] for position in valid_positions],
                                    [ys[position] for position in valid_positions],
                                    yerr=[[ys[position] - lows[position] for position in valid_positions],
                                          [highs[position] - ys[position] for position in valid_positions]],
                                    fmt="none", ecolor=color, alpha=.8, capsize=2, linewidth=.8)
            axis_max = family_metric_limits[metric]
            ax.set(xticks=RANKING_CUTOFFS, ylim=(0, axis_max), xlabel="Corte k",
                   ylabel=f"Média macro por tema · escala 0–{axis_max:g}",
                   title=_format_metric(metric))
            ax.grid(alpha=.25)
        axes[-1].legend(loc="center left", bbox_to_anchor=(1.02, .5), fontsize=7.5, frameon=False)
        fig.suptitle(f"MAP e NDCG por corte · {label} · zoom com zero visível · {_design_label(family)} · "
                     "IC bootstrap 95% sobre temas em k=5 e k=20 (descritivo)", y=1.02)
        fig.tight_layout()
        generated.extend(_save(fig, directory, stem, formats))
    return generated


def _plot_low_score_cdf(frame, directory, formats):
    if frame.empty or "f1@20" not in frame:
        return []
    chosen = frame[(~frame["ranking"].isin(GRAPH_RANKINGS)) | (frame["seed_label"] == "query_entities")]
    records = []
    headline = set(_headline_configurations(chosen, top_n=5))
    fig, ax = plt.subplots(figsize=(10, 6))
    observed_max = float(chosen["f1@20"].max()) if chosen["f1@20"].notna().any() else 0.0
    x_max = _ceil_axis_max([observed_max], step=.05)
    for config, group in chosen.groupby("configuration", sort=False):
        values = group["f1@20"].dropna().to_numpy()
        if not len(values):
            continue
        x = np.sort(values)
        y = np.arange(1, len(x) + 1) / len(x)
        records.append({"configuration": config, "queries": len(x),
                        "share_zero": float(np.mean(x == 0)),
                        "share_le_10pct": float(np.mean(x <= .10)),
                        "share_le_20pct": float(np.mean(x <= .20))})
        if config in headline:
            ranking = group["ranking"].iloc[0]
            ax.step(x, y, where="post", linewidth=1.5, color=_ranking_color(ranking),
                    linestyle=_ranking_linestyle(ranking), label=_short_configuration(config))
    for threshold in (0, .1, .2):
        if threshold <= x_max:
            ax.axvline(threshold, color="#555555", linestyle=":" if threshold else "--", linewidth=.8)
            if threshold:
                ax.text(threshold, .98, f"limiar {threshold:.2f}".replace(".", ","),
                        transform=ax.get_xaxis_transform(), rotation=90, ha="right", va="top",
                        fontsize=7, color="#444444", backgroundcolor="white")
    ax.set(xlim=(0, x_max), ylim=(0, 1), xlabel=f"F1@20 · escala ampliada 0–{x_max:g}",
           ylabel="Proporção de consultas no limiar ou abaixo dele",
             title=f"Cauda inferior de F1@20 · {_design_label(chosen)} · taxas exatas em CSV")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, .5), fontsize=7.5, frameon=False,
              title="Destaques; tabela completa em CSV")
    ax.grid(alpha=.2)
    pd.DataFrame(records).to_csv(directory / "low_score_rates.csv", index=False)
    fig.tight_layout()
    return _save(fig, directory, "fig10_low_score_cdf", formats)


def _plot_theme_heatmap(frame, directory, formats):
    if frame.empty or "f1@20" not in frame:
        return []
    chosen = frame[(~frame["ranking"].isin(GRAPH_RANKINGS)) | (frame["seed_label"] == "query_entities")]
    matrix = chosen.pivot_table(index="theme_label", columns="configuration", values="f1@20", aggfunc="mean")
    matrix = matrix.loc[matrix.mean(axis=1).sort_values(ascending=False).index]
    query_counts = (chosen.drop_duplicates("evaluation_id").groupby("theme_label")["evaluation_id"]
                    .nunique().reindex(matrix.index))
    matrix.assign(queries=query_counts).to_csv(directory / "theme_heterogeneity.csv")
    headline = [name for name in _headline_configurations(chosen) if name in matrix.columns]
    if not headline:
        headline = list(matrix.columns)
    view = matrix[headline]
    vmax = _ceil_axis_max([matrix.to_numpy().max()], step=.05)
    fig, ax = plt.subplots(figsize=(max(12, view.shape[1] * .85), max(6, view.shape[0] * .42)))
    sns.heatmap(view, vmin=0, vmax=vmax, cmap="viridis", mask=view.isna(), ax=ax,
                annot=view.size <= 120, fmt=".2f",
                cbar_kws={"label": f"F1@20 · escala 0–{vmax:g}"})
    ax.set(title=f"F1@20 por tema · configurações em destaque · {_design_label(chosen)} · "
                 f"escala ampliada 0–{vmax:g}",
           xlabel="Ranking · semente", ylabel="Tema")
    ax.set_yticklabels([f"{label.get_text()} (n={int(query_counts.loc[label.get_text()])})"
                        for label in ax.get_yticklabels()], fontsize=8)
    ax.set_xticklabels([_short_configuration(label.get_text()) for label in ax.get_xticklabels()],
                       rotation=40, ha="right", fontsize=8)
    fig.tight_layout()
    return _save(fig, directory, "fig11_theme_heterogeneity", formats)


def _plot_theme_difficulty(frame, directory, formats):
    columns = ["theme_label", "matching_articles_count", "eligible_articles_count", "difficulty_score"]
    required = set(columns)
    if frame.empty or not required.issubset(frame.columns):
        return []
    columns.extend(column for column in ("main_entities", "eligibility_snapshot_id")
                   if column in frame.columns)
    metrics = frame[columns].dropna(subset=[
        "matching_articles_count", "eligible_articles_count", "difficulty_score",
    ]).drop_duplicates("theme_label")
    if metrics.empty:
        return []
    metrics = metrics.sort_values(["difficulty_score", "theme_label"], ascending=[False, True])
    metrics.to_csv(directory / "theme_difficulty.csv", index=False)
    height = max(5, .34 * len(metrics) + 1.5)
    fig, ax = plt.subplots(figsize=(11, height))
    bars = ax.barh(metrics["theme_label"], metrics["difficulty_score"], color="#527da8")
    ax.invert_yaxis()
    ax.set_xlabel("Dificuldade · log(1 + correspondentes) / log(1 + elegíveis) (0–1)")
    ax.set_ylabel("Tema")
    ax.set_title("Dificuldade por tema segundo a prevalência das entidades principais")
    ax.set_xlim(0, 1)
    for bar, row in zip(bars, metrics.itertuples(index=False)):
        ax.text(bar.get_width() + .01, bar.get_y() + bar.get_height() / 2,
                f"{int(row.matching_articles_count)}/{int(row.eligible_articles_count)} artigos",
                va="center", fontsize=8)
    ax.grid(axis="x", alpha=.2)
    fig.tight_layout()
    return _save(fig, directory, "fig15_theme_difficulty", formats)


def _plot_theme_performance_matrix(frame, directory, formats):
    performance_metrics = ["f1@20", "mrr@20", "ndcg@20"]
    required = {"theme", "theme_label", "evaluation_id", "difficulty_score",
                "matching_articles_count", "eligible_articles_count", *performance_metrics}
    if frame.empty or not required.issubset(frame.columns):
        return []
    per_query = (frame.dropna(subset=["difficulty_score"])
                 .groupby(["theme", "theme_label", "evaluation_id"], as_index=False)
                 .agg(**{metric: (metric, "mean") for metric in performance_metrics},
                      difficulty_score=("difficulty_score", "first"),
                      matching_articles_count=("matching_articles_count", "first"),
                      eligible_articles_count=("eligible_articles_count", "first")))
    if per_query.empty:
        return []
    metrics = (per_query.groupby(["theme", "theme_label"], as_index=False)
               .agg(**{metric: (metric, "mean") for metric in performance_metrics},
                    difficulty_score=("difficulty_score", "first"),
                    matching_articles_count=("matching_articles_count", "first"),
                    eligible_articles_count=("eligible_articles_count", "first"),
                    query_count=("evaluation_id", "nunique")))
    metrics = metrics.sort_values(["difficulty_score", "theme_label"], ascending=[True, True])
    metrics.to_csv(directory / "theme_performance_by_difficulty.csv", index=False)

    row_count = len(metrics)
    fig_height = max(5, .30 * row_count + 1.4)
    fig, axes = plt.subplots(
        1, 6, figsize=(17, fig_height), sharey=True,
        gridspec_kw={"width_ratios": [2.2, .95, 1.25, 1.25, 1.25, 1.25], "wspace": .08},
    )
    y_values = np.arange(row_count)
    for axis in axes[:3]:
        axis.set_ylim(row_count - .5, -.5)
        axis.set_yticks(y_values)
        axis.set_yticklabels([])
        axis.tick_params(axis="y", length=0)
        axis.set_xlim(0, 1)
        axis.axis("off")
    axes[0].set_title("Tema", loc="left")
    axes[1].set_title("Dificuldade", loc="left")
    axes[2].set_title("Match / elegíveis", loc="left")
    for index, row in enumerate(metrics.itertuples(index=False)):
        axes[0].text(0, index, row.theme_label, va="center", fontsize=8)
        axes[1].text(0, index, f"{row.difficulty_score:.4f}", va="center", fontsize=8)
        axes[2].text(0, index,
                     f"{int(row.matching_articles_count)}/{int(row.eligible_articles_count)}",
                     va="center", fontsize=8)

    colors = {"f1@20": "#527da8", "mrr@20": "#2a9d8f", "ndcg@20": "#d98e32"}
    for axis, metric in zip(axes[3:], performance_metrics):
        axis.set_ylim(row_count - .5, -.5)
        axis.set_xlim(0, 1)
        axis.set_yticks(y_values)
        axis.set_yticklabels([])
        axis.tick_params(axis="y", length=0)
        axis.set_title(metric.upper())
        axis.set_xticks([0, .5, 1], ["0.0", "0.5", "1.0"])
        axis.grid(axis="x", alpha=.2)
        axis.scatter(metrics[metric], y_values, color=colors[metric], s=28,
                     edgecolors="white", linewidths=.5, zorder=3)
        for index, value in enumerate(metrics[metric]):
            if pd.notna(value):
                axis.plot([0, value], [index, index], color=colors[metric], alpha=.25,
                          linewidth=1, zorder=2)
        axis.set_xlabel("Desempenho (0–1)", fontsize=8)
    rankings = sorted(frame["ranking"].dropna().unique()) if "ranking" in frame else []
    ranking_scope = (f"ranking {rankings[0]}" if len(rankings) == 1
                     else f"média de {len(rankings)} rankings selecionados")
    fig.suptitle(f"Desempenho por tema ordenado pela dificuldade · macro por consulta · {ranking_scope}", y=.995)
    fig.subplots_adjust(left=.02, right=.995, top=.92, bottom=.09, wspace=.08)
    return _save(fig, directory, "fig16_theme_performance_matrix", formats)


def _plot_runtime_quality(frame, directory, formats):
    if frame.empty or "computation_seconds" not in frame or frame["computation_seconds"].notna().sum() == 0:
        return []
    timed = frame.dropna(subset=["computation_seconds", "f1@20"]).copy()
    if "computation_reused" in timed and timed["computation_reused"].notna().any():
        timed = timed[timed["computation_reused"] == False]  # noqa: E712
    if timed.empty:
        return []
    timed["theme"] = timed["theme"].astype(str)
    configs = []
    for config, group in timed.groupby("configuration"):
        configs.append({"configuration": config,
                        "seconds": float(group.groupby("theme")["computation_seconds"].median().median()),
                        "f1": float(group.groupby("theme")["f1@20"].mean().mean()),
                        "queries": group["evaluation_id"].nunique()})
    plot = pd.DataFrame(configs)
    plot["pareto_frontier"] = plot.apply(
        lambda row: not ((plot["seconds"] <= row["seconds"]) & (plot["f1"] >= row["f1"])
                         & ((plot["seconds"] < row["seconds"]) | (plot["f1"] > row["f1"]))).any(), axis=1
    )
    plot = plot.sort_values("seconds").reset_index(drop=True)
    ranking_by_config = frame.drop_duplicates("configuration").set_index("configuration")["ranking"]
    plot["ranking"] = plot["configuration"].map(ranking_by_config)

    def runtime_family(ranking):
        if ranking == "ensemble_rrf":
            return "Ensemble RRF"
        if ranking in HEADLINE_BASELINES:
            return "Baselines medidas"
        return "Métodos de grafo"

    runtime_styles = {
        "Baselines medidas": ("#7A8793", "o"),
        "Métodos de grafo": ("#0072B2", "s"),
        "Ensemble RRF": ("#E69F00", "D"),
    }
    plot["family"] = plot["ranking"].map(runtime_family)
    fig, ax = plt.subplots(figsize=(10, 6))
    uses_log1p = bool((plot["seconds"] <= 0).any())
    plot["plot_seconds"] = np.log1p(plot["seconds"]) if uses_log1p else plot["seconds"]
    ax.set_xscale("linear" if uses_log1p else "log")
    for family, subset in plot.groupby("family", sort=False):
        color, marker = runtime_styles[family]
        dominated = subset[~subset["pareto_frontier"]]
        frontier_family = subset[subset["pareto_frontier"]]
        if not dominated.empty:
            ax.scatter(dominated["plot_seconds"], dominated["f1"], s=34, color=color, marker=marker,
                       alpha=.28, label=f"{family} · dominadas")
        if not frontier_family.empty:
            ax.scatter(frontier_family["plot_seconds"], frontier_family["f1"], s=54,
                       color=color, marker=marker, edgecolors="white", linewidths=.7,
                       alpha=.95, label=f"{family} · não dominadas")
    frontier = plot[plot["pareto_frontier"]].sort_values("seconds")
    label_configs = _runtime_frontier_label_configs(frontier)
    plot["annotated"] = plot["configuration"].isin(label_configs)
    ax.plot(frontier["plot_seconds"], frontier["f1"], color="#009E73", linewidth=1.6,
            marker="o", markersize=5, markerfacecolor="white", markeredgewidth=1.5,
            label="Fronteira de Pareto · menor tempo / maior F1")
    label_offsets = ((8, 12), (8, -14), (-8, 16), (-8, -18), (25, 1), (-25, 1))
    frontier_rows = list(frontier[frontier["configuration"].isin(label_configs)].itertuples())
    clustered = [row for row in frontier_rows if row.plot_seconds >= .02]
    cluster_positions = {row.configuration: index for index, row in enumerate(clustered)}
    for position, row in enumerate(frontier_rows):
        if row.plot_seconds >= .02 and len(clustered) > 1:
            cluster_index = cluster_positions[row.configuration]
            vertical_offset = (cluster_index - (len(clustered) - 1) / 2) * 19
            offset, align = (38, vertical_offset), "left"
        else:
            offset = label_offsets[position % len(label_offsets)]
            align = "left" if offset[0] >= 0 else "right"
        ax.annotate(_short_configuration(row.configuration), (row.plot_seconds, row.f1),
                    xytext=offset, textcoords="offset points", fontsize=7, ha=align,
                    va="bottom" if offset[1] >= 0 else "top",
                    bbox={"facecolor": "white", "edgecolor": "none", "alpha": .82, "pad": 1},
                    arrowprops={"arrowstyle": "-", "color": "#777777", "linewidth": .6,
                                "shrinkA": 2, "shrinkB": 3})
    max_seconds = float(plot["seconds"].max())
    min_seconds = float(plot.loc[plot["seconds"] > 0, "seconds"].min()) if (plot["seconds"] > 0).any() else 0
    tick_seconds = [value for value in (.001, .01, .1, 1, 10, 50, 100)
                    if value <= max_seconds * 1.05 and (uses_log1p or value >= min_seconds * .9)]
    if uses_log1p:
        tick_seconds = [0, *tick_seconds]
        ax.set_xticks(np.log1p(tick_seconds), [f"{value:g}" for value in tick_seconds])
        scale_label = "log1p"
    else:
        ax.set_xticks(tick_seconds, [f"{value:g}" for value in tick_seconds])
        scale_label = "logarítmica"
    ax.set_ylim(0, min(1.0, _ceil_axis_max(plot["f1"], step=.025) * 1.15))
    ax.set(xlabel=f"Tempo de computação do ranking (segundos; escala {scale_label})",
           ylabel="F1@20 macro por tema",
           title=f"Trade-off qualidade–custo do ranking · {_design_label(timed)} · "
                 "fronteira em destaque; rótulos espaçados; não é latência total")
    ax.margins(x=.10)
    ax.grid(alpha=.25)
    ax.legend(frameon=False)
    plot.drop(columns="plot_seconds").to_csv(directory / "runtime_quality.csv", index=False)
    fig.tight_layout()
    return _save(fig, directory, "fig12_runtime_quality", formats)


def _plot_graph_diagnostics(frame, directory, formats):
    if (frame.empty or "query_entity_matched_count" not in frame
            or "query_entity_count" not in frame):
        return []
    all_graph = frame[frame["ranking"].isin(GRAPH_RANKINGS)
                      & frame["seed_label"].eq("query_entities")].copy()
    for column in ("query_entity_count", "query_entity_matched_count", "f1@20"):
        all_graph[column] = pd.to_numeric(all_graph[column], errors="coerce")
    graph = all_graph.dropna(subset=["query_entity_count", "query_entity_matched_count", "f1@20"]).copy()
    if graph.empty:
        return []
    graph["query_entity_count"] = graph["query_entity_count"].clip(lower=0)
    graph["query_entity_matched_count"] = graph["query_entity_matched_count"].clip(lower=0)
    diagnostic_columns = [column for column in
                          ("evaluation_id", "theme", "formulation", "ranking", "query_entity_count",
                           "query_entity_matched_count", "query_seed_fallback_reason", "f1@20")
                          if column in all_graph]
    diagnostic = all_graph[diagnostic_columns].copy()
    diagnostic.to_csv(directory / "graph_diagnostics.csv", index=False)
    missing_matches = int(all_graph["query_entity_matched_count"].isna().sum())

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    max_extracted = int(graph["query_entity_count"].max())
    max_matched = int(graph["query_entity_matched_count"].max())
    scatter = axes[0].scatter(graph["query_entity_count"],
                               graph["query_entity_matched_count"],
                               c=graph["f1@20"], cmap="viridis", vmin=0, vmax=_ceil_axis_max(graph["f1@20"]),
                               alpha=.38, s=24, edgecolors="none")
    axes[0].plot([0, max(max_extracted, max_matched)], [0, max(max_extracted, max_matched)],
                 color="#777777", linestyle=":", linewidth=.8)
    axes[0].set_xticks(range(max_extracted + 1))
    axes[0].set_yticks(range(max_matched + 1))
    axes[0].set(xlim=(-.25, max(.5, max_extracted + .5)), ylim=(-.25, max(.5, max_matched + .5)),
                xlabel="Entidades extraídas da consulta", ylabel="Entidades correspondidas no grafo",
                title="Extraídas × correspondidas · pontos sobrepostos escurecem")
    axes[0].grid(alpha=.18)
    colorbar = fig.colorbar(scatter, ax=axes[0], fraction=.046, pad=.04)
    colorbar.set_label("F1@20")

    counts = graph.groupby(["query_entity_count", "query_entity_matched_count"], as_index=False).size()
    matrix = counts.pivot(index="query_entity_matched_count", columns="query_entity_count", values="size")
    matrix = matrix.reindex(index=range(max_matched + 1), columns=range(max_extracted + 1), fill_value=0)
    sns.heatmap(matrix, annot=True, fmt="g", cmap="Blues", cbar_kws={"label": "Linhas método-consulta"},
                ax=axes[1])
    axes[1].invert_yaxis()
    axes[1].set(xlabel="Entidades extraídas da consulta", ylabel="Entidades correspondidas no grafo",
                title="Frequência por consulta × método (célula vazia = zero)")
    fig.suptitle(f"Diagnóstico de entidades · {graph['evaluation_id'].nunique()} consultas · "
                 f"{len(graph)}/{len(all_graph)} observações com contagens · "
                 f"{missing_matches} sem contagem de correspondência", y=1.02)
    fig.tight_layout()
    return _save(fig, directory, "fig13_graph_diagnostics", formats)


def _plot_ranking_overlap(frame, directory, formats):
    if frame.empty or "ranked_urls" not in frame:
        return []
    chosen = frame[(~frame["ranking"].isin(GRAPH_RANKINGS)) | (frame["seed_label"] == "query_entities")]
    rankings = sorted(chosen["configuration"].dropna().unique())
    if len(rankings) < 2:
        return []
    per_query = {}
    for (evaluation_id, config), group in chosen.groupby(["evaluation_id", "configuration"]):
        ranked = next((urls for urls in group["ranked_urls"] if isinstance(urls, list)), [])
        per_query[(evaluation_id, config)] = set(ranked[:20])
    matrix = pd.DataFrame(np.nan, index=rankings, columns=rankings)
    paired_counts = pd.DataFrame(0, index=rankings, columns=rankings, dtype=int)
    pair_records = []
    for left, right in itertools.combinations_with_replacement(rankings, 2):
        scores = []
        for evaluation_id in chosen["evaluation_id"].unique():
            a = per_query.get((evaluation_id, left)); b = per_query.get((evaluation_id, right))
            if a is None or b is None:
                continue
            union = a | b
            scores.append(len(a & b) / len(union) if union else 1.0)
        if scores:
            mean_score = float(np.mean(scores))
            matrix.loc[left, right] = matrix.loc[right, left] = mean_score
            paired_counts.loc[left, right] = paired_counts.loc[right, left] = len(scores)
            pair_records.append({"ranking_a": left, "ranking_b": right,
                                 "jaccard_mean": mean_score, "paired_queries": len(scores)})
    pd.DataFrame(pair_records).to_csv(directory / "ranking_overlap_pairs.csv", index=False)
    fig, ax = plt.subplots(figsize=(max(9, .55 * len(rankings)), max(7, .48 * len(rankings))))
    sns.heatmap(matrix, vmin=0, vmax=1, cmap="viridis", square=True, ax=ax,
                cbar_kws={"label": "Sobreposição Jaccard média no top-20 (0–1)"})
    ax.set(title=f"Sobreposição dos 20 primeiros resultados · {_design_label(chosen)} · "
                 "n de consultas pareadas por par no CSV",
           xlabel="Configuração do método", ylabel="Configuração do método")
    ax.set_xticklabels([_short_configuration(label.get_text()) for label in ax.get_xticklabels()],
                       rotation=45, ha="right", fontsize=7)
    ax.set_yticklabels([_short_configuration(label.get_text()) for label in ax.get_yticklabels()],
                       rotation=0, fontsize=7)
    fig.tight_layout()
    return _save(fig, directory, "fig14_ranking_overlap", formats)


def _plot_headline_summary(frame, directory, formats):
    if frame.empty:
        return []
    query = _query_level(frame)
    summary = summarize_configurations(frame)
    graph_summary = summary[summary["ranking"].isin(GRAPH_RANKINGS)]
    best_graph = graph_summary.sort_values("f1@20", ascending=False).head(1)
    rrf = summary[summary["ranking"].eq("rrf")].head(1)
    pool_recall = query["reference_pool_recall"].mean() if "reference_pool_recall" in query else np.nan
    oracle = frame.drop_duplicates("evaluation_id")
    oracle_mean = oracle["oracle_f1@20"].mean() if "oracle_f1@20" in oracle else np.nan
    themes = query["theme"].nunique()
    n_queries = query["evaluation_id"].nunique()
    runtime = pd.to_numeric(frame.get("computation_seconds"), errors="coerce")
    if "computation_reused" in frame:
        runtime = runtime[~frame["computation_reused"].fillna(False).astype(bool)]
    runtime_median = runtime.median() if len(runtime) else np.nan
    cross_encoder_runtime = pd.to_numeric(
        frame.loc[frame["ranking"].eq("cross_encoder"), "computation_seconds"], errors="coerce"
    ).median() if frame["ranking"].eq("cross_encoder").any() else np.nan

    fig, axes = plt.subplots(2, 2, figsize=(12, 7))
    for ax in axes.flat:
        ax.axis("off")
    blocks = [
        (f"DESENHO\n{themes} temas · {n_queries} consultas\n"
         "Médias por consulta dentro do tema; peso igual por tema."),
        (f"COBERTURA\nRevocação média no pool: {pool_recall:.3f}\n"
         f"F1@20 oráculo no pool: {oracle_mean:.3f}\n(teto apenas no conjunto recuperado)"
         if pd.notna(pool_recall) and pd.notna(oracle_mean) else "COBERTURA\nMétricas de cobertura indisponíveis."),
        ("RANKING · DESCRITIVO\n"
         + (f"RRF: F1@20={rrf.iloc[0]['f1@20']:.3f}\n" if not rrf.empty else "RRF: indisponível\n")
         + (f"Maior média graph: {_short_configuration(best_graph.iloc[0]['configuration'])}\n"
            f"F1@20={best_graph.iloc[0]['f1@20']:.3f} (selecionado neste run)"
            if not best_graph.empty else "Nenhum resultado graph disponível.")),
        (f"CUSTO COMPUTACIONAL\nMediana ranking: {runtime_median:.3f} s\n"
         f"Cross-encoder: {cross_encoder_runtime:.3f} s\n(tempo de ranking; não latência total)"
         if pd.notna(runtime_median) and pd.notna(cross_encoder_runtime)
         else "CUSTO COMPUTACIONAL\nTempos indisponíveis."),
    ]
    for ax, text in zip(axes.flat, blocks):
        heading, *body = text.split("\n")
        ax.text(.02, .95, heading, transform=ax.transAxes, va="top", fontsize=11,
                fontweight="bold", color="#315b7d")
        ax.text(.02, .75, "\n".join(body), transform=ax.transAxes, va="top", fontsize=12,
                linespacing=1.6)
        ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes, fill=False,
                                   edgecolor="#d5dbe3", linewidth=1))
    fig.suptitle(f"Resumo da rodada · evidência descritiva; "
                 f"incerteza reamostrada em {themes} temas", y=.99)
    fig.tight_layout(rect=(0, 0, 1, .96))
    return _save(fig, directory, "headline_summary", formats)


def _figure_manifest(frame, metadata, output_dir, formats, include_partial, include_ranking_overlap,
                     baselines, progress_callback=None, rankings=None, seed_methods=None,
                     filters=None, figure_families=None, audit_counts=None):
    global PARTIAL_INCLUSIVE
    rankings = sorted(set(rankings or SUPPORTED_RANKINGS))
    seed_methods = sorted(set(seed_methods or SUPPORTED_SEED_METHODS))
    baselines = list(dict.fromkeys(baselines or []))
    filters = filters or {}
    figure_families = set(figure_families or DEFAULT_FIGURE_FAMILIES)
    if include_ranking_overlap:
        figure_families.add("overlap")
    if not set(rankings).issubset(SUPPORTED_RANKINGS):
        raise ValueError("One or more selected ranking methods are not supported.")
    if not set(seed_methods).issubset(SUPPORTED_SEED_METHODS):
        raise ValueError("One or more selected seeding methods are not supported.")
    if not set(baselines).issubset(SUPPORTED_RANKINGS):
        raise ValueError("One or more paired-comparison references are not supported.")
    if not figure_families or not figure_families.issubset(FIGURE_FAMILIES):
        raise ValueError("Select at least one supported figure family.")
    if progress_callback:
        progress_callback({"phase": "analyzing", "stage": "auditing",
                           "stage_label": "Conferindo grupos e completude"})
    analysis_started = time.perf_counter()
    analysis_started = time.perf_counter()
    full_audit = (audit_groups_from_counts(audit_counts, metadata.get("settings") or {})
                  if audit_counts is not None else audit_groups(frame, metadata.get("settings") or {}))
    scoped_frame = filter_result_scope(frame, filters)
    requested_rankings = set(rankings) | set(baselines)
    scoped_frame = scoped_frame[scoped_frame["ranking"].isin(requested_rankings)].copy()
    graph_mask = scoped_frame["ranking"].isin(GRAPH_RANKINGS)
    scoped_frame = scoped_frame[~graph_mask | scoped_frame["seed"].isin(seed_methods)].copy()
    if scoped_frame.empty:
        raise ValueError("No results match the selected methods and filters.")
    analysis_and_references = prepare_analysis_frame(scoped_frame, full_audit,
                                                     include_partial=include_partial)
    analysis = filter_methods(analysis_and_references, rankings, seed_methods)
    if analysis.empty:
        raise ValueError("No complete result groups remain. Include partial groups or adjust the filters.")
    analysis_seconds = time.perf_counter() - analysis_started
    comparison_analysis = analysis_and_references[
        analysis_and_references["ranking"].isin(baselines)
    ].copy()
    audit_keys = {
        tuple(_canonical_value(value) for value in row)
        for row in scoped_frame[["evaluation_id", "preset", "quorum", "result_unit"]]
        .itertuples(index=False, name=None)
    }
    audit = full_audit[
        full_audit.apply(lambda row: tuple(_canonical_value(row[column]) for column in
                                           ("evaluation_id", "preset", "quorum", "result_unit"))
                         in audit_keys, axis=1)
    ].copy()
    PARTIAL_INCLUSIVE = bool(include_partial and not analysis.empty and analysis["partial_group"].any())
    output_dir.mkdir(parents=True, exist_ok=True)
    if progress_callback:
        progress_callback({"phase": "analyzing", "stage": "saving_tables",
                           "stage_label": "Salvando tabelas de análise"})
    tables_started = time.perf_counter()
    scoped_frame.to_csv(output_dir / "normalized_results.csv", index=False)
    audit.to_csv(output_dir / "group_completeness.csv", index=False)
    analysis.to_csv(output_dir / "analysis_results.csv", index=False)
    example_columns = [column for column in
                       ("evaluation_id", "theme", "formulation", "query", "ranking", "seed_label",
                        "f1@20", "query_entity_count", "query_entity_matched_count",
                        "query_seed_fallback_reason") if column in analysis]
    if "f1@20" in analysis:
        graph_rows = analysis[analysis["ranking"].isin(GRAPH_RANKINGS)]
        extracted = (pd.to_numeric(graph_rows["query_entity_count"], errors="coerce").fillna(0)
                     if "query_entity_count" in graph_rows else pd.Series(0, index=graph_rows.index))
        matched = (pd.to_numeric(graph_rows["query_entity_matched_count"], errors="coerce").fillna(0)
                   if "query_entity_matched_count" in graph_rows
                   else pd.Series(0, index=graph_rows.index))
        no_matches = extracted.gt(0) & matched.eq(0)
        examples = graph_rows[graph_rows["f1@20"].eq(0) | no_matches]
        examples[example_columns].drop_duplicates().to_csv(output_dir / "query_diagnostic_examples.csv", index=False)
    tables_seconds = time.perf_counter() - tables_started
    generated = []
    plots = []
    if "overview" in figure_families:
        plots.extend([
            ("Resumo geral", _plot_headline_summary),
            ("Composição da avaliação", _plot_composition),
            ("Cobertura e teto", _plot_retrieval_ceiling),
            ("Qualidade dos rankings", _plot_ranking_leaderboard),
            ("Desempenho por formulação", _plot_formulation_heatmaps),
        ])
    if "graph" in figure_families:
        plots.extend([("Sensibilidade às sementes", _plot_seed_sensitivity),
                      ("Diagnóstico de entidades", _plot_graph_diagnostics)])
    if "cutoff" in figure_families:
        plots.extend([("Perfis por corte", _plot_cutoff_profiles),
                      ("MAP/NDCG por corte", _plot_ranking_cutoff_profiles)])
    if "tail" in figure_families:
        plots.append(("Cauda de F1", _plot_low_score_cdf))
    if "theme" in figure_families:
        plots.extend([("Heterogeneidade por tema", _plot_theme_heatmap),
                      ("Dificuldade por tema", _plot_theme_difficulty),
                      ("Desempenho por tema × dificuldade", _plot_theme_performance_matrix)])
    if "runtime" in figure_families:
        plots.append(("Qualidade e custo", _plot_runtime_quality))
    tasks = list(plots)
    if "comparisons" in figure_families and baselines:
        tasks.append(("Diferenças pareadas", None))
    if "overlap" in figure_families:
        tasks.append(("Sobreposição top-20", None))
    if not tasks:
        raise ValueError("The selected figure families have no outputs to generate.")
    task_total = len(tasks)
    plot_timings = {}
    for task_index, (task_label, plot) in enumerate(tasks, start=1):
        task_started = time.perf_counter()
        if progress_callback:
            progress_callback({"phase": "plotting", "completed_tasks": task_index - 1,
                               "total_tasks": task_total, "current_task": task_label,
                               "subtask_completed": None, "subtask_total": None,
                               "current_subtask": None})
        if plot is not None:
            generated.extend(plot(analysis, output_dir, formats))
        elif task_label == "Diferenças pareadas":
            nested_callback = None
            if progress_callback:
                nested_callback = lambda event: progress_callback({
                    "completed_tasks": task_index - 1,
                    "total_tasks": task_total,
                    "current_task": task_label,
                    **event,
                })
            paired_frame = pd.concat([analysis, comparison_analysis], ignore_index=True)
            generated.extend(_plot_paired_deltas(paired_frame, output_dir, formats, baselines,
                                                  progress_callback=nested_callback))
        else:
            overlap = merge_ranking_lists(scoped_frame, analysis)
            generated.extend(_plot_ranking_overlap(overlap, output_dir, formats))
        plot_timings[task_label] = time.perf_counter() - task_started
        if progress_callback:
            progress_callback({"phase": "plotting", "completed_tasks": task_index,
                               "total_tasks": task_total,
                               "current_task": tasks[task_index][0] if task_index < task_total else None,
                               "last_completed_task": task_label,
                               "last_task_seconds": plot_timings[task_label],
                               "subtask_completed": None, "subtask_total": None,
                               "current_subtask": None})
    if progress_callback:
        progress_callback({"phase": "writing_manifest", "stage_label": "Finalizando manifesto"})
    generated = sorted(generated, key=_natural_figure_sort_key)
    warnings = []
    if audit.empty or not audit["complete"].all():
        warnings.append("Some query/configuration groups are incomplete; headline figures use complete groups only.")
    partial_rows_present = ("partial_group" in analysis
                            and bool(analysis["partial_group"].fillna(False).any()))
    if include_partial and partial_rows_present:
        warnings.append("Partial rows were included in exploratory figures and are marked in analysis_results.csv.")
    not_generated = []
    query_frame = scoped_frame.drop_duplicates("evaluation_id") if "evaluation_id" in scoped_frame else scoped_frame
    query_count = int(query_frame["evaluation_id"].nunique()) if "evaluation_id" in query_frame else 0
    theme_count = int(query_frame["theme"].nunique()) if "theme" in query_frame else 0
    theme_query_counts = (
        {str(key): int(value) for key, value in
         query_frame.groupby("theme")["evaluation_id"].nunique().items()}
        if {"theme", "evaluation_id"}.issubset(query_frame.columns) else {}
    )
    formulation_column = "formulation_label" if "formulation_label" in query_frame else "formulation"
    formulation_query_counts = (
        {str(key): int(value) for key, value in
         query_frame.groupby(formulation_column)["evaluation_id"].nunique().items()}
        if {formulation_column, "evaluation_id"}.issubset(query_frame.columns) else {}
    )
    quorums = sorted(analysis["quorum"].dropna().unique()) if "quorum" in analysis else []
    if len(quorums) < 2:
        not_generated.append({"analysis": "quorum_sensitivity",
                              "reason": "only one distinct quorum is present; sensitivity is not estimable"})
    if "ranked_urls" not in scoped_frame:
        not_generated.append({"analysis": "ranking_overlap",
                              "reason": "ranked URL lists are absent from the persisted inputs"})
    elif "overlap" not in figure_families:
        not_generated.append({"analysis": "ranking_overlap", "reason": "not requested"})
    metadata_out = {
        **metadata,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "query_count": query_count,
        "theme_count": theme_count,
        "theme_query_counts": theme_query_counts,
        "formulation_query_counts": formulation_query_counts,
        "analysis_query_count": int(analysis["evaluation_id"].nunique()) if "evaluation_id" in analysis else 0,
        "analysis_theme_count": int(analysis["theme"].nunique()) if "theme" in analysis else 0,
        "analysis_rows": len(analysis), "all_rows": metadata.get("observed_result_rows", len(frame)),
        "selected_source_rows": len(scoped_frame),
        "timings_seconds": {
            **(metadata.get("timings_seconds") or {}),
            "analysis_seconds": analysis_seconds,
            "tables_seconds": tables_seconds,
            "plot_tasks": plot_timings,
        },
        "complete_query_configuration_groups": int(audit["complete"].sum()) if not audit.empty else 0,
        "partial_query_configuration_groups": int((~audit["complete"]).sum()) if not audit.empty else 0,
        "figure_formats": list(formats), "figures": generated, "not_generated": not_generated,
        "warnings": warnings,
        "selection": {
            "rankings": rankings,
            "seed_methods": seed_methods,
            "comparison_only_rankings": sorted(set(baselines) - set(rankings)),
            "paired_comparison_references": baselines,
            "figure_families": sorted(figure_families),
            "filters": filters,
            "include_partial": bool(include_partial),
            "runs_pooled": False,
        },
        "analysis_policy": {
            "runs_pooled": False, "partial_groups_in_headline_figures": False,
            "seed_independent_rankings": sorted(SEED_INDEPENDENT),
            "theme_macro": "mean queries within theme, then equal mean across themes",
            "uncertainty": (f"95% percentile bootstrap over themes; 1000 replicates; "
                            f"{theme_count} resampling units; descriptive, not a significance test"),
            "theme_resampling_units": theme_count,
            "primary_metrics": list(PRIMARY_METRICS),
            "paired_delta_baselines": list(baselines),
            "runtime": "ranking computation time; not total query latency",
            "oracle_metrics": "ceiling within the retrieved pool; not the full corpus",
            "metrics_protocol_note": "Do not pool with earlier ordered-prefix P/R/F1 results without protocol verification.",
        },
    }
    (output_dir / "manifest.json").write_text(json.dumps(metadata_out, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
    if progress_callback:
        progress_callback({"phase": "run_complete", "completed_tasks": task_total,
                           "total_tasks": task_total, "current_task": None})
    return metadata_out


def merge_ranking_lists(frame, analysis):
    """Join optional rank lists into the deduplicated complete-case analysis frame."""
    if "ranked_urls" not in frame:
        return analysis
    frame = frame.copy()
    frame["seed_label"] = np.where(frame["ranking"].isin(SEED_INDEPENDENT), "independent",
                                   frame["seed"].fillna("none"))
    key = ["evaluation_id", "preset", "quorum", "result_unit", "ranking", "seed_label"]
    lists = frame.sort_values("seq", na_position="last").drop_duplicates(key)[key + ["ranked_urls"]]
    return analysis.merge(lists, on=key, how="left", suffixes=("", "_rank_lists"))


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--run-id", action="append", help="Dashboard run ID; repeat to create separate output bundles.")
    selection.add_argument("--list-runs", action="store_true", help="List saved runs and exit.")
    selection.add_argument("--from-bundle", type=Path,
                           help="Render again from a prior bundle's normalized_results.csv and manifest.json (no DB access).")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--format", dest="formats", nargs="+", choices=("pdf", "png", "svg"),
                        default=("pdf", "png", "svg"))
    parser.add_argument("--include-partial", action="store_true",
                        help="Include partial groups in exploratory plots; complete groups remain the headline default.")
    parser.add_argument("--include-ranking-overlap", action="store_true",
                        help="Load saved ranked URLs and generate top-20 diversity heatmap.")
    parser.add_argument("--ranking", action="append", choices=sorted(SUPPORTED_RANKINGS),
                        help="Ranking method to include; repeat to select several (default: all).")
    parser.add_argument("--seed-method", action="append", choices=sorted(SUPPORTED_SEED_METHODS),
                        help="Graph seeding method to include; repeat to select several (default: all).")
    parser.add_argument("--figure-family", action="append", choices=sorted(FIGURE_FAMILIES),
                        help="Figure family to generate; repeat to select several.")
    parser.add_argument("--filter-theme", action="append", default=[],
                        help="Keep only this theme ID; repeat to select several.")
    parser.add_argument("--filter-formulation", action="append", default=[],
                        help="Keep only this query formulation; repeat to select several.")
    parser.add_argument("--filter-preset", action="append", default=[],
                        help="Keep only this preset; repeat to select several.")
    parser.add_argument("--filter-quorum", action="append", type=float, default=[],
                        help="Keep only this quorum; repeat to select several.")
    parser.add_argument("--filter-evaluation-id", action="append", default=[],
                        help="Keep only this evaluation/query ID; repeat to select several.")
    parser.add_argument("--progress-jsonl", action="store_true",
                        help="Emit structured progress events for background job consumers.")
    parser.add_argument("--baseline-ranking", action="append", default=None,
                        help="Reference method for paired-delta figures; repeat to compare several baselines (default: hybrid_max).")
    return parser.parse_args(argv)


def _list_runs(engine):
    query = text("SELECT run_id, created_at, dataset, state FROM evaluation_runs ORDER BY created_at DESC")
    with engine.connect() as connection:
        for row in connection.execute(query).mappings():
            state = _json_value(row["state"]) or {}
            progress = state.get("progress") or {}
            print(f"{row['run_id']}\t{state.get('status', 'unknown')}\t"
                  f"{progress.get('completed', 0)}/{progress.get('total', 0)}\t{row['dataset']}")


def _load_bundle(bundle_dir):
    bundle_dir = Path(bundle_dir)
    normalized_path = bundle_dir / "normalized_results.csv"
    manifest_path = bundle_dir / "manifest.json"
    if not normalized_path.is_file() or not manifest_path.is_file():
        raise ValueError(f"Expected normalized_results.csv and manifest.json in {bundle_dir}")
    metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
    metadata.setdefault("run_id", bundle_dir.name)
    frame = pd.read_csv(normalized_path)
    if "ranked_urls" in frame:
        def parse_ranked_urls(value):
            if isinstance(value, list):
                return value
            if pd.isna(value):
                return None
            try:
                parsed = _json_value(value)
                return parsed if isinstance(parsed, list) else ast.literal_eval(value)
            except (ValueError, SyntaxError):
                return None

        frame["ranked_urls"] = frame["ranked_urls"].map(parse_ranked_urls)
    return metadata, frame


def _create_db_engine():
    # Bundle rendering is intentionally offline; require configuration only for DB-backed runs.
    from config import POSTGRES_DSN  # noqa: PLC0415

    return create_engine(POSTGRES_DSN, pool_pre_ping=True)


def _progress_reporter(run_id, run_index, run_total):
    def report(event):
        payload = {"run_id": run_id, "run_index": run_index, "run_total": run_total, **event}
        print(PROGRESS_PREFIX + json.dumps(payload, ensure_ascii=False), file=sys.stderr, flush=True)

    return report


def _selection_kwargs(args):
    return {
        "rankings": args.ranking or sorted(SUPPORTED_RANKINGS),
        "seed_methods": args.seed_method or sorted(SUPPORTED_SEED_METHODS),
        "figure_families": args.figure_family or sorted(DEFAULT_FIGURE_FAMILIES),
        "filters": {
            "themes": args.filter_theme,
            "formulations": args.filter_formulation,
            "presets": args.filter_preset,
            "quorums": args.filter_quorum,
            "evaluation_ids": args.filter_evaluation_id,
        },
    }


def main(argv=None):
    args = _parse_args(argv)
    if args.list_runs:
        engine = _create_db_engine()
        _list_runs(engine)
        engine.dispose()
        return 0
    if args.from_bundle:
        metadata, frame = _load_bundle(args.from_bundle)
        run_id = str(metadata["run_id"])
        run_dir = args.output_dir / run_id
        progress_callback = _progress_reporter(run_id, 1, 1) if args.progress_jsonl else None
        if progress_callback:
            progress_callback({"phase": "starting"})
        print(f"Rendering saved bundle for {run_id}…", file=sys.stderr, flush=True)
        report = _figure_manifest(frame, metadata, run_dir, args.formats,
                                  include_partial=args.include_partial,
                                  include_ranking_overlap=args.include_ranking_overlap,
                                  baselines=args.baseline_ranking or ["hybrid_max"],
                                  progress_callback=progress_callback,
                                  **_selection_kwargs(args))
        print(f"{run_id}: {report['analysis_rows']} analysis rows; "
              f"{report['complete_query_configuration_groups']} complete groups; "
              f"{len(report['figures'])} figures -> {run_dir}", flush=True)
        return 0
    engine = _create_db_engine()
    selection = _selection_kwargs(args)
    baselines = args.baseline_ranking or ["hybrid_max"]
    load_baselines = baselines if "comparisons" in selection["figure_families"] else []
    include_ranking_lists = args.include_ranking_overlap or "overlap" in selection["figure_families"]
    for run_index, run_id in enumerate(args.run_id, start=1):
        progress_callback = (_progress_reporter(run_id, run_index, len(args.run_id))
                             if args.progress_jsonl else None)
        if progress_callback:
            progress_callback({"phase": "starting"})
        print(f"Reading persisted results for {run_id}…", file=sys.stderr)
        metadata, frame, audit_counts = load_run(
            engine, run_id, include_ranking_lists=include_ranking_lists,
            progress_callback=progress_callback,
            rankings=selection["rankings"], seed_methods=selection["seed_methods"],
            baselines=load_baselines, filters=selection["filters"],
        )
        run_dir = args.output_dir / run_id
        print(f"Generating figures for {run_id}…", file=sys.stderr, flush=True)
        report = _figure_manifest(frame, metadata, run_dir, args.formats,
                                  include_partial=args.include_partial,
                                  include_ranking_overlap=args.include_ranking_overlap,
                                  baselines=baselines,
                                  progress_callback=progress_callback,
                                  audit_counts=audit_counts,
                                  **selection)
        print(f"{run_id}: {report['analysis_rows']} analysis rows; "
              f"{report['complete_query_configuration_groups']} complete groups; "
              f"{len(report['figures'])} figures -> {run_dir}", flush=True)
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
