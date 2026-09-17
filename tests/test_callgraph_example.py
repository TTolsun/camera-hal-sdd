"""examples/mini-hal 을 libclang 대체 경로로 끝까지 추출해서, 시나리오와 관계가 기대대로 나오는지 확인한다."""

from pathlib import Path

import pytest

from sdd import compdb, extract
from sdd.config import load

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "mini-hal"


@pytest.fixture(scope="module")
def model(tmp_path_factory):
    # 예제 설정을 tmp 로 복사해서 저장소의 build/ 를 건드리지 않는다.
    import shutil

    work = tmp_path_factory.mktemp("mini-hal")
    shutil.copytree(EXAMPLE / "src", work / "src")
    shutil.copytree(EXAMPLE / "stubs", work / "stubs")
    shutil.copytree(EXAMPLE / "config", work / "config")
    text = (EXAMPLE / "sdd.yaml").read_text(encoding="utf-8")
    text = text.replace("../../", (ROOT.as_posix() + "/")).replace("kind: ollama", "kind: dry-run")
    text = text.replace("clang_uml: clang-uml", "clang_uml: none")
    (work / "sdd.yaml").write_text(text, encoding="utf-8")
    cfg = load(work / "sdd.yaml")
    return extract.run(cfg)


def test_simple_compdb_resolves_relative_include_paths(model):
    entries = compdb.load_entries(Path(model.meta["compile_commands"]))
    assert len(entries) == 6
    args = entries[0]["arguments"]
    stub = args[args.index("-isystem") + 1]
    assert Path(stub).is_absolute() and Path(stub).name == "stubs"
    assert compdb.defines(entries) == {"USE_SAT": "1", "USE_DUAL_CAMERA": "0", "MAX_PIPES": "8"}


def test_classes_packages_and_relations(model):
    assert model.meta["structure_backend"] == "libclang"
    assert {"device", "pipeline", "hal3"} <= set(model.packages)
    assert "halcam::CameraDevice" in model.packages["device"].classes
    rel = {(r.source.rsplit("::", 1)[-1], r.target.rsplit("::", 1)[-1], r.type) for r in model.relations}
    assert ("IspPipe", "Pipe", "inheritance") in rel
    assert ("CameraDevice", "RequestManager", "association") in rel      # std::unique_ptr<RequestManager> 필드
    assert ("FrameFactory", "Pipe", "association") in rel               # std::vector<std::unique_ptr<Pipe>> 필드
    assert model.classes["halcam::CameraDevice"].brief.startswith("HAL3 device object")


def test_capture_request_scenario_follows_virtual_candidates(model):
    sc = model.scenarios["process_capture_request"]
    steps = [(m.src, m.dst, m.name, m.note) for m in sc.messages]
    assert steps[0] == ("CameraDevice", "RequestManager", "submit", "")
    assert ("RequestManager", "CaptureFrameFactory", "createFrame", "virtual 후보") in steps
    assert ("FrameFactory", "PreviewFrameFactory", "buildPipes", "virtual 후보") in steps
    # Base::method(...) 한정 호출은 가상 함수라도 정적으로 결정된다.
    assert ("CaptureFrameFactory", "FrameFactory", "createFrame", "") in steps
    assert steps[-1][:3] == ("RequestManager", "PipeThread", "enqueue")
    assert sc.messages[0].loc.file == "device/CameraDevice.cpp"
    assert "sequenceDiagram" in sc.mermaid and "RequestManager-->>CaptureFrameFactory: createFrame() [virtual 후보]" in sc.mermaid


def test_worker_scenario_marks_function_pointer_as_unresolved(model):
    sc = model.scenarios["frame_processing"]
    assert sc.unresolved == 1
    fp = next(m for m in sc.messages if m.name == "process_capture_result")
    assert fp.dst == "camera3_callback_ops" and "함수 포인터" in fp.note
    assert ("FrameFactory", "SatPipe", "process") in [(m.src, m.dst, m.name) for m in sc.messages]


def test_feature_flags_have_usage_sites(model):
    assert [u.file for u in model.defines["USE_SAT"].usages].count("pipeline/Pipe.h") >= 1
    assert model.defines["USE_DUAL_CAMERA"].usages[0].file == "device/CameraDevice.cpp"
    assert model.defines["MAX_PIPES"].usages == []      # #if 분기가 아니라 값으로만 쓰인다
