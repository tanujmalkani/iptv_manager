from __future__ import annotations

from datetime import UTC, datetime
from threading import Thread
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import TestRun
from app.db.models.enums import TestRunStatus, TestType
from app.db.session import SessionLocal, get_db
from app.testing.campaign import TestCampaignRunner
from app.testing.deep import DeepTestEngine
from app.testing.quick import QuickTestEngine

router = APIRouter(prefix="/api", tags=["testing"])
DbSession = Annotated[Session, Depends(get_db)]
_DEFAULT_CONCURRENCY = 4
_MAX_CONCURRENCY = 32


def _run_tests(
    test_run_id: int,
    source_playlist_id: int | None,
    test_type: str,
    timeout_seconds: float,
    playback_duration_seconds: float,
    ffmpeg_binary: str,
    concurrency: int,
) -> None:
    with SessionLocal() as session:
        test_run = session.get(TestRun, test_run_id)
        if test_run is None:
            return
        try:
            if test_type == TestType.DEEP.value:
                engine = DeepTestEngine(
                    timeout_seconds=timeout_seconds,
                    playback_duration_seconds=playback_duration_seconds,
                    ffmpeg_binary=ffmpeg_binary,
                )
            else:
                engine = QuickTestEngine(
                    timeout_seconds=timeout_seconds,
                    ffmpeg_binary=ffmpeg_binary,
                )
            runner = TestCampaignRunner(
                engine,
                test_type=test_type,
                concurrency=concurrency,
            )
            runner.run(
                session,
                name=test_run.name,
                source_playlist_id=source_playlist_id,
                existing_test_run=test_run,
            )
        except Exception as exc:
            test_run.status = TestRunStatus.FAILED.value
            test_run.completed_at = datetime.now(UTC)
            test_run.configuration_json = {
                **test_run.configuration_json,
                "error": str(exc),
            }
            session.commit()


def _start_background_test(
    test_run_id: int,
    source_playlist_id: int | None,
    test_type: str,
    timeout_seconds: float,
    playback_duration_seconds: float,
    ffmpeg_binary: str,
    concurrency: int,
) -> None:
    Thread(
        target=_run_tests,
        args=(
            test_run_id,
            source_playlist_id,
            test_type,
            timeout_seconds,
            playback_duration_seconds,
            ffmpeg_binary,
            concurrency,
        ),
        daemon=True,
        name=f"{test_type}-test-{test_run_id}",
    ).start()


@router.post("/stream-tests", response_model=dict[str, int | str])
def start_stream_tests(
    session: DbSession,
    source_playlist_id: int | None = None,
    test_type: str = TestType.QUICK.value,
    timeout_seconds: float = 10.0,
    playback_duration_seconds: float = 10.0,
    ffmpeg_binary: str = "ffmpeg",
    concurrency: int = _DEFAULT_CONCURRENCY,
) -> dict[str, int | str]:
    if test_type not in {TestType.QUICK.value, TestType.DEEP.value}:
        raise HTTPException(status_code=400, detail="test_type must be quick or deep")
    if timeout_seconds <= 0:
        raise HTTPException(status_code=400, detail="timeout_seconds must be greater than zero")
    if test_type == TestType.DEEP.value and playback_duration_seconds <= 0:
        raise HTTPException(
            status_code=400,
            detail="playback_duration_seconds must be greater than zero",
        )
    if not 1 <= concurrency <= _MAX_CONCURRENCY:
        raise HTTPException(
            status_code=400,
            detail=f"concurrency must be between 1 and {_MAX_CONCURRENCY}",
        )

    if test_type == TestType.DEEP.value:
        engine = DeepTestEngine(
            timeout_seconds=timeout_seconds,
            playback_duration_seconds=playback_duration_seconds,
            ffmpeg_binary=ffmpeg_binary,
        )
    else:
        engine = QuickTestEngine(timeout_seconds=timeout_seconds, ffmpeg_binary=ffmpeg_binary)

    streams = TestCampaignRunner(
        engine,
        test_type=test_type,
        concurrency=concurrency,
    )._test_streams
    # Use the existing runner selection logic without executing the campaign in the request.
    from app.testing.quick import QuickTestRunner

    selected_streams = QuickTestRunner(engine)._select_streams(session, source_playlist_id, None)
    del streams
    test_run = TestRun(
        source_playlist_id=source_playlist_id,
        name=f"{test_type.title()} Test",
        profile=test_type,
        status=TestRunStatus.PENDING.value,
        total_streams=len(selected_streams),
        completed_streams=0,
        successful_streams=0,
        failed_streams=0,
        configuration_json={
            "test_type": test_type,
            "timeout_seconds": timeout_seconds,
            "ffmpeg_binary": ffmpeg_binary,
            "concurrency": concurrency,
            **(
                {"playback_duration_seconds": playback_duration_seconds}
                if test_type == TestType.DEEP.value
                else {}
            ),
        },
    )
    session.add(test_run)
    session.commit()
    session.refresh(test_run)

    _start_background_test(
        test_run.id,
        source_playlist_id,
        test_type,
        timeout_seconds,
        playback_duration_seconds,
        ffmpeg_binary,
        concurrency,
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
