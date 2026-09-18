-- Strip Search: the Medical Probe Machine. It stands in a Strip Search room
-- and runs it. The room is every tile zoned with the machine's own tile,
-- found by walking outwards from it, so the room needs no doors of its own
-- to work.
--
-- Whoever steps into the room is to be searched: every prisoner, any guard
-- the game knows to be crooked, and every crate, on the floor or in
-- someone's arms. The game's own guard search is the only thing that takes
-- contraband off a person, so that is what is asked for. No object's script
-- is given the work queue, so the machine leaves word for the mod's world
-- script (data/world.lua): it names itself CALL_NAME and names each person
-- to be searched MARK_PREFIX followed by their id, and the world script
-- asks the game for those searches and clears the names.
--
-- A prisoner is probed as they come in, which hurts a little: a small
-- injury, once per visit.
--
-- Until their search is done nobody leaves. There is no door to hold shut,
-- so the machine holds the person instead: anyone unsearched found outside
-- the room is put back where they last stood inside it, and so is anyone
-- carrying an unsearched crate.
--
-- The game reports nothing when a search ends, so the machine watches the
-- guards. A guard's job is readable and a search is one job: a job that
-- ends after a search's worth of standing against someone still to be
-- searched was that search.

local SCAN_INTERVAL = 0.25
local LAYOUT_RECHECK = 5
local MAX_ROOM_TILES = 400
-- How far past the room's edge people are looked for.
local MARGIN = 4
-- How close a guard stands to search, and how near their destination is to
-- the person when the person is where they are going.
local SEARCH_REACH = 1.6
local DEST_REACH = 1.8
-- The game's search times in seconds, and the slack allowed on them.
local SEARCH_TIME_ENTITY = 10
local SEARCH_TIME_CRATE = 5
local SEARCH_RATE = { DogHandler = 5 }
local SEARCH_SLACK = 1
-- Someone unseen this long has gone: off the map, unpacked, or dead.
local SEEN_GRACE = 1.5
-- A search asked for and not seen to start is asked for again after this.
local RETRY_AFTER = 40
-- What the probe costs a prisoner, of a whole life of 1, and the most
-- injured it will leave anyone.
local PROBE_INJURY = 0.05
local PROBE_CEILING = 0.6
local CALL_NAME = "StripSearchCall"
local MARK_PREFIX = "StripSearchTarget"
local DEBUG = false

-- Everyone who can walk.
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

local clock = 0
local scanTimer = SCAN_INTERVAL
local layoutTimer = LAYOUT_RECHECK

-- The room's tiles keyed "x,y", and how far it reaches from the machine.
local roomTiles = {}
local roomReach = 1
local zoned = false

-- Everyone and every crate in the room, or held to it, keyed by object id:
--   { id, obj, kind, x, y, inX, inY (where they last stood inside), target,
--     searched, marked, requested, ownName, seen, carrier (a crate's) }
local records = {}
-- Each guard's job as last seen, keyed by guard id: { id, work = seconds
-- stood against each person, keyed by their id }.
local guardJobs = {}
local guards = {}
local lastProgress = 0
local lastRequest = 0

local function log(text)
    if DEBUG then
        Game.DebugOut("StripSearch " .. tostring(this.Id.i) .. ": " .. text)
    end
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

-- ------------------------------------------------------------------ room

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

-- The room is every tile zoned with the machine's, reached from it a step
-- at a time.
local function mapRoom()
    local sx, sy = position(this)
    if sx == nil then
        return
    end
    local ox, oy = math.floor(sx), math.floor(sy)
    local tiles, count, reach = {}, 0, 1
    local home = cellRoom(World.GetCell(ox, oy))
    if home >= 0 then
        local queue = { { ox, oy } }
        tiles[tileKey(ox, oy)] = true
        count = 1
        local head = 1
        while head <= #queue and count < MAX_ROOM_TILES do
            local x, y = queue[head][1], queue[head][2]
            head = head + 1
            for _, step in ipairs({ { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } }) do
                local nx, ny = x + step[1], y + step[2]
                local key = tileKey(nx, ny)
                if tiles[key] == nil and cellRoom(World.GetCell(nx, ny)) == home then
                    tiles[key] = true
                    count = count + 1
                    reach = math.max(reach, math.abs(nx - ox), math.abs(ny - oy))
                    queue[#queue + 1] = { nx, ny }
                end
            end
        end
    end
    roomTiles, roomReach, zoned = tiles, reach, home >= 0
end

local function inside(x, y)
    return roomTiles[tileKey(x, y)] == true
end

-- ---------------------------------------------------------------- people

local function isCrateKind(kind)
    return kind == "Box" or kind == "Stack"
end

local function isTarget(kind, obj)
    if kind == "Prisoner" or isCrateKind(kind) then
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

local function held(record)
    return record.target and not record.searched
end

-- The probe: a small injury, never enough to put anyone down.
local function probe(record)
    local damage = number(Get(record.obj, "Damage"), 0)
    if damage < PROBE_CEILING then
        Set(record.obj, "Damage", math.min(PROBE_CEILING, damage + PROBE_INJURY))
    end
    log("prisoner " .. tostring(record.id) .. " probed")
end

-- Puts someone back where they last stood inside the room.
local function putBack(record)
    if record.inX == nil then
        return
    end
    Set(record.obj, "Pos.x", record.inX)
    Set(record.obj, "Pos.y", record.inY)
    Object.ClearRouting(record.obj)
    record.x, record.y = record.inX, record.inY
    log(record.kind .. " " .. tostring(record.id) .. " put back")
end

local function note(id, obj, kind, x, y)
    local record = records[id]
    if record == nil then
        record = { id = id, obj = obj, kind = kind, target = isTarget(kind, obj), searched = false }
        records[id] = record
        if isMark(nameOf(obj)) then
            -- marked before a save: carry on from there, already probed
            record.marked = clock
            record.ownName = ""
        elseif kind == "Prisoner" then
            probe(record)
        end
        log(kind .. " " .. tostring(id) .. " came in" .. (record.target and ", to be searched" or ""))
    end
    record.obj = obj
    record.x, record.y = x, y
    record.seen = clock
    return record
end

-- Everyone within reach of the room. Someone inside is recorded, and their
-- place inside remembered. Someone outside is looked at only if already
-- kept. The dead are ignored. A crate goes where its carrier goes. Returns
-- the ids of everyone recorded who is now outside.
local function scanPeople()
    local range = roomReach + MARGIN
    guards = {}
    local outside = {}
    for _, kind in ipairs(MOVERS) do
        for obj, _ in pairs(Find(kind, range) or {}) do
            local x, y = position(obj)
            local id = objectId(obj)
            if x ~= nil and id ~= nil and not isDead(obj) then
                if SEARCHERS[kind] then
                    guards[#guards + 1] = { obj = obj, id = id, kind = kind, x = x, y = y }
                end
                if inside(x, y) then
                    local record = note(id, obj, kind, x, y)
                    record.inX, record.inY = x, y
                elseif records[id] ~= nil then
                    note(id, obj, kind, x, y)
                    outside[id] = true
                end
            end
        end
    end
    for _, kind in ipairs(CRATES) do
        for obj, _ in pairs(Find(kind, range) or {}) do
            local x, y = position(obj)
            local id = objectId(obj)
            if x ~= nil and id ~= nil then
                local carrierId = number(Get(obj, "CarrierId.i"), -1)
                local carrier = records[carrierId]
                if inside(x, y) or (carrier ~= nil and not outside[carrierId]) then
                    local record = note(id, obj, kind, x, y)
                    record.carrier = carrier ~= nil and carrierId or nil
                    if inside(x, y) then
                        record.inX, record.inY = x, y
                    end
                elseif records[id] ~= nil then
                    local record = note(id, obj, kind, x, y)
                    record.carrier = carrierId >= 0 and carrierId or nil
                    outside[id] = true
                end
            end
        end
    end
    return outside
end

-- Settles everyone the last look saw outside, once the searches that look
-- could see finished have been counted. An unsearched crate outside in
-- someone's arms: the carrier goes back, and the crate with them. One on
-- the floor outside is put back itself.
local function enforce(outside)
    local carrying = {}
    for _, record in pairs(records) do
        if isCrateKind(record.kind) and held(record) and record.carrier ~= nil then
            carrying[record.carrier] = true
        end
    end
    for id, record in pairs(records) do
        if clock - record.seen > SEEN_GRACE then
            unmark(record)
            records[id] = nil
        elseif outside[id] then
            local crate = isCrateKind(record.kind)
            if crate and held(record) then
                if record.carrier == nil then
                    putBack(record)
                end
            elseif not crate and (held(record) or carrying[id]) then
                putBack(record)
            else
                unmark(record)
                records[id] = nil
                log(record.kind .. " " .. tostring(id) .. " gone")
            end
        end
    end
end

-- -------------------------------------------------------------- searches

-- Where a guard is going, or nil when nowhere is set.
local function destination(guard)
    local dest = Get(guard.obj, "Dest")
    if type(dest) == "table" then
        local dx, dy = tonumber(dest.x), tonumber(dest.y)
        if dx ~= nil and dy ~= nil and dx >= 0 and dy >= 0 and (dx > 0 or dy > 0) then
            return dx, dy
        end
    end
    return nil, nil
end

-- How well a guard on a job fits being the one searching this person: nil
-- when they cannot be, otherwise how far the person is from where the guard
-- is going, or from the guard when nowhere is set. A guard walks to the
-- person they search, so the nearest to their destination is the one.
local function searching(guard, record)
    if guard.id == record.id then
        return nil
    end
    if distance(guard.x, guard.y, record.x, record.y) > SEARCH_REACH then
        return nil
    end
    if guard.dx ~= nil then
        local d = distance(guard.dx, guard.dy, record.x, record.y)
        if d > DEST_REACH then
            return nil
        end
        return d
    end
    return distance(guard.x, guard.y, record.x, record.y)
end

local function unsearched()
    local list = {}
    for _, record in pairs(records) do
        if held(record) then
            list[#list + 1] = record
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

-- A guard's job has ended. The work they did is kept by who they stood
-- against, so the search goes to whoever had the most of it, if that was a
-- search's worth: ten seconds for a person, five for a crate.
local function creditSearch(track, pending)
    local best, bestWork = nil, 0
    for id, work in pairs(track.work) do
        if work > bestWork then
            best, bestWork = id, work
        end
    end
    for i, record in ipairs(pending) do
        if record.id == best then
            local needed = isCrateKind(record.kind) and SEARCH_TIME_CRATE or SEARCH_TIME_ENTITY
            if bestWork >= needed - SEARCH_SLACK then
                record.searched = true
                unmark(record)
                table.remove(pending, i)
                log(record.kind .. " " .. tostring(record.id) .. " searched")
            end
            return
        end
    end
end

-- Asks for a search of everyone still to be searched, follows every
-- guard's job to see the searches done, and asks again once nothing has
-- moved for a while. Returns how many are still waiting.
local function watchSearches(elapsed)
    local pending = unsearched()
    if #pending == 0 then
        guardJobs = {}
        return 0
    end
    local unasked = {}
    for _, record in ipairs(pending) do
        if record.requested == nil and record.marked == nil then
            unasked[#unasked + 1] = record
        end
    end
    if #unasked > 0 then
        requestSearches(unasked)
    end
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
    for _, guard in ipairs(guards) do
        seen[guard.id] = true
        local jobId = number(Get(guard.obj, "JobId"), -1)
        local track = guardJobs[guard.id]
        if track ~= nil and track.id ~= jobId then
            creditSearch(track, pending)
            guardJobs[guard.id] = nil
            track = nil
        end
        if jobId >= 0 then
            if track == nil then
                track = { id = jobId, work = {} }
                guardJobs[guard.id] = track
            end
            -- the work goes to the nearest person the guard could be searching
            local nearest, nearestAt = nil, nil
            guard.dx, guard.dy = destination(guard)
            for _, record in ipairs(pending) do
                local d = searching(guard, record)
                if d ~= nil then
                    if nearestAt == nil or d < nearestAt then
                        nearest, nearestAt = record, d
                    end
                end
            end
            if nearest ~= nil then
                track.work[nearest.id] = (track.work[nearest.id] or 0)
                    + elapsed * (SEARCH_RATE[guard.kind] or 1)
                progress = true
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
    elseif clock - lastRequest >= RETRY_AFTER and clock - lastProgress >= RETRY_AFTER then
        requestSearches(pending)
    end
    return #pending
end

local lastTooltip = nil
local frame = -1

-- Frame 0 is the machine at rest, frame 1 the machine with someone held.
local function showFrame(n)
    if frame ~= n then
        frame = n
        this.SubType = n
    end
end

local function showTooltip(waiting)
    showFrame((zoned and waiting > 0) and 1 or 0)
    local tip = "tooltip_MedicalProbeMachine_Clear"
    if not zoned then
        tip = "tooltip_MedicalProbeMachine_NoRoom"
    elseif waiting > 0 then
        tip = "tooltip_MedicalProbeMachine_Holding"
    end
    if tip ~= lastTooltip then
        lastTooltip = tip
        this.Tooltip = tip
    end
end

function Create()
    mapRoom()
    showTooltip(0)
end

function Update(timePassed)
    clock = clock + timePassed
    layoutTimer = layoutTimer + timePassed
    if layoutTimer >= LAYOUT_RECHECK then
        layoutTimer = 0
        mapRoom()
    end
    scanTimer = scanTimer + timePassed
    if scanTimer >= SCAN_INTERVAL then
        local elapsed = scanTimer
        scanTimer = 0
        local outside = scanPeople()
        local waiting = watchSearches(elapsed)
        enforce(outside)
        showTooltip(waiting)
    end
end
