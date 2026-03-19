const nodemailer = require('nodemailer');
const { buildOtpEmailTemplate } = require('../templates/otp-email.template');
const { createOtpMagicLinkToken } = require('../utils/security');

const SMTP_HOST = process.env.OTP_EMAIL_HOST || 'smtp.gmail.com';
const SMTP_PORT = Number(process.env.OTP_EMAIL_PORT || 465);
const SMTP_SECURE =
  process.env.OTP_EMAIL_SECURE === undefined ? true : process.env.OTP_EMAIL_SECURE === 'true';
const SMTP_USER = process.env.OTP_EMAIL_USER || 'huertoconnect@gmail.com';
const SMTP_PASS = (process.env.OTP_EMAIL_APP_PASSWORD || '').replace(/\s+/g, '');
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:4200';
const API_PUBLIC_URL =
  process.env.API_PUBLIC_URL ||
  process.env.PUBLIC_API_URL ||
  `http://localhost:${Number(process.env.API_PORT || 3000)}`;
const FROM_EMAIL = 'huertoconnect@gmail.com';
const DELIVERY_MODE = (process.env.OTP_DELIVERY_MODE || '').trim().toLowerCase() || 'console';

let transporter;

function getTransporter() {
  if (!SMTP_PASS && DELIVERY_MODE === 'smtp') {
    throw new Error('OTP_EMAIL_APP_PASSWORD is missing. Configure Gmail App Password first.');
  }

  if (!transporter) {
    transporter = nodemailer.createTransport({
      host: SMTP_HOST,
      port: SMTP_PORT,
      secure: SMTP_SECURE,
      auth: {
        user: SMTP_USER,
        pass: SMTP_PASS
      }
    });
  }

  return transporter;
}

function buildVerifyUrl({ challengeId, otpCode, purpose, expiresAt }) {
  if (!challengeId || !otpCode) {
    return `${FRONTEND_URL.replace(/\/$/, '')}/login`;
  }

  const token = createOtpMagicLinkToken({
    challengeId,
    otpCode,
    purpose,
    expiresAt
  });

  return `${API_PUBLIC_URL.replace(/\/$/, '')}/api/auth/verify-email-link?token=${encodeURIComponent(token)}`;
}

async function sendOtpEmail({ to, recipientName, challengeId, otpCode, expiresInMinutes, expiresAt, purpose }) {
  const verifyUrl = buildVerifyUrl({
    challengeId,
    otpCode,
    purpose,
    expiresAt
  });
  const template = await buildOtpEmailTemplate({
    recipientName,
    email: to,
    otpCode,
    expiresInMinutes,
    verifyUrl,
    purpose
  });

  const attachmentCount = (template.attachments || []).length;
  console.log(`[OTP-EMAIL] purpose=${purpose || 'login'} to=${to} attachments=${attachmentCount} subject="${template.subject}"`);

  if (DELIVERY_MODE !== 'smtp') {
    console.log(
      `[OTP][DEV-CONSOLE] to=${to} code=${otpCode} expiresInMinutes=${expiresInMinutes} from=${FROM_EMAIL}`
    );
    return {
      messageId: `console-${Date.now()}`
    };
  }

  const info = await getTransporter().sendMail({
    from: `Huerto Connect <${FROM_EMAIL}>`,
    to,
    subject: template.subject,
    html: template.html,
    text: template.text,
    attachments: template.attachments || []
  });

  return {
    messageId: info.messageId
  };
}

module.exports = {
  sendOtpEmail
};
