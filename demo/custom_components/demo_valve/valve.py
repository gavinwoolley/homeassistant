"""Minimal, genuinely-stateful demo valve platform.

valve has no template/YAML backing in this HA version (same reasoning as
lawn_mower/media_player/remote - confirmed against the installed source), so
the real irrigation dashboard's per-zone valve tiles would otherwise
permanently show "Entity not found". This provides one real ValveEntity per
entry in `valves:` instead - toggling it in the UI genuinely opens/closes and
sticks, same treatment as every other generated demo entity.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.valve import (
    PLATFORM_SCHEMA,
    ValveEntity,
    ValveEntityFeature,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

CONF_VALVES = "valves"
CONF_OBJECT_ID = "object_id"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_VALVES): vol.All(
            cv.ensure_list,
            [
                vol.Schema(
                    {
                        vol.Required(CONF_NAME): cv.string,
                        vol.Required(CONF_OBJECT_ID): cv.string,
                    }
                )
            ],
        )
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the demo valve platform."""
    async_add_entities(
        DemoValve(v[CONF_NAME], v[CONF_OBJECT_ID]) for v in config[CONF_VALVES]
    )


class DemoValve(ValveEntity):
    """A single fake, genuinely-stateful irrigation valve."""

    _attr_should_poll = False
    _attr_reports_position = False
    _attr_supported_features = ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE

    def __init__(self, name: str, object_id: str) -> None:
        self._attr_name = name
        self._attr_unique_id = f"demo_valve_{object_id}"
        self.entity_id = f"valve.{object_id}"
        self._attr_is_closed = True

    async def async_open_valve(self, **kwargs: Any) -> None:
        self._attr_is_closed = False
        self.async_write_ha_state()

    async def async_close_valve(self, **kwargs: Any) -> None:
        self._attr_is_closed = True
        self.async_write_ha_state()
