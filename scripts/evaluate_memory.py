"""Reproducible synthetic ranking comparison. No database or real patient data."""

import argparse
import json
import statistics
from datetime import timedelta
from pathlib import Path
from time import perf_counter

from t1d_memory.benchmark import Benchmark, JudgedQuery, evaluate_benchmark
from t1d_memory.contracts import ProfileName
from t1d_memory.episodes import build_episodes
from t1d_memory.evaluation import metrics
from t1d_memory.ranking import cosine, embed, rank
from t1d_memory.synthetic import PATIENT, START, STUDY, cohort


def synthetic_benchmark() -> Benchmark:
    episodes, _ = build_episodes(cohort(80), START + timedelta(days=30), STUDY, PATIENT)
    # Fictional incremental materialization, immediately after the last fictional
    # CGM sample is available. Never rewrite availability in the live store.
    episodes = [
        e.model_copy(update={"available_at": e.end_at + timedelta(seconds=1)}) for e in episodes
    ]
    history, queries = episodes[:60], episodes[60:]
    return Benchmark(
        dataset_version="authored-synthetic-v1",
        data_kind="synthetic",
        judgment_method="synthetic-food-overlap",
        protocol_version="food-overlap-simulated-availability-v1",
        episodes=tuple(history),
        queries=tuple(
            JudgedQuery(
                query_id=q.id,
                study_id=q.study_id,
                patient_id=q.patient_id,
                anchor_meal_id=q.anchor_id,
                input_cutoff=q.start_at,
                foods=q.foods,
                nutrients=q.nutrients,
                judgments={e.id: 1 if set(e.foods) & set(q.foods) else 0 for e in history},
            )
            for q in queries
        ),
    )


def evaluate() -> dict[str, object]:
    benchmark = synthetic_benchmark()
    history, queries = list(benchmark.episodes), benchmark.queries
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
            "In-process profile scoring/ranking, not service latency; excludes feature preparation",
            "Hash feature vectors are not pretrained semantic embeddings",
            "No forecasting outcome improvement established",
        ],
    }
    results = {}
    history_vectors = {e.id: embed(e.foods) for e in history}
    for profile in profiles:
        measures = []
        elapsed = []
        for query in queries:
            relevant = {str(e.id) for e in history if set(e.foods) & set(query.foods)}
            query_vector = embed(query.foods)
            started = perf_counter()
            vectors = (
                None
                if profile == "structured-v1"
                else {str(e.id): cosine(history_vectors[e.id], query_vector) for e in history}
            )
            graph = (
                None
                if profile != "hybrid-v1"
                else {
                    str(e.id): len(set(e.foods) & set(query.foods))
                    / len(set(e.foods) | set(query.foods))
                    for e in history
                }
            )
            result = rank(history, query.foods, query.nutrients, profile, 5, vectors, graph)
            elapsed.append((perf_counter() - started) * 1000)
            measures.append(metrics([str(e.episode_id) for e in result], relevant, 5))
        results[profile] = {
            **{name: statistics.mean(row[name] for row in measures) for name in measures[0]},
            "latency_p50_ms": statistics.median(elapsed),
            "latency_p95_ms": sorted(elapsed)[int(0.95 * (len(elapsed) - 1))],
        }
    report["profiles"] = results
    report["patient_clustered_evaluation"] = evaluate_benchmark(benchmark)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--judged-input",
        type=Path,
        help="Governed offline Benchmark JSON with exhaustive independent judgments",
    )
    parser.add_argument("--export-template", type=Path, help="Write fictional benchmark input")
    parser.add_argument("--export-schema", type=Path, help="Write benchmark JSON Schema")
    args = parser.parse_args()
    if args.export_template:
        args.export_template.parent.mkdir(parents=True, exist_ok=True)
        args.export_template.write_text(
            synthetic_benchmark().model_dump_json(indent=2), encoding="utf-8"
        )
    if args.export_schema:
        args.export_schema.parent.mkdir(parents=True, exist_ok=True)
        args.export_schema.write_text(
            json.dumps(Benchmark.model_json_schema(), indent=2), encoding="utf-8"
        )
    if args.judged_input:
        try:
            if args.judged_input.stat().st_size > 20_000_000:
                raise ValueError("Input exceeds evaluation limit")
            report = evaluate_benchmark(
                Benchmark.model_validate_json(args.judged_input.read_bytes())
            )
        except (ValueError, OSError):
            parser.error("Invalid evaluation input; verify the schema, scope, cutoff and judgments")
    else:
        report = evaluate()
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
