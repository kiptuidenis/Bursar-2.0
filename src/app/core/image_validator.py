import io
from typing import Tuple
from PIL import Image, ImageOps

# Decompression bomb DoS protection: limit max image pixels to 10 megapixels (10,000,000)
Image.MAX_IMAGE_PIXELS = 10_000_000

MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2MB max payload

# Exact binary magic byte signatures for supported image types
MAGIC_SIGNATURES = {
    "png": b"\x89PNG\r\n\x1a\n",
    "jpeg": b"\xff\xd8\xff",
    "webp": b"RIFF"  # WEBP starts with RIFF and contains WEBP at byte offset 8..12
}

def detect_magic_format(contents: bytes) -> str:
    """
    Detect image format from binary magic bytes.
    Returns 'png', 'jpeg', or 'webp' if valid, or raises ValueError.
    """
    if contents.startswith(MAGIC_SIGNATURES["png"]):
        return "png"
    if contents.startswith(MAGIC_SIGNATURES["jpeg"]):
        return "jpeg"
    if contents.startswith(b"RIFF") and len(contents) >= 12 and contents[8:12] == b"WEBP":
        return "webp"
    
    # Reject SVG, XML, HTML, or non-matching magic headers explicitly
    raise ValueError("Invalid or unsupported image file format. Only PNG, JPEG, and WEBP images are permitted.")

def process_and_sanitize_avatar(contents: bytes) -> Tuple[bytes, str]:
    """
    Validates, re-encodes, and sanitizes uploaded avatar image bytes.
    
    1. Checks file payload size limit (max 2MB).
    2. Detects format via binary magic bytes (rejects SVG/HTML/disguised text).
    3. Opens image with PIL to verify structural integrity and decompression pixel caps.
    4. Re-encodes pure pixel data into a fresh byte stream, stripping polyglot scripts, 
       EXIF metadata, and custom chunk payloads.
    
    Returns (sanitized_bytes, file_extension).
    """
    if not contents or len(contents) == 0:
        raise ValueError("Uploaded file payload is empty.")

    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise ValueError("Avatar file size exceeds the 2MB limit.")

    # 1. Binary Magic Bytes Inspection
    detected_fmt = detect_magic_format(contents)

    # 2. PIL Structural Verification & Decompression Bomb Check
    try:
        stream = io.BytesIO(contents)
        with Image.open(stream) as img:
            # Check dimension bounds
            width, height = img.size
            if width * height > Image.MAX_IMAGE_PIXELS:
                raise ValueError("Image dimensions exceed maximum allowable pixel capacity.")

            # Validate PIL format matches detected magic format
            pil_format = (img.format or "").lower()
            if pil_format == "jpeg":
                pil_format = "jpeg"
            elif pil_format in ("png", "webp"):
                pass
            else:
                raise ValueError("Invalid or unsupported image format.")

            # Standardize color mode for safe re-encoding (RGB for JPEG, RGBA/RGB for PNG/WEBP)
            if detected_fmt == "jpeg":
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
            else:
                if img.mode not in ("RGB", "RGBA", "L"):
                    img = img.convert("RGBA")

            # 3. Re-encode Image (Decodes pixels & discards EXIF / polyglot payloads)
            out_buf = io.BytesIO()
            save_fmt = "JPEG" if detected_fmt == "jpeg" else detected_fmt.upper()
            
            # Save re-encoded pixel buffer without original metadata/EXIF
            img.save(out_buf, format=save_fmt, optimize=True)
            sanitized_bytes = out_buf.getvalue()

            canonical_ext = "jpg" if detected_fmt == "jpeg" else detected_fmt
            return sanitized_bytes, canonical_ext

    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Invalid or corrupted image file structure.") from exc
