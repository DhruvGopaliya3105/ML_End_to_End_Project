import os

from dotenv import load_dotenv
from groq import Groq


# =========================================================
# LOAD .ENV
# =========================================================

load_dotenv()


# =========================================================
# GET API KEY
# =========================================================

api_key = os.getenv("GROQ_API_KEY")


if not api_key:
    raise ValueError(
        "GROQ_API_KEY was not found in .env"
    )


# =========================================================
# CREATE GROQ CLIENT
# =========================================================

client = Groq(
    api_key=api_key
)


# =========================================================
# SEND TEST MESSAGE
# =========================================================

response = client.chat.completions.create(

    model="openai/gpt-oss-20b",

    messages=[
        {
            "role": "system",
            "content": (
                "You are a helpful AI assistant "
                "for Sanjeevani Clinic."
            )
        },
        {
            "role": "user",
            "content": (
                "Hello! Introduce yourself briefly."
            )
        }
    ],

    temperature=0.7,

    max_tokens=200
)


# =========================================================
# GET RESPONSE
# =========================================================

answer = response.choices[0].message.content


# =========================================================
# PRINT RESPONSE
# =========================================================

print()
print("=" * 50)
print("GROQ AI RESPONSE")
print("=" * 50)
print()

print(answer)

print()
print("=" * 50)