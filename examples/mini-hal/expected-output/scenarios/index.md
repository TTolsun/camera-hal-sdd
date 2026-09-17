---
generated_at: 2026-09-17T14:15:29+00:00
source_commit: 
agent: ollama/qwen3.5:4b
status: ok
section: scenarios
---

# 핵심 시나리오 시퀀스

**추적하려는 동작의 시나리오를 표에서 고르세요. 각 시나리오는 진입 함수부터 호출 순서를 번호로 보여 줍니다.**

| 지금 확인할 내용 | 이동할 절 |
|---|---|
| 디바이스 종료 (camera_device_close) 흐름을 추적합니다. | [디바이스 종료 (camera_device_close)](close_device.md) |
| 스트림 구성 (configureStreams) 흐름을 추적합니다. | [스트림 구성 (configureStreams)](configure_streams.md) |
| 플러시 (flush) 흐름을 추적합니다. | [플러시 (flush)](flush.md) |
| 워커 스레드 프레임 처리 (onFrame) 흐름을 추적합니다. | [워커 스레드 프레임 처리 (onFrame)](frame_processing.md) |
| 디바이스 오픈 (camera_device_open) 흐름을 추적합니다. | [디바이스 오픈 (camera_device_open)](open_device.md) |
| 캡처 요청 처리 (processCaptureRequest) 흐름을 추적합니다. | [캡처 요청 처리 (processCaptureRequest)](process_capture_request.md) |

## 시나리오 목록

| 시나리오 | 진입점 | 단계 수 | 미해결 호출 |
|---|---|---|---|
| [디바이스 종료 (camera_device_close)](close_device.md) | `camera_device_close(halcam::CameraDevice *)` | 2 | 0 |
| [스트림 구성 (configureStreams)](configure_streams.md) | `halcam::CameraDevice::configureStreams(camera3_stream_configuration_t *)` | 1 | 0 |
| [플러시 (flush)](flush.md) | `halcam::CameraDevice::flush()` | 1 | 0 |
| [워커 스레드 프레임 처리 (onFrame)](frame_processing.md) | `halcam::RequestManager::onFrame(halcam::Frame &)` | 7 | 1 |
| [디바이스 오픈 (camera_device_open)](open_device.md) | `camera_device_open(int, halcam::CameraDevice **)` | 1 | 0 |
| [캡처 요청 처리 (processCaptureRequest)](process_capture_request.md) | `halcam::CameraDevice::processCaptureRequest(camera3_capture_request_t *)` | 10 | 0 |

??? note "근거와 검토 정보"
    - 근거 파일: (없음)
    - 근거 수준: 코드 확인 (정적 분석, simple_compdb 구성, commit `?`)
    - 인용 검증: 통과
    - 검토: 2026-09-17 · ollama/qwen3.5:4b · 사람 검토 전

다음 단계: [Feature flag 매트릭스](../feature-flags.md)
