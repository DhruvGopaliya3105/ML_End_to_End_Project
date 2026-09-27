from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
    password: str
    age: int | None = None
    gender: str | None = None


class UserUpdate(BaseModel):
    name: str
    phone: str | None = None
    age: int | None = None
    gender: str | None = None