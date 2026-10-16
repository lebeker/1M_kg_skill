# The `kg/1` format

A graph is one JSON file. It is meant to be small enough to read, diff and hand-edit.

```json
{
  "meta": {
    "title": "My Field",
    "schema": "kg/1",
    "app": "viewer",
    "app_url": "https://…/viewer.html",
    "requires": { "skills": ["kg"], "plugins": [], "tools": ["openalex"] },
    "colors": { "concept": "#7b9ecb", "lab": "#93c47d" }
  },
  "nodes": [
    {
      "id": "telo",
      "label": "Telomere attrition",
      "kind": "concept",
      "level": 2,
      "size": 4,
      "style": "solid",
      "desc": "optional free text",
      "link": "https://optional-url"
    }
  ],
  "edges": [
    { "from": "lab1", "to": "telo", "label": "studies", "dir": "in", "time": "optional" }
  ]
}
```

## `meta`

| key | meaning |
|---|---|
| `title` | shown at the top of the render |
| `schema` | always `kg/1`; the engine stamps it |
| `app` | **the app that renders this graph** — the name of a template in the skill's `assets/` (`viewer` → `assets/viewer.html`). Omitted means the shipped `viewer.html` |
| `app_url` | where to fetch that app if it is not installed. `new` seeds it from the built viewer's own `<name>.version` sidecar, so a graph carries the way to render itself |
| `requires` | what the graph needs beyond the document: `{ "skills": [], "plugins": [], "tools": [] }`. Written by `require`; read by `check` |
| `colors` | kind → hex colour. Seeded from the default palette; extend it with `set-palette` |

`app` is how the document stays independent of any one viewer: it names *what drawer to
use*, and an app it does not have can be fetched and dropped in without touching the
JSON. `render --app <name>` overrides it for one run; `apps` lists what is present,
`info` / `validate` tell you when a graph names an app that is missing, and `check` puts
all of it together: the app, whether it is here, where its `app_url` would fetch it from,
and what `requires` declares.

`requires` is a **declaration, not a manifest of installed things.** A skill can be looked
for (a folder with a `SKILL.md` under `$KG_SKILLS_PATH`, `.codex/skills`, `.claude/skills`
or `~/.hermes/skills`); a tool like `openalex` cannot be verified from a JSON file, and
`check` says so instead of pretending. The point is that a document can tell the next
agent — or the next human — what it was built with.

An older or hand-written file with a partial `colors` map is **healed on the next
write** — missing kinds are filled in from the default palette, so the legend never
silently drops a colour.

## Nodes

| field | required | meaning |
|---|---|---|
| `id` | yes | stable, unique, short. Edges refer to it. Never reuse it for different content |
| `label` | yes | what the reader sees |
| `kind` | yes | the type. Determines colour. Any string is allowed |
| `level` | no | vertical position, the third axis: convention is low = foundational/concrete, high = abstract/evidence. **The 3D view is the only place it moves anything** — a ring- or force-laid-out 2D map ignores it, and a graph that does not use it should not carry it |
| `size` | no | a weight **set by hand**, in the same units as `weight`. Leave it out and the node is drawn from its `weight` instead |
| `weight` | no | how important the node is **on this map**: the number the drawing is a picture of. Half the summed power of the node's edges times a multiplier for its kind, unless the document states it (see *How a node's size is decided*) |
| `style` | no | `solid` (settled), `hollow` (proposed), `cloud` / `critter` (threatening or eroding), `skull` (abandoned) |
| `desc` | no | free text |
| `link` | no | a single URL. Adapters lift URLs out of `desc` when a format buries them there (see `scripts/adapters/`) |
| `x`,`y` | no | authored position. If **every** node has them they are used as given; if any node carries `ring` the rings are built; with neither, the graph is laid out in the browser on open (the page says `layout computed here`) |
| `ring` | no | placement as a concentric ring: `0` is the centre, higher numbers are further out. The usual assignment is organisations 0, researchers 1, publications 2, subjects 3 |
| anything else | no | a property in its own right. Carried through untouched and given its own row in the panel |

`level` and `style` are what make a graph readable at a glance instead of a hairball.
A graph where everything is `level 0, style solid` is a ring of dots and argues nothing.

### How a node's size is decided

```
weight = ½ × (sum of the powers of the node's edges) × kind multiplier
        ↑ the document's own `weight`, when a node states one
drawn radius in px = 2.5 × √weight            (floor 1.5 px, ceiling 28 px)
```

The multipliers say what a kind is worth on *this* map: a publication is a small element of a
field map (0.1), a researcher is the middle (1), a lab, institution or company is a body of work
(3), a subject or concept is what the map is about (10). They are **data** — a graph carries its
own, and `weigh --mul subject=20` changes it for that graph alone:

```json
"meta": { "weight": { "metric": "relevant papers", "kind_multipliers": { "publication": 0.1, "subject": 10 },
                      "note": "one relevant paper per unit of connection" } }
```

**The declared metric is what the drawing follows.** `metric` is a phrase the panel shows beside
every weight (*"weight 0.203 — by relevant papers"*), so a reader can tell what a circle is a
claim about. Stating the weights beats declaring a formula: a node whose `weight` the document
gives is drawn from it, and every node's row says which of the two it came from.

That is the honest way to change what the map measures. Weighting a field by **contribution in
relevant papers** is a fair first assumption; being asked to weigh it by **grant money raised**
instead is the same graph with one property rewritten per node, and the panel then says so:

```bash
kg.py set-node --id max-planck --set weight=48        # €48m of grants, the unit is in the metric
kg.py weigh --graph longevity --metric "grant funding (€m)" --bake
```

`--bake` writes the result into each node's `size`, so a graph that has to look the same
everywhere carries the numbers itself.

### One kind axis, and what a viewer may do with it

The multipliers are not only a drawing rule: they are the map's own notion of **level**, and a
viewer is free to read them that way. The viewer that ships with this skill uses them for
**collapse** — folding a node's part of the map away without deleting anything from the document:

- It descends from the node you collapsed *down* the multipliers: a company (3) takes its people
  (1) and their papers (0.1) with it, and neither the concepts those papers are about (10) nor a
  partner company (3) is touched. Nothing at or above the level you started from is hidden.
- What is hidden stays readable as **counted lines from the node you collapsed** — two of a
  company's papers about model organisms give it one line to model organisms at power 2.
- Those lines are the **view's own**: they exist in the page, never in `kg.json`. A document that
  never mentioned them is still the document, and `validate` never sees them.

Which relations a collapse may cross is the graph's to decide:

```bash
python3 scripts/kg.py visuals --graph my-map --hierarchy "works at,authored"
```

With a hierarchy declared, only those relations are crossed — a citation into a company's paper
is a fact about the field, not a membership. With none declared, any relation may be crossed.

**The walk is strictly downhill, and that is the whole rule.** A step is allowed only from a node
to a neighbour of a *lower* level than that node: a company takes its people, its people take their
papers, and a paper has nothing below it, so the walk stops there. Nothing at or above the level
you started from is ever hidden.

Getting this wrong is easy in both directions, and both were tried: walking down from the *node
you started at* rather than from where you are lets the descent climb back up out of a paper into
every co-author on the map (one company swallowed 48 of 81 nodes); guarding on "is the visible map
still holding this?" instead left 56 of 59 nodes with a button that did nothing at all. If you
change this rule, sweep **every** node in a real graph — checking the one node you designed it
around proves nothing.

Because it is the same axis the document already declares, a graph can change what collapse does
by declaring different multipliers — no code, no setting.

### Adding a property or a kind is a data act, never a code change

The viewer has no list of fields and no list of kinds: it draws
what it is given, colours a kind from `meta.colors` (falling back to a stable hash), builds
the legend from the kinds actually present, and gives every property it does not lay out
itself its own row in the panel. A value that looks like a DOI or a URL becomes a link there.

| you want | command |
|---|---|
| a property on a new node | `add-node … --set doi=10.1126/science.abn9257` (repeatable) |
| a property on an existing node | `set-node --id <id> --set key=value` |
| a property on an edge | `add-edge … --set rel=co-cited` |
| a new kind | `set-palette --kind paper --color "#8b93a1"`, then `add-node --kind paper` — legend and colours follow |
| a new edge relation | `add-edge … --label "co-cited in 66 works"` — an edge's relation is its label |

`doi` is the canonical case. A work — a paper, a trial, a patent — that a graph promotes to a
node carries its DOI as **an identifier, not prose**: `desc` carries sentences, `doi` carries
the one string that finds the record again, and the panel resolves it to `https://doi.org/…`
rather than leaving the reader to dig it out of a paragraph.

**A property you set that does not appear is an app bug, not a graph problem.** Report it —
do not go and edit the viewer's source to make your own field visible.

## Edges

| field | meaning |
|---|---|
| `from`, `to` | node ids |
| `label` | what the relation is. Unlabelled edges render as bare lines — avoid |
| `dir` | `in` = the relation points at `to`; `out` = it points at `from`; `both`. Omit for an undirected relation |
| `style` | what the relation **looks** like, space-separated: a stroke (`solid`, `dashed`, `dotted`) and/or a shape (`arrow`, `double`, `clamped`, `rectangle`, `triangle`). `--style "dotted arrow"`. An unknown word is refused rather than stored: a style the renderer ignores is a silent loss of meaning |
| `color` | this relation's own colour, e.g. `#8fa3c8`. `--color` |
| `dash` | an explicit dash pattern, e.g. `"6 4"`. `--dash`. Drawn on the 2D overlay layer, so any pattern works |
| `width` | an explicit line width in px, for when `power` is not the right control. `--width` |
| `time` | optional estimate or date, e.g. `2018`, `"18mo"`, `"years"` |
| `power` | how much this relation weighs, where **1 is a normal relation** and 0.05 is one that barely counts. Drawn as line thickness; below 0.5 it is a hairline at half opacity. `--power`, `--weight` (the older spelling), or `--set power=0.05` |
| `count`, `cocited`, … | a measured number is **data, not emphasis**: `--set cocited=66` puts "66 papers cite both" in the panel, while the power stays the emphasis you meant |

**Three conventions worth more than the schema.**

A piece of work — a paper, a trial, a patent — may be an **edge** (`from` the researcher,
`to` the subject, `label` the title, `time` the year) or a **node** of kind `publication`
carrying its `doi`. The node form is what to use when the work itself has to be connected to
anything: a DOI of its own, a co-citation count against another work, a venue. An edge cannot
be cited; a node can.

Two organisations working on the same subject get an edge **between them**, labelled with
that subject — that is what makes a cluster legible instead of a fan of lines into one dot.

A **citation** is an edge with a direction: `--from` the citing work, `--to` the cited one,
`--dir in`. Direction is *stored* by `dir` and *drawn* only when asked: `visuals --arrows on`
for the whole graph, or `--style arrow` on one relation. A citation map wants heads; a field map
usually reads better without them, and the choice belongs to the graph, not to the viewer.

A **co-citation** is a weak relation between two works, and it should look weak in both
dimensions: `--power 0.05 --style dashed --set cocited=66` says *66 papers cite both, this is
background, not structure*. A field map reads well when the citation skeleton is strong and the
co-citation texture is faint and broken; a graph where co-citations are as loud as authorship
argues nothing. (The engine warns when a node is labelled a co-citation at power > 0.1, because
that mistake is silent until somebody looks at the picture.)

Size and placement are asked for, not applied: `weight` or `size` on the nodes you care about,
`power` on the relations that matter, `ring` to say centre/middle/periphery. Everything left out
is filled in from the graph itself, so a document with none of them still reads.

## `meta.visuals` — how this graph wants to look

Taste is data too, so it lives in the document. The app has defaults; a document overrides them,
which is the difference between "the viewer draws arrows" and "this graph draws arrows".

| key | meaning |
|---|---|
| `arrows` | draw a head on a directed relation. **Off unless asked for** (`visuals --arrows on`) |
| `edge_width` | multiply every relation's width (`visuals --edge-width 1.4`) |
| `node_scale` | multiply every node's radius |
| `halo` | draw a ring around a node that has nodes collapsed inside it (default on) |
| `max_nodes` | the node budget this graph was *measured* at (`capacity --nodes 4000 --note "…"`). A fallback, not a rule: the viewer measures the host it is running on |

## Notes: the long form of a description

A graph says what is connected to what. It does not say what any of it means, and for a field
being surveyed that is most of the work. So the long form of a node's description is a markdown
file in a `docs/` folder beside the document — one subject, one folder, its own notes:

```
storage/longevity-map/
  graph.json
  index.html            # written by render; the page you hand to somebody
  docs/
    overview.md         # the subject itself: what this map is, what it is missing
    hallmarks.md        # one node's note, pointed at by the node's `doc`
```

`kg.py note --graph <id> --node <hallmarks>` creates the file from a skeleton and sets
`doc: docs/hallmarks.md` on the node; `kg.py note --graph <id>` writes the subject's overview
note. `render` inlines every note into the page (a page opened from `file://` cannot fetch its
neighbours), where it appears in a second panel — reachable from the node's **read the note**
button, or the header's **notes** button for the overview.

The panel reads notes anywhere and can edit a *copy* anywhere: **a page opened from `file://`
cannot write to the reader's disk.** The ways back to the file are explicit — download, copy, or
hand it to the agent that owns the folder. This is a real constraint of the shape (a file, no
server), not an unfinished feature, and the reason the notes stay plain markdown in a
predictable place.

**A body must say what it is.** `subject`, `concept`, `lab`, `institution` and `company` nodes
are refused by `add-node` without `--desc`: one sentence saying what the thing is and why it
matters *for this subject*. Publications are exempt — a title and a DOI are their identity. A
description is written about something at a moment, so the engine records the node's connection
count when the sentence is written (`desc_rev`); `review` then lists the bodies the graph has
grown past, which is the work of keeping a survey honest rather than a formality.

## What the engine guarantees

- `new` and every write create the parent directory, so `--out kg/deep/x.json` works.
- Writes are whole-file; there is no partial merge. Copy before a bulk update.
- `stats` reports counts by kind, style and level, plus any kind with no colour.
- `check` reports whether the graph can be shown here: the app, its `app_url`, and what
  `requires` declares — exiting non-zero when the app is missing.
- `render` emits a self-contained page — no CDN, no network, opens from disk.
- `render` is the only way a graph becomes a page: `render`, refresh the tab, done. No
  server exists in the engine, so no port, no PID and no URL that can go stale.

## Portability

The format has no notion of a host, a user, or a project. A graph file can be moved,
committed, emailed or published as-is, and the same file renders identically elsewhere.
