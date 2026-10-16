"""Insights tab: summaries across this clinic's saved patient records (patient_results\\).

Each patient code has one saved record (its latest save), so these are one-row-per-patient summaries.
"""

from datetime import date, datetime
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from patient_forms_ui import show_full_table
from patient_records import STATUS_LABELS, RecordError, load_record, saved_codes
from patient_trend import patient_trend_view
from risk_thresholds import DEFAULT_PRESET
from scoring_config import band_label, instrument

RISK_ORDER = ["Low", "Moderate", "High", "Insufficient information", "Other"]
RISK_COLORS = ["#15803D", "#B45309", "#B91C1C", "#94A3B8", "#475569"]
REPEAT_MONTHS = {"Low": 12, "Moderate": 6, "High": 3}
STATUS_SHORT = {"auto_unverified": "Automatic draft", "responses_verified": "Responses verified", "final_report": "Final report"}
NOT_SCORED = "Not scored"
SMALL_SAMPLE = 5
ITEM_KEYS = ("phq9_items", "peg_items", "pdi_items", "ort_oud_items", "comm_items")
MEASURES = {
    "PHQ-9 total (0-27)": "phq9",
    "PEG average (0-10)": "peg",
    "PDI total (0-70)": "pdi",
    "ORT / ORT-OUD total": "ort",
    "COMM total": "comm",
}
COLUMNS = [
    "patient", "visit", "visit_label", "status", "risk", "repeat", "next_due", "phq9", "severity", "item9",
    "peg", "pdi", "ort", "ort_version", "comm", "comm_max", "blank_answers", "thresholds",
]
DISPLAY = {
    "patient": "Patient", "visit_label": "Visit date", "status": "Record status", "risk": "Overall risk",
    "next_due": "Next battery due", "phq9": "PHQ-9", "severity": "PHQ-9 severity", "item9": "Item 9",
    "peg": "PEG", "pdi": "PDI", "ort": "ORT", "comm": "COMM", "blank_answers": "Blank answers",
    "thresholds": "Risk thresholds",
}


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number


def _risk(value: Any) -> str:
    text = str(value or "")
    if text in RISK_ORDER:
        return text
    return "Insufficient information" if text.startswith("Insufficient") else "Other"


def record_row(record: dict[str, Any]) -> dict[str, Any]:
    """One summary row for a saved record; raises KeyError/ValueError when essential fields are unusable."""
    scores = record.get("scores") or {}
    visit = datetime.strptime(record["visit_folder"], "%Y_%m_%d").date()
    risk = _risk(record.get("integrated_risk"))
    phq9 = _number(scores.get("phq9"))
    months = REPEAT_MONTHS.get(risk)
    thresholds = next(
        (row.get("result") for row in record.get("score_summary") or [] if row.get("measure") == "Risk Thresholds"),
        DEFAULT_PRESET,
    )
    return {
        "patient": str(record["patient_code"]),
        "visit": pd.Timestamp(visit),
        "visit_label": visit.isoformat(),
        "status": STATUS_SHORT.get(record.get("status"), str(record.get("status") or "Unknown")),
        "risk": risk,
        "repeat": record.get("recommended_repeat_interval") or "",
        "next_due": (pd.Timestamp(visit) + pd.DateOffset(months=months)) if months else pd.NaT,
        "phq9": phq9,
        "severity": band_label("PHQ-9", phq9).split(" (")[0] if phq9 is not None else NOT_SCORED,
        "item9": _number(scores.get("item9")),
        "peg": _number(scores.get("peg_avg")),
        "pdi": _number(scores.get("pdi")),
        "ort": _number(scores.get("ort")),
        "ort_version": scores.get("ort_version") or "ORT",
        "comm": _number(scores.get("comm")),
        "comm_max": int(_number(scores.get("comm_max")) or 68),
        "blank_answers": sum(value is None for key in ITEM_KEYS for value in scores.get(key) or []),
        "thresholds": thresholds,
    }


def load_records(root: Path | None = None) -> tuple[pd.DataFrame, list[str]]:
    """All saved records as one row per patient code, plus messages for records that could not be read."""
    rows, problems = [], []
    for code in saved_codes(root):
        try:
            record = load_record(code, root)
            if record:
                rows.append(record_row(record))
        except RecordError as error:
            problems.append(str(error))
        except (KeyError, TypeError, ValueError) as error:
            problems.append(f"{code}: saved record skipped - missing or invalid field ({error}).")
    frame = pd.DataFrame(rows, columns=COLUMNS)
    frame["visit"] = pd.to_datetime(frame["visit"])
    frame["next_due"] = pd.to_datetime(frame["next_due"])
    return frame.sort_values(["visit", "patient"], ascending=[False, True], ignore_index=True), problems


def flag_rates(frame: pd.DataFrame) -> pd.DataFrame:
    """Share of patients with each clinical flag, among patients for whom that measure was scored."""
    ort_cut = (frame["ort_version"] == "ORT-OUD").map({True: 3, False: 4})
    checks = {
        "PEG >= 7 (high pain interference)": (frame["peg"], frame["peg"] >= 7),
        "PDI >= 41 (severe disability)": (frame["pdi"], frame["pdi"] >= 41),
        "Elevated mood burden (PHQ-9 >= 15)": (frame["phq9"], frame["phq9"] >= 15),
        "PHQ-9 item 9 > 0 (suicide-risk assessment)": (frame["item9"], frame["item9"] > 0),
        "COMM >= 9 (misuse-risk signal)": (frame["comm"], frame["comm"] >= 9),
        "ORT-OUD >= 3 / ORT >= 4 (baseline risk)": (frame["ort"], frame["ort"] >= ort_cut),
    }
    rows = []
    for flag, (values, positive) in checks.items():
        scored = values.notna()
        count = int(scored.sum())
        flagged = int((positive & scored).sum())
        rows.append({"flag": flag, "patients_flagged": flagged, "patients_scored": count,
                     "rate": flagged / count if count else 0.0})
    return pd.DataFrame(rows)


def follow_up(frame: pd.DataFrame, today: date | None = None) -> pd.DataFrame:
    """Patients needing action, most urgent first."""
    today_stamp = pd.Timestamp(today or date.today())
    rows = []
    for row in frame.itertuples(index=False):
        reasons: list[tuple[int, str]] = []
        if row.item9 is not None and not pd.isna(row.item9) and row.item9 > 0:
            reasons.append((1, "PHQ-9 item 9 positive: same-day suicide-risk assessment"))
        if row.risk == "High":
            reasons.append((2, "High overall risk"))
        if row.risk == "Insufficient information":
            reasons.append((3, "Insufficient information: complete missing answers"))
        if not pd.isna(row.next_due) and row.next_due < today_stamp:
            reasons.append((4, f"Repeat battery overdue (due {row.next_due.date().isoformat()})"))
        if row.blank_answers:
            reasons.append((5, f"{row.blank_answers} blank answer(s) need review"))
        if row.status == STATUS_SHORT["auto_unverified"]:
            reasons.append((6, "Automatic draft: verify responses"))
        elif row.status == STATUS_SHORT["responses_verified"]:
            reasons.append((7, "Clinician report pending"))
        if reasons:
            rows.append({
                "priority": min(rank for rank, _ in reasons), "Patient": row.patient, "Visit date": row.visit_label,
                "Overall risk": row.risk, "Record status": row.status,
                "Action needed": "; ".join(text for _, text in sorted(reasons)),
            })
    columns = ["priority", "Patient", "Visit date", "Overall risk", "Record status", "Action needed"]
    result = pd.DataFrame(rows, columns=columns).sort_values(["priority", "Patient"], ignore_index=True)
    return result.drop(columns="priority")


HEATMAP_MEASURES = ["PHQ-9", "Item 9", "PEG", "PDI", "ORT", "COMM"]


def heatmap_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """One cell per patient and measure: raw score, share of the scale maximum and whether it meets the flag threshold."""
    rows = []
    for row in frame.itertuples(index=False):
        ort_oud = row.ort_version == "ORT-OUD"
        cells = {
            "PHQ-9": (row.phq9, 27, 15), "Item 9": (row.item9, 3, 1),
            "PEG": (row.peg, 10, 7), "PDI": (row.pdi, 70, 41),
            "ORT": (row.ort, 9 if ort_oud else 26, 3 if ort_oud else 4), "COMM": (row.comm, row.comm_max, 9),
        }
        for measure, (value, maximum, threshold) in cells.items():
            scored = value is not None and not pd.isna(value)
            rows.append({
                "patient": row.patient, "risk": row.risk, "visit_label": row.visit_label, "measure": measure,
                "value": value if scored else None, "maximum": maximum,
                "share": min(value / maximum, 1.0) if scored and maximum else None,
                "flagged": bool(scored and value >= threshold), "threshold": threshold,
                "text": f"{round(value, 1):g}" if scored else "-",
            })
    return pd.DataFrame(rows, columns=[
        "patient", "risk", "visit_label", "measure", "value", "maximum", "share", "flagged", "threshold", "text",
    ])


def _heatmap_chart(frame: pd.DataFrame) -> alt.LayerChart:
    cells = heatmap_frame(frame)
    rank = {risk: index for index, risk in enumerate(["High", "Moderate", "Insufficient information", "Other", "Low"])}
    order = (
        frame.assign(rank=frame["risk"].map(rank), score=frame["phq9"].fillna(-1))
        .sort_values(["rank", "score", "patient"], ascending=[True, False, True])["patient"].tolist()
    )
    base = alt.Chart(cells).encode(
        x=alt.X("measure:N", sort=HEATMAP_MEASURES, title=None, axis=alt.Axis(labelAngle=0, orient="top")),
        y=alt.Y("patient:N", sort=order, title=None),
        tooltip=[
            "patient:N", "visit_label:N", "risk:N", "measure:N", alt.Tooltip("value:Q", format=".2f"),
            "maximum:Q", alt.Tooltip("share:Q", format=".0%", title="share of maximum"), "threshold:Q", "flagged:N",
        ],
    )
    color = alt.condition(
        "isValid(datum.share)",
        alt.Color("share:Q", title="Share of scale maximum", scale=alt.Scale(scheme="orangered", domain=[0, 1]),
                  legend=alt.Legend(format="%")),
        alt.value("#E2E8F0"),
    )
    heat = base.mark_rect(stroke="white", strokeWidth=2).encode(color=color)
    flagged = base.transform_filter("datum.flagged").mark_rect(fill=None, stroke="#111827", strokeWidth=2.5)
    labels = base.mark_text(fontSize=12).encode(
        text="text:N",
        color=alt.condition("datum.share > 0.55", alt.value("white"), alt.value("#111827")),
    )
    return (heat + flagged + labels).properties(height=max(120, 32 * len(order)))


def _multiselect(label: str, options: list[str], key: str) -> list[str]:
    chosen = st.multiselect(label, options, key=key, placeholder="All")
    return chosen or options


def display_table(frame: pd.DataFrame) -> pd.DataFrame:
    table = frame.copy()
    table["next_due"] = table["next_due"].dt.date.astype("string").fillna("-")
    table["comm"] = [
        "-" if pd.isna(value) else f"{value:g} / {maximum}" for value, maximum in zip(table["comm"], table["comm_max"])
    ]
    for column in ("phq9", "item9", "peg", "pdi", "ort"):
        table[column] = table[column].map(lambda value: "-" if pd.isna(value) else f"{round(value, 2):g}")
    return table[list(DISPLAY)].rename(columns=DISPLAY)


def clinic_insights_view(root: Path | None = None, today: date | None = None) -> None:
    st.subheader("Insights: Saved assessments")
    st.caption(
        "Built from the saved patient records in the patient_results folder: one row per patient code, using the "
        "latest saved visit. Overall risk is shown as it was saved. Everything stays on this computer."
    )
    frame, problems = load_records(root)
    for problem in problems:
        st.warning(problem)
    if frame.empty:
        st.info("No saved patient records yet. Use **Calculate and save scores** in the Assessment tab to add some.")
        return

    with st.expander("Filter saved assessments", expanded=True):
        columns = st.columns(3)
        with columns[0]:
            visits = _multiselect("Visit date", sorted(frame["visit_label"].unique(), reverse=True), "clinic_visits")
        with columns[1]:
            statuses = _multiselect(
                "Record status", [s for s in STATUS_SHORT.values() if s in set(frame["status"])]
                + sorted(set(frame["status"]) - set(STATUS_SHORT.values())), "clinic_status",
            )
        with columns[2]:
            risks = _multiselect("Overall risk", [r for r in RISK_ORDER if r in set(frame["risk"])], "clinic_risk")
    selected = frame[frame["visit_label"].isin(visits) & frame["status"].isin(statuses) & frame["risk"].isin(risks)]
    if selected.empty:
        st.warning("No saved assessments match the selected filters.")
        return

    if selected["thresholds"].nunique() > 1:
        st.warning("These records were saved with different risk-threshold presets, so their overall risk levels are not directly comparable.")
    if len(selected) < SMALL_SAMPLE:
        st.caption(f"Only {len(selected)} patient(s) selected: percentages and charts will change a lot as more records are saved.")

    metrics = st.columns(5)
    metrics[0].metric("Patients", f"{len(selected)}")
    metrics[1].metric("High risk", f"{int((selected['risk'] == 'High').sum())}")
    metrics[2].metric("Item 9 positive", f"{int((selected['item9'] > 0).sum())}")
    metrics[3].metric("Insufficient information", f"{int((selected['risk'] == 'Insufficient information').sum())}")
    metrics[4].metric("Final reports", f"{int((selected['status'] == STATUS_SHORT['final_report']).sum())}")

    actions = follow_up(selected, today)
    st.markdown("**Follow-up list** (most urgent first)")
    if actions.empty:
        st.success("No follow-up actions for the selected patients.")
    else:
        show_full_table(actions)

    st.markdown("**Score heatmap** (patients x measures, highest risk first)")
    st.altair_chart(_heatmap_chart(selected), use_container_width=True)
    st.caption(
        "Colour = score as a share of that scale's maximum; the number is the raw score. Outlined cells meet the "
        "clinical flag threshold (PHQ-9 >= 15, item 9 > 0, PEG >= 7, PDI >= 41, ORT-OUD >= 3 / ORT >= 4, "
        "COMM >= 9). Grey cells were not scored."
    )

    left, right = st.columns(2)
    with left:
        st.markdown("**Overall risk**")
        risk_counts = selected.groupby("risk").size().reset_index(name="patients")
        risk_counts["share"] = risk_counts["patients"] / risk_counts["patients"].sum()
        donut = alt.Chart(risk_counts).encode(
            theta=alt.Theta("patients:Q", stack=True),
            order=alt.Order("rank:Q"),
            color=alt.Color("risk:N", title="Overall risk", sort=RISK_ORDER,
                            scale=alt.Scale(domain=RISK_ORDER, range=RISK_COLORS)),
            tooltip=["risk:N", "patients:Q", alt.Tooltip("share:Q", format=".0%")],
        ).transform_calculate(rank=f"indexof({RISK_ORDER}, datum.risk)")
        st.altair_chart(
            donut.mark_arc(innerRadius=60, outerRadius=110, stroke="white", strokeWidth=2)
            + donut.mark_text(radius=135, fontSize=13).encode(text="patients:Q", color=alt.value("#111827")),
            use_container_width=True,
        )
    with right:
        st.markdown("**PHQ-9 depression severity**")
        severity_order = [band["label"].split(" (")[0] for band in instrument("PHQ-9")["bands"]] + [NOT_SCORED]
        severity_counts = selected.groupby("severity").size().reset_index(name="patients")
        st.altair_chart(
            alt.Chart(severity_counts).mark_bar(cornerRadiusEnd=4).encode(
                y=alt.Y("severity:N", sort=severity_order, title=None),
                x=alt.X("patients:Q", title="Patients", axis=alt.Axis(tickMinStep=1)),
                color=alt.Color("severity:N", sort=severity_order, scale=alt.Scale(scheme="orangered"), legend=None),
                tooltip=["severity:N", "patients:Q"],
            ),
            use_container_width=True,
        )

    st.markdown("**Clinical flags: share of patients flagged** (among patients with that measure scored)")
    rates = flag_rates(selected)
    lollipop = alt.Chart(rates).encode(
        y=alt.Y("flag:N", sort=list(rates["flag"]), title=None),
        tooltip=["flag:N", alt.Tooltip("rate:Q", format=".0%"), "patients_flagged:Q", "patients_scored:Q"],
    )
    st.altair_chart(
        lollipop.mark_rule(color="#94A3B8", strokeWidth=2).encode(
            x=alt.X("rate:Q", title="Patients flagged", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
            x2=alt.X2(datum=0),
        )
        + lollipop.mark_circle(size=220, color="#0F766E", opacity=1).encode(x="rate:Q")
        + lollipop.mark_text(dx=18, align="left", fontSize=12).encode(x="rate:Q", text=alt.Text("rate:Q", format=".0%")),
        use_container_width=True,
    )

    left, right = st.columns(2)
    with left:
        st.markdown("**Pain interference vs disability** (one point per patient)")
        both = selected[selected["peg"].notna() & selected["pdi"].notna()]
        st.altair_chart(
            alt.Chart(both).mark_circle(size=140, opacity=0.8).encode(
                x=alt.X("peg:Q", title="PEG average (0-10)", scale=alt.Scale(domain=[0, 10])),
                y=alt.Y("pdi:Q", title="PDI total (0-70)", scale=alt.Scale(domain=[0, 70])),
                color=alt.Color("risk:N", title="Overall risk", sort=RISK_ORDER,
                                scale=alt.Scale(domain=RISK_ORDER, range=RISK_COLORS)),
                tooltip=["patient:N", "visit_label:N", alt.Tooltip("peg:Q", format=".2f"), "pdi:Q", "risk:N"],
            ),
            use_container_width=True,
        )
    with right:
        st.markdown("**Saved assessments by visit date**")
        by_visit = selected.groupby(["visit_label", "risk"]).size().reset_index(name="patients")
        st.altair_chart(
            alt.Chart(by_visit).mark_bar().encode(
                x=alt.X("visit_label:N", title="Visit date", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("patients:Q", title="Patients", axis=alt.Axis(tickMinStep=1)),
                color=alt.Color("risk:N", title="Overall risk", sort=RISK_ORDER,
                                scale=alt.Scale(domain=RISK_ORDER, range=RISK_COLORS)),
                tooltip=["visit_label:N", "risk:N", "patients:Q"],
            ),
            use_container_width=True,
        )

    measure_label = st.selectbox("Score distribution", list(MEASURES), key="clinic_measure")
    measure = MEASURES[measure_label]
    scored = selected[selected[measure].notna()]
    st.altair_chart(
        alt.Chart(scored).mark_tick(thickness=4, size=40).encode(
            x=alt.X(f"{measure}:Q", title=measure_label),
            color=alt.Color("risk:N", title="Overall risk", sort=RISK_ORDER,
                            scale=alt.Scale(domain=RISK_ORDER, range=RISK_COLORS)),
            tooltip=["patient:N", "visit_label:N", alt.Tooltip(f"{measure}:Q", format=".2f"), "risk:N"],
        ),
        use_container_width=True,
    )
    st.caption(f"{len(scored)} of {len(selected)} patient(s) have a {measure_label.split(' (')[0]} score.")

    st.markdown("**All saved assessments**")
    table = display_table(selected)
    show_full_table(table)
    st.download_button(
        "Download this table (.csv)", data=table.to_csv(index=False).encode("utf-8"),
        file_name="saved_assessments_summary.csv", mime="text/csv",
    )

    st.subheader("Patient trend")
    trend_code = st.selectbox(
        "Patient", sorted(frame["patient"]), key="clinic_trend_patient",
        help="Every saved visit for this patient, oldest to newest.",
    )
    patient_trend_view(trend_code, root, key="clinic_trend")
    st.caption(
        "Summaries of saved records only: they do not change scoring, risk levels or reports. Patient codes are "
        "shown because these are this clinic's own records; take care when sharing screenshots or the CSV."
    )
