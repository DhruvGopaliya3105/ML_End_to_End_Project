import os
import base64
import json

from groq import Groq
from dotenv import load_dotenv


# =========================================================
# LOAD ENVIRONMENT VARIABLES
# =========================================================

load_dotenv()


GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY"
)


GROQ_VISION_MODEL = os.getenv(
    "GROQ_VISION_MODEL",
    "qwen/qwen3.8-27b"
)


# =========================================================
# GROQ CLIENT
# =========================================================

client = Groq(
    api_key=GROQ_API_KEY
)


# =========================================================
# ANALYZE INJURY IMAGE
# =========================================================

def analyze_injury_image(
    file_bytes: bytes,
    filename: str
):

    try:

        # =================================================
        # 1. CONVERT IMAGE TO BASE64
        # =================================================

        encoded_image = base64.b64encode(
            file_bytes
        ).decode("utf-8")

        # =================================================
        # 2. DETECT IMAGE TYPE
        # =================================================

        extension = (
            filename
            .lower()
            .split(".")[-1]
        )

        mime_types = {

            "jpg": "image/jpeg",

            "jpeg": "image/jpeg",

            "png": "image/png",

            "webp": "image/webp"
        }

        mime_type = mime_types.get(
            extension,
            "image/jpeg"
        )

        # =================================================
        # 3. CREATE IMAGE URL
        # =================================================

        image_url = (
            f"data:{mime_type};base64,"
            f"{encoded_image}"
        )

        # =================================================
        # 4. AI PROMPT
        # =================================================

        prompt = """

You are a medical image TRIAGE assistant
for Sanjeevani Clinic.

Analyze the uploaded image only for
preliminary injury triage.

IMPORTANT SAFETY RULES:

1. Do NOT give a definitive diagnosis.

2. Do NOT prescribe medicines.

3. Do NOT claim certainty.

4. Do NOT invent information that cannot
   be reasonably observed from the image.

5. This is preliminary triage only.

6. An injury should be marked emergency
   ONLY when the image gives a reasonable
   indication of a potentially serious
   or life-threatening condition.

7. Do NOT mark a normal minor abrasion,
   small cut, mild bruise, or ordinary
   swelling as emergency.

8. Moderate does NOT mean emergency.

9. Severe does NOT always mean a diagnosis,
   but severe visible injury should be
   routed for urgent medical attention.

10. Recommend a specialist based on the
    visible injury/body part.

SPECIALIST RULES:

- Bone, joint, fracture, dislocation,
  serious musculoskeletal injury:
  Orthopedic

- Skin-related injury, rash, superficial
  skin problem or burn:
  Dermatologist

- Neurological-looking injury:
  Neurologist

- Heart/chest-related concern:
  Cardiologist

- General non-specialist problem:
  General Physician

- Clearly dangerous emergency:
  Emergency

If the specialist cannot reasonably be
determined, use "Unknown".

Return ONLY valid JSON.

Use EXACTLY this structure:

{
    "injury_type": "",
    "body_part": "",
    "severity": "",
    "specialist": "",
    "recommendation": "",
    "emergency": false
}

Allowed severity values:

- minor
- moderate
- severe
- unclear

Possible injury types:

- cut
- bruise
- burn
- swelling
- abrasion
- wound
- possible fracture
- possible dislocation
- rash
- other
- unclear

Allowed specialist values:

- Orthopedic
- Dermatologist
- Neurologist
- Cardiologist
- General Physician
- Emergency
- Unknown

IMPORTANT:

If the image shows only a moderate abrasion,
do NOT set emergency=true.

If the image is not clearly dangerous,
emergency must be false.

Do not invent information.
"""

        # =================================================
        # 5. GROQ VISION REQUEST
        # =================================================

        response = client.chat.completions.create(

            model=GROQ_VISION_MODEL,

            messages=[

                {
                    "role": "system",

                    "content": (
                        "You are a safe medical "
                        "image triage assistant."
                    )
                },

                {
                    "role": "user",

                    "content": [

                        {
                            "type": "text",

                            "text": prompt
                        },

                        {
                            "type": "image_url",

                            "image_url": {

                                "url": image_url
                            }
                        }
                    ]
                }
            ],

            temperature=0,

            max_tokens=500,

            response_format={
                "type": "json_object"
            }
        )

        # =================================================
        # 6. GET AI RESPONSE
        # =================================================

        content = (
            response
            .choices[0]
            .message
            .content
        )

        # =================================================
        # 7. JSON PARSE
        # =================================================

        result = json.loads(
            content
        )

        # =================================================
        # 8. SAFETY DEFAULTS
        # =================================================

        if "injury_type" not in result:
            result["injury_type"] = "unclear"

        if "body_part" not in result:
            result["body_part"] = "unclear"

        if "severity" not in result:
            result["severity"] = "unclear"

        if "specialist" not in result:
            result["specialist"] = "Unknown"

        if "recommendation" not in result:
            result["recommendation"] = ""

        if "emergency" not in result:
            result["emergency"] = False

        # =================================================
        # 9. NORMALIZE EMERGENCY
        # =================================================

        if isinstance(
            result["emergency"],
            str
        ):

            result["emergency"] = (
                result["emergency"]
                .lower()
                .strip()
                in [
                    "true",
                    "yes",
                    "1"
                ]
            )

        # =================================================
        # 10. NORMALIZE SEVERITY
        # =================================================

        result["severity"] = (
            str(
                result["severity"]
            )
            .lower()
            .strip()
        )

        # =================================================
        # 11. RETURN RESULT
        # =================================================

        return {

            "success": True,

            "data": result
        }

    except Exception as e:

        print(
            "INJURY ANALYSIS ERROR:",
            str(e)
        )

        return {

            "success": False,

            "error": str(e)
        }


# =========================================================
# SPECIALIST NORMALIZATION
# =========================================================

def normalize_specialist(
    specialist: str
):

    if not specialist:

        return "General Physician"

    specialist_lower = (
        str(specialist)
        .lower()
        .strip()
    )

    # =====================================================
    # ORTHOPEDIC
    # =====================================================

    if (
        "orthopedic" in specialist_lower
        or
        "orthopaedic" in specialist_lower
    ):

        return "Orthopedic"

    # =====================================================
    # DERMATOLOGIST
    # =====================================================

    if (
        "dermat" in specialist_lower
        or
        "skin" in specialist_lower
    ):

        return "Dermatologist"

    # =====================================================
    # NEUROLOGIST
    # =====================================================

    if (
        "neurolog" in specialist_lower
        or
        "neuro" in specialist_lower
    ):

        return "Neurologist"

    # =====================================================
    # CARDIOLOGIST
    # =====================================================

    if (
        "cardio" in specialist_lower
        or
        "heart" in specialist_lower
    ):

        return "Cardiologist"

    # =====================================================
    # EMERGENCY
    # =====================================================

    if "emergency" in specialist_lower:

        return "Emergency"

    # =====================================================
    # GENERAL PHYSICIAN
    # =====================================================

    if (
        "general" in specialist_lower
        or
        "physician" in specialist_lower
        or
        "doctor" in specialist_lower
    ):

        return "General Physician"

    # =====================================================
    # UNKNOWN
    # =====================================================

    if (
        specialist_lower == "unknown"
        or
        specialist_lower == "unclear"
    ):

        return "General Physician"

    return specialist