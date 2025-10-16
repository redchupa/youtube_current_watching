# Contributing to YouTube Current Watching

Thank you for considering contributing to this project! 

##  Reporting Bugs

When reporting bugs, please include:

1. **Home Assistant Version**
   ```
   Settings → About → Home Assistant Core
   ```

2. **Integration Version**
   ```
   HACS → YouTube Current Watching → Version
   ```

3. **Error Logs**
   - Enable debug logging (see below)
   - Copy relevant error messages
   - Settings → System → Logs → Search "youtube_current_watching"

4. **Steps to Reproduce**
   - What were you doing when the error occurred?
   - Can you reproduce it consistently?

5. **Media Player Information**
   - Type: Apple TV / Android TV / etc.
   - Model and version
   - Developer Tools → States → Your media_player entity

### Enable Debug Logging

Add to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.youtube_current_watching: debug
```

Restart Home Assistant after adding this configuration.

### Enable HTML Debug (Advanced)

If you're experiencing issues with video detection:

1. Open `custom_components/youtube_current_watching/coordinator.py`
2. Find the commented debug code (around line 95):
   ```python
   # Debug: Uncomment below to save HTML for analysis
   ```
3. Remove the `#` comments to activate
4. Play a YouTube video
5. Check `/config/youtube_history_debug.html`
6. This file helps analyze YouTube page structure changes

** Important**: Do NOT share `youtube_history_debug.html` publicly as it may contain personal information!

---

##  Suggesting Features

Feature suggestions are welcome! Please include:

1. **Use Case**: What problem does this feature solve?
2. **Description**: How should it work?
3. **Examples**: Are there similar features in other integrations?

---

## 🔧 Code Contributions

### Development Setup

1. **Fork the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/youtube_current_watching.git
   cd youtube_current_watching
   ```

2. **Install in development mode**
   ```bash
   # Link to your Home Assistant custom_components
   ln -s $(pwd) /config/custom_components/youtube_current_watching
   ```

3. **Enable debug mode**
   - Add debug logging to `configuration.yaml`
   - Uncomment debug code in `coordinator.py` if needed

### Code Style

- Follow PEP 8 guidelines
- Use type hints for function parameters and return values
- Add docstrings to all functions and classes
- Keep functions focused and concise
- Use meaningful variable names

### Example Code Style

```python
def _extract_video_info(self, video_data: dict) -> dict[str, Any] | None:
    """Extract information from video data.
    
    Args:
        video_data: Video data dictionary from YouTube API
        
    Returns:
        Dictionary containing video information or None if extraction fails
    """
    try:
        video_id = video_data.get("videoId")
        if not video_id:
            return None
        
        # Extract title
        title = self._extract_title(video_data)
        
        return {
            "video_id": video_id,
            "title": title,
        }
    except Exception as err:
        _LOGGER.error("Failed to extract video info: %s", err)
        return None
```

### Testing

Before submitting a pull request:

1. **Test basic functionality**
   - Install integration
   - Configure with your cookies
   - Play YouTube videos
   - Verify sensor updates correctly

2. **Test error cases**
   - Invalid cookies path
   - Expired cookies
   - No media player available
   - YouTube page structure changes

3. **Check logs**
   - No unexpected errors
   - Debug messages are informative
   - No sensitive information logged

### Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write clean, documented code
   - Follow existing code style
   - Update README if needed

3. **Test thoroughly**
   - Verify on your Home Assistant instance
   - Check for any breaking changes

4. **Commit with clear messages**
   ```bash
   git commit -m "feat: Add support for YouTube Music detection"
   ```

5. **Push and create PR**
   ```bash
   git push origin feature/your-feature-name
   ```
   - Create pull request on GitHub
   - Describe what changed and why
   - Link any related issues

### Commit Message Format

Follow conventional commits:

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation only
- `style:` Code style changes (formatting, etc.)
- `refactor:` Code restructuring
- `test:` Adding tests
- `chore:` Maintenance tasks

Examples:
```
feat: Add support for YouTube Shorts detection
fix: Handle expired cookies gracefully
docs: Update installation instructions
refactor: Simplify video extraction logic
```

---

##  Understanding the Code

### Key Files

- **`__init__.py`**: Integration setup and media player state monitoring
- **`coordinator.py`**: Data fetching and YouTube API interaction
- **`sensor.py`**: Sensor entities (watching, subscriptions)
- **`binary_sensor.py`**: Cookie status sensor
- **`config_flow.py`**: Configuration UI flow
- **`const.py`**: Constants and configuration keys

### How It Works

1. **Detection**: Monitors media player for YouTube app playback
2. **Fetching**: Uses cookies to access YouTube watch history page
3. **Parsing**: Extracts `ytInitialData` JSON from HTML
4. **Extraction**: Finds video information from multiple possible paths
5. **Update**: Updates sensor with latest video information

### YouTube Page Structure

YouTube uses different JSON structures:

- **lockupViewModel**: New format (2024+)
- **videoRenderer**: Old format (pre-2024)
- **shortsLockupViewModel**: YouTube Shorts

The integration tries all formats to maximize compatibility.

---

##  Documentation

When contributing documentation:

- Keep language simple and clear
- Include examples where helpful
- Update both Korean and English versions
- Test all code examples

---

##  Questions?

- **General Questions**: Create a discussion
- **Bug Reports**: Create an issue
- **Feature Requests**: Create an issue with "enhancement" label

---

Thank you for contributing! 