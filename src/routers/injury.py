from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Depends,
    Request
)

from fastapi.responses import (
    HTMLResponse,
    JSONResponse
)

from sqlalchemy.orm import Session

from src.database.connection import get_db

from src.services.injury_service import (
    analyze_injury_image,
    normalize_specialist
)

from src.models.doctor import Doctor


router = APIRouter(
    prefix="/injury",
    tags=["Injury"]
)


# =========================================================
# INJURY PAGE
# =========================================================

@router.get(
    "",
    response_class=HTMLResponse
)
async def injury_page(request: Request):

    templates = request.app.state.templates

    return templates.TemplateResponse(
        "injury.html",
        {
            "request": request
        }
    )


# =========================================================
# ANALYZE INJURY IMAGE
# =========================================================

@router.post("/analyze")
async def analyze_injury(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):

    # =====================================================
    # 1. CHECK FILE TYPE
    # =====================================================

    allowed_types = [
        "image/jpeg",
        "image/png",
        "image/webp"
    ]

    if file.content_type not in allowed_types:

        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": (
                    "Please upload JPG, PNG or WEBP image."
                )
            }
        )

    # =====================================================
    # 2. READ IMAGE
    # =====================================================

    file_bytes = await file.read()

    # =====================================================
    # 3. CHECK IMAGE SIZE
    # =====================================================

    if len(file_bytes) > 10 * 1024 * 1024:

        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": (
                    "Image size must be less than 10 MB."
                )
            }
        )

    # =====================================================
    # 4. AI IMAGE ANALYSIS
    # =====================================================

    result = analyze_injury_image(
        file_bytes=file_bytes,
        filename=file.filename
    )

    if not result["success"]:

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": (
                    "Unable to analyze the injury image."
                ),
                "error": result.get("error")
            }
        )

    data = result["data"]

    # =====================================================
    # 5. GET AI RESULT
    # =====================================================

    injury_type = data.get(
        "injury_type",
        "unclear"
    )

    body_part = data.get(
        "body_part",
        "unclear"
    )

    severity = str(
        data.get(
            "severity",
            "unclear"
        )
    ).lower().strip()

    specialist = data.get(
        "specialist",
        "Unknown"
    )

    recommendation = data.get(
        "recommendation",
        ""
    )

    emergency = data.get(
        "emergency",
        False
    )

    # =====================================================
    # 6. NORMALIZE EMERGENCY VALUE
    # =====================================================

    if isinstance(emergency, str):

        emergency = emergency.lower().strip() in [
            "true",
            "yes",
            "1"
        ]

    else:

        emergency = bool(emergency)

    # =====================================================
    # 7. NORMALIZE SPECIALIST
    # =====================================================

    specialist = normalize_specialist(
        specialist
    )

    # =====================================================
    # 8. EMERGENCY LOGIC
    #
    # IMPORTANT:
    # Only TRUE emergency OR severe injury
    # goes to emergency.
    # Moderate injury will NOT automatically
    # become emergency.
    # =====================================================

    if emergency is True or severity == "severe":

        return {
            "success": True,

            "route": "EMERGENCY",

            "analysis": {

                "injury_type": injury_type,

                "body_part": body_part,

                "severity": severity,

                "specialist": specialist,

                "recommendation": recommendation
            },

            "doctors": [],

            "message": (
                "The image may indicate a serious condition. "
                "Please seek urgent medical attention."
            )
        }

    # =====================================================
    # 9. MINOR INJURY
    #
    # Minor -> General OPD
    # =====================================================

    if severity == "minor":

        route = "OPD"

    # =====================================================
    # 10. MODERATE INJURY
    #
    # Moderate -> Specialist
    # =====================================================

    elif severity == "moderate":

        route = "SPECIALIST"

    # =====================================================
    # 11. UNCLEAR SEVERITY
    #
    # If AI is not sure, use specialist if available.
    # =====================================================

    else:

        route = "SPECIALIST"

    # =====================================================
    # 12. FIND SPECIALIST DOCTORS
    # =====================================================

    doctors = []

    if route == "SPECIALIST":

        doctors = (
            db.query(Doctor)
            .filter(
                Doctor.is_active == True,
                Doctor.specialization.ilike(
                    f"%{specialist}%"
                )
            )
            .all()
        )

    # =====================================================
    # 13. IF EXACT SPECIALIST NOT AVAILABLE
    #
    # Do NOT show every doctor.
    #
    # First try a few useful specialist mappings.
    # =====================================================

    if route == "SPECIALIST" and not doctors:

        specialist_mapping = {

            "Orthopedic": [
                "Orthopedic",
                "Orthopaedic",
                "Orthopedics",
                "Orthopaedics"
            ],

            "Dermatologist": [
                "Dermatologist",
                "Dermatology"
            ],

            "General Physician": [
                "General Physician",
                "General Medicine",
                "Physician"
            ],

            "Cardiologist": [
                "Cardiologist",
                "Cardiology"
            ],

            "Neurologist": [
                "Neurologist",
                "Neurology"
            ]
        }

        search_terms = specialist_mapping.get(
            specialist,
            [specialist]
        )

        for term in search_terms:

            doctors = (
                db.query(Doctor)
                .filter(
                    Doctor.is_active == True,
                    Doctor.specialization.ilike(
                        f"%{term}%"
                    )
                )
                .all()
            )

            if doctors:
                break

    # =====================================================
    # 14. IF SPECIALIST IS NOT AVAILABLE
    #
    # Then General Physician can be shown.
    # =====================================================

    if route == "SPECIALIST" and not doctors:

        route = "OPD"

        doctors = (
            db.query(Doctor)
            .filter(
                Doctor.is_active == True,
                Doctor.specialization.ilike(
                    "%General Physician%"
                )
            )
            .all()
        )

    # =====================================================
    # 15. BUILD DOCTOR RESPONSE
    # =====================================================

    doctor_list = []

    for doctor in doctors:

        doctor_name = (
            getattr(
                doctor,
                "name",
                None
            )
            or getattr(
                doctor,
                "full_name",
                None
            )
            or "Doctor"
        )

        doctor_specialization = (
            getattr(
                doctor,
                "specialization",
                None
            )
            or "General"
        )

        doctor_list.append({

            "id": doctor.id,

            "name": doctor_name,

            "specialization": doctor_specialization
        })

    # =====================================================
    # 16. FINAL RESPONSE
    # =====================================================

    return {

        "success": True,

        "route": route,

        "analysis": {

            "injury_type": injury_type,

            "body_part": body_part,

            "severity": severity,

            "specialist": specialist,

            "recommendation": recommendation
        },

        "doctors": doctor_list,

        "message": (
            "Your injury has been analyzed. "
            "The recommended specialist is "
            f"{specialist}. "
            "Only available matching doctors "
            "are shown for appointment booking."
        )
    }