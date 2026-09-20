from sdd.manuscript import describe, lint, unwrap


def test_clean_manuscript_passes():
    body = ("`CameraDevice` 는 카메라마다 하나씩 만들어집니다 `device/CameraDevice.h:40`.\n\n"
            "1. `configureStreams()` 를 먼저 읽습니다.\n\n"
            "| 클래스 | 위치 |\n|---|---|\n| `CameraDevice` | `device/CameraDevice.h:40` |")
    assert lint(body) == []


def test_plain_sentence_endings_are_rejected():
    findings = lint("스트림 구성은 `configureStreams()` 가 담당한다 `device/CameraDevice.cpp:120`.")
    assert [f.rule for f in findings] == ["종결어미"]
    assert lint("버퍼 소유자는 확인이 필요함")[0].rule == "종결어미"
    # 인용이 문장 끝에 붙어도 "~합니다" 는 통과한다.
    assert lint("버퍼를 소유합니다 `device/CameraDevice.h:12`.") == []


def test_headings_and_tables_skip_sentence_rules():
    assert lint("## 스레드 모델 요약이다") == []
    assert lint("| 값 없음 | 확인 필요함 |") == []


def test_fenced_code_lines_are_skipped():
    assert lint("```cpp\nint run() { return 0; } // 실행한다\n```\n본문은 여기서 끝납니다.") == []


def test_unterminated_fence_is_itself_a_finding():
    findings = lint("```cpp\nint run();\n펜스가 닫히지 않은 채 본문이 이어진다")
    assert [f.rule for f in findings] == ["닫히지 않은 코드 펜스"]
    assert findings[0].line == 1


def test_dialogue_and_prompt_leak_are_rejected():
    assert [f.rule for f in lint("이 원고는 다음 절에서 검토를 요청합니다.")] == ["대화체·작업 보고"]
    assert [f.rule for f in lint("제공된 코드에서 콜백 등록을 확인했습니다.")] == ["원고·근거 언급"]


def test_paths_and_json_residue_are_rejected():
    assert [f.rule for f in lint("자세한 내용은 file://server/doc 에 있습니다.")] == ["절대 경로·줄 번호 링크"]
    assert [f.rule for f in lint("구현은 CameraDevice.cpp#L12 에 있습니다.")] == ["절대 경로·줄 번호 링크"]
    assert [f.rule for f in lint('스레드 설명입니다."}')] == ["JSON 잔여물"]
    assert [f.rule for f in lint("첫 줄\\n둘째 줄입니다.")] == ["JSON 잔여물"]
    # 인라인 코드 안의 \n 과 상대 경로 인용은 위반이 아니다.
    assert lint("`a\\nb` 는 이스케이프 예시입니다 `device/CameraDevice.h:12`.") == []


def test_bold_line_heading_is_rejected():
    assert [f.rule for f in lint("**스레드 모델**")] == ["굵은 글씨 제목"]
    assert lint("**중요:** 이 함수는 잠금을 잡지 않습니다.") == []


def test_unwrap_removes_outer_fence_only():
    inner = "본문입니다.\n\n```mermaid\ngraph TD\n```\n\n끝입니다."
    assert unwrap(f"```markdown\n{inner}\n```") == inner
    assert unwrap("포장 없는 본문입니다.") == "포장 없는 본문입니다."
    assert unwrap("```\n한 줄입니다.\n```") == "한 줄입니다."


def test_describe_makes_one_line_notes():
    notes = describe(lint("스트림 구성은 " + "아주 긴 설명 " * 20 + "함수가 담당한다"))
    assert len(notes) == 1
    assert notes[0].startswith("[종결어미] 1행 ")
    assert "…" in notes[0] and "\n" not in notes[0]
