# camera-hal-sdd

**사내 Camera HAL 소스에서 검토용 설계 문서를 만들고, 코드 변경에 맞춰 유지하기 위한 생성기입니다.** Clang으로 구조와 근거 위치를 추출하고 LLM으로 설명 초안을 작성합니다. 현재는 공개 libcamera로 검증하는 단계이며, 사내 HAL 적용이나 무인 게시가 완료된 상태는 아닙니다.

## 저장소 역할

| 저장소 | 관리 대상 |
|---|---|
| `camera-hal-sdd` | 사실 추출, 변경 영향·문서 범위 검사, 설명·Mermaid 생성, 검증과 사이트 구성 |
| [libcamera-sdd](https://github.com/TTolsun/libcamera-sdd) | 공개 libcamera 원본 이력의 `upstream/master` 브랜치와 검토용 문서 배포 |

사내 소스와 파생 facts·프롬프트·문서·로그는 공개 테스트 저장소에 올리지 않습니다. 빌드 입력, LLM 엔드포인트와 게시 환경은 프로젝트에 맞게 설정합니다. 세부 기준은 [AGENTS.md](AGENTS.md)를 따릅니다.

## 현재 가능한 작업과 한계

| 작업 | 현재 동작 |
|---|---|
| 소스 분석 | compile DB로 클래스·함수·근거 위치·일부 관계와 호출 흐름을 추출합니다. |
| 변경 검사 | Git diff로 재생성할 섹션을 고르고, 문서 선택 범위에서 빠진 클래스·함수를 검토 대상으로 표시합니다. |
| 문서 생성 | 사실 기반 표·Mermaid와 LLM 설명을 Markdown으로 만듭니다. 자동 클래스 그림은 명시적으로 활성화합니다. |
| 자동 검사 | 인용 위치와 문장 형태를 검사합니다. 설정에 따라 입력 근거·일부 구조 주장·설계 계약의 근거 해시도 검사합니다. 일반적인 문장 의미의 정확성이나 사람의 승인을 보장하지 않습니다. |
| 사이트 구성 | 탐색·목차·검색·그림 확대를 제공하고 내부 링크와 산출물 해시를 검사합니다. |
| 게시 | 검토 후 별도 배포 절차로 진행합니다. upstream 감시와 Git 자동 게시 기능은 없습니다. |

`ok`는 해당 생성 방식에 적용된 자동 검사 결과입니다. `mapped`는 설정상 문서 범위 연결 결과입니다. 둘 다 사람의 승인이나 설계 문서의 충분성을 뜻하지 않습니다.

## 시작하기

Python 3.11 이상과 해당 소스의 `compile_commands.json`이 필요합니다. Python 의존성에는 libclang이 포함됩니다. 실제 소스를 해석할 헤더와 빌드 환경도 준비해야 합니다. NDK는 NDK-build를 사용하는 프로젝트에만 필요하며, libcamera 예제는 Linux/Meson 환경에서 검증했습니다. clang-uml이 없으면 libclang 대체 분석을 사용합니다.

```bash
uv sync --extra dev
# sdd.yaml 또는 같은 디렉터리의 sdd.local.yaml에 프로젝트 경로와 agent를 설정합니다.
uv run sdd extract
uv run sdd generate
```

기본 `sdd.yaml`은 Camera HAL용 예시 경로이므로 실행 전에 수정해야 합니다. LLM 없이 흐름을 확인하려면 `sdd.local.yaml`에 다음을 둡니다.

```yaml
agent:
  kind: dry-run
```

- 작은 HAL 예제: [examples/mini-hal](examples/mini-hal/)과 [기존 결과 스냅샷](examples/mini-hal/expected-output/)
- 사내 Camera HAL: [적용 절차와 준비 항목](docs/inhouse-adoption.md) (사내 환경에서 실행되지 않은 절차입니다)
- 공개 libcamera: [환경 준비와 실행](docs/libcamera-home-lab.md), [실제 WSL 실행 기록](docs/libcamera-wsl-run.md)
- 게시 결과: [검토용 사이트](https://ttolsun.github.io/libcamera-sdd/), [카메라 모델 문서의 충분성 평가](docs/camera-model-review.md)

다른 설정은 `uv run sdd --config examples/libcamera/sdd.yaml <명령>`처럼 지정합니다. `dry-run`은 프롬프트와 검토용 초안을 만들며 설명 품질 검증을 수행하지 않습니다.

## 변경을 문서에 반영하기

이전 커밋의 facts를 별도로 보관한 뒤 대상 커밋을 체크아웃하고 분석합니다.

```bash
uv run sdd extract
uv run sdd impact --base <이전-커밋> --base-facts <이전-facts.json> --fail-on-coverage-gap
```

`build/impact.json`과 `build/impact-review.md`를 확인합니다. `watch`가 일치해도 해당 클래스를 선택하는 문서가 없으면 검토 항목이 남습니다. 엄격 옵션은 보고서를 기록하고 종료 코드 2로 중단합니다. 이전 facts를 생략하면 삭제된 심볼 검사가 제한됩니다.

범위를 검토·보완한 뒤 `generate --from-impact`로 선택된 섹션을 생성할 수 있습니다. 영향 밖의 원고는 LLM을 부르지 않고 인용을 새 facts로 재검증한 뒤 기준 커밋을 이월하므로, 재검증까지 통과하면 전체 재생성 없이 사이트를 만들 수 있습니다. 인용이 어긋난 원고는 이월하지 않고 재생성 대상으로 보고합니다. per-package 페이지는 영향 밖 패키지의 기존 절을 지우지 않고 같은 방식으로 이월합니다.

```bash
uv run sdd generate
uv run sdd export-site
uv run sdd verify-site
```

`site.enabled: true`이면 생성 후 사이트 빌드까지 수행합니다. 단일 HTML은 `export-html`로 만들 수 있습니다. [문서 범위 검사](docs/document-coverage.md)와 [사이트 구성·사내 자산 설정](docs/document-site.md)에 옵션과 제한을 설명합니다.

## 설정 위치

| 위치 | 역할 |
|---|---|
| `sdd.yaml`, `sdd.local.yaml` | 소스·compile DB·출력·LLM·검사 정책. 로컬 설정은 Git에서 제외합니다. |
| `config/sections.yaml` | 문서 종류, 클래스·함수 선택 범위와 변경 감시 규칙 |
| `config/scenarios.yaml` | 추적할 호출 진입점 |
| `prompts/`, `templates/`, `style/` | 설명 지시문, 페이지 구조, 집필 규칙 |
| `diagrams`, `site` 설정 | 자동 그림 활성화, 노드 한도, 사이트 이름·소스 링크·Mermaid 경로 |

설명 모델은 `ollama`, `openai-compatible`, `dry-run` 중 선택합니다. 사내에서는 승인된 엔드포인트를 지정하고 인증 토큰은 `SDD_AGENT_API_KEY`로 전달합니다. 설정만으로 데이터 반출을 차단하는 기능은 없으므로 실제 연결 대상은 운영 환경에서 관리해야 합니다.

## 유지보수와 검증

```bash
uv run pytest -q
```

CI는 Windows/Ubuntu와 Python 3.11/3.14에서 회귀 테스트를 실행합니다. [코드 책임 분리](docs/code-structure.md)와 [반복 생성 디자인 계약](DESIGN.md)을 기준으로 수정합니다. 생성 HTML을 직접 수정해서 테마를 유지하지 않습니다.

실제 libcamera 두 커밋에서는 빌드·구조 추출·Mermaid 갱신을 확인했고, 문서 범위 누락과 LLM 설명 오류도 발견했습니다. 새 범위 검사는 LSC 누락을 검출합니다. [A/B 검증 기록](docs/libcamera-revision-validation.md)을 성공 범위와 함께 확인하세요.

설명에는 선택적으로 문단별 입력 인용·한정 이름·일부 상속과 필드 참조 검사를 적용합니다. libcamera의 요청·버퍼·종료·동시성 등 여섯 설계 주제는 검토한 소스 발췌와 해시에 연결해 반복 생성하며, 근거가 바뀌면 재검토 대상으로 남깁니다. 검사 대상 원고의 이월도 구조·소스 근거 지문을 확인합니다. [설계 근거와 검증 범위](docs/design-evidence.md)를 참고하세요.

남은 과제는 일반적인 설명 의미 검증, 미해결 범위 항목 검토와 사내 HAL에서의 실제 검증입니다. 가상 호출·스레드·수명 관계는 정적 추출만으로 완전하게 설명할 수 없으며 코드 검토와 실행 근거가 필요합니다.
