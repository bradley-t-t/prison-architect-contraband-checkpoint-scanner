-- Contraband Checkpoint Scanner: the Contraband Scanner. It stands in a Contraband Checkpoint room
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
-- The game will not search anything in someone's arms, so whoever carries
-- an unsearched crate into the room, or escorts an unsearched prisoner into
-- it, is made to let go, and the search happens in the room.
--
-- Nobody is kept for ever. Anyone still waiting HOLD_TIMEOUT seconds after
-- they came in is let go, whatever went wrong.
--
-- Until their search is done nobody leaves. There is no door to hold shut,
-- so the machine holds the person instead: anyone unsearched found outside
-- the room is put back where they last stood inside it, and so is anyone
-- carrying an unsearched crate.
--
-- A Guard Scanner on the room's floor deals with crooked guards. The game
-- lets a bribed crooked guard miss what they search for. With a scanner in
-- the room, a crooked guard who comes to search is caught: they search as
-- an honest guard would for as long as the job lasts, and come out of it
-- exposed, for the player to deal with. The one miss left is the game's
-- own: a guard whose needs are neglected skips the confiscation some of the
-- time, and nothing a script may safely call changes that.
--
-- The game reports nothing when a search ends, so the machine watches the
-- guards. A guard's job is readable and a search is one job: a job that
-- ends after a search's worth of standing against someone still to be
-- searched was that search.

local SCAN_INTERVAL = 0.25
-- With nobody in reach the machine looks this often instead. Reach runs
-- MARGIN tiles past the room, more than anyone walks in that time.
local IDLE_INTERVAL = 1
local LAYOUT_RECHECK = 30
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
-- Nobody is kept longer than this, whatever has gone wrong: a search the
-- machine never saw finish, a job the game dropped, no guard ever free.
local HOLD_TIMEOUT = 90
-- The game will not search the same person twice inside this long, so
-- someone the machine saw searched this recently is not kept again.
local SEARCH_COOLDOWN = 30
-- Looking for a carrier who is not a guard means searching the map for
-- every kind of person. It is done this often at most.
local CARRIER_SEARCH_EVERY = 2
local SCANNER = "RoomScanner"
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
-- The kinds looked for at every look: whoever can be searched and whoever
-- searches. Looking around is a search of the map, so the list is as short
-- as it can be.
local WATCHED_KINDS = { "Prisoner", "Guard", "ArmedGuard", "RiotGuard", "DogHandler", "Box", "Stack" }
local WATCHED = {}
for _, kind in ipairs(WATCHED_KINDS) do
    WATCHED[kind] = true
end

local Find = Object.GetNearbyObjects
local Get = Object.GetProperty
local Set = Object.SetProperty

local clock = 0
-- Timers start at a random point so several machines do not all look on
-- the same tick.
local scanTimer = math.random() * SCAN_INTERVAL
local scanEvery = SCAN_INTERVAL
local layoutTimer = math.random() * LAYOUT_RECHECK

-- The room's tiles keyed "x,y", and how far it reaches from the machine.
local roomTiles = {}
local roomReach = 1
local zoned = false
-- Whether a Guard Scanner stands in the room.
local scanned = false

-- Everyone and every crate in the room, or held to it, keyed by object id:
--   { id, obj, kind, x, y, inX, inY (where they last stood inside), target,
--     searched, marked, requested, ownName, seen }
local records = {}
-- Each guard's job as last seen, keyed by guard id: { id, work = seconds
-- stood against each person, dist = that time weighted by how far they were
-- from where the guard was going, both keyed by the person's id }.
local guardJobs = {}
local guards = {}
local lastProgress = 0
local lastRequest = 0
local lastCarrierSearch = -CARRIER_SEARCH_EVERY
-- When each person was last seen searched, keyed by id.
local searchedAt = {}

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

-- A tile as one number, which costs less than building a string.
local function tileKey(x, y)
    return math.floor(x) * 4096 + math.floor(y)
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

local STEPS = { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } }

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
            for _, step in ipairs(STEPS) do
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
    scanned = false
    for obj, _ in pairs(Find(SCANNER, reach + 1) or {}) do
        local x, y = position(obj)
        if x ~= nil and tiles[tileKey(x, y)] == true then
            scanned = true
        end
    end
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

-- Makes whoever is carrying a crate, or escorting a prisoner, let go of it
-- where they stand. The game will not search anything in someone's arms, so
-- it is searched standing in the room.
-- This is what the game's own drop does to the two of them: neither holds
-- the other any more.
local function setDown(record, carrier)
    Set(carrier.obj, "Carrying.i", -1)
    Set(carrier.obj, "Carrying.u", -1)
    Set(record.obj, "CarrierId.i", -1)
    Set(record.obj, "CarrierId.u", -1)
    Set(record.obj, "Carried", 0)
    log(record.kind .. " " .. tostring(record.id) .. " set down by " .. carrier.kind .. " " .. tostring(carrier.id))
end

local function note(id, obj, kind, x, y)
    local record = records[id]
    if record == nil then
        record = { id = id, obj = obj, kind = kind, target = isTarget(kind, obj), searched = false,
                   since = clock }
        records[id] = record
        if searchedAt[id] ~= nil and clock - searchedAt[id] < SEARCH_COOLDOWN then
            -- searched moments ago, and the game would refuse another
            record.searched = true
        end
        if isMark(nameOf(obj)) then
            -- marked before a save: carry on from there
            record.marked = clock
            record.ownName = ""
        end
        log(kind .. " " .. tostring(id) .. " came in" .. (record.target and ", to be searched" or ""))
    end
    record.obj = obj
    record.x, record.y = x, y
    record.seen = clock
    return record
end

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

-- Whoever is carrying something, as an object the script can write to. A
-- guard is known from this look already. Anyone else means searching the
-- map for every kind of person there is, the dearest thing this script ever
-- does, so it is done once in a look at most and only in a look that has
-- something in someone's arms to put down.
local function carrierOf(carrierId, range, everyone)
    for _, guard in ipairs(guards) do
        if guard.id == carrierId then
            return guard, everyone
        end
    end
    local record = records[carrierId]
    if record ~= nil then
        return record, everyone
    end
    if everyone == nil then
        everyone = {}
        if clock - lastCarrierSearch < CARRIER_SEARCH_EVERY then
            return nil, everyone
        end
        lastCarrierSearch = clock
        for _, kind in ipairs(MOVERS) do
            if not WATCHED[kind] then
                for obj, _ in pairs(Find(kind, range) or {}) do
                    local id = objectId(obj)
                    if id ~= nil then
                        everyone[id] = { obj = obj, id = id, kind = kind }
                    end
                end
            end
        end
    end
    return everyone[carrierId], everyone
end

-- Everyone who matters within reach of the room: prisoners, the guards who
-- search, and crates. Nobody else is ever searched or held, so nobody else
-- is looked for. Someone inside is recorded, and their place inside
-- remembered. Someone outside is looked at only if already kept. The dead
-- are ignored. Returns the ids of everyone recorded who is now outside, and
-- whether anyone at all was in reach.
local function scanPeople()
    local range = roomReach + MARGIN
    guards = {}
    local outside, anyone = {}, false
    for _, kind in ipairs(WATCHED_KINDS) do
        local crate = isCrateKind(kind)
        for obj, _ in pairs(Find(kind, range) or {}) do
            local x, y = position(obj)
            local id = objectId(obj)
            local stored = false
            if x ~= nil and id ~= nil then
                local known = records[id] ~= nil
                local within = inside(x, y)
                if crate and number(Get(obj, "CarrierId.i"), -1) >= 0
                    and number(Get(obj, "Carried"), 0) <= 0 then
                    -- stored on a shelf, a cooker or a truck rather than in
                    -- anyone's arms: part of the furniture, not a delivery
                    within, known = false, false
                    stored = true
                end
                if SEARCHERS[kind] then
                    guards[#guards + 1] = { obj = obj, id = id, kind = kind, x = x, y = y }
                end
                if (within or known) and (crate or not isDead(obj)) then
                    local record = note(id, obj, kind, x, y)
                    if within then
                        record.inX, record.inY = x, y
                    else
                        outside[id] = true
                    end
                end
            end
            -- A stored crate never moves, so it is no reason to look often.
            if not stored then
                anyone = true
            end
        end
    end
    -- Nothing in anyone's arms can be searched, and that goes for a
    -- prisoner under escort as much as for a crate: the game's search job
    -- fails for as long as they are carried. Whoever carries someone or
    -- something still to be searched lets go of it in the room.
    local everyone = nil
    for id, record in pairs(records) do
        if held(record) and not outside[id] and record.inX ~= nil then
            local carrierId = number(Get(record.obj, "CarrierId.i"), -1)
            if carrierId >= 0 and number(Get(record.obj, "Carried"), 0) > 0 then
                local carrier
                carrier, everyone = carrierOf(carrierId, range, everyone)
                -- A guard searching someone holds them while he does it,
                -- and that is not carrying: letting go there would break
                -- the very search being waited for. A guard with a job who
                -- is going nowhere else is searching; one bound elsewhere
                -- is an escort.
                local busy = false
                if carrier ~= nil and SEARCHERS[carrier.kind]
                    and number(Get(carrier.obj, "JobId"), -1) >= 0 then
                    carrier.x, carrier.y = position(carrier.obj)
                    carrier.dx, carrier.dy = destination(carrier)
                    busy = carrier.x ~= nil and searching(carrier, record) ~= nil
                end
                if carrier ~= nil and not busy then
                    setDown(record, carrier)
                end
            end
        end
    end
    return outside, anyone
end

-- Settles everyone the last look saw outside, once the searches that look
-- could see finished have been counted. Anyone still to be searched is put
-- back. Anyone else has left, and is forgotten.
local function enforce(outside)
    for id, record in pairs(records) do
        if held(record) and clock - record.since > HOLD_TIMEOUT then
            record.searched = true
            unmark(record)
            log(record.kind .. " " .. tostring(id) .. " let go after " .. HOLD_TIMEOUT .. " seconds")
        end
        if clock - record.seen > SEEN_GRACE then
            unmark(record)
            records[id] = nil
        elseif outside[id] then
            if held(record) then
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

-- A guard's job has ended. The time they spent at it is kept for everyone
-- they could have been searching, with how far each was from where the
-- guard was going. A person's search takes ten seconds and a crate's five,
-- so the length of the job says which it was: a full-length job was a
-- person's if any person fits, and a crate's only if none does. Among those
-- who fit, the one who was nearest to where the guard was going has it.
local function creditSearch(track, pending)
    local best, bestAt, bestDist, bestCrate = nil, nil, nil, nil
    for i, record in ipairs(pending) do
        local work = track.work[record.id] or 0
        local crate = isCrateKind(record.kind)
        local needed = crate and SEARCH_TIME_CRATE or SEARCH_TIME_ENTITY
        if work >= needed - SEARCH_SLACK then
            local d = track.dist[record.id] / work
            local better = best == nil
                or (bestCrate and not crate)
                or (bestCrate == crate and d < bestDist)
            if better then
                best, bestAt, bestDist, bestCrate = record, i, d, crate
            end
        end
    end
    if best ~= nil then
        best.searched = true
        searchedAt[best.id] = clock
        unmark(best)
        table.remove(pending, bestAt)
        log(best.kind .. " " .. tostring(best.id) .. " searched")
    end
end

-- Asks for a search of everyone still to be searched, follows every
-- guard's job to see the searches done, and asks again once nothing has
-- moved for a while. Returns how many are still waiting.
local function watchSearches(elapsed)
    local pending = unsearched()
    if #pending == 0 then
        for _, track in pairs(guardJobs) do
            if track.crooked and track.obj ~= nil then
                Set(track.obj, "Corrupted", true)
                Set(track.obj, "Exposed", true)
            end
        end
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
    local seen, progress = {}, false
    for _, guard in ipairs(guards) do
        seen[guard.id] = true
        local jobId = number(Get(guard.obj, "JobId"), -1)
        local track = guardJobs[guard.id]
        if track ~= nil and track.id ~= jobId then
            if track.crooked then
                -- the job is over: they are what they were, and now known
                Set(guard.obj, "Corrupted", true)
                Set(guard.obj, "Exposed", true)
                log("guard " .. tostring(guard.id) .. " exposed")
            end
            creditSearch(track, pending)
            guardJobs[guard.id] = nil
            track = nil
        end
        if jobId >= 0 then
            if track == nil then
                track = { id = jobId, work = {}, dist = {}, obj = guard.obj }
                guardJobs[guard.id] = track
            end
            -- the time counts for everyone the guard could be searching
            guard.dx, guard.dy = destination(guard)
            local working = false
            -- a guard holds whoever he is searching, which names them
            local holding = number(Get(guard.obj, "Carrying.i"), -1)
            for _, record in ipairs(pending) do
                local d = searching(guard, record)
                if d ~= nil and (holding < 0 or holding == record.id) then
                    local spent = elapsed * (SEARCH_RATE[guard.kind] or 1)
                    track.work[record.id] = (track.work[record.id] or 0) + spent
                    track.dist[record.id] = (track.dist[record.id] or 0) + d * spent
                    working = true
                end
            end
            if working then
                progress = true
                if scanned and not track.crooked and Get(guard.obj, "Corrupted") == true then
                    -- the game lets a bribed crooked guard miss: for this
                    -- job they are not one
                    track.crooked = true
                    Set(guard.obj, "Corrupted", false)
                    log("guard " .. tostring(guard.id) .. " is crooked, held honest for this search")
                end
            end
        end
    end
    for id, track in pairs(guardJobs) do
        if not seen[id] then
            if track.crooked and track.obj ~= nil then
                Set(track.obj, "Corrupted", true)
                Set(track.obj, "Exposed", true)
            end
            guardJobs[id] = nil
        end
    end
    if waiting and nameOf(this) ~= CALL_NAME then
        this.Name = CALL_NAME
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
    elseif not scanned then
        tip = "tooltip_MedicalProbeMachine_NoScanner"
    elseif waiting > 0 then
        tip = "tooltip_MedicalProbeMachine_Holding"
    end
    if tip ~= lastTooltip then
        lastTooltip = tip
        this.Tooltip = tip
    end
end

-- The game hands a script every object a search finds as a global named for
-- the object's type and id, and never takes one back, so a machine that the
-- whole prison walks past holds on to everyone who ever did, and Lua's
-- collector walks all of them on every pass. Every FORGET_EVERY seconds those
-- globals are cleared, just before a look fetches everyone in reach afresh.
-- Reading a property of an object goes through its global, so the people the
-- machine still keeps a record of and the guards whose jobs it is following
-- keep theirs.
local FORGET_EVERY = 20
local forgetTimer = math.random() * FORGET_EVERY

local function forget()
    if _G == nil then
        return
    end
    for name, value in pairs(_G) do
        if type(value) == "table" and type(name) == "string" then
            local id = string.match(name, "i(%-?%d+)u%-?%d+$")
            id = id and tonumber(id)
            if id ~= nil and records[id] == nil and guardJobs[id] == nil then
                _G[name] = nil
            end
        end
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
    forgetTimer = forgetTimer + timePassed
    scanTimer = scanTimer + timePassed
    if scanTimer >= scanEvery then
        local elapsed = scanTimer
        scanTimer = 0
        if forgetTimer >= FORGET_EVERY then
            forgetTimer = 0
            forget()
        end
        local outside, anyone = scanPeople()
        local waiting = watchSearches(elapsed)
        enforce(outside)
        showTooltip(waiting)
        scanEvery = (anyone or next(records) ~= nil) and SCAN_INTERVAL or IDLE_INTERVAL
    end
end
