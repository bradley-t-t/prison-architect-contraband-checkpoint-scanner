"""Builds every generated file the Strip Search mod ships.

Outputs, relative to the mod root (the parent of this tools/ folder):
  data/sprites.png                  the scanner's four frames and both doors
  data/materials.txt                the scanner, the two doors and the room
  data/prefabs.txt                  the four quick builds, 1x1 to 4x4
  data/language/base-language.txt   names, build-menu text and tooltips
  thumbnail.png                     the mod's card image in the game's mod list
  tools/preview.png                 every sprite at twice the size, labelled

Usage: python gen_assets.py

The scanner script itself, data/scripts/StripSearchScanner.lua, is written
by hand and not touched here.
"""

import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
TOOLS = os.path.join(ROOT, "tools")

# Sprites are laid out on a sheet of 32 px cells; a tile is two cells.
CELL = 32
TILE = 64

STEEL = (150, 156, 164)
STEEL_HI = (196, 201, 208)
STEEL_LO = (104, 110, 118)
DARK = (44, 48, 54)
DARK_HI = (66, 71, 78)
SHADOW = (0, 0, 0, 90)

# The scanner is a floor gate people walk over: two posts either side of the
# tile with a light bar between them. Frame 0 is idle, 1 and 2 are the two
# halves of the scanning pulse, 3 is all clear.
SCANNER_FRAMES = 4
FRAME_IDLE, FRAME_SCAN_A, FRAME_SCAN_B, FRAME_CLEAR = range(SCANNER_FRAMES)
SCAN_BLUE = dict(core=(72, 165, 255), hot=(205, 235, 255), dim=(22, 78, 190))
CLEAR_GREEN = dict(core=(84, 220, 120), hot=(200, 255, 215), dim=(24, 120, 60))
IDLE_AMBER = dict(core=(255, 176, 32), hot=(255, 230, 170), dim=(120, 76, 10))

# The doors are plain doors the game slides open along the wall. Each has one
# sprite: the door leaf in its frame, with a coloured band that says which
# door it is. Green is the way in, amber the way out.
DOORS = [
    # name, band colour, price
    ("StripSearchDoorIn", (84, 220, 120), 300),
    ("StripSearchDoorOut", (255, 176, 32), 300),
]

# The engine does not rotate a sprite that rotates with the wall; it reads
# pre-drawn orientations from fixed spots beside the base sprite (x, y, w, h):
# the 180-degree version at (x + w, y), and the 90 and 270-degree versions at
# (x + 2w, y + h - w) and (x + 2w + h, y + h - w). For a one-tile door that is
# four 2x2 sprites in a row, eight cells per door.
DOOR_STRIDE = 8
DOOR_ROW = 2
SHEET_CELLS = (16, 4)

# The quick builds: a chamber of N by N tiles. Each side of the room is an
# outer door in the outside wall, a one-tile vestibule walled off to the
# door's column, and an inner door in a wall across the room. The scanner
# stands in the door column in the middle of the chamber.
PREFAB_SIZES = (1, 2, 3, 4)
FLOOR = "ConcreteTiles"
WALL = "ConcreteWall"

SCANNER_PRICE = 1000


# ---------------------------------------------------------------- drawing

def overlay(w=TILE, h=TILE):
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def post(d, x0, y0, x1, y1):
    d.rectangle([x0, y0, x1, y1], fill=STEEL + (255,))
    d.line([(x0, y0), (x1, y0)], fill=STEEL_HI + (255,))
    d.line([(x0, y0), (x0, y1)], fill=STEEL_HI + (255,))
    d.line([(x0, y1), (x1, y1)], fill=STEEL_LO + (255,))
    d.line([(x1, y0), (x1, y1)], fill=STEEL_LO + (255,))


def scanner_sprite(frame):
    """The gate seen from above: a post at the west and east edge of the
    tile, a dark mat between them, and the light bar across the middle."""
    im = overlay()
    d = ImageDraw.Draw(im)
    d.rectangle([4, 6, 59, 61], fill=SHADOW)
    d.rectangle([12, 4, 51, 59], fill=DARK + (255,))
    d.rectangle([12, 4, 51, 5], fill=DARK_HI + (255,))
    for y in range(10, 58, 8):
        d.line([(14, y), (49, y)], fill=DARK_HI + (255,))
    post(d, 2, 2, 11, 61)
    post(d, 52, 2, 61, 61)
    for x0 in (4, 54):
        for y in (8, 20, 32, 44):
            d.rectangle([x0, y, x0 + 5, y + 8], fill=(58, 62, 70, 255))
    if frame == FRAME_IDLE:
        col, bar = IDLE_AMBER, [(28, 34)]
    elif frame == FRAME_SCAN_A:
        col, bar = SCAN_BLUE, [(14, 22), (40, 48)]
    elif frame == FRAME_SCAN_B:
        col, bar = SCAN_BLUE, [(26, 36)]
    else:
        col, bar = CLEAR_GREEN, [(20, 42)]
    glow = overlay()
    g = ImageDraw.Draw(glow)
    for y0, y1 in bar:
        g.rectangle([12, y0 - 3, 51, y1 + 3], fill=col["dim"] + (110,))
        g.rectangle([12, y0, 51, y1], fill=col["core"] + (230,))
        mid = (y0 + y1) // 2
        g.line([(14, mid), (49, mid)], fill=col["hot"] + (255,))
    im.alpha_composite(glow)
    # the lamp on each post
    for x0 in (4, 54):
        d.rectangle([x0, 55, x0 + 5, 58], fill=col["core"] + (255,))
        d.line([(x0 + 1, 56), (x0 + 4, 56)], fill=col["hot"] + (255,))
    return im


def door_leaf(band):
    """A door in an east-west wall, seen from above: the leaf fills the
    doorway between two end posts, with the band across its middle."""
    im = overlay()
    d = ImageDraw.Draw(im)
    d.rectangle([2, 22, 61, 43], fill=SHADOW)
    for x0 in (0, TILE - 8):
        d.rectangle([x0, 18, x0 + 7, 45], fill=STEEL + (255,))
        d.line([(x0, 18), (x0, 45)], fill=STEEL_HI + (255,))
        d.line([(x0 + 7, 18), (x0 + 7, 45)], fill=STEEL_LO + (255,))
    d.rectangle([8, 22, 55, 41], fill=(96, 102, 110, 255))
    d.rectangle([8, 22, 55, 23], fill=STEEL_HI + (255,))
    d.rectangle([8, 40, 55, 41], fill=STEEL_LO + (255,))
    for x in range(12, 54, 6):
        d.line([(x, 25), (x, 38)], fill=(80, 86, 94, 255))
    d.rectangle([8, 29, 55, 34], fill=band + (255,))
    d.rectangle([8, 29, 55, 29], fill=tuple(min(255, c + 60) for c in band) + (255,))
    d.rectangle([8, 34, 55, 34], fill=tuple(max(0, c - 60) for c in band) + (255,))
    for x in (28, 33):
        d.rectangle([x, 30, x + 2, 33], fill=(30, 33, 38, 255))
    return im


def build_sprites():
    sheet = Image.new("RGBA", (SHEET_CELLS[0] * CELL, SHEET_CELLS[1] * CELL), (0, 0, 0, 0))
    for f in range(SCANNER_FRAMES):
        sheet.paste(scanner_sprite(f), (f * TILE, 0))
    for i, (_, band, _) in enumerate(DOORS):
        flat = door_leaf(band)
        x0 = i * DOOR_STRIDE * CELL
        y0 = DOOR_ROW * CELL
        sheet.paste(flat, (x0, y0))
        sheet.paste(flat.transpose(Image.ROTATE_180), (x0 + 2 * CELL, y0))
        sheet.paste(flat.transpose(Image.ROTATE_270), (x0 + 4 * CELL, y0))
        sheet.paste(flat.transpose(Image.ROTATE_90), (x0 + 6 * CELL, y0))
    return sheet


def build_thumbnail():
    im = Image.new("RGBA", (256, 256), (16, 18, 21, 255))
    cells = [door_leaf(DOORS[0][1]), scanner_sprite(FRAME_SCAN_A),
             scanner_sprite(FRAME_CLEAR), door_leaf(DOORS[1][1])]
    for i, t in enumerate(cells):
        im.paste(t.resize((128, 128), Image.NEAREST), ((i % 2) * 128, (i // 2) * 128), t.resize((128, 128), Image.NEAREST))
    return im


def build_preview():
    im = Image.new("RGBA", (6 * 140 + 20, 2 * 160), (30, 30, 50, 255))
    d = ImageDraw.Draw(im)
    for f in range(SCANNER_FRAMES):
        im.paste(scanner_sprite(f).resize((128, 128), Image.NEAREST), (f * 140 + 10, 16))
        d.text((f * 140 + 10, 2), f"StripSearchScanner frame {f}", fill=(255, 255, 0, 255))
    for i, (name, band, _) in enumerate(DOORS):
        flat = door_leaf(band)
        im.paste(flat.resize((128, 128), Image.NEAREST), (i * 280 + 10, 176))
        d.text((i * 280 + 10, 162), name, fill=(255, 255, 0, 255))
        im.paste(flat.transpose(Image.ROTATE_90).resize((128, 128), Image.NEAREST), (i * 280 + 150, 176))
        d.text((i * 280 + 150, 162), name + " vertical", fill=(255, 255, 0, 255))
    return im


# ---------------------------------------------------------------- text files

def materials_text():
    sprites = ""
    for f in range(SCANNER_FRAMES):
        sprites += f"    BEGIN Sprite         x {2 * f}  y 0  w 2  h 2  RotateType 0  TopAligned false  END\n"
    text = f"""BEGIN Object
    Name                 StripSearchScanner
    ConstructionTime     10.0000
    Toughness            200.000
    Price                -{SCANNER_PRICE}
    Filter               Security
    RenderDepth          3
    Group                StaticObject
    BlockedBy            Wall
    BlockedBy            UtilityStation
    BlockedBy            StaticObject
    MadeOf               SolidMetal
    Properties           StaticObject
    Properties           Scripted
    Properties           DontAvoid
    NumSprites           {SCANNER_FRAMES}
    BEGIN ToolbarSprite  x 0  y 0  w 2  h 2  END
{sprites}END

"""
    for i, (name, _, price) in enumerate(DOORS):
        x = i * DOOR_STRIDE
        text += f"""BEGIN Object
    Name                 {name}
    ConstructionTime     10.0000
    Toughness            300.000
    Teleportable         true
    Price                -{price}
    Filter               Security
    RenderDepth          2
    Group                StaticObject
    BlockedBy            StaticObject
    BlockedBy            UtilityStation
    MadeOf               SolidMetal
    Properties           StaticObject
    Properties           Door
    NumSprites           1
    BEGIN ToolbarSprite  x {x}  y {DOOR_ROW}  w 2  h 2  END
    BEGIN Sprite         x {x}  y {DOOR_ROW}  w 2  h 2  RotateType 1  TopAligned false  END
END

"""
    text += """BEGIN Room
    Name                 StripSearch
    BEGIN Requirement Type Enclosed  END
    BEGIN Requirement Type MinimumSize  x 1  y 1  END
    BEGIN Requirement Type Object  Id StripSearchScanner  END
    BEGIN LikelyObject  Id  StripSearchDoorIn  END
    BEGIN LikelyObject  Id  StripSearchDoorOut  END
END
"""
    return text


def prefab_text(n):
    w, h = n + 2, n + 6
    dc = 1 + n // 2
    lines = [
        "BEGIN Prefab",
        f"    Name        StripSearch{n}",
        f"    w           {w}",
        f"    h           {h}",
        "    RoomType    StripSearch",
    ]

    def material(kind, x, y, mw, mh):
        lines.append(f"    BEGIN Material  Type    {kind:<20} x {x:>3}  y {y:>3}  w {mw:>3}  h {mh:>3}  END")

    def obj(kind, x, y):
        lines.append(f"    BEGIN Object    Type    {kind:<20} x {x:>3}  y {y:>3}  orX  0  orY  1  END")

    # floor under the whole way through, chamber and both vestibules
    material(FLOOR, 1, 1, n, h - 2)
    # the vestibule rows are walled off to the door's column
    for y in (1, h - 2):
        if dc > 1:
            material(WALL, 1, y, dc - 1, 1)
        if dc < n:
            material(WALL, dc + 1, y, n - dc, 1)
    # the walls across the room that carry the inner doors
    material(WALL, 1, 2, n, 1)
    material(WALL, 1, h - 3, n, 1)
    lines.append(f"    BEGIN Zone      Type    StripSearch          x   1  y   3  w {n:>3}  h {n:>3}  END")
    obj("StripSearchDoorIn", dc, 0)
    obj("StripSearchDoorIn", dc, 2)
    obj("StripSearchScanner", dc, 3 + n // 2)
    obj("StripSearchDoorOut", dc, h - 3)
    obj("StripSearchDoorOut", dc, h - 1)
    lines.append("END")
    return "\n".join(lines) + "\n"


def prefabs_text():
    return "\n".join(prefab_text(n) for n in PREFAB_SIZES)


def language_text():
    door_in = ("The way into a Strip Search room. The room's scanner holds it: open while people "
               "are coming in, shut while they are searched, and never open together with the exit.")
    door_out = ("The way out of a Strip Search room. The room's scanner holds it shut until everyone "
                "inside has been searched, so nothing gets past the room unsearched.")
    scanner = ("Runs a Strip Search room. Build it in a walled room with a Strip Search Entrance and a "
               "Strip Search Exit, or use the quick builds. It lets people in through one door, shuts "
               "them in, calls guards to search every prisoner, crooked guard and crate inside, and only "
               "then opens the other door. Nothing crosses the room without a search.")
    room = ("A search checkpoint. Everyone who goes through is shut in and searched by a guard before the far "
            "door opens, so contraband cannot be carried past it. Build with the quick builds, or by hand: "
            "a walled room with a Strip Search Scanner, a Strip Search Entrance in one wall and a Strip "
            "Search Exit in another, each best with a one-tile vestibule behind a second door of the same kind.")
    rows = [
        ("object_StripSearchScanner", "Strip Search Scanner"),
        ("buildtoolbar_popup_obj_StripSearchScanner", scanner),
        ("object_StripSearchDoorIn", "Strip Search Entrance"),
        ("buildtoolbar_popup_obj_StripSearchDoorIn", door_in),
        ("object_StripSearchDoorOut", "Strip Search Exit"),
        ("buildtoolbar_popup_obj_StripSearchDoorOut", door_out),
        ("room_stripsearch", "Strip Search"),
        ("buildtoolbar_popup_room_stripsearch", room),
        ("tooltip_StripSearchScanner_Intake", "Letting people in."),
        ("tooltip_StripSearchScanner_Sealed", "Shut. Everyone inside is being searched."),
        ("tooltip_StripSearchScanner_Release", "All clear. Letting people out."),
    ]
    for n in PREFAB_SIZES:
        label = f"Strip Search {n}x{n}"
        rows.append((f"quickbuild_stripsearch{n}", label))
        rows.append((f"quickbuild_StripSearch{n}", label))
    width = max(len(k) for k, _ in rows) + 4
    return "".join(f"{k:<{width}}{v}\n" for k, v in rows)


def main():
    os.makedirs(os.path.join(DATA, "language"), exist_ok=True)
    build_sprites().save(os.path.join(DATA, "sprites.png"))
    with open(os.path.join(DATA, "materials.txt"), "w") as f:
        f.write(materials_text())
    with open(os.path.join(DATA, "prefabs.txt"), "w") as f:
        f.write(prefabs_text())
    with open(os.path.join(DATA, "language", "base-language.txt"), "w") as f:
        f.write(language_text())
    build_thumbnail().save(os.path.join(ROOT, "thumbnail.png"))
    build_preview().save(os.path.join(TOOLS, "preview.png"))
    print("wrote sprites.png, materials.txt, prefabs.txt, base-language.txt, thumbnail.png, preview.png")


if __name__ == "__main__":
    main()
