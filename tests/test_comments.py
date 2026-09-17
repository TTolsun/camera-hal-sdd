"""libclang 이 실제로 동작하는지, compile DB 플래그 정리가 맞는지 작은 C++ 파일로 확인한다."""

import json

from sdd import compdb
from sdd.facts import comments
from sdd.facts.model import KnowledgeModel

SRC = """
namespace hal {

// 프레임을 만드는 공장. Doxygen 형식이 아닌 일반 주석.
class FrameFactory {
public:
    /// 새 프레임을 만든다.
    int createFrame(int id);
    void destroyFrame();
};

int FrameFactory::createFrame(int id) { return id + 1; }

}  // namespace hal

// HAL 모듈 진입점
int camera_device_open(int id);
int camera_device_open(int id) { return hal::FrameFactory().createFrame(id); }
"""


def test_libclang_extracts_comments_and_locations(tmp_cfg):
    hal = tmp_cfg.source_root
    src = hal / "FrameFactory.cpp"
    src.write_text(SRC, encoding="utf-8")
    entries = [{
        "directory": hal.as_posix(),
        "file": src.as_posix(),
        # NDK 가 만드는 형태를 흉내 낸 플래그. -o / -c / -MMD 는 파싱 전에 제거되어야 한다.
        "command": f"clang++ -std=c++17 -DUSE_SAT -O2 -c -MMD -MF x.d -o x.o {src.as_posix()}",
    }]
    json.dump(entries, (hal / "compile_commands.json").open("w", encoding="utf-8"))

    _, args = comments.parse_args(entries[0])
    assert "-o" not in args and "x.o" not in args and "-c" not in args and "-MMD" not in args
    assert "-DUSE_SAT" in args and "-fparse-all-comments" in args
    assert compdb.defines(entries) == {"USE_SAT": "1"}

    model = KnowledgeModel()
    stats = comments.collect(model, tmp_cfg, entries)
    assert stats["tus"] == 1 and stats["errors"] == 0

    ff = model.classes["hal::FrameFactory"]
    assert ff.loc.file == "FrameFactory.cpp"
    assert "프레임을 만드는 공장" in ff.brief
    create = next(m for m in ff.methods if m.name == "createFrame")
    assert create.brief == "새 프레임을 만든다."
    assert create.loc.line == 8 and create.def_loc.line == 12

    fn = model.functions["camera_device_open"]
    assert fn.loc.line == 17 and fn.def_loc.line == 18
    assert fn.brief == "HAL 모듈 진입점"
    assert "FrameFactory.cpp:12" in model.citations()
