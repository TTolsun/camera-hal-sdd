"""Generate comparable local-LLM documents from both validated Linux fact exports.

Input directory: a/{facts.json,execution.json,facts-verification.json}, b/{...}.
Produces the three current pages plus an explicitly scoped IPU3 regression probe.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

import yaml

from sdd.config import load


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    example = Path(__file__).resolve().parent
    cfg = load(example / "sdd.yaml")
    if cfg.agent.kind != "ollama":
        parser.error("This experiment requires the configured local Ollama backend")
    for letter in ("a", "b"):
        for name in ("execution.json", "facts-verification.json"):
            if not json.loads((root / letter / name).read_text(encoding="utf-8"))["ok"]:
                raise RuntimeError(f"Input verification failed: {letter}/{name}")
        meta = json.loads((root / letter / "facts.json").read_text(encoding="utf-8"))["meta"]
        if meta["comments"]["errors"]:
            raise RuntimeError(f"Parse errors in {letter}")
        if (root / letter / "sdd").exists():
            raise RuntimeError("Use a fresh output directory to avoid feeding previous prose to the model")
    sections = cfg.sections()
    sections.append({"id": "ipu3-lsc-probe", "title": "IPU3 알고리즘과 처리 상태", "output": "ipu3-lsc-probe.md", "kind": "prose",
                     "lead": "이번 커밋에서 확인되는 IPU3 알고리즘과 처리 상태의 선언을 확인하세요.",
                     "reader": "IPU3 알고리즘 변경을 검토하는 개발자",
                     "answers": ["현재 추출 사실에서 확인되는 IPU3 알고리즘과 처리 상태 클래스는 무엇인가?",
                                 "LSC 관련 구현의 선언, 상속과 메서드는 어디에서 확인할 수 있는가?"],
                     "facts": {"classes": ["libcamera::ipa::ipu3::IPAActiveState", "libcamera::ipa::ipu3::IPAFrameContext",
                                             "libcamera::ipa::lsc::ActiveState", "libcamera::ipa::lsc::FrameContext",
                                             "libcamera::ipa::LscAlgorithm", "libcamera::ipa::ipu3::algorithms::Lsc"]},
                     "watch": ["src/ipa/ipu3/**", "src/ipa/libipa/lsc*"],
                     "next": {"title": "카메라와 요청 모델", "link": "camera-model.md"}})
    sections_path = root / "sections.yaml"
    sections_path.write_text(yaml.safe_dump({"sections": sections}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    with urllib.request.urlopen(cfg.agent.base_url + "/api/tags", timeout=10) as response:
        tags = json.load(response)
    (root / "model.json").write_text(json.dumps(tags, indent=2) + "\n", encoding="utf-8")
    runs = []
    for letter in ("a", "b"):
        run = root / letter
        current = copy.deepcopy(cfg.raw)
        current["paths"] = {k: str(v) for k, v in cfg.paths.items()}
        current["paths"]["sections_file"] = str(sections_path)
        current["output"] = {"facts_dir": ".", "sdd_dir": "sdd", "diagrams_dir": "sdd/diagrams"}
        current["agent"]["temperature"] = 0
        current["site"].update(enabled=True, intro="intro.md")
        commit = json.loads((run / "facts.json").read_text(encoding="utf-8"))["meta"]["source_commit"]
        (run / "intro.md").write_text(f"# 커밋 비교 검증\n\n분석 기준: `{commit}`.\n\n공개 libcamera 검증용이며 사람 검토 전입니다.\n", encoding="utf-8")
        config = run / "sdd.yaml"
        config.write_text(yaml.safe_dump(current, allow_unicode=True, sort_keys=False), encoding="utf-8")
        command = [sys.executable, "-m", "sdd.cli", "--config", str(config), "generate"]
        started = time.monotonic()
        print(f"Generating {letter} {commit}", flush=True)
        with (run / "generate.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        runs.append({"revision": letter, "source_commit": commit, "exit_code": result.returncode,
                     "seconds": round(time.monotonic() - started, 2)})
        (root / "narration.json").write_text(json.dumps(runs, indent=2) + "\n", encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"Generation failed; see {run / 'generate.log'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
