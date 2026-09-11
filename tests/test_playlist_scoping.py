from datetime import UTC, datetime

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
    StreamTest,
    StreamVariant,
    TestRun,
)
from app.db.session import get_db
from app.main import app
from app.performance.channels import get_channels_performance


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


def test_performance_ranking_is_scoped_to_source_playlist() -> None:
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
    channel = Channel(canonical_name="Shared", normalized_name="shared")
    stream_a = Stream(
        url="https://example.test/fast.m3u8",
        normalized_url="https://example.test/fast.m3u8",
        stream_kind="media_playlist",
    )
    stream_b = Stream(
        url="https://example.test/slow.m3u8",
        normalized_url="https://example.test/slow.m3u8",
        stream_kind="media_playlist",
    )
    run_a = TestRun(name="A", source_playlist_id=playlist_a.id)
    run_b = TestRun(name="B", source_playlist_id=playlist_b.id)
    session.add_all([
        playlist_a,
        playlist_b,
        version_a,
        version_b,
        channel,
        stream_a,
        stream_b,
    ])
    session.flush()
    run_a.source_playlist_id = playlist_a.id
    run_b.source_playlist_id = playlist_b.id
    session.add_all([
        ChannelStream(channel_id=channel.id, stream_id=stream_a.id),
        ChannelStream(channel_id=channel.id, stream_id=stream_b.id),
        PlaylistEntry(
            source_playlist_version_id=version_a.id,
            channel_id=channel.id,
            stream_id=stream_a.id,
            original_position=0,
            original_name="Shared",
        ),
        PlaylistEntry(
            source_playlist_version_id=version_b.id,
            channel_id=channel.id,
            stream_id=stream_b.id,
            original_position=0,
            original_name="Shared",
        ),
        run_a,
        run_b,
    ])
    session.flush()
    now = datetime.now(UTC)
    session.add_all([
        StreamTest(
            test_run_id=run_a.id,
            stream_id=stream_a.id,
            test_type="deep",
            result="success",
            available=True,
            first_frame_ms=100,
            completed_at=now,
            extra_metrics={"stable": True, "playback_duration_ms": 10_000},
        ),
        StreamTest(
            test_run_id=run_b.id,
            stream_id=stream_b.id,
            test_type="deep",
            result="success",
            available=True,
            first_frame_ms=900,
            completed_at=now,
            extra_metrics={"stable": True, "playback_duration_ms": 10_000},
        ),
    ])
    session.commit()

    try:
        performance_a = get_channels_performance(session, source_playlist_id=playlist_a.id)
        performance_b = get_channels_performance(session, source_playlist_id=playlist_b.id)

        assert len(performance_a) == 1
        assert len(performance_b) == 1
        assert [item.stream_id for item in performance_a[0].streams] == [stream_a.id]
        assert [item.stream_id for item in performance_b[0].streams] == [stream_b.id]
        assert performance_a[0].primary_stream_id == stream_a.id
        assert performance_b[0].primary_stream_id == stream_b.id
    finally:
        session.close()


def test_playlist_scope_includes_playable_hls_children_and_detail_matches_summary() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)

    playlist = SourcePlaylist(name="HLS Playlist", source_type="text", source_location="hls")
    version = SourcePlaylistVersion(
        source_playlist=playlist,
        version_number=1,
        content_hash="c" * 64,
        entry_count=1,
        status="completed",
    )
    channel = Channel(canonical_name="HLS Channel", normalized_name="hls channel")
    master = Stream(
        url="https://example.test/master.m3u8",
        normalized_url="https://example.test/master.m3u8",
        stream_kind="master_playlist",
    )
    child_1080 = Stream(
        url="https://example.test/1080.m3u8",
        normalized_url="https://example.test/1080.m3u8",
        stream_kind="media_playlist",
    )
    child_720 = Stream(
        url="https://example.test/720.m3u8",
        normalized_url="https://example.test/720.m3u8",
        stream_kind="media_playlist",
    )
    session.add_all([playlist, version, channel, master, child_1080, child_720])
    session.flush()
    session.add_all([
        ChannelStream(channel_id=channel.id, stream_id=master.id),
        ChannelStream(channel_id=channel.id, stream_id=child_1080.id),
        ChannelStream(channel_id=channel.id, stream_id=child_720.id),
        PlaylistEntry(
            source_playlist_version_id=version.id,
            channel_id=channel.id,
            stream_id=master.id,
            original_position=0,
            original_name="HLS Channel",
        ),
        StreamVariant(parent_stream_id=master.id, variant_stream_id=child_1080.id),
        StreamVariant(parent_stream_id=master.id, variant_stream_id=child_720.id),
    ])
    session.commit()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        summary = client.get(f"/api/channels?source_playlist_id={playlist.id}")
        assert summary.status_code == 200
        item = summary.json()[0]
        assert item["stream_count"] == 2
        assert item["tested_stream_count"] == 0

        detail = client.get(f"/api/channels/{channel.id}?source_playlist_id={playlist.id}")
        assert detail.status_code == 200
        assert len(detail.json()["streams"]) == 2
        assert {stream["stream_id"] for stream in detail.json()["streams"]} == {
            child_1080.id,
            child_720.id,
        }
    finally:
        app.dependency_overrides.clear()
        session.close()
