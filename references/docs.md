# The document is the deliverable

A graph that renders is not a finished job. The question that decides whether the work is done
is the reader's: *what do I get?* — a survey, a brief, a comparison, a timeline. The graph is
how that document's claims are checked; the page is how it is read.

## Ask what the graph is for

`new --intent` records it in `meta.intent`. Five answers, and each one changes the shape of the
work, not just the wording:

| intent | the document | the graph must carry | done when |
|---|---|---|---|
| `overview` | a survey of a field, 1,500+ words, publishable | authored shelves, evidence under them, the periphery (people, money, companies) | every section has a node, every paragraph cites one, the shelves are measured against an outside frame |
| `profile` | one page answering five written questions about one subject | the subject, their works, their orbit | each question is answered with node ids |
| `comparison` | a table: one row per alternative, one column per axis | the alternatives, what they share, the money, the competition | no empty cell that does not say "no evidence" |
| `timeline` | a dated narrative | stages as levels, progression as edges | every claim is dated and sourced |
| `explore` | nothing yet — the map is the answer | whatever the question needs | the user can see the shape and say what to ask next |

If the user has no firm intention, that is `explore`, and it is honest to say so. Do not write a
report nobody asked for; do not skip the report when that is the job.

## The doc set: a folder with roles

Documents live in `docs/` beside the graph, and `docs/index.json` says what each one is:

```json
{
  "docs": [
    {"file": "report.md",    "title": "Longevity research, 2018-2026", "role": "report"},
    {"file": "overview.md",  "title": "How to read this map",          "role": "read"},
    {"file": "method.md",    "title": "Method",                        "role": "method"},
    {"file": "sources.md",   "title": "Sources",                       "role": "sources"},
    {"file": "rejected.md",  "title": "Rejected",                      "role": "rejected"},
    {"file": "reference.md", "title": "The frame we measure against",  "role": "reference"},
    {"file": "coverage.md",  "title": "Coverage",                      "role": "coverage"}
  ]
}
```

Start each one with `kg.py doc --graph <id> --role <role>`; it writes the skeleton and lists the
document. `doc --list` shows the set and anything sitting in `docs/` that the manifest does not
name — a file the page cannot place. `validate` says the same thing as a warning, and `stats`
says which roles the intent still expects:

```
intent      : overview — a survey of a field
docs        : 5 in docs/ · declared 5 · report ✓ read ✓ sources ✓ method — 
```

| role | what it is for |
|---|---|
| `report` | the document the graph was built to produce |
| `read` | how to read the map: what it is, what a node carries, what it does not claim |
| `method` | how the corpus was built, what was searched, what was excluded |
| `sources` | every source, query, date — and what it cost |
| `rejected` | what was considered and left out, and why |
| `reference` | an outside taxonomy to measure the shelves against |
| `coverage` | generated: the shelves against that reference |
| `note` | anything else, including a node's long description |

The page lists the set by role (the `docs` button) and renders each one. **A node id written in
backticks inside a document is a link into the map**: click it and the map selects that node. So
the report's claims are checkable one at a time, which is the whole reason the report is being
written from a graph and not from a blank page.

## Measuring the shelves (the `overview` intent)

A taxonomy cannot check itself: a set of categories that the same agent wrote will always look
coherent. The check is external.

1. **Take a frame you did not write.** A recent review's section headings, a standards body's
   list, a handbook's chapter titles — the words its author used. Save it verbatim as
   `docs/reference.md`, one heading per section (`doc --role reference`, then paste).
2. **Run the diff.**
   ```bash
   python3 "$ENGINE" coverage --graph field --against docs/reference.md --write
   ```
3. **Read four numbers** and put them in the report: `covered` (a top-layer node carries the
   section), `buried` (only a node inside a shelf matches — the reader would look for a shelf
   and not find one), `missing` (nothing at all), and `unclaimed` (shelves no section names).
4. **Do not paper over a mismatch.** If a reference section is missing, the honest outcomes are:
   the frame is wrong for this map, the map has a real gap, or the section belongs one level
   down. Say which, in the report, next to the number.

The matching is vocabulary-based (plurals and adjectives count as the same word; half a section
is enough when the half that matched is its subject word). It is a **report, not a verdict** —
`coverage.md` states that in its own last paragraph. The agent's job is the judgement the
script cannot make, and the table is where it is made visible.

## The acceptance line

For `overview`, "done" means all of these, and they are checkable:

- **the report exists** — 1,500+ words, 15+ sources, a written scope line ("what this does not
  claim"), every paragraph carrying at least one node id;
- **the shelves are measured** — `coverage` run against a reference, the four numbers in the
  report, every miss explained;
- **the weights are defined** — `meta.weight.metric` says what the number on a node means,
  and the panel shows it;
- **the map is readable** — `render`, then look at it: the categories at the top layer, a
  branch opens, 3D has depth, the docs button lists the set;
- **the cost is recorded** — wall clock, source calls, and what was paid, if anything.

Anything less is a map, not a survey. Say which one was delivered.
