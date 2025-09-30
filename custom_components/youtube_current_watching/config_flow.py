"""Config flow for YouTube Watching integration."""
from __future__ import annotations

import logging
import os
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_APPLE_TV,
    CONF_COOKIES_PATH,
    CONF_TRACK_ALL,
    DEFAULT_COOKIES_PATH,
)

_LOGGER = logging.getLogger(__name__)


class YouTubeCurrentWatchingConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for YouTube Watching."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Validate cookies file exists
            cookies_path = user_input[CONF_COOKIES_PATH]
            
            try:
                file_exists = await self.hass.async_add_executor_job(
                    os.path.exists, cookies_path
                )
                
                if not file_exists:
                    errors["base"] = "cookies_not_found"
                else:
                    # Check for existing entries
                    await self.async_set_unique_id(f"{DOMAIN}_{user_input[CONF_APPLE_TV]}")
                    self._abort_if_unique_id_configured()
                    
                    # Create entry
                    return self.async_create_entry(
                        title="YouTube Current Watching",
                        data={
                            CONF_APPLE_TV: user_input[CONF_APPLE_TV],
                            CONF_COOKIES_PATH: cookies_path,
                            CONF_TRACK_ALL: user_input.get(CONF_TRACK_ALL, False),
                        },
                    )
            except Exception as err:
                _LOGGER.exception("Unexpected error during config flow: %s", err)
                errors["base"] = "unknown"

        # Get list of media_player entities
        try:
            media_players = self.hass.states.async_entity_ids("media_player")
        except Exception as err:
            _LOGGER.exception("Error getting media players: %s", err)
            media_players = []

        if not media_players and not errors:
            errors["base"] = "no_media_players"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_APPLE_TV): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="media_player",
                        multiple=False,
                    )
                ),
                vol.Required(
                    CONF_COOKIES_PATH, 
                    default=DEFAULT_COOKIES_PATH
                ): str,
                vol.Optional(CONF_TRACK_ALL, default=False): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )