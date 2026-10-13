"""AI safety benchmark runs and per-test results."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class AiBenchmarkRun(Base):
    """One run of the AI reliability / red-team benchmark suite."""

    __tablename__ = "ai_benchmark_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    suite_version: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(60))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_tests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # measured metrics: unsupported-claim rate, grounding accuracy, refusal
    # accuracy, unauthorized-access prevention rate, regression pass rate...
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AiBenchmarkResult(Base):
    """One benchmark test result within a run."""

    __tablename__ = "ai_benchmark_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ai_benchmark_runs.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    test_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    # grounding | refusal | access | injection | conflict | regression
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metric_name: Mapped[str | None] = mapped_column(String(60))
    metric_value: Mapped[float | None] = mapped_column(Float)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
