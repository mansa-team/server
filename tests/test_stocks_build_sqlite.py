"""Cheap coverage for the MySQL -> feather pipeline (reviewer issue #13/#26 follow-up).

buildFeatherCache() targets MySQL in prod, but its SHOW COLUMNS failure path
falls back to typeless columns, so the full build -> read roundtrip runs on a
throwaway SQLite file with the same SQL shape (SELECT * ... ORDER BY TICKER,
TIME DESC). exercises chunking, zstd JSON compression, presorted flag.
"""

from sqlalchemy import create_engine, text

from main.app.stocks_api import build as buildMod
from main.app.stocks_api.build import buildFeatherCache, readFeatherDataFrame


def _seeded_sqlite(path):
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE b3_stocks (TICKER VARCHAR(20), NOME VARCHAR(255), "
                "TIME DATETIME, PRECO DOUBLE, `COTACAO 10Y PADRAO` TEXT)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO b3_stocks VALUES "
                "('PETR4', 'Petrobras', '2026-01-02 10:00:00', 10.5, '[{\"DATA\": \"02-01-2026\"}]'),"
                "('PETR4', 'Petrobras', '2026-01-01 10:00:00', 10.0, NULL),"
                "('VALE3', 'Vale', '2026-01-02 10:00:00', 20.0, NULL)"
            )
        )
    return engine


def test_build_and_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(buildMod, "CACHE_FEATHER_PATH", tmp_path / "stocks_cache.feather")
    monkeypatch.setattr(buildMod, "CACHE_NESTED_PATH", tmp_path / "stocks_nested.feather")
    engine = _seeded_sqlite(tmp_path / "seed.db")

    buildFeatherCache(engine)
    df, presorted = readFeatherDataFrame(tmp_path / "stocks_cache.feather")

    assert presorted is True
    assert len(df) == 3
    assert df.iloc[0]["TICKER"] == "PETR4"  # presorted: TICKER ASC, TIME DESC
    assert "COTACAO 10Y PADRAO" in df.columns


def test_empty_table_builds_no_feather(tmp_path, monkeypatch):
    monkeypatch.setattr(buildMod, "CACHE_FEATHER_PATH", tmp_path / "stocks_cache.feather")
    monkeypatch.setattr(buildMod, "CACHE_NESTED_PATH", tmp_path / "stocks_nested.feather")
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE b3_stocks (TICKER VARCHAR(20), TIME DATETIME)"))

    buildFeatherCache(engine)
    assert not (tmp_path / "stocks_cache.feather").exists()
