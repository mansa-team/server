import asyncio

import numpy as np
import pytest

import main.app.prometheus.memory as memoryMod
import main.app.prometheus.tools as toolsMod
from main.app.prometheus.memory import PrometheusMemory, clearAll, getMatrix
from main.app.prometheus.tools import save_memory, search_memory


def makeQueryVector():
    return [1.0] + [0.0] * 383


def makeMatchVector():
    return [1.0, 1.0] + [0.0] * 382


def makeDistractorVector():
    return [0.0, 0.0, 1.0] + [0.0] * 381


def makeFlatVector():
    return [0.5] * 384


class TestSearchAsyncVectorPath:
    def test_searchAsync_vectorPath(self, dbSession, monkeypatch):
        clearAll()
        monkeypatch.setattr(memoryMod, "embed", lambda texts: [makeQueryVector() for _ in texts])
        asyncio.run(
            PrometheusMemory.upsertMemoryAsync(
                dbSession,
                31,
                "ticker favorito",
                "minha acao favorita e WEGE3",
                "preference",
                embedding=makeMatchVector(),
            ),
        )
        asyncio.run(
            PrometheusMemory.upsertMemoryAsync(
                dbSession,
                31,
                "outro",
                "texto sem relacao com nada especifico",
                "preference",
                embedding=makeDistractorVector(),
            ),
        )
        res = asyncio.run(PrometheusMemory.searchAsync(dbSession, 31, "WEGE3"))
        assert res[0]["memoryKey"] == "ticker favorito"
        assert res[0]["similarity"] > 0


class TestUpsertThenSearch:
    def test_upsertThenSearchFindsRow(self, dbSession, monkeypatch):
        clearAll()
        monkeypatch.setattr(memoryMod, "embed", lambda texts: [makeFlatVector() for _ in texts])
        asyncio.run(
            PrometheusMemory.upsertMemoryAsync(
                dbSession,
                32,
                "chave teste",
                "valor de teste WEGE3",
                "preference",
                embedding=makeFlatVector(),
            ),
        )
        res = asyncio.run(PrometheusMemory.searchAsync(dbSession, 32, "teste"))
        assert any(r["memoryKey"] == "chave teste" for r in res)


class TestToolsInsideLoop:
    def test_saveMemoryToolInsideLoop(self, dbSession, monkeypatch):
        clearAll()
        monkeypatch.setattr(toolsMod, "embed", lambda texts: [makeQueryVector() for _ in texts])
        monkeypatch.setattr(memoryMod, "embed", lambda texts: [makeQueryVector() for _ in texts])
        saved = asyncio.run(
            save_memory(
                "ticker favorito",
                "minha acao favorita e WEGE3",
                "preference",
                user={"userId": 33, "roles": []},
                db=dbSession,
            ),
        )
        assert saved["status"] == "created"
        found = asyncio.run(
            search_memory(
                "WEGE3",
                user={"userId": 33},
                db=dbSession,
            ),
        )
        assert any(m["memoryKey"] == "ticker favorito" for m in found["memories"])


class TestSyncDeadlockRegression:
    def test_syncGetMatrixInsideLoopRaises(self):
        clearAll()

        def seedLoader():
            return ([1], np.eye(1, dtype=np.float32))

        async def inner():
            return getMatrix(99, seedLoader)

        with pytest.raises(RuntimeError):
            asyncio.run(inner())
