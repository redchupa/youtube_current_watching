"""DataUpdateCoordinator for YouTube Watching integration."""
from __future__ import annotations

from datetime import timedelta
import json
import logging
import os
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
        """Initialize the coordinator.
        
        Args:
            hass: Home Assistant instance
            cookies_path: Path to YouTube cookies file
        """
        self.cookies_path = cookies_path
        self.cookies_valid = False
        self.subscriptions_data = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )

    async def _async_update_data(self) -> dict[str, Any] | None:
        """Fetch data from YouTube.
        
        Returns:
            Dictionary containing video information or None if no data
        """
        try:
            history_data = await self.hass.async_add_executor_job(
                self._fetch_youtube_history
            )
            subscriptions_data = await self.hass.async_add_executor_job(
                self._fetch_subscribed_channels
            )
            
            self.subscriptions_data = subscriptions_data
            
            # Mark cookies as valid if either data source succeeds
            if subscriptions_data is not None or history_data is not None:
                self.cookies_valid = True
                _LOGGER.debug("Cookies are valid - data fetched successfully")
            
            return history_data
        except Exception as err:
            _LOGGER.error("Error fetching YouTube data: %s", err)
            raise UpdateFailed(f"Error communicating with YouTube: {err}") from err

    def _get_session(self) -> requests.Session | None:
        """Create and return a session with cookies.
        
        Returns:
            Requests session with loaded cookies or None if failed
        """
        if not os.path.exists(self.cookies_path):
            _LOGGER.error("Cookies file not found at path: %s", self.cookies_path)
            self.cookies_valid = False
            return None
        
        cookie_jar = MozillaCookieJar(self.cookies_path)
        try:
            cookie_jar.load(ignore_discard=True, ignore_expires=True)
        except OSError as err:
            _LOGGER.error(
                "Failed to load cookies file: %s. Error: %s. "
                "Please make sure the file is in Netscape format.",
                self.cookies_path, err
            )
            self.cookies_valid = False
            return None
        except Exception as err:
            _LOGGER.error(
                "Unexpected error loading cookies: %s. "
                "The cookies file might be corrupted.",
                err
            )
            self.cookies_valid = False
            return None

        if len(cookie_jar) == 0:
            _LOGGER.error("Cookies file is empty: %s", self.cookies_path)
            self.cookies_valid = False
            return None

        session = requests.Session()
        session.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-us,en;q=0.5",
            "Sec-Fetch-Mode": "navigate",
        }
        session.cookies = cookie_jar
        
        _LOGGER.debug("Successfully loaded %d cookies from file", len(cookie_jar))
        return session

    def _fetch_youtube_history(self) -> dict[str, Any] | None:
        """Fetch the most recent watch history from YouTube.
        
        Returns:
            Dictionary containing the most recent video information or None
        """
        session = self._get_session()
        if session is None:
            _LOGGER.warning("Cannot fetch history - session creation failed")
            return None

        try:
            response = session.get("https://www.youtube.com/feed/history", timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as err:
            _LOGGER.error("YouTube history request error: %s", err)
            return None

        # Save cookies for next request
        try:
            cookie_jar = MozillaCookieJar(self.cookies_path)
            cookie_jar.load(ignore_discard=True, ignore_expires=True)
            cookie_jar.save(ignore_discard=True, ignore_expires=True)
        except Exception as err:
            _LOGGER.warning("Failed to save cookies: %s", err)

        html = response.text
        
        # Debug: Uncomment below to save HTML for analysis
        # This is useful for troubleshooting YouTube page structure changes
        # try:
        #     debug_path = "/config/youtube_history_debug.html"
        #     with open(debug_path, 'w', encoding='utf-8') as f:
        #         f.write(html)
        #     
        #     video_count = html.count('"videoRenderer"')
        #     lockup_count = html.count('"lockupViewModel"')
        #     rich_count = html.count('"richItemRenderer"')
        #     
        #     _LOGGER.info(
        #         "HTML contains: %d videoRenderer, %d lockupViewModel, %d richItemRenderer",
        #         video_count, lockup_count, rich_count
        #     )
        #     
        # except Exception as err:
        #     _LOGGER.warning("Failed to save debug HTML: %s", err)

        # Parse ytInitialData JSON
        try:
            regex = r"var ytInitialData\s*=\s*({.*?});"
            match = re.search(regex, html, re.DOTALL)
            if not match:
                alt_regex = r"ytInitialData\s*=\s*({.*?});"
                alt_match = re.search(alt_regex, html, re.DOTALL)
                if alt_match:
                    match = alt_match
                else:
                    _LOGGER.error("Cannot find ytInitialData")
                    return None

            json_str = match.group(1)
            json_size = len(json_str)
            _LOGGER.info("ytInitialData size: %d characters", json_size)
            
            data = json.loads(json_str)

        except (AttributeError, json.JSONDecodeError, KeyError) as err:
            _LOGGER.error("Can't parse JSON: %s", err)
            return None

        # Try multiple paths to find video content
        path = None
        
        # Path 1: Standard path
        try:
            path = data["contents"]["twoColumnBrowseResultsRenderer"]["tabs"][0]["tabRenderer"] \
                       ["content"]["sectionListRenderer"]["contents"][0]["itemSectionRenderer"]["contents"]
            _LOGGER.info("Using standard path")
        except (KeyError, TypeError, IndexError):
            pass
                
        # Path 2: Iterate through tabs
        if path is None:
            try:
                tabs = data["contents"]["twoColumnBrowseResultsRenderer"]["tabs"]
                for i, tab in enumerate(tabs):
                    if "tabRenderer" in tab:
                        content = tab["tabRenderer"].get("content", {})
                        if "sectionListRenderer" in content:
                            sections = content["sectionListRenderer"].get("contents", [])
                            for j, section in enumerate(sections):
                                if "itemSectionRenderer" in section:
                                    contents = section["itemSectionRenderer"].get("contents", [])
                                    if contents:
                                        path = contents
                                        _LOGGER.info("Found path in tab[%d] section[%d]", i, j)
                                        break
                        if path:
                            break
            except (KeyError, TypeError):
                pass

        if not path:
            _LOGGER.error("Could not find videos in history")
            return None

        # Check for messageRenderer (empty history or paused)
        for item in path:
            if isinstance(item, dict) and "messageRenderer" in item:
                message_data = item["messageRenderer"]
                message_text = message_data.get("text", {})
                if "runs" in message_text:
                    msg = " ".join([run.get("text", "") for run in message_text["runs"]])
                    _LOGGER.warning("YouTube message: %s", msg)
                elif "simpleText" in message_text:
                    _LOGGER.warning("YouTube message: %s", message_text['simpleText'])
                return None
        
        # Find video: Try lockupViewModel first, then videoRenderer, then Shorts
        video_data = None
        
        # Step 1: Look for lockupViewModel (new YouTube format)
        for item in path:
            if isinstance(item, dict) and "lockupViewModel" in item:
                lockup = item["lockupViewModel"]
                content_type = lockup.get("contentType", "")
                if content_type == "LOCKUP_CONTENT_TYPE_VIDEO":
                    video_data = self._extract_lockup_info(lockup)
                    if video_data:
                        _LOGGER.info("Found lockupViewModel video")
                        return video_data
        
        # Step 2: Look for videoRenderer (old YouTube format)
        for item in path:
            if isinstance(item, dict):
                if "videoRenderer" in item:
                    video_data = self._extract_video_renderer_info(item["videoRenderer"])
                    if video_data:
                        _LOGGER.info("Found videoRenderer")
                        return video_data
                elif "richItemRenderer" in item:
                    content = item["richItemRenderer"].get("content", {})
                    if "videoRenderer" in content:
                        video_data = self._extract_video_renderer_info(content["videoRenderer"])
                        if video_data:
                            _LOGGER.info("Found videoRenderer in richItemRenderer")
                            return video_data
        
        # Step 3: Look for Shorts
        for item in path:
            if isinstance(item, dict):
                if "reelShelfRenderer" in item:
                    reel_shelf = item["reelShelfRenderer"]
                    reel_items = reel_shelf.get("items", [])
                    for reel_item in reel_items:
                        if "shortsLockupViewModel" in reel_item:
                            video_data = self._extract_shorts_info(reel_item["shortsLockupViewModel"])
                            if video_data:
                                _LOGGER.info("Found Shorts video")
                                return video_data

        _LOGGER.error("No video found in history")
        return None

    def _extract_lockup_info(self, lockup: dict) -> dict[str, Any] | None:
        """Extract information from lockupViewModel (new YouTube format).
        
        Args:
            lockup: lockupViewModel dictionary from YouTube API
            
        Returns:
            Dictionary containing video information or None if extraction fails
        """
        try:
            video_id = lockup.get("contentId")
            if not video_id:
                return None
            
            metadata = lockup.get("metadata", {}).get("lockupMetadataViewModel", {})
            
            # Extract title
            title = metadata.get("title", {}).get("content", "N/A")
            
            # Extract channel from first metadata row
            channel = "N/A"
            metadata_rows = metadata.get("metadata", {}).get("contentMetadataViewModel", {}).get("metadataRows", [])
            if metadata_rows:
                first_row = metadata_rows[0]
                parts = first_row.get("metadataParts", [])
                if parts:
                    channel = parts[0].get("text", {}).get("content", "N/A")
            
            # Extract duration from thumbnail overlay
            duration = "N/A"
            thumbnail = lockup.get("contentImage", {}).get("thumbnailViewModel", {})
            overlays = thumbnail.get("overlays", [])
            for overlay in overlays:
                if "thumbnailBottomOverlayViewModel" in overlay:
                    badges = overlay["thumbnailBottomOverlayViewModel"].get("badges", [])
                    for badge in badges:
                        if "thumbnailBadgeViewModel" in badge:
                            duration = badge["thumbnailBadgeViewModel"].get("text", "N/A")
                            break
                    if duration != "N/A":
                        break
            
            output = {
                "channel": channel,
                "title": title,
                "video_id": video_id,
                "duration": duration,
                "thumbnail": self._get_best_thumbnail(video_id),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }

            _LOGGER.info("Extracted: %s by %s", title, channel)
            return output
            
        except Exception as err:
            _LOGGER.error("Failed to extract lockupViewModel: %s", err)
            return None

    def _extract_video_renderer_info(self, video_renderer: dict) -> dict[str, Any] | None:
        """Extract information from videoRenderer (old YouTube format).
        
        Args:
            video_renderer: videoRenderer dictionary from YouTube API
            
        Returns:
            Dictionary containing video information or None if extraction fails
        """
        try:
            video_id = video_renderer.get("videoId", "N/A")
            
            # Extract title
            title = "N/A"
            if "title" in video_renderer:
                title_data = video_renderer["title"]
                if "runs" in title_data and len(title_data["runs"]) > 0:
                    title = title_data["runs"][0].get("text", "N/A")
                elif "simpleText" in title_data:
                    title = title_data["simpleText"]
            
            # Extract channel
            channel = "N/A"
            for key in ["longBylineText", "shortBylineText", "ownerText"]:
                if key in video_renderer:
                    byline = video_renderer[key]
                    if "runs" in byline and len(byline["runs"]) > 0:
                        channel = byline["runs"][0].get("text", "N/A")
                        break
                    elif "simpleText" in byline:
                        channel = byline["simpleText"]
                        break
            
            output = {
                "channel": channel,
                "title": title,
                "video_id": video_id,
                "duration": video_renderer.get("lengthText", {}).get("simpleText", "N/A"),
                "thumbnail": self._get_best_thumbnail(video_id),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }

            return output
            
        except Exception as err:
            _LOGGER.error("Failed to extract videoRenderer: %s", err)
            return None

    def _extract_shorts_info(self, shorts_data: dict) -> dict[str, Any] | None:
        """Extract information from shortsLockupViewModel.
        
        Args:
            shorts_data: shortsLockupViewModel dictionary from YouTube API
            
        Returns:
            Dictionary containing Shorts video information or None if extraction fails
        """
        try:
            entity_id = shorts_data.get("entityId", "")
            video_id = entity_id.split("-")[-1] if entity_id else None
            
            # Alternative method to get video ID
            if not video_id or video_id == "item":
                on_tap = shorts_data.get("onTap", {})
                innertube = on_tap.get("innertubeCommand", {})
                reel_watch = innertube.get("reelWatchEndpoint", {})
                video_id = reel_watch.get("videoId")
            
            if not video_id:
                return None
            
            overlay = shorts_data.get("overlayMetadata", {})
            title = overlay.get("primaryText", {}).get("content", "YouTube Shorts")
            
            output = {
                "channel": "YouTube Shorts",
                "title": title,
                "video_id": video_id,
                "duration": "Shorts",
                "thumbnail": self._get_best_thumbnail(video_id),
                "url": f"https://www.youtube.com/shorts/{video_id}",
            }
            
            return output
            
        except Exception as err:
            _LOGGER.error("Failed to extract Shorts info: %s", err)
            return None

    def _fetch_subscribed_channels(self) -> dict[str, Any] | None:
        """Fetch subscribed channels from YouTube.
        
        Returns:
            Dictionary containing subscription information or None if fetch fails
        """
        session = self._get_session()
        if session is None:
            return None

        try:
            response = session.get("https://www.youtube.com/feed/channels", timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as err:
            _LOGGER.error("YouTube subscriptions request error: %s", err)
            return None

        html = response.text

        try:
            regex = r"var ytInitialData\s*=\s*({.*?});"
            match = re.search(regex, html, re.DOTALL)
            if not match:
                _LOGGER.warning("Couldn't find ytInitialData in subscriptions page")
                return None

            json_str = match.group(1)
            data = json.loads(json_str)

            tabs = data["contents"]["twoColumnBrowseResultsRenderer"]["tabs"]
            
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
                _LOGGER.warning("No channel list found")
                return {"total_count": 0, "channels": []}

            channels = []
            for item in channel_list:
                if "channelRenderer" in item:
                    channel_renderer = item["channelRenderer"]
                    channel_title = channel_renderer.get("title", {}).get("simpleText", "")
                    
                    if channel_title:
                        channels.append({"channel_name": channel_title})

            result = {
                "total_count": len(channels),
                "channels": channels,
            }

            _LOGGER.info("Fetched %d subscribed channels", len(channels))
            return result

        except (AttributeError, json.JSONDecodeError, KeyError) as err:
            _LOGGER.error("Can't parse subscriptions JSON: %s", err)
            return None

    def _get_best_thumbnail(self, video_id: str) -> str:
        """Get the best available thumbnail for a video.
        
        Args:
            video_id: YouTube video ID
            
        Returns:
            URL of the best available thumbnail
        """
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