/**
 * Middleware factory: authorizeRole
 *
 * Usage:
 *   authorizeRole(['admin'])              — only admins
 *   authorizeRole(['admin', 'manager'])   — admins and managers
 *
 * Requires `authenticate` middleware to run before this one
 * so that req.user is populated.
 */
function authorizeRole(allowedRoles) {
  return (req, res, next) => {
    if (!req.user) {
      return res.status(401).json({
        message: 'No autenticado.'
      });
    }

    if (!allowedRoles.includes(req.user.role)) {
      return res.status(403).json({
        message: 'No tienes permisos para acceder a este recurso.'
      });
    }

    next();
  };
}

module.exports = { authorizeRole };
