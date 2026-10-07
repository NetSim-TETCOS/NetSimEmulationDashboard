from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from typing import Any


def percentile(values: Sequence[float], percent: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil((percent / 100) * len(ordered)))
    return round(float(ordered[rank - 1]), 2)


def calculate_rtt_metrics(
    samples: Sequence[float], timeout_count: int = 0, baseline_size: int = 10
) -> dict[str, Any]:
    values = [float(value) for value in samples if value >= 0]
    total = len(values) + timeout_count
    baseline_values = values[:baseline_size]
    current = values[-1] if values else None
    baseline = statistics.fmean(baseline_values) if len(baseline_values) >= baseline_size else None
    jitter = (
        statistics.fmean(abs(right - left) for left, right in zip(values, values[1:]))
        if len(values) > 1
        else 0.0
    )
    result = {
        "current_rtt": current,
        "min_rtt": min(values) if values else None,
        "max_rtt": max(values) if values else None,
        "mean_rtt": statistics.fmean(values) if values else None,
        "median_rtt": statistics.median(values) if values else None,
        "p95_rtt": percentile(values, 95),
        "jitter": jitter,
        "success_count": len(values),
        "timeout_count": timeout_count,
        "timeout_percentage": (timeout_count / total * 100) if total else 0.0,
        "baseline_rtt": baseline,
        "baseline_sample_count": min(len(values), baseline_size),
        "baseline_complete": len(baseline_values) >= baseline_size,
    }
    result["rtt_delta"] = current - baseline if current is not None and baseline is not None else None
    result["rtt_increase_percentage"] = (
        ((current - baseline) / baseline * 100)
        if current is not None and baseline not in (None, 0)
        else None
    )
    return {key: round(value, 2) if isinstance(value, float) else value for key, value in result.items()}
