const express = require('express');
const { findUserByEmail, verifyPassword } = require('../config/users');
const { sendOtpEmail } = require('../services/mailer.service');
const {
  createOtpChallenge,
  discardOtpChallenge,
  getSessionFromToken,
  regenerateOtpForChallenge,
  revokeSession,
  verifyOtpChallenge
} = require('../services/otp-auth.service');
const { maskEmail, sanitizeNumericOtp } = require('../utils/security');

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const EXPOSE_OTP_IN_RESPONSE = process.env.OTP_EXPOSE_CODE_IN_RESPONSE === 'true';
const router = express.Router();

router.post('/send-otp', async (req, res, next) => {
  try {
    const email = String(req.body?.email ?? '').trim().toLowerCase();
    const password = String(req.body?.password ?? '');

    if (!EMAIL_REGEX.test(email) || password.length < 6) {
      return res.status(400).json({
        message: 'Correo o contrasena invalido.'
      });
    }

    const user = findUserByEmail(email);
    if (!user || !verifyPassword(user, password)) {
      return res.status(401).json({
        message: 'Credenciales invalidas.'
      });
    }

    const otpChallenge = createOtpChallenge(user);

    try {
      await sendOtpEmail({
        to: user.email,
        recipientName: user.name,
        otpCode: otpChallenge.otpCode,
        expiresInMinutes: otpChallenge.expiresInMinutes
      });
    } catch (error) {
      discardOtpChallenge(otpChallenge.challengeId);
      throw error;
    }

    const payload = {
      message: 'Codigo OTP enviado al correo electronico.',
      challengeId: otpChallenge.challengeId,
      expiresAt: otpChallenge.expiresAt,
      maskedEmail: maskEmail(user.email)
    };

    if (EXPOSE_OTP_IN_RESPONSE) {
      payload.devOtpCode = otpChallenge.otpCode;
    }

    return res.status(200).json(payload);
  } catch (error) {
    return next(error);
  }
});

router.post('/verify-otp', (req, res) => {
  const challengeId = String(req.body?.challengeId ?? '').trim();
  const otpCode = sanitizeNumericOtp(req.body?.otpCode);

  if (!challengeId || otpCode.length !== 6) {
    return res.status(400).json({
      message: 'El codigo OTP debe contener 6 digitos.'
    });
  }

  const result = verifyOtpChallenge({ challengeId, otpCode });

  if (result.status === 'ok') {
    return res.status(200).json({
      message: 'Codigo OTP validado correctamente.',
      session: result.session,
      user: result.user
    });
  }

  const baseError = {
    message: result.message,
    allowResend: result.allowResend ?? false
  };

  if (result.code === 'challenge_not_found') {
    return res.status(404).json(baseError);
  }

  if (result.code === 'too_many_attempts') {
    return res.status(429).json(baseError);
  }

  return res.status(400).json({
    ...baseError,
    remainingAttempts: result.remainingAttempts
  });
});

router.post('/resend-otp', async (req, res, next) => {
  try {
    const challengeId = String(req.body?.challengeId ?? '').trim();

    if (!challengeId) {
      return res.status(400).json({
        message: 'challengeId es requerido.'
      });
    }

    const result = regenerateOtpForChallenge(challengeId);

    if (result.status !== 'ok') {
      if (result.code === 'challenge_not_found') {
        return res.status(404).json({
          message: result.message
        });
      }

      return res.status(429).json({
        message: result.message
      });
    }

    await sendOtpEmail({
      to: result.email,
      recipientName: result.name,
      otpCode: result.otpCode,
      expiresInMinutes: result.expiresInMinutes
    });

    const payload = {
      message: 'Nuevo codigo OTP enviado correctamente.',
      challengeId: result.challengeId,
      expiresAt: result.expiresAt,
      maskedEmail: maskEmail(result.email)
    };

    if (EXPOSE_OTP_IN_RESPONSE) {
      payload.devOtpCode = result.otpCode;
    }

    return res.status(200).json(payload);
  } catch (error) {
    return next(error);
  }
});

router.get('/session', (req, res) => {
  const authHeader = String(req.headers.authorization ?? '');
  const token = authHeader.startsWith('Bearer ') ? authHeader.slice(7).trim() : '';

  if (!token) {
    return res.status(401).json({
      message: 'Token de sesion requerido.'
    });
  }

  const session = getSessionFromToken(token);

  if (!session) {
    return res.status(401).json({
      message: 'Sesion invalida o expirada.'
    });
  }

  return res.status(200).json({
    session
  });
});

router.post('/logout', (req, res) => {
  const token = String(req.body?.token ?? '');

  if (token) {
    revokeSession(token);
  }

  return res.status(200).json({
    message: 'Sesion cerrada.'
  });
});

module.exports = router;
