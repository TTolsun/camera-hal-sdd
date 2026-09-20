"""증분 생성 뒤, 영향 밖 원고의 근거를 새 facts 로 재검증해 커밋 기준을 이월한다.

사이트 빌드는 facts 와 모든 원고의 source_commit 이 같아야 게시한다. 전체 재생성으로
기준을 맞추면 소형 모델이 감당하지 못하므로, 영향이 없던 원고는 LLM 을 부르지 않고
기존 본문의 `파일:줄` 인용이 새 facts 에도 전부 있는지 확인한 뒤 source_commit 만
승격한다. 인용이 하나라도 어긋나면 승격하지 않고 재생성 대상으로 보고한다. 조용히
통과시키지 않는다는 DESIGN.md 6번 계약을 따른다.
"""

from __future__ import annotations

import re
from pathlib import Path

from .config import Config
from .facts.model import KnowledgeModel
from .validate import extract_citations

_FM = re.compile(r"^---\n(.*?)\n---\n", re.S)


def _meta(frontmatter: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in frontmatter.splitlines():
        if line[:1].isspace() or ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip()
    return out


def carry_forward(cfg: Config, model: KnowledgeModel,
                  written: list[Path]) -> tuple[list[Path], list[tuple[Path, list[str]]]]:
    """이번에 생성하지 않은 파이프라인 소유 페이지를 재검증한다.

    반환: (승격한 페이지, [(승격하지 못한 페이지, 새 facts 에 없는 인용)]).
    수동 페이지(kind: manual)와 파이프라인 frontmatter 가 없는 파일은 건드리지 않는다."""
    new_commit = str(model.meta.get("source_commit", ""))
    promoted: list[Path] = []
    stale: list[tuple[Path, list[str]]] = []
    if not new_commit:
        return promoted, stale

    done = {p.resolve() for p in written}
    allowed = model.citations()
    for path in sorted(cfg.sdd_dir.rglob("*.md")):
        if path.resolve() in done:
            continue
        text = path.read_text(encoding="utf-8")
        m = _FM.match(text)
        if not m:
            continue
        meta = _meta(m.group(1))
        # 생성 페이지의 표식은 source_commit + agent 다. 수동 문서는 사람이 재검토한다.
        if meta.get("kind") == "manual" or "source_commit" not in meta or "agent" not in meta:
            continue
        old_commit = meta.get("source_commit", "")
        if old_commit == new_commit:
            continue

        body = text[m.end():]
        invalid = sorted({c for c in extract_citations(body) if c not in allowed})
        if invalid:
            stale.append((path, invalid))
            continue

        fm = re.sub(r"^source_commit:.*$", f"source_commit: {new_commit}", m.group(1), count=1, flags=re.M)
        fm = re.sub(r"^revalidated_from:.*\n?", "", fm, flags=re.M).rstrip()
        if old_commit:
            fm += f"\nrevalidated_from: {old_commit}"
        path.write_text(f"---\n{fm}\n---\n{body}", encoding="utf-8", newline="\n")
        promoted.append(path)
    return promoted, stale
