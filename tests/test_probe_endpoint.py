"""Tests for privacy-safe endpoint probing."""

from scripts.probe_endpoint import _shape


def test_shape_preserves_public_schema_and_masks_user_keys() -> None:
    """Do not expose user-assigned keys that resemble schema properties."""
    assert _shape(
        {
            "Device": {
                "Outputs": {
                    "LivingRoom": {
                        "Name": "Living Room TV",
                        "FutureProperty": "private value",
                    }
                }
            }
        }
    ) == {
        "Device": {
            "Outputs": {
                "<entry>": {
                    "Name": "str",
                    "<entry>": "str",
                }
            }
        }
    }


def test_shape_collapses_values_to_types() -> None:
    """Keep allowlisted field names without exposing their values."""
    assert _shape({"Model": "DM-NVX-360", "Streams": []}) == {
        "Model": "str",
        "Streams": [],
    }
