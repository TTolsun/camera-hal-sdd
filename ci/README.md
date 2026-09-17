# CI 연동

`gerrit-hook.sh` 는 HAL 변경 하나에 대해 다음을 수행합니다.

1. HAL 소스를 해당 patchset 으로 checkout 하고 `origin/<branch>` 와의 merge-base 를 구합니다.
2. `sdd compdb` 로 compile DB 를 갱신합니다 (Android.mk 가 바뀌었을 수 있습니다).
3. `sdd run --base <merge-base>` 로 영향 섹션만 다시 생성합니다.
4. `sdd/` 를 docs 프로젝트의 로컬 clone(`DOCS_DIR`)에 복사하고, 그 clone 에서 commit 해 Gerrit change 로 push 합니다. 이 저장소(파이프라인 코드)의 HEAD 는 push 하지 않습니다. topic 을 HAL change 번호로 맞춰 함께 리뷰되게 합니다.

## nightly 전체 재생성

증분 갱신은 놓치는 경우가 있으므로(예: 시나리오 진입점 추가) 하루 한 번 전체를 다시 만드는 job 을 두는 것을 권장합니다.

```bash
uv run sdd compdb --regenerate
uv run sdd run            # --base 없음 = 전체 생성
```

## CI 머신 준비

- NDK: compile DB 의 `--sysroot` 가 가리키는 경로와 같은 버전이 같은 위치에 있어야 합니다. 다르면 `config/clang-uml.yaml` 의 `remove_compile_flags` / `add_compile_flags` 로 보정합니다.
- clang-uml: 릴리스 바이너리 또는 사내 패키지. `sdd doctor` 가 PATH 에서 찾습니다.
- LLM: Ollama 데몬이 CI 머신에 있거나, `sdd.local.yaml` 로 사내 게이트웨이(`openai-compatible`)를 가리킵니다. 토큰은 `SDD_AGENT_API_KEY` 환경 변수로만 넘깁니다.
