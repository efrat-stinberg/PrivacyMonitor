"""
Client Service Main Entry Point
Manages scheduling and orchestrates screenshot capture, processing, and sending.
"""

import logging
import sys
from datetime import datetime

import psutil
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from api_client import APIClient
from config import (
    BROWSER_PROCESSES,
    LOG_FILE,
    LOG_FORMAT,
    LOG_LEVEL,
    SCREENSHOT_INTERVAL_MINUTES,
)
from ocr_processor import OCRProcessor
from screenshot import ScreenshotCapture

# =============================================================================
# Logging Configuration
# =============================================================================

def setup_logging() -> logging.Logger:
    """
    Configure logging for the application.
    
    Sets up both file and console handlers with appropriate formatting.
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(LOG_FORMAT)
    
    # File handler - save to log file
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console handler - display in stdout
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger


# Initialize logging
logger = setup_logging()

# =============================================================================
# Module Instances
# =============================================================================

screenshot_capture = ScreenshotCapture()
ocr_processor = OCRProcessor()
api_client = APIClient()

# =============================================================================
# Core Functions
# =============================================================================

def is_browser_active() -> bool:
    """
    Check if any browser process is currently running.
    
    Scans all running processes and compares against the list of
    known browser process names.
    
    Returns:
        True if a browser is active, False otherwise
    """
    try:
        # Convert browser processes to lowercase set for faster lookup
        browser_names = {name.lower() for name in BROWSER_PROCESSES}
        
        for process in psutil.process_iter(["name"]):
            try:
                process_name = process.info["name"]
                if process_name and process_name.lower() in browser_names:
                    logger.debug(f"Active browser detected: {process_name}")
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                # Process may have terminated or we don't have access
                continue
                
        return False
        
    except Exception as e:
        logger.error(f"Error checking for active browsers: {e}")
        return False


def capture_and_send() -> None:
    """
    Main function executed by the scheduler.
    
    Captures screenshots from all monitors, processes them (OCR, blur if needed),
    and sends them to the server.
    """
    timestamp = datetime.now().isoformat()
    logger.info(f"Starting capture process at {timestamp}")
    
    # Step 1: Check if browser is active
    if not is_browser_active():
        logger.info("No active browser detected, skipping capture")
        return
    
    # Step 2: Capture screenshots
    screenshots = screenshot_capture.capture_all_screens()
    
    if not screenshots:
        logger.warning("No screenshots captured")
        return
    
    logger.info(f"Captured {len(screenshots)} screenshot(s)")
    
    # Step 3: Process and send each screenshot
    success_count = 0
    fail_count = 0
    
    for screenshot_info in screenshots:
        monitor_number = screenshot_info["monitor_number"]
        
        try:
            # Process image (OCR, detect sensitive content, blur if needed, compress)
            image = screenshot_info["image"]
            image_bytes, metadata = ocr_processor.process_image(image)
            
            # Add additional metadata
            metadata["monitor_number"] = monitor_number
            metadata["width"] = screenshot_info["width"]
            metadata["height"] = screenshot_info["height"]
            metadata["timestamp"] = timestamp
            metadata["left"] = screenshot_info["left"]
            metadata["top"] = screenshot_info["top"]
            
            # Send to server
            success = api_client.send_screenshot(
                image_bytes=image_bytes,
                metadata=metadata,
                monitor_number=monitor_number
            )
            
            if success:
                success_count += 1
            else:
                fail_count += 1
                
        except Exception as e:
            logger.error(
                f"Error processing monitor {monitor_number}: "
                f"{type(e).__name__}: {e}"
            )
            fail_count += 1
            continue
    
    # Step 4: Log summary
    logger.info(
        f"Capture complete: {success_count} succeeded, {fail_count} failed "
        f"out of {len(screenshots)} monitors"
    )


def main() -> None:
    """
    Application entry point.
    
    Sets up the scheduler and starts the capture loop.
    """
    logger.info("=" * 60)
    logger.info("Privacy Monitor Client Service Starting")
    logger.info(f"Screenshot interval: {SCREENSHOT_INTERVAL_MINUTES} minutes")
    logger.info("=" * 60)
    
    # Create scheduler
    scheduler = BlockingScheduler()
    
    # Configure the capture job
    scheduler.add_job(
        func=capture_and_send,
        trigger=IntervalTrigger(minutes=SCREENSHOT_INTERVAL_MINUTES),
        id="screenshot_job",
        name="Capture and Send Screenshots",
        replace_existing=True,
    )
    
    logger.info("Scheduler configured successfully")
    
    # Run first capture immediately
    logger.info("Running initial capture...")
    capture_and_send()
    
    # Start the scheduler (blocking - runs forever)
    try:
        logger.info("Starting scheduler (press Ctrl+C to stop)...")
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        scheduler.shutdown(wait=False)
        logger.info("Client service stopped")
    except Exception as e:
        logger.error(f"Scheduler error: {e}")
        scheduler.shutdown(wait=False)
        raise


if __name__ == "__main__":
    main()
