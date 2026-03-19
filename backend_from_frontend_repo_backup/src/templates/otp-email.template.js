function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function buildOtpEmailTemplate({ recipientName, otpCode, expiresInMinutes, verifyUrl }) {
  const safeName = recipientName ? escapeHtml(recipientName) : 'Usuario';
  const safeCode = escapeHtml(otpCode);
  const safeVerifyUrl = verifyUrl ? escapeHtml(verifyUrl) : '';
  const verificationButton = safeVerifyUrl
    ? `
      <tr>
        <td align="center" style="padding: 0 32px 24px 32px;">
          <a href="${safeVerifyUrl}" style="display:inline-block;background:#0d6b9f;color:#ffffff;text-decoration:none;font-size:15px;font-weight:700;line-height:1;padding:14px 26px;border-radius:999px;">
            Abrir Huerto Connect
          </a>
        </td>
      </tr>`
    : '';

  const html = `<!doctype html>
<html lang="es">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Verifica tu cuenta - Huerto Connect</title>
    <style>
      @media only screen and (max-width: 640px) {
        .email-card {
          border-radius: 0 !important;
        }
        .content-cell {
          padding-left: 20px !important;
          padding-right: 20px !important;
        }
        .otp-code {
          font-size: 34px !important;
          letter-spacing: 10px !important;
        }
      }
    </style>
  </head>
  <body style="margin:0;padding:0;background-color:#edf3ee;font-family:Arial,'Segoe UI',Tahoma,sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#edf3ee;">
      <tr>
        <td align="center" style="padding:24px 12px;">
          <table role="presentation" width="640" cellspacing="0" cellpadding="0" border="0" class="email-card" style="width:100%;max-width:640px;background:#ffffff;border-radius:18px;overflow:hidden;box-shadow:0 14px 38px rgba(18,67,44,0.18);">
            <tr>
              <td style="padding:24px 32px;background:linear-gradient(135deg,#1b7a48 0%,#155f8f 58%,#7b5a33 100%);color:#ffffff;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                  <tr>
                    <td style="font-size:14px;font-weight:700;letter-spacing:0.6px;text-transform:uppercase;">
                      Huerto Connect
                    </td>
                    <td align="right">
                      <span style="display:inline-block;width:42px;height:42px;border-radius:50%;background:rgba(255,255,255,0.22);text-align:center;line-height:42px;font-size:22px;">🔐</span>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td class="content-cell" style="padding:32px;">
                <p style="margin:0 0 10px 0;color:#2f4738;font-size:14px;">Hola, ${safeName}</p>
                <h1 style="margin:0 0 12px 0;color:#123c2b;font-size:32px;line-height:1.2;font-weight:800;">
                  Verifica tu cuenta
                </h1>
                <p style="margin:0 0 20px 0;color:#35584a;font-size:15px;line-height:1.6;">
                  Usa este código para completar el inicio de sesión en Huerto Connect. Por seguridad, el código es de un solo uso.
                </p>
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 18px 0;">
                  <tr>
                    <td align="center" style="border:1px solid #d4e8dd;border-radius:14px;background:linear-gradient(135deg,#f7fcf8 0%,#edf4f8 55%,#f8f1ea 100%);padding:18px;">
                      <div class="otp-code" style="font-size:44px;letter-spacing:14px;color:#155c89;font-weight:800;line-height:1;">
                        ${safeCode}
                      </div>
                    </td>
                  </tr>
                </table>
                <p style="margin:0 0 6px 0;color:#35584a;font-size:14px;">
                  Este código expira en <strong>${expiresInMinutes} minutos</strong>.
                </p>
                <p style="margin:0 0 24px 0;color:#35584a;font-size:14px;">
                  Si no solicitaste este acceso, ignora este correo y cambia tu contraseña.
                </p>
              </td>
            </tr>
            ${verificationButton}
            <tr>
              <td style="padding:20px 32px;background:#f7faf8;border-top:1px solid #e1ece6;">
                <p style="margin:0 0 4px 0;color:#2b4f3f;font-size:13px;font-weight:700;">Huerto Connect</p>
                <p style="margin:0 0 4px 0;font-size:12px;color:#4d665b;">
                  Contacto:
                  <a href="mailto:huertoconnect@gmail.com" style="color:#155f8f;text-decoration:none;">huertoconnect@gmail.com</a>
                  &nbsp;|&nbsp;
                  <a href="https://huertoconnect.com" style="color:#155f8f;text-decoration:none;">huertoconnect.com</a>
                </p>
                <p style="margin:0;font-size:11px;line-height:1.5;color:#657f73;">
                  Aviso de seguridad: nunca compartas este código OTP con terceros. El equipo de Huerto Connect nunca solicitará este código por chat o llamada.
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>`;

  const text = [
    'Huerto Connect - Verifica tu cuenta',
    '',
    `Hola ${safeName},`,
    '',
    `Tu código OTP para completar el inicio de sesión es: ${otpCode}`,
    `Este código expira en ${expiresInMinutes} minutos.`,
    '',
    'Si no solicitaste este acceso, ignora este correo y cambia tu contraseña.',
    '',
    'Contacto: huertoconnect@gmail.com'
  ].join('\n');

  return {
    subject: 'Huerto Connect - Verifica tu cuenta',
    html,
    text
  };
}

module.exports = {
  buildOtpEmailTemplate
};
