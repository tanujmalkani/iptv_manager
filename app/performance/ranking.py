from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import exp, sqrt

from app.performance.aggregation import StreamPerformance


@dataclass(frozen=True, slots=True)
class RankedStream:
    performance: StreamPerformance
    rank: int
    score: float
    reliability_score: float
    speed_score: float
    p95_score: float
    evidence_score: float
    stability_score: float = 0.0
    resolution_score: float = 0.0


def _wilson_lower_bound(successes: int, total: int, z: float = 1.96) -> float:
    if total == 0:
        return 0.0
    proportion = successes / total
    denominator = 1.0 + z * z / total
    centre = proportion + z * z / (2.0 * total)
    margin = z * sqrt(
        proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total)
    )
    return max(0.0, (centre - margin) / denominator)


def _latency_score(milliseconds: float | None, scale_ms: float) -> float:
    if milliseconds is None:
        return 0.0
    return 100.0 * exp(-milliseconds / scale_ms)


def _resolution_pixels(resolution: str | None) -> int | None:
    if not resolution:
        return None
    match = re.search(r"(\d{2,5})\s*[x×]\s*(\d{2,5})", resolution.lower())
    if not match:
        return None
    width = int(match.group(1))
    height = int(match.group(2))
    pixels = width * height
    return pixels if pixels > 0 else None


def _resolution_scores(
    performances: Sequence[StreamPerformance],
    resolution_by_stream: Mapping[int, str | None] | None,
) -> dict[int, float]:
    if not resolution_by_stream:
        return {performance.stream_id: 0.0 for performance in performances}

    pixels_by_stream = {
        performance.stream_id: _resolution_pixels(
            resolution_by_stream.get(performance.stream_id)
        )
        for performance in performances
    }
    known_pixels = [pixels for pixels in pixels_by_stream.values() if pixels is not None]
    max_pixels = max(known_pixels, default=0)
    if max_pixels <= 0:
        return {performance.stream_id: 0.0 for performance in performances}

    return {
        stream_id: 100.0 * pixels / max_pixels if pixels is not None else 0.0
        for stream_id, pixels in pixels_by_stream.items()
    }


def rank_channel_streams(
    performances: Sequence[StreamPerformance],
) -> list[RankedStream]:
    """Rank streams with the original reliability-first scoring policy."""
    return rank_channel_streams_for_policy(
        performances,
        reliability_weight=0.60,
        speed_weight=0.20,
        p95_weight=0.10,
        stability_weight=0.00,
        evidence_weight=0.10,
        resolution_weight=0.00,
    )


def rank_channel_streams_for_policy(
    performances: Sequence[StreamPerformance],
    *,
    reliability_weight: float,
    speed_weight: float,
    p95_weight: float,
    stability_weight: float,
    evidence_weight: float,
    resolution_weight: float = 0.00,
    resolution_by_stream: Mapping[int, str | None] | None = None,
) -> list[RankedStream]:
    """Rank streams using configurable weights while keeping common score components."""
    resolution_scores = _resolution_scores(performances, resolution_by_stream)
    ranked: list[RankedStream] = []
    for performance in performances:
        reliability = 100.0 * _wilson_lower_bound(
            performance.successful_tests,
            performance.total_tests,
        )
        speed = _latency_score(performance.median_first_frame_ms, 1500.0)
        p95 = _latency_score(performance.p95_first_frame_ms, 3000.0)
        evidence = min(performance.total_tests / 10.0, 1.0) * 100.0
        stability = 100.0 * performance.stability_rate
        resolution = resolution_scores.get(performance.stream_id, 0.0)
        score = (
            reliability * reliability_weight
            + speed * speed_weight
            + p95 * p95_weight
            + stability * stability_weight
            + evidence * evidence_weight
            + resolution * resolution_weight
        )
        ranked.append(
            RankedStream(
                performance=performance,
                rank=0,
                score=score,
                reliability_score=reliability,
                speed_score=speed,
                p95_score=p95,
                evidence_score=evidence,
                stability_score=stability,
                resolution_score=resolution,
            )
        )

    ranked.sort(
        key=lambda item: (
            -item.score,
            -item.performance.success_rate,
            item.performance.median_first_frame_ms
            if item.performance.median_first_frame_ms is not None
            else float("inf"),
            -item.performance.total_tests,
            item.performance.stream_id,
        )
    )
    return [
        RankedStream(
            performance=item.performance,
            rank=index,
            score=item.score,
            reliability_score=item.reliability_score,
            speed_score=item.speed_score,
            p95_score=item.p95_score,
            evidence_score=item.evidence_score,
            stability_score=item.stability_score,
            resolution_score=item.resolution_score,
        )
        for index, item in enumerate(ranked, start=1)
    ]
