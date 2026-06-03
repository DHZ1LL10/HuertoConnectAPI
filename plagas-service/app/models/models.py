"""
Plagas Service — SQLAlchemy models for PostgreSQL.
Includes base tables (plaga_detecciones, alertas) and AI/ML tables.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from shared.database import Base


class PlagaDeteccion(Base):
    __tablename__ = "plaga_detecciones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    imagen_url = Column(String(500))
    plaga = Column(String(200), nullable=False)
    confianza = Column(Numeric(5, 2))
    huerto_id = Column(String(100), nullable=False)
    cultivo_id = Column(String(100))
    severidad = Column(String(20), nullable=False, default="Baja")
    estado = Column(String(20), nullable=False, default="Pendiente")
    fecha = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Alerta(Base):
    __tablename__ = "alertas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    titulo = Column(String(300), nullable=False)
    tipo = Column(String(20), nullable=False)
    severidad = Column(String(20), nullable=False, default="Seguro")
    estado = Column(String(20), nullable=False, default="Abierta")
    huerto_id = Column(String(100), nullable=False)
    responsable_id = Column(String(100))
    fecha = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    resuelta_en = Column(DateTime(timezone=True), nullable=True)


# ===================== AI/ML TABLES =====================

class ModeloIA(Base):
    __tablename__ = "modelos_ia"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(200), nullable=False)
    version = Column(String(50), nullable=False)
    tipo = Column(String(50), nullable=False)
    arquitectura = Column(String(200))
    ruta_archivo = Column(String(500))
    precision_score = Column(Numeric(5, 4))
    recall_score = Column(Numeric(5, 4))
    f1_score = Column(Numeric(5, 4))
    estado = Column(String(20), nullable=False, default="inactivo")
    parametros_json = Column(Text)
    fecha_entrenamiento = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("nombre", "version", name="uq_modelo_nombre_version"),)

    predicciones = relationship("Prediccion", back_populates="modelo")
    historial = relationship("EntrenamientoHistorial", back_populates="modelo")
    metricas = relationship("MetricasModelo", back_populates="modelo")


class Prediccion(Base):
    __tablename__ = "predicciones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    modelo_id = Column(UUID(as_uuid=True), ForeignKey("modelos_ia.id", ondelete="CASCADE"), nullable=False)
    imagen_url = Column(String(500))
    huerto_id = Column(String(100), nullable=False)
    cultivo_id = Column(String(100))
    plaga_predicha = Column(String(200))
    confianza = Column(Numeric(5, 2))
    severidad_predicha = Column(String(20))
    resultado_real = Column(String(200))
    correcto = Column(Boolean)
    latencia_ms = Column(Integer)
    fecha = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    modelo = relationship("ModeloIA", back_populates="predicciones")
    features = relationship("FeatureExtraction", back_populates="prediccion")


class EntrenamientoHistorial(Base):
    __tablename__ = "entrenamiento_historial"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    modelo_id = Column(UUID(as_uuid=True), ForeignKey("modelos_ia.id", ondelete="CASCADE"), nullable=False)
    epoca = Column(Integer, nullable=False)
    loss = Column(Numeric(10, 6))
    val_loss = Column(Numeric(10, 6))
    accuracy = Column(Numeric(5, 4))
    val_accuracy = Column(Numeric(5, 4))
    learning_rate = Column(Numeric(10, 8))
    duracion_segundos = Column(Numeric(10, 2))
    fecha = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    modelo = relationship("ModeloIA", back_populates="historial")


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(200), nullable=False)
    descripcion = Column(Text)
    tipo = Column(String(20), nullable=False)
    total_imagenes = Column(Integer, nullable=False, default=0)
    clases_json = Column(Text)
    ruta_almacenamiento = Column(String(500))
    version = Column(String(50))
    fecha_creacion = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class MetricasModelo(Base):
    __tablename__ = "metricas_modelo"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    modelo_id = Column(UUID(as_uuid=True), ForeignKey("modelos_ia.id", ondelete="CASCADE"), nullable=False)
    fecha_evaluacion = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True)
    total_muestras = Column(Integer, nullable=False, default=0)
    verdaderos_positivos = Column(Integer, default=0)
    falsos_positivos = Column(Integer, default=0)
    verdaderos_negativos = Column(Integer, default=0)
    falsos_negativos = Column(Integer, default=0)
    precision_score = Column(Numeric(5, 4))
    recall_score = Column(Numeric(5, 4))
    f1_score = Column(Numeric(5, 4))
    matriz_confusion_json = Column(Text)

    modelo = relationship("ModeloIA", back_populates="metricas")


class FeatureExtraction(Base):
    __tablename__ = "feature_extractions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prediccion_id = Column(UUID(as_uuid=True), ForeignKey("predicciones.id", ondelete="CASCADE"), nullable=False)
    capa_modelo = Column(String(100))
    vector_features_json = Column(Text)
    dimensiones = Column(Integer)
    fecha = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    prediccion = relationship("Prediccion", back_populates="features")


class RecomendacionCultivo(Base):
    __tablename__ = "recomendaciones_cultivo"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    huerto_id = Column(String(100), nullable=False)
    cultivo_id = Column(String(100))
    modelo_id = Column(UUID(as_uuid=True), ForeignKey("modelos_ia.id", ondelete="SET NULL"), nullable=True)
    tipo_recomendacion = Column(String(30), nullable=False)
    descripcion = Column(Text, nullable=False)
    confianza = Column(Numeric(5, 2))
    parametros_entrada_json = Column(Text)
    aceptada = Column(Boolean)
    fecha = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
