"""
Client Service Main Entry Point
Manages scheduling and orchestrates screenshot capture, processing, and sending.
"""

import atexit
import ctypes
import logging
import signal
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
    SKIP_WINDOW_TITLES,
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
# Shutdown Tracking
# =============================================================================

# Track the reason for shutdown
_shutdown_reason: str = "unknown"

# =============================================================================
# Module Instances
# =============================================================================

screenshot_capture = ScreenshotCapture()
ocr_processor = OCRProcessor()
api_client = APIClient()

# =============================================================================
# Core Functions
# =============================================================================

def get_foreground_window_info() -> tuple[str | None, str | None, bool]:
    """
    Get the process name, title, and visibility state of the current foreground window.
    
    Uses Windows API to determine which window is currently active
    and retrieves its associated process name, window title, and whether it's visible.
    
    Returns:
        Tuple of (process_name, window_title, is_visible), or (None, None, False) if unavailable
    """
    if sys.platform != 'win32':
        logger.debug("Foreground window detection only supported on Windows")
        return None, None, False
    
    try:
        user32 = ctypes.windll.user32
        
        # Get the foreground window handle
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            logger.debug("No foreground window found")
            return None, None, False
        
        # Check if window is minimized (IsIconic returns non-zero if minimized)
        is_minimized = user32.IsIconic(hwnd) != 0
        
        # Check if window is visible
        is_window_visible = user32.IsWindowVisible(hwnd) != 0
        
        # Window is considered "visible in foreground" only if not minimized and visible
        is_visible = is_window_visible and not is_minimized
        
        if is_minimized:
            logger.debug("Foreground window is minimized")
        
        # Get window title
        title_length = user32.GetWindowTextLengthW(hwnd) + 1
        title_buffer = ctypes.create_unicode_buffer(title_length)
        user32.GetWindowTextW(hwnd, title_buffer, title_length)
        window_title = title_buffer.value
        
        # Get process ID from window handle
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        
        if not pid.value:
            logger.debug("Could not get process ID for foreground window")
            return None, window_title, is_visible
        
        # Get process name from PID
        try:
            process = psutil.Process(pid.value)
            process_name = process.name()
            return process_name, window_title, is_visible
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            logger.debug(f"Could not get process name for PID {pid.value}")
            return None, window_title, is_visible
            
    except Exception as e:
        logger.error(f"Error getting foreground window info: {e}")
        return None, None, False


def is_browser_in_foreground() -> tuple[bool, str | None]:
    """
    Check if the current foreground window is a browser and is visible (not minimized).
    
    Returns:
        Tuple of (is_browser, window_title)
        - is_browser: True if a browser is visible in the foreground (not minimized)
        - window_title: The title of the foreground window (or None)
    """
    process_name, window_title, is_visible = get_foreground_window_info()
    
    if not process_name:
        logger.debug("Could not determine foreground process")
        return False, window_title
    
    # Check if the window is actually visible (not minimized)
    if not is_visible:
        logger.debug(f"Foreground window is minimized or not visible: {process_name}")
        return False, window_title
    
    # Check if the process is a known browser
    browser_names = {name.lower() for name in BROWSER_PROCESSES}
    is_browser = process_name.lower() in browser_names
    
    if is_browser:
        logger.debug(f"Browser visible in foreground: {process_name} - '{window_title}'")
    else:
        logger.debug(f"Non-browser in foreground: {process_name}")
    
    return is_browser, window_title


def should_skip_window_title(window_title: str | None) -> bool:
    """
    Check if the window title matches any skip patterns.
    
    Args:
        window_title: The title of the window to check
        
    Returns:
        True if the capture should be skipped, False otherwise
    """
    if not window_title:
        return False
    
    title_lower = window_title.lower()
    
    for skip_pattern in SKIP_WINDOW_TITLES:
        if skip_pattern.lower() in title_lower:
            logger.info(f"Skipping capture: window title contains '{skip_pattern}'")
            return True
    
    return False


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
    
    # Step 1: Check if browser is in the foreground (not minimized)
    is_browser, window_title = is_browser_in_foreground()
    
    if not is_browser:
        logger.info("No browser in foreground, skipping capture")
        return
    
    logger.info(f"Browser detected in foreground with title: '{window_title}'")
    
    # Step 2: Check if window title should be skipped (Gmail, Bank, etc.)
    if should_skip_window_title(window_title):
        logger.info(f"Window title matched skip pattern, skipping capture: '{window_title}'")
        return
    
    # Step 3: Capture screenshots
    logger.info("Browser is active and title is allowed - proceeding with capture")
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


# =============================================================================
# Signal and Shutdown Handlers
# =============================================================================

def _set_shutdown_reason(reason: str) -> None:
    """Set the shutdown reason for logging."""
    global _shutdown_reason
    _shutdown_reason = reason


def _log_shutdown() -> None:
    """Log shutdown message with the appropriate reason."""
    global _shutdown_reason
    if _shutdown_reason == "system_shutdown":
        logger.info("Service shutting down due to system shutdown")
    elif _shutdown_reason == "system_logoff":
        logger.info("Service shutting down due to user logoff")
    elif _shutdown_reason == "ctrl_c":
        logger.info("Service stopped via Ctrl+C (keyboard interrupt)")
    elif _shutdown_reason == "ctrl_break":
        logger.info("Service stopped via Ctrl+Break")
    elif _shutdown_reason == "console_close":
        logger.info("Service stopped via console window close")
    elif _shutdown_reason == "signal_term":
        logger.info("Service stopped via SIGTERM signal (CMD/task kill)")
    elif _shutdown_reason == "signal_int":
        logger.info("Service stopped via SIGINT signal")
    elif _shutdown_reason == "task_manager":
        logger.info("Service stopped via Windows Task Manager or taskkill")
    else:
        logger.info(f"Service stopped (reason: {_shutdown_reason})")
    logger.info("Privacy Monitor Client Service terminated")


def _signal_handler(signum: int, frame) -> None:
    """Handle Unix-style signals (SIGTERM, SIGINT, etc.)."""
    signal_names = {
        signal.SIGTERM: "signal_term",
        signal.SIGINT: "signal_int",
    }
    # On Windows, SIGBREAK is available
    if hasattr(signal, 'SIGBREAK'):
        signal_names[signal.SIGBREAK] = "ctrl_break"
    
    reason = signal_names.get(signum, f"signal_{signum}")
    _set_shutdown_reason(reason)
    logger.info(f"Received signal {signum}, initiating shutdown...")
    sys.exit(0)


def _setup_signal_handlers() -> None:
    """Set up signal handlers for graceful shutdown."""
    # Standard signals
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    
    # Windows-specific SIGBREAK (Ctrl+Break)
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, _signal_handler)


def _windows_console_ctrl_handler(ctrl_type: int) -> bool:
    """
    Handle Windows console control events.
    
    Args:
        ctrl_type: The type of control event:
            0 = CTRL_C_EVENT
            1 = CTRL_BREAK_EVENT
            2 = CTRL_CLOSE_EVENT
            5 = CTRL_LOGOFF_EVENT
            6 = CTRL_SHUTDOWN_EVENT
    
    Returns:
        True to indicate the event was handled
    """
    ctrl_type_names = {
        0: "ctrl_c",
        1: "ctrl_break",
        2: "console_close",
        5: "system_logoff",
        6: "system_shutdown",
    }
    
    reason = ctrl_type_names.get(ctrl_type, f"windows_ctrl_{ctrl_type}")
    _set_shutdown_reason(reason)
    
    # Log immediately for shutdown/logoff events as we may not get atexit
    if ctrl_type in (5, 6):  # LOGOFF or SHUTDOWN
        _log_shutdown()
    
    return True  # Indicate we handled the event


def _setup_windows_console_handler() -> None:
    """Set up Windows console control handler for shutdown events."""
    if sys.platform != 'win32':
        return
    
    try:
        # Define the handler function type
        HANDLER_ROUTINE = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong)
        
        # Create a handler that won't be garbage collected
        handler = HANDLER_ROUTINE(_windows_console_ctrl_handler)
        
        # Store reference to prevent garbage collection
        _setup_windows_console_handler._handler = handler
        
        # Register the handler
        kernel32 = ctypes.windll.kernel32
        if not kernel32.SetConsoleCtrlHandler(handler, True):
            logger.warning("Failed to set Windows console control handler")
        else:
            logger.debug("Windows console control handler registered")
            
    except Exception as e:
        logger.warning(f"Could not set up Windows console handler: {e}")


def main() -> None:
    """
    Application entry point.
    
    Sets up the scheduler and starts the capture loop.
    """
    global _shutdown_reason
    
    # Register shutdown logging via atexit
    atexit.register(_log_shutdown)
    
    # Set up signal handlers
    _setup_signal_handlers()
    
    # Set up Windows-specific console handler
    _setup_windows_console_handler()
    
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
        logger.info("Starting scheduler (press Ctrl+C to stop)...)")
        scheduler.start()
    except KeyboardInterrupt:
        _set_shutdown_reason("ctrl_c")
        logger.info("Received keyboard interrupt")
        scheduler.shutdown(wait=False)
    except SystemExit:
        # Normal exit via signal handler
        scheduler.shutdown(wait=False)
    except Exception as e:
        _set_shutdown_reason(f"error: {e}")
        logger.error(f"Scheduler error: {e}")
        scheduler.shutdown(wait=False)
        raise


if __name__ == "__main__":
    main()
