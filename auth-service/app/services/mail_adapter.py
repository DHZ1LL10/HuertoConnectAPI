"""
Auth Service — Adaptador de correo para el nuevo flujo OTP.

Envuelve la función ``send_otp_email`` del mail_service existente y expone
una interfaz más simple orientada al router de registro/login.

El envío siempre se realiza como ``BackgroundTask`` para no bloquear
la respuesta HTTP. Si el envío falla, se registra el error en logs
pero NO se lanza excepción (el challenge ya está guardado en BD).
"""

import asyncio

from fastapi import BackgroundTasks

from app.services.mail_service import send_otp_email as _send_otp_email


# ---------------------------------------------------------------------------
# Tipos de acción que determinan el asunto y cuerpo del correo
# ---------------------------------------------------------------------------

_TIPO_TO_ACTION: dict[str, str] = {
    "registro": "registro",
    "login": "login",
    "reset-password": "reset-password",
    "reset_password": "reset-password",
    "recuperacion": "reset-password",
    "recovery": "reset-password",
}


def _fire_and_log(coro) -> None:
    """
    Ejecuta una corutina en el event loop actual de forma no bloqueante.
    Cualquier excepción queda registrada en el log sin propagarse.
    """
    async def _wrapper():
        try:
            await coro
        except Exception as exc:
            print(f"[MAIL BACKGROUND ERROR] {exc}")

    asyncio.create_task(_wrapper())


async def send_otp_background(
    background_tasks: BackgroundTasks,
    *,
    email: str,
    otp_code: str,
    tipo: str,
    recipient_name: str = "",
    challenge_id: str = "",
    expires_at: str = "",
) -> None:
    """
    Encola el envío del correo OTP como tarea de fondo.

    Args:
        background_tasks: Instancia de ``BackgroundTasks`` de FastAPI.
        email:            Dirección de destino.
        otp_code:         Código OTP en texto plano (se envía en el correo).
        tipo:             Tipo de challenge (``registro`` | ``login`` | ``reset-password``).
        recipient_name:   Nombre del destinatario para personalizar el saludo.
        challenge_id:     ID del challenge para construir el magic-link.
        expires_at:       ISO timestamp de expiración para el magic-link.
    """
    action = _TIPO_TO_ACTION.get(tipo, "login")

    background_tasks.add_task(
        _send_otp_email,
        to_email=email,
        otp_code=otp_code,
        action=action,
        recipient_name=recipient_name,
        challenge_id=challenge_id,
        expires_at=expires_at,
    )
