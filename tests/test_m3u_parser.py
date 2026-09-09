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


def test_reject_invalid_header() -> None:
    try:
        parse_m3u("not an m3u")
    except ValueError as exc:
        assert "EXTM3U" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
