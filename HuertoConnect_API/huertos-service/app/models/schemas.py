"""
Huertos Service — Pydantic schemas for requests/responses.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ===================== REGIONES =====================

class RegionCreate(BaseModel):
    nombre: str = Field(..., min_length=1)
    actividad: str = Field(default="Media", pattern=r"^(Alta|Media|Baja)$")
    priorizada: bool = False


class RegionUpdate(BaseModel):
    nombre: Optional[str] = None
    actividad: Optional[str] = None
    priorizada: Optional[bool] = None


class RegionResponse(BaseModel):
    id: str
    nombre: str
    actividad: str
    priorizada: bool
    created_at: Optional[str] = None


# ===================== HUERTOS =====================

class HuertoCreate(BaseModel):
    nombre: str = Field(..., min_length=1)
    municipio: str = ""
    region_id: Optional[str] = None
    estado: str = Field(default="Optimo", pattern=r"^(Optimo|Atencion|Critico)$")
    salud: int = Field(default=100, ge=0, le=100)


class HuertoUpdate(BaseModel):
    nombre: Optional[str] = None
    municipio: Optional[str] = None
    region_id: Optional[str] = None
    estado: Optional[str] = None
    salud: Optional[int] = None


class HuertoResponse(BaseModel):
    id: str
    nombre: str
    usuario_id: str
    municipio: str
    region_id: Optional[str] = None
    estado: str
    salud: int
    created_at: Optional[str] = None


# ===================== CULTIVOS =====================

class CultivoCreate(BaseModel):
    nombre: str = Field(..., min_length=1)
    temporada: str = ""
    dificultad: str = Field(default="Media", pattern=r"^(Baja|Media|Alta)$")
    riego: str = ""
    fertilizacion: str = ""
    activo: bool = True


class CultivoUpdate(BaseModel):
    nombre: Optional[str] = None
    temporada: Optional[str] = None
    dificultad: Optional[str] = None
    riego: Optional[str] = None
    fertilizacion: Optional[str] = None
    activo: Optional[bool] = None


class CultivoResponse(BaseModel):
    id: str
    nombre: str
    temporada: str
    dificultad: str
    riego: str
    fertilizacion: str
    activo: bool
    created_at: Optional[str] = None


# ===================== HUERTO CULTIVOS =====================

class HuertoCultivoCreate(BaseModel):
    huerto_id: str
    cultivo_id: str
    fecha_siembra: Optional[str] = None
    estado: str = Field(default="Activo", pattern=r"^(Activo|Cosechado|Perdido)$")


class HuertoCultivoResponse(BaseModel):
    id: str
    huerto_id: str
    cultivo_id: str
    fecha_siembra: Optional[str] = None
    estado: str
    created_at: Optional[str] = None


# ===================== PLANTIOS =====================

class PlantioCreate(BaseModel):
    nombre: str = Field(..., min_length=1)
    huerto_cultivo_id: str
    municipio: str = ""
    lat: float = 0.0
    lng: float = 0.0
    salud: int = Field(default=100, ge=0, le=100)
    severidad: str = Field(default="Baja", pattern=r"^(Baja|Media|Alta)$")


class PlantioResponse(BaseModel):
    id: str
    nombre: str
    huerto_cultivo_id: str
    municipio: str
    lat: float
    lng: float
    salud: int
    severidad: str
    created_at: Optional[str] = None


# ===================== CONTACTO =====================

class ContactoCreate(BaseModel):
    nombre: str = Field(..., min_length=1)
    email: EmailStr
    telefono: str = ""
    mensaje: str = Field(..., min_length=1)


class ContactoResponse(BaseModel):
    id: str
    nombre: str
    email: str
    telefono: str
    mensaje: str
    leido: bool
    fecha: Optional[str] = None


# ===================== DATASET IMAGENES =====================

class DatasetImagenCreate(BaseModel):
    imagen_url: str
    huerto_id: Optional[str] = None
    cultivo_id: Optional[str] = None
    etiqueta_plaga: Optional[str] = None
    etiqueta_severidad: Optional[str] = None
    anotaciones_json: Optional[str] = None
    fuente: str = "manual"
    validada: bool = False


class DatasetImagenResponse(BaseModel):
    id: str
    imagen_url: str
    huerto_id: Optional[str] = None
    cultivo_id: Optional[str] = None
    etiqueta_plaga: Optional[str] = None
    etiqueta_severidad: Optional[str] = None
    fuente: str
    validada: bool
    fecha_captura: Optional[str] = None


# ===================== NOTIFICACIONES =====================

class NotificacionResponse(BaseModel):
    id: str
    usuario_id: str
    titulo: str
    mensaje: str
    tipo: str
    leida: bool
    referencia_id: Optional[str] = None
    referencia_tipo: Optional[str] = None
    fecha: Optional[str] = None


# ===================== USUARIOS (Admin) =====================

class UsuarioAdminUpdate(BaseModel):
    nombre: Optional[str] = None
    apellidos: Optional[str] = None
    rol: Optional[str] = None
    estado: Optional[str] = None
    region_id: Optional[str] = None


class UsuarioAdminResponse(BaseModel):
    id: str
    nombre: str
    apellidos: str
    email: str
    rol: str
    estado: str
    email_verificado: bool
    region_id: Optional[str] = None
    ultima_actividad: Optional[str] = None
    created_at: Optional[str] = None


class MessageResponse(BaseModel):
    message: str
