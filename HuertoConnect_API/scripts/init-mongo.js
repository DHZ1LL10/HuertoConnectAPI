// ============================================================
// MongoDB Init Script - Huerto Connect
// Runs on first container start to create indexes and seed data
// ============================================================

// Switch to the application database
db = db.getSiblingDB('huerto_connect');

// ===================== INDEXES =====================

// --- usuarios ---
db.usuarios.createIndex({ "email": 1 }, { unique: true });
db.usuarios.createIndex({ "region_id": 1, "estado": 1 });
db.usuarios.createIndex({ "rol": 1 });
db.usuarios.createIndex({ "deleted_at": 1 });

// --- otp_challenges ---
db.otp_challenges.createIndex({ "usuario_id": 1, "tipo": 1, "expires_at": 1 });
db.otp_challenges.createIndex({ "expires_at": 1 }, { expireAfterSeconds: 0 });

// --- password_resets ---
db.password_resets.createIndex({ "token_hash": 1 }, { unique: true });
db.password_resets.createIndex({ "usuario_id": 1, "expires_at": 1, "used_at": 1 });
db.password_resets.createIndex({ "expires_at": 1 }, { expireAfterSeconds: 3600 });

// --- sesiones ---
db.sesiones.createIndex({ "token_hash": 1 }, { unique: true });
db.sesiones.createIndex({ "usuario_id": 1, "activa": 1, "expires_at": 1 });
db.sesiones.createIndex({ "expires_at": 1 }, { expireAfterSeconds: 0 });

// --- huertos ---
db.huertos.createIndex({ "usuario_id": 1 });
db.huertos.createIndex({ "region_id": 1, "estado": 1 });
db.huertos.createIndex({ "deleted_at": 1 });

// --- regiones ---
db.regiones.createIndex({ "nombre": 1 }, { unique: true });

// --- cultivos ---
db.cultivos.createIndex({ "nombre": 1 });
db.cultivos.createIndex({ "activo": 1 });

// --- huerto_cultivos ---
db.huerto_cultivos.createIndex({ "huerto_id": 1, "cultivo_id": 1 });
db.huerto_cultivos.createIndex({ "estado": 1 });

// --- plantios ---
db.plantios.createIndex({ "huerto_cultivo_id": 1 });
db.plantios.createIndex({ "lat": 1, "lng": 1 });

// --- chat_conversaciones ---
db.chat_conversaciones.createIndex({ "usuario_id": 1, "fecha": -1 });
db.chat_conversaciones.createIndex({ "estado": 1 });

// --- chat_mensajes ---
db.chat_mensajes.createIndex({ "conversacion_id": 1, "fecha": 1 });

// --- chat_metricas ---
db.chat_metricas.createIndex({ "tema": 1 }, { unique: true });

// --- contacto_mensajes ---
db.contacto_mensajes.createIndex({ "leido": 1, "fecha": -1 });

// --- dataset_imagenes ---
db.dataset_imagenes.createIndex({ "huerto_id": 1 });
db.dataset_imagenes.createIndex({ "etiqueta_plaga": 1 });
db.dataset_imagenes.createIndex({ "validada": 1 });

// --- notificaciones_usuario ---
db.notificaciones_usuario.createIndex({ "usuario_id": 1, "leida": 1, "fecha": -1 });

print("✅ MongoDB indexes created successfully");
print("📦 Database: huerto_connect");
