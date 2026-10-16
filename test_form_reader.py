import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw
from pypdf import PdfWriter
from streamlit.testing.v1 import AppTest

from app import form_summary, save_form_record, scores_from_form
from form_reader import (
    CHECKBOXES, HEADERS, HEIGHT, WIDTH, FormInspection, FormReadError, Response,
    aligned_page, checkbox_responses, date_folders, folder_pdfs, inspect_form,
    png_bytes, rating_responses,
)
from patient_forms_ui import form_key, short_risk, short_score
from patient_records import (
    HISTORY_SCORES, RecordError, load_record, patient_code, patient_history, save_record, saved_codes, visit_history,
)


def checkbox_page(page, marks=None):
    image = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = HEADERS[page]
    draw.rectangle((left, top, right, bottom), fill=140)
    xs, ys = CHECKBOXES[page]
    for row, y in enumerate(ys):
        for column, x in enumerate(xs):
            draw.line((x - 10, y - 13, x - 10, y + 13), fill=0, width=3)
            draw.line((x + 10, y - 13, x + 10, y + 13), fill=0, width=3)
            for dx in (-10, 7):
                for dy in (-13, 11):
                    draw.line((x + dx, y + dy, x + dx + 3, y + dy), fill=0, width=2)
            if column in (marks or {}).get(row, []):
                draw.line((x - 15, y - 16, x + 17, y + 16), fill=0, width=4)
                draw.line((x - 15, y + 16, x + 17, y - 16), fill=0, width=4)
    return image


def synthetic_inspection(folder, name):
    crop = png_bytes(Image.new("L", (100, 40), 255))
    responses = []
    for instrument, count, page in (("PHQ-9", 9, 1), ("PEG", 3, 2), ("PDI", 7, 3), ("ORT-OUD", 9, 4), ("COMM-16", 16, 5)):
        for index in range(1, count + 1):
            value = 1.0 if instrument == "ORT-OUD" and index in (1, 5, 7) else 0.0
            responses.append(Response(instrument, index, page, value, "Synthetic test mark", crop))
    return FormInspection(folder, name, responses)


class FileDiscoveryTests(unittest.TestCase):
    def test_six_page_pdf_extraction_end_to_end(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "2026_10_15"
            folder.mkdir()
            images = []
            for page in range(6):
                if page in CHECKBOXES:
                    image = checkbox_page(page, {0: [1]})
                else:
                    image = Image.new("L", (WIDTH, HEIGHT), 255)
                    ImageDraw.Draw(image).rectangle(HEADERS[page], fill=140)
                images.append(image.convert("RGB"))
            path = folder / "synthetic.pdf"
            images[0].save(path, "PDF", save_all=True, append_images=images[1:])
            result = inspect_form(path, root)
            self.assertEqual(len(result.responses), 44)
            self.assertEqual(len(result.page_previews), 6)
            self.assertEqual(result.responses[0].value, 1)
            self.assertEqual(result.folder, "2026_10_15")
            self.assertEqual(result.filename, "synthetic.pdf")

    def test_real_dates_and_direct_pdfs_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual(date_folders(root / "missing"), [])
            for name in ("2026_10_14", "2026_10_15", "2026_02_30", "notes", "2026_1_01"):
                (root / name).mkdir()
            directory = root / "2026_10_15"
            (directory / "B.PDF").touch()
            (directory / "a.pdf").touch()
            (directory / "ignore.txt").touch()
            (directory / "nested").mkdir()
            (directory / "nested" / "not_direct.pdf").touch()
            self.assertEqual(date_folders(root), ["2026_10_15", "2026_10_14"])
            self.assertEqual([path.name for path in folder_pdfs("2026_10_15", root)], ["a.pdf", "B.PDF"])
            for folder in ("..", "2026_02_30", "missing"):
                with self.assertRaises(FormReadError):
                    folder_pdfs(folder, root)

    def test_reject_outside_and_wrong_page_count_and_corrupt_pdf(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "2026_10_15"
            folder.mkdir()
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            path = folder / "wrong.pdf"
            writer.write(path)
            with self.assertRaisesRegex(FormReadError, "six-page"):
                inspect_form(path, root)
            corrupt = folder / "corrupt.pdf"
            corrupt.write_bytes(b"not a pdf")
            with self.assertRaises(FormReadError):
                inspect_form(corrupt, root)
            with self.assertRaises(FormReadError):
                inspect_form(root / "outside.pdf", root)


class OpticalMarkTests(unittest.TestCase):
    def test_checkbox_choices_blank_and_double_marks(self):
        for page in (0, 3, 4, 5):
            _, ys = CHECKBOXES[page]
            image = checkbox_page(page, {0: [1], 1: [0, 1]})
            aligned = aligned_page(image, page)
            responses = checkbox_responses(aligned, page)
            self.assertEqual(responses[0].value, 0 if page == 3 else 1)
            self.assertIsNone(responses[1].value)
            self.assertTrue(all(response.value is None for response in responses[2:]))
            self.assertEqual(len(responses), len(ys))
            self.assertTrue(responses[0].crop.startswith(b"\x89PNG"))

    def test_unsupported_layout_rejected(self):
        with self.assertRaisesRegex(FormReadError, "header"):
            aligned_page(Image.new("L", (WIDTH, HEIGHT), 255), 0)
        with self.assertRaisesRegex(FormReadError, "boxes"):
            checkbox_responses(np.full((HEIGHT, WIDTH), 255, dtype=np.uint8), 0)

    def test_blank_and_centered_or_overlapping_circles(self):
        from form_reader import RATINGS

        for page in (1, 2):
            xs, ys = RATINGS[page]
            image = Image.new("L", (WIDTH, HEIGHT), 255)
            draw = ImageDraw.Draw(image)
            for y in ys:
                for x in xs:
                    draw.rectangle((x - 5, y - 11, x + 5, y + 11), outline=60, width=2)
            draw.ellipse((xs[4] - 14, ys[0] - 20, xs[4] + 14, ys[0] + 20), outline=0, width=3)
            # Ambiguous: circle around 5 with a stray stroke trailing toward 2; majority enclosed area wins.
            draw.ellipse((xs[5] - 14, ys[1] - 20, xs[5] + 14, ys[1] + 20), outline=0, width=3)
            draw.line((xs[2], ys[1] + 18, xs[5] - 14, ys[1] + 18), fill=0, width=3)
            result = rating_responses(np.array(image), page)
            self.assertEqual(result[0].value, 4)
            self.assertEqual(result[1].value, 5)
            self.assertIn("AMBIGUOUS", result[1].note)
            self.assertTrue(all(response.value is None for response in result[2:]))
            self.assertTrue(all("No pen mark" in response.note for response in result[2:]))

    def test_double_checkbox_mark_takes_heavier_box(self):
        page = 0
        xs, ys = CHECKBOXES[page]
        image = checkbox_page(page, {0: [1, 2]})
        draw = ImageDraw.Draw(image)
        draw.rectangle((xs[2] - 14, ys[0] - 14, xs[2] + 14, ys[0] + 14), fill=0)
        responses = checkbox_responses(aligned_page(image, page), page)
        self.assertEqual(responses[0].value, 2)
        self.assertIn("AMBIGUOUS", responses[0].note)

    def test_circles_touching_printed_numbers(self):
        """Regression: pen circles that touch the printed 0-10 numerals were reported as unclear."""
        from form_reader import RATINGS

        for page in (1, 2):
            xs, ys = RATINGS[page]
            image = Image.new("L", (WIDTH, HEIGHT), 255)
            draw = ImageDraw.Draw(image)
            for y in ys:
                for x in xs:
                    draw.rectangle((x - 5, y - 11, x + 5, y + 11), outline=60, width=2)
            choices = [3, 10, 0] if page == 1 else [9, 6, None, 5, 4, 3, 0]
            for y, choice in zip(ys, choices):
                if choice is not None:
                    x = xs[choice] - 2
                    draw.ellipse((x - 15, y - 19, x + 17, y + 18), outline=0, width=3)
            result = rating_responses(np.array(image), page)
            self.assertEqual([response.value for response in result], [None if c is None else float(c) for c in choices])
            self.assertIn("No pen mark", result[2].note if page == 2 else "No pen mark")


class BatchMappingTests(unittest.TestCase):
    def test_overview_values_are_compact(self):
        self.assertEqual(short_score("8 / 27; Mild. Prorated: raw sum 7 x 9 / 8 answered"), "8 / 27 - Mild")
        self.assertEqual(short_score("5 / 9; High risk for Opioid Use Disorder"), "5 / 9 - High risk")
        self.assertEqual(short_score("PROVISIONAL: item(s) 2 blank; mean. 7 / 10; exact mean 7.0000"), "7 / 10*")
        self.assertEqual(short_score("23 / 64. Modified 16-item form"), "23 / 64")
        self.assertEqual(short_score("14 / 27; URGENT ACTION TRIGGER: PHQ-9 item 9 >= 1 overrides the total score; high risk."), "14 / 27 - URGENT: item 9 positive")
        self.assertEqual(short_score("Not scored: all items blank or unresolved"), "Not scored")
        self.assertEqual(short_risk("Moderate (4 points; repeat battery every 6 months). UDS/PDMP pending"), "Moderate")
        self.assertEqual(short_risk("Insufficient information: PHQ-9 item #9"), "Insufficient information")
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.results = Path(temporary.name)
        redirect = patch("patient_records.RESULTS_ROOT", self.results)
        redirect.start()
        self.addCleanup(redirect.stop)

    def test_item_order_and_scoring_are_not_merged(self):
        form = synthetic_inspection("2026_10_15", "patient.pdf")
        values = {}
        for response in form.responses:
            values.setdefault(response.instrument, []).append(response.value)
        scores = scores_from_form(values)
        self.assertEqual(scores["ort_oud_items"], [True, False, False, False, True, False, True, False, False])
        self.assertEqual(scores["ort"], 3)
        self.assertEqual(scores["comm_max"], 64)
        self.assertIn(("ORT-OUD", "3 / 9; High risk for Opioid Use Disorder"), form_summary(values))
        other = synthetic_inspection("2026_10_14", "patient.pdf")
        self.assertNotEqual(form_key(form), form_key(other))
        values["ORT-OUD"][0] = 2.0
        with self.assertRaises(ValueError):
            scores_from_form(values)

    def test_sidebar_folder_mode_review_and_loading(self):
        forms = {
            "2026_10_14": [Path("2026_10_14") / "same.pdf", Path("2026_10_14") / "other.pdf"],
            "2026_10_15": [Path("2026_10_15") / "same.pdf"],
        }
        def fake_inspect(path, _root):
            self.assertIsInstance(_root, Path)
            return synthetic_inspection(path.parent.name, path.name)

        def fake_paths(folder, root):
            self.assertIsInstance(root, Path)
            return forms[folder]

        with patch("patient_forms_ui.date_folders", return_value=list(forms)), \
                patch("patient_forms_ui.folder_pdfs", side_effect=fake_paths), \
                patch("patient_forms_ui.inspect_form", side_effect=fake_inspect) as inspector:
            app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=30).run()
            self.assertEqual(app.sidebar.selectbox(key="forms_folder").options, ["2026_10_15", "2026_10_14"])
            app.sidebar.selectbox(key="forms_folder").select("2026_10_14").run()
            next(button for button in app.sidebar.button if button.label == "Calculate and save scores").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(inspector.call_count, 2)
            loaded = app.session_state["forms_result_inspections"]
            self.assertEqual(len(loaded), 2)
            self.assertEqual(load_record("same", self.results)["status"], "auto_unverified")
            self.assertEqual(load_record("same", self.results)["visit_folder"], "2026_10_14")
            self.assertEqual(load_record("other", self.results)["status"], "auto_unverified")
            self.assertEqual(sorted(path.name for path in self.results.iterdir() if path.name.startswith("same")), ["same_history.json", "same_score.json", "same_score.txt"])
            self.assertEqual(app.selectbox(key="forms_inspect_code").options, ["same", "other"])
            self.assertFalse(any(toggle.key == "forms_manual_inspection" for toggle in app.sidebar.toggle))
            self.assertFalse(any(e.label.startswith("Patient ") and not e.label.startswith("Patient trend") for e in app.expander))
            self.assertTrue(any("Calculated result" in frame.value.columns for frame in app.dataframe))
            self.assertIn("Patient trend: same (saved visits)", [e.label for e in app.expander])
            self.assertTrue(any("Patient same:" in text.value for text in app.markdown))
            self.assertEqual(app.selectbox(key="records_code").value, "same")
            app.selectbox(key="forms_inspect_code").select("other").run()
            self.assertTrue(any("Patient other:" in text.value for text in app.markdown))
            # The saved record shown must be the patient selected for scores, not the first saved code.
            self.assertEqual(app.selectbox(key="records_code").value, "other")
            self.assertTrue(app.text_area(key="records_report_other").value)
            app.selectbox(key="records_code").select("same").run()
            self.assertEqual(app.selectbox(key="records_code").value, "same")
            headings = lambda: [header.value for header in app.subheader]
            self.assertIn("All Assessments Scores", headings())
            self.assertIn("Individual Total Scores", headings())
            # Visual inspection is only offered for an individual patient / record score.
            app.sidebar.radio(key="forms_mode").set_value("Individual Assessments").run()
            app.sidebar.selectbox(key="forms_code").select("same").run()
            app.sidebar.button[0].click().run()
            self.assertIn("Individual Assessment Scores", headings())
            self.assertIn("Individual Total Scores", headings())
            self.assertFalse(app.sidebar.toggle(key="forms_manual_inspection").value)
            self.assertFalse(any(e.label.startswith("Patient ") and not e.label.startswith("Patient trend") for e in app.expander))
            # Two visits: the summary, paste box and saved record default to the latest visit.
            self.assertEqual(app.selectbox(key="forms_visit_same").value, "2026_10_15")
            patient_lines = [text.value for text in app.markdown if text.value.startswith("**Patient same:")]
            self.assertEqual(patient_lines, ["**Patient same: 2026_10_15 / same.pdf**"])
            self.assertIn("visit 2026_10_15", app.text_area(key="assessment_text").value)
            self.assertFalse(any("the scores above are for visit" in box.value for box in app.info))
            app.selectbox(key="forms_visit_same").select("2026_10_14").run()
            self.assertIn("visit 2026_10_14", app.text_area(key="assessment_text").value)
            self.assertTrue(any("latest visit (2026_10_15); the scores above are for visit 2026_10_14" in box.value for box in app.info))
            app.selectbox(key="forms_visit_same").select("2026_10_15").run()
            app.sidebar.toggle(key="forms_manual_inspection").set_value(True).run()
            self.assertIn("Individual Manual Inspection", headings())
            loaded = app.session_state["forms_result_inspections"]
            self.assertEqual([form.folder for form in loaded], ["2026_10_15", "2026_10_14"])
            self.assertEqual(len([e for e in app.expander if e.label.startswith("Patient same:")]), 2)
            token = form_key(loaded[0])
            self.assertTrue(app.button(key=f"forms_review_{token}_save").disabled)
            app.checkbox(key=f"forms_review_{token}_verified").check().run()
            app.button(key=f"forms_review_{token}_save").click().run()
            self.assertEqual(load_record("same", self.results)["status"], "responses_verified")
            app.sidebar.button[0].click().run()
            # Re-running replaces the record with the latest run; no extra copies are created.
            self.assertEqual(load_record("same", self.results)["status"], "auto_unverified")
            self.assertEqual(load_record("same", self.results)["visit_folder"], "2026_10_15")
            self.assertEqual(sorted(path.name for path in self.results.iterdir() if path.name.startswith("same")), ["same_history.json", "same_score.json", "same_score.txt"])
            self.assertTrue(app.button(key=f"forms_review_{token}_load").disabled)
            app.checkbox(key=f"forms_review_{token}_verified").check().run()
            app.selectbox(key=f"forms_review_{token}_PHQ-9_9").select(1.0).run()
            self.assertFalse(app.checkbox(key=f"forms_review_{token}_verified").value)
            self.assertTrue(any("immediate" in error.value for error in app.error))
            # Hiding manual inspection keeps the correction and shows it in the summary view.
            app.sidebar.toggle(key="forms_manual_inspection").set_value(False).run()
            self.assertFalse(any(e.label.startswith("Patient ") and not e.label.startswith("Patient trend") for e in app.expander))
            self.assertTrue(any("immediate" in error.value for error in app.error))
            app.sidebar.toggle(key="forms_manual_inspection").set_value(True).run()
            self.assertEqual(app.selectbox(key=f"forms_review_{token}_PHQ-9_9").value, 1.0)
            app.checkbox(key=f"forms_review_{token}_verified").check().run()
            app.button(key=f"forms_review_{token}_load").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.radio(key="assessment_mode").value, "Manual entry")
            self.assertEqual(app.selectbox(key="assessment_ort_version").value, "ORT-OUD")
            self.assertEqual(app.selectbox(key="assessment_comm_max").value, 64)
            self.assertEqual(app.number_input(key="assessment_item9").value, 1.0)
            self.assertFalse(any(box.key and "_item_" in box.key for box in app.selectbox if box.key.startswith("assessment_")))
            self.assertFalse(app.checkbox(key="assessment_scores_verified").value)
            self.assertFalse(app.checkbox(key="assessment_time_confirmed").value)
            app.sidebar.radio(key="forms_mode").set_value("All Assessments").run()
            self.assertFalse(any(e.label.startswith("Patient ") and not e.label.startswith("Patient trend") for e in app.expander))
            self.assertEqual(app.text_area(key="assessment_text").value, "")
            self.assertFalse(app.exception)

    def test_sidebar_individual_patient_code_mode(self):
        forms = {
            "2026_10_14": [Path("2026_10_14") / "10001.pdf", Path("2026_10_14") / "10002.pdf", Path("2026_10_14") / "Test 1 .pdf"],
            "2026_10_15": [Path("2026_10_15") / "10001.pdf"],
        }
        with patch("patient_forms_ui.date_folders", return_value=list(forms)), \
                patch("patient_forms_ui.folder_pdfs", side_effect=lambda folder, root: forms[folder]), \
                patch("patient_forms_ui.inspect_form", side_effect=lambda path, root: synthetic_inspection(path.parent.name, path.name)) as inspector:
            app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=30).run()
            app.sidebar.radio(key="forms_mode").set_value("Individual Assessments").run()
            self.assertEqual(app.sidebar.selectbox(key="forms_code").label, "Patient / record score")
            self.assertEqual(app.sidebar.selectbox(key="forms_code").options, ["10001", "10002"])
            self.assertIsNone(app.sidebar.selectbox(key="forms_code").value)
            self.assertTrue(app.sidebar.button[0].disabled)
            app.sidebar.selectbox(key="forms_code").select("10001").run()
            self.assertFalse(any(box.key == "forms_code_folder" for box in app.sidebar.selectbox))
            app.sidebar.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(inspector.call_count, 2)
            self.assertEqual([form.folder for form in app.session_state["forms_result_inspections"]], ["2026_10_15", "2026_10_14"])
            record = load_record("10001", self.results)
            self.assertEqual(record["status"], "auto_unverified")
            self.assertEqual(record["visit_folder"], "2026_10_15")
            self.assertEqual(sorted(path.name for path in self.results.iterdir() if path.name.startswith("10001")), ["10001_history.json", "10001_score.json", "10001_score.txt"])
            self.assertIsNone(load_record("10002", self.results))
            self.assertEqual(len(app.session_state["forms_result_saved"]), 1)
            self.assertFalse(any("10001_score.json" in message.value for message in app.sidebar.success))
            self.assertEqual(app.radio(key="assessment_mode").value, "Paste text")
            text = app.text_area(key="assessment_text").value
            self.assertIn("10001, visit 2026_10_15", text)
            self.assertIn("ORT-OUD: 3 / 9", text)
            self.assertIn("COMM-16:", text)
            self.assertEqual(app.selectbox(key="assessment_ort_version").value, "ORT-OUD")
            self.assertTrue(any("NOT verified" in warning.value for warning in app.warning))
            self.assertFalse(app.checkbox(key="assessment_scores_verified").value)

    def test_final_report_saved_and_browsed_by_patient_code(self):
        with patch("patient_forms_ui.date_folders", return_value=["2026_10_15"]), \
                patch("patient_forms_ui.folder_pdfs", return_value=[Path("2026_10_15") / "10001.pdf"]), \
                patch("patient_forms_ui.inspect_form", return_value=synthetic_inspection("2026_10_15", "10001.pdf")):
            app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=30).run()
            app.sidebar.radio(key="forms_mode").set_value("Individual Assessments").run()
            app.sidebar.selectbox(key="forms_code").select("10001").run()
            app.sidebar.button[0].click().run()
            app.sidebar.toggle(key="forms_manual_inspection").set_value(True).run()
            token = form_key(app.session_state["forms_result_inspections"][0])
            app.checkbox(key=f"forms_review_{token}_verified").check().run()
            app.button(key=f"forms_review_{token}_load").click().run()
            app.checkbox(key="assessment_scores_verified").check().run()
            next(b for b in app.button if b.label == "Generate reviewed report").click().run()
            final = next(b for b in app.button if b.label.startswith("Save final report to patient record 10001"))
            self.assertTrue(final.disabled)
            app.checkbox(key="assessment_clinician_verified").check().run()
            next(b for b in app.button if b.label == "Generate reviewed report").click().run()
            next(b for b in app.button if b.label.startswith("Save final report to patient record 10001")).click().run()
            self.assertFalse(app.exception)
            record = load_record("10001", self.results)
            self.assertEqual(record["status"], "final_report")
            report = (self.results / "10001_score.txt").read_text(encoding="utf-8")
            self.assertIn("CLINICIAN REVIEW CONFIRMED BY USER", report)
            measures = [row["measure"] for row in record["score_summary"]]
            self.assertIn("PHQ-9 Responses (1-9)", measures)
            self.assertIn("COMM Responses", measures)
            self.assertEqual(app.selectbox(key="records_code").value, "10001")
            self.assertIn("CLINICIAN REVIEW CONFIRMED", app.text_area(key="records_report_10001").value)

    def test_bad_pdf_is_reported_without_discarding_other_results(self):
        with patch("patient_forms_ui.date_folders", return_value=["2026_10_15"]), \
                patch("patient_forms_ui.folder_pdfs", return_value=[Path("2026_10_15") / "bad.pdf", Path("2026_10_15") / "good.pdf"]), \
                patch("patient_forms_ui.inspect_form", side_effect=[FormReadError("unsupported layout"), synthetic_inspection("2026_10_15", "good.pdf")]):
            app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=30).run()
            next(button for button in app.sidebar.button if button.label == "Calculate and save scores").click().run()
            self.assertEqual(len(app.session_state["forms_result_inspections"]), 1)
            self.assertTrue(any("bad.pdf: unsupported layout" in error.value for error in app.sidebar.error))
            self.assertFalse(app.exception)
class PatientRecordTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def save(self, status, risk="Insufficient information", folder="2026_10_14"):
        return save_record(
            "10001", folder, status, source_pdf="10001.pdf", report=f"{status} report",
            rows=[("PHQ-9", "8 / 27", "Mild")], flags={"Flag": None}, risk=risk, repeat="Not assigned",
            scores={"phq9": 8.0, "item9": 0.0}, root=self.root,
        )

    def test_patient_code_from_filename(self):
        self.assertEqual(patient_code("10001.pdf"), "10001")
        self.assertEqual(patient_code("A-17_b.PDF"), "A-17_b")
        for name in ("Test 1 .pdf", "../10001.pdf", "10001.txt", ".pdf", "10001 .pdf"):
            self.assertIsNone(patient_code(name), name)

    def files(self):
        return sorted(path.name for path in self.root.iterdir())

    def test_latest_save_always_replaces_single_record(self):
        self.assertTrue(self.save("final_report", risk="Low")[0])
        saved, message = self.save("auto_unverified", folder="2026_10_15")
        self.assertTrue(saved)
        self.assertIn("replaced previous record (2026_10_14", message)
        record = load_record("10001", self.root)
        self.assertEqual(record["status"], "auto_unverified")
        self.assertEqual(record["visit_folder"], "2026_10_15")
        self.assertEqual((self.root / "10001_score.txt").read_text(encoding="utf-8"), "auto_unverified report")
        self.assertTrue(self.save("responses_verified", folder="2026_10_14")[0])
        self.assertEqual(load_record("10001", self.root)["visit_folder"], "2026_10_14")
        self.assertEqual(self.files(), ["10001_history.json", "10001_score.json", "10001_score.txt"])
        self.assertEqual(len(patient_history("10001", self.root)), 1)

    def test_old_per_visit_copies_are_removed(self):
        for folder in ("2026_10_14", "2026_10_15"):
            old = self.root / "10001" / folder
            old.mkdir(parents=True)
            (old / "10001_score.json").write_text(json.dumps({"status": "auto_unverified"}), encoding="utf-8")
            (old / "results.json").write_text("{}", encoding="utf-8")
        self.assertTrue(self.save("auto_unverified")[0])
        self.assertEqual(self.files(), ["10001_history.json", "10001_score.json", "10001_score.txt"])
        self.assertFalse((self.root / "10001").exists())

    def test_each_patient_number_has_its_own_files(self):
        self.save("auto_unverified")
        save_record(
            "10002", "2026_10_14", "auto_unverified", source_pdf="10002.pdf", report="other", rows=[], flags={},
            risk="", repeat="", scores={}, root=self.root,
        )
        self.save("auto_unverified")
        self.assertEqual(self.files(), ["10001_history.json", "10001_score.json", "10001_score.txt", "10002_history.json", "10002_score.json", "10002_score.txt"])
        self.assertEqual(saved_codes(self.root), ["10001", "10002"])

    def test_visit_history_keeps_one_entry_per_visit_date(self):
        self.assertEqual(visit_history("10001", self.root), [])
        self.save("auto_unverified", risk="Low", folder="2026_10_15")
        self.save("final_report", risk="Moderate", folder="2026_04_14")
        self.save("responses_verified", risk="High", folder="2026_10_15")
        visits = visit_history("10001", self.root)
        self.assertEqual([visit["visit_folder"] for visit in visits], ["2026_04_14", "2026_10_15"])
        self.assertEqual([visit["integrated_risk"] for visit in visits], ["Moderate", "High"])
        self.assertEqual(visits[1]["status"], "responses_verified")
        self.assertEqual(set(visits[0]["scores"]), set(HISTORY_SCORES))
        self.assertEqual(load_record("10001", self.root)["visit_folder"], "2026_10_15")

    def test_record_saved_before_history_is_kept_as_first_visit(self):
        self.save("final_report", risk="Low", folder="2026_04_14")
        (self.root / "10001_history.json").unlink()
        self.assertEqual([visit["visit_folder"] for visit in visit_history("10001", self.root)], ["2026_04_14"])
        self.save("auto_unverified", folder="2026_10_14")
        self.assertEqual([visit["visit_folder"] for visit in visit_history("10001", self.root)], ["2026_04_14", "2026_10_14"])
        (self.root / "10001_history.json").write_text("{broken", encoding="utf-8")
        with self.assertRaises(RecordError):
            visit_history("10001", self.root)

    def test_invalid_codes_and_folders_rejected(self):
        with self.assertRaises(RecordError):
            save_record("../x", "2026_10_14", "auto_unverified", source_pdf="x.pdf", report="", rows=[], flags={},
                        risk="", repeat="", scores={}, root=self.root)
        with self.assertRaises(RecordError):
            save_record("10001", "..", "auto_unverified", source_pdf="x.pdf", report="", rows=[], flags={},
                        risk="", repeat="", scores={}, root=self.root)
        with self.assertRaises(RecordError):
            self.save("approved")

    def test_automatic_form_record_contents(self):
        values = {}
        for response in synthetic_inspection("2026_10_15", "10001.pdf").responses:
            values.setdefault(response.instrument, []).append(response.value)
        with patch("patient_records.RESULTS_ROOT", self.root):
            saved, _ = save_form_record("2026_10_15", "10001.pdf", values, "auto_unverified")
            unnamed, message = save_form_record("2026_10_15", "Test 1 .pdf", values, "auto_unverified")
        self.assertTrue(saved)
        self.assertFalse(unnamed)
        self.assertIn("rename the PDF", message)
        record = load_record("10001", self.root)
        self.assertEqual(record["scores"]["ort"], 3)
        self.assertEqual(record["source_pdf"], "10001.pdf")
        self.assertEqual(record["integrated_risk"], "Low")
        report = (self.root / "10001_score.txt").read_text(encoding="utf-8")
        self.assertTrue(report.startswith("AUTOMATIC RECORD"))
        self.assertIn("Patient code: 10001", report)
        self.assertIn("Clinical context / trigger: Not documented", report)
        self.assertNotIn("Routine interval", report)


if __name__ == "__main__":
    unittest.main()
