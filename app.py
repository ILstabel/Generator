import html
import math
import os
import re
from typing import Any, Literal, TypedDict

import pandas as pd
import streamlit as st

from form_reader import FormInspection
from clinic_insights import clinic_insights_view
from patient_forms_ui import ReviewedForm, form_key, patient_forms_sidebar, review_patient_forms, saved_records_view, show_full_table
from patient_records import RecordError, patient_code, save_record
from risk_thresholds import (
    CUSTOM, DEFAULT, DEFAULT_PRESET, PRESETS, SECTIONS, Thresholds, make_thresholds, rule_label, rule_text,
    tiered_points, validate_cutoffs,
)
from scoring_config import CONFIG, band_label, band_table, instrument

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


class AssessmentDetails(TypedDict, total=False):
    phq9_items: list[float | None]
    phq9_function: str | None
    peg_items: list[float | None]
    peg_baseline: float | None
    pdi_items: list[float | None]
    pdi_baseline: float | None
    ort_version: Literal["Original ORT", "ORT-OUD"]
    ort_oud_items: list[bool | None]
    comm_items: list[float | None]
    source_form: str


class Scores(AssessmentDetails):
    peg_avg: float | None
    pdi: float | None
    phq9: float | None
    item9: float | None
    comm: float | None
    ort: float | None
    comm_max: int


class ParsedScores(TypedDict):
    scores: Scores
    errors: list[str]
    warnings: list[str]


ScoreKey = Literal["peg_avg", "pdi", "phq9", "item9", "comm", "ort"]
SCORE_LABELS: dict[ScoreKey, str] = {
    "peg_avg": "PEG average", "pdi": "PDI", "phq9": "PHQ-9",
    "item9": "PHQ-9 item #9", "comm": "COMM", "ort": "ORT",
}
DIAGNOSES = {
    "F11.20": "Opioid dependence, uncomplicated",
    "G89.4": "Chronic pain syndrome",
}
MODEL_NOTICE = (
    "App-defined decision support, not a validated clinical prediction model. "
    "The existing point formula and repeat intervals require clinician verification. "
    "As in the original HTML template, COMM points (>=9: 2; >=18: 3) apply to every COMM form and ORT points "
    "(>=4: 1; >=8: 3) apply to both Original ORT and ORT-OUD totals; these mappings are not validated for "
    "modified COMM forms or ORT-OUD."
)
PHQ9_FUNCTION = [
    "Not difficult at all", "Somewhat difficult", "Very difficult", "Extremely difficult",
]
PHQ9_SOURCE = "https://www.psychiatry.org/getmedia/a3986be5-94af-42e7-afce-19234c2f4998/APA-DSM5TR-SeverityMeasureForDepressionAdult.pdf"
PEG_SOURCE = "https://northwestpainguidance.org/wp-content/uploads/2016/05/PEG-3.pdf"
PDI_SOURCE = "https://pmc.ncbi.nlm.nih.gov/articles/PMC6137945/"
ORT_OUD_SOURCE = "https://nida.nih.gov/nidamed-medical-health-professionals/screening-tools-resources/opioid-risk-tool-oud-ort-oud"
COMM_SOURCE = "https://www.utahmed.org/Common/Uploaded%20files/Docs/CS_Resources/COMM%20-%20Current%20Opioid%20Misuse%20Measure.pdf"
ORT_OUD_FACTORS = [
    "Family history: alcohol abuse", "Family history: illegal drug abuse",
    "Family history: prescription drug abuse", "Personal history: alcohol abuse",
    "Personal history: illegal drug abuse", "Personal history: prescription drug abuse",
    "Age 16-45 years", "History of depression",
    "History of ADD, OCD, bipolar disorder or schizophrenia",
]
NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
LABEL_PATTERN = re.compile(
    r"(?<!\w)(?P<label>PHQ\s*-?\s*9\s+item\s*#?\s*9|Question\s*#?\s*9|Item\s*#?\s*9"
    r"|PEG(?:\s+(?:Average|Avg))?|PDI|PHQ\s*-?\s*9|COMM(?:\s*-?\s*(?:17|16|7))?|ORT(?:\s*-\s*OUD)?)"
    r"(?!\w)(?:[ \t]+(?:Score|Total))?[ \t]*(?:[:=.]?[ \t]*)(?:Answer[ \t]*:[ \t]*)?",
    re.IGNORECASE,
)


def empty_scores() -> Scores:
    return {
        "peg_avg": None, "pdi": None, "phq9": None,
        "item9": None, "comm": None, "ort": None, "comm_max": 68,
    }


def round_clinical(value: float) -> int:
    return math.floor(value + 0.5)


def instrument_version() -> str:
    return CONFIG["version"]


def item_errors(items: list[float | None], count: int, maximum: int, label: str) -> list[str]:
    if len(items) != count:
        return [f"{label} requires exactly {count} item positions (use blank for missing answers)."]
    return [
        f"{label} item {index} must be a whole number from 0-{maximum} or blank."
        for index, value in enumerate(items, 1)
        if value is not None and (
            not math.isfinite(value) or not 0 <= value <= maximum or value != int(value)
        )
    ]


class Phq9Calculation(TypedDict):
    answered: int
    raw_sum: float
    exact: float | None
    total: int | None
    prorated: bool
    provisional: bool


def blank_items(items: list[Any]) -> list[int]:
    """1-based positions of blank or unresolved responses."""
    return [index for index, value in enumerate(items, 1) if value is None]


def calculate_phq9(items: list[float | None]) -> Phq9Calculation:
    """Prorate 1-2 missing items; with more blanks, total the answered items as a provisional score."""
    errors = item_errors(items, 9, 3, "PHQ-9")
    if errors:
        raise ValueError("\n".join(errors))
    answered = [value for value in items if value is not None]
    raw_sum = sum(answered)
    exact = raw_sum * 9 / len(answered) if len(answered) >= 7 else raw_sum if answered else None
    return {
        "answered": len(answered), "raw_sum": raw_sum, "exact": exact,
        "total": round_clinical(exact) if exact is not None else None,
        "prorated": 7 <= len(answered) < 9,
        "provisional": 0 < len(answered) < 7,
    }


def calculate_peg(items: list[float | None]) -> float | None:
    """Mean of the answered items; blanks are skipped (provisional when any are blank)."""
    errors = item_errors(items, 3, 10, "PEG")
    if errors:
        raise ValueError("\n".join(errors))
    answered = [value for value in items if value is not None]
    return sum(answered) / len(answered) if answered else None


class PdiCalculation(TypedDict):
    answered: int
    raw_sum: float
    imputed_value: float | None
    total: float | None
    provisional: bool


def calculate_pdi(items: list[float | None]) -> PdiCalculation:
    """Mean-impute one missing domain; with more blanks, total the answered domains as a provisional score."""
    errors = item_errors(items, 7, 10, "PDI")
    if errors:
        raise ValueError("\n".join(errors))
    answered = [value for value in items if value is not None]
    raw_sum = sum(answered)
    imputed = raw_sum / 6 if len(answered) == 6 else None
    return {
        "answered": len(answered), "raw_sum": raw_sum, "imputed_value": imputed,
        "total": raw_sum if len(answered) == 7 else raw_sum * 7 / 6 if len(answered) == 6 else raw_sum if answered else None,
        "provisional": 0 < len(answered) < 6,
    }


def pdi_scoring_note(scores: Scores) -> str:
    if "pdi_items" not in scores:
        if scores["pdi"] is None:
            return "No PDI total documented."
        return "Entered total; individual responses and missing-domain count not verified by the app."
    result = calculate_pdi(scores["pdi_items"])
    if result["total"] is None:
        return "Not scored: all 7 domains blank or unresolved."
    if result["provisional"]:
        return (
            f"PROVISIONAL: domain(s) {', '.join(map(str, blank_items(scores['pdi_items'])))} blank - needs review. "
            f"Sum of the {result['answered']} answered domains = {result['total']:g}; blanks skipped, not scored as zero."
        )
    if result["imputed_value"] is not None:
        return (
            f"Mean-imputed: raw sum {result['raw_sum']:g} / 6 answered = {result['imputed_value']:.4f} "
            f"for the missing domain; total = {result['total']:.4f} / 70. Not a complete observed score."
        )
    return f"Complete: sum of all 7 domains = {result['total']:g}."


def pdi_change(scores: Scores) -> str:
    current, baseline = scores["pdi"], scores.get("pdi_baseline")
    if current is None or baseline is None:
        return "Change not assessed: a current and baseline PDI score are required."
    if baseline == 0:
        return "Percentage change undefined from a zero baseline; no percentage improvement conclusion assigned."
    reduction = (baseline - current) / baseline
    threshold = instrument("PDI")["improvement"]["min_percent_drop"]
    meaning = f"Meets the configured >={threshold}% improvement criterion." if reduction * 100 >= threshold else f"Does not meet the configured {threshold}% improvement criterion."
    return f"Baseline {baseline:g}; current {current:.4f}; reduction {reduction * 100:.1f}%. {meaning} Protocol-specific, not diagnostic."


def phq9_scoring_note(scores: Scores) -> str:
    if "phq9_items" not in scores:
        if scores["phq9"] is None:
            return "No PHQ-9 total documented."
        return "Entered total; individual responses and missing-item count not verified by the app."
    result = calculate_phq9(scores["phq9_items"])
    if result["total"] is None:
        return "Not scored: all 9 items blank or unresolved. Re-administer PHQ-9."
    if result["provisional"]:
        return (
            f"PROVISIONAL: item(s) {', '.join(map(str, blank_items(scores['phq9_items'])))} blank - needs review. "
            f"Sum of the {result['answered']} answered items = {result['total']}; blanks skipped, not scored as zero."
        )
    if result["prorated"]:
        return (
            f"Prorated: raw sum {result['raw_sum']:g} x 9 / {result['answered']} answered "
            f"= {result['exact']:.4f}; rounded to {result['total']}. "
            "Missing responses are not assumed to be zero."
        )
    return f"Complete: sum of all 9 responses = {result['total']}."


def peg_improvement_rule() -> str:
    rule = instrument("PEG")["improvement"]
    joiner = " OR " if rule["rule"] == "any" else " AND "
    return f"decrease >={rule['min_point_drop']:g} point{joiner}>={rule['min_percent_drop']:g}%"


def peg_change(scores: Scores) -> str:
    current, baseline = scores["peg_avg"], scores.get("peg_baseline")
    if current is None or baseline is None:
        return "Change not assessed: a current and prior PEG score are required."
    rule = instrument("PEG")["improvement"]
    decrease = baseline - current
    percent_drop = decrease / baseline * 100 if baseline > 0 else None
    percent = f"{percent_drop:.1f}% reduction" if percent_drop is not None else "percentage change undefined from a zero baseline"
    tests = [decrease >= rule["min_point_drop"], percent_drop is not None and percent_drop >= rule["min_percent_drop"]]
    improved = (any if rule["rule"] == "any" else all)(tests)
    if improved and decrease > 0:
        meaning = f"Meets the configured improvement criterion ({peg_improvement_rule()})."
    elif decrease > 0:
        meaning = f"Decrease is below the configured improvement criterion ({peg_improvement_rule()})."
    elif decrease == 0:
        meaning = "No change."
    else:
        meaning = "Score increased; assess worsening pain/interference."
    return f"Prior {baseline:g}; current mean {current:.4f}; decrease {decrease:.4f} points; {percent}. {meaning} Not diagnostic."


def calculate_ort_oud(items: list[bool | None]) -> int | None:
    if len(items) != 9 or any(value is not None and not isinstance(value, bool) for value in items):
        raise ValueError("ORT-OUD requires nine Yes/No responses (blank means missing).")
    return sum(value is True for value in items) if any(value is not None for value in items) else None


def calculate_comm(items: list[float | None], maximum: int = 68) -> float | None:
    if maximum not in {28, 64, 68}:
        raise ValueError("Select a supported COMM maximum (28, 64 or 68).")
    errors = item_errors(items, maximum // 4, 4, "COMM")
    if errors:
        raise ValueError("\n".join(errors))
    return sum(value for value in items if value is not None) if any(value is not None for value in items) else None


def comm_scoring_note(scores: Scores) -> str:
    form = "Standard 17-item COMM" if scores["comm_max"] == 68 else f"Modified {scores['comm_max'] // 4}-item form; standard >=9 threshold applied per original template"
    if "comm_items" not in scores:
        return form + ". Entered total; item completeness must be verified by the reviewer."
    items = scores["comm_items"]
    answered = [value for value in items if value is not None]
    blanks = blank_items(items)
    status = (
        "Complete sum; no reverse scoring." if not blanks else
        "Not scored: all items blank or unresolved." if not answered else
        f"PROVISIONAL: item(s) {', '.join(map(str, blanks))} blank - needs review; blanks skipped, not scored as zero."
    )
    return f"{form}. Answered {len(answered)}/{len(items)}; observed sum {sum(answered):g}. {status}"


def ort_level(value: float | None, version: str = "Original ORT") -> str:
    if value is None:
        return "Not documented"
    if version == "ORT-OUD":
        return band_label("ORT-OUD", value)
    return "Low Risk" if value <= 3 else "Moderate Risk" if value <= 7 else "High Risk"


def validate_scores(scores: Scores) -> list[str]:
    errors = []
    if "comm_items" in scores:
        maximum = scores["comm_max"]
        comm_errors = item_errors(scores["comm_items"], maximum // 4, 4, "COMM")
        errors.extend(comm_errors)
        if maximum in {28, 64, 68} and not comm_errors and scores["comm"] != calculate_comm(scores["comm_items"], maximum):
            errors.append("COMM total must match its item responses and selected form.")
    version = scores.get("ort_version", "Original ORT")
    if version not in {"Original ORT", "ORT-OUD"}:
        errors.append("Select Original ORT or ORT-OUD.")
    if "ort_oud_items" in scores:
        items = scores["ort_oud_items"]
        if len(items) != 9 or any(value is not None and not isinstance(value, bool) for value in items):
            errors.append("ORT-OUD requires nine Yes/No responses (blank means missing).")
        elif version != "ORT-OUD" or scores["ort"] != calculate_ort_oud(items):
            errors.append("ORT-OUD total must match its nine responses and selected version.")
    prorated = False
    pdi_imputed = False
    if "pdi_items" in scores:
        pdi_errors = item_errors(scores["pdi_items"], 7, 10, "PDI")
        errors.extend(pdi_errors)
        if not pdi_errors:
            pdi_result = calculate_pdi(scores["pdi_items"])
            pdi_imputed = pdi_result["imputed_value"] is not None
            if scores["pdi"] != pdi_result["total"]:
                errors.append("PDI total must match the seven-domain calculation.")
    if "phq9_items" in scores:
        phq_errors = item_errors(scores["phq9_items"], 9, 3, "PHQ-9")
        errors.extend(phq_errors)
        if not phq_errors:
            calculated = calculate_phq9(scores["phq9_items"])
            prorated = calculated["prorated"]
            if scores["phq9"] != calculated["total"] or scores["item9"] != scores["phq9_items"][8]:
                errors.append("PHQ-9 total and item #9 must match the item-by-item calculation.")
    if "peg_items" in scores:
        peg_errors = item_errors(scores["peg_items"], 3, 10, "PEG")
        errors.extend(peg_errors)
        if not peg_errors and scores["peg_avg"] != calculate_peg(scores["peg_items"]):
            errors.append("PEG mean must match the three entered responses.")
    baseline = scores.get("peg_baseline")
    if baseline is not None and (not math.isfinite(baseline) or not 0 <= baseline <= 10):
        errors.append("Prior PEG score must be 0-10 or blank.")
    pdi_baseline = scores.get("pdi_baseline")
    if pdi_baseline is not None and (not math.isfinite(pdi_baseline) or not 0 <= pdi_baseline <= 70):
        errors.append("Baseline PDI score must be 0-70 or blank.")
    if scores.get("phq9_function") is not None and scores["phq9_function"] not in PHQ9_FUNCTION:
        errors.append("Select a supported functional-impairment response or leave it blank.")
    limits = {"peg_avg": 10, "pdi": 70, "phq9": 27, "item9": 3, "comm": scores["comm_max"]}
    if version == "ORT-OUD":
        limits["ort"] = 9
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
        elif key != "peg_avg" and not (key == "pdi" and pdi_imputed) and value != int(value):
            errors.append(f"{label} must be a whole number.")
    if scores["phq9"] is not None and scores["item9"] is not None:
        if scores["item9"] > scores["phq9"]:
            errors.append("PHQ-9 item #9 cannot exceed the PHQ-9 total.")
        if not prorated and scores["phq9"] - scores["item9"] > 24:
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
            else "ort" if label == "ortoud"
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
            if item_errors(values, 3, 10, "PEG"):
                errors.append("Each PEG item must be a whole number from 0-10.")
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
            if reported and not (
                math.isclose(float(reported[1]), value, abs_tol=0.01)
                or float(reported[1]) == round_clinical(value)
            ):
                errors.append("PEG stated average conflicts with both its exact mean and rounded clinical score.")
        else:
            denominator = re.match(rf"/\s*({NUMBER})(?![\w.])", tail)
            if tail.startswith("/") and denominator is None and key != "ort":
                errors.append(f"{name}: unreadable denominator.")
            maxima = {"peg_avg": 10, "pdi": 70, "phq9": 27, "item9": 3}
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
                if label == "ortoud":
                    scores["ort_version"] = "ORT-OUD"
                    if denominator and float(denominator[1]) != 9:
                        errors.append("ORT-OUD: expected denominator 9.")
                stated = re.search(r"\b(Low|Moderate|High)(?:\s+Risk)?\b", tail, re.IGNORECASE)
                if stated and stated[1].lower() != ort_level(value, scores.get("ort_version", "Original ORT")).split()[0].lower():
                    errors.append("ORT stated risk conflicts with its numeric score.")
        scores[key] = value
    errors.extend(validate_scores(scores))
    if not matches and clean.strip():
        errors.append("No supported score labels were recognized. Correct the text or use manual entry.")
    return {"scores": scores, "errors": errors, "warnings": warnings}


def peg_interference(value: float | None) -> str:
    """Pain-interference wording from the original HTML template (PEG has no configured bands)."""
    if value is None:
        return "Not found"
    if value < 4:
        return "Low pain interference"
    if value <= 6:
        return "Moderate pain interference"
    return "High pain interference"


def severity_pdi(value: float | None) -> str:
    if value is None:
        return "Not found"
    return f"{band_label('PDI', value)} (configured band; screening result, not a diagnosis)"


def severity_phq9(value: float | None, item9: float | None = None) -> str:
    if value is None:
        return "Not found"
    label = band_label("PHQ-9", value)
    guardrail = instrument("PHQ-9")["guardrail"]
    if item9 is not None and item9 >= guardrail["trigger_min"]:
        return f"{guardrail['label']}. Total-score band: {label}"
    return label


def severity_comm(value: float | None, maximum: int = 68) -> str:
    if value is None:
        return "Not found"
    if maximum != 68:
        return band_label("COMM", value) + " (standard 17-item threshold applied to modified form, per original template)"
    return band_label("COMM", value)


def comm_signal(value: float | None) -> str:
    """COMM wording from the original HTML template."""
    if value is None:
        return "Not found"
    return "Elevated opioid misuse-risk signal" if value >= 9 else "Below elevated misuse-risk threshold"


def missing_information(scores: Scores, uds_code: str, refill_code: str) -> list[str]:
    """Missing inputs that block the overall risk level (see pending_review for non-blocking items)."""
    missing = [
        SCORE_LABELS[key] for key in ("peg_avg", "pdi", "comm", "ort")
        if scores[key] is None
    ]
    if scores["phq9"] is None:
        missing.append("PHQ-9 total")
    for key, (label, names) in ITEM_LABELS.items():
        blanks = blank_items(scores.get(key, []))
        # One blank PHQ-9 item (prorated) or PDI domain (mean-imputed) does not block the risk level.
        if blanks and len(blanks) < len(scores[key]) and not (key in {"phq9_items", "pdi_items"} and len(blanks) == 1):
            missing.append(f"{label} {_blank_text(blanks, names)} blank - needs review (total calculated by skipping blanks)")
    if scores["phq9"] is not None and scores["item9"] is None:
        missing.append("PHQ-9 item #9")
    return missing


def pending_review(scores: Scores, uds_code: str, refill_code: str) -> list[str]:
    """Items to review that do not block the overall risk level (they add 0 points, as in the original HTML)."""
    pending = []
    for key in ("phq9_items", "pdi_items"):
        blanks = blank_items(scores.get(key, []))
        if len(blanks) == 1 and key in scores and not (key == "phq9_items" and blanks == [9]):
            label, names = ITEM_LABELS[key]
            pending.append(f"{label} {_blank_text(blanks, names)} blank - needs review ({'prorated' if key == 'phq9_items' else 'mean-imputed'})")
    if uds_code in {"not_reviewed", "uds_pending_pdmp_ok"}:
        pending.append("UDS/PDMP review (0 points until reviewed)")
    if refill_code == "not_reviewed":
        pending.append("Refill behavior review (0 points until reviewed)")
    return pending


ITEM_LABELS: dict[str, tuple[str, tuple[str, ...] | None]] = {
    "phq9_items": ("PHQ-9", None), "peg_items": ("PEG", None), "pdi_items": ("PDI", None),
    "ort_oud_items": ("ORT-OUD", tuple(ORT_OUD_FACTORS)), "comm_items": ("COMM", None),
}


def _blank_text(blanks: list[int], names: tuple[str, ...] | None) -> str:
    return "; ".join(names[index - 1] for index in blanks) if names else "item(s) " + ", ".join(map(str, blanks))


def active_thresholds() -> Thresholds:
    """Thresholds chosen in the sidebar for this browser session; the original template outside a running app."""
    try:
        value = st.session_state.get("risk_thresholds", DEFAULT)
    except Exception:
        return DEFAULT
    return value if isinstance(value, Thresholds) else DEFAULT


def risk_contributions(
    scores: Scores, uds_code: str, refill_code: str, contexts: list[str], thresholds: Thresholds | None = None,
) -> dict[str, int]:
    """Point rules from the original HTML template; COMM and ORT thresholds apply to every form version.

    Thresholds for COMM, ORT and PHQ-9 follow the selected preset (default: original template).
    """
    thresholds = thresholds or active_thresholds()
    contributions: dict[str, int] = {}
    form = "COMM" if scores["comm_max"] == 68 else f"Modified COMM-{scores['comm_max'] // 4}"
    contributions[f"{form} ({rule_label('COMM', thresholds)})"] = tiered_points(scores["comm"], "COMM", thresholds)
    version = "ORT-OUD" if scores.get("ort_version") == "ORT-OUD" else "Original ORT"
    contributions[f"{version} ({rule_label('ORT', thresholds)})"] = tiered_points(scores["ort"], "ORT", thresholds)
    if scores["phq9"] is not None:
        contributions[f"PHQ-9 ({rule_label('PHQ-9', thresholds)})"] = tiered_points(scores["phq9"], "PHQ-9", thresholds)
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


def risk_level(
    scores: Scores, uds_code: str, refill_code: str, contexts: list[str], thresholds: Thresholds | None = None,
) -> str:
    errors = validate_scores(scores)
    if errors:
        raise ValueError("\n".join(errors))
    if uds_code not in UDS_LABELS or refill_code not in REFILL_LABELS or any(code not in CONTEXT_LABELS for code in contexts):
        raise ValueError("Unknown clinical context, UDS/PDMP or refill selection.")
    if missing_information(scores, uds_code, refill_code):
        return "Insufficient information"
    thresholds = thresholds or active_thresholds()
    points = sum(risk_contributions(scores, uds_code, refill_code, contexts, thresholds).values())
    moderate, high = thresholds.get("Overall")
    return "High" if points >= high else "Moderate" if points >= moderate else "Low"


def monitoring_interval(risk: str) -> str:
    if risk == "High":
        return "Repeat battery every 3 months"
    if risk == "Moderate":
        return "Repeat battery every 6 months"
    if risk == "Low":
        return "Repeat battery yearly / every 12 months"
    return "Not assigned: complete the assessment and obtain clinician review"


def qhp_time_allocation(minutes: int) -> dict[str, int]:
    """Split total QHP minutes as the original HTML template does (20/35/25/15%, remainder to feedback)."""
    review = max(1, round_clinical(minutes * 0.20))
    integration = max(1, round_clinical(minutes * 0.35))
    decision = max(1, round_clinical(minutes * 0.25))
    documentation = max(1, round_clinical(minutes * 0.15))
    feedback = max(0, minutes - review - integration - decision - documentation)
    documentation += minutes - (review + integration + decision + documentation + feedback)
    return {"review": review, "integration": integration, "decision": decision, "documentation": documentation, "feedback": feedback}


def report_sections(report: str) -> list[tuple[str, str]]:
    """Split the readable report into (heading, body) pairs at its ===== section banners."""
    parts = re.split(r"\n=+\n(.+)\n=+\n", report)
    return [(parts[index].strip().title(), parts[index + 1].strip()) for index in range(1, len(parts) - 1, 2)]


def score_displays(scores: Scores) -> dict[str, str]:
    """Display strings and template wording shared by the score summary and the clinical impression."""
    phq_label = "PHQ-9"
    phq_value = scores["phq9"]
    phq_interpretation = severity_phq9(scores["phq9"], scores["item9"])
    if scores["phq9"] is not None and "Total-score band" not in phq_interpretation:
        phq_interpretation = f"{band_label('PHQ-9', scores['phq9']).split(' (')[0].capitalize()} depressive symptoms"
    ort_version = scores.get("ort_version", "Original ORT")
    ort_interpretation = ort_level(scores["ort"], ort_version)
    return {
        "peg": f"{scores['peg_avg']:.2f} / 10" if scores["peg_avg"] is not None else "Not found",
        "peg_interpretation": peg_interference(scores["peg_avg"]),
        "pdi": f"{scores['pdi']:g} / 70" if scores["pdi"] is not None else "Not found",
        "pdi_interpretation": band_label("PDI", scores["pdi"]) if scores["pdi"] is not None else "Not found",
        "phq_label": phq_label,
        "phq_display": f"{phq_value:g} / 27" if phq_value is not None else "Not found",
        "phq_interpretation": phq_interpretation,
        "comm": f"{scores['comm']:g}" if scores["comm"] is not None else "Not found",
        "comm_interpretation": comm_signal(scores["comm"]),
        "ort_version": ort_version,
        "ort_interpretation": ort_interpretation,
        "ort": f"{scores['ort']:g}{' / 9' if ort_version == 'ORT-OUD' else ''} / {ort_interpretation}" if scores["ort"] is not None else "Not found",
    }


def suicide_text(item9: float | None) -> str:
    if item9 is not None and item9 > 0:
        return (
            "PHQ-9 item #9 is positive. Immediate suicide risk assessment and safety protocol are required, including assessment "
            "of passive versus active suicidal ideation, plan, intent, access to means, protective factors, "
            "clinical judgment of acute risk level, safety planning, crisis resources, and disposition."
        )
    if item9 == 0:
        return (
            "PHQ-9 item #9 = 0. No suicidal ideation endorsed on this measure. Same-day suicide-risk escalation was not "
            "triggered by the PHQ-9 response today."
        )
    return "PHQ-9 item #9 not documented. Assess suicide risk if clinically indicated or if depressive symptoms are elevated."


def clinical_impression(
    scores: Scores, contexts: list[str], uds_code: str, refill_code: str, risk: str, context_documented: bool = True,
) -> str:
    """Score-by-score interval impression shown in the on-screen summary (formatted HTML template version)."""
    shown = score_displays(scores)
    context_text = "; ".join(CONTEXT_LABELS[c] for c in (contexts or ["routine"])) if context_documented else "Not documented"
    comm = f"{shown['comm']} / {scores['comm_max']}" if scores["comm"] is not None else shown["comm"]
    return (
        f"Interval psychological/behavioral testing was completed in the context of {context_text}. "
        f"Results demonstrate {shown['peg_interpretation'].lower()} with PEG average score of {shown['peg']} and "
        f"{shown['pdi_interpretation'].lower()} with PDI score of {shown['pdi']}. {shown['phq_label']} score of "
        f"{shown['phq_display']} is consistent with {shown['phq_interpretation'].lower()}. {suicide_text(scores['item9'])}\n\n"
        f"Opioid-risk findings were reviewed in the context of chronic opioid monitoring. COMM score of {comm} is interpreted as "
        f"{shown['comm_interpretation']}, and {shown['ort_version']} score of {shown['ort']} reflects baseline opioid-risk factors. "
        f"UDS/PDMP status: {UDS_LABELS[uds_code]}. Refill behavior: {REFILL_LABELS[refill_code]}. "
        + (f"The integrated profile supports an overall {risk} opioid risk level." if risk != "Insufficient information" else
           "An overall opioid risk level cannot be assigned until the missing information is completed.")
    )


def make_report(
    scores: Scores, contexts: list[str], uds_code: str, refill_code: str, minutes: int = 0,
    *, feedback_confirmed: bool = False, time_confirmed: bool = False,
    diagnoses: tuple[str, ...] = (), clinician_verified: bool = False, synthetic: bool = False,
    context_documented: bool = True, thresholds: Thresholds | None = None,
) -> tuple[str, list[tuple[str, str, str]], dict[str, bool | None], str, str]:
    if minutes < 0 or minutes != int(minutes):
        raise ValueError("Actual QHP time must be a non-negative whole number of minutes.")
    if time_confirmed and minutes <= 0:
        raise ValueError("Enter actual time greater than zero before confirming the time attestation.")
    if any(code not in DIAGNOSES for code in diagnoses):
        raise ValueError("Unknown diagnosis selection.")
    if not contexts:
        contexts = ["routine"]
    thresholds = thresholds or active_thresholds()
    risk = risk_level(scores, uds_code, refill_code, contexts, thresholds)
    context_text = "; ".join(CONTEXT_LABELS[c] for c in contexts) if context_documented else (
        "Not documented: automatic record from scanned form; clinician must review clinical context"
    )
    uds = UDS_LABELS[uds_code]
    refill = REFILL_LABELS[refill_code]
    time_total = f"{minutes} minutes" if minutes else "Not documented"
    repeat = monitoring_interval(risk)
    shown = score_displays(scores)
    peg, pdi, phq_label, phq_display = shown["peg"], shown["pdi"], shown["phq_label"], shown["phq_display"]
    comm_display, ort_version, ort_display = shown["comm"], shown["ort_version"], shown["ort"]
    item9 = scores["item9"]
    suicide = suicide_text(item9)

    contexts_concern = {"worsening", "escalation", "elevated_misuse", "mood", "discordant", "aberrancy_history"}
    context_flags = [CONTEXT_LABELS[c] for c in contexts if c in contexts_concern]
    mood = scores["phq9"]
    flags: dict[str, bool | None] = {
        "PEG ≥ 7 — severe pain impact": None if scores["peg_avg"] is None else scores["peg_avg"] >= 7,
        "PDI ≥ 41 — severe disability": None if scores["pdi"] is None else scores["pdi"] >= 41,
        "Elevated mood symptom burden": None if mood is None else mood >= 15,
        "PHQ-9 item #9 > 0 — suicide risk assessment indicated": None if item9 is None else item9 > 0,
        "COMM >= 9 — elevated opioid misuse-risk signal": None if scores["comm"] is None else scores["comm"] >= 9,
        "ORT-OUD high screening risk (>=3)" if ort_version == "ORT-OUD" else "ORT moderate/high baseline risk": None if scores["ort"] is None else scores["ort"] >= (3 if ort_version == "ORT-OUD" else 4),
        "Worsening trajectory / function concern from clinical context": "worsening" in contexts,
        "Opioid escalation request from clinical context": "escalation" in contexts,
        "; ".join(context_flags) if context_flags else "Clinical context does not independently raise risk": bool(context_flags),
        "UDS/PDMP concern or closer monitoring indicated": None if uds_code in {"not_reviewed", "uds_pending_pdmp_ok"} else uds_code in {"requires_review", "discordant"},
        "Refill behavior concern / closer monitoring indicated": None if refill_code == "not_reviewed" else refill_code in {"intermittent", "early_or_escalation", "lost_stolen", "requires_review"},
    }

    allocation = qhp_time_allocation(minutes) if minutes else None
    rows = [
        ("Integrated Opioid Risk", risk, "Overall opioid risk classification"),
        ("Recommended Repeat Interval", repeat, "Risk-stratified battery repeat interval"),
        ("PEG Average", peg, shown["peg_interpretation"]),
        ("PDI", pdi, shown["pdi_interpretation"]),
        (phq_label, phq_display, shown["phq_interpretation"]),
        ("PHQ-9 Item #9", f"{item9:g}" if item9 is not None else "Not documented", "Positive SI item; risk assessment indicated" if item9 is not None and item9 > 0 else "No SI endorsed on item #9" if item9 == 0 else "Not documented"),
        ("COMM", comm_display, shown["comm_interpretation"]),
        (ort_version, ort_display, shown["ort_interpretation"]),
        ("Clinical Context", "Selected", context_text),
        ("UDS / PDMP", "Selected", uds),
        ("Refill Behavior", "Selected", refill),
        ("QHP Evaluation Time", time_total, "Professional interpretation/integration time"),
    ]
    rows.extend(("Billing ICD-10", code, DIAGNOSES[code]) for code in diagnoses)
    rows += [
        ("PEG Change", peg_change(scores), f"Comparison uses unrounded means when available; configured improvement criterion: {peg_improvement_rule()}"),
        ("PDI Scoring Method", pdi_scoring_note(scores), "One missing domain: mean imputation; two or more: answered domains totalled (provisional)"),
        ("PDI Change", pdi_change(scores), f"Configured protocol: >={instrument('PDI')['improvement']['min_percent_drop']}% reduction from baseline; not a universal diagnostic threshold"),
        ("COMM Scoring Method", comm_scoring_note(scores), "Past 30 days; each item 0-4; standard form has 17 items"),
        ("PHQ-9 Scoring Method", phq9_scoring_note(scores), "Past 2 weeks; items 1-9 scored 0-3"),
        ("PHQ-9 Functional Impairment (item 10)", scores.get("phq9_function") or "Not documented", "Work, home life and relationships; excluded from the 0-27 total and risk points"),
    ]
    if "phq9_items" in scores:
        rows.append(("PHQ-9 Responses (1-9)", ", ".join("Missing" if value is None else f"{value:g}" for value in scores["phq9_items"]), "Missing/unclear answers remain missing"))
    if "peg_items" in scores:
        rows.append(("PEG Responses (P, E, G)", ", ".join("Missing" if value is None else f"{value:g}" for value in scores["peg_items"]), "Mean of answered items; blanks skipped and flagged for review"))
    if "pdi_items" in scores:
        rows.append(("PDI Responses (7 domains)", ", ".join("Missing" if value is None else f"{value:g}" for value in scores["pdi_items"]), "Missing/unresolved answers are not zero"))
    if "ort_oud_items" in scores:
        rows.extend(
            (f"ORT-OUD: {factor}", "Missing" if value is None else "Yes (1)" if value else "No (0)", "Blank answers skipped in the total and flagged for review")
            for factor, value in zip(ORT_OUD_FACTORS, scores["ort_oud_items"])
        )
    if "comm_items" in scores:
        rows.append(("COMM Responses", ", ".join("Missing" if value is None else f"{value:g}" for value in scores["comm_items"]), "No reverse scoring; blanks are not zero"))
    if "source_form" in scores:
        rows.append(("Imported Patient Form", scores["source_form"], "Folder date label; responses manually reviewed after local optical detection"))
    missing = missing_information(scores, uds_code, refill_code)
    pending = pending_review(scores, uds_code, refill_code)
    completeness = (
        "Incomplete: " + "; ".join(missing) if missing else
        "Complete for the risk level; pending review: " + "; ".join(pending) if pending else
        "Complete for app-required inputs (not a comprehensive clinical assessment)"
    )
    rows.insert(12 + len(diagnoses), ("Assessment Completeness", completeness, "Missing data are not negative findings"))
    if not thresholds.is_default:
        rows.append(("Risk Thresholds", thresholds.preset, "Non-default thresholds (local choice, not validated): " + thresholds.describe()))
        completeness_line_thresholds = (
            f"\nRISK THRESHOLDS: {thresholds.preset} - non-default thresholds (local choice, not validated): {thresholds.describe()}"
        )
    else:
        completeness_line_thresholds = ""

    flag_lines = "\n".join(f"{'[?] Not assessed:' if checked is None else '[x]' if checked else '[ ]'} {label}" for label, checked in flags.items())
    rows_text = "\n".join(f"{name}: {value}\n  Interpretation: {meaning}" for name, value, meaning in rows[:12 + len(diagnoses)])
    feedback_text = (
        "Results were reviewed with the patient, including pain interference, functional disability, mood screening, "
        "suicide-risk screen response, opioid misuse-risk screening, integrated opioid risk level, UDS/PDMP and refill-behavior "
        "context, and recommended battery repeat interval / monitoring plan."
        if feedback_confirmed else "Patient feedback not confirmed; review with the patient is not documented."
    )
    diagnosis_text = "\n".join(f"{code} - {DIAGNOSES[code]}" for code in diagnoses) or "None selected."
    if allocation:
        time_lines = (
            "Time Allocation:\n"
            f"- Review/scoring of completed measures: {allocation['review']} minutes\n"
            "- Interpretation/integration with clinical data, UDS/PDMP/refill behavior, mood/suicide-risk screen, clinical context, "
            f"and opioid-risk factors: {allocation['integration']} minutes\n"
            f"- Clinical decision-making, opioid-risk stratification, and treatment/monitoring plan: {allocation['decision']} minutes\n"
            f"- Documentation/reporting: {allocation['documentation']} minutes\n"
            f"- Feedback/care coordination as indicated: {allocation['feedback']} minutes\n\n"
            "Time included review of completed interval testing measures; scoring and interpretation of pain/function, mood/safety, "
            "and opioid-risk screening results; integration with UDS/PDMP status, refill behavior, clinical context/trigger, and "
            "relevant clinical data; clinical decision-making; opioid-risk stratification; treatment planning; documentation/reporting; "
            "and feedback/care coordination as indicated.\n\n"
            "Time excluded patient form-completion time and any separately billed administration time."
        )
    else:
        time_lines = "No time allocation: enter the actual QHP minutes to generate one."
    attestation = (
        f"\n\nAttestation: I personally spent {minutes} minutes performing the psychological testing evaluation service. "
        f"This included review/scoring of completed measures ({allocation['review']} minutes), interpretation/integration with "
        f"clinical and opioid-risk data ({allocation['integration']} minutes), clinical decision-making/treatment planning "
        f"({allocation['decision']} minutes), documentation/reporting ({allocation['documentation']} minutes), and feedback/care "
        f"coordination as indicated ({allocation['feedback']} minutes)."
        if time_confirmed and allocation else ""
    )
    risk_sentence = (
        f"The integrated profile supports an overall {risk} opioid risk level." if risk != "Insufficient information" else
        "An overall opioid risk level cannot be assigned until the missing information is completed."
    )
    status = "CLINICIAN REVIEW CONFIRMED BY USER" if clinician_verified else "DRAFT - CLINICIAN VERIFICATION REQUIRED"
    header = f"SYNTHETIC TEST DATA - NOT FOR PATIENT DOCUMENTATION\n{status}" if synthetic else status
    completeness_line = "" if not (missing or pending) else f"\nASSESSMENT COMPLETENESS: {completeness}"
    review_notes = [
        f"- {name}: {note}" for name, note in (
            ("PHQ-9", phq9_scoring_note(scores)), ("PDI", pdi_scoring_note(scores)), ("COMM", comm_scoring_note(scores)),
        ) if any(word in note for word in ("PROVISIONAL", "Mean-imputed", "Prorated", "Not scored", "Modified"))
    ]
    if "peg_items" in scores and blank_items(scores["peg_items"]):
        review_notes.append(f"- PEG: PROVISIONAL: item(s) {', '.join(map(str, blank_items(scores['peg_items'])))} blank - needs review; mean of answered items.")
    if review_notes:
        completeness_line += "\nREVIEW NOTES:\n" + "\n".join(review_notes)
    report = f"""{header}

INTEGRATED OPIOID RISK LEVEL: {risk.upper()}
RECOMMENDED REPEAT INTERVAL: {repeat}{completeness_line_thresholds}{completeness_line}

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
Interval psychological/behavioral testing was completed in the context of {context_text}. Results were reviewed and integrated across pain interference, functional disability, mood/suicide-risk screening, opioid misuse-risk findings, baseline opioid-risk factors, UDS/PDMP status, refill behavior, and documented clinical context.

Clinical context / trigger: {context_text}

UDS / PDMP: {uds}

Refill behavior: {refill}

{suicide}

Opioid-risk findings were reviewed in the context of chronic opioid monitoring. COMM findings, ORT risk factors, UDS/PDMP status, refill behavior, clinical context/trigger, mood/safety screening, pain interference, and functional trajectory were integrated to determine the overall opioid-risk category. {risk_sentence}

============================================================
INTEGRATED OPIOID RISK INTERPRETATION
============================================================
Integrated opioid risk level is {risk}. This rating incorporates opioid-specific risk tools, current medication-use behavior, UDS/PDMP status, refill behavior, clinical context/trigger, mood burden, suicide-risk screening, pain interference, functional disability, and trajectory over time.

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

{time_lines}{attestation}"""
    return report, rows, flags, risk, repeat


SAMPLES = {
    "Low": "PEG: 3 + 3 + 3\nPDI: 12\nPHQ9: 3\nQuestion 9: 0\nCOMM: 2 / 68\nORT: 2 / Low Risk",
    "Moderate": "PEG: 5 + 6 + 5\nPDI: 28\nPHQ9: 8\nQuestion 9: 0\nCOMM: 9 / 68\nORT: 3 / Low Risk",
    "High": "PEG: 7 + 8 + 7\nPDI: 45\nPHQ9: 12\nQuestion 9: 0\nCOMM: 18 / 68\nORT: 8 / High Risk",
    "Incomplete": "PEG Average: 8 / 10\nPHQ9: 15\nQuestion 9: 1",
}


def reset_assessment() -> None:
    for key in list(st.session_state):
        if key.startswith("assessment_"):
            del st.session_state[key]


def invalidate_parse() -> None:
    st.session_state["assessment_ready"] = False
    st.session_state.pop("assessment_report_inputs", None)
    invalidate_review()
    st.session_state["assessment_time_confirmed"] = False


def invalidate_review() -> None:
    st.session_state["assessment_scores_verified"] = False
    st.session_state["assessment_clinician_verified"] = False
    st.session_state["assessment_feedback"] = False


def change_ort_version() -> None:
    invalidate_review()
    st.session_state["assessment_ort"] = None


def change_comm_form() -> None:
    invalidate_review()
    st.session_state["assessment_comm"] = None


def invalidate_documentation() -> None:
    st.session_state["assessment_clinician_verified"] = False


def invalidate_time() -> None:
    invalidate_documentation()
    st.session_state["assessment_time_confirmed"] = False


def load_parsed_scores() -> None:
    text = st.session_state.get("assessment_text", "")
    parsed = parse_scores(text)
    for key in SCORE_LABELS:
        st.session_state[f"assessment_{key}"] = parsed["scores"][key]
    st.session_state["assessment_comm_max"] = parsed["scores"]["comm_max"]
    st.session_state["assessment_ort_version"] = parsed["scores"].get("ort_version", "Original ORT")
    errors = parsed["errors"]
    if text and text == st.session_state.get("assessment_autofill_text") and st.session_state.get("assessment_form_items"):
        # Unedited auto-filled text: keep the scanned items so imputed/provisional totals validate against them.
        scores = {**empty_scores(), **parsed["scores"]}
        attach_form_items(scores)
        errors = validate_scores(scores)
    else:
        for key in ("source_form", "source_folder", "source_filename", "source_token", "form_items"):
            st.session_state.pop(f"assessment_{key}", None)
    st.session_state["assessment_peg_baseline"] = None
    st.session_state["assessment_pdi_baseline"] = None
    st.session_state["assessment_parse_errors"] = errors
    st.session_state["assessment_parse_warnings"] = parsed["warnings"]
    st.session_state["assessment_ready"] = True
    invalidate_review()
    st.session_state["assessment_time_confirmed"] = False
    st.session_state.pop("assessment_report_inputs", None)


def scores_from_form(values: dict[str, list[float | None]]) -> Scores:
    errors = item_errors(values["ORT-OUD"], 9, 1, "ORT-OUD")
    if errors:
        raise ValueError("\n".join(errors))
    scores = empty_scores()
    phq9 = calculate_phq9(values["PHQ-9"])
    scores["phq9_items"] = values["PHQ-9"]
    scores["phq9"], scores["item9"] = phq9["total"], values["PHQ-9"][8]
    scores["peg_items"] = values["PEG"]
    scores["peg_avg"] = calculate_peg(values["PEG"])
    scores["pdi_items"] = values["PDI"]
    scores["pdi"] = calculate_pdi(values["PDI"])["total"]
    scores["comm_max"] = 64
    scores["comm_items"] = values["COMM-16"]
    scores["comm"] = calculate_comm(values["COMM-16"], 64)
    # Scanned form orders age/comorbidities first; the assessment lists family history first.
    scores["ort_oud_items"] = [
        None if values["ORT-OUD"][index] is None else bool(values["ORT-OUD"][index])
        for index in (6, 7, 8, 3, 4, 5, 0, 1, 2)
    ]
    scores["ort_version"] = "ORT-OUD"
    scores["ort"] = calculate_ort_oud(scores["ort_oud_items"])
    return scores


def overall_form_risk(scores: Scores) -> str:
    """Overall risk before UDS/PDMP, refill and clinical context are reviewed (they add 0 points until then)."""
    if validate_scores(scores):
        return "Not assigned: score errors."
    missing = missing_information(scores, "not_reviewed", "not_reviewed")
    if missing:
        return "Insufficient information: " + "; ".join(missing)
    risk = risk_level(scores, "not_reviewed", "not_reviewed", ["routine"])
    points = sum(risk_contributions(scores, "not_reviewed", "not_reviewed", ["routine"]).values())
    return f"{risk} ({points} points; {monitoring_interval(risk).lower()}). UDS/PDMP, refill and clinical context still to review."


def form_summary(values: dict[str, list[float | None]]) -> list[tuple[str, str]]:
    scores = scores_from_form(values)
    peg = scores["peg_avg"]
    phq = scores["phq9"]
    peg_note = (
        f"PROVISIONAL: item(s) {', '.join(map(str, blank_items(scores['peg_items'])))} blank - needs review; mean of answered items. "
        if blank_items(scores["peg_items"]) else ""
    )
    ort_blanks = [ORT_OUD_FACTORS[index - 1] for index in blank_items(scores["ort_oud_items"])]
    ort_note = f" PROVISIONAL: blank - needs review: {'; '.join(ort_blanks)}." if ort_blanks else ""
    return [
        ("PHQ-9", f"{phq:g} / 27; {severity_phq9(phq, scores['item9'])}. {phq9_scoring_note(scores)}" if phq is not None else phq9_scoring_note(scores)),
        ("PHQ-9 item 9", "Missing / unresolved - needs review" if scores["item9"] is None else f"{scores['item9']:g}"),
        ("PEG", "Not scored: all items blank or unresolved" if peg is None else f"{peg_note}{round_clinical(peg)} / 10; exact mean {peg:.4f}"),
        ("PDI", f"{scores['pdi']:g} / 70; {severity_pdi(scores['pdi'])}. {pdi_scoring_note(scores)}" if scores["pdi"] is not None else pdi_scoring_note(scores)),
        ("ORT-OUD", "Not scored: all items blank or unresolved" if scores["ort"] is None else f"{scores['ort']:g} / 9; {ort_level(scores['ort'], 'ORT-OUD')}{'.' + ort_note if ort_note else ''}"),
        ("Modified COMM-16", f"{scores['comm']:g} / 64. {comm_scoring_note(scores)}" if scores["comm"] is not None else comm_scoring_note(scores)),
        ("Overall risk", overall_form_risk(scores)),
    ]


def save_form_record(folder: str, filename: str, values: dict[str, list[float | None]], status: str) -> tuple[bool, str]:
    """Calculate a scanned form and save its generator output under the patient code from the filename."""
    code = patient_code(filename)
    if code is None:
        return False, f"{folder} / {filename}: not saved - rename the PDF to the patient code, for example 10001.pdf."
    scores = scores_from_form(values)
    scores["source_form"] = f"{folder} / {filename}"
    errors = validate_scores(scores)
    if errors:
        return False, f"{folder} / {filename}: not saved - " + "; ".join(errors)
    report, rows, flags, risk, repeat = make_report(
        scores, [], "not_reviewed", "not_reviewed", context_documented=False,
    )
    banner = (
        "AUTOMATIC RECORD - OPTICALLY DETECTED RESPONSES NOT VERIFIED. DO NOT USE CLINICALLY UNTIL REVIEWED."
        if status == "auto_unverified" else
        "FORM RESPONSES VERIFIED BY USER. UDS/PDMP, refill, clinical context and clinician report still pending."
    )
    try:
        return save_record(
            code, folder, status, source_pdf=filename, report=f"{banner}\nPatient code: {code}\n\n{report}",
            rows=rows, flags=flags, risk=risk, repeat=repeat, scores=dict(scores),
        )
    except (RecordError, OSError) as error:
        return False, f"{folder} / {filename}: not saved - {error}"


def load_reviewed_form(form: ReviewedForm) -> None:
    if not form.verified:
        raise ValueError("Verify every extracted form response before loading an assessment.")
    scores = scores_from_form(form.values)
    errors = validate_scores(scores)
    if errors:
        raise ValueError("\n".join(errors))
    import_form_scores(form.inspection, scores)
    st.session_state["assessment_mode"] = "Manual entry"


def form_score_text(inspection: FormInspection, scores: Scores) -> str:
    """Paste-format score lines for a calculated form; unscored measures are omitted."""
    code = patient_code(inspection.filename) or inspection.filename
    lines = [f"Source: {code}, visit {inspection.folder} (automatic optical detection, not verified)"]
    if scores["phq9"] is not None:
        lines.append(f"PHQ-9: {scores['phq9']:g} / 27")
    if scores["item9"] is not None:
        lines.append(f"PHQ-9 item 9: {scores['item9']:g}")
    peg_items = scores["peg_items"]
    if all(value is not None for value in peg_items):
        lines.append("PEG: " + " + ".join(f"{value:g}" for value in peg_items))
    elif scores["peg_avg"] is not None:
        lines.append(f"PEG average: {scores['peg_avg']:g} / 10 (provisional: blank item skipped)")
    if scores["pdi"] is not None:
        lines.append(f"PDI: {scores['pdi']:g} / 70")
    if scores["ort"] is not None:
        lines.append(f"ORT-OUD: {scores['ort']:g} / 9")
    if scores["comm"] is not None:
        lines.append(f"COMM-16: {scores['comm']:g} / 64")
    return "\n".join(lines)


def autofill_from_form(inspection: FormInspection, values: dict[str, list[float | None]]) -> None:
    """Fill the paste-scores box and review fields from a calculated (unverified) scanned form."""
    try:
        scores = scores_from_form(values)
    except ValueError:
        return
    if validate_scores(scores):
        return
    import_form_scores(inspection, scores)
    st.session_state["assessment_mode"] = "Paste text"
    st.session_state["assessment_text"] = form_score_text(inspection, scores)
    st.session_state["assessment_autofill_text"] = st.session_state["assessment_text"]
    st.session_state["assessment_ready"] = True
    st.session_state["assessment_parse_errors"] = []
    st.session_state["assessment_parse_warnings"] = []
    st.session_state["assessment_autofilled"] = True


def import_form_scores(inspection: FormInspection, scores: Scores) -> None:
    reset_assessment()
    st.session_state["assessment_source_form"] = f"{inspection.folder} / {inspection.filename}"
    st.session_state["assessment_source_folder"] = inspection.folder
    st.session_state["assessment_source_filename"] = inspection.filename
    st.session_state["assessment_source_token"] = form_key(inspection)
    st.session_state["assessment_ort_version"] = scores["ort_version"]
    st.session_state["assessment_comm_max"] = scores["comm_max"]
    for key in SCORE_LABELS:
        st.session_state[f"assessment_{key}"] = scores[key]
    # Item responses stay out of the UI; they back the totals in the report while the totals are unchanged.
    st.session_state["assessment_form_items"] = {
        key: list(scores[key]) for key in ("phq9_items", "peg_items", "pdi_items", "ort_oud_items", "comm_items")
    } | {"comm_max": scores["comm_max"]}


def attach_form_items(scores: Scores) -> None:
    items = st.session_state.get("assessment_form_items")
    if not items:
        return
    phq9 = items["phq9_items"]
    if scores["phq9"] == calculate_phq9(phq9)["total"] and scores["item9"] == phq9[8]:
        scores["phq9_items"] = phq9
    if scores["peg_avg"] == calculate_peg(items["peg_items"]):
        scores["peg_items"] = items["peg_items"]
    if scores["pdi"] == calculate_pdi(items["pdi_items"])["total"]:
        scores["pdi_items"] = items["pdi_items"]
    if scores["ort_version"] == "ORT-OUD" and scores["ort"] == calculate_ort_oud(items["ort_oud_items"]):
        scores["ort_oud_items"] = items["ort_oud_items"]
    if scores["comm_max"] == items["comm_max"] and scores["comm"] == calculate_comm(items["comm_items"], items["comm_max"]):
        scores["comm_items"] = items["comm_items"]


RISK_COLORS = {"low": ("#E7F6EC", "#15803D"), "moderate": ("#FEF6E4", "#B45309"), "high": ("#FDECEC", "#B91C1C")}


def risk_banner(risk: str, repeat: str) -> None:
    """Coloured headline for the integrated risk level: green Low, amber Moderate, red High, grey otherwise."""
    background, accent = RISK_COLORS.get(risk.lower(), ("#EEF2F5", "#475569"))
    st.markdown(
        f'<div style="background:{background};border-left:6px solid {accent};border-radius:8px;'
        f'padding:14px 18px;margin:8px 0 16px">'
        f'<div style="color:{accent};font-size:1.35rem;font-weight:700;letter-spacing:.02em">'
        f"INTEGRATED OPIOID RISK LEVEL: {html.escape(risk.upper())}</div>"
        f'<div style="color:#1F2933;margin-top:4px"><b>Recommended Repeat Interval:</b> {html.escape(repeat)}</div></div>',
        unsafe_allow_html=True,
    )


SIDEBAR_STYLE = """
<style>
[data-testid="stSidebar"] { background-color: #CFE6DD; }
[data-testid="stSidebar"] [data-baseweb="select"] > div,
[data-testid="stSidebar"] input { background-color: #FFFFFF; }
[data-testid="stTextArea"]:has(textarea[aria-label="Saved report"]) [data-baseweb="textarea"],
[data-testid="stTextArea"]:has(textarea[aria-label="Saved report"]) [data-baseweb="base-input"],
textarea[aria-label="Saved report"] { background-color: #F7FBF9 !important; }
textarea[aria-label="Saved report"] { color: #1F2933 !important; -webkit-text-fill-color: #1F2933 !important; }
</style>
"""


DEMO_NOTICE = (
    "Public demo with made-up patient forms. Do not enter real patient information. "
    "Saved results are shared with every visitor and are cleared when the site restarts."
)


def main() -> None:
    st.set_page_config(page_title="Chronic Pain / Opioid Risk Generator", layout="wide")
    st.markdown(SIDEBAR_STYLE, unsafe_allow_html=True)
    st.title("Chronic Pain / Opioid Risk Generator")
    if os.environ.get("DEMO_MODE", "").lower() in {"1", "true", "yes"}:
        st.warning(DEMO_NOTICE)
    assessment_tab, clinic_tab, about_tab = st.tabs(["Assessment", "Insights", "About"])
    # The Assessment tab renders first because it builds the sidebar, including the risk thresholds used elsewhere.
    with assessment_tab:
        assessment_page()
    with about_tab:
        about_page()
    with clinic_tab:
        clinic_insights_view()


def point_rules(thresholds: Thresholds) -> list[tuple[str, str]]:
    return [
        ("COMM (any form)", rule_text("COMM", thresholds)),
        ("ORT / ORT-OUD", rule_text("ORT", thresholds)),
        ("PHQ-9 total", rule_text("PHQ-9", thresholds)),
        ("PHQ-9 item #9 (thoughts of self-harm)", "Any answer above 0: 3 points, plus an urgent safety alert"),
        ("UDS / PDMP", f"Requires review: 2 points; discordant: 3 points; {UDS_LABELS['not_reviewed'].split(' /')[0].lower()}: 0, listed as pending"),
        ("Refill behavior", "Intermittent or requires review: 1 point; early/escalation or lost/stolen: 2 points"),
        ("Clinical context", "Worsening, mood or aberrancy history: 1 each; escalation, elevated misuse or discordant: 2 each; capped at 3"),
        ("PEG and PDI", "Reported and flagged, but not counted as risk points"),
    ]


def level_text(thresholds: Thresholds) -> str:
    moderate, high = thresholds.get("Overall")
    return f"Low 0-{moderate - 1} points; Moderate {moderate}-{high - 1}; High {high} or more"


def threshold_sidebar() -> None:
    """Sidebar preset picker for risk-point and risk-level thresholds; stores the result in session state."""
    st.sidebar.header("Risk Thresholds")
    choice = st.sidebar.selectbox(
        "Preset", [*PRESETS, CUSTOM], key="risk_preset",
        help="Sets which scores add moderate or high risk points for each test, and how many points make "
             "Moderate or High overall risk. The default reproduces the original template.",
    )
    if choice != CUSTOM:
        thresholds = PRESETS[choice]
        for section in SECTIONS:
            moderate, high = thresholds.get(section)
            st.session_state[f"risk_cut_{section}_moderate"] = moderate
            st.session_state[f"risk_cut_{section}_high"] = high
    with st.sidebar.expander("Thresholds" + (" (edit)" if choice == CUSTOM else ""), expanded=choice == CUSTOM):
        values = {}
        for section, (name, maximum, moderate_points, high_points) in SECTIONS.items():
            st.markdown(f"**{name}**")
            left, right = st.columns(2)
            moderate_label = "Moderate at (points)" if section == "Overall" else f"Moderate (+{moderate_points}) at"
            high_label = "High at (points)" if section == "Overall" else f"High (+{high_points}) at"
            moderate = left.number_input(
                moderate_label, min_value=1, max_value=maximum, step=1,
                key=f"risk_cut_{section}_moderate", disabled=choice != CUSTOM,
            )
            high = right.number_input(
                high_label, min_value=1, max_value=maximum, step=1,
                key=f"risk_cut_{section}_high", disabled=choice != CUSTOM,
            )
            values[section] = (int(moderate), int(high))
    errors = validate_cutoffs(values)
    if errors:
        for error in errors:
            st.sidebar.error(error)
        st.sidebar.warning("Invalid custom thresholds: the original template thresholds are used until corrected.")
        st.session_state["risk_thresholds"] = DEFAULT
        return
    thresholds = make_thresholds(choice, values)
    st.session_state["risk_thresholds"] = thresholds
    if thresholds.is_default:
        st.sidebar.caption("Using the original template thresholds.")
    else:
        st.sidebar.warning("Non-default thresholds are a local choice and have not been validated. Reports and saved records note the preset used.")


def about_page() -> None:
    st.subheader("What this app does")
    st.markdown(
        "This app helps a pain-management clinic turn completed patient questionnaires into a clear, "
        "consistent report about **pain, daily function, mood and opioid-medication risk**.\n\n"
        "1. **Read the forms.** Patients fill in a six-page paper packet (PHQ-9 mood, PEG pain, PDI disability, "
        "ORT-OUD opioid risk factors and COMM medication-use questions). Scanned PDFs are placed in a folder named "
        "for the visit date. The app finds the ticked boxes and circled numbers on this computer; nothing is sent "
        "to the internet.\n"
        "2. **Add up the scores.** Each questionnaire is scored with the published rules. Blank answers are never "
        "counted as zero; they are flagged so staff can check the scan.\n"
        "3. **Check and correct.** Staff can view each answer next to its scan, fix any misread mark, and confirm "
        "the responses.\n"
        "4. **Combine the results.** The clinician adds drug-test / prescription-database results, refill behavior "
        "and the reason for the visit. The app then gives an overall opioid risk level (**Low, Moderate or High**) "
        "and how soon the questionnaires should be repeated (12, 6 or 3 months).\n"
        "5. **Write the report.** A ready-to-file report follows the clinic's original template, including "
        "clinical flags, a suicide-risk statement, treatment guidance, billing codes and time attestation. "
        "Each patient's latest result is saved in the `patient_results` folder.\n\n"
        "The **Insights** tab summarizes this clinic's saved assessments and shows each patient's trend across visits."
    )
    st.info(
        "Support tool only. A qualified clinician must verify scores, interpretations, risk levels, "
        "recommendations, diagnoses and documentation before use. A positive answer to PHQ-9 question 9 "
        "always requires same-day clinician suicide-risk assessment."
    )
    st.subheader("How the app calculates points")
    st.write(MODEL_NOTICE)
    thresholds = active_thresholds()
    if not thresholds.is_default:
        st.warning(f"Showing the sidebar preset **{thresholds.preset}**, not the original template thresholds.")
    show_full_table(pd.DataFrame(point_rules(thresholds), columns=["Input", "Points"]))
    st.markdown(
        f"**Overall risk:** {level_text(thresholds)}.  \n"
        "**Repeat interval:** High: every 3 months; Moderate: every 6 months; Low: every 12 months. "
        "Incomplete assessments get no risk level or interval.  \n"
        "Missing information is never treated as a normal (negative) finding."
    )
    st.subheader("Questionnaire scoring rules and references")
    st.markdown(
        f"**PHQ-9:** 9 items, 0-3 each, sum 0-27. One or two missing: sum x 9 / answered, "
        f"rounded half-up. Three or more missing: answered items added up as a provisional total and flagged for review. "
        f"Item 10 is not scored. "
        f"Bands: {band_table('PHQ-9')}. Item 9 >= 1 is an urgent action trigger that overrides the total. [Reference]({PHQ9_SOURCE})\n\n"
        f"**PEG:** mean of 3 ratings, 0-10 each; rounded clinical score, exact mean retained. "
        f"Compare over time, not diagnostic. Improvement: {peg_improvement_rule()}. [Reference]({PEG_SOURCE})\n\n"
        f"**PDI:** sum of 7 domains, 0-10 each. Supplied protocol: one missing uses the answered-domain "
        f"mean; two or more missing gives a provisional answered-domain total flagged for review. Bands: {band_table('PDI')}. "
        f"Progress criterion: >={instrument('PDI')['improvement']['min_percent_drop']}% reduction from baseline. [Reference]({PDI_SOURCE})\n\n"
        f"**ORT-OUD:** 9 Yes/No factors; Yes = 1. {band_table('ORT-OUD')}. No sex weights supplied. "
        f"Not interchangeable with original ORT and not a diagnosis. [Reference]({ORT_OUD_SOURCE})\n\n"
        f"**Standard COMM:** 17 items over the past 30 days, scored 0-4, sum 0-68, no reverse scoring. "
        f">=9 positive; <9 negative, not a diagnosis. Modified forms use the same >=9 threshold, as in the original template (not validated). [Reference]({COMM_SOURCE})\n\n"
        f"Labels, bands and thresholds are loaded from `scoring_config.json` (version {instrument_version()})."
    )


def assessment_page() -> None:
    inspections = patient_forms_sidebar(save_form=save_form_record)
    threshold_sidebar()
    review_patient_forms(inspections, form_summary, load_reviewed_form, save_form_record, autofill_from_form)
    saved_records_view()
    st.caption("Support tool only: a qualified clinician must verify all results. Scoring rules and point calculations are in the About tab.")
    st.button("Reset assessment", on_click=reset_assessment)
    if st.session_state.get("assessment_autofilled"):
        st.warning(
            "Scores auto-filled from optical detection of the scanned form; responses are NOT verified. "
            "Check each response in Manual inspection before relying on these scores."
        )
    if st.session_state.get("assessment_source_form"):
        st.info(f"Assessment imported from: {st.session_state['assessment_source_form']}. Other patient selections, diagnoses and attestations were cleared.")
    mode = st.radio(
        "Entry method", ["Paste text", "Manual entry"], horizontal=True,
        key="assessment_mode", on_change=invalidate_parse,
    )
    if mode == "Paste text":
        st.text_area(
            "Paste scores or copied text from a filled form",
            height=180,
            placeholder="PEG: 8 + 10 + 6 / 3 = 8\nPDI: 40\nPHQ9: 19\nQuestion 9. Answer: 0\nCOMM: 0\nORT: 4 / Moderate Risk",
            key="assessment_text", on_change=invalidate_parse,
        )
        st.button("Complete assessment", on_click=load_parsed_scores)
        if not st.session_state.get("assessment_ready"):
            st.info("Paste scores and click Complete assessment before reviewing or generating a report.")
            return
        for message in st.session_state.get("assessment_parse_errors", []):
            st.warning(f"Source parser issue: {message} Correct the source or resolve it in the review fields below; source notes remain visible after manual corrections.")
        for message in st.session_state.get("assessment_parse_warnings", []):
            st.warning(message)

    st.subheader("Review and correct scores")
    st.caption("Blank means not documented, never zero. Clear a field to mark it missing. Verify the COMM form maximum.")
    scores = empty_scores()
    if st.session_state.get("assessment_source_form"):
        scores["source_form"] = st.session_state["assessment_source_form"]
    scores["ort_version"] = st.selectbox(
        "Opioid risk instrument", ["Original ORT", "ORT-OUD"],
        key="assessment_ort_version", on_change=change_ort_version,
    )
    scores["comm_max"] = st.selectbox(
        "COMM form maximum", [68, 64, 28],
        format_func=lambda value: "Standard COMM: 17 items / 68" if value == 68 else f"Modified form: {value // 4} items / {value}",
        key="assessment_comm_max", on_change=change_comm_form,
    )
    fields = st.columns(3)
    for index, key in enumerate(SCORE_LABELS):
        label = SCORE_LABELS[key]
        if key == "ort" and scores["ort_version"] == "ORT-OUD":
            label = "ORT-OUD total / 9"
        scores[key] = fields[index % 3].number_input(
            label, value=None, step=0.01 if key == "peg_avg" else 1.0,
            format="%.2f" if key == "peg_avg" else "%g", key=f"assessment_{key}",
            on_change=invalidate_review,
        )
    attach_form_items(scores)
    if "phq9_items" in scores:
        st.caption(phq9_scoring_note(scores))
        if scores["phq9"] is None:
            st.warning("PHQ-9 has 3 or more missing responses. No total is calculated; re-administer the questionnaire.")
    scores["peg_baseline"] = st.number_input(
        "Prior PEG score / 10 (optional; use the unrounded mean if available)", value=None,
        step=0.01, key="assessment_peg_baseline", on_change=invalidate_review,
    )
    if scores["peg_avg"] is not None and math.isfinite(scores["peg_avg"]) and 0 <= scores["peg_avg"] <= 10:
        st.write(f"PEG clinical score: {round_clinical(scores['peg_avg'])} / 10 (mean {scores['peg_avg']:.4f})")
        if not validate_scores(scores):
            st.caption(peg_change(scores))
    elif "peg_items" in scores:
        st.warning("All three PEG responses are required. No average is calculated from missing responses.")
    if scores["phq9"] is not None and math.isfinite(scores["phq9"]) and 0 <= scores["phq9"] <= 27:
        st.write(f"PHQ-9 severity: {severity_phq9(scores['phq9'], scores['item9'])} (screening result, not a diagnosis)")
    if "pdi_items" in scores:
        st.caption(pdi_scoring_note(scores))
    scores["pdi_baseline"] = st.number_input(
        "Baseline PDI score / 70 (optional)", value=None, step=0.01,
        key="assessment_pdi_baseline", on_change=invalidate_review,
    )
    if not validate_scores(scores):
        st.caption(pdi_change(scores))
    if scores["ort_version"] == "ORT-OUD":
        if scores["ort"] is not None and math.isfinite(scores["ort"]) and 0 <= scores["ort"] <= 9:
            st.write(f"ORT-OUD: {scores['ort']:g} / 9 - {ort_level(scores['ort'], 'ORT-OUD')}")
        st.caption(
            "ORT-OUD is not interchangeable with original ORT. Its total uses the original template's ORT points "
            "(>=4: 1; >=8: 3) in the overall risk level."
        )
    if "comm_items" in scores:
        st.caption(comm_scoring_note(scores))
    if scores["comm_max"] != 68:
        st.caption(
            "Modified COMM form: the standard >=9 threshold and the original template's points (>=9: 2; >=18: 3) "
            "are applied, as in the original HTML."
        )
    if scores["comm"] is not None and math.isfinite(scores["comm"]) and 0 <= scores["comm"] <= scores["comm_max"]:
        st.write(severity_comm(scores["comm"], scores["comm_max"]))
    errors = validate_scores(scores)
    for error in errors:
        st.error(error)
    if scores["item9"] is not None and math.isfinite(scores["item9"]) and 0 < scores["item9"] <= 3:
        st.error(
            "Safety alert: positive PHQ-9 item #9. Immediate clinician suicide-risk assessment and safety protocol are required, "
            "independent of opioid-risk classification. This screening response does not determine acute risk."
        )
    elif scores["item9"] is None:
        st.warning("PHQ-9 item #9 not documented.")
    elif scores["item9"] == 0:
        st.success("PHQ-9 item #9 = 0: no suicidal ideation endorsed. This is a complete, normal answer.")

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
    pending = pending_review(scores, uds_code, refill_code)
    if missing:
        st.warning("Assessment incomplete. Missing: " + "; ".join(missing) + ". No overall classification or repeat interval will be assigned.")
    elif pending:
        st.info("Overall risk calculated. Pending review (does not change the risk level until updated): " + "; ".join(pending) + ".")
    else:
        st.success("All app-required assessment inputs are present. This does not establish clinical completeness.")
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
        active_thresholds(),
    )
    if st.button(
        "Generate reviewed report", type="primary",
        disabled=bool(errors) or not scores_verified or (time_confirmed and minutes == 0),
    ):
        st.session_state["assessment_report_inputs"] = inputs
        st.session_state.pop("assessment_final_save_message", None)
    if st.session_state.get("assessment_report_inputs") != inputs:
        return
    report, rows, flags, risk, repeat = make_report(
        scores, contexts, uds_code, refill_code, minutes,
        feedback_confirmed=feedback, time_confirmed=time_confirmed, diagnoses=tuple(diagnoses),
        clinician_verified=clinician_verified, synthetic=st.session_state.get("assessment_synthetic", False),
    )
    risk_banner(risk, repeat)
    st.subheader("Score Summary")
    show_full_table(pd.DataFrame(rows, columns=["Measure", "Score", "Interpretation"]))
    st.subheader("Clinical Flags")
    st.markdown("  \n".join(f"{'❔ Not assessed:' if checked is None else '☑' if checked else '☐'} {label}" for label, checked in flags.items()))
    for heading, body in report_sections(report):
        if heading in {"Score Summary", "Clinical Flags"}:
            continue
        if heading == "Interval Clinical Impression":
            body = clinical_impression(scores, contexts, uds_code, refill_code, risk)
        st.subheader(heading)
        st.markdown(body.replace("\n", "  \n"))
    st.subheader("Readable Report")
    st.text_area("Generated report", value=report, height=700, disabled=True)
    st.download_button(
        "Download readable report (.txt)",
        data=report, file_name="opioid_risk_report.txt", mime="text/plain",
    )
    folder = st.session_state.get("assessment_source_folder")
    filename = st.session_state.get("assessment_source_filename")
    code = patient_code(filename) if filename else None
    if folder and filename and not st.session_state.get("assessment_synthetic"):
        if code is None:
            st.warning(f"{filename} is not named with a patient code (for example 10001.pdf); the final report cannot be saved to a patient record.")
        else:
            st.button(
                f"Save final report to patient record {code} ({folder})",
                disabled=not clinician_verified,
                help="Requires the reviewing-clinician confirmation. Replaces earlier automatic or response-review records for this visit.",
                on_click=save_final_report,
                args=(code, folder, filename, report, rows, flags, risk, repeat, dict(scores)),
            )
            message = st.session_state.get("assessment_final_save_message")
            if message:
                (st.success if message[0] else st.error)(message[1])


def save_final_report(
    code: str, folder: str, filename: str, report: str, rows: list[tuple[str, str, str]],
    flags: dict[str, bool | None], risk: str, repeat: str, scores: dict,
) -> None:
    if not st.session_state.get("assessment_clinician_verified"):
        st.session_state["assessment_final_save_message"] = (False, "Confirm clinician verification before saving the final report.")
        return
    try:
        st.session_state["assessment_final_save_message"] = save_record(
            code, folder, "final_report", source_pdf=filename, report=f"Patient code: {code}\n\n{report}",
            rows=rows, flags=flags, risk=risk, repeat=repeat, scores=scores,
        )
    except (RecordError, OSError) as error:
        st.session_state["assessment_final_save_message"] = (False, f"Final report not saved: {error}")


if __name__ == "__main__":
    main()
