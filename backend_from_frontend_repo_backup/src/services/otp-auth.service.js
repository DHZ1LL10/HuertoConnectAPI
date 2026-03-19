const { generateOtpCode, generateRandomId, hashOtpCode, constantTimeEqualHex } = require('../utils/security');

const OTP_TTL_MS = 5 * 60 * 1000;
const OTP_EXPIRATION_MINUTES = 5;
const CHALLENGE_RETENTION_MS = 30 * 60 * 1000;
const SESSION_TTL_MS = 8 * 60 * 60 * 1000;
const MAX_VERIFY_ATTEMPTS = 5;
const MAX_RESENDS = 3;

const otpChallenges = new Map();
const sessions = new Map();

let cleanupWorkerStarted = false;

function createOtpChallenge(user) {
  const challengeId = generateRandomId(16);
  const otpCode = generateOtpCode();
  const now = Date.now();
  const challenge = {
    id: challengeId,
    userId: user.id,
    name: user.name,
    email: user.email,
    otpHash: hashOtpCode({ challengeId, otpCode }),
    createdAt: now,
    updatedAt: now,
    expiresAt: now + OTP_TTL_MS,
    verifyAttempts: 0,
    resendCount: 0
  };

  otpChallenges.set(challengeId, challenge);

  return {
    challengeId,
    otpCode,
    expiresAt: new Date(challenge.expiresAt).toISOString(),
    expiresInMinutes: OTP_EXPIRATION_MINUTES
  };
}

function verifyOtpChallenge({ challengeId, otpCode }) {
  const challenge = otpChallenges.get(challengeId);

  if (!challenge) {
    return {
      status: 'error',
      code: 'challenge_not_found',
      message: 'El proceso de verificacion no existe o ya expiro.'
    };
  }

  const now = Date.now();
  if (now > challenge.expiresAt) {
    return {
      status: 'error',
      code: 'otp_expired',
      message: 'El codigo OTP expiro. Solicita un nuevo codigo.',
      allowResend: true
    };
  }

  if (challenge.verifyAttempts >= MAX_VERIFY_ATTEMPTS) {
    return {
      status: 'error',
      code: 'too_many_attempts',
      message: 'Superaste el limite de intentos. Solicita un nuevo codigo.',
      allowResend: true
    };
  }

  const hashedCandidate = hashOtpCode({ challengeId, otpCode });
  const isValid = constantTimeEqualHex(challenge.otpHash, hashedCandidate);

  if (!isValid) {
    challenge.verifyAttempts += 1;
    challenge.updatedAt = now;
    return {
      status: 'error',
      code: 'invalid_otp',
      message: 'El codigo OTP es incorrecto.',
      remainingAttempts: Math.max(0, MAX_VERIFY_ATTEMPTS - challenge.verifyAttempts),
      allowResend: true
    };
  }

  otpChallenges.delete(challengeId);

  const session = createSession({
    userId: challenge.userId,
    email: challenge.email,
    name: challenge.name
  });

  return {
    status: 'ok',
    session,
    user: {
      id: challenge.userId,
      email: challenge.email,
      name: challenge.name
    }
  };
}

function regenerateOtpForChallenge(challengeId) {
  const challenge = otpChallenges.get(challengeId);

  if (!challenge) {
    return {
      status: 'error',
      code: 'challenge_not_found',
      message: 'No se encontro un proceso OTP activo.'
    };
  }

  if (challenge.resendCount >= MAX_RESENDS) {
    return {
      status: 'error',
      code: 'resend_limit_reached',
      message: 'Ya alcanzaste el limite de reenvios para este codigo.'
    };
  }

  const now = Date.now();
  const otpCode = generateOtpCode();

  challenge.otpHash = hashOtpCode({ challengeId, otpCode });
  challenge.expiresAt = now + OTP_TTL_MS;
  challenge.updatedAt = now;
  challenge.verifyAttempts = 0;
  challenge.resendCount += 1;

  return {
    status: 'ok',
    challengeId,
    otpCode,
    expiresAt: new Date(challenge.expiresAt).toISOString(),
    expiresInMinutes: OTP_EXPIRATION_MINUTES,
    email: challenge.email,
    name: challenge.name
  };
}

function discardOtpChallenge(challengeId) {
  otpChallenges.delete(challengeId);
}

function createSession(user) {
  const token = generateRandomId(32);
  const expiresAt = Date.now() + SESSION_TTL_MS;
  const session = {
    token,
    userId: user.userId,
    email: user.email,
    name: user.name,
    expiresAt
  };

  sessions.set(token, session);

  return {
    token,
    expiresAt: new Date(expiresAt).toISOString(),
    user: {
      id: user.userId,
      email: user.email,
      name: user.name
    }
  };
}

function getSessionFromToken(token) {
  const session = sessions.get(token);

  if (!session) {
    return null;
  }

  if (Date.now() > session.expiresAt) {
    sessions.delete(token);
    return null;
  }

  return {
    token: session.token,
    expiresAt: new Date(session.expiresAt).toISOString(),
    user: {
      id: session.userId,
      email: session.email,
      name: session.name
    }
  };
}

function revokeSession(token) {
  sessions.delete(token);
}

function cleanupExpiredRecords() {
  const now = Date.now();

  for (const [challengeId, challenge] of otpChallenges.entries()) {
    const maxLifetime = challenge.updatedAt + CHALLENGE_RETENTION_MS;
    if (now > maxLifetime) {
      otpChallenges.delete(challengeId);
    }
  }

  for (const [token, session] of sessions.entries()) {
    if (now > session.expiresAt) {
      sessions.delete(token);
    }
  }
}

function startCleanupWorker() {
  if (cleanupWorkerStarted) {
    return;
  }

  cleanupWorkerStarted = true;
  const timer = setInterval(cleanupExpiredRecords, 60_000);
  timer.unref();
}

module.exports = {
  createOtpChallenge,
  discardOtpChallenge,
  getSessionFromToken,
  regenerateOtpForChallenge,
  revokeSession,
  startCleanupWorker,
  verifyOtpChallenge
};
