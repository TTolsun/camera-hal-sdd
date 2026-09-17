"""Feature flag 사실: compile DB 의 -D 목록과 소스에서의 #if 사용 위치.

정적 분석 도구 없이 전처리 지시문만 훑는다. 값 해석은 하지 않고 "어디서 분기하는가" 만 기록한다.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .. import compdb
from ..config import Config
from .model import Define, KnowledgeModel, Location, relpath

_SRC_SUFFIXES = {".c", ".cc", ".cpp", ".h", ".hpp"}
_SKIP_DIRS = {"test", "tests", "toolchains", "sysroot", ".git", "build", "obj", "libs"}
_PP_LINE = re.compile(r"^\s*#\s*(if|ifdef|ifndef|elif)\b(.*)$")
_MAX_USAGES_PER_DEFINE = 20


def _source_files(root: Path):
    for p in root.rglob("*"):
        if p.suffix.lower() not in _SRC_SUFFIXES:
            continue
        if any(part in _SKIP_DIRS for part in p.relative_to(root).parts[:-1]):
            continue
        yield p


def collect(model: KnowledgeModel, cfg: Config, entries: list[dict[str, Any]]) -> None:
    names = compdb.defines(entries)
    for name, value in names.items():
        model.defines.setdefault(name, Define(name=name, value=value))
    if not model.defines:
        return

    # 한 번의 정규식으로 모든 플래그 이름을 찾는다. 이름이 긴 것부터 넣어 부분 일치를 막는다.
    pattern = re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(model.defines, key=len, reverse=True)) + r")\b")
    for src in _source_files(cfg.source_root):
        try:
            lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        rel = relpath(str(src), cfg.source_root)
        for i, line in enumerate(lines, start=1):
            m = _PP_LINE.match(line)
            if not m:
                continue
            for hit in set(pattern.findall(m.group(2))):
                d = model.defines[hit]
                if len(d.usages) < _MAX_USAGES_PER_DEFINE:
                    d.usages.append(Location(file=rel, line=i))
