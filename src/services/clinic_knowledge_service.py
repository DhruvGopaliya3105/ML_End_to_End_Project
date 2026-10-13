"""Local, database-backed answers for the clinic chatbot.

This module lets the chatbot answer questions about medicines, diseases,
doctors, nearby chemists and clinic services using ONLY the project's own
database - no API key and no network needed. The chatbot router tries these
handlers before it falls back to the Groq AI, so catalog questions (prices,
stock, dosage) are always answered from the live tables and can never be
invented or wrong.

The bot understands plain English and common Hinglish words (dawai, bukhar,
khansi, sardi, dard, dukaan, kitna, batao ...), so patients can type the way
they actually talk.
"""

from __future__ import annotations

import re

from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.models.disease import Disease
from src.models.doctor import Doctor
from src.models.medicine import Medicine
from src.models.medicine_disease import MedicineDisease
from src.models.nearby_pharmacy import NearbyPharmacy
from src.models.visit_type import VisitType


# ============================================================
# SMALL HELPERS
# ============================================================

def _display_name(name) -> str:
    """Doctor names are stored WITH the 'Dr.' prefix - strip it so the
    'Dr.' label added in replies never renders as 'Dr. Dr.'"""
    cleaned = re.sub(
        r"^dr\.?\s+",
        "",
        (name or "").strip(),
        flags=re.IGNORECASE
    )
    return cleaned or "Doctor"


def _stock_line(med: Medicine) -> str:
    """Human friendly stock status for one medicine."""
    stock = int(med.stock or 0)
    alert = int(med.low_stock_alert or 0)
    if stock <= 0:
        return "Out of stock right now"
    if alert and stock <= alert:
        return f"Low stock - only {stock} pack(s) left"
    return f"In stock ({stock} packs)"


def _money(value) -> str:
    try:
        return f"Rs {float(value):.2f}"
    except (TypeError, ValueError):
        return "Rs 0.00"


def _diseases_of(db: Session, medicine_id: int) -> list[str]:
    rows = (
        db.query(Disease.name)
        .join(MedicineDisease, MedicineDisease.disease_id == Disease.id)
        .filter(MedicineDisease.medicine_id == medicine_id)
        .order_by(Disease.name)
        .all()
    )
    return [row[0] for row in rows]


def _active_medicines(db: Session, term: str, limit: int = 5) -> list[Medicine]:
    term = (term or "").strip()
    if not term:
        return []
    like = f"%{term}%"
    return (
        db.query(Medicine)
        .filter(
            Medicine.is_active.is_(True),
            or_(Medicine.name.ilike(like), Medicine.generic_name.ilike(like)),
        )
        .order_by(Medicine.stock.desc(), Medicine.name)
        .limit(limit)
        .all()
    )


# ============================================================
# DISEASE ALIASES (Hinglish + common short forms)
# ============================================================

DISEASE_ALIASES = {
    "diabetes": "diabetes", "diabetic": "diabetes", "sugar": "diabetes",
    "hypertension": "hypertension", "blood pressure": "hypertension",
    "bp": "hypertension", "thyroid": "thyroid", "asthma": "asthma",
    "breathing": "asthma", "cold": "cough-cold", "cough": "cough-cold",
    "sardi": "cough-cold", "jukam": "cough-cold", "throat": "cough-cold",
    "sorethroat": "cough-cold", "fever": "fever", "bukhar": "fever",
    "temperature": "fever", "headache": "headache", "migraine": "headache",
    "sir dard": "headache", "sirdard": "headache", "allergy": "allergy",
    "skin": "allergy", "rash": "allergy", "acidity": "acidity",
    "gas": "acidity", "pain": "pain", "dard": "pain", "body pain": "pain",
    "injury": "pain", "hurt": "pain", "arthritis": "arthritis",
    "joint": "arthritis", "joint pain": "arthritis", "knee": "arthritis",
    "infection": "antibiotic", "antibiotic": "antibiotic",
    "bacterial": "antibiotic", "sleep": "anxiety", "stress": "anxiety",
    "anxiety": "anxiety", "depression": "anxiety", "nerve": "nerve",
    "weakness": "nerve",
}

# which specialist usually handles a disease category (for the hint line)
DISEASE_SPECIALIST = {
    "diabetes": "General Medicine", "hypertension": "General Medicine",
    "thyroid": "General Medicine", "asthma": "General Medicine",
    "cough-cold": "General Medicine", "fever": "General Medicine",
    "headache": "Neurology", "allergy": "Dermatology",
    "acidity": "General Medicine", "pain": "Orthopedics",
    "arthritis": "Orthopedics", "antibiotic": "General Medicine",
    "anxiety": "Neurology", "nerve": "Neurology",
}


def _find_disease(db: Session, term: str):
    """Match a disease by alias, slug or (partial) name."""
    term = (term or "").strip().lower()
    if not term:
        return None
    slug = DISEASE_ALIASES.get(term, term)
    disease = db.query(Disease).filter(Disease.slug == slug).first()
    if disease:
        return disease
    if len(term) < 3:
        # too short for a fuzzy name match - "%a%" would match almost anything
        return None
    like = f"%{term}%"
    return (
        db.query(Disease)
        .filter(or_(Disease.name.ilike(like), Disease.slug.ilike(like)))
        .first()
    )


# ============================================================
# MEDICINE QUESTIONS
# ============================================================

# words that are intent, not part of a medicine name
_MEDICINE_STOPWORDS = {
    "price", "cost", "costs", "of", "the", "a", "an", "is", "are", "medicine",
    "medicines", "medicin", "dawai", "dawa", "dawaa", "tablet", "tablets",
    "capsule", "capsules", "syrup", "stock", "available", "availability",
    "have", "you", "your", "do", "my", "me", "please", "tell", "about",
    "side", "effect", "effects", "dosage", "dose", "doses", "how", "much",
    "what", "whats", "in", "our", "pharmacy", "catalog", "catalogue", "kya",
    "hai", "ka", "ki", "ke", "batao", "bata", "dikhao", "dikha", "hai",
    "for", "with", "and", "or", "i", "we", "need", "want", "buy", "get",
    "order", "show", "list", "all", "some", "any", "mrp", "rate", "rs",
    "mg", "strip", "bottle", "pack", "packs", "otc", "prescription", "rx",
    "prescribed", "doctor", "take", "taking", "use", "used", "uses", "like",
    "know", "find", "search", "looking", "there", "here", "sakte", "hain",
    "mujhe", "mera", "apne", "kaise", "kab", "kahan", "bought", "bought",
}


def _medicine_terms(message: str) -> list[str]:
    """Candidate name fragments, longest (bigram) first."""
    words = re.findall(r"[a-zA-Z0-9]+", message.lower())
    terms: list[str] = []
    for i in range(len(words) - 1):
        terms.append(f"{words[i]} {words[i + 1]}")
    terms.extend(words)
    seen, out = set(), []
    for term in terms:
        if len(term) >= 3 and term not in _MEDICINE_STOPWORDS and term not in seen:
            seen.add(term)
            out.append(term)
    return out


def _medicine_aspect(message: str) -> str:
    if "side effect" in message or "side-effect" in message:
        return "side_effects"
    if any(w in message for w in ("dosage", "dose", "how to take", "kaise le", "kaise len")):
        return "dosage"
    if any(w in message for w in ("stock", "available", "availability", "have", "hai kya", "in stock")):
        return "stock"
    if any(w in message for w in ("price", "cost", "daam", "kitna", "kitni", "kitne", "mrp", "rate")):
        return "price"
    if any(w in message for w in ("prescription", " rx", "rx ", "prescribed")):
        return "prescription"
    return "card"


def _medicine_card(db: Session, med: Medicine, aspect: str) -> str:
    diseases = _diseases_of(db, med.id)
    rx = bool(med.requires_prescription)
    lines = [f"💊 {med.name}"]
    if aspect == "price":
        lines.append(f"   Price: {_money(med.price)} (MRP {_money(med.mrp)})")
        lines.append(f"   Stock: {_stock_line(med)}")
    elif aspect == "stock":
        lines.append(f"   Stock: {_stock_line(med)}")
        lines.append(f"   Price: {_money(med.price)}")
    elif aspect == "dosage":
        lines.append(f"   How to take: {med.dosage_info or 'Follow the label / ask the pharmacist.'}")
        lines.append(f"   Pack: {med.pack_size or '-'}")
    elif aspect == "side_effects":
        lines.append(f"   Side effects: {med.side_effects or 'Not listed - please ask the pharmacist.'}")
    elif aspect == "prescription":
        lines.append(
            "   Prescription: "
            + ("REQUIRED - please get it from your doctor." if rx
               else "Not required (OTC - you can buy it directly).")
        )
        lines.append(f"   Price: {_money(med.price)}")
    else:  # full card
        if med.generic_name:
            lines.append(f"   Salt: {med.generic_name}")
        bits = [med.form, med.strength, med.pack_size]
        lines.append("   " + " | ".join(b for b in bits if b))
        lines.append(f"   Price: {_money(med.price)} (MRP {_money(med.mrp)})")
        lines.append(f"   Stock: {_stock_line(med)}")
        lines.append(
            "   Prescription: " + ("Required" if rx else "Not required (OTC)")
        )
        if diseases:
            lines.append("   Used for: " + ", ".join(diseases))
        if med.dosage_info:
            lines.append(f"   How to take: {med.dosage_info}")
        if med.side_effects:
            lines.append(f"   Side effects: {med.side_effects}")
        if med.warning:
            lines.append(f"   Note: {med.warning}")
    lines.append(
        f"\nOrder it on the /pharmacy page - search \"{med.name.split()[0]}\"."
    )
    if int(med.stock or 0) <= 0:
        lines.append("It is out of stock here - ask me about nearby chemists.")
    return "\n".join(lines)


def medicine_reply(db: Session, message: str) -> str | None:
    """Answer a catalog question from the medicines table.

    Returns None when the message is not about a medicine (or asks for a
    whole category, e.g. "medicine for diabetes" - that is disease_reply's
    job).
    """
    msg = message.lower()

    # "medicine for X" / "dawai for X" / "X ke liye dawai" -> disease question
    if re.search(r"(medicines?|dawai|dawa|tablet|capsule|syrup)\s+(for|se)\s+", msg) \
            or "ke liye" in msg:
        return None

    # "I have a fever", "I feel ..." -> a symptom, not a catalog question
    if any(phrase in msg for phrase in (
        "i have", "i am having", "i feel", "i got", "suffering",
        "hurts", "hurting", "pain in", "since ", "for the last",
    )):
        return None

    # "chest pain", "stomach pain", "fever" ... -> a symptom, never a
    # medicine name ("pain" would otherwise substring-match "Gum Paint")
    if any(keyword in msg for keyword in _ALL_SYMPTOM_KEYWORDS):
        return None

    # "all medicines" / "sari dawai" -> the whole live catalog
    if any(phrase in msg for phrase in (
        "all medicines", "all medicine", "all the medicines",
        "all tablets", "all tablet", "all capsules", "all syrup",
        "sari dawai", "sari dawa", "sari dawaiyan",
        "sab dawai", "sab dawa", "sab medicine", "sab medicines",
        "list all medicines", "list of all medicines",
        "show all medicines", "show me all medicines",
        "medicine list", "dawai list", "dawai ki list",
        "full catalog", "entire catalog", "whole catalog",
        "poori catalog", "catalog", "catalogue",
    )):
        meds = (
            db.query(Medicine)
            .filter(Medicine.is_active.is_(True))
            .order_by(Medicine.name)
            .all()
        )
        if not meds:
            return (
                "Our catalog is empty right now. 😕\n"
                "Please call the clinic and we will help you."
            )
        lines = [f"💊 All {len(meds)} medicines in our pharmacy:"]
        for med in meds:
            rx = " (Rx)" if med.requires_prescription else ""
            lines.append(f"• {med.name}{rx} - {_money(med.price)} - {_stock_line(med)}")
        lines.append(
            '\nAsk me "price of Dolo 650" for one medicine, or "medicine '
            'for diabetes" for everything we stock for a disease.'
        )
        return "\n".join(lines)

    intent = any(w in msg for w in (
        "medicine", "medicines", "dawai", "dawa", "tablet", "capsule",
        "syrup", "price of", "cost of", "stock of", "dosage of",
        "side effects of", "do you have", "hai kya", "kitna", "kitni",
        "kitne", "daam", "mrp", "otc", "prescription",
    ))
    if not intent:
        # still try a direct name match ("dolo", "paracetamol", "crocin")
        pass

    for term in _medicine_terms(msg):
        matches = _active_medicines(db, term, limit=5)
        if matches:
            if len(matches) == 1 or intent:
                return _medicine_card(db, matches[0], _medicine_aspect(msg))
            # several matches and no specific intent: list them
            lines = ["Here is what we have:"]
            for med in matches:
                lines.append(
                    f"• {med.name} - {_money(med.price)} - {_stock_line(med)}"
                )
            lines.append("\nAsk me the price, stock or dosage of any of these.")
            return "\n".join(lines)

    if intent:
        return (
            "I could not find that in our catalog. 😕\n\n"
            "You can browse all the medicines on the /pharmacy page, "
            "or tell me a disease (\"medicine for diabetes\") and I will "
            "list what we stock for it."
        )
    return None


# ============================================================
# DISEASE QUESTIONS
# ============================================================

def _disease_picker_reply(db: Session) -> str:
    """Ask which disease is meant, listing the ones we record."""
    rows = (
        db.query(Disease.name)
        .order_by(Disease.name)
        .all()
    )
    names = [row[0] for row in rows]
    if not names:
        return (
            "I could not find that disease in our records. 😕\n"
            "Browse the medicines on the /pharmacy page, or ask me "
            "about a medicine by name."
        )
    lines = ["🩺 Which disease do you mean? We record medicines for:"]
    lines.extend(f"• {name}" for name in names)
    lines.append(
        '\nTell me "medicine for diabetes" (or any disease above) and '
        "I will list what we stock for it."
    )
    return "\n".join(lines)


def _doctor_slots_line(db: Session, doctor_id: int) -> str:
    """Compact schedule summary, e.g. 'Mon-Sun, 10:00 AM - 02:00 PM'."""
    from src.models.doctor_schedule import DoctorSchedule

    rows = (
        db.query(DoctorSchedule)
        .filter(
            DoctorSchedule.doctor_id == doctor_id,
            DoctorSchedule.is_available.is_(True),
        )
        .all()
    )
    if not rows:
        return ""
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    days = sorted({row.day_of_week for row in rows})
    day_text = "Mon-Sun" if len(days) == 7 else ", ".join(day_names[d] for d in days)
    start = min(row.start_time for row in rows)
    end = max(row.end_time for row in rows)
    return f"{day_text}, {start.strftime('%I:%M %p')} - {end.strftime('%I:%M %p')}"


def disease_reply(db: Session, message: str) -> str | None:
    """Answer 'what is X' / 'medicine for X' from the diseases table."""
    msg = message.lower()

    med_for_intent = bool(
        re.search(r"(medicines?|dawai|dawa|tablet|capsule|syrup)\s+(for|se)\s+", msg)
        or "ke liye" in msg
    )
    explicit = (
        med_for_intent
        or "what is" in msg
        or "kya hai" in msg
        or "tell me about" in msg
        or "cure for" in msg
        or "treatment for" in msg
        or "ilaj" in msg
    )
    whole = re.sub(r"[^a-z ]", " ", msg).strip()

    disease = None
    if explicit:
        # try several candidate terms: after the intent phrase, every single
        # word and every word pair (Hinglish word order varies a lot)
        after_intent = re.sub(
            r".*?(medicines?|dawai|dawa|tablet|capsule|syrup|for|se|what is|kya hai|"
            r"tell me about|cure for|treatment for|ke liye|ilaj)\s*",
            "", msg,
        ).strip(" ?.!")
        words = re.findall(r"[a-z]+", msg)
        candidates = [after_intent, whole]
        candidates.extend(words)
        for i in range(len(words) - 1):
            candidates.append(f"{words[i]} {words[i + 1]}")
        for candidate in candidates:
            disease = _find_disease(db, candidate)
            if disease:
                break
    elif len(whole.split()) <= 3:
        # a bare disease name, e.g. "diabetes" or "bukhar"
        disease = _find_disease(db, whole)

    if not disease:
        if med_for_intent:
            # "medicines for a disease" - no specific disease named:
            # list the ones we record and ask which one
            return _disease_picker_reply(db)
        return None

    meds = (
        db.query(Medicine)
        .join(MedicineDisease, MedicineDisease.medicine_id == Medicine.id)
        .filter(
            MedicineDisease.disease_id == disease.id,
            Medicine.is_active.is_(True),
        )
        .order_by(Medicine.stock.desc(), Medicine.name)
        .all()
    )

    lines = [
        f"😔 Sorry to hear you are dealing with {disease.name}.",
        "Here is what our records say - general information only, "
        "not a diagnosis.",
        "",
        f"🩺 {disease.name}",
    ]
    if disease.description:
        lines.append(f"   {disease.description}")
    lines.append("")
    if meds:
        lines.append(f"💊 Medicines we stock for it ({len(meds)}):")
        for med in meds:
            rx = " (Rx required)" if med.requires_prescription else ""
            lines.append(f"   • {med.name} - {_money(med.price)} - {_stock_line(med)}{rx}")
            if med.dosage_info:
                lines.append(f"     How to take: {med.dosage_info}")
            if med.warning:
                lines.append(f"     ⚠ {med.warning}")
        lines.append(
            "   Which one to take: your doctor will decide the right one "
            "for you - OTC medicines can be bought directly, \"Rx "
            "required\" ones need a doctor's prescription."
        )
    else:
        lines.append("   We do not stock a specific medicine for it yet.")
    lines.append("")
    lines.append("🌿 If it is a normal / starting stage - what you can do:")
    lines.append("   • Rest, drink plenty of fluids and eat light food.")
    lines.append(
        "   • Monitor your symptoms - most mild cases settle within a few days."
    )
    lines.append(
        "   • The OTC medicines listed above can help - take them on time; "
        "a mild condition usually gets better with them."
    )
    lines.append("")
    lines.append("⚠️ If tablets are not taken:")
    lines.append(
        "   Skipping or stopping medicines can let the condition worsen "
        "or come back - take them on time and complete the full course."
    )
    lines.append("⚕️ Precautions:")
    lines.append(
        "   Every medicine can have side effects - read the label and ask "
        "the pharmacist. Do not mix medicines or stop them on your own."
    )
    lines.append("")
    lines.append("🚨 If it is a serious condition:")
    lines.append(
        "   If symptoms are severe, getting worse or lasting more than a "
        "few days, talk to a doctor immediately - do not self-medicate."
    )

    specialist = DISEASE_SPECIALIST.get(disease.slug)
    doctors = []
    if specialist:
        doctors = (
            db.query(Doctor)
            .filter(
                Doctor.is_active.is_(True),
                Doctor.specialization.ilike(f"%{specialist}%"),
            )
            .order_by(*doctor_fee_order())
            .limit(3)
            .all()
        )
    if doctors:
        lines.append("")
        lines.append(f"👨‍⚕️ {specialist} doctors at the clinic:")
        for doc in doctors:
            fee = (
                f"Rs {float(doc.consultation_fee):.0f}"
                if doc.consultation_fee
                else "fee on request"
            )
            slots = _doctor_slots_line(db, doc.id)
            slot_text = f" - Slots: {slots}" if slots else ""
            lines.append(
                f"   • Dr. {_display_name(doc.name)} - consultation {fee}{slot_text}"
            )
        lines.append("   Book and confirm your slot on the /doctors page.")
    elif specialist:
        lines.append("")
        lines.append(
            f"👨‍⚕️ Tip: book a {specialist} doctor from the /doctors page."
        )
    lines.append("")
    lines.append("   Please confirm with a doctor before starting any medicine.")
    return "\n".join(lines)


# ============================================================
# PHARMACY / CHEMIST / ORDERING QUESTIONS
# ============================================================

def pharmacy_reply(db: Session, message: str) -> str | None:
    msg = message.lower()

    # ---- nearby chemists ----
    if any(w in msg for w in (
        "chemist", "medical store", "medical shop", "dukaan", "dukan",
        "nearby", "near me", "near me", "around", "shop", "store", "where can",
        "out of stock",
    )):
        shops = (
            db.query(NearbyPharmacy)
            .filter(NearbyPharmacy.is_active.is_(True))
            .order_by(NearbyPharmacy.is_partner.desc(), NearbyPharmacy.name)
            .limit(5)
            .all()
        )
        if not shops:
            return (
                "I could not find any chemist shops in our records yet. 😕\n"
                "Please call the clinic and we will help you locate one."
            )
        lines = ["🏪 Chemist shops near the clinic:"]
        for shop in shops:
            badge = " (partner - live stock)" if shop.is_partner else ""
            open24 = " | 24x7" if shop.open_24x7 else ""
            phone = f" | ☎ {shop.phone}" if shop.phone else ""
            area = f", {shop.area}" if shop.area else ""
            lines.append(f"• {shop.name}{area}{badge}{open24}{phone}")
        lines.append(
            "\nOpen the /pharmacy/nearby page to see which shop has your "
            "medicine in stock, with a call button and a Google Maps route."
        )
        return "\n".join(lines)

    # ---- how to order / payment ----
    if any(w in msg for w in (
        "order", "cart", "buy", "purchase", "khareed", "kharid", "delivery",
        "deliver", "payment", "pay", "upi", "cash", "pickup", "pickup",
    )):
        return (
            "🛒 How ordering works:\n\n"
            "1. Open /pharmacy and search the medicine.\n"
            "2. Click \"Add to cart\" (prescription medicines need a doctor's "
            "prescription - they appear on your /pharmacy/prescriptions tab).\n"
            "3. Open the cart and checkout.\n"
            "4. Choose PICKUP or HOME DELIVERY.\n"
            "5. Pay ONLINE (UPI / QR - simulated on this demo) or CASH at "
            "the counter.\n"
            "6. Track it on /pharmacy/orders and print the receipt.\n\n"
            "Cancelled orders give the stock back automatically."
        )

    # ---- prescription rule ----
    if "prescription" in msg or re.search(r"\brx\b", msg):
        return (
            "📋 Prescription rule:\n\n"
            "• Medicines marked \"Rx required\" cannot be added to the cart "
            "until your doctor issues a prescription.\n"
            "• Once your doctor writes one, it shows on "
            "/pharmacy/prescriptions with an \"Add to cart\" button.\n"
            "• Everything else (OTC) can be bought directly."
        )

    return None


# ============================================================
# CLINIC SERVICES / TIMINGS / FEES
# ============================================================

def clinic_info_reply(db: Session, message: str) -> str | None:
    msg = message.lower()

    # ---- opening hours (computed from the real schedules) ----
    if any(w in msg for w in ("timing", "timings", "open", "close", "closed", "hours", "kab khul", "kab band")):
        from src.models.doctor_schedule import DoctorSchedule

        rows = (
            db.query(DoctorSchedule.start_time, DoctorSchedule.end_time)
            .distinct()
            .all()
        )
        if rows:
            start = min(r[0] for r in rows)
            end = max(r[1] for r in rows)
            lines = [
                f"🕒 Clinic timings: {start.strftime('%I:%M %p')} - "
                f"{end.strftime('%I:%M %p')}, Monday to Sunday.",
                "Appointments are booked in short slots - pick any time that "
                "fits you on the booking page.",
            ]
        else:
            lines = ["🕒 Please call the clinic for the current timings."]
        return "\n".join(lines)

    # ---- consultation fees ----
    if any(w in msg for w in ("fee", "fees", "charges", "charge", "cost of consultation", "consultation cost")):
        doctors = db.query(Doctor).filter(Doctor.is_active.is_(True)).all()
        fees = [float(d.consultation_fee) for d in doctors if d.consultation_fee]
        if fees:
            return (
                f"💰 Consultation fees at Sanjeevani Clinic range from "
                f"Rs {min(fees):.0f} to Rs {max(fees):.0f}, depending on the "
                f"specialist.\n\nThe exact fee is shown on each doctor's "
                f"profile on the /doctors page."
            )
        return "💰 The consultation fee is shown on each doctor's profile."

    # ---- services / visit types ----
    if any(w in msg for w in (
        "service", "services", "visit type", "visit types", "what do you treat",
        "what do you offer", "consultation type",
    )):
        visit_types = (
            db.query(VisitType)
            .filter(VisitType.is_active.is_(True))
            .order_by(VisitType.name)
            .all()
        )
        lines = ["🏥 Services at Sanjeevani Clinic:"]
        for vt in visit_types:
            lines.append(
                f"• {vt.name} ({vt.default_duration_minutes} min)"
            )
        lines.append(
            "\nPlus: online pharmacy with home delivery, AI symptom "
            "screening, medical reports upload and doctor follow-up care."
        )
        return "\n".join(lines)

    # ---- how to book ----
    if any(w in msg for w in ("how to book", "how do i book", "book an appointment", "appointment kaise", "booking kaise")):
        return (
            "📅 Booking an appointment:\n\n"
            "1. Open /doctors and pick a specialist.\n"
            "2. Choose a date - the page shows the free slots.\n"
            "3. Pick a slot and confirm.\n"
            "4. Pay online (UPI/QR) or cash at the counter.\n"
            "5. See it on /appointments - you can cancel or reschedule there.\n\n"
            "You can also tell me \"I need a cardiologist\" or \"book 10 AM\" "
            "and I will walk you through it."
        )

    # ---- cancel / refund ----
    if "cancel" in msg or "refund" in msg:
        return (
            "↩️ Cancellation & refunds:\n\n"
            "• Appointments: cancel from the /appointments page; the slot "
            "becomes free again.\n"
            "• Medicine orders: cancel from /pharmacy/orders before they are "
            "handed over - the stock is restored automatically.\n"
            "• Paid orders are refunded by the pharmacy counter; cash orders "
            "need no refund."
        )

    # ---- reports / tests ----
    if any(w in msg for w in ("report", "reports", "test", "tests", "lab", "upload")):
        return (
            "📄 Medical reports:\n\n"
            "• Upload prescriptions, lab reports and scans on "
            "/medical-reports.\n"
            "• Your doctor sees them in your file on the Doctor Desk.\n"
            "• Your full history is on /medical-history."
        )

    return None


# ============================================================
# SYMPTOM GUIDANCE (safe, local, no AI key needed)
# ============================================================

EMERGENCY_SYMPTOMS = (
    "chest pain", "heart attack", "can't breathe", "cant breathe",
    "cannot breathe", "difficulty breathing", "shortness of breath",
    "faint", "unconscious", "blue lips", "uncontrolled bleeding",
    "severe bleeding", "stroke", "seizure", "convulsion",
)


def emergency_reply(message: str) -> str | None:
    """Urgent-care message for emergency symptoms.

    Kept separate from symptom_reply() so the chatbot router can check for
    emergencies BEFORE any catalog handler runs - a medical emergency must
    never be answered with a medicine card.
    """
    msg = message.lower()

    if any(symptom in msg for symptom in EMERGENCY_SYMPTOMS):
        return (
            "🚨 This can be an emergency.\n\n"
            "Please seek urgent medical care immediately - call an ambulance "
            "or go to the nearest hospital emergency. Do not wait.\n\n"
            "If you are at the clinic, inform the front desk right away."
        )

    return None


SYMPTOM_SPECIALISTS = [
    (("chest", "heart palpitation", "breathing"), "Cardiology"),
    (("fever", "cold", "cough", "sore throat", "runny nose", "bukhar",
      "khansi", "sardi", "jukam", "throat"), "General Medicine"),
    (("headache", "migraine", "dizziness", "sir dard", "dizzy"), "Neurology"),
    (("stomach", "vomit", "diarrhea", "loose motion", "acidity", "gas",
      "nausea"), "General Medicine"),
    (("skin", "rash", "acne", "itch", "allergy", "hair fall"), "Dermatology"),
    (("tooth", "teeth", "dental", "gum"), "Dentistry"),
    (("ear", "nose", "sinus"), "ENT"),
    (("eye", "eyes", "vision", "red eye"), "Ophthalmology"),
    (("bone", "joint", "back pain", "knee", "arthritis", "fracture",
      "sprain"), "Orthopedics"),
    (("child", "kid", "kids", "baby", "infant"), "Pediatrics"),
    (("pregnan", "period", "gyne", "women"), "Gynecology"),
    (("anxiety", "stress", "sleep", "depression", "nerve", "weakness",
      "numbness"), "Neurology"),
    (("pain", "hurt", "dard", "injury", "swelling", "burn"), "General Medicine"),
]


# every keyword emergency_reply/symptom_reply react to - medicine_reply must
# NOT answer messages containing these (a symptom is never a medicine name)
_ALL_SYMPTOM_KEYWORDS = tuple(
    set(EMERGENCY_SYMPTOMS)
    | {keyword for keywords, _ in SYMPTOM_SPECIALISTS for keyword in keywords}
)


def doctor_fee_order():
    """Portable "cheapest consultation first, fee-less doctors last".

    The SQL-standard way of pushing NULL fees to the end of an ORDER BY
    clause is PostgreSQL/SQLite-only syntax - MySQL/MariaDB reject it
    with error 1064. Emulating it with ``(fee IS NULL)`` first works on
    every supported database.
    """

    return (
        Doctor.consultation_fee.is_(None),
        Doctor.consultation_fee,
        Doctor.name,
    )


def symptom_reply(db: Session, message: str) -> str | None:
    """Safe general guidance + real doctors from the database."""
    msg = message.lower()

    emergency = emergency_reply(msg)

    if emergency:
        return emergency

    specialist = None
    for keywords, spec in SYMPTOM_SPECIALISTS:
        if any(keyword in msg for keyword in keywords):
            specialist = spec
            break

    if not specialist:
        return None

    doctors = (
        db.query(Doctor)
        .filter(
            Doctor.is_active.is_(True),
            Doctor.specialization.ilike(f"%{specialist}%"),
        )
        .order_by(*doctor_fee_order())
        .limit(3)
        .all()
    )

    lines = [
        "⚕️ I am not a doctor - this is general information only.\n",
        f"For these symptoms, a {specialist} specialist is usually the "
        f"right first visit.",
        "",
        "Rest, fluids and monitoring symptoms help in most mild cases. Please "
        "see a doctor if symptoms are severe, getting worse, or last more "
        "than a few days.",
    ]
    if doctors:
        lines.append("")
        lines.append(f"👨‍⚕️ Our {specialist} doctors:")
        for doc in doctors:
            fee = f"Rs {float(doc.consultation_fee):.0f}" if doc.consultation_fee else "fee on request"
            exp = f", {doc.experience_years} yrs" if doc.experience_years else ""
            lines.append(f"• Dr. {_display_name(doc.name)}{exp} - consultation {fee}")
        lines.append("")
        lines.append(
            "Book on the /doctors page, or tell me \"I need a "
            f"{specialist.lower()} doctor\" and I will show you the slots."
        )
    return "\n".join(lines)


# ============================================================
# GENERAL FALLBACK (no key, nothing matched)
# ============================================================

def general_reply() -> str:
    return (
        "I can answer from the clinic's own records - no internet needed 😊\n\n"
        "• 💊 Medicines - price, stock, dosage, side effects\n"
        "• 🩺 Diseases - what we stock for them\n"
        "• 👨‍⚕️ Doctors - specialization, fees, availability\n"
        "• 🏪 Nearby chemist shops\n"
        "• 📅 Appointments - booking, timings, cancellation\n"
        "• 🤒 General symptom guidance\n\n"
        "Try one of these:\n"
        "\"price of Dolo 650\"\n"
        "\"medicine for diabetes\"\n"
        "\"cardiologist\"\n"
        "\"chemist near me\"\n"
        "\"I have a fever\"\n"
        "\"clinic timings\""
    )
