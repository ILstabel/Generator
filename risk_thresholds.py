"""Selectable thresholds for integrated opioid-risk points and the overall Moderate/High levels.

The default preset reproduces the original template exactly. Other presets are local clinic
choices and have not been validated.
"""

from dataclasses import dataclass

# Section key -> (display name, score maximum, points at the moderate threshold, points at the high threshold).
SECTIONS: dict[str, tuple[str, int, int, int]] = {
    "COMM": ("COMM (any form)", 68, 2, 3),
    "ORT": ("ORT / ORT-OUD", 26, 1, 3),
    "PHQ-9": ("PHQ-9 total", 27, 1, 2),
    "Overall": ("Overall risk level (total points)", 19, 0, 0),
}

DEFAULT_PRESET = "Original template (default)"
CUSTOM = "Custom"


@dataclass(frozen=True)
class Thresholds:
    """Each value is a (moderate, high) pair of minimum scores; Overall holds the points needed for Moderate and High."""

    preset: str
    cutoffs: tuple[tuple[str, tuple[int, int]], ...]

    def get(self, section: str) -> tuple[int, int]:
        return dict(self.cutoffs)[section]

    @property
    def is_default(self) -> bool:
        return self.cutoffs == PRESETS[DEFAULT_PRESET].cutoffs

    def describe(self) -> str:
        return "; ".join(f"{section} moderate >={moderate}, high >={high}" for section, (moderate, high) in self.cutoffs)


def make_thresholds(preset: str, values: dict[str, tuple[int, int]]) -> Thresholds:
    errors = validate_cutoffs(values)
    if errors:
        raise ValueError("\n".join(errors))
    return Thresholds(preset, tuple((section, tuple(values[section])) for section in SECTIONS))


def validate_cutoffs(values: dict[str, tuple[int, int]]) -> list[str]:
    errors = []
    for section, (name, maximum, _, _) in SECTIONS.items():
        if section not in values:
            errors.append(f"{name}: thresholds missing.")
            continue
        moderate, high = values[section]
        if not (1 <= moderate <= maximum and 1 <= high <= maximum):
            errors.append(f"{name}: thresholds must be between 1 and {maximum}.")
        elif moderate >= high:
            errors.append(f"{name}: the moderate threshold ({moderate}) must be lower than the high threshold ({high}).")
    return errors


PRESETS: dict[str, Thresholds] = {}
PRESETS[DEFAULT_PRESET] = make_thresholds(DEFAULT_PRESET, {
    "COMM": (9, 18), "ORT": (4, 8), "PHQ-9": (15, 20), "Overall": (2, 5),
})
PRESETS["Conservative (flags more patients)"] = make_thresholds("Conservative (flags more patients)", {
    "COMM": (9, 14), "ORT": (3, 6), "PHQ-9": (10, 15), "Overall": (2, 4),
})
PRESETS["Lenient (flags fewer patients)"] = make_thresholds("Lenient (flags fewer patients)", {
    "COMM": (12, 24), "ORT": (5, 9), "PHQ-9": (20, 25), "Overall": (3, 6),
})
DEFAULT = PRESETS[DEFAULT_PRESET]


def tiered_points(value: float | None, section: str, thresholds: Thresholds) -> int:
    if value is None:
        return 0
    _, _, moderate_points, high_points = SECTIONS[section]
    moderate, high = thresholds.get(section)
    return high_points if value >= high else moderate_points if value >= moderate else 0


def rule_label(section: str, thresholds: Thresholds) -> str:
    """Point rule in the original template wording, e.g. '>=18: 3; >=9: 2'."""
    _, _, moderate_points, high_points = SECTIONS[section]
    moderate, high = thresholds.get(section)
    return f">={high}: {high_points}; >={moderate}: {moderate_points}"


def rule_text(section: str, thresholds: Thresholds) -> str:
    """Plain-language point rule, e.g. '9-17: 2 points; 18 or more: 3 points'."""
    _, _, moderate_points, high_points = SECTIONS[section]
    moderate, high = thresholds.get(section)
    plural = lambda points: f"{points} point{'s' if points != 1 else ''}"
    return f"{moderate}-{high - 1}: {plural(moderate_points)}; {high} or more: {plural(high_points)}"
