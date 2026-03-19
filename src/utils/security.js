const crypto = require('node:crypto');

const OTP_HASH_SECRET =
  process.env.OTP_HASH_SECRET || 'huerto-connect-dev-otp-secret-change-in-production';
const OTP_LINK_SECRET =
  process.env.OTP_LINK_SECRET || OTP_HASH_SECRET || 'huerto-connect-dev-otp-link-secret-change-in-production';
const OTP_LINK_DEFAULT_TTL_MS = 5 * 60 * 1000;

function toBase64Url(value) {
  return Buffer.from(value)
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '');
}

function fromBase64Url(value) {
  const normalized = String(value).replace(/-/g, '+').replace(/_/g, '/');
  const padded = normalized + '==='.slice((normalized.length + 3) % 4);
  return Buffer.from(padded, 'base64');
}

function generateRandomId(bytes = 24) {
  return crypto.randomBytes(bytes).toString('hex');
}

function generateOtpCode() {
  return crypto.randomInt(0, 1_000_000).toString().padStart(6, '0');
}

function hashOtpCode({ challengeId, otpCode }) {
  return crypto
    .createHmac('sha256', OTP_HASH_SECRET)
    .update(`${challengeId}:${otpCode}`)
    .digest('hex');
}

function constantTimeEqualBuffer(expectedBuffer, candidateBuffer) {
  if (!Buffer.isBuffer(expectedBuffer) || !Buffer.isBuffer(candidateBuffer)) {
    return false;
  }

  if (expectedBuffer.length !== candidateBuffer.length) {
    return false;
  }

  try {
    return crypto.timingSafeEqual(expectedBuffer, candidateBuffer);
  } catch {
    return false;
  }
}

function constantTimeEqualHex(expectedHex, candidateHex) {
  if (typeof expectedHex !== 'string' || typeof candidateHex !== 'string') {
    return false;
  }

  if (expectedHex.length !== candidateHex.length) {
    return false;
  }

  try {
    const expected = Buffer.from(expectedHex, 'hex');
    const candidate = Buffer.from(candidateHex, 'hex');
    return constantTimeEqualBuffer(expected, candidate);
  } catch {
    return false;
  }
}

function createOtpMagicLinkToken({ challengeId, otpCode, purpose, expiresAt }) {
  const parsedExpiry = Date.parse(String(expiresAt ?? ''));
  const exp = Number.isFinite(parsedExpiry) ? parsedExpiry : Date.now() + OTP_LINK_DEFAULT_TTL_MS;

  const payload = {
    challengeId: String(challengeId ?? ''),
    otpCode: sanitizeNumericOtp(otpCode),
    purpose: String(purpose ?? 'login'),
    exp
  };

  const payloadEncoded = toBase64Url(JSON.stringify(payload));
  const signature = crypto.createHmac('sha256', OTP_LINK_SECRET).update(payloadEncoded).digest();

  return `${payloadEncoded}.${toBase64Url(signature)}`;
}

function verifyOtpMagicLinkToken(token) {
  if (typeof token !== 'string') {
    return { ok: false, code: 'invalid_token' };
  }

  const trimmed = token.trim();
  const tokenParts = trimmed.split('.');
  if (tokenParts.length !== 2) {
    return { ok: false, code: 'invalid_token' };
  }

  const [payloadEncoded, signatureEncoded] = tokenParts;
  if (!payloadEncoded || !signatureEncoded) {
    return { ok: false, code: 'invalid_token' };
  }

  let candidateSignature;
  let payload;

  try {
    candidateSignature = fromBase64Url(signatureEncoded);
    payload = JSON.parse(fromBase64Url(payloadEncoded).toString('utf8'));
  } catch {
    return { ok: false, code: 'invalid_token' };
  }

  const expectedSignature = crypto.createHmac('sha256', OTP_LINK_SECRET).update(payloadEncoded).digest();
  if (!constantTimeEqualBuffer(expectedSignature, candidateSignature)) {
    return { ok: false, code: 'invalid_token' };
  }

  const challengeId = String(payload?.challengeId ?? '').trim();
  const otpCode = sanitizeNumericOtp(payload?.otpCode);
  const purpose = String(payload?.purpose ?? '').trim() || 'login';
  const exp = Number(payload?.exp ?? 0);

  if (!challengeId || otpCode.length !== 6 || !Number.isFinite(exp) || exp <= Date.now()) {
    return { ok: false, code: 'expired_or_invalid' };
  }

  return {
    ok: true,
    challengeId,
    otpCode,
    purpose,
    expiresAt: new Date(exp).toISOString()
  };
}

function maskEmail(email) {
  const [rawLocalPart = '', rawDomain = ''] = email.split('@');
  const localPart = rawLocalPart.trim();
  const domain = rawDomain.trim();

  if (!localPart || !domain) {
    return email;
  }

  if (localPart.length === 1) {
    return `*${localPart}@${domain}`;
  }

  if (localPart.length === 2) {
    return `${localPart[0]}*@${domain}`;
  }

  return `${localPart.slice(0, 2)}***${localPart.slice(-1)}@${domain}`;
}

function sanitizeNumericOtp(input) {
  return String(input ?? '')
    .replace(/\D/g, '')
    .slice(0, 6);
}

module.exports = {
  createOtpMagicLinkToken,
  constantTimeEqualHex,
  generateOtpCode,
  generateRandomId,
  hashOtpCode,
  maskEmail,
  sanitizeNumericOtp,
  verifyOtpMagicLinkToken
};
