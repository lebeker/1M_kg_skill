---
name: kg
description: >
  Turn a research field into a knowledge-graph you can look at, and keep it current.
  Use when the user asks to "map a research field", "show me what's happening in
  <field>", "build a knowledge graph", "graph these papers",
  "who works on <topic>", "track this research direction", "see what changed since
  last time", "turn this bibliography into a map", "visualise my literature review",
  or wants to explore, enrich, import, validate or render an existing kg/1 graph JSON.
  Also use for "what graphs do I have", "show me the <name> graph", "let's work on
  <graph>", "open the knowledge graph", or asks for a
  graph of something and needs the right kind of map for it. Produces a
  self-contained interactive HTML page — pan, zoom, search, collapse — plus a
  validated, shareable JSON artifact.
version: 0.7.0
author: Denis Tatarenko
license: MIT
platforms: [macos, linux]
---

# kg

Turn a research field into a graph you can **look at** — then keep it current.

This skill produces a self-contained HTML page from a small JSON document: what the
field is made of, who works on it, what is applied versus speculative, and what changed
since last time. A text dump of the same facts tells you far less, so the loop below
always ends with someone *looking at the picture*.

**This skill is self-contained.** It has no dependencies on any other project, and its
paths are relative to this folder. `ENGINE` is used throughout as shorthand:

```bash
export ENGINE="$PWD/scripts/kg.py"     # run from this folder
```

✅ `test -f "$ENGINE"` exits 0 and `python3 "$ENGINE" --help` prints the command list.

## Start here

If you have just been pointed at this folder and are not sure what to do, run these
three commands and read the output. They tell you everything:

```bash
python3 "$ENGINE" --help        # the whole command surface
python3 "$ENGINE" graphs        # what graphs exist, and which one is current
python3 "$ENGINE" render        # build the current graph's page and print a link
```

✅ You can state the command surface, what graphs the workspace holds, and the link you
printed.

**On a clean slate** — `graphs` prints nothing, or the folder you were pointed at has no
`storage/` — there is nothing to find, and looking for a sample graph is wasted work.
The workspace is created by the first graph in it:

```bash
python3 "$ENGINE" new --id field --title "My Field"
```

The shape it writes is the whole format, and it is small:

```json
{
  "meta": {
    "title": "Telomere attrition — mini example",
    "schema": "kg/1",
    "app": "viewer",
    "app_url": "https://…/viewer-v0.0.30/viewer.html",
    "requires": { "skills": ["kg"], "plugins": [], "tools": ["openalex"] }
  },
  "nodes": [
    { "id": "telo",    "label": "Telomere attrition", "kind": "concept",     "level": 1, "size": 4 },
    { "id": "greider", "label": "Carol Greider",      "kind": "scientist",   "level": 3, "size": 3 },
    { "id": "jhu",     "label": "Johns Hopkins",      "kind": "institution", "level": 4, "size": 2 },
    { "id": "unity",   "label": "Unity Biotechnology","kind": "company",     "level": 4, "size": 2 },
    { "id": "calico",  "label": "Calico Life Sciences","kind": "company",    "level": 4, "size": 2 }
  ],
  "edges": [
    { "from": "greider", "to": "telo",   "label": "Telomerase activity and cellular aging", "dir": "in", "time": 2018 },
    { "from": "greider", "to": "jhu",    "label": "works at" },
    { "from": "unity",   "to": "calico", "label": "collaborates on telomere biology" }
  ]
}
```

Five nodes are enough to check the whole loop — create, add, validate, render, look. Do
that once on any new setup before trusting the skill on a real field.

`references/format.md` is the format in full (every field, and what the engine
guarantees). `examples/` is deliberately empty: a sample graph in this folder would go
stale and start lying about the format the engine actually writes.

## The workspace

Graphs live in **one folder each**, and the whole thing is a workspace you can look at:

```
<root>/storage/<id>/          ← one graph, self-contained
    graph.json                ← the kg/1 document the engine reads and writes
    <raw export>              ← where it came from, if it was imported
    index.html                ← the rendered page, written next to its graph
<root>/storage/.current       ← which graph you are working on
```

`<root>` is `$KG_WORKSPACE` if you set it, otherwise the directory you run from. Never
hardcode a host path into the skill or into a command you hand the user — the workspace
is wherever they are.

**`--graph` takes an id from the workspace or a path to any `.json`**, and every command
that reads or writes a graph takes it. With no `--graph` at all you get the current
graph. That is what makes the three asks answerable:

| the user says | you run |
|---|---|
| "what graphs do I have?" | `python3 "$ENGINE" graphs` |
| "show me the longevity one" | `python3 "$ENGINE" render --graph longevity` → give them the `file://` link it prints |
| "let's work on longevity" | `python3 "$ENGINE" use longevity` — every later command needs no `--graph` |
| "what's in it?" | `python3 "$ENGINE" info` |
| "show me the graph", "open it" | `python3 "$ENGINE" render` → then the preview pane, or `open --html <the page>` | prints |
| "which viewers are there?" | `python3 "$ENGINE" apps` |
| "can I see this one?" | `python3 "$ENGINE" check` — reports the app, what the graph needs, and what is missing |
| "it needs openalex" | `python3 "$ENGINE" require --tool openalex` — records it on the graph |

`graphs` marks the current one with `*`. `use` and `current` set and show it; `use`
refuses an id that is not there rather than pretending.

## From an ask to a graph

Nobody says "produce a `kg/1` document". They say what they want, and you have to land on
the right *shape* of graph before anything else. The app decides the shape: it declares what
it is for, what it needs to be useful, and which node kinds and edges a graph for it is made
of.

```bash
python3 "$ENGINE" suggest "map the cryogenics research field"
```

`suggest` picks the app that fits the words and prints what it is for, whether it is
installed, every skill/plugin/tool it **requires** — each with what it is for — what it only
*suggests*, the kinds to build with, and the edge patterns to follow.

| the user says | you run |
|---|---|
| "map the longevity field", "graph these papers" | `suggest "<their words>"` |
| "build me a graph for X" | `new --id x --title "X" --app viewer` |
| "what can this thing draw?" | `apps` |

1. **Say which app fits, and why — in one or two lines.** Not a catalogue dump: "this is a
   field map; the app is `viewer`, and it is built from OpenAlex."
2. **Say what is missing and what it is for.** Skills are checked on this machine; tools
   cannot be — a JSON file cannot see an MCP server. Name the tools you will work from and
   what the graph loses without them (for a field map: no works, no authors, no
   institutions — you would be inventing the field's contents).
3. **Install nothing without a yes.**
   ```bash
   python3 "$ENGINE" fetch-app viewer     # the viewer, and the app's own declaration
   ```
   That page will run in the user's browser with their data inside it. Say where it comes
   from, then ask.
4. **Create the graph from the app's conventions, not your own.**
   ```bash
   python3 "$ENGINE" new --id cryo --title "Cryogenics" --app viewer
   ```
   `new --app` writes `meta.app`, `meta.app_url` and the app's `requires` into the graph,
   seeds the palette with the app's kinds so `stats` never warns, and prints the kinds and
   edge patterns to build with. `new --ask "…"` does the same, picking the app from the
   user's own words.
5. **Then build it and show it** — the procedure below. The graph is the deliverable; the
   app only decides its shape.

**Where this knowledge lives.** `scripts/apps.json` is this skill's own short list of known
apps, so the first question can be answered before anything is installed. Once an app is
installed, **its own declaration** (`assets/<name>.app.json`, fetched beside the viewer)
takes over — the app defines the goal and the skill does not argue with it. A discovery
service for the paid tier replaces that list, not the commands that read it. Full schemas:
`references/apps.md`.

## Controlling the picture

Two ways to control how a graph looks, and both are data — never a change to the viewer.

**Direct: the user asks for it.**

| the user says | you run | what it does |
|---|---|---|
| "make these bigger", "this is the important one" | `--set weight=8` (`set-node --id x --set weight=8`) | node size, in the graph's own units |
| "this relation is strong", "this one is background" | `add-edge … --power 1.5`, `set-edge --from a --to b --power 0.05` | line thickness — 1 is normal, 0.05 is a hairline |
| "66 papers cite both" | `--set cocited=66` and a low `--power` | the count is data; the power is emphasis |
| "companies in the centre, subjects on the periphery" | `--set ring=0` … `--set ring=3` | concentric placement |
| "move this one to the left of that" | `--set x=-800 --set y=0`, `set-node … --set x=…` | exact position |
| "make that one a different colour" | `set-palette --kind preprint --color "#aabbcc"` | a kind's colour |
| "I don't want to see arrows" | `visuals --graph X --arrows off` (the default), or `--style arrow` on one edge | whether a directed relation gets a head — the graph decides, not the viewer |
| "those edges should be blue and dotted" | `add-edge … --style dotted --color "#8fa3c8"`, or `set-edge --from a --to b --style "dashed arrow"` | the relation's appearance: stroke (`solid`/`dashed`/`dotted`), shape (`arrow`/`double`/`clamped`/`rectangle`/`triangle`), colour, dash pattern, width |
| "arrows should show what cites what", and the same relation is used 2,000 times | `declare --edge cite --dir out --from paper --to paper --color "#3f6fd8"`, then `add-edge … --rel cite` | the relation's direction, its allowed ends and its look are declared once; every edge of that name inherits them, and `validate` refuses an edge with the wrong ends |
| "undo that" / "what changed?" | `history --graph <id>`, `undo --graph <id> [--steps n]` | changes are committed in batches when git is present (only that graph's folder), so a wrong sweep is one command back |
| "this graph should read bigger/smaller" | `visuals --graph X --edge-width 1.4 --node-scale 1.2` | global scale for the whole graph |
| "10k articles, but my laptop dies" | `limits --nodes N --edges M` — two numbers the page respects by opening the graph grouped; write the graph anyway | how much is drawn at once; the page decides how, the numbers only say how much it should try to hold |

**Intrinsic: what happens when nobody asks.** A node with no `weight` and no `size` is drawn
from ½ × the summed power of its edges × a multiplier for its kind; an edge with no `power` is
an ordinary relation; a graph with no `ring` and no positions is laid out by the viewer. This is
the default because a map has to be legible on arrival — the user should be adding emphasis, not
making the thing readable in the first place.

**Say what the sizes mean.** `weigh --graph X --metric "relevant papers"` records the method in
`meta.weight`, and every panel row then reads `weight 0.203 — by relevant papers`. Contribution in
relevant papers is the fair first assumption; being asked for grant money, headcount or citations
instead is `set-node --set weight=…` per node plus a new `--metric`, with nothing else touched.
A graph that does not say what its circles measure cannot be argued with. `references/recipes.md`
has this, and the two other jobs (a paper-only citation map; the whole field), as command
sequences.

**Bodies must say what they are.** `subject`, `concept`, `lab`, `institution` and `company`
nodes are refused by `add-node` without `--desc` — one sentence, general and relevant to this
subject. That is not a formality: on a field map those sentences *are* the reading. When a
sentence is not enough, `note --graph X --node <id>` writes `docs/<slug>.md` inside the graph's
folder and points the node at it; `note --graph X` writes the subject's own overview note, which
is the draft of whatever is being written about this map. `render` inlines every note into the
page, where it opens in a second panel. `review --graph X` is the work list: bodies with no
description, and bodies whose sentence was written when the node had fewer connections than it
has now. `set-node --id <n> --desc "…"` rewrites one and re-dates it.

**The page cannot write to the reader's disk.** It is opened from `file://`, and a browser
refuses that; so the note panel edits a copy and offers download, copy, or handing the text to
the agent that owns the folder. Say this rather than promising a save button.

`ring` beats a force layout (the page then says `· arranged by ring`) and every node with
`x`,`y` beats both. The two coexist: a node with a ring *and* an `x`,`y` keeps the position
it was given.

## The starter vocabulary, and what is not in it

A research map starts from six kinds — `publication`, `researcher`, `subject`, `lab`,
`institution`, `company` — with meanings and default rings in the app's declaration
(`app.json` → `kinds`, `visuals`). `publication` is the one to reach for first: it is what a
DOI identifies, and it is the main object of a field map.

A kind outside the list is not an error: it renders, it gets a stable colour, it appears in
the legend, and any property it carries gets its own panel row. The same is true of a
property — `add-node --set venue=Nature` needs no declaration anywhere. So when the graph
wants a `trial`, or a `funding round`, or a `patent`, the answer is `add-node --kind trial`,
not a new viewer. **If something set this way does not render, that is an app bug worth
reporting — not a reason to edit the app.**

## When to Use

- "map this research field", "show me what is happening in X"
- tracking a narrow direction over time and seeing what changed since the last run
- finding what is near-applied, and which company or group is behind it
- importing an existing graph from another tool's export
- Don't use for: literature search by itself (use Scholar/Litmaps/ResearchRabbit), or
  for facts with no relational structure at all.

## Procedure

1. **Create or open the graph.**
   ```bash
   python3 "$ENGINE" new --id field --title "My Field"   # -> storage/field/graph.json
   python3 "$ENGINE" use field                            # later commands need no --graph
   ```
   ✅ `new` prints `created …` and `current graph is now field`. `new --out <path>` still
   works for a graph that is not part of a workspace.

2. **Add the nodes that carry the structure** — the concepts/questions, and the labs,
   companies or people attached to them. Give each a `level` (vertical position) and a
   `size` (importance).
   ```bash
   python3 "$ENGINE" add-node --id telo --label "Telomere attrition" \
       --kind concept --level 2 --size 4 --style solid
   python3 "$ENGINE" add-node --id lab1 --label "Blackburn Lab" \
       --kind lab --level 3 --size 3 --style solid --link "https://example.org/lab"
   ```
   ✅ `stats` shows the node counts rising and no `no palette` warning.

3. **Add the relations.** Label every edge — an unlabelled edge is a line with no
   meaning. `--dir in` means the relation points at the target.
   ```bash
   python3 "$ENGINE" add-edge --from lab1 --to telo --label studies --dir in
   ```
   ✅ `stats` shows `edges` and no `isolated` list for the nodes you intended to connect.

   **A piece of work is an edge, not a node.** A paper, a trial, a patent: `from` the
   researcher, `to` the subject, `label` the title, `--time` the year. The researcher is
   then *connected to* what they work on, which is the thing the reader is looking for.
   Two organisations working on the same subject get an edge **between them**, labelled
   with the subject — that is what makes a cluster of companies legible instead of a fan
   of lines into one dot.

4. **Check the graph before rendering.**
   ```bash
   python3 "$ENGINE" stats
   ```
   ✅ kinds, styles, levels and any warnings appear. If `stats` reports `no palette`,
   fix it now — `set-palette --kind X --color "#rrggbb"` — or the legend will be
   meaningless.

5. **Render to HTML, then look at it.**
   ```bash
   python3 "$ENGINE" render                  # -> next to the graph, prints the link
   ```
   ✅ the page is far larger than the JSON — the graph is inlined into it, and it opens over
   `file://` with no server and no network.

6. **LOOK AT THE PAGE.** The engine has no screenshot command on purpose: it is python3 only,
   and a headless browser is a dependency the user's machine may not have. Look with whatever
   your own client has — the preview pane, `vision_analyze` on a screenshot you take, or the
   user's browser. **Never report on a graph you have not looked at.**
   ✅ You can name the node kinds, the shapes, the levels, and one labelled relation —
   things the JSON alone does not tell you.

   The viewer fits the whole graph on open, so at that zoom you see **structure only**:
   clusters and dots, no text. That is expected for a few hundred nodes — a 1000-node
   canvas cannot carry 1000 readable labels. Text appears as the reader zooms in, which
   is what the search box is for.

7. **If the picture is wrong** — hairball, overlapping labels, everything on one row —
   fix the **artifact** (levels, sizes, colours, `meta.layout`), not the HTML by hand, and
   repeat from step 5. **Look twice, not forty times.** Two screenshots — after the first
   full render and once at the end — are enough to catch a broken picture. Looking after
   every node is how a graph becomes a canvas: one real run spent 221 of 437 commands moving
   dots and 27 screenshots checking them, while the data sat still. The page has an
   `x/y · force` switch; you do not have to place every dot for the picture to be right.

8. **Work in batches; commit a batch, not a node.** Every write is recorded (when git is
   present) and consecutive edits amend one commit, so a whole turn costs one version. Close
   it when the user's request is done:
   ```bash
   python3 "$ENGINE" commit --graph <id> -m "what this batch did"
   ```
   ✅ `history` shows one line per batch, and `undo` puts the graph back to before the batch —
   which is the only rollback a reader ever asks for.

9. **Validate before you hand over — this is what makes it a shareable artifact.**
   ```bash
   python3 "$ENGINE" validate
   ```
   ✅ prints `conformant — N nodes / M edges, schema kg/1` and exits 0. Fix every
   `error:`; `warning:` lines are judgement calls, `note:` lines are facts about the
   graph you should know before editing it.

10. **Hand it over.** See the next section — this is not optional, and a bare filename
   is not a handover.

## Viewers are pluggable — the skill does not carry its own

`render` does not draw anything. It takes **a template** and puts the graph
into it. A template is a single-file HTML carrying one element:

```html
<script id="kg-graph" type="application/json">__KG_GRAPH__</script>
```

Everything else in the file — React, WebGL, physics, styling — is the template's
business, and the engine never looks at it. `assets/viewer.html` is the viewer that
ships: 2D (sigma + graphology) and 3D (3d-force-graph), both inlined so the page works
off `file://` with no network.

- `python3 "$ENGINE" apps` lists the templates present, whether each one can actually be
  rendered into, and where it came from (the `<name>.version` sidecar records the repo
  and commit it was built from).
- `python3 "$ENGINE" render --app <name>` picks one for this run. Otherwise the **graph's
  own `meta.app`** decides (`new` seeds it with the shipped viewer), and failing that,
  `viewer.html`. That is the interface: the document names the drawer, not a copy of it.
- **If the graph names an app that is not here**, do not substitute another one silently
  — the picture would be wrong and you would not know. Say which app is missing and get it:
  ```bash
  python3 "$ENGINE" apps                  # what is here, and where each copy came from
  python3 "$ENGINE" fetch-viewer --url <url-of-the-single-file-viewer>
  ```
  `fetch-viewer` needs no node and no bun — `assets/README.md` carries the published URL of
  the viewer that ships. Never fetch a viewer implicitly and never from a source you cannot
  name: that page runs in the user's browser with their data inside it.
- To add a viewer: drop another single-file HTML into `assets/` that contains the element
  above, and it is immediately usable by name. **Do not build it here** — a viewer is
  built in its own repo and copied in (see `assets/README.md`).

One trap: replacing the text of that element must not be able to break the page, so a
`</script>` inside the graph is escaped by `inject()`. If you hand-write a template,
keep the element unique — `render` refuses a template with two of them.

Another: **a blank page is a viewer older than the graph.** Positions are optional in the
document, and sigma throws rather than draws when a node has none — during construction,
so the page comes up empty instead of showing a graph. Viewers from 0.0.1 on lay the graph
out themselves and say so in the header (`layout computed here`). If a page is blank,
that is the thing to check first: re-fetch the viewer rather than hunting for the bug in
the graph.

## What a graph needs to be shown

A graph is not only its nodes: it names **the app that draws it** and **what it needs** —
skills, plugins, tools — so somebody else can pick the file up and know what to bring.

```bash
python3 "$ENGINE" check                 # the current graph
python3 "$ENGINE" check --graph field   # any graph in the workspace
```

`check` prints the app the graph names and whether it is here, where to fetch it from if
not, the skills/plugins/tools it declares, and — for skills — whether they are actually on
this machine (it looks in `$KG_SKILLS_PATH`, `.codex/skills`, `.claude/skills` and
`~/.hermes/skills`). It exits non-zero when something **needed to draw the graph** is
missing.

**When something is missing, say what and why, then ask.** Do not install on your own
initiative. `fetch-viewer` and `check --install` put a page into the user's browser that
will run there with their data inside it — the URL matters, and so does their yes.

```bash
python3 "$ENGINE" check --install    # fetch a missing app from the graph's own app_url
python3 "$ENGINE" check --probe-url  # is that app_url reachable? (network)
```

Recording what a graph needs is how it stays honest about itself:

```bash
python3 "$ENGINE" require --tool openalex --skill kg    # built with these
python3 "$ENGINE" require --remove --tool openalex      # and no longer
```

Tools are **declared, not verified** — `check` cannot know whether this agent has an
OpenAlex tool or a key, and it says so rather than guessing. Skills it can check, because
a skill is a folder with a `SKILL.md` in a place agents look.

## Importing another tool's export

The engine reads and writes `kg/1` and **nothing else**. Other tools' formats are
handled by **adapters** in `scripts/adapters/`, one file per foreign format:

```bash
python3 "$ENGINE" import --format foresight --graph raw.graph --id field
```

- `python3 "$ENGINE" graphs` shows the result; it becomes the current graph.
- The refusal is the feature: loading a foreign export used to produce a confident
  **"0 nodes"**. Now the engine names the problem and lists the adapters that exist.
- To support a new format, add `scripts/adapters/<name>.py` exporting
  `convert(src, title, schema, colors) -> dict` — see `scripts/adapters/README.md`.
  Never teach the engine a vendor's shape.

## Editing a graph that someone else made

The point of the `kg/1` schema is that **a different agent, in a different session,
on a different machine can pick the file up cold.** When you are that second agent:

1. `validate` first. Errors mean the original writer left it broken; say so rather than
   silently working around it.
2. Read the `note:` lines to learn the shape before touching it — how many nodes are
   isolated, how many edges carry labels. Do not assume.
3. Make your change, then `validate` again and re-render.

```bash
# fold another graph's content into this one (--other takes an id or a path)
python3 "$ENGINE" merge --other other --on-conflict rename
# ... skip (default) keeps the existing node, overwrite replaces it, rename suffixes
#     the incoming id with _m and records where it came from

# correct a mistake (these did not exist before; agents used to hand-edit the JSON)
python3 "$ENGINE" remove-node --id typo1
python3 "$ENGINE" remove-edge --from lab1 --to telo
# keep the node, drop only its wiring:
python3 "$ENGINE" remove-node --id lab1 --drop-orphan-edges-only
```

`remove-node` also deletes every edge touching the node, so you cannot leave a dangling
line behind. It refuses ids that do not exist rather than reporting a cheerful `0`.

## Handing the graph to a human

**A filename is not a link**, and neither is a path the human has to assemble. This is the
most common way this skill fails its user.

**The page is the deliverable, and it is self-contained** — the whole graph is inlined into
the HTML — so it needs no server, no network and nothing left running:

```bash
python3 "$ENGINE" render --graph field                        # → storage/field/index.html
python3 "$ENGINE" open   --html storage/field/index.html       # prints the link, opens it
```

- **If your client has a preview pane** — the Hermes desktop app does — open the file in the
  pane. That is the clickable button; a bare `http://localhost:…`, or a `file:///…` pasted as
  text, is not.
- Otherwise `render` prints the `file:///…` link itself: give it **verbatim**. `open` also
  launches the user's real browser.
- Nothing has to stay alive for the page to work. That is the point of it.

### There is no server in this skill, and that is a decision

The page is a file. `render` writes it, the pane or `open` shows it, and **nothing has to stay
alive** for it to work — which is the whole reason it is built this way. The engine has no
`serve` and no `shot`: a listening socket is a process the user has to remember to kill, and a
headless browser is a dependency their machine may not have. Both used to be here and both cost
more than they gave.

While a graph is being edited, re-render (`python3 "$ENGINE" render`) and tell the human to
refresh the page they already have open. That is the live loop, and it has no port in it.

### What the human can do in the viewer

Tell them this, or they will click once, see an unreadable cloud, and conclude it is
broken:

- **Pan and zoom** — drag to pan, wheel to zoom. Labels fade in as you zoom, so start by
  zooming into the branch you care about.
- **Search** — the box top-left, or press `/`. Typing filters across labels, kinds and
  tags; clicking a hit centres it. `Esc` clears.
- **2D / 3D** — the buttons top-right switch renderer. The 3D one is loaded on demand
  (about 1.4 MB), so the first click takes a moment. `fit` reframes the graph.
- **Selection** — clicking a node shows its label, kind, level, size, and then **every other
  property the node carries, each in its own row**: the panel has no fixed list of fields, so
  a property you put in the document is shown without anyone changing the app. A value that
  looks like a DOI or a URL resolves to a link.

✅ You have described at least search and the 2D/3D switch. A viewer nobody knows how to
drive is the same as no viewer.

## Updating a field you already mapped

1. `cp storage/field/graph.json storage/field/graph.backup.json` — always, so you can
   diff.
2. Add the new work (new papers, new labs, new companies).
3. `stats` the two files and compare counts by kind. The backup is *not* named
   `graph.json`, so it does not shadow the graph: `graph.json` always wins in a folder.
4. Re-render, screenshot, **look**. Then state what changed in words.
5. `render` again and tell the human to refresh the page they already have open — the file
   is the same one, so the same tab shows the new graph.

The diff is the product. "Two new labs entered this space since March, both working on
the same mechanism from different directions" is the output; a list of node ids is not.

## Where output goes

**The page belongs next to its graph**, which is where `render` puts it by default:
`storage/<id>/index.html`. Nothing to remember, nothing to pass.

Renders are build output. They are large, they are regenerated by one command, and they
do not belong in version control — a workspace's `storage/` is the user's data, not a
repo. If you are working outside a workspace and writing into a git repo, keep renders
inside a gitignored folder (`kg/`, `web/`); never `--out` a file to the repo root.

## Pitfalls

1. **A bare filename is not a link.** See "Handing the graph to a human". This is the
   defect users hit most, and it makes good work unusable.
2. **Positions belong to the viewer; authored ones win.** A graph whose nodes carry no
   `x,y` is laid out in the browser on open — the header says `layout computed here`. If
   *every* node carries a position, that layout is used exactly as given, because
   positions are an editorial decision, not noise. An imported graph authored for a
   different canvas can start enormous in 3D for the same reason: hand-authored
   coordinates and a free 3D simulation do not mix.
3. **Unknown kinds render in a hashed colour** and `stats` warns. Not an error, but a
   legend that lies.
4. **An unlabelled edge tells the reader nothing.** The engine allows it; the picture
   suffers.
5. **`render` needs a template.** If `assets/viewer.html` is missing, say so — the skill
   ships templates, it does not build them. Do not hand-write HTML to work around it.
6. **A screenshot is not optional.** The whole point of the skill is that an agent can
   see the result before a human has to.

## References

- `references/format.md` — the `kg/1` document format in full.
- `references/recipes.md` — the jobs (one paper's citation neighbourhood, the whole field, a
  map centred on something and weighed by a stated metric, the survey with its notes, and a
  10k-article pull) as command sequences.
- `references/providers.md` — where a list of works can come from: OpenAlex, Crossref, PubMed,
  Europe PMC, arXiv, Semantic Scholar, CORE, DOAJ, and a web search as the last resort — with
  what each is good for, what it costs, and what it cannot give you.
- `references/apps.md` — what an app declares (purpose, requirements, kinds, edges), the
  catalogue the skill matches against, and the rules around installing one.
- `scripts/adapters/README.md` — how to add an importer for another tool's export.
- `README.md` — what this is for, how a graph is shared, and how the viewer is built.
- `assets/viewer.html` — the bundled viewer (built elsewhere, copied in; see README).
