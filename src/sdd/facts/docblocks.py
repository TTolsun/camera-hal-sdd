"""선언에 붙지 않은 문서 주석 블록에서 클래스 설명을 가져온다.

libclang 은 선언 바로 앞에 붙은 주석만 그 선언의 주석으로 준다. 그런데 클래스 설명을 헤더가 아니라
구현 파일에 `\\class` / `\\struct` 블록으로 따로 적는 코드베이스가 있다. 그 블록은 어떤 선언에도 붙지
않으므로 설명이 통째로 빠진다. libcamera 에서는 `Camera`, `CameraManager`, `Request`,
`PipelineHandler` 를 포함해 클래스의 3분의 2가 설명 없이 들어왔다.

이 모듈은 그 블록을 읽어 이름이 하나로 정해질 때만 해당 클래스에 붙인다. 후보가 여럿이면 어느 것을
설명하는지 알 수 없으므로 건드리지 않는다. 선언에 붙은 주석이 이미 있으면 그대로 둔다.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

from ..config import Config
from .comments import _EXCLUDES
from .model import KnowledgeModel, relpath

# `/** ... */` 한 덩어리. 여는 기호가 `/**` 인 것만 문서 주석으로 본다.
_BLOCK = re.compile(r"/\*\*(.*?)\*/", re.S)
# `\class Foo` 또는 `\struct ns::Foo`. doxygen 은 `@class` 표기도 허용한다.
_TAG = re.compile(r"[\\@](class|struct)\s+([A-Za-z_][\w:]*)")
# `\brief 한 줄 설명`.
_BRIEF = re.compile(r"[\\@]brief\s+([^\n]*)")
_JUNK = re.compile(r"^\s*\*\s?")


def _brief_text(body: str) -> str:
    m = _BRIEF.search(body)
    if not m:
        return ""
    return " ".join(_JUNK.sub("", m.group(1)).split())[:200]


def blocks(text: str) -> list[tuple[str, str]]:
    """문서 주석에서 (설명 대상 이름, 한 줄 설명) 을 뽑는다. 둘 다 있는 블록만 돌려준다."""
    found: list[tuple[str, str]] = []
    for match in _BLOCK.finditer(text):
        body = match.group(1)
        tag = _TAG.search(body)
        if not tag:
            continue
        brief = _brief_text(body)
        if brief:
            found.append((tag.group(2), brief))
    return found


def resolve(name: str, model: KnowledgeModel, near: str = "") -> str | None:
    """설명 대상 이름을 facts 의 클래스 하나로 정한다. 하나로 정해지지 않으면 None.

    `near` 는 그 블록이 있는 파일의 디렉터리다. 같은 짧은 이름이 여러 네임스페이스에 있을 때
    (`ipu3::IPAContext` 와 `rkisp1::IPAContext`) 같은 디렉터리에 선언된 클래스를 고른다.
    구현 파일은 자기 옆에 선언된 것을 설명하기 때문이다. 그래도 하나로 좁혀지지 않으면 비운다.
    """
    if name in model.classes:
        return name
    tail = name.rsplit("::", 1)[-1]
    candidates = [n for n in model.classes if n.rsplit("::", 1)[-1] == tail]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates or not near:
        return None
    same_dir = [n for n in candidates
                if model.classes[n].loc and str(PurePosixPath(model.classes[n].loc.file).parent) == near]
    return same_dir[0] if len(same_dir) == 1 else None


def collect(model: KnowledgeModel, cfg: Config, entries: list[dict[str, Any]]) -> dict[str, int]:
    """빌드에 들어간 파일의 문서 주석 블록으로 비어 있는 클래스 설명을 채운다."""
    root = cfg.source_root.resolve()
    # 빌드에 들어간 파일만 본다: compile DB 의 translation unit 과 이미 사실에 오른 선언 파일.
    files: set[Path] = set()
    for entry in entries:
        source = Path(str(entry.get("file", "")))
        files.add(source if source.is_absolute() else Path(str(entry.get("directory", "."))) / source)
    for info in model.classes.values():
        if info.loc:
            files.add(root / info.loc.file)

    stats = {"files": 0, "blocks": 0, "filled": 0, "ambiguous": 0, "unknown": 0}
    for path in sorted(files):
        rel = relpath(str(path), root)
        if any(x.fullmatch(rel) for x in _EXCLUDES) or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        stats["files"] += 1
        for name, brief in blocks(text):
            stats["blocks"] += 1
            target = resolve(name, model, near=str(PurePosixPath(rel).parent))
            if target is None:
                tail = name.rsplit("::", 1)[-1]
                key = "ambiguous" if any(n.rsplit("::", 1)[-1] == tail for n in model.classes) else "unknown"
                stats[key] += 1
                continue
            # 선언에 붙은 주석이 이미 있으면 그것이 더 가깝다. 덮어쓰지 않는다.
            if model.classes[target].brief:
                continue
            model.classes[target].brief = brief
            stats["filled"] += 1
    return stats
