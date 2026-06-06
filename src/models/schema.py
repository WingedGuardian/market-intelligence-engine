"""
SQLAlchemy models for the intent engine pipeline.

Tables follow the signal → score → outreach flow. scores_history exists
for trend visualization; the live score lives on the company row.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    domain = Column(String(255), unique=True, nullable=False)
    industry = Column(String(128))
    intent_score = Column(Float, default=0.0)
    last_scored_at = Column(DateTime)
    last_alerted_at = Column(DateTime)  # cooldown tracking
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    signals = relationship("Signal", back_populates="company", lazy="dynamic")
    contacts = relationship("Contact", back_populates="company")
    scores = relationship("ScoreHistory", back_populates="company", lazy="dynamic")

    __table_args__ = (
        Index("ix_companies_score", "intent_score"),
    )


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    source = Column(String(64), nullable=False)  # rss, edgar, web, manual
    type = Column(String(64), nullable=False)     # executive_hire, funding, etc.
    content = Column(Text)
    sentiment = Column(Float)  # -1.0 to 1.0
    confidence = Column(Float, default=0.5)
    raw_json = Column(JSONB)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    company = relationship("Company", back_populates="signals")

    __table_args__ = (
        Index("ix_signals_company_created", "company_id", "created_at"),
    )


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    name = Column(String(255), nullable=False)
    title = Column(String(255))
    email = Column(String(255))
    linkedin_url = Column(String(512))
    source = Column(String(64))
    discovered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    company = relationship("Company", back_populates="contacts")


class ScoreHistory(Base):
    __tablename__ = "scores_history"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    score = Column(Float, nullable=False)
    scored_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    company = relationship("Company", back_populates="scores")

    __table_args__ = (
        Index("ix_scores_company_time", "company_id", "scored_at"),
    )


class Outreach(Base):
    __tablename__ = "outreach"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    contact_id = Column(Integer, ForeignKey("contacts.id"))
    message = Column(Text)
    talking_points = Column(JSONB)
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def init_db(database_url: str):
    """Create all tables. Idempotent."""
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    return engine
