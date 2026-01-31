"""Media API routes for OpenBotX."""

from io import BytesIO

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from openbotx.api.schemas import MediaListResponse, MediaResponse
from openbotx.models.enums import ProviderType
from openbotx.providers.base import get_provider_registry
from openbotx.providers.storage.base import StorageProvider

router = APIRouter()


def _get_storage() -> StorageProvider:
    """Get storage provider."""
    registry = get_provider_registry()
    provider = registry.get(ProviderType.STORAGE)
    if not isinstance(provider, StorageProvider):
        raise HTTPException(status_code=503, detail="Storage not available")
    return provider


@router.get("", response_model=MediaListResponse)
async def list_media(
    prefix: str = "",
    limit: int = 100,
) -> MediaListResponse:
    """List media files.

    Args:
        prefix: Path prefix filter
        limit: Maximum files to return

    Returns:
        List of media files
    """
    storage = _get_storage()
    files = await storage.list_files(prefix=prefix, limit=limit)

    return MediaListResponse(
        files=[
            MediaResponse(
                id=f.id,
                filename=f.filename,
                content_type=f.content_type,
                size=f.size,
                path=f.path,
                url=f.url,
                created_at=f.created_at,
            )
            for f in files
        ],
        total=len(files),
    )


@router.get("/{path:path}")
async def get_media(path: str) -> StreamingResponse:
    """Get a media file.

    Args:
        path: File path

    Returns:
        File content
    """
    storage = _get_storage()

    if not await storage.exists(path):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    content = await storage.get(path)

    # Guess content type from path
    import mimetypes

    content_type, _ = mimetypes.guess_type(path)

    return StreamingResponse(
        BytesIO(content),
        media_type=content_type or "application/octet-stream",
    )


@router.post("", response_model=MediaResponse)
async def upload_media(file: UploadFile = File(...)) -> MediaResponse:
    """Upload a media file.

    Args:
        file: File to upload

    Returns:
        Uploaded file info
    """
    storage = _get_storage()

    content = await file.read()
    stored = await storage.save_bytes(
        data=content,
        filename=file.filename or "unknown",
        content_type=file.content_type or "application/octet-stream",
    )

    return MediaResponse(
        id=stored.id,
        filename=stored.filename,
        content_type=stored.content_type,
        size=stored.size,
        path=stored.path,
        url=stored.url,
        created_at=stored.created_at,
    )


@router.delete("/{path:path}")
async def delete_media(path: str) -> dict[str, bool]:
    """Delete a media file.

    Args:
        path: File path

    Returns:
        Success status
    """
    storage = _get_storage()

    if not await storage.exists(path):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    success = await storage.delete(path)

    return {"success": success}
