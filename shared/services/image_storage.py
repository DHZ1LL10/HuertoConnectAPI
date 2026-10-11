"""Server-side ImageKit uploads preserving the original image bytes."""
import uuid
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import httpx
from shared.config import settings


def original_image_url(url):
    parsed = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parsed.query) if key != "tr"]
    query.append(("tr", "orig-true"))
    return urlunsplit(parsed._replace(query=urlencode(query)))


async def upload_image(file_bytes, *, folder, public_id=None, resource_type="image"):
    if settings.IMAGE_STORAGE_PROVIDER != "imagekit" or not settings.IMAGEKIT_PRIVATE_KEY:
        raise RuntimeError("Almacenamiento de imágenes no configurado")
    try:
        extension, mime = ("png", "image/png") if file_bytes.startswith(b"\x89PNG\r\n\x1a\n") else (("webp", "image/webp") if file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP" else ("jpg", "image/jpeg"))
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            response = await client.post(
                "https://upload.imagekit.io/api/v1/files/upload",
                auth=httpx.BasicAuth(settings.IMAGEKIT_PRIVATE_KEY, ""),
                data={"fileName": (public_id or uuid.uuid4().hex) + "." + extension,
                      "folder": "/" + folder.strip("/"), "useUniqueFileName": "true"},
                files={"file": ("imagen." + extension, file_bytes, mime)},
            )
            response.raise_for_status()
            result = response.json()
        if not isinstance(result, dict) or not isinstance(result.get("url"), str) or not result["url"].startswith("https://") or not result.get("fileId"):
            raise ValueError("Invalid upload response")
        return {"secure_url": original_image_url(result["url"]), "public_id": result["fileId"], "provider": "imagekit"}
    except (httpx.HTTPError, ValueError, TypeError):
        raise RuntimeError("No fue posible almacenar la imagen en ImageKit") from None


async def delete_image(file_id):
    """Rollback an upload using its server-issued fileId, never a client URL."""
    from urllib.parse import quote
    if settings.IMAGE_STORAGE_PROVIDER != "imagekit" or not settings.IMAGEKIT_PRIVATE_KEY:
        raise RuntimeError("Almacenamiento de imágenes no configurado")
    try:
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            response = await client.delete(
                "https://api.imagekit.io/v1/files/" + quote(str(file_id), safe=""),
                auth=httpx.BasicAuth(settings.IMAGEKIT_PRIVATE_KEY, ""),
            )
            if response.status_code != 404:
                response.raise_for_status()
    except httpx.HTTPError:
        raise RuntimeError("No fue posible retirar la imagen de ImageKit") from None
