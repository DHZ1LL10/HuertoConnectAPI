# Reportes Service

Servicio Python/FastAPI en puerto 8005 con MongoDB y PostgreSQL.
Genera PDF y CSV desde diagnósticos V6 de huertos propios y proporciona
estadísticas, catálogo de reportes y auditoría administrativa.

Contrato completo: [Reportes y auditoría](../docs/DOCUMENTACION_API.md#9-reportes-y-auditoría).

```powershell
docker compose up -d --build reportes-service
python -m pytest tests/test_reportes_service.py -q
```

Las descargas no requieren ImageKit ni publican un archivo permanente. La
propiedad del huerto se verifica para todos los roles; auditoría global exige Admin.
