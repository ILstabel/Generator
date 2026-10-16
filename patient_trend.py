"""Patient trend: totals and overall risk across a patient's saved visits (from <code>_history.json)."""

from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from patient_records import RecordError, visit_history
from scoring_config import instrument

RISK_LEVELS = ["Low", "Moderate", "High"]
RISK_COLORS = {"Low": "#15803D", "Moderate": "#B45309", "High": "#B91C1C", "Insufficient information": "#94A3B8"}
# Measure key -> (chart title, fixed axis maximum or None for the form's own maximum, flag line, flag text).
TREND_MEASURES: dict[str, tuple[str, int | None, float | None, str]] = {
    "phq9": ("PHQ-9 total (0-27)", 27, 15, "15 = elevated mood burden"),
    "item9": ("PHQ-9 item 9 (0-3)", 3, 1, "above 0 = suicide-risk assessment"),
    "peg": ("PEG average (0-10)", 10, 7, "7 = high pain interference"),
    "pdi": ("PDI total (0-70)", 70, 41, "41 = severe disability"),
    "ort": ("ORT-OUD total", None, 3, "3 = high ORT-OUD risk"),
    "comm": ("COMM total", None, 9, "9 = misuse-risk signal"),
}


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number


def trend_frame(visits: list[dict[str, Any]]) -> pd.DataFrame:
    """One row per saved visit, oldest first, totals only."""
    rows = []
    for visit in visits:
        scores = visit.get("scores") or {}
        risk = str(visit.get("integrated_risk") or "")
        rows.append({
            "visit": pd.Timestamp(pd.to_datetime(visit["visit_folder"], format="%Y_%m_%d")),
            "visit_label": pd.to_datetime(visit["visit_folder"], format="%Y_%m_%d").date().isoformat(),
            "status": visit.get("status_label") or visit.get("status") or "",
            "risk": "Insufficient information" if risk.startswith("Insufficient") else risk or "Not recorded",
            "phq9": _number(scores.get("phq9")), "item9": _number(scores.get("item9")),
            "peg": _number(scores.get("peg_avg")), "pdi": _number(scores.get("pdi")),
            "ort": _number(scores.get("ort")), "ort_version": scores.get("ort_version") or "ORT",
            "comm": _number(scores.get("comm")), "comm_max": int(_number(scores.get("comm_max")) or 68),
        })
    columns = ["visit", "visit_label", "status", "risk", "phq9", "item9", "peg", "pdi", "ort", "ort_version", "comm", "comm_max"]
    return pd.DataFrame(rows, columns=columns).sort_values("visit", ignore_index=True)


def _improvement(measure: str, first: float, latest: float) -> str:
    rule = instrument("PEG" if measure == "peg" else "PDI")["improvement"]
    drop = first - latest
    percent = drop / first * 100 if first > 0 else None
    if drop < 0:
        return "Worse than first visit"
    if drop == 0:
        return "No change"
    if measure == "peg":
        tests = [drop >= rule["min_point_drop"], percent is not None and percent >= rule["min_percent_drop"]]
        met = (any if rule["rule"] == "any" else all)(tests)
        joiner = " or " if rule["rule"] == "any" else " and "
        criterion = f">={rule['min_point_drop']:g} point{joiner}>={rule['min_percent_drop']:g}%"
    else:
        met = percent is not None and percent >= rule["min_percent_drop"]
        criterion = f">={rule['min_percent_drop']:g}%"
    return f"{'Meets' if met else 'Below'} improvement criterion ({criterion})"


def change_since_first(frame: pd.DataFrame) -> pd.DataFrame:
    """PEG and PDI change from the first to the latest visit where each was scored."""
    rows = []
    for measure, name in (("peg", "PEG average"), ("pdi", "PDI total")):
        scored = frame[frame[measure].notna()]
        if len(scored) < 2:
            rows.append({"Measure": name, "First visit": "-", "Latest visit": "-", "Change": "-",
                         "% change": "-", "Improvement": "Needs two visits with this score"})
            continue
        first, latest = scored.iloc[0], scored.iloc[-1]
        change = latest[measure] - first[measure]
        percent = f"{change / first[measure] * 100:+.0f}%" if first[measure] > 0 else "undefined (zero at first visit)"
        rows.append({
            "Measure": name,
            "First visit": f"{round(first[measure], 2):g} ({first['visit_label']})",
            "Latest visit": f"{round(latest[measure], 2):g} ({latest['visit_label']})",
            "Change": f"{round(change, 2):+g}", "% change": percent,
            "Improvement": _improvement(measure, first[measure], latest[measure]),
        })
    return pd.DataFrame(rows)


def visits_table(frame: pd.DataFrame) -> pd.DataFrame:
    text = lambda value: "-" if pd.isna(value) else f"{round(value, 2):g}"  # noqa: E731
    return pd.DataFrame({
        "Visit date": frame["visit_label"], "Overall risk": frame["risk"],
        "PHQ-9": frame["phq9"].map(text), "Item 9": frame["item9"].map(text), "PEG": frame["peg"].map(text),
        "PDI": frame["pdi"].map(text), "ORT-OUD": frame["ort"].map(text),
        "COMM": ["-" if pd.isna(value) else f"{value:g} / {maximum}" for value, maximum in zip(frame["comm"], frame["comm_max"])],
        "Record status": frame["status"],
    })


def _measure_chart(frame: pd.DataFrame, measure: str) -> alt.LayerChart | None:
    title, maximum, flag, flag_text = TREND_MEASURES[measure]
    scored = frame[frame[measure].notna()]
    if scored.empty:
        return None
    if maximum is None:
        maximum = int(scored["comm_max"].max()) if measure == "comm" else 9 if (scored["ort_version"] == "ORT-OUD").all() else 26
    if measure == "ort" and not (scored["ort_version"] == "ORT-OUD").all():
        flag, flag_text = 4, "4 = moderate ORT risk"
    base = alt.Chart(scored).encode(
        x=alt.X("visit:T", title=None, axis=alt.Axis(format="%Y-%m-%d", labelAngle=-30, tickCount=len(scored))),
        y=alt.Y(f"{measure}:Q", title=None, scale=alt.Scale(domain=[0, maximum])),
        tooltip=[alt.Tooltip("visit_label:N", title="Visit"), alt.Tooltip(f"{measure}:Q", title=title, format=".2f"),
                 alt.Tooltip("risk:N", title="Overall risk")],
    )
    line = base.mark_line(color="#0F766E", strokeWidth=3) + base.mark_circle(size=90, color="#0F766E")
    rule = alt.Chart(pd.DataFrame({"y": [flag], "label": [flag_text]})).mark_rule(
        color="#B91C1C", strokeDash=[5, 4], opacity=0.7,
    ).encode(y="y:Q", tooltip=alt.Tooltip("label:N", title="Flag line"))
    return (line + rule).properties(title=title, height=190)


def _risk_chart(frame: pd.DataFrame) -> alt.Chart:
    order = RISK_LEVELS + ["Insufficient information"]
    return alt.Chart(frame).mark_circle(size=220).encode(
        x=alt.X("visit:T", title=None, axis=alt.Axis(format="%Y-%m-%d", labelAngle=-30, tickCount=len(frame))),
        y=alt.Y("risk:N", sort=list(reversed(order)), title=None, scale=alt.Scale(domain=list(reversed(order)))),
        color=alt.Color("risk:N", scale=alt.Scale(domain=list(RISK_COLORS), range=list(RISK_COLORS.values())), legend=None),
        tooltip=[alt.Tooltip("visit_label:N", title="Visit"), alt.Tooltip("risk:N", title="Overall risk"), "status:N"],
    ).properties(title="Overall risk", height=190)


def patient_trend_view(code: str, root: Path | None = None, *, key: str = "trend") -> None:
    """Trend charts and tables for one patient's saved visits."""
    from patient_forms_ui import show_full_table

    try:
        visits = visit_history(code, root)
    except RecordError as error:
        st.error(str(error))
        return
    if not visits:
        st.info(f"No saved visits for patient {code} yet. Save scores for this patient to start a trend.")
        return
    frame = trend_frame(visits)
    if len(frame) == 1:
        st.info(
            f"Patient {code} has one saved visit ({frame['visit_label'].iloc[0]}). The trend appears once a second "
            "visit date is saved."
        )
    else:
        st.caption(
            f"Patient {code}: {len(frame)} saved visits, {frame['visit_label'].iloc[0]} to {frame['visit_label'].iloc[-1]}. "
            "Dashed red lines mark the clinical flag thresholds."
        )
    show_full_table(visits_table(frame))
    if len(frame) < 2:
        return
    charts = [_risk_chart(frame)] + [chart for measure in TREND_MEASURES if (chart := _measure_chart(frame, measure))]
    for start in range(0, len(charts), 3):
        columns = st.columns(3)
        for column, chart in zip(columns, charts[start:start + 3]):
            column.altair_chart(chart, use_container_width=True)
    st.markdown("**Change since first visit (PEG and PDI)**")
    show_full_table(change_since_first(frame))
    if (frame["item9"] > 0).any():
        positives = ", ".join(frame.loc[frame["item9"] > 0, "visit_label"])
        st.error(f"PHQ-9 item 9 was positive at: {positives}.")
    st.caption("Trends use each visit's saved totals and overall risk as they were saved. Not diagnostic.")
