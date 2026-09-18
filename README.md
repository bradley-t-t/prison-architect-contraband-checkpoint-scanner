# Strip Search

A Prison Architect mod. Anyone who steps into a Strip Search room is
searched by a guard before they can leave it.

## What you get

- The **Strip Search** room type.
- The **Medical Probe Machine**, in the Security objects. It runs the room
  it stands in, and the room needs nothing else: no doors of its own, no
  particular walls or floor.

## How it works

Zone a Strip Search room across a corridor, a doorway or the way into a
cell block, and put a Medical Probe Machine anywhere in it. The room is
every tile zoned together with the machine's.

1. Someone steps in. A prisoner is probed on the way in, which costs them a
   small injury, once per visit.
2. The machine asks the game for a guard search of everyone inside who
   could be carrying anything: every prisoner, any guard the game knows to
   be crooked, and every crate, on the floor or in someone's arms. The
   game's own search is the only thing that takes contraband off a person,
   and one search takes everything the guard finds, so that is what is
   used.
3. The game will not search a crate while someone is carrying it, so
   whoever carries an unsearched crate into the room is made to set it
   down there. It is searched on the floor, and the game has it collected
   again afterwards.
4. Until that search is done they do not leave. There is no door to hold
   shut, so the machine holds the person: anyone unsearched who steps out
   of the room is put back where they last stood inside it.
5. Once searched they walk on. Coming back in later is a new visit and a
   new search.

Other staff, visitors and dogs walk through freely. The game's search does
nothing to them, so holding them would only block the corridor.

The machine cannot see what a person carries and the game reports nothing
when a search ends, so it watches the guards instead. A guard's job is
readable, and a search is one job: a job that ends after a search's worth of
standing against the person it was walking to was that person's search. The
machine's light is green with nobody waiting and red while it holds anyone.

## What it cannot do

These are the game's own rules, and no room changes them:

- A guard whose needs are neglected skips the confiscation half the time,
  and a crooked guard who has been bribed skips it. Keep your guards happy
  and your staff clean.
- Contraband thrown over a wall, or dug under one, never goes through the
  room.
- The game will not search the same person twice inside thirty seconds.
  Someone who walks straight back in waits that out.
- With no guard free, people wait. Keep guards near the room.

## Why the room needs the machine

The game tells a script which room a tile belongs to, and never what kind
of room that is. The machine is how the mod knows a room is a Strip Search
room: it reads the room its own tile is zoned into.

## Files

- `data/scripts/MedicalProbeMachine.lua` is the machine, written by hand.
- `data/world.lua` asks the game for the searches. The game gives its work
  queue to a mod's world script and to no object's own script, so the
  machine marks who is to be searched and this file does the asking.
- `tools/gen_assets.py` writes everything else the mod ships: the sprites,
  `materials.txt`, the language file and the thumbnail.
- `tools/simulate.py` runs both scripts against a mock of the game (needs
  the `lupa` package), each in its own Lua state with only what the game
  gives that kind of script. People walk a corridor with the room zoned
  across it, in both directions, and never stop trying to walk on. It
  checks, over every seed, that nobody and no crate gets more than a step
  out of the room unsearched, that everyone gets through in the end, that
  each prisoner is hurt once a visit, and that everyone has their own name
  back afterwards.
