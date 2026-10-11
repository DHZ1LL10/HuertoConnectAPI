# Huerto Connect API

## Manual técnico y de uso

Edición final: 11 de octubre de 2026.

Huerto Connect es una API agrícola desarrollada en Python/FastAPI. Integra
autenticación, huertos, catálogos de Veracruz, clasificación visual, estimación de
rendimiento agrícola, asistencia conversacional, reportes y comunidad de usuarios.
El proyecto contiene únicamente backend, herramientas de operación y pruebas.

La documentación interactiva del contrato HTTP está en
[Swagger](http://localhost:8000/docs) y [ReDoc](http://localhost:8000/redoc).
El esquema se obtiene en `GET /openapi.json`. Este manual reúne la documentación
técnica y operativa de todos los módulos en un solo documento.

### Índice

1. Arquitectura y estructura.
2. Configuración y dependencias.
3. Instalación y operación.
4. Autenticación y sesiones.
5. Huertos, regiones y catálogos.
6. Comunidad Agricultora.
7. Inferencia visual y rendimiento agrícola.
8. Chat y asistente agrícola.
9. Reportes y auditoría.
10. Fotos, correo y conectividad limitada.
11. Persistencia, permisos y errores.
12. Verificación y alcance técnico.

## 1. Arquitectura y estructura

El Gateway centraliza las solicitudes del cliente y combina los esquemas OpenAPI.
Huertos incluye Comunidad como módulo; no existe un servicio adicional para esta
función. Chat conserva las conversaciones y llama a Agent, que genera con Ollama.

| Componente | Puerto | Responsabilidad | Persistencia/dependencia |
|---|---:|---|---|
| Gateway | 8000 | Proxy, Swagger, ReDoc y salud integrada | Servicios internos |
| Auth | 8001 | OTP, Google, usuarios y sesiones | MongoDB, SMTP, Google |
| Huertos | 8002 | Huertos, catálogos, perfiles, comunidad | MongoDB, ImageKit |
| Plagas/IA | 8003 | YOLO V6, Random Forest, alertas | MongoDB, PostgreSQL, pesos V6 |
| Chat | 8004 | Historial y coordinación del asistente | MongoDB, Agent |
| Reportes | 8005 | PDF, CSV, estadísticas y auditoría | MongoDB, PostgreSQL |
| Agent | 8006 | Generación agrícola interna | Ollama |
| MongoDB | 27017 interno | Documentos y sesiones | Volumen `mongo_data` |
| PostgreSQL | 5432 interno | Catálogos SQL y auditoría | Volumen `postgres_data` |
| Ollama | 11434 interno | Modelo conversacional | Volumen `ollama_data` |

La URL local de consumo es `http://localhost:8000`. Los puertos de servicios
permiten diagnóstico durante desarrollo; Plagas y Agent se publican solo en
loopback. MongoDB, PostgreSQL y Ollama no publican sus puertos al host en Compose.
El cliente utiliza Gateway, no las credenciales internas de los servicios.

```text
HuertoConnectAPI/
  auth-service/        Autenticación y correo OTP
  huertos-service/     Huertos, catálogos y Comunidad
  plagas-service/      Clasificación V6 y rendimiento
  chat-service/        Conversaciones y mensajes
  agent-service/       Generación con Ollama
  reportes-service/    Descargas y auditoría
  gateway/            Proxy y documentación unificada
  shared/             Configuración, autenticación y utilidades compartidas
  migrations/         Migraciones PostgreSQL
  scripts/            Inicialización, mantenimiento y verificaciones
  tests/              Pruebas automatizadas
  docs/               Manual final
  docker-compose.yml  Orquestación integrada
  alembic.ini         Configuración de migraciones
  pytest.ini          Configuración de pruebas
```

Los scripts de inicialización de MongoDB usan el lenguaje admitido por `mongosh`;
no constituyen un backend Node.js. El código de aplicación y correo es Python.
Las ilustraciones del correo se conservan en `auth-service/app/assets` y su
generador reproducible es `scripts/generate_email_botanical.py`.

## 2. Configuración y dependencias

Docker Compose ejecuta los servicios sobre sus imágenes Python. Para ejecución
nativa se utilizan Python 3.11/3.12 y los `requirements.txt` de cada componente.
Las pruebas añaden `requirements-test.txt` y las dependencias del servicio probado.

La configuración se lee del entorno y del `.env` local. Las contraseñas, llaves
privadas y tokens no aparecen en este manual. El mismo `JWT_SECRET` se utiliza
en Auth y en los servicios que validan las sesiones.

| Grupo | Variables principales | Uso |
|---|---|---|
| MongoDB en Compose | `MONGO_USER`, `MONGO_PASSWORD`, `MONGO_DB` | Inicialización y conexión interna |
| PostgreSQL en Compose | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Inicialización y conexión interna |
| Conexión nativa | `MONGO_URI`, `POSTGRES_URI` | URLs de bases accesibles desde el proceso |
| JWT | `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRE_HOURS` / `JWT_EXPIRATION_HOURS` | Firma y expiración de sesiones |
| OTP | `OTP_HASH_SECRET`, `OTP_LINK_SECRET`, `OTP_EXPIRATION_MINUTES`, `OTP_MAX_ATTEMPTS`, `OTP_MAX_RESENDS` | Códigos y límites |
| Entorno | `ENVIRONMENT`, `CORS_ORIGINS` | Modo y orígenes explícitos |
| Enlaces del cliente | `FRONTEND_URL`, `FRONTEND_ORIGIN`, `FRONTEND_LOGIN_PATH`, `API_PUBLIC_URL` | Pantalla de acceso y enlaces públicos |
| SMTP | `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURE`, `SMTP_USER`, `SMTP_APP_PASSWORD`, `MAIL_FROM` | Correo de verificación |
| Entrega OTP | `OTP_DELIVERY_MODE`, `OTP_EXPOSE_CODE_IN_RESPONSE` | SMTP o pruebas; exposición desactivada en uso real |
| Google | `GOOGLE_CLIENT_ID`, `GOOGLE_TIMEOUT_SECONDS` | Verificación del ID token del cliente OAuth |
| Fotos | `IMAGE_STORAGE_PROVIDER=imagekit`, `IMAGEKIT_PRIVATE_KEY`, `IMAGEKIT_PUBLIC_KEY` | Almacenamiento original |
| Comunicación interna | `AGENT_API_KEY` | Clave compartida de Chat/Agent; mínimo 32 caracteres |
| Ollama | `OLLAMA_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_TIMEOUT_SECONDS` | Modelo y proveedor de generación |
| Generación | `OLLAMA_CONTEXT_WINDOW`, `OLLAMA_MAX_OUTPUT_TOKENS`, `OLLAMA_KEEP_ALIVE` | Contexto, salida y permanencia en memoria |
| Visión/RF | `PLAGUE_MODEL_PATH`, `DISEASE_MODEL_PATH`, `RF_MODEL_PATH`, `AI_DEVICE` | Pesos y dispositivo |
| Validación visual | `AI_MAX_IMAGE_BYTES`, `AI_MIN_CONFIDENCE`, `AI_MIN_MARGIN` | Tamaño, confianza y margen |

En Compose, las URLs internas de MongoDB/PostgreSQL y Ollama se establecen para
la red de contenedores. `APP_API_KEY` es un alias interno admitido por Agent;
si se configura, tiene prioridad y debe coincidir con la clave que usa Chat.
`JWT_SECRET` y `OTP_HASH_SECRET` tienen un mínimo de 32 caracteres.

SMTP admite puerto 465 con TLS directo (`SMTP_SECURE=true`) y 587 con STARTTLS
(`SMTP_SECURE=false`). Auth también acepta aliases `OTP_EMAIL_*` y `MAIL_*`.
`OTP_DELIVERY_MODE=console` se reserva para pruebas; no envía correos. En
`ENVIRONMENT=production` se exige SMTP y códigos ocultos en las respuestas.

### Artefactos V6

```text
plagas-service/app/models/ml/yolo_plagas_veracruz_v6.pt
plagas-service/app/models/ml/yolo_enfermedades_veracruz_v6.pt
plagas-service/app/models/ml/metadata_ia_veracruz_v6.json
huertos-service/app/models/ml/random_forest_veracruz.joblib
huertos-service/app/models/ml/random_forest_metadata.json
```

Compose monta los directorios de pesos en solo lectura. Los archivos de modelos
no forman parte de las capas de las imágenes de servicio. Los aliases históricos
de pesos se conservan para compatibilidad. La carga de PyTorch/joblib utiliza
únicamente artefactos de procedencia confiable.

Ollama mantiene su propio modelo en un volumen independiente. El predeterminado
es `gemma3:1b`; `OLLAMA_MODEL` selecciona otra variante disponible. La imagen y
el modelo conversacional se descargan en la preparación inicial si faltan.

## 3. Instalación y operación

Con la configuración local y los cinco artefactos V6 disponibles, el arranque
integrado se realiza desde la raíz:

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps -a
curl.exe --connect-timeout 5 --max-time 30 http://localhost:8000/api/health
```

La primera construcción instala dependencias. Las construcciones posteriores
reutilizan las capas que no cambiaron. `ollama-init` comprueba el modelo y lo
descarga solamente si falta. La instalación inicial necesita conectividad.

Compose espera las bases de datos y las comprobaciones de disponibilidad de
los servicios. Agent espera la preparación de Ollama, Chat espera a Agent y
Gateway espera a los servicios de negocio. Estas condiciones controlan el
arranque; una caída posterior se informa mediante salud y respuestas HTTP.

Para iniciar imágenes existentes sin construir ni descargar:

```powershell
docker compose up -d --no-build --pull never
```

Para detener conservando imágenes, contenedores y volúmenes:

```powershell
docker compose stop
```

Para revisar un servicio:

```powershell
docker compose logs --tail 100 huertos-service
docker compose logs --tail 100 gateway
```

`start.ps1` inicia la pila y muestra las URLs de documentación y módulos.
`docker compose down -v` elimina los volúmenes asociados: no forma parte de
la detención ordinaria porque borra bases de datos y el modelo persistido.

La actualización normal de código de Huertos/Gateway es:

```powershell
docker compose build huertos-service gateway
docker compose up -d --no-deps huertos-service gateway
```

`scripts/Dockerfile.code-update` permite actualizar código sobre una imagen
local existente sin instalar dependencias. Solo se utiliza cuando los paquetes
de esa imagen ya satisfacen el código. Los cambios de dependencias se construyen
con los Dockerfiles normales. Los pesos no se descargan durante la inferencia.

## 4. Autenticación y sesiones

Las rutas de negocio requieren `Authorization: Bearer <JWT_DE_LA_API>`.
Swagger permite introducir el JWT en **Authorize**, sin añadir manualmente
`Bearer` al campo del diálogo. No se utiliza la llave interna de Agent.

### Registro y login con OTP

1. `POST /api/auth/register` recibe datos de registro y devuelve HTTP 201 con
   `challengeId`, `expiresAt` y `maskedEmail`.
2. `POST /api/auth/login` recibe correo/contraseña y devuelve un desafío OTP.
3. `POST /api/auth/verify-otp` recibe el desafío y el código de seis dígitos.
   Para registro/login devuelve `token`, `userId` y `expiresAt`.
4. `POST /api/auth/resend-otp` recibe `challengeId` y rota el código.

Ejemplos ilustrativos; el código debe ser el recibido por correo:

```json
{"email":"persona@example.com","password":"CONTRASENA_DEL_USUARIO"}
```

```json
{"challengeId":"ID_DEL_DESAFIO","otpCode":"123456"}
```

El registro también recibe `nombre`, `apellidos` y `confirmPassword`. Los códigos
caducan a los cinco minutos por defecto; se permiten cinco intentos y tres
reenvíos. Se almacenan protegidos con HMAC, se consumen una sola vez y los
códigos anteriores del mismo flujo se invalidan al rotarlos. Las contraseñas
nuevas utilizan bcrypt-SHA256; se conservan los hashes bcrypt compatibles.

### Google Sign-In

`GET /api/auth/google/config` devuelve `enabled` y el Client ID público.
El cliente obtiene un ID token mediante Google Identity Services y lo envía:

```json
{"credential":"ID_TOKEN_EMITIDO_POR_GOOGLE"}
```

`POST /api/auth/google` verifica firma, audiencia, emisor, expiración y correo
verificado. Abre sesión sin OTP y devuelve el **JWT de Huerto Connect** en
`token`. El ID token de Google solo autentica ese intercambio; no es el JWT
usado para las demás rutas. Se admiten también los aliases `idToken` e `id_token`.

El cliente OAuth tiene los orígenes exactos del frontend autorizados, incluyendo
protocolo y puerto. La página temporal de prueba no forma parte del proyecto.
Para correos externos a Gmail/Workspace, la vinculación de una cuenta existente
se realiza mediante `POST /api/auth/google/link` desde una sesión verificada.
Las cuentas inactivas, suspendidas o eliminadas no se restauran automáticamente.

### Recuperación y sesiones

La recuperación utiliza `forgot-password`, verificación OTP y `reset-password`.
La verificación de recuperación devuelve `resetToken`, no un JWT de acceso.
El token de restablecimiento tiene un solo uso y caduca a los diez minutos.
La respuesta inicial no revela si un correo está registrado.

| Método | Ruta | Función |
|---|---|---|
| POST | `/api/auth/register` | Registro y desafío OTP |
| POST | `/api/auth/login` | Login y desafío OTP |
| POST | `/api/auth/send-otp` | Alias de login |
| POST | `/api/auth/verify-otp` | JWT o token de recuperación según el flujo |
| POST | `/api/auth/resend-otp` | Rotación del OTP |
| GET | `/api/auth/google/config` | Configuración pública |
| POST | `/api/auth/google` | Login/registro con Google |
| POST | `/api/auth/google/link` | Vincular Google a la cuenta verificada |
| POST | `/api/auth/forgot-password` | Desafío de recuperación |
| POST | `/api/auth/reset-password` | Nueva contraseña con `resetToken` |
| GET | `/api/auth/session`, `/api/auth/me` | Sesión y usuario autenticado |
| POST | `/api/auth/logout` | Revocar sesión actual |
| GET | `/api/auth/sesiones` | Sesiones propias activas |
| DELETE | `/api/auth/sesiones/{session_id}` | Revocar una sesión propia |
| POST | `/api/auth/sesiones/revoke-all` | Revocar otras sesiones propias |

La validación cruza el JWT, usuario, sesión activa, expiración y revocación en
MongoDB. El planificador elimina desafíos y tokens expirados y sesiones inactivas.
El administrador existente no cambia de contraseña al reiniciar el servicio.

## 5. Huertos, regiones y catálogos

### Regiones oficiales

El catálogo corresponde a las regiones de planeación de Veracruz:

Huasteca Alta, Huasteca Baja, Totonaca, Nautla, Capital, Las Montañas, Sotavento,
Papaloapan, Los Tuxtlas y Olmeca.

Se trabaja por nombre. Se normalizan mayúsculas/acentos y aliases equivalentes;
los `region_id` históricos siguen siendo compatibles en los recursos heredados.
Nombre e ID contradictorios se rechazan. El catálogo oficial no se renombra ni
se elimina mediante las rutas de administración.

Ejemplo de creación de huerto:

```json
{"nombre":"Mi huerto","municipio":"Xalapa","region":"Capital"}
```

`POST /api/huertos` devuelve `id`; ese valor identifica siembras, inferencias y
reportes del huerto. Un usuario solo puede operar sus propios huertos, incluso
si tiene rol Técnico o Admin. La eliminación es lógica y no borra registros
relacionados. Salud admite 0 a 100 y las fechas de siembra usan `YYYY-MM-DD`.

| Método | Ruta | Función |
|---|---|---|
| GET, POST | `/api/huertos` | Listar huertos propios / crear huerto |
| GET, PUT, DELETE | `/api/huertos/{huerto_id}` | Consultar / actualizar / eliminar huerto propio |
| GET, POST | `/api/regiones` | Catálogo / incorporación de región oficial |
| GET, PUT, DELETE | `/api/regiones/{region}` | Consulta y administración del catálogo por nombre |
| GET | `/api/regiones/{region}/plantios` | Plantíos de huertos propios en la región |
| GET, POST | `/api/cultivos` | Catálogo compartido / creación |
| PUT, DELETE | `/api/cultivos/{cultivo_id}` | Edición / eliminación según rol |
| POST | `/api/cultivos/siembras` | Vincular cultivo activo y huerto propio |
| GET | `/api/cultivos/siembras/{huerto_id}` | Siembras del huerto propio |

Todos los roles pueden consultar/crear cultivos; Técnico/Admin pueden editar y
Admin puede eliminar. Un cultivo con siembras asociadas se desactiva en lugar
de eliminarse. Las referencias inexistentes o ajenas se rechazan.

### Perfiles, contacto, notificaciones y datos

| Método | Ruta | Función |
|---|---|---|
| GET, POST | `/api/usuarios` | Listado y creación por Admin |
| GET, PATCH | `/api/usuarios/{user_id}` | Consulta/actualización según propiedad y rol |
| DELETE | `/api/usuarios/{user_id}` | Baja por Admin |
| PATCH | `/api/usuarios/{user_id}/foto` | Foto de perfil según autorización |
| POST | `/api/public/contacto` | Formulario público de contacto |
| GET | `/api/public/contacto` | Consulta de contactos por Admin |
| GET | `/api/notificaciones` | Notificaciones propias paginadas |
| POST | `/api/notificaciones` | Creación por Admin/Técnico |
| GET | `/api/notificaciones/resumen` | Conteo y resumen propios |
| PATCH | `/api/notificaciones/leer-todas` | Marcar notificaciones propias |
| PATCH | `/api/notificaciones/{notif_id}/leer` | Marcar una notificación propia |
| GET, POST | `/api/datasets/imagenes` | Imágenes de dataset por Admin/Técnico |

La edición de un perfil no permite a un usuario elevar su rol ni cambiar el
correo sin verificación. Las fotos de perfil usan el campo multipart `foto`.
Los datasets verifican huerto/propietario y no exponen imágenes históricas sin
asignación. Contacto guarda la solicitud e intenta su entrega por SMTP.

## 6. Comunidad Agricultora

Todas las rutas requieren sesión activa. La publicación no necesita un ID previo;
el servidor lo crea y lo devuelve. El autor se obtiene del JWT/sesión y no se
acepta en el cuerpo. No se comparte correo ni información de sesiones.

### Crear, comentar y editar

**Paso 1: crear publicación**, en `POST /api/comunidad/publicaciones`:

```json
{
  "titulo": "Mi experiencia con jitomate en maceta",
  "contenido": "Mejoré el drenaje y reviso la humedad antes de regar.",
  "tipo": "Experiencia",
  "region": "Capital",
  "cultivo": "Jitomate"
}
```

La respuesta HTTP 201 contiene `id`. En Swagger no existe un parámetro de ID
para esta creación: solo el cuerpo JSON. Los tipos son `Experiencia`, `Pregunta`
y `Consejo`; región/cultivo son opcionales. Título admite 3–160 caracteres,
contenido 1–5000 y cultivo 1–80. Cultivo es una etiqueta libre, no una inferencia.

**Paso 2: crear comentario**, usando el ID anterior como `publicacion_id` en
`POST /api/comunidad/publicaciones/{publicacion_id}/comentarios`:

```json
{"contenido":"¿Cada cuánto revisas la humedad de tus macetas?"}
```

La respuesta HTTP 201 contiene el `id` **del comentario**. Ese nuevo ID se utiliza
como `comentario_id` en PATCH/DELETE de comentarios. El comentario admite hasta
1500 caracteres. No se utiliza el ID de la publicación para editar un comentario.

**Paso 3: editar publicación**, con `PATCH /api/comunidad/publicaciones/{id}`:

```json
{"titulo":"Mi experiencia actualizada","contenido":"Este es el resultado del nuevo manejo de riego."}
```

Editar un comentario utiliza `PATCH /api/comunidad/comentarios/{comentario_id}`
con el mismo formato de texto del paso 2. Solo el autor modifica/elimina su
contenido. Un administrador modera, pero no suplanta la edición del autor.

| Método | Ruta relativa a `/api/comunidad` | Función |
|---|---|---|
| GET | `/opciones` | Regiones, tipos y límites |
| POST | `/publicaciones` | Crear publicación; devuelve `id` |
| GET | `/publicaciones` | Listado filtrado y paginado |
| GET, PATCH, DELETE | `/publicaciones/{publicacion_id}` | Detalle / edición / baja lógica |
| POST | `/publicaciones/{publicacion_id}/fotos` | Foto original con campo `foto` |
| POST | `/publicaciones/{publicacion_id}/comentarios` | Crear comentario; devuelve su `id` |
| GET | `/publicaciones/{publicacion_id}/comentarios` | Comentarios paginados |
| PATCH, DELETE | `/comentarios/{comentario_id}` | Editar / eliminar comentario propio |
| PUT, DELETE | `/publicaciones/{publicacion_id}/me-gusta` | Agregar / retirar me gusta |
| PATCH | `/publicaciones/{publicacion_id}/moderacion` | Admin: ocultar/restablecer |
| PATCH | `/comentarios/{comentario_id}/moderacion` | Admin: ocultar/restablecer |
| GET | `/moderacion/{tipo}/{contenido_id}` | Admin: últimas 20 decisiones |

### Listados, fotos y moderación

El listado usa `limit=10` por defecto, máximo 50, y devuelve `items`, `hay_mas`
y `siguiente_cursor`. Se continúa con ese cursor y los mismos filtros. El orden
es por identificador de creación descendente; editar no reordena la publicación.
Filtros: `region`, `cultivo`, `tipo`, `solo_mias`. Cultivo ignora acentos y
mayúsculas, sin inventar sinónimos.

El listado devuelve un resumen de hasta 240 caracteres y omite las URLs de fotos
por defecto (`fotos=[]`, `total_fotos` disponible). `incluir_fotos=true` incorpora
las URLs; el detalle contiene texto completo y URLs originales. No hay base64
en las respuestas ni conteo completo de todas las publicaciones.

Cada publicación admite cuatro fotos de hasta 5 MiB, JPEG/PNG/WebP y 25 millones
de píxeles. El archivo se valida y almacena sin reducirlo. El límite de cantidad
se comprueba también al asociar una subida concurrente. Si la publicación deja
de estar disponible durante la subida, se intenta retirar el archivo recién creado.

Me gusta es idempotente: repetir PUT no duplica y repetir DELETE es seguro.
POST de publicaciones/comentarios no tiene clave de idempotencia; ante una
respuesta incierta se consulta el listado antes de repetir la creación.
Los límites básicos son cinco publicaciones y veinte comentarios por minuto
por usuario, con 429 y `Retry-After: 60`.

La moderación recibe:

```json
{"estado":"Oculta","motivo":"Contenido ajeno a la comunidad agricultora"}
```

Admin puede usar `Publicada` u `Oculta`, con motivo obligatorio. El documento
conserva las últimas veinte decisiones. Una publicación oculta no aparece en
el listado general; su autor/Admin pueden leerla, pero no recibe ediciones,
fotos, comentarios ni me gusta mientras está oculta. El autor puede eliminarla.

- Propias ocultas: `solo_mias=true&incluir_ocultas=true`.
- Admin: `incluir_ocultas=true` permite revisión de publicaciones ajenas.
- Admin: `incluir_ocultos=true` permite revisión de comentarios ocultos.
- `{tipo}` del historial admite `publicaciones` o `comentarios`.

La eliminación es lógica. Los documentos y fotos asociados se conservan;
restablecer por moderación no recupera contenido eliminado por su autor.
Ocultar en la API no revoca una URL pública de ImageKit copiada anteriormente.
Este módulo no almacena fotos privadas ni convierte publicaciones en diagnósticos.
Los textos se muestran como texto plano; un cliente no los inserta como HTML.
No incluye mensajería privada.

## 7. Inferencia visual y rendimiento agrícola

### YOLO V6

| Método | Ruta | Función |
|---|---|---|
| POST | `/ai/plagas/predict` | Clasificar foto de plaga |
| POST | `/ai/enfermedades/predict` | Clasificar foto de enfermedad |
| GET | `/ai/{tipo}/classes` | Clases del artefacto; `plagas` o `enfermedades` |
| GET | `/ai/diagnosticos/{huerto_id}` | Historial V6 de huerto propio |
| GET | `/ai/health` | Disponibilidad de los tres modelos |
| POST | `/api/plagas/detectar` | Alias compatible de clasificación |

Los POST visuales reciben multipart con `imagen`, `huerto_id` opcional y
`guardar_imagen=false` por defecto. Swagger muestra un selector de archivo.
El tamaño predeterminado máximo es 10 MiB y 25 millones de píxeles; se admiten
JPEG/PNG/WebP y se verifican contenido y MIME. La orientación EXIF se aplica a
la imagen utilizada para inferencia, sin alterar los bytes almacenados.

Sin huerto, se devuelve la clasificación sin persistir un diagnóstico. Con
huerto propio se guarda en MongoDB y se devuelve `diagnostico_id`.
`guardar_imagen=true` almacena el original en ImageKit y devuelve `imagen_url`
y `imagen_file_id`. Un fallo de almacenamiento en ese flujo responde 502.

Los modelos clasifican la imagen completa: no generan cajas de detección.
El artefacto de plagas contiene 17 clases y el de enfermedades 10; `model.names`
es la autoridad, no las listas descriptivas de metadata. Se cargan una vez al
arrancar. Un modelo ausente/inválido responde 503, sin fabricar predicciones.

La respuesta contiene `tipo`, `detectado`, `clase`, `confianza`, `margen`, `top`
(hasta tres clases), `modelo`, `version`, `nota` y `recomendaciones`.
Las probabilidades están entre 0 y 1. Los umbrales predeterminados son confianza
0.70 y margen 0.12. Una clasificación que supera ambos sigue sin confirmar una
enfermedad: fotos fuera del dominio pueden producir respuestas equivocadas.
La orientación preventiva son reglas explícitas, no tratamientos aprendidos.
Los resultados compatibles con HLB requieren interpretación especializada.

### Random Forest

| Método | Ruta | Función |
|---|---|---|
| GET | `/ai/rendimiento/opciones` | Categorías reales de municipio/cultivo/ciclo/modalidad |
| POST | `/ai/rendimiento/predict` | Estimar rendimiento agrícola histórico |

El POST recibe `Anio` (entero entre 2000 y 2100), `Nommunicipio`, `Nomcultivo`,
`Nomcicloproductivo` y `Nommodalidad`. Las categorías se obtienen del endpoint
de opciones, no de un catálogo inventado. Se normalizan diferencias de acentos
y mayúsculas; categorías desconocidas producen 422.

```json
{
  "Anio": 2026,
  "Nommunicipio": "Xalapa",
  "Nomcultivo": "Maíz grano",
  "Nomcicloproductivo": "Primavera-Verano",
  "Nommodalidad": "Temporal"
}
```

El ejemplo ilustra los campos; la selección efectiva corresponde a las opciones
admitidas por el artefacto instalado. La salida incluye rendimiento, metadatos,
limitaciones y orientación de planificación. El modelo no predice clima,
fertilización, plagas ni cultivo ideal y no garantiza una cosecha. La validación
individual de categorías no verifica todas las combinaciones históricas entre
municipio y cultivo.

Cada modelo tiene control de concurrencia: una solicitud que encuentra su
modelo ocupado responde 429 con `Retry-After`. La configuración utiliza un
worker para no duplicar los pesos en memoria.

### Alertas, estadísticas y compatibilidad

| Método | Ruta | Función |
|---|---|---|
| GET, POST | `/api/alertas` | Consulta propia / creación por Admin/Técnico |
| PATCH, DELETE | `/api/alertas/{alerta_id}` | Gestión autorizada de alertas |
| GET | `/api/dashboard/kpis` | Estadísticas por Admin/Técnico |
| GET, POST | `/api/datasets` | Catálogo SQL por Admin/Técnico |

Las rutas manuales `/api/plagas`, `/api/modelos`, `/api/predicciones` y
`/api/recomendaciones` se conservan para sus consumidores SQL, pero no aparecen
en Swagger como flujo de inferencia. Sus registros no se mezclan con el historial
V6 de MongoDB. El endpoint histórico de recomendación climática de Huertos no
forma parte de la API vigente. No existe integración Cloudinary.

## 8. Chat y asistente agrícola

`POST /api/agent/v1/chat` es la ruta de generación pública y requiere JWT:

```json
{"message":"¿Cómo reviso el riego de jitomate en maceta?"}
```

La respuesta incluye `answer`, `status`, `safety_reason`, `model`, `request_id`
y `conversation_id`. Para continuar, el cliente añade el `conversation_id`
devuelto. Los estados del asistente son `answered`, `blocked` y `redirected`.

Chat comprueba la propiedad de la conversación, prepara el contexto y llama
internamente a `POST /v1/generate` con `X-API-Key` y `X-User-ID`. Agent recibe
mensaje/historial, no un identificador de conversación. Chat guarda los
intercambios exitosos; no conserva fallos del proveedor como respuestas agrícolas.

| Método | Ruta | Función |
|---|---|---|
| POST | `/api/agent/v1/chat` | Generación y continuación de conversación |
| GET | `/api/agent/v1/conversations/{conversation_id}/messages` | Historial propio |
| DELETE | `/api/agent/v1/conversations/{conversation_id}` | Cerrar conversación propia |
| GET, POST | `/api/chatbot/conversaciones` | Listar / crear conversación propia |
| GET, POST | `/api/chatbot/conversaciones/{conv_id}/mensajes` | Leer / incorporar mensajes autorizados |
| PATCH | `/api/chatbot/conversaciones/{conv_id}/cerrar` | Cerrar conversación propia |
| GET | `/api/chatbot/metricas` | Métricas por Admin/Técnico |

Agent no mantiene SQLite ni otro historial. Las antiguas rutas internas de
conversación no son el contrato público. La generación utiliza `gemma3:1b`,
contexto de 2048 tokens, salida de hasta 180 tokens, seis mensajes/2400 caracteres
de historial y permanencia en memoria de 30 minutos. El historial completo
permanece en Chat; solo se limita lo enviado al generador.

Límites predeterminados: mensaje de 2000 caracteres, cuerpo de 64 KiB, una
generación simultánea, dos segundos de espera de turno y 120 segundos de timeout.
Agent precarga el modelo y registra tiempos sin registrar preguntas, respuestas
ni claves. Los límites de generación y rate limiting son por proceso.

La generación ocurre en el servidor, no en el dispositivo móvil. El modelo
ligero proporciona orientación básica; los filtros temáticos/de seguridad no
garantizan exactitud agronómica ni sustituyen a un especialista.

## 9. Reportes y auditoría

| Método | Ruta | Función |
|---|---|---|
| GET | `/api/reportes/huertos/{huerto_id}/{formato}` | Descarga `pdf` o `csv` |
| GET | `/api/reportes/huertos/{huerto_id}/estadisticas/resumen` | Resumen propio |
| GET, POST | `/api/reportes` | Catálogo de metadatos por Admin/Técnico |
| DELETE | `/api/reportes/{reporte_id}` | Eliminar metadato propio por Admin |
| GET | `/api/auditoria` | Auditoría global por Admin |

Las descargas y estadísticas usan los diagnósticos V6 del usuario en MongoDB,
no registros manuales SQL. Huerto y diagnósticos se verifican por propiedad para
todos los roles. Los filtros `desde` y `hasta` reciben fechas ISO y cubren días
inclusivos en UTC. `limite` admite 1–1000, con 1000 por defecto.

Se exportan los registros más recientes. `X-Report-Total`, `X-Report-Records` y
`X-Report-Truncated` informan el alcance de la descarga. El PDF incluye aviso de
truncamiento, huerto/municipio, modelo/versión, confianza, cabeceras y páginas.
Los textos históricos extensos se abrevian a 400 caracteres en PDF; CSV los
conserva. El CSV tiene BOM UTF-8 y escapa posibles fórmulas de hoja de cálculo.

Cada emisión se registra en `reporte_exportaciones`. Las descargas tienen
`Cache-Control: no-store`, no generan un archivo permanente en ImageKit ni una
URL pública y no requieren ese proveedor.

El catálogo SQL acepta nombre, tipo y URL HTTP(S) opcional sin credenciales
incrustadas. Con URL se registra `Generado`; sin ella, `En_proceso`. Guardar
metadatos no lanza un trabajo de generación ni valida accesibilidad externa.
Crear/eliminar metadatos registra auditoría en la misma transacción. Eliminar
metadatos no elimina archivos externos.

## 10. Fotos, correo y conectividad limitada

### Almacenamiento original

El adaptador ImageKit envía los bytes validados sin redimensionar ni recomprimir.
Las URLs nuevas incluyen `tr=orig-true` para solicitar el original. La llave
privada se utiliza únicamente en Python mediante autenticación del servidor.
Por compatibilidad, algunos contratos utilizan `secure_url` para la URL y
`public_id` para el `fileId` de ImageKit. No se transforman URLs históricas ni
se eliminan automáticamente archivos anteriores.

Los límites de tamaño/dimensiones rechazan archivos mayores; no los reducen
silenciosamente. Una foto de baja calidad puede afectar la clasificación.
La validación de formato no certifica enfoque, iluminación ni precisión del modelo.

### Correo OTP

El correo incluye texto plano y HTML adaptable, código por dígitos, caducidad
y enlace a la pantalla de acceso. Utiliza una ilustración botánica de maceta,
árbol y raíces ramificadas sobre toda la composición, con tonos crema/oliva.
Tres PNG se incrustan mediante MIME inline; no dependen de descargas de imágenes
remotas para mostrarse. El HTML escapa datos dinámicos del destinatario.

El botón abre la pantalla de login, no consume el OTP mediante GET ni lo incluye
en la URL. Auth confirma aceptación SMTP antes de responder; si falla, devuelve
503 e invalida el código no entregado. Aceptación SMTP no garantiza llegada a la
bandeja principal: el cliente de correo/proveedor aplica sus propias políticas.

### Transferencia de datos

Gateway y los servicios con observabilidad comprimen respuestas JSON/HTTP
superiores a 1 KiB con gzip, sin pérdida. Los navegadores negocian la compresión;
otros clientes pueden enviar `Accept-Encoding: gzip`. Esto no comprime ni
reduce fotografías de entrada.

El historial de diagnósticos devuelve veinte registros por defecto, máximo 200,
con `skip`/`limit`. Comunidad devuelve diez resúmenes por página y no precarga
fotos. Notificaciones/conversaciones también tienen consultas limitadas.
`guardar_imagen=false` evita la segunda transferencia al proveedor cuando solo
se necesita inferencia. La API no implementa operación offline ni sincronización
del dispositivo; la disponibilidad de red sigue siendo necesaria.

## 11. Persistencia, permisos y errores

MongoDB conserva usuarios, sesiones, desafíos OTP, huertos, siembras, diagnósticos,
conversaciones, notificaciones y las colecciones `comunidad_publicaciones`,
`comunidad_comentarios`, `comunidad_me_gusta`. Los índices se crean al arrancar;
me gusta tiene unicidad por publicación/usuario. PostgreSQL utiliza Alembic para
sus tablas y catálogo/auditoría. Los scripts `init-mongo.js` e `init-postgres.sql`
se aplican en la inicialización de volúmenes nuevos.

El catálogo oficial se inicializa de forma idempotente. La herramienta
`migrate_veracruz_regions.py` respalda/remapea catálogos históricos de manera
explícita; regiones no equivalentes quedan sin asignación, con su nombre anterior
conservado. No se inventa una ubicación al migrar.

Roles normalizados: `Usuario`, `Tecnico` y `Admin`. Tener un rol administrativo
no omite controles de propiedad de huertos, reportes o conversaciones. Comunidad
tiene permisos separados para autoría y moderación. Datos privados y claves
internas no se devuelven en errores ni registros de solicitudes.

| Código HTTP | Significado general |
|---|---|
| 200 | Consulta o modificación completada |
| 201 | Recurso creado; su identificador está en la respuesta |
| 400 | Solicitud sin cambios o flujo inválido |
| 401 | Token ausente, inválido, expirado o sesión revocada |
| 403 | Rol insuficiente, cuenta bloqueada o acción no permitida |
| 404 | Recurso inexistente, ajeno o no visible |
| 409 | Conflicto, referencia activa o estado concurrente incompatible |
| 413 | Cuerpo o imagen demasiado grande |
| 415 | Formato de imagen no admitido |
| 422 | Error de campos, categorías, imagen o identificador |
| 429 | Límite temporal/modelo ocupado; consultar `Retry-After` |
| 502 | Error del proveedor de almacenamiento en inferencia/proxy |
| 503 | Servicio, base, modelo, correo o almacenamiento no disponible |
| 504 | Tiempo agotado al comunicarse con el proveedor |

El mensaje habitual de error es `detail`; las validaciones de FastAPI incluyen
el detalle por campo. Los cuerpos máximos se limitan en cada servicio.
CORS admite orígenes explícitos, no comodines con credenciales.

`/health/live` indica proceso activo; `/health/ready` comprueba dependencias.
Gateway `GET /api/health` consulta los servicios en paralelo y devuelve 503 si
alguno no está listo. Chat comprueba MongoDB/Agent; Agent comprueba Ollama y
modelo exacto; Plagas comprueba ambas bases y los tres modelos V6.

## 12. Verificación y alcance técnico

Las pruebas automatizadas están en `tests`. Para ejecución nativa, las
dependencias de los servicios y `requirements-test.txt` están instaladas en el
entorno Python. La suite se ejecuta con:

```powershell
python -m pytest tests -q
```

Las pruebas aíslan proveedores y bases con dobles controlados, pero ejercitan
los contratos ASGI, JWT/sesiones, propiedad, validaciones y OpenAPI. Las pilas
`compose.test.yml` de Auth/Huertos/Plagas/Reportes permiten verificaciones
adicionales con bases separadas de las operativas.

Los scripts smoke crean registros propios de prueba y tienen limpieza acotada:

```powershell
docker compose cp scripts/smoke_comunidad.py huertos-service:/tmp/smoke_comunidad.py
docker compose exec -T huertos-service python /tmp/smoke_comunidad.py --storage
docker compose cp scripts/smoke_ai_workflows.py plagas-service:/tmp/smoke_ai_workflows.py
docker compose exec -T plagas-service python /tmp/smoke_ai_workflows.py --storage --chat
```

`--storage` realiza una subida real y elimina el archivo temporal. El smoke no
borra cuentas reales. `verify_huertos_external.py --smtp` verifica TLS y
autenticación SMTP; el envío a un destinatario requiere la opción explícita de
destino. `benchmark_agent.py` mide preguntas agrícolas genéricas sin persistencia.

### Evidencia funcional

- La suite integrada aprobó 125 pruebas, incluidos los contratos, permisos,
  procesos de inferencia y la organización de Swagger.
- Google Sign-In completó la prueba interactiva reportada por el usuario.
- Comunidad completó creación, comentarios, filtros, me gusta idempotente,
  moderación, historial y baja lógica mediante Gateway real.
- Las subidas reales a ImageKit verificaron coincidencia byte a byte del original;
  los registros/archivos temporales de las verificaciones integradas se eliminaron.
- Plagas, Enfermedades y Random Forest devolvieron HTTP 200 en verificación
  funcional; Gateway informó todas las dependencias disponibles.
- Una consulta local por el chat público tardó 9.16 segundos con `gemma3:1b`.
  Muestras aisladas sin historial estuvieron entre 7.08 y 11.83 segundos; el modelo
  anterior 4B necesitó aproximadamente 69 segundos en ese equipo.

Las mediciones son muestras locales, no garantías de duración para cualquier
CPU, carga, conversación o conexión rural. Las pruebas funcionales no constituyen
una auditoría de seguridad de producción, un estudio estadístico de latencia ni
una validación de precisión agronómica. Fotos fuera del entrenamiento pueden
clasificarse con confianza alta; el sistema comunica orientación y límites, no
certificados de diagnóstico ni tratamientos garantizados.

## 13. Versiones de la entrega

| Módulo | Versión de API | Etiqueta de entrega |
|---|---|---|
| Auth | 1.0.0 | `auth-service/v1.0.0` |
| Huertos y Comunidad | 1.0.0 | `huertos-service/v1.0.0` |
| Plagas e inferencia V6 | 1.0.0 | `plagas-service/v1.0.0` |
| Chat | 1.0.0 | `chat-service/v1.0.0` |
| Agent | 3.0.0 | `agent-service/v3.0.0` |
| Reportes | 1.0.0 | `reportes-service/v1.0.0` |
| Gateway | 1.0.0 | `gateway/v1.0.0` |

Las etiquetas identifican el mismo conjunto integrado de código. Las versiones
de API son independientes de la versión V6 de los artefactos de inferencia.
