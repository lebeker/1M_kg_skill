# adapters

Importers for **other tools' export formats**. The engine knows `kg/1` and nothing
else; each adapter knows exactly one foreign format. That separation is the point: a
vendor's export shape must not become part of a general engine.

## Writing one

A file here exporting a single function:

```python
def convert(src: Path, title: str | None, schema: str, colors: dict) -> dict:
    """Return a complete kg/1 document."""
```

`src` is the file to read, `title` an optional override, `schema` and `colors` are the
engine's defaults to stamp into `meta`. Return `{"meta": ..., "nodes": [...],
"edges": [...]}`.

Use it as:

```bash
python3 scripts/kg.py import --format <name> --graph <file> --id <workspace-id>
python3 scripts/kg.py import --format <name> --graph <file> --out path/to.json
```

`python3 scripts/kg.py graphs` lists what is in the workspace afterwards.

## Conventions worth keeping

- **Carry the structure across.** If the source expresses hierarchy (a tree, panels,
  nesting) and you drop it, the result is a point cloud no viewer can repair. Use
  `parent`.
- **Lift links out of prose.** Exports rarely put URLs in a field called `link`; they
  bury them in a description. Extract them.
- **Record provenance** in `meta`: `imported_from` and `imported_at`. A graph whose
  origin is unknown cannot be re-derived.

## Shipped

| name | format |
|---|---|
| `foresight` | the Foresight Institute tech-tree `.graph` export (flat `items` list of nodes and edges) |
