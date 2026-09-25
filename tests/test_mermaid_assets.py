"""Mermaid ESM 배포본 반입: tarball 에서 본체와 chunk 를 함께 꺼낸다."""

import io
import tarfile

import pytest

from sdd import mermaid_assets


def _tarball(tmp_path, members: dict[str, bytes]):
    path = tmp_path / "mermaid-11.12.0.tgz"
    with tarfile.open(path, "w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def test_본체와_chunk_를_구조_그대로_꺼낸다(tmp_path):
    tarball = _tarball(tmp_path, {
        "package/package.json": b"{}",
        "package/dist/mermaid.esm.min.mjs": b"export default {};",
        "package/dist/mermaid.min.js": b"// UMD, not needed",
        "package/dist/chunks/mermaid.esm.min/chunk-1.mjs": b"// chunk",
    })
    dest = tmp_path / "assets"
    written = mermaid_assets.fetch(dest, tarball=tarball)
    assert (dest / "mermaid.esm.min.mjs").read_bytes() == b"export default {};"
    assert (dest / "chunks/mermaid.esm.min/chunk-1.mjs").is_file()
    assert not (dest / "mermaid.min.js").exists()
    assert not (dest / "package.json").exists()
    assert len(written) == 2


def test_chunk_가_없으면_실패한다(tmp_path):
    tarball = _tarball(tmp_path, {"package/dist/mermaid.esm.min.mjs": b"x"})
    with pytest.raises(RuntimeError, match="chunks"):
        mermaid_assets.fetch(tmp_path / "assets", tarball=tarball)


def test_본체가_없으면_실패한다(tmp_path):
    tarball = _tarball(tmp_path, {"package/dist/chunks/mermaid.esm.min/chunk-1.mjs": b"x"})
    with pytest.raises(RuntimeError, match="mermaid.esm.min.mjs"):
        mermaid_assets.fetch(tmp_path / "assets", tarball=tarball)
