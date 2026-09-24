# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

Camera HAL 소스에서 검토용 설계 문서(SDD)를 생성하고, 코드 변경에 맞춰 증분 갱신하는 파이프라인입니다. Clang(compile DB)으로 구조와 근거 위치를 추출하고, LLM으로 한국어 설명 초안을 작성합니다. 최종 적용 대상은 사내 Camera HAL이며, 공개 libcamera는 검증용 테스트 대상입니다. 생성 문서의 디자인 계약은 `DESIGN.md`를 따릅니다.

프로젝트 목적과 작업 기준은 아래 문서를 그대로 따릅니다.

@AGENTS.md

## 자주 쓰는 명령

```bash
uv sync --extra dev                # 의존성 설치 (Python 3.11 이상)
uv run pytest -q                   # 전체 회귀 테스트
uv run pytest tests/test_impact.py -q                    # 파일 하나만 실행
uv run pytest tests/test_impact.py::test_이름 -q         # 테스트 하나만 실행
```

파이프라인 명령은 `sdd` CLI(`src/sdd/cli.py`)로 실행합니다.

```bash
uv run sdd extract                 # compile DB에서 facts.json 추출
uv run sdd impact --base <이전-커밋> --base-facts <이전-facts.json> --fail-on-coverage-gap
uv run sdd generate                # 문서 생성 (--from-impact로 영향 범위만 생성)
uv run sdd export-site             # 정적 사이트 생성
uv run sdd verify-site             # 산출물 해시와 내부 링크 검사
uv run sdd export-html             # 단일 HTML 생성
```

다른 프로젝트 설정은 `uv run sdd --config examples/libcamera/sdd.yaml <명령>`처럼 지정합니다. `--config`는 지정한 파일을 그대로 읽으므로 한 디렉터리에 설정을 여럿 둘 수 있고, 로컬 덮어쓰기는 같은 이름의 `.local.yaml`에서 찾습니다. LLM 없이 흐름만 확인하려면 `sdd.local.yaml`(Git 제외)에 `agent: {kind: dry-run}`을 둡니다. 기본 `sdd.yaml`은 사내 HAL용 예시 경로이므로 실제 실행 전에 수정이 필요합니다.

## 아키텍처

파이프라인 단계: `extract`(facts.json 추출) → `impact`(Git diff로 재생성 대상 계산과 범위 누락 검사) → `generate`(LLM 설명 + Mermaid + 인용 검증) → `export-site`/`verify-site`(사이트 생성과 검증).

핵심 데이터 흐름과 책임 분리는 `docs/code-structure.md`에 있습니다. 요점은 다음과 같습니다.

- 구조 정보(클래스, 관계, 다이어그램)는 `facts.json`에서만 가져옵니다. `src/sdd/diagrams.py`가 Markdown 생성과 사이트 빌드가 공유하는 Mermaid 규칙이며, LLM에는 배치나 화살표 생성을 맡기지 않습니다.
- `impact.py`가 재생성 대상을 계산하고, `coverage.py`가 문서 범위 누락을 판정합니다. `coverage.py`는 Config·Git·파일에 접근하지 않고 주입받은 값만 사용합니다. `impact → coverage → impact` 순환 의존을 다시 만들지 않습니다.
- 클래스·함수 이름 비교는 생성·그림·영향 분석·범위 검사가 같은 함수(`matching.py`)를 사용합니다. C++ 이름은 대소문자를 구분하고, 경로 glob은 심볼 선택과 별도 규칙입니다.
- 영향 밖의 원고는 LLM을 부르지 않고 인용을 새 facts로 재검증한 뒤 이월합니다(`carryover.py`). 인용이 어긋난 원고는 이월하지 않고 재생성 대상으로 보고합니다.
- `manuscript.py` 린트가 문장 형태(종결어미, 대화체, 프롬프트 누설, 절대 경로)를 검사하고, `validate.py`가 인용 토큰이 facts의 위치 집합에 있는지 검사합니다. 두 검사 모두 문장의 의미가 참인지는 보장하지 않으며, `ok`/`mapped` 상태를 사람 검토 통과로 승격하지 않습니다.
- 사이트 빌드는 임시 디렉터리에서 검증한 뒤 배포 디렉터리에 반영하고, 직전 manifest가 소유한 파일만 정리합니다. 실패 시 기존 출력을 보존합니다.

설정 계층: `sdd.yaml` + `sdd.local.yaml`(로컬 덮어쓰기, Git 제외)이 소스·출력·LLM·검사 정책을 담고, `config/sections.yaml`이 문서 종류와 클래스 선택·변경 감시 규칙을, `config/scenarios.yaml`이 추적할 호출 진입점을 담습니다. `prompts/`, `templates/`, `style/`이 설명 지시문과 집필 규칙입니다.

## 테스트 기준

CI(`.github/workflows/tests.yml`)는 Ubuntu/Windows와 Python 3.11/3.14에서 `pytest`를 실행합니다. 수정 시 반복 실행의 동일성, 관계 추가·삭제 반영, 삭제·이름 변경·한글 경로 처리, 실패 시 기존 출력 보존을 회귀 테스트로 확인합니다. CSS/JS 변경은 데스크톱·모바일 화면과 검색·그림 조작을 브라우저에서 직접 확인합니다.
