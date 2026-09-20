"""Reading-oriented, multi-page SDD site. Presentation never changes review verdicts."""

from __future__ import annotations

import html
import json
import posixpath
import re
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit

import markdown

from .config import Config
from .diagrams import class_diagram, section_diagram, diagram_block
from .export_html import _mermaid_fence, _nav_entries, _split, _title_of_text
from .facts.model import KnowledgeModel

MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.12.0/dist/mermaid.esm.min.mjs"
ASSETS = Path(__file__).parent / "site_assets"


def _path(rel: str) -> str:
    p = PurePosixPath(rel.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or ":" in str(p) or p.suffix != ".md":
        raise RuntimeError(f"Invalid documentation path: {rel}")
    return str(p)


def _href(rel: str, current: str) -> str:
    return quote(posixpath.relpath(rel, posixpath.dirname(current) or "."), safe="/.-")


def _html_path(rel: str) -> str:
    return str(PurePosixPath(rel).with_suffix(".html"))



def _status(meta: dict) -> str:
    status = str(meta.get("status", "unrecorded"))
    label = {"ok": "인용 검사 통과", "needs-review": "인용 검사 확인 필요"}.get(status, "인용 검사 미기록")
    return f'<span class="review-state">사람 검토 전</span><span>{label} · <code>{html.escape(status)}</code></span>'


def _render(body: str, rel: str, known: set[str], model: KnowledgeModel | None,
            source_url: str, commit: str) -> tuple[str, str, list[dict]]:
    def slug(value: str, separator: str) -> str:
        return re.sub(r"[-\s]+", separator, re.sub(r"[^\w\s-]", "", value.lower().strip()))

    md = markdown.Markdown(extensions=["tables", "toc", "attr_list", "pymdownx.details", "pymdownx.superfences"],
                           extension_configs={"toc": {"slugify": slug}, "pymdownx.superfences": {"custom_fences": [
                               {"name": "mermaid", "class": "mermaid", "format": _mermaid_fence}]}})
    rendered = md.convert(body)

    def link(match: re.Match) -> str:
        href = html.unescape(match[1])
        parts = urlsplit(href)
        if parts.scheme or parts.netloc or not parts.path:
            return match[0]
        target = posixpath.normpath(posixpath.join(posixpath.dirname(rel), parts.path))
        if target in known:
            dest = _href(_html_path(target), _html_path(rel))
            if parts.fragment:
                dest += "#" + quote(parts.fragment)
            return f'href="{html.escape(dest, quote=True)}"'
        return match[0]

    rendered = re.sub(r'href="([^"]+)"', link, rendered)
    if model and source_url and re.fullmatch(r"[0-9a-f]{40}", commit):
        valid = model.citations() if commit == model.meta.get("source_commit") else set()

        def citation(match: re.Match) -> str:
            cite = html.unescape(match[1])
            if cite not in valid:
                return match[0]
            file, line = cite.rsplit(":", 1)
            if PurePosixPath(file).is_absolute() or ".." in PurePosixPath(file).parts:
                return match[0]
            url = f"{source_url.rstrip('/')}/blob/{commit}/{quote(file, safe='/')}#L{line}"
            return f'<a class="citation" href="{html.escape(url, quote=True)}">{match[0]}</a>'

        rendered = re.sub(r"<code>([^<>]+:\d+)</code>", citation, rendered)
    rendered = re.sub(r"(<table>.*?</table>)", r'<div class="table-scroll" tabindex="0" role="region" aria-label="표">\1</div>', rendered, flags=re.S)
    return rendered, md.toc, md.toc_tokens


def export_site(cfg: Config, out: Path | None = None, mermaid_src: str | None = None) -> Path:
    from .site_build import build_site
    return build_site(cfg, out or cfg.build_dir / "site", _render_site, mermaid_src)


def _render_site(cfg: Config, out: Path | None = None, mermaid_src: str | None = None) -> Path:
    settings = cfg.raw.get("site", {}) or {}
    title = str(settings.get("title", "Camera HAL SDD"))
    source_url = str(settings.get("source_url", ""))
    mermaid_src = mermaid_src or str(settings.get("mermaid", MERMAID))
    out = (out or cfg.build_dir / "site").resolve()
    if out == cfg.sdd_dir.resolve() or out in cfg.sdd_dir.resolve().parents:
        raise RuntimeError("Site output must be separate from the Markdown source directory")
    sections = {_path(s["output"]): s for s in cfg.sections() if s.get("output")}
    missing = [rel for rel, section in sections.items()
               if section.get("kind") != "manual" and not (cfg.sdd_dir / rel).is_file()]
    if missing:
        raise RuntimeError("Configured pages are missing; run generate first: " + ", ".join(missing))
    entries = [("설계 문서", s.get("title", rel), rel) for rel, s in sections.items()
               if (cfg.sdd_dir / rel).is_file()]
    # Include configured MkDocs pages and scenario pages without losing section ordering.
    for group, name, rel in _nav_entries(cfg.root / "mkdocs.yml", cfg.sdd_dir):
        if sections and not (cfg.root / "mkdocs.yml").exists():
            # Old Markdown can remain for history; removed sections must not return to the menu.
            if not (rel.startswith("scenarios/") and any(s.get("kind") == "per-scenario" for s in sections.values())):
                continue
        rel = _path(rel)
        if (cfg.sdd_dir / rel).is_file() and rel not in {e[2] for e in entries}:
            entries.append((group or "설계 문서", name, rel))
    if not entries:
        raise RuntimeError("No generated Markdown pages found")
    texts = {rel: (cfg.sdd_dir / rel).read_text(encoding="utf-8") for _, _, rel in entries}
    if "index.md" not in texts:
        intro = settings.get("intro")
        if intro:
            texts["index.md"] = (cfg.root / str(intro)).read_text(encoding="utf-8")
        else:
            texts["index.md"] = "# 문서 안내\n\n코드에서 추출한 구조와 문장별 근거를 함께 확인하세요.\n"
        texts["index.md"] += "\n## 문서 목록\n\n| 문서 | 인용 검사 | 검토 상태 |\n|---|---|---|\n"
        for _, name, rel in entries:
            status = _split(texts[rel])[0].get("status", "unrecorded")
            texts["index.md"] += f"| [{name}]({rel}) | `{status}` | 사람 검토 전 |\n"
        entries.insert(0, ("시작하기", "문서 안내", "index.md"))
    model = KnowledgeModel.load(cfg.facts_path) if cfg.facts_path.exists() else None
    if model is None and any(s.get("kind", "prose") == "prose" and s.get("facts", {}).get("classes")
                            and {**(cfg.raw.get("diagrams") or {}), **(s.get("diagram") or {})}.get("enabled", False)
                            for s in sections.values()):
        raise RuntimeError("facts.json is required to generate configured class diagrams")
    known = set(texts)
    rendered_pages = {}
    search = []
    diagram_sources = {}
    for group, name, rel in entries:
        meta, body = _split(texts[rel])
        page_title = _title_of_text(body)
        body = re.sub(r"^\s*# .+\n", "", body, count=1)
        section = sections.get(rel, {})
        if section and section.get("kind", "prose") == "prose":
            if model and meta.get("source_commit") != model.meta.get("source_commit"):
                raise RuntimeError(f"Facts and page source commits differ: {rel}")
            diagram = section_diagram(cfg, model, section) if model else ""
            block = diagram_block(diagram)
            if "<!-- sdd:class-diagram -->" in body:
                # Keep the heading for existing route links, but never retain stale edges.
                replacement = block.strip() or "## 클래스 관계\n\n현재 설정에서 표시할 클래스 관계 그림이 없습니다."
                body = re.sub(r"<!-- sdd:class-diagram -->.*?<!-- /sdd:class-diagram -->", lambda _: replacement, body, flags=re.S)
                block = ""
            if diagram:
                diagram_sources[rel] = diagram
                before, marker, after = body.partition('??? note "근거와 검토 정보"')
                # Move intact generated sections into reading order; preserve their wording.
                parts = re.fullmatch(r"(.*?)^(## 관련 클래스\n.*?)(^## 구조 설명\n.*)", before, re.S | re.M)
                if parts:
                    body = parts[1] + parts[3] + block + parts[2] + marker + after
                else:
                    body = before + block + marker + after
        content, toc, tokens = _render(body, rel, known, model, source_url, str(meta.get("source_commit", "")))
        rendered_pages[rel] = (page_title, meta, content, toc)
        search.append({"title": page_title, "page": page_title, "url": _html_path(rel)})

        def headings(items: list[dict]) -> None:
            for item in items:
                search.append({"title": html.unescape(re.sub("<[^>]+>", "", item["name"])),
                               "page": page_title, "url": _html_path(rel) + "#" + quote(item["id"])})
                headings(item.get("children", []))

        headings(tokens)
    out.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ASSETS, out / "assets", dirs_exist_ok=True)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    for index, (group, name, rel) in enumerate(entries):
        current = _html_path(rel)
        root = _href("index.html", current).removesuffix("index.html") or "./"
        page_title, meta, content, toc = rendered_pages[rel]
        nav = []
        last_group = None
        for nav_group, nav_title, nav_rel in entries:
            if nav_group != last_group:
                nav.append(f'<p class="nav-group">{html.escape(nav_group)}</p>')
                last_group = nav_group
            active = ' aria-current="page"' if nav_rel == rel else ""
            nav.append(f'<a href="{_href(_html_path(nav_rel), current)}"{active}>{html.escape(nav_title)}</a>')
        previous_next = []
        for offset, label in [(-1, "이전"), (1, "다음")]:
            other = index + offset
            if 0 <= other < len(entries):
                _, dest_title, dest_rel = entries[other]
                previous_next.append(f'<a class="{"previous" if offset < 0 else "next"}" href="{_href(_html_path(dest_rel), current)}"><small>{label}</small>{html.escape(dest_title)} {"←" if offset < 0 else "→"}</a>')
        info = []
        for key, label in [("source_commit", "분석 기준 커밋"), ("generated_at", "문서 생성 시각"), ("agent", "문장 생성 모델")]:
            if meta.get(key):
                info.append(f'<dt>{label}</dt><dd><code>{html.escape(str(meta[key]))}</code></dd>')
        downloads = ""
        if rel in sections or (cfg.sdd_dir / rel).is_file():
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cfg.sdd_dir / rel, out / rel)
            downloads = f'<a href="{_href(rel, current)}">Markdown 원문 ↗</a>'
        if rel in diagram_sources:
            mmd = str(PurePosixPath(rel).with_suffix(".mmd"))
            (out / mmd).write_text(diagram_sources[rel] + "\n", encoding="utf-8", newline="\n")
            downloads += f' <a href="{_href(mmd, current)}">Mermaid 원문 ↗</a>'
        evidence = f'<section class="evidence"><h2 id="page-evidence">생성 근거</h2><dl>{"".join(info)}</dl>{downloads}</section>' if info else ""
        status = _status(meta) if meta else '<span class="review-state">검토용 문서</span>'
        config_json = json.dumps({"root": root, "mermaid": mermaid_src}, ensure_ascii=False).replace("<", "\\u003c")
        doc = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(page_title)} · {html.escape(title)}</title><link rel="stylesheet" href="{root}assets/reading.css"></head>
<body><a class="skip" href="#main">본문으로 이동</a>
<header class="site-header"><a class="brand" href="{root}index.html"><span class="brand-mark" aria-hidden="true">◉</span>{html.escape(title)}</a>
<div class="header-actions"><button id="search-open" hidden>문서 찾기 <kbd>Ctrl K</kbd></button><button id="menu-toggle" aria-controls="sidebar" aria-expanded="false" hidden>메뉴</button></div></header>
<div class="layout"><aside id="sidebar"><p class="edition">DESIGN DOCUMENTATION</p><nav aria-label="문서 메뉴">{''.join(nav)}</nav><p class="sidebar-note">코드에서 구조를 추출하고<br>근거와 함께 검토합니다.</p></aside>
<main id="main"><p class="breadcrumb">{html.escape(group)} <span>/</span> {html.escape(page_title)}</p><h1>{html.escape(page_title)}</h1><div class="page-state">{status}</div>
<details class="mobile-toc"><summary>이 페이지의 목차</summary>{toc}</details><article>{content}</article>{evidence}<nav class="pagination" aria-label="이전과 다음 문서">{''.join(previous_next)}</nav>
<footer>Generated by camera-hal-sdd · 인용 검사와 사람의 내용 검토는 별도입니다.</footer></main>
<aside class="page-toc"><nav aria-label="현재 페이지 목차"><p>이 페이지에서</p>{toc}</nav></aside></div>
<dialog id="search-dialog" aria-labelledby="search-title"><div class="dialog-head"><h2 id="search-title">문서 찾기</h2><button data-close>닫기 <kbd>Esc</kbd></button></div><label for="search-input">문서 제목과 절 제목 검색</label><input id="search-input" type="search" autocomplete="off" placeholder="예: Pipeline, 클래스 관계"><p id="search-count" role="status"></p><ul id="search-results"></ul></dialog>
<dialog id="diagram-dialog" aria-labelledby="diagram-title"><div class="dialog-head"><h2 id="diagram-title">클래스 관계</h2><button data-close>닫기 <kbd>Esc</kbd></button></div><div class="diagram-tools"><label for="node-search">요소 찾기</label><input id="node-search" type="search" placeholder="클래스 이름"><output id="node-count" aria-live="polite"></output><button id="zoom-out" aria-label="축소">−</button><output id="zoom-value">100%</output><button id="zoom-in" aria-label="확대">+</button><button id="zoom-fit">화면에 맞춤</button><button id="zoom-reset">100%</button></div><div id="diagram-viewport" tabindex="0" role="region" aria-label="확대된 다이어그램"><div id="diagram-canvas"></div></div></dialog>
<script id="site-config" type="application/json">{config_json}</script><script defer src="{root}assets/site.js"></script></body></html>'''
        target = out / current
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(doc, encoding="utf-8", newline="\n")
    (out / "assets" / "search.json").write_text(json.dumps(search, ensure_ascii=False), encoding="utf-8")
    return out
