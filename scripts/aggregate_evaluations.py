"""Combine batch inputs without duplicating queries or changing relevance order."""

import argparse
import hashlib
import json
from pathlib import Path

from services.batch_evaluation import validate_document


STYLES = ("keyword", "short_theme", "specific_keywords", "broad_theme", "short_question",
          "specific_question", "information_request", "baseline", "unspecified")


def aggregate(documents):
    cases = {}
    source_stats = []
    id_keys = {}
    for source, document in documents:
        evaluations = validate_document(document)
        eligible = 0
        for item in evaluations:
            if len(set(item["relevant_urls"])) < 20:
                continue
            eligible += 1
            # The ordered reference list is part of the test, not just its set.
            key = (item["query"], tuple(item["relevant_urls"]))
            if item["id"] in id_keys and id_keys[item["id"]] != key:
                raise ValueError(f"Conflicting evaluation ID: {item['id']}")
            id_keys[item["id"]] = key
            record = cases.setdefault(key, {"item": item, "sources": []})
            record["sources"].append({"file": source, "id": item["id"]})
            # Prefer the explicitly labelled variant to its identical standalone
            # baseline or an older file without formulation metadata.
            def preference(value):
                return (value.get("query_formulation", "unspecified") != "unspecified", "__" in value["id"])
            if preference(item) > preference(record["item"]):
                record["item"] = item
        source_stats.append({"file": source, "input_cases": len(evaluations), "eligible_cases": eligible,
                             "excluded_below_20": len(evaluations) - eligible})

    def order(record):
        item = record["item"]
        style = item.get("query_formulation", "unspecified")
        return (STYLES.index(style) if style in STYLES else len(STYLES), item["id"].split("__", 1)[0], item["id"])

    records = sorted(cases.values(), key=order)
    result = {"schema_version": 1, "evaluations": [record["item"] for record in records]}
    validate_document(result)
    return result, {"sources": source_stats, "unique_cases": len(records),
                    "duplicate_cases_removed": sum(row["eligible_cases"] for row in source_stats) - len(records),
                    "cases": [{"id": row["item"]["id"], "sources": row["sources"]} for row in records]}


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root / "evals_definitive_2025_2026.json")
    parser.add_argument("--inputs", type=Path, nargs="+", help="Defaults to root eval*.json input documents.")
    args = parser.parse_args()
    provenance_path = args.output.with_suffix(".sources.json")
    for path in (args.output, provenance_path):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite {path}")
    documents, hashes = [], {}
    for path in (args.inputs if args.inputs is not None else sorted(root.glob("eval*.json"))):
        document = json.loads(path.read_text(encoding="utf-8"))
        if set(document) != {"schema_version", "evaluations"}:
            if args.inputs is not None:
                raise ValueError(f"Not a batch input: {path}")
            continue
        source = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
        documents.append((source, document))
        hashes[source] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not documents:
        raise ValueError("No evaluation input documents found")
    result, provenance = aggregate(documents)
    provenance["source_sha256"] = hashes
    for path, document in ((args.output, result), (provenance_path, provenance)):
        with path.open("x", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    print(f"Wrote {len(result['evaluations'])} unique cases to {args.output}")
    print(f"Removed {provenance['duplicate_cases_removed']} duplicate cases; provenance: {provenance_path}")


if __name__ == "__main__":
    main()
