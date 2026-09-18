"""Minimal, genuinely-stateful demo media_player platform.

media_player has no template/YAML backing in this HA version (same as
lawn_mower - confirmed against the installed source, no media_player.py
under the template component), so every media_player card on the real
dashboard would otherwise permanently show "Entity not found". This
provides one real, toggleable MediaPlayerEntity per entry in `players:`
instead - power on/off, play/pause/stop, volume, and source selection all
genuinely work and stick, same as every other "come alive" entity in this
demo (switch/light/vacuum/...).
"""
from __future__ import annotations

import random

import voluptuous as vol

from homeassistant.components.media_player import (
    PLATFORM_SCHEMA,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

CONF_PLAYERS = "players"
CONF_OBJECT_ID = "object_id"
CONF_SOURCES = "sources"
CONF_KIND = "kind"

DEFAULT_SOURCES = ["Netflix", "YouTube", "Disney+", "HDMI 1", "Live TV"]

# Picked whenever a player transitions into PLAYING with nothing already
# queued (a real "come alive" turn-on, not a resume) - makes the "now
# playing" card show something plausible instead of a blank title, without
# any automation needing to know or choose what's playing. Simpsons-canon
# titles, same decoy theme as the zone/place names elsewhere in this demo.
VIDEO_CONTENT = [
    ("The Itchy & Scratchy Show", "tvshow"),
    ("Krusty the Klown Show", "tvshow"),
    ("McBain: Let's Get Silly", "movie"),
    ("Troy McClure's Fire Safety Tips", "movie"),
    ("Radioactive Man", "movie"),
    ("Down with Homework (documentary)", "movie"),
]
MUSIC_CONTENT = [
    ("Do the Bartman", "Bart Simpson"),
    ("See My Vest", "Mr. Burns"),
    ("The Monorail Song", "Lyle Lanley"),
    ("We Put the Spring in Springfield", "Miss Springfield"),
    ("Señor Burns", "The Be Sharps"),
    ("Duff Beer Jingle", "Duff Brewing Co."),
]

# object_id substring -> content pool. Checked in order, first match wins;
# anything unmatched (generic "speaker"/group entities) falls back to music,
# same as a real smart speaker with no screen.
_VIDEO_HINTS = ("roku_tv", "chromecast", "smartdisplay", "smart_display")

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_PLAYERS): vol.All(
            cv.ensure_list,
            [
                vol.Schema(
                    {
                        vol.Required(CONF_NAME): cv.string,
                        vol.Required(CONF_OBJECT_ID): cv.string,
                        vol.Optional(CONF_SOURCES, default=DEFAULT_SOURCES): [cv.string],
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
    """Set up the demo media_player platform."""
    async_add_entities(
        DemoMediaPlayer(p[CONF_NAME], p[CONF_OBJECT_ID], p[CONF_SOURCES])
        for p in config[CONF_PLAYERS]
    )


class DemoMediaPlayer(MediaPlayerEntity):
    """A single fake, genuinely-stateful media player."""

    _attr_should_poll = False
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
    )

    def __init__(self, name: str, object_id: str, sources: list[str]) -> None:
        self._attr_name = name
        self._attr_unique_id = f"demo_mp_{object_id}"
        self.entity_id = f"media_player.{object_id}"
        self._attr_state = MediaPlayerState.OFF
        self._attr_volume_level = 0.4
        self._attr_is_volume_muted = False
        self._attr_source_list = sources
        self._attr_source = sources[0]
        self._video_capable = any(h in object_id for h in _VIDEO_HINTS)
        self._attr_media_title = None
        self._attr_media_artist = None
        self._attr_media_content_type = None
        self._attr_media_image_url = None

    def _pick_now_playing(self) -> None:
        if self._video_capable:
            title, content_type = random.choice(VIDEO_CONTENT)
            self._attr_media_title = title
            self._attr_media_artist = None
            self._attr_media_content_type = content_type
            self._attr_media_image_url = "/local/media-video-placeholder.svg"
        else:
            title, artist = random.choice(MUSIC_CONTENT)
            self._attr_media_title = title
            self._attr_media_artist = artist
            self._attr_media_content_type = "music"
            self._attr_media_image_url = "/local/media-music-placeholder.svg"

    def _clear_now_playing(self) -> None:
        self._attr_media_title = None
        self._attr_media_artist = None
        self._attr_media_content_type = None
        self._attr_media_image_url = None

    async def async_turn_on(self) -> None:
        self._attr_state = MediaPlayerState.PLAYING
        self._pick_now_playing()
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        self._attr_state = MediaPlayerState.OFF
        self._clear_now_playing()
        self.async_write_ha_state()

    async def async_media_play(self) -> None:
        self._attr_state = MediaPlayerState.PLAYING
        if not self._attr_media_title:
            self._pick_now_playing()
        self.async_write_ha_state()

    async def async_media_pause(self) -> None:
        self._attr_state = MediaPlayerState.PAUSED
        self.async_write_ha_state()

    async def async_media_stop(self) -> None:
        self._attr_state = MediaPlayerState.IDLE
        self._clear_now_playing()
        self.async_write_ha_state()

    async def async_set_volume_level(self, volume: float) -> None:
        self._attr_volume_level = volume
        self.async_write_ha_state()

    async def async_volume_up(self) -> None:
        self._attr_volume_level = min(1.0, (self._attr_volume_level or 0.0) + 0.05)
        self.async_write_ha_state()

    async def async_volume_down(self) -> None:
        self._attr_volume_level = max(0.0, (self._attr_volume_level or 0.0) - 0.05)
        self.async_write_ha_state()

    async def async_mute_volume(self, mute: bool) -> None:
        self._attr_is_volume_muted = mute
        self.async_write_ha_state()

    async def async_select_source(self, source: str) -> None:
        self._attr_source = source
        self._attr_state = MediaPlayerState.PLAYING
        self._pick_now_playing()
        self.async_write_ha_state()

    async def async_media_next_track(self) -> None:
        if self._attr_state == MediaPlayerState.PLAYING:
            self._pick_now_playing()
        self.async_write_ha_state()

    async def async_media_previous_track(self) -> None:
        self.async_write_ha_state()
