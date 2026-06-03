"""
Auth Service — Scheduler de limpieza automática de registros expirados.

Usa ``AsyncIOScheduler`` de APScheduler para ejecutar tareas de mantenimiento
sin bloquear el event-loop de FastAPI.

Jobs configurados:
  - ``cleanup_otp_challenges``  → cada hora (removes expirados o >24h)
  - ``cleanup_password_resets`` → cada hora (removes expirados o usados)
  - ``cleanup_inactive_sessions``→ cada 24 horas (removes inactivas >7 días)

Integración con FastAPI (lifespan):

    from app.core.scheduler import create_scheduler

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = await connect_mongodb()
        app.state.mongodb = db

        scheduler = create_scheduler(db)
        scheduler.start()
        yield
        scheduler.shutdown(wait=False)
"""

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger("auth.scheduler")


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

async def cleanup_otp_challenges(db: AsyncIOMotorDatabase) -> None:
    """
    Elimina OTP challenges expirados o creados hace más de 24 horas.

    Criterios de borrado (OR):
      - ``expires_at`` < ahora                  → expiración natural del OTP
      - ``created_at`` < ahora − 24 h           → antigüedad máxima de seguridad
    """
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)

    result = await db.otp_challenges.delete_many({
        "$or": [
            {"expires_at": {"$lt": now}},
            {"created_at": {"$lt": cutoff_24h}},
        ]
    })
    count = result.deleted_count
    if count:
        logger.info("🧹 [OTP Cleanup] Eliminados %d challenge(s) expirado(s).", count)
    else:
        logger.debug("✅ [OTP Cleanup] Sin registros expirados.")


async def cleanup_password_resets(db: AsyncIOMotorDatabase) -> None:
    """
    Elimina tokens de restablecimiento de contraseña expirados o ya usados.

    Criterios de borrado (OR):
      - ``expires_at`` < ahora    → token expirado (>10 min)
      - ``used_at`` != None       → token ya consumido
    """
    now = datetime.now(timezone.utc)

    result = await db.password_resets.delete_many({
        "$or": [
            {"expires_at": {"$lt": now}},
            {"used_at": {"$ne": None}},
        ]
    })
    count = result.deleted_count
    if count:
        logger.info("🧹 [Reset Cleanup] Eliminados %d token(s) expirado(s)/usado(s).", count)
    else:
        logger.debug("✅ [Reset Cleanup] Sin registros pendientes.")


async def cleanup_inactive_sessions(db: AsyncIOMotorDatabase) -> None:
    """
    Elimina sesiones inactivas (revocadas) con más de 7 días de antigüedad.

    Criterios de borrado (AND):
      - ``activa`` == False
      - ``created_at`` < ahora − 7 días
    """
    now = datetime.now(timezone.utc)
    cutoff_7d = now - timedelta(days=7)

    result = await db.sesiones.delete_many({
        "activa": False,
        "created_at": {"$lt": cutoff_7d},
    })
    count = result.deleted_count
    if count:
        logger.info("🧹 [Session Cleanup] Eliminadas %d sesión(es) inactiva(s).", count)
    else:
        logger.debug("✅ [Session Cleanup] Sin sesiones que limpiar.")


# ---------------------------------------------------------------------------
# Wrappers síncronos compatibles con APScheduler
# ---------------------------------------------------------------------------
# APScheduler llama a los jobs de forma síncrona, pero al usar AsyncIOScheduler
# las corutinas async se ejecutan de forma nativa en el event-loop de FastAPI.


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_scheduler(db: AsyncIOMotorDatabase) -> AsyncIOScheduler:
    """
    Crea y configura el ``AsyncIOScheduler`` con los 3 jobs de limpieza.

    Args:
        db: Instancia activa de ``AsyncIOMotorDatabase`` (de Motor).

    Returns:
        Instancia de ``AsyncIOScheduler`` lista para ser arrancada.
        Llama a ``.start()`` después de obtenerla y a ``.shutdown()``
        en el shutdown del lifespan.

    Example::

        scheduler = create_scheduler(db)
        scheduler.start()
    """
    scheduler = AsyncIOScheduler(
        job_defaults={
            "coalesce": True,        # si varios disparos se acumulan, ejecutar solo uno
            "max_instances": 1,      # evitar solapamiento de ejecuciones
            "misfire_grace_time": 60,# tolerar hasta 60 s de retraso
        },
        timezone="UTC",
    )

    # ── Job 1: Limpieza de OTP challenges (cada hora) ──────────────────────
    scheduler.add_job(
        cleanup_otp_challenges,
        trigger=IntervalTrigger(hours=1),
        id="cleanup_otp_challenges",
        name="Limpieza de OTP challenges expirados",
        args=[db],
        replace_existing=True,
    )

    # ── Job 2: Limpieza de password resets (cada hora) ────────────────────
    scheduler.add_job(
        cleanup_password_resets,
        trigger=IntervalTrigger(hours=1),
        id="cleanup_password_resets",
        name="Limpieza de tokens de reset expirados/usados",
        args=[db],
        replace_existing=True,
    )

    # ── Job 3: Limpieza de sesiones inactivas (cada 24 horas) ─────────────
    scheduler.add_job(
        cleanup_inactive_sessions,
        trigger=IntervalTrigger(hours=24),
        id="cleanup_inactive_sessions",
        name="Limpieza de sesiones inactivas (>7 días)",
        args=[db],
        replace_existing=True,
    )

    logger.info(
        "📅 Scheduler configurado: %d job(s) registrado(s).",
        len(scheduler.get_jobs()),
    )
    return scheduler
