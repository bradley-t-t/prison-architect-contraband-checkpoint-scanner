-- Strip Search Scanner. It runs the room it stands in as a search airlock.
--
-- Each side of the room has a Strip Search Entrance or Exit on the outer
-- wall, a lobby, and a second door of the same kind between the lobby and
-- the room. Every door is a plain door that the scanner holds
-- open or shut itself, every tick, so the engine never gets to open one on
-- its own. People come in through one side's pair of doors; once nobody new
-- has stepped in for a moment the scanner shuts them, and with everything
-- shut it asks the game for a guard search of everyone inside who could be
-- carrying anything: every prisoner, any guard the game knows to be crooked,
-- and any crate on the floor or in someone's arms. The game's own search is
-- the one thing that takes contraband off a person, so that is what is used.
-- A guard comes. One arriving on the side people came in by is let straight
-- in. One arriving on the far side is let into that side's lobby first,
-- the outer door shut behind them, and the inner door opened, so nobody
-- inside can slip out past them. When every search is done the far side's
-- doors open and the room empties. Anyone who walks in while a door is open
-- is unsearched, and the doors on the other side stay shut until they have
-- been searched too, so nothing crosses the room without a search between.
--
-- The room works in both directions. Someone waiting at the far side while
-- the room is empty is let in there and searched on the way back. A side
-- built with a single door works too, but a guard can only be let in there
-- when everyone unsearched inside came in that way.
--
-- The scanner cannot see what a person carries, and the game reports nothing
-- when a search ends, so searches are watched instead. A guard's job id is
-- readable, and a search is one job: every moment a guard on a job stands
-- against someone still to be searched, with nowhere else to go, is work on
-- that job, and a job that ends after a search's worth of work was that
-- search, credited to whoever the guard stood against. A guard whose
-- destination is somewhere else, such as one escorting a prisoner on
-- through the room, is not counted. Nobody leaves by the far side until
-- everyone who came in has a search to their name.
--
-- The game gives its work queue to a mod's world script only, so the search
-- itself is asked for by data/world.lua: this script marks who is to be
-- searched and the world script does the asking. See CALL_NAME below.
--
-- Two of the game's own rules are used against the doors. Someone whose
-- route runs through a door that is merely held shut waits at it for ever,
-- so that is how the doors are held. A door the game itself has locked shut
-- is left out of routing altogether: a guard stuck outside with a search
-- job loses that job within seconds and the game hands it to whoever can
-- get there, which is how a guard already inside ends up doing it.

local SCAN_INTERVAL = 0.25
-- How often the room's shape and its doors are looked up again.
local LAYOUT_RECHECK = 5
-- How far from the scanner the doors and the room may reach.
local DOOR_REACH = 10
-- A guard is searching someone when standing this close to them.
local SEARCH_REACH = 1.6
-- A searching guard's destination is the person; a guard whose destination
-- is further away than this is on some other job. A destination the engine
-- has left unset does not count against the guard.
local DEST_REACH = 1.8
-- The game's search takes ten seconds of work on a person and five on a
-- crate, and a dog handler works five times as fast as a guard. A job that
-- ends after that much work, less a look's worth of slack, was a search.
local SEARCH_TIME_ENTITY = 10
local SEARCH_TIME_CRATE = 5
local SEARCH_RATE = { DogHandler = 5 }
local SEARCH_SLACK = 1
-- Someone inside who a look misses is kept on the books this long; someone
-- seen outside is off them at once.
local SEEN_GRACE = 1
-- Seconds without a newcomer before the intake doors shut, the longest they
-- stay open once someone is inside, and the point at which they shut even
-- with someone still in a doorway.
local LOAD_GRACE = 3
local LOAD_MAX = 12
local LOAD_FORCE = 24
-- Doors opened to let a guard in shut this long after nobody is coming in,
-- and the same guard is not let in again for a while.
local ADMIT_GRACE = 3
local ADMIT_COOLDOWN = 15
-- A guard on a job who has waited this long at a door that cannot open for
-- them has that door locked shut in the game's own sense, which takes it out
-- of the map for routing: the guard's route fails, the game drops the job
-- back on the queue within seconds, and whoever can reach the person, such
-- as a guard already inside, picks it up. A door held shut any other way is
-- waited at for ever. The door is a plain door again the moment the guard
-- gives up or the door is to open.
local LOCK_AFTER = 6
local MODE_NORMAL = 0
local MODE_LOCKED_SHUT = 1
-- The game gives its work queue to a mod's world script and to no object's
-- own script, so this script cannot ask for a search itself. It names the
-- person instead: every object has a Name a script can look it up by. The
-- person is named MARK_PREFIX and their id, this scanner is named CALL_NAME,
-- and the mod's data/world.lua finds the scanner by that name, asks the game
-- to search everyone near it carrying the mark, and clears both names. A
-- cleared mark is the word that the search has been asked for.
local CALL_NAME = "StripSearchCall"
local MARK_PREFIX = "StripSearchTarget"
-- Someone waiting at the far side of an empty room this long is let in there.
local WAIT_SWITCH = 2
-- A search the game has not started in this long is asked for again. The
-- game refuses a repeat request within thirty seconds of a search.
local RETRY_AFTER = 40
-- While the room empties, once nobody has left for RELEASE_GRACE seconds
-- whoever is left is taken to want something else: unsearched newcomers a
-- search, cleared people the other side. The open side is never swapped
-- sooner than RELEASE_SWAP seconds after it opened.
local RELEASE_GRACE = 3
local RELEASE_SWAP = 8
-- How far from a door's tile someone counts as waiting at it.
local DOOR_WAIT = 1.8
-- A door counts as shut for changing over once the engine reports it below
-- this. The engine itself treats a door as open from 0.75.
local SHUT_AT = 0.1
-- Sprites: 0 idle, 1 and 2 the scan pulse, 3 all clear.
local FRAME_IDLE = 0
local FRAME_SCAN_A = 1
local FRAME_SCAN_B = 2
local FRAME_CLEAR = 3
local PULSE_INTERVAL = 0.4
local MAX_ROOM_TILES = 256
-- A guard or a workman is no business of this room's. With nobody in reach
-- who could carry anything, and with the room not yet finished, every door
-- stands open; the moment a prisoner or a crate comes within reach they all
-- shut and the airlock takes over. A door the player has locked open is left
-- alone altogether.
local MODE_LOCKED_OPEN = 2
local DEBUG = false

local DOOR_TYPES = { In = "StripSearchDoorIn", Out = "StripSearchDoorOut" }
local SIDES = { "In", "Out" }
local OTHER_SIDE = { In = "Out", Out = "In" }
local WHICH = { "inner", "outer" }

-- Everyone who can walk through a door.
local MOVERS = {
    "Prisoner", "Guard", "ArmedGuard", "RiotGuard", "Sniper", "DogHandler", "Dog",
    "Workman", "Cook", "Doctor", "Janitor", "Gardener", "Farmer", "Foreman",
    "Chief", "Warden", "Accountant", "Lawyer", "Psychologist", "Psychiatrist",
    "Orderly", "Paramedic", "Fireman", "Soldier", "EliteOps", "Teacher",
    "FireSafetyTeacher", "SpiritualLeader", "Visitor", "ParoleOfficer",
    "ParoleLawyer", "AppealsLawyer", "AppealsMagistrate", "ExecutionWitness",
    "Actor", "CivilianChild", "RehabilitatedPrisoner", "RestaurantCustomer",
    "TruckDriver", "EntityDeliveryMan", "GritterDriver", "Zombie", "Avatar",
}
-- The staff who carry out a search.
local SEARCHERS = { Guard = true, ArmedGuard = true, RiotGuard = true, DogHandler = true }
-- The only things the game lets contraband travel in.
local CRATES = { "Box", "Stack" }

local Find = Object.GetNearbyObjects
local Get = Object.GetProperty
local Set = Object.SetProperty

local scanTimer = SCAN_INTERVAL
local layoutTimer = LAYOUT_RECHECK
local pulseTimer = 0
local frame = -1
local clock = 0

-- The room: its tiles keyed "x,y" to "chamber" or the side whose lobby they
-- are, and how far it reaches from the scanner.
local roomTiles = {}
local finished = false
local idle = false
local roomReach = 3
-- The doors by side: outer is the door to the outside, inner the door
-- between the lobby and the room, nil when the side has one door. Each door
-- is { obj = table, tx = tile x, ty = tile y, ax and ay = the way out of the
-- room through it, open = the engine's last reported openness, want = what
-- it is held at, lock = whether it is to be locked shut, locked = the mode
-- last written }.
local doors = { In = {}, Out = {} }
-- How long a guard has waited at each side's outer door without being let in.
local stuck = { In = 0, Out = 0 }

-- Where the airlock is in its cycle:
--   intake   one side open, people coming in (side = that side)
--   sealed   everything shut, searches under way
--   admit    a side opened for a guard while sealed (side = that side);
--            stage "full" opens both doors, "outer" then "inner" one at a
--            time through the lobby
--   release  one side open for cleared people to leave (side = that side)
local mode = "intake"
local side = "In"
local stage = nil
local modeTimer = 0
local lastEntrant = 0
local lastLeft = 0
local waitTimer = { In = 0, Out = 0 }
local admitted = {}
-- Everything shut and the next mode waiting for the engine to report it.
local closing = nil

-- Everyone inside or in a doorway, keyed by object id:
--   { id, obj, kind, x, y, where ("chamber", "lobby" or "doorway"),
--     zone (side of a lobby or doorway), cameIn (a side, or UNKNOWN),
--     target, searched, requested (clock), seen (clock) }
local occupants = {}
-- Crates inside, keyed by object id, with the same fields.
local crates = {}
-- Someone first seen with every door shut came in by nobody knows which
-- side, so until searched they keep every door shut.
local UNKNOWN = "?"
-- Each guard's job as last seen, keyed by guard id: { id = the job id, work
-- = work done against someone still to be searched }. A job that ends
-- after a search's worth of work was that search.
local guardJobs = {}
-- When a search was last seen under way, and when they were last asked for.
local lastProgress = 0
local lastRequest = 0

-- What the last scan saw around the room.
local scan = { guards = {}, waiting = { In = 0, Out = 0 }, doorway = { In = 0, Out = 0 } }

local function log(text)
    if DEBUG then
        Game.DebugOut("StripSearch " .. tostring(this.Id.i) .. ": " .. text)
    end
end

local function showFrame(n)
    if frame ~= n then
        frame = n
        this.SubType = n
    end
end

local function nearby(kind, range)
    return Find(kind, range) or {}
end

local function number(v, fallback)
    local n = tonumber(v)
    if n == nil then
        return fallback
    end
    return n
end

local function objectId(obj)
    local id = obj.Id
    if id == nil then
        return nil
    end
    return tonumber(id.i)
end

local function position(obj)
    local pos = obj.Pos
    if pos == nil then
        return nil, nil
    end
    return tonumber(pos.x), tonumber(pos.y)
end

local function tileKey(x, y)
    return math.floor(x) .. "," .. math.floor(y)
end

local function distance(ax, ay, bx, by)
    local dx, dy = ax - bx, ay - by
    return math.sqrt(dx * dx + dy * dy)
end

-- ---------------------------------------------------------------- layout

local function cellRoom(cell)
    if cell == nil then
        return -1
    end
    local room = cell.Room
    if type(room) == "table" then
        return number(room.i, -1)
    end
    return number(cell["Room.i"], -1)
end

-- The way out of the room through a door, as a step of one tile: straight
-- away from the scanner, along whichever line the door is further down.
local function wayOut(door, sx, sy)
    local dx, dy = door.tx + 0.5 - sx, door.ty + 0.5 - sy
    if math.abs(dx) > math.abs(dy) then
        return dx < 0 and -1 or 1, 0
    end
    return 0, dy < 0 and -1 or 1
end

-- The two nearest doors of a side's kind: the nearer is the inner door and
-- the further the outer, unless there is only one, which is then the outer.
local function findDoors()
    local sx, sy = position(this)
    for _, s in ipairs(SIDES) do
        local found = {}
        for door, _ in pairs(nearby(DOOR_TYPES[s], DOOR_REACH)) do
            local dx, dy = position(door)
            if dx ~= nil then
                found[#found + 1] = { obj = door, tx = math.floor(dx), ty = math.floor(dy),
                                      dist = distance(sx, sy, dx, dy), open = 0, want = false,
                                      lock = false, locked = nil }
            end
        end
        table.sort(found, function(a, b) return a.dist < b.dist end)
        local was = doors[s]
        local new = {}
        if #found >= 2 then
            new.inner, new.outer = found[1], found[2]
        elseif #found == 1 then
            new.outer = found[1]
        end
        for _, which in ipairs(WHICH) do
            if new[which] ~= nil then
                new[which].ax, new[which].ay = wayOut(new[which], sx, sy)
            end
            if new[which] ~= nil and was[which] ~= nil and objectId(was[which].obj) == objectId(new[which].obj) then
                local old = was[which]
                new[which].open, new[which].want = old.open, old.want
                new[which].lock, new[which].locked = old.lock, old.locked
            end
        end
        doors[s] = new
    end
end

local function eachDoor(f)
    for _, s in ipairs(SIDES) do
        for _, which in ipairs(WHICH) do
            local door = doors[s][which]
            if door ~= nil then
                f(s, which, door)
            end
        end
    end
end

-- The side and door a tile holds, if any.
local function doorwayAt(x, y)
    local tx, ty = math.floor(x), math.floor(y)
    for _, s in ipairs(SIDES) do
        for _, which in ipairs(WHICH) do
            local door = doors[s][which]
            if door ~= nil and door.tx == tx and door.ty == ty then
                return s, which
            end
        end
    end
    return nil
end

-- The chamber is every tile zoned like the scanner's own, reached without
-- crossing a door; an unzoned scanner falls back to the block of tiles
-- between its inner doors. A side's lobby is the tiles between its two
-- doors, and across the width of the room between those doors' own rows.
local function mapRoom()
    local sx, sy = position(this)
    local ox, oy = math.floor(sx), math.floor(sy)
    local tiles, count, reach = {}, 0, 1
    local function add(x, y, what)
        local key = tileKey(x, y)
        if tiles[key] == nil then
            tiles[key] = what
            count = count + 1
            reach = math.max(reach, math.abs(x - ox), math.abs(y - oy))
        end
    end
    local function block(a, b, what)
        for x = math.min(a.tx, b.tx), math.max(a.tx, b.tx) do
            for y = math.min(a.ty, b.ty), math.max(a.ty, b.ty) do
                if doorwayAt(x, y) == nil then
                    add(x, y, what)
                end
            end
        end
    end
    local home = cellRoom(World.GetCell(ox, oy))
    if home >= 0 then
        local queue = { { ox, oy } }
        add(ox, oy, "chamber")
        local head = 1
        while head <= #queue and count < MAX_ROOM_TILES do
            local x, y = queue[head][1], queue[head][2]
            head = head + 1
            for _, step in ipairs({ { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } }) do
                local nx, ny = x + step[1], y + step[2]
                if tiles[tileKey(nx, ny)] == nil and doorwayAt(nx, ny) == nil
                    and cellRoom(World.GetCell(nx, ny)) == home then
                    add(nx, ny, "chamber")
                    queue[#queue + 1] = { nx, ny }
                end
            end
        end
    else
        local a = doors.In.inner or doors.In.outer
        local b = doors.Out.inner or doors.Out.outer
        if a ~= nil and b ~= nil then
            block(a, b, "chamber")
        end
    end
    if count == 0 then
        add(ox, oy, "chamber")
    end
    -- A lobby is as wide as the room: every tile between its two doors' own
    -- rows, across the room's width.
    local function widen(s)
        local inner, outer = doors[s].inner, doors[s].outer
        local ax, ay = outer.ax, outer.ay
        local depth = (outer.tx - inner.tx) * ax + (outer.ty - inner.ty) * ay
        local lo, hi = 0, 0
        for key, what in pairs(tiles) do
            if what == "chamber" then
                local x, y = string.match(key, "^(-?%d+),(-?%d+)$")
                local across = (tonumber(x) - inner.tx) * -ay + (tonumber(y) - inner.ty) * ax
                lo, hi = math.min(lo, across), math.max(hi, across)
            end
        end
        for along = 1, depth - 1 do
            for across = lo, hi do
                local x, y = inner.tx + along * ax + across * -ay, inner.ty + along * ay + across * ax
                if doorwayAt(x, y) == nil then
                    add(x, y, s)
                end
            end
        end
    end
    for _, s in ipairs(SIDES) do
        if doors[s].inner ~= nil then
            block(doors[s].inner, doors[s].outer, s)
            widen(s)
        end
    end
    roomTiles, roomReach = tiles, reach
    finished = home >= 0 and doors.In.outer ~= nil and doors.Out.outer ~= nil
end

local function relayout()
    findDoors()
    mapRoom()
    if DEBUG then
        local n = 0
        for _ in pairs(roomTiles) do
            n = n + 1
        end
        local function sideText(s)
            if doors[s].outer == nil then
                return "no door"
            end
            return doors[s].inner and "two doors" or "one door"
        end
        log("layout: " .. n .. " tiles, reach " .. roomReach
            .. ", In " .. sideText("In") .. ", Out " .. sideText("Out"))
    end
end

-- "chamber", a lobby's side, or nil for a tile outside the room.
local function insideAt(x, y)
    return roomTiles[tileKey(x, y)]
end

-- How far a spot lies out past a door, along the way out through it.
local function past(door, x, y)
    return (x - door.tx - 0.5) * door.ax + (y - door.ty - 0.5) * door.ay
end

-- Whether a spot lies out past the wall a side's outer door stands in. The
-- only way there from inside is through that door.
local function pastOuterDoor(x, y)
    for _, s in ipairs(SIDES) do
        local door = doors[s].outer
        if door ~= nil and past(door, x, y) > 0.5 then
            return true
        end
    end
    return false
end

-- Where someone already on the books is when the map does not know the
-- tile they stand on: still inside, unless they are out past an outer door.
-- The map can fall short of the room, with a lobby whose walls it could not
-- make out or a room zoned only in part, and nobody is to drop off the books
-- by stepping onto a tile it missed. They are in the lobby of the side whose
-- inner door they are out past, and otherwise in the chamber.
local function stillInsideAt(x, y)
    if doors.In.outer == nil and doors.Out.outer == nil then
        return nil
    end
    if pastOuterDoor(x, y) then
        return nil
    end
    for _, s in ipairs(SIDES) do
        local door = doors[s].inner
        if door ~= nil and past(door, x, y) > 0.5 then
            return s
        end
    end
    return "chamber"
end

local function nearOuterDoor(s, x, y)
    local door = doors[s].outer
    if door == nil then
        return false
    end
    return distance(x, y, door.tx + 0.5, door.ty + 0.5) <= DOOR_WAIT
end

-- A side that has a door; with one side missing the other serves both ways.
local function existing(s)
    if doors[s].outer == nil and doors[OTHER_SIDE[s]].outer ~= nil then
        return OTHER_SIDE[s]
    end
    return s
end

-- ---------------------------------------------------------------- doors

local function pinDoors()
    eachDoor(function(_, _, door)
        -- A door is held open by the game's own lock, which keeps it open
        -- without a gap; an openness written from here lasts only until the
        -- door's next move, and a door held that way flickers. Shut, it is
        -- a plain door whose openness is written back to nothing, or one
        -- locked shut. "locked" is the mode last written: a door found
        -- locked open that this script did not lock is the player's, and
        -- is left to them until they unlock it.
        door.open = number(Get(door.obj, "Open"), 0)
        local now = number(Get(door.obj, "Mode"), MODE_NORMAL)
        if now == MODE_LOCKED_OPEN and door.locked ~= MODE_LOCKED_OPEN then
            return
        end
        local wanted = door.want and MODE_LOCKED_OPEN or (door.lock and MODE_LOCKED_SHUT or MODE_NORMAL)
        if now ~= wanted then
            Set(door.obj, "Mode", wanted)
        end
        door.locked = wanted
        if not door.want and door.open > 0 then
            Set(door.obj, "Open", 0)
        end
    end)
end

local function unlockDoors()
    eachDoor(function(_, _, door)
        door.lock = false
    end)
    stuck.In, stuck.Out = 0, 0
end

local function doorShut(door)
    return door == nil or door.open < SHUT_AT
end

local function holdShut()
    eachDoor(function(_, _, door)
        door.want = false
    end)
end

-- True once the engine reports every door shut.
local function allShut()
    local shut = true
    eachDoor(function(_, _, door)
        if not doorShut(door) then
            shut = false
        end
    end)
    return shut
end

-- Holds one door open. The other side is shut first, and this door waits
-- for the engine to report it so.
local function holdOpen(s, which)
    local clear = true
    for _, w in ipairs(WHICH) do
        local door = doors[OTHER_SIDE[s]][w]
        if door ~= nil then
            door.want = false
            if not doorShut(door) then
                clear = false
            end
        end
    end
    local door = doors[s][which]
    if door ~= nil and clear then
        door.want = true
    end
end

-- Opens a whole side: its outer door, and its inner door if it has one.
local function holdSideOpen(s)
    holdOpen(s, "outer")
    if doors[s].inner ~= nil then
        holdOpen(s, "inner")
    end
end

-- Holds both inner doors open with both outer doors shut, so a guard inside
-- can reach anyone in a lobby while nobody can leave.
local function holdInnersOpen()
    for _, s in ipairs(SIDES) do
        local door = doors[s].outer
        if door ~= nil then
            door.want = false
            if not doorShut(door) then
                return
            end
        end
    end
    for _, s in ipairs(SIDES) do
        if doors[s].inner ~= nil then
            doors[s].inner.want = true
        end
    end
end

-- Shuts everything and enters the next mode once the engine agrees.
local function shutThen(newMode, newSide, newStage)
    holdShut()
    closing = { mode = newMode, side = newSide, stage = newStage }
end

-- ---------------------------------------------------------------- people

local function isTarget(kind, obj)
    if kind == "Prisoner" then
        return true
    end
    if kind == "Guard" then
        return Get(obj, "Corrupted") == true or Get(obj, "Exposed") == true
    end
    return false
end

local function isDead(obj)
    return number(Get(obj, "Damage"), 0) >= 1
end

local function nameOf(obj)
    local name = Get(obj, "Name")
    if type(name) ~= "string" then
        return ""
    end
    return name
end

local function isMark(name)
    return string.sub(name, 1, #MARK_PREFIX) == MARK_PREFIX
end

-- Marks someone for the world script to have searched. Whatever name they
-- had is kept to give back.
local function requestSearch(record)
    local name = nameOf(record.obj)
    if not isMark(name) then
        record.ownName = name
        Set(record.obj, "Name", MARK_PREFIX .. tostring(record.id))
    end
    record.marked = clock
    record.requested = nil
    log("search wanted for " .. record.kind .. " " .. tostring(record.id))
end

-- Takes the mark off again and gives back the name it replaced.
local function unmark(record)
    if record.marked == nil then
        return
    end
    record.marked = nil
    local name = nameOf(record.obj)
    local own = record.ownName or ""
    if isMark(name) or (own ~= "" and name == "") then
        Set(record.obj, "Name", own)
    end
end

-- True once the world script has taken the mark off, which it does only
-- after asking the game for the search.
local function acknowledged(record)
    if isMark(nameOf(record.obj)) then
        return false
    end
    record.requested = clock
    unmark(record)
    log("search requested for " .. record.kind .. " " .. tostring(record.id))
    return true
end

-- The side someone came in by is the one open at the time. Someone who
-- appears while everything is shut came in by nobody knows which.
local function entrySide()
    if mode == "sealed" then
        return UNKNOWN
    end
    return side
end

-- Records someone inside or in a doorway. Their side is settled at their
-- first look: the side open at the time, or for a crate the side its
-- carrier came in by.
local function noteOccupant(list, id, obj, kind, x, y, where, zone, origin)
    local record = list[id]
    if record == nil then
        record = {
            id = id, obj = obj, kind = kind,
            cameIn = origin or entrySide(),
            target = list == crates or isTarget(kind, obj),
            searched = false, requested = nil,
        }
        list[id] = record
        lastEntrant = clock
        if isMark(nameOf(obj)) then
            -- marked before a save: carry on from there
            record.marked = clock
            record.ownName = ""
        end
        log(kind .. " " .. id .. " came in by the " .. record.cameIn
            .. (record.target and ", to be searched" or ""))
    end
    record.obj = obj
    record.x, record.y = x, y
    record.seen = clock
    record.where, record.zone = where, zone
    return record
end

-- Drops whoever this look saw outside, and whoever it has not seen for a
-- while.
local function forget(list, outside)
    for id, record in pairs(list) do
        if outside[id] or clock - record.seen > SEEN_GRACE then
            unmark(record)
            list[id] = nil
            lastLeft = clock
            log(record.kind .. " " .. id .. " gone")
        end
    end
end

local function notePlace(list, id, obj, kind, x, y, place, origin)
    if place == "chamber" then
        noteOccupant(list, id, obj, kind, x, y, "chamber", nil, origin)
    else
        noteOccupant(list, id, obj, kind, x, y, "lobby", place, origin)
    end
end

-- Everyone within reach of the room, sorted into occupants, people in a
-- doorway and people waiting outside a side. Guards are kept for the
-- attendance check. The dead are ignored: a body carried through goes with
-- its carrier. A crate goes wherever its carrier is.
local function scanPeople()
    local range = roomReach + DOOR_WAIT + 2
    local outside = {}
    scan.guards = {}
    scan.targets = 0
    scan.waiting.In, scan.waiting.Out = 0, 0
    scan.doorway.In, scan.doorway.Out = 0, 0
    for _, kind in ipairs(MOVERS) do
        for obj, _ in pairs(nearby(kind, range)) do
            local x, y = position(obj)
            local id = objectId(obj)
            if x ~= nil and id ~= nil and not isDead(obj) then
                if isTarget(kind, obj) then
                    scan.targets = scan.targets + 1
                end
                local place = insideAt(x, y)
                local doorway = place == nil and doorwayAt(x, y) or nil
                if place == nil and doorway == nil and occupants[id] ~= nil then
                    place = stillInsideAt(x, y)
                end
                if SEARCHERS[kind] then
                    scan.guards[#scan.guards + 1] = { obj = obj, id = id, kind = kind, x = x, y = y,
                                                      place = place or (doorway and "doorway") }
                end
                if place ~= nil then
                    notePlace(occupants, id, obj, kind, x, y, place)
                elseif doorway ~= nil then
                    scan.doorway[doorway] = scan.doorway[doorway] + 1
                    noteOccupant(occupants, id, obj, kind, x, y, "doorway", doorway)
                else
                    outside[id] = true
                    for _, w in ipairs(SIDES) do
                        if nearOuterDoor(w, x, y) then
                            scan.waiting[w] = scan.waiting[w] + 1
                        end
                    end
                end
            end
        end
    end
    forget(occupants, outside)
    outside = {}
    for _, kind in ipairs(CRATES) do
        for obj, _ in pairs(nearby(kind, range)) do
            local x, y = position(obj)
            local id = objectId(obj)
            if x ~= nil and id ~= nil then
                scan.targets = scan.targets + 1
                local carrier = occupants[number(Get(obj, "CarrierId.i"), -1)]
                local place = insideAt(x, y)
                if place == nil and crates[id] ~= nil and doorwayAt(x, y) == nil then
                    place = stillInsideAt(x, y)
                end
                if carrier ~= nil then
                    noteOccupant(crates, id, obj, kind, x, y, carrier.where, carrier.zone, carrier.cameIn)
                elseif place ~= nil then
                    notePlace(crates, id, obj, kind, x, y, place)
                else
                    outside[id] = true
                end
            end
        end
    end
    forget(crates, outside)
end

-- A guard on a job, standing against the person, whose destination is the
-- person or unset.
local function searching(guard, record)
    if guard.id == record.id then
        return false
    end
    if distance(guard.x, guard.y, record.x, record.y) > SEARCH_REACH then
        return false
    end
    if number(Get(guard.obj, "JobId"), -1) < 0 then
        return false
    end
    local dest = Get(guard.obj, "Dest")
    if type(dest) == "table" then
        local dx, dy = tonumber(dest.x), tonumber(dest.y)
        if dx ~= nil and dy ~= nil and dx >= 0 and dy >= 0 and (dx > 0 or dy > 0)
            and distance(dx, dy, record.x, record.y) > DEST_REACH then
            return false
        end
    end
    return true
end

-- Everyone inside still to be searched.
local function unsearched()
    local list = {}
    for _, records in ipairs({ occupants, crates }) do
        for _, record in pairs(records) do
            if record.target and not record.searched then
                list[#list + 1] = record
            end
        end
    end
    return list
end

local function requestSearches(pending)
    for _, record in ipairs(pending) do
        requestSearch(record)
    end
    lastRequest = clock
end

local function isCrate(record)
    return record.kind == "Box" or record.kind == "Stack"
end

-- A guard's job has ended after this much work against people still to be
-- searched: the search is credited to the nearest of them the work fits. A
-- person's search takes twice a crate's, so a job that ran the shorter time
-- was a crate's, if any crate is waiting.
local function creditSearch(guard, work, pending)
    local crateOnly = work < SEARCH_TIME_ENTITY - SEARCH_SLACK
    if work < SEARCH_TIME_CRATE - SEARCH_SLACK then
        return
    end
    local best, bestAt, bestDist = nil, nil, nil
    for i, record in ipairs(pending) do
        local crate = isCrate(record)
        if not crateOnly or crate then
            local d = distance(guard.x, guard.y, record.x, record.y)
            -- with the full time done a person comes before a crate
            if not crateOnly and not crate then
                d = d - 1000
            end
            if bestDist == nil or d < bestDist then
                best, bestAt, bestDist = record, i, d
            end
        end
    end
    if best ~= nil then
        best.searched = true
        unmark(best)
        table.remove(pending, bestAt)
        log(best.kind .. " " .. best.id .. " searched")
    end
end

-- Follows every guard's job. Work is counted while a guard on a job stands
-- against someone still to be searched with nowhere else to go; a job that
-- ends after a search's worth of it was that search. Searches are asked for
-- only while the room is shut, and asked for again once nothing has moved
-- for a while.
local function watchSearches(mayRequest)
    local pending = unsearched()
    if #pending == 0 then
        guardJobs = {}
        return
    end
    if mayRequest then
        local unasked = {}
        for _, record in ipairs(pending) do
            if record.requested == nil and record.marked == nil then
                unasked[#unasked + 1] = record
            end
        end
        if #unasked > 0 then
            requestSearches(unasked)
        end
    end
    -- The world script answers a call by clearing the marks and the call.
    -- While any mark still stands the call is kept up.
    local waiting = false
    for _, record in ipairs(pending) do
        if record.marked ~= nil and not acknowledged(record) then
            waiting = true
        end
    end
    if waiting and nameOf(this) ~= CALL_NAME then
        this.Name = CALL_NAME
    end
    local seen, progress = {}, false
    for _, guard in ipairs(scan.guards) do
        seen[guard.id] = true
        local jobId = number(Get(guard.obj, "JobId"), -1)
        local track = guardJobs[guard.id]
        if track ~= nil and track.id ~= jobId then
            creditSearch(guard, track.work, pending)
            guardJobs[guard.id] = nil
            track = nil
        end
        if jobId >= 0 then
            if track == nil then
                track = { id = jobId, work = 0 }
                guardJobs[guard.id] = track
            end
            for _, record in ipairs(pending) do
                if searching(guard, record) then
                    track.work = track.work + SCAN_INTERVAL * (SEARCH_RATE[guard.kind] or 1)
                    progress = true
                    break
                end
            end
        end
    end
    for id in pairs(guardJobs) do
        if not seen[id] then
            guardJobs[id] = nil
        end
    end
    if progress then
        lastProgress = clock
    elseif mayRequest and #pending > 0 and clock - lastRequest >= RETRY_AFTER
        and clock - lastProgress >= RETRY_AFTER then
        requestSearches(pending)
    end
end

-- Counts over everyone inside.
local function census()
    local c = { total = 0, unsearched = 0, wantIn = 0, wantOut = 0 }
    for _, list in ipairs({ occupants, crates }) do
        for _, record in pairs(list) do
            c.total = c.total + 1
            if record.target and not record.searched then
                c.unsearched = c.unsearched + 1
            elseif list == occupants then
                -- A cleared person wants the side they did not come in by.
                if record.cameIn == "Out" then
                    c.wantIn = c.wantIn + 1
                else
                    c.wantOut = c.wantOut + 1
                end
            end
        end
    end
    return c
end

-- A side may open right through only if nobody inside could cross the room
-- that way unsearched: everyone unsearched came in by that side.
local function mayOpen(s)
    for _, list in ipairs({ occupants, crates }) do
        for _, record in pairs(list) do
            if record.target and not record.searched and record.cameIn ~= s then
                return false
            end
        end
    end
    return true
end

-- Whether anyone unsearched is in a side's lobby or one of its
-- doorways, from either side or only from the other one.
local function lobbyHeld(s, fromOther)
    for _, list in ipairs({ occupants, crates }) do
        for _, record in pairs(list) do
            if record.where ~= "chamber" and record.zone == s and record.target
                and not record.searched and (not fromOther or record.cameIn ~= s) then
                return true
            end
        end
    end
    return false
end

-- A side's outer door alone may open only behind a shut inner door, and
-- only while nobody unsearched from the other side is in its lobby.
local function mayOpenOuter(s)
    return doors[s].inner ~= nil and not lobbyHeld(s, true)
end

-- Where a guard is heading: "inside" for a destination in the room or one
-- of its doorways, or beside someone on the books wherever the map puts
-- them, "away" for one elsewhere, nil for none the engine has set.
local function heading(guard)
    local dest = Get(guard.obj, "Dest")
    if type(dest) ~= "table" then
        return nil
    end
    local dx, dy = tonumber(dest.x), tonumber(dest.y)
    if dx == nil or dy == nil or dx < 0 or dy < 0 or (dx == 0 and dy == 0) then
        return nil
    end
    if insideAt(dx, dy) ~= nil or doorwayAt(dx, dy) ~= nil then
        return "inside"
    end
    for _, list in ipairs({ occupants, crates }) do
        for _, record in pairs(list) do
            if record.id ~= guard.id and distance(dx, dy, record.x, record.y) <= DEST_REACH then
                return "inside"
            end
        end
    end
    return "away"
end

-- By side, a guard on a job waiting outside its outer door, not let in
-- lately.
local function guardsWaiting()
    local found = {}
    for _, guard in ipairs(scan.guards) do
        local last = admitted[guard.id]
        if (last == nil or clock - last >= ADMIT_COOLDOWN) and guard.place == nil
            and number(Get(guard.obj, "JobId"), -1) >= 0 then
            for _, s in ipairs(SIDES) do
                if found[s] == nil and nearOuterDoor(s, guard.x, guard.y) then
                    found[s] = guard.id
                end
            end
        end
    end
    return found
end

-- Whether a guard stands in the chamber, or in a side's lobby.
local function guardIn(place)
    for _, guard in ipairs(scan.guards) do
        if guard.place == place then
            return true
        end
    end
    return false
end

-- Whether a guard inside the room is staying: free, or on a job in here.
-- One on the way out, such as an escort passing through, does not count.
local function searcherInside()
    for _, guard in ipairs(scan.guards) do
        if guard.place ~= nil and guard.place ~= "doorway" and heading(guard) ~= "away" then
            return true
        end
    end
    return false
end

local function enter(newMode, newSide, newStage)
    if newMode == "sealed" and mode ~= "admit" then
        lastProgress = clock
    end
    unlockDoors()
    mode = newMode
    side = existing(newSide or side)
    stage = newStage
    modeTimer = 0
    log("mode " .. mode .. " " .. side .. (stage and (" " .. stage) or ""))
end

local function reset()
    for _, list in ipairs({ occupants, crates }) do
        for _, record in pairs(list) do
            record.cameIn = nil
            record.searched = false
            record.requested = nil
        end
    end
    admitted = {}
end

-- ---------------------------------------------------------------- cycle

local function step(c)
    modeTimer = modeTimer + SCAN_INTERVAL
    if closing ~= nil then
        holdShut()
        if allShut() then
            local next = closing
            closing = nil
            enter(next.mode, next.side, next.stage)
        end
        return
    end
    local far = OTHER_SIDE[side]
    if mode == "intake" then
        holdSideOpen(side)
        if c.total == 0 and scan.doorway[side] == 0 then
            -- Empty. Someone waiting at the far side is let in there while
            -- nobody is coming in on this side.
            modeTimer = 0
            if doors[far].outer ~= nil and scan.waiting[far] > 0 and scan.waiting[side] == 0 then
                waitTimer[far] = waitTimer[far] + SCAN_INTERVAL
                if waitTimer[far] >= WAIT_SWITCH then
                    waitTimer[far] = 0
                    shutThen("intake", far)
                end
            else
                waitTimer[far] = 0
            end
        elseif c.total > 0 and ((scan.doorway[side] == 0
                and (clock - lastEntrant >= LOAD_GRACE or modeTimer >= LOAD_MAX))
                or modeTimer >= LOAD_FORCE) then
            if c.unsearched == 0 then
                shutThen("release", far)
            else
                shutThen("sealed")
            end
        end
    elseif mode == "sealed" then
        holdShut()
        if c.unsearched == 0 then
            enter("release", c.wantIn > c.wantOut and "In" or "Out")
            return
        end
        -- With a guard inside the inner doors stand open behind the shut
        -- outer doors, so anyone held in a lobby can be reached. With
        -- nobody inside to reach them they stay shut, so nobody unsearched
        -- ends up in the lobby of the side they did not come in by,
        -- where they would keep its outer door from ever opening.
        if searcherInside() then
            holdInnersOpen()
        end
        local waiting = guardsWaiting()
        for _, s in ipairs(SIDES) do
            local guard = waiting[s]
            if guard == nil then
                stuck[s] = 0
                if doors[s].outer ~= nil then
                    doors[s].outer.lock = false
                end
            elseif mayOpen(s) then
                admitted[guard] = clock
                shutThen("admit", s, "full")
                return
            elseif mayOpenOuter(s) then
                admitted[guard] = clock
                shutThen("admit", s, "outer")
                return
            else
                stuck[s] = stuck[s] + SCAN_INTERVAL
                if stuck[s] >= LOCK_AFTER then
                    doors[s].outer.lock = true
                end
            end
        end
    elseif mode == "admit" then
        if stage == "full" then
            holdSideOpen(side)
            if scan.doorway[side] == 0 and modeTimer >= ADMIT_GRACE then
                shutThen("sealed")
            end
        elseif stage == "outer" then
            -- Someone unsearched from the other side who reached this
            -- lobby before the inner door shut would walk straight out.
            if not mayOpenOuter(side) then
                shutThen("sealed")
                return
            end
            holdOpen(side, "outer")
            if (guardIn(side) and scan.doorway[side] == 0) or modeTimer >= ADMIT_GRACE * 2 then
                shutThen("admit", side, "inner")
            end
        else
            holdOpen(side, "inner")
            if (guardIn("chamber") and scan.doorway[side] == 0) or modeTimer >= ADMIT_GRACE * 2 then
                shutThen("sealed")
            end
        end
    elseif mode == "release" then
        if not mayOpen(side) then
            -- Someone unsearched turned up who did not come in by this side.
            -- Seal and search them before anything else.
            shutThen("sealed")
            return
        end
        holdSideOpen(side)
        local settled = clock - lastLeft >= RELEASE_GRACE and scan.doorway[side] == 0
        if c.total == 0 and scan.doorway.In == 0 and scan.doorway.Out == 0 then
            reset()
            if side == existing("In") then
                enter("intake", "In")
            else
                shutThen("intake", "In")
            end
        elseif c.unsearched > 0 and settled then
            -- Nobody cleared is still leaving; the unsearched newcomers who
            -- came in by this side get their search.
            shutThen("sealed")
        elseif settled and modeTimer >= RELEASE_SWAP and doors[far].outer ~= nil then
            -- Everyone left inside is cleared and nobody is leaving this
            -- way, so they want the other side.
            shutThen("release", far)
        end
    end
end

local function tooltip()
    if mode == "intake" then
        return "tooltip_StripSearchScanner_Intake"
    elseif mode == "release" then
        return "tooltip_StripSearchScanner_Release"
    end
    return "tooltip_StripSearchScanner_Sealed"
end

local lastTooltip = nil

function Create()
    lastTooltip = tooltip()
    this.Tooltip = lastTooltip
    showFrame(FRAME_IDLE)
    relayout()
end

function Update(timePassed)
    clock = clock + timePassed
    layoutTimer = layoutTimer + timePassed
    if layoutTimer >= LAYOUT_RECHECK then
        layoutTimer = 0
        relayout()
    end

    scanTimer = scanTimer + timePassed
    if scanTimer >= SCAN_INTERVAL then
        scanTimer = 0
        scanPeople()
        local c = census()
        if not finished or (scan.targets == 0 and c.unsearched == 0) then
            if not idle then
                idle = true
                closing = nil
                unlockDoors()
                log("standing open")
            end
            eachDoor(function(_, _, door)
                door.want = true
            end)
        else
            if idle then
                idle = false
                reset()
                shutThen("intake", "In")
            end
            watchSearches(mode == "sealed" or mode == "admit")
            step(c)
        end
        local text = tooltip()
        if text ~= lastTooltip then
            lastTooltip = text
            this.Tooltip = text
        end
    end

    pinDoors()

    if mode == "sealed" or mode == "admit" then
        pulseTimer = pulseTimer + timePassed
        if pulseTimer >= PULSE_INTERVAL then
            pulseTimer = 0
            showFrame(frame == FRAME_SCAN_A and FRAME_SCAN_B or FRAME_SCAN_A)
        end
    elseif mode == "release" then
        showFrame(FRAME_CLEAR)
    else
        showFrame(FRAME_IDLE)
    end
end
