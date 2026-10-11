import httpx
import builtins
import importlib
import pytest
from shared.services import image_storage as service
from shared.openapi_uploads import normalize_upload_schemas


def test_imagekit_does_not_import_cloudinary(monkeypatch):
    original = builtins.__import__
    def without_cloudinary(name, *args, **kwargs):
        if name == "cloudinary" or name.startswith("cloudinary."):
            raise AssertionError("El SDK retirado no debe importarse")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", without_cloudinary)
    import shared.services
    importlib.reload(shared.services)
    importlib.reload(service)


def test_openapi_file_controls_handle_new_pydantic_schema():
    schema = {"components": {"schemas": {"Upload": {"properties": {"imagen": {"type": "string", "contentMediaType": "application/octet-stream"}, "nombre": {"type": "string"}}}}}}
    normalized = normalize_upload_schemas(schema)
    properties = normalized["components"]["schemas"]["Upload"]["properties"]
    assert properties["imagen"]["format"] == "binary"
    assert "format" not in properties["nombre"]


@pytest.mark.parametrize("status", [200, 401, 500])
async def test_imagekit_upload_and_sanitized_errors(monkeypatch, status):
    monkeypatch.setattr(service.settings, "IMAGE_STORAGE_PROVIDER", "imagekit")
    monkeypatch.setattr(service.settings, "IMAGEKIT_PRIVATE_KEY", "private-test")
    original = httpx.AsyncClient
    def handler(request):
        assert request.url == "https://upload.imagekit.io/api/v1/files/upload"
        assert request.headers["authorization"].startswith("Basic ")
        assert b'name="file"' in request.content
        return httpx.Response(status, json={"url": "https://ik.imagekit.io/test/image.jpg", "fileId": "id-1", "error": "private-test"})
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    if status == 200:
        result = await service.upload_image(b"image", folder="test")
        assert result["public_id"] == "id-1" and result["provider"] == "imagekit"
        assert result["secure_url"].endswith("?tr=orig-true")
    else:
        with pytest.raises(RuntimeError) as error:
            await service.upload_image(b"image", folder="test")
        assert "private-test" not in str(error.value)


@pytest.mark.parametrize("status", [204, 404, 401, 500])
async def test_imagekit_rollback_delete(monkeypatch, status):
    monkeypatch.setattr(service.settings, "IMAGE_STORAGE_PROVIDER", "imagekit")
    monkeypatch.setattr(service.settings, "IMAGEKIT_PRIVATE_KEY", "private-test")
    original = httpx.AsyncClient
    def handler(request):
        assert request.method == "DELETE" and request.url == "https://api.imagekit.io/v1/files/uploaded-file-id"
        return httpx.Response(status, text="private-test" if status >= 400 else "")
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    if status in {204, 404}:
        await service.delete_image("uploaded-file-id")
    else:
        with pytest.raises(RuntimeError) as error:
            await service.delete_image("uploaded-file-id")
        assert "private-test" not in str(error.value)
