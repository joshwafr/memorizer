from datetime import datetime, timezone
from sqlalchemy import String, Text, Boolean, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base, UTCDateTime

def utcnow():
    return datetime.now(timezone.utc)

class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(2048), unique=True)
    source_type: Mapped[str] = mapped_column(String(20))          # youtube | article
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending -> fetched -> inbox | discarded | failed ; inbox -> approved | rejected
    triage_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), default=utcnow)
    cards: Mapped[list["Card"]] = relationship(back_populates="source")

class Card(Base):
    __tablename__ = "cards"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    key_points: Mapped[list] = mapped_column(JSON, default=list)
    fsrs_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime(timezone=True), nullable=True, index=True)
    suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), default=utcnow)
    source: Mapped["Source"] = relationship(back_populates="cards")

class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"))
    grade: Mapped[str] = mapped_column(String(10))                 # again|hard|good|easy
    mode: Mapped[str] = mapped_column(String(10), default="text")
    user_answer: Mapped[str] = mapped_column(Text)
    feedback: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), default=utcnow)

class InterestProfile(Base):
    __tablename__ = "interest_profile"
    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), default=utcnow)

class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)

class ListenProgress(Base):
    __tablename__ = "listen_progress"
    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[str] = mapped_column(String(100), unique=True)   # spotify episode id
    kind: Mapped[str] = mapped_column(String(20), default="podcast")
    show_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(default=0)
    max_position_ms: Mapped[int] = mapped_column(default=0)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), default=utcnow)

class SiteCookie(Base):
    __tablename__ = "site_cookies"
    domain: Mapped[str] = mapped_column(String(200), primary_key=True)  # e.g. ft.com
    cookies: Mapped[str] = mapped_column(Text)                          # raw Cookie header value
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), default=utcnow)
