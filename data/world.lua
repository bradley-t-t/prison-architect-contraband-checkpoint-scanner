-- Strip Search: the mod's world script. The game hands its work queue to
-- this script and to no object's own script, so a Medical Probe Machine
-- cannot ask for a guard search itself. It leaves word instead, in the one
-- place both scripts can reach: every object has a Name a script can look
-- it up by. A machine wanting searches names itself CALL_NAME and names each
-- person to be searched MARK_PREFIX followed by their id. This script looks
-- for a machine by that name, asks the game to search everyone near it who
-- carries the mark, and clears the names again. The cleared mark tells the
-- machine the search has been asked for.

local POLL = 0.25
local CALL_NAME = "StripSearchCall"
local MARK_PREFIX = "StripSearchTarget"
-- How far from a machine its room can reach.
local REACH = 32
-- Machines answered in one look. Any others are answered on the next.
local MAX_CALLS = 8
-- Everything a machine ever asks to have searched.
local KINDS = { "Prisoner", "Guard", "Box", "Stack" }

local timer = 0

local function isMark(name)
    return type(name) == "string" and string.sub(name, 1, #MARK_PREFIX) == MARK_PREFIX
end

local function answer(machine)
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
    for _ = 1, MAX_CALLS do
        local machine = Game.GetObject(CALL_NAME)
        if machine == nil then
            return
        end
        answer(machine)
    end
end
