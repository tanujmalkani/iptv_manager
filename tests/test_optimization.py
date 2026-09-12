from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.optimization import OptimizationProfile, build_channel_optimization


def _test(
    stream_id: int,
    *,
    available: bool,
    first_frame_ms: float | None,
    minute: int,
    test_type: str = "quick",
    error_type: str | None = None,
) -> SimpleNamespace:
    completed_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=minute)
    return SimpleNamespace(
        stream_id=stream_id,
        available=available,
        result="success" if available else "failed",
        test_type=test_type,
        error_type=error_type,
        first_frame_ms=first_frame_ms,
        throughput_bps=4_000_000 if available else None,
        extra_metrics={"stable": available, "observed_fps": 25.0 if available else None},
        completed_at=completed_at,
        started_at=completed_at - timedelta(seconds=10),
    )


def _channel() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        canonical_name="News",
        streams=[
            SimpleNamespace(stream_id=10),
            SimpleNamespace(stream_id=20),
        ],
    )


def test_fast_profile_prefers_low_startup_for_eligible_streams() -> None:
    tests = {
        10: [_test(10, available=True, first_frame_ms=100, minute=index) for index in range(4)],
        20: [_test(20, available=True, first_frame_ms=500, minute=index + 4) for index in range(4)],
    }

    result = build_channel_optimization(_channel(), tests, profile=OptimizationProfile.FAST)

    assert result.primary_stream_id == 10
    assert [item.performance.stream_id for item in result.candidates] == [10, 20]


def test_fast_profile_uses_resolution_to_offset_small_speed_improvement() -> None:
    tests = {
        10: [_test(10, available=True, first_frame_ms=100, minute=index) for index in range(4)],
        20: [_test(20, available=True, first_frame_ms=110, minute=index + 4) for index in range(4)],
    }

    result = build_channel_optimization(
        _channel(),
        tests,
        profile=OptimizationProfile.FAST,
        resolution_by_stream={10: "1280x720", 20: "1920x1080"},
    )

    assert result.primary_stream_id == 20
    assert result.candidates[0].resolution_score == 100.0
    assert result.candidates[1].resolution_score < result.candidates[0].resolution_score


def test_reliable_profile_excludes_flaky_stream() -> None:
    tests = {
        10: [
            _test(10, available=True, first_frame_ms=100, minute=0),
            _test(10, available=False, first_frame_ms=None, minute=1),
            _test(10, available=True, first_frame_ms=100, minute=2),
            _test(10, available=False, first_frame_ms=None, minute=3),
        ],
        20: [_test(20, available=True, first_frame_ms=500, minute=index + 4) for index in range(4)],
    }

    result = build_channel_optimization(_channel(), tests, profile=OptimizationProfile.RELIABLE)

    assert result.primary_stream_id == 20
    assert [item.performance.stream_id for item in result.candidates] == [20]


def test_all_profile_keeps_all_successful_candidates() -> None:
    tests = {
        10: [_test(10, available=True, first_frame_ms=100, minute=0)],
        20: [_test(20, available=True, first_frame_ms=500, minute=1)],
    }

    result = build_channel_optimization(_channel(), tests, profile=OptimizationProfile.ALL)

    assert {item.performance.stream_id for item in result.candidates} == {10, 20}
    assert result.primary_stream_id == 10


def test_fast_profile_accepts_successful_deep_validation_after_quick_decoder_failure() -> None:
    tests = {
        10: [
            _test(
                10,
                available=False,
                first_frame_ms=None,
                minute=0,
                test_type="quick",
                error_type="decoder_error",
            ),
            _test(10, available=False, first_frame_ms=None, minute=1, test_type="quick"),
            _test(10, available=True, first_frame_ms=120, minute=2, test_type="deep"),
        ],
        20: [_test(20, available=True, first_frame_ms=500, minute=3)],
    }

    result = build_channel_optimization(_channel(), tests, profile=OptimizationProfile.FAST)

    assert result.primary_stream_id == 10
    assert [item.performance.stream_id for item in result.candidates] == [10, 20]
