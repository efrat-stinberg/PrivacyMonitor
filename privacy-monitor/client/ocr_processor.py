"""
OCR Processor Module
Handles OCR text extraction, sensitive content detection, and image blurring.
"""

import io
import logging
from typing import TypedDict

import cv2
import numpy as np
import pytesseract
from PIL import Image

from config import JPEG_QUALITY, SENSITIVE_KEYWORDS, TESSERACT_PATH

logger = logging.getLogger(__name__)

# Configure Tesseract path
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


class ProcessedImageMetadata(TypedDict):
    """Type definition for processed image metadata."""
    has_sensitive: bool
    sensitive_keywords: list[str]
    was_blurred: bool
    original_size: tuple[int, int]


class OCRProcessor:
    """
    Handles image pre-processing before sending to server.
    
    Performs OCR, detects sensitive content, blurs if necessary,
    and compresses the image.
    """

    def extract_text(self, image: Image.Image) -> str:
        """
        Extract text from image using Tesseract OCR.
        
        Args:
            image: PIL Image to process
            
        Returns:
            Detected text string, empty string if OCR fails
        """
        try:
            # Configure Tesseract for Hebrew + English
            # PSM 6: Assume a single uniform block of text
            custom_config = r"--psm 6"
            
            text = pytesseract.image_to_string(
                image,
                lang="heb+eng",
                config=custom_config
            )
            
            logger.debug(f"OCR extracted {len(text)} characters")
            return text
            
        except pytesseract.TesseractNotFoundError:
            logger.error(
                f"Tesseract not found at {TESSERACT_PATH}. "
                "Please install Tesseract OCR."
            )
            return ""
            
        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return ""

    def detect_sensitive_content(self, text: str) -> list[str]:
        """
        Detect sensitive keywords in text.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of sensitive keywords found in the text
        """
        if not text:
            return []
            
        # Convert text to lowercase for case-insensitive matching
        text_lower = text.lower()
        
        found_keywords: list[str] = []
        
        for keyword in SENSITIVE_KEYWORDS:
            if keyword.lower() in text_lower:
                found_keywords.append(keyword)
                
        if found_keywords:
            logger.info(f"Detected sensitive keywords: {found_keywords}")
            
        return found_keywords

    def blur_image(
        self,
        image: Image.Image,
        blur_strength: int = 99
    ) -> Image.Image:
        """
        Apply Gaussian blur to the entire image.
        
        Args:
            image: PIL Image to blur
            blur_strength: Kernel size for Gaussian blur (must be odd number)
            
        Returns:
            Blurred PIL Image
        """
        # Ensure blur_strength is odd
        if blur_strength % 2 == 0:
            blur_strength += 1
            
        # Convert PIL Image to numpy array
        img_array = np.array(image)
        
        # Convert RGB to BGR (OpenCV format)
        if len(img_array.shape) == 3 and img_array.shape[2] == 3:
            img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        else:
            img_bgr = img_array
            
        # Apply Gaussian Blur
        blurred = cv2.GaussianBlur(
            img_bgr,
            (blur_strength, blur_strength),
            sigmaX=30,
            sigmaY=30
        )
        
        # Convert back to RGB
        if len(blurred.shape) == 3 and blurred.shape[2] == 3:
            blurred_rgb = cv2.cvtColor(blurred, cv2.COLOR_BGR2RGB)
        else:
            blurred_rgb = blurred
            
        # Convert back to PIL Image
        return Image.fromarray(blurred_rgb)

    def compress_image(
        self,
        image: Image.Image,
        quality: int = JPEG_QUALITY
    ) -> bytes:
        """
        Compress image to JPEG format.
        
        Args:
            image: PIL Image to compress
            quality: JPEG quality (0-100)
            
        Returns:
            Compressed image as bytes
        """
        buffer = io.BytesIO()
        
        # Ensure image is in RGB mode
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGB")
            
        image.save(
            buffer,
            format="JPEG",
            quality=quality,
            optimize=True
        )
        
        return buffer.getvalue()

    def process_image(
        self,
        image: Image.Image
    ) -> tuple[bytes, ProcessedImageMetadata]:
        """
        Main processing pipeline for an image.
        
        Performs:
        1. OCR text extraction
        2. Sensitive content detection
        3. Conditional blurring (if sensitive content found)
        4. Compression
        
        Args:
            image: PIL Image to process
            
        Returns:
            Tuple of (compressed_image_bytes, metadata_dict)
        """
        original_size = image.size
        
        # Step 1: OCR - Extract text
        extracted_text = self.extract_text(image)
        
        # Step 2: Detection - Check for sensitive content
        sensitive_keywords = self.detect_sensitive_content(extracted_text)
        has_sensitive = len(sensitive_keywords) > 0
        
        # Step 3: Conditional Blur
        was_blurred = False
        processed_image = image
        
        if has_sensitive:
            logger.info("Sensitive content detected, applying blur")
            processed_image = self.blur_image(image)
            was_blurred = True
            
        # Step 4: Compression
        image_bytes = self.compress_image(processed_image)
        
        # Build metadata
        metadata: ProcessedImageMetadata = {
            "has_sensitive": has_sensitive,
            "sensitive_keywords": sensitive_keywords,
            "was_blurred": was_blurred,
            "original_size": original_size,
        }
        
        logger.debug(
            f"Processed image: size={original_size}, "
            f"has_sensitive={has_sensitive}, "
            f"was_blurred={was_blurred}, "
            f"output_size={len(image_bytes)} bytes"
        )
        
        return image_bytes, metadata
