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
| `level` | no | vertical position. Convention: low = foundational/concrete, high = abstract/evidence |
| `size` | no | visual weight, standing in for importance |
| `style` | no | `solid` (settled), `hollow` (proposed), `cloud` / `critter` (threatening or eroding), `skull` (abandoned) |
| `desc` | no | free text |
| `link` | no | a single URL. Adapters lift URLs out of `desc` when a format buries them there (see `scripts/adapters/`) |
| `x`,`y` | no | authored position. If **every** node has them they are used as given; a graph with none is laid out in the browser on open (the page says `layout computed here`) |

`level` and `style` are what make a graph readable at a glance instead of a hairball.
A graph where everything is `level 0, style solid` is a ring of dots and argues nothing.

## Edges

| field | meaning |
|---|---|
| `from`, `to` | node ids |
| `label` | what the relation is. Unlabelled edges render as bare lines — avoid |
| `dir` | `in` = the arrow points at `to`; omit for an undirected relation |
| `time` | optional estimate or date, e.g. `2018`, `"18mo"`, `"years"` |
| `weight` | optional line weight |

**Two conventions worth more than the schema.** A piece of work — a paper, a trial, a
patent — is an **edge, not a node**: `from` the researcher, `to` the subject, `label` the
title, `time` the year. And two organisations working on the same subject get an edge
**between them**, labelled with that subject. Together they turn a graph of dots into a
graph where the researcher is visibly connected to what they work on and companies cluster
around what they share.

## What the engine guarantees

- `new` and every write create the parent directory, so `--out kg/deep/x.json` works.
- Writes are whole-file; there is no partial merge. Copy before a bulk update.
- `stats` reports counts by kind, style and level, plus any kind with no colour.
- `check` reports whether the graph can be shown here: the app, its `app_url`, and what
  `requires` declares — exiting non-zero when the app is missing.
- `render` emits a self-contained page — no CDN, no network, opens from disk.
- `serve` re-renders from the JSON on every request, so refresh shows current state.

## Portability

The format has no notion of a host, a user, or a project. A graph file can be moved,
committed, emailed or published as-is, and the same file renders identically elsewhere.
