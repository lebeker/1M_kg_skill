"""Foresight tech-tree export -> kg/1.

The Foresight Institute publishes its tech tree as a `.graph` file: a JSON object
with a flat `items` list, where each item is either a node or an edge. It is not a
kg/1 document and loading one as if it were yields a plausible "0 nodes" — the worst
kind of wrong answer, which is why the engine refuses it by name.

What this export does that the kg/1 format does not assume:

  * source URLs live in `desc`, not in `link` — they are pulled out here;
  * the tree lives in `parent` on the node, not in the edges, so a node's hierarchy
    survives only if `parent` is carried across (`parent` groups nodes into panels);
  * `tags` carry `goal` / `project`, which is what maps to a node kind;
  * `pos.x` / `pos.y` are authored positions — the layout is skipped for them;
  * `fill` is the node colour when it is not plain white.

Contract with the engine (`kg.py import --format foresight ...`):

    convert(src: Path, title: str | None, schema: str, colors: dict) -> dict

It returns a complete kg/1 document. Nothing here is imported by the engine at
startup — adapters are loaded by name, so one vendor's format never becomes part of
the engine.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

URL_RE = re.compile(r"https?://[^\s\)\]\"<>]+")


def convert(src: Path, title: str | None, schema: str, colors: dict) -> dict:
    raw = json.loads(src.read_text())
    items = raw.get("items", [])
    nodes, edges = [], []

    for it in items:
        if it.get("kind") == "node":
            tags = it.get("tags") or []
            desc = it.get("desc") or ""
            link = it.get("link") or ""
            urls = URL_RE.findall(desc) + URL_RE.findall(link)
            label = it.get("label") or ""
            low = label.strip().lower()
            if re.search(r"\b(lab|laboratory)\s*$", low):
                kind = "lab"
            elif "goal" in tags:
                kind = "concept"
            elif "project" in tags:
                kind = "company"
            else:
                kind = "concept"
            n = {
                "id": str(it.get("id")),
                "label": label,
                "kind": kind,
                "size": 2,
                "style": "solid",
                "desc": desc[:600],
                "link": urls[0] if urls else "",
                "urls": urls,
                "tags": tags,
            }
            # The hierarchy IS the tree. Dropping `parent` turns a tech tree into a
            # point cloud, and no viewer can rebuild it.
            if it.get("parent") not in (None, ""):
                n["parent"] = str(it["parent"])
            if it.get("is_collapsed"):
                n["collapsed"] = True
            pos = it.get("pos") or {}
            if isinstance(pos, dict) and pos.get("x") is not None:
                n["x"], n["y"] = pos.get("x"), pos.get("y")
            fill = (it.get("fill") or "").strip()
            if fill and fill not in ("#ffffff", "#ffffffff", "white"):
                n["color"] = fill
            nodes.append(n)

        elif it.get("kind") == "edge":
            edges.append({
                "from": str(it.get("fromId")),
                "to": str(it.get("toId")),
                "label": it.get("label") or "",
                "dir": "in" if it.get("directed") else "none",
                "weight": it.get("weight") or 1,
                "desc": (it.get("desc") or "")[:300],
            })

    return {
        "meta": {
            "title": title or src.stem,
            "schema": schema,
            "imported_from": str(src),
            "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "colors": dict(colors),
        },
        "nodes": nodes,
        "edges": edges,
    }
