"""What-if scenario runs - always synthetic, never live patient data."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class ScenarioRun(Base):
    """One what-if workflow simulation and its outputs.

    Simulations run on synthetic or isolated data only. ``is_synthetic`` is
    always True for anything created through the simulator tools - simulated
    results are never real patient facts and never modify live records.
    """

    __tablename__ = "scenario_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # doctor_unavailability | reschedule | followup_disruption | custom
    scenario_type: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    assumptions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    inputs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    outputs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    affected_counts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # RUNNING | COMPLETED | FAILED
    status: Mapped[str] = mapped_column(String(16), default="COMPLETED", nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
