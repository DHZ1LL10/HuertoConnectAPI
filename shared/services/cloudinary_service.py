"""
Shared — Servicio de Cloudinary para subida y gestión de imágenes.

Inicializa el SDK de Cloudinary una única vez a partir de CLOUDINARY_URL
del entorno. Expone funciones async-friendly que corren las operaciones
bloqueantes de Cloudinary en un executor para no bloquear el event loop.

Uso:
    from shared.services.cloudinary_service import upload_image, delete_image, get_thumbnail_url

    url = await upload_image(file, folder="huerto-connect/perfiles")
    ok  = await delete_image("huerto-connect/perfiles/abc123")
    thumb = get_thumbnail_url("huerto-connect/perfiles/abc123")
"""

import asyncio
import os
from functools import partial

import cloudinary
import cloudinary.uploader
import cloudinary.utils

# ---------------------------------------------------------------------------
# Inicialización — se ejecuta al importar el módulo
# ---------------------------------------------------------------------------

_CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL", "")

if _CLOUDINARY_URL:
    cloudinary.config(cloudinary_url=_CLOUDINARY_URL)
else:
    # Configuración individual como fallback (útil en local con variables separadas)
    cloudinary.config(
        cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
        api_key=os.environ.get("CLOUDINARY_API_KEY", ""),
        api_secret=os.environ.get("CLOUDINARY_API_SECRET", ""),
        secure=True,
    )


# ---------------------------------------------------------------------------
# Constantes de validación
# ---------------------------------------------------------------------------

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_FILE_SIZE_MB = 5
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


# ---------------------------------------------------------------------------
# Helpers de validación
# ---------------------------------------------------------------------------

def validate_image_file(filename: str, content_type: str, size: int | None = None) -> None:
    """
    Valida que el archivo sea una imagen permitida y no supere el límite de tamaño.

    Args:
        filename:     Nombre original del archivo.
        content_type: MIME type del archivo (e.g. ``image/jpeg``).
        size:         Tamaño en bytes (opcional). Si es None, no se valida.

    Raises:
        ValueError: Si el archivo no es válido.
    """
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Extensión de archivo no permitida: '{ext}'. "
            f"Usa: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    if content_type not in ALLOWED_MIME_TYPES:
        raise ValueError(
            f"Tipo MIME no permitido: '{content_type}'. "
            f"Usa: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
        )
    if size is not None and size > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"El archivo supera el tamaño máximo de {MAX_FILE_SIZE_MB} MB."
        )


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

async def upload_image(
    file_bytes: bytes,
    *,
    folder: str,
    public_id: str | None = None,
    resource_type: str = "image",
) -> dict:
    """
    Sube una imagen a Cloudinary de forma no bloqueante.

    Args:
        file_bytes:    Contenido del archivo en bytes.
        folder:        Carpeta destino en Cloudinary (e.g. ``"huerto-connect/perfiles"``).
        public_id:     ID público personalizado. Si es None, Cloudinary lo genera.
        resource_type: ``"image"`` (default) o ``"raw"``.

    Returns:
        Diccionario con la respuesta de Cloudinary. Claves útiles:
        - ``secure_url``  → URL HTTPS de la imagen.
        - ``public_id``   → Identificador para transformaciones y borrado.
        - ``width`` / ``height`` → Dimensiones de la imagen subida.

    Raises:
        RuntimeError: Si la subida falla en Cloudinary.
    """
    upload_kwargs: dict = {
        "folder": folder,
        "resource_type": resource_type,
        "overwrite": True,
    }
    if public_id:
        upload_kwargs["public_id"] = public_id

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            partial(cloudinary.uploader.upload, file_bytes, **upload_kwargs),
        )
    except Exception as exc:
        raise RuntimeError(f"Error al subir imagen a Cloudinary: {exc}") from exc

    return result


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

async def delete_image(public_id: str, resource_type: str = "image") -> bool:
    """
    Elimina una imagen de Cloudinary por su ``public_id``.

    Args:
        public_id:     ID público de la imagen en Cloudinary.
        resource_type: Tipo de recurso (``"image"`` por defecto).

    Returns:
        ``True`` si fue eliminada, ``False`` si no se encontró.
    """
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            partial(cloudinary.uploader.destroy, public_id, resource_type=resource_type),
        )
        return result.get("result") == "ok"
    except Exception as exc:
        print(f"[CLOUDINARY] delete_image error for '{public_id}': {exc}")
        return False


# ---------------------------------------------------------------------------
# Thumbnail URL (sin I/O — solo construcción de URL)
# ---------------------------------------------------------------------------

def get_thumbnail_url(
    public_id: str,
    *,
    width: int = 200,
    height: int = 200,
    crop: str = "fill",
    gravity: str = "face",
    format: str = "webp",
) -> str:
    """
    Genera la URL de una miniatura con transformaciones de Cloudinary.

    No realiza ninguna petición HTTP; la URL de transformación se construye
    localmente a partir del ``public_id``.

    Args:
        public_id: ID público de la imagen en Cloudinary.
        width:     Ancho de la miniatura en píxeles (default: 200).
        height:    Alto de la miniatura en píxeles (default: 200).
        crop:      Modo de recorte. ``"fill"`` rellena manteniendo la proporción.
        gravity:   Punto focal del recorte. ``"face"`` centra en la cara.
        format:    Formato de salida (``"webp"`` por defecto para optimizar tamaño).

    Returns:
        URL HTTPS con transformaciones aplicadas.
    """
    url, _ = cloudinary.utils.cloudinary_url(
        public_id,
        width=width,
        height=height,
        crop=crop,
        gravity=gravity,
        fetch_format=format,
        quality="auto",
        secure=True,
    )
    return url
