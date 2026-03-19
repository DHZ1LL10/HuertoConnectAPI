const nodemailer = require('nodemailer');
const { buildOtpEmailTemplate } = require('../templates/otp-email.template');

const SMTP_HOST = process.env.OTP_EMAIL_HOST || 'smtp.gmail.com';
const SMTP_PORT = Number(process.env.OTP_EMAIL_PORT || 465);
const SMTP_SECURE =
  process.env.OTP_EMAIL_SECURE === undefined ? true : process.env.OTP_EMAIL_SECURE === 'true';
const SMTP_USER = process.env.OTP_EMAIL_USER || 'huertoconnect@gmail.com';
const SMTP_PASS = (process.env.OTP_EMAIL_APP_PASSWORD || '').replace(/\s+/g, '');
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:4200';
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

async function sendOtpEmail({ to, recipientName, otpCode, expiresInMinutes }) {
  const verifyUrl = `${FRONTEND_URL.replace(/\/$/, '')}/login`;
  const template = buildOtpEmailTemplate({
    recipientName,
    otpCode,
    expiresInMinutes,
    verifyUrl
  });

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
    text: template.text
  });

  return {
    messageId: info.messageId
  };
}

module.exports = {
  sendOtpEmail
};
