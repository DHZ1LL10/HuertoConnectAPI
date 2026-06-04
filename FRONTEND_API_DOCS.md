# 📚 HuertoConnect — Guía de Consumo de API para el Equipo Frontend

> **v1.0 MVP — Producción en AWS EC2**  
> Última actualización: Junio 2026

Este documento es la referencia oficial para que el equipo de Frontend (Web / Móvil) pueda conectarse al backend de Huerto Connect que ya está corriendo en producción.

---

## 🌐 URL Base de Producción

```
http://3.17.60.253:8000
```

> ⚠️ **REGLA DE ORO — LEE ESTO PRIMERO:**
>
> **EL PUERTO 8000 ES EL ÚNICO PUNTO DE ENTRADA.** El API Gateway enruta internamente hacia los microservicios de autenticación, huertos y plagas. **NO intentes conectarte a los puertos 8001, 8002 o 8003 directamente desde la app.** Esos puertos están bloqueados en el firewall de AWS por seguridad y no responderán. Todas tus peticiones deben ir al puerto `8000`, sin excepción.

---

## 🔑 Autenticación

Antes de poder consumir cualquier endpoint de IA, el usuario debe iniciar sesión. El login te devuelve un **Token JWT** que debes guardar en `SecureStorage` (móvil) o `localStorage` (web) y mandarlo en todas las demás peticiones.

### Flujo de Login Completo

**Paso 1 — Enviar credenciales:**
```http
POST http://3.17.60.253:8000/api/auth/send-otp
Content-Type: application/json

{
  "email": "usuario@correo.com",
  "password": "Password123!"
}
```
*→ Response: El sistema envía un código OTP de 6 dígitos al correo.*

**Paso 2 — Verificar OTP y obtener Token:**
```http
POST http://3.17.60.253:8000/api/auth/verify-otp
Content-Type: application/json

{
  "email": "usuario@correo.com",
  "otp": "123456"
}
```
*→ Response: Devuelve `{ "token": "eyJhbGci..." }` — **¡GUARDA ESTE TOKEN!***

---

## 📋 Endpoints de Autenticación (`/api/auth`)

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| `POST` | `/api/auth/register` | Registrar nuevo usuario | — |
| `POST` | `/api/auth/send-otp` | Iniciar Login (envía OTP al correo) | — |
| `POST` | `/api/auth/verify-otp` | Verificar OTP y obtener JWT | — |
| `POST` | `/api/auth/resend-otp` | Reenviar código OTP | — |
| `POST` | `/api/auth/forgot-password` | Iniciar recuperación de contraseña | — |
| `POST` | `/api/auth/reset-password` | Cambiar contraseña con resetToken | — |
| `POST` | `/api/auth/google` | Login/Registro con Google ID Token | — |
| `GET` | `/api/auth/me` | Datos del usuario autenticado | ✅ Bearer |
| `GET` | `/api/auth/session` | Validar si el token sigue activo | ✅ Bearer |
| `POST` | `/api/auth/logout` | Cerrar sesión (revocar token) | ✅ Bearer |

**Headers para rutas protegidas (con ✅):**
```http
Authorization: Bearer eyJhbGciOiJIUz...
Content-Type: application/json
```

---

## 🤖 Endpoint de IA: Recomendación de Cultivos

Descarga el clima en tiempo real de OpenWeather y lo pasa por el modelo Random Forest para recomendar los 3 mejores cultivos.

```http
POST http://3.17.60.253:8000/api/huertos/recomendar
Authorization: Bearer <TU_TOKEN>
Content-Type: application/json

{
  "lat": 19.5312,
  "lon": -96.9276,
  "municipio": "Xalapa"
}
```

**Response exitosa:**
```json
{
  "clima": {
    "temp_actual": 17.8,
    "humedad": 97,
    "descripcion": "Lluvia ligera",
    "ciudad": "Xalapa"
  },
  "recomendaciones": [
    {
      "cultivo": "Tomate",
      "confianza": 0.85,
      "justificacion": "Modelo predictivo basado en Xalapa, temp: 17.8°C, humedad: 97%",
      "temporada_ideal": "Otoño-Invierno (Oct–Feb)",
      "tecnica_riego": "Goteo, cada 2 días"
    }
  ],
  "modo": "modelo_real"
}
```

---

## 🐛 Endpoint de IA: Detección de Plagas (Visión Artificial)

Analiza una foto foliar a través de YOLOv8n para detectar la plaga y devolver tratamientos ecológicos.

> **Nota:** Primero sube la foto a Cloudinary/Firebase Storage desde la app y manda la URL pública aquí.

```http
POST http://3.17.60.253:8000/api/plagas/detectar
Authorization: Bearer <TU_TOKEN>
Content-Type: application/json

{
  "imagen_url": "https://res.cloudinary.com/tu-cloud/image/upload/foto.jpg"
}
```

**Response exitosa:**
```json
{
  "deteccion": {
    "plaga": "Pulgon Verde",
    "nombre_cientifico": "Myzus persicae",
    "confianza": 0.72,
    "severidad": "Media",
    "descripcion_plaga": "Áfido verde que coloniza brotes...",
    "cultivos_afectados": ["Chile", "Jitomate"],
    "tratamientos_ecologicos": [
      {
        "nombre": "Extracto de ajo y chile",
        "tipo": "botanico",
        "aplicacion": "50g ajo + 50g chile / L agua. Filtrar, diluir 1:10.",
        "frecuencia": "Cada 5 días"
      }
    ]
  },
  "modo": "modelo_real"
}
```

---

## 💡 Buenas Prácticas UI/UX

1. **Token vencido (HTTP 401):** Cierra sesión inmediatamente y manda al usuario a la pantalla de Login.
2. **Loading States:** Los endpoints de IA pueden tardar de 1 a 3 segundos. Muestra un spinner o skeleton loader, nunca dejes la pantalla congelada.
3. **Campo `modo`:** Si la respuesta dice `"modo": "mock"`, significa que el servidor no tiene los modelos cargados. Avísenle al backend. En producción siempre debe decir `"modo": "modelo_real"`.
4. **Campo `nota_mitigacion`:** Si viene con texto (no null) en la respuesta de plagas, muéstralo en pantalla como un "tip de experto" — es una advertencia inteligente del modelo.
5. **Severidad de plagas:** Usa el campo `severidad` para pintar el ícono con colores: `Alta` = 🔴, `Media` = 🟡, `Baja` = 🟢.

---

## 👥 Credenciales de Prueba

Para hacer pruebas durante el desarrollo (modo consola, el OTP aparece en los logs del servidor):

| Email | Contraseña | Rol |
|---|---|---|
| `admin@huertoconnect.com` | `Admin12345!` | `admin` |
| `manager@huertoconnect.com` | `Manager123!` | `manager` |
| `productor@huertoconnect.com` | `Productor123!` | `user` |
