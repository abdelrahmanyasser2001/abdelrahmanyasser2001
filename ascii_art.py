#!/usr/bin/env python3
"""
ascii_art.py
------------
Converts an image (e.g. a GitHub avatar) into colored ASCII art and
emits it as ready-to-embed SVG <text> rows, neofetch-card style.

Usage as a library:
    from ascii_art import image_to_svg_rows
    rows_svg = image_to_svg_rows("avatar.png", cols=48, x=20, y=30, line_height=11)
    # rows_svg is a string of <text>...</text> elements you can drop into a template

Usage standalone (writes a preview SVG you can open directly):
    python3 ascii_art.py avatar.png preview.svg
"""

import sys
from xml.sax.saxutils import escape
from PIL import Image

# Darkest-to-lightest ramp (dense chars = dark/detail, sparse = light/background)
RAMP = "@%#*+=-:. "


def _char_for_brightness(brightness):
    """brightness: 0 (black) - 255 (white)"""
    idx = int((brightness / 255) * (len(RAMP) - 1))
    return RAMP[idx]


def image_to_svg_rows(image_path, cols=48, x=20, y=30, line_height=11,
                       char_width=6.2, font_size=10, min_brightness_floor=40):
    """
    Reads image_path, downsamples to a `cols`-wide character grid (rows
    computed from aspect ratio, correcting for the fact that monospace
    characters are taller than they are wide), and returns a string of
    SVG <text> elements — one per row, with <tspan> runs grouped by color
    to keep the SVG small.
    """
    img = Image.open(image_path).convert("RGB")
    w, h = img.size

    # monospace chars are roughly 1.9x taller than wide -> compress rows
    char_aspect = 1.9
    rows = max(1, round(cols * (h / w) / char_aspect))

    small = img.resize((cols, rows), Image.LANCZOS)
    pixels = small.load()

    svg_rows = []
    for row in range(rows):
        # group consecutive columns that share (approximately) the same
        # color into one <tspan> to keep element count reasonable
        tspans = []
        cur_color = None
        cur_text = ""

        for col in range(cols):
            r, g, b = pixels[col, row]
            brightness = 0.299 * r + 0.587 * g + 0.114 * b
            # floor brightness so background never fully disappears into black
            brightness = max(brightness, min_brightness_floor if (r, g, b) != (0, 0, 0) else 0)
            ch = _char_for_brightness(brightness)
            color = f"#{r:02x}{g:02x}{b:02x}"

            if color == cur_color:
                cur_text += ch
            else:
                if cur_text:
                    tspans.append((cur_color, cur_text))
                cur_color = color
                cur_text = ch

        if cur_text:
            tspans.append((cur_color, cur_text))

        row_y = y + row * line_height
        tspan_str = "".join(
            f'<tspan fill="{color}">{escape(text)}</tspan>'
            for color, text in tspans
        )
        svg_rows.append(f'<text x="{x}" y="{row_y}" xml:space="preserve">{tspan_str}</text>')

    return "\n".join(svg_rows), rows


def art_block_height(rows, line_height=11, y_start=30):
    return y_start + rows * line_height


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python3 ascii_art.py <input_image> <output_svg>")
        raise SystemExit(1)

    src, out = sys.argv[1], sys.argv[2]
    rows_svg, n_rows = image_to_svg_rows(src, cols=48)
    height = art_block_height(n_rows) + 20
    svg = f'''<svg width="360" height="{height}" viewBox="0 0 360 {height}" xmlns="http://www.w3.org/2000/svg" font-family="Consolas,monospace" font-size="10">
<rect width="360" height="{height}" fill="#0d1117" />
{rows_svg}
</svg>'''
    with open(out, "w") as f:
        f.write(svg)
    print(f"wrote {out} ({n_rows} rows)")
