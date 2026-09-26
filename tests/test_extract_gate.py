import json

import pytest

from sdd import extract


@pytest.mark.parametrize("failure", ["empty", "parse", "entry"])
def test_incomplete_extraction_preserves_previous_facts(tmp_cfg, monkeypatch, failure):
    tmp_cfg.clang_uml_bin = "none"
    tmp_cfg.compile_commands.parent.mkdir(parents=True, exist_ok=True)
    tmp_cfg.compile_commands.write_text(json.dumps([] if failure == "empty" else [
        {"file": "unit.cpp", "directory": str(tmp_cfg.source_root), "arguments": ["clang++", "unit.cpp"]}
    ]), encoding="utf-8")
    tmp_cfg.facts_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_cfg.facts_path.write_text("previous verified facts", encoding="utf-8")
    monkeypatch.setattr(extract.comments, "collect", lambda *args: {
        "tus": 1, "errors": int(failure == "parse"), "classes": 0, "methods": 0, "functions": 0})
    monkeypatch.setattr(extract.docblocks, "collect", lambda *args: {
        "blocks": 0, "filled": 0, "ambiguous": 0, "unknown": 0})
    monkeypatch.setattr(extract.callgraph, "collect", lambda *args: {
        "functions": 1, "scenarios": 0, "missing_entries": int(failure == "entry")})
    with pytest.raises(RuntimeError, match={"empty": "비어", "parse": "파싱 오류", "entry": "진입점"}[failure]):
        extract.run(tmp_cfg)
    assert tmp_cfg.facts_path.read_text(encoding="utf-8") == "previous verified facts"
