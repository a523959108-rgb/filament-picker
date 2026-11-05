from __future__ import annotations

BRAND_SLUGS: dict[str, str] = {
    "Bambu Lab": "bambu-lab",
    "Polymaker": "polymaker",
    "Eryone": "eryone",
    "SUNLU": "sunlu",
    "Overture": "overture",
    "彩多屋 CaiLab": "cailab",
    "Elegoo": "elegoo",
    "Hatchbox": "hatchbox",
    "Kexcelled": "kexcelled",
    "eSUN": "esun",
    "Anycubic": "anycubic",
    "Proto-pasta": "proto-pasta",
    "Amolen": "amolen",
    "Atomic Filament": "atomic-filament",
    "Creality": "creality",
    "Jayo": "jayo",
    "阿米阿米/RMERME": "rmerme",
    "Prusament": "prusament",
    "天瑞 Tinmorry/Tronhoo": "tinmorry",
    "彩格": "caige",
    "没毛病/ByeHassle": "byehassle",
}

BRAND_ALIASES: dict[str, tuple[str, ...]] = {
    "bambu-lab": ("拓竹", "bambu", "bambulab"),
    "polymaker": ("polymaker",),
    "eryone": ("eryone",),
    "sunlu": ("sunlu", "三绿"),
    "overture": ("overture",),
    "cailab": ("彩多屋", "cailab"),
    "elegoo": ("elegoo", "爱乐酷"),
    "hatchbox": ("hatchbox",),
    "kexcelled": ("kexcelled",),
    "esun": ("esun", "易生"),
    "anycubic": ("anycubic", "纵维"),
    "proto-pasta": ("proto-pasta", "protopasta"),
    "amolen": ("amolen",),
    "atomic-filament": ("atomic",),
    "creality": ("creality", "创想"),
    "jayo": ("jayo",),
    "rmerme": ("阿米阿米", "rmerme"),
    "prusament": ("prusament", "prusa"),
    "tinmorry": ("天瑞", "tinmorry", "tronhoo"),
    "caige": ("彩格",),
    "byehassle": ("没毛病", "byehassle"),
}

BRAND_ORDER: tuple[str, ...] = tuple(BRAND_SLUGS.values())


class UnknownBrandError(ValueError):
    pass


def brand_slug(name: str) -> str:
    try:
        return BRAND_SLUGS[name]
    except KeyError as exc:
        raise UnknownBrandError(name) from exc
