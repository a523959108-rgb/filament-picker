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
    assert goods == 202
    assert search == 3646
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


# Collected 2026-11-09. Shared goods_id values are multi-SKU listings, kept as-is.
BAMBU_PDD_BATCH1: dict[str, str] = {
    "bambu-lab/pla-basic/black-10101": "646322960873",
    "bambu-lab/pla-basic/jade-white-10100": "646322960873",
    "bambu-lab/pla-basic/gray-10103": "646322960873",
    "bambu-lab/pla-basic/light-gray-10104": "646322960873",
    "bambu-lab/pla-basic/dark-gray-10105": "1008327197594",
    "bambu-lab/pla-basic/blue-gray-10602": "981078022134",
    "bambu-lab/pla-basic/red-10200": "995613337990",
    "bambu-lab/pla-basic/maroon-red-10205": "1012953356814",
    "bambu-lab/pla-basic/blue-10601": "981078022134",
    "bambu-lab/pla-basic/cobalt-blue-10604": "961735796587",
    "bambu-lab/pla-basic/blueberry-bubblegum-10905": "955911205517",
    "bambu-lab/pla-basic/bambu-green-10501": "955911205517",
    "bambu-lab/pla-basic/mistletoe-green-10502": "646322960873",
    "bambu-lab/pla-basic/bright-green-10503": "1012953356814",
    "bambu-lab/pla-basic/yellow-10400": "973331464720",
    "bambu-lab/pla-basic/sunflower-yellow-10402": "1024899541908",
    "bambu-lab/pla-basic/orange-10300": "1014117624513",
    "bambu-lab/pla-basic/pumpkin-orange-10301": "1010819723555",
    "bambu-lab/pla-basic/beige-10201": "711535009405",
    "bambu-lab/pla-basic/brown-10800": "954504553679",
    "bambu-lab/pla-matte/ivory-white-11100": "991922531824",
    "bambu-lab/pla-matte/bone-white-11103": "1012964573898",
    "bambu-lab/pla-matte/ash-gray-11102": "981915000568",
    "bambu-lab/pla-matte/nardo-gray-11104": "956968690774",
    "bambu-lab/pla-matte/scarlet-red-11200": "981915000568",
    "bambu-lab/pla-matte/dark-red-11202": "981915000568",
    "bambu-lab/pla-matte/marine-blue-11600": "982941879558",
    "bambu-lab/pla-matte/ice-blue-11601": "981915000568",
    "bambu-lab/pla-matte/dark-blue-11602": "937521722746",
    "bambu-lab/pla-matte/sky-blue-11603": "850209947277",
}
_PLA_BASIC_STORE = "https://jp.store.bambulab.com/products/pla-basic-filament"
_PLA_MATTE_STORE = "https://jp.store.bambulab.com/products/pla-matte-filament"


def test_bambu_pdd_batch1_goods_promote_to_primary(repo_root: Path) -> None:
    catalog = json.loads(
        (repo_root / "data/build/filament-catalog.json").read_text(encoding="utf-8")
    )
    web = json.loads((repo_root / "web/public/web-catalog.json").read_text(encoding="utf-8"))
    by_id = {entry["id"]: entry for entry in catalog["entries"]}
    web_by_id = {entry["id"]: entry for entry in web["entries"]}
    assert len(BAMBU_PDD_BATCH1) == 30
    for color_id, goods_id in BAMBU_PDD_BATCH1.items():
        url = f"https://mobile.pinduoduo.com/goods.html?goods_id={goods_id}"
        assert is_pdd_goods_url(url) is True
        assert "search_result.html" not in url
        entry = by_id[color_id]
        store = _PLA_MATTE_STORE if "/pla-matte/" in color_id else _PLA_BASIC_STORE
        assert entry["offers"][0] == {
            "channel": "Bambu Lab 日本官方商城",
            "url": store,
            "price_text": "¥2,400起 JPY",
        }
        assert entry["offers"][1] == {"channel": "拼多多", "url": url, "price_text": ""}
        primary, alt = purchase_links(entry)
        assert primary == url
        assert alt == store
        web_entry = web_by_id[color_id]
        assert web_entry["url"] == primary
        assert web_entry["alt_url"] == alt
        assert web_entry["price"] is None


# Collected 2026-11-09. Shared goods_id values are multi-SKU listings, kept as-is.
OTHER_PDD_BATCH2: dict[str, str] = {
    "cailab/matte-pla/black-mt419": "1022763383907",
    "cailab/matte-pla/army-green-mt2407": "979958260123",
    "cailab/matte-pla/orange-mt4012": "1022763383907",
    "cailab/matte-pla/beige-mt4030": "1022763383907",
    "cailab/matte-pla/ivory-mt9003": "979958260123",
    "cailab/matte-pla/lavender-mt2645": "988153320187",
    "cailab/pla-plus/black-ac419": "1014245843334",
    "cailab/pla-plus/white-ac9003": "988125819049",
    "cailab/pla-plus/gray-ac11": "690492320303",
    "cailab/pla-plus/light-gray-ac421": "988125819049",
    "esun/pla-basic/black": "809320909551",
    "esun/pla-basic/bone-white": "1021996966685",
    "esun/pla-basic/white": "1021996966685",
    "esun/pla-basic/grey": "992151643295",
    "esun/pla-basic/light-grey": "809320909551",
    "esun/pla-basic/red": "1008369918083",
    "esun/pla-basic/blue": "992151480844",
    "esun/pla-basic/dark-blue": "413409947777",
    "polymaker/panchroma-basic-pla/black": "711862832098",
    "polymaker/polylite-pla/black": "466104937652",
    "polymaker/panchroma-basic-pla/white": "1025925048307",
    "polymaker/polylite-pla/white": "979589316143",
    "polymaker/panchroma-basic-pla/dark-grey": "987668775194",
    "polymaker/panchroma-basic-pla/grey": "568967946166",
    "anycubic/pla-basic/black": "892043402692",
    "anycubic/pla-basic/white": "1006640350626",
    "anycubic/pla-basic/grey": "997622109775",
    "anycubic/pla-basic/light-grey": "1006640350626",
    "anycubic/pla-basic/red": "892043402692",
    "anycubic/pla-basic/blue": "997622109775",
    "sunlu/matte-pla/black": "923179436917",
    "sunlu/matte-pla/white": "923179436917",
    "sunlu/matte-pla/grey": "923179436917",
    "sunlu/matte-pla/red": "923179436917",
    "sunlu/matte-pla/blue": "923179436917",
    "sunlu/matte-pla/light-blue": "975593755299",
}
_CAILAB_MATTE = (
    "CaiLab 海外官网",
    "https://www.cailab3d.com/products/matte-pla-filament-1-75mm-1kg-spool",
    "US$17.99",
)
_CAILAB_PLUS = (
    "CaiLab 海外官网",
    "https://www.cailab3d.com/products/pla-plus-filament-pla-bio-1-75mm-1kg-spool",
    "US$17.99",
)
_ESUN_BASIC = (
    "eSUN 官网商城（色块为店铺示意色）",
    "https://www.esun3d.com/pla-basic-product",
    "US$13.99",
)
_PANCHROMA = (
    "Polymaker 美国官网",
    "https://us.polymaker.com/products/panchroma-pla",
    "US$17.99",
)
_POLYLITE = (
    "Polymaker 美国官网",
    "https://us.polymaker.com/products/polylite-pla",
    "US$19.99",
)
_ANYCUBIC_BASIC = (
    "Anycubic 官方商城",
    "https://store.anycubic.com/products/pla-filament",
    "US$17.99",
)
_SUNLU_MATTE = (
    "SUNLU 官网商城",
    "https://store.sunlu.com/products/over-6kg-bulk-sale-pla-matte-filament-neatly-wound-filament",
    "US$10.99起",
)


def _other_batch2_store(color_id: str) -> tuple[str, str, str]:
    if color_id.startswith("cailab/matte-pla/"):
        return _CAILAB_MATTE
    if color_id.startswith("cailab/pla-plus/"):
        return _CAILAB_PLUS
    if color_id.startswith("esun/pla-basic/"):
        return _ESUN_BASIC
    if color_id.startswith("polymaker/panchroma-basic-pla/"):
        return _PANCHROMA
    if color_id.startswith("polymaker/polylite-pla/"):
        return _POLYLITE
    if color_id.startswith("anycubic/pla-basic/"):
        return _ANYCUBIC_BASIC
    if color_id.startswith("sunlu/matte-pla/"):
        return _SUNLU_MATTE
    raise AssertionError(color_id)


def test_other_pdd_batch2_goods_promote_to_primary(repo_root: Path) -> None:
    catalog = json.loads(
        (repo_root / "data/build/filament-catalog.json").read_text(encoding="utf-8")
    )
    web = json.loads((repo_root / "web/public/web-catalog.json").read_text(encoding="utf-8"))
    by_id = {entry["id"]: entry for entry in catalog["entries"]}
    web_by_id = {entry["id"]: entry for entry in web["entries"]}
    assert len(OTHER_PDD_BATCH2) == 36
    assert len(set(OTHER_PDD_BATCH2.values())) == 23
    for color_id, goods_id in OTHER_PDD_BATCH2.items():
        url = f"https://mobile.pinduoduo.com/goods.html?goods_id={goods_id}"
        assert is_pdd_goods_url(url) is True
        assert "search_result.html" not in url
        channel, store, price = _other_batch2_store(color_id)
        entry = by_id[color_id]
        assert entry["offers"][0] == {"channel": channel, "url": store, "price_text": price}
        assert entry["offers"][1] == {"channel": "拼多多", "url": url, "price_text": ""}
        primary, alt = purchase_links(entry)
        assert primary == url
        assert alt == store
        web_entry = web_by_id[color_id]
        assert web_entry["url"] == primary
        assert web_entry["alt_url"] == alt
        assert web_entry["price"] is None
