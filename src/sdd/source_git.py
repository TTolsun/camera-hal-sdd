"""Git adapter for immutable revisions and source-relative changed paths."""

import subprocess
from pathlib import Path


def resolve_commit(source_root: Path, ref: str) -> str:
    return subprocess.check_output(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
                                   cwd=source_root, encoding="utf-8").strip()


def changed_files(source_root: Path, base: str, head: str = "HEAD") -> list[str]:
    # --relative: 소스 루트가 저장소의 하위 디렉터리여도 facts 의 file 과 같은 기준(소스 루트 상대)이 된다.
    res = subprocess.run(["git", "diff", "--name-only", "-z", "--no-renames", "--relative", f"{base}..{head}", "--"], cwd=source_root,
                         check=True, capture_output=True, encoding="utf-8")
    return sorted(set(path for path in res.stdout.split("\0") if path))
