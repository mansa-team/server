import argparse
import json
import os
import time
from datetime import datetime, timezone

import numpy as np

DIMS = 384


def benchOnce(n: int, useReal: bool) -> dict:
    rng = np.random.default_rng(42)
    mat = rng.normal(size=(n, DIMS)).astype(np.float32)
    mat /= np.linalg.norm(mat, axis=1, keepdims=True)
    blobs = [r.tobytes() for r in mat]
    q = rng.normal(size=(DIMS,)).astype(np.float32)
    q /= float(np.linalg.norm(q))
    t0 = time.perf_counter()
    from main.app.prometheus.vector import decodeEmbeddings, batchCosineSimilarity

    decoded = decodeEmbeddings(blobs)
    decodeMs = (time.perf_counter() - t0) * 1000.0
    t1 = time.perf_counter()
    scores = batchCosineSimilarity(q.tolist(), decoded)
    searchMs = (time.perf_counter() - t1) * 1000.0
    encodeMs = 0.0
    if useReal:
        from main.app.prometheus.vector import embed

        t2 = time.perf_counter()
        embed(["carteira de dividendos Wege"])
        encodeMs = (time.perf_counter() - t2) * 1000.0
    return {
        "n": n,
        "encodeMs": round(encodeMs, 1),
        "decodeMs": round(decodeMs, 1),
        "searchMs": round(searchMs, 1),
        "topScore": round(float(np.max(scores)), 4),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true")
    ap.add_argument("--label", default="run")
    args = ap.parse_args()
    out = {"label": args.label, "at": datetime.now(timezone.utc).isoformat(), "rows": []}
    for n in (50, 250, 500):
        out["rows"].append(benchOnce(n, args.real))
    os.makedirs("bench/results", exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with open(f"bench/results/{ts}-{args.label}.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
