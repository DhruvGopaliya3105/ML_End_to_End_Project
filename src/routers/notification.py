from fastapi import (
    APIRouter,
    Depends,
    Request
)

from fastapi.responses import RedirectResponse

from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session

from src.database.connection import get_db

from src.models.notification import Notification


router = APIRouter()

templates = Jinja2Templates(
    directory="templates"
)


# =====================================================
# NOTIFICATIONS PAGE
# =====================================================

@router.get("/notifications")
def notifications_page(

    request: Request,

    db: Session = Depends(get_db)

):

    user_id = request.session.get(
        "user_id"
    )


    # -----------------------------------------------
    # LOGIN CHECK
    # -----------------------------------------------

    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )


    # -----------------------------------------------
    # GET USER NOTIFICATIONS
    # -----------------------------------------------

    notifications = (

        db.query(Notification)

        .filter(
            Notification.user_id == user_id
        )

        .order_by(
            Notification.created_at.desc()
        )

        .all()

    )


    # -----------------------------------------------
    # SHOW PAGE
    # -----------------------------------------------

    return templates.TemplateResponse(

        request,

        "notifications.html",

        {
            "user": request.session,
            "notifications": notifications
        }

    )