"""`sdd` CLI.

  sdd doctor                      도구, compile DB, LLM 도달 여부 점검
  sdd compdb [--regenerate]       compile_commands.json 확보 (ndk-build)
  sdd extract [--skip-comments]    facts.json 생성 (clang-uml + libclang 주석 + flags)
  sdd impact --base <ref>         git diff 로 영향 섹션 계산 -> build/impact.json
  sdd generate [--sections a,b] [--from-impact]   SDD Markdown 생성
  sdd run --base <ref>            extract -> impact -> generate 한 번에
  sdd build                       mkdocs build
  sdd export-site [--out dir]     탐색 메뉴·검색·Mermaid 확대를 갖춘 정적 사이트
  sdd export-html [--out f.html]  SDD 전체를 파일 하나짜리 HTML 로
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from . import compdb, extract, impact as impact_mod
from .config import Config, load
from .facts.model import KnowledgeModel
from .generate import Generator
from .llm import Agent, AgentError
from .impact_review import review_markdown
from .source_git import changed_files, resolve_commit


def _cfg(args: argparse.Namespace) -> Config:
    return load(Path(args.config).resolve() if args.config else None)


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    ok = True

    def line(label: str, good: bool, detail: str) -> None:
        nonlocal ok
        ok = ok and good
        print(f"[{'OK' if good else '!!'}] {label}: {detail}")

    line("소스 루트", cfg.source_root.exists(), cfg.source_root.as_posix())
    line("git", (cfg.source_root / ".git").exists(), "소스 루트가 git 저장소인지")
    line("compile DB", cfg.compile_commands.exists(),
         cfg.compile_commands.as_posix() + ("" if cfg.compile_commands.exists() else "  (sdd compdb 로 생성)"))
    for name, binary in (("clang-uml", cfg.clang_uml_bin), ("ndk-build", "ndk-build")):
        path = shutil.which(binary)
        line(name, path is not None, path or f"{binary} 를 PATH 에서 찾지 못함")
    try:
        line("agent", True, Agent(cfg.agent).ping())
    except AgentError as e:
        line("agent", False, str(e))
    if cfg.compile_commands.exists():
        for w in compdb.check(compdb.load_entries(cfg.compile_commands)):
            print(f"[..] compile DB 경고: {w}")
    return 0 if ok else 1


def cmd_compdb(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    path = compdb.ensure(cfg, regenerate=args.regenerate)
    entries = compdb.load_entries(path)
    print(f"compile DB: {path} (TU {len(entries)} 개, -D {len(compdb.defines(entries))} 개)")
    for w in compdb.check(entries):
        print(f"경고: {w}")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    model = extract.run(cfg, skip_comments=args.skip_comments, skip_clang_uml=args.skip_clang_uml,
                        only_diagrams=args.only.split(",") if args.only else None)
    print(f"facts: {cfg.facts_path} (클래스 {len(model.classes)}, 시나리오 {len(model.scenarios)}, "
          f"플래그 {len(model.defines)})")
    return 0


def _load_model(cfg: Config) -> KnowledgeModel:
    if not cfg.facts_path.exists():
        print("facts.json 이 없습니다. 먼저 `sdd extract` 를 실행하세요.", file=sys.stderr)
        raise SystemExit(2)
    return KnowledgeModel.load(cfg.facts_path)


def cmd_impact(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    model = _load_model(cfg)
    base, head = (resolve_commit(cfg.source_root, ref) for ref in (args.base, args.head))
    if model.meta.get("source_commit") != head:
        raise RuntimeError("현재 facts의 source_commit이 --head와 다릅니다. 대상 커밋에서 extract를 다시 실행하세요.")
    base_model = KnowledgeModel.load(Path(args.base_facts)) if args.base_facts else None
    if base_model and base_model.meta.get("source_commit") != base:
        raise RuntimeError("--base-facts의 source_commit이 --base와 다릅니다.")
    files = changed_files(cfg.source_root, base, head)
    report = impact_mod.compute(cfg, model, files, base, head, base_model)
    out = cfg.build_dir / "impact.json"
    report.save(out)
    review = cfg.build_dir / "impact-review.md"
    review.write_text(review_markdown(report), encoding="utf-8", newline="\n")
    print(f"변경 파일 {len(files)} 개, 영향 섹션 {sorted(report.sections)}, 시나리오 {sorted(report.scenarios)}")
    print(f"-> {out}")
    print(f"문서 범위: {report.coverage['status']}, 검토 항목 {len(report.coverage['findings'])}개 -> {review}")
    if not base_model:
        print("이전 facts 미제공: 삭제된 심볼의 범위 검사는 제한됩니다. --base-facts를 사용할 수 있습니다.")
    return 2 if args.fail_on_coverage_gap and report.coverage["findings"] else 0


def cmd_generate(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    model = _load_model(cfg)
    report = None
    if args.from_impact:
        p = cfg.build_dir / "impact.json"
        if not p.exists():
            print("build/impact.json 이 없습니다. 먼저 `sdd impact --base <ref>` 를 실행하세요.", file=sys.stderr)
            return 2
        report = impact_mod.ImpactReport.load(p)
        if report.coverage.get("findings"):
            print(f"문서 범위 검토 {len(report.coverage['findings'])}개가 남아 있습니다. build/impact-review.md를 확인하세요.")
    agent = Agent(cfg.agent, dump_dir=cfg.build_dir / "prompts")
    gen = Generator(cfg, model, agent)
    written = gen.run(section_ids=args.sections.split(",") if args.sections else None, impact=report)
    for w in written:
        print(f"-> {w.relative_to(cfg.root).as_posix()}")
    if report and cfg.agent.kind != "dry-run":
        summary = agent.chat((cfg.prompts_dir / "system.md").read_text(encoding="utf-8"),
                             (cfg.prompts_dir / "change_impact.md").read_text(encoding="utf-8")
                             .format(facts=impact_mod.summary_facts(report, model)), tag="change_impact")
        (cfg.build_dir / "change_impact.md").write_text(summary + "\n", encoding="utf-8")
        print("-> build/change_impact.md (리뷰어용 변경 요약)")
    if (cfg.raw.get("site") or {}).get("enabled", False):
        from .export_site import export_site
        print(f"-> {export_site(cfg)}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    rc = cmd_extract(args)
    if rc:
        return rc
    if args.base:
        rc = cmd_impact(args)
        if rc:
            return rc
        args.from_impact = True
    else:
        args.from_impact = False
    args.sections = None
    return cmd_generate(args)


def cmd_build(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    return subprocess.run(["mkdocs", "build", "--strict"], cwd=cfg.root).returncode


def cmd_export_html(args: argparse.Namespace) -> int:
    from .export_html import export

    cfg = _cfg(args)
    out = export(cfg, out=Path(args.out).resolve() if args.out else None,
                 mkdocs_yml=Path(args.mkdocs).resolve() if args.mkdocs else None,
                 mermaid_src=args.mermaid, site_name=args.title,
                 pages=args.pages.split(",") if args.pages else None)
    print(f"-> {out}")
    return 0


def cmd_export_site(args: argparse.Namespace) -> int:
    from .export_site import export_site

    out = export_site(_cfg(args), out=Path(args.out).resolve() if args.out else None,
                      mermaid_src=args.mermaid)
    print(f"-> {out}")
    return 0


def cmd_verify_site(args: argparse.Namespace) -> int:
    from .site_build import verify_site
    cfg = _cfg(args)
    print(verify_site(Path(args.out) if args.out else cfg.build_dir / "site"))
    return 0


def main(argv: list[str] | None = None) -> int:
    # Windows 콘솔의 기본 코드 페이지(cp949)에서도 한국어 메시지가 깨지지 않게 한다.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="sdd", description="Camera HAL SDD 자동 생성 파이프라인")
    p.add_argument("--config", help="sdd.yaml 경로 (기본: 현재 디렉터리에서 위로 탐색)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)

    s = sub.add_parser("compdb")
    s.add_argument("--regenerate", action="store_true")
    s.set_defaults(fn=cmd_compdb)

    s = sub.add_parser("extract")
    s.add_argument("--skip-comments", action="store_true")
    s.add_argument("--skip-clang-uml", action="store_true")
    s.add_argument("--only", help="clang-uml 다이어그램 이름을 쉼표로 나열 (예: class_overview,seq_flush)")
    s.set_defaults(fn=cmd_extract)

    s = sub.add_parser("impact")
    s.add_argument("--base", required=True, help="비교 기준 commit/ref (예: HEAD~1, origin/main)")
    s.add_argument("--head", default="HEAD")
    s.add_argument("--base-facts", help="삭제·이름 변경 검토에 사용할 이전 커밋의 facts.json")
    s.add_argument("--fail-on-coverage-gap", action="store_true", help="범위 검토 항목을 기록한 뒤 종료 코드 2로 중단")
    s.set_defaults(fn=cmd_impact)

    s = sub.add_parser("generate")
    s.add_argument("--sections", help="섹션 id 를 쉼표로 나열. 생략하면 전체")
    s.add_argument("--from-impact", action="store_true", help="build/impact.json 의 섹션만 재생성")
    s.set_defaults(fn=cmd_generate)

    s = sub.add_parser("run")
    s.add_argument("--base", help="주면 impact 기반으로 영향 섹션만, 없으면 전체 생성")
    s.add_argument("--head", default="HEAD")
    s.add_argument("--base-facts", help="이전 커밋의 facts.json")
    s.add_argument("--fail-on-coverage-gap", action="store_true", help="범위 검토 항목이 있으면 생성 전에 중단")
    s.add_argument("--skip-comments", action="store_true")
    s.add_argument("--skip-clang-uml", action="store_true")
    s.add_argument("--only", default=None)
    s.set_defaults(fn=cmd_run)

    sub.add_parser("build").set_defaults(fn=cmd_build)

    s = sub.add_parser("export-site", help="탐색 메뉴, 목차, 검색, Mermaid 확대를 갖춘 정적 문서 사이트")
    s.add_argument("--out", help="출력 디렉터리 (기본: build/site)")
    s.add_argument("--mermaid", help="Mermaid ESM URL 또는 사이트 루트 기준 로컬 경로")
    s.set_defaults(fn=cmd_export_site)

    s = sub.add_parser("verify-site", help="사이트 산출물 해시와 내부 링크를 검사한다")
    s.add_argument("--out", help="검사할 사이트 디렉터리 (기본: build/site)")
    s.set_defaults(fn=cmd_verify_site)

    s = sub.add_parser("export-html", help="SDD 전체를 파일 하나짜리 HTML 로 만든다 (메일, 오프라인 열람용)")
    s.add_argument("--out", help="출력 파일 (기본: build/sdd.html)")
    s.add_argument("--mkdocs", help="페이지 순서를 가져올 mkdocs.yml (기본: 저장소 루트)")
    s.add_argument("--mermaid", default="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs",
                   help="Mermaid ESM 경로. 사내망에서 CDN 이 막히면 로컬 파일 경로를 준다")
    s.add_argument("--title", default="Camera HAL SDD")
    s.add_argument("--pages", help="담을 페이지를 쉼표로 나열 (예: overview.md,scenarios/flush.md). 생략하면 전체")
    s.set_defaults(fn=cmd_export_html)

    args = p.parse_args(argv)
    if args.cmd == "run" and not args.base and (args.base_facts or args.fail_on_coverage_gap):
        p.error("run의 --base-facts와 --fail-on-coverage-gap에는 --base가 필요합니다.")
    try:
        return int(args.fn(args))
    except (AgentError, FileNotFoundError, RuntimeError, subprocess.CalledProcessError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
