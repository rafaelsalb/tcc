import pandas as pd
import json
import matplotlib.pyplot as plt
import numpy as np

from scripts import generate_evaluation_figures as figures
from scripts.generate_evaluation_figures import (
    _event_to_row,
    audit_groups,
    bootstrap_theme_mean,
    filter_methods,
    filter_result_scope,
    audit_groups_from_counts,
    _load_bundle,
    _scope_predicate,
    _group_count_is_selected,
    prepare_analysis_frame,
    _figure_manifest,
)


def event(seq, evaluation_id, ranking, seed, score, quorum=0.3):
    return {
        "seq": seq,
        "evaluation_id": evaluation_id,
        "query": "test query",
        "query_formulation": "keyword",
        "result": {
            "ranking": ranking,
            "seed_method": seed,
            "preset": "rapido",
            "quorum": quorum,
            "result_unit": "articles",
            "retrieval_id": f"pool-{evaluation_id}-{quorum}",
            "computation_seconds": 1.0,
            "computation_reused": False,
            "retrieval_seconds": 2.0,
            "metrics": {"metrics": [
                {"k": k, "precision": score, "recall": score, "f1": score}
                for k in (1, 3, 5, 10, 20)
            ]},
            "ranking_metrics": {"mrr@20": score, "map@5": score, "map@10": score,
                                "map@20": score, "ndcg@5": score, "ndcg@10": score,
                                "ndcg@20": score},
            "coverage": {"reference_pool_recall": 0.8, "oracle_metrics": [
                {"k": 20, "precision": 1.0, "recall": 1.0, "f1": 1.0}
            ]},
            "diagnostics": {"query_entity_matched_count": 2, "effective_seed_method": seed},
            "ranked_urls": [f"https://example.test/{ranking}/{seed}/{i}" for i in range(20)],
        },
    }


def analysis_fixture():
    rows = []
    seq = 0
    for evaluation_id, score in (("theme_a__keyword", .2), ("theme_b__keyword", .6)):
        for ranking, value in (("hybrid_max", score), ("fused", score - .1)):
            for seed in ("hits", "query_entities"):
                seq += 1
                rows.append(_event_to_row(event(seq, evaluation_id, ranking, seed, value), "run-test",
                                          {evaluation_id: 20}, include_ranking_lists=True))
    frame = pd.DataFrame(rows)
    settings = {"rankings": ["hybrid_max", "fused"], "seed_methods": ["hits", "query_entities"]}
    return frame, settings


def test_metric_flattening_and_oracle_fields_are_preserved():
    row = _event_to_row(event(1, "theme__keyword", "fused", "query_entities", .4), "run",
                        {"theme__keyword": 20})
    assert row["f1@20"] == .4
    assert row["mrr@20"] == .4
    assert row["ndcg@20"] == .4
    assert row["oracle_f1@20"] == 1.0
    assert row["reference_pool_recall"] == .8
    assert row["query_entity_matched_count"] == 2


def test_completeness_audit_and_seed_independent_deduplication():
    frame, settings = analysis_fixture()
    audit = audit_groups(frame, settings)
    assert audit["complete"].all()
    prepared = prepare_analysis_frame(frame, audit)
    # Baseline duplicates across seeds collapse; graph seed comparisons remain.
    assert len(prepared) == 6
    assert (prepared["ranking"] == "hybrid_max").sum() == 2
    assert (prepared["ranking"] == "fused").sum() == 4


def test_compact_group_audit_matches_row_level_completeness_audit():
    frame, settings = analysis_fixture()
    keys = ["evaluation_id", "preset", "quorum", "result_unit", "ranking", "seed"]
    counts = frame.groupby(keys, dropna=False, as_index=False).agg(
        row_count=("ranking", "size"), formulation=("formulation", "first"),
    )
    row_audit = audit_groups(frame, settings).sort_values("evaluation_id").reset_index(drop=True)
    compact_audit = audit_groups_from_counts(counts, settings).sort_values("evaluation_id").reset_index(drop=True)
    columns = ["evaluation_id", "rows", "expected", "complete", "duplicates", "missing", "unexpected"]
    pd.testing.assert_frame_equal(row_audit[columns], compact_audit[columns])


def test_figure_scope_filters_rankings_seeds_and_dimensions():
    frame, settings = analysis_fixture()
    scoped = filter_result_scope(frame, {
        "themes": ["theme_a"], "formulations": ["keyword"],
        "presets": ["rapido"], "quorums": [.3],
        "evaluation_ids": ["theme_a__keyword"],
    })
    prepared = prepare_analysis_frame(scoped, audit_groups(frame, settings))
    selected = filter_methods(prepared, rankings=["fused"], seed_methods=["query_entities"])
    assert set(selected["evaluation_id"]) == {"theme_a__keyword"}
    assert set(selected["ranking"]) == {"fused"}
    assert set(selected["seed_label"]) == {"query_entities"}


def test_sql_scope_predicate_includes_selected_methods_and_only_restricts_graph_seeds():
    where, params, expanding = _scope_predicate(
        ["hybrid_max", "graph_hits"], ["query_entities"], {"themes": ["theme_a"]}
    )
    assert "payload->'result'->>'ranking' IN :selected_rankings" in where
    assert where.count("payload->'result'->>'ranking' IN :graph_rankings") == 1
    assert "NOT (payload->'result'->>'ranking' IN :graph_rankings) OR" in where
    assert params["selected_rankings"] == ["hybrid_max", "graph_hits"]
    assert params["selected_seeds"] == ["query_entities"]
    assert params["selected_themes"] == ["theme_a"]
    assert len(expanding) == 4


def test_incomplete_group_is_excluded_unless_explicitly_included():
    frame, settings = analysis_fixture()
    frame = frame[~((frame["evaluation_id"] == "theme_b__keyword")
                    & (frame["ranking"] == "fused") & (frame["seed"] == "hits"))]
    audit = audit_groups(frame, settings)
    assert audit["complete"].sum() == 1
    complete = prepare_analysis_frame(frame, audit)
    exploratory = prepare_analysis_frame(frame, audit, include_partial=True)
    assert set(complete["evaluation_id"]) == {"theme_a__keyword"}
    assert exploratory["partial_group"].any()


def test_theme_bootstrap_is_deterministic_and_single_theme_is_degenerate():
    assert bootstrap_theme_mean([.2, .4, .6], seed=7) == bootstrap_theme_mean([.2, .4, .6], seed=7)
    assert bootstrap_theme_mean([.25]) == (.25, .25, .25)


def test_formulation_display_labels_preserve_source_values():
    assert figures.FORMULATION_LABELS["keyword"] == "Palavras-chave"
    assert figures.FORMULATION_LABELS["specific_question"] == "Pergunta específica"
    frame, settings = analysis_fixture()
    prepared = prepare_analysis_frame(frame, audit_groups(frame, settings))
    assert set(prepared["formulation"]) == {"keyword"}
    assert set(prepared["formulation_label"]) == {"Palavras-chave"}
    assert set(prepared["theme"]) == {"theme_a", "theme_b"}
    assert set(prepared["theme_label"]) == {"theme_a", "theme_b"}


def test_known_theme_ids_are_translated_for_display_and_unknown_ids_are_preserved():
    assert figures.THEME_LABELS["banco_master"] == "Banco Master"
    assert figures.THEME_LABELS["eleicoes_brasil_2026"] == "Eleições no Brasil (2026)"
    frame, settings = analysis_fixture()
    frame["evaluation_id"] = frame["evaluation_id"].str.replace("theme_a", "banco_master")
    frame["theme"] = frame["theme"].replace("theme_a", "banco_master")
    prepared = prepare_analysis_frame(frame, audit_groups(frame, settings))
    assert "banco_master" in set(prepared["theme"])
    assert "Banco Master" in set(prepared["theme_label"])


def test_ranking_seed_and_metric_labels_are_academic_portuguese():
    assert figures._short_configuration("graph_fusion · semente=query_entities") == (
        "Híbrido + HITS (RRF) · entidades da consulta"
    )
    assert figures._short_configuration("ensemble_rrf · semente=louvain") == "Ensemble RRF · Louvain"
    assert figures._format_metric("precision") == "Precisão"
    assert figures._format_metric("ndcg@20") == "NDCG@20"


def test_formulation_sample_note_reports_unequal_query_counts():
    frame, _ = analysis_fixture()
    extra = frame.iloc[[0]].copy()
    extra["seq"] += 100
    extra["evaluation_id"] = "theme_c__unspecified"
    extra["theme"] = "theme_c"
    extra["formulation"] = "unspecified"
    frame = pd.concat([frame, extra], ignore_index=True)
    assert figures._formulation_sample_label(frame) == "n varia de 1 a 2 consultas por formulação"
    assert figures._short_formulation_label("Consulta de referência") == "Consulta ref."
    assert figures._short_formulation_label("Palavras-chave específicas") == "Palavras-chave esp."


def test_uniform_composition_uses_compact_summary_layout(monkeypatch, tmp_path):
    frame = pd.DataFrame({
        "evaluation_id": ["a__keyword", "a__question", "b__keyword", "b__question",
                           "c__keyword", "c__question"],
        "theme": ["a", "a", "b", "b", "c", "c"],
        "theme_label": ["Tema A", "Tema A", "Tema B", "Tema B", "Tema C", "Tema C"],
        "formulation_label": ["Palavras-chave", "Pergunta", "Palavras-chave", "Pergunta",
                              "Palavras-chave", "Pergunta"],
        "reference_count": [20] * 6,
    })
    captured = {}

    def capture(fig, directory, stem, formats):
        captured["size"] = fig.get_size_inches()
        captured["axes"] = fig.axes
        captured["text"] = [text.get_text() for ax in fig.axes for text in ax.texts]
        plt.close(fig)
        return [f"{stem}.png"]

    monkeypatch.setattr(figures, "_save", capture)
    assert figures._plot_composition(frame, tmp_path, ("png",)) == ["fig01_evaluation_composition.png"]
    assert captured["size"][0] < 13
    assert captured["size"][1] < 4.5
    assert "3 temas × 2 formulações" in captured["text"]
    assert "6 consultas" in captured["text"]


def test_runtime_frontier_labels_are_evenly_sampled_and_keep_endpoints():
    frontier = pd.DataFrame({
        "configuration": [f"config_{index}" for index in range(9)],
        "seconds": [index + 1 for index in range(9)],
    })
    selected = figures._runtime_frontier_label_configs(frontier, max_labels=4)
    assert len(selected) == 4
    assert "config_0" in selected
    assert "config_8" in selected
    assert selected == figures._runtime_frontier_label_configs(frontier, max_labels=4)


def test_figure_copy_is_portuguese_while_source_categories_remain_unchanged(monkeypatch, tmp_path):
    frame, settings = analysis_fixture()
    extra = frame.copy()
    extra["seq"] += 100
    extra["quorum"] = .7
    extra["retrieval_id"] = extra["retrieval_id"].astype(str) + "-q07"
    frame = pd.concat([frame, extra], ignore_index=True)
    audit = audit_groups(frame, settings)
    prepared = prepare_analysis_frame(frame, audit)
    visible_text = []

    def capture(fig, directory, stem, formats):
        for item in fig.texts:
            visible_text.append(item.get_text())
        for ax in fig.axes:
            visible_text.extend((ax.get_title(), ax.get_xlabel(), ax.get_ylabel()))
            visible_text.extend(label.get_text() for label in ax.get_xticklabels())
            visible_text.extend(label.get_text() for label in ax.get_yticklabels())
            visible_text.extend(item.get_text() for item in ax.texts)
            legend = ax.get_legend()
            if legend:
                visible_text.extend(item.get_text() for item in legend.get_texts())
        plt.close(fig)
        return []

    monkeypatch.setattr(figures, "_save", capture)
    plots = (
        figures._plot_headline_summary(prepared, tmp_path, ("png",)),
        figures._plot_composition(prepared, tmp_path, ("png",)),
        figures._plot_retrieval_ceiling(prepared, tmp_path, ("png",)),
        figures._plot_ranking_leaderboard(prepared, tmp_path, ("png",)),
        figures._plot_formulation_heatmaps(prepared, tmp_path, ("png",)),
        figures._plot_paired_deltas(prepared, tmp_path, ("png",), ["hybrid_max"]),
        figures._plot_seed_sensitivity(prepared, tmp_path, ("png",)),
        figures._plot_quorum_sensitivity(prepared, tmp_path, ("png",)),
        figures._plot_cutoff_profiles(prepared, tmp_path, ("png",)),
        figures._plot_ranking_cutoff_profiles(prepared, tmp_path, ("png",)),
        figures._plot_low_score_cdf(prepared, tmp_path, ("png",)),
        figures._plot_theme_heatmap(prepared, tmp_path, ("png",)),
        figures._plot_runtime_quality(prepared, tmp_path, ("png",)),
        figures._plot_graph_diagnostics(prepared, tmp_path, ("png",)),
        figures._plot_ranking_overlap(figures.merge_ranking_lists(frame, prepared), tmp_path, ("png",)),
    )
    assert all(result == [] for result in plots)
    assert any(text.startswith("Composição do conjunto de avaliação") for text in visible_text)
    assert "Palavras-chave" in visible_text
    assert any("2 temas / 2 consultas" in text for text in visible_text)
    assert any("n=2 consultas por formulação" in text for text in visible_text)
    assert any("IC bootstrap sobre 2 temas" in text for text in visible_text)
    assert any(text.startswith("Híbrido + PPR · entidades da consulta") for text in visible_text)
    assert "hybrid_max" not in visible_text
    assert not any("4 temas" in text or "16 consultas" in text for text in visible_text)
    forbidden_english = (
        "Evaluation queries", "Reference-set size", "Relevant references found",
        "Ranking quality", "Paired delta", "Sensitivity to", "Theme-macro",
        "Precision, recall", "Cumulative lower-tail", "Share of queries", "Mean top-20",
    )
    assert not any(phrase in text for phrase in forbidden_english for text in visible_text)


def test_figure_manifest_generates_expected_plots_and_audit(tmp_path):
    frame, settings = analysis_fixture()
    metadata = {"run_id": "run-test", "settings": settings, "state": {"status": "completed"},
                "dataset_snapshot_sha256": "fixture"}
    events = []
    report = _figure_manifest(frame, metadata, tmp_path, ("png",), True, True, ["hybrid_max"],
                              progress_callback=events.append)
    assert report["complete_query_configuration_groups"] == 2
    assert "fig03_ranking_quality_leaderboard.png" in report["figures"]
    assert "fig14_ranking_overlap.png" in report["figures"]
    assert "paired_method_deltas.csv" in {path.name for path in tmp_path.iterdir()}
    assert (tmp_path / "normalized_results.csv").exists()
    assert (tmp_path / "group_completeness.csv").exists()
    stored = json.loads((tmp_path / "manifest.json").read_text())
    assert stored["analysis_policy"]["runs_pooled"] is False
    assert not any("Partial rows were included" in warning for warning in stored["warnings"])
    assert stored["query_count"] == 2
    assert stored["theme_count"] == 2
    assert stored["theme_query_counts"] == {"theme_a": 1, "theme_b": 1}
    assert stored["formulation_query_counts"] == {"keyword": 2}
    assert stored["analysis_policy"]["theme_resampling_units"] == 2
    assert stored["timings_seconds"]["analysis_seconds"] >= 0
    assert stored["timings_seconds"]["tables_seconds"] >= 0
    assert stored["timings_seconds"]["plot_tasks"]
    assert all(seconds >= 0 for seconds in stored["timings_seconds"]["plot_tasks"].values())
    assert any(item["analysis"] == "quorum_sensitivity" for item in stored["not_generated"])
    assert len(stored["figures"]) == len(set(stored["figures"]))
    assert events[0]["phase"] == "analyzing"
    assert any(event["phase"] == "plotting" and event.get("current_task") for event in events)
    assert any(event.get("last_completed_task") and event.get("last_task_seconds", -1) >= 0
               for event in events)
    assert events[-1]["phase"] == "run_complete"
    assert events[-1]["completed_tasks"] == events[-1]["total_tasks"]


def test_compact_audit_counts_obey_selected_scope():
    counts = {"evaluation_id": "theme_a__query", "formulation": "keyword",
              "preset": "rapido", "quorum": "0.3", "ranking": "graph_hits",
              "seed": "query_entities", "row_count": 4}
    assert _group_count_is_selected(
        counts, ["graph_hits"], ["query_entities"],
        {"themes": ["theme_a"], "formulations": ["keyword"],
         "presets": ["rapido"], "quorums": [.3],
         "evaluation_ids": ["theme_a__query"]},
    )
    assert not _group_count_is_selected(
        counts, ["graph_hits"], ["louvain"], {"themes": ["theme_a"]},
    )
    assert not _group_count_is_selected(
        counts, ["graph_hits"], ["query_entities"], {"quorums": [.5]},
    )


def test_theme_difficulty_plot_records_matching_and_eligible_counts(tmp_path, monkeypatch):
    frame = pd.DataFrame([
        {"theme_label": "Tema raro", "matching_articles_count": 2,
         "eligible_articles_count": 100, "difficulty_score": np.log1p(2) / np.log1p(100)},
        {"theme_label": "Tema comum", "matching_articles_count": 80,
         "eligible_articles_count": 100, "difficulty_score": np.log1p(80) / np.log1p(100)},
    ])
    saved = []
    axis_limits = []
    def capture(fig, directory, name, formats):
        saved.append(name)
        axis_limits.append(fig.axes[0].get_xlim())
        return [name]
    monkeypatch.setattr(figures, "_save", capture)

    result = figures._plot_theme_difficulty(frame, tmp_path, ("png",))

    assert result == ["fig15_theme_difficulty"]
    assert saved == ["fig15_theme_difficulty"]
    assert axis_limits == [(0.0, 1.0)]
    csv = pd.read_csv(tmp_path / "theme_difficulty.csv").set_index("theme_label")
    assert csv.loc["Tema raro", "matching_articles_count"] == 2
    assert csv.loc["Tema raro", "eligible_articles_count"] == 100
    plt.close("all")


def test_theme_difficulty_figure_obeys_selected_theme_filter(tmp_path):
    frame, settings = analysis_fixture()
    frame["matching_articles_count"] = frame["theme"].map({"theme_a": 2, "theme_b": 80})
    frame["eligible_articles_count"] = 100
    frame["difficulty_score"] = np.log1p(frame["matching_articles_count"]) / np.log1p(frame["eligible_articles_count"])
    metadata = {"run_id": "run-theme-filter", "settings": settings,
                "state": {"status": "completed"}}

    report = _figure_manifest(
        frame, metadata, tmp_path, ("png",), False, False, [],
        figure_families=["theme"], filters={"themes": ["theme_a"]},
    )

    plotted = pd.read_csv(tmp_path / "theme_difficulty.csv")
    assert plotted["theme_label"].tolist() == ["theme_a"]
    performance = pd.read_csv(tmp_path / "theme_performance_by_difficulty.csv")
    assert set(performance["theme_label"]) == {"theme_a"}
    assert {"f1@20", "mrr@20", "ndcg@20"}.issubset(performance.columns)
    assert "fig16_theme_performance_matrix.png" in report["figures"]


def test_figure_manifest_records_selection_and_keeps_comparison_only_reference(tmp_path):
    frame, settings = analysis_fixture()
    metadata = {"run_id": "run-filtered", "settings": settings, "state": {"status": "completed"}}
    report = _figure_manifest(
        frame, metadata, tmp_path, ("png",), False, False, ["hybrid_max"],
        rankings=["fused"], seed_methods=["query_entities"],
        figure_families=["comparisons"],
        filters={"themes": ["theme_a"], "evaluation_ids": ["theme_a__keyword"]},
    )
    analysis = pd.read_csv(tmp_path / "analysis_results.csv")
    normalized = pd.read_csv(tmp_path / "normalized_results.csv")
    assert set(analysis["ranking"]) == {"fused"}
    assert set(analysis["seed_label"]) == {"query_entities"}
    assert set(normalized["ranking"]) == {"fused", "hybrid_max"}
    assert set(normalized["evaluation_id"]) == {"theme_a__keyword"}
    assert report["selection"]["rankings"] == ["fused"]
    assert report["selection"]["comparison_only_rankings"] == ["hybrid_max"]
    assert report["selection"]["filters"]["themes"] == ["theme_a"]
    assert any(name.startswith("fig05_paired_deltas") for name in report["figures"])


def test_figure_manifest_rejects_empty_filter_scope(tmp_path):
    frame, settings = analysis_fixture()
    metadata = {"run_id": "run-empty", "settings": settings}
    try:
        _figure_manifest(frame, metadata, tmp_path, ("png",), False, False, [],
                         filters={"themes": ["no_such_theme"]})
    except ValueError as error:
        assert "No results match" in str(error)
    else:
        raise AssertionError("expected empty-scope validation")


def test_graph_diagnostics_uses_numeric_counts_and_exports_both_entity_counts(monkeypatch, tmp_path):
    frame, _ = analysis_fixture()
    graph = frame[(frame["ranking"] == "fused") & (frame["seed"] == "query_entities")].copy()
    graph["seed_label"] = "query_entities"
    graph["query_entity_count"] = ["0", "7"]
    graph["query_entity_matched_count"] = ["0", "5"]
    graph["query_seed_fallback_reason"] = [None, None]
    repeated = graph.iloc[[0]].copy()
    missing = graph.iloc[[0]].copy()
    missing["query_entity_matched_count"] = None
    graph = pd.concat([graph, repeated, missing], ignore_index=True)
    captured = {}

    def capture(fig, directory, stem, formats):
        captured["axes"] = fig.axes
        captured["stem"] = stem
        plt.close(fig)
        return [f"{stem}.png"]

    monkeypatch.setattr(figures, "_save", capture)
    result = figures._plot_graph_diagnostics(graph, tmp_path, ("png",))
    assert result == ["fig13_graph_diagnostics.png"]
    assert captured["axes"][0].get_xlabel() == "Entidades extraídas da consulta"
    assert captured["axes"][0].get_ylabel() == "Entidades correspondidas no grafo"
    points = captured["axes"][0].collections[0]
    assert points.get_alpha() == .38
    assert points.get_sizes().tolist() == [24]
    offsets = points.get_offsets()
    assert len(offsets) == 3
    assert all(float(value).is_integer() for value in offsets.ravel())
    heatmap = next(ax for ax in captured["axes"] if ax.get_title().startswith("Frequência"))
    assert heatmap.get_xlabel() == captured["axes"][0].get_xlabel()
    assert heatmap.get_ylabel() == captured["axes"][0].get_ylabel()
    assert heatmap.get_ylim()[0] < heatmap.get_ylim()[1]
    counts = pd.read_csv(tmp_path / "graph_diagnostics.csv")["query_entity_matched_count"]
    assert counts.notna().sum() == 3
    assert counts.isna().sum() == 1


def test_runtime_quality_uses_log1p_axis_and_marks_pareto_frontier(monkeypatch, tmp_path):
    frame, settings = analysis_fixture()
    frame = prepare_analysis_frame(frame, audit_groups(frame, settings))
    frame["computation_seconds"] = [0.01, 0.02, 0.03, 1.0, 10.0, 51.0]
    frame["computation_reused"] = False
    captured = {}

    def capture(fig, directory, stem, formats):
        captured["axis"] = fig.axes[0]
        plt.close(fig)
        return [f"{stem}.png"]

    monkeypatch.setattr(figures, "_save", capture)
    figures._plot_runtime_quality(frame, tmp_path, ("png",))
    assert "log" in captured["axis"].get_xlabel()
    summary = pd.read_csv(tmp_path / "runtime_quality.csv")
    assert summary["pareto_frontier"].dtype == bool
    assert summary["annotated"].equals(summary["pareto_frontier"])
    assert any(line.get_label().startswith("Fronteira de Pareto") for line in captured["axis"].lines)


def test_retrieval_ceiling_adds_theme_formulation_heatmap(monkeypatch, tmp_path):
    frame, settings = analysis_fixture()
    prepared = prepare_analysis_frame(frame, audit_groups(frame, settings))
    captured = {}

    def capture(fig, directory, stem, formats):
        captured[stem] = fig
        return [f"{stem}.png"]

    monkeypatch.setattr(figures, "_save", capture)
    outputs = figures._plot_retrieval_ceiling(prepared, tmp_path, ("png",))
    assert outputs == ["fig02_retrieval_coverage_and_ceiling.png", "fig02_theme_formulation_values.png"]
    heatmap = captured["fig02_theme_formulation_values"].axes[0]
    assert heatmap.get_xlabel() == "Formulação"
    assert heatmap.get_ylabel() == "Tema"
    for fig in captured.values():
        plt.close(fig)


def test_composition_avoids_uniform_all_ones_heatmap(monkeypatch, tmp_path):
    frame, settings = analysis_fixture()
    prepared = prepare_analysis_frame(frame, audit_groups(frame, settings))
    captured = {}

    def capture(fig, directory, stem, formats):
        captured["fig"] = fig
        plt.close(fig)
        return []

    monkeypatch.setattr(figures, "_save", capture)
    figures._plot_composition(prepared, tmp_path, ("png",))
    axis = captured["fig"].axes[0]
    content = " ".join(text.get_text() for text in axis.texts)
    assert "1 consulta por combinação" in content
    assert not axis.collections


def test_low_score_plot_labels_reference_thresholds(monkeypatch, tmp_path):
    frame, settings = analysis_fixture()
    prepared = prepare_analysis_frame(frame, audit_groups(frame, settings))
    captured = {}

    def capture(fig, directory, stem, formats):
        captured["axis"] = fig.axes[0]
        plt.close(fig)
        return []

    monkeypatch.setattr(figures, "_save", capture)
    figures._plot_low_score_cdf(prepared, tmp_path, ("png",))
    labels = {text.get_text() for text in captured["axis"].texts}
    assert {"limiar 0,10", "limiar 0,20"}.issubset(labels)


def test_cutoff_figures_use_distinct_fig08_colors_and_split_fig09(monkeypatch, tmp_path):
    frame, settings = analysis_fixture()
    prepared = prepare_analysis_frame(frame, audit_groups(frame, settings))
    # Add the three independent baselines and enough graph rows to exercise both families.
    extra = []
    for ranking, color in (("rrf", .3), ("cross_encoder", .4), ("graph_fusion", .2)):
        for evaluation_id in prepared["evaluation_id"].unique():
            row = prepared.iloc[0].copy()
            row["ranking"] = ranking
            row["configuration"] = ranking + " · semente=query_entities"
            row["evaluation_id"] = evaluation_id
            row["theme"] = evaluation_id.split("__")[0]
            for metric in ("precision", "recall", "f1"):
                for k in figures.F1_CUTOFFS:
                    row[f"{metric}@{k}"] = color
            for metric in ("map", "ndcg"):
                for k in figures.RANKING_CUTOFFS:
                    row[f"{metric}@{k}"] = color
            extra.append(row)
    prepared = pd.concat([prepared, pd.DataFrame(extra)], ignore_index=True)
    prepared.loc[prepared["ranking"].isin(figures.GRAPH_RANKINGS), "seed_label"] = "query_entities"
    captured = {}

    def capture(fig, directory, stem, formats):
        captured[stem] = fig
        return []

    monkeypatch.setattr(figures, "_save", capture)
    figures._plot_cutoff_profiles(prepared, tmp_path, ("png",))
    figures._plot_ranking_cutoff_profiles(prepared, tmp_path, ("png",))
    assert {"fig09_map_ndcg_cutoff_profiles", "supp_graph_map_ndcg_cutoff_profiles"}.issubset(captured)
    retrieval_axis = captured["fig08_retrieval_cutoff_profiles"].axes[0]
    colored_lines = [line for line in retrieval_axis.lines if not line.get_label().startswith("_")]
    colors = {line.get_color() for line in colored_lines}
    assert {"#0072B2", "#D55E00", "#009E73"}.issubset(colors)
    assert captured["fig09_map_ndcg_cutoff_profiles"].axes[0].get_ylim() == \
        captured["supp_graph_map_ndcg_cutoff_profiles"].axes[0].get_ylim()
    for fig in captured.values():
        plt.close(fig)


def test_ranking_overlap_uses_viridis(monkeypatch, tmp_path):
    frame, settings = analysis_fixture()
    prepared = prepare_analysis_frame(frame, audit_groups(frame, settings))
    merged = figures.merge_ranking_lists(frame, prepared)
    captured = {}

    def capture(fig, directory, stem, formats):
        captured["cmap"] = fig.axes[0].collections[0].cmap.name
        captured["title"] = fig.axes[0].get_title()
        captured["xlabel"] = fig.axes[0].get_xlabel()
        plt.close(fig)
        return []

    monkeypatch.setattr(figures, "_save", capture)
    figures._plot_ranking_overlap(merged, tmp_path, ("png",))
    assert captured["cmap"] == "viridis"
    assert captured["title"].startswith("Sobreposição dos 20 primeiros resultados")
    assert captured["xlabel"] == "Configuração do método"


def test_bundle_loader_reads_saved_csv_without_database(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"run_id": "saved-run", "settings": {}}))
    pd.DataFrame([{"evaluation_id": "theme__query", "query_entity_matched_count": 5,
                   "ranked_urls": ["https://example.test/a", "https://example.test/b"]}]).to_csv(
        tmp_path / "normalized_results.csv", index=False
    )
    metadata, frame = _load_bundle(tmp_path)
    assert metadata["run_id"] == "saved-run"
    assert frame.loc[0, "query_entity_matched_count"] == 5
    assert frame.loc[0, "ranked_urls"] == ["https://example.test/a", "https://example.test/b"]


def test_paired_delta_progress_reports_baseline_subtasks(tmp_path):
    frame, settings = analysis_fixture()
    prepared = prepare_analysis_frame(frame, audit_groups(frame, settings))
    events = []
    figures._plot_paired_deltas(prepared, tmp_path, ("png",), ["hybrid_max", "rrf"],
                                progress_callback=events.append)
    assert events[0]["subtask_completed"] == 0
    assert events[0]["current_subtask"] == "hybrid_max"
    assert events[-1]["subtask_completed"] == 2
    assert events[-1]["current_subtask"] is None


def test_paired_deltas_use_one_shared_axis_label(monkeypatch, tmp_path):
    frame, settings = analysis_fixture()
    prepared = prepare_analysis_frame(frame, audit_groups(frame, settings))
    captured = []

    def capture(fig, directory, stem, formats):
        captured.append((fig, stem))
        return []

    monkeypatch.setattr(figures, "_save", capture)
    figures._plot_paired_deltas(prepared, tmp_path, ("png",), ["hybrid_max"])

    assert captured
    for fig, _ in captured:
        assert all(ax.get_xlabel() == "" for ax in fig.axes[:3])
        assert fig._supxlabel.get_text() == (
            "Diferença pareada (método − referência); valores positivos favorecem o método"
        )
        plt.close(fig)


def test_plot_layout_helpers_adapt_to_density():
    assert figures._heatmap_annotations_readable((5, 6))
    assert not figures._heatmap_annotations_readable((10, 9))
    assert not figures._heatmap_annotations_readable((23, 9))
    assert figures._sparse_plot_height(4) < figures._sparse_plot_height(15)
    assert figures._sparse_plot_height(4) < 5


def test_cutoff_profiles_use_ranking_line_styles_and_adaptive_bands(monkeypatch, tmp_path):
    frame, settings = analysis_fixture()
    prepared = prepare_analysis_frame(frame, audit_groups(frame, settings))
    captured = {}

    def capture(fig, directory, stem, formats):
        captured[stem] = fig
        return []

    monkeypatch.setattr(figures, "_save", capture)
    figures._plot_cutoff_profiles(prepared, tmp_path, ("png",))
    figures._plot_ranking_cutoff_profiles(prepared, tmp_path, ("png",))

    assert figures._uncertainty_band_alpha(6) < figures._uncertainty_band_alpha(2)
    graph_axis = captured["supp_graph_method_cutoff_profiles"].axes[0]
    graph_line = next(line for line in graph_axis.lines if line.get_label() != "_child0")
    assert graph_line.get_linestyle() == figures._ranking_linestyle("fused")
    for fig in captured.values():
        plt.close(fig)
