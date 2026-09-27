from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.models.user import User


router = APIRouter()

templates = Jinja2Templates(directory="templates")


# ==========================================
# VIEW PROFILE
# ==========================================

@router.get("/profile")
def profile_page(
    request: Request,
    db: Session = Depends(get_db)
):
    # Session se logged-in user ki ID nikalo
    user_id = request.session.get("user_id")

    # Agar login nahi hai
    if user_id is None:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    # MySQL se current user nikalo
    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    # Agar user database mein nahi mila
    if user is None:
        request.session.clear()

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    # Profile VIEW page open karo
    return templates.TemplateResponse(
        request,
        "profile.html",
        {
            "user": user
        }
    )


# ==========================================
# EDIT PROFILE PAGE
# ==========================================

@router.get("/profile/edit")
def edit_profile_page(
    request: Request,
    db: Session = Depends(get_db)
):
    # Logged-in user ki ID
    user_id = request.session.get("user_id")

    # Login check
    if user_id is None:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    # User database se find karo
    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    # User nahi mila
    if user is None:
        request.session.clear()

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    # Edit form open karo
    return templates.TemplateResponse(
        request,
        "edit_profile.html",
        {
            "user": user
        }
    )


# ==========================================
# UPDATE PROFILE
# ==========================================

@router.post("/profile/update")
def update_profile(
    request: Request,

    name: str = Form(...),

    phone: str = Form(None),

    age: int = Form(None),

    gender: str = Form(None),

    db: Session = Depends(get_db)
):

    # Session se user ID
    user_id = request.session.get("user_id")

    # Login check
    if user_id is None:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    # Current user database se find karo
    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    # User nahi mila
    if user is None:
        request.session.clear()

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    # ======================================
    # UPDATE USER INFORMATION
    # ======================================

    user.name = name

    user.phone = phone

    user.age = age

    user.gender = gender

    # MySQL mein save
    db.commit()

    # Latest data reload
    db.refresh(user)

    # Session mein updated name
    request.session["user_name"] = user.name

    # Profile VIEW par redirect
    return RedirectResponse(
        url="/profile",
        status_code=303
    )