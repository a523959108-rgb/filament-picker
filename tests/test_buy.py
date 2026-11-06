import json
from pathlib import Path
from urllib.parse import unquote

from filament_picker.buy import (
    PDD_SEARCH_PREFIX,
    brand_search_name,
    is_github_color_table_url,
    is_pdd_goods_url,
    pdd_search_url,
    price_text_for,
    purchase_links,
    search_query,
)

GOODS = "https://mobile.pinduoduo.com/goods.html?goods_id=931315367733"
GITHUB = (
    "https://github.com/bambulab/BambuStudio/blob/master/resources/profiles/"
    "BBL/filament/filaments_color_codes.json"
)
STORE = "https://jp.store.bambulab.com/products/petg-basic"


def _entry(**extra: object) -> dict:
    entry = {
        "brand_slug": "bambu-lab",
        "brand_name": "Bambu Lab",
        "series_name": "PETG Basic",
        "material": "PETG",
        "name_zh": "黑色",
        "name_en": "Black",
        "code": "30105",
        "offers": [{"channel": "store", "url": STORE, "price_text": "¥2,800 JPY"}],
    }
    entry.update(extra)
    return entry


def test_brand_search_name_reuses_cjk_alias_and_fills_gaps() -> None:
    assert brand_search_name("bambu-lab", "Bambu Lab") == "拓竹"
    assert brand_search_name("sunlu", "SUNLU") == "三绿"
    assert brand_search_name("esun", "eSUN") == "易生"
    assert brand_search_name("byehassle", "没毛病/ByeHassle") == "没毛病"
    assert brand_search_name("polymaker", "Polymaker") == "宝丽玛"
    assert brand_search_name("eryone", "Eryone") == "艾瑞欧"
    assert brand_search_name("kexcelled", "Kexcelled") == "凯想"
    assert brand_search_name("overture", "Overture") == "Overture"
    assert brand_search_name("hatchbox", "Hatchbox") == "Hatchbox"


def test_search_query_uses_chinese_brand_series_and_color() -> None:
    assert search_query(_entry()) == "拓竹 PETG Basic 黑色"


def test_search_query_uses_english_color_when_chinese_is_missing() -> None:
    query = search_query(
        _entry(
            brand_slug="esun",
            brand_name="eSUN",
            series_name="PETG-Basic",
            name_zh=None,
            name_en="Black",
        )
    )
    assert query == "易生 PETG-Basic Black"


def test_search_query_strips_channel_note_and_does_not_repeat_material() -> None:
    query = search_query(
        _entry(
            brand_slug="byehassle",
            brand_name="没毛病/ByeHassle",
            series_name="PLA哑光（拼多多）",
            material="PLA",
            name_zh="樱花粉",
            name_en="Sakura Bloom",
        )
    )
    assert query == "没毛病 PLA哑光 樱花粉"


def test_search_query_adds_material_when_series_omits_it() -> None:
    query = search_query(
        _entry(
            brand_slug="hatchbox",
            brand_name="Hatchbox",
            series_name="Matte",
            material="PLA",
            name_zh=None,
            name_en="Black",
        )
    )
    assert query == "Hatchbox PLA Matte Black"


def test_pdd_search_url_is_public_and_has_no_goods_id() -> None:
    url = pdd_search_url("拓竹 PLA 黑色")
    assert url.startswith(PDD_SEARCH_PREFIX)
    assert unquote(url.removeprefix(PDD_SEARCH_PREFIX)) == "拓竹 PLA 黑色"
    assert "goods_id" not in url
    assert " " not in url.split("?", 1)[1]
    assert is_pdd_goods_url(url) is False


def test_goods_url_detection() -> None:
    assert is_pdd_goods_url(GOODS) is True
    assert is_pdd_goods_url("https://mobile.yangkeduo.com/goods.html?goods_id=42") is True
    assert is_pdd_goods_url("https://mobile.pinduoduo.com/goods.html?goods_id=not-real") is False
    assert is_pdd_goods_url(STORE) is False
    assert is_pdd_goods_url(GITHUB) is False
    assert is_github_color_table_url(GITHUB) is True
    assert is_github_color_table_url(STORE) is False


def test_real_goods_url_is_kept_and_has_no_alternate() -> None:
    primary, alt = purchase_links(_entry(offers=[{"url": GOODS, "price_text": "¥34.5"}]))
    assert primary == GOODS
    assert alt is None
    assert (
        price_text_for(_entry(offers=[{"url": GOODS, "price_text": "¥34.5"}]), primary) == "¥34.5"
    )


def test_missing_goods_url_uses_search_and_keeps_store_as_alt() -> None:
    primary, alt = purchase_links(_entry())
    assert primary == pdd_search_url("拓竹 PETG Basic 黑色")
    assert "goods_id" not in primary
    assert alt == STORE
    assert price_text_for(_entry(), primary) == "¥2,800 JPY"


def test_github_color_table_is_neither_primary_nor_alternate() -> None:
    primary, alt = purchase_links(
        _entry(
            series_name="PLA Tough",
            material="PLA",
            offers=[{"url": GITHUB, "price_text": ""}],
        )
    )
    assert primary == pdd_search_url("拓竹 PLA Tough 黑色")
    assert alt is None
    assert (
        price_text_for(
            _entry(offers=[{"url": GITHUB, "price_text": ""}]),
            primary,
        )
        is None
    )


def test_goods_url_is_promoted_ahead_of_the_store_link() -> None:
    goods = "https://mobile.yangkeduo.com/goods.html?goods_id=42"
    store = "https://store.example.com/pla"
    entry = _entry(
        brand_slug="jayo",
        brand_name="Jayo",
        series_name="Matte PLA",
        material="PLA",
        name_zh=None,
        name_en="Black",
        offers=[
            {"url": store, "price_text": "US$20"},
            {"url": goods, "price_text": "¥19"},
        ],
    )
    primary, alt = purchase_links(entry)
    assert primary == goods
    assert alt == store
    assert price_text_for(entry, primary) == "¥19"


def test_first_store_offer_is_the_alternate_when_several_exist() -> None:
    official = "https://www.cailab3d.com/products/rainbow-shift-pla-filament"
    taobao = "https://pcdetail.taobao.com/example.html"
    primary, alt = purchase_links(
        _entry(
            brand_slug="cailab",
            brand_name="彩多屋 CaiLab",
            series_name="Rainbow shift PLA",
            material="PLA",
            name_zh=None,
            name_en="Bamboo",
            offers=[{"url": official}, {"url": taobao}],
        )
    )
    assert primary == pdd_search_url("彩多屋 Rainbow shift PLA Bamboo")
    assert alt == official


def test_catalog_entries_prefer_pdd(repo_root: Path) -> None:
    catalog = json.loads(
        (repo_root / "data/build/filament-catalog.json").read_text(encoding="utf-8")
    )
    goods = 0
    search = 0
    for entry in catalog["entries"]:
        primary, alt = purchase_links(entry)
        original_goods = [
            offer["url"] for offer in entry["offers"] if is_pdd_goods_url(offer["url"])
        ]
        if original_goods:
            assert primary == original_goods[0]
            goods += 1
        else:
            assert primary.startswith(PDD_SEARCH_PREFIX)
            assert "goods_id" not in primary
            search += 1
        assert is_github_color_table_url(primary) is False
        if alt is not None:
            assert alt != primary
            assert is_github_color_table_url(alt) is False
            assert is_pdd_goods_url(alt) is False
            assert any(offer["url"] == alt for offer in entry["offers"])
    assert goods == 136
    assert search == 3712
    assert goods + search == len(catalog["entries"]) == 3848

    bambu = next(
        entry for entry in catalog["entries"] if entry["id"] == "bambu-lab/petg-basic/black-30105"
    )
    primary, alt = purchase_links(bambu)
    assert unquote(primary.removeprefix(PDD_SEARCH_PREFIX)) == "拓竹 PETG Basic 黑色"
    assert alt == "https://jp.store.bambulab.com/products/petg-basic"

    tough = next(
        entry for entry in catalog["entries"] if entry["id"] == "bambu-lab/pla-tough/black-12101"
    )
    primary, alt = purchase_links(tough)
    assert unquote(primary.removeprefix(PDD_SEARCH_PREFIX)) == "拓竹 PLA Tough 黑色"
    assert alt is None
