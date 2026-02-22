"""
Client Service Configuration
Centralized management of all settings and constants.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# =============================================================================
# Server Settings
# =============================================================================
API_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8000")
API_KEY: str = os.getenv("API_KEY", "")
USER_ID: str = os.getenv("USER_ID", "")

# =============================================================================
# Screenshot Settings
# =============================================================================
SCREENSHOT_INTERVAL_MINUTES: int = int(os.getenv("SCREENSHOT_INTERVAL_MINUTES", "15"))
JPEG_QUALITY: int = int(os.getenv("JPEG_QUALITY", "70"))

# =============================================================================
# OCR Settings
# =============================================================================
# Default paths for Tesseract installation
_DEFAULT_TESSERACT_PATH_WINDOWS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
_DEFAULT_TESSERACT_PATH_UNIX = "/usr/bin/tesseract"

# Determine default path based on OS
_DEFAULT_TESSERACT_PATH = (
    _DEFAULT_TESSERACT_PATH_WINDOWS
    if os.name == "nt"
    else _DEFAULT_TESSERACT_PATH_UNIX
)

TESSERACT_PATH: str = os.getenv("TESSERACT_PATH", _DEFAULT_TESSERACT_PATH)

# =============================================================================
# Sensitive Keywords
# =============================================================================
SENSITIVE_KEYWORDS: list[str] = [
    "password",
    "סיסמה",
    "credit card",
    "כרטיס אשראי",
    "cvv",
    "ssn",
    "social security",
    "ביטוח לאומי",
    "secret",
    "סוד",
    "confidential",
    "חסוי",
    "pin code",
    "קוד סודי",
    "bank account",
    "חשבון בנק",
    "routing number",
    "private key",
    "מפתח פרטי",
    "api key",
    "token",
    "auth",
]

# =============================================================================
# Browser Detection
# =============================================================================
BROWSER_PROCESSES: list[str] = [
    # Windows
    "chrome.exe",
    "firefox.exe",
    "msedge.exe",
    "brave.exe",
    "opera.exe",
    "iexplore.exe",
    "vivaldi.exe",
    # Linux/Mac (process names without extension)
    "chrome",
    "firefox",
    "safari",
    "brave",
    "opera",
    "chromium",
    "chromium-browser",
    "google-chrome",
    "microsoft-edge",
]

# =============================================================================
# Retry Settings
# =============================================================================
MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
RETRY_BACKOFF_FACTOR: int = int(os.getenv("RETRY_BACKOFF_FACTOR", "2"))
REQUEST_TIMEOUT_SECONDS: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))

# =============================================================================
# Logging Settings
# =============================================================================
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: str = os.getenv("LOG_FILE", "client.log")
LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
