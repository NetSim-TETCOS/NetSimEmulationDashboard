from backend.app.metrics import calculate_rtt_metrics, percentile


def test_percentile_uses_nearest_rank() -> None:
    assert percentile(list(range(1, 101)), 95) == 95.0
    assert percentile([], 95) is None


def test_rtt_metrics_baseline_jitter_and_timeout() -> None:
    samples = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110]
    metrics = calculate_rtt_metrics(samples, timeout_count=1)
    assert metrics["current_rtt"] == 110.0
    assert metrics["baseline_rtt"] == 55.0
    assert metrics["median_rtt"] == 60.0
    assert metrics["jitter"] == 10.0
    assert metrics["rtt_delta"] == 55.0
    assert metrics["success_count"] == 11
    assert metrics["timeout_percentage"] == 8.33


def test_baseline_waits_for_ten_valid_samples() -> None:
    metrics = calculate_rtt_metrics([12, 14, 16])
    assert metrics["baseline_rtt"] is None
    assert metrics["baseline_sample_count"] == 3
    assert metrics["baseline_complete"] is False
