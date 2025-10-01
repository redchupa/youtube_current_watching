"""DataUpdateCoordinator for YouTube Watching integration."""
from __future__ import annotations

from datetime import timedelta
import json
import logging
import re
from http.cookiejar import MozillaCookieJar
from typing import Any

import requests

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class YouTubeDataCoordinator(DataUpdateCoordinator):
    """Class to manage fetching YouTube watch history data."""

    def __init__(self, hass: HomeAssistant, cookies_path: str) -> None:
        """Initialize."""
        self.cookies_path = cookies_path
        self.cookies_valid = False
        self.subscriptions_data = None  # 구독 채널 데이터 저장

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )

    async def _async_update_data(self) -> dict[str, Any] | None:
        """Fetch data from YouTube."""
        try:
            # 시청 기록과 구독 채널 정보를 동시에 가져옴
            history_data = await self.hass.async_add_executor_job(self._fetch_youtube_history)
            subscriptions_data = await self.hass.async_add_executor_job(self._fetch_subscribed_channels)
            
            self.subscriptions_data = subscriptions_data
            
            return history_data
        except Exception as err:
            _LOGGER.error("Error fetching YouTube data: %s", err)
            raise UpdateFailed(f"Error communicating with YouTube: {err}") from err

    def _get_session(self) -> requests.Session | None:
        """Create and return a session with cookies."""
        # Load cookies
        cookie_jar = MozillaCookieJar(self.cookies_path)
        try:
            cookie_jar.load(ignore_discard=True, ignore_expires=True)
        except OSError as err:
            _LOGGER.error("Cookies file not found: %s. Error: %s", self.cookies_path, err)
            self.cookies_valid = False
            return None

        # Create session
        session = requests.Session()
        session.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-us,en;q=0.5",
            "Sec-Fetch-Mode": "navigate",
        }
        session.cookies = cookie_jar
        
        return session

    def _fetch_youtube_history(self) -> dict[str, Any] | None:
        """Fetch the most recent watch history from YouTube."""
        session = self._get_session()
        if session is None:
            return None

        # Fetch YouTube history page
        try:
            response = session.get("https://www.youtube.com/feed/history", timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as err:
            _LOGGER.error("YouTube request error: %s", err)
            self.cookies_valid = False
            return None

        # Save cookies
        try:
            cookie_jar = MozillaCookieJar(self.cookies_path)
            cookie_jar.load(ignore_discard=True, ignore_expires=True)
            cookie_jar.save(ignore_discard=True, ignore_expires=True)
        except Exception as err:
            _LOGGER.warning("Failed to save cookies: %s", err)

        html = response.text

        # Parse ytInitialData JSON
        try:
            regex = r"var ytInitialData\s*=\s*(\{.*?\});"
            match = re.search(regex, html, re.DOTALL)
            if not match:
                raise AttributeError("Couldn't find ytInitialData JSON in the page source.")

            json_str = match.group(1)
            data = json.loads(json_str)

            # Navigate to video renderer
            path = data["contents"]["twoColumnBrowseResultsRenderer"]["tabs"][0]["tabRenderer"] \
                       ["content"]["sectionListRenderer"]["contents"][0]["itemSectionRenderer"]["contents"]

        except (AttributeError, json.JSONDecodeError, KeyError) as err:
            _LOGGER.error("Can't parse ytInitialData JSON: %s", err)
            self.cookies_valid = False
            return None

        # Find video renderer
        video_renderer = None
        for item in path:
            if "videoRenderer" in item:
                video_renderer = item["videoRenderer"]
                break

        if video_renderer is None:
            _LOGGER.error("No videoRenderer found in YouTube data")
            self.cookies_valid = False
            return None

        # Cookies are valid
        self.cookies_valid = True

        # Extract video information
        video_id = video_renderer.get("videoId", "N/A")
        
        output = {
            "channel": video_renderer.get("longBylineText", {}).get("runs", [{}])[0].get("text", "N/A"),
            "title": video_renderer.get("title", {}).get("runs", [{}])[0].get("text", "N/A"),
            "video_id": video_id,
            "duration": video_renderer.get("lengthText", {}).get("simpleText", "N/A"),
            "thumbnail": self._get_best_thumbnail(video_id),
            "url": f"https://www.youtube.com/watch?v={video_id}",
        }

        return output

    def _fetch_subscribed_channels(self) -> dict[str, Any] | None:
        """Fetch subscribed channels from YouTube."""
        session = self._get_session()
        if session is None:
            return None

        # Fetch YouTube subscriptions page
        try:
            response = session.get("https://www.youtube.com/feed/channels", timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as err:
            _LOGGER.error("YouTube subscriptions request error: %s", err)
            return None

        html = response.text

        # Parse ytInitialData JSON
        try:
            regex = r"var ytInitialData\s*=\s*(\{.*?\});"
            match = re.search(regex, html, re.DOTALL)
            if not match:
                _LOGGER.warning("Couldn't find ytInitialData JSON in subscriptions page")
                return None

            json_str = match.group(1)
            data = json.loads(json_str)

            # Navigate to channel list
            tabs = data["contents"]["twoColumnBrowseResultsRenderer"]["tabs"]
            
            # Find the subscriptions tab
            channel_list = None
            for tab in tabs:
                if "tabRenderer" in tab:
                    tab_content = tab["tabRenderer"].get("content", {})
                    if "sectionListRenderer" in tab_content:
                        sections = tab_content["sectionListRenderer"].get("contents", [])
                        for section in sections:
                            if "itemSectionRenderer" in section:
                                items = section["itemSectionRenderer"].get("contents", [])
                                for item in items:
                                    if "shelfRenderer" in item:
                                        shelf_content = item["shelfRenderer"].get("content", {})
                                        if "expandedShelfContentsRenderer" in shelf_content:
                                            channel_list = shelf_content["expandedShelfContentsRenderer"].get("items", [])
                                            break
                                if channel_list:
                                    break
                    if channel_list:
                        break

            if not channel_list:
                _LOGGER.warning("No channel list found in subscriptions data")
                return {"total_count": 0, "channels": []}

            # Extract channel information (채널명만 추출)
            channels = []
            for item in channel_list:
                if "channelRenderer" in item:
                    channel_renderer = item["channelRenderer"]
                    channel_title = channel_renderer.get("title", {}).get("simpleText", "")
                    
                    if channel_title:  # 빈 이름 제외
                        channels.append({"channel_name": channel_title})

            result = {
                "total_count": len(channels),
                "channels": channels,
            }

            _LOGGER.info("Successfully fetched %d subscribed channels", len(channels))
            return result

        except (AttributeError, json.JSONDecodeError, KeyError) as err:
            _LOGGER.error("Can't parse subscriptions ytInitialData JSON: %s", err)
            return None

    def _get_best_thumbnail(self, video_id: str) -> str:
        """Get the best available thumbnail for a video."""
        if not video_id or video_id == "N/A":
            return ""
            
        url_base = f"https://img.youtube.com/vi/{video_id}"
        maxres_url = f"{url_base}/maxresdefault.jpg"
        default_url = f"{url_base}/0.jpg"

        try:
            response = requests.get(maxres_url, timeout=3)
            if response.status_code == 200:
                return maxres_url
        except requests.exceptions.RequestException as err:
            _LOGGER.debug("Thumbnail request error: %s", err)

        return default_url
