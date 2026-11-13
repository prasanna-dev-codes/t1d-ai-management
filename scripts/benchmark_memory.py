"""Reproducible offline assembly timing; large cases are stress tests, not API limits."""

import argparse
import json
import platform
import statistics
from datetime import timedelta
from pathlib import Path
from time import perf_counter

from t1d_memory.episodes import build_episodes, canonical_hash
from t1d_memory.synthetic import PATIENT, START, STUDY, cohort


def benchmark(count: int, repeats: int) -> dict[str, object]:
    if not 1 <= count <= 1000 or not 1 <= repeats <= 20:
        raise ValueError("Bounded workload/repetitions required")
    events = cohort(count)
    cutoff = START + timedelta(days=200)
    expected, skipped = build_episodes(events, cutoff, STUDY, PATIENT)
    times = []
    for _ in range(repeats):
        start = perf_counter()
        episodes, ignored = build_episodes(events, cutoff, STUDY, PATIENT)
        times.append((perf_counter() - start) * 1000)
        if ignored != skipped or episodes != expected:
            raise ValueError("Nondeterministic assembly")
    return {
        "meals": count,
        "events": len(events),
        "repeats": repeats,
        "median_ms": statistics.median(times),
        "minimum_ms": min(times),
        "maximum_ms": max(times),
        "episodes": len(expected),
        "skipped": skipped,
        "identity_sha256": canonical_hash([str(e.id) for e in expected]),
        "exceeds_live_cgm_limit": count * 25 > 5000,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--meals", type=int, nargs="+", default=[80, 200, 1000])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = {
            "workload": "authored-synthetic-assembly-v1",
            "python": platform.python_version(),
            "platform": platform.system(),
            "scope": "Offline assembly only; no database, API or network timing",
            "results": [benchmark(n, args.repeats) for n in args.meals],
        }
    except ValueError:
        parser.error("Use 1–1000 meals per workload and 1–20 repetitions")
    output = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output)
