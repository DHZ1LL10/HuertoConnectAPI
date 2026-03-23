"""
Huertos Service — Pydantic schemas for requests/responses.
"""

from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ===================== REGIONES =====================

class RegionCreate(BaseModel):
    nombre: str = Field(..., min_length=1)
    actividad: str = Field(default="Media", pattern=r"^(Alta|Media|Baja)$")
    priorizada: bool = False

    model_config = {
        "json_schema_extra": {
            "example": {
                "nombre": "Bajio Norte",
                "actividad": "Alta",
                "priorizada": True,
            }
        }
    }


class RegionUpdate(BaseModel):
    nombre: Optional[str] = None
    actividad: Optional[str] = None
    priorizada: Optional[bool] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "actividad": "Media",
                "priorizada": False,
            }
        }
    }


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

    model_config = {
        "json_schema_extra": {
            "example": {
                "nombre": "Huerto La Esperanza",
                "municipio": "Irapuato",
                "region_id": "65f2d6ea9f3d2a3e8a7b9d01",
                "estado": "Optimo",
                "salud": 92,
            }
        }
    }


class HuertoUpdate(BaseModel):
    nombre: Optional[str] = None
    municipio: Optional[str] = None
    region_id: Optional[str] = None
    estado: Optional[str] = None
    salud: Optional[int] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "estado": "Atencion",
                "salud": 68,
            }
        }
    }


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

    model_config = {
        "json_schema_extra": {
            "example": {
                "nombre": "Jitomate Saladette",
                "temporada": "Primavera-Verano",
                "dificultad": "Media",
                "riego": "Cada 2 dias por goteo",
                "fertilizacion": "NPK 20-20-20 cada 15 dias",
                "activo": True,
            }
        }
    }


class CultivoUpdate(BaseModel):
    nombre: Optional[str] = None
    temporada: Optional[str] = None
    dificultad: Optional[str] = None
    riego: Optional[str] = None
    fertilizacion: Optional[str] = None
    activo: Optional[bool] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "riego": "Diario en temporada seca",
                "activo": True,
            }
        }
    }


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

    model_config = {
        "json_schema_extra": {
            "example": {
                "huerto_id": "65f2d6ea9f3d2a3e8a7b9e10",
                "cultivo_id": "65f2d6ea9f3d2a3e8a7b9e11",
                "fecha_siembra": "2026-03-15",
                "estado": "Activo",
            }
        }
    }


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

    model_config = {
        "json_schema_extra": {
            "example": {
                "nombre": "Parcela A - Surco 3",
                "huerto_cultivo_id": "65f2d6ea9f3d2a3e8a7b9e22",
                "municipio": "Irapuato",
                "lat": 20.6767,
                "lng": -101.3563,
                "salud": 88,
                "severidad": "Media",
            }
        }
    }


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

    model_config = {
        "json_schema_extra": {
            "example": {
                "nombre": "Carlos Perez",
                "email": "carlos.perez@gmail.com",
                "telefono": "+52 462 123 4567",
                "mensaje": "Necesito asesoria para control de trips en invernadero.",
            }
        }
    }


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

    model_config = {
        "json_schema_extra": {
            "example": {
                "imagen_url": "https://res.cloudinary.com/demo/image/upload/v1/plagas/trips_001.jpg",
                "huerto_id": "65f2d6ea9f3d2a3e8a7b9e10",
                "cultivo_id": "65f2d6ea9f3d2a3e8a7b9e11",
                "etiqueta_plaga": "Trips",
                "etiqueta_severidad": "Media",
                "anotaciones_json": "{\"bbox\":[120,80,260,210],\"confidence\":0.93}",
                "fuente": "manual",
                "validada": True,
            }
        }
    }


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

class NotificacionCreate(BaseModel):
    usuario_id: str
    titulo: str = Field(..., min_length=1, max_length=180)
    mensaje: str = Field(..., min_length=1, max_length=1000)
    tipo: str = Field(default="alerta", pattern=r"^(alerta|info|warning|success|error)$")
    referencia_id: Optional[str] = None
    referencia_tipo: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "usuario_id": "65f2d6ea9f3d2a3e8a7b9c10",
                "titulo": "Nueva alerta en tu huerto",
                "mensaje": "Se detectó posible presencia de trips en Huerto La Esperanza.",
                "tipo": "alerta",
                "referencia_id": "3f2dc4d1-7d13-4d50-95f2-c335f39f0cb7",
                "referencia_tipo": "alerta",
            }
        }
    }


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

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "65f7e30f8b9f6f3bb3d04299",
                "usuario_id": "65f2d6ea9f3d2a3e8a7b9c10",
                "titulo": "Nueva alerta en tu huerto",
                "mensaje": "Se detectó posible presencia de trips en Huerto La Esperanza.",
                "tipo": "alerta",
                "leida": False,
                "referencia_id": "3f2dc4d1-7d13-4d50-95f2-c335f39f0cb7",
                "referencia_tipo": "alerta",
                "fecha": "2026-03-21T23:40:00+00:00",
            }
        }
    }


class NotificacionResumenResponse(BaseModel):
    total: int
    no_leidas: int
    leidas: int
    por_tipo: dict[str, int]

    model_config = {
        "json_schema_extra": {
            "example": {
                "total": 12,
                "no_leidas": 5,
                "leidas": 7,
                "por_tipo": {
                    "alerta": 8,
                    "info": 2,
                    "warning": 2,
                },
            }
        }
    }


# ===================== USUARIOS (Admin) =====================

class UsuarioAdminUpdate(BaseModel):
    nombre: Optional[str] = None
    apellidos: Optional[str] = None
    email: Optional[EmailStr] = None
    rol: Optional[str] = None
    estado: Optional[str] = None
    region_id: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "nombre": "Ana",
                "rol": "Tecnico",
                "estado": "Activo",
                "region_id": "65f2d6ea9f3d2a3e8a7b9d01",
            }
        }
    }


class UsuarioAdminCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=120)
    apellidos: str = Field(default="", max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    rol: str = Field(default="Usuario")
    estado: str = Field(default="Activo")
    region_id: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "nombre": "Luis",
                "apellidos": "Mendoza",
                "email": "luis.mendoza@huertoconnect.com",
                "password": "PassTecnico2026!",
                "rol": "Tecnico",
                "estado": "Activo",
                "region_id": "65f2d6ea9f3d2a3e8a7b9d01",
            }
        }
    }


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

    model_config = {
        "json_schema_extra": {
            "example": {
                "message": "Operación completada correctamente.",
            }
        }
    }
