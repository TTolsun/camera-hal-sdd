from sdd.budget import Block, fit
from sdd.validate import check, extract_citations


def test_fit_drops_lowest_priority_whole_blocks_first():
    blocks = [Block("core", "a" * 100, 0), Block("mid", "b" * 100, 1), Block("low", "c" * 100, 2)]
    text, omitted = fit(blocks, max_chars=250)
    assert omitted == ["low"]
    assert "c" not in text and "a" in text and "b" in text


def test_fit_never_drops_priority_zero():
    blocks = [Block("core", "a" * 500, 0), Block("low", "c" * 10, 2)]
    text, omitted = fit(blocks, max_chars=100)
    assert omitted == ["low"]
    assert text == "a" * 500


def test_citations_are_extracted_and_validated():
    allowed = {"device/CameraDevice.cpp:120", "pipeline/FrameFactory.cpp:1240"}
    text = ("CameraDevice 클래스는 스트림을 구성합니다 `device/CameraDevice.cpp:120`.\n\n"
            "FrameFactory 가 프레임을 만듭니다 `pipeline/FrameFactory.cpp:1240`.")
    assert extract_citations(text) == ["device/CameraDevice.cpp:120", "pipeline/FrameFactory.cpp:1240"]
    assert check(text, allowed).ok


def test_unknown_citation_fails():
    v = check("이 함수는 `device/Nope.cpp:1` 에 있습니다.", {"device/CameraDevice.cpp:120"})
    assert not v.ok
    assert v.invalid == ["device/Nope.cpp:1"]


def test_missing_citation_fails_when_required():
    v = check("클래스 설명만 있고 인용이 없습니다.", {"x.cpp:1"}, require=True)
    assert not v.ok
    assert v.uncited_paragraphs == 1


def test_normalize_citations_restores_directory_when_unique():
    from sdd.validate import normalize_citations, strip_headings
    allowed = {"module/CameraModule.cpp:17", "device/CameraDevice.cpp:44", "pipeline/Pipe.cpp:44"}
    text = "진입점은 `CameraModule.cpp:17` 에 있습니다. 애매한 `Pipe.cpp:44` 와 `CameraDevice.cpp:44`."
    out = normalize_citations(text, allowed)
    assert "`module/CameraModule.cpp:17`" in out
    assert "`device/CameraDevice.cpp:44`" in out
    assert "`pipeline/Pipe.cpp:44`" in out
    # 같은 basename 이 둘이면 손대지 않는다.
    allowed2 = allowed | {"other/Pipe.cpp:44"}
    assert "`Pipe.cpp:44`" in normalize_citations("`Pipe.cpp:44`", allowed2)
    assert strip_headings("# 제목\n\n본문입니다.\n## 소제목\n둘째 문단.") == "본문입니다.\n둘째 문단."


def test_strip_echo_removes_prompt_lines_but_keeps_new_prose():
    from sdd.validate import strip_echo, check
    prompt = "사실:\n- class halcam::CameraDevice `device/CameraDevice.h:10` -- HAL3 device object.\n| 클래스 | 선언 위치 |\n|---|---|"
    out = "- class halcam::CameraDevice `device/CameraDevice.h:10` -- HAL3 device object.\n\n`CameraDevice` 는 카메라마다 하나씩 만들어집니다 `device/CameraDevice.h:10`."
    assert strip_echo(out, prompt) == "`CameraDevice` 는 카메라마다 하나씩 만들어집니다 `device/CameraDevice.h:10`."
    v = check("| 클래스 | 위치 |\n|---|---|\n| a | `x.cpp:1` |", {"x.cpp:1"})
    assert not v.ok and any("표를 출력" in n for n in v.notes)
