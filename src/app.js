require('dotenv').config();
const express = require('express');
const cors = require('cors');
const authRoutes = require('./routes/auth.routes');
const adminRoutes = require('./routes/admin.routes');
const resourcesRoutes = require('./routes/resources.routes');
const { startCleanupWorker } = require('./services/otp-auth.service');

const DEFAULT_ALLOWED_ORIGINS = [
  'http://localhost:4200',
  'http://127.0.0.1:4200',
  'https://huertoconnect.netlify.app'
];

const envOrigins = String(process.env.FRONTEND_ORIGIN || '')
  .split(',')
  .map((origin) => origin.trim())
  .filter(Boolean);

const allowedOrigins = new Set([...DEFAULT_ALLOWED_ORIGINS, ...envOrigins]);

const app = express();

app.disable('x-powered-by');
app.use(
  cors({
    origin(origin, callback) {
      if (!origin || allowedOrigins.has(origin)) {
        callback(null, true);
        return;
      }

      callback(new Error(`Origin not allowed by CORS: ${origin}`));
    }
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
app.use('/api/admin', adminRoutes);
app.use('/api', resourcesRoutes);

app.use((error, _req, res, _next) => {
  console.error('[auth-api]', error);
  res.status(500).json({
    message: 'Error interno del servidor.'
  });
});

startCleanupWorker();

module.exports = app;
