"""Constants for the Crestron DM NVX integration."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "crestron_nvx"
SIGNAL_ROUTING_UPDATED = f"{DOMAIN}_routing_updated"
MANUFACTURER = "Crestron"

CONF_VERIFY_SSL = "verify_ssl"

DEFAULT_VERIFY_SSL = False
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)

PLATFORMS: tuple[Platform, ...] = (
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.IMAGE,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.BUTTON,
)
