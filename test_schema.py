from src.schemas.user import UserCreate


user = UserCreate(
    name="Dhruv",
    email="dhruv@example.com",
    phone="9876543210",
    password="TestPassword123",
    age=24,
    gender="Male"
)


print("User schema is valid!")
print(user)