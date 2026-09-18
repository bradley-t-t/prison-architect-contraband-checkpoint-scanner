"""Runs the Strip Search Scanner script against a mock of the game.

The mock stands in for the engine. Its map is the quick build the mod ships,
read from data/prefabs.txt: four doors, an outer and an inner one on each
side of the room with a lobby between them, that swing on their own when
someone asks and obey the scanner's writes. People walk a corridor that
passes through the room, and spread out sideways wherever a shut door holds
them up. Guards take the search jobs the scanner asks for, walk to the
person, stand against them for the game's ten seconds (five for a crate)
and only then clear them. There are escorts, crates in a workman's arms, and
traffic in both directions.

It checks, over every seed and room size, that nothing crosses the room
without a finished search, that both doors are never open together, and
that everybody gets through in the end. It prints how long the crossing
took and how much the scanner asked of the engine.

Usage: python simulate.py [seeds]   (needs the lupa package)
"""

import math
import os
import random
import re
import sys

from lupa import LuaRuntime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "data", "scripts", "StripSearchScanner.lua")
WORLD_SCRIPT = os.path.join(ROOT, "data", "world.lua")
PREFABS = os.path.join(ROOT, "data", "prefabs.txt")
# What the map's walls are made of.
WALLS = ("ConcreteWall",)
SEEDS = int(sys.argv[1]) if len(sys.argv) > 1 else 12
DT = 1.0 / 30
HORIZON = 60 * 30            # simulated seconds per run
WALK = 1.6                   # tiles per second
DOOR_SPEED = 2.5             # openness per second when the engine swings a door
OPEN_AT = 0.75
SEARCH_WORK = {"entity": 10.0, "crate": 5.0}
SEARCH_COOLDOWN = 30.0
LOCK_GIVE_UP = 6.0           # seconds at a door locked shut before a route fails
RETREAT = 30.0               # seconds a prisoner whose route failed stays away
FAR = 8                      # tiles beyond a door where the corridor ends
REACH = 0.9                  # how close a guard stands to the person searched
# The mock counts tiles from the chamber's corner, so the entrance side is
# below zero. No map in the game has a tile below zero, and the scanner reads
# a destination of less than zero as none set, so everything the scripts see
# is moved this far along both ways.
SHIFT = 40


def read_prefab(n):
    """The quick build of that size as the mock's map: a grid of "wall",
    "lobby", "room" and "door", the chamber's corner, and the door column.
    The edge of a quick build is wall wherever no door stands."""
    text = open(PREFABS).read()
    block = next(b for b in re.split(r"\nBEGIN Prefab", "\n" + text)[1:]
                 if re.search(r"Name\s+StripSearch%d\b" % n, b))
    w, h = (int(re.search(r"^\s*%s\s+(\d+)" % k, block, re.M).group(1)) for k in ("w", "h"))
    grid = [["wall" if x in (0, w - 1) or y in (0, h - 1) else "lobby" for x in range(w)] for y in range(h)]
    for kind, x, y, mw, mh in re.findall(r"BEGIN Material\s+Type\s+(\S+)\s+x\s+(\d+)\s+y\s+(\d+)\s+w\s+(\d+)\s+h\s+(\d+)", block):
        for yy in range(int(y), int(y) + int(mh)):
            for xx in range(int(x), int(x) + int(mw)):
                if "Wall" in kind:
                    grid[yy][xx] = "wall"
    zx, zy, zw, zh = (int(v) for v in re.search(
        r"BEGIN Zone\s+Type\s+StripSearch\s+x\s+(\d+)\s+y\s+(\d+)\s+w\s+(\d+)\s+h\s+(\d+)", block).groups())
    for yy in range(zy, zy + zh):
        for xx in range(zx, zx + zw):
            grid[yy][xx] = "room"
    things = [(kind, int(x), int(y)) for kind, x, y in re.findall(
        r"BEGIN Object\s+Type\s+(\S+)\s+x\s+(\d+)\s+y\s+(\d+)", block)]
    for kind, x, y in things:
        if kind.startswith("StripSearchDoor"):
            grid[y][x] = "door"
    assert (zw, zh) == (n, n), "the %dx%d quick build's room is %dx%d" % (n, n, zw, zh)
    return grid, (zx, zy), things


def luafn(L, f):
    return L.eval("function(f) return function(...) return f(...) end end")(f)


class Thing:
    _next = 100

    def __init__(self, kind, x, y):
        self.id = Thing._next
        Thing._next += 1
        self.kind = kind
        self.x, self.y = float(x), float(y)
        self.props = {}
        self.alive = True


class Mover(Thing):
    """Someone walking the corridor from one end to the other."""

    def __init__(self, kind, world, direction, delay, carrying=False):
        cx = world.cx
        start = -3 - FAR if direction > 0 else world.n + 2 + FAR
        super().__init__(kind, cx + 0.5, start)
        self.direction = direction        # +1 walks entry to exit, -1 the reverse
        self.delay = delay
        self.carrying = carrying          # contraband, cleared only by a finished search
        self.searches = 0                 # finished searches during this visit
        self.crossed = False
        self.entered_by = None
        self.job = None                   # guards only
        self.dest = None
        self.follow = None                # escorted prisoner: the guard ahead
        self.crate = None                 # workman: the crate carried
        self.done = False
        self.finished_at = None
        self.searcher = False             # a guard who takes search jobs
        self.home_bound = False
        self.home_y = None
        self.escort = False
        self.blocked = 0.0                # seconds spent at a door locked shut
        self.retreat_until = 0.0          # a prisoner who gave up waits this long
        self.spot = None                  # where they drift to while held up


class World:
    def __init__(self, seed, n, scenario, wall=WALLS[0]):
        self.rng = random.Random(seed)
        self.n = n
        self.wall = wall
        # the mock's tiles count from the chamber's corner; the quick build's
        # count from its own
        self.grid, self.corner, things = read_prefab(n)
        door_x = {x - self.corner[0] for kind, x, y in things if kind.startswith("StripSearchDoor")}
        door_y = sorted(y - self.corner[1] for kind, x, y in things if kind.startswith("StripSearchDoor"))
        assert len(door_x) == 1 and door_y == [-3, -1, n, n + 2], "doors at %s, %s" % (door_x, door_y)
        self.cx = door_x.pop()
        self.t = 0.0
        self.tick = 0
        self.reads = 0
        self.writes = 0
        self.requests = 0
        self.lookups = 0
        self.log = []
        self.violations = []
        sx, sy = next((x, y) for kind, x, y in things if kind == "StripSearchScanner")
        self.scanner = Thing("StripSearchScanner", sx - self.corner[0] + 0.5, sy - self.corner[1] + 0.5)
        self.scanner.props.update({"SubType": 0, "Tooltip": ""})
        # rows: -3 outer In door, -2 In vestibule, -1 inner In door, 0..n-1 the
        # chamber, n inner Out door, n+1 Out vestibule, n+2 outer Out door
        self.door_in = Thing("StripSearchDoorIn", self.cx + 0.5, -3 + 0.5)
        self.door_in_inner = Thing("StripSearchDoorIn", self.cx + 0.5, -1 + 0.5)
        self.door_out_inner = Thing("StripSearchDoorOut", self.cx + 0.5, n + 0.5)
        self.door_out = Thing("StripSearchDoorOut", self.cx + 0.5, n + 2 + 0.5)
        self.doors = (self.door_in, self.door_in_inner, self.door_out_inner, self.door_out)
        for d in self.doors:
            d.props["Open"] = 0.0
            d.props["Mode"] = 0
            d.requested = False
        self.movers = []
        self.crates = []
        self.jobs = []
        self.guards_home = []
        self.both_open_ticks = 0
        self.scenario = scenario
        scenario(self)

    # ---------------------------------------------------------------- geometry
    def tile(self, x, y):
        """What the quick build has at a tile, or None outside it."""
        gx, gy = math.floor(x) + self.corner[0], math.floor(y) + self.corner[1]
        if 0 <= gy < len(self.grid) and 0 <= gx < len(self.grid[0]):
            return self.grid[gy][gx]
        return None

    def inside(self, x, y):
        return self.tile(x, y) == "room"

    def span(self, y):
        """The open tiles of a row either side of the door column."""
        if self.tile(self.cx, y) not in ("lobby", "room"):
            return self.cx, self.cx
        lo = hi = self.cx
        while self.tile(lo - 1, y) in ("lobby", "room"):
            lo -= 1
        while self.tile(hi + 1, y) in ("lobby", "room"):
            hi += 1
        return lo, hi

    def door_at(self, y):
        ty = math.floor(y)
        if ty == -3:
            return self.door_in
        if ty == -1:
            return self.door_in_inner
        if ty == self.n:
            return self.door_out_inner
        if ty == self.n + 2:
            return self.door_out
        return None

    def in_airlock(self, y):
        return -3 <= y <= self.n + 2

    def door_open(self, door):
        return door.props["Open"] >= OPEN_AT

    def objects(self):
        yield self.scanner
        for d in self.doors:
            yield d
        for m in self.movers:
            if m.alive:
                yield m
        for c in self.crates:
            yield c

    # ---------------------------------------------------------------- lua side
    def bind(self, L, script):
        """Gives a Lua state what the game gives that kind of script. An
        object's own script ("object") gets Object, World, Interface and a
        Game holding only Time and DebugOut, with "this" as the object. A
        mod's world script ("world") gets Object, World, the whole Game
        library and the work queue, and has no object of its own."""
        world = self

        def proxy(obj):
            def index(t, k):
                world.reads += 1
                if k == "Id":
                    return L.table(i=obj.id, u=1)
                if k == "Pos":
                    return L.table(x=obj.x + SHIFT, y=obj.y + SHIFT)
                if k == "Or" and obj.kind.startswith("StripSearchDoor"):
                    return L.table(x=0, y=1)
                return obj.props.get(k)

            def newindex(t, k, v):
                world.writes += 1
                obj.props[k] = v

            t = L.table()
            L.globals().setmetatable(t, L.table(__index=luafn(L, index), __newindex=luafn(L, newindex)))
            L.eval("rawset")(t, "__id", obj.id)
            return t

        def resolve(tbl):
            i = L.eval("rawget")(tbl, "__id")
            for o in world.objects():
                if o.id == i:
                    return o
            return None

        def get_nearby(*args):
            world.reads += 1
            out = L.table()
            if len(args) == 3:
                centre, kind, rng = resolve(args[0]), args[1], args[2]
            elif script == "object":
                centre, kind, rng = world.scanner, args[0], args[1]
            else:
                centre = None      # a world script has no object to measure from
            if centre is None:
                return out
            # the game files each object's table under the object's Name when
            # it has one, so two objects sharing a Name come back as one
            named = {}
            for o in world.objects():
                if o.kind == kind and o is not centre:
                    d = math.hypot(o.x - centre.x, o.y - centre.y)
                    if d <= rng:
                        name = o.props.get("Name") or ""
                        if name:
                            named[name] = (o, d)
                        else:
                            out[proxy(o)] = d
            for o, d in named.values():
                out[proxy(o)] = d
            return out

        def get_property(*args):
            world.reads += 1
            if len(args) == 1:
                o, key = (world.scanner if script == "object" else None), args[0]
            else:
                o, key = resolve(args[0]), args[1]
            if o is None:
                return None
            if key == "JobId":
                return o.job.id if getattr(o, "job", None) else -1
            if key == "Dest":
                d = getattr(o, "dest", None)
                return L.table(x=d[0] + SHIFT, y=d[1] + SHIFT) if d else None
            if key == "CarrierId.i":
                return o.props.get("CarrierId.i", -1)
            return o.props.get(key)

        def set_property(*args):
            world.writes += 1
            if len(args) == 2:
                o, key, value = (world.scanner if script == "object" else None), args[0], args[1]
            else:
                o, key, value = resolve(args[0]), args[1], args[2]
            if o is not None:
                o.props[key] = float(value) if key == "Open" else value

        def get_object(name):
            # the first object in the world carrying that Name
            world.lookups += 1
            for o in world.objects():
                if o.props.get("Name") == name:
                    return proxy(o)
            return None

        def request(kind, tbl):
            assert kind == "SearchObject"
            world.requests += 1
            o = resolve(tbl)
            if o is None:
                return
            for j in world.jobs:
                if j.target is o and not j.done:
                    return
            if world.t - getattr(o, "last_searched", -1e9) < SEARCH_COOLDOWN:
                return
            world.jobs.append(Job(o, world.t))

        def get_cell(x, y):
            world.reads += 1
            what = world.tile(x - SHIFT, y - SHIFT)
            room = 7 if what == "room" else -1
            mat = {None: "Grass", "wall": world.wall, "room": "WhiteTiles"}.get(what, "ConcreteFloor")
            return L.table(Room=L.table(i=room, u=1), Mat=mat)

        debug_out = luafn(L, lambda s: world.log.append("%7.2f %s" % (world.t, s)))
        game_time = luafn(L, lambda: world.t)
        g = L.globals()
        g["Object"] = L.table(GetNearbyObjects=luafn(L, get_nearby), GetProperty=luafn(L, get_property),
                              SetProperty=luafn(L, set_property))
        g["World"] = L.table(GetCell=luafn(L, get_cell))
        if script == "object":
            g["this"] = proxy(self.scanner)
            g["Game"] = L.table(DebugOut=debug_out, Time=game_time)
        else:
            g["Game"] = L.table(DebugOut=debug_out, Time=game_time, GetObject=luafn(L, get_object))
            g["WorkQueue"] = L.table(Request=luafn(L, request))

    # ---------------------------------------------------------------- the engine's tick
    def step(self):
        self.t += DT
        self.tick += 1
        # doors swing for whoever is waiting at them, and drift shut otherwise
        for d in self.doors:
            opening = d.requested and d.props.get("Mode") != 1
            d.props["Open"] = max(0.0, min(1.0, d.props["Open"] + (DOOR_SPEED if opening else -DOOR_SPEED) * DT))
            d.requested = False
        for m in self.movers:
            if m.alive:
                self.move(m)
        self.assign_jobs()
        for m in self.movers:
            if m.searcher and m.job:
                if m.job.done:
                    # an errand elsewhere ends on its own
                    if self.t >= getattr(m.job, "until", 0):
                        m.job = None
                        m.home_bound = True
                else:
                    self.work(m)
        for c in self.crates:
            carrier = next((m for m in self.movers if m.crate is c), None)
            if carrier:
                c.x, c.y = carrier.x, carrier.y
        # a way through exists when both outer doors are open, or an outer
        # door together with the far side's inner door
        o_in, i_in = self.door_open(self.door_in), self.door_open(self.door_in_inner)
        o_out, i_out = self.door_open(self.door_out), self.door_open(self.door_out_inner)
        # which matters only while someone or something to be searched is in
        # the airlock; with nobody of the kind in reach the doors stand open
        searchable = [m for m in self.movers if m.alive and (m.kind == "Prisoner" or m.props.get("Corrupted"))] + self.crates
        if ((o_in and o_out) or (o_in and i_out) or (o_out and i_in)) and any(self.in_airlock(t.y) for t in searchable):
            self.both_open_ticks += 1

    def move(self, m):
        if self.t < m.delay or self.t < m.retreat_until:
            return
        if m.searcher:
            if m.job is not None or m.home_bound:
                self.move_guard(m)
            return
        if m.done:
            return
        if m.follow is not None and not m.follow.done:
            # an escorted prisoner keeps a step behind the guard
            gap = (m.follow.y - m.y) * m.direction
            if gap > 0.8:
                self.walk(m, m.direction)
            return
        self.walk(m, m.direction)

    def sidestep(self, m, x):
        """Moves someone along their row towards x; true once there."""
        gap = x - m.x
        step = WALK * DT
        if abs(gap) <= step:
            m.x = x
            return True
        m.x += step if gap > 0 else -step
        return False

    def mill(self, m):
        """Someone held up inside drifts off to a spot somewhere in their row."""
        if not self.in_airlock(m.y) or self.door_at(m.y) is not None:
            return
        if m.spot is None:
            lo, hi = self.span(m.y)
            m.spot = self.rng.uniform(lo + 0.1, hi + 0.9)
        self.sidestep(m, m.spot)

    def walk(self, m, direction, target_y=None):
        ny = m.y + direction * WALK * DT
        lane = self.cx + 0.5
        # stepping onto a door tile needs the door open
        cur_door = self.door_at(m.y)
        next_door = self.door_at(ny)
        if next_door is not None and next_door is not cur_door:
            if self.door_open(next_door) and m.x != lane:
                # a door is only as wide as its column
                m.spot = None
                self.sidestep(m, lane)
                return True
            if not self.door_open(next_door):
                next_door.requested = True
                if next_door.props.get("Mode") != 1:
                    self.mill(m)
                if next_door.props.get("Mode") == 1:
                    # the game routes nobody through a door locked shut: a
                    # guard's job fails within seconds and goes back on the
                    # queue, and anyone else gives up for a while
                    m.blocked += DT
                    if m.blocked >= LOCK_GIVE_UP:
                        m.blocked = 0.0
                        if m.job is not None and m.searcher:
                            m.job.guard = None
                            m.job = None
                            m.dest = None
                            m.home_bound = True
                        elif not m.searcher:
                            m.y -= direction * 2
                            m.retreat_until = self.t + RETREAT
                else:
                    m.blocked = 0.0
                return False
        m.spot = None
        was_in = self.in_airlock(m.y)
        m.y = ny
        now_in = self.in_airlock(m.y)
        if now_in and not was_in:
            m.entered_by = "In" if direction > 0 else "Out"
            m.searches = 0
        if was_in and not now_in:
            leaving_by = "In" if direction < 0 else "Out"
            if leaving_by != m.entered_by:
                m.crossed = True
                if m.carrying:
                    self.violations.append("%s %d crossed at %.1f carrying contraband (searches %d)" % (m.kind, m.id, self.t, m.searches))
                if m.crate is not None and m.crate.carrying:
                    self.violations.append("crate %d crossed at %.1f carrying contraband" % (m.crate.id, self.t))
        end = self.n + 2 + FAR if direction > 0 else -3 - FAR
        if not m.searcher and ((direction > 0 and m.y >= end) or (direction < 0 and m.y <= end)):
            m.done = True
            m.finished_at = self.t
            m.alive = False
            if m.crate is not None:
                self.crates.remove(m.crate)
        return True

    # ---------------------------------------------------------------- guards and jobs
    def assign_jobs(self):
        pending = [j for j in self.jobs if not j.done and j.guard is None]
        if not pending:
            return
        for j in pending:
            idle = [g for g in self.movers if g.kind in ("Guard", "ArmedGuard") and g.alive and g.job is None
                    and g.searcher and self.t >= g.delay]
            if not idle:
                return
            # the nearest idle guard takes the oldest job
            g = min(idle, key=lambda g: abs(g.y - j.target.y))
            g.job = j
            g.home_bound = False
            j.guard = g

    def move_guard(self, g):
        if g.job is not None:
            tx, ty = g.job.target.x, g.job.target.y
            g.dest = (tx, ty)
            if abs(g.y - ty) <= REACH:
                # level with them: across the row to their side
                if abs(g.x - tx) > REACH and not g.job.done:
                    if self.door_at(g.y) is None:
                        self.sidestep(g, tx)
                    else:
                        self.walk(g, 1 if ty > g.y else -1)   # out of the doorway first
                return  # adjacent: work happens in work()
            if g.job.done and self.door_at(g.y) is None and not self.in_airlock(g.y):
                return  # an errand elsewhere: out of the corridor, it just waits
            direction = 1 if ty > g.y else -1
            self.walk(g, direction)
        else:
            # done: head home along the corridor, out of whichever door opens
            g.dest = (self.cx + 0.5, g.home_y)
            direction = 1 if g.home_y > g.y else -1
            self.walk(g, direction)
            if abs(g.y - g.home_y) < 0.5:
                g.home_bound = False
                g.dest = None

    def work(self, g):
        j = g.job
        if abs(g.y - j.target.y) > REACH or abs(g.x - j.target.x) > REACH:
            return
        j.work += DT
        interrupt_at = getattr(self, "interrupt_at", None)
        if interrupt_at is not None and j.work >= interrupt_at and not getattr(j, "interrupted", False):
            # the game pulls the guard off onto another job somewhere else:
            # the search fails, its work is lost, and it goes back on the
            # queue for later
            j.interrupted = True
            j.work = 0.0
            j.guard = None
            errand = Job(Thing("Errand", self.cx + 0.5, g.home_y), self.t)
            errand.done = True
            errand.until = self.t + 20
            g.job = errand
            return
        if j.work >= SEARCH_WORK[j.category]:
            j.done = True
            j.target.carrying = False
            j.target.last_searched = self.t
            if hasattr(j.target, "searches"):
                j.target.searches += 1
            g.job = None
            g.home_bound = True
            g.dest = None


class Job:
    _next = 5000

    def __init__(self, target, t):
        self.id = Job._next
        Job._next += 1
        self.target = target
        self.category = "crate" if target.kind in ("Box", "Stack") else "entity"
        self.work = 0.0
        self.done = False
        self.guard = None
        self.created = t


# -------------------------------------------------------------------- scenarios

IN_HOME = -3 - FAR - 2


def out_home(world):
    return world.n + 2 + FAR + 2


def add_guards(world, count, home_y):
    for _ in range(count):
        g = Mover("Guard", world, +1, 0)
        g.y = float(home_y)
        g.home_y = float(home_y)
        g.searcher = True
        g.home_bound = False
        g.done = True          # a guard at home is not walking the corridor
        world.movers.append(g)
    return world


def mealtime(world):
    """Twelve prisoners queue at the entrance, most carrying something."""
    add_guards(world, 2, IN_HOME)
    for i in range(12):
        p = Mover("Prisoner", world, +1, world.rng.uniform(0, 20), carrying=world.rng.random() < 0.6)
        world.movers.append(p)


def both_ways(world):
    """Prisoners come from both sides, with guards stationed on each."""
    add_guards(world, 1, IN_HOME)
    add_guards(world, 1, out_home(world))
    for i in range(6):
        world.movers.append(Mover("Prisoner", world, +1, world.rng.uniform(0, 25), carrying=True))
    for i in range(6):
        world.movers.append(Mover("Prisoner", world, -1, world.rng.uniform(0, 25), carrying=True))


def escort(world):
    """A guard walks a shackled prisoner through, with a cook in the way."""
    add_guards(world, 2, IN_HOME)
    g = Mover("Guard", world, +1, 2)
    g.searcher = False           # busy: on the escort
    g.job = Job(g, 0)            # any job id, not a search
    g.job.done = True            # so no search accounting touches it
    g.home_bound = False
    g.dest = (world.cx, world.n + 2 + FAR)
    g.escort = True
    world.movers.append(g)
    p = Mover("Prisoner", world, +1, 2, carrying=True)
    p.follow = g
    p.y = g.y - 1
    p.props["Shackled"] = True
    world.movers.append(p)
    world.movers.append(Mover("Cook", world, +1, 6))


def deliveries(world):
    """Workmen carry crates through, one crate with contraband inside."""
    add_guards(world, 2, IN_HOME)
    for i, dirty in enumerate((True, False, True)):
        w = Mover("Workman", world, +1, 3 + 8 * i)
        c = Thing("Stack", w.x, w.y)
        c.carrying = dirty
        c.props["CarrierId.i"] = w.id
        w.crate = c
        world.movers.append(w)
        world.crates.append(c)
    world.movers.append(Mover("Prisoner", world, +1, 5, carrying=True))


def staff_only(world):
    """Nobody to search: the room should just pass people through."""
    add_guards(world, 1, IN_HOME)
    for i in range(4):
        world.movers.append(Mover("Janitor", world, +1, i * 3))


def crooked(world):
    """A crooked guard walks through with a prisoner and must be searched too."""
    add_guards(world, 2, IN_HOME)
    bad = Mover("Guard", world, +1, 1, carrying=True)
    bad.props["Corrupted"] = True
    bad.searcher = False
    bad.job = None
    bad.home_bound = False
    world.movers.append(bad)
    world.movers.append(Mover("Prisoner", world, +1, 1.5, carrying=True))


def far_guards(world):
    """Every guard lives beyond the exit, so each search needs the vestibule."""
    add_guards(world, 2, out_home(world))
    for i in range(6):
        world.movers.append(Mover("Prisoner", world, +1, world.rng.uniform(0, 12), carrying=True))


def mixed_far(world):
    """Traffic both ways but every guard beyond the exit: the far side's
    crowd floods in whenever a guard is let in there."""
    add_guards(world, 2, out_home(world))
    for i in range(5):
        world.movers.append(Mover("Prisoner", world, +1, world.rng.uniform(0, 20), carrying=True))
    for i in range(5):
        world.movers.append(Mover("Prisoner", world, -1, world.rng.uniform(0, 20), carrying=True))


def interrupted(world):
    """A guard is pulled off a search part-way through and comes back later."""
    add_guards(world, 1, IN_HOME)
    world.interrupt_at = 4.0
    for i in range(4):
        world.movers.append(Mover("Prisoner", world, +1, world.rng.uniform(0, 8), carrying=True))


SCENARIOS = [mealtime, both_ways, escort, deliveries, staff_only, crooked, far_guards, mixed_far, interrupted]


# -------------------------------------------------------------------- the run

def run(seed, n, scenario, wall=WALLS[0]):
    world = World(seed, n, scenario, wall)
    # two Lua states, as in the game: the scanner's own script, and the mod's
    # world script, which alone is given the work queue
    L = LuaRuntime(unpack_returned_tuples=True)
    world.bind(L, "object")
    L.execute(open(SCRIPT).read())
    g = L.globals()
    W = LuaRuntime(unpack_returned_tuples=True)
    world.bind(W, "world")
    W.execute(open(WORLD_SCRIPT).read())
    wg = W.globals()
    wg.Init()
    g.Create()
    steps = int(HORIZON / DT)
    for _ in range(steps):
        world.step()
        wg.Update("%f" % DT)       # the game hands a world script its time as text
        g.Update(DT)
        if all(m.done for m in world.movers if not m.searcher):
            break
    walkers = [m for m in world.movers if not m.searcher]
    stuck = [m for m in walkers if not m.done]
    for m in stuck:
        world.violations.append("%s %d never got through (at y=%.1f, mode log tail: %s)" % (
            m.kind, m.id, m.y, world.log[-1] if world.log else "-"))
    if world.both_open_ticks:
        world.violations.append("a way through stood open for %d ticks" % world.both_open_ticks)
    crossings = [m.finished_at for m in walkers if m.done]
    return world, crossings


def main():
    failures = 0
    for scenario in SCENARIOS:
        for n in (1, 2, 3, 4):
            worst = 0.0
            reads = writes = requests = ticks = runs = 0
            for wall in WALLS:
                for seed in range(SEEDS):
                    world, crossings = run(seed, n, scenario, wall)
                    if world.violations:
                        failures += 1
                        print("FAIL %s %dx%d seed %d, walls of %s:" % (scenario.__name__, n, n, seed, wall))
                        for v in world.violations[:6]:
                            print("   ", v)
                    worst = max(worst, max(crossings) if crossings else 0)
                    reads += world.reads
                    writes += world.writes
                    requests += world.requests
                    ticks += world.tick
                    runs += 1
            print("%-11s %dx%d  last crossing %5.0fs  reads/tick %5.1f  writes/tick %4.2f  search requests/run %.1f" % (
                scenario.__name__, n, n, worst, reads / ticks, writes / ticks, requests / runs))
    print("failures:", failures)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
