"""Create a ready-to-use SQLite database for the app (optional helper).

Use this only if you are running WITHOUT MySQL (i.e. USE_SQLITE=true in .env,
or MySQL is unreachable). It builds ``sanjeevani_clinic.db`` next to this file
and fills it with the same baseline data as your MySQL setup:

* 20 doctors (8 specialisations)
* doctor_schedules for all 20 doctors, Monday-Sunday, 10:00-14:00, 5 min slots
* the 5 visit types
* two demo logins so you can sign in immediately

Run:

    python seed_sqlite_demo.py

WARNING: it deletes and recreates sanjeevani_clinic.db. Your MySQL database is
never touched.
"""

import sys
from datetime import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

DB_PATH = BASE_DIR / "sanjeevani_clinic.db"

# ---- demo logins created by this script -------------------------------
DEMO_PATIENT_EMAIL = "patient@demo.com"
DEMO_PATIENT_PASSWORD = "Demo@1234"
DEMO_ADMIN_EMAIL = "admin@demo.com"
DEMO_ADMIN_PASSWORD = "Admin@1234"
# -----------------------------------------------------------------------

DOCTORS = [
    ("Dr. Amit Sharma", "amit.sharma@sanjeevani.com", "9876543210", "Cardiology", "MBBS, MD Cardiology", 8, 800.00),
    ("Dr. Neha Verma", "neha.verma@sanjeevani.com", "9876500001", "Cardiology", "MBBS, MD Cardiology", 6, 700.00),
    ("Dr. Priya Mehta", "priya.mehta@sanjeevani.com", "9876500002", "Dermatology", "MBBS, MD Dermatology", 7, 600.00),
    ("Dr. Rahul Jain", "rahul.jain@sanjeevani.com", "9876500003", "Dermatology", "MBBS, MD Dermatology", 10, 800.00),
    ("Dr. Arjun Singh", "arjun.singh@sanjeevani.com", "9876500004", "Neurology", "MBBS, DM Neurology", 9, 1000.00),
    ("Dr. Kavita Rao", "kavita.rao@sanjeevani.com", "9876500005", "Neurology", "MBBS, MD, DM Neurology", 12, 1200.00),
    ("Dr. Raj Malhotra", "raj.malhotra@sanjeevani.com", "9876500006", "Orthopedics", "MBBS, MS Orthopedics", 11, 900.00),
    ("Dr. Anjali Gupta", "anjali.gupta@sanjeevani.com", "9876500007", "Orthopedics", "MBBS, MS Orthopedics", 6, 700.00),
    ("Dr. Rohan Sharma", "rohan.sharma@sanjeevani.com", "9876500008", "Pediatrics", "MBBS, MD Pediatrics", 8, 600.00),
    ("Dr. Sneha Kapoor", "sneha.kapoor@sanjeevani.com", "9876500009", "Pediatrics", "MBBS, MD Pediatrics", 5, 550.00),
    ("Dr. Vikram Joshi", "vikram.joshi@sanjeevani.com", "9876500010", "General Medicine", "MBBS, MD Medicine", 10, 500.00),
    ("Dr. Pooja Shah", "pooja.shah@sanjeevani.com", "9876500011", "General Medicine", "MBBS, MD Medicine", 7, 450.00),
    ("Dr. Nitin Agarwal", "nitin.agarwal@sanjeevani.com", "9876500012", "Ophthalmology", "MBBS, MS Ophthalmology", 9, 700.00),
    ("Dr. Riya Bansal", "riya.bansal@sanjeevani.com", "9876500013", "Ophthalmology", "MBBS, MS Ophthalmology", 6, 650.00),
    ("Dr. Karan Mehta", "karan.mehta@sanjeevani.com", "9876500014", "Dentistry", "BDS, MDS", 8, 500.00),
    ("Dr. Simran Kaur", "simran.kaur@sanjeevani.com", "9876500015", "Dentistry", "BDS, MDS", 5, 450.00),
    ("Dr. Manish Sethi", "manish.sethi@sanjeevani.com", "9876500016", "ENT", "MBBS, MS ENT", 10, 650.00),
    ("Dr. Aarti Mishra", "aarti.mishra@sanjeevani.com", "9876500017", "ENT", "MBBS, MS ENT", 7, 600.00),
    ("Dr. Shreya Kapoor", "shreya.kapoor@sanjeevani.com", "9876500018", "Gynecology", "MBBS, MS Gynecology", 9, 800.00),
    ("Dr. Meera Joshi", "meera.joshi@sanjeevani.com", "9876500019", "Gynecology", "MBBS, MD Gynecology", 12, 1000.00),
]

VISIT_TYPES = [
    ("General Consultation", 10, 15, 15),
    ("Follow-up", 10, 15, 10),
    ("Specialist Consultation", 15, 20, 20),
    ("Detailed Consultation", 20, 30, 30),
    ("Procedure / Assessment", 30, 60, 45),
]


def main() -> int:
    # Point the app at the SQLite file before importing the models.
    import os

    os.environ["USE_SQLITE"] = "true"
    os.environ.setdefault("GROQ_API_KEY", "seed-script")

    if DB_PATH.exists():
        print(f"Removing old database: {DB_PATH}")
        DB_PATH.unlink()

    from src.database.connection import SessionLocal, engine
    from src.database.base import Base

    # Import every model so Base.metadata knows all tables.
    import src.models  # noqa: F401
    import src.models.doctor_schedule  # noqa: F401
    import src.models.doctor_slot  # noqa: F401
    import src.models.notification  # noqa: F401
    import src.models.patient_document  # noqa: F401
    import src.models.screening  # noqa: F401
    import src.models.visit_type  # noqa: F401

    from src.models.doctor import Doctor
    from src.models.doctor_schedule import DoctorSchedule
    from src.models.user import User
    from src.models.visit_type import VisitType
    from src.security.password import hash_password

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        for (name, email, phone, spec, qual, exp, fee) in DOCTORS:
            db.add(Doctor(
                name=name, email=email, phone=phone, specialization=spec,
                qualification=qual, experience_years=exp,
                languages="Hindi, English", consultation_fee=fee,
                bio=f"{spec} specialist at Sanjeevani Clinic.",
                is_active=True,
            ))
        db.flush()

        for doctor in db.query(Doctor).all():
            for day in range(7):  # 0 = Monday ... 6 = Sunday
                db.add(DoctorSchedule(
                    doctor_id=doctor.id,
                    day_of_week=day,
                    start_time=time(10, 0),
                    end_time=time(14, 0),
                    slot_interval_minutes=5,
                    is_available=True,
                ))

        for (name, mn, mx, default) in VISIT_TYPES:
            db.add(VisitType(
                name=name,
                min_duration_minutes=mn,
                max_duration_minutes=mx,
                default_duration_minutes=default,
                is_active=True,
            ))

        db.add(User(
            name="Demo Patient", email=DEMO_PATIENT_EMAIL, phone="9000000001",
            password_hash=hash_password(DEMO_PATIENT_PASSWORD),
            age=30, gender="Male", role="PATIENT", is_active=True,
        ))
        db.add(User(
            name="Demo Admin", email=DEMO_ADMIN_EMAIL, phone="9000000002",
            password_hash=hash_password(DEMO_ADMIN_PASSWORD),
            age=35, gender="Female", role="ADMIN", is_active=True,
        ))

        db.commit()

        print()
        print(f"Database created : {DB_PATH}")
        print(f"  doctors        : {db.query(Doctor).count()}")
        print(f"  schedules      : {db.query(DoctorSchedule).count()}")
        print(f"  visit types    : {db.query(VisitType).count()}")
        print(f"  users          : {db.query(User).count()}")
        print()
        print("Log in with:")
        print(f"  patient : {DEMO_PATIENT_EMAIL} / {DEMO_PATIENT_PASSWORD}")
        print(f"  admin   : {DEMO_ADMIN_EMAIL} / {DEMO_ADMIN_PASSWORD}")
        print()

    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
