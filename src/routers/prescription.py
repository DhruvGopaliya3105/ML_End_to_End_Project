from fastapi import (
    APIRouter,
    Depends,
    Request
)

from fastapi.responses import (
    HTMLResponse,
    JSONResponse
)

from sqlalchemy.orm import Session

from src.database.connection import get_db

from src.services.prescription_service import (
    create_prescription,
    get_patient_prescriptions,
    get_prescription
)

from src.schemas.prescription import (
    PrescriptionInput
)


# =========================================================
# ROUTER
# =========================================================

router = APIRouter(

    prefix="/prescription",

    tags=["Prescription"]

)


# =========================================================
# PRESCRIPTION PAGE
# =========================================================

@router.get(
    "",
    response_class=HTMLResponse
)
def prescription_page(
    request: Request
):

    templates = request.app.state.templates

    return templates.TemplateResponse(

        request,

        "prescription.html",

        {
            "user":
                request.session
        }

    )


# =========================================================
# CREATE NEW PRESCRIPTION
# =========================================================

@router.post(
    "/create"
)
def create_new_prescription(

    data: PrescriptionInput,

    request: Request,

    db: Session = Depends(get_db)

):

    # -----------------------------------------------------
    # CHECK LOGIN
    # -----------------------------------------------------

    user_id = request.session.get(
        "user_id"
    )


    if user_id is None:

        return JSONResponse(

            status_code=401,

            content={

                "success": False,

                "message":
                    "Please login first."

            }

        )


    # -----------------------------------------------------
    # CREATE PRESCRIPTION
    # -----------------------------------------------------

    prescription = create_prescription(

        db=db,

        patient_id=user_id,

        doctor_id=data.doctor_id,

        medical_record_id=data.medical_record_id,

        treatment_id=data.treatment_id,

        diagnosis=data.diagnosis,

        doctor_instructions=
            data.doctor_instructions,

        medicines=[

            medicine.model_dump()

            for medicine
            in data.medicines

        ]

    )


    # -----------------------------------------------------
    # RESPONSE
    # -----------------------------------------------------

    return {

        "success": True,

        "message":
            "Prescription created successfully.",

        "prescription_id":
            prescription.id

    }


# =========================================================
# PATIENT PRESCRIPTION HISTORY
# =========================================================

@router.get(
    "/history"
)
def prescription_history(

    request: Request,

    db: Session = Depends(get_db)

):

    # -----------------------------------------------------
    # CHECK LOGIN
    # -----------------------------------------------------

    user_id = request.session.get(
        "user_id"
    )


    if user_id is None:

        return JSONResponse(

            status_code=401,

            content={

                "success": False,

                "message":
                    "Please login first."

            }

        )


    # -----------------------------------------------------
    # GET HISTORY
    # -----------------------------------------------------

    history = get_patient_prescriptions(

        db=db,

        patient_id=user_id

    )


    # -----------------------------------------------------
    # FORMAT RESPONSE
    # -----------------------------------------------------

    prescriptions = []


    for item in history:

        prescription = item[
            "prescription"
        ]

        medicines = item[
            "medicines"
        ]


        prescriptions.append({

            "id":
                prescription.id,

            "diagnosis":
                prescription.diagnosis,

            "doctor_instructions":
                prescription.doctor_instructions,

            "created_at":
                str(
                    prescription.created_at
                ),

            "medicines": [

                {

                    "name":
                        medicine.medicine_name,

                    "dosage":
                        medicine.dosage,

                    "frequency":
                        medicine.frequency,

                    "duration":
                        medicine.duration,

                    "instructions":
                        medicine.instructions

                }

                for medicine
                in medicines

            ]

        })


    return {

        "success": True,

        "prescriptions":
            prescriptions

    }


# =========================================================
# SINGLE PRESCRIPTION
# =========================================================

@router.get(
    "/{prescription_id}"
)
def single_prescription(

    prescription_id: int,

    request: Request,

    db: Session = Depends(get_db)

):

    # -----------------------------------------------------
    # CHECK LOGIN
    # -----------------------------------------------------

    user_id = request.session.get(
        "user_id"
    )


    if user_id is None:

        return JSONResponse(

            status_code=401,

            content={

                "success": False,

                "message":
                    "Please login first."

            }

        )


    # -----------------------------------------------------
    # GET PRESCRIPTION
    # -----------------------------------------------------

    result = get_prescription(

        db=db,

        prescription_id=
            prescription_id,

        patient_id=
            user_id

    )


    # -----------------------------------------------------
    # NOT FOUND
    # -----------------------------------------------------

    if result is None:

        return JSONResponse(

            status_code=404,

            content={

                "success": False,

                "message":
                    "Prescription not found."

            }

        )


    prescription = result[
        "prescription"
    ]


    # -----------------------------------------------------
    # RESPONSE
    # -----------------------------------------------------

    return {

        "success": True,

        "prescription": {

            "id":
                prescription.id,

            "diagnosis":
                prescription.diagnosis,

            "doctor_instructions":
                prescription.doctor_instructions,

            "created_at":
                str(
                    prescription.created_at
                )

        },

        "medicines": [

            {

                "name":
                    medicine.medicine_name,

                "dosage":
                    medicine.dosage,

                "frequency":
                    medicine.frequency,

                "duration":
                    medicine.duration,

                "instructions":
                    medicine.instructions

            }

            for medicine
            in result[
                "medicines"
            ]

        ]

    }