import copy
import json
import math
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from scoring_config import CONFIG_PATH, ConfigError, validate_config
from app import (
    SAMPLES,
    Scores,
    calculate_pdi,
    calculate_peg,
    calculate_phq9,
    calculate_ort_oud,
    calculate_comm,
    empty_scores,
    make_report,
    missing_information,
    monitoring_interval,
    ort_level,
    parse_scores,
    pdi_change,
    peg_change,
    pending_review,
    clinical_impression,
    report_sections,
    risk_contributions,
    risk_level,
    severity_audit,
    severity_comm,
    severity_pdi,
    severity_peg,
    severity_phq4,
    severity_phq9,
    round_clinical,
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
        parsed_rounded = parse_scores("PEG: 6 + 4 + 4 / 3 = 5")
        self.assertEqual(parsed_rounded["errors"], [])
        self.assertAlmostEqual(parsed_rounded["scores"]["peg_avg"], 14 / 3)
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
            "PEG: 1 + 2", "PEG: 1.5 + 2 + 3", "PEG: 1 + 2 + 3 + 4", "PEG: 1 + 2 + 3 / 10",
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
            # As in the original HTML: unreviewed UDS/PDMP or refill adds 0 points and is listed as pending, not blocking.
            self.assertEqual(risk_level(low_scores(), uds, refill, []), "Low")
            self.assertTrue(pending_review(low_scores(), uds, refill))
        items = [1.0] * 7 + [None, 0.0]
        scores = {**low_scores(), "phq9_items": items, "phq9": calculate_phq9(items)["total"], "item9": 0.0}
        self.assertEqual(risk_level(scores, "consistent", "stable", []), "Low")
        self.assertIn("PHQ-9 item(s) 8 blank - needs review (prorated)", pending_review(scores, "consistent", "stable"))
        items = [1.0] * 6 + [None, None, 0.0]
        scores.update(phq9_items=items, phq9=calculate_phq9(items)["total"])
        self.assertEqual(risk_level(scores, "consistent", "stable", []), "Insufficient information")

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
            (severity_phq9, 4, "Minimal"), (severity_phq9, 5, "Mild"),
            (severity_phq9, 10, "Moderate (standard clinical positive cutoff)"), (severity_phq9, 15, "Moderately Severe"),
            (severity_phq9, 20, "Severe depression risk"), (severity_phq4, 2, "Minimal"),
            (severity_phq4, 3, "Mild"), (severity_phq4, 6, "Moderate"),
            (severity_phq4, 9, "Severe"), (severity_comm, 8, "Negative"),
            (severity_comm, 9, "Positive"),
        )
        for function, score, prefix in cases:
            with self.subTest(function=function.__name__, score=score):
                self.assertTrue(function(score).startswith(prefix))
        for score in (0, 4, 7, 10):
            self.assertIn("not diagnostic", severity_peg(score))
        for score, label in ((0, "Mild"), (20, "Mild"), (20.5, "Mild"), (21, "Moderate"), (40, "Moderate"),
                             (40.5, "Moderate"), (41, "Severe"), (70, "Severe")):
            with self.subTest(pdi=score):
                self.assertTrue(severity_pdi(score).startswith(label))
        for score, label in ((0, "Low-risk"), (7, "Low-risk"), (8, "Hazardous"), (14, "Hazardous"), (15, "Likely"), (40, "Likely")):
            with self.subTest(audit=score):
                self.assertTrue(severity_audit(score).startswith(label))
        with self.assertRaises(ValueError):
            severity_audit(41)

    def test_phq9_item9_guardrail_overrides_total(self):
        self.assertTrue(severity_phq9(3, 1).startswith("URGENT ACTION TRIGGER"))
        self.assertIn("Total-score band: Minimal", severity_phq9(3, 1))
        self.assertEqual(severity_phq9(3, 0), "Minimal")
        self.assertEqual(severity_phq9(3, None), "Minimal")
        scores = {**low_scores(), "item9": 2.0}
        self.assertIn("URGENT ACTION TRIGGER", make_report(scores, [], "consistent", "stable")[0])

    def test_config_validation_rejects_bad_bands(self):
        good = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(validate_config(copy.deepcopy(good))["version"], good["version"])
        mutations = (
            lambda c: c["instruments"]["PDI"]["bands"][1].update(min=31),
            lambda c: c["instruments"]["PDI"]["bands"][1].update(min=29),
            lambda c: c["instruments"]["PHQ-9"]["bands"][-1].update(max=26),
            lambda c: c["instruments"].pop("AUDIT"),
            lambda c: c["instruments"]["PEG"]["improvement"].update(rule="either"),
        )
        for mutate in mutations:
            config = copy.deepcopy(good)
            mutate(config)
            with self.assertRaises(ConfigError):
                validate_config(config)


class ReportTests(unittest.TestCase):
    def test_default_report_does_not_assert_unconfirmed_facts(self):
        report, rows, flags, risk, repeat = make_report(low_scores(), [], "consistent", "stable")
        self.assertTrue(report.startswith("DRAFT - CLINICIAN VERIFICATION REQUIRED"))
        self.assertNotIn("I personally spent", report)
        self.assertNotIn("F11.20", report)
        self.assertNotIn("G89.4", report)
        self.assertNotIn("Results were reviewed with the patient", report)
        self.assertIn("No time allocation", report)
        self.assertNotIn("not a validated", report)
        self.assertNotIn("RISK POINT CONTRIBUTIONS", report)
        self.assertNotIn("ASSESSMENT COMPLETENESS", report)
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
        self.assertIn("Results were reviewed with the patient", report)
        self.assertIn("Review/scoring of completed measures: 5 minutes", report)
        self.assertIn("G89.4", report)
        self.assertNotIn("F11.20", report)
        with self.assertRaises(ValueError):
            make_report(low_scores(), [], "consistent", "stable", time_confirmed=True)
        with self.assertRaises(ValueError):
            make_report(low_scores(), [], "consistent", "stable", -1)
        with self.assertRaises(ValueError):
            make_report(low_scores(), [], "consistent", "stable", diagnoses=("unknown",))

    def test_report_matches_original_template_sections(self):
        scores = parse_scores("PEG: 7 / 10\nPDI: 42 / 70\nPHQ9: 8\nQuestion 9: 0\nCOMM: 23 / 68\nORT: 5")["scores"]
        report, rows, flags, risk, repeat = make_report(
            scores, ["routine", "escalation"], "requires_review", "intermittent", 30,
            feedback_confirmed=True, time_confirmed=True, diagnoses=("F11.20", "G89.4"),
        )
        self.assertEqual((risk, repeat), ("High", "Repeat battery every 3 months"))
        self.assertEqual(
            [name for name, _, _ in rows[:14]],
            ["Integrated Opioid Risk", "Recommended Repeat Interval", "PEG Average", "PDI", "PHQ-9", "PHQ-9 Item #9", "COMM",
             "Original ORT", "Clinical Context", "UDS / PDMP", "Refill Behavior", "QHP Evaluation Time", "Billing ICD-10", "Billing ICD-10"],
        )
        self.assertTrue(flags["PEG ≥ 7 — severe pain impact"])
        self.assertTrue(flags["PDI ≥ 41 — severe disability"])
        self.assertEqual(
            [heading for heading, _ in report_sections(report)],
            ["Score Summary", "Clinical Flags", "Interval Clinical Impression", "Integrated Opioid Risk Interpretation",
             "Suicide Risk Assessment", "Opioid Treatment Guidance", "Feedback Provided To Patient", "Billing / Diagnostic Codes",
             "Qhp Time & Attestation"],
        )
        for text in (
            "Interval psychological/behavioral testing was completed in the context of",
            "The integrated profile supports an overall High opioid risk level.",
            "No suicidal ideation endorsed on this measure.",
            "F11.20 - Opioid dependence, uncomplicated",
            "Review/scoring of completed measures: 6 minutes",
            "integration with clinical data, UDS/PDMP/refill behavior, mood/suicide-risk screen, clinical context, and opioid-risk factors: 11 minutes",
            "treatment/monitoring plan: 8 minutes", "Documentation/reporting: 5 minutes",
            "Feedback/care coordination as indicated: 0 minutes",
            "Time excluded patient form-completion time",
            "I personally spent 30 minutes performing the psychological testing evaluation service",
        ):
            self.assertIn(text, report)
        for text in ("PEG Average: 7.00 / 10\n  Interpretation: High pain interference", "PDI: 42 / 70\n  Interpretation: Severe disability",
                     "PHQ-9: 8 / 27\n  Interpretation: Mild depressive symptoms", "COMM: 23\n  Interpretation: Elevated opioid misuse-risk signal"):
            self.assertIn(text, report)
        self.assertNotIn("Responses", report)
        impression = clinical_impression(scores, ["routine", "escalation"], "requires_review", "intermittent", risk)
        self.assertIn("Results demonstrate high pain interference with PEG average score of 7.00 / 10 and severe disability with PDI score of 42 / 70.", impression)
        self.assertIn("PHQ-9 score of 8 / 27 is consistent with mild depressive symptoms.", impression)
        self.assertIn("COMM score of 23 / 68 is interpreted as Elevated opioid misuse-risk signal", impression)

    def test_safety_and_unknown_flags_are_independent_of_risk(self):
        scores = parse_scores(SAMPLES["Incomplete"])["scores"]
        report, _, flags, risk, _ = make_report(scores, [], "not_reviewed", "not_reviewed", synthetic=True)
        self.assertIn("SYNTHETIC TEST DATA", report)
        self.assertIn("Immediate suicide risk assessment and safety protocol", report)
        self.assertEqual(risk, "Insufficient information")
        self.assertIsNone(flags["PDI ≥ 41 — severe disability"])
        self.assertIn("[?] Not assessed:", report)
        scores["item9"] = None
        self.assertIn("item #9 not documented", make_report(scores, [], "not_reviewed", "stable")[0])
        self.assertIn("No suicidal ideation endorsed on this measure", make_report(low_scores(), [], "consistent", "stable")[0])


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()
        self.assertFalse(self.app.exception)

    def click(self, label):
        next(button for button in self.app.button if button.label == label).click().run()
        self.assertFalse(self.app.exception)

    def load_sample(self, name):
        self.click("Reset assessment")
        self.app.text_area(key="assessment_text").set_value(SAMPLES[name]).run()
        self.click("Complete assessment")
        if name != "Incomplete":
            self.app.selectbox(key="assessment_uds").select("consistent").run()
            self.app.selectbox(key="assessment_refill").select("stable").run()

    def generate(self):
        self.app.checkbox(key="assessment_scores_verified").check().run()
        self.click("Generate reviewed report")

    def report(self):
        return next(field.value for field in self.app.text_area if field.label == "Generated report")

    def table_text(self):
        return "\n".join(frame.value.to_string() for frame in self.app.dataframe)

    def test_about_tab_holds_summary_rules_and_points(self):
        about = self.app.tabs[2]
        self.assertEqual(about.label, "About")
        about_text = "\n".join(block.value for block in about.markdown)
        self.assertIn("What this app does", "\n".join(header.value for header in about.subheader))
        self.assertIn("Read the forms", about_text)
        self.assertIn("Bands:", about_text)
        self.assertIn("High 5 or more", about_text)
        self.assertIn("capped at 3", "\n".join(frame.value.to_string() for frame in about.dataframe))
        assessment = self.app.tabs[0]
        self.assertFalse(any("Bands:" in block.value for block in assessment.markdown))
        self.assertFalse(any(e.label in {"How the app calculates points", "Questionnaire scoring rules and references"} for e in self.app.expander))

    def test_load_generate_change_and_reset(self):
        for name in ("Low", "Moderate", "High"):
            self.load_sample(name)
            self.generate()
            self.assertIn(f"INTEGRATED OPIOID RISK LEVEL: {name.upper()}", self.report())
            colour = {"Low": "#15803D", "Moderate": "#B45309", "High": "#B91C1C"}[name]
            self.assertTrue(any(
                f"RISK LEVEL: {name.upper()}" in block.value and colour in block.value for block in self.app.markdown
            ))
        self.app.number_input(key="assessment_pdi").set_value(10).run()
        self.assertFalse(self.app.checkbox(key="assessment_scores_verified").value)
        self.assertFalse(any(field.label == "Generated report" for field in self.app.text_area))
        self.click("Reset assessment")
        self.assertEqual(self.app.text_area(key="assessment_text").value, "")
        self.assertFalse(any(field.label == "Generated report" for field in self.app.text_area))
        self.assertFalse(self.app.exception)

    def test_invalid_parse_can_be_corrected_but_not_generated_as_invalid(self):
        self.app.text_area(key="assessment_text").set_value(SAMPLES["Low"].replace("PHQ9: 3", "PHQ9: 99")).run()
        self.click("Complete assessment")
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
        self.load_sample("Incomplete")
        self.assertTrue(any("Safety alert" in error.value for error in self.app.error))
        self.generate()
        self.assertIn("INSUFFICIENT INFORMATION", self.report())
        self.assertIn("Not assigned", self.report())

    def test_structured_entry_and_documentation_confirmations(self):
        self.app.radio(key="assessment_mode").set_value("Manual entry").run()
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

    def test_only_evaluator_dropdowns_remain(self):
        self.load_sample("Low")
        self.assertFalse(any(box.key == "assessment_phq4" for box in self.app.number_input))
        self.app.text_area(key="assessment_text").set_value(SAMPLES["Low"].replace("PHQ9: 3", "PHQ4: 3")).run()
        self.click("Complete assessment")
        self.assertEqual(self.app.number_input(key="assessment_phq4").value, 3)
        self.load_sample("Low")
        keys = {box.key for box in self.app.selectbox if box.key and box.key.startswith("assessment_")}
        self.assertEqual(keys, {"assessment_ort_version", "assessment_comm_max", "assessment_uds", "assessment_refill"})
        self.assertEqual([radio.key for radio in self.app.radio if radio.key and radio.key.startswith("assessment_")], ["assessment_mode"])
        self.assertIsNotNone(self.app.multiselect(key="assessment_contexts"))
        self.app.number_input(key="assessment_item9").set_value(1).run()
        self.assertFalse(self.app.checkbox(key="assessment_scores_verified").value)
        self.assertTrue(any("Safety alert" in error.value for error in self.app.error))

    def test_peg_and_pdi_totals_and_baselines(self):
        self.load_sample("Low")
        self.app.number_input(key="assessment_peg_avg").set_value(4.5).run()
        self.app.number_input(key="assessment_peg_baseline").set_value(8.0).run()
        self.app.number_input(key="assessment_pdi").set_value(32).run()
        self.app.number_input(key="assessment_pdi_baseline").set_value(50.0).run()
        self.generate()
        self.assertIn("36.0%", self.table_text())
        self.assertIn("Meets the configured improvement criterion", self.table_text())
        self.assertIn("PDI: 32 / 70\n  Interpretation: Moderate disability", self.report())
        self.assertNotIn("Severe disability", self.report())

    def test_ort_oud_version_total_and_combined_risk_guard(self):
        self.load_sample("Low")
        self.app.selectbox(key="assessment_ort_version").select("ORT-OUD").run()
        self.assertIsNone(self.app.number_input(key="assessment_ort").value)
        self.app.number_input(key="assessment_ort").set_value(5).run()
        self.generate()
        self.assertIn("ORT-OUD: 5 / 9 / High risk for Opioid Use Disorder", self.report())
        self.assertIn("INTEGRATED OPIOID RISK LEVEL: LOW", self.report())
        self.assertEqual(risk_contributions({**low_scores(), "ort": 5, "ort_version": "ORT-OUD"}, "consistent", "stable", [])["ORT-OUD (>=8: 3; >=4: 1)"], 1)
        self.assertIn("[x] ORT-OUD high screening risk", self.report())
        self.app.selectbox(key="assessment_ort_version").select("Original ORT").run()
        self.assertIsNone(self.app.number_input(key="assessment_ort").value)
        self.assertFalse(self.app.checkbox(key="assessment_scores_verified").value)
        self.app.number_input(key="assessment_ort").set_value(5).run()
        self.generate()
        self.assertIn("Original ORT: 5 / Moderate Risk", self.report())

    def test_standard_comm_total_and_modified_form_guard(self):
        self.load_sample("Low")
        self.app.number_input(key="assessment_comm").set_value(9).run()
        self.generate()
        self.assertIn("COMM: 9\n  Interpretation: Elevated opioid misuse-risk signal", self.report())
        self.app.selectbox(key="assessment_comm_max").select(64).run()
        self.assertIsNone(self.app.number_input(key="assessment_comm").value)
        self.app.number_input(key="assessment_comm").set_value(23).run()
        self.generate()
        self.assertIn("Modified 16-item form; standard >=9 cutoff applied per original template", self.report())
        self.assertIn("[x] COMM >= 9", self.report())
        self.assertEqual(risk_contributions({**low_scores(), "comm": 23, "comm_max": 64}, "consistent", "stable", [])["Modified COMM-16 (>=18: 3; >=9: 2)"], 3)
        self.assertIn("INTEGRATED OPIOID RISK LEVEL: MODERATE", self.report())


class QuestionnaireCalculationTests(unittest.TestCase):
    def test_phq9_totals_proration_and_rounding(self):
        for items, total, exact, answered in (
            ([0.0] * 9, 0, 0, 9),
            ([3.0] * 9, 27, 27, 9),
            ([1.0] * 8 + [None], 9, 9, 8),
            ([3.0, 3.0, 3.0, 3.0, 0.0, 0.0, 0.0, 0.0, None], 14, 13.5, 8),
            ([3.0, 3.0, 2.0, 2.0, 0.0, 0.0, 0.0, None, None], 13, 90 / 7, 7),
            ([1.0] * 6 + [None] * 3, 6, 6, 6),
            ([None] * 9, None, None, 0),
        ):
            with self.subTest(items=items):
                result = calculate_phq9(items)
                self.assertEqual(result["total"], total)
                self.assertEqual(result["exact"], exact)
                self.assertEqual(result["answered"], answered)
                self.assertEqual(result["prorated"], 7 <= answered < 9)
                self.assertEqual(result["provisional"], 0 < answered < 7)

    def test_all_phq9_integer_severity_bands(self):
        for value in range(28):
            expected = (
                "Minimal" if value < 5 else "Mild" if value < 10 else
                "Moderate (" if value < 15 else "Moderately Severe" if value < 20 else "Severe depression risk"
            )
            self.assertTrue(severity_phq9(value).startswith(expected))

    def test_item_calculators_reject_invalid_values_and_lengths(self):
        for calculator, length, maximum in ((calculate_phq9, 9, 3), (calculate_peg, 3, 10), (calculate_pdi, 7, 10)):
            for items in ([0.0] * (length - 1), [0.0] * (length + 1)):
                with self.subTest(calculator=calculator.__name__, items=items), self.assertRaises(ValueError):
                    calculator(items)
            for value in (-1.0, float(maximum + 1), 1.5, math.inf, math.nan):
                with self.subTest(calculator=calculator.__name__, value=value), self.assertRaises(ValueError):
                    calculator([value] + [0.0] * (length - 1))

    def test_phq9_item9_is_not_imputed_and_safety_survives_invalid_total(self):
        scores = low_scores()
        items = [1.0] * 8 + [None]
        scores.update(phq9_items=items, phq9=calculate_phq9(items)["total"], item9=None)
        self.assertEqual(validate_scores(scores), [])
        self.assertIn("PHQ-9 item #9", missing_information(scores, "consistent", "stable"))
        self.assertEqual(risk_level(scores, "consistent", "stable", []), "Insufficient information")
        items = [None] * 8 + [1.0]
        scores.update(phq9_items=items, phq9=calculate_phq9(items)["total"], item9=1.0)
        report = make_report(scores, [], "consistent", "stable")[0]
        self.assertIn("Immediate suicide risk assessment", report)
        self.assertIn("PROVISIONAL: item(s) 1, 2, 3, 4, 5, 6, 7, 8 blank - needs review", report)

    def test_metadata_cannot_disagree_with_computed_values(self):
        scores = low_scores()
        scores.update(phq9_items=[0.0] * 9)
        self.assertTrue(validate_scores(scores))
        scores = low_scores()
        scores.update(peg_items=[0.0] * 3)
        self.assertTrue(validate_scores(scores))
        scores = low_scores()
        scores.update(pdi_items=[0.0] * 7)
        self.assertTrue(validate_scores(scores))

    def test_functional_impairment_does_not_change_totals_or_points(self):
        for impairment in ("Not difficult at all", "Somewhat difficult", "Very difficult", "Extremely difficult"):
            scores = {**low_scores(), "phq9_function": impairment}
            self.assertEqual(validate_scores(scores), [])
            self.assertEqual(risk_contributions(scores, "consistent", "stable", []), risk_contributions(low_scores(), "consistent", "stable", []))
            rows = make_report(scores, [], "consistent", "stable")[1]
            self.assertIn(("PHQ-9 Functional Impairment (item 10)", impairment), [(name, value) for name, value, _ in rows])
        self.assertTrue(validate_scores({**low_scores(), "phq9_function": "unsupported"}))

    def test_peg_mean_rounding_missing_and_change_threshold(self):
        self.assertEqual(calculate_peg([6.0, 4.0, 5.0]), 5)
        self.assertEqual(calculate_peg([0.0] * 3), 0)
        self.assertEqual(calculate_peg([10.0] * 3), 10)
        self.assertEqual(calculate_peg([6.0, 4.0, None]), 5)
        self.assertIsNone(calculate_peg([None] * 3))
        self.assertEqual(round_clinical(4.5), 5)
        self.assertEqual(round_clinical(calculate_peg([6.0, 4.0, 4.0])), 5)
        # Configured rule: decrease >=1.0 point OR >=30%.
        for mean, baseline, expected in (
            (7.0, 8.0, "Meets"), (7.01, 8.0, "below"), (2.1, 3.0, "Meets"), (2.11, 3.0, "below"),
            (8.0, 8.0, "No change"), (9.0, 8.0, "increased"),
        ):
            with self.subTest(mean=mean, baseline=baseline):
                note = peg_change({**low_scores(), "peg_avg": mean, "peg_baseline": baseline})
                self.assertIn(expected, note)
        self.assertIn("25.0%", peg_change({**low_scores(), "peg_avg": 6.0, "peg_baseline": 8.0}))
        self.assertIn("undefined", peg_change({**low_scores(), "peg_baseline": 0.0}))

    def test_pdi_mean_imputation_and_missing_threshold(self):
        self.assertEqual(calculate_pdi([0.0] * 7)["total"], 0)
        self.assertEqual(calculate_pdi([10.0] * 7)["total"], 70)
        result = calculate_pdi([9.0, 6.0, None, 5.0, 4.0, 3.0, 0.0])
        self.assertEqual(result, {"answered": 6, "raw_sum": 27, "imputed_value": 4.5, "total": 31.5, "provisional": False})
        self.assertEqual(calculate_pdi([None, None] + [10.0] * 5)["total"], 50)
        self.assertTrue(calculate_pdi([None, None] + [10.0] * 5)["provisional"])
        self.assertIsNone(calculate_pdi([None] * 7)["total"])
        scores = low_scores()
        scores.update(pdi_items=[9.0, 6.0, None, 5.0, 4.0, 3.0, 0.0], pdi=31.5)
        self.assertEqual(validate_scores(scores), [])
        self.assertIn("Mean-imputed", make_report(scores, [], "consistent", "stable")[0])

    def test_pdi_change_threshold_and_invalid_baselines(self):
        self.assertIn("Meets", pdi_change({**low_scores(), "pdi": 35.0, "pdi_baseline": 50.0}))
        self.assertIn("Does not meet", pdi_change({**low_scores(), "pdi": 35.01, "pdi_baseline": 50.0}))
        self.assertIn("undefined", pdi_change({**low_scores(), "pdi_baseline": 0.0}))
        for key, invalid in (("peg_baseline", 11.0), ("pdi_baseline", 71.0), ("pdi_baseline", math.nan)):
            self.assertTrue(validate_scores({**low_scores(), key: invalid}))

    def test_ort_oud_binary_totals_all_boundaries(self):
        for yes_count in range(10):
            result = calculate_ort_oud([True] * yes_count + [False] * (9 - yes_count))
            self.assertEqual(result, yes_count)
            self.assertEqual(ort_level(result, "ORT-OUD"), "Low risk for Opioid Use Disorder" if yes_count <= 2 else "High risk for Opioid Use Disorder")
        self.assertEqual(calculate_ort_oud([True] * 8 + [None]), 8)
        self.assertIsNone(calculate_ort_oud([None] * 9))
        for items in ([True] * 8, [True] * 10, [1] * 9):
            with self.assertRaises(ValueError):
                calculate_ort_oud(items)
        self.assertEqual(ort_level(5), "Moderate Risk")
        self.assertEqual(ort_level(5, "ORT-OUD"), "High risk for Opioid Use Disorder")

    def test_ort_oud_parse_range_and_version_conflicts(self):
        parsed = parse_scores("ORT-OUD: 5 / 9 / High Risk")
        self.assertEqual(parsed["errors"], [])
        self.assertEqual(parsed["scores"]["ort_version"], "ORT-OUD")
        self.assertEqual(parsed["scores"]["ort"], 5)
        for text in ("ORT-OUD: 10", "ORT-OUD: -1", "ORT-OUD: 2.5", "ORT-OUD: 5 / Moderate Risk", "ORT-OUD: 5 / 27"):
            self.assertTrue(parse_scores(text)["errors"], text)
        self.assertTrue(parse_scores("ORT: 5\nORT-OUD: 5")["errors"])
        scores = {**low_scores(), "ort_version": "ORT-OUD", "ort": 5.0}
        self.assertEqual(validate_scores(scores), [])
        self.assertEqual(risk_level(scores, "consistent", "stable", []), "Low")
        contributions = risk_contributions(scores, "consistent", "stable", [])
        self.assertEqual(contributions["ORT-OUD (>=8: 3; >=4: 1)"], 1)
        scores["ort_oud_items"] = [False] * 9
        self.assertTrue(validate_scores(scores))

    def test_standard_comm_sum_no_reverse_scoring_and_missing_items(self):
        for value in range(5):
            self.assertEqual(calculate_comm([float(value)] * 17), value * 17)
        self.assertEqual(calculate_comm([1.0] * 16 + [None]), 16)
        self.assertIsNone(calculate_comm([None] * 17))
        for maximum in (64, 28):
            self.assertEqual(calculate_comm([4.0] * (maximum // 4), maximum), maximum)
        for value in (-1.0, 5.0, 1.5, math.nan, math.inf):
            with self.assertRaises(ValueError):
                calculate_comm([value] + [0.0] * 16)
        with self.assertRaises(ValueError):
            calculate_comm([0.0] * 16)
        with self.assertRaises(ValueError):
            calculate_comm([0.0] * 17, 99)

    def test_standard_comm_cutoff_and_modified_interpretation(self):
        for value in range(69):
            self.assertTrue(severity_comm(value).startswith("Negative" if value < 9 else "Positive"))
        for maximum in (28, 64):
            scores = {**low_scores(), "comm_max": maximum, "comm": 23.0}
            self.assertEqual(validate_scores(scores), [])
            self.assertIn("standard 17-item cutoff applied to modified form", severity_comm(23, maximum))
            self.assertEqual(risk_level(scores, "consistent", "stable", []), "Moderate")
            self.assertEqual(risk_contributions(scores, "consistent", "stable", [])[f"Modified COMM-{maximum // 4} (>=18: 3; >=9: 2)"], 3)
        scores = {**low_scores(), "comm_items": [0.0] * 17}
        self.assertTrue(validate_scores(scores))
        scores["comm"] = 0.0
        self.assertEqual(validate_scores(scores), [])

    def test_blank_items_are_skipped_but_flagged_for_review(self):
        scores = {**low_scores(), "comm_items": [1.0] * 14 + [None, None, 1.0], "comm": calculate_comm([1.0] * 14 + [None, None, 1.0])}
        self.assertEqual(scores["comm"], 15)
        self.assertEqual(validate_scores(scores), [])
        missing = missing_information(scores, "consistent", "stable")
        self.assertIn("COMM item(s) 15, 16 blank - needs review (total calculated by skipping blanks)", missing)
        self.assertEqual(risk_level(scores, "consistent", "stable", []), "Insufficient information")
        self.assertIn("PROVISIONAL", make_report(scores, [], "consistent", "stable")[0])


if __name__ == "__main__":
    unittest.main()
