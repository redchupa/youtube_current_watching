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
        self.recommended_data = None  # 추천 영상 데이터 추가

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
            # 추천 영상 가져오기 추가
            recommended_data = await self.hass.async_add_executor_job(
                self._fetch_recommended_videos
            )
            
            self.subscriptions_data = subscriptions_data
            self.recommended_data = recommended_data
            
            # Mark cookies as valid if any data source succeeds
            if subscriptions_data is not None or history_data is not None or recommended_data is not None:
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

    def _fetch_recommended_videos(self) -> list[dict[str, Any]] | None:
        """Fetch recommended videos from YouTube (최대 3개).
        
        Returns:
            List of dictionaries containing recommended video information or None
        """
        session = self._get_session()
        if session is None:
            _LOGGER.warning("Cannot fetch recommended - session creation failed")
            return None

        try:
            response = session.get("https://www.youtube.com", timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as err:
            _LOGGER.error("YouTube recommended request error: %s", err)
            return None

        html = response.text

        try:
            regex = r"var ytInitialData\s*=\s*({.*?});"
            match = re.search(regex, html, re.DOTALL)
            if not match:
                _LOGGER.warning("Couldn't find ytInitialData in home page")
                return None

            json_str = match.group(1)
            data = json.loads(json_str)

            # YouTube 홈페이지 구조 파싱
            tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
            
            videos = []
            
            # selected가 true인 탭 찾기
            for tab in tabs:
                tab_renderer = tab.get("tabRenderer", {})
                if tab_renderer.get("selected"):
                    # richGridRenderer 찾기
                    rich_grid = tab_renderer.get("content", {}).get("richGridRenderer", {})
                    grid_contents = rich_grid.get("contents", [])
                    
                    _LOGGER.info("Found richGridRenderer with %d items", len(grid_contents))
                    
                    for item in grid_contents:
                        # richItemRenderer에서 비디오 찾기
                        rich_item = item.get("richItemRenderer", {})
                        content = rich_item.get("content", {})
                        
                        # lockupViewModel 체크
                        if "lockupViewModel" in content:
                            lockup = content["lockupViewModel"]
                            
                            # contentType이 VIDEO인지 확인
                            content_type = lockup.get("contentType", "")
                            if content_type == "LOCKUP_CONTENT_TYPE_VIDEO":
                                video_info = self._extract_lockup_info(lockup)
                                if video_info:
                                    videos.append(video_info)
                                    _LOGGER.debug("Found recommended video: %s", video_info.get("title"))
                        
                        # videoRenderer도 체크 (혹시 모를 경우 대비)
                        elif "videoRenderer" in content:
                            video_info = self._extract_video_renderer_info(content["videoRenderer"])
                            if video_info:
                                videos.append(video_info)
                                _LOGGER.debug("Found recommended video (videoRenderer): %s", video_info.get("title"))
                        
                        # 3개 찾으면 종료
                        if len(videos) >= 3:
                            break
                    
                    # 탭을 찾았으면 루프 종료
                    break

            if videos:
                _LOGGER.info("Successfully fetched %d recommended videos", len(videos))
                return videos
            else:
                _LOGGER.warning("No recommended videos found")
                return None

        except (AttributeError, json.JSONDecodeError, KeyError) as err:
            _LOGGER.error("Can't parse recommended videos JSON: %s", err)
            _LOGGER.debug("Error details:", exc_info=True)
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
            
            # Extract duration - 개선된 로직
            duration = "N/A"
            is_live = False
            
            # 방법 1: contentImage > thumbnailViewModel > overlays에서 찾기
            thumbnail = lockup.get("contentImage", {}).get("thumbnailViewModel", {})
            overlays = thumbnail.get("overlays", [])
            
            for overlay in overlays:
                # thumbnailOverlayBadgeViewModel 체크 (라이브 및 duration)
                if "thumbnailOverlayBadgeViewModel" in overlay:
                    badge_vm = overlay["thumbnailOverlayBadgeViewModel"]
                    badges = badge_vm.get("thumbnailBadges", [])
                    for badge in badges:
                        if "thumbnailBadgeViewModel" in badge:
                            badge_data = badge["thumbnailBadgeViewModel"]
                            badge_text = badge_data.get("text", "")
                            badge_style = badge_data.get("badgeStyle", "")
                            
                            # 라이브 영상 체크
                            if badge_style == "THUMBNAIL_OVERLAY_BADGE_STYLE_LIVE" or badge_text in ["라이브", "LIVE"]:
                                is_live = True
                                duration = "LIVE"
                                _LOGGER.debug("Found LIVE stream badge")
                                break
                            # 일반 duration
                            elif badge_text and re.match(r'^\d{1,2}:\d{2}', badge_text):
                                duration = badge_text
                                _LOGGER.debug("Found duration in thumbnailBadgeViewModel: %s", duration)
                                break
                    if duration != "N/A":
                        break
                
                # thumbnailOverlayTimeStatusRenderer 체크 (새로운 형식)
                elif "thumbnailOverlayTimeStatusRenderer" in overlay:
                    time_status = overlay["thumbnailOverlayTimeStatusRenderer"]
                    text_obj = time_status.get("text", {})
                    if "simpleText" in text_obj:
                        duration = text_obj["simpleText"]
                        _LOGGER.debug("Found duration in thumbnailOverlayTimeStatusRenderer: %s", duration)
                        break
                    elif "accessibility" in text_obj:
                        duration = text_obj["accessibility"].get("accessibilityData", {}).get("label", "N/A")
                        _LOGGER.debug("Found duration in accessibility: %s", duration)
                        break
                
                # thumbnailBottomOverlayViewModel 체크 (기존 형식)
                elif "thumbnailBottomOverlayViewModel" in overlay:
                    badges = overlay["thumbnailBottomOverlayViewModel"].get("badges", [])
                    for badge in badges:
                        if "thumbnailBadgeViewModel" in badge:
                            duration = badge["thumbnailBadgeViewModel"].get("text", "N/A")
                            _LOGGER.debug("Found duration in thumbnailBadgeViewModel: %s", duration)
                            break
                    if duration != "N/A":
                        break
            
            # 방법 2: metadata에서 duration 찾기 (추가 시도)
            if duration == "N/A":
                for row in metadata_rows:
                    parts = row.get("metadataParts", [])
                    for part in parts:
                        text = part.get("text", {}).get("content", "")
                        # duration 형식 체크 (예: "10:23", "1:05:30")
                        if re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', text):
                            duration = text
                            _LOGGER.debug("Found duration in metadata: %s", duration)
                            break
                    if duration != "N/A":
                        break
            
            # 디버깅: duration을 못 찾은 경우 전체 lockup 구조 로깅
            if duration == "N/A":
                _LOGGER.warning("Could not find duration for video: %s", title)
                _LOGGER.debug("Lockup structure: %s", json.dumps(lockup, indent=2, ensure_ascii=False))
            
            output = {
                "channel": channel,
                "title": title,
                "video_id": video_id,
                "duration": duration,
                "thumbnail": self._get_best_thumbnail(video_id),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }

            _LOGGER.info("Extracted: %s by %s (duration: %s)", title, channel, duration)
            return output
            
        except Exception as err:
            _LOGGER.error("Failed to extract lockupViewModel: %s", err)
            _LOGGER.debug("Error details:", exc_info=True)
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