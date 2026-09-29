from fastapi import (
    APIRouter,
    Depends,
    Form,
    Request
)

from fastapi.responses import RedirectResponse

from fastapi.templating import (
    Jinja2Templates
)

from sqlalchemy.orm import Session

from src.database.connection import get_db

from src.schemas.user import UserCreate

from src.services.user_service import create_user

from src.models.user import User

from src.security.password import verify_password


router = APIRouter()

templates = Jinja2Templates(
    directory="templates"
)


# ============================================================
# SIGNUP PAGE
# ============================================================

@router.get("/signup")
def signup_page(request: Request):

    return templates.TemplateResponse(
        request,
        "signup.html"
    )


# ============================================================
# SIGNUP
# ============================================================

@router.post("/signup")
def signup(

    request: Request,

    name: str = Form(...),

    email: str = Form(...),

    phone: str = Form(None),

    password: str = Form(...),

    age: int | None = Form(None),

    gender: str | None = Form(None),

    db: Session = Depends(get_db)

):

    try:

        user_data = UserCreate(
            name=name,
            email=email,
            phone=phone,
            password=password,
            age=age,
            gender=gender
        )

        user = create_user(
            db,
            user_data
        )

        if user is None:

            return templates.TemplateResponse(
                request,
                "signup.html",
                {
                    "error":
                    "Email already registered!"
                },
                status_code=400
            )

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    except Exception as e:

        return templates.TemplateResponse(
            request,
            "signup.html",
            {
                "error": str(e)
            },
            status_code=400
        )


# ============================================================
# LOGIN PAGE
# ============================================================

@router.get("/login")
def login_page(request: Request):

    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": None
        }
    )


# ============================================================
# LOGIN
# ============================================================

@router.post("/login")
def login(

    request: Request,

    email: str = Form(...),

    password: str = Form(...),

    db: Session = Depends(get_db)

):

    # Find user
    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    # User doesn't exist
    if user is None:

        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error":
                "Invalid email or password."
            },
            status_code=401
        )

    # Verify password
    password_correct = verify_password(
        password,
        user.password_hash
    )

    if not password_correct:

        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error":
                "Invalid email or password."
            },
            status_code=401
        )

    # Check active account
    if not user.is_active:

        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error":
                "Your account is inactive."
            },
            status_code=403
        )

    # ========================================================
    # CREATE SESSION
    # ========================================================

    request.session["user_id"] = user.id

    request.session["user_name"] = user.name

    request.session["user_email"] = user.email

    request.session["user_role"] = user.role

    # ========================================================
    # REDIRECT
    # ========================================================

    return RedirectResponse(
        url="/dashboard",
        status_code=303
    )


# ============================================================
# DASHBOARD
# ============================================================

@router.get("/dashboard")
def dashboard(

    request: Request,

    db: Session = Depends(get_db)

):

    user_id = request.session.get(
        "user_id"
    )

    if user_id is not None:

        user = (
            db.query(User)
            .filter(User.id == user_id)
            .first()
        )

        if user is None:

            request.session.clear()

            user = {
                "user_name": "Guest",
                "user_email": "",
                "user_role": "PATIENT"
            }

        else:
            user = {
                "user_name": user.name,
                "user_email": user.email,
                "user_role": user.role
            }

    else:
        user = {
            "user_name": "Guest",
            "user_email": "",
            "user_role": "PATIENT"
        }

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user
        }
    )


# ============================================================
# LOGOUT
# ============================================================

@router.get("/logout")
def logout(request: Request):

    request.session.clear()

    return RedirectResponse(
        url="/login",
        status_code=303
    )