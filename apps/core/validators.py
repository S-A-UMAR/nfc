import os
from urllib.parse import urlparse
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from PIL import Image

ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
ALLOWED_IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP'}
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


def validate_image_upload(file, max_size_bytes=MAX_IMAGE_SIZE_BYTES):
    """
    Strict validation for uploaded raster images:
    1. Checks file extension whitelist (strictly rejects .svg, .exe, .html, etc.)
    2. Enforces maximum file size (default 5MB)
    3. Verifies file content integrity using Pillow Image.verify()
    """
    if not file:
        return file

    # 1. Check extension
    filename = getattr(file, 'name', '')
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(
            _(f"Unsupported file format '.{ext}'. Only JPG, PNG, and WEBP raster images are accepted.")
        )

    # 2. Check file size
    if hasattr(file, 'size') and file.size > max_size_bytes:
        size_mb = max_size_bytes / (1024 * 1024)
        raise ValidationError(
            _(f"File size exceeds {size_mb:.0f}MB limit. Please upload a smaller image.")
        )

    # 3. Pillow integrity verification
    try:
        # Save position, verify, and rewind
        initial_pos = file.tell() if hasattr(file, 'tell') else 0
        img = Image.open(file)
        img.verify()

        if img.format not in ALLOWED_IMAGE_FORMATS:
            raise ValidationError(_(f"Unsupported image type: {img.format}."))

        if hasattr(file, 'seek'):
            file.seek(initial_pos)
    except Exception as e:
        if isinstance(e, ValidationError):
            raise
        raise ValidationError(_("Corrupt or invalid image file. Please upload a valid raster image."))

    return file


DANGEROUS_URL_SCHEMES = {'javascript', 'data', 'vbscript', 'file'}

def validate_safe_url(url: str, allow_relative: bool = True) -> str:
    """
    Validates that a URL does not use dangerous schemes (e.g. javascript:, data:).
    Only permits http, https, or safe relative paths.
    """
    if not url:
        return url

    cleaned_url = url.strip()

    # Check for scheme-relative or dangerous inline schemes
    lower_url = cleaned_url.lower()
    for scheme in DANGEROUS_URL_SCHEMES:
        if lower_url.startswith(f"{scheme}:"):
            raise ValidationError(_(f"Dangerous URL scheme '{scheme}:' is not permitted."))

    # Parse scheme
    parsed = urlparse(cleaned_url)
    if parsed.scheme:
        if parsed.scheme.lower() not in {'http', 'https'}:
            raise ValidationError(_(f"Only 'http' and 'https' links are permitted."))
    elif not allow_relative and not cleaned_url.startswith(('http://', 'https://')):
        raise ValidationError(_("Please provide a valid web URL starting with https:// or http://."))

    return cleaned_url
