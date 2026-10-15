import math
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from app import (
    SAMPLES,
    Scores,
    empty_scores,
    make_report,
    missing_information,
    monitoring_interval,
    parse_scores,
    risk_contributions,
    risk_level,
    severity_comm,
    severity_pdi,
    severity_peg,
    severity_phq4,
    severity_phq9,
    validate_scores,
)


def low_scores() -> Scores:
    return parse_scores(SAMPLES["Low"])["scores"]


class ParserTests(unittest.TestCase):
    def test_samples(self):
        for name, text in SAMPLES.items():
            with self.subTest(name=name):
                parsed = parse_scores(text)
                self.assertEqual(parsed["errors"], [])
                expected = "Insufficient information" if name == "Incomplete" else name
                self.assertEqual(risk_level(parsed["scores"], "consistent", "stable", ["routine"]), expected)

    def test_original_placeholder_and_supported_forms(self):
        parsed = parse_scores(
            "PEG: 8 + 10 + 6 / 3 = 8\r\nPDI Total: 40 / 70\r\n"
            "PHQ-9 Score: 19 / 27\r\nQuestion 9. Answer: 0\r\n"
            "COMM-16 Total: 0 / 64\r\nORT: 4 / Moderate Risk"
        )
        self.assertEqual(parsed["errors"], [])
        self.assertEqual(parsed["scores"], {
            "peg_avg": 8.0, "pdi": 40.0, "phq9": 19.0, "phq4": None,
            "item9": 0.0, "comm": 0.0, "comm_max": 64, "ort": 4.0,
        })
        for text in ("PEG Avg: 5 / 10", "PEG Average = 5 / 10", "PEG: 4, 5, 6"):
            with self.subTest(text=text):
                self.assertEqual(parse_scores(text)["scores"]["peg_avg"], 5)
        parsed = parse_scores("PHQ4: 6 / 12\nPHQ-9 item #9: 1\nCOMM-7 Score: 12 / 28")
        self.assertEqual(parsed["errors"], [])
        self.assertIsNone(parsed["scores"]["phq9"])
        self.assertEqual(parsed["scores"]["item9"], 1)
        self.assertEqual(parsed["scores"]["comm_max"], 28)

    def test_duplicate_values_never_silently_choose_one(self):
        for text in ("PHQ9: 3\nPHQ9: 3", "PHQ9: 3 PHQ-9: 20", "PHQ9: 3\nPHQ9: 4\nPHQ9: 5"):
            with self.subTest(text=text):
                parsed = parse_scores(text)
                self.assertTrue(any("Duplicate" in error for error in parsed["errors"]))
                self.assertIsNone(parsed["scores"]["phq9"])

    def test_invalid_pasted_values(self):
        invalid = [
            "PHQ9: 99", "PHQ9: -2", "PHQ9: 1.5", "PHQ4: 13", "Question 9: 4",
            "PDI: 71", "PDI: -1", "PEG: 11 + 0 + 0", "PEG: -1 + 5 + 5",
            "PEG: 1 + 2", "PEG: 1 + 2 + 3 + 4", "PEG: 1 + 2 + 3 / 10",
            "PEG: 1 + 2 + 3 / 3 = 9", "PEG Average: 11 / 10", "PEG Average: 4 / 70",
            "PDI: 4 / 27", "PHQ9: 3 / 12", "PHQ9: 3 / unknown", "COMM: 69 / 68", "COMM-7: 29",
            "COMM-16: 12 / 28", "COMM: 4 / 99", "ORT: -1", "ORT: 8 / Low Risk",
            "PHQ9: unavailable", "PHQ9: 2abc", "PHQ9: nan", "unrecognized input",
        ]
        for text in invalid:
            with self.subTest(text=text):
                self.assertTrue(parse_scores(text)["errors"], text)

    def test_negative_is_not_converted_to_positive(self):
        self.assertEqual(parse_scores("PHQ9: -2")["scores"]["phq9"], -2)

    def test_unspecified_comm_form_requires_review_warning(self):
        self.assertTrue(parse_scores("COMM: 4")["warnings"])

    def test_empty_is_missing_not_zero(self):
        scores = parse_scores("")["scores"]
        self.assertIsNone(scores["phq9"])
        self.assertEqual(risk_level(scores, "not_reviewed", "not_reviewed", []), "Insufficient information")
        self.assertIn("Not assigned", monitoring_interval("Insufficient information"))


class ValidationAndRiskTests(unittest.TestCase):
    def test_structured_boundaries_and_nonfinite(self):
        for key, maximum in (("peg_avg", 10), ("pdi", 70), ("phq9", 27), ("phq4", 12), ("item9", 3), ("comm", 68)):
            for value in (-1.0, maximum + 1.0, math.nan, math.inf):
                with self.subTest(key=key, value=value):
                    scores = empty_scores()
                    scores[key] = value
                    self.assertTrue(validate_scores(scores))
            for value in (0.0, float(maximum)):
                scores = empty_scores()
                scores[key] = value
                self.assertEqual(validate_scores(scores), [])
        self.assertTrue(validate_scores({**empty_scores(), "ort": -1.0}))
        self.assertTrue(validate_scores({**empty_scores(), "pdi": 2.5}))
        self.assertEqual(validate_scores({**empty_scores(), "peg_avg": 6.5}), [])

    def test_item9_consistency(self):
        for total, item in ((0.0, 1.0), (27.0, 0.0)):
            self.assertTrue(validate_scores({**empty_scores(), "phq9": total, "item9": item}))

    def test_invalid_scores_and_selections_block_report(self):
        with self.assertRaises(ValueError):
            make_report({**low_scores(), "phq9": 99.0}, [], "consistent", "stable")
        with self.assertRaises(ValueError):
            make_report(low_scores(), [], "unknown", "stable")
        with self.assertRaises(ValueError):
            make_report(low_scores(), ["unknown"], "consistent", "stable")

    def test_each_missing_required_field_blocks_classification(self):
        for key in ("peg_avg", "pdi", "phq9", "item9", "comm", "ort"):
            with self.subTest(key=key):
                scores = low_scores()
                scores[key] = None
                self.assertTrue(missing_information(scores, "consistent", "stable"))
                self.assertEqual(risk_level(scores, "consistent", "stable", []), "Insufficient information")
        for uds, refill in (("not_reviewed", "stable"), ("uds_pending_pdmp_ok", "stable"), ("consistent", "not_reviewed")):
            self.assertEqual(risk_level(low_scores(), uds, refill, []), "Insufficient information")

    def test_point_boundaries(self):
        cases = (
            ("comm", 8, 0), ("comm", 9, 2), ("comm", 17, 2), ("comm", 18, 3),
            ("ort", 3, 0), ("ort", 4, 1), ("ort", 7, 1), ("ort", 8, 3),
            ("phq9", 14, 0), ("phq9", 15, 1), ("phq9", 19, 1), ("phq9", 20, 2),
            ("item9", 0, 0), ("item9", 1, 3),
        )
        for key, value, expected in cases:
            with self.subTest(key=key, value=value):
                scores = low_scores()
                scores[key] = float(value)
                self.assertEqual(sum(risk_contributions(scores, "consistent", "stable", []).values()), expected)
        for score, points in ((5, 0), (6, 1), (8, 1), (9, 2)):
            scores = {**low_scores(), "phq9": None, "phq4": float(score)}
            self.assertEqual(sum(risk_contributions(scores, "consistent", "stable", []).values()), points)

    def test_risk_cutoffs_and_intervals(self):
        for contexts, uds, refill, expected in (
            ([], "consistent", "stable", "Low"),
            (["mood"], "consistent", "stable", "Low"),
            (["escalation"], "consistent", "stable", "Moderate"),
            ([], "requires_review", "early_or_escalation", "Moderate"),
            ([], "discordant", "early_or_escalation", "High"),
        ):
            self.assertEqual(risk_level(low_scores(), uds, refill, contexts), expected)
        self.assertIn("12 months", monitoring_interval("Low"))
        self.assertIn("6 months", monitoring_interval("Moderate"))
        self.assertIn("3 months", monitoring_interval("High"))
        self.assertEqual(
            sum(risk_contributions(low_scores(), "consistent", "stable", ["escalation", "discordant", "mood"]).values()), 3,
        )

    def test_phq4_does_not_require_item9_but_does_not_imply_negative(self):
        scores = {**low_scores(), "phq9": None, "phq4": 6.0, "item9": None}
        self.assertEqual(missing_information(scores, "consistent", "stable"), [])
        report, _, flags, _, _ = make_report(scores, [], "consistent", "stable")
        self.assertIn("PHQ-4 does not assess suicidal ideation", report)
        self.assertIsNone(flags["PHQ-9 item #9 > 0 — suicide risk assessment indicated"])

    def test_mood_precedence_is_consistent(self):
        scores = {**low_scores(), "phq4": 12.0}
        report, rows, flags, risk, _ = make_report(scores, [], "consistent", "stable")
        self.assertEqual(risk, "Low")
        self.assertFalse(flags["Elevated mood symptom burden"])
        self.assertNotIn("PHQ-4", [row[0] for row in rows])
        self.assertIn("PHQ-9", report)

    def test_severity_boundaries(self):
        cases = (
            (severity_peg, 3.99, "Low"), (severity_peg, 4, "Moderate"),
            (severity_peg, 6.5, "Moderate"), (severity_peg, 7, "High"),
            (severity_pdi, 20, "Mild"), (severity_pdi, 21, "Moderate"),
            (severity_pdi, 40, "Moderate"), (severity_pdi, 41, "Severe"),
            (severity_phq9, 4, "Minimal"), (severity_phq9, 5, "Mild"),
            (severity_phq9, 10, "Moderate"), (severity_phq9, 15, "Moderately severe"),
            (severity_phq9, 20, "Severe"), (severity_phq4, 2, "Minimal"),
            (severity_phq4, 3, "Mild"), (severity_phq4, 6, "Moderate"),
            (severity_phq4, 9, "Severe"), (severity_comm, 8, "Below"),
            (severity_comm, 9, "Elevated"),
        )
        for function, score, prefix in cases:
            with self.subTest(function=function.__name__, score=score):
                self.assertTrue(function(score).startswith(prefix))


class ReportTests(unittest.TestCase):
    def test_default_report_does_not_assert_unconfirmed_facts(self):
        report, rows, flags, risk, repeat = make_report(low_scores(), [], "consistent", "stable")
        self.assertTrue(report.startswith("DRAFT - CLINICIAN VERIFICATION REQUIRED"))
        self.assertNotIn("I personally spent", report)
        self.assertNotIn("F11.20", report)
        self.assertNotIn("G89.4", report)
        self.assertNotIn("results were reviewed with the patient.", report)
        self.assertIn("No automatic time allocation", report)
        self.assertIn("not a validated", report)
        self.assertEqual(risk, "Low")
        self.assertTrue(rows)
        self.assertTrue(flags)
        self.assertIn("12 months", repeat)

    def test_confirmed_facts_are_explicit_and_selected_only(self):
        report = make_report(
            low_scores(), [], "consistent", "stable", 23, feedback_confirmed=True,
            time_confirmed=True, diagnoses=("G89.4",), clinician_verified=True,
        )[0]
        self.assertTrue(report.startswith("CLINICIAN REVIEW CONFIRMED BY USER"))
        self.assertIn("I personally spent 23 minutes", report)
        self.assertIn("results were reviewed with the patient", report)
        self.assertIn("G89.4", report)
        self.assertNotIn("F11.20", report)
        with self.assertRaises(ValueError):
            make_report(low_scores(), [], "consistent", "stable", time_confirmed=True)
        with self.assertRaises(ValueError):
            make_report(low_scores(), [], "consistent", "stable", -1)
        with self.assertRaises(ValueError):
            make_report(low_scores(), [], "consistent", "stable", diagnoses=("unknown",))

    def test_safety_and_unknown_flags_are_independent_of_risk(self):
        scores = parse_scores(SAMPLES["Incomplete"])["scores"]
        report, _, flags, risk, _ = make_report(scores, [], "not_reviewed", "not_reviewed", synthetic=True)
        self.assertIn("SYNTHETIC TEST DATA", report)
        self.assertIn("Same-day suicide risk assessment", report)
        self.assertEqual(risk, "Insufficient information")
        self.assertIsNone(flags["PDI >= 41 — severe disability"])
        self.assertIn("[?] Not assessed:", report)
        scores["item9"] = None
        self.assertIn("item #9 not documented", make_report(scores, [], "not_reviewed", "stable")[0])
        self.assertIn("does not rule out suicide risk", make_report(low_scores(), [], "consistent", "stable")[0])


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()
        self.assertFalse(self.app.exception)

    def click(self, label):
        next(button for button in self.app.button if button.label == label).click().run()
        self.assertFalse(self.app.exception)

    def generate(self):
        self.app.checkbox(key="assessment_scores_verified").check().run()
        self.click("Generate reviewed report")

    def report(self):
        return next(field.value for field in self.app.text_area if field.label == "Generated report")

    def test_load_generate_change_and_reset(self):
        for name in ("low", "moderate", "high"):
            self.click(f"Load {name} sample")
            self.generate()
            self.assertIn(f"INTEGRATED OPIOID RISK LEVEL: {name.upper()}", self.report())
            self.assertIn("SYNTHETIC TEST DATA", self.report())
        self.app.number_input(key="assessment_pdi").set_value(10).run()
        self.assertFalse(self.app.checkbox(key="assessment_scores_verified").value)
        self.assertFalse(any(field.label == "Generated report" for field in self.app.text_area))
        self.click("Reset assessment")
        self.assertEqual(self.app.text_area(key="assessment_text").value, "")
        self.assertFalse(any(field.label == "Generated report" for field in self.app.text_area))
        self.assertFalse(self.app.exception)

    def test_invalid_parse_can_be_corrected_but_not_generated_as_invalid(self):
        self.app.text_area(key="assessment_text").set_value(SAMPLES["Low"].replace("PHQ9: 3", "PHQ9: 99")).run()
        self.click("Parse into review fields")
        self.app.checkbox(key="assessment_scores_verified").check().run()
        button = next(button for button in self.app.button if button.label == "Generate reviewed report")
        self.assertTrue(button.disabled)
        self.assertTrue(any("0-27" in error.value for error in self.app.error))
        self.app.number_input(key="assessment_phq9").set_value(3).run()
        self.app.selectbox(key="assessment_uds").select("consistent").run()
        self.app.selectbox(key="assessment_refill").select("stable").run()
        self.generate()
        self.assertIn("INTEGRATED OPIOID RISK LEVEL: LOW", self.report())
        self.app.text_area(key="assessment_text").set_value("PHQ9: 20").run()
        self.assertFalse(any(field.label == "Generated report" for field in self.app.text_area))

    def test_incomplete_safety_alert_and_no_interval(self):
        self.click("Load incomplete sample")
        self.assertTrue(any("Safety alert" in error.value for error in self.app.error))
        self.generate()
        self.assertIn("INSUFFICIENT INFORMATION", self.report())
        self.assertIn("Not assigned", self.report())

    def test_structured_entry_and_documentation_confirmations(self):
        self.app.radio(key="assessment_mode").set_value("Structured entry").run()
        self.assertIsNone(self.app.number_input(key="assessment_phq9").value)
        self.generate()
        self.assertIn("INSUFFICIENT INFORMATION", self.report())
        self.app.number_input(key="assessment_minutes").set_value(30).run()
        self.assertFalse(any(field.label == "Generated report" for field in self.app.text_area))
        self.app.checkbox(key="assessment_time_confirmed").check().run()
        self.app.checkbox(key="assessment_feedback").check().run()
        self.app.multiselect(key="assessment_diagnoses").select("G89.4").run()
        self.app.checkbox(key="assessment_clinician_verified").check().run()
        self.generate()
        self.assertIn("I personally spent 30 minutes", self.report())
        self.assertIn("G89.4", self.report())
        self.assertIn("CLINICIAN REVIEW CONFIRMED BY USER", self.report())
        self.app.number_input(key="assessment_minutes").set_value(0).run()
        self.assertFalse(self.app.checkbox(key="assessment_clinician_verified").value)
        self.assertFalse(self.app.checkbox(key="assessment_time_confirmed").value)
        self.app.checkbox(key="assessment_time_confirmed").check().run()
        self.assertTrue(any("actual time" in error.value for error in self.app.error))


if __name__ == "__main__":
    unittest.main()
