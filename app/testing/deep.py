from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import StreamTest, TestRun
from app.db.models.enums import TestType
from app.testing.stream import StreamTestEngine, StreamTestRunner


DeepTestEngine = StreamTestEngine


class DeepTestRunner(StreamTestRunner):
    """Persist sustained playback observations as deep-test history."""

    @staticmethod
    def _next_attempt_number(session: Session, test_run_id: int, stream_id: int) -> int:
        del test_run_id
        latest = session.scalar(
            select(func.max(StreamTest.attempt_number)).where(
                StreamTest.stream_id == stream_id,
                StreamTest.test_type == TestType.DEEP.value,
            )
        )
        return (latest or 0) + 1

    def run(self, session: Session, **kwargs) -> TestRun:
        test_run = super().run(session, **kwargs)
        for stream_test in test_run.stream_tests:
            stream_test.test_type = TestType.DEEP.value
        test_run.profile = TestType.DEEP.value
        test_run.configuration_json = {
            **test_run.configuration_json,
            "test_type": TestType.DEEP.value,
        }
        session.commit()
        session.refresh(test_run)
        return test_run
