from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from src.database.connection import get_db

from src.services.medical_history_service import (
    get_patient_medical_history
)

from src.config import TEMPLATES_DIR


router = APIRouter()

templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR)
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

    # A doctor can mark a note "patient can read it" from the doctor desk;
    # those share onto this page. Everything marked internal stays hidden -
    # the desk stores both kinds in doctor_patient_notes (visibility column).
    doctor_notes = []

    try:
        from src.services import doctor_desk_service as doctor_desk

        doctor_notes = [
            note for note in doctor_desk.notes_for(db, user_id)
            if (note.get("visibility") or "") == "PATIENT_VISIBLE"
        ]
    except Exception:  # noqa: BLE001 - a missing desk table must not hide history
        doctor_notes = []

    return templates.TemplateResponse(
        request,
        "medical_history.html",
        {
            "user": request.session,
            "history": history,
            "doctor_notes": doctor_notes
        }
    )