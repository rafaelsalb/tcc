import argparse
import json
import sys
from datetime import date
from pathlib import Path

from services.batch_evaluation import (
    ensure_output_available,
    load_evaluation_file,
    output_paths,
    run_batch_evaluation,
)


def main(args):
    # query = "Pelo que o empresário é investigado?"
    # result = vectorizer.embed("qwen3-embedding:0.6b", [query], 768)
    # query_embeddings = result[0]
    # results = chunk_repo.query_chunks(query_embeddings)
    # best = results[0]
    # pprint(best)
    if args.populate_chunks and args.populate_embeddings:
        print("Please choose either --populate-chunks or --populate-embeddings, not both.")
        sys.exit(1)
    if args.generate_themes:
        from db import engine
        from services.theme_generation import ThemeSelectionPolicy, generate_themes

        policy = ThemeSelectionPolicy(
            min_articles=args.theme_min_articles,
            max_articles=args.theme_max_articles,
            band_edges=tuple(args.theme_band_edges),
            per_band=args.theme_per_band,
            max_entities=args.theme_max_entities,
        )
        try:
            document = generate_themes(engine, args.theme_date_from, args.theme_date_to, policy)
        except ValueError as exc:
            print(f"Invalid theme generation options: {exc}", file=sys.stderr)
            sys.exit(2)
        args.generate_themes.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {len(document['themes'])} generated themes to {args.generate_themes}")
        return
    if args.attach_theme_counts_file:
        from db import engine
        from services.theme_counts import attach_theme_counts_file

        try:
            results = attach_theme_counts_file(engine, args.attach_theme_counts_file)
        except (ValueError, LookupError, RuntimeError) as exc:
            print(f"Could not attach theme article counts: {exc}", file=sys.stderr)
            sys.exit(2)
        print(f"Attached theme article counts for {len(results)} completed run(s):")
        for result in results:
            print(f"  {result['run_id']}: {len(result['themes'])} theme(s)")
        return
    if args.backfill_theme_difficulty:
        from db import engine
        from services.theme_counts import backfill_theme_difficulty_metrics

        try:
            result = backfill_theme_difficulty_metrics(engine)
        except Exception as exc:
            print(f"Could not backfill theme difficulty metrics: {exc}", file=sys.stderr)
            sys.exit(2)
        print(f"Updated {result['metrics_upgraded']} metric(s) across {len(result['runs_updated'])} run(s).")
        return
    if args.evaluate_file:
        try:
            evaluations = load_evaluation_file(args.evaluate_file)
            json_path, csv_path = output_paths(args.evaluate_file, args.output)
            ensure_output_available((json_path, csv_path), args.overwrite, args.resume)
        except (ValueError, FileExistsError) as exc:
            print(f"Invalid batch evaluation: {exc}", file=sys.stderr)
            sys.exit(2)
        from db import engine

        try:
            summary = run_batch_evaluation(
                engine, args.api_url, evaluations, json_path, csv_path,
                resume=args.resume, overwrite=args.overwrite,
                compare_stages=args.compare_stages, result_unit=args.result_unit,
                presets=args.presets, quorums=args.quorums, seed_methods=args.seed_methods,
                rankings=args.rankings, exclude_seed_methods=args.exclude_seed_methods,
                exclude_rankings=args.exclude_rankings,
                reuse=not args.no_reuse, benchmark=args.benchmark,
                workers=args.workers,
                query_seed_fallback=args.query_seed_fallback,
                ensemble_rankings=args.ensemble_rankings,
            )
        except KeyboardInterrupt:
            print("Batch stopped before a request started. Existing checkpoints are preserved.", file=sys.stderr)
            sys.exit(130)
        except Exception as exc:
            print(f"Batch evaluation failed: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"Wrote detailed results to {json_path}")
        print(f"Wrote summary to {csv_path}")
        if summary["status"] == "interrupted":
            sys.exit(128 + summary["stop_signal"])
        return
    from app import App

    app = App()
    if args.populate_chunks:
        app.populate_chunks()
    elif args.populate_embeddings:
        app.populate_embeddings()
    elif args.populate_entities:
        app.populate_entities()
    elif args.canonicalize_entities:
        app.canonicalize_entities(limit=args.limit)
    elif args.search:
        results = app.search_service.search(args.search, top_k=100)
        for result in results:
            print(f"Title: {result['article_title']}")
            print(f"URL: {result['article_url']}")
            print(f"Chunk: {result['chunk']}")
            print("-" * 80)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the G1 article processing app.")
    parser.add_argument("--populate-chunks", action="store_true", help="Populate the database with article chunks.")
    parser.add_argument("--populate-embeddings", action="store_true", help="Populate the database with chunk embeddings.")
    parser.add_argument("--populate-entities", action="store_true", help="Populate the database with article entities.")
    parser.add_argument("--canonicalize-entities", action="store_true", help="Link existing entities to DBpedia URIs (junk flags + alias canonicalization).")
    parser.add_argument("--limit", type=int, default=None, help="Limit entities processed by --canonicalize-entities (for trial runs).")
    parser.add_argument("--search", type=str, help="Search for a query in the chunks.")
    parser.add_argument("--evaluate-file", type=Path, help="Run batch search evaluations from a strict JSON input file.")
    parser.add_argument("--generate-themes", type=Path, help="Generate entity-co-occurrence themes and write a JSON artifact.")
    parser.add_argument("--attach-theme-counts-file", type=Path, help="Attach post-hoc theme article counts to completed runs using a JSON mapping file.")
    parser.add_argument("--backfill-theme-difficulty", action="store_true",
                        help="Append the current difficulty metric revision using already stored article counts; does not rerun searches or counts.")
    parser.add_argument("--theme-date-from", type=date.fromisoformat, default=date(2025, 6, 1), help="Inclusive article publication date lower bound (default: 2025-06-01).")
    parser.add_argument("--theme-date-to", type=date.fromisoformat, default=date(2026, 6, 30), help="Inclusive article publication date upper bound (default: 2026-06-30).")
    parser.add_argument("--theme-min-articles", type=int, default=10, help="Minimum matching article count (default: 10).")
    parser.add_argument("--theme-max-articles", type=int, default=1000, help="Maximum matching article count (default: 1000).")
    parser.add_argument("--theme-band-edges", nargs="+", type=int, default=(50, 200), help="Exclusive upper bounds separating prevalence bands (default: 50 200).")
    parser.add_argument("--theme-per-band", type=int, default=5, help="Maximum number of selected themes per prevalence band (default: 5).")
    parser.add_argument("--theme-max-entities", type=int, choices=(1, 2), default=2, help="Largest entity set considered (default: 2).")
    parser.add_argument("--output", type=Path, help="JSON report path (live CSV and JSONL checkpoint are written beside it). Defaults to <input>.results.json.")
    parser.add_argument("--api-url", type=str, default="http://localhost:5000", help="Base URL of the running Flask API (default: http://localhost:5000).")
    parser.add_argument("--compare-stages", action="store_true", help="Include lexical/hybrid/PPR/fused stage comparisons; combine with --rankings for one batch.")
    parser.add_argument("--result-unit", choices=("chunks", "articles"), default="chunks", help="Whether top_k limits chunks (legacy) or distinct articles.")
    parser.add_argument("--presets", nargs="+", choices=("rapido", "balanceado", "profundo"), help="Restrict batch search presets.")
    parser.add_argument("--quorums", nargs="+", type=float, help="Restrict batch quorum values, e.g. 0.3 0.7.")
    parser.add_argument("--seed-methods", nargs="+", choices=("louvain", "hits", "ppr_top10", "query_entities"), help="Restrict graph seeding methods.")
    parser.add_argument("--exclude-seed-methods", nargs="+", choices=("louvain", "hits", "ppr_top10", "query_entities"), help="Exclude seeding methods from the selected/default set.")
    parser.add_argument("--query-seed-fallback", choices=("hits", "louvain", "ppr_top10"), default="hits", help="Existing seed method used when query entities have no graph match.")
    parser.add_argument("--rankings", nargs="+", choices=("ppr", "hybrid_max", "rrf", "cross_encoder", "fused", "mmr", "graph_rwr", "graph_hits", "graph_salsa", "graph_path", "graph_walk", "graph_fusion", "graph_hits_cross_encoder", "lexical", "vector", "ensemble_rrf"), help="Ranking methods to include; with --compare-stages, they are added to the stage comparisons.")
    parser.add_argument("--exclude-rankings", nargs="+", choices=("ppr", "hybrid_max", "rrf", "cross_encoder", "fused", "mmr", "graph_rwr", "graph_hits", "graph_salsa", "graph_path", "graph_walk", "graph_fusion", "graph_hits_cross_encoder", "lexical", "vector", "ensemble_rrf"), help="Exclude rankings from the selected/default set.")
    parser.add_argument("--ensemble-rankings", nargs="+", choices=("ppr", "hybrid_max", "rrf", "cross_encoder", "fused", "mmr", "graph_rwr", "graph_hits", "graph_salsa", "graph_path", "graph_walk", "graph_fusion", "graph_hits_cross_encoder", "lexical", "vector"), help="Components for ensemble_rrf (default: rrf cross_encoder ppr).")
    parser.add_argument("--no-reuse", action="store_true", help="Use independent /search requests instead of the shared /evaluate endpoint.")
    parser.add_argument("--benchmark", action="store_true", help="Measure reuse against an independent baseline per output row, checking rank/score equivalence (extra work).")
    parser.add_argument("--workers", type=int, default=1, help="Maximum concurrent batch API requests/groups (1-16; default: 1). Use small values to protect CPU and database capacity.")
    output_mode = parser.add_mutually_exclusive_group()
    output_mode.add_argument("--overwrite", action="store_true", help="Replace existing batch evaluation outputs and checkpoint.")
    output_mode.add_argument("--resume", action="store_true", help="Resume a matching batch checkpoint, skipping saved configurations.")
    args = parser.parse_args()

    main(args)
