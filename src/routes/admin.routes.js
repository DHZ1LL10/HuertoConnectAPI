const express = require('express');
const { getAllUsers, updateUserRole, VALID_ROLES } = require('../config/users');
const { getAllHuertos } = require('../config/huertos');
const { authenticate } = require('../middleware/authenticate');
const { authorizeRole } = require('../middleware/authorize-role');

const router = express.Router();

router.use(authenticate, authorizeRole(['admin']));

router.get('/users', (_req, res) => {
  return res.status(200).json({
    users: getAllUsers()
  });
});

router.patch('/users/:userId/role', (req, res) => {
  const userId = String(req.params?.userId ?? '').trim();
  const role = String(req.body?.role ?? '').trim().toLowerCase();

  if (!userId) {
    return res.status(400).json({
      message: 'userId es requerido.'
    });
  }

  if (!VALID_ROLES.includes(role)) {
    return res.status(400).json({
      message: `Rol invalido. Valores permitidos: ${VALID_ROLES.join(', ')}.`
    });
  }

  const result = updateUserRole(userId, role);
  if (!result.success) {
    return res.status(404).json({
      message: result.message
    });
  }

  return res.status(200).json({
    message: 'Rol actualizado correctamente.',
    user: {
      id: result.user.id,
      name: result.user.name,
      email: result.user.email,
      role: result.user.role,
      profile_picture: result.user.profile_picture
    }
  });
});

router.get('/dashboard', (_req, res) => {
  const users = getAllUsers();
  const huertos = getAllHuertos();
  const usuariosActivos = users.filter((item) => item.estado === 'Activo').length;
  const plagasDetectadas = 12;

  return res.status(200).json({
    widgets: {
      usuarios: users.length,
      usuariosActivos,
      huertosActivos: huertos.length,
      plagasDetectadas,
      actividadReciente: 27
    }
  });
});

module.exports = router;
