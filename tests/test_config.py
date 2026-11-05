from pathlib import Path

import pytest

from filament_picker import config

EXPECTED_CONSTANTS = {
    "TZ": "Asia/Tokyo",
    "MAX_SLUG_LEN": 60,
    "HEX_CONF_OFFICIAL": 1.0,
    "HEX_CONF_STORE_SWATCH": 0.8,
    "HEX_CONF_MANUAL": 0.9,
    "SOURCE_RANK": {"official": 0, "store_swatch": 1, "manual": 2, "image_extracted": 3},
    "EXTRACT_LONG_SIDE": 256,
    "BORDER_PX": 4,
    "BG_BORDER_AGREE_DE": 10.0,
    "BG_BORDER_AGREE_FRAC": 0.60,
    "BG_REMOVE_DE": 12.0,
    "HIGHLIGHT_L": 92.0,
    "HIGHLIGHT_C": 10.0,
    "SHADOW_L": 8.0,
    "SHADOW_KEEP_MIN_FRAC": 0.15,
    "MIN_PIXELS": 500,
    "MAX_SAMPLE": 20000,
    "EXTRACT_K_SINGLE": 3,
    "EXTRACT_K_MULTI": 6,
    "MULTI_MIN_SHARE": 0.15,
    "MULTI_MAX_COLORS": 3,
    "CONF_SPREAD_DE": 10.0,
    "CONF_PENALTY_EFFECTS": ("silk", "translucent", "glow", "sparkle"),
    "CONF_PENALTY_FACTOR": 0.6,
    "EXTRACT_MIN_CONF": 0.40,
    "KMEANS_MAX_ITER": 20,
    "KMEANS_TOL": 0.01,
    "PLAN_LONG_SIDE": 512,
    "PLAN_MAX_SAMPLE": 40000,
    "PLAN_MIN_SIDE": 64,
    "DEFAULT_MAX_COLORS": 4,
    "DEFAULT_AMS_SLOTS": 4,
    "DEFAULT_PER_COLOR": 2,
    "DEFAULT_MATERIALS": ("PLA",),
    "MERGE_DE": 6.0,
    "SMALL_SHARE": 0.02,
    "MATCH_MAX_DE": 10.0,
    "MATCH_MIN_CONF": 0.5,
    "LABEL_THRESHOLDS": ((2.0, "几乎一样"), (5.0, "接近"), (10.0, "勉强")),
    "MATCH_EXCLUDE_EFFECTS": (
        "multi",
        "dual",
        "tri",
        "gradient",
        "color_change",
        "translucent",
        "glow",
        "sparkle",
        "marble",
        "wood",
    ),
    "WORKER_POLL_S": 1.0,
    "CLEANUP_INTERVAL_S": 3600,
    "RETENTION_DAYS": 7,
    "CARD_TOKEN_BYTES": 24,
}


@pytest.mark.parametrize(("name", "expected"), EXPECTED_CONSTANTS.items())
def test_spec_constants(name: str, expected: object) -> None:
    assert getattr(config, name) == expected


def test_repo_root() -> None:
    assert Path(__file__).resolve().parents[1] == config.REPO_ROOT


def test_default_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "FP_ROOT",
        "FP_CATALOG",
        "FP_CARD_BASE_URL",
        "FP_SHOTS_DIR",
        "FP_FONT_REGULAR",
        "FP_FONT_BOLD",
        "FP_FONT_INDEX",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = config.get_settings()
    assert settings.root == Path("/home/box/agent-data/shared/filament-picker")
    assert settings.card_base_url is None
    assert settings.font_index == 2
    assert settings.catalog == config.REPO_ROOT / "data/build/filament-catalog.json"


def test_card_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_CARD_BASE_URL", "http://x.example.invalid")
    with pytest.raises(ValueError, match="FP_CARD_BASE_URL must start with https://"):
        config.get_settings()
    monkeypatch.setenv("FP_CARD_BASE_URL", "https://x.example.invalid/c")
    assert config.get_settings().card_base_url == "https://x.example.invalid/c"
    monkeypatch.setenv("FP_CARD_BASE_URL", "")
    assert config.get_settings().card_base_url is None


def test_font_index(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_FONT_INDEX", "0")
    assert config.get_settings().font_index == 0
