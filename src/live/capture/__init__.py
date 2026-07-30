"""Capture adapter contracts and implementations."""

from .base import CaptureAdapter
from .factory import CaptureCapabilities, CaptureUnavailable, capture_capabilities, create_capture_adapter

__all__ = ["CaptureAdapter", "CaptureCapabilities", "CaptureUnavailable", "capture_capabilities", "create_capture_adapter"]
