"""Builds every generated file the Strip Search mod ships.

Outputs, relative to the mod root (the parent of this tools/ folder):
  data/sprites.png                  the scanner's four frames and both doors
  data/materials.txt                the scanner, the two doors and the room
  data/prefabs.txt                  the four quick builds, 1x1 to 4x4
  data/language/base-language.txt   names, build-menu text and tooltips
  thumbnail.png                     the mod's card image in the game's mod list
  tools/preview.png                 every sprite at twice the size, and a plan of each quick build

Usage: python gen_assets.py

The scanner script itself, data/scripts/StripSearchScanner.lua, is written
by hand and not touched here.
"""

import os

from PIL import Image, ImageChops, ImageDraw

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

# The quick builds, drawn a character to a tile: "#" wall, "." a lobby's
# floor, "," the searched room's floor, "I" and "O" the entrance and exit
# doors, "S" the scanner. People walk straight down the map, in at the top
# and out at the bottom: outer door, lobby, inner door, the room, inner door,
# lobby, outer door. The ring of wall round the edge is the game's own work,
# since a quick build walls its edge itself in whatever wall the player has
# picked and builds every wall drawn here in the same one. No wall is more
# than a tile thick, because the game draws a thicker one as a lattice. The
# column the doors stand in is kept clear of furniture. What furnishes a
# build is listed beside its map as (type, x, y, facing): "s" and "n" face
# down and up the map, and "e" and "w" turn a long piece to run down the map
# from x, y. Nothing here is anything a prisoner can use: a chair or a bench
# meets the need for comfort, and one in this room would bring prisoners in
# from all over the prison to sit on it.
LOBBY_FLOOR = "ConcreteFloor"
ROOM_FLOOR = "NewCargoFloor"
WALL = "ConcreteWall"
FACING = {"s": (0, 1), "n": (0, -1), "e": (1, 0), "w": (-1, 0)}
LAYOUTS = {
    1: dict(
        rows=["#I#",
              "#.#",
              "#I#",
              "#S#",
              "#O#",
              "#.#",
              "#O#"],
        things=[("Light", 1, 1, "s"), ("Light", 1, 5, "s")]),
    2: dict(
        rows=["##I#",
              "#..#",
              "##I#",
              "#,,#",
              "#,S#",
              "##O#",
              "#..#",
              "##O#"],
        things=[("OfficeDesk", 1, 3, "e"),
                ("Light", 1, 1, "s"), ("Light", 2, 3, "s"), ("Light", 1, 6, "s")]),
    3: dict(
        rows=["##I##",
              "#...#",
              "##I##",
              "#,,,#",
              "#,S,#",
              "#,,,#",
              "##O##",
              "#...#",
              "##O##"],
        things=[("FilingCabinet", 1, 3, "s"), ("OfficeDesk", 1, 4, "e"),
                ("Light", 2, 1, "s"), ("Light", 2, 3, "s"), ("Light", 2, 7, "s")]),
    4: dict(
        rows=["##I###",
              "#....#",
              "##I###",
              "#,,,,#",
              "#,,,,#",
              "#,S,,#",
              "#,,,,#",
              "##O###",
              "#....#",
              "##O###"],
        things=[("FilingCabinet", 1, 3, "s"), ("OfficeDesk", 1, 4, "e"), ("Table", 4, 3, "e"),
                ("Light", 3, 1, "s"), ("Light", 3, 4, "s"), ("Light", 3, 8, "s")]),
}
PREFAB_SIZES = tuple(sorted(LAYOUTS))

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


# What each piece of furniture covers, in tiles, lying along the map.
FOOTPRINT = {"OfficeDesk": (2, 1), "Table": (4, 1)}
PLAN_TILE = 28
PLAN_COLOURS = {
    "#": (74, 78, 86), ".": (150, 146, 140), ",": (52, 74, 84),
    "OfficeDesk": (156, 112, 66), "FilingCabinet": (104, 142, 64), "Table": (226, 226, 222),
}


def layout_plan(n):
    """One quick build drawn as a plan: walls, the two floors, the mod's own
    sprites for the doors and the scanner, a block for each piece of
    furniture and a dot for each light."""
    layout = LAYOUTS[n]
    rows = layout["rows"]
    t = PLAN_TILE
    im = Image.new("RGBA", (len(rows[0]) * t, len(rows) * t), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            floor = "," if c == "S" else "." if c in "IO" else c
            d.rectangle([x * t, y * t, (x + 1) * t - 1, (y + 1) * t - 1], fill=PLAN_COLOURS[floor] + (255,))
            if floor != "#":
                d.rectangle([x * t, y * t, (x + 1) * t - 1, (y + 1) * t - 1], outline=(0, 0, 0, 28))
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            sprite = {"I": door_leaf(DOORS[0][1]), "O": door_leaf(DOORS[1][1]),
                      "S": scanner_sprite(FRAME_IDLE)}.get(c)
            if sprite is not None:
                small = sprite.resize((t, t), Image.LANCZOS)
                im.paste(small, (x * t, y * t), small)
    for kind, x, y, facing in layout["things"]:
        if kind == "Light":
            cx, cy = x * t + t // 2, y * t + t // 2
            d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(255, 214, 64, 255), outline=(120, 90, 0, 255))
            continue
        w, h = FOOTPRINT.get(kind, (1, 1))
        if facing in "ew":
            w, h = h, w
        d.rounded_rectangle([x * t + 3, y * t + 3, (x + w) * t - 4, (y + h) * t - 4], radius=4,
                            fill=PLAN_COLOURS[kind] + (255,), outline=(0, 0, 0, 160))
    return im


def build_preview():
    plans = [layout_plan(n) for n in PREFAB_SIZES]
    top = 2 * 160
    im = Image.new("RGBA", (6 * 140 + 20, top + max(p.height for p in plans) + 40), (30, 30, 50, 255))
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
    x = 10
    for n, plan in zip(PREFAB_SIZES, plans):
        d.text((x, top + 6), f"StripSearch{n}  {plan.width // PLAN_TILE}x{plan.height // PLAN_TILE}", fill=(255, 255, 0, 255))
        im.paste(plan, (x, top + 24), plan)
        x += plan.width + 40
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


def rectangles(rows, wanted):
    """The tiles of a map drawn in any of the wanted characters, as a few
    rectangles (x, y, w, h): runs along each row, joined down the map where
    the same run repeats."""
    open_runs, done = {}, []
    for y, row in enumerate(rows):
        runs, x = [], 0
        while x < len(row):
            if row[x] in wanted:
                start = x
                while x < len(row) and row[x] in wanted:
                    x += 1
                runs.append((start, x - start))
            else:
                x += 1
        carried = {}
        for run in runs:
            if run in open_runs:
                top, height = open_runs.pop(run)
                carried[run] = (top, height + 1)
            else:
                carried[run] = (y, 1)
        done += [(rx, top, rw, height) for (rx, rw), (top, height) in open_runs.items()]
        open_runs = carried
    done += [(rx, top, rw, height) for (rx, rw), (top, height) in open_runs.items()]
    return sorted(done, key=lambda r: (r[1], r[0]))


def prefab_text(n):
    layout = LAYOUTS[n]
    rows = layout["rows"]
    w, h = len(rows[0]), len(rows)
    assert all(len(row) == w for row in rows), f"size {n}: ragged map"
    inside = [row[1:-1] for row in rows[1:-1]]
    lines = [
        "BEGIN Prefab",
        f"    Name        StripSearch{n}",
        f"    w           {w}",
        f"    h           {h}",
        "    RoomType    StripSearch",
    ]

    def material(kind, wanted):
        for x, y, mw, mh in rectangles(inside, wanted):
            lines.append(f"    BEGIN Material  Type    {kind:<20} x {x + 1:>3}  y {y + 1:>3}  w {mw:>3}  h {mh:>3}  END")

    def obj(kind, x, y, facing="s"):
        ox, oy = FACING[facing]
        lines.append(f"    BEGIN Object    Type    {kind:<20} x {x:>3}  y {y:>3}  orX {ox:>2}  orY {oy:>2}  END")

    # floor first, the doors' own tiles included; walls never under a door
    material(LOBBY_FLOOR, ".IO")
    material(ROOM_FLOOR, ",S")
    material(WALL, "#")
    room = [(x, y) for y, row in enumerate(rows) for x, c in enumerate(row) if c in ",S"]
    x0, y0 = min(x for x, _ in room), min(y for _, y in room)
    x1, y1 = max(x for x, _ in room), max(y for _, y in room)
    assert len(room) == (x1 - x0 + 1) * (y1 - y0 + 1), f"size {n}: the room is not a rectangle"
    lines.append(f"    BEGIN Zone      Type    StripSearch          x {x0:>3}  y {y0:>3}  w {x1 - x0 + 1:>3}  h {y1 - y0 + 1:>3}  END")
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            if c == "I":
                obj("StripSearchDoorIn", x, y)
            elif c == "O":
                obj("StripSearchDoorOut", x, y)
            elif c == "S":
                obj("StripSearchScanner", x, y)
    for kind, x, y, facing in layout["things"]:
        obj(kind, x, y, facing)
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
            "Search Exit in another, each best with a lobby behind a second door of the same kind.")
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


def save_image(im, path):
    """Writes a picture unless the file already holds the same pixels: a
    different version of the imaging library packs the same picture into
    different bytes, and that is not a change."""
    if os.path.exists(path):
        with Image.open(path) as old:
            if old.size == im.size and ImageChops.difference(old.convert("RGBA"), im.convert("RGBA")).getbbox() is None:
                return
    im.save(path)


def main():
    os.makedirs(os.path.join(DATA, "language"), exist_ok=True)
    save_image(build_sprites(), os.path.join(DATA, "sprites.png"))
    with open(os.path.join(DATA, "materials.txt"), "w") as f:
        f.write(materials_text())
    with open(os.path.join(DATA, "prefabs.txt"), "w") as f:
        f.write(prefabs_text())
    with open(os.path.join(DATA, "language", "base-language.txt"), "w") as f:
        f.write(language_text())
    save_image(build_thumbnail(), os.path.join(ROOT, "thumbnail.png"))
    save_image(build_preview(), os.path.join(TOOLS, "preview.png"))
    print("wrote sprites.png, materials.txt, prefabs.txt, base-language.txt, thumbnail.png, preview.png")


if __name__ == "__main__":
    main()
