---
generated_at: 2026-09-17T14:11:56+00:00
source_commit: 
agent: ollama/qwen3.5:4b
status: ok
section: overview
---

# 시스템 개요

**수정할 기능이 어느 패키지에 있는지 아래 표에서 먼저 찾으세요.**

| 지금 확인할 내용 | 이동할 절 |
|---|---|
| 수정할 패키지를 찾습니다. | [패키지별 역할](#패키지별-역할) |
| 프레임워크에서 HAL 로 들어오는 진입점을 찾습니다. | [HAL 진입점](#hal-진입점) |
| 코드를 처음 읽습니다. | [코드를 처음 읽는 순서](#코드를-처음-읽는-순서) |
| 클래스 단위 책임을 확인합니다. | [컴포넌트 구조와 책임](components.md) |

## 패키지별 역할

| 패키지 | 클래스 수 | 대표 클래스 |
|---|---|---|
| `device` | 2 | `halcam::RequestManager`, `halcam::CameraDevice` |
| `hal3` | 5 | `camera3_stream`, `camera3_stream_configuration`, `camera3_capture_request`, `camera3_capture_result`, `camera3_callback_ops` |
| `pipeline` | 8 | `halcam::Frame`, `halcam::Pipe`, `halcam::IspPipe`, `halcam::SatPipe`, `halcam::FrameFactory` |

## 패키지 사이의 의존

| 방향 | 관계 종류 | 관계 수 |
|---|---|---|
| `device` → `pipeline` | association | 4 |
| `device` → `hal3` | association | 2 |

## HAL 진입점

| 함수 | 위치 | 설명 |
|---|---|---|
| `camera_device_close()` | `module/CameraModule.cpp:26` | Closes and deletes a device returned by camera_device_open. |
| `camera_device_open()` | `module/CameraModule.cpp:17` | Opens a camera device. The caller owns the returned device and must call camera_device_close. |
| `get_number_of_cameras()` | `module/CameraModule.cpp:12` | Returns the number of cameras this HAL exposes. |

## 코드를 처음 읽는 순서

1. `device/CameraDevice.cpp` 에서 `submit()` 부분을 읽습니다.
2. `device/RequestManager.cpp` 에서 `selectFactory()` 부분을 읽습니다.
3. `pipeline/FrameFactory.cpp` 에서 `buildPipes()` 부분을 읽습니다.

이 순서는 `캡처 요청 처리 (processCaptureRequest)` 시나리오의 호출 경로에서 만들었습니다. 자세한 흐름은 시나리오 문서 [캡처 요청 처리 (processCaptureRequest)](scenarios/process_capture_request.md) 에서 확인하세요.

## 구조 설명

이 HAL 은 `device`, `hal3`, `pipeline` 패키지로 나뉘며, 프레임워크 진입점은 `camera_device_open()` 함수입니다 `module/CameraModule.cpp:17`. `device` 패키지는 카메라 장치 관리를 담당하고, `hal3`는 하드웨어 인터페이스를, `pipeline`은 이미지 처리 파이프라인을 구현합니다. 패키지 간 의존 관계는 `device`가 `pipeline`과 `hal3`를 각각 참조하며, 이는 4 개와 2 개의 association 관계로 나타납니다 `device/CameraDevice.h:10`, `device/CameraDevice.cpp:5`. 프레임워크는 `camera_device_open()` 를 호출하여 장치 객체를 얻고, 이후 `processCaptureRequest()` 를 통해 캡처 요청을 제출합니다 `device/CameraDevice.cpp:40`.

`CameraDevice` 는 프레임워크 스레드에서 호출되는 콜백을 등록하고, `initialize()` 함수를 통해 이를 설정합니다 `device/CameraDevice.cpp:9`. `configureStreams()` 함수는 스트림 세트를 유효성 검사한 후 요청 매니저를 초기화하며, 이는 `processCaptureRequest()` 가 실행되기 전 필수 단계입니다 `device/CameraDevice.cpp:27`. 프레임워크 스레드에서 `camera_device_open()` 이 반환한 장치 객체는 호출자가 소유하며, 해당 객체는 `close()` 를 통해 해제됩니다 `device/CameraDevice.cpp:54`.

`RequestManager` 는 캡처 요청이 제출된 후 결과 콜백이 호출될 때까지 비행 중인 프레임을 소유합니다. 프레임은 여기서 생성되어 `PipeThread` 에서 처리되며, 완료 시에는 `onFrameDone()` 을 통해 반환됩니다 `device/RequestManager.h:14`. `selectFactory()` 함수는 요청에 따라 미리보기 또는 캡처 경로를 선택하고, `submit()` 은 해당 팩토리를 사용하여 프레임을 생성하여 작업자에게 전달합니다 `device/RequestManager.cpp:15`, `device/RequestManager.cpp:23`. `PipeThread` 는 작업자 스레드로, 프레임 큐를 드레인하며 `enqueue()` 를 통해 프레임이 처리될 때까지 대기합니다 `pipeline/PipeThread.cpp:27`.

프레임은 `FrameFactory` 에 의해 생성되어 파이프라인을 거쳐 처리되며, `createFrame()` 함수는 요청에 맞는 프레임을 만듭니다 `pipeline/FrameFactory.cpp:5`. `buildPipes()` 는 구체적인 팩토리가 어떤 파이프를 연결할지 결정하며, 이는 `PreviewFrameFactory` 나 `halcam::FrameFactory` 에서 수행됩니다 `pipeline/FrameFactory.cpp:25`, `pipeline/FrameFactory.cpp:35`. ISP 단계는 항상 존재하며, `IspPipe.process()` 는 이미지 신호 처리 단계를 수행합니다 `pipeline/Pipe.cpp:6`.

캡처 경로는 ISP 를 거쳐 SAT(공간 정렬) 단계를 거치며, 이는 `-DUSE_SAT` 플래그가 설정된 경우에만 컴파일됩니다. `SatPipe.alignWithSecondary()` 함수는 두 카메라의 영상을 정렬하는 역할을 합니다 `pipeline/Pipe.cpp:20`. 프레임워크 스레드에서 `camera_device_close()` 를 호출하면 장치 객체가 삭제되고, 이는 `close()` 함수를 통해 수행됩니다 `module/CameraModule.cpp:26`, `device/CameraDevice.cpp:54`.

프레임 처리 완료 후 결과는 `camera3_callback_ops` 의 `process_capture_result` 를 통해 프레임워크에 전달됩니다 `hal3/types.h:30`. `flush()` 함수는 큐에 대기 중인 프레임을 모두 버리고 비행 중인 프레임을 기다립니다 `device/CameraDevice.cpp:47`. 파이프라인은 `validateStreams()` 를 통해 스트림 구성을 검증하며, 이는 `configureStreams()` 에서 호출됩니다 `device/CameraDevice.cpp:14`.

??? note "근거와 검토 정보"
    - 근거 파일: `device/CameraDevice.cpp`, `device/CameraDevice.h`, `device/RequestManager.cpp`, `device/RequestManager.h`, `hal3/types.h`, `module/CameraModule.cpp`, `pipeline/Frame.h`, `pipeline/FrameFactory.cpp`, `pipeline/FrameFactory.h`, `pipeline/Pipe.cpp`, `pipeline/Pipe.h`, `pipeline/PipeThread.cpp`, `pipeline/PipeThread.h`
    - 근거 수준: 코드 확인 (정적 분석, simple_compdb 구성, commit `?`)
    - 인용 검증: 통과
    - 검토: 2026-09-17 · ollama/qwen3.5:4b · 사람 검토 전

다음 단계: [컴포넌트 구조와 책임](components.md)
