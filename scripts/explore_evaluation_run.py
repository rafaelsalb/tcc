"""Create exploratory visualizations from one persisted evaluation-run bundle.

Example:
    uv run python scripts/explore_evaluation_run.py
    uv run python scripts/explore_evaluation_run.py --input-dir PATH --output-dir PATH

Input is the analysis_results.csv exported by generate_evaluation_figures.py.
Seeded ranking rows are averaged within query before method-level comparisons.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "0cca98bd889e49dd89b3993a6407bff5"
DEFAULT_INPUT = (
    ROOT / "resultados" / "figuras" / "manual-0cca98bd-20261020T011425Z-2e13bef7"
    / "figures" / RUN_ID / "analysis_results.csv"
)
DEFAULT_OUTPUT = ROOT / "resultados" / "eda" / RUN_ID

RANKING_LABELS = {
    "hybrid_max": "Híbrido (máximo)",
    "rrf": "RRF",
    "cross_encoder": "Cross-encoder",
    "ensemble_rrf": "Ensemble RRF",
    "fused": "Fusão + PPR",
    "graph_fusion": "Fusão + HITS",
    "graph_hits_cross_encoder": "HITS + cross-encoder",
    "graph_salsa": "SALSA",
}
SEED_LABELS = {
    "hits": "HITS",
    "louvain": "Louvain",
    "ppr_top10": "PPR top 10%",
    "query_entities": "Entidades da consulta",
}
PALETTE = {
    "hybrid_max": "#697782",
    "rrf": "#9AA4AC",
    "cross_encoder": "#404B55",
    "ensemble_rrf": "#E69F00",
    "fused": "#0072B2",
    "graph_fusion": "#009E73",
    "graph_hits_cross_encoder": "#CC79A7",
    "graph_salsa": "#D55E00",
}
THEME_LABELS = {
    "acordo_mercosul_uniao_europeia": "Acordo Mercosul–UE",
    "eleicoes_brasil_2026": "Eleições 2026",
    "gripe_aviaria_brasil": "Gripe aviária",
    "guerra_israel_ira_2025": "Israel–Irã",
    "mundial_clubes_2025": "Mundial de Clubes",
    "brics_rio_2025": "BRICS no Rio",
    "concurso_nacional_unificado_2025": "Concurso Nacional Unificado",
    "crise_venezuela_2026": "Crise na Venezuela",
    "dengue_brasil_2025_2026": "Dengue",
    "enem_2025": "ENEM",
    "gaza_2025_2026": "Gaza",
    "imposto_renda_2026": "Imposto de Renda",
    "libertadores_2025": "Libertadores",
    "pix_brasil": "Pix",
    "queda_aviao_air_india_2025": "Queda do voo Air India",
    "banco_master": "Banco Master",
    "cao_orelha": "Cão Orelha",
    "caso_benicio": "Caso Benício",
    "cop30_negociacoes": "Negociações da COP30",
    "descontos_inss": "Descontos do INSS",
    "julgamento_nucleo_golpe": "Núcleo da tentativa de golpe",
    "juliana_marins": "Juliana Marins",
    "metanol_bebidas": "Metanol em bebidas",
    "operacao_contencao": "Operação Contenção",
    "tarifaco_eua_brasil": "Tarifaço EUA–Brasil",
    "rio_security_operation": "Segurança no Rio",
}
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


def _args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT,
                        help="analysis_results.csv from the run's figure bundle")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def _save(fig, output_dir, stem):
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"{stem}.{suffix}", dpi=240, bbox_inches="tight",
                    facecolor="white")
    plt.close(fig)


def _theme_label(theme):
    return THEME_LABELS.get(theme, str(theme).replace("_", " ").capitalize())


def _prepare(raw):
    needed = {"run_id", "evaluation_id", "theme", "formulation", "ranking", "seed_label",
              "f1@20", "mrr@20", "ndcg@20", "computation_seconds"}
    missing = needed - set(raw.columns)
    if missing:
        raise ValueError(f"Input is missing required columns: {', '.join(sorted(missing))}")
    found_runs = set(raw["run_id"].dropna().astype(str))
    if found_runs != {RUN_ID}:
        raise ValueError(f"Expected run {RUN_ID}, found: {sorted(found_runs)}")

    # Seed variants are experimental configurations of the same query/method.
    # Average them first so every query contributes one observation per ranking.
    query_method = (raw.groupby(["evaluation_id", "theme", "formulation", "ranking"],
                                as_index=False, dropna=False)
                   .agg(f1=("f1@20", "mean"), mrr=("mrr@20", "mean"),
                        ndcg=("ndcg@20", "mean"),
                        computation_seconds=("computation_seconds", "median")))
    query_method["ranking_label"] = query_method["ranking"].map(RANKING_LABELS).fillna(
        query_method["ranking"])
    query_method["theme_label"] = query_method["theme"].map(_theme_label)

    theme_method = (query_method.groupby(["theme", "theme_label", "ranking", "ranking_label"],
                                         as_index=False)
                    .agg(f1=("f1", "mean"), mrr=("mrr", "mean"),
                         ndcg=("ndcg", "mean"),
                         median_computation_seconds=("computation_seconds", "median"),
                         query_count=("evaluation_id", "nunique")))
    # Equal weighting of themes, matching the thesis analysis convention.
    ranking_summary = (theme_method.groupby(["ranking", "ranking_label"], as_index=False)
                       .agg(f1_macro=("f1", "mean"), mrr_macro=("mrr", "mean"),
                            ndcg_macro=("ndcg", "mean"),
                            median_computation_seconds=("median_computation_seconds", "median"),
                            themes=("theme", "nunique")))
    ranking_summary = ranking_summary.sort_values("f1_macro", ascending=False)
    return query_method, theme_method, ranking_summary


def _plot_coverage(raw, output_dir):
    queries = raw[["evaluation_id", "theme", "formulation"]].drop_duplicates()
    theme_counts = queries.groupby("theme").size().sort_values()
    formulation_counts = queries["formulation"].value_counts().sort_values()
    fig, axes = plt.subplots(1, 2, figsize=(15, 9), gridspec_kw={"width_ratios": [1.55, 1]})
    axes[0].barh([_theme_label(value) for value in theme_counts.index], theme_counts.values,
                 color="#0072B2")
    axes[0].set_title("Consultas avaliadas por tema")
    axes[0].set_xlabel("Número de consultas")
    axes[0].set_ylabel("")
    axes[0].bar_label(axes[0].containers[0], padding=3, fontsize=8)
    axes[0].set_xlim(0, max(theme_counts.values) * 1.18)

    axes[1].barh([FORMULATION_LABELS.get(value, str(value).replace("_", " ").capitalize())
                  for value in formulation_counts.index], formulation_counts.values,
                 color="#009E73")
    axes[1].set_title("Composição por formulação")
    axes[1].set_xlabel("Número de consultas")
    axes[1].set_ylabel("")
    axes[1].bar_label(axes[1].containers[0], padding=3, fontsize=8)
    axes[1].set_xlim(0, max(formulation_counts.values) * 1.18)
    fig.suptitle("Cobertura do conjunto avaliado", fontsize=16, fontweight="bold")
    fig.tight_layout()
    _save(fig, output_dir, "fig01_evaluation_coverage")


def _plot_f1_distribution(query_method, ranking_summary, output_dir):
    order = ranking_summary["ranking"].tolist()
    data = query_method.copy()
    fig, ax = plt.subplots(figsize=(12, 7))
    boxes = ax.boxplot([data.loc[data["ranking"].eq(ranking), "f1"].dropna()
                        for ranking in order],
                       vert=False, patch_artist=True, showfliers=False, widths=0.68,
                       medianprops={"color": "#202830", "linewidth": 1.8},
                       whiskerprops={"color": "#7C8992"},
                       capprops={"color": "#7C8992"})
    for patch, ranking in zip(boxes["boxes"], order):
        patch.set_facecolor(PALETTE.get(ranking, "#7A8793"))
        patch.set_alpha(0.78)
    ax.set_yticks(range(1, len(order) + 1),
                  [RANKING_LABELS.get(ranking, ranking) for ranking in order])
    ax.invert_yaxis()
    ax.set_xlim(0, 0.55)
    ax.set_xlabel("F1@20 por consulta (média entre sementes quando aplicável)")
    ax.set_ylabel("")
    ax.set_title("Distribuição do F1@20 por método", loc="left", fontweight="bold")
    ax.grid(axis="x", alpha=0.25)
    ax.text(0, -0.14, "Cada caixa resume até 201 consultas; extremos foram ocultados para legibilidade.",
            transform=ax.transAxes, fontsize=9, color="#555E65")
    fig.tight_layout()
    _save(fig, output_dir, "fig02_f1_distribution")


def _plot_theme_heatmap(theme_method, ranking_summary, output_dir):
    order = ranking_summary["ranking"].tolist()
    matrix = theme_method.pivot(index="theme_label", columns="ranking", values="f1")[order]
    theme_order = matrix.mean(axis=1).sort_values(ascending=False).index
    matrix = matrix.loc[theme_order]
    fig, ax = plt.subplots(figsize=(14, 10))
    sns.heatmap(matrix, cmap="YlGnBu", vmin=0, vmax=0.5, annot=True, fmt=".2f",
                linewidths=0.35, linecolor="white", cbar_kws={"label": "F1@20 médio"},
                annot_kws={"fontsize": 8}, ax=ax)
    ax.set_xticklabels([RANKING_LABELS.get(value, value) for value in order],
                       rotation=35, ha="right")
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_title("F1@20 por tema e método", loc="left", fontweight="bold", pad=14)
    fig.tight_layout()
    _save(fig, output_dir, "fig03_theme_method_heatmap")


def _plot_seed_heatmap(raw, output_dir):
    graph_rankings = ["fused", "graph_fusion", "graph_hits_cross_encoder", "graph_salsa"]
    data = raw[raw["ranking"].isin(graph_rankings)].copy()
    # Average query scores within each theme before the equal-theme macro mean.
    query_seed = (data.groupby(["evaluation_id", "theme", "ranking", "seed_label"],
                               as_index=False)
                 .agg(f1=("f1@20", "mean")))
    theme_seed = query_seed.groupby(["theme", "ranking", "seed_label"], as_index=False)["f1"].mean()
    macro = theme_seed.groupby(["ranking", "seed_label"])["f1"].mean().unstack("seed_label")
    macro = macro.reindex(index=graph_rankings,
                          columns=["hits", "louvain", "ppr_top10", "query_entities"])
    macro.index = [RANKING_LABELS.get(value, value) for value in macro.index]
    macro.columns = [SEED_LABELS.get(value, value) for value in macro.columns]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    sns.heatmap(macro, cmap="YlOrBr", vmin=0, vmax=0.3, annot=True, fmt=".3f",
                linewidths=0.5, linecolor="white", cbar_kws={"label": "F1@20 médio"}, ax=ax)
    ax.set_xlabel("Método de semente")
    ax.set_ylabel("")
    ax.set_title("Sensibilidade dos métodos de grafo à semente", loc="left",
                 fontweight="bold", pad=14)
    fig.tight_layout()
    _save(fig, output_dir, "fig04_graph_seed_heatmap")


def _plot_runtime_quality(ranking_summary, output_dir):
    fig, ax = plt.subplots(figsize=(11, 7))
    for row in ranking_summary.itertuples(index=False):
        seconds = max(float(row.median_computation_seconds), 0.0005)
        ax.scatter(seconds, row.f1_macro, s=95, color=PALETTE.get(row.ranking, "#7A8793"),
                   edgecolor="white", linewidth=0.8, zorder=3)
        label = RANKING_LABELS.get(row.ranking, row.ranking)
        offsets = {
            "hybrid_max": (8, 8, "left"), "rrf": (8, -17, "left"),
            "cross_encoder": (8, -10, "left"), "ensemble_rrf": (8, 9, "left"),
            "fused": (10, -20, "left"), "graph_fusion": (8, 9, "left"),
            "graph_hits_cross_encoder": (-10, 13, "right"),
            "graph_salsa": (8, -14, "left"),
        }
        dx, dy, alignment = offsets.get(row.ranking, (7, 7, "left"))
        ax.annotate(label, (seconds, row.f1_macro), xytext=(dx, dy),
                    textcoords="offset points", ha=alignment, fontsize=9)
    ax.set_xscale("log")
    ax.set_ylim(0, max(0.3, ranking_summary["f1_macro"].max() + 0.06))
    ax.set_xlabel("Tempo de computação do ranking por consulta (s; escala log)")
    ax.set_ylabel("F1@20 macro por tema")
    ax.set_title("Qualidade e custo de ranking", loc="left", fontweight="bold")
    ax.grid(alpha=0.25, which="both")
    ax.text(0, -0.16,
            "Tempos são medianas por tema; não representam latência fim a fim da busca.",
            transform=ax.transAxes, fontsize=9, color="#555E65")
    fig.tight_layout()
    _save(fig, output_dir, "fig05_quality_runtime")


def _write_report(raw, query_method, ranking_summary, input_path, output_dir):
    query_rows = raw[["evaluation_id", "theme", "formulation"]].drop_duplicates()
    ref_counts = raw[["evaluation_id", "reference_count"]].drop_duplicates("evaluation_id")["reference_count"]
    best = ranking_summary.iloc[0]
    worst = ranking_summary.iloc[-1]
    theme_counts = query_rows.groupby("theme").size()
    lines = [
        "# EDA — execução 0cca98",
        "",
        f"- Fonte: `{input_path.relative_to(ROOT) if input_path.is_relative_to(ROOT) else input_path}`",
        f"- Resultados analisados: {len(raw):,} linhas; {query_rows.evaluation_id.nunique()} consultas; "
        f"{query_rows.theme.nunique()} temas; {raw.ranking.nunique()} métodos.",
        f"- Consultas por tema: {theme_counts.min()}–{theme_counts.max()} "
        f"(mediana {theme_counts.median():.0f}); referências relevantes por consulta: "
        f"mediana {ref_counts.median():.0f}.",
        "- Agregação: variantes de semente são primeiro resumidas dentro da consulta; "
        "comparações macro dão o mesmo peso a cada tema.",
        "",
        "## Observações descritivas",
        "",
        f"- Maior F1@20 macro por tema: **{best.ranking_label}** "
        f"({best.f1_macro:.3f}; MRR {best.mrr_macro:.3f}; NDCG {best.ndcg_macro:.3f}).",
        f"- Menor F1@20 macro por tema: **{worst.ranking_label}** ({worst.f1_macro:.3f}).",
        "- O mapa de calor mostra variação importante entre temas; rankings que se destacam "
        "na média não lideram necessariamente em todos os temas.",
        "- O gráfico de sementes compara as quatro estratégias nos métodos de grafo; "
        "diferenças são descritivas e não constituem teste de significância.",
        "- O custo do cross-encoder é muito superior ao dos demais métodos nesta execução; "
        "o eixo temporal usa escala logarítmica.",
        "",
        "## Limitações de interpretação",
        "",
        "- Trata-se de uma análise exploratória de uma única execução, com quorum 0,3, "
        "preset `rapido` e resultados em artigos.",
        "- F1@20 é calculado sobre os 20 primeiros resultados; tempo de ranking não é "
        "latência total (busca/recuperação excluídas).",
        "- Médias e distribuições são descritivas; não inferir causalidade ou significância estatística.",
        "",
        "## Figuras",
        "",
        "1. `fig01_evaluation_coverage` — composição das consultas por tema e formulação.",
        "2. `fig02_f1_distribution` — distribuição de F1@20 por método, com sementes agregadas.",
        "3. `fig03_theme_method_heatmap` — heterogeneidade de desempenho por tema.",
        "4. `fig04_graph_seed_heatmap` — sensibilidade dos métodos de grafo às sementes.",
        "5. `fig05_quality_runtime` — relação exploratória entre F1@20 e tempo de ranking.",
    ]
    (output_dir / "eda_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    args = _args(argv)
    if not args.input.is_file():
        raise FileNotFoundError(f"Analysis CSV not found: {args.input}")
    raw = pd.read_csv(args.input)
    query_method, theme_method, ranking_summary = _prepare(raw)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    query_method.to_csv(args.output_dir / "query_method_summary.csv", index=False)
    theme_method.to_csv(args.output_dir / "theme_method_summary.csv", index=False)
    ranking_summary.to_csv(args.output_dir / "ranking_summary.csv", index=False)
    _plot_coverage(raw, args.output_dir)
    _plot_f1_distribution(query_method, ranking_summary, args.output_dir)
    _plot_theme_heatmap(theme_method, ranking_summary, args.output_dir)
    _plot_seed_heatmap(raw, args.output_dir)
    _plot_runtime_quality(ranking_summary, args.output_dir)
    _write_report(raw, query_method, ranking_summary, args.input.resolve(), args.output_dir)

    manifest = {
        "run_id": RUN_ID,
        "source_csv": str(args.input.resolve()),
        "output_dir": str(args.output_dir.resolve()),
        "analysis_rows": int(len(raw)),
        "queries": int(raw["evaluation_id"].nunique()),
        "themes": int(raw["theme"].nunique()),
        "rankings": sorted(raw["ranking"].dropna().unique().tolist()),
        "aggregation": "mean seed variants within query; equal-theme macro averages for ranking comparisons",
        "figures": [
            "fig01_evaluation_coverage", "fig02_f1_distribution",
            "fig03_theme_method_heatmap", "fig04_graph_seed_heatmap",
            "fig05_quality_runtime",
        ],
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved 5 EDA figures and summary to {args.output_dir}")
    print(ranking_summary[["ranking_label", "f1_macro", "mrr_macro", "ndcg_macro",
                           "median_computation_seconds"]].round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
