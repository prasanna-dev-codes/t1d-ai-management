"""Independent ranking metrics; synthetic labels do not establish clinical relevance."""

import math
from collections.abc import Sequence


def metrics(retrieved: Sequence[str], relevant: set[str], k: int) -> dict[str, float]:
    if k < 1 or len(retrieved) != len(set(retrieved)):
        raise ValueError("Positive k and unique ranked identities required")
    selected = list(retrieved[:k])
    hits = [int(identity in relevant) for identity in selected]
    precision = sum(hits) / k
    recall = sum(hits) / len(relevant) if relevant else 0.0
    dcg = sum(hit / math.log2(index + 2) for index, hit in enumerate(hits))
    ideal = sum(1 / math.log2(index + 2) for index in range(min(k, len(relevant))))
    reciprocal = next((1 / (i + 1) for i, h in enumerate(hits) if h), 0.0)
    return {
        "precision_at_k": precision,
        "recall_at_k": recall,
        "ndcg_at_k": dcg / ideal if ideal else 0.0,
        "reciprocal_rank": reciprocal,
    }
