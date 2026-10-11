# Huertos Service

Servicio Python/FastAPI en puerto 8002 con MongoDB. Gestiona huertos, regiones,
cultivos, siembras, perfiles, contacto, notificaciones y Comunidad Agricultora.
Las fotos se almacenan en ImageKit sin reducir sus bytes originales.

Contratos completos:
[Huertos y catálogos](../docs/DOCUMENTACION_API.md#5-huertos-regiones-y-catálogos),
[Comunidad](../docs/DOCUMENTACION_API.md#6-comunidad-agricultora).

```powershell
docker compose up -d --build huertos-service
python -m pytest tests/test_huertos_service.py tests/test_comunidad.py -q
```

Los índices de MongoDB se crean al arrancar. La gestión de huertos verifica
propiedad incluso para Admin y Técnico. Comunidad distingue autoría de contenido
y permisos de moderación.
