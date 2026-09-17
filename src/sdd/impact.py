"""변경 영향 매핑: git diff -> 변경 파일/심볼 -> 재생성할 SDD 섹션과 시나리오.

두 단계로 잡는다.
1. 경로 규칙: sections.yaml 의 watch glob 에 변경 파일이 걸리면 그 섹션.
2. 심볼 규칙: 변경 파일에 정의된 클래스가 속한 패키지, 변경 파일을 지나는 시나리오.
"""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import Config
from .facts.model import KnowledgeModel


@dataclass
class ImpactReport:
    base: str
    head: str
    changed_files: list[str] = field(default_factory=list)
    changed_classes: list[str] = field(default_factory=list)
    sections: dict[str, list[str]] = field(default_factory=dict)     # section id -> 이유
    scenarios: dict[str, list[str]] = field(default_factory=dict)    # scenario id -> 이유
    packages: list[str] = field(default_factory=list)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")

    @classmethod
    def load(cls, path: Path) -> "ImpactReport":
        return cls(**json.loads(path.read_text(encoding="utf-8")))


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """`**/` 는 0개 이상의 디렉터리, `*` 는 슬래시를 넘지 않는 glob 을 정규식으로 바꾼다."""
    out = ""
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
            continue
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
            continue
        if c == "*":
            out += "[^/]*"
        elif c == "?":
            out += "[^/]"
        else:
            out += re.escape(c)
        i += 1
    return re.compile("^" + out + "$")


def match_any(path: str, globs: list[str]) -> bool:
    return any(glob_to_regex(g).match(path) for g in globs)


def changed_files(source_root: Path, base: str, head: str = "HEAD") -> list[str]:
    # --relative: 소스 루트가 저장소의 하위 디렉터리여도 facts 의 file 과 같은 기준(소스 루트 상대)이 된다.
    res = subprocess.run(["git", "diff", "--name-only", "--relative", f"{base}..{head}"], cwd=source_root,
                         check=True, capture_output=True, text=True)
    return [line.strip().replace("\\", "/") for line in res.stdout.splitlines() if line.strip()]


def compute(cfg: Config, model: KnowledgeModel, files: list[str], base: str, head: str) -> ImpactReport:
    report = ImpactReport(base=base, head=head, changed_files=files)
    fileset = set(files)
    sections = cfg.sections()

    # 1. 경로 규칙
    for sec in sections:
        hits = [f for f in files if match_any(f, sec.get("watch", []) or [])]
        if hits:
            report.sections.setdefault(sec["id"], []).append(f"watch 일치: {', '.join(hits[:5])}")

    # 2. 심볼 규칙
    changed_classes = model.classes_in_files(fileset)
    report.changed_classes = sorted(c.name for c in changed_classes)
    report.packages = sorted({c.package for c in changed_classes if c.package})
    for sec in sections:
        facts = sec.get("facts", {})
        # impact_classes 가 있으면 그것을, 없으면 classes 를 쓴다 (개요처럼 인용용으로만 클래스를 넘기는 절 대응).
        patterns = facts.get("impact_classes", facts.get("classes")) or []
        if not patterns:
            continue
        hit = [c.name for c in changed_classes if any(fnmatch.fnmatch(c.name, p) for p in patterns)]
        if hit:
            report.sections.setdefault(sec["id"], []).append(f"클래스 변경: {', '.join(hit[:5])}")

    for sc in model.scenarios_touching(fileset):
        report.scenarios.setdefault(sc.id, []).append("시나리오 경로에 포함된 파일이 변경됨")
    if report.scenarios:
        report.sections.setdefault("scenarios", []).append(f"영향 시나리오: {', '.join(sorted(report.scenarios))}")

    # 3. 사람이 쓰는 문서: frontmatter 의 evidence_files 가 바뀌면 재검토 대상으로 올린다 (재생성은 하지 않는다).
    for sec in sections:
        if sec.get("kind") != "manual":
            continue
        evidence = manual_evidence_files(cfg.sdd_dir / sec.get("output", f"{sec['id']}.md"))
        hit = sorted(f for f in evidence if f in fileset or any(match_any(f, [c]) for c in files))
        if hit:
            report.sections.setdefault(sec["id"], []).append(f"수동 문서의 근거 파일 변경: {', '.join(hit[:5])} (사람이 재검토)")

    return report


def manual_evidence_files(path: Path) -> list[str]:
    """manual 문서 frontmatter 의 evidence_files 목록. 없으면 빈 목록."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return []
    try:
        import yaml
        data = yaml.safe_load(m.group(1)) or {}
    except Exception:
        return []
    return [str(f).replace("\\", "/") for f in (data.get("evidence_files") or [])]


def summary_facts(report: ImpactReport, model: KnowledgeModel) -> str:
    """change_impact 프롬프트에 넣을 사실 블록."""
    lines = [f"- 비교 범위: {report.base}..{report.head}", f"- 변경 파일 {len(report.changed_files)} 개:"]
    lines += [f"  - {f}" for f in report.changed_files[:30]]
    if report.changed_classes:
        lines.append("- 변경된 파일에 정의된 클래스:")
        for name in report.changed_classes[:30]:
            c = model.classes[name]
            lines.append(f"  - {name} ({c.loc.cite() if c.loc else '위치 없음'})")
    if report.scenarios:
        lines.append("- 영향 받는 시나리오: " + ", ".join(sorted(report.scenarios)))
    lines.append("- 재생성된 SDD 섹션: " + ", ".join(sorted(report.sections)) if report.sections else "- 재생성된 섹션 없음")
    return "\n".join(lines)
