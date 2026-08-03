"""SQLAlchemy ORM table definitions."""
import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base


def utcnow():
    return datetime.datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    last_active_at = Column(DateTime, default=utcnow, nullable=False)

    events = relationship("Event", back_populates="user", cascade="all, delete-orphan")
    recommendation = relationship(
        "Recommendation", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), index=True, nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(100), index=True, nullable=False)
    price = Column(Float, nullable=False, default=0.0)
    difficulty_level = Column(String(20), nullable=False, default="beginner")
    tags = Column(String(500), nullable=False, default="")
    instructor_name = Column(String(255), nullable=False, default="")
    duration_hours = Column(Float, nullable=False, default=0.0)
    thumbnail_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    event_type = Column(String(50), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    search_query = Column(String(500), nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True, nullable=False)

    user = relationship("User", back_populates="events")
    product = relationship("Product")

    __table_args__ = (
        Index("ix_events_user_created", "user_id", "created_at"),
        Index("ix_events_user_type", "user_id", "event_type"),
    )


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    narrative = Column(Text, nullable=False)
    product_ids_json = Column(Text, nullable=False, default="[]")
    behavioral_summary = Column(Text, nullable=True)
    retrieval_scores_json = Column(Text, nullable=True)
    events_count_at_generation = Column(Integer, default=0, nullable=False)
    model_used = Column(String(100), nullable=True)
    generation_duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    user = relationship("User", back_populates="recommendation")


class EmailDeliveryLog(Base):
    __tablename__ = "email_delivery_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recommendation_id = Column(Integer, ForeignKey("recommendations.id"), nullable=True)
    delivered_at = Column(DateTime, default=utcnow, nullable=False)
    status = Column(String(20), nullable=False)  # sent / failed / skipped
    error_message = Column(Text, nullable=True)
