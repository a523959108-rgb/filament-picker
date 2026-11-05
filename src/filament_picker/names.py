import re
import unicodedata
from dataclasses import dataclass

WEIGHT: re.Pattern[str] = re.compile(r"\s*[-/]?\s*\d+(?:\.\d+)?\s*kg\b", re.I)
PCODE: re.Pattern[str] = re.compile(r"\s*\((\d{4,6})\)\s*$")
TCODE: re.Pattern[str] = re.compile(r"(?<=\s)([A-Z]{1,4}\d{2,5}[A-Z]?)\s*$")
ZH: re.Pattern[str] = re.compile(r"[\u3400-\u9fff](?:[\u3400-\u9fff\-·]*[\u3400-\u9fff])?")


@dataclass(frozen=True, slots=True)
class ParsedName:
    name_en: str | None
    name_zh: str | None
    code: str | None


def nfkc(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def parse_color_name(raw: str) -> ParsedName:
    s = nfkc(raw)
    s = WEIGHT.sub("", s).strip()
    code = None
    m = PCODE.search(s)
    if m is None:
        m = TCODE.search(s)
    if m is not None:
        code = m[1]
        s = s[: m.start()].strip()
    name_zh = " ".join(ZH.findall(s)) or None
    en = ZH.sub(" ", s)
    en = re.sub(r"\(\s*\)", "", en)
    en = re.sub(r"\s+", " ", en).strip(" -/")
    if m := re.fullmatch(r"\((.*)\)", en):
        en = m[1].strip()
    name_en = en or None
    return ParsedName(name_en=name_en, name_zh=name_zh, code=code)
