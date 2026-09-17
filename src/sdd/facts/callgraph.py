"""libclang 만으로 호출 순서(시나리오)와 클래스 관계를 뽑는다. clang-uml 이 없을 때의 대체 경로.

clang-uml 보다 얻는 것이 적다(템플릿 관계, 조건 분기 블록, include 그래프 없음).
대신 pip 의존성만으로 동작하므로 PoC 와 CI 초기 구성에 쓴다.

두 단계로 동작한다.
1. 모든 TU 를 파싱해 함수 정의마다 "호출 목록" 을 모으고(USR 기준), 클래스의 상속·필드 관계를 모은다.
2. scenarios.yaml 의 진입 함수에서 깊이 제한 DFS 로 호출 순서를 만든다.
   가상 함수 호출은 정적으로 확정되지 않으므로 "virtual 후보" 로 표시하고 override 를 함께 따라간다.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from clang import cindex

from ..config import Config
from .comments import _CLASS_KINDS, _FUNCTION_KINDS, _METHOD_KINDS, _loc, _qualified, _under, parse_args
from .model import ClassInfo, KnowledgeModel, Location, Message, PackageInfo, Relation, Scenario, relpath

_MAX_MESSAGES = 120


@dataclass
class Call:
    callee_usr: str
    callee_name: str          # 짧은 이름 (메서드 이름)
    callee_owner: str         # 클래스 짧은 이름 또는 파일 stem
    loc: Location | None
    # direct | virtual | pointer(함수 포인터 멤버) | callable(std::function 등) | unresolved
    kind: str = "direct"


@dataclass
class FuncDef:
    usr: str
    qualified: str
    display: str              # 이름(인자 타입) 형태
    owner: str
    loc: Location | None
    calls: list[Call] = field(default_factory=list)


@dataclass
class Graph:
    defs: dict[str, FuncDef] = field(default_factory=dict)
    # 클래스 USR -> (짧은 이름, 완전한 이름)
    classes: dict[str, tuple[str, str]] = field(default_factory=dict)
    # 오버라이드: 기반 메서드 USR -> 파생 메서드 USR 목록
    overrides: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    inherits: list[tuple[str, str]] = field(default_factory=list)       # (derived, base) 완전한 이름
    fields: list[tuple[str, str, str]] = field(default_factory=list)    # (owner, target, field name)
    # 클래스 완전한 이름 -> {메서드 displayname: USR}. override 계산용.
    methods: dict[str, dict[str, str]] = field(default_factory=lambda: defaultdict(dict))


def _short(qualified: str) -> str:
    return qualified.rsplit("::", 1)[-1]


def _owner_of(cursor: cindex.Cursor, root: Path) -> str:
    parent = cursor.semantic_parent
    if parent is not None and parent.kind in _CLASS_KINDS:
        return _short(_qualified(parent))
    f = cursor.location.file
    return Path(f.name).stem if f else "?"


def _type_decl(t: cindex.Type, root: Path, depth: int = 0) -> cindex.Cursor | None:
    """std::unique_ptr<Foo>, std::vector<std::unique_ptr<Foo>>, Foo*, const Foo& 에서
    소스 루트 안에 선언된 Foo 를 찾는다. 루트 밖 템플릿(std::)은 인자를 차례로 들여다본다."""
    if depth > 4:
        return None
    t = t.get_canonical()
    for _ in range(4):
        if t.kind in (cindex.TypeKind.POINTER, cindex.TypeKind.LVALUEREFERENCE, cindex.TypeKind.RVALUEREFERENCE):
            t = t.get_pointee()
            continue
        break
    decl = t.get_declaration()
    if decl is not None and decl.kind in _CLASS_KINDS and decl.spelling and _under(decl, root):
        return decl
    n = t.get_num_template_arguments()
    for i in range(max(n, 0)):
        found = _type_decl(t.get_template_argument_type(i), root, depth + 1)
        if found is not None:
            return found
    return None


def _is_qualified_call(node: cindex.Cursor) -> bool:
    """`Base::method(...)` 처럼 한정된 호출은 가상 함수라도 정적으로 결정된다."""
    for tok in node.get_tokens():
        if tok.spelling == "(":
            return False
        if tok.spelling == "::":
            return True
    return False


def _callee_expr_name(node: cindex.Cursor) -> str:
    for c in node.get_children():
        if c.kind in (cindex.CursorKind.MEMBER_REF_EXPR, cindex.CursorKind.DECL_REF_EXPR) and c.spelling:
            return c.spelling
        inner = _callee_expr_name(c)
        if inner:
            return inner
    return ""


def _walk_all(cursor: cindex.Cursor, root: Path):
    for child in cursor.get_children():
        if not _under(child, root):
            continue
        yield child
        yield from _walk_all(child, root)


def build_graph(cfg: Config, entries: list[dict[str, Any]]) -> Graph:
    index = cindex.Index.create()
    root = cfg.source_root.resolve()
    g = Graph()
    for entry in entries:
        src, args = parse_args(entry)
        try:
            tu = index.parse(str(src), args=args)
        except cindex.TranslationUnitLoadError:
            continue
        for cur in _walk_all(tu.cursor, root):
            if cur.kind in _CLASS_KINDS and cur.is_definition() and cur.spelling:
                q = _qualified(cur)
                g.classes[cur.get_usr()] = (cur.spelling, q)
                for child in cur.get_children():
                    if child.kind == cindex.CursorKind.CXX_METHOD:
                        g.methods[q][child.displayname] = child.get_usr()
                    if child.kind == cindex.CursorKind.CXX_BASE_SPECIFIER:
                        base = child.referenced
                        if base is not None and _under(base, root) and (q, _qualified(base)) not in g.inherits:
                            g.inherits.append((q, _qualified(base)))
                    elif child.kind == cindex.CursorKind.FIELD_DECL:
                        decl = _type_decl(child.type, root)
                        if decl is not None and _qualified(decl) != q:
                            edge = (q, _qualified(decl), child.spelling)
                            if edge not in g.fields:
                                g.fields.append(edge)
                continue

            if cur.kind not in (_METHOD_KINDS | _FUNCTION_KINDS) or not cur.is_definition():
                continue
            usr = cur.get_usr()
            fd = FuncDef(usr=usr, qualified=_qualified(cur), display=cur.displayname,
                         owner=_owner_of(cur, root), loc=_loc(cur, root))
            for node in _walk_all(cur, root):
                if node.kind != cindex.CursorKind.CALL_EXPR:
                    continue
                loc = (Location(file=relpath(node.location.file.name, root), line=node.location.line)
                       if node.location.file else None)
                ref = node.referenced
                if ref is None:
                    fd.calls.append(Call("", _callee_expr_name(node) or "(알 수 없는 호출)", "?", loc, kind="unresolved"))
                    continue
                if ref.kind in (cindex.CursorKind.FIELD_DECL, cindex.CursorKind.VAR_DECL, cindex.CursorKind.PARM_DECL):
                    # 함수 포인터 멤버 호출: callbacks_->process_capture_result(...)
                    fd.calls.append(Call("", ref.spelling, _owner_of(ref, root), loc, kind="pointer"))
                    continue
                if ref.kind == cindex.CursorKind.CXX_METHOD and ref.spelling == "operator()" and not _under(ref, root):
                    # std::function 같은 호출 가능 객체: handler_(*frame)
                    fd.calls.append(Call("", _callee_expr_name(node) or "callable", fd.owner, loc, kind="callable"))
                    continue
                if ref.kind not in (_METHOD_KINDS | _FUNCTION_KINDS) or not _under(ref, root):
                    continue
                if ref.kind == cindex.CursorKind.CONSTRUCTOR and ref.semantic_parent is not None \
                        and not ref.semantic_parent.spelling:
                    continue
                is_virtual = (ref.kind == cindex.CursorKind.CXX_METHOD and ref.is_virtual_method()
                              and not _is_qualified_call(node))
                fd.calls.append(Call(ref.get_usr(), ref.spelling, _owner_of(ref, root), loc,
                                     kind="virtual" if is_virtual else "direct"))
            g.defs.setdefault(usr, fd)

    # override: 파생 클래스에 같은 displayname 의 메서드가 있으면 기반 메서드의 후보로 등록한다.
    # (이 libclang 바인딩에는 get_overridden_cursors 가 없어서 이름으로 맞춘다. 상속 사슬을 따라 올라간다.)
    bases_of: dict[str, list[str]] = defaultdict(list)
    for derived, base in g.inherits:
        bases_of[derived].append(base)
    for derived, methods in g.methods.items():
        stack = list(bases_of.get(derived, []))
        seen: set[str] = set()
        while stack:
            base = stack.pop()
            if base in seen:
                continue
            seen.add(base)
            for display, usr in methods.items():
                base_usr = g.methods.get(base, {}).get(display)
                if base_usr and base_usr != usr and usr not in g.overrides[base_usr]:
                    g.overrides[base_usr].append(usr)
            stack.extend(bases_of.get(base, []))
    return g


def _normalize_sig(sig: str) -> tuple[str, str]:
    name, _, params = sig.partition("(")
    params = re.sub(r"\s+", "", params.rstrip(")"))
    return name.strip(), params


def find_entry(g: Graph, from_sig: str) -> FuncDef | None:
    name, params = _normalize_sig(from_sig)
    candidates = [fd for fd in g.defs.values() if fd.qualified == name or fd.qualified.endswith("::" + name)]
    if params:
        exact = [fd for fd in candidates if re.sub(r"\s+", "", fd.display.partition("(")[2].rstrip(")")) == params]
        if exact:
            return exact[0]
    return candidates[0] if candidates else None


def trace(g: Graph, entry: FuncDef, depth: int) -> tuple[list[Message], int]:
    messages: list[Message] = []
    unresolved = 0

    def visit(fd: FuncDef, level: int, path: set[str]) -> None:
        nonlocal unresolved
        if level >= depth or len(messages) >= _MAX_MESSAGES:
            return
        for call in fd.calls:
            if call.kind in ("pointer", "callable", "unresolved"):
                unresolved += 1
                label = {"pointer": "함수 포인터, 정적 추적 불가", "callable": "콜백 객체, 정적 추적 불가",
                         "unresolved": "정적 추적 불가"}[call.kind]
                messages.append(Message(src=fd.owner, dst=call.callee_owner, name=call.callee_name,
                                        loc=call.loc, note=label))
                continue
            targets = [call.callee_usr]
            note = ""
            if call.kind == "virtual":
                over = g.overrides.get(call.callee_usr, [])
                # 기반 구현이 있으면(순수 가상이 아니면) 그것도 후보다.
                base_def = g.defs.get(call.callee_usr)
                targets = ([call.callee_usr] if base_def else []) + over
                if len(targets) > 1:
                    note = "virtual 후보"
                elif not targets:
                    unresolved += 1
                    messages.append(Message(src=fd.owner, dst=call.callee_owner, name=call.callee_name,
                                            loc=call.loc, note="virtual, override 없음"))
                    continue
            for t_usr in targets:
                t = g.defs.get(t_usr)
                owner = t.owner if t else call.callee_owner
                messages.append(Message(src=fd.owner, dst=owner, name=call.callee_name, loc=call.loc, note=note))
                if t and t_usr not in path:
                    visit(t, level + 1, path | {t_usr})

    visit(entry, 0, {entry.usr})
    return messages, unresolved


def mermaid_sequence(entry: FuncDef, messages: list[Message]) -> str:
    parts = ["sequenceDiagram"]
    seen: list[str] = []
    for name in [entry.owner] + [m.dst for m in messages]:
        if name not in seen:
            seen.append(name)
            parts.append(f"    participant {name}")
    for m in messages:
        arrow = "-->>" if m.note else "->>"
        label = f"{m.name}()" + (f" [{m.note}]" if m.note else "")
        parts.append(f"    {m.src}{arrow}{m.dst}: {label}")
    return "\n".join(parts)


def mermaid_class(model: KnowledgeModel) -> str:
    parts = ["classDiagram"]
    for c in sorted(model.classes.values(), key=lambda x: x.name):
        parts.append(f"    class {_short(c.name)} {{")
        for m in c.methods[:6]:
            parts.append(f"        +{m.name}()")
        parts.append("    }")
    for r in model.relations:
        s, t = _short(r.source), _short(r.target)
        if r.type == "inheritance":
            parts.append(f"    {t} <|-- {s}")
        elif r.type == "association":
            parts.append(f"    {s} --> {t}")
    return "\n".join(parts)


def collect(model: KnowledgeModel, cfg: Config, entries: list[dict[str, Any]]) -> dict[str, int]:
    g = build_graph(cfg, entries)
    root = cfg.source_root.resolve()

    # 패키지 = 선언 파일의 첫 디렉터리. clang-uml 의 package_type: directory 와 같은 규칙.
    for c in model.classes.values():
        if c.loc and not c.package:
            parts = Path(c.loc.file).parts
            c.package = parts[0] if len(parts) > 1 else "(root)"
        if c.package:
            p = model.packages.setdefault(c.package, PackageInfo(name=c.package, path=c.package))
            if c.name not in p.classes:
                p.classes.append(c.name)

    for derived, base in g.inherits:
        model.relations.append(Relation(source=derived, target=base, type="inheritance"))
        c = model.classes.get(derived)
        if c is not None and base not in c.bases:
            c.bases.append(base)
    seen_assoc: set[tuple[str, str]] = set()
    for owner, target, _name in g.fields:
        if (owner, target) not in seen_assoc:
            seen_assoc.add((owner, target))
            model.relations.append(Relation(source=owner, target=target, type="association"))

    stats = {"functions": len(g.defs), "scenarios": 0, "missing_entries": 0}
    for sc in cfg.scenarios():
        entry = find_entry(g, sc["from"])
        if entry is None:
            print(f"[callgraph] 시나리오 {sc['id']}: 진입 함수를 찾지 못했습니다: {sc['from']}")
            stats["missing_entries"] += 1
            continue
        messages, unresolved = trace(g, entry, int(sc.get("depth", 4) or 4))
        model.scenarios[sc["id"]] = Scenario(
            id=sc["id"], title=sc.get("title", sc["id"]), entry=sc["from"],
            participants=list(dict.fromkeys([entry.owner] + [m.dst for m in messages])),
            messages=messages, mermaid=mermaid_sequence(entry, messages), unresolved=unresolved)
        stats["scenarios"] += 1

    diagrams = cfg.diagrams_dir
    diagrams.mkdir(parents=True, exist_ok=True)
    (diagrams / "class_overview.mmd").write_text(mermaid_class(model) + "\n", encoding="utf-8")
    for sid, sc in model.scenarios.items():
        (diagrams / f"seq_{sid}.mmd").write_text(sc.mermaid + "\n", encoding="utf-8")
    model.meta["callgraph"] = stats
    return stats
