from datetime import date

from fastapi import (
    APIRouter,
    Depends,
    Request,
    Form
)

from fastapi.responses import RedirectResponse

from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.pipeline.predict_pipeline import CustomData, PredictPipeline
from src.services.screening_service import create_screening

from src.models.doctor import Doctor


# =====================================================
# ROUTER
# =====================================================

router = APIRouter()


# =====================================================
# TEMPLATES
# =====================================================

templates = Jinja2Templates(
    directory="templates"
)


def _predict_with_model_or_fallback(
    age: int,
    gender: str,
    fever: float,
    cough: str,
    city: str
):
    try:
        result, probability = PredictPipeline().predict(
            CustomData(
                age=age,
                gender=gender,
                fever=fever,
                cough=cough,
                city=city
            ).get_data_as_dataframe()
        )
        return result, float(probability or 0.0)
    except Exception:
        risk_score = 0

        if age >= 60:
            risk_score += 30
        if fever >= 100.4:
            risk_score += 35
        if cough.lower() == "strong":
            risk_score += 25
        elif cough.lower() == "mild":
            risk_score += 10
        if city.lower() in {"delhi", "mumbai", "kolkata", "jaipur"}:
            risk_score += 15
        if gender.lower() == "male":
            risk_score += 5

        result = "Positive" if risk_score >= 60 else "Negative"
        probability = min(max(risk_score, 50.0), 96.0)
        return result, round(probability, 2)


@router.get("/predict")
def predict_page(request: Request):
    return templates.TemplateResponse(
        request,
        "predict.html",
        {
            "user": request.session,
            "result": None,
            "probability": None,
            "form_data": None,
            "error": None
        }
    )


@router.post("/predict")
def submit_predict(
    request: Request,
    age: int = Form(...),
    gender: str = Form(...),
    fever: float = Form(...),
    cough: str = Form(...),
    city: str = Form(...)
):
    form_data = {
        "age": age,
        "gender": gender,
        "fever": fever,
        "cough": cough,
        "city": city
    }

    try:
        result, probability = _predict_with_model_or_fallback(
            age=age,
            gender=gender,
            fever=fever,
            cough=cough,
            city=city,
        )
        return templates.TemplateResponse(
            request,
            "predict.html",
            {
                "user": request.session,
                "result": result,
                "probability": probability,
                "form_data": form_data,
                "error": None
            }
        )
    except Exception:
        return templates.TemplateResponse(
            request,
            "predict.html",
            {
                "user": request.session,
                "result": None,
                "probability": None,
                "form_data": form_data,
                "error": "Prediction could not be completed. Please try again."
            }
        )


# =====================================================
# GET /screening
# =====================================================

@router.get("/screening")
def screening_page(
    request: Request
):

    # -------------------------------------------------
    # Get logged-in user
    # -------------------------------------------------

    user_id = request.session.get(
        "user_id"
    )


    # -------------------------------------------------
    # Check login
    # -------------------------------------------------

    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )


    # -------------------------------------------------
    # Open screening page
    # -------------------------------------------------

    return templates.TemplateResponse(

        request,

        "screening.html",

        {
            "user": request.session,

            "result": None,

            "doctors": [],

            "error": None,

            # Current date
            "today": date.today()
        }

    )


# =====================================================
# POST /screening
# =====================================================

@router.post("/screening")
def submit_screening(

    request: Request,

    symptoms: str = Form(...),

    db: Session = Depends(get_db)

):

    # -------------------------------------------------
    # Get logged-in user
    # -------------------------------------------------

    user_id = request.session.get(
        "user_id"
    )


    # -------------------------------------------------
    # Check login
    # -------------------------------------------------

    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )


    # -------------------------------------------------
    # Clean symptoms
    # -------------------------------------------------

    symptoms = symptoms.strip()


    # -------------------------------------------------
    # Empty input check
    # -------------------------------------------------

    if not symptoms:

        return templates.TemplateResponse(

            request,

            "screening.html",

            {

                "user": request.session,

                "result": None,

                "doctors": [],

                "error":
                    "Please enter your symptoms.",

                "today":
                    date.today()

            }

        )


    # -------------------------------------------------
    # Convert to lowercase
    # -------------------------------------------------

    symptoms_lower = symptoms.lower()


    # =================================================
    # DEFAULT RESULT
    # =================================================

    care_category = (
        "General Medicine"
    )

    recommended_specialist = (
        "General Physician"
    )

    severity = "Mild"


    # =================================================
    # CARDIOLOGY
    # =================================================

    if (

        "chest pain"
        in symptoms_lower

        or

        "heart pain"
        in symptoms_lower

        or

        "chest pressure"
        in symptoms_lower

    ):

        care_category = (
            "Cardiology"
        )

        recommended_specialist = (
            "Cardiologist"
        )

        severity = "Urgent"


    # =================================================
    # DERMATOLOGY
    # =================================================

    elif (

        "skin"
        in symptoms_lower

        or

        "rash"
        in symptoms_lower

        or

        "itching"
        in symptoms_lower

        or

        "acne"
        in symptoms_lower

    ):

        care_category = (
            "Dermatology"
        )

        recommended_specialist = (
            "Dermatologist"
        )

        severity = "Moderate"


    # =================================================
    # NEUROLOGY
    # =================================================

    elif (

        "headache"
        in symptoms_lower

        or

        "migraine"
        in symptoms_lower

        or

        "dizziness"
        in symptoms_lower

        or

        "vertigo"
        in symptoms_lower

    ):

        care_category = (
            "Neurology"
        )

        recommended_specialist = (
            "Neurologist"
        )

        severity = "Moderate"


    # =================================================
    # ORTHOPEDICS
    # =================================================

    elif (

        "bone"
        in symptoms_lower

        or

        "joint pain"
        in symptoms_lower

        or

        "back pain"
        in symptoms_lower

        or

        "knee pain"
        in symptoms_lower

        or

        "shoulder pain"
        in symptoms_lower

    ):

        care_category = (
            "Orthopedics"
        )

        recommended_specialist = (
            "Orthopedic Specialist"
        )

        severity = "Moderate"


    # =================================================
    # OPHTHALMOLOGY
    # =================================================

    elif (

        "eye"
        in symptoms_lower

        or

        "vision"
        in symptoms_lower

        or

        "blurred vision"
        in symptoms_lower

        or

        "eye pain"
        in symptoms_lower

    ):

        care_category = (
            "Ophthalmology"
        )

        recommended_specialist = (
            "Ophthalmologist"
        )

        severity = "Moderate"


    # =================================================
    # DENTISTRY
    # =================================================

    elif (

        "tooth"
        in symptoms_lower

        or

        "teeth"
        in symptoms_lower

        or

        "toothache"
        in symptoms_lower

        or

        "gum"
        in symptoms_lower

    ):

        care_category = (
            "Dentistry"
        )

        recommended_specialist = (
            "Dentist"
        )

        severity = "Moderate"


    # =================================================
    # ENT
    # =================================================

    elif (

        "ear"
        in symptoms_lower

        or

        "throat"
        in symptoms_lower

        or

        "hearing"
        in symptoms_lower

        or

        "tonsil"
        in symptoms_lower

    ):

        care_category = (
            "ENT"
        )

        recommended_specialist = (
            "ENT Specialist"
        )

        severity = "Moderate"


    # =================================================
    # GENERAL MEDICINE
    # =================================================

    elif (

        "fever"
        in symptoms_lower

        or

        "cough"
        in symptoms_lower

        or

        "cold"
        in symptoms_lower

        or

        "flu"
        in symptoms_lower

        or

        "weakness"
        in symptoms_lower

    ):

        care_category = (
            "General Medicine"
        )

        recommended_specialist = (
            "General Physician"
        )

        severity = "Mild"


    # =================================================
    # AI RESPONSE
    # =================================================

    ai_response = (

        f"Based on the symptoms provided, "

        f"general care guidance suggests "

        f"considering {care_category}. "

        f"A {recommended_specialist} may be "

        f"appropriate for further evaluation."

    )


    # =================================================
    # SAVE SCREENING IN DATABASE
    # =================================================

    screening = create_screening(

        db=db,

        patient_id=user_id,

        symptoms=symptoms,

        ai_response=ai_response,

        care_category=care_category,

        recommended_specialist=
            recommended_specialist,

        severity=severity

    )


    # =================================================
    # FIND MATCHING DOCTORS
    # =================================================

    doctors = (

        db.query(Doctor)

        .filter(

            Doctor.specialization
            == care_category,

            Doctor.is_active == True

        )

        .order_by(

            Doctor.experience_years.desc()

        )

        .all()

    )


    # =================================================
    # RESULT
    # =================================================

    result = {

        "id":
            screening.id,

        "symptoms":
            symptoms,

        "ai_response":
            ai_response,

        "care_category":
            care_category,

        "recommended_specialist":
            recommended_specialist,

        "severity":
            severity

    }


    # =================================================
    # SHOW RESULT + DOCTORS
    # =================================================

    return templates.TemplateResponse(

        request,

        "screening.html",

        {

            "user":
                request.session,

            "result":
                result,

            "doctors":
                doctors,

            "error":
                None,

            # Current date for
            # appointment booking
            "today":
                date.today()

        }

    )