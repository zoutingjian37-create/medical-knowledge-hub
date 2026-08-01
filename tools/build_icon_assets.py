"""Build deterministic Windows icon assets from the product design tokens."""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
PNG_DIR = ASSETS / "icon-png"
SIZES = (16, 24, 32, 48, 64, 128, 256)
SCALE = 8

BACKGROUND = "#F9FBFB"
LINE = "#DCE3E6"
INK = "#17233A"
ACCENT = "#087E78"


def scaled_point(x: int, y: int) -> tuple[int, int]:
    return x * SCALE, y * SCALE


def scaled_box(left: int, top: int, right: int, bottom: int) -> tuple[int, ...]:
    return tuple(value * SCALE for value in (left, top, right, bottom))


def build_master() -> Image.Image:
    image = Image.new("RGBA", (256 * SCALE, 256 * SCALE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        scaled_box(16, 16, 240, 240),
        radius=52 * SCALE,
        fill=BACKGROUND,
        outline=LINE,
        width=4 * SCALE,
    )

    document = [
        scaled_point(72, 54),
        scaled_point(145, 54),
        scaled_point(174, 83),
        scaled_point(174, 158),
        scaled_point(72, 158),
        scaled_point(72, 54),
    ]
    draw.line(document, fill=INK, width=13 * SCALE, joint="curve")
    draw.line(
        [scaled_point(145, 55), scaled_point(145, 85), scaled_point(173, 85)],
        fill=INK,
        width=13 * SCALE,
        joint="curve",
    )
    draw.line(
        [scaled_point(94, 105), scaled_point(142, 105)],
        fill=INK,
        width=11 * SCALE,
    )
    draw.line(
        [scaled_point(94, 132), scaled_point(133, 132)],
        fill=INK,
        width=11 * SCALE,
    )

    draw.rounded_rectangle(
        scaled_box(107, 143, 197, 214),
        radius=16 * SCALE,
        fill=ACCENT,
    )
    draw.line(
        [scaled_point(152, 158), scaled_point(152, 189)],
        fill=BACKGROUND,
        width=10 * SCALE,
    )
    draw.line(
        [scaled_point(139, 176), scaled_point(152, 189), scaled_point(165, 176)],
        fill=BACKGROUND,
        width=10 * SCALE,
        joint="curve",
    )
    draw.line(
        [scaled_point(130, 200), scaled_point(174, 200)],
        fill=BACKGROUND,
        width=10 * SCALE,
    )
    return image


def main() -> None:
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    master = build_master()
    images = {}
    for size in SIZES:
        rendered = master.resize((size, size), Image.Resampling.LANCZOS)
        images[size] = rendered
        rendered.save(PNG_DIR / f"medical-knowledge-hub-{size}.png", optimize=True)

    images[256].save(ASSETS / "medical-knowledge-hub.png", optimize=True)
    images[256].save(
        ASSETS / "medical-knowledge-hub.ico",
        format="ICO",
        sizes=[(size, size) for size in SIZES if size != 24],
    )


if __name__ == "__main__":
    main()
