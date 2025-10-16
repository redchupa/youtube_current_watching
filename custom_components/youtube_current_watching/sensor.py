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
    ATTR_TOTAL_COUNT,
    ATTR_CHANNELS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up YouTube Watching sensor from a config entry.
    
    Args:
        hass: Home Assistant instance
        entry: Config entry
        async_add_entities: Callback to add entities
    """
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    async_add_entities(
        [
            YouTubeWatchingSensor(coordinator),
            YouTubeSubscriptionsSensor(coordinator),
        ],
        True,
    )


class YouTubeWatchingSensor(CoordinatorEntity, SensorEntity):
    """Representation of a YouTube Watching sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator) -> None:
        """Initialize the sensor.
        
        Args:
            coordinator: Data coordinator instance
        """
        super().__init__(coordinator)
        self._attr_name = "YouTube Watching"
        self._attr_unique_id = f"{DOMAIN}_watching"
        self._attr_icon = "mdi:youtube"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return "No Recent Videos"
        
        title = self.coordinator.data.get(ATTR_TITLE)
        if not title or title == "N/A":
            return "No Recent Videos"
            
        return title

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes."""
        if self.coordinator.data is None:
            return {
                ATTR_CHANNEL: None,
                ATTR_TITLE: None,
                ATTR_VIDEO_ID: None,
                ATTR_THUMBNAIL: None,
                ATTR_DURATION: None,
                ATTR_URL: None,
            }

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

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Always available if cookies are valid (even if no data yet)
        return self.coordinator.cookies_valid


class YouTubeSubscriptionsSensor(CoordinatorEntity, SensorEntity):
    """Representation of a YouTube Subscriptions sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator) -> None:
        """Initialize the sensor.
        
        Args:
            coordinator: Data coordinator instance
        """
        super().__init__(coordinator)
        self._attr_name = "YouTube Subscriptions"
        self._attr_unique_id = f"{DOMAIN}_subscriptions"
        self._attr_icon = "mdi:youtube-subscription"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor (total subscription count)."""
        if self.coordinator.subscriptions_data is None:
            return 0
        return self.coordinator.subscriptions_data.get(ATTR_TOTAL_COUNT, 0)

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return "channels"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes."""
        if self.coordinator.subscriptions_data is None:
            return {
                ATTR_TOTAL_COUNT: 0,
                "channel_names": [],
            }

        channels = self.coordinator.subscriptions_data.get(ATTR_CHANNELS, [])
        
        # Extract and process channel names
        channel_names = []
        for channel in channels:
            name = channel.get("channel_name", "Unknown")
            # Replace commas with periods to avoid delimiter confusion
            name = name.replace(",", ".")
            # Truncate long names and add ellipsis
            if len(name) > 30:
                name = name[:30] + "..."
            channel_names.append(name)
        
        return {
            ATTR_TOTAL_COUNT: self.coordinator.subscriptions_data.get(ATTR_TOTAL_COUNT, 0),
            "channel_names": channel_names,
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Always available if cookies are valid
        return self.coordinator.cookies_valid