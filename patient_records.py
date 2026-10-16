"""Local per-patient storage of generator results, keyed by the PDF patient code.

Each patient code has exactly one score record directly in the results folder:
``patient_results/<code>_score.json`` and ``patient_results/<code>_score.txt``. Every save overwrites
them, so re-running a calculation never creates copies or sub-folders.
"""

import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RESULTS_ROOT = Path(__file__).parent / "patient_results"
PATIENT_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
STATUS_LABELS = {
    "auto_unverified": "Automatic draft - responses NOT verified",
    "responses_verified": "Responses verified by user - clinician report pending",
    "final_report": "Final report - clinician verification confirmed by user",
}


class RecordError(Exception):
    pass


def results_root() -> Path:
    return RESULTS_ROOT


def valid_folder(folder: str) -> bool:
    if len(folder) != 10:
        return False
    try:
        datetime.strptime(folder, "%Y_%m_%d")
    except ValueError:
        return False
    return True


def patient_code(filename: str) -> str | None:
    """Return the patient code from a PDF name such as ``10001.pdf``; None when the name is not a valid code."""
    path = Path(filename)
    if path.name != filename or "/" in filename or "\\" in filename or path.suffix.lower() != ".pdf":
        return None
    stem = path.stem
    return stem if PATIENT_CODE.fullmatch(stem) else None


def record_dir(code: str, root: Path | None = None) -> Path:
    """Folder holding a patient's score files: the results folder itself (no per-patient sub-folders)."""
    if not PATIENT_CODE.fullmatch(code):
        raise RecordError(f"Invalid patient code {code!r}: use letters, digits, '-' or '_' only (for example 10001).")
    return root or results_root()


def score_file_names(code: str) -> tuple[str, str]:
    """(data, report) file names for a patient code, for example 10001_score.json and 10001_score.txt."""
    return f"{code}_score.json", f"{code}_score.txt"


def saved_codes(root: Path | None = None) -> list[str]:
    """Patient codes that have a saved ``<code>_score.json`` in the results folder."""
    directory = root or results_root()
    if not directory.is_dir():
        return []
    codes = (path.name.removesuffix("_score.json") for path in directory.glob("*_score.json") if path.is_file())
    return sorted(code for code in codes if PATIENT_CODE.fullmatch(code))


def load_record(code: str, root: Path | None = None) -> dict[str, Any] | None:
    path = record_dir(code, root) / score_file_names(code)[0]
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RecordError(f"Cannot read saved record {path}: {error}") from error


def _write_atomic(path: Path, text: str) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _remove_old_copies(code: str, directory: Path) -> None:
    """Delete the ``<code>`` sub-folder (and any dated copies inside it) left by earlier versions."""
    old = directory / code
    if old.is_dir() and not old.is_symlink():
        shutil.rmtree(old)


def save_record(
    code: str, folder: str, status: str, *, source_pdf: str, report: str,
    rows: list[tuple[str, str, str]], flags: dict[str, bool | None], risk: str, repeat: str,
    scores: dict[str, Any], root: Path | None = None,
) -> tuple[bool, str]:
    """Save <code>_score.txt and <code>_score.json, replacing any earlier record for this patient code.

    The latest save always wins, whatever the previous record's visit folder or review status.
    Returns (saved, message).
    """
    if status not in STATUS_LABELS:
        raise RecordError(f"Unknown record status {status!r}.")
    if not valid_folder(folder):
        raise RecordError(f"Invalid visit folder {folder!r}: expected YYYY_MM_DD.")
    directory = record_dir(code, root)
    previous = load_record(code, root)
    directory.mkdir(parents=True, exist_ok=True)
    data_name, report_name = score_file_names(code)
    record = {
        "patient_code": code,
        "visit_folder": folder,
        "source_pdf": source_pdf,
        "status": status,
        "status_label": STATUS_LABELS[status],
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "integrated_risk": risk,
        "recommended_repeat_interval": repeat,
        "score_summary": [{"measure": name, "result": value, "interpretation": meaning} for name, value, meaning in rows],
        "clinical_flags": [{"flag": label, "status": None if checked is None else bool(checked)} for label, checked in flags.items()],
        "scores": scores,
        "report_file": report_name,
    }
    _write_atomic(directory / report_name, report)
    _write_atomic(directory / data_name, json.dumps(record, indent=2, ensure_ascii=False))
    _remove_old_copies(code, directory)
    replaced = ""
    if previous:
        replaced = f"; replaced previous record ({previous.get('visit_folder', '?')}, {previous.get('status_label', '?')})"
    return True, f"{code}: saved {folder} ({STATUS_LABELS[status]}) as {data_name} and {report_name}{replaced}"


def patient_history(code: str, root: Path | None = None) -> list[dict[str, Any]]:
    """The saved score record for one patient code, as a list (empty when none is saved)."""
    if not PATIENT_CODE.fullmatch(code):
        return []
    record = load_record(code, root)
    return [record] if record else []
