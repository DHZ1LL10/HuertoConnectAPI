-- ============================================================
-- PostgreSQL Init Script - Huerto Connect (AI/Analytics)
-- Creates all tables and indexes for the SQL database
-- ============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ===================== TABLAS BASE =====================

-- Detecciones de plagas (resultados de análisis de imágenes)
CREATE TABLE plaga_detecciones (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    imagen_url      VARCHAR(500),
    plaga           VARCHAR(200) NOT NULL,
    confianza       DECIMAL(5,2) CHECK (confianza >= 0 AND confianza <= 100),
    huerto_id       VARCHAR(100) NOT NULL,
    cultivo_id      VARCHAR(100),
    severidad       VARCHAR(20) NOT NULL DEFAULT 'Baja'
                    CHECK (severidad IN ('Baja', 'Media', 'Alta')),
    estado          VARCHAR(20) NOT NULL DEFAULT 'Pendiente'
                    CHECK (estado IN ('Pendiente', 'Confirmada', 'Descartada')),
    fecha           TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Alertas del sistema
CREATE TABLE alertas (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    titulo          VARCHAR(300) NOT NULL,
    tipo            VARCHAR(20) NOT NULL
                    CHECK (tipo IN ('Plaga', 'Riego', 'Sistema')),
    severidad       VARCHAR(20) NOT NULL DEFAULT 'Seguro'
                    CHECK (severidad IN ('Seguro', 'Advertencia', 'Critico')),
    estado          VARCHAR(20) NOT NULL DEFAULT 'Abierta'
                    CHECK (estado IN ('Abierta', 'En_progreso', 'Resuelta')),
    huerto_id       VARCHAR(100) NOT NULL,
    responsable_id  VARCHAR(100),
    fecha           TIMESTAMP NOT NULL DEFAULT NOW(),
    resuelta_en     TIMESTAMP
);

-- Reportes generados
CREATE TABLE reportes (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nombre          VARCHAR(300) NOT NULL,
    tipo            VARCHAR(100) NOT NULL,
    estado          VARCHAR(20) NOT NULL DEFAULT 'En_proceso'
                    CHECK (estado IN ('Generado', 'En_proceso', 'Error')),
    archivo_url     VARCHAR(500),
    generado_por    VARCHAR(100) NOT NULL,
    fecha           TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Logs de auditoría
CREATE TABLE auditoria_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    actor_id        VARCHAR(100) NOT NULL,
    accion          VARCHAR(200) NOT NULL,
    modulo          VARCHAR(100) NOT NULL,
    ip              VARCHAR(50),
    detalle_json    TEXT,
    fecha           TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ===================== TABLAS IA/ML =====================

-- Registro de modelos de IA entrenados
CREATE TABLE modelos_ia (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nombre              VARCHAR(200) NOT NULL,
    version             VARCHAR(50) NOT NULL,
    tipo                VARCHAR(50) NOT NULL
                        CHECK (tipo IN ('clasificacion', 'deteccion', 'prediccion')),
    arquitectura        VARCHAR(200),
    ruta_archivo        VARCHAR(500),
    precision_score     DECIMAL(5,4),
    recall_score        DECIMAL(5,4),
    f1_score            DECIMAL(5,4),
    estado              VARCHAR(20) NOT NULL DEFAULT 'inactivo'
                        CHECK (estado IN ('entrenando', 'activo', 'inactivo', 'descartado')),
    parametros_json     TEXT,
    fecha_entrenamiento TIMESTAMP,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(nombre, version)
);

-- Predicciones realizadas por modelos
CREATE TABLE predicciones (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    modelo_id           UUID NOT NULL REFERENCES modelos_ia(id) ON DELETE CASCADE,
    imagen_url          VARCHAR(500),
    huerto_id           VARCHAR(100) NOT NULL,
    cultivo_id          VARCHAR(100),
    plaga_predicha      VARCHAR(200),
    confianza           DECIMAL(5,2) CHECK (confianza >= 0 AND confianza <= 100),
    severidad_predicha  VARCHAR(20)
                        CHECK (severidad_predicha IN ('Baja', 'Media', 'Alta')),
    resultado_real      VARCHAR(200),
    correcto            BOOLEAN,
    latencia_ms         INTEGER,
    fecha               TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Historial de entrenamiento (época por época)
CREATE TABLE entrenamiento_historial (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    modelo_id           UUID NOT NULL REFERENCES modelos_ia(id) ON DELETE CASCADE,
    epoca               INTEGER NOT NULL,
    loss                DECIMAL(10,6),
    val_loss            DECIMAL(10,6),
    accuracy            DECIMAL(5,4),
    val_accuracy        DECIMAL(5,4),
    learning_rate       DECIMAL(10,8),
    duracion_segundos   DECIMAL(10,2),
    fecha               TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Métricas de evaluación de modelos
CREATE TABLE metricas_modelo (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    modelo_id               UUID NOT NULL REFERENCES modelos_ia(id) ON DELETE CASCADE,
    fecha_evaluacion        TIMESTAMP NOT NULL DEFAULT NOW(),
    dataset_id              UUID,
    total_muestras          INTEGER NOT NULL DEFAULT 0,
    verdaderos_positivos    INTEGER NOT NULL DEFAULT 0,
    falsos_positivos        INTEGER NOT NULL DEFAULT 0,
    verdaderos_negativos    INTEGER NOT NULL DEFAULT 0,
    falsos_negativos        INTEGER NOT NULL DEFAULT 0,
    precision_score         DECIMAL(5,4),
    recall_score            DECIMAL(5,4),
    f1_score                DECIMAL(5,4),
    matriz_confusion_json   TEXT
);

-- Catálogo de datasets
CREATE TABLE datasets (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nombre              VARCHAR(200) NOT NULL,
    descripcion         TEXT,
    tipo                VARCHAR(20) NOT NULL
                        CHECK (tipo IN ('entrenamiento', 'validacion', 'test')),
    total_imagenes      INTEGER NOT NULL DEFAULT 0,
    clases_json         TEXT,
    ruta_almacenamiento VARCHAR(500),
    version             VARCHAR(50),
    fecha_creacion      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Extracción de features de imágenes
CREATE TABLE feature_extractions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prediccion_id       UUID NOT NULL REFERENCES predicciones(id) ON DELETE CASCADE,
    capa_modelo         VARCHAR(100),
    vector_features_json TEXT,
    dimensiones         INTEGER,
    fecha               TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Recomendaciones de cultivo generadas por IA
CREATE TABLE recomendaciones_cultivo (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    huerto_id               VARCHAR(100) NOT NULL,
    cultivo_id              VARCHAR(100),
    modelo_id               UUID REFERENCES modelos_ia(id) ON DELETE SET NULL,
    tipo_recomendacion      VARCHAR(30) NOT NULL
                            CHECK (tipo_recomendacion IN ('siembra', 'riego', 'fertilizacion', 'tratamiento')),
    descripcion             TEXT NOT NULL,
    confianza               DECIMAL(5,2) CHECK (confianza >= 0 AND confianza <= 100),
    parametros_entrada_json TEXT,
    aceptada                BOOLEAN,
    fecha                   TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ===================== INDEXES =====================

-- Plaga detecciones
CREATE INDEX idx_plaga_det_huerto ON plaga_detecciones(huerto_id, fecha DESC);
CREATE INDEX idx_plaga_det_severidad ON plaga_detecciones(severidad, estado);
CREATE INDEX idx_plaga_det_huerto_sev ON plaga_detecciones(huerto_id, severidad, estado, fecha DESC);

-- Alertas
CREATE INDEX idx_alertas_huerto ON alertas(huerto_id, severidad, estado, fecha DESC);
CREATE INDEX idx_alertas_responsable ON alertas(responsable_id, estado);
CREATE INDEX idx_alertas_tipo ON alertas(tipo, estado);

-- Reportes
CREATE INDEX idx_reportes_generado ON reportes(generado_por, fecha DESC);
CREATE INDEX idx_reportes_estado ON reportes(estado);

-- Auditoría
CREATE INDEX idx_auditoria_actor ON auditoria_logs(actor_id, fecha DESC);
CREATE INDEX idx_auditoria_modulo ON auditoria_logs(modulo, fecha DESC);

-- Modelos IA
CREATE INDEX idx_modelos_tipo ON modelos_ia(tipo, estado);
CREATE INDEX idx_modelos_estado ON modelos_ia(estado);

-- Predicciones
CREATE INDEX idx_pred_modelo ON predicciones(modelo_id, fecha DESC);
CREATE INDEX idx_pred_huerto ON predicciones(huerto_id, fecha DESC);
CREATE INDEX idx_pred_correcto ON predicciones(modelo_id, correcto);

-- Entrenamiento historial
CREATE INDEX idx_entrenamiento_modelo ON entrenamiento_historial(modelo_id, epoca);

-- Métricas modelo
CREATE INDEX idx_metricas_modelo ON metricas_modelo(modelo_id, fecha_evaluacion DESC);
CREATE INDEX idx_metricas_dataset ON metricas_modelo(dataset_id);

-- Datasets
CREATE INDEX idx_datasets_tipo ON datasets(tipo);

-- Feature extractions
CREATE INDEX idx_features_pred ON feature_extractions(prediccion_id);

-- Recomendaciones
CREATE INDEX idx_recomendaciones_huerto ON recomendaciones_cultivo(huerto_id, fecha DESC);
CREATE INDEX idx_recomendaciones_modelo ON recomendaciones_cultivo(modelo_id);
CREATE INDEX idx_recomendaciones_tipo ON recomendaciones_cultivo(tipo_recomendacion);

-- Add FK reference for metricas_modelo -> datasets
ALTER TABLE metricas_modelo
    ADD CONSTRAINT fk_metricas_dataset
    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE SET NULL;
