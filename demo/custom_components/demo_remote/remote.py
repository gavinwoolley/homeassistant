"""Minimal, genuinely-stateful demo remote platform.

remote has no template/YAML backing in this HA version (same reasoning as
lawn_mower/media_player - confirmed against the installed source), so the
real dashboard's TV remote cards would otherwise permanently show "Entity
not found" for every button. This provides one real RemoteEntity per entry
in `remotes:` instead - turning it on/off and sending commands both
genuinely work (a sent command is just logged, same treatment as every
generated button.* entity elsewhere in this demo).
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import voluptuous as vol

from homeassistant.components.remote import PLATFORM_SCHEMA, RemoteEntity
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

CONF_REMOTES = "remotes"
CONF_OBJECT_ID = "object_id"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_REMOTES): vol.All(
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
    """Set up the demo remote platform."""
    async_add_entities(
        DemoRemote(r[CONF_NAME], r[CONF_OBJECT_ID]) for r in config[CONF_REMOTES]
    )


class DemoRemote(RemoteEntity):
    """A single fake, genuinely-stateful remote."""

    _attr_should_poll = False

    def __init__(self, name: str, object_id: str) -> None:
        self._attr_name = name
        self._attr_unique_id = f"demo_rm_{object_id}"
        self.entity_id = f"remote.{object_id}"
        self._attr_is_on = True

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        await self.hass.services.async_call(
            "logbook",
            "log",
            {"name": self._attr_name, "message": f"sent command: {', '.join(command)} (demo)"},
        )
