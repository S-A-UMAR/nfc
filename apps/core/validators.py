from urllib.parse import urlparse
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from PIL import Image

ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
ALLOWED_IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP'}
# MIME type → extension fallback for browsers that omit file extensions
CONTENT_TYPE_TO_EXT = {
    'image/jpeg': 'jpg',
    'image/jpg':  'jpg',
    'image/png':  'png',
    'image/webp': 'webp',
}
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


def validate_image_upload(file, max_size_bytes=MAX_IMAGE_SIZE_BYTES):
    """
    Strict validation for uploaded raster images:
    1. Checks file extension whitelist, with MIME-type fallback when the browser
       omits an extension (e.g. some iOS / Android uploads).
    2. Enforces maximum file size (default 5 MB).
    3. Verifies file content integrity using Pillow.
       IMPORTANT: img.format is captured BEFORE img.verify() because verify()
       is destructive — it closes Pillow's internal stream and can clear
       img.format to None in some Pillow builds.
    """
    if not file:
        return file

    # 1. Resolve extension (with MIME-type fallback)
    filename = getattr(file, 'name', '') or ''
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    if not ext:
        # Browser sent no extension — try the declared content type
        content_type = (getattr(file, 'content_type', '') or '').lower().split(';')[0].strip()
        ext = CONTENT_TYPE_TO_EXT.get(content_type, '')

    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        if ext in ('heic', 'heif', 'avif'):
            raise ValidationError(
                _("HEIC/HEIF/AVIF photos are not supported. Please convert to JPG or PNG before uploading.")
            )
        display_ext = f'.{ext}' if ext else '(unknown format — no extension detected)'
        raise ValidationError(
            _(f"Unsupported file format '{display_ext}'. Only JPG, PNG, and WEBP images are accepted.")
        )

    # 2. Check file size
    if hasattr(file, 'size') and file.size > max_size_bytes:
        size_mb = max_size_bytes / (1024 * 1024)
        raise ValidationError(
            _(f"File size exceeds {size_mb:.0f} MB limit. Please upload a smaller image.")
        )

    # 3. Pillow integrity check
    try:
        initial_pos = file.tell() if hasattr(file, 'tell') else 0
        img = Image.open(file)
        # Capture format BEFORE verify() — verify() is destructive and clears
        # img.format in many Pillow versions once the stream is exhausted.
        detected_format = img.format
        img.verify()

        if detected_format not in ALLOWED_IMAGE_FORMATS:
            raise ValidationError(
                _(f"Unsupported image type '{detected_format}'. Only JPG, PNG, and WEBP are accepted.")
            )

        if hasattr(file, 'seek'):
            file.seek(initial_pos)
    except Exception as e:
        if isinstance(e, ValidationError):
            raise
        raise ValidationError(_("Corrupt or invalid image file. Please upload a valid JPG, PNG, or WEBP image."))

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
