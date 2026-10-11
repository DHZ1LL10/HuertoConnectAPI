"""Compatibility route using the shared V6 classifier."""
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from app.routes.ai import Classification, classify
from shared.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/plagas", tags=["IA V6"])

@router.post("/detectar", response_model=Classification)
async def detectar_plaga(request: Request, imagen: UploadFile = File(...), huerto_id: str | None = Form(None), cultivo_id: str | None = Form(None), guardar_imagen: bool = Form(False, description="Guardar también la foto en ImageKit"), current_user=Depends(get_current_user)):
    """Alias de /ai/plagas/predict. Respuesta V6."""
    return await classify(request, "plaga", imagen, huerto_id, current_user, guardar_imagen)
