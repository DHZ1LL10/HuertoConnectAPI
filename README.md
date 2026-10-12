# Huerto Connect API

Backend agrícola desarrollado en Python y FastAPI. Integra autenticación OTP y
Google, gestión de huertos, clasificación visual V6, estimación de rendimiento,
chat agrícola, reportes y Comunidad Agricultora.

## Documentación

El [Manual de la API](docs/DOCUMENTACION_API.md) contiene arquitectura,
instalación, configuración, contratos, ejemplos, seguridad y verificación.

- Swagger unificado: [http://localhost:8000/docs](http://localhost:8000/docs).
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc).
- Salud integrada: [http://localhost:8000/api/health](http://localhost:8000/api/health).

## Ejecución

Con la configuración local y los modelos V6 disponibles:

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps -a
```

Para detener la pila conservando imágenes y datos:

```powershell
docker compose stop
```

Para el servidor con Cloudflare Tunnel, el archivo
`docker-compose.cloudflare.yml` configura la conexión interna `http://gateway:8000`,
los enlaces HTTPS y los puertos internos. El token se configura en `.env` como
`CLOUDFLARE_TUNNEL_TOKEN`; el dominio predeterminado es `api.huertoconnect.com`.
La [sección Cloudflare del manual](docs/DOCUMENTACION_API.md#14-servidor-con-cloudflare-tunnel)
describe la ruta publicada y los parámetros del dominio.

```powershell
.\start.ps1 -Cloudflare -CheckOnly
.\start.ps1 -Cloudflare -Build
```

## Estructura

- `auth-service`: cuentas, OTP, Google y sesiones.
- `huertos-service`: huertos, catálogos, perfiles, notificaciones y comunidad.
- `plagas-service`: YOLO V6, Random Forest, alertas y estadísticas.
- `chat-service`: conversaciones y coordinación del asistente.
- `agent-service`: generación interna con Ollama.
- `reportes-service`: PDF, CSV, estadísticas y auditoría.
- `gateway`: acceso HTTP y documentación unificada.
- `shared`, `migrations`, `scripts`: componentes compartidos, persistencia y operación.
- `tests`, `.github`: pruebas automatizadas y automatización de validación.
- `docs`: manual técnico final.

El código de aplicación no incluye frontend. La configuración privada, el
entorno Python local y las cachés no forman parte del paquete de código fuente.
Los pesos V6 permanecen separados de las imágenes Docker.
