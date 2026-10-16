"""Population insights tab: PHQ-9 and mood visualizations from the research dataset in Data\\."""

from pathlib import Path
from typing import Any, Callable

import altair as alt
import pandas as pd
import streamlit as st

from scoring_config import band_label, instrument

DATA_PATH = Path(__file__).with_name("Data") / "Dataset_14-day_AA_depression_symptoms_mood_and_PHQ-9.csv"
PHQ_ITEMS = [f"phq{index}" for index in range(1, 10)]
ITEM_NAMES = [
    "1 Interest", "2 Low mood", "3 Sleep", "4 Energy", "5 Appetite",
    "6 Self-worth", "7 Concentration", "8 Psychomotor", "9 Self-harm thoughts",
]
MIN_GROUP = 5
SMALL_GROUP = "Other / not reported"
INCOMPLETE = "Incomplete PHQ-9"
AGE_BINS = [0, 17, 24, 34, 44, 200]
AGE_LABELS = ["Under 18", "18-24", "25-34", "35-44", "45+"]
GROUPINGS = {
    "Depression severity": "severity",
    "Sex": "sex",
    "Age group": "age_group",
    "PHQ-9 item #9": "item9_group",
}
PERIOD_ORDER = ["morning", "midday", "evening"]


def severity_order() -> list[str]:
    return [band["label"].split(" (")[0] for band in instrument("PHQ-9")["bands"]] + [INCOMPLETE]


def merge_small_groups(values: pd.Series, minimum: int = MIN_GROUP) -> pd.Series:
    """Fold groups with fewer than ``minimum`` participants (and missing values) into one group."""
    values = values.fillna(SMALL_GROUP)
    counts = values.value_counts()
    small = counts[counts < minimum].index
    return values.where(~values.isin(small), SMALL_GROUP)


def participant_profiles(data: pd.DataFrame, score_phq9: Callable[[list[float | None]], dict[str, Any]]) -> pd.DataFrame:
    """One row per participant: demographics, PHQ-9 total/severity (app scoring rules) and mood summary."""
    first = lambda column: column.dropna().iloc[0] if column.notna().any() else None  # noqa: E731
    people = data.groupby("user_id").agg(
        age=("age", first), sex=("sex", first), checkins=("happiness.score", "size"),
        mean_mood=("happiness.score", "mean"), **{item: (item, first) for item in PHQ_ITEMS},
    ).reset_index()
    totals, severities = [], []
    for row in people[PHQ_ITEMS].itertuples(index=False):
        result = score_phq9([None if pd.isna(value) else float(value) for value in row])
        complete = result["total"] is not None and not result["provisional"]
        totals.append(result["total"] if complete else None)
        severities.append(band_label("PHQ-9", result["total"]).split(" (")[0] if complete else INCOMPLETE)
    people["phq9_total"] = pd.array(totals, dtype="Int64")
    people["severity"] = pd.Categorical(severities, categories=severity_order(), ordered=True)
    people["sex"] = merge_small_groups(people["sex"].str.capitalize())
    people["age_group"] = merge_small_groups(
        pd.cut(people["age"], AGE_BINS, labels=AGE_LABELS).astype("string").astype(object)
    )
    people["item9_group"] = people["phq9"].map(
        lambda value: "Not answered" if pd.isna(value) else "Positive (>0)" if value > 0 else "Negative (0)"
    )
    return people


def checkins(data: pd.DataFrame) -> pd.DataFrame:
    """One row per mood check-in with the whole study day since the participant started."""
    frame = data[["user_id", "time", "start.time", "period.name", "happiness.score"]].copy()
    elapsed = pd.to_datetime(frame["time"]) - pd.to_datetime(frame["start.time"])
    frame["study_day"] = (elapsed.dt.total_seconds() // 86400).astype(int)
    return frame.rename(columns={"period.name": "period", "happiness.score": "mood"})


@st.cache_data(show_spinner="Loading population dataset...")
def load_population(path: str, modified: float, _score_phq9: Callable) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = pd.read_csv(path)
    return participant_profiles(data, _score_phq9), checkins(data)


def _filter_options(label: str, values: pd.Series, key: str) -> list[str]:
    """Multi-select filter that shows every group until the user picks specific ones."""
    options = [value for value in pd.unique(values.astype(str)) if value != "nan"]
    order = {"Depression severity": severity_order(), "Age group": AGE_LABELS}.get(label, sorted(options))
    options = [value for value in order if value in options] + sorted(set(options) - set(order))
    if SMALL_GROUP in options:
        options = [value for value in options if value != SMALL_GROUP] + [SMALL_GROUP]
    chosen = st.multiselect(label, options, key=key, placeholder="All")
    return chosen or options


def population_view(path: Path = DATA_PATH, score_phq9: Callable | None = None) -> None:
    st.subheader("Insights")
    st.caption(
        "Research dataset (14-day depression symptom and mood study), not patients of this practice. "
        "PHQ-9 totals use this app's scoring rules; mood is the 0-4 happiness rating from each check-in. "
        f"Groups with fewer than {MIN_GROUP} participants are combined into \"{SMALL_GROUP}\" to avoid identifying individuals."
    )
    if score_phq9 is None or not path.is_file():
        st.info(f"Add the dataset to {path} to enable population insights.")
        return
    try:
        people, moods = load_population(str(path), path.stat().st_mtime, score_phq9)
    except (OSError, ValueError, KeyError) as error:
        st.error(f"Cannot read the population dataset: {error}")
        return

    with st.expander("Filter populations", expanded=True):
        columns = st.columns(4)
        with columns[0]:
            sexes = _filter_options("Sex", people["sex"], "population_sex")
        with columns[1]:
            ages = _filter_options("Age group", people["age_group"], "population_age")
        with columns[2]:
            severities = _filter_options("Depression severity", people["severity"], "population_severity")
        with columns[3]:
            grouping_label = st.selectbox("Compare populations by", list(GROUPINGS), key="population_grouping")
    group = GROUPINGS[grouping_label]
    selected = people[
        people["sex"].isin(sexes) & people["age_group"].isin(ages) & people["severity"].astype(str).isin(severities)
    ]
    if selected.empty:
        st.warning("No participants match the selected filters.")
        return
    scored = selected[selected["phq9_total"].notna()]
    selected_moods = moods[moods["user_id"].isin(selected["user_id"])].merge(selected[["user_id", group]], on="user_id")

    metrics = st.columns(5)
    metrics[0].metric("Participants", f"{len(selected)}")
    metrics[1].metric("Mood check-ins", f"{len(selected_moods):,}")
    metrics[2].metric("Median PHQ-9", f"{scored['phq9_total'].median():.0f}" if len(scored) else "-")
    metrics[3].metric("Moderate or worse", f"{(scored['phq9_total'] >= 10).mean():.0%}" if len(scored) else "-")
    answered9 = selected[selected["phq9"].notna()]
    metrics[4].metric("Item #9 positive", f"{(answered9['phq9'] > 0).mean():.0%}" if len(answered9) else "-")

    left, right = st.columns(2)
    with left:
        st.markdown("**Depression severity mix by population**")
        mix = selected.groupby(list(dict.fromkeys([group, "severity"])), observed=True).size().reset_index(name="participants")
        st.altair_chart(
            alt.Chart(mix).mark_bar().encode(
                y=alt.Y(f"{group}:N", title=grouping_label),
                x=alt.X("participants:Q", stack="normalize", title="Share of participants", axis=alt.Axis(format="%")),
                color=alt.Color("severity:N", sort=severity_order(), title="Severity",
                                scale=alt.Scale(scheme="orangered")),
                order=alt.Order("severity:N"),
                tooltip=[f"{group}:N", "severity:N", "participants:Q"],
            ),
            use_container_width=True,
        )
    with right:
        st.markdown("**PHQ-9 total distribution**")
        st.altair_chart(
            alt.Chart(scored.assign(phq9_total=scored["phq9_total"].astype(float))).mark_boxplot(extent="min-max").encode(
                x=alt.X(f"{group}:N", title=grouping_label),
                y=alt.Y("phq9_total:Q", title="PHQ-9 total (0-27)", scale=alt.Scale(domain=[0, 27])),
                color=alt.Color(f"{group}:N", legend=None),
            ),
            use_container_width=True,
        )

    left, right = st.columns(2)
    with left:
        st.markdown("**PHQ-9 item #9 (self-harm thoughts) positive rate**")
        rates = answered9.groupby(group, observed=True)["phq9"].agg(
            positive_rate=lambda values: (values > 0).mean(), participants="size",
        ).reset_index()
        st.altair_chart(
            alt.Chart(rates).mark_bar().encode(
                x=alt.X(f"{group}:N", title=grouping_label),
                y=alt.Y("positive_rate:Q", title="Item #9 > 0", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
                color=alt.Color(f"{group}:N", legend=None),
                tooltip=[f"{group}:N", alt.Tooltip("positive_rate:Q", format=".0%"), "participants:Q"],
            ),
            use_container_width=True,
        )
    with right:
        st.markdown("**Symptom profile: mean item score (0-3)**")
        items = selected.groupby(group, observed=True)[PHQ_ITEMS].mean().reset_index().melt(
            id_vars=group, var_name="item", value_name="mean_score",
        )
        items["item"] = items["item"].map(dict(zip(PHQ_ITEMS, ITEM_NAMES)))
        st.altair_chart(
            alt.Chart(items).mark_rect().encode(
                x=alt.X("item:N", sort=ITEM_NAMES, title=None),
                y=alt.Y(f"{group}:N", title=grouping_label),
                color=alt.Color("mean_score:Q", title="Mean", scale=alt.Scale(scheme="reds", domain=[0, 3])),
                tooltip=[f"{group}:N", "item:N", alt.Tooltip("mean_score:Q", format=".2f")],
            ),
            use_container_width=True,
        )

    st.markdown("**Mood trend over the study (mean 0-4 rating per study day)**")
    last_day = st.slider("Study days shown", 7, int(min(moods["study_day"].max(), 120)), 14, key="population_days")
    trend = selected_moods[selected_moods["study_day"] <= last_day].groupby(["study_day", group], observed=True).agg(
        mood=("mood", "mean"), checkins=("mood", "size"), participants=("user_id", "nunique"),
    ).reset_index()
    trend = trend[trend["participants"] >= MIN_GROUP]
    st.altair_chart(
        alt.Chart(trend).mark_line(point=True).encode(
            x=alt.X("study_day:Q", title="Study day"),
            y=alt.Y("mood:Q", title="Mean mood (0-4)", scale=alt.Scale(domain=[0, 4])),
            color=alt.Color(f"{group}:N", title=grouping_label),
            tooltip=["study_day:Q", f"{group}:N", alt.Tooltip("mood:Q", format=".2f"), "participants:Q", "checkins:Q"],
        ),
        use_container_width=True,
    )
    st.caption(f"Days with fewer than {MIN_GROUP} participants in a group are hidden.")

    left, right = st.columns(2)
    with left:
        st.markdown("**Mood by time of day**")
        periods = selected_moods.groupby(["period", group], observed=True)["mood"].mean().reset_index()
        st.altair_chart(
            alt.Chart(periods).mark_bar().encode(
                x=alt.X("period:N", sort=PERIOD_ORDER, title=None),
                xOffset=alt.XOffset(f"{group}:N"),
                y=alt.Y("mood:Q", title="Mean mood (0-4)", scale=alt.Scale(domain=[0, 4])),
                color=alt.Color(f"{group}:N", title=grouping_label),
                tooltip=["period:N", f"{group}:N", alt.Tooltip("mood:Q", format=".2f")],
            ),
            use_container_width=True,
        )
    with right:
        st.markdown("**PHQ-9 total vs average mood (one point per participant)**")
        st.altair_chart(
            alt.Chart(scored.assign(phq9_total=scored["phq9_total"].astype(float))).mark_circle(size=60, opacity=0.7).encode(
                x=alt.X("phq9_total:Q", title="PHQ-9 total", scale=alt.Scale(domain=[0, 27])),
                y=alt.Y("mean_mood:Q", title="Mean mood (0-4)", scale=alt.Scale(domain=[0, 4])),
                color=alt.Color(f"{group}:N", title=grouping_label),
                tooltip=[alt.Tooltip("phq9_total:Q", title="PHQ-9"), alt.Tooltip("mean_mood:Q", format=".2f"),
                         f"{group}:N", "checkins:Q"],
            ),
            use_container_width=True,
        )
    st.caption(
        "Descriptive research data only: these charts do not describe any individual patient and do not change "
        "scoring, risk levels or reports in the Assessment tab."
    )
