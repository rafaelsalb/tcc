"""Generate a batch input comparing eight formulations of each curated theme."""

import argparse
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
STYLES = (
    "keyword", "short_theme", "specific_keywords", "broad_theme",
    "short_question", "specific_question", "information_request", "baseline",
)
QUERIES = {
    "banco_master": (
        "Banco Master",
        "crise Banco Master",
        "Banco Master BRB liquidação fraude FGC",
        "crise no Banco Master e seus impactos",
        "O que aconteceu com o Banco Master?",
        "Como a crise do Banco Master envolveu o BRB e afetou os investidores?",
        "Entenda a crise do Banco Master, as suspeitas de fraude e as consequências da liquidação.",
    ),
    "descontos_inss": (
        "fraude INSS",
        "descontos indevidos INSS",
        "INSS descontos associativos fraude aposentados ressarcimento",
        "fraudes em aposentadorias do INSS e investigação",
        "O que foi a fraude dos descontos no INSS?",
        "Como funcionavam os descontos associativos não autorizados no INSS e o ressarcimento às vítimas?",
        "Explique o esquema de descontos indevidos no INSS e os principais desdobramentos da investigação.",
    ),
    "tarifaco_eua_brasil": (
        "tarifaço Brasil",
        "tarifaço EUA Brasil",
        "tarifas Trump Brasil exportações negociação Suprema Corte",
        "tarifas americanas e impactos no Brasil",
        "O que aconteceu com o tarifaço contra o Brasil?",
        "Como as negociações e a decisão da Suprema Corte mudaram as tarifas dos EUA sobre produtos brasileiros?",
        "Entenda a imposição do tarifaço ao Brasil, seus impactos e as mudanças posteriores na cobrança.",
    ),
    "metanol_bebidas": (
        "metanol bebidas",
        "crise do metanol em bebidas",
        "metanol bebidas adulteradas intoxicação investigação antídotos",
        "intoxicações por bebidas adulteradas no Brasil",
        "O que aconteceu na crise do metanol?",
        "Como o metanol chegou às bebidas adulteradas e quais medidas foram tomadas para combater as intoxicações?",
        "Explique o surto de intoxicações por metanol em bebidas e os principais resultados da investigação.",
    ),
    "caso_benicio": (
        "Benício adrenalina",
        "caso Benício em Manaus",
        "Benício Xavier adrenalina Hospital Santa Júlia erro prescrição perícia",
        "morte de Benício e investigação do atendimento hospitalar",
        "O que aconteceu com o menino Benício?",
        "Qual foi o erro na administração de adrenalina a Benício Xavier e o que a perícia concluiu?",
        "Explique o caso Benício, o atendimento no Hospital Santa Júlia e os desdobramentos da investigação.",
    ),
}


def build_variants(source):
    if (
        set(source) != {"schema_version", "evaluations"}
        or type(source["schema_version"]) is not int
        or source["schema_version"] != 1
    ):
        raise ValueError("Expected a schema_version=1 batch input.")
    originals = source["evaluations"]
    if len(originals) != len(QUERIES) or {item["id"] for item in originals} != set(QUERIES):
        raise ValueError("Expected exactly the five curated theme IDs.")
    variants = []
    # Interleave themes so the first results cover all themes with short queries.
    for style_index, style in enumerate(STYLES):
        for item in originals:
            urls = item["relevant_urls"]
            if not urls or len(set(urls)) != len(urls):
                raise ValueError(f"{item['id']}: expected nonempty, unique, relevance-ordered URLs.")
            query = item["query"] if style == "baseline" else QUERIES[item["id"]][style_index]
            variants.append({
                "id": f"{item['id']}__{style}", "query": query,
                "query_formulation": style,
                "relevant_urls": list(urls),
            })
    return {"schema_version": 1, "evaluations": variants}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=REPO / "evals_curated_2025_2026.json")
    parser.add_argument("--output", type=Path, default=REPO / "evals_curated_query_variants_stages_2025_2026.json")
    args = parser.parse_args()
    document = build_variants(json.loads(args.input.read_text(encoding="utf-8")))
    # Never overwrite existing evaluation inputs; choose another name to regenerate.
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"Wrote {len(document['evaluations'])} evaluations to {args.output}")


if __name__ == "__main__":
    main()
