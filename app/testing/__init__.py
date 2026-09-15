from app.testing.campaign import TestCampaignRunner
from app.testing.deep import DeepTestEngine, DeepTestRunner
from app.testing.quick import QuickTestEngine, QuickTestResult, QuickTestRunner
from app.testing.request_options import install_kodi_request_support
from app.testing.stream import StreamTestEngine, StreamTestRunner

install_kodi_request_support()

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
