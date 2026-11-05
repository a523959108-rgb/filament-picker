import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
TZ: str = "Asia/Tokyo"
MAX_SLUG_LEN: int = 60
HEX_CONF_OFFICIAL: float = 1.0
HEX_CONF_STORE_SWATCH: float = 0.8
HEX_CONF_MANUAL: float = 0.9
SOURCE_RANK: dict[str, int] = {
    "official": 0,
    "store_swatch": 1,
    "manual": 2,
    "image_extracted": 3,
}
EXTRACT_LONG_SIDE: int = 256
BORDER_PX: int = 4
BG_BORDER_AGREE_DE: float = 10.0
BG_BORDER_AGREE_FRAC: float = 0.60
BG_REMOVE_DE: float = 12.0
HIGHLIGHT_L: float = 92.0
HIGHLIGHT_C: float = 10.0
SHADOW_L: float = 8.0
SHADOW_KEEP_MIN_FRAC: float = 0.15
MIN_PIXELS: int = 500
MAX_SAMPLE: int = 20000
EXTRACT_K_SINGLE: int = 3
EXTRACT_K_MULTI: int = 6
MULTI_MIN_SHARE: float = 0.15
MULTI_MAX_COLORS: int = 3
CONF_SPREAD_DE: float = 10.0
CONF_PENALTY_EFFECTS: tuple[str, ...] = ("silk", "translucent", "glow", "sparkle")
CONF_PENALTY_FACTOR: float = 0.6
EXTRACT_MIN_CONF: float = 0.40
KMEANS_MAX_ITER: int = 20
KMEANS_TOL: float = 0.01
PLAN_LONG_SIDE: int = 512
PLAN_MAX_SAMPLE: int = 40000
PLAN_MIN_SIDE: int = 64
DEFAULT_MAX_COLORS: int = 4
DEFAULT_AMS_SLOTS: int = 4
DEFAULT_PER_COLOR: int = 2
DEFAULT_MATERIALS: tuple[str, ...] = ("PLA",)
MERGE_DE: float = 6.0
SMALL_SHARE: float = 0.02
MATCH_MAX_DE: float = 10.0
MATCH_MIN_CONF: float = 0.5
LABEL_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (2.0, "几乎一样"),
    (5.0, "接近"),
    (10.0, "勉强"),
)
MATCH_EXCLUDE_EFFECTS: tuple[str, ...] = (
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
)
WORKER_POLL_S: float = 1.0
CLEANUP_INTERVAL_S: int = 3600
RETENTION_DAYS: int = 7
CARD_TOKEN_BYTES: int = 24


@dataclass(frozen=True, slots=True)
class Settings:
    root: Path
    catalog: Path
    card_base_url: str | None
    shots_dir: Path
    font_regular: Path
    font_bold: Path
    font_index: int


def get_settings() -> Settings:
    root = Path(os.environ.get("FP_ROOT", "/home/box/agent-data/shared/filament-picker"))
    catalog = Path(
        os.environ.get("FP_CATALOG", str(REPO_ROOT / "data/build/filament-catalog.json"))
    )
    card_base_url = os.environ.get("FP_CARD_BASE_URL") or None
    if card_base_url is not None and not card_base_url.startswith("https://"):
        raise ValueError("FP_CARD_BASE_URL must start with https://")
    shots_dir = Path(os.environ.get("FP_SHOTS_DIR", "/workspace/filament-shots"))
    font_regular = Path(
        os.environ.get("FP_FONT_REGULAR", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    )
    font_bold = Path(
        os.environ.get("FP_FONT_BOLD", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")
    )
    font_index = int(os.environ.get("FP_FONT_INDEX", "2"))
    return Settings(root, catalog, card_base_url, shots_dir, font_regular, font_bold, font_index)
