from sdd.carryover import carry_forward

PAGE = """---
generated_at: 2026-09-01T00:00:00+00:00
source_commit: old111
agent: ollama/qwen3.5:4b
status: ok
section: overview
---

# 개요

`CameraDevice` 는 카메라마다 하나씩 만들어집니다 `device/CameraDevice.h:40`.
"""


def _write(cfg, name, text):
    p = cfg.sdd_dir / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


def test_valid_citations_promote_commit(tmp_cfg, sample_model):
    page = _write(tmp_cfg, "overview.md", PAGE)
    promoted, stale = carry_forward(tmp_cfg, sample_model, [])
    assert promoted == [page] and stale == []
    text = page.read_text(encoding="utf-8")
    assert "source_commit: abc123" in text
    assert text.count("revalidated_from: old111") == 1
    # 본문과 나머지 frontmatter 는 그대로다.
    assert "status: ok" in text and "카메라마다 하나씩 만들어집니다" in text


def test_repeated_promotion_keeps_single_revalidated_from(tmp_cfg, sample_model):
    page = _write(tmp_cfg, "overview.md", PAGE.replace("section: overview",
                                                       "section: overview\nrevalidated_from: zzz999"))
    carry_forward(tmp_cfg, sample_model, [])
    text = page.read_text(encoding="utf-8")
    assert text.count("revalidated_from:") == 1 and "revalidated_from: old111" in text


def test_broken_citation_blocks_promotion(tmp_cfg, sample_model):
    page = _write(tmp_cfg, "threading.md", PAGE.replace("device/CameraDevice.h:40", "device/Gone.cpp:1"))
    promoted, stale = carry_forward(tmp_cfg, sample_model, [])
    assert promoted == []
    assert stale == [(page, ["device/Gone.cpp:1"])]
    assert "source_commit: old111" in page.read_text(encoding="utf-8")


def test_manual_written_current_and_plain_pages_are_skipped(tmp_cfg, sample_model):
    _write(tmp_cfg, "constraints.md",
           "---\nstatus: ok\nkind: manual\nsource_commit: old111\nagent: x\n---\n\n# 제약\n")
    _write(tmp_cfg, "flags.md", PAGE.replace("old111", "abc123"))          # 이미 현재 커밋
    written = _write(tmp_cfg, "components.md", PAGE)                       # 이번에 생성됨
    _write(tmp_cfg, "notes.md", "# 파이프라인 frontmatter 없는 메모\n")
    promoted, stale = carry_forward(tmp_cfg, sample_model, [written])
    assert promoted == [] and stale == []
    assert "source_commit: old111" in written.read_text(encoding="utf-8")
