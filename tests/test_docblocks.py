"""선언에 붙지 않은 문서 주석 블록을 클래스에 연결하는 규칙."""

from pathlib import Path

from sdd.facts import comments, docblocks
from sdd.facts.model import ClassInfo, KnowledgeModel, Location

DOC = """
/**
 * \\file
 * \\brief 파일 설명은 클래스가 아니므로 대상이 아니다
 */

/**
 * \\class Camera
 * \\brief Camera device
 *
 * 본문은 가져오지 않는다.
 */

/**
 * \\struct Request
 * \\brief A frame capture request
 */

/**
 * \\class Nowhere
 * \\brief 사실에 없는 이름
 */
"""


def _model():
    return KnowledgeModel(classes={
        "hal::Camera": ClassInfo("hal::Camera", Location("device/camera.h", 10)),
        "hal::Request": ClassInfo("hal::Request", Location("device/request.h", 5)),
    })


def test_이름이_하나로_정해지면_설명을_채운다():
    model = _model()
    for name, brief in docblocks.blocks(DOC):
        target = docblocks.resolve(name, model)
        if target:
            model.classes[target].brief = brief
    assert model.classes["hal::Camera"].brief == "Camera device"
    assert model.classes["hal::Request"].brief == "A frame capture request"


def test_파일_설명과_사실에_없는_이름은_대상이_아니다():
    model = _model()
    names = [n for n, _ in docblocks.blocks(DOC)]
    assert "Nowhere" in names                      # 블록으로는 읽되
    assert docblocks.resolve("Nowhere", model) is None   # 연결하지는 않는다
    assert not any(n == "file" for n in names)     # \file 은 대상 태그가 아니다


def test_같은_짧은_이름은_같은_디렉터리로_가린다():
    """구현 파일은 자기 옆에 선언된 것을 설명한다."""
    model = KnowledgeModel(classes={
        "hal::ipu3::Context": ClassInfo("hal::ipu3::Context", Location("ipa/ipu3/context.h", 9)),
        "hal::rkisp1::Context": ClassInfo("hal::rkisp1::Context", Location("ipa/rkisp1/context.h", 9)),
    })
    assert docblocks.resolve("Context", model) is None                      # 단서가 없으면 비운다
    assert docblocks.resolve("Context", model, near="ipa/ipu3") == "hal::ipu3::Context"
    assert docblocks.resolve("Context", model, near="ipa/rkisp1") == "hal::rkisp1::Context"
    assert docblocks.resolve("Context", model, near="ipa/uvc") is None      # 어느 쪽도 아니면 비운다


def test_한정_이름은_그대로_찾는다():
    model = _model()
    assert docblocks.resolve("hal::Camera", model) == "hal::Camera"


def test_선언에_붙은_주석을_덮어쓰지_않는다(tmp_path, tmp_cfg):
    src = tmp_path / "src"
    (src / "device").mkdir(parents=True)
    (src / "device" / "camera.cpp").write_text(DOC, encoding="utf-8")
    tmp_cfg.source_root = src
    comments.set_excludes([])
    model = _model()
    model.classes["hal::Camera"].brief = "헤더에 적힌 설명"
    entries = [{"file": str(src / "device" / "camera.cpp"), "directory": str(src)}]
    stats = docblocks.collect(model, tmp_cfg, entries)
    assert model.classes["hal::Camera"].brief == "헤더에 적힌 설명"
    assert model.classes["hal::Request"].brief == "A frame capture request"
    assert stats["filled"] == 1
    assert stats["unknown"] == 1                   # Nowhere


def test_제외한_경로는_읽지_않는다(tmp_path, tmp_cfg):
    src = tmp_path / "src"
    (src / "third_party").mkdir(parents=True)
    (src / "third_party" / "camera.cpp").write_text(DOC, encoding="utf-8")
    tmp_cfg.source_root = src
    comments.set_excludes(["third_party/**"])
    model = _model()
    entries = [{"file": str(src / "third_party" / "camera.cpp"), "directory": str(src)}]
    stats = docblocks.collect(model, tmp_cfg, entries)
    assert stats["files"] == 0 and stats["filled"] == 0
    assert model.classes["hal::Camera"].brief == ""
    comments.set_excludes([])
