<div align="center">

# 🌱 HuertoConnect API & Microservicios IA

**API REST y Gateway de Inteligencia Artificial para la plataforma Huerto Connect**  
Sistema de gestión y monitoreo inteligente de huertos con modelos de Machine Learning y Visión Artificial.

[![Node.js](https://img.shields.io/badge/Node.js-20+-339933?logo=node.js&logoColor=white)](https://nodejs.org/)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![YOLOv8](https://img.shields.io/badge/YOLO-v8n-00FFFF?logo=pytorch&logoColor=black)]()
[![Scikit-Learn](https://img.shields.io/badge/scikit--learn-Random_Forest-F7931E?logo=scikit-learn&logoColor=white)]()

</div>

---

## 📖 Descripción

**HuertoConnect API** es el núcleo backend de la plataforma Huerto Connect. Está diseñado con una arquitectura orientada a microservicios donde un API Gateway en **Node.js/Express** gestiona la seguridad, roles y autenticación, delegando el procesamiento intensivo y el análisis predictivo a microservicios especializados en **Python/FastAPI**.

El sistema integra Inteligencia Artificial directamente en el flujo agrícola del usuario, ofreciendo recomendaciones de cultivos basadas en clima en tiempo real, y un motor de detección de plagas mediante visión artificial entrenado con datos reales del Estado de Veracruz.

---

## 🛠️ Stack Tecnológico & Arquitectura

El ecosistema está dividido en un Gateway principal y microservicios satelitales conectados por red interna (Docker Compose).

### 🖥️ API Gateway (Node.js)
- **Runtime:** Node.js 20+ con Express 5.x
- **Seguridad:** Hash con `crypto.scryptSync`, OTP (One Time Password), Magic Links con HMAC-SHA256, JWT Bearer Tokens.
- **Utilidades:** Nodemailer (SMTP), Sharp (procesamiento de imágenes).

### 🤖 Microservicios de IA (Python)
- **Framework:** FastAPI con Uvicorn + uvloop.
- **Machine Learning (Huertos):** `scikit-learn` y `pandas`. Modelo **Random Forest** entrenado con datasets climáticos de Veracruz para recomendar los mejores cultivos según temperatura, humedad y municipio.
- **Visión Artificial (Plagas):** `ultralytics` (YOLOv8n), `PyTorch` y `OpenCV`. Modelo convolucional entrenado a medida para clasificar 10 plagas comunes con cajas delimitadoras (Bounding Boxes), devolviendo tratamientos ecológicos y botánicos.

---

## 📊 Estado del Proyecto

### ✅ Módulos Completados

| Módulo | Descripción | Endpoint(s) |
|---|---|---|
| **Autenticación Email+Password** | Login con validación de credenciales y 2FA por OTP | `POST /api/auth/send-otp` |
| **Magic Link y Verificación** | Botón de email que autentica al usuario sin password | `GET/POST /api/auth/verify-email-link` |
| **Recuperación de contraseña** | Flujo completo: forgot → OTP → reset | `POST /api/auth/forgot-password` |
| **Gestión de sesiones y Roles** | Validación de JWT y roles (`admin`, `manager`, `user`) | `GET /api/auth/session` |
| **IA — Recomendación de Cultivos** | Consumo de clima en vivo (OpenWeather) e inferencia con Random Forest | `POST /api/huertos/recomendar` |
| **IA — Detección de Plagas** | Visión por computadora con YOLOv8n sobre imágenes foliares | `POST /api/plagas/detectar` |
| **Recursos y Dashboards** | Estadísticas globales y reportes del productor | `GET /api/admin/dashboard` |

### 🚧 En Desarrollo

| Módulo | Descripción | Prioridad |
|---|---|---|
| **Persistencia de Base de Datos** | Migración completa a PostgreSQL + Prisma ORM | 🔴 Alta |
| **CRUD Tareas Agrícolas** | Registro de tareas (riego, poda, cosecha) | 🔴 Alta |
| **AI Gateway — Chatbot** | Asistente conversacional especializado en agronomía | 🟡 Media |

---

## 🤖 Arquitectura de Inteligencia Artificial

### 1. Modelo Random Forest (Recomendación de Huertos)
- **Dataset:** Histórico de clima (Veracruz) y condiciones de suelo por municipio.
- **Features (X):** `temp_max`, `temp_min`, `humedad`, `municipio` (One-Hot Encoded), `tipo_suelo` (Ordinal).
- **Target (Y):** Cultivo de mayor viabilidad.
- **Pipeline:** Codificadores categóricos empaquetados junto al estimador de 200 árboles en un archivo `.pkl`. Inferencia en < 50ms.

### 2. Detección de Objetos YOLOv8n (Control de Plagas)
- **Tecnología:** Red neuronal convolucional "You Only Look Once" v8 Nano.
- **Dataset de Entrenamiento:** Imágenes reales etiquetadas (`mosca_blanca`, `pulgon_verde`, `arana_roja`, `gusano_cogollero`, `roya`, etc).
- **Proceso:** La imagen subida a Cloudinary es descargada por la API, procesada tensorialmente en PyTorch, y evaluada para cruzar la clase inferida con una base de conocimientos de *tratamientos ecológicos, biológicos y culturales*.

---

## ⚙️ Instalación y Uso Local

### 1. Requisitos previos
- **Docker Desktop** (Recomendado para correr la suite de microservicios).
- **Node.js 20+** y **Python 3.12** (Si se desea correr sin contenedores).

### 2. Levantar la plataforma con Docker

El proyecto está dockerizado para orquestar los microservicios sin fricción de dependencias:

```bash
docker-compose up -d --build
```

Esto levantará automáticamente:
1. El Gateway Node.js en el puerto `3000`.
2. El servicio de Huertos (ML) en el puerto `8000`.
3. El servicio de Plagas (Visión) en el puerto `8003`.
4. Bases de datos MongoDB y PostgreSQL aisladas.

---

## 🔒 Seguridad Implementada (A nivel Enterprise)
- Defensas contra *Timing Attacks* en comparaciones de strings criptográficos.
- Prevención de ataques de fuerza bruta mediante Rate Limiting en endpoints de OTP.
- Contraseñas cifradas con `scrypt` + Salt Individual + Pepper de servidor.
- Rutas intra-microservicio protegidas y comunicación inter-contenedores en red bridge cerrada de Docker.

---

<div align="center">
Desarrollado para <b>Huerto Connect</b> — Innovando la agricultura con IA 🚀
</div>
