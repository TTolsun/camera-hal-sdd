"""Build and extract two real libcamera revisions in isolated Linux worktrees.

Uses the configured libcamera example and current generator. Never changes the source checkout
or publishes results. Run with the Linux environment that contains Meson, Ninja and libclang.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import yaml


def run_revision(source: Path, commit: str, root: Path, generator: Path, jobs: int) -> dict:
    started = time.monotonic()
    root.mkdir(parents=True, exist_ok=True)
    checkout = root / "source"
    if checkout.exists():
        raise RuntimeError(f"Use a fresh validation directory; checkout exists: {checkout}")
    subprocess.run(["git", "worktree", "add", "--detach", str(checkout), commit], cwd=source, check=True)
    env = {**os.environ, "PYTHONPATH": str(generator / "src"), "CC": "clang", "CXX": "clang++"}
    config_dir = root / "config"
    config_dir.mkdir()
    cfg = yaml.safe_load((generator / "examples/libcamera/sdd.yaml").read_text(encoding="utf-8"))
    cfg["source"].update(root=str(checkout), compile_commands=str(config_dir / "build/compile_commands.json"))
    cfg["paths"] = {k: str((generator / "examples/libcamera" / v).resolve()) for k, v in cfg["paths"].items()}
    cfg["output"] = {"facts_dir": "build/facts", "sdd_dir": "build/sdd", "diagrams_dir": "build/sdd/diagrams"}
    cfg["agent"]["kind"] = "dry-run"
    config = config_dir / "sdd.yaml"
    config.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    commands = [
        ["meson", "setup", "build", "-Dpipelines=ipu3,rkisp1,uvcvideo", "-Dipas=ipu3,rkisp1",
         "-Dgstreamer=enabled", "-Dcam=disabled", "-Dqcam=disabled", "-Ddocumentation=disabled", "-Dpycamera=disabled", "-Dtest=false"],
        ["ninja", "-C", "build", "-j", str(jobs)],
        [sys.executable, str(generator / "examples/libcamera/prepare_compdb.py"), "--build-dir", str(checkout / "build"),
         "--out", str(config_dir / "build/compile_commands.json")],
        [sys.executable, "-m", "sdd.cli", "--config", str(config), "extract"],
        [sys.executable, str(generator / "examples/libcamera/verify_facts.py"), "--config", str(config)],
    ]
    record = {"source_commit": commit, "source_root": str(checkout), "commands": []}
    try:
        for i, command in enumerate(commands):
            log = root / f"{i + 1:02d}.log"
            print(f"{root.name}: {command[0]} {command[1]} -> {log}", flush=True)
            tick = time.monotonic()
            with log.open("w", encoding="utf-8") as stream:
                result = subprocess.run(command, cwd=checkout, env=env, stdout=stream, stderr=subprocess.STDOUT)
            record["commands"].append({"argv": command, "exit_code": result.returncode,
                                       "seconds": round(time.monotonic() - tick, 2), "log": str(log)})
            if result.returncode:
                raise RuntimeError(f"Command failed ({result.returncode}); see {log}")
        record["ok"] = True
    except Exception as error:
        record.update(ok=False, error=str(error))
    record["seconds"] = round(time.monotonic() - started, 2)
    (root / "execution.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def export_results(workdir: Path, destination: Path) -> None:
    for letter in ("a", "b"):
        source = workdir / letter
        if not json.loads((source / "execution.json").read_text(encoding="utf-8"))["ok"]:
            raise RuntimeError(f"Cannot export failed run: {letter}")
        target = destination / letter
        target.mkdir(parents=True, exist_ok=True)
        files = {"facts.json": source / "config/build/facts/facts.json",
                 "facts-verification.json": source / "config/build/facts-verification.json",
                 "execution.json": source / "execution.json"}
        files.update({p.name: p for p in source.glob("*.log")})
        for name, path in files.items():
            shutil.copyfile(path, target / name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--export-to", type=Path, help="Copy verified facts and logs to a Windows-accessible directory")
    parser.add_argument("--export-only", action="store_true", help="Export an already completed pair without rebuilding")
    args = parser.parse_args()
    generator = Path(__file__).resolve().parents[2]
    if args.export_only:
        if not args.export_to:
            parser.error("--export-only requires --export-to")
        export_results(args.workdir, args.export_to)
        return 0
    refs = [subprocess.check_output(["git", "rev-parse", f"{ref}^{{commit}}"], cwd=args.source, text=True).strip()
            for ref in (args.base, args.head)]
    if refs[0] == refs[1]:
        parser.error("Two distinct source commits are required")
    with ThreadPoolExecutor(max_workers=2) as executor:
        tasks = [executor.submit(run_revision, args.source.resolve(), commit, args.workdir.resolve() / name, generator, args.jobs)
                 for name, commit in zip(("a", "b"), refs)]
        results = [task.result() for task in tasks]
    (args.workdir / "execution.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps([{"source_commit": r["source_commit"], "ok": r["ok"], "seconds": r["seconds"]} for r in results]))
    if args.export_to and all(r["ok"] for r in results):
        export_results(args.workdir, args.export_to)
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
