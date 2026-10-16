"""Loads and validates scoring_config.json, the reference table that scoring interpretation follows."""

import json
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).with_name("scoring_config.json")


class ConfigError(ValueError):
    pass


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    instruments = config.get("instruments")
    if not isinstance(instruments, dict):
        raise ConfigError("scoring config: 'instruments' mapping is required.")
    for name in ("PEG", "PDI", "PHQ-9", "ORT-OUD", "AUDIT", "COMM"):
        if name not in instruments:
            raise ConfigError(f"scoring config: missing instrument {name}.")
    for name, tool in instruments.items():
        low, high = tool["range"]
        bands = tool.get("bands", [])
        if bands:
            if bands[0]["min"] != low or bands[-1]["max"] != high:
                raise ConfigError(f"scoring config: {name} bands must cover {low}-{high}.")
            for previous, current in zip(bands, bands[1:]):
                if current["min"] != previous["max"] + 1:
                    raise ConfigError(f"scoring config: {name} bands must be contiguous without overlap.")
            for band in bands:
                if band["min"] > band["max"] or not band.get("label"):
                    raise ConfigError(f"scoring config: {name} band {band} is invalid.")
    improvement = instruments["PEG"].get("improvement", {})
    if improvement.get("rule") not in {"any", "all"}:
        raise ConfigError("scoring config: PEG improvement rule must be 'any' or 'all'.")
    return config


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    try:
        return validate_config(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError) as error:
        if isinstance(error, ConfigError):
            raise
        raise ConfigError(f"Cannot load scoring config {path}: {error}") from error


CONFIG = load_config()


def instrument(name: str) -> dict[str, Any]:
    return CONFIG["instruments"][name]


def band_label(name: str, value: float) -> str:
    """Interpretation label for a score, following the configured inclusive bands."""
    tool = instrument(name)
    low, high = tool["range"]
    if not low <= value <= high:
        raise ValueError(f"{name} score {value:g} is outside the configured range {low}-{high}.")
    label = tool["bands"][0]["label"]
    for band in tool["bands"]:
        if value >= band["min"]:
            label = band["label"]
    return label


def band_table(name: str) -> str:
    return "; ".join(f"{band['min']}-{band['max']}: {band['label']}" for band in instrument(name)["bands"])
