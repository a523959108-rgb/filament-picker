import pytest

from filament_picker.errors import (
    ERROR_MESSAGES,
    FPError,
    ImageMissingError,
    ImageTooSmallError,
    ImageUnreadableError,
    InternalError,
    InvalidRequestError,
    NoForegroundError,
    NoMatchError,
)

ERROR_CASES = [
    ("INVALID_REQUEST", "请求格式不对，请重新发一次图片。"),
    ("IMAGE_MISSING", "没找到这张图片，可能已过期，请重新发送。"),
    ("IMAGE_UNREADABLE", "这张图片打不开，请换成 PNG 或 JPG 再发。"),
    ("IMAGE_TOO_SMALL", "图片太小了，请发原图。"),
    ("NO_FOREGROUND", "没能从图里分出主体颜色，请换一张背景更干净的图。"),
    ("NO_MATCH", "在当前条件下没找到足够接近的耗材，可以放宽品牌/材料，或去掉「只要官方」。"),
    ("CATALOG_ERROR", "色卡数据加载失败，请稍后再试。"),
    ("INTERNAL", "处理时出错了，请稍后再试。"),
]


def test_error_messages_order_and_size():
    assert len(ERROR_MESSAGES) == 8
    assert list(ERROR_MESSAGES) == [code for code, _ in ERROR_CASES]


@pytest.mark.parametrize(("code", "message"), ERROR_CASES)
def test_error_messages_are_exact(code, message):
    assert ERROR_MESSAGES[code] == message


@pytest.mark.parametrize(
    "error_type",
    [
        InvalidRequestError,
        ImageMissingError,
        ImageUnreadableError,
        ImageTooSmallError,
        NoForegroundError,
        NoMatchError,
        InternalError,
    ],
)
def test_error_subclasses(error_type):
    assert issubclass(error_type, FPError)


def test_image_too_small_error_code_and_message():
    error = ImageTooSmallError()
    assert error.code == "IMAGE_TOO_SMALL"
    assert error.message_zh == "图片太小了，请发原图。"


def test_catalog_error_is_message_only():
    assert "CATALOG_ERROR" in ERROR_MESSAGES
    assert not hasattr(
        __import__("filament_picker.errors", fromlist=["CatalogError"]), "CatalogError"
    )
