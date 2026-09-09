from collections import Counter

from sqlalchemy import func, select

from app.db.models import (
    Channel,
    ChannelStream,
    PlaylistEntry,
    SourcePlaylist,
    SourcePlaylistVersion,
    Stream,
    StreamVariant,
)
from app.db.session import SessionLocal


def main() -> int:
    with SessionLocal() as session:
        counts = {
            "Source playlists": session.scalar(select(func.count()).select_from(SourcePlaylist)) or 0,
            "Playlist versions": session.scalar(
                select(func.count()).select_from(SourcePlaylistVersion)
            )
            or 0,
            "Playlist entries": session.scalar(select(func.count()).select_from(PlaylistEntry)) or 0,
            "Channels": session.scalar(select(func.count()).select_from(Channel)) or 0,
            "Streams": session.scalar(select(func.count()).select_from(Stream)) or 0,
            "Channel streams": session.scalar(select(func.count()).select_from(ChannelStream)) or 0,
            "Stream variants": session.scalar(select(func.count()).select_from(StreamVariant)) or 0,
        }

        print("IPTV Manager Database")
        print("=" * 24)
        for label, count in counts.items():
            print(f"{label}: {count}")

        channels = session.scalars(select(Channel).order_by(Channel.canonical_name)).all()
        if not channels:
            return 0

        stream_counts = Counter(
            channel_id
            for channel_id, in session.execute(select(ChannelStream.channel_id))
        )

        print("\nChannels")
        print("=" * 24)
        for channel in channels:
            print(f"{channel.id}. {channel.canonical_name} ({stream_counts[channel.id]} streams)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
