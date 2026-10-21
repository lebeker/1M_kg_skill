# kg

An agent skill that turns a research field into a **graph you can look at**, and keeps
it current as new work appears.

Feed it a field — a longevity sub-branch, a materials niche, whatever you are tracking —
and it produces a single self-contained HTML page: what the field is made of, who is
working on it, what is applied versus speculative, and what changed since last time.
The picture is the point. A JSON dump of the same facts tells you far less.

**A worked case:** <https://lebeker.github.io/1M_kg_sciense-kg_webapp/> — one article on the
neurokinin antagonist class, the document it came from, and the page it renders into.

Nothing here is specific to any one project. Import your own data, name your own node
kinds, keep your graphs in your own workspace.

---

## What it is for

Three jobs, all of which are about **seeing** rather than searching:

1. **Track a direction over time.** The value is the *diff* — what appeared since the
   last run. Narrow fields are the sweet spot; a whole discipline is a hairball.
2. **Map a field before writing.** For a dissertation or a literature review: what are
   the clusters, where are the gaps, which groups own which question.
3. **Spot near-applied work.** Which lines are still academic, which have a company
   attached, and who is already building it.

It is not a literature search engine. Use Scholar, Litmaps or ResearchRabbit to *find*
papers. This skill is for what you do with them afterwards — the structure, the change,
the picture.

## The workspace

Your graphs live in one folder each, and the skill never hardcodes where:

```
<root>/storage/<id>/          one graph, self-contained
    graph.json                the kg/1 document the engine reads and writes
    <raw export>              what it was imported from, if anything
    index.html                the page, rendered next to its graph
<root>/storage/.current       which graph you are working on
```

`<root>` is `$KG_WORKSPACE`, or the directory you run from. `--graph` takes an **id**
from the workspace or a **path** to any `.json`; with no `--graph` you get the current
one. So the ordinary questions work:

```bash
python3 "$ENGINE" graphs                       # what do I have, and which is current
python3 "$ENGINE" use longevity                # let's work on this one
python3 "$ENGINE" render --graph longevity     # show me that one (prints a link)
python3 "$ENGINE" info                         # what is in the current one
```

## What you get

| Artifact | What it is |
|---|---|
| `storage/<id>/graph.json` | the graph itself — a small, diffable `kg/1` document |
| `storage/<id>/index.html` | a self-contained page (no CDN, works offline, opens anywhere) |
| `storage/<id>/docs/*.md` | an Open Knowledge Format note per node, the long form of a description |

## Quick start

```bash
git clone <this-repo> kg
cd kg
export ENGINE="$PWD/scripts/kg.py"      # no absolute host paths anywhere in this repo

python3 "$ENGINE" new --id field --title "My Field"
python3 "$ENGINE" add-node --id telo --label "Telomere attrition" \
    --kind concept --level 2 --size 4 --style solid
python3 "$ENGINE" add-node --id lab1 --label "Blackburn Lab" --kind lab --level 3 --size 3
python3 "$ENGINE" add-edge --from lab1 --to telo --label studies --dir in
python3 "$ENGINE" render                        # -> storage/field/index.html + a link
python3 "$ENGINE" open --html storage/field/index.html
```

Requirements: `python3` (standard library only — no pip install, no node, no bun, and no
browser of ours: the page is a plain file that opens over `file://`). `new` creates
`storage/<id>/` for you.

## Keeping it live, with no server in the loop

Run any `add-node` / `add-edge` / `set-node` command and `render` again; the tab the human
already has open shows the new state on refresh. There is deliberately **no server command**:
a listening socket is a process somebody has to remember to kill, and a URL in a chat stops
meaning what it meant the moment that process ends. The page is the artifact.

## The loop an agent must follow

```
build or load  →  stats  →  render  →  screenshot  →  LOOK AT IT  →  fix the JSON, repeat
```

The screenshot step is not decoration. An agent that has not looked at its own graph
cannot tell a readable map from a hairball, and will confidently describe both as
"showing the field's structure". Render it, look at it, and fix the *artifact* —
levels, sizes, colours — rather than the HTML by hand.

## Commands

| Command | Purpose |
|---|---|
| `graphs` | list the workspace: id, title, size, which one is current |
| `current` / `use` | show / set the graph you are working on |
| `suggest` | which app fits what the user asked for, what it needs, how a graph for it is shaped |
| `apps` | list the bundled viewers (templates), their purpose, what each needs, where each came from |
| `fetch-app` | install an app from the catalogue: the viewer and its own declaration (no node, no bun) |
| `fetch-viewer` | download a viewer into `assets/` — no node, no bun, no build |
| `new` | create an empty graph (`--id` in the workspace, or `--out <path>`) |
| `import` | convert another tool's export (`--format <adapter>`) |
| `add-node` / `add-edge` | build the graph |
| `set-node` | change a property (`--set level=3 --set style=cloud`) |
| `set-palette` / `set-meta` | colour a node kind; set the title |
| `require` | record what this graph needs: skills, plugins, tools, the app that draws it |
| `check` | can this graph be shown here? what is missing — exits non-zero if the app is (`--install` fetches it from the graph's `app_url`) |
| `remove-node` / `remove-edge` | correct a mistake without hand-editing JSON |
| `merge` | fold another graph in (`--on-conflict skip\|overwrite\|rename`) |
| `validate` | check conformance to `kg/1` |
| `info` / `stats` | what is in this graph; counts by kind, style, level |
| `render` | template + graph → self-contained HTML, and prints the link |
| `open` | open the rendered page in the browser the user already has |

## Choosing the app, from what the user asked for

An app declares what it is for, what it needs to be useful, and the node kinds and edge
patterns a graph for it is made of. That declaration is what turns "make me a graph" into a
specific thing to build:

```bash
python3 "$ENGINE" suggest "map the cryogenics research field"
```

It prints the app that fits, whether it is installed, every required skill/plugin/tool with
what each is for, what it only suggests, and the kinds and edges to build with. Then:

```bash
python3 "$ENGINE" fetch-app viewer        # install it: viewer + its own declaration
python3 "$ENGINE" new --ask "map the cryogenics research field" --id cryo
python3 "$ENGINE" new --id cryo --title "Cryogenics" --app viewer   # or name the app yourself
```

`new --app` writes `meta.app`, `meta.app_url` and the app's `requires` into the graph and
seeds the palette with the app's kinds, so the graph is shaped by the app rather than by
whatever the agent felt like. The skill's own copy of that knowledge — for the case where
nothing is installed yet — is `scripts/apps.json`; the app's own `app.json`, fetched beside
its viewer, wins once it is here. Schemas: `references/apps.md`.

Nothing is installed without a yes: a viewer runs in the user's browser with their data
inside it.

## Viewers are separate, and pluggable

`render` draws nothing itself. It takes a **template** — a single-file
HTML carrying

```html
<script id="kg-graph" type="application/json">__KG_GRAPH__</script>
```

— and substitute the graph into that element. Only that element's text is replaced, and a
`</script>` inside the graph is escaped so it cannot break the page.

`assets/viewer.html` is the viewer that ships: **2D** via sigma + graphology and **3D** via
3d-force-graph, both inlined for `file://`. Which template is used is decided by the graph
itself — `meta.app` — with `--app <name>` overriding it for one run:

```json
{ "meta": { "schema": "kg/1", "app": "viewer",
            "app_url": "https://…/viewer-v0.0.30/viewer.html",
            "requires": { "skills": ["kg"], "plugins": [], "tools": ["openalex"] } } }
```

That is the interface: a `kg/1` document names the drawer, it does not contain one. It also
says **where to get that drawer** (`app_url`, seeded by `new` from the built viewer's own
sidecar) and **what else it needs** (`requires`). An app the machine does not have is
fetched, not substituted — `apps` prints the repo each copy was built from, `info` /
`validate` say when a graph names a missing one, and `check` puts the whole question
together:

```bash
python3 "$ENGINE" check                # app, app_url, requires, and what is missing
python3 "$ENGINE" check --install      # fetch a missing app from the graph's own app_url
python3 "$ENGINE" require --tool openalex --skill kg
```

Skills are looked for on disk; tools are declared, not verified — a JSON file cannot know
whether this machine has an OpenAlex tool, and `check` says so instead of guessing.

**Positions are optional, and the viewer's job.** A graph whose nodes carry no `x,y` is
laid out in the browser on open and says so in the header (`layout computed here`); if
*every* node carries a position, that layout is used exactly as given. (A blank page means
the viewer predates this — sigma throws rather than draws when a node has no position.)

A viewer is built in its own repository and copied in — this skill does not build it (it
would then need node, and it takes `python3` only):

```bash
# the viewer that ships comes from:
#   https://github.com/lebeker/1M_kg_sciense-kg_webapp
git clone https://github.com/lebeker/1M_kg_sciense-kg_webapp && cd 1M_kg_sciense-kg_webapp
bun install && bun run build:local && node scripts/bundle.mjs /path/to/this/skill
```

The copy lands as `assets/viewer.html` plus an `assets/viewer.version` sidecar recording
the repo, commit and build time. Both are gitignored — they are build output, and this
repo carries none.

## Importing another tool's export

The engine knows `kg/1` and nothing else. Foreign formats live in `scripts/adapters/`, one
file per format:

```bash
python3 "$ENGINE" import --format foresight --graph raw.graph --id field
```

Loading a foreign export directly is refused by name — it used to yield a confident
"0 nodes", the worst possible answer. To support a new format, add
`scripts/adapters/<name>.py` exporting `convert(src, title, schema, colors) -> dict`; see
`scripts/adapters/README.md`.

## Node vocabulary

The default palette covers a research-branch vocabulary — `concept`, `lab`, `company`,
`institution`, `person`, `tool`, `dataset`, `funding` — but nothing is fixed. Use
`--kind` with any string and give it a colour with `set-palette`:

```bash
python3 "$ENGINE" add-node --id x --label "Cryo-EM" --kind technique --level 2 --size 3
python3 "$ENGINE" set-palette --kind technique --color "#f6bd16"
```

`stats` will tell you when a kind has no colour rather than silently painting it grey.

**Shapes carry meaning** — use `--style` deliberately: `solid` for settled things,
`hollow` for proposals or speculation, `cloud`/`critter` for things that threaten or
erode, `skull` for abandoned lines. An all-solid graph is a graph with no argument in it.

## Updating a graph you already have

Always copy before a bulk update, so you can diff:

```bash
cp storage/field/graph.json storage/field/graph.backup.json
# ...add nodes and edges...
diff <(python3 -c "import json;print(*sorted(n['id'] for n in json.load(open('storage/field/graph.backup.json'))['nodes']),sep=chr(10))") \
     <(python3 -c "import json;print(*sorted(n['id'] for n in json.load(open('storage/field/graph.json'))['nodes']),sep=chr(10))")
```

The backup is deliberately *not* called `graph.json`: in a workspace folder, `graph.json`
wins, so a stray second JSON never shadows the graph.

## Test data

This skill ships no example graph, on purpose. A graph you test against is **workspace
data**, not part of the skill — keep it where your graphs live and pass its path or id to
the engine. Anything bundled here would be one particular vocabulary presented as if it
were the general case.

A five-node example in `SKILL.md` shows the shape of the format, and building that on a new
setup — `new`, five `add-node`, a few `add-edge`, `validate`, `render` — is the cheapest way
to check the whole loop works before pointing it at a real field.

## Syncing graphs between people

The graph is a plain JSON document, so the obvious mechanism is a git repository —
personal or shared. A public repo of graphs is a way to publish a map and let others build
on it; a shared private one is how a small group keeps a common artifact current. Two
people editing the same document will conflict the ordinary way, which is fine for a file
this small and this rarely edited.

A hosted service that merges concurrent edits is the alternative, and it is a different
amount of work: accounts, storage, conflict resolution, and an answer to who pays for it.
Nothing in this skill depends on either choice — the format is the interface.

**Git first.** It needs no new software, it works today, and it will tell you whether
anyone actually wants to share a map before you build infrastructure for it.

## Layout

```
kg/
├── SKILL.md              the agent-facing instructions
├── README.md             this file
├── LICENSE
├── references/
│   ├── format.md         the kg/1 document format, in full
│   └── apps.md           what an app declares, and the catalogue the skill matches against
├── scripts/
│   ├── kg.py             the engine (stdlib only)
│   ├── apps.json         the known apps: purpose, keywords, requirements, where to fetch
│   └── adapters/         one file per foreign export format (foresight, …)
└── assets/
    ├── README.md         how the viewer is built, and where to fetch it from
    ├── viewer.html       the bundled viewer — built elsewhere, copied in (gitignored)
    ├── viewer.version    provenance sidecar: repo, commit, build time, fetch URL
    └── viewer.app.json   the app's own declaration: purpose, requirements, kinds, edges
```

`storage/` is not here: it belongs to whoever runs the skill, not to the skill.

## License

MIT
