import numpy as np
import pytest

from repositories import chunk as chunk_module
from repositories.chunk import ChunkRepository


class FakeSession:
    def __init__(self, engine):
        self.executions = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, parameters):
        self.executions.append((statement, parameters))

    def commit(self):
        self.committed = True


def test_batch_update_embeddings_uses_one_executemany(monkeypatch):
    sessions = []

    def make_session(engine):
        session = FakeSession(engine)
        sessions.append(session)
        return session

    monkeypatch.setattr(chunk_module, "Session", make_session)
    ids = [11, 12, 13]
    vectors = [np.asarray([float(i), 0.0]) for i in range(3)]

    ChunkRepository(object()).batch_update_embeddings(ids, vectors)

    assert len(sessions) == 1
    assert len(sessions[0].executions) == 1
    actual = sessions[0].executions[0][1]
    assert [row["id"] for row in actual] == ids
    assert all(np.array_equal(row["embedding"], vector)
               for row, vector in zip(actual, vectors))
    assert sessions[0].committed


def test_batch_update_embeddings_rejects_mismatched_inputs(monkeypatch):
    monkeypatch.setattr(
        chunk_module, "Session",
        lambda _engine: pytest.fail("must validate before opening a session"),
    )

    with pytest.raises(ValueError, match="same length"):
        ChunkRepository(object()).batch_update_embeddings([1], [])


def test_batch_update_embeddings_empty_input_does_not_open_session(monkeypatch):
    monkeypatch.setattr(
        chunk_module, "Session",
        lambda _engine: pytest.fail("empty batch must not open a session"),
    )

    assert ChunkRepository(object()).batch_update_embeddings([], []) is None
