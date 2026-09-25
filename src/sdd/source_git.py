"""Git adapter for immutable revisions and source-relative changed paths."""

import subprocess
from pathlib import Path


def resolve_commit(source_root: Path, ref: str) -> str:
    return subprocess.check_output(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
                                   cwd=source_root, encoding="utf-8").strip()


def commits_between(source_root: Path, base: str, to: str) -> list[str]:
    """base 다음부터 to 까지의 커밋을 오래된 것부터 차례대로. first-parent 만 따라간다."""
    out = subprocess.check_output(["git", "rev-list", "--reverse", "--first-parent", f"{base}..{to}"],
                                  cwd=source_root, encoding="utf-8")
    return [line for line in out.splitlines() if line]


def is_clean(source_root: Path) -> bool:
    out = subprocess.check_output(["git", "status", "--porcelain"], cwd=source_root, encoding="utf-8")
    return not out.strip()


def checkout(source_root: Path, sha: str) -> None:
    subprocess.run(["git", "checkout", "--detach", "--quiet", sha], cwd=source_root, check=True)


def current_ref(source_root: Path) -> str:
    """현재 브랜치 이름. detached 상태면 커밋 SHA."""
    res = subprocess.run(["git", "symbolic-ref", "--short", "-q", "HEAD"],
                         cwd=source_root, capture_output=True, encoding="utf-8")
    return res.stdout.strip() or resolve_commit(source_root, "HEAD")


def checkout_ref(source_root: Path, ref: str) -> None:
    """브랜치 이름이면 그 브랜치로 되돌린다 (detach 하지 않는다)."""
    subprocess.run(["git", "checkout", "--quiet", ref], cwd=source_root, check=True)


def fetch(source_root: Path) -> None:
    subprocess.run(["git", "fetch", "--quiet"], cwd=source_root, check=True)


def changed_files(source_root: Path, base: str, head: str = "HEAD") -> list[str]:
    # --relative: 소스 루트가 저장소의 하위 디렉터리여도 facts 의 file 과 같은 기준(소스 루트 상대)이 된다.
    res = subprocess.run(["git", "diff", "--name-only", "-z", "--no-renames", "--relative", f"{base}..{head}", "--"], cwd=source_root,
                         check=True, capture_output=True, encoding="utf-8")
    return sorted(set(path for path in res.stdout.split("\0") if path))
