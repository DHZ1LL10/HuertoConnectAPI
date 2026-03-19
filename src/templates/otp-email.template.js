const sharp = require('sharp');

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

/* Cache converted PNGs so we don't re-render on every email */
const pngCache = new Map();

/* ─────────────────────────────────────────────────────────
   SVG sources as raw strings – will be attached via CID
   ───────────────────────────────────────────────────────── */

const SVG_SOURCES = {
  logo: `<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 44 44">
<circle cx="22" cy="22" r="21" fill="white" opacity="0.15"/>
<path d="M22,8 Q32,10 34,20 Q36,30 26,36 Q20,28 18,22 Q16,16 22,8Z" fill="#A5D6A7" opacity="0.9"/>
<path d="M22,8 Q28,14 28,22 Q28,30 26,36" fill="none" stroke="white" stroke-width="1.5" opacity="0.8"/>
<path d="M24,16 L30,16" stroke="white" stroke-width="1" opacity="0.6"/>
<path d="M25,22 L32,22" stroke="white" stroke-width="1" opacity="0.6"/>
<path d="M24,28 L28,28" stroke="white" stroke-width="1" opacity="0.6"/>
<circle cx="30" cy="16" r="1.5" fill="white" opacity="0.5"/>
<circle cx="32" cy="22" r="1.5" fill="white" opacity="0.5"/>
<circle cx="28" cy="28" r="1.5" fill="white" opacity="0.5"/>
</svg>`,

  headerScene: `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="200" viewBox="0 0 640 200">
<defs>
<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#0D47A1"/><stop offset="35%" stop-color="#1565C0"/><stop offset="65%" stop-color="#42A5F5"/><stop offset="100%" stop-color="#90CAF9"/></linearGradient>
<linearGradient id="hill1" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#66BB6A"/><stop offset="100%" stop-color="#2E7D32"/></linearGradient>
<linearGradient id="hill2" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#43A047"/><stop offset="100%" stop-color="#1B5E20"/></linearGradient>
<linearGradient id="hill3" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#388E3C"/><stop offset="100%" stop-color="#1B5E20"/></linearGradient>
<linearGradient id="soil" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#6D4C41"/><stop offset="100%" stop-color="#4E342E"/></linearGradient>
<radialGradient id="sunGlow" cx="0.5" cy="0.5" r="0.5"><stop offset="0%" stop-color="#FFF9C4" stop-opacity="1"/><stop offset="40%" stop-color="#FFF176" stop-opacity="0.8"/><stop offset="70%" stop-color="#FFEE58" stop-opacity="0.3"/><stop offset="100%" stop-color="#FFD54F" stop-opacity="0"/></radialGradient>
</defs>
<rect width="640" height="200" fill="url(#sky)"/>
<circle cx="540" cy="48" r="50" fill="url(#sunGlow)"/>
<g stroke="#FFF176" stroke-width="1.5" opacity="0.5">
<line x1="540" y1="10" x2="540" y2="22"/><line x1="540" y1="74" x2="540" y2="86"/>
<line x1="502" y1="48" x2="514" y2="48"/><line x1="566" y1="48" x2="578" y2="48"/>
<line x1="513" y1="21" x2="521" y2="29"/><line x1="559" y1="67" x2="567" y2="75"/>
<line x1="567" y1="21" x2="559" y2="29"/><line x1="521" y1="67" x2="513" y2="75"/>
<line x1="507" y1="33" x2="516" y2="38"/><line x1="564" y1="58" x2="573" y2="63"/>
<line x1="525" y1="15" x2="530" y2="25"/><line x1="550" y1="71" x2="555" y2="81"/>
</g>
<circle cx="540" cy="48" r="22" fill="#FFF9C4"/>
<circle cx="540" cy="48" r="17" fill="#FFEE58"/>
<circle cx="536" cy="44" r="5" fill="#FFF9C4" opacity="0.6"/>
<ellipse cx="100" cy="45" rx="55" ry="20" fill="white" opacity="0.55"/><ellipse cx="130" cy="38" rx="40" ry="16" fill="white" opacity="0.45"/><ellipse cx="80" cy="42" rx="25" ry="12" fill="white" opacity="0.3"/>
<ellipse cx="380" cy="35" rx="50" ry="18" fill="white" opacity="0.4"/><ellipse cx="410" cy="30" rx="35" ry="14" fill="white" opacity="0.3"/>
<ellipse cx="260" cy="55" rx="35" ry="13" fill="white" opacity="0.3"/>
<path d="M0,120 Q60,85 120,105 Q180,75 260,100 Q340,78 420,95 Q500,80 560,90 Q600,85 640,92 L640,200 L0,200Z" fill="url(#hill1)" opacity="0.6"/>
<path d="M0,135 Q80,108 160,125 Q240,102 340,118 Q440,100 540,115 Q600,108 640,112 L640,200 L0,200Z" fill="url(#hill2)" opacity="0.85"/>
<path d="M0,148 Q100,130 200,142 Q280,128 380,138 Q460,125 560,135 Q610,130 640,134 L640,200 L0,200Z" fill="url(#hill3)"/>
<rect x="0" y="162" width="640" height="38" fill="url(#soil)"/>
<g fill="#5D4037" opacity="0.3"><circle cx="20" cy="175" r="1"/><circle cx="90" cy="172" r="1.2"/><circle cx="170" cy="176" r="1"/><circle cx="250" cy="174" r="1.1"/><circle cx="340" cy="176" r="1"/><circle cx="420" cy="175" r="1.2"/><circle cx="500" cy="173" r="1"/><circle cx="580" cy="176" r="1.1"/></g>
<g transform="translate(45,162)"><line x1="0" y1="0" x2="0" y2="-14" stroke="#2E7D32" stroke-width="2.5" stroke-linecap="round"/><path d="M0,-14 Q-8,-20 -12,-14" fill="#66BB6A" stroke="#2E7D32" stroke-width="0.8"/><path d="M0,-14 Q8,-22 12,-16" fill="#81C784" stroke="#2E7D32" stroke-width="0.8"/><line x1="0" y1="0" x2="-4" y2="6" stroke="#5D4037" stroke-width="1" opacity="0.4"/><line x1="0" y1="0" x2="3" y2="7" stroke="#5D4037" stroke-width="0.8" opacity="0.3"/></g>
<g transform="translate(110,162)"><line x1="0" y1="0" x2="0" y2="-20" stroke="#2E7D32" stroke-width="2.5" stroke-linecap="round"/><path d="M0,-20 Q-10,-28 -14,-20" fill="#4CAF50" stroke="#2E7D32" stroke-width="0.8"/><path d="M0,-20 Q10,-28 14,-22" fill="#66BB6A" stroke="#2E7D32" stroke-width="0.8"/><path d="M0,-12 Q-7,-16 -10,-10" fill="#81C784" stroke="#388E3C" stroke-width="0.6" opacity="0.8"/></g>
<g transform="translate(165,162)"><line x1="0" y1="0" x2="0" y2="-10" stroke="#388E3C" stroke-width="2" stroke-linecap="round"/><path d="M0,-10 Q-5,-15 -8,-10" fill="#A5D6A7" stroke="#388E3C" stroke-width="0.6"/><path d="M0,-10 Q5,-15 8,-11" fill="#C8E6C9" stroke="#388E3C" stroke-width="0.6"/></g>
<g transform="translate(230,162)"><path d="M0,0 Q-2,-8 0,-18" fill="none" stroke="#2E7D32" stroke-width="2.5" stroke-linecap="round"/><path d="M0,-18 Q-10,-26 -15,-18" fill="#66BB6A" stroke="#2E7D32" stroke-width="0.8"/><path d="M0,-18 Q8,-26 13,-20" fill="#4CAF50" stroke="#2E7D32" stroke-width="0.8"/><path d="M-1,-10 Q7,-14 10,-8" fill="#81C784" stroke="#388E3C" stroke-width="0.6" opacity="0.7"/></g>
<g transform="translate(295,162)"><line x1="0" y1="0" x2="0" y2="-16" stroke="#2E7D32" stroke-width="2.5" stroke-linecap="round"/><path d="M0,-16 Q-9,-24 -13,-16" fill="#43A047" stroke="#2E7D32" stroke-width="0.8"/><path d="M0,-16 Q9,-23 13,-17" fill="#66BB6A" stroke="#2E7D32" stroke-width="0.8"/></g>
<g transform="translate(355,162)"><path d="M0,0 Q1,-10 0,-22" fill="none" stroke="#2E7D32" stroke-width="2.8" stroke-linecap="round"/><path d="M0,-22 Q-11,-30 -16,-22" fill="#4CAF50" stroke="#1B5E20" stroke-width="0.8"/><path d="M0,-22 Q11,-31 15,-23" fill="#66BB6A" stroke="#2E7D32" stroke-width="0.8"/><path d="M0,-14 Q-8,-18 -11,-12" fill="#81C784" stroke="#388E3C" stroke-width="0.6" opacity="0.8"/><path d="M0,-8 Q6,-12 9,-7" fill="#A5D6A7" stroke="#388E3C" stroke-width="0.5" opacity="0.7"/></g>
<g transform="translate(415,162)"><line x1="0" y1="0" x2="0" y2="-11" stroke="#388E3C" stroke-width="2" stroke-linecap="round"/><path d="M0,-11 Q-6,-17 -9,-11" fill="#A5D6A7" stroke="#388E3C" stroke-width="0.6"/><path d="M0,-11 Q6,-16 9,-12" fill="#C8E6C9" stroke="#43A047" stroke-width="0.6"/></g>
<g transform="translate(475,162)"><line x1="0" y1="0" x2="0" y2="-17" stroke="#2E7D32" stroke-width="2.5" stroke-linecap="round"/><path d="M0,-17 Q-9,-25 -13,-17" fill="#66BB6A" stroke="#2E7D32" stroke-width="0.8"/><path d="M0,-17 Q9,-24 12,-18" fill="#4CAF50" stroke="#2E7D32" stroke-width="0.8"/><path d="M0,-10 Q-6,-14 -9,-9" fill="#81C784" stroke="#388E3C" stroke-width="0.6" opacity="0.75"/></g>
<g transform="translate(530,162)"><line x1="0" y1="0" x2="0" y2="-8" stroke="#43A047" stroke-width="1.8" stroke-linecap="round"/><path d="M0,-8 Q-4,-13 -7,-8" fill="#C8E6C9" stroke="#43A047" stroke-width="0.5"/><path d="M0,-8 Q4,-12 7,-9" fill="#A5D6A7" stroke="#43A047" stroke-width="0.5"/></g>
<g transform="translate(590,162)"><line x1="0" y1="0" x2="0" y2="-15" stroke="#2E7D32" stroke-width="2.5" stroke-linecap="round"/><path d="M0,-15 Q-8,-22 -12,-15" fill="#66BB6A" stroke="#2E7D32" stroke-width="0.8"/><path d="M0,-15 Q8,-22 12,-16" fill="#43A047" stroke="#2E7D32" stroke-width="0.8"/><path d="M0,-8 Q5,-12 8,-7" fill="#81C784" stroke="#388E3C" stroke-width="0.5" opacity="0.7"/></g>
<rect x="325" y="135" width="3" height="22" rx="1" fill="#78909C"/><circle cx="326" cy="133" r="4" fill="#1565C0" opacity="0.8"/><circle cx="326" cy="133" r="7" fill="#1565C0" opacity="0.15"/>
<g transform="translate(200,70)" opacity="0.7"><rect x="-2" y="0" width="4" height="3" rx="1" fill="#455A64"/><line x1="-12" y1="0" x2="12" y2="0" stroke="#607D8B" stroke-width="1.5"/><circle cx="-12" cy="0" r="4" fill="none" stroke="#90A4AE" stroke-width="1"/><circle cx="12" cy="0" r="4" fill="none" stroke="#90A4AE" stroke-width="1"/></g>
<g stroke="#37474F" stroke-width="1" fill="none" opacity="0.35"><path d="M440,70 Q445,65 450,70"/><path d="M450,70 Q455,65 460,70"/><path d="M470,60 Q474,56 478,60"/><path d="M478,60 Q482,56 486,60"/></g>
</svg>`,

  leaf: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#66BB6A" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 8C8 10 5.9 16.17 3.82 21.34l1.89.66L7 18c4-2 7.5-2.5 10-1 2.5 1.5 3 4 3 4s1-4.5-1-8c-1.06-1.86-2.58-3.21-4.27-4.13"/><path d="M2 2s7.17 1.59 9 8"/></svg>`,

  sprout: `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#2E7D32" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 20h10"/><path d="M10 20c5.5-2.5.8-6.4 3-10"/><path d="M9.5 9.4c1.1.8 1.8 2.2 2.3 3.7-2 .4-3.5.4-4.8-.3-1.2-.6-2.3-1.9-3-4.2 2.8-.5 4.4 0 5.5.8z"/><path d="M14.1 6a7 7 0 0 0-1.1 4c1.9-.1 3.3-.6 4.3-1.4 1-1 1.6-2.3 1.7-4.6-2.7.1-4 1-4.9 2z"/></svg>`,

  wheat: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#6D4C41" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 22 16 8"/><path d="M3.47 12.53 5 11l1.53 1.53a3.5 3.5 0 0 1 0 4.94L5 19l-1.53-1.53a3.5 3.5 0 0 1 0-4.94Z"/><path d="M7.47 8.53 9 7l1.53 1.53a3.5 3.5 0 0 1 0 4.94L9 15l-1.53-1.53a3.5 3.5 0 0 1 0-4.94Z"/><path d="M11.47 4.53 13 3l1.53 1.53a3.5 3.5 0 0 1 0 4.94L13 11l-1.53-1.53a3.5 3.5 0 0 1 0-4.94Z"/><path d="M20 2h2v2a4 4 0 0 1-4 4h-2V6a4 4 0 0 1 4-4Z"/></svg>`,

  shield: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#1565C0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>`,

  clock: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1565C0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,

  tree: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#2E7D32" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 20a7 7 0 0 1-9.9-8.5L4 7l3 1 2-4 2 4 3-1 2.9 4.5A7 7 0 0 1 13 20z"/><path d="M12 20v2"/></svg>`,

  rootsDivider: `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="30" viewBox="0 0 400 30"><path d="M0,15 Q30,5 60,15 T120,15 T180,15 T240,15 T300,15 T360,15 L400,15" fill="none" stroke="#6D4C41" stroke-width="1.5" opacity="0.3"/><path d="M10,18 Q40,28 70,18 T130,18 T190,18 T250,18 T310,18 T370,18 L400,18" fill="none" stroke="#2E7D32" stroke-width="1" opacity="0.2"/><circle cx="60" cy="12" r="3" fill="#66BB6A" opacity="0.4"/><circle cx="180" cy="18" r="2" fill="#2E7D32" opacity="0.3"/><circle cx="300" cy="14" r="2.5" fill="#66BB6A" opacity="0.35"/><path d="M140,15 L142,8 M140,15 L138,7" stroke="#2E7D32" stroke-width="1" opacity="0.3"/><path d="M260,15 L263,7 M260,15 L257,8" stroke="#66BB6A" stroke-width="1" opacity="0.3"/></svg>`,

  cornerVineTL: `<svg xmlns="http://www.w3.org/2000/svg" width="60" height="60" viewBox="0 0 60 60"><path d="M5,55 Q5,30 15,20 Q25,10 45,5" fill="none" stroke="#66BB6A" stroke-width="1.5" opacity="0.35"/><path d="M10,50 Q12,35 20,25" fill="none" stroke="#2E7D32" stroke-width="1" opacity="0.25"/><circle cx="15" cy="18" r="3" fill="#66BB6A" opacity="0.2"/><circle cx="45" cy="5" r="2" fill="#2E7D32" opacity="0.3"/><path d="M18,22 Q14,18 16,14" fill="none" stroke="#81C784" stroke-width="0.8" opacity="0.3"/></svg>`,

  cornerVineBR: `<svg xmlns="http://www.w3.org/2000/svg" width="60" height="60" viewBox="0 0 60 60"><path d="M55,5 Q55,30 45,40 Q35,50 15,55" fill="none" stroke="#6D4C41" stroke-width="1.5" opacity="0.25"/><path d="M50,10 Q48,25 40,35" fill="none" stroke="#8D6E63" stroke-width="1" opacity="0.2"/><circle cx="45" cy="42" r="3" fill="#6D4C41" opacity="0.15"/><circle cx="15" cy="55" r="2" fill="#8D6E63" opacity="0.2"/></svg>`
};

/**
 * Convert SVG sources to PNG and build CID attachments for nodemailer.
 * Uses sharp for SVG→PNG conversion. Results are cached.
 */
async function buildAttachments() {
  const attachments = [];

  for (const [key, svg] of Object.entries(SVG_SOURCES)) {
    let pngBuffer = pngCache.get(key);

    if (!pngBuffer) {
      // Determine output size based on SVG dimensions
      const widthMatch = svg.match(/width="(\d+)"/);
      const heightMatch = svg.match(/height="(\d+)"/);
      const w = widthMatch ? parseInt(widthMatch[1], 10) : 200;
      const h = heightMatch ? parseInt(heightMatch[1], 10) : 200;

      // Scale up small icons for crispness (2x), keep large images at 1x
      const scale = w <= 44 ? 3 : 1;

      pngBuffer = await sharp(Buffer.from(svg))
        .resize(w * scale, h * scale)
        .png()
        .toBuffer();

      pngCache.set(key, pngBuffer);
    }

    attachments.push({
      filename: `${key}.png`,
      content: pngBuffer,
      cid: `${key}@huerto`,
      contentType: 'image/png',
      contentDisposition: 'inline',
      headers: {
        'Content-ID': `<${key}@huerto>`,
        'X-Attachment-Id': `${key}@huerto`
      }
    });
  }

  return attachments;
}

/* Pre-warm the PNG cache at module load so first email is fast */
let _preWarmPromise;
function preWarmAttachments() {
  if (!_preWarmPromise) {
    _preWarmPromise = buildAttachments().catch((err) => {
      console.error('[OTP-EMAIL] Failed to pre-warm PNG cache:', err.message);
      _preWarmPromise = null;
    });
  }
  return _preWarmPromise;
}
preWarmAttachments();

/* Helper: generate a cid img tag */
function cidImg(key, width, height, alt = '') {
  return `<img src="cid:${key}@huerto" width="${width}" height="${height}" alt="${alt}" style="display:inline-block;vertical-align:middle;border:0;outline:none;" />`;
}


async function buildOtpEmailTemplate({ recipientName, email, otpCode, expiresInMinutes, verifyUrl, purpose }) {
  const isRegistro = purpose === 'registro';
  const isPasswordReset = purpose === 'reset-password';
  let displayName = 'Usuario';
  if (recipientName) {
    displayName = recipientName;
  } else if (email) {
    displayName = email.split('@')[0].replace(/[._-]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  }
  const safeName = escapeHtml(displayName);
  const safeCode = escapeHtml(otpCode);
  const safeVerifyUrl = verifyUrl ? escapeHtml(verifyUrl) : '';

  const emailSubject = isRegistro
    ? 'Huerto Connect - Confirma tu registro'
    : isPasswordReset
      ? 'Huerto Connect - Cambia tu contrasena'
      : 'Huerto Connect - Verifica tu cuenta';
  const emailTitle = isRegistro
    ? 'Confirma tu registro'
    : isPasswordReset
      ? 'Cambia tu contrasena'
      : 'Verifica tu cuenta';
  const emailMessage = isRegistro
    ? `Usa el siguiente c&oacute;digo para activar tu cuenta en <strong style="color:#2E7D32;">Huerto Connect</strong>.`
    : isPasswordReset
      ? `Usa el siguiente c&oacute;digo para autorizar el <strong style="color:#2E7D32;">cambio de contrase&ntilde;a</strong> de tu cuenta en <strong style="color:#2E7D32;">Huerto Connect</strong>.`
      : `Usa el siguiente c&oacute;digo para completar tu inicio de sesi&oacute;n en <strong style="color:#2E7D32;">Huerto Connect</strong>.`;
  const emailWarning = isRegistro
    ? 'Si no creaste esta cuenta, ignora este correo.'
    : isPasswordReset
      ? 'Si no solicitaste este cambio de contrase&ntilde;a, ignora este correo y revisa la seguridad de tu cuenta.'
      : 'Si no solicitaste este inicio de sesi&oacute;n, ignora este correo y protege tu cuenta.';
  const emailButtonText = isRegistro ? 'Activar cuenta' : isPasswordReset ? 'Cambiar contrasena' : 'Verificar acceso';
  const emailHeaderBadge = isRegistro
    ? 'Verificaci&oacute;n de registro de cuenta'
    : isPasswordReset
      ? 'Restablecimiento de contrase&ntilde;a'
      : 'Verificaci&oacute;n de cuenta';
  const otpSectionLabel = isPasswordReset ? 'Parcela de recuperaci&oacute;n' : 'Parcela de verificaci&oacute;n';
  const otpFooterLegend = isPasswordReset ? 'protegiendo tu cuenta digital' : 'cultivando seguridad';
  const securityNotice = isPasswordReset
    ? `${cidImg('shield', 18, 18)} <strong>Aviso de seguridad:</strong> Si no solicitaste este cambio de contrase&ntilde;a, ignora este correo y cambia tu contrase&ntilde;a desde un entorno seguro.`
    : `${cidImg('shield', 18, 18)} <strong>Aviso de seguridad:</strong> Nunca compartas este c&oacute;digo OTP. Nuestro equipo no solicita este c&oacute;digo por chat, llamada o redes sociales.`;

  const otpDigits = String(safeCode)
    .split('')
    .map(
      (d) =>
        `<td align="center" style="padding:0 3px;">
          <div style="width:46px;height:58px;line-height:58px;text-align:center;font-size:28px;font-weight:800;font-family:'Segoe UI',Arial,sans-serif;color:#1565C0;background-color:#FFFFFF;border:2px solid #8D6E63;border-radius:10px;">${d}</div>
        </td>`
    )
    .join('');

  const verificationButton = safeVerifyUrl
    ? `<tr>
        <td align="center" style="padding:6px 28px 24px 28px;">
          <a href="${safeVerifyUrl}" style="display:inline-block;padding:15px 40px;border-radius:999px;background-color:#2E7D32;color:#FFFFFF;font-size:15px;font-weight:700;text-decoration:none;text-align:center;letter-spacing:0.4px;">
            ${emailButtonText}
          </a>
        </td>
      </tr>`
    : '';

  const html = `<!doctype html>
<html lang="es" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta http-equiv="X-UA-Compatible" content="IE=edge" />
    <title>${escapeHtml(emailSubject)}</title>
    <!--[if mso]>
    <noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript>
    <![endif]-->
    <style>
      body, table, td, p, a, li, blockquote { -ms-text-size-adjust:100%; -webkit-text-size-adjust:100%; }
      table, td { mso-table-lspace:0pt; mso-table-rspace:0pt; }
      img { -ms-interpolation-mode:bicubic; border:0; outline:none; text-decoration:none; }
      @media only screen and (max-width: 640px) {
        .wrapper-cell { padding: 10px !important; }
        .card-main { border-radius: 16px !important; }
        .content-cell { padding: 20px 16px !important; }
        .title-text { font-size: 26px !important; }
        .header-scene { height: auto !important; }
        .otp-cell { padding: 16px 10px !important; }
        .footer-cell { padding: 18px 16px !important; }
      }
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
                            ${cidImg('logo', 44, 44, 'Huerto Connect')}
                            <span style="display:inline-block;vertical-align:middle;margin-left:10px;">
                              <span style="font-size:18px;font-weight:800;letter-spacing:0.5px;color:#FFFFFF;">HUERTO CONNECT</span><br/>
                              <span style="font-size:11px;font-weight:400;letter-spacing:0.8px;text-transform:uppercase;color:#C8E6C9;">Agricultura Inteligente</span>
                            </span>
                          </td>
                          <td align="right" valign="middle">
                            <span style="font-size:11px;font-weight:400;letter-spacing:0.6px;text-transform:uppercase;color:#C8E6C9;">
                              ${emailHeaderBadge}
                            </span>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                  <!-- Header scene -->
                  <tr>
                    <td style="padding:0;font-size:0;line-height:0;" class="header-scene">
                      ${cidImg('headerScene', 640, 200, 'Huerto Connect - Agricultura Inteligente')}
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
                          <td width="60" valign="top" style="padding:0;">${cidImg('cornerVineTL', 60, 60)}</td>
                          <td style="padding:18px 12px 18px 0;">
                            <p style="margin:0 0 6px 0;font-size:14px;font-weight:600;color:#2E7D32;">
                              ${cidImg('sprout', 20, 20)} Hola, ${safeName}
                            </p>
                            <h1 class="title-text" style="margin:0;color:#1a3a2a;font-size:30px;line-height:1.25;font-weight:800;">
                              ${emailTitle}
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
                  <tr><td style="font-size:0;line-height:0;">${cidImg('rootsDivider', 400, 30)}</td></tr>
                </table>

                <!-- Message card -->
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                  <tr>
                    <td style="padding:16px 20px;background-color:#FFFFFF;border:1px solid #d3c9b8;border-radius:14px;">
                      <p style="margin:0;color:#3a4e44;font-size:15px;line-height:1.65;">
                        ${cidImg('leaf', 18, 18)} ${emailMessage}
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
                            ${cidImg('wheat', 16, 16)} ${otpSectionLabel}
                          </td>
                          <td align="right" style="font-size:12px;color:#6D4C41;padding-bottom:4px;">
                            ${cidImg('sprout', 20, 20)}
                          </td>
                        </tr>
                      </table>

                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom:8px;">
                        <tr><td style="font-size:0;line-height:0;">${cidImg('rootsDivider', 400, 30)}</td></tr>
                      </table>

                      <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:0 auto;">
                        <tr>
                          ${otpDigits}
                        </tr>
                      </table>

                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-top:10px;">
                        <tr><td style="font-size:0;line-height:0;">${cidImg('rootsDivider', 400, 30)}</td></tr>
                      </table>

                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-top:6px;">
                        <tr>
                          <td align="center" style="font-size:11px;color:#8D6E63;font-style:italic;">
                            ${cidImg('tree', 14, 14)} ${otpFooterLegend} ${cidImg('tree', 14, 14)}
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
                              ${cidImg('clock', 16, 16)} Este c&oacute;digo expirar&aacute; en <strong style="color:#1565C0;">${expiresInMinutes} minutos</strong>.
                            </p>
                            <p style="margin:0;color:#5a6d64;font-size:13px;line-height:1.55;">
                              ${emailWarning}
                            </p>
                          </td>
                          <td width="60" valign="bottom" style="padding:0;">${cidImg('cornerVineBR', 60, 60)}</td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                </table>

              </td>
            </tr>


            <!-- ===== VERIFICATION BUTTON ===== -->
            ${verificationButton}


            <!-- ===== SECURITY NOTICE ===== -->
            <tr>
              <td style="padding:8px 28px 0 28px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                  <tr>
                    <td style="padding:14px 18px;background-color:#FFF8E1;border:1px solid #FFE082;border-radius:12px;border-left:4px solid #FFA000;">
                      <p style="margin:0;color:#5D4037;font-size:13px;line-height:1.55;">
                        ${securityNotice}
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
                      <span style="font-size:16px;font-weight:800;letter-spacing:0.4px;color:#FFFFFF;">${cidImg('sprout', 20, 20)} Huerto Connect</span>
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
                      ${cidImg('leaf', 18, 18)} Crecimiento &bull; ${cidImg('wheat', 16, 16)} Naturaleza &bull; ${cidImg('tree', 14, 14)} Huerto &bull; ${cidImg('shield', 18, 18)} Seguridad
                    </td>
                  </tr>
                  <tr>
                    <td style="padding-top:6px;font-size:10px;color:rgba(255,255,255,0.45);">
                      &copy; ${new Date().getFullYear()} Huerto Connect. Todos los derechos reservados.
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
</html>`;

  const textMessage = isRegistro
    ? 'Usa el siguiente codigo para activar tu cuenta en Huerto Connect.'
    : isPasswordReset
      ? 'Usa el siguiente codigo para autorizar el cambio de contrasena de tu cuenta en Huerto Connect.'
      : 'Usa el siguiente codigo para completar tu inicio de sesion en Huerto Connect.';
  const textWarning = isRegistro
    ? 'Si no creaste esta cuenta, ignora este correo.'
    : isPasswordReset
      ? 'Si no solicitaste este cambio de contrasena, ignora este correo y revisa la seguridad de tu cuenta.'
      : 'Si no solicitaste este acceso, ignora este correo y protege tu cuenta.';
  const textSecurityNotice = isPasswordReset
    ? 'Aviso de seguridad: si no solicitaste este cambio de contrasena, ignora este correo y cambia tu contrasena desde un entorno seguro.'
    : 'Aviso de seguridad: nunca compartas este codigo OTP.';

  const text = [
    emailSubject,
    '-------------------------------------------',
    '',
    `Hola ${safeName},`,
    '',
    textMessage,
    '',
    `Codigo OTP: ${otpCode}`,
    '',
    `Este codigo expirara en ${expiresInMinutes} minutos.`,
    '',
    textWarning,
    '',
    textSecurityNotice,
    'Nuestro equipo no solicita este codigo por chat, llamada o redes sociales.',
    '',
    '-------------------------------------------',
    'Huerto Connect - Tecnologia para agricultura inteligente',
    'Contacto: huertoconnect@gmail.com',
    'Seguridad: https://huertoconnect.com/seguridad',
    'Soporte: https://huertoconnect.com/soporte'
  ].join('\n');

  return {
    subject: emailSubject,
    html,
    text,
    attachments: await buildAttachments()
  };
}

module.exports = {
  buildOtpEmailTemplate
};
