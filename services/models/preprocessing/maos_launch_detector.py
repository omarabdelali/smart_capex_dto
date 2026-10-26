"""Compatibility entry point for strict traffic-confirmed event detection."""
from .network_events import detect_and_save_events


class MAOSLaunchDetector:
    def detect_and_save(self):
        return detect_and_save_events()
