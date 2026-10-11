"""Verify Google ID tokens with bounded network calls outside the event loop."""
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from google.auth.exceptions import TransportError, GoogleAuthError
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from app.core.config import settings

class TimedRequest(google_requests.Request):
    def __call__(self, *args, **kwargs):
        kwargs["timeout"] = settings.GOOGLE_TIMEOUT_SECONDS
        return super().__call__(*args, **kwargs)

def _verify(credential):
    import requests
    with requests.Session() as session:
        return id_token.verify_oauth2_token(credential, TimedRequest(session=session), audience=settings.GOOGLE_CLIENT_ID)

async def verify_google_token(credential: str) -> dict:
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(503, "Google Sign-In no está configurado")
    try:
        payload = await run_in_threadpool(_verify, credential)
    except TransportError:
        raise HTTPException(503, "No se pudo contactar con Google. Intenta de nuevo.")
    except (ValueError, GoogleAuthError, KeyError):
        raise HTTPException(401, "Token de Google inválido, expirado o destinado a otro cliente")
    if not payload.get("sub") or not payload.get("email"):
        raise HTTPException(401, "El token no contiene una identidad válida")
    if payload.get("email_verified") is not True:
        raise HTTPException(401, "El correo de Google no está verificado")
    return payload

def extract_google_user_info(payload):
    full_name = payload.get("name", "")
    given = payload.get("given_name", "") or full_name.split(" ", 1)[0]
    family = payload.get("family_name", "")
    return {"google_id": payload["sub"], "email": payload["email"].strip().lower(), "nombre": given, "apellidos": family, "picture": payload.get("picture")}
