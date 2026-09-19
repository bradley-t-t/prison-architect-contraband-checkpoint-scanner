"""Builds every generated file the Contraband Checkpoint Scanner mod ships.

Outputs, relative to the mod root (the parent of this tools/ folder):
  data/sprites.png                  the Medical Probe Machine's two frames and the Room Scanner
  data/materials.txt                the machine, the scanner and the room
  data/language/base-language.txt   names, build-menu text and tooltips
  thumbnail.png                     the mod's card, built by card.py around tools/card-art.png

Usage: python gen_assets.py

The scripts, data/scripts/MedicalProbeMachine.lua and data/world.lua, are
written by hand and not touched here.
"""

import os

from PIL import Image, ImageChops, ImageDraw

import card

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

# The game measures a sprite sheet in 32-pixel cells; a map tile is two.
CELL = 32
TILE = 64

STEEL = (150, 156, 164)
STEEL_HI = (196, 201, 208)
STEEL_LO = (104, 110, 118)
DARK = (44, 48, 54)
DARK_HI = (66, 71, 78)
PAD = (222, 228, 232)
PAD_LO = (176, 184, 190)
SHADOW = (0, 0, 0, 90)

# Frame 0 is the machine at rest, frame 1 the machine with someone held.
FRAMES = 2
LAMPS = [
    dict(core=(84, 220, 120), hot=(200, 255, 215)),
    dict(core=(235, 64, 64), hot=(255, 200, 200)),
]
SHEET_CELLS = (8, 2)
PRICE = 500
SCANNER_PRICE = 800
SCANNER_CELL = 4             # where the Room Scanner sits on the sheet, in cells
LENS = dict(core=(72, 165, 255), hot=(205, 235, 255), dim=(22, 78, 190))


def overlay(w=TILE, h=TILE):
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def plate(d, x0, y0, x1, y1, fill=STEEL):
    d.rectangle([x0, y0, x1, y1], fill=fill + (255,))
    d.line([(x0, y0), (x1, y0)], fill=STEEL_HI + (255,))
    d.line([(x0, y0), (x0, y1)], fill=STEEL_HI + (255,))
    d.line([(x0, y1), (x1, y1)], fill=STEEL_LO + (255,))
    d.line([(x1, y0), (x1, y1)], fill=STEEL_LO + (255,))


def machine_sprite(frame):
    """The machine seen from above: a steel cabinet along the top of the
    tile with a screen and a lamp, a padded couch below it, and the probe
    arm reaching out over the couch."""
    lamp = LAMPS[frame]
    im = overlay()
    d = ImageDraw.Draw(im)
    d.rectangle([5, 7, 61, 62], fill=SHADOW)
    # the couch
    plate(d, 12, 22, 51, 59, DARK)
    d.rectangle([15, 25, 48, 56], fill=PAD + (255,))
    d.rectangle([15, 55, 48, 56], fill=PAD_LO + (255,))
    d.line([(15, 36), (48, 36)], fill=PAD_LO + (255,))
    # the cabinet
    plate(d, 3, 3, 60, 21)
    d.rectangle([8, 7, 31, 17], fill=DARK + (255,))
    d.rectangle([8, 7, 31, 8], fill=DARK_HI + (255,))
    d.line([(11, 13), (15, 13), (18, 10), (21, 15), (24, 12), (28, 12)], fill=lamp["core"] + (255,))
    for x in (38, 44):
        d.rectangle([x, 8, x + 3, 11], fill=DARK_HI + (255,))
    d.rectangle([51, 7, 56, 12], fill=lamp["core"] + (255,))
    d.line([(52, 8), (55, 8)], fill=lamp["hot"] + (255,))
    # the arm and the probe
    d.rectangle([36, 20, 40, 44], fill=STEEL_LO + (255,))
    d.line([(36, 20), (36, 44)], fill=STEEL_HI + (255,))
    d.rectangle([33, 42, 43, 47], fill=STEEL + (255,))
    d.rectangle([37, 47, 39, 52], fill=lamp["core"] + (255,))
    return im


def scanner_sprite():
    """The Room Scanner seen from above: a round sensor head on a dark floor
    plate, with a blue lens and four short feet."""
    im = overlay()
    d = ImageDraw.Draw(im)
    d.ellipse([10, 13, 58, 61], fill=SHADOW)
    for x, y in ((8, 8), (48, 8), (8, 48), (48, 48)):
        d.rectangle([x, y, x + 7, y + 7], fill=STEEL_LO + (255,))
    d.ellipse([6, 6, 57, 57], fill=DARK + (255,))
    d.ellipse([6, 6, 57, 57], outline=DARK_HI + (255,))
    d.ellipse([13, 13, 50, 50], fill=STEEL + (255,))
    d.arc([13, 13, 50, 50], 180, 300, fill=STEEL_HI + (255,))
    d.arc([13, 13, 50, 50], 0, 120, fill=STEEL_LO + (255,))
    d.ellipse([20, 20, 43, 43], fill=LENS["dim"] + (255,))
    d.ellipse([24, 24, 39, 39], fill=LENS["core"] + (255,))
    d.ellipse([27, 26, 33, 31], fill=LENS["hot"] + (255,))
    return im


def build_sprites():
    sheet = Image.new("RGBA", (SHEET_CELLS[0] * CELL, SHEET_CELLS[1] * CELL), (0, 0, 0, 0))
    for f in range(FRAMES):
        sheet.paste(machine_sprite(f), (f * TILE, 0))
    sheet.paste(scanner_sprite(), (SCANNER_CELL * CELL, 0))
    return sheet


def build_thumbnail():
    im = Image.new("RGBA", (256, 256), (16, 18, 21, 255))
    big = machine_sprite(1).resize((192, 192), Image.NEAREST)
    im.paste(big, (8, 8), big)
    small = scanner_sprite().resize((96, 96), Image.NEAREST)
    im.paste(small, (152, 152), small)
    return im


def materials_text():
    sprites = ""
    for f in range(FRAMES):
        sprites += f"    BEGIN Sprite         x {2 * f}  y 0  w 2  h 2  RotateType 0  TopAligned false  END\n"
    return f"""BEGIN Object
    Name                 MedicalProbeMachine
    ConstructionTime     10.0000
    Toughness            200.000
    Price                -{PRICE}
    Filter               Security
    RenderDepth          1
    Group                StaticObject
    BlockedBy            Wall
    BlockedBy            UtilityStation
    BlockedBy            StaticObject
    MadeOf               SolidMetal
    Properties           StaticObject
    Properties           Scripted
    NumSprites           {FRAMES}
    BEGIN ToolbarSprite  x 0  y 0  w 2  h 2  END
{sprites}END

BEGIN Object
    Name                 RoomScanner
    ConstructionTime     10.0000
    Toughness            200.000
    Price                -{SCANNER_PRICE}
    Filter               Security
    RenderDepth          1
    Group                StaticObject
    BlockedBy            Wall
    BlockedBy            UtilityStation
    BlockedBy            StaticObject
    MadeOf               SolidMetal
    Properties           StaticObject
    NumSprites           1
    BEGIN ToolbarSprite  x {SCANNER_CELL}  y 0  w 2  h 2  END
    BEGIN Sprite         x {SCANNER_CELL}  y 0  w 2  h 2  RotateType 0  TopAligned false  END
END

BEGIN Room
    Name                 StripSearch
    BEGIN Requirement Type MinimumSize  x 2  y 2  END
    BEGIN Requirement Type Object  Id MedicalProbeMachine  END
    BEGIN Requirement Type Object  Id RoomScanner  END
END
"""


def language_text():
    machine = ("Runs the Strip Search room it stands in. Every prisoner who steps into the room is probed, "
               "which hurts a little, and a guard is called to search them. Crooked guards and crates are "
               "searched too, and anyone carrying a crate sets it down to be searched. Nobody unsearched "
               "leaves the room.")
    scanner = ("Stands on the floor of a Strip Search room and catches crooked guards. A crooked guard who "
               "comes to search in the room searches as an honest one would, so a bribe buys nothing, and "
               "comes out of the job exposed.")
    room = ("Anyone who steps in is searched by a guard before they can leave. Zone it across a corridor "
            "or a doorway and put a Medical Probe Machine and a Room Scanner in it. It needs no doors of "
            "its own. Keep guards close by: with none free, people wait.")
    rows = [
        ("object_MedicalProbeMachine", "Medical Probe Machine"),
        ("buildtoolbar_popup_obj_MedicalProbeMachine", machine),
        ("object_RoomScanner", "Room Scanner"),
        ("buildtoolbar_popup_obj_RoomScanner", scanner),
        ("room_stripsearch", "Strip Search"),
        ("buildtoolbar_popup_room_stripsearch", room),
        ("tooltip_MedicalProbeMachine_NoRoom", "Not in a Strip Search room. Zone one over it."),
        ("tooltip_MedicalProbeMachine_NoScanner", "No Room Scanner in the room. A bribed guard's search here can miss."),
        ("tooltip_MedicalProbeMachine_Holding", "Holding people until a guard has searched them."),
        ("tooltip_MedicalProbeMachine_Clear", "Nobody waiting to be searched."),
    ]
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
    with open(os.path.join(DATA, "language", "base-language.txt"), "w") as f:
        f.write(language_text())
    save_image(build_thumbnail(), os.path.join(ROOT, "tools", "card-art.png"))
    card.build(ROOT)
    print("wrote sprites.png, materials.txt, base-language.txt, thumbnail.png")


if __name__ == "__main__":
    main()
