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

    left_page = [
        scaled_point(42, 76), scaled_point(65, 70), scaled_point(91, 73),
        scaled_point(110, 80), scaled_point(128, 89), scaled_point(128, 198),
        scaled_point(107, 188), scaled_point(84, 182), scaled_point(62, 182),
        scaled_point(42, 186), scaled_point(42, 76),
    ]
    right_page = [
        scaled_point(214, 76), scaled_point(191, 70), scaled_point(165, 73),
        scaled_point(146, 80), scaled_point(128, 89), scaled_point(128, 198),
        scaled_point(149, 188), scaled_point(172, 182), scaled_point(194, 182),
        scaled_point(214, 186), scaled_point(214, 76),
    ]
    draw.polygon(left_page, fill="#FFFFFF")
    draw.polygon(right_page, fill="#FFFFFF")
    draw.line(left_page, fill=INK, width=11 * SCALE, joint="curve")
    draw.line(right_page, fill=INK, width=11 * SCALE, joint="curve")
    draw.line(
        [scaled_point(128, 89), scaled_point(128, 198)],
        fill=INK,
        width=11 * SCALE,
    )
    for start, end in (
        ((65, 119), (109, 126)), ((65, 146), (109, 153)),
        ((191, 119), (147, 126)), ((191, 146), (147, 153)),
    ):
        draw.line(
            [scaled_point(*start), scaled_point(*end)],
            fill=INK,
            width=8 * SCALE,
        )

    draw.ellipse(
        scaled_box(91, 45, 165, 119),
        fill=BACKGROUND,
    )
    draw.ellipse(
        scaled_box(95, 49, 161, 115),
        fill=ACCENT,
    )
    draw.line(
        [scaled_point(128, 63), scaled_point(128, 101)],
        fill="#FFFFFF",
        width=11 * SCALE,
    )
    draw.line(
        [scaled_point(109, 82), scaled_point(147, 82)],
        fill="#FFFFFF",
        width=11 * SCALE,
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
    icon_sizes = [(size, size) for size in SIZES if size != 24]
    for filename in (
        "medical-knowledge-hub.ico",
        "medical-knowledge-hub-20260802.ico",
    ):
        images[256].save(
            ASSETS / filename,
            format="ICO",
            sizes=icon_sizes,
        )


if __name__ == "__main__":
    main()
