"""compile_commands.json 확보와 해석.

NDK-build 환경에서는 `ndk-build compile_commands.json` 이 compile DB 를 만든다.
여기서 나온 -I / -D / --sysroot 가 clang-uml 과 libclang 의 #ifdef 해석 기준이 된다.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from .config import Config

# shlex 가 posix=False 로 나눈 토큰을 감싸고 있을 수 있는 따옴표 (큰따옴표, 작은따옴표)
_QUOTE_CHARS = "\x22\x27"


def load_entries(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path}: compile DB 는 JSON 배열이어야 합니다.")
    return data


def generate_with_ndk(cfg: Config) -> Path:
    ndk = cfg.ndk_build
    if not ndk.get("enabled"):
        raise RuntimeError("source.ndk_build.enabled 가 false 이고 compile DB 도 없습니다.")
    project_dir = Path(ndk.get("project_dir") or cfg.source_root)
    cmd = ["ndk-build", "compile_commands.json", *[str(a) for a in (ndk.get("args") or [])]]
    subprocess.run(cmd, cwd=project_dir, check=True)
    # ndk-build 는 NDK_PROJECT_PATH 아래에 compile_commands.json 을 쓴다.
    for c in (project_dir / "compile_commands.json", cfg.compile_commands):
        if c.exists():
            if c != cfg.compile_commands:
                cfg.compile_commands.parent.mkdir(parents=True, exist_ok=True)
                cfg.compile_commands.write_bytes(c.read_bytes())
            return cfg.compile_commands
    raise FileNotFoundError("ndk-build 를 실행했지만 compile_commands.json 을 찾지 못했습니다.")


def generate_simple(cfg: Config) -> Path:
    """ndk-build 없이 compile DB 를 만든다. source.simple_compdb.flags 를 모든 .cpp 에 같은 플래그로 적용한다.

    NDK 트리가 아닌 디렉터리(예: AOSP 에서 떼어 낸 HAL, examples/)를 돌릴 때 쓴다.
    -D 와 -I 를 사람이 적어야 하므로 실제 빌드 구성과 어긋날 수 있다. 가능하면 ndk-build 경로를 쓴다.
    """
    simple = (cfg.raw.get("source", {}) or {}).get("simple_compdb") or {}
    compiler = str(simple.get("compiler", "clang++"))
    root = cfg.source_root.resolve()
    # -I / -isystem 뒤의 상대 경로는 소스 루트 기준으로 절대 경로로 바꾼다. libclang 은 directory 로 chdir 하지 않는다.
    flags: list[str] = []
    raw_flags = [str(f) for f in (simple.get("flags") or [])]
    for i, tok in enumerate(raw_flags):
        prev = raw_flags[i - 1] if i else ""
        if prev in ("-I", "-isystem", "-iquote") and not Path(tok).is_absolute():
            tok = (root / tok).resolve().as_posix()
        elif tok.startswith("-I") and len(tok) > 2 and not Path(tok[2:]).is_absolute():
            tok = "-I" + (root / tok[2:]).resolve().as_posix()
        flags.append(tok)
    entries = []
    for src in sorted(root.rglob("*")):
        if src.suffix.lower() not in (".cpp", ".cc", ".c") or any(p in ("build", "obj", "libs") for p in src.parts):
            continue
        entries.append({
            "directory": root.as_posix(),
            "file": src.as_posix(),
            "arguments": [compiler, *flags, "-I" + root.as_posix(), "-c", src.as_posix()],
        })
    cfg.compile_commands.parent.mkdir(parents=True, exist_ok=True)
    cfg.compile_commands.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    return cfg.compile_commands


def ensure(cfg: Config, regenerate: bool = False) -> Path:
    if cfg.compile_commands.exists() and not regenerate:
        return cfg.compile_commands
    if (cfg.raw.get("source", {}) or {}).get("simple_compdb"):
        return generate_simple(cfg)
    return generate_with_ndk(cfg)


def _argv(entry: dict[str, Any]) -> list[str]:
    if isinstance(entry.get("arguments"), list):
        return [str(a) for a in entry["arguments"]]
    cmd = str(entry.get("command", ""))
    # Windows 경로의 백슬래시를 보존하기 위해 posix=False 로 나누고 따옴표만 벗긴다.
    posix = os.name != "nt"
    toks = shlex.split(cmd, posix=posix)
    if not posix:
        toks = [
            t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in _QUOTE_CHARS else t
            for t in toks
        ]
    return toks


def _flag_values(argv: list[str], flags: tuple[str, ...]) -> list[str]:
    """-DFOO, -D FOO, -Ipath, -I path, -isystem path, --sysroot=path 형태를 모두 모은다."""
    out: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        for fl in flags:
            if tok == fl and i + 1 < len(argv):
                out.append(argv[i + 1])
                i += 1
                break
            if tok.startswith(fl) and len(tok) > len(fl):
                rest = tok[len(fl):]
                out.append(rest[1:] if rest.startswith("=") else rest)
                break
        i += 1
    return out


def defines(entries: list[dict[str, Any]]) -> dict[str, str]:
    """-D 매크로를 이름 -> 값 으로 모은다. 값이 없으면 "1"."""
    out: dict[str, str] = {}
    for e in entries:
        for d in _flag_values(_argv(e), ("-D",)):
            name, _, value = d.partition("=")
            if name and name not in out:
                out[name] = value or "1"
    return out


def include_dirs(entries: list[dict[str, Any]]) -> list[str]:
    seen: dict[str, None] = {}
    for e in entries:
        for inc in _flag_values(_argv(e), ("-I", "-isystem", "-iquote")):
            seen.setdefault(inc, None)
    return list(seen)


def sysroots(entries: list[dict[str, Any]]) -> list[str]:
    seen: dict[str, None] = {}
    for e in entries:
        for s in _flag_values(_argv(e), ("--sysroot", "-isysroot")):
            seen.setdefault(s, None)
    return list(seen)


def translation_units(entries: list[dict[str, Any]]) -> list[Path]:
    out: list[Path] = []
    for e in entries:
        f = Path(str(e.get("file", "")))
        if not f.is_absolute():
            f = Path(str(e.get("directory", "."))) / f
        out.append(f)
    return out


def check(entries: list[dict[str, Any]]) -> list[str]:
    """clang-uml 실행 전에 잡을 수 있는 문제를 경고 문자열로 돌려준다."""
    warnings: list[str] = []
    if not entries:
        warnings.append("compile DB 가 비어 있습니다.")
        return warnings
    for s in sysroots(entries):
        if not Path(s).exists():
            warnings.append(f"sysroot 경로가 없습니다: {s} (NDK 가 이 머신에 설치되어 있는지 확인)")
    missing = [str(p) for p in translation_units(entries) if not p.exists()]
    if missing:
        warnings.append(f"compile DB 의 소스 {len(missing)} 개가 존재하지 않습니다. 예: {missing[0]}")
    return warnings
