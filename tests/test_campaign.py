from __future__ import annotations

import threading
import time

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import Base, Channel, ChannelStream, Stream, StreamTest
from app.db.models.enums import TestResult, TestRunStatus
from app.testing.campaign import TestCampaignRunner
from app.testing.quick import QuickTestResult


class FakeCampaignEngine:
    timeout_seconds = 10.0
    ffmpeg_binary = "ffmpeg"

    def __init__(self, *, delay: float = 0.05) -> None:
        self.delay = delay
        self.calls: list[str] = []
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def test(self, url: str) -> QuickTestResult:
        with self._lock:
            self.calls.append(url)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(self.delay)
            return QuickTestResult(
                result=TestResult.SUCCESS,
                available=True,
                first_frame_ms=100.0,
                test_duration_ms=self.delay * 1000,
            )
        finally:
            with self._lock:
                self.active -= 1


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def add_streams(session: Session, count: int) -> list[Stream]:
    channel = Channel(canonical_name="News", normalized_name="news")
    streams = [
        Stream(
            url=f"https://example.test/{index}.m3u8",
            normalized_url=f"https://example.test/{index}.m3u8",
            stream_kind="media_playlist",
        )
        for index in range(count)
    ]
    session.add(channel)
    session.add_all(streams)
    session.flush()
    session.add_all(
        [ChannelStream(channel_id=channel.id, stream_id=stream.id) for stream in streams]
    )
    session.commit()
    return streams


def test_campaign_runs_streams_concurrently_and_persists_results() -> None:
    session = make_session()
    try:
        streams = add_streams(session, 6)
        engine = FakeCampaignEngine()
        runner = TestCampaignRunner(engine, test_type="quick", concurrency=3)

        test_run = runner.run(session, name="Quick Campaign")

        assert test_run.status == TestRunStatus.COMPLETED.value
        assert test_run.total_streams == 6
        assert test_run.completed_streams == 6
        assert test_run.successful_streams == 6
        assert test_run.failed_streams == 0
        assert engine.max_active == 3
        assert sorted(engine.calls) == sorted(stream.url for stream in streams)
        assert test_run.configuration_json["concurrency"] == 3
        assert len(session.scalars(select(StreamTest)).all()) == 6
    finally:
        session.close()


def test_campaign_records_worker_exceptions_as_failed_results() -> None:
    session = make_session()
    try:
        streams = add_streams(session, 2)

        class FailingEngine(FakeCampaignEngine):
            def test(self, url: str) -> QuickTestResult:
                if url == streams[1].url:
                    raise RuntimeError("worker exploded")
                return super().test(url)

        test_run = TestCampaignRunner(
            FailingEngine(),
            test_type="quick",
            concurrency=2,
        ).run(session, name="Failure Campaign")

        assert test_run.status == TestRunStatus.COMPLETED.value
        assert test_run.successful_streams == 1
        assert test_run.failed_streams == 1
        failed = session.scalar(
            select(StreamTest).where(StreamTest.stream_id == streams[1].id)
        )
        assert failed is not None
        assert failed.error_stage == "runner"
        assert "worker exploded" in (failed.error_message or "")
    finally:
        session.close()


def test_campaign_rejects_invalid_concurrency() -> None:
    engine = FakeCampaignEngine()
    try:
        TestCampaignRunner(engine, test_type="quick", concurrency=0)
    except ValueError as exc:
        assert "between 1 and 32" in str(exc)
    else:
        raise AssertionError("Expected invalid concurrency to raise ValueError")
