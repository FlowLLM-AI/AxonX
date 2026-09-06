"""Generate matching SVG and transparent PNG versions of the FlowLLM f logo."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

VIEWBOX_SIZE = 1024
PNG_SIZE = 2048
RENDER_SCALE = 4
STROKE_WIDTH = 82

STOPS = (
    (0.00, (0, 220, 247)),
    (0.28, (0, 157, 248)),
    (0.55, (13, 94, 247)),
    (0.78, (57, 58, 235)),
    (1.00, (105, 35, 226)),
)

# One uninterrupted path: crossbar -> lower loop -> stem -> upper hook.
F_CURVES = (
    ((742, 446), (625, 440), (512, 438), (420, 448)),
    ((420, 448), (310, 456), (215, 492), (198, 574)),
    ((198, 574), (178, 674), (231, 778), (314, 802)),
    ((314, 802), (385, 823), (430, 772), (447, 694)),
    ((447, 694), (471, 580), (454, 499), (430, 448)),
    ((430, 448), (409, 391), (406, 299), (431, 222)),
    ((431, 222), (460, 134), (538, 99), (626, 111)),
)


def interpolate_color(position: float) -> tuple[int, int, int]:
    """Interpolate the configured gradient stops at ``position``."""
    for (left_at, left), (right_at, right) in zip(STOPS, STOPS[1:]):
        if position <= right_at:
            amount = max(
                0.0,
                min(1.0, (position - left_at) / (right_at - left_at)),
            )
            return tuple(round(a + (b - a) * amount) for a, b in zip(left, right))
    return STOPS[-1][1]


def sample_curve(
    curve: tuple[tuple[int, int], ...],
    scale: int,
    steps: int = 120,
) -> list[tuple[int, int]]:
    """Sample a cubic Bézier curve into scaled raster coordinates."""
    start, control_1, control_2, end = curve
    points = []
    for index in range(steps + 1):
        t = index / steps
        inverse = 1.0 - t
        x = (
            inverse**3 * start[0]
            + 3 * inverse**2 * t * control_1[0]
            + 3 * inverse * t**2 * control_2[0]
            + t**3 * end[0]
        )
        y = (
            inverse**3 * start[1]
            + 3 * inverse**2 * t * control_1[1]
            + 3 * inverse * t**2 * control_2[1]
            + t**3 * end[1]
        )
        points.append((round(x * scale), round(y * scale)))
    return points


def create_mask() -> Image.Image:
    """Rasterize the continuous logo stroke into an alpha mask."""
    render_size = VIEWBOX_SIZE * RENDER_SCALE
    mask = Image.new("L", (render_size, render_size), 0)
    draw = ImageDraw.Draw(mask)

    points = []
    for curve in F_CURVES:
        sampled = sample_curve(curve, RENDER_SCALE)
        points.extend(sampled if not points else sampled[1:])

    width = STROKE_WIDTH * RENDER_SCALE
    radius = width // 2
    draw.line(points, fill=255, width=width, joint="curve")
    for x, y in (points[0], points[-1]):
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=255,
        )
    return mask


def create_gradient() -> Image.Image:
    """Create the cyan-to-violet gradient used by the PNG logo."""
    small_size = 512
    gradient = Image.new("RGB", (small_size, small_size))
    pixels = gradient.load()
    for y in range(small_size):
        for x in range(small_size):
            viewbox_x = x / (small_size - 1) * VIEWBOX_SIZE
            viewbox_y = y / (small_size - 1) * VIEWBOX_SIZE
            horizontal = (viewbox_x - 145) / 775
            vertical = (viewbox_y - 125) / 765
            position = 0.30 * horizontal + 0.70 * vertical
            pixels[x, y] = interpolate_color(position)
    render_size = VIEWBOX_SIZE * RENDER_SCALE
    return gradient.resize((render_size, render_size), Image.Resampling.BICUBIC)


def write_png(path: Path) -> None:
    """Render and write the transparent high-resolution PNG logo."""
    logo = create_gradient().convert("RGBA")
    logo.putalpha(create_mask())
    logo = logo.resize((PNG_SIZE, PNG_SIZE), Image.Resampling.LANCZOS)
    path.parent.mkdir(parents=True, exist_ok=True)
    logo.save(path, optimize=True)


def svg_path() -> str:
    """Return SVG path commands for the continuous logo stroke."""
    start = F_CURVES[0][0]
    commands = [f"M {start[0]} {start[1]}"]
    for _, control_1, control_2, end in F_CURVES:
        commands.append(
            f"C {control_1[0]} {control_1[1]}, " f"{control_2[0]} {control_2[1]}, {end[0]} {end[1]}",
        )
    return " ".join(commands)


def write_svg(path: Path) -> None:
    """Write the accessible vector representation of the logo."""
    stops = "\n".join(
        f'      <stop offset="{offset:.2f}" ' f'stop-color="#{red:02X}{green:02X}{blue:02X}"/>'
        for offset, (red, green, blue) in STOPS
    )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg"
     width="2048" height="2048" viewBox="0 0 1024 1024"
     role="img" aria-labelledby="title description">
  <title id="title">FlowLLM f logo</title>
  <desc id="description">A continuous one-stroke mathematical f.</desc>
  <defs>
    <linearGradient id="flow-gradient" gradientUnits="userSpaceOnUse"
                    x1="350" y1="70" x2="560" y2="930">
{stops}
    </linearGradient>
  </defs>
  <g fill="none" stroke="url(#flow-gradient)"
     stroke-width="{STROKE_WIDTH}" stroke-linecap="round"
     stroke-linejoin="round">
    <path d="{svg_path()}"/>
  </g>
</svg>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")


def main() -> None:
    """Generate both logo formats in the requested output directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/figures"),
    )
    args = parser.parse_args()

    svg_pathname = args.output_dir / "flowllm-f-logo.svg"
    png_pathname = args.output_dir / "flowllm-f-logo.png"
    write_svg(svg_pathname)
    write_png(png_pathname)
    print(f"Wrote {svg_pathname}")
    print(f"Wrote {png_pathname} ({PNG_SIZE}x{PNG_SIZE}, transparent RGBA)")


if __name__ == "__main__":
    main()
