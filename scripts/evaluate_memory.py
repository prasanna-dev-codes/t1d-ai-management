"""Reproducible synthetic ranking comparison. No database or real patient data."""

import argparse
import json
import statistics
from datetime import timedelta
from pathlib import Path
from time import perf_counter

from t1d_memory.contracts import ProfileName
from t1d_memory.episodes import build_episodes
from t1d_memory.evaluation import metrics
from t1d_memory.ranking import cosine, embed, rank
from t1d_memory.synthetic import PATIENT, START, STUDY, cohort


def evaluate() -> dict[str, object]:
    episodes, _ = build_episodes(cohort(80), START + timedelta(days=30), STUDY, PATIENT)
    history, queries = episodes[:60], episodes[60:]
    profiles: list[ProfileName] = ["structured-v1", "vector-v1", "hybrid-v1"]
    report: dict[str, object] = {
        "data": "authored-synthetic-v1",
        "seed": "deterministic-no-rng",
        "history_episodes": len(history),
        "queries": len(queries),
        "k": 5,
        "relevance": "exact-food-concept-overlap; fictional labels, not metabolic equivalence",
        "limitations": [
            "No real patient or expert-adjudicated relevance set",
            "In-process graph/vector calculations, not service latency",
            "Hash feature vectors are not pretrained semantic embeddings",
            "No forecasting outcome improvement established",
        ],
    }
    results = {}
    for profile in profiles:
        measures = []
        elapsed = []
        for query in queries:
            relevant = {str(e.id) for e in history if set(e.foods) & set(query.foods)}
            started = perf_counter()
            vectors = {str(e.id): cosine(embed(e.foods), embed(query.foods)) for e in history}
            graph = {
                str(e.id): len(set(e.foods) & set(query.foods))
                / len(set(e.foods) | set(query.foods))
                for e in history
            }
            result = rank(history, query.foods, query.nutrients, profile, 5, vectors, graph)
            elapsed.append((perf_counter() - started) * 1000)
            measures.append(metrics([str(e.episode_id) for e in result], relevant, 5))
        results[profile] = {
            **{name: statistics.mean(row[name] for row in measures) for name in measures[0]},
            "latency_p50_ms": statistics.median(elapsed),
            "latency_p95_ms": sorted(elapsed)[int(0.95 * (len(elapsed) - 1))],
        }
    report["profiles"] = results
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    text = json.dumps(evaluate(), indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
