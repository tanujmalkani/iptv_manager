from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utcnow


class Stream(Base):
    __tablename__ = "streams"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    protocol: Mapped[str | None] = mapped_column(String(32))
    hostname: Mapped[str | None] = mapped_column(String(512), index=True)
    port: Mapped[int | None] = mapped_column(Integer)
    path: Mapped[str | None] = mapped_column(Text)
    stream_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    channels: Mapped[list["ChannelStream"]] = relationship(back_populates="stream", cascade="all, delete-orphan")
    variants_as_parent: Mapped[list["StreamVariant"]] = relationship(foreign_keys="StreamVariant.parent_stream_id", back_populates="parent_stream", cascade="all, delete-orphan")
    variants_as_child: Mapped[list["StreamVariant"]] = relationship(foreign_keys="StreamVariant.variant_stream_id", back_populates="variant_stream", cascade="all, delete-orphan")
    entries: Mapped[list["PlaylistEntry"]] = relationship(back_populates="stream")
    tests: Mapped[list["StreamTest"]] = relationship(back_populates="stream", cascade="all, delete-orphan")


class ChannelStream(Base):
    __tablename__ = "channel_streams"

    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), primary_key=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id", ondelete="CASCADE"), primary_key=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    channel: Mapped["Channel"] = relationship(back_populates="streams")
    stream: Mapped["Stream"] = relationship(back_populates="channels")


class StreamVariant(Base):
    __tablename__ = "stream_variants"
    __table_args__ = (UniqueConstraint("parent_stream_id", "variant_stream_id", name="uq_stream_variant"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id", ondelete="CASCADE"), nullable=False, index=True)
    variant_stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id", ondelete="CASCADE"), nullable=False, index=True)
    bandwidth: Mapped[int | None] = mapped_column(Integer)
    average_bandwidth: Mapped[int | None] = mapped_column(Integer)
    resolution_width: Mapped[int | None] = mapped_column(Integer)
    resolution_height: Mapped[int | None] = mapped_column(Integer)
    frame_rate: Mapped[float | None] = mapped_column(Float)
    codecs: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    parent_stream: Mapped["Stream"] = relationship(foreign_keys=[parent_stream_id], back_populates="variants_as_parent")
    variant_stream: Mapped["Stream"] = relationship(foreign_keys=[variant_stream_id], back_populates="variants_as_child")
