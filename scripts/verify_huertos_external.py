"""Explicit real-provider smoke. Never uses a real user's profile or database."""
import argparse
from pathlib import Path
import smtplib
import ssl
import sys
from email.message import EmailMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.config import settings


def smtp_check(recipient=None):
    if not settings.SMTP_USER or not settings.SMTP_APP_PASSWORD:
        raise RuntimeError("SMTP no configurado")
    context = ssl.create_default_context()
    cls = smtplib.SMTP_SSL if settings.SMTP_SECURE else smtplib.SMTP
    options = {"timeout": 20}
    if settings.SMTP_SECURE:
        options["context"] = context
    with cls(settings.SMTP_HOST, settings.SMTP_PORT, **options) as client:
        if not settings.SMTP_SECURE:
            client.ehlo()
            client.starttls(context=context)
            client.ehlo()
        client.login(settings.SMTP_USER, settings.SMTP_APP_PASSWORD)
        print("SMTP: autenticación TLS correcta")
        if recipient:
            message = EmailMessage()
            message["From"] = settings.SMTP_USER
            message["To"] = recipient
            message["Subject"] = "Huerto Connect: prueba autorizada de correo"
            message.set_content("Esta es una prueba técnica autorizada de Huerto Connect. No contiene códigos de acceso ni requiere ninguna acción.")
            refused = client.send_message(message)
            if refused:
                raise RuntimeError("Destinatario rechazado")
            print("SMTP: mensaje aceptado por el servidor; confirmar recepción con el destinatario")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smtp", action="store_true")
    parser.add_argument("--to", help="Destinatario autorizado; sin esta opción SMTP solo autentica")
    args = parser.parse_args()
    try:
        if args.smtp:
            smtp_check(args.to)
    except Exception as exc:
        print("Verificación fallida:", type(exc).__name__)
        sys.exit(1)
