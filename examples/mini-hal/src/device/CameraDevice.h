#pragma once
#include <memory>
#include "hal3/types.h"
#include "device/RequestManager.h"

namespace halcam {

// HAL3 device object. One instance per opened camera id.
// Framework calls arrive on the framework thread; results are sent from PipeThread.
class CameraDevice {
public:
    explicit CameraDevice(int cameraId);
    ~CameraDevice();

    // Registers framework callbacks. Must precede configureStreams.
    int initialize(const camera3_callback_ops_t *callbacks);
    // Validates the stream set and resets the request manager.
    int configureStreams(camera3_stream_configuration_t *config);
    // Submits one capture request. Returns after the frame is queued, not after it completes.
    int processCaptureRequest(camera3_capture_request_t *request);
    // Drops queued frames and waits for in-flight frames.
    int flush();
    // Releases the request manager. The device must not be used afterwards.
    int close();

private:
    int validateStreams(const camera3_stream_configuration_t &config);

    int cameraId_;
    const camera3_callback_ops_t *callbacks_ = nullptr;
    std::unique_ptr<RequestManager> requests_;
    bool configured_ = false;
};

}  // namespace halcam
