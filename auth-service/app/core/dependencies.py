"""
Auth Service — Dependencias de control de roles.

Separa las comprobaciones de autorización en funciones reutilizables
para mantener los routers limpios y con lógica de negocio explícita.

Roles válidos del sistema: admin, tecnico, usuario
(en minúsculas, tal como se almacenan en la colección usuarios del auth-service).

NOTA: Este módulo es específico del auth-service. Los otros servicios
usan ``shared.auth.dependencies``, que trabaja con roles en PascalCase
(Admin, Tecnico, Usuario). Mantener en sync si cambia la nomenclatura.
"""

from typing import Callable

from fastapi import Depends, HTTPException, status

from app.routers.dependencies import get_current_user


# ---------------------------------------------------------------------------
# Constantes de rol
# ---------------------------------------------------------------------------

ROLE_ADMIN = "admin"
ROLE_TECNICO = "tecnico"
ROLE_USUARIO = "usuario"

_ADMIN_ROLES = {ROLE_ADMIN, "Admin"}
_STAFF_ROLES = {ROLE_ADMIN, ROLE_TECNICO, "Admin", "Tecnico"}


# ---------------------------------------------------------------------------
# Dependencias de rol
# ---------------------------------------------------------------------------

async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Permite el acceso únicamente a usuarios con rol ``admin``.

    Raises:
        HTTPException 403: Si el usuario no es administrador.
    """
    role = (current_user.get("role") or current_user.get("rol") or "").lower()
    if role not in ("admin",):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de Administrador.",
        )
    return current_user


async def require_tecnico(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Permite el acceso a usuarios con rol ``admin`` o ``tecnico``.

    Raises:
        HTTPException 403: Si el usuario no es admin ni técnico.
    """
    role = (current_user.get("role") or current_user.get("rol") or "").lower()
    if role not in ("admin", "tecnico"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de Técnico o Administrador.",
        )
    return current_user


async def require_any_auth(current_user: dict = Depends(get_current_user)) -> dict:
    """Permite el acceso a cualquier usuario autenticado."""
    return current_user


# ---------------------------------------------------------------------------
# Factoría de dependencia de roles (compatible con el estilo de shared/)
# ---------------------------------------------------------------------------

def require_roles(roles: list[str]) -> Callable:
    """
    Factoría que devuelve una dependencia que exige que el usuario tenga
    uno de los roles indicados.

    Soporta roles en cualquier capitalización (admin / Admin / ADMIN).

    Example::

        @router.delete("/foo")
        async def delete_foo(user = Depends(require_roles(["admin"]))):
            ...
    """
    normalized = {r.lower() for r in roles}

    async def _check(current_user: dict = Depends(get_current_user)) -> dict:
        role = (current_user.get("role") or current_user.get("rol") or "").lower()
        if role not in normalized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permisos insuficientes. Roles permitidos: {', '.join(roles)}.",
            )
        return current_user

    return _check


# ---------------------------------------------------------------------------
# Verificación de propiedad (owner) o admin
# ---------------------------------------------------------------------------

def require_owner_or_admin(resource_user_id: str) -> Callable:
    """
    Valida que el usuario autenticado sea el dueño del recurso o un admin.

    Args:
        resource_user_id: ID del usuario propietario del recurso (string).

    Returns:
        Dependencia FastAPI que resuelve el usuario autenticado si pasa.

    Raises:
        HTTPException 403: Si el usuario no es propietario ni admin.

    Example::

        @router.get("/perfil/{user_id}")
        async def get_perfil(
            user_id: str,
            current_user: dict = Depends(require_owner_or_admin(user_id)),
        ):
            ...

    NOTA: Para usar con path params dinámicos, inyecta el check directamente
    en el body del endpoint (ver require_owner_or_admin_check).
    """
    async def _check(current_user: dict = Depends(get_current_user)) -> dict:
        user_id = str(current_user.get("_id") or current_user.get("id") or "")
        role = (current_user.get("role") or current_user.get("rol") or "").lower()

        if role != "admin" and user_id != resource_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso denegado. Solo puedes gestionar tu propio perfil.",
            )
        return current_user

    return _check


async def require_owner_or_admin_check(
    target_user_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Versión directa para usar en endpoints con path params.
    Llama esta función dentro del cuerpo del endpoint en lugar de en Depends.

    Example::

        @router.patch("/{user_id}/foto")
        async def update_foto(user_id: str, current_user = Depends(get_current_user)):
            await require_owner_or_admin_check(user_id, current_user)
    """
    user_id = str(current_user.get("_id") or current_user.get("id") or "")
    role = (current_user.get("role") or current_user.get("rol") or "").lower()

    if role != "admin" and user_id != target_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado. Solo puedes gestionar tu propio perfil.",
        )
    return current_user
