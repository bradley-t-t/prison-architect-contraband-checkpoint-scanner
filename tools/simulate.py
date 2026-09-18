"""Runs the Medical Probe Machine script and the world script against a mock
of the game.

The mock stands in for the engine. Its map is a corridor three tiles wide
with a Strip Search room zoned across the middle of it and no doors
anywhere. People walk the corridor from one end to the other, in both
directions, and keep walking whatever happens to them. Guards take the
search jobs the scripts ask for, walk to the person, stand against them for
the game's ten seconds (five for a crate) and only then clear them. There
is a guard escorting a shackled prisoner, workmen with crates in their arms, which the game will not search until
they are set down, a crate left on the room's floor, and a crooked guard.

Every target carries contraband, and one of the searching guards is crooked
and bribed, whose searches always miss while they are crooked. A Room Scanner
stands in the room.

Each script runs in its own Lua state with only what the game gives that
kind of script. It checks, over every seed, that nobody and no crate gets
more than a step out of the room before their search is done, that nothing
leaves the room still carrying contraband, that everyone
reaches the far end in the end, that with no guards at all the timeout still
gets everyone through, that every prisoner is hurt once a visit and
no more, and that everybody has their own name back afterwards.

Usage: python simulate.py [seeds]   (needs the lupa package)
"""

import math
import os
import random
import sys

from lupa import LuaRuntime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "data", "scripts", "MedicalProbeMachine.lua")
WORLD_SCRIPT = os.path.join(ROOT, "data", "world.lua")
SEEDS = int(sys.argv[1]) if len(sys.argv) > 1 else 12
DT = 1.0 / 30
HORIZON = 60 * 20
WALK = 1.6
SEARCH_WORK = {"entity": 10.0, "crate": 5.0}
SEARCH_COOLDOWN = 30.0
REACH = 0.9
WIDTH = 3
LENGTH = 40
ROOM = (18, 22)              # the room's first and last row
MACHINE = (0, 18)
ROOM_ID = 7
# How far out of the room anyone unsearched may be seen: a quarter second's
# walk between two looks, and a little over.
LEASH = 0.75
INJURY = 0.05


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
        self.job = None
        self.dest = None
        self.last_searched = -1e9
        self.searches = 0
        self.stored = False
        self.goal = None
        self.carrying = None
        self.entered = False
        self.visits = 0
        self.was_inside = False


class Job:
    _next = 1

    def __init__(self, target):
        self.id = Job._next
        Job._next += 1
        self.target = target
        self.guard = None
        self.holding = False
        self.work = 0.0
        self.done = False


def in_room(x, y):
    return 0 <= x < WIDTH and ROOM[0] <= math.floor(y) <= ROOM[1]


class World:
    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.t = 0.0
        self.machine = Thing("MedicalProbeMachine", MACHINE[0] + 0.5, MACHINE[1] + 0.5)
        self.scanner = Thing("RoomScanner", MACHINE[0] + 2.5, MACHINE[1] + 0.5)
        self.missed = 0
        self.movers, self.crates, self.jobs, self.log = [], [], [], []
        self.requests = 0
        self.broken = 0
        self.set_down = 0
        self.failures = []
        for i in range(6):
            self.walker("Prisoner", up=i % 2 == 0, name="Prisoner %d" % i)
        for _ in range(2):
            self.walker("Workman", up=True, crate=True)
        self.walker("Cook", up=False)
        crooked = self.walker("Guard", up=True, name="Bent")
        crooked.props["Corrupted"] = True
        # a guard escorting a shackled prisoner through: carried, like a crate
        escort = self.walker("Guard", up=True)
        inmate = Thing("Prisoner", escort.x, escort.y)
        inmate.props["Name"] = inmate.own = "Escorted"
        inmate.props["CarrierId.i"], inmate.props["Carried"] = escort.id, 5
        escort.carrying = escort.charge = inmate
        escort.job = Job(None)        # an escort is a guard on a job, bound elsewhere
        escort.dest = (escort.x, LENGTH - 1.5)
        self.movers.append(inmate)
        floor = Thing("Stack", 1.5, ROOM[0] + 2.5)
        self.crates.append(floor)
        # ingredients on a cooker in the room: furniture, never to be searched
        shelf = Thing("Stack", 2.5, ROOM[0] + 1.5)
        shelf.props["CarrierId.i"] = 9999
        shelf.stored = True
        self.crates.append(shelf)
        self.guards = []
        for i in range(3):
            g = Thing("Guard", 0.5 + i, 4.5)
            g.home = (g.x, g.y)
            g.fed_up = False
            if i == 0:
                g.props["Corrupted"] = True
            self.guards.append(g)
            self.movers.append(g)

    def walker(self, kind, up, name=None, crate=False):
        x = 0.5 + self.rng.randrange(WIDTH)
        m = Thing(kind, x, 1.5 if up else LENGTH - 1.5)
        m.goal = LENGTH - 1.5 if up else 1.5
        m.delay = self.rng.uniform(0, 60)
        if name:
            m.props["Name"] = name
            m.own = name
        if crate:
            c = Thing("Box", m.x, m.y)
            c.props["CarrierId.i"], c.props["Carried"] = m.id, 5
            m.carrying = c
            self.crates.append(c)
        self.movers.append(m)
        return m

    def objects(self):
        yield self.machine
        yield self.scanner
        for m in self.movers:
            yield m
        for c in self.crates:
            yield c

    def bind(self, L, script):
        world = self

        def proxy(obj):
            def index(t, k):
                if k == "Id":
                    return L.table(i=obj.id, u=1)
                if k == "Pos":
                    return L.table(x=obj.x, y=obj.y)
                return obj.props.get(k)

            def newindex(t, k, v):
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
            out = L.table()
            if len(args) == 3:
                centre, kind, rng = resolve(args[0]), args[1], args[2]
            elif script == "object":
                centre, kind, rng = world.machine, args[0], args[1]
            else:
                centre = None
            if centre is None:
                return out
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
            o, key = resolve(args[0]), args[1]
            if o is None:
                return None
            if key == "JobId":
                return o.job.id if o.job else -1
            if key == "Dest":
                return L.table(x=o.dest[0], y=o.dest[1]) if o.dest else None
            if key == "CarrierId.i":
                return o.props.get("CarrierId.i", -1)
            return o.props.get(key)

        def set_property(*args):
            o, key, value = resolve(args[0]), args[1], args[2]
            if o is None:
                return
            if key == "CarrierId.i" and float(value) < 0:
                for m in world.movers:
                    if m.carrying is o:
                        m.carrying = None
                        world.set_down += 1
                for j in world.jobs:
                    if j.target is o and not j.done and j.holding:
                        # torn out of the hands of the guard searching it
                        j.work, j.holding = 0.0, False
                        world.broken += 1
            if key == "Pos.x":
                o.x = float(value)
            elif key == "Pos.y":
                o.y = float(value)
            else:
                o.props[key] = value

        def get_object(name):
            for o in world.objects():
                if o.props.get("Name") == name:
                    return proxy(o)
            return None

        def request(kind, tbl):
            assert kind == "SearchObject"
            world.requests += 1
            o = resolve(tbl)
            if o is None or any(j.target is o and not j.done for j in world.jobs):
                return
            if world.t - o.last_searched < SEARCH_COOLDOWN:
                return
            if o.stored:
                world.failures.append("%.1f a search was asked for a stack stored on a shelf" % world.t)
            world.jobs.append(Job(o))

        def get_cell(x, y):
            return L.table(Room=L.table(i=ROOM_ID if in_room(x, y) else -1, u=1))

        debug_out = luafn(L, lambda s: world.log.append("%7.2f %s" % (world.t, s)))
        g = L.globals()
        g["unpack"] = L.eval("table.unpack")
        g["Object"] = L.table(GetNearbyObjects=luafn(L, get_nearby), GetProperty=luafn(L, get_property),
                              SetProperty=luafn(L, set_property), ClearRouting=luafn(L, lambda o: None))
        g["World"] = L.table(GetCell=luafn(L, get_cell))
        if script == "object":
            g["this"] = proxy(self.machine)
            g["Game"] = L.table(DebugOut=debug_out)
        else:
            # No campaign commands: in the game they crash outside the campaign,
            # so a script that reaches for one fails here too.
            g["Game"] = L.table(DebugOut=debug_out, GetObject=luafn(L, get_object))
            g["WorkQueue"] = L.table(Request=luafn(L, request))

    def step_towards(self, m, tx, ty, speed=WALK):
        dx, dy = tx - m.x, ty - m.y
        d = math.hypot(dx, dy)
        if d < 1e-6:
            return True
        s = min(d, speed * DT)
        m.x += dx / d * s
        m.y += dy / d * s
        return d <= s

    def step(self):
        self.t += DT
        for j in self.jobs:
            if j.done:
                continue
            if j.guard is None:
                free = [g for g in self.guards if g.job is None and g is not j.target]
                if free:
                    j.guard = min(free, key=lambda g: math.hypot(g.x - j.target.x, g.y - j.target.y))
                    j.guard.job = j
            if j.guard is not None:
                g, o = j.guard, j.target
                g.dest = (o.x, o.y)
                if math.hypot(g.x - o.x, g.y - o.y) > REACH:
                    self.step_towards(g, o.x, o.y, WALK * 1.5)
                elif o.props.get("CarrierId.i", -1) not in (-1, None, g.id):
                    pass        # in someone else's arms: the game's search fails
                else:
                    # a guard holds whatever he searches for as long as it takes
                    if not j.holding:
                        j.holding = True
                        o.props["CarrierId.i"], o.props["Carried"] = g.id, 4
                        g.props["Carrying.i"] = o.id
                    j.work += DT
                    kind = "crate" if o.kind in ("Box", "Stack") else "entity"
                    if j.work >= SEARCH_WORK[kind]:
                        j.done, j.holding = True, False
                        o.props["CarrierId.i"], o.props["Carried"] = -1, 0
                        g.props["Carrying.i"] = -1
                        o.last_searched = self.t
                        miss = g.props.get("Corrupted") is True or g.fed_up
                        if miss:
                            self.missed += 1
                        else:
                            o.contraband = False
                            o.searches += 1
                        g.job, g.dest = None, None
        for g in self.guards:
            if g.job is None:
                self.step_towards(g, *g.home)
        for m in self.movers:
            if m.goal is None or self.t < m.delay:
                continue
            held = any(j.target is m and j.guard is not None and not j.done
                       and math.hypot(j.guard.x - m.x, j.guard.y - m.y) <= REACH for j in self.jobs)
            if getattr(m, "charge", None) is not None and m.carrying is None:
                held = True
            if not held:
                self.step_towards(m, m.x, m.goal)
            charge = getattr(m, "charge", None)
            if charge is not None and m.carrying is None:
                # the escort waits by a prisoner it was made to let go of,
                # and takes them on again once they have been searched
                held = True
                m.let_go_at = getattr(m, "let_go_at", self.t)
                done = charge.searches > 0 and self.t - charge.last_searched > 2
                waited = self.t - m.let_go_at > 100
                if waited or (done and not any(j.target is charge and not j.done for j in self.jobs)):
                    m.carrying = charge
                    charge.props["CarrierId.i"], charge.props["Carried"] = m.id, 5
                    m.x, m.y = charge.x, charge.y
            if m.carrying is not None:
                m.carrying.x, m.carrying.y = m.x, m.y
        self.check()

    def target(self, o):
        if o.stored:
            return False
        return o.kind in ("Prisoner", "Box", "Stack") or o.props.get("Corrupted") is True

    def check(self):
        for o in list(self.movers) + self.crates:
            inside = in_room(o.x, o.y)
            # Coming in is a new visit only from well outside: being put
            # back from a step beyond the edge is the same visit carrying on.
            away = max(ROOM[0] - o.y, o.y - (ROOM[1] + 1))
            if away > 2 * LEASH:
                o.far = True
            if inside and not o.was_inside and getattr(o, "far", True):
                o.far = False
                o.visits += 1
                o.entered = True
                o.searches_at_entry = o.searches
                o.contraband = self.target(o)
                if self.t - o.last_searched < SEARCH_COOLDOWN:
                    # searched moments ago: the game would refuse another, so
                    # walking straight through is right
                    o.searches_at_entry = o.searches - 1
                    o.contraband = False
            o.was_inside = inside
            if not o.entered or inside or not self.target(o):
                continue
            if o.searches > getattr(o, "searches_at_entry", 0):
                if getattr(o, "contraband", False):
                    self.failures.append("%.1f %s %d left with contraband" % (self.t, o.kind, o.id))
                continue
            out = max(ROOM[0] - o.y, o.y - (ROOM[1] + 1))
            if out > LEASH:
                self.failures.append("%.1f %s %d unsearched %.2f tiles out of the room" % (self.t, o.kind, o.id, out))
                o.entered = False


def run(seed, guards=True):
    Thing._next, Job._next = 100, 1
    world = World(seed)
    if not guards:
        # nobody to search anyone: only the timeout gets people through
        for g in world.guards:
            world.movers.remove(g)
        world.guards = []
    obj, wld = LuaRuntime(unpack_returned_tuples=True), LuaRuntime(unpack_returned_tuples=True)
    world.bind(obj, "object")
    world.bind(wld, "world")
    obj.execute(open(SCRIPT).read())
    wld.execute(open(WORLD_SCRIPT).read())
    obj.globals()["Create"]()
    wld.globals()["Init"]()
    update, world_update = obj.globals()["Update"], wld.globals()["Update"]
    while world.t < HORIZON:
        world.step()
        update(DT)
        world_update(str(DT))
    failures = world.failures
    if not guards:
        return [("%s %d never arrived without guards (y %.1f)" % (m.kind, m.id, m.y))
                for m in world.movers if m.goal is not None and abs(m.y - m.goal) > 0.1], 0, world.requests
    for m in world.movers:
        if m.goal is not None and abs(m.y - m.goal) > 0.1:
            failures.append("%s %d never arrived (y %.1f)" % (m.kind, m.id, m.y))
        if hasattr(m, "own") and m.props.get("Name") != m.own:
            failures.append("%s %d is named %r, not %r" % (m.kind, m.id, m.props.get("Name"), m.own))
        if m.kind == "Prisoner" and m.goal is None and abs(m.y - (LENGTH - 1.5)) > 0.1:
            failures.append("the escorted prisoner never arrived (y %.1f)" % m.y)
        if m.kind == "Prisoner":
            hurt = m.props.get("Damage") or 0
            if abs(hurt - INJURY * m.visits) > 1e-6 or m.visits != 1:
                failures.append("Prisoner %d hurt %.2f over %d visits" % (m.id, hurt, m.visits))
    for g in world.guards:
        if g.props.get("Name"):
            failures.append("guard %d is still named %r" % (g.id, g.props.get("Name")))
    bent = world.guards[0]
    if bent.props.get("Corrupted") is not True or bent.props.get("Exposed") is not True:
        failures.append("the crooked guard ended corrupted=%r exposed=%r" % (
            bent.props.get("Corrupted"), bent.props.get("Exposed")))
    if world.broken:
        failures.append("%d searches broken by taking the person out of the guard's hands" % world.broken)
    if world.set_down != 3:
        failures.append("%d things set down, not 3" % world.set_down)
    if world.machine.props.get("Name"):
        failures.append("the machine is still calling")
    searched = sum(1 for o in list(world.movers) + world.crates if o.searches)
    return failures, searched, world.requests


def main():
    total = 0
    stuck, _, _ = run(0, guards=False)
    total += len(stuck)
    print("no guards  failures %d" % len(stuck))
    for f in stuck[:6]:
        print("    " + f)
    for seed in range(SEEDS):
        failures, searched, requests = run(seed)
        total += len(failures)
        print("seed %2d  searched %2d  requests %3d  failures %d" % (seed, searched, requests, len(failures)))
        for f in failures[:6]:
            print("    " + f)
    print("failures: %d" % total)
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
