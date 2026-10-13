"""AI request evidence records - the hallucination-control audit trail."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class AiRequest(Base):
    """One evidence-grounded chatbot answer (or a controlled refusal)."""

    __tablename__ = "ai_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    actor: Mapped[str | None] = mapped_column(String(150), index=True)
    role: Mapped[str | None] = mapped_column(String(20))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    # VERIFIED | INCOMPLETE | CONFLICTED | NOT_FOUND | SOURCE_UNAVAILABLE | ACCESS_DENIED
    status: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    refusal_reason: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class AiEvidence(Base):
    """One piece of evidence retrieved for an AI request."""

    __tablename__ = "ai_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ai_request_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ai_requests.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    # DATABASE | APPROVED_SOURCE
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # e.g. "medicines#12" - a safe reference, never a full patient record
    source_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(60))
    snippet: Mapped[str | None] = mapped_column(Text)
    # True = supports the claim, False = contradicts it, None = neutral
    supports_claim: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AiClaim(Base):
    """One checkable claim from an AI answer, tied to its evidence."""

    __tablename__ = "ai_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ai_request_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ai_requests.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    # medicine_price | medicine_stock | medicine_for_disease | doctor_fee |
    # clinic_timing | appointment_status | followup_status | prescribed_medicine
    claim_kind: Mapped[str | None] = mapped_column(String(40), index=True)
    # VERIFIED | UNSUPPORTED | CONFLICTED | NOT_FOUND | SOURCE_UNAVAILABLE
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
