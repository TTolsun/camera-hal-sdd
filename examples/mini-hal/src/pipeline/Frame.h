#pragma once
#include <cstdint>
#include <string>

namespace halcam {

// One capture in flight. Created by a FrameFactory, consumed by pipes, released by RequestManager.
struct Frame {
    uint32_t frameNumber = 0;
    void *buffer = nullptr;
    void *secondaryBuffer = nullptr;  // Only set when USE_DUAL_CAMERA is enabled.
    std::string stage;
    bool isPreview = false;
};

}  // namespace halcam
