"""Check the resolved deployment without starting containers or using credentials."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import httpx
import pytest
from conftest import load_service
from shared.config import settings


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def compose_config(tmp_path):
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("Docker Compose CLI is required to validate deployment")
    empty_env = tmp_path / "compose.env"
    empty_env.write_text("", encoding="utf-8")
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("CLOUDFLARE_", "COMPOSE_"))
    }
    environment.update({
        "MONGO_USER": "test", "MONGO_PASSWORD": "test", "MONGO_DB": "test",
        "POSTGRES_USER": "test", "POSTGRES_PASSWORD": "test", "POSTGRES_DB": "test",
        "AGENT_API_KEY": "test-agent-" + "x" * 64,
        "CLOUDFLARE_TUNNEL_TOKEN": "test-only-do-not-connect",
    })

    def resolve(cloudflare=True, **overrides):
        command = [docker, "compose", "--env-file", str(empty_env), "-f", str(ROOT / "docker-compose.yml")]
        if cloudflare:
            command += ["-f", str(ROOT / "docker-compose.cloudflare.yml")]
        # Never resolve the private env_file values into the test output.
        command += ["config", "--no-env-resolution", "--format", "json"]
        result = subprocess.run(command, cwd=ROOT, env={**environment, **overrides},
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    return resolve


def test_cloudflare_only_publishes_gateway_on_loopback(compose_config):
    services = compose_config()["services"]
    for name, service in services.items():
        if name != "gateway":
            assert not service.get("ports"), name
    assert len(services["gateway"]["ports"]) == 1
    port = services["gateway"]["ports"][0]
    assert (port["host_ip"], port["published"], port["target"]) == ("127.0.0.1", "8000", 8000)
    assert services["cloudflared"]["networks"].keys() == services["gateway"]["networks"].keys()
    assert services["cloudflared"]["depends_on"]["gateway"]["condition"] == "service_healthy"


def test_tunnel_token_is_only_granted_to_connector(compose_config):
    model = compose_config()
    connector = model["services"]["cloudflared"]
    assert model["secrets"]["cloudflare_tunnel_token"]["environment"] == "CLOUDFLARE_TUNNEL_TOKEN"
    assert "test-only-do-not-connect" not in json.dumps(model)
    assert "/run/secrets/cloudflare_tunnel_token" in connector["command"]
    assert "--token" not in connector["command"]
    assert connector["healthcheck"]["test"][-1] == "ready"
    for name, service in model["services"].items():
        if name != "cloudflared":
            assert not service.get("secrets"), name
            if service.get("env_file"):
                assert service["environment"]["CLOUDFLARE_TUNNEL_TOKEN"] == "", name


def test_public_domain_applies_to_otp_links_cors_and_https(compose_config):
    model = compose_config(CLOUDFLARE_PUBLIC_HOSTNAME="api.huerto.test",
                           CLOUDFLARE_FRONTEND_HOSTNAME="huerto.test",
                           CLOUDFLARE_ADMIN_HOSTNAME="panel.huerto.test")
    for name in ("gateway", "auth-service", "huertos-service", "plagas-service", "chat-service", "reportes-service"):
        environment = model["services"][name]["environment"]
        assert environment["API_PUBLIC_URL"] == "https://api.huerto.test"
        assert environment["FRONTEND_URL"] == "https://huerto.test"
        assert environment["CORS_ORIGINS"] == "https://huerto.test,https://www.huerto.test,https://panel.huerto.test,https://api.huerto.test"
        assert environment["ENVIRONMENT"] == "production"
        assert environment["OTP_DELIVERY_MODE"] == "smtp"
        assert environment["OTP_EXPOSE_CODE_IN_RESPONSE"] == "false"
    assert "--proxy-headers" in model["services"]["gateway"]["command"]
    for volume in model["services"]["plagas-service"]["volumes"]:
        assert volume["read_only"]


def test_local_mode_remains_available_without_cloudflare(compose_config):
    services = compose_config(cloudflare=False)["services"]
    assert "cloudflared" not in services
    assert services["auth-service"]["ports"][0]["published"] == "8001"
    model = compose_config(CLOUDFLARE_CORS_ORIGINS="https://cliente.huerto.test")
    assert model["services"]["auth-service"]["environment"]["CORS_ORIGINS"] == "https://cliente.huerto.test"


@pytest.mark.asyncio
@pytest.mark.parametrize("origin,expected", [
    ("https://panel.huerto.test", 200),
    ("https://otro.huerto.test", 400),
])
async def test_admin_browser_preflight_uses_deployment_origins(compose_config, monkeypatch, origin, expected):
    model = compose_config(CLOUDFLARE_ADMIN_HOSTNAME="panel.huerto.test")
    monkeypatch.setattr(settings, "CORS_ORIGINS", model["services"]["gateway"]["environment"]["CORS_ORIGINS"])
    gateway = load_service("gateway")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway.app),
                                 base_url="https://api.huertoconnect.com") as client:
        response = await client.options("/api/auth/login", headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        })
    assert response.status_code == expected
    if expected == 200:
        assert response.headers["access-control-allow-origin"] == origin
        assert "authorization" in response.headers["access-control-allow-headers"].lower()
    else:
        assert "access-control-allow-origin" not in response.headers
