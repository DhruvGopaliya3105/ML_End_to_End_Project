"""Every ORM model in one place.

Importing this package registers ALL tables on ``Base.metadata``. That matters
twice:

* ``main.py`` calls ``Base.metadata.create_all(bind=engine)`` - on a fresh
  MySQL/SQLite file that has to see every table, or cross-table foreign keys
  (appointments.slot_id -> doctor_slots.id) fail to resolve.
* the seed scripts (``seed_sqlite_demo.py``, ``seed_pharmacy.py``) can just
  ``import src.models`` and get the whole schema.
"""

# ---- existing clinic models -------------------------------------------------
from src.models.user import User
from src.models.doctor import Doctor
from src.models.doctor_schedule import DoctorSchedule
from src.models.doctor_slot import DoctorSlot
from src.models.visit_type import VisitType
from src.models.appointment import Appointment
from src.models.medical_record import MedicalRecord
from src.models.treatment import Treatment
from src.models.follow_up import FollowUp
from src.models.prescription import Prescription
from src.models.prescription_medicine import PrescriptionMedicine
from src.models.treatment_review import TreatmentReview
from src.models.notification import Notification
from src.models.patient_document import PatientDocument
from src.models.screening import ScreeningHistory

# ---- pharmacy module --------------------------------------------------------
from src.models.disease import Disease
from src.models.medicine import Medicine
from src.models.medicine_disease import MedicineDisease
from src.models.pharmacy_cart import PharmacyCartItem
from src.models.pharmacy_order import PharmacyOrder
from src.models.pharmacy_order import PharmacyOrderItem
from src.models.nearby_pharmacy import NearbyPharmacy
from src.models.nearby_pharmacy import NearbyPharmacyStock
from src.models.pharmacy_audit_log import PharmacyAuditLog
from src.models.pharmacy_snapshot import PharmacySnapshot
from src.models.role_permission import RolePermission
from src.models.doctor_patient_note import DoctorPatientNote

__all__ = [
    # clinic
    "User",
    "Doctor",
    "DoctorSchedule",
    "DoctorSlot",
    "VisitType",
    "Appointment",
    "MedicalRecord",
    "Treatment",
    "FollowUp",
    "Prescription",
    "PrescriptionMedicine",
    "TreatmentReview",
    "Notification",
    "PatientDocument",
    "ScreeningHistory",
    # pharmacy
    "Disease",
    "Medicine",
    "MedicineDisease",
    "PharmacyCartItem",
    "PharmacyOrder",
    "PharmacyOrderItem",
    "NearbyPharmacy",
    "NearbyPharmacyStock",
    "PharmacyAuditLog",
    "PharmacySnapshot",
    "RolePermission",
    "DoctorPatientNote",
]
