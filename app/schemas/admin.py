from pydantic import BaseModel, Field, EmailStr
from uuid import UUID
from datetime import datetime


class LoginForm(BaseModel):
    email: str
    password: str


class AdminUserOut(BaseModel):
    id: UUID
    email: str
    name: str
    role: str
    active: bool
    last_login: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminUserCreate(BaseModel):
    email: str = Field(..., max_length=200)
    name: str = Field(..., max_length=200)
    password: str = Field(..., min_length=12)
    role: str = Field(default="receptionist")


class AdminUserUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    role: str | None = None
    active: bool | None = None


class DepartmentCreate(BaseModel):
    name_ca: str = Field(..., max_length=200)
    name_es: str = Field(..., max_length=200)
    name_fr: str = Field(..., max_length=200)
    name_en: str = Field(..., max_length=200)
    order: int = 0


class DepartmentUpdate(BaseModel):
    name_ca: str | None = Field(None, max_length=200)
    name_es: str | None = Field(None, max_length=200)
    name_fr: str | None = Field(None, max_length=200)
    name_en: str | None = Field(None, max_length=200)
    order: int | None = None
    active: bool | None = None


class LegalDocCreate(BaseModel):
    content_ca: str
    content_es: str
    content_fr: str
    content_en: str
