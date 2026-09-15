from app.testing.campaign import TestCampaignRunner
from app.testing.deep import DeepTestRunner
from app.testing.quick import QuickTestResult, QuickTestRunner
from app.testing.request_options import (
    KodiAwareQuickTestEngine,
    KodiAwareStreamTestEngine,
    install_kodi_request_support,
)
from app.testing.stream import StreamTestRunner

install_kodi_request_support()

DeepTestEngine = KodiAwareStreamTestEngine
QuickTestEngine = KodiAwareQuickTestEngine
StreamTestEngine = KodiAwareStreamTestEngine

__all__ = [
    "DeepTestEngine",
    "DeepTestRunner",
    "QuickTestEngine",
    "QuickTestResult",
    "QuickTestRunner",
    "StreamTestEngine",
    "StreamTestRunner",
    "TestCampaignRunner",
]
