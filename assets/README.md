# assets

**Templates live here; they are build output, not source.** Nothing in this folder is
committed except this file — see `.gitignore`.

A template is a single-file HTML carrying one element:

```html
<script id="kg-graph" type="application/json">__KG_GRAPH__</script>
```

`render` substitutes the graph into that element's text and nothing else, so a
template is free to be whatever it likes: React, WebGL, physics, styling. The engine never
looks inside.

## Which template gets used

The graph says so itself, in `meta.app`:

```json
{ "meta": { "title": "Longevity", "schema": "kg/1", "app": "viewer",
            "app_url": "https://…/viewer-v0.0.18/viewer.html" } }
```

`render` resolves the name in this order: `--app <name>` on the command line, then the
graph's `meta.app`, then `viewer.html`. A `kg/1` document therefore carries the *name of
the drawer*, not a copy of it — the same JSON renders on another machine as long as the
app it names is there.

`meta.app_url` is where that app comes from if it is not here. `new` seeds it from the
built viewer's own `.version` sidecar, so a graph can carry the way to render itself:

```bash
python3 scripts/kg.py check              # app, app_url, requires — what is missing
python3 scripts/kg.py check --install    # fetch a missing app from the graph's own app_url
```

## `viewer.html`

The viewer that ships — **2D** (sigma + graphology) and **3D** (3d-force-graph), both
inlined so the page works off `file://` — is built in its own repository. You have two
ways to get it, and the first one needs **no node, no bun, no build**:

### Fetch the published build (what most people want)

```bash
python3 scripts/kg.py fetch-viewer --url <url-of-the-single-file-viewer>
# --as <name>   install under another template name
# --force       replace one that is already here
```

The latest published build of the shipped viewer:

```
https://raw.githubusercontent.com/lebeker/1M_kg_sciense-kg_webapp/viewer-v0.0.18/viewer.html
```

That URL is a tag, so it never changes under you: a fix is published as a new tag
(`0.0.1` stays exactly as it was), and `assets/<name>.version` records the URL a copy came
from. `fetch-viewer` verifies what it got (it must be big enough and must contain the
`#kg-graph` element), writes
`assets/<name>.html` plus a `.version` sidecar recording the URL, the fetch time and the
sha256, and prints the hash. It refuses to overwrite an existing template without
`--force`, and it writes **nothing** if the file is not a viewer.

Get a recent one. Positions are optional in the document, and sigma does not draw a node
that has none — it throws while being constructed, so an older viewer paints a blank page
instead of a graph. Viewers from 0.0.1 on lay such a graph out themselves and say so in the
header (`layout computed here`). A blank page is the first symptom to check for, before
suspecting the graph.

Fetching is the only network call the engine makes, and it never happens implicitly:
`render` will not download an app a graph names, because rendering a fetched page means
running someone else's code in the browser with the user's data in it. That is the user's
decision, taken out loud. Only fetch a viewer from a source you trust.

### Build it from source (contributors)

- repo: <https://github.com/lebeker/1M_kg_sciense-kg_webapp>

```bash
git clone https://github.com/lebeker/1M_kg_sciense-kg_webapp && cd 1M_kg_sciense-kg_webapp
bun install && bun run build:local && node scripts/bundle.mjs /path/to/this/skill
```

In the testbed, `make bundle` does that for you.

## The app's own declaration: `<name>.app.json`

A viewer is half an app. The other half is what the app says about itself — what it is for,
what it needs to be useful, and the node kinds and edges a graph for it is made of:

```json
{ "id": "viewer",
  "title": "Research field map",
  "purpose": "Map a research field so it can be looked at…",
  "keywords": ["research", "field", "paper", "publication", "…"],
  "requires":   { "skills": ["kg"], "plugins": [], "tools": ["openalex"] },
  "recommends": { "tools": ["a web-search tool"] },
  "tool_notes": { "openalex": "what it gives you, and why the graph needs it" },
  "kinds": [ { "kind": "publication", "color": "#cdd9e5",
               "meaning": "a work — the thing a DOI identifies" } ],
  "kind_notes": { "one word per thing": "…" },
  "edges": [ { "pattern": "researcher → publication", "label": "authored",
               "meaning": "the main link of a research field" } ],
  "visuals": { "node size": "…", "edge power": "…", "placement": "…" },
  "alternative": { "a work as an edge": "…" } }
```

`kinds` is a **starter set, not a schema**: it exists so the main cases of a research map
come out recognisable, and `visuals` says how size, weight and placement are controlled.
Neither constrains a graph — a kind or a property outside the declaration is legal, and the
viewer renders it. `apps.md` in `references/` has the full keys; the engine reads `kinds`
and `edges` and ignores the prose.

It is authored in the app's own repository (`app.json`, next to the viewer's source) and
published at:

```
https://raw.githubusercontent.com/lebeker/1M_kg_sciense-kg_webapp/main/app.json
```

Not tag-pinned, on purpose: the declaration says what the app is *for*, which does not
change when the build does. The viewer is tag-pinned; the declaration stays current.

With it, `suggest "<the user's words>"` can pick the app, name what is missing, and hand the
agent the kinds and edge patterns to build with. It arrives together with the viewer:

```bash
python3 scripts/kg.py fetch-app viewer
```

Without it, the skill falls back to its own catalogue (`scripts/apps.json`) — the whole flow
still works, from a copy rather than the app's own word. Schemas: `references/apps.md`.

### `viewer.version` — where a template came from

Whoever puts a template here should say where it came from. Two shapes exist, both read by
`apps`:

```json
{ "name": "kg-viewer", "version": "0.0.2", "built_at": "…",
  "origin": "https://github.com/lebeker/1M_kg_sciense-kg_webapp",
  "commit": "e4ca883", "bytes": 1799703,
  "fetch_url": "https://raw.githubusercontent.com/…/viewer-v0.0.18/viewer.html",
  "manifest_url": "https://raw.githubusercontent.com/…/main/app.json" }

{ "name": "viewer", "origin": "https://…/viewer.html",
  "fetched_at": "…", "bytes": 1799703, "sha256": "…" }
```

`fetch_url` is what `new` copies into a fresh graph's `meta.app_url`, which is how a graph
comes to carry the address of its own drawer. `manifest_url` is the app's declaration.

That is how an agent answers "is this viewer current, and where do I get a newer one?"
without guessing — and why the skill can stay ignorant of which app happens to be
installed. A sidecar is optional.

## Adding another viewer

Drop any other single-file HTML in here that carries the element above and it is usable
immediately by name:

```bash
python3 scripts/kg.py apps                                # what is here, can it render, where from
python3 scripts/kg.py render --app <name>                 # use it once
python3 scripts/kg.py set-meta --key app --value <name>   # make the graph use it always
```

Keep the element unique: `render` refuses a template with two `#kg-graph` elements rather
than picking one silently. A graph naming an app that is not here fails loudly too — `info`
and `validate` both say so, and `render` says where to get it.
