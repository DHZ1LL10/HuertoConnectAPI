require('dotenv').config();
const express = require('express');
const cors = require('cors');
const authRoutes = require('./routes/auth.routes');
const { startCleanupWorker } = require('./services/otp-auth.service');

const FRONTEND_ORIGIN = process.env.FRONTEND_ORIGIN || 'http://localhost:4200';

const app = express();

app.disable('x-powered-by');
app.use(
  cors({
    origin: FRONTEND_ORIGIN
  })
);
app.use(express.json({ limit: '100kb' }));

app.get('/api/health', (_req, res) => {
  res.status(200).json({
    service: 'huerto-connect-auth-api',
    status: 'ok'
  });
});

app.use('/api/auth', authRoutes);

app.use((error, _req, res, _next) => {
  console.error('[auth-api]', error);
  res.status(500).json({
    message: 'Error interno del servidor.'
  });
});

startCleanupWorker();

module.exports = app;
