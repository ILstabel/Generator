"""Date-folder batch selection and review for local patient scans."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st

from form_reader import (
    FORMS_ROOT,
    FormInspection,
    FormReadError,
    date_folders,
    folder_pdfs,
    inspect_form,
)
from patient_records import RecordError, load_record, patient_code, patient_history, record_dir, saved_codes


def show_full_table(frame: pd.DataFrame) -> None:
    """Show every row without an inner scrollbar, using the full page width (~35 px per row plus header)."""
    st.dataframe(frame, hide_index=True, use_container_width=True, height=(len(frame) + 1) * 35 + 3)

SaveForm = Callable[[str, str, dict[str, list[float | None]], str], tuple[bool, str]]
SCORE_FRACTION = re.compile(r"\d+(?:\.\d+)? / \d+")
SHORT_STATUS = {
    "auto_unverified": "Draft (not verified)",
    "responses_verified": "Responses verified",
    "final_report": "Final report",
}


def short_score(text: str) -> str:
    """Compact table value, e.g. '8 / 27 - Mild depressive symptoms'; '*' marks a provisional total."""
    match = SCORE_FRACTION.search(text)
    if not match:
        return "Not scored"
    value = match.group(0) + ("*" if "PROVISIONAL" in text else "")
    rest = text[match.end():]
    if rest.startswith("; ") and not rest.startswith("; exact"):
        band = re.split(r"[.(]", rest[2:], maxsplit=1)[0].replace(" for Opioid Use Disorder", "").strip()
        if band:
            value += f" - {band}"
    return value


def short_risk(text: str) -> str:
    return re.split(r"[(:]", text, maxsplit=1)[0].strip().rstrip(".")


def detected_values(form: FormInspection) -> dict[str, list[float | None]]:
    values: dict[str, list[float | None]] = {}
    for response in form.responses:
        values.setdefault(response.instrument, []).append(response.value)
    return values


def inspection_label(form: FormInspection) -> str:
    code = patient_code(form.filename)
    return code if code else f"No patient code: {form.folder} / {form.filename}"


def saved_status(form: FormInspection) -> str:
    code = patient_code(form.filename)
    if code is None:
        return "Not saved: rename PDF to patient code"
    try:
        record = load_record(code)
    except RecordError as error:
        return f"Unreadable record: {error}"
    if not record:
        return "Not saved"
    if record.get("visit_folder") != form.folder:
        return f"Saved from {record.get('visit_folder')}"
    return SHORT_STATUS.get(record.get("status", ""), record.get("status_label", "Saved"))


@dataclass
class ReviewedForm:
    inspection: FormInspection
    values: dict[str, list[float | None]]
    verified: bool


def form_key(form: FormInspection) -> str:
    return hashlib.sha256(f"{form.folder}/{form.filename}".encode()).hexdigest()[:16]


def current_values(form: FormInspection) -> dict[str, list[float | None]]:
    """Detected responses with any manual corrections from the review fields applied."""
    token = form_key(form)
    values: dict[str, list[float | None]] = {}
    for response in form.responses:
        key = f"forms_review_{token}_{response.instrument}_{response.item}"
        values.setdefault(response.instrument, []).append(st.session_state.get(key, response.value))
    return values


def clear_batch() -> None:
    st.session_state.pop("forms_autofill_source", None)
    for key in list(st.session_state):
        if key.startswith("forms_result_") or key.startswith("forms_review_"):
            del st.session_state[key]
    clear_imported_assessment()


def clear_imported_assessment() -> None:
    if st.session_state.get("assessment_source_form"):
        for key in list(st.session_state):
            if key.startswith("assessment_"):
                del st.session_state[key]


FOLDER_MODE = "All Assessments"
PATIENT_MODE = "Individual Assessments"


def patient_codes_by_folder(root: Path = FORMS_ROOT) -> dict[str, list[str]]:
    """Map each patient code found in the date folders to the folders containing <code>.pdf, newest first."""
    codes: dict[str, list[str]] = {}
    for folder in sorted(date_folders(root), reverse=True):
        try:
            paths = folder_pdfs(folder, root)
        except (FormReadError, OSError):
            continue
        for path in paths:
            code = patient_code(path.name)
            if code and folder not in codes.setdefault(code, []):
                codes[code].append(folder)
    return dict(sorted(codes.items()))


def inspect_selected(
    root: Path, folders: list[str], save_form: SaveForm | None = None, code: str | None = None,
) -> None:
    """Inspect every PDF in the folders (only <code>.pdf when a code is given) and auto-save each result."""
    clear_batch()
    selection = (tuple(folders), code)
    results = []
    errors = []
    for folder in folders:
        try:
            paths = folder_pdfs(folder, root)
        except (FormReadError, OSError) as error:
            errors.append(f"{folder}: {error}")
            continue
        if code is not None:
            paths = [path for path in paths if patient_code(path.name) == code]
            if not paths:
                errors.append(f"{folder}: no PDF for patient code {code}.")
        elif not paths:
            errors.append(f"{folder}: no PDF files found.")
        for path in paths:
            try:
                results.append(inspect_form(path, root))
            except (FormReadError, OSError) as error:
                errors.append(f"{folder} / {path.name}: {error}")
    saved = []
    if save_form:
        # One record per patient code: within a run only the newest visit folder is saved.
        newest: dict[str, str] = {}
        counts: dict[tuple[str, str], int] = {}
        for form in results:
            code = patient_code(form.filename)
            if code:
                newest[code] = max(newest.get(code, form.folder), form.folder)
                counts[(code, form.folder)] = counts.get((code, form.folder), 0) + 1
        for form in results:
            code = patient_code(form.filename)
            if code and form.folder != newest[code]:
                continue
            if code and counts[(code, form.folder)] > 1:
                errors.append(f"{form.folder} / {form.filename}: not saved - patient code {code} appears more than once in this folder.")
                continue
            try:
                ok, message = save_form(form.folder, form.filename, detected_values(form), "auto_unverified")
            except ValueError as error:
                ok, message = False, f"{form.folder} / {form.filename}: not saved - {error}"
            (saved if ok else errors).append(message)
    st.session_state["forms_result_inspections"] = results
    st.session_state["forms_result_errors"] = errors
    st.session_state["forms_result_saved"] = saved
    st.session_state["forms_result_selection"] = selection


def patient_forms_sidebar(root: Path = FORMS_ROOT, save_form: SaveForm | None = None) -> list[FormInspection]:
    st.sidebar.header("Select Assessment")
    try:
        folders = sorted(date_folders(root), reverse=True)
        codes = patient_codes_by_folder(root)
    except OSError as error:
        st.sidebar.error(f"Cannot list patient-form folders: {error}")
        return []
    if not folders:
        st.sidebar.info("Add PDFs to patient_forms\\YYYY_MM_DD\\ to enable folder selection.")
        return []
    mode = st.sidebar.radio("Calculate", [FOLDER_MODE, PATIENT_MODE], key="forms_mode", on_change=clear_batch)
    code: str | None = None
    if mode == FOLDER_MODE:
        folder = st.sidebar.selectbox(
            "Folder", folders, key="forms_folder", on_change=clear_batch,
            help="Every PDF directly inside this patient_forms folder is calculated and saved separately.",
        )
        selected = [folder] if folder else []
    else:
        code = st.sidebar.selectbox(
            "Patient / record score", list(codes), index=None, key="forms_code", on_change=clear_batch,
            placeholder="Type or select, e.g. 10001",
            help="Codes come from PDF file names such as 10001.pdf. Every visit is inspected; the newest is saved as the patient's score record.",
        )
        if not codes:
            st.sidebar.info("No PDFs named with a patient code (for example 10001.pdf) were found.")
        selected = codes.get(code, []) if code else []
        if selected:
            st.sidebar.caption(f"Visits found: {', '.join(selected)}")
        st.sidebar.toggle(
            "Manual / visual inspection", key="forms_manual_inspection",
            help="Off: show only the calculated summary. On: show scan previews and every detected response for checking, correcting and saving.",
        )
    selection = (tuple(selected), code) if selected else None
    if st.sidebar.button(
        "Calculate and save scores",
        disabled=selection is None,
        help="Saves one record per patient directly in patient_results as <code>_score.json and <code>_score.txt, overwriting any earlier run.",
    ):
        with st.spinner("Inspecting local scans; no patient forms are uploaded..."):
            inspect_selected(root, selected, save_form, code)
    if selection is None or st.session_state.get("forms_result_selection") != selection:
        return []
    for error in st.session_state.get("forms_result_errors", []):
        st.sidebar.error(error)
    return st.session_state.get("forms_result_inspections", [])


def review_patient_forms(
    inspections: list[FormInspection],
    calculate_summary: Callable[[dict[str, list[float | None]]], list[tuple[str, str]]],
    load_form: Callable[[ReviewedForm], None],
    save_form: SaveForm | None = None,
    autofill: Callable[[FormInspection, dict[str, list[float | None]]], None] | None = None,
) -> None:
    if not inspections:
        return
    individual = st.session_state.get("forms_mode") == PATIENT_MODE
    st.subheader("Individual Assessment Scores" if individual else "All Assessments Scores")
    overview = []
    for form in inspections:
        token = form_key(form)
        summary = dict(calculate_summary(current_values(form)))
        overview.append({
            "Patient": patient_code(form.filename) or "MISSING CODE", "Visit date": form.folder,
            "Overall risk": short_risk(summary["Overall risk"]),
            "PHQ-9": short_score(summary["PHQ-9"]), "Item 9": summary["PHQ-9 item 9"].split(" - ")[0],
            "PEG": short_score(summary["PEG"]), "PDI": short_score(summary["PDI"]),
            "ORT-OUD": short_score(summary["ORT-OUD"]), "COMM-16": short_score(summary["Modified COMM-16"]),
            "Responses": "Verified" if st.session_state.get(f"forms_review_{token}_verified") else "Not verified",
            "Saved record": saved_status(form),
        })
    show_full_table(pd.DataFrame(overview))
    st.caption(
        "\\* Provisional total: some answers are blank and need review. Overall risk excludes UDS/PDMP, refill "
        "and clinical context until they are reviewed. Select a patient below for full details."
    )
    labels = list(dict.fromkeys(inspection_label(form) for form in inspections))
    manual = st.session_state.get("forms_mode") == PATIENT_MODE and bool(st.session_state.get("forms_manual_inspection"))
    st.subheader("Individual Manual Inspection" if manual else "Individual Total Scores")
    selected_label = st.selectbox(
        "Patient code", labels, key="forms_inspect_code",
        help="Shows every selected-date form for this patient code."
        + (" Review, correct and save each one." if manual else " Visual inspection is available in Individual Assessments mode."),
    )
    if autofill:
        # The newest visit for the selected patient fills the paste-scores box; refreshed when the patient or a corrected response changes.
        form = next(form for form in inspections if inspection_label(form) == selected_label)
        values = current_values(form)
        marker = (form_key(form), repr(sorted(values.items())))
        if st.session_state.get("forms_autofill_source") != marker:
            autofill(form, values)
            st.session_state["forms_autofill_source"] = marker
    if not manual:
        keep_review_state()
        for form in inspections:
            if inspection_label(form) != selected_label:
                continue
            values = current_values(form)
            st.markdown(f"**Patient {patient_code(form.filename) or 'code missing'}: {form.folder} / {form.filename}**")
            show_full_table(pd.DataFrame(calculate_summary(values), columns=["Measure", "Calculated result"]))
            item9 = values.get("PHQ-9", [None] * 9)[8]
            if item9 is not None and item9 > 0:
                st.error("Positive PHQ-9 item 9: immediate clinician suicide-risk assessment and safety protocol required, independent of total.")
            elif item9 is None:
                st.warning("PHQ-9 item 9 unresolved; do not infer a negative safety response.")
        return
    for form in inspections:
        if inspection_label(form) != selected_label:
            continue
        token = form_key(form)
        with st.expander(f"Patient {patient_code(form.filename) or 'code missing'}: {form.folder} / {form.filename}", expanded=True):
            st.caption("Source: local PDF. Separate assessment; no patient records or dates are merged.")
            if form.page_previews:
                page_number = st.selectbox(
                    "Original page preview", list(range(1, len(form.page_previews) + 1)),
                    key=f"forms_review_{token}_preview",
                )
                st.image(form.page_previews[page_number - 1], caption=f"Original scan, page {page_number}. Verify layout and response position.")
            values: dict[str, list[float | None]] = {}
            for instrument in ("PHQ-9", "PEG", "PDI", "ORT-OUD", "COMM-16"):
                responses = [response for response in form.responses if response.instrument == instrument]
                st.markdown(f"**{instrument}**")
                instrument_values = []
                for response in responses:
                    columns = st.columns([1, 3])
                    options = [None, 0.0, 1.0] if instrument == "ORT-OUD" else [None, *[float(number) for number in range(11 if instrument in {"PEG", "PDI"} else 4 if instrument == "PHQ-9" else 5)]]
                    key = f"forms_review_{token}_{instrument}_{response.item}"
                    if key not in st.session_state:
                        st.session_state[key] = response.value
                    value = columns[0].selectbox(
                        f"{instrument} item {response.item} (page {response.page})", options,
                        key=key,
                        format_func=(
                            (lambda value: "Missing / unresolved" if value is None else "Yes (1)" if value else "No (0)")
                            if instrument == "ORT-OUD" else
                            (lambda value: "Missing / unresolved" if value is None else f"{value:g}")
                        ),
                        on_change=unverify_form, args=(token,),
                    )
                    columns[1].image(response.crop, caption=response.note)
                    instrument_values.append(value)
                values[instrument] = instrument_values
            show_full_table(pd.DataFrame(calculate_summary(values), columns=["Measure", "Calculated result"]))
            item9 = values["PHQ-9"][8]
            if item9 is not None and item9 > 0:
                st.error("Positive PHQ-9 item 9: immediate clinician suicide-risk assessment and safety protocol required, independent of total.")
            elif item9 is None:
                st.warning("PHQ-9 item 9 unresolved; do not infer a negative safety response.")
            verified = st.checkbox(
                "I checked every response crop and corrected detection errors; unresolved values are genuinely missing.",
                key=f"forms_review_{token}_verified",
            )
            st.button(
                "Load reviewed responses into assessment",
                key=f"forms_review_{token}_load", disabled=not verified,
                on_click=load_form, args=(ReviewedForm(form, values, verified),),
            )
            if save_form:
                code = patient_code(form.filename)
                st.button(
                    f"Save reviewed results to patient record {code or ''}".rstrip(),
                    key=f"forms_review_{token}_save", disabled=not verified or code is None,
                    help="Replaces this patient's score record (the latest save always wins, including over a final report).",
                    on_click=save_reviewed, args=(save_form, token, form.folder, form.filename, values),
                )
                message = st.session_state.get(f"forms_review_{token}_save_message")
                if message:
                    (st.success if message[0] else st.error)(message[1])


def keep_review_state() -> None:
    """Streamlit drops state of widgets that are not rendered; re-store corrections while manual inspection is hidden."""
    for key in list(st.session_state):
        if key.startswith("forms_review_") and not key.endswith(("_load", "_save")):
            st.session_state[key] = st.session_state[key]


def save_reviewed(save_form: SaveForm, token: str, folder: str, filename: str, values: dict[str, list[float | None]]) -> None:
    if not st.session_state.get(f"forms_review_{token}_verified"):
        st.session_state[f"forms_review_{token}_save_message"] = (False, "Confirm the response review before saving.")
        return
    try:
        st.session_state[f"forms_review_{token}_save_message"] = save_form(folder, filename, values, "responses_verified")
    except ValueError as error:
        st.session_state[f"forms_review_{token}_save_message"] = (False, f"Not saved: {error}")


def saved_records_view() -> None:
    """Browse saved generator results by patient code."""
    try:
        codes = saved_codes()
    except OSError as error:
        st.error(f"Cannot list saved patient records: {error}")
        return
    with st.expander(f"Saved patient records ({len(codes)} patient codes)"):
        if not codes:
            st.caption("No saved records yet. Inspecting forms named with a patient code (for example 10001.pdf) saves them automatically.")
            return
        code = st.selectbox("Patient code", codes, key="records_code")
        try:
            history = patient_history(code)
        except RecordError as error:
            st.error(str(error))
            return
        if not history:
            st.caption("No readable score record for this patient code.")
            return
        record = history[0]
        visit = record["visit_folder"]
        show_full_table(pd.DataFrame([
            {"Visit folder": visit, "Status": record["status_label"], "Saved (UTC)": record["saved_at"],
             "Integrated risk": record["integrated_risk"], "Source PDF": record["source_pdf"]}
        ]))
        if record["status"] != "final_report":
            st.warning(f"{record['status_label']}. Not a final clinical document.")
        show_full_table(pd.DataFrame(record["score_summary"]))
        report_path = record_dir(code) / Path(record.get("report_file", f"{code}_score.txt")).name
        try:
            report = report_path.read_text(encoding="utf-8")
        except OSError as error:
            st.error(f"Cannot read saved report: {error}")
            return
        st.text_area("Saved report", report, height=400, disabled=True, key=f"records_report_{code}")
        st.download_button(
            "Download saved report (.txt)", report, file_name=f"{code}_score.txt",
            mime="text/plain", key=f"records_download_{code}",
        )


def unverify_form(token: str) -> None:
    st.session_state[f"forms_review_{token}_verified"] = False
    st.session_state.pop(f"forms_review_{token}_save_message", None)
    if st.session_state.get("assessment_source_token") == token:
        clear_imported_assessment()
