"""
Auth Service — Conexión asíncrona a MongoDB mediante Motor.

Uso recomendado (lifespan de FastAPI):

    from app.core.database import connect_db, close_db, get_db

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await connect_db()
        yield
        await close_db()

    # Dentro de un endpoint:
    db = get_db()
    user = await db.usuarios.find_one({"email": email})
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

# ---------------------------------------------------------------------------
# Estado del cliente (módulo singleton)
# ---------------------------------------------------------------------------

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_db() -> None:
    """
    Inicializa el cliente Motor y selecciona la base de datos.

    Llama a esta función al arrancar la aplicación (lifespan startup).
    """
    global _client, _db

    _client = AsyncIOMotorClient(
        settings.MONGO_URL,
        serverSelectionTimeoutMS=5_000,  # falla rápido si no hay conexión
    )

    # Ping para verificar que la conexión es válida antes de continuar
    await _client.admin.command("ping")

    _db = _client[settings.DB_NAME]
    print(f"✅ MongoDB conectado — base de datos: '{settings.DB_NAME}'")


async def close_db() -> None:
    """
    Cierra el cliente Motor.

    Llama a esta función al detener la aplicación (lifespan shutdown).
    """
    global _client, _db

    if _client is not None:
        _client.close()
        _client = None
        _db = None
        print("🔌 MongoDB desconectado.")


def get_db() -> AsyncIOMotorDatabase:
    """
    Devuelve la instancia de la base de datos activa.

    Returns:
        Instancia de ``AsyncIOMotorDatabase``.

    Raises:
        RuntimeError: Si ``connect_db()`` no ha sido llamado previamente.
    """
    if _db is None:
        raise RuntimeError(
            "La base de datos no está inicializada. "
            "Asegúrate de llamar a connect_db() al iniciar la aplicación."
        )
    return _db
