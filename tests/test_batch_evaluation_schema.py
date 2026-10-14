import pytest

from services.batch_evaluation import validate_document


def valid_document():
    return {
        "schema_version": 1,
        "evaluations": [{
            "id": "eval-1",
            "query": "consulta de teste",
            "relevant_urls": [f"https://g1.globo.com/artigo/{i}" for i in range(10)],
        }],
    }


def test_validate_document_accepts_ten_unique_relevant_urls():
    assert len(validate_document(valid_document())) == 1


def test_validate_document_requires_ten_relevant_urls_per_evaluation():
    document = valid_document()
    document["evaluations"][0]["relevant_urls"].pop()

    with pytest.raises(ValueError, match="at least 10"):
        validate_document(document)


def test_validate_document_rejects_duplicate_relevant_urls():
    document = valid_document()
    document["evaluations"][0]["relevant_urls"][-1] = document["evaluations"][0]["relevant_urls"][0]

    with pytest.raises(ValueError, match="unique URLs"):
        validate_document(document)


def test_validate_document_rejects_unknown_fields():
    document = valid_document()
    document["evaluations"][0]["extra"] = True

    with pytest.raises(ValueError, match="keys must be exactly"):
        validate_document(document)
