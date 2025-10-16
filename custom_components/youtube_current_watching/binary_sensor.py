"""Binary sensor platform for YouTube Watching integration."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up YouTube Watching binary sensor from a config entry.
    
    Args:
        hass: Home Assistant instance
        entry: Config entry
        async_add_entities: Callback to add entities
    """
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    async_add_entities([YouTubeCookiesStatusSensor(coordinator)], True)


class YouTubeCookiesStatusSensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of YouTube Cookies Status binary sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator) -> None:
        """Initialize the binary sensor.
        
        Args:
            coordinator: Data coordinator instance
        """
        super().__init__(coordinator)
        self._attr_name = "Youtube Cookies Status"
        self._attr_unique_id = f"{DOMAIN}_cookies_status"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_icon = "mdi:cookie"

    @property
    def is_on(self) -> bool:
        """Return true if cookies are valid."""
        # Cookies are valid if either subscription data or history data is successfully fetched
        has_subscription_data = self.coordinator.subscriptions_data is not None
        has_history_data = self.coordinator.data is not None
        
        # If either data source has data, cookies are valid
        if has_subscription_data or has_history_data:
            return True
        
        # Also check coordinator's cookies_valid flag
        return self.coordinator.cookies_valid

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        return {
            "has_history_data": self.coordinator.data is not None,
            "has_subscription_data": self.coordinator.subscriptions_data is not None,
            "cookies_valid_flag": self.coordinator.cookies_valid,
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True  # Always available to show cookie status