from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import (
    Base,
    Channel,
    ChannelStream,
    PlaylistEntry,
    PlaylistProfile,
    PlaylistProfileEntry,
    SourcePlaylist,
    SourcePlaylistVersion,
    Stream,
    StreamTest,
    TestRun,
)
from app.exporter import export_m3u, preview_m3u
from app.optimization import OptimizationProfile


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def make_playlist(
    session: Session,
) -> tuple[SourcePlaylist, SourcePlaylistVersion, Channel, Stream]:
    playlist = SourcePlaylist(name="Test", source_type="text", source_location="test")
    version = SourcePlaylistVersion(
        source_playlist=playlist,
        version_number=1,
        content_hash="a" * 64,
        entry_count=1,
        status="completed",
    )
    channel = Channel(canonical_name="News", normalized_name="news")
    source_stream = Stream(
        url="https://example.test/source.m3u8",
        normalized_url="https://example.test/source.m3u8",
        stream_kind="media_playlist",
    )
    session.add_all([playlist, version, channel, source_stream])
    session.flush()
    session.add(ChannelStream(channel_id=channel.id, stream_id=source_stream.id))
    session.add(
        PlaylistEntry(
            source_playlist_version_id=version.id,
            channel_id=channel.id,
            stream_id=source_stream.id,
            original_position=0,
            original_name="News",
            raw_extinf="#EXTINF:-1,News",
        )
    )
    session.commit()
    return playlist, version, channel, source_stream


def make_profile(
    session: Session,
    playlist: SourcePlaylist,
    channel: Channel,
    selected_stream_id: int,
) -> PlaylistProfile:
    profile = PlaylistProfile(
        source_playlist_id=playlist.id,
        name="Living Room",
        selection_mode="custom",
        stream_mode="source",
    )
    session.add(profile)
    session.flush()
    session.add(
        PlaylistProfileEntry(
            profile_id=profile.id,
            channel_id=channel.id,
            position=0,
            enabled=True,
            selected_stream_id=selected_stream_id,
        )
    )
    session.commit()
    return profile


def test_preview_and_export_fall_back_for_stale_manual_selection() -> None:
    session = make_session()
    try:
        playlist, _, channel, source_stream = make_playlist(session)
        stale_stream = Stream(
            url="https://example.test/stale.m3u8",
            normalized_url="https://example.test/stale.m3u8",
            stream_kind="media_playlist",
        )
        session.add(stale_stream)
        session.commit()
        profile = make_profile(session, playlist, channel, stale_stream.id)

        preview = preview_m3u(
            session,
            playlist.id,
            playlist_profile_id=profile.id,
        )
        result = export_m3u(
            session,
            playlist.id,
            playlist_profile_id=profile.id,
        )

        assert preview is not None
        assert result is not None
        assert preview.invalid_selection_count == 1
        assert preview.fallback_count == 1
        assert preview.optimized_count == 0
        assert result.fallback_count == 1
        assert source_stream.url in result.content
        assert stale_stream.url not in result.content
    finally:
        session.close()


def test_preview_and_export_reject_master_playlist_selection() -> None:
    session = make_session()
    try:
        playlist, _, channel, source_stream = make_playlist(session)
        master_stream = Stream(
            url="https://example.test/master.m3u8",
            normalized_url="https://example.test/master.m3u8",
            stream_kind="master_playlist",
        )
        session.add(master_stream)
        session.commit()
        profile = make_profile(session, playlist, channel, master_stream.id)

        preview = preview_m3u(
            session,
            playlist.id,
            playlist_profile_id=profile.id,
        )
        result = export_m3u(
            session,
            playlist.id,
            playlist_profile_id=profile.id,
        )

        assert preview is not None
        assert result is not None
        assert preview.invalid_selection_count == 1
        assert preview.fallback_count == 1
        assert any("master playlist" in warning for warning in preview.warnings)
        assert result.fallback_count == 1
        assert source_stream.url in result.content
        assert master_stream.url not in result.content
    finally:
        session.close()


def test_preview_with_optimization_handles_existing_test_history() -> None:
    session = make_session()
    try:
        playlist, _, _, source_stream = make_playlist(session)
        test_run = TestRun(
            source_playlist_id=playlist.id,
            name="Export preview test",
            profile="quick",
            status="completed",
        )
        session.add(test_run)
        session.flush()
        now = datetime.now(UTC).replace(tzinfo=None)
        session.add(
            StreamTest(
                test_run_id=test_run.id,
                stream_id=source_stream.id,
                attempt_number=1,
                test_type="quick",
                result="success",
                started_at=now,
                completed_at=now,
                available=True,
                first_frame_ms=100.0,
            )
        )
        session.commit()

        preview = preview_m3u(
            session,
            playlist.id,
            optimization_profile=OptimizationProfile.FAST,
        )
        result = export_m3u(
            session,
            playlist.id,
            optimization_profile=OptimizationProfile.FAST,
        )

        assert preview is not None
        assert result is not None
        assert preview.optimized_count == 0
        assert preview.automatic_selection_count == 1
        assert preview.untested_count == 0
        assert preview.no_successful_test_count == 0
        assert result.content.count(source_stream.url) == 1
    finally:
        session.close()
