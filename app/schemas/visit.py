from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime


class VisitFormData(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=150)
    company: str = Field(..., min_length=1, max_length=200)
    id_document: str = Field(..., min_length=1, max_length=50)
    department_id: UUID
    visit_reason: str = Field(..., min_length=1, max_length=2000)
    phone: str | None = Field(None, max_length=30)


class VisitOut(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    company: str
    phone: str | None
    department_name: str | None = None
    visit_reason: str
    language: str
    checked_in_at: datetime
    checked_out_at: datetime | None
    checkout_method: str | None
    minutes_inside: float | None = None

    model_config = {"from_attributes": True}


class ActiveVisitOut(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    company: str
    department_name: str | None = None
    checked_in_at: datetime
    minutes_inside: float

    model_config = {"from_attributes": True}


class DayStats(BaseModel):
    active_now: int
    entries_today: int
    exits_today: int
    avg_duration_minutes: float | None
