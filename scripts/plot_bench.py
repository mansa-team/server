"""Plot bench_samples.jsonl into PNGs (re-plottable without re-running).

Usage:
    python scripts/plot_bench.py
    python scripts/plot_bench.py --samples scripts/bench_samples.jsonl --out-dir scripts/plots

Emits: p95_vs_concurrency.png, rps_vs_concurrency.png, cdf_cached_c100.png
"""

import argparse
import json
import os
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    return sorted_vals[min(len(sorted_vals) - 1, int(pct / 100.0 * len(sorted_vals)))]


def load(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def groups(rows: list[dict]) -> dict[tuple[str, str, int], list[dict]]:
    grouped: dict[tuple[str, str, int], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(row["target"], row["route"], row["level"])].append(row)
    return grouped


def plot_p95(grouped: dict, out_dir: str) -> str:
    series: dict[tuple[str, str], dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for (target, route, level), rows in grouped.items():
        series[(target, route)][level].extend(r["latency_ms"] for r in rows)
    plt.figure()
    for (target, route), by_level in sorted(series.items()):
        levels = sorted(by_level)
        p95 = [percentile(sorted(by_level[level]), 95) for level in levels]
        plt.plot(levels, p95, marker="o", label=f"{target} {route}")
    plt.xlabel("concurrency")
    plt.ylabel("p95 latency (ms)")
    plt.title("p95 vs concurrency")
    plt.legend(fontsize="small")
    path = os.path.join(out_dir, "p95_vs_concurrency.png")
    plt.savefig(path, dpi=100, bbox_inches="tight")
    plt.close()
    return path


def plot_rps(grouped: dict, out_dir: str) -> str:
    series: dict[tuple[str, str], dict[int, float]] = defaultdict(dict)
    for (target, route, level), rows in grouped.items():
        stamps = [r["t"] for r in rows if "t" in r]
        span = max(stamps) - min(stamps) if len(stamps) > 1 else 0.0
        series[(target, route)][level] = len(rows) / span if span > 0 else 0.0
    plt.figure()
    for (target, route), by_level in sorted(series.items()):
        levels = sorted(by_level)
        plt.plot(levels, [by_level[level] for level in levels], marker="o", label=f"{target} {route}")
    plt.xlabel("concurrency")
    plt.ylabel("requests/sec")
    plt.title("rps vs concurrency")
    plt.legend(fontsize="small")
    path = os.path.join(out_dir, "rps_vs_concurrency.png")
    plt.savefig(path, dpi=100, bbox_inches="tight")
    plt.close()
    return path


def plot_cdf(rows: list[dict], out_dir: str) -> str:
    cached = [r for r in rows if r["route"] == "/stocks/fields"]
    top = max(r["level"] for r in cached)
    plt.figure()
    for target in sorted({r["target"] for r in cached}):
        vals = sorted(r["latency_ms"] for r in cached if r["target"] == target and r["level"] == top)
        n = len(vals)
        plt.plot(vals, [(i + 1) / n for i in range(n)], label=f"{target} (c={top}, n={n})")
    plt.xlabel("latency (ms)")
    plt.ylabel("CDF")
    plt.title(f"cached-route latency CDF at c={top}")
    plt.legend(fontsize="small")
    path = os.path.join(out_dir, "cdf_cached_c100.png")
    plt.savefig(path, dpi=100, bbox_inches="tight")
    plt.close()
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="plot bench JSONL samples")
    parser.add_argument("--samples", default="scripts/bench_samples.jsonl")
    parser.add_argument("--out-dir", default="scripts/plots")
    args = parser.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    rows = load(args.samples)
    grouped = groups(rows)
    print(f"rows={len(rows)} groups={len(grouped)}")
    for path in (plot_p95(grouped, args.out_dir), plot_rps(grouped, args.out_dir), plot_cdf(rows, args.out_dir)):
        print(f"wrote {path} ({os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    main()
