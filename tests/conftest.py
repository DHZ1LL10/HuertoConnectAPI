import importlib
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.update({
    "JWT_SECRET": "test-jwt-" + "x" * 64,
    "OTP_HASH_SECRET": "test-otp-" + "x" * 64,
    "OTP_LINK_SECRET": "test-link-" + "x" * 64,
    "AGENT_API_KEY": "test-agent-" + "x" * 64,
    "APP_API_KEY": "test-agent-" + "x" * 64,
    "ENVIRONMENT": "testing", "OTP_DELIVERY_MODE": "console",
    "OTP_EXPOSE_CODE_IN_RESPONSE": "true", "MONGO_URI": "mongodb://localhost:27017",
    "MONGO_URL": "mongodb://localhost:27017", "MONGO_DB": "test_huerto", "DB_NAME": "test_huerto",
    "POSTGRES_URI": "postgresql://localhost/test_huerto", "ADMIN_PASSWORD": "",
    "SMTP_APP_PASSWORD": "", "MAIL_PASSWORD": "", "SMTP_USER": "", "MAIL_USERNAME": "",
})


def load_service(name):
    # Each service runs in its own process in Docker. Reproduce that ORM isolation
    # when tests reload the shared 'app' namespace in a single Python process.
    from shared.database import Base
    Base.registry.dispose()
    Base.metadata.clear()
    for key in list(sys.modules):
        if key == "app" or key.startswith("app."):
            del sys.modules[key]
    sys.path[:] = [p for p in sys.path if not p.endswith("-service") and not p.endswith("gateway")]
    sys.path.insert(0, str(ROOT / name))
    return importlib.import_module("app.main")
