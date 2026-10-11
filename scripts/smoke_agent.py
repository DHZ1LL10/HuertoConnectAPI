"""Check Agent against local Ollama without storing or sending user data."""
import argparse
from pathlib import Path
import sys
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent-service"))
from app.config import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8006")
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    with httpx.Client(base_url=args.url, timeout=settings.ollama_timeout_seconds + 10, trust_env=False) as client:
        for path in ["/health/live", "/health/ready", "/docs"]:
            response = client.get(path)
            assert response.status_code == 200, f"{path}: {response.status_code}"
        assert client.post("/v1/generate", json={"message": "¿Cómo cuido mi huerto?"}).status_code == 401
        if args.generate:
            headers = {"X-API-Key": settings.app_api_key.get_secret_value(), "X-User-ID": "agent-smoke-test"}
            result = client.post("/v1/generate", headers=headers, json={"message": "Tengo jitomates en maceta. ¿Cómo puedo comprobar si necesitan riego?"})
            assert result.status_code == 200, f"Generación: {result.status_code}"
            body = result.json()
            assert body["status"] == "answered" and body["answer"].strip(), body.get("status")
            assert body["model"] == settings.ollama_model
            print("Respuesta real de Ollama:", body["answer"])
    print("Agent smoke OK: health, readiness, Swagger, autenticación" + (" y generación real." if args.generate else "."))


if __name__ == "__main__":
    main()
