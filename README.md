# Strip Search

A Prison Architect mod. A Strip Search room is a checkpoint: everyone who
goes through it is shut in and searched by a guard before the far door
opens, so nothing carries contraband past it, in either direction.

## What you get

- **Strip Search Scanner**, in the Security objects. It runs the room it
  stands in.
- **Strip Search Entrance** and **Strip Search Exit**, two doors the scanner
  holds open or shut itself. The game never opens them on its own.
- The **Strip Search** room type.
- Four quick builds in the Quick Rooms menu: **Strip Search 1x1, 2x2, 3x3
  and 4x4**. Each is the room with, on both sides, an outer door in the
  outside wall, a one-tile vestibule, and an inner door in a wall across
  the room.

## How it works

The scanner runs the doors as an airlock.

1. One side's doors are open and people walk in. Once nobody new has
   stepped in for a moment, they shut.
2. With everything shut, the scanner asks the game for a guard search of
   everyone inside who could be carrying anything: every prisoner, any
   guard the game knows to be crooked, and every crate, on the floor or in
   someone's arms. The game's own search is the only thing that takes
   contraband off a person, so that is what is used.
3. A guard comes. One arriving on the side people came in by is let
   straight in. One arriving on the far side is let into that side's
   vestibule first, the outer door shut behind them, and only then the
   inner door opened, so nobody inside can slip out past them.
4. When every search is done the far side's doors open and the room
   empties. Anyone who walks in while a door is open is unsearched, and the
   doors on the other side stay shut until they have been searched too.

The room works in both directions: someone waiting at the far side while
the room is empty is let in there and searched on the way back. Escorted
prisoners, staff and deliveries pass through like anyone else; only
prisoners, crooked guards and crates are searched.

The scanner cannot see what a person carries and the game reports nothing
when a search ends, so it watches the guards instead. A guard's job is
readable, and a search is one job: a job that ends after a search's worth
of standing against someone still to be searched was that search. Nobody
leaves by the far side until everyone who came in has a search to their
name.

## What it cannot do

These are the game's own rules, and no room changes them:

- A guard whose needs are neglected skips the confiscation half the time,
  and a crooked guard who has been bribed skips it. Keep your guards happy
  and your staff clean.
- Contraband thrown over a wall, or dug under one, never goes through a
  door.
- The room holds people until a guard has searched them. With no guard free
  they wait. Keep guards near it.

## Building by hand

A walled room with the scanner inside, a Strip Search Entrance in one wall
and a Strip Search Exit in another. The quick builds add a one-tile
vestibule behind a second door of the same kind on each side; that is what
lets a guard in from the far side safely, and a side built with a single
door can only admit a guard when everyone unsearched inside came in that
way. Zone the room as Strip Search so the scanner knows its shape.

## Files

- `data/scripts/StripSearchScanner.lua` is the scanner, written by hand.
- `tools/gen_assets.py` writes everything else the mod ships: the sprites,
  `materials.txt`, `prefabs.txt`, the language file and the thumbnail.
- `tools/simulate.py` runs the scanner script against a mock of the game
  (needs the `lupa` package): four doors, people walking through in both
  directions, guards who take the search jobs and stand against people for
  the game's search time, escorts, crates and crooked guards. It checks,
  over every seed and room size, that nothing crosses the room without a
  finished search, that no way through ever stands open, and that everyone
  gets through in the end.
