"""Conservative documentation-scope audit; watch hits are not content coverage."""

from __future__ import annotations

import fnmatch
from typing import TYPE_CHECKING

from .config import Config
from .facts.model import KnowledgeModel

if TYPE_CHECKING:
    from .impact import ImpactReport


def _matches(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(name.rsplit("::", 1)[-1], p) for p in patterns)


def audit(cfg: Config, model: KnowledgeModel, files: list[str],
          base_model: KnowledgeModel | None = None, *, impacted_sections: set[str]) -> dict:
    from .impact import manual_evidence_files, match_any

    sections = cfg.sections()
    ignored = sorted(f for f in set(files) if match_any(f, cfg.exclude))
    active = set(files) - set(ignored)
    # Inspect both sides so deleted declarations and renamed paths cannot disappear.
    entities: dict[tuple[str, str], dict] = {}
    for side, snapshot in [("base", base_model), ("head", model)]:
        if snapshot is None:
            continue
        for kind, collection in [("class", snapshot.classes), ("function", snapshot.functions)]:
            for name, entity in collection.items():
                if kind == "class":
                    locations = [entity.loc] + [loc for method in entity.methods for loc in (method.loc, method.def_loc)]
                else:
                    locations = [entity.loc, entity.def_loc]
                locations = [loc for loc in locations if loc and loc.file in active]
                if not locations:
                    continue
                item = entities.setdefault((kind, name), {"kind": kind, "name": name, "files": set(),
                                                          "evidence": {}, "sections": set()})
                item["files"].update(loc.file for loc in locations)
                item["evidence"][side] = sorted({loc.cite() for loc in locations})
                for section in sections:
                    section_kind = section.get("kind", "prose")
                    facts = section.get("facts", {})
                    selected = False
                    if kind == "class" and section_kind in ("prose", "per-package"):
                        selected = _matches(name, facts.get("classes") or [])
                        if section_kind == "per-package":
                            selected = selected and any(name in p.classes for p in snapshot.packages.values())
                    elif kind == "function" and section_kind == "prose":
                        selected = _matches(name, facts.get("functions") or [])
                    if selected:
                        item["sections"].add(section["id"])

    items = []
    findings = []
    for key in sorted(entities):
        item = entities[key]
        item["files"] = sorted(item["files"])
        item["sections"] = sorted(item["sections"])
        reason = ("entity-outside-document-scope" if not item["sections"] else
                  "document-not-scheduled" if not impacted_sections.intersection(item["sections"]) else None)
        item["status"] = "needs-review" if reason else "mapped"
        items.append(item)
        if reason:
            findings.append({"reason": reason, "kind": item["kind"],
                             "name": item["name"], "files": item["files"]})

    file_items = []
    for file in sorted(active):
        watch = sorted(s["id"] for s in sections if match_any(file, s.get("watch") or []))
        manual = sorted(s["id"] for s in sections if s.get("kind") == "manual"
                        and file in manual_evidence_files(cfg.sdd_dir / s.get("output", f"{s['id']}.md")))
        related = [item for item in items if file in item["files"]]
        if not related:
            # Build scripts, unparsed sources and deleted files without baseline facts
            # require review even when a broad watch rule selects a document.
            findings.append({"reason": "no-extracted-entity", "kind": "file", "name": file, "files": [file]})
        file_items.append({"file": file, "watch_sections": watch, "manual_review_sections": manual,
                           "status": "needs-review" if not related or any(i["status"] == "needs-review" for i in related) else "mapped"})
    return {"schema": 1, "status": "needs-review" if findings else "mapped",
            "baseline_available": base_model is not None, "ignored_files": ignored,
            "files": file_items, "entities": items, "findings": findings,
            "limitations": ["File-level scope mapping does not prove changed-line coverage, generated prose accuracy or human approval.",
                            "Without baseline facts, removed entities in surviving files may be missed.",
                            "A watch hit, package summary or scenario call is not class/function documentation coverage."]}


def review_markdown(report: ImpactReport) -> str:
    coverage = report.coverage
    lines = ["# 변경 문서 범위 검토", "", f"비교 범위: `{report.base}..{report.head}`", ""]
    if not coverage:
        return "\n".join(lines + ["범위 검사가 없는 이전 영향 보고서입니다. impact를 다시 실행하세요.", ""])
    lines += [f"상태: **{coverage['status']}** · 검토 항목 {len(coverage['findings'])}개", "",
              "이 결과는 설정상 문서 범위 검사입니다. 문서의 존재·최신성·설명 정확성이나 사람의 승인을 보장하지 않습니다.", "",
              "## 검토할 변경", ""]
    labels = {"entity-outside-document-scope": "클래스·함수를 선택하는 문서가 없습니다",
              "document-not-scheduled": "대응 문서는 있지만 재생성 대상으로 선택되지 않았습니다",
              "no-extracted-entity": "추출한 클래스·함수와 연결되지 않아 범위를 확인할 수 없습니다"}
    for item in coverage["findings"]:
        lines += [f"- `{item['name']}`: {labels[item['reason']]}.",
                  "  근거 파일: " + ", ".join(f"`{f}`" for f in item["files"]) + "."]
    if not coverage["findings"]:
        lines.append("현재 추출 사실과 설정에서 범위 누락을 찾지 못했습니다.")
    lines += ["", "## 파일 감시와 수동 검토 연결", ""]
    for item in coverage["files"]:
        lines.append(f"- `{item['file']}`: {item['status']}; watch={', '.join(item['watch_sections']) or '(없음)'}; "
                     f"수동 검토={', '.join(item['manual_review_sections']) or '(없음)'}")
    lines += ["", "## 검사 한계", "",
              "- 변경 파일 안의 선언·정의 위치를 사용합니다. 줄별 변경이나 LLM 입력 예산에 따른 생략은 별도 검증이 필요합니다.",
              "- watch 일치만으로 누락이 해결되지는 않습니다. facts.classes/functions 범위를 보완하거나 검토자가 범위 밖 변경인지 판단해야 합니다.",
              "- 빌드 파일과 추출되지 않은 코드는 검토 대상으로 남습니다. 수동 문서의 근거 연결은 검토 위치만 안내합니다."]
    if not coverage["baseline_available"]:
        lines.append("- 이전 facts가 없어 삭제된 심볼을 완전히 검사하지 못했습니다. --base-facts로 비교 기준의 facts를 제공하세요.")
    if coverage["ignored_files"]:
        lines += ["", "source.exclude로 제외한 파일: " + ", ".join(f"`{f}`" for f in coverage["ignored_files"])]
    return "\n".join(lines) + "\n"
