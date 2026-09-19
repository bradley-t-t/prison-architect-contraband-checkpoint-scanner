"""Builds the mod's Steam Workshop card, thumbnail.png, from its art.

Every mod in the set carries this same file, so every card has the same
layout: the mod's art on a dark blueprint ground, corner brackets, and a
title band along the bottom with the mod's name over the game's. Only the
art and the name differ.

The art is tools/card-art.png, a square picture of the mod's objects. A flat
background around it is cut away so the art sits on the card's own ground;
art that fills its square, a tile sample say, is kept whole and given a frame.

Usage: python card.py            reads the name from manifest.txt
"""

import os
import re

from PIL import Image, ImageDraw, ImageFont

SIZE = 512
GROUND = (16, 18, 22, 255)
GRID = (23, 27, 33, 255)
BAND = (10, 11, 14, 255)
ACCENT = (240, 160, 40, 255)
TITLE = (242, 242, 238, 255)
SUBTITLE = (140, 146, 156, 255)
GRID_STEP = 32
BAND_TOP = 400
ART_BOX = 344                   # the art is fitted inside a square this big
ART_CENTRE = (SIZE // 2, 200)
# A bold face both Windows and macOS ship, tried in order.
FACES = ("C:/Windows/Fonts/arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
         "/Library/Fonts/Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
TITLE_SIZE = 46
SUBTITLE_SIZE = 19
BRACKET = 44                    # length of a corner bracket's arm
BRACKET_INSET = 18
LINE = 4
GAME = "Prison Architect Mod"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cut_out(art):
    """The art with a flat background made clear, and whether it had one."""
    art = art.convert("RGBA")
    w, h = art.size
    corners = {art.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))}
    if len(corners) != 1:
        return art, False
    ground = corners.pop()
    if ground[3] == 0:
        return art, True
    px = art.load()
    seen = set()
    stack = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    while stack:
        x, y = stack.pop()
        if (x, y) in seen or not (0 <= x < w and 0 <= y < h) or px[x, y] != ground:
            continue
        seen.add((x, y))
        px[x, y] = (0, 0, 0, 0)
        stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    return art, True


def fitted(art):
    """The art trimmed to what is drawn and scaled to the art box. It is
    scaled in quarter steps, which keep the blocks of pixel art drawn four to
    a block the same size as each other."""
    box = art.getbbox()
    if box:
        art = art.crop(box)
    w, h = art.size
    scale = ART_BOX / max(w, h)
    if scale >= 1:
        scale = int(scale * 4) / 4
    return art.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.NEAREST)


def face(size):
    for path in FACES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def fitting(label, size, widest):
    """The face to set a line in: smaller if it would run wider than widest."""
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    while True:
        font = face(size)
        left, _, right, _ = probe.textbbox((0, 0), label, font=font)
        if right - left <= widest or size <= 12:
            return font
        size -= 2


def line(draw, label, font, colour, middle):
    """Sets a line so its capitals are centred on middle, whatever its size
    and whether or not it has letters that hang below the line."""
    _, top, _, bottom = font.getbbox("H", anchor="ls")
    draw.text((SIZE // 2, middle + (bottom - top) // 2), label, font=font, fill=colour, anchor="ms")


def brackets(draw):
    a, b = BRACKET_INSET, SIZE - BRACKET_INSET
    for x, dx in ((a, 1), (b, -1)):
        for y, dy in ((a, 1), (BAND_TOP - BRACKET_INSET, -1)):
            draw.line([(x, y), (x + dx * BRACKET, y)], fill=ACCENT, width=LINE)
            draw.line([(x, y), (x, y + dy * BRACKET)], fill=ACCENT, width=LINE)


def frame(art, name):
    card = Image.new("RGBA", (SIZE, SIZE), GROUND)
    draw = ImageDraw.Draw(card)
    for n in range(0, SIZE, GRID_STEP):
        draw.line([(n, 0), (n, BAND_TOP)], fill=GRID)
        draw.line([(0, n), (SIZE, n)], fill=GRID)
    art, cut = cut_out(art)
    art = fitted(art)
    x = ART_CENTRE[0] - art.width // 2
    y = ART_CENTRE[1] - art.height // 2
    if not cut:
        draw.rectangle([x - LINE, y - LINE, x + art.width + LINE - 1, y + art.height + LINE - 1], fill=ACCENT)
    card.alpha_composite(art, (x, y))
    brackets(draw)
    draw.rectangle([0, BAND_TOP, SIZE, SIZE], fill=BAND)
    draw.rectangle([0, BAND_TOP, SIZE, BAND_TOP + LINE - 1], fill=ACCENT)
    draw = ImageDraw.Draw(card)
    line(draw, name, fitting(name, TITLE_SIZE, SIZE - 56), TITLE, BAND_TOP + 44)
    line(draw, GAME, fitting(GAME, SUBTITLE_SIZE, SIZE - 56), SUBTITLE, SIZE - 28)
    return card.convert("RGB")


def manifest_name(root=ROOT):
    with open(os.path.join(root, "manifest.txt"), encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.match(r'\s*Name\s+"?([^"\r\n]+?)"?\s*$', line)
            if m:
                return m.group(1)
    raise SystemExit("manifest.txt names no mod")


def build(root=ROOT):
    art = Image.open(os.path.join(root, "tools", "card-art.png"))
    frame(art, manifest_name(root)).save(os.path.join(root, "thumbnail.png"))


if __name__ == "__main__":
    build()
    print("wrote thumbnail.png")
