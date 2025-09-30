"""Sensor platform for YouTube Watching integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ATTR_CHANNEL,
    ATTR_TITLE,
    ATTR_VIDEO_ID,
    ATTR_THUMBNAIL,
    ATTR_DURATION,
    ATTR_URL,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up YouTube Watching sensor from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    async_add_entities([YouTubeWatchingSensor(coordinator)], True)


class YouTubeWatchingSensor(CoordinatorEntity, SensorEntity):
    """Representation of a YouTube Watching sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = "YouTube Watching"
        self._attr_unique_id = f"{DOMAIN}_watching"
        self._attr_icon = "mdi:youtube"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(ATTR_TITLE, "Unknown")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes."""
        if self.coordinator.data is None:
            return {}

        return {
            ATTR_CHANNEL: self.coordinator.data.get(ATTR_CHANNEL),
            ATTR_TITLE: self.coordinator.data.get(ATTR_TITLE),
            ATTR_VIDEO_ID: self.coordinator.data.get(ATTR_VIDEO_ID),
            ATTR_THUMBNAIL: self.coordinator.data.get(ATTR_THUMBNAIL),
            ATTR_DURATION: self.coordinator.data.get(ATTR_DURATION),
            ATTR_URL: self.coordinator.data.get(ATTR_URL),
        }

    @property
    def entity_picture(self) -> str | None:
        """Return the entity picture to use in the frontend."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(ATTR_THUMBNAIL)