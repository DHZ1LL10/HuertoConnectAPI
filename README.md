<div align="center">

# 🌱 HuertoConnect API & Microservicios IA

**API REST y Gateway de Inteligencia Artificial para la plataforma Huerto Connect**  
Sistema de gestión y monitoreo inteligente de huertos con modelos de Machine Learning y Visión Artificial.

[![Status](https://img.shields.io/badge/Estado-v1.0%20MVP%20Listo%20para%20Expociencia-brightgreen)]()
[![Deploy](https://img.shields.io/badge/Deploy-AWS%20EC2%20Ubuntu-FF9900?logo=amazon-aws&logoColor=white)]()
[![Node.js](https://img.shields.io/badge/Node.js-20+-339933?logo=node.js&logoColor=white)](https://nodejs.org/)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![YOLOv8](https://img.shields.io/badge/YOLO-v8n-00FFFF?logo=pytorch&logoColor=black)]()
[![Scikit-Learn](https://img.shields.io/badge/scikit--learn-Random_Forest-F7931E?logo=scikit-learn&logoColor=white)]()
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)]()

</div>

---

## 🚀 Deployment en Producción (AWS EC2)

> **v1.0 — MVP Listo para Expociencia**

El sistema está desplegado en producción sobre una instancia **Amazon EC2 (Ubuntu, t2.micro)** con **2GB de Swap Memory** adicional para soportar los modelos de IA, orquestado completamente con **Docker Compose**.

| | |
|---|---|
| **URL Base Pública** | `http://3.17.60.253:8000` |
| **Proveedor** | Amazon Web Services (AWS EC2) |
| **SO** | Ubuntu 22.04 LTS |
| **Orquestación** | Docker Compose (5 microservicios) |
| **Memoria** | 1GB RAM + 2GB Swap |

> ⚠️ **ARQUITECTURA IMPORTANTE:** El **API Gateway (puerto 8000) ES EL ÚNICO PUNTO DE ENTRADA PÚBLICO**. Toda petición (`/api/auth`, `/api/huertos`, `/api/plagas`, etc.) pasa por el puerto `8000`. Los microservicios internos (puertos 8001, 8002, 8003) están aislados en la red interna de Docker por seguridad y **no deben ser consumidos directamente**.

---

## 📖 Descripción

**HuertoConnect API** es el núcleo backend de la plataforma Huerto Connect. Está diseñado con una arquitectura orientada a microservicios donde un **API Gateway** gestiona la seguridad, roles y autenticación, enrutando las peticiones hacia microservicios especializados en **Python/FastAPI** para el procesamiento de Inteligencia Artificial.

El sistema integra IA directamente en el flujo agrícola: recomendaciones de cultivos basadas en clima en tiempo real (Random Forest) y un motor de detección de plagas mediante visión artificial entrenado con datos reales del Estado de Veracruz (YOLOv8n).

---

## 🛠️ Stack Tecnológico & Arquitectura

### 🌐 API Gateway (Python/FastAPI — Puerto 8000)
- Punto de entrada único. Enruta peticiones hacia los microservicios internos.
- Gestiona CORS y seguridad de red.

### 🔐 Auth Service (Python/FastAPI — Interno)
- **Seguridad:** OTP de 6 dígitos, Magic Links con HMAC-SHA256, JWT Bearer Tokens.
- **Base de datos:** MongoDB (sesiones y usuarios).

### 🤖 Microservicios de IA (Python/FastAPI — Internos)
- **Huertos (ML):** `scikit-learn` y `pandas`. Modelo **Random Forest** (200 árboles) entrenado con datasets climáticos de Veracruz.
- **Plagas (Visión):** `ultralytics` (YOLOv8n), `PyTorch` y `OpenCV`. Clasifica 10 plagas comunes con Bounding Boxes y devuelve tratamientos ecológicos.

---

## 📊 Estado del Proyecto — v1.0 MVP

### ✅ Módulos Completados

| Módulo | Descripción | Endpoint |
|---|---|---|
| **Autenticación Email+OTP** | Login con 2FA por código de 6 dígitos | `POST /api/auth/send-otp` |
| **Magic Link** | Autenticación por link en email | `GET/POST /api/auth/verify-email-link` |
| **Recuperación de contraseña** | Flujo completo: forgot → OTP → reset | `POST /api/auth/forgot-password` |
| **Gestión de sesiones y Roles** | JWT con roles `admin`, `manager`, `user` | `GET /api/auth/session` |
| **IA — Recomendación de Cultivos** | Clima en vivo (OpenWeather) + Random Forest | `POST /api/huertos/recomendar` |
| **IA — Detección de Plagas** | Visión artificial YOLOv8n sobre imagen foliar | `POST /api/plagas/detectar` |

### 🚧 Siguiente Iteración

| Módulo | Prioridad |
|---|---|
| **Persistencia PostgreSQL + Prisma ORM** | 🔴 Alta |
| **CRUD Tareas Agrícolas** | 🔴 Alta |
| **Chatbot Agrónomo (IA conversacional)** | 🟡 Media |

---

## 🤖 Arquitectura de Inteligencia Artificial

### 1. Modelo Random Forest (Recomendación de Huertos)
- **Dataset:** Histórico de clima (Veracruz) y condiciones de suelo por municipio.
- **Features (X):** `temp_max`, `temp_min`, `humedad`, `municipio` (One-Hot Encoded), `tipo_suelo` (Ordinal).
- **Target (Y):** Cultivo de mayor viabilidad.
- **Pipeline:** 200 árboles de decisión + codificadores empaquetados en `.pkl`. Inferencia en < 50ms.

### 2. Detección de Objetos YOLOv8n (Control de Plagas)
- **Tecnología:** Red neuronal convolucional "You Only Look Once" v8 Nano (PyTorch).
- **Dataset:** Imágenes reales etiquetadas: `mosca_blanca`, `pulgon_verde`, `arana_roja`, `gusano_cogollero`, `roya` y más.
- **Proceso:** La imagen es descargada, procesada tensorialmente y evaluada. La clase inferida se cruza con base de conocimiento de tratamientos ecológicos, biológicos y culturales.

---

## ⚙️ Instalación y Uso Local

```bash
git clone https://github.com/DHZ1LL10/HuertoConnectAPI.git
cd HuertoConnectAPI
cp .env.example .env
# Editar .env con tus credenciales
sudo docker compose up -d --build
```

---

## 🔒 Seguridad Implementada
- Timing-Attack safe con `crypto.timingSafeEqual`.
- Rate Limiting en endpoints de OTP (máx. 5 intentos).
- Contraseñas con `scrypt` + Salt Individual + Pepper de servidor.
- Microservicios aislados en red bridge privada de Docker (no accesibles desde internet).

---

<div align="center">
Desarrollado para <b>Huerto Connect</b> — Innovando la agricultura con IA 🚀<br/>
<i>v1.0 MVP — Expociencia 2026</i>
</div>
