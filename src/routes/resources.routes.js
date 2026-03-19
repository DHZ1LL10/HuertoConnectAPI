const express = require('express');
const { authenticate } = require('../middleware/authenticate');
const { authorizeRole } = require('../middleware/authorize-role');
const { getAllHuertos, getHuertosByUserId, getUserDashboard } = require('../config/huertos');

const router = express.Router();

router.get('/huertos', authenticate, authorizeRole(['admin', 'manager']), (_req, res) => {
  return res.status(200).json({
    huertos: getAllHuertos()
  });
});

router.get('/user/huertos', authenticate, authorizeRole(['user']), (req, res) => {
  return res.status(200).json({
    huertos: getHuertosByUserId(req.user.id)
  });
});

router.get('/user/dashboard', authenticate, authorizeRole(['user']), (req, res) => {
  return res.status(200).json(getUserDashboard(req.user.id));
});

module.exports = router;
