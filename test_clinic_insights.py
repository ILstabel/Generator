import math
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from clinic_insights import display_table, flag_rates, follow_up, heatmap_frame, load_records
from patient_records import save_record, saved_codes, visit_history
from patient_trend import change_since_first, trend_frame


def save(root: Path, code: str, folder: str, risk: str, status: str = "auto_unverified", **scores) -> None:
    lenient = scores.pop("lenient", False)
    values = {"phq9": 5, "item9": 0.0, "peg_avg": 3.0, "pdi": 10.0, "ort": 1, "comm": 2.0, "comm_max": 68,
              "ort_version": "ORT-OUD", "phq9_items": [0.0] * 9} | scores
    rows = [("Risk Thresholds", "Lenient (flags fewer patients)", "x")] if lenient else []
    save_record(code, folder, status, source_pdf=f"{code}.pdf", report="report", rows=rows, flags={},
                risk=risk, repeat="", scores=values, root=root)


def clinic_app(root: str, today: str) -> None:
    from datetime import date
    from pathlib import Path

    from clinic_insights import clinic_insights_view

    clinic_insights_view(Path(root), date.fromisoformat(today))


class ClinicInsightsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        save(self.root, "10001", "2026_10_14", "Moderate", peg_avg=7.0, pdi=42.0, ort=5, comm=23.0, comm_max=64)
        save(self.root, "10003", "2026_10_15", "Insufficient information", phq9=14, item9=1.0,
             phq9_items=[1.0] * 8 + [1.0], comm_items=[1.0, None, None])
        save(self.root, "20001", "2026_01_05", "High", status="final_report", phq9=21, comm=20.0)
        save(self.root, "20002", "2025_01_05", "Low", status="responses_verified", phq9=None, item9=None)
        (self.root / "bad_score.json").write_text("{not json", encoding="utf-8")

    def tearDown(self):
        self.directory.cleanup()

    def test_load_records_one_row_per_patient_and_reports_bad_files(self):
        frame, problems = load_records(self.root)
        self.assertEqual(list(frame["patient"]), ["10003", "10001", "20001", "20002"])
        self.assertEqual(len(problems), 1)
        self.assertIn("bad", problems[0])
        row = frame.set_index("patient").loc["10003"]
        self.assertEqual(row["severity"], "Moderate")
        self.assertEqual(row["blank_answers"], 2)
        self.assertEqual(row["status"], "Automatic draft")
        moderate = frame.set_index("patient").loc["10001"]
        self.assertEqual(moderate["next_due"].date(), date(2027, 4, 14))
        self.assertTrue(frame.set_index("patient").loc["10003"][["next_due"]].isna().all())
        self.assertEqual(frame.set_index("patient").loc["20002"]["severity"], "Not scored")

    def test_flag_rates_use_only_scored_patients(self):
        frame, _ = load_records(self.root)
        rates = flag_rates(frame).set_index("flag")
        item9 = rates.loc["PHQ-9 item 9 > 0 (suicide-risk assessment)"]
        self.assertEqual((item9["patients_flagged"], item9["patients_scored"]), (1, 3))
        mood = rates.loc["Elevated mood burden (PHQ-9 >= 15)"]
        self.assertEqual((mood["patients_flagged"], mood["patients_scored"]), (1, 3))
        self.assertEqual(rates.loc["COMM >= 9 (misuse-risk signal)"]["patients_flagged"], 2)
        self.assertEqual(rates.loc["PDI >= 41 (severe disability)"]["patients_flagged"], 1)

    def test_follow_up_orders_by_urgency(self):
        frame, _ = load_records(self.root)
        actions = follow_up(frame, date(2026, 10, 15))
        self.assertEqual(list(actions["Patient"]), ["10003", "20001", "20002", "10001"])
        first = actions.iloc[0]["Action needed"]
        self.assertTrue(first.startswith("PHQ-9 item 9 positive"))
        self.assertIn("2 blank answer(s) need review", first)
        self.assertIn("Repeat battery overdue (due 2026-04-05)", actions.iloc[1]["Action needed"])
        self.assertIn("Clinician report pending", actions.iloc[2]["Action needed"])
        table = display_table(frame)
        self.assertEqual(table.set_index("Patient").loc["10001", "COMM"], "23 / 64")

    def test_heatmap_cells_scale_flag_and_mark_unscored(self):
        frame, _ = load_records(self.root)
        cells = heatmap_frame(frame).set_index(["patient", "measure"])
        self.assertEqual(len(cells), 4 * 6)
        self.assertNotIn("PHQ-4", set(cells.index.get_level_values("measure")))
        pdi = cells.loc[("10001", "PDI")]
        self.assertAlmostEqual(pdi["share"], 42 / 70)
        self.assertTrue(pdi["flagged"])
        self.assertTrue(cells.loc[("10001", "ORT")]["flagged"])
        self.assertAlmostEqual(cells.loc[("10001", "COMM")]["share"], 23 / 64)
        self.assertTrue(cells.loc[("10003", "Item 9")]["flagged"])
        self.assertFalse(cells.loc[("10003", "PHQ-9")]["flagged"])
        missing = cells.loc[("20002", "PHQ-9")]
        self.assertEqual(missing["text"], "-")
        self.assertFalse(missing["flagged"])
        self.assertTrue(math.isnan(cells.loc[("20002", "PHQ-9")]["share"]))

    def test_view_renders_filters_and_empty_state(self):
        app = AppTest.from_function(clinic_app, args=(str(self.root), "2026-10-15"), default_timeout=60).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, "4")
        self.assertFalse(any("automatic drafts" in warning.value for warning in app.warning))
        self.assertFalse(any("different risk-threshold presets" in warning.value for warning in app.warning))
        app.multiselect(key="clinic_risk").select("High").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, "1")
        self.assertEqual(app.metric[1].value, "1")
        for label in ("PHQ-9 total (0-27)", "COMM total"):
            app.selectbox(key="clinic_measure").select(label).run()
            self.assertFalse(app.exception)
        empty = tempfile.TemporaryDirectory()
        self.addCleanup(empty.cleanup)
        app = AppTest.from_function(clinic_app, args=(empty.name, "2026-10-15"), default_timeout=60).run()
        self.assertFalse(app.exception)
        self.assertIn("No saved patient records yet", app.info[0].value)

    def test_mixed_threshold_presets_warn(self):
        save(self.root, "30001", "2026_10_15", "Low", lenient=True)
        frame, _ = load_records(self.root)
        self.assertEqual(frame.set_index("patient").loc["30001"]["thresholds"], "Lenient (flags fewer patients)")
        app = AppTest.from_function(clinic_app, args=(str(self.root), "2026-10-15"), default_timeout=60).run()
        self.assertTrue(any("different risk-threshold presets" in warning.value for warning in app.warning))


class PatientTrendTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def test_change_since_first_uses_configured_criteria(self):
        save(self.root, "40001", "2026_01_10", "Moderate", peg_avg=8.0, pdi=50.0)
        save(self.root, "40001", "2026_04_10", "Moderate", peg_avg=7.0, pdi=45.0)
        save(self.root, "40001", "2026_07_10", "Low", peg_avg=6.0, pdi=36.0)
        frame = trend_frame(visit_history("40001", self.root))
        self.assertEqual(list(frame["visit_label"]), ["2026-01-10", "2026-04-10", "2026-07-10"])
        changes = change_since_first(frame).set_index("Measure")
        self.assertEqual(changes.loc["PEG average", "% change"], "-25%")
        self.assertIn("Meets", changes.loc["PEG average", "Improvement"])
        self.assertEqual(changes.loc["PDI total", "% change"], "-28%")
        self.assertIn("Below", changes.loc["PDI total", "Improvement"])
        save(self.root, "40001", "2026_10_10", "High", peg_avg=9.0, pdi=55.0)
        changes = change_since_first(trend_frame(visit_history("40001", self.root))).set_index("Measure")
        self.assertEqual(changes.loc["PDI total", "Improvement"], "Worse than first visit")

    def test_trend_view_in_insights_2(self):
        save(self.root, "40002", "2026_01_10", "Low")
        save(self.root, "40002", "2026_07_10", "High", item9=1.0, phq9=16)
        save(self.root, "40003", "2026_07_10", "Low")
        app = AppTest.from_function(clinic_app, args=(str(self.root), "2026-10-15"), default_timeout=60).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox(key="clinic_trend_patient").value, "40002")
        self.assertTrue(any("item 9 was positive at: 2026-07-10" in error.value for error in app.error))
        self.assertTrue(any("2 saved visits" in caption.value for caption in app.caption))
        app.selectbox(key="clinic_trend_patient").select("40003").run()
        self.assertFalse(app.exception)
        self.assertTrue(any("one saved visit" in info.value for info in app.info))

    def test_test_record_generator_creates_and_removes(self):
        from make_test_records import PATIENTS, create, remove

        create(self.root)
        self.assertEqual(saved_codes(self.root), sorted(PATIENTS))
        self.assertEqual(len(visit_history("TEST01", self.root)), 4)
        self.assertTrue((self.root / "TEST01_score.txt").read_text(encoding="utf-8").count("SYNTHETIC TEST DATA"))
        frame, problems = load_records(self.root)
        self.assertEqual(problems, [])
        self.assertEqual(frame.set_index("patient").loc["TEST06", "risk"], "Insufficient information")
        remove(self.root)
        self.assertEqual(list(self.root.iterdir()), [])


class TabLayoutTests(unittest.TestCase):
    def test_tabs_are_assessment_insights_about(self):
        app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=60).run()
        self.assertFalse(app.exception)
        self.assertEqual([tab.label for tab in app.tabs], ["Assessment", "Insights", "About"])
        self.assertTrue(any(header.value == "Insights: Saved assessments" for header in app.subheader))
        self.assertFalse(any("Public demo" in box.value for box in app.warning))

    def test_demo_mode_shows_notice(self):
        with patch.dict(os.environ, {"DEMO_MODE": "true"}):
            app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=60).run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Do not enter real patient information" in box.value for box in app.warning))


if __name__ == "__main__":
    unittest.main()
