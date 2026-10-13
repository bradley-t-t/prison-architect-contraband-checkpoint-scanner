-- Contraband Checkpoint Scanner: the mod's world script. The game hands its work queue to
-- this script and to no object's own script, so a Contraband Scanner
-- cannot ask for a guard search itself. It leaves word instead, in the one
-- place both scripts can reach: every object has a Name a script can look
-- it up by. A machine wanting searches names itself CALL_NAME, names each
-- person to be searched MARK_PREFIX followed by their id, and lists those
-- ids in WANTED. This script looks for a machine by that name, looks each
-- person on its list up by their mark, asks the game to search them, and
-- clears the names again. The cleared mark tells the machine the search has
-- been asked for.
--
-- A search of the map hands back a full record of everyone it finds, so
-- the ground round a machine is searched for marks only once a minute, for
-- any mark no machine listed: one left from before a save, or by a machine
-- taken down since.
--
-- Nothing here may call the game's campaign commands (Game.SetNeeds and the
-- rest of that family). Outside the campaign they crash the game.

local POLL = 0.5
local CALL_NAME = "StripSearchCall"
local MARK_PREFIX = "StripSearchTarget"
-- A name an earlier version left on guards at work. Any still standing
-- from a save made then is taken off.
local GUARD_PREFIX = "StripSearchGuard"
local SEARCHERS = { "Guard", "ArmedGuard", "RiotGuard", "DogHandler" }
-- How far from a machine its room can reach.
local REACH = 32
-- Machines answered in one look. Any others are answered on the next.
local MAX_CALLS = 8
-- Everything a machine ever asks to have searched.
local KINDS = { "Prisoner", "Guard", "Box", "Stack" }
-- Where a machine lists the ids it has marked, separated by commas.
local WANTED = "StripSearchWanted"
-- Seconds between searches round one machine for marks it did not list.
local SWEEP_EVERY = 60

local timer = 0
local clock = 0
-- Machine id -> the clock at the last search round it.
local sweptAt = {}

local function isMark(name)
    return type(name) == "string" and string.sub(name, 1, #MARK_PREFIX) == MARK_PREFIX
end

local function hasPrefix(name, prefix)
    return type(name) == "string" and string.sub(name, 1, #prefix) == prefix
end

local function clearOldNames(machine)
    for _, kind in ipairs(SEARCHERS) do
        for obj, _ in pairs(Object.GetNearbyObjects(machine, kind, REACH) or {}) do
            if hasPrefix(Object.GetProperty(obj, "Name"), GUARD_PREFIX) then
                Object.SetProperty(obj, "Name", "")
            end
        end
    end
end

local function request(obj)
    WorkQueue.Request("SearchObject", obj)
    Object.SetProperty(obj, "Name", "")
end

-- Every mark within REACH of the machine, found by searching for everyone
-- of each kind a machine asks to have searched.
local function sweep(machine)
    clearOldNames(machine)
    for _, kind in ipairs(KINDS) do
        for obj, _ in pairs(Object.GetNearbyObjects(machine, kind, REACH) or {}) do
            if isMark(Object.GetProperty(obj, "Name")) then
                request(obj)
            end
        end
    end
end

local function answer(machine)
    local id = machine.Id and tonumber(machine.Id.i) or -1
    if sweptAt[id] == nil or clock - sweptAt[id] >= SWEEP_EVERY then
        sweptAt[id] = clock
        sweep(machine)
    end
    local wanted = Object.GetProperty(machine, WANTED)
    if wanted ~= nil then
        for each in string.gmatch(tostring(wanted), "[^,]+") do
            local obj = Game.GetObject(MARK_PREFIX .. each)
            if obj ~= nil and isMark(Object.GetProperty(obj, "Name")) then
                request(obj)
            end
        end
    end
    Object.SetProperty(machine, "Name", "")
end

function Init()
end

function Update(timePassed)
    clock = clock + (tonumber(timePassed) or 0)
    timer = timer + (tonumber(timePassed) or 0)
    if timer < POLL then
        return
    end
    timer = 0
    for _ = 1, MAX_CALLS do
        local machine = Game.GetObject(CALL_NAME)
        if machine == nil then
            return
        end
        answer(machine)
    end
end

-- The game hands a script every object a search finds as a global named for
-- the object's type and id, and never takes one back, so a script that
-- searches holds on to everyone it has ever found. Every FORGET_EVERY seconds
-- those globals are cleared, and Lua's own collector frees what they held.
-- Reading a property of an object goes through its global, so this is only
-- for a script that keeps no object from one update to the next.
local FORGET_EVERY = 20
local forgetTimer = math.random() * FORGET_EVERY
local runUpdate = Update
function Update(timePassed)
    forgetTimer = forgetTimer + (tonumber(timePassed) or 0)
    if forgetTimer >= FORGET_EVERY then
        forgetTimer = 0
        if _G ~= nil then
            for name, value in pairs(_G) do
                if type(value) == "table" and type(name) == "string" and name:find("i%-?%d+u%-?%d+$") then
                    _G[name] = nil
                end
            end
        end
    end
    return runUpdate(timePassed)
end
