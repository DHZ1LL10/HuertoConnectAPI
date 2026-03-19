"""
Plagas Service — Pydantic schemas for requests/responses.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ===================== PLAGA DETECCIONES =====================

class PlagaDeteccionCreate(BaseModel):
    imagen_url: Optional[str] = None
    plaga: str = Field(..., min_length=1)
    confianza: float = Field(default=0, ge=0, le=100)
    huerto_id: str
    cultivo_id: Optional[str] = None
    severidad: str = Field(default="Baja", pattern=r"^(Baja|Media|Alta)$")
    estado: str = Field(default="Pendiente", pattern=r"^(Pendiente|Confirmada|Descartada)$")


class PlagaDeteccionUpdate(BaseModel):
    plaga: Optional[str] = None
    confianza: Optional[float] = None
    severidad: Optional[str] = None
    estado: Optional[str] = None


class PlagaDeteccionResponse(BaseModel):
    id: str
    imagen_url: Optional[str] = None
    plaga: str
    confianza: float
    huerto_id: str
    cultivo_id: Optional[str] = None
    severidad: str
    estado: str
    fecha: Optional[str] = None


# ===================== ALERTAS =====================

class AlertaCreate(BaseModel):
    titulo: str = Field(..., min_length=1)
    tipo: str = Field(..., pattern=r"^(Plaga|Riego|Sistema)$")
    severidad: str = Field(default="Seguro", pattern=r"^(Seguro|Advertencia|Critico)$")
    huerto_id: str
    responsable_id: Optional[str] = None


class AlertaUpdate(BaseModel):
    titulo: Optional[str] = None
    severidad: Optional[str] = None
    estado: Optional[str] = None
    responsable_id: Optional[str] = None


class AlertaResponse(BaseModel):
    id: str
    titulo: str
    tipo: str
    severidad: str
    estado: str
    huerto_id: str
    responsable_id: Optional[str] = None
    fecha: Optional[str] = None
    resuelta_en: Optional[str] = None


# ===================== MODELOS IA =====================

class ModeloIACreate(BaseModel):
    nombre: str
    version: str
    tipo: str = Field(..., pattern=r"^(clasificacion|deteccion|prediccion)$")
    arquitectura: Optional[str] = None
    ruta_archivo: Optional[str] = None
    parametros_json: Optional[str] = None


class ModeloIAResponse(BaseModel):
    id: str
    nombre: str
    version: str
    tipo: str
    arquitectura: Optional[str] = None
    precision_score: Optional[float] = None
    recall_score: Optional[float] = None
    f1_score: Optional[float] = None
    estado: str
    fecha_entrenamiento: Optional[str] = None
    created_at: Optional[str] = None


# ===================== PREDICCIONES =====================

class PrediccionCreate(BaseModel):
    modelo_id: str
    imagen_url: Optional[str] = None
    huerto_id: str
    cultivo_id: Optional[str] = None
    plaga_predicha: Optional[str] = None
    confianza: Optional[float] = None
    severidad_predicha: Optional[str] = None
    latencia_ms: Optional[int] = None


class PrediccionFeedback(BaseModel):
    resultado_real: str
    correcto: bool


class PrediccionResponse(BaseModel):
    id: str
    modelo_id: str
    imagen_url: Optional[str] = None
    huerto_id: str
    plaga_predicha: Optional[str] = None
    confianza: Optional[float] = None
    severidad_predicha: Optional[str] = None
    resultado_real: Optional[str] = None
    correcto: Optional[bool] = None
    latencia_ms: Optional[int] = None
    fecha: Optional[str] = None


# ===================== DATASETS =====================

class DatasetCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    tipo: str = Field(..., pattern=r"^(entrenamiento|validacion|test)$")
    total_imagenes: int = 0
    clases_json: Optional[str] = None
    ruta_almacenamiento: Optional[str] = None
    version: Optional[str] = None


class DatasetResponse(BaseModel):
    id: str
    nombre: str
    descripcion: Optional[str] = None
    tipo: str
    total_imagenes: int
    clases_json: Optional[str] = None
    version: Optional[str] = None
    fecha_creacion: Optional[str] = None


# ===================== RECOMENDACIONES =====================

class RecomendacionCreate(BaseModel):
    huerto_id: str
    cultivo_id: Optional[str] = None
    modelo_id: Optional[str] = None
    tipo_recomendacion: str = Field(..., pattern=r"^(siembra|riego|fertilizacion|tratamiento)$")
    descripcion: str
    confianza: Optional[float] = None
    parametros_entrada_json: Optional[str] = None


class RecomendacionResponse(BaseModel):
    id: str
    huerto_id: str
    cultivo_id: Optional[str] = None
    modelo_id: Optional[str] = None
    tipo_recomendacion: str
    descripcion: str
    confianza: Optional[float] = None
    aceptada: Optional[bool] = None
    fecha: Optional[str] = None


# ===================== DASHBOARD =====================

class DashboardKPIs(BaseModel):
    total_detecciones: int = 0
    detecciones_confirmadas: int = 0
    alertas_abiertas: int = 0
    alertas_criticas: int = 0
    modelos_activos: int = 0
    predicciones_totales: int = 0
    precision_promedio: Optional[float] = None


class MessageResponse(BaseModel):
    message: str
