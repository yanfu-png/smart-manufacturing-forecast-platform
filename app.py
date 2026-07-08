"""
app.py
------
Smart Manufacturing Forecasting — Dashboard V4.1 (UI/UX bug-fix + polish)

PRESENTATION LAYER ONLY. Does not train models, does not call any ML
pipeline code, and does not modify any results files. Reads three
files already produced by the forecasting pipeline:

    results/machine_status_summary.csv        - latest snapshot, 1 row/machine
    results/dashboard_forecast_predictions.csv - full test-period actual vs predicted history (hourly)
    results/dashboard_metrics.json             - fleet-wide aggregate model quality metrics

V4.1 fixes (see README_dashboard.md for the full changelog):
  1. The Historical Timeline slider is now the true single source of
     truth for every timestamp-dependent section on the page (KPIs,
     Factory Insights, machine cards, ranking tables, Machine Detail,
     Decision Support, forecast chart marker). Fixed by reading the
     slider's session_state value BEFORE anything else renders, and
     only drawing the slider widget itself at the bottom of the page
     (see "Historical Timeline" section) - Streamlit widgets read their
     own session_state key on every rerun regardless of where in the
     script they are drawn, so this lets one widget at the bottom drive
     everything above it.
  2. The Historical Timeline panel itself is now compact and lives at
     the bottom of the page instead of dominating the top.
  3. Machine cards no longer use the fragile invisible-button/absolute-
     overlay click hack. Cards render in normal document flow with a
     real, visible "View Detail →" button.
  4. Ranking panels are single self-contained HTML blocks (title +
     subtitle + table together) so borders/padding can never separate
     from their content.

Run with:
    streamlit run app.py
"""

import json
import os
import re
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.decision_engine import (
    generate_decision_summary,
    generate_fleet_insights,
    TREND_INCREASE_RATIO,
    TREND_DECREASE_RATIO,
)

# ---------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------

st.set_page_config(
    page_title="Smart Manufacturing — Forecast Intelligence Platform",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

RESULTS_DIR = "results"

# ---------------------------------------------------------------------
# Unified color system
# ---------------------------------------------------------------------

COLOR_BG = "#0B0F17"
COLOR_PANEL = "#151B26"
COLOR_BORDER = "#2B3548"
COLOR_PRIMARY = "#4EA1FF"
COLOR_TEXT = "#F3F4F6"
COLOR_MUTED = "#A0A7B5"
COLOR_WARNING = "#F59E0B"
COLOR_CRITICAL = "#C96257"
COLOR_HEALTHY = "#3FB87F"

STATUS_COLORS = {"Normal": COLOR_HEALTHY, "Warning": COLOR_WARNING, "Critical": COLOR_CRITICAL}
PRIORITY_COLORS = {"High": COLOR_CRITICAL, "Medium": COLOR_WARNING, "Low": COLOR_HEALTHY}
CARD_HEIGHT_PX = 216
PANEL_MARKER = "sm-panel-marker"


# ---------------------------------------------------------------------
# Theme / CSS
# ---------------------------------------------------------------------


def inject_css():
    st.markdown(
        f"""
        <style>
        .stApp {{ background-color: {COLOR_BG}; color: {COLOR_TEXT}; }}
        div.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1360px; }}
        * {{ transition: border-color 150ms ease, box-shadow 150ms ease, background-color 150ms ease; }}

        /* =========================================================
           TYPOGRAPHY SYSTEM
           ========================================================= */
        .sm-section-title {{
            font-size: 28px; font-weight: 700; color: {COLOR_TEXT};
            letter-spacing: -0.01em; margin: 0 0 6px 0;
        }}
        .sm-section-subtitle {{
            font-size: 15px; color: {COLOR_MUTED}; margin: 0 0 20px 0; line-height: 1.5;
        }}
        .sm-card-label {{
            font-size: 11px; color: {COLOR_MUTED}; text-transform: uppercase;
            letter-spacing: 0.08em; font-weight: 600;
        }}
        .sm-metric-value {{
            font-size: 44px; font-weight: 700; color: {COLOR_TEXT}; letter-spacing: -0.02em; line-height: 1.05;
        }}
        .sm-machine-name {{ font-size: 20px; font-weight: 700; color: {COLOR_TEXT}; }}

        /* =========================================================
           PREMIUM PANEL SYSTEM — every major section shares this
           exact styling via a small invisible marker + :has(), so no
           section-rendering logic below has to change to get it.
           ========================================================= */
        div[data-testid="stVerticalBlock"]:has(
            > div[data-testid="stElementContainer"] > div[data-testid="stMarkdown"] .{PANEL_MARKER}
        ) {{
            background: {COLOR_PANEL};
            border: 1px solid {COLOR_BORDER};
            border-radius: 16px;
            padding: 28px 28px 24px 28px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.24), 0 8px 24px rgba(0,0,0,0.18);
            margin-bottom: 40px;
        }}
        .{PANEL_MARKER} {{ display: none; }}

        /* ---- Hero header ---- */
        .hero-panel {{
            background: linear-gradient(135deg, {COLOR_PANEL} 0%, #10151f 100%);
            border: 1px solid {COLOR_BORDER};
            border-top: 3px solid {COLOR_PRIMARY};
            border-radius: 16px;
            padding: 36px 40px;
        }}
        .hero-eyebrow {{
            font-size: 12.5px; color: {COLOR_PRIMARY}; letter-spacing: 0.22em;
            text-transform: uppercase; font-weight: 800; margin-bottom: 8px;
        }}
        .hero-title {{
            font-size: 40px; font-weight: 800; color: {COLOR_TEXT}; line-height: 1.12; letter-spacing: -0.02em;
        }}
        .hero-subtitle {{ font-size: 15.5px; color: {COLOR_MUTED}; margin-top: 12px; max-width: 620px; line-height: 1.55; }}
        .hero-meta {{ text-align: right; font-size: 12.5px; color: {COLOR_MUTED}; line-height: 1.8; white-space: nowrap; }}
        .hero-meta b {{ color: {COLOR_TEXT}; }}
        .status-chip {{
            display: inline-block; background: #1b2333; border: 1px solid {COLOR_BORDER};
            color: {COLOR_MUTED}; border-radius: 999px; padding: 5px 14px; font-size: 12px;
            margin-right: 8px; margin-top: 20px;
        }}
        .status-chip b {{ color: {COLOR_TEXT}; }}

        /* ---- KPI cards ---- */
        .metric-card {{
            background: #10151f; border: 1px solid {COLOR_BORDER}; border-radius: 14px;
            padding: 20px 22px; height: 100%;
        }}
        .metric-card:hover {{ border-color: {COLOR_PRIMARY}; box-shadow: 0 4px 16px rgba(78,161,255,0.12); }}
        .metric-label {{
            font-size: 11px; color: {COLOR_MUTED}; text-transform: uppercase;
            letter-spacing: 0.08em; margin-bottom: 10px; font-weight: 600;
        }}
        .metric-value {{ font-size: 34px; font-weight: 700; color: {COLOR_TEXT}; letter-spacing: -0.02em; }}
        .info-note {{ color: {COLOR_MUTED}; font-size: 12.5px; line-height: 1.5; }}

        /* ---- Section titles (legacy class kept for any stray references) ---- */
        .section-title {{
            font-size: 28px; font-weight: 700; color: {COLOR_TEXT};
            letter-spacing: -0.01em; margin: 0 0 6px 0; border-left: none; padding-left: 0;
        }}
        .section-subtitle {{ font-size: 15px; color: {COLOR_MUTED}; margin: 0 0 20px 0; line-height: 1.5; }}

        /* ---- Machine cards ---- */
        .machine-card-wrap {{ position: relative; cursor: pointer; }}
        .machine-card {{
            background: #10151f;
            border: 1px solid {COLOR_BORDER};
            border-left: 3px solid #444;
            border-radius: 14px;
            padding: 16px 14px;
            height: {CARD_HEIGHT_PX}px;
            display: flex;
            flex-direction: column;
            box-sizing: border-box;
            overflow: hidden;
        }}
        .machine-card-wrap:hover .machine-card {{
            border-color: {COLOR_PRIMARY};
            box-shadow: 0 6px 20px rgba(78,161,255,0.16);
            transform: translateY(-1px);
        }}
        .machine-card.selected {{
            box-shadow: 0 0 0 2px {COLOR_PRIMARY}, 0 8px 24px rgba(78,161,255,0.28);
            border-left-color: {COLOR_PRIMARY} !important;
            border-left-width: 4px;
        }}
        .machine-card-header {{
            display: flex; justify-content: space-between; align-items: center;
            gap: 6px; margin-bottom: 12px; min-height: 24px;
        }}
        .machine-id {{
            font-size: 15px; font-weight: 700; color: {COLOR_TEXT};
            overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
            flex: 1 1 auto; min-width: 0;
        }}
        .status-pill-small {{
            display: inline-block; padding: 3px 8px; border-radius: 999px;
            font-size: 9.5px; font-weight: 700; color: {COLOR_BG}; opacity: 0.92;
            flex-shrink: 0; white-space: nowrap;
        }}
        .primary-metric-label {{
            font-size: 10.5px; color: {COLOR_MUTED}; text-transform: uppercase; letter-spacing: 0.06em;
            white-space: nowrap;
        }}
        .primary-metric {{
            font-size: 24px; font-weight: 700; color: {COLOR_PRIMARY}; line-height: 1.2; margin: 3px 0 6px 0;
        }}
        .trend-indicator {{ font-size: 12px; font-weight: 700; margin-bottom: 10px; }}
        .machine-row {{
            font-size: 12px; color: #c2c8d4; display: flex; justify-content: space-between; margin-top: 4px;
        }}
        .machine-row .muted-value {{ color: {COLOR_MUTED}; }}
        .machine-card-spacer {{ flex: 1 1 auto; }}

        /* Secondary "View Detail" affordance - the whole card is clickable
           (see machine-card-wrap onclick), this stays as a small, clearly
           secondary text link rather than a competing full-width button. */
        div[data-testid="stButton"] button {{
            background: transparent;
            border: none;
            color: {COLOR_PRIMARY};
            font-size: 12px;
            font-weight: 600;
            padding: 4px 0;
            width: 100%;
            text-align: right;
            margin-top: 2px;
        }}
        div[data-testid="stButton"] button:hover {{ color: {COLOR_TEXT}; text-decoration: underline; }}

        /* ---- Decision Support ---- */
        .decision-card {{
            background: #10151f; border-radius: 14px; padding: 22px 24px;
            border-left: 4px solid {COLOR_PRIMARY}; border-top: 1px solid {COLOR_BORDER};
            border-right: 1px solid {COLOR_BORDER}; border-bottom: 1px solid {COLOR_BORDER};
        }}
        .decision-title {{ font-size: 19px; font-weight: 700; color: {COLOR_TEXT}; margin-bottom: 16px; }}
        .decision-field-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px 32px; margin-bottom: 6px; }}
        .decision-field-label {{
            font-size: 11px; color: {COLOR_MUTED}; text-transform: uppercase;
            letter-spacing: 0.06em; margin-bottom: 5px; font-weight: 600;
        }}
        .decision-field-value {{ font-size: 14px; color: {COLOR_TEXT}; line-height: 1.5; }}
        .priority-pill {{
            display: inline-block; padding: 3px 12px; border-radius: 999px;
            font-size: 11px; font-weight: 700; color: {COLOR_BG};
        }}
        .decision-confidence {{ font-size: 12px; color: {COLOR_MUTED}; margin-top: 16px; font-style: italic; }}
        .caveat-box {{
            background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.28); border-radius: 10px;
            padding: 11px 14px; font-size: 12.5px; color: #e0c589; margin-top: 14px;
        }}
        .interpretation-box {{
            background: #0e1420; border-left: 3px solid {COLOR_PRIMARY}; border-radius: 8px;
            padding: 14px 16px; font-size: 13.5px; color: #c9cfdb; margin-top: 14px; line-height: 1.6;
        }}

        /* ---- Factory Insights cards ---- */
        .insight-card {{
            background: #10151f; border-radius: 14px; padding: 20px 22px;
            border: 1px solid {COLOR_BORDER}; border-top: 2px solid {COLOR_PRIMARY};
            height: 120px; display: flex; flex-direction: column; justify-content: center;
        }}
        .insight-card:hover {{ border-color: {COLOR_PRIMARY}; box-shadow: 0 6px 20px rgba(78,161,255,0.14); }}
        .insight-label {{
            font-size: 11px; color: {COLOR_MUTED}; text-transform: uppercase;
            letter-spacing: 0.07em; margin-bottom: 8px; font-weight: 600;
        }}
        .insight-value {{ font-size: 26px; font-weight: 800; color: {COLOR_TEXT}; line-height: 1.1; letter-spacing: -0.01em; }}
        .insight-subvalue {{ font-size: 13px; color: {COLOR_PRIMARY}; margin-top: 6px; }}

        /* ---- Ranking panels ---- */
        .ranking-panel {{
            background: #10151f; border: 1px solid {COLOR_BORDER}; border-radius: 14px;
            padding: 22px 24px; min-height: 300px; display: flex; flex-direction: column;
        }}
        .ranking-panel:hover {{ border-color: {COLOR_PRIMARY}; }}
        .ranking-title {{ font-size: 16px; font-weight: 700; color: {COLOR_TEXT}; margin-bottom: 4px; }}
        .ranking-subtitle {{ font-size: 12px; color: {COLOR_MUTED}; margin-bottom: 18px; line-height: 1.45; }}
        .dark-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        .dark-table th {{
            color: {COLOR_MUTED}; text-transform: uppercase; font-weight: 600;
            font-size: 10.5px; letter-spacing: 0.05em; text-align: right; padding: 8px 6px;
            border-bottom: 1px solid {COLOR_BORDER};
        }}
        .dark-table th:first-child, .dark-table td:first-child {{ text-align: left; }}
        .dark-table td {{
            color: {COLOR_TEXT}; text-align: right; padding: 9px 6px;
            border-bottom: 1px solid #1c2330;
        }}
        .dark-table tr:last-child td {{ border-bottom: none; }}
        .dark-table tbody tr:hover td {{ background: rgba(78,161,255,0.06); }}
        .pct-positive {{ color: {COLOR_WARNING}; }}
        .pct-negative {{ color: {COLOR_HEALTHY}; }}

        /* ---- Historical Timeline (bottom of page) — Apple/Linear-style
           slider redesign. Streamlit's default select_slider renders its
           entire track as one uniformly-colored bar (there is no native
           two-tone "traveled vs remaining" fill in this version) - to get
           a real progress effect, a small script recomputes a CSS
           gradient on the track using the thumb's ARIA value attributes
           (see inject_timeline_style_script()). Everything below is
           presentation only; the slider's key/options/on-change
           behavior is completely untouched. ---- */
        .timeline-panel {{
            background: #10151f; border: 1px solid {COLOR_BORDER}; border-radius: 12px;
            padding: 28px 24px 16px 24px;
        }}
        .timeline-bounds-row {{
            display: flex; justify-content: space-between; margin-top: 10px;
            font-size: 12px; color: {COLOR_MUTED};
        }}
        .timeline-footer-row {{
            margin-top: 14px; padding-top: 12px; border-top: 1px solid {COLOR_BORDER};
            font-size: 13px; color: {COLOR_MUTED}; text-align: center;
        }}

        /* Hide Streamlit's default tick-bar labels and thumb-value bubble
           entirely - replaced by our own centered label (via the script)
           and our own boundary row (timeline-bounds-row) above. */
        [data-testid="stSliderTickBar"] {{ display: none !important; }}

        div[data-baseweb="slider"] {{ padding-top: 28px !important; padding-bottom: 4px !important; }}

        /* Track: thin, dark gray. The fill color is applied dynamically
           as an inline gradient by the injected script, so no blue is
           hard-coded here - only the base (fully "remaining") look. */
        div[data-baseweb="slider"] div[style*="height: 0.25rem"],
        div[data-baseweb="slider"] div[style*="linear-gradient"],
        div[data-baseweb="slider"] div[style*="background-color: rgb(255"] {{
            background: #3A4254 !important;
            height: 5px !important;
            border-radius: 999px !important;
        }}

        /* Thumb: circular, blue, soft glow - premium look instead of the
           default flat BaseWeb handle. */
        div[data-baseweb="slider"] [role="slider"] {{
            background-color: {COLOR_PRIMARY} !important;
            border: 2px solid #ffffff !important;
            width: 20px !important; height: 20px !important;
            box-shadow: 0 0 0 6px rgba(78, 161, 255, 0.22), 0 2px 6px rgba(0,0,0,0.35) !important;
        }}

        /* Large centered timestamp label above the thumb. Streamlit's
           built-in "current value" bubble already auto-centers itself
           above the thumb and tracks it as it moves - far more robust
           than reimplementing that positioning by hand - so it is kept
           and simply restyled to look like a plain floating label
           instead of a small tooltip pill (no background/border/pill
           shape, larger semibold white text). */
        [data-testid="stSliderThumbValue"] {{
            background: transparent !important;
            border: none !important;
            padding: 0 !important;
            color: #ffffff !important;
            font-size: 16px !important;
            font-weight: 600 !important;
        }}

        /* Machine Detail + Decision Support should read as one visual
           unit within the same panel; a light internal divider helps
           separate the chart column from the summary column without a
           second nested panel. */
        hr {{ border-color: {COLOR_BORDER}; opacity: 0.5; margin: 40px 0; }}
        </style>
        """,
        unsafe_allow_html=True,
    )



# ---------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------

@st.cache_data
def load_data():
    """Loads all three pipeline output files. Cached; does not recompute anything."""
    summary = pd.read_csv(os.path.join(RESULTS_DIR, "machine_status_summary.csv"))
    predictions = pd.read_csv(os.path.join(RESULTS_DIR, "dashboard_forecast_predictions.csv"))
    predictions["timestamp"] = pd.to_datetime(predictions["timestamp"])
    with open(os.path.join(RESULTS_DIR, "dashboard_metrics.json")) as f:
        metrics = json.load(f)
    return summary, predictions, metrics


def format_timestamp(raw_ts) -> str:
    """'2025-03-10 10:00:00' -> 'Mar 10, 2025 · 10:00' (single clean line)."""
    ts = pd.to_datetime(raw_ts)
    return ts.strftime("%b %d, %Y · %H:%M")


def _extract_machine_number(machine_id: str) -> int:
    """'machine_12' -> 12. Used only to sort machine_ids numerically for
    the display-name mapping below (a plain string sort would put
    'machine_12' before 'machine_2', which looks wrong to a viewer)."""
    match = re.search(r"(\d+)", str(machine_id))
    return int(match.group(1)) if match else 0


def build_machine_display_map(machine_ids) -> dict:
    """
    Deterministic, stable machine_id -> display-name mapping, e.g.
    'machine_2' -> 'Production Unit 01'. This is PRESENTATION ONLY:
    every filter, join, session_state value, chart query, and CSV lookup
    in this app continues to use the raw machine_id internally, exactly
    as before - only what a viewer sees on screen changes.

    machine_ids are sorted numerically (by the number after "machine_"),
    not alphabetically, so the assigned unit numbers read in the order a
    person would expect.
    """
    sorted_ids = sorted(machine_ids, key=_extract_machine_number)
    return {mid: f"Production Unit {i + 1:02d}" for i, mid in enumerate(sorted_ids)}


def get_display_name(machine_id: str) -> str:
    """Raw machine_id -> clean display name. Falls back to the raw id
    itself if it's ever missing from the map, so this never crashes or
    silently hides a machine."""
    return MACHINE_DISPLAY_MAP.get(machine_id, machine_id)


def get_short_display_name(machine_id: str) -> str:
    """
    Compact form ('Unit 19') used ONLY inside the Factory Overview cards,
    where six cards share one row and the full 'Production Unit 19'
    label would overflow the available width no matter how the internal
    card spacing is tuned (verified: the full label is roughly twice as
    wide as the space available per card at 6-across). Every other
    section (Factory Insights, Rankings, Machine Detail, dropdown,
    Decision Support) still shows the full 'Production Unit NN' name -
    this short form exists purely so the card grid never clips text,
    while the full name a viewer would actually reference stays
    consistent everywhere else. Both forms share the same unit number,
    so there is no ambiguity between them.
    """
    full_name = get_display_name(machine_id)
    return full_name.replace("Production ", "") if full_name.startswith("Production ") else full_name


def get_machine_id_from_display(display_name: str) -> str:
    """Reverse lookup, provided for completeness / future use. The
    dropdown in Machine Detail does not actually need this - Streamlit's
    selectbox keeps the underlying value as the raw machine_id and only
    uses format_func for the label - but a direct display-name -> id
    lookup is included here in case any future UI element needs it."""
    return MACHINE_ID_FROM_DISPLAY.get(display_name, display_name)


@st.cache_data
def get_common_timestamps(predictions: pd.DataFrame) -> list:
    """
    Timestamps present for EVERY machine (each machine's test period
    starts/ends a few hours apart because slightly different missing-value
    counts shift each machine's 70/30 split point). Restricting the
    Historical Timeline slider to this intersection guarantees every
    snapshot below is fully defined for all 34 machines at any slider
    position.
    """
    ts_sets = predictions.groupby("machine_id")["timestamp"].apply(set)
    common = set.intersection(*ts_sets)
    return sorted(common)


def get_timestamp_snapshot(predictions_df: pd.DataFrame, summary_df: pd.DataFrame, selected_timestamp) -> pd.DataFrame:
    """
    THE single source of truth for every timestamp-dependent value shown
    anywhere on the page. Returns one row per machine, as of
    `selected_timestamp`:

        machine_id, selected_timestamp, current_energy,
        predicted_24h_avg_energy, predicted_24h_max_energy,
        regression_rmse, predicted_status, energy_change_pct,
        trend_direction

    - current_energy / predicted_24h_avg_energy / predicted_24h_max_energy
      come from dashboard_forecast_predictions.csv AT the selected hour.
    - predicted_24h_max_energy falls back to the latest machine-level
      value from machine_status_summary.csv if it's missing for that
      exact hour (defensive; in practice every common timestamp has it).
    - regression_rmse and predicted_status are carried over from the
      latest machine_status_summary.csv row, since those are fixed
      per-machine model-quality metrics, not hourly quantities.
    - energy_change_pct / trend_direction are computed here directly
      (using the SAME thresholds as src/decision_engine.py, imported
      rather than duplicated) so cards/tables can use them without
      calling the decision engine.
    """
    at_ts = predictions_df[predictions_df["timestamp"] == selected_timestamp].copy()

    snapshot = at_ts.rename(columns={"actual_24h_avg_energy": "current_energy"})[
        ["machine_id", "current_energy", "predicted_24h_avg_energy", "predicted_24h_max_energy"]
    ]

    static_cols = summary_df[["machine_id", "regression_rmse", "classification_f1",
                               "predicted_status", "predicted_24h_max_energy"]]
    static_cols = static_cols.rename(columns={"predicted_24h_max_energy": "_latest_predicted_max"})

    snapshot = snapshot.merge(static_cols, on="machine_id", how="left")
    snapshot["predicted_24h_max_energy"] = snapshot["predicted_24h_max_energy"].fillna(snapshot["_latest_predicted_max"])
    snapshot = snapshot.drop(columns=["_latest_predicted_max"])

    snapshot["selected_timestamp"] = selected_timestamp

    safe_current = snapshot["current_energy"].replace(0, np.nan)
    snapshot["energy_change_pct"] = (
        (snapshot["predicted_24h_avg_energy"] - snapshot["current_energy"]) / safe_current * 100
    ).fillna(0.0)

    def _trend(row):
        if row["current_energy"] == 0:
            return "Stable"
        if row["predicted_24h_avg_energy"] > row["current_energy"] * TREND_INCREASE_RATIO:
            return "Increasing"
        elif row["predicted_24h_avg_energy"] < row["current_energy"] * TREND_DECREASE_RATIO:
            return "Decreasing"
        return "Stable"

    snapshot["trend_direction"] = snapshot.apply(_trend, axis=1)

    return snapshot


def trend_arrow_html(trend_direction: str) -> str:
    """Small visual trend indicator matching trend_direction already computed in the snapshot."""
    if trend_direction == "Increasing":
        return f'<span style="color:{COLOR_WARNING};">↑ Increasing</span>'
    elif trend_direction == "Decreasing":
        return f'<span style="color:{COLOR_HEALTHY};">↓ Decreasing</span>'
    else:
        return f'<span style="color:{COLOR_MUTED};">→ Stable</span>'


def build_cause_text(decision: dict) -> str:
    """Short, structured 'why' phrase for the Decision Support panel, built
    entirely from the decision dict's own fields (presentation logic only)."""
    reasons = []
    if decision["priority_level"] == "High":
        reasons.append("predicted peak energy is high")
    elif decision["priority_level"] == "Medium":
        reasons.append("predicted peak energy is moderately elevated")

    if decision["trend_direction"] == "Increasing":
        reasons.append("energy demand is trending upward")
    elif decision["trend_direction"] == "Decreasing":
        reasons.append("energy demand is trending downward")

    if decision["forecast_quality"] == "Low":
        reasons.append("forecast reliability for this machine is low")

    if not reasons:
        reasons.append("no significant risk factors detected")

    return "; ".join(reasons).capitalize() + "."


# ---------------------------------------------------------------------
# Small render helpers
# ---------------------------------------------------------------------

def status_pill(status: str) -> str:
    color = STATUS_COLORS.get(status, "#999")
    return f'<span class="status-pill-small" style="background:{color};">{status}</span>'


def render_kpi_card(label: str, value: str):
    st.markdown(
        f'<div class="metric-card"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div></div>',
        unsafe_allow_html=True,
    )


def render_header(selected_ts, n_machines: int):
    """Product-style hero header (refined for stronger hierarchy in V4.1)."""
    st.markdown(
        f"""
        <div class="hero-panel">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:16px;">
                <div>
                    <div class="hero-eyebrow">SMART MANUFACTURING</div>
                    <div class="hero-title">Forecast Intelligence Platform</div>
                    <div class="hero-subtitle">
                        AI-powered factory energy forecasting and decision support for machine-level monitoring.
                    </div>
                    <div>
                        <span class="status-chip"><b>{n_machines}</b> Machines</span>
                        <span class="status-chip"><b>24h</b> Forecast</span>
                        <span class="status-chip">Decision Support</span>
                        <span class="status-chip">Historical Timeline</span>
                    </div>
                </div>
                <div class="hero-meta">
                    Production Demo<br>
                    Version 1.0<br>
                    Last Update: <b>{format_timestamp(selected_ts)}</b>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def select_machine(machine_id: str):
    """View Detail button callback: update selection + request scroll."""
    st.session_state["selected_machine"] = machine_id
    st.session_state["scroll_to_detail"] = True


def render_machine_card(machine: pd.Series, is_selected: bool):
    """
    Renders one Factory Overview card in NORMAL document flow (no
    absolute-positioning/overlay hack - that approach was removed in
    V4.1 for being fragile). The ENTIRE card is clickable: the wrapper
    div carries a `data-machine-id` attribute, and a single small script
    (injected once via inject_card_click_delegation(), after all cards
    are rendered) listens for clicks anywhere in `.machine-card-wrap`
    and programmatically clicks the matching real Streamlit button -
    identified via its stable `st-key-<key>` class - so no plain inline
    `onclick=` attribute is needed (Streamlit's HTML sanitizer strips
    those from st.markdown output). The button itself remains as a
    secondary, explicit "View Detail" affordance.
    """
    border_color = STATUS_COLORS.get(machine["predicted_status"], "#444")
    selected_class = " selected" if is_selected else ""
    arrow_html = trend_arrow_html(machine["trend_direction"])
    machine_id = machine["machine_id"]
    display_name = get_display_name(machine_id)
    card_name = get_short_display_name(machine_id)
    button_key = f"card_select_{machine_id}"

    st.markdown(
        f"""
        <div class="machine-card-wrap" data-machine-id="{machine_id}">
            <div class="machine-card{selected_class}" style="border-left-color:{border_color};">
                <div class="machine-card-header">
                    <span class="machine-id" title="{display_name}">{card_name}</span>
                    {status_pill(machine['predicted_status'])}
                </div>
                <div class="primary-metric-label">Predicted 24h Avg</div>
                <div class="primary-metric">{machine['predicted_24h_avg_energy']:.2f}</div>
                <div class="trend-indicator">{arrow_html}</div>
                <div class="machine-card-spacer"></div>
                <div class="machine-row"><span>Current</span><span class="muted-value">{machine['current_energy']:.2f}</span></div>
                <div class="machine-row"><span>Pred 24h Max</span><span class="muted-value">{machine['predicted_24h_max_energy']:.2f}</span></div>
                <div class="machine-row"><span>RMSE</span><span class="muted-value">{machine['regression_rmse']:.3f}</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.button(
        "View Detail →",
        key=button_key,
        on_click=select_machine,
        args=(machine_id,),
        help=f"View {display_name} in Machine Detail",
        width='stretch',
    )


def inject_card_click_delegation():
    """
    Makes whole machine cards clickable. Streamlit's st.markdown()
    sanitizer strips inline `onclick=` attributes from raw HTML (a
    security measure), so a plain onclick on the card div silently does
    nothing - this was caught during V6 testing (a click appeared to
    "work" only because it happened to land on the already-selected
    default card; clicking any OTHER card did nothing).

    The robust fix: st.iframe() runs in a sandboxed frame that can still
    reach the main page via window.parent.document (the same technique
    already used elsewhere in this app for the scroll-to-anchor
    behavior). One small delegated click-listener is bound to the page
    body; a MutationObserver re-applies it after every Streamlit rerun
    (which replaces the card elements with new ones).
    """
    st.iframe(
        """
        <script>
            const doc = window.parent.document;
            function bindCardClicks() {
                doc.querySelectorAll('.machine-card-wrap').forEach(function(card) {
                    if (card.dataset.clickBound) return;
                    card.dataset.clickBound = "1";
                    card.addEventListener('click', function() {
                        const machineId = card.getAttribute('data-machine-id');
                        const btn = doc.querySelector('.st-key-card_select_' + machineId + ' button');
                        if (btn) { btn.click(); }
                    });
                });
            }
            bindCardClicks();
            if (!window._smCardObserver) {
                window._smCardObserver = new MutationObserver(bindCardClicks);
                window._smCardObserver.observe(doc.body, {childList: true, subtree: true});
            }
        </script>
        """,
        height=1,
    )


def inject_timeline_fill_script():
    """
    Gives the Historical Timeline slider a real two-tone "traveled vs
    remaining" progress look (blue up to the thumb, dark gray after it).

    Streamlit's select_slider in this version does not render that
    two-tone effect natively - the whole track is always one uniform
    color regardless of the thumb's position (verified directly: the
    colored track element's width stayed the full track width at every
    slider position tested, from 0% to 100%; there is no separate
    proportionally-sized "fill" element to just recolor with CSS alone).

    To get the requested Apple/Linear-style progress bar, this script
    reads the thumb's standard ARIA attributes (aria-valuenow/min/max -
    stable, semantic, and not tied to any Streamlit-internal class name
    that could change between versions) to compute a percentage, then
    applies a hard-stop CSS gradient inline on the track so it visually
    splits into a blue "traveled" segment and a gray "remaining" segment
    at exactly the thumb's position. Re-applied on every DOM change via
    MutationObserver, since a Streamlit rerun replaces the slider
    elements each time the value changes.
    """
    st.iframe(
        f"""
        <script>
            const doc = window.parent.document;
            function updateTimelineFill() {{
                const slider = doc.querySelector('div[data-baseweb="slider"]');
                if (!slider) return;
                const thumb = slider.querySelector('[role="slider"]');
                if (!thumb) return;
                const now = parseFloat(thumb.getAttribute('aria-valuenow'));
                const min = parseFloat(thumb.getAttribute('aria-valuemin'));
                const max = parseFloat(thumb.getAttribute('aria-valuemax'));
                if (isNaN(now) || isNaN(min) || isNaN(max) || max === min) return;
                const pct = ((now - min) / (max - min)) * 100;
                const gradient = 'linear-gradient(to right, {COLOR_PRIMARY} 0%, {COLOR_PRIMARY} '
                    + pct + '%, #3A4254 ' + pct + '%, #3A4254 100%)';
                slider.querySelectorAll('div').forEach(function(el) {{
                    const r = el.getBoundingClientRect();
                    if (r.height > 0 && r.height <= 8 && r.width > 100) {{
                        el.style.setProperty('background', gradient, 'important');
                        el.style.setProperty('height', '5px', 'important');
                        el.style.setProperty('border-radius', '999px', 'important');
                    }}
                }});
            }}
            updateTimelineFill();
            if (!window._smTimelineObserver) {{
                window._smTimelineObserver = new MutationObserver(updateTimelineFill);
                window._smTimelineObserver.observe(doc.body, {{childList: true, subtree: true, attributes: true}});
            }}
        </script>
        """,
        height=1,
    )


def _format_table_cell(col: str, val) -> str:
    if not isinstance(val, (int, float, np.floating, np.integer)):
        return str(val)
    if col == "Change %":
        return f"{val:+.1f}%"
    if col == "RMSE":
        return f"{val:.3f}"
    return f"{val:.2f}"


def render_ranking_panel(title: str, subtitle: str, df: pd.DataFrame, columns: dict, pct_column: str = None):
    """
    Renders one ranking panel (title + subtitle + table) as ONE single
    HTML block, so the border/padding/background can never visually
    separate from the title or table - fixes the V4 overflow/misalignment
    issue where title, subtitle, and table were three separate elements.

    columns: ordered dict of {source_column: display_name}.
    """
    display_df = df[list(columns.keys())].rename(columns=columns)

    header_html = "".join(f"<th>{col}</th>" for col in display_df.columns)
    rows_html = ""
    for _, row in display_df.iterrows():
        cells = []
        for col in display_df.columns:
            val = row[col]
            cell_text = _format_table_cell(col, val)
            css_class = ""
            if col == pct_column and isinstance(val, (int, float, np.floating)):
                css_class = ' class="pct-positive"' if val >= 0 else ' class="pct-negative"'
            cells.append(f"<td{css_class}>{cell_text}</td>")
        rows_html += f"<tr>{''.join(cells)}</tr>"

    st.markdown(
        f"""
        <div class="ranking-panel">
            <div class="ranking-title">{title}</div>
            <div class="ranking-subtitle">{subtitle}</div>
            <table class="dark-table">
                <thead><tr>{header_html}</tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_interpretation_text(machine_row: pd.Series) -> str:
    """Auto-generated (not hardcoded) plain-language summary for the selected machine."""
    display_name = get_display_name(machine_row["machine_id"])
    pred_avg = machine_row["predicted_24h_avg_energy"]
    pred_max = machine_row["predicted_24h_max_energy"]
    current = machine_row["current_energy"]
    rmse = machine_row["regression_rmse"]
    status = machine_row["predicted_status"]

    direction = "higher than" if pred_avg > current else "lower than" if pred_avg < current else "similar to"

    return (
        f"<b>{display_name}</b> is at <b>{current:.2f}</b> energy units as of the selected time. "
        f"Over the next 24 hours, the model expects an average of <b>{pred_avg:.2f}</b> "
        f"({direction} that reading) with a predicted peak (max) of <b>{pred_max:.2f}</b>. "
        f"Forecast error for this machine is <b>±{rmse:.3f}</b> (RMSE). "
        f"The experimental status classifier currently labels this machine "
        f"<b>{status}</b> — treat this as a prototype signal, not a confirmed risk assessment."
    )


def render_decision_support(machine_row: pd.Series, container=st):
    """
    Decision Support V1 panel: runs the rule-based decision_engine on the
    selected machine's snapshot row (i.e. AS OF the selected timestamp)
    and displays the result as structured fields. NOT an LLM - every
    field comes from fixed if/else thresholds in src/decision_engine.py,
    which was not modified for V6 or this polish pass.

    src/decision_engine.py's recommendation_text embeds the raw
    machine_id (it has no knowledge of display names - and shouldn't
    need to, since it's a pure calculation module). Rather than touch
    that module, we do a simple, safe substring swap here in the
    presentation layer: the raw id appears verbatim once at the very
    start of recommendation_text, so replacing it with the display name
    is exact and can't accidentally corrupt the rest of the sentence.
    """
    decision = generate_decision_summary(machine_row)
    priority_color = PRIORITY_COLORS.get(decision["priority_level"], "#999")
    cause_text = build_cause_text(decision)

    display_name = get_display_name(machine_row["machine_id"])
    decision["recommendation_text"] = decision["recommendation_text"].replace(
        machine_row["machine_id"], display_name
    )

    container.markdown('<div class="sm-section-title">Decision Support</div>', unsafe_allow_html=True)
    container.markdown(
        '<div class="sm-section-subtitle">Rule-based recommendation (V1) — not an LLM. '
        "Generated from the machine state at the selected time.</div>",
        unsafe_allow_html=True,
    )

    container.markdown(
        f"""
        <div class="decision-card">
            <div class="decision-title">
                {decision['recommendation_title']}
                <span class="priority-pill" style="background:{priority_color};">{decision['priority_level']} priority</span>
            </div>
            <div class="decision-field-grid">
                <div>
                    <div class="decision-field-label">Risk / Priority</div>
                    <div class="decision-field-value">{decision['priority_level']}</div>
                </div>
                <div>
                    <div class="decision-field-label">Forecast Quality</div>
                    <div class="decision-field-value">{decision['forecast_quality']}</div>
                </div>
                <div style="grid-column: 1 / -1;">
                    <div class="decision-field-label">Cause</div>
                    <div class="decision-field-value">{cause_text}</div>
                </div>
                <div style="grid-column: 1 / -1;">
                    <div class="decision-field-label">Recommendation</div>
                    <div class="decision-field-value">{decision['recommendation_text']}</div>
                </div>
                <div style="grid-column: 1 / -1;">
                    <div class="decision-field-label">Suggested Action</div>
                    <div class="decision-field-value">{decision['suggested_action']}</div>
                </div>
            </div>
            <div class="decision-confidence">ℹ {decision['confidence_note']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_historical_timeline(common_timestamps: list, container=st) -> None:
    """
    Historical Timeline widget, redesigned to an Apple/Linear-style
    slider (thin gray track, blue progress, circular glowing thumb,
    large centered timestamp label). This is placed at the BOTTOM of
    the page, but the value it controls is read at the TOP of the
    script on every rerun via st.session_state["selected_ts_index"] -
    Streamlit widgets always read/write their own session_state key
    regardless of where in the script they are physically drawn, so one
    slider here still drives every section above it. No timeline LOGIC
    changed here - only rendering (title, subtitle, slider, boundary
    labels, footer); the slider's key/options/behavior are untouched.
    """
    container.markdown('<div class="sm-section-title">Historical Timeline</div>', unsafe_allow_html=True)
    container.markdown(
        '<div class="sm-section-subtitle">Inspect hourly factory state across the evaluation period. '
        "This is not repeated forecast-version replay.</div>",
        unsafe_allow_html=True,
    )

    selected_index = container.select_slider(
        "Select hour",
        options=list(range(len(common_timestamps))),
        format_func=lambda i: format_timestamp(common_timestamps[i]),
        key="selected_ts_index",
        label_visibility="collapsed",
    )

    # Static boundary labels (first/last available hour) - rendered by
    # us, not Streamlit's native tick bar (which showed full date+time
    # and is hidden via CSS), since the request calls for date-only
    # labels here ("Feb 18" / "Mar 10").
    container.markdown(
        f"""
        <div class="timeline-bounds-row">
            <span>{common_timestamps[0].strftime('%b %d')}</span>
            <span>{common_timestamps[-1].strftime('%b %d')}</span>
        </div>
        <div class="timeline-footer-row">Viewing Hour {selected_index + 1} / {len(common_timestamps)}</div>
        """,
        unsafe_allow_html=True,
    )

    inject_timeline_fill_script()


def render_machine_detail(machine_id: str, snapshot_df: pd.DataFrame, predictions_df: pd.DataFrame, selected_ts, container=st):
    machine_row = snapshot_df[snapshot_df["machine_id"] == machine_id].iloc[0]
    display_name = get_display_name(machine_id)

    detail_cols = container.columns([1, 3])

    with detail_cols[0]:
        # format_func only changes what the dropdown SHOWS; the value
        # Streamlit stores in st.session_state["selected_machine"] stays
        # the raw machine_id, so nothing downstream needs to change.
        st.selectbox(
            "Or select a machine manually", ALL_MACHINE_IDS, key="selected_machine",
            format_func=get_display_name,
        )

        st.markdown(
            f"""
            <div class="machine-card selected" style="border-left-color:{STATUS_COLORS.get(machine_row['predicted_status'], '#444')}; height:auto; margin-top:14px;">
                <div class="machine-card-header">
                    <span class="sm-machine-name">{display_name}</span>
                    {status_pill(machine_row['predicted_status'])}
                </div>
                <div class="machine-row"><span>Energy at Selected Time</span><span>{machine_row['current_energy']:.3f}</span></div>
                <div class="machine-row"><span>Predicted 24h Avg</span><span>{machine_row['predicted_24h_avg_energy']:.3f}</span></div>
                <div class="machine-row"><span>Predicted 24h Max</span><span>{machine_row['predicted_24h_max_energy']:.3f}</span></div>
                <div class="machine-row"><span>Regression RMSE</span><span>{machine_row['regression_rmse']:.3f}</span></div>
                <div class="machine-row"><span>Selected Timestamp</span><span>{format_timestamp(selected_ts)}</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="caveat-box">⚠ Status labels are experimental and should not be used '
            "as final risk decisions.</div>",
            unsafe_allow_html=True,
        )

    with detail_cols[1]:
        machine_preds = predictions_df[predictions_df["machine_id"] == machine_id].sort_values("timestamp")
        selected_row = machine_preds[machine_preds["timestamp"] == selected_ts]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=machine_preds["timestamp"], y=machine_preds["actual_24h_avg_energy"],
            name="Actual (24h avg)", line=dict(color=COLOR_PRIMARY, width=1.6),
            hovertemplate="%{x|%b %d, %H:%M}<br>Actual: %{y:.2f}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=machine_preds["timestamp"], y=machine_preds["predicted_24h_avg_energy"],
            name="Predicted (24h avg)", line=dict(color=COLOR_WARNING, width=1.6, dash="dash"),
            hovertemplate="%{x|%b %d, %H:%M}<br>Predicted: %{y:.2f}<extra></extra>",
        ))

        if len(selected_row) > 0:
            fig.add_vline(x=selected_ts, line=dict(color=COLOR_TEXT, width=1.2, dash="dot"))
            fig.add_annotation(
                x=selected_ts, y=1.06, yref="paper", showarrow=False,
                text="Selected Time", font=dict(color=COLOR_TEXT, size=11),
                xanchor="right", yanchor="bottom",
            )
            fig.add_trace(go.Scatter(
                x=[selected_ts], y=[selected_row["predicted_24h_max_energy"].iloc[0]],
                mode="markers", name="Predicted Peak (24h max)",
                marker=dict(color=COLOR_CRITICAL, size=10, symbol="diamond"),
                hovertemplate="Predicted 24h max: %{y:.2f}<extra></extra>",
            ))

        fig.update_layout(
            title=dict(text=f"Forecast Trend — {display_name}", font=dict(size=14), y=0.98),
            template="plotly_dark",
            plot_bgcolor="#10151f", paper_bgcolor="#10151f",
            height=390,
            margin=dict(l=10, r=10, t=60, b=70),
            # Legend moved BELOW the plot (rather than sharing the top
            # strip with the title and the "Selected Time" annotation),
            # so the two can never overlap regardless of where the
            # selected timestamp falls on the x-axis.
            legend=dict(orientation="h", yanchor="top", y=-0.22, xanchor="center", x=0.5, font=dict(size=11)),
            xaxis=dict(title="Date", tickfont=dict(size=11), gridcolor=COLOR_BORDER),
            yaxis=dict(title="Energy", tickfont=dict(size=11), gridcolor=COLOR_BORDER),
        )
        st.plotly_chart(fig, width='stretch')

        st.markdown(
            f'<div class="interpretation-box">{build_interpretation_text(machine_row)}</div>',
            unsafe_allow_html=True,
        )

    return machine_preds, machine_row


# =======================================================================
# Load data + resolve the selected timestamp (BEFORE anything else renders)
# =======================================================================

inject_css()

try:
    summary_df, predictions_df, metrics = load_data()
except FileNotFoundError as e:
    st.error(
        f"Could not find a required results file: {e}. Run the forecasting pipeline "
        f"first (src/dashboard_pipeline.py) so that results/machine_status_summary.csv, "
        f"results/dashboard_forecast_predictions.csv and results/dashboard_metrics.json all exist."
    )
    st.stop()

ALL_MACHINE_IDS = sorted(summary_df["machine_id"].unique(), key=_extract_machine_number)
COMMON_TIMESTAMPS = get_common_timestamps(predictions_df)

# Display-name mapping (see build_machine_display_map docstring). Built
# once, right after we know the full machine list, so it stays stable
# for the whole session. This is presentation-only: session_state,
# filtering, and every data lookup below still use ALL_MACHINE_IDS /
# raw machine_id values exactly as before.
MACHINE_DISPLAY_MAP = build_machine_display_map(ALL_MACHINE_IDS)
MACHINE_ID_FROM_DISPLAY = {v: k for k, v in MACHINE_DISPLAY_MAP.items()}

if "selected_machine" not in st.session_state:
    st.session_state["selected_machine"] = ALL_MACHINE_IDS[0]
if "scroll_to_detail" not in st.session_state:
    st.session_state["scroll_to_detail"] = False

# --- THE FIX for "timeline only updates Factory Insights" ---
# Read the slider's session_state value NOW, before any section below is
# rendered. The slider widget itself is only drawn much later, at the
# bottom of the page (render_historical_timeline) - but Streamlit ties a
# widget's value to its `key` in session_state independently of where the
# widget is physically drawn, so reading st.session_state["selected_ts_index"]
# here always reflects the CURRENT slider position, including on the
# very first load (falls back to the most recent hour).
if "selected_ts_index" not in st.session_state:
    st.session_state["selected_ts_index"] = len(COMMON_TIMESTAMPS) - 1

selected_ts_index = st.session_state["selected_ts_index"]
selected_ts = COMMON_TIMESTAMPS[selected_ts_index]

# snapshot_df is now THE single source of truth for every timestamp-
# dependent value rendered anywhere below - KPIs, Factory Insights,
# machine cards, ranking tables, Machine Detail, and Decision Support
# all read from this one dataframe.
snapshot_df = get_timestamp_snapshot(predictions_df, summary_df, selected_ts)


# ---------------------------------------------------------------------
# 1. Product Header
# ---------------------------------------------------------------------

render_header(selected_ts, len(summary_df))


# ---------------------------------------------------------------------
# 2. KPI cards
# ---------------------------------------------------------------------

kpi_panel = st.container()
kpi_panel.markdown(f'<div class="{PANEL_MARKER}"></div>', unsafe_allow_html=True)
kpi_panel.markdown('<div class="sm-section-title">Overview</div>', unsafe_allow_html=True)
kpi_panel.markdown(
    '<div class="sm-section-subtitle">Fleet-wide energy snapshot at the selected time.</div>',
    unsafe_allow_html=True,
)

kpi_cols = kpi_panel.columns(5)
with kpi_cols[0]:
    render_kpi_card("Total Machines", f"{len(snapshot_df)}")
with kpi_cols[1]:
    render_kpi_card("Avg Current Energy", f"{snapshot_df['current_energy'].mean():.2f}")
with kpi_cols[2]:
    render_kpi_card("Avg Predicted 24h Energy", f"{snapshot_df['predicted_24h_avg_energy'].mean():.2f}")
with kpi_cols[3]:
    render_kpi_card("Highest Predicted 24h Max", f"{snapshot_df['predicted_24h_max_energy'].max():.2f}")
with kpi_cols[4]:
    render_kpi_card("Avg Model RMSE", f"{snapshot_df['regression_rmse'].mean():.3f}")

kpi_panel.markdown(
    '<div class="info-note" style="margin-top:16px;">'
    "Forecasts are generated from the saved ML pipeline outputs. Status labels are experimental."
    "</div>",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------
# 3. Factory Insights
# ---------------------------------------------------------------------

insights_panel = st.container()
insights_panel.markdown(f'<div class="{PANEL_MARKER}"></div>', unsafe_allow_html=True)
insights_panel.markdown('<div class="sm-section-title">Factory Insights</div>', unsafe_allow_html=True)
insights_panel.markdown(
    '<div class="sm-section-subtitle">Auto-generated from the Decision Support engine at the selected time (rule-based, not LLM).</div>',
    unsafe_allow_html=True,
)

fleet_insights = generate_fleet_insights(snapshot_df)

insight_cols = insights_panel.columns(4)
with insight_cols[0]:
    st.markdown(
        f"""<div class="insight-card">
            <div class="insight-label">Highest Predicted Peak</div>
            <div class="insight-value">{get_display_name(fleet_insights['highest_peak_machine'])}</div>
            <div class="insight-subvalue">{fleet_insights['highest_peak_value']:.2f} predicted max energy</div>
        </div>""",
        unsafe_allow_html=True,
    )
with insight_cols[1]:
    st.markdown(
        f"""<div class="insight-card">
            <div class="insight-label">Largest Predicted Increase</div>
            <div class="insight-value">{get_display_name(fleet_insights['largest_increase_machine'])}</div>
            <div class="insight-subvalue">{fleet_insights['largest_increase_pct']:+.1f}% avg energy change</div>
        </div>""",
        unsafe_allow_html=True,
    )
with insight_cols[2]:
    st.markdown(
        f"""<div class="insight-card">
            <div class="insight-label">Most Reliable Forecast</div>
            <div class="insight-value">{get_display_name(fleet_insights['most_reliable_machine'])}</div>
            <div class="insight-subvalue">{fleet_insights['most_reliable_rmse']:.3f} RMSE</div>
        </div>""",
        unsafe_allow_html=True,
    )
with insight_cols[3]:
    st.markdown(
        f"""<div class="insight-card">
            <div class="insight-label">High-Priority Machines</div>
            <div class="insight-value">{fleet_insights['high_priority_count']} of {len(snapshot_df)}</div>
            <div class="insight-subvalue">predicted 24h max ≥ 4.75</div>
        </div>""",
        unsafe_allow_html=True,
    )



# ---------------------------------------------------------------------
# 4. Factory Overview (machine cards)
# ---------------------------------------------------------------------

overview_panel = st.container()
overview_panel.markdown(f'<div class="{PANEL_MARKER}"></div>', unsafe_allow_html=True)
overview_panel.markdown('<div class="sm-section-title">Factory Overview</div>', unsafe_allow_html=True)
overview_panel.markdown(
    '<div class="sm-section-subtitle">Values reflect the selected time on the Historical Timeline below. '
    "Click anywhere on a card to open it in Machine Detail.</div>",
    unsafe_allow_html=True,
)

sort_option = overview_panel.radio(
    "Sort cards by",
    ["Predicted 24h Avg Energy", "Unit Number", "Lowest RMSE", "Experimental Status"],
    horizontal=True,
    label_visibility="collapsed",
)

cards_df = snapshot_df.copy()
if sort_option == "Unit Number":
    cards_df["_unit_num"] = cards_df["machine_id"].apply(_extract_machine_number)
    cards_df = cards_df.sort_values("_unit_num")
elif sort_option == "Predicted 24h Avg Energy":
    cards_df = cards_df.sort_values("predicted_24h_avg_energy", ascending=False)
elif sort_option == "Lowest RMSE":
    cards_df = cards_df.sort_values("regression_rmse", ascending=True)
else:
    status_rank = {"Critical": 0, "Warning": 1, "Normal": 2}
    cards_df["_rank"] = cards_df["predicted_status"].map(status_rank)
    cards_df = cards_df.sort_values("_rank")

overview_panel.markdown(
    f'<div class="info-note" style="margin:2px 0 10px 0;">Sorted by: <b style="color:{COLOR_TEXT};">{sort_option}</b></div>',
    unsafe_allow_html=True,
)

N_COLS = 6
for i in range(0, len(cards_df), N_COLS):
    row_chunk = cards_df.iloc[i:i + N_COLS]
    cols = overview_panel.columns(N_COLS)
    for col, (_, machine) in zip(cols, row_chunk.iterrows()):
        with col:
            is_selected = machine["machine_id"] == st.session_state["selected_machine"]
            render_machine_card(machine, is_selected)

inject_card_click_delegation()


# ---------------------------------------------------------------------
# 5. Ranking panels
# ---------------------------------------------------------------------

rankings_panel = st.container()
rankings_panel.markdown(f'<div class="{PANEL_MARKER}"></div>', unsafe_allow_html=True)
rankings_panel.markdown('<div class="sm-section-title">Rankings</div>', unsafe_allow_html=True)
rankings_panel.markdown(
    '<div class="sm-section-subtitle">Fleet-wide comparisons at the selected time.</div>',
    unsafe_allow_html=True,
)

panel_cols = rankings_panel.columns(3)

ranked_df = snapshot_df.copy()
ranked_df = ranked_df.rename(columns={"energy_change_pct": "change_pct"})

with panel_cols[0]:
    top_energy = ranked_df.sort_values("predicted_24h_avg_energy", ascending=False).head(5).copy()
    top_energy["machine_id"] = top_energy["machine_id"].map(get_display_name)
    render_ranking_panel(
        "Top Future Energy",
        "Highest predicted 24h average energy at the selected time.",
        top_energy,
        {"machine_id": "Machine", "predicted_24h_avg_energy": "Pred 24h Avg",
         "current_energy": "Current", "change_pct": "Change %"},
        pct_column="Change %",
    )

with panel_cols[1]:
    lowest_rmse = ranked_df.sort_values("regression_rmse", ascending=True).head(5).copy()
    lowest_rmse["machine_id"] = lowest_rmse["machine_id"].map(get_display_name)
    render_ranking_panel(
        "Most Reliable Forecasts",
        "Lowest RMSE fleet-wide (based on latest model evaluation, not hourly).",
        lowest_rmse,
        {"machine_id": "Machine", "regression_rmse": "RMSE", "predicted_24h_avg_energy": "Pred 24h Avg"},
    )

with panel_cols[2]:
    largest_increase = ranked_df.sort_values("change_pct", ascending=False).head(5).copy()
    largest_increase["machine_id"] = largest_increase["machine_id"].map(get_display_name)
    render_ranking_panel(
        "Largest Expected Increase",
        "Biggest jump from current to predicted 24h average energy.",
        largest_increase,
        {"machine_id": "Machine", "current_energy": "Current",
         "predicted_24h_avg_energy": "Pred 24h Avg", "change_pct": "Change %"},
        pct_column="Change %",
    )


# ---------------------------------------------------------------------
# 6. Machine Detail
# ---------------------------------------------------------------------

st.markdown('<div id="machine-detail-anchor"></div>', unsafe_allow_html=True)

detail_panel = st.container()
detail_panel.markdown(f'<div class="{PANEL_MARKER}"></div>', unsafe_allow_html=True)
detail_panel.markdown('<div class="sm-section-title">Machine Detail</div>', unsafe_allow_html=True)
detail_panel.markdown(
    '<div class="sm-section-subtitle">Chart, machine info, and summary for the selected machine at the selected time.</div>',
    unsafe_allow_html=True,
)

machine_preds, machine_row = render_machine_detail(
    st.session_state["selected_machine"], snapshot_df, predictions_df, selected_ts, container=detail_panel
)

if st.session_state["scroll_to_detail"]:
    st.session_state["scroll_to_detail"] = False
    st.iframe(
        """
        <script>
            const doc = window.parent.document;
            const anchor = doc.getElementById('machine-detail-anchor');
            if (anchor) { anchor.scrollIntoView({behavior: 'smooth', block: 'start'}); }
        </script>
        """,
        height=1,
    )


# ---------------------------------------------------------------------
# 7. Decision Support
# ---------------------------------------------------------------------

decision_panel = st.container()
decision_panel.markdown(f'<div class="{PANEL_MARKER}"></div>', unsafe_allow_html=True)
render_decision_support(machine_row, container=decision_panel)


# ---------------------------------------------------------------------
# 8. Historical Timeline (compact, bottom of page - see note above on
#    why this widget still controls everything rendered earlier)
# ---------------------------------------------------------------------

timeline_panel = st.container()
timeline_panel.markdown(f'<div class="{PANEL_MARKER}"></div>', unsafe_allow_html=True)
render_historical_timeline(COMMON_TIMESTAMPS, container=timeline_panel)
