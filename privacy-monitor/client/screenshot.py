"""
Screenshot Capture Module
Handles physical screenshot capture of all connected monitors.
"""

import ctypes
import io
import os
import logging
import sys
from typing import TypedDict, List

import mss
from PIL import Image

from config import JPEG_QUALITY

logger = logging.getLogger(__name__)


def is_workstation_locked() -> bool:
    """
    Check if the Windows workstation is currently locked.
    
    Returns:
        True if the workstation is locked, False otherwise.
        On non-Windows systems, always returns False.
    """
    if sys.platform != 'win32':
        return False
    
    try:
        user32 = ctypes.windll.user32
        
        # Method 1: Check if input is blocked (screen is locked)
        # GetForegroundWindow returns 0 when desktop is not accessible
        foreground_window = user32.GetForegroundWindow()
        
        # Method 2: Check the desktop name
        # When locked, the desktop switches to "Winlogon"
        hdesk = user32.OpenInputDesktop(0, False, 0x0001)  # DESKTOP_READOBJECTS
        if hdesk == 0:
            # Cannot open input desktop - likely locked
            return True
        
        # Close the handle
        user32.CloseDesktop(hdesk)
        return False
        
    except Exception as e:
        logger.debug(f"Could not determine lock state: {e}")
        return False


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

        # Check if workstation is locked before attempting capture
        if is_workstation_locked():
            logger.warning(
                "Screenshot capture failed: Computer is locked. "
                "Screen capture is not possible while the workstation is locked."
            )
            return screenshots

        try:
            with mss.mss() as sct:
                physical_monitors = sct.monitors[1:]
                logger.debug(f"Detected {len(physical_monitors)} physical monitor(s)")

                for monitor_number, monitor in enumerate(physical_monitors, start=1):
                    try:
                        screenshot = sct.grab(monitor)

                        # Check if the screenshot is all black (another sign of locked screen)
                        if screenshot.raw and all(b == 0 for b in screenshot.raw[:1000]):
                            logger.warning(
                                f"Screenshot capture failed for monitor {monitor_number}: "
                                "Screen appears black (computer may be locked)"
                            )
                            continue

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
                        error_msg = str(e).lower()
                        # Check for common lock-related error messages
                        if any(phrase in error_msg for phrase in [
                            "access denied", "locked", "not available",
                            "no desktop", "interactive", "session"
                        ]):
                            logger.warning(
                                f"Screenshot capture failed for monitor {monitor_number}: "
                                f"Computer appears to be locked. Error: {e}"
                            )
                        else:
                            logger.error(f"Failed to capture monitor {monitor_number}: {e}")
                        continue

        except Exception as e:
            error_msg = str(e).lower()
            # Check for lock-related errors at the initialization level
            if any(phrase in error_msg for phrase in [
                "access denied", "locked", "not available",
                "no desktop", "interactive", "session"
            ]):
                logger.warning(
                    "Screenshot capture failed: Computer is locked or screen is not accessible. "
                    f"Error: {e}"
                )
            else:
                logger.error(f"Failed to initialize screen capture: {e}")

        return screenshots


if __name__ == "__main__":
    sc = ScreenshotCapture()
    sc.capture_all_screens()  # capture and save immediately in current folder