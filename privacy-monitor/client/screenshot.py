"""
Screenshot Capture Module
Handles physical screenshot capture of alxxxxxxxcted monitors.
"""

import io
import logging
from typing import TypedDict

import mss
import mss.tools
from PIL import Image

from config import JPEG_QUALITY

logger = logging.getLogger(__name__)


class ScreenshotInfo(TypedDict):
    """Type definition for screenshot information."""
    image: Image.Image
    monitor_number: int
    width: int
    height: int
    left: int
    top: int


class ScreenshotCapture:
    """
    Handles screenshot capture for all connected monitors.
    
    Uses mss library for fast, cross-platform screenshot capture.
    """

    def capture_all_screens(self) -> list[ScreenshotInfo]:
        """
        Capture screenshots of all connected physical monitors.
        
        Returns:
            List of dictionaries containing image data and monitor information.
            Each dict contains: image (PIL.Image), monitor_number, width, height, left, top
        """
        screenshots: list[ScreenshotInfo] = []
        
        try:
            with mss.mss() as sct:
                # sct.monitors[0] is the "all monitors" virtual screen
                # sct.monitors[1:] are the individual physical monitors
                physical_monitors = sct.monitors[1:]
                
                logger.debug(f"Detected {len(physical_monitors)} physical monitor(s)")
                
                for monitor_number, monitor in enumerate(physical_monitors, start=1):
                    try:
                        # Capture the monitor
                        screenshot = sct.grab(monitor)
                        
                        # Convert to PIL Image
                        # mss returns BGRA, we need to convert to RGB
                        image = Image.frombytes(
                            "RGB",
                            screenshot.size,
                            screenshot.bgra,
                            "raw",
                            "BGRX"
                        )
                        
                        screenshot_info: ScreenshotInfo = {
                            "image": image,
                            "monitor_number": monitor_number,
                            "width": monitor["width"],
                            "height": monitor["height"],
                            "left": monitor["left"],
                            "top": monitor["top"],
                        }
                        
                        screenshots.append(screenshot_info)
                        logger.debug(
                            f"Captured monitor {monitor_number}: "
                            f"{monitor['width']}x{monitor['height']} "
                            f"at ({monitor['left']}, {monitor['top']})"
                        )
                        
                    except Exception as e:
                        # Handle error for individual monitor, continue to next
                        logger.error(
                            f"Failed to capture monitor {monitor_number}: {e}"
                        )
                        continue
                        
        except Exception as e:
            logger.error(f"Failed to initialize screen capture: {e}")
            
        return screenshots

    @staticmethod
    def image_to_bytes(image: Image.Image, quality: int = JPEG_QUALITY) -> bytes:
        """
        Convert PIL Image to JPEG bytes.
        
        Args:
            image: PIL Image object to convert
            quality: JPEG compression quality (0-100)
            
        Returns:
            Image data as bytes in JPEG format
        """
        buffer = io.BytesIO()
        
        # Ensure image is in RGB mode (JPEG doesn't support alpha channel)
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGB")
            
        image.save(
            buffer,
            format="JPEG",
            quality=quality,
            optimize=True
        )
        
        return buffer.getvalue()
