# Strip Search

A Prison Architect mod. Anyone who steps into a Strip Search room is
searched by a guard before they can leave it.

## What you get

- The **Strip Search** room type.
- The **Medical Probe Machine**, in the Security objects. It runs the room
  it stands in.
- The **Room Scanner**, in the Security objects. It stands on the room's
  floor and is why a search there finds everything.

The room needs those two and nothing else: no doors of its own, no
particular walls or floor.

## How it works

Zone a Strip Search room across a corridor, a doorway or the way into a
cell block, and put a Medical Probe Machine and a Room Scanner anywhere in
it. The room is
every tile zoned together with the machine's.

1. Someone steps in. A prisoner is probed on the way in, which costs them a
   small injury, once per visit.
2. The machine asks the game for a guard search of everyone inside who
   could be carrying anything: every prisoner, any guard the game knows to
   be crooked, and every crate, on the floor or in someone's arms. The
   game's own search is the only thing that takes contraband off a person,
   and one search takes everything the guard finds, so that is what is
   used.
3. The game will not search anything while someone is carrying it, so
   whoever carries an unsearched crate into the room is made to set it
   down there, and a guard escorting an unsearched prisoner is made to let
   go of them. The search happens in the room, and the game has the crate
   collected, or the prisoner escorted, again afterwards.
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
standing against the person it was walking to was that person's search.
A person's search takes twice as long as a crate's, so the length of the
job tells the two apart when a crate lies beside someone. The
machine's light is green with nobody waiting and red while it holds anyone.

## What the Room Scanner does

The game lets a search miss in two cases. A crooked guard who has been
bribed skips the confiscation, and a guard whose needs are neglected skips
it some of the time. The Room Scanner closes the first:

- A crooked guard who comes to search in the room is caught. They search as
  an honest guard would for as long as the job lasts, and come out of it
  exposed, with the game's own marker over them, for you to deal with.

The second is the game's own and stays. The only call that could meet a
guard's needs from a script belongs to the campaign, and outside the
campaign it crashes the game, so the mod does not touch it. Keep your guards'
needs met and no search in the room misses.

Without a scanner the machine still works and says so in its tooltip: a
bribed guard's search in that room can miss.

## What it cannot do

These are the game's own rules, and no room changes them:

- A guard whose needs are neglected skips the confiscation half the time.
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
  across it, in both directions, and never stop trying to walk on. One
  searching guard is crooked and bribed. It
  checks, over every seed, that nobody and no crate gets more than a step
  out of the room unsearched, that nothing leaves still carrying
  contraband, that the crooked guard ends exposed, that everyone gets through in the end, that
  each prisoner is hurt once a visit, and that everyone has their own name
  back afterwards.
