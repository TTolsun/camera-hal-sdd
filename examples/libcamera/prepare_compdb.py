"""Prepare a Meson compilation database for pip libclang without editing the original.

Run in Linux with the same toolchain that built libcamera.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import subprocess


def absolute_paths(argv: list[str], directory: Path) -> list[str]:
    """Also make AST file locations absolute, not just Clang's working directory."""
    options = ("-include-pch", "-isystem", "-iquote", "-idirafter", "-imacros", "-include", "-isysroot", "-I", "-F")

    def resolve(value: str) -> str:
        path = Path(value)
        return str((directory / path).resolve()) if not path.is_absolute() else value

    result = []
    pending = False
    for token in argv:
        if pending:
            result.append(resolve(token))
            pending = False
        elif token in options:
            result.append(token)
            pending = True
        elif token.startswith("--sysroot="):
            result.append("--sysroot=" + resolve(token.split("=", 1)[1]))
        elif token.startswith("@"):
            raise ValueError("Expand response files before preparing the compilation database")
        else:
            for option in options:
                if token.startswith(option) and len(token) > len(option):
                    result.append(option + resolve(token[len(option):]))
                    break
            else:
                result.append(token)
    if pending:
        raise ValueError("Missing path after compiler option")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--clang", default="clang")
    args = parser.parse_args()
    build = args.build_dir.resolve()
    original = build / "compile_commands.json"
    output = args.out.resolve()
    if output == original:
        parser.error("--out must differ from the original compilation database")
    resource = Path(subprocess.check_output(
        [args.clang, "-print-resource-dir"], text=True
    ).strip()).resolve()
    if not (resource / "include" / "stddef.h").is_file():
        parser.error(f"Clang standard headers are missing: {resource}")
    entries = json.loads(original.read_text(encoding="utf-8"))
    for entry in entries:
        directory = Path(entry["directory"])
        if not directory.is_absolute():
            directory = build / directory
        directory = directory.resolve()
        source = Path(entry["file"])
        if not source.is_absolute():
            source = directory / source
        argv = entry.get("arguments") or shlex.split(entry["command"])
        entry["directory"] = str(directory)
        entry["file"] = str(source.resolve())
        entry["arguments"] = [
            *absolute_paths(argv, directory),
            f"-working-directory={directory}",
            f"-resource-dir={resource}",
        ]
        entry.pop("command", None)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(entries)} translation units: {output}")
    print(f"Clang resource directory: {resource}")


if __name__ == "__main__":
    main()
