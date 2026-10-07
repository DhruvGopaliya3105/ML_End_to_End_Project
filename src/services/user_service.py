from sqlalchemy.orm import Session

from src.models.user import User
from src.schemas.user import UserCreate
from src.security.password import hash_password


def create_user(db: Session, user_data: UserCreate):

    # Check whether email already exists
    existing_user = (
        db.query(User)
        .filter(User.email == user_data.email)
        .first()
    )

    if existing_user:
        return None

    # Create new user
    new_user = User(
        name=user_data.name,
        email=user_data.email,
        phone=user_data.phone,
        password_hash=hash_password(user_data.password),
        age=user_data.age,
        gender=user_data.gender,
        role="PATIENT"
    )

    # Save user
    db.add(new_user)
    db.commit()

    # Get generated ID and other DB values
    db.refresh(new_user)

    return new_user
