"""소형 모델(Qwen 4B, Hermes)용 입력 예산.

토크나이저에 의존하지 않고 문자 수로 관리한다. 초과하면 우선순위가 낮은 블록부터 통째로 뺀다.
블록 중간을 자르지 않는다. 잘린 사실은 문서에 없는 것과 같으므로, 무엇을 뺐는지 목록으로 돌려준다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Block:
    label: str        # 제외됐을 때 frontmatter 에 남길 이름
    text: str
    priority: int     # 낮을수록 중요 (0 = 절대 제외하지 않음)


def fit(blocks: list[Block], max_chars: int, reserved: int = 0) -> tuple[str, list[str]]:
    """블록을 우선순위 순으로 담고, 예산을 넘기면 가장 덜 중요한 것부터 뺀다.

    reserved: 프롬프트 템플릿, system 메시지 등 사실 블록 외에 이미 쓰인 문자 수.
    """
    budget = max(0, max_chars - reserved)
    kept = sorted(blocks, key=lambda b: b.priority)
    omitted: list[str] = []
    total = sum(len(b.text) + 2 for b in kept)
    while total > budget and kept:
        idx = max(range(len(kept)), key=lambda i: kept[i].priority)
        if kept[idx].priority == 0:
            break
        removed = kept.pop(idx)
        omitted.append(removed.label)
        total -= len(removed.text) + 2
    # 원래 순서(우선순위 순)를 유지해서 붙인다.
    return "\n\n".join(b.text for b in kept), omitted
