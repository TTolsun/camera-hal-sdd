// HAL module entry points. The framework loads the module and calls these C functions.
#include <memory>
#include "device/CameraDevice.h"

using halcam::CameraDevice;

namespace {
constexpr int kCameraCount = 2;
}

// Returns the number of cameras this HAL exposes.
extern "C" int get_number_of_cameras() {
    return kCameraCount;
}

// Opens a camera device. The caller owns the returned device and must call camera_device_close.
extern "C" int camera_device_open(int cameraId, CameraDevice **device) {
    if (cameraId < 0 || cameraId >= kCameraCount) {
        return -1;
    }
    *device = new CameraDevice(cameraId);
    return 0;
}

// Closes and deletes a device returned by camera_device_open.
extern "C" int camera_device_close(CameraDevice *device) {
    if (device == nullptr) {
        return -1;
    }
    int ret = device->close();
    delete device;
    return ret;
}
