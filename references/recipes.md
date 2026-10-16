# Recipes: three jobs, one document

What differs between these is **which nodes and relations go in, and how they are weighed** —
not which program draws them. Each recipe below is the whole of it: the same `render`, the same
viewer, a different document.

## 1. The Litmaps job — one paper's neighbourhood

Publications only, joined by citations. No companies, no subjects, no researchers: the map is
about *papers*, so the papers must be able to be big.

```bash
# the seed, with the numbers a reader will want beside it
kg.py new --id citation-map --title "The citation neighbourhood of X" --app viewer
kg.py add-node --graph citation-map --id seed --kind publication --label "Hallmarks of aging..." \
   --set weight=6.4 --set citations=6421 --set year=2023 --set doi=10.1016/j.cell.2022.11.001
# every paper it cites, and the direction of the relation
kg.py add-node --graph citation-map --id hallmarks-2013 --kind publication \
   --label "The Hallmarks of Aging" --set weight=14.9 --set citations=14920 --set year=2013
kg.py add-edge --graph citation-map --from seed --to hallmarks-2013 --label cites --dir in
```

The data comes from OpenAlex either way: `openalex_related --id <W…> --mode references|cited_by`
walks the citation graph at a tenfold discount over searching for the same papers
(`--per_page 20` is twenty papers for $0.0001). `openalex_get` then fills in titles, years, DOIs
and citation counts **for free**, up to twenty ids a call.

Weigh it by citations, in a unit a reader can hold:

```bash
kg.py weigh --graph citation-map --metric "thousands of citations (OpenAlex)" \
            --mul publication=10 --top 10
```

Two things this fixes, both of which a raw count gets wrong: raw citation counts put every
paper over a hundred citations at the ceiling, and the default multiplier for a publication
(0.1) assumes a paper is a small element of a *mixed* map. In a paper-only map it is the
subject, so it gets a multiplier of its own — for that graph alone, from its own document.

**A citation is an edge, not a layout trick.** `--dir in` draws the arrowhead at the cited work.
Co-citations are the weak texture *under* the citation skeleton: `--power 0.05
--set cocited=66` — thin and faint, with the count in the panel.

## 2. The GraphCommons job — the field, not the paper

The same viewer with the whole cast: publications, researchers, institutions, companies,
subjects. This is the case the starter vocabulary in `assets/README.md` is written for.

```bash
kg.py new --id longevity --title "Longevity — research field map" --app viewer
# ... nodes of six kinds, edges: authored / works at / is about / targets / collaborates on
kg.py weigh --graph longevity --metric "relevant papers per affiliation"
kg.py set-palette --graph longevity --kind preprint --color "#b7c4d6"   # any kind, any colour
```

The reading is the **rings** (organisations 0 → subjects 3) plus the sizes: a company that works
on a subject sits in the middle with the subjects it targets on the outside, and the papers that
connect them between. What makes it GraphCommons-shaped rather than Litmaps-shaped is only that
concepts and companies are nodes with weights of their own.

## 3. A map centred on something, weighted honestly

"I want it centred on this institute" and "weight by what actually matters" are two different
asks, and both are data:

| ask | how |
|---|---|
| centre on a person, institution or subject | `--set ring=0` on it (and on its collaborators), higher rings for what is further from it; or `--set x=`/`--set y=` for an exact place |
| weight by contribution to the field | the default: half the summed power of a node's edges × its kind multiplier |
| weight by money, headcount, citations, trials | `set-node --set weight=…` per node, then `weigh --metric "<the unit>" --bake` |
| correct one node by hand | `set-node --id <id> --set weight=…` — the panel then says *as the document states* |

**The metric is shown, not implied.** Every node's panel row reads `weight 0.203 — by relevant
papers` or `as the document states`, so a reader can see what a circle is a claim about, and a
later reader can disagree with the number rather than with the picture.

Naming the method is not decoration: *"weighted by grants"* and *"weighted by papers"* are
different claims about a field, and a graph that does not say which one it is cannot be argued
with. Say which one it is in `weigh --metric`, and put the reasoning in `--note` when the choice
is not obvious.

## What none of the three needs

A schema change. Every recipe above is `new`, `add-node`, `add-edge`, `set-node`, `set-edge`,
`weigh`, `render` — and the third job's whole point is that swapping what "importance" means
never touches the viewer.
