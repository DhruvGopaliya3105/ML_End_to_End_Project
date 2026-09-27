from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

import os


# ============================================================
# DATABASE
# ============================================================

from src.database.base import Base
from src.database.connection import engine


# ============================================================
# IMPORT MODELS
# ============================================================
# Important:
# Models ko import karna zaroori hai taaki
# SQLAlchemy unki tables ko identify kar sake.

from src.models.prescription import Prescription
from src.models.prescription_medicine import PrescriptionMedicine


# ============================================================
# CREATE DATABASE TABLES
# ============================================================

Base.metadata.create_all(
    bind=engine
)


# ============================================================
# SESSION SECRET
# ============================================================

SESSION_SECRET = os.getenv(
    "SESSION_SECRET",
    "change_this_to_a_long_random_secret"
)


# ============================================================
# CREATE FASTAPI APP
# ============================================================

app = FastAPI(

    title="Sanjeevani Clinic",

    description="AI Assisted Healthcare Platform",

    version="1.0.0"

)


# ============================================================
# SESSION MIDDLEWARE
# ============================================================

app.add_middleware(

    SessionMiddleware,

    secret_key=SESSION_SECRET,

    max_age=60 * 60 * 24 * 7

)


# ============================================================
# STATIC FILES
# ============================================================

if os.path.isdir("static"):

    app.mount(

        "/static",

        StaticFiles(
            directory="static"
        ),

        name="static"

    )


# ============================================================
# TEMPLATES
# ============================================================

templates = Jinja2Templates(

    directory="templates"

)


# ============================================================
# MAKE TEMPLATES AVAILABLE THROUGH APP STATE
# ============================================================

app.state.templates = templates


# ============================================================
# IMPORT ROUTERS
# ============================================================

from src.routers.auth import (
    router as auth_router
)

from src.routers.profile import (
    router as profile_router
)

from src.routers.doctor import (
    router as doctor_router
)

from src.routers.appointment import (
    router as appointment_router
)

from src.routers.notification import (
    router as notification_router
)

from src.routers.screening import (
    router as screening_router
)

from src.routers.medical_history import (
    router as medical_history_router
)

from src.routers.documents import (
    router as documents_router
)

from src.routers.chatbot import (
    router as chatbot_router
)

from src.routers.injury import (
    router as injury_router
)

from src.routers.prescription import (
    router as prescription_router
)

from src.routers.treatment_review import (
    router as treatment_review_router
)


# ============================================================
# REGISTER ROUTERS
# ============================================================

app.include_router(
    auth_router
)


app.include_router(
    profile_router
)


app.include_router(
    doctor_router
)


app.include_router(
    appointment_router
)


app.include_router(
    notification_router
)


app.include_router(
    screening_router
)


app.include_router(
    medical_history_router
)


app.include_router(
    documents_router
)


app.include_router(
    chatbot_router
)


app.include_router(
    injury_router
)


app.include_router(
    prescription_router
)


app.include_router(
    treatment_review_router
)


# ============================================================
# HOME PAGE
# ============================================================

@app.get(
    "/",
    response_class=HTMLResponse
)
def home(
    request: Request
):

    return templates.TemplateResponse(

        request,

        "index.html",

        {

            "user":
                request.session

        }

    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health():

    return {

        "status":
            "healthy",

        "service":
            "Sanjeevani Clinic"

    }