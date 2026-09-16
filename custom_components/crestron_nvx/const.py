"""Constants for the Crestron DM NVX integration."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "crestron_nvx"
MANUFACTURER = "Crestron"

CONF_VERIFY_SSL = "verify_ssl"

DEFAULT_VERIFY_SSL = False
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)

PLATFORMS: tuple[Platform, ...] = (
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.IMAGE,
)

SUPPORTED_MODELS = frozenset({"DM-NVX-350", "DM-NVX-360", "DM-NVX-E30"})
