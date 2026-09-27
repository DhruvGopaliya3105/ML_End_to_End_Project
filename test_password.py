from src.security.password import hash_password, verify_password


password = "TestPassword123"

hashed_password = hash_password(password)

print("Original password:", password)
print("Hashed password:", hashed_password)

print(
    "Correct password:",
    verify_password(password, hashed_password)
)

print(
    "Wrong password:",
    verify_password("WrongPassword", hashed_password)
)