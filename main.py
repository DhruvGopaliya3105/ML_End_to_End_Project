import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import OperationalError
from starlette.middleware.sessions import SessionMiddleware


# ============================================================
# DATABASE
# ============================================================

from src.database.base import Base
from src.database.connection import engine


logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    try:
        Base.metadata.create_all(bind=engine)
    except OperationalError:
        app.state.database_ready = False
        logger.exception(
            "Database is unavailable; the API will start, but database-backed "
            "routes will not work until the database is available."
        )
    else:
        app.state.database_ready = True

    yield


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

    version="1.0.0",

    lifespan=lifespan

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

STATIC_DIR = BASE_DIR / "static"

if STATIC_DIR.is_dir():

    app.mount(

        "/static",

        StaticFiles(
            directory=STATIC_DIR
        ),

        name="static"

    )


# ============================================================
# TEMPLATES
# ============================================================

templates = Jinja2Templates(

    directory=BASE_DIR / "templates"

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
def health(request: Request):

    return {

        "status":
            "healthy",

        "service":
            "Sanjeevani Clinic",

        "database":
            "ready"
            if getattr(request.app.state, "database_ready", False)
            else "unavailable"

    }