from importlib.metadata import version
from pathlib import Path
import re


def test_fastmcp4_sdk2_importable():
    import fastmcp

    assert int(fastmcp.__version__.split(".")[0]) >= 4
    # mcp 2.x dropped the __version__ attribute; canonical version via stdlib metadata
    assert int(version("mcp").split(".")[0]) >= 2


def test_no_fastapi_mcp_requirement():
    # order-independent: conftest imports the app, so sys.modules would
    # contain any eagerly imported dep in a full-suite run. Pin the
    # deliverable instead: the dep is gone from requirements.
    requirementText = Path(__file__).resolve().parent.parent.joinpath("requirements.txt").read_text()
    packageNames = []
    for rawLine in requirementText.splitlines():
        strippedLine = rawLine.split("#", 1)[0].strip()
        if not strippedLine:
            continue
        packageName = re.split(r"[<>=!~\s\[;]+", strippedLine, maxsplit=1)[0].strip().lower().replace("_", "-")
        if packageName:
            packageNames.append(packageName)
    assert "fastapi-mcp" not in packageNames
