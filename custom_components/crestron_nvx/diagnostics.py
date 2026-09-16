"""Diagnostics support for Crestron DM NVX."""

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import CrestronNvxConfigEntry

_TO_REDACT = {CONF_HOST, CONF_PASSWORD, CONF_USERNAME, "unique_id", "title"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: CrestronNvxConfigEntry
) -> dict[str, Any]:
    """Return diagnostics with network and identity data redacted."""

    snapshot = asdict(entry.runtime_data.data)
    # Model-specific data is intentionally not exported until each field has
    # been classified. A future firmware may add secrets to this object.
    snapshot.pop("raw_device_specific", None)
    device = snapshot["device"]
    for key in ("device_id", "name", "serial_number", "mac_address"):
        device[key] = REDACTED
    for port in snapshot["av_ports"]:
        port["port_id"] = REDACTED
        port["name"] = REDACTED
    for collection in ("receive_streams", "transmit_streams"):
        for stream in snapshot[collection]:
            stream["stream_id"] = REDACTED
    return {
        "entry": async_redact_data(entry.as_dict(), _TO_REDACT),
        "snapshot": snapshot,
        "last_update_success": entry.runtime_data.last_update_success,
        "last_exception_type": (
            type(entry.runtime_data.last_exception).__name__
            if entry.runtime_data.last_exception
            else None
        ),
    }
