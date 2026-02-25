"""
API Client Module
Handles HTTP communication with the server, including retry logic.
"""

import json
import logging
import time
from typing import Any

import requests
from requests.exceptions import Timeout, ConnectionError

from config import (
    API_BASE_URL,
    API_KEY,
    MAX_RETRIES,
    REQUEST_TIMEOUT_SECONDS,
    RETRY_BACKOFF_FACTOR,
    USER_ID,
)

logger = logging.getLogger(__name__)


class APIClient:
    """
    HTTP client for communication with the screenshot server.
    
    Implements retry logic with exponential backoff for resilient
    network communication.
    """

    def __init__(self):
        """Initialize the API client."""
        self.base_url = API_BASE_URL.rstrip("/")
        self.timeout = REQUEST_TIMEOUT_SECONDS
        
    def _get_headers(self) -> dict[str, str]:
        """
        Get HTTP headers for API requests.
        
        Returns:
            Dictionary with authentication headers
        """
        return {
            "X-API-Key": API_KEY,
            "X-User-Id": USER_ID,
        }

    def send_screenshot(
        self,
        image_bytes: bytes,
        metadata: dict[str, Any],
        monitor_number: int
    ) -> bool:
        """
        Send a screenshot to the server with retry logic.
        
        Args:
            image_bytes: Processed image in JPEG format
            metadata: Additional information about the image
            monitor_number: Monitor number (1, 2, 3, ...)
            
        Returns:
            True if successful, False otherwise
        """
        url = f"{self.base_url}/api/v1/screenshot"
        
        # Prepare the file for upload
        filename = f"screenshot_monitor_{monitor_number}.jpg"
        files = {
            "file": (filename, image_bytes, "image/jpeg")
        }
        
        # Prepare form data
        data = {
            "monitor_number": str(monitor_number),
            "metadata": json.dumps(metadata),
        }
        
        # Get headers (without Content-Type, requests will set it for multipart)
        headers = self._get_headers()
        
        # Retry loop with exponential backoff
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.debug(
                    f"Attempt {attempt}/{MAX_RETRIES}: "
                    f"Sending screenshot for monitor {monitor_number}"
                )
                
                response = requests.post(
                    url,
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    logger.info(
                        f"Successfully sent screenshot for monitor {monitor_number}"
                    )
                    return True
                    
                elif response.status_code == 401:
                    # Authorization error - no point retrying
                    logger.error(
                        f"Authorization error (401): Invalid API key or User ID. "
                        "Please check your .env configuration."
                    )
                    return False
                    
                elif response.status_code == 403:
                    # Forbidden - no point retrying
                    logger.error(
                        f"Forbidden (403): Access denied. "
                        "Please check your permissions."
                    )
                    return False
                    
                else:
                    logger.warning(
                        f"Attempt {attempt}/{MAX_RETRIES}: "
                        f"Server returned status {response.status_code}: "
                        f"{response.text[:200]}"
                    )
                    
            except Timeout:
                logger.warning(
                    f"Attempt {attempt}/{MAX_RETRIES}: "
                    f"Request timed out after {self.timeout} seconds"
                )
                
            except ConnectionError:
                logger.warning(
                    f"Attempt {attempt}/{MAX_RETRIES}: "
                    f"Connection error - server may be unavailable"
                )
                
            except Exception as e:
                logger.error(
                    f"Attempt {attempt}/{MAX_RETRIES}: "
                    f"Unexpected error: {type(e).__name__}: {e}"
                )
            
            # Calculate wait time with exponential backoff
            if attempt < MAX_RETRIES:
                wait_time = RETRY_BACKOFF_FACTOR ** attempt
                logger.debug(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
                
                # Reset files for retry (BytesIO position)
                files = {
                    "file": (filename, image_bytes, "image/jpeg")
                }
        
        # All attempts failed
        logger.error(
            f"Failed to send screenshot for monitor {monitor_number} "
            f"after {MAX_RETRIES} attempts"
        )
        return False

    def health_check(self) -> bool:
        """
        Check if the server is available.
        
        Returns:
            True if server responds, False otherwise
        """
        url = f"{self.base_url}/health"
        
        try:
            response = requests.get(url, timeout=5)
            return response.status_code == 200
        except Exception:
            return False
