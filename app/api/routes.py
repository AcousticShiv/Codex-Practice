from fastapi import APIRouter, HTTPException
from app.models import ConvertRequest, ConvertResponse
from app.services.converter import convert_m_to_tableau

router = APIRouter(prefix="/api/v1", tags=["converter"])


@router.post("/convert", response_model=ConvertResponse)
def convert(req: ConvertRequest):
    try:
        return convert_m_to_tableau(req.m_code)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {exc}") from exc
