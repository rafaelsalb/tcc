from config import SPOTLIGHT_ENDPOINT
from db import engine
from repositories.entities import EntityRepository
from services.linking import accepts_surface, is_junk_surface, link_surface, uri_label
from services.ner import NERService


ner_service = NERService(EntityRepository(engine))


def test_accepts_surface():
    # exact matches (accent/case-insensitive)
    assert accepts_surface("Donald Trump", "Donald Trump")
    assert accepts_surface("EUA", "eua")
    # title/function-word prefixes around the salient mention
    assert accepts_surface("presidente Lula", "Lula")
    assert accepts_surface("de Lula", "Lula")
    # a shorter spotted form inside a different full name must be rejected
    assert not accepts_surface("José Guimarães", "Guimarães")
    assert not accepts_surface("Fábio Luís Lula da Silva", "Lula")
    assert not accepts_surface("Melania Trump", "Trump")


def test_uri_label():
    assert uri_label("http://pt.dbpedia.org/resource/Donald_Trump") == "Donald Trump"
    assert uri_label("http://pt.dbpedia.org/resource/Estados_Unidos") == "Estados Unidos"


def test_is_junk_surface():
    assert is_junk_surface("Foto")
    assert is_junk_surface("foto")
    assert is_junk_surface("Donald Trump — Foto")
    assert is_junk_surface("Reprodução/")
    assert is_junk_surface("123")
    assert not is_junk_surface("Donald Trump")
    assert not is_junk_surface("Polícia Federal")


def test_link_surface():
    uri = link_surface("Donald Trump", SPOTLIGHT_ENDPOINT)
    assert uri is not None
    assert "Trump" in uri


def test_hybrid_extraction_links_entities():
    text = (
        "O presidente dos Estados Unidos, Donald Trump, afirmou que os EUA "
        "vão intensificar os ataques. Trump também criticou o Irã e o primeiro-ministro de Israel."
    )
    entities = ner_service.extract_entities(text)
    assert len(entities) > 0
    assert all(set(entity) >= {"text", "label", "canonical"} for entity in entities)
    linked = [entity["canonical"] for entity in entities if entity["canonical"]]
    assert len(linked) > 0
    # surfaces of the same entity link to the same canonical URI
    trump_uris = {entity["canonical"] for entity in entities if "Trump" in entity["text"] and entity["canonical"]}
    assert len(trump_uris) <= 1
