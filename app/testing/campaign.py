from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from threading import Event
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Stream, StreamTest, TestRun
from app.db.models.enums import ErrorType, TestResult, TestRunStatus, TestType
from app.testing.quick import QuickTestEngine, QuickTestResult, QuickTestRunner

_DEFAULT_CONCURRENCY = 4
_MAX_CONCURRENCY = 32


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TestCampaignRunner:
    """Run a batch of stream tests concurrently and persist results safely."""

    def __init__(
        self,
        engine: QuickTestEngine,
        *,
        test_type: str,
        concurrency: int = _DEFAULT_CONCURRENCY,
    ) -> None:
        if test_type not in {TestType.QUICK.value, TestType.DEEP.value}:
            raise ValueError("test_type must be quick or deep")
        if not 1 <= concurrency <= _MAX_CONCURRENCY:
            raise ValueError(f"concurrency must be between 1 and {_MAX_CONCURRENCY}")
        self.engine = engine
        self.test_type = test_type
        self.concurrency = concurrency

    def run(
        self,
        session: Session,
        *,
        name: str,
        source_playlist_id: int | None = None,
        stream_ids: list[int] | None = None,
        on_result: Callable[[StreamTest, int, int], None] | None = None,
        existing_test_run: TestRun | None = None,
        cancel_event: Event | None = None,
    ) -> TestRun:
        selector = QuickTestRunner(self.engine)
        streams = selector._select_streams(session, source_playlist_id, stream_ids)
        test_run = existing_test_run

        if test_run is None:
            test_run = TestRun(
                source_playlist_id=source_playlist_id,
                name=name,
                profile=self.test_type,
                status=TestRunStatus.RUNNING.value,
                started_at=_utcnow(),
                total_streams=len(streams),
                configuration_json=self._configuration(),
            )
            session.add(test_run)
            session.flush()
        else:
            test_run.status = TestRunStatus.RUNNING.value
            test_run.started_at = _utcnow()
            test_run.total_streams = len(streams)
            test_run.completed_streams = 0
            test_run.successful_streams = 0
            test_run.failed_streams = 0
            test_run.configuration_json = {
                **test_run.configuration_json,
                **self._configuration(),
            }
            session.commit()

        try:
            results, cancelled = self._test_streams(streams, cancel_event=cancel_event)
            for index, stream in enumerate((s for s in streams if s.id in results), start=1):
                result = results[stream.id]
                stream_test = self._persist_result(session, test_run, stream, result)
                test_run.completed_streams += 1
                if result.available:
                    test_run.successful_streams += 1
                else:
                    test_run.failed_streams += 1
                session.commit()
                session.refresh(test_run)
                session.refresh(stream_test)
                if on_result is not None:
                    on_result(stream_test, index, len(streams))

            test_run.status = (
                TestRunStatus.CANCELLED.value if cancelled else TestRunStatus.COMPLETED.value
            )
            test_run.completed_at = _utcnow()
            test_run.configuration_json = {
                **test_run.configuration_json,
                "cancelled": cancelled,
            }
            session.commit()
            session.refresh(test_run)
            return test_run
        except Exception:
            test_run.status = TestRunStatus.FAILED.value
            test_run.completed_at = _utcnow()
            session.commit()
            raise

    def _test_streams(
        self,
        streams: list[Stream],
        *,
        cancel_event: Event | None = None,
    ) -> tuple[dict[int, QuickTestResult], bool]:
        if not streams:
            return {}, bool(cancel_event and cancel_event.is_set())

        executor = ThreadPoolExecutor(
            max_workers=min(self.concurrency, len(streams)),
            thread_name_prefix=f"{self.test_type}-campaign",
        )
        futures = {
            executor.submit(self._safe_test, stream.url): stream.id for stream in streams
        }
        results: dict[int, QuickTestResult] = {}
        cancelled = False
        try:
            for future in as_completed(futures):
                if future.cancelled():
                    cancelled = True
                    continue
                results[futures[future]] = future.result()
                if cancel_event is not None and cancel_event.is_set():
                    cancelled = True
                    break
        finally:
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
            executor.shutdown(wait=True, cancel_futures=cancelled)
            for future, stream_id in futures.items():
                if stream_id in results or future.cancelled() or not future.done():
                    continue
                results[stream_id] = future.result()
        return results, cancelled

    def _safe_test(self, url: str) -> QuickTestResult:
        started = _utcnow()
        try:
            return self.engine.test(url)
        except Exception as exc:
            return QuickTestResult(
                result=TestResult.FAILED,
                available=False,
                error_stage="runner",
                error_type=ErrorType.UNKNOWN,
                error_message=str(exc),
                test_duration_ms=(_utcnow() - started).total_seconds() * 1000.0,
            )

    def _persist_result(
        self,
        session: Session,
        test_run: TestRun,
        stream: Stream,
        result: QuickTestResult,
    ) -> StreamTest:
        stream_test = StreamTest(
            test_run_id=test_run.id,
            stream_id=stream.id,
            attempt_number=self._next_attempt_number(session, stream.id),
            test_type=self.test_type,
            result=result.result.value,
            started_at=_utcnow(),
            completed_at=_utcnow(),
            available=result.available,
            error_stage=result.error_stage,
            error_type=result.error_type.value if result.error_type else None,
            error_message=result.error_message,
            dns_ms=result.dns_ms,
            connect_ms=result.connect_ms,
            tls_ms=result.tls_ms,
            http_response_ms=result.http_response_ms,
            manifest_ms=result.manifest_ms,
            first_data_ms=result.first_data_ms,
            first_frame_ms=result.first_frame_ms,
            bytes_received=result.bytes_received,
            test_duration_ms=result.test_duration_ms,
            throughput_bps=result.extra_metrics.get("throughput_bps"),
            extra_metrics=result.extra_metrics,
        )
        session.add(stream_test)
        return stream_test

    def _configuration(self) -> dict[str, object]:
        configuration: dict[str, object] = {
            "test_type": self.test_type,
            "timeout_seconds": self.engine.timeout_seconds,
            "ffmpeg_binary": self.engine.ffmpeg_binary,
            "concurrency": self.concurrency,
        }
        playback_duration = getattr(self.engine, "playback_duration_seconds", None)
        if playback_duration is not None:
            configuration["playback_duration_seconds"] = playback_duration
        return configuration

    def _next_attempt_number(self, session: Session, stream_id: int) -> int:
        latest = session.scalar(
            select(func.max(StreamTest.attempt_number)).where(
                StreamTest.stream_id == stream_id,
                StreamTest.test_type == self.test_type,
            )
        )
        return (latest or 0) + 1
