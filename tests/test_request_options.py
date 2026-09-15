from app.testing.request_options import (
    KodiAwareQuickTestEngine,
    KodiAwareStreamTestEngine,
    ffmpeg_headers_arg,
    http_headers_from_options,
    split_stream_reference,
)


def test_split_stream_reference_supports_encoded_kodi_pipe() -> None:
    url, options = split_stream_reference(
        "https://dwby15d04agvq.cloudfront.net/index_5.m3u8"
        "%7CReferer=https://www.zeebiz.com/"
    )

    assert url == "https://dwby15d04agvq.cloudfront.net/index_5.m3u8"
    assert options == {"Referer": "https://www.zeebiz.com/"}


def test_request_options_support_multiple_http_headers() -> None:
    url, options = split_stream_reference(
        "https://example.test/live.m3u8"
        "|Referer=https://example.test/&User-Agent=Kodi"
    )

    assert url == "https://example.test/live.m3u8"
    assert options["Referer"] == "https://example.test/"
    assert options["User-Agent"] == "Kodi"
    assert http_headers_from_options(options) == {
        "Referer": "https://example.test/",
        "User-Agent": "Kodi",
    }


def test_ffmpeg_headers_argument_is_crlf_delimited() -> None:
    assert ffmpeg_headers_arg(
        {"Referer": "https://example.test/", "User-Agent": "Kodi"}
    ) == "Referer: https://example.test/\r\nUser-Agent: Kodi\r\n"


def test_application_testing_classes_are_kodi_aware() -> None:
    from app.testing.quick import QuickTestEngine
    from app.testing.stream import StreamTestEngine

    assert QuickTestEngine is KodiAwareQuickTestEngine
    assert StreamTestEngine is KodiAwareStreamTestEngine
