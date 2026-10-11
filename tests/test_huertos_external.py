import importlib
import io
from datetime import datetime, timezone
import pytest
from PIL import Image
from bson import ObjectId
from test_huertos_service import api, module


async def test_profile_upload_response_and_failure_preserve_picture(api, monkeypatch):
    client, db, owner, other, headers = api
    from shared.services import image_storage
    await db.usuarios.update_one({"_id": ObjectId(owner["id"])}, {"$set": {"nombre": "Prueba", "profile_picture": "https://example.com/old.png"}})
    stream = io.BytesIO()
    Image.new("RGB", (16, 16), "green").save(stream, format="PNG")
    files = {"foto": ("photo.png", stream.getvalue(), "image/png")}

    async def fail(*args, **kwargs):
        raise RuntimeError("private-provider-detail")
    monkeypatch.setattr(image_storage, "upload_image", fail)
    response = await client.patch(f"/api/usuarios/{owner['id']}/foto", files=files)
    assert response.status_code == 502 and "private-provider" not in response.text
    assert (await db.usuarios.find_one({"_id": ObjectId(owner["id"])}))["profile_picture"] == "https://example.com/old.png"

    async def success(*args, **kwargs):
        return {"secure_url": "https://example.com/new.png", "public_id": "test-new"}
    monkeypatch.setattr(image_storage, "upload_image", success)
    response = await client.patch(f"/api/usuarios/{owner['id']}/foto", files=files)
    assert response.status_code == 200, response.text
    assert response.json()["profile_picture"] == "https://example.com/new.png"
    assert (await client.get(f"/api/usuarios/{owner['id']}")).json()["profile_picture"] == "https://example.com/new.png"


async def test_contact_smtp_tls_headers(module, monkeypatch):
    routes = importlib.import_module("app.routes.extras")
    schemas = importlib.import_module("app.models.schemas")
    captured = {}
    class SMTP:
        def __init__(self, host, port, **kwargs):
            assert kwargs["timeout"] == 20 and kwargs["context"]
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def login(self, username, password):
            assert username == "sender@example.com" and password == "test-only"
        def send_message(self, message):
            captured["message"] = message
    monkeypatch.setattr(routes.smtplib, "SMTP_SSL", SMTP)
    monkeypatch.setattr(routes.settings, "SMTP_SECURE", True)
    monkeypatch.setattr(routes.settings, "SMTP_USER", "sender@example.com")
    monkeypatch.setattr(routes.settings, "SMTP_APP_PASSWORD", "test-only")
    monkeypatch.setattr(routes.settings, "CONTACT_INBOX_EMAIL", "receiver@example.com")
    contact = schemas.ContactoCreate(nombre="Prueba\r\nBcc: injected@example.com", email="reply@example.com", mensaje="Prueba")
    await routes._send_contact_notification_email(contact, datetime.now(timezone.utc))
    assert captured["message"]["Bcc"] is None
    assert captured["message"]["To"] == "receiver@example.com"
    assert captured["message"]["Reply-To"] == "reply@example.com"
