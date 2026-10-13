"""Photo storage: Azure Blob Storage in production, local folders in dev/tests.

The database keeps a short reference string for each stored file:
  - Azure: "blob:<container>/<name>"
  - local: the file's path on disk (the original, pre-Azure format)
`load` returns None for a missing file, so callers can answer 404.
"""

import os
from functools import lru_cache

from app.config import settings

BLOB_PREFIX = "blob:"

AVATARS = "avatars"
FIELD_SELFIES = "field_selfies"
EMPLOYEE_PHOTOS = "employee_photos"
SIGNAGE_MEDIA = "signage_media"


def using_blob() -> bool:
    return bool(settings.azure_storage_connection_string)


def _container(kind: str) -> str:
    return {
        AVATARS: settings.storage_container_avatars,
        FIELD_SELFIES: settings.storage_container_field_selfies,
        EMPLOYEE_PHOTOS: settings.storage_container_employee_photos,
        SIGNAGE_MEDIA: settings.storage_container_signage,
    }[kind]


def _local_dir(kind: str) -> str:
    return {
        AVATARS: settings.avatar_dir,
        FIELD_SELFIES: settings.field_selfie_dir,
        EMPLOYEE_PHOTOS: settings.employee_photo_dir,
        SIGNAGE_MEDIA: settings.signage_media_dir,
    }[kind]


@lru_cache(maxsize=2)
def _service(connection_string: str):
    from azure.storage.blob import BlobServiceClient

    return BlobServiceClient.from_connection_string(connection_string)


def _blob_client(container: str, name: str):
    return _service(settings.azure_storage_connection_string).get_blob_client(
        container=container, blob=name
    )


def _split_blob_ref(ref: str) -> tuple[str, str]:
    container, name = ref[len(BLOB_PREFIX):].split("/", 1)
    return container, name


def save(kind: str, name: str, data: bytes, content_type: str = "image/jpeg") -> str:
    """Store `data` under `name` and return the reference to keep in the DB."""
    if using_blob():
        from azure.storage.blob import ContentSettings

        container = _container(kind)
        _blob_client(container, name).upload_blob(
            data, overwrite=True, content_settings=ContentSettings(content_type=content_type)
        )
        return f"{BLOB_PREFIX}{container}/{name}"

    path = os.path.join(_local_dir(kind), name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def load(ref: str | None) -> bytes | None:
    """Return the stored bytes, or None if there's no such file."""
    if not ref:
        return None
    if ref.startswith(BLOB_PREFIX):
        if not using_blob():
            return None
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return _blob_client(*_split_blob_ref(ref)).download_blob().readall()
        except ResourceNotFoundError:
            return None
    try:
        with open(ref, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def delete(ref: str | None) -> None:
    """Remove a stored file; a missing file is not an error."""
    if not ref:
        return
    if ref.startswith(BLOB_PREFIX):
        if not using_blob():
            return
        from azure.core.exceptions import ResourceNotFoundError

        try:
            _blob_client(*_split_blob_ref(ref)).delete_blob()
        except ResourceNotFoundError:
            pass
        return
    try:
        os.remove(ref)
    except OSError:
        pass
