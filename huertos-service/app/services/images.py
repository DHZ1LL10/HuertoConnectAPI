"""Validate profile image bytes before sending them to external storage."""
import io
import warnings
from PIL import Image, UnidentifiedImageError
from fastapi import HTTPException


def validate_image(data, mime):
    formats = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != formats.get(mime) or image.width * image.height > 25_000_000:
                    raise ValueError()
                image.verify()
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, "Imagen inválida")
