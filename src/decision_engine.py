"""
decision_engine.py
--------------------
Decision Support Module V1.

Converts the ML pipeline's saved forecast outputs into plain-language,
factory-manager-facing recommendations. This is a deliberately simple,
fully transparent RULE-BASED engine — not an LLM, not a new model, and
it does not read raw sensor data or retrain anything. It only reads the
same per-machine numbers already sitting in
`results/machine_status_summary.csv` (current_energy,
predicted_24h_avg_energy, predicted_24h_max_energy, regression_rmse)
and applies a fixed set of if/else thresholds.

Why rule-based first: every threshold here is a plain number a factory
manager can question, verify, and adjust ("why is High priority set at
4.75?") - there is nothing to "trust" beyond arithmetic. This is meant
as the transparent baseline a future LLM-based or optimization-based
decision layer would need to beat, not the final decision system.

Public functions:
    generate_decision_summary(machine_row) -> dict
        One machine in, one recommendation dict out.

    generate_fleet_insights(summary_df) -> dict
        Runs generate_decision_summary for every machine and rolls the
        results up into fleet-wide highlights ("which machine is most
        urgent", "how many machines are High priority", etc).
"""

import pandas as pd

# ---------------------------------------------------------------------
# Thresholds - all named constants so they are easy to find, question,
# and change without hunting through logic.
# ---------------------------------------------------------------------

TREND_INCREASE_RATIO = 1.10   # predicted_avg > current * 1.10 -> Increasing
TREND_DECREASE_RATIO = 0.90   # predicted_avg < current * 0.90 -> Decreasing

RMSE_HIGH_QUALITY_MAX = 0.33   # RMSE <= this -> forecast_quality = High
RMSE_MEDIUM_QUALITY_MAX = 0.40  # RMSE <= this -> forecast_quality = Medium
                                 # else -> Low

PRIORITY_HIGH_MIN = 4.75    # predicted_24h_max_energy >= this -> High priority
PRIORITY_MEDIUM_MIN = 4.50  # predicted_24h_max_energy >= this -> Medium priority
                              # else -> Low priority


# ---------------------------------------------------------------------
# Step-by-step rule functions (kept separate so each rule can be tested
# / explained on its own)
# ---------------------------------------------------------------------

def _compute_trend(current_energy: float, predicted_24h_avg_energy: float) -> tuple:
    """
    Returns (trend_direction, energy_change_pct).

    energy_change_pct is signed: positive = energy expected to rise,
    negative = expected to fall. Guards against current_energy == 0
    (would otherwise be a division by zero) by falling back to a 0%
    change label - this is a data edge case, not expected in normal
    operation, but should never crash the dashboard.
    """
    if current_energy == 0:
        return "Stable", 0.0

    energy_change_pct = (predicted_24h_avg_energy - current_energy) / current_energy * 100

    if predicted_24h_avg_energy > current_energy * TREND_INCREASE_RATIO:
        trend_direction = "Increasing"
    elif predicted_24h_avg_energy < current_energy * TREND_DECREASE_RATIO:
        trend_direction = "Decreasing"
    else:
        trend_direction = "Stable"

    return trend_direction, energy_change_pct


def _compute_forecast_quality(regression_rmse: float) -> str:
    """Lower RMSE = more trustworthy forecast for this specific machine."""
    if regression_rmse <= RMSE_HIGH_QUALITY_MAX:
        return "High"
    elif regression_rmse <= RMSE_MEDIUM_QUALITY_MAX:
        return "Medium"
    else:
        return "Low"


def _compute_priority(predicted_24h_max_energy: float) -> str:
    """Priority is driven by how high the predicted peak energy is expected to reach."""
    if predicted_24h_max_energy >= PRIORITY_HIGH_MIN:
        return "High"
    elif predicted_24h_max_energy >= PRIORITY_MEDIUM_MIN:
        return "Medium"
    else:
        return "Low"


def _build_recommendation(trend_direction: str, priority_level: str) -> tuple:
    """
    Returns (recommendation_title, suggested_action).

    Decreasing trend takes precedence over the priority-based message,
    even if predicted peak energy is technically still high - a machine
    that is winding down is a maintenance opportunity, not an energy
    concern, regardless of what its peak looked like going in.
    """
    if trend_direction == "Decreasing":
        return (
            "Energy demand expected to decrease",
            "This may be a good window for inspection or light maintenance.",
        )
    elif priority_level == "High":
        return (
            "High future energy peak expected",
            "Review machine workload and avoid stacking high-load operations.",
        )
    elif priority_level == "Medium":
        return (
            "Moderate energy increase expected",
            "Monitor this machine during the next production window.",
        )
    else:
        return (
            "No major energy concern detected",
            "Continue normal operation.",
        )


def _build_confidence_note(forecast_quality: str) -> str:
    """A plain-language caveat tied directly to forecast_quality, so the
    recommendation never gets presented with more confidence than the
    underlying forecast actually supports."""
    if forecast_quality == "Low":
        return (
            "Forecast quality for this machine is LOW (high RMSE). "
            "This recommendation should be reviewed manually before acting on it."
        )
    elif forecast_quality == "Medium":
        return (
            "Forecast quality for this machine is MODERATE. "
            "Treat this recommendation as directional guidance, not a precise figure."
        )
    else:
        return (
            "Forecast quality for this machine is HIGH. "
            "This recommendation can be used with reasonable confidence."
        )


def _build_recommendation_text(
    machine_id: str, trend_direction: str, energy_change_pct: float,
    predicted_24h_max_energy: float, forecast_quality: str,
) -> str:
    """One-paragraph plain-language summary combining the numbers, for
    display under the title/action in the UI."""
    trend_phrase = {
        "Increasing": "increase",
        "Decreasing": "decrease",
        "Stable": "stay roughly stable",
    }[trend_direction]

    return (
        f"{machine_id} is forecast to {trend_phrase} over the next 24 hours "
        f"({energy_change_pct:+.1f}% average change), with a predicted peak of "
        f"{predicted_24h_max_energy:.2f}. Forecast reliability for this machine is "
        f"{forecast_quality.lower()} (see confidence note)."
    )


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def generate_decision_summary(machine_row) -> dict:
    """
    Converts one row of machine_status_summary.csv into a decision
    summary dictionary.

    Parameters
    ----------
    machine_row : pd.Series or dict
        Must contain: machine_id, current_energy, predicted_24h_avg_energy,
        predicted_24h_max_energy, regression_rmse.

    Returns
    -------
    dict with keys: machine_id, trend_direction, energy_change_pct,
    forecast_quality, priority_level, recommendation_title,
    recommendation_text, suggested_action, confidence_note.
    """
    machine_id = machine_row["machine_id"]
    current_energy = float(machine_row["current_energy"])
    predicted_24h_avg_energy = float(machine_row["predicted_24h_avg_energy"])
    predicted_24h_max_energy = float(machine_row["predicted_24h_max_energy"])
    regression_rmse = float(machine_row["regression_rmse"])

    trend_direction, energy_change_pct = _compute_trend(current_energy, predicted_24h_avg_energy)
    forecast_quality = _compute_forecast_quality(regression_rmse)
    priority_level = _compute_priority(predicted_24h_max_energy)

    recommendation_title, suggested_action = _build_recommendation(trend_direction, priority_level)
    recommendation_text = _build_recommendation_text(
        machine_id, trend_direction, energy_change_pct, predicted_24h_max_energy, forecast_quality,
    )
    confidence_note = _build_confidence_note(forecast_quality)

    return {
        "machine_id": machine_id,
        "trend_direction": trend_direction,
        "energy_change_pct": round(energy_change_pct, 2),
        "forecast_quality": forecast_quality,
        "priority_level": priority_level,
        "recommendation_title": recommendation_title,
        "recommendation_text": recommendation_text,
        "suggested_action": suggested_action,
        "confidence_note": confidence_note,
    }


def generate_fleet_insights(summary_df: pd.DataFrame) -> dict:
    """
    Runs generate_decision_summary for every machine in the fleet and
    rolls the results up into a small set of headline insights for the
    "Factory Insights" panel.

    Returns
    -------
    dict with keys:
        highest_peak_machine, highest_peak_value
        largest_increase_machine, largest_increase_pct
        most_reliable_machine, most_reliable_rmse
        high_priority_count
    """
    all_decisions = [generate_decision_summary(row) for _, row in summary_df.iterrows()]
    decisions_df = pd.DataFrame(all_decisions)

    highest_peak_row = summary_df.loc[summary_df["predicted_24h_max_energy"].idxmax()]
    largest_increase_row = decisions_df.loc[decisions_df["energy_change_pct"].idxmax()]
    most_reliable_row = summary_df.loc[summary_df["regression_rmse"].idxmin()]
    high_priority_count = int((decisions_df["priority_level"] == "High").sum())

    return {
        "highest_peak_machine": highest_peak_row["machine_id"],
        "highest_peak_value": round(float(highest_peak_row["predicted_24h_max_energy"]), 2),
        "largest_increase_machine": largest_increase_row["machine_id"],
        "largest_increase_pct": round(float(largest_increase_row["energy_change_pct"]), 2),
        "most_reliable_machine": most_reliable_row["machine_id"],
        "most_reliable_rmse": round(float(most_reliable_row["regression_rmse"]), 3),
        "high_priority_count": high_priority_count,
    }
