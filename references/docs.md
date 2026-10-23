# The document is the deliverable

A graph that renders is not a finished job. The question that decides whether the work is done
is the reader's: *what do I get?* — a survey, a brief, a comparison, a timeline. The graph is
how that document's claims are checked; the page is how it is read.

## The report comes first, and the intention is yours to establish

The user's goal is always a report. What goes in it is **not** something to ask them as a menu of
shapes — it is the agent's job to work out from three things: what they said, what decision the
report feeds, and who reads it. Write the answer down in one sentence and put it in the document:

```bash
python3 "$ENGINE" set-meta --graph field --key brief --value "Which parts of longevity research
are structurally thin, and where does the money sit against the literature?"
```

`meta.brief` is the report's question. If the answer would not change anything for the reader,
it is the wrong question — pick another before building, not after. `meta.intent` (`overview`,
`profile`, `comparison`, `timeline`, `explore`) is a note about the *shape* of the work, for the
next agent; it is never a question to put to the user.

If their words are genuinely empty, build the map that lets them ask a better question
(`explore`) and say plainly that no report was written. Do not invent a report nobody wanted;
do not skip the report when that is the job.

**A gap in the data is a price, not a disclaimer.** Never close a report with "this could be
wrong because…". Name the four or five places the evidence is thinner than the claims, and for
each one write: what is missing, **how to get it**, what it costs (money, queries, hours), and
what the number would do if it came back the other way. "The money is apportioned rather than read
from awards" is half a sentence; "apportioned; fix with NIH RePORTER, free, one query per funder,
about a day" is the whole one. If a finding cannot survive any of the four fixes, cut it. If it
survives all four, say so — that sentence is the report's spine.

**The report is about the field; the map is the evidence.** A reader who is told what a weight
means, how folding works, or what the coverage script does has been handed the instrument
instead of the finding. Those belong in `method.md`, for whoever checks the work. The report
carries findings and cites the nodes they rest on.

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

- **the report answers its brief** — every section is one of the questions `meta.brief` asks, every
  paragraph carries at least one node id, and every finding says what it would take to overturn
  it. Length is whatever those three rules produce; a word count is not a definition of done;
- **the shelves are measured** — `coverage` run against a reference, the four numbers in the
  report, every miss explained;
- **the gaps are paths** — every thin place names its fix, its cost and what the finding does
  without it, and no sentence in the report ends in "but this could be wrong";
- **the apparatus exists and stays out of the report** — `meta.weight.metric` says what the
  number on a node means, the method says how the corpus was built, the sources say what was
  asked and paid, and none of that machinery is explained to the reader of the report;
- **the map is readable** — `render`, then look at it: the categories at the top layer, a
  branch opens, 3D has depth, the docs button lists the set;
- **the cost is recorded** — wall clock, source calls, and what was paid, if anything.

Anything less is a map, not a survey. Say which one was delivered.
