from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import TestRun
from app.db.models.enums import TestRunStatus
from app.db.session import SessionLocal, get_db
from app.testing.stream import StreamTestEngine, StreamTestRunner

router = APIRouter(prefix="/api", tags=["testing"])
DbSession = Annotated[Session, Depends(get_db)]


def _run_stream_tests(
    test_run_id: int,
    source_playlist_id: int | None,
    stream_ids: list[int] | None,
    timeout_seconds: float,
    playback_duration_seconds: float,
    ffmpeg_binary: str,
) -> None:
    with SessionLocal() as session:
        test_run = session.get(TestRun, test_run_id)
        if test_run is None:
            return
        try:
            runner = StreamTestRunner(
                StreamTestEngine(
                    timeout_seconds=timeout_seconds,
                    playback_duration_seconds=playback_duration_seconds,
                    ffmpeg_binary=ffmpeg_binary,
                )
            )
            runner.run(
                session,
                name=test_run.name,
                source_playlist_id=source_playlist_id,
                stream_ids=stream_ids,
            )
        except Exception as exc:
            test_run.status = TestRunStatus.FAILED.value
            test_run.configuration_json = {
                **test_run.configuration_json,
                "error": str(exc),
            }
            session.commit()


@router.post("/stream-tests", response_model=dict[str, int | str])
def start_stream_tests(
    background_tasks: BackgroundTasks,
    session: DbSession,
    source_playlist_id: int | None = None,
    timeout_seconds: float = 10.0,
    playback_duration_seconds: float = 10.0,
    ffmpeg_binary: str = "ffmpeg",
) -> dict[str, int | str]:
    if timeout_seconds <= 0 or playback_duration_seconds <= 0:
        raise HTTPException(status_code=400, detail="Test durations must be greater than zero")

    test_run = TestRun(
        source_playlist_id=source_playlist_id,
        name="Stream Test",
        profile="quick",
        status=TestRunStatus.PENDING.value,
        total_streams=0,
        completed_streams=0,
        successful_streams=0,
        failed_streams=0,
        configuration_json={
            "test_type": "quick",
            "timeout_seconds": timeout_seconds,
            "playback_duration_seconds": playback_duration_seconds,
            "ffmpeg_binary": ffmpeg_binary,
        },
    )
    session.add(test_run)
    session.commit()
    session.refresh(test_run)

    background_tasks.add_task(
        _run_stream_tests,
        test_run.id,
        source_playlist_id,
        None,
        timeout_seconds,
        playback_duration_seconds,
        ffmpeg_binary,
    )
    return {"test_run_id": test_run.id, "status": test_run.status}


@router.get("/stream-tests/{test_run_id}", response_model=dict[str, object])
def get_stream_test_run(test_run_id: int, session: DbSession) -> dict[str, object]:
    test_run = session.get(TestRun, test_run_id)
    if test_run is None:
        raise HTTPException(status_code=404, detail="Test run not found")
    return {
        "id": test_run.id,
        "status": test_run.status,
        "total_streams": test_run.total_streams,
        "completed_streams": test_run.completed_streams,
        "successful_streams": test_run.successful_streams,
        "failed_streams": test_run.failed_streams,
        "started_at": test_run.started_at,
        "completed_at": test_run.completed_at,
        "configuration": test_run.configuration_json,
    }
