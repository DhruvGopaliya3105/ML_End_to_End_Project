"""U4 - What-If Workflow Simulator MCP (USER, port 9104, svc-u4-simulator).

Simulates operational decisions on SYNTHETIC data. Simulations never modify
live appointments, prescriptions or patient records.
"""

from datetime import date, timedelta

from src.database.connection import SessionLocal
from src.mcp.server_base import (
    ControlledError,
    build_server,
    mcp_tool,
    serve,
)
from src.models.appointment import Appointment
from src.models.follow_up import FollowUp
from src.models.scenario_run import ScenarioRun
from src.services.mcp_rbac import get_server

SERVER = get_server("workflow-simulator")
mcp = build_server(SERVER)

SCENARIO_TYPES = ("doctor_unavailability", "reschedule", "followup_disruption")
_ACTIVE = ("CONFIRMED", "PENDING")


def _validate(scenario: dict) -> dict:
    scenario = dict(scenario or {})
    stype = scenario.get("scenario_type")
    if stype not in SCENARIO_TYPES:
        raise ControlledError(
            "INVALID_INPUT",
            f"scenario_type must be one of {list(SCENARIO_TYPES)}",
        )
    params = dict(scenario.get("params") or {})
    if stype == "doctor_unavailability" and (not params.get("doctor_id") or not params.get("days")):
        raise ControlledError("INVALID_INPUT", "doctor_unavailability needs doctor_id + days")
    if stype == "reschedule" and not params.get("shift_days"):
        raise ControlledError("INVALID_INPUT", "reschedule needs shift_days")
    if stype == "followup_disruption" and not params.get("days"):
        raise ControlledError("INVALID_INPUT", "followup_disruption needs days")
    return {"scenario_type": stype, "params": params}


def _simulate(db, scenario: dict) -> dict:
    """Compute synthetic outcomes + real aggregate counts (counts only)."""
    stype = scenario["scenario_type"]
    params = scenario["params"]
    today = date.today()
    if stype == "doctor_unavailability":
        horizon = today + timedelta(days=int(params["days"]))
        upcoming = (
            db.query(Appointment)
            .filter(
                Appointment.doctor_id == int(params["doctor_id"]),
                Appointment.appointment_date >= today,
                Appointment.appointment_date <= horizon,
                Appointment.status.in_(_ACTIVE),
            )
            .count()
        )
        assumptions = {"reschedule_rate": 0.8, "wait_rate": 0.15, "cancel_rate": 0.05}
        return {
            "assumptions": assumptions,
            "affected_counts": {"upcoming_appointments": upcoming},
            "outputs": {
                "rescheduled": round(upcoming * assumptions["reschedule_rate"]),
                "kept_waiting": round(upcoming * assumptions["wait_rate"]),
                "cancelled": round(upcoming * assumptions["cancel_rate"]),
            },
        }
    if stype == "reschedule":
        shift = int(params["shift_days"])
        horizon = today + timedelta(days=30)
        upcoming = (
            db.query(Appointment)
            .filter(
                Appointment.appointment_date >= today,
                Appointment.appointment_date <= horizon,
                Appointment.status.in_(_ACTIVE),
            )
            .count()
        )
        assumptions = {"shift_days": shift, "conflict_rate": 0.1}
        return {
            "assumptions": assumptions,
            "affected_counts": {"upcoming_appointments": upcoming},
            "outputs": {
                "moved": round(upcoming * 0.9),
                "conflicts_needing_review": round(upcoming * assumptions["conflict_rate"]),
            },
        }
    # followup_disruption
    horizon = today + timedelta(days=int(params["days"]))
    due = (
        db.query(FollowUp)
        .filter(
            FollowUp.follow_up_date >= today,
            FollowUp.follow_up_date <= horizon,
            FollowUp.status == "PENDING",
        )
        .count()
    )
    assumptions = {"reschedule_rate": 0.7, "missed_rate": 0.3}
    return {
        "assumptions": assumptions,
        "affected_counts": {"follow_ups_due": due},
        "outputs": {
            "rescheduled": round(due * assumptions["reschedule_rate"]),
            "at_risk_of_missed": round(due * assumptions["missed_rate"]),
        },
    }


@mcp_tool(mcp, SERVER, "validate_scenario_inputs")
def validate_scenario_inputs(scenario: dict, principal: dict | None = None,
                             audit_correlation_id: str = "") -> dict:
    """Validate scenario inputs before simulation (synthetic data only)."""
    validated = _validate(scenario)
    return {"valid": True, **validated}


@mcp_tool(mcp, SERVER, "simulate_scenario")
def simulate_scenario(scenario: dict, principal: dict | None = None,
                      audit_correlation_id: str = "") -> dict:
    """Simulate an operational decision - synthetic results, live data untouched."""
    db = SessionLocal()
    try:
        validated = _validate(scenario)
        result = _simulate(db, validated)
        run = ScenarioRun(
            scenario_type=validated["scenario_type"],
            assumptions=result["assumptions"],
            inputs=validated["params"],
            outputs=result["outputs"],
            affected_counts=result["affected_counts"],
            is_synthetic=True,
            created_by=(principal or {}).get("email"),
        )
        db.add(run)
        db.commit()
        return {
            "run_id": run.id,
            "is_synthetic": True,
            "assumptions": result["assumptions"],
            "affected_counts": result["affected_counts"],
            "outputs": result["outputs"],
            "note": "Simulated results are not real patient facts.",
        }
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "compare_outcomes")
def compare_outcomes(scenario_a: dict, scenario_b: dict,
                     principal: dict | None = None,
                     audit_correlation_id: str = "") -> dict:
    """Run two scenarios and compare their outcomes side by side."""
    db = SessionLocal()
    try:
        a = _validate(scenario_a)
        b = _validate(scenario_b)
        ra = _simulate(db, a)
        rb = _simulate(db, b)
        return {
            "scenario_a": {"type": a["scenario_type"], **ra},
            "scenario_b": {"type": b["scenario_type"], **rb},
            "comparison": {
                "affected_a": sum(ra["affected_counts"].values()),
                "affected_b": sum(rb["affected_counts"].values()),
            },
            "note": "Simulated results are not real patient facts.",
        }
    finally:
        db.close()


@mcp_tool(mcp, SERVER, "explain_assumptions")
def explain_assumptions(run_id: int, principal: dict | None = None,
                        audit_correlation_id: str = "") -> dict:
    """Explain the assumptions behind a stored scenario run."""
    db = SessionLocal()
    try:
        run = db.get(ScenarioRun, run_id)
        if run is None:
            raise ControlledError("NOT_FOUND", "scenario run not found")
        return {
            "run_id": run.id,
            "scenario_type": run.scenario_type,
            "is_synthetic": run.is_synthetic,
            "assumptions": run.assumptions,
            "explanation": (
                "All rates are explicit planning assumptions applied to aggregate "
                "counts only; no live appointment, prescription or patient record "
                "was read row-by-row or modified."
            ),
        }
    finally:
        db.close()


if __name__ == "__main__":
    serve(SERVER, mcp)
