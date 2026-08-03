"""Pydantic request/response models."""
import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------- Auth ----------

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    is_admin: bool
    is_active: bool
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


# ---------- Products ----------

class ProductCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    category: str = Field(min_length=1, max_length=100)
    price: float = Field(ge=0)
    difficulty_level: str = Field(pattern="^(beginner|intermediate|advanced)$")
    tags: str = ""
    instructor_name: str = ""
    duration_hours: float = Field(ge=0, default=0)
    thumbnail_url: Optional[str] = None
    is_active: bool = True

    @field_validator("difficulty_level")
    @classmethod
    def validate_difficulty(cls, v):
        if v not in ("beginner", "intermediate", "advanced"):
            raise ValueError("difficulty_level must be beginner, intermediate, or advanced")
        return v


class ProductUpdate(ProductCreate):
    pass


class ProductOut(BaseModel):
    id: int
    title: str
    description: str
    category: str
    price: float
    difficulty_level: str
    tags: str
    instructor_name: str
    duration_hours: float
    thumbnail_url: Optional[str] = None
    is_active: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class ProductCardOut(BaseModel):
    """Trimmed product representation used inside recommendation payloads."""
    id: int
    title: str
    category: str
    difficulty_level: str
    price: float
    thumbnail_url: Optional[str] = None
    description: str


# ---------- Events ----------

class EventIn(BaseModel):
    event_type: str
    product_id: Optional[int] = None
    search_query: Optional[str] = None
    timestamp: Optional[str] = None
    metadata: Optional[dict] = None


class EventBatchIn(BaseModel):
    events: list[EventIn]


# ---------- Recommendations ----------

class RecommendationOut(BaseModel):
    narrative: str
    products: list[ProductCardOut]
    behavioral_summary: Optional[str] = None
    updated_at: datetime.datetime
    events_count_at_generation: int


# ---------- Generic error ----------

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
