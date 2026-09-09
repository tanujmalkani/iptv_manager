from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import (
    Base,
    Channel,
    ChannelMerge,
    ChannelOption,
    ChannelSelection,
    ChannelStream,
    PlaylistEntry,
    PlaylistProfile,
    PlaylistProfileEntry,
    PlaylistProfileGroup,
    SourcePlaylist,
    SourcePlaylistVersion,
    Stream,
    StreamTest,
    StreamVariant,
    TestRun,
)


def test_model_metadata_creates_and_relationships_round_trip() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        source = SourcePlaylist(name="Test", source_type="text")
        session.add(source)
        session.flush()

        version = SourcePlaylistVersion(
            source_playlist=source,
            version_number=1,
            content_hash="a" * 64,
        )
        channel = Channel(canonical_name="Example HD", normalized_name="example hd")
        stream = Stream(
            url="https://example.test/live.m3u8",
            normalized_url="https://example.test/live.m3u8",
            protocol="https",
            hostname="example.test",
            path="/live.m3u8",
            stream_kind="media_playlist",
        )
        session.add_all([version, channel, stream])
        session.flush()

        entry = PlaylistEntry(
            source_playlist_version=version,
            channel=channel,
            stream=stream,
            original_position=0,
            original_name="Example HD",
            original_attributes={"tvg-id": "example"},
            original_directives=["#KODIPROP:inputstream=inputstream.adaptive"],
        )
        option = ChannelOption(
            channel=channel,
            option_type="name",
            value="Example HD",
            source_playlist=source,
            playlist_entry=entry,
        )
        selection = ChannelSelection(channel=channel, name_option=option)
        channel_stream = ChannelStream(channel=channel, stream=stream)
        session.add_all([entry, option, selection, channel_stream])

        variant_stream = Stream(
            url="https://example.test/720p.m3u8",
            normalized_url="https://example.test/720p.m3u8",
            protocol="https",
            hostname="example.test",
            path="/720p.m3u8",
            stream_kind="media_playlist",
        )
        session.add(variant_stream)
        session.flush()
        variant = StreamVariant(
            parent_stream=stream,
            variant_stream=variant_stream,
            bandwidth=2_000_000,
            resolution_width=1280,
            resolution_height=720,
            frame_rate=25.0,
        )
        session.add(variant)

        test_run = TestRun(source_playlist=source, name="Quick test", profile="quick")
        session.add(test_run)
        session.flush()
        stream_test = StreamTest(
            test_run=test_run,
            stream=stream,
            test_type="quick",
            result="success",
            available=True,
            first_frame_ms=350.5,
        )
        session.add(stream_test)

        profile = PlaylistProfile(source_playlist=source, name="Fast Zap")
        group = PlaylistProfileGroup(profile=profile, name="TV")
        profile_entry = PlaylistProfileEntry(
            profile=profile,
            channel=channel,
            group=group,
            position=0,
            selected_stream=stream,
            selected_name_option=option,
        )
        session.add(profile_entry)

        merge_target = Channel(canonical_name="Example", normalized_name="example")
        session.add(merge_target)
        session.flush()
        merge = ChannelMerge(source_channel=channel, target_channel=merge_target)
        session.add(merge)

        session.commit()

        assert channel.selection is selection
        assert channel.options == [option]
        assert channel.streams == [channel_stream]
        assert stream.variants_as_parent == [variant]
        assert test_run.stream_tests == [stream_test]
        assert profile.entries == [profile_entry]
        assert channel.source_merges == [merge]
        assert merge.target_channel is merge_target
