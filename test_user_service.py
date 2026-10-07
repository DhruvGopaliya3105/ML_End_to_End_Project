from src.database.connection import SessionLocal
from src.schemas.user import UserCreate
from src.services.user_service import create_user


# Database session create
db = SessionLocal()

try:

    # Test signup data
    user_data = UserCreate(
        name="Test Patient",
        email="testpatient@example.com",
        phone="9876543210",
        password="TestPassword123",
        age=24,
        gender="Male"
    )

    # Create user
    user = create_user(db, user_data)

    if user:
        print("User created successfully!")
        print("User ID:", user.id)
        print("Name:", user.name)
        print("Email:", user.email)
        print("Role:", user.role)
    else:
        print("Email already exists!")

finally:

    # Close database connection
    db.close()