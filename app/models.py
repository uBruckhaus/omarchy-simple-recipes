from datetime import datetime
from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

class Recipe(Base):
    __tablename__ = "recipes"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    emoji: Mapped[str] = mapped_column(String(8), default="🍽️")
    image_url: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(Text, unique=True)
    source_type: Mapped[str] = mapped_column(String(30), default="Webseite")
    category: Mapped[str] = mapped_column(String(80), default="")
    ingredients: Mapped[str] = mapped_column(Text, default="[]")
    instructions: Mapped[str] = mapped_column(Text, default="[]")
    tags: Mapped[str] = mapped_column(Text, default="[]")
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_class: Mapped[str] = mapped_column(String(20), default="unbekannt")
    servings: Mapped[str] = mapped_column(String(80), default="")
    calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunks: Mapped[int] = mapped_column(Integer, default=1)
    tried: Mapped[bool] = mapped_column(Boolean, default=False)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

class Setting(Base):
    """Simple key/value store for local preferences (no user accounts)."""
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text, default="")

class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    icon: Mapped[str] = mapped_column(String(16), default="🏷️")
