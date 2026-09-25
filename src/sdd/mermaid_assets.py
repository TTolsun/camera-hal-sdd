"""Mermaid ESM 배포본을 사내·오프라인 자산으로 가져오는 절차.

Mermaid ESM 은 본체(mermaid.esm.min.mjs) 하나가 아니라 chunks/ 디렉터리의 모듈 여러 개를
상대 경로로 불러온다. 그래서 파일 하나만 복사하면 사이트에서 그림이 뜨지 않는다. 이 모듈은
npm 레지스트리 tarball 에서 본체와 chunk 를 함께 꺼내 한 디렉터리에 놓는다.

망이 분리된 환경에서는 tarball 파일을 먼저 반입한 뒤 --tarball 로 지정한다.
"""

from __future__ import annotations

import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath

DEFAULT_VERSION = "11.12.0"
DEFAULT_REGISTRY = "https://registry.npmjs.org"
ENTRY = "mermaid.esm.min.mjs"
# npm tarball 안에서 가져올 경로. dist/ 의 나머지(UMD 빌드, map)는 사이트가 쓰지 않는다.
_WANTED_PREFIXES = ("package/dist/mermaid.esm.min.mjs", "package/dist/chunks/mermaid.esm.min/")


def tarball_url(version: str = DEFAULT_VERSION, registry: str = DEFAULT_REGISTRY) -> str:
    return f"{registry.rstrip('/')}/mermaid/-/mermaid-{version}.tgz"


def _safe_relpath(member_name: str) -> PurePosixPath:
    rel = PurePosixPath(member_name)
    if rel.is_absolute() or ".." in rel.parts:
        raise RuntimeError(f"tarball 안의 경로가 안전하지 않습니다: {member_name}")
    return rel


def extract(tarball: Path, dest: Path) -> list[Path]:
    """tarball 에서 ESM 본체와 chunk 만 dest 에 꺼낸다. 꺼낸 파일 목록을 돌려준다."""
    written: list[Path] = []
    dest = dest.resolve()
    with tarfile.open(tarball, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() or not member.name.startswith(_WANTED_PREFIXES):
                continue
            if member.name.endswith(".map"):
                # source map 은 렌더링에 필요 없고 배포본 크기만 두 배로 늘린다.
                continue
            rel = _safe_relpath(member.name)
            # package/dist/ 아래 구조를 그대로 보존한다. chunk 는 본체 옆 chunks/ 에서 상대 경로로 로드된다.
            target = dest.joinpath(*rel.parts[2:])
            if not target.resolve().is_relative_to(dest):
                raise RuntimeError(f"tarball 안의 경로가 안전하지 않습니다: {member.name}")
            source = tar.extractfile(member)
            if source is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read())
            written.append(target)
    if not any(p.name == ENTRY for p in written):
        raise RuntimeError(f"tarball 에서 {ENTRY} 를 찾지 못했습니다. Mermaid 배포 구조가 바뀌었는지 확인하세요.")
    if not any("chunks" in p.parts for p in written):
        raise RuntimeError("tarball 에서 chunks/ 모듈을 찾지 못했습니다. 본체만으로는 그림이 뜨지 않습니다.")
    return written


def fetch(dest: Path, version: str = DEFAULT_VERSION, registry: str = DEFAULT_REGISTRY,
          tarball: Path | None = None) -> list[Path]:
    """Mermaid ESM 배포본을 dest 디렉터리에 놓는다.

    tarball 을 지정하면 그 파일을 쓰고(망 분리 환경), 없으면 registry 에서 내려받는다.
    """
    if tarball is not None:
        return extract(tarball, dest)
    url = tarball_url(version, registry)
    with tempfile.TemporaryDirectory(prefix="mermaid-") as temporary:
        downloaded = Path(temporary) / f"mermaid-{version}.tgz"
        # timeout 이 없으면 응답이 멈춘 프록시·레지스트리에서 명령이 끝나지 않는다.
        with urllib.request.urlopen(url, timeout=60) as response, downloaded.open("wb") as f:
            f.write(response.read())
        return extract(downloaded, dest)
