from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from src.database.connection import get_db

from src.services.medical_history_service import (
    get_patient_medical_history
)


router = APIRouter()

templates = Jinja2Templates(
    directory="templates"
)


@router.get("/medical-history")
def medical_history_page(
    request: Request,
    db: Session = Depends(get_db)
):

    user_id = request.session.get(
        "user_id"
    )

    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    history = get_patient_medical_history(
        db=db,
        patient_id=user_id
    )

    return templates.TemplateResponse(
        request,
        "medical_history.html",
        {
            "user": request.session,
            "history": history
        }
    )