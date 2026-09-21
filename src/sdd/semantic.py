"""Conservative structural checks, not a general natural-language truth oracle."""
from __future__ import annotations

import re

from .facts.model import KnowledgeModel
from .validate import extract_citations


def review(text: str, model: KnowledgeModel, supplied: set[str]) -> list[str]:
    findings = []
    # A declared base may be a typedef/alias without its own ClassInfo.
    known = set(model.classes) | {b for c in model.classes.values() for b in c.bases}
    known |= {n for r in model.relations for n in (r.source, r.target)}
    def resolve(name: str) -> str | None:
        candidates = [n for n in known if n == name or ('::' not in name and n.rsplit('::', 1)[-1] == name)]
        return candidates[0] if len(candidates) == 1 else None
    for paragraph in re.split(r"\n\s*\n", text):
        if not paragraph.strip():
            continue
        citations = set(extract_citations(paragraph))
        if not citations:
            findings.append("설명 문단에 근거 인용이 없습니다.")
        elif citations - supplied:
            findings.append("현재 설명 입력에 제공되지 않은 위치를 인용했습니다: " + ", ".join(sorted(citations - supplied)))
    for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
        names = re.findall(r"`([\w:]+)`", sentence)
        resolved = []
        for name in names:
            candidate = resolve(name)
            tail = sentence.split(f'`{name}`', 1)[1].split('`', 1)[0]
            absence = bool(re.search(r"존재하지 않|추출되지 않|포함되지 않|포함되어 있지 않", tail))
            if absence and candidate:
                findings.append(f"현재 facts에 있는 클래스를 없다고 서술했습니다: {name}")
            if "::" in name and not candidate and name not in model.functions:
                # Qualified methods and enumerators may not be class entities.
                owner = name.rsplit("::", 1)[0]
                if not absence and not any(n == owner or n.rsplit('::', 1)[-1] == owner for n in model.classes):
                    findings.append(f"추출 사실에서 확인되지 않는 한정 이름: {name}")
            if candidate:
                resolved.append(candidate)
        if "상속" in sentence and not re.search(r"없|않|아니|확인 필요|미확인", sentence):
            # Only bind an explicit subject/base phrase. A sentence can discuss
            # several independent relationships; its first name is not necessarily
            # the subject of the inheritance clause.
            pair = re.search(r'`([\w:]+)`\s*(?:은|는|이|가)\s*`([\w:]+)`\s*(?:을|를)\s*(?:직접\s*)?상속', sentence)
            subjects = resolved if len(resolved) == 1 or re.search(r'모두|이들도|둘 다', sentence) else []
            if pair:
                source, target = resolve(pair[1]), resolve(pair[2])
                subjects = [source] if source else []
                if source in model.classes and target and target not in model.classes[source].bases:
                    findings.append(f"추출되지 않은 직접 상속: {source} → {target}")
            for name in subjects:
                if name in model.classes and not model.classes[name].bases:
                    findings.append(f"추출된 기반 클래스가 없는 {name}에 상속을 주장했습니다.")
        if "필드 참조" in sentence and len(resolved) == 2 and not re.search(r"없|않|아니|확인 필요", sentence):
            if not any(r.source == resolved[0] and r.target == resolved[1] and r.type == "association" for r in model.relations):
                findings.append(f"추출되지 않은 필드 참조: {resolved[0]} → {resolved[1]}")
    return list(dict.fromkeys(findings))


def relation_facts(model: KnowledgeModel, names: set[str]) -> str:
    rows = ["직접 상속과 관계는 아래 추출 결과만 사용합니다. 관계가 없다는 사실은 실행 동작의 부재를 증명하지 않습니다."]
    for name in sorted(names):
        c = model.classes[name]
        cite = f" `{c.loc.cite()}`" if c.loc else ""
        rows.append(f"{name}: 직접 기반 클래스 = {', '.join(c.bases) or '(없음)'}{cite}")
    for source, target, kind in sorted({(r.source, r.target, r.type) for r in model.relations if r.source in names}):
        c = model.classes[source]
        cite = f" `{c.loc.cite()}`" if c.loc else ""
        rows.append(f"{source} → {target}: {kind}{cite}")
    return "\n".join(rows)


def structural_text(model: KnowledgeModel, names: set[str]) -> str:
    """Render structural assertions directly, without generative paraphrasing."""
    labels = {'association': '필드 참조', 'aggregation': '집합', 'composition': '합성', 'dependency': '의존'}
    paragraphs = []
    for name in sorted(names):
        cls = model.classes[name]
        citation = f" `{cls.loc.cite()}`" if cls.loc else ''
        bases = ', '.join(f'`{b}`' for b in cls.bases)
        text = (f'`{name}`의 추출된 직접 기반 클래스는 {bases}입니다.' if bases else
                f'`{name}`에는 추출된 직접 기반 클래스가 없습니다.')
        for target, kind in sorted({(r.target, r.type) for r in model.relations
                                   if r.source == name and r.target in names and r.type in labels}):
            text += f' `{target}`에 대한 {labels[kind]} 관계가 추출되었습니다.'
        if not cls.loc:
            text += ' 확인 필요: 선언 위치가 없습니다.'
        paragraphs.append(text + citation)
    return '\n\n'.join(paragraphs)
