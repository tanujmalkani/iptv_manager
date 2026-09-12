from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock, Thread
from uuid import uuid4

from app.db.session import SessionLocal
from app.importer.service import ImportResult, PlaylistImporter


@dataclass(slots=True)
class ImportJob:
    id: str
    status: str = "pending"
    stage: str = "queued"
    current: int = 0
    total: int = 0
    message: str = "Waiting to start"
    result: ImportResult | None = None
    error_type: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    lock: Lock = field(default_factory=Lock, repr=False)


_jobs: dict[str, ImportJob] = {}
_jobs_lock = Lock()


def create_import_job() -> ImportJob:
    job = ImportJob(id=str(uuid4()))
    with _jobs_lock:
        _jobs[job.id] = job
    return job


def get_import_job(job_id: str) -> ImportJob | None:
    with _jobs_lock:
        return _jobs.get(job_id)


def _set_progress(job: ImportJob, stage: str, current: int, total: int, message: str) -> None:
    with job.lock:
        job.status = "running"
        job.stage = stage
        job.current = current
        job.total = total
        job.message = message


def _result_payload(result: ImportResult) -> dict[str, object]:
    return {
        "source_playlist_id": result.source_playlist_id,
        "version_id": result.version_id,
        "version_number": result.version_number,
        "entries": result.entries,
        "channels": result.channels,
        "unique_streams": result.unique_streams,
        "duplicate_urls": result.duplicate_urls,
        "new_channels": result.new_channels,
        "discovered_streams": result.discovered_streams,
        "warnings": result.warnings,
        "identical_version": result.identical_version,
    }


def serialize_import_job(job: ImportJob) -> dict[str, object]:
    with job.lock:
        payload: dict[str, object] = {
            "id": job.id,
            "status": job.status,
            "stage": job.stage,
            "current": job.current,
            "total": job.total,
            "message": job.message,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "error_type": job.error_type,
            "error": job.error,
        }
        payload["result"] = _result_payload(job.result) if job.result is not None else None
        return payload


def _run_import(
    job: ImportJob,
    name: str,
    text: str,
    source_location: str | None,
) -> None:
    with job.lock:
        job.started_at = datetime.now(UTC)
        job.status = "running"
        job.stage = "starting"
        job.message = "Starting playlist import"

    def progress(stage: str, current: int, total: int, message: str) -> None:
        _set_progress(job, stage, current, total, message)

    try:
        with SessionLocal() as session:
            result = PlaylistImporter().import_text(
                session,
                name=name,
                text=text,
                source_location=source_location,
                progress=progress,
            )
        with job.lock:
            job.status = "completed"
            job.stage = "complete"
            job.current = result.entries
            job.total = result.entries
            job.message = (
                "Existing version detected"
                if result.identical_version
                else (
                    f"Import complete · {result.channels} channels · "
                    f"{result.unique_streams} source streams"
                )
            )
            job.result = result
            job.completed_at = datetime.now(UTC)
    except Exception as exc:
        with job.lock:
            job.status = "failed"
            job.stage = "failed"
            job.message = "Import failed"
            job.error_type = type(exc).__name__
            job.error = str(exc) or repr(exc)
            job.completed_at = datetime.now(UTC)


def start_import_job(
    name: str,
    text: str,
    source_location: str | None,
) -> ImportJob:
    job = create_import_job()
    Thread(
        target=_run_import,
        args=(job, name, text, source_location),
        daemon=True,
        name=f"playlist-import-{job.id[:8]}",
    ).start()
    return job
