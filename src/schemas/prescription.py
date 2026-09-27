from typing import Optional

from pydantic import BaseModel, Field


# =========================================================
# MEDICINE INPUT
# =========================================================

class MedicineInput(BaseModel):

    medicine_name: str

    dosage: Optional[str] = None

    frequency: Optional[str] = None

    duration: Optional[str] = None

    instructions: Optional[str] = None


# =========================================================
# PRESCRIPTION INPUT
# =========================================================

class PrescriptionInput(BaseModel):

    doctor_id: Optional[int] = None

    medical_record_id: Optional[int] = None

    treatment_id: Optional[int] = None

    diagnosis: Optional[str] = None

    doctor_instructions: Optional[str] = None

    medicines: list[MedicineInput] = Field(
        default_factory=list
    )