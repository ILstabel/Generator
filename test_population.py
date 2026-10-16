import unittest
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from app import calculate_phq9
from population_insights import DATA_PATH, SMALL_GROUP, checkins, merge_small_groups, participant_profiles


def synthetic_rows() -> pd.DataFrame:
    rows = []
    for user, (items, age, sex) in enumerate((
        ([3] * 9, 30, "female"), ([0] * 9, 20, "male"), ([None] * 9, None, None), ([1] + [None] * 8, 50, "transgender"),
    ), 1):
        for day, mood in enumerate((1, 3)):
            rows.append({
                "user_id": user, "age": age, "sex": sex, "happiness.score": mood, "period.name": "morning",
                "time": f"2017-01-0{day + 2} 08:00:00", "start.time": "2017-01-01 20:00:00",
                **{f"phq{index}": value for index, value in enumerate(items, 1)},
            })
    return pd.DataFrame(rows)


class PopulationDataTests(unittest.TestCase):
    def test_small_and_missing_groups_are_merged(self):
        merged = merge_small_groups(pd.Series(["a"] * 5 + ["b"] * 4 + [None]))
        self.assertEqual(merged.value_counts().to_dict(), {"a": 5, SMALL_GROUP: 5})

    def test_profiles_use_app_phq9_rules(self):
        people = participant_profiles(synthetic_rows(), calculate_phq9).set_index("user_id")
        self.assertEqual(people.loc[1, "phq9_total"], 27)
        self.assertEqual(people.loc[1, "item9_group"], "Positive (>0)")
        self.assertEqual(people.loc[2, "severity"], "Minimal")
        self.assertEqual(people.loc[3, "severity"], "Incomplete PHQ-9")
        self.assertEqual(people.loc[4, "severity"], "Incomplete PHQ-9")
        self.assertTrue(pd.isna(people.loc[4, "phq9_total"]))
        self.assertEqual(people.loc[3, "item9_group"], "Not answered")
        self.assertEqual(set(people["sex"]), {SMALL_GROUP})
        self.assertEqual(people.loc[1, "mean_mood"], 2)
        self.assertEqual(checkins(synthetic_rows())["study_day"].tolist()[:2], [0, 1])


@unittest.skipUnless(DATA_PATH.is_file(), "population dataset not present")
class PopulationTabTests(unittest.TestCase):
    def test_tab_renders_charts_and_filters(self):
        app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=60).run()
        self.assertFalse(app.exception)
        self.assertEqual([tab.label for tab in app.tabs], ["Assessment", "Insights", "About"])
        self.assertEqual(app.metric[0].value, "185")
        for grouping in ("Sex", "Age group", "PHQ-9 item #9", "Depression severity"):
            app.selectbox(key="population_grouping").select(grouping).run()
            self.assertFalse(app.exception)
        self.assertEqual(app.multiselect(key="population_sex").value, [])
        app.multiselect(key="population_sex").set_value(["Male"]).run()
        self.assertEqual(app.metric[0].value, "31")
        app.multiselect(key="population_sex").set_value(["Male", "Female"]).run()
        self.assertEqual(app.metric[0].value, "160")
        app.multiselect(key="population_age").set_value(["Under 18", "18-24"]).run()
        self.assertEqual(app.multiselect(key="population_age").options[0], "Under 18")
        self.assertFalse(app.exception)
        app.multiselect(key="population_sex").set_value([]).run()
        app.multiselect(key="population_age").set_value([]).run()
        self.assertEqual(app.metric[0].value, "185")


if __name__ == "__main__":
    unittest.main()
