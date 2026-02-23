"""
OCR Processor Module
Handles OCR text extraction, sensitive content detection, and image blurring.
Supports asynchronous OCR processing for scheduler.
"""

import io
import os
import logging
from datetime import datetime
from typing import TypedDict
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
from PIL import Image
import easyocr

from config import JPEG_QUALITY, SENSITIVE_KEYWORDS

logger = logging.getLogger(__name__)

# Initialize EasyOCR reader once (heavy operation)
reader = easyocr.Reader(['en', 'he'])

# Thread pool for asynchronous OCR
ocr_executor = ThreadPoolExecutor(max_workers=2)  # adjust workers as needed


class ProcessedImageMetadata(TypedDict):
    """Type definition for processed image metadata."""
    has_sensitive: bool
    sensitive_keywords: list[str]
    was_blurred: bool
    original_size: tuple[int, int]


class OCRProcessor:
    """
    Handles image pre-processing before sending to server.
    
    Performs OCR asynchronously, detects sensitive content, blurs if necessary,
    compresses the image, and automatically saves extracted text.
    """

    def extract_text(self, image: Image.Image) -> str:
        """
        Extract text from image using EasyOCR (synchronous).
        """
        try:
            img_array = np.array(image)
            if len(img_array.shape) == 2:  # grayscale
                img_array = cv2.cvtColor(img_array, cv2.COLOR_GRAY2RGB)
            elif img_array.shape[2] == 4:  # RGBA
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2RGB)

            results = reader.readtext(img_array)
            extracted_text = " ".join([text for (_, text, _) in results])
            logger.debug(f"OCR extracted {len(extracted_text)} characters")
            return extracted_text

        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return ""

    def extract_text_async(self, image: Image.Image):
        """
        Submit OCR job to thread pool for asynchronous execution.
        Returns a Future object.
        """
        return ocr_executor.submit(self.extract_text, image)

    def detect_sensitive_content(self, text: str) -> list[str]:
        if not text:
            return []

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
        if blur_strength % 2 == 0:
            blur_strength += 1

        img_array = np.array(image)

        if len(img_array.shape) == 3 and img_array.shape[2] == 3:
            img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        else:
            img_bgr = img_array

        blurred = cv2.GaussianBlur(
            img_bgr,
            (blur_strength, blur_strength),
            sigmaX=30,
            sigmaY=30
        )

        if len(blurred.shape) == 3 and blurred.shape[2] == 3:
            blurred_rgb = cv2.cvtColor(blurred, cv2.COLOR_BGR2RGB)
        else:
            blurred_rgb = blurred

        return Image.fromarray(blurred_rgb)

    def compress_image(
        self,
        image: Image.Image,
        quality: int = JPEG_QUALITY
    ) -> bytes:
        buffer = io.BytesIO()
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGB")

        image.save(buffer, format="JPEG", quality=quality, optimize=True)
        return buffer.getvalue()

    def process_image(
        self,
        image: Image.Image,
        image_name: str | None = None  # optional: used for naming OCR file
    ) -> tuple[bytes, ProcessedImageMetadata]:
        original_size = image.size

        # Step 1: OCR asynchronously
        ocr_future = self.extract_text_async(image)
        extracted_text = ocr_future.result()  # blocks only here, not on submit

        # Step 1b: Save OCR text automatically
        try:
            os.makedirs("ocr_outputs", exist_ok=True)
            if image_name:
                base_name = os.path.splitext(os.path.basename(image_name))[0]
            else:
                base_name = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = os.path.join("ocr_outputs", f"{base_name}_ocr.txt")
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(extracted_text)
            logger.info(f"OCR text automatically saved to {save_path}")
        except Exception as e:
            logger.error(f"Failed to automatically save OCR text: {e}")

        # Step 2: Detect sensitive content
        sensitive_keywords = self.detect_sensitive_content(extracted_text)
        has_sensitive = len(sensitive_keywords) > 0

        # Step 3: Conditional blur
        was_blurred = False
        processed_image = image
        if has_sensitive:
            logger.info("Sensitive content detected, applying blur")
            processed_image = self.blur_image(image)
            was_blurred = True

        # Step 4: Compress
        image_bytes = self.compress_image(processed_image)

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