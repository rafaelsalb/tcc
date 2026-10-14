import argparse
import sys
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
    if args.evaluate_file:
        try:
            evaluations = load_evaluation_file(args.evaluate_file)
            json_path, csv_path = output_paths(args.evaluate_file, args.output)
            ensure_output_available((json_path, csv_path), args.overwrite)
        except (ValueError, FileExistsError) as exc:
            print(f"Invalid batch evaluation: {exc}", file=sys.stderr)
            sys.exit(2)
        from app import App

        app = App()
        try:
            run_batch_evaluation(app, evaluations, json_path, csv_path)
        except Exception as exc:
            print(f"Batch evaluation failed: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"Wrote detailed results to {json_path}")
        print(f"Wrote summary to {csv_path}")
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
    parser.add_argument("--output", type=Path, help="JSON output path (CSV summary is written beside it). Defaults to <input>.results.json.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing batch evaluation outputs.")
    args = parser.parse_args()

    main(args)
