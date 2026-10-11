# Plagas e IA Service

Servicio Python/FastAPI en puerto 8003 con MongoDB y PostgreSQL.
Carga una vez los clasificadores YOLO V6 y el Random Forest de rendimiento.
No entrena modelos ni descarga pesos durante las solicitudes.

Contrato completo: [Inferencia y rendimiento](../docs/DOCUMENTACION_API.md#7-inferencia-visual-y-rendimiento-agrícola).

```powershell
docker compose up -d --build plagas-service
python -m pytest tests/test_plagas_service.py tests/test_imagekit_storage.py -q
```

Los pesos se montan en solo lectura. YOLO clasifica la imagen completa, no genera
cajas de detección. Random Forest estima rendimiento histórico, no clima ni el
cultivo ideal. La orientación preventiva no equivale a un diagnóstico confirmado.
