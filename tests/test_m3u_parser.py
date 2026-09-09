from app.m3u.parser import parse_m3u


def test_parse_extended_m3u_attributes() -> None:
    text = (
        '#EXTM3U\n'
        '#EXTINF:-1 tvg-id="bbc1.uk" tvg-name="BBC One" '
        'tvg-logo="https://logo/bbc1.png" group-title="UK",BBC One\n'
        'https://stream.example/bbc1.m3u8\n'
    )
    playlist = parse_m3u(text)

    assert len(playlist.entries) == 1
    entry = playlist.entries[0]
    assert entry.name == "BBC One"
    assert entry.url == "https://stream.example/bbc1.m3u8"
    assert entry.attributes["tvg-id"] == "bbc1.uk"
    assert entry.attributes["tvg-name"] == "BBC One"
    assert entry.attributes["tvg-logo"] == "https://logo/bbc1.png"
    assert entry.attributes["group-title"] == "UK"


def test_parse_quoted_attribute_with_spaces() -> None:
    playlist = parse_m3u(
        '#EXTM3U\n#EXTINF:-1 tvg-name="BBC UK One" custom="hello world",Display Name\n'
        "https://example.test/live"
    )

    entry = playlist.entries[0]
    assert entry.name == "Display Name"
    assert entry.attributes["tvg-name"] == "BBC UK One"
    assert entry.attributes["custom"] == "hello world"


def test_preserve_directives_and_tolerate_bare_urls() -> None:
    playlist = parse_m3u(
        "#EXTM3U\n#EXTVLCOPT:http-referrer=https://example.test/\n"
        "https://example.test/live\n"
        "#EXTINF:-1,Second\nhttps://example.test/second"
    )

    assert playlist.entries[0].name == ""
    assert playlist.entries[0].url == "https://example.test/live"
    assert playlist.entries[0].directives == [
        "#EXTVLCOPT:http-referrer=https://example.test/"
    ]
    assert playlist.entries[1].name == "Second"


def test_tolerate_missing_header_and_bom() -> None:
    playlist = parse_m3u(
        "\ufeff#EXTINF:-1 tvg-name=News, News Channel\n"
        "https://example.test/news.m3u8\n"
    )

    assert playlist.header == "#EXTM3U"
    assert len(playlist.entries) == 1
    assert playlist.entries[0].name == "News Channel"
    assert playlist.entries[0].url == "https://example.test/news.m3u8"


def test_tolerate_malformed_duration_and_preserve_directive() -> None:
    playlist = parse_m3u(
        "#EXTM3U\n#KODIPROP:inputstream=inputstream.adaptive\n"
        "#EXTINF:not-a-number tvg-id=abc,Channel\n"
        "https://example.test/live?token=a%20b\n"
    )

    entry = playlist.entries[0]
    assert entry.duration is None
    assert entry.attributes["tvg-id"] == "abc"
    assert entry.directives == ["#KODIPROP:inputstream=inputstream.adaptive"]
    assert entry.url == "https://example.test/live?token=a%20b"


def test_empty_playlist_rejected() -> None:
    try:
        parse_m3u("\n   \n")
    except ValueError as exc:
        assert "empty" in str(exc).lower()
    else:
        raise AssertionError("Expected ValueError")
