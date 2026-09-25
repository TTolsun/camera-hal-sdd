"""절 단위 승인 장부: 본문 해시 기반 승인, 이월 유지, 범위 검토 관문."""

from sdd import approvals


PAGE = "---\nsource_commit: " + "a" * 40 + "\nstatus: ok\n---\n\n# 개요\n\n본문 문장입니다.\n"


def test_승인은_본문이_같으면_유지되고_바뀌면_stale이_된다(tmp_cfg):
    ledger = approvals.load(tmp_cfg)
    assert approvals.page_status(ledger, "overview.md", PAGE) == "unreviewed"
    approvals.approve_page(ledger, "overview.md", PAGE, by="검토자", source_commit="a" * 40)
    assert approvals.page_status(ledger, "overview.md", PAGE) == "approved"
    # 이월은 frontmatter 의 기준 커밋만 바꾼다. 본문이 같으므로 승인이 유지된다.
    carried = PAGE.replace("a" * 40, "b" * 40)
    assert approvals.page_status(ledger, "overview.md", carried) == "approved"
    edited = PAGE.replace("본문 문장", "고친 문장")
    assert approvals.page_status(ledger, "overview.md", edited) == "stale"


def test_장부는_저장하고_다시_읽어도_같다(tmp_cfg):
    ledger = approvals.load(tmp_cfg)
    approvals.approve_page(ledger, "overview.md", PAGE, by="검토자")
    approvals.record_finding(ledger, "no-extracted-entity:file:meson.build", "accepted", by="검토자")
    approvals.save(tmp_cfg, ledger)
    loaded = approvals.load(tmp_cfg)
    assert approvals.page_status(loaded, "overview.md", PAGE) == "approved"
    assert loaded["findings"]["no-extracted-entity:file:meson.build"]["state"] == "accepted"


def test_승인된_범위_항목만_관문에서_빠진다(tmp_cfg):
    coverage = {"findings": [
        {"reason": "no-extracted-entity", "kind": "file", "name": "meson.build", "files": ["meson.build"]},
        {"reason": "entity-outside-document-scope", "kind": "class", "name": "hal::New", "files": ["new.h"]},
    ]}
    ledger = approvals.load(tmp_cfg)
    assert len(approvals.open_findings(coverage, ledger)) == 2
    approvals.record_finding(ledger, "no-extracted-entity:file:meson.build", "accepted", by="검토자")
    remaining = approvals.open_findings(coverage, ledger)
    assert [f["name"] for f in remaining] == ["hal::New"]
    # 보류(deferred)는 확인만 한 상태이므로 관문을 통과시키지 않는다.
    approvals.record_finding(ledger, "entity-outside-document-scope:class:hal::New", "deferred", by="검토자")
    assert [f["name"] for f in approvals.open_findings(coverage, ledger)] == ["hal::New"]


def test_잘못된_상태는_기록을_거부한다(tmp_cfg):
    import pytest
    ledger = approvals.load(tmp_cfg)
    with pytest.raises(RuntimeError, match="accepted 또는 deferred"):
        approvals.record_finding(ledger, "k", "approved", by="검토자")


def test_검토_보고서가_장부_키와_상태를_보여준다():
    from sdd.impact import ImpactReport
    from sdd.impact_review import review_markdown

    report = ImpactReport(base="b" * 40, head="a" * 40, coverage={
        "status": "needs-review", "baseline_available": True, "ignored_files": [], "files": [],
        "entities": [], "findings": [
            {"reason": "no-extracted-entity", "kind": "file", "name": "meson.build", "files": ["meson.build"]}],
    })
    ledger = {"schema": 1, "pages": {}, "findings": {
        "no-extracted-entity:file:meson.build": {"state": "accepted", "by": "검토자", "at": "2026-09-25"}}}
    text = review_markdown(report, ledger)
    assert "no-extracted-entity:file:meson.build" in text
    assert "장부에서 승인됨" in text
    assert "sdd accept --finding" in text
