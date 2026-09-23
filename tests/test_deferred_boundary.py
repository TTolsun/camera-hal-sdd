"""인자로 넘긴 메서드를 신호·큐 경계로 기록하는지 확인한다.

`invokeMethod(&Worker::run, ...)` 처럼 메서드를 값으로 넘기면 그 자리에서 실행되지 않는다.
추적이 그 자리에서 끊기는 사실을 문서에 남기지 않으면, 읽는 사람이 번호 목록을 실제 실행 순서로
오해한다.
"""

from pathlib import Path

import pytest

from sdd.facts import callgraph
from sdd.facts.model import KnowledgeModel

SOURCE = """
namespace hal {

class Worker {
public:
    void run();
};

class Dispatcher {
public:
    template <typename T, typename R, typename... A>
    void invokeMethod(R (T::*method)(A...), T *object) {}
};

class Front {
public:
    void submit();

private:
    Dispatcher dispatcher_;
    Worker worker_;
};

void Worker::run() {}

void Front::submit()
{
    dispatcher_.invokeMethod(&Worker::run, &worker_);
}

}  // namespace hal
"""


@pytest.fixture
def model_and_cfg(tmp_cfg, tmp_path):
    src_dir = tmp_path / "hal"
    src_dir.mkdir(exist_ok=True)
    cpp = src_dir / "front.cpp"
    cpp.write_text(SOURCE, encoding="utf-8")
    tmp_cfg.source_root = src_dir
    (tmp_cfg.config_dir / "scenarios.yaml").write_text(
        "scenarios:\n  - id: submit\n    title: 제출\n    from: \"Front::submit()\"\n    depth: 4\n",
        encoding="utf-8")
    entries = [{"directory": str(src_dir), "file": str(cpp),
                "arguments": ["clang++", "-std=c++17", "-nostdinc++", "-c", str(cpp)]}]
    model = KnowledgeModel()
    callgraph.collect(model, tmp_cfg, entries)
    return model


def test_예약된_호출을_경계로_기록한다(model_and_cfg):
    sc = model_and_cfg.scenarios["submit"]
    deferred = [m for m in sc.messages if m.note.startswith("예약된 호출")]
    assert len(deferred) == 1, [(m.src, m.dst, m.name, m.note) for m in sc.messages]
    assert (deferred[0].dst, deferred[0].name) == ("Worker", "run")
    assert sc.deferred == 1
    # 예약된 대상을 따라 들어가면 없는 순서를 만들게 되므로 추적하지 않는다.
    assert all(m.src != "Worker" for m in sc.messages)


def test_예약_경계는_facts_왕복을_견딘다(model_and_cfg, tmp_path):
    path = tmp_path / "facts.json"
    model_and_cfg.save(path)
    again = KnowledgeModel.load(path)
    assert again.scenarios["submit"].deferred == 1
