"""Compare extracted structure and generated artifacts without treating prose diffs as proof."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from sdd.config import load
from sdd.diagrams import section_diagram
from sdd.export_html import _split
from sdd.facts.model import KnowledgeModel


def normalized(value, source_root: str):
    if isinstance(value, str):
        return value.replace(source_root, "$SOURCE")
    if isinstance(value, list):
        return [normalized(item, source_root) for item in value]
    if isinstance(value, dict):
        return {normalized(k, source_root): normalized(v, source_root) for k, v in value.items()}
    return value


def compare(a_dir: Path, b_dir: Path) -> dict:
    configs = [load(p / "sdd.yaml") for p in (a_dir, b_dir)]
    models = [KnowledgeModel.load(cfg.facts_path) for cfg in configs]
    classes = []
    relations = []
    for model in models:
        root = model.meta["source_root"]
        classes.append({normalized(name, root): normalized({"bases": c.bases, "methods": [m.name for m in c.methods], "kind": c.kind}, root)
                        for name, c in model.classes.items()})
        relations.append({tuple(normalized([r.source, r.type, r.target], root)) for r in model.relations})
    a, b = classes
    result = {"base": models[0].meta["source_commit"], "head": models[1].meta["source_commit"],
              "classes_added": sorted(b.keys() - a.keys()), "classes_removed": sorted(a.keys() - b.keys()),
              "classes_structurally_changed": sorted(n for n in a.keys() & b.keys() if a[n] != b[n]),
              "relations_added": sorted(relations[1] - relations[0]), "relations_removed": sorted(relations[0] - relations[1]),
              "pages": [], "note": "Body differences include LLM variability and source-line movement; they do not prove semantic correctness."}
    result["named_classes_added"] = [name for name in result["classes_added"] if "(unnamed " not in name]
    result["named_classes_removed"] = [name for name in result["classes_removed"] if "(unnamed " not in name]
    for section in configs[0].sections():
        rel = section["output"]
        diagrams = [section_diagram(cfg, model, section) for cfg, model in zip(configs, models)]
        pages = [_split((cfg.sdd_dir / rel).read_text(encoding="utf-8")) for cfg in configs]
        prose = []
        for _, body in pages:
            match = re.search(r"^## 구조 설명\n(.*?)(?=^<!-- sdd:|^## |^\?\?\? |\Z)", body, re.S | re.M)
            prose.append(match[1].strip() if match else "")
        result["pages"].append({"section": section["id"], "diagram_changed": diagrams[0] != diagrams[1],
                                "body_changed": pages[0][1] != pages[1][1],
                                "prose_changed": prose[0] != prose[1], "prose": prose,
                                "status": [p[0].get("status") for p in pages],
                                "facts_omitted": [p[0].get("facts_omitted", []) for p in pages],
                                "diagram_sha256": [hashlib.sha256(d.encode()).hexdigest() for d in diagrams]})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--head-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.base_dir.resolve(), args.head_dir.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"base": report["base"], "head": report["head"],
                      "named_classes_added": report["named_classes_added"],
                      "pages": [{k: v for k, v in page.items() if k not in ("prose", "diagram_sha256")}
                                for page in report["pages"]]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
