"""패키지 묶음 깊이. 소스가 src/ 와 include/ 아래로만 나뉘면 깊이 1 은 패키지 표를 쓸모없게 만든다."""

from pathlib import Path

import pytest

from sdd.config import load
from sdd.facts.callgraph import package_of

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("file, depth, expected", [
    # 깊이 1 은 기존 동작이다. libcamera 는 이 규칙에서 include / src / build 세 개로 뭉친다.
    ("src/ipa/ipu3/algorithms/lsc.cpp", 1, "src"),
    ("include/libcamera/internal/pipeline_handler.h", 1, "include"),
    # 깊이 3 이면 검토 단위로 쓸 수 있는 이름이 나온다.
    ("src/ipa/ipu3/algorithms/lsc.cpp", 3, "src/ipa/ipu3"),
    ("src/libcamera/pipeline/ipu3/ipu3.cpp", 3, "src/libcamera/pipeline"),
    ("include/libcamera/internal/pipeline_handler.h", 3, "include/libcamera/internal"),
    # 깊이보다 얕은 경로는 빈 이름을 만들지 않고 파일이 든 디렉터리까지만 쓴다.
    ("device/CameraDevice.h", 3, "device"),
    ("Android.mk", 3, "(root)"),
    ("types.h", 1, "(root)"),
])
def test_깊이별_패키지_이름(file, depth, expected):
    assert package_of(file, depth) == expected


def test_설정_기본값은_1이고_예제는_3이다(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "sdd.yaml").write_text(
        "source:\n  root: ./hal\n  compile_commands: ./hal/compile_commands.json\n",
        encoding="utf-8")
    assert load(root / "sdd.yaml").package_depth == 1
    assert load(ROOT / "examples" / "libcamera" / "sdd.yaml").package_depth == 3


def test_깊이는_0이하로_내려가지_않는다(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "sdd.yaml").write_text(
        "source:\n  root: ./hal\n  compile_commands: ./hal/compile_commands.json\n"
        "facts:\n  package_depth: 0\n",
        encoding="utf-8")
    assert load(root / "sdd.yaml").package_depth == 1
