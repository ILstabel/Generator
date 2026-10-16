"""Create (or remove) synthetic patient records for testing Insights and patient trends.

    python make_test_records.py           # create TEST01-TEST08 records in patient_results\\
    python make_test_records.py --remove  # delete every TEST* record

Every visit is built from item-level answers and scored with the app's own scoring, report and save code.
Reports are marked "SYNTHETIC TEST DATA - NOT FOR PATIENT DOCUMENTATION". Replace with real records later.
"""

import argparse
import sys
from pathlib import Path

from patient_records import RESULTS_ROOT, save_record

PREFIX = "TEST"

# One row per visit: (visit folder, PHQ-9 total, item 9, PEG item sum (0-30), PDI total, ORT-OUD yes count,
# COMM-16 total, record status, blank items as "INSTRUMENT:item" strings).
PATIENTS: dict[str, tuple[str, list[tuple]]] = {
    "TEST01": ("Improving: pain, function and mood get better", [
        ("2025_04_10", 13, 0, 22, 45, 2, 12, "final_report", ()),
        ("2025_10_09", 10, 0, 18, 38, 2, 9, "final_report", ()),
        ("2026_04_09", 7, 0, 14, 27, 2, 6, "final_report", ()),
        ("2026_10_08", 4, 0, 10, 18, 2, 4, "responses_verified", ()),
    ]),
    "TEST02": ("Worsening: rising misuse signal; item 9 positive at last visit", [
        ("2025_09_15", 6, 0, 12, 20, 4, 6, "final_report", ()),
        ("2026_03_16", 12, 0, 18, 34, 4, 14, "final_report", ()),
        ("2026_09_14", 17, 1, 24, 48, 4, 22, "auto_unverified", ()),
    ]),
    "TEST03": ("Stable high risk; repeat battery overdue", [
        ("2026_01_12", 16, 0, 24, 50, 6, 24, "final_report", ()),
        ("2026_04_13", 18, 0, 25, 52, 6, 26, "final_report", ()),
        ("2026_07_13", 15, 0, 23, 49, 6, 21, "responses_verified", ()),
    ]),
    "TEST04": ("Single low-risk visit; yearly repeat overdue", [
        ("2025_08_20", 2, 0, 6, 8, 1, 2, "final_report", ()),
    ]),
    "TEST05": ("Item 9 positive at two middle visits, then resolved", [
        ("2025_12_01", 9, 0, 15, 30, 3, 8, "final_report", ()),
        ("2026_03_02", 15, 2, 17, 33, 3, 10, "final_report", ()),
        ("2026_06_01", 12, 1, 15, 31, 3, 9, "final_report", ()),
        ("2026_09_01", 8, 0, 13, 26, 3, 7, "responses_verified", ()),
    ]),
    "TEST06": ("Latest scan has blank answers (insufficient information)", [
        ("2026_05_05", 11, 0, 17, 36, 2, 11, "final_report", ()),
        ("2026_10_14", 9, 0, 16, 32, 2, 10, "auto_unverified", ("PHQ-9:2", "PHQ-9:5", "PHQ-9:7", "COMM-16:4")),
    ]),
    "TEST07": ("Stable moderate risk", [
        ("2026_02_10", 8, 0, 16, 28, 3, 10, "final_report", ()),
        ("2026_08_11", 9, 0, 16, 29, 3, 11, "final_report", ()),
    ]),
    "TEST08": ("PEG improves but PDI does not meet the 30% criterion", [
        ("2026_06_22", 5, 0, 21, 40, 1, 5, "final_report", ()),
        ("2026_10_13", 4, 0, 15, 33, 1, 4, "auto_unverified", ()),
    ]),
}



def spread(total: int, count: int, maximum: int) -> list[float]:
    """Split a whole-number total across items as evenly as possible."""
    if not 0 <= total <= count * maximum:
        raise ValueError(f"Total {total} does not fit {count} items scored 0-{maximum}.")
    base, extra = divmod(total, count)
    return [float(base + (1 if index < extra else 0)) for index in range(count)]


def form_values(phq9: int, item9: int, peg_sum: int, pdi: int, ort_yes: int, comm: int, blanks: tuple[str, ...]):
    values = {
        "PHQ-9": spread(phq9 - item9, 8, 3) + [float(item9)],
        "PEG": spread(peg_sum, 3, 10),
        "PDI": spread(pdi, 7, 10),
        "ORT-OUD": [1.0] * ort_yes + [0.0] * (9 - ort_yes),
        "COMM-16": spread(comm, 16, 4),
    }
    for blank in blanks:
        name, item = blank.split(":")
        values[name][int(item) - 1] = None
    return values


def visit_record(code: str, folder: str, values, status: str, context: str):
    from app import make_report, scores_from_form, validate_scores

    scores = scores_from_form(values)
    scores["source_form"] = f"{folder} / {code}.pdf (synthetic)"
    errors = validate_scores(scores)
    if errors:
        raise ValueError(f"{code} {folder}: " + "; ".join(errors))
    if status == "final_report":
        contexts = ["worsening"] if context.startswith("Worsening") else ["routine"]
        report, rows, flags, risk, repeat = make_report(
            scores, contexts, "consistent", "stable", 30, feedback_confirmed=True, time_confirmed=True,
            clinician_verified=True, synthetic=True,
        )
    else:
        report, rows, flags, risk, repeat = make_report(
            scores, [], "not_reviewed", "not_reviewed", context_documented=False, synthetic=True,
        )
    return scores, report, rows, flags, risk, repeat


def create(root: Path) -> None:
    for code, (story, visits) in PATIENTS.items():
        risks = []
        for folder, phq9, item9, peg_sum, pdi, ort_yes, comm, status, blanks in visits:
            values = form_values(phq9, item9, peg_sum, pdi, ort_yes, comm, blanks)
            scores, report, rows, flags, risk, repeat = visit_record(code, folder, values, status, story)
            save_record(
                code, folder, status, source_pdf=f"{code}.pdf", report=f"Patient code: {code}\n\n{report}",
                rows=rows, flags=flags, risk=risk, repeat=repeat, scores=dict(scores), root=root,
            )
            risks.append(f"{folder}: {risk}")
        print(f"{code} ({story}): " + "; ".join(risks))


def remove(root: Path) -> None:
    removed = [path for path in root.glob(f"{PREFIX}*_*.*") if path.is_file()]
    for path in removed:
        path.unlink()
    print(f"Removed {len(removed)} file(s) for {PREFIX}* test patients from {root}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--remove", action="store_true", help="delete the TEST* records instead of creating them")
    parser.add_argument("--root", type=Path, default=RESULTS_ROOT, help="results folder (default: patient_results)")
    arguments = parser.parse_args()
    arguments.root.mkdir(parents=True, exist_ok=True)
    if arguments.remove:
        remove(arguments.root)
    else:
        remove(arguments.root)
        create(arguments.root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
