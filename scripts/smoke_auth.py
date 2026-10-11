"""Smoke test ONLY against the isolated compose.test.yml service (no real email)."""
import uuid
import httpx


def main():
    with httpx.Client(base_url="http://127.0.0.1:18001", timeout=30) as client:
        assert client.get("/health").status_code == 200
        email = f"smoke-{uuid.uuid4().hex}@example.com"
        password = "Smoke-test-password-123!"
        register = client.post("/api/auth/register", json={"nombre": "Prueba aislada", "email": email, "password": password})
        assert register.status_code == 201, register.text
        challenge = register.json()
        verified = client.post("/api/auth/verify-otp", json={"challengeId": challenge["challengeId"], "otpCode": challenge["devOtpCode"]})
        assert verified.status_code == 200, verified.text
        token = verified.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/auth/me", headers=headers).status_code == 200
        login = client.post("/api/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200, login.text
        code = login.json()
        assert client.post("/api/auth/verify-otp", json={"challengeId": code["challengeId"], "otpCode": code["devOtpCode"]}).status_code == 200
        assert client.post("/api/auth/logout", headers=headers).status_code == 200
        assert client.get("/api/auth/me", headers=headers).status_code == 401
        assert client.get("/api/auth/google/config").status_code == 200
    print("Auth smoke OK: health, registro, OTP, login, sesion, logout y configuracion Google.")


if __name__ == "__main__":
    main()
