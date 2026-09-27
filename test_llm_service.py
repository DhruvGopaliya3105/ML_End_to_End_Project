from src.services.llm_service import generate_ai_response


history = []


# User 1
user_message = "I have cough."

answer = generate_ai_response(
    user_message,
    history
)

print("\nBOT:", answer)


history.append(
    {
        "role": "user",
        "content": user_message
    }
)

history.append(
    {
        "role": "assistant",
        "content": answer
    }
)


# User 2
user_message = "It has been happening for 3 days."

answer = generate_ai_response(
    user_message,
    history
)

print("\nBOT:", answer)