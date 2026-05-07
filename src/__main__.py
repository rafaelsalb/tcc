import argparse
import sys

from app import App


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
    app = App()
    if args.populate_chunks:
        app.populate_chunks()
    elif args.populate_embeddings:
        app.populate_embeddings()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the G1 article processing app.")
    parser.add_argument("--populate-chunks", action="store_true", help="Populate the database with article chunks.")
    parser.add_argument("--populate-embeddings", action="store_true", help="Populate the database with chunk embeddings.")
    args = parser.parse_args()

    main(args)
