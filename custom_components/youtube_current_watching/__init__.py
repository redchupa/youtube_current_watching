"""The YouTube Watching integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, STATE_PLAYING
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN, CONF_APPLE_TV, CONF_COOKIES_PATH, CONF_TRACK_ALL, YOUTUBE_APP_IDS
from .coordinator import YouTubeDataCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up YouTube Watching from a config entry."""
    
    # Create coordinator
    coordinator = YouTubeDataCoordinator(
        hass,
        entry.data[CONF_COOKIES_PATH],
    )

    # Store coordinator and config
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "apple_tv_entity": entry.data[CONF_APPLE_TV],
        "track_all": entry.data.get(CONF_TRACK_ALL, False),
    }

    # Track all mode: 미디어 플레이어 상태와 관계없이 주기적으로 업데이트
    track_all_mode = entry.data.get(CONF_TRACK_ALL, False)
    
    if track_all_mode:
        _LOGGER.info("Track All mode enabled - will update regardless of media player state")
        # 주기적 업데이트만 사용 (coordinator의 update_interval에 의존)
    else:
        # Set up state listener for media player (기존 방식)
        @callback
        def media_player_state_changed(event):
            """Handle media player state changes."""
            new_state = event.data.get("new_state")
            old_state = event.data.get("old_state")
            
            if new_state is None:
                return

            # Check if state changed to playing
            if new_state.state == STATE_PLAYING and (old_state is None or old_state.state != STATE_PLAYING):
                # Get attributes
                app_id = new_state.attributes.get("app_id", "")
                app_name = new_state.attributes.get("app_name", "")
                media_title = new_state.attributes.get("media_title", "")
                source = new_state.attributes.get("source", "")
                media_content_id = new_state.attributes.get("media_content_id", "")
                
                # Check if YouTube is playing (multiple methods)
                is_youtube = False
                detection_method = None
                
                # Method 1: Check app_id (Apple TV, Android TV, etc.)
                if app_id in YOUTUBE_APP_IDS:
                    is_youtube = True
                    detection_method = f"app_id: {app_id}"
                
                # Method 2: Check app_name
                elif "youtube" in app_name.lower():
                    is_youtube = True
                    detection_method = f"app_name: {app_name}"
                
                # Method 3: Check source
                elif "youtube" in source.lower():
                    is_youtube = True
                    detection_method = f"source: {source}"
                
                # Method 4: Check media_content_id (URL 포함 가능)
                elif "youtube" in media_content_id.lower():
                    is_youtube = True
                    detection_method = f"media_content_id: {media_content_id}"
                
                # Method 5: Check media_title for YouTube patterns
                elif media_title and any(keyword in media_title.lower() for keyword in ["youtube", "yt:"]):
                    is_youtube = True
                    detection_method = f"media_title: {media_title}"
                
                if is_youtube:
                    _LOGGER.info("YouTube detected via %s", detection_method)
                    
                    # Check if title changed
                    current_sensor_title = None
                    if coordinator.data:
                        current_sensor_title = coordinator.data.get("title")
                    
                    if media_title and media_title != current_sensor_title:
                        _LOGGER.debug("YouTube started playing new video: %s", media_title)
                        hass.async_create_task(coordinator.async_refresh())
                    else:
                        _LOGGER.debug("Same video playing, skipping refresh")
                else:
                    _LOGGER.debug(
                        "Not YouTube - app_id: %s, app_name: %s, source: %s, media_content_id: %s, media_title: %s",
                        app_id, app_name, source, media_content_id, media_title
                    )

        # Track media player state changes
        entry.async_on_unload(
            async_track_state_change_event(
                hass,
                [entry.data[CONF_APPLE_TV]],
                media_player_state_changed,
            )
        )

    # Initial data fetch
    await coordinator.async_config_entry_first_refresh()

    # Forward entry setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok