from pathlib import Path

from PIL import Image, ImageDraw


def quadrants(path: Path, size: int = 400) -> Path:
    image = Image.new("RGB", (size, size), "#000000")
    draw = ImageDraw.Draw(image)
    half = size // 2
    draw.rectangle((half, 0, size - 1, half - 1), fill="#FFFFFF")
    draw.rectangle((0, half, half - 1, size - 1), fill="#00AE42")
    draw.rectangle((half, half, size - 1, size - 1), fill="#C8102E")
    image.save(path, format="PNG")
    return path


def square_on_white(path: Path, fg: str = "#00AE42", size: int = 200, inner: int = 120) -> Path:
    image = Image.new("RGB", (size, size), "#FFFFFF")
    start = (size - inner) // 2
    ImageDraw.Draw(image).rectangle((start, start, start + inner - 1, start + inner - 1), fill=fg)
    image.save(path, format="PNG")
    return path


def two_tone(
    path: Path,
    left: str = "#C8102E",
    right: str = "#00AE42",
    size: int = 200,
    inner: int = 120,
    split: float = 0.6,
) -> Path:
    image = Image.new("RGB", (size, size), "#FFFFFF")
    start = (size - inner) // 2
    split_columns = round(inner * split)
    draw = ImageDraw.Draw(image)
    draw.rectangle((start, start, start + split_columns - 1, start + inner - 1), fill=left)
    draw.rectangle((start + split_columns, start, start + inner - 1, start + inner - 1), fill=right)
    image.save(path, format="PNG")
    return path


def tiny(path: Path, size: int = 32) -> Path:
    Image.new("RGB", (size, size), "#00AE42").save(path, format="PNG")
    return path


def blank_white(path: Path, size: int = 200) -> Path:
    Image.new("RGB", (size, size), "#FFFFFF").save(path, format="PNG")
    return path


def rgba_square(path: Path, size: int = 200) -> Path:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    start = (size - 120) // 2
    ImageDraw.Draw(image).rectangle((start, start, start + 119, start + 119), fill="#00AE42FF")
    image.save(path, format="PNG")
    return path
