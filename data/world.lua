-- Strip Search: the mod's world script. The game hands its work queue to
-- this script and to no object's own script, so a Medical Probe Machine
-- cannot ask for a guard search itself. It leaves word instead, in the one
-- place both scripts can reach: every object has a Name a script can look
-- it up by. A machine wanting searches names itself CALL_NAME and names each
-- person to be searched MARK_PREFIX followed by their id. This script looks
-- for a machine by that name, asks the game to search everyone near it who
-- carries the mark, and clears the names again. The cleared mark tells the
-- machine the search has been asked for.
--
-- With a Room Scanner in its room a machine also names each guard at work
-- on a search GUARD_PREFIX followed by their id. The game lets a fed-up
-- guard miss what they search for, so this script has the game meet that
-- guard's needs. The game does that by name and a moment later, so the name
-- is left on until the next look and cleared then.

local POLL = 0.25
local CALL_NAME = "StripSearchCall"
local MARK_PREFIX = "StripSearchTarget"
local GUARD_PREFIX = "StripSearchGuard"
-- The staff who carry out a search.
local SEARCHERS = { "Guard", "ArmedGuard", "RiotGuard", "DogHandler" }
-- How far from a machine its room can reach.
local REACH = 32
-- Machines answered in one look. Any others are answered on the next.
local MAX_CALLS = 8
-- Everything a machine ever asks to have searched.
local KINDS = { "Prisoner", "Guard", "Box", "Stack" }

local timer = 0
-- Guards whose needs were met at the last look, still to be given their
-- own names back.
local tended = {}

local function isMark(name)
    return type(name) == "string" and string.sub(name, 1, #MARK_PREFIX) == MARK_PREFIX
end

local function hasPrefix(name, prefix)
    return type(name) == "string" and string.sub(name, 1, #prefix) == prefix
end

local function tend(machine)
    for _, kind in ipairs(SEARCHERS) do
        for obj, _ in pairs(Object.GetNearbyObjects(machine, kind, REACH) or {}) do
            local name = Object.GetProperty(obj, "Name")
            if hasPrefix(name, GUARD_PREFIX) then
                Game.SetNeeds(name, 0)
                tended[#tended + 1] = obj
            end
        end
    end
end

local function answer(machine)
    tend(machine)
    for _, kind in ipairs(KINDS) do
        for obj, _ in pairs(Object.GetNearbyObjects(machine, kind, REACH) or {}) do
            if isMark(Object.GetProperty(obj, "Name")) then
                WorkQueue.Request("SearchObject", obj)
                Object.SetProperty(obj, "Name", "")
            end
        end
    end
    Object.SetProperty(machine, "Name", "")
end

function Init()
end

function Update(timePassed)
    timer = timer + (tonumber(timePassed) or 0)
    if timer < POLL then
        return
    end
    timer = 0
    for _, obj in ipairs(tended) do
        if hasPrefix(Object.GetProperty(obj, "Name"), GUARD_PREFIX) then
            Object.SetProperty(obj, "Name", "")
        end
    end
    tended = {}
    for _ = 1, MAX_CALLS do
        local machine = Game.GetObject(CALL_NAME)
        if machine == nil then
            return
        end
        answer(machine)
    end
end
