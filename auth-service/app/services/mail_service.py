"""
Auth Service — Mail service for sending OTP codes via SMTP.
Includes rich HTML email template (ported from Express API) with CID attachments.
"""

import aiosmtplib
import base64
import hashlib
import hmac
import json
import re
from datetime import datetime, timezone
from typing import Dict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from pathlib import Path

from app.core.config import settings

PNG_CACHE_PATH = Path(__file__).parent / "png_cache.json"
def _load_png_cache(path: Path) -> dict:
    if not path.exists():
        return {}

    candidate_encodings = ("utf-8", "utf-8-sig", "utf-16")
    for encoding in candidate_encodings:
        try:
            with open(path, "r", encoding=encoding) as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
                return {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        except OSError:
            return {}

    print(f"[MAIL WARN] Could not decode PNG cache: {path}")
    return {}

PNG_CACHE = _load_png_cache(PNG_CACHE_PATH)

# ===================== MAGIC-LINK TOKEN HELPERS =====================

def _sanitize_numeric_otp(raw: str) -> str:
    """Strip non-digit characters and return at most 6 digits."""
    return re.sub(r"\D", "", str(raw or ""))[:6]

def _to_base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

def create_otp_magic_link_token(
    challenge_id: str,
    otp_code: str,
    purpose: str = "login",
    expires_at: str = "",
) -> str:
    secret = (settings.OTP_LINK_SECRET or settings.OTP_HASH_SECRET).encode("utf-8")

    if expires_at:
        try:
            exp_ms = int(datetime.fromisoformat(expires_at).timestamp() * 1000)
        except (ValueError, TypeError):
            exp_ms = int((datetime.now(timezone.utc).timestamp() + 300) * 1000)
    else:
        exp_ms = int((datetime.now(timezone.utc).timestamp() + 300) * 1000)

    payload = {
        "challengeId": challenge_id,
        "otpCode": _sanitize_numeric_otp(otp_code),
        "purpose": purpose,
        "exp": exp_ms,
    }

    payload_encoded = _to_base64url(json.dumps(payload).encode("utf-8"))
    signature = hmac.new(secret, payload_encoded.encode("utf-8"), hashlib.sha256).digest()

    return f"{payload_encoded}.{_to_base64url(signature)}"

# ===================== EMAIL MASKING =====================

def mask_email(email: str) -> str:
    if not email or "@" not in email:
        return email

    local, domain = email.split("@", 1)
    local = local.strip()
    domain = domain.strip()

    if not local or not domain:
        return email

    if len(local) == 1:
        return f"*{local}@{domain}"
    if len(local) == 2:
        return f"{local[0]}*@{domain}"

    return f"{local[:2]}***{local[-1]}@{domain}"

# ===================== MAGIC LINK URL =====================

def build_verify_url(
    challenge_id: str,
    otp_code: str,
    purpose: str = "login",
    expires_at: str = "",
) -> str:
    if not challenge_id or not otp_code:
        return f"{settings.FRONTEND_URL.rstrip('/')}{settings.FRONTEND_LOGIN_PATH}"

    token = create_otp_magic_link_token(
        challenge_id=challenge_id,
        otp_code=otp_code,
        purpose=purpose,
        expires_at=expires_at,
    )

    base = settings.API_PUBLIC_URL.rstrip("/")
    return f"{base}/api/auth/verify-email-link?token={token}"

# ===================== HTML EMAIL TEMPLATE =====================

def _escape_html(value: str) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )

def _cid_img(key: str, width: int, height: int, alt: str = "") -> str:
    return f'<img src="cid:{key}@huerto" width="{width}" height="{height}" alt="{alt}" style="display:inline-block;vertical-align:middle;border:0;outline:none;" />'

def _normalize_action(action: str) -> str:
    normalized = str(action or "login").strip().lower().replace("_", "-")
    if normalized in {"registro", "register", "signup", "sign-up"}:
        return "registro"
    if normalized in {"reset-password", "recover", "recovery", "recuperacion", "password-reset"}:
        return "reset-password"
    return "login"

def _resolve_email_copy(action: str) -> Dict[str, str]:
    normalized = _normalize_action(action)

    if normalized == "registro":
        return {
            "subject": "Huerto Connect - Confirma tu registro",
            "title": "Confirma tu registro",
            "message_html": 'Usa el siguiente c&oacute;digo para activar tu cuenta en <strong style="color:#2E7D32;">Huerto Connect</strong>.',
            "warning_html": "Si no creaste esta cuenta, ignora este correo.",
            "button_text": "Activar cuenta",
            "header_badge": "Verificaci&oacute;n de registro de cuenta",
            "otp_section_label": "Parcela de verificaci&oacute;n",
            "otp_footer_legend": "cultivando seguridad",
            "security_notice_html": f"{_cid_img('shield', 18, 18)} <strong>Aviso de seguridad:</strong> Nunca compartas este c&oacute;digo OTP. Nuestro equipo no solicita este c&oacute;digo por chat, llamada o redes sociales.",
            "text_message": "Usa el siguiente codigo para activar tu cuenta en Huerto Connect.",
            "text_warning": "Si no creaste esta cuenta, ignora este correo.",
            "text_security_notice": "Aviso de seguridad: nunca compartas este codigo OTP.",
        }

    if normalized == "reset-password":
        return {
            "subject": "Huerto Connect - Cambia tu contrasena",
            "title": "Cambia tu contrasena",
            "message_html": 'Usa el siguiente c&oacute;digo para autorizar el <strong style="color:#2E7D32;">cambio de contrase&ntilde;a</strong> de tu cuenta en <strong style="color:#2E7D32;">Huerto Connect</strong>.',
            "warning_html": "Si no solicitaste este cambio de contrase&ntilde;a, ignora este correo y revisa la seguridad de tu cuenta.",
            "button_text": "Cambiar contrasena",
            "header_badge": "Restablecimiento de contrase&ntilde;a",
            "otp_section_label": "Parcela de recuperaci&oacute;n",
            "otp_footer_legend": "protegiendo tu cuenta digital",
            "security_notice_html": f"{_cid_img('shield', 18, 18)} <strong>Aviso de seguridad:</strong> Si no solicitaste este cambio de contrase&ntilde;a, ignora este correo y cambia tu contrase&ntilde;a desde un entorno seguro.",
            "text_message": "Usa el siguiente codigo para autorizar el cambio de contrasena de tu cuenta en Huerto Connect.",
            "text_warning": "Si no solicitaste este cambio de contrasena, ignora este correo y revisa la seguridad de tu cuenta.",
            "text_security_notice": "Aviso de seguridad: si no solicitaste este cambio de contrasena, ignora este correo y cambia tu contrasena desde un entorno seguro.",
        }

    return {
        "subject": "Huerto Connect - Verifica tu cuenta",
        "title": "Verifica tu cuenta",
        "message_html": 'Usa el siguiente c&oacute;digo para completar tu inicio de sesi&oacute;n en <strong style="color:#2E7D32;">Huerto Connect</strong>.',
        "warning_html": "Si no solicitaste este inicio de sesi&oacute;n, ignora este correo y protege tu cuenta.",
        "button_text": "Verificar acceso",
        "header_badge": "Verificaci&oacute;n de cuenta",
        "otp_section_label": "Parcela de verificaci&oacute;n",
        "otp_footer_legend": "cultivando seguridad",
        "security_notice_html": f"{_cid_img('shield', 18, 18)} <strong>Aviso de seguridad:</strong> Nunca compartas este c&oacute;digo OTP. Nuestro equipo no solicita este c&oacute;digo por chat, llamada o redes sociales.",
        "text_message": "Usa el siguiente codigo para completar tu inicio de sesion en Huerto Connect.",
        "text_warning": "Si no solicitaste este inicio de sesion, ignora este correo y protege tu cuenta.",
        "text_security_notice": "Aviso de seguridad: nunca compartas este codigo OTP.",
    }

def _build_otp_html(
    otp_code: str,
    action: str,
    recipient_name: str = "Usuario",
    expires_in_minutes: int = 5,
    verify_url: str = "",
) -> str:
    normalized_action = _normalize_action(action)
    copy = _resolve_email_copy(normalized_action)

    safe_name = _escape_html(recipient_name)
    safe_code = _escape_html(otp_code)

    otp_digits = "".join(f'<td align="center" style="padding:0 3px;"><div style="width:46px;height:58px;line-height:58px;text-align:center;font-size:28px;font-weight:800;font-family:\'Segoe UI\',Arial,sans-serif;color:#1565C0;background-color:#FFFFFF;border:2px solid #8D6E63;border-radius:10px;">{d}</div></td>' for d in safe_code)

    verification_button = ""
    if verify_url:
        safe_url = _escape_html(verify_url)
        verification_button = f"""<tr><td align="center" style="padding:6px 28px 24px 28px;"><a href="{safe_url}" style="display:inline-block;padding:15px 40px;border-radius:999px;background-color:#2E7D32;color:#FFFFFF;font-size:15px;font-weight:700;text-decoration:none;text-align:center;letter-spacing:0.4px;">{copy['button_text']}</a></td></tr>"""

    return f"""<!doctype html>
<html lang="es" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta http-equiv="X-UA-Compatible" content="IE=edge" />
    <title>{_escape_html(copy['subject'])}</title>
    <!--[if mso]>
    <noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript>
    <![endif]-->
    <style>
      body, table, td, p, a, li, blockquote {{ -ms-text-size-adjust:100%; -webkit-text-size-adjust:100%; }}
      table, td {{ mso-table-lspace:0pt; mso-table-rspace:0pt; }}
      img {{ -ms-interpolation-mode:bicubic; border:0; outline:none; text-decoration:none; }}
      @media only screen and (max-width: 640px) {{
        .wrapper-cell {{ padding: 10px !important; }}
        .card-main {{ border-radius: 16px !important; }}
        .content-cell {{ padding: 20px 16px !important; }}
        .title-text {{ font-size: 26px !important; }}
        .header-scene {{ height: auto !important; }}
        .otp-cell {{ padding: 16px 10px !important; }}
        .footer-cell {{ padding: 18px 16px !important; }}
      }}
    </style>
  </head>
  <body style="margin:0;padding:0;background-color:#e4ede2;font-family:'Segoe UI',Arial,Tahoma,Helvetica,sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#e4ede2;">
      <tr>
        <td align="center" class="wrapper-cell" style="padding:24px 14px;">
          <table role="presentation" width="640" cellspacing="0" cellpadding="0" border="0" class="card-main"
                 style="width:100%;max-width:640px;background-color:#FFFFFF;border-radius:22px;overflow:hidden;">
            <!-- ===== HEADER ===== -->
            <tr>
              <td style="padding:0;background-color:#2E7D32;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                  <tr>
                    <td style="padding:20px 28px 12px 28px;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                        <tr>
                          <td style="color:#FFFFFF;font-size:0;" valign="middle">
                            {_cid_img('logo', 44, 44, 'Huerto Connect')}
                            <span style="display:inline-block;vertical-align:middle;margin-left:10px;">
                              <span style="font-size:18px;font-weight:800;letter-spacing:0.5px;color:#FFFFFF;">HUERTO CONNECT</span><br/>
                              <span style="font-size:11px;font-weight:400;letter-spacing:0.8px;text-transform:uppercase;color:#C8E6C9;">Agricultura Inteligente</span>
                            </span>
                          </td>
                          <td align="right" valign="middle">
                            <span style="font-size:11px;font-weight:400;letter-spacing:0.6px;text-transform:uppercase;color:#C8E6C9;">
                              {copy['header_badge']}
                            </span>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                  <!-- Header scene -->
                  <tr>
                    <td style="padding:0;font-size:0;line-height:0;" class="header-scene">
                      {_cid_img('headerScene', 640, 200, 'Huerto Connect - Agricultura Inteligente')}
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <!-- ===== BODY ===== -->
            <tr>
              <td class="content-cell" style="padding:24px 28px 10px 28px;background-color:#F5F1E6;">
                <!-- Greeting card -->
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                  <tr>
                    <td style="padding:0;background-color:#FFFFFF;border:1px solid #d3c9b8;border-left:4px solid #2E7D32;border-radius:16px;overflow:hidden;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                        <tr>
                          <td width="60" valign="top" style="padding:0;">{_cid_img('cornerVineTL', 60, 60)}</td>
                          <td style="padding:18px 12px 18px 0;">
                            <p style="margin:0 0 6px 0;font-size:14px;font-weight:600;color:#2E7D32;">
                              {_cid_img('sprout', 20, 20)} Hola, {safe_name}
                            </p>
                            <h1 class="title-text" style="margin:0;color:#1a3a2a;font-size:30px;line-height:1.25;font-weight:800;">
                              {copy['title']}
                            </h1>
                          </td>
                          <td width="10" style="padding:0;"></td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                </table>
                <!-- Roots divider -->
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:14px 0 6px 0;">
                  <tr><td style="font-size:0;line-height:0;">{_cid_img('rootsDivider', 400, 30)}</td></tr>
                </table>
                <!-- Message card -->
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                  <tr>
                    <td style="padding:16px 20px;background-color:#FFFFFF;border:1px solid #d3c9b8;border-radius:14px;">
                      <p style="margin:0;color:#3a4e44;font-size:15px;line-height:1.65;">
                        {_cid_img('leaf', 18, 18)} {copy['message_html']}
                      </p>
                    </td>
                  </tr>
                </table>
                <!-- ===== OTP PARCELA ===== -->
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-top:18px;">
                  <tr>
                    <td class="otp-cell" align="center" style="padding:22px 18px;background-color:#F5F1E6;border:2px solid #8D6E63;border-radius:18px;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                        <tr>
                          <td align="left" style="font-size:12px;color:#6D4C41;font-weight:600;letter-spacing:0.5px;padding-bottom:4px;">
                            {_cid_img('wheat', 16, 16)} {copy['otp_section_label']}
                          </td>
                          <td align="right" style="font-size:12px;color:#6D4C41;padding-bottom:4px;">
                            {_cid_img('sprout', 20, 20)}
                          </td>
                        </tr>
                      </table>
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom:8px;">
                        <tr><td style="font-size:0;line-height:0;">{_cid_img('rootsDivider', 400, 30)}</td></tr>
                      </table>
                      <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:0 auto;">
                        <tr>
                          {otp_digits}
                        </tr>
                      </table>
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-top:10px;">
                        <tr><td style="font-size:0;line-height:0;">{_cid_img('rootsDivider', 400, 30)}</td></tr>
                      </table>
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-top:6px;">
                        <tr>
                          <td align="center" style="font-size:11px;color:#8D6E63;font-style:italic;">
                            {_cid_img('tree', 14, 14)} {copy['otp_footer_legend']} {_cid_img('tree', 14, 14)}
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                </table>
                <!-- Expiry card -->
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-top:16px;margin-bottom:6px;">
                  <tr>
                    <td style="background-color:#FFFFFF;border:1px solid #d3c9b8;border-radius:14px;border-left:4px solid #1565C0;overflow:hidden;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                        <tr>
                          <td style="padding:14px 18px;">
                            <p style="margin:0 0 5px 0;color:#2f4f43;font-size:14px;line-height:1.55;">
                              {_cid_img('clock', 16, 16)} Este c&oacute;digo expirar&aacute; en <strong style="color:#1565C0;">{expires_in_minutes} minutos</strong>.
                            </p>
                            <p style="margin:0;color:#5a6d64;font-size:13px;line-height:1.55;">
                              {copy['warning_html']}
                            </p>
                          </td>
                          <td width="60" valign="bottom" style="padding:0;">{_cid_img('cornerVineBR', 60, 60)}</td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <!-- ===== VERIFICATION BUTTON ===== -->
            {verification_button}
            <!-- ===== SECURITY NOTICE ===== -->
            <tr>
              <td style="padding:8px 28px 0 28px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                  <tr>
                    <td style="padding:14px 18px;background-color:#FFF8E1;border:1px solid #FFE082;border-radius:12px;border-left:4px solid #FFA000;">
                      <p style="margin:0;color:#5D4037;font-size:13px;line-height:1.55;">
                        {copy['security_notice_html']}
                      </p>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <!-- ===== FOOTER ===== -->
            <tr>
              <td class="footer-cell" style="padding:24px 28px;background-color:#143f37;color:#FFFFFF;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                  <tr>
                    <td style="padding-bottom:10px;">
                      <span style="font-size:16px;font-weight:800;letter-spacing:0.4px;color:#FFFFFF;">{_cid_img('sprout', 20, 20)} Huerto Connect</span>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding-bottom:14px;">
                      <span style="font-size:12px;color:#A5D6A7;letter-spacing:0.6px;">Tecnolog&iacute;a para agricultura inteligente</span>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding-bottom:14px;font-size:13px;line-height:1.7;">
                      <a href="mailto:huertoconnect@gmail.com" style="color:#81D4FA;text-decoration:none;font-weight:600;">Contacto</a>
                      <span style="color:#4a7a5e;margin:0 6px;">&bull;</span>
                      <a href="https://huertoconnect.com/seguridad" style="color:#81D4FA;text-decoration:none;font-weight:600;">Seguridad</a>
                      <span style="color:#4a7a5e;margin:0 6px;">&bull;</span>
                      <a href="https://huertoconnect.com/soporte" style="color:#81D4FA;text-decoration:none;font-weight:600;">Soporte</a>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding-bottom:12px;border-top:1px solid rgba(255,255,255,0.1);font-size:0;line-height:0;height:1px;">&nbsp;</td>
                  </tr>
                  <tr>
                    <td style="font-size:11px;line-height:1.6;color:rgba(255,255,255,0.7);">
                      {_cid_img('leaf', 18, 18)} Crecimiento &bull; {_cid_img('wheat', 16, 16)} Naturaleza &bull; {_cid_img('tree', 14, 14)} Huerto &bull; {_cid_img('shield', 18, 18)} Seguridad
                    </td>
                  </tr>
                  <tr>
                    <td style="padding-top:6px;font-size:10px;color:rgba(255,255,255,0.45);">
                      &copy; {datetime.now(timezone.utc).year} Huerto Connect. Todos los derechos reservados.
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""

def _build_otp_text(
    otp_code: str,
    action: str,
    recipient_name: str,
    expires_in_minutes: int,
) -> str:
    copy = _resolve_email_copy(action)
    safe_name = recipient_name or "Usuario"

    lines = [
        copy["subject"],
        "-------------------------------------------",
        "",
        f"Hola {safe_name},",
        "",
        copy["text_message"],
        "",
        f"Codigo OTP: {otp_code}",
        "",
        f"Este codigo expirara en {expires_in_minutes} minutos.",
        "",
        copy["text_warning"],
        "",
        copy["text_security_notice"],
        "Nuestro equipo no solicita este codigo por chat, llamada o redes sociales.",
        "",
        "-------------------------------------------",
        "Huerto Connect - Tecnologia para agricultura inteligente",
        "Contacto: huertoconnect@gmail.com",
        "Seguridad: https://huertoconnect.com/seguridad",
        "Soporte: https://huertoconnect.com/soporte",
    ]

    return "\n".join(lines)


# ===================== SEND OTP EMAIL =====================

async def send_otp_email(
    to_email: str,
    otp_code: str,
    action: str = "login",
    recipient_name: str = "",
    challenge_id: str = "",
    expires_at: str = "",
) -> bool:
    action = _normalize_action(action)

    if not recipient_name:
        local = to_email.split("@")[0] if "@" in to_email else to_email
        recipient_name = local.replace(".", " ").replace("_", " ").replace("-", " ").title()

    verify_url = ""
    if challenge_id:
        verify_url = build_verify_url(
            challenge_id=challenge_id,
            otp_code=otp_code,
            purpose=action,
            expires_at=expires_at,
        )

    if settings.OTP_DELIVERY_MODE != "smtp":
        print(f"[MAIL] OTP for {to_email}: {otp_code} (delivery mode: {settings.OTP_DELIVERY_MODE})")
        if verify_url:
            print(f"[MAIL] Magic link: {verify_url}")
        return True

    try:
        html_body = _build_otp_html(
            otp_code=otp_code,
            action=action,
            recipient_name=recipient_name,
            expires_in_minutes=settings.OTP_EXPIRATION_MINUTES,
            verify_url=verify_url,
        )

        copy = _resolve_email_copy(action)
        subject = copy["subject"]

        msg = MIMEMultipart("alternative")
        msg["From"] = f"Huerto Connect <{settings.SMTP_USER}>"
        msg["To"] = to_email
        msg["Subject"] = subject

        plain = _build_otp_text(
            otp_code=otp_code,
            action=action,
            recipient_name=recipient_name,
            expires_in_minutes=settings.OTP_EXPIRATION_MINUTES,
        )
        msg.attach(MIMEText(plain, "plain", "utf-8"))

        msg_html = MIMEMultipart("related")
        msg_html.attach(MIMEText(html_body, "html", "utf-8"))

        for key, b64_str in PNG_CACHE.items():
            img_data = base64.b64decode(b64_str)
            img = MIMEImage(img_data, _subtype="png")
            img.add_header("Content-ID", f"<{key}@huerto>")
            img.add_header("X-Attachment-Id", f"{key}@huerto")
            img.add_header("Content-Disposition", "inline", filename=f"{key}.png")
            msg_html.attach(img)

        msg.attach(msg_html)

        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            use_tls=settings.SMTP_SECURE,
            username=settings.SMTP_USER,
            password=settings.SMTP_APP_PASSWORD,
        )
        print(f"[MAIL] OTP sent to {to_email}")
        return True
    except Exception as e:
        print(f"[MAIL ERROR] Failed to send OTP to {to_email}: {e}")
        return False
