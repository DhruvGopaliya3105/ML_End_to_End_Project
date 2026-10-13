import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import OperationalError
from starlette.middleware.sessions import SessionMiddleware


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# DATABASE
# ============================================================

from src.config import (
    BASE_DIR,
    STATIC_DIR,
    TEMPLATES_DIR,
)

from src.database.base import Base

# Registers every table (including the pharmacy ones) on Base.metadata before
# create_all() runs in lifespan.
import src.models  # noqa: F401,E402

from src.database.connection import (
    DATABASE_BACKEND,
    DATABASE_LABEL,
    MYSQL_FALLBACK_REASON,
    engine,
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=os.getenv(
        "LOG_LEVEL",
        "INFO"
    ).upper(),

    format=(
        "%(asctime)s | "
        "%(levelname)-8s | "
        "%(name)s | "
        "%(message)s"
    ),
)

logger = logging.getLogger(__name__)


# ============================================================
# DATABASE WARNING
# ============================================================

if DATABASE_BACKEND == "sqlite":

    logger.warning(
        "=" * 78
    )

    logger.warning(
        "ACTIVE DATABASE: %s",
        DATABASE_LABEL
    )

    if MYSQL_FALLBACK_REASON:

        logger.warning(
            "Reason for fallback: %s",
            MYSQL_FALLBACK_REASON
        )

    logger.warning(
        "Set USE_SQLITE=true to silence this, "
        "or fix your MySQL settings in .env."
    )

    logger.warning(
        "=" * 78
    )


# ============================================================
# APPLICATION LIFESPAN
# ============================================================

@asynccontextmanager
async def lifespan(
    app: FastAPI
) -> AsyncGenerator[None, None]:

    try:

        Base.metadata.create_all(
            bind=engine
        )

    except OperationalError:

        app.state.database_ready = False

        logger.exception(
            "Database is unavailable; the API will start, "
            "but database-backed routes will not work until "
            "the database is available."
        )

    else:

        app.state.database_ready = True

        # register the 10 MCP servers (idempotent - safe on every boot)
        try:
            from src.database.connection import SessionLocal
            from src.services.mcp_rbac import seed_mcp_registry

            _db = SessionLocal()
            try:
                seed_mcp_registry(_db)
            finally:
                _db.close()
        except Exception:
            logger.exception("MCP registry seed failed")

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
# AUDIT CONTEXT MIDDLEWARE (MCP platform)
# ============================================================
# Fresh correlation + request IDs per request, echoed back as
# X-Correlation-ID. The principal is attached only after server-side
# authentication - never trusted from the browser.

from src.services.audit_context import AuditContextMiddleware

app.add_middleware(AuditContextMiddleware)


# ============================================================
# STATIC FILES
# ============================================================

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

    directory=str(
        TEMPLATES_DIR
    )

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
# PHARMACY ROUTERS
# ============================================================
# Patient side: catalog, cart, checkout, prescription buying, nearby search.
# Admin side: catalog + stock, order queue, audit log, role matrix, snapshots.
# Imported before include_router below; their SQLAlchemy models are imported
# too, so Base.metadata.create_all() in lifespan creates the pharmacy tables.

from src.routers.pharmacy import (
    router as pharmacy_router
)

from src.routers.pharmacy_admin import (
    router as pharmacy_admin_router
)

from src.routers.doctor_desk import (
    router as doctor_desk_router
)

# ============================================================
# FOLLOW-UP ROUTER
# ============================================================

from src.routers.follow_up import (
    router as follow_up_router
)

# ============================================================
# MCP INTELLIGENCE PLATFORM ROUTER
# ============================================================

from src.routers.mcp_platform import (
    router as mcp_platform_router
)

# ============================================================
# MCP PLATFORM MODELS
# ============================================================
# Imported so Base.metadata.create_all() in lifespan also creates the MCP
# platform tables: registry, audit + security events, AI evidence, care
# gaps, clinical conflicts, scenario runs, change requests, workflow
# events, recovery attempts and AI benchmark runs.

from src.models.mcp_registry import McpServer  # noqa: F401
from src.models.audit_event import AuditEvent, SecurityEvent  # noqa: F401
from src.models.ai_evidence import AiRequest, AiEvidence, AiClaim  # noqa: F401
from src.models.care_gap import CareGap, CareReviewTask  # noqa: F401
from src.models.clinical_conflict import ClinicalConflict  # noqa: F401
from src.models.scenario_run import ScenarioRun  # noqa: F401
from src.models.change_request import ChangeRequest, ChangeApproval  # noqa: F401
from src.models.workflow_event import WorkflowEvent, RecoveryAttempt  # noqa: F401
from src.models.ai_benchmark import AiBenchmarkRun, AiBenchmarkResult  # noqa: F401


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
# PHARMACY ROUTERS REGISTER
# ============================================================

app.include_router(
    pharmacy_router
)

app.include_router(
    pharmacy_admin_router
)

# ============================================================
# DOCTOR DESK REGISTER
# ============================================================
# A doctor's own patient register: every enrolled patient, their whole
# file (visits, records, prescriptions, medicines, invoices, reviews) and
# the tools to write notes / records / prescriptions back into it.

app.include_router(
    doctor_desk_router
)

# ============================================================
# FOLLOW-UP ROUTER REGISTER
# ============================================================

app.include_router(
    follow_up_router
)

# ============================================================
# MCP INTELLIGENCE PLATFORM REGISTER
# ============================================================
# The /mcp intelligence console + the gateway APIs to the 10 MCP servers.

app.include_router(
    mcp_platform_router
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
def health(
    request: Request
):

    from src.services.groq_client import (
        ai_is_configured
    )

    database_ready = getattr(
        request.app.state,
        "database_ready",
        False
    )

    payload = {

        "status":
            "healthy",

        "service":
            "Sanjeevani Clinic",

        "database":
            "ready"
            if database_ready
            else "unavailable",

        "database_backend":
            DATABASE_BACKEND,

        "database_target":
            DATABASE_LABEL,

        "ai_features":
            "enabled"
            if ai_is_configured()
            else "disabled (GROQ_API_KEY not set)",

    }

    if (
        DATABASE_BACKEND == "sqlite"
        and MYSQL_FALLBACK_REASON
    ):

        payload[
            "database_fallback_reason"
        ] = MYSQL_FALLBACK_REASON

    return payload