"""
Screenshot Capture Module
Handles physical screenshot capture of all connected monitors.
"""

import io
import os
import logging
from typing import TypedDict, List

import mss
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

    def capture_all_screens(self, save_folder: str = ".") -> List[ScreenshotInfo]:
        """
        Capture screenshots of all connected physical monitors and save them immediately.
        
        Args:
            save_folder: folder to save screenshots (default is current folder)
        
        Returns:
            List of ScreenshotInfo dictionaries.
        """
        screenshots: List[ScreenshotInfo] = []
        os.makedirs(save_folder, exist_ok=True)

        try:
            with mss.mss() as sct:
                physical_monitors = sct.monitors[1:]
                logger.debug(f"Detected {len(physical_monitors)} physical monitor(s)")

                for monitor_number, monitor in enumerate(physical_monitors, start=1):
                    try:
                        screenshot = sct.grab(monitor)

                        image = Image.frombytes(
                            "RGB",
                            screenshot.size,
                            screenshot.bgra,
                            "raw",
                            "BGRX"
                        )

                        filename = os.path.join(save_folder, f"monitor_{monitor_number}.jpg")
                        image.save(filename, format="JPEG", quality=JPEG_QUALITY)
                        logger.info(f"Saved screenshot to {filename}")

                        screenshot_info: ScreenshotInfo = {
                            "image": image,
                            "monitor_number": monitor_number,
                            "width": monitor["width"],
                            "height": monitor["height"],
                            "left": monitor["left"],
                            "top": monitor["top"],
                        }

                        screenshots.append(screenshot_info)

                    except Exception as e:
                        logger.error(f"Failed to capture monitor {monitor_number}: {e}")
                        continue

        except Exception as e:
            logger.error(f"Failed to initialize screen capture: {e}")

        return screenshots


if __name__ == "__main__":
    sc = ScreenshotCapture()
    sc.capture_all_screens()  # capture and save immediately in current folder