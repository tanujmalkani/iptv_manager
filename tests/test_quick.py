from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import Base, Channel, ChannelStream, Stream, StreamTest
from app.db.models.enums import TestResult as QuickTestResultEnum
from app.db.models.enums import TestRunStatus as QuickTestRunStatus
from app.testing import QuickTestResult, QuickTestRunner


class FakeQuickEngine:
    timeout_seconds = 10.0
    ffmpeg_binary = "ffmpeg"

    def __init__(self, results: dict[str, QuickTestResult]) -> None:
        self.results = results
        self.calls: list[str] = []

    def test(self, url: str) -> QuickTestResult:
        self.calls.append(url)
        return self.results[url]


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_quick_runner_tests_distinct_playable_streams_once_and_persists_results() -> None:
    session = make_session()
    try:
        channel = Channel(canonical_name="News", normalized_name="news")
        first = Stream(
            url="https://example.test/one.m3u8",
            normalized_url="https://example.test/one.m3u8",
            stream_kind="media_playlist",
        )
        second = Stream(
            url="https://example.test/two.m3u8",
            normalized_url="https://example.test/two.m3u8",
            stream_kind="media_playlist",
        )
        session.add_all([channel, first, second])
        session.flush()
        session.add_all(
            [
                ChannelStream(channel_id=channel.id, stream_id=first.id),
                ChannelStream(channel_id=channel.id, stream_id=second.id),
            ]
        )
        session.commit()

        fake = FakeQuickEngine(
            {
                first.url: QuickTestResult(
                    result=QuickTestResultEnum.SUCCESS,
                    available=True,
                    first_frame_ms=321.5,
                    test_duration_ms=350.0,
                ),
                second.url: QuickTestResult(
                    result=QuickTestResultEnum.FAILED,
                    available=False,
                    error_stage="decoder",
                    error_message="No video",
                    test_duration_ms=1000.0,
                ),
            }
        )

        test_run = QuickTestRunner(fake).run(session)

        assert test_run.status == QuickTestRunStatus.COMPLETED.value
        assert test_run.total_streams == 2
        assert test_run.completed_streams == 2
        assert test_run.successful_streams == 1
        assert test_run.failed_streams == 1
        assert fake.calls == [first.url, second.url]

        tests = session.scalars(
            select(StreamTest).order_by(StreamTest.stream_id)
        ).all()
        assert len(tests) == 2
        assert tests[0].first_frame_ms == 321.5
        assert tests[0].available is True
        assert tests[1].available is False
        assert tests[1].error_stage == "decoder"
    finally:
        session.close()


def test_quick_runner_deduplicates_streams_shared_by_channels() -> None:
    session = make_session()
    try:
        first_channel = Channel(canonical_name="One", normalized_name="one")
        second_channel = Channel(canonical_name="Two", normalized_name="two")
        stream = Stream(
            url="https://example.test/shared.m3u8",
            normalized_url="https://example.test/shared.m3u8",
            stream_kind="media_playlist",
        )
        session.add_all([first_channel, second_channel, stream])
        session.flush()
        session.add_all(
            [
                ChannelStream(channel_id=first_channel.id, stream_id=stream.id),
                ChannelStream(channel_id=second_channel.id, stream_id=stream.id),
            ]
        )
        session.commit()

        fake = FakeQuickEngine(
            {
                stream.url: QuickTestResult(
                    result=QuickTestResultEnum.SUCCESS,
                    available=True,
                    first_frame_ms=125.0,
                )
            }
        )

        test_run = QuickTestRunner(fake).run(session)

        assert test_run.total_streams == 1
        assert test_run.completed_streams == 1
        assert fake.calls == [stream.url]
        assert len(session.scalars(select(StreamTest)).all()) == 1
    finally:
        session.close()
