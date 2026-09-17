"""clang-uml 실행과 JSON 결과 해석.

config/clang-uml.yaml (정적 다이어그램) + config/scenarios.yaml (sequence 진입점) 을 합쳐
build/clang-uml.yaml 을 만들고, `clang-uml -g json -g mermaid` 로 두 형식을 동시에 뽑는다.
JSON 은 knowledge model 로, Mermaid 는 SDD 본문에 그대로 싣는다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Iterator

import yaml

from ..config import Config
from .model import (ClassInfo, IncludeEdge, KnowledgeModel, Location, Message, Method,
                    PackageInfo, Relation, Scenario, relpath)


def write_config(cfg: Config, compdb_dir: Path) -> Path:
    with cfg.clang_uml_file.open("r", encoding="utf-8") as f:
        base: dict[str, Any] = yaml.safe_load(f) or {}

    base["compilation_database_dir"] = compdb_dir.as_posix()
    base["output_directory"] = (cfg.build_dir / "diagrams").as_posix()
    diagrams: dict[str, Any] = base.setdefault("diagrams", {})

    # include 다이어그램의 relative_to 도 실제 소스 루트로 맞춘다.
    for d in diagrams.values():
        if d.get("type") == "include":
            d["relative_to"] = cfg.source_root.as_posix()

    for sc in cfg.scenarios():
        diagrams[f"seq_{sc['id']}"] = {
            "type": "sequence",
            "glob": list(sc.get("glob") or ["**/*.cpp"]),
            "from": [{"function": sc["from"]}],
            "combine_free_functions_into_file_participants": True,
            "generate_message_comments": False,
            "generate_return_types": False,
            "generate_condition_statements": True,
        }

    out = cfg.build_dir / "clang-uml.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        yaml.safe_dump(base, f, allow_unicode=True, sort_keys=False)
    return out


def run(cfg: Config, config_path: Path, only: list[str] | None = None) -> Path:
    cmd = [cfg.clang_uml_bin, "-c", config_path.as_posix(), "-g", "json", "-g", "mermaid", "--progress"]
    for name in only or []:
        cmd += ["-n", name]
    subprocess.run(cmd, cwd=cfg.root, check=True)
    return cfg.build_dir / "diagrams"


# ---- JSON 해석 ------------------------------------------------------------

def _loc(d: dict[str, Any] | None, root: Path) -> Location | None:
    if not d or "file" not in d:
        return None
    return Location(file=relpath(str(d["file"]), root), line=int(d.get("line", 0)))


def _walk_elements(elements: list[dict[str, Any]], package: str = "") -> Iterator[tuple[dict[str, Any], str]]:
    """package 로 중첩된 elements 를 (element, package_name) 으로 평탄화한다."""
    for el in elements:
        if el.get("type") == "package":
            pkg = el.get("display_name") or el.get("name") or package
            yield el, pkg
            yield from _walk_elements(el.get("elements", []), pkg)
        else:
            yield el, package


def _parse_class(model: KnowledgeModel, doc: dict[str, Any], root: Path) -> None:
    ids: dict[str, str] = {}
    for el, pkg in _walk_elements(doc.get("elements", [])):
        t = el.get("type")
        name = el.get("display_name") or el.get("name") or ""
        if t == "package":
            model.packages.setdefault(pkg, PackageInfo(name=pkg, path=str(el.get("path", ""))))
            continue
        if t not in ("class", "struct", "enum", "concept", "objc_interface"):
            continue
        ids[str(el.get("id"))] = name
        ci = model.classes.get(name) or ClassInfo(name=name, kind=t)
        ci.loc = ci.loc or _loc(el.get("source_location"), root)
        ci.package = ci.package or pkg
        for m in el.get("methods", []) or []:
            mname = m.get("display_name") or m.get("name") or ""
            if mname and all(x.name != mname for x in ci.methods):
                ci.methods.append(Method(name=mname, loc=_loc(m.get("source_location"), root)))
        model.classes[name] = ci
        if pkg:
            p = model.packages.setdefault(pkg, PackageInfo(name=pkg))
            if name not in p.classes:
                p.classes.append(name)

    for rel in doc.get("relationships", []) or []:
        s = ids.get(str(rel.get("source")))
        d = ids.get(str(rel.get("destination")))
        rtype = str(rel.get("type", ""))
        if not s or not d:
            continue
        if rtype in ("inheritance", "extension"):
            model.classes[s].bases.append(d)
        model.relations.append(Relation(source=s, target=d, type=rtype))


def _iter_messages(items: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """if/for/while 같은 블록 안에 중첩된 message 를 순서대로 꺼낸다."""
    for it in items:
        if it.get("type") == "message":
            yield it
            continue
        for key in ("messages", "branches"):
            sub = it.get(key)
            if isinstance(sub, list):
                # branches 의 원소는 {type, messages} 이므로 재귀로 같은 함수가 처리한다.
                yield from _iter_messages(sub)


def _parse_sequence(model: KnowledgeModel, doc: dict[str, Any], sid: str, sc: dict[str, Any], root: Path) -> None:
    names: dict[str, str] = {}
    for p in doc.get("participants", []) or []:
        names[str(p.get("id"))] = p.get("display_name") or p.get("name") or str(p.get("id"))

    scenario = Scenario(id=sid, title=sc.get("title", sid), entry=sc.get("from", ""),
                        participants=list(dict.fromkeys(names.values())))
    depth_limit = int(sc.get("depth", 0) or 0)
    for seq in doc.get("sequences", []) or []:
        for m in _iter_messages(seq.get("messages", []) or []):
            src = names.get(str(m.get("from")), str(m.get("from")))
            dst = names.get(str(m.get("to")), str(m.get("to")))
            scenario.messages.append(Message(src=src, dst=dst, name=str(m.get("name", "")),
                                             loc=_loc(m.get("source_location"), root)))
    # depth 는 메시지 수 상한으로 근사한다. 정확한 호출 깊이는 clang-uml 이 JSON 에 주지 않는다.
    if depth_limit and len(scenario.messages) > depth_limit * 25:
        scenario.messages = scenario.messages[: depth_limit * 25]
    model.scenarios[sid] = scenario


def _parse_include(model: KnowledgeModel, doc: dict[str, Any]) -> None:
    ids: dict[str, str] = {}
    for el, _ in _walk_elements(doc.get("elements", [])):
        if el.get("type") in ("file", "folder"):
            ids[str(el.get("id"))] = el.get("display_name") or el.get("name") or ""
    for rel in doc.get("relationships", []) or []:
        s, d = ids.get(str(rel.get("source"))), ids.get(str(rel.get("destination")))
        if s and d:
            model.includes.append(IncludeEdge(src=s, dst=d))


def parse_into(model: KnowledgeModel, cfg: Config, diagrams_dir: Path) -> None:
    import json

    scenarios = {sc["id"]: sc for sc in cfg.scenarios()}
    for jf in sorted(diagrams_dir.glob("*.json")):
        with jf.open("r", encoding="utf-8") as f:
            doc = json.load(f)
        dtype = doc.get("diagram_type")
        name = jf.stem
        if dtype == "class":
            _parse_class(model, doc, cfg.source_root)
        elif dtype == "package":
            for el, pkg in _walk_elements(doc.get("elements", [])):
                if el.get("type") == "package":
                    model.packages.setdefault(pkg, PackageInfo(name=pkg, path=str(el.get("path", ""))))
        elif dtype == "include":
            _parse_include(model, doc)
        elif dtype == "sequence" and name.startswith("seq_"):
            sid = name[len("seq_"):]
            _parse_sequence(model, doc, sid, scenarios.get(sid, {}), cfg.source_root)
            mmd = jf.with_suffix(".mmd")
            if mmd.exists():
                model.scenarios[sid].mermaid = mmd.read_text(encoding="utf-8")
