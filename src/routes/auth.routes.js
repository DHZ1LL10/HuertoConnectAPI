const express = require('express');
const { addOrFindGoogleUser, addUser, emailExists, findUserByEmail, findUserById, generateSalt, hashPassword, updatePassword, verifyPassword } = require('../config/users');
const { authenticate } = require('../middleware/authenticate');
const { authorizeRole } = require('../middleware/authorize-role');
const { sendOtpEmail } = require('../services/mailer.service');
const {
  consumeResetToken,
  createOtpChallenge,
  createPasswordResetChallenge,
  createRegistrationChallenge,
  createSession,
  discardOtpChallenge,
  getSessionFromToken,
  regenerateOtpForChallenge,
  revokeSession,
  verifyOtpChallenge
} = require('../services/otp-auth.service');
const { maskEmail, sanitizeNumericOtp, verifyOtpMagicLinkToken } = require('../utils/security');

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const EXPOSE_OTP_IN_RESPONSE = process.env.OTP_EXPOSE_CODE_IN_RESPONSE === 'true';
const FRONTEND_URL = (process.env.FRONTEND_URL || 'http://localhost:4200').replace(/\/$/, '');
const FRONTEND_LOGIN_PATH = process.env.FRONTEND_LOGIN_PATH || '/login';
const FRONTEND_DASHBOARD_PATH = process.env.FRONTEND_DASHBOARD_PATH || '/dashboard';
const router = express.Router();

function buildFrontendUrl(pathname, params = {}) {
  const normalizedPath = pathname.startsWith('/') ? pathname : `/${pathname}`;
  const url = new URL(`${FRONTEND_URL}${normalizedPath}`);

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value));
    }
  }

  return url.toString();
}

function buildOtpSuccessPayload(result) {
  if (result.tipo === 'reset-password') {
    return {
      statusCode: 200,
      payload: {
        message: 'Codigo verificado. Ya puedes actualizar tu contrasena.',
        resetToken: result.resetToken
      }
    };
  }

  if (result.tipo === 'registro') {
    const pending = result.pendingUser;

    if (emailExists(pending.email)) {
      return {
        statusCode: 409,
        payload: {
          message: 'Ya existe una cuenta con ese correo electronico.'
        }
      };
    }

    const newUser = addUser({
      nombre: pending.nombre,
      apellidos: pending.apellidos,
      email: pending.email,
      passwordHash: pending.passwordHash,
      passwordSalt: pending.passwordSalt
    });

    const session = createSession({
      userId: newUser.id,
      email: newUser.email,
      name: newUser.name,
      role: newUser.role,
      profile_picture: newUser.profile_picture
    });

    return {
      statusCode: 201,
      payload: {
        message: 'Cuenta creada y verificada exitosamente.',
        session,
        user: {
          id: newUser.id,
          email: newUser.email,
          name: newUser.name,
          role: newUser.role,
          profile_picture: newUser.profile_picture
        }
      }
    };
  }

  return {
    statusCode: 200,
    payload: {
      message: 'Codigo OTP validado correctamente.',
      session: result.session,
      user: result.user
    }
  };
}

function sendOtpVerificationErrorResponse(res, result) {
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
}

function buildMagicLinkErrorRedirect(code, message) {
  return buildFrontendUrl(FRONTEND_LOGIN_PATH, {
    source: 'email-link',
    magicLinkStatus: 'error',
    magicLinkCode: code,
    magicLinkMessage: message
  });
}

function buildMagicLinkSuccessRedirect(result, payload) {
  if (result.tipo === 'reset-password') {
    return buildFrontendUrl(FRONTEND_LOGIN_PATH, {
      source: 'email-link',
      magicLinkStatus: 'ok',
      magicLinkType: 'reset-password',
      flow: 'forgot-reset',
      resetToken: payload.resetToken
    });
  }

  const session = payload.session;
  const user = payload.user ?? session?.user;

  return buildFrontendUrl(FRONTEND_LOGIN_PATH, {
    source: 'email-link',
    magicLinkStatus: 'ok',
    magicLinkType: result.tipo || 'login',
    flow: 'magic-login',
    redirectTo: FRONTEND_DASHBOARD_PATH,
    sessionToken: session?.token,
    sessionExpiresAt: session?.expiresAt,
    userId: user?.id,
    userEmail: user?.email,
    userName: user?.name,
    userRole: user?.role,
    userProfilePicture: user?.profile_picture
  });
}

// ─── LOGIN: Send OTP ──────────────────────────────────────────

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

    if (!user.emailVerificado) {
      return res.status(403).json({
        message: 'Tu cuenta aun no esta verificada. Registrate de nuevo para recibir un codigo de verificacion.'
      });
    }

    const otpChallenge = createOtpChallenge(user);

    try {
      await sendOtpEmail({
        to: user.email,
        recipientName: user.name,
        challengeId: otpChallenge.challengeId,
        otpCode: otpChallenge.otpCode,
        expiresInMinutes: otpChallenge.expiresInMinutes,
        expiresAt: otpChallenge.expiresAt,
        purpose: 'login'
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

// ─── REGISTER ─────────────────────────────────────────────────

router.post('/register', async (req, res, next) => {
  try {
    const nombre = String(req.body?.nombre ?? '').trim();
    const apellidos = String(req.body?.apellidos ?? '').trim();
    const email = String(req.body?.email ?? '').trim().toLowerCase();
    const password = String(req.body?.password ?? '');

    if (!nombre) {
      return res.status(400).json({
        message: 'El nombre es requerido.'
      });
    }

    if (!EMAIL_REGEX.test(email)) {
      return res.status(400).json({
        message: 'El correo electronico no es valido.'
      });
    }

    if (password.length < 6) {
      return res.status(400).json({
        message: 'La contrasena debe tener al menos 6 caracteres.'
      });
    }

    if (emailExists(email)) {
      return res.status(409).json({
        message: 'Ya existe una cuenta con ese correo electronico.'
      });
    }

    const passwordSalt = generateSalt(email);
    const passwordHash = hashPassword(password, passwordSalt);
    const fullName = [nombre, apellidos].filter(Boolean).join(' ');

    const otpChallenge = createRegistrationChallenge({
      nombre,
      apellidos,
      email,
      passwordHash,
      passwordSalt
    });

    try {
      await sendOtpEmail({
        to: email,
        recipientName: fullName,
        challengeId: otpChallenge.challengeId,
        otpCode: otpChallenge.otpCode,
        expiresInMinutes: otpChallenge.expiresInMinutes,
        expiresAt: otpChallenge.expiresAt,
        purpose: 'registro'
      });
    } catch (error) {
      discardOtpChallenge(otpChallenge.challengeId);
      throw error;
    }

    const payload = {
      message: 'Codigo de verificacion enviado al correo electronico.',
      challengeId: otpChallenge.challengeId,
      expiresAt: otpChallenge.expiresAt,
      maskedEmail: maskEmail(email)
    };

    if (EXPOSE_OTP_IN_RESPONSE) {
      payload.devOtpCode = otpChallenge.otpCode;
    }

    return res.status(201).json(payload);
  } catch (error) {
    return next(error);
  }
});

// ─── VERIFY OTP (login + registro) ───────────────────────────

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
    const success = buildOtpSuccessPayload(result);
    return res.status(success.statusCode).json(success.payload);
  }

  return sendOtpVerificationErrorResponse(res, result);
});

// ─── VERIFY EMAIL LINK (magic button) ────────────────────────

router.post('/verify-email-link', (req, res) => {
  const token = String(req.body?.token ?? '').trim();

  if (!token) {
    return res.status(400).json({
      message: 'Token del enlace requerido.'
    });
  }

  const tokenData = verifyOtpMagicLinkToken(token);
  if (!tokenData.ok) {
    return res.status(400).json({
      message: 'El enlace es invalido o ya expiro. Solicita un nuevo codigo.',
      code: tokenData.code
    });
  }

  const result = verifyOtpChallenge({
    challengeId: tokenData.challengeId,
    otpCode: tokenData.otpCode
  });

  if (result.status === 'ok') {
    const success = buildOtpSuccessPayload(result);
    return res.status(success.statusCode).json({
      ...success.payload,
      tipo: result.tipo
    });
  }

  return sendOtpVerificationErrorResponse(res, result);
});

router.get('/verify-email-link', (req, res) => {
  const token = String(req.query?.token ?? '').trim();

  if (!token) {
    return res.redirect(
      buildMagicLinkErrorRedirect('missing_token', 'El enlace es invalido o incompleto.')
    );
  }

  const tokenData = verifyOtpMagicLinkToken(token);
  if (!tokenData.ok) {
    return res.redirect(
      buildMagicLinkErrorRedirect(
        tokenData.code,
        'El enlace expiro o no es valido. Solicita un nuevo codigo.'
      )
    );
  }

  const result = verifyOtpChallenge({
    challengeId: tokenData.challengeId,
    otpCode: tokenData.otpCode
  });

  if (result.status !== 'ok') {
    return res.redirect(buildMagicLinkErrorRedirect(result.code, result.message));
  }

  const success = buildOtpSuccessPayload(result);
  if (success.statusCode >= 400) {
    return res.redirect(buildMagicLinkErrorRedirect('cannot_complete', success.payload.message));
  }

  return res.redirect(buildMagicLinkSuccessRedirect(result, success.payload));
});

// ─── FORGOT PASSWORD ──────────────────────────────────────────

router.post('/forgot-password', async (req, res, next) => {
  try {
    const email = String(req.body?.email ?? '').trim().toLowerCase();

    if (!EMAIL_REGEX.test(email)) {
      return res.status(400).json({
        message: 'El correo electronico no es valido.'
      });
    }

    const user = findUserByEmail(email);
    if (!user) {
      // Don't reveal whether the email exists
      return res.status(200).json({
        message: 'Si el correo esta registrado, recibiras un codigo para cambiar tu contrasena.',
        challengeId: '',
        expiresAt: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
        maskedEmail: maskEmail(email)
      });
    }

    const otpChallenge = createPasswordResetChallenge(user);

    try {
      await sendOtpEmail({
        to: user.email,
        recipientName: user.name,
        challengeId: otpChallenge.challengeId,
        otpCode: otpChallenge.otpCode,
        expiresInMinutes: otpChallenge.expiresInMinutes,
        expiresAt: otpChallenge.expiresAt,
        purpose: 'reset-password'
      });
    } catch (error) {
      discardOtpChallenge(otpChallenge.challengeId);
      throw error;
    }

    const payload = {
      message: 'Codigo para cambio de contrasena enviado al correo electronico.',
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

// ─── RESET PASSWORD ───────────────────────────────────────────

router.post('/reset-password', (req, res) => {
  const resetToken = String(req.body?.resetToken ?? req.body?.token ?? '').trim();
  const newPassword = String(req.body?.newPassword ?? '');

  if (!resetToken) {
    return res.status(400).json({
      message: 'Token de restablecimiento requerido.'
    });
  }

  if (newPassword.length < 6) {
    return res.status(400).json({
      message: 'La nueva contrasena debe tener al menos 6 caracteres.'
    });
  }

  const tokenData = consumeResetToken(resetToken);
  if (!tokenData) {
    return res.status(400).json({
      message: 'El enlace de restablecimiento expiro o ya fue usado. Solicita uno nuevo.'
    });
  }

  const passwordSalt = generateSalt(tokenData.email);
  const passwordHash = hashPassword(newPassword, passwordSalt);
  const updated = updatePassword(tokenData.userId, passwordHash, passwordSalt);

  if (!updated) {
    return res.status(404).json({
      message: 'No se encontro la cuenta.'
    });
  }

  return res.status(200).json({
    message: 'Contrasena actualizada exitosamente. Ya puedes iniciar sesion.'
  });
});

// ─── RESEND OTP ───────────────────────────────────────────────

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
      challengeId: result.challengeId,
      otpCode: result.otpCode,
      expiresInMinutes: result.expiresInMinutes,
      expiresAt: result.expiresAt,
      purpose:
        result.tipo === 'registro'
          ? 'registro'
          : result.tipo === 'reset-password'
            ? 'reset-password'
            : 'login'
    });

    const payload = {
      message:
        result.tipo === 'reset-password'
          ? 'Nuevo codigo de recuperacion enviado correctamente.'
          : 'Nuevo codigo OTP enviado correctamente.',
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

// ─── GOOGLE AUTH ──────────────────────────────────────────────

router.post('/google', async (req, res, next) => {
  try {
    const idToken = String(req.body?.idToken ?? '').trim();

    if (!idToken) {
      return res.status(400).json({
        message: 'Token de Google requerido.'
      });
    }

    // Verify the Google ID token via Google's tokeninfo endpoint
    let googleData;
    try {
      const response = await fetch(`https://oauth2.googleapis.com/tokeninfo?id_token=${encodeURIComponent(idToken)}`);
      if (!response.ok) {
        return res.status(401).json({
          message: 'Token de Google invalido o expirado.'
        });
      }
      googleData = await response.json();
    } catch {
      return res.status(502).json({
        message: 'No se pudo verificar el token con Google. Intenta de nuevo.'
      });
    }

    const email = (googleData.email || '').trim().toLowerCase();
    if (!email || googleData.email_verified !== 'true') {
      return res.status(401).json({
        message: 'El correo de Google no esta verificado.'
      });
    }

    const nombre = googleData.given_name || googleData.name || 'Usuario';
    const apellidos = googleData.family_name || '';
    const google_id = googleData.sub || null;
    const profile_picture = googleData.picture || null;

    const user = addOrFindGoogleUser({ email, nombre, apellidos, google_id, profile_picture });

    const session = createSession({
      userId: user.id,
      email: user.email,
      name: user.name,
      role: user.role,
      profile_picture: user.profile_picture
    });

    return res.status(200).json({
      message: 'Sesion iniciada con Google exitosamente.',
      session,
      user: {
        id: user.id,
        email: user.email,
        name: user.name,
        role: user.role,
        profile_picture: user.profile_picture
      }
    });
  } catch (error) {
    return next(error);
  }
});

// ─── GET /auth/me ─────────────────────────────────────────────

router.get('/me', authenticate, (req, res) => {
  return res.status(200).json({
    id: req.user.id,
    name: req.user.name,
    email: req.user.email,
    role: req.user.role,
    profile_picture: req.user.profile_picture
  });
});

// ─── SESSION ──────────────────────────────────────────────────

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

// ─── LOGOUT ───────────────────────────────────────────────────

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
