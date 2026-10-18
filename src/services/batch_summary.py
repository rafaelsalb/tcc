"""Incremental metric aggregates for live batch reports, without retaining rankings."""

import json
import os
from pathlib import Path
import tempfile


GRAPH_RANKINGS = {"ppr", "fused", "mmr", "graph_rwr", "graph_hits", "graph_salsa",
                  "graph_path", "graph_walk", "graph_fusion", "graph_hits_cross_encoder", "ensemble_rrf"}


def summary_paths(json_path):
    return json_path.with_suffix(".summary.md"), json_path.with_suffix(".summary.json")


class LiveSummary:
    def __init__(self, ks):
        self.ks = ks
        self.completed = 0
        self.groups = {name: {} for name in (
            "overall", "themes", "query_structures", "parameter_sets", "rankings", "seeding_methods", "stages")}

    def add(self, item, result):
        # Older comparison checkpoints may contain multiple rows in a record.
        for comparison in result.get("comparisons", [result]):
            row = {**result, **comparison}
            if "comparisons" in result:
                row["ranking"] = comparison.get("ranking", comparison["stage"])
                row["mode"] = "compare"
            self._add_row(item, row)

    def _add_row(self, item, row):
        self.completed += 1
        stage = row.get("stage", "ppr")
        ranking = row.get("ranking", stage)
        seed = row.get("seed_method", "none")
        values = {}
        for prefix, metrics in (("", row["metrics"]["metrics"]),
                                ("oracle_", row.get("coverage", {}).get("oracle_metrics", []))):
            for metric in metrics:
                for name in ("precision", "recall", "f1"):
                    values[f"{prefix}{name}@{metric['k']}"] = metric[name]
        for name in ("reference_pool_recall", "reference_in_pool"):
            if name in row.get("coverage", {}):
                values[name] = row["coverage"][name]
        values.update(row.get("ranking_metrics", {}))
        dimensions = {
            "overall": {"scope": "all saved rows"},
            "themes": {"theme": item["id"].split("__", 1)[0]},
            "query_structures": {"query_formulation": item.get("query_formulation", "unspecified")},
            "parameter_sets": {key: row.get(key) for key in (
                "mode", "stage", "ranking", "seed_method", "preset", "quorum", "limit", "top_k", "result_unit")},
            "rankings": {"ranking": ranking},
        }
        # Seed-independent rankings must not influence the seed leaderboard.
        if ranking in GRAPH_RANKINGS and seed not in ("none", "paired"):
            dimensions["seeding_methods"] = {"seed_method": seed}
        # stage=ppr is just the API dispatch path in ordinary ranking mode.
        # Compare actual stage outputs only when explicitly requested.
        if row.get("mode") == "compare" or ("mode" not in row and row.get("stage") in ("lexical", "hybrid", "fused")):
            dimensions["stages"] = {"stage": stage}
        for dimension, parameters in dimensions.items():
            key = json.dumps(parameters, sort_keys=True)
            group = self.groups[dimension].setdefault(key, {
                "parameters": parameters, "rows": 0, "queries": set(), "sums": {}, "counts": {}})
            group["rows"] += 1
            group["queries"].add(item["id"])
            for name, value in values.items():
                group["sums"][name] = group["sums"].get(name, 0.0) + value
                group["counts"][name] = group["counts"].get(name, 0) + 1

    def snapshot(self, completed, total, status):
        groups = {}
        for dimension, entries in self.groups.items():
            groups[dimension] = [{
                "parameters": group["parameters"], "rows": group["rows"],
                "queries": len(group["queries"]),
                "means": {name: value / group["counts"][name] for name, value in group["sums"].items()},
                "metric_counts": group["counts"],
            } for group in entries.values()]
            groups[dimension].sort(key=lambda row: (
                -row["means"].get("f1@20", 0), json.dumps(row["parameters"], sort_keys=True)))
        return {"status": status, "completed_results": completed, "total_results": total,
                "summarized_rows": self.completed, "ks": list(self.ks), "sorted_by": "mean f1@20 descending",
                "groups": groups}

    def markdown(self, report):
        lines = ["# Resumo ao vivo da avaliação", "",
                 f"Status: **{report['status']}** — **{report['completed_results']}/{report['total_results']}** resultados salvos.",
                 f"Linhas agregadas: {report['summarized_rows']}.", "",
                 "Médias por linha salva; todos os grupos são listados em ordem de F1@20 decrescente. "
                 "Durante a execução, grupos podem ter coberturas diferentes: compare também linhas e consultas.", "",
                 "O tema é inferido do prefixo do ID antes de `__`. Seeds são comparadas somente em PPR/fusão/MMR. "
                 "Etapas são comparadas somente nas linhas de `compare`, não pelo caminho de execução `stage=ppr`.", "",
                  "P@k/R@k/F1@k usam o conjunto completo de URLs relevantes. O oráculo é o teto para o pool retornado, "
                 "não para todo o corpus. O JSON acompanhante inclui todas as médias e contagens por métrica.", ""]
        titles = {"overall": "Geral", "themes": "Temas", "query_structures": "Estruturas de consulta",
                  "parameter_sets": "Conjuntos de parâmetros", "rankings": "Rankings",
                  "seeding_methods": "Métodos de seed", "stages": "Etapas"}
        for dimension, entries in report["groups"].items():
            lines += [f"## {titles[dimension]}", ""]
            if not entries:
                lines += ["Sem resultados aplicáveis nesta execução.", ""]
                continue
            for prefix, title in (("", "Métricas observadas"), ("oracle_", "Métricas oráculo")):
                lines += [f"### {title}", "",
                          "| Parâmetros | Linhas | Consultas | " + " | ".join(f"{name}@{k}" for k in self.ks for name in ("P", "R", "F1")) + " |",
                          "|---|---:|---:|" + "---:|" * (len(self.ks) * 3)]
                for entry in entries:
                    label = ", ".join(f"{key}={value}" for key, value in entry["parameters"].items())
                    label = label.replace("|", "\\|").replace("\n", " ")
                    cells = [f"{100 * entry['means'][prefix + name + '@' + str(k)]:.2f}%"
                             if prefix + name + '@' + str(k) in entry["means"] else "—"
                             for k in self.ks for name in ("precision", "recall", "f1")]
                    lines.append(f"| {label} | {entry['rows']} | {entry['queries']} | " + " | ".join(cells) + " |")
                lines.append("")
            lines += ["### Métricas de ranking (referência completa)", "",
                      "MRR@20, MAP@k e NDCG@k usam o conjunto completo de URLs relevantes, "
                      "sem o prefixo editorial `relevant_urls[:k]`.", "",
                      "| Parâmetros | Linhas | Consultas | MRR@20 | MAP@5 | MAP@10 | MAP@20 | NDCG@5 | NDCG@10 | NDCG@20 |",
                      "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
            ranking_metric_names = ("mrr@20", "map@5", "map@10", "map@20", "ndcg@5", "ndcg@10", "ndcg@20")
            for entry in entries:
                label = ", ".join(f"{key}={value}" for key, value in entry["parameters"].items())
                label = label.replace("|", "\\|").replace("\n", " ")
                cells = [f"{100 * entry['means'][name]:.2f}%" if name in entry["means"] else "—"
                         for name in ranking_metric_names]
                lines.append(f"| {label} | {entry['rows']} | {entry['queries']} | " + " | ".join(cells) + " |")
            lines.append("")
        return "\n".join(lines) + "\n"

    def write(self, json_path, completed, total, status):
        report = self.snapshot(completed, total, status)
        markdown_path, summary_json_path = summary_paths(json_path)
        for path, content in ((markdown_path, self.markdown(report)),
                              (summary_json_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")):
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                                 prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(content)
                # Readers see a complete old or new snapshot, never a half-written file.
                os.replace(temporary, path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
