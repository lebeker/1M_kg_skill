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
  declare         declare a relation: its direction, the kinds it may join, its look
  history         what changed in a graph, one line per command that changed it
  undo            put a graph back to an earlier version
  validate        check conformance to kg/1
  merge           fold another kg/1 graph into this one
  info            what is in this graph — run this first
  stats           textual summary (what the graph contains)
  check           can this graph be shown here? what is missing, and install it
  apps            list the bundled viewers (templates)
  fetch-app       install an app from the catalogue: viewer + its own declaration
  fetch-viewer    download a viewer into assets/ — no node, no bun, no build
  render          write a standalone HTML from a template + the graph
  open            open the HTML in the real browser (for the human)

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
  assets/viewer.html is the one that ships; `render` substitutes the graph into
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
# Two numbers, and they are a request, not a promise: what a document can afford to have drawn at
# once. The page decides how to respect them on the host it actually runs on — and a reader (or a
# measurement) may rewrite them later. Writing a graph never stops because of them.
DEFAULT_LIMITS = {"nodes": 500, "edges": 5000}
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


# --------------------------------------------------------- what a relation looks like
#
# A relation's appearance is data, not a code change. `style` is a space-separated list of words:
# the stroke (`solid`, `dashed`, `dotted`) and/or the shape (`arrow`, `double`, `clamped`,
# `rectangle`, `triangle`), so `"dotted arrow"` is a style and reads the way somebody would say
# it. `color`, `dash` (an explicit pattern like "6 4") and `width` are the other knobs, and
# `power` remains the emphasis. The viewer reads this same vocabulary; keep the two in step:
# webapp/src/kg.ts, EDGE_STROKES / EDGE_SHAPES / edgeDash / edgeShape.
EDGE_STROKES = ("solid", "dashed", "dotted")
EDGE_SHAPES = ("arrow", "double", "clamped", "rectangle", "triangle")
EDGE_WORDS = EDGE_STROKES + EDGE_SHAPES
EDGE_DIRS = ("in", "out", "both", "none")


# ------------------------------------------------------- nodes that must say what they are
#
# A publication can stand alone: a title, a DOI, a count. A *body* cannot. A concept, a lab, a
# company is in the graph because it means something for this subject, and a body with no
# description is the difference between a map and a scatter of dots. The kinds below must be
# described when they are created; `review` then shows which descriptions have gone stale as the
# graph grew around them, which is the work of keeping a field survey honest.
NEEDS_DESC = ("subject", "concept", "lab", "institution", "company")


# ------------------------------------------------------------------ loading

def load(path: Path) -> dict:
    if path.is_dir():
        doc = graph_file_in(path)
        if doc is None:
            raise SystemExit(f"error: {path} is a folder with no graph document in it.\n"
                             f"  a graph folder holds graph.json or its one .json file")
        path = doc
    if not path.exists():
        return {"meta": {"title": path.stem, "schema": SCHEMA, "colors": dict(DEFAULT_COLORS),
                          "limits": dict(DEFAULT_LIMITS)},
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
    autocommit(path)


# ------------------------------------------------------------------ history
#
# A graph is a file, and a file that changes without a record of what changed is a file nobody
# can trust. Every write goes through `save`, so every write can be committed: one commit per
# command, the command line as the message. Nothing here is required — no git, no history, the
# engine still works — and nothing leaves the machine.

LAST_CMD = ""


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True)


def repo_root_for(path: Path) -> Path | None:
    """The nearest folder above this graph that already is a repository, if any."""
    for parent in [path.parent, *path.parents]:
        if (parent / ".git").exists():
            return parent
    return None


def autocommit(path: Path, note: str | None = None) -> None:
    """
    Record one change. Best effort by design: a machine without git, or a workspace the reader
    asked to leave alone (`KG_NO_GIT=1`), is a normal machine, not an error.

    Only the graph's own folder is staged, so a workspace that happens to sit inside someone's
    notes repository does not get their unrelated edits swept into a commit.
    """
    if os.environ.get("KG_NO_GIT") or not shutil.which("git"):
        return
    root = repo_root_for(path)
    if root is None:
        root = workspace_root()
        _git(root, "init", "-q")
    folder = path.parent
    try:
        rel = folder.relative_to(root)
    except ValueError:
        return
    _git(root, "add", "-A", "--", str(rel))
    if not _git(root, "diff", "--cached", "--quiet", "--", str(rel)).returncode:
        return  # nothing changed
    msg = note or LAST_CMD or f"update {path.parent.name}"
    _git(root, "commit", "-q", "-m", msg, "--", str(rel))


def graph_history(path: Path, limit: int = 12) -> list[str]:
    root = repo_root_for(path)
    if root is None or not shutil.which("git"):
        return []
    rel = path.parent.relative_to(root)
    out = _git(root, "log", f"-n{limit}", "--format=%h  %ad  %s", "--date=short", "--", str(rel))
    return [line for line in out.stdout.splitlines() if line.strip()]


def graph_undo(path: Path, steps: int = 1) -> tuple[bool, str]:
    """Put the graph back to how it was `steps` changes ago. The undo is itself a change."""
    root = repo_root_for(path)
    if root is None or not shutil.which("git"):
        return False, "no git repository here (or no git installed) — nothing to undo against"
    rel = path.parent.relative_to(root)
    out = _git(root, "log", "--format=%H", "--", str(rel))
    commits = [line.strip() for line in out.stdout.splitlines() if line.strip()]
    if len(commits) <= steps:
        return False, f"only {len(commits)} change(s) recorded for this graph"
    target = commits[steps]
    show = _git(root, "show", f"{target}:{rel / 'graph.json'}")
    if show.returncode != 0:
        return False, f"could not read that version: {show.stderr.strip().splitlines()[:1]}"
    path.write_text(show.stdout)
    autocommit(path, f"undo {steps} change(s) of {path.parent.name}")
    return True, target[:7]


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

    # --- how connected each node is: used by the drift check, and by the summary below
    deg_now = {}
    for e in edges:
        deg_now[e.get("from")] = deg_now.get(e.get("from"), 0) + 1
        deg_now[e.get("to")] = deg_now.get(e.get("to"), 0) + 1
    deg = deg_now

    # --- what each relation says it looks like, against what the viewer can draw
    unknown_style, style_count = {}, 0
    for e in edges:
        words = str(e.get("style") or "").lower().replace(",", " ").split()
        if not words:
            continue
        style_count += 1
        for w in words:
            if w not in EDGE_WORDS:
                unknown_style.setdefault(w, 0)
                unknown_style[w] += 1
    if unknown_style:
        warnings.append(
            "edge style word(s) the renderer does not know: "
            + ", ".join(f"{w!r} ({n}x)" for w, n in sorted(unknown_style.items()))
            + f" — known: {', '.join(EDGE_WORDS)}. An unknown word is ignored (the edge draws "
              "solid), which is a silent loss of meaning.")

    # --- a relation whose label contradicts its own strength
    weak_words = ("co-cit", "cocit", "co cit", "cited together")
    loud = []
    for e in edges:
        label = str(e.get("label") or "").lower()
        if any(w in label for w in weak_words) and edge_power(e) > 0.1:
            loud.append(f"{e.get('from')}->{e.get('to')}")
    if loud:
        warnings.append(f"{len(loud)} edge(s) are labelled a co-citation but carry power > 0.1 "
                        f"({', '.join(loud[:4])}{'…' if len(loud) > 4 else ''}) — co-citation is "
                        "texture, not structure: --power 0.05 --style dashed, with the count in "
                        "--set cocited=N")

    # --- bodies without a description. A map of a field is read through these sentences.
    thin = [n.get("id") for n in nodes
            if n.get("kind") in NEEDS_DESC and not (n.get("desc") or "").strip()]
    if thin:
        warnings.append(f"{len(thin)} {('/'.join(NEEDS_DESC))} node(s) have no description "
                        f"({', '.join(str(x) for x in thin[:5])}"
                        f"{'…' if len(thin) > 5 else ''}) — a body with no description is a dot "
                        "with a name")

    # --- descriptions written before the graph grew around them: the nodes that have taken on
    # connections since their sentence was written are the ones whose sentence may be wrong now.
    stale = []
    for n in nodes:
        rev = n.get("desc_rev")
        if not isinstance(rev, int) or not (n.get("desc") or "").strip():
            continue
        if deg_now.get(n.get("id"), 0) > rev:
            stale.append(n.get("id"))
    if stale:
        info.append(f"{len(stale)} node(s) gained connections after their description was "
                    f"written ({', '.join(str(x) for x in stale[:4])}"
                    f"{'…' if len(stale) > 4 else ''}) — worth re-reading: "
                    "python3 scripts/kg.py review --graph <id>")

    # --- structure an agent should know before editing
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
# The notes element. A template without it simply has no notes panel; nothing fails.
DOCS_ELEMENT_RE = re.compile(
    r"(<script[^>]*\bid=[\"\']kg-docs[\"\'][^>]*>)(.*?)(</script>)", re.S)

DOCS_DIRNAME = "docs"
DOCS_OVERVIEW = "overview.md"


def docs_dir_for(graph: Path) -> Path:
    """Where a graph's notes live: a `docs/` folder beside the document.

    One subject is one folder, and the notes belong to the subject, not to the viewer and not to
    the agent that happened to write them. This is also the `docs/` an OKF-shaped workspace
    already looks for, so the folder is where a reader would expect to find it.
    """
    return graph.resolve().parent / DOCS_DIRNAME


def collect_docs(graph: Path) -> dict:
    """Every note in the graph's docs/, keyed by the path a node refers to it by."""
    out = {}
    d = docs_dir_for(graph)
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.md")):
        try:
            out[f"{DOCS_DIRNAME}/{f.name}"] = f.read_text()
        except OSError:
            continue
    return out


def inject_docs(html: str, docs: dict) -> str:
    """Put the notes into the template's notes element, the same way the graph goes in.

    They are inlined rather than linked because the page is opened from `file://`, where a
    browser will not read a file sitting next to it — the same reason the graph is inlined.
    """
    if not docs:
        return html
    m = DOCS_ELEMENT_RE.search(html)
    if not m:
        return html
    payload = json.dumps(docs, separators=(",", ":")).replace("</script>", "<\\/script>")
    return html[:m.start(2)] + payload + html[m.end(2):]


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


def render(g: dict, out: Path, app: str | None = None, source: Path | None = None) -> Path:
    """A template plus the graph, written as one self-contained HTML file.

    Which template, in order: `--app`, then the graph's own `meta.app`, then the shipped
    `viewer.html`. The graph naming its viewer is the interface — the same JSON can be
    rendered by a different app on a different machine without editing anything.

    `source` is where the document came from, which is also where its notes are: the `docs/`
    folder beside it travels into the page, so the page stays a file you can hand over.
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
    docs = collect_docs(source) if source else {}
    html = inject_docs(html, docs)
    title = (g.get("meta") or {}).get("title") or "knowledge graph"
    html = re.sub(r"<title>.*?</title>", f"<title>{html_escape(title)}</title>",
                  html, count=1, flags=re.S)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    return out


# -------------------------------------------------------------------- main

def main() -> int:
    global LAST_CMD
    LAST_CMD = "kg " + " ".join(sys.argv[1:4])
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
    p.add_argument("--rel",
                   help="a relation declared with `declare`: the label, its direction, its look, "
                        "and a check that both ends are of the kinds it may join")
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
    p.add_argument("--style", default="",
                   help="how the relation is drawn: a stroke ('solid', 'dashed', 'dotted') "
                        "and/or a shape ('arrow', 'double', 'clamped', 'rectangle', "
                        "'triangle'), space-separated. Example: --style \"dashed\" for a "
                        "co-citation, --style \"arrow\" for a citation")
    p.add_argument("--color", help="this edge's own colour, e.g. '#8fa3c8'")
    p.add_argument("--dash", help="an explicit dash pattern instead of a named stroke, "
                                  "e.g. \"6 4\"")
    p.add_argument("--width", type=float,
                   help="an explicit line width in px, when `power` is not the right control")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                   help="any other property on the edge (repeatable), e.g. "
                        "--set rel=co-cited")

    p = with_graph(sub.add_parser("set-node"))
    p.add_argument("--id", required=True)
    p.add_argument("--desc", default=None,
                   help="rewrite the node's description. Re-dating it is the point: the engine "
                        "records how many connections it was written against, so `review` can "
                        "say later which sentences the graph has grown past")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    p.add_argument("--unset", action="append", default=[], metavar="KEY",
                   help="drop a property: what a document was made to carry by mistake "
                        "has to be removable, or the mistake is permanent")

    p = with_graph(sub.add_parser("set-edge", help="set properties on an edge that exists"))
    p.add_argument("--from", dest="src", required=True)
    p.add_argument("--to", dest="dst", required=True)
    p.add_argument("--power", type=float, default=None,
                   help="how much this relation weighs: 1 is normal, 0.05 barely counts. Raise it "
                        "to say a relation matters more, lower it to say it is incidental")
    p.add_argument("--style", default=None,
                   help="how this relation is drawn — see add-edge. Pass an empty string to "
                        "take the style off an edge")
    p.add_argument("--color", default=None, help="this edge's own colour")
    p.add_argument("--dash", default=None, help="an explicit dash pattern, e.g. '6 4'")
    p.add_argument("--width", type=float, default=None, help="an explicit width in px")
    p.add_argument("--label", default=None, help="the relation's words")
    p.add_argument("--dir", default=None, choices=["none", "in", "out", "both"],
                   help="which way it points")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                   help="the properties to set (repeatable)")
    p.add_argument("--unset", action="append", default=[], metavar="KEY",
                   help="drop a property: what a document was made to carry by mistake "
                        "has to be removable, or the mistake is permanent")

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

    p = with_graph(sub.add_parser("note", help="write the long form of a description, as a "
                                                 "markdown file in the graph's docs/"))
    p.add_argument("--node", help="the node this note is about (omit for the subject's "
                                  "overview note)")
    p.add_argument("--file", help="file name inside docs/ (default: the node's slug, or "
                                  "overview.md)")
    p.add_argument("--title", help="the note's heading")
    p.add_argument("--text", default="", help="write this instead of the skeleton")
    p.add_argument("--list", action="store_true", help="list the notes and what points at them")

    p = with_graph(sub.add_parser("review", help="the work list for a field survey: which bodies "
                                                 "need a description, and which have gone stale"))
    p.add_argument("--top", type=int, default=20, help="how many rows to list")

    p = with_graph(sub.add_parser("visuals", help="how this graph wants to look: arrows, width, "
                                                  "scale, rings"))
    p.add_argument("--arrows", choices=["on", "off"],
                   help="does a directed relation get a head by default? The app's default is "
                        "off; a citation map usually wants it on")
    p.add_argument("--halo", choices=["on", "off"],
                   help="draw a ring around a node that has nodes collapsed inside it")
    p.add_argument("--edge-width", dest="edge_width", type=float,
                   help="multiply every relation's width")
    p.add_argument("--node-scale", dest="node_scale", type=float)
    p.add_argument("--show", action="store_true", help="print what is recorded, then any change")

    p = with_graph(sub.add_parser("limits", help="how much of this graph should be drawn at once "
                                                  "(two numbers; the page decides how to respect them)"))
    p.add_argument("--nodes", type=int, help="nodes the page should draw before grouping")
    p.add_argument("--edges", type=int, help="edges the page should draw before grouping")

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

    p = with_graph(sub.add_parser("history", help="what changed in this graph, newest first"))
    p.add_argument("--limit", type=int, default=12)

    p = with_graph(sub.add_parser("undo", help="put this graph back to an earlier version"))
    p.add_argument("--steps", type=int, default=1,
                   help="how many recorded changes back (default 1 = the state before the last one)")

    p = with_graph(sub.add_parser(
        "declare",
        help="declare a relation: does it point, and which kinds may it join"))
    p.add_argument("--edge", required=True, help="the relation word, e.g. cite, part-of")
    p.add_argument("--dir", default="none", choices=["none", "in", "out", "both"])
    p.add_argument("--from", dest="src_kinds", default="",
                   help="kinds allowed at the tail, comma-separated (empty = any kind)")
    p.add_argument("--to", dest="dst_kinds", default="",
                   help="kinds allowed at the head, comma-separated (empty = any kind)")
    p.add_argument("--color", help="the colour this relation is drawn in when an edge has none")
    p.add_argument("--style", help="the stroke this relation is drawn in when an edge has none")
    p.add_argument("--power", type=float,
                   help="the power this relation takes when an edge does not set one")

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

    p = sub.add_parser("open"); p.add_argument("--html", required=True)

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

        meta = {"title": a.title, "schema": SCHEMA, "limits": dict(DEFAULT_LIMITS)}
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
                 "remove-node", "remove-edge", "validate", "merge", "info",
                 "history", "undo", "declare", "limits"):
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
            if a.style is not None:
                style = a.style.strip().lower()
                weird = [w for w in style.replace(",", " ").split() if w not in EDGE_WORDS]
                if weird:
                    print(f"error: unknown style word(s) {weird} — known: "
                          f"{', '.join(EDGE_WORDS)}", file=sys.stderr)
                    return 2
                # An empty style means "no style", which is a real instruction: take the word
                # off the edge rather than storing the empty string.
                extra["style"] = style
            for flag, key in ((a.color, "color"), (a.dash, "dash"),
                              (a.width, "width"), (a.label, "label")):
                if flag is not None:
                    extra[key] = flag
            if a.dir is not None and a.dir != "none":
                extra["dir"] = a.dir
            if not extra and not a.unset:
                print("error: nothing to set — pass --power, --style, --color, --dash, --width, "
                      "--label, --dir, --set KEY=VALUE and/or --unset KEY", file=sys.stderr)
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
                for k in a.unset:
                    e.pop(k, None)
                e.update(extra)
            save(g, path)
            said = ", ".join(f"{k}={v}" for k, v in extra.items())
            if a.unset:
                said += (", " if said else "") + "dropped " + ", ".join(a.unset)
            print(f"updated {len(hits)} edge(s) {a.src} -> {a.dst}: {said}")
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
            # A body without a description is a dot with a name. Publications are exempt — they
            # carry their own identity in a title and a DOI — and so is anything the app has
            # never heard of. The four kinds below are the ones a reader is meant to *read*.
            desc = (a.desc or "").strip() or str(extra.get("desc") or "").strip()
            if a.kind in NEEDS_DESC and not desc:
                print(f"error: a {a.kind} needs a description — one sentence saying what it is "
                      f"and why it matters for this subject.\n"
                      f"       --desc \"...\"  (the long form goes in a note: kg.py note "
                      f"--graph <id> --node {a.id})", file=sys.stderr)
                return 2
            n = {"id": a.id, "label": a.label, "kind": a.kind,
                 "style": a.style, "desc": desc, "link": a.link, **extra}
            if a.size is not None: n["size"] = a.size
            if a.level is not None: n["level"] = a.level
            if a.color: n["color"] = a.color
            if desc:
                # What the description was written against. When the graph grows around this
                # node, `review` can say which sentences have not been re-read since.
                n["desc_rev"] = 0
            g["nodes"].append(n); save(g, path)
            print(f"added node {a.id} ({a.kind}) -> {len(g['nodes'])} nodes")
            if desc:
                print(f"          described: \"{desc[:70]}{'…' if len(desc) > 70 else ''}\"")
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
            style = (a.style or "").strip().lower()
            weird = [w for w in style.replace(",", " ").split() if w not in EDGE_WORDS]
            if weird:
                print(f"error: unknown style word(s) {weird} — the renderer knows: "
                      f"{', '.join(EDGE_WORDS)}.\n"
                      f"       A word it does not know is ignored, which is a silent loss of "
                      f"meaning, so this is refused rather than stored.", file=sys.stderr)
                return 2
            rel_name = (a.rel or "").strip()
            decl = None
            if rel_name:
                declared = (g.get("meta") or {}).get("edges") or []
                decl = next((d for d in declared if d.get("name") == rel_name), None)
                if decl is None:
                    print(f"error: no relation is declared as '{rel_name}'.\n"
                          f"       Declare it first, so its direction and its ends are a "
                          f"decision and not a guess:\n"
                          f"       python3 scripts/kg.py declare --graph {a.graph or '<id>'} "
                          f"--edge {rel_name} --dir out --from paper --to paper",
                          file=sys.stderr)
                    return 2
                kinds = {n["id"]: (n.get("kind") or "") for n in g["nodes"]}
                got = (kinds.get(a.src, ""), kinds.get(a.dst, ""))
                want = (decl.get("from") or [], decl.get("to") or [])
                ok = (not want[0] or got[0] in want[0]) and (not want[1] or got[1] in want[1])
                if not ok and decl.get("dir") == "in":
                    got = got[::-1]
                    ok = (not want[0] or got[0] in want[0]) and (not want[1] or got[1] in want[1])
                if not ok:
                    print(f"error: '{rel_name}' joins {want[0] or ['any']} -> {want[1] or ['any']}, "
                          f"but this edge is {got[0] or '?'} -> {got[1] or '?'}.\n"
                          f"       A relation with the wrong ends is a different relation: "
                          f"declare another one, or fix the edge.", file=sys.stderr)
                    return 2
                # The relation's look is decided once, in the declaration.
                if not a.color and decl.get("color"):
                    a.color = decl["color"]
                if not style and decl.get("style"):
                    style = str(decl["style"]).lower()
                if a.power == 1 and decl.get("power") is not None:
                    a.power = float(decl["power"])
            e = {"from": a.src, "to": a.dst, **extra}
            # Only what was meant: an empty label or an absent direction is not a property, and
            # a document full of defaults nobody chose is a document nobody can read.
            if rel_name:
                e["label"] = rel_name
            elif a.label:
                e["label"] = a.label
            if a.dir and a.dir != "none":
                e["dir"] = a.dir
            if a.time:
                e["time"] = a.time
            if style:
                e["style"] = style
            if a.color:
                e["color"] = a.color
            if a.dash:
                e["dash"] = a.dash
            if a.width is not None:
                e["width"] = a.width
            # Written explicitly, and only when it is not the default: an edge of power 1 in the
            # document says nothing.
            if a.power != 1:
                e["power"] = a.power
            g["edges"].append(e)
            save(g, path)
            looks = f" [{style}]" if style else ""
            print(f"added edge {a.src} -> {a.dst}{looks} -> {len(g['edges'])} edges")
            # A co-citation drawn as structure is the mistake that made the loudest thing on the
            # map the weakest relation. Say it at the moment it is written, not a week later.
            if "co-cit" in (a.label or "").lower() and a.power > 0.1:
                print(f"          note: this is labelled a co-citation at power {a.power} — "
                      f"co-citation is texture: --power 0.05 --style dashed, count in "
                      f"--set cocited=N")
            return 0
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
        if a.cmd == "history":
            rows = graph_history(path, a.limit)
            if not rows:
                print("no history: this workspace is not a git repository, or git is not "
                      "installed. Every change is still saved — there is just nothing to "
                      "compare against.")
                return 0
            print(f"{path.parent.name}: {len(rows)} change(s), newest first")
            for line in rows:
                print(f"  {line}")
            return 0

        if a.cmd == "undo":
            ok, detail = graph_undo(path, max(1, a.steps))
            if not ok:
                print(f"error: {detail}", file=sys.stderr)
                return 2
            g = load(path)
            print(f"restored {path.parent.name} to {detail} — "
                  f"{len(g['nodes'])} nodes / {len(g['edges'])} edges")
            print("the undo is itself a change, so `history` shows it and `undo` can undo it")
            return 0

        if a.cmd == "declare":
            name = a.edge.strip()
            if not name:
                print("error: --edge wants a relation word", file=sys.stderr)
                return 2
            meta = g.setdefault("meta", {})
            declared = meta.setdefault("edges", [])
            froms = [k.strip() for k in a.src_kinds.split(",") if k.strip()]
            tos = [k.strip() for k in a.dst_kinds.split(",") if k.strip()]
            entry = {"name": name, "dir": a.dir}
            if froms:
                entry["from"] = froms
            if tos:
                entry["to"] = tos
            for key, val in (("color", a.color), ("style", a.style), ("power", a.power)):
                if val is not None:
                    entry[key] = val
            replaced = False
            for i, ex in enumerate(declared):
                if ex.get("name") == name:
                    declared[i] = entry
                    replaced = True
                    break
            if not replaced:
                declared.append(entry)
            save(g, path)
            ends = f"{','.join(froms) or 'any'} -> {','.join(tos) or 'any'}"
            print(f"{'updated' if replaced else 'declared'} relation '{name}': dir={a.dir}, "
                  f"{ends}")
            print(f"          now `add-edge --rel {name}` checks its ends and takes this "
                  f"relation's look")
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
            lim = (g.get("meta") or {}).get("limits") or {}
            if lim.get("nodes") or lim.get("edges"):
                over = []
                if lim.get("nodes") and len(g.get("nodes", [])) > lim["nodes"]:
                    over.append(f"{len(g['nodes'])} nodes over the {lim['nodes']} asked for")
                if lim.get("edges") and len(g.get("edges", [])) > lim["edges"]:
                    over.append(f"{len(g['edges'])} edges over the {lim['edges']} asked for")
                if over:
                    r["info"].append(
                        "over this graph's own draw limits (" + ", ".join(over) +
                        ") — legal to write, but the page will open it grouped; "
                        "`limits --nodes N --edges M` changes what it asks for")

            # A declared relation is a promise about both ends. Check the edges that use one:
            # a `part-of` running into a paper is not a typo the reader can see on screen.
            decls = (g.get("meta") or {}).get("edges") or []
            if decls:
                kinds = {n["id"]: (n.get("kind") or "") for n in g.get("nodes", [])}
                by_name = {d.get("name"): d for d in decls if d.get("name")}
                mismatched = []
                unknown = []
                for e in g.get("edges", []):
                    name = e.get("label") or ""
                    d = by_name.get(name)
                    if not d:
                        continue
                    got = (kinds.get(e.get("from"), ""), kinds.get(e.get("to"), ""))
                    want = (d.get("from") or [], d.get("to") or [])
                    ok = (not want[0] or got[0] in want[0]) and (not want[1] or got[1] in want[1])
                    if not ok and d.get("dir") == "in":
                        got = got[::-1]
                        ok = (not want[0] or got[0] in want[0]) and (not want[1] or got[1] in want[1])
                    if not ok:
                        mismatched.append(f"{e.get('from')} -> {e.get('to')} ({name}: "
                                          f"{got[0] or '?'} -> {got[1] or '?'})")
                for name in by_name:
                    if not any((e.get("label") or "") == name for e in g.get("edges", [])):
                        unknown.append(name)
                if mismatched:
                    r["errors"].append(
                        f"{len(mismatched)} edge(s) break the kind contract of their relation: "
                        + "; ".join(mismatched[:3]) + (" …" if len(mismatched) > 3 else ""))
                if unknown:
                    r["warnings"].append(
                        f"declared relation(s) nothing uses: {', '.join(unknown)} — a declaration "
                        f"no edge carries is a decision that never applies")

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
            if a.desc is not None:
                extra["desc"] = a.desc
            if not extra and not a.unset:
                print("error: nothing to set — pass --set KEY=VALUE, --desc \"...\" and/or "
                      "--unset KEY", file=sys.stderr)
                return 2
            deg = {}
            for e in g["edges"]:
                deg[e.get("from")] = deg.get(e.get("from"), 0) + 1
                deg[e.get("to")] = deg.get(e.get("to"), 0) + 1
            for n in g["nodes"]:
                if n["id"] == a.id:
                    # A description is written *about* something at a moment: keeping the number
                    # of connections it was written against is what lets `review` say later which
                    # sentences have not been re-read since the graph grew around them.
                    if "desc" in extra:
                        n["desc_rev"] = deg.get(n["id"], 0)
                    for k in a.unset:
                        n.pop(k, None)
                    n.update(extra)
                    save(g, path)
                    shown = ", ".join(f"{k}={str(v)[:40]}" for k, v in extra.items())
                    if a.unset:
                        shown += (", " if shown else "") + "dropped " + ", ".join(a.unset)
                    print(f"updated {a.id}: {shown}")
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
            print(f"          python3 scripts/kg.py open   --html <the page it printed>")
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

    if a.cmd == "note":
        path = resolve_graph(a.graph)
        g = load(path)
        d = docs_dir_for(path)
        if a.list:
            docs = collect_docs(path)
            if not docs:
                print(f"no notes yet — {d} does not exist, or holds no .md files")
            else:
                print(f"{len(docs)} note(s) in {d}:")
                pointed = {str(n.get("doc") or n.get("md") or "") for n in g["nodes"]}
                for k in docs:
                    mark = "-> a node" if k in pointed else "  (unlinked)"
                    print(f"  {k:<34} {len(docs[k]):>6} chars  {mark}")
            return 0
        name = (a.file or "").strip()
        title = (a.title or "").strip()
        if a.node:
            n = next((x for x in g["nodes"] if x["id"] == a.node), None)
            if n is None:
                print(f"error: no node '{a.node}' in this graph", file=sys.stderr)
                return 2
            name = name or f"{slug(n.get('label') or a.node)}.md"
            title = title or str(n.get("label") or a.node)
        else:
            name = name or DOCS_OVERVIEW
            title = title or f"{(g.get('meta') or {}).get('title') or 'this graph'} — notes"
        if not name.endswith(".md"):
            name += ".md"
        d.mkdir(parents=True, exist_ok=True)
        f = d / name
        existed = f.exists()
        if a.text:
            # --text writes what was given, whether or not a note is already there: an agent
            # that has written the prose and passes it in means it, and silently keeping the
            # skeleton instead would be the worst of both.
            f.write_text(a.text if a.text.endswith("\n") else a.text + "\n")
        elif not existed:
            f.write_text(
                f"# {title}\n\n"
                f"<!-- What this is, why it matters to the subject, and where the claim comes "
                f"from.\n     A note is read by the reader *and* by the next agent: write both "
                f"audiences. -->\n\n"
                f"## What it is\n\n\n## Why it matters here\n\n\n## Sources\n\n")
        if a.node:
            for x in g["nodes"]:
                if x["id"] == a.node:
                    x["doc"] = f"{DOCS_DIRNAME}/{name}"
            save(g, path)
        rel = f"{DOCS_DIRNAME}/{name}"
        print(f"{'updated' if existed else 'created'} {rel}"
              + (f" and pointed {a.node} at it" if a.node else ""))
        print(f"  {f}")
        print("  render to put it in the page: it travels inlined, so the page stays one file")
        return 0

    if a.cmd == "review":
        path = resolve_graph(a.graph)
        g = load(path)
        # The work list for keeping a field survey honest: what each body says, how connected it
        # is now, and whether its sentence predates the connections around it.
        deg = {}
        for e in g["edges"]:
            deg[e.get("from")] = deg.get(e.get("from"), 0) + 1
            deg[e.get("to")] = deg.get(e.get("to"), 0) + 1
        bodies = [n for n in g["nodes"] if n.get("kind") in NEEDS_DESC]
        notes = collect_docs(path)
        missing, stale, fresh = [], [], []
        for n in bodies:
            nid = n.get("id")
            desc = (n.get("desc") or "").strip()
            rev = n.get("desc_rev")
            row = (nid, n.get("kind"), deg.get(nid, 0), len(desc), n.get("doc") or "")
            if not desc:
                missing.append(row)
            elif isinstance(rev, int) and deg.get(nid, 0) > rev:
                stale.append(row + (rev,))
            else:
                fresh.append(row)
        print(f"{len(bodies)} body/bodies that must carry a description, in "
              f"{(g.get('meta') or {}).get('title') or 'this graph'}:")
        print(f"  {len(fresh):>3} described and current")
        print(f"  {len(stale):>3} described before the graph grew around them  (re-read these)")
        print(f"  {len(missing):>3} with no description at all")
        for label, rows in (("stale", stale), ("missing", missing)):
            for row in rows[:max(0, a.top)]:
                nid, kind, d, n, doc = row[:5]
                extra = f" written at degree {row[5]}" if len(row) > 5 else ""
                print(f"    - {nid} ({kind}) degree {d}{extra}"
                      + (f" note: {doc}" if doc else " — no note either"))
        unlinked = [k for k in notes if k not in {str(x.get("doc") or "") for x in g["nodes"]}]
        if unlinked:
            print(f"  {len(unlinked)} note(s) no node points at: {', '.join(unlinked[:4])}")
        if missing or stale:
            print("\nto write or rewrite one:  python3 scripts/kg.py set-node --graph <id> "
                  "--id <node> --desc \"...\"")
            print("the long form:            python3 scripts/kg.py note --graph <id> "
                  "--node <node>")
        return 0

    if a.cmd == "visuals":
        path = resolve_graph(a.graph)
        g = load(path)
        vis = g["meta"].setdefault("visuals", {})
        wanted = any(x is not None for x in (a.arrows, a.edge_width, a.node_scale, a.halo,
                                           ))
        if not wanted or a.show:
            if not vis:
                print("nothing decided for this graph — the app's defaults are in force")
            for k, v in sorted(vis.items()):
                print(f"  {k} = {v}")
            if not wanted:
                return 0
        if a.arrows is not None:
            vis["arrows"] = a.arrows == "on"
        if a.halo is not None:
            vis["halo"] = a.halo == "on"
        if a.edge_width is not None:
            vis["edge_width"] = a.edge_width
        if a.node_scale is not None:
            vis["node_scale"] = a.node_scale
        save(g, path)
        print("visuals recorded:",
              ", ".join(f"{k}={v}" for k, v in sorted(vis.items())))
        return 0

    if a.cmd == "limits":
        path = resolve_graph(a.graph)
        g = load(path)
        cur = (g.get("meta") or {}).get("limits") or dict(DEFAULT_LIMITS)
        if a.nodes is None and a.edges is None:
            n, e = len(g.get("nodes", [])), len(g.get("edges", []))
            print(f"limits {cur.get('nodes')} nodes / {cur.get('edges')} edges")
            print(f"this graph is {n} nodes / {e} edges — "
                  + ("within them" if n <= cur.get("nodes", n) and e <= cur.get("edges", e)
                     else "over them, so the page opens it grouped"))
            print("ask for more:  limits --nodes N --edges M   "
                  "(it is a request, not a hard stop — the page decides)")
            return 0
        meta = g.setdefault("meta", {})
        meta["limits"] = {"nodes": int(a.nodes if a.nodes is not None else cur.get("nodes", DEFAULT_LIMITS["nodes"])),
                          "edges": int(a.edges if a.edges is not None else cur.get("edges", DEFAULT_LIMITS["edges"]))}
        save(g, path)
        print(f"limits {meta['limits']['nodes']} nodes / {meta['limits']['edges']} edges")
        return 0


    if a.cmd == "render":
        path = resolve_graph(a.graph)
        g = load(path)
        out = render(g, Path(a.out) if a.out else default_out(path), a.app, path)
        print(f"rendered {len(g['nodes'])} nodes / {len(g['edges'])} edges -> {out}")
        notes = len(collect_docs(path))
        if notes:
            print(f"  with {notes} note(s) from {DOCS_DIRNAME}/ — they travel in the page")
        print(f"  {file_url(out)}")
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

    return 1


if __name__ == "__main__":
    sys.exit(main())
