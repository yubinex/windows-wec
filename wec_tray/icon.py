"""Tray icon rendering: a generic countdown badge (not the WEC logo)."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

SIZE = 64
# state -> (background, text)
COLORS = {
    "live": ((225, 6, 0, 255), (255, 255, 255, 255)),
    "soon": ((224, 184, 79, 255), (20, 20, 20, 255)),
    "idle": ((32, 34, 40, 255), (255, 255, 255, 255)),
    "none": ((32, 34, 40, 255), (150, 150, 150, 255)),
}


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("arialbd.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_icon(text: str, state: str) -> Image.Image:
    """Draw `text` (e.g. "12d", "LIVE") as large as fits on a coloured badge."""
    bg, fg = COLORS.get(state, COLORS["idle"])
    text = text or "WEC"
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=12, fill=bg)
    # Tray icons are shown at 16-24 px, so use the largest font that fits.
    for size in range(44, 9, -2):
        font = _font(size)
        box = draw.textbbox((0, 0), text, font=font)
        w, h = box[2] - box[0], box[3] - box[1]
        if w <= SIZE - 6 and h <= SIZE - 10:
            break
    draw.text(((SIZE - w) / 2 - box[0], (SIZE - h) / 2 - box[1]), text, font=font, fill=fg)
    return img
