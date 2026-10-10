from importlib.metadata import version
from pathlib import Path


def test_fastmcp4_sdk2_importable():
    import fastmcp

    assert int(fastmcp.__version__.split(".")[0]) >= 4
    # mcp 2.x dropped the __version__ attribute; canonical version via stdlib metadata
    assert int(version("mcp").split(".")[0]) >= 2


def test_no_fastapi_mcp_import():
    # order-independent: conftest imports the app (which still mounts legacy
    # FastApiMCP until Task 6 purges it), so sys.modules always contains it
    # in a full-suite run. Pin the Task 1 deliverable instead: the dep is
    # gone from requirements.
    requirements = Path(__file__).resolve().parent.parent.joinpath("requirements.txt").read_text()
    assert "fastapi_mcp" not in requirements
