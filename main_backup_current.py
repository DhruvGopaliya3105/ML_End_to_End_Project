from fastapi import FastAPI

app = FastAPI(
    title="Sanjeevani Clinic",
    description="AI Assisted Healthcare Platform",
    version="1.0.0"
)

from src.routers.auth import router as auth_router
from src.routers.profile import router as profile_router
from src.routers.doctor import router as doctor_router
from src.routers.appointment import router as appointment_router
from src.routers.notification import router as notification_router
from src.routers.screening import router as screening_router
from src.routers.medical_history import router as medical_history_router
from src.routers.documents import router as documents_router

app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(doctor_router)
app.include_router(appointment_router)
app.include_router(notification_router)
app.include_router(screening_router)
app.include_router(medical_history_router)
app.include_router(documents_router)