"""Minimal stand-in lawn mower platform for the demo instance.

The real mower is a robot lawn mower integration whose entity_id bakes in
the device's own serial number (lawn_mower.mower_<serial>) - config-entry
only, no YAML/template backing exists for that domain anywhere in this HA
version (confirmed against the installed source: no climate-style
"generic_lawn_mower" integration, and the template component has no
lawn_mower.py). Left ungenerated, the real dashboard's lawn_mower card
falls back to "Entity not found" and prints that real serial as literal
text. This provides one fake, harmless lawn_mower entity under a made-up
id instead, so nothing real ever appears on screen.
"""
from __future__ import annotations

from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
    PLATFORM_SCHEMA,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the demo lawn mower platform."""
    async_add_entities([DemoLawnMower()])


class DemoLawnMower(LawnMowerEntity):
    """A single fake, always-available lawn mower."""

    _attr_name = "Ambrogio L250i Deluxe"
    _attr_unique_id = "demo_lawn_mower_1"
    _attr_supported_features = (
        LawnMowerEntityFeature.START_MOWING
        | LawnMowerEntityFeature.PAUSE
        | LawnMowerEntityFeature.DOCK
    )

    def __init__(self) -> None:
        self.entity_id = "lawn_mower.mower_demo"
        self._attr_activity = LawnMowerActivity.DOCKED

    async def async_start_mowing(self) -> None:
        self._attr_activity = LawnMowerActivity.MOWING
        self.async_write_ha_state()

    async def async_pause(self) -> None:
        self._attr_activity = LawnMowerActivity.PAUSED
        self.async_write_ha_state()

    async def async_dock(self) -> None:
        self._attr_activity = LawnMowerActivity.DOCKED
        self.async_write_ha_state()
