# Where a list of works can come from

A map of a field is only as good as the list of works under it, and that list comes from a
provider. This file is the landscape: what each one gives, what it costs, and what it needs. Read
it before promising a user 10,000 articles — the limit is almost never the graph format, it is
the source.

**Nothing here is bundled with the skill.** `kg` is python3 and the standard library: it records
what a graph needs (`require --tool openalex`) and reads `meta.requires.tools` back, but a
provider is a *tool the agent already has*, on the user's own machine. That is deliberate. The
skill ships no keys, no client and no bill.

## The short list

| provider | what it is good for | access | limits to expect |
|---|---|---|---|
| **OpenAlex** | the default. Works, authors, institutions, concepts, citations and references in one graph, with ids that join to each other | free, no key; a polite `mailto` is appreciated | metered in credits (a search costs 10× a count); a large refresh can exhaust a day's free allowance — count first, then search |
| **Crossref** | publisher-deposited metadata: DOIs, funders, licences, reference lists. The authority for "is this DOI real" | free REST, no key (a polite pool with an email in the User-Agent) | no citation graph — references are deposited, *citations received* are not |
| **PubMed / Europe PMC** | biomedical and life sciences, including abstracts; Europe PMC also covers preprints and adds citation data | free (`E-utilities`; an NCBI key raises the rate limit), Europe PMC free REST | life sciences only; PubMed records are not concept-tagged the way OpenAlex is |
| **arXiv** | preprints, months before they are indexed anywhere else; full text is available | free API, no key | no citation graph, no author disambiguation, no institutions |
| **Semantic Scholar** | citation contexts, influence and "fields of study" for a work; a fast way to walk a citation neighbourhood | free API, key optional | unauthenticated requests share a small rate pool; a key is needed for anything sustained |
| **CORE** | open-access full texts, including repositories nobody else aggregates | API key required (free registration) | coverage is uneven by field |
| **DOAJ** | a clean list of open-access journals and articles, with licences | free API | open access only |
| **a web search tool** | the only way to evidence a *company*, and the fallback for anything the APIs do not hold. It can reach Google Scholar, publisher pages and company sites when a task says so | depends on the agent's own tools | no structured output: whatever it finds has to be turned into nodes by hand, and its claims need their source recorded |

Institutional subscriptions (Scopus, Web of Science, Dimensions, Lens.org) are better sources
than any of the above for bibliometrics, and they are not in the table because a skill cannot
assume them. If the user has one, use it, and say in the graph that the pull came from it.

## How to choose

1. **Ask what the graph has to answer.** A citation skeleton wants OpenAlex or Semantic Scholar
   (references/citations). A "who works on this and where" map wants OpenAlex (authors and
   institutions). A company map wants web search, plus the company's own pages as sources.
2. **Count before you search.** Most of these are rate-limited or metered, and the cost of a
   thousand searches is not the cost of one. `openalex_count` before `openalex_search` is the
   cheap habit that makes a 10k pull possible at all.
3. **Say where each node came from.** Whatever the provider, put it in the node:
   `--set found_by="openalex: search 'longevity'"` (or the query, the date, the tool). A map
   built from three sources with no provenance is a map nobody can audit, and the second agent
   to open it will have to redo the work.
4. **Expect to merge.** Two providers index the same paper under different ids. The join key is
   the DOI, which is why `publication` carries one; a node with no DOI is a node that will
   duplicate later.

## What a provider does not give you

- **Concepts.** OpenAlex tags works with concepts, and those tags are a starting point, not a
  conclusion. The subjects on a field map are the author's claim about what the field is made of,
  which is why every `subject` node carries a description (`add-node` refuses without one).
- **Institutions of a private company.** No free API lists what a private company is working on.
  A `company` node's edges are as good as the source you can cite for them, and nothing else.
- **A stopping rule.** "As many articles as possible" is a real strategy for a first pull, but it
  produces a graph where the number of nodes is a property of the query, not of the field. Once
  the map is drawn, the reading is what it is missing — which is what `review` and the notes are
  for.
