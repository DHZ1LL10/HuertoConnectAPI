<div align="center">

# 🌱 HuertoConnect API

**API REST para la plataforma Huerto Connect**  
Sistema de gestión y monitoreo inteligente de huertos con integración de Inteligencia Artificial.

[![Node.js](https://img.shields.io/badge/Node.js-20+-339933?logo=node.js&logoColor=white)](https://nodejs.org/)
[![Express](https://img.shields.io/badge/Express-5.x-000000?logo=express&logoColor=white)](https://expressjs.com/)
[![License](https://img.shields.io/badge/License-Private-red)](LICENSE)
[![Status](https://img.shields.io/badge/Status-En%20Desarrollo-yellow)]()

</div>

---

## 📖 Descripción

**HuertoConnect API** es el núcleo backend de la plataforma Huerto Connect. Gestiona la autenticación segura de usuarios, el acceso controlado por roles y expone los endpoints necesarios para el registro, monitoreo y análisis de huertos agrícolas.

La arquitectura está diseñada para escalar como **Gateway de Inteligencia Artificial**, enrutando peticiones hacia microservicios de ML/DL en Python para recomendaciones agrícolas personalizadas, análisis predictivo de plagas y optimización de riego.

---

## 🛠️ Stack Tecnológico

| Capa | Tecnología | Versión |
|---|---|---|
| Runtime | Node.js | 20+ |
| Framework | Express | 5.x |
| Email / OTP | Nodemailer | 7.x |
| Imágenes | Sharp | 0.34.x |
| Variables de entorno | dotenv | 17.x |
| Base de datos *(próximo)* | PostgreSQL + Prisma | — |
| IA Gateway *(próximo)* | HTTP hacia microservicios Python | — |

### Seguridad implementada
- Hash de contraseñas con `crypto.scryptSync` + salt individual + pepper global
- Comparación con `crypto.timingSafeEqual` (resistente a timing attacks)
- OTP de 6 dígitos con expiración y límite de intentos
- Magic Link firmado con HMAC-SHA256 (uso único)
- Sesiones basadas en tokens Bearer
- CORS estricto con lista de orígenes permitidos
- Body limit de 100 KB

---

## 📊 Estado del Proyecto

### ✅ Módulos Completados

| Módulo | Descripción | Endpoint(s) |
|---|---|---|
| **Autenticación Email+Password** | Login con validación de credenciales y 2FA por OTP | `POST /api/auth/send-otp` |
| **Verificación OTP** | Validación de código de 6 dígitos con reintentos limitados | `POST /api/auth/verify-otp` |
| **Magic Link por Email** | Botón de email que autentica automáticamente al usuario | `GET/POST /api/auth/verify-email-link` |
| **Reenvío de OTP** | Regeneración de código con rate limiting | `POST /api/auth/resend-otp` |
| **Registro con verificación** | Flujo completo: registro → OTP → creación de cuenta | `POST /api/auth/register` |
| **Recuperación de contraseña** | Flujo completo: forgot → OTP → reset | `POST /api/auth/forgot-password` + `reset-password` |
| **Google OAuth** | Login/registro con Google ID Token | `POST /api/auth/google` |
| **Gestión de sesiones** | Validación y revocación de tokens Bearer | `GET /api/auth/session` + `POST /api/auth/logout` |
| **Perfil autenticado** | Endpoint protegido para obtener datos del usuario actual | `GET /api/auth/me` |
| **Control de roles** | Sistema de roles: `admin`, `manager`, `user` | Middleware `authorizeRole` |
| **Dashboard Admin** | Estadísticas globales del sistema (datos en memoria) | `GET /api/admin/dashboard` |
| **Gestión de usuarios (Admin)** | Listado y cambio de roles | `GET/PATCH /api/admin/users` |
| **Recursos de usuario** | Huertos y dashboard del productor (datos en memoria) | `GET /api/user/huertos` + `/dashboard` |
| **Health Check** | Verificación de estado del servicio | `GET /api/health` |

### 🚧 En Desarrollo

| Módulo | Descripción | Prioridad |
|---|---|---|
| **Persistencia con PostgreSQL** | Reemplazar almacenamiento en memoria con Prisma ORM | 🔴 Alta |
| **CRUD Huertos** | Crear, listar, actualizar y eliminar huertos por usuario | 🔴 Alta |
| **CRUD Cultivos** | Gestión de cultivos asociados a cada huerto | 🔴 Alta |
| **CRUD Tareas** | Registro de tareas: riego, fertilización, poda, cosecha | 🔴 Alta |
| **Dashboard Admin (datos reales)** | Estadísticas y reportes consultados desde BD | 🟡 Media |
| **Reportes Administrativos** | Exportación de actividad, cultivos y usuarios | 🟡 Media |
| **AI Gateway — Chat** | Proxy hacia microservicio Python para asistente agrícola | 🟡 Media |
| **AI Gateway — Recommendations** | Recomendaciones personalizadas por huerto via IA | 🟡 Media |
| **AI Gateway — Análisis** | Análisis predictivo de salud del huerto | 🟢 Baja |

---

## 📁 Estructura del Proyecto

```
huerto-connect-api/
├── src/
│   ├── app.js                          # Configuración Express, CORS y montaje de rutas
│   ├── server.js                       # Punto de entrada, inicia el servidor HTTP
│   │
│   ├── config/
│   │   ├── users.js                    # Store de usuarios (actualmente en memoria)
│   │   └── huertos.js                  # Store de huertos/dashboard (actualmente en memoria)
│   │
│   ├── middleware/
│   │   ├── authenticate.js             # Valida token Bearer de sesión
│   │   └── authorize-role.js           # Verifica roles requeridos por ruta
│   │
│   ├── routes/
│   │   ├── auth.routes.js              # Todos los endpoints de autenticación
│   │   ├── admin.routes.js             # Endpoints del panel administrativo (solo admin)
│   │   └── resources.routes.js         # Recursos del usuario autenticado
│   │
│   ├── services/
│   │   ├── otp-auth.service.js         # Lógica de challenges OTP, sesiones y reset tokens
│   │   └── mailer.service.js           # Envío de emails via SMTP (Nodemailer)
│   │
│   ├── templates/
│   │   └── otp-email.template.js       # Template HTML del email OTP con Magic Link
│   │
│   └── utils/
│       └── security.js                 # Helpers: maskEmail, sanitizeOtp, verifyMagicLinkToken
│
├── .env                                # Variables de entorno locales (no se sube al repo)
├── .env.example                        # Plantilla de variables de entorno
├── package.json
└── README.md
```

---

## ⚙️ Instalación y Uso Local

### Requisitos previos
- **Node.js** 20 o superior
- **npm** 9 o superior
- Una cuenta de Gmail con [App Password](https://myaccount.google.com/apppasswords) habilitada *(solo para modo SMTP real)*

### 1. Clonar el repositorio

```bash
git clone https://github.com/DHZ1LL10/HuertoConnectAPI.git
cd HuertoConnectAPI
```

### 2. Instalar dependencias

```bash
npm install
```

### 3. Configurar variables de entorno

```bash
cp .env.example .env
```

Edita el archivo `.env` con tus valores:

```env
# Servidor
API_PORT=3000
API_PUBLIC_URL=http://localhost:3000

# Frontend (para CORS y redirecciones del Magic Link)
FRONTEND_URL=http://localhost:4200
FRONTEND_ORIGIN=http://localhost:4200
FRONTEND_LOGIN_PATH=/login
FRONTEND_DASHBOARD_PATH=/admin

# Modo de entrega OTP:
#   "console" → imprime el código en la terminal (ideal para desarrollo)
#   "smtp"    → envía email real por SMTP
OTP_DELIVERY_MODE=console
OTP_EXPOSE_CODE_IN_RESPONSE=true   # Solo en desarrollo. Eliminar en producción.

# Credenciales SMTP (solo requerido si OTP_DELIVERY_MODE=smtp)
OTP_EMAIL_HOST=smtp.gmail.com
OTP_EMAIL_PORT=465
OTP_EMAIL_SECURE=true
OTP_EMAIL_USER=tu-email@gmail.com
OTP_EMAIL_APP_PASSWORD=tu_app_password_de_16_caracteres

# Secretos de seguridad (CAMBIAR en producción)
OTP_HASH_SECRET=change-this-otp-secret
OTP_LINK_SECRET=change-this-otp-link-secret
AUTH_PASSWORD_PEPPER=change-this-password-pepper
```

### 4. Levantar el servidor

**Modo desarrollo (con hot reload):**
```bash
npm run start:watch
```

**Modo producción:**
```bash
npm start
```

El servidor estará disponible en: `http://localhost:3000`

### 5. Verificar que funciona

```bash
curl http://localhost:3000/api/health
# Respuesta esperada: { "service": "huerto-connect-auth-api", "status": "ok" }
```

---

## 🔑 Usuarios de Prueba

Con `OTP_DELIVERY_MODE=console`, el OTP se imprime en la terminal. Los siguientes usuarios están precargados:

| Email | Contraseña | Rol |
|---|---|---|
| `admin@huertoconnect.com` | `Admin12345!` | `admin` |
| `manager@huertoconnect.com` | `Manager123!` | `manager` |
| `productor@huertoconnect.com` | `Productor123!` | `user` |

---

## 🌐 Endpoints Disponibles

### Autenticación — `/api/auth`

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| `POST` | `/send-otp` | Inicia login, envía OTP al email | — |
| `POST` | `/verify-otp` | Verifica el código OTP | — |
| `POST` | `/verify-email-link` | Verifica token del Magic Link (API) | — |
| `GET` | `/verify-email-link` | Verifica token y redirige al frontend | — |
| `POST` | `/resend-otp` | Reenvía un nuevo código OTP | — |
| `POST` | `/register` | Registra nuevo usuario (envía OTP de verificación) | — |
| `POST` | `/forgot-password` | Envía OTP de recuperación de contraseña | — |
| `POST` | `/reset-password` | Actualiza la contraseña con resetToken | — |
| `POST` | `/google` | Login/registro con Google ID Token | — |
| `GET` | `/session` | Valida sesión activa | Bearer |
| `GET` | `/me` | Datos del usuario autenticado | Bearer |
| `POST` | `/logout` | Revoca la sesión | — |

### Recursos de Usuario — `/api`

| Método | Ruta | Descripción | Rol |
|---|---|---|---|
| `GET` | `/user/huertos` | Mis huertos | `user` |
| `GET` | `/user/dashboard` | Mi dashboard completo | `user` |
| `GET` | `/huertos` | Todos los huertos | `admin`, `manager` |

### Administración — `/api/admin` *(requiere rol `admin`)*

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/dashboard` | Estadísticas globales del sistema |
| `GET` | `/users` | Listado de todos los usuarios |
| `PATCH` | `/users/:id/role` | Cambiar rol de un usuario |

---

## 🔒 Seguridad en Producción

Antes de hacer deploy, asegúrate de:

- [ ] Cambiar todos los secretos en `.env` (`OTP_HASH_SECRET`, `OTP_LINK_SECRET`, `AUTH_PASSWORD_PEPPER`)
- [ ] Configurar `OTP_DELIVERY_MODE=smtp` con credenciales SMTP reales
- [ ] Establecer `OTP_EXPOSE_CODE_IN_RESPONSE=false`
- [ ] Configurar `FRONTEND_ORIGIN` con el dominio de producción del frontend
- [ ] Usar HTTPS en `API_PUBLIC_URL` y `FRONTEND_URL`
- [ ] Configurar `DATABASE_URL` con la cadena de conexión a PostgreSQL en producción

---

## 📄 Licencia

Proyecto privado — © 2026 HuertoConnect. Todos los derechos reservados.
