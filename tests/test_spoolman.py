import json
import urllib.error
import urllib.request
from email.message import Message

import pytest

from filament_picker.spoolman import (
    COLOR_ID_EXTRA_KEY,
    SpoolmanClient,
    SpoolmanError,
    SpoolmanSettings,
    annotate_recommendations,
    spool_list_url,
    spoolman_settings,
    stock_hint,
    vendor_brand_slug,
)

_ENV = ("FP_SPOOLMAN_ENABLED", "FP_SPOOLMAN_BASE_URL", "FP_SPOOLMAN_TIMEOUT_S")
_COLOR = "bambu-lab/pla-basic/black-10101"


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)


def test_settings_default_off(clean_env: None) -> None:
    settings = spoolman_settings()
    assert settings == SpoolmanSettings(enabled=False, base_url=None, timeout_s=3.0)


def test_settings_enabled_requires_base_url(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FP_SPOOLMAN_ENABLED", "1")
    with pytest.raises(ValueError, match="FP_SPOOLMAN_BASE_URL"):
        spoolman_settings()


def test_settings_reject_credentials(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_SPOOLMAN_ENABLED", "yes")
    monkeypatch.setenv("FP_SPOOLMAN_BASE_URL", "http://admin:secret@spoolman.local:7912")
    with pytest.raises(ValueError, match="credentials") as exc_info:
        spoolman_settings()
    assert "secret" not in str(exc_info.value)


def test_settings_reject_non_http_and_query(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FP_SPOOLMAN_BASE_URL", "file:///tmp/spoolman")
    with pytest.raises(ValueError, match="http"):
        spoolman_settings()
    monkeypatch.setenv("FP_SPOOLMAN_BASE_URL", "http://spoolman.local:7912/?token=abc")
    with pytest.raises(ValueError, match="query"):
        spoolman_settings()


def test_settings_normalize_base_url(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_SPOOLMAN_ENABLED", "TRUE")
    monkeypatch.setenv("FP_SPOOLMAN_BASE_URL", "http://spoolman.local:7912/spoolman/")
    monkeypatch.setenv("FP_SPOOLMAN_TIMEOUT_S", "2.5")
    settings = spoolman_settings()
    assert settings.enabled is True
    assert settings.base_url == "http://spoolman.local:7912/spoolman"
    assert settings.timeout_s == 2.5
    assert spool_list_url(settings.base_url) == "http://spoolman.local:7912/spoolman/api/v1/spool"


def test_settings_reject_bad_flag_and_timeout(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FP_SPOOLMAN_ENABLED", "maybe")
    with pytest.raises(ValueError, match="FP_SPOOLMAN_ENABLED"):
        spoolman_settings()
    monkeypatch.setenv("FP_SPOOLMAN_ENABLED", "0")
    monkeypatch.setenv("FP_SPOOLMAN_TIMEOUT_S", "0")
    with pytest.raises(ValueError, match="FP_SPOOLMAN_TIMEOUT_S"):
        spoolman_settings()


def test_vendor_brand_slug() -> None:
    assert vendor_brand_slug("Bambu Lab") == "bambu-lab"
    assert vendor_brand_slug("拓竹") == "bambu-lab"
    assert vendor_brand_slug(" sunlu ") == "sunlu"
    assert vendor_brand_slug("三绿") == "sunlu"
    assert vendor_brand_slug("Not A Brand") is None
    assert vendor_brand_slug(None) is None


def _filament(**overrides: object) -> dict[str, object]:
    filament: dict[str, object] = {
        "id": 10,
        "vendor": {"name": "Bambu Lab"},
        "material": "PLA",
        "color_hex": "000000",
        "extra": {COLOR_ID_EXTRA_KEY: _COLOR},
    }
    filament.update(overrides)
    return filament


def _spool(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "id": 1,
        "archived": False,
        "remaining_weight": 800,
        "location": "柜A",
        "filament": _filament(),
    }
    item.update(overrides)
    return item


def _entry(
    color_id: str = _COLOR,
    *,
    hex_color: str | None = "#000000",
    material: str = "PLA",
    brand_slug: str = "bambu-lab",
) -> dict[str, object]:
    return {
        "id": color_id,
        "brand_slug": brand_slug,
        "material": material,
        "hex": [] if hex_color is None else [hex_color],
    }


def test_list_spools_disabled_does_not_call_opener() -> None:
    def opener(url: str, timeout_s: float) -> bytes:
        raise AssertionError((url, timeout_s))

    client = SpoolmanClient(SpoolmanSettings(False, "http://spoolman.local:7912", 3.0), opener)
    assert client.list_spools() == ()


def test_list_spools_parses_mocked_payload() -> None:
    encoded = json.dumps(_COLOR)
    payload = [
        _spool(),
        _spool(
            id=2,
            archived=True,
            remaining_weight=500,
            location="",
            filament=_filament(extra={COLOR_ID_EXTRA_KEY: encoded}),
        ),
        _spool(
            id=3,
            remaining_weight=None,
            filament=_filament(extra={}, external_id="PM70820", color_hex="ZZZZZZ"),
        ),
    ]
    seen: list[tuple[str, float]] = []

    def opener(url: str, timeout_s: float) -> bytes:
        seen.append((url, timeout_s))
        return json.dumps(payload).encode()

    client = SpoolmanClient(SpoolmanSettings(True, "http://spoolman.local:7912", 1.5), opener)
    spools = client.list_spools()
    assert seen == [("http://spoolman.local:7912/api/v1/spool", 1.5)]
    assert [spool.spool_id for spool in spools] == [1, 2, 3]
    assert spools[0].color_id == _COLOR
    assert spools[0].in_stock is True
    assert spools[0].remaining_weight_g == 800.0
    assert spools[0].location == "柜A"
    assert spools[1].color_id == _COLOR
    assert spools[1].in_stock is False
    assert spools[1].location is None
    assert spools[2].color_id is None
    assert spools[2].color_hex is None
    assert spools[2].in_stock is False


def test_extra_color_id_wins_over_external_id() -> None:
    other = "bambu-lab/pla-matte/black-11101"
    payload = [_spool(filament=_filament(extra={COLOR_ID_EXTRA_KEY: _COLOR}, external_id=other))]

    def opener(url: str, timeout_s: float) -> bytes:
        return json.dumps(payload).encode()

    spool = SpoolmanClient(
        SpoolmanSettings(True, "http://spoolman.local", 3.0), opener
    ).list_spools()[0]
    assert spool.color_id == _COLOR


def test_external_id_used_when_it_is_a_color_id() -> None:
    payload = [_spool(filament=_filament(extra={}, external_id=_COLOR))]

    def opener(url: str, timeout_s: float) -> bytes:
        return json.dumps(payload).encode()

    spool = SpoolmanClient(
        SpoolmanSettings(True, "http://spoolman.local", 3.0), opener
    ).list_spools()[0]
    assert spool.color_id == _COLOR


def test_list_spools_rejects_bad_json_and_shape() -> None:
    client = SpoolmanClient(
        SpoolmanSettings(True, "http://spoolman.local", 3.0),
        lambda url, timeout_s: b"{",
    )
    with pytest.raises(SpoolmanError, match="JSON"):
        client.list_spools()
    client = SpoolmanClient(
        SpoolmanSettings(True, "http://spoolman.local", 3.0),
        lambda url, timeout_s: b'{"id": 1}',
    )
    with pytest.raises(SpoolmanError, match="array"):
        client.list_spools()


def test_enabled_without_base_url_does_not_call_opener() -> None:
    def opener(url: str, timeout_s: float) -> bytes:
        raise AssertionError((url, timeout_s))

    client = SpoolmanClient(SpoolmanSettings(True, None, 3.0), opener)
    with pytest.raises(SpoolmanError, match="base URL"):
        client.list_spools()


def test_http_errors_do_not_open_a_real_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_http(request: urllib.request.Request, timeout: float) -> object:
        assert request.get_method() == "GET"
        assert request.full_url == "http://spoolman.local:7912/api/v1/spool"
        assert timeout == 3.0
        raise urllib.error.HTTPError(request.full_url, 503, "unavailable", Message(), None)

    monkeypatch.setattr(urllib.request, "urlopen", fail_http)
    client = SpoolmanClient(SpoolmanSettings(True, "http://spoolman.local:7912", 3.0))
    with pytest.raises(SpoolmanError, match="503"):
        client.list_spools()

    def fail_url(request: urllib.request.Request, timeout: float) -> object:
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", fail_url)
    with pytest.raises(SpoolmanError, match="failed"):
        client.list_spools()


def test_stock_hint_prefers_exact_color_id_over_fuzzy() -> None:
    from filament_picker.spoolman import parse_spool

    exact = parse_spool(_spool(id=7, remaining_weight=100, location="柜A"))
    smaller = parse_spool(_spool(id=6, remaining_weight=50, location="柜A"))
    fuzzy = parse_spool(
        _spool(
            id=8,
            remaining_weight=900,
            filament=_filament(
                extra={},
                external_id="bambu-lab/pla-matte/black-11101",
                color_hex="000000",
            ),
        )
    )
    hint = stock_hint(_entry(), (fuzzy, smaller, exact))
    assert hint.match == "color_id"
    assert hint.in_stock is True
    assert hint.nearby_in_stock is False
    assert hint.spool_id == 7
    assert hint.remaining_weight_g == 100.0


def test_exact_empty_spool_does_not_fall_through_to_nearby() -> None:
    from filament_picker.spoolman import parse_spool

    empty = parse_spool(_spool(id=4, remaining_weight=0))
    nearby = parse_spool(
        _spool(
            id=5,
            remaining_weight=700,
            filament=_filament(extra={}, external_id="bambu-lab/pla-matte/black-11101"),
        )
    )
    hint = stock_hint(_entry(), (empty, nearby))
    assert hint.match == "color_id"
    assert hint.in_stock is False
    assert hint.nearby_in_stock is False
    assert hint.spool_id == 4


def test_fuzzy_same_brand_material_and_color() -> None:
    from filament_picker.spoolman import parse_spool

    nearby = parse_spool(
        _spool(
            id=5,
            remaining_weight=700,
            location="柜B",
            filament=_filament(
                extra={},
                external_id="bambu-lab/pla-matte/black-11101",
                vendor={"name": "拓竹"},
                material="pla",
            ),
        )
    )
    hint = stock_hint(_entry(), (nearby,))
    assert hint.match == "brand_material_color"
    assert hint.in_stock is False
    assert hint.nearby_in_stock is True
    assert hint.spool_id == 5
    assert hint.location == "柜B"


def test_fuzzy_rejects_other_brand_material_distance_and_multi_hex() -> None:
    from filament_picker.spoolman import parse_spool

    other_brand = parse_spool(
        _spool(filament=_filament(extra={}, vendor={"name": "Polymaker"}, color_hex="000000"))
    )
    other_material = parse_spool(
        _spool(filament=_filament(extra={}, material="PETG", color_hex="000000"))
    )
    far_color = parse_spool(_spool(filament=_filament(extra={}, color_hex="FF0000")))
    same_black = parse_spool(_spool(filament=_filament(extra={}, color_hex="000000")))
    multi = _entry() | {"hex": ["#000000", "#FFFFFF"]}
    assert stock_hint(_entry(), (other_brand,)).match == "none"
    assert stock_hint(_entry(), (other_material,)).match == "none"
    assert stock_hint(_entry(), (far_color,)).match == "none"
    assert stock_hint(multi, (same_black,)).match == "none"


def test_multi_color_spool_does_not_fuzzy_match() -> None:
    from filament_picker.spoolman import parse_spool

    spool = parse_spool(
        _spool(
            filament=_filament(
                extra={},
                color_hex="000000",
                multi_color_hexes="000000,FFFFFF",
            )
        )
    )
    assert spool.color_hex is None
    assert stock_hint(_entry(), (spool,)).match == "none"


def test_annotate_recommendations_puts_in_stock_first_and_keeps_the_rest() -> None:
    from filament_picker.spoolman import parse_spool

    basic = _COLOR
    matte = "bambu-lab/pla-matte/black-11101"
    red = "bambu-lab/pla-basic/red-10200"
    matches = [
        {"id": basic, "delta_e": 1.0},
        {"id": matte, "delta_e": 4.0},
        {"id": red, "delta_e": 0.5},
    ]
    entries = {
        basic: _entry(basic),
        matte: _entry(matte),
        red: _entry(red, hex_color="#FF0000"),
    }
    spools = (
        parse_spool(
            _spool(id=1, remaining_weight=0, filament=_filament(extra={COLOR_ID_EXTRA_KEY: basic}))
        ),
        parse_spool(
            _spool(
                id=2, remaining_weight=600, filament=_filament(extra={COLOR_ID_EXTRA_KEY: matte})
            )
        ),
    )
    annotated = annotate_recommendations(matches, entries, spools)
    assert [item["id"] for item in annotated] == [matte, basic, red]
    assert annotated[0]["stock"]["in_stock"] is True
    assert annotated[0]["stock"]["match"] == "color_id"
    assert annotated[1]["stock"]["in_stock"] is False
    assert annotated[2]["stock"]["match"] == "none"
    assert "stock" not in matches[0]
    assert annotated[0]["delta_e"] == 4.0


def test_annotate_puts_nearby_stock_ahead_of_an_empty_exact_spool() -> None:
    from filament_picker.spoolman import parse_spool

    basic = _COLOR
    matte = "bambu-lab/pla-matte/black-11101"
    matches = [
        {"id": basic, "delta_e": 0.2},
        {"id": matte, "delta_e": 3.0},
    ]
    entries = {basic: _entry(basic), matte: _entry(matte)}
    spools = (
        parse_spool(
            _spool(id=1, remaining_weight=0, filament=_filament(extra={COLOR_ID_EXTRA_KEY: basic}))
        ),
        parse_spool(
            _spool(id=9, remaining_weight=400, filament=_filament(extra={}, color_hex="000000"))
        ),
    )
    annotated = annotate_recommendations(matches, entries, spools)
    assert [item["id"] for item in annotated] == [matte, basic]
    assert annotated[0]["stock"]["match"] == "brand_material_color"
    assert annotated[0]["stock"]["nearby_in_stock"] is True
    assert annotated[0]["stock"]["in_stock"] is False
    assert annotated[1]["stock"]["match"] == "color_id"
    assert annotated[1]["stock"]["in_stock"] is False
