"""
Auth Service — Mail service for sending OTP codes via SMTP.
Includes rich HTML email template (ported from Express API) and magic-link support.
"""

import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urlencode

from shared.auth.security import create_otp_magic_link_token
from shared.config import settings


# ===================== EMAIL MASKING =====================

def mask_email(email: str) -> str:
    """Mask email for security, matches Express implementation."""
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
    """Build a magic-link verification URL — mirrors Express buildVerifyUrl()."""
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
    """Escape HTML special characters."""
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _build_otp_html(
    otp_code: str,
    action: str,
    recipient_name: str = "Usuario",
    expires_in_minutes: int = 5,
    verify_url: str = "",
) -> str:
    """
    Build rich HTML email template for OTP.
    Adapted from the Express otp-email.template.js — uses inline SVG instead of
    CID attachments for simpler deployment (no sharp dependency needed).
    """
    is_registro = action == "registro"
    is_reset = action in ("reset_password", "reset-password")

    safe_name = _escape_html(recipient_name)
    safe_code = _escape_html(otp_code)

    # --- Dynamic text based on purpose ---
    if is_registro:
        email_subject = "Huerto Connect - Confirma tu registro"
        email_title = "Confirma tu registro"
        email_message = 'Usa el siguiente c&oacute;digo para activar tu cuenta en <strong style="color:#2E7D32;">Huerto Connect</strong>.'
        email_warning = "Si no creaste esta cuenta, ignora este correo."
        button_text = "Activar cuenta"
    elif is_reset:
        email_subject = "Huerto Connect - Cambia tu contrasena"
        email_title = "Cambia tu contrasena"
        email_message = 'Usa el siguiente c&oacute;digo para autorizar el <strong style="color:#2E7D32;">cambio de contrase&ntilde;a</strong> de tu cuenta.'
        email_warning = "Si no solicitaste este cambio, ignora este correo y revisa la seguridad de tu cuenta."
        button_text = "Cambiar contrasena"
    else:
        email_subject = "Huerto Connect - Verifica tu cuenta"
        email_title = "Verifica tu cuenta"
        email_message = 'Usa el siguiente c&oacute;digo para completar tu inicio de sesi&oacute;n en <strong style="color:#2E7D32;">Huerto Connect</strong>.'
        email_warning = "Si no solicitaste este acceso, ignora este correo y protege tu cuenta."
        button_text = "Verificar acceso"

    security_notice = (
        "<strong>Aviso de seguridad:</strong> Si no solicitaste este cambio, ignora este correo."
        if is_reset else
        "<strong>Aviso de seguridad:</strong> Nunca compartas este c&oacute;digo OTP. Nuestro equipo no solicita este c&oacute;digo por chat, llamada o redes sociales."
    )

    # --- OTP digits as styled boxes ---
    otp_digits = "".join(
        f'<td align="center" style="padding:0 3px;">'
        f'<div style="width:46px;height:58px;line-height:58px;text-align:center;font-size:28px;font-weight:800;'
        f"font-family:'Segoe UI',Arial,sans-serif;color:#1565C0;background-color:#FFFFFF;"
        f'border:2px solid #8D6E63;border-radius:10px;">{d}</div></td>'
        for d in safe_code
    )

    # --- Verification button (if magic-link URL available) ---
    verification_button = ""
    if verify_url:
        safe_url = _escape_html(verify_url)
        verification_button = f"""
        <tr>
          <td align="center" style="padding:6px 28px 24px 28px;">
            <a href="{safe_url}" style="display:inline-block;padding:15px 40px;border-radius:999px;
               background-color:#2E7D32;color:#FFFFFF;font-size:15px;font-weight:700;
               text-decoration:none;text-align:center;letter-spacing:0.4px;">
              {button_text}
            </a>
          </td>
        </tr>"""

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{_escape_html(email_subject)}</title>
  <style>
    body, table, td, p, a {{ -ms-text-size-adjust:100%; -webkit-text-size-adjust:100%; }}
    table, td {{ mso-table-lspace:0pt; mso-table-rspace:0pt; }}
    @media only screen and (max-width: 640px) {{
      .wrapper-cell {{ padding: 10px !important; }}
      .card-main {{ border-radius: 16px !important; }}
      .content-cell {{ padding: 20px 16px !important; }}
      .title-text {{ font-size: 26px !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background-color:#e4ede2;font-family:'Segoe UI',Arial,Tahoma,Helvetica,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#e4ede2;">
    <tr>
      <td align="center" class="wrapper-cell" style="padding:24px 14px;">
        <table role="presentation" width="640" cellspacing="0" cellpadding="0" border="0" class="card-main"
               style="width:100%;max-width:640px;background-color:#FFFFFF;border-radius:22px;overflow:hidden;">

          <!-- HEADER -->
          <tr>
            <td style="padding:20px 28px;background-color:#2E7D32;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td style="color:#FFFFFF;" valign="middle">
                    <span style="font-size:18px;font-weight:800;letter-spacing:0.5px;color:#FFFFFF;">
                      &#127807; HUERTO CONNECT
                    </span><br/>
                    <span style="font-size:11px;font-weight:400;letter-spacing:0.8px;text-transform:uppercase;color:#C8E6C9;">
                      Agricultura Inteligente
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- BODY -->
          <tr>
            <td class="content-cell" style="padding:24px 28px 10px 28px;background-color:#F5F1E6;">

              <!-- Greeting -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td style="padding:18px 20px;background-color:#FFFFFF;border:1px solid #d3c9b8;border-left:4px solid #2E7D32;border-radius:16px;">
                    <p style="margin:0 0 6px 0;font-size:14px;font-weight:600;color:#2E7D32;">
                      &#127793; Hola, {safe_name}
                    </p>
                    <h1 class="title-text" style="margin:0;color:#1a3a2a;font-size:30px;line-height:1.25;font-weight:800;">
                      {email_title}
                    </h1>
                  </td>
                </tr>
              </table>

              <!-- Message -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-top:16px;">
                <tr>
                  <td style="padding:16px 20px;background-color:#FFFFFF;border:1px solid #d3c9b8;border-radius:14px;">
                    <p style="margin:0;color:#3a4e44;font-size:15px;line-height:1.65;">
                      &#127811; {email_message}
                    </p>
                  </td>
                </tr>
              </table>

              <!-- OTP CODE -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-top:18px;">
                <tr>
                  <td align="center" style="padding:22px 18px;background-color:#F5F1E6;border:2px solid #8D6E63;border-radius:18px;">
                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:0 auto;">
                      <tr>{otp_digits}</tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- Expiry -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-top:16px;margin-bottom:6px;">
                <tr>
                  <td style="padding:14px 18px;background-color:#FFFFFF;border:1px solid #d3c9b8;border-radius:14px;border-left:4px solid #1565C0;">
                    <p style="margin:0 0 5px 0;color:#2f4f43;font-size:14px;line-height:1.55;">
                      &#9203; Este c&oacute;digo expirar&aacute; en <strong style="color:#1565C0;">{expires_in_minutes} minutos</strong>.
                    </p>
                    <p style="margin:0;color:#5a6d64;font-size:13px;line-height:1.55;">
                      {email_warning}
                    </p>
                  </td>
                </tr>
              </table>

            </td>
          </tr>

          <!-- VERIFICATION BUTTON -->
          {verification_button}

          <!-- SECURITY NOTICE -->
          <tr>
            <td style="padding:8px 28px 0 28px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td style="padding:14px 18px;background-color:#FFF8E1;border:1px solid #FFE082;border-radius:12px;border-left:4px solid #FFA000;">
                    <p style="margin:0;color:#5D4037;font-size:13px;line-height:1.55;">
                      &#128737; {security_notice}
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- FOOTER -->
          <tr>
            <td style="padding:24px 28px;background-color:#143f37;color:#FFFFFF;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td style="padding-bottom:10px;">
                    <span style="font-size:16px;font-weight:800;letter-spacing:0.4px;color:#FFFFFF;">&#127793; Huerto Connect</span>
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
                  <td style="padding-top:6px;font-size:10px;color:rgba(255,255,255,0.45);">
                    &copy; 2026 Huerto Connect. Todos los derechos reservados.
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


# ===================== SEND OTP EMAIL =====================

async def send_otp_email(
    to_email: str,
    otp_code: str,
    action: str = "login",
    recipient_name: str = "",
    challenge_id: str = "",
    expires_at: str = "",
) -> bool:
    """
    Send OTP email via SMTP with magic-link button.
    Returns True if sent successfully, False otherwise.
    """
    # Build display name
    if not recipient_name:
        local = to_email.split("@")[0] if "@" in to_email else to_email
        recipient_name = local.replace(".", " ").replace("_", " ").replace("-", " ").title()

    # Build magic-link verify URL
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
            verify_url=verify_url,
        )

        # Subject
        if action == "registro":
            subject = "Huerto Connect - Confirma tu registro"
        elif action in ("reset_password", "reset-password"):
            subject = "Huerto Connect - Cambia tu contrasena"
        else:
            subject = "Huerto Connect - Verifica tu cuenta"

        msg = MIMEMultipart("alternative")
        msg["From"] = f"Huerto Connect <{settings.SMTP_USER}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        # Plain text fallback
        plain = (
            f"Hola {recipient_name},\n\n"
            f"Tu codigo de verificacion es: {otp_code}\n"
            f"Este codigo expira en {settings.OTP_EXPIRATION_MINUTES} minutos.\n\n"
            f"Huerto Connect"
        )
        msg.attach(MIMEText(plain, "plain", "utf-8"))

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
