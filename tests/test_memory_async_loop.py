import asyncio
from types import SimpleNamespace

import numpy as np

import main.app.orunmila.memory as memoryMod
import main.app.orunmila.tools.memory as toolsMemoryMod
from main.app.orunmila.memory import OrunmilaMemory, getMatrix
from tests.conftest import clearAll
from main.app.orunmila.tools import save_memory, search_memory


def _fakeModel(fn):
    def _encode(texts, normalize_embeddings=True):
        vals = fn(texts)
        return SimpleNamespace(tolist=lambda: vals)

    return SimpleNamespace(encode=_encode)


def makeQueryVector():
    return [1.0] + [0.0] * 383


def makeMatchVector():
    return [1.0, 1.0] + [0.0] * 382


def makeDistractorVector():
    return [0.0, 0.0, 1.0] + [0.0] * 381


def makeFlatVector():
    return [0.5] * 384


class TestSearchVectorPath:
    def test_search_vectorPath(self, dbSession, monkeypatch):
        clearAll()
        monkeypatch.setattr(
            memoryMod, "getEmbeddingModel", lambda: _fakeModel(lambda texts: [makeQueryVector() for _ in texts])
        )
        OrunmilaMemory.upsertMemory(
            dbSession,
            31,
            "ticker favorito",
            "minha acao favorita e WEGE3",
            "preference",
            embedding=makeMatchVector(),
        )
        OrunmilaMemory.upsertMemory(
            dbSession,
            31,
            "outro",
            "texto sem relacao com nada especifico",
            "preference",
            embedding=makeDistractorVector(),
        )
        res = OrunmilaMemory.search(dbSession, 31, "WEGE3")
        assert res[0]["memoryKey"] == "ticker favorito"
        assert res[0]["similarity"] > 0


class TestUpsertThenSearch:
    def test_upsertThenSearchFindsRow(self, dbSession, monkeypatch):
        clearAll()
        monkeypatch.setattr(
            memoryMod, "getEmbeddingModel", lambda: _fakeModel(lambda texts: [makeFlatVector() for _ in texts])
        )
        OrunmilaMemory.upsertMemory(
            dbSession,
            32,
            "chave teste",
            "valor de teste WEGE3",
            "preference",
            embedding=makeFlatVector(),
        )
        res = OrunmilaMemory.search(dbSession, 32, "teste")
        assert any(r["memoryKey"] == "chave teste" for r in res)


class TestToolsInsideLoop:
    async def test_saveMemoryToolInsideLoop(self, dbSession, monkeypatch):
        # clearAll() is sync and drives the cache via asyncio.run — run it in a
        # worker thread since this test itself runs inside an event loop.
        await asyncio.to_thread(clearAll)
        monkeypatch.setattr(
            toolsMemoryMod, "getEmbeddingModel", lambda: _fakeModel(lambda texts: [makeQueryVector() for _ in texts])
        )
        monkeypatch.setattr(
            memoryMod, "getEmbeddingModel", lambda: _fakeModel(lambda texts: [makeQueryVector() for _ in texts])
        )
        saved = await save_memory(
            "ticker favorito",
            "minha acao favorita e WEGE3",
            "preference",
            user={"userId": 33, "roles": []},
            db=dbSession,
        )
        assert saved["status"] == "created"
        found = await search_memory(
            "WEGE3",
            user={"userId": 33},
            db=dbSession,
        )
        assert any(m["memoryKey"] == "ticker favorito" for m in found["memories"])


class TestSyncDeadlockRegression:
    async def test_syncGetMatrixInsideLoopSucceeds(self):
        # The persistent cache loop owns all cache IO, so a sync cached call
        # from a thread with a running loop blocks briefly and succeeds
        # instead of raising (old per-call asyncio.run limitation).
        await asyncio.to_thread(clearAll)
        calls = []

        def seedLoader():
            calls.append(1)
            return ([1], np.eye(1, dtype=np.float32))

        ids, matrix = getMatrix(99, seedLoader)
        assert ids == [1]
        assert matrix.shape == (1, 1)
        idsAgain, _ = getMatrix(99, seedLoader)
        assert idsAgain == [1]
        assert calls == [1]  # second call is a cache hit
