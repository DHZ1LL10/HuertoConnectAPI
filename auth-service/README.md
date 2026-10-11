# Auth Service

Servicio Python/FastAPI en puerto 8001. Proporciona registro, login por contraseña
y OTP, Google Sign-In, recuperación de contraseña y gestión de sesiones.
Utiliza MongoDB y SMTP; los correos contienen texto plano y HTML con ilustraciones
PNG integradas mediante MIME inline.

Contrato completo: [Autenticación](../docs/DOCUMENTACION_API.md#4-autenticación-y-sesiones).

```powershell
docker compose up -d --build auth-service
python -m pytest tests/test_auth_service.py -q
```

Las dependencias están en `requirements.txt` y `requirements-dev.txt`.
La configuración privada y los comandos integrados figuran en el manual general.
