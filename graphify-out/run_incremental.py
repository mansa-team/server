import json
from graphify.detect import detect_incremental, save_manifest
from pathlib import Path

result = detect_incremental(Path("."))
new_total = result.get("new_total", 0)
print(json.dumps(result, indent=2))
Path("graphify-out/.graphify_incremental.json").write_text(json.dumps(result))
if new_total == 0:
    print("No files changed since last run. Nothing to update.")
    raise SystemExit(0)
print(f"{new_total} new/changed file(s) to re-extract.")
