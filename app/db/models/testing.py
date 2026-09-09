from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utcnow


class TestRun(Base):
    __tablename__ = "test_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_playlist_id: Mapped[int | None] = mapped_column(ForeignKey("source_playlists.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    profile: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    total_streams: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_streams: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_streams: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_streams: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    configuration_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    source_playlist: Mapped["SourcePlaylist | None"] = relationship()
    stream_tests: Mapped[list["StreamTest"]] = relationship(back_populates="test_run", cascade="all, delete-orphan")


class StreamTest(Base):
    __tablename__ = "stream_tests"
    __table_args__ = (UniqueConstraint("test_run_id", "stream_id", "attempt_number", name="uq_stream_test_attempt"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    test_run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    test_type: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    available: Mapped[bool | None] = mapped_column()
    error_stage: Mapped[str | None] = mapped_column(String(64))
    error_type: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    dns_ms: Mapped[float | None] = mapped_column(Float)
    connect_ms: Mapped[float | None] = mapped_column(Float)
    tls_ms: Mapped[float | None] = mapped_column(Float)
    http_response_ms: Mapped[float | None] = mapped_column(Float)
    manifest_ms: Mapped[float | None] = mapped_column(Float)
    first_data_ms: Mapped[float | None] = mapped_column(Float)
    first_frame_ms: Mapped[float | None] = mapped_column(Float)
    bytes_received: Mapped[int | None] = mapped_column(Integer)
    test_duration_ms: Mapped[float | None] = mapped_column(Float)
    throughput_bps: Mapped[float | None] = mapped_column(Float)
    extra_metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    test_run: Mapped["TestRun"] = relationship(back_populates="stream_tests")
    stream: Mapped["Stream"] = relationship(back_populates="tests")
