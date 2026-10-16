# Apps, and what they need

An **app** is two things: a viewer (a single-file HTML that draws a `kg/1` document) and a
**declaration** saying what the app is for, what it needs in order to be useful, and what
kinds of node and edge a graph for it is made of.

The declaration is the point. It is what turns "make me a graph" into a specific thing to
build, and it lives in the app's own repository — the app defines the goal, the skill
follows it.

## The three files of an installed app

```
assets/<name>.html        the viewer itself (build output; gitignored here)
assets/<name>.version     provenance: repo, commit, build time, where to fetch it
assets/<name>.app.json    the app's own declaration, fetched with the viewer
```

All three arrive with one command, and none of them require node:

```bash
python3 scripts/kg.py fetch-app viewer
python3 scripts/kg.py fetch-app viewer --url file:///tmp/my-build.html   # a local build
```

`fetch-app` reads the skill's catalogue for the URLs; `--url` overrides it, which is how a
mirror, a fork or a local build is installed. If the declaration cannot be fetched, the
viewer is still installed and the command says so — the catalogue's copy of the facts is
used instead.

## `scripts/apps.json` — what the skill knows before anything is installed

A finite list, on purpose: a first question arrives before any app is on the machine, and
answering it must not need the network.

```json
{
  "apps": [
    {
      "id": "viewer",
      "title": "Research field map",
      "purpose": "one line a human can read",
      "keywords": ["research", "field", "longevity", "…"],
      "repo": "https://github.com/<owner>/<repo>",
      "url": "…/viewer-v0.0.6/viewer.html",
      "manifest_url": "…/main/app.json",
      "requires": { "skills": ["kg"], "plugins": [], "tools": ["openalex"] },
      "recommends": { "tools": ["a web-search tool"] },
      "tool_notes": { "openalex": "what it gives you, and why the graph needs it" }
    }
  ]
}
```

- **`keywords` decide the match.** `suggest` scores an ask by keyword hits (three points
  each) and then by words shared with `title` and `purpose` (one each), so a vague ask still
  lands somewhere instead of on whatever is first in the list.
- **`requires`** is what the graph cannot be built without. **`recommends`** is what makes
  it better; say so, and do not block on it.
- **`tool_notes`** is the "why we need it" a user has to hear before agreeing to anything.
- The viewer is tag-pinned (the tag `apps.json` names never changes), and the entry moves with
  the release: it names the tag the current release will create, so between publishing and
  the tag existing `fetch-viewer` 404s. That is a pre-production window, not a defect — but if
  a release is abandoned, fix the entry. The declaration is not pinned: it says what the app
  is *for*, which does not change when the build does, and it stays readable at `main`.
- **The pinned tag is whatever `package.json` will release.** The entry and the release are
  one step: bump `package.json`, publish, and the tag the entry names comes into existence.

A **discovery service** for the paid tier replaces this file, not the commands that read it:
the same list, fetched from a server, with the same fields.

## `<name>.app.json` — the app's own declaration

```json
{
  "id": "viewer",
  "title": "Research field map",
  "purpose": "Map a research field so it can be looked at…",
  "keywords": ["…"],
  "requires":    { "skills": ["kg"], "plugins": [], "tools": ["openalex"] },
  "recommends":  { "tools": ["a web-search tool", "crossref", "arxiv"] },
  "tool_notes":  { "openalex": "…" },
  "kinds": [
    { "kind": "concept", "color": "#7b9ecb", "meaning": "…" },
    { "kind": "scientist", "color": "#d47fa6", "meaning": "…" }
  ],
  "edges": [
    { "pattern": "scientist → concept", "label": "the title of the work",
      "meaning": "a piece of work is an EDGE, not a node: --time the year, --dir in" }
  ],
  "layout": { "note": "…" }
}
```

- **`kinds`** become the graph's palette (`new --app` seeds them, so `stats` never warns)
  and the list the agent builds with.
- **`edges`** are conventions, not rules: the patterns that make a graph of this kind
  legible. A work as an edge from researcher to subject; two organisations on the same
  subject joined to each other.
- **`layout`** is advice about arrangement for whoever authors positions.
- Installed manifest wins over the catalogue entry: the app's own word is authoritative.

## Commands

| command | what it does |
|---|---|
| `apps` | what is installed here — size, provenance, purpose, and what each one needs |
| `suggest "<the user's words>"` | the app that fits, why, what is missing, and the kinds and edges to build with |
| `fetch-app <id>` | install it: viewer + declaration, no node, no bun |
| `check` | for a *graph*: the app it names, whether it is here, and what its `requires` declares |
| `require --tool x --skill y` | record what a graph needs, on the graph |
| `new --app <id>` | start a graph shaped by that app |
| `new --ask "…"` | same, but pick the app from the user's words |

## Rules that do not bend

1. **Nothing is installed without a yes.** A viewer runs in the user's browser with their
   data inside it; `fetch-app`, `fetch-viewer` and `check --install` all print where the
   file comes from before it is used.
2. **Tools are declared, not verified.** A skill can be looked for on disk; whether this
   machine has an OpenAlex tool or a key cannot be seen from a JSON file. `check` and
   `suggest` say so instead of guessing, and the agent is expected to confirm it out loud
   with the user.
3. **A missing app is never substituted.** Rendering with the wrong drawer produces a
   picture that is wrong in ways nobody can see.
