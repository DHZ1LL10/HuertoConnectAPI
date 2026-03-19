const { getSessionFromToken } = require('../services/otp-auth.service');
const { findUserById } = require('../config/users');

/**
 * Middleware: authenticate
 * Extracts Bearer token from Authorization header, loads session,
 * and attaches full user data (including role) to req.user.
 */
function authenticate(req, res, next) {
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

  // Load fresh user data from store (includes role, profile picture, etc.)
  const user = findUserById(session.user.id);

  if (!user) {
    return res.status(401).json({
      message: 'Usuario no encontrado.'
    });
  }

  req.user = {
    id: user.id,
    name: user.name,
    email: user.email,
    role: user.role,
    profile_picture: user.profile_picture
  };

  req.session = session;
  next();
}

module.exports = { authenticate };
