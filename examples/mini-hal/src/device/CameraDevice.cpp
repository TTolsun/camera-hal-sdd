#include "device/CameraDevice.h"

namespace halcam {

CameraDevice::CameraDevice(int cameraId) : cameraId_(cameraId) {}

CameraDevice::~CameraDevice() { close(); }

int CameraDevice::initialize(const camera3_callback_ops_t *callbacks) {
    callbacks_ = callbacks;
    return 0;
}

int CameraDevice::validateStreams(const camera3_stream_configuration_t &config) {
    if (config.num_streams == 0 || config.num_streams > MAX_PIPES) {
        return -1;
    }
#if USE_DUAL_CAMERA
    // Dual camera needs an even number of streams: one per physical camera.
    if (config.num_streams % 2 != 0) {
        return -1;
    }
#endif
    return 0;
}

int CameraDevice::configureStreams(camera3_stream_configuration_t *config) {
    if (callbacks_ == nullptr || config == nullptr) {
        return -1;
    }
    if (validateStreams(*config) != 0) {
        return -1;
    }
    // Reconfiguration drops the previous manager and every in-flight frame with it.
    requests_ = std::make_unique<RequestManager>(callbacks_);
    configured_ = true;
    return 0;
}

int CameraDevice::processCaptureRequest(camera3_capture_request_t *request) {
    if (!configured_ || request == nullptr) {
        return -1;
    }
    return requests_->submit(*request);
}

int CameraDevice::flush() {
    if (requests_) {
        requests_->drain();
    }
    return 0;
}

int CameraDevice::close() {
    if (requests_) {
        requests_->drain();
        requests_.reset();
    }
    configured_ = false;
    return 0;
}

}  // namespace halcam
