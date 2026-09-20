from pathlib import Path

from sdd.budget import Block
from sdd.generate import Generator, compose_system_prompt, slugify
from sdd.impact import compute
from sdd.llm import Agent


class _FakeAgent:
    """정해진 답을 차례로 돌려주는 LLM 대역. 마지막 답을 반복한다."""

    def __init__(self, replies: list[str]):
        self.replies = replies
        self.users: list[str] = []

    def chat(self, system: str, user: str, tag: str = "") -> str:
        self.users.append(user)
        return self.replies[min(len(self.users) - 1, len(self.replies) - 1)]


_GOOD = ("`CameraDevice` 는 카메라마다 하나씩 만들어집니다 `device/CameraDevice.h:40`. "
         "스트림 구성은 `configureStreams()` 가 담당합니다 `device/CameraDevice.cpp:120`.")
_BAD = _GOOD.replace("담당합니다", "담당한다")


def _ask(tmp_cfg, sample_model, replies):
    tmp_cfg.agent.kind = "fake"
    agent = _FakeAgent(replies)
    gen = Generator(tmp_cfg, sample_model, agent)
    sec = {"id": "t", "title": "테스트"}
    blocks = [Block("core", "class CameraDevice `device/CameraDevice.h:40`", 0)]
    text, _, verdict = gen._ask("t", sec, "테스트", blocks, "")
    return text, verdict, agent


def test_slugify_keeps_korean_like_pymdownx():
    assert slugify("패키지별 역할") == "패키지별-역할"
    assert slugify("HAL 진입점") == "hal-진입점"
    assert slugify("코드를 처음 읽는 순서") == "코드를-처음-읽는-순서"


def test_system_prompt_includes_style_readme_only_by_default(tmp_cfg):
    system = compose_system_prompt(tmp_cfg)
    assert "개발자 가이드 집필 규칙:" in system and "1. 각 페이지는 독자가 먼저 할 일이나" in system
    assert "brief.mjs" not in system                          # README 의 설명 문단은 넣지 않는다
    assert "Lead with the next action" not in system       # i-have-adhd 원문은 기본 제외
    tmp_cfg.agent.full_style_guides = True
    assert "Lead with the next action" in compose_system_prompt(tmp_cfg)


def test_dry_run_generates_all_pages_with_frame(tmp_cfg, sample_model):
    agent = Agent(tmp_cfg.agent, dump_dir=tmp_cfg.build_dir / "prompts")
    written = Generator(tmp_cfg, sample_model, agent).run()
    names = sorted(p.relative_to(tmp_cfg.sdd_dir).as_posix() for p in written)
    assert names == ["components.md", "feature-flags.md", "overview.md",
                     "scenarios/index.md", "scenarios/process_capture_request.md", "threading.md"]

    overview = (tmp_cfg.sdd_dir / "overview.md").read_text(encoding="utf-8")
    # 페이지 뼈대: lead(굵게) -> 확인할 내용 표 -> 본문 -> 근거 -> 다음 단계
    assert overview.index("**수정할 기능이") < overview.index("| 지금 확인할 내용 | 이동할 절 |")
    assert "## 패키지별 역할" in overview and "| `device` | 1 |" in overview
    assert "## 코드를 처음 읽는 순서" in overview
    assert "1. `device/CameraDevice.cpp` 에서 `createFrame()` 부분을 읽습니다." in overview
    assert '??? note "근거와 검토 정보"' in overview
    assert "- 근거 파일: `device/CameraDevice.cpp`" in overview
    assert overview.rstrip().endswith("다음 단계: [컴포넌트 구조와 책임](components.md)")

    components = (tmp_cfg.sdd_dir / "components.md").read_text(encoding="utf-8")
    assert "## device" in components and "## pipeline" in components
    assert "| `CameraDevice` | `device/CameraDevice.h:40` | – | HAL3 디바이스 진입점 |" in components
    assert "| `PipeThread` | `pipeline/PipeThread.h:8` | `Thread` | 확인 필요 |" in components
    assert "| device 패키지의 클래스를 수정합니다. | [device](#device) |" in components
    assert '??? note "근거와 검토 정보: pipeline"' in components

    flags = (tmp_cfg.sdd_dir / "feature-flags.md").read_text(encoding="utf-8")
    assert "| `USE_SAT` | `1` | `device/CameraDevice.cpp:310` |" in flags
    assert "status: ok" in flags            # table 종류는 LLM 을 안 거치므로 바로 ok

    scen = (tmp_cfg.sdd_dir / "scenarios/process_capture_request.md").read_text(encoding="utf-8")
    assert "```mermaid" in scen
    assert "1. `CameraDevice` 가 `FrameFactory::createFrame()` 를 호출합니다. `device/CameraDevice.cpp:305`" in scen
    assert "status: needs-review" in scen   # dry-run 출력은 사람이 봐야 한다
    assert "다음 단계: [핵심 시나리오 목록](index.md)" in scen   # scenarios/ 안에서는 index.md 가 같은 디렉터리

    index = (tmp_cfg.sdd_dir / "scenarios/index.md").read_text(encoding="utf-8")
    assert "| [캡처 요청 처리](process_capture_request.md) |" in index

    threading = (tmp_cfg.sdd_dir / "threading.md").read_text(encoding="utf-8")
    assert "needs_human: true" in threading and "PipeThread" in threading

    prompts = sorted((tmp_cfg.build_dir / "prompts").glob("*.md"))
    assert prompts, "dry-run 은 프롬프트를 기록해야 한다"
    body = prompts[0].read_text(encoding="utf-8")
    assert "개발자 가이드 집필 규칙" in body and "사실 (이 목록 밖의 내용은 쓰지 않습니다):" in body


def test_lint_finding_triggers_retry_with_reason(tmp_cfg, sample_model):
    text, verdict, agent = _ask(tmp_cfg, sample_model, [_BAD, _GOOD])
    assert verdict.ok and "담당합니다" in text
    assert len(agent.users) == 2
    # 재요청 프롬프트에 반려 사유가 들어간다.
    assert "[종결어미]" in agent.users[1] and "이전 출력의 문제" in agent.users[1]


def test_lint_finding_survives_retries_as_needs_review(tmp_cfg, sample_model):
    _, verdict, agent = _ask(tmp_cfg, sample_model, [_BAD])
    assert not verdict.ok
    assert len(agent.users) == tmp_cfg.max_retries + 1
    assert any("[종결어미]" in n for n in verdict.notes)


def test_fence_wrapped_reply_is_unwrapped_before_checks(tmp_cfg, sample_model):
    text, verdict, agent = _ask(tmp_cfg, sample_model, [f"```markdown\n{_GOOD}\n```"])
    assert verdict.ok and len(agent.users) == 1
    assert "```" not in text


def test_impact_limits_regeneration(tmp_cfg, sample_model):
    agent = Agent(tmp_cfg.agent)
    report = compute(tmp_cfg, sample_model, ["pipeline/PipeThread.h"], base="a", head="b")
    written = Generator(tmp_cfg, sample_model, agent).run(impact=report)
    names = {p.name for p in written}
    assert "threading.md" in names and "overview.md" in names
    assert "process_capture_request.md" not in names


def test_manual_page_evidence_files_flagged(tmp_cfg, sample_model):
    page = tmp_cfg.sdd_dir / "constraints.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("---\nstatus: ok\nkind: manual\nevidence_files:\n  - device/CameraDevice.cpp\n---\n\n# 제약\n",
                    encoding="utf-8")
    report = compute(tmp_cfg, sample_model, ["device/CameraDevice.cpp"], base="a", head="b")
    assert "constraints" in report.sections
    assert any("재검토" in r for r in report.sections["constraints"])
    # manual 은 재생성 대상이 아니다.
    written = Generator(tmp_cfg, sample_model, Agent(tmp_cfg.agent)).run(impact=report)
    assert all(Path(p).name != "constraints.md" for p in written)
