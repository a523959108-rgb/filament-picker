import re

from filament_picker.names import nfkc

EFFECT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("matte", re.compile(r"matte|哑光|磨砂")),
    ("silk", re.compile(r"silk|丝绸|丝光")),
    ("dual", re.compile(r"\bdual\b|双色")),
    ("tri", re.compile(r"tri-?colou?r|triple|三色")),
    ("gradient", re.compile(r"gradient|rainbow|渐变|彩虹")),
    ("glow", re.compile(r"glow|夜光")),
    ("translucent", re.compile(r"translucent|transparent|\bclear\b|透明")),
    ("metallic", re.compile(r"metal|金属")),
    ("sparkle", re.compile(r"sparkl|glitter|galaxy|starry|twinkl|estars|闪|星空")),
    ("wood", re.compile(r"\bwood|木纹|木质")),
    ("marble", re.compile(r"marble|大理石")),
    ("cf", re.compile(r"\bcf\b|carbon fib|碳纤")),
    ("gf", re.compile(r"\bgf\b|glass fib|玻纤")),
    ("color_change", re.compile(r"colou?r[ -]?chang|变色|光变|温变")),
)

MULTI_FAMILY: str = "多色/渐变"


def detect_effects(series: str, color_raw: str, family: str) -> tuple[str, ...]:
    t = nfkc(series + " " + color_raw).lower()
    effects = [name for name, pattern in EFFECT_PATTERNS if pattern.search(t)]
    if family == MULTI_FAMILY:
        effects.append("multi")
    return tuple(effects)


def detect_material(series: str) -> str:
    return "PETG" if "PETG" in series.upper() else "PLA"
