import math
import re
from typing import Literal, TypedDict

import pandas as pd
import streamlit as st


UDS_LABELS = {
    "not_reviewed": "Not reviewed / not available at time of assessment",
    "consistent": "Consistent with prescribed medication regimen and no concerning PDMP findings",
    "uds_consistent_pdmp_ok": "UDS consistent; PDMP review without concerning findings",
    "uds_pending_pdmp_ok": "UDS pending; PDMP review without concerning findings",
    "requires_review": "UDS/PDMP findings require provider review and closer monitoring",
    "discordant": "Discordant UDS and/or concerning PDMP findings noted",
}
REFILL_LABELS = {
    "not_reviewed": "Not reviewed / refill behavior not documented",
    "stable": "Stable refill behavior without early refill pattern",
    "no_concerns": "No concerning refill behavior reported at this interval",
    "intermittent": "Intermittent refill timing concerns requiring monitoring",
    "early_or_escalation": "Early refill request or dose-escalation request noted",
    "lost_stolen": "Lost/stolen medication report or medication-management concern noted",
    "requires_review": "Refill behavior requires provider review and closer monitoring",
}
CONTEXT_LABELS = {
    "routine": "Routine interval chronic opioid monitoring",
    "high_pain": "High pain interference with ongoing opioid therapy",
    "worsening": "Worsening pain/function trajectory",
    "escalation": "Opioid escalation request",
    "elevated_misuse": "Elevated opioid misuse-risk screen",
    "mood": "Mood deterioration affecting pain/opioid risk",
    "discordant": "Discordant UDS/PDMP or refill concern",
    "aberrancy_history": "Documented history of opioid-related aberrant medication-use behavior",
    "post_procedure": "Post-procedure / post-intervention reassessment",
    "agreement": "Treatment agreement / opioid safety reassessment",
}


class Scores(TypedDict):
    peg_avg: float | None
    pdi: float | None
    phq9: float | None
    phq4: float | None
    item9: float | None
    comm: float | None
    ort: float | None
    comm_max: int


class ParsedScores(TypedDict):
    scores: Scores
    errors: list[str]
    warnings: list[str]


ScoreKey = Literal["peg_avg", "pdi", "phq9", "phq4", "item9", "comm", "ort"]
SCORE_LABELS: dict[ScoreKey, str] = {
    "peg_avg": "PEG average", "pdi": "PDI", "phq9": "PHQ-9",
    "phq4": "PHQ-4", "item9": "PHQ-9 item #9", "comm": "COMM", "ort": "ORT",
}
DIAGNOSES = {
    "F11.20": "Opioid dependence, uncomplicated",
    "G89.4": "Chronic pain syndrome",
}
MODEL_NOTICE = (
    "App-defined decision support, not a validated clinical prediction model. "
    "The existing point formula and repeat intervals require clinician verification. "
    "COMM thresholds are retained from the source logic; applicability to each form is not established."
)
NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
LABEL_PATTERN = re.compile(
    r"(?<!\w)(?P<label>PHQ\s*-?\s*9\s+item\s*#?\s*9|Question\s*#?\s*9|Item\s*#?\s*9"
    r"|PEG(?:\s+(?:Average|Avg))?|PDI|PHQ\s*-?\s*[94]|COMM(?:\s*-?\s*(?:17|16|7))?|ORT)"
    r"(?!\w)(?:[ \t]+(?:Score|Total))?[ \t]*(?:[:=.]?[ \t]*)(?:Answer[ \t]*:[ \t]*)?",
    re.IGNORECASE,
)


def empty_scores() -> Scores:
    return {
        "peg_avg": None, "pdi": None, "phq9": None, "phq4": None,
        "item9": None, "comm": None, "ort": None, "comm_max": 68,
    }


def ort_level(value: float | None) -> str:
    if value is None:
        return "Not documented"
    return "Low Risk" if value <= 3 else "Moderate Risk" if value <= 7 else "High Risk"


def validate_scores(scores: Scores) -> list[str]:
    errors = []
    limits = {"peg_avg": 10, "pdi": 70, "phq9": 27, "phq4": 12, "item9": 3, "comm": scores["comm_max"]}
    if scores["comm_max"] not in {28, 64, 68}:
        errors.append("Select a supported COMM maximum (28, 64 or 68).")
    for key, label in SCORE_LABELS.items():
        value = scores[key]
        if value is None:
            continue
        maximum = limits.get(key)
        if not math.isfinite(value) or value < 0 or (maximum is not None and value > maximum):
            bounds = f"0-{maximum}" if maximum is not None else "a non-negative number"
            errors.append(f"{label} must be {bounds}.")
        elif key != "peg_avg" and value != int(value):
            errors.append(f"{label} must be a whole number.")
    if scores["phq9"] is not None and scores["item9"] is not None:
        if scores["item9"] > scores["phq9"]:
            errors.append("PHQ-9 item #9 cannot exceed the PHQ-9 total.")
        if scores["phq9"] - scores["item9"] > 24:
            errors.append("PHQ-9 total is inconsistent with item #9 (other eight items total at most 24).")
    return errors


def parse_scores(text: str) -> ParsedScores:
    clean = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    scores = empty_scores()
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    matches = list(LABEL_PATTERN.finditer(clean))
    for index, match in enumerate(matches):
        label = re.sub(r"[\s#-]", "", match["label"]).lower()
        normalized = (
            "item9" if label.startswith(("question", "item")) or "item9" in label
            else "peg_avg" if label.startswith("peg")
            else "comm" if label.startswith("comm")
            else label
        )
        keys: dict[str, ScoreKey] = {key: key for key in SCORE_LABELS}
        key = keys[normalized]
        name = SCORE_LABELS[key]
        if key in seen:
            errors.append(f"Duplicate {name}: resolve repeated or conflicting values in the review fields.")
            scores[key] = None
            continue
        seen.add(key)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(clean)
        body = clean[match.end():end].split("\n")[0].strip()
        number = re.match(rf"({NUMBER})(?![\w.])", body)
        if number is None:
            errors.append(f"{name}: no readable numeric value after the label.")
            continue
        value = float(number[1])
        tail = body[number.end():].strip()
        if key == "peg_avg" and tail.startswith(("+", ",")):
            items = re.match(rf"({NUMBER})\s*[+,]\s*({NUMBER})\s*[+,]\s*({NUMBER})(?![\w.])", body)
            if not items:
                errors.append("PEG requires exactly three items or one average / 10.")
                continue
            values = [float(item) for item in items.groups()]
            if any(not math.isfinite(item) or not 0 <= item <= 10 for item in values):
                errors.append("Each PEG item must be 0-10.")
                continue
            remainder = body[items.end():].strip()
            if remainder.startswith(("+", ",")):
                errors.append("PEG requires exactly three items.")
                continue
            value = sum(values) / 3
            if remainder.startswith("/"):
                divisor = re.match(rf"/\s*({NUMBER})(?![\w.])", remainder)
                if divisor is None or float(divisor[1]) != 3:
                    errors.append("A three-item PEG expression must divide by 3.")
            reported = re.search(rf"=\s*({NUMBER})(?![\w.])", remainder)
            if reported and not math.isclose(float(reported[1]), value, abs_tol=0.01):
                errors.append("PEG stated average conflicts with its three items.")
        else:
            denominator = re.match(rf"/\s*({NUMBER})(?![\w.])", tail)
            if tail.startswith("/") and denominator is None and key != "ort":
                errors.append(f"{name}: unreadable denominator.")
            maxima = {"peg_avg": 10, "pdi": 70, "phq9": 27, "phq4": 12, "item9": 3}
            if denominator and key in maxima and float(denominator[1]) != maxima[key]:
                errors.append(f"{name}: expected denominator {maxima[key]}.")
            if key == "comm":
                version_max = {"comm17": 68, "comm16": 64, "comm7": 28}.get(label)
                maximum = float(denominator[1]) if denominator else version_max
                if maximum is not None and maximum not in {28, 64, 68}:
                    errors.append("COMM denominator must be 28, 64 or 68.")
                elif maximum is not None:
                    scores["comm_max"] = int(maximum)
                else:
                    warnings.append("COMM form was not specified. Verify the selected 68-point maximum.")
                if denominator and version_max and float(denominator[1]) != version_max:
                    errors.append("COMM version conflicts with its denominator.")
            if key == "ort":
                stated = re.search(r"\b(Low|Moderate|High)(?:\s+Risk)?\b", tail, re.IGNORECASE)
                if stated and stated[1].lower() != ort_level(value).split()[0].lower():
                    errors.append("ORT stated risk conflicts with its numeric score.")
        scores[key] = value
    errors.extend(validate_scores(scores))
    if scores["phq9"] is not None and scores["phq4"] is not None:
        warnings.append("Both mood scales are present. PHQ-9 takes precedence for risk points and mood flags.")
    if not matches and clean.strip():
        errors.append("No supported score labels were recognized. Correct the text or use structured entry.")
    return {"scores": scores, "errors": errors, "warnings": warnings}


def severity_peg(value: float | None) -> str:
    if value is None:
        return "Not found"
    if value < 4:
        return "Low pain interference"
    if value < 7:
        return "Moderate pain interference"
    return "High pain interference"


def severity_pdi(value: float | None) -> str:
    if value is None:
        return "Not found"
    if value <= 20:
        return "Mild disability"
    if value <= 40:
        return "Moderate disability"
    return "Severe disability"


def severity_phq9(value: float | None) -> str:
    if value is None:
        return "Not found"
    if value <= 4:
        return "Minimal depressive symptoms"
    if value <= 9:
        return "Mild depressive symptoms"
    if value <= 14:
        return "Moderate depressive symptoms"
    if value <= 19:
        return "Moderately severe depressive symptoms"
    return "Severe depressive symptoms"


def severity_phq4(value: float | None) -> str:
    if value is None:
        return "Not found"
    if value <= 2:
        return "Minimal mood/anxiety symptoms"
    if value <= 5:
        return "Mild mood/anxiety symptoms"
    if value <= 8:
        return "Moderate mood/anxiety symptoms"
    return "Severe mood/anxiety symptoms"


def severity_comm(value: float | None) -> str:
    if value is None:
        return "Not found"
    return "Elevated opioid misuse-risk signal" if value >= 9 else "Below elevated misuse-risk threshold"


def missing_information(scores: Scores, uds_code: str, refill_code: str) -> list[str]:
    missing = [
        SCORE_LABELS[key] for key in ("peg_avg", "pdi", "comm", "ort")
        if scores[key] is None
    ]
    if scores["phq9"] is None and scores["phq4"] is None:
        missing.append("PHQ-9 or PHQ-4 total")
    if scores["phq9"] is not None and scores["item9"] is None:
        missing.append("PHQ-9 item #9")
    if uds_code in {"not_reviewed", "uds_pending_pdmp_ok"}:
        missing.append("Completed UDS/PDMP review")
    if refill_code == "not_reviewed":
        missing.append("Refill behavior review")
    return missing


def risk_contributions(scores: Scores, uds_code: str, refill_code: str, contexts: list[str]) -> dict[str, int]:
    contributions: dict[str, int] = {}
    comm, ort = scores["comm"], scores["ort"]
    contributions["COMM (>=18: 3; >=9: 2)"] = 3 if comm is not None and comm >= 18 else 2 if comm is not None and comm >= 9 else 0
    contributions["ORT (>=8: 3; >=4: 1)"] = 3 if ort is not None and ort >= 8 else 1 if ort is not None and ort >= 4 else 0
    if scores["phq9"] is not None:
        contributions["PHQ-9 (>=20: 2; >=15: 1)"] = 2 if scores["phq9"] >= 20 else 1 if scores["phq9"] >= 15 else 0
    elif scores["phq4"] is not None:
        contributions["PHQ-4 (>=9: 2; >=6: 1)"] = 2 if scores["phq4"] >= 9 else 1 if scores["phq4"] >= 6 else 0
    contributions["Positive PHQ-9 item #9 (3)"] = 3 if scores["item9"] is not None and scores["item9"] > 0 else 0
    contributions["UDS/PDMP (discordant: 3; requires review: 2)"] = 3 if uds_code == "discordant" else 2 if uds_code == "requires_review" else 0
    contributions["Refill behavior (early/lost: 2; other concern: 1)"] = 2 if refill_code in {"early_or_escalation", "lost_stolen"} else 1 if refill_code in {"intermittent", "requires_review"} else 0
    context_points = sum(
        2 if code in {"elevated_misuse", "escalation", "discordant"}
        else 1 if code in {"worsening", "mood", "aberrancy_history"}
        else 0
        for code in contexts
    )
    contributions["Clinical context (sum capped at 3)"] = min(3, context_points)
    return contributions


def risk_level(scores: Scores, uds_code: str, refill_code: str, contexts: list[str]) -> str:
    errors = validate_scores(scores)
    if errors:
        raise ValueError("\n".join(errors))
    if uds_code not in UDS_LABELS or refill_code not in REFILL_LABELS or any(code not in CONTEXT_LABELS for code in contexts):
        raise ValueError("Unknown clinical context, UDS/PDMP or refill selection.")
    if missing_information(scores, uds_code, refill_code):
        return "Insufficient information"
    points = sum(risk_contributions(scores, uds_code, refill_code, contexts).values())
    return "High" if points >= 5 else "Moderate" if points >= 2 else "Low"


def monitoring_interval(risk: str) -> str:
    if risk == "High":
        return "Repeat battery every 3 months"
    if risk == "Moderate":
        return "Repeat battery every 6 months"
    if risk == "Low":
        return "Repeat battery yearly / every 12 months"
    return "Not assigned: complete the assessment and obtain clinician review"


def make_report(
    scores: Scores, contexts: list[str], uds_code: str, refill_code: str, minutes: int = 0,
    *, feedback_confirmed: bool = False, time_confirmed: bool = False,
    diagnoses: tuple[str, ...] = (), clinician_verified: bool = False, synthetic: bool = False,
) -> tuple[str, list[tuple[str, str, str]], dict[str, bool | None], str, str]:
    if minutes < 0 or minutes != int(minutes):
        raise ValueError("Actual QHP time must be a non-negative whole number of minutes.")
    if time_confirmed and minutes <= 0:
        raise ValueError("Enter actual time greater than zero before confirming the time attestation.")
    if any(code not in DIAGNOSES for code in diagnoses):
        raise ValueError("Unknown diagnosis selection.")
    if not contexts:
        contexts = ["routine"]
    risk = risk_level(scores, uds_code, refill_code, contexts)
    context_text = "; ".join(CONTEXT_LABELS[c] for c in contexts)
    uds = UDS_LABELS[uds_code]
    refill = REFILL_LABELS[refill_code]
    time_total = f"{minutes} minutes (user-entered actual time)" if minutes else "Not documented"
    repeat = monitoring_interval(risk)

    peg = f"{scores['peg_avg']:.2f} / 10" if scores["peg_avg"] is not None else "Not found"
    pdi = f"{scores['pdi']:g} / 70" if scores["pdi"] is not None else "Not found"
    phq_label = "PHQ-9" if scores["phq9"] is not None else "PHQ-4"
    phq_value = scores["phq9"] if scores["phq9"] is not None else scores["phq4"]
    phq_display = f"{phq_value:g} / {'27' if scores['phq9'] is not None else '12'}" if phq_value is not None else "Not found"
    phq_interpretation = severity_phq9(scores["phq9"]) if scores["phq9"] is not None else severity_phq4(scores["phq4"])
    item9 = scores["item9"]
    comm_display = f"{scores['comm']:g}" if scores["comm"] is not None else "Not found"
    ort_display = f"{scores['ort']:g} / {ort_level(scores['ort'])}" if scores["ort"] is not None else "Not found"

    if item9 is not None and item9 > 0:
        suicide = (
            "PHQ-9 item #9 is positive. Same-day suicide risk assessment is indicated, including assessment "
            "of passive versus active suicidal ideation, plan, intent, access to means, protective factors, "
            "clinical judgment of acute risk level, safety planning, crisis resources, and disposition."
        )
    elif item9 == 0:
        suicide = "PHQ-9 item #9 = 0. Negative response on this item only; this does not rule out suicide risk. Assess further if clinically indicated."
    else:
        suicide = "PHQ-9 item #9 not documented; suicide risk has not been established by this input. PHQ-4 does not assess suicidal ideation. Assess if clinically indicated."
    suicide += " A screening response alone does not determine acute suicide risk."

    contexts_concern = {"worsening", "escalation", "elevated_misuse", "mood", "discordant", "aberrancy_history"}
    context_flags = [CONTEXT_LABELS[c] for c in contexts if c in contexts_concern]
    mood = scores["phq9"] if scores["phq9"] is not None else scores["phq4"]
    flags: dict[str, bool | None] = {
        "PEG >= 7 — severe pain impact": None if scores["peg_avg"] is None else scores["peg_avg"] >= 7,
        "PDI >= 41 — severe disability": None if scores["pdi"] is None else scores["pdi"] >= 41,
        "Elevated mood symptom burden": None if mood is None else mood >= (15 if scores["phq9"] is not None else 6),
        "PHQ-9 item #9 > 0 — suicide risk assessment indicated": None if item9 is None else item9 > 0,
        "COMM >= 9 — elevated opioid misuse-risk signal": None if scores["comm"] is None else scores["comm"] >= 9,
        "ORT moderate/high baseline risk": None if scores["ort"] is None else scores["ort"] >= 4,
        "Worsening trajectory / function concern from clinical context": "worsening" in contexts,
        "Opioid escalation request from clinical context": "escalation" in contexts,
        "; ".join(context_flags) if context_flags else "Clinical context does not independently raise risk": bool(context_flags),
        "UDS/PDMP concern or closer monitoring indicated": None if uds_code in {"not_reviewed", "uds_pending_pdmp_ok"} else uds_code in {"requires_review", "discordant"},
        "Refill behavior concern / closer monitoring indicated": None if refill_code == "not_reviewed" else refill_code in {"intermittent", "early_or_escalation", "lost_stolen", "requires_review"},
    }

    rows = [
        ("Integrated Opioid Risk", risk, "App-defined classification; clinician verification required"),
        ("Recommended Repeat Interval", repeat, "Risk-stratified battery repeat interval"),
        ("PEG Average", peg, severity_peg(scores["peg_avg"])),
        ("PDI", pdi, severity_pdi(scores["pdi"])),
        (phq_label, phq_display, phq_interpretation),
        ("PHQ-9 Item #9", f"{item9:g}" if item9 is not None else "Not documented", "Positive SI item; risk assessment indicated" if item9 is not None and item9 > 0 else "No SI endorsed on item #9" if item9 == 0 else "Not documented"),
        ("COMM", f"{comm_display} / {scores['comm_max']}", severity_comm(scores["comm"])),
        ("ORT", ort_display, ort_level(scores["ort"])),
        ("Clinical Context", "Selected", context_text),
        ("UDS / PDMP", "Selected", uds),
        ("Refill Behavior", "Selected", refill),
        ("QHP Evaluation Time", time_total, "Confirmed by user" if time_confirmed else "Not attested"),
    ]
    rows.extend(("Clinician-selected ICD-10", code, DIAGNOSES[code]) for code in diagnoses)
    missing = missing_information(scores, uds_code, refill_code)
    completeness = "Incomplete: " + "; ".join(missing) if missing else "Complete for app-required inputs (not a comprehensive clinical assessment)"
    rows.insert(1, ("Assessment Completeness", completeness, "Missing data are not negative findings"))

    flag_lines = "\n".join(f"{'[?] Not assessed:' if checked is None else '[x]' if checked else '[ ]'} {label}" for label, checked in flags.items())
    rows_text = "\n".join(f"{name}: {value}\n  Interpretation: {meaning}" for name, value, meaning in rows)
    contribution_lines = "\n".join(
        f"- {label}: {points}" for label, points in risk_contributions(scores, uds_code, refill_code, contexts).items()
    )
    feedback_text = (
        "User confirmed: assessment results were reviewed with the patient."
        if feedback_confirmed else "Patient feedback not confirmed; review with the patient is not documented."
    )
    diagnosis_text = "\n".join(f"{code} - {DIAGNOSES[code]}" for code in diagnoses) or "None selected. Screening scores do not establish a diagnosis or billing eligibility."
    attestation = (
        f"User-confirmed attestation: I personally spent {minutes} minutes performing the evaluation service, "
        "excluding patient form-completion time and separately billed administration time."
        if time_confirmed else "Time attestation not confirmed; no personal-time statement included."
    )
    status = "CLINICIAN REVIEW CONFIRMED BY USER" if clinician_verified else "DRAFT - CLINICIAN VERIFICATION REQUIRED"
    report = f"""{'SYNTHETIC TEST DATA - NOT FOR PATIENT DOCUMENTATION' if synthetic else status}
{status if synthetic else ''}
{MODEL_NOTICE}

INTEGRATED OPIOID RISK LEVEL: {risk.upper()}
RECOMMENDED REPEAT INTERVAL: {repeat}
ASSESSMENT COMPLETENESS: {completeness}

RISK POINT CONTRIBUTIONS (missing inputs contribute no known points, not negative findings)
{contribution_lines}
Known points: {sum(risk_contributions(scores, uds_code, refill_code, contexts).values())}
Source thresholds: Low 0-1; Moderate 2-4; High >=5. No classification or interval assigned to incomplete assessments.

============================================================
SCORE SUMMARY
============================================================
{rows_text}

============================================================
CLINICAL FLAGS
============================================================
{flag_lines}

============================================================
INTERVAL CLINICAL IMPRESSION
============================================================
This summary describes entered data only; it does not attest that testing or a clinical evaluation was performed.
PEG: {peg} ({severity_peg(scores['peg_avg'])}).
PDI: {pdi} ({severity_pdi(scores['pdi'])}).
{phq_label}: {phq_display} ({phq_interpretation}).

Clinical context / trigger: {context_text}
UDS / PDMP: {uds}
Refill behavior: {refill}
{suicide}

App-defined result: {risk}. Assessment completeness: {completeness}.

============================================================
INTEGRATED OPIOID RISK INTERPRETATION
============================================================
App-defined opioid-risk result: {risk}. Points use COMM, ORT, the prioritized mood scale, PHQ-9 item 9, selected UDS/PDMP status, refill behavior and clinical context. PEG and PDI affect flags but do not add points. This is not a validated clinical risk prediction or a treatment decision.

Recommended battery repeat interval: {repeat}.

The repeat interval is based on the integrated opioid-risk level:
- High risk: repeat battery every 3 months
- Moderate risk: repeat battery every 6 months
- Low risk: repeat battery yearly / every 12 months

Reassess sooner if medication-use behavior, mood symptoms, suicide-risk status, function, UDS/PDMP, refill pattern, or clinical presentation worsens.

============================================================
SUICIDE RISK ASSESSMENT
============================================================
{suicide}

If suicide-risk responses or clinical presentation indicate concern, complete same-day risk assessment, document passive versus active suicidal ideation, plan, intent, access to means, protective factors, clinical risk level, safety planning, crisis resources, and disposition.

============================================================
OPIOID TREATMENT GUIDANCE
============================================================
Continue risk-stratified opioid safety monitoring. Treatment planning should emphasize measurable functional goals, adherence with the opioid treatment agreement, medication safety, PDMP/UDS monitoring as clinically indicated, non-opioid pain strategies, and reassessment of benefit versus risk over time.

Monitoring and treatment plan should be adjusted if the patient has elevated COMM score, moderate/high ORT risk, concerning UDS/PDMP findings, early refill/lost medication pattern, dose-escalation request, opioid-related aberrant medication-use history, mood/safety deterioration, or worsening pain/function trajectory.

============================================================
FEEDBACK PROVIDED TO PATIENT
============================================================
{feedback_text}

============================================================
BILLING / DIAGNOSTIC CODES
============================================================
{diagnosis_text}

============================================================
QHP TIME & ATTESTATION
============================================================
Total QHP Evaluation Time: {time_total}
No automatic time allocation has been generated.
{attestation}

Clinician must verify all interpretations, recommendations, diagnoses, time and billing eligibility before use."""
    return report, rows, flags, risk, repeat


SAMPLES = {
    "Low": "PEG: 3 + 3 + 3\nPDI: 12\nPHQ9: 3\nQuestion 9: 0\nCOMM: 2 / 68\nORT: 2 / Low Risk",
    "Moderate": "PEG: 5 + 6 + 5\nPDI: 28\nPHQ9: 8\nQuestion 9: 0\nCOMM: 9 / 68\nORT: 3 / Low Risk",
    "High": "PEG: 7 + 8 + 7\nPDI: 45\nPHQ9: 12\nQuestion 9: 0\nCOMM: 18 / 68\nORT: 8 / High Risk",
    "Incomplete": "PEG Average: 8 / 10\nPHQ9: 15\nQuestion 9: 1",
}


def reset_assessment(sample: str | None = None) -> None:
    for key in list(st.session_state):
        if key.startswith("assessment_"):
            del st.session_state[key]
    if sample:
        st.session_state["assessment_text"] = SAMPLES[sample]
        st.session_state["assessment_synthetic"] = True
        load_parsed_scores()
        if sample != "Incomplete":
            st.session_state["assessment_uds"] = "consistent"
            st.session_state["assessment_refill"] = "stable"


def invalidate_parse() -> None:
    st.session_state["assessment_ready"] = False
    st.session_state.pop("assessment_report_inputs", None)
    invalidate_review()
    st.session_state["assessment_time_confirmed"] = False


def invalidate_review() -> None:
    st.session_state["assessment_scores_verified"] = False
    st.session_state["assessment_clinician_verified"] = False
    st.session_state["assessment_feedback"] = False


def invalidate_documentation() -> None:
    st.session_state["assessment_clinician_verified"] = False


def invalidate_time() -> None:
    invalidate_documentation()
    st.session_state["assessment_time_confirmed"] = False


def load_parsed_scores() -> None:
    parsed = parse_scores(st.session_state.get("assessment_text", ""))
    for key in SCORE_LABELS:
        st.session_state[f"assessment_{key}"] = parsed["scores"][key]
    st.session_state["assessment_comm_max"] = parsed["scores"]["comm_max"]
    st.session_state["assessment_parse_errors"] = parsed["errors"]
    st.session_state["assessment_parse_warnings"] = parsed["warnings"]
    st.session_state["assessment_ready"] = True
    invalidate_review()
    st.session_state["assessment_time_confirmed"] = False
    st.session_state.pop("assessment_report_inputs", None)


def main() -> None:
    st.set_page_config(page_title="Chronic Pain / Opioid Risk Generator", layout="wide")
    st.title("Chronic Pain / Opioid Risk Generator")
    st.info(
        "Support tool only. A qualified clinician must verify scores, interpretations, risk levels, "
        "recommendations, diagnoses and documentation before use."
    )
    st.caption(MODEL_NOTICE)
    st.caption("Source repeat guidance: High: 3 months; Moderate: 6 months; Low: 12 months. Incomplete: no interval assigned.")
    columns = st.columns(5)
    for column, sample in zip(columns, SAMPLES):
        column.button(f"Load {sample.lower()} sample", on_click=reset_assessment, args=(sample,))
    columns[-1].button("Reset assessment", on_click=reset_assessment)
    if st.session_state.get("assessment_synthetic"):
        st.warning("Synthetic test data loaded. Generated reports will be watermarked. Reset before entering real assessment data.")
    mode = st.radio(
        "Entry method", ["Paste text", "Structured entry"], horizontal=True,
        key="assessment_mode", on_change=invalidate_parse,
    )
    if mode == "Paste text":
        st.text_area(
            "Paste scores or copied text from a filled form",
            height=180,
            placeholder="PEG: 8 + 10 + 6 / 3 = 8\nPDI: 40\nPHQ9: 19\nQuestion 9. Answer: 0\nCOMM: 0\nORT: 4 / Moderate Risk",
            key="assessment_text", on_change=invalidate_parse,
        )
        st.button("Parse into review fields", on_click=load_parsed_scores)
        if not st.session_state.get("assessment_ready"):
            st.info("Paste scores and parse them before reviewing or generating a report.")
            return
        for message in st.session_state.get("assessment_parse_errors", []):
            st.warning(f"Source parser issue: {message} Correct the source or resolve it in the review fields below; source notes remain visible after manual corrections.")
        for message in st.session_state.get("assessment_parse_warnings", []):
            st.warning(message)

    st.subheader("Review and correct scores")
    st.caption("Blank means not documented, never zero. Clear a field to mark it missing. Verify the COMM form maximum.")
    scores = empty_scores()
    fields = st.columns(3)
    for index, (key, label) in enumerate(SCORE_LABELS.items()):
        scores[key] = fields[index % 3].number_input(
            label, value=None, step=0.01 if key == "peg_avg" else 1.0,
            format="%.2f" if key == "peg_avg" else "%g", key=f"assessment_{key}",
            on_change=invalidate_review,
        )
    scores["comm_max"] = st.selectbox("COMM form maximum", [68, 64, 28], key="assessment_comm_max", on_change=invalidate_review)
    if scores["phq9"] is not None and scores["phq4"] is not None:
        st.warning("Both mood scales entered: PHQ-9 takes precedence for risk points, the summary and mood flags.")
    if scores["comm_max"] != 68:
        st.warning("Shorter COMM form selected. The source's >=9 / >=18 point thresholds are not established for this form; clinician verification is essential.")
    errors = validate_scores(scores)
    for error in errors:
        st.error(error)
    if scores["item9"] is not None and math.isfinite(scores["item9"]) and 0 < scores["item9"] <= 3:
        st.error(
            "Safety alert: positive PHQ-9 item #9. Same-day clinician suicide-risk assessment is indicated, "
            "independent of opioid-risk classification. This screening response does not determine acute risk."
        )
    elif scores["item9"] is None:
        st.warning("PHQ-9 item #9 not documented. PHQ-4 does not assess suicidal ideation.")
    elif scores["item9"] == 0:
        st.caption("PHQ-9 item #9 is negative; this does not rule out suicide risk.")

    left, middle, right = st.columns(3)
    with left:
        contexts = st.multiselect(
            "Clinical Context / Trigger (select all that apply)",
            options=list(CONTEXT_LABELS), default=["routine"],
            format_func=lambda key: CONTEXT_LABELS[key], key="assessment_contexts", on_change=invalidate_review,
        )
    with middle:
        uds_code = st.selectbox("UDS / PDMP", list(UDS_LABELS), format_func=lambda key: UDS_LABELS[key], key="assessment_uds", on_change=invalidate_review)
    with right:
        refill_code = st.selectbox("Refill Behavior", list(REFILL_LABELS), format_func=lambda key: REFILL_LABELS[key], key="assessment_refill", on_change=invalidate_review)
    missing = missing_information(scores, uds_code, refill_code)
    if missing:
        st.warning("Assessment incomplete. Missing: " + "; ".join(missing) + ". No overall classification or repeat interval will be assigned.")
    else:
        st.success("All app-required assessment inputs are present. This does not establish clinical completeness.")
    with st.expander("How the app calculates points"):
        st.write(MODEL_NOTICE)
        st.dataframe(
            pd.DataFrame(risk_contributions(scores, uds_code, refill_code, contexts).items(), columns=["Input / rule", "Points"]),
            hide_index=True,
        )
        st.caption("Low: 0-1 points; Moderate: 2-4; High: 5+. PEG and PDI affect flags, not points. Missing data are not negative findings.")
    st.subheader("Documentation confirmations")
    diagnoses = st.multiselect(
        "Clinician-established diagnoses (optional; never inferred from scores)",
        list(DIAGNOSES), format_func=lambda code: f"{code} - {DIAGNOSES[code]}", key="assessment_diagnoses", on_change=invalidate_documentation,
    )
    minutes = st.number_input(
        "Actual QHP evaluation time / minutes (0 = not documented)",
        min_value=0, step=1, value=0, key="assessment_minutes", on_change=invalidate_time,
    )
    feedback = st.checkbox("I confirm assessment results were reviewed with the patient.", key="assessment_feedback", on_change=invalidate_documentation)
    time_confirmed = st.checkbox(
        "I attest I personally spent the actual minutes entered, excluding form completion and separately billed administration.",
        key="assessment_time_confirmed", on_change=invalidate_documentation,
    )
    clinician_verified = st.checkbox(
        "I am the reviewing clinician and have verified the assessment and generated documentation.", key="assessment_clinician_verified",
    )
    scores_verified = st.checkbox(
        "I verified/corrected every review field, resolved any parser errors, and verified the COMM form maximum.",
        key="assessment_scores_verified",
    )
    if time_confirmed and minutes == 0:
        st.error("Enter actual time greater than zero or uncheck the time attestation.")
    inputs = (
        dict(scores), tuple(contexts), uds_code, refill_code, minutes, feedback, time_confirmed,
        tuple(diagnoses), clinician_verified, scores_verified, st.session_state.get("assessment_synthetic", False),
    )
    if st.button(
        "Generate reviewed report", type="primary",
        disabled=bool(errors) or not scores_verified or (time_confirmed and minutes == 0),
    ):
        st.session_state["assessment_report_inputs"] = inputs
    if st.session_state.get("assessment_report_inputs") != inputs:
        return
    report, rows, flags, risk, repeat = make_report(
        scores, contexts, uds_code, refill_code, minutes,
        feedback_confirmed=feedback, time_confirmed=time_confirmed, diagnoses=tuple(diagnoses),
        clinician_verified=clinician_verified, synthetic=st.session_state.get("assessment_synthetic", False),
    )
    st.subheader(f"Integrated opioid risk level: {risk}")
    st.write(f"**Recommended repeat interval:** {repeat}")
    st.subheader("Score Summary")
    st.dataframe(pd.DataFrame(rows, columns=["Measure", "Score", "Interpretation"]), hide_index=True)
    st.subheader("Clinical Flags")
    for label, checked in flags.items():
        st.write(f"{'Not assessed:' if checked is None else 'Flagged:' if checked else 'Not flagged:'} {label}")
    st.subheader("Readable Report")
    st.text_area("Generated report", value=report, height=700, disabled=True)
    st.download_button(
        "Download readable report (.txt)",
        data=report, file_name="opioid_risk_report.txt", mime="text/plain", on_click="ignore",
    )


if __name__ == "__main__":
    main()
