from __future__ import annotations

from typing import ClassVar

ERROR_MESSAGES: dict[str, str] = {
    "INVALID_REQUEST": "请求格式不对，请重新发一次图片。",
    "IMAGE_MISSING": "没找到这张图片，可能已过期，请重新发送。",
    "IMAGE_UNREADABLE": "这张图片打不开，请换成 PNG 或 JPG 再发。",
    "IMAGE_TOO_SMALL": "图片太小了，请发原图。",
    "NO_FOREGROUND": "没能从图里分出主体颜色，请换一张背景更干净的图。",
    "NO_MATCH": "在当前条件下没找到足够接近的耗材，可以放宽品牌/材料，或去掉「只要官方」。",
    "CATALOG_ERROR": "色卡数据加载失败，请稍后再试。",
    "INTERNAL": "处理时出错了，请稍后再试。",
}


class FPError(Exception):
    code: ClassVar[str] = "INTERNAL"

    @property
    def message_zh(self) -> str:
        return ERROR_MESSAGES[self.code]


class InvalidRequestError(FPError):
    code = "INVALID_REQUEST"


class ImageMissingError(FPError):
    code = "IMAGE_MISSING"


class ImageUnreadableError(FPError):
    code = "IMAGE_UNREADABLE"


class ImageTooSmallError(FPError):
    code = "IMAGE_TOO_SMALL"


class NoForegroundError(FPError):
    code = "NO_FOREGROUND"


class NoMatchError(FPError):
    code = "NO_MATCH"


class InternalError(FPError):
    code = "INTERNAL"
