import pytest

from src.live.types import CaptureSource


def test_factory_selects_only_requested_platform_adapter():
    from src.live.capture.factory import create_capture_adapter

    assert create_capture_adapter("win32", CaptureSource.MIC).__class__.__name__ == "WindowsMicrophoneAdapter"
    assert create_capture_adapter("darwin", CaptureSource.SYSTEM).__class__.__name__ == "MacSystemAudioAdapter"
    assert create_capture_adapter("linux", CaptureSource.SYSTEM).__class__.__name__ == "LinuxSystemAudioAdapter"


def test_factory_rejects_unknown_platform_without_noop_fallback():
    from src.live.capture.factory import CaptureUnavailable, create_capture_adapter

    with pytest.raises(CaptureUnavailable, match="Unsupported platform"):
        create_capture_adapter("freebsd", CaptureSource.MIC)


def test_capabilities_identify_required_optional_runtime():
    from src.live.capture.factory import capture_capabilities

    capabilities = capture_capabilities("win32")

    assert capabilities.platform == "win32"
    assert CaptureSource.MIC in capabilities.sources
    assert "PyAudioWPatch" in capabilities.install_hint
