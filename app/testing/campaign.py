from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from threading import Event

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
            raise ValueError(f"Unsupported test type: {test_type}")
        if not 1 <= concurrency <= _MAX_CONCURRENCY:
            raise ValueError(f"Concurrency must be between 1 and {_MAX_CONCURRENCY}")
        self.engine = engine
        self.test_type = test_type
        self.concurrency = concurrency

    def run(
        self,
        session: Session,
        *,
        source_playlist_id: int | None = None,
        stream_ids: set[int] | None = None,
        test_run: TestRun | None = None,
        cancel_event: Event | None = None,
    ) -> TestRun:
        selector = QuickTestRunner(self.engine)
        streams = selector._select_streams(session, source_playlist_id, stream_ids)
        if test_run is None:
            test_run = TestRun(
                profile=self.test_type,
                status=TestRunStatus.PENDING,
                started_at=_utcnow(),
                configuration_json={
                    "test_type": self.test_type,
                    "concurrency": self.concurrency,
                },
            )
            session.add(test_run)
            session.flush()

        test_run.status = TestRunStatus.RUNNING
        test_run.started_at = _utcnow()
        test_run.configuration_json = {
            **(test_run.configuration_json or {}),
            "test_type": self.test_type,
            "concurrency": self.concurrency,
        }
        session.commit()

        results, cancelled = self._test_streams(streams, cancel_event)
        for stream in streams:
            result = results.get(stream.id)
            if result is None:
                continue
            started_at = _utcnow()
            stream_test = StreamTest(
                stream_id=stream.id,
                test_run_id=test_run.id,
                test_type=self.test_type,
                attempt_number=self._next_attempt_number(session, stream.id, self.test_type),
                started_at=started_at,
                completed_at=_utcnow(),
                result=TestResult.SUCCESS if result.success else TestResult.FAILURE,
                error_type=result.error_type or ErrorType.NONE,
                error_message=result.error_message,
                metrics_json=result.metrics,
            )
            session.add(stream_test)
        test_run.configuration_json = {
            **(test_run.configuration_json or {}),
            "cancelled": cancelled,
        }
        test_run.status = TestRunStatus.CANCELLED if cancelled else TestRunStatus.COMPLETED
        test_run.completed_at = _utcnow()
        session.commit()
        return test_run

    def _test_streams(
        self,
        streams: list[Stream],
        cancel_event: Event | None,
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
        try:
            if self.test_type == TestType.DEEP.value:
                return self.engine.test(url, deep=True)
            return self.engine.test(url, deep=False)
        except Exception as exc:  # noqa: BLE001
            return QuickTestResult(
                success=False,
                error_type=ErrorType.EXCEPTION.value,
                error_message=str(exc),
                metrics={},
            )

    @staticmethod
    def _next_attempt_number(session: Session, stream_id: int, test_type: str) -> int:
        current = session.scalar(
            select(func.max(StreamTest.attempt_number)).where(
                StreamTest.stream_id == stream_id,
                StreamTest.test_type == test_type,
            )
        )
        return (current or 0) + 1
