from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utcnow

if TYPE_CHECKING:
    from .channel import Channel
    from .source import SourcePlaylistVersion
    from .stream import Stream


class PlaylistEntry(Base):
    __tablename__ = "playlist_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_playlist_version_id: Mapped[int] = mapped_column(
        ForeignKey("source_playlist_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    stream_id: Mapped[int] = mapped_column(
        ForeignKey("streams.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    original_position: Mapped[int] = mapped_column(Integer, nullable=False)
    original_name: Mapped[str | None] = mapped_column(Text)
    original_group: Mapped[str | None] = mapped_column(Text)
    original_tvg_id: Mapped[str | None] = mapped_column(Text)
    original_tvg_name: Mapped[str | None] = mapped_column(Text)
    original_logo_url: Mapped[str | None] = mapped_column(Text)
    original_attributes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    original_directives: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    raw_extinf: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    source_playlist_version: Mapped[SourcePlaylistVersion] = relationship(
        back_populates="entries"
    )
    channel: Mapped[Channel] = relationship(back_populates="entries")
    stream: Mapped[Stream] = relationship(back_populates="entries")
