"""SDD 페이지 생성.

페이지 뼈대(templates/page.md)는 style/README.md 규칙을 따른다.
  1. 할 일 또는 결론 한 문장(lead)  2. 확인할 내용 -> 절 표(routes)  3. 본문
  4. 근거와 검토 정보  5. 다음 단계 하나(next)

본문에서 표, 번호 목록, 다이어그램은 사실(facts)에서 파이프라인이 직접 만든다.
LLM 은 표만으로 알 수 없는 관계와 순서를 서술하는 문단만 쓴다.
"""

from __future__ import annotations

import datetime as dt
import fnmatch
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .budget import Block, fit
from .config import Config
from .diagrams import diagram_block, section_diagram
from .facts.model import ClassInfo, KnowledgeModel, Scenario
from .impact import ImpactReport
from .llm import Agent
from .validate import Verdict, check, extract_citations, normalize_citations, strip_echo, strip_headings

_FRONTMATTER = re.compile(r"^---\n.*?\n---\n", re.S)
_YAML_FRONTMATTER = re.compile(r"^---\n.*?\n---\n", re.S)
_MAX_STEPS = 30
_MAX_READING = 6


def slugify(text: str) -> str:
    """pymdownx.slugs.slugify(case=lower) 와 같은 규칙. 한글 제목도 앵커가 된다."""
    text = re.sub(r"[^\w\s-]", "", text.strip().lower())
    return re.sub(r"[-\s]+", "-", text)


def style_rules(readme_text: str) -> str:
    """style/README.md 에서 번호 붙은 규칙만 뽑는다.

    README 전체(출처 링크, brief.mjs 설명)를 넣으면 소형 모델이 그 문서를 그대로 되풀이하는 일이 있었다.
    규칙 5개만 넣으면 그 문제가 사라지고 프롬프트도 짧아진다."""
    rules = [l.strip() for l in readme_text.splitlines() if re.match(r"^\s*\d+\.\s", l)]
    return "개발자 가이드 집필 규칙:\n" + "\n".join(rules) if rules else readme_text.strip()


def compose_system_prompt(cfg: Config) -> str:
    """prompts/system.md + style/README.md 의 규칙 (+ 원문 두 개, 설정 시). omm-doc-workflow 의 brief.mjs 와 같은 방식."""
    parts = [(cfg.prompts_dir / "system.md").read_text(encoding="utf-8").strip()]
    readme = cfg.style_dir / "README.md"
    if readme.exists():
        parts.append(style_rules(readme.read_text(encoding="utf-8")))
    if cfg.agent.full_style_guides:
        for name in ("i-have-adhd.md", "fluent-korean.md"):
            p = cfg.style_dir / name
            if p.exists():
                parts.append(_YAML_FRONTMATTER.sub("", p.read_text(encoding="utf-8"), count=1).strip())
    return "\n\n---\n\n".join(parts)


class Generator:
    def __init__(self, cfg: Config, model: KnowledgeModel, agent: Agent):
        self.cfg = cfg
        self.model = model
        self.agent = agent
        self.system = compose_system_prompt(cfg)
        self.section_tpl = (cfg.prompts_dir / "section.md").read_text(encoding="utf-8")
        self.page_tpl = (cfg.templates_dir / "page.md").read_text(encoding="utf-8")
        self.allowed = model.citations()
        # routes 표의 링크 글자: 페이지 링크는 섹션 제목, 앵커 링크는 본문의 ## 제목 원문을 쓴다.
        self.page_titles = {sec.get("output", f"{sec['id']}.md"): sec["title"] for sec in cfg.sections()}
        self.page_titles.update({f"{sid}.md": sc.title for sid, sc in model.scenarios.items()})

    # ---- 진입점 ------------------------------------------------------------

    def run(self, section_ids: list[str] | None = None, impact: ImpactReport | None = None) -> list[Path]:
        written: list[Path] = []
        for sec in self.cfg.sections():
            kind = sec.get("kind", "prose")
            if kind == "manual":
                continue
            if section_ids and sec["id"] not in section_ids:
                continue
            if impact and sec["id"] not in impact.sections:
                continue
            if kind == "prose":
                written.append(self._prose(sec))
            elif kind == "per-package":
                written.append(self._per_package(sec, impact))
            elif kind == "per-scenario":
                written += self._per_scenario(sec, impact)
            elif kind == "table":
                written.append(self._flags_table(sec))
            else:
                raise ValueError(f"{sec['id']}: 알 수 없는 kind {kind}")
        return written

    # ---- 종류별 --------------------------------------------------------------

    def _prose(self, sec: dict[str, Any]) -> Path:
        # Validate diagram policy before spending a model call. Structure is never LLM output.
        diagram = diagram_block(section_diagram(self.cfg, self.model, sec))
        facts = sec.get("facts", {})
        tables: list[str] = []
        blocks: list[Block] = []

        if facts.get("packages"):
            t = self._package_table(facts["packages"])
            tables.append("## 패키지별 역할\n\n" + t)
            blocks.append(Block("packages", "### 패키지별 역할\n" + t, 0))
            deps = self._package_deps_table()
            if deps:
                tables.append("## 패키지 사이의 의존\n\n" + deps)
                blocks.append(Block("package-deps", "### 패키지 사이의 의존\n" + deps, 1))
        if facts.get("functions"):
            t = self._entrypoint_table(facts["functions"])
            if t:
                tables.append("## HAL 진입점\n\n" + t)
                blocks.append(Block("functions", "### HAL 진입점\n" + t, 2))
        if facts.get("classes"):
            classes = [c for c in self._sorted_classes() if _match_class(c, sec)]
            if classes:
                # class_table: false 이면 표는 안 그리고 LLM 에게 인용할 사실만 준다 (개요처럼 표가 과한 절).
                if facts.get("class_table", True):
                    tables.append("## 관련 클래스\n\n" + _class_table(classes))
                blocks += [Block(f"class:{c.name}", _class_fact(c), 2) for c in classes]
        if facts.get("reading_order"):
            ro = self._reading_order(facts["reading_order"])
            if ro:
                tables.append("## 코드를 처음 읽는 순서\n\n" + ro)

        text, omitted, verdict = self._ask(sec["id"], sec, sec["title"], blocks, self._existing(sec))
        body = "\n\n".join([f"## {sec.get('prose_heading', '구조 설명')}\n\n{text}"]
                           + ([diagram] if diagram else []) + tables)
        if sec.get("needs_human"):
            body += "\n\n확인 필요: 이 절의 내용은 정적 분석 결과입니다. 콜백 실행 스레드와 종료 순서는 코드를 직접 실행해서 확인해야 합니다."
        return self._write_section(sec, body, blocks, tables, verdict, omitted)

    def _per_package(self, sec: dict[str, Any], impact: ImpactReport | None) -> Path:
        parts: list[str] = []
        routes: list[tuple[str, str]] = []
        all_blocks: list[Block] = []
        all_tables: list[str] = []
        omitted_all: list[str] = []
        worst = Verdict(ok=True)
        existing = self._existing(sec)
        targets = sorted(self.model.packages)
        if impact and impact.packages:
            targets = [p for p in targets if p in impact.packages]

        diagram = self._diagram_ref(sec.get("facts", {}).get("diagram"))
        if diagram:
            parts.append("## 전체 구조도\n\n" + diagram)

        for pkg_name in targets:
            classes = [self.model.classes[n] for n in self.model.packages[pkg_name].classes if n in self.model.classes]
            classes = [c for c in classes if _match_class(c, sec)]
            if not classes:
                continue
            table = _class_table(classes)
            blocks = [Block("table", f"### 패키지 {pkg_name}\n{table}", 0)]
            blocks += [Block(f"class:{c.name}", _class_fact(c), 1) for c in classes]
            text, omitted, verdict = self._ask(f"{sec['id']}_{slugify(pkg_name)}", sec,
                                               f"{sec['title']}: {pkg_name}", blocks, _subsection(existing, pkg_name))
            evidence = self._evidence_lines(blocks, [table], verdict, omitted)
            parts.append(f"## {pkg_name}\n\n{table}\n\n{text}\n\n??? note \"근거와 검토 정보: {pkg_name}\"\n{evidence}")
            routes.append((f"{pkg_name} 패키지의 클래스를 수정합니다.", f"#{slugify(pkg_name)}"))
            all_blocks += blocks
            all_tables.append(table)
            omitted_all += [f"{pkg_name}/{o}" for o in omitted]
            if not verdict.ok:
                worst = verdict

        return self._write_section(sec, "\n\n".join(parts), all_blocks, all_tables, worst, omitted_all,
                                   routes=routes or None)

    def _per_scenario(self, sec: dict[str, Any], impact: ImpactReport | None) -> list[Path]:
        out: list[Path] = []
        ordered = sorted(self.model.scenarios.items())
        rows = ["| 시나리오 | 진입점 | 단계 수 | 미해결 호출 |", "|---|---|---|---|"]
        routes: list[tuple[str, str]] = []
        for sid, sc in ordered:
            rows.append(f"| [{sc.title}]({sid}.md) | `{sc.entry}` | {len(sc.messages)} | {sc.unresolved} |")  # index.md 와 같은 디렉터리
            routes.append((f"{sc.title} 흐름을 추적합니다.", f"scenarios/{sid}.md"))

        for idx, (sid, sc) in enumerate(ordered):
            if impact and sid not in impact.scenarios:
                continue
            steps = _steps(sc)
            blocks = [Block("steps", f"### 시나리오 {sc.title}\n- 진입점: {sc.entry}\n{steps}", 0)]
            text, omitted, verdict = self._ask(f"scenario_{sid}", sec, sc.title, blocks, "")
            mermaid = f"```mermaid\n{sc.mermaid.strip()}\n```" if sc.mermaid else ""
            body_parts = [p for p in (mermaid, f"## 호출 순서\n\n{steps}", f"## 이 흐름에서 확인할 것\n\n{text}") if p]
            if sc.unresolved:
                body_parts.append(f"확인 필요: 가상 함수나 함수 포인터 때문에 정적으로 끊긴 호출이 {sc.unresolved} 개 있습니다. "
                                  "끊긴 지점 이후는 코드를 직접 따라가야 합니다.")
            nxt = ordered[idx + 1][1] if idx + 1 < len(ordered) else None
            next_link = (nxt.title, f"scenarios/{nxt.id}.md") if nxt else ("핵심 시나리오 목록", "scenarios/index.md")
            path = self.cfg.sdd_dir / "scenarios" / f"{sid}.md"
            page = self._render(
                title=sc.title, lead=f"`{sc.entry}` 에서 시작하는 호출 순서를 아래 번호대로 따라가세요.",
                body="\n\n".join(body_parts), routes=None,
                evidence=self._evidence_lines(blocks, [steps], verdict, omitted),
                next_link=next_link, status=_status(verdict), omitted=omitted,
                extra={"section": sec["id"], "entry": sc.entry}, page_path=path)
            out.append(self._write(path, page))

        index_body = "## 시나리오 목록\n\n" + "\n".join(rows)
        index_path = self.cfg.sdd_dir / sec.get("output", "scenarios/index.md")
        index_page = self._render(
            title=sec["title"], lead=sec.get("lead", ""), body=index_body, routes=routes,
            evidence=self._evidence_lines([], [], Verdict(ok=True), []),
            next_link=_next_of(sec), status="ok", omitted=[], extra={"section": sec["id"]}, page_path=index_path)
        out.append(self._write(index_path, index_page))
        return out

    def _flags_table(self, sec: dict[str, Any]) -> Path:
        lines = ["## 플래그 표", "",
                 "이 표는 compile DB(NDK-build 구성)의 `-D` 목록과 소스의 `#if` 분기 위치를 그대로 옮긴 것입니다. LLM 을 거치지 않았습니다.",
                 "", "| 플래그 | 값 | 분기 위치 (최대 20) |", "|---|---|---|"]
        for name in sorted(self.model.defines):
            d = self.model.defines[name]
            sites = ", ".join(f"`{u.cite()}`" for u in d.usages) or "(소스에서 분기 없음)"
            lines.append(f"| `{name}` | `{d.value}` | {sites} |")
        body = "\n".join(lines)
        return self._write_section(sec, body, [], [body], Verdict(ok=True), [])

    # ---- LLM 호출 ------------------------------------------------------------

    def _ask(self, tag: str, sec: dict[str, Any], title: str, blocks: list[Block],
             existing: str) -> tuple[str, list[str], Verdict]:
        if existing:
            blocks = blocks + [Block("existing", existing, 9)]
        reserved = len(self.system) + len(self.section_tpl) + len(title) + 400
        facts, omitted = fit(blocks, self.cfg.agent.max_input_chars, reserved=reserved)
        existing_txt = existing if existing and "existing" not in omitted else "(없음)"
        answers = "\n".join(f"- {a}" for a in (sec.get("answers") or ["이 절의 독자가 알아야 하는 구조와 관계는 무엇인가?"]))
        user = self.section_tpl.format(title=title, reader=sec.get("reader", "이 HAL 을 수정하는 개발자"),
                                       answers=answers, facts=facts, existing=existing_txt)
        if self.cfg.agent.kind == "dry-run":
            # 프롬프트만 기록한다. 검증할 출력이 없으므로 사람이 볼 문서로 표시한다.
            text = self.agent.chat(self.system, user, tag=tag)
            return text, omitted, Verdict(ok=False, notes=["dry-run: LLM 을 호출하지 않았습니다."])

        verdict = Verdict(ok=False)
        text = ""
        for attempt in range(self.cfg.max_retries + 1):
            raw = self.agent.chat(self.system, user, tag=f"{tag}_{attempt}")
            text = strip_headings(strip_echo(normalize_citations(raw, self.allowed), self.system + "\n" + user))
            verdict = check(text, self.allowed, require=self.cfg.require_citations)
            if verdict.ok:
                break
            usable = list(dict.fromkeys(extract_citations(facts)))[:12]
            user = user + "\n\n## 이전 출력의 문제\n" + "\n".join(f"- {n}" for n in verdict.notes) + \
                "\n위 문제를 고쳐서 다시 씁니다. 사실 블록에 적힌 `파일:줄` 을 디렉터리까지 그대로 복사해서 인용합니다." + \
                ("\n인용할 수 있는 위치 예: " + ", ".join(f"`{c}`" for c in usable) if usable else "")
        return text, omitted, verdict

    # ---- 사실에서 만드는 표와 목록 -------------------------------------------------

    def _sorted_classes(self) -> list[ClassInfo]:
        return sorted(self.model.classes.values(), key=lambda x: x.name)

    def _package_table(self, pats: list[str]) -> str:
        rows = ["| 패키지 | 클래스 수 | 대표 클래스 |", "|---|---|---|"]
        for name in sorted(self.model.packages):
            if not any(fnmatch.fnmatch(name, p) for p in pats):
                continue
            p = self.model.packages[name]
            reps = ", ".join(f"`{c}`" for c in p.classes[:5]) or "(없음)"
            rows.append(f"| `{name}` | {len(p.classes)} | {reps} |")
        return "\n".join(rows)

    def _package_deps_table(self) -> str:
        pkg_of = {name: c.package for name, c in self.model.classes.items() if c.package}
        edges: Counter[tuple[str, str, str]] = Counter()
        for r in self.model.relations:
            s, t = pkg_of.get(r.source), pkg_of.get(r.target)
            if s and t and s != t:
                edges[(s, t, r.type)] += 1
        if not edges:
            return ""
        rows = ["| 방향 | 관계 종류 | 관계 수 |", "|---|---|---|"]
        for (s, t, typ), n in sorted(edges.items(), key=lambda kv: (-kv[1], kv[0])):
            rows.append(f"| `{s}` → `{t}` | {typ} | {n} |")
        return "\n".join(rows)

    def _entrypoint_table(self, pats: list[str]) -> str:
        rows = ["| 함수 | 위치 | 설명 |", "|---|---|---|"]
        for name in sorted(self.model.functions):
            if not any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(name.rsplit("::", 1)[-1], p) for p in pats):
                continue
            fn = self.model.functions[name]
            loc = next((l for l in (fn.def_loc, fn.loc) if l), None)
            rows.append(f"| `{name}()` | {f'`{loc.cite()}`' if loc else '위치 없음'} | {fn.brief or '확인 필요'} |")
        return "\n".join(rows) if len(rows) > 2 else ""

    def _reading_order(self, scenario_id: str) -> str:
        sc = self.model.scenarios.get(scenario_id)
        if not sc or not sc.messages:
            return ""
        seen: list[tuple[str, str]] = []
        for m in sc.messages:
            if not m.loc:
                continue
            key = (m.loc.file, m.name)
            if all(f != m.loc.file for f, _ in seen):
                seen.append(key)
            if len(seen) >= _MAX_READING:
                break
        lines = [f"{i}. `{f}` 에서 `{fn}()` 부분을 읽습니다." for i, (f, fn) in enumerate(seen, start=1)]
        lines.append(f"\n이 순서는 `{sc.title}` 시나리오의 호출 경로에서 만들었습니다. "
                     f"자세한 흐름은 시나리오 문서 [{sc.title}](scenarios/{sc.id}.md) 에서 확인하세요.")
        return "\n".join(lines)

    def _entity_files(self, sec: dict[str, Any]) -> set[str]:
        """표에 file:line 이 없는 절(개요)에서도 근거 파일을 남기기 위해, 표에 오른 엔티티의 파일을 모은다."""
        facts = sec.get("facts", {})
        files: set[str] = set()
        pkg_pats = facts.get("packages") or []
        for name, p in self.model.packages.items():
            if any(fnmatch.fnmatch(name, pat) for pat in pkg_pats):
                for cname in p.classes:
                    c = self.model.classes.get(cname)
                    if c and c.loc:
                        files.add(c.loc.file)
        fn_pats = facts.get("functions") or []
        for name, fn in self.model.functions.items():
            if any(fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(name.rsplit("::", 1)[-1], pat) for pat in fn_pats):
                for l in (fn.def_loc, fn.loc):
                    if l:
                        files.add(l.file)
        sc = self.model.scenarios.get(str(facts.get("reading_order", "")))
        if sc:
            files.update(m.loc.file for m in sc.messages if m.loc)
        return files

    def _diagram_ref(self, name: str | None) -> str:
        if not name:
            return ""
        mmd = self.cfg.diagrams_dir / f"{name}.mmd"
        if not mmd.exists():
            return ""
        return f"```mermaid\n{mmd.read_text(encoding='utf-8').strip()}\n```"

    # ---- 페이지 뼈대 -------------------------------------------------------------

    def _write_section(self, sec: dict[str, Any], body: str, blocks: list[Block], tables: list[str],
                       verdict: Verdict, omitted: list[str], routes: list[tuple[str, str]] | None = None) -> Path:
        extra = {"section": sec["id"]}
        status = _status(verdict)
        if sec.get("needs_human"):
            extra["needs_human"] = "true"
            status = "needs-review"
        path = self.cfg.sdd_dir / sec.get("output", f"{sec['id']}.md")
        page = self._render(title=sec["title"], lead=sec.get("lead", ""), body=body,
                            routes=routes or _routes_from_config(sec) or _routes_from_headings(body),
                            evidence=self._evidence_lines(blocks, tables, verdict, omitted, self._entity_files(sec)),
                            next_link=_next_of(sec), status=status, omitted=omitted, extra=extra, page_path=path)
        return self._write(path, page)

    def _render(self, title: str, lead: str, body: str, routes: list[tuple[str, str]] | None, evidence: str,
                next_link: tuple[str, str], status: str, omitted: list[str], extra: dict[str, str],
                page_path: Path) -> str:
        meta = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "source_commit": self.model.meta.get("source_commit", ""),
            "agent": f"{self.cfg.agent.kind}/{self.cfg.agent.model}",
            "status": status,
            **extra,
        }
        fm = "\n".join(f"{k}: {v}" for k, v in meta.items())
        if omitted:
            fm += "\nfacts_omitted:\n" + "\n".join(f"  - {o}" for o in omitted)
        routes_md = ""
        if routes:
            headings = {slugify(h): h for h in re.findall(r"^## (.+)$", body, re.M)}
            routes_md = "| 지금 확인할 내용 | 이동할 절 |\n|---|---|\n" + "\n".join(
                f"| {q} | [{self._route_label(to, headings)}]({self._rel(to, page_path)}) |" for q, to in routes)
        return self.page_tpl.format(frontmatter=fm, title=title, lead=lead or "이 절의 표부터 확인하세요.",
                                    routes=routes_md, body=body.strip(), evidence=evidence,
                                    next_title=next_link[0], next_link=self._rel(next_link[1], page_path))

    def _rel(self, link: str, page_path: Path) -> str:
        """설정과 코드의 링크는 sdd 루트 기준이다. 페이지가 하위 디렉터리에 있으면 그 페이지 기준으로 바꾼다."""
        if link.startswith("#") or "://" in link:
            return link
        target, _, anchor = link.partition("#")
        rel = os.path.relpath(self.cfg.sdd_dir / target, page_path.parent).replace("\\", "/")
        return rel + (f"#{anchor}" if anchor else "")

    def _route_label(self, to: str, headings: dict[str, str]) -> str:
        if to.startswith("#"):
            return headings.get(to[1:], to[1:].replace("-", " "))
        name = to.split("#", 1)[0]
        return self.page_titles.get(name) or self.page_titles.get(Path(name).name) or Path(name).stem

    def _evidence_lines(self, blocks: list[Block], tables: list[str], verdict: Verdict, omitted: list[str],
                        extra_files: set[str] | None = None) -> str:
        text = "\n".join([b.text for b in blocks] + tables)
        files = sorted({c.rsplit(":", 1)[0] for c in extract_citations(text)} | (extra_files or set()))
        meta = self.model.meta
        lines = [
            "- 근거 파일: " + (", ".join(f"`{f}`" for f in files) if files else "(없음)"),
            f"- 근거 수준: 코드 확인 (정적 분석, {meta.get('build_config', 'ndk-build')} 구성, commit `{meta.get('source_commit', '')[:10] or '?'}`)",
            "- 인용 검증: " + ("통과" if verdict.ok else "실패 (" + "; ".join(verdict.notes) + ")"),
        ]
        if omitted:
            lines.append("- 입력 예산 때문에 제외된 사실: " + ", ".join(omitted))
        lines.append(f"- 검토: {dt.date.today().isoformat()} · {self.cfg.agent.kind}/{self.cfg.agent.model} · 사람 검토 전")
        return "\n".join("    " + l for l in lines)

    def _existing(self, sec: dict[str, Any]) -> str:
        path = self.cfg.sdd_dir / sec.get("output", f"{sec['id']}.md")
        if not path.exists():
            return ""
        text = _FRONTMATTER.sub("", path.read_text(encoding="utf-8"), count=1)
        text = re.sub(r"^# .*\n", "", text, count=1)
        text = re.sub(r"<!-- sdd:class-diagram -->.*?<!-- /sdd:class-diagram -->", "", text, flags=re.S)
        # 표, 다이어그램, 근거 블록, 번호 목록, 다음 단계 줄은 파이프라인이 다시 만든다. LLM 에는 문단만 돌려준다.
        text = re.sub(r"```mermaid.*?```", "", text, flags=re.S)
        text = re.sub(r"^\?\?\? note.*?(?=^\S|\Z)", "", text, flags=re.S | re.M)
        kept = [l for l in text.splitlines()
                if not l.lstrip().startswith("|") and not l.startswith("다음 단계:")
                and not re.match(r"^\s*\d+\. ", l)]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()

    @staticmethod
    def _write(path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        # 플랫폼과 무관하게 LF 로 쓴다. Windows 개발자와 Linux CI 가 같은 파일을 만들어야 diff 가 조용하다.
        path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")
        return path


# ---- helpers -----------------------------------------------------------------

def _status(v: Verdict) -> str:
    return "ok" if v.ok else "needs-review"


def _next_of(sec: dict[str, Any]) -> tuple[str, str]:
    nxt = sec.get("next") or {}
    return (str(nxt.get("title", "시스템 개요")), str(nxt.get("link", "overview.md")))


def _routes_from_config(sec: dict[str, Any]) -> list[tuple[str, str]] | None:
    routes = sec.get("routes")
    if not routes:
        return None
    return [(str(r.get("q", "")), str(r.get("to", "#"))) for r in routes]


def _routes_from_headings(body: str) -> list[tuple[str, str]] | None:
    heads = re.findall(r"^## (.+)$", body, re.M)
    if len(heads) < 2:
        return None
    return [(f"{h} 절을 확인합니다.", f"#{slugify(h)}") for h in heads]




def _match_class(c: ClassInfo, sec: dict[str, Any]) -> bool:
    pats = sec.get("facts", {}).get("classes") or []
    return any(fnmatch.fnmatch(c.name, p) or fnmatch.fnmatch(c.name.rsplit("::", 1)[-1], p) for p in pats)


def _class_table(classes: list[ClassInfo]) -> str:
    rows = ["| 클래스 | 선언 위치 | 상속 | 책임 (주석) |", "|---|---|---|---|"]
    for c in classes:
        bases = ", ".join(f"`{b}`" for b in c.bases) or "–"
        loc = f"`{c.loc.cite()}`" if c.loc else "위치 없음"
        rows.append(f"| `{c.name}` | {loc} | {bases} | {c.brief or '확인 필요'} |")
    return "\n".join(rows)


def _class_fact(c: ClassInfo) -> str:
    head = f"- {c.kind} {c.name}"
    if c.loc:
        head += f" `{c.loc.cite()}`"
    if c.bases:
        head += " : " + ", ".join(c.bases)
    if c.brief:
        head += f" -- {c.brief}"
    lines = [head]
    for m in c.methods[:12]:
        line = f"  - {m.name}()"
        # 정의 위치(.cpp)가 있으면 그쪽을 인용한다. 개발자가 열어 볼 곳이 거기다.
        for l in (m.def_loc, m.loc):
            if l:
                line += f" `{l.cite()}`"
                break
        if m.brief:
            line += f" -- {m.brief}"
        lines.append(line)
    if len(c.methods) > 12:
        lines.append(f"  - (메서드 {len(c.methods) - 12} 개 생략)")
    return "\n".join(lines)


def _steps(sc: Scenario) -> str:
    """연속 중복을 합친 번호 목록. 각 단계에 file:line 을 붙인다."""
    lines: list[str] = []
    prev: tuple[str, str, str] | None = None
    truncated = False
    for m in sc.messages:
        key = (m.src, m.dst, m.name)
        if key == prev:
            continue
        prev = key
        if len(lines) >= _MAX_STEPS:
            truncated = True
            break
        cite = f" `{m.loc.cite()}`" if m.loc else ""
        note = f" ({m.note})" if m.note else ""
        lines.append(f"{len(lines) + 1}. `{m.src}` 가 `{m.dst}::{m.name}()` 를 호출합니다.{note}{cite}")
    if truncated:
        lines.append("\n(이후 단계는 생략했습니다. 전체 흐름은 위 다이어그램을 보세요.)")
    return "\n".join(lines) if lines else "호출 순서를 얻지 못했습니다. 확인 필요: 진입 함수 시그니처가 clang-uml 설정과 맞는지 확인하세요."


def _subsection(existing: str, heading: str) -> str:
    """기존 문서에서 `## heading` 아래 본문만 돌려준다."""
    if not existing:
        return ""
    m = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |^\?\?\? |\Z)", existing, re.S | re.M)
    return m.group(1).strip() if m else ""
