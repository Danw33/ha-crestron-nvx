"""Conservatively retain entity IDs when replacing unstable A/V port UUIDs."""

import logging
import re
from collections import Counter

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from crestron_nvx import NvxSnapshot

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
_UUID = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
_METRICS = {
    "input": (
        ("binary_sensor", "sync", "input sync"),
        ("sensor", "resolution", "input resolution"),
    ),
    "output": (
        ("binary_sensor", "connected", "output connected"),
        ("binary_sensor", "transmitting", "output transmitting"),
        ("sensor", "resolution", "output resolution"),
    ),
}


@callback
def async_migrate_port_entities(
    hass: HomeAssistant, entry_id: str, snapshot: NvxSnapshot
) -> None:
    """Migrate a known legacy key only when the original port label is unique.

    English is currently the integration's only translation. Match the stored
    original label, never a user's name or a generated entity-ID suffix. Keep
    surplus entries: they may be referenced by automations or dashboards.
    This is idempotent and runs after the first snapshot, before platform setup.
    """
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry_id)
    if not entries:
        return
    labels = Counter((port.direction, port.name) for port in snapshot.av_ports)
    for port in snapshot.av_ports:
        if labels[(port.direction, port.name)] != 1:
            continue
        for domain, metric, suffix in _METRICS[port.direction]:
            unique_id = (
                f"{snapshot.device.device_id}_{port.direction}_{port.port_id}_{metric}"
            )
            if registry.async_get_entity_id(domain, DOMAIN, unique_id):
                continue
            prefix = re.escape(f"{snapshot.device.device_id}_{port.direction}_")
            legacy_key = re.compile(
                rf"{prefix}(?:{_UUID}|{port.direction}_\d+_\d+)_{metric}"
            )
            candidates = [
                entity
                for entity in entries
                if entity.platform == DOMAIN
                and entity.domain == domain
                and legacy_key.fullmatch(entity.unique_id)
                and (entity.original_name_unprefixed or entity.original_name)
                == f"{port.name} {suffix}"
            ]
            if not candidates:
                continue
            oldest = min(
                candidates, key=lambda entity: (entity.created_at, entity.entity_id)
            )
            registry.async_update_entity(oldest.entity_id, new_unique_id=unique_id)
            if len(candidates) > 1:
                _LOGGER.warning(
                    "Migrated %s to stable port identity; retained %s other duplicate "
                    "entries for manual review of automation references",
                    oldest.entity_id,
                    len(candidates) - 1,
                )
