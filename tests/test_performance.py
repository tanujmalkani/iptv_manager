from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.performance import aggregate_stream_tests, rank_channel_streams
from app.performance.ranking import _wilson_lower_bound


def _test(
    stream_id: int,
    *,
    available: bool,
    first_frame_ms: float | None,
    stable: bool,
    fps: float | None,
    throughput_bps: float | None = None,
    completed_at: datetime,
) -> SimpleNamespace:
    return SimpleNamespace(
        stream_id=stream_id,
        available=available,
        first_frame_ms=first_frame_ms,
        throughput_bps=throughput_bps,
        extra_metrics={
            "stable": stable,
            "observed_fps": fps,
            "playback_duration_ms": 10_000.0 if stable else 2_000.0,
        },
        completed_at=completed_at,
        started_at=completed_at - timedelta(seconds=10),
    )


def test_aggregate_uses_only_successes_for_startup_latency() -> None:
    now = datetime.now(UTC)
    tests = [
        _test(
            12,
            available=True,
            first_frame_ms=200,
            stable=True,
            fps=25,
            completed_at=now,
        ),
        _test(
            12,
            available=True,
            first_frame_ms=400,
            stable=True,
            fps=25,
            completed_at=now + timedelta(minutes=1),
        ),
        _test(
            12,
            available=False,
            first_frame_ms=None,
            stable=False,
            fps=None,
            completed_at=now + timedelta(minutes=2),
        ),
    ]

    performance = aggregate_stream_tests(12, tests)

    assert performance.total_tests == 3
    assert performance.successful_tests == 2
    assert performance.failed_tests == 1
    assert performance.success_rate == 2 / 3
    assert performance.median_first_frame_ms == 300
    assert performance.average_first_frame_ms == 300
    assert performance.p95_first_frame_ms == 390
    assert performance.stable_tests == 2
    assert performance.stability_rate == 2 / 3
    assert performance.average_fps == 25
    assert performance.last_tested_at == now + timedelta(minutes=2)


def test_aggregate_tracks_successful_throughput() -> None:
    now = datetime.now(UTC)
    tests = [
        _test(
            12,
            available=True,
            first_frame_ms=200,
            stable=True,
            fps=25,
            throughput_bps=4_000_000,
            completed_at=now,
        ),
        _test(
            12,
            available=True,
            first_frame_ms=300,
            stable=True,
            fps=25,
            throughput_bps=6_000_000,
            completed_at=now + timedelta(minutes=1),
        ),
        _test(
            12,
            available=False,
            first_frame_ms=None,
            stable=False,
            fps=None,
            throughput_bps=None,
            completed_at=now + timedelta(minutes=2),
        ),
    ]

    performance = aggregate_stream_tests(12, tests)

    assert performance.median_throughput_bps == 5_000_000
    assert performance.average_throughput_bps == 5_000_000


def test_empty_stream_has_no_performance_values() -> None:
    performance = aggregate_stream_tests(99, [])

    assert performance.total_tests == 0
    assert performance.success_rate == 0
    assert performance.median_first_frame_ms is None
    assert performance.median_throughput_bps is None
    assert performance.p95_first_frame_ms is None
    assert performance.last_tested_at is None


def test_wilson_bound_rewards_evidence() -> None:
    assert _wilson_lower_bound(1, 1) < _wilson_lower_bound(8, 8)
    assert _wilson_lower_bound(8, 8) < 1.0
    assert _wilson_lower_bound(0, 8) == 0.0


def test_ranking_prioritizes_reliability_over_one_fast_sample() -> None:
    now = datetime.now(UTC)
    reliable = aggregate_stream_tests(
        12,
        [
            _test(
                12,
                available=True,
                first_frame_ms=500,
                stable=True,
                fps=25,
                completed_at=now + timedelta(minutes=i),
            )
            for i in range(8)
        ],
    )
    fast_but_flaky = aggregate_stream_tests(
        13,
        [
            _test(13, available=True, first_frame_ms=100, stable=True, fps=25, completed_at=now),
            *[
                _test(
                    13,
                    available=False,
                    first_frame_ms=None,
                    stable=False,
                    fps=None,
                    completed_at=now + timedelta(minutes=i + 1),
                )
                for i in range(7)
            ],
        ],
    )

    ranked = rank_channel_streams([reliable, fast_but_flaky])

    assert ranked[0].performance.stream_id == 12
    assert ranked[0].rank == 1
    assert ranked[1].rank == 2
