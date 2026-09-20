"""Read review evidence declared by human-authored Markdown pages."""

import re
from pathlib import Path

import yaml


def manual_evidence_files(path: Path) -> list[str]:
    """manual 문서 frontmatter 의 evidence_files 목록. 없으면 빈 목록."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return []
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return []
    return [str(f).replace("\\", "/") for f in (data.get("evidence_files") or [])]
