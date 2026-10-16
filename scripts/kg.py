#!/usr/bin/env python3
"""
kg.py - create / update / render a knowledge-graph artifact that an AGENT can
actually SEE.

The point of this tool is not storage. Agents already write JSON fine. The point
is that a graph artifact is unreadable as data - the semantics live in colour,
shape, level and position, none of which survives a text dump. So this renders a
self-contained HTML file AND a PNG, because an agent cannot look at HTML; it can
only look at pixels.

Subcommands:
  graphs          list the graphs in the workspace
  current         print the graph you are working on
  use             set the current graph
  suggest         which app fits a user's ask, what it needs, how a graph for it is shaped
  new             start an empty graph (--app, or --ask to pick the app from the words)
  import          convert another tool's export into kg format (--format <name>)
  add-node        append a node
  add-edge        append an edge
  set-node        update node fields in place
  set-palette     set the colour for a node kind
  set-meta        set a top-level meta field
  require         record what a graph needs: skills, plugins, tools, its app
  remove-node     delete a node and every edge touching it
  remove-edge     delete an edge by its endpoints
  validate        check conformance to kg/1
  merge           fold another kg/1 graph into this one
  info            what is in this graph — run this first
  stats           textual summary (what the graph contains)
  check           can this graph be shown here? what is missing, and install it
  apps            list the bundled viewers (templates)
  fetch-app       install an app from the catalogue: viewer + its own declaration
  fetch-viewer    download a viewer into assets/ — no node, no bun, no build
  render          write a standalone HTML from a template + the graph
  shot            headless-Chrome screenshot of that HTML -> PNG
  open            open the HTML in the real browser (for the human)
  serve           serve the graph, re-rendering on every change

Workspace:
  Graphs live in <root>/storage/<id>/graph.json — one folder per graph, so a graph's
  source, its JSON and its rendered page stay together. <root> is $KG_WORKSPACE, or
  the directory you run from. --graph accepts either an id from the workspace or a
  path to a .json file; with no --graph at all it uses the current graph (`use`).

What a graph needs (meta.app / meta.app_url / meta.requires):
  A graph names the app that draws it and, optionally, where to fetch that app if it is
  not here; and it declares the skills, plugins and tools the work needs. `check` reads
  all of that, says what is present and what is missing, and installs the app on request.
  The engine never fetches anything unless a command says so.

Renderers:
  A template is a single-file HTML carrying
  <script id="kg-graph" type="application/json">__KG_GRAPH__</script>.
  assets/viewer.html is the one that ships; `render`/`serve` substitute the graph into
  that element. This engine renders no HTML of its own — the viewer is a separate,
  replaceable artifact.

Graph format (kg/1):
{
  "meta": {"title": str, "schema": "kg/1", "colors": {kind: hex}},
  "nodes": [{"id","label","kind","level","size","style","color","x","y",
             "desc","link","doi","tags":[]}],
  "edges": [{"from","to","label","dir","weight","time","desc"}]
}
style: solid | hollow | cloud | critter | skull   (default solid)
dir:   none | in | out | both                     (arrow into / out of `to`)
level: number, 0 at the base of the axis          (optional)
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html import escape as html_escape
from pathlib import Path

SCHEMA = "kg/1"
URL_RE = re.compile(r"https?://[^\s\)\]\"<>]+")

DEFAULT_COLORS = {
    # ── goals / risks (if you map what you have, want, and face) ───────
    "have": "#4a9d7f",
    "want": "#4a7dc9",
    "threat": "#c0392b",
    "action": "#e08a1e",
    "skull": "#6b6b6b",
    # ── personal health (if you map a condition) ───────────────────────
    "organ": "#a05195",
    "condition": "#d45087",
    "protocol": "#2e8b8b",
    "research": "#7f6ad4",
    "marker": "#e6a817",
    "evidence": "#8d99ae",
    "treatment": "#e07a5f",
    # ── research branch (default vocabulary) ───────────────────────────
    # The main cases of a research map, and the names the viewer's starter palette uses, so a
    # graph built with no app declared still comes out in the same colours as one built with
    # the research app. `scientist`/`concept`/`research` are older names and still work.
    "publication": "#cdd9e5",
    "researcher": "#d47fa6",
    "scientist": "#d47fa6",
    "subject": "#7b9ecb",
    "concept": "#7b9ecb",
    "lab": "#93c47d",
    "company": "#f5a623",
    "institution": "#9aa0a6",
    "person": "#d47fa6",
    "goal": "#66c2a5",
    "project": "#8da0cb",
    # ── generic ────────────────────────────────────────────────────────
    "default": "#888888",
}


def kind_color(kind: str, colors: dict) -> str:
    return colors.get(kind) or colors.get("default") or "#888888"


# --------------------------------------------------------------- importance
#
# Half the sum of the powers of the edges touching a node, times a multiplier for its kind. The
# viewer computes the same thing for a graph that does not state a weight; `weigh` states it, and
# can bake it into `size` so the numbers travel with the document. Keep the two in step:
# webapp/src/kg.ts, DEFAULT_KIND_MULTIPLIERS / WEIGHT_SCALE / WEIGHT_MIN_PX / WEIGHT_MAX_PX.
DEFAULT_SIZE_MULTIPLIERS = {
    "publication": 0.1, "paper": 0.1, "article": 0.1,
    "researcher": 1.0, "scientist": 1.0, "person": 1.0,
    "lab": 3.0, "institution": 3.0, "company": 3.0,
    "subject": 10.0, "concept": 10.0,
}
WEIGHT_SCALE, WEIGHT_MIN_PX, WEIGHT_MAX_PX = 2.5, 1.5, 28.0


def px_from_weight(score: float) -> float:
    return min(WEIGHT_MAX_PX, max(WEIGHT_MIN_PX, WEIGHT_SCALE * math.sqrt(max(0.0, score))))


def edge_power(e: dict) -> float:
    """An edge's power, defaulting to 1. `weight` is the older spelling."""
    for key in ("power", "weight"):
        v = e.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    return 1.0


# ------------------------------------------------------------------ loading

def load(path: Path) -> dict:
    if path.is_dir():
        doc = graph_file_in(path)
        if doc is None:
            raise SystemExit(f"error: {path} is a folder with no graph document in it.\n"
                             f"  a graph folder holds graph.json or its one .json file")
        path = doc
    if not path.exists():
        return {"meta": {"title": path.stem, "schema": SCHEMA, "colors": dict(DEFAULT_COLORS)},
                "nodes": [], "edges": []}
    try:
        g = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(f"error: {path} is not valid JSON ({e}).\n"
                         f"  If it is another tool's export, it is a different format — "
                         f"import it first:\n"
                         f"    python3 scripts/kg.py import --format <name> "
                         f"--graph {path} --out {path.with_suffix('.json')}")
    # A raw export from another tool is not a kg/1 document. Loading one used to yield
    # a silent, plausible "0 nodes" — the worst possible answer. Refuse it loudly and
    # say how to convert it.
    if isinstance(g, dict) and "nodes" not in g and isinstance(g.get("items"), list):
        raise SystemExit(f"error: {path} is a raw export from another tool, not a kg/1 "
                         f"graph.\n"
                         f"  Import it:\n"
                         f"    python3 scripts/kg.py import --format <name> "
                         f"--graph {path} --out {path.with_suffix('.json')}\n"
                         f"  adapters available: "
                         f"{', '.join(adapter_names()) or '(none)'}")
    if not isinstance(g, dict) or not isinstance(g.get("nodes"), list) \
            or not isinstance(g.get("edges"), list):
        raise SystemExit(f"error: {path} is not a kg/1 graph — it has no 'nodes' and "
                         f"'edges' arrays.\n"
                         f"  Create a new one:  python3 scripts/kg.py new --out "
                         f"{path} --title \"...\"")
    g.setdefault("meta", {})
    g.setdefault("nodes", [])
    g.setdefault("edges", [])
    # seed any known kind the palette is missing, without clobbering existing keys
    colors = g["meta"].setdefault("colors", {})
    for k, v in DEFAULT_COLORS.items():
        colors.setdefault(k, v)
    g["meta"].setdefault("schema", SCHEMA)
    return g


def save(g: dict, path: Path) -> None:
    """Write the graph, creating the parent directory if the agent has not."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(g, indent=1))


def ensure_ids(g: dict) -> None:
    have = {n["id"] for n in g["nodes"]}
    for i, n in enumerate(g["nodes"]):
        if not n.get("id"):
            nid = f"n{i + 1}"
            while nid in have:
                nid += "_"
            n["id"] = nid
            have.add(nid)


# ------------------------------------------------------------------ adapters

ADAPTERS_DIR = Path(__file__).resolve().parent / "adapters"


def adapter_names() -> list[str]:
    if not ADAPTERS_DIR.is_dir():
        return []
    return sorted(p.stem for p in ADAPTERS_DIR.glob("*.py") if not p.stem.startswith("_"))


def load_adapter(name: str):
    """Import scripts/adapters/<name>.py.

    One tool's export format is not another's, and every tool invents its own. Keeping
    importers out of the engine is what keeps the format general: the engine knows kg/1
    and nothing else; an adapter knows exactly one foreign shape.
    """
    if name not in adapter_names():
        raise SystemExit(f"error: no adapter '{name}'.\n"
                         f"  available: {', '.join(adapter_names()) or '(none)'}\n"
                         f"  see scripts/adapters/README.md")
    spec = importlib.util.spec_from_file_location(f"kg_adapter_{name}",
                                                  ADAPTERS_DIR / f"{name}.py")
    if spec is None or spec.loader is None:
        raise SystemExit(f"error: could not load adapter '{name}'")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "convert"):
        raise SystemExit(f"error: adapter '{name}' has no "
                         f"convert(src, title, schema, colors) function")
    return mod


# ------------------------------------------------------- schema / conformance

# Node kinds the Researcher vocabulary uses. A graph may declare any kinds it likes;
# these are the ones the skill understands without further explanation.
RESEARCH_KINDS = [
    "concept",   # a question, mechanism, hypothesis or field area
    "paper",     # a publication
    "scientist", # a person doing the research
    "idea",      # a proposed direction, not yet a paper
    "experiment",# a planned or running study
    "company",   # a commercial entity
    "institution", # university, institute, funder
    "tool",      # an instrument, dataset, method or software
]


def conform(g: dict) -> dict:
    """Check conformance of a `kg/1` document.

    Returns {"errors": [...], "warnings": [...], "info": [...]}.  A graph that validates
    is a *shareable artifact*: another agent, in another session, on another machine, can
    open it, trust it, and edit it without asking the author what the fields mean.
    """
    errors, warnings, info = [], [], []
    meta = g.get("meta") or {}
    nodes = g.get("nodes")
    edges = g.get("edges")

    if meta.get("schema") != SCHEMA:
        errors.append(f"meta.schema is {meta.get('schema')!r}, expected {SCHEMA!r}")
    if not meta.get("title"):
        warnings.append("meta.title is empty — the render will be titled 'knowledge graph'")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        errors.append("'nodes' and 'edges' must both be arrays")
        return {"errors": errors, "warnings": warnings, "info": info}
    if not nodes:
        info.append("the graph is empty")

    # --- ids: present, unique, string
    seen, dupes, unkeyed = set(), [], []
    for i, n in enumerate(nodes):
        nid = n.get("id")
        if nid in (None, ""):
            unkeyed.append(i)
            continue
        if nid in seen:
            dupes.append(nid)
        seen.add(nid)
    if unkeyed:
        errors.append(f"{len(unkeyed)} node(s) have no id — nothing can reference them")
    if dupes:
        errors.append(f"duplicate node ids {sorted(set(dupes))[:8]} — another agent cannot "
                      "tell which one it is editing")

    # --- required node fields.  An unlabeled node is legal when it is a CONTAINER
    # (a panel/group that holds children) — the reader navigates to it, not into it.
    parented = {n.get("parent") for n in nodes if n.get("parent") not in (None, "")}
    has_children = {n.get("parent") for n in nodes if n.get("parent") not in (None, "")}
    bare_containers, bare_leafs = [], []
    for n in nodes:
        if (n.get("label") or "").strip():
            continue
        (bare_containers if n.get("id") in has_children else bare_leafs).append(n.get("id"))
    if bare_leafs:
        errors.append(f"{len(bare_leafs)} node(s) have no label and no children — the "
                      f"reader sees an unnamed dot: {bare_leafs[:5]}")
    if bare_containers:
        info.append(f"{len(bare_containers)} unlabeled container node(s) (panels/groups) "
                    "— legal, they carry children")

    for n in nodes:
        nid = n.get("id", "?")
        if not (n.get("kind") or "").strip():
            warnings.append(f"node {nid}: no kind — it renders in a hashed colour")

    # --- dangling parent references: the tree silently loses a whole subtree
    for n in nodes:
        p = n.get("parent")
        if p not in (None, "") and p not in seen:
            errors.append(f"node {n.get('id')!r}: parent {p!r} is not a node id — the "
                          "subtree is orphaned")

    # --- edges
    for i, e in enumerate(edges):
        src, dst = e.get("from"), e.get("to")
        if src not in seen:
            errors.append(f"edge {i}: 'from' {src!r} is not a node id")
        if dst not in seen:
            errors.append(f"edge {i}: 'to' {dst!r} is not a node id")
        if src == dst and src is not None:
            warnings.append(f"self-loop on {src!r}")

    labeled_edges = sum(1 for e in edges if (e.get("label") or "").strip())
    if edges and not labeled_edges:
        warnings.append(f"all {len(edges)} edge(s) are unlabeled — every relation reads the "
                        "same, so the reader must click each one")
    elif labeled_edges < len(edges):
        info.append(f"{labeled_edges}/{len(edges)} edge(s) carry a label")

    # --- palette coverage: a missing colour makes the legend lie
    colors = meta.get("colors") or {}
    kinds = {n.get("kind") for n in nodes if n.get("kind")}
    unpainted = sorted(k for k in kinds if k not in colors)
    if unpainted:
        warnings.append(f"kinds with no colour {unpainted} — they get a hashed colour and "
                        "the legend lies")

    # --- structure an agent should know before editing
    deg = {}
    for e in edges:
        deg[e.get("from")] = deg.get(e.get("from"), 0) + 1
        deg[e.get("to")] = deg.get(e.get("to"), 0) + 1
    lonely = [n.get("id") for n in nodes
              if not deg.get(n.get("id")) and n.get("id") not in has_children]
    if lonely:
        info.append(f"{len(lonely)} node(s) are isolated (no edges, no children) — legal, "
                    "but nothing links them to the rest")

    return {"errors": errors, "warnings": warnings, "info": info}


# ------------------------------------------------ workspace and templates

PLACEHOLDER = "__KG_GRAPH__"
GRAPH_ELEMENT_RE = re.compile(
    r"(<script[^>]*\bid=[\"\']kg-graph[\"\'][^>]*>)(.*?)(</script>)", re.S)


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return s or "graph"


def parse_sets(pairs: list[str]) -> tuple[dict, list[str]]:
    """`KEY=VALUE` pairs -> the properties they name.

    Numbers stay numbers, so a reader can sort on them. A pair that is not KEY=VALUE is
    returned instead of guessed at: silently dropping a property someone asked for is how a
    graph ends up quietly missing a field, and nobody notices until they look at the picture.
    """
    out: dict = {}
    bad: list[str] = []
    for kv in pairs:
        k, sep, v = kv.partition("=")
        k = k.strip()
        if not sep or not k:
            bad.append(kv)
            continue
        try:
            out[k] = float(v) if v.strip() else v
        except ValueError:
            out[k] = v
    return out, bad


def workspace_root() -> Path:
    """Where the graphs live: $KG_WORKSPACE if set, else the working directory."""
    return Path(os.environ.get("KG_WORKSPACE") or ".").expanduser().resolve()


def storage_dir() -> Path:
    return workspace_root() / "storage"


def graph_dir(gid: str) -> Path:
    return storage_dir() / gid


def current_marker() -> Path:
    return storage_dir() / ".current"


def current_id() -> str | None:
    m = current_marker()
    if not m.exists():
        return None
    gid = m.read_text().strip()
    return gid or None


def set_current(gid: str) -> None:
    current_marker().parent.mkdir(parents=True, exist_ok=True)
    current_marker().write_text(gid + "\n")


def graph_file_in(d: Path) -> Path | None:
    """The graph inside a workspace folder: `graph.json`, or the folder's only .json.

    The fallback is forgiveness, not sloppiness: folders arrive from earlier sessions
    holding `longevity.json`, and refusing them would make the workspace a convention
    nobody can retrofit.
    """
    if not d.is_dir():
        return None
    g = d / "graph.json"
    if g.exists():
        return g
    cands = sorted(p for p in d.glob("*.json") if p.name != "graph.json")
    return cands[0] if len(cands) == 1 else None


def graph_target(gid: str) -> Path:
    """Where to write a graph: into its existing file if it has one, else graph.json."""
    d = graph_dir(gid)
    return graph_file_in(d) or (d / "graph.json")


def workspace_graphs() -> list[dict]:
    """Every graph in the workspace, most recently written first."""
    out: list[dict] = []
    if not storage_dir().is_dir():
        return out
    for d in sorted(storage_dir().iterdir()):
        g = graph_file_in(d)
        if g is None:
            continue
        try:
            doc = json.loads(g.read_text())
        except (json.JSONDecodeError, OSError):
            out.append({"id": d.name, "path": g, "nodes": None, "edges": None,
                        "title": "(unreadable)", "mtime": 0.0})
            continue
        out.append({
            "id": d.name,
            "path": g,
            "nodes": len(doc.get("nodes") or []),
            "edges": len(doc.get("edges") or []),
            "title": (doc.get("meta") or {}).get("title") or "",
            "mtime": g.stat().st_mtime,
        })
    return sorted(out, key=lambda r: r.get("mtime", 0.0), reverse=True)


def resolve_graph(value: str | None) -> Path:
    """--graph is an id from the workspace or a path. No --graph: the current graph."""
    if value:
        p = Path(value).expanduser()
        # A graph is a folder with a document in it, so handing over the folder is a normal
        # thing to do — a traceback out of open() is not an answer.
        if p.is_dir():
            doc = graph_file_in(p)
            if doc is None:
                raise SystemExit(f"error: {p} is a folder with no graph document in it.\n"
                                 f"  a graph folder holds graph.json or its one .json file")
            return doc
        if "/" in value or value.endswith(".json") or p.is_file():
            return p
        cand = graph_file_in(graph_dir(value))
        if cand is not None:
            return cand
        raise SystemExit(f"error: no graph '{value}' in {storage_dir()} and no such "
                         f"file.\n  list them:  python3 scripts/kg.py graphs")
    cur = current_id()
    if cur:
        p = graph_file_in(graph_dir(cur))
        if p is None:
            raise SystemExit(f"error: the current graph '{cur}' is gone from "
                             f"{storage_dir()}.\n  list them:  python3 scripts/kg.py "
                             f"graphs")
        return p
    raise SystemExit("error: no --graph given and no current graph.\n"
                     "  list them:  python3 scripts/kg.py graphs\n"
                     "  pick one:   python3 scripts/kg.py use <id>")


def assets_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "assets"


def template_names() -> list[str]:
    if not assets_dir().is_dir():
        return []
    return sorted(p.stem for p in assets_dir().glob("*.html"))


def template_rows() -> list[dict]:
    """Every template present, whether it can be rendered into, and where it came from.

    The `<name>.version` sidecar is written by whoever built the template (the web-app
    repo's bundle script). It is how a reader finds out which app this is and where to
    fetch a newer one, without the skill having to know any particular app.
    """
    rows = []
    for n in template_names():
        p = assets_dir() / f"{n}.html"
        txt = p.read_text(errors="replace")
        m = GRAPH_ELEMENT_RE.search(txt)
        row = {"name": n, "path": p, "bytes": p.stat().st_size, "ok": bool(m),
               "placeholder": (m.group(2).strip() if m else None)}
        sidecar = assets_dir() / f"{n}.version"
        if sidecar.exists():
            try:
                row["stamp"] = json.loads(sidecar.read_text())
            except json.JSONDecodeError:
                row["stamp"] = {"version": sidecar.read_text().strip()}
        rows.append(row)
    return rows


def default_app() -> str | None:
    """The template a new graph should name: the one that ships, if it is here."""
    return "viewer" if (assets_dir() / "viewer.html").exists() else None


def stamp_for(app: str) -> dict:
    """The provenance sidecar of a template, if it has one."""
    sidecar = assets_dir() / f"{app}.version"
    if not sidecar.exists():
        return {}
    try:
        return json.loads(sidecar.read_text())
    except json.JSONDecodeError:
        return {}


def default_app_url() -> str:
    """Where the shipped app can be fetched from — recorded on the graph itself.

    A graph that names `app: viewer` should also be able to say where to get one, or the
    document is only portable to machines that already have the same assets. The URL comes
    from the template's own provenance, so nothing here hardcodes a vendor.
    """
    app = default_app()
    if not app:
        return ""
    return stamp_for(app).get("fetch_url") or ""


# ------------------------------------------------------- what a graph needs

def skill_search_roots() -> list[Path]:
    """Where an agent might keep skills. Checked, not assumed: a "found" means a folder
    with a SKILL.md is actually there."""
    roots: list[Path] = []
    env = os.environ.get("KG_SKILLS_PATH")
    if env:
        roots += [Path(p).expanduser() for p in env.split(":") if p]
    here = Path.cwd()
    ws = workspace_root()
    for base in (here, ws):
        roots += [base / ".codex" / "skills", base / ".claude" / "skills", base / "skills"]
    roots += [Path.home() / ".hermes" / "skills", Path.home() / ".claude" / "skills"]
    seen, out = set(), []
    for r in roots:
        key = str(r)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def find_skill(name: str) -> Path | None:
    for r in skill_search_roots():
        p = r / name
        try:
            if (p / "SKILL.md").exists():
                return p
        except OSError:
            continue
    return None


def check_graph(g: dict, path: Path, install: bool, probe: bool) -> int:
    """What does this graph need to be shown, and what of that is missing?

    The point is that a graph arriving from someone else must be able to tell you what it
    needs — a viewer it does not have, a skill, a tool — instead of failing with a stack
    trace or, worse, rendering with the wrong drawer. Installing anything is explicit:
    `--install` is the consent.
    """
    meta = g.get("meta") or {}
    app = meta.get("app") or "viewer"
    app_url = meta.get("app_url") or ""
    req = meta.get("requires") or {}
    dest = assets_dir() / f"{app}.html"
    have = dest.exists()

    print(f"graph     {path}")
    print(f"app       {app}")

    if not have and install and app_url:
        print(f"          missing — fetching it because you asked (--install)")
        rc = fetch_viewer(app_url, app, force=False)
        have = dest.exists() if rc == 0 else have
        if rc != 0:
            print("          install failed; see the error above")
    print(f"          {'present  ' + str(dest) if have else 'MISSING — this graph cannot be rendered without it'}")

    if app_url:
        print(f"app_url   {app_url}")
        if probe:
            try:
                rq = urllib.request.Request(app_url, method="HEAD",
                                            headers={"User-Agent": "kg-skill-check/1"})
                with urllib.request.urlopen(rq, timeout=20) as r:
                    size = r.headers.get("Content-Length")
                    print(f"          reachable — HTTP {r.status}"
                          + (f", {int(size):,} bytes" if size else ""))
            except Exception as e:
                print(f"          NOT reachable: {e}")

    declared = {k: list(req.get(k) or []) for k in ("skills", "plugins", "tools")}
    if not any(declared.values()):
        print("requires  nothing declared (see `require`)")
    else:
        for kind, names in declared.items():
            for name in names:
                if kind == "skills":
                    found = find_skill(name)
                    state = (f"found — {found}" if found else
                             "not found in " +
                             ", ".join(str(r) for r in skill_search_roots() if r.is_dir()))
                elif kind == "plugins":
                    state = ("declared — the viewer or host provides it; not verifiable "
                             "from here")
                else:
                    state = "declared source — used when searching or enriching"
                print(f"{kind[:-1]:<9} {name}"
                      .ljust(20) + f" {state}")

    if not have:
        print()
        if app_url:
            print(f"to show this graph:  kg.py fetch-viewer --url {app_url} --as {app}")
        else:
            print("to show this graph: the app it names is not here and the graph does not "
                  "say where to get it.\n  Drop the file into " + str(assets_dir()) +
                  ", then: kg.py render")
        return 1
    return 0


def fetch_viewer(url: str, name: str | None, force: bool) -> int:
    """Download a single-file viewer into assets/.

    This is the ONLY command in the engine that touches the network, and it is deliberate:
    the people who use the graph should not have to install node and bun to get a page to
    look at it. Nothing is ever fetched implicitly — `render` will not download an app a
    graph asks for, because rendering a downloaded page means running someone else's code
    in the user's browser with their data in it. That is the user's call, made out loud.
    """
    path_part = urllib.parse.urlparse(url).path
    if not name:
        name = Path(path_part).stem or "viewer"
    name = re.sub(r"[^A-Za-z0-9._-]", "-", name).strip("-") or "viewer"
    dest = assets_dir() / f"{name}.html"

    if dest.exists() and not force:
        print(f"error: {dest} already exists — pass --force to replace it", file=sys.stderr)
        return 2

    req = urllib.request.Request(url, headers={"User-Agent": "kg-skill-fetch-viewer/1"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
    except Exception as e:  # URLError, HTTPError, timeout, bad scheme…
        print(f"error: could not fetch {url}\n  {e}", file=sys.stderr)
        return 3

    if len(body) < 20_000:
        print(f"error: {len(body)} bytes is too small to be a viewer — refusing it",
              file=sys.stderr)
        return 3
    text = body.decode("utf-8", errors="replace")
    if not GRAPH_ELEMENT_RE.search(text):
        print(f"error: what came back from {url} has no #kg-graph element, so it is not a "
              f"viewer for this format. Nothing was written.", file=sys.stderr)
        return 3

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    (assets_dir() / f"{name}.version").write_text(json.dumps({
        "name": name,
        "origin": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bytes": len(body),
        "sha256": digest,
    }, indent=1) + "\n")

    print(f"installed {dest} ({len(body)} bytes)")
    print(f"  from   {url}")
    print(f"  sha256 {digest}")
    print(f"  name   {name}   (use it with: render --app {name})")
    print("  This page runs in the browser with your graph inside it — only fetch a "
          "viewer from a source you trust.")
    return 0


# --------------------------------------------------------- the app catalogue

def catalogue() -> list[dict]:
    """The apps this skill knows about, from `scripts/apps.json`.

    A finite list on purpose. The app's own manifest (`<name>.app.json`, installed next to
    the viewer) is what the app says about itself; this is what the skill knows before
    anything is installed, which is the state a user's first question arrives in. A
    discovery process that asks a server for available apps replaces this file, not the
    commands that read it.
    """
    p = Path(__file__).resolve().parent / "apps.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
    except Exception:
        return []
    apps = data.get("apps") if isinstance(data, dict) else data
    return [a for a in (apps or []) if isinstance(a, dict) and a.get("id")]


def catalogue_entry(name: str) -> dict:
    for a in catalogue():
        if a.get("id") == name:
            return a
    return {}


def app_manifest(name: str) -> dict:
    """The app's own declaration, installed beside it as `<name>.app.json`."""
    p = assets_dir() / f"{name}.app.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text())
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def app_facts(name: str) -> dict:
    """Catalogue entry + installed manifest. The manifest is the app's own word, so it wins."""
    facts = dict(catalogue_entry(name))
    for k, v in app_manifest(name).items():
        if v not in (None, "", [], {}):
            facts[k] = v
    return facts


def requirement_state(name: str, kind: str) -> tuple[bool | None, str]:
    """(is it here, one line for a human). None means: this file cannot know."""
    if kind == "skills":
        found = find_skill(name)
        if found:
            return True, f"found — {found}"
        tried = ", ".join(str(r) for r in skill_search_roots() if r.is_dir())
        return False, f"not found — looked in {tried}"
    if kind == "plugins":
        return None, "declared — the viewer or the host provides it; not verifiable here"
    return None, ("declared — used to search and enrich; a JSON file cannot see whether "
                  "this machine has it")


def score_app(ask: str, app: dict) -> tuple[int, list[str]]:
    """How well does this app fit what the user asked for? Keywords are the signal; words
    from the title and purpose are a weaker one, so a vague ask still lands somewhere
    instead of on whatever happens to be first."""
    text = ask.lower()
    hits = [kw for kw in (app.get("keywords") or []) if kw.lower() in text]
    words = set(re.findall(r"[a-z]{4,}", text))
    blob = f"{app.get('title', '')} {app.get('purpose', '')}".lower()
    soft = sorted(w for w in words if w in blob and w not in hits)
    return len(hits) * 3 + len(soft), hits + soft


def print_app_guide(facts: dict, pad: str = "") -> int:
    """What an app is for, what it needs, and what it builds. Prints the missing pieces and
    returns how many of them there are — a person has to hear about those before anything
    gets installed."""
    notes = facts.get("tool_notes") or {}
    missing = 0
    unverifiable: list[str] = []
    for kind in ("skills", "plugins", "tools"):
        for name in (facts.get("requires") or {}).get(kind) or []:
            here, state = requirement_state(name, kind)
            if here is False:
                missing += 1
            elif here is None:
                unverifiable.append(name)
            note = notes.get(name)
            print(f"{pad}{kind[:-1]:<9} {name}" + (f" — {note}" if note else ""))
            print(f"{pad}          {state}")
    for name in ((facts.get("recommends") or {}).get("tools") or []):
        note = notes.get(name)
        print(f"{pad}{'suggests':<9} {name}" + (f" — {note}" if note else ""))
    if facts.get("kinds"):
        print(f"{pad}kinds     " + ", ".join(
            str(k.get("kind")) for k in facts["kinds"] if k.get("kind")))
    for e in facts.get("edges") or []:
        line = f"{e.get('pattern', '')}" + (f" — {e.get('meaning')}" if e.get("meaning") else "")
        print(f"{pad}edges     {line}")
    if unverifiable:
        print(f"{pad}note      {', '.join(unverifiable)} cannot be checked from a file: "
              f"confirm this agent has them (an MCP tool, a plugin or a key) before building "
              f"the graph from them, and tell the user what to add if it does not.")
    return missing


def suggest_app(ask: str) -> int:
    """Which app fits this ask, what it needs, and how a graph for it is shaped."""
    apps = catalogue()
    if not apps:
        print("error: no app catalogue here (scripts/apps.json) — nothing to suggest",
              file=sys.stderr)
        return 3
    scored = sorted(((score_app(ask, a)[0], a) for a in apps), key=lambda t: -t[0])
    score, best = scored[0]
    name = best["id"]
    facts = app_facts(name)
    installed = (assets_dir() / f"{name}.html").exists()

    print(f'ask       "{ask}"')
    print(f"app       {name} — {best.get('title', '')}"
          + ("" if score else "   (nothing matched; it is the only app this skill knows)"))
    hits = score_app(ask, best)[1]
    if hits:
        print(f"matched   {', '.join(hits[:8])}")
    if facts.get("purpose"):
        print(f"purpose   {facts['purpose']}")
    print(f"installed {'yes' if installed else 'no'}")
    missing = print_app_guide(facts)
    print()
    if not installed:
        print(f"to install it:  kg.py fetch-app {name}"
              + ("" if best.get("url") else "   (no url in the catalogue)"))
    if missing:
        print(f"missing   {missing} required piece(s) — tell the user which, what each is for, "
              f"and that the graph is built from them. Install nothing without a yes.")
    print(f"then      kg.py new --id <id> --app {name} --title \"…\"")
    return 0


def fetch_app(name: str, url: str | None, manifest_url: str | None, force: bool) -> int:
    """Install an app from the catalogue: the viewer, and the app's own declaration.

    `--url` overrides the catalogue, which is how a mirror, a fork or a local build gets
    installed by the same command.
    """
    entry = catalogue_entry(name)
    src = url or entry.get("url")
    if not entry and not url:
        print(f"error: '{name}' is not in the catalogue (scripts/apps.json) — "
              f"pass --url to install a viewer from somewhere else", file=sys.stderr)
        return 2
    if not src:
        print(f"error: the catalogue has no url for '{name}'", file=sys.stderr)
        return 3
    rc = fetch_viewer(src, name, force)
    if rc != 0:
        return rc

    man_src = manifest_url or entry.get("manifest_url")
    if not man_src:
        return 0
    try:
        rq = urllib.request.Request(man_src, headers={"User-Agent": "kg-skill-fetch-app/1"})
        with urllib.request.urlopen(rq, timeout=60) as r:
            body = r.read()
        d = json.loads(body.decode("utf-8", errors="replace"))
        if not isinstance(d, dict) or not d.get("id"):
            raise ValueError("that is not an app manifest")
        (assets_dir() / f"{name}.app.json").write_text(json.dumps(d, indent=1) + "\n")
        print(f"  what   {d.get('title', '')} — {d.get('purpose', '')}")
        print_app_guide(d, pad="  ")
    except Exception as e:
        print(f"  note   the viewer is installed, but its manifest did not come with it "
              f"({man_src}): {e}\n"
              f"         what it needs is still in this skill's catalogue: kg.py apps",
              file=sys.stderr)
    return 0


def template_path(app: str | None) -> Path:
    """A template is a single-file HTML with the graph element in it."""
    if app:
        p = assets_dir() / (app if app.endswith(".html") else app + ".html")
        if not p.exists():
            raise SystemExit(f"error: no template '{app}' in {assets_dir()}\n"
                             f"  available: {', '.join(template_names()) or '(none)'}")
        return p
    default = assets_dir() / "viewer.html"
    if not default.exists():
        raise SystemExit(f"error: no bundled viewer at {default}\n"
                         f"  this skill ships templates, it does not build them.\n"
                         f"  build one and copy it in — see README.\n"
                         f"  available: {', '.join(template_names()) or '(none)'}")
    return default


def inject(html: str, g: dict) -> str:
    """Put the graph into the template's placeholder element.

    Only the *text of that one element* is replaced; nothing else in the template is
    touched. `</script>` inside the payload would close the element early, so it is
    escaped — the graph is data and must not be able to break the page.
    """
    found = GRAPH_ELEMENT_RE.findall(html)
    if not found:
        raise SystemExit('error: this template has no <script id="kg-graph" '
                         'type="application/json"> element to put the graph in')
    if len(found) > 1:
        raise SystemExit("error: this template has more than one #kg-graph element — "
                         "which one gets the graph?")
    m = GRAPH_ELEMENT_RE.search(html)
    payload = json.dumps(g, separators=(",", ":")).replace("</script>", "<\\/script>")
    return html[:m.start(2)] + payload + html[m.end(2):]


def default_out(graph: Path) -> Path:
    """Next to the graph when it lives in the workspace, else the classic name."""
    try:
        graph.resolve().relative_to(storage_dir().resolve())
    except ValueError:
        return Path("graph.html")
    return graph.resolve().parent / "index.html"


def file_url(p: Path) -> str:
    return "file://" + urllib.parse.quote(str(p.resolve()))


def render(g: dict, out: Path, app: str | None = None) -> Path:
    """A template plus the graph, written as one self-contained HTML file.

    Which template, in order: `--app`, then the graph's own `meta.app`, then the shipped
    `viewer.html`. The graph naming its viewer is the interface — the same JSON can be
    rendered by a different app on a different machine without editing anything.
    """
    app = app or (g.get("meta") or {}).get("app")
    try:
        tmpl = template_path(app)
    except SystemExit:
        # A graph that says where its app lives can be helped; say so before giving up.
        url = (g.get("meta") or {}).get("app_url")
        if url:
            print(f"  this graph says its app can be fetched from:\n    {url}\n"
                  f"    python3 scripts/kg.py check --install", file=sys.stderr)
        raise
    html = inject(tmpl.read_text(), g)
    title = (g.get("meta") or {}).get("title") or "knowledge graph"
    html = re.sub(r"<title>.*?</title>", f"<title>{html_escape(title)}</title>",
                  html, count=1, flags=re.S)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    return out


CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


def find_chrome() -> str | None:
    for c in CHROME_CANDIDATES:
        if Path(c).exists():
            return c
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    return None


# -------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description="create/update/render a knowledge graph")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def with_graph(p):
        p.add_argument("--graph", help="graph id from the workspace, or a path to a "
                                       ".json file (default: the current graph)")
        return p

    p = sub.add_parser("graphs", help="list the graphs in the workspace")
    p.add_argument("--json", action="store_true", help="machine-readable output")

    sub.add_parser("current", help="print the graph you are working on")

    p = sub.add_parser("use", help="set the current graph")
    p.add_argument("id")

    p = sub.add_parser("apps", help="list the bundled viewers (templates)")
    p.add_argument("--json", action="store_true", help="machine-readable output")

    p = sub.add_parser("fetch-viewer", help="download a viewer into assets/ "
                                            "(no node, no bun, no build)")
    p.add_argument("--url", required=True, help="where the single-file viewer lives")
    p.add_argument("--as", dest="as_", help="template name (default: from the URL)")
    p.add_argument("--force", action="store_true", help="replace an existing template")

    p = sub.add_parser("suggest", help="which app fits this ask, what it needs, and how a "
                                       "graph for it is shaped")
    p.add_argument("ask", help="what the user asked for, in their own words")

    p = sub.add_parser("fetch-app", help="install an app from the catalogue: the viewer and "
                                         "the app's own declaration")
    p.add_argument("id", help="app id, e.g. viewer")
    p.add_argument("--url", help="install from here instead of the catalogue "
                                 "(a mirror, a fork, a local build)")
    p.add_argument("--manifest-url", dest="manifest_url",
                   help="where the app's declaration lives")
    p.add_argument("--force", action="store_true", help="replace an existing copy")

    p = sub.add_parser("new", help="start an empty graph")
    p.add_argument("--out", help="explicit path (default: storage/<id>/graph.json)")
    p.add_argument("--id", help="workspace id for the graph")
    p.add_argument("--title", default="graph")
    p.add_argument("--app", help="seed the graph from this app: its requirements, kinds, "
                                 "colours and the shape of its edges")
    p.add_argument("--ask", help="a user's words — pick the app that fits, then seed from it")

    p = sub.add_parser("import", help="convert another tool's export into kg format")
    p.add_argument("--format", dest="fmt", required=True,
                   help=f"adapter name: {', '.join(adapter_names()) or '(none)'}")
    p.add_argument("--graph", required=True, help="the file to convert")
    p.add_argument("--out", help="explicit path (default: storage/<id>/graph.json)")
    p.add_argument("--id", help="workspace id for the result")
    p.add_argument("--title")

    p = with_graph(sub.add_parser("add-node"))
    p.add_argument("--id", required=True); p.add_argument("--label", required=True)
    p.add_argument("--kind", default="concept")
    p.add_argument("--level", type=float)
    p.add_argument("--size", type=float,
                   help="a weight from 1 to 10. Leave it out and the reader sizes the node by "
                        "how connected it is, so the map shows importance without editing.")
    p.add_argument("--style", default="solid"); p.add_argument("--color")
    p.add_argument("--desc", default=""); p.add_argument("--link", default="")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                   help="any other property, set as given (repeatable). A graph is data: "
                        "the reader shows what you put here, so a new field is an edit to "
                        "the graph, never a change to the app that draws it. Example: "
                        "--set doi=10.1126/science.abn9257")

    p = with_graph(sub.add_parser("add-edge"))
    p.add_argument("--from", dest="src", required=True)
    p.add_argument("--to", dest="dst", required=True)
    p.add_argument("--label", default="")
    p.add_argument("--dir", default="none", choices=["none", "in", "out", "both"])
    p.add_argument("--power", type=float, default=1,
                   help="how much this relation weighs, where 1 is a normal relation and 0.05 "
                        "is one that barely counts (drawn as a hairline at low opacity). A "
                        "measured count is a different thing: put it in --set and it shows in "
                        "the panel, while the power stays the emphasis you mean")
    p.add_argument("--weight", dest="legacy_weight", type=float, default=None,
                   help="the old name for --power, refused so that a measured count of 66 "
                        "cannot silently become a line six pixels wide")
    p.add_argument("--time", default="")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                   help="any other property on the edge (repeatable), e.g. "
                        "--set rel=co-cited")

    p = with_graph(sub.add_parser("set-node"))
    p.add_argument("--id", required=True)
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")

    p = with_graph(sub.add_parser("set-edge", help="set properties on an edge that exists"))
    p.add_argument("--from", dest="src", required=True)
    p.add_argument("--to", dest="dst", required=True)
    p.add_argument("--power", type=float, default=None,
                   help="how much this relation weighs: 1 is normal, 0.05 barely counts. Raise it "
                        "to say a relation matters more, lower it to say it is incidental")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                   help="the properties to set (repeatable)")

    p = with_graph(sub.add_parser("set-palette", help="set the colour for a node kind"))
    p.add_argument("--kind", required=True)
    p.add_argument("--color", required=True, help="#rrggbb or hsl(...)")

    p = with_graph(sub.add_parser("weigh", help="record how node importance was measured"))
    p.add_argument("--metric", default="",
                   help="what the numbers measure, in words: \"relevant papers\", \"grant "
                        "funding (USD)\". It is shown beside every weight, so a reader can tell "
                        "what a node's size is a claim about")
    p.add_argument("--mul", action="append", default=[], metavar="KIND=N",
                   help="what one unit of a node's connections is worth for that kind "
                        "(repeatable). Defaults: publication 0.1, researcher 1, "
                        "lab/institution/company 3, subject 10")
    p.add_argument("--note", default="", help="a sentence for the reader about the method")
    p.add_argument("--bake", action="store_true",
                   help="also write the result into each node's `size`, so the graph looks the "
                        "same anywhere without recomputing")
    p.add_argument("--top", type=int, default=10, help="how many nodes to list")

    p = with_graph(sub.add_parser("set-meta", help="set a top-level meta field"))
    p.add_argument("--key", required=True); p.add_argument("--value", required=True)

    p = with_graph(sub.add_parser("require", help="record what this graph needs: skills, "
                                                  "plugins, tools, its app"))
    p.add_argument("--skill", action="append", default=[])
    p.add_argument("--plugin", action="append", default=[])
    p.add_argument("--tool", action="append", default=[])
    p.add_argument("--app", help="the app that draws this graph")
    p.add_argument("--app-url", dest="app_url", help="where to fetch that app")
    p.add_argument("--remove", action="store_true", help="remove instead of add")

    p = with_graph(sub.add_parser("check", help="can this graph be shown here, and what "
                                                "is missing"))
    p.add_argument("--install", action="store_true",
                   help="fetch a missing app from the graph's app_url (asking is the consent)")
    p.add_argument("--probe-url", dest="probe_url", action="store_true",
                   help="check that the app_url is reachable (network)")

    p = with_graph(sub.add_parser("remove-node",
                                  help="delete a node and every edge touching it"))
    p.add_argument("--id", required=True, action="append")
    p.add_argument("--drop-orphan-edges-only", action="store_true",
                   help="keep the node, drop only its edges")

    p = with_graph(sub.add_parser("remove-edge", help="delete an edge by its endpoints"))
    p.add_argument("--from", dest="src", required=True)
    p.add_argument("--to", dest="dst", required=True)

    p = with_graph(sub.add_parser("validate", help="check that a graph conforms to kg/1"))
    p.add_argument("--strict", action="store_true", help="treat warnings as errors")

    p = with_graph(sub.add_parser("merge", help="fold another kg/1 graph into this one"))
    p.add_argument("--other", required=True, help="graph id or path to add")
    p.add_argument("--on-conflict", default="skip",
                   choices=["skip", "overwrite", "rename"],
                   help="what to do when a node id already exists (default: skip)")

    p = with_graph(sub.add_parser("info", help="what is in this graph — run this first"))

    p = with_graph(sub.add_parser("stats"))

    p = with_graph(sub.add_parser("render", help="template + graph -> one HTML file"))
    p.add_argument("--app", help="template to use (default: viewer.html)")
    p.add_argument("--out", help="where to write it (default: next to the graph)")

    p = sub.add_parser("shot")
    p.add_argument("--html", required=True); p.add_argument("--out", default="graph.png")
    p.add_argument("--width", type=int, default=1600)
    p.add_argument("--height", type=int, default=1000)

    p = sub.add_parser("open"); p.add_argument("--html", required=True)

    p = with_graph(sub.add_parser("serve", help="serve the graph, re-rendering on "
                                                "every change"))
    p.add_argument("--app", help="template to use (default: viewer.html)")
    p.add_argument("--out", help="what to serve (default: next to the graph)")
    p.add_argument("--port", type=int, default=8300,
                   help="port to listen on (default 8300); serve does not walk to another "
                        "port — if it is taken it says who holds it and exits")
    p.add_argument("--title", default=None)

    a = ap.parse_args()

    if a.cmd == "graphs":
        rows = workspace_graphs()
        cur = current_id()
        if a.json:
            print(json.dumps([{k: (str(v) if isinstance(v, Path) else v)
                               for k, v in r.items()} for r in rows], indent=1))
            return 0
        print(f"workspace {storage_dir()}")
        if not rows:
            print("no graphs yet.")
            print('  create one:  python3 scripts/kg.py new --id <id> --title "..."')
            return 0
        for r in rows:
            mark = "*" if r["id"] == cur else " "
            size = ("unreadable" if r.get("nodes") is None
                    else f"{r['nodes']} nodes / {r.get('edges') or 0} edges")
            print(f" {mark} {r['id']:<20} {(r['title'] or '(untitled)'):<28} {size}")
        print()
        print("  * = current.   work on one:  python3 scripts/kg.py use <id>")
        return 0

    if a.cmd == "current":
        cur = current_id()
        path = graph_file_in(graph_dir(cur)) if cur else None
        if path is None:
            print("error: no current graph set", file=sys.stderr)
            print("  list them:  python3 scripts/kg.py graphs", file=sys.stderr)
            return 1
        print(path)
        return 0

    if a.cmd == "use":
        cand = graph_file_in(graph_dir(a.id))
        if cand is None:
            print(f"error: no graph '{a.id}' in {storage_dir()}", file=sys.stderr)
            print("  list them:  python3 scripts/kg.py graphs", file=sys.stderr)
            return 2
        set_current(a.id)
        print(f"current graph is now {a.id}  ({cand})")
        return 0

    if a.cmd == "apps":
        rows = template_rows()
        if a.json:
            print(json.dumps([{k: (str(v) if isinstance(v, Path) else v)
                               for k, v in r.items()} for r in rows], indent=1))
            return 0
        print(f"templates in {assets_dir()}")
        if not rows:
            print("none — this skill ships templates, it does not build them.")
            print("  build a viewer and copy it in:  see README")
            return 0
        for r in rows:
            state = "ok" if r["ok"] else "NO #kg-graph element — cannot render"
            print(f"   {r['name']:<16} {r['bytes'] // 1024:>5} KB  {state}")
            stamp = r.get("stamp") or {}
            if stamp:
                where = stamp.get("origin") or "(origin not recorded)"
                what = stamp.get("version")
                if not what:
                    what = ("fetched " + (stamp.get("fetched_at") or "")[:10]).strip()
                print(f"   {'':<16} {'':>5}      {what} {stamp.get('commit', '')}  {where}")
            # What the app says it is for. This is a property of the app, printed by the
            # command that lists apps, so `apps` answers "which of these do I want?".
            facts = app_facts(r["name"])
            if facts.get("purpose"):
                print(f"   {'':<16} {'':>5}      {facts.get('title', '')} — {facts['purpose']}")
            needs = [n for k in ("skills", "plugins", "tools")
                     for n in ((facts.get("requires") or {}).get(k) or [])]
            if needs:
                print(f"   {'':<16} {'':>5}      needs: {', '.join(needs)}"
                      + ("" if facts.get("kinds") else "")
                      + ("   (kg.py check --graph <graph> says whether they are here)"))
        return 0

    if a.cmd == "fetch-viewer":
        return fetch_viewer(a.url, a.as_, a.force)

    if a.cmd == "suggest":
        return suggest_app(a.ask)

    if a.cmd == "fetch-app":
        return fetch_app(a.id, a.url, a.manifest_url, a.force)

    if a.cmd == "require":
        path = resolve_graph(a.graph)
        g = load(path)
        meta = g.setdefault("meta", {})
        req = meta.setdefault("requires", {})
        changed = []
        for kind, names in (("skills", a.skill), ("plugins", a.plugin), ("tools", a.tool)):
            lst = req.setdefault(kind, [])
            for n in names:
                if a.remove:
                    if n in lst:
                        lst.remove(n)
                        changed.append(f"-{kind[:-1]} {n}")
                elif n not in lst:
                    lst.append(n)
                    changed.append(f"+{kind[:-1]} {n}")
        if a.app:
            meta["app"] = a.app
            changed.append(f"app = {a.app}")
        if a.app_url:
            meta["app_url"] = a.app_url
            changed.append(f"app_url = {a.app_url}")
        if not changed:
            print("nothing changed")
            return 0
        save(g, path)
        print(f"updated {path}")
        for c in changed:
            print(f"  {c}")
        return 0

    if a.cmd == "check":
        path = resolve_graph(a.graph)
        return check_graph(load(path), path, a.install, a.probe_url)

    if a.cmd == "new":
        if a.out:
            out = Path(a.out)
            gid = None
        else:
            gid = a.id or slug(a.title)
            out = graph_target(gid)

        # Which app this graph is for. The user's own words decide when there is no --app:
        # the intention comes first, the app follows from it, and the app says the rest.
        chosen = a.app
        if not chosen and a.ask:
            apps = catalogue()
            if apps:
                chosen = sorted(apps, key=lambda x: -score_app(a.ask, x)[0])[0]["id"]
                print(f'ask       "{a.ask}"')
        facts = app_facts(chosen) if chosen else {}
        app = chosen or default_app()

        meta = {"title": a.title, "schema": SCHEMA}
        if app:
            meta["app"] = app
            url = facts.get("url") or default_app_url()
            if url:
                meta["app_url"] = url
        # The slots exist on every graph from the start: a document that can say what it
        # needs is a document that can be handed to someone else. An app fills them in.
        meta["requires"] = {k: list((facts.get("requires") or {}).get(k) or [])
                            for k in ("skills", "plugins", "tools")}
        meta["colors"] = dict(DEFAULT_COLORS)
        # A graph built to an app's conventions should not trip `stats` on the colours that
        # app asked for, so its kinds are seeded rather than left to a hash.
        for k in facts.get("kinds") or []:
            if k.get("kind") and k.get("color"):
                meta["colors"][str(k["kind"])] = str(k["color"])
        save({"meta": meta, "nodes": [], "edges": []}, out)
        if gid:
            set_current(gid)
        print(f"created {out}")
        if gid:
            print(f"current graph is now {gid}")
        if facts:
            print(f"app       {app} — {facts.get('title', '')}")
            if facts.get("purpose"):
                print(f"          {facts['purpose']}")
            missing = print_app_guide(facts)
            if missing:
                print(f"missing   {missing} required piece(s) — tell the user which, what each "
                      f"is for, and why the graph is built from them. Install nothing "
                      f"without a yes.")
        return 0

    if a.cmd == "import":
        mod = load_adapter(a.fmt)
        src = Path(a.graph).expanduser()
        if not src.is_file():
            print(f"error: no such file: {src}", file=sys.stderr)
            return 2
        g = mod.convert(src, a.title, SCHEMA, DEFAULT_COLORS)
        app = default_app()
        if app:
            g.setdefault("meta", {}).setdefault("app", app)
            url = default_app_url()
            if url:
                g["meta"].setdefault("app_url", url)
        g.setdefault("meta", {}).setdefault(
            "requires", {"skills": [], "plugins": [], "tools": []})
        if a.out:
            out = Path(a.out)
            gid = None
        else:
            gid = a.id or slug(a.title or src.stem)
            out = graph_target(gid)
        save(g, out)
        if gid:
            set_current(gid)
        print(f"imported {len(g['nodes'])} nodes / {len(g['edges'])} edges from "
              f"{src.name} ({a.fmt}) -> {out}")
        if gid:
            print(f"current graph is now {gid}")
        return 0

    if a.cmd in ("add-node", "add-edge", "set-node", "set-edge", "set-palette", "weigh", "set-meta", "stats",
                 "remove-node", "remove-edge", "validate", "merge", "info"):
        path = resolve_graph(a.graph); g = load(path)
        if a.cmd == "set-palette":
            g["meta"].setdefault("colors", {})[a.kind] = a.color
            save(g, path)
            print(f"palette[{a.kind}] = {a.color}")
            return 0
        if a.cmd == "set-edge":
            extra, bad = parse_sets(a.set)
            if bad:
                print(f"error: --set wants KEY=VALUE, got: {', '.join(bad)}", file=sys.stderr)
                return 2
            if a.power is not None:
                extra["power"] = a.power
            if not extra:
                print("error: nothing to set — pass --power and/or --set KEY=VALUE",
                      file=sys.stderr)
                return 2
            hits = [e for e in g["edges"] if e.get("from") == a.src and e.get("to") == a.dst]
            if not hits:
                print(f"error: no edge {a.src} -> {a.dst} in this graph", file=sys.stderr)
                return 2
            migrated = 0
            for e in hits:
                # `weight` on an edge used to be read as power, which is how a measured count of
                # 66 became a line six pixels wide. Once a power is stated, the old key goes.
                if a.power is not None and "weight" in e:
                    del e["weight"]
                    migrated += 1
                e.update(extra)
            save(g, path)
            print(f"updated {len(hits)} edge(s) {a.src} -> {a.dst}: "
                  f"{', '.join(f'{k}={v}' for k, v in extra.items())}")
            if migrated:
                print(f"          dropped the old `weight` on {migrated} edge(s) — it used to be "
                      f"read as power; keep a count in its own property instead")
            return 0
        if a.cmd == "weigh":
            mult, bad = parse_sets(a.mul)
            if bad:
                print(f"error: --mul wants KIND=NUMBER, got: {', '.join(bad)}", file=sys.stderr)
                return 2
            mult = {**DEFAULT_SIZE_MULTIPLIERS, **mult}
            touching: dict[str, float] = {n["id"]: 0.0 for n in g["nodes"]}
            for e in g["edges"]:
                p = edge_power(e)
                for end in (e.get("from"), e.get("to")):
                    if end in touching:
                        touching[end] += p
            scored = []
            for n in g["nodes"]:
                stated = n.get("weight")
                score = (float(stated) if isinstance(stated, (int, float))
                         else 0.5 * touching[n["id"]] * mult.get(n.get("kind", ""), 1.0))
                scored.append((score, n))
                if a.bake:
                    # `size` is a weight in the document, so store the weight that draws at the
                    # same size the score would. One meaning for `size`, computed or written.
                    n["size"] = round(max(0.0, (px_from_weight(score) - 3) / 1.6), 2)
            block: dict = {"kind_multipliers": mult}
            if a.metric:
                block["metric"] = a.metric
            if a.note:
                block["note"] = a.note
            g["meta"]["weight"] = block
            save(g, path)
            print(f"weight recorded for {len(g['nodes'])} nodes, by "
                  f"\"{a.metric or 'connections'}\"" + (" — baked into size" if a.bake else ""))
            for score, n in sorted(scored, key=lambda t: -t[0])[:max(0, a.top)]:
                print(f"  {score:9.3f}  {n.get('kind', '?'):<12} {n.get('label', n['id'])[:44]}")
            return 0
        if a.cmd == "set-meta":
            g["meta"][a.key] = a.value
            save(g, path)
            print(f"meta[{a.key}] = {a.value}")
            return 0
        if a.cmd == "add-node":
            if any(n["id"] == a.id for n in g["nodes"]):
                print(f"error: node id '{a.id}' already exists", file=sys.stderr); return 2
            extra, bad = parse_sets(a.set)
            if bad:
                print(f"error: --set wants KEY=VALUE, got: {', '.join(bad)}", file=sys.stderr)
                return 2
            n = {"id": a.id, "label": a.label, "kind": a.kind,
                 "style": a.style, "desc": a.desc, "link": a.link, **extra}
            if a.size is not None: n["size"] = a.size
            if a.level is not None: n["level"] = a.level
            if a.color: n["color"] = a.color
            g["nodes"].append(n); save(g, path)
            print(f"added node {a.id} ({a.kind}) -> {len(g['nodes'])} nodes")
            if extra:
                print(f"          with {', '.join(sorted(extra))} — its own row in the panel")
            return 0
        if a.cmd == "add-edge":
            if a.legacy_weight is not None:
                print("error: --weight is the old name for an edge's strength and is no longer "
                      "read: a count of 66 used to become a line six pixels wide.\n"
                      "       Use --power for emphasis (1 is a normal relation, 0.05 is a "
                      "hairline) and --set count=66 to keep the measured number.", file=sys.stderr)
                return 2
            extra, bad = parse_sets(a.set)
            if bad:
                print(f"error: --set wants KEY=VALUE, got: {', '.join(bad)}", file=sys.stderr)
                return 2
            e = {"from": a.src, "to": a.dst, **extra}
            # Only what was meant: an empty label or an absent direction is not a property, and
            # a document full of defaults nobody chose is a document nobody can read.
            if a.label:
                e["label"] = a.label
            if a.dir and a.dir != "none":
                e["dir"] = a.dir
            if a.time:
                e["time"] = a.time
            # Written explicitly, and only when it is not the default: an edge of power 1 in the
            # document says nothing.
            if a.power != 1:
                e["power"] = a.power
            g["edges"].append(e)
            save(g, path)
            print(f"added edge {a.src} -> {a.dst} -> {len(g['edges'])} edges"); return 0
        if a.cmd == "remove-node":
            targets = set(a.id)
            present = {n["id"] for n in g["nodes"]}
            unknown = targets - present
            if unknown:
                print(f"error: no such node id(s): {sorted(unknown)}", file=sys.stderr); return 2
            if a.drop_orphan_edges_only:
                before = len(g["edges"])
                g["edges"] = [e for e in g["edges"]
                              if e.get("from") not in targets and e.get("to") not in targets]
                save(g, path)
                print(f"dropped {before - len(g['edges'])} edge(s) touching {sorted(targets)}; "
                      f"nodes kept")
                return 0
            before_n, before_e = len(g["nodes"]), len(g["edges"])
            g["nodes"] = [n for n in g["nodes"] if n["id"] not in targets]
            g["edges"] = [e for e in g["edges"]
                          if e.get("from") not in targets and e.get("to") not in targets]
            save(g, path)
            print(f"removed {before_n - len(g['nodes'])} node(s) and "
                  f"{before_e - len(g['edges'])} edge(s) -> {len(g['nodes'])} nodes / "
                  f"{len(g['edges'])} edges")
            return 0
        if a.cmd == "remove-edge":
            before = len(g["edges"])
            g["edges"] = [e for e in g["edges"]
                          if not (e.get("from") == a.src and e.get("to") == a.dst)]
            if len(g["edges"]) == before:
                print(f"error: no edge {a.src} -> {a.dst}", file=sys.stderr); return 2
            save(g, path)
            print(f"removed edge {a.src} -> {a.dst} -> {len(g['edges'])} edges")
            return 0
        if a.cmd == "validate":
            r = conform(g)
            # The graph names the app that draws it; if that app is not here, `render`
            # will fail later and the reader deserves to hear it from `validate` now.
            app = (g.get("meta") or {}).get("app")
            if app and not (assets_dir() / f"{app}.html").exists():
                url = (g.get("meta") or {}).get("app_url")
                how = (f"fetch it: kg.py fetch-viewer --url {url}"
                       if url else "see assets/README.md")
                r["warnings"].append(f"meta.app names '{app}' but assets/{app}.html is not "
                                     f"here — render will fail; {how}")
            # Findings are aggregated at the source: a 1000-node graph would otherwise
            # emit one line per edge, and a wall of output is indistinguishable from
            # no check at all.
            for e in r["errors"]:
                print(f"error:   {e}")
            for w in r["warnings"]:
                print(f"warning: {w}")
            for m in r["info"]:
                print(f"note:    {m}")
            bad = len(r["errors"]) + (len(r["warnings"]) if a.strict else 0)
            if bad:
                print(f"NOT CONFORMANT — {len(r['errors'])} error(s), "
                      f"{len(r['warnings'])} warning(s)")
                return 1
            print(f"conformant — {len(g['nodes'])} nodes / {len(g['edges'])} edges, "
                  f"schema {g['meta'].get('schema')}")
            return 0
        if a.cmd == "merge":
            other_path = resolve_graph(a.other)
            other = load(other_path)
            have = {n["id"] for n in g["nodes"]}
            added = skipped = renamed = 0
            idmap = {}
            for n in other["nodes"]:
                nid = n["id"]
                if nid in have:
                    if a.on_conflict == "skip":
                        idmap[nid] = None
                        skipped += 1
                        continue
                    if a.on_conflict == "overwrite":
                        g["nodes"] = [x for x in g["nodes"] if x["id"] != nid]
                        idmap[nid] = nid
                    else:  # rename
                        new = nid
                        while new in have:
                            new += "_m"
                        idmap[nid] = new
                        n = dict(n, id=new, desc=(n.get("desc", "") +
                                                  f"\n(merged from {other_path})"))
                        renamed += 1
                else:
                    idmap[nid] = nid
                g["nodes"].append(n)
                have.add(n["id"])
                added += 1
            e_added = 0
            for e in other["edges"]:
                s, d = idmap.get(e.get("from")), idmap.get(e.get("to"))
                if s is None or d is None:
                    continue
                g["edges"].append(dict(e, **{"from": s, "to": d}))
                e_added += 1
            save(g, path)
            print(f"merged {other_path}: +{added} node(s) ({renamed} renamed, {skipped} "
                  f"skipped), +{e_added} edge(s) -> {len(g['nodes'])} nodes / "
                  f"{len(g['edges'])} edges")
            return 0
        if a.cmd == "set-node":
            extra, bad = parse_sets(a.set)
            if bad:
                print(f"error: --set wants KEY=VALUE, got: {', '.join(bad)}", file=sys.stderr)
                return 2
            for n in g["nodes"]:
                if n["id"] == a.id:
                    n.update(extra)
                    save(g, path); print(f"updated {a.id}: {a.set}")
                    return 0
            print(f"error: no node '{a.id}'", file=sys.stderr); return 2
        if a.cmd == "info":
            # The first command an unknown agent should run on an unfamiliar graph.
            # Answers "what am I looking at?" in one screen, no JSON reading required.
            r = conform(g)
            m = g["meta"]
            kinds = {}
            for n in g["nodes"]:
                kinds[n.get("kind") or "(none)"] = kinds.get(n.get("kind") or "(none)", 0) + 1
            print(f"graph     {path}")
            print(f"title     {m.get('title') or '(untitled)'}")
            print(f"schema    {m.get('schema')}")
            app = m.get("app")
            if app:
                have = (assets_dir() / f"{app}.html").exists()
                print(f"viewer    {app}" + ("" if have else
                                            "   (no such template — render will fail; "
                                            "see assets/README.md)"))
            req = m.get("requires") or {}
            bits = [f"{k[:-1]} {n}" for k in ("skills", "plugins", "tools")
                    for n in (req.get(k) or [])]
            if bits:
                print(f"requires  {', '.join(bits)}")
            if m.get("imported_from"):
                print(f"imported  {m['imported_from']}")
            if m.get("imported_at"):
                print(f"          {m['imported_at']}")
            print(f"size      {len(g['nodes'])} nodes / {len(g['edges'])} edges")
            print("kinds     " + ", ".join(f"{k} ({v})" for k, v in
                                           sorted(kinds.items(), key=lambda kv: -kv[1])))
            nparent = sum(1 for n in g["nodes"] if n.get("parent"))
            if nparent:
                print(f"tree      {nparent} node(s) carry a parent — it groups into panels")
            nl = sum(1 for e in g["edges"] if (e.get("label") or "").strip())
            print(f"edges     {nl} of {len(g['edges'])} carry a label")
            print(f"health    {len(r['errors'])} error(s), {len(r['warnings'])} warning(s)")
            if r["errors"]:
                for e in r["errors"]:
                    print(f"  error   {e}")
            print()
            print("next      python3 scripts/kg.py render --graph " f"{path}")
            print(f"          python3 scripts/kg.py serve  --graph {path}")
            return 1 if r["errors"] else 0

        if a.cmd == "stats":
            from collections import Counter
            kinds = Counter(n.get("kind", "?") for n in g["nodes"])
            styles = Counter(n.get("style", "solid") for n in g["nodes"])
            lv = sorted({n["level"] for n in g["nodes"] if n.get("level") is not None})
            placed = sum(1 for n in g["nodes"] if n.get("x") is not None)
            print(f"title       : {g['meta'].get('title')}")
            print(f"nodes/edges : {len(g['nodes'])} / {len(g['edges'])}")
            print(f"kinds       : {dict(kinds)}")
            print(f"styles      : {dict(styles)}")
            print(f"levels      : {lv if lv else '(none - layout will be computed)'}")
            print(f"positioned  : {placed}/{len(g['nodes'])} have authored x,y")
            orphan = [n["id"] for n in g["nodes"]
                      if not any(e["from"] == n["id"] or e["to"] == n["id"] for e in g["edges"])]
            print(f"isolated    : {len(orphan)} nodes have no edges" +
                  (f" ({', '.join(orphan[:6])}{'…' if len(orphan) > 6 else ''})" if orphan else ""))
            known = set(g["meta"].get("colors") or {})
            custom = sorted({str(n.get("kind", "")) for n in g["nodes"]} - known) if known else []
            if custom:
                print(f"no palette  : {custom} — these get a hashed colour; add them to "
                      f"meta.colors for control")
            return 0

    if a.cmd == "render":
        path = resolve_graph(a.graph)
        g = load(path)
        out = render(g, Path(a.out) if a.out else default_out(path), a.app)
        print(f"rendered {len(g['nodes'])} nodes / {len(g['edges'])} edges -> {out}")
        print(f"  {file_url(out)}")
        return 0

    if a.cmd == "shot":
        chrome = find_chrome()
        if not chrome:
            print("error: no Chrome/Chromium found for headless screenshot", file=sys.stderr)
            return 3
        html = Path(a.html).resolve()
        out = Path(a.out).resolve()
        # Software WebGL, named explicitly. Headless Chrome will not give a page a GPU
        # context, and the `--disable-gpu` that used to be here made sigma throw inside its
        # constructor: every screenshot came out a flat dark rectangle, which reads as "the
        # graph is broken" when it is the screenshot that is broken.
        cmd = [chrome, "--headless=new", "--hide-scrollbars",
               "--force-device-scale-factor=1",
               "--enable-unsafe-swiftshader", "--use-gl=angle", "--use-angle=swiftshader",
               "--virtual-time-budget=8000",
               f"--window-size={a.width},{a.height}",
               f"--screenshot={out}", f"file://{html}"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if not out.exists():
            print(f"error: screenshot failed\n{r.stderr[:400]}", file=sys.stderr); return 3
        size = out.stat().st_size
        print(f"screenshot {out} ({size // 1024} KB)")
        # A blank page of this size compresses to a few KB. Saying so is the difference
        # between an agent checking its own work and an agent reporting an empty graph.
        if size < 12_000 and a.width * a.height >= 200_000:
            print("  warning: that is small enough to be a flat page — the renderer probably "
                  "did not start rather than the graph being empty", file=sys.stderr)
        return 0

    if a.cmd == "open":
        # The path that works when no server can bind (sandboxed agents). Prints a
        # file:// URL — clickable, unlike a bare path — and tries to launch it.
        p = Path(a.html).resolve()
        if not p.exists():
            print(f"error: no such file: {p}", file=sys.stderr)
            print("  render one first:  python3 scripts/kg.py render --graph <id>",
                  file=sys.stderr)
            return 2
        print(file_url(p))
        if sys.platform == "darwin":
            subprocess.run(["open", str(p)], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", str(p)], check=False)
        else:
            subprocess.run(["start", str(p)], shell=True, check=False)
        return 0

    if a.cmd == "serve":
        # Serve the graph AND its JSON, re-rendering on every request so that a
        # re-run of the build commands is visible on browser refresh.
        import http.server
        import socketserver

        graph = resolve_graph(a.graph).resolve()
        out = (Path(a.out) if a.out else default_out(graph)).resolve()
        if not graph.exists():
            print(f"error: no such graph: {graph}", file=sys.stderr)
            print("  create one first:  kg.py new --out <path> --title \"...\"", file=sys.stderr)
            return 2
        out.parent.mkdir(parents=True, exist_ok=True)
        title = a.title
        last = {"mtime": None}

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kw):
                super().__init__(*args, directory=str(out.parent), **kw)

            def log_message(self, fmt, *args):  # keep the console readable
                sys.stderr.write("  %s\n" % (fmt % args))

            def end_headers(self):
                # Without this the browser can serve a cached page and the user reports
                # "it doesn't work" while the server is fine. There is no reason to cache
                # a page whose whole purpose is to re-render on refresh.
                self.send_header("Cache-Control", "no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                super().end_headers()

            def _fresh(self) -> bool:
                try:
                    m = graph.stat().st_mtime
                except FileNotFoundError:
                    return False
                if last["mtime"] is None or m != last["mtime"]:
                    last["mtime"] = m
                    g = load(graph)
                    if title:
                        g.setdefault("meta", {})["title"] = title
                    render(g, out, a.app)
                    return True
                return False

            def do_GET(self):
                self._fresh()
                super().do_GET()

            def do_HEAD(self):
                self._fresh()
                super().do_HEAD()

        # render once so the first visit is not empty
        g = load(graph)
        if title:
            g.setdefault("meta", {})["title"] = title
        render(g, out, a.app)

        # Bind. Be honest about WHY it failed: a sandbox that blocks bind() makes every
        # port fail, and calling that "port busy" sends the agent hunting for a free port
        # forever. Observed: codex tried 8300-8319, 8350-8369, 8400-8419 and 12345-12364
        # while nothing was listening on any of them.
        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        # Bind exactly the port asked for, and refuse rather than walking forward. Walking is
        # how two servers end up alive while the URL in the user's chat points at the first
        # one, and how "the server is temperamental" gets said about a tool that was fine. A
        # URL handed to a human has to keep meaning what it meant when it was handed over.
        port = a.port
        httpd = None
        first_err = None
        try:
            httpd = Server(("127.0.0.1", port), Handler)
        except OSError as e:
            first_err = e

        if httpd is None:
            # Careful with errno: 48 is EADDRINUSE on macOS but EADDRNOTAVAIL on Linux. The
            # old code listed 48 as a permission failure, so a busy port on a Mac was reported
            # as a sandbox restriction and the agent went hunting for ports.
            err = getattr(first_err, "errno", None)
            busy = err == 98 or (err == 48 and sys.platform == "darwin")
            print(f"error: could not listen on {port}: {first_err}", file=sys.stderr)
            print("", file=sys.stderr)
            if busy:
                holder = ""
                try:
                    r = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
                                       capture_output=True, text=True, timeout=5)
                    rows = [ln.split() for ln in r.stdout.strip().splitlines()[1:] if ln.strip()]
                    if rows:
                        holder = f" — {rows[0][0]}, pid {rows[0][1]}"
                except Exception:
                    pass
                print(f"  Port {port} is already in use{holder}. Something is probably serving",
                      file=sys.stderr)
                print("  this graph already. Probe it before starting a second server:",
                      file=sys.stderr)
                print(f"    http://localhost:{port}/{out.name}", file=sys.stderr)
                print(f"  Or ask for a different port:  --port {port + 1}", file=sys.stderr)
            elif err in (1, 13, 49):
                print("  This is a PERMISSION failure, not a busy port. A sandbox that", file=sys.stderr)
                print("  forbids binding sockets fails every port the same way — moving to", file=sys.stderr)
                print("  another port will not help. Serve it from a terminal outside the", file=sys.stderr)
                print("  sandbox, or hand over the page instead:", file=sys.stderr)
            else:
                print("  Not a busy port and not a permission failure — read the errno above.", file=sys.stderr)
            print(f"    python3 scripts/kg.py render --graph {graph} --out {out}", file=sys.stderr)
            print(f"    python3 scripts/kg.py open   --html {out}", file=sys.stderr)
            return 2

        url = f"http://localhost:{port}/{out.name}"
        print(f"serving {out.parent}")
        print(f"re-rendering from {graph.name} on every change — refresh to see it")
        print()
        print(f"    {url}")
        print()
        print("Ctrl-C to stop")
        try:
            with httpd:
                httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
