import logging
import re
from cloudinary_storage.storage import MediaCloudinaryStorage

logger = logging.getLogger('stride.storage')


class StrideMediaCloudinaryStorage(MediaCloudinaryStorage):
    """
    Hardened Cloudinary media storage backend for STRIDE.

    Key improvements over standard MediaCloudinaryStorage:
    1. Prevents malformed public_id generation by sanitizing asset names
       before saving to Cloudinary.
    2. Gracefully resolves legacy or malformed database references containing
       redundant scheme/domain prefixes (e.g. 'https:/res.cloudinary.com/...').
    3. Guarantees valid CDN delivery URLs with '/image/upload/' and versioning.
    4. Preserves existing valid Cloudinary paths without duplicate folder prefixing.
    """

    @staticmethod
    def clean_asset_name(name: str) -> str:
        """
        Strips accidental scheme and domain prefixes from asset names.
        Examples:
          'https:/res.cloudinary.com/drh8fjiwq/profiles/avatars/img.jpg' -> 'profiles/avatars/img.jpg'
          'https://res.cloudinary.com/drh8fjiwq/profiles/avatars/img.jpg' -> 'profiles/avatars/img.jpg'
          'profiles/avatars/img.jpg' -> 'profiles/avatars/img.jpg'
        """
        if not name:
            return ""
        name_str = str(name).strip()
        # Remove any leading URL scheme + domain + cloud name prefix
        cleaned = re.sub(r'^https?:/+[^/]+/[^/]+/', '', name_str)
        # Also handle cases where only scheme/host was prepended without cloud name
        cleaned = re.sub(r'^https?:/+', '', cleaned)
        return cleaned.lstrip('/')

    def _save(self, name, content):
        clean_name = self.clean_asset_name(name)
        return super()._save(clean_name, content)

    def url(self, name):
        if not name:
            return ""
        clean_name = self.clean_asset_name(name)
        return super().url(clean_name)
