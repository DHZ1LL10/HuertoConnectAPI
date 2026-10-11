"""Python-only SMTP delivery and responsive transactional email."""
import logging
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, formatdate
from html import escape
from urllib.parse import urlparse
import aiosmtplib
from app.core.config import settings

logger = logging.getLogger(__name__)

class MailDeliveryError(RuntimeError):
    pass

def mask_email(email):
    local, _, domain = email.partition("@")
    return f"{local[:2]}***@{domain}" if domain else "***"

def _normalize_action(action):
    if action in {"registro", "register"}:
        return "registro"
    return "reset-password" if action in {"reset-password", "reset_password", "recuperacion"} else "login"

def _resolve_email_copy(action):
    return {
        "registro": {"subject": "Tu cuenta está por florecer · Huerto Connect", "title": "Bienvenido a tu huerto.", "message": "Confirma tu correo para empezar a cultivar con nosotros.", "label": "CONFIRMA TU REGISTRO"},
        "login": {"subject": "Tu código de acceso · Huerto Connect", "title": "Qué bueno verte de nuevo.", "message": "Usa este código para completar tu inicio de sesión.", "label": "ACCESO SEGURO"},
        "reset-password": {"subject": "Recupera tu acceso · Huerto Connect", "title": "Volvamos a conectar.", "message": "Usa este código para autorizar el cambio de tu contraseña.", "label": "RECUPERACIÓN DE CUENTA"},
    }[_normalize_action(action)]

def build_verify_url(challenge_id="", otp_code="", purpose="login", expires_at=""):
    # Links open the client only. GET requests from mail scanners must never consume OTPs.
    return f"{settings.FRONTEND_URL.rstrip('/')}/{settings.FRONTEND_LOGIN_PATH.lstrip('/')}"

def _build_otp_html(otp_code, action, recipient_name="Usuario", expires_in_minutes=5, verify_url=""):
    copy = _resolve_email_copy(action)
    name = escape(recipient_name or "Usuario")
    code = escape(otp_code)
    digits = "".join(f'<td style="padding:0 3px"><span style="display:block;border:1px solid #c99d80;border-radius:9px;background:#fff;padding:12px 8px;font:700 27px Courier New,monospace;color:#235943">{escape(digit)}</span></td>' for digit in otp_code)
    roots = '<img src="cid:huerto-raices" width="460" alt="" style="display:block;width:100%;max-width:460px;height:auto" />'
    button = ""
    if verify_url and urlparse(verify_url).scheme in {"http", "https"}:
        button = f'<p style="margin:26px 0;text-align:center"><a href="{escape(verify_url, quote=True)}" style="display:inline-block;background:#2c783b;color:#fff;padding:16px 30px;border-radius:24px;text-decoration:none;font-size:14px;font-weight:700">Continuar a Huerto Connect &rarr;</a></p>'
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(copy['subject'])}</title>
<style>@media(max-width:600px){{.outer{{padding:16px 8px!important}}.inner{{padding:24px 18px!important}}.heading{{font-size:27px!important}}}}</style></head>
<body background="cid:huerto-marco" style="margin:0;background-color:#315726;background-image:url('cid:huerto-marco');background-repeat:repeat;background-size:560px 900px;font-family:Arial,Helvetica,sans-serif;color:#214332">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">Tu código de un solo uso expira en {expires_in_minutes} minutos.</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td class="outer" align="center" style="padding:40px 12px">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="width:100%;max-width:560px;border:1px solid #d1d8c4;border-radius:20px;background:#faf7ef;overflow:hidden">
<tr><td style="padding:24px 30px;background:#294d22;border-bottom:1px solid #779653;color:#fff">
<p style="margin:0;font-size:22px;font-weight:800;letter-spacing:1px">HUERTO <span style="color:#d8e7b3">CONNECT</span></p>
<p style="margin:7px 0 0;font-size:10px;letter-spacing:2px;color:#d2e1cb">AGRICULTURA INTELIGENTE · CONEXIONES QUE CRECEN</p></td></tr>
<tr><td align="center" style="background:#3f6b22;padding:12px 10px 25px">
<img src="cid:huerto-maceta" width="520" alt="Una planta en maceta con raíces que se extienden" style="display:block;width:100%;max-width:520px;height:auto">
<p style="margin:0;font-size:10px;letter-spacing:2px;color:#e4ecca">CADA CONEXIÓN EMPIEZA CON UNA RAÍZ</p></td></tr>
<tr><td class="inner" background="cid:huerto-marco" style="padding:28px 30px;background-color:#315726;background-image:url('cid:huerto-marco');background-repeat:repeat-y;background-position:top center;background-size:100% auto">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td style="padding:22px;background:#fff;border:1px solid #d6d7c4;border-left:4px solid #73964e;border-radius:12px">
<p style="margin:0 0 12px;color:#73904f;font-size:10px;font-weight:700;letter-spacing:1.5px">{copy['label']}</p>
<h1 class="heading" style="margin:0;font-size:30px;line-height:1.2;color:#234936">{copy['title']}</h1>
<p style="margin:16px 0 0;font-size:14px;line-height:1.6">Hola, <strong>{name}</strong>.<br>{copy['message']}</p></td></tr></table>
{roots}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eeefdf;border:1px solid #ba9a7f;border-radius:15px"><tr><td align="center" style="padding:22px 12px">
<p style="margin:0 0 17px;font-size:10px;letter-spacing:1.5px;color:#796146">TU PARCELA DE VERIFICACIÓN</p>
<table role="presentation" aria-label="Código {code}" cellpadding="0" cellspacing="0" style="margin:auto"><tr>{digits}</tr></table>
{roots}
<p style="margin:5px 0 0;font-size:12px;color:#657249">Válido durante <strong>{expires_in_minutes} minutos</strong> · Un solo uso</p>
</td></tr></table>
{button}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td style="padding:15px 18px;background:#fff9e6;border:1px solid #e3cc8d;border-left:4px solid #d4ad55;border-radius:10px">
<p style="margin:0;font-size:12px;font-weight:700;color:#795e2b">Cuidamos tus raíces y tu seguridad</p>
<p style="margin:7px 0 0;font-size:12px;line-height:1.7;color:#776b50">No compartas este código. Nunca te lo pediremos por teléfono o chat. Si no solicitaste esta acción, puedes ignorar este correo.</p></td></tr></table>
{roots}
</td></tr>
<tr><td style="padding:25px 30px;background:#244322;border-top:3px solid #a9bf84">
<p style="margin:0;font-size:16px;font-weight:700;color:#d5e6c6">Cultivamos confianza, desde la raíz.</p>
<p style="margin:9px 0 0;font-size:11px;line-height:1.7;color:#b2cbb7">Pequeños cuidados. Grandes cosechas.<br>© {datetime.now(timezone.utc).year} Huerto Connect · Correo automático de seguridad</p>
</td></tr></table></td></tr></table></body></html>"""


def preview_otp_html(*args, embed=True, **kwargs):
    """Self-contained preview; email uses standard embedded MIME images instead."""
    import base64
    from pathlib import Path
    html = _build_otp_html(*args, **kwargs)
    for cid, filename in (("huerto-maceta", "maceta_raices.png"), ("huerto-raices", "raices.png"), ("huerto-marco", "raices_marco.png")):
        if not embed:
            html = html.replace("cid:" + cid, "../auth-service/app/assets/" + filename)
            continue
        data = (Path(__file__).resolve().parents[1] / "assets" / filename).read_bytes()
        html = html.replace("cid:" + cid, "data:image/png;base64," + base64.b64encode(data).decode())
    return html

def _build_otp_text(otp_code, action, recipient_name, expires_in_minutes):
    copy = _resolve_email_copy(action)
    return f"{copy['subject']}\n\nHola, {recipient_name or 'Usuario'}.\n{copy['message']}\n\nCódigo: {otp_code}\nExpira en {expires_in_minutes} minutos. Un solo uso.\n\nNo compartas este código. Si no lo solicitaste, ignora este correo."

async def send_otp_email(to_email, otp_code, action="login", recipient_name="", challenge_id="", expires_at=""):
    if settings.OTP_DELIVERY_MODE == "console":
        if settings.ENVIRONMENT == "production":
            raise MailDeliveryError("SMTP requerido")
        logger.info("otp_delivery_skipped development_mode=true")
        return True
    if not settings.SMTP_USER or not settings.SMTP_APP_PASSWORD:
        raise MailDeliveryError("SMTP no configurado")
    msg = EmailMessage()
    msg["From"] = formataddr(("Huerto Connect", settings.MAIL_FROM or settings.SMTP_USER))
    msg["To"] = to_email
    msg["Subject"] = _resolve_email_copy(action)["subject"]
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid()
    minutes = settings.OTP_EXPIRATION_MINUTES
    msg.set_content(_build_otp_text(otp_code, action, recipient_name, minutes))
    msg.add_alternative(_build_otp_html(otp_code, action, recipient_name, minutes, build_verify_url()), subtype="html")
    from pathlib import Path
    for cid, filename in (("huerto-maceta", "maceta_raices.png"), ("huerto-raices", "raices.png"), ("huerto-marco", "raices_marco.png")):
        data = (Path(__file__).resolve().parents[1] / "assets" / filename).read_bytes()
        msg.get_body(preferencelist=("html",)).add_related(data, maintype="image", subtype="png", cid="<" + cid + ">", disposition="inline")
    try:
        await aiosmtplib.send(msg, hostname=settings.SMTP_HOST, port=settings.SMTP_PORT,
            use_tls=settings.SMTP_SECURE, start_tls=not settings.SMTP_SECURE,
            username=settings.SMTP_USER, password=settings.SMTP_APP_PASSWORD,
            timeout=settings.SMTP_TIMEOUT_SECONDS)
    except (aiosmtplib.SMTPException, OSError, TimeoutError) as exc:
        logger.error("otp_delivery_failed error=%s", type(exc).__name__)
        raise MailDeliveryError("No se pudo entregar el correo") from exc
    logger.info("otp_delivered")
    return True
