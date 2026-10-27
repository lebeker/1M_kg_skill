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
| `level` | no | vertical position, the third axis: convention is low = foundational/concrete, high = abstract/evidence. **The 3D view is the only place it moves anything** — a ring- or force-laid-out 2D map ignores it, and a graph that does not use it should not carry it. In 3D the level span is scaled to the picture's own width, so a map is tilted rather than spiked |
| `z` | no | **where the node sits in depth, when you want to say it yourself.** It wins over `level`, and `level` wins over `weight`: the viewer only reaches for its own rule when the document said nothing. Use it for a shape no level can express — a basin, a ridge, a deliberate outlier. Same units as `x`/`y` |
| `size` | no | a radius **set by hand**, in pixels, overriding what the node's `weight` would draw. It exists for emphasis the connections do not support — a hub that matters for a reason the map cannot see. Leave it out and the radius comes from `weight`; `weight` is the claim, `size` is the override |
| `weight` | no | how important the node is **on this map**: the number the drawing is a picture of. Half the summed power of the node's edges times a multiplier for its kind, unless the document states it (see *How a node's size is decided*) |
| `style` | no | `solid` (settled), `hollow` (proposed), `cloud` / `critter` (threatening or eroding), `skull` (abandoned) |
| `desc` | no | free text |
| `link` | no | a single URL. Adapters lift URLs out of `desc` when a format buries them there (see `scripts/adapters/`) |
| `x`,`y` | no | authored position. If **every** node has them they are used as given; if any node carries `ring` the rings are built; with neither, the graph is laid out in the browser on open (the page says `layout computed here`) |
| `ring` | no | placement as a concentric ring: `0` is the centre, higher numbers are further out. The usual assignment is organisations 0, researchers 1, publications 2, subjects 3 |
| `cited_by` | no | how many works the index says cite this one. **A count, not a list.** Store it with `cited_by_source` (`openalex`, `crossref`, `s2`) and `cited_by_at` (a date) — a bare number ages into a lie. It comes free with any record you fetch; never pay a search for it |
| `desc_rev` | no | **bookkeeping, not content**: the node's degree at the moment its description was written. `validate` uses it to warn that a description went stale. The panel never shows it |
| anything else | no | a property in its own right. Carried through untouched and given its own row in the panel |

Three numbers are worth distinguishing, and only one of them is stored:

```
cited 300 · 6 here · 20 pulled
      │        │        └── the list you actually fetched (OpenCitations `/citations/<doi>`, free)
      │        └────────── computed from the `cites` edges already drawn — never stored, so it cannot
      │                       disagree with the picture
      └─────────────────── `cited_by`, from the record
```

The middle one is the only one that can be computed, and the right one is the only one that can be
bought. A fourth number that is a judgement ("20 relevant") has no source and does not belong in a
document.

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

### One kind axis, and what `level` means

The multipliers are a drawing rule. `level` is the map's own notion of **depth** and nothing
more: concepts at 2, publications at 3, people at 4, labs at 5, institutions and companies at 6.
It is structure a reader may use; it is not a drawing setting. `weight` says how big a node is
drawn and says nothing about who contains whom.

**The anchors are whole numbers, and a node may stand anywhere between them.** The numbers
above are what the app *suggests* for a kind (`meta.levels`, seeded by `new`); the document
always wins. A level is a real number on one axis, so a hierarchy that a kind cannot express
is written between the anchors:

| what is being levelled | level | why |
|---|---|---|
| a root concept | `2` | it is the top of its own tree |
| a sub-concept | `2.2`, `2.4`, `2.6` … | deeper than its root, still above every publication |
| a satellite paper | `3.2`/`3.4` | a publication, but not one the map is about |
| a principal author | `3.6` | a person who matters more than the paper they wrote |
| a group the agent invented | any value between two anchors | a graph of one kind still folds if the agent groups it |

Two consequences worth knowing before you assign levels:

- **A single-kind graph does not need levels.** Eight publications at 3 have nothing to fold
  into — that is a map, not a hierarchy. If it is too big to read, the answer is to *add*
  grouping nodes (a `subject` at 2 with its own sentence) and let them fold, not to invent
  levels that no edge supports.
- **A level is only as good as the edges under it.** Two nodes at different levels that share
  no edge are two branches, not a parent and a child. Folding follows edges; the level only
  tells it which way is down.

**Folding is the webapp's job, not the document's.** The document says what exists and how deep
it sits; the viewer decides what to hide, what to count, and how to draw what is left. Nothing in
`kg.json` describes a fold, and the engine has no command that folds — a document that carries
view state is a document that only one viewer can read.

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

## `meta.limits` — how much of this graph to draw at once

Two numbers, and two only:

```json
"meta": { "limits": { "nodes": 500, "edges": 5000 } }
```

They are a **request addressed to the page**, not a rule the engine enforces: the document is
written whole, and how much of it is drawn is the page's decision on the host it is actually
running on. When a graph is over them, the page opens **grouped to its top layer** and says so,
and drawing everything is a two-step decision, because it is the one operation that can make the
tab unusable. A reader — or a measurement of a faster machine — may rewrite the numbers later:

```
kg.py limits --graph <id> --nodes 2000 --edges 20000
kg.py limits --graph <id>            # what it asks for, and where it stands
```

`validate` treats a graph over its own numbers as conformant with a note, never an error.

## `meta.edges` — relations that are declared, not repeated

A relation is a decision about *direction* and *ends*, and that decision belongs in the document
once, not in every edge:

```json
"meta": { "edges": [
  { "name": "cite",     "dir": "out",  "from": ["paper"],    "to": ["paper"],    "color": "#3f6fd8", "style": "arrow" },
  { "name": "part-of",  "dir": "out",  "from": ["concept"],  "to": ["concept"],  "color": "#7c8aa0" },
  { "name": "field-of", "dir": "out",  "from": ["scientist"],"to": ["concept"],  "color": "#c89b3c", "style": "dotted" }
] }
```

- `dir` — `none` (undirected), `out` (the arrow points at `from`), `in`, `both`.
- `from` / `to` — the kinds allowed at each end. Empty/absent means any kind.
- `color`, `style`, `power` — the default look. An edge that sets its own keeps it.

An edge inherits them by its `label`, so `add-edge --rel cite` writes one edge with no repeated
attributes, and changing the declaration changes every `cite` edge at once. `validate` refuses an
edge that breaks the contract (`cite` running into a concept is an error, not a style choice), and
the viewer reads the same declarations, so what the engine checks is what the page draws.

## History — a batch is a version, not a command

If `git` is installed, `save` records changes, staging only that graph's folder. Nothing leaves
the machine; without git the engine works exactly as before.

Consecutive edits land in **one commit, amended in place**, until the batch is closed. One commit
per command produced 437 commits for one 35-node article — a history nobody can read, and a
rollback target for every keystroke. What a reader asks for is "put it back the way it was before
this turn", so the unit of history is the batch:

```
kg.py commit  --graph <id> -m "what this batch did"   # seal it, with a sentence a person wrote
kg.py history --graph <id> [--limit 12]
kg.py undo    --graph <id> [--steps 1]
```

- A batch closes when you seal it with `commit -m`, after `KG_SQUASH_WINDOW` seconds (default
  1800) with no new edit, or when `KG_NO_SQUASH=1` asks for the old one-commit-per-command.
- **Seal a batch when the user's request is finished**, not after every step: the user sees
  "before you started" and "after", so that is the pair a rollback has to restore.
- `undo` restores the graph from `steps` recorded batches ago and is recorded as a batch of its
  own, so it can itself be undone.
- `KG_NO_GIT=1` opts a workspace out entirely.

## `meta.layout` — who decides where the dots go

`x`/`y` belong to the viewer, not to the author. A document can say which rule draws it:

| `meta.layout` | what happens |
|---|---|
| `"force"` | the coordinates in the file are ignored; the page lays the graph out from its edges |
| absent, every node has `x`/`y` | the author's placement, used as given |
| absent, nodes carry `ring` | rings are built: 0 at the centre, higher numbers further out |
| absent, no geometry | force, from a deterministic start (the same file looks the same twice) |

`meta.layout` is a **default**, not a law: the page carries an `x/y · force` switch next to the
2D/3D buttons and the reader can overrule the file at any time. 3D reads the same switch — with
`x/y` it holds every node where the document put it and uses `level` as depth, so the two views
are one picture seen from two angles; with `force` it runs its own simulation. A node may carry
`x`, `y` and `z`; the z is depth in 3D and is ignored in 2D.

Writing coordinates by hand is the most expensive thing an author can do — 221 of 437 commands in
one real run were `set-node`, almost all of them moving a dot. Place roughly, in a box, and leave
it: `force` is there if the picture needs redrawing, and the reader can press it without you.

## `meta.visuals` — how this graph wants to look

Taste is data too, so it lives in the document. The app has defaults; a document overrides them,
which is the difference between "the viewer draws arrows" and "this graph draws arrows".

| key | meaning |
|---|---|
| `arrows` | draw a head on a directed relation. **Off unless asked for** (`visuals --arrows on`) |
| `edge_width` | multiply every relation's width (`visuals --edge-width 1.4`) |
| `node_scale` | multiply every node's radius |
| `halo` | draw a ring around a node that has nodes collapsed inside it (default on) |
| `labels` | `on`, `hover` or `off` — how much of the map is named at rest (`visuals --labels hover`). Default: `on` up to 50 nodes, `hover` above |
| `max_nodes` | superseded by `meta.limits` — kept readable, no longer written |

**A relation's words are its type, and a measured number is a property.** `co-cited in 66 works`
is not a relation type, it is one relation word wearing a number: nineteen such edges are nineteen
types, so no reader (and no legend) can switch co-citation off as a kind. Write the type as the
label and the count as a property:

```bash
python3 scripts/kg.py add-edge --graph my-map --from p1 --to p2 --label "co-cited" \
  --power 0.05 --set cocitations=66
```

`power` is the emphasis (0.05 = texture, drawn as a hairline); `cocitations` is the measurement,
which the panel prints as its own row.

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

## Originals: the document behind a node

A supplied measurement, analysis or scan is **a file first**. It is kept beside the graph, never
inside it:

```
storage/<graph>/
  graph.json
  originals/
    2024-11-07-dobrobut-805248681.pdf
    2024-11-07-dobrobut-805248681.png
```

`attach --node <id> --file <path>` copies (or `--move`) the document in, hashes it, and writes the
reference onto the node. The same document attached twice is one entry — the hash is the identity.

```json
{
  "id": "lab-2024-11-07",
  "label": "Лабораторні дослідження № 805248681",
  "kind": "analysis",
  "date": "2024-11-07",
  "panel": "Вуглеводний обмін",
  "originals": [
    { "path": "originals/2024-11-07-dobrobut-805248681.pdf", "bytes": 51234,
      "sha256": "…", "added": "2026-10-27" }
  ],
  "values": [
    { "name": "Глюкоза", "value": 4.94, "unit": "ммоль/л", "ref": [4.11, 5.89] }
  ]
}
```

`validate` fails when an `originals` path does not exist: a node that says it has the document must
have the document.

### What an analysis says about an organ

An analysis does not "belong" to a body part by convention; it **points at it with an edge**, and
the edge carries the two numbers the picture is made of:

```json
{ "from": "lab-2024-11-07", "to": "pancreas", "label": "assesses",
  "evidence": 82, "confidence": 70 }
```

| field | range | meaning | drawn as |
|---|---|---|---|
| `evidence` | 0–100 | how strongly the result argues that the organ is **functioning normally** — 100 is a clean result, 0 is clearly wrong | the colour: **green → yellow → red** |
| `confidence` | 0–100 | how much the result can be trusted for that organ — a single fasting glucose is weaker than an HbA1c plus a repeat | the opacity of the edge (and of the analysis node) |

Both are **the document's own numbers** — a lab report with one raised marker out of twelve is not
`evidence: 0`. The skill writes them; the app only paints them. A renderer that hard-codes a
different rule is disagreeing with the data in public.

The same two numbers govern how an analysis fades as the user walks the timeline away from its
date: the further the chosen date from the analysis's `date`, the weaker its claim, and the app
draws it accordingly. The `date` is the anchor; nothing else in the document moves in time.
