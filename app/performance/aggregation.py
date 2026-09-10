from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import mean, median

from app.db.models import StreamTest


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


@dataclass(frozen=True, slots=True)
class StreamPerformance:
    stream_id: int
    total_tests: int
    successful_tests: int
    failed_tests: int
    success_rate: float
    median_first_frame_ms: float | None
    average_first_frame_ms: float | None
    p95_first_frame_ms: float | None
    median_playback_duration_ms: float | None
    average_fps: float | None
    median_throughput_bps: float | None
    average_throughput_bps: float | None
    stable_tests: int
    stability_rate: float
    last_tested_at: datetime | None


def aggregate_stream_tests(
    stream_id: int,
    tests: Sequence[StreamTest],
) -> StreamPerformance:
    """Aggregate historical observations for one stream.

    Startup latency and throughput statistics use successful observations only.
    Failed attempts remain part of reliability and stability calculations so a
    fast stream cannot look healthy merely because its successful attempts were fast.
    """
    stream_tests = [test for test in tests if test.stream_id == stream_id]
    total = len(stream_tests)
    successful = sum(1 for test in stream_tests if test.available)
    failed = total - successful
    success_rate = successful / total if total else 0.0

    first_frames = [
        float(test.first_frame_ms)
        for test in stream_tests
        if test.available and test.first_frame_ms is not None
    ]
    playback_durations = [
        float(test.extra_metrics["playback_duration_ms"])
        for test in stream_tests
        if test.available
        and test.extra_metrics.get("playback_duration_ms") is not None
    ]
    fps_values = [
        float(test.extra_metrics["observed_fps"])
        for test in stream_tests
        if test.available and test.extra_metrics.get("observed_fps") is not None
    ]
    throughput_values = [
        float(test.throughput_bps)
        for test in stream_tests
        if test.available and test.throughput_bps is not None
    ]
    stable_tests = sum(1 for test in stream_tests if bool(test.extra_metrics.get("stable")))
    stability_rate = stable_tests / total if total else 0.0

    timestamps = [
        timestamp
        for test in stream_tests
        for timestamp in (test.completed_at, test.started_at)
        if timestamp is not None
    ]

    return StreamPerformance(
        stream_id=stream_id,
        total_tests=total,
        successful_tests=successful,
        failed_tests=failed,
        success_rate=success_rate,
        median_first_frame_ms=median(first_frames) if first_frames else None,
        average_first_frame_ms=mean(first_frames) if first_frames else None,
        p95_first_frame_ms=_percentile(first_frames, 0.95),
        median_playback_duration_ms=median(playback_durations) if playback_durations else None,
        average_fps=mean(fps_values) if fps_values else None,
        median_throughput_bps=median(throughput_values) if throughput_values else None,
        average_throughput_bps=mean(throughput_values) if throughput_values else None,
        stable_tests=stable_tests,
        stability_rate=stability_rate,
        last_tested_at=max(timestamps) if timestamps else None,
    )
