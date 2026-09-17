---
generated_at: 2026-09-17T14:12:49+00:00
source_commit: 
agent: ollama/qwen3.5:4b
status: ok
section: feature-flags
---

# Feature flag 매트릭스

**바꾸려는 동작이 어떤 -D 플래그 아래에 있는지 표에서 확인하세요. 이 표는 NDK-build 구성 기준입니다.**



## 플래그 표

이 표는 compile DB(NDK-build 구성)의 `-D` 목록과 소스의 `#if` 분기 위치를 그대로 옮긴 것입니다. LLM 을 거치지 않았습니다.

| 플래그 | 값 | 분기 위치 (최대 20) |
|---|---|---|
| `MAX_PIPES` | `8` | (소스에서 분기 없음) |
| `USE_DUAL_CAMERA` | `0` | `device/CameraDevice.cpp:18` |
| `USE_SAT` | `1` | `pipeline/FrameFactory.cpp:37`, `pipeline/Pipe.cpp:12`, `pipeline/Pipe.h:31` |

??? note "근거와 검토 정보"
    - 근거 파일: `device/CameraDevice.cpp`, `pipeline/FrameFactory.cpp`, `pipeline/Pipe.cpp`, `pipeline/Pipe.h`
    - 근거 수준: 코드 확인 (정적 분석, simple_compdb 구성, commit `?`)
    - 인용 검증: 통과
    - 검토: 2026-09-17 · ollama/qwen3.5:4b · 사람 검토 전

다음 단계: [스레드와 큐 모델](threading.md)
