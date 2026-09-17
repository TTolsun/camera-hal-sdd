---
generated_at: 2026-09-17T14:12:55+00:00
source_commit: 
agent: ollama/qwen3.5:4b
status: needs-review
section: threading
needs_human: true
---

# 스레드와 큐 모델

**콜백이 어느 스레드에서 실행되는지는 정적 분석으로 확인되지 않았습니다. 아래 표의 클래스를 수정하기 전에 실행 스레드를 직접 확인하세요.**

| 지금 확인할 내용 | 이동할 절 |
|---|---|
| 관련 클래스 절을 확인합니다. | [관련 클래스](#관련-클래스) |
| 구조 설명 절을 확인합니다. | [구조 설명](#구조-설명) |

## 관련 클래스

| 클래스 | 선언 위치 | 상속 | 책임 (주석) |
|---|---|---|---|
| `halcam::PipeThread` | `pipeline/PipeThread.h:14` | – | Worker thread that drains a frame queue. One PipeThread per RequestManager. enqueue() may be called from the framework thread; the handler runs on the worker thread. |

## 구조 설명

`halcam::PipeThread` 클래스는 각 `RequestManager` 에 한 개의 워커 스레드를 소유하며, 이 스레드는 프레임 큐를 드레인하는 역할을 수행합니다 `pipeline/PipeThread.h:14`. 프레임이 제출되는 호출은 프레임워크 스레드에서 이루어질 수 있으나, 실제 처리 로직은 `PipeThread` 의 워커 스레드 내부에서 실행됩니다 `pipeline/PipeThread.h:14`. `PipeThread` 의 생성자 `PipeThread()` 는 초기화 작업만 수행하고, `start()` 메서드를 호출하여 워커 스레드를 시작합니다 `pipeline/PipeThread.cpp:6`, `pipeline/PipeThread.cpp:10`. `stop()` 메서드는 카메라 장치의 닫힘 과정에서 호출되며, 남은 프레임을 드레인한 후 워커 스레드를 종료합니다 `pipeline/PipeThread.cpp:8`, `pipeline/PipeThread.cpp:17`. 프레임 처리를 위해 큐에 프레임을 추가하는 `enqueue()` 메서드는 반환 값이 false 일 때만 워커 스레드가 중지되었음을 의미하며, 이 호출은 프레임워크 스레드에서 발생할 수 있습니다 `pipeline/PipeThread.cpp:27`, `pipeline/PipeThread.cpp:10`.

확인 필요: 이 절의 내용은 정적 분석 결과입니다. 콜백 실행 스레드와 종료 순서는 코드를 직접 실행해서 확인해야 합니다.

??? note "근거와 검토 정보"
    - 근거 파일: `pipeline/PipeThread.cpp`, `pipeline/PipeThread.h`
    - 근거 수준: 코드 확인 (정적 분석, simple_compdb 구성, commit `?`)
    - 인용 검증: 통과
    - 검토: 2026-09-17 · ollama/qwen3.5:4b · 사람 검토 전

다음 단계: [변경 시 지켜야 할 제약](constraints.md)
