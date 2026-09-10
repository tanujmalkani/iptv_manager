from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import (
    Base,
    Channel,
    ChannelStream,
    PlaylistEntry,
    SourcePlaylist,
    SourcePlaylistVersion,
    Stream,
)
from app.db.session import get_db
from app.main import app


def test_channels_api_can_be_scoped_to_source_playlist() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)

    playlist_a = SourcePlaylist(
        name="Playlist A",
        source_type="text",
        source_location="a",
    )
    playlist_b = SourcePlaylist(
        name="Playlist B",
        source_type="text",
        source_location="b",
    )
    version_a = SourcePlaylistVersion(
        source_playlist=playlist_a,
        version_number=1,
        content_hash="a" * 64,
        entry_count=1,
        status="completed",
    )
    version_b = SourcePlaylistVersion(
        source_playlist=playlist_b,
        version_number=1,
        content_hash="b" * 64,
        entry_count=1,
        status="completed",
    )
    channel_a = Channel(canonical_name="Alpha", normalized_name="alpha")
    channel_b = Channel(canonical_name="Beta", normalized_name="beta")
    stream_a = Stream(
        url="https://example.test/a.m3u8",
        normalized_url="https://example.test/a.m3u8",
        stream_kind="media_playlist",
    )
    stream_b = Stream(
        url="https://example.test/b.m3u8",
        normalized_url="https://example.test/b.m3u8",
        stream_kind="media_playlist",
    )
    session.add_all([
        playlist_a,
        playlist_b,
        version_a,
        version_b,
        channel_a,
        channel_b,
        stream_a,
        stream_b,
    ])
    session.flush()
    session.add_all([
        ChannelStream(channel_id=channel_a.id, stream_id=stream_a.id),
        ChannelStream(channel_id=channel_b.id, stream_id=stream_b.id),
        PlaylistEntry(
            source_playlist_version_id=version_a.id,
            channel_id=channel_a.id,
            stream_id=stream_a.id,
            original_position=0,
            original_name="Alpha",
        ),
        PlaylistEntry(
            source_playlist_version_id=version_b.id,
            channel_id=channel_b.id,
            stream_id=stream_b.id,
            original_position=0,
            original_name="Beta",
        ),
    ])
    session.commit()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        response = client.get(f"/api/channels?source_playlist_id={playlist_a.id}")
        assert response.status_code == 200
        assert [item["channel_name"] for item in response.json()] == ["Alpha"]

        response = client.get(f"/api/channels?source_playlist_id={playlist_b.id}")
        assert response.status_code == 200
        assert [item["channel_name"] for item in response.json()] == ["Beta"]
    finally:
        app.dependency_overrides.clear()
        session.close()
