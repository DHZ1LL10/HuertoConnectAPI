const crypto = require('node:crypto');

const OTP_HASH_SECRET =
  process.env.OTP_HASH_SECRET || 'huerto-connect-dev-otp-secret-change-in-production';

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
    return crypto.timingSafeEqual(expected, candidate);
  } catch {
    return false;
  }
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
  constantTimeEqualHex,
  generateOtpCode,
  generateRandomId,
  hashOtpCode,
  maskEmail,
  sanitizeNumericOtp
};
