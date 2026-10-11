"""Bounded, plain-text community contracts; no client-supplied author or role."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TipoPublicacion = Literal["Experiencia", "Pregunta", "Consejo"]
EstadoContenido = Literal["Publicada", "Oculta"]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PublicacionCreate(Entrada):
    titulo: str = Field(min_length=3, max_length=160, examples=["Mi experiencia cultivando jitomate en maceta"])
    contenido: str = Field(min_length=1, max_length=5000, examples=["He conseguido mejorar el drenaje de mis macetas..."])
    tipo: TipoPublicacion = "Experiencia"
    region: str | None = Field(default=None, min_length=1, max_length=80, examples=["Capital"])
    cultivo: str | None = Field(default=None, min_length=1, max_length=80, examples=["Jitomate"])


class PublicacionUpdate(Entrada):
    titulo: str | None = Field(default=None, min_length=3, max_length=160)
    contenido: str | None = Field(default=None, min_length=1, max_length=5000)
    tipo: TipoPublicacion | None = None
    region: str | None = Field(default=None, min_length=1, max_length=80)
    cultivo: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("titulo", "contenido", "tipo", mode="before")
    @classmethod
    def no_null(cls, value):
        if value is None:
            raise ValueError("El campo no puede ser null")
        return value


class ComentarioCreate(Entrada):
    contenido: str = Field(min_length=1, max_length=1500, examples=["¿Cada cuánto riegas tus macetas?"])


class ModeracionRequest(Entrada):
    estado: EstadoContenido
    motivo: str = Field(min_length=5, max_length=500, examples=["Contenido ajeno a la comunidad agricultora"])


class AutorPublico(BaseModel):
    id: str
    nombre: str


class FotoComunidad(BaseModel):
    id: str
    url: str


class PublicacionResumen(BaseModel):
    id: str
    autor: AutorPublico
    titulo: str
    resumen: str
    tipo: TipoPublicacion
    region: str | None
    cultivo: str | None
    estado: EstadoContenido
    fotos: list[FotoComunidad]
    total_fotos: int
    total_comentarios: int
    total_me_gusta: int
    me_gusta: bool
    created_at: datetime
    updated_at: datetime


class PublicacionDetalle(PublicacionResumen):
    contenido: str


class PublicacionesPagina(BaseModel):
    items: list[PublicacionResumen]
    siguiente_cursor: str | None
    hay_mas: bool


class ComentarioResponse(BaseModel):
    id: str
    publicacion_id: str
    autor: AutorPublico
    contenido: str
    estado: EstadoContenido
    created_at: datetime
    updated_at: datetime


class ComentariosPagina(BaseModel):
    items: list[ComentarioResponse]
    siguiente_cursor: str | None
    hay_mas: bool


class MeGustaResponse(BaseModel):
    publicacion_id: str
    me_gusta: bool
    total_me_gusta: int


class ResultadoModeracion(BaseModel):
    id: str
    estado: EstadoContenido
    motivo: str
    moderado_por: str
    updated_at: datetime


class ModeracionEvento(BaseModel):
    estado: EstadoContenido
    motivo: str
    moderado_por: str
    fecha: datetime


class HistorialModeracion(BaseModel):
    id: str
    estado: EstadoContenido
    historial: list[ModeracionEvento]


class ComunidadMessage(BaseModel):
    message: str
