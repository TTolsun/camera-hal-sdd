"""Deterministic diagram policy shared by Markdown generation and site rendering."""

from __future__ import annotations

import fnmatch
import html

from .config import Config
from .facts.model import KnowledgeModel

POLICY_VERSION = 1

def class_diagram(model: KnowledgeModel, patterns: list[str], limit: int = 16, direction: str = "LR", strip_namespace: str = "") -> str:
    """Only declared classes and extracted edges; no inferred call ordering."""
    selected = {n for n in model.classes if any(fnmatch.fnmatchcase(n, p) or fnmatch.fnmatchcase(n.rsplit("::", 1)[-1], p) for p in patterns)}
    if not selected:
        return ""
    if direction not in ("LR", "TB", "RL", "BT") or limit < 1:
        raise RuntimeError("Invalid diagram direction or max_nodes")
    names = set(selected)
    # Direct bases give the diagram context. Never expand the entire dependency graph.
    bases = {b for n in selected for b in model.classes[n].bases}
    if len(names | bases) > limit:
        raise RuntimeError(f"Diagram has {len(names | bases)} nodes (limit {limit}); narrow facts.classes or increase diagrams.max_nodes")
    names |= bases
    ids = {n: f"c{i}" for i, n in enumerate(sorted(names))}
    rows = [f"flowchart {direction}"]
    for name, ident in ids.items():
        label = html.escape(name.removeprefix(strip_namespace), quote=True)
        rows.append(f'  {ident}["{label}"]' + (":::context" if name not in selected else ""))
    edges = {(n, b, "inheritance") for n in selected for b in model.classes[n].bases}
    edges |= {(r.source, r.target, r.type) for r in model.relations
              if r.source in selected and r.target in names}
    labels = {"inheritance": "상속", "association": "필드 참조", "dependency": "의존",
              "aggregation": "집합", "composition": "합성"}
    for source, target, kind in sorted(edges):
        if kind in labels:
            arrow = "-.->" if kind == "inheritance" else "-->"
            rows.append(f"  {ids[source]} {arrow}|{labels[kind]}| {ids[target]}")
    rows.append("  classDef context fill:#fafafa,stroke:#aaa,stroke-dasharray:4 3,color:#555")
    return "\n".join(rows)


def section_diagram(cfg: Config, model: KnowledgeModel, section: dict) -> str:
    policy = {**(cfg.raw.get("diagrams") or {}), **(section.get("diagram") or {})}
    if not policy.get("enabled", False):
        return ""
    return class_diagram(model, section.get("facts", {}).get("classes", []),
                         limit=int(policy.get("max_nodes", 16)),
                         direction=str(policy.get("direction", "LR")),
                         strip_namespace=str(policy.get("strip_namespace", "")))


def diagram_block(source: str) -> str:
    if not source:
        return ""
    return ("\n<!-- sdd:class-diagram -->\n## 클래스 관계\n\n"
            "화살표의 글자는 추출한 관계를 나타내며, 점선은 상속입니다. "
            "화살표는 참조 대상 또는 기반 클래스를 향합니다. 호출 순서를 뜻하지 않습니다.\n\n"
            f"```mermaid\n{source}\n```\n<!-- /sdd:class-diagram -->\n\n")
