import asyncio
import importlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
from bson import ObjectId
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient
from conftest import load_service


@pytest.fixture
async def auth(monkeypatch):
    main = load_service("auth-service")
    db = AsyncMongoMockClient(tz_aware=True).auth_test
    importlib.import_module("app.core.database")._db = db
    main.app.state.mongodb = db
    await db.usuarios.create_index("email", unique=True)
    await db.sesiones.create_index("token_hash", unique=True)
    otp = importlib.import_module("app.services.otp_service")
    monkeypatch.setattr(otp, "generate_otp", lambda: "123456")
    mail = importlib.import_module("app.services.mail_adapter")
    deliver = AsyncMock(return_value=True)
    monkeypatch.setattr(mail, "send_otp_email", deliver)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        yield client, db, otp, deliver


async def register(client):
    response = await client.post("/api/auth/register", json={"nombre": "Ana", "apellidos": "García", "email": "ana@example.com", "password": "Password123!", "confirmPassword": "Password123!"})
    assert response.status_code == 201, response.text
    return response.json()["challengeId"]


async def verify(client, cid, code="123456"):
    return await client.post("/api/auth/verify-otp", json={"challengeId": cid, "otpCode": code})


async def test_register_login_otp_session_logout(auth):
    client, db, otp, deliver = auth
    cid = await register(client)
    assert deliver.await_count == 1
    doc = await db.otp_challenges.find_one({"_id": ObjectId(cid)})
    assert doc["otp_hash"] != "123456"
    response = await verify(client, cid)
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert (await verify(client, cid)).status_code == 404
    assert (await client.get("/api/auth/session", headers=headers)).json()["email"] == "ana@example.com"
    assert (await client.get("/api/auth/session")).status_code == 401
    assert (await client.post("/api/auth/login", json={"email": "ana@example.com", "password": "incorrecta"})).status_code == 401
    response = await client.post("/api/auth/login", json={"email": "ana@example.com", "password": "Password123!"})
    assert response.status_code == 200, response.text
    assert not response.json().get("token")
    assert (await verify(client, response.json()["challengeId"])).status_code == 200
    assert (await client.post("/api/auth/logout", headers=headers)).status_code == 200
    assert (await client.get("/api/auth/session", headers=headers)).status_code == 401


async def test_otp_wrong_expired_rotated_and_consumed_atomically(auth, monkeypatch):
    client, db, otp, deliver = auth
    cid = await register(client)
    for _ in range(5):
        assert (await verify(client, cid, "000000")).status_code == 401
    assert (await verify(client, cid)).status_code == 429
    monkeypatch.setattr(otp, "generate_otp", lambda: "654321")
    assert (await client.post("/api/auth/resend-otp", json={"challengeId": cid})).status_code == 200
    assert (await verify(client, cid)).status_code == 401
    outcomes = await asyncio.gather(otp.validate_and_consume_otp(db, cid, "654321"), otp.validate_and_consume_otp(db, cid, "654321"), return_exceptions=True)
    assert sum(isinstance(o, dict) for o in outcomes) == 1
    cid = await register(client)
    await db.otp_challenges.update_one({"_id": ObjectId(cid)}, {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)}})
    assert (await verify(client, cid, "654321")).status_code == 410


async def test_smtp_failure_is_not_reported_as_success(auth):
    client, db, otp, deliver = auth
    deliver.side_effect = importlib.import_module("app.services.mail_service").MailDeliveryError("private SMTP details")
    response = await client.post("/api/auth/register", json={"nombre": "Ana", "email": "ana@example.com", "password": "Password123!"})
    assert response.status_code == 503, response.text
    assert "private" not in response.text
    assert await db.otp_challenges.count_documents({}) == 0


async def test_suspended_user_cannot_complete_old_otp(auth):
    client, db, otp, deliver = auth
    cid = await register(client)
    await db.usuarios.update_one({"email": "ana@example.com"}, {"$set": {"estado": "Suspendido"}})
    assert (await verify(client, cid)).status_code == 403


async def test_google_repeated_sessions_and_aliases(auth, monkeypatch):
    client, db, otp, deliver = auth
    google = importlib.import_module("app.services.google_service")
    payload = {"sub": "google-unique-123", "email": "ana@gmail.com", "email_verified": True, "given_name": "Ana"}
    monkeypatch.setattr(google, "verify_google_token", AsyncMock(return_value=payload))
    for key in ["credential", "idToken", "id_token"]:
        response = await client.post("/api/auth/google", json={key: "valid-test-token"})
        assert response.status_code == 200, response.text
        token = response.json()["token"]
        assert (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})).status_code == 200
    sessions = await db.sesiones.find().to_list(10)
    assert len(sessions) == 3 and len({s["token_hash"] for s in sessions}) == 3
    assert await db.usuarios.count_documents({}) == 1
    await db.usuarios.update_one({"email": "ana@gmail.com"}, {"$set": {"estado": "Suspendido"}})
    assert (await client.post("/api/auth/google", json={"credential": "valid"})).status_code == 403


async def test_google_token_validation(auth, monkeypatch):
    client, db, otp, deliver = auth
    google = importlib.import_module("app.services.google_service")
    monkeypatch.setattr(google.settings, "GOOGLE_CLIENT_ID", "expected.apps.googleusercontent.com")
    def invalid(token):
        raise ValueError("private verifier details")
    monkeypatch.setattr(google, "_verify", invalid)
    response = await client.post("/api/auth/google", json={"credential": "invalid"})
    assert response.status_code == 401 and "private" not in response.text
    monkeypatch.setattr(google, "_verify", lambda token: {"sub": "g", "email": "a@gmail.com", "email_verified": False})
    assert (await client.post("/api/auth/google", json={"credential": "invalid"})).status_code == 401
    monkeypatch.setattr(google.settings, "GOOGLE_CLIENT_ID", "")
    assert (await client.post("/api/auth/google", json={"credential": "invalid"})).status_code == 503


async def test_email_template_and_smtp_options(auth, monkeypatch):
    client, db, otp, deliver = auth
    mail = importlib.import_module("app.services.mail_service")
    html = mail._build_otp_html("123456", "registro", '<script>alert(1)</script>', 5, "https://example.com/login")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "cid:huerto-raices" in html and "cid:huerto-maceta" in html and "123456" in html and "@media" in html
    assert "javascript:" not in mail._build_otp_html("123456", "login", verify_url="javascript:alert(1)")
    monkeypatch.setattr(mail.settings, "OTP_DELIVERY_MODE", "smtp")
    monkeypatch.setattr(mail.settings, "SMTP_USER", "test@example.com")
    monkeypatch.setattr(mail.settings, "SMTP_APP_PASSWORD", "testing-only")
    smtp = AsyncMock(return_value=({}, "queued"))
    monkeypatch.setattr(mail.aiosmtplib, "send", smtp)
    assert await mail.send_otp_email("recipient@example.com", "123456")
    msg = smtp.call_args.args[0]
    assert msg.get_body(preferencelist=("html",)).get_content_type() == "text/html"
    assert msg.get_body(preferencelist=("plain",)).get_content_type() == "text/plain"
    inline = [part for part in msg.walk() if part.get_content_type() == "image/png"]
    assert {part["Content-ID"] for part in inline} == {"<huerto-maceta>", "<huerto-raices>", "<huerto-marco>"}
    assert all(part.get_payload(decode=True).startswith(b"\x89PNG") for part in inline)
    assert smtp.call_args.kwargs["timeout"] == 15


async def test_password_reset_revokes_sessions_and_cannot_be_replayed(auth):
    client, db, otp, deliver = auth
    cid = await register(client)
    token = (await verify(client, cid)).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    forgot = await client.post("/api/auth/forgot-password", json={"email": "ana@example.com"})
    assert forgot.status_code == 200
    verified = await verify(client, forgot.json()["challengeId"])
    assert verified.status_code == 200, verified.text
    reset = {"resetToken": verified.json()["resetToken"], "newPassword": "New-password-123!"}
    assert (await client.post("/api/auth/reset-password", json=reset)).status_code == 200
    assert (await client.post("/api/auth/reset-password", json=reset)).status_code == 400
    assert (await client.get("/api/auth/me", headers=headers)).status_code == 401
    assert (await client.post("/api/auth/login", json={"email": "ana@example.com", "password": "New-password-123!"})).status_code == 200


async def test_untrusted_email_requires_explicit_google_link(auth, monkeypatch):
    client, db, otp, deliver = auth
    cid = await register(client)
    token = (await verify(client, cid)).json()["token"]
    google = importlib.import_module("app.services.google_service")
    monkeypatch.setattr(google, "verify_google_token", AsyncMock(return_value={"sub": "google-external", "email": "ana@example.com", "email_verified": True}))
    assert (await client.post("/api/auth/google", json={"credential": "valid"})).status_code == 409
    response = await client.post("/api/auth/google/link", json={"credential": "valid"}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    assert (await client.post("/api/auth/google", json={"credential": "valid"})).status_code == 200


async def test_rate_limit_and_resend_limit(auth):
    client, db, otp, deliver = auth
    cid = await register(client)
    for _ in range(3):
        assert (await client.post("/api/auth/resend-otp", json={"challengeId": cid})).status_code == 200
    assert (await client.post("/api/auth/resend-otp", json={"challengeId": cid})).status_code == 429
    await db.auth_rate_limits.update_many({}, {"$set": {"attempts": 30}})
    assert (await client.post("/api/auth/login", json={"email": "ana@example.com", "password": "Password123!"})).status_code == 429


async def test_google_provider_outage_and_smtp_starttls(auth, monkeypatch):
    client, db, otp, deliver = auth
    google = importlib.import_module("app.services.google_service")
    from google.auth.exceptions import TransportError
    monkeypatch.setattr(google.settings, "GOOGLE_CLIENT_ID", "test.apps.googleusercontent.com")
    def unavailable(token):
        raise TransportError("private network details")
    monkeypatch.setattr(google, "_verify", unavailable)
    response = await client.post("/api/auth/google", json={"credential": "token"})
    assert response.status_code == 503 and "private" not in response.text
    mail = importlib.import_module("app.services.mail_service")
    for name, value in {"OTP_DELIVERY_MODE": "smtp", "SMTP_USER": "test@example.com", "SMTP_APP_PASSWORD": "fake", "SMTP_SECURE": False, "SMTP_PORT": 587}.items():
        monkeypatch.setattr(mail.settings, name, value)
    smtp = AsyncMock(return_value=({}, "queued"))
    monkeypatch.setattr(mail.aiosmtplib, "send", smtp)
    await mail.send_otp_email("recipient@example.com", "123456")
    assert smtp.call_args.kwargs["start_tls"] is True
    assert smtp.call_args.kwargs["use_tls"] is False


async def test_google_signature_audience_and_expiration(auth, monkeypatch):
    """Exercise google-auth itself using local signing keys, without contacting Google."""
    import json
    import jwt
    from types import SimpleNamespace
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    client, db, otp, deliver = auth
    google = importlib.import_module("app.services.google_service")
    audience = "expected.apps.googleusercontent.com"
    monkeypatch.setattr(google.settings, "GOOGLE_CLIENT_ID", audience)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    certs = json.dumps({"test-key": public_key}).encode()
    monkeypatch.setattr(google.TimedRequest, "__call__", lambda *args, **kwargs: SimpleNamespace(status=200, data=certs))
    now = int(datetime.now(timezone.utc).timestamp())
    claims = {"sub": "signed-google-user", "email": "signed@gmail.com", "email_verified": True, "iss": "https://accounts.google.com", "aud": audience, "iat": now, "exp": now + 300}
    def token(values):
        return jwt.encode(values, private_key, algorithm="RS256", headers={"kid": "test-key"})
    assert (await client.post("/api/auth/google", json={"credential": token(claims)})).status_code == 200
    for invalid_claims in [{**claims, "aud": "wrong-client"}, {**claims, "iat": now-600, "exp": now-300}, {**claims, "iss": "https://attacker.example"}]:
        assert (await client.post("/api/auth/google", json={"credential": token(invalid_claims)})).status_code == 401
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(claims, other_key, algorithm="RS256", headers={"kid": "test-key"})
    assert (await client.post("/api/auth/google", json={"credential": forged})).status_code == 401
