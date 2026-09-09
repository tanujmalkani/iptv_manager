from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utcnow

if TYPE_CHECKING:
    from .playlist import PlaylistEntry
    from .source import SourcePlaylist
    from .stream import ChannelStream


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
    is_merged: Mapped[bool] = mapped_column(default=False, nullable=False)

    entries: Mapped[list[PlaylistEntry]] = relationship(back_populates="channel")
    options: Mapped[list[ChannelOption]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )
    streams: Mapped[list[ChannelStream]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )
    selection: Mapped[ChannelSelection | None] = relationship(
        back_populates="channel", uselist=False, cascade="all, delete-orphan"
    )
    source_merges: Mapped[list[ChannelMerge]] = relationship(
        foreign_keys="ChannelMerge.source_channel_id",
        back_populates="source_channel",
        cascade="all, delete-orphan",
    )
    target_merges: Mapped[list[ChannelMerge]] = relationship(
        foreign_keys="ChannelMerge.target_channel_id",
        back_populates="target_channel",
        cascade="all, delete-orphan",
    )


class ChannelOption(Base):
    __tablename__ = "channel_options"
    __table_args__ = (
        UniqueConstraint("channel_id", "option_type", "value", name="uq_channel_option"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    option_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    source_playlist_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_playlists.id", ondelete="SET NULL")
    )
    playlist_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("playlist_entries.id", ondelete="SET NULL")
    )
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    channel: Mapped[Channel] = relationship(back_populates="options")
    source_playlist: Mapped[SourcePlaylist | None] = relationship()
    playlist_entry: Mapped[PlaylistEntry | None] = relationship()


class ChannelSelection(Base):
    __tablename__ = "channel_selections"

    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), primary_key=True
    )
    name_option_id: Mapped[int | None] = mapped_column(ForeignKey("channel_options.id"))
    logo_option_id: Mapped[int | None] = mapped_column(ForeignKey("channel_options.id"))
    epg_id_option_id: Mapped[int | None] = mapped_column(ForeignKey("channel_options.id"))
    epg_name_option_id: Mapped[int | None] = mapped_column(ForeignKey("channel_options.id"))
    group_option_id: Mapped[int | None] = mapped_column(ForeignKey("channel_options.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    channel: Mapped[Channel] = relationship(back_populates="selection")
    name_option: Mapped[ChannelOption | None] = relationship(
        foreign_keys=[name_option_id]
    )
    logo_option: Mapped[ChannelOption | None] = relationship(
        foreign_keys=[logo_option_id]
    )
    epg_id_option: Mapped[ChannelOption | None] = relationship(
        foreign_keys=[epg_id_option_id]
    )
    epg_name_option: Mapped[ChannelOption | None] = relationship(
        foreign_keys=[epg_name_option_id]
    )
    group_option: Mapped[ChannelOption | None] = relationship(
        foreign_keys=[group_option_id]
    )


class ChannelMerge(Base):
    __tablename__ = "channel_merges"
    __table_args__ = (
        UniqueConstraint("source_channel_id", "target_channel_id", name="uq_channel_merge"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    target_channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    source_channel: Mapped[Channel] = relationship(
        foreign_keys=[source_channel_id], back_populates="source_merges"
    )
    target_channel: Mapped[Channel] = relationship(
        foreign_keys=[target_channel_id], back_populates="target_merges"
    )
