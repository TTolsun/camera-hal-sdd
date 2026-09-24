# 사내 Camera HAL 적용 절차

**사내 환경이 생기면 [3. 실행 순서](#3-실행-순서)의 네 명령을 차례로 실행하고, 그 전에 [2. 바꿀 설정](#2-바꿀-설정)의 네 파일을 고치세요.**

이 문서는 libcamera 공개 검증에서 확인한 파이프라인을 사내 Camera HAL에 옮기는 절차입니다. **사내 소스와 빌드 구성을 아직 받지 못했으므로 여기 적은 절차는 실행으로 검증되지 않았습니다.** libcamera에서 확인한 동작과 사내에서 확인해야 할 항목을 구분해서 적습니다.

| 지금 확인할 내용 | 이동할 절 |
|---|---|
| 사내에서 무엇을 받아야 하는지 확인합니다. | [필요한 입력](#1-필요한-입력) |
| 어떤 설정을 고쳐야 하는지 확인합니다. | [바꿀 설정](#2-바꿀-설정) |
| 어떤 명령을 어떤 순서로 실행하는지 확인합니다. | [실행 순서](#3-실행-순서) |
| 환경 없이 지금 할 수 있는 일을 찾습니다. | [환경 없이 준비할 수 있는 것](#4-환경-없이-준비할-수-있는-것) |
| 사내에서만 확인할 수 있는 위험을 봅니다. | [사내에서 확인해야 하는 것](#5-사내에서-확인해야-하는-것) |

## 1. 필요한 입력

네 가지를 확보해야 시작할 수 있습니다. 하나라도 없으면 그 앞 단계에서 멈춥니다.

1. **HAL 소스와 고정할 SHA.** 문서의 모든 인용이 이 SHA의 파일과 줄을 가리킵니다. 움직이는 브랜치 이름을 기준으로 삼으면 인용이 어긋납니다.
2. **`compile_commands.json`.** NDK-build나 AOSP 빌드가 만든 것이어야 합니다. 실제 제품의 include 경로, `-D` 매크로, 생성 헤더가 들어 있어야 합니다. 이것이 없으면 파싱이 전부 실패합니다.
3. **LLM 엔드포인트.** 사내 Hermes나 OpenAI 호환 게이트웨이의 주소와 모델 이름입니다. 호출 가능한지 먼저 확인해야 합니다.
4. **정적 자산과 게시 위치.** Mermaid 기본 주소는 공개 CDN입니다. `site.mermaid`를 사내 경로로 바꾸지 않으면 그림이 뜨지 않습니다.

## 2. 바꿀 설정

파일 네 개입니다. 생성기 코드는 고치지 않습니다.

### sdd.yaml

```yaml
source:
  root: ../hal-camera                    # 사내 HAL 소스 루트
  compile_commands: ../hal-camera/compile_commands.json
  exclude: []                            # third_party 헤더처럼 사실에서 뺄 경로
  ndk_build:
    enabled: true
    project_dir: ../hal-camera

facts:
  package_depth: 1                       # 패키지가 두세 개로 뭉치면 2 나 3 으로 올린다

agent:
  kind: openai-compatible                # 사내 게이트웨이를 쓸 때
  base_url: https://<사내 엔드포인트>
  model: <모델 이름>

site:
  enabled: true
  title: Camera HAL 설계 문서
  source_url: <사내 코드 열람 주소>       # 인용을 코드로 연결할 주소 형식
  nav_groups: ["시작하기", "For Users", "For Developers"]
```

`package_depth`는 libcamera에서 실제로 문제가 됐던 값입니다. 소스가 `src/`와 `include/` 아래로만 나뉘면 기본값 1은 패키지를 세 개로 뭉쳐서 개요의 패키지 표가 쓸모없어집니다. 추출 후 `facts.json`의 `packages` 개수를 보고 정합니다.

`source_url`은 GitHub 형식(`<url>/blob/<sha>/<파일>#L<줄>`)을 가정합니다. 사내 코드 열람 도구의 링크 형식이 다르면 이 부분을 맞춰야 합니다.

### config/scenarios.yaml

HAL3 진입점의 **실제 시그니처**로 바꿉니다. 현재 값은 예시입니다.

```yaml
scenarios:
  - id: process_capture_request
    title: 캡처 요청 처리 (processCaptureRequest)
    from: "CameraDevice::processCaptureRequest(camera3_capture_request_t *)"
    # 정의: <파일>:<줄>                  # 대조한 위치를 적어 둔다
    depth: 5
```

시그니처가 정의와 다르면 `extract` 로그가 `진입점 못 찾음 N 개`를 보고합니다. **이 경고를 무시하면 시나리오 문서가 빈 채로 나옵니다.**

로깅 매크로가 호출 그래프의 대부분을 차지하면 `defaults.hide`에 이름을 적습니다. libcamera에서는 `LOG()` 매크로와 d-pointer 접근자가 첫 30단계 중 22단계를 차지했습니다. 사내 HAL은 `ALOGD` 계열이 같은 자리에 올 가능성이 높습니다.

```yaml
defaults:
  hide:
    owners: ["Log", "Trace"]
    names: ["ALOG*", "_d"]
```

### config/sections.yaml

`facts.classes`와 `facts.functions`의 패턴을 사내 네임스페이스로 바꿉니다. 현재 값은 `camera_*`, `HAL_*` 같은 예시입니다. `group` 값은 독자 기준으로 이미 나뉘어 있으므로 그대로 두거나 사내 용어로 바꿉니다.

### 사내 자산

Mermaid를 사내 경로에서 불러오도록 지정합니다. `sdd.yaml`의 `site.mermaid`에 적거나, 실행할 때 `--mermaid`로 넘깁니다. 사이트 루트 기준 로컬 경로도 받습니다.

```yaml
site:
  mermaid: assets/mermaid.esm.min.mjs      # 사이트 루트 기준 경로 또는 사내 주소
```

지정하지 않으면 `https://cdn.jsdelivr.net/npm/mermaid@11/...`을 그대로 씁니다. 엔드포인트 설정만으로 외부 통신이 차단되는 것은 아니므로, 실행 환경의 통신 경계도 함께 확인해야 합니다.

## 3. 실행 순서

```bash
uv run sdd --config <사내설정>/sdd.yaml doctor
uv run sdd --config <사내설정>/sdd.yaml extract
uv run sdd --config <사내설정>/sdd.yaml generate
uv run sdd --config <사내설정>/sdd.yaml export-site
uv run sdd --config <사내설정>/sdd.yaml verify-site
```

각 단계에서 확인할 숫자입니다. 기대와 다르면 다음 단계로 넘어가지 않습니다.

| 단계 | 확인할 값 | 어긋나면 |
|---|---|---|
| `extract` | 파싱 오류 0 개 | compile DB의 include 경로와 생성 헤더를 확인합니다. |
| `extract` | 진입점 못 찾음 0 개 | `scenarios.yaml`의 시그니처를 정의와 대조합니다. |
| `extract` | 클래스 수가 소스 규모와 맞는가 | 파싱은 됐지만 범위가 좁으면 `exclude`와 compile DB의 translation unit 수를 봅니다. |
| `generate` | `status: needs-review` 페이지 목록 | 사유가 각 페이지의 근거 블록에 적혀 있습니다. |
| `verify-site` | `broken_links: 0` | 링크가 깨진 채로 게시하지 않습니다. |

Windows에서 Meson이나 NDK 빌드가 어려우면 libcamera 검증과 같은 방식을 씁니다. Linux에서 추출까지 수행하고 `facts.json`을 옮긴 뒤, LLM 호출이 가능한 환경에서 생성합니다. 이때 compile DB의 상대 경로와 clang 내장 헤더 때문에 파싱이 실패할 수 있으므로, `examples/libcamera/prepare_compdb.py`처럼 경로를 절대 경로로 바꾸고 `-resource-dir`를 채우는 과정이 필요합니다.

## 4. 환경 없이 준비할 수 있는 것

사내 소스 없이 지금 할 수 있는 일입니다.

1. **진입점 목록 작성.** HAL3 인터페이스는 공개 규격이므로 `open`, `configure_streams`, `process_capture_request`, `flush`, `close`의 시그니처를 미리 적어 둘 수 있습니다. 실제 정의와의 대조만 나중에 합니다.
2. **문서 구성 결정.** 어떤 문서를 만들고 누구에게 보일지는 소스 없이 정할 수 있습니다. `config/sections.yaml`의 `group`과 `reader`가 그 결정을 담습니다.
3. **리허설.** `examples/mini-hal`이 그 목적의 최소 HAL입니다. 클래스 15개와 시나리오 6편으로 추출부터 사이트까지 전 과정이 돕니다. 사내 적용 전에 절차를 손에 익히는 용도로 쓸 수 있습니다.
4. **링크 형식 확인.** 사내 코드 열람 도구가 `blob/<sha>/<파일>#L<줄>` 형식을 쓰는지 확인해 두면, 인용이 코드로 연결되지 않는 문제를 미리 피할 수 있습니다.

## 5. 사내에서 확인해야 하는 것

libcamera에서 확인한 것이 사내에서도 같다고 가정하지 않습니다.

코드 모양은 맞습니다. 사내 HAL은 C++ 클래스 중심이므로 클래스 표, 상속·필드 관계, 패키지 요약, 클래스 단위 시나리오 추적이 그대로 적용됩니다. C 구조체 함수 포인터가 중심인 코드였다면 시나리오가 일찍 끊기고 클래스 표가 얇아지는데, 그 위험은 해당하지 않습니다. 남은 불확실성은 아래 네 가지입니다.

- **빌드 시스템이 다릅니다. 가장 먼저 깨질 곳입니다.** libcamera는 Meson, 사내 HAL은 NDK/AOSP입니다. libcamera에서도 Meson이 만든 DB를 그대로 넘겨 171개 TU가 전부 파싱에 실패했고, 경로를 절대 경로로 바꾸고 `-resource-dir`를 채운 뒤에야 통과했습니다. NDK DB도 같은 조정이 필요할 가능성이 큽니다.
- **게시 방식이 다릅니다.** GitHub Pages를 쓰지 않습니다. `export-site`의 출력은 정적 파일이므로 사내 웹 서버에 그대로 올릴 수 있지만, 경로와 접근 권한은 별도로 정해야 합니다.
- **모델이 다릅니다.** 문장 품질은 모델에 크게 좌우됩니다. libcamera 검증은 4B 모델로 수행했고, 그 결과 이름 표기와 인용을 자동 검사로 보완해야 했습니다.
- **반출 금지.** 사내 소스에서 파생된 facts, 문서, 프롬프트, 로그를 공개 저장소에 올리지 않습니다. 공개 저장소는 libcamera 검증 전용입니다.

## 근거와 검토 정보

- 설정 항목은 [설정 로더](../src/sdd/config.py)와 [libcamera 예제 설정](../examples/libcamera/sdd.yaml)에서 확인했습니다.
- 실행 순서와 확인 값은 [libcamera WSL2 실행 기록](libcamera-wsl-run.md)에서 실제로 수행한 결과입니다.
- 사내 전환 시 바뀌는 항목의 개요는 [가정용 검증 절차](libcamera-home-lab.md)의 마지막 절에 있습니다.

**이 문서의 절차는 사내 환경에서 실행되지 않았습니다.** 실행한 뒤 어긋난 부분을 이 문서에 반영해야 합니다.

다음 단계: [examples/mini-hal/sdd.yaml](../examples/mini-hal/sdd.yaml)을 열어 사내 설정에서 바꿀 항목이 어디에 있는지 확인합니다.
