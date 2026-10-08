"""HTTP bench: warmup then fixed-total levels at rising concurrency.

Stdlib only (asyncio + urllib). Read-only GET traffic.
Reports p50/p95/p99 + rps + errors per level; aborts a level if 5xx > 1%.

Usage:
    python scripts/bench_http.py --base http://localhost:3200 --path /stocks/fields
    python scripts/bench_http.py --base http://localhost:8080 --path /stocks/fields --levels 10,25,50,100
"""

import argparse
import asyncio
import json
import random
import statistics
import time
import urllib.request


def fetch(url: str, timeout: float) -> tuple[int, float, str | None]:
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            response.read()
            status = response.status
            cache_status = response.headers.get("X-Cache-Status")
    except Exception as exc:
        status = getattr(exc, "code", 0) or 0
        cache_status = None
    return status, 1000.0 * (time.perf_counter() - start), cache_status


def percentile(samples: list[float], pct: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = min(len(ordered) - 1, int(pct / 100.0 * len(ordered)))
    return ordered[index]


async def run_level(url: str, concurrency: int, total: int, jitter_ms: float, timeout: float) -> dict:
    sem = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    samples: list[dict] = []
    errors = 0
    count_5xx = 0
    statuses: dict[int, int] = {}

    async def one() -> None:
        nonlocal errors, count_5xx
        async with sem:
            if jitter_ms > 0:
                await asyncio.sleep(random.uniform(0, jitter_ms / 1000.0))
            status, ms, cache_status = await asyncio.to_thread(fetch, url, timeout)
            latencies.append(ms)
            samples.append(
                {"t": round(time.time(), 3), "latency_ms": round(ms, 2), "status": status, "cache_status": cache_status}
            )
            statuses[status] = statuses.get(status, 0) + 1
            if status >= 500 or status == 0:
                count_5xx += 1
            if status != 200:
                errors += 1

    start = time.perf_counter()
    await asyncio.gather(*[one() for _ in range(total)])
    elapsed = time.perf_counter() - start
    aborted = count_5xx / total > 0.01
    return {
        "concurrency": concurrency,
        "total": total,
        "samples": samples,
        "elapsed_s": round(elapsed, 2),
        "rps": round(total / elapsed, 1) if elapsed > 0 else 0.0,
        "p50_ms": round(percentile(latencies, 50), 1),
        "p95_ms": round(percentile(latencies, 95), 1),
        "p99_ms": round(percentile(latencies, 99), 1),
        "mean_ms": round(statistics.fmean(latencies), 1) if latencies else 0.0,
        "errors": errors,
        "err_pct": round(100.0 * errors / total, 2),
        "aborted_5xx": aborted,
    }


async def main_async(args: argparse.Namespace) -> None:
    url = args.base.rstrip("/") + args.path
    print(f"target: {url}  levels={args.levels}  total={args.total}  warmup={args.warmup}")
    for _ in range(args.warmup):
        await asyncio.to_thread(fetch, url, args.timeout)
    print("warmed up")
    out = open(args.out, "w" if args.fresh else "a", encoding="utf-8") if args.out else None
    try:
        for level in [int(x) for x in args.levels.split(",") if x.strip()]:
            result = await run_level(url, level, args.total, args.jitter_ms, args.timeout)
            if out is not None:
                for sample in result["samples"]:
                    sample.update({"target": args.base, "level": level, "route": args.path})
                    out.write(json.dumps(sample) + "\n")
            print(
                f"c={result['concurrency']:>3} n={result['total']} "
                f"p50={result['p50_ms']}ms p95={result['p95_ms']}ms p99={result['p99_ms']}ms "
                f"mean={result['mean_ms']}ms rps={result['rps']} "
                f"errors={result['errors']} ({result['err_pct']}%)"
                + (" ABORTED-5xx>1%" if result["aborted_5xx"] else "")
            )
            if result["aborted_5xx"]:
                print(f"abort: 5xx>1% at c={level}, stopping ramp")
                break
    finally:
        if out is not None:
            out.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="stdlib HTTP bench")
    parser.add_argument("--base", default="http://localhost:3200")
    parser.add_argument("--path", default="/stocks/fields")
    parser.add_argument("--levels", default="10,25,50,100")
    parser.add_argument("--total", type=int, default=200)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--jitter-ms", type=float, default=5.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--out", default="scripts/bench_samples.jsonl", help="JSONL raw samples file (append unless --fresh)"
    )
    parser.add_argument("--fresh", action="store_true", help="truncate --out before writing")
    parser.add_argument("--no-out", action="store_true", help="skip writing raw samples")
    args = parser.parse_args()
    if args.no_out:
        args.out = None
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
