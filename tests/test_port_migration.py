"""Preserve registry customisations without deleting historical duplicates."""

from dataclasses import replace

from crestron_nvx import NvxAvPort
from homeassistant.helpers import entity_registry as er

from custom_components.crestron_nvx.const import DOMAIN
from custom_components.crestron_nvx.migration import async_migrate_port_entities

from .conftest import DEVICE_ID, SNAPSHOT

PORT = NvxAvPort(port_id="input_slot0_hdmi_0", name="INPUT 1", direction="input")
NEW_ID = f"{DEVICE_ID}_input_{PORT.port_id}_sync"


def legacy(registry, entry, number=1, **kwargs):
    return registry.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        f"{DEVICE_ID}_input_00000000-0000-4000-8000-{number:012d}_sync",
        config_entry=entry,
        original_name="INPUT 1 input sync",
        **kwargs,
    )


async def test_migration_preserves_oldest_entity_and_leaves_duplicates(
    hass, mock_config_entry
):
    registry = er.async_get(hass)
    first = legacy(registry, mock_config_entry)
    registry.async_update_entity(
        first.entity_id, name="My HDMI", disabled_by=er.RegistryEntryDisabler.USER
    )
    second = legacy(registry, mock_config_entry, 2)
    snapshot = replace(SNAPSHOT, av_ports=(PORT,))
    async_migrate_port_entities(hass, mock_config_entry.entry_id, snapshot)
    migrated = registry.async_get(first.entity_id)
    assert migrated.unique_id == NEW_ID
    assert migrated.name == "My HDMI"
    assert migrated.disabled_by == er.RegistryEntryDisabler.USER
    assert registry.async_get(second.entity_id).unique_id == second.unique_id
    async_migrate_port_entities(hass, mock_config_entry.entry_id, snapshot)
    assert (
        len(er.async_entries_for_config_entry(registry, mock_config_entry.entry_id))
        == 2
    )


async def test_ambiguous_port_names_are_not_guessed(hass, mock_config_entry):
    registry = er.async_get(hass)
    old = legacy(registry, mock_config_entry)
    snapshot = replace(
        SNAPSHOT, av_ports=(PORT, replace(PORT, port_id="input_slot1_hdmi_0"))
    )
    async_migrate_port_entities(hass, mock_config_entry.entry_id, snapshot)
    assert registry.async_get(old.entity_id).unique_id == old.unique_id


async def test_unrecognised_keys_and_unrelated_entities_are_untouched(
    hass, mock_config_entry
):
    registry = er.async_get(hass)
    old = legacy(registry, mock_config_entry)
    registry.async_update_entity(
        old.entity_id, original_name="Different port input sync"
    )
    unrelated = registry.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        "unrecognised-key",
        config_entry=mock_config_entry,
        original_name="INPUT 1 input sync",
    )
    async_migrate_port_entities(
        hass, mock_config_entry.entry_id, replace(SNAPSHOT, av_ports=(PORT,))
    )
    assert registry.async_get(old.entity_id).unique_id == old.unique_id
    assert registry.async_get(unrelated.entity_id).unique_id == "unrecognised-key"


async def test_single_legacy_positional_entry_migrates(hass, mock_config_entry):
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{DEVICE_ID}_output_output_0_0_resolution",
        config_entry=mock_config_entry,
        original_name="OUTPUT 1 output resolution",
    )
    output = NvxAvPort(
        port_id="output_slot0_hdmi_0", direction="output", name="OUTPUT 1"
    )
    async_migrate_port_entities(
        hass, mock_config_entry.entry_id, replace(SNAPSHOT, av_ports=(output,))
    )
    assert (
        registry.async_get(old.entity_id).unique_id
        == f"{DEVICE_ID}_output_{output.port_id}_resolution"
    )
