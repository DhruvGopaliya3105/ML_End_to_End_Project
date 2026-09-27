# ============================================================
# CHATBOT ROUTER
# Sanjeevani Clinic
# ============================================================

from datetime import date, datetime, timedelta, time
import os
import re
import random

from fastapi import (
    APIRouter,
    Request,
    Depends
)

from fastapi.responses import JSONResponse

from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session

from dotenv import load_dotenv


# ============================================================
# LOAD ENV
# ============================================================

load_dotenv()


# ============================================================
# GROQ
# ============================================================

try:

    from groq import Groq

    GROQ_AVAILABLE = True

except ImportError:

    GROQ_AVAILABLE = False


# ============================================================
# DATABASE
# ============================================================

from src.database.connection import get_db


# ============================================================
# MODELS
# ============================================================

from src.models.doctor import Doctor

from src.models.visit_type import VisitType

from src.models.appointment import Appointment


# ============================================================
# SERVICES
# ============================================================

from src.services.availability_service import (
    get_available_times
)

from src.services.appointment_service import (
    book_dynamic_appointment,
    get_patient_appointments,
    confirm_appointment
)


# ============================================================
# ROUTER
# ============================================================

router = APIRouter()


# ============================================================
# TEMPLATE
# ============================================================

templates = Jinja2Templates(
    directory="templates"
)


# ============================================================
# GROQ CLIENT
# ============================================================

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY"
)

# IMPORTANT:
# Put the SAME model name in .env
# that worked in your test_groq.py

GROQ_MODEL = os.getenv(
    "GROQ_MODEL"
)


groq_client = None


if GROQ_AVAILABLE and GROQ_API_KEY:

    try:

        groq_client = Groq(
            api_key=GROQ_API_KEY
        )

    except Exception:

        groq_client = None


# ============================================================
# CHATBOT PAGE
# ============================================================

@router.get("/chatbot")
def chatbot_page(
    request: Request
):

    return templates.TemplateResponse(

        request,

        "chatbot.html",

        {
            "user": request.session
        }

    )


# ============================================================
# HELPER
# FORMAT TIME
# ============================================================

def format_time(value):

    if value is None:

        return ""

    return value.strftime(
        "%I:%M %p"
    )


# ============================================================
# HELPER
# DOCTOR NAME
# ============================================================

def get_doctor_name(appointment):

    if (
        appointment
        and appointment.doctor
    ):

        return appointment.doctor.name

    return "Doctor"


# ============================================================
# HELPER
# FIND SPECIALIZATION
# ============================================================

def detect_specialization(
    user_message: str
):

    message = user_message.lower()

    # --------------------------------------------------------
    # NEUROLOGY
    # --------------------------------------------------------

    if any(
        word in message
        for word in [
            "neurologist",
            "neurology",
            "brain doctor",
            "nerve doctor",
            "nerves doctor",
            "migraine doctor"
        ]
    ):

        return "neurolog"


    # --------------------------------------------------------
    # CARDIOLOGY
    # --------------------------------------------------------

    if any(
        word in message
        for word in [
            "cardiologist",
            "cardiology",
            "heart doctor",
            "heart specialist"
        ]
    ):

        return "cardiolog"


    # --------------------------------------------------------
    # DERMATOLOGY
    # --------------------------------------------------------

    if any(
        word in message
        for word in [
            "dermatologist",
            "dermatology",
            "skin doctor",
            "skin specialist"
        ]
    ):

        return "dermatolog"


    # --------------------------------------------------------
    # DENTIST
    # --------------------------------------------------------

    if any(
        word in message
        for word in [
            "dentist",
            "dental",
            "tooth doctor",
            "teeth doctor"
        ]
    ):

        return "dent"


    # --------------------------------------------------------
    # ORTHOPEDIC
    # --------------------------------------------------------

    if any(
        word in message
        for word in [
            "orthopedic",
            "orthopaedic",
            "bone doctor",
            "bone specialist",
            "joint doctor"
        ]
    ):

        return "orthop"


    # --------------------------------------------------------
    # GYNECOLOGY
    # --------------------------------------------------------

    if any(
        word in message
        for word in [
            "gynecologist",
            "gynaecologist",
            "gynecology",
            "gynaecology",
            "women doctor"
        ]
    ):

        return "gynecolog"


    # --------------------------------------------------------
    # ENT
    # --------------------------------------------------------

    if any(
        word in message
        for word in [
            "ent",
            "ear doctor",
            "nose doctor",
            "throat doctor"
        ]
    ):

        return "ent"


    # --------------------------------------------------------
    # PEDIATRICIAN
    # --------------------------------------------------------

    if any(
        word in message
        for word in [
            "pediatrician",
            "paediatrician",
            "child doctor",
            "children doctor",
            "kids doctor"
        ]
    ):

        return "pediatric"


    # --------------------------------------------------------
    # PSYCHIATRIST
    # --------------------------------------------------------

    if any(
        word in message
        for word in [
            "psychiatrist",
            "psychiatry",
            "mental health doctor"
        ]
    ):

        return "psychiatr"


    # --------------------------------------------------------
    # GENERAL PHYSICIAN
    # --------------------------------------------------------

    if any(
        word in message
        for word in [
            "general physician",
            "general doctor",
            "physician",
            "family doctor"
        ]
    ):

        return "general"


    return None


# ============================================================
# HELPER
# FIND DOCTOR
# ============================================================

def find_doctors(
    db: Session,
    specialization_keyword: str
):

    doctors = (

        db.query(Doctor)

        .filter(
            Doctor.is_active == True,

            Doctor.specialization.ilike(
                f"%{specialization_keyword}%"
            )
        )

        .all()

    )

    return doctors


# ============================================================
# HELPER
# FIND NEXT AVAILABLE SLOT
# ============================================================

def find_next_available_slot(
    db: Session,
    doctor,
    duration_minutes: int
):

    today = date.today()

    # --------------------------------------------------------
    # Search today + next 7 days
    # --------------------------------------------------------

    for day_number in range(8):

        selected_date = (
            today
            + timedelta(
                days=day_number
            )
        )

        try:

            slots = get_available_times(

                db=db,

                doctor_id=doctor.id,

                selected_date=selected_date,

                duration_minutes=duration_minutes

            )

        except Exception:

            # If availability service/database
            # has an error, continue safely.

            slots = []


        if slots:

            return (
                selected_date,
                slots
            )


    return (
        None,
        []
    )


# ============================================================
# HELPER
# SAVE PENDING BOOKING
# ============================================================

def save_pending_booking(
    request: Request,
    doctor,
    visit_type,
    selected_date
):

    request.session[
        "pending_booking"
    ] = {

        "doctor_id":
            doctor.id,

        "doctor_name":
            doctor.name,

        "visit_type_id":
            visit_type.id,

        "visit_type_name":
            visit_type.name,

        "appointment_date":
            str(selected_date)

    }


# ============================================================
# HELPER
# GET PENDING BOOKING
# ============================================================

def get_pending_booking(
    request: Request
):

    return request.session.get(
        "pending_booking"
    )


# ============================================================
# HELPER
# CLEAR PENDING BOOKING
# ============================================================

def clear_pending_booking(
    request: Request
):

    request.session.pop(
        "pending_booking",
        None
    )


# ============================================================
# HELPER
# PARSE TIME FROM MESSAGE
# ============================================================

def parse_time_from_message(
    user_message: str
):

    # --------------------------------------------------------
    # 10:30 AM
    # 10 AM
    # 10:30
    # --------------------------------------------------------

    match = re.search(

        r"\b"
        r"(\d{1,2})"
        r"(?:[:.](\d{2}))?"
        r"\s*"
        r"(am|pm)?"
        r"\b",

        user_message.lower()

    )


    if not match:

        return None


    hour = int(
        match.group(1)
    )

    minute = int(
        match.group(2)
        or 0
    )

    am_pm = match.group(3)


    # --------------------------------------------------------
    # AM / PM
    # --------------------------------------------------------

    if am_pm:

        if (
            am_pm == "pm"
            and hour != 12
        ):

            hour += 12


        if (
            am_pm == "am"
            and hour == 12
        ):

            hour = 0


    # --------------------------------------------------------
    # VALIDATE
    # --------------------------------------------------------

    if hour > 23:

        return None


    if minute > 59:

        return None


    return time(
        hour,
        minute
    )


# ============================================================
# DYNAMIC DOCTOR + SLOTS
# ============================================================

def handle_doctor_search(
    request: Request,
    db: Session,
    user_message: str
):

    specialization_keyword = (
        detect_specialization(
            user_message
        )
    )


    if not specialization_keyword:

        return None


    # ========================================================
    # FIND DOCTORS FROM DB
    # ========================================================

    doctors = find_doctors(

        db=db,

        specialization_keyword=
            specialization_keyword

    )


    # ========================================================
    # NO DOCTOR
    # ========================================================

    if not doctors:

        return {

            "success": True,

            "reply":
                "Sorry, I could not find an "
                "active doctor for this specialization "
                "in our clinic database."

        }


    # ========================================================
    # RANDOM DOCTOR
    # ========================================================

    doctor = random.choice(
        doctors
    )


    # ========================================================
    # VISIT TYPE
    # ========================================================

    visit_type = (

        db.query(VisitType)

        .filter(
            VisitType.is_active == True
        )

        .order_by(
            VisitType.id
        )

        .first()

    )


    if visit_type is None:

        return {

            "success": False,

            "reply":
                "No active visit type is "
                "available right now."

        }


    # ========================================================
    # FIND AVAILABLE DATE + SLOTS
    # ========================================================

    selected_date, slots = (
        find_next_available_slot(

            db=db,

            doctor=doctor,

            duration_minutes=
                visit_type.default_duration_minutes

        )
    )


    # ========================================================
    # NO SLOT
    # ========================================================

    if not slots:

        return {

            "success": True,

            "reply":
                f"I found Dr. {doctor.name}, "
                f"but there are no available "
                f"slots for the next 7 days."

        }


    # ========================================================
    # SAVE BOOKING STATE
    # ========================================================

    save_pending_booking(

        request=request,

        doctor=doctor,

        visit_type=visit_type,

        selected_date=selected_date

    )


    # ========================================================
    # RESPONSE
    # ========================================================

    reply = (

        f"Yes! I found Dr. {doctor.name}. 👨‍⚕️\n\n"

        f"Specialization: "
        f"{doctor.specialization}\n"

        f"Date: {selected_date}\n\n"

        "Available slots:\n\n"

    )


    # --------------------------------------------------------
    # SHOW MAX 10 SLOTS
    # --------------------------------------------------------

    for index, slot in enumerate(
        slots[:10],
        start=1
    ):

        reply += (

            f"{index}. "
            f"{format_time(slot['start_time'])}"
            f" - "
            f"{format_time(slot['end_time'])}\n"

        )


    reply += (

        "\nTell me which time you want to book.\n"

        "Example:\n"

        "\"Book 10:00 AM\""

    )


    return {

        "success": True,

        "reply": reply,

        "action":
            "select_appointment_slot",

        "doctor_id":
            doctor.id,

        "doctor_name":
            doctor.name,

        "appointment_date":
            str(selected_date)

    }


# ============================================================
# BOOK SELECTED SLOT
# ============================================================

def handle_slot_booking(
    request: Request,
    db: Session,
    user_id: int,
    user_message: str
):

    pending_booking = (
        get_pending_booking(
            request
        )
    )


    # --------------------------------------------------------
    # No pending booking
    # --------------------------------------------------------

    if not pending_booking:

        return None


    # --------------------------------------------------------
    # Check booking words
    # --------------------------------------------------------

    booking_words = [

        "book",

        "schedule",

        "reserve",

        "book me",

        "i want this",

        "select this",

        "take this slot"

    ]


    is_booking_request = any(

        word in user_message

        for word in booking_words

    )


    if not is_booking_request:

        return None


    # --------------------------------------------------------
    # Parse time
    # --------------------------------------------------------

    requested_time = (
        parse_time_from_message(
            user_message
        )
    )


    if requested_time is None:

        return {

            "success": True,

            "reply":
                "Please tell me the time "
                "you want to book.\n\n"
                "Example: Book 10:00 AM"

        }


    # ========================================================
    # GET PENDING DATA
    # ========================================================

    doctor_id = (
        pending_booking[
            "doctor_id"
        ]
    )

    visit_type_id = (
        pending_booking[
            "visit_type_id"
        ]
    )

    appointment_date = datetime.strptime(

        pending_booking[
            "appointment_date"
        ],

        "%Y-%m-%d"

    ).date()


    # ========================================================
    # VISIT TYPE
    # ========================================================

    visit_type = (

        db.query(VisitType)

        .filter(
            VisitType.id ==
                visit_type_id,

            VisitType.is_active ==
                True
        )

        .first()

    )


    if visit_type is None:

        return {

            "success": False,

            "reply":
                "The selected visit type "
                "is no longer available."

        }


    # ========================================================
    # CHECK ACTUAL SLOTS AGAIN
    # ========================================================

    try:

        slots = get_available_times(

            db=db,

            doctor_id=doctor_id,

            selected_date=
                appointment_date,

            duration_minutes=
                visit_type.default_duration_minutes

        )

    except Exception:

        return {

            "success": False,

            "reply":
                "I could not check the latest "
                "availability. Please try again."

        }


    # ========================================================
    # FIND REQUESTED SLOT
    # ========================================================

    selected_slot = None


    for slot in slots:

        if (
            slot["start_time"]
            == requested_time
        ):

            selected_slot = slot

            break


    # ========================================================
    # SLOT NOT AVAILABLE
    # ========================================================

    if selected_slot is None:

        reply = (

            "Sorry, that time is not available. ❌\n\n"

            "Please choose from these available slots:\n\n"

        )


        for slot in slots[:10]:

            reply += (

                f"• "
                f"{format_time(slot['start_time'])}"
                f" - "
                f"{format_time(slot['end_time'])}\n"

            )


        return {

            "success": True,

            "reply": reply

        }


    # ========================================================
    # BOOK
    # ========================================================

    appointment, error = (

        book_dynamic_appointment(

            db=db,

            patient_id=user_id,

            doctor_id=doctor_id,

            appointment_date=
                appointment_date,

            start_time=
                selected_slot[
                    "start_time"
                ],

            end_time=
                selected_slot[
                    "end_time"
                ],

            visit_type_id=
                visit_type_id,

            reason=
                "Booked through clinic chatbot",

            payment_method=
                "CASH",

            payment_amount=0

        )

    )


    # ========================================================
    # BOOKING ERROR
    # ========================================================

    if error:

        return {

            "success": False,

            "reply":
                "Sorry, I could not book "
                "that appointment.\n\n"
                f"Reason: {error}"

        }


    # ========================================================
    # CLEAR SESSION
    # ========================================================

    clear_pending_booking(
        request
    )


    # ========================================================
    # DOCTOR NAME
    # ========================================================

    doctor_name = (
        appointment.doctor.name
        if appointment.doctor
        else pending_booking[
            "doctor_name"
        ]
    )


    # ========================================================
    # SUCCESS
    # ========================================================

    return {

        "success": True,

        "reply":

            "Your appointment has been "
            "booked successfully! ✅\n\n"

            f"Appointment ID: "
            f"#{appointment.id}\n"

            f"Doctor: Dr. "
            f"{doctor_name}\n"

            f"Date: "
            f"{appointment.appointment_date}\n"

            f"Time: "
            f"{format_time(appointment.start_time)}"
            f" - "
            f"{format_time(appointment.end_time)}\n"

            f"Status: "
            f"{appointment.status}\n\n"

            "You can now type:\n"
            "\"Confirm my appointment\""

    }


# ============================================================
# CONFIRM APPOINTMENT
# ============================================================

def handle_confirmation(
    db: Session,
    user_id: int
):

    appointments = (
        get_patient_appointments(

            db,

            user_id

        )
    )


    # ========================================================
    # FIND BOOKED APPOINTMENT
    # ========================================================

    booked_appointment = None


    for appointment in appointments:

        if appointment.status == "BOOKED":

            booked_appointment = (
                appointment
            )

            break


    # ========================================================
    # ALREADY CONFIRMED
    # ========================================================

    if booked_appointment is None:

        for appointment in appointments:

            if (
                appointment.status
                == "CONFIRMED"
            ):

                doctor_name = (
                    get_doctor_name(
                        appointment
                    )
                )


                return {

                    "success": True,

                    "reply":

                        "Your appointment is "
                        "already confirmed. ✅\n\n"

                        f"Appointment ID: "
                        f"#{appointment.id}\n"

                        f"Doctor: Dr. "
                        f"{doctor_name}\n"

                        f"Date: "
                        f"{appointment.appointment_date}\n"

                        f"Time: "
                        f"{format_time(appointment.start_time)}"
                        f" - "
                        f"{format_time(appointment.end_time)}\n"

                        "Status: CONFIRMED"

                }


        return {

            "success": True,

            "reply":
                "I could not find a BOOKED "
                "appointment that needs confirmation."

        }


    # ========================================================
    # CONFIRM
    # ========================================================

    # Your appointment_service.py version
    # supports appointment_id.

    confirmed_appointment, error = (

        confirm_appointment(

            db=db,

            appointment_id=
                booked_appointment.id

        )

    )


    # ========================================================
    # ERROR
    # ========================================================

    if error:

        return {

            "success": False,

            "reply":
                "Sorry, I could not confirm "
                "your appointment.\n\n"
                f"Reason: {error}"

        }


    # ========================================================
    # SUCCESS
    # ========================================================

    doctor_name = (
        get_doctor_name(
            confirmed_appointment
        )
    )


    return {

        "success": True,

        "reply":

            "Your appointment has been "
            "confirmed successfully. ✅\n\n"

            f"Appointment ID: "
            f"#{confirmed_appointment.id}\n"

            f"Doctor: Dr. "
            f"{doctor_name}\n"

            f"Date: "
            f"{confirmed_appointment.appointment_date}\n"

            f"Time: "
            f"{format_time(confirmed_appointment.start_time)}"
            f" - "
            f"{format_time(confirmed_appointment.end_time)}\n"

            "Status: CONFIRMED\n\n"

            "Please arrive a few minutes "
            "before your appointment time."

    }


# ============================================================
# GROQ HEALTH RESPONSE
# ============================================================

def get_groq_response(
    user_message: str
):

    # --------------------------------------------------------
    # Groq unavailable
    # --------------------------------------------------------

    if groq_client is None:

        return (

            "I can help with general health "
            "information, but the AI service "
            "is currently unavailable."

        )


    # --------------------------------------------------------
    # Model missing
    # --------------------------------------------------------

    if not GROQ_MODEL:

        return (

            "GROQ_MODEL is not configured "
            "in the .env file."

        )


    # ========================================================
    # SYSTEM PROMPT
    # ========================================================

    system_prompt = """

You are the AI health assistant for Sanjeevani Clinic.

Your job is to provide general health information,
symptom guidance, and safe next steps.

IMPORTANT SAFETY RULES:

1. Do NOT diagnose a disease with certainty.
2. Do NOT prescribe prescription medicines.
3. Do NOT tell the patient to stop prescribed medicines.
4. Do NOT claim that a symptom definitely means a disease.
5. Clearly state when medical evaluation is recommended.
6. For emergency symptoms, tell the patient to seek
   urgent medical care immediately.
7. Keep answers understandable and practical.
8. Ask relevant follow-up questions when needed.
9. You may suggest the appropriate type of doctor,
   but actual doctors and appointment slots must come
   from the clinic database.
10. Never invent doctor names, appointment times,
    booking IDs, or medical records.

For symptoms such as cough, fever, pain, headache,
stomach problems, vomiting, diarrhea, cold, sore throat,
breathing problems, chest pain, dizziness, weakness,
skin problems, tooth pain, ear problems, or injuries,
give general information and safety guidance.

For cough, consider asking about:
- duration
- dry or mucus
- fever
- shortness of breath
- chest pain
- wheezing
- sore throat
- runny nose
- smoke/dust exposure
- medications
- allergies

For emergency warning signs such as severe difficulty
breathing, severe chest pain, fainting, confusion,
blue lips, uncontrolled bleeding, or severe sudden symptoms,
recommend urgent/emergency medical care.

You are NOT a replacement for a doctor.

"""

    # ========================================================
    # GROQ CALL
    # ========================================================

    try:

        response = (
            groq_client
            .chat
            .completions
            .create(

                model=GROQ_MODEL,

                messages=[

                    {
                        "role":
                            "system",

                        "content":
                            system_prompt
                    },

                    {
                        "role":
                            "user",

                        "content":
                            user_message
                    }

                ],

                temperature=0.2,

                max_tokens=500

            )
        )


        return (
            response
            .choices[0]
            .message
            .content
            .strip()
        )


    except Exception as e:

        print(
            "GROQ ERROR:",
            str(e)
        )


        return (

            "Sorry, I could not connect to "
            "the AI health assistant right now. "
            "Please try again."

        )


# ============================================================
# MAIN CHATBOT MESSAGE
# ============================================================

@router.post("/chatbot/message")
def chatbot_message(
    request: Request,
    message: str,
    db: Session = Depends(get_db)
):

    # ========================================================
    # LOGIN
    # ========================================================

    user_id = request.session.get(
        "user_id"
    )


    if user_id is None:

        return JSONResponse(

            status_code=401,

            content={

                "success": False,

                "reply":
                    "Please login first."

            }

        )


    # ========================================================
    # CLEAN MESSAGE
    # ========================================================

    user_message = (

        message

        .lower()

        .strip()

    )


    # ========================================================
    # GET USER APPOINTMENTS
    # ========================================================

    appointments = (
        get_patient_appointments(

            db,

            user_id

        )
    )


    # ========================================================
    # HELLO
    # ========================================================

    if user_message in [

        "hi",
        "hello",
        "hey",
        "hii",
        "good morning",
        "good afternoon",
        "good evening"

    ]:

        return {

            "success": True,

            "reply":

                "Hello! 👋\n\n"

                "Welcome to Sanjeevani Clinic. "
                "I am your clinic assistant.\n\n"

                "I can help you with:\n"

                "• Health questions\n"
                "• Symptoms\n"
                "• Finding a doctor\n"
                "• Checking available slots\n"
                "• Booking appointments\n"
                "• Confirming appointments\n"
                "• Checking your appointment\n\n"

                "How can I help you today?"

        }


    # ========================================================
    # HELP
    # ========================================================

    if (
        "help" in user_message
        or "what can you do" in user_message
    ):

        return {

            "success": True,

            "reply":

                "I can help you with:\n\n"

                "• General health questions\n"
                "• Symptoms\n"
                "• Find a specialist\n"
                "• Check doctor availability\n"
                "• Book an appointment\n"
                "• Confirm an appointment\n"
                "• Check your appointment\n\n"

                "Examples:\n\n"

                "\"I have a cough\"\n"
                "\"I need a neurologist\"\n"
                "\"Show available slots\"\n"
                "\"Book 10 AM\"\n"
                "\"What is my appointment time?\"\n"
                "\"Confirm my appointment\""

        }


    # ========================================================
    # CONFIRM APPOINTMENT
    # ========================================================

    confirmation_words = [

        "confirm my appointment",

        "confirm appointment",

        "confirm my booking",

        "confirm booking",

        "please confirm",

        "i want to confirm",

        "confirm it",

        "yes confirm",

        "yes, confirm",

        "confirm it please"

    ]


    is_confirmation_request = any(

        phrase in user_message

        for phrase in confirmation_words

    )


    if is_confirmation_request:

        return handle_confirmation(

            db=db,

            user_id=user_id

        )


    # ========================================================
    # BOOK SLOT
    # ========================================================

    booking_result = handle_slot_booking(

        request=request,

        db=db,

        user_id=user_id,

        user_message=user_message

    )


    if booking_result is not None:

        return booking_result


    # ========================================================
    # DOCTOR SEARCH
    # ========================================================

    doctor_result = handle_doctor_search(

        request=request,

        db=db,

        user_message=user_message

    )


    if doctor_result is not None:

        return doctor_result


    # ========================================================
    # APPOINTMENT DETAILS
    # ========================================================

    appointment_words = [

        "my appointment",

        "appointment time",

        "appointment date",

        "when is my appointment",

        "my booking",

        "booking time",

        "booking date"

    ]


    if any(

        word in user_message

        for word in appointment_words

    ):

        if not appointments:

            return {

                "success": True,

                "reply":
                    "You currently do not have "
                    "any appointments."

            }


        appointment = (
            appointments[0]
        )


        doctor_name = (
            get_doctor_name(
                appointment
            )
        )


        return {

            "success": True,

            "reply":

                "📅 Your appointment\n\n"

                f"Appointment ID: "
                f"#{appointment.id}\n"

                f"Doctor: Dr. "
                f"{doctor_name}\n"

                f"Date: "
                f"{appointment.appointment_date}\n"

                f"Time: "
                f"{format_time(appointment.start_time)}"
                f" - "
                f"{format_time(appointment.end_time)}\n"

                f"Status: "
                f"{appointment.status}"

        }


    # ========================================================
    # MY DOCTOR
    # ========================================================

    if (
        "who is my doctor"
        in user_message

        or "doctor name"
        in user_message
    ):

        if appointments:

            appointment = (
                appointments[0]
            )


            if appointment.doctor:

                return {

                    "success": True,

                    "reply":

                        f"Your appointment is "
                        f"with Dr. "
                        f"{appointment.doctor.name}.\n\n"

                        f"Specialization: "
                        f"{appointment.doctor.specialization}"

                }


        return {

            "success": True,

            "reply":
                "You currently do not have "
                "any appointment."

        }


    # ========================================================
    # RESCHEDULE
    # ========================================================

    if any(

        word in user_message

        for word in [

            "reschedule",

            "change appointment",

            "change date"

        ]

    ):

        if appointments:

            appointment = (
                appointments[0]
            )


            return {

                "success": True,

                "reply":
                    "Sure! You can reschedule "
                    "your appointment.",

                "action":
                    "reschedule",

                "appointment_id":
                    appointment.id

            }


        return {

            "success": True,

            "reply":
                "You do not have any "
                "appointment to reschedule."

        }


    # ========================================================
    # CANCEL
    # ========================================================

    if any(

        word in user_message

        for word in [

            "cancel my appointment",

            "cancel appointment",

            "cancel booking"

        ]

    ):

        if appointments:

            appointment = (
                appointments[0]
            )


            return {

                "success": True,

                "reply":
                    "Sure! You can cancel "
                    "your appointment.",

                "action":
                    "cancel",

                "appointment_id":
                    appointment.id

            }


        return {

            "success": True,

            "reply":
                "You do not have any "
                "appointment to cancel."

        }


    # ========================================================
    # THANK YOU
    # ========================================================

    if any(

        phrase in user_message

        for phrase in [

            "thank you",
            "thanks",
            "thank u"

        ]

    ):

        return {

            "success": True,

            "reply":
                "You're very welcome! 😊\n\n"
                "I'm happy to help."

        }


    # ========================================================
    # BYE
    # ========================================================

    if user_message in [

        "bye",
        "goodbye"

    ]:

        return {

            "success": True,

            "reply":
                "Goodbye! 👋\n\n"
                "Thank you for visiting "
                "Sanjeevani Clinic. "
                "Take care!"

        }


    # ========================================================
    # GROQ HEALTH AI
    # ========================================================

    ai_reply = get_groq_response(

        user_message

    )


    return {

        "success": True,

        "reply": ai_reply

    }