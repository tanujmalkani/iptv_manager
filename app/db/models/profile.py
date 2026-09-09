from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utcnow

if TYPE_CHECKING:
    from .channel import Channel, ChannelOption
    from .source import SourcePlaylist
    from .stream import Stream


class PlaylistProfile(Base):
    __tablename__ = "playlist_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_playlist_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_playlists.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    selection_mode: Mapped[str] = mapped_column(String(32), default="all", nullable=False)
    stream_mode: Mapped[str] = mapped_column(
        String(32), default="fastest_startup", nullable=False
    )
    minimum_score: Mapped[float | None] = mapped_column()
    minimum_width: Mapped[int | None] = mapped_column(Integer)
    maximum_startup_ms: Mapped[float | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    source_playlist: Mapped[SourcePlaylist | None] = relationship()
    groups: Mapped[list[PlaylistProfileGroup]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    entries: Mapped[list[PlaylistProfileEntry]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class PlaylistProfileGroup(Base):
    __tablename__ = "playlist_profile_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("playlist_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    profile: Mapped[PlaylistProfile] = relationship(back_populates="groups")
    entries: Mapped[list[PlaylistProfileEntry]] = relationship(back_populates="group")


class PlaylistProfileEntry(Base):
    __tablename__ = "playlist_profile_entries"
    __table_args__ = (
        UniqueConstraint("profile_id", "position", name="uq_profile_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("playlist_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("playlist_profile_groups.id", ondelete="SET NULL")
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    selected_stream_id: Mapped[int | None] = mapped_column(
        ForeignKey("streams.id", ondelete="SET NULL")
    )
    selected_name_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_options.id", ondelete="SET NULL")
    )
    selected_logo_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_options.id", ondelete="SET NULL")
    )
    selected_epg_id_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_options.id", ondelete="SET NULL")
    )
    selected_group_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_options.id", ondelete="SET NULL")
    )

    profile: Mapped[PlaylistProfile] = relationship(back_populates="entries")
    channel: Mapped[Channel] = relationship()
    group: Mapped[PlaylistProfileGroup | None] = relationship(back_populates="entries")
    selected_stream: Mapped[Stream | None] = relationship()
    selected_name_option: Mapped[ChannelOption | None] = relationship(
        foreign_keys=[selected_name_option_id]
    )
    selected_logo_option: Mapped[ChannelOption | None] = relationship(
        foreign_keys=[selected_logo_option_id]
    )
    selected_epg_id_option: Mapped[ChannelOption | None] = relationship(
        foreign_keys=[selected_epg_id_option_id]
    )
    selected_group_option: Mapped[ChannelOption | None] = relationship(
        foreign_keys=[selected_group_option_id]
    )
