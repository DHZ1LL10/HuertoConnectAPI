# Huerto Connect API

API de autenticacion con Email OTP para Huerto Connect.


## Requisitos
- Node.js 20+

## Configuracion
1. Copia `.env.example` a `.env`.
2. Ajusta credenciales SMTP y secretos.

## Ejecutar
```bash
npm install
npm start
```

API por defecto: `http://localhost:3000`

## Endpoints
- `POST /api/auth/send-otp`
- `POST /api/auth/verify-otp`
- `POST /api/auth/verify-email-link`
- `GET /api/auth/verify-email-link`
- `POST /api/auth/resend-otp`
- `POST /api/auth/register`
- `POST /api/auth/forgot-password`
- `POST /api/auth/reset-password`
- `GET /api/auth/session`
- `POST /api/auth/logout`

## Boton de correo (enlace magico)
- El boton del email ahora consume automaticamente el OTP (sin capturarlo manualmente).
- Si el flujo es login/registro, valida el codigo y genera sesion.
- Si el flujo es recuperacion, valida el codigo y genera `resetToken` para cambio de contrasena.
- El endpoint `GET /api/auth/verify-email-link` redirige al frontend con parametros segun el resultado.
- Login/registro redirige con `sessionToken`, `sessionExpiresAt`, `userEmail`, `userName`, `redirectTo`.
- Recuperacion redirige con `flow=forgot-reset` y `resetToken`.
