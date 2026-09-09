from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utcnow
from .enums import VersionStatus


class SourcePlaylist(Base):
    __tablename__ = "source_playlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_location: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    entry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    versions: Mapped[list["SourcePlaylistVersion"]] = relationship(
        back_populates="source_playlist", cascade="all, delete-orphan"
    )


class SourcePlaylistVersion(Base):
    __tablename__ = "source_playlist_versions"
    __table_args__ = (
        UniqueConstraint("source_playlist_id", "version_number", name="uq_playlist_version_number"),
        UniqueConstraint("source_playlist_id", "content_hash", name="uq_playlist_content_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_playlist_id: Mapped[int] = mapped_column(ForeignKey("source_playlists.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    raw_content_path: Mapped[str | None] = mapped_column(Text)
    original_header: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default=VersionStatus.IMPORTING.value, nullable=False)

    source_playlist: Mapped["SourcePlaylist"] = relationship(back_populates="versions")
    entries: Mapped[list["PlaylistEntry"]] = relationship(
        back_populates="source_playlist_version", cascade="all, delete-orphan"
    )
